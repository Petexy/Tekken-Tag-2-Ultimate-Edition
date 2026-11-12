"""A Tekken 8 fighter's own hands: TTT2's hand animation format (ttt2/motion.py), the clips' conversion
(tekken8/anim.py HandFrames), the moves' rows (convert/moveset.py), the dark metal of a weapon (tekken8/bake.py).
Made-up numbers only."""
import struct
import types
import unittest

import numpy as np

from ttt2char.convert import moveset, retarget
from ttt2char.tekken8 import anim, bake
from ttt2char.ttt2 import animation, motion


def wrapped(a, b):
    return np.abs(((np.asarray(a) - np.asarray(b) + 32768) & 0xFFFF) - 32768)


def walk(frames, step=900, seed=1):
    r = np.random.RandomState(seed)
    v = np.cumsum(r.randint(-step, step, (frames, motion.HAND_VALUES)), 0)
    return ((v + 32768) & 0xFFFF) - 32768


def container(a):
    """A hands container of the one animation a."""
    head = struct.pack('<HHHH', 1, 1, 15, 15) + struct.pack('<I', 72) + struct.pack('<15H', *[8] * 15) + \
        struct.pack('<15H', *range(15))
    return head + a


class HandAnimationTest(unittest.TestCase):
    def test_round_trip(self):
        """First and last frames exact, those between within half the stored step, at every length around a block."""
        for frames in (1, 2, 3, 4, 16, 17, 18, 19, 33, 34, 35, 100, 932):
            v = walk(frames)
            d = np.array(motion.decode_hand_animation(motion.encode_hand_animation(v.tolist())))
            self.assertEqual(d.shape, v.shape)
            np.testing.assert_array_equal(d[0], v[0])
            np.testing.assert_array_equal(d[-1], v[-1])
            self.assertLessEqual(wrapped(d, v).max(), 8)

    def test_large_jumps_and_stills(self):
        """A jump past what a delta holds takes the absolute code; a still value costs almost nothing."""
        v = np.zeros((40, motion.HAND_VALUES), int)
        v[20:, 3] = 30000
        v[25:, 4] = -30000
        a = motion.encode_hand_animation(v.tolist())
        self.assertLessEqual(wrapped(motion.decode_hand_animation(a), v).max(), 8)
        still = motion.encode_hand_animation(np.zeros((400, motion.HAND_VALUES), int).tolist())
        self.assertLess(len(still), 25 * motion.HAND_VALUES * 2 * 2 + 300)

    def test_block_table(self):
        """The header: u16 frames, two poses, ((frames + 14) >> 4) word offsets, each at a chunk."""
        v = walk(50)
        a = motion.encode_hand_animation(v.tolist())
        self.assertEqual(struct.unpack_from('<H', a, 0)[0], 50)
        n = motion.HAND_VALUES
        offs = struct.unpack_from('<4H', a, 2 + 4 * n)
        self.assertEqual(offs[0] * 2, 2 + 4 * n + 2 * ((50 + 14) >> 4))
        self.assertEqual(sorted(offs), list(offs))

    def test_refuses_a_wrong_shape(self):
        with self.assertRaises(ValueError):
            motion.encode_hand_animation([[0] * 44])

    def test_hand_frames_replaced(self):
        """The hand shapes (a hands container of one animation) with some frames replaced, the others as they were."""
        v = walk(40)
        h = container(motion.encode_hand_animation(v.tolist()))
        row = list(range(motion.HAND_VALUES))
        out = motion.with_hand_frames(h, {1: row, 7: row})
        self.assertEqual(out[:72], h[:72])
        d = np.array(motion.decode_hand_animation(motion.hand_animations(out)[0]))
        self.assertEqual(len(d), 40)
        for f in (1, 7):
            self.assertLessEqual(wrapped(d[f], row).max(), 8)
        for f in set(range(40)) - {1, 7}:
            self.assertLessEqual(wrapped(d[f], v[f]).max(), 16)

    def test_container_of_several_refused(self):
        h = motion.extend_hands(container(motion.encode_hand_animation(walk(4).tolist())), [b'\1\0'])
        with self.assertRaises(ValueError):
            motion.with_hand_frames(h, {0: [0] * motion.HAND_VALUES})


class Joint:
    def __init__(self, q):
        self.rotation, self.stored_rotation = q, True


class Clip:
    def __init__(self, frames, joints):
        self.frames, self._j = frames, joints

    def joints(self):
        return self._j


def hand_skeleton():
    """A hand on a root, each finger's chain with an identity bind."""
    names = ['R_Hand']
    parents = [-1]
    for f in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
        up = 0
        for k in (0, 1, 2) if f == 'Thumb' else (0, 1, 2, 3):
            names.append('R_%s%d' % (f, k))
            parents.append(up)
            up = len(names) - 1
    n = len(names)
    return retarget.Skeleton(names, parents, np.zeros((n, 3)), np.repeat(np.eye(3)[None], n, 0), np.ones((n, 3)))


def frames_of(sk):
    f = anim.HandFrames.__new__(anim.HandFrames)
    f.sk = sk
    f.wrist = {'R': np.eye(3)}
    f.base = {'R': np.eye(3)}
    f.fingers = {'R': [np.eye(3)] * len(anim.HAND_JOINTS)}
    return f


def about_z(angle):
    return np.array([0.0, 0.0, np.sin(angle / 2), np.cos(angle / 2)])


class HandClipTest(unittest.TestCase):
    def setUp(self):
        self.sk = hand_skeleton()
        self.frames = frames_of(self.sk)

    def rotations(self, v):
        return animation.local_rotation(v.astype(np.float64).reshape(-1, 15, 3) * np.pi / 32768, animation.COMPRESSED)

    def test_bind_is_no_turn(self):
        v = self.frames.values(Clip(3, {'R_Index1': Joint(np.repeat(np.array([[0, 0, 0, 1.0]]), 3, 0))}))
        self.assertEqual(v.shape, (3, 45))
        self.assertLessEqual(np.abs(v).max(), 1)

    def test_curl_reaches_its_channel(self):
        """A joint's turn is its bone's channel (index 2 = channel 4), the turn back again in the next one's."""
        q = np.array([about_z(a) for a in (0.2, 0.6, 1.0)])
        v = self.frames.values(Clip(3, {'R_Index2': Joint(q)}))
        L = self.rotations(v)
        want = animation.quaternion_to_matrix(q)
        np.testing.assert_allclose(L[:, 4], want, atol=1e-3)
        np.testing.assert_allclose(L[:, 3], np.repeat(np.eye(3)[None], 3, 0), atol=1e-3)
        np.testing.assert_allclose(L[:, 5], np.repeat(np.eye(3)[None], 3, 0), atol=1e-3)

    def test_metacarpal_goes_to_the_first_bone(self):
        """The metacarpal has no bone: its turn is on the finger's first."""
        q = np.array([about_z(0.5)])
        v = self.frames.values(Clip(1, {'R_Middle0': Joint(q)}))
        np.testing.assert_allclose(self.rotations(v)[0, 6], animation.quaternion_to_matrix(q)[0], atol=1e-3)

    def test_left_hand_values(self):
        """The game reads a left hand's values as -x, y, -z."""
        sk = retarget.Skeleton([n.replace('R_', 'L_') for n in self.sk.names], self.sk.parents, self.sk.t, self.sk.R, self.sk.s)
        f = frames_of(sk)
        for side in ('L',):
            f.wrist[side], f.base[side], f.fingers[side] = f.wrist['R'], f.base['R'], f.fingers['R']
        q = np.array([about_z(a) for a in (0.2, 0.6, 1.0)])
        left = f.values(Clip(3, {'L_Index2': Joint(q)}))
        right = self.frames.values(Clip(3, {'R_Index2': Joint(q)}))
        np.testing.assert_array_equal(left[:, 12 + 0], -right[:, 12 + 0])
        np.testing.assert_array_equal(left[:, 12 + 1], right[:, 12 + 1])
        np.testing.assert_array_equal(left[:, 12 + 2], -right[:, 12 + 2])

    def test_both_hands_refused(self):
        q = np.array([[0, 0, 0, 1.0]])
        with self.assertRaises(ValueError):
            self.frames.values(Clip(1, {'R_Index1': Joint(q), 'L_Index1': Joint(q)}))


class Textures:
    def __init__(self, rma):
        self.rma = rma

    def exists(self, path):
        return path == 'RMA'

    def image(self, path, max_size=None):
        return self.rma, False


class DarkMetalTest(unittest.TestCase):
    def setUp(self):
        rma = np.zeros((1, 2, 3), np.uint8)
        rma[0, :, 0] = (51, 51)                                     # roughness
        rma[0, :, 1] = (255, 0)                                     # metal, not metal
        rma[0, :, 2] = (255, 255)
        self.tex = Textures(rma)
        self.eff = dict(textures={'RMA_A': 'RMA'}, vectors={}, scalars={})

    def test_only_the_metal_darkens(self):
        rgb = np.full((1, 2, 3), 0.8, np.float32)
        out = bake.dark_metal(rgb, self.eff, self.tex, (0.1, 0.5, 0.25, 1.0))
        np.testing.assert_allclose(out[0, 0], 0.08, atol=1e-5)
        np.testing.assert_allclose(out[0, 1], 0.8, atol=1e-5)

    def test_other_greys_take_their_own_factor(self):
        rgb = np.full((1, 2, 3), 0.8, np.float32)
        out = bake.dark_metal(rgb, self.eff, self.tex, (0.1, 0.5, 0.25, 0.5))
        np.testing.assert_allclose(out[0, 0], 0.08, atol=1e-5)
        np.testing.assert_allclose(out[0, 1], 0.4, atol=1e-5)

    def test_coloured_texels_stay(self):
        rgb = np.array([[[0.8, 0.0, 0.5], [0.8, 0.0, 0.5]]], np.float32)
        out = bake.dark_metal(rgb, self.eff, self.tex, (0.1, 0.5, 0.25, 0.5))
        np.testing.assert_allclose(out, rgb, atol=1e-5)

    def test_no_map_no_change(self):
        rgb = np.full((1, 2, 3), 0.8, np.float32)
        self.assertIs(bake.dark_metal(rgb, dict(textures={}), self.tex, (0.1, 0.5, 0.25, 1.0)), rgb)

    def test_shine(self):
        plain = bake.specular(self.eff, self.tex).astype(float)
        dark = bake.specular(self.eff, self.tex, dark=(0.1, 0.5, 0.25, 1.0)).astype(float)
        self.assertAlmostEqual(dark[0, 0, 0], plain[0, 0, 0] * 0.5, delta=1)
        self.assertAlmostEqual(dark[0, 0, 1], plain[0, 0, 1] * 0.25, delta=1)
        self.assertEqual(dark[0, 1, 0], plain[0, 1, 0])
        self.assertEqual(dark[0, 0, 3], plain[0, 0, 3])


class HandRowsTest(unittest.TestCase):
    def test_with_props_drops(self):
        c = moveset.Converter.__new__(moveset.Converter)
        c.T = {'extra_move_properties': [dict(frame=1, id=0x82d7, value=5), dict(frame=2, id=0x9999, value=6),
                                         dict(frame=0, id=0, value=0)]}
        at = c.with_props(0, [dict(frame=0x8001, id=0x82dc, value=0x4001)], drop=moveset.HAND_ROWS)
        self.assertEqual(c.T['extra_move_properties'][at:], [
            dict(frame=2, id=0x9999, value=6), dict(frame=0x8001, id=0x82dc, value=0x4001), dict(frame=0, id=0, value=0)])

    def test_no_hands_no_change(self):
        """A fighter without hand clips (hands8) is left as it is."""
        c = moveset.Converter.__new__(moveset.Converter)
        c.hands8 = None
        self.assertIsNone(c.hands8_generic())

    def test_hand_shapes_from_the_stance(self):
        c = moveset.Converter.__new__(moveset.Converter)
        c.d = types.SimpleNamespace(tables={'moves': []})
        c.T = {'moves': []}
        c.posed_hands = {}
        c.hand8_shapes = {}
        c.prefix = 'Abc'
        c.kn = {'Abc_sKAM00_': 0}
        c.k = types.SimpleNamespace(tables={'moves': [dict(extraprops=0)]})
        c.xp_rows = lambda start: [(0x8001, 0x8610, 5, None), (0x8001, 0x8611, 6, None), (0x8001, 0x9999, 7, None)]
        c.hands8 = types.SimpleNamespace(values=lambda v: np.full((2, 45), v))
        c.hands8_generic()
        self.assertEqual(c.hand8_shapes[moveset.HAND_SHAPE_LEFT], [5] * 45)
        self.assertEqual(c.hand8_shapes[moveset.HAND_SHAPE_RIGHT], [6] * 45)
        for frame in moveset.HAND_SHAPES_OPEN:                                  # (closed, not the donor's open hand)
            self.assertEqual(c.hand8_shapes[frame], [6] * 45)
        self.assertNotIn(0, c.hand8_shapes)

    def test_numbers_after_the_donors(self):
        c = moveset.Converter.__new__(moveset.Converter)
        c.hand_anims, c._hand8_numbers = [], None
        two = motion.extend_hands(container(b'\2\0' + bytes(100)), [b'\2\0' + bytes(100)])
        c.donor_pack = motion.build_pack([b'', two, b'', b'', b'', b''])
        self.assertEqual(c.hand8_number(b'a'), moveset.HAND_OWN | 2)
        self.assertEqual(c.hand8_number(b'b'), moveset.HAND_OWN | 3)
        self.assertEqual(c.hand8_number(b'a'), moveset.HAND_OWN | 2)
        self.assertEqual(c.hand_anims, [b'a', b'b'])


if __name__ == '__main__':
    unittest.main()
