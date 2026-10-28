"""Focused-terminal RFID prototype; macOS afplay output, no dependencies."""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


def load_cards(path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not data:
        raise ValueError("Card map must be a nonempty JSON object")
    cards = {}
    for raw_id, item in data.items():
        card_id = raw_id.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{14}", card_id):
            raise ValueError("Card IDs must be 14 hexadecimal characters stored as strings")
        if card_id in cards:
            raise ValueError("Duplicate normalized card ID")
        if not isinstance(item, dict):
            raise ValueError("Each card needs a title and file")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise ValueError("Each card needs a nonempty title")
        if not isinstance(item.get("file"), str) or not item["file"].strip():
            raise ValueError("Each card needs a file path")
        media = Path(item["file"]).expanduser()
        if not media.is_absolute():
            media = path.parent / media
        media = media.resolve()
        if not media.is_file():
            raise ValueError(f"Missing audio file for {item['title']}: {media}")
        cards[card_id] = {"title": item["title"], "file": str(media)}
    return cards


class Player:
    def __init__(self, cards, dry_run=False, launch=subprocess.Popen, clock=time.monotonic):
        self.cards = cards
        self.dry_run = dry_run
        self.launch = launch
        self.clock = clock
        self.process = None
        self.last_id = None
        self.last_scan = 0

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
        self.last_id = None

    def check_exit(self):
        if self.process is not None:
            status = self.process.poll()
            if status is not None:
                self.process = None
                if status != 0:
                    print(f"Playback failed (afplay exit {status}). Check the file/audio output.", flush=True)

    def handle(self, line):
        token = line.strip().lower()
        if not token:
            return
        if token == "stop":
            self.stop()
            print("Stopped.", flush=True)
            return
        if token not in self.cards:
            print(f"Unknown card: {token!r}. Current playback unchanged.", flush=True)
            return
        now = self.clock()
        if token == self.last_id and now - self.last_scan < 1.5:
            self.last_scan = now
            print("Duplicate scan ignored.", flush=True)
            return
        item = self.cards[token]
        # Check before stopping: a removed file must not interrupt current audio.
        if not Path(item["file"]).is_file():
            print("Audio file is missing; current playback unchanged.", flush=True)
            return
        self.stop()
        if not self.dry_run:
            # Argument list preserves spaces and never interprets shell syntax.
            self.process = self.launch(["/usr/bin/afplay", "-v", "0.25", item["file"]])
        self.last_id, self.last_scan = token, now
        print(f"{'DRY RUN: would play' if self.dry_run else 'Playing'}: {item['title']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, default=Path(__file__).resolve().parents[1] / "cards.example.json")
    parser.add_argument("--dry-run", action="store_true", help="Check mappings without playing sound")
    args = parser.parse_args()
    player = None
    try:
        cards = load_cards(args.cards.resolve())
        if not args.dry_run and sys.platform != "darwin":
            raise ValueError("Playback backend is macOS only; use --dry-run elsewhere")
        player = Player(cards, args.dry_run)
        print("Ready. Keep this Terminal focused. Scan a card, or type its ID and Enter.", flush=True)
        print("Type stop + Enter to stop. Type quit + Enter or press Ctrl+C to exit.", flush=True)
        print("Rescan after 1.5 seconds to restart. Output uses the Mac's selected audio device.", flush=True)
        for line in sys.stdin:
            player.check_exit()
            if line.strip().lower() == "quit":
                break
            player.handle(line)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        if player is not None:
            player.stop()


if __name__ == "__main__":
    sys.exit(main())
