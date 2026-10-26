"""Unit tests of ttt2char.tekken8's animation side (panm.py, anmbin.py, anim.py) on made-up data: PANM clips,
animation banks and a fighter skeleton written here as Tekken 8 lays them out (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_anim.py
"""
import os
import struct
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from ttt2char import InputError  # noqa: E402
from ttt2char.convert import retarget as RT  # noqa: E402
from ttt2char.tekken8 import anim as T8, anmbin, panm  # noqa: E402
from ttt2char.ttt2 import animation  # noqa: E402
import test_retarget as TR  # noqa: E402


# ------------------------------------------------------------------------------------------------ FlatBuffers
class Table:
    """fields {k: value}: ('B' | 'H' | 'I' | 'f', number), str, [objects], or a Table."""

    def __init__(self, **fields):
        self.fields = {int(k[1:]): v for k, v in fields.items()}


def flatbuffer(root, ident):
    """A FlatBuffers buffer (no schema): root offset, identifier, then the objects, parents before children (every
    offset points forward; each table's vtable right before it)."""
    b = bytearray(8)
    b[4:8] = ident

    def put(obj):
        while len(b) % 4:
            b.append(0)
        at = len(b)
        if isinstance(obj, str):
            s = obj.encode()
            b.extend(struct.pack('<I', len(s)) + s + b'\0')
            return at
        if isinstance(obj, list):
            b.extend(struct.pack('<I', len(obj)) + bytes(4 * len(obj)))
            for i, o in enumerate(obj):
                slot = at + 4 + 4 * i
                struct.pack_into('<I', b, slot, put(o) - slot)
            return at
        keys = sorted(obj.fields)
        n = keys[-1] + 1 if keys else 0
        vt = at
        size = 4 + 4 * len(keys)
        b.extend(struct.pack('<HH', 4 + 2 * n, size) + bytes(2 * n))
        while len(b) % 4:
            b.append(0)
        t = len(b)
        struct.pack_into('<HH', b, vt, 4 + 2 * n, size)
        b.extend(struct.pack('<i', t - vt))
        later = []
        for j, k in enumerate(keys):
            pos = t + 4 + 4 * j
            struct.pack_into('<H', b, vt + 4 + 2 * k, pos - t)
            v = obj.fields[k]
            if isinstance(v, tuple):
                b.extend(struct.pack('<' + v[0], v[1]).ljust(4, b'\0'))
            else:
                b.extend(bytes(4))
                later.append((pos, v))
        for pos, v in later:
            struct.pack_into('<I', b, pos, put(v) - pos)
        return t

    struct.pack_into('<I', b, 0, put(root))
    return bytes(b)


def vec(*xs):
    return Table(**{'f%d' % i: ('f', float(x)) for i, x in enumerate(xs)})


# ------------------------------------------------------------------------------------------------ PANM clips
def quantised(values, rot_bits=14, trans_bits=12, uniform=False):
    """Storage-3 track data of transform samples (frames, 11): scale (one field if uniform), rotation x y z with
    the w sign bit, translation x y z."""
    v = np.asarray(values, np.float64)
    F = len(v)
    mask = panm.Q_SCALE | panm.Q_ROTATION | panm.Q_TRANSLATION | (panm.Q_UNIFORM if uniform else 0)
    chans = []
    for c in (0, 1, 2, 3, 4, 5, 7, 8, 9):
        lo, hi = float(v[:, c].min()), float(v[:, c].max())
        bits = (trans_bits if c >= 7 else rot_bits if c >= 3 else 10) if hi > lo else 0
        chans.append((lo, hi, bits, c))
    fields = ([chans[0]] if uniform else chans[:3]) + chans[3:]
    bpf = sum(f[2] for f in fields) + 1
    base_at, stream_at = 0xA0, 0xCC
    bits = []
    for f in range(F):
        for lo, hi, n, c in fields:
            q = int(round((v[f, c] - lo) / (hi - lo) * ((1 << n) - 1))) if n else 0
            bits += [(q >> i) & 1 for i in range(n)]
        bits.append(1 if v[f, 6] < 0 else 0)
    bits += [0] * (-len(bits) % 8)
    stream = np.packbits(np.array(bits, np.uint8), bitorder='little').tobytes()
    head = struct.pack('<4H2I', panm.Q_VERSION, mask, base_at, bpf, stream_at, F)
    head += b''.join(struct.pack('<2f2I', lo, hi, n, 0) for lo, hi, n, c in chans)
    head = head.ljust(base_at, b'\0') + struct.pack('<11f', *v[0]).ljust(stream_at - base_at, b'\0')
    return head + stream


def clip(tracks, frames, fps=60.0):
    """A PANM blob: tracks [(joint, values (n, 11) or (n, 1), storage, flags, channel)]."""
    data = bytearray()
    nodes = {}
    for joint, values, storage, flags, channel in tracks:
        values = np.asarray(values, np.float64)
        width = values.shape[1]
        if storage == panm.QUANTISED:
            raw = quantised(values) if width == panm.SAMPLE else float_quantised(values[:, 0])
        else:
            raw = np.asarray(values, '<f4').tobytes()
        while len(data) % 48:
            data.append(0)
        fl = Table(**{'f%d' % k: ('B', 1) for k, bit in ((1, 1), (2, 2), (3, 4), (4, 8), (8, 0x80)) if flags & bit})
        tr = Table(f1=channel, f2=('I', panm.TRANSFORM if width == panm.SAMPLE else panm.FLOAT),
                   f3=('I', storage), f4=('I', len(values)), f5=fl, f6=('I', len(data)), f7=('I', len(raw)))
        data += raw
        nodes.setdefault(joint, []).append(tr)
    group = Table(f1=('I', 1), f2=[Table(f1=n, f2=t) for n, t in nodes.items()])

    def build(at):
        an = Table(f1=('I', frames - 1), f2=('f', fps), f3=('I', 1), f4=[group], f5=('I', at), f6=('I', len(data)),
                   f7=('I', len(data)), f9=('I', len(data)))
        return flatbuffer(Table(f2=('B', 1), f3=an), panm.IDENTIFIER)
    head = build(0)
    head = build(len(head))
    return head + bytes(data)


def float_quantised(values, bits=13):
    v = np.asarray(values, np.float64)
    lo, hi = float(v.min()), float(v.max())
    out = []
    for x in v:
        q = int(round((x - lo) / (hi - lo) * ((1 << bits) - 1)))
        out += [(q >> i) & 1 for i in range(bits)]
    out += [0] * (-len(out) % 8)
    stream = np.packbits(np.array(out, np.uint8), bitorder='little').tobytes()
    head = struct.pack('<4H2I', panm.Q_VERSION, 0, 0x20, bits, 0x24, len(v)) + struct.pack('<2f2I', lo, hi, bits, 0)
    return head.ljust(0x20, b'\0') + struct.pack('<f', v[0]) + stream


def sample(q=(0, 0, 0, 1), t=(0, 0, 0), s=(1, 1, 1)):
    return list(s) + list(q) + list(t) + [0.0]


def matrix_quaternion(m):
    """(x, y, z, w) of rotation matrices (..., 3, 3) (the inverse of animation.quaternion_to_matrix)."""
    m = np.asarray(m, np.float64)
    w = np.sqrt(np.maximum(0, 1 + m[..., 0, 0] + m[..., 1, 1] + m[..., 2, 2])) / 2
    x = np.sqrt(np.maximum(0, 1 + m[..., 0, 0] - m[..., 1, 1] - m[..., 2, 2])) / 2
    y = np.sqrt(np.maximum(0, 1 - m[..., 0, 0] + m[..., 1, 1] - m[..., 2, 2])) / 2
    z = np.sqrt(np.maximum(0, 1 - m[..., 0, 0] - m[..., 1, 1] + m[..., 2, 2])) / 2
    x = np.copysign(x, m[..., 2, 1] - m[..., 1, 2])
    y = np.copysign(y, m[..., 0, 2] - m[..., 2, 0])
    z = np.copysign(z, m[..., 1, 0] - m[..., 0, 1])
    return np.stack([x, y, z, w], -1)


# ------------------------------------------------------------------------------------------------ banks
def bank(categories, key_lists=None):
    """An .anmbin: categories [6 x [(key, blob or None, fighters)]], key_lists [6 x [keys]]."""
    key_lists = key_lists or [[] for _ in range(6)]
    at = anmbin.HEADER_SIZE
    lists, klists = [], []
    for c in range(6):
        lists.append(at)
        at += anmbin.ENTRY_SIZE * len(categories[c])
    for c in range(6):
        klists.append(at)
        at += 4 * len(key_lists[c])
    index_end = at
    out = bytearray(struct.pack('<I6I6II6Q6Q', index_end, *[len(x) for x in categories],
                                *[len(x) for x in key_lists], 0, *lists, *klists))
    blobs = bytearray()
    for c in range(6):
        for key, blob, fighters in categories[c]:
            mask = [0] * anmbin.MASK_WORDS
            for f in fighters:
                mask[f // 32] |= 1 << (f % 32)
            off = 0
            if blob is not None:
                off = index_end + len(blobs)
                blobs += blob
            out += struct.pack('<IIQQ8I', key, 0, off, 0, *mask)
    for c in range(6):
        out += struct.pack('<%dI' % len(key_lists[c]), *key_lists[c])
    return bytes(out + blobs)


# ------------------------------------------------------------------------------------------------ a fighter
# Tekken 8's joints for the TTT2 bones they drive (and the landmarks), the rest of its hierarchy around them
T8_OF = {'Spine1': 'HARA_ROT1', 'Spine2': 'MUNE2_jnt', 'Neck': 'KUBI_jnt', 'Head': 'ATAMA_jnt', 'C_Leg': 'KOSHI_jnt'}
for _s in 'RL':
    T8_OF.update({'%s_Shoulder' % _s: 'SAKOTSU_%s_jnt' % _s, '%s_UpperArm' % _s: 'KATA_%s_jnt' % _s,
                  '%s_LowerArm' % _s: 'UDE_%s_jnt' % _s, '%s_Hand' % _s: 'TE_%s_jnt' % _s,
                  '%s_UpperLeg' % _s: 'MOMO_%s_jnt' % _s, '%s_LowerLeg' % _s: 'HIZA_%s_jnt' % _s,
                  '%s_Foot' % _s: 'ASHI_%s_jnt' % _s, '%s_Toe' % _s: 'TSUMASAKI_%s_jnt' % _s})
T8_PARENT = {'Root': None, 'Top': None, 'Trans': 'Top', 'Rot': 'Trans', 'MUKI': 'Rot', 'Hip': 'Rot', 'C_Leg': 'Hip',
             'Spine1': 'Hip', 'Spine2': 'Spine1', 'Neck': 'Spine2', 'Head': 'Neck'}
for _s in 'RL':
    T8_PARENT.update({'%s_Shoulder' % _s: 'Spine2', '%s_UpperArm' % _s: '%s_Shoulder' % _s,
                      '%s_LowerArm' % _s: '%s_UpperArm' % _s, '%s_Hand' % _s: '%s_LowerArm' % _s,
                      '%s_UpperLeg' % _s: 'C_Leg', '%s_LowerLeg' % _s: '%s_UpperLeg' % _s,
                      '%s_Foot' % _s: '%s_LowerLeg' % _s, '%s_Toe' % _s: '%s_Foot' % _s})
SIZE = 1.05                                     # the made-up fighter: 1.05 times the TTT2 skeleton (before its scale)


class Fighter:
    """A made-up Tekken 8 fighter built on a TTT2 skeleton: its joints at the TTT2 bones' A-posed places (x SIZE /
    the scale, in cm), random joint axes; .psks its PSKS buffer, .sk the skeleton anim.skeleton reads of it."""

    def __init__(self, bon, seed=7):
        rng = np.random.default_rng(seed)
        self.bon = bon
        self.ttt2 = RT.ttt2_skeleton(bon)
        WR, Wp = TR.a_pose(self.ttt2)
        f = SIZE / self.ttt2.scale / 10
        self.names = list(T8_PARENT)
        self.parents = [self.names.index(T8_PARENT[n]) if T8_PARENT[n] else -1 for n in self.names]
        hara = Wp[0]
        place = {'Root': np.zeros(3), 'Top': np.zeros(3), 'Trans': hara, 'Rot': hara, 'MUKI': hara,
                 'Hip': hara - [0, 150, 0]}
        self.Q = {}
        W, P = [], []
        for n in self.names:
            b = T8_OF.get(n)
            if b is not None:
                i = self.ttt2.index[b]
                self.Q[n] = TR.random_rotation(rng)
                W.append(WR[i] @ self.Q[n])
                P.append(Wp[i] * f)
            else:
                W.append(np.eye(3) if n in ('Root', 'Top', 'Trans', 'Rot', 'MUKI') else TR.random_rotation(rng))
                P.append(place[n] * f)
        self.W, self.P = np.array(W), np.array(P)
        R, t = TR.locals_of(self.parents, self.W, self.P)
        self.R, self.t = R, t
        bones = [Table(f2=n, f4=('H', p if p >= 0 else 0xFFFF), f5=vec(*t[i]), f6=vec(*matrix_quaternion(R[i])))
                 for i, (n, p) in enumerate(zip(self.names, self.parents))]
        self.psks = flatbuffer(Table(f2=('I', 1), f3=Table(f1=bones, f3=[])), b'PSKS')
        self.sk = T8.skeleton(T8.read_skeleton(self.psks))
        self.f = f

    def clip(self, values, legacy=False, leg_offset=None):
        """The fighter's clip of a TTT2 pose (body channel values): every joint's local rotation (raw storage, or
        quantised: an older clip without translations), Top / Trans translations (cm), MUKI's yaw."""
        sk = self.ttt2
        F = len(values)
        WR, Wp = RT.pose(sk, values, animation.COMPRESSED, root_motion=False)
        idx = {n: i for i, n in enumerate(self.names)}
        W = np.repeat(self.W[None], F, 0)
        for n, b in T8_OF.items():
            W[:, idx[n]] = WR[:, sk.index[b]] @ self.Q[n]
        # Rot carries C_Leg (Hip and C_Leg keep their bind locals), Spine1 Spine2 (its bind local)
        W[:, idx['Hip']] = W[:, idx['C_Leg']] @ self.R[idx['C_Leg']].T
        W[:, idx['Rot']] = W[:, idx['Hip']] @ self.R[idx['Hip']].T
        W[:, idx['Spine1']] = W[:, idx['Spine2']] @ self.R[idx['Spine2']].T
        T = animation.local_rotation(values[:, 2], animation.COMPRESSED)
        W[:, idx['MUKI']] = W[:, idx['Rot']] @ T
        tracks = []
        for i, n in enumerate(self.names):
            p = self.parents[i]
            L = W[:, i] if p < 0 else np.swapaxes(W[:, p], 1, 2) @ W[:, i]
            q = matrix_quaternion(L)
            t = np.repeat(self.t[i][None], F, 0)
            if n == 'Top':
                t = values[:, 0] * sk.scale * self.f * [1, 0, 1]
            elif n == 'Trans':
                t = Wp[:, RT.HARA] * self.f
            elif n == 'L_LowerLeg' and leg_offset is not None:
                t = t + leg_offset
            v = np.concatenate([np.ones((F, 3)), q, t, np.zeros((F, 1))], 1)
            if legacy:
                tracks.append((n, v, panm.QUANTISED, panm.NO_TRANSLATION | panm.LEGACY_A, 'Transform'))
            else:
                tracks.append((n, v, panm.RAW, panm.NEW, 'Transform'))
        return clip(tracks, F)


# ------------------------------------------------------------------------------------------------ tests
class PanmTest(unittest.TestCase):
    def test_raw_and_constant(self):
        q = np.array([[0, 0, np.sin(a), np.cos(a)] for a in np.linspace(0, 1, 5)])
        raw = np.array([sample(x, (1, 2, 3)) for x in q])
        b = clip([('A', raw, panm.RAW, panm.NEW, 'Transform'),
                  ('B', [sample((0, 0, 0, 1), (4, 5, 6))], panm.CONSTANT, panm.NO_ROTATION, 'Transform')], 5)
        a = panm.Animation(b)
        self.assertEqual((a.frames, a.fps, a.version, a.legacy), (5, 60.0, 1, False))
        self.assertEqual(panm.frame_count(b), 5)
        J = a.joints()
        np.testing.assert_allclose(J['A'].rotation, q, atol=1e-6)
        np.testing.assert_allclose(J['A'].translation, np.tile([1, 2, 3], (5, 1)), atol=1e-6)
        np.testing.assert_allclose(J['B'].translation, np.tile([4, 5, 6], (5, 1)), atol=1e-6)
        self.assertTrue(J['A'].stored_rotation and J['A'].stored_translation)
        self.assertFalse(J['B'].stored_rotation)
        self.assertEqual(J['B'].storage, panm.CONSTANT)

    def test_quantised(self):
        F = 30
        q = np.array([[np.sin(a) * 0.6, 0.1, np.cos(a) * 0.3, 0] for a in np.linspace(-2, 2, F)])
        q[:, 3] = np.sqrt(1 - (q[:, :3] ** 2).sum(1)) * np.where(np.arange(F) % 7 == 3, -1, 1)
        v = np.array([sample(x, (np.sin(i), 100 + i, -i * 0.5)) for i, x in enumerate(q)])
        b = clip([('J', v, panm.QUANTISED, panm.NO_TRANSLATION | panm.LEGACY_A, 'Transform')], F)
        a = panm.Animation(b)
        self.assertTrue(a.legacy)
        J = a.joints()['J']
        same = np.abs((J.rotation * q).sum(1))
        self.assertGreater(same.min(), 1 - 1e-6)
        np.testing.assert_allclose(J.translation, v[:, 7:10], atol=0.01)
        self.assertFalse(J.stored_translation)

    def test_quantised_uniform_scale_and_float(self):
        F = 20
        v = np.array([sample((0, 0, 0, 1), (0, 0, 0), (1 + i / 40,) * 3) for i in range(F)])
        v[:, 3:7] = matrix_quaternion(np.array([TR.rot_about([1, 1, 0], a) for a in np.linspace(0, 1, F)]))
        data = quantised(v, uniform=True)
        out = panm.dequantise(data, panm.SAMPLE)
        np.testing.assert_allclose(out[:, 0], out[:, 2])
        np.testing.assert_allclose(out[:, 0], v[:, 0], atol=1e-3)
        fov = np.linspace(0.3, 0.39, F)[:, None]
        b = clip([('cam_transform', fov, panm.QUANTISED, 0, 'FieldOfView')], F)
        t = [x for x in panm.Animation(b).tracks if x.channel == 'FieldOfView'][0]
        np.testing.assert_allclose(t.values()[:, 0], fov[:, 0], atol=2e-5)

    def test_bad_data(self):
        with self.assertRaises(ValueError):
            panm.Animation(b'\x08\0\0\0NOPE' + bytes(16))
        data = bytearray(quantised(np.array([sample((0, 0, 0.1, 0.99), (0, 1, 0)) for _ in range(4)] +
                                            [sample((0, 0.1, 0, 0.99), (0, 2, 0))])))
        struct.pack_into('<H', data, 6, struct.unpack_from('<H', data, 6)[0] + 1)    # bits per frame off by one
        with self.assertRaises(ValueError):
            panm.dequantise(bytes(data), panm.SAMPLE)

    def test_resample(self):
        v = np.array([sample(matrix_quaternion(TR.rot_about([0, 1, 0], a)), (a, 0, 0)) for a in (0, 0.5, 1.0)])
        b = clip([('A', v, panm.RAW, 0, 'Transform')], 3, fps=30.0)
        a = panm.Animation(b)
        self.assertEqual(a.frames_at(60.0), 5)
        J = a.joints()['A']
        self.assertEqual(len(J.translation), 5)
        np.testing.assert_allclose(J.translation[:, 0], [0, 0.25, 0.5, 0.75, 1.0], atol=1e-6)
        np.testing.assert_allclose(np.abs(J.rotation[1]), np.abs(matrix_quaternion(TR.rot_about([0, 1, 0], 0.25))),
                                   atol=1e-6)


class BankTest(unittest.TestCase):
    def setUp(self):
        self.a = clip([('A', [sample()], panm.CONSTANT, 0, 'Transform')], 3)
        self.b = clip([('B', [sample()] * 4, panm.RAW, 0, 'Transform')], 4)
        own = [[(0x11, self.a, []), (0x22, None, []), (0x33, None, [])], [(0x44, self.b, [])], [], [], [], []]
        com = [[(0x22, self.b, [28]), (0x33, self.a, [5])], [], [], [], [], []]
        self.own = anmbin.Bank(bank(own, [[0x11, 0x22, 0x33, 0x22], [0x44], [], [], [], []]), 'own')
        self.com = anmbin.Bank(bank(com), 'com')
        self.banks = anmbin.Banks(self.own, self.com, 28)

    def test_index(self):
        self.assertEqual(self.own.counts, (3, 1, 0, 0, 0, 0))
        self.assertEqual(self.own.keys(anmbin.BODY), [0x11, 0x22, 0x33])
        self.assertEqual(self.own.blob(anmbin.BODY, 0x11), self.a)
        self.assertEqual(self.own.blob(anmbin.HANDS, 0x44), self.b)        # the last blob runs to the file's end
        self.assertIsNone(self.own.blob(anmbin.BODY, 0x22))
        self.assertTrue(self.com.entry(anmbin.BODY, 0x22).serves(28))
        self.assertFalse(self.com.entry(anmbin.BODY, 0x33).serves(28))
        self.assertEqual(self.own.key_lists[0], [0x11, 0x22, 0x33, 0x22])

    def test_banks(self):
        b = self.banks
        self.assertEqual((b.where(0, 0x11), b.where(0, 0x22), b.where(0, 0x33), b.where(0, 0x99)),
                         ('own', 'com', None, None))
        self.assertEqual(b.blob(0, 0x22), self.b)
        self.assertIsNone(b.blob(0, 0x33))                  # the shared entry does not serve fighter 28
        self.assertEqual(b.anim_key(3), 0x22)
        with self.assertRaises(IndexError):
            b.anim_key(4)
        self.assertEqual(b.move_keys(), [(0x11, 'own'), (0x22, 'com'), (0x33, None)])

    def test_files(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(InputError):
                anmbin.open_banks(d, 'zzz', 28)
            for name, data in (('zzz', self.own.data), ('com', self.com.data)):
                with open(os.path.join(d, name + '.anmbin'), 'wb') as f:
                    f.write(data)
            b = anmbin.open_banks(d, 'zzz', 28)
            self.assertEqual(b.blob(0, 0x22), self.b)
            b.own.close()
            b.shared.close()
        with self.assertRaises(InputError):
            anmbin.Bank(b'\0' * 16)
        cut = bytearray(self.own.data)
        struct.pack_into('<I', cut, 0, len(cut) + 100)          # the index runs past the end
        with self.assertRaises(InputError):
            anmbin.Bank(bytes(cut))


class SkeletonTest(unittest.TestCase):
    def test_read(self):
        f = Fighter(TR.ttt2_bon())
        s = T8.read_skeleton(f.psks)
        self.assertEqual(s['names'], f.names)
        self.assertEqual(s['parents'], f.parents)
        np.testing.assert_allclose(s['t'], f.t, atol=1e-4)
        np.testing.assert_allclose(f.sk.t, f.t * T8.CM, atol=1e-3)
        WR, Wp = f.sk.bind_world()
        np.testing.assert_allclose(WR, f.W, atol=1e-5)                 # (single-precision rotations)
        np.testing.assert_allclose(Wp, f.P * T8.CM, atol=1e-3)

    def test_bad(self):
        with self.assertRaises(InputError):
            T8.read_skeleton(b'\x08\0\0\0PSKX' + bytes(8))
        with self.assertRaises(InputError):
            T8.read_skeleton(flatbuffer(Table(f3=Table(f1=[], f3=[])), b'PSKS'))
        bad = flatbuffer(Table(f3=Table(f1=[Table(f2='a', f4=('H', 5))])), b'PSKS')
        with self.assertRaises(InputError):
            T8.read_skeleton(bad)


class ConverterTest(unittest.TestCase):
    def setUp(self):
        self.bon = TR.ttt2_bon()
        self.fighter = Fighter(self.bon)
        self.values = TR.smooth_values(24)
        self.cv = T8.Converter(self.fighter.sk, self.bon)

    def test_conventions(self):
        """Top -> channel 0, Trans -> channel 1, MUKI -> channel 2, the joints -> the TTT2 bones' world rotations."""
        b = self.fighter.clip(self.values)
        out, info = self.cv.channels(panm.Animation(b))
        self.assertAlmostEqual(info['root_scale'], 1 / SIZE, 6)
        self.assertAlmostEqual(info['leg'], 860 * SIZE, 2)
        v = self.values
        np.testing.assert_allclose(out[:, 0], v[:, 0] * [1, 0, 1], atol=0.05)
        np.testing.assert_allclose(out[:, 1], v[:, 1], atol=0.05)
        sk = self.cv.cal.dst
        W0, P0 = RT.pose(sk, v, animation.COMPRESSED)
        W1, P1 = RT.pose(sk, out, animation.COMPRESSED)
        self.assertLess(RT.angle(W1[:, 1:22], W0[:, 1:22]).max(), 1e-3)
        self.assertLess(np.abs(P1[:, :22] - P0[:, :22]).max(), 0.1)
        T0 = animation.local_rotation(v[:, 2], animation.COMPRESSED)
        T1 = animation.local_rotation(out[:, 2], animation.COMPRESSED)
        self.assertLess(RT.angle(T0, T1).max(), 1e-3)

    def test_bytes(self):
        data = self.cv.animation(self.fighter.clip(self.values))
        h = animation.header(data)
        self.assertEqual((h['type'], h['frames'], h['nch'], h['size']), (animation.COMPRESSED, 24, 23, len(data)))
        self.assertEqual(data, T8.convert_body(self.fighter.clip(self.values), self.fighter.sk, self.bon))
        raw = T8.Converter(self.fighter.sk, self.bon, animation.RAW).animation(self.fighter.clip(self.values))
        self.assertEqual(animation.header(raw)['type'], animation.RAW)
        sk = self.cv.cal.dst
        W0, P0 = RT.pose(sk, animation.decode(data)['values'], animation.COMPRESSED)
        W1, P1 = RT.pose(sk, animation.decode(raw)['values'], animation.RAW)
        self.assertLess(np.abs(P1[:, :22] - P0[:, :22]).max(), 0.5)

    def test_only_the_root_moves(self):
        """A clip's other translations are its authoring rig's: the fighter keeps its own lengths."""
        a = self.cv.channels(panm.Animation(self.fighter.clip(self.values)))[0]
        b = self.cv.channels(panm.Animation(self.fighter.clip(self.values, leg_offset=(3.0, 0, 0))))[0]
        np.testing.assert_allclose(a, b, atol=1e-9)

    def test_older_clips_in_ttt2_units(self):
        out, info = self.cv.channels(panm.Animation(self.fighter.clip(self.values, legacy=True)))
        self.assertAlmostEqual(info['leg'], T8.LEGACY_LEG)
        self.assertAlmostEqual(info['root_scale'], 860.0 / T8.LEGACY_LEG, 6)

    def test_provider(self):
        good = self.fighter.clip(self.values)
        own = [[(0x10, good, []), (0x20, None, [])], [], [], [], [], []]
        banks = anmbin.Banks(anmbin.Bank(bank(own, [[0x10, 0x20], [], [], [], [], []])),
                             anmbin.Bank(bank([[], [], [], [], [], []])), 28)
        p = T8.Animations(banks, self.cv)
        first = p(0x10, 'own')
        self.assertEqual(first, self.cv.animation(good))
        self.assertIs(p(0x10, 'own'), first)                    # converted once
        self.assertIsNone(p(0x20, None))
        self.assertEqual(sum(p.stats.values()), 2)


if __name__ == '__main__':
    unittest.main()
