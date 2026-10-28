# Card Play

Built by [Curio](https://github.com/project-curio).

A DIY, card-controlled music player for children. Pick a card, tap it on a USB RFID reader, and play a lesson, a folder of songs, or a YouTube Music playlist through a speaker.

The player runs on a Raspberry Pi. An adult uses the desktop to set it up; the goal is everyday listening without a phone or screen. You supply the cards, audio, and any streaming account.

**Status: experimental build, October 2026.** Card-triggered YouTube Music playback on the Pi is user-confirmed. Local playback and speaker reconnection after one reboot are also user-confirmed. The corrected manual SSH keyring-unlock flow is user-confirmed. Repeated boots without a monitor, playback after SSH disconnect, all speaker buttons, and sustained playback still need physical testing. This is a project to build and improve, not a finished appliance.

## Build your own

Follow these guides in order. They use your own username, reader, cards, and speaker:

1. [Parts and compatibility](docs/01-hardware.md) — what you need and what to check before buying.
2. [Set up the Raspberry Pi](docs/02-pi-setup.md) — install, check audio, identify the reader, and enroll your first card.
3. [Add music and cards](docs/03-cards-and-content.md) — local files, folders, playlists, stop, and shutdown.
4. [Use, maintain, and troubleshoot](docs/04-operation.md) — startup, recovery, updates, and acceptance checks.

Allow time for hardware troubleshooting. The current reader selection is specific to two measured device names; another reader can require a small source change as well as a device permission rule. Read the compatibility guide first.

## What it does

| Feature | Implementation and limits |
| --- | --- |
| Local audio | VLC plays a file or a folder queue. Local content does not require a streaming account. |
| YouTube Music | Opens an ordinary playlist watch URL in a dedicated Chromium profile; adult sign-in and internet access may be needed. |
| Card input | Python/evdev reads the selected USB keyboard-style reader independently of window focus. |
| Switching | Controller stops its previous player before launching the next selection. Physical no-overlap testing remains necessary. |
| Controls | Stop card and double-scan shutdown card; speaker media buttons need verification with your setup. |
| Startup | Desktop autostart launches a supervised systemd user service. A graphical session is required. |

Spotify, voice interaction, offline YouTube downloads, and a setup UI are **not implemented**. Browser restarts on each deliberate playlist selection; login data persists, playback position does not. Autologin can leave the desktop keyring locked and block streaming after boot.

```text
RFID card → USB reader → Python controller → VLC (local audio)
                                         → Chromium (YouTube Music)
                                         → selected audio output → speaker
```

## Try the controller without hardware

From the project directory on macOS or Linux with Python 3:

```sh
python3 scripts/pi_player.py --config cards.public.example.json --check
printf '00000000000001\n00000000000002\nquit\n' | python3 scripts/pi_player.py --config cards.public.example.json --simulate
```

These commands validate and simulate a lesson selection and stop. They do not play sound or check devices, media files, or accounts. The included card numbers are fictional; enroll your own before real use. The Raspberry Pi is the supported build path; Mac scripts are development prototypes.

## Contribute and follow the build

See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and useful hardware reports. No music, browser credentials, or streaming subscription is supplied.

## License

[MIT](LICENSE). Use, modify, and share the code under that license. Bring your own audio and streaming account; the license does not cover third-party music or artwork.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Runtime directories and the service retain the `curio-player` name for compatibility. Card Play is the device/project name.
