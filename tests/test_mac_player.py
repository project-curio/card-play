import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("mac_player", Path(__file__).resolve().parents[1] / "scripts/mac_player.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.audio = self.root / "lesson with spaces.m4a"
        self.audio.touch()
        self.card = "000000000000aa"
        self.cards = {self.card: {"title": "Lesson", "file": str(self.audio)}}

    def test_mapping_preserves_leading_zeros_and_relative_paths(self):
        mapping = self.root / "cards.json"
        mapping.write_text(json.dumps({self.card: {"title": "Lesson", "file": self.audio.name}}))
        self.assertEqual(module.load_cards(mapping), self.cards)

    def test_unknown_card_does_not_interrupt_and_repeat_is_debounced(self):
        launch = Mock()
        launch.return_value.poll.return_value = None
        player = module.Player(self.cards, launch=launch, clock=Mock(side_effect=[10, 10.5, 13]))
        player.handle(self.card.upper())
        player.handle("not a card; touch /tmp/no")
        player.handle(self.card)
        launch.assert_called_once_with(["/usr/bin/afplay", "-v", "0.25", str(self.audio)])
        launch.return_value.terminate.assert_not_called()
        player.handle(self.card)
        self.assertEqual(launch.call_count, 2)
        launch.return_value.terminate.assert_called_once()
        player.stop()

    def test_removed_file_does_not_stop_current_playback(self):
        player = module.Player(self.cards)
        current = Mock()
        player.process = current
        self.audio.unlink()
        player.handle(self.card)
        current.terminate.assert_not_called()

    def test_stop_and_dry_run(self):
        launch = Mock()
        player = module.Player(self.cards, dry_run=True, launch=launch)
        player.handle(self.card)
        player.handle("stop")
        launch.assert_not_called()
        self.assertIsNone(player.last_id)

    def test_shutdown_kills_unresponsive_child(self):
        player = module.Player(self.cards)
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [module.subprocess.TimeoutExpired("afplay", 2), 0]
        player.process = child
        player.stop()
        child.kill.assert_called_once()
        self.assertIsNone(player.process)


if __name__ == "__main__":
    unittest.main()
