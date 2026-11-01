"""Swimsuit actions require only the Wii U game and preserve native imports."""
import unittest
from test_native_backend import NativeBackendTests
from backend import swimsuit_runtime_ready

class SwimsuitBackendTests(unittest.TestCase):
    setUp = NativeBackendTests.setUp

    def test_capability_is_checked_separately(self):
        exe = self.game / 'TTT2 Ultimate.exe'
        exe.write_bytes(b'ttt2: native roster costumes v2:')
        self.assertFalse(swimsuit_runtime_ready(self.settings))
        with self.assertRaisesRegex(ValueError, 'swimsuit-enabled'):
            self.settings.swimsuit_command(['knm'])
        exe.write_bytes(b'ttt2: Wii U swimsuits v1:')
        self.assertTrue(swimsuit_runtime_ready(self.settings))
        command = self.settings.swimsuit_command(['knm', 'leo'])
        self.assertEqual(command[-2:], ['knm', 'leo'])
        self.assertIn('import_swimsuits.py', ' '.join(command))
        self.assertNotIn('--tekken7', command)

    def test_removal_does_not_require_updated_binary(self):
        self.assertIn('--remove', self.settings.swimsuit_command(['knm'], remove=True))

    def test_unknown_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'supported'):
            self.settings.swimsuit_command(['../../native/pau'], remove=True)

if __name__ == '__main__':
    unittest.main()
