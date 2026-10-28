import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("mac_playlist", Path(__file__).resolve().parents[1] / "scripts/mac_playlist.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        self.card = "000000000000aa"
        self.pid = "EXAMPLE_PLAYLIST_ID"
        self.url = "https://music.youtube.com/playlist?list=" + self.pid
        self.cards = {self.card: {"title": "Playlist", "url": self.url}}

    def test_known_card_opens_once_unknown_does_nothing(self):
        run = Mock()
        launcher = module.Launcher(self.cards, run=run)
        launcher.scan("not a card")
        run.assert_not_called()
        launcher.scan(self.card.upper())
        launcher.scan(self.card)
        run.assert_called_once_with(["/usr/bin/open", self.url], check=True, timeout=10)

    def test_failed_launch_can_be_retried(self):
        run = Mock(side_effect=[subprocess.CalledProcessError(1, "open"), None])
        launcher = module.Launcher(self.cards, run=run)
        with self.assertRaises(subprocess.CalledProcessError):
            launcher.scan(self.card)
        launcher.scan(self.card)
        self.assertEqual(run.call_count, 2)

    def test_dry_run_never_opens_browser(self):
        run = Mock()
        module.Launcher(self.cards, dry_run=True, run=run).scan(self.card)
        run.assert_not_called()

    def test_config_preserves_card_and_rejects_url_injection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cards.json"
            mapping = {self.card: {"title": "Playlist", "playlist_id": self.pid}}
            path.write_text(json.dumps(mapping))
            self.assertEqual(module.load_cards(path), self.cards)
            mapping[self.card]["playlist_id"] = "https://example.com/;bad"
            path.write_text(json.dumps(mapping))
            with self.assertRaises(ValueError):
                module.load_cards(path)

    def test_start_track_keeps_playlist_context_and_validates_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cards.json"
            mapping = {self.card: {"title": "Playlist", "playlist_id": self.pid, "start_video_id": "VIDEO_ID_11"}}
            path.write_text(json.dumps(mapping))
            self.assertEqual(module.load_cards(path)[self.card]["url"],
                             "https://music.youtube.com/watch?v=VIDEO_ID_11&list=" + self.pid)
            mapping[self.card]["start_video_id"] = "bad&list=other"
            path.write_text(json.dumps(mapping))
            with self.assertRaises(ValueError):
                module.load_cards(path)


if __name__ == "__main__":
    unittest.main()
