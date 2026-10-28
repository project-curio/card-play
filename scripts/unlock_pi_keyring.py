#!/usr/bin/env python3
"""Unlock the observed Pi keyring using GNOME's internal, version-specific API.

Run as the desktop user over SSH, never sudo. No password is saved or passed
as a process argument. Requires the OS python3-dbus package.
"""
import getpass
import os
import re
import sys
import warnings


STEP = 'startup'


def error_summary(error):
    # Exception messages/arguments can contain secrets; report identifiers only.
    kind = type(error).__name__
    get_name = getattr(error, 'get_dbus_name', None)
    if callable(get_name):
        name = get_name()
        if isinstance(name, str) and re.fullmatch(r'(?:org\.freedesktop\.|org\.gnome\.)[A-Za-z0-9_.]+', name):
            kind = name
    return f'Failed at {STEP}: {kind}. No password was saved.'


def main():
    global STEP

    if sys.platform != 'linux' or os.geteuid() == 0:
        raise SystemExit('Run on the Pi as the desktop user, without sudo.')
    try:
        import dbus
    except ImportError:
        raise SystemExit('Install the dependency: sudo apt install python3-dbus')
    os.environ['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{os.getuid()}/bus'
    STEP = 'connect to desktop bus'
    bus = dbus.SessionBus()
    name = 'org.freedesktop.secrets'
    root = bus.get_object(name, '/org/freedesktop/secrets')
    path = '/org/freedesktop/secrets/collection/Default_5fKeyring'
    collection = bus.get_object(name, path)
    props = dbus.Interface(collection, 'org.freedesktop.DBus.Properties')
    def locked():
        return bool(props.Get('org.freedesktop.Secret.Collection', 'Locked'))
    STEP = 'read Default Keyring lock state'
    if not locked():
        print('Default Keyring is already unlocked.')
        return
    interface = 'org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface'
    STEP = 'inspect unlock method'
    xml = dbus.Interface(root, 'org.freedesktop.DBus.Introspectable').Introspect()
    if interface not in xml or 'UnlockWithMasterPassword' not in xml:
        raise SystemExit('This GNOME version does not expose the required unlock method; nothing changed.')
    service = dbus.Interface(root, 'org.freedesktop.Secret.Service')
    STEP = 'open keyring protocol session'
    _, session = service.OpenSession('plain', dbus.String('', variant_level=1))
    try:
        # Fail rather than fall back to an echoed password if no terminal exists.
        STEP = 'read hidden password'
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Default Keyring password: ')
        if not password:
            raise SystemExit('Empty password refused; nothing changed.')
        STEP = 'prepare unlock request'
        secret = dbus.Struct((dbus.ObjectPath(session), dbus.ByteArray(b''),
                              dbus.ByteArray(password.encode('utf-8')),
                              'text/plain; charset=utf-8'), signature='oayays')
        del password
        try:
            STEP = 'unlock Default Keyring'
            dbus.Interface(root, interface).UnlockWithMasterPassword(path, secret)
        finally:
            del secret
        STEP = 'verify Default Keyring is unlocked'
        if locked():
            raise SystemExit('Default Keyring is still locked.')
        print('Default Keyring unlocked. Restart the player and scan a playlist.')
    finally:
        # Cleanup must not hide the original unlock error.
        try:
            dbus.Interface(bus.get_object(name, session), 'org.freedesktop.Secret.Session').Close()
        except Exception:
            print('Protocol session cleanup failed; this does not determine the keyring lock state.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(error_summary(error)) from None
