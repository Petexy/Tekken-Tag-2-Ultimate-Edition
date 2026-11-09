"""Surfaces under a costume's own plates (a Tekken 8 definition's TEKKEN8['covered'], off by default).

An armoured costume is modelled in layers: a leg's shell, and over it, a few mm off, its plates, straps and buckles. The
shell under a plate is never seen, and the costume's texture paints it black. Decimated, neither layer stays where it
was to the millimetre, so the black shell rises through the plate here and there: sharp black flecks on a boot, a shin,
a corset's lower edge (Clive's, the first armour imported), and every vertex spent on it is lost to what shows.

hidden() finds those triangles: seen from no direction by a depth test of sample points (cells CELL wide, each holding its
front sample's plane, so a sloped surface does not hide itself and a plate a millimetre above a shell does hide it).
mark() gives the decimation those hidden in the bind pose, and either with the limbs bent as well or painted black, to take
first, trim() takes the rest of them from its result, and mark's map of the texels that show lets paint() take the black
out of those that do not, for what the kept triangles hold of them. Pieces that move apart from what they cover (a mantle)
are named `moving`: they neither go nor hide anything.

Written for this project (no third-party code).
"""
import math

import numpy as np

STEP = 1.5              # mm: the triangles are sampled this often ..
CELL = 2.0              # .. and judged in cells this wide
ABOVE = 0.25            # mm: closer under the front surface's plane than this still shows
FACING = 0.05           # a surface is drawn towards directions it faces this much (the game does not draw its back)
FACED = 0.5             # a texel shows if its surface shows from a direction it faces this much (mark's map)
DARK = 0.035            # sRGB brightness: a map's texels under this are black ..
BLACK = 0.5             # .. and a triangle with this share of them, black
PAINT = 0.2             # sRGB brightness: texels under this that no eye sees are painted over (paint)
SINK = 8.0              # mm: how far under what hides them the free vertices the decimation left go (trim)
UNDER = 4.0             # mm: how far the other vertices nothing shows at bind go: a lining a mm under its cloth rises through it once
                        # both are decimated, each its own way (Clive's corset: a dark slash); seen in a bend, 4 mm do not show
SHOWN_SIZE = 1024       # a material's map of the texels shown has this many cells a side
FILL_STEPS = 512
_BARY = np.array([(i, j, 6 - i - j) for i in range(7) for j in range(7 - i)], np.float64) / 6.0


def _views():
    """The directions of the test (y up): all round at five heights, straight above and below."""
    out = [(0.0, 1.0, 0.0), (0.0, -1.0, 0.0)]
    for up, step in ((0, 30), (45, 45), (-45, 45), (20, 45), (-20, 45)):
        c, s = math.cos(math.radians(up)), math.sin(math.radians(up))
        for a in range(0, 360, step):
            out.append((math.sin(math.radians(a)) * c, s, math.cos(math.radians(a)) * c))
    return np.array(out)


def _samples(corners):
    """Points on the triangles (t, 3, 3), at most STEP apart -> (points, each one's triangle, its corners' weights)."""
    longest = np.linalg.norm(corners[:, [1, 2, 0]] - corners, axis=2).max(1)
    rows = np.clip(np.ceil(longest / STEP), 1, 96).astype(np.int64)
    points, owner, weights = [], [], []
    for n in np.unique(rows):
        which = np.nonzero(rows == n)[0]
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
        keep = i + j <= n
        w = np.stack([n - i[keep] - j[keep], i[keep], j[keep]], 1) / float(n)
        points.append(np.einsum('tcx,mc->tmx', corners[which], w).reshape(-1, 3))
        owner.append(np.repeat(which, len(w)))
        weights.append(np.tile(w.astype(np.float32), (len(which), 1)))
    return np.concatenate(points), np.concatenate(owner), np.concatenate(weights)


def _faces(corners):
    """The triangles' normals (t, 3) by their corners' order, not normalised."""
    return np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])


def _seen(corners, sides):
    """The depth test of the triangles (corners (t, 3, 3) in mm; sides (t,): +1 or -1, how their corners' order gives their outer
    side), hiding one another -> (each sample's triangle, its corners' weights, whether it shows from any of _views(), whether
    from one it faces by FACED at least: what shows only at a slant, past a strap's edge, is a shadow under the strap)."""
    face = _faces(corners) * sides[:, None]
    face /= np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-12)
    points, owner, weights = _samples(corners)
    seen, faced = np.zeros(len(points), bool), np.zeros(len(points), bool)
    for d in _views():
        up = np.array([0.0, 0.0, 1.0]) if abs(d[1]) > 0.9 else np.array([0.0, 1.0, 0.0])
        x = np.cross(up, d)
        x /= np.linalg.norm(x)
        y = np.cross(d, x)
        c = face @ d
        at = np.nonzero((c > FACING)[owner])[0]
        if not len(at):
            continue
        p, o = points[at], owner[at]
        u, v, z = p @ x, p @ y, p @ d
        cu, cv = np.floor(u / CELL).astype(np.int64), np.floor(v / CELL).astype(np.int64)
        cell = (cu - cu.min()) * int(cv.max() - cv.min() + 1) + (cv - cv.min())
        top = np.full(int(cell.max()) + 1, -np.inf, z.dtype)
        np.maximum.at(top, cell, z)
        front = np.zeros(len(top), np.int64)     # (each cell's front sample)
        i = np.nonzero(z == top[cell])[0]
        front[cell[i]] = i
        f = front[cell]
        n = face[o[f]]
        slope_u, slope_v = n @ x / (n @ d), n @ y / (n @ d)
        plane = z[f] - slope_u * (u - u[f]) - slope_v * (v - v[f])
        shows = at[z >= plane - ABOVE]
        seen[shows] = True
        faced[shows[c[owner[shows]] >= FACED]] = True
    return owner, weights, seen, faced


def hidden(corners, sides):
    """The triangles (as _seen) that show from none of _views() -> bool (t,)."""
    owner, _, seen, _ = _seen(corners, sides)
    shows = np.zeros(len(corners), bool)
    shows[owner[seen]] = True
    return ~shows


def paint(rgb, shown):
    """A material's colours (H, W, 3, linear) with the dark texels no eye sees (shown: mark's map of it) taken from the nearest
    texels not dark: what a kept triangle still holds of them (under a stud the decimation lost) stays no black spot."""
    h, w = rgb.shape[:2]
    gh, gw = shown.shape
    mask = shown[np.arange(h) * gh // h][:, np.arange(w) * gw // w]
    ok = np.power(np.clip(rgb, 0, 1), 1.0 / 2.2) @ np.array((0.3, 0.6, 0.1), rgb.dtype) >= PAINT
    fill = rgb.copy()
    ys, xs = np.nonzero(~ok)
    todo = ~ok & ~mask
    for _ in range(FILL_STEPS):
        if not len(ys):
            break
        total, n = np.zeros((len(ys), 3), rgb.dtype), np.zeros(len(ys), rgb.dtype)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            y, x = np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)
            near = ok[y, x]
            total[near] += fill[y[near], x[near]]
            n[near] += 1
        got = n > 0
        fill[ys[got], xs[got]] = total[got] / n[got, None]
        ok[ys[got], xs[got]] = True
        ys, xs = ys[~got], xs[~got]
    return np.where(todo[..., None], fill, rgb)


def dark_share(tris, uv, luma):
    """How much of each triangle (t, 3) the map luma (H, W) paints black (under DARK), by its UVs uv (n, 2) -> (t,)."""
    h, w = luma.shape
    at = np.einsum('sb,tbx->tsx', _BARY, uv[tris])
    x = (at[..., 0] % 1.0 * w).astype(np.int64)
    y = (at[..., 1] % 1.0 * h).astype(np.int64)
    return (luma[y, x] < DARK).mean(1)


def mark(k, spec, poses, luma, log=print):
    """Model dict k (model.load_tekken7_model's shape) with its vertices for the taking as 'free' (bool per vertex: only on
    triangles of its parts spec['parts'] that hidden() finds in the bind pose and either in each of `poses`
    (skeleton.bend_poses: what a limb hides only until it moves stays) or black in their map (luma(material) -> (H, W) sRGB
    brightness: what the costume's author left for no eye)), but for the materials spec['moving'] (spec: the definition's) ->
    (a new model dict, {material: its texels the bind pose shows (n, n) bool}: paint's). No triangle goes yet: cut out now,
    each stair of the cut's edge would stay through the decimation (a corner of an open boundary does not move), and a 80k
    body stops at 26k. decimate.decimate takes free vertices first and at no bound; trim() takes what is left of them."""
    from . import decimate
    moving = set(spec.get('moving', ()))
    prims = [p for p in k['prims'] if p['part'] in spec['parts'] and p['material'] not in moving]
    if not prims:
        return k, {}
    s0 = prims[0]
    tris = np.concatenate([p['tris'] for p in prims])
    pos, nrm = s0['pos'].astype(np.float64), s0['nrm'].astype(np.float64)
    sides = np.where(np.einsum('ij,ij->i', _faces(pos[tris]), nrm[tris].sum(1)) < 0, -1.0, 1.0)
    owner, weights, seen, faced = _seen(pos[tris], sides)
    shows = np.zeros(len(tris), bool)
    shows[owner[seen]] = True
    out = ~shows
    bent = out.copy()
    used = np.unique(tris)
    posed = pos.copy()
    moved = decimate.posed_points(pos[used], s0['joints'][used], s0['weights'][used], poses) if len(poses) else ()
    for m in moved:
        posed[used] = m
        bent &= hidden(posed[tris], sides)
    uv = np.asarray(s0['uv'], np.float64)
    uv = uv if uv.ndim == 2 else uv[:, 0]
    # (the texels shown: by the samples that showed)
    of = np.repeat(np.arange(len(prims)), [len(p['tris']) for p in prims])[owner[faced]]
    where = np.einsum('sb,sbx->sx', weights[faced].astype(np.float64), uv[tris[owner[faced]]]) % 1.0
    maps = {}
    for i, p in enumerate(prims):
        grid = maps.setdefault(p['material'], np.zeros((SHOWN_SIZE, SHOWN_SIZE), bool))
        grid[(where[of == i, 1] * SHOWN_SIZE).astype(np.int64), (where[of == i, 0] * SHOWN_SIZE).astype(np.int64)] = True
    for name, grid in maps.items():              # (samples a cell or so apart: a cell round them counts)
        grown = grid.copy()
        grown[1:] |= grid[:-1]
        grown[:-1] |= grid[1:]
        grown[:, 1:] |= grid[:, :-1]
        grown[:, :-1] |= grid[:, 1:]
        maps[name] = grown
    black = np.concatenate([dark_share(p['tris'], uv, luma(p['material'])) for p in prims]) > BLACK
    out &= bent | black
    free = np.zeros(len(pos), bool)
    free[np.unique(tris[out])] = True
    free[tris[~out].reshape(-1)] = False
    under = np.zeros(len(pos), bool)
    under[np.unique(tris[~shows])] = True
    under[tris[shows].reshape(-1)] = False
    for p in k['prims']:                         # (whatever else draws them keeps them)
        if not any(p is q for q in prims):
            free[p['tris'].reshape(-1)] = False
            under[p['tris'].reshape(-1)] = False
    log('  covered surfaces: %d of %d triangles of %s under plates (seen from no direction), %d vertices for the taking' % (
        int(out.sum()), len(out), ', '.join(sorted(spec['parts'])), int(free.sum())))
    return dict(k, free=free, under=under), maps


def trim(out, free, under=None):
    """A decimated model (decimate.decimate's: 'source' its vertices' numbers in the model it had) less the triangles all of
    whose corners are free there (mark's), the other free vertices SINK mm down their normals: a triangle from a plate's rim
    to one, long now, runs under the plate and does not rise through it. under (mark's): vertices the bind pose does not
    show, UNDER mm down theirs."""
    f = free[out['source']]
    s0 = out['prims'][0]
    pos = s0['pos'].copy()
    if under is not None:
        u = under[out['source']] & ~f
        pos[u] -= (s0['nrm'][u, :3] * UNDER).astype(pos.dtype)
    pos[f] -= (s0['nrm'][f, :3] * SINK).astype(pos.dtype)
    prims = []
    for p in out['prims']:
        t = p['tris'][~f[p['tris']].all(1)]
        if len(t):
            prims.append(dict(p, tris=t, pos=pos))
    out = dict(out, prims=prims)
    out.pop('free', None)
    out.pop('under', None)
    return out
