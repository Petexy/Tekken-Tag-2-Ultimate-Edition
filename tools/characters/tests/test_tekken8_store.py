"""The Tekken 8 installation as a store (tekken8/store.py), on a made-up game folder: IoStore containers with a
patch, pak files with a patch, packages and their imports.

    python3 -m unittest discover tools/characters/tests
"""
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char import InputError                       # noqa: E402
from ttt2char.tekken8 import cityhash, store, zen     # noqa: E402

PKG_A, PKG_B, PKG_C = '/Game/Test/A', '/Game/Test/B', '/Game/Test/C'
ENGINE = cityhash.script_object_id('/Script/Engine')
TEXTURE = cityhash.script_object_id('/Script/Engine.Texture2D')
HASH_B = cityhash.public_export_hash('ObjB')
NULL = synth.NULL


def _package_a(bulk_data):
    inline = b'\x01\x00\x00\x00' + b'INLINE'            # the bulk entry's index (1) right before its payload
    exports = [{'name': 'A', 'cls': synth.script_index(TEXTURE), 'data': b'\0' * 8 + inline},
               {'name': 'Sub', 'cls': synth.script_index(TEXTURE), 'outer': 0, 'data': b'sub data'}]
    bulk = [(0, len(bulk_data), zen.BULK_SEPARATE), (12, 6, zen.BULK_INLINE), (0, 0, 0)]
    return synth.zen_package(PKG_A, exports, imports=[synth.script_index(TEXTURE), synth.package_import(0, 0), NULL],
                             hashes=[HASH_B], bulk=bulk, imported_packages=1, order=[1, 0], cooked_order=[0, 1])



def _package_b(name):
    return synth.zen_package(PKG_B, [{'name': name, 'cls': synth.script_index(TEXTURE), 'hash': HASH_B,
                                      'data': b'B' * 3000}])


class Store(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.game = os.path.join(cls.dir, 'steamapps', 'common', 'TEKKEN 8')
        paks = os.path.join(cls.game, 'Polaris', 'Content', 'Paks')
        os.makedirs(paks)
        rnd = random.Random(3)
        cls.bulk = bytes(rnd.randrange(256) for _ in range(5000))        # five blocks of 0x400, incompressible
        cls.pid = {p: cityhash.package_id(p) for p in (PKG_A, PKG_B, PKG_C)}
        a, b = _package_a(cls.bulk), _package_b('ObjB')
        synth.write_container(os.path.join(paks, 'global'), [
            (0, zen.CHUNK_SCRIPT_OBJECTS, 0, synth.script_objects([('/Script/Engine', ENGINE, NULL),
                                                                   ('Texture2D', TEXTURE, ENGINE)]))], [])
        synth.write_container(os.path.join(paks, 'pakchunk0-Windows'), [
            (cls.pid[PKG_A], 1, 0, a), (cls.pid[PKG_A], 2, 0, cls.bulk), (cls.pid[PKG_B], 1, 0, b),
            (11, zen.CHUNK_CONTAINER_HEADER, 0, synth.container_header(11, [(cls.pid[PKG_A], [cls.pid[PKG_B]]),
                                                                           (cls.pid[PKG_B], [])]))],
            [('Polaris/Content/Test/A.uasset', 0), ('Polaris/Content/Test/A.ubulk', 1),
             ('Polaris/Content/Test/B.uasset', 2)], container_id=11)
        cls.b_patched = _package_b('ObjB')[:-3000] + b'P' * 3000
        synth.write_container(os.path.join(paks, 'pakchunk0-Windows_0_P'), [
            (cls.pid[PKG_B], 1, 0, cls.b_patched), (cls.pid[PKG_C], 1, 0, _package_b('ObjC')),
            (12, zen.CHUNK_CONTAINER_HEADER, 0, synth.container_header(12, [(cls.pid[PKG_B], []),
                                                                           (cls.pid[PKG_C], [])]))],
            [('Polaris/Content/Test/B.uasset', 0), ('Polaris/Content/Test/C.uasset', 1)], container_id=12)
        synth.write_pak(os.path.join(paks, 'pakchunk0-Windows.pak'), {
            'Polaris/Content/WwiseAudio/Media/1.wem': b'RIFF one' * 300,
            'Polaris/Content/WwiseAudio/Event/Play_X.bnk': b'BKHD base',
            'Polaris/Content/Binary/pak/tkdata.bin': b'never read'})
        synth.write_pak(os.path.join(paks, 'pakchunk0-Windows_0_P.pak'), {
            'Polaris/Content/WwiseAudio/Event/Play_X.bnk': b'BKHD patched'},
            deleted=['Polaris/Content/WwiseAudio/Media/1.wem'])
        with open(os.path.join(paks, 'pakchunk9-Windows.pak'), 'wb') as f:
            f.write(bytes(339))                                          # a stub that is not a pak: skipped
        cls.s = store.Store(cls.game)

    @classmethod
    def tearDownClass(cls):
        cls.s.close()
        shutil.rmtree(cls.dir)

    def test_folder(self):
        for f in (self.game, os.path.join(self.game, 'Polaris', 'Content', 'Paks'), self.dir,
                  os.path.join(self.dir, 'steamapps')):
            self.assertEqual(store.game_folder(f), self.game)
        with self.assertRaises(InputError):
            store.Store(os.path.join(self.dir, 'steamapps', 'nothing'))
        with self.assertRaises(InputError):
            store.game_folder('')
        self.assertEqual(self.s.exe, os.path.join(self.game, 'Polaris', 'Binaries', 'Win64',
                                                  'Polaris-Win64-Shipping.exe'))

    def test_paths(self):
        s = self.s
        for p in (PKG_A, PKG_A + '.A', PKG_A + '.A:Sub', 'Polaris/Content/Test/A', 'polaris/content/test/a.uasset',
                  '../../../Polaris/Content/Test/A.uasset'):
            self.assertEqual(s.file_path(p), 'Polaris/Content/Test/A.uasset', p)
        self.assertFalse(s.exists('/Game/Test/Missing'))
        self.assertFalse(s.exists('/Nowhere/Test/A'))
        self.assertEqual(s.find('/Game/Test/'), ['Polaris/Content/Test/A.uasset', 'Polaris/Content/Test/A.ubulk',
                                                 'Polaris/Content/Test/B.uasset', 'Polaris/Content/Test/C.uasset'])
        self.assertEqual(s.find('*/test/?.uasset'), ['Polaris/Content/Test/A.uasset', 'Polaris/Content/Test/B.uasset',
                                                     'Polaris/Content/Test/C.uasset'])
        self.assertEqual(store.mount_to_package('Polaris/Content/Test/A.uasset'), PKG_A)
        self.assertEqual(store.mount_to_package('Engine/Plugins/FX/Niagara/Content/X/Y.uasset'), '/Niagara/X/Y')
        self.assertEqual([n for n, _ in s.skipped], ['pakchunk9-Windows.pak'])

    def test_reads(self):
        s = self.s
        self.assertEqual(s.read('Polaris/Content/Test/A.ubulk'), self.bulk)
        for o, n in ((0, 1), (1000, 2000), (1023, 2), (4999, 10), (3072, 1024)):
            self.assertEqual(s.read('Polaris/Content/Test/A.ubulk', o, n), self.bulk[o:o + n])
        self.assertEqual(s.chunk(self.pid[PKG_A], zen.CHUNK_BULK), self.bulk)
        self.assertTrue(s.has_chunk(self.pid[PKG_A], zen.CHUNK_BULK))
        self.assertEqual(s.read(PKG_B), self.b_patched)                  # the patch container wins
        self.assertEqual(s.read('Polaris/Content/WwiseAudio/Event/Play_X.bnk'), b'BKHD patched')
        self.assertFalse(s.exists('Polaris/Content/WwiseAudio/Media/1.wem'))     # deleted by the patch pak
        with self.assertRaises(KeyError):
            s.read('Polaris/Content/Binary/pak/tkdata.bin')              # never read
        with self.assertRaises(KeyError):
            s.read('/Game/Test/Missing')

    def test_packages(self):
        s = self.s
        k = s.package(PKG_A)
        self.assertEqual(k.name, PKG_A)
        self.assertEqual(k.package_id, self.pid[PKG_A])
        self.assertEqual(k.imports, ['/Script/Engine.Texture2D', (PKG_B, 'ObjB'), None])
        self.assertEqual([e.class_name for e in k.exports], ['Texture2D', 'Texture2D'])
        self.assertEqual(k.exports[1].path, PKG_A + '.A:Sub')
        self.assertEqual(k.exports[0].data, b'\0' * 8 + b'\x01\x00\x00\x00INLINE')    # bundle order, not cooked
        self.assertEqual(k.exports[1].data, b'sub data')
        self.assertEqual(k.bulk(0), self.bulk)
        self.assertEqual(k.bulk(1), b'INLINE')
        self.assertEqual(k.bulk(2), b'')
        self.assertEqual(k.reference(-2), PKG_B + '.ObjB')
        self.assertEqual(k.reference(1), PKG_A + '.A')
        self.assertEqual(s.package_name(self.pid[PKG_C]), PKG_C)
        self.assertEqual(s.imported_package_ids(self.pid[PKG_A]), (self.pid[PKG_B],))
        with self.assertRaises(KeyError):
            s.package('Polaris/Content/Test/A.ubulk')


if __name__ == '__main__':
    unittest.main()
