import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('unlock_pi_keyring', Path(__file__).resolve().parents[1] / 'scripts/unlock_pi_keyring.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class UnlockTests(unittest.TestCase):
    def test_protocol_interfaces_unlock_and_close(self):
        props = Mock()
        props.Get.side_effect = [True, False]
        introspection = Mock()
        internal_name = 'org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface'
        introspection.Introspect.return_value = internal_name + ' UnlockWithMasterPassword'
        service, session, internal = Mock(), Mock(), Mock()
        session_path = '/org/freedesktop/secrets/session/test'
        service.OpenSession.return_value = ('', session_path)
        interfaces = {
            'org.freedesktop.DBus.Properties': props,
            'org.freedesktop.DBus.Introspectable': introspection,
            'org.freedesktop.Secret.Service': service,
            'org.freedesktop.Secret.Session': session,
            internal_name: internal,
        }
        bus = Mock()
        dbus = SimpleNamespace(
            SessionBus=lambda: bus,
            Interface=lambda obj, name: interfaces[name],
            String=lambda value, **kw: value,
            ObjectPath=lambda value: value,
            ByteArray=bytes,
            Struct=lambda value, **kw: value,
        )
        output = io.StringIO()
        with patch.dict('sys.modules', {'dbus': dbus}), patch.object(m.sys, 'platform', 'linux'), \
                patch.object(m.os, 'geteuid', return_value=1000), \
                patch.object(m.getpass, 'getpass', return_value='test-only-password'), \
                contextlib.redirect_stdout(output):
            m.main()
        service.OpenSession.assert_called_once_with('plain', '')
        args = internal.UnlockWithMasterPassword.call_args.args
        self.assertEqual(args[0], '/org/freedesktop/secrets/collection/Default_5fKeyring')
        self.assertEqual(args[1][0], session_path)
        session.Close.assert_called_once_with()
        self.assertIn('Default Keyring unlocked', output.getvalue())
        self.assertNotIn('test-only-password', output.getvalue())

    def test_error_message_does_not_expose_exception_arguments(self):
        self.assertNotIn('test-only-password', m.error_summary(ValueError('test-only-password')))


if __name__ == '__main__':
    unittest.main()
