"""Install user-owned runtime/autostart files on the Pi; preserve existing config."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    if sys.platform != 'linux' or os.geteuid() == 0:
        sys.exit('Run as the normal desktop user on the Pi, not with sudo.')
    missing = [name for name in ('cvlc', 'pactl', 'bluetoothctl', 'systemctl') if not shutil.which(name)]
    if not (shutil.which('chromium') or shutil.which('chromium-browser')):
        missing.append('chromium')
    try:
        import evdev  # noqa: F401
    except ImportError:
        missing.append('python3-evdev')
    if missing:
        sys.exit('Install dependencies first: ' + ', '.join(missing))
    root = Path(__file__).resolve().parents[1]
    home = Path.home()
    runtime = home / '.local/share/curio-player'
    config = home / '.config/curio-player'
    units = home / '.config/systemd/user'
    autostart = home / '.config/autostart'
    for folder in (runtime, config, units, autostart):
        folder.mkdir(parents=True, exist_ok=True)
    # Stop existing runtime before upgrading code. Missing unit is normal initially.
    subprocess.run(['systemctl', '--user', 'stop', 'curio-player.service'], check=False)
    shutil.copy2(root / 'scripts/pi_player.py', runtime / 'pi_player.py')
    shutil.copy2(root / 'deploy/session-start.sh', runtime / 'session-start.sh')
    (runtime / 'session-start.sh').chmod(0o700)
    shutil.copy2(root / 'deploy/curio-player.service', units / 'curio-player.service')
    if not (config / 'cards.json').exists():
        shutil.copy2(root / 'cards.pi.example.json', config / 'cards.json')
        (config / 'cards.json').chmod(0o600)
    # Desktop Entry Exec uses its own escaping (not shell interpolation).
    entry_path = str(runtime / 'session-start.sh')
    escaped = entry_path.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    (autostart / 'curio-player.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=Card Tap\n'
        'Exec="' + escaped + '"\nTerminal=false\n')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    print('Installed. Existing cards.json preserved. Not started; finish docs/02-pi-setup.md.')
    print('Runtime:', runtime)
    print('Configuration:', config / 'cards.json')


if __name__ == '__main__':
    main()
