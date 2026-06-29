# Deliverable 1: Confirm the car and sensors work


This deliverable contains one small, independent test script per device on the robot, plus a single combined checker that runs them all and prints one PASS/FAIL table.

| Assignment item | File Location |
|---|---|
| Identify the camera, LiDAR, microphone, motor-control, and ROS interfaces | [`test_sensors/test.py`](test_sensors/test.py) |
| One working test script per available sensor / interface | [`camera/check_camera.py`](camera/check_camera.py), [`audio_record/check_audio.py`](audio_record/check_audio.py), [`navigation/check_lidar.py`](navigation/check_lidar.py), [`navigation/check_motors.py`](navigation/check_motors.py), [`navigation/check_control_board.py`](navigation/check_control_board.py) |
| ROS-interface (data-flow) tests | [`test_sensors/sensor_health.py`](test_sensors/sensor_health.py) |
| One combined preflight + overall table | [`test_sensors/check_all_sensors.py`](test_sensors/check_all_sensors.py) |






## 1. Map of what is plugged in and what it does:

| Device (USB id) | What it really is | OS handle |
|---|---|---|
| ORBBEC Depth Sensor (`2bc5:060f`) | **The microphone** (audio in lives on the depth camera) | ALSA `card 0`, pulse source `*orbbec*` |
| Orbbec USB 2.0 Camera (`2bc5:050f`) | **RGB camera** | `/dev/video0` |
| Silicon Labs CP2102 (`10c4:ea60`) | **LiDAR** USB-UART bridge (YDLidar) | `/dev/ydlidar` → `ttyUSB0` |
| QinHeng CH340 (`1a86:7523`) | **Motor control board** (Rosmaster, motors + IMU + battery) | `/dev/myserial` → `ttyUSB1` |
| DragonRise Controller (`0079:181c`) | USB gamepad (teleop) | `/dev/input/js*` |


---

## 2. Directory structure

```
sidharth_dev/
├── m1_README.md               ← this file (status + how to run)
│
├── audio_record/              ← microphone (ORBBEC) — capture / transcribe
│   ├── check_audio.py         ★ MIC test       (the deliverable health check)
│   ├── audio_publisher.py       records 10 s, whisper-transcribes, publishes /audio/transcribed
│   ├── record_audio.py          records 10 s → mp3
│   └── transcribe_audio.py      whisper-transcribes any mp3 in the folder
│
├── camera/                    ← RGB camera (/dev/video0)
│   ├── check_camera.py        ★ CAMERA test    (the deliverable health check)
│   ├── image_publisher.py       publishes /camera/image_raw @ 30 fps
│   └── image_subscriber.py      displays /camera/image_raw
│
├── navigation/                ← LiDAR + motor control board
│   ├── check_lidar.py         ★ LIDAR test     (the deliverable health check)
│   ├── check_control_board.py ★ CONTROL-BOARD wiring/identity check
│   └── check_motors.py        ★ MOTORS test    (the deliverable health check)
│
└── test_sensors/              ← combined + cross-cutting tools
   ├── check_all_sensors.py   ★ runs EVERY check above, prints ONE table
   ├── sensor_health.py         ROS data-flow checks (passive, + --active)
   └── test.py                  device & firmware/version inventory
```

★ = a "one test script per sensor/interface" deliverable.

The per-device checkers live next to the code they protect (the camera checker
sits beside the camera publisher, etc.). The combined checker in `test_sensors/`
reaches into each folder and reuses those same classes so nothing is duplicated.

---

## 3. The five per-device checks

| Layer | Method | Question it answers |
|---|---|---|
| **1. USB** | `check_usb()` | Is the device physically on the USB bus? (`lsusb` scan) |
| **2. Present** | `check_present()` | Is the OS handle there — `/dev/...`, `card0`, the symlink? |
| **3. Working** | `check_working()` | Does **real data** come off it? (records 1 s / grabs a frame / spins the LiDAR / reads the board) |

Plus a `list_devices()` helper (informational dump) and two ways to read the result:

* every `check_*` method **returns** a status dict `{"name", "status", "detail"}`
 → use it as a status code, and
* `assert_ok()` **raises** a typed exception (`AudioError`, `CameraError`, …) on the
 first failure → use it as a hard gate in front of a pipeline, e.g.
 `python3 check_camera.py && python3 image_publisher.py`.

Each checker exits `0` if everything passed and `1` otherwise, so it is chainable
in shell scripts.

> ⚠️ **Single-access ports.** The camera, the LiDAR and the control board can each
> be held by only **one** program at a time. Run these checks with the ROS drivers
> **down**. If a driver is already running it owns the port and `check_working`
> will correctly report `busy`, that is expected and not a bug.

### 3.1 Microphone — `audio_record/check_audio.py`

The mic is the ORBBEC depth sensor on ALSA `card 0`. In the future it will be replaced with a standalone microphone, but for right now it works. It picks up on a lot of noise even in silence, which is a good substitute for the background noise of the Polaris Ranger or Tractor.

* **usb** — looks for `orbbec` in `lsusb`.
* **present** — `/proc/asound/card0` exists (the OS handle for the sound card).
* **working** — records ~1 s with `arecord` and measures **RMS** (loudness). Below
 an RMS of 5 it is treated as digital silence (muted / wrong source / not streaming).

```bash
cd ~/sidharth_dev/audio_record
python3 check_audio.py
```

Example output (the `arecord -l` dump also lists ~20 Jetson APE virtual cards, cut here):

```
--- ALSA capture cards (arecord -l) ---
**** List of CAPTURE Hardware Devices ****
card 0: Sensor [ORBBEC Depth Sensor], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
... (card 2 = NVIDIA Jetson Orin NX APE, 20 virtual XBAR cards, omitted) ...

--- pulseaudio sources (pactl list sources short) ---
0  alsa_input.usb-Orbbec_R__ORBBEC_Depth_Sensor-01.analog-stereo  module-alsa-card.c  s16le 2ch 48000Hz  SUSPENDED
1  alsa_output.platform-sound.analog-stereo.monitor  module-alsa-card.c  s16le 2ch 44100Hz  SUSPENDED
2  alsa_input.platform-sound.analog-stereo  module-alsa-card.c  s16le 2ch 44100Hz  SUSPENDED

=== audio check ===
  [ ok ] usb      Bus 001 Device 010: ID 2bc5:050f Orbbec 3D Technology International, Inc USB 2.0 Camera
  [ ok ] present  /proc/asound/card0 exists
  [ ok ] working  hears something (RMS=3555)

3 checks, 0 failed.
```

The `usb` row prints the Camera line, not the depth sensor, because both Orbbec
devices have "Orbbec" in their `lsusb` name and the camera comes up first. The mic
itself is `card 0` in the ALSA list above. The `working` RMS bounces around with
room noise (roughly 3000–4000 in the lab), which is what I want, it should never sit
near zero. If it ever does, that is the silent-default-source problem in
[Roadblocks](#roadblocks).

### 3.2 Camera — `camera/check_camera.py`

* **usb** — looks for a `Camera` line in `lsusb`.
* **list** — `v4l2-ctl --list-devices` + the `/dev/video*` nodes (so you can see
 that `/dev/video0` is the real capture node and `/dev/video1` is metadata).
* **present** — `/dev/video0` exists.
* **working** — opens `/dev/video0` with the **V4L2 backend**, grabs a frame,
 **saves** it to `/tmp/camera_check.jpg`, and checks the mean pixel value so an
 all-black frame (lens cap, no image) fails instead of silently passing.

```bash
cd ~/sidharth_dev/camera
source /opt/ros/humble/setup.bash    # this file imports rclpy at the top
python3 check_camera.py
```

Example output:

```
--- V4L2 video devices (v4l2-ctl --list-devices) ---
NVIDIA Tegra Video Input Device (platform:tegra-camrtc-ca):
 /dev/media0


USB 2.0 Camera: USB Camera (usb-3610000.usb-2.4.1.2):
 /dev/video0
 /dev/video1
 /dev/media1


--- /dev/video* nodes ---
 /dev/video0, /dev/video1


=== camera check ===
 [ ok ] usb        Bus 001 Device 010: ID 2bc5:050f Orbbec 3D Technology International, Inc USB 2.0 Camera
 [ ok ] present    /dev/video0 exists
 [ ok ] working    grabbed 640x480 frame (mean=126.2), saved /tmp/camera_check.jpg


3 checks, 0 failed.
```

### 3.3 LiDAR — `navigation/check_lidar.py`

* **usb** — matches the **CP210x / Silicon Labs** line specifically (not just
 "serial", because the CH340 control board is also a serial device).
* **list** — `/dev/ttyUSB*`, the `/dev/serial/by-id` symlinks, and the
 `ydlidar`/`myserial` symlinks so the aliasing is visible.
* **present** — `/dev/ydlidar` exists (the stable udev symlink, not a bare ttyUSB).
* **working** — opens the port at **512000 baud**, sends the YDLidar **scan-START**
 command (`0xA5 0x60`) because the LiDAR does **not** stream on its own, reads ~1 s,
 confirms bytes are flowing (and the `0xA5 0x5A` reply header), then **always**
 sends scan-STOP so the motor doesn't keep spinning. Needs **no ROS**.

```bash
cd ~/sidharth_dev/navigation
python3 check_lidar.py
```

Example output:

```
--- /dev/ttyUSB* nodes ---
  /dev/ttyUSB0, /dev/ttyUSB1

--- /dev/serial/by-id (stable names -> ttyUSB) ---
total 0
lrwxrwxrwx 1 root root 13 Jan  1  1970 usb-1a86_USB_Serial-if00-port0 -> ../../ttyUSB0
lrwxrwxrwx 1 root root 13 Jan  1  1970 usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0 -> ../../ttyUSB1

--- lidar/control-board symlinks ---
  /dev/ydlidar -> ttyUSB1
  /dev/myserial -> ttyUSB0

=== lidar check ===
  [ ok ] usb        Bus 001 Device 011: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
  [ ok ] present    /dev/ydlidar -> /dev/ttyUSB1
  [ ok ] working    streaming 5241 bytes in 1s (looks like YDLidar packets)

3 checks, 0 failed.
```

### 3.4 Motor control board — `navigation/check_motors.py`

* **usb** — looks for a CP210x/CH340/UART bridge (not fatal if absent — the board
 could be on the Tegra UART `/dev/ttyTHS1`).
* **list** — every serial port + the Yahboom udev symlinks.
* **present** — a usable board port exists **and** is read/write (you must be in the
 `dialout` group).
* **working** — opens the board with `Rosmaster_Lib`, reads the **firmware version**
 and **battery voltage**; a version > 0 plus a sane battery (6–13 V) means a real
 board answered. Ports are deduped by `realpath` so `myserial`→`ttyUSB1` isn't
 probed twice.

```bash
cd ~/sidharth_dev/navigation
source /opt/ros/humble/setup.bash
python3 check_motors.py
```

Example output:

```
--- serial ports ---
  /dev/ttyTHS1, /dev/ttyTHS2, /dev/ttyUSB0, /dev/ttyUSB1

--- Yahboom udev symlinks ---
  /dev/myserial -> /dev/ttyUSB0
  /dev/rplidar -> /dev/ttyUSB1
  /dev/ydlidar -> /dev/ttyUSB1
Rosmaster Serial Opened! Baudrate=115200
----------------create receive threading--------------

=== motor check ===
  [ ok ] usb        Bus 001 Device 011: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
  [ ok ] present    usable serial port(s): ['/dev/myserial', '/dev/ttyTHS1']
  [ ok ] working    board v3.6 @ /dev/myserial, battery 12.2V

3 checks, 0 failed.
```

### 3.5 Control-board wiring/identity — `navigation/check_control_board.py`

`check_motors.py` proves that *some* board answers on a serial port. It does not
prove that `/dev/myserial` points at the control board and not at the LiDAR, and
that gap is exactly the bug that bit me. The LiDAR (CP2102) and the control board
(CH340) both come up as `ttyUSB*`, and out of the box the Yahboom udev rule had
`/dev/myserial` bound to the LiDAR's chip. **I had to go into the udev rules and
manually change the binding so `/dev/myserial` points at the control board's CH340
instead of the LiDAR.** The full story is in [Roadblocks](#roadblocks).

This check is the guard that makes sure that never silently comes back. It only
looks at the plumbing (pure `os` + `udevadm`, no ROS, never opens the port), so it
is safe to run even while a driver owns the port.

* **usb** — is the control board's own chip `1a86:7523` on the bus? (stricter than
 the motor check, which matches any serial bridge).
* **present** — does `/dev/myserial` exist and is it read/write? (tells a missing
 link apart from a *dangling* one).
* **identity (working)** — does `/dev/myserial` actually resolve to `1a86:7523`?
 If it resolves to the LiDAR's `10c4:ea60` it says so straight out: *"myserial is
 bound to the LiDAR, rebind it."* It does not care which `ttyUSBx` the link lands
 on, only which chip is behind it.

```bash
cd ~/sidharth_dev/navigation
python3 check_control_board.py
```

Example output:

```
=== control board check ===
  [ ok ] usb        Bus 001 Device 007: ID 1a86:7523 QinHeng Electronics CH340 serial converter
  [ ok ] present    /dev/myserial -> /dev/ttyUSB0
  [ ok ] identity   /dev/myserial -> /dev/ttyUSB0 is the control board (1a86:7523)

3 checks, 0 failed.
```

---

## 4. Cross cutting  tools

### `test_sensors/sensor_health.py` — ROS data-flow checks

Where the per-device checks talk to hardware directly, this one checks the **ROS
interface**: it subscribes to the live topics and asks "is real data flowing at a
healthy rate?". **Liveness == data at the expected rate, not "a process exists",**
so it assumes the corresponding publishers are already running.

* `camera` → `/camera/image_raw` ≥ ~25 Hz and not all-black
* `lidar` → `/scan` ≥ ~5 Hz with finite ranges
* `mic` → 1 s `arecord`, RMS above the noise floor
* `motors` → `/odom` publishing

Passive (safe) by default; `--active` additionally asks you to speak (whisper
transcribes it) and **briefly drives the robot forward** to confirm `/odom` moves, then
always stops.

```bash
source /opt/ros/humble/setup.bash
cd ~/sidharth_dev/test_sensors
python3 sensor_health.py            # passive, safe
python3 sensor_health.py --active   # also speaks + MOVES the robot (asks first)
```

## The combined checker — `check_all_sensors.py`

`test_sensors/check_all_sensors.py` is the **single preflight** that ties the five
per-device checkers together. It is the script to run when you just want to know
"is the robot healthy right now?". It does three things, in order:

1. **Prints the friendly device map** — the "ORBBEC = microphone, CP2102 = LiDAR"
  identity table, with a `[+]`/`[-]` showing which expected devices are actually
  present on the USB bus.
2. **Imports and runs every checker.** It adds `camera/`, `audio_record/` and
  `navigation/` to the path, imports `AudioCheck` / `CameraCheck` / `LidarCheck` /
  `ControlBoardCheck` / `MotorCheck`, and calls the shared `check_usb` /
  `check_present` / `check_working` on each. The control-board check runs *before*
  the motor check, so a mis-wired `/dev/myserial` is diagnosed before the generic
  "board didn't answer" message appears.
3. **Prints one combined PASS/FAIL table** and exits non-zero if anything failed —
  so you can chain it before a bringup launch.

**It is fault-tolerant by design.** Imports are wrapped: if one checker can't even
import (e.g. ROS isn't sourced, so `check_camera`'s top-level `import rclpy` fails),
that subsystem is reported as a single failed row instead of crashing the whole
preflight. Each row reuses the exact same `{name, status, detail}` shape every
checker already returns, which is what makes one uniform table possible.

### How to run it

```bash
source /opt/ros/humble/setup.bash      # camera + motor checkers import rclpy
cd ~/sidharth_dev/test_sensors
python3 check_all_sensors.py
```

Run it with the **publishers turned off.** Each `check_working` exercises its
device (records 1 s, grabs a frame, spins the LiDAR, reads the board), and those
ports are single-access, so a running driver would make `check_working` say `busy`.

### How it produces the overall table

Each per-device checker contributes its three core rows (`usb`, `present`,
`working`; `control` contributes `usb`, `present`, `identity`). The printer measures
the longest subsystem name and the longest check name, left-aligns every column,
tags each row `[ ok ]` or `[FAIL]`, and finishes with a one-line tally
(`N checks, M failed.`). The process exit code is `0` only when `M == 0`.

### Example output (all 15 green)

```
=== devices on this robot ===
  [+] ORBBEC Depth Sensor    = microphone (audio in)
  [+] Orbbec USB 2.0 Camera  = RGB camera -> /dev/video0
  [+] Silicon Labs CP2102    = LiDAR -> /dev/ydlidar
  [+] QinHeng CH340          = motor control board -> /dev/myserial
  [+] DragonRise Controller  = USB gamepad (teleop)
  [+] Jetson Orin NX         = compute host
Rosmaster Serial Opened! Baudrate=115200
----------------create receive threading--------------

=== sensor preflight ===
  [ ok ] audio    usb       Bus 001 Device 010: ID 2bc5:050f Orbbec 3D Technology International, Inc USB 2.0 Camera
  [ ok ] audio    present   /proc/asound/card0 exists
  [ ok ] audio    working   hears something (RMS=3834)
  [ ok ] camera   usb       Bus 001 Device 010: ID 2bc5:050f Orbbec 3D Technology International, Inc USB 2.0 Camera
  [ ok ] camera   present   /dev/video0 exists
  [ ok ] camera   working   grabbed 640x480 frame (mean=196.2), saved /tmp/camera_check.jpg
  [ ok ] lidar    usb       Bus 001 Device 011: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
  [ ok ] lidar    present   /dev/ydlidar -> /dev/ttyUSB1
  [ ok ] lidar    working   streaming 457 bytes in 1s (looks like YDLidar packets)
  [ ok ] control  usb       Bus 001 Device 007: ID 1a86:7523 QinHeng Electronics CH340 serial converter
  [ ok ] control  present   /dev/myserial -> /dev/ttyUSB0
  [ ok ] control  identity  /dev/myserial -> /dev/ttyUSB0 is the control board (1a86:7523)
  [ ok ] motors   usb       Bus 001 Device 011: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
  [ ok ] motors   present   usable serial port(s): ['/dev/myserial', '/dev/ttyTHS1']
  [ ok ] motors   working   board v3.6 @ /dev/myserial, battery 12.2V

15 checks, 0 failed.
```

Reading the table: the `audio` and `camera` `usb` rows both print the Camera line
because both Orbbec devices share the "Orbbec" string and the camera shows up first
in `lsusb`; `lidar working` is real bytes streamed off the spinning LiDAR; `control
identity` confirms `/dev/myserial` resolves to the CH340 (`1a86:7523`) and **not**
the LiDAR; and `motors working` reads live firmware `v3.6` and battery `12.2 V`
straight off the board. Notice the LiDAR is on `ttyUSB1` and the board on `ttyUSB0`
here, on an earlier boot they were swapped. That is the whole reason the checks key
off the udev symlinks and the chip IDs and never the bare `ttyUSB` number.

---

## Roadblocks

The three problems that actually cost me time, and what fixed them.

### 1. `/dev/myserial` was bound to the LiDAR, not the control board

The bringup talks to the control board over `/dev/myserial`, and the board kept
dropping out with a useless "board didn't answer" error. The cause: the LiDAR
(CP2102, `10c4:ea60`) and the control board (CH340, `1a86:7523`) both enumerate as
`ttyUSB*`, and the order is not stable across reboots, so `ttyUSB0` is sometimes one
and sometimes the other. On top of that the udev rule that ships with the robot
pointed `/dev/myserial` straight at the LiDAR's chip:

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="myserial", MODE="0666"
```

So `myserial` was the LiDAR, and a loose USB cable on the board made it flaky on top
of that.

The fix was manual. I went into `/etc/udev/rules.d`, disabled that rule (renamed it
to `99-yahboom-myserial.rules.disabled`), and wrote my own `serial.rules` that binds
`myserial` to the control board's CH340 by its own vendor:product id:

```
KERNEL=="ttyUSB*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE:="0777", SYMLINK+="myserial"
```

The LiDAR keeps its own `/dev/ydlidar` symlink from `ydlidar.rules`. Reload without
a reboot:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

After that `myserial` follows the board's chip no matter which `ttyUSB` number it
lands on, which you can see in the table above where the numbers flipped between
boots. `check_control_board.py` exists so this can never silently come back.

### 2. The mic is the depth camera, and the default audio source is silent

There is no separate microphone, audio input lives on the ORBBEC depth sensor, which
shows up as ALSA `card 0`. Worse, PulseAudio's default source flips to the silent
built-in input across reboots, so recording from the default device gives you 10
seconds of nothing and whisper just returns "".

The fix is to never trust the default. The audio code runs `pactl list sources
short`, finds the source with `orbbec` in the name, and pins `PULSE_SOURCE` to it
before recording. It also records through pulse (`arecord -D pulse`) instead of
around it, because going straight at `plughw:0,0` fails "busy" since pulse already
owns the card.

### 3. Whisper makes up text on silence

When a clip is silent or near-silent, whisper confidently hallucinates, usually
"Thanks for watching!" or "Thank you." `audio_publisher.py` filters those out before
publishing to `/audio/transcribed`: it skips clips under an RMS floor, drops results
with high no-speech probability, low average log-prob, or a too-high compression
ratio, and throws away a list of known hallucination phrases.

---

### Installation & dependencies

Confirmed working on: **Jetson Orin NX, JetPack / L4T R36.4.3, Ubuntu 22.04, Python
3.10.12, ROS 2 Humble.**

### System packages / CLI tools (used by the checks)

`lsusb`, `v4l2-ctl`, `arecord`, `pactl`, `udevadm`, `ffmpeg` — all present on this
image. If any are missing:

```bash
sudo apt update
sudo apt install usbutils v4l-utils alsa-utils pulseaudio-utils udev ffmpeg
```

### Python packages

```bash
pip install numpy opencv-python pyserial sounddevice openai-whisper
```

Currently installed and verified: `numpy 1.23.5`, `opencv 4.10.0`, `pyserial 3.5`,
`sounddevice`, `whisper`. `cv_bridge` comes from ROS. `Rosmaster_Lib` is the
Yahboom-provided library for the control board (already installed on this robot).

### Permissions & udev (one-time setup)

* **`dialout` group** — needed to open the serial ports. The `jetson` user is
 already in it (`groups` shows `dialout`). On a fresh user:
 `sudo usermod -aG dialout $USER` then log out/in.
* **Stable serial symlinks** — `/etc/udev/rules.d/ydlidar.rules` pins the LiDAR's
 CP2102 to `/dev/ydlidar`, and `/etc/udev/rules.d/serial.rules` pins the CH340 to
 `/dev/myserial`. **Getting this rule right was a roadblock** — see
 [Roadblocks](#roadblocks).

## 6. Quick reference

```bash
# one-shot: is the whole robot healthy? (run with ROS drivers DOWN)
source /opt/ros/humble/setup.bash
cd ~/sidharth_dev/test_sensors && python3 check_all_sensors.py


# individual device checks
python3 ~/sidharth_dev/audio_record/check_audio.py        # microphone
python3 ~/sidharth_dev/camera/check_camera.py             # camera
python3 ~/sidharth_dev/navigation/check_lidar.py          # LiDAR
python3 ~/sidharth_dev/navigation/check_control_board.py  # myserial wiring
python3 ~/sidharth_dev/navigation/check_motors.py         # motor board


# ROS data-flow checks (run with the drivers UP)
python3 ~/sidharth_dev/test_sensors/sensor_health.py            # passive
python3 ~/sidharth_dev/test_sensors/sensor_health.py --active   # speaks + MOVES robot


# device / firmware inventory
python3 ~/sidharth_dev/test_sensors/test.py
```
