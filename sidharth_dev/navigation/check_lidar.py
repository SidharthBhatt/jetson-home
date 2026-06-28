#!/usr/bin/env python3
'''
check_lidar.py - health check / interface gate for the LiDAR, mirroring
check_audio.py and check_camera.py. Same idea: fail loudly with a clear message
instead of letting SLAM / nav2 start up against a dead lidar and then wondering
why the map never builds and /scan is empty.

What it checks, in order:

1. usb scan   - is the lidar's USB-UART bridge plugged in? The YDLidar talks
                over a Silicon Labs CP2102 (10c4:ea60). NOTE this is a DIFFERENT
                chip from the robot's control board (a CH340, 1a86:7523) - both
                show up as ttyUSB*, so we match on the CP2102 specifically.
2. list       - print every serial device + the /dev/serial/by-id symlinks, so I
                can eyeball which ttyUSB is the lidar vs the control board.
3. present    - is /dev/ydlidar there at all? (the udev symlink, see below)
4. working    - open /dev/ydlidar, START the scan, read ~1s of raw bytes and make
                sure data is actually flowing, then STOP the scan again. This is
                the lidar equivalent of the audio "is it silent?" RMS test and the
                camera "is it all-black?" mean-pixel test: prove real data comes
                off the device, no ROS required.

Two ways to read the result, same as check_audio / check_camera:
  - every check_* method RETURNS a status dict   -> use it as a status code
  - assert_ok() RAISES LidarError on first fail   -> hard gate before a pipeline

How to run:
    cd ~/sidharth_dev/navigation
    python3 check_lidar.py                 # prints a report, exits 0 if all good

    # chain it so the lidar driver only starts if the lidar is alive:
    # python3 check_lidar.py && ros2 launch ydlidar_ros2_driver ydlidar_launch.py ...

Note: like check_audio (and unlike the SLAM/nav stuff), checks 1-4 do NOT need ROS
sourced - we talk to the lidar straight over its serial port with pyserial. The
optional check_scan() at the bottom is the only ROS-dependent piece, and it's
commented out by default for exactly the reason check_camera's check_published is:
single-access (see below).

Two YDLidar-specific gotchas, both verified on this robot:

  * /dev/ydlidar, NOT /dev/ttyUSB0. ttyUSB enumeration order is NOT stable across
    reboots - the lidar (CP2102) and the control board (CH340) race for ttyUSB0 vs
    ttyUSB1. udev (/etc/udev/rules.d/ydlidar.rules) pins the CP2102 to a stable
    /dev/ydlidar symlink, and the driver's params point at /dev/ydlidar too, so we
    use that and never trust the bare ttyUSB number. (Same spirit as check_audio
    hunting the ORBBEC pulse source by name instead of trusting the default.)

  * the lidar does NOT stream on its own. Open the port and just read and you get
    ZERO bytes forever - it sits idle until it's told to spin. So check_working
    sends the YDLidar scan-START command (0xA5 0x60), reads, then ALWAYS sends
    scan-STOP (0xA5 0x65) so we don't leave the motor spinning.

  * SINGLE-ACCESS, like the camera: only one program can hold the serial port. If
    the ydlidar driver is already running it OWNS /dev/ydlidar, so check_working
    will report "busy" - that's expected; the live proof of life is then /scan
    (run check_scan with the driver up). You normally won't see check_working green
    AND the driver running at the same time; that's the port being single-access,
    not a bug.
'''

import os
import sys
import time
import subprocess

import serial


# the lidar's stable udev symlink (-> the CP2102 bridge, currently ttyUSB0). the
# driver's params_file points here too. if you ever swap the lidar, check
# /etc/udev/rules.d/ydlidar.rules and `ls -l /dev/serial/by-id/`.
LIDAR_DEV = "/dev/ydlidar"

# baud the YDLidar talks at - taken straight from ydlidar_reliable.yaml
# (baudrate: 512000). wrong baud = garbage / zero bytes even on a healthy lidar.
LIDAR_BAUD = 512000

LIDAR_TOPIC = "/scan"

# YDLidar control bytes: every command is 0xA5 then an opcode.
SCAN_START = bytes([0xA5, 0x60])   # spin up + start streaming scan data
SCAN_STOP  = bytes([0xA5, 0x65])   # stop streaming + let it idle again

# the device replies to a command with a 7-byte response header that starts with
# this sync pair. seeing it back means we're really talking to the lidar and not
# just reading line noise.
RESP_SYNC = bytes([0xA5, 0x5A])

# a healthy lidar pushes ~5 KB/s once spinning, so ~1s should be thousands of
# bytes. anything below this in our read window means it never actually started
# streaming -> asleep, wrong baud, or not powered.
MIN_BYTES = 200


class LidarError(Exception):
    '''Raised by assert_ok() when the lidar is missing or not streaming.'''
    pass


# every check returns this same little dict so callers always get the same shape.
# "status" is the status code: "ok" or "fail". (identical to check_audio.status)
def status(name, ok, detail=""):
    return {"name": name, "status": "ok" if ok else "fail", "detail": detail}


class LidarCheck:
    '''
    One object, one method per check. Call them individually, or run_all() /
    assert_ok() to do the whole sweep.
    '''

    # ============ CHECK 1: usb descriptor scan ============
    # is the lidar physically plugged in? lsusb dumps every usb device's
    # descriptor; we look for the CP2102 line ("CP210x" / "Silicon Labs"). catches
    # "someone unplugged the lidar" before we bother opening a serial port.
    # NB: we deliberately match the CP210x and NOT just "serial", because the CH340
    # control board is also a usb serial device - matching "serial" would pass even
    # with the lidar unplugged.
    def check_usb(self):
        try:
            out = subprocess.check_output(["lsusb"], text=True)
        except Exception as e:
            return status("usb", False, f"couldn't run lsusb: {e}")
        for line in out.splitlines():
            low = line.lower()
            if "cp210" in low or "silicon labs" in low:
                return status("usb", True, line.strip())
        return status("usb", False, "no CP210x/Silicon Labs bridge in lsusb (lidar unplugged?)")

    # ============ CHECK 2: list every serial device ============
    # not pass/fail - the "show me what the OS can see" dump so I can eyeball which
    # ttyUSB is the lidar (CP2102 -> /dev/ydlidar) vs the control board
    # (CH340 -> /dev/myserial). always returns ok (informational).
    def list_devices(self):
        print("\n--- /dev/ttyUSB* nodes ---")
        nodes = sorted(p for p in os.listdir("/dev") if p.startswith("ttyUSB"))
        print("  " + (", ".join("/dev/" + n for n in nodes) if nodes else "(none)"))

        print("\n--- /dev/serial/by-id (stable names -> ttyUSB) ---")
        try:
            print(subprocess.check_output(["ls", "-l", "/dev/serial/by-id/"],
                                          text=True).strip())
        except Exception as e:
            print(f"  (couldn't list by-id: {e})")

        print("\n--- lidar/control-board symlinks ---")
        for link in ("/dev/ydlidar", "/dev/myserial"):
            if os.path.islink(link):
                print(f"  {link} -> {os.readlink(link)}")
            else:
                print(f"  {link} (missing)")

        return status("list", True, "printed above")

    # ============ CHECK 3: is the lidar port present? ============
    # /dev/ydlidar is the OS handle for the lidar. if the symlink is missing then
    # either the lidar isn't enumerated or the udev rule didn't fire, and there's
    # no point trying to open it.
    def check_present(self):
        if not os.path.exists(LIDAR_DEV):
            return status("present", False,
                          f"{LIDAR_DEV} missing (lidar not enumerated, or udev rule didn't fire)")
        target = os.path.realpath(LIDAR_DEV)
        return status("present", True, f"{LIDAR_DEV} -> {target}")

    # ============ CHECK 4: open it, start the scan, read real bytes ============
    # the lidar equivalent of check_audio.check_working / check_camera.check_working:
    # actually pull data off the device and prove it's real. open the serial port,
    # send the YDLidar START command (it won't stream otherwise), read for ~1s, and
    # confirm bytes are flowing. ALWAYS send STOP and close in a finally so we never
    # leave the motor spinning or the port locked.
    def check_working(self, window=1.2):
        present = self.check_present()
        if present["status"] == "fail":
            return present

        try:
            ser = serial.Serial(LIDAR_DEV, LIDAR_BAUD, timeout=0.3)
        except Exception as e:
            # most common cause: the ydlidar driver already holds the port
            return status("working", False,
                          f"could not open {LIDAR_DEV} (busy? ydlidar driver may be holding it): {e}")

        try:
            time.sleep(0.2)
            ser.reset_input_buffer()
            ser.write(SCAN_START)
            ser.flush()

            data = bytearray()
            end = time.time() + window
            while time.time() < end:
                data += ser.read(8192)
        finally:
            # ALWAYS stop the scan + release the port, even if something threw
            try:
                ser.write(SCAN_STOP)
                ser.flush()
                time.sleep(0.05)
            except Exception:
                pass
            ser.close()

        n = len(data)
        looks_like_lidar = RESP_SYNC in data    # did we get the 0xA5 0x5A header back?
        if n < MIN_BYTES:
            return status("working", False,
                          f"started scan but only {n} bytes in {window:.0f}s "
                          f"(lidar asleep / not powered?) -> recommended action: fully power-cycle robot")
        tag = "looks like YDLidar packets" if looks_like_lidar else "WARN: no 0xA5 0x5A header, but data flowing"
        return status("working", True, f"streaming {n} bytes in {window:.0f}s ({tag})")

    # ============ CHECK 5: is /scan actually being PUBLISHED? ============
    # the only ROS check: subscribe to /scan for a couple seconds and confirm scans
    # are arriving at a healthy rate with some finite ranges. needs ROS sourced +
    # the ydlidar driver running. (mirrors sensor_health.py's test_lidar.)
    #
    # commented out by default for the SAME reason check_camera.check_published is:
    # the driver holds /dev/ydlidar, so you'd run THIS (driver up) OR check_working
    # (driver down), not both. uncomment + source ROS when the driver is running.
    '''
    def check_scan(self, window=3.0):
        try:
            import math
            import rclpy
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import LaserScan
        except Exception as e:
            return status("scan", False, f"ROS not available (did you source it?): {e}")

        started_here = not rclpy.ok()
        if started_here:
            rclpy.init()
        node = rclpy.create_node("lidar_check_sub")
        msgs = []
        node.create_subscription(LaserScan, LIDAR_TOPIC,
                                 lambda m: msgs.append(m), qos_profile_sensor_data)
        end = time.time() + window
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
        node.destroy_node()
        if started_here:
            rclpy.shutdown()

        if not msgs:
            return status("scan", False,
                          f"no scans on {LIDAR_TOPIC} in {window:.0f}s (is the ydlidar driver running?)")
        rate = len(msgs) / window
        last = msgs[-1]
        finite = [r for r in last.ranges
                  if math.isfinite(r) and last.range_min <= r <= last.range_max]
        if not finite:
            return status("scan", False,
                          f"{rate:.1f} Hz but no finite ranges (lidar blinded / too close?)")
        return status("scan", True,
                      f"{rate:.1f} Hz on {LIDAR_TOPIC}, {len(last.ranges)} beams, {len(finite)} valid")
    '''

    # ---- run every check and hand back the list of results ----
    def run_all(self):
        results = []
        results.append(self.check_usb())
        self.list_devices()              # informational, prints its own dump
        results.append(self.check_present())
        results.append(self.check_working())
        # results.append(self.check_scan())
        return results

    # ---- the "interface gate": raise instead of return ----
    # call this before starting anything that uses the lidar. NOTE: only gates on
    # being able to OPEN + stream from the lidar (usb/present/working), NOT on
    # 'scan' - the driver can't be running yet if we're about to start it, and it
    # would also hold the port and make check_working fail busy.
    def assert_ok(self):
        for r in (self.check_usb(), self.check_present(), self.check_working()):
            if r["status"] == "fail":
                raise LidarError(f"{r['name']}: {r['detail']}")
        return True


def print_report(results):
    print("\n=== lidar check ===")
    n_fail = 0
    for r in results:
        tag = "[ ok ]" if r["status"] == "ok" else "[FAIL]"
        if r["status"] == "fail":
            n_fail += 1
        print(f"  {tag} {r['name']:<10} {r['detail']}")
    print(f"\n{len(results)} checks, {n_fail} failed.")
    return n_fail


def main():
    check = LidarCheck()
    results = check.run_all()
    n_fail = print_report(results)

    # exit 0 if everything passed, 1 otherwise -> lets you chain this in a script
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
