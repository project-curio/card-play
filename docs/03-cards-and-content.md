# 3. Add music and cards

[Pi setup](02-pi-setup.md) · Next: [Operation](04-operation.md)

All configuration lives in `~/.config/curio-player/cards.json`. The repository examples are templates, not your runtime configuration. Use your own audio and account; this project supplies neither music nor rights to redistribute it.

## 1. Add local audio

Create a folder and copy your own files into it using the desktop file manager:

```sh
mkdir -p ~/Music/curio
```

Name files in the order you want: `01 Welcome.mp3`, `02 Lesson.mp3`, and so on. Folder cards include direct, non-hidden files with `.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, or `.opus` extensions, sorted in natural filename order. Subfolders are not scanned. The extension alone does not guarantee that the file's codec will play; test it in VLC.

## 2. Edit the starter mapping

Stop the player while enrolling or editing:

```sh
systemctl --user stop curio-player.service
nano ~/.config/curio-player/cards.json
```

Replace the fictional keys with IDs from `--enroll`. Keep the keys quoted with all 14 characters, including leading zeros. A minimal configuration looks like this; the sink name and IDs below are illustrative:

```json
{
  "audio_sink": "YOUR_EXACT_SINK_NAME",
  "speaker_address": "",
  "cards": {
    "00000000000001": {
      "type": "folder",
      "title": "My lessons",
      "folder": "~/Music/curio"
    },
    "00000000000002": {"type": "stop", "title": "Stop"}
  }
}
```

JSON needs commas between entries, double quotes, and no comments or trailing commas. Make every card ID unique. `title` is an adult-readable label for the mapping; it is not spoken aloud.

## 3. Choose content types

Add these objects inside `cards`, under your enrolled IDs:

| Type | Required fields beyond `type` and `title` | Behavior |
| --- | --- | --- |
| `file` | `"file": "~/Music/curio/01 Welcome.mp3"` | Plays one file. |
| `folder` | `"folder": "~/Music/curio"` | Re-reads the folder each scan; queues supported files. |
| `youtube` | `playlist_id` and `start_video_id` | Opens YouTube Music at that video in the playlist. |
| `stop` | None | Stops playback and cancels a queued selection. |
| `shutdown` | None | Requires two scans of that card 2–8 seconds apart before requesting power-off. |

Absolute paths and `~/` paths are simplest. Relative paths resolve against the configuration directory, not the source directory.

## 4. Add a YouTube Music playlist

1. In YouTube Music, open a playlist and start the track you want to begin with.
2. Copy its watch URL. It should contain both `v=` and `list=` parameters.
3. Put the `v` value in `start_video_id` and the `list` value in `playlist_id`; do not paste the whole URL into either field. The video ID must be 11 characters. Use actual IDs, not invented examples.
4. Add a card with `type: youtube` and a meaningful title.
5. Validate and restart, scan the card, sign in in the dedicated Chromium window if needed, and check the first track, Next, Play/Pause, and natural advance.

The browser profile is `~/.local/share/curio-player/browser-profile/`. It holds account session data: never upload it. The controller uses a [separate Chromium data directory](https://www.chromium.org/developers/creating-and-using-profiles/); do not launch another browser against that directory while the player runs.

Streaming availability, ads, account requirements, and autoplay are controlled by the service. A successful browser launch is not proof of audible playback. This project does not download YouTube audio or implement offline YouTube playback.

## 5. Validate, restart, and label

```sh
python3 ~/.local/share/curio-player/pi_player.py --check
~/.local/share/curio-player/session-start.sh
```

Scan each card and confirm its actual result before adding artwork. The sticker remains unchanged when you edit the mapping. You can reassign a card simply by editing its entry and restarting the service.

A same-card scan within 1.5 seconds is ignored; a later scan restarts the selection. Unknown cards or missing local media leave current playback alone. A shutdown card has no audible confirmation yet: verify clean shutdown with a monitor before relying on it, and wait for shutdown to finish before unplugging power.
