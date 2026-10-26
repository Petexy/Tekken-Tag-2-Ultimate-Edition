"""tekken8/oodle.c (running the game's own decompressor natively) on a made-up program: a tiny PE image whose
"OodleLZ_Decompress" copies its input through the memcpy import, calls another import when asked to (the trap),
faults when asked to, and reads a pointer that a base relocation fixes. Each case runs in a child process (the
library maps one image per process).

    python3 -m unittest discover tools/characters/tests
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char import native                           # noqa: E402

BASE = 0x200000000                                    # the made-up program's preferred base (free in a test)
TEXT, RDATA, DATA, PDATA, RELOC = 0x1000, 0x2000, 0x3000, 0x4000, 0x5000
NEEDLE = b'oo2::OodleLZ_Decompress\0'
CHILD = r'''
import ctypes, json, sys
lib = ctypes.CDLL(sys.argv[1])
lib.oodle8_open.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
lib.oodle8_decompress.restype = ctypes.c_ssize_t
lib.oodle8_decompress.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_ssize_t]
lib.oodle8_error.restype = ctypes.c_char_p
lib.oodle8_function_rva.restype = ctypes.c_uint64
lib.oodle8_image_base.restype = ctypes.c_uint64
out = {}
if sys.argv[3] == 'blocked':
    libc = ctypes.CDLL(None)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
    out['blocker'] = libc.mmap(int(sys.argv[4]), 4096, 3, 0x22 | 0x100000, -1, 0)
err = ctypes.create_string_buffer(256)
out['open'] = lib.oodle8_open(sys.argv[2].encode(), err, 256)
out['open_error'] = err.value.decode()
out['rva'] = lib.oodle8_function_rva()
out['base'] = lib.oodle8_image_base()
data = b'made-up compressed bytes'
buf = ctypes.create_string_buffer(len(data))
out['copy'] = lib.oodle8_decompress(data, len(data), buf, len(data))
out['copied'] = buf.raw == data
out['trap'] = lib.oodle8_decompress(b'x', 1, buf, len(data))
out['trap_error'] = lib.oodle8_error().decode()
out['fault'] = lib.oodle8_decompress(b'xy', 2, buf, len(data))
out['fault_error'] = lib.oodle8_error().decode()
out['again'] = lib.oodle8_decompress(data, len(data), buf, len(data))
print(json.dumps(out))
'''


def _rel32(at, target, size):
    return struct.pack('<i', target - (at + size))


def program():
    """The made-up PE image (bytes) and the RVA its decompressor starts at."""
    needle = RDATA
    rdata = bytearray(NEEDLE)
    rdata += bytes(-len(rdata) % 8)
    unwind_a = RDATA + len(rdata)
    rdata += b'\x01\x00\x00\x00'
    unwind_b = RDATA + len(rdata)
    rdata += bytes([0x01 | (4 << 3), 0, 0, 0]) + struct.pack('<III', TEXT, TEXT + 0x60, unwind_a)  # chained
    rdata += bytes(-len(rdata) % 8)
    hint_memcpy = RDATA + len(rdata)
    rdata += b'\0\0memcpy\0\0'
    hint_sleep = RDATA + len(rdata)
    rdata += b'\0\0Sleep\0'
    dll = RDATA + len(rdata)
    rdata += b'TEST.dll\0'
    rdata += bytes(-len(rdata) % 8)
    ilt = RDATA + len(rdata)
    rdata += struct.pack('<QQQ', hint_memcpy, hint_sleep, 0)
    iat = RDATA + len(rdata)
    rdata += struct.pack('<QQQ', hint_memcpy, hint_sleep, 0)
    descriptors = RDATA + len(rdata)
    rdata += struct.pack('<IIIII', ilt, 0, 0, dll, iat) + bytes(20)
    data = struct.pack('<Q', BASE + needle)               # an absolute pointer: fixed by the relocation
    pdata = struct.pack('<6I', TEXT, TEXT + 0x60, unwind_a, TEXT + 0x60, TEXT + 0x68, unwind_b)
    reloc = struct.pack('<IIHH', DATA, 12, 0xA000, 0)
    code = bytearray()

    def emit(b):
        code.extend(b)
    emit(b'\x48\x83\xfa\x01\x75\x06')                     # cmp rdx, 1; jne +6
    emit(b'\xff\x15' + _rel32(TEXT + len(code), iat + 8, 6))      # call [Sleep]: the trap
    emit(b'\x48\x83\xfa\x02\x75\x08')                     # cmp rdx, 2; jne +8
    emit(b'\x48\x8b\x04\x25\x00\x00\x00\x00')             # mov rax, [0]: a fault
    emit(b'\x48\x8b\x05' + _rel32(TEXT + len(code), DATA, 7))     # mov rax, [the pointer]
    emit(b'\x0f\xb6\x00')                                 # movzx eax, byte [rax]
    emit(b'\x53\x48\x83\xec\x20\x4c\x89\xcb')             # push rbx; sub rsp, 32; mov rbx, r9
    emit(b'\x48\x89\xc8\x4c\x89\xc1\x49\x89\xd0\x48\x89\xc2')     # memcpy(raw, comp, compLen)
    emit(b'\xff\x15' + _rel32(TEXT + len(code), iat, 6))          # call [memcpy]
    emit(b'\x48\x89\xd8\x48\x83\xc4\x20\x5b\xc3')         # return rawLen
    assert len(code) <= 0x60
    code += b'\xcc' * (0x60 - len(code))
    emit(b'\x48\x8d\x05' + _rel32(TEXT + len(code), needle, 7) + b'\xc3')     # the fragment naming the function
    image = synth.pe_image(BASE, [('.text', TEXT, bytes(code), 0x60000020), ('.rdata', RDATA, bytes(rdata), 0x40000040),
                                  ('.data', DATA, data, 0xC0000040), ('.pdata', PDATA, pdata, 0x40000040),
                                  ('.reloc', RELOC, reloc, 0x42000040)],
                           {1: (descriptors, 40), 3: (PDATA, len(pdata)), 5: (RELOC, len(reloc))})
    return image, TEXT


class Oodle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if native.compiler() is None:
            raise unittest.SkipTest('no C compiler')
        cls.dir = tempfile.mkdtemp()
        cls.lib = native.build('oodle', os.path.join('tekken8', 'oodle.c'), libs=('-lpthread',),
                               cache=os.path.join(cls.dir, 'native'))
        cls.exe = os.path.join(cls.dir, 'Test-Shipping.exe')
        image, cls.rva = program()
        with open(cls.exe, 'wb') as f:
            f.write(image)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def run_child(self, mode, exe=None):
        r = subprocess.run([sys.executable, '-c', CHILD, self.lib, exe or self.exe, mode, str(BASE)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def check(self, out):
        self.assertEqual(out['open'], 0, out['open_error'])
        self.assertEqual(out['rva'], self.rva)                 # found through the string, .pdata and the chain
        self.assertEqual(out['copy'], 24)
        self.assertTrue(out['copied'])
        self.assertEqual(out['trap'], -3)                      # OODLE8_IMPORT, not the end of the process
        self.assertIn('TEST.dll!Sleep', out['trap_error'])
        self.assertEqual(out['fault'], -4)                     # OODLE8_FAULT
        self.assertIn('signal 11', out['fault_error'])
        self.assertEqual(out['again'], 24)

    def test_preferred_base(self):
        out = self.run_child('free')
        self.check(out)
        self.assertEqual(out['base'], BASE)

    def test_relocated(self):
        out = self.run_child('blocked')
        self.assertEqual(out['blocker'], BASE)
        self.check(out)                                        # the pointer read works only when relocated
        self.assertNotEqual(out['base'], BASE)

    def test_not_the_game(self):
        other = os.path.join(self.dir, 'other.exe')
        image, _ = program()
        with open(other, 'wb') as f:
            f.write(image.replace(NEEDLE, b'xx2::OodleLZ_Decompress\0'))
        out = self.run_child('free', other)
        self.assertEqual(out['open'], -1)
        self.assertIn('no Oodle decompressor', out['open_error'])
        self.assertEqual(out['copy'], -1)                      # OODLE8_NOT_OPEN


if __name__ == '__main__':
    unittest.main()
