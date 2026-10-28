# 4. Use, maintain, and troubleshoot

[Cards and content](03-cards-and-content.md) · [README](../README.md)

## 1. Start a listening session

1. Power on the speaker and Pi.
2. Wait for the desktop session and player to start. During setup, run `~/.local/share/curio-player/session-start.sh` from the desktop terminal.
3. Unlock the desktop keyring and sign in to YouTube Music if requested.
4. Scan a card. Use a Stop card to end playback. Test the speaker's media buttons with each source before depending on them.

The player retries the configured, already-paired Bluetooth speaker. If the speaker disappears, it stops and queues the current selection; after recovery it starts from the beginning. Stop cancels the pending selection. Disconnecting the reader stops playback; reconnect it and scan again. A player process that exits needs a rescan.

## 2. Configure startup and test it

The installer creates `~/.config/autostart/curio-player.desktop` and `~/.config/systemd/user/curio-player.service`.

1. Run `sudo raspi-config`, find the boot/autologin options, and choose desktop autologin for the dedicated player user. Menu labels depend on the OS version.
2. Reboot with the monitor connected. Check `systemctl --user status curio-player.service` in the desktop terminal.
3. Test local and streaming cards. A locked keyring after autologin can still require adult intervention. SSH login alone does not unlock it. Keep keyring protection; do not delete the keyring or set a blank password as a routine setup step.
4. Shut down cleanly, remove the monitor/keyboard, and try a cold boot. Repeat three times, including a speaker power cycle.

If a graphical session does not start without HDMI, displayless setup is still unresolved for your device. A system service or systemd lingering does not create the desktop session Chromium needs. Keep the monitor available until this works. The included `scripts/unlock_pi_keyring.py` uses a version-specific GNOME internal API. Its corrected flow is user-confirmed on the original Pi, but not universal. For the same `Default Keyring` collection, install `python3-dbus` and run `python3 ~/curio-player-source/scripts/unlock_pi_keyring.py` as the desktop user over SSH. It privately prompts for the existing keyring password; do not use sudo. Restart the service and scan again if Chromium was blocked. A different collection or missing internal API requires diagnosis. This remains a manual step after reboot; verify playback after disconnecting SSH.

## 3. Record acceptance results

| Check | Pass means |
| --- | --- |
| Reader | 20 scans with no USB controller failure; scans while Chromium is focused do not type into the page. |
| Content | Every card selects the intended content; folder order and playlist first track are correct. |
| Switching | Local → YouTube → local leaves only one audible source. |
| Controls | Stop works; Play/Pause and Next/Previous work where there are multiple tracks. |
| Sound | At least 15 minutes each of local and streaming audio without interruptions. |
| Recovery | Reader reconnect, speaker power cycle, unavailable content, and network restoration recover as documented. |
| Offline | With networking disconnected, a local card still plays. Do not count YouTube as an offline source. |
| Shutdown | Double scan requests clean shutdown; unplug only after shutdown finishes. |
| Boot | Three cold boots without monitor/keyboard, including keyring/account checks, need no manual command. |

Record your Pi, OS/kernel, reader name/IDs, speaker, observations, and failures. Automated tests do not replace these checks.

## 4. Troubleshoot one layer at a time

| Symptom | Check and next step |
| --- | --- |
| No sound | Play the file in VLC manually; inspect `pactl info` and `pactl list short sinks`; compare the exact sink name with config. Check both volume controls. |
| Waiting for speaker | Pair/connect it in the desktop, confirm its address and trusted status, then rescan. |
| No matching reader | Check `/proc/bus/input/devices`, source name/vendor/product matching, serial-specific udev rule, replug, and active desktop login. Do not run the player as root. |
| More than one matching interface | Disconnect extra readers; investigate the actual event interfaces before narrowing `open_reader()`. |
| IDs type into a page | Service may not be running or grabbing the correct reader. Inspect logs and permissions. |
| Unknown card | Enroll again; copy the normalized ID exactly into config and restart. |
| Config valid, file will not play | `--check` does not inspect files. Confirm path, readable file, folder contents, and VLC decoding. |
| Browser opens but is silent | Check login, keyring prompt, availability, autoplay, and the audio output in that dedicated window. |
| USB devices vanish | Inspect kernel logs. Stop testing the player until hardware input is stable; the original hub workaround failed. |
| Service repeatedly crashes | Read logs, fix the reported cause, run `systemctl --user reset-failed curio-player.service`, then the desktop session launcher. |
| Choppy sound | Compare local audio alone, streaming alone, and local audio with a browser open. Check power/throttling and audio logs before changing several settings. |

Useful diagnostics:

```sh
systemctl --user status curio-player.service
journalctl --user -u curio-player.service -b -n 100 --no-pager
journalctl --user -u pipewire -u pipewire-pulse -u wireplumber -b -n 100 --no-pager
sudo journalctl -k -b -n 100 --no-pager
vcgencmd get_throttled
```

Review logs before sharing: redact account details, personal paths, addresses, and any credentials. Include the exact error and what you actually heard or saw.

## 5. Update and back up

1. Stop the service: `systemctl --user stop curio-player.service`.
2. Back up `~/.config/curio-player/cards.json`, your local reader rule, any source adaptations, and original audio to private storage. Keep the browser profile private; it is not a portable music backup.
3. Obtain the new source. Compare and reapply reader adaptations; source updates can replace them.
4. In the source directory, run `python3 -m unittest discover -s tests -v`, then `python3 scripts/install_pi.py`. Existing runtime config is preserved.
5. If your reader rule changed, reinstall it using the setup guide and replug the reader.
6. Run `--check` and the desktop session launcher again. Re-test cards and reboot behavior.

## 6. Disable or uninstall

To stop now and prevent future desktop startup:

```sh
systemctl --user stop curio-player.service
rm ~/.config/autostart/curio-player.desktop
```

To remove the installed program afterward:

```sh
rm ~/.config/systemd/user/curio-player.service
systemctl --user daemon-reload
sudo rm /etc/udev/rules.d/70-curio-reader.rules
sudo udevadm control --reload-rules
```

After making backups, use the file manager to delete `~/.local/share/curio-player` if desired; this also deletes the dedicated browser login/profile. Configuration is separately stored in `~/.config/curio-player`. Your original music files are not removed by these instructions. Replug the reader after removing its permission rule.
