#!/usr/bin/env python3
'''
check_audio.py - health check / interface gate for the audio recording stuff.

The rest of the system (audio_publisher.py, record_audio.py, transcribe_audio.py)
should call this BEFORE it starts grabbing audio, so we fail loudly with a clear
message instead of silently recording 10 seconds of nothing and wondering why
whisper keeps returning "" .

What it checks, in order:

1. usb scan    - is the ORBBEC actually plugged into a USB port? (lsusb scan of
                 the USB descriptors, looking for the orbbec device)
2. list        - print every capture device the OS can see, so I can eyeball
                 which card / source is the mic
3. present     - is ALSA card 0 (the ORBBEC) there at all?
4. working     - record ~1s and check it isn't digital silence (RMS / loudness test)

The spec asked for BOTH "raise an exception" and "return a status code", so there
are two ways to read the result:

  - every check_* method RETURNS a little status dict  -> use it as a status code
  - assert_ok() RAISES AudioError on the first failure -> use it as a hard gate
    in front of the pipeline

How to run:
    cd ~/sidharth_dev/audio_record
    python3 check_audio.py        # prints a report, exits 0 if all good, 1 if not

    # you can chain it so the publisher only starts if audio is healthy:
    # python3 check_audio.py && python3 audio_publisher.py

Note: unlike the other files in here this one does NOT need ROS sourced - it's
just talking to ALSA / pulseaudio, no rclpy.

Why arecord here instead of sounddevice (which record_audio.py uses)?
    The ORBBEC is a combined depth-camera + mic on ONE usb device. Capturing with
    in-process PortAudio (sounddevice) can wedge python so hard it ignores ctrl-c.
    arecord is a separate process we can kill with a timeout, so a dead mic can
    never hang this check. (same reasoning + same flags as sensor_health.py.)
'''

import os
import sys
import subprocess
import tempfile
import wave

import numpy as np


# the ORBBEC shows up as ALSA card 0 on this jetson. if you ever move it or plug
# in another sound card, double check with `arecord -l` and fix this path.
ORBBEC_CARD = "/proc/asound/card0"

# anything below this RMS is basically digital silence -> mic muted, wrong source
# selected, or the orbbec stopped streaming. a real mic in a quiet room still
# sits comfortably above this.
SILENCE_RMS = 5.0


class AudioError(Exception):
    '''Raised by assert_ok() when the mic is missing or not making any sound.'''
    pass


# every check returns this same little dict so callers always get the same shape.
# "status" is the status code the spec asked for: "ok" or "fail".
def status(name, ok, detail=""):
    return {"name": name, "status": "ok" if ok else "fail", "detail": detail}


class AudioCheck:
    '''
    One object, one method per check. Call them one at a time if you only care
    about a single thing, or call run_all() / assert_ok() to do the whole sweep.
    '''

    # ---- helper: find the ORBBEC's pulseaudio source name ----
    # the DEFAULT pulse source on this box flips to the silent built-in input
    # across reboots, so we never trust the default - we hunt down the orbbec
    # source by name and pin to it later. (lifted from sensor_health.py)
    def _orbbec_source(self):
        try:
            out = subprocess.check_output(["pactl", "list", "sources", "short"], text=True)
        except Exception:
            return None
        for line in out.splitlines():
            if "orbbec" in line.lower():
                return line.split()[1]   # column 1 is the source name
        return None

    # ============ CHECK 1: usb descriptor scan ============
    # is the ORBBEC physically plugged in? lsusb dumps the descriptor table of
    # every usb device; we just look for "orbbec" in there. this catches the
    # "someone unplugged the camera" case before we even bother with ALSA.
    def check_usb(self):
        try:
            out = subprocess.check_output(["lsusb"], text=True)
        except Exception as e:
            return status("usb", False, f"couldn't run lsusb: {e}")
        for line in out.splitlines():
            if "orbbec" in line.lower():
                return status("usb", True, line.strip())
        return status("usb", False, "no ORBBEC found in lsusb (mic unplugged?)")

    # ============ CHECK 2: list every capture device ============
    # not really pass/fail - this is the "show me what the OS can see" dump so I
    # can sanity-check which card is actually the mic. prints arecord's hardware
    # card list AND pulse's source list. always returns ok (it's informational).
    def list_devices(self):
        print("\n--- ALSA capture cards (arecord -l) ---")
        try:
            print(subprocess.check_output(["arecord", "-l"], text=True).strip())
        except Exception as e:
            print(f"  (arecord -l failed: {e})")

        print("\n--- pulseaudio sources (pactl list sources short) ---")
        try:
            print(subprocess.check_output(["pactl", "list", "sources", "short"], text=True).strip())
        except Exception as e:
            print(f"  (pactl failed: {e})")

        return status("list", True, "printed above")

    # ============ CHECK 3: is the mic present to ALSA? ============
    # sensor_health.py just checks /proc/asound/card0 exists - that file IS the OS
    # handle for the sound card. if it's missing, ALSA literally can't see the mic
    # no matter what, so there's no point trying to record.
    def check_present(self):
        if not os.path.exists(ORBBEC_CARD):
            return status("present", False, f"{ORBBEC_CARD} missing (ALSA can't see the mic)")
        return status("present", True, f"{ORBBEC_CARD} exists")

    # ============ CHECK 4: does the mic actually hear anything? ============
    # record ~1 second then measure RMS (the "average loudness"). a working mic in
    # a quiet room still picks up a bit of noise so RMS sits well above 0. if it
    # comes back near-zero the mic is muted / wrong source / not streaming.
    def check_working(self, seconds=1, rate=48000):
        # bail early if the card isn't even there - no card, nothing to record
        present = self.check_present()
        if present["status"] == "fail":
            return present

        path = os.path.join(tempfile.gettempdir(), "audio_check.wav")

        # pin the recording to the orbbec source, ignoring the (silent) default
        env = dict(os.environ)
        src = self._orbbec_source()
        if src:
            env["PULSE_SOURCE"] = src

        # arecord flags, since they're easy to forget:
        #   -D pulse   go THROUGH pulseaudio. going around it (plughw:0,0) fails
        #              "busy" because pulse already owns the card.
        #   -f S16_LE  16-bit signed little-endian samples (we read these as int16)
        #   -r / -c    sample rate / 1 channel (mono)
        #   -d         record this many seconds then quit on its own
        # timeout=seconds+5 is the safety net: if arecord hangs (mic not
        # streaming) the timeout kills it so this check can never hang forever.
        try:
            subprocess.run(
                ["arecord", "-D", "pulse", "-f", "S16_LE",
                 "-r", str(rate), "-c", "1", "-d", str(int(seconds)), path],
                timeout=seconds + 5, check=True, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return status("working", False, "recording timed out (mic not streaming) -> recommended action: fully power-cycle robot")
        except Exception as e:
            return status("working", False, f"arecord failed: {e}")

        # read the wav back and turn the raw bytes into a numpy array of samples
        with wave.open(path, "rb") as w:
            raw = w.readframes(w.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)

        if samples.size == 0:
            return status("working", False, "recorded 0 samples")

        # RMS = root-mean-square = sqrt(average of the squared samples).
        # squaring makes negatives count too, so it's a clean "how loud was it".
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if rms < SILENCE_RMS:
            return status("working", False, f"silent (RMS={rms:.0f}) - muted or wrong source ? -> recommended action: fully power-cycle robot   ")
        return status("working", True, f"hears something (RMS={rms:.0f})")

    # ---- run every check and hand back the list of results ----
    def run_all(self):
        results = []
        results.append(self.check_usb())
        self.list_devices()              # informational, prints its own dump
        results.append(self.check_present())
        results.append(self.check_working())
        return results

    # ---- the "interface gate": raise instead of return ----
    # this is what the rest of the system calls before starting the audio
    # pipeline. if anything's wrong it throws AudioError with a readable message,
    # so the caller crashes early and obviously instead of publishing silence.
    def assert_ok(self):
        for r in (self.check_usb(), self.check_present(), self.check_working()):
            if r["status"] == "fail":
                raise AudioError(f"{r['name']}: {r['detail']}")
        return True


def print_report(results):
    print("\n=== audio check ===")
    n_fail = 0
    for r in results:
        tag = "[ ok ]" if r["status"] == "ok" else "[FAIL]"
        if r["status"] == "fail":
            n_fail += 1
        print(f"  {tag} {r['name']:<8} {r['detail']}")
    print(f"\n{len(results)} checks, {n_fail} failed.")
    return n_fail


def main():
    check = AudioCheck()
    results = check.run_all()
    n_fail = print_report(results)
    # exit 0 if everything passed, 1 otherwise -> lets you chain this in a script
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
