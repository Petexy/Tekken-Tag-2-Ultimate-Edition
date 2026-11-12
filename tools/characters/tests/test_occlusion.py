"""Unit tests of convert/occlusion.py (skin a costume shades, darkened) on made-up data."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import occlusion          # noqa: E402


def _model(roof=True):
    """A made-up model: a floor quad 200 mm a side facing up (part 'skin', UVs over the whole texture), and over its left
    half, 30 mm up, a roof quad (part 'coat') facing up too; one shared pos/nrm/uv as a loaded model has."""
    pos = np.array([(-100, 0, -100), (100, 0, -100), (100, 0, 100), (-100, 0, 100),     # floor
                    (-110, 30, -110), (0, 30, -110), (0, 30, 110), (-110, 30, 110)], np.float64)    # roof (x < 0)
    nrm = np.tile([0.0, 1.0, 0.0], (len(pos), 1))
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0), (1, 0), (1, 1), (0, 1)], np.float64)
    floor = np.array([(0, 1, 2), (0, 2, 3)])
    prims = [dict(part='skin', material='skin', tris=floor, pos=pos, nrm=nrm, uv=uv)]
    if roof:
        prims.append(dict(part='coat', material='coat', tris=np.array([(4, 5, 6), (4, 6, 7)]), pos=pos, nrm=nrm, uv=uv))
    return {'prims': prims}


class Openness(unittest.TestCase):
    def test_open_and_under_a_roof(self):
        points = np.array([(50.0, 0.0, 0.0), (-60.0, 0.0, 0.0)])
        normals = np.array([(0.0, 1.0, 0.0), (0.0, 1.0, 0.0)])
        cover = occlusion._points(np.array([[(-110, 30, -110), (0, 30, -110), (0, 30, 110)],
                                            [(-110, 30, -110), (0, 30, 110), (-110, 30, 110)]], np.float64))
        ao = occlusion.openness(points, normals, cover)
        self.assertGreater(ao[0], 0.6)              # beside the roof: open above, some of its side shaded
        self.assertLess(ao[1], 0.2)                 # under it
        self.assertGreater(ao[0], ao[1])

    def test_nothing_over_it(self):
        ao = occlusion.openness(np.array([(0.0, 0.0, 0.0)]), np.array([(0.0, 1.0, 0.0)]),
                                np.array([(500.0, -50.0, 500.0)]))
        self.assertAlmostEqual(float(ao[0]), 1.0)


class MarkApply(unittest.TestCase):
    def test_mark_and_apply(self):
        spec = {'materials': ('skin',), 'parts': ('coat',), 'open': 0.8, 'power': 1.0}
        entry = occlusion.mark(_model(), spec, log=lambda *a: None)['skin']
        self.assertGreater(entry['ao'][1], entry['ao'][0])         # (the right corners lie out from under the roof)
        rgb = np.full((32, 32, 3), 0.5, np.float32)
        out = occlusion.apply(rgb, entry)
        left, right = out[16, 2, 0], out[16, 29, 0]
        self.assertLess(left, right)                # the texels under the roof darker
        want = 0.5 * occlusion.scale_map(entry, (32, 32))        # (the vertices' scales through the UVs)
        np.testing.assert_allclose(out[..., 0], want, atol=1e-5)
        self.assertLessEqual(float(out.max()), 0.5 + 1e-6)          # never brighter
        np.testing.assert_allclose(entry['scale'][:4], np.clip(entry['ao'][:4] / 0.8, 0, 1), atol=1e-6)

    def test_up_and_power(self):
        spec = {'materials': ('skin',), 'parts': ('coat',), 'open': 0.8, 'power': 2.0, 'up': 0.6}
        entry = occlusion.mark(_model(), spec, log=lambda *a: None)['skin']
        # (the floor faces straight up: each vertex loses 60%)
        np.testing.assert_allclose(entry['scale'][:4], 0.4 * np.clip(entry['ao'][:4] / 0.8, 0, 1) ** 2, atol=1e-6)
        model = _model()
        side = np.tile([1.0, 0.0, 0.0], (8, 1))
        for p in model['prims']:
            p['nrm'] = side                          # (facing sideways: no loss for facing up)
        entry = occlusion.mark(model, spec, log=lambda *a: None)['skin']
        np.testing.assert_allclose(entry['scale'][:4], np.clip(entry['ao'][:4] / 0.8, 0, 1) ** 2, atol=1e-6)

    def test_open_texels_stay(self):
        rgb = np.random.default_rng(1).random((8, 8, 3)).astype(np.float32)
        full = dict(tris=np.array([(0, 1, 2), (0, 2, 3)]), uv=_model()['prims'][0]['uv'], ao=np.ones(8, np.float32),
                    scale=np.ones(8, np.float32))
        np.testing.assert_allclose(occlusion.apply(rgb, full), rgb)

    def test_nothing_shades(self):
        model = _model()
        model['prims'][1] = dict(model['prims'][1], tris=np.zeros((0, 3), np.int64))
        spec = {'materials': ('skin',), 'parts': ('coat',)}
        self.assertEqual(occlusion.mark(model, spec, log=lambda *a: None), {})

    def test_kept_joints(self):
        model = _model()
        model['bones'] = {'names': ['root', 'neck', 'head', 'jaw'], 'parents': [-1, 0, 1, 2]}
        joints = np.zeros((8, 2), np.int64)
        weights = np.zeros((8, 2))
        joints[:, 0], weights[:, 0] = 1, 1.0                    # (all on the neck ..)
        joints[0], weights[0] = (3, 1), (0.5, 0.5)              # (.. but the first corner half on the jaw, a head's child)
        for p in model['prims']:
            p['joints'], p['weights'] = joints, weights
        np.testing.assert_allclose(occlusion._kept(model, ('head',))[:2], [0.5, 0.0])
        spec = {'materials': ('skin',), 'parts': ('coat',), 'keep': ('head',)}
        plain = occlusion.mark(_model(), {'materials': ('skin',), 'parts': ('coat',)}, log=lambda *a: None)['skin']['scale']
        kept = occlusion.mark(model, spec, log=lambda *a: None)['skin']['scale']
        self.assertAlmostEqual(float(kept[0]), float(plain[0] + (1 - plain[0]) * 0.5), places=5)
        self.assertAlmostEqual(float(kept[1]), float(plain[1]), places=5)

    def test_no_such_material(self):
        spec = {'materials': ('other',), 'parts': ('coat',)}
        self.assertEqual(occlusion.mark(_model(), spec, log=lambda *a: None), {})


if __name__ == '__main__':
    unittest.main()
