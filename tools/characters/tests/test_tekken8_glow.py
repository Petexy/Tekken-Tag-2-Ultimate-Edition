"""Unit tests of a Tekken 8 fighter's glowing summons and their fades (tekken8/bake.py glowing parts,
tekken8/model.py section_uvs, convert/summonfade.py, summons8.fade_value, pack.character_ini's ramps) on made-up data
(no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_glow.py
"""
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from ttt2char import pack  # noqa: E402
from ttt2char.convert import summonfade, summons8  # noqa: E402
from ttt2char.tekken8 import bake, model as t8model  # noqa: E402
from ttt2char.ttt2 import bone  # noqa: E402


# ------------------------------------------------------------------------------------------------ made-up materials
class Textures:
    """material.Textures' interface over made-up linear images {path: (H, W, 3)}."""

    def __init__(self, images):
        self.images = images

    def exists(self, path):
        return bool(path) and path in self.images

    def linear(self, path, max_size=None):
        rgb = np.asarray(self.images[path], np.float32)
        return rgb, np.ones(rgb.shape[:2], np.float32)


def colour(r, g, b):
    return {'r': r, 'g': g, 'b': b, 'a': 1.0}


def part(emissive=5.0, fresnel=False, tint=(1, 1, 1), base='M_CH_Extra_Parts', switches=None, mask='mask'):
    eff = {'base': base, 'scalars': {'EmissiveIntensity_A': emissive, 'EmissiveMask_Power': 1.0, 'FresnelPower': 4.0,
                                     'Fresnel Intensity': 10.0},
           'vectors': {'BaseTintColor': colour(*tint), 'EmissiveColor_A': colour(0.0, 0.1, 0.5),
                       'Fresnel Color': colour(0.0, 0.3, 0.8)},
           'textures': {'BaseColor': 'base', 'EmissiveMask': mask},
           'switches': dict({'Use EmissiveMask': True, 'Use Fresnel': fresnel}, **(switches or {})),
           'overrides': {}}
    images = {'base': np.full((8, 4, 3), 0.04, np.float32), 'mask': np.full((8, 4, 3), 1.0, np.float32)}
    return eff, Textures(images)


class GlowBakeTest(unittest.TestCase):
    def test_share(self):
        eff, tex = part()
        lit = 0.04 * bake.GLOW_AMBIENT                      # (grey base x tint 1)
        e = float(np.array([0.0, 0.5, 2.5]) @ bake.GLOW_LUMA)
        self.assertAlmostEqual(bake.emission_share(eff, tex), e / (e + lit), places=5)
        eff, tex = part(emissive=0.0)
        self.assertEqual(bake.emission_share(eff, tex), 0.0)

    def test_share_only_for_glowing_parts(self):
        eff, tex = part(base='M_CH_ITM_id_RGBA')
        self.assertIsNone(bake.emission_share(eff, tex))
        eff['base'] = 'M_CH_Extra_Parts'
        eff['textures'] = {}
        self.assertIsNone(bake.emission_share(eff, tex))   # (nothing to bake)

    def test_classify(self):
        self.assertEqual(bake.classify('MI_CH_x_exp_1p', 'M_CH_Extra_Parts', None, 0.9), ('glow', False, False))
        self.assertEqual(bake.classify('MI_CH_x_exp_1p', 'M_CH_Extra_Parts', None, bake.GLOW_SHARE),
                         ('glow', False, False))
        self.assertEqual(bake.classify('MI_CH_x_exp_1p', 'M_CH_Extra_Parts', None, 0.5)[0], 'cloth')
        self.assertEqual(bake.classify('MI_CH_x_exp_1p', 'M_CH_Extra_Parts', None)[0], 'cloth')    # (share unknown)
        self.assertEqual(bake.classify('MI_CH_x_bdf', 'M_CH_ITM_id_RGBA', None, 0.99)[0], 'cloth')
        self.assertEqual(bake.classify('MI_CH_x_skin', 'M_CH_skin_V3', None)[0], 'skin')

    def test_bake(self):
        """bake_emissive = the tone curve of base x tint x ambient + E, as linear values whose sRGB is the colour."""
        eff, tex = part(tint=(0.5, 0.5, 0.5))
        rgb, alpha = bake.bake_emissive(eff, tex)
        self.assertIsNone(alpha)
        self.assertEqual(rgb.shape, (8, 4, 3))
        want = bake.glow_encode(np.array([0.04 * 0.5 * bake.GLOW_AMBIENT] * 3) + np.array([0.0, 0.5, 2.5]))
        np.testing.assert_allclose(bake.linear_to_srgb(rgb[0, 0]), want, atol=1e-5)
        self.assertGreater(rgb[0, 0, 2], rgb[0, 0, 1])     # blue
        self.assertEqual(bake.bake_emissive(dict(eff, textures={}), tex), (None, None))

    def test_fresnel(self):
        eff, tex = part(emissive=0.0, fresnel=True)
        lit, E = bake._emissive_terms(eff, tex)
        np.testing.assert_allclose(E[0, 0], bake.fresnel_mean(4.0) * 10.0 * np.array([0.0, 0.3, 0.8]), rtol=1e-5)
        self.assertAlmostEqual(bake.fresnel_mean(0.0), 1.0)
        self.assertLess(bake.fresnel_mean(4.0), bake.fresnel_mean(1.0))
        self.assertAlmostEqual(bake.fresnel_mean(1.0), 1 - np.pi / 4, places=3)   # (the mean of 1 - sqrt(1 - x^2))

    def test_mask_in_another_uv_set(self):
        """An emissive mask laid out along another UV set than the colour: its mean everywhere."""
        eff, tex = part(switches={'Use UV1 for EmissiveMask': True})
        tex.images['mask'] = np.concatenate([np.ones((4, 4, 3)), np.zeros((4, 4, 3))], 0).astype(np.float32)
        _, E = bake._emissive_terms(eff, tex)
        np.testing.assert_allclose(E[0, 0], E[-1, -1])
        np.testing.assert_allclose(E[0, 0], 0.5 * 5.0 * np.array([0.0, 0.1, 0.5]), rtol=1e-5)

    def test_encode(self):
        x = np.array([[0.0, 0.0, 0.0], [0.1, 0.4, 2.0], [100.0, 100.0, 100.0]], np.float32)
        y = bake.glow_encode(x)
        self.assertTrue(np.all(y >= 0) and np.all(y <= 1))
        np.testing.assert_allclose(y[0], 0, atol=1e-6)
        self.assertGreater(y[2].min(), 0.99)
        self.assertGreater(y[1, 2], y[1, 1])

    def test_uv_set(self):
        self.assertEqual(bake.uv_set({'switches': {'Use UV1 for BaseColor': True}}, 'BaseColor'), 1)
        self.assertEqual(bake.uv_set({'switches': {'Use UV1 for BaseColor': False}}, 'BaseColor'), 0)
        self.assertEqual(bake.uv_set({}, 'EmissiveMask'), 0)


class SectionUvsTest(unittest.TestCase):
    def test_uv1_material(self):
        """A section whose material names UV1 for its colour takes UV1; the others UV0."""
        uvs = np.zeros((6, 2, 2), np.float32)
        uvs[:, 0] = 0.25
        uvs[:, 1] = 0.75
        geo = {'uvs': uvs, 'triangles': [np.array([[0, 1, 2]]), np.array([[3, 4, 5]])]}
        m = types.SimpleNamespace(lods=[types.SimpleNamespace(sections=[types.SimpleNamespace(material_index=0),
                                                                        types.SimpleNamespace(material_index=1)])],
                                  materials=[{'material': '/Game/a/MI_plain'}, {'material': '/Game/a/MI_tail'}])

        class Materials:
            def effective(self, ref):
                if ref.endswith('MI_missing'):
                    raise KeyError(ref)
                return {'switches': {'Use UV1 for BaseColor': ref.endswith('MI_tail')}}
        uv = t8model.section_uvs(Materials(), m, geo)
        np.testing.assert_allclose(uv[:3], 0.25)
        np.testing.assert_allclose(uv[3:], 0.75)
        m.materials[1]['material'] = '/Game/a/MI_missing'   # (a material it cannot read: UV0)
        np.testing.assert_allclose(t8model.section_uvs(Materials(), m, geo), 0.25)
        one = {'uvs': uvs[:, :1], 'triangles': geo['triangles']}
        m.materials[1]['material'] = '/Game/a/MI_tail'
        np.testing.assert_allclose(t8model.section_uvs(Materials(), m, one), 0.25)   # (one UV set only)


# ------------------------------------------------------------------------------------------------ fades
def cylinder(axis, n=24, length=1000.0, radius=30.0, centre=(0.0, 0.0, 0.0)):
    """Points of a cylinder along axis `axis` (0..2) from 0 to length, centred on that axis through `centre`."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    out = []
    for t in np.linspace(0, length, 5):
        p = np.zeros((n, 3))
        cross = [k for k in range(3) if k != axis]
        p[:, cross[0]] = radius * np.cos(a)
        p[:, cross[1]] = radius * np.sin(a)
        p[:, axis] = t
        out.append(p)
    return np.concatenate(out) + np.asarray(centre)


class RampTest(unittest.TestCase):
    def test_mesh_ramp(self):
        self.assertEqual(summonfade.mesh_ramp(cylinder(1)), summonfade.RAMP_X | summonfade.RAMP_Z)
        self.assertEqual(summonfade.mesh_ramp(cylinder(0)), summonfade.RAMP_Y | summonfade.RAMP_Z)
        self.assertEqual(summonfade.mesh_ramp(cylinder(2)), summonfade.RAMP_X | summonfade.RAMP_Y)
        # off its axis (the horn at the head joint's frame): shrunk whole
        self.assertEqual(summonfade.mesh_ramp(cylinder(1, centre=(140.0, 0.0, 0.0))), summonfade.RAMP_ALL)
        self.assertEqual(summonfade.mesh_ramp(np.zeros((0, 3))), summonfade.RAMP_ALL)

    def test_still_frame(self):
        """A still weapon's frame from its mesh: y along it, base -> tip (away from the parent), origin at its base on
        its axis, a rotation; its vertices then run along y, centred: a thickness ramp."""
        d = np.array([0.0, 0.8, 0.6])
        rng = np.random.default_rng(0)
        local = cylinder(1, length=200.0, radius=15.0)
        x = np.cross(d, [1.0, 0.0, 0.0])
        x /= np.linalg.norm(x)
        R = np.stack([x, d, np.cross(x, d)], 1)
        base = np.array([0.0, 1700.0, 100.0])
        pts = local @ R.T + base + rng.normal(0, 0.01, local.shape)
        w = summonfade.still_frame(pts, parent_origin=(0.0, 1600.0, 0.0))
        self.assertAlmostEqual(np.linalg.det(w[:3, :3]), 1.0, places=6)
        np.testing.assert_allclose(w[:3, :3].T @ w[:3, :3], np.eye(3), atol=1e-9)
        np.testing.assert_allclose(w[:3, 1], d, atol=1e-3)
        np.testing.assert_allclose(w[:3, 3], base, atol=0.5)
        inv = np.linalg.inv(w)
        self.assertEqual(summonfade.mesh_ramp(pts @ inv[:3, :3].T + inv[:3, 3]), summonfade.RAMP_X | summonfade.RAMP_Z)
        # (the tip side is the one away from the parent, whichever way the vertices come)
        w2 = summonfade.still_frame(pts[::-1], parent_origin=(0.0, 1600.0, 0.0))
        np.testing.assert_allclose(w2[:3, 1], d, atol=1e-3)

    def test_part_points(self):
        prim = dict(part='wpn2', tris=np.array([[0, 1, 2]]), pos=np.arange(12.0).reshape(4, 3),
                    joints=np.array([[5, 0], [5, 0], [6, 0], [5, 0]]), weights=np.array([[1.0, 0], [1, 0], [1, 0],
                                                                                          [1, 0]]))
        other = dict(prim, part='bdf', tris=np.array([[1, 2, 3]]))
        pts = summonfade.part_points({'prims': [prim, other]}, 'wpn2', [5])
        np.testing.assert_allclose(pts, [[0, 1, 2], [3, 4, 5]])


def skeleton(rows):
    """A made-up skeleton dict (bone.read's) of [(name, parent, translation)] (no rotations)."""
    n = len(rows)
    return dict(names=[r[0] for r in rows], parent=[r[1] for r in rows],
                t=np.array([r[2] for r in rows], np.float32), r=np.zeros((n, 3), np.float32),
                s=np.ones((n, 3), np.float32), opt=[])


def verts(points, bone_index):
    p = np.asarray(points, np.float32)
    dt = np.dtype([('pos', '>f4', (3,)), ('bones', '>u4', (4,)), ('w', '>f4', (4,))])
    v = np.zeros(len(p), dt)
    v['pos'] = p
    v['bones'][:, 0] = bone_index
    v['w'][:, 0] = 1.0
    return v


class RampsTest(unittest.TestCase):
    def setUp(self):
        # KOSHI, a staff along y at the hand, a two-link tail along x under KOSHI, a root point (summon 63)
        self.skel = skeleton([('cha:KOSHI_jnt', -1, (0, 1000, 0)), ('cha:TE_R_jnt', 0, (-700, 400, 0)),
                              ('cha:OPT801_staff', 1, (0, 0, 0)), ('cha:OPT803_tail_01', 0, (0, 0, -150)),
                              ('cha:OPT804_tail_03', 3, (200, 0, 0)), ('cha:OPT812_root_a', 0, (0, 0, 750))])
        w = bone.world_matrices(self.skel)
        staff = cylinder(1, length=2400.0) - (0, 1200, 0)
        link = cylinder(0, length=200.0)
        self.model = {'meshes': [{'polys': [{'verts': verts(staff + w[2][:3, 3], 2)},
                                            {'verts': np.concatenate([verts(link + w[3][:3, 3], 3),
                                                                      verts(link + w[4][:3, 3], 4)])}]}]}
        self.ini = [(1, 1, [], 1), (3, 0, [], 2), (4, 0, [], 2), (12, 0, [(3, 2)], 63)]

    def test_ramps(self):
        out = summonfade.ramps(self.skel, self.model, self.ini)
        self.assertEqual([w[:4] for w in out], self.ini)
        X, Y, Z = summonfade.RAMP_X, summonfade.RAMP_Y, summonfade.RAMP_Z
        self.assertEqual([w[4] for w in out], [X | Z, Y | Z, Y | Z | summonfade.RAMP_UNDER, 0])

    def test_no_mesh_of_its_own(self):
        """A summoned weapon with no mesh of its own but bones under it carrying one (the snakes' still weapon at the
        elbow, their skeleton under it) shrinks whole; a point-only one (only a point bone under it) has no ramp."""
        skel = skeleton([('cha:KOSHI_jnt', -1, (0, 1000, 0)), ('cha:UDE_R_jnt', 0, (-300, 400, 0)),
                         ('cha:OPT821_snakes', 1, (0, 0, 0)), ('cha:OPT600_snake_a', 2, (0, 0, 100)),
                         ('cha:OPT601_snake_b', 3, (0, 0, 100)), ('cha:OPT802_snake', 1, (0, 0, 300)),
                         ('cha:OPT850_hit79_0', 5, (0, 0, 0))])
        w = bone.world_matrices(skel)
        body = cylinder(2, length=100.0, radius=20.0)
        model = {'meshes': [{'polys': [{'verts': np.concatenate([verts(body + w[3][:3, 3], 3),
                                                                 verts(body + w[4][:3, 3], 4)])}]}]}
        self.assertEqual(summonfade.bones_under(skel, 2), [3, 4])
        self.assertEqual(summonfade.bones_under(skel, 1, stop={2}), [5, 6])
        self.assertEqual(len(summonfade.weapon_vertices(model, [3, 4])), 2 * len(body))
        self.assertEqual(len(summonfade.weapon_vertices(model, [])), 0)
        out = summonfade.ramps(skel, model, [(2, 1, [(0, 0)], 4), (21, 1, [], 4)])
        self.assertEqual([r[4] for r in out], [0, summonfade.RAMP_ALL])

    def test_nothing_summoned(self):
        """No weapon a move summons (Reina's, Azucena's root points): no ramps, the model not read."""
        out = summonfade.ramps(self.skel, b'not a nud', [(12, 0, [(3, 2)], 63), (13, 0, [(4, 3)], None)])
        self.assertEqual(out, [(12, 0, [(3, 2)], 63, 0), (13, 0, [(4, 3)], None, 0)])

    def test_ini(self):
        d = types.SimpleNamespace(NAME='X', CODE='xyz', DONOR='jun', SEX='female', TEKKEN8_CODE='xyz')
        text = pack.character_ini(d, 0, weapons=[(1, 9, [], 1, 5), (3, 3, [], 2, 14), (12, 0, [(3, 2)], 63, 0),
                                                 (2, 9, [(0, 0)], None, 7), (0, 13, [], 0)])
        line = next(x for x in text.split('\n') if x.startswith('weapons ='))
        self.assertEqual(line, 'weapons = 1:9::1:5 3:3::2:14 12:0:3>2:63 2:9:0::7 0:13::0')


class FadeValueTest(unittest.TestCase):
    def test_fade_value(self):
        self.assertEqual(summons8.fade_value(1, 5), 1 | 5 << 8)
        self.assertEqual(summons8.fade_value(3, 10), 3 | 10 << 8)
        self.assertEqual([summons8.fade_value(2, f) for f in (0, 1, None)], [2, 2, 2])   # at once: as before
        self.assertEqual(summons8.fade_value(0, 1000), summons8.FADE_MAX << 8)
        self.assertEqual(summons8.fade_value(4, 8) & summons8.SUMMON_MASK, 4)

    def test_rows(self):
        """Show / hide rows carry their value3 (the fade) in the value."""
        k = types.SimpleNamespace(tables=dict(moves=[], extra_move_properties=[
            dict(id=0x8410, value=2, value2=1, value3=5), dict(id=0x8410, value=2, value2=1, value3=1)],
            move_begin_props=[], move_end_props=[dict(id=0x8410, value=4, value2=0, value3=10)]))
        d = types.SimpleNamespace(WEAPONS=[dict(bone='staff', parent='TE_R_jnt', pair=1, summon=1),
                                           dict(bone='tail', parent='KOSHI_jnt', pair=3, summon=2)])
        log = []
        summons8.prepare(k, d, log=log.append)
        ex, end = k.tables['extra_move_properties'], k.tables['move_end_props']
        self.assertEqual([(r['id'], r['value']) for r in ex], [(summons8.SUMMON, 1 | 5 << 8), (summons8.SUMMON, 1)])
        self.assertEqual((end[0]['id'], end[0]['value']), (summons8.DISMISS, 2 | 10 << 8))
        self.assertTrue(any('fading (in over 5 frames)' in line for line in log))
        self.assertTrue(any('fading (out over 10 frames)' in line for line in log))

    def test_summons_out_by_default(self):
        """moveset.default_summons reads a fading value as its summon number (the frames above it ignored)."""
        from ttt2char.convert import moveset
        show, hide = summons8.SUMMON, summons8.DISMISS
        moves = [[(5, hide, summons8.fade_value(3, 10)), (40, show, summons8.fade_value(3, 5))],   # 3: out before
                 [(2, hide, summons8.fade_value(3, 8)), (30, show, 3)],
                 [(4, show, summons8.fade_value(1, 5)), (30, hide, summons8.fade_value(1, 10))]]   # 1: not out
        c = types.SimpleNamespace(game='t8', summons={1: {}, 3: {}},
                                  k=types.SimpleNamespace(tables=dict(moves=[dict(extraprops=i) for i in range(3)])))
        c.xp_rows = lambda i: [(f, idv, v, None) for f, idv, v in moves[i]] + [(0, 0, 0, None)]
        self.assertEqual(moveset.Converter.default_summons(c), [3])


if __name__ == '__main__':
    unittest.main()
