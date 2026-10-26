"""CityHash32 (version 1.1): the 32-bit string hash Tekken 8 names its moves and animations by.

CityHash32 hashes a byte string to 32 bits; inputs of 0-4, 5-12, 13-24 and longer bytes take different paths
(the longer ones run over 20-byte chunks with three words of state, then mix). The moveset (tekken8/motbin.py)
keeps three such keys per move instead of names:
    name key  CityHash32 of the move's name, e.g. 'dwDWN_00U' or 'Zbr_sKAM00_' (case as written, no NUL)
    move key  CityHash32 of the fighter's code in upper case, '_' and the name ('ZBR_Zbr_sKAM00_'): a move's
              identity across fighters (other fighters' movesets and the command list refer to moves by it)
    anim key  CityHash32 of the move's animation name
The same function keys the game's own file lookups (its program's string hash); names are found by hashing
candidates (tekken8/movenames.py), many at a time with city32_many.

Written for this project from the algorithm's description (no third-party code); checked against the hash
function in Tekken 8's program (called natively in the research, 415 random strings) and against Abseil's
CityHash32 (tests).
"""
import struct

import numpy as np

M32 = 0xFFFFFFFF
C1 = 0xcc9e2d51
C2 = 0x1b873593
MIX = 0xe6546b64                     # the Murmur3 step constant: h = h * 5 + MIX
FMIX1, FMIX2 = 0x85ebca6b, 0xc2b2ae35
BLOCK = 20                           # bytes per round of the long path


# ---------------------------------------------------------------------------------------------------- one string
def _rot(v, r):
    """Rotate right (CityHash's Rotate32)."""
    return ((v >> r) | (v << (32 - r))) & M32


def _fmix(h):
    h ^= h >> 16
    h = (h * FMIX1) & M32
    h ^= h >> 13
    h = (h * FMIX2) & M32
    return h ^ (h >> 16)


def _mur(a, h):
    a = (_rot((a * C1) & M32, 17) * C2) & M32
    return (_rot(h ^ a, 19) * 5 + MIX) & M32


def _f32(s, i):
    return struct.unpack_from('<I', s, i)[0]


def _bswap(v):
    return int.from_bytes(v.to_bytes(4, 'little'), 'big')


def city32(data):
    """CityHash32 v1.1 of bytes (a str is hashed as Latin-1, as the game's names are plain ASCII)."""
    s = data.encode('latin1') if isinstance(data, str) else bytes(data)
    n = len(s)
    if n <= 4:
        b, c = 0, 9
        for x in s:
            b = (b * C1 + (x - 256 if x >= 128 else x)) & M32       # the bytes are signed chars
            c ^= b
        return _fmix(_mur(b, _mur(n, c)))
    if n <= 12:
        a, b, c = (n + _f32(s, 0)) & M32, (n * 5 + _f32(s, n - 4)) & M32, (9 + _f32(s, (n >> 1) & 4)) & M32
        return _fmix(_mur(c, _mur(b, _mur(a, n * 5))))
    if n <= 24:
        h = n
        for o in ((n >> 1) - 4, 4, n - 8, n >> 1, 0, n - 4):
            h = _mur(_f32(s, o), h)
        return _fmix(h)

    def k(i):
        return (_rot((_f32(s, i) * C1) & M32, 17) * C2) & M32
    h, g = n, (C1 * n) & M32
    f = g
    h = (_rot(h ^ k(n - 4), 19) * 5 + MIX) & M32
    h = (_rot(h ^ k(n - 16), 19) * 5 + MIX) & M32
    g = (_rot(g ^ k(n - 8), 19) * 5 + MIX) & M32
    g = (_rot(g ^ k(n - 12), 19) * 5 + MIX) & M32
    f = (_rot((f + k(n - 20)) & M32, 19) * 5 + MIX) & M32
    for p in range(0, (n - 1) // BLOCK * BLOCK, BLOCK):
        a0, a1, a2, a3, a4 = k(p), _f32(s, p + 4), k(p + 8), k(p + 12), _f32(s, p + 16)
        h = (_rot(h ^ a0, 18) * 5 + MIX) & M32
        f = (_rot((f + a1) & M32, 19) * C1) & M32
        g = (_rot((g + a2) & M32, 18) * 5 + MIX) & M32
        h = (_rot(h ^ ((a3 + a1) & M32), 19) * 5 + MIX) & M32
        g = (_bswap(g ^ a4) * 5) & M32
        h = _bswap((h + a4 * 5) & M32)
        f = (f + a0) & M32
        f, h, g = g, f, h                                           # PERMUTE3(f, h, g)
    g = (_rot((_rot(g, 11) * C1) & M32, 17) * C1) & M32
    f = (_rot((_rot(f, 11) * C1) & M32, 17) * C1) & M32
    h = (_rot((_rot((h + g) & M32, 19) * 5 + MIX) & M32, 17) * C1) & M32
    return (_rot((_rot((h + f) & M32, 19) * 5 + MIX) & M32, 17) * C1) & M32


# ---------------------------------------------------------------------------------------------------- many strings
_U = np.uint32


def _vrot(v, r):
    return (v >> _U(r)) | (v << _U(32 - r))


def _vfmix(h):
    h = h ^ (h >> _U(16))
    h = h * _U(FMIX1)
    h = h ^ (h >> _U(13))
    h = h * _U(FMIX2)
    return h ^ (h >> _U(16))


def _vmur(a, h):
    a = _vrot(a * _U(C1), 17) * _U(C2)
    return _vrot(h ^ a, 19) * _U(5) + _U(MIX)


def _vbswap(v):
    return v.byteswap()


def _hash_rows(buf):
    """CityHash32 of every row of a (count, n) uint8 array (all strings of length n)."""
    count, n = buf.shape
    w = buf.astype(np.uint32)

    def f(i):
        return w[:, i] | (w[:, i + 1] << _U(8)) | (w[:, i + 2] << _U(16)) | (w[:, i + 3] << _U(24))

    def k(i):
        return _vrot(f(i) * _U(C1), 17) * _U(C2)
    with np.errstate(over='ignore'):
        if n <= 4:
            b, c = np.zeros(count, np.uint32), np.full(count, 9, np.uint32)
            for i in range(n):
                b = b * _U(C1) + buf[:, i].view(np.int8).astype(np.int32).view(np.uint32)
                c = c ^ b
            return _vfmix(_vmur(b, _vmur(np.full(count, n, np.uint32), c)))
        if n <= 12:
            a, b, c = _U(n) + f(0), _U(n * 5) + f(n - 4), _U(9) + f((n >> 1) & 4)
            return _vfmix(_vmur(c, _vmur(b, _vmur(a, np.full(count, n * 5, np.uint32)))))
        if n <= 24:
            h = np.full(count, n, np.uint32)
            for o in ((n >> 1) - 4, 4, n - 8, n >> 1, 0, n - 4):
                h = _vmur(f(o), h)
            return _vfmix(h)
        h = np.full(count, n, np.uint32)
        g = np.full(count, (C1 * n) & M32, np.uint32)
        fh = g.copy()
        h = _vrot(h ^ k(n - 4), 19) * _U(5) + _U(MIX)
        h = _vrot(h ^ k(n - 16), 19) * _U(5) + _U(MIX)
        g = _vrot(g ^ k(n - 8), 19) * _U(5) + _U(MIX)
        g = _vrot(g ^ k(n - 12), 19) * _U(5) + _U(MIX)
        fh = _vrot(fh + k(n - 20), 19) * _U(5) + _U(MIX)
        for p in range(0, (n - 1) // BLOCK * BLOCK, BLOCK):
            a0, a1, a2, a3, a4 = k(p), f(p + 4), k(p + 8), k(p + 12), f(p + 16)
            h = _vrot(h ^ a0, 18) * _U(5) + _U(MIX)
            fh = _vrot(fh + a1, 19) * _U(C1)
            g = _vrot(g + a2, 18) * _U(5) + _U(MIX)
            h = _vrot(h ^ (a3 + a1), 19) * _U(5) + _U(MIX)
            g = _vbswap(g ^ a4) * _U(5)
            h = _vbswap(h + a4 * _U(5))
            fh = fh + a0
            fh, h, g = g, fh, h
        g = _vrot(_vrot(g, 11) * _U(C1), 17) * _U(C1)
        fh = _vrot(_vrot(fh, 11) * _U(C1), 17) * _U(C1)
        h = _vrot(_vrot(h + g, 19) * _U(5) + _U(MIX), 17) * _U(C1)
        return _vrot(_vrot(h + fh, 19) * _U(5) + _U(MIX), 17) * _U(C1)


def city32_many(strings):
    """CityHash32 of each of a list of byte strings -> uint32 array in the same order (vectorised by length)."""
    out = np.zeros(len(strings), np.uint32)
    groups = {}
    for i, s in enumerate(strings):
        groups.setdefault(len(s), []).append(i)
    for n, idx in groups.items():
        if n == 0:
            out[idx] = city32(b'')
            continue
        buf = np.frombuffer(b''.join(strings[i] for i in idx), np.uint8).reshape(len(idx), n)
        out[idx] = _hash_rows(buf)
    return out


def city32_rows(buf):
    """CityHash32 of every row of a (count, n) uint8 array: equal-length strings already side by side."""
    buf = np.ascontiguousarray(buf, np.uint8)
    if buf.shape[1] == 0:
        return np.full(buf.shape[0], city32(b''), np.uint32)
    return _hash_rows(buf)
