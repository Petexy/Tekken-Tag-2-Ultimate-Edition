"""Cloth Tekken 7 simulates -> swinging chains of extra bones, like Lars Alexandersson's coat tails.

Tekken 7 simulates the cloth of a costume part with APEX (tekken7/apex.py: Claudio's and Katarina's coats, Leroy's
jacket, Master Raven's ribbons, Shaheen's robe and headscarf); its skinned copy, all the port drew, stays rigid on the
body. TTT2 has no cloth simulation for fighters: Lars's coat tails (lar_upb_1p_mantle) are nine chains of six extra
bones `cha:OPT110_..` hanging from MUNE2_jnt, each link along the bone's local +X (down), local Y facing away from
the body, Z = X x Y; their spring entries (flag 0x60: angle limits) and the coat's capsules round his shins and thighs
are in the part's spring file, with which bones touch which capsule and links between neighbouring chains (mop
layout below). So for each clothing asset whose vertices may move at least FREE_MIN:
* the physical mesh's vertices with max distance 0 are pinned; the others hang from them: geodesic distance g from
  the pinned ones (along the mesh's edges) and the pinned vertex each hangs from;
* chains start along the line the cloth hangs from, SPACING apart (each free vertex belongs to the chain whose root
  is nearest the vertex it hangs from); a chain's bones sit LINK apart in g, each at the mean of its vertices there;
  chains whose vertices touch are neighbours;
* chains tilted more than FLOWING from straight down, root to tip (cloth modelled flowing: Master Raven's ribbons,
  Shaheen's headscarf, Claudio's arm band) hang HANG from straight down, kept MARGIN outside the body; the vertices
  follow (chains.drape); cloth modelled hanging (coats flaring out) keeps its shape;
* the drawn section's vertices are skinned like Lars's coat: two neighbouring chains by distance, the two bones of
  the nearest link along them; over BLEND below the pinned line they keep some of their own weights;
* posed in the fighter's standing pose, links reaching into a thigh or shin turn outward till they hang
  SETTLE_MARGIN outside it (settle: a round starts with the cloth at rest, and the game pushes bones crossing a
  capsule's surface, not bones inside it); the vertices follow;
* the bones join the skeleton as `cha:OPT<n>_cloth<c>_<chain>_<link>` from OPT_FIRST (the first one's parent: the
  TTT2 bone the cloth's own weights near it go to) and the spring file gets an entry per bone (Lars's coat entry for
  the same link, the length its own, swinging out up to OUTWARD; in no further than its rest if settle draped it),
  capsules fitted to the fighter's hips, thighs, shins, belly and chest (BODY: the body's vertices nearest each
  piece, the ellipsoid their extents along the bone's axes span, CAPSULE_MARGIN round, LEG_MARGIN round the hips and
  legs), pairs (every bone but a chain's top below the chest with the hips and legs, kicks reach anywhere, and with
  the belly or chest when near; none for chains hung from an arm), each capsule as thick as reaches the nearest of
  its cloth bones at rest (TOUCH), and links between neighbouring chains (Lars's values).
Tekken 8's strands (tekken8/cloth.py: the cords and strap ends its Catwalk Cloth swings) come in as such cloths too,
each with its own link length, shortest chain and how it hangs.

The spring file (big-endian), as the game's files have it (1572 of its 1607 spring files read this way to the byte):
    f32 5.0, 28 zero bytes | u32 entry count, 12 zero bytes | entries of 0x60 bytes: u32 OPT number, 11 f32
    (Lars's coat: 30, 10, 70, length to the next bone in mm, angle limits about local Y +/-, about local Z (toward
    +Y = away from the body / toward -Y), 1, 1, 0.05), u32 flags at 0x30, u32 pair count at 0x34, u32 link count at
    0x38, .. | u32 capsule count, 12 zero bytes | capsules of 0x50 bytes: u32 1 (an ellipsoid), u32 bone index, f32
    0, 0, rotation x y z, 0, offset x y z (mm in the bone's frame), 0, sizes along x y z (half axes, mm), 5 x 0 | the
    entries' pairs in entry order, 16 bytes each: u32 OPT number, u32 capsule index, 8 zero bytes | the entries'
    links in entry order, 52 bytes each: u32 OPT number, u32 the other chain's OPT number, f32 0.8, f32 50/80/150,
    36 zero bytes.

Written for this project from the files themselves (no third-party code).
"""
import heapq
import re
import struct

import numpy as np

from ..tekken7 import apex
from ..tekken7.uasset import load
from ..ttt2 import animation, archive, bone
from . import chains as hanging, skeleton

OPT_FIRST = 400                 # the first cloth bone's number (hair chains 300.., the tiger 600.., weapons 800..)
OPT_END = 600
FREE_MIN = 25.0                 # cm: a cloth moving less than this only wobbles (trousers, sleeves): left skinned
PINNED = 0.5                    # cm: a vertex allowed to move no further than this is pinned to the body
SPACING = 120.0                 # mm: chains start 1/2..1 of this apart (Lars's coat: 60..140)
LINK = 150.0                    # mm between a chain's bones (Lars's: 180..270; the cloth between two bones goes
                                # through what it meets: closer bones clip less)
FLOWING = np.radians(30.0)      # a chain tilted more than this from straight down was modelled flowing: it hangs
HANG = np.radians(5.0)          # ... this far from straight down
REACH = 150.0                   # mm: shorter chains are left out (sleeve ends)
MARGIN = 15.0                   # mm the draped chains keep outside the body
BLEND = 40.0                    # mm below the pinned line over which the cloth's own skin weights give way
MAX_BONES = 100                 # cloth bones of a fighter
SKELETON = 249                  # bones of a fighter's skeleton at most: the most a skeleton of the game's own has
NAME = 'cloth%d_%d_%d'          # the bones' names: (cloth, chain, link)
_NAMED = re.compile(r'cha:OPT(\d+)_cloth(\d+)_(\d+)_(\d+)$')

# Lars's coat tails' spring file: his `mop` pack (lar_upb_1p_mantle, pi 8); the chain at his back's centre is the
# entry template (OPT 110 its top bone .. 115)
TEMPLATE = (0x66C4E6AD, 8)
TEMPLATE_FIRST = 110
TEMPLATE_LINKS = 6
RELATION_STIFFNESS = 0.8
RELATION_VALUES = (50.0, 80.0, 150.0)       # by link: the top, the next, the rest
LIMBS = ('SAKOTSU', 'KENKO', 'KATA', 'HIJI', 'UDE', 'TE_', 'slide_')   # chains hung from an arm touch no capsule
# the body's capsules (ellipsoids) the cloth keeps out of, fitted to the fighter's own body: a bone, the joints its
# piece of the body reaches to and how far from it its vertices may be (mm: what hangs further from a leg, a coat's
# front edge, is not the leg); the body's vertices go to the nearest piece, OTHER pieces only take theirs away
BODY = [('KOSHI_jnt', ('MOMO_R_jnt', 'MOMO_L_jnt'), 250.0), ('MOMO_R_jnt', ('HIZA_R_jnt',), 150.0),
        ('MOMO_L_jnt', ('HIZA_L_jnt',), 150.0), ('HIZA_R_jnt', ('ASHI_R_jnt',), 130.0),
        ('HIZA_L_jnt', ('ASHI_L_jnt',), 130.0), ('MUNE1_jnt', ('MUNE2_jnt',), 250.0),
        ('MUNE2_jnt', ('KUBI_jnt',), 250.0)]
LEGS = 5                        # the first BODY pieces: hips, thighs, shins (kicks take them anywhere near the cloth)
LIMB = (1, 2, 3, 4)             # pieces along a limb: as long as it, as thick as its middle (LIMB_MIDDLE of its length)
LIMB_MIDDLE = (0.2, 0.9)
OTHER = [(a % s, b % s) for s in 'RL' for a, b in (('SAKOTSU_%s_jnt', 'KATA_%s_jnt'), ('KATA_%s_jnt', 'UDE_%s_jnt'),
                                                    ('UDE_%s_jnt', 'TE_%s_jnt'), ('ASHI_%s_jnt', 'TSUMASAKI_%s_jnt'))]
OTHER += [('KUBI_jnt', 'ATAMA_jnt')]
FIT = 90.0                      # the percentile of a piece's vertices along each of its bone's axes (both ways) ..
FIT_SHARE = 0.95                # .. a round piece's surface reaches this share of its radius at
CAPSULE_MARGIN = 20.0           # mm added round them (Miharu's skirt: her thighs' ~90 mm radius, capsules 110) ..
LEG_MARGIN = 30.0               # .. round the hips and legs (then scaled to touch the cloth: TOUCH below): the cloth
                                # between two bones touches nothing, and legs reach it before its bones
TRUNK_REACH = 2.5               # bones within this many of a trunk capsule's own sizes touch it
# The game pushes a bone out of a capsule where the bone crosses its surface; a bone wholly inside is not pushed (a
# 300 mm sphere round the hips holding Master Raven's ribbons moved nothing), so a leg that swallows a link in one
# frame goes through the cloth. Lars's coat rests on his 200..300 mm leg capsules: always touching, pushed as soon as
# a leg moves. So each capsule's thickness is scaled till its surface reaches the nearest cloth bone it touches at
# rest (TOUCH: 1 = on it), within SHRINK..GROW of the body's own
TOUCH = 1.0
SHRINK = 0.8
GROW = 3.0
# A round starts with the cloth bones at rest on their parents, the fighter standing: cloth hanging straight down
# where a thigh comes forward (Leroy's jacket) starts inside its capsule and stays there. So the chains are posed in
# the fighter's standing pose (its standing move's first frame) and each link reaching into a thigh or shin capsule
# turns outward (SETTLE_STEP at a time, up to SETTLE_MAX) till it hangs SETTLE_MARGIN outside the leg capsules (as
# fitted, before TOUCH), at its points SETTLE_ALONG it (the cloth between two bones is straight); their rest is that.
# (A cushion beyond the capsules floated Claudio's coat off him: the user disliked it.)
SETTLE_MARGIN = 0.0
SETTLE_ALONG = (1 / 3, 2 / 3, 1.0)
SETTLE_STEP = np.radians(2.0)
SETTLE_MAX = np.radians(90.0)
# how far a chain touching capsules may swing out (about local Z, toward +Y: away from the body; rad): Lars's coat's
# top links swing out 0.2..0.3, too little for a leg to push the cloth off it (Feng Wei's jacket: up to 1.6); its
# other limits stay. Chains hung from an arm keep Lars's
OUTWARD = 1.2
# chains draped off a leg (settle) swing no further in than their rest: the old capsules are thicker than the leg, so
# their rest lies inside them, where the game leaves a bone be, and Lars's limits let cloth sag in (0.04..0.9 rad):
# Leroy's front panel sagged back into his thigh standing still. Like Feng Wei's jacket (0), for these chains only
DRAPED_INWARD = 0.0

MOP_COUNT, MOP_ENTRIES, MOP_ENTRY, MOP_CAPSULE, MOP_PAIR, MOP_LINK = 0x20, 0x30, 0x60, 0x50, 16, 52


def _points(v):
    """Tekken 7 centimetres (x, y, z), Z up -> TTT2 millimetres (x, z, y)."""
    return np.stack([v[:, 0], v[:, 2], v[:, 1]], 1) * 10.0


def find(paks, k, parts, log=print):
    """The cloth of the costume's parts Tekken 7 simulates and that hangs: [{'part', 'asset' (apex.Asset),
    'vertices' (the drawn vertices in k's streams)}]. parts: [(tag, path)] as load_tekken7_model had them."""
    out = []
    for tag, path in parts:
        sk = k['parts'].get(tag)
        if sk is None:
            continue
        sections = sk['mesh'].lods[0].sections
        if not any(s.cloth_mapping for s in sections):
            continue
        assets = apex.assets(load(paks, path).data)
        by_asset = {}
        for s in sections:
            if not s.disabled or not 0 <= s.cloth_section < len(sections):
                continue
            a = sections[s.cloth_section].cloth_asset
            if 0 <= a < len(assets):
                by_asset.setdefault(a, []).append(np.arange(s.num_vertices) + s.base_vertex + sk['first'])
        for a, ranges in sorted(by_asset.items()):
            asset = assets[a]
            free = float(asset.max_distance.max())
            if free < FREE_MIN:
                log('  %s cloth %d: moves up to %.0f cm, left skinned' % (tag, a, free))
                continue
            out.append(dict(part=tag, asset=asset, vertices=np.concatenate(ranges), name='%s cloth %d' % (tag, a)))
    return out


def _edges(triangles, n):
    e = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    adjacency = [[] for _ in range(n)]
    for a, b in e:
        adjacency[a].append(b)
        adjacency[b].append(a)
    return e, adjacency


def _hang(points, pinned, adjacency):
    """Geodesic distance from the pinned vertices along the mesh, and the pinned vertex each vertex hangs from."""
    g = np.full(len(points), np.inf)
    source = np.full(len(points), -1, np.int64)
    heap = []
    for v in np.nonzero(pinned)[0]:
        g[v], source[v] = 0.0, v
        heap.append((0.0, int(v)))
    heapq.heapify(heap)
    while heap:
        d, v = heapq.heappop(heap)
        if d > g[v]:
            continue
        for u in adjacency[v]:
            nd = d + float(np.linalg.norm(points[u] - points[v]))
            if nd < g[u]:
                g[u], source[u] = nd, source[v]
                heapq.heappush(heap, (nd, int(u)))
    return g, source


def _spread(points, spacing):
    """Indices of points at least about `spacing` apart covering them all (farthest point sampling)."""
    if not len(points):
        return []
    chosen = [int(np.lexsort(points.T[::-1])[0])]
    d = np.linalg.norm(points - points[chosen[0]], axis=1)
    while d.max() > spacing:
        chosen.append(int(d.argmax()))
        d = np.minimum(d, np.linalg.norm(points - points[chosen[-1]], axis=1))
    return chosen


def _nearest(a, b, chunk=2048):
    """For each point of a, the index of the nearest point of b and the distance."""
    index = np.empty(len(a), np.int64)
    dist = np.empty(len(a))
    for s in range(0, len(a), chunk):
        d = ((a[s:s + chunk, None, :] - b[None, :, :]) ** 2).sum(-1)
        index[s:s + chunk] = d.argmin(1)
        dist[s:s + chunk] = np.sqrt(d[np.arange(len(index[s:s + chunk])), index[s:s + chunk]])
    return index, dist


def _on_polyline(p, nodes):
    """Distance from points p to the polyline through nodes, and per point the segment and the place along it."""
    if len(nodes) == 1:
        return np.linalg.norm(p - nodes[0], axis=1), np.zeros(len(p), np.int64), np.zeros(len(p))
    best = np.full(len(p), np.inf)
    seg = np.zeros(len(p), np.int64)
    at = np.zeros(len(p))
    for i in range(len(nodes) - 1):
        a, ab = nodes[i], nodes[i + 1] - nodes[i]
        t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-9), 0, 1)
        d = np.linalg.norm(p - (a + t[:, None] * ab), axis=1)
        better = d < best
        best[better], seg[better], at[better] = d[better], i, t[better]
    return best, seg, at


def _anatomical(k, b):
    """The nearest of bone b and its ancestors that is a body joint (not a cloth or physics bone)."""
    names, parents = k['bones']['names'], k['bones']['parents']
    while b >= 0 and skeleton.t7_weight_target(names[b], None) is None:
        b = parents[b]
    return b


def _frame(x, outward):
    x = x / max(np.linalg.norm(x), 1e-9)
    y = outward - x * float(outward @ x)
    if np.linalg.norm(y) < 1e-6:
        y = np.cross(x, [0.0, 0.0, 1.0] if abs(x[2]) < 0.9 else [1.0, 0.0, 0.0])
    y = y / np.linalg.norm(y)
    return np.stack([x, y, np.cross(x, y)], 1)


def _drape(nodes, body, normals, flowing=FLOWING, down=None):
    """Link directions for the chain through nodes if it was modelled flowing (tilted more than `flowing` from
    straight down, root to tip): HANG from straight down toward where it flowed, the bones kept MARGIN outside the
    body (points, outward normals). None for a chain modelled hanging. down: another way to hang (a unit vector:
    along an arm, for a Tekken 8 strand hung from one)."""
    down = np.array([0.0, -1.0, 0.0]) if down is None else np.asarray(down, np.float64)
    whole = nodes[-1] - nodes[0]
    if float(np.arccos(np.clip(whole @ down / max(np.linalg.norm(whole), 1e-9), -1, 1))) <= flowing:
        return None
    side = whole - down * float(whole @ down)
    side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-6 else np.array([0.0, 0.0, -1.0])
    hang = down * np.cos(HANG) + side * np.sin(HANG)
    out, dirs = [nodes[0]], []
    for i in range(len(nodes) - 1):
        length = float(np.linalg.norm(nodes[i + 1] - nodes[i]))
        d = hang
        for _ in range(4):                       # (keeping the link's length gives back some of each push)
            p = out[-1] + length * d
            q, _ = _nearest(p[None], body)
            depth = float((p - body[q[0]]) @ normals[q[0]])
            if depth >= MARGIN - 0.5:
                break
            p = p + (MARGIN - depth) * normals[q[0]]
            d = (p - out[-1]) / max(np.linalg.norm(p - out[-1]), 1e-9)
        dirs.append(d)
        out.append(out[-1] + length * d)
    return dirs


def rig(k, cloths, log=print, spacing=SPACING, link=LINK):
    """Adds the cloth's chains to k: bones `cloth<c>_<chain>_<link>` after its Tekken 7 bones (bind frames in TTT2
    space), the drawn vertices skinned to them, the chains draped. A cloth's own 'link' and 'reach' (mm), 'flowing'
    and 'down' (_drape's; Tekken 8's strands: tekken8/cloth.py) stand for LINK, REACH, FLOWING and straight down
    (`link` scales its link as it scales LINK). -> [{'part', 'bones' (k bone indices), 'neighbours' (chain
    numbers)}] in chain number order."""
    s0 = k['prims'][0]
    pos, nrm, joints, weights = s0['pos'], s0['nrm'], s0['joints'], s0['weights']
    names, parents = list(k['bones']['names']), list(k['bones']['parents'])
    world = list(k['bones']['world'])
    cloth_vertices = np.zeros(len(pos), bool)
    for c in cloths:
        cloth_vertices[c['vertices']] = True
    used = np.unique(np.concatenate([p['tris'].reshape(-1) for p in k['prims']]))
    body = used[~cloth_vertices[used]]
    body_pos, body_nrm = pos[body], nrm[body]
    out, drapes = [], []
    for ci, c in enumerate(cloths):
        a = c['asset']
        shortest = c.get('reach', REACH)
        step = link * c['link'] / LINK if 'link' in c else link
        sim = _points(a.vertices)
        n = len(sim)
        pinned = a.max_distance <= PINNED
        if not pinned.any():
            pinned = a.max_distance <= np.quantile(a.max_distance, 0.05)
        _, adjacency = _edges(a.triangles, n)
        g, source = _hang(sim, pinned, adjacency)
        free = ~pinned & np.isfinite(g)
        if not free.any():
            continue
        attach = np.unique(source[free])
        roots = attach[_spread(sim[attach], spacing / 2)]
        # chains: each free vertex with the root nearest the vertex it hangs from; short ones left out
        for _ in range(2):
            ri, rd = _nearest(sim[source], sim[roots])
            chain = np.where(free & (rd <= 1.5 * spacing), ri, -1)
            reach = np.array([g[chain == r].max() if (chain == r).any() else 0.0 for r in range(len(roots))])
            keep = reach >= shortest
            if keep.all() or not keep.any():
                break
            roots = roots[keep]
        chains = [np.nonzero(chain == r)[0] for r in range(len(roots))]
        # the drawn vertices: where they are on the physical mesh
        drawn = c['vertices']
        near, _ = _nearest(pos[drawn], sim)
        dg = g[near]
        dchain = chain[near]
        first = len(out)
        made = []
        for r, members in enumerate(chains):
            reach = float(g[members].max()) if len(members) else 0.0
            if reach < shortest:
                made.append(None)
                continue
            levels = list(np.arange(0.0, reach - step / 3, step)[1:]) + [reach]
            nodes = [sim[source[members]].mean(0)]
            for j, lv in enumerate(levels):
                lo = lv - step / 2 if j + 1 < len(levels) else lv - step / 3
                band = members[(g[members] >= lo) & (g[members] <= lv + step / 2)]
                if not len(band):
                    break
                nodes.append(sim[band].mean(0))
            nodes = np.array(nodes)
            if len(nodes) < 2:
                made.append(None)
                continue
            # the root's parent: the bone the drawn vertices pinned next to it are mostly skinned to
            pin = drawn[(dg <= 0) & (np.linalg.norm(pos[drawn] - nodes[0], axis=1) <= spacing)]
            if not len(pin):
                pin = drawn[np.argsort(np.linalg.norm(pos[drawn] - nodes[0], axis=1))[:8]]
            acc = np.zeros(len(names))
            np.add.at(acc, joints[pin].reshape(-1), weights[pin].reshape(-1))
            parent = int(acc[:len(k['bones']['names'])].argmax())
            axis = world[_anatomical(k, parent)][:3, 3]
            bones = []
            for j, p in enumerate(nodes):
                x = nodes[j + 1] - p if j + 1 < len(nodes) else p - nodes[j - 1]
                outward = p - axis
                outward[1] = 0.0
                m = np.eye(4)
                m[:3, :3] = _frame(x, outward)
                m[:3, 3] = p
                bones.append(len(names))
                names.append(NAME % (ci, len(out), j))
                parents.append(parent if j == 0 else bones[-2])
                world.append(m)
            made.append((len(out), nodes, bones))
            out.append(dict(part=c['part'], bones=bones, neighbours=set(), parent=parent))
        number = {r: m[0] for r, m in enumerate(made) if m is not None}
        # neighbours: chains whose vertices share edges
        e, _ = _edges(a.triangles, n)
        ca, cb = chain[e[:, 0]], chain[e[:, 1]]
        touch = {}
        for x, y in zip(ca, cb):
            if x != y and x >= 0 and y >= 0 and x in number and y in number:
                key = (min(number[x], number[y]), max(number[x], number[y]))
                touch[key] = touch.get(key, 0) + 1
        for (x, y), count in touch.items():
            if count >= 2:
                out[x]['neighbours'].add(y)
                out[y]['neighbours'].add(x)
        # skin weights: the two nearest neighbouring chains, the two bones of the nearest link of each
        lines = {m[0]: m[1] for m in made if m is not None}
        bones_of = {m[0]: m[2] for m in made if m is not None}
        moved = 0
        for chain_r, own in number.items():
            sel = np.nonzero((dchain == chain_r) & (dg > 0))[0]
            if not len(sel):
                continue
            v = drawn[sel]
            p = pos[v]
            d1, seg1, t1 = _on_polyline(p, lines[own])
            best2 = np.full(len(v), np.inf)
            other = np.full(len(v), -1)
            seg2, t2 = np.zeros(len(v), np.int64), np.zeros(len(v))
            for nb in out[own]['neighbours']:
                d, s_, t_ = _on_polyline(p, lines[nb])
                better = d < best2
                best2[better], other[better], seg2[better], t2[better] = d[better], nb, s_[better], t_[better]
            near2 = (other >= 0) & (best2 < 2 * spacing)
            d2 = np.where(near2, best2, 0.0)
            lateral = np.where(near2, d2 / np.maximum(d1 + d2, 1e-9), 1.0)
            blend = np.clip(dg[sel] / BLEND, 0, 1)
            for i, vi in enumerate(v):
                acc = {}
                b1 = bones_of[own]
                for bb, w in ((b1[seg1[i]], 1 - t1[i]), (b1[seg1[i] + 1], t1[i])):
                    acc[bb] = acc.get(bb, 0.0) + w * lateral[i] * blend[i]
                if lateral[i] < 1.0:
                    b2 = bones_of[other[i]]
                    for bb, w in ((b2[seg2[i]], 1 - t2[i]), (b2[seg2[i] + 1], t2[i])):
                        acc[bb] = acc.get(bb, 0.0) + w * (1 - lateral[i]) * blend[i]
                if blend[i] < 1.0:
                    own_w = sorted(((float(w), int(j)) for j, w in zip(joints[vi], weights[vi]) if w > 0),
                                   reverse=True)[:4]
                    total = sum(w for w, _ in own_w)
                    for w, j in own_w:
                        acc[j] = acc.get(j, 0.0) + w / total * (1 - blend[i])
                top = sorted(acc.items(), key=lambda x: -x[1])[:joints.shape[1]]
                total = sum(w for _, w in top)
                joints[vi] = 0
                weights[vi] = 0.0
                for q, (j, w) in enumerate(top):
                    joints[vi, q] = j
                    weights[vi, q] = w / total
                moved += 1
        drapes += [(bones_of[m[0]], m[1], c.get('flowing', FLOWING), c.get('down')) for m in made if m is not None]
        log('  %s: %d chains (%s bones) hang from %s; %d vertices skinned to them' % (
            c['name'], len(number), '+'.join(str(len(bones_of[x])) for x in sorted(bones_of)),
            ', '.join(sorted({names[out[x]['parent']].split('@')[0] for x in bones_of})), moved))
    k['bones']['names'], k['bones']['parents'] = names, parents
    k['bones']['world'] = np.array(world)
    draped = []
    for bones, nodes, flowing, down in drapes:
        dirs = _drape(nodes, body_pos, body_nrm, flowing, down)
        if dirs is not None:
            draped.append((bones, dirs))
    if draped:
        moved = hanging.drape(k, draped)
        log('  cloth modelled flowing: %d chains hang (%d vertices moved)' % (len(draped), moved))
    return out


def add(k, cloths, room=MAX_BONES, log=print):
    """rig() with chains far enough apart that the fighter gets at most `room` (and MAX_BONES) cloth bones."""
    s0 = k['prims'][0]
    saved = ({key: list(v) if isinstance(v, list) else v.copy() for key, v in k['bones'].items()},
             {key: s0[key].copy() for key in ('pos', 'nrm', 'tan', 'joints', 'weights')})
    scale = 1.0
    while True:
        lines = []
        chains = rig(k, cloths, lines.append, SPACING * scale, LINK * min(scale, 1.5))
        count = sum(len(c['bones']) for c in chains)
        if count <= min(room, MAX_BONES, OPT_END - OPT_FIRST):
            break
        if scale > 4:
            log('  cloth: no room for its bones (%d, room for %d): left skinned' % (count, room))
            k['bones'] = saved[0]
            for key, v in saved[1].items():
                s0[key][...] = v
            return []
        k['bones'] = {key: list(v) if isinstance(v, list) else v.copy() for key, v in saved[0].items()}
        for key, v in saved[1].items():
            s0[key][...] = v
        scale *= 1.25
    for line in lines:
        log(line)
    if scale > 1:
        log('  cloth: chains %.0f mm apart (%d bones; room for %d)' % (SPACING * scale, count, min(room, MAX_BONES)))
    return chains


def _segment_distance(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-9), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def capsules(skel, body):
    """The body's capsules (BODY) fitted to its vertices (body: (n, 3) bind positions, mm): [(bone index, offset,
    sizes)] in the bone's frame (its local axes, mm)."""
    world = bone.world_matrices(skel)
    names = list(skel['names'])
    at = {n[4:]: world[i][:3, 3] for i, n in enumerate(names) if n.startswith('cha:')}
    pieces = [(at[b], np.mean([at[e] for e in ends], 0)) for b, ends, _ in BODY] + [(at[a], at[b]) for a, b in OTHER]
    d = np.stack([_segment_distance(body, a, b) for a, b in pieces], 1)
    piece = d.argmin(1)
    out = []
    for i, (b, _, reach) in enumerate(BODY):
        m = world[names.index('cha:' + b)]
        rot = m[:3, :3] / np.linalg.norm(m[:3, :3], axis=0)
        a, e = pieces[i]
        along = ((body - a) @ (e - a)) / max(float((e - a) @ (e - a)), 1e-9)
        keep = (piece == i) & (d[:, i] < reach)
        if i in LIMB:
            keep &= (along >= LIMB_MIDDLE[0]) & (along <= LIMB_MIDDLE[1])
        if keep.sum() < 20:
            continue
        local = (body[keep] - m[:3, 3]) @ rot
        lo, hi = np.percentile(local, 100 - FIT, 0), np.percentile(local, FIT, 0)
        margin = LEG_MARGIN if i < LEGS else CAPSULE_MARGIN
        offset, size = (lo + hi) / 2, (hi - lo) / 2 / FIT_SHARE + margin
        if i in LIMB:                            # (its length the bones'; its local X runs along it)
            ends = (np.array([0.0, 1.0])[:, None] * (e - a) + a - m[:3, 3]) @ rot
            offset[0], size[0] = ends[:, 0].mean(), abs(ends[1, 0] - ends[0, 0]) / 2 + CAPSULE_MARGIN
        out.append((names.index('cha:' + b), offset, size))
    return out


def standing(moveset):
    """The fighter's standing pose: (channel values, animation type) of the first frame of its standing move's
    animation (alias 0x8000) in a Tekken 7 moveset (tkmvst.read); None if it has none."""
    try:
        at = moveset.tables['moves'][moveset.aliases[0]]['anim']
        return animation.decode_frame(moveset.animbuf, 0, '<', at), animation.header(moveset.animbuf, '<', at)['type']
    except (IndexError, KeyError, ValueError, struct.error):
        return None


def pose(skel, still):
    """World matrices of skel posed by one animation frame (standing()): the body channels' rotations, the hips
    where channel 1 puts them; the other bones at rest on their parents."""
    values, kind = still
    channel = {b: c for c, b in enumerate(animation.BODY_BONES) if b >= 0}
    out = []
    for i, p in enumerate(skel['parent']):
        m = bone.local_matrix(skel, i)
        if i in channel and channel[i] < len(values):
            m[:3, :3] = animation.local_rotation(np.asarray(values[channel[i]], np.float64), kind)
        if i == 0:
            m[:3, 3] = np.asarray(values[1], np.float64) * (1, 1, -1)   # (the game negates the body's z)
        out.append(m if p < 0 else out[p] @ m)
    return np.array(out)


def _turn(axis, angle):
    x, y, z = axis
    c, s = np.cos(angle), np.sin(angle)
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + s * k + (1 - c) * k @ k


def settle(k, chains, skel, parents, still, body):
    """Turns the chains' links that reach into a leg in the standing pose (still: standing()) outward till they hang
    SETTLE_MARGIN outside the thigh and shin capsules and the knees (skel: the fighter's skeleton without the chains,
    parents: each chain's parent in it, body: as springs()); only cloth closed round the leg (a chain with neighbours
    on both sides): a leg passes through an opening (Claudio's open coat) by its edges unseen; the vertices follow.
    Changes k's bind matrices and vertex streams in place. -> (links turned, vertices moved)."""
    names = list(skel['names'])
    bind, posed = bone.world_matrices(skel), pose(skel, still)
    limbs = [BODY[i][0] for i in LIMB]
    legs = []
    for b, offset, size in capsules(skel, body):
        if names[b][4:] in limbs:
            m = posed[b]
            legs.append((m[:3, 3], m[:3, :3] / np.linalg.norm(m[:3, :3], axis=0), offset, size + SETTLE_MARGIN))
            if names[b][4:8] == 'MOMO':              # (and a ball round the knee, as thick as the thigh: the
                knee = posed[names.index(names[b].replace('MOMO', 'HIZA'))]   # thigh's and shin's ends taper there)
                legs.append((knee[:3, 3], np.eye(3), np.zeros(3), np.full(3, min(size[1:])) + SETTLE_MARGIN))

    def deepest(pivot, link):
        """(capsule, point, where it is in it: 1 on its surface) of the leg capsule a link (its points along it:
        the cloth between two bones is straight) is deepest in."""
        best = (None, None, np.inf)
        for t in SETTLE_ALONG:
            p = pivot + t * link
            for c, (at, rot, offset, size) in enumerate(legs):
                q = float(np.linalg.norm(((p - at) @ rot - offset) / size))
                if q < best[2]:
                    best = (c, p, q)
        return best

    world = k['bones']['world']
    before = world.copy()
    turned = 0
    for chain, parent in zip(chains, parents):
        if any(x in names[parent] for x in LIMBS) or len(chain['neighbours']) < 2:
            continue                                                 # (an opening's edge: a leg passes by it)
        to_pose = posed[parent] @ np.linalg.inv(bind[parent])        # (at rest on its parent)
        frames = [to_pose @ before[b] for b in chain['bones']]
        rest = [f[:3, 3].copy() for f in frames]
        for j in range(1, len(frames)):
            pivot = frames[j - 1][:3, 3].copy()
            link = frames[j][:3, 3] - pivot
            want = rest[j] - rest[j - 1]                             # (its own direction: below a leg it hangs again)
            c, p, q = deepest(pivot, want)
            if q < 1.0:
                at, rot, offset, size = legs[c]
                normal = rot @ (((p - at) @ rot - offset) / size ** 2)  # (outward: |q|'s gradient)
                axis = np.cross(want, normal)
                if np.linalg.norm(axis) < 1e-6:
                    axis = np.cross(want, frames[j - 1][:3, 1])      # (its own outward axis)
                axis = axis / max(np.linalg.norm(axis), 1e-9)
                for angle in np.arange(SETTLE_STEP, SETTLE_MAX + SETTLE_STEP / 2, SETTLE_STEP):
                    r = _turn(axis, angle)
                    if deepest(pivot, r @ want)[2] >= 1.0:
                        want = r @ want
                        turned += 1
                        chain['draped'] = True
                        break
                else:
                    want = link
            r = hanging.turn(link / np.linalg.norm(link), want / np.linalg.norm(want))
            for f in frames[j - 1:]:                                 # (the link's bone turns, and all below it)
                f[:3, :3] = r @ f[:3, :3]
                f[:3, 3] = pivot + r @ (f[:3, 3] - pivot)
        back = np.linalg.inv(to_pose)
        for b, f in zip(chain['bones'], frames):
            world[b] = back @ f
    changed = [b for chain in chains for b in chain['bones'] if not np.allclose(world[b], before[b])]
    return turned, hanging.follow(k, before, changed) if changed else 0


def springs(skel, made, chains, body):
    """The spring file's cloth part: skel the fighter's skeleton with the chains' bones (made: their indices, in
    chain order; chains: rig()'s result), body: the body's vertices without the cloth ((n, 3) bind positions, mm).
    -> {'entries': [(OPT number, link, length, (outward, inward limit or None) or None: Lars's)], 'capsules':
    [(bone index, offset, sizes)], 'pairs': [(OPT number, capsule)], 'links': [(OPT number, other OPT number,
    link)]}."""
    world = bone.world_matrices(skel)
    names = list(skel['names'])
    chest = world[names.index('cha:MUNE2_jnt')][1, 3]
    caps = capsules(skel, body)

    def inside(p, c):
        """Where p is in capsule c: 1 on its surface."""
        b, offset, size = caps[c]
        m = world[b]
        rot = m[:3, :3] / np.linalg.norm(m[:3, :3], axis=0)
        return float(np.linalg.norm(((p - m[:3, 3]) @ rot - offset) / size))

    def touches(chain):
        """[(bone, capsule)] a chain's bones may touch: below the chest, all leg capsules, near ones of the trunk;
        none for a chain hung from an arm or its top bone."""
        if any(x in names[skel['parent'][chain[0]]] for x in LIMBS):
            return []
        out = []
        for b in chain[1:]:
            p = world[b][:3, 3]
            if p[1] > chest:
                continue
            out += [(b, c) for c in range(len(caps)) if caps[c][0] in [names.index('cha:' + x) for x, _, _ in
                                                                        BODY[:LEGS]] or inside(p, c) < TRUNK_REACH]
        return out

    candidates = [x for bones in made for x in touches(bones)]
    for c in range(len(caps)):                   # thickness: touching the nearest cloth bone at rest
        b, offset, size = caps[c]
        m = world[b]
        rot = m[:3, :3] / np.linalg.norm(m[:3, :3], axis=0)
        limb = names[b][4:] in [BODY[i][0] for i in LIMB]
        scales = []
        for bb, cc in candidates:
            if cc != c:
                continue
            q = ((world[bb][:3, 3] - m[:3, 3]) @ rot - offset) / size
            if limb:                             # (along a limb its length stays: only its thickness scales)
                if abs(q[0]) < 1.0:
                    scales.append(float(np.sqrt((q[1] ** 2 + q[2] ** 2) / (1.0 - q[0] ** 2))))
            else:
                scales.append(float(np.linalg.norm(q)))
        if scales:
            k = min(max(min(scales) / TOUCH, SHRINK), GROW)
            size = size * (np.array([1.0, k, k]) if limb else k)
            caps[c] = (b, offset, size)
    touching = set(candidates)
    number = {}
    for i, n in enumerate(names):
        m = _NAMED.match(n)
        if m:
            number[i] = int(m.group(1))
    entries, pairs, links = [], [], []
    for c, (bones, chain) in enumerate(zip(made, chains)):
        limits = None if any(x in names[skel['parent'][bones[0]]] for x in LIMBS) else (
            OUTWARD, DRAPED_INWARD if chain.get('draped') else None)
        for j, b in enumerate(bones):
            p = world[b][:3, 3]
            nxt = world[bones[j + 1]][:3, 3] if j + 1 < len(bones) else world[bones[j - 1]][:3, 3]
            entries.append((number[b], j, float(np.linalg.norm(nxt - p)), limits))
            pairs += [(number[b], cc) for cc in range(len(caps)) if (b, cc) in touching]
        for nb in sorted(chain['neighbours']):
            if nb <= c:
                continue
            for j, (a, b) in enumerate(zip(bones, made[nb])):
                links.append((number[a], number[b], j))
    order = {e[0]: i for i, e in enumerate(entries)}         # (the file lists them in entry order)
    pairs.sort(key=lambda x: order[x[0]])
    links.sort(key=lambda x: order[x[0]])
    return dict(entries=entries, capsules=caps, pairs=pairs, links=links)


def template(archives):
    """Lars's coat tails' spring file (the entries and capsules the chains copy)."""
    return archives.read(archive.member_key(*TEMPLATE))


def parse(m):
    """A spring file's (entries, capsules, pairs, links, the rest): byte strings."""
    n, = struct.unpack_from('>I', m, MOP_COUNT)
    entries = [m[MOP_ENTRIES + MOP_ENTRY * i:MOP_ENTRIES + MOP_ENTRY * (i + 1)] for i in range(n)]
    at = MOP_ENTRIES + MOP_ENTRY * n
    nc, = struct.unpack_from('>I', m, at)
    capsules = [m[at + 16 + MOP_CAPSULE * i:at + 16 + MOP_CAPSULE * (i + 1)] for i in range(nc)]
    at += 16 + MOP_CAPSULE * nc
    npairs = sum(struct.unpack_from('>I', e, 0x34)[0] for e in entries)
    nlinks = sum(struct.unpack_from('>I', e, 0x38)[0] for e in entries)
    pairs = m[at:at + MOP_PAIR * npairs]
    links = m[at + MOP_PAIR * npairs:at + MOP_PAIR * npairs + MOP_LINK * nlinks]
    return entries, capsules, pairs, links, m[at + MOP_PAIR * npairs + MOP_LINK * nlinks:]


def spring_file(mop, template_mop, cloth):
    """mop with the cloth's entries (Lars's coat's for each link), capsules, pairs and links after its own
    (springs()'s result)."""
    entries, capsules, old_pairs, old_links, rest = parse(mop)
    t_entries = parse(template_mop)[0]
    by_number = {struct.unpack_from('>I', e)[0]: e for e in t_entries}
    first_capsule = len(capsules)
    npairs, nlinks = {}, {}
    for number, _ in cloth['pairs']:
        npairs[number] = npairs.get(number, 0) + 1
    for number, _, _ in cloth['links']:
        nlinks[number] = nlinks.get(number, 0) + 1
    out = list(entries)
    for number, j, length, limits in cloth['entries']:
        e = bytearray(by_number[TEMPLATE_FIRST + min(j, TEMPLATE_LINKS - 1)])
        struct.pack_into('>I', e, 0, number)
        struct.pack_into('>f', e, 16, length)
        if limits is not None:                   # (about local Z: out at 28, in at 32, stored negative)
            struct.pack_into('>f', e, 28, limits[0])
            if limits[1] is not None:
                struct.pack_into('>f', e, 32, -limits[1])
        struct.pack_into('>II', e, 0x34, npairs.get(number, 0), nlinks.get(number, 0))
        out.append(bytes(e))
    pairs = b''.join(struct.pack('>II8x', number, first_capsule + capsule) for number, capsule in cloth['pairs'])
    links = b''.join(struct.pack('>IIff36x', a, b, RELATION_STIFFNESS, RELATION_VALUES[min(j, 2)])
                     for a, b, j in cloth['links'])
    capsules = capsules + [struct.pack('>II2f3ff3ff3f5f', 1, b, 0, 0, 0, 0, 0, 0, *offset, 0, *size, 0, 0, 0, 0, 0)
                           for b, offset, size in cloth['capsules']]
    return (mop[:MOP_COUNT] + struct.pack('>I', len(out)) + bytes(12) + b''.join(out)
            + struct.pack('>I', len(capsules)) + bytes(12) + b''.join(capsules) + old_pairs + pairs + old_links + links
            + rest)
