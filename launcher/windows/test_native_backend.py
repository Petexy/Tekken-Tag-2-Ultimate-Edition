"""Native roster launcher commands and actual-runtime capability checks."""
from pathlib import Path
import tempfile
import unittest

from backend import Settings, native_runtime_ready


class NativeBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.settings = Settings(self.root / 'build', self.root / 'config.json', self.root)
        self.game = self.root / 'installed'
        (self.game / 'game/code').mkdir(parents=True)
        (self.game / 'game/content/hdd').mkdir(parents=True)
        (self.game / '.ttt2-install').touch()
        (self.game / 'game/code/Tekken.rpx').touch()
        (self.game / 'game/content/hdd/data000.ofs').touch()
        self.settings.values.update(install=str(self.game), packs=str(self.root / 'packs'))

    def test_actual_binary_must_support_native_costumes(self):
        self.assertFalse(native_runtime_ready(self.settings))
        exe = self.game / 'TTT2 Ultimate.exe'
        exe.write_bytes(b'old game')
        with self.assertRaisesRegex(ValueError, 'costume-enabled'):
            self.settings.native_costume_command(['DefaultCos1P'])
        exe.write_bytes(b'header\x00ttt2: native Paul:\x00old-six-slot-build')
        self.assertFalse(native_runtime_ready(self.settings))
        exe.write_bytes(b'header\x00ttt2: native costume pages v1:\x00old-paul-only-build')
        self.assertFalse(native_runtime_ready(self.settings))
        exe.write_bytes(b'header\x00ttt2: native roster costumes v2:\x00test')
        self.assertTrue(native_runtime_ready(self.settings))
        command = self.settings.native_costume_command(['DefaultCos1P', 'cb'])
        self.assertEqual(command[-2:], ['DefaultCos1P', 'cb'])
        self.assertIn(str(self.root / 'tools/characters/import_native_costumes.py'), command)
        self.assertNotIn('import_character.py', ' '.join(command))

    def test_roster_requests_keep_target_and_presets_separate(self):
        (self.game / 'TTT2 Ultimate.exe').write_bytes(b'ttt2: native roster costumes v2:')
        command = self.settings.native_costume_command(['jul:DefaultCos1P', 'jul:nature'])
        self.assertEqual(command[-4:], ['--fighter', 'jul', 'DefaultCos1P', 'nature'])
        self.assertEqual(self.settings.native_costume_command(['all'])[-1], '--all-roster')
        self.assertEqual(self.settings.native_costume_command(['law'], remove=True)[-3:], ['--fighter', 'law', '--remove'])
        from ttt2char import InputError
        with self.assertRaises(InputError):
            self.settings.native_costume_command(['law:DefaultCos1P', 'jul:DefaultCos1P'])

    def test_remove_does_not_require_the_new_runtime(self):
        command = self.settings.native_costume_command([], remove=True)
        self.assertEqual(command[-1], '--remove')


if __name__ == '__main__':
    unittest.main()
