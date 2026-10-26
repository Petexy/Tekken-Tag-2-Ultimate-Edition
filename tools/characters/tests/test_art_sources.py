"""The 2D pictures' sources (convert/art.py): picture sources of either game, the glows taken off each game's
pictures and cutting a fighter out of a costume picture, on made-up pictures (no game files needed).

    python3 -m unittest discover tools/characters/tests
"""
import os
import sys
import types
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import art                      # noqa: E402

RIM = np.array([240, 60, 100]) / 255.0


def rim_lit(h=120, w=100):
    """A fighter (an opaque dark blue disc) with dark half-transparent hair strands at its top and a pink rim light
    around it: a band of one colour whose alpha falls from 0.3 to nothing (straight colour, as Tekken 8 stores it:
    the transparent pixels have the rim's colour too)."""
    y, x = np.mgrid[0:h, 0:w]
    r = np.hypot(y - h / 2, x - w / 2)
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = RIM
    img[..., 3] = np.clip(0.3 * (1.0 - (r - 30) / 25), 0.0, 0.3)
    disc = r <= 30
    img[disc] = [0.1, 0.1, 0.3, 1.0]
    strands = (np.abs(x - w / 2) < 12) & (y >= 8) & (y < h / 2 - 28) & (x % 3 == 0)
    img[strands] = [0.12, 0.1, 0.2, 0.5]
    return img, disc, strands


class Glows(unittest.TestCase):
    def test_rim_light(self):
        img, disc, strands = rim_lit()
        out = art.deglow_rim(img)
        band = ~disc & ~strands & (img[..., 3] > 0)
        self.assertLess(out[..., 3][band].max(), 0.01)                    # the rim light is gone
        np.testing.assert_array_equal(out[disc], img[disc])               # the fighter stays
        np.testing.assert_array_equal(out[strands], img[strands])         # and the hair (another colour)
        np.testing.assert_array_equal(out[..., :3], img[..., :3])         # colours as they were

    def test_no_rim_light(self):
        # faint pixels of many colours (no one colour among them): nothing is taken off
        rnd = np.random.default_rng(1)
        img = rnd.random((64, 64, 4)).astype(np.float32)
        img[..., 3] *= 0.09
        np.testing.assert_array_equal(art.deglow_rim(img), img)

    def test_glows_by_game(self):
        self.assertEqual(art.GLOWS['tekken7'], {'body': art.deglow})
        self.assertEqual(art.GLOWS['tekken8'], {'bust': art.deglow_rim})


class Pictures(unittest.TestCase):
    """Sources() takes its pictures from a picture source and takes the glows of that source's game off."""

    def definition(self):
        return types.SimpleNamespace(ART={'bust': ('/b', (10, 20, 30)), 'body': ('/w', (5, 6, 7)), 'name': '/n'})

    def source(self, game, pictures):
        s = types.SimpleNamespace(game=game, asked=[])
        s.picture = lambda path: (s.asked.append(path), pictures[path])[1]
        return s

    def test_tekken8(self):
        img, disc, strands = rim_lit()
        as_bytes = np.round(img * 255).astype(np.uint8)
        src = self.source('tekken8', {'/b': as_bytes, '/w': as_bytes, '/n': as_bytes})
        s = art.Sources(src, self.definition())
        self.assertEqual(sorted(src.asked), ['/b', '/n', '/w'])
        # the bust's face framed bigger and lower (BUST_FRAME: 1.5 times, 0.1 of eyes-to-chin), the body's as measured
        self.assertEqual(s.faces, {'bust': (10, 17.0, 20.0), 'body': (5, 6, 7)})
        self.assertLess(s.pictures['bust'][..., 3][~disc & ~strands].max(), 0.01)     # the bust's rim light is off
        np.testing.assert_array_equal(s.pictures['body'], art._float(as_bytes))     # the body as it is

    def test_tekken7(self):
        glow = np.zeros((8, 8, 4), np.uint8)
        glow[...] = (250, 250, 250, 128)                                  # a pale, half-transparent glow
        src = self.source('tekken7', {'/b': glow, '/w': glow, '/n': glow})
        s = art.Sources(src, self.definition())
        np.testing.assert_array_equal(s.pictures['body'], art.deglow(art._float(glow)))
        np.testing.assert_array_equal(s.pictures['bust'], art._float(glow))
        self.assertEqual(s.faces, {'bust': (10, 20, 30), 'body': (5, 6, 7)})          # Tekken 7's as measured

    def test_paks(self):
        # Tekken 7's paks as they are (the calls before picture sources): read through Tekken7Pictures
        paks = object()
        source = art.picture_source(paks)
        self.assertIsInstance(source, art.Tekken7Pictures)
        self.assertIs(source.paks, paks)
        self.assertEqual(source.game, 'tekken7')
        with mock.patch.object(art, 'load', return_value='package') as load, \
                mock.patch.object(art, 'Texture2D') as texture:
            texture.return_value.decode.return_value = 'pixels'
            self.assertEqual(source.picture('/Game/x'), 'pixels')
        load.assert_called_once_with(paks, '/Game/x')
        texture.assert_called_once_with('package')
        mine = self.source('tekken8', {})
        self.assertIs(art.picture_source(mine), mine)

    def test_source_of(self):
        d = types.SimpleNamespace(CODE='rei')
        one, two = self.source('tekken7', {}), self.source('tekken8', {})
        self.assertIs(art.source_of(one, 3, d), one)
        self.assertIs(art.source_of({3: two}, 3, d), two)                 # by slot
        self.assertIs(art.source_of({'rei': two, 0: one}, 3, d), two)     # by code
        self.assertIs(art.source_of(lambda x: two if x is d else one, 3, d), two)    # by definition
        self.assertIsInstance(art.source_of({3: object()}, 3, d), art.Tekken7Pictures)


class CutOut(unittest.TestCase):
    def test_transparent_background(self):
        # Tekken 8's costume picture: the fighter on a transparent background, cut to what is not transparent
        img = np.zeros((60, 40, 4), np.uint8)
        img[..., :3] = (200, 50, 90)                                      # (the transparent pixels' colour)
        img[10:50, 12:30] = (20, 30, 160, 255)
        img[9, 20] = (20, 30, 160, 100)                                   # a half-transparent hair at the top
        img[51, 5] = (0, 0, 0, 3)                                         # nearly nothing: not the fighter
        out = art.cut_out(img)
        self.assertEqual(out.shape, (41, 18, 4))
        self.assertAlmostEqual(float(out[0, 8, 3]), 100 / 255, places=5)
        np.testing.assert_allclose(out[5, 5], np.array([20, 30, 160, 255]) / 255.0, atol=1e-6)
        self.assertIsNone(art.cut_out(np.zeros((8, 8, 4), np.uint8)))

    def test_grey_panel(self):
        # Tekken 7's costume slot: white margins, a smooth grey panel, the fighter on it (opaque picture)
        img = np.full((50, 40, 4), 255, np.uint8)
        img[5:45, 4:36, :3] = (120, 120, 130)
        img[15:35, 15:25, :3] = (200, 30, 30)
        out = art.cut_out(img)
        self.assertEqual(out.shape, (20, 10, 4))
        self.assertTrue((out[..., 3] == 1.0).all())
        np.testing.assert_allclose(out[0, 0, :3], np.array([200, 30, 30]) / 255.0, atol=1e-6)


if __name__ == '__main__':
    unittest.main()
