"""Unit tests of ttt2char.convert.retarget on made-up skeletons (no game files needed): a TTT2-like skeleton in a
T-pose with random joint axes, and a source made of it in an A-pose, with other random joint axes, other units and
size; poses through the source come back as the same TTT2 channels.

    python3 -m pytest -q tools/characters/tests/test_retarget.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import retarget as RT  # noqa: E402
from ttt2char.ttt2 import animation, bone  # noqa: E402

# bones 0..21 of every TTT2 skeleton: name, parent, T-pose position (mm, before the size scale)
TTT2_BONES = [('HARA_ROT1', -1, (0, 1150, 0)), ('MUNE1_jnt', 0, (0, 1150, 0)), ('MUNE2_jnt', 1, (0, 1272, 0)),
              ('KOSHI_jnt', 0, (0, 1150, 0)), ('KUBI_jnt', 2, (0, 1487, 0)), ('ATAMA_jnt', 4, (0, 1562, 0))]
for _s, _x in (('R', -1), ('L', 1)):
    TTT2_BONES += [('SAKOTSU_%s_jnt' % _s, 2, (94 * _x, 1478, 0)), ('KATA_%s_jnt' % _s, None, (183 * _x, 1478, 0)),
                   ('UDE_%s_jnt' % _s, None, (488 * _x, 1479, 0)), ('TE_%s_jnt' % _s, None, (722 * _x, 1479, 0))]
for _s, _x in (('R', -1), ('L', 1)):
    TTT2_BONES += [('MOMO_%s_jnt' % _s, 3, (98 * _x, 990, 0)), ('HIZA_%s_jnt' % _s, None, (98 * _x, 557, 0)),
                   ('ASHI_%s_jnt' % _s, None, (98 * _x, 130, 0))]
TTT2_BONES += [('TSUMASAKI_R_jnt', 16, (-98, 50, 80)), ('TSUMASAKI_L_jnt', 19, (98, 50, 80))]
TTT2_BONES = [(n, (i - 1 if p is None else p), xyz) for i, (n, p, xyz) in enumerate(TTT2_BONES)]


def rot_about(axis, angle):
    a = np.asarray(axis, np.float64) / np.linalg.norm(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * K @ K


def random_rotation(rng):
    return rot_about(rng.normal(size=3), rng.uniform(0, np.pi))


def locals_of(parents, WR, Wp):
    """Local rotations and translations of world ones."""
    n = len(parents)
    R, t = np.zeros((n, 3, 3)), np.zeros((n, 3))
    for i, p in enumerate(parents):
        R[i] = WR[i] if p < 0 else WR[p].T @ WR[i]
        t[i] = Wp[i] if p < 0 else WR[p].T @ (Wp[i] - Wp[p])
    return R, t


def ttt2_bon(scale=0.98, seed=1):
    """A bone.read()-like TTT2 skeleton: bones 0..21, T-pose, random bind axes (HARA_ROT1 the identity)."""
    rng = np.random.default_rng(seed)
    names = ['cha:' + n for n, p, xyz in TTT2_BONES]
    parents = [p for n, p, xyz in TTT2_BONES]
    Wp = np.array([xyz for n, p, xyz in TTT2_BONES], np.float64) * scale
    WR = np.array([np.eye(3)] + [random_rotation(rng) for _ in TTT2_BONES[1:]])
    R, t = locals_of(parents, WR, Wp)
    return dict(names=names, parent=parents, t=t, r=np.array([bone.euler_xyz_from_matrix(m) for m in R]),
                scale=scale, s=np.full((len(names), 3), scale))


def a_pose(sk, arm_down=45, forearm_fwd=15, leg_out=6):
    """World rotations / positions of a TTT2 skeleton's bind re-posed to an A-pose as Tekken 8 binds: arms down
    about the forward axis, forearms forward, legs out with the soles kept flat (each turn keeps the frame rules)."""
    WR, Wp = sk.bind_world()
    WR, Wp = WR.copy(), Wp.copy()
    kids = {i: {i} for i in range(len(sk.names))}
    for i in sk.order[::-1]:
        if sk.parents[i] >= 0:
            kids[sk.parents[i]] |= kids[i]

    def turn(root, m):
        piv = Wp[root].copy()
        for i in kids[root]:
            WR[i] = m @ WR[i]
            Wp[i] = piv + m @ (Wp[i] - piv)
    for s, sign in (('L', -1), ('R', 1)):
        turn(sk.index['KATA_%s_jnt' % s], rot_about([0, 0, 1], np.radians(sign * arm_down)))
        e, w = sk.index['UDE_%s_jnt' % s], sk.index['TE_%s_jnt' % s]
        turn(e, rot_about(np.cross(Wp[w] - Wp[e], [0, 0, 1.0]), np.radians(forearm_fwd)))
        turn(sk.index['MOMO_%s_jnt' % s], rot_about([0, 0, 1], np.radians(-sign * leg_out)))
        turn(sk.index['ASHI_%s_jnt' % s], rot_about([0, 0, 1], np.radians(sign * leg_out)))
    return WR, Wp


def source_of(sk, size=1.1, unit=0.1, seed=2):
    """A source skeleton of a TTT2 Skeleton: the same joints in an A-pose, random joint axes Q (its bind world =
    A-pose x Q), size x larger in units of `unit` mm. -> (Skeleton, Q, size * unit)."""
    rng = np.random.default_rng(seed)
    WR, Wp = a_pose(sk)
    Q = np.array([random_rotation(rng) for _ in sk.names])
    f = size * unit
    R, t = locals_of(sk.parents, WR @ Q, Wp * f)
    return RT.Skeleton(sk.names, sk.parents, t, R), Q, f


def smooth_values(frames, seed=3):
    """TTT2 0x64 body channel values: smooth random rotations, root motion and a turning yaw."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, frames)
    v = np.zeros((frames, 23, 3))
    for c, d in enumerate(animation.BODY_DESCRIPTORS):
        if animation.is_rotation(d):
            a, b = rng.normal(size=3), rng.normal(size=3) * 0.6
            mats = np.array([rot_about(a + b * x, 0.4 + 1.2 * x) for x in t])
            v[:, c] = animation.axis_angles(mats)
    yaw = 1.3 * np.sin(2 * t)
    v[:, 2] = np.stack([np.full(frames, -np.pi / 2), np.zeros(frames), -yaw], 1)
    v[:, 0] = np.stack([300 * t, np.zeros(frames), 900 * t * t], 1)
    v[:, 1] = np.stack([20 * np.sin(5 * t), 1050 + 60 * np.cos(3 * t), -15 * t], 1)
    v[:, 6] = (-400, 0, 0)
    return v


def source_motion(sk, Q, f, values):
    """The source's frames of a TTT2 pose: world rotations of every joint (TTT2's before the turn x Q), the hara's
    position above the displaced origin, the displacement (source units) and the yaw."""
    WR, Wp = RT.pose(sk, values, animation.COMPRESSED, root_motion=False)
    world = {n: WR[:, i] @ Q[i] for i, n in enumerate(sk.names)}
    T = animation.local_rotation(values[:, 2], animation.COMPRESSED)
    yaw = np.arctan2(T[:, 0, 2], T[:, 2, 2])
    return world, Wp[:, RT.HARA] * f, values[:, 0] * sk.scale * f, yaw


class Fixture(unittest.TestCase):
    def setUp(self):
        self.bon = ttt2_bon()
        self.sk = RT.ttt2_skeleton(self.bon)
        self.src, self.Q, self.f = source_of(self.sk)
        self.landmarks = dict(RT.TTT2_LANDMARKS)
        self.drivers = {n: n for n in RT.RULES if n != 'HARA_ROT1'}


class SkeletonTest(Fixture):
    def test_ttt2_skeleton(self):
        self.assertEqual(self.sk.names[0], 'HARA_ROT1')
        self.assertAlmostEqual(self.sk.scale, 0.98, 6)
        WR, Wp = self.sk.bind_world()
        np.testing.assert_allclose(Wp[self.sk.index['TE_L_jnt']], np.array([722, 1479, 0]) * 0.98, atol=1e-6)
        W = bone.world_matrices(self.bon)
        np.testing.assert_allclose(WR, W[:, :3, :3], atol=1e-9)

    def test_chain_fk_matches_full(self):
        rng = np.random.default_rng(5)
        LR = np.array([[random_rotation(rng) for _ in self.src.names] for _ in range(3)])
        want = [self.src.index['TE_L_jnt'], self.src.index['ASHI_R_jnt']]
        WR, Wp = self.src.fk(LR)
        WRs, Wps = self.src.fk(LR, joints=want)
        for i in self.src.chain(want):
            np.testing.assert_allclose(WRs[:, i], WR[:, i], atol=1e-12)
            np.testing.assert_allclose(Wps[:, i], Wp[:, i], atol=1e-9)
        self.assertEqual(self.src.chain([self.src.index['UDE_L_jnt']])[:3], [0, 1, 2])

    def test_scales_carry_children(self):
        sk = RT.Skeleton(['a', 'b'], [-1, 0], [[0, 0, 0], [10, 0, 0]], np.repeat(np.eye(3)[None], 2, 0),
                         [[2, 2, 2], [1, 1, 1]])
        self.assertAlmostEqual(sk.bind_world()[1][1, 0], 20.0)

    def test_parent_loop(self):
        with self.assertRaises(ValueError):
            RT.Skeleton(['a', 'b'], [1, 0], np.zeros((2, 3)), np.repeat(np.eye(3)[None], 2, 0))

    def test_leg_length(self):
        self.assertAlmostEqual(RT.leg_length(self.bon), 860.0, 6)

    def test_anatomical_frame(self):
        P = {'a': np.zeros(3), 'b': np.array([0, 0, 5.0]), 'c': np.array([1.0, 0, 1.0])}
        F = RT.anatomical_frame(P, (('a', 'b'), ('a', 'c')))
        np.testing.assert_allclose(F, np.stack([[0, 0, 1], [1, 0, 0], [0, 1, 0]], 1), atol=1e-12)
        with self.assertRaises(ValueError):
            RT.anatomical_frame(P, (('a', 'b'), 'fwd'))


class CalibrationTest(Fixture):
    def test_recovers_axes(self):
        cal = RT.Calibration(self.src, self.landmarks, self.drivers, self.sk)
        for b in self.drivers:                          # O_b = Q_b^T: the source's axes cancel
            self.assertLess(RT.angle(cal.offsets[b], self.Q[self.sk.index[b]].T), 1e-6, b)

    def test_unknown_joint(self):
        with self.assertRaises(ValueError):
            RT.Calibration(self.src, self.landmarks, {'KUBI_jnt': 'nothing'}, self.sk)

    def test_drivers_of_bones_the_skeleton_lacks_are_ignored(self):
        cal = RT.Calibration(self.src, self.landmarks, dict(self.drivers, NOT_A_BONE='KUBI_jnt'), self.sk)
        self.assertNotIn('NOT_A_BONE', cal.drivers)


class ChannelsTest(Fixture):
    def convert(self, drivers, kind=animation.COMPRESSED, frames=24):
        v = smooth_values(frames)
        cal = RT.Calibration(self.src, self.landmarks, drivers, self.sk)
        world, root, D, yaw = source_motion(self.sk, self.Q, self.f, v)
        out = RT.body_channels(cal, world, root, D, yaw, 1 / (self.sk.scale * self.f), kind)
        return v, out

    def test_round_trip(self):
        v, out = self.convert(self.drivers)
        W0, P0 = RT.pose(self.sk, v, animation.COMPRESSED)
        W1, P1 = RT.pose(self.sk, out, animation.COMPRESSED)
        body = list(range(1, 22))                       # HARA_ROT1 itself keeps the identity
        self.assertLess(RT.angle(W1[:, body], W0[:, body]).max(), 1e-6)
        self.assertLess(np.abs(P1 - P0).max(), 1e-6)
        np.testing.assert_allclose(out[:, 0], v[:, 0] * [1, 0, 1], atol=1e-6)
        np.testing.assert_allclose(out[:, 1], v[:, 1], atol=1e-6)
        np.testing.assert_allclose(out[:, 6], 0.0)      # the spine post-process off
        np.testing.assert_allclose(out[:, 3], 0.0, atol=1e-12)
        T0 = animation.local_rotation(v[:, 2], animation.COMPRESSED)
        T1 = animation.local_rotation(out[:, 2], animation.COMPRESSED)
        self.assertLess(RT.angle(T0, T1).max(), 1e-6)

    def test_hara_driven(self):
        v, out = self.convert(dict(self.drivers, HARA_ROT1='HARA_ROT1'))
        W0, _ = RT.pose(self.sk, v, animation.COMPRESSED)
        W1, _ = RT.pose(self.sk, out, animation.COMPRESSED)
        self.assertLess(RT.angle(W1[:, :22], W0[:, :22]).max(), 1e-6)

    def test_raw(self):
        v, out = self.convert(self.drivers, animation.RAW)
        W0, P0 = RT.pose(self.sk, v, animation.COMPRESSED)
        W1, P1 = RT.pose(self.sk, out, animation.RAW)
        self.assertLess(RT.angle(W1[:, 1:22], W0[:, 1:22]).max(), 1e-6)
        self.assertLess(np.abs(P1 - P0).max(), 1e-6)
        np.testing.assert_allclose(out[:, 2, [0, 2]], 0.0)
        dec = animation.decode(RT.encode(out, animation.RAW))
        self.assertEqual(dec['type'], animation.RAW)
        self.assertEqual(dec['descriptors'], list(RT.RAW_DESCRIPTORS))
        self.assertEqual(set(dec['descriptors'][3:]) - {animation.TRANSLATION}, {animation.ROTATION})

    def test_bones_without_driver_keep_their_bind(self):
        drivers = {b: j for b, j in self.drivers.items() if b not in ('KUBI_jnt', 'TE_L_jnt')}
        v, out = self.convert(drivers, frames=5)
        for c, b in ((7, 'KUBI_jnt'), (16, 'TE_L_jnt')):
            L = animation.local_rotation(out[:, c], animation.COMPRESSED)
            self.assertLess(RT.angle(L, self.sk.R[self.sk.index[b]][None]).max(), 1e-6, b)

    def test_encoded(self):
        v, out = self.convert(self.drivers)
        b = RT.encode(out)
        dec = animation.decode(b)
        self.assertEqual(animation.header(b)['size'], len(b))
        self.assertEqual(animation.header(b)['rotation_shift'], RT.rotation_shift(out))
        W0, P0 = RT.pose(self.sk, out, animation.COMPRESSED)
        W1, P1 = RT.pose(self.sk, dec['values'], animation.COMPRESSED)
        self.assertLess(RT.angle(W1[:, :22], W0[:, :22]).max(), 0.05)    # steps of 2^shift units along a chain
        self.assertLess(np.abs(P1 - P0).max(), 1.0)


def game_world(sk, values, kind=animation.COMPRESSED):
    """World rotations (F, n, 3, 3) and positions of a TTT2 skeleton posed as the game composes the turn T with
    HARA_ROT1's H: T^T H (retarget.PREBLEND), no ground displacement."""
    v = np.asarray(values, np.float64)
    F = len(v)
    LR, Lt = np.repeat(sk.R[None], F, 0), np.repeat(sk.t[None], F, 0)
    for c, b in enumerate(animation.BODY_BONES):
        if b >= 0:
            LR[:, b] = animation.local_rotation(v[:, c], kind)
    LR[:, RT.HARA] = np.swapaxes(animation.local_rotation(v[:, 2], kind), -1, -2) @ LR[:, RT.HARA]
    Lt[:, RT.HARA] = v[:, 1] * sk.scale
    return sk.fk(LR, Lt)


def lying_next(sk, clip):
    """Frame 0 of a TTT2-like down move continuing a clip's last frame in TTT2's split: no turn, HARA_ROT1 lying (90
    degrees about x), MUNE1 and KOSHI relative to it (the same world pose)."""
    last = np.asarray(clip[-1], np.float64)
    T = animation.local_rotation(last[2][None])[0]
    H = animation.local_rotation(last[3][None])[0]
    Hn = rot_about((1, 0, 0), np.pi / 2)
    nxt = last.copy()
    nxt[2] = 0.0
    nxt[3] = animation.axis_angle_from_matrix(Hn)
    for c in RT.CHILD_CHANNELS:
        nxt[c] = animation.axis_angle_from_matrix(Hn.T @ T.T @ H @ animation.local_rotation(last[c][None])[0])
    return nxt


def preblend_end(values, nxt, kind=animation.COMPRESSED):
    """MUNE1's and KOSHI's world rotations after the game's pre-blend (the next's sampled rotations with the clip's
    turn and HARA_ROT1 kept) and as the next move starts: (pre-blend, next) for each child."""
    T = animation.local_rotation(values[-1, 2][None], kind)[0]
    H = animation.local_rotation(values[-1, 3][None], kind)[0]
    Tn = animation.local_rotation(nxt[2][None], kind)[0]
    Hn = animation.local_rotation(nxt[3][None], kind)[0]
    out = []
    for c in RT.CHILD_CHANNELS:
        Ln = animation.local_rotation(nxt[c][None], kind)[0]
        out.append((T.T @ H @ T @ Tn.T @ Ln, Tn.T @ Hn @ Ln))
    return out


class HandoffTest(Fixture):
    """A converted clip (HARA_ROT1 upright, a turn) ending lying, handed off to a TTT2 down move (HARA_ROT1 lying)."""

    def clip(self, frames=60):
        v = smooth_values(frames)
        v[:, 3] = 0.0                                   # HARA_ROT1 upright, as every converted clip
        v[:, 2, 2] = np.linspace(0, -5.5, frames)      # a turn beyond half a turn, as Reina's 1+3 throw's victim
        v[:, 6] = RT.SPINE_PARAMETER
        return v

    def test_world_kept(self):
        v = self.clip()
        nxt = lying_next(self.sk, v)
        out = RT.handoff(v, animation.COMPRESSED, nxt, animation.COMPRESSED)
        W0, P0 = game_world(self.sk, v)
        W1, P1 = game_world(self.sk, out)
        self.assertLess(RT.angle(W1[:, 1:22], W0[:, 1:22]).max(), 1e-6)    # every bone but HARA_ROT1's own frame
        self.assertLess(np.abs(P1 - P0).max(), 1e-6)
        w1 = len(v) - 1 - RT.PREBLEND - 1
        unchanged = np.abs(out - v).max((1, 2)) == 0
        self.assertTrue(unchanged[:w1 - RT.HANDOFF_WINDOW].all())             # the frames before the window
        self.assertFalse(unchanged[-1])

    def test_split_matches_the_next(self):
        v = self.clip()
        nxt = lying_next(self.sk, v)
        self.assertGreater(RT.handoff_mismatch(v, animation.COMPRESSED, nxt, animation.COMPRESSED), 80)
        out = RT.handoff(v, animation.COMPRESSED, nxt, animation.COMPRESSED)
        self.assertLess(RT.handoff_mismatch(out, animation.COMPRESSED, nxt, animation.COMPRESSED), 1e-4)
        start = len(v) - 1 - RT.PREBLEND - 1
        for c in (2, 3) + RT.CHILD_CHANNELS:              # the turn and HARA_ROT1 the next's from the pre-blend's
            R = animation.local_rotation(out[start if c < 4 else -1:, c])     # start, the children at the end
            self.assertLess(RT.angle(R, animation.local_rotation(nxt[c][None])[0]).max(), 1e-4)
            q, qn = animation.game_quaternion(out[-1, c]), animation.game_quaternion(nxt[c])
            self.assertGreater(q @ qn, 0)                    # the hemisphere the game's blend tests
        # what the pre-blend leaves MUNE1 and KOSHI in, against the next move's start: 90 degrees apart before (the
        # opponent sat up), together after
        before = max(RT.angle(a, b) for a, b in preblend_end(v, nxt))
        after = max(RT.angle(a, b) for a, b in preblend_end(out, nxt))
        self.assertGreater(before, 80)
        self.assertLess(after, 1e-4)

    def test_raw(self):
        v = self.clip()
        nxt = lying_next(self.sk, v)
        raw = animation.to_raw(list(animation.BODY_DESCRIPTORS), v).astype(np.float64)
        out = RT.handoff(raw, animation.RAW, nxt, animation.COMPRESSED)
        W0, P0 = game_world(self.sk, raw, animation.RAW)
        W1, P1 = game_world(self.sk, out, animation.RAW)
        self.assertLess(RT.angle(W1[:, 1:22], W0[:, 1:22]).max(), 1e-6)
        self.assertLess(RT.handoff_mismatch(out, animation.RAW, nxt, animation.COMPRESSED), 1e-4)

    def test_short_clip(self):
        v = self.clip(8)                                 # shorter than the pre-blend: from frame 1
        nxt = lying_next(self.sk, v)
        out = RT.handoff(v, animation.COMPRESSED, nxt, animation.COMPRESSED)
        self.assertTrue(np.array_equal(out[0], v[0]))
        self.assertLess(RT.handoff_mismatch(out, animation.COMPRESSED, nxt, animation.COMPRESSED), 1e-4)

    def test_upright_next_needs_nothing(self):
        v = self.clip()
        nxt = v[0].copy()                                 # a converted stance: HARA_ROT1 upright too
        self.assertLess(RT.handoff_mismatch(v, animation.COMPRESSED, nxt, animation.COMPRESSED), RT.HANDOFF_NEEDED)


class AxisAnglesTest(unittest.TestCase):
    def test_continues_from_prev(self):
        mats = np.array([rot_about((0, 1, 0), a) for a in (0.2, 0.3)])[:, None]
        prev = np.array([[-np.pi / 2, 0.0, -0.1 + 2 * np.pi]])     # the same axis, one turn on
        out = animation.axis_angles(mats, prev)
        self.assertEqual(out.shape, (2, 1, 3))
        self.assertTrue(np.allclose(RT.angle(animation.local_rotation(out[:, 0]), mats[:, 0]), 0, atol=1e-6))
        self.assertTrue((np.abs(out[:, 0, 2]) > np.pi).all())    # stayed on the branch it continues
        self.assertTrue((np.abs(animation.axis_angles(mats)[:, 0, 2]) < np.pi).all())


class ShiftTest(unittest.TestCase):
    def test_rotation_shift(self):
        v = np.zeros((4, 23, 3))
        self.assertEqual(RT.rotation_shift(v), 0)
        v[:, 3, 2] = 3.0
        self.assertEqual(RT.rotation_shift(v), 0)
        v[2, 3, 2] = 4.0                                # beyond pi: one more shift holds +-2 pi
        self.assertEqual(RT.rotation_shift(v), 1)
        v[2, 4, 0] = -20.0
        self.assertEqual(RT.rotation_shift(v), 3)
        v[:, 1] = 1e6                                   # translations do not count
        self.assertEqual(RT.rotation_shift(v), 3)


if __name__ == '__main__':
    unittest.main()
