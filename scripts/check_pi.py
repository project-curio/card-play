"""Read-only setup inventory. No installs, configuration changes, or playback."""

import json
import platform
import shutil
import subprocess
from pathlib import Path


def read_text(path):
    try:
        return Path(path).read_text().strip().strip("\x00")
    except OSError:
        return "unavailable"


def probe(command):
    if not shutil.which(command[0]):
        return "not installed"
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "check failed or timed out"
    if result.returncode:
        return "unavailable in this session"
    return result.stdout.strip() or "no devices reported"


def main():
    system = platform.system()
    report = {
        "system": system,
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "note": "Inventory only; this does not prove audible playback or card input.",
    }
    if system != "Linux":
        report["next_step"] = "Run this script on the Raspberry Pi, not the Mac."
    else:
        release = read_text("/etc/os-release")
        report["os"] = next(
            (line.split("=", 1)[1].strip('"') for line in release.splitlines()
             if line.startswith("PRETTY_NAME=")),
            "unknown",
        )
        report["model"] = read_text("/proc/device-tree/model")
        report["tools"] = {
            name: bool(shutil.which(name))
            for name in ("mopidy", "gst-launch-1.0", "aplay", "wpctl", "bluetoothctl")
        }
        report["alsa_outputs"] = probe(["aplay", "-l"])
        # A stable device alias helps select only the RFID reader later.
        # Names only: do not read keyboard events or dump configuration/secrets.
        inputs = Path("/dev/input/by-id")
        try:
            report["input_device_aliases"] = sorted(p.name for p in inputs.iterdir())
        except OSError:
            report["input_device_aliases"] = "unavailable"
        report["next_step"] = "Review the inventory and choose an audio output before installation."
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
