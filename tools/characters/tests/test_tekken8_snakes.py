"""Unit tests of a Tekken 8 summoned model with its own skeleton and clips (Miary Zo's snakes: convert/snakes8.py, the
UE5 per-track clip reader tekken8/ue5anim.py, the heads' pair of tekken8/anim.py, the converter's hooks) on made-up
data (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_snakes.py
"""
import collections
import os
import struct
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from ttt2char.convert import cloth, model, moveset, snakes8, tiger, weapons  # noqa: E402
from ttt2char.characters import miary_zo  # noqa: E402
from ttt2char.tekken7 import mesh as t7mesh  # noqa: E402
from ttt2char.tekken8 import anim as T8, ue5anim  # noqa: E402
from ttt2char.ttt2 import animation, bone  # noqa: E402
import test_retarget as TR  # noqa: E402

D = np.diag([1.0, -1.0, 1.0])
P = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])


# ------------------------------------------------------------------------------------------------ the clip reader
def _fstring(s):
    b = s.encode('latin-1') + b'\0'
    return struct.pack('<i', len(b)) + b


def track(fmt, comps, keys, frames=None):
    """One track's bytes: fmt FLOAT96 / FIXED48 / INTERVAL32, comps the stored components (0..2), keys (k, len(comps))
    raw values (floats, u16, or for INTERVAL32 ((min, range) per comp, u32 keys)), frames: a frame table (u8)."""
    flags = sum(1 << c for c in comps) | (8 if frames is not None else 0)
    if fmt == ue5anim.INTERVAL32:
        mr, raw = keys
        n = len(raw)
        out = struct.pack('<I', n | flags << 24 | fmt << 28) + struct.pack('<%df' % len(mr), *mr) + \
            struct.pack('<%dI' % n, *raw)
    else:
        keys = np.asarray(keys)
        n = len(keys)
        out = struct.pack('<I', n | flags << 24 | fmt << 28)
        out += (keys.astype('<f4') if fmt == ue5anim.FLOAT96 else keys.astype('<u2')).tobytes()
    out += b'\x55' * (-len(out) % 4)
    if frames is not None:
        out += bytes(frames)
        out += b'\x55' * (-len(out) % 4)
    return out


def sequence(tracks, frames, track_map, end=8):
    """A made-up AnimSequence export's bytes (properties ending at `end`): tracks [(translation, rotation, scale)
    track bytes or None] per entry of track_map."""
    data = b''
    offs, soffs = [], []
    for t, r, s in tracks:
        for part, out in ((t, offs), (r, offs), (s, soffs)):
            if part is None:
                out.append(-1)
            else:
                out.append(len(data))
                data += part
    stream = struct.pack('<%di' % len(offs), *offs) + struct.pack('<%di' % len(soffs), *soffs) + data
    b = bytes(end) + struct.pack('<I', 0) + bytes(16) + struct.pack('<H', 0) + struct.pack('<I', 1)
    b += struct.pack('<ii', 1000, len(track_map)) + struct.pack('<%di' % len(track_map), *track_map)
    b += struct.pack('<i', 0) + struct.pack('<iI', len(stream), 0) + stream
    b += _fstring('AnimCompress_PerTrackCompression_2') + _fstring('/Script/None') + struct.pack('<i', 0)
    b += struct.pack('<i', frames) + bytes([2, 6, 6, 6])
    b += struct.pack('<5i', len(data), len(offs), len(soffs), 1, 1)
    return b


class Ue5AnimTest(unittest.TestCase):
    def test_float96_and_single_key(self):
        F = 5
        v = np.arange(F * 2, dtype=np.float64).reshape(F, 2)
        out, end = ue5anim.read_track(track(ue5anim.FLOAT96, (0, 2), v), 0, F, False)
        np.testing.assert_allclose(out[:, [0, 2]], v)
        np.testing.assert_allclose(out[:, 1], 0)
        self.assertEqual(end, 4 + 4 * v.size)
        out, _ = ue5anim.read_track(track(ue5anim.FLOAT96, (1,), [[3.5]]), 0, F, False)
        np.testing.assert_allclose(out, np.repeat([[0.0, 3.5, 0.0]], F, 0))

    def test_fixed48_rotation_and_vector(self):
        q = np.array([[0.1, -0.2, 0.3], [0.0, 0.5, -0.5], [-0.7, 0.1, 0.1]])
        raw = np.round(q * 32767 + 32767)
        out, _ = ue5anim.read_track(track(ue5anim.FIXED48, (0, 1, 2), raw), 0, 3, True)
        w = np.sqrt(1 - (q ** 2).sum(1))
        np.testing.assert_allclose(out, np.concatenate([q, w[:, None]], 1), atol=1e-4)
        np.testing.assert_allclose(np.linalg.norm(out, axis=1), 1, atol=1e-9)
        out, _ = ue5anim.read_track(track(ue5anim.FIXED48, (0, 1), [[256, 260]]), 0, 2, False)   # raw - 255
        np.testing.assert_allclose(out, [[1.0, 5.0, 0.0]] * 2)

    def test_interval32(self):
        bx, by, bz = ue5anim.INTERVAL_BITS
        x, y, z = 100, 2000, 7
        raw = x << (by + bz) | y << bz | z
        out, _ = ue5anim.read_track(track(ue5anim.INTERVAL32, (0, 1, 2), ((1.0, 2.0, -1.0, 4.0, 0.0, 1.0), [raw])),
                                    0, 2, False)
        want = [1.0 + 2.0 * x / ((1 << bx) - 1), -1.0 + 4.0 * y / ((1 << by) - 1), z / ((1 << bz) - 1)]
        np.testing.assert_allclose(out, [want] * 2, atol=1e-6)

    def test_timed_track_interpolates(self):
        """A frame table: keys at those frames, linear between; the data padded before the table and after."""
        v = np.array([[0.0], [10.0], [40.0]])
        b = track(ue5anim.FLOAT96, (0,), v, frames=[0, 2, 5])
        out, end = ue5anim.read_track(b + b'\0' * 8, 0, 6, False)
        np.testing.assert_allclose(out[:, 0], [0, 5, 10, 20, 30, 40])
        self.assertEqual(end, len(b))

    def test_decode(self):
        F = 4
        t = track(ue5anim.FLOAT96, (0, 1, 2), np.arange(F * 3).reshape(F, 3))
        r = track(ue5anim.FIXED48, (2,), np.full((1, 1), 32767))          # (0, 0, 0, 1)
        s = track(ue5anim.FIXED48, (0, 1, 2), np.full((1, 3), 256))
        b = sequence([(t, r, s), (None, None, None)], F, [3, 1])
        clip = ue5anim.decode(b, 8)
        self.assertEqual((clip.frames, sorted(clip.tracks)), (F, [1, 3]))
        tr, rot, sc = clip.tracks[3]
        np.testing.assert_allclose(tr, np.arange(F * 3).reshape(F, 3))
        np.testing.assert_allclose(rot, np.repeat([[0.0, 0.0, 0.0, 1.0]], F, 0))
        np.testing.assert_allclose(sc, np.ones((F, 3)))
        self.assertEqual(clip.tracks[1], (None, None, None))
        sk = {'pose': np.tile([0.0, 0.0, 0.0, 1.0, 5.0, 6.0, 7.0, 2.0, 2.0, 2.0], (4, 1))}
        pose = ue5anim.local_poses(clip, sk)
        np.testing.assert_allclose(pose[:, 3, 4:7], tr)
        np.testing.assert_allclose(pose[:, 1, 4:7], 0)                      # (a track without data: 0 / identity)
        np.testing.assert_allclose(pose[:, 1, 7:10], 2.0)                   # (no scale data: the reference's)
        np.testing.assert_allclose(pose[:, 0], np.repeat(sk['pose'][:1], F, 0))   # (no track: the reference pose)

    def test_layout_refuses(self):
        b = bytearray(sequence([(track(ue5anim.FLOAT96, (0,), [[1.0]]), None, None)], 2, [0]))
        b[8 + 4 + 16 + 2] = 0                                                # not compressed
        with self.assertRaises(ValueError):
            ue5anim.layout(bytes(b), 8)


# ------------------------------------------------------------------------------------------------ the skeleton
def snake_skeleton():
    """names, parents of a made-up snake rig: Root, the centre, the dambe, per snake its base, 12 necks, head, jaw and
    a tongue joint under the jaw (parents first)."""
    names, parents = ['Root', snakes8.CENTER, snakes8.DAMBE], [-1, 0, 0]
    for s in snakes8.CHAINS:
        up = 1
        for q in range(snakes8.NECKS + 3):
            names.append(snakes8.chain_name(s, q))
            parents.append(up if q != snakes8.NECKS + 2 else len(names) - 2)
            up = len(names) - 1
        names.append('ATH_tongue_%s_01' % s)
        parents.append(len(names) - 2)
    return names, parents


class SkeletonTest(unittest.TestCase):
    def setUp(self):
        self.names, self.parents = snake_skeleton()
        self.necks = (2, 5, 8, 11)
        self.keep = snakes8.kept(self.names, self.necks)

    def test_kept(self):
        d = types.SimpleNamespace(SNAKES={'necks': self.necks, 'vertices': {'snk': 10, 'dmb': 2}})
        self.assertEqual(len(self.keep), snakes8.bone_count(d))
        self.assertEqual(snakes8.vertices(d), 12)
        self.assertEqual(snakes8.bone_count(types.SimpleNamespace()), 0)
        kept = [self.names[b] for b in self.keep]
        self.assertEqual(kept[:3], [snakes8.CENTER, snakes8.DAMBE, 'ATH_snake_A'])
        self.assertNotIn('Root', kept)
        up = snakes8.kept_parents(self.parents, self.keep)
        self.assertEqual(up[:2], [-1, -1])                                  # (the roots: under the weapon bone)
        self.assertEqual(kept[up[kept.index('ATH_neck_A_05')]], 'ATH_neck_A_02')
        self.assertEqual(kept[up[kept.index('ATH_head_A')]], 'ATH_neck_A_11')
        with self.assertRaises(ValueError):
            snakes8.kept(self.names[:-5], self.necks)

    def test_remap(self):
        """A neck left out: the kept joints before and after it, linearly by place; the jaw kept; the tongue its
        nearest kept ancestor (the jaw); Root nothing."""
        table = snakes8.remap(self.names, self.parents, self.keep)
        at = {self.names[b]: k for k, b in enumerate(self.keep)}
        i = self.names.index
        for name, want in (('ATH_neck_B_03', [('ATH_neck_B_02', 2 / 3), ('ATH_neck_B_05', 1 / 3)]),
                           ('ATH_neck_B_01', [('ATH_snake_B', 0.5), ('ATH_neck_B_02', 0.5)]),
                           ('ATH_neck_B_12', [('ATH_neck_B_11', 0.5), ('ATH_head_B', 0.5)])):
            got = table[i(name)]
            self.assertEqual([k for k, _ in got], [at[x] for x, _ in want])
            np.testing.assert_allclose([w for _, w in got], [w for _, w in want])
        self.assertEqual(table[i('ATH_jaw_C')], [(at['ATH_jaw_C'], 1.0)])
        self.assertEqual(table[i('ATH_tongue_C_01')], [(at['ATH_jaw_C'], 1.0)])
        self.assertEqual(table[i('Root')], [])

    def test_remap_weights(self):
        table = snakes8.remap(self.names, self.parents, self.keep)
        i = self.names.index
        joints = np.array([[i('ATH_neck_A_03'), i('Root'), 0], [i('ATH_head_A'), i('ATH_jaw_A'), 0]])
        weights = np.array([[0.75, 0.25, 0.0], [0.5, 0.5, 0.0]])
        j, w, lost = snakes8.remap_weights(joints, weights, table, len(self.keep), influences=4)
        self.assertAlmostEqual(lost, 0.25)
        at = {self.names[b]: k for k, b in enumerate(self.keep)}
        got = {int(a): float(b) for a, b in zip(j[0], w[0]) if b > 0}
        self.assertEqual(set(got), {at['ATH_neck_A_02'], at['ATH_neck_A_05']})
        self.assertAlmostEqual(got[at['ATH_neck_A_02']], 2 / 3)
        np.testing.assert_allclose(w.sum(1), 1)

    def test_chain_place(self):
        self.assertEqual(snakes8.chain_place('ATH_neck_C_07'), ('C', 7))
        self.assertEqual(snakes8.chain_place('ATH_jaw_B'), ('B', snakes8.NECKS + 2))
        self.assertIsNone(snakes8.chain_place('ATH_center'))


def random_pose(rng, parents, scale_bone=None):
    """(n, 10) local poses (quaternion x y z w, translation cm, scale) of a skeleton."""
    n = len(parents)
    q = rng.normal(size=(n, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    pose = np.concatenate([q, rng.uniform(-15, 15, (n, 3)), np.ones((n, 3))], 1)
    if scale_bone is not None:
        pose[scale_bone, 7:10] = (0.5, 0.5, 0.5)
    return pose


def store_local(t, r, s):
    """The runtime's record of a part-3 frame as a column-vector local (roster.cpp store_local: rows the axes,
    scaled)."""
    cx, sx, cy, sy, cz, sz = np.cos(r[0]), np.sin(r[0]), np.cos(r[1]), np.sin(r[1]), np.cos(r[2]), np.sin(r[2])
    R = np.array([[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
                  [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
                  [-sy, cy * sx, cy * cx]])
    out = np.eye(4)
    out[:3, :3] = R * np.asarray(s)[None, :]
    out[:3, 3] = t
    return out


def runtime_worlds(L, up, U=np.eye(4)):
    """Worlds of the kept bones from their locals (kept, 4, 4) decomposed and written the runtime's way."""
    t, r, s = snakes8.decompose(L)
    out = []
    for k in range(len(L)):
        parent = U if up[k] < 0 else out[up[k]]
        out.append(parent @ store_local(t[k], r[k], s[k]))
    return np.array(out)


class LocalsTest(unittest.TestCase):
    """ttt2_locals: every kept bone's TTT2 world under the weapon bone's frame (the identity: UDE_R_jnt's) is the
    snakes' space mapped into UDE_R_jnt's frame: rotation O^T D G P, position O^T D t x 10."""

    def setUp(self):
        self.rng = np.random.default_rng(5)
        self.names, self.parents = snake_skeleton()
        self.keep = snakes8.kept(self.names, (2, 5, 8, 11))
        self.up = snakes8.kept_parents(self.parents, self.keep)
        self.O = TR.random_rotation(self.rng)

    def test_worlds(self):
        pose = random_pose(self.rng, self.parents)
        G = snakes8.world_poses(pose[None], self.parents)[0]
        W = runtime_worlds(snakes8.ttt2_locals(G, self.parents, self.keep, self.O), self.up)
        A = self.O.T @ D
        for k, b in enumerate(self.keep):
            np.testing.assert_allclose(W[k][:3, :3], A @ G[b][:3, :3] @ P, atol=1e-9)
            np.testing.assert_allclose(W[k][:3, 3], A @ G[b][:3, 3] * 10.0, atol=1e-6)

    def test_scale_reaches_the_children(self):
        """A snake's base at half scale (Tekken 8 shrinks a snake so): its necks follow at half size, as in UE."""
        base = self.names.index('ATH_snake_B')
        pose = random_pose(self.rng, self.parents, scale_bone=base)
        G = snakes8.world_poses(pose[None], self.parents)[0]
        W = runtime_worlds(snakes8.ttt2_locals(G, self.parents, self.keep, self.O), self.up)
        A = self.O.T @ D
        for k, b in enumerate(self.keep):
            np.testing.assert_allclose(W[k][:3, :3], A @ G[b][:3, :3] @ P, atol=1e-9)
            np.testing.assert_allclose(W[k][:3, 3], A @ G[b][:3, 3] * 10.0, atol=1e-6)
        head = self.keep.index(self.names.index('ATH_head_B'))
        self.assertAlmostEqual(float(np.linalg.norm(W[head][:3, 0])), 0.5)

    def test_skinning_any_bind_rotation(self):
        """Vertices bound with one offset (the model step's) and posed with another (the animations'): the skinned
        vertex is the UE one mapped with the animations' offset (the bind's rotation cancels)."""
        A_bind, W = TR.random_rotation(self.rng), np.eye(4)
        W[:3, :3], W[:3, 3] = TR.random_rotation(self.rng), (300.0, 1200.0, -50.0)
        bind = random_pose(self.rng, self.parents)
        Gb = snakes8.world_poses(bind[None], self.parents)[0]
        Lb = snakes8.ttt2_locals(Gb, self.parents, self.keep, A_bind)
        Wb = W @ runtime_worlds(Lb, self.up)                                 # the bones' bind worlds in the model
        b = self.keep.index(self.names.index('ATH_neck_C_08'))
        v = self.rng.uniform(-20, 20, 3)                                     # cm, the snakes' space
        geo = dict(positions=v[None], normals=np.array([[0.0, 0.0, 1.0]]), tangents=np.array([[1.0, 0, 0, 1.0]]),
                   uvs=np.zeros((1, 1, 2)), joints=np.array([[self.keep[b]]]), weights=np.array([[1.0]]))
        table = snakes8.remap(self.names, self.parents, self.keep)
        streams, lost, flip = snakes8.mesh_streams(geo, self.keep, table, W, A_bind)
        self.assertTrue(flip)                                                # (D: a reflection)
        self.assertEqual(int(streams['joints'][0, 0]), b)
        anim = random_pose(self.rng, self.parents)
        Ga = snakes8.world_poses(anim[None], self.parents)[0]
        Wa = W @ runtime_worlds(snakes8.ttt2_locals(Ga, self.parents, self.keep, self.O), self.up)
        p = Wa[b] @ np.linalg.inv(Wb[b]) @ np.append(streams['pos'][0], 1.0)
        ue = Ga[self.keep[b]] @ np.linalg.inv(Gb[self.keep[b]]) @ np.append(v, 1.0)
        want = W[:3, :3] @ (self.O.T @ D @ ue[:3] * 10.0) + W[:3, 3]
        np.testing.assert_allclose(p[:3], want, atol=1e-6)

    def test_locked(self):
        pose = random_pose(self.rng, self.parents)[None].repeat(3, 0)
        ref = random_pose(self.rng, self.parents)
        out = snakes8.locked(pose, self.parents, ref)
        np.testing.assert_allclose(out[:, 0, 0:7], np.repeat(ref[None, 0, 0:7], 3, 0))
        np.testing.assert_allclose(out[:, 1:], pose[:, 1:])

    def test_world_poses_order(self):
        pose = np.zeros((1, 2, 10))
        pose[..., 3] = 1.0
        with self.assertRaises(ValueError):
            snakes8.world_poses(pose, [1, -1])


# ------------------------------------------------------------------------------------------------ part 3
class Part3Test(unittest.TestCase):
    """Snakes.part3: each clip (led by its frame 0 once more: the runtime shows index int(animator frame), 1 on the
    start property's frame; ended by REST's pose, which the runtime poses when the animation ends), REST (the roots'
    axes 0: every bone folded into the weapon bone's origin), and the continuations' copies from their first frame,
    numbered by their START_PROP values."""

    def setUp(self):
        self.names, self.parents = snake_skeleton()
        self.keep = snakes8.kept(self.names, (2, 5, 8, 11))
        self.up = snakes8.kept_parents(self.parents, self.keep)
        rng = np.random.default_rng(9)
        self.O = TR.random_rotation(rng)
        s = object.__new__(snakes8.Snakes)
        s.paths, s.keep, s.log = ['clip0', None, 'clip2'], list(self.keep), lambda line: None
        s._local = {}
        for k, F in ((0, 6), (2, 4)):
            G = snakes8.world_poses(np.stack([random_pose(rng, self.parents) for _ in range(F)]), self.parents)
            s._local[k] = (snakes8.ttt2_locals(G, self.parents, self.keep, self.O), np.zeros((F, 3, 3)))
        self.snakes = s
        skel = dict(names=['cha:HARA', 'cha:UDE_R_jnt', 'cha:OPT821_snakes'], parent=[-1, 0, 1], opt=[0, 0, 821],
                    t=np.zeros((3, 3), np.float32), r=np.zeros((3, 3), np.float32), s=np.ones((3, 3), np.float32))
        binds = s._local[0][0][0]
        self.skel, self.first = snakes8.append_bones(skel, [self.names[b] for b in self.keep], self.up, binds, 2)

    def raw(self, a):
        typ, ch, frames = struct.unpack_from('>HHI', a, 0)
        return typ, ch, np.frombuffer(a, '>f4', frames * ch * 3, 8 + 4 * ch).reshape(frames, ch, 3)

    def test_animations(self):
        plan = snakes8.Plan()
        plan.copies = [(0, 2)]
        anims, index = self.snakes.part3(plan, self.skel)
        self.assertEqual(index, {0: 0, 2: 1, snakes8.REST: 2, snakes8.COPY_FIRST: 3})
        n = len(self.keep)
        typ, ch, v = self.raw(anims[0])
        self.assertEqual((typ, ch, len(v)), (0xC8, 3 * n, 8))                # (frame 0 once more, then REST's pose)
        np.testing.assert_allclose(v[0], v[1])
        self.assertEqual(snakes8.LEAD, 1)
        for f in (3, 5):                                                     # (clip frame f = index f + 1; 5 its last)
            W = runtime_worlds(self.snakes._local[0][0][f], self.up)
            t, r, s = v[f + 1, 0::3], v[f + 1, 1::3], v[f + 1, 2::3]
            for k in range(n):
                parent = np.eye(4) if self.up[k] < 0 else W[self.up[k]]
                np.testing.assert_allclose(parent @ store_local(t[k], r[k], s[k]), W[k], atol=1e-4)
        _, _, rest = self.raw(anims[2])
        roots = [k for k in range(n) if self.up[k] < 0]
        for k in range(n):
            M = store_local(rest[0, 3 * k], rest[0, 3 * k + 1], rest[0, 3 * k + 2])
            if k in roots:
                np.testing.assert_allclose(M[:3, :3], 0)
            else:                                                            # (the others: their binds)
                np.testing.assert_allclose(M, bone.local_matrix(self.skel, self.first + k), atol=1e-5)
        _, _, copy = self.raw(anims[3])
        np.testing.assert_allclose(copy[1:-1], v[3:-1], atol=1e-6)           # (clip frames 2.., led by frame 2)
        np.testing.assert_allclose(copy[0], v[3], atol=1e-6)
        _, _, other = self.raw(anims[1])
        for a in (v, copy, other):                                           # (every one ends folded: REST's pose)
            np.testing.assert_allclose(a[-1], rest[0], atol=1e-6)
        self.assertEqual([self.skel['opt'][self.first + k] for k in range(n)], list(range(600, 600 + n)))
        self.assertEqual(snakes8.spring_numbers(types.SimpleNamespace(SNAKES={'necks': (2, 5, 8, 11)}), self.skel),
                         list(range(600, 600 + n)))
        self.assertEqual(self.skel['parent'][self.first], 2)                 # (a root: under the weapon bone)

    def test_pairs(self):
        plan = snakes8.Plan()
        plan.by_key = {0xAB: (0, 7), 0xCD: (1, 0), 0xEF: (9, 0)}             # (clip 1 has no path, 9 none at all)
        out = self.snakes.pairs(plan)
        self.assertEqual(sorted(out), [0xAB])
        self.assertEqual(out[0xAB][1], 7 + snakes8.FRAME_OFFSET)


# ------------------------------------------------------------------------------------------------ moves
class Moveset:
    """A made-up Tekken 8 moveset: moves {anim key, extraprops, cancel}, extra properties {id, frame, value},
    cancels {direction, move_id, start_frame}, end properties {id, value}."""

    def __init__(self, moves, extra, cancels=(), end=()):
        self.tables = dict(moves=[dict(m) for m in moves], extra_move_properties=[dict(r) for r in extra],
                           cancels=[dict(c) for c in cancels], move_begin_props=[],
                           move_end_props=[dict(r) for r in end])

    def anim_ref(self, i):
        return self.tables['moves'][i]['key'], 'own'

    def resolve_alias(self, mid):
        return mid

    def iter_list(self, table, start, end_test):
        t = self.tables[table]
        i = start
        while i is not None and i < len(t):
            yield i, t[i]
            if end_test(t[i]):
                return
            i += 1


END = dict(id=0, frame=0, value=0)
SNAKES_DEF = types.SimpleNamespace(SNAKES={'necks': (2, 5, 8, 11)})


def cancel(target, start=0):
    return dict(direction=0, move_id=target, start_frame=start)


class PrepareTest(unittest.TestCase):
    def moveset(self):
        """0 starts clip 3 at frame 10 (index 9), stops it as it ends; 1 continues 0 from frame 25 (a copy from clip
        frame 16: move frame 26 shows clip frame 26 - 1 - 9), its cancel's window 21..25 (made to open at 25), 2
        continues 0 from frame 5 (before the clip: its start row), 3 continues 1 from frame 40 (a copy from 31); 4
        starts clip 1 at the start in another clip; 5 plays clip 0xBB without a start of its own (not a
        continuation: another body animation)."""
        S, X = snakes8.START_PROP, snakes8.STOP_PROP
        extra = [dict(id=S, frame=10, value=3), dict(id=0x8001, frame=12, value=1), END,     # 0: rows 0..2
                 dict(id=0x8001, frame=30, value=2), END,                                   # 1: rows 3..4
                 dict(id=S, frame=snakes8.AT_START, value=1), dict(id=X, frame=40, value=0), END]   # 4: rows 5..7
        cancels = [dict(cancel(1, 25), win_start=21, win_end=25), dict(cancel(2, 5), win_start=2, win_end=2),
                   cancel(5, 3), dict(direction=0x8000, move_id=0, start_frame=0),
                   cancel(3, 40), dict(direction=0x8000, move_id=0, start_frame=0)]
        moves = [dict(key=0xAA, extraprops=0, cancel=0), dict(key=0xAA, extraprops=3, cancel=4),
                 dict(key=0xAA, extraprops=None, cancel=None), dict(key=0xAA, extraprops=None, cancel=None),
                 dict(key=0xCC, extraprops=5, cancel=None), dict(key=0xBB, extraprops=None, cancel=None)]
        return Moveset(moves, extra, cancels, end=[dict(id=X, value=0), dict(id=0x8001, value=5)])

    def rows(self, k, i):
        return [r for _, r in k.iter_list('extra_move_properties', k.tables['moves'][i]['extraprops'],
                                          lambda r: r['id'] == 0 and r['frame'] == 0)][:-1]

    def test_plan(self):
        k = self.moveset()
        lines = []
        plan = snakes8.prepare(k, SNAKES_DEF, log=lines.append)
        S = snakes8.START_PROP
        self.assertEqual(k.tables['move_end_props'][0]['id'], S)             # stops -> REST
        self.assertEqual(k.tables['move_end_props'][0]['value'], snakes8.REST)
        self.assertEqual((k.tables['extra_move_properties'][6]['id'], k.tables['extra_move_properties'][6]['value']),
                         (S, snakes8.REST))
        self.assertEqual(plan.by_key, {0xAA: (3, 9), 0xCC: (1, 0)})
        self.assertEqual(plan.copies, [(3, 16), (3, 31)])
        self.assertEqual((k.tables['cancels'][0]['win_start'], k.tables['cancels'][0]['win_end']), (25, 25))
        self.assertEqual(k.tables['cancels'][1]['win_start'], 2)             # (a window after its start: as it is)
        self.assertTrue(any('windows made to open' in line for line in lines))
        one = self.rows(k, 1)
        self.assertEqual(one[0]['value'], 2)                                 # (its own rows kept, first)
        self.assertEqual((one[-1]['id'], one[-1]['frame'], one[-1]['value']), (S, snakes8.AT_START,
                                                                                snakes8.COPY_FIRST))
        two = self.rows(k, 2)
        self.assertEqual([(r['id'], r['frame'], r['value']) for r in two], [(S, 10, 3)])
        three = self.rows(k, 3)
        self.assertEqual(three[-1]['value'], snakes8.COPY_FIRST + 1)
        self.assertIsNone(k.tables['moves'][5]['extraprops'])
        self.assertEqual(sorted(plan.moves), [0, 1, 2, 3, 4])
        self.assertTrue(any('continuations' in line for line in lines))

    def test_without_snakes(self):
        k = self.moveset()
        self.assertIsNone(snakes8.prepare(k, types.SimpleNamespace(), log=lambda s: None))
        self.assertEqual(k.tables['move_end_props'][0]['id'], snakes8.STOP_PROP)

    def test_start_index(self):
        self.assertEqual([snakes8.start_index(f) for f in (snakes8.AT_START, 1, 25, 0x8002, 0)], [0, 0, 24, None,
                                                                                                    None])


class ConverterHookTest(unittest.TestCase):
    """Tekken 8's start of a summoned model's clip (TIGER_PROP 't8') -> 0x82de 0x4000 + its part-3 index, only for a
    fighter whose converter has those animations (opt_anims), never held to the values TTT2's movesets pass."""

    def converter(self, opt_anims):
        c = moveset.Converter.__new__(moveset.Converter)
        c.game, c.opt_anims, c.flag_props, c.gauge = 't8', dict(opt_anims), {}, None
        c.defn = types.SimpleNamespace(MOVESET={})
        return c

    def test_mapped(self):
        c = self.converter({3: 0, snakes8.REST: 16, snakes8.COPY_FIRST: 17})
        self.assertEqual(moveset.TIGER_PROP['t8'], snakes8.START_PROP)
        self.assertEqual(c.map_prop(snakes8.START_PROP), moveset.OPT_ANIM_PROP)
        self.assertEqual(c.conv_value(snakes8.START_PROP, 3), moveset.OPT_ANIM_BASE)
        self.assertEqual(c.conv_value(snakes8.START_PROP, snakes8.REST), moveset.OPT_ANIM_BASE + 16)
        self.assertEqual(c.conv_value(snakes8.START_PROP, snakes8.COPY_FIRST), moveset.OPT_ANIM_BASE + 17)
        self.assertIsNone(c.conv_value(snakes8.START_PROP, 0x10000))        # (a Rage Art's: none)
        self.assertFalse(c.guarded(snakes8.START_PROP))

    def test_others_unchanged(self):
        c = self.converter({})
        self.assertTrue(c.guarded(snakes8.START_PROP))


# ------------------------------------------------------------------------------------------------ the heads' pair
class HeadsPairTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(13)
        self.F = 6
        self.WR = np.stack([np.array([TR.random_rotation(rng) for _ in range(2)]) for _ in range(self.F)])
        self.Wp = rng.uniform(-500, 500, (self.F, 2, 3))
        self.O = TR.random_rotation(rng)
        spec = dict(kind='snakes', driver='Drv', offset=self.O, anchor='Drv',
                    bind=(np.array([1.0, 2.0, 3.0]), np.eye(3)))
        self.conv = types.SimpleNamespace(sub=types.SimpleNamespace(index={'Drv': 0, 'X': 1}), pairs=[spec],
                                          scale=1.0, kind=animation.COMPRESSED)
        self.H = rng.uniform(-1500, 1500, (4, 3, 3))

    def test_most_forward_head_from_the_start(self):
        start = 2
        out = T8.pair_values(self.conv, self.WR, self.Wp, TR.smooth_values(self.F), 1.0, None, 1, (self.H, start))
        t = out[:, 0]
        for f in range(self.F):
            g = min(max(f - start, 0), len(self.H) - 1)
            world = np.einsum('ij,mj->mi', self.WR[f, 0] @ self.O, self.H[g])
            np.testing.assert_allclose(t[f], self.H[g][np.argmax(world[:, 2])], atol=1e-9)
        R = animation.local_rotation(out[:, 1], animation.COMPRESSED)
        np.testing.assert_allclose(R, np.repeat(np.eye(3)[None], self.F, 0), atol=1e-9)

    def test_heads_in(self):
        """snakes8.heads_in: (frames, heads, 3), frame by frame (not heads by frames: a clip's heads indexed by
        frame number gave her hit point another head's place of another frame), O^T D x 10."""
        rng = np.random.default_rng(21)
        G = np.repeat(np.eye(4)[None, None], 5, 0).repeat(7, 1)
        G[:, :, :3, 3] = rng.uniform(-300, 300, (5, 7, 3))
        out = snakes8.heads_in(G, [6, 2, 4], self.O)
        self.assertEqual(out.shape, (5, 3, 3))
        for f in range(5):
            for m, b in enumerate([6, 2, 4]):
                np.testing.assert_allclose(out[f, m], self.O.T @ snakes8.D @ G[f, b, :3, 3] * 10.0, atol=1e-9)

    def test_bind_without_heads(self):
        out = T8.pair_values(self.conv, self.WR, self.Wp, TR.smooth_values(self.F), 1.0, None, 1)
        np.testing.assert_allclose(out[:, 0], np.repeat([[1.0, 2.0, 3.0]], self.F, 0))

    def test_specs(self):
        """A weapon with 'snakes' under a driven bone: its kind, no joint of its own."""
        sk = types.SimpleNamespace(index={n: i for i, n in enumerate(['C_Leg', 'R_LowerArm'])})
        cal = types.SimpleNamespace(drivers={'UDE_R_jnt': 'R_LowerArm'}, offsets={'UDE_R_jnt': np.eye(3)})
        w = [dict(bone='snake', parent='UDE_R_jnt', pair=0, snakes=True)]
        bon = TR.ttt2_bon()
        bon['opt'] = [0] * len(bon['names'])
        if 'UDE_R_jnt' not in [n[4:] for n in bon['names']]:
            self.skipTest('the made-up skeleton has no UDE_R_jnt')
        hw = bone.world_matrices(bon)
        bon = weapons.append_tekken8(bon, w[0], hw[weapons.parent_index(bon, 'UDE_R_jnt')])[0]
        specs = T8.pair_specs(sk, bon, w, cal)
        self.assertEqual(specs[0]['kind'], 'snakes')
        self.assertEqual(T8.pair_joints(specs), ['R_LowerArm'])


class ProviderTest(unittest.TestCase):
    def test_snakes_clips_converted_with_their_heads(self):
        calls = []
        conv = types.SimpleNamespace(animation=lambda blob, **kw: calls.append(kw) or b'x', pairs=[1], last_pairs=1)
        banks = types.SimpleNamespace(blob=lambda cat, key: b'clip', where=lambda cat, key: 'own')
        heads = (np.zeros((2, 3, 3)), 4)
        p = T8.Animations(banks, conv, originals={5: 0x1}, roots={6: [(0.0, 0.0, 0.0)]}, snakes={5: heads, 6: heads})
        self.assertEqual(p(5, 'own'), b'x')                                  # (TTT2's original left aside)
        p(6, 'own')
        p(7, 'own')
        self.assertEqual([sorted(kw) for kw in calls], [['snakes'], ['roots', 'snakes'], []])
        self.assertEqual(p.stats['body animations with weapon pairs (snakes\' heads too)'], 1)


# ------------------------------------------------------------------------------------------------ the bone room
class RoomTest(unittest.TestCase):
    def test_cloth_most(self):
        """cloth.add takes the definition's own cloth bones at most (CLOTH_BONES) in place of MAX_BONES."""
        made = []

        def rig(k, cloths, log, spacing, link):
            made.append(spacing)
            return [dict(bones=list(range(110 if spacing <= cloth.SPACING else 60)))]
        old = cloth.rig
        cloth.rig = rig
        try:
            k = {'bones': {'names': []}, 'prims': [{key: np.zeros((1, 3)) for key in
                                                    ('pos', 'nrm', 'tan', 'joints', 'weights')}]}
            out = cloth.add(k, [{}], room=200, log=lambda s: None, most=124)
            self.assertEqual(sum(len(c['bones']) for c in out), 110)
            made.clear()
            out = cloth.add(k, [{}], room=200, log=lambda s: None)             # (MAX_BONES: spread wider)
            self.assertEqual(sum(len(c['bones']) for c in out), 60)
        finally:
            cloth.rig = old

    def test_her_room(self):
        """Miary Zo's bone room holds her cloth, weapons (with the two root points) and snakes besides a body."""
        d = miary_zo
        extra = d.CLOTH_BONES + model.weapon_bones(d.WEAPONS) + 4 + snakes8.bone_count(d)
        self.assertLess(extra, d.SKELETON_BONES)
        self.assertGreater(d.SKELETON_BONES, cloth.SKELETON)
        self.assertFalse('cloth_spare' in d.TEKKEN8)
        self.assertEqual(snakes8.weapon(d)['summon'], next(w['summon'] for w in d.WEAPONS if w.get('snakes')))
        self.assertTrue(snakes8.weapon(d).get('still'))


if __name__ == '__main__':
    unittest.main()
