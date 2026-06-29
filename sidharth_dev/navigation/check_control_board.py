'''
This file checks that the MOTOR CONTROL BOARD (Yahboom expansion board, CH340
USB-serial, 1a86:7523) is actually connected AND that /dev/myserial is wired to
it - not to the LiDAR. It is the missing "identity" check: the other checkers
prove that *a* serial port exists and that *some* board answers, but none of them
verify that /dev/myserial points at the right chip. That gap is exactly what let
a mis-pointed udev rule (myserial -> the LiDAR) and a loose USB cable hide.
'''

# check_control_board.py - connectivity / identity gate for the control board.
# It deliberately does NOT open the serial port: check_motors.py already does the
# functional "open the board, read firmware + battery" test, and the port is
# single-access. This checker only inspects the *plumbing*, so it is fast, needs
# no ROS / Rosmaster_Lib (pure os + udevadm, so it always imports), and is safe to
# run even while a driver owns the port.
#
# What it checks, in order - each layer gives a SPECIFIC diagnosis:
#   1. check_usb     - is the control board's OWN chip (1a86:7523) on the USB bus?
#                      a miss here == the board never enumerated -> loose cable /
#                      no power (the "lights on but no ttyUSB" failure). this is
#                      stricter than check_motors.check_usb, which matches ANY
#                      serial bridge and so passes off the LiDAR alone.
#   2. check_present - does /dev/myserial exist and is it read/write (dialout)?
#                      a miss == the udev symlink isn't being created (rule
#                      disabled), the link is dangling, or we lack 'dialout'.
#   3. check_working - does /dev/myserial actually RESOLVE to 1a86:7523? this is
#                      the real point. if it resolves to 10c4:ea60 we say so out
#                      loud: "myserial is bound to the LiDAR" - the udev mis-bind
#                      that cost a whole debugging session. number-independent:
#                      we don't care which ttyUSBx it is, only which chip is behind
#                      it. cross-checked against the by-id link as a second witness.
#
# Two ways to read the result (same contract as check_motors / check_camera):
#   - every check_* method RETURNS a status dict       -> use it as a status code
#   - assert_ok() RAISES ControlBoardError on first fail -> hard gate before bringup
#
# How to run:
#   cd ~/sidharth_dev/navigation
#   python3 check_control_board.py        # prints a report, exits 0 if all good
#   # chain it so you only bring up the robot if myserial is correctly wired:
#   # python3 check_control_board.py && ros2 launch yahboomcar_bringup ...

import os
import sys
import subprocess


# the control board's USB-serial bridge: QinHeng CH340, vendor:product 1a86:7523.
# (the LiDAR is the OTHER chip, Silicon Labs CP210x = 10c4:ea60 - we name it so we
#  can produce the specific "you're pointed at the LiDAR" message instead of a
#  generic mismatch.)
EXPECTED_VID, EXPECTED_PID = "1a86", "7523"
LIDAR_VID,    LIDAR_PID    = "10c4", "ea60"

MYSERIAL = "/dev/myserial"
# udev creates this stable by-id link ONLY when the CH340 actually enumerates, so
# it doubles as an independent "is the board on the bus + which tty" witness.
BY_ID = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"


class ControlBoardError(Exception):
    '''Raised by assert_ok() when the board is missing or myserial is mis-wired.'''
    pass


# same status shape every checker uses, so the combined table stays uniform.
def status(name, ok, detail=""):
    return {"name": name, "status": "ok" if ok else "fail", "detail": detail}


# ---- helper: udev's view of a device node (follows the symlink) ----
# returns (vid, pid) lowercased, or (None, None) if it isn't a USB device or the
# node is missing. udevadm reports ID_VENDOR_ID / ID_MODEL_ID for USB-serial ttys;
# a Tegra UART (ttyTHS1) has neither, which is how we tell them apart.
def _usb_ids(node):
    try:
        out = subprocess.check_output(
            ["udevadm", "info", "-q", "property", "-n", node],
            text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None, None
    props = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
    vid = (props.get("ID_VENDOR_ID") or "").lower()
    pid = (props.get("ID_MODEL_ID") or "").lower()
    return (vid or None), (pid or None)


class ControlBoardCheck:
    '''One object, one method per layer. Run them individually, or run_all() /
    assert_ok() for the whole sweep.'''

    # ============ CHECK 1: is the CH340 (1a86:7523) on the USB bus? ============
    def check_usb(self):
        try:
            out = subprocess.check_output(["lsusb"], text=True)
        except Exception as e:
            return status("usb", False, f"couldn't run lsusb: {e}")
        usb_id = f"{EXPECTED_VID}:{EXPECTED_PID}"
        for line in out.splitlines():
            if usb_id in line:
                return status("usb", True, line.strip())
        return status("usb", False,
                      f"{usb_id} (CH340 control board) not on USB bus - "
                      "loose cable / board unpowered?")

    # ============ CHECK 2: is /dev/myserial present and openable? ============
    def check_present(self):
        if not os.path.exists(MYSERIAL):
            # distinguish "no link at all" from "link points at a gone target".
            if os.path.islink(MYSERIAL):
                return status("present", False,
                              f"{MYSERIAL} is a DANGLING symlink -> "
                              f"{os.readlink(MYSERIAL)} (target gone - "
                              "board not enumerated?)")
            return status("present", False,
                          f"{MYSERIAL} missing (udev symlink not created - "
                          "rule disabled, or board not enumerated)")
        if not (os.access(MYSERIAL, os.R_OK) and os.access(MYSERIAL, os.W_OK)):
            return status("present", False,
                          f"{MYSERIAL} exists but no R/W access (add user to 'dialout')")
        return status("present", True,
                      f"{MYSERIAL} -> {os.path.realpath(MYSERIAL)}")

    # ============ CHECK 3: does /dev/myserial resolve to the CONTROL BOARD? ====
    # the identity check - the whole reason this file exists.
    def check_working(self):
        if not os.path.exists(MYSERIAL):
            return status("identity", False, f"{MYSERIAL} missing - see 'present'")

        vid, pid = _usb_ids(MYSERIAL)
        real = os.path.realpath(MYSERIAL)

        if vid is None:
            return status("identity", False,
                          f"{MYSERIAL} -> {real}: not a USB device "
                          "(Tegra UART ttyTHS1?) - can't confirm it's the board")
        if (vid, pid) == (LIDAR_VID, LIDAR_PID):
            return status("identity", False,
                          f"{MYSERIAL} -> {real} is the LiDAR ({vid}:{pid})! "
                          "udev rule mis-pointed - rebind myserial to "
                          f"{EXPECTED_VID}:{EXPECTED_PID}")
        if (vid, pid) != (EXPECTED_VID, EXPECTED_PID):
            return status("identity", False,
                          f"{MYSERIAL} -> {real} is {vid}:{pid}, expected "
                          f"control board {EXPECTED_VID}:{EXPECTED_PID}")

        # right chip. confirm the independent by-id witness agrees on the tty.
        witness = ""
        if os.path.exists(BY_ID):
            if os.path.realpath(BY_ID) != real:
                witness = "  (warning: by-id link resolves elsewhere!)"
        else:
            witness = "  (note: 1a86 by-id link absent)"
        return status("identity", True,
                      f"{MYSERIAL} -> {real} is the control board "
                      f"({vid}:{pid}){witness}")

    # ---- run every check, hand back the list of results ----
    def run_all(self):
        return [self.check_usb(), self.check_present(), self.check_working()]

    # ---- the "interface gate": raise instead of return ----
    # call this before bringup to refuse to launch onto a mis-wired myserial.
    def assert_ok(self):
        for r in self.run_all():
            if r["status"] == "fail":
                raise ControlBoardError(f"{r['name']}: {r['detail']}")
        return True


def print_report(results):
    print("\n=== control board check ===")
    n_fail = 0
    for r in results:
        tag = "[ ok ]" if r["status"] == "ok" else "[FAIL]"
        if r["status"] == "fail":
            n_fail += 1
        print(f"  {tag} {r['name']:<10} {r['detail']}")
    print(f"\n{len(results)} checks, {n_fail} failed.")
    return n_fail


def main():
    results = ControlBoardCheck().run_all()
    n_fail = print_report(results)
    # exit 0 if everything passed, 1 otherwise -> chainable before a bringup launch
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
