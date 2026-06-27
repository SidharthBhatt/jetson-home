#!/usr/bin/env python3
"""
test.py - inventory every device on the robot: vendor, model, and (where the
device actually exposes it) firmware version.

There is no single "give me the firmware" call, so this runs in two passes:

  Pass 1  USB descriptor scan via /sys   -> vendor + model + USB-rev for EVERY
                                            usb device. No deps, no root.
  Pass 2  device-specific probes         -> the REAL firmware version, but only
                                            for devices that speak a protocol we
                                            can talk to (the Yahboom driver board
                                            and the Jetson host).

Cameras, the mic and the gamepad do not expose a queryable firmware version, so
for those the "version" column shows the USB device-release (bcdDevice) and the
source is marked 'usb-descriptor' to be honest about it.

Run:  python3 test.py


"""

import os
import re
import glob
import time


# --------------------------------------------------------------------------
# the uniform record - every probe returns this same shape so we can print
# them all in one table (the "contract")
# --------------------------------------------------------------------------
def make_record(name, vendor="?", model="?", version="?", source="?"):
    return {"name": name, "vendor": vendor, "model": model,
            "version": version, "source": source}


def read_text(path):
    """Read a small sysfs/proc file, return stripped string or None."""
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


# --------------------------------------------------------------------------
# Pass 1 - USB descriptor scan (works for everything, no dependencies)
# --------------------------------------------------------------------------
def scan_usb():
    records = []
    for dev in sorted(glob.glob("/sys/bus/usb/devices/*")):
        vid = read_text(os.path.join(dev, "idVendor"))
        if vid is None:
            continue  # interface node, not a whole device

        pid = read_text(os.path.join(dev, "idProduct")) or "????"
        mfr = read_text(os.path.join(dev, "manufacturer")) or "unknown"
        product = read_text(os.path.join(dev, "product")) or "unknown"
        bcd = read_text(os.path.join(dev, "bcdDevice")) or "?"

        # hubs and host controllers aren't devices we care about
        low = product.lower()
        if "hub" in low or "host controller" in low or "billboard" in low:
            continue

        records.append(make_record(
            name=product.strip(),
            vendor=f"{mfr.strip()} [{vid}:{pid}]",
            model=product.strip(),
            version=bcd,              # USB device-release, NOT true firmware
            source="usb-descriptor",
        ))
    return records


# --------------------------------------------------------------------------
# Pass 2a - Jetson host (L4T / JetPack version)
# --------------------------------------------------------------------------
def probe_jetson():
    text = read_text("/etc/nv_tegra_release")
    if not text:
        return None
    # e.g.  "# R36 (release), REVISION: 4.3, GCID: ..., DATE: ..."
    m = re.search(r"R(\d+).*REVISION:\s*([\d.]+)", text)
    version = f"L4T R{m.group(1)}.{m.group(2)}" if m else text
    return make_record("Jetson (host)", vendor="NVIDIA",
                       model="Tegra Orin NX", version=version,
                       source="nv_tegra_release")


# --------------------------------------------------------------------------
# Pass 2b - Yahboom driver board firmware via Rosmaster_Lib.get_version()
# The board's serial port can't be known from the udev names (myserial,
# rplidar, ydlidar all symlink to ttyUSB0), so we TRY each candidate and
# keep the first that answers with a real version.
# --------------------------------------------------------------------------
def probe_board():
    try:
        from Rosmaster_Lib import Rosmaster
    except ImportError:
        return make_record("Driver board (motors/IMU)", vendor="Yahboom",
                           model="Rosmaster",
                           version="Rosmaster_Lib not installed",
                           source="rosmaster")

    # dedup by real path: /dev/myserial, /dev/rplidar etc. all symlink to the
    # same ttyUSB0, so opening each "name" would hit one port repeatedly.
    candidates, seen = [], set()
    for port in ["/dev/myserial", "/dev/ttyUSB0", "/dev/ttyTHS1"]:
        if not os.path.exists(port):
            continue
        real = os.path.realpath(port)
        if real not in seen:
            seen.add(real)
            candidates.append(port)

    no_access = []
    for port in candidates:
        if not (os.access(port, os.R_OK) and os.access(port, os.W_OK)):
            no_access.append(port)             # e.g. ttyTHS1 without dialout group
            continue
        bot = None
        try:
            bot = Rosmaster(com=port)
            bot.create_receive_threading()      # background thread parses frames
            time.sleep(1.0)                      # give it a moment to read one
            ver = bot.get_version()
            if ver and float(ver) > 0:
                return make_record("Driver board (motors/IMU)", vendor="Yahboom",
                                   model="Rosmaster", version=f"v{ver}  (@{port})",
                                   source="rosmaster")
        except Exception:
            pass
        finally:
            if bot is not None and hasattr(bot, "ser"):
                try:
                    bot.ser.close()              # free the port for bringup later
                except Exception:
                    pass

    if no_access:
        hint = f"no response; can't open {','.join(no_access)} (add user to 'dialout' group)"
    else:
        hint = "no response (check port/power, or bringup may be using it)"
    return make_record("Driver board (motors/IMU)", vendor="Yahboom",
                       model="Rosmaster", version=hint, source="rosmaster")


# --------------------------------------------------------------------------
# Pass 2c - lidar: real firmware needs the YDLidar SDK python binding, which
# isn't installed here, so be honest rather than fake it.
# --------------------------------------------------------------------------
def probe_lidar():
    try:
        import ydlidar  # noqa: F401
    except ImportError:
        return make_record("Lidar", vendor="(YDLidar/RPLidar via CP2102)",
                           model="serial-USB",
                           version="ydlidar SDK not installed - firmware not probed",
                           source="ydlidar-sdk")
    # If the SDK ever gets installed, this is where getDeviceInfo() would go.
    return make_record("Lidar", vendor="?", model="?",
                       version="SDK present - add getDeviceInfo() probe",
                       source="ydlidar-sdk")


# --------------------------------------------------------------------------
# pretty-print all records as one table
# --------------------------------------------------------------------------
def print_table(records):
    cols = [("DEVICE", "name"), ("VENDOR [usb id]", "vendor"),
            ("VERSION", "version"), ("SOURCE", "source")]
    widths = {key: len(title) for title, key in cols}
    for r in records:
        for _, key in cols:
            widths[key] = max(widths[key], len(str(r[key])))

    line = "  ".join(title.ljust(widths[key]) for title, key in cols)
    print(line)
    print("-" * len(line))
    for r in records:
        print("  ".join(str(r[key]).ljust(widths[key]) for _, key in cols))


def main():
    records = []
    records += scan_usb()          # Pass 1
    # records.append(probe_board())  # Pass 2b
    records.append(probe_lidar())  # Pass 2c
    host = probe_jetson()          # Pass 2a
    if host:
        records.append(host)

    print_table(records)
    print(f"\n{len(records)} devices listed.")


if __name__ == "__main__":
    main()


'''

test.py — "what's attached and what version" (two passes)
read_text(path) — a tiny helper that reads a small file and returns None if it doesn't exist. Used everywhere so a missing file never crashes the script.

scan_usb() (Pass 1) — the universal layer. It globs /sys/bus/usb/devices/* and, for each device, reads the kernel's descriptor files: idVendor, idProduct, manufacturer, product, bcdDevice. It skips hubs and host controllers (you don't care about those), and builds one record per real device. This is how it lists the camera, ORBBEC, lidar bridge, gamepad — all in one loop, no dependencies. The version here is bcdDevice, the USB device-release number (not true firmware — the code is honest about that).

probe_jetson() (Pass 2a) — reads /etc/nv_tegra_release and uses a regex to pull out R36 + REVISION: 4.3, formatting it as L4T R36.4.3. That's your Jetson's OS/firmware version.

probe_board() (Pass 2b) — the driver board's real firmware. The tricky parts:

It builds a list of candidate serial ports (/dev/myserial, /dev/ttyUSB0, /dev/ttyTHS1) but deduplicates by os.path.realpath — because myserial is just a symlink to ttyUSB0, so without this it'd open the same port twice.
It skips ports it can't read/write (os.access) and reports that as "add user to dialout" instead of crashing — that's the error you saw before the dialout fix.
For a usable port it opens Rosmaster(com=port), starts the receive thread, waits a second, and calls get_version(). First port that answers with a real version wins; otherwise it returns a "no response" hint.
probe_lidar() (Pass 2c) — tries import ydlidar; since the SDK isn't installed, it honestly says so rather than faking a number.

print_table() — measures the longest value in each column, then prints everything left-aligned. main() just runs the four probes, collects the records, and prints them.
'''