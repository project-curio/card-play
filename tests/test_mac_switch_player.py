import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mac_switch_player as m


class MacSwitchTests(unittest.TestCase):
    def test_real_mapping_and_dry_switch_both_ways(self):
        config = m.load_config(Path(__file__).resolve().parents[1] / 'cards.mac.example.json')
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        (Path(folder.name) / '01 Lesson.mp3').write_bytes(b'test audio fixture')
        config['cards']['000000000000aa']['folder'] = folder.name
        backend = m.MacBackend(config, True)
        controller = m.Controller(config, backend)
        with patch.object(m.subprocess, 'Popen') as launch:
            for token in ('000000000000aa', '000000000000bb', '000000000000aa'):
                controller.scan(token)
                self.assertEqual(controller.active, token)
            controller.stop()
            launch.assert_not_called()

    def test_stop_uses_owned_process_not_group_signals(self):
        backend = m.MacBackend({})
        child = Mock()
        child.poll.return_value = None
        backend.child, backend.group = child, 123
        with patch.object(m.os, 'killpg', side_effect=PermissionError('denied')) as group_signal:
            backend.stop()
        group_signal.assert_not_called()
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=5)
        self.assertIsNone(backend.child)

    def test_denied_termination_blocks_switch_and_keeps_ownership(self):
        backend = m.MacBackend({})
        child = Mock()
        child.poll.return_value = None
        child.terminate.side_effect = PermissionError('denied')
        backend.child = child
        with self.assertRaisesRegex(RuntimeError, 'Close that player window manually'):
            backend.stop()
        self.assertIs(backend.child, child)

    def test_stop_waits_for_real_owned_child(self):
        backend = m.MacBackend({})
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], start_new_session=True)
        backend.child, backend.group = child, child.pid
        try:
            backend.stop()
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_local_page_encodes_path_and_escapes_script_markup(self):
        page = m.lesson_page({'title': '</script><img src=x>', 'file': '/tmp/a b.m4a'})
        self.assertIn('file:///tmp/a%20b.m4a', page)
        self.assertNotIn('</script><img', page)
        self.assertIn('&lt;/script&gt;', page)

    def test_lesson_media_actions_pause_resume_and_stop(self):
        if not shutil.which('node'):
            self.skipTest('Node unavailable for JavaScript media-handler test')
        page = m.lesson_page({'title': 'Lessons', '_tracks': ['/tmp/first.m4a', '/tmp/second.wav', '/tmp/third.m4a']})
        script = page.split('<script>')[1].split('</script>')[0]
        harness = '''const vm = require('node:vm');
const assert = require('node:assert/strict');
const handlers = {}, events = {};
const audio = {paused:true,currentTime:17,play(){this.paused=false; if(events.play)events.play(); return Promise.resolve();},pause(){this.paused=true; if(events.pause)events.pause();},addEventListener(n,f){events[n]=f;}};
const status = {};
const mediaSession = {setActionHandler(n,f){handlers[n]=f;}};
vm.runInNewContext(SCRIPT, {document:{getElementById:id=>id==='lesson'?audio:status}, navigator:{mediaSession}, MediaMetadata:function(x){Object.assign(this,x);}});
assert.equal(audio.paused,false);
handlers.pause(); assert.equal(audio.paused,true); assert.equal(mediaSession.playbackState,'paused');
handlers.play(); assert.equal(audio.paused,false); assert.equal(mediaSession.playbackState,'playing');
handlers.stop(); assert.equal(audio.paused,true); assert.equal(audio.currentTime,0);
assert.equal(audio.src,'file:///tmp/first.m4a');
handlers.nexttrack(); assert.equal(audio.src,'file:///tmp/second.wav');
assert.equal(mediaSession.metadata.title,'second');
handlers.previoustrack(); assert.equal(audio.src,'file:///tmp/first.m4a');
handlers.previoustrack(); assert.equal(audio.src,'file:///tmp/first.m4a');
events.ended(); assert.equal(audio.src,'file:///tmp/second.wav');
events.ended(); assert.equal(audio.src,'file:///tmp/third.m4a');
handlers.nexttrack(); assert.equal(audio.src,'file:///tmp/third.m4a');
events.ended(); assert.equal(mediaSession.playbackState,'none');
assert.equal(audio.src,'file:///tmp/third.m4a');
'''.replace('SCRIPT', json.dumps(script))
        subprocess.run(['node', '-e', harness], check=True, capture_output=True, timeout=10)

    def test_folder_filters_and_natural_order_refresh_on_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ('10 Song.m4a', '2 Song.wav', '1 Song.mp3', '.hidden.wav', 'notes.txt'):
                (folder / name).touch()
            (folder / 'nested').mkdir()
            (folder / 'nested/0 Song.mp3').touch()
            card = {'type': 'folder', 'folder': str(folder)}
            self.assertEqual([p.name for p in m.local_tracks(card)], ['1 Song.mp3', '2 Song.wav', '10 Song.m4a'])
            (folder / '3 Added.M4A').touch()
            m.validate_local(card)
            self.assertEqual(len(card['_tracks']), 4)

    def test_empty_folder_does_not_interrupt_current_source(self):
        with tempfile.TemporaryDirectory() as directory:
            card = {'type': 'folder', 'title': 'Empty', 'folder': directory}
            backend = m.MacBackend({}, True)
            controller = m.Controller({'cards': {'00000000000001': card}}, backend)
            controller.active = 'previous'
            with patch.object(backend, 'stop') as stop:
                with self.assertRaisesRegex(ValueError, 'No supported audio'):
                    controller.scan('00000000000001')
                stop.assert_not_called()
                self.assertEqual(controller.active, 'previous')

    def test_launch_owns_separate_profile_not_default_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = m.MacBackend({})
            backend.runtime = Path(folder)
            backend.profile = Path(folder) / 'profile'
            with patch.object(m.subprocess, 'Popen') as launch:
                launch.return_value.pid = 123
                backend.start({'type': 'file', 'title': 'Lesson', 'file': '/tmp/a.m4a'})
            args = launch.call_args.args[0]
            self.assertIn('--user-data-dir=' + str(backend.profile), args)
            self.assertEqual(args[-1], (Path(folder) / 'lesson.html').as_uri())
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(backend.group, 123)


if __name__ == '__main__':
    unittest.main()
