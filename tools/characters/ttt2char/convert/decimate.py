"""Fewer vertices for a model the game cannot skin whole: quadric edge collapses (decimate.c does them).

TTT2 skins at most model.VERTEX_BUDGET vertices of a fighter (counted per material primitive after welding, the
2P colour layers' copies included); Tekken 7 costumes land at 25-30k, a Tekken 8 one has a single level of detail
of ~78k (Reina: body 48.6k, face 11k, hair 18.4k). decimate() takes the engine-free model dict
(model.load_tekken7_model's shape: prims sharing one set of vertex streams, only their 'tris' differ) and returns
one of the same shape with at most `target` vertices by that count (Reina 77.8k -> 30k in about a second).

How (decimate.c):
* Vertices at one position (within WELD) are one point of the surface; each primitive's vertices at a point are
  its wedges there, those with equal normal, UV and skin weights one wedge (model.py welds them so too). The vertex
  count is the wedges' count: a vertex two primitives use counts in each, as model.py counts it.
* A collapse moves a point U onto a neighbour V: U's triangles take V's wedges, V keeps its position and attributes
  (normal, UV, tangent, skin weights: no blends). Its cost is U's quadric error at V (the triangles' planes, area
  weighted), the attribute error of U's wedges (each triangle's linear UV and normal fields, Garland and Heckbert
  1998) at V's position and attributes, the squared change of skin weights times U's area (SKIN_WEIGHT), and a
  little of the edge's length (REGULAR: evens out flat areas, where all else is 0); the cheapest goes first.
  Positions are in mean edge lengths, UVs in what their texture covers on the primitive (its surface over its UV
  area), so the terms compare. Area-weighted errors grow with the fourth power of a shape's size, so in
  millimetres fingers, ears and buckles would go first: each point's cost is divided by its own mean edge length
  (in mean edge lengths) to the RELATIVE power, at most MOST_RELATIVE times and never less than once, so a shape
  the mesh has finely made keeps it, and coarse large areas (legs, a jacket's front) keep their outlines.
* Feature edges: open boundaries (one triangle) and seams (the two triangles use different wedges at an end: UV or
  normal seams, and every border between primitives, since wedges are per primitive) get a plane along the edge
  across the surface in their ends' quadrics (FEATURE_WEIGHT), and their points only move along them, onto the
  next point of the same curve, every side's wedges together (each wedge of U must go to exactly one wedge of V):
  seams stay closed, borders between materials stay where they are, holes do not open. A point with other than two
  feature edges (a seam's end, where three meet), at a corner of its feature curve (sharper than CORNER_COS), on an
  edge of three or more triangles, at an exactly doubled triangle or where separate fans meet does not move.
* No collapse may make a non-manifold edge (the link condition) or, on a triangle it changes, turn the face normal
  by more than FLIP_COS allows, turn the face to the other side of its corners' normals, or give it two corners
  whose normals are further apart than NORMAL_COS (a hem's rounding joined across: a dark streak); triangles that
  lose a side to it go (no degenerate triangles are left).
* Hair, eyelashes and eyebrows are alpha-tested cards (strips two or three vertices wide, every vertex on their
  outline): they are decimated along their length like any surface, their outlines being open boundaries, and
  every card keeps its four corners (CORNER_COS), so no card shrinks to a sliver or disappears; their UVs count
  CARD_UV_WEIGHT times more (the texture is their shape). Cards: primitives whose material is named like hair or
  whose vertices are mostly on boundaries (CARD_BOUNDARY). Locking their outlines instead would leave hair (90% of
  its vertices are outline) almost as it is; how much a part gives up is part_weights' business.
* part_weights {part tag: weight} (a part not named: 1): each part gives up a share of its vertices proportional
  to its weight ({'bdf': 1.0, 'fac': 0.3, 'har': 0.7}: the face loses 0.3 times the share the body loses, so its
  eyes, lips and nose keep their shapes); the errors only choose which of a part's vertices go. A point on a border
  between parts stops moving when either part has reached its quota; a part that cannot reach its quota (all
  that is left is locked) keeps what it has and the others give up the rest in a further pass. 0 leaves a part as
  it is. part_weights None: no quotas, the errors alone share out the reduction.
* Only when every part is stuck above the target do the corners go too (a further pass without the corner locks,
  flips up to 90 degrees); a model that still does not fit is returned as it got, with a warning.

vertex_target() picks the target from model.VERTEX_BUDGET: the 2P colour layers (colours.py; model.py adds one per
cloth primitive whose colours change between players, a copy of all its vertices) need room on top.

Written for this project (no third-party code).
"""
import ctypes
import math
import os
import re
import time

import numpy as np

from .. import native
from . import model as model_mod

WELD = 0.01                     # mm: vertices this close are one point of the surface (model.py welds at 0.001)
FEATURE_WEIGHT = 10.0           # a boundary or seam edge's plane against the triangles' (per squared edge length)
FLIP_COS = 0.2                  # a collapse may turn a triangle's normal by at most acos(this) (78 degrees)
NORMAL_COS = 0.0                # .. nor give it two corners whose normals are further apart than acos(this) (90
                                # degrees: a thin fold, a hem, joined across with its rounding gone shades dark)
CORNER_COS = -0.5               # a feature point whose two feature edges meet at less than 120 degrees stays (cards
                                # keep their four corners)
SKIN_WEIGHT = 1.0               # a full change of skin weights (squared difference 2) against moving by 0.7 edges (more
                                # puts fingers' vertices on their weight borders, not on their shapes: jagged)
UV_WEIGHT = 1.0                 # a UV error (in surface the texture covers) against the same distance of position
CARD_UV_WEIGHT = 4.0            # on cards (their texture is their shape)
NORMAL_SCALE = 0.5              # a normal error of 1 (60 degrees) against moving by half an edge
REGULAR = 1e-3                  # the edge's squared length in the cost: prefers short edges where nothing else counts
CARD_NAMES = re.compile(r'hair|(?:^|_)har(?:_|$)|lash|brow', re.I)  # alpha-tested strands, eyelashes, eyebrows
CARD_BOUNDARY = 0.5             # a primitive with more of its vertices on open boundaries than this is cards too
NOT_LAYERED = re.compile(r'skin|face|eye|mouth|teeth|tongue|hair|(?:^|_)har(?:_|$)|lash|brow|tear|(?:^|_)ao(?:_|$)',
                         re.I)
                                # materials that never get a 2P colour layer (model.py layers only cloth)
SKIN_INFLUENCES = 8             # the model dict's joints / weights per vertex (decimate.c's INF)
RELATIVE = 4                    # a point's cost / (its mean edge length / the mean) ^ this: area-weighted errors grow
                                # with the fourth power of a shape's size (fingers would go first)
MOST_RELATIVE = 100.0           # .. but at most this many times; and never less than once (coarse areas: their outline)
MOST_REMOVED = 0.95             # a part gives up at most this share of its vertices in a pass
PASSES = 6                      # passes at most: a part that cannot reach its quota passes the rest to the others
_STATS = 5                      # decimate.c's S_COUNT


# ------------------------------------------------------------------------------------------------- the C core
_lib = None


def _build(cache=None):
    """decimate.c compiled into the cache (native.build: $XDG_CACHE_HOME/ttt2/native, or ~/.cache/ttt2/native) when
    it is not there or is older than the source -> the library's path."""
    return native.build('decimate', os.path.join('convert', 'decimate.c'), libs=('-lm',), cache=cache)


def _core():
    global _lib
    if _lib is None:
        lib = ctypes.CDLL(_build())
        f64, i32 = np.ctypeslib.ndpointer(np.float64, flags='C'), np.ctypeslib.ndpointer(np.int32, flags='C')
        lib.ttt2_decimate.restype = ctypes.c_int64
        lib.ttt2_decimate.argtypes = [ctypes.c_int, f64, ctypes.c_int, i32, ctypes.c_int, f64, i32, f64, f64, f64,
                                      np.ctypeslib.ndpointer(np.uint8, flags='C'), ctypes.c_int, i32, i32,
                                      ctypes.c_int, np.ctypeslib.ndpointer(np.int64, flags='C'), f64, ctypes.c_int64,
                                      f64]
        _lib = lib
    return _lib


# ------------------------------------------------------------------------------------------------- counting
def count(model):
    """The model's vertices as model.py counts them (before its welding): each primitive's distinct vertices."""
    return sum(len(np.unique(p['tris'])) for p in model['prims'])


def layered_materials(model):
    """The materials whose primitives may get a 2P colour layer: all but skin, eyes, mouth, hair, lashes, brows."""
    return {p['material'] for p in model['prims'] if not NOT_LAYERED.search(p['material'])}


def vertex_target(model, layered=None, budget=None):
    """The target for decimate() that leaves room for 2P colour layers over the `layered` materials (default:
    layered_materials) within `budget` (default model.VERTEX_BUDGET): budget / (1 + their share of the vertices).
    The share is the model's before decimating; part weights that keep more of the face and hair than of the
    clothes make the clothes' share smaller after it, so the layers fit (model.py leaves out the largest layers when
    they do not)."""
    budget = model_mod.VERTEX_BUDGET if budget is None else budget
    layered = layered_materials(model) if layered is None else set(layered)
    total = count(model)
    if not total:
        return budget
    share = sum(len(np.unique(p['tris'])) for p in model['prims'] if p['material'] in layered) / float(total)
    return int(budget / (1.0 + share))


# ---------------------------------------------------------------------------------------------- preparation
def _tri_areas(p, tris):
    if p.shape[1] == 2:
        e1, e2 = p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]]
        return 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    return 0.5 * np.linalg.norm(np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]]), axis=1)


def _boundary_share(ptris):
    """The share of a primitive's points (triangles of point ids) on its open boundary."""
    e = np.sort(np.concatenate([ptris[:, [0, 1]], ptris[:, [1, 2]], ptris[:, [2, 0]]]), 1)
    ue, cnt = np.unique(e, axis=0, return_counts=True)
    return len(np.unique(ue[cnt == 1])) / float(max(len(np.unique(ptris)), 1))


def _is_card(prim, ptris):
    return bool(CARD_NAMES.search(prim['material'])) or _boundary_share(ptris) > CARD_BOUNDARY


def _live_by_part(tri, wpart, nparts):
    """The wedges live triangles use, per part."""
    return np.bincount(wpart[np.unique(tri[tri[:, 0] >= 0])], minlength=nparts).astype(np.int64)


def _quotas(sizes, share, target, stuck):
    """Each part's quota (the vertices it keeps at least) for getting `sizes` (per part) down to `target`: the parts
    not `stuck` give up shares of their vertices proportional to `share` (at most MOST_REMOVED of a part in a pass),
    the stuck ones keep theirs."""
    free = ~stuck & (share > 0)
    need = float(sizes.sum() - target)
    if not free.any() or need <= 0:
        return sizes.copy()

    def removed(r):
        return np.where(free, np.minimum(MOST_REMOVED, share * r) * sizes, 0.0)
    lo, hi = 0.0, 1.0
    while removed(hi).sum() < need and hi < 1e6:
        hi *= 2
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if removed(mid).sum() < need else (lo, mid)
    return sizes - np.ceil(removed(hi)).astype(np.int64)


# ------------------------------------------------------------------------------------------------- decimate
def decimate(model, target, part_weights=None, log=print):
    """model: model.load_tekken7_model's dict (every prim the same vertex arrays); target: vertices at most (count()).
    -> a new model dict: compacted streams (shared by the prims again), the prims' triangles on them (a prim left
    with none is dropped), 'parts' entries' 'first' = the part's first vertex in the new streams (vertex numbers of
    a part's own mesh, such as its sections' base vertices, no longer apply), 'source' = each new vertex's index in
    the old streams. The model itself is returned when it is within the target already."""
    t0 = time.time()
    prims = model['prims']
    before = count(model)
    if before <= target or not prims:
        return model
    s0 = prims[0]
    n = len(s0['pos'])
    for p in prims:
        if p['pos'] is not s0['pos'] and not (p['pos'].shape == s0['pos'].shape and np.shares_memory(
                p['pos'], s0['pos'])):
            raise ValueError('decimate: the prims do not share one set of vertex streams')
    stream_keys = [k for k, v in s0.items() if k != 'tris' and isinstance(v, np.ndarray) and len(v) == n]
    pos, nrm, uv = s0['pos'], s0['nrm'], s0['uv']
    joints, weights = s0['joints'], s0['weights']
    if joints.shape[1] < SKIN_INFLUENCES:
        pad = SKIN_INFLUENCES - joints.shape[1]
        joints = np.concatenate([joints, np.zeros((n, pad), joints.dtype)], 1)
        weights = np.concatenate([weights, np.zeros((n, pad))], 1)
    # points: vertices within WELD; wedges: a prim's vertices at a point with the same attributes
    _, pid = np.unique(np.round(pos / WELD), axis=0, return_inverse=True)
    pid = pid.reshape(-1)
    npos = int(pid.max()) + 1
    akey = np.concatenate([pid[:, None], np.round(nrm, 4), np.round(uv, 6), joints, np.round(weights, 4)], 1)
    wvert, wprim, ttris, tprim = [], [], [], []
    base = 0
    for i, p in enumerate(prims):
        used = np.unique(p['tris'])
        if not len(used):
            continue
        _, first, inv = np.unique(akey[used], axis=0, return_index=True, return_inverse=True)
        vmap = np.full(n, -1, np.int64)
        vmap[used] = base + inv.reshape(-1)
        wvert.append(used[first])
        wprim.append(np.full(len(first), i))
        ttris.append(vmap[p['tris']])
        tprim.append(np.full(len(p['tris']), i))
        base += len(first)
    wvert, wprim = np.concatenate(wvert), np.concatenate(wprim)
    tri, tprim = np.concatenate(ttris), np.concatenate(tprim)
    wpos = pid[wvert]
    pt = wpos[tri]
    good = (pt[:, 0] != pt[:, 1]) & (pt[:, 1] != pt[:, 2]) & (pt[:, 0] != pt[:, 2])
    dropped = int((~good).sum())
    tri, tprim, pt = tri[good], tprim[good], pt[good]
    # positions in mean edge lengths
    rep = np.zeros(npos, np.int64)
    rep[pid] = np.arange(n)
    edge = np.linalg.norm(pos[rep[pt[:, [1, 2, 0]]]] - pos[rep[pt]], axis=2)
    scale = 1.0 / max(float(edge.mean()), 1e-12)
    ppos = np.ascontiguousarray(pos[rep] * scale, np.float64)
    # attributes, per prim: UVs in the surface their texture covers, normals scaled; locks; parts
    attr = np.zeros((len(wvert), 5))
    attr[:, 2:] = nrm[wvert] * NORMAL_SCALE
    lock = np.zeros(npos, np.uint8)
    tags = sorted({p['part'] for p in prims})
    share = np.array([max(float((part_weights or {}).get(t, 1.0)), 0.0) for t in tags])
    prim_part = np.array([tags.index(p['part']) for p in prims])
    cards = []
    for i, p in enumerate(prims):
        sel = tprim == i
        if not sel.any():
            continue
        card = _is_card(p, pt[sel])
        if card:
            cards.append(p['material'])
        a3 = _tri_areas(ppos, pt[sel]).sum()
        auv = _tri_areas(uv, wvert[tri[sel]]).sum()
        k = math.sqrt(a3 / auv) if auv > 1e-20 else 0.0
        k *= math.sqrt(CARD_UV_WEIGHT if card else UV_WEIGHT)
        mine = wprim == i
        attr[mine, :2] = uv[wvert[mine]] * k
        if share[prim_part[i]] <= 0:
            lock[np.unique(pt[sel])] = 1
    # exactly doubled triangles (the same three points) stay as they are
    _, inv, dup = np.unique(np.sort(pt, 1), axis=0, return_inverse=True, return_counts=True)
    lock[np.unique(pt[dup[inv.reshape(-1)] > 1])] = 1
    wpart = np.ascontiguousarray(prim_part[wprim], np.int32)
    sj = np.ascontiguousarray(joints[wvert][:, :SKIN_INFLUENCES], np.int32)
    sw = np.ascontiguousarray(weights[wvert][:, :SKIN_INFLUENCES], np.float64)
    wpos32, attr = np.ascontiguousarray(wpos, np.int32), np.ascontiguousarray(attr)
    wnrm = nrm[wvert] / np.maximum(np.linalg.norm(nrm[wvert], axis=1, keepdims=True), 1e-12)
    wnrm = np.ascontiguousarray(wnrm, np.float64)
    # each point's cost in its own scale: area-weighted errors grow with the fourth power of a feature's size
    loc = np.zeros(npos)
    cnt = np.zeros(npos)
    for k in range(3):
        np.add.at(loc, pt[:, k], edge[:, k] + edge[:, (k + 2) % 3])
        np.add.at(cnt, pt[:, k], 2)
    loc = np.where(cnt > 0, loc * scale / np.maximum(cnt, 1), 1.0)
    pfactor = np.clip(1.0 / np.maximum(loc, 1e-6) ** RELATIVE, 1.0, MOST_RELATIVE)
    tri32 = np.ascontiguousarray(tri, np.int32)
    stats, collapses = np.zeros(_STATS), 0
    lib = _core()
    stuck = share <= 0              # parts that keep what they have
    corner, flip = CORNER_COS, FLIP_COS
    for _ in range(PASSES):
        sizes = _live_by_part(tri32, wpart, len(tags))
        if sizes.sum() <= target:
            break
        quota = _quotas(sizes, share, target, stuck) if part_weights is not None else np.zeros(len(tags), np.int64)
        params = np.array([FEATURE_WEIGHT, flip, corner, SKIN_WEIGHT, REGULAR, 1e300, NORMAL_COS], np.float64)
        got = lib.ttt2_decimate(npos, ppos, len(wvert), wpos32, attr.shape[1], attr, sj, sw, wnrm, pfactor, lock,
                                len(tri32), tri32, wpart, len(tags), quota, params, int(target), stats)
        if got < 0:
            raise MemoryError('decimate: out of memory')
        collapses += int(stats[0])
        tri32 = np.ascontiguousarray(tri32[tri32[:, 0] >= 0])
        now = _live_by_part(tri32, wpart, len(tags))
        stuck |= now > quota            # could not get there: the others give up more
        if got > target and stuck.all() and corner == CORNER_COS:
            log('  decimate: %d vertices left with the cards\' corners kept; going on without' % got)
            corner, flip = 1.0, 0.0
            stuck = share <= 0
    # the new model
    tri_v, tprim = wvert[tri32], wprim[tri32[:, 0]]
    kept = np.unique(tri_v)
    streams = {k: s0[k][kept] for k in stream_keys}
    new_prims = []
    for i, p in enumerate(prims):
        t = tri_v[tprim == i]
        if not len(t):
            continue
        q = dict(p)
        q.update(streams)
        q['tris'] = np.searchsorted(kept, t).astype(p['tris'].dtype)
        new_prims.append(q)
    out = dict(model, prims=new_prims, source=kept)
    if 'parts' in model:
        out['parts'] = {tag: dict(info, first=int(np.searchsorted(kept, info['first']))) if 'first' in info else
                        dict(info) for tag, info in model['parts'].items()}
    after = count(out)
    by_part = {}
    for p in prims:
        by_part.setdefault(p['part'], [0, 0])[0] += len(np.unique(p['tris']))
    for q in new_prims:
        by_part[q['part']][1] += len(np.unique(q['tris']))
    log('  decimated: %d -> %d vertices (%s; %d collapses, %d points stay, cards: %s) in %.1f s' % (
        before, after, ', '.join('%s %d -> %d' % (k, a, b) for k, (a, b) in sorted(by_part.items())),
        collapses, stats[2], ', '.join(cards) or 'none', time.time() - t0))
    if dropped:
        log('  decimate: %d degenerate triangles left out' % dropped)
    if after > target:
        log('  WARNING: decimate could not get the model under %d vertices (%d)' % (target, after))
    return out
