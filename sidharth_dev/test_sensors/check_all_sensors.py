'''
List all the connected devices and their names which are easy to identify. E.g ORBBEC depth sensor is the microphone for audio input
Call all the specific check_* methods as we wrote in check_camera.py, check_audio.py, check_lidar.py, check_motors.py,
Print the results in a table.

checkall -> bash command to run this script

DO NOT TOUCH

'''

# check_all_sensors.py - the single preflight that ties the four per-device
# checkers together. It does three things, in order:
#   1. prints the friendly "what is each device" map (ORBBEC = mic, etc.)
#   2. imports + runs every check_* class (AudioCheck / CameraCheck / LidarCheck /
#      MotorCheck) - reusing the shared check_usb/check_present/check_working that
#      all four expose
#   3. prints one combined PASS/FAIL table and exits non-zero if anything failed
#
# How to run:
#   source /opt/ros/humble/setup.bash      # camera+motor checkers import rclpy at top
#   cd ~/sidharth_dev/test_sensors
#   python3 check_all_sensors.py
#
# Notes:
#   * the four checkers live next to their device code (camera/, audio_record/,
#     navigation/), so we add those dirs to sys.path before importing them.
#   * imports are fault-tolerant: if one checker can't import (e.g. ROS not sourced,
#     so check_camera's rclpy import fails) it's reported as a failed row instead of
#     crashing the whole preflight.
#   * each check_working actually exercises its device (records 1s, grabs a frame,
#     spins the lidar ~1s, reads the board), so run this with the drivers DOWN -
#     a running driver holds the single-access port and check_working will say "busy".

import os
import sys
import importlib
import subprocess


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # ~/sidharth_dev

# (label, subdir, module, class) for each per-device checker.
SPECS = [
    ("audio",   "audio_record", "check_audio",         "AudioCheck"),
    ("camera",  "camera",       "check_camera",        "CameraCheck"),
    ("lidar",   "navigation",   "check_lidar",         "LidarCheck"),
    # control-board plumbing/identity gate - runs BEFORE motors so a mis-wired
    # /dev/myserial is diagnosed (loose cable / udev points at the LiDAR) before
    # MotorCheck's functional "open the board" check fails with a generic message.
    ("control", "navigation",   "check_control_board", "ControlBoardCheck"),
    ("motors",  "navigation",   "check_motors",        "MotorCheck"),
]

# friendly identity of every device we expect, keyed by usb vendor:product.
# this is the "ORBBEC depth sensor == the microphone" mapping the spec asked for.
KNOWN_USB = [
    ("2bc5:060f", "ORBBEC Depth Sensor",   "microphone (audio in)"),
    ("2bc5:050f", "Orbbec USB 2.0 Camera", "RGB camera -> /dev/video0"),
    ("10c4:ea60", "Silicon Labs CP2102",   "LiDAR -> /dev/ydlidar"),
    ("1a86:7523", "QinHeng CH340",         "motor control board -> /dev/myserial"),
    ("0079:181c", "DragonRise Controller", "USB gamepad (teleop)"),
]

# the three pass/fail checks EVERY check_* class exposes - the shared contract
# that makes this loop possible. list_devices() is skipped (informational only).
CORE_CHECKS = ("check_usb", "check_present", "check_working")


# same status shape every checker uses, so the combined table is uniform.
def status(name, ok, detail=""):
    return {"name": name, "status": "ok" if ok else "fail", "detail": detail}


# ---- spec item 1: friendly device map ----
def list_devices():
    try:
        lsusb = subprocess.check_output(["lsusb"], text=True)
    except Exception as e:
        lsusb = ""
        print(f"(couldn't run lsusb: {e})")
    print("=== devices on this robot ===")
    for usbid, name, role in KNOWN_USB:
        here = any(usbid in line for line in lsusb.splitlines())
        print(f"  [{'+' if here else '-'}] {name:<22} = {role}")
    print(f"  [+] {'Jetson Orin NX':<22} = compute host")


# ---- spec item 2a: import each checker (tolerating breakage) ----
def load_checks():
    loaded = []                          # each: (label, instance_or_None, error_or_None)
    for label, subdir, mod, cls in SPECS:
        path = os.path.join(ROOT, subdir)
        if path not in sys.path:
            sys.path.insert(0, path)
        try:
            module = importlib.import_module(mod)
            loaded.append((label, getattr(module, cls)(), None))
        except Exception as e:
            loaded.append((label, None, f"import failed: {e}"))
    return loaded


# ---- spec item 2b: run check_usb/present/working on each subsystem ----
def run_all_checks(loaded):
    rows = []                            # each: (subsystem_label, status_dict)
    for label, inst, err in loaded:
        if inst is None:
            rows.append((label, status("import", False, err)))
            continue
        for method in CORE_CHECKS:
            fn = getattr(inst, method, None)
            if fn is None:
                rows.append((label, status(method, False, "method missing")))
                continue
            try:
                rows.append((label, fn()))
            except Exception as e:
                rows.append((label, status(method, False, f"crashed: {e}")))
    return rows


# ---- spec item 3: one combined table ----
def print_table(rows):
    print("\n=== sensor preflight ===")
    sub_w = max((len(s) for s, _ in rows), default=6)
    chk_w = max((len(r["name"]) for _, r in rows), default=8)
    n_fail = 0
    for sub, r in rows:
        tag = "[ ok ]" if r["status"] == "ok" else "[FAIL]"
        if r["status"] == "fail":
            n_fail += 1
        print(f"  {tag} {sub:<{sub_w}}  {r['name']:<{chk_w}}  {r['detail']}")
    print(f"\n{len(rows)} checks, {n_fail} failed.")
    return n_fail


def main():
    list_devices()
    loaded = load_checks()
    rows = run_all_checks(loaded)
    n_fail = print_table(rows)
    # exit 0 if everything passed, 1 otherwise -> chainable before a bringup launch
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
