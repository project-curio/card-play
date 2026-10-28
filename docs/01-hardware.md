# 1. Parts and compatibility

[README](../README.md) · Next: [Pi setup](02-pi-setup.md)

## What to gather

| Part | Build reference | What matters for your build |
| --- | --- | --- |
| Computer | Raspberry Pi 5, 8 GB | Other models have not been verified by this project. |
| Power, storage, cooling | Pi 5 supply, microSD, case with active cooling | Use a supply suitable for the Pi and attached USB devices; select your own card capacity for your media. |
| Speaker | K9-M Bluetooth speaker | Bluetooth audio and media-button support are separate checks. A different speaker may behave differently. |
| Reader | USB HID keyboard RFID reader | Must work stably on your Pi and report a supported card format followed by Enter. Details below. |
| Tags | 13.56 MHz MIFARE Classic 1K stickers in the original build | Match tags to the reader's documented technology; frequency alone does not prove compatibility. |
| Cards | Cards with stickers and labels | The software maps the sticker ID; it does not write songs onto the sticker. |
| Setup equipment | Monitor, micro-HDMI cable, keyboard, mouse, network | Keep these available until boot and recovery are proven. |

No microphone, ReSpeaker board, soldering, or GPIO wiring is required for this version. The Pi 5 has no built-in 3.5 mm audio jack; an AUX speaker needs a suitable audio adapter. Consult the [official Pi setup documentation](https://www.raspberrypi.com/documentation/computers/getting-started.html) for power, storage, display, and OS preparation.

## Reader compatibility is the main hardware constraint

The controller currently accepts USB vendor/product `ffff:0035`, one of these exact input names, and an Enter-capable keyboard interface:

| Measured input name | Evidence from this build |
| --- | --- |
| `ARM CM0 USB HID Keyboard` | Replacement reader: user-confirmed card-triggered YouTube playback on Pi. Broader stability tests remain pending. |
| `SDZNKJLTD USB Reader` | Original reader: Pi USB controller failures observed, including through a hub. Do not treat this as a recommended Pi reader. |

These are device-reported names, not guarantees that a retail listing contains the same electronics. No universal plug-and-play reader support is claimed. The shipped udev rule is a placeholder template and must be adapted for your reader.

Supported scan formats are exactly 14 hexadecimal characters or 10 decimal digits representing an unsigned 32-bit value. The decimal format is normalized to 14 hexadecimal characters. Other lengths, prefixes, or byte orders require code and test changes. Confirm multiple stickers, including leading zeros; do not infer compatibility from one successful scan.

## Before installing the controller

1. Boot the Pi with the reader disconnected; confirm the desktop works.
2. Connect the reader. In a plain text editor, scan several tags. Record each complete string and whether Enter follows it. Avoid scanning into a shell prompt.
3. Run `lsusb` now and again after a minute. Scan at least 20 times.
4. Inspect `sudo journalctl -k -b -n 100 --no-pager`. Stop if USB devices disappear or logs show xHCI controller death. A software player cannot fix an unstable USB connection.
5. Continue to [Pi setup](02-pi-setup.md) only after stable input. Keep tiny stickers secured and cables/enclosure suitable for the intended child; set a comfortable volume during adult testing.
