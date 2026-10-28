import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('pi_player', Path(__file__).resolve().parents[1] / 'scripts/pi_player.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
A, B, STOP, OFF = '000000000000aa', '000000000000bb', '00000000000001', '00000000000002'


def config():
    return {'cards': {A: {'type': 'file', 'title': 'Lesson', 'file': '/tmp/lesson.m4a'},
                      B: {'type': 'youtube', 'title': 'Playlist', 'url': 'https://music.youtube.com/watch?v=VIDEO_ID_11'},
                      STOP: {'type': 'stop', 'title': 'Stop'}, OFF: {'type': 'shutdown', 'title': 'Off'}},
            'audio_sink': 'bluez_output.test.1', 'speaker_address': '', 'volume_percent': 25}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.backend.available.return_value = True
        self.backend.ended.return_value = False
        self.clock = Mock(return_value=10)
        self.ctrl = m.Controller(config(), self.backend, self.clock)

    def test_switch_stops_before_start_and_unknown_keeps_playing(self):
        self.ctrl.scan(A)
        self.backend.reset_mock()
        self.ctrl.scan('unknown')
        self.backend.assert_not_called()
        self.assertEqual(self.backend.mock_calls, [])
        self.ctrl.scan(B)
        names = [c[0] for c in self.backend.mock_calls]
        self.assertLess(names.index('stop'), names.index('start'))
        self.assertEqual(self.ctrl.active, B)

    def test_missing_file_keeps_old_source(self):
        self.ctrl.scan(B)
        self.backend.reset_mock()
        self.backend.validate.side_effect = ValueError('missing')
        with self.assertRaises(ValueError):
            self.ctrl.scan(A)
        self.backend.stop.assert_not_called()
        self.assertEqual(self.ctrl.active, B)

    def test_repeat_debounce_then_restart(self):
        self.ctrl.scan(A)
        self.ctrl.scan(A)
        self.assertEqual(self.backend.start.call_count, 1)
        self.clock.return_value = 12
        self.ctrl.scan(A)
        self.assertEqual(self.backend.start.call_count, 2)

    def test_stop_cancels_pending_and_rescan_is_immediate(self):
        self.backend.available.return_value = False
        self.ctrl.scan(A)
        self.assertEqual(self.ctrl.pending, A)
        self.ctrl.scan(STOP)
        self.backend.available.return_value = True
        self.ctrl.tick()
        self.backend.start.assert_not_called()
        self.ctrl.scan(A)
        self.backend.start.assert_called_once()

    def test_speaker_loss_waits_and_restarts_latest_selection(self):
        self.ctrl.scan(A)
        self.backend.available.return_value = False
        self.ctrl.tick()
        self.assertIsNone(self.ctrl.active)
        self.assertEqual(self.ctrl.pending, A)
        self.ctrl.scan(B)
        self.backend.available.return_value = True
        self.clock.return_value = 16
        self.ctrl.tick()
        self.assertEqual(self.ctrl.active, B)

    def test_failed_launch_cleans_up_and_is_retryable(self):
        self.backend.start.side_effect = OSError('failed')
        with self.assertRaises(OSError):
            self.ctrl.scan(B)
        self.assertIsNone(self.ctrl.active)
        self.assertIsNone(self.ctrl.pending)
        self.assertIsNone(self.ctrl.last_id)
        self.backend.start.side_effect = None
        self.ctrl.scan(B)
        self.assertEqual(self.ctrl.active, B)

    def test_ended_player_does_not_relaunch_forever(self):
        self.ctrl.scan(B)
        self.backend.ended.return_value = True
        self.ctrl.tick()
        self.assertIsNone(self.ctrl.active)
        self.assertEqual(self.backend.start.call_count, 1)

    def test_shutdown_requires_two_scans_not_reader_duplicates(self):
        self.ctrl.scan(OFF)
        self.clock.return_value = 10.2
        self.ctrl.scan(OFF)
        self.backend.shutdown.assert_not_called()
        self.clock.return_value = 13
        self.ctrl.scan(OFF)
        self.backend.shutdown.assert_called_once()

    def test_shutdown_expires_and_other_scan_cancels(self):
        self.ctrl.scan(OFF)
        self.clock.return_value = 20
        self.ctrl.scan(OFF)
        self.backend.shutdown.assert_not_called()
        self.ctrl.scan('unknown')
        self.clock.return_value = 23
        self.ctrl.scan(OFF)
        self.backend.shutdown.assert_not_called()


class DecoderTests(unittest.TestCase):
    def feed_id(self, decoder, token, when=1):
        for char in token:
            decoder.feed('KEY_' + char.upper(), 1, when)
            decoder.feed('KEY_' + char.upper(), 0, when)
        return decoder.feed('KEY_ENTER', 1, when)

    def test_real_id_and_leading_zeros(self):
        self.assertEqual(self.feed_id(m.Decoder(), A), A)

    def test_repeats_ignored_and_bad_reports_rejected(self):
        d = m.Decoder()
        d.feed('KEY_X', 2, 1)
        self.assertEqual(self.feed_id(d, A), A)
        for bad in ('short', A + '0', 'x' + A, '0' * 1000):
            self.assertIsNone(self.feed_id(d, bad))
        self.assertEqual(self.feed_id(d, B), B)

    def test_timeout_cannot_combine_partial_cards(self):
        d = m.Decoder()
        for char in A[:7]:
            d.feed('KEY_' + char.upper(), 1, 1)
        self.assertIsNone(self.feed_id(d, A[7:], when=3))
        self.assertEqual(self.feed_id(d, A, when=4), A)


class ConfigurationTests(unittest.TestCase):
    def test_example_preserves_ids_and_builds_playlist_url(self):
        path = Path(__file__).resolve().parents[1] / 'cards.pi.example.json'
        loaded = m.load_config(path)
        self.assertIn(A, loaded['cards'])
        self.assertIn('&list=EXAMPLE_PLAYLIST_ID', loaded['cards'][B]['url'])

    def test_invalid_values_and_duplicate_normalized_ids(self):
        example = json.loads((Path(__file__).resolve().parents[1] / 'cards.pi.example.json').read_text())
        mutations = [lambda c: c.update(volume_percent=100), lambda c: c.update(volume_percent=True),
                     lambda c: c['cards'][B].update(playlist_id='; bad'),
                     lambda c: c['cards'][B].update(start_video_id='bad'),
                     lambda c: c['cards'].update({A.upper(): c['cards'][A]}),
                     lambda c: c['cards'][A].update(type='execute-shell')]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cards.json'
            for mutate in mutations:
                data = json.loads(json.dumps(example))
                mutate(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    m.load_config(path)


class BackendTests(unittest.TestCase):
    def test_simulation_has_no_subprocess_or_signal_effects(self):
        backend = m.Backend(config(), True)
        with patch.object(m.subprocess, 'Popen') as popen, patch.object(m.subprocess, 'run') as run, patch.object(m.os, 'killpg') as kill:
            backend.start(config()['cards'][A])
            backend.stop()
            backend.shutdown()
            self.assertTrue(backend.available())
            popen.assert_not_called()
            run.assert_not_called()
            kill.assert_not_called()

    def test_exact_sink_required_not_any_bluetooth_or_hdmi(self):
        backend = m.Backend(config())
        backend.run = Mock(return_value=Mock(stdout='1 alsa_output.hdmi module\n2 bluez_output.other.1 module\n'))
        self.assertFalse(backend.available())
        backend.run.return_value.stdout += '3 bluez_output.test.1 module\n'
        self.assertTrue(backend.available())

    def test_missing_configured_sink_fails_closed(self):
        data = config()
        data['audio_sink'] = ''
        with self.assertRaises(ValueError):
            m.Backend(data).available()

    def test_real_owned_process_terminated_without_touching_unrelated_process(self):
        backend = m.Backend(config())
        other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], start_new_session=True)
        backend.child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], start_new_session=True)
        backend.group = backend.child.pid
        child = backend.child
        try:
            try:
                backend.stop()
            except PermissionError:
                self.skipTest('Workspace sandbox denies process-group existence checks; verify on Pi')
            self.assertIsNotNone(child.poll())
            self.assertIsNone(other.poll())
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            other.terminate()
            other.wait()

    def test_reader_only_grabs_matching_keyboard_interface(self):
        keyboard, reader, extra = Mock(), Mock(), Mock()
        keyboard.info.vendor = 0x05ac
        for dev in (reader, extra):
            dev.info.vendor, dev.info.product, dev.name = 0xffff, 0x0035, 'SDZNKJLTD USB Reader'
        reader.capabilities.return_value = {1: [28]}
        extra.capabilities.return_value = {1: [42]}
        fake = Mock()
        fake.ecodes.EV_KEY, fake.ecodes.KEY_ENTER = 1, 28
        fake.list_devices.return_value = ['keyboard', 'reader', 'extra']
        fake.InputDevice.side_effect = [keyboard, reader, extra]
        with patch.dict(sys.modules, {'evdev': fake}):
            self.assertIs(m.open_reader(), reader)
        reader.grab.assert_called_once()
        keyboard.grab.assert_not_called()
        extra.grab.assert_not_called()
        keyboard.close.assert_called_once()
        extra.close.assert_called_once()

    def test_ambiguous_readers_are_not_grabbed(self):
        devices = [Mock(), Mock()]
        for dev in devices:
            dev.info.vendor, dev.info.product, dev.name = 0xffff, 0x0035, 'SDZNKJLTD USB Reader'
            dev.capabilities.return_value = {1: [28]}
        fake = Mock()
        fake.ecodes.EV_KEY, fake.ecodes.KEY_ENTER = 1, 28
        fake.list_devices.return_value = ['one', 'two']
        fake.InputDevice.side_effect = devices
        with patch.dict(sys.modules, {'evdev': fake}), self.assertRaises(OSError):
            m.open_reader()
        for dev in devices:
            dev.grab.assert_not_called()
            dev.close.assert_called_once()

class InstallTests(unittest.TestCase):
    def test_installer_creates_session_files_and_preserves_config_on_upgrade(self):
        installer_spec = importlib.util.spec_from_file_location('install_pi', Path(__file__).resolve().parents[1] / 'scripts/install_pi.py')
        installer = importlib.util.module_from_spec(installer_spec)
        installer_spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with patch.object(installer.sys, 'platform', 'linux'), patch.object(installer.os, 'geteuid', return_value=1000), patch.object(installer.Path, 'home', return_value=home), patch.object(installer.shutil, 'which', return_value='/usr/bin/tool'), patch.object(installer.subprocess, 'run') as run, patch.dict(sys.modules, {'evdev': Mock()}):
                installer.main()
                config_path = home / '.config/curio-player/cards.json'
                self.assertIn(A, json.loads(config_path.read_text())['cards'])
                config_path.write_text('{"preserve": "adult configuration"}')
                installer.main()
                self.assertEqual(json.loads(config_path.read_text()), {'preserve': 'adult configuration'})
                self.assertTrue((home / '.local/share/curio-player/pi_player.py').is_file())
                self.assertIn('session-start.sh', (home / '.config/autostart/curio-player.desktop').read_text())
                self.assertIn('KillMode=control-group', (home / '.config/systemd/user/curio-player.service').read_text())
                self.assertFalse(any('start' in call.args[0] for call in run.call_args_list))

    def test_cleanup_only_signals_owned_group_and_reaps_parent(self):
        backend = m.Backend(config())
        child = Mock()
        backend.child, backend.group = child, 123456
        with patch.object(m.os, 'killpg', side_effect=[None, ProcessLookupError()]) as kill:
            backend.stop()
        self.assertEqual(kill.call_args_list[0].args, (123456, signal.SIGTERM))
        child.wait.assert_called_once_with(timeout=2)
        self.assertIsNone(backend.group)


class ReplacementReaderTests(unittest.TestCase):
    def test_decimal_sample_matches_original_playlist(self):
        self.assertEqual(m.normalize_scan('0000000187'), B)
        self.assertEqual(m.normalize_scan(B), B)
        self.assertEqual(m.normalize_scan('0000000001'), '00000000000001')
        for bad in ('4294967296', '326521554', '00000001870', '-326521554', '32652155a0'):
            self.assertIsNone(m.normalize_scan(bad))

    def test_decimal_decoder_and_keypad(self):
        for prefix in ('KEY_', 'KEY_KP'):
            decoder = m.Decoder()
            for digit in '0000000187':
                decoder.feed(prefix + digit, 1, 1)
            self.assertEqual(decoder.feed('KEY_ENTER', 1, 1), B)

    def test_decimal_dispatches_existing_mapping(self):
        backend = Mock()
        backend.available.return_value = True
        controller = m.Controller(config(), backend)
        controller.scan('0000000187')
        self.assertEqual(controller.active, B)
        backend.start.assert_called_once_with(config()['cards'][B])

    def test_new_reader_keyboard_interface_is_selected(self):
        dev = Mock()
        dev.info.vendor, dev.info.product = 0xffff, 0x0035
        dev.name = 'ARM CM0 USB HID Keyboard'
        dev.capabilities.return_value = {1: [28]}
        fake = Mock()
        fake.ecodes.EV_KEY, fake.ecodes.KEY_ENTER = 1, 28
        fake.list_devices.return_value = ['replacement']
        fake.InputDevice.return_value = dev
        with patch.dict(sys.modules, {'evdev': fake}):
            self.assertIs(m.open_reader(), dev)
        dev.grab.assert_called_once()


class VolumeTests(unittest.TestCase):
    def test_launch_preserves_sink_volume_for_both_sources(self):
        backend = m.Backend(config())
        backend.run = Mock()
        with tempfile.TemporaryDirectory() as folder:
            backend.profile = Path(folder) / 'profile'
            with patch.object(m.subprocess, 'Popen') as launch, patch.object(m.shutil, 'which', return_value='/usr/bin/chromium'):
                for key in (A, B):
                    backend.start(config()['cards'][key])
                self.assertEqual(launch.call_count, 2)
                browser_calls = [c.args[0] for c in launch.call_args_list if c.args[0][0] == '/usr/bin/chromium']
                self.assertEqual(len(browser_calls), 1)
                self.assertNotIn('--password-store=basic', browser_calls[0])
        self.assertEqual([call.args[0] for call in backend.run.call_args_list],
                         [['pactl', 'set-default-sink', 'bluez_output.test.1']] * 2)


if __name__ == '__main__':
    unittest.main()
