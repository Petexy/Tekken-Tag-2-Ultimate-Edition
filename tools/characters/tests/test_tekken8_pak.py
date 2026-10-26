"""Tekken 8's pak files, version 11 (tekken8/pak.py), on made-up paks.

    python3 -m unittest discover tools/characters/tests
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char.tekken8 import pak                      # noqa: E402

FILES = {'Polaris/Content/WwiseAudio/Event/Play_Test.bnk': b'BKHD' + bytes(range(256)) * 9,      # several blocks
         'Polaris/Content/WwiseAudio/Media/1234.wem': b'RIFF\x01\x02\x03',                      # stored
         'Engine/GlobalShaderCache.bin': b'shader' * 50}                                        # one block


class Pak(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_encoded_entries(self):
        path = os.path.join(self.dir, 'pakchunk0-Windows.pak')
        synth.write_pak(path, FILES, deleted=['Polaris/Content/Gone.wem'])
        k = pak.Pak(path)
        self.assertEqual(k.version, 11)
        self.assertEqual(sorted(k.files), sorted(FILES))
        self.assertEqual(k.deleted, {'Polaris/Content/Gone.wem'})
        for name, data in FILES.items():
            self.assertEqual(k.read(name), data, name)
        e = k.entry('Polaris/Content/WwiseAudio/Event/Play_Test.bnk')
        self.assertEqual((e.method, e.block_size, len(e.blocks)), ('Zlib', 0x400, 3))
        self.assertEqual(k.entry('Polaris/Content/WwiseAudio/Media/1234.wem').method, '')
        with self.assertRaises(KeyError):
            k.entry('Polaris/Content/Nothing.wem')
        k.close()

    def test_records_and_path_hashes(self):
        path = os.path.join(self.dir, 'pakchunk1-Windows.pak')
        synth.write_pak(path, FILES, records=['Engine/GlobalShaderCache.bin'], hash_index=True, seed=99)
        k = pak.Pak(path)
        self.assertEqual(k.files, {})                       # a path hash index lists nothing ...
        for name, data in FILES.items():
            self.assertEqual(k.read(name), data, name)      # ... but reads by path, in any case
        self.assertEqual(k.read('engine/globalshadercache.bin'), FILES['Engine/GlobalShaderCache.bin'])
        k.close()

    def test_path_hash_and_order(self):
        # FNV-1a 64 over UTF-16LE, the offset basis moved by the seed
        h = pak.FNV_OFFSET
        for c in 'ab'.encode('utf-16-le'):
            h = ((h ^ c) * pak.FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
        self.assertEqual(pak.path_hash('AB', 0), h)
        self.assertNotEqual(pak.path_hash('ab', 1), h)
        names = ['pakchunk0-Windows_1_P.pak', 'pakchunk0-Windows.pak', 'pakchunk0-Windows_0_P.pak', 'a.pak']
        self.assertEqual(sorted(names, key=pak.patch_order),
                         ['a.pak', 'pakchunk0-Windows.pak', 'pakchunk0-Windows_0_P.pak', 'pakchunk0-Windows_1_P.pak'])

    def test_not_a_pak(self):
        path = os.path.join(self.dir, 'bad.pak')
        with open(path, 'wb') as f:
            f.write(bytes(400))
        with self.assertRaises(ValueError):
            pak.Pak(path)


if __name__ == '__main__':
    unittest.main()
