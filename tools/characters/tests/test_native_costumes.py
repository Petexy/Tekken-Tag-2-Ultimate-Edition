"""Synthetic native-Paul pack lifecycle and chooser input tests (no game assets)."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ttt2char import InputError, native_costumes as native


class NativeCostumeTests(unittest.TestCase):
    def test_texture_ids_keep_native_class_and_do_not_overlap_added_presets(self):
        # A different high byte passes file read-back but asserts when the game resolves material textures.
        self.assertEqual(native.TEXTURE_BASE >> 24, 0x10)
        self.assertEqual(native.PREVIEW_BASE >> 24, 0x10)
        self.assertGreaterEqual(native.TEXTURE_BASE, 0x10d00000)
        self.assertGreaterEqual(native.PREVIEW_BASE, native.TEXTURE_BASE + len(native.PRESETS) * 0x1000)

    def test_selection_deduplicates_and_keeps_stable_codes(self):
        self.assertEqual(native.selection(['cb', 'DefaultCos1P', 'cb']), ['DefaultCos1P', 'cb'])
        self.assertEqual(native.body_code('cb'), 'pvd')
        self.assertEqual(len(native.selection([name for name, _ in native.PRESETS])), 10)
        for invalid in ([], ['unknown']):
            with self.assertRaises(InputError):
                native.selection(invalid)

    def test_publishing_retains_previous_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / 'pau', root / '.new'
            old.mkdir(); new.mkdir()
            (old / 'native.ini').write_text('old')
            (new / 'native.ini').write_text('new')
            native.publish(new, old)
            self.assertEqual((old / 'native.ini').read_text(), 'new')
            backups = list(root.glob('.pau-backup-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / 'native.ini').read_text(), 'old')

    def test_failed_publication_restores_old_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / 'pau', root / '.new'
            old.mkdir(); new.mkdir()
            (old / 'native.ini').write_text('old')
            rename = Path.rename
            def fail(source, target):
                if source == new:
                    raise OSError('simulated failed publish')
                return rename(source, target)
            with patch.object(Path, 'rename', fail), self.assertRaises(OSError):
                native.publish(new, old)
            self.assertEqual((old / 'native.ini').read_text(), 'old')

    def test_unrecognised_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / 'pau', root / '.new'
            old.mkdir(); new.mkdir()
            with self.assertRaises(InputError):
                native.publish(new, old)
            self.assertTrue(old.is_dir())


if __name__ == '__main__':
    unittest.main()
