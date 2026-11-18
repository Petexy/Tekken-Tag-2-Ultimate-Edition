"""Unit tests of the measured look of a fighter's Tekken 8 effects (convert/effects8.py, a definition's
TEKKEN8_EFFECT_TUNE 'measured') on made-up data (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_measured.py
"""
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import effects8 as E8, particles as P     # noqa: E402


def run(frames=10, particles=8, **history):
    return types.SimpleNamespace(history=history, lifetime=np.full(particles, 0.2))


class Measure(unittest.TestCase):
    def test_numbers_over_the_life(self):
        place = np.zeros((20, 8, 3))
        place[:, :, 0] = np.arange(20)[:, None] * 10.0                 # 10 cm a frame ahead
        colour = np.ones((20, 8, 4))
        colour[:, :, 3] = np.linspace(1.0, 0.0, 20)[:, None]
        m = E8.Measured(run(Position=place, Color=colour))
        self.assertAlmostEqual(m.life[0], 0.2)
        self.assertAlmostEqual(m.path[0][0], 0.0)
        self.assertAlmostEqual(m.path[-1][0], 120.0)                    # (frame 12: its life's last)
        self.assertGreater(m.alpha[0], m.alpha[-1])
        self.assertEqual(m.drifts and max(m.speed_half), 0.0)

    def test_particles_that_fly_apart_have_their_drifts(self):
        place = np.zeros((20, 8, 3))
        place[:, :, 1] = np.arange(20)[:, None] * np.linspace(-5.0, 5.0, 8)[None, :]
        m = E8.Measured(run(Position=place))
        self.assertEqual(len(m.drifts), E8.DRIFT_CLONES)
        self.assertAlmostEqual(sum(d[1] for d in m.drifts), 0.0, places=3)
        self.assertLess(m.drifts[0][1], 0.0)
        self.assertGreater(m.drifts[-1][1], 0.0)

    def test_a_scriptless_or_gpu_emitter_is_not_measured(self):
        self.assertIsNone(E8.measure(types.SimpleNamespace(gpu=True, scripts=None)))
        self.assertIsNone(E8.measure(types.SimpleNamespace(gpu=False, scripts=None)))


class Tune(unittest.TestCase):
    def test_first_pattern_wins(self):
        roles = ((r'^Flare', dict(alpha=0.1)), (r'Fl', dict(alpha=0.5)))
        self.assertEqual(E8.tuned('Flare002', roles), dict(alpha=0.1))
        self.assertEqual(E8.tuned('Other', roles), {})

    def test_the_measured_look_is_the_definitions_choice(self):
        self.assertFalse(P.Converter.flat_models)
        conv = E8.Converter.__new__(E8.Converter)
        conv.materials = types.SimpleNamespace()
        conv.textures = types.SimpleNamespace()
        conv.set_tune(None)
        self.assertFalse(conv.measured or conv.flat_models or conv.textures.hot or conv.materials.measured)
        conv.set_tune({'measured': True})
        self.assertTrue(conv.measured and conv.flat_models and conv.textures.hot and conv.materials.measured)


    def test_dim_is_a_factor_on_the_colour_track(self):
        emitter = {'spawner': {'tracks': {P.alo.COLOUR_TRACK: {'keys': [[0, 1.0, 0.5, 0.0], [10, 0.5, 0.5, 0.5]]}}}}
        E8.dimmed(emitter, 0.5)
        self.assertEqual(emitter['spawner']['tracks'][P.alo.COLOUR_TRACK]['keys'],
                         [[0, 0.5, 0.25, 0.0], [10, 0.25, 0.25, 0.25]])

    def test_palette_colours_a_gpu_emitter(self):
        conv = E8.Converter.__new__(E8.Converter)
        conv.materials = types.SimpleNamespace(describe=lambda mat: dict(alpha=1.0, blend='BLEND_Additive', base=''))
        conv.flat_box = lambda desc, sm, sprite: False
        conv.tune, conv.emitter = {}, lambda em, cap: []
        seen = []
        old, old_power = E8.cascade, P._power
        E8.cascade = lambda e, r, colour, *a, **k: seen.append(colour)
        P._power = lambda desc: (1.0,)
        try:
            e = types.SimpleNamespace(name='Shitaji', gpu=True, scripts=None, colours={})
            for roles in ((), (('Shitaji', {'palette': (0.3, 1.0, 0.4)}),), (('Other', {'palette': (1.0, 0.0, 0.0)}),)):
                conv._measured(e, None, None, None, '/Game/M.M', False, False, (1.0, 1.0, 1.0), None, None, roles)
        finally:
            E8.cascade, P._power = old, old_power
        self.assertEqual(seen, [(1.0, 1.0, 1.0), (0.3, 1.0, 0.4), (1.0, 1.0, 1.0)])    # (else the system's colour)

    def test_paint_wins_over_a_gpu_emitters_own_colours(self):
        e = types.SimpleNamespace(name='BitA', gpu=True, colours={'c': [(0.0, 1.0, 1.0, 1.0)]}, rate=0.0,
                                  per_unit=False, loop=1.0, bursts=[(0.0, 4)], local=False)
        r = types.SimpleNamespace(kind='sprite', meshes=[], material='/Game/M.M', sub_images=(1, 1))
        old = (E8.brightest, E8.size_curve, E8.alpha_curve)
        E8.brightest = lambda colours: (1.0, 1.0, 1.0) if colours else None
        E8.size_curve = E8.alpha_curve = lambda *a: None
        try:
            def start(roles):
                em = E8.cascade(e, r, (0.2, 0.2, 0.2), roles=roles)
                mod = next(m for m in em.modules if m.cls == 'Color')
                return mod.dist('StartColor', 3).samples
            own, painted = start(()), start((('^BitA$', {'paint': (0.45, 0.15, 1.0)}),))
        finally:
            E8.brightest, E8.size_curve, E8.alpha_curve = old
        b = E8.GPU_BRIGHTNESS
        self.assertEqual(own, E8.ranged([b, b, b], dim=3).samples)              # its own colour (white)
        self.assertEqual(painted, E8.ranged([0.45 * b, 0.15 * b, 1.0 * b], dim=3).samples)

    def test_no_donor_effects_is_the_definitions_choice(self):
        from ttt2char import importer
        self.assertEqual(importer._donor_effects(types.SimpleNamespace(DONOR_EFFECTS=False), b''), [])


class Texels(unittest.TestCase):
    @staticmethod
    def image(value, alpha=1.0, n=4):
        img = np.full((n, n, 4), float(value), np.float32)
        img[..., 3] = alpha
        return img

    def test_hot_burns_to_white_dim_stays_coloured(self):
        blue = (0.1, 0.3, 1.0)
        dim = E8.hot_texels(self.image(1.0), [x * 2.0 for x in blue], 1.0, True)[0, 0]
        hot = E8.hot_texels(self.image(1.0), [x * 1000.0 for x in blue], 1.0, True)[0, 0]
        self.assertLess(dim[0], dim[2])
        self.assertGreater(hot[0], 0.7)                                 # white, its blue only where it fades

    def test_a_black_bake_is_no_texture(self):
        tex = E8.Textures(None, 0x10408800, hot=True)
        src = types.SimpleNamespace(key=('k',), img=self.image(0.0), side=4)
        with self.assertRaises(P.Invisible):
            tex.lit(src, (1.0, 1.0, 1.0), 1.0, True)
        self.assertEqual(tex.files, {})

    def test_a_lit_bake_is_written(self):
        tex = E8.Textures(None, 0x10408800, hot=True)
        src = types.SimpleNamespace(key=('k',), img=self.image(1.0), side=16)
        self.assertTrue(tex.lit(src, (1.0, 1.0, 1.0), 1.0, True)[0].endswith('.nut'))
        self.assertEqual(len(tex.files), 1)

    def test_a_flat_mask_tiles_only_the_base(self):
        base = self.image(1.0, 1.0, 8)
        mask = np.zeros((8, 8, 4), np.float32)
        mask[..., 3] = 1.0
        mask[4, 4, :3] = 1.0                                            # a shape in the middle of the mask
        sources = {'b': base, 'm': mask}
        tex = types.SimpleNamespace(linear_image=lambda p: sources[p].copy(), sources={}, hot=True)
        mat = dict(textures={'BaseTexture': 'b', 'MaskTexture': 'm'}, switches={}, scalars={},
                   vectors={'BaseTexTilling': {'r': 0.25, 'g': 0.25}})
        src = P.material_source(tex, mat)
        self.assertGreater(src.img[..., 3].max(), 0.5)                  # (the tile's corner of the mask is empty)


class Shapes(unittest.TestCase):
    def test_generated_flare_fades_out_from_its_middle(self):
        a = E8.generated_mask('flare')[..., 3]
        n = a.shape[0]
        self.assertGreater(a[n // 2, n // 2], 0.9)
        self.assertEqual(float(a[0, 0]), 0.0)

    def test_generated_rim_is_bright_at_the_rim(self):
        a = E8.generated_mask('rim')[..., 3]
        n = a.shape[0]
        self.assertLess(a[n // 2, n // 2], 0.01)
        self.assertGreater(a[n // 2, 2:n // 2].max(), 0.2)

    def test_two_sided_mesh_has_each_triangle_twice(self):
        sm = types.SimpleNamespace(positions=np.zeros((3, 3)), triangles=lambda: [('m', np.array([[0, 1, 2]]))])
        two = E8.TwoSidedMesh(sm)
        (material, triangles), = two.triangles()
        self.assertEqual(material, 'm')
        self.assertEqual(sorted(map(tuple, triangles.tolist())), [(0, 1, 2), (2, 1, 0)])
        self.assertIs(two.positions, sm.positions)


class FlatBox(unittest.TestCase):
    def conv(self, img):
        conv = E8.Converter.__new__(E8.Converter)
        conv.textures = types.SimpleNamespace(
            linear_image=lambda p: img.copy(), sources={}, hot=True)
        return conv

    MAT = dict(textures={'BaseTexture': 't'}, switches={}, scalars={}, vectors={})

    def test_a_sprite_of_a_full_texture_is_a_box(self):
        full = np.ones((8, 8, 4), np.float32)
        full[..., :3] = (0.2, 0.5, 1.0)
        full[0, 0, 3] = 0.5                                             # (its shape is in alpha: and it fills the sprite)
        self.assertTrue(self.conv(full).flat_box(self.MAT, None, False))

    def test_a_sprite_of_a_soft_shape_is_not(self):
        n = 16
        y, x = np.mgrid[0:n, 0:n]
        soft = np.ones((n, n, 4), np.float32)
        soft[..., 3] = np.clip(1.0 - np.hypot(x - n / 2, y - n / 2) / (n / 2), 0.0, 1.0) ** 2
        self.assertFalse(self.conv(soft).flat_box(self.MAT, None, False))


if __name__ == '__main__':
    unittest.main()
