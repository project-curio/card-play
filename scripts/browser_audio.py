"""Prepare browser-compatible copies of GSM WAV lessons; never edit originals."""
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import wave


def is_gsm_wav(path):
    with path.open('rb') as audio:
        header = audio.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WAVE':
            return False
        while True:
            chunk = audio.read(8)
            if len(chunk) != 8:
                return False
            tag, size = struct.unpack('<4sI', chunk)
            if tag == b'fmt ':
                encoding = audio.read(2)
                return size >= 2 and len(encoding) == 2 and struct.unpack('<H', encoding)[0] == 0x31
            audio.seek(size + size % 2, 1)


def prepare_track(path, cache):
    path = Path(path)
    if path.suffix.lower() != '.wav' or not is_gsm_wav(path):
        return path
    stamp = path.stat()
    key = hashlib.sha256(f'{path.resolve()}:{stamp.st_size}:{stamp.st_mtime_ns}'.encode()).hexdigest()[:24]
    target = cache / key / path.name
    if target.is_file():
        return target
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('These lessons use GSM WAV audio. Run brew install ffmpeg in Mac Terminal, then restart this script.')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        output = Path(staging) / 'converted.wav'
        subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', str(path),
                        '-map', '0:a:0', '-c:a', 'pcm_s16le', str(output)],
                       check=True, capture_output=True, text=True, timeout=120)
        with wave.open(str(output)) as audio:
            if audio.getsampwidth() != 2 or audio.getnframes() <= 0:
                raise ValueError('Converted lesson did not contain valid PCM audio')
        output.replace(target)
    return target
