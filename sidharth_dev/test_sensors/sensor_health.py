#!/usr/bin/env python3
"""
sensor_health.py - functional health check for the four subsystems.

For each device we check two layers and give ONE verdict:
  L0  present  - is the OS handle there at all?
  L2  data     - is real data flowing, at a healthy rate, with sane values?

Liveness == data at the expected rate, NOT "a process exists". So the ROS
tests assume the matching driver is already running (your camera publisher,
the lidar driver, the base/odom node). "no data" therefore means that driver
isn't up.

Passive by default. Pass --active to also run the tests that move hardware:
    mic    : asks you to speak, expects a non-empty transcript
    motors : nudges the robot forward briefly, checks /odom moved, then STOPS

Run:
    source /opt/ros/humble/setup.bash
    cd sidharth_dev/test_sensors/
    python3 sensor_health.py            # passive (safe)
    python3 sensor_health.py --active   # + speak + MOVES THE ROBOT
"""

import argparse
import math
import os
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image, LaserScan
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist


# --------------------------------------------------------------------------
# uniform result contract - every test returns this same shape
# --------------------------------------------------------------------------
PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


def result(name, status, detail="", metric=None):
    return {"name": name, "status": status, "detail": detail, "metric": metric}


class SensorTester(Node):
    def __init__(self):
        super().__init__("sensor_health")

    # ---- generic observer: gather messages on a topic for `duration` sec ----
    def collect(self, topic, msg_type, duration, qos=qos_profile_sensor_data):
        msgs = []
        sub = self.create_subscription(msg_type, topic, lambda m: msgs.append(m), qos)
        end = time.time() + duration
        try:
            while time.time() < end and rclpy.ok():
                rclpy.spin_once(self, timeout_sec=0.05)
        finally:
            self.destroy_subscription(sub)
        rate = len(msgs) / duration if duration > 0 else 0.0
        return msgs, rate

    # ================= CAMERA =================
    # L0 /dev/video0 opens | L2 /camera/image_raw >= ~25 Hz and not all-black
    def test_camera(self, topic="/camera/image_raw", window=3.0):
        if not os.path.exists("/dev/video0"):
            return result("camera", FAIL, "/dev/video0 not present")
        msgs, rate = self.collect(topic, Image, window)
        if not msgs:
            return result("camera", FAIL, f"no data on {topic} (is image_publisher running?)")
        last = msgs[-1]
        mean = float(np.frombuffer(bytes(last.data), dtype=np.uint8).mean())
        detail = f"{rate:.1f} Hz, {last.width}x{last.height}, mean-px {mean:.1f}"
        if mean < 2.0:
            return result("camera", FAIL, detail + " (frame all-black)", rate)
        if rate < 25:
            return result("camera", WARN, detail + " (rate < 25 Hz)", rate)
        return result("camera", PASS, detail, rate)

    # ================= LIDAR =================
    # L0 /dev/ttyUSB0 present | L2 /scan >= ~5 Hz and some finite ranges
    def test_lidar(self, topic="/scan", window=3.0):
        if not os.path.exists("/dev/ttyUSB0"):
            return result("lidar", FAIL, "/dev/ttyUSB0 not present")
        msgs, rate = self.collect(topic, LaserScan, window)
        if not msgs:
            return result("lidar", FAIL, f"no data on {topic} (is the lidar driver running?)")
        last = msgs[-1]
        finite = [r for r in last.ranges
                  if math.isfinite(r) and last.range_min <= r <= last.range_max]
        detail = f"{rate:.1f} Hz, {len(last.ranges)} beams, {len(finite)} valid"
        if not finite:
            return result("lidar", FAIL, detail + " (no finite ranges)", rate)
        if rate < 5:
            return result("lidar", WARN, detail + " (rate < 5 Hz)", rate)
        return result("lidar", PASS, detail, rate)

    # ================= MIC (passive) =================
    # L0 card 0 present | L2 capture ~1s via arecord, RMS above a noise floor.
    #
    # We capture with an EXTERNAL arecord process, not in-process PortAudio:
    # PortAudio on the combined depth+audio ORBBEC can wedge the interpreter so
    # hard it ignores SIGTERM, which would hang the whole suite. arecord is
    # killable, so subprocess timeout always returns control.
    #
    # We go THROUGH pulse ("-D pulse"), not around it ("plughw:0,0" fails with
    # "busy" because PulseAudio owns the card), and pin PULSE_SOURCE to the
    # ORBBEC so capture doesn't depend on the default source (which flips to the
    # silent built-in input across reboots).
    def _orbbec_source(self):
        try:
            out = subprocess.check_output(["pactl", "list", "sources", "short"],
                                          text=True)
        except Exception:
            return None
        for line in out.splitlines():
            if "orbbec" in line.lower():
                return line.split()[1]
        return None

    def _arecord(self, path, seconds, rate=48000):
        env = dict(os.environ)
        src = self._orbbec_source()
        if src:
            env["PULSE_SOURCE"] = src
        subprocess.run(
            ["arecord", "-D", "pulse", "-f", "S16_LE",
             "-r", str(rate), "-c", "1", "-d", str(int(seconds)), path],
            timeout=seconds + 5, check=True, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def test_mic(self, seconds=1, rate=48000):
        if not os.path.exists("/proc/asound/card0"):
            return result("mic", FAIL, "card 0 not present")
        path = os.path.join(tempfile.gettempdir(), "mic_health.wav")
        try:
            self._arecord(path, seconds, rate)
        except subprocess.TimeoutExpired:
            return result("mic", FAIL,
                          "capture timed out (ORBBEC not streaming - suspended/contended)")
        except Exception as e:
            return result("mic", FAIL, f"arecord failed: {e}")
        with wave.open(path, "rb") as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("f8")
        if x.size == 0:
            return result("mic", FAIL, "captured 0 samples")
        rms = float(np.sqrt(np.mean(x * x)))
        detail = f"{seconds}s @ {rate}Hz, RMS={rms:.0f}"
        if rms < 5:                       # essentially digital silence
            return result("mic", FAIL, detail + " (silent - muted or wrong source?)", rms)
        return result("mic", PASS, detail + " (hears something)", rms)

    # ================= MOTORS (passive) =================
    # L0 serial port present | L2 /odom publishing
    def test_motors(self, topic="/odom", window=3.0):
        if not (os.path.exists("/dev/ttyUSB0") or os.path.exists("/dev/ttyTHS1")):
            return result("motors", FAIL, "no serial port (ttyUSB0/ttyTHS1)")
        msgs, rate = self.collect(topic, Odometry, window, qos=10)  # odom is reliable
        if not msgs:
            return result("motors", FAIL, f"no data on {topic} (is the base/bringup node running?)")
        detail = f"/odom publishing at {rate:.1f} Hz"
        if rate < 1:
            return result("motors", WARN, detail + " (very low rate)", rate)
        return result("motors", PASS, detail, rate)

    # ================= MIC (active) =================
    # capture a few seconds via arecord, then let whisper transcribe the wav
    # (whisper.transcribe(path) uses ffmpeg to decode + resample to 16 kHz).
    def test_mic_active(self, seconds=4):
        path = os.path.join(tempfile.gettempdir(), "mic_active.wav")
        print(f"\n>> SPEAK NOW for ~{seconds} seconds...")
        try:
            self._arecord(path, seconds)
        except subprocess.TimeoutExpired:
            return result("mic(active)", FAIL, "capture timed out (ORBBEC not streaming)")
        except Exception as e:
            return result("mic(active)", FAIL, f"arecord failed: {e}")
        try:
            import whisper
        except ImportError as e:
            return result("mic(active)", SKIP, f"whisper not available: {e}")
        model = whisper.load_model("base")
        text = model.transcribe(path, fp16=False).get("text", "").strip()
        if text:
            return result("mic(active)", PASS, f'heard: "{text}"')
        return result("mic(active)", FAIL, "no speech transcribed")

    # ================= MOTORS (active) =================
    # nudge cmd_vel, confirm /odom moved, then STOP (guaranteed)
    def test_motors_active(self, push=0.12, drive_s=1.0):
        before, _ = self.collect("/odom", Odometry, 1.0, qos=10)
        if not before:
            return result("motors(active)", SKIP, "no /odom; skipping nudge")
        p0 = before[-1].pose.pose.position

        pub = self.create_publisher(Twist, "/cmd_vel", 10)
        fwd = Twist()
        fwd.linear.x = push
        try:
            t_end = time.time() + drive_s
            while time.time() < t_end and rclpy.ok():
                pub.publish(fwd)
                rclpy.spin_once(self, timeout_sec=0.05)
        finally:
            # ALWAYS stop, even if something above threw
            for _ in range(10):
                pub.publish(Twist())
                rclpy.spin_once(self, timeout_sec=0.02)

        after, _ = self.collect("/odom", Odometry, 1.0, qos=10)
        self.destroy_publisher(pub)
        p1 = after[-1].pose.pose.position
        moved = math.hypot(p1.x - p0.x, p1.y - p0.y)
        detail = f"moved {moved * 100:.1f} cm on /odom"
        if moved > 0.02:
            return result("motors(active)", PASS, detail)
        return result("motors(active)", FAIL, detail + " (no movement - wheels/driver?)")


# --------------------------------------------------------------------------
def print_results(results):
    width = max(len(r["name"]) for r in results)
    icon = {PASS: "[PASS]", FAIL: "[FAIL]", WARN: "[WARN]", SKIP: "[SKIP]"}
    print()
    for r in results:
        print(f"  {icon.get(r['status'], '[????]')} {r['name'].ljust(width)}  {r['detail']}")
    n_fail = sum(1 for r in results if r["status"] == FAIL)
    print(f"\n{len(results)} checks, {n_fail} failed.")
    return n_fail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--active", action="store_true",
                    help="also run hardware-moving tests (speak + MOVE robot)")
    args = ap.parse_args()

    rclpy.init()
    node = SensorTester()
    results = []
    try:
        results.append(node.test_camera())
        results.append(node.test_lidar())
        results.append(node.test_mic())
        results.append(node.test_motors())

        if args.active:
            results.append(node.test_mic_active())
            print("\n** ACTIVE MOTOR TEST: the robot will drive forward briefly. **")
            print("   Make sure it's on blocks or has clear space.")
            if input("   Type 'yes' to proceed, anything else to skip: ").strip().lower() == "yes":
                results.append(node.test_motors_active())
            else:
                results.append(result("motors(active)", SKIP, "user skipped"))
    finally:
        node.destroy_node()
        rclpy.shutdown()

    n_fail = print_results(results)
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
