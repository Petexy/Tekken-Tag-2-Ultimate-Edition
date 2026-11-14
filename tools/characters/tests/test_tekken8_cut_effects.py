"""Unit tests of a Tekken 8 solid's cut (convert/effects8.py: role 'cut', CUT_*, cut_timeline, cut_bake, cut_texels,
window_keys, ended_keys, CutMesh, Converter._cut and _measured's steps) on made-up data (no game files needed).

    python3 -m unittest tests.test_tekken8_cut_effects
"""
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import effects8 as E8, particles as P     # noqa: E402


def quad_mesh(uv_sets):
    """A square (2 triangles) of 1 x 1 m facing up, UV sets [(4, 2) arrays]."""
    positions = np.array([[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]], np.float32)
    tris = np.array([[0, 1, 2], [0, 2, 3]], np.int32)
    uvs = np.stack([np.asarray(u, np.float32) for u in uv_sets], 1)
    return types.SimpleNamespace(positions=positions, normals=np.tile([[0.0, 0.0, 1.0]], (4, 1)).astype(np.float32),
                                 uvs=uvs, colors=None, indices=tris.ravel(), triangles=lambda: [(0, tris)])


FULL = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
FOLDED = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [1.0, 0.0]]          # (the second triangle over the first)


class Timeline(unittest.TestCase):
    def test_steps_follow_the_threshold(self):
        # dynamic 3 .. then falling 0.25 a frame: k = 1 + clip - dynamic
        dynamic = [3.0] * 10 + [1.25 - 0.25 * f for f in range(10)] + [-1.0] * 10
        first, steps, end = E8.cut_timeline(dynamic, 0.25, 0.1, 30)
        self.assertEqual(first, 10)                               # (k = 0: the glow starts)
        self.assertEqual(end, 14)                                 # (k = 1: nothing left)
        self.assertEqual([(a, b) for a, b, _ in steps], [(10, 11), (11, 12), (12, 13), (13, 14)])
        self.assertTrue(np.allclose([k for _, _, k in steps], [0.0, 0.25, 0.5, 0.75]))

    def test_never_cut_and_a_long_cut(self):
        self.assertIsNone(E8.cut_timeline([3.0] * 60, 1 / 3, 0.04, 60))
        slow = [1.0 + 1 / 3 - f / 50.0 for f in range(60)]      # (k = f / 50: 50 frames of cut)
        first, steps, end = E8.cut_timeline(slow, 1 / 3, 0.0, 60, most=8)
        self.assertEqual((first, end, len(steps)), (1, 50, 8))
        self.assertEqual(steps[0][0], first)
        self.assertEqual(steps[-1][1], end)
        self.assertTrue(all(a < b for a, b, _ in steps))
        self.assertTrue(all(steps[n][1] == steps[n + 1][0] for n in range(len(steps) - 1)))   # (no gap)

    def test_a_history_shorter_than_the_life(self):
        # the sim's history ends before the cut does: its last value held to the end of the life (no IndexError)
        first, steps, end = E8.cut_timeline([3.0] * 20 + [1.0] * 10, 1 / 3, 0.04, 60)
        self.assertEqual((first, end), (20, 60))
        self.assertEqual(steps[-1][1], 60)
        self.assertTrue(np.allclose([k for _, _, k in steps], 1 / 3))
        self.assertIsNone(E8.cut_timeline([], 1 / 3, 0.04, 60))

    def test_alpha_windows(self):
        self.assertEqual(E8.window_keys(42, 43, 60), [[0, 0.0], [41, 0.0], [42, 1.0], [43, 0.0], [60, 0.0]])
        self.assertEqual(E8.window_keys(10, 14, 14), [[0, 0.0], [9, 0.0], [10, 1.0], [13, 1.0], [14, 0.0]])
        self.assertEqual(E8.window_keys(0, 2, 60), [[0, 1.0], [1, 1.0], [2, 0.0], [60, 0.0]])
        keys = [[0, 1.0], [8, 1.0], [44, 1.0], [52, 0.458], [60, 0.0]]
        self.assertEqual(E8.ended_keys(keys, 42), [[0, 1.0], [8, 1.0], [41, 1.0], [42, 0.0], [60, 0.0]])
        many = [[f, 1.0] for f in range(0, 41, 5)] + [[60, 0.0]]
        self.assertLessEqual(len(E8.ended_keys(many, 42)), P.CURVE_KEYS)


class Bake(unittest.TestCase):
    def test_unique_layout_skips_folded_sets(self):
        self.assertEqual(E8.unique_layout(quad_mesh([FOLDED, FULL])), 1)
        self.assertIsNone(E8.unique_layout(quad_mesh([FOLDED])))
        self.assertGreater(E8.overlap(np.asarray(FOLDED), np.array([[0, 1, 2], [0, 2, 3]])), 0.4)

    def test_spread_fills_round_islands(self):
        covered = np.zeros((8, 8), bool)
        covered[3:5, 3:5] = True
        vals = np.where(covered, 2.0, 0.0)
        out, have = E8.spread(vals, covered, texels=2)
        self.assertTrue(have[1:7, 1:7].all() and not have[0].any())
        self.assertTrue(np.allclose(out[have], 2.0))

    def test_colours_and_order_through_their_sets(self):
        sm = quad_mesh([FULL, FULL])
        albedo = np.zeros((4, 4, 4), np.float32)
        albedo[..., 1] = 0.5
        noise = np.tile(np.linspace(1.0, 0.0, 16, dtype=np.float32)[:, None], (1, 16))   # bright at v = 0
        rgb, order, covered, grad = E8.cut_bake(sm, 0, albedo, noise, 1, side=16)
        self.assertTrue(covered.all())
        shade = E8.lit_shade(sm.normals)[0]                      # (lit from above as ShadedMesh's)
        self.assertTrue(np.allclose(rgb[..., 1], 0.5 ** (1 / P.GAMMA) * shade, atol=1e-5))
        self.assertGreater(order[2].mean(), order[13].mean())     # (the noise's rows along v)
        self.assertTrue((grad[4:12, 4:12] > 0).all())

    def test_a_steps_texels(self):
        order = np.tile(np.linspace(0.0, 1.0, 11, dtype=np.float32), (2, 1))
        covered = np.ones_like(order, bool)
        covered[1, -1] = False
        rgb = np.full(order.shape + (3,), 0.3, np.float32)
        band, halo = np.array([1.0, 0.9, 1.0]), np.array([0.6, 0.3, 1.0])
        out = E8.cut_texels(rgb, order, covered, np.full_like(order, 0.1), 0.5, 0.2, band, halo, glow=0.5)
        a = out[0, :, 3]
        self.assertTrue(np.allclose(a[6:], 1.0))                  # kept (order > k)
        self.assertTrue(np.allclose(a[:3], 0.0))                  # cut away, past the halo
        self.assertTrue(0.0 < a[4] < a[5] <= 0.5)                 # the halo just past the cut
        self.assertTrue(np.allclose(out[0, 6, :3], band * 0.5 + halo * 0.5, atol=1e-5))    # the glow across
        self.assertTrue(np.allclose(out[0, 9, :3], 0.3))          # crystal
        self.assertEqual(out[1, -1, 3], 0.0)                      # (nothing there)
        wide = E8.cut_texels(rgb, order, covered, np.full_like(order, 0.2), 0.5, 0.05, band, halo, bloom=1.5)
        self.assertFalse(np.allclose(wide[0, 8, :3], 0.3))        # (at least `bloom` texels of glow)

    def test_no_halo_film_where_the_noise_is_flat(self):
        # a flat stretch of noise cut away whole leaves nothing drawn: no texel half seen
        order = np.full((16, 16), 0.3, np.float32)
        covered = np.ones_like(order, bool)
        rgb = np.full(order.shape + (3,), 0.3, np.float32)
        band, halo = np.array([1.0, 0.9, 1.0]), np.array([0.6, 0.3, 1.0])
        for k in (0.25, 0.29, 0.3, 0.31, 0.5):
            a = E8.cut_texels(rgb, order, covered, np.zeros_like(order), k, 0.04, band, halo)[..., 3]
            self.assertFalse(((a > 0.0) & (a < 1.0)).any(), k)

    def test_the_halo_stays_within_bloom_texels(self):
        # a shallow ramp (0.01 of order a texel, Edge 0.04 = 4 texels of band) next to a flat cut-away plateau, the
        # gradient as cut_bake takes it: the halo only within `bloom` texels of the cut
        x = np.arange(64, dtype=np.float32)
        row = np.where(x < 24, 0.2, 0.2 + 0.01 * (x - 24))
        order = np.tile(row, (8, 1)).astype(np.float32)
        covered = np.ones_like(order, bool)
        gy, gx = np.gradient(order)
        grad = np.hypot(gx, gy)
        rgb = np.full(order.shape + (3,), 0.3, np.float32)
        band, halo = np.array([1.0, 0.9, 1.0]), np.array([0.6, 0.3, 1.0])
        for k in (0.215, 0.3, 0.405):
            a = E8.cut_texels(rgb, order, covered, grad, k, 0.04, band, halo, bloom=1.5)[0, :, 3]
            kept = np.flatnonzero(a >= 1.0)
            part = np.flatnonzero((a > 0.0) & (a < 1.0))
            self.assertTrue(len(part) > 0, k)
            self.assertLessEqual(kept.min() - part.min(), 1.5 + 1.0, k)     # (from the first kept texel)
            self.assertTrue((part < kept.min()).all(), k)
        a = E8.cut_texels(rgb, order, covered, grad, 0.21, 0.04, band, halo, bloom=1.5)[0, :, 3]
        self.assertFalse(((a[:22] > 0.0) & (a[:22] < 1.0)).any())        # (the plateau: no film)

    def test_no_halo_round_a_bump_just_cut_away(self):
        # a cone of noise peaking at 0.3 (0.02 a texel) with the threshold just over its top: nothing kept, no ring
        y, x = np.mgrid[0:32, 0:32].astype(np.float32)
        order = np.clip(0.3 - 0.02 * np.hypot(x - 16, y - 16), 0.0, 1.0).astype(np.float32)
        covered = np.ones_like(order, bool)
        gy, gx = np.gradient(order)
        grad = np.hypot(gx, gy)
        rgb = np.full(order.shape + (3,), 0.3, np.float32)
        band, halo = np.array([1.0, 0.9, 1.0]), np.array([0.6, 0.3, 1.0])
        a = E8.cut_texels(rgb, order, covered, grad, 0.305, 0.04, band, halo)[..., 3]
        self.assertFalse((a > 0.0).any())
        a = E8.cut_texels(rgb, order, covered, grad, 0.25, 0.04, band, halo)[..., 3]   # (its top kept: a rim)
        part = (a > 0.0) & (a < 1.0)
        self.assertTrue(part.any())
        self.assertFalse((part & ~E8.grown(a >= 1.0, 2)).any())

    def test_grown(self):
        m = np.zeros((7, 7), bool)
        m[3, 3] = True
        self.assertEqual(int(E8.grown(m, 1).sum()), 9)
        self.assertEqual(int(E8.grown(m, 2).sum()), 25)
        self.assertTrue(np.array_equal(E8.grown(m, 0), m))
        edge = np.zeros((4, 4), bool)
        edge[0, 0] = True
        self.assertEqual(int(E8.grown(edge, 1).sum()), 4)                 # (no wrap)

    def test_cut_mesh_draws_its_layout_white(self):
        sm = quad_mesh([FOLDED, FULL])
        cut = E8.CutMesh(sm, 1)
        self.assertEqual(cut.uvs.shape, (4, 1, 2))
        self.assertTrue(np.array_equal(cut.uvs[:, 0], sm.uvs[:, 1]))
        self.assertIsNone(cut.colors)
        self.assertIs(cut.positions, sm.positions)
        conv = E8.Converter.__new__(E8.Converter)
        conv._meshes = {'/Game/SM.SM': sm}
        made = conv._static_mesh(E8.CUT_MESH + '1:/Game/SM.SM')
        self.assertIsInstance(made, E8.CutMesh)
        self.assertEqual(made.layout, 1)
        self.assertIs(conv._static_mesh('/Game/SM.SM'), sm)


class Wiring(unittest.TestCase):
    def test_step_material_and_texture(self):
        mats = E8.Materials.__new__(E8.Materials)
        mats._done, mats.measured = {}, True
        mats.m = types.SimpleNamespace(effective=lambda path: {'base': 'M_EF_CH_ITM_id4_x'})
        desc = mats.describe('/Game/MI_Crystal.MI_Crystal' + E8.Materials.CUT + '0:3')
        self.assertEqual(desc['textures'], {'BaseTexture': 'cut:0:3'})
        self.assertEqual((desc['blend'], desc['alpha']), ('BLEND_Translucent', 1.0))
        solid = mats.describe('/Game/MI_Crystal.MI_Crystal' + E8.Materials.SOLID)
        self.assertEqual(solid['textures'], {'BaseTexture': E8.SOLID_TEXTURE + '/Game/MI_Crystal.MI_Crystal'})
        tex = E8.Textures(None, 0x1000, hot=True)
        img = np.zeros((32, 32, 4), np.float32)
        img[:16, :, :] = (0.2, 0.1, 0.6, 1.0)
        tex.cuts['cut:0:3'] = img
        src = types.SimpleNamespace(key=('cut:0:3',), img=None, side=128)
        name, gidx, w, h = tex.lit(src, (1.0, 1.0, 1.0), 1.0, False)
        self.assertEqual((w, h), (32, 32))                        # (its own size)
        from ttt2char.ttt2 import nut
        texels = np.asarray(nut.decode(nut.read(tex.files[name])['textures'][0]))
        self.assertGreater(texels[:12, :, 3].min(), 250)          # kept
        self.assertLess(texels[20:, :, 3].max(), 5)               # cut away
        self.assertIs(tex.linear_image('cut:0:3'), img)

    @staticmethod
    def converter(cut):
        conv = E8.Converter.__new__(E8.Converter)
        conv.tune, conv.measured, conv.stats, conv.turn = {'measured': True}, True, {}, None
        conv.log = lambda s: None
        conv.materials = types.SimpleNamespace(describe=lambda path: {'base': 'M_EF_CH_ITM_id4_x', 'alpha': 1.0,
                                                                      'blend': 'BLEND_Masked', 'scalars': {},
                                                                      'vectors': {}, 'textures': {}})
        conv.flat_box = lambda desc, sm, sprite: False
        conv.made = []

        def emitter(em, cap=None):
            conv.made.append(em)
            e = {'spawner': {'tracks': {P.alo.ALPHA_TRACK: {'keys': [[0, 1.0], [44, 1.0], [60, 0.0]]}}}}
            return [(e, 't', 'm')]
        conv.emitter = emitter
        conv._cut = lambda path, sm, mat, spec, m: cut
        return conv

    def test_measured_whole_then_steps(self):
        cut = {'first': 42, 'steps': [(42, 43, 'cut:0:0'), (43, 44, 'cut:0:1')], 'mesh': 'cut:2:/Game/SM.SM',
               'life': 60}
        conv = self.converter(cut)
        m = types.SimpleNamespace(**vars(TestMeasured.measured()))
        e = types.SimpleNamespace(name='CrystalPillar', gpu=False, loop=None, rate=0.0, per_unit=False,
                                  bursts=[(0.0, 1)], local=False, colours={}, scripts=None)
        r = types.SimpleNamespace(kind='mesh', meshes=[('/Game/SM.SM', '/Game/MI.MI')], material=None,
                                  sub_images=(1, 1))
        old = E8.measure
        E8.measure = lambda em: m
        try:
            made = conv._measured(e, r, r.meshes[0], object(), '/Game/MI.MI', False, True, (1, 1, 1), None, None,
                                  ((r'^CrystalPillar$', {'solid': True, 'dissolve': True, 'cut': {'uv': 1}}),))
        finally:
            E8.measure = old
        self.assertEqual(len(made), 3)
        alpha = lambda n: made[n][0]['spawner']['tracks'][P.alo.ALPHA_TRACK]['keys']
        self.assertEqual(alpha(0), [[0, 1.0], [41, 1.0], [42, 0.0], [60, 0.0]])          # the whole, until the cut
        self.assertEqual(alpha(1), E8.window_keys(42, 43, 60))
        self.assertEqual(alpha(2), E8.window_keys(43, 44, 60))
        mesh = lambda em: next(x for x in em.modules if x.cls == 'TypeDataMesh').get('Mesh')
        material = lambda em: next(x for x in em.modules if x.cls == 'Required').get('Material')
        self.assertEqual(mesh(conv.made[0]), E8.SOLID_MESH + '/Game/SM.SM')
        self.assertEqual([mesh(x) for x in conv.made[1:]], ['cut:2:/Game/SM.SM'] * 2)
        self.assertEqual([material(x) for x in conv.made[1:]], ['/Game/MI.MI#cut:0:0', '/Game/MI.MI#cut:0:1'])
        # without a cut (the role's or nothing to cut): the whole one only, its track as made
        conv = self.converter(None)
        E8.measure = lambda em: m
        try:
            made = conv._measured(e, r, r.meshes[0], object(), '/Game/MI.MI', False, True, (1, 1, 1), None, None,
                                  ((r'^CrystalPillar$', {'solid': True, 'dissolve': True}),))
        finally:
            E8.measure = old
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0][0]['spawner']['tracks'][P.alo.ALPHA_TRACK]['keys'], [[0, 1.0], [44, 1.0], [60, 0.0]])

    def test_one_bake_for_every_look(self):
        conv = E8.Converter.__new__(E8.Converter)
        calls = []
        conv._cut_steps = lambda path, sm, mat, spec, m, life, number: calls.append(number) or {'n': number}
        m = types.SimpleNamespace(dynamic_frames=[3.0] * 60, life=(1.0, 0.0))
        a = conv._cut('/Game/SM.SM', None, '/Game/MI.MI', {'uv': 1}, m)
        b = conv._cut('/Game/SM.SM', None, '/Game/MI.MI', {'uv': 1}, m)
        c = conv._cut('/Game/SM.SM', None, '/Game/MI.MI', {'uv': 1, 'first': 'light'}, m)
        self.assertIs(a, b)
        self.assertEqual(calls, [0, 1])
        self.assertEqual(c, {'n': 1})
        self.assertIsNone(conv._cut('/Game/SM.SM', None, '/Game/MI.MI', {}, types.SimpleNamespace(
            dynamic_frames=None, life=(1.0, 0.0))))

    def test_the_definition_cuts_the_pillar_only(self):
        from ttt2char.characters import azazel
        roles = azazel.TEKKEN8_EFFECT_TUNE['system_roles'][30]
        self.assertEqual(E8.tuned('CrystalPillar', roles).get('cut'), {'uv': 1, 'first': 'dark'})
        for bit in ('Bit_Collision', 'BitB', 'BitC'):
            self.assertEqual(E8.tuned(bit, roles), {'solid': True, 'dissolve': True})


class TestMeasured:
    @staticmethod
    def measured(n=E8.CURVE_POINTS):
        return types.SimpleNamespace(times=[k / (n - 1) for k in range(n)], life=(1.0, 0.0), colour=None,
                                     alpha=[1.0] * n, scale=[(1.0, 1.0, 1.0)] * n, size=None, scale_half=0.0,
                                     path=[(0.0, 0.0, 0.0)] * n, start_half=(0.0, 0.0, 0.0),
                                     speed_half=(0.0, 0.0, 0.0), drifts=[], sprite_turn=None, pre=(0.0, 0.0, 0.0),
                                     turn_half=(0.0, 0.0, 0.0), spin=(0.0, 0.0, 0.0), spin_half=(0.0, 0.0, 0.0),
                                     dynamic=[3.0] * n, dynamic_frames=[3.0] * 60)


if __name__ == '__main__':
    unittest.main()
