"""Unit tests of ttt2char.convert.face (face animations moved with an added fighter's face joints, its eyelids turned as
its own game turns them) and skin.gained, on made-up data (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_face.py
"""
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import face, skeleton, skin   # noqa: E402
from ttt2char.movesets import TABLE_ORDER            # noqa: E402
from ttt2char.ttt2 import animation as A, bone, motbin, motion   # noqa: E402

DESCRIPTORS = [A.TRANSLATION, A.ROTATION] * len(skeleton.FACE) + [3, 3] + [A.TRANSLATION] * 6
EMPTY = b'MOTA\0\1\0\0' + struct.pack('>III', 0x14, 0, 0)
UWA = 2 * skeleton.FACE.index('L_UwaMabuta_Joint') + 1
EYE = 2 * skeleton.FACE.index('L_Eye_Joint') + 1


def face_values(frames, seed):
    """Made-up face animation values: joints at made-up places, the lids turning about x up to 1 rad."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, frames)
    v = np.zeros((frames, len(DESCRIPTORS), 3))
    for c, d in enumerate(DESCRIPTORS):
        if A.is_rotation(d):
            v[:, c] = (0.0, np.pi / 2, 0.0)               # axis +x (rotation_axis: cos x sin y, -sin x, cos x cos y)
            v[:, c, 2] = 0.1 * np.sin(6 * t + c)
        else:
            v[:, c] = rng.normal(size=3) * 40 + np.outer(np.sin(5 * t + c), rng.normal(size=3))
    for name in face.LIDS:
        v[:, 2 * skeleton.FACE.index(name) + 1, 2] = np.sin(np.pi * t) * (1.0 if 'Uwa' in name else 0.3)
    return v


def made_skeleton(offset):
    """A bone.read()-like skeleton: the face joints under a head, their translations moved by `offset` (mm)."""
    names = ['ATAMA_Joint'] + skeleton.FACE
    t = np.zeros((len(names), 3), np.float32)
    t[1:] = np.arange(3 * len(skeleton.FACE)).reshape(-1, 3) + np.asarray(offset, np.float32)
    return dict(parent=[-1] + [0] * len(skeleton.FACE), t=t, r=np.zeros_like(t), opt=[], params=[0.0] * 8,
                names=names, s=np.ones_like(t), scale=1.0)


def made_files():
    """(moveset, pack, [the animations' values]) with two face animations: the moveset's face MOTA has entries 0, 1,
    0 (two share one), a MOTA after it; the pack's face MOTA has both."""
    vals = [face_values(37, 1), face_values(20, 2)]
    anims = [A.encode_compressed(DESCRIPTORS, v) for v in vals]
    mota = face._mota(EMPTY, [0, 1, 0], anims)
    blob = EMPTY + mota + EMPTY
    hdr = bytearray(motbin.BASE)
    hdr[4:8] = b'COM\0'
    slots = [0, None, None, None, len(EMPTY), None, len(EMPTY) + len(mota)] + [None] * 6
    moveset = motbin.build(hdr, b'[X]\0', {t: [] for t in TABLE_ORDER}, blob, slots)
    pack = motion.build_pack([EMPTY, b'', face._mota(EMPTY, [0, 1], anims), EMPTY, EMPTY, EMPTY])
    return moveset, pack, vals


def face_animations(moveset, pack):
    """[(entries' offsets, [decoded values])] of the moveset's face MOTA and the pack's."""
    out = []
    at = motbin.BASE + struct.unpack_from('>I', moveset, 0x1D8 + 4 * face.MOTBIN_SLOT)[0]
    for buf, start in ((moveset, at), (pack, motion.pack_items(pack)[face.PACK_ITEM][0])):
        e, offs = motion.mota_offsets(buf, start)
        out.append((offs, [A.decode(buf, e, start + o)['values'].astype(np.float64) for o in offs]))
    return out


class Retarget(unittest.TestCase):
    def test_offsets(self):
        moves = face.offsets(made_skeleton((1, 2, 3)), made_skeleton((0, 0, 0)))
        self.assertEqual(sorted(moves), list(range(0, 2 * len(skeleton.FACE), 2)))
        np.testing.assert_allclose(moves[0], (1, 2, 3))
        self.assertEqual(face.offsets(made_skeleton((0, 0, 0)), made_skeleton((0, 0, 0))), {})

    def test_moved_and_turned(self):
        moveset, pack, vals = made_files()
        lids = dict.fromkeys(face.LIDS[:2], 30.0)          # the donor's upper lids turn 57.3 degrees: x0.52
        new_moveset, new_pack, changed, scales = face.retarget(moveset, pack, made_skeleton((5, -2, 1)),
                                                               made_skeleton((0, 0, 0)), lids)
        self.assertEqual(changed, 4)                       # two animations in each MOTA (shared ones once)
        s = 30.0 / np.degrees(1.0)
        self.assertEqual(sorted(scales), sorted(face.LIDS[:2]))
        self.assertAlmostEqual(scales['L_UwaMabuta_Joint'], s, 3)
        before, after = face_animations(moveset, pack), face_animations(new_moveset, new_pack)
        for (offs0, old), (offs1, new) in zip(before, after):
            self.assertEqual([offs0.index(o) for o in offs0], [offs1.index(o) for o in offs1])   # sharing kept
            for a, b in zip(old, new):
                np.testing.assert_allclose(b[:, 0], a[:, 0] + (5, -2, 1), atol=1e-3)   # translations moved
                np.testing.assert_allclose(b[:, UWA, 2], a[:, UWA, 2] * s, atol=2e-3)   # the upper lids turned
                np.testing.assert_array_equal(b[:, EYE], a[:, EYE])                     # the rest as it was
                lower = 2 * skeleton.FACE.index('L_SitaMabuta_Joint') + 1
                np.testing.assert_array_equal(b[:, lower], a[:, lower])
        # the MOTA after the face MOTA moved along
        slot6 = struct.unpack_from('>I', new_moveset, 0x1D8 + 24)[0]
        self.assertEqual(new_moveset[motbin.BASE + slot6:motbin.BASE + slot6 + 4], b'MOTA')
        self.assertEqual(new_moveset[0x1D8:0x1D8 + 4], moveset[0x1D8:0x1D8 + 4])     # the MOTAs before it stay

    def test_nothing_to_do(self):
        moveset, pack, _ = made_files()
        out = face.retarget(moveset, pack, made_skeleton((0, 0, 0)), made_skeleton((0, 0, 0)), None)
        self.assertEqual(out, (moveset, pack, 0, {}))


class Lids(unittest.TestCase):
    def test_scales(self):
        donor = {'L_UwaMabuta_Joint': 60.0, 'R_UwaMabuta_Joint': 62.0, 'L_SitaMabuta_Joint': 20.0,
                 'R_SitaMabuta_Joint': 20.0}
        mine = {'L_UwaMabuta_Joint': 29.0, 'R_UwaMabuta_Joint': 31.0, 'L_SitaMabuta_Joint': 30.0,
                'R_SitaMabuta_Joint': 2.0}
        scales = face.lid_scales(mine, donor)
        self.assertEqual(scales['L_UwaMabuta_Joint'], scales['R_UwaMabuta_Joint'])   # both eyes alike
        self.assertAlmostEqual(scales['L_UwaMabuta_Joint'], 0.5)
        self.assertNotIn('L_SitaMabuta_Joint', scales)    # never turned further than the donor's
        self.assertAlmostEqual(face.lid_scales(dict(mine, R_UwaMabuta_Joint=1.0, L_UwaMabuta_Joint=1.0), donor)[
            'R_UwaMabuta_Joint'], face.LID_SCALES[0])
        self.assertEqual(face.lid_scales({}, donor), {})

    def test_tekken7_lids(self):
        frames = 200
        v = np.zeros((frames, face.TEKKEN7_CHANNELS, 3))
        v[:, 1::2] = (0.0, 0.0, 0.4)                       # every joint's usual pose: 0.4 rad about z
        turn = np.zeros(frames)
        turn[90:110] = np.sin(np.linspace(0, np.pi, 20)) * 0.5            # one blink, 0.5 rad about x
        for c in face.TEKKEN7_LIDS.values():
            R = np.array([A.local_rotation(np.array([0.0, 0.0, 0.4])) @ A.local_rotation(np.array([0, np.pi / 2, a]))
                          for a in turn])
            v[:, c] = A.axis_angles(R)
        lids = face.tekken7_lids([v, np.zeros((5, 70, 3))])      # (a 70-channel animation is no Tekken 7 face's)
        self.assertEqual(sorted(lids), sorted(face.LIDS))
        for name in face.LIDS:
            self.assertAlmostEqual(lids[name], np.degrees(turn.max()), 1)
        self.assertEqual(face.tekken7_lids([]), {})


PIVOTS = {'L': (30.0, 40.0, 80.0), 'R': (-30.0, 40.0, 80.0)}
RADIUS = 16.0


def lid_skeleton():
    """made_skeleton's, both eyes' lid joints at the eye centres PIVOTS."""
    s = made_skeleton((0, 0, 0))
    for name in face.LIDS:
        s['t'][s['names'].index(name)] = PIVOTS[name[0]]
    return s


def lid_model(skel, upper, lower, weights=(1.0, 1.0), wtype='>f4'):
    """A nud.read()-like model: each eye's upper / lower lid margin a row of points across the eye (x within 12 mm of
    its centre) on a sphere of RADIUS about it, `upper` / `lower` degrees above its front, weighted weights[0] /
    weights[1] to the lid joint (the rest to the head, bone 0)."""
    rows = []
    for side, pv in PIVOTS.items():
        for name, deg, w in ((side + '_UwaMabuta_Joint', upper, weights[0]), (side + '_SitaMabuta_Joint', lower,
                                                                                weights[1])):
            for x in np.linspace(-12, 12, 13):
                a = np.radians(deg)
                rows.append((np.add(pv, (x, RADIUS * np.sin(a), RADIUS * np.cos(a))), skel['names'].index(name), w))
    v = np.zeros(len(rows), [('pos', '>f4', 3), ('bones', 'u1', 4), ('w', wtype, 4)])
    for k, (p, j, w) in enumerate(rows):
        v[k]['pos'] = p
        v[k]['bones'] = (j, 0, 0, 0)
        v[k]['w'] = (round(w * 255), 255 - round(w * 255), 0, 0) if wtype == 'u1' else (w, 1 - w, 0, 0)
    return {'meshes': [{'name': 'face', 'polys': [{'verts': v}]}]}


def closed_share(up_deg, w, turn):
    """Degrees a margin point `up_deg` above the front closes when its joint turns `turn` degrees (linear blend w)."""
    a, b = np.radians(up_deg), np.radians(up_deg - turn)
    return up_deg - np.degrees(np.arctan2((1 - w) * np.sin(a) + w * np.sin(b), (1 - w) * np.cos(a) + w * np.cos(b)))


class MeshLids(unittest.TestCase):
    """Tekken 8's lids: the donor's turns scaled so that each lid closes the same share of the fighter's eye opening
    (TTT2 weights a lid half to its joint, Tekken 8 fully)."""

    def anims(self):
        _, pack, vals = made_files()
        at, size = motion.pack_items(pack)[face.PACK_ITEM]
        endian, _, anims = face._animations(pack, at, at + size)
        for v in vals:                      # (the upper lids close with negative turns about +x, as Jun's)
            for name in face.LIDS[:2]:
                c = 2 * skeleton.FACE.index(name) + 1
                v[:, c, 2] = -np.abs(v[:, c, 2])
        return [(endian, A.encode_compressed(DESCRIPTORS, v)) for v in vals], vals

    def test_axes(self):
        anims, vals = self.anims()
        axes, turns = face.lid_axes(anims)
        self.assertEqual(sorted(axes), sorted(face.LIDS))
        np.testing.assert_allclose(axes['L_UwaMabuta_Joint'], (1, 0, 0), atol=1e-6)    # (turned by -z: closes down)
        np.testing.assert_allclose(axes['L_SitaMabuta_Joint'], (-1, 0, 0), atol=1e-6)
        self.assertAlmostEqual(turns['L_UwaMabuta_Joint'], np.degrees(1.0), 1)
        self.assertAlmostEqual(turns['L_SitaMabuta_Joint'], np.degrees(0.3), 1)
        self.assertEqual(face.lid_axes([]), ({}, {}))

    def test_motion(self):
        anims, _ = self.anims()
        axes, turns = face.lid_axes(anims)
        skel = lid_skeleton()
        opening, rates = face.lid_motion(lid_model(skel, 10, -25, (0.5, 0.7)), skel, axes, turns)
        self.assertAlmostEqual(opening, 35.0, 3)
        self.assertAlmostEqual(rates['UwaMabuta_Joint'], 0.5, 3)          # half weighted: half the turn
        t = turns['L_SitaMabuta_Joint']
        self.assertAlmostEqual(rates['SitaMabuta_Joint'], -closed_share(-25, 0.7, -t) / t, 3)
        self.assertEqual(face.lid_motion({'meshes': []}, skel, axes, turns), (None, {}))

    def test_scales(self):
        anims, _ = self.anims()
        skel = lid_skeleton()
        donor = lid_model(skel, 10, -25, (0.5, 0.7), wtype='u1')        # (u8 weights: 255ths)
        mine = lid_model(skel, 6, -30, (1.0, 1.0))
        scales = face.lid_turns_on_meshes(mine, skel, donor, skel, anims)
        self.assertEqual(sorted(scales), sorted(face.LIDS))
        self.assertAlmostEqual(scales['L_UwaMabuta_Joint'], scales['R_UwaMabuta_Joint'])
        # each lid closes the same share of its eye's opening (36 degrees, the donor's 35) as the donor's
        _, turns = face.lid_axes(anims)
        for name, (up, w) in (('L_UwaMabuta_Joint', (10, round(0.5 * 255) / 255)),
                              ('L_SitaMabuta_Joint', (-25, round(0.7 * 255) / 255))):
            t = turns[name] * (1 if 'Uwa' in name else -1)
            donor_share = abs(closed_share(up, w, t)) / 35.0
            self.assertAlmostEqual(abs(t) * scales[name] / 36.0, donor_share, 2)
        self.assertEqual(face.lid_turns_on_meshes(donor, skel, donor, skel, anims), {})   # the donor's own lids
        self.assertEqual(face.lid_turns_on_meshes(mine, skel, donor, skel, []), {})

    def test_retarget_with_meshes(self):
        moveset, pack, vals = made_files()
        skel = lid_skeleton()
        mine, donor = lid_model(skel, 6, -30), lid_model(skel, 10, -25, (0.5, 0.7))
        _, _, changed, scales = face.retarget(moveset, pack, skel, skel, None, (mine, donor))
        self.assertTrue(changed)
        self.assertEqual(sorted(scales), sorted(face.LIDS))
        self.assertLess(scales['L_UwaMabuta_Joint'], 0.6)
        _, _, _, kept = face.retarget(moveset, pack, skel, skel, dict.fromkeys(face.LIDS, 30.0), (mine, donor))
        self.assertNotEqual(kept, scales)                  # (a Tekken 7 fighter's own turns win)


class SameJoints(unittest.TestCase):
    def test_face_joints_copied(self):
        mine, ref = made_skeleton((0, 0, 0)), made_skeleton((3, 3, 3))
        mine['t'][0] = (7, 7, 7)
        out = bone.read(face.same_joints(bone.write(mine), bone.write(ref)))
        np.testing.assert_array_equal(out['t'][1:], ref['t'][1:])
        np.testing.assert_array_equal(out['t'][0], (7, 7, 7))
        same = bone.write(ref)
        self.assertIs(face.same_joints(same, same), same)


class SkinGain(unittest.TestCase):
    def test_other_colours_keep_their_hue(self):
        g = np.array([1.5, 2.0, 2.5])
        tex = np.zeros((4, 4, 3), np.float32)
        tex[:] = (0.45, 0.21, 0.14)                        # orange skin
        tex[0, 0] = (0.11, 0.06, 0.10)                     # mauve
        out = skin.gained(tex, g)
        np.testing.assert_allclose(out[1, 1], tex[1, 1] * g, rtol=1e-5)
        k = out[0, 0] / tex[0, 0]
        self.assertLess(float(k.max() - k.min()), 0.1 * (g.max() - g.min()))    # (nearly) one gain for all three
        self.assertTrue(1.5 < k[0] < 2.5)


if __name__ == '__main__':
    unittest.main()
