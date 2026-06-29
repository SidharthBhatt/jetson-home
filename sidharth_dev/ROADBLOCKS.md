# Roadblocks & Fixes

The problems we hit while confirming the car and sensors, and how we solved each.
These are the reasons the test scripts are shaped the way they are — almost every
defensive choice in the code traces back to one of these.

---

## 1. `/dev/myserial` was wired to the **LiDAR**, not the control board

**Symptom.** The motor / bringup code talks to the control board over
`/dev/myserial`. The board would intermittently fail to respond, and a generic
"board didn't answer" error gave no hint why. The LiDAR and the control board both
enumerate as `ttyUSB*`, and their order is **not stable across reboots**, so
`ttyUSB0` was sometimes the LiDAR and sometimes the board.

**Root cause.** The Yahboom-provided udev rule pointed `/dev/myserial` at the wrong
chip. The original rule (now kept disabled as
`/etc/udev/rules.d/99-yahboom-myserial.rules.disabled`) reads:

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="myserial", MODE="0666"
```

`10c4:ea60` is the **LiDAR's CP2102**, not the control board. So `myserial`
symlinked to the LiDAR, and a loose USB cable on the board made it intermittent and
even harder to spot.

**Fix.** Disable that rule and bind `myserial` to the control board's own chip, the
**CH340 `1a86:7523`**, in `/etc/udev/rules.d/serial.rules`:

```
KERNEL=="ttyUSB*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE:="0777", SYMLINK+="myserial"
```

The LiDAR keeps its own stable symlink via `/etc/udev/rules.d/ydlidar.rules`
(`10c4:ea60` → `/dev/ydlidar`). Reload with:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

**Verification / prevention.** This single mis-bind cost a whole debugging session,
so we wrote [`navigation/check_control_board.py`](navigation/check_control_board.py)
specifically to catch it. Its `identity` check resolves `/dev/myserial` and reports
the exact failure — *"myserial → … is the LiDAR (10c4:ea60)! udev rule mis-pointed"*
— instead of a generic mismatch. It is number-independent: it doesn't care which
`ttyUSBx` the link points at, only which **chip** is behind it, and it cross-checks
the `/dev/serial/by-id` link as a second witness. It now passes:

```
[ ok ] control  identity  /dev/myserial -> /dev/ttyUSB1 is the control board (1a86:7523)
```

**Takeaway / design rule.** Never trust a bare `ttyUSB0/1` number. Always use the
stable udev symlinks (`/dev/ydlidar`, `/dev/myserial`) and verify the chip identity.

---

## 2. The microphone is the depth camera, and the default source is silent

**Symptom.** Recording produced 10 seconds of digital silence; whisper kept
returning empty strings. Nothing in the audio chain errored — it just heard nothing.

**Root cause (two parts).**
1. There is no separate "microphone" — audio input lives **on the ORBBEC depth
   sensor**, which shows up as ALSA `card 0`.
2. PulseAudio's **default source flips to the silent built-in input** across
   reboots, so capturing from the default device records nothing.

**Fix.** Never trust the default source. The checks query
`pactl list sources short`, find the source whose name contains `orbbec`, and pin
`PULSE_SOURCE` to it before recording. They also capture **through pulse**
(`arecord -D pulse`) rather than around it — going around it with `plughw:0,0` fails
`busy` because PulseAudio already owns the card.

**Verification.** [`audio_record/check_audio.py`](audio_record/check_audio.py)
records ~1 s and computes RMS; anything below 5 is flagged as silence with a clear
message. It now reports `working hears something (RMS=2887)`.

> This matches a known device fact for this robot: the ORBBEC mic is card 0, the
> default pulse source is silent, and `arecord plughw:0,0` is busy — go through
> pulse, pin the source.

---

## 3. In-process audio capture (PortAudio) could wedge Python

**Symptom.** When the mic wasn't streaming, an in-process `sounddevice`/PortAudio
capture could hang so hard that the Python process **ignored Ctrl-C / SIGTERM**,
freezing the whole test run.

**Root cause.** The ORBBEC is a combined depth-camera + mic on **one** USB device.
A stuck PortAudio read inside the interpreter has no killable boundary.

**Fix.** The health checks capture with an **external `arecord` subprocess** with a
hard `timeout` (`timeout = seconds + 5`). A dead mic now causes the subprocess to be
killed and the check to return `FAIL` ("capture timed out — ORBBEC not streaming"),
instead of hanging the suite. (`record_audio.py` / `audio_publisher.py` still use
`sounddevice` for the actual recording pipeline; only the *health checks* use
`arecord`, precisely so a check can never hang.)

---

## 4. The LiDAR returns zero bytes when you just open and read it

**Symptom.** Opening `/dev/ydlidar` and reading returned **zero bytes forever**,
making a healthy LiDAR look dead.

**Root cause.** The YDLidar does **not** stream on its own — it sits idle until it
is explicitly told to spin. It also runs at a non-default **512000 baud**; the wrong
baud yields garbage or zero bytes even on a healthy unit.

**Fix.** [`navigation/check_lidar.py`](navigation/check_lidar.py) opens at 512000,
sends the scan-START command (`0xA5 0x60`), reads for ~1 s, looks for the
`0xA5 0x5A` reply header, and **always** sends scan-STOP (`0xA5 0x65`) in a
`finally` so the motor never keeps spinning. It now reports
`streaming 5257 bytes in 1s (looks like YDLidar packets)`.

---

## 5. Serial ports refused to open — `dialout` permissions

**Symptom.** A port that clearly existed couldn't be opened; probing the board
raised a permission error.

**Root cause.** The Yahboom serial ports belong to group `dialout`. A user not in
that group can *see* the device file but can't open it.

**Fix.** Add the user to `dialout` (the `jetson` user already is):

```bash
sudo usermod -aG dialout $USER   # then log out / back in
```

**Prevention.** The motor and control-board checks now test for read/write access
(`os.access`) and, on failure, return the actionable message *"add user to 'dialout'
group"* rather than crashing with a raw `PermissionError`.

---

## 6. Single-access ports look like failures when a driver is running

**Symptom.** Running a `check_working` while the matching ROS driver was up reported
the device as `busy` / couldn't open — looking like a hardware failure.

**Root cause.** The camera, LiDAR and control-board ports are **single-access**:
exactly one program can hold each at a time. A running driver legitimately owns the
port.

**Fix / convention.** This isn't a bug, it's physics, so we documented it and split
responsibilities:

* Run the **direct hardware checks** (`check_*`) with the drivers **down**.
* Run [`test_sensors/sensor_health.py`](test_sensors/sensor_health.py) with the
  drivers **up** — it checks the **ROS topics** (`/scan`, `/odom`,
  `/camera/image_raw`) instead of grabbing the port, so it confirms liveness while a
  driver owns the device.

---

## 7. Camera defaulted to a huge resolution → ~2 Hz

**Symptom.** The camera publisher delivered only ~2 frames/sec.

**Root cause.** The camera defaults to `2048x1536`; each raw `bgr8` frame is ~9 MB,
which throttles the pipeline. OpenCV also sometimes auto-picked a backend that
couldn't read the UVC camera at all.

**Fix.** [`camera/image_publisher.py`](camera/image_publisher.py) forces the V4L2
backend (`cv2.CAP_V4L2`), sets **MJPG** at **640x480 @ 30 fps**, and gets a true
30 Hz. The camera health check uses the same V4L2 backend so its results match what
the publisher will see.

---

## 8. Whisper "hallucinations" on silent/near-silent audio

**Symptom.** Transcribing quiet clips produced confident but fake text — phrases
like *"Thanks for watching!"* that were never spoken.

**Root cause.** Whisper hallucinates on silence/low-information audio.

**Fix.** [`audio_record/audio_publisher.py`](audio_record/audio_publisher.py) gates
the output: skip clips below an RMS threshold, drop results with high
`no_speech_prob`, low `avg_logprob`, an over-high compression ratio, or that match a
known-hallucination phrase list before publishing to `/audio/transcribed`.

---

## Open / unresolved items

* **CH340 vendor-driver warning.** The vendor `ch34x` driver logs a benign warning
  for this chip. The in-kernel `ch341` driver handles it without the warning;
  swapping drivers would silence it. Optional cleanup — does **not** affect
  operation, so left as-is for now.
* **LiDAR firmware version not probed.** The YDLidar SDK Python binding isn't
  installed, so [`test_sensors/test.py`](test_sensors/test.py) reports *"ydlidar SDK
  not installed — firmware not probed"* rather than faking a version. The functional
  LiDAR check still confirms the device streams real data, so this is cosmetic.
