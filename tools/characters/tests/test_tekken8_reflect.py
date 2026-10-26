"""Class and struct layouts read from a program (tekken8/reflect.py), on a made-up PE image holding the code
generator's parameter tables for two classes, two structs and an enum.

    python3 -m unittest discover tools/characters/tests
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char.tekken8 import reflect                  # noqa: E402

BASE = 0x140000000
TEXT, RDATA, DATA, PDATA = 0x1000, 0x2000, 0x5000, 0x7000
SLOT = 32                                             # bytes per made-up function
(BASE_CLASS, DERIVED_CLASS, DERIVED_NOREGISTER, CONSTRUCT_BASE, CONSTRUCT_TINT, CONSTRUCT_PACKED, CONSTRUCT_KIND,
 TINT_OPS, TINT_CAPS, PACKED_OPS, PACKED_CAPS, DESTRUCTOR) = range(12)


def fn(i):
    return BASE + TEXT + SLOT * i


class Section:
    def __init__(self, rva):
        self.rva, self.b = rva, bytearray()

    def put(self, data, align=8):
        self.b += bytes(-len(self.b) % align)
        va = BASE + self.rva + len(self.b)
        self.b += data
        return va


def program():
    rd, da = Section(RDATA), Section(DATA)
    unwind = rd.put(b'\x01\x00\x00\x00', 4)
    w = {s: rd.put(s.encode('utf-16-le') + b'\0\0', 2) for s in ('/Script/Test', 'Base', 'Derived')}
    c = {s: rd.put(s.encode() + b'\0', 1) for s in ('Health', 'Names', 'Tint', 'Mode', 'UnderlyingType', 'Lookup',
                                                     'Lookup_Key', 'Owner', 'Slots', 'R', 'Flag', 'Packed', 'EKind',
                                                     'EKind::A', 'EKind::B')}

    def prop(name, gen, dim=1, func=0):
        return rd.put(struct.pack('<QQQBxxxIiIQQiIQQ', c[name], 0, 0x5, gen, 0x45, dim, 0, 0, 0, 0, 0, func, 0))

    def array(ptrs):
        return rd.put(b''.join(struct.pack('<Q', p) for p in ptrs))
    base_props = array([prop('Health', 0x03), prop('Names', 0x14), prop('Names', 0x16)])
    derived_props = array([prop('Tint', 0x19, func=fn(CONSTRUCT_TINT)), prop('UnderlyingType', 0x00),
                           prop('Mode', 0x1E, func=fn(CONSTRUCT_KIND)), prop('Lookup', 0x03),
                           prop('Lookup_Key', 0x15), prop('Lookup', 0x17),
                           prop('Owner', 0x12 | 0x40, func=fn(CONSTRUCT_BASE)), prop('Slots', 0x03, dim=4)])
    tint_props = array([prop('R', 0x0A), prop('Flag', 0x0C)])
    no_deps = array([0])
    base_deps = array([fn(CONSTRUCT_BASE)])

    def class_params(no_register, deps, props, n):
        return rd.put(struct.pack('<QQQQQQQiiiiI4x', no_register, 0, 0, deps, 0, props, 0, 1, 0, n, 0, 0x100080))
    base_params = class_params(fn(BASE_CLASS), no_deps, base_props, 3)
    derived_params = class_params(fn(DERIVED_NOREGISTER), base_deps, derived_props, 8)
    enumerators = rd.put(struct.pack('<QqQq', c['EKind::A'], 0, c['EKind::B'], 5))
    kind_params = rd.put(struct.pack('<QQQQQiIIB7x', 0, 0, c['EKind'], c['EKind'], enumerators, 2, 0x45, 0, 1))
    tint_vtable = rd.put(struct.pack('<QQ', fn(DESTRUCTOR), fn(TINT_CAPS)))
    packed_vtable = rd.put(struct.pack('<QQ', fn(DESTRUCTOR), fn(PACKED_CAPS)))
    tint_params = da.put(struct.pack('<QQQQQQQiII4x', 0, 0, fn(TINT_OPS), c['Tint'], 8, 4, tint_props, 2, 0x45, 0x1))
    packed_params = da.put(struct.pack('<QQQQQQQiII4x', 0, fn(CONSTRUCT_TINT), fn(PACKED_OPS), c['Packed'], 8, 4, 0,
                                       0, 0x45, 0x1))
    code = bytearray(b'\xcc' * (SLOT * 12))

    def lea(slot, at, reg, target):                    # lea rcx/rdx, [rip + target]
        va = fn(slot) + at
        code[SLOT * slot + at:SLOT * slot + at + 7] = b'\x48\x8d' + bytes([reg]) + struct.pack('<i', target - va - 7)
    for slot, name in ((BASE_CLASS, 'Base'), (DERIVED_CLASS, 'Derived')):
        lea(slot, 0, 0x0d, w['/Script/Test'])
        lea(slot, 7, 0x15, w[name])
        code[SLOT * slot + 14] = 0xc3
    code[SLOT * DERIVED_NOREGISTER:SLOT * DERIVED_NOREGISTER + 5] = b'\xe9' + struct.pack(
        '<i', fn(DERIVED_CLASS) - fn(DERIVED_NOREGISTER) - 5)
    for slot, target in ((CONSTRUCT_BASE, base_params), (CONSTRUCT_TINT, tint_params),
                         (CONSTRUCT_PACKED, packed_params), (CONSTRUCT_KIND, kind_params),
                         (TINT_OPS, tint_vtable), (PACKED_OPS, packed_vtable)):
        lea(slot, 0, 0x0d, target)
        code[SLOT * slot + 7] = 0xc3
    for slot, bits in ((TINT_CAPS, 0x2004), (PACKED_CAPS, 0x200c)):
        code[SLOT * slot:SLOT * slot + 7] = b'\x66\xc7\x42\x08' + struct.pack('<H', bits) + b'\xc3'
    code[SLOT * DESTRUCTOR] = 0xc3
    pdata = b''.join(struct.pack('<III', TEXT + SLOT * i, TEXT + SLOT * (i + 1), unwind - BASE) for i in range(12))
    return synth.pe_image(BASE, [('.text', TEXT, bytes(code), 0x60000020), ('.rdata', RDATA, bytes(rd.b), 0x40000040),
                                 ('.data', DATA, bytes(da.b), 0xC0000040), ('.pdata', PDATA, pdata, 0x40000040)],
                          {3: (PDATA, len(pdata))})


class Reflect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.dir, 'Test-Shipping.exe')
        with open(cls.exe, 'wb') as f:
            f.write(program())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def test_scan(self):
        d = reflect.scan(self.exe)
        self.assertEqual(sorted(d['classes']), ['/Script/Test.Base', '/Script/Test.Derived'])
        base, derived = d['classes']['/Script/Test.Base'], d['classes']['/Script/Test.Derived']
        self.assertIsNone(base['super'])
        self.assertEqual(derived['super'], '/Script/Test.Base')
        s = reflect.Schema(d)
        self.assertEqual([repr(p) for p in s.properties('Base')], ['Health:Int', 'Names:Array[Names:Name]'])
        self.assertEqual([repr(p) for p in s.properties('/Script/Test.Derived')],
                         ['Tint:Struct<Tint>', 'Mode:Enum<EKind>[UnderlyingType:Byte]',
                          'Lookup:Map[Lookup_Key:Str, Lookup:Int]', 'Owner:Object</Script/Test.Base>', 'Slots:Int*4'])
        self.assertEqual([(p.name, i) for p, i in s.schema('Derived')][-6:],     # own properties, then the super's
                         [('Slots', 0), ('Slots', 1), ('Slots', 2), ('Slots', 3), ('Health', 0), ('Names', 0)])
        self.assertEqual(d['structs']['Tint']['serializer'], False)
        self.assertEqual(d['structs']['Packed']['serializer'], True)
        self.assertEqual(s.struct_super('Packed'), 'Tint')
        self.assertEqual([repr(p) for p in s.properties('Tint', struct=True)], ['R:Float', 'Flag:Bool'])
        self.assertEqual(d['enums'], {'EKind': {'0': 'A', '5': 'B'}})
        self.assertEqual(s.enum_name('EKind', 5), 'B')

    def test_cache(self):
        cache = os.path.join(self.dir, 'cache')
        s = reflect.Schema.load(self.exe, cache)
        files = os.listdir(cache)
        self.assertEqual(len(files), 1)
        with open(os.path.join(cache, files[0])) as f:
            self.assertEqual(json.load(f)['version'], reflect.SCHEMA_VERSION)
        with mock.patch.object(reflect, 'scan', side_effect=AssertionError('scanned again')):
            again = reflect.Schema.load(self.exe, cache)          # from the cache
        self.assertEqual(sorted(again.classes), sorted(s.classes))
        with open(os.path.join(cache, 'schema-v0-1-2.json'), 'w') as f:
            f.write('{}')                                         # an older program's: removed on the next scan
        os.utime(self.exe, (1, 1))
        reflect.Schema.load(self.exe, cache)
        self.assertEqual(len(os.listdir(cache)), 1)


if __name__ == '__main__':
    unittest.main()
