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
* Folds (poses: test poses of the model's skeleton, skeleton.bend_poses: its elbows, knees, shoulders, hips, wrists,
  ankles, waist and neck turned; Tekken 8 models): the skin weights' change in a collapse is weighed by the same
  share of the area as everything else, so along a smooth limb, where the weights pass from the upper arm's
  joints to the forearm's over a long band, each collapse changes them a little and the chain of them took every
  vertex between the shoulder and the forearm (Miary Zo: no vertex of her upper arms and thighs; bent, her elbows
  and knees were flat planks from the shoulder and hip). So the bones are grouped by how the poses move them
  (skin_groups: a joint with its twist and muscle helpers, which turn with it, is one group; the head with every
  face and hair joint another), each wedge carries the range of every group's weight over the original vertices
  it stands for (from pass to pass), and no collapse may leave one of them further than FOLD_STEP (times the
  group's bend: its turn against its parent group's over FOLD_BEND) from its survivor's: a fold keeps a vertex at
  least every 2 x FOLD_STEP of the passing weight, a region one group moves (it only turns) loses its middle
  vertices freely, and the face and hair, one group, are decimated as before. The error the poses add to the
  bind pose's (each point's quadric of its triangles' planes in each pose, the triangles posed by their own
  vertices' weights, at V's posed position, less the same in the bind pose) adds to the cost (POSE_WEIGHT), so
  the folds that change the bent shape most go last when there is room to choose. Fingers are not bent (their
  knuckles' rings would take the vertices that keep their shapes, as a bigger SKIN_WEIGHT does).
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
* Pieces lying on others (classes' 'lying'): a strap on the skin or on a bikini top, a band, a cuff lies 1-3 mm over
  what is under it, and its errors are small for its area (a ribbon 20 mm wide flattens cheaply): Miary Zo's straps
  under her bust kept their twisted ends, their middles became long triangles that sank 4-8 mm into the skin and
  the skin hid them. A point of such a piece (over the skin or another of its part's pieces by LIE_NEAR at most) may
  move by that share of its height over it (LIE_LEAST at least): no collapse may leave it, or the points it took in,
  further than that from the new triangles (decimate.c tracks how far each point's taken-in points lie off its
  surface). The points under the piece are not held (they are hidden). The bounds give way after the floors.
* Reach (classes' 'reach', 'skin_reach'): the same bound, in mm, on every point of a part's large pieces and its skin.
  A piece's floor counts vertices, not where they go: with her straps held, her bikini top's bounded points took
  its whole floor and its cups flattened by 14 mm. Bounded, a piece gives what it can spare and keeps what its
  shape needs (past its floor: the others give up the rest), and the skin puts its floor where it curves.
* Skin under the pieces (_skin_under): each point stayed near where it was, but the skin's long new triangles still
  rise through what lies on them at places; those last few are taken back under the piece.
* Hair strands (classes' 'strands'): a hair card is a strip, a UV grid two to four vertices across (STRAND_COLUMNS) and
  up to fifty along, each row one v of the strand texture, each column one u (strips(): Miary Zo's hair 970 of its
  975 pieces, Reina's all). Collapsed like any surface, every card kept its four corners and its outline collapsed
  along itself, so a curved lock became the chord from its root to its tip (her 440 locks kept 3..23 vertices each,
  2060 more went to 515 tufts hidden at the back of her head): straight wide planks, a fringe lock lying across her
  right eye where Tekken 8's curves round it, the crown's cards cutting through the skull (the scalp showing between
  them). So the strips of such a part's cards (a primitive whose strips hold STRAND_SHARE of its vertices: not a braid,
  a mesh) are a quota group of their own the collapses never touch, made again in each pass for its quota from the
  original vertices (no blends: 'source' and the hair chains bound afterwards work as before): each strip keeps its
  first and last rows and columns (its UV span), its rows where it bends (top-down splits: the row furthest off the
  line between its kept neighbours first, a kept segment counting as lying STRAND_LENGTH of its length off: the chains
  bend a strand at its kept rows only), its inner columns where its cross-section bends (a gutter, not a plank), and
  is left out whole when the share of it that shows (shown(): seen from 13 directions, every card in front of it
  covering STRAND_COVER of it, alpha-tested strands let the inner layers show; judged again once those under which it
  lay are gone: drop_errors()) times STRAND_DROP of its length is less than the tolerance: tufts and inner layers go,
  the fringe, the parting and the outline stay. One tolerance for all, the least that fits the quota; the class's
  value (mm) is the floor: what that tolerance keeps.
* Wires (classes' 'tubes'): a thin tube is a grid of rings (tubes(): Miary Zo's necklace, two loops of 49 and 45
  six-sided rings 3 mm thick). The collapses took them across the rings, from one side of a ring to the other, so
  each loop (343 and 315 vertices, kept 99 and 97) became a twisted flat ribbon up to 6 mm wide on her chest. So
  they are reduced as the strands are, a quota group of their own: whole rings, kept where the wire bends (the
  top-down splits of the rings, the same STRAND_LENGTH), each with every other side of six or more (three sides of a
  wire 3 mm thick show as round as six: the normals are the source's).
* Only when every part is stuck above the target do the folds give way (further passes with twice the step, then
  without the rule: a fold's vertices count no more than the parts' quotas), and only then the corners too (a
  further pass without the corner locks, flips up to 90 degrees); a model that still does not fit is returned as
  it got, with a warning. The folds' vertices come out of what the parts' quotas and the locks leave free: a model
  whose locked points nearly fill the target (Miary Zo: 32.3k of 36k, every part but the face at its floor) pays
  for them with the parts still free (her face: 4913 -> 4618).

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
FOLD_STEP = 0.25                # a skin group's weight may change by this much (times its bend: FOLD_BEND) for every
                                # original vertex a collapse leaves to another: a fold keeps a vertex every 0.5 of it
FOLD_BEND = 90.0                # degrees: a group whose joint the test poses turn by this much counts its change whole
POSE_WEIGHT = 1.0               # what the bent poses add to the bind pose's error, in the cost (summed over the poses)
MOST_REMOVED = 0.95             # a part gives up at most this share of its vertices in a pass
PASSES = 6                      # passes at most: a part that cannot reach its quota passes the rest to the others
SKIN_NAMES = re.compile(r'skin', re.I)  # a part's bare skin (classes' 'skin': the arms', legs', hands', feet', body's)
BIG_PIECE = 100.0               # mm: a connected piece of a material this long or longer is one of its part's large
                                # pieces (classes' 'big': a bikini top, a sarong, a jacket; not a bead or a buckle)
SMALL_PIECE = 30.0              # mm: a piece shorter than this is small (classes' 'small': a bead, a stud, a coin) ..
SMALL_LEAST = 6                 # .. and keeps this many vertices (classes' 'small' more per mm of its length)
LIE_NEAR = 8.0                  # mm: a point of a clothing piece this close to the skin or another piece (over or
                                # under it) lies on it (classes' 'lying': a strap, a band, a glove's cuff) ..
LIE_PIECE = 15.0                # .. a piece at least this long (a bead's error is never seen, a buckle's parts' are) ..
FREE_COST = 1e-4                # a point covered.mark gives up: its cost this much of what it would be
LIE_LEAST = 1.0                 # .. and may move by its 'lying' share of its height over the skin, at least this
LIE_COS = 0.7                   # .. over it: within 45 degrees of its normal (not beside it, past a material border)
LIE_UNDER = 1.0                 # mm: or under it by no more than this (a strap's edge pressed in); deeper, it is hidden
UNDER_CLEAR = 1.0               # mm: the new skin ends this far under what lies on it (_skin_under) ..
UNDER_EVERY = 4.0               # .. looked at this often over the pieces' triangles (mm) ..
UNDER_ROUNDS = 5                # .. this many times (moving a corner uncovers its neighbours' triangles) ..
UNDER_MOST = 5.0                # .. a corner moving this far at most
STRAND_COLUMNS = 4              # a hair card's strip: a UV grid of 2..this many columns (strips(); wider: a mesh) ..
STRAND_SHARE = 0.9              # .. a card primitive of a part with 'strands' whose strips hold this share of its
                                # vertices is reduced as strands (Miary Zo's and Reina's hair; a braid, a mesh: collapses)
STRAND_LENGTH = 0.04            # a strand's kept segment counts as lying this share of its length off (the hair chains,
                                # bound after decimating, bend a strand at its kept rows only: 100 mm = 4 mm)
STRAND_DROP = 0.5               # a strip left out counts as this share of its length times the share of it that shows
                                # (0.25 left two 1 mm slits of neck skin between the inner strips at Reina's nape)
STRAND_STEP = 2.5               # mm: what shows of a strip: the surfaces sampled this often ..
STRAND_CELL = 3.5               # .. seen in cells this wide ..
STRAND_NEAR = 1.5               # .. a sample this close to the front of its cell is at the front ..
STRAND_COVER = 0.5              # .. and each card in front of it hides this share of it (its strands' alpha test)
STRAND_PEEL = (1.0, 4.0)        # mm: what shows of the strips is judged again without those left out up to these
STRAND_MARGIN = 50.0            # mm: the surfaces round the strips that may hide them
TUBE_SIDES = (3, 16)            # a wire (tubes()): a grid of rings of this many sides ..
TUBE_RADIUS = 3.0               # mm: .. none of them wider than this round its centre ..
TUBE_MOST = 4096                # .. in a piece of at most this many vertices (anything larger is no wire)
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
        f32 = np.ctypeslib.ndpointer(np.float32, flags='C')
        lib.ttt2_decimate.restype = ctypes.c_int64
        lib.ttt2_decimate.argtypes = [ctypes.c_int, f64, ctypes.c_int, i32, ctypes.c_int, f64, i32, f64, f64, f64,
                                      np.ctypeslib.ndpointer(np.uint8, flags='C'), ctypes.c_int, i32, i32,
                                      ctypes.c_int, np.ctypeslib.ndpointer(np.int64, flags='C'), f64, ctypes.c_int64,
                                      f64, ctypes.c_int, f64, ctypes.c_int, f32, f32, f32, f64, f64, f64, f64]
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


def _quotas(sizes, share, target, stuck, floor=None):
    """Each part's quota (the vertices it keeps at least) for getting `sizes` (per part) down to `target`: the parts
    not `stuck` give up shares of their vertices proportional to `share` (at most MOST_REMOVED of a part in a pass,
    and never below its `floor`: what the others give up instead), the stuck ones keep theirs."""
    floor = np.zeros(len(sizes)) if floor is None else floor
    free = ~stuck & (share > 0) & (sizes > floor)
    need = float(sizes.sum() - target)
    if not free.any() or need <= 0:
        return sizes.copy()

    def removed(r):
        return np.where(free, np.minimum(np.minimum(MOST_REMOVED, share * r) * sizes, sizes - floor), 0.0)
    lo, hi = 0.0, 1.0
    while removed(hi).sum() < need and hi < 1e6:
        hi *= 2
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if removed(mid).sum() < need else (lo, mid)
    return sizes - np.ceil(removed(hi)).astype(np.int64)


# ------------------------------------------------------------------------------------------------- decimate
def posed_points(pos, joints, weights, poses):
    """The vertices' positions (n, 3) in each of `poses` ([(bones, 4, 4) changes]: skeleton.bend_poses) as linear
    blend skinning puts them, each by its own joints and weights -> (len(poses), n, 3)."""
    w = weights / np.maximum(weights.sum(1, keepdims=True), 1e-12)
    out = np.empty((len(poses), len(pos), 3))
    for k, D in enumerate(poses):
        M = np.einsum('vk,vkij->vij', w, np.asarray(D, np.float64)[joints])
        out[k] = np.einsum('vij,vj->vi', M[:, :3, :3], pos) + M[:, :3, 3]
    return out


def skin_groups(bones, poses):
    """The bones that move together in the test poses ([(bones, 4, 4) changes]: skeleton.bend_poses): each bone's group
    (bones whose changes are the same in every pose: a joint and its twist and muscle helpers, the head with the face
    and hair joints) and each group's bend (the largest angle it turns by against the group of its nearest parent
    outside it, over FOLD_BEND; the root's 0) -> (groups (bones,), bends (groups,))."""
    n = len(bones['names'])
    key = np.round(np.concatenate([np.asarray(D, np.float64)[:, :3, :].reshape(n, -1) for D in poses], 1), 5)
    _, group = np.unique(key, axis=0, return_inverse=True)
    group = group.reshape(-1)
    bend = np.zeros(int(group.max()) + 1)
    parents = bones['parents']
    for i in range(n):
        p = parents[i]
        while p >= 0 and group[p] == group[i]:
            p = parents[p]
        if p < 0:
            continue
        for D in poses:
            r = np.asarray(D[i], np.float64)[:3, :3] @ np.asarray(D[p], np.float64)[:3, :3].T
            angle = np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1)))
            bend[group[i]] = max(bend[group[i]], angle / FOLD_BEND)
    return group, bend


def _connected(n, e):
    """The connected components of n nodes joined by the edges e (m, 2): each node's label, the smallest node number of
    its component."""
    label = np.arange(n)
    while True:                      # (each node's smallest label over its edges, then pointer jumping)
        a, b = label[e[:, 0]], label[e[:, 1]]
        low = np.minimum(a, b)
        new = label.copy()
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        while True:
            jumped = new[new]
            if (jumped == new).all():
                break
            new = jumped
        if (new == label).all():
            return label
        label = new


def _pieces(pt, tprim, npos, pos):
    """Each triangle's connected piece of its own primitive (triangles of one prim sharing points: a bikini top, each
    bead of a necklace) and each piece's length (the largest side of its box, in pos's units) -> (piece per
    triangle, lengths)."""
    key = tprim[:, None].astype(np.int64) * npos + pt
    _, node = np.unique(key, return_inverse=True)
    node = node.reshape(pt.shape)
    label = _connected(int(node.max()) + 1, np.concatenate([node[:, [0, 1]], node[:, [1, 2]]]))
    _, piece = np.unique(label[node[:, 0]], return_inverse=True)
    piece = piece.reshape(-1)
    corners = pos[pt].reshape(-1, 3)
    lo = np.full((int(piece.max()) + 1, 3), np.inf)
    hi = np.full_like(lo, -np.inf)
    np.minimum.at(lo, np.repeat(piece, 3), corners)
    np.maximum.at(hi, np.repeat(piece, 3), corners)
    return piece, (hi - lo).max(1)


def _small(prims, pid, npos, ppos, classes):
    """The pieces of the prims (_pieces, over every prim's triangles in order: -1 for a degenerate one) and the small
    ones of the parts `classes` names with 'small' (shorter than SMALL_PIECE, not cards): each one's allowance
    (SMALL_LEAST + 'small' per mm of its length; 0 for the others) -> (piece per triangle, lengths, allowances)."""
    vt = np.concatenate([p['tris'] for p in prims]).astype(np.int64)
    tp = np.concatenate([np.full(len(p['tris']), i) for i, p in enumerate(prims)])
    pt = pid[vt]
    ok = (pt[:, 0] != pt[:, 1]) & (pt[:, 1] != pt[:, 2]) & (pt[:, 0] != pt[:, 2])
    piece = np.full(len(vt), -1, np.int64)
    if not ok.any():
        return piece, np.zeros(0), np.zeros(0, np.int64)
    piece[ok], length = _pieces(pt[ok], tp[ok], npos, ppos)
    allowance = np.zeros(len(length), np.int64)
    for i, p in enumerate(prims):
        own = (classes.get(p['part']) or {}).get('small')
        sel = (tp == i) & ok
        if own is None or not sel.any() or _is_card(p, pt[sel]):
            continue
        mine = np.unique(piece[sel])
        mine = mine[length[mine] < SMALL_PIECE]
        allowance[mine] = SMALL_LEAST + np.round(float(own) * length[mine]).astype(np.int64)
    return piece, length, allowance


def surface_gap(points, corners, normals, near, owner=None, tri_owner=None, under=np.inf, which=False):
    """How far each of `points` (n, 3) lies over the surface of the triangles `corners` (t, 3, 3), whose sides
    `normals` (t, 3) face outward: its distance to the closest triangle it lies over, or under by no more than `under`
    (the way to it within acos(LIE_COS) of the triangle's normal: not one beside it, past a border between
    materials), signed (< 0 under it), or NaN when no such triangle is within `near` (a grid of cells `near` wide:
    only the triangles in a point's cell and its neighbours count). owner (n), tri_owner (t): a point does not lie on
    its own piece's triangles. which: -> (the distances, each point's triangle (-1: none))."""
    out = np.full(len(points), np.nan)
    closest = np.full(len(points), -1, np.int64)
    if not len(points) or not len(corners):
        return (out, closest) if which else out
    lo = np.minimum(points.min(0), corners.reshape(-1, 3).min(0)) - 2 * near
    cmin = np.floor((corners.min(1) - near - lo) / near).astype(np.int64)
    cmax = np.floor((corners.max(1) + near - lo) / near).astype(np.int64)
    dims = np.maximum(cmax.max(0), np.floor((points.max(0) - lo) / near).astype(np.int64)) + 1
    span = cmax - cmin + 1
    many = span.prod(1)
    # every (cell, triangle) the triangles' boxes (grown by `near`) cover
    tri = np.repeat(np.arange(len(corners)), many)
    k = np.arange(len(tri)) - np.repeat(np.cumsum(many) - many, many)
    sy, sz = span[tri, 1], span[tri, 2]
    cell = cmin[tri] + np.stack([k // (sy * sz), (k // sz) % sy, k % sz], 1)
    key = (cell[:, 0] * dims[1] + cell[:, 1]) * dims[2] + cell[:, 2]
    order = np.argsort(key, kind='stable')
    key, tri = key[order], tri[order]
    pc = np.floor((points - lo) / near).astype(np.int64)
    pkey = (pc[:, 0] * dims[1] + pc[:, 1]) * dims[2] + pc[:, 2]
    first, last = np.searchsorted(key, pkey, 'left'), np.searchsorted(key, pkey, 'right')
    best = np.full(len(points), np.inf)
    sign = np.zeros(len(points))
    todo = np.nonzero(last > first)[0]
    chunk = 1 << 20                  # (pairs at a time)
    i = 0
    while i < len(todo):
        n = np.cumsum(last[todo[i:]] - first[todo[i:]])
        j = i + max(int(np.searchsorted(n, chunk)), 1)
        pts = todo[i:j]
        cnt = last[pts] - first[pts]
        pp = np.repeat(pts, cnt)
        tt = tri[np.repeat(first[pts], cnt) + np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)]
        q = _closest(points[pp], corners[tt])
        dist = np.linalg.norm(points[pp] - q, axis=1)
        side = np.einsum('ij,ij->i', points[pp] - q, normals[tt])
        keep = (np.abs(side) >= LIE_COS * dist) & (side >= -under)
        if owner is not None:
            keep &= owner[pp] != tri_owner[tt]
        pp, tt, dist, side = pp[keep], tt[keep], dist[keep], side[keep]
        # each point's closest pair (a tie between triangles meeting at an edge: the farthest-out side wins, so a
        # point over a convex edge is not taken for one under it)
        o = np.lexsort((-side, dist, pp))
        pp, tt, dist, side = pp[o], tt[o], dist[o], side[o]
        head = np.ones(len(pp), bool)
        head[1:] = pp[1:] != pp[:-1]
        better = dist[head] < best[pp[head]]
        best[pp[head][better]] = dist[head][better]
        sign[pp[head][better]] = np.where(side[head][better] < 0, -1.0, 1.0)
        closest[pp[head][better]] = tt[head][better]
        i = j
    ok = best <= near
    out[ok] = best[ok] * sign[ok]
    closest[~ok] = -1
    return (out, closest) if which else out


def _closest(p, t):
    """The closest point to each p (n, 3) on its triangle t (n, 3, 3) (by the regions of its corners, edges and
    face)."""
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    ab, ac, ap, bp, cp = b - a, c - a, p - a, p - b, p - c

    def d(x, y):
        return np.einsum('ij,ij->i', x, y)
    d1, d2, d3, d4, d5, d6 = d(ab, ap), d(ac, ap), d(ab, bp), d(ac, bp), d(ab, cp), d(ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    with np.errstate(divide='ignore', invalid='ignore'):
        den = va + vb + vc
        v, w = np.where(den != 0, vb / den, 0.0), np.where(den != 0, vc / den, 0.0)
        q = a + ab * v[:, None] + ac * w[:, None]
        sel = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)            # (edge bc)
        x = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        q[sel] = (b + (c - b) * x[:, None])[sel]
        sel = (vb <= 0) & (d2 >= 0) & (d6 <= 0)                       # (edge ac)
        x = d2 / (d2 - d6)
        q[sel] = (a + ac * x[:, None])[sel]
        sel = (vc <= 0) & (d1 >= 0) & (d3 <= 0)                       # (edge ab)
        x = d1 / (d1 - d3)
        q[sel] = (a + ab * x[:, None])[sel]
    q[(d6 >= 0) & (d5 <= d6)] = c[(d6 >= 0) & (d5 <= d6)]
    q[(d3 >= 0) & (d4 <= d3)] = b[(d3 >= 0) & (d4 <= d3)]
    q[(d1 <= 0) & (d2 <= 0)] = a[(d1 <= 0) & (d2 <= 0)]
    return q


def _bounds(prims, pid, npos, pos, nrm, classes, cards, piece, length):
    """Each point's bound (mm; inf: none) from its part's `classes` (not cards; piece, length: _small's). With
    'lying': a point of a clothing piece at least LIE_PIECE long lying on the skin (any part's: a collar on the face's
    neck) or on another such piece of those parts, over it by LIE_NEAR at most or under it by LIE_UNDER (a strap on the
    skin or on a bikini top, a band, a glove's cuff; not what lies under a piece: it is hidden), may move by that share
    of its height over the closest, at least LIE_LEAST. With 'reach': every point of the pieces not small may move by
    that many mm at most, with 'skin_reach': the points of its skin."""
    bound = np.full(npos, np.inf)
    vt = np.concatenate([p['tris'] for p in prims]).astype(np.int64)
    tp = np.concatenate([np.full(len(p['tris']), i) for i, p in enumerate(prims)])
    own = [(classes.get(p['part']) or {}) for p in prims]
    share = np.array([np.nan if p['material'] in cards else float(o.get('lying', np.nan)) for p, o in zip(prims, own)])
    skin = np.array([bool(SKIN_NAMES.search(p['material'])) and p['material'] not in cards for p in prims])
    reach = np.array([np.inf if p['material'] in cards else float(o.get('skin_reach' if s else 'reach', np.inf))
                      for p, o, s in zip(prims, own, skin)])
    far = (piece >= 0) & np.isfinite(reach[tp])
    far[far] = skin[tp[far]] | (length[piece[far]] >= SMALL_PIECE)
    np.minimum.at(bound, pid[vt[far].reshape(-1)], np.repeat(reach[tp[far]], 3))
    mine = (piece >= 0) & ~np.isnan(share[tp])
    mine[mine] = skin[tp[mine]] | (length[piece[mine]] >= LIE_PIECE)
    cloth = mine & ~skin[tp]
    if not cloth.any():
        return bound
    under = mine | ((piece >= 0) & skin[tp])
    corners = pos[vt[under]].astype(np.float64)
    face = _outward(corners, nrm[vt[under]])
    # the clothing's points with their pieces (a point on a border between two materials: once for each)
    corner = vt[cloth].reshape(-1)
    owner = np.repeat(piece[cloth], 3)
    _, first = np.unique(np.stack([pid[corner], owner], 1), axis=0, return_index=True)
    corner, owner = corner[first], owner[first]
    gap = surface_gap(pos[corner].astype(np.float64), corners, face, LIE_NEAR, owner, piece[under], LIE_UNDER)
    on = ~np.isnan(gap)
    least = np.repeat(share[tp[cloth]], 3)[first]
    np.minimum.at(bound, pid[corner[on]], np.maximum(least[on] * np.maximum(gap[on], 0.0), LIE_LEAST))
    return bound


def _outward(corners, normals):
    """The unit normals of the triangles `corners` (t, 3, 3) on the side their vertices' normals (t, 3, 3) point to,
    whatever the winding."""
    face = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    face *= np.where(np.einsum('ij,ij->i', face, normals.sum(1)) < 0, -1.0, 1.0)[:, None]
    return face / np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-12)


def _skin_under(streams, new_prims, kept, pid, prims, pos, nrm, classes, cards, log):
    """The last step of the pieces lying on the skin: each point stayed near where it was, but the skin's long new
    triangles still rise through what lies on them at places (a strap's edge, a cup's, a nail). Wherever a new piece
    of a part with 'lying' lies under any part's new skin though it lay over the skin before (or under it by LIE_UNDER at
    most: an end tucked deeper into the skin stays tucked), the skin is taken back to UNDER_CLEAR below it: the
    triangle's corners go back along their normals, the least that clears it, UNDER_MOST at most (a point's wedges
    together) -> the vertices moved. What hides under a piece is not seen; what is seen beside it is a few mm deeper."""
    on = {t for t, own in classes.items() if own.get('lying') is not None}

    def tris(which, skin):
        got = [q['tris'] for q in which if q['material'] not in cards and (q['part'] in on or skin) and
               bool(SKIN_NAMES.search(q['material'])) == skin]
        return np.concatenate(got).astype(np.int64) if got else np.zeros((0, 3), np.int64)
    skin, cloth = tris(new_prims, True), tris(new_prims, False)
    if not len(skin) or not len(cloth):
        return 0
    new = streams['pos']
    now = new.astype(np.float64)
    corner = now[cloth]
    # points on the pieces, at most UNDER_EVERY apart
    rows = np.clip(np.ceil(np.linalg.norm(corner[:, [1, 2, 0]] - corner, axis=2).max(1) / UNDER_EVERY), 1, 64)
    points = []
    for n in np.unique(rows.astype(np.int64)):
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
        keep = i + j <= n
        w = np.stack([i[keep], j[keep], n - i[keep] - j[keep]], 1) / float(n)
        points.append(np.einsum('tcx,mc->tmx', corner[rows == n], w).reshape(-1, 3))
    points = np.concatenate(points)
    was = tris(prims, True)
    c = pos[was].astype(np.float64)
    gap = surface_gap(points, c, _outward(c, nrm[was]), LIE_NEAR)
    points = points[np.nan_to_num(gap, nan=-np.inf) >= -LIE_UNDER]
    used = np.unique(skin)
    point = np.full(len(new), -1, np.int64)
    point[used] = np.unique(pid[kept[used]], return_inverse=True)[1].reshape(-1)
    normal = streams['nrm'].astype(np.float64)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    moved = np.zeros(len(new))
    for _ in range(UNDER_ROUNDS):
        c = now[skin]
        gap, tri = surface_gap(points, c, _outward(c, normal[skin]), LIE_NEAR, which=True)
        over = (tri >= 0) & (np.nan_to_num(gap, nan=np.inf) < UNDER_CLEAR)
        if not over.any():
            break
        c, gap, tri = c[tri[over]], gap[over], tri[over]
        # (the closest point's weights over its corners; each corner's share of the way the least that clears it)
        e1, e2, d = c[:, 1] - c[:, 0], c[:, 2] - c[:, 0], _closest(points[over], c) - c[:, 0]
        aa, ab, bb = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
        da, db = (d * e1).sum(1), (d * e2).sum(1)
        den = np.maximum(aa * bb - ab * ab, 1e-12)
        w1, w2 = (bb * da - ab * db) / den, (aa * db - ab * da) / den
        w = np.stack([1.0 - w1 - w2, w1, w2], 1)
        need = (UNDER_CLEAR - gap)[:, None] * w / np.maximum((w * w).sum(1, keepdims=True), 1e-12)
        back = np.zeros(int(point.max()) + 1)
        np.maximum.at(back, point[skin[tri]].reshape(-1), need.reshape(-1))
        step = np.minimum(back[point[used]], UNDER_MOST - moved[used])
        now[used] -= normal[used] * step[:, None]
        moved[used] += step
    new[used] = now[used]
    done = int((moved[used] > 0).sum())
    if done:
        log('  decimate: %d skin vertices taken back under the pieces lying on them (%.1f mm at most)' % (
            done, moved[used].max()))
    return done


# ------------------------------------------------------------------------------------------------- strands
def strips(prim, pid=None):
    """The strips of a hair card primitive: the connected pieces of its triangles (joined by vertices, not positions)
    that are UV grids (every vertex of a row has the row's v, every vertex of a column the column's u, one vertex in
    each place; 2..STRAND_COLUMNS columns, 2 rows or more) made of two triangles in each cell, open at both sides (pid:
    the vertices' points; a strip whose first and last columns meet is a tube) -> ([(grid (rows, columns) of vertex
    numbers in the rows' v and the columns' u order, rows' v, columns' u, +1 when the triangles turn from the row's
    direction to the column's in (column, row), -1 the other way)], the share of the prim's vertices in them)."""
    T = np.asarray(prim['tris'], np.int64)
    used = np.unique(T)
    if not len(used):
        return [], 0.0
    local = np.full(len(prim['pos']), -1, np.int64)
    local[used] = np.arange(len(used))
    lt = local[T]
    _, comp = np.unique(_connected(len(used), np.concatenate([lt[:, [0, 1]], lt[:, [1, 2]]])), return_inverse=True)
    comp = comp.reshape(-1)
    count = int(comp.max()) + 1
    vorder = np.argsort(comp, kind='stable')
    vstart = np.searchsorted(comp[vorder], np.arange(count + 1))
    tcomp = comp[lt[:, 0]]
    torder = np.argsort(tcomp, kind='stable')
    tstart = np.searchsorted(tcomp[torder], np.arange(count + 1))
    uv = np.round(np.asarray(prim['uv'], np.float64)[used], 5)
    row, col = np.zeros(len(used), np.int64), np.zeros(len(used), np.int64)
    out, inside = [], 0
    for c in range(count):
        vs = vorder[vstart[c]:vstart[c + 1]]
        rv, ri = np.unique(uv[vs, 1], return_inverse=True)
        cu, ci = np.unique(uv[vs, 0], return_inverse=True)
        R, C = len(rv), len(cu)
        tr = lt[torder[tstart[c]:tstart[c + 1]]]
        if R < 2 or not 2 <= C <= STRAND_COLUMNS or R * C != len(vs) or len(tr) != 2 * (R - 1) * (C - 1):
            continue
        grid = np.full((R, C), -1, np.int64)
        grid[ri.reshape(-1), ci.reshape(-1)] = vs
        if (grid < 0).any():
            continue
        row[vs], col[vs] = ri.reshape(-1), ci.reshape(-1)
        r, q = row[tr], col[tr]
        cell = r.min(1) * (C - 1) + q.min(1)
        turn = (q[:, 1] - q[:, 0]) * (r[:, 2] - r[:, 0]) - (r[:, 1] - r[:, 0]) * (q[:, 2] - q[:, 0])
        if ((r.max(1) - r.min(1)) != 1).any() or ((q.max(1) - q.min(1)) != 1).any() or \
                (np.bincount(cell, minlength=(R - 1) * (C - 1)) != 2).any() or not (
                (turn > 0).all() or (turn < 0).all()):
            continue
        grid = used[grid]
        if pid is not None and (pid[grid[:, 0]] == pid[grid[:, -1]]).any():
            continue
        out.append((grid, rv, cu, 1 if turn[0] > 0 else -1))
        inside += len(vs)
    return out, inside / float(len(used))


def _grid(T, n):
    """T (t, 3): the triangles of one connected piece, its vertices numbered 0..n-1 -> the (rows, columns) grid of its
    vertex numbers when it is a grid of cells (its outline a rectangle; walked from a corner along the outline: the
    first row and column; each further vertex the one next to both of its neighbours before it, not the one between
    them; then every cell two triangles of its own) or None."""
    e = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1)
    ue, cnt = np.unique(e, axis=0, return_counts=True)
    outline = ue[cnt == 1]
    half = len(outline) // 2 + 2                     # (rows + columns, rows x columns = n)
    disc = half * half - 4 * n
    if (cnt > 2).any() or len(outline) % 2 or disc < 0:
        return None
    rows = int(round((half - math.sqrt(disc)) / 2))
    if rows < 2 or rows * (half - rows) != n or len(T) != 2 * (rows - 1) * (half - rows - 1):
        return None
    near = [set() for _ in range(n)]
    for a, b in ue:
        near[a].add(b)
        near[b].add(a)
    along = [[] for _ in range(n)]
    for a, b in outline:
        along[a].append(b)
        along[b].append(a)
    if any(len(x) not in (0, 2) for x in along):
        return None
    tris = np.bincount(T.reshape(-1), minlength=n)
    for corner in [v for v in range(n) if along[v] and tris[v] <= 2]:
        for nxt in along[corner]:
            loop = [corner, nxt]
            while len(loop) < len(outline):
                a, b = along[loop[-1]]
                loop.append(b if a == loop[-2] else a)
            if corner not in along[loop[-1]]:
                return None                          # (more than one outline: a ring, holes)
            for R in (rows, half - rows):
                C = half - R
                g = np.full((R, C), -1, np.int64)
                g[0], g[:, 0] = loop[:C], [corner] + loop[:-R:-1]
                for i in range(1, R):
                    for j in range(1, C):
                        d = (near[g[i - 1, j]] & near[g[i, j - 1]]) - {g[i - 1, j - 1]}
                        if len(d) != 1:
                            break
                        g[i, j] = d.pop()
                    else:
                        continue
                    break
                if (g < 0).any() or len(np.unique(g)) != n:
                    continue
                at = np.empty((n, 2), np.int64)
                at[g.reshape(-1)] = np.stack(np.meshgrid(np.arange(R), np.arange(C), indexing='ij'), 2).reshape(-1, 2)
                r, q = at[T, 0], at[T, 1]
                cell = r.min(1) * (C - 1) + q.min(1)
                if ((r.max(1) - r.min(1)) == 1).all() and ((q.max(1) - q.min(1)) == 1).all() and \
                        (np.bincount(cell, minlength=(R - 1) * (C - 1)) == 2).all():
                    return g
    return None


def tubes(prim, pid, pos):
    """The wires of a primitive: its connected pieces (joined by vertices) that are grids (_grid) whose first and last
    columns meet (pid: the vertices' points), each row a ring of TUBE_SIDES sides none wider than TUBE_RADIUS round its
    centre (pos: the positions, mm), three rings or more, SMALL_PIECE long or longer (shorter: a small piece, a bead),
    its triangles all turning one way -> [(grid (rings, sides + 1) of vertex numbers, each ring's distance along the
    wire from the first (mm), +1 when the triangles turn from the row's direction to the column's in (column, row), -1
    the other way)]."""
    T = np.asarray(prim['tris'], np.int64)
    used = np.unique(T)
    if not len(used):
        return []
    local = np.full(len(prim['pos']), -1, np.int64)
    local[used] = np.arange(len(used))
    lt = local[T]
    _, comp = np.unique(_connected(len(used), np.concatenate([lt[:, [0, 1]], lt[:, [1, 2]]])), return_inverse=True)
    comp = comp.reshape(-1)
    count = int(comp.max()) + 1
    size = np.bincount(comp, minlength=count)
    tcomp = comp[lt[:, 0]]
    out = []
    for c in np.nonzero((size >= 3 * (TUBE_SIDES[0] + 1)) & (size <= TUBE_MOST))[0]:
        vs = np.nonzero(comp == c)[0]
        mine = np.full(len(used), -1, np.int64)
        mine[vs] = np.arange(len(vs))
        tr = mine[lt[tcomp == c]]
        g = _grid(tr, len(vs))
        if g is None:
            continue
        g = vs[g]
        if (pid[used[g[0]]] == pid[used[g[-1]]]).all():
            g = g.T                                  # (the rings are the rows)
        P = np.asarray(pos, np.float64)[used[g]]
        if not (pid[used[g[:, 0]]] == pid[used[g[:, -1]]]).all() or len(g) < 3 or \
                not TUBE_SIDES[0] <= g.shape[1] - 1 <= TUBE_SIDES[1]:
            continue
        centre = P[:, :-1].mean(1)
        if np.linalg.norm(P - centre[:, None], axis=2).max() > TUBE_RADIUS:
            continue
        at = np.empty((len(used), 2), np.int64)
        R, C = g.shape
        at[g.reshape(-1)] = np.stack(np.meshgrid(np.arange(R), np.arange(C), indexing='ij'), 2).reshape(-1, 2)
        t = lt[tcomp == c]
        r, q = at[t, 0], at[t, 1]
        turn = (q[:, 1] - q[:, 0]) * (r[:, 2] - r[:, 0]) - (r[:, 1] - r[:, 0]) * (q[:, 2] - q[:, 0])
        if not ((turn > 0).all() or (turn < 0).all()):
            continue
        along = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(centre, axis=0), axis=1))])
        if along[-1] >= SMALL_PIECE:
            out.append((used[g], along, 1 if turn[0] > 0 else -1))
    return out


def _splits(P, t, length):
    """Top-down splits of a grid's rows (P (rows, columns, 3) positions, t (rows,) the rows' texture coordinate, which
    the triangles interpolate): each inner row's error when it is put back, the worst first (how far the rows between
    its kept neighbours lie off the lines between them, at least `length` times the distance between those two rows;
    never more than the error of the split it came from: the rows a tolerance keeps nest) -> (rows,), inf at the ends."""
    err = np.zeros(len(t))
    err[0] = err[-1] = np.inf
    todo = [(0, len(t) - 1, np.inf)]
    while todo:
        a, b, cap = todo.pop()
        if b - a < 2:
            continue
        s = ((t[a + 1:b] - t[a]) / (t[b] - t[a]))[:, None, None]
        off = np.linalg.norm(P[a + 1:b] - (P[a] * (1.0 - s) + P[b] * s), axis=2).max(1)
        r = int(np.argmax(off))
        e = min(max(float(off[r]), length * float(np.linalg.norm(P[b].mean(0) - P[a].mean(0)))), cap)
        err[a + 1 + r] = e
        todo += [(a, a + 1 + r, e), (a + 1 + r, b, e)]
    return err


def _views():
    """The directions what shows of the hair is judged from (the model's y up): the four sides, the four between them,
    the four from 45 degrees above and from above."""
    out = [(0.0, 1.0, 0.0)]
    for a in range(0, 360, 45):
        out.append((math.sin(math.radians(a)), 0.0, math.cos(math.radians(a))))
    for a in range(0, 360, 90):
        out.append((math.sin(math.radians(a)) * 0.7071, 0.7071, math.cos(math.radians(a)) * 0.7071))
    return np.array(out)


def _samples(corners):
    """Points on the triangles `corners` (t, 3, 3), at most STRAND_STEP apart -> (points, each one's triangle)."""
    longest = np.linalg.norm(corners[:, [1, 2, 0]] - corners, axis=2).max(1)
    rows = np.clip(np.ceil(longest / STRAND_STEP), 1, 64).astype(np.int64)
    points, owner = [], []
    for n in np.unique(rows):
        sel = np.nonzero(rows == n)[0]
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
        keep = i + j <= n
        w = np.stack([n - i[keep] - j[keep], i[keep], j[keep]], 1) / float(n)
        points.append(np.einsum('tcx,mc->tmx', corners[sel], w).reshape(-1, 3))
        owner.append(np.repeat(sel, len(w)))
    return np.concatenate(points), np.concatenate(owner)


def shown(points, layer, opaque, strip, nstrips):
    """What shows of each strip from outside: `points` (n, 3) on the surfaces near the strips (_samples: the strips',
    the cards' and the opaque ones'), seen from each of _views() in cells STRAND_CELL wide. A point of a strip shows
    from a direction when no opaque surface's point (opaque (n,)) lies in front of it in its cell (by more than
    STRAND_NEAR), by STRAND_COVER less for each other card layer (layer (n,): a strip, a card piece) that does: the
    strands are alpha tested, the inner layers show between those over them. strip (n,): the point's strip (-1: none)
    -> each strip's points' mean of what shows of them from their best direction (0..1)."""
    mine = strip >= 0
    best = np.zeros(int(mine.sum()))
    nl = int(layer.max()) + 1
    for d in _views():
        up = np.array([0.0, 0.0, 1.0]) if abs(d[1]) > 0.9 else np.array([0.0, 1.0, 0.0])
        x = np.cross(up, d)
        x /= np.linalg.norm(x)
        y = np.cross(d, x)
        u = np.floor(points @ x / STRAND_CELL).astype(np.int64)
        v = np.floor(points @ y / STRAND_CELL).astype(np.int64)
        z = points @ d                                   # (towards the viewer)
        cell = (u - u.min()) * int(v.max() - v.min() + 1) + (v - v.min())
        front = np.full(int(cell.max()) + 1, -np.inf)
        np.maximum.at(front, cell[opaque], z[opaque])
        # each card layer's front in each cell, the cells' layers front first: how many lie in front of a sample
        cards = ~opaque
        key, at = np.unique(cell[cards] * nl + layer[cards], return_inverse=True)
        lz = np.full(len(key), -np.inf)
        np.maximum.at(lz, at.reshape(-1), z[cards])
        lcell = key // nl
        order = np.lexsort((-lz, lcell))
        lcell, lz = lcell[order], lz[order]
        start = np.searchsorted(lcell, np.arange(len(front) + 1))
        scale = float(np.abs(lz).max() + np.abs(z).max() + 4 * STRAND_NEAR + 1.0)   # (cell, then front first, as one key)
        before = np.searchsorted(lcell * scale - lz, cell[mine] * scale - z[mine] - STRAND_NEAR) - start[cell[mine]]
        see = np.where(z[mine] >= front[cell[mine]] - STRAND_NEAR, (1.0 - STRAND_COVER) ** np.maximum(before, 0), 0.0)
        best = np.maximum(best, see)
    return np.bincount(strip[mine], best, nstrips) / np.maximum(np.bincount(strip[mine], minlength=nstrips), 1)


def drop_errors(corners, layer, opaque, strip, length):
    """Each strip's error when it is left out: STRAND_DROP x its length (length (strips,), mm) x what shows of it
    (shown(): the triangles `corners` (t, 3, 3) near the strips sampled every STRAND_STEP mm, layer, opaque, strip
    (t,) as there), peeled: a strip is judged again once those that go before it are gone, in rounds up to each of
    STRAND_PEEL mm (two inner layers each half hid the other; judged together both went and left a hole at Reina's
    nape) -> (strips,), each at least the round it went in."""
    points, owner = _samples(corners)
    layer, opaque, strip = layer[owner], opaque[owner], strip[owner]
    err = np.full(len(length), np.inf)
    keep = np.ones(len(points), bool)
    low = 0.0
    for top in STRAND_PEEL + (np.inf,):
        e = STRAND_DROP * length * shown(points[keep], layer[keep], opaque[keep], strip[keep], len(length))
        new = np.isinf(err) & (e <= top)
        err[new] = np.maximum(e[new], low)
        keep &= ~((strip >= 0) & new[np.maximum(strip, 0)])
        low = top
    return err


class _Strands:
    """A part's hair strips, reduced as strands (see Hair strands above), or its wires (Wires above): grids of wedges,
    each row's and inner column's error when it is put back (_splits), each strip's error when it is left out
    (STRAND_DROP x its length x what shows of it); one tolerance for them all keeps what is worse than it."""

    def __init__(self, grids, wpos, pos, drop, rings=False):
        """grids: [(grid (rows, columns) of wedges, rows' v, columns' u, turn)], wpos: the wedges' points, pos: the
        points' positions (mm), drop: each strip's error when left out (drop_errors()). rings: the grids are wires'
        (tubes(): rows' v = their distance along it, no u), each kept row a whole ring with every other side of six or
        more (no column's error: kept or not at any tolerance)."""
        self.grids, self.turn, self.wpos = [g for g, _, _, _ in grids], [t for _, _, _, t in grids], wpos
        self.rings = rings
        self.rows, self.cols = [], []
        for g, rv, cu, _ in grids:
            P = pos[wpos[g]]
            if rings:
                sides = g.shape[1] - 1
                keep = np.arange(sides + 1) % (2 if sides >= 6 and sides % 2 == 0 else 1) == 0
                self.rows.append(_splits(P[:, keep], rv, STRAND_LENGTH))
                self.cols.append(np.where(keep, np.inf, -1.0))
                continue
            self.rows.append(_splits(P, rv, STRAND_LENGTH))
            self.cols.append(_splits(P.transpose(1, 0, 2), cu, 0.0))
        self.drop = np.asarray(drop, np.float64)
        self.row_of = np.concatenate([np.full(len(r), i) for i, r in enumerate(self.rows)])
        self.col_of = np.concatenate([np.full(len(c), i) for i, c in enumerate(self.cols)])
        self.row_err, self.col_err = np.concatenate(self.rows), np.concatenate(self.cols)
        self.at = pos[wpos]                       # (the wedges' positions)
        errors = np.concatenate([self.row_err, self.col_err, self.drop, [0.0]])
        self.levels = np.unique(errors[np.isfinite(errors) & (errors >= 0)])
        self.tol, self.out = 0.0, 0

    def count(self, tol):
        """The wedges kept at tolerance `tol`."""
        n = len(self.grids)
        rows = np.bincount(self.row_of[self.row_err > tol], minlength=n)
        cols = np.bincount(self.col_of[self.col_err > tol], minlength=n)
        return int((rows * cols * (self.drop > tol)).sum())

    def tolerance(self, most):
        """The least tolerance that keeps at most `most` wedges (the levels it can change at)."""
        lo, hi = 0, len(self.levels) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.count(self.levels[mid]) <= most:
                hi = mid
            else:
                lo = mid + 1
        return float(self.levels[lo])

    def triangles(self, tol):
        """The strips' triangles (wedges) at tolerance `tol`: the kept rows' and columns' cells, each cut along its
        shorter diagonal, turning as the strip's did; none with two corners at one point."""
        out = []
        self.tol, self.out = tol, 0
        for g, re, ce, turn, drop in zip(self.grids, self.rows, self.cols, self.turn, self.drop):
            if drop <= tol:
                self.out += 1
                continue
            g = g[np.ix_(np.nonzero(re > tol)[0], np.nonzero(ce > tol)[0])]
            a, b, c, d = g[:-1, :-1].reshape(-1), g[:-1, 1:].reshape(-1), g[1:, :-1].reshape(-1), g[1:, 1:].reshape(-1)
            P = self.at
            short = (np.linalg.norm(P[a] - P[d], axis=1) <= np.linalg.norm(P[b] - P[c], axis=1))[:, None]
            # (in (column, row): a (0, 0), b (1, 0), c (0, 1), d (1, 1); both triangles of either cut turn +1)
            t = np.concatenate([np.where(short, np.stack([a, b, d], 1), np.stack([a, b, c], 1)),
                                np.where(short, np.stack([a, d, c], 1), np.stack([b, d, c], 1))])
            out.append(t if turn > 0 else t[:, ::-1])
        t = np.concatenate(out) if out else np.zeros((0, 3), np.int64)
        pt = self.wpos[t]
        return t[(pt[:, 0] != pt[:, 1]) & (pt[:, 1] != pt[:, 2]) & (pt[:, 0] != pt[:, 2])]

    def place(self, tri, most, mine):
        """tri (the live triangles, wedges) with the strips' triangles made again for at most `most` wedges (mine: which
        wedges are the strips')."""
        new = self.triangles(self.tolerance(most))
        return np.ascontiguousarray(np.concatenate([tri[~mine[tri[:, 0]]], new.astype(np.int32)]), np.int32)


def decimate(model, target, part_weights=None, log=print, poses=None, classes=None):
    """model: model.load_tekken7_model's dict (every prim the same vertex arrays); target: vertices at most (count()).
    poses: test poses of its skeleton ([(bones, 4, 4) changes]: skeleton.bend_poses) whose folds must be kept, or
    None. classes: {part tag: {'skin': share, 'big': share, 'small': vertices per mm, 'lying': share, 'reach': mm,
    'skin_reach': mm, 'strands': mm, 'tubes': mm}} or None: its hair cards' strips are reduced as strands, its wires
    as whole rings (see Hair strands and Wires above: with part_weights only), in that part each skin material
    (SKIN_NAMES) and each large piece (BIG_PIECE) keeps at least that share of its vertices while anything else can
    give (the floors), each small piece (SMALL_PIECE) goes down to SMALL_LEAST + that many vertices per mm of its
    length first, a point of a piece lying on the skin or another piece moves by at most that share of its height over
    it, a point of a piece not small or of the skin by at most the reaches ('lying' switches these on: see Pieces
    lying on others and Reach above), and the skin ends under the pieces on it (_skin_under: the kept skin vertices
    move). -> a new model dict: compacted streams (shared by the prims
    again), the prims' triangles on them (a prim left with none is dropped), 'parts' entries' 'first' = the part's
    first vertex in the new streams (vertex numbers of a part's own mesh, such as its sections' base vertices, no
    longer apply), 'source' = each new vertex's index in the old streams. The model itself is returned when it is
    within the target already."""
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
    rep = np.zeros(npos, np.int64)
    rep[pid] = np.arange(n)
    akey = np.concatenate([pid[:, None], np.round(nrm, 4), np.round(uv, 6), joints, np.round(weights, 4)], 1)
    wvert, wprim, ttris, tprim = [], [], [], []
    vmaps = {}                              # (the prims of parts with 'strands' or 'tubes': each vertex's wedge)
    base = 0
    for i, p in enumerate(prims):
        used = np.unique(p['tris'])
        if not len(used):
            continue
        _, first, inv = np.unique(akey[used], axis=0, return_index=True, return_inverse=True)
        vmap = np.full(n, -1, np.int64)
        vmap[used] = base + inv.reshape(-1)
        if part_weights is not None and {'strands', 'tubes'} & set((classes or {}).get(p['part']) or {}):
            vmaps[i] = vmap
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
    edge = np.linalg.norm(pos[rep[pt[:, [1, 2, 0]]]] - pos[rep[pt]], axis=2)
    scale = 1.0 / max(float(edge.mean()), 1e-12)
    ppos = np.ascontiguousarray(pos[rep] * scale, np.float64)
    if poses:
        ppose = np.ascontiguousarray(posed_points(pos[rep], s0['joints'][rep], s0['weights'][rep], poses) * scale)
    else:
        ppose = np.zeros(3)
    # attributes, per prim: UVs in the surface their texture covers, normals scaled; locks; parts
    attr = np.zeros((len(wvert), 5))
    attr[:, 2:] = nrm[wvert] * NORMAL_SCALE
    lock = np.zeros(npos, np.uint8)
    tags = sorted({p['part'] for p in prims})
    share = np.array([max(float((part_weights or {}).get(t, 1.0)), 0.0) for t in tags])
    prim_part = np.array([tags.index(p['part']) for p in prims])
    cards = []
    is_card = np.zeros(len(prims), bool)
    for i, p in enumerate(prims):
        sel = tprim == i
        if not sel.any():
            continue
        card = _is_card(p, pt[sel])
        if card:
            cards.append(p['material'])
            is_card[i] = True
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
    wpart = prim_part[wprim]
    # hair strands (Hair strands above): the strips of the parts' cards with 'strands' leave the collapses (their
    # points stay where they are; each pass makes them again for their quota)
    wstrip = np.full(len(wvert), -1, np.int64)        # the strips' wedges: their strip
    grids = []
    for i, vmap in sorted(vmaps.items()):
        if not is_card[i] or 'strands' not in classes[prims[i]['part']]:
            continue
        found, held = strips(prims[i], pid)
        if held < STRAND_SHARE:
            continue
        for g, rv, cu, turn in found:
            wstrip[vmap[g].reshape(-1)] = len(grids)
            grids.append((vmap[g], rv, cu, turn, prim_part[i]))
    strands = {}                                      # quota group -> (its _Strands, its wedges)
    if grids:
        lock[np.unique(wpos[wstrip >= 0])] = 1
        corners = pos[rep[pt]].astype(np.float64)
        box = pos[rep[wpos[wstrip >= 0]]]
        lo, hi = box.min(0) - STRAND_MARGIN, box.max(0) + STRAND_MARGIN
        near = ((corners.max(1) >= lo) & (corners.min(1) <= hi)).all(1)
        tstrip = wstrip[tri[:, 0]]
        length = np.array([np.linalg.norm(np.diff(pos[rep[wpos[g[0]]]].mean(1), axis=0), axis=1).sum() for g in grids])
        drop = drop_errors(corners[near], np.where(tstrip >= 0, tstrip, len(grids) + tprim)[near],
                           ~is_card[tprim][near], tstrip[near], length)
    # wires (Wires above): the same, whole rings
    wtube = np.full(len(wvert), -1, np.int64)         # the wires' wedges: their wire
    wires = []
    for i, vmap in sorted(vmaps.items()):
        if 'tubes' in classes[prims[i]['part']]:
            for g, along, turn in tubes(prims[i], pid, pos):
                wtube[vmap[g].reshape(-1)] = len(wires)
                wires.append((vmap[g], along, None, turn, prim_part[i]))
    if wires:
        lock[np.unique(wpos[wtube >= 0])] = 1
    # classes: a part's smooth skin and large clothing pieces were what its errors took first, while its small closed
    # pieces (beads, studs, buckles, every point on a seam) could not go below what their locks keep (Miary Zo: her
    # body at that floor, its skin 10.5k -> 680 vertices, her bikini top 1025 -> 141: the background seen between the
    # cups and the flat slab of skin behind them, faceted limbs). Each skin material and each large piece is a quota
    # group of its own with its part's weight and a floor (its 'skin' / 'big' share of its vertices: it gives no
    # more while a group above its floor can, in any part); the small pieces go down to their allowances first
    floor = np.zeros(len(tags))
    wsmall = np.full(len(wvert), -1, np.int64)       # the wedges of small pieces: their piece
    named = {}                                        # quota group -> (part tag, class) for the log
    if classes:
        piece_of, length, allowance = _small(prims, pid, npos, pos[rep], classes)
        piece = piece_of[good]
        wpiece = np.full(len(wvert), -1, np.int64)
        for c in range(3):
            wpiece[tri[:, c]] = piece
        skin = np.array([bool(SKIN_NAMES.search(p['material'])) for p in prims])[wprim]
        weight, floors = list(share), list(floor)
        for t, own in sorted(classes.items()):
            if t not in tags or share[tags.index(t)] <= 0:
                continue
            at = tags.index(t)
            inside = wpart == at
            groups = []
            if 'strands' in own and grids:            # (its hair cards' strips: no other class's)
                groups.append(('strands', own['strands'], inside & (wstrip >= 0)))
                inside &= wstrip < 0
            if 'tubes' in own and wires:              # (its wires: the same)
                groups.append(('tubes', own['tubes'], inside & (wtube >= 0)))
                inside &= wtube < 0
            if 'skin' in own:                         # (each skin material)
                groups += [('skin', own['skin'], inside & skin & (wprim == i)) for i in np.unique(wprim[inside & skin])]
            if 'big' in own:                          # (each large piece)
                big = inside & ~skin & (wpiece >= 0)
                big[big] = length[wpiece[big]] >= BIG_PIECE
                groups += [('big', own['big'], big & (wpiece == x)) for x in np.unique(wpiece[big])]
            if 'small' in own:                        # (every small piece, together: they keep their allowances)
                small = inside & ~skin & (wpiece >= 0)
                small[small] = allowance[wpiece[small]] > 0
                groups.append(('small', None, small))
                wsmall[small] = wpiece[small]
            for name, least, sel in groups:
                if not sel.any():
                    continue
                most = 0.0 if least is None else float(least) * int(sel.sum())
                if name in ('strands', 'tubes'):     # (its floor: what its tolerance keeps)
                    own_grids = grids if name == 'strands' else wires
                    mine = [x for x, g in enumerate(own_grids) if g[4] == at]
                    s = _Strands([own_grids[x][:4] for x in mine], wpos, pos[rep],
                                 drop[mine] if name == 'strands' else np.full(len(mine), np.inf), name == 'tubes')
                    strands[len(tags)] = (s, sel)
                    most = float(s.count(float(least)))
                named[len(tags)] = (t, name)
                tags.append('%s %s %d' % (t, name, len(tags)))
                weight.append(0.0 if least is None else share[at])
                floors.append(most)
                wpart[sel] = len(tags) - 1
        share, floor = np.array(weight), np.array(floors)
    wpart = np.ascontiguousarray(wpart, np.int32)
    first_sizes = _live_by_part(np.ascontiguousarray(tri, np.int32), wpart, len(tags))
    sj = np.ascontiguousarray(joints[wvert][:, :SKIN_INFLUENCES], np.int32)
    sw = np.ascontiguousarray(weights[wvert][:, :SKIN_INFLUENCES], np.float64)
    wpos32, attr = np.ascontiguousarray(wpos, np.int32), np.ascontiguousarray(attr)
    if poses:                       # the wedges' weights per skin group (the folds' rule)
        group, bend = skin_groups(model['bones'], poses)
        gw = np.zeros((len(wvert), len(bend)), np.float32)
        wj = group[s0['joints'][wvert]]
        np.add.at(gw, (np.repeat(np.arange(len(wvert)), wj.shape[1]), wj.reshape(-1)),
                  s0['weights'][wvert].reshape(-1))
        gw /= np.maximum(gw.sum(1, keepdims=True), 1e-12)
        gw, bend = np.ascontiguousarray(gw), np.ascontiguousarray(bend, np.float64)
    else:
        gw, bend = np.zeros((1, 1), np.float32), np.zeros(1)
    gmin, gmax = gw.copy(), gw.copy()   # what each wedge stands for, kept from pass to pass (a survivor's range)
    # bounds (Pieces lying on others, Reach above), in mean edge lengths. They give way when nothing else does, after
    # the floors
    bound = np.full(npos, 1e300)
    lying = 0
    if classes and any(key in own for own in classes.values() for key in ('lying', 'reach', 'skin_reach')):
        mm = _bounds(prims, pid, npos, pos, nrm, classes, set(cards), piece_of, length)
        lying = int(np.isfinite(mm).sum())
        bound[np.isfinite(mm)] = mm[np.isfinite(mm)] * scale
    dev = np.zeros(npos)
    bounded = lying > 0
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
    if model.get('free') is not None:   # (hidden surfaces, covered.mark: taken first, at no bound; off without a definition's)
        used = np.unique(np.concatenate([p['tris'].reshape(-1) for p in prims]))
        free_point = np.ones(npos, bool)
        np.logical_and.at(free_point, pid[used], model['free'][used])
        pfactor[free_point] *= FREE_COST
        bound[free_point] = 1e300
    tri32 = np.ascontiguousarray(tri, np.int32)
    stats, collapses = np.zeros(_STATS), 0
    lib = _core()
    stuck = share <= 0              # parts that keep what they have
    corner, flip = CORNER_COS, FLIP_COS
    step = np.full(len(tags), FOLD_STEP if poses else 1e300)     # each part's step in the folds' rule
    if (wsmall >= 0).any():
        # the small pieces first, alone, each to its allowance (its own quota; everything else keeps its own), the
        # corners of a triangle's normals free to point apart (NORMAL_COS: a bead's rounding is what goes); then
        # they keep what they have
        ids, inv = np.unique(wsmall[wsmall >= 0], return_inverse=True)
        alone = wpart.copy()
        alone[wsmall >= 0] = len(tags) + inv.reshape(-1)
        alone = np.ascontiguousarray(alone, np.int32)
        sizes = _live_by_part(tri32, alone, len(tags) + len(ids))
        quota = sizes.copy()
        quota[len(tags):] = np.minimum(allowance[ids], sizes[len(tags):])
        params = np.array([FEATURE_WEIGHT, flip, corner, SKIN_WEIGHT, REGULAR, 1e300, -1.0, POSE_WEIGHT], np.float64)
        got = lib.ttt2_decimate(npos, ppos, len(wvert), wpos32, attr.shape[1], attr, sj, sw, wnrm, pfactor, lock,
                                len(tri32), tri32, alone, len(quota), quota, params, int(quota.sum()), stats,
                                len(poses) if poses else 0, ppose, gw.shape[1] if poses else 0, gw, gmin, gmax, bend,
                                np.full(len(quota), 1e300), bound, dev)
        if got < 0:
            raise MemoryError('decimate: out of memory')
        collapses += int(stats[0])
        tri32 = np.ascontiguousarray(tri32[tri32[:, 0] >= 0])
    for _ in range(PASSES + 4):
        sizes = _live_by_part(tri32, wpart, len(tags))
        if sizes.sum() <= target:
            break
        if part_weights is None:
            quota = np.zeros(len(tags), np.int64)
        else:
            quota = _quotas(sizes, share, target, stuck, np.minimum(floor, sizes))
        for g, (s, mine) in strands.items():         # (the strands made for their quota; the collapses leave them)
            tri32 = s.place(tri32, int(quota[g]), mine)
        params = np.array([FEATURE_WEIGHT, flip, corner, SKIN_WEIGHT, REGULAR, 1e300, NORMAL_COS, POSE_WEIGHT],
                          np.float64)
        got = lib.ttt2_decimate(npos, ppos, len(wvert), wpos32, attr.shape[1], attr, sj, sw, wnrm, pfactor, lock,
                                len(tri32), tri32, wpart, len(tags), quota, params, int(target), stats,
                                len(poses) if poses else 0, ppose, gw.shape[1] if poses else 0, gw, gmin, gmax, bend,
                                step, bound if bounded else np.full(npos, 1e300), dev)
        if got < 0:
            raise MemoryError('decimate: out of memory')
        collapses += int(stats[0])
        tri32 = np.ascontiguousarray(tri32[tri32[:, 0] >= 0])
        now = _live_by_part(tri32, wpart, len(tags))
        stuck |= now > quota            # could not get there: the others give up more
        if got > target and (stuck | (now <= floor)).all() and floor.any():
            log('  decimate: %d vertices left with the classes\' floors kept; going on without' % got)
            floor[:] = 0.0
            stuck = share <= 0
        elif got > target and stuck.all() and bounded:
            log('  decimate: %d vertices left with the pieces lying on others kept on them; going on without' % got)
            bounded = False
            stuck = share <= 0
        elif got > target and stuck.all() and step[0] < 1e300:
            step[:] = step[0] * 2 if step[0] * 2 < 1.0 else 1e300
            log('  decimate: %d vertices left with the folds kept; going on %s' % (
                got, 'without them' if step[0] >= 1e300 else 'with a step of %.2f' % step[0]))
            stuck = share <= 0
        elif got > target and stuck.all() and corner == CORNER_COS:
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
    if classes and any(own.get('lying') is not None for own in classes.values()):
        _skin_under(streams, new_prims, kept, pid, prims, pos, nrm, classes, set(cards), log)
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
    if named:                           # (the classes: wedges, as the quotas count them)
        last = _live_by_part(tri32, wpart, len(tags))
        sums = {}
        for c, key in named.items():
            sums.setdefault(key, [0, 0, 0])
            sums[key][0] += int(first_sizes[c])
            sums[key][1] += int(last[c])
            sums[key][2] += 1
        log('  decimate: classes %s%s' % (', '.join('%s %s %d -> %d%s' % (
            t, name, a, b, ' (%d pieces)' % m if name == 'big' else '') for (t, name), (a, b, m) in sorted(sums.items())),
            '; %d points bounded' % lying if lying else ''))
    for g, (s, mine) in strands.items():
        if s.rings:
            log('  decimate: %s wires: %d tubes, rings within %.1f mm' % (named[g][0], len(s.grids), s.tol))
        else:
            log('  decimate: %s strands: %d strips, rows and columns within %.1f mm, %d strips left out' % (
                named[g][0], len(s.grids), s.tol, s.out))
    if dropped:
        log('  decimate: %d degenerate triangles left out' % dropped)
    if after > target:
        log('  WARNING: decimate could not get the model under %d vertices (%d)' % (target, after))
    return out
