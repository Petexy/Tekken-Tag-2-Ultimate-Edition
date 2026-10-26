"""CityHash64 and the Unreal ids made from it (tekken8/cityhash.py), on made-up inputs.

    python3 -m unittest discover tools/characters/tests
"""
import ctypes
import glob
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.tekken8 import cityhash                 # noqa: E402

# CityHash64 v1.1 of inputs that take each length path (0, 1-3, 4-7, 8-16, 17-32, 33-64, > 64 bytes), as the
# system's Abseil library (absl::hash_internal::CityHash64, CityHash 1.1) computes them
KNOWN = [(b'', 0x9ae16a3b2f90404f), (b'a', 0xb3454265b6df75e3), (b'abc', 0x24a5b3a074e7f369),
         (b'abcdefgh', 0xfee9d22990c82909), (b'0123456789abcdef0', 0x6deb36b4a021a909),
         (b'x' * 40, 0xf6c8e2c2a453ffe5), (b'y' * 100, 0x7a9c72386a250d6), (b'z' * 200, 0x47fe0d06cbd4f33e)]


def _abseil():
    """Abseil's CityHash64 through ctypes, when the system has the library (else None)."""
    for path in sorted(glob.glob('/usr/lib*/libabsl_city.so*') + glob.glob('/usr/lib/*/libabsl_city.so*')):
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        with open(path, 'rb') as f:
            data = f.read()
        i = data.find(b'13hash_internal10CityHash64EPKcm')
        if i < 0:
            continue
        start = data.rfind(b'_ZN4absl', 0, i)
        name = data[start:i + len(b'13hash_internal10CityHash64EPKcm')].decode()
        try:
            fn = getattr(lib, name)
        except AttributeError:
            continue
        fn.restype = ctypes.c_uint64
        fn.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        return fn
    return None


class CityHash(unittest.TestCase):
    def test_known_values(self):
        for data, h in KNOWN:
            self.assertEqual(cityhash.cityhash64(data), h, data[:8])

    def test_against_abseil(self):
        fn = _abseil()
        if fn is None:
            self.skipTest('no libabsl_city on this system')
        rnd = random.Random(5)
        for n in list(range(0, 200)) + [rnd.randrange(200, 3000) for _ in range(50)]:
            data = bytes(rnd.randrange(256) for _ in range(n))
            self.assertEqual(cityhash.cityhash64(data), fn(data, n), n)

    def test_ids(self):
        name = '/Game/Character/Item/Example/SK_Example'
        self.assertEqual(cityhash.package_id(name), cityhash.cityhash64(name.lower().encode('utf-16-le')))
        self.assertEqual(cityhash.package_id(name), cityhash.package_id(name.upper()))
        sid = cityhash.script_object_id('/Script/Engine.SkeletalMesh')
        self.assertEqual(sid >> 62, 1)                     # script import
        self.assertEqual(sid & ((1 << 62) - 1), cityhash.cityhash64('/script/engine/skeletalmesh'.encode('utf-16-le'))
                         & ((1 << 62) - 1))
        self.assertEqual(cityhash.public_export_hash('Obj:Sub'), cityhash.cityhash64('obj/sub'.encode('utf-16-le')))
        self.assertEqual(cityhash.public_export_hash('Obj.Sub'), cityhash.public_export_hash('obj:sub'))


if __name__ == '__main__':
    unittest.main()
