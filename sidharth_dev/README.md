# Deliverable 1 - Confirm the car and sensors work

# Yahboom Robot — Sensor & Interface Test Suite

This repository is the deliverable for **Milestone 1: "Confirm the car and sensors
work."** It contains one small, independent test script per device on the robot,
plus a single combined checker that runs them all and prints one PASS/FAIL table.

| Assignment item | Where it lives |
|---|---|
| Identify the camera, LiDAR, microphone, motor-control, and ROS interfaces | [`test_sensors/test.py`](test_sensors/test.py) (inventory) + the per-device USB scans |
| One working test script per available sensor / interface | [`camera/check_camera.py`](camera/check_camera.py), [`audio_record/check_audio.py`](audio_record/check_audio.py), [`navigation/check_lidar.py`](navigation/check_lidar.py), [`navigation/check_motors.py`](navigation/check_motors.py), [`navigation/check_control_board.py`](navigation/check_control_board.py) |
| ROS-interface (data-flow) tests | [`test_sensors/sensor_health.py`](test_sensors/sensor_health.py) |
| One combined preflight + overall table | [`test_sensors/check_all_sensors.py`](test_sensors/check_all_sensors.py) |
| Installation steps & unresolved errors | this file + [`ROADBLOCKS.md`](ROADBLOCKS.md) |

> The combined checker and its example output are documented in their own section:
> [**The combined checker — `check_all_sensors.py`**](#the-combined-checker--check_all_sensorspy).

---



## 1. Map of what is plugged in and what it actually does:

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
├── README.md                  ← this file (status + how to run)
├── ROADBLOCKS.md              ← problems we hit and how we solved them
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

The mic is the ORBBEC depth sensor on ALSA `card 0`.

* **usb** — looks for `orbbec` in `lsusb`.
* **present** — `/proc/asound/card0` exists (the OS handle for the sound card).
* **working** — records ~1 s with `arecord` and measures **RMS** (loudness). Below
 an RMS of 5 it is treated as digital silence (muted / wrong source / not streaming).

```bash
cd ~/sidharth_dev/audio_record
python3 check_audio.py
```

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

### 3.5 Control-board wiring/identity — `navigation/check_control_board.py`

## FIX THIS
This is the **missing identity check** that the others can't do. `check_motors.py`
proves *some* board answers; this proves `/dev/myserial` is wired to the **right
chip**. It inspects only the *plumbing* (pure `os` + `udevadm`, no ROS, no opening
the port), so it is safe to run even while a driver owns the port.

* **usb** — is the control board's own chip `1a86:7523` on the bus? (stricter than
 the motor check, which matches any serial bridge).
* **present** — does `/dev/myserial` exist and is it read/write? (distinguishes a
 missing link from a *dangling* one).
* **identity (working)** — does `/dev/myserial` actually resolve to `1a86:7523`?
 If it resolves to the LiDAR's `10c4:ea60` it says so out loud: *"myserial is bound
 to the LiDAR — rebind it."* This is the check that would have caught the udev
 mis-bind that cost us a debugging session (see [`ROADBLOCKS.md`](ROADBLOCKS.md)).

```bash
cd ~/sidharth_dev/navigation
python3 check_control_board.py
```

---

## 4. Cross-cutting tools

### `test_sensors/sensor_health.py` — ROS data-flow ("liveness") checks

Where the per-device checks talk to hardware directly, this one checks the **ROS
interface**: it subscribes to the live topics and asks "is real data flowing at a
healthy rate?". **Liveness == data at the expected rate, not "a process exists",**
so it assumes the matching drivers are already running.

* `camera` → `/camera/image_raw` ≥ ~25 Hz and not all-black
* `lidar` → `/scan` ≥ ~5 Hz with finite ranges
* `mic` → 1 s `arecord`, RMS above the noise floor
* `motors` → `/odom` publishing

Passive (safe) by default; `--active` additionally asks you to speak (whisper
transcribes it) and **briefly drives the robot** to confirm `/odom` moves, then
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

Run it with the **drivers down**  each `check_working` actually exercises its
device (records 1 s, grabs a frame, spins the LiDAR, reads the board), and those
ports are single-access, so a running driver would make `check_working` say `busy`.

### How it produces the overall table

Each per-device checker contributes its three core rows (`usb`, `present`,
`working`; `control` contributes `usb`, `present`, `identity`). The printer measures
the longest subsystem name and the longest check name, left-aligns every column,
tags each row `[ ok ]` or `[FAIL]`, and finishes with a one-line tally
(`N checks, M failed.`). The process exit code is `0` only when `M == 0`.

### Example output (full, captured 2026-06-29 — all green)

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
 [ ok ] audio    working   hears something (RMS=2887)
 [ ok ] camera   usb       Bus 001 Device 010: ID 2bc5:050f Orbbec 3D Technology International, Inc USB 2.0 Camera
 [ ok ] camera   present   /dev/video0 exists
 [ ok ] camera   working   grabbed 640x480 frame (mean=126.3), saved /tmp/camera_check.jpg
 [ ok ] lidar    usb       Bus 001 Device 011: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
 [ ok ] lidar    present   /dev/ydlidar -> /dev/ttyUSB0
 [ ok ] lidar    working   streaming 5257 bytes in 1s (looks like YDLidar packets)
 [ ok ] control  usb       Bus 001 Device 007: ID 1a86:7523 QinHeng Electronics CH340 serial converter
 [ ok ] control  present   /dev/myserial -> /dev/ttyUSB1
 [ ok ] control  identity  /dev/myserial -> /dev/ttyUSB1 is the control board (1a86:7523)
 [ ok ] motors   usb       Bus 001 Device 011: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
 [ ok ] motors   present   usable serial port(s): ['/dev/myserial', '/dev/ttyUSB0', '/dev/ttyTHS1']
 [ ok ] motors   working   board v3.6 @ /dev/myserial, battery 11.3V


15 checks, 0 failed.
```

Reading the table: the `audio`/`camera` `usb` rows print whichever Orbbec line
`lsusb` matched first (both Orbbec devices share the "Orbbec" string); `lidar
working` shows real bytes streamed off the spinning LiDAR; `control identity`
confirms `/dev/myserial` resolves to the CH340 (`1a86:7523`) and **not** the LiDAR;
and `motors working` reports live firmware `v3.6` and battery `11.3 V` read straight
off the board.

---

## 5. Installation & dependencies

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
 [`ROADBLOCKS.md`](ROADBLOCKS.md).

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
