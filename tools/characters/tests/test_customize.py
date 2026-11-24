"""An added fighter's saved customization file (ttt2char/customize.py, customize_slot.py): made-up items."""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

from ttt2char import customize

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'customize_slot.py')


class Layout(unittest.TestCase):
    def test_empty_file(self):
        body = customize.empty()
        self.assertEqual(len(body), 256400)
        self.assertEqual(struct.unpack_from('>f', body, 0)[0], struct.unpack('>f', struct.pack('>f', 1.2))[0])
        for n in range(customize.RECORDS):
            self.assertFalse(customize.filled(body, n))
        self.assertEqual(bytes(body[customize.FIRST_PICTURE:]), bytes(11 * 19584))

    def test_empty_record(self):
        r = customize.empty_record()
        self.assertEqual(r[0], 0)
        self.assertEqual(struct.unpack_from('>21i', r, 4), (-1,) * 21)
        self.assertEqual(bytes(r[568:574]), b'\xff' * 6)
        self.assertEqual(struct.unpack_from('>IIf', r, 576 + 12 * 69), (0, 0, -1.0))
        self.assertEqual(struct.unpack_from('>ii6f', r, 2464), (-1, -1, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0))
        self.assertEqual(struct.unpack_from('>i', r, 2320 + 36 + 4), (-1,))
        self.assertEqual(struct.unpack_from('>5i', r, 3264), (-1, -1, 0, -1, -1))

    def test_record(self):
        items, colours = customize.parse('0=7, 5=300,15=12/3,c26=40,c31=41,c51=18433')
        r = customize.record(items, colours, 2)
        self.assertEqual(r[0], 1)
        self.assertEqual(struct.unpack_from('>i', r, 4)[0], 7)
        self.assertEqual(struct.unpack_from('>i', r, 4 + 4 * 5)[0], 300)
        self.assertEqual(struct.unpack_from('>i', r, 4 + 4 * 1)[0], -1)
        self.assertEqual(struct.unpack_from('>3H', r, 568), (3, 0xFFFF, 0xFFFF))
        self.assertEqual(struct.unpack_from('>I', r, 636 + 4)[0], 40)        # group 0 is stored second
        self.assertEqual(struct.unpack_from('>I', r, 576 + 4)[0], 41)        # group 1 first
        self.assertEqual(struct.unpack_from('>I', r, 576 + 60 * 5 + 4)[0], 18433)
        self.assertEqual(struct.unpack_from('>i', r, 3276)[0], 2)

    def test_bad_texts(self):
        for bad in ('5', '21=1', '-1=1', '5=0', '5=x', '5=1/2', 'c25=1', 'c96=1', 'c30=-1', '5=70000'):
            with self.assertRaises(ValueError, msg=bad):
                customize.parse(bad)

    def test_merge_later_wins(self):
        items, colours = customize.merge(['0=5,8=1,c51=3', '8=42,9=36,c51=91'])
        self.assertEqual(items, {0: (5, None), 8: (42, None), 9: (36, None)})
        self.assertEqual(colours, {51: 91})


class Files(unittest.TestCase):
    def test_slots_by_code(self):
        with tempfile.TemporaryDirectory() as save:
            body = customize.load(save, 'abc')
            customize.set_slot(body, 1, ['0=5,8=42'])
            out = customize.store(save, 'abc', body)
            self.assertEqual(out, os.path.join(save, 'customize', 'abc.bin'))
            self.assertEqual(os.listdir(os.path.join(save, 'customize')), ['abc.bin'])   # no temporary file left
            again = customize.load(save, 'abc')
            self.assertEqual(again, body)
            self.assertEqual([customize.filled(again, n) for n in range(5)], [False, True, False, False, False])
            self.assertEqual(customize.items_of(again, 1), {0: 5, 8: 42})
            self.assertFalse(customize.filled(customize.load(save, 'abd'), 1))           # another code: its own file
            customize.clear_slot(again, 1)
            self.assertEqual(again, customize.empty())

    def test_only_slots_and_codes(self):
        body = customize.empty()
        for bad in (-1, 5, 9):
            with self.assertRaises(ValueError):
                customize.set_slot(body, bad, ['0=5'])
        with self.assertRaises(ValueError):
            customize.set_slot(body, 0, ['c51=3'])
        for bad in ('', '../x', 'a/b', 'a.b'):
            with self.assertRaises(ValueError):
                customize.path('save', bad)

    def test_not_a_customization_file(self):
        with tempfile.TemporaryDirectory() as save:
            os.makedirs(os.path.join(save, 'customize'))
            with open(os.path.join(save, 'customize', 'abc.bin'), 'wb') as f:
                f.write(b'x' * 100)
            with self.assertRaises(ValueError):
                customize.load(save, 'abc')

    def test_tool(self):
        with tempfile.TemporaryDirectory() as root:
            save, pack = os.path.join(root, 'save'), os.path.join(root, 'abc')
            os.makedirs(save)
            os.makedirs(pack)
            with open(os.path.join(pack, 'wardrobe.txt'), 'w', encoding='utf-8') as f:
                f.write('xyz_upb_shirt: 8=51,9=49,c51=91\nxyz_lob_jeans: 12=86,13=72,c66=83\nxyz_lob_jeans_b: 12=86,c66=2\n')
            run = lambda *a: subprocess.run([sys.executable, TOOL, save, 'abc', *a], capture_output=True, text=True)
            done = run('3', '0=5,8=1,12=2', '--pack', pack, 'upb_shirt', 'xyz_lob_jeans')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            body = customize.load(save, 'abc')
            self.assertEqual(customize.items_of(body, 3), {0: 5, 8: 51, 9: 49, 12: 86, 13: 72})
            self.assertIn('slot 3: 0=5,8=51,9=49,12=86,13=72', run().stdout)
            self.assertNotEqual(run('2', '--pack', pack, 'nothing_like_it').returncode, 0)
            self.assertNotEqual(run('2', '--pack', pack, 'xyz_lob').returncode, 0)        # names two rows
            self.assertEqual(run('3', '--clear').returncode, 0)
            self.assertEqual(customize.load(save, 'abc'), customize.empty())


if __name__ == '__main__':
    unittest.main()
