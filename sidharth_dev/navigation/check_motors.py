import rclpy
from rclpy.node import Node

'''
This file should check that the motors are connected to the robot.
DO NOT TOUCH
'''

# check_motors.py - health check / interface gate for the motors / Yahboom driver
# board, mirroring check_camera.py. Same idea: fail loudly with a clear message
# instead of publishing cmd_vel into the void and wondering why the wheels don't move.
#
# What it checks, in order:
#   1. usb scan   - is a USB-serial bridge (CP2102/CH340) for the board present?
#                   (the board may instead sit on the Tegra UART /dev/ttyTHS1, in
#                    which case it won't show in lsusb - that's noted, not fatal)
#   2. list       - print every serial port + the Yahboom udev symlinks
#   3. present    - is a usable board serial port there (and do we have dialout)?
#   4. working    - open the board (Rosmaster_Lib) and read firmware version +
#                   battery voltage; a real version + sane voltage == board alive
#                   (the motor equivalent of the camera "is it an all-black frame?")
#
# Two ways to read the result, same as check_camera:
#   - every check_* method RETURNS a status dict   -> use it as a status code
#   - assert_ok() RAISES MotorError on first fail  -> hard gate before driving
#
# How to run:
#   cd ~/sidharth_dev/navigation
#   source /opt/ros/humble/setup.bash      # only needed for the (commented) odom check
#   python3 check_motors.py                # prints a report, exits 0 if all good
#
#   # chain it so you only drive if the board answers:
#   # python3 check_motors.py && python3 go_foward.py
#
# IMPORTANT - the board's serial port is SINGLE-ACCESS (one program at a time):
#   * if yahboomcar_bringup is running it OWNS the board's port, so check 4
#     ('working') will fail "busy" - that's expected, and an /odom check would pass.
#   * if bringup is NOT running, check 4 can open the board directly and read it,
#     but /odom won't be published. Same single-access situation as the camera.

import os
import sys
import glob
import time
import subprocess

from Rosmaster_Lib import Rosmaster


# the board talks over a serial UART. Rosmaster_Lib defaults to /dev/myserial
# (-> ttyUSB0). on this jetson ttyUSB0 (CP2102) is most likely the LIDAR and the
# board is on /dev/ttyTHS1 (the 40-pin UART) - so we try several ports and keep
# whichever answers with a real firmware version.
MOTOR_PORTS = ["/dev/myserial", "/dev/ttyUSB0", "/dev/ttyTHS1"]
ODOM_TOPIC = "/odom"

# get_version() returns a float > 0 only when a real Yahboom board answers.
# battery is the pack voltage; a healthy pack sits in this window. 0 / garbage
# means the port opened but nothing on the other end is actually the board.
BATTERY_MIN = 6.0
BATTERY_MAX = 13.0


class MotorError(Exception):
    '''Raised by assert_ok() when the board is missing or not responding.'''
    pass


# every check returns this same little dict so callers always get the same shape.
# "status" is the status code: "ok" or "fail". (identical to check_camera.status)
def status(name, ok, detail=""):
    return {"name": name, "status": "ok" if ok else "fail", "detail": detail}


class MotorCheck:
    '''
    One object, one method per check. Call them individually, or run_all() /
    assert_ok() to do the whole sweep.
    '''

    # ---- helper: candidate ports that exist, deduped by real path ----
    # /dev/myserial is a symlink to ttyUSB0, so without the realpath dedup we'd
    # try the exact same port twice. (same trick as test.py's probe_board.)
    def _ports(self):
        seen, out = set(), []
        for p in MOTOR_PORTS:
            if os.path.exists(p):
                real = os.path.realpath(p)
                if real not in seen:
                    seen.add(real)
                    out.append(p)
        return out

    # ============ CHECK 1: usb-serial bridge scan ============
    # is a USB-serial chip the board could be on plugged in? lsusb dumps every usb
    # device; we look for a CP210x / CH340 / UART line. NOT fatal if absent - the
    # board may be wired to the Tegra UART (ttyTHS1), which never shows in lsusb.
    def check_usb(self):
        try:
            out = subprocess.check_output(["lsusb"], text=True)
        except Exception as e:
            return status("usb", False, f"couldn't run lsusb: {e}")
        for line in out.splitlines():
            low = line.lower()
            if "cp210" in low or "ch340" in low or "uart" in low or "serial" in low:
                return status("usb", True, line.strip())
        return status("usb", False,
                      "no USB-serial bridge in lsusb (board may be on /dev/ttyTHS1 UART)")

    # ============ CHECK 2: list every serial port ============
    # not pass/fail - the "show me what the OS can see" dump so I can eyeball which
    # tty is the board vs the lidar. prints the raw ports AND the Yahboom udev
    # symlinks (myserial/rplidar/ydlidar) so the aliasing is obvious.
    def list_devices(self):
        print("\n--- serial ports ---")
        ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
                       + glob.glob("/dev/ttyTHS*"))
        print("  " + (", ".join(ports) if ports else "(none)"))

        print("\n--- Yahboom udev symlinks ---")
        any_link = False
        for link in ("/dev/myserial", "/dev/rplidar", "/dev/ydlidar"):
            if os.path.exists(link):
                print(f"  {link} -> {os.path.realpath(link)}")
                any_link = True
        if not any_link:
            print("  (none)")

        return status("list", True, "printed above")

    # ============ CHECK 3: is a board port present (and openable)? ============
    # the tty node IS the OS handle for the board. it also has to be readable AND
    # writable - the board ports are group 'dialout', so without that group you
    # can see the file but can't open it (the exact gotcha test.py hit).
    def check_present(self):
        ports = self._ports()
        if not ports:
            return status("present", False,
                          f"none of {MOTOR_PORTS} exist (board unplugged / unpowered?)")
        usable = [p for p in ports if os.access(p, os.R_OK) and os.access(p, os.W_OK)]
        if not usable:
            return status("present", False,
                          f"ports exist {ports} but no R/W access (add user to 'dialout' group)")
        return status("present", True, f"usable serial port(s): {usable}")

    # ============ CHECK 4: open the board, read version + battery ============
    # the motor equivalent of check_camera.check_working: actually talk to the
    # device and prove it's real. open each candidate port with Rosmaster_Lib,
    # start the receive thread, and read get_version()/get_battery_voltage(). a
    # version > 0 means a real board answered; battery is reported and sanity-checked
    # (a 0V / wildly-off reading is the "all-black frame" of motors).
    def check_working(self):
        present = self.check_present()
        if present["status"] == "fail":
            return present

        for port in self._ports():
            if not (os.access(port, os.R_OK) and os.access(port, os.W_OK)):
                continue
            bot = None
            try:
                bot = Rosmaster(com=port)
                bot.create_receive_threading()   # bg thread parses incoming frames
                time.sleep(1.0)                  # give it a moment to read a frame
                ver = bot.get_version()
                batt = bot.get_battery_voltage()
                if ver and float(ver) > 0:
                    ok_batt = BATTERY_MIN <= batt <= BATTERY_MAX
                    note = "" if ok_batt else "  (battery reading looks off!)"
                    return status("working", True,
                                  f"board v{ver} @ {port}, battery {batt:.1f}V{note}")
            except Exception:
                pass
            finally:
                # close the port explicitly so bringup can use it later, and so we
                # don't trip Rosmaster's noisy __del__ on a half-open handle.
                if bot is not None and hasattr(bot, "ser"):
                    try:
                        bot.ser.close()
                    except Exception:
                        pass

        return status("working", False,
                      "no board answered (busy with bringup? wrong port? unpowered?)")

    # ============ CHECK 5: is /odom actually being PUBLISHED? ============
    # the only ROS check: subscribe to /odom for a couple seconds and confirm the
    # driver is emitting odometry. needs ROS sourced + yahboomcar_bringup running
    # (which would also hold the board's port, so check 4 would be 'busy'). left
    # commented out, exactly like check_camera's check_published.
    '''
    def check_odom(self, window=3.0):
        try:
            import rclpy
            from nav_msgs.msg import Odometry
        except Exception as e:
            return status("odom", False, f"ROS not available (did you source it?): {e}")

        started_here = not rclpy.ok()
        if started_here:
            rclpy.init()
        node = rclpy.create_node("motor_check_sub")
        msgs = []
        node.create_subscription(Odometry, ODOM_TOPIC, lambda m: msgs.append(m), 10)
        end = time.time() + window
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
        node.destroy_node()
        if started_here:
            rclpy.shutdown()

        if not msgs:
            return status("odom", False,
                          f"no /odom in {window:.0f}s (is yahboomcar_bringup running?)")
        return status("odom", True, f"{len(msgs) / window:.1f} Hz on {ODOM_TOPIC}")
        '''

    # ---- run every check and hand back the list of results ----
    def run_all(self):
        results = []
        results.append(self.check_usb())
        self.list_devices()              # informational, prints its own dump
        results.append(self.check_present())
        results.append(self.check_working())
        # results.append(self.check_odom())
        return results

    # ---- the "interface gate": raise instead of return ----
    # call this before driving. only gates on being able to OPEN+read the board
    # (present/working), NOT on /odom - bringup can't be running yet if we're about
    # to start it, and it would also hold the port and make check_working fail busy.
    def assert_ok(self):
        for r in (self.check_present(), self.check_working()):
            if r["status"] == "fail":
                raise MotorError(f"{r['name']}: {r['detail']}")
        return True


def print_report(results):
    print("\n=== motor check ===")
    n_fail = 0
    for r in results:
        tag = "[ ok ]" if r["status"] == "ok" else "[FAIL]"
        if r["status"] == "fail":
            n_fail += 1
        print(f"  {tag} {r['name']:<10} {r['detail']}")
    print(f"\n{len(results)} checks, {n_fail} failed.")
    return n_fail


def main():
    check = MotorCheck()
    results = check.run_all()
    n_fail = print_report(results)
    # exit 0 if everything passed, 1 otherwise -> lets you chain this in a script
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
