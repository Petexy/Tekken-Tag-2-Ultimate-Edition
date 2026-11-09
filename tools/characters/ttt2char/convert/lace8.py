"""A summon's sheet of many small pieces drawn as a picture of itself on a low grid (a definition's prefab model 'lace':
convert/prefabs8.py).

Bahamut's wings are two membranes under about a thousand torn feather pieces and their bones (28k vertices); in a
summon's share of the model (its 'vertices') the decimation merges the pieces into a few hard shards and the torn
outline, the gaps and the bones go. Instead each group of the sheet (the vertices under one root of the kept bones:
one wing) is drawn from above its own plane (its principal axes) into one texture, all its pieces as they lie in the
mesh's bind: per texel, at SUPERSAMPLE^2 points, the front-most piece's point in the material's own UV0 layout, from
which the material's bake (prefabs8.bake, at the model's 'source_size') gives the texel its colour, and the share of the
points any piece covers its alpha. The gaps between the pieces and their torn edges are the texture's holes then,
drawn alpha-tested (the template's cut: no sorting), and the pieces keep Tekken 8's own colours.

A grid of square cells carries each picture: the cells over covered texels, each node at the sheet's depth there
(the covered texels' mean within a cell of it) and skinned by their weights on the kept bones (likewise), mapped to
the picture straight down; the cell size the finest at which all nodes, a front face and a back face each (TTT2
lights a face seen from behind by its front's normal), fit the model's vertices. A group lying as the mirror image of
one already drawn (the other wing) uses that one's picture: its frame is that one's mirrored (the principal axes, each
turned to where its points reach furthest), so its texels fall in the same places.

The front is the side each group's points reach furthest out to along its plane's normal (the bones on the
membranes); the back face shows the same picture. Positions are the streams' (TTT2 model space, mm).

TTT2 lights a face by its own normal alone: the side of a wing turned from the stage's sun came out dark where Tekken
8's thin membranes show alike from both sides. TTT2's own wings (Devil Jin's, the angel, fairy and butterfly wings)
are the same doubled one-sided sheets, lit, hiding it by being dark or translucent; a model's 'kind' gives its
material another template than the classification's (Clive's 'glow_cut': an unlit one, the picture's colours as they
are from every side).

A model's 'dissolve' makes the pictures form and go as Tekken 8's summon does, not by its scale: each covered texel
gets a place in the order the summon forms (a share 0..1: noise of a few sizes mixed with its distance from the group's
root, the point nearest all groups' centre, ranked to even shares), its alpha 1 for the first and DISSOLVE_REF / 255
for the last, and the material the alpha test at DISSOLVE_REF (all covered texels pass); the runtime (title/roster.cpp,
a weapon's ramp bit RAMP_DISSOLVE) raises that reference over the summon's fade so that a share s of the texels shows.
No TTT2 model's alpha test uses DISSOLVE_REF (all 8702 NUDs of the game read: 10 .. 250, not it).

Written for this project from the files themselves (no third-party code).
"""
import numpy as np

SUPERSAMPLE = 4         # points per texel side drawn (coverage and colour their mean)
MARGIN = 2              # empty texels round each picture (the filtering's reach)
COVERED = 0.5           # a texel this much covered keeps its cell (the template's cut is near it)
FINEST_MM = 10.0        # the grid's cells no smaller
COARSEST_MM = 600.0     # ... nor larger
CELL_STEP = 0.97        # the cell sizes tried, each this share of the one before
SAME_MM = 1.0           # a group whose points lie within this of another's in their frames is its mirror image
SAME_SHARE = 0.01        # ... and whose count of points differs by at most this share
SOURCE_SIZE = 1024      # the material's bake the pictures sample, at most this size (a model's 'source_size')
DISSOLVE_REF = 107       # a dissolving lace material's alpha test reference (/ 255; the runtime's kDissolveRef)
DISSOLVE_NOISE = 0.6    # the noise's share of a texel's place in the order (the rest its distance from the root)
NOISE_TEXELS = (1, 4, 12)  # the noise's sizes (texels), summed with weights falling as they grow finer
DISSOLVE_SEED = 8       # (the noise is the same in every import)

_cards = {}             # material name -> Card


class Card:
    """A material's pictures: per texel of the texture (H, W) its SUPERSAMPLE^2 points' UV0 points `uv` (H, W, n, 2)
    and whether a piece covers each (`covered` (H, W, n)); kind: the template its material takes (None: its own
    classification's); order (H, W): each texel's place in a dissolve (None: no dissolve)."""

    def __init__(self, uv, covered, source_size=SOURCE_SIZE, kind=None, order=None):
        self.uv, self.covered, self.source_size = uv, covered, int(source_size)
        self.kind, self.order = kind, order

    def texture(self, rgb, alpha=None):
        """(rgb (H, W, 3), alpha (H, W)) of the pictures from the material's bake rgb (h, w, 3) and its alpha (h, w)
        (None: opaque) in its UV0 layout; uncovered texels take their covered neighbours' colour (the filtering)."""
        from . import uvmap8
        a = self.covered.astype(np.float32)
        if alpha is not None:
            a = a * uvmap8.sample(np.asarray(alpha, np.float32)[..., None], self.uv)[..., 0]
        col = uvmap8.sample(np.asarray(rgb, np.float32)[..., :3], self.uv)
        total = a.sum(-1)
        out = (col * a[..., None]).sum(2) / np.maximum(total, 1e-6)[..., None]
        share = (total / a.shape[-1]).astype(np.float32)
        if self.order is not None:      # (a dissolve: the covered texels' alpha their place, the rest below the cut)
            lo = DISSOLVE_REF / 255.0
            share = np.where(share >= COVERED, lo + (1.0 - lo) * (1.0 - self.order),
                             share * (lo / COVERED) * 0.9).astype(np.float32)
        return _filled(out, total > 0), share

    def resample(self, img, longest=128):
        """img (h, w, C) in the material's UV0 layout (its shine) laid out as the pictures, at most `longest` texels
        across (each texel its first point's)."""
        from . import uvmap8
        H, W = self.covered.shape[:2]
        k = max(1, int(np.ceil(max(H, W) / float(longest))))
        uv, have = self.uv[k // 2::k, k // 2::k, 0], self.covered[k // 2::k, k // 2::k, 0]
        x = np.asarray(img)
        out = uvmap8.sample(x.astype(np.float32), uv)
        out = _filled(out, have)
        return (np.clip(out, 0, 255) + 0.5).astype(x.dtype) if x.dtype == np.uint8 else out.astype(x.dtype)


def card(name):
    """Material `name`'s Card, or None (not drawn as lace)."""
    return _cards.get(name)


def _filled(img, have, steps=64):
    """img with its texels not `have` taken from a neighbour's, step by step, the rest the mean of those had."""
    img, have = img.copy(), have.copy()
    if not have.any():
        return img
    mean = img[have].mean(0)
    for _ in range(steps):
        if have.all():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            take = np.roll(have, (dy, dx), (0, 1)) & ~have
            if take.any():
                img[take] = np.roll(img, (dy, dx), (0, 1))[take]
                have = have | take
    img[~have] = mean
    return img


def _frame(p):
    """(centre, rows e1 e2 n) of points p (n, 3): their principal axes, each turned to where they reach furthest."""
    c = p.mean(0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    axes = []
    for a in vt:
        d = (p - c) @ a
        axes.append(a if d.max() >= -d.min() else -a)
    return c, np.array(axes)


def _raster(xy, z, tris, shape):
    """(triangle index (-1 none), barycentric weights (h, w, 3)) of the front-most (largest z) of tris over each
    point (h, w) = shape of the plane, xy in points (centres at + 0.5)."""
    H, W = shape
    zb = np.full(shape, -np.inf)
    tid = np.full(shape, -1, np.int64)
    bw = np.zeros(shape + (2,))
    A, B, C = xy[tris[:, 0]], xy[tris[:, 1]], xy[tris[:, 2]]
    den = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
    lo = np.floor(np.minimum(np.minimum(A, B), C) - 0.5).astype(np.int64) + 1
    hi = np.ceil(np.maximum(np.maximum(A, B), C) - 0.5).astype(np.int64) - 1
    lo, hi = np.maximum(lo, 0), np.minimum(hi, [W - 1, H - 1])
    for k in np.nonzero(np.abs(den) > 1e-12)[0]:
        (x0, y0), (x1, y1) = lo[k], hi[k]
        if x1 < x0 or y1 < y0:
            continue
        X = np.arange(x0, x1 + 1)[None, :] + 0.5
        Y = np.arange(y0, y1 + 1)[:, None] + 0.5
        a, b, c = A[k], B[k], C[k]
        l1 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / den[k]
        l2 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / den[k]
        l3 = 1.0 - l1 - l2
        inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        if not inside.any():
            continue
        t = tris[k]
        zz = l1 * z[t[0]] + l2 * z[t[1]] + l3 * z[t[2]]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        win = inside & (zz > sub)
        sub[win] = zz[win]
        tid[y0:y1 + 1, x0:x1 + 1][win] = k
        bw[y0:y1 + 1, x0:x1 + 1][win] = np.stack([l1, l2], -1)[win]
    return tid, np.concatenate([bw, 1.0 - bw.sum(-1, keepdims=True)], -1)


def _texels(x, S):
    """(h S, w S, ...) per point -> (h, w, S S, ...) per texel."""
    h, w = x.shape[0] // S, x.shape[1] // S
    x = x.reshape((h, S, w, S) + x.shape[2:])
    return np.moveaxis(x, 2, 1).reshape((h, w, S * S) + x.shape[4:])


def _integral(a):
    """The summed-area table of a (h, w, ...): (h + 1, w + 1, ...)."""
    out = np.zeros((a.shape[0] + 1, a.shape[1] + 1) + a.shape[2:])
    out[1:, 1:] = np.cumsum(np.cumsum(a, 0), 1)
    return out


def _box(table, y0, x0, y1, x1):
    """Sums of the table's array over rows y0..y1 - 1 and columns x0..x1 - 1 (index arrays, clipped)."""
    h, w = table.shape[0] - 1, table.shape[1] - 1
    y0, y1 = np.clip(y0, 0, h), np.clip(y1, 0, h)
    x0, x1 = np.clip(x0, 0, w), np.clip(x1, 0, w)
    return table[y1, x1] - table[y0, x1] - table[y1, x0] + table[y0, x0]


class _Group:
    """One group's frame, its picture's points and its texels' coverage, depth and skin weights."""

    def __init__(self, pos, tris, dense):
        self.tris = tris
        used = np.unique(tris)
        self.c, self.E = _frame(pos[used])
        self.q = (pos - self.c) @ self.E.T                  # (u, v, depth) of every vertex
        self.lo, self.hi = self.q[used, :2].min(0), self.q[used, :2].max(0)
        self.used, self.dense = used, dense

    def same(self, other):
        """Whether this group lies in its frame as `other` in its own (a mirror image, or a copy): about as many points,
        each coordinate's percentiles within SAME_MM (a few stray points apart: the wings differ by two)."""
        if abs(len(self.used) - len(other.used)) > SAME_SHARE * len(other.used):
            return False
        at = np.linspace(0.0, 1.0, 101)
        a, b = self.q[self.used], other.q[other.used]
        return bool(np.abs(np.quantile(a, at, axis=0) - np.quantile(b, at, axis=0)).max() <= SAME_MM)

    def draw(self, t, S):
        """Draws the group at texel size t (mm), S points per texel side: its texels' size (h, w) and per point the
        triangle and barycentric weights; per texel coverage, depth and skin weights."""
        h, w = (np.ceil((self.hi - self.lo) / t).astype(np.int64) + 2 * MARGIN)[::-1]
        self.t, self.shape = t, (int(h), int(w))
        xy = ((self.q[:, :2] - self.lo) / t + MARGIN) * S
        self.tid, self.bw = _raster(xy, self.q[:, 2], self.tris, (int(h) * S, int(w) * S))
        cov = _texels(self.tid >= 0, S).astype(np.float64)                 # (h, w, S S)
        tri = self.tris[np.maximum(self.tid, 0)]                             # (h S, w S, 3)
        depth = (self.q[tri, 2] * self.bw).sum(-1)
        n = cov.sum(-1)
        self.cover = n / (S * S)
        self.depth = (_texels(depth, S) * cov).sum(-1) / np.maximum(n, 1)
        K = self.dense.shape[1]
        wsum = np.zeros((int(h), int(w), K))
        for s in range(S * S):                                               # (point by point: the memory)
            ts = _texels(tri, S)[:, :, s]
            bs = _texels(self.bw, S)[:, :, s]
            wsum += (self.dense[ts] * bs[..., None]).sum(2) * cov[:, :, s, None]
        self.weights = wsum / np.maximum(n, 1)[..., None]

    def grid(self, cell):
        """(nodes (i, j) (m, 2), cells (k, 2) by their lower node) of the grid of `cell` mm over the covered texels."""
        if not hasattr(self, '_kept'):
            self._kept = _integral((self.cover >= COVERED).astype(np.float64))
        nu, nv = (np.ceil((self.hi - self.lo) / cell).astype(np.int64) + 1)
        I, J = np.meshgrid(np.arange(nu), np.arange(nv), indexing='ij')
        I, J = I.ravel(), J.ravel()
        x0 = np.floor(I * cell / self.t).astype(np.int64) + MARGIN
        x1 = np.ceil((I + 1) * cell / self.t).astype(np.int64) + MARGIN
        y0 = np.floor(J * cell / self.t).astype(np.int64) + MARGIN
        y1 = np.ceil((J + 1) * cell / self.t).astype(np.int64) + MARGIN
        on = _box(self._kept, y0, x0, y1, x1) > 0
        cells = np.stack([I[on], J[on]], 1)
        corners = np.concatenate([cells + d for d in ((0, 0), (1, 0), (1, 1), (0, 1))], 0)
        return np.unique(corners, axis=0), cells


def _noise(shape, rng):
    """Noise (shape) of NOISE_TEXELS' sizes, each a grid of random values blended smoothly over the texels (no square
    cells on screen), the finer weighing less."""
    out = np.zeros(shape)
    for i, size in enumerate(NOISE_TEXELS):
        h, w = -(-shape[0] // size) + 1, -(-shape[1] // size) + 1
        cells = rng.random((h, w))
        y, x = (np.arange(shape[0]) + 0.5) / size, (np.arange(shape[1]) + 0.5) / size
        y0, x0 = np.minimum(y.astype(int), h - 2), np.minimum(x.astype(int), w - 2)
        fy, fx = y - y0, x - x0
        fy, fx = (fy * fy * (3 - 2 * fy))[:, None], (fx * fx * (3 - 2 * fx))[None, :]
        top = cells[y0][:, x0] * (1 - fx) + cells[y0][:, x0 + 1] * fx
        bottom = cells[y0 + 1][:, x0] * (1 - fx) + cells[y0 + 1][:, x0 + 1] * fx
        out += (top * (1 - fy) + bottom * fy) * (i + 1)
    return out


def _ranked(x):
    """x's values as their ranks, 0..1 (even shares)."""
    out = np.empty(len(x))
    out[np.argsort(x, kind='stable')] = np.linspace(0.0, 1.0, len(x)) if len(x) > 1 else 0.0
    return out


def dissolve_order(g, centre, rng):
    """Group g's (drawn) texels' places in the order the summon forms, (h, w) 0..1 over its covered texels (1 the
    rest): DISSOLVE_NOISE of noise, the rest its distance from its root (its point nearest `centre`), ranked."""
    h, w = g.shape
    root = g.q[g.used][np.argmin(np.linalg.norm((g.c + g.q[g.used] @ g.E) - centre, axis=1)), :2]
    u = (np.arange(w) + 0.5 - MARGIN) * g.t + g.lo[0]
    v = (np.arange(h) + 0.5 - MARGIN) * g.t + g.lo[1]
    far = np.hypot(u[None, :] - root[0], v[:, None] - root[1])
    on = g.cover >= COVERED
    out = np.ones((h, w))
    if on.any():
        mix = DISSOLVE_NOISE * _ranked(_noise((h, w), rng)[on]) + (1.0 - DISSOLVE_NOISE) * _ranked(far[on])
        out[on] = _ranked(mix)
    return out


def cards(prims, up, goal, spec, log=print):
    """The prims of one model (prefabs8.model's: one material, streams shared) drawn as lace: [prim] of its grids,
    within goal vertices, and the material's Card kept for its bake. up: the kept bones' parents (-1 a root).
    spec: the model's 'lace' {'texture': (width, height), 'source_size': the bake's, 'kind': its material's
    template, 'dissolve': True to form and go by the alpha test (the module notes)}."""
    names = {q['material'] for q in prims}
    if len(names) != 1:
        raise ValueError('lace: one material per model, not %s' % sorted(names))
    name = names.pop()
    first = prims[0]
    pos = np.asarray(first['pos'], np.float64)
    tris = np.concatenate([np.asarray(q['tris'], np.int64) for q in prims], 0)
    joints, weights = np.asarray(first['joints'], np.int64), np.asarray(first['weights'], np.float64)
    K = len(up)
    dense = np.zeros((len(pos), K), np.float32)
    np.add.at(dense, (np.repeat(np.arange(len(pos)), joints.shape[1]), joints.ravel()), weights.ravel())
    root = []
    for k in range(K):
        while up[k] >= 0:
            k = up[k]
        root.append(k)
    group = np.asarray(root)[dense.argmax(1)][tris[:, 0]]
    # TTT2's front: the winding the source's triangles have about their vertices' normals
    nrm = np.asarray(first['nrm'], np.float64)
    e = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    turn = 1.0 if (e * nrm[tris].sum(1)).sum() >= 0 else -1.0
    groups = [_Group(pos, tris[group == g], dense) for g in np.unique(group)]
    pictures, of = [], []
    for g in groups:
        twin = next((p for p in pictures if g.same(groups[p])), None)
        of.append(len(pictures) if twin is None else pictures.index(twin))
        if twin is None:
            pictures.append(groups.index(g))
    from . import model
    W, H = (min(int(x), model.MAX_TEX) for x in spec.get('texture', (512, 256)))
    # (no larger than the converted textures' cap: a larger one is resized there with its alpha, the colours in its
    # holes lost to black, and its mips darkened by them)
    S = SUPERSAMPLE
    spans = [groups[p].hi - groups[p].lo for p in pictures]
    t = max(sum(s[0] for s in spans) / max(W - 2 * MARGIN * len(pictures) - len(pictures), 1),
            max(s[1] for s in spans) / max(H - 2 * MARGIN - 1, 1))
    for g in groups:
        g.draw(t, S)
    x0s, x = [], 0
    for p in pictures:
        x0s.append(x)
        x += groups[p].shape[1]
    uv = np.zeros((H, W, S * S, 2), np.float32)
    covered = np.zeros((H, W, S * S), bool)
    order = np.ones((H, W)) if spec.get('dissolve') else None
    rng = np.random.default_rng(DISSOLVE_SEED)
    centre = np.mean([g.c for g in groups], 0)      # (between the wings: their roots nearest it)
    src_uv = np.asarray(first['uv'], np.float64)
    for p, x0 in zip(pictures, x0s):
        g = groups[p]
        h, w = g.shape
        tri = g.tris[np.maximum(g.tid, 0)]
        at = (src_uv[tri] * g.bw[..., None]).sum(2)
        uv[:h, x0:x0 + w] = _texels(at, S)
        covered[:h, x0:x0 + w] = _texels(g.tid >= 0, S)
        if order is not None:
            order[:h, x0:x0 + w] = dissolve_order(g, centre, rng)
    _cards[name] = Card(uv, covered, spec.get('source_size', SOURCE_SIZE), spec.get('kind'), order)
    # the finest cells whose nodes (front and back) fit
    cell, best = COARSEST_MM, None
    while cell >= FINEST_MM:
        made = [g.grid(cell) for g in groups]
        if 2 * sum(len(n) for n, _ in made) > goal:
            break
        best = (cell, made)
        cell *= CELL_STEP
    if best is None:
        raise ValueError('lace %s: %d vertices hold no grid of %.0f mm cells' % (name, goal, COARSEST_MM))
    cell, made = best
    width = joints.shape[1]
    P_, N_, T_, U_, J_, Wt_, tris_out = [], [], [], [], [], [], []
    base = 0
    for g, (nodes, cells), k in zip(groups, made, of):
        u = np.minimum(nodes[:, 0] * cell, g.hi[0] - g.lo[0])
        v = np.minimum(nodes[:, 1] * cell, g.hi[1] - g.lo[1])
        # depth and weights: the covered texels' mean within a cell of the node (the cells round it)
        cx, cy = u / t + MARGIN, v / t + MARGIN
        r = cell / t
        y0, y1 = np.floor(cy - r).astype(np.int64), np.ceil(cy + r).astype(np.int64)
        x0, x1 = np.floor(cx - r).astype(np.int64), np.ceil(cx + r).astype(np.int64)
        cov = g.cover
        n = np.maximum(_box(_integral(cov), y0, x0, y1, x1), 1e-9)
        depth = _box(_integral(cov * g.depth), y0, x0, y1, x1) / n
        wts = _box(_integral(cov[..., None] * g.weights), y0, x0, y1, x1) / n[:, None]
        pts = g.c + np.stack([u + g.lo[0], v + g.lo[1], depth], 1) @ g.E
        index = {tuple(a): i for i, a in enumerate(nodes.tolist())}
        corner = np.array([[index[(a + da, b + db)] for da, db in ((0, 0), (1, 0), (1, 1), (0, 1))]
                           for a, b in cells.tolist()], np.int64).reshape(-1, 4)
        quads = np.concatenate([corner[:, [0, 1, 2]], corner[:, [0, 2, 3]]], 0)
        # the frame's handedness: (e1, e2) wind about +n, or about -n for a mirrored one
        hand = 1.0 if np.cross(g.E[0], g.E[1]) @ g.E[2] > 0 else -1.0
        front = quads if hand * turn > 0 else quads[:, [0, 2, 1]]
        fn = np.cross(pts[front[:, 1]] - pts[front[:, 0]], pts[front[:, 2]] - pts[front[:, 0]]) * turn
        nn = np.zeros_like(pts)
        for c in range(3):
            np.add.at(nn, front[:, c], fn)
        nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
        nn[(nn @ g.E[2]) < 0] *= -1.0
        order = np.argsort(-wts, 1, kind='stable')[:, :width]
        top = np.take_along_axis(wts, order, 1)
        if order.shape[1] < width:                      # (fewer kept bones than the streams' influences)
            order = np.pad(order, ((0, 0), (0, width - order.shape[1])), mode='edge')
            top = np.pad(top, ((0, 0), (0, width - top.shape[1])))
        top /= np.maximum(top.sum(1, keepdims=True), 1e-12)
        at = np.stack([u / t + MARGIN + x0s[k], v / t + MARGIN], 1) / [W, H]
        m = len(nodes)
        for side, faces in ((1.0, front), (-1.0, front[:, [0, 2, 1]])):
            P_.append(pts)
            N_.append(nn * side)
            T_.append(np.concatenate([np.repeat(g.E[:1], m, 0), np.full((m, 1), side)], 1))
            U_.append(at)
            J_.append(order)
            Wt_.append(top)
            tris_out.append(faces + base)
            base += m
        log('  lace %s: group %d (%d triangles) %s, %.0f%% of its texels covered, %d cells, %d nodes' % (
            name, len(P_) // 2, len(g.tris), 'its own picture' if pictures[k] == groups.index(g) else
            'the picture of group %d (its mirror image)' % (pictures[k] + 1),
            100.0 * float((g.cover >= COVERED).mean()), len(cells), m))
    out = dict(pos=np.concatenate(P_).astype(first['pos'].dtype), nrm=np.concatenate(N_).astype(first['nrm'].dtype),
               tan=np.concatenate(T_).astype(first['tan'].dtype), uv=np.concatenate(U_).astype(first['uv'].dtype),
               joints=np.concatenate(J_).astype(first['joints'].dtype),
               weights=np.concatenate(Wt_).astype(first['weights'].dtype))
    log('  lace %s: %d pictures in a %dx%d texture (a texel %.1f mm), cells of %.0f mm, %d vertices (of %d)%s%s' % (
        name, len(pictures), W, H, t, cell, base, goal, ', template %s' % spec['kind'] if spec.get('kind') else '',
        ', dissolving (alpha test at %d)' % DISSOLVE_REF if order is not None else ''))
    return [dict(first, tris=np.concatenate(tris_out, 0), **out)]
