"""Batch-assigned places must preserve existing fighters and never overlap them."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ttt2char import InputError, importer, pack


class ImportSlots(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows drive roots')
    def test_output_on_another_drive_is_outside_the_repository(self):
        drive = 'Z:' if os.path.splitdrive(pack.REPOSITORY)[0].upper() != 'Z:' else 'Y:'
        target = drive + '\\TTT2-character-test'
        self.assertEqual(pack.output_folder(target), target)

    def test_assigned_places_cannot_replace_or_move_an_existing_fighter(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / 'aaa'
            old.mkdir()
            (old / 'character.ini').write_text('format = %d\ncode = aaa\ndonor = hei\nslot = 0\n' % pack.PACK_FORMAT)
            self.assertEqual(importer._slot_for(folder, 'aaa'), 0)
            self.assertEqual(importer._slot_for(folder, 'bbb'), 1)
            self.assertEqual(importer._slot_for(folder, 'bbb', 1), 1)
            self.assertEqual(importer._slot_for(folder, 'aaa', 0), 0)
            for code, reserved in [('bbb', 0), ('aaa', 1), ('bbb', -1), ('bbb', pack.MAX_FIGHTERS)]:
                with self.subTest(code=code, reserved=reserved), self.assertRaises(InputError):
                    importer._slot_for(folder, code, reserved)


if __name__ == '__main__':
    unittest.main()
