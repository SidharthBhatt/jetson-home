'''
do the same thing as you did in check_audio but for the camera.
List all camera devices, check if /dev/video0 is present, and if it is,
try to open it and save the image, make sure the image published

DO NOT CHANGE THIS COMMENT
'''

# check_camera.py - health check / interface gate for the camera, mirroring
# check_audio.py. Same idea: fail loudly with a clear message instead of letting
# the publisher silently push black frames (or no frames) and then wondering why
# rqt_image_view is blank.
#
# What it checks, in order:
#   1. usb scan   - is the camera (Sonix "USB 2.0 Camera", 2bc5:050f) plugged in?
#   2. list       - print every video device the OS can see (v4l2-ctl / /dev/video*)
#   3. present    - is /dev/video0 there at all?
#   4. working    - open /dev/video0, grab one frame, SAVE it to a jpg, and make
#                   sure it isn't an all-black frame (the camera equivalent of the
#                   audio "is it silent?" RMS test)
#   5. published  - is anyone actually publishing frames on /camera/image_raw?
#                   (this is the only check that needs ROS sourced)
#
# Two ways to read the result, same as check_audio:
#   - every check_* method RETURNS a status dict    -> use it as a status code
#   - assert_ok() RAISES CameraError on first fail  -> hard gate before a pipeline
#
# How to run:
#   cd ~/sidharth_dev/camera
#   source /opt/ros/humble/setup.bash      # only needed for the 'published' check
#   python3 check_camera.py                # prints a report, exits 0 if all good
#
#   # chain it so the publisher only starts if the camera opens:
#   # python3 check_camera.py && python3 image_publisher.py
#
# IMPORTANT - the USB camera is SINGLE-ACCESS (one program can hold it at a time):
#   * if image_publisher.py is running it OWNS /dev/video0, so check 4 ('working')
#     will report "busy" - that's expected, and check 5 ('published') should pass.
#   * if the publisher is NOT running, check 4 passes (opens + saves a frame) but
#     check 5 fails "no frames". So you normally won't see 4 and 5 green at once;
#     that's the camera being single-access, not a bug.

import os
import sys
import time
import tempfile
import subprocess

import numpy as np
import cv2


# /dev/video0 is the ORBBEC RGB camera's capture node on this jetson. video1 is a
# metadata node, not a real capture device. double-check with `v4l2-ctl --list-devices`.
CAMERA_DEV = "/dev/video0"
CAMERA_TOPIC = "/camera/image_raw"
SAVE_PATH = os.path.join(tempfile.gettempdir(), "camera_check.jpg")

# a frame whose average pixel value is below this is basically all-black -> lens
# cap on, camera not actually producing an image, etc. a real scene sits well above.
BLACK_MEAN = 2.0


class CameraError(Exception):
    '''Raised by assert_ok() when the camera is missing or not producing images.'''
    pass


# every check returns this same little dict so callers always get the same shape.
# "status" is the status code: "ok" or "fail". (identical to check_audio.status)
def status(name, ok, detail=""):
    return {"name": name, "status": "ok" if ok else "fail", "detail": detail}


class CameraCheck:
    '''
    One object, one method per check. Call them individually, or run_all() /
    assert_ok() to do the whole sweep.
    '''

    # ============ CHECK 1: usb descriptor scan ============
    # is the camera physically plugged in? lsusb dumps every usb device's
    # descriptor; we look for a "camera" line. catches "someone unplugged it"
    # before we bother with V4L2.
    def check_usb(self):
        try:
            out = subprocess.check_output(["lsusb"], text=True)
        except Exception as e:
            return status("usb", False, f"couldn't run lsusb: {e}")
        for line in out.splitlines():
            if "camera" in line.lower():
                return status("usb", True, line.strip())
        return status("usb", False, "no 'Camera' found in lsusb (camera unplugged?)")

    # ============ CHECK 2: list every video device ============
    # not pass/fail - the "show me what the OS can see" dump so I can eyeball which
    # /dev/videoN is the real capture node. always returns ok (informational).
    def list_devices(self):
        print("\n--- V4L2 video devices (v4l2-ctl --list-devices) ---")
        try:
            print(subprocess.check_output(["v4l2-ctl", "--list-devices"],
                                          text=True, stderr=subprocess.STDOUT).strip())
        except Exception as e:
            print(f"  (v4l2-ctl failed: {e})")

        print("\n--- /dev/video* nodes ---")
        nodes = sorted(p for p in os.listdir("/dev") if p.startswith("video"))
        print("  " + (", ".join("/dev/" + n for n in nodes) if nodes else "(none)"))

        return status("list", True, "printed above")

    # ============ CHECK 3: is /dev/video0 present? ============
    # the device node IS the OS handle for the camera. if it's missing, V4L2/OpenCV
    # literally can't see it, so there's no point trying to open it.
    def check_present(self):
        if not os.path.exists(CAMERA_DEV):
            return status("present", False, f"{CAMERA_DEV} missing (camera not enumerated)")
        return status("present", True, f"{CAMERA_DEV} exists")

    # ============ CHECK 4: open it, grab a frame, save it ============
    # the camera equivalent of check_audio.check_working: actually pull data off
    # the device and prove it's real. open with the V4L2 backend (same as
    # image_publisher.py - without CAP_V4L2 OpenCV may pick a backend that won't
    # read), grab a frame, SAVE it, and make sure it isn't an all-black image.
    def check_working(self):
        present = self.check_present()
        if present["status"] == "fail":
            return present

        cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        if not cap.isOpened():
            # most common cause: image_publisher.py already holds the camera
            return status("working", False,
                          f"could not open {CAMERA_DEV} (busy? image_publisher may be holding it)")
        try:
            ok, frame = False, None
            for _ in range(5):           # first frame or two off a USB cam can be empty
                ok, frame = cap.read()
                if ok and frame is not None:
                    break
        finally:
            cap.release()                # ALWAYS release so we don't keep the camera locked

        if not ok or frame is None:
            return status("working", False, "opened device but read no frame")

        cv2.imwrite(SAVE_PATH, frame)    # save the image, as the comment asked

        # mean pixel value = quick "is there actually a picture" test, the visual
        # analogue of the audio RMS check. all-black -> near 0.
        mean = float(frame.mean())
        h, w = frame.shape[:2]
        if mean < BLACK_MEAN:
            return status("working", False,
                          f"frame is all-black (mean={mean:.1f}), saved {SAVE_PATH}")
        return status("working", True,
                      f"grabbed {w}x{h} frame (mean={mean:.1f}), saved {SAVE_PATH}")

    # ============ CHECK 5: is it actually being PUBLISHED? ============
    # the only ROS check: subscribe to /camera/image_raw for a couple seconds and
    # confirm frames are arriving. needs ROS sourced + image_publisher running.
    # (mirrors sensor_health.py's camera test.) sensor-data QoS = best-effort, so
    # it can receive from the publisher whether it's reliable or best-effort.
    def check_published(self, window=3.0):
        try:
            import rclpy
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import Image
        except Exception as e:
            return status("published", False, f"ROS not available (did you source it?): {e}")

        started_here = not rclpy.ok()
        if started_here:
            rclpy.init()
        node = rclpy.create_node("camera_check_sub")
        msgs = []
        node.create_subscription(Image, CAMERA_TOPIC,
                                 lambda m: msgs.append(m), qos_profile_sensor_data)
        end = time.time() + window
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
        node.destroy_node()
        if started_here:
            rclpy.shutdown()

        if not msgs:
            return status("published", False,
                          f"no frames on {CAMERA_TOPIC} in {window:.0f}s (is image_publisher running?)")
        rate = len(msgs) / window
        last = msgs[-1]
        return status("published", True,
                      f"{rate:.1f} Hz on {CAMERA_TOPIC} ({last.width}x{last.height})")

    # ---- run every check and hand back the list of results ----
    def run_all(self):
        results = []
        results.append(self.check_usb())
        self.list_devices()              # informational, prints its own dump
        results.append(self.check_present())
        results.append(self.check_working())
        results.append(self.check_published())
        return results

    # ---- the "interface gate": raise instead of return ----
    # call this before starting anything that uses the camera. NOTE: only gates on
    # being able to OPEN the camera (usb/present/working), NOT on 'published' - the
    # publisher can't be running yet if we're about to start it, and it would also
    # hold the camera and make check_working fail busy.
    def assert_ok(self):
        for r in (self.check_usb(), self.check_present(), self.check_working()):
            if r["status"] == "fail":
                raise CameraError(f"{r['name']}: {r['detail']}")
        return True


def print_report(results):
    print("\n=== camera check ===")
    n_fail = 0
    for r in results:
        tag = "[ ok ]" if r["status"] == "ok" else "[FAIL]"
        if r["status"] == "fail":
            n_fail += 1
        print(f"  {tag} {r['name']:<10} {r['detail']}")
    print(f"\n{len(results)} checks, {n_fail} failed.")
    return n_fail


def main():
    check = CameraCheck()
    results = check.run_all()
    n_fail = print_report(results)
    # exit 0 if everything passed, 1 otherwise -> lets you chain this in a script
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
