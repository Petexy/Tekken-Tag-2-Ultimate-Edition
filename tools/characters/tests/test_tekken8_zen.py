"""Tekken 8's zen packages (tekken8/zen.py) on made-up packages, names resolved through a made-up store.

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char.tekken8 import cityhash, zen            # noqa: E402

NULL = synth.NULL
CLS = cityhash.script_object_id('/Script/Polaris.CustomizeItem')
PKG = cityhash.script_object_id('/Script/Polaris')


class FakeStore:
    """What zen.Resolver asks a store for."""

    def __init__(self, packages, imported, scripts, chunks=None):
        self.packages, self.imported, self.scripts, self.chunks = packages, imported, scripts, chunks or {}

    def script_objects_data(self):
        return self.scripts

    def imported_package_ids(self, pid):
        return self.imported.get(pid, ())

    def package_name(self, pid):
        return None

    def package_header(self, pid):
        return self.packages.get(pid)

    def chunk(self, pid, ctype, index=0):
        return self.chunks[(pid, ctype, index)]


class Zen(unittest.TestCase):
    def setUp(self):
        self.lib = '/Game/Lib/Materials'
        self.lib_id = cityhash.package_id(self.lib)
        lib = synth.zen_package(self.lib, [
            {'name': 'MI_Red', 'cls': synth.script_index(CLS), 'hash': cityhash.public_export_hash('MI_Red'),
             'data': b'red'},
            {'name': 'Inner', 'cls': synth.script_index(CLS), 'outer': 0,
             'hash': cityhash.public_export_hash('MI_Red:Inner'), 'data': b'inner'}])
        self.main = '/Game/Fighter/CI_Test'
        self.main_id = cityhash.package_id(self.main)
        exports = [{'name': 'Default__CI_Test_C', 'cls': 2, 'data': b'cdo!'},                    # class: export 2
                   {'name': 'CI_Test', 'cls': synth.script_index(CLS), 'data': b'\x01\x00\x00\x00PAYLOAD!' + b'x' * 50},
                   {'name': 'CI_Test_C', 'cls': synth.package_import(0, 1), 'data': b'class'}]
        self.data = synth.zen_package(
            self.main, exports, imports=[synth.script_index(CLS), synth.package_import(0, 0),
                                         synth.package_import(0, 1), NULL, synth.package_import(1, 0)],
            hashes=[cityhash.public_export_hash('MI_Red'), cityhash.public_export_hash('mi_red/inner')],
            bulk=[(0, 4, zen.BULK_SEPARATE), (4, 8, zen.BULK_INLINE)], imported_packages=1, order=[2, 1, 0])
        scripts = synth.script_objects([('/Script/Polaris', PKG, NULL), ('CustomizeItem', CLS, PKG),
                                        ('Default__CustomizeItem', cityhash.script_object_id(
                                            '/Script/Polaris.Default__CustomizeItem'), PKG)])
        self.store = FakeStore({self.lib_id: lib}, {self.main_id: (self.lib_id,)}, scripts,
                               {(self.main_id, zen.CHUNK_BULK, 0): b'BULKdata'})
        self.resolver = zen.Resolver(self.store)
        self.pkg = zen.Package(self.data, 'Polaris/Content/Fighter/CI_Test.uasset', self.main_id, self.resolver,
                               self.store)

    def test_layout(self):
        k = self.pkg
        self.assertEqual(k.name, self.main)
        self.assertEqual([e.name for e in k.exports], ['Default__CI_Test_C', 'CI_Test', 'CI_Test_C'])
        # the data follows the bundles' serialize order (2, 1, 0), not the cooked offsets (reversed here)
        self.assertEqual(k.exports[2].offset, k.header_size)
        self.assertEqual(k.exports[2].data, b'class')
        self.assertEqual(k.exports[0].data, b'cdo!')
        self.assertEqual(len(k.bundles), 1)
        self.assertEqual(len(k.external_arcs), 1)
        self.assertEqual(k.main_export().name, 'CI_Test')
        self.assertEqual(k.find_export('CustomizeItem').name, 'CI_Test')
        self.assertEqual(k.find_export('/Script/Polaris.CustomizeItem', 'CI_Test').index, 1)
        self.assertIsNone(k.find_export('Texture2D'))

    def test_names(self):
        k = self.pkg
        self.assertEqual(k.imports, ['/Script/Polaris.CustomizeItem', (self.lib, 'MI_Red'), (self.lib, 'MI_Red:Inner'),
                                     None, ('?package#1', '?%016x' % cityhash.public_export_hash('MI_Red'))])
        self.assertEqual(k.exports[1].class_path, '/Script/Polaris.CustomizeItem')
        self.assertEqual(k.exports[1].class_name, 'CustomizeItem')
        self.assertEqual(k.exports[0].class_name, 'CI_Test_C')                 # a class among its own exports
        self.assertEqual(k.exports[2].class_path, self.lib + '.MI_Red:Inner')  # (an import; any object here)
        self.assertEqual(k.reference(-2), self.lib + '.MI_Red')
        self.assertEqual(k.reference(-3), self.lib + '.MI_Red:Inner')
        self.assertEqual(k.reference(2), self.main + '.CI_Test')
        self.assertIsNone(k.reference(0))
        self.assertEqual(zen.short_name('/Game/X/Y.Z:W'), 'W')

    def test_bulk(self):
        k = self.pkg
        self.assertEqual(k.bulk(0), b'BULKdata'[:4])
        self.assertEqual(k.bulk_owner(k.bulk_map[1]).name, 'CI_Test')        # the export with index 1 before it
        self.assertEqual(k.bulk(1), b'PAYLOAD!')
        self.assertEqual(k.bulk(1, k.exports[1]), b'PAYLOAD!')

    def test_without_resolver(self):
        k = zen.Package(self.data)
        self.assertEqual(k.exports[1].class_path, 'script:%016x' % synth.script_index(CLS))
        self.assertEqual(k.imports[1], ('package#0', '?%016x' % cityhash.public_export_hash('MI_Red')))
        with self.assertRaises(zen.ParseError):
            k.bulk(0)                                   # a separate payload needs the store

    def test_tables(self):
        scripts = zen.script_objects(self.store.scripts)
        self.assertEqual(scripts[CLS], '/Script/Polaris.CustomizeItem')
        self.assertEqual(scripts[PKG], '/Script/Polaris')
        header = zen.container_header(synth.container_header(5, [(1, [2, 3]), (2, [])]))
        self.assertEqual(header, {1: (1, 1, (2, 3)), 2: (1, 1, ())})
        with self.assertRaises(zen.ParseError):
            zen.container_header(b'\0' * 32)

    def test_bad_packages(self):
        with self.assertRaises(zen.ParseError):
            zen.Package(b'\0' * 10)
        bad = bytearray(self.data)
        struct.pack_into('<I', bad, 0, 1)               # versioned
        with self.assertRaises(zen.ParseError):
            zen.Package(bytes(bad))


if __name__ == '__main__':
    unittest.main()
