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

HAVE_CC = bool(native.compiler())


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


def tube(rings=61, around=12, length=300.0, radius=30.0):
    """An open tube along +x -> (points, normals, triangles facing out)."""
    a = 2 * np.pi * np.arange(around) / around
    pts = np.array([(x, radius * np.cos(t), radius * np.sin(t)) for x in np.linspace(0, length, rings) for t in a])
    nrm = np.array([(0.0, np.cos(t), np.sin(t)) for _ in range(rings) for t in a])
    tris = []
    for r in range(rings - 1):
        for k in range(around):
            p, q = r * around + k, r * around + (k + 1) % around
            tris += [(p, p + around, q), (q, p + around, q + around)]
    return pts, nrm, np.array(tris)


def turn_about_z(pivot, degrees):
    t = np.radians(degrees)
    m = np.eye(4)
    m[:3, :3] = [[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]]
    m[:3, 3] = np.asarray(pivot, np.float64) - m[:3, :3] @ pivot
    return m


def skinned(p, pose):
    """A prim's vertices skinned by one pose ((bones, 4, 4) changes; model_of's two influences)."""
    w = p['weights'] / p['weights'].sum(1, keepdims=True)
    M = np.einsum('vk,vkij->vij', w, pose[p['joints']])
    return np.einsum('vij,vj->vi', M[:, :3, :3], p['pos']) + M[:, :3, 3]


def off_surface(points, pos, tris, n=10):
    """The farthest of `points` from the triangles (pos, tris), measured to points sampled on them."""
    a, b = np.meshgrid(np.arange(n + 1), np.arange(n + 1))
    keep = a + b <= n
    u, v = a[keep] / n, b[keep] / n
    s = ((1 - u - v)[None, :, None] * pos[tris[:, 0]][:, None] + u[None, :, None] * pos[tris[:, 1]][:, None] +
         v[None, :, None] * pos[tris[:, 2]][:, None]).reshape(-1, 3)
    return max(float(np.min(np.linalg.norm(s - x, axis=1))) for x in points)


@unittest.skipUnless(HAVE_CC, 'needs a C compiler')
class Folds(unittest.TestCase):
    """A tube skinned to bone A at one end and to B at the other, the weights passing from A to B over a long band
    in the middle (x 90..210, as along an arm), and a test pose that turns B by 90 degrees about the band's middle."""

    def setUp(self):
        self.pts, self.nrm, self.tris = tube()
        self.wa = np.clip((210.0 - self.pts[:, 0]) / 120.0, 0, 1)          # A's weight
        self.bent = np.stack([np.eye(4), turn_about_z([150.0, 0, 0], 90)])
        self.full = skinned(self.model()['prims'][0], self.bent)

    def model(self):
        return model_of(self.pts, [('bdf', 'MI_skin', self.tris)], nrm=self.nrm, weights=self.wa)

    def test_band_keeps_its_vertices_and_the_ends_give_theirs(self):
        out = decimate.decimate(self.model(), 60, log=quiet, poses=[self.bent])
        p = out['prims'][0]
        self.assertLessEqual(decimate.count(out), 60)
        used = np.unique(p['tris'])
        x = p['pos'][used, 0]
        # inside the one-bone ends nothing but their rims is left (they only turn: their middles are free to go)
        self.assertFalse(((x > 1) & (x < 89)).any() or ((x > 211) & (x < 299)).any())
        # the band's weights still pass in steps of at most twice the fold step
        w = np.unique(np.round(p['weights'][used, 0], 6))
        self.assertLessEqual(np.diff(w).max(), 2 * decimate.FOLD_STEP + 1e-6)
        self.assertGreaterEqual(((w > 0.2) & (w < 0.8)).sum(), 2)

    def test_the_ranges_hold_from_pass_to_pass(self):
        # a six-sided tube that may lose only 30% a pass (seven passes): what each survivor stands for carries over
        # to the next pass, so the band keeps its rings until the rule gives way, and says so (started afresh in each
        # pass, the steps added up and the band wore down to the target without a word)
        pts, nrm, tris = tube(61, 6)
        m = model_of(pts, [('bdf', 'MI_skin', tris)], nrm=nrm, weights=np.clip((210.0 - pts[:, 0]) / 120.0, 0, 1))
        said = []
        with mock.patch.object(decimate, 'MOST_REMOVED', 0.3):
            out = decimate.decimate(m, 22, {'bdf': 1.0}, log=said.append, poses=[self.bent])
        self.assertLessEqual(decimate.count(out), 22)
        held = [int(s.split()[1]) for s in said if 'folds kept' in s]
        self.assertTrue(held and held[0] >= 24, said)

    def test_bent_it_stays_closer_to_the_full_model(self):
        dist = []
        for poses in (None, [self.bent]):
            p = decimate.decimate(self.model(), 60, log=quiet, poses=poses)['prims'][0]
            dist.append(off_surface(self.full, skinned(p, self.bent), p['tris']))
        self.assertLess(dist[1], 0.8 * dist[0])

    def test_one_bone_is_as_without_poses(self):
        m = model_of(self.pts, [('bdf', 'MI_skin', self.tris)], nrm=self.nrm)            # all on A: the pose
        a = decimate.decimate(m, 60, log=quiet)                                         # moves nothing of it
        b = decimate.decimate(m, 60, log=quiet, poses=[self.bent])
        self.assertEqual(a['source'].tolist(), b['source'].tolist())
        self.assertEqual(a['prims'][0]['tris'].tolist(), b['prims'][0]['tris'].tolist())

    def test_a_part_short_of_its_quota_with_folds_kept_passes_them_on(self):
        tube_pts, tube_nrm, tube_tris = tube(31, 8)                      # (a coarser one: 95% of it may go)
        grid_pts, grid_tris = grid(16, 200.0)
        pts = np.concatenate([tube_pts, grid_pts + [0, 0, 200.0]])
        nrm = np.concatenate([tube_nrm, np.tile([0, 0, 1.0], (len(grid_pts), 1))])
        wa = np.clip((210.0 - tube_pts[:, 0]) / 120.0, 0, 1)
        m = model_of(pts, [('bdf', 'MI_skin', tube_tris), ('fac', 'MI_face', grid_tris + len(tube_pts))], nrm=nrm,
                     weights=np.concatenate([wa, np.ones(len(grid_pts))]))
        plain = decimate.decimate(m, 150, {'bdf': 1.0, 'fac': 0.1}, log=quiet)
        folds = decimate.decimate(m, 150, {'bdf': 1.0, 'fac': 0.1}, log=quiet, poses=[self.bent])
        sizes = [[len(np.unique(p['tris'])) for p in o['prims']] for o in (plain, folds)]
        self.assertLessEqual(sum(sizes[1]), 150)
        self.assertGreater(sizes[1][0], sizes[0][0])                    # the tube keeps more, the grid gives more
        self.assertLess(sizes[1][1], sizes[0][1])

    def test_folds_give_way_when_nothing_else_fits(self):
        # 16: kept, the folds leave 24 to 28 vertices, so they must give way. (12 was too near what a 732-vertex tube
        # can come down to at all: points one ulp off, as another platform's sin and cos make them, ended at 13 or 14
        # one time in ten, with decimate's warning; Windows CI got 13)
        said = []
        out = decimate.decimate(self.model(), 16, log=said.append, poses=[self.bent])
        self.assertLessEqual(decimate.count(out), 16)
        self.assertTrue(any('folds' in s for s in said))


class BendPoses(unittest.TestCase):
    def skeleton(self):
        """Shoulder (L_Arm) -> elbow (L_ForeArm) -> wrist (L_Hand) along +x, a twist helper under the forearm and an
        elbow helper under the upper arm that follows the forearm by half."""
        names = ['L_Arm', 'L_ForeArm', 'L_Hand', 'L_ForeArm_twist', 'L_Elbow_half']
        at = [(0.0, 0, 0), (300.0, 0, 0), (550.0, 0, 0), (420.0, 0, 0), (300.0, 0, 0)]
        world = np.tile(np.eye(4), (5, 1, 1))
        world[:, :3, 3] = at
        return {'names': names, 'parents': [-1, 0, 1, 1, 0], 'world': world,
                'follow': [None, None, None, None, (1, 0.5)]}

    def test_poses_turn_the_bent_joints_and_carry_the_rest(self):
        from ttt2char.convert import skeleton
        bones = self.skeleton()
        with mock.patch.object(skeleton, 'BENDS', [('L_ForeArm', 'L_Hand', 90)]):
            poses = skeleton.bend_poses(bones)
        self.assertEqual(len(poses), 2)
        for D in poses:
            np.testing.assert_allclose(D[0], np.eye(4), atol=1e-9)                       # the shoulder stays
            hand = (D[2] @ bones['world'][2])[:3, 3]
            self.assertAlmostEqual(np.linalg.norm(hand - [300.0, 0, 0]), 250.0, places=6)  # turned about the elbow
            self.assertAlmostEqual(float((hand - [300.0, 0, 0]) @ [1.0, 0, 0]), 0.0, places=6)
            np.testing.assert_allclose(D[3], D[1], atol=1e-9)                          # the twist helper with it
        groups, bends = decimate.skin_groups(bones, poses)
        self.assertEqual(groups[3], groups[1])
        self.assertEqual(len({groups[0], groups[1], groups[4]}), 3)
        self.assertAlmostEqual(bends[groups[1]], 1.0, places=6)                        # 90 of FOLD_BEND's 90
        self.assertAlmostEqual(bends[groups[4]], 0.5, places=6)                        # the half helper
        self.assertEqual(bends[groups[0]], 0.0)

    def test_no_bent_joint_no_poses(self):
        from ttt2char.convert import skeleton
        bones = self.skeleton()
        bones['names'] = ['a', 'b', 'c', 'd', 'e']
        self.assertEqual(skeleton.bend_poses(bones), [])


@unittest.skipUnless(HAVE_CC, 'needs a C compiler')
class Classes(unittest.TestCase):
    """decimate(classes=): in a part, each skin material and each large piece keeps a floor share of its vertices
    while anything else can give; its small pieces go down to their allowances first."""

    def body(self):
        """A body part with bare skin (a grid) and cloth (a grid), and a face part (a grid), side by side."""
        pa, ta = grid(12)
        pb, tb = grid(12, 100.0, 300.0)
        pc, tc = grid(12, 100.0, 600.0)
        return model_of(np.concatenate([pa, pb, pc]), [('bdf', 'MI_CH_xyz_arm_skin', ta),
                                                       ('bdf', 'MI_CH_xyz_cloth', tb + len(pa)),
                                                       ('fac', 'MI_CH_xyz_face_skin', tc + 2 * len(pa))])

    @staticmethod
    def kept(out, material):
        return sum(len(np.unique(p['tris'])) for p in out['prims'] if p['material'] == material)

    def test_quotas_keep_the_floors(self):
        quota = decimate._quotas(np.array([100, 100]), np.array([1.0, 1.0]), 120, np.zeros(2, bool),
                                 np.array([80.0, 0.0]))
        self.assertEqual(quota.tolist(), [80, 40])                          # (60 / 60 without the floor)
        self.assertEqual(decimate._quotas(np.array([100, 100]), np.array([1.0, 1.0]), 120,
                                          np.zeros(2, bool)).tolist(), [60, 60])

    def test_skin_keeps_its_floor_while_others_give(self):
        m = self.body()
        weights = {'bdf': 1.0, 'fac': 1.0}
        plain = decimate.decimate(m, 200, weights, log=quiet)
        self.assertLess(self.kept(plain, 'MI_CH_xyz_arm_skin'), 72)        # (the errors share it out: ~1/3 each)
        out = decimate.decimate(m, 200, weights, log=quiet, classes={'bdf': {'skin': 0.5}})
        self.assertGreaterEqual(self.kept(out, 'MI_CH_xyz_arm_skin'), 72)  # (half of its 144)
        self.assertLessEqual(decimate.count(out), 200)
        # the face's skin is in a part without classes: no floor
        self.assertLess(self.kept(out, 'MI_CH_xyz_face_skin'), self.kept(plain, 'MI_CH_xyz_face_skin'))

    def test_floors_give_way_when_nothing_else_fits(self):
        lines = []
        out = decimate.decimate(self.body(), 120, {'bdf': 1.0, 'fac': 1.0}, log=lines.append,
                                classes={'bdf': {'skin': 0.9}})                # (the grids' corners and 130)
        self.assertLessEqual(decimate.count(out), 120)
        self.assertTrue(any('floors kept; going on without' in line for line in lines))

    def test_each_large_piece_keeps_its_floor(self):
        """Two large pieces (150 mm) of one material and a face: each piece keeps its share, however the errors would
        share the part out (one of them is finely made: errors favour taking the other)."""
        pa, ta = grid(12, 150.0)
        pb, tb = grid(20, 150.0, 300.0)
        pc, tc = grid(12, 100.0, 600.0)
        m = model_of(np.concatenate([pa, pb, pc]), [('bdf', 'MI_CH_xyz_cloth', np.concatenate([ta, tb + len(pa)])),
                                                    ('fac', 'MI_CH_xyz_face_skin', tc + len(pa) + len(pb))])
        out = decimate.decimate(m, 300, {'bdf': 1.0, 'fac': 1.0}, log=quiet, classes={'bdf': {'big': 0.4}})
        q = out['prims'][0]
        used = np.unique(q['tris'])
        left = (q['pos'][used, 0] < 200).sum()
        self.assertGreaterEqual(left, int(0.4 * 144))
        self.assertGreaterEqual(len(used) - left, int(0.4 * 400))
        self.assertLessEqual(decimate.count(out), 300)

    def test_small_pieces_go_to_their_allowance_first(self):
        """Six beads (spheres 10 mm across, 162 vertices) and a sheet: the beads go down to SMALL_LEAST + 1 per mm
        first, then keep it while the sheet gives the rest (without: the beads' share)."""
        bead, btris, bnrm = icosphere(2, 5.0)
        pa, ta = grid(12, 150.0)
        pos, tris, nrm = [pa], [ta], [np.tile([0.0, 0, 1], (len(pa), 1))]
        for i in range(6):
            tris.append(btris + sum(len(x) for x in pos))
            pos.append(bead + [30.0 * i, 0, 50.0])
            nrm.append(bnrm)
        pos, nrm = np.concatenate(pos), np.concatenate(nrm)
        m = model_of(pos, [('bdf', 'MI_CH_xyz_cloth', np.concatenate(tris))], nrm=nrm, uv=nrm[:, :2])
        lines = []
        out = decimate.decimate(m, 200, {'bdf': 1.0}, log=lines.append, classes={'bdf': {'small': 1.0}})
        q = out['prims'][0]
        used = np.unique(q['tris'])
        on_beads = q['pos'][used, 2] > 25
        allowance = decimate.SMALL_LEAST + 10
        self.assertLessEqual(on_beads.sum(), 6 * allowance)
        self.assertGreaterEqual(on_beads.sum(), 6 * 4)
        self.assertLessEqual(len(used), 200)
        self.assertTrue(any('bdf small %d ->' % (6 * 162) in line for line in lines))
        plain = decimate.decimate(m, 200, {'bdf': 1.0}, log=quiet)['prims'][0]
        sheet = (plain['pos'][np.unique(plain['tris']), 2] < 25).sum()
        self.assertLess(sheet, (~on_beads).sum())                             # (the beads kept more of theirs)


def ribbon(around=61, across=5, width=20.0, radius=61.0, arc=2.6, length=300.0):
    """A strap round tube()'s axis: a ribbon `width` wide over `arc` radians of a circle of `radius`, across the tube's
    middle -> (points, normals, triangles facing out)."""
    a = np.linspace(0.0, arc, around)
    xs = length / 2 + np.linspace(-width / 2, width / 2, across)
    pts = np.array([(x, radius * np.cos(t), radius * np.sin(t)) for t in a for x in xs])
    nrm = np.array([(0.0, np.cos(t), np.sin(t)) for t in a for _ in xs])
    tris = []
    for r in range(around - 1):
        for k in range(across - 1):
            p, q = r * across + k, r * across + k + 1
            tris += [(p, q, p + across), (q, q + across, p + across)]
    return pts, nrm, np.array(tris)


def surface_samples(pos, tris, n=6):
    a, b = np.meshgrid(np.arange(n + 1), np.arange(n + 1))
    keep = a + b <= n
    u, v = a[keep] / n, b[keep] / n
    return ((1 - u - v)[None, :, None] * pos[tris[:, 0]][:, None] + u[None, :, None] * pos[tris[:, 1]][:, None] +
            v[None, :, None] * pos[tris[:, 2]][:, None]).reshape(-1, 3)


@unittest.skipUnless(HAVE_CC, 'needs a C compiler')
class Lying(unittest.TestCase):
    """decimate(classes={'lying': ...}): a strap lying on the skin stays on it; 'reach', 'skin_reach' bound a piece's
    and the skin's points; the skin ends under what lies on it."""

    def body(self):
        """A smooth tube of skin (radius 60), a strap over it by 1 mm, a face part with room to give (a fine sphere)."""
        ps, ns, ts = tube(rings=61, around=48, radius=60.0)
        pr, nr, tr = ribbon()
        pc, tc, nc = icosphere(levels=4, radius=50.0)
        pc = pc + [0.0, 500.0, 0.0]
        pos = np.concatenate([ps, pr, pc])
        nrm = np.concatenate([ns, nr, nc])
        return model_of(pos, [('bdf', 'MI_CH_xyz_body_skin', ts), ('bdf', 'MI_CH_xyz_strap', tr + len(ps)),
                              ('fac', 'MI_CH_xyz_face', tc + len(ps) + len(pr))], nrm=nrm)

    @staticmethod
    def prim(out, material):
        return [p for p in out['prims'] if p['material'] == material][0]

    def strap_inside(self, out):
        """How deep the new strap goes under the skin's radius (mm; < 0: nowhere under)."""
        q = self.prim(out, 'MI_CH_xyz_strap')
        s = surface_samples(q['pos'], q['tris'])
        return 60.0 - float(np.hypot(s[:, 1], s[:, 2]).min())

    def test_surface_gap(self):
        c = np.array([[[0.0, 0, 0], [10, 0, 0], [0, 10, 0]]])
        n = np.array([[0.0, 0, 1]])
        pts = np.array([[1.0, 1, 2], [1, 1, -2], [1, 1, -0.5], [1, 1, 20], [30, 1, 2], [13, 1, 1]])
        g = decimate.surface_gap(pts, c, n, 8.0)
        self.assertAlmostEqual(g[0], 2.0)
        self.assertAlmostEqual(g[1], -2.0)
        self.assertTrue(np.isnan(g[3]) and np.isnan(g[4]))                 # (too far)
        self.assertTrue(np.isnan(g[5]))                                    # (beside it: past its edge, not over it)
        g, tri = decimate.surface_gap(pts, c, n, 8.0, under=1.0, which=True)
        self.assertTrue(np.isnan(g[1]))                                    # (under it by more than `under`)
        self.assertAlmostEqual(g[2], -0.5)
        self.assertEqual(tri.tolist(), [0, -1, 0, -1, -1, -1])
        own = decimate.surface_gap(pts[:1], c, n, 8.0, np.array([7]), np.array([7]))
        self.assertTrue(np.isnan(own[0]))                                  # (not on its own piece)

    def test_strap_without_the_rule_sinks_with_it_stays_on_the_skin(self):
        m = self.body()
        weights = {'bdf': 1.0, 'fac': 1.0}
        target = decimate.count(m) // 24
        plain = decimate.decimate(m, target, weights, log=quiet, classes={'bdf': {'skin': 0.1, 'big': 0.05}})
        self.assertGreater(self.strap_inside(plain), 1.0)
        lying = decimate.decimate(m, target, weights, log=quiet,
                                  classes={'bdf': {'skin': 0.1, 'big': 0.05, 'lying': 1.0}})
        self.assertLessEqual(decimate.count(lying), target)
        self.assertLess(self.strap_inside(lying), 0.0)
        self.assertGreater(len(np.unique(self.prim(lying, 'MI_CH_xyz_strap')['tris'])),
                           len(np.unique(self.prim(plain, 'MI_CH_xyz_strap')['tris'])))

    def test_reach_bounds_a_piece_past_its_floor(self):
        """A large piece away from anything: its floor keeps a few of its vertices; with 'reach' it keeps what stays
        within that many mm of its shape, the other part giving up the rest."""
        ps, ts, ns = icosphere(levels=4, radius=60.0)
        pf, tf, nf = icosphere(levels=4, radius=50.0)
        pos = np.concatenate([ps, pf + [0.0, 500.0, 0.0]])
        nrm = np.concatenate([ns, nf])
        m = model_of(pos, [('bdf', 'MI_CH_xyz_cloth', ts), ('fac', 'MI_CH_xyz_face', tf + len(ps))], nrm=nrm)
        target = decimate.count(m) // 8
        weights = {'bdf': 1.0, 'fac': 0.1}
        a = decimate.decimate(m, target, weights, log=quiet, classes={'bdf': {'big': 0.02, 'lying': 1.0}})
        b = decimate.decimate(m, target, weights, log=quiet, classes={'bdf': {'big': 0.02, 'lying': 1.0, 'reach': 1.0}})
        qa, qb = self.prim(a, 'MI_CH_xyz_cloth'), self.prim(b, 'MI_CH_xyz_cloth')
        self.assertLessEqual(decimate.count(b), target)
        self.assertGreater(len(np.unique(qb['tris'])), len(np.unique(qa['tris'])))
        self.assertLess(off_surface(ps[::37], qb['pos'], qb['tris']), off_surface(ps[::37], qa['pos'], qa['tris']))

    def test_skin_reach_alone_bounds_a_part_without_floors(self):
        """A face's class with only 'skin_reach': no floors, no post pass, but its skin stays within that many mm of
        its shape, the other part giving up the rest; its other materials (an eye) are not bounded."""
        ps, ts, ns = icosphere(levels=4, radius=60.0)
        pe, te, ne = icosphere(levels=3, radius=12.0)
        pb, tb, nb = icosphere(levels=4, radius=70.0)
        pos = np.concatenate([ps, pe + [0.0, 200.0, 0.0], pb + [0.0, 500.0, 0.0]])
        nrm = np.concatenate([ns, ne, nb])
        m = model_of(pos, [('fac', 'MI_CH_xyz_face_skin', ts), ('fac', 'MI_CH_xyz_eye', te + len(ps)),
                           ('bdf', 'MI_CH_xyz_cloth', tb + len(ps) + len(pe))], nrm=nrm)
        target = decimate.count(m) // 8
        weights = {'fac': 0.5, 'bdf': 1.0}
        a = decimate.decimate(m, target, weights, log=quiet)
        b = decimate.decimate(m, target, weights, log=quiet, classes={'fac': {'skin_reach': 0.5}})
        qa, qb = self.prim(a, 'MI_CH_xyz_face_skin'), self.prim(b, 'MI_CH_xyz_face_skin')
        self.assertLessEqual(decimate.count(b), target)
        self.assertLess(off_surface(ps[::37], qb['pos'], qb['tris']), off_surface(ps[::37], qa['pos'], qa['tris']))
        self.assertGreater(len(np.unique(qb['tris'])), len(np.unique(qa['tris'])))
        self.assertLess(len(np.unique(self.prim(b, 'MI_CH_xyz_eye')['tris'])),
                        len(np.unique(self.prim(a, 'MI_CH_xyz_eye')['tris'])))

    def test_bounds_give_way_when_nothing_else_fits(self):
        lines = []
        m = self.body()
        out = decimate.decimate(m, 150, {'bdf': 1.0, 'fac': 1.0}, log=lines.append,
                                classes={'bdf': {'lying': 1.0, 'reach': 0.01, 'skin_reach': 0.01}})
        self.assertLessEqual(decimate.count(out), 150)
        self.assertTrue(any('lying on others kept on them; going on without' in line for line in lines))

    def _under(self, new_y, source_y=-5.0, cloth_y=-3.0, most=None):
        """A skin triangle at new_y (it was at source_y) over a small strap at cloth_y (normals +y): _skin_under's
        inputs -> (the skin's y, the strap's y, what it returned)."""
        size = 200.0
        skin_old = [[-size, source_y, -size], [size, source_y, -size], [0.0, source_y, size]]
        skin_new = [[-size, new_y, -size], [size, new_y, -size], [0.0, new_y, size]]
        cloth = [[-20.0, cloth_y, -20.0], [20.0, cloth_y, -20.0], [0.0, cloth_y, 20.0]]
        pos = np.array(skin_old + cloth, np.float64)
        nrm = np.tile([0.0, 1.0, 0.0], (6, 1))
        tris = np.array([[0, 2, 1]]), np.array([[3, 5, 4]])
        pid = np.arange(6)
        prims = [dict(part='bdf', material='MI_CH_xyz_body_skin', tris=tris[0]),
                 dict(part='bdf', material='MI_CH_xyz_strap', tris=tris[1])]
        streams = dict(pos=np.array(skin_new + cloth, np.float64), nrm=nrm.copy())
        lines = []
        moved = decimate._skin_under(streams, prims, np.arange(6), pid, prims, pos, nrm, {'bdf': {'lying': 1.0}}, set(),
                                     lines.append)
        return streams['pos'][:3, 1], streams['pos'][3:, 1], moved

    def test_skin_is_taken_back_under_the_strap_on_it(self):
        skin, strap, moved = self._under(0.0)                        # (3 mm over the strap: was 2 under it)
        self.assertEqual(moved, 3)
        self.assertEqual(strap.tolist(), [-3.0, -3.0, -3.0])         # (the strap stays)
        self.assertLess(skin.max(), 0.0)
        self.assertLessEqual(skin.max(), decimate.UNDER_MOST)
        # under the strap at its middle by UNDER_CLEAR, as near as the corners' least move gets it
        self.assertGreaterEqual(-skin.mean(), 3.0)

    def test_skin_below_the_strap_stays(self):
        skin, _, moved = self._under(-6.0)                           # (3 under it already)
        self.assertEqual(moved, 0)
        self.assertEqual(skin.tolist(), [-6.0, -6.0, -6.0])

    def test_an_end_tucked_into_the_skin_stays_tucked(self):
        skin, _, moved = self._under(-5.0, source_y=-5.0, cloth_y=-7.0)      # (2 mm under the skin as it was)
        self.assertEqual(moved, 0)
        self.assertEqual(skin.tolist(), [-5.0, -5.0, -5.0])

    def test_the_move_has_a_limit(self):
        skin, _, _ = self._under(10.0, source_y=-5.0, cloth_y=-3.0)  # (13 mm over: out of LIE_NEAR's reach, left)
        self.assertEqual(skin.tolist(), [10.0, 10.0, 10.0])
        skin, _, _ = self._under(4.5, source_y=-5.0, cloth_y=-3.0)
        self.assertGreaterEqual(skin.min(), 4.5 - decimate.UNDER_MOST - 1e-9)

    def test_decimated_skin_is_under_the_strap(self):
        """The whole way: nothing of the strap under the new skin where it lay over the skin."""
        m = self.body()
        target = decimate.count(m) // 12
        out = decimate.decimate(m, target, {'bdf': 1.0, 'fac': 1.0}, log=quiet,
                                classes={'bdf': {'skin': 0.05, 'big': 0.05, 'lying': 1.0}})
        skin, strap = self.prim(out, 'MI_CH_xyz_body_skin'), self.prim(out, 'MI_CH_xyz_strap')
        c = skin['pos'][skin['tris']]
        n = decimate._outward(c, skin['nrm'][skin['tris']])
        gap = decimate.surface_gap(surface_samples(strap['pos'], strap['tris']), c, n, decimate.LIE_NEAR)
        gap = gap[~np.isnan(gap)]
        self.assertTrue(len(gap))
        self.assertGreater(gap.min(), 0.0)


def strand_cards(n=12, rows=30, cols=3, length=150.0, width=12.0, bend=60.0, z=0.0, x0=0.0, gutter=0.0, seed=1):
    """n hair cards side by side: strips `cols` vertices across (u: 0.1 wide, its own column of the atlas) and `rows`
    along (v: 0..1), each hanging down and bending forward along a circle (`bend`: its radius; 0: straight), lying
    over the plane z = `z` (its centre column `gutter` mm further out) -> (points, triangles, uvs)."""
    rng = np.random.default_rng(seed)
    pts, tris, uv = [], [], []
    for k in range(n):
        base = len(pts)
        for r in range(rows):
            s = length * r / (rows - 1)
            y, dz = (-s, 0.0) if not bend else (-bend * np.sin(s / bend), bend * (1 - np.cos(s / bend)))
            for c in range(cols):
                f = c / (cols - 1.0)
                pts.append((x0 + k * width * 1.2 + f * width, y,
                            z + dz + gutter * np.sin(np.pi * f) + rng.normal(0, 0.01)))
                uv.append((0.1 * (k % 8) + 0.1 * f, r / (rows - 1.0)))
        for r in range(rows - 1):
            for c in range(cols - 1):
                a = base + r * cols + c
                b, cc, d = a + 1, a + cols, a + cols + 1
                tris += [(a, b, d), (a, d, cc)]
    return np.array(pts), np.array(tris), np.array(uv)


@unittest.skipUnless(HAVE_CC, 'needs a C compiler')
class Strands(unittest.TestCase):
    """decimate(classes={'har': {'strands': mm}}): hair cards' strips are reduced as strands (rows by their bend, inner
    columns by their cross-section, the strips that show least left out), not collapsed; the floor keeps them within
    that many mm."""

    def model(self, **kw):
        """Bent cards (part har) and a body sheet with room to give (part bdf)."""
        pc, tc, uc = strand_cards(**kw)
        pb, tb = grid(14, 100.0, 400.0)
        ub = pb[:, :2] / 100.0
        return model_of(np.concatenate([pc, pb]), [('har', 'MI_CH_xyz_har_1p', tc),
                                                   ('bdf', 'MI_CH_xyz_cloth', tb + len(pc))],
                        uv=np.concatenate([uc, ub])), len(pc)

    def test_strips_are_the_uv_grids(self):
        pts, tris, uv = strand_cards(n=3, rows=5, cols=3)
        # a fourth piece that is no grid: a fan
        fan = np.array([(0.0, 0, 50), (10, 0, 50), (10, 10, 50), (0, 10, 50), (5, 5, 52)])
        ftris = np.array([(4, 0, 1), (4, 1, 2), (4, 2, 3), (4, 3, 0)]) + len(pts)
        m = model_of(np.concatenate([pts, fan]), [('har', 'MI_CH_xyz_har_1p', np.concatenate([tris, ftris]))],
                     uv=np.concatenate([uv, fan[:, :2] / 10.0]))
        found, share = decimate.strips(m['prims'][0])
        self.assertEqual(len(found), 3)
        self.assertAlmostEqual(share, 45 / 50.0)
        g, rv, cu, turn = found[0]
        self.assertEqual(g.shape, (5, 3))
        self.assertEqual(g[0].tolist(), [0, 1, 2])                          # (rows by v, columns by u)
        self.assertEqual(turn, 1)
        flipped = model_of(pts, [('har', 'MI_CH_xyz_har_1p', tris[:, ::-1])], uv=uv)
        self.assertEqual(decimate.strips(flipped['prims'][0])[0][0][3], -1)

    def test_a_tube_is_no_strip(self):
        # four columns round a square tube, the first and the last at one place (a seam)
        ring = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 0.0)]
        pts = np.array([(x, -10.0 * r, z) for r in range(4) for x, z in ring])
        uv = np.array([(c / 3.0, r / 3.0) for r in range(4) for c in range(4)])
        tris = []
        for r in range(3):
            for c in range(3):
                a = r * 4 + c
                tris += [(a, a + 1, a + 5), (a, a + 5, a + 4)]
        p = model_of(pts, [('har', 'MI_CH_xyz_har_1p', tris)], uv=uv)['prims'][0]
        self.assertEqual(len(decimate.strips(p)[0]), 1)
        pid = np.unique(np.round(pts, 3), axis=0, return_inverse=True)[1].reshape(-1)
        self.assertEqual(decimate.strips(p, pid)[0], [])

    def test_splits_keep_the_bend(self):
        pts, tris, uv = strand_cards(n=1, rows=40, bend=60.0)
        P = pts.reshape(40, 3, 3)
        err = decimate._splits(P, uv[::3, 1], 0.0)
        self.assertTrue(np.isinf(err[0]) and np.isinf(err[-1]))
        for tol in (0.5, 2.0, 5.0):
            keep = np.nonzero(err > tol)[0]
            # every row lies within tol of the line between the kept rows round it
            for a, b in zip(keep[:-1], keep[1:]):
                for r in range(a + 1, b):
                    t = (r - a) / float(b - a)
                    self.assertLessEqual(np.linalg.norm(P[r] - (1 - t) * P[a] - t * P[b], axis=1).max(), tol + 1e-6)
        self.assertGreater((err > 0.5).sum(), (err > 5.0).sum())
        straight = decimate._splits(strand_cards(n=1, rows=40, bend=0.0)[0].reshape(40, 3, 3), uv[::3, 1], 0.0)
        self.assertEqual((straight > 0.1).sum(), 2)                        # (a straight strip: its two ends)
        # the length share: a straight strip keeps a row at least every 1 / share of the tolerance
        long = decimate._splits(strand_cards(n=1, rows=40, bend=0.0)[0].reshape(40, 3, 3), uv[::3, 1], 0.04)
        keep = np.nonzero(long > 2.0)[0]
        self.assertLessEqual(np.diff(keep).max() * 150.0 / 39, 2.0 / 0.04 + 1e-6)

    def test_strands_keep_their_bend_ends_and_texture_span(self):
        m, nc = self.model(gutter=1.0)
        lines = []
        out = decimate.decimate(m, 420, {'har': 1.0, 'bdf': 1.0}, log=lines.append, classes={'har': {'strands': 3.0}})
        self.assertLessEqual(decimate.count(out), 420)
        q = [p for p in out['prims'] if p['part'] == 'har'][0]
        src = out['source']
        cards = src[q['tris']] // 90                                        # (each card's 90 vertices)
        self.assertTrue((cards == cards[:, :1]).all())                      # no triangle joins two cards
        tol = float([x for x in lines if 'strands:' in x][0].split('within ')[1].split(' mm')[0])
        self.assertLessEqual(tol, 3.0 + 1e-9)
        P = m['prims'][0]['pos'][:nc].reshape(12, 30, 3, 3)
        kept = np.zeros(len(m['prims'][0]['pos']), bool)
        kept[src[np.unique(q['tris'])]] = True
        kept = kept[:nc].reshape(12, 30, 3)
        for k in range(12):
            if not kept[k].any():
                continue
            rows = np.nonzero(kept[k].any(1))[0]
            cols = np.nonzero(kept[k].any(0))[0]
            self.assertEqual((rows[0], rows[-1], cols[0], cols[-1]), (0, 29, 0, 2))     # its ends, its UV span
            self.assertTrue(kept[k][np.ix_(rows, cols)].all())               # a grid
            for a, b in zip(rows[:-1], rows[1:]):                            # the bend within the tolerance
                for r in range(a + 1, b):
                    t = (r - a) / float(b - a)
                    edge = (1 - t) * P[k, a][cols] + t * P[k, b][cols]
                    self.assertLessEqual(np.linalg.norm(P[k, r][cols] - edge, axis=1).max(), tol + 0.05)
        # turning as before: from the row's direction to the column's in (column, row), as strand_cards makes them
        t = src[q['tris']] % 90
        r, c = t // 3, t % 3
        turn = (c[:, 1] - c[:, 0]) * (r[:, 2] - r[:, 0]) - (r[:, 1] - r[:, 0]) * (c[:, 2] - c[:, 0])
        self.assertTrue((turn > 0).all())
        self.assertTrue(any('har strands 1080 ->' in x for x in lines))

    def test_strands_give_way_as_their_quota_falls(self):
        m, _ = self.model()
        counts = []
        for target in (700, 450, 300):
            out = decimate.decimate(m, target, {'har': 1.0, 'bdf': 1.0}, log=quiet, classes={'har': {'strands': 0.5}})
            self.assertLessEqual(decimate.count(out), target)
            counts.append(len(np.unique([p for p in out['prims'] if p['part'] == 'har'][0]['tris'])))
        self.assertGreater(counts[0], counts[1])
        self.assertGreater(counts[1], counts[2])

    def test_without_the_class_the_cards_collapse_as_before(self):
        m, _ = self.model()
        plain = decimate.decimate(m, 420, {'har': 1.0, 'bdf': 1.0}, log=quiet)
        other = decimate.decimate(m, 420, {'har': 1.0, 'bdf': 1.0}, log=quiet, classes={'bdf': {'skin': 0.4}})
        self.assertEqual(plain['source'].tolist(), other['source'].tolist())

    def test_hidden_strips_go_first(self):
        """An outer layer of cards over an inner one (narrower, 2 mm under it), both over an opaque sheet: at a target
        below what the rows can give, the inner cards are left out, the outer ones stay."""
        po, to, uo = strand_cards(n=8, rows=10, bend=0.0, z=6.0, length=100.0, width=16.0)
        pi, ti, ui = strand_cards(n=8, rows=10, bend=0.0, z=4.0, length=100.0, width=8.0, x0=4.0)
        pi[:, 0] += np.repeat(np.arange(8) * (16.0 * 1.2 - 8.0 * 1.2), 30)       # (each under its outer card)
        pb, tb = grid(6, 200.0, -20.0)
        pb = pb - [0.0, 150.0, 0.0]
        pos = np.concatenate([po, pi, pb])
        m = model_of(pos, [('har', 'MI_CH_xyz_har_1p', np.concatenate([to, ti + len(po)])),
                           ('bdf', 'MI_CH_xyz_body_skin', tb + len(po) + len(pi))],
                     uv=np.concatenate([uo, ui, pb[:, :2] / 100.0]))
        lines = []
        out = decimate.decimate(m, 36 + 34, {'har': 1.0, 'bdf': 0.0}, log=lines.append,
                                classes={'har': {'strands': 0.0}})     # (the sheet's 36, 4 for each outer card)
        self.assertLessEqual(decimate.count(out), 70)
        src = out['source']
        q = [p for p in out['prims'] if p['part'] == 'har'][0]
        used = src[np.unique(q['tris'])]
        self.assertEqual(len(np.unique(used[used < len(po)] // 30)), 8)                  # (every outer card)
        self.assertEqual(((used >= len(po)) & (used < len(po) + len(pi))).sum(), 0)    # (no inner card)

    def test_left_out_uncovers_what_was_under_it(self):
        """Peeling: a strip judged half hidden by one that goes before it is judged again without it."""
        corners = np.array([[[0.0, 0, 0], [10, 0, 0], [0, 10, 0]], [[0.0, 0, 1], [10, 0, 1], [0, 10, 1]]])
        strip, layer, opaque = np.array([0, 1]), np.array([0, 1]), np.zeros(2, bool)

        def seen(points, layer, opaque, strip, n):          # (the second shows half while the first is there)
            return np.array([1.0, 0.5 if (strip == 0).any() else 1.0])
        length = np.array([10.0, 100.0])
        d = decimate.STRAND_DROP
        with mock.patch.object(decimate, 'shown', seen):
            with mock.patch.object(decimate, 'STRAND_PEEL', ()):
                once = decimate.drop_errors(corners, layer, opaque, strip, length)
            with mock.patch.object(decimate, 'STRAND_PEEL', (d * 10.0 + 1.0,)):     # (a round the first goes in)
                peeled = decimate.drop_errors(corners, layer, opaque, strip, length)
        self.assertEqual(once.tolist(), [d * 10.0, d * 50.0])
        self.assertEqual(peeled.tolist(), [d * 10.0, d * 100.0])

    def test_what_shows(self):
        """shown(): a card alone shows whole; one under another card by STRAND_COVER less from that side; one under
        an opaque sheet from its open side only."""
        a, ta, _ = strand_cards(n=1, rows=6, bend=0.0, z=4.0, length=50.0, width=20.0)
        b, tb, _ = strand_cards(n=1, rows=6, bend=0.0, z=0.0, length=50.0, width=20.0)
        corners = np.concatenate([a[ta], b[tb]])
        strip = np.repeat([0, 1], len(ta))
        points, owner = decimate._samples(corners)
        alone = decimate.shown(points[owner < len(ta)], strip[owner][owner < len(ta)],
                               np.zeros((owner < len(ta)).sum(), bool), strip[owner][owner < len(ta)], 2)
        self.assertAlmostEqual(alone[0], 1.0)
        both = decimate.shown(points, strip[owner], np.zeros(len(points), bool), strip[owner], 2)
        self.assertAlmostEqual(both[0], 1.0)
        self.assertAlmostEqual(both[1], 1.0, 1)             # (seen from behind, it is the front one)
        opaque = decimate.shown(points, strip[owner], strip[owner] == 0, np.where(strip[owner] == 1, 1, -1), 2)
        self.assertAlmostEqual(opaque[1], 1.0, 1)           # (from behind: nothing over it)
        # closed in: a sheet in front and one behind
        c, tc = grid(8, 60.0, -20.0)
        front, back = c + [0.0, -55.0, 8.0], c + [0.0, -55.0, -4.0]
        walls = np.concatenate([front[tc], back[tc]])
        corners = np.concatenate([b[tb], walls])
        strip = np.concatenate([np.zeros(len(tb), int), np.full(len(walls), -1)])
        points, owner = decimate._samples(corners)
        boxed = decimate.shown(points, np.where(strip[owner] >= 0, 0, 1), strip[owner] < 0, strip[owner], 1)
        self.assertLess(boxed[0], 0.8)                     # (edge-on from the sides and above only)

    def test_tolerance_is_the_least_that_fits(self):
        m, nc = self.model()
        p = m['prims'][0]
        found, _ = decimate.strips(p)
        s = decimate._Strands(found, np.arange(len(p['pos'])), p['pos'], np.full(len(found), np.inf))
        for most in (1080, 600, 200, 48):
            tol = s.tolerance(most)
            self.assertLessEqual(s.count(tol), most)
            lower = s.levels[s.levels < tol]
            if len(lower):
                self.assertGreater(s.count(lower[-1]), most)
            t = s.triangles(tol)
            self.assertEqual(len(np.unique(t)), s.count(tol))



def wire(rings=49, sides=6, radius=1.5, sag=120.0, width=240.0, x0=0.0, order=None):
    """A wire hanging in a loop (a necklace): `rings` rings of `sides` sides `radius` mm round a centre line that sags
    `sag` mm over `width` mm (a parabola in x, y), each ring's first vertex again at its end (u 1: a seam) ->
    (points, triangles facing out, uvs); order: the vertices' numbers shuffled by this permutation."""
    cols = sides + 1
    x = np.linspace(-width / 2, width / 2, rings)
    centre = np.stack([x + x0, sag * (2 * x / width) ** 2, np.zeros(rings)], 1)
    ahead = np.gradient(centre, axis=0)
    ahead /= np.linalg.norm(ahead, axis=1, keepdims=True)
    side = np.cross(ahead, [0.0, 0.0, 1.0])
    up = np.cross(side, ahead)
    a = 2 * np.pi * np.arange(cols) / sides
    pts = centre[:, None] + radius * (np.cos(a)[None, :, None] * side[:, None] + np.sin(a)[None, :, None] * up[:, None])
    uv = np.stack(np.meshgrid(np.arange(cols) / float(sides), np.arange(rings) / (rings - 1.0)), 2)
    tris = []
    for r in range(rings - 1):
        for c in range(sides):
            p, q = r * cols + c, r * cols + c + 1
            tris += [(p, q, p + cols), (q, q + cols, p + cols)]
    pts, uv, tris = pts.reshape(-1, 3), uv.reshape(-1, 2), np.array(tris)
    if order is not None:
        back = np.argsort(order)
        pts, uv, tris = pts[order], uv[order], back[tris]
    return pts, tris, uv


@unittest.skipUnless(HAVE_CC, 'needs a C compiler')
class Wires(unittest.TestCase):
    """decimate(classes={'bdf': {'tubes': mm}}): a part's thin tubes are reduced as whole rings kept where they bend
    (every other side of six), not collapsed across their rings into flat ribbons."""

    def model(self):
        """A wire (part bdf, 49 rings of 6 sides) and a body sheet with room to give."""
        pw, tw, uw = wire()
        pb, tb = grid(14, 100.0, 400.0)
        return model_of(np.concatenate([pw, pb]), [('bdf', 'MI_CH_xyz_chest', tw),
                                                   ('bdf', 'MI_CH_xyz_cloth', tb + len(pw))],
                        uv=np.concatenate([uw, pb[:, :2] / 100.0])), len(pw)

    def test_wires_are_the_grids_of_rings(self):
        parts = [wire(), wire(radius=8.0, x0=400.0), wire(rings=5, width=20.0, sag=2.0, x0=800.0)]
        pf, tf = grid(5, 40.0, 1200.0)                                       # (an open sheet: no rings)
        parts.append((pf, tf, pf[:, :2] / 40.0))
        pts, tris, uv, base = [], [], [], 0
        for p, t, u in parts:
            pts.append(p), tris.append(t + base), uv.append(u)
            base += len(p)
        m = model_of(np.concatenate(pts), [('bdf', 'MI_CH_xyz_chest', np.concatenate(tris))], uv=np.concatenate(uv))
        _, pid = np.unique(np.round(m['prims'][0]['pos'] / decimate.WELD), axis=0, return_inverse=True)
        found = decimate.tubes(m['prims'][0], pid.reshape(-1), m['prims'][0]['pos'])
        self.assertEqual(len(found), 1)                                      # (too thick, too short, no rings)
        g, along, turn = found[0]
        self.assertEqual(g.shape, (49, 7))
        self.assertEqual(sorted(g.reshape(-1).tolist()), list(range(343)))
        self.assertTrue((pid[g[:, 0]] == pid[g[:, -1]]).all())               # (the seam)
        self.assertTrue((np.diff(along) > 0).all())
        self.assertGreater(along[-1], 240.0)
        # numbered in any order, the same rings
        order = np.random.default_rng(3).permutation(343)
        p, t, u = wire(order=order)
        m = model_of(p, [('bdf', 'MI_CH_xyz_chest', t)], uv=u)
        _, pid = np.unique(np.round(p / decimate.WELD), axis=0, return_inverse=True)
        (g2, _, _), = decimate.tubes(m['prims'][0], pid.reshape(-1), p)
        self.assertEqual({frozenset(x) for x in order[g2].tolist()}, {frozenset(x) for x in g.tolist()})

    def test_wires_keep_whole_rings(self):
        m, nw = self.model()
        lines = []
        out = decimate.decimate(m, 220, {'bdf': 1.0}, log=lines.append, classes={'bdf': {'tubes': 1.0}})
        self.assertLessEqual(decimate.count(out), 220)
        q = [p for p in out['prims'] if p['material'] == 'MI_CH_xyz_chest'][0]
        src = out['source'][q['tris']]
        self.assertTrue((src < nw).all())
        ring, col = src // 7, src % 7
        kept = np.unique(ring)
        self.assertEqual((kept[0], kept[-1]), (0, 48))                       # (its ends)
        self.assertLess(len(kept), 49)
        self.assertEqual(sorted(np.unique(col).tolist()), [0, 2, 4, 6])      # (every other side)
        for r in kept:                                                       # each kept ring whole
            self.assertEqual(sorted(np.unique(col[ring == r]).tolist()), [0, 2, 4, 6])
        step = np.searchsorted(kept, ring)                                   # no triangle across a ring
        self.assertTrue(((step.max(1) - step.min(1)) == 1).all())
        self.assertTrue(((col.max(1) - col.min(1)) == 2).all())
        tol = float([x for x in lines if 'wires:' in x][0].split('within ')[1].split(' mm')[0])
        self.assertLessEqual(tol, 1.0 + 1e-9)
        # the centre line within the tolerance of the kept rings' (the bottom of the loop kept closer)
        P = m['prims'][0]['pos'][:nw].reshape(49, 7, 3)[:, [0, 2, 4, 6]]
        for a, b in zip(kept[:-1], kept[1:]):
            for r in range(a + 1, b):
                t = (r - a) / float(b - a)
                self.assertLessEqual(np.linalg.norm(P[r] - ((1 - t) * P[a] + t * P[b]), axis=1).max(), tol + 0.05)

    def test_without_the_class_the_rings_collapse(self):
        m, nw = self.model()
        out = decimate.decimate(m, 220, {'bdf': 1.0}, log=quiet)
        q = [p for p in out['prims'] if p['material'] == 'MI_CH_xyz_chest'][0]
        src = out['source'][np.unique(q['tris'])]
        whole = [len(np.unique(src[src // 7 == r] % 7)) for r in np.unique(src // 7)]
        self.assertLess(min(whole), 4)                                       # (a ring cut across: a ribbon)


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
        env = {k: v for k, v in os.environ.items() if k not in ('CC', 'TTT2_HELPER_CC', 'TTT2_NATIVE_DECIMATE')}
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
