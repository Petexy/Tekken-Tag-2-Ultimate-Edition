"""Unversioned properties (tekken8/uprops.py) with a made-up schema and package.

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char.tekken8 import cityhash, reflect, uprops, zen   # noqa: E402

ITEM = '/Script/Test.Item'
CLS = cityhash.script_object_id(ITEM)


def p(name, t, **kw):
    d = {'n': name, 't': t}
    d.update(kw)
    return d


SCHEMA = {
    'classes': {
        ITEM: {'name': 'Item', 'super': '/Script/Test.Base', 'flags': 0, 'props': [
            p('Count', 'Int'), p('Ratio', 'Float'), p('Flag', 'Bool'),
            p('Kind', 'Enum', r='EKind', i=p('UnderlyingType', 'Byte')), p('Tag', 'Name'), p('Label', 'Str'),
            p('Mesh', 'Object', r='SkeletalMesh'), p('Soft', 'SoftObject'), p('Tint', 'Struct', r='LinearColor'),
            p('Spot', 'Struct', r='Vector'), p('Parts', 'Array', i=p('Parts', 'Struct', r='Part')),
            p('Table', 'Map', i=p('Table_Key', 'Name'), v=p('Table', 'Int')), p('Raw', 'Array', i=p('Raw', 'Byte')),
            p('Title', 'Text'), p('Slots', 'Int', d=3), p('Pair', 'Struct', r='Pair'), p('Mode', 'Byte', r='EKind'),
            p('Odd', 'Struct', r='Custom'), p('Big', 'Double')]},
        '/Script/Test.Base': {'name': 'Base', 'super': None, 'flags': 0, 'props': [p('BaseValue', 'Int')]}},
    'structs': {
        'Part': {'name': 'Part', 'super': None, 'flags': 0, 'size': 16, 'serializer': False,
                 'props': [p('Name', 'Name'), p('Weight', 'Float'), p('Sub', 'Struct', r='Inner')]},
        'Inner': {'name': 'Inner', 'super': None, 'flags': 0, 'size': 4, 'serializer': False, 'props': [p('V', 'Int')]},
        'Pair': {'name': 'Pair', 'super': None, 'flags': reflect.STRUCT_IMMUTABLE, 'size': 8, 'serializer': None,
                 'props': [p('A', 'Int'), p('B', 'Int16')]},
        'Custom': {'name': 'Custom', 'super': None, 'flags': 0, 'size': 4, 'serializer': True, 'props': []}},
    'enums': {'EKind': {'0': 'First', '3': 'Third'}},
}
NAMES = ['/Game/Test/Item', 'Item', 'None', 'Hello', 'Part1', 'Key1', 'Key2', 'Part2']


def header(entries):
    """An FUnversionedHeader for [(schema index, zero)] (ascending)."""
    frags, at, i = [], 0, 0
    while i < len(entries):
        skip = entries[i][0] - at
        j = i
        while j + 1 < len(entries) and entries[j + 1][0] == entries[j][0] + 1:
            j += 1
        run = entries[i:j + 1]
        frags.append((skip, any(z for _, z in run), len(run), run))
        at = entries[j][0] + 1
        i = j + 1
    out = b''
    for k, (skip, zeros, n, _) in enumerate(frags):
        out += struct.pack('<H', skip | (0x80 if zeros else 0) | (0x100 if k == len(frags) - 1 else 0) | (n << 9))
    bits = [z for _, zeros, _, run in frags if zeros for _, z in run]
    if bits:
        v = sum(1 << k for k, b in enumerate(bits) if b)
        out += struct.pack('<B' if len(bits) <= 8 else '<H' if len(bits) <= 16 else '<I', v)
    return out


def name(n):
    return struct.pack('<II', NAMES.index(n), 0)


def fstring(s):
    b = s.encode() + b'\0'
    return struct.pack('<i', len(b)) + b


class Scripts:
    """The resolver part a package asks for script imports."""

    def script_path(self, v):
        return {cityhash.script_object_id('/Script/Engine.SkeletalMesh'): '/Script/Engine.SkeletalMesh',
                CLS: ITEM}.get(v)


def package(data):
    mesh = synth.script_index(cityhash.script_object_id('/Script/Engine.SkeletalMesh'))
    k = zen.Package(synth.zen_package('/Game/Test/Item', [{'name': 'Item', 'cls': synth.script_index(CLS),
                                                            'data': data}], imports=[mesh]), resolver=Scripts())
    k.names = NAMES                     # the property data's names (the package's own map has the first two)
    return k


class Props(unittest.TestCase):
    def setUp(self):
        self.schema = reflect.Schema(SCHEMA)

    def test_schema(self):
        s = self.schema
        order = [(q.name, i) for q, i in s.schema(ITEM)]
        self.assertEqual(order[14:17], [('Slots', 0), ('Slots', 1), ('Slots', 2)])
        self.assertEqual(order[-1], ('BaseValue', 0))                    # own properties first, then the super's
        self.assertEqual(s.class_key('Item'), ITEM)
        self.assertEqual(s.class_super('Item'), '/Script/Test.Base')
        self.assertEqual(s.enum_name('EKind', 3), 'Third')
        self.assertTrue(s.struct_serializer('Custom'))
        with self.assertRaises(KeyError):
            s.schema('/Script/Test.Nothing')

    def test_values(self):
        part = header([(0, False), (1, False), (2, False)]) + name('Part1') + struct.pack('<f', 0.5) + \
            header([(0, False)]) + struct.pack('<i', 9)
        part2 = header([(0, False), (1, True)]) + name('Part2')         # Weight zero, Sub left out
        data = (header([(0, False), (1, False), (2, False), (3, False), (4, False), (5, False), (6, False),
                        (7, False), (8, False), (9, False), (10, False), (11, False), (12, False), (13, False),
                        (15, False), (16, True), (17, False), (18, False), (20, True), (21, False)]) +
                struct.pack('<i', -5) + struct.pack('<f', 1.5) + b'\x01' + b'\x03' + name('Hello') + fstring('label') +
                struct.pack('<i', -1) + name('/Game/Test/Item') + name('Item') + fstring('') +
                struct.pack('<4f', 1, 0.5, 0.25, 1) + struct.pack('<3d', 1, 2, 3) +
                struct.pack('<i', 2) + part + part2 +
                struct.pack('<ii', 0, 2) + name('Key1') + struct.pack('<i', 10) + name('Key2') + struct.pack('<i', 20) +
                struct.pack('<i', 3) + b'abc' +
                struct.pack('<Ib', 0, 0) + fstring('ns') + fstring('k') + fstring('Source') +
                struct.pack('<i', 41) + struct.pack('<ih', 7, -2) + b'\x03' + struct.pack('<i', 123) +
                b'\0\0\0\0' + b'native')
        k = package(data)
        props, end = uprops.read(k, k.exports[0], self.schema)
        self.assertEqual(k.exports[0].data[end:], b'\0\0\0\0native')
        self.assertEqual(uprops.read_object(k, k.exports[0], self.schema)[1], end + 4)     # after the GUID flag
        self.assertEqual(props['Count'], -5)
        self.assertEqual(props['Ratio'], 1.5)
        self.assertIs(props['Flag'], True)
        self.assertEqual(props['Kind'], 3)
        self.assertEqual(props['Kind'].name, 'Third')
        self.assertEqual((props['Tag'], props['Label']), ('Hello', 'label'))
        self.assertEqual(props['Mesh'], '/Script/Engine.SkeletalMesh')
        self.assertEqual(props['Soft'], '/Game/Test/Item.Item')
        self.assertEqual(props['Tint'], {'R': 1.0, 'G': 0.5, 'B': 0.25, 'A': 1.0})
        self.assertEqual(props['Spot'], {'X': 1.0, 'Y': 2.0, 'Z': 3.0})
        self.assertEqual(props['Parts'], [{'Name': 'Part1', 'Weight': 0.5, 'Sub': {'V': 9}},
                                          {'Name': 'Part2', 'Weight': 0.0}])
        self.assertEqual(props['Table'], {'Key1': 10, 'Key2': 20})
        self.assertEqual(props['Raw'], b'abc')
        self.assertEqual(props['Title'], {'flags': 0, 'namespace': 'ns', 'key': 'k', 'source': 'Source'})
        self.assertEqual((props['Slots[1]'], props['Slots[2]']), (41, 0))
        self.assertNotIn('Slots[0]', props)                            # left out: the class default
        self.assertEqual(props['Pair'], {'A': 7, 'B': -2})
        self.assertEqual(props['Mode'].name, 'Third')
        self.assertEqual(props['Big'], 0.0)
        self.assertEqual(props['BaseValue'], 123)

    def test_custom_struct(self):
        data = header([(19, False)]) + b'\0' * 8
        k = package(data)
        with self.assertRaises(NotImplementedError):
            uprops.read(k, k.exports[0], self.schema)

    def test_zero_struct_and_errors(self):
        data = header([(8, True), (10, True), (11, True)]) + b'\0' * 4
        k = package(data)
        props, end = uprops.read(k, k.exports[0], self.schema)
        self.assertEqual(props, {'Tint': {'R': 0.0, 'G': 0.0, 'B': 0.0, 'A': 0.0}, 'Parts': [], 'Table': {}})
        k = package(header([(40, False)]) + b'\0' * 4)                 # beyond the schema
        with self.assertRaises(ValueError):
            uprops.read(k, k.exports[0], self.schema)
        k = package(header([(0, False)]))                              # value past the export's end
        with self.assertRaises(ValueError):
            uprops.read(k, k.exports[0], self.schema)
        with self.assertRaises(KeyError):
            uprops.read(k, k.exports[0], self.schema, class_name='/Script/Test.Nothing')


if __name__ == '__main__':
    unittest.main()
