"""Scan a card in a focused Terminal to open normal YouTube Music on macOS."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode


def load_cards(path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not data:
        raise ValueError("Expected a nonempty card map")
    cards = {}
    for key, value in data.items():
        key = key.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{14}", key) or key in cards:
            raise ValueError("Expected unique 14-character hexadecimal card IDs")
        if not isinstance(value, dict):
            raise ValueError("Each card needs a title and playlist_id")
        title, playlist_id = value.get("title"), value.get("playlist_id")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Missing playlist title")
        if not isinstance(playlist_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", playlist_id):
            raise ValueError("Invalid playlist ID")
        start_video_id = value.get("start_video_id")
        if start_video_id is not None:
            if not isinstance(start_video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", start_video_id):
                raise ValueError("Invalid start video ID")
            url = "https://music.youtube.com/watch?" + urlencode({"v": start_video_id, "list": playlist_id})
        else:
            url = "https://music.youtube.com/playlist?" + urlencode({"list": playlist_id})
        cards[key] = {
            "title": title,
            "url": url,
        }
    return cards


class Launcher:
    def __init__(self, cards, dry_run=False, run=subprocess.run):
        self.cards = cards
        self.dry_run = dry_run
        self.run = run
        self.opened = set()

    def scan(self, token):
        token = token.strip().lower()
        if not token:
            return
        if token not in self.cards:
            print(f"Unknown card: {token!r}. Browser unchanged.", flush=True)
            return
        if token in self.opened:
            print("Already opened this card this session; use the existing browser tab.", flush=True)
            return
        card = self.cards[token]
        if not self.dry_run:
            # Open the official site; no extraction, login handling or injected scripts.
            self.run(["/usr/bin/open", card["url"]], check=True, timeout=10)
        self.opened.add(token)
        print(f"{'DRY RUN: would open' if self.dry_run else 'Opened'}: {card['title']}", flush=True)
        print("The browser may need a Play click. Opening a URL does not confirm playback.", flush=True)
        print("Browser is now focused: click back into this Terminal BEFORE scanning again.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, default=Path(__file__).resolve().parents[1] / "cards.youtube.example.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        cards = load_cards(args.cards)
        if sys.platform != "darwin" and not args.dry_run:
            raise ValueError("This launcher is for macOS; use --dry-run elsewhere")
        launcher = Launcher(cards, args.dry_run)
        print("Ready. Focus this Terminal, then scan your playlist card.", flush=True)
        print("Repeated cards will not create more tabs. Type quit + Enter or Ctrl+C to exit.", flush=True)
        print("Exiting does NOT stop browser music; use the speaker or browser controls.", flush=True)
        for line in sys.stdin:
            if line.strip().lower() == "quit":
                break
            try:
                launcher.scan(line)
            except (OSError, subprocess.SubprocessError) as error:
                print(f"Could not open playlist: {error}. Scan again to retry.", flush=True)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
