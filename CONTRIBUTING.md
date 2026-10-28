# Contributing

Start with the [README](README.md) and [builder guides](docs/01-hardware.md). Useful contributions include a tested reader setup, clearer installation instructions, reproducible bug reports, and fixes for startup or audio recovery.

## Development checks

From the project directory on macOS or Linux with Python 3:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/pi_player.py --config cards.public.example.json --check
printf '00000000000001\n00000000000002\nquit\n' | python3 scripts/pi_player.py --config cards.public.example.json --simulate
```

The tests use mocks for hardware and browser behavior. Some process-lifecycle checks may fail in restricted sandboxes; report the exact failure instead of calling the suite green. Real Pi operation needs the dependencies and device permissions in the setup guide.

For a change, explain the problem, resulting behavior, checks run, and what remains physically unverified. Add focused regression coverage for behavior changes. Keep voice and Spotify work separate from the current local-audio/YouTube path.

## Hardware reports

Include Pi model, OS/kernel, reader-reported name and USB vendor/product, scan format, speaker model, setup step, expected behavior, actual observation, and relevant redacted logs. Do not post passwords, tokens, browser profiles, personal media, or account screenshots. Serial numbers and Bluetooth addresses can be redacted in public reports; retain them locally for your permission rule/config.

For a new reader, check multiple cards, window-focus independence, no ordinary keyboard capture, reconnects, 20 consecutive scans, and a cold boot. A model name or one successful scan is insufficient evidence of general compatibility.

## Content and licensing

Contribute code or documentation you have permission to share. Do not upload music, artwork, or third-party account data with a code change. Contributions are shared under the [MIT license](LICENSE).
