"""convert/remesh8.py (a summon's large sheets as UV grids) and prefabs8's dithered opacity and metal, on made-up
data."""
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from ttt2char.convert import prefabs8, remesh8  # noqa: E402


def _sheet(side_cm, cells, z=0.0, uv0=(0.0, 0.0), uv_size=0.5, notch=False):
    """A flat square sheet side_cm wide in cells x cells quads, laid out in UV from uv0 over uv_size; notch: the quads
    of one corner left out (a torn edge)."""
    n = cells + 1
    xs = np.linspace(0, side_cm, n)
    pos = np.array([(x, y, z) for y in xs for x in xs], np.float32)
    uv = np.array([(uv0[0] + uv_size * i / cells, uv0[1] + uv_size * j / cells) for j in range(n) for i in range(n)],
                  np.float32)
    tris = []
    for j in range(cells):
        for i in range(cells):
            if notch and i >= cells // 2 and j >= cells // 2:
                continue
            a, b, c, d = j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i
            tris += [(a, b, c), (a, c, d)]
    return pos, uv, np.array(tris, np.int64)


def _geo(*sheets):
    pos, uv, tris, base = [], [], [], 0
    for p, u, t in sheets:
        pos.append(p)
        uv.append(u)
        tris.append(t + base)
        base += len(p)
    pos, uv = np.concatenate(pos), np.concatenate(uv)
    n = len(pos)
    joints = np.zeros((n, 4), np.int64)
    joints[:, 1] = 1
    weights = np.zeros((n, 4), np.float32)
    weights[:, 0] = np.clip(pos[:, 0] / 100.0, 0, 1)
    weights[:, 1] = 1 - weights[:, 0]
    return {'positions': pos, 'normals': np.tile((0.0, 0.0, 1.0, 0.0), (n, 1)).astype(np.float32),
            'tangents': np.tile((1.0, 0.0, 0.0, 1.0), (n, 1)).astype(np.float32), 'uvs': uv, 'joints': joints,
            'weights': weights, 'triangles': [np.concatenate(tris)]}

class Remesh8Test(unittest.TestCase):
    def test_a_torn_sheet_becomes_a_grid_at_its_step_its_outline_kept_as_coverage(self):
        remesh8._cover.clear()
        remesh8._two_sided.clear()
        geo = _geo(_sheet(100.0, 40, notch=True))
        out = remesh8.remesh(geo, ['made_up_sheet'], step_cm=20.0, min_area_m2=0.1, log=lambda *a: None)
        used = np.unique(out['triangles'][0])
        assert used.min() >= len(geo['positions'])             # (the old vertices are left unused)
        assert len(used) <= 7 * 7                               # a node every 20 cm over a metre (and a step's margin)
        whole = remesh8.remesh(_geo(_sheet(100.0, 40)), ['made_up_whole'], 20.0, 0.1, log=lambda *a: None)
        assert len(np.unique(whole['triangles'][0])) > len(used)    # (the notch's cells are not made)
        pos = out['positions'][used]
        assert pos[:, 0].min() >= -1e-3 and pos[:, 0].max() <= 100.001 and np.allclose(pos[:, 2], 0)
        w = out['weights'][used]
        assert np.allclose(w.sum(1), 1.0, atol=1e-5)
        # the grid's own vertices keep the source's skinning: joint 0's weight follows x
        j0 = (w * (out['joints'][used] == 0)).sum(1)
        assert np.allclose(j0, np.clip(pos[:, 0] / 100.0, 0, 1), atol=0.05)
        cov = remesh8.coverage('made_up_sheet', (64, 64))
        # (the notch is cut out)
        assert cov[8, 8] > 0.9 and cov[24, 24] < 0.1 and cov[40, 40] < 0.1 and cov[8, 24] > 0.9
        assert remesh8.coverage('another', (8, 8)) is None and not remesh8.two_sided('made_up_sheet')

    def test_a_sheet_lying_on_another_is_left_out_and_the_kept_one_drawn_from_both_sides(self):
        remesh8._cover.clear()
        remesh8._two_sided.clear()
        geo = _geo(_sheet(100.0, 10), _sheet(100.0, 10, z=0.5, uv0=(0.5, 0.5)))
        out = remesh8.remesh(geo, ['made_up_layers'], step_cm=25.0, min_area_m2=0.1, log=lambda *a: None)
        used = np.unique(out['triangles'][0])
        assert np.allclose(out['positions'][used][:, 2], 0)     # (the second layer's grid is not made)
        assert remesh8.two_sided('made_up_layers') and prefabs8.two_sided('made_up_layers')
        small = remesh8.remesh(_geo(_sheet(10.0, 4)), ['made_up_small'], 5.0, 0.1, log=lambda *a: None)
        # (under the area: as it was)
        assert np.array_equal(small['triangles'][0], _geo(_sheet(10.0, 4))['triangles'][0])

    def test_a_dithered_mask_is_drawn_where_tekken_8_draws_it_half_the_time(self):
        s = {'Opacity_Power': 1.0, 'OpacityDitherBlend': 1.0, 'AlphaThreshold': 1.0 / 3.0}
        a = np.array([0.0, 5.0 / 12.0, 0.6, 5.0 / 6.0, 1.0], np.float32)
        got = prefabs8.dithered(a, s)
        assert got[0] == 0 and abs(got[1] - prefabs8.TEMPLATE_CUT) < 1e-5 and got[3] == 1 and got[4] == 1
        hard = prefabs8.dithered(np.array([0.2, 0.5], np.float32), dict(s, OpacityDitherBlend=0.0))
        assert hard[0] == 0 and hard[1] == 1

    def test_a_summons_metal_and_roughness_lie_between_its_min_and_max(self):
        class Textures:
            def exists(self, path):
                return path == 'made/up'

            def image(self, path, size):
                img = np.zeros((size, size, 4), np.uint8)
                img[..., 0], img[..., 1], img[..., 2] = 255, 0, 255
                return img, None
        eff = {'textures': {'RMA': 'made/up'},
               'scalars': {'Metallic_Min': 0.5, 'Metallic_Max': 1.0, 'Roughness_Max': 0.5}}
        rough, metal, ao = prefabs8._rma(eff, Textures(), 4)
        assert np.allclose(rough, 0.5) and np.allclose(metal, 0.5) and np.allclose(ao, 1.0)
        got = prefabs8.shine(types.SimpleNamespace(PREFABS={'models': []}), eff, Textures())
        assert got[0, 0, 1] == int(255 * 0.6 * 0.5 * 0.5 + 0.5)    # reflection: REFLECTION x metal x (1 - rough)

    def test_mirror_gives_each_grid_a_back_face_of_its_own_instead_of_drawing_it_from_both_sides(self):
        remesh8._cover.clear()
        remesh8._two_sided.clear()
        geo = _geo(_sheet(100.0, 10), _sheet(100.0, 10, z=0.5, uv0=(0.5, 0.5)))
        one = remesh8.remesh(geo, ['made_up_one'], 25.0, 0.1, log=lambda *a: None)
        two = remesh8.remesh(geo, ['made_up_two'], 25.0, 0.1, log=lambda *a: None, mirror=True)
        assert remesh8.two_sided('made_up_one') and not remesh8.two_sided('made_up_two')
        t1, t2 = one['triangles'][0], two['triangles'][0]
        assert len(t2) == 2 * len(t1)
        front, back = t2[:len(t1)], t2[len(t1):]
        m0 = back.min() - front.min()
        assert np.array_equal(back, front[:, [0, 2, 1]] + m0)              # (the same cells, wound the other way)
        f, b = np.unique(front), np.unique(back)
        assert np.allclose(two['normals'][b][:, :3], -two['normals'][f][:, :3])
        assert np.allclose(two['tangents'][b][:, 3], -two['tangents'][f][:, 3])
        assert np.allclose(two['positions'][b] - two['positions'][f], -remesh8.BACK_CM * two['normals'][f][:, :3],
                           atol=1e-5)

    def test_a_metal_lit_material_keeps_its_whole_colour_where_others_show_their_non_metal_share(self):
        class Textures:
            def exists(self, path):
                return path in ('made/rma', 'made/base')

            def image(self, path, size):
                img = np.zeros((size, size, 4), np.uint8)
                img[..., 0], img[..., 1], img[..., 2] = 255, 255, 255
                return img, None

            def linear(self, path, size):
                return np.full((size, size, 3), 0.5, np.float32), None
        eff = {'base': 'made_up_base', 'textures': {'RMA': 'made/rma', 'Basecolor': 'made/base'}, 'switches': {},
               'vectors': {}, 'scalars': {'Metallic_Min': 0.0, 'Metallic_Max': 0.5}}
        d = types.SimpleNamespace(PREFABS={'models': [], 'bases': ('made_up_base',), 'texture_size': 8,
                                           'metal_lit': ('made_up_lit',)})
        dark, _ = prefabs8.bake(d, eff, Textures(), 'made_up_other')
        lit, _ = prefabs8.bake(d, eff, Textures(), 'made_up_lit')
        assert np.allclose(dark, 0.25, atol=1e-3) and np.allclose(lit, 0.5, atol=1e-3)


if __name__ == '__main__':
    unittest.main()
