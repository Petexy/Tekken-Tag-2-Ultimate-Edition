"""convert/layerfit.py: a 2P colour layer fitted texel by texel, and its values carried into its holes. Made-up colours.

    python3 -m unittest discover tools/characters/tests
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, HERE)

from ttt2char.convert import colours, layerfit          # noqa: E402


class Palette:
    def __init__(self):
        self.placed = []

    def place(self, rgb):
        self.placed.append(rgb)
        return (len(self.placed), 1, 9)


def drawn(f, player):
    """What the layer draws: 2 * shade * (the groups' colours blended by b), where it is in."""
    a, b = np.array(f['groups'][0][1 + 2 * player]), np.array(f['groups'][1][1 + 2 * player])
    p = a[None, None] * (1 - f['b'][..., None]) + b[None, None] * f['b'][..., None]
    return np.clip(2 * f['shade'][..., None] * p, 0, 1)


class Fit(unittest.TestCase):
    def setUp(self):
        # a grey cloth (1P), red on the left and ochre on the right in 2P, with a few pale pink specks in the red
        self.c1 = np.full((32, 32, 3), 0.40)
        self.c2 = np.zeros((32, 32, 3))
        self.c2[:, :16] = (0.60, 0.20, 0.22)
        self.c2[:, 16:] = (0.70, 0.60, 0.40)
        self.specks = np.zeros((32, 32), bool)
        self.specks[4:30:6, 3:13:4] = True
        self.c2[self.specks] = (0.65, 0.40, 0.31)          # between the two: the old fit gives it one group's colour

    def test_blend_meets_both_players(self):
        f = layerfit.fit(self.c1, self.c2, Palette())
        self.assertEqual(f['alpha'].min(), 1.0)
        self.assertTrue(((f['b'] >= 0) & (f['b'] <= 1)).all())
        self.assertTrue((f['b'][self.specks] > 0.1).all() and (f['b'][self.specks] < 0.9).all())
        self.assertLess(np.abs(drawn(f, 1) - self.c2).max(), colours.MAX_ERROR)
        self.assertLess(np.abs(drawn(f, 0) - self.c1).max(), colours.MAX_ERROR)

    def test_a_texel_the_layer_cannot_draw_is_left_out(self):
        self.c2[10, 20] = (0.05, 0.60, 0.05)              # green: no blend of red and ochre
        f = layerfit.fit(self.c1, self.c2, Palette())
        self.assertEqual(f['alpha'][10, 20], 0.0)
        self.assertEqual(f['shade'][10, 20], 0.0)
        self.assertGreater(f['alpha'].mean(), 0.99)

    def test_nothing_changes(self):
        self.assertIsNone(layerfit.fit(self.c1, self.c1.copy(), Palette()))

    def test_lift_gives_the_palette_colours(self):
        seen = []

        def lift(group, rgb, texels):
            seen.append((group, texels.sum()))
            return np.clip(rgb * 1.5, 0, 1)
        pal = Palette()
        f = layerfit.fit(self.c1, self.c2, pal, lift=lift)
        self.assertEqual(sorted(g for g, _ in seen), [0, 0, 1, 1])
        self.assertEqual(sum(n for _, n in seen), 2 * 32 * 32)
        self.assertEqual(len(pal.placed), 4)
        self.assertTrue(np.allclose(f['groups'][0][1], np.clip(f['groups'][0][1], 0, 1)))


class Bleed(unittest.TestCase):
    def test_holes_take_their_neighbours(self):
        x = np.zeros((8, 8))
        x[:, :4], x[:, 4:] = 0.2, 0.8
        inside = np.ones((8, 8), bool)
        inside[3:5, 1:3] = False                          # a hole in the 0.2 half
        inside[3, 6] = False                               # one in the 0.8 half
        y = layerfit.bleed(inside, np.where(inside, x, 0.0))
        self.assertTrue(np.allclose(y[inside], x[inside]))
        self.assertTrue(np.allclose(y[3:5, 1:3], 0.2))
        self.assertAlmostEqual(y[3, 6], 0.8)

    def test_passes_bound_the_reach(self):
        inside = np.zeros((1, 10), bool)
        inside[0, 0] = True
        y = layerfit.bleed(inside, np.where(inside, 1.0, 0.0), passes=3)
        self.assertTrue(np.allclose(y[0, :4], 1.0))
        self.assertTrue(np.allclose(y[0, 4:], 0.0))


if __name__ == '__main__':
    unittest.main()
