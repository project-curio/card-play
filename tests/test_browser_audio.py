import struct
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import browser_audio as m


def gsm(path):
    path.write_bytes(b'RIFF' + struct.pack('<I', 30) + b'WAVE' + b'JUNK' + struct.pack('<I', 1) + b'x\0' + b'fmt ' + struct.pack('<I', 2) + struct.pack('<H', 0x31))


class BrowserAudioTests(unittest.TestCase):
    def test_detects_gsm_with_padding_and_leaves_normal_media(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lesson.wav'
            gsm(source)
            self.assertTrue(m.is_gsm_wav(source))
            other = Path(folder) / 'lesson.m4a'
            other.write_bytes(b'example')
            self.assertEqual(m.prepare_track(other, Path(folder) / 'cache'), other)

    def test_missing_converter_is_actionable_and_original_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lesson.wav'
            gsm(source)
            original = source.read_bytes()
            with patch.object(m.shutil, 'which', return_value=None), self.assertRaisesRegex(ValueError, 'brew install ffmpeg'):
                m.prepare_track(source, Path(folder) / 'cache')
            self.assertEqual(source.read_bytes(), original)

    def test_conversion_validated_cached_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lesson.wav'
            gsm(source)
            original = source.read_bytes()
            def convert(args, **kwargs):
                with wave.open(args[-1], 'wb') as audio:
                    audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                    audio.writeframes(b'\0\0' * 320)
            with patch.object(m.shutil, 'which', return_value='/example/ffmpeg'), patch.object(m.subprocess, 'run', side_effect=convert) as run:
                output = m.prepare_track(source, Path(folder) / 'cache')
                self.assertEqual(m.prepare_track(source, Path(folder) / 'cache'), output)
                run.assert_called_once()
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(output.name, source.name)
            self.assertFalse(m.is_gsm_wav(output))

    def test_invalid_conversion_is_not_published(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lesson.wav'
            gsm(source)
            cache = Path(folder) / 'cache'
            with patch.object(m.shutil, 'which', return_value='/example/ffmpeg'), patch.object(m.subprocess, 'run'), self.assertRaises(FileNotFoundError):
                m.prepare_track(source, cache)
            self.assertEqual(list(cache.rglob('*.wav')), [])
