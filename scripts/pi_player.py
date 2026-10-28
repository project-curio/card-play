"""Pi card controller. Simulation needs only Python; real input uses python3-evdev."""
import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import urlencode

LOG = logging.getLogger('curio')
CARD = re.compile(r'[0-9a-f]{14}')
READER_NAMES = {'SDZNKJLTD USB Reader', 'ARM CM0 USB HID Keyboard'}


def normalize_scan(token):
    token = token.strip().lower()
    if CARD.fullmatch(token):
        return token
    if re.fullmatch(r'[0-9]{10}', token) and int(token) <= 0xffffffff:
        return format(int(token), '014x')
    return None


def load_config(path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get('cards'), dict) or not data['cards']:
        raise ValueError('Expected nonempty cards object')
    result = dict(data)
    result['cards'] = {}
    for raw, source in data['cards'].items():
        key = raw.strip().lower()
        if not CARD.fullmatch(key) or key in result['cards'] or not isinstance(source, dict):
            raise ValueError('Each card requires a unique 14-digit hex ID and object')
        card = dict(source)
        if not isinstance(card.get('title'), str) or not card['title'].strip():
            raise ValueError('Every card needs a title')
        kind = card.get('type')
        if kind in ('file', 'folder'):
            field = kind
            if not isinstance(card.get(field), str) or not card[field].strip():
                raise ValueError('Local cards need a file or folder path')
            media = Path(card[field]).expanduser()
            card[field] = str((path.parent / media).resolve())
        elif kind == 'youtube':
            for field, pattern in [('playlist_id', r'[A-Za-z0-9_-]{10,100}'), ('start_video_id', r'[A-Za-z0-9_-]{11}')]:
                if not isinstance(card.get(field), str) or not re.fullmatch(pattern, card[field]):
                    raise ValueError('Invalid YouTube ' + field)
            card['url'] = 'https://music.youtube.com/watch?' + urlencode({'v': card['start_video_id'], 'list': card['playlist_id']})
        elif kind not in ('stop', 'shutdown'):
            raise ValueError('Card type must be file, folder, youtube, stop, or shutdown')
        result['cards'][key] = card
    volume = data.get('volume_percent', 25)
    if type(volume) is not int or not 1 <= volume <= 60:
        raise ValueError('volume_percent must be an integer from 1 to 60')
    result['volume_percent'] = volume
    sink = data.get('audio_sink', '')
    if not isinstance(sink, str) or (sink and not re.fullmatch(r'[A-Za-z0-9_.:-]+', sink)):
        raise ValueError('audio_sink must be an exact pactl sink name')
    address = data.get('speaker_address', '')
    if not isinstance(address, str) or (address and not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', address)):
        raise ValueError('speaker_address must be a Bluetooth MAC address or empty')
    result['audio_sink'], result['speaker_address'] = sink, address
    return result


AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.aac', '.flac', '.ogg', '.opus'}

def local_tracks(card):
    if card.get('type', 'file') == 'file':
        return [Path(card['file'])]
    folder = Path(card['folder'])
    if not folder.is_dir():
        raise ValueError('Lesson folder is missing: ' + str(folder))
    def order(path):
        return [int(part) if part.isdigit() else part.casefold()
                for part in re.split(r'(\d+)', path.name)]
    tracks = sorted((p for p in folder.iterdir() if not p.name.startswith('.')
                     and p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS), key=order)
    if not tracks:
        raise ValueError('No supported audio files in lesson folder: ' + str(folder))
    return tracks


def validate_local(card):
    tracks = local_tracks(card)
    for track in tracks:
        if not track.is_file() or not os.access(track, os.R_OK):
            raise ValueError('Lesson file is missing or unreadable: ' + str(track))
    card['_tracks'] = [str(track) for track in tracks]



class Decoder:
    """Ignore key-up/repeat; discard malformed, overlong and stale reports."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.text, self.invalid, self.last = '', False, 0

    def feed(self, key, value, now):
        if value != 1:
            return None
        if now - self.last > 1:
            self.reset()
        self.last = now
        if key in ('KEY_ENTER', 'KEY_KPENTER'):
            token = normalize_scan(self.text) if not self.invalid else None
            self.reset()
            return token
        char = key.removeprefix('KEY_').removeprefix('KP').lower()
        if len(char) == 1 and char in '0123456789abcdef' and len(self.text) < 14:
            self.text += char
        elif key not in ('KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT'):
            self.invalid = True
        return None


class Backend:
    """Own one isolated process group. Never touch the user's normal browser."""
    def __init__(self, config, dry_run=False):
        self.config, self.dry_run = config, dry_run
        self.child = None
        self.group = None
        self.next_connect = 0
        self.profile = Path.home() / '.local/share/curio-player/browser-profile'

    def run(self, args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=8)

    def validate(self, card):
        if self.dry_run:
            return
        if card['type'] in ('file', 'folder'):
            validate_local(card)
            if not shutil.which('cvlc'):
                raise ValueError('Install VLC first')
        elif card['type'] == 'youtube':
            if not (shutil.which('chromium') or shutil.which('chromium-browser')):
                raise ValueError('Install Chromium first')
            if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
                raise ValueError('YouTube requires the desktop session')

    def available(self):
        if self.dry_run:
            return True
        sink = self.config['audio_sink']
        if not sink:
            raise ValueError('Configure audio_sink before real playback')
        names = [line.split()[1] for line in self.run(['pactl', 'list', 'short', 'sinks']).stdout.splitlines() if len(line.split()) >= 2]
        if sink in names:
            return True
        address = self.config['speaker_address']
        if address and time.monotonic() >= self.next_connect:
            self.next_connect = time.monotonic() + 20
            try:
                self.run(['bluetoothctl', 'connect', address])
            except (OSError, subprocess.SubprocessError):
                LOG.warning('Speaker reconnect not ready; will retry')
        return False

    def start(self, card):
        if self.dry_run:
            LOG.info('SIMULATED start %s: %s', card['type'], card['title'])
            return
        sink = self.config['audio_sink']
        self.run(['pactl', 'set-default-sink', sink])
        # Preserve the user's current sink volume across card changes/reconnects.
        # Legacy volume_percent config is accepted but no longer applied here.
        env = dict(os.environ, PULSE_SINK=sink)
        if card['type'] in ('file', 'folder'):
            args = ['cvlc', '--no-one-instance', '--intf=dummy', '--extraintf=dbus', '--no-video', '--play-and-exit', '--aout=pulse', '--'] + card.get('_tracks', [str(p) for p in local_tracks(card)])
        else:
            self.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
            args = [shutil.which('chromium') or shutil.which('chromium-browser'),
                    '--user-data-dir=' + str(self.profile), '--no-first-run',
                    '--no-default-browser-check', '--disable-background-mode',
                    '--autoplay-policy=no-user-gesture-required', '--new-window', card['url']]
        self.child = subprocess.Popen(args, env=env, start_new_session=True)
        self.group = self.child.pid
        LOG.info('Launched %s; audible playback is not confirmed', card['title'])

    def stop(self):
        if self.dry_run:
            LOG.info('SIMULATED stop')
            return
        if self.group is None:
            return
        # Children inherit this group. Terminate them even if their parent exited.
        try:
            os.killpg(self.group, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if self.child:
                self.child.poll()  # reap parent, including its zombie
            try:
                os.killpg(self.group, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            try:
                os.killpg(self.group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.child:
            self.child.wait(timeout=2)
        self.child, self.group = None, None

    def shutdown(self):
        if self.dry_run:
            LOG.info('SIMULATED clean shutdown')
        else:
            self.run(['systemctl', 'poweroff'])

    def ended(self):
        return not self.dry_run and self.child is not None and self.child.poll() is not None


class Controller:
    def __init__(self, config, backend, clock=time.monotonic):
        self.cards, self.backend, self.clock = config['cards'], backend, clock
        self.active = self.pending = None
        self.last_id, self.last_time = None, -100
        self.next_retry = 0
        self.shutdown_arm = None

    def stop(self):
        self.backend.stop()
        self.active = self.pending = None
        self.last_id = None
        self.shutdown_arm = None

    def scan(self, token):
        token = normalize_scan(token) or token.strip().lower()
        card = self.cards.get(token)
        now = self.clock()
        if card and card['type'] == 'shutdown':
            if self.shutdown_arm and self.shutdown_arm[0] == token and 2 <= now - self.shutdown_arm[1] <= 8:
                self.stop()
                self.backend.shutdown()
            elif not self.shutdown_arm or self.shutdown_arm[0] != token or now - self.shutdown_arm[1] > 8:
                self.shutdown_arm = (token, now)
                LOG.warning('Shutdown armed: scan same card again in 2 to 8 seconds')
            return
        self.shutdown_arm = None
        if card is None:
            LOG.warning('Unknown card %s; current playback unchanged', token)
            return
        if card['type'] == 'stop':
            self.stop()
            return
        now = self.clock()
        if token == self.last_id and now - self.last_time < 1.5:
            return
        self.backend.validate(card)  # Missing files never interrupt the old source.
        ready = self.backend.available()
        self.backend.stop()  # No new source until previous one is stopped.
        self.active = None
        self.pending = token
        self.last_id, self.last_time = token, now
        if ready:
            self._start_pending()
        else:
            LOG.warning('Waiting for configured speaker; selection queued')

    def _start_pending(self):
        token = self.pending
        try:
            self.backend.validate(self.cards[token])
            self.backend.start(self.cards[token])
        except Exception:
            self.backend.stop()
            self.pending = None  # Failed launch requires explicit rescan, no restart storm.
            self.last_id = None
            raise
        self.active, self.pending = token, None

    def tick(self):
        if self.active and self.backend.ended():
            LOG.info('Player exited; scan to start again')
            self.stop()
        now = self.clock()
        if now < self.next_retry:
            return
        self.next_retry = now + 5
        if self.active or self.pending:
            ready = self.backend.available()
            if self.active and not ready:
                self.backend.stop()
                self.pending, self.active = self.active, None
                LOG.warning('Speaker lost; stopped player, waiting to restart selection')
            if self.pending and ready:
                self._start_pending()


def open_reader():
    from evdev import InputDevice, list_devices, ecodes
    matches = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            continue  # A device may disappear during enumeration.
        if (dev.info.vendor == 0xffff and dev.info.product == 0x0035
                and dev.name in READER_NAMES
                and ecodes.KEY_ENTER in dev.capabilities().get(ecodes.EV_KEY, [])):
            matches.append(dev)
        else:
            dev.close()
    if len(matches) != 1:
        for dev in matches:
            dev.close()
        raise OSError('Expected exactly one matching reader keyboard interface; found ' + str(len(matches)))
    dev = matches[0]
    try:
        dev.grab()
    except Exception:
        dev.close()
        raise
    return dev


def listen(controller, enroll=False):
    from evdev import ecodes
    device, decoder, retry = None, Decoder(), 0
    try:
        while True:
            if device is None and time.monotonic() >= retry:
                retry = time.monotonic() + 5
                try:
                    device = open_reader()
                    decoder.reset()
                    LOG.info('Reader grabbed: %s; focus independent', device.path)
                except OSError as error:
                    LOG.warning('Reader unavailable: %s', error)
            if device is not None:
                try:
                    ready, _, _ = select.select([device.fd], [], [], 0.2)
                    if ready:
                        for event in device.read():
                            if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_DROPPED:
                                raise OSError('Input events lost; discard scan and reopen reader')
                            if event.type == ecodes.EV_KEY:
                                key = ecodes.KEY.get(event.code, '')
                                if isinstance(key, list):
                                    key = key[0]
                                token = decoder.feed(key, event.value, time.monotonic())
                                if token:
                                    if enroll:
                                        print(token, flush=True)
                                    else:
                                        try:
                                            controller.scan(token)
                                        except (ValueError, OSError, subprocess.SubprocessError) as error:
                                            LOG.error('Card failed: %s', error)
                except OSError as error:
                    LOG.warning('Reader disconnected: %s; stopping playback', error)
                    controller.stop()
                    device.close()
                    device = None
                    decoder.reset()
            else:
                time.sleep(0.2)
            if not enroll:
                try:
                    controller.tick()
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    LOG.error('Audio recovery failed: %s', error)
                    controller.stop()
    finally:
        if device is not None:
            device.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path.home() / '.config/curio-player/cards.json')
    parser.add_argument('--simulate', action='store_true', help='stdin cards, no devices or playback')
    parser.add_argument('--check', action='store_true', help='validate configuration only')
    parser.add_argument('--enroll', action='store_true', help='print reader IDs, no playback')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        config = load_config(args.config.resolve())
        if args.check:
            print('Configuration valid; ' + str(len(config['cards'])) + ' cards. No hardware checked.')
            return 0
        if not args.simulate and sys.platform != 'linux':
            raise ValueError('Real player requires Linux; use --simulate on Mac')
        backend = Backend(config, args.simulate or args.enroll)
        controller = Controller(config, backend)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        # Keep lock file open for process lifetime. No two controllers own playback.
        lock_path = Path.home() / '.local/share/curio-player/controller.lock'
        if not args.simulate:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = lock_path.open('w')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if args.simulate:
                for line in sys.stdin:
                    token = line.strip()
                    if token == 'quit':
                        break
                    if token == 'stop':
                        controller.stop()
                    else:
                        controller.scan(token)
            else:
                listen(controller, args.enroll)
        finally:
            controller.stop()
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, ImportError, subprocess.SubprocessError) as error:
        LOG.error('%s', error)
        return 1


if __name__ == '__main__':
    sys.exit(main())
