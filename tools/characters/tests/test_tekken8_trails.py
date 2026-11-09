"""Unit tests of a Tekken 8 fighter's weapon trails (convert/trails8.py, the moveset converter's trail rows) on made-up
data (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_trails.py
"""
import collections
import os
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import moveset, trails8 as T      # noqa: E402

SHRINK = [(0.0, 1.0), (0.5, 1.0), (1.0, 0.0)]


class Decode(unittest.TestCase):
    def test_value(self):
        self.assertEqual(T.decode(0x03120a01), (3, 18, 10, 1))

    def test_socket_is_mm_with_y_reversed(self):
        self.assertEqual(T.socket((1.0, 2.0, 3.0)).tolist(), [100.0, -200.0, 300.0])


class Sweep(unittest.TestCase):
    def setUp(self):
        self.far = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [1000.0, 0.0, 0.0], [1010.0, 0.0, 0.0]])
        self.near = self.far + np.array([0.0, -500.0, 0.0])

    def test_passes_through_every_frame(self):
        times, far, near = T.sweep(self.far, self.near)
        for f in range(4):
            k = int(np.argmin(np.abs(times - f)))
            self.assertAlmostEqual(times[k], f)
            np.testing.assert_allclose(far[k], self.far[f], atol=1e-6)
            np.testing.assert_allclose(near[k], self.near[f], atol=1e-6)

    def test_more_slices_where_the_blade_flies(self):
        times, _, _ = T.sweep(self.far, self.near)
        self.assertEqual(int(np.sum(times <= 1.0)), 2)                     # a slow frame: its ends only
        self.assertEqual(int(np.sum((times > 1.0) & (times <= 2.0))), T.MAX_SLICES)
        self.assertTrue(np.all(np.diff(times) > 0))

    def test_mesh(self):
        times = np.array([0.0, 1.0])
        far = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
        near = far + np.array([0.0, 0.0, 1000.0])
        pos, uv, tris = T.mesh(times, far, near, 5.0, 1.2)
        self.assertEqual(len(pos), 2 * T.ROWS)
        self.assertEqual(len(tris), 2 * (T.ROWS - 1))
        np.testing.assert_allclose(pos[0], [0.0, 0.0, -T.RIM * 1200.0])     # beyond the far end: the rim's glow
        np.testing.assert_allclose(pos[T.ROWS - 1], [0.0, 0.0, 1200.0])     # the near end pulled out by the width
        np.testing.assert_allclose(uv[:, 1], [0.0] * T.ROWS + [-0.2] * T.ROWS)      # later slices further back
        np.testing.assert_allclose(uv[:T.ROWS, 0], np.linspace(0.0, 1.0, T.ROWS))


class Look(unittest.TestCase):
    def bake(self, **kw):
        eff = dict(scalars={'Alpha': 8.0, 'ColorBoost': 1.0, 'ColorBoost2': 10.0}, vectors={
            'BaseTexColor': dict(r=1.0, g=0.1, b=0.0), 'BaseTex2Color': dict(r=1.0, g=0.0, b=0.0)}, textures={},
            switches={})
        materials = mock.Mock()
        materials.effective.return_value = eff
        kind = dict(materials=['/Game/M.M'], edge=False)
        kind.update(kw.pop('kind', {}))
        return T.bake(None, materials, kind, SHRINK, along=128, across=64, **kw)

    def test_clear_beyond_the_ages_and_the_edges(self):
        out = self.bake(tails=2.0)
        self.assertEqual(out[0, :, 3].max(), 0.0)                           # the head's row
        self.assertEqual(out[80:, :, 3].max(), 0.0)                         # older than the tail
        self.assertEqual(out[:, [0, -1], 3].max(), 0.0)
        self.assertGreater(out[10, 32, 3], 200.0)

    def test_narrows_towards_the_far_end(self):
        out = self.bake()
        x = (np.arange(64) + 0.5) / 64 * (1.0 + T.RIM) - T.RIM
        young = out[32, :, 3] > 0
        self.assertTrue(young[np.argmin(np.abs(x - 0.9))])
        old = out[96, :, 3] > 0                                             # age 0.75: half of it left
        self.assertFalse(old[np.argmin(np.abs(x - 0.9))])
        self.assertTrue(old[np.argmin(np.abs(x - 0.3))])

    def test_the_refraction_layer_draws_nothing(self):
        self.assertIsNone(T.layer(None, dict(scalars={'Alpha': 0.0}, vectors={}, textures={}), np.zeros(2), np.zeros(2)))

    def test_a_kinds_body_scales_its_opacity(self):
        whole, faint = self.bake()[10, 32, 3], self.bake(kind=dict(body=0.25))[10, 32, 3]
        self.assertAlmostEqual(faint / whole, 0.25, places=1)

    def test_a_rim_goes_round_the_head(self):
        out = self.bake(kind=dict(materials=['/Game/M.M', '/Game/M.M'], edge=True))
        x = (np.arange(64) + 0.5) / 64 * (1.0 + T.RIM) - T.RIM
        near_end, middle = np.argmin(np.abs(x - 0.97)), np.argmin(np.abs(x - 0.5))
        self.assertGreater(out[3, middle, 3], 200.0)                        # the head's middle comes first
        self.assertEqual(out[3, near_end, 3], 0.0)                          # its ends later
        self.assertGreater(out[40, near_end, 3], 200.0)

    def test_a_fires_colours_run_from_dark_red_to_pale(self):
        light = np.linspace(0.0, 200.0, 256, dtype=np.float32)
        plain = np.stack([light, light * 0.2, light * 0.01], -1)[None]
        got = T.fire(plain, np.ones(light.shape, np.float32)[None], np.ones(light.shape, np.float32)[None])
        self.assertGreater(got[0, 0, 0], 2.0 * got[0, 0, 1])                # the darkest: red, not black
        self.assertGreater(got[0, 0, 0], 0.2)
        self.assertTrue(np.all(np.diff(got[0, :, 1]) >= 0.0))
        self.assertGreater(got[0, -1, 2], 0.5)                              # the brightest: pale

    def test_red_goes_orange_not_grey(self):
        r, g, b = T.shown(np.array([30.0, 0.0, 0.0], np.float32), T.EXPOSURE)
        self.assertGreater(r, g)
        self.assertGreater(g, b)


class LeftBehind(unittest.TestCase):
    def run_it(self, kind, burning):
        far = np.zeros((13, 3))
        far[:, 0] = np.arange(13) * (T.WISP_SPEED + 1.0)
        far[9:, 0] = far[8, 0]                                              # (it stops at frame 8)
        conv = mock.MagicMock()
        conv.textures.bake.return_value = (1, 2)
        with mock.patch.object(T, 'burning', return_value=burning), mock.patch.object(T, 'puff') as puff, \
                mock.patch.object(T, 'wisp_look'), mock.patch.object(T, 'fleck_look'), mock.patch.object(T, 'spark_look'):
            T.left_behind(conv, mock.Mock(), dict(kind=kind, kind_id=1, seen=far, far=far), {})
        return [c.args[3] for c in puff.call_args_list], conv

    def test_a_plain_kind_leaves_nothing(self):
        delays, conv = self.run_it({}, False)
        self.assertEqual(delays, [])
        conv._append.assert_not_called()

    def test_a_fire_leaves_clouds_and_sparks_while_it_flies(self):
        delays, conv = self.run_it({}, True)
        self.assertEqual(delays, [4, 4, 8, 8])
        self.assertEqual(conv._append.call_count, 4)

    def test_flecks_alone(self):
        delays, conv = self.run_it(dict(flecks=True), False)
        self.assertEqual(delays, [4, 8])
        self.assertEqual(conv._append.call_count, 2)


class Rows(unittest.TestCase):
    def converter(self, sampler):
        class K:
            tables = {'moves': [{'anim_len': 60}, {'anim_len': 60}, {'anim_len': 60}]}

            @staticmethod
            def anim_ref(i):
                return ('same' if i < 2 else 'other'), 'own'
        c = moveset.Converter.__new__(moveset.Converter)
        c.k, c.effect_ids, c.stats = K(), {5}, collections.Counter()
        c.trail_sampler, c.trail_rows = sampler, []
        return c

    def test_end_row_or_its_frames(self):
        calls = []
        c = self.converter(lambda *a: calls.append(a) or dict(a=1))
        v = 2 << 24 | 26 << 16 | 10 << 8 | 3
        t8 = [(16, moveset.EFFECT8_TRAIL, v, None), (42, moveset.EFFECT8_TRAIL_END, 0, None)]
        c.trail8_rows([], t8, 16, v, 0)
        c.trail8_rows([], [(16, moveset.EFFECT8_TRAIL, v, None), (20, moveset.EFFECT8_TRAIL_END, 0, None)], 16, v, 0)
        c.trail8_rows([], [(16, moveset.EFFECT8_TRAIL, v, None)], 16, v, 0)
        self.assertEqual([a[2] for a in calls], [26, 4, 26])

    def test_same_clip_start_and_value_share_an_id(self):
        c = self.converter(lambda *a: dict(a=a))
        v = 0x01120a01
        t8 = [(18, moveset.EFFECT8_TRAIL, v, None)]
        rows = [[], [], []]
        for m in range(3):
            c.trail8_rows(rows[m], t8, 18, v, m)
        got = c.assign_trails(used={100})
        self.assertEqual(sorted(got), [101, 102])                           # (100 is the donor's)
        self.assertEqual([r[0]['value'] for r in rows], [101, 101, 102])    # part 0: the hips
        self.assertEqual({r[0]['id'] for r in rows}, {moveset.EFFECT_PROP})
        self.assertEqual({r[0]['frame'] for r in rows}, {18})
        self.assertLessEqual({5, 101, 102}, c.effect_ids)

    def test_no_clip_no_row(self):
        c = self.converter(lambda *a: None)
        rows = []
        c.trail8_rows(rows, [(18, moveset.EFFECT8_TRAIL, 0x01120a01, None)], 18, 0x01120a01, 0)
        self.assertEqual(rows, [])
        self.assertEqual(c.assign_trails(set()), {})


class Stops(unittest.TestCase):
    def test_a_0x8036_row_is_not_a_spawn(self):
        self.assertNotIn(0x8036, (moveset.EFFECT8_SPAWN, moveset.EFFECT8_TRAIL, moveset.EFFECT_PROP))


if __name__ == '__main__':
    unittest.main()
