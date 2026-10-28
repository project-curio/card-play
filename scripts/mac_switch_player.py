"""Unified Mac card test: local lesson and YouTube in an owned Chrome profile."""
import argparse
import fcntl
import html
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys

from browser_audio import prepare_track
from pi_player import Backend, Controller, load_config, local_tracks, validate_local

CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')


def lesson_page(card):
    # A local file page can load a local media file without exposing a web server.
    title = html.escape(card['title'])
    tracks = [Path(p) for p in card.get('_prepared_tracks', card.get('_tracks', []))] or local_tracks(card)
    settings = json.dumps({'tracks': [{'title': p.stem, 'url': p.as_uri()} for p in tracks]}).replace('<', '\\u003c')
    return '''<!doctype html><meta charset="utf-8"><title>Curio lesson</title>
<style>body{font:20px system-ui;max-width:700px;margin:80px auto;padding:24px}audio{width:100%}</style>
<h1>''' + title + '''</h1><p id="track"></p><audio id="lesson" controls></audio>
<p id="status">Loading lesson…</p><p>Use the speaker's Play/Pause button. Click back into Terminal before scanning another card.</p>
<script>
const settings = ''' + settings + ''';
const audio = document.getElementById('lesson');
const status = document.getElementById('status');
let index = 0;
audio.volume = 0.25;
function showError(error) {
  status.textContent = error && error.name === 'NotAllowedError'
    ? 'Click Play once to allow playback.'
    : 'This lesson could not be decoded or opened. Restart the updated script; GSM WAV lessons need FFmpeg conversion.';
}
function play() { return audio.play().catch(showError); }
function state(value) {
  status.textContent = value === 'playing' ? 'Playing' : value === 'paused' ? 'Paused' : 'Finished';
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = value;
}
audio.addEventListener('play', () => state('playing'));
audio.addEventListener('pause', () => { if (audio.error) showError(audio.error); else if (!audio.ended) state('paused'); });
function selectTrack(next) {
  index = next;
  const track = settings.tracks[index];
  audio.src = track.url;
  audio.currentTime = 0;
  document.getElementById('track').textContent = `${index + 1} / ${settings.tracks.length} — ${track.title}`;
  if ('mediaSession' in navigator) navigator.mediaSession.metadata = new MediaMetadata({title: track.title, artist: 'Curio lessons'});
  play();
}
function nextTrack() {
  if (index + 1 < settings.tracks.length) selectTrack(index + 1);
}
function previousTrack() { selectTrack(Math.max(0, index - 1)); }
audio.addEventListener('ended', () => {
  if (index + 1 < settings.tracks.length) nextTrack();
  else state('none');
});
audio.addEventListener('error', () => showError(audio.error));
if ('mediaSession' in navigator) {
  navigator.mediaSession.setActionHandler('play', play);
  navigator.mediaSession.setActionHandler('pause', () => audio.pause());
  navigator.mediaSession.setActionHandler('nexttrack', nextTrack);
  navigator.mediaSession.setActionHandler('previoustrack', previousTrack);
  navigator.mediaSession.setActionHandler('stop', () => { audio.pause(); audio.currentTime = 0; });
}
selectTrack(0);
</script>'''


class MacBackend(Backend):
    def __init__(self, config, dry_run=False):
        super().__init__(config, dry_run)
        self.runtime = Path.home() / 'Library/Application Support/CurioMusicPlayer'
        self.profile = self.runtime / 'ChromeProfile'

    def validate(self, card):
        if card['type'] not in ('file', 'folder', 'youtube'):
            raise ValueError('This Mac test supports only lesson, playlist and Stop')
        if card['type'] in ('file', 'folder'):
            validate_local(card)
            if not self.dry_run:
                card['_prepared_tracks'] = [str(prepare_track(Path(p), self.runtime / 'PreparedAudio')) for p in card['_tracks']]
        if not self.dry_run and not CHROME.is_file():
            raise ValueError('Google Chrome is required in /Applications')

    def available(self):
        return True  # Mac output selection stays with the user, no Pi Bluetooth commands.

    def start(self, card):
        if self.dry_run:
            logging.info('DRY RUN: switch to %s (%s)', card['title'], card['type'])
            return
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.profile.mkdir(exist_ok=True, mode=0o700)
        if card['type'] in ('file', 'folder'):
            page = self.runtime / 'lesson.html'
            page.write_text(lesson_page(card))
            url = page.as_uri()
        else:
            url = card['url']
        args = [str(CHROME), '--user-data-dir=' + str(self.profile),
                '--no-first-run', '--no-default-browser-check', '--disable-background-mode',
                '--autoplay-policy=no-user-gesture-required', '--new-window', url]
        self.child = subprocess.Popen(args, start_new_session=True)
        self.group = self.child.pid
        print('Opened ' + card['title'] + '. Click back into this Terminal BEFORE another scan.', flush=True)

    def stop(self):
        # macOS process-group probes can return EPERM. Wait on our owned
        # browser process instead; never signal unrelated Chrome processes.
        if self.dry_run or self.child is None:
            return
        try:
            if self.child.poll() is None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=3)
        except (OSError, subprocess.SubprocessError) as error:
            # Retain ownership and block the next launch if cleanup failed.
            raise RuntimeError('Cannot close the player Chrome window: ' + str(error) +
                               '. Close that player window manually, then rescan.') from error
        self.child, self.group = None, None

    def shutdown(self):
        raise ValueError('Mac shutdown is intentionally unsupported in this playback test')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'cards.mac.example.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    controller = None
    try:
        config = load_config(args.config.resolve())
        if any(c['type'] == 'shutdown' for c in config['cards'].values()):
            raise ValueError('Shutdown cards are not supported by this Mac test')
        if sys.platform != 'darwin' and not args.dry_run:
            raise ValueError('Use this script on Mac, or pass --dry-run')
        backend = MacBackend(config, args.dry_run)
        if not args.dry_run:
            backend.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock = (backend.runtime / 'controller.lock').open('w')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        controller = Controller(config, backend)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        print('Ready. Focus this Terminal and scan either card. Type stop or quit + Enter.', flush=True)
        print('Uses a separate Chrome profile; YouTube may need a first-time sign-in.', flush=True)
        for line in sys.stdin:
            token = line.strip().lower()
            if token == 'quit':
                break
            try:
                if token == 'stop':
                    controller.stop()
                else:
                    controller.scan(token)
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                print('Could not switch: ' + str(error), flush=True)
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if controller is not None:
            try:
                controller.stop()
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                print(str(error), file=sys.stderr)


if __name__ == '__main__':
    sys.exit(main())
