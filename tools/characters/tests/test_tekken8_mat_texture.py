"""Tekken 8 textures (tekken8/texture.py) on made-up Texture2D packages: platform data, inline and .ubulk mips, the
mip chosen for a size (only its bytes read), the sRGB flag.

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char.tekken8 import cityhash, reflect, texture, zen   # noqa: E402

TEXTURE = '/Script/Engine.Texture2D'
CLS = cityhash.script_object_id(TEXTURE)
SCHEMA = {'classes': {TEXTURE: {'name': 'Texture2D', 'super': None, 'flags': 0, 'props': [
    {'n': 'SRGB', 't': 'Bool'}, {'n': 'LODGroup', 't': 'Byte'}]}}, 'structs': {}, 'enums': {}}
NAMES = ['/Game/T/T_Test', 'T_Test', 'None', 'PF_B8G8R8A8']
PID = 77


class Scripts:
    def script_path(self, v):
        return TEXTURE if v == CLS else None


class Store:
    """What Texture2D asks of a store (file_path, package_id, package_header, read, chunk, resolver, schema); reads
    of the package file and chunks are recorded."""

    FILE = 'Polaris/Content/T/T_Test.uasset'

    def __init__(self):
        self.schema = reflect.Schema(SCHEMA)
        self.resolver = Scripts()
        self.chunks = {}
        self.data = b''
        self.reads = []

    def file_path(self, path):
        return self.FILE if path in (NAMES[0], NAMES[0] + '.T_Test', self.FILE) else None

    def package_id(self, path):
        return PID if self.file_path(path) else None

    def package_header(self, pid):
        return self.data[:zen.HEADER_PEEK] if pid == PID else None

    def read(self, path, offset=0, size=None):
        assert path == self.FILE
        self.reads.append(('file', offset, size))
        return self.data[offset:] if size is None else self.data[offset:offset + size]

    def chunk(self, pid, ctype, index=0, offset=0, size=None):
        self.reads.append((ctype, offset, size))
        data = self.chunks[(pid, ctype)]
        return data[offset:offset + size]

    def payload_reads(self, at_least):
        """The recorded reads of at least that many bytes."""
        return [r for r in self.reads if (r[2] or 0) >= at_least]


def image(w, h, seed):
    """BGRA bytes of a w x h image whose texels say where they are."""
    a = np.zeros((h, w, 4), np.uint8)
    a[..., 0] = seed
    a[..., 1] = np.arange(w)[None]
    a[..., 2] = np.arange(h)[:, None]
    a[..., 3] = 200
    return a.tobytes()


def texture_package(store, mips, srgb=None, separate=(), fmt='PF_B8G8R8A8', bad_offset=False):
    """A Texture2D package; mips: [(w, h)], their bytes from image(); separate: the mips kept in the .ubulk."""
    if srgb is None:
        props = struct.pack('<H', 0x100)                                     # no properties stored
    else:
        props = struct.pack('<H', 0x100 | (1 << 9) | (0 if srgb else 0x80)) + (b'' if srgb is False else b'')
        props += b'\x01' if srgb is False else b'\x01'                      # SRGB stored zero / one
        if srgb is False:
            props = struct.pack('<H', 0x100 | 0x80 | (1 << 9)) + b'\x01'    # the zero mask: SRGB = False
    d = bytearray(props)
    d += struct.pack('<I', 0) + b'\0' * 4 + struct.pack('<I', 1)            # GUID flag, strip flags, cooked
    d += struct.pack('<II', NAMES.index(fmt), 0)
    skip_at = len(d)
    d += struct.pack('<q', 0) + b'\0' * 16
    d += struct.pack('<iiI', mips[0][0], mips[0][1], 1)
    f = fmt.encode() + b'\0'
    d += struct.pack('<i', len(f)) + f + struct.pack('<ii', 0, len(mips))
    bulk, ubulk = [], b''
    for i, (w, h) in enumerate(mips):
        payload = image(w, h, i)
        d += struct.pack('<i', len(bulk))
        if i in separate:
            bulk.append((len(ubulk), len(payload), zen.BULK_SEPARATE | 0x1))
            ubulk += payload
        else:
            bulk.append((len(d) + (4 if bad_offset else 0), len(payload), zen.BULK_INLINE | 0x8))
            d += payload
        d += struct.pack('<iii', w, h, 1)
    d += struct.pack('<I', 0)                                               # not virtual
    struct.pack_into('<q', d, skip_at, len(d) - skip_at)
    d += struct.pack('<II', NAMES.index('None'), 0)
    # (the builder takes its names from the exports: the names the texture's data uses ride on empty ones)
    data = synth.zen_package(NAMES[0], [{'name': 'T_Test', 'cls': synth.script_index(CLS), 'data': bytes(d)},
                                        {'name': 'None', 'cls': synth.NULL, 'data': b''},
                                        {'name': 'PF_B8G8R8A8', 'cls': synth.NULL, 'data': b''}], bulk=bulk)
    store.data = data
    if ubulk:
        store.chunks[(PID, zen.CHUNK_BULK)] = ubulk
    return data


class Textures(unittest.TestCase):
    def test_inline_mips(self):
        s = Store()
        texture_package(s, [(8, 4), (4, 2), (2, 1)])
        t = texture.Texture2D(s, '/Game/T/T_Test')
        self.assertEqual((t.pixel_format, t.width, t.height), ('PF_B8G8R8A8', 8, 4))
        self.assertEqual([(m.width, m.height) for m in t.mips], [(8, 4), (4, 2), (2, 1)])
        self.assertTrue(t.srgb)                                  # not stored: the class default
        top = t.decode()
        self.assertEqual(top.shape, (4, 8, 4))
        self.assertEqual(tuple(top[3, 5]), (3, 5, 0, 200))      # B8G8R8A8 -> RGBA
        self.assertEqual(t.decode(4).shape, (2, 4, 4))          # the largest mip at most 4 on its longest side
        self.assertEqual(t.decode(7).shape, (2, 4, 4))
        self.assertEqual(t.decode(1).shape, (1, 2, 4))          # none that small: the smallest
        self.assertEqual(t.level(None), 0)
        self.assertFalse([r for r in s.reads if r[0] != 'file'])

    def test_only_the_mip_decoded_is_read(self):
        s = Store()
        texture_package(s, [(128, 128), (64, 64), (32, 32)])
        t = texture.Texture2D(s, '/Game/T/T_Test.T_Test')
        top, mid = 128 * 128 * 4, 64 * 64 * 4
        self.assertEqual(s.payload_reads(mid), [])               # the parse skips over the payloads
        a = t.decode(64)
        self.assertEqual((a.shape, int(a[0, 0, 2])), ((64, 64, 4), 1))   # mip 1 (its seed is in red)
        self.assertEqual(s.payload_reads(mid), [('file', t.export.offset + t.mips[1].bulk.offset, mid)])
        self.assertEqual(int(t.decode()[0, 0, 2]), 0)
        self.assertEqual(len(s.payload_reads(top)), 1)
        self.assertEqual(int(t.decode(32)[5, 7, 1]), 7)

    def test_ubulk_mip_read_alone(self):
        s = Store()
        texture_package(s, [(8, 8), (4, 4), (2, 2)], separate=(0, 1))
        t = texture.Texture2D(s, '/Game/T/T_Test')
        a = t.decode(4)
        self.assertEqual(a.shape, (4, 4, 4))
        self.assertEqual(int(a[0, 0, 2]), 1)                    # mip 1's seed (in red after the swap)
        bulk = [r for r in s.reads if r[0] != 'file']
        self.assertEqual(bulk, [(zen.CHUNK_BULK, 8 * 8 * 4, 4 * 4 * 4)])   # its bytes only
        self.assertEqual(t.decode(2).shape, (2, 2, 4))          # inline
        self.assertEqual(len([r for r in s.reads if r[0] != 'file']), 1)

    def test_srgb_zero(self):
        s = Store()
        texture_package(s, [(4, 4)], srgb=False)
        self.assertFalse(texture.Texture2D(s, '/Game/T/T_Test').srgb)

    def test_errors(self):
        s = Store()
        texture_package(s, [(4, 4)], bad_offset=True)
        with self.assertRaises(zen.ParseError):
            texture.Texture2D(s, '/Game/T/T_Test')
        texture_package(s, [(4, 4)], fmt='None')
        with self.assertRaises(zen.ParseError):                 # no platform data
            texture.Texture2D(s, '/Game/T/T_Test')
        with self.assertRaises(KeyError):
            texture.Texture2D(s, '/Game/T/T_Other')


if __name__ == '__main__':
    unittest.main()
