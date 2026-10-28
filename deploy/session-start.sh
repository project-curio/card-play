#!/bin/sh
# Run by XDG desktop autostart, not SSH or a system boot service.
set -eu
for name in DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS; do
    if printenv "$name" >/dev/null 2>&1; then
        systemctl --user import-environment "$name"
    else
        systemctl --user unset-environment "$name"
    fi
done
systemctl --user restart curio-player.service
