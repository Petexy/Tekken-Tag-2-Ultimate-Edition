"""Native Windows process lifetime checks; no game or Steam data required."""
import ctypes
from ctypes import wintypes
import os
import secrets
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if os.name == 'nt':
    from ttt2char.tekken7 import autodump, autodump_windows as windows


@unittest.skipUnless(os.name == 'nt', 'native Windows host')
class WindowsHost(unittest.TestCase):
    def test_attach_targets_only_the_session_process(self):
        helper = autodump.Helper.__new__(autodump.Helper)
        helper.target_pid = 1234
        helper._answer = mock.Mock(return_value='ok')
        self.assertEqual(helper.attach(), 'ok')
        helper._answer.assert_called_once_with('attach 1234')

    def test_structures_and_process_list(self):
        self.assertEqual(ctypes.sizeof(windows.Startup), 104)
        self.assertEqual(ctypes.sizeof(windows.ProcessInfo), 24)
        self.assertEqual(ctypes.sizeof(windows.ExtendedLimits), 144)
        self.assertIn(os.getpid(), [pid for pid, _ in windows.processes()])

    def test_existing_game_is_refused_without_starting_children(self):
        with tempfile.TemporaryDirectory() as folder:
            before = list(autodump._open)
            t7 = SimpleNamespace(game=folder)
            with mock.patch.object(windows, 'tekken7_running', return_value=True), \
                    mock.patch.object(windows.Session, '_spawn') as spawn:
                with self.assertRaisesRegex(autodump.DumpError, 'close it first'):
                    windows.Session(t7, 'unused', folder, True)
                spawn.assert_not_called()
            self.assertEqual(autodump._open, before)

    def test_private_desktop_job_ends_only_its_own_process(self):
        open_process = windows.api(windows.kernel, 'OpenProcess', wintypes.HANDLE,
                                   wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        session, monitor = None, None
        try:
            with tempfile.TemporaryDirectory() as folder:
                session = windows.Session.__new__(windows.Session)
                session.t7, session.run = SimpleNamespace(game=folder), folder
                session.closed = session.locked = False
                session.helper = session.mutex = session.desktop = None
                session.children = []
                session.job = windows.checked(windows.create_job(None, None), 'test job')
                limits = windows.ExtendedLimits()
                limits.basic.flags = 0x2000
                windows.checked(windows.set_job(session.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), 'test limits')
                name = 'TTT2ImportTest-' + secrets.token_hex(8)
                session.desktop = windows.checked(windows.create_desktop(name, None, None, 0, 0x1ff, None), 'test desktop')
                child = session._spawn([sys.executable, '-c', 'import time; time.sleep(30)'], 'child.log', name)
                monitor = windows.checked(open_process(0x100000, False, child.pid), 'test process handle')
                self.assertEqual(windows.wait(monitor, 50), 0x102)
                session.close()
                session.close()  # idempotent
                self.assertEqual(windows.wait(monitor, 1000), 0)
                self.assertIsNone(unrelated.poll())
        finally:
            if session:
                session.close()
            if monitor:
                windows.close_handle(monitor)
            unrelated.terminate()
            unrelated.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
