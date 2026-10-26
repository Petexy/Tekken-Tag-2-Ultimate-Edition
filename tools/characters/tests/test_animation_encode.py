"""Unit tests of ttt2char.ttt2.animation's 0x64 writer (encode_compressed, compression_params, axis_angles) on made-up
animations, decoded back with the module's own decoder (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_animation_encode.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.ttt2 import animation as A  # noqa: E402

UNIT = float(A.ROTATION_UNIT)


def rot_about(axis, angle):
    a = np.asarray(axis, np.float64) / np.linalg.norm(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * K @ K


def angle(Ra, Rb):
    d = np.linalg.norm(np.asarray(Ra) - np.asarray(Rb), axis=(-2, -1))
    return np.degrees(2 * np.arcsin(np.clip(d / (2 * np.sqrt(2)), 0, 1)))


def body(frames, seed=1):
    """Smooth made-up body values: rotations as axis-angle triples, translations in mm."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, frames)
    v = np.zeros((frames, 23, 3))
    for c, d in enumerate(A.BODY_DESCRIPTORS):
        if A.is_rotation(d):
            a, b = rng.normal(size=3), rng.normal(size=3)
            v[:, c] = A.axis_angles(np.array([rot_about(a + b * x, 0.3 + 2 * x) for x in t]))
        else:
            v[:, c] = rng.normal(size=3) * 100 + np.outer(t, rng.normal(size=3) * 500)
    return v


def chunks(buf, endian='>'):
    """(block, channel, component, first 4-bit code, chunk bytes) of every chunk of a 0x64 animation."""
    h = A.header(buf, endian)
    out = []
    for b, off in enumerate(h['offsets']):
        p = h['table'] + off
        for c in range(h['nch']):
            for k in range(3):
                n = buf[p] >> 2
                code = ((buf[p] & 3) << 2 | buf[p + 1] >> 6) if n > 1 else None
                out.append((b, c, k, code, buf[p:p + n]))
                p += n
    return out


class EncodeTest(unittest.TestCase):
    def check(self, v, shift=A.ROTATION_SHIFT, endian='>', descriptors=A.BODY_DESCRIPTORS):
        buf = A.encode_compressed(list(descriptors), v, endian, rotation_shift=shift)
        h = A.header(buf, endian)
        self.assertEqual(h['size'], len(buf))
        self.assertEqual((h['type'], h['frames'], h['rotation_shift']), (A.COMPRESSED, len(v), shift))
        dec = A.decode(buf, endian)['values'].astype(np.float64)
        rot = np.array([A.is_rotation(d) for d in descriptors])
        if rot.any():
            err = angle(A.local_rotation(dec[:, rot]), A.local_rotation(v[:, rot])).max()
            # each component within half a step of 2^shift units: the angle's error plus the axis's (two
            # components) turned through up to the angle
            self.assertLess(err, np.degrees(UNIT * (1 << shift)) * 2.5 + 1e-4)
        if (~rot).any():
            step = np.abs(v[:, ~rot] - v[:1, ~rot]).max((0, 2)) / A.TRANSLATION_STEPS
            self.assertTrue((np.abs(dec[:, ~rot] - v[:, ~rot]) <= step[None, :, None] * 0.51 + 1e-3).all())
        return buf, dec

    def test_round_trip(self):
        for shift in (0, 2, 4):
            self.check(body(40), shift)

    def test_lengths(self):
        for frames in (1, 2, 15, 16, 17, 18, 33, 70):
            buf, dec = self.check(body(frames))
            self.assertEqual(len(A.header(buf)['offsets']), (frames + 14) >> 4)
            np.testing.assert_allclose(dec[0, 0], np.float32(body(frames)[0, 0]), atol=1e-3)

    def test_little_endian(self):
        self.check(body(20), endian='<')

    def test_exact(self):
        buf, dec = self.check(body(50), 3)
        p = A.compression_params(buf)
        self.assertEqual(p['rotation_shift'], 3)
        again = A.encode_compressed(list(A.BODY_DESCRIPTORS), dec, params=p)
        dec2 = A.decode(again)['values']
        self.assertTrue(np.array_equal(dec2.view(np.uint32), dec.astype(np.float32).view(np.uint32)))
        self.assertEqual(A.header(again)['size'], len(again))

    def test_exact_keeps_the_flag(self):
        buf = bytearray(A.encode_compressed(list(A.BODY_DESCRIPTORS), body(20)))
        buf[4 + 2 * 23 + 2] |= 0x80                     # the rotation flag the decoder masks off
        p = A.compression_params(bytes(buf))
        self.assertEqual(p['rotation_flag'], 1)
        again = A.encode_compressed(list(A.BODY_DESCRIPTORS), A.decode(bytes(buf))['values'], params=p)
        self.assertEqual(again[4 + 2 * 23 + 2] >> 7, 1)
        self.assertEqual(A.header(again)['rotation_flag'], 1)

    def test_constant_channels_end_early(self):
        v = body(33)
        v[:, 5] = v[0, 5]                               # a still rotation: every chunk ends with code 15
        v[:, 6] = (-400.0, 0.0, 0.0)
        buf, dec = self.check(v)
        sizes = [len(c[4]) for c in chunks(buf) if c[1] in (5, 6)]
        self.assertTrue(all(s <= 2 for s in sizes))
        np.testing.assert_allclose(dec[:, 6], np.tile([-400.0, 0, 0], (33, 1)))

    def test_holds_after_moving(self):
        v = body(17)
        v[9:, 8] = v[8, 8]                              # moves, then holds to the block's end
        buf, dec = self.check(v, 0)
        self.assertLess(angle(A.local_rotation(dec[9:, 8]), A.local_rotation(dec[8:9, 8])).max(), 1e-9)

    def test_runs(self):
        v = np.zeros((33, 23, 3))
        v[:, 3, 2] = np.arange(33) * UNIT * 3           # constant velocity: second differences all 0
        v[:, 4, 2] = (np.arange(33) ** 2) * UNIT        # constant acceleration: one repeated value
        v[:, 0] = np.outer(np.arange(33), [1.0, 0, 2.0])
        buf, dec = self.check(v, 0)
        np.testing.assert_allclose(dec[:, 4, 2], np.float32(v[:, 4, 2]), atol=UNIT)
        self.assertLess(len(buf), 700)

    def test_no_chunk_starts_with_a_run(self):
        for c in chunks(A.encode_compressed(list(A.BODY_DESCRIPTORS), body(48))):
            self.assertNotEqual(c[3], 14)

    def test_wraps_by_whole_turns(self):
        v = np.zeros((40, 23, 3))
        v[:, 3] = A.axis_angles(np.array([rot_about([0, 1, 0.2], a) for a in np.linspace(0, 9, 40)]))
        self.assertGreater(np.abs(v[:, 3]).max(), np.pi)
        buf, dec = self.check(v, 0)
        self.assertLess(angle(A.local_rotation(dec[:, 3]), A.local_rotation(v[:, 3])).max(), 0.01)

    def test_face_descriptors(self):
        desc = [A.TRANSLATION, A.ROTATION, 3, A.HINGE_Z]
        v = np.zeros((20, 4, 3))
        v[:, 0] = np.outer(np.linspace(0, 1, 20), [1.0, 2.0, 3.0])
        v[:, 2] = np.outer(np.linspace(0, 1, 20), [0.001, 0.0, 0.0])
        v[:, 3, 2] = np.linspace(0, 1.5, 20)
        self.check(v, 4, descriptors=desc)

    def test_bad_values(self):
        with self.assertRaises(ValueError):
            A.encode_compressed(list(A.BODY_DESCRIPTORS), np.zeros((3, 22, 3)))
        with self.assertRaises(ValueError):
            A.encode_compressed(list(A.BODY_DESCRIPTORS), np.zeros((0, 23, 3)))
        with self.assertRaises(ValueError):
            A.compression_params(A.encode_raw(list(A.BODY_DESCRIPTORS), np.zeros((2, 23, 3))))

    def test_chunk_writer(self):
        b = A._encode_chunk([0, 1, -4, 300, -30000])
        self.assertEqual(b[0] >> 2, len(b))
        n, vals, modes = A._chunk(b, 0, (0, 0), 5)
        self.assertEqual(vals, [0, 1, -4, 300, -30000])
        b = A._encode_chunk([7, 0, 0, 0], end_at=2)
        n, vals, modes = A._chunk(b, 0, (0, 0), 4)
        self.assertEqual(vals[:2], [7, 0])
        self.assertEqual(vals[2], A.END)


class AxisAngleTest(unittest.TestCase):
    def test_same_rotations(self):
        rng = np.random.default_rng(4)
        mats = np.array([rot_about(rng.normal(size=3), rng.uniform(0, np.pi)) for _ in range(30)])
        mats[3] = np.eye(3)
        mats[5] = rot_about([1, 2, 3], np.pi)           # half turns
        mats[6] = rot_about([0, 0, 1], np.pi)
        v = A.axis_angles(mats)
        self.assertLess(angle(A.local_rotation(v), mats).max(), 1e-6)
        self.assertTrue((np.abs(v[0]) <= np.pi + 1e-9).all())

    def test_continuous(self):
        # a spin about a fixed axis through several turns (from off the identity, whose axis is any), and an axis
        # sweeping round the horizon (y wraps)
        mats = np.array([rot_about([0.3, 1, 0], a) for a in np.linspace(0.5, 14, 200)])
        v = A.axis_angles(mats)
        self.assertLess(np.abs(np.diff(v, axis=0)).max(), 0.1)
        self.assertLess(angle(A.local_rotation(v), mats).max(), 1e-6)
        mats = np.array([rot_about([np.cos(a), 0.1, np.sin(a)], 1.0) for a in np.linspace(0, 9, 180)])
        v = A.axis_angles(mats)
        self.assertLess(np.abs(np.diff(v, axis=0)).max(), 0.2)
        self.assertLess(angle(A.local_rotation(v), mats).max(), 1e-6)

    def test_identity_stays_put(self):
        mats = np.array([rot_about([1, 0, 0], 0.5), np.eye(3), np.eye(3), rot_about([1, 0, 0], 0.4)])
        v = A.axis_angles(mats)
        np.testing.assert_allclose(v[1, :2], v[0, :2])
        self.assertLess(angle(A.local_rotation(v), mats).max(), 1e-6)

    def test_shapes(self):
        rng = np.random.default_rng(5)
        mats = np.array([[[rot_about(rng.normal(size=3), 1.0) for _ in range(3)] for _ in range(2)]
                         for _ in range(6)])
        v = A.axis_angles(mats)
        self.assertEqual(v.shape, (6, 2, 3, 3))
        self.assertLess(angle(A.local_rotation(v), mats).max(), 1e-6)
        self.assertEqual(A.axis_angles(mats[:, 0, 0]).shape, (6, 3))

    def test_matches_scalar(self):
        rng = np.random.default_rng(6)
        for _ in range(20):
            m = rot_about(rng.normal(size=3), rng.uniform(0.01, 3.1))
            np.testing.assert_allclose(A._axis_angle(m), A.axis_angle_from_matrix(m), atol=1e-9)


if __name__ == '__main__':
    unittest.main()
