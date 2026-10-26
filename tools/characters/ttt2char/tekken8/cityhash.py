"""CityHash64 (version 1.1, as Unreal Engine's Core uses it) and the Unreal ids Tekken 8 builds from it.

CityHash64 hashes a byte string to 64 bits; inputs of 0-16, 17-32, 33-64 and longer bytes take different paths
(the longer ones run over 64-byte chunks with 56 bytes of state). Unreal Engine 5 names packages and script
objects by it:
    FPackageId (a package's chunk id in the IoStore containers, its id in other packages' import lists):
        CityHash64 of the package name ('/Game/Character/...'; Tekken 8's '/Game/' is Polaris/Content/) in lower
        case as UTF-16LE
    FPackageObjectIndex of a script object ('/Script/Engine.SkeletalMesh', the classes and their defaults objects
        the exe defines): the path in lower case with '.' and ':' as '/', UTF-16LE, CityHash64, the top two bits
        replaced by the index type 1 (script import)
    a public export's hash (FExportMapEntry.PublicExportHash, what an import of it names): CityHash64 of its path
        below the package ('obj' or 'obj/sub') in lower case as UTF-16LE

Written for this project from the algorithm's description (no third-party code); checked against Tekken 8's own
chunk ids, its 42504 script objects and the public export hashes of its packages.
"""
import struct

M64 = (1 << 64) - 1
K0 = 0xc3a5c85c97cb3127
K1 = 0xb492b66fbe98f273
K2 = 0x9ae16a3b2f90404f              # also the hash of empty input
KMUL = 0x9ddfea08eb382d69            # Hash128to64's multiplier
INDEX_SCRIPT = 1 << 62               # FPackageObjectIndex type bits: 1 = script import
INDEX_MASK = (1 << 62) - 1


# ---------------------------------------------------------------------------------------------------- helpers
def _f64(s, i):
    return struct.unpack_from('<Q', s, i)[0]


def _f32(s, i):
    return struct.unpack_from('<I', s, i)[0]


def _rot(v, r):
    return v if r == 0 else ((v >> r) | (v << (64 - r))) & M64


def _shift_mix(v):
    return v ^ (v >> 47)


def _bswap(v):
    return int.from_bytes(v.to_bytes(8, 'little'), 'big')


def _len16(u, v, mul=KMUL):
    a = ((u ^ v) * mul) & M64
    a ^= a >> 47
    b = ((v ^ a) * mul) & M64
    b ^= b >> 47
    return (b * mul) & M64


def _len0to16(s, n):
    if n >= 8:
        mul = K2 + n * 2
        a = (_f64(s, 0) + K2) & M64
        b = _f64(s, n - 8)
        c = (_rot(b, 37) * mul + a) & M64
        d = ((_rot(a, 25) + b) * mul) & M64
        return _len16(c, d, mul)
    if n >= 4:
        mul = K2 + n * 2
        return _len16(n + (_f32(s, 0) << 3), _f32(s, n - 4), mul)
    if n > 0:
        y = s[0] + (s[n >> 1] << 8)
        z = n + (s[n - 1] << 2)
        return (_shift_mix(((y * K2) ^ (z * K0)) & M64) * K2) & M64
    return K2


def _len17to32(s, n):
    mul = K2 + n * 2
    a = (_f64(s, 0) * K1) & M64
    b = _f64(s, 8)
    c = (_f64(s, n - 8) * mul) & M64
    d = (_f64(s, n - 16) * K2) & M64
    return _len16((_rot((a + b) & M64, 43) + _rot(c, 30) + d) & M64, (a + _rot((b + K2) & M64, 18) + c) & M64, mul)


def _len33to64(s, n):
    mul = K2 + n * 2
    a = (_f64(s, 0) * K2) & M64
    b = _f64(s, 8)
    c = _f64(s, n - 24)
    d = _f64(s, n - 32)
    e = (_f64(s, 16) * K2) & M64
    f = (_f64(s, 24) * 9) & M64
    g = _f64(s, n - 8)
    h = (_f64(s, n - 16) * mul) & M64
    u = (_rot((a + g) & M64, 43) + (_rot(b, 30) + c) * 9) & M64
    v = ((((a + g) & M64) ^ d) + f + 1) & M64
    w = (_bswap(((u + v) * mul) & M64) + h) & M64
    x = (_rot((e + f) & M64, 42) + c) & M64
    y = ((_bswap(((v + w) * mul) & M64) + g) * mul) & M64
    z = (e + f + c) & M64
    a = (_bswap(((x + z) * mul + y) & M64) + b) & M64
    b = (_shift_mix(((z + a) * mul + d + h) & M64) * mul) & M64
    return (b + x) & M64


def _weak32(s, i, a, b):
    """WeakHashLen32WithSeeds over the 32 bytes at s[i:]."""
    w, x, y, z = struct.unpack_from('<4Q', s, i)
    a = (a + w) & M64
    b = _rot((b + a + z) & M64, 21)
    c = a
    a = (a + x + y) & M64
    b = (b + _rot(a, 44)) & M64
    return (a + z) & M64, (b + c) & M64


# ---------------------------------------------------------------------------------------------------- hashes
def cityhash64(data):
    """CityHash64 v1.1 of bytes."""
    s = bytes(data)
    n = len(s)
    if n <= 16:
        return _len0to16(s, n)
    if n <= 32:
        return _len17to32(s, n)
    if n <= 64:
        return _len33to64(s, n)
    x = _f64(s, n - 40)
    y = (_f64(s, n - 16) + _f64(s, n - 56)) & M64
    z = _len16((_f64(s, n - 48) + n) & M64, _f64(s, n - 24))
    v = _weak32(s, n - 64, n, z)
    w = _weak32(s, n - 32, (y + K1) & M64, x)
    x = (x * K1 + _f64(s, 0)) & M64
    left = (n - 1) & ~63
    p = 0
    while True:
        x = (_rot((x + y + v[0] + _f64(s, p + 8)) & M64, 37) * K1) & M64
        y = (_rot((y + v[1] + _f64(s, p + 48)) & M64, 42) * K1) & M64
        x ^= w[1]
        y = (y + v[0] + _f64(s, p + 40)) & M64
        z = (_rot((z + w[0]) & M64, 33) * K1) & M64
        v = _weak32(s, p, (v[1] * K1) & M64, (x + w[0]) & M64)
        w = _weak32(s, p + 32, (z + w[1]) & M64, (y + _f64(s, p + 16)) & M64)
        z, x = x, z
        p += 64
        left -= 64
        if left == 0:
            break
    return _len16((_len16(v[0], w[0]) + _shift_mix(y) * K1 + z) & M64, (_len16(v[1], w[1]) + x) & M64)


def package_id(name):
    """FPackageId of a package name such as '/Game/Character/Item/...' (any case)."""
    return cityhash64(name.lower().encode('utf-16-le'))


def script_object_id(path):
    """FPackageObjectIndex of a script object such as '/Script/Engine.SkeletalMesh' (any case)."""
    p = path.lower().replace('.', '/').replace(':', '/')
    return (cityhash64(p.encode('utf-16-le')) & INDEX_MASK) | INDEX_SCRIPT


def public_export_hash(relative):
    """FExportMapEntry.PublicExportHash of an object below its package: 'obj', 'obj.sub' or 'obj:sub' (any case)."""
    p = relative.lower().replace('.', '/').replace(':', '/').lstrip('/')
    return cityhash64(p.encode('utf-16-le'))
