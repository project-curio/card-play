# 2. Set up the Raspberry Pi

[Parts](01-hardware.md) · Next: [Cards and content](03-cards-and-content.md)

This is a reproducible setup procedure to test on your hardware, not a claim that every step has passed on every Pi. Run commands in the **Pi desktop terminal as your normal desktop user**, except where explicitly stated. Do not run the player or installer with sudo.

## 1. Prepare the OS

1. Back up any existing microSD contents you need. Writing an OS image erases the selected card.
2. On your setup computer, use [Raspberry Pi Imager](https://www.raspberrypi.com/documentation/computers/getting-started.html#install-an-operating-system). Choose your Pi model and Raspberry Pi OS **64-bit with Desktop**, not Lite.
3. Set your own username, password, hostname, Wi-Fi, and optional SSH settings. Verify the target storage before writing.
4. Insert the card, connect monitor/keyboard/mouse, and boot with the RFID reader disconnected.
5. Finish desktop setup and check internet access. Record `cat /etc/os-release` and `uname -r` when reporting problems. The latest original build used a Trixie desktop installation; other releases need their own verification.

## 2. Get the complete source

Download [Card Tap from GitHub](https://github.com/project-curio/card-tap) using **Code → Download ZIP**, extract into your home directory, and rename the extracted directory `curio-player-source`. Or, with Git installed:

```sh
git clone https://github.com/project-curio/card-tap.git ~/curio-player-source
cd ~/curio-player-source
ls scripts/pi_player.py scripts/install_pi.py cards.pi.example.json
```

For a ZIP download, also run `cd ~/curio-player-source` before continuing.

## 3. Install dependencies

```sh
sudo apt update
sudo apt install python3 python3-evdev vlc chromium pulseaudio-utils bluez
python3 scripts/install_pi.py
```

The installer creates the runtime, user service, desktop autostart entry, and a neutral `~/.config/curio-player/cards.json` on first installation. It does not start playback and preserves existing configuration. Replace fictional card IDs and empty audio settings before real playback.

## 4. Hear audio before using cards

1. Use the desktop Bluetooth menu to pair/connect your speaker and choose it as the output. For a wired/USB output, select that output instead.
2. Check the audio server and available sinks:

```sh
pactl info
pactl list short sinks
bluetoothctl devices
```

3. Play one of your own audio files in VLC and confirm sound comes from the intended speaker. Set a comfortable level in the desktop and on the speaker.
4. Open `~/.config/curio-player/cards.json` in a text editor. Put the exact sink name (the second column of `pactl list short sinks`) in `audio_sink`.
5. For Bluetooth, put your paired speaker's actual address in `speaker_address`. To allow reconnects, run `bluetoothctl trust` followed by that address. Leave `speaker_address` empty for a non-Bluetooth output.

A working PipeWire desktop needs no historical PulseAudio disable/mask repair. If `pactl info` fails, fix desktop audio first. The player preserves the selected volume; it does not enforce a loudness cap.

## 5. Identify and grant access to your reader

First complete the stability checks in [the hardware guide](01-hardware.md). Then find its event node:

```sh
cat /proc/bus/input/devices
```

Match the reader's `N: Name` and `H: Handlers` lines. The handler includes an `event` number. Substitute that number for `eventN` below:

```sh
udevadm info --attribute-walk --name=/dev/input/eventN
```

Find the reader's USB parent block containing `idVendor`, `idProduct`, and `serial`. Record these values locally. Do not use your normal keyboard's attributes. Create a local rule:

```sh
cp deploy/70-curio-reader.rules deploy/70-curio-reader.local.rules
nano deploy/70-curio-reader.local.rules
```

Replace the template rule with **one** line for your measured reader. Replace all three placeholders before installing:

```text
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{idVendor}=="YOUR_VENDOR", ATTRS{idProduct}=="YOUR_PRODUCT", ATTRS{serial}=="YOUR_SERIAL", TAG+="uaccess"
```

The attributes must belong to the same USB parent. If your reader has no serial or multiple matching keyboard interfaces, stop here and adapt device identification deliberately; do not grant access to every keyboard or add the user to the broad `input` group.

Check `READER_NAMES` and `open_reader()` in `scripts/pi_player.py` against the measured name and IDs. If they differ, add your exact name and adapt the vendor/product match to your reader, preserving the Enter capability check and exactly-one-device requirement. That is a source adaptation requiring tests, not a JSON setting. A different scan format also needs decoder changes. Reinstall after any source change:

```sh
python3 scripts/install_pi.py
sudo install -m 644 deploy/70-curio-reader.local.rules /etc/udev/rules.d/70-curio-reader.rules
sudo udevadm control --reload-rules
```

Unplug/replug the reader while logged into the local desktop. `uaccess` is for the active desktop session; SSH alone is not a substitute. See [udev rules](https://www.freedesktop.org/software/systemd/man/latest/udev.html) and [evdev device access](https://python-evdev.readthedocs.io/en/latest/tutorial.html) for the underlying mechanisms.

## 6. Enroll your cards

```sh
systemctl --user stop curio-player.service
python3 ~/.local/share/curio-player/pi_player.py --enroll
```

Scan each sticker, label it, and record the printed normalized 14-character ID. Press Ctrl+C when done. Enrollment prints IDs; it does not edit your configuration or write to the tags. It still needs a syntactically valid config, which the starter provides. Permission or device-selection errors must be resolved before continuing.

Follow [Cards and content](03-cards-and-content.md) to replace the fictional IDs and add your audio.

## 7. Start and verify

After configuring cards:

```sh
python3 ~/.local/share/curio-player/pi_player.py --check
~/.local/share/curio-player/session-start.sh
journalctl --user -u curio-player.service -f
```

`--check` validates configuration only. Scan the local card and listen. Scan Stop. Try a YouTube card only after the local path works. Sign in yourself in the dedicated browser if prompted, and unlock the desktop keyring if necessary. Ctrl+C exits the log viewer; it does not stop the service.

Do not remove the monitor yet. Continue with [startup and acceptance checks](04-operation.md).
