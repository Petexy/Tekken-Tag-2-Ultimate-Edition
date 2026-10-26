"""Unit tests of the mesh decimator (decimate.py, decimate.c) on made-up meshes (no game files needed).

    python3 -m unittest discover tools/characters/tests
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char import InputError, native                # noqa: E402
from ttt2char.convert import decimate                  # noqa: E402

HAVE_CC = bool(shutil.which('gcc') or shutil.which('cc'))


def model_of(pos, prims, nrm=None, uv=None, weights=None):
    """A model dict as model.load_tekken7_model gives it: prims [(part, material, tris)] on shared streams."""
    pos = np.asarray(pos, np.float64)
    n = len(pos)
    if nrm is None:
        nrm = np.tile([0.0, 0.0, 1.0], (n, 1))
    if uv is None:
        uv = pos[:, :2] / 100.0
    joints = np.zeros((n, 8), np.int64)
    w = np.zeros((n, 8))
    if weights is None:
        w[:, 0] = 1.0
    else:
        joints[:, 1] = 1
        w[:, 0], w[:, 1] = weights, 1.0 - weights
    streams = dict(pos=pos, nrm=np.asarray(nrm, np.float64), tan=np.tile([1.0, 0, 0, 1], (n, 1)),
                   uv=np.asarray(uv, np.float64), joints=joints, weights=w)
    return {'bones': {'names': ['A', 'B'], 'parents': [-1, 0]},
            'prims': [dict(part=part, material=mat, tris=np.asarray(t, np.int64), **streams)
                      for part, mat, t in prims],
            'parts': {part: {'first': 0} for part, _, _ in prims}}


def grid(n, size=100.0, x0=0.0):
    """n x n points over a size x size square (z = 0) -> (points, triangles facing +z)."""
    xs = np.linspace(x0, x0 + size, n)
    pts = np.array([(x, y, 0.0) for y in np.linspace(0, size, n) for x in xs])
    tris = []
    for j in range(n - 1):
        for i in range(n - 1):
            a, b, c, d = j * n + i, j * n + i + 1, (j + 1) * n + i, (j + 1) * n + i + 1
            tris += [(a, b, d), (a, d, c)]
    return pts, np.array(tris)


def icosphere(levels=3, radius=50.0):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    v = [np.array(p, np.float64) / np.linalg.norm(p) for p in v]
    for _ in range(levels):
        mid, nf = {}, []

        def m(a, b):
            k = (min(a, b), max(a, b))
            if k not in mid:
                p = v[a] + v[b]
                v.append(p / np.linalg.norm(p))
                mid[k] = len(v) - 1
            return mid[k]
        for a, b, c in f:
            ab, bc, ca = m(a, b), m(b, c), m(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    v = np.array(v)
    return v * radius, np.array(f), v


def disc(rings=12, radius=50.0):
    """A flat disc of rings round a centre point (z = 0) -> (points, triangles facing +z)."""
    pts, tris, prev = [(0.0, 0.0, 0.0)], [], [0]
    for r in range(1, rings + 1):
        n = 6 * r
        cur = list(range(len(pts), len(pts) + n))
        pts += [(radius * r / rings * np.cos(2 * np.pi * k / n), radius * r / rings * np.sin(2 * np.pi * k / n), 0.0)
                for k in range(n)]
        for k in range(n):
            j, j2 = int(round(k * len(prev) / n)) % len(prev), int(round((k + 1) * len(prev) / n)) % len(prev)
            tris.append((prev[j], cur[k], cur[(k + 1) % n]))
            if j2 != j:
                tris.append((prev[j], cur[(k + 1) % n], prev[j2]))
        prev = cur
    return np.array(pts), np.array(tris)


def edges(points, tris):
    """Position-level edges of triangles (vertex ids made position ids) -> (edges, triangles per edge)."""
    _, pid = np.unique(np.round(points, 6), axis=0, return_inverse=True)
    p = pid.reshape(-1)[tris]
    e = np.sort(np.concatenate([p[:, [0, 1]], p[:, [1, 2]], p[:, [2, 0]]]), 1)
    return np.unique(e, axis=0, return_counts=True)


def face_normals(pos, tris):
    return np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])


def area(pos, tris):
    return 0.5 * np.linalg.norm(face_normals(pos, tris), axis=1).sum()


def quiet(*_):
    pass


@unittest.skipUnless(HAVE_CC, 'needs a C compiler')
class Decimate(unittest.TestCase):
    def test_grid_keeps_its_outline_and_faces(self):
        pts, tris = grid(30)
        m = model_of(pts, [('bdf', 'MI_cloth', tris)], weights=pts[:, 0] / 100.0)
        out = decimate.decimate(m, 300, log=quiet)
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 300)
        self.assertAlmostEqual(area(p['pos'], p['tris']), 100.0 * 100.0, delta=1e-6)   # no holes, no overlaps
        self.assertTrue((face_normals(p['pos'], p['tris'])[:, 2] > 0).all())             # no flips
        ue, cnt = edges(p['pos'], p['tris'])
        self.assertFalse((cnt > 2).any())
        on_rim = np.unique(np.round(p['pos'], 6), axis=0)[np.unique(ue[cnt == 1])]
        self.assertTrue((np.isclose(on_rim[:, 0], 0) | np.isclose(on_rim[:, 0], 100) | np.isclose(on_rim[:, 1], 0) |
                         np.isclose(on_rim[:, 1], 100)).all())                            # the outline stays outline
        corners = {(0.0, 0.0), (100.0, 0.0), (0.0, 100.0), (100.0, 100.0)}
        self.assertTrue(corners <= {tuple(q) for q in np.round(p['pos'][:, :2], 6)})

    def test_open_boundary_stays_where_it_was(self):
        pts, tris = disc()
        m = model_of(pts, [('bdf', 'MI_cloth', tris)])
        with mock.patch.object(decimate, 'FEATURE_WEIGHT', 0.0):      # the rule alone, without the rim's planes
            out = decimate.decimate(m, 40, log=quiet)
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 40)
        ue, cnt = edges(p['pos'], p['tris'])
        rim = np.unique(np.round(p['pos'], 6), axis=0)[np.unique(ue[cnt == 1])]
        np.testing.assert_allclose(np.linalg.norm(rim, axis=1), 50.0, atol=1e-6)
        self.assertTrue((face_normals(p['pos'], p['tris'])[:, 2] > 0).all())
        p = decimate.decimate(m, 40, log=quiet)['prims'][0]           # the planes keep the rim round
        self.assertGreater(area(p['pos'], p['tris']), 0.98 * area(pts, tris))

    def test_no_fold_overs_in_a_flat_l(self):
        # flat: every collapse inside costs nothing, only the normal test keeps triangles from folding over the notch
        pts, tris = grid(21)
        notch = (pts[tris].mean(1)[:, 0] > 50) & (pts[tris].mean(1)[:, 1] > 50)
        m = model_of(pts, [('bdf', 'MI_cloth', tris[~notch])])
        out = decimate.decimate(m, 8, log=quiet)
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 8)
        self.assertTrue((face_normals(p['pos'], p['tris'])[:, 2] > 0).all())
        self.assertAlmostEqual(area(p['pos'], p['tris']), 7500.0, delta=1e-6)

    def test_streams_are_the_kept_vertices_own(self):
        pts, tris = grid(20)
        m = model_of(pts, [('bdf', 'MI_cloth', tris[:300]), ('bdf', 'MI_other', tris[300:])],
                     weights=np.linspace(0, 1, len(pts)))
        out = decimate.decimate(m, 150, log=quiet)
        src = out['source']
        a, b = out['prims']
        for k in ('pos', 'nrm', 'tan', 'uv', 'joints', 'weights'):
            self.assertIs(a[k], b[k])                                                     # shared again
            np.testing.assert_array_equal(a[k], m['prims'][0][k][src])                    # no blends
        self.assertEqual(a['tris'].dtype, np.int64)
        self.assertEqual(sorted(np.unique(np.concatenate([a['tris'], b['tris']]))), list(range(len(src))))
        self.assertEqual(out['parts']['bdf']['first'], 0)

    def test_sphere_stays_closed_and_round(self):
        pts, tris, nrm = icosphere()
        m = model_of(pts, [('bdf', 'MI_skin', tris)], nrm=nrm, uv=nrm[:, :2])
        out = decimate.decimate(m, 30, log=quiet)
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 30)
        self.assertLess(len(p['tris']), len(tris))
        ue, cnt = edges(p['pos'], p['tris'])
        self.assertTrue((cnt == 2).all())                                                 # closed, manifold
        centre = p['pos'][p['tris']].mean(1)
        self.assertTrue(((face_normals(p['pos'], p['tris']) * centre).sum(1) > 0).all())  # all face out
        vol = (np.cross(p['pos'][p['tris'][:, 0]], p['pos'][p['tris'][:, 1]]) *
               p['pos'][p['tris'][:, 2]]).sum() / 6.0
        self.assertGreater(vol, 0.6 * 4 / 3 * np.pi * 50.0 ** 3)

    def test_sphere_at_its_least_is_still_a_solid(self):
        pts, tris, nrm = icosphere(2)
        m = model_of(pts, [('bdf', 'MI_skin', tris)], nrm=nrm, uv=nrm[:, :2])
        out = decimate.decimate(m, 4, log=quiet)                       # more than it can give
        p = out['prims'][0]
        self.assertGreaterEqual(len(p['tris']), 4)
        self.assertEqual(len(np.unique(np.sort(p['tris'], 1), axis=0)), len(p['tris']))  # no doubled triangles
        ue, cnt = edges(p['pos'], p['tris'])
        self.assertTrue((cnt == 2).all())
        centre = p['pos'][p['tris']].mean(1) - p['pos'][np.unique(p['tris'])].mean(0)
        self.assertTrue(((face_normals(p['pos'], p['tris']) * centre).sum(1) > 0).all())

    def test_folds_keep_their_rounding(self):
        # a hem: two sheets 4 mm apart joined by a half round, smooth normals turning through it
        prof = [(x, 2.0, 0.0, 1.0) for x in np.linspace(0, 50, 11)]
        prof += [(50 + 2 * np.sin(a), 2 * np.cos(a), np.sin(a), np.cos(a)) for a in np.linspace(0, np.pi, 9)[1:-1]]
        prof += [(x, -2.0, 0.0, -1.0) for x in np.linspace(50, 0, 11)]
        cols, rows = len(prof), 15
        pts = np.array([(x, y, z) for y in np.linspace(0, 100, rows) for x, z, _, _ in prof])
        nrm = np.array([(nx, 0.0, nz) for _ in range(rows) for _, _, nx, nz in prof])
        tris = []
        for r in range(rows - 1):
            for c in range(cols - 1):
                a = r * cols + c
                tris += [(a, a + 1, a + cols + 1), (a, a + cols + 1, a + cols)]
        tris = np.array(tris)
        m = model_of(pts, [('bdf', 'MI_cloth', tris)], nrm=nrm, uv=pts[:, [0, 1]] / 100.0)
        out = decimate.decimate(m, 60, log=quiet)
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 60)
        n = p['nrm'][p['tris']]
        spread = np.minimum(np.minimum((n[:, 0] * n[:, 1]).sum(1), (n[:, 1] * n[:, 2]).sum(1)),
                            (n[:, 0] * n[:, 2]).sum(1))
        self.assertGreaterEqual(spread.min(), -1e-9)            # no triangle joins the sheets across the fold

    def test_border_between_two_materials_stays_closed(self):
        # two grids side by side, each with its own copy of the column where they meet (as exported meshes have)
        pa, ta = grid(16, 100.0, 0.0)
        pb, tb = grid(16, 100.0, 100.0)
        pts = np.concatenate([pa, pb])
        m = model_of(pts, [('bdf', 'MI_left', ta), ('bdf', 'MI_right', tb + len(pa))])
        out = decimate.decimate(m, 200, log=quiet)
        left, right = out['prims']
        pos = left['pos']
        self.assertLessEqual(decimate.count(out), 200)
        self.assertAlmostEqual(area(pos, left['tris']), 100.0 * 100.0, delta=1e-6)
        self.assertAlmostEqual(area(pos, right['tris']), 100.0 * 100.0, delta=1e-6)
        self.assertTrue((pos[np.unique(left['tris'])][:, 0] <= 100.0 + 1e-9).all())
        self.assertTrue((pos[np.unique(right['tris'])][:, 0] >= 100.0 - 1e-9).all())

        def border(tris):
            ue, cnt = edges(pos, tris)
            q = np.round(pos, 6)
            keys = {tuple(r): i for i, r in enumerate(np.unique(q, axis=0))}
            back = {i: r for r, i in keys.items()}
            return {(back[a], back[b]) for a, b in ue[cnt == 1] if back[a][0] == 100.0 and back[b][0] == 100.0}
        self.assertTrue(border(left['tris']))
        self.assertEqual(border(left['tris']), border(right['tris']))                    # no cracks
        ue, cnt = edges(pos, np.concatenate([left['tris'], right['tris']]))
        self.assertFalse((cnt > 2).any())

    def test_uv_seam_stays_closed(self):
        # a tube whose last column repeats the first's positions with u = 1 (the seam)
        cols, rows = 24, 16
        pts, uv = [], []
        for r in range(rows):
            for c in range(cols + 1):
                t = 2 * np.pi * c / cols
                pts.append((30 * np.cos(t), 30 * np.sin(t), 8.0 * r))
                uv.append((c / cols, r / (rows - 1)))
        pts, uv = np.array(pts), np.array(uv)
        pts[cols::cols + 1] = pts[0::cols + 1]
        tris = []
        for r in range(rows - 1):
            for c in range(cols):
                a, b = r * (cols + 1) + c, r * (cols + 1) + c + 1
                tris += [(a, b, b + cols + 1), (a, b + cols + 1, a + cols + 1)]
        nrm = pts * [1, 1, 0] / 30.0
        m = model_of(pts, [('bdf', 'MI_sleeve', tris)], nrm=nrm, uv=uv)
        out = decimate.decimate(m, 160, log=quiet)
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 160)
        ue, cnt = edges(p['pos'], p['tris'])
        self.assertFalse((cnt > 2).any())
        q = np.unique(np.round(p['pos'], 6), axis=0)
        ends = q[np.unique(ue[cnt == 1])][:, 2]
        self.assertTrue(np.isin(np.round(ends, 6), [0.0, 8.0 * (rows - 1)]).all())        # only the tube's ends open
        spans = np.ptp(p['uv'][p['tris']][:, :, 0], axis=1)
        self.assertLess(spans.max(), 0.5)                                                 # no triangle across the seam

    def cards(self, width):
        """30 hair cards: strips two points wide, 12 long, bent a little -> (model, their corners)."""
        pts, tris, corners = [], [], []
        rng = np.random.default_rng(3)
        for k in range(30):
            base = len(pts)
            x0, y0 = (k % 6) * 30.0, (k // 6) * 40.0
            for i in range(12):
                for side in (0, 1):
                    s = i * 3.0
                    pts.append((x0 + side * width, y0 + s, 0.002 * s * s + rng.normal(0, 0.01)))
            for i in range(11):
                a = base + 2 * i
                tris += [(a, a + 1, a + 3), (a, a + 3, a + 2)]
            corners += [base, base + 1, base + 22, base + 23]
        pts = np.array(pts)
        uv = np.stack([(pts[:, 0] % 30.0) / width, (pts[:, 1] % 40.0) / 33.0], 1)
        return model_of(pts, [('har', 'MI_CH_xyz_har_1p', tris)], uv=uv), corners

    def test_card_corners_stay_when_they_are_the_cheapest(self):
        # only the length of the edge counts: the 2 mm ends are shorter than the 3 mm steps along a card
        m, corners = self.cards(2.0)
        with mock.patch.multiple(decimate, FEATURE_WEIGHT=0.0, UV_WEIGHT=0.0, CARD_UV_WEIGHT=0.0, NORMAL_SCALE=0.0):
            out = decimate.decimate(m, 120, log=quiet)
        self.assertEqual(sorted(out['source'].tolist()), sorted(corners))

    def test_corners_go_only_when_nothing_else_fits(self):
        m, corners = self.cards(4.0)
        said = []
        out = decimate.decimate(m, 100, log=said.append)               # fewer than the 120 corners
        self.assertLessEqual(decimate.count(out), 100)
        self.assertTrue(any('corners' in s for s in said))

    def test_cards_keep_their_corners(self):
        m, corners = self.cards(4.0)
        out = decimate.decimate(m, 120, log=quiet)                     # down to four points a card
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 120)
        self.assertEqual(sorted(out['source'].tolist()), sorted(corners))                 # every card's corners
        ue, cnt = edges(p['pos'], p['tris'])
        self.assertFalse((cnt > 2).any())
        cards = {}
        for t in out['source'][p['tris']]:
            cards.setdefault(int(t[0]) // 24, set()).update(int(x) for x in t)
        self.assertEqual(len(cards), 30)
        self.assertTrue(all(len(v) == 4 for v in cards.values()))

    def test_part_weights_share_out_the_reduction(self):
        pts, tris, nrm = icosphere()
        n = len(pts)
        both = np.concatenate([pts, pts + [200.0, 0, 0]])
        m = model_of(both, [('bdf', 'MI_body', tris), ('fac', 'MI_face_skin', tris + n)],
                     nrm=np.concatenate([nrm, nrm]), uv=np.concatenate([nrm[:, :2], nrm[:, :2]]))
        out = decimate.decimate(m, n, {'bdf': 1.0, 'fac': 0.3}, log=quiet)
        body, face = (len(np.unique(p['tris'])) for p in out['prims'])
        self.assertLessEqual(body + face, n)
        lost_body, lost_face = 1 - body / n, 1 - face / n
        self.assertAlmostEqual(lost_face / lost_body, 0.3, delta=0.03)
        self.assertLessEqual(decimate.count(decimate.decimate(m, n, log=quiet)), n)       # no quotas: errors alone

    def test_part_weight_zero_keeps_a_part(self):
        pa, ta = grid(12)
        pb, tb = grid(12, 100.0, 300.0)
        m = model_of(np.concatenate([pa, pb]), [('bdf', 'MI_a', ta), ('fac', 'MI_b', tb + len(pa))])
        out = decimate.decimate(m, 160, {'fac': 0.0}, log=quiet)
        self.assertEqual(len(np.unique(out['prims'][1]['tris'])), len(pb))
        self.assertLessEqual(decimate.count(out), 160)

    def test_degenerate_triangles_go(self):
        pts, tris = grid(10)
        pts = np.concatenate([pts, pts[:1]])                                               # a copy of point 0
        bad = np.array([[0, 0, 1], [len(pts) - 1, 0, 11]])
        m = model_of(pts, [('bdf', 'MI_cloth', np.concatenate([tris, bad]))])
        out = decimate.decimate(m, 60, log=quiet)
        p = out['prims'][0]
        q = np.round(p['pos'], 6)[p['tris']]
        same = (q[:, 0] == q[:, 1]).all(1) | (q[:, 1] == q[:, 2]).all(1) | (q[:, 0] == q[:, 2]).all(1)
        self.assertFalse(same.any())

    def test_within_target_returns_the_model(self):
        pts, tris = grid(5)
        m = model_of(pts, [('bdf', 'MI_cloth', tris)])
        self.assertIs(decimate.decimate(m, 25, log=quiet), m)

    def test_large_model_is_quick(self):
        pts, tris = grid(280, 1000.0)
        pts[:, 2] = 20 * np.sin(pts[:, 0] / 70.0) * np.cos(pts[:, 1] / 90.0)
        m = model_of(pts, [('bdf', 'MI_cloth', tris)])
        t0 = time.time()
        out = decimate.decimate(m, 30000, log=quiet)
        self.assertLessEqual(decimate.count(out), 30000)
        self.assertLess(time.time() - t0, 30.0)


class Budget(unittest.TestCase):
    def test_count_is_per_primitive(self):
        pts, tris = grid(4)
        m = model_of(pts, [('bdf', 'MI_a', tris), ('bdf', 'MI_b', tris[:2])])
        self.assertEqual(decimate.count(m), 16 + 4)

    def test_target_leaves_room_for_colour_layers(self):
        pts, tris = grid(11)
        m = model_of(pts, [('bdf', 'MI_CH_xyz_outerwear', tris[:120]), ('fac', 'MI_CH_xyz_face_skin', tris[120:]),
                           ('har', 'MI_CH_xyz_har_1p', tris[120:])])
        self.assertEqual(decimate.layered_materials(m), {'MI_CH_xyz_outerwear'})
        layered = len(np.unique(tris[:120]))
        total = decimate.count(m)
        self.assertEqual(decimate.vertex_target(m, budget=42000), int(42000 / (1 + layered / float(total))))
        self.assertEqual(decimate.vertex_target(m, layered=(), budget=1000), 1000)


class Build(unittest.TestCase):
    def test_no_compiler_says_what_to_install(self):
        env = {k: v for k, v in os.environ.items() if k not in ('CC', 'TTT2_NATIVE_DECIMATE')}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(native.shutil, 'which', return_value=None):
            with self.assertRaises(InputError) as e:
                decimate._build(tmp)
            self.assertIn('gcc', str(e.exception))

    @unittest.skipUnless(HAVE_CC, 'needs a C compiler')
    def test_built_once_into_the_cache(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {'TTT2_NATIVE_DECIMATE': ''}):
            lib = decimate._build(tmp)
            self.assertEqual(lib, native.output_path('decimate', cache=tmp))
            stamp = os.path.getmtime(lib)
            self.assertEqual(decimate._build(tmp), lib)
            self.assertEqual(os.path.getmtime(lib), stamp)


if __name__ == '__main__':
    unittest.main()
