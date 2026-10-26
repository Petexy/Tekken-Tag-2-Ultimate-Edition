"""Strands Tekken 8 simulates (cords, strap ends, ties) -> the cloth convert/cloth.py turns into swinging chains.

Tekken 8 moves a costume's cloth with Catwalk Cloth, its own solver. A skeletal mesh with cloth carries:
* simulation meshes: sections of its own, skinned like the rest, in a material nobody sees (mesh.SIM_MATERIALS;
  Reina's body: MI_Cal_Mesh, 3123 vertices: her jacket, hood, sleeves, socks, boots' laces, the hood's strings,
  the hem's three cords and the sleeve straps' loose ends);
* after its LODs, the Catwalk hook (`CatwalkClothHook` in the name map): a header naming the cloth's variations
  (Reina's: v0, sta1, select, zbrvscbr_00_c1), then per variation its solver data, of which this module reads one
  part, the first variation's (the others differ in how much of the jacket moves):
      u32 count, count x {u32 length, that many bytes (a NUL-terminated Maya path:
          '|zbr_bdu_1p_gp_msl|sim_mesh_group_bdu_msl|sim_mesh_zbr_1p_string_002|..Shape'), u32 the mesh's number}
      u32 count, count x {u32 N, N x u32 body, u32 m, u32 section, u32 simulation mesh's number, u32 kind}
  kind 0: the vertices of `section` (a simulation section) the solver moves for that simulation mesh: N = n (2 + m),
      n vertex numbers (in the section, ascending), n x u32 whose high 16 bits are how much the solver moves the
      vertex (0..65535: 0 = it follows its skin weights, 65535 = wholly simulated: a hood string's top 0, then 0.41,
      0.74, 0.92, then 1; a vertex of the section in no list follows its skin), then n x m u32 (u16 a neighbour, u16
      a value: the solver's constraints, not read);
  kind 1: the vertices of a drawn section that follow that simulation mesh: n vertex numbers, then the rest (how
      they follow it: not read).
Read for Reina from her body (47 lists in each of 4 variations, every one parsing to the byte), her hair the same.

TTT2 has no cloth solver. The big pieces (jacket, hood, sleeves, socks) hang as modelled and stay skinned, as
convert/cloth.py leaves Tekken 7's barely moving cloth: how far Catwalk lets them move is in the parts not read.
What sticks out is the strands Tekken 8 models straight out and lets fall: Reina's hem cords (out to the sides and
back, 20 cm), her sleeve straps' loose ends (out from the upper arms; up after the re-pose to the donor's T-pose).
A strand is an island of a simulation section (vertices joined by triangles) that
* the solver moves wholly somewhere (FULL),
* hangs from something: vertices it does not move (PINNED) or sewn onto another island (within WELD: a cord's top
  is on the jacket's hem, a strap's on its sleeve); an island hanging from nothing is left (the hood),
* is narrow (its vertices' second principal spread at most NARROW mm: a sleeve is a tube, a jacket a sheet), at
  least STRAND_REACH long from where it hangs, has drawn vertices following it and does not lie on the body (LYING:
  a boot's lace ends stay as they are).
Each becomes one cloth for convert/cloth.add (the dict convert/cloth.find gives): its asset the strand's vertices
posed as the model is (skinned through the model's re-pose: skeleton.repose), max distance 0 where it hangs from,
its geodesic distance from there elsewhere; its drawn vertices those of the part the game moves with its
simulation mesh (when the model says which they were: decimate's 'source') within DRAWN_REACH of the strand and
nearer to it than to the rest of the simulation section; its chains have links STRAND_LINK long, are kept from
STRAND_REACH, and hang (rig drapes them, _hanging): straight down when modelled tilted more than STRAND_FLOWING (the
cords; the hood's strings lean on the chest as modelled and keep it), along the arm when hung from one (the straps:
straight down in the T-pose would point into the body with the arms lowered). convert/cloth.py skins the drawn
vertices to them and gives TTT2's spring file their entries and the legs' capsules. Its standing pose (settle) does
nothing for them: it turns only chains closed round a leg (neighbours on both sides), and a strand is one chain.

Written for this project from the files themselves (no third-party code).
"""
import re
import struct

import numpy as np

from ..convert import cloth as cloth_chains, model as convert_model, skeleton
from ..tekken7 import mesh as t7mesh
from . import mesh as t8mesh, uprops

PINNED = 0.01                   # share of a vertex's motion the solver makes at most for it to follow the skin
FULL = 0.9                      # ... at least somewhere on an island for it to be a strand
WELD = 0.05                     # cm: a strand's vertex this near another island's is sewn onto it
NARROW = 25.0                   # mm: a strand's vertices spread no further than this across it (one sigma)
STRAND_REACH = 50.0             # mm: shorter strands stay skinned (cloth.REACH for Tekken 7's cloth: 150)
STRAND_LINK = 80.0              # mm between a strand chain's bones (a 20 cm cord: 3 links)
DRAWN_REACH = 50.0              # mm: drawn vertices this near a strand's simulated vertices follow it (a cord drawn
                                # 3-4 cm off its simulated line: Reina's hem cords)
LYING = 20.0                    # mm: a strand whose vertices are this near the body (median) lies on it: left (a
                                # boot's lace ends)
STRAND_FLOWING = np.radians(50.0)   # a strand tilted more than this from straight down was modelled flowing: it
                                # hangs (rig's FLOWING for Tekken 7's cloth: 30; a hood's strings lean 44 degrees on
                                # the chest as modelled, the hem's cords stand out 58-60)
ARMS = (('L_Arm', 'L_ForeArm'), ('L_ForeArm', 'L_Hand'), ('R_Arm', 'R_ForeArm'), ('R_ForeArm', 'R_Hand'))
KIND_SIMULATED, KIND_DRIVEN = 0, 1
MAX_LISTS = 1 << 16
NAME = re.compile(rb'[\x20-\x7e]{2,4095}\x00')


class Strand:
    """A strand as convert/cloth.rig takes a Tekken 7 APEX asset: vertices (n, 3) in Unreal centimetres (Z up,
    tekken7/apex.py's units), max_distance (n,) cm (0: where it hangs from), triangles (t, 3)."""

    def __init__(self, vertices, max_distance, triangles):
        self.vertices, self.max_distance, self.triangles = vertices, max_distance, triangles


# ------------------------------------------------------------------------------------------------ the hook
def hook_offset(m):
    """Where mesh m's data after its LODs starts in its package (the Catwalk hook of an _msl mesh): what
    tekken8.mesh reads before it, read again."""
    pkg, e = m.package, m.export
    _, start = uprops.read_object(pkg, e)
    r = t8mesh.Reader(pkg, e.offset + start, e.offset + e.size)
    r.strip()
    r.take('7d')                               # bounds
    for _ in range(r.count(1024)):             # materials
        r.i32(), r.fname(), r.u32(), r.take('II4f')
    for _ in range(r.count(t8mesh.MAX_BONES)):
        r.fname(), r.i32()
    r.array('<f8', 10 * r.count(t8mesh.MAX_BONES))
    for _ in range(r.count(t8mesh.MAX_BONES)):
        r.fname(), r.i32()
    r.bool32()                                 # cooked
    for _ in range(r.count(16)):
        t8mesh._lod(r, bool(m.props.get('bHasVertexColors', False)))
    return r.p, e.offset + e.size


def _name_map(b, start, end):
    """The first simulation mesh name map in b[start:end] -> ({number: name}, the offset after it) or (None, None)."""
    for mt in NAME.finditer(b, start, end):
        s = mt.start()
        if s < start + 8 or struct.unpack_from('<I', b, s - 4)[0] != mt.end() - s:
            continue
        count, = struct.unpack_from('<I', b, s - 8)
        if not 1 <= count <= 256:
            continue
        p, names = s - 4, {}
        for _ in range(count):
            if p + 4 > end:
                break
            length, = struct.unpack_from('<I', b, p)
            if not 2 <= length <= 4096 or p + 8 + length > end or b[p + 3 + length] != 0 or \
                    not NAME.fullmatch(b, p + 4, p + 4 + length):
                break
            number, = struct.unpack_from('<I', b, p + 4 + length)
            names[number] = b[p + 4:p + 3 + length].decode('ascii')
            p += 8 + length
        else:
            if sorted(names) == list(range(count)):
                return names, p
    return None, None


def _lists(b, p, end, sections):
    """The vertex lists after a name map at b[p:] (sections: each section's vertex count) -> [(section, simulation
    mesh, kind, vertices, the u32 after them)], or None when they do not parse as such."""
    count, = struct.unpack_from('<I', b, p)
    if not 1 <= count <= MAX_LISTS:
        return None
    p += 4
    out = []
    for _ in range(count):
        if p + 4 > end:
            return None
        n_words, = struct.unpack_from('<I', b, p)
        if p + 4 + 4 * n_words + 16 > end:
            return None
        body = np.frombuffer(b, '<u4', n_words, p + 4)
        p += 4 + 4 * n_words
        m, section, sim, kind = struct.unpack_from('<4I', b, p)
        p += 16
        if kind not in (KIND_SIMULATED, KIND_DRIVEN) or section >= len(sections) or m > 64 or n_words % (m + 2):
            return None
        n = n_words // (m + 2)
        vertices = body[:n].astype(np.int64)
        if n and (vertices.max() >= sections[section] or (np.diff(vertices) <= 0).any()):
            return None
        out.append((section, sim, kind, vertices, body[n:2 * n]))
    return out


def catwalk(m):
    """Mesh m's Catwalk data this module reads: {'meshes': {number: name}, 'moved': {section: (n,) how much the
    solver moves each vertex, 0..1}, 'mesh_of': {section: (n,) the simulation mesh each vertex is in or -1},
    'driven': {(drawn section, simulation mesh): its vertices}}; None for a mesh without (or an unknown layout)."""
    sections = m.lods[0].sections
    if not any(s.cloth_mapping for s in sections):
        return None
    start, end = hook_offset(m)
    b = m.package.data
    counts = [s.num_vertices for s in sections]
    while True:
        names, p = _name_map(b, start, end)
        if names is None:
            return None
        lists = _lists(b, p, end, counts)
        if lists is not None:
            break
        start = p
    moved, mesh_of, driven = {}, {}, {}
    for section, sim, kind, vertices, words in lists:
        if kind == KIND_SIMULATED:
            if section not in moved:
                moved[section] = np.zeros(counts[section])
                mesh_of[section] = np.full(counts[section], -1)
            moved[section][vertices] = (words >> 16) / 65535.0
            mesh_of[section][vertices] = sim
        else:
            key = (section, sim)
            driven[key] = np.union1d(driven.get(key, np.zeros(0, np.int64)), vertices)
    return {'meshes': names, 'moved': moved, 'mesh_of': mesh_of, 'driven': driven}


# ------------------------------------------------------------------------------------------------ strands
def _islands(triangles, n):
    """Each vertex's island (vertices joined by triangles), -1 for vertices in none."""
    parent = np.arange(n)

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in triangles:
        ra = root(a)
        parent[root(b)] = ra
        parent[root(c)] = ra
    out = np.array([root(x) for x in range(n)])
    used = np.zeros(n, bool)
    used[triangles.reshape(-1)] = True
    return np.where(used, out, -1)


def strands(positions, triangles, moved):
    """The strands of a simulation section: positions (n, 3) cm, triangles (t, 3), moved (n,) 0..1 (catwalk()).
    -> [(its vertices, which of them it hangs from (bool), its triangles in its own numbering)]."""
    island = _islands(triangles, len(positions))
    out = []
    for i in np.unique(island[island >= 0]):
        v = np.nonzero(island == i)[0]
        if moved[v].max() < FULL:
            continue
        others = np.nonzero((island != i) & (island >= 0))[0]
        sewn = np.zeros(len(v), bool)
        if len(others):
            _, d = cloth_chains._nearest(positions[v], positions[others])
            sewn = d <= WELD
        hangs = sewn | (moved[v] <= PINNED)
        if not hangs.any() or hangs.all():
            continue
        p = positions[v] * 10.0
        spread = np.sqrt(np.maximum(np.linalg.eigvalsh(np.cov((p - p.mean(0)).T)), 0.0))
        if spread[1] > NARROW:
            continue
        own = np.full(len(positions), -1)
        own[v] = np.arange(len(v))
        tris = own[triangles[(island[triangles[:, 0]] == i)]]
        out.append((v, hangs, tris))
    return out


def _bind_world(m):
    """Mesh m's bones' bind matrices in TTT2 space as tekken8.model.load_model makes them (mm)."""
    cm = convert_model
    g = t7mesh.global_matrices(m.skeleton['pose'], m.skeleton['parents'])
    ibm = np.linalg.inv(cm._ue_to_ttt2_matrix(g)).astype(np.float32)
    world = np.linalg.inv(ibm.astype(np.float64))
    world[:, :3, 3] *= cm.M_TO_MM
    return world


def _posed(k, info, geo, vertices):
    """A part's mesh vertices (its geometry() numbering) in TTT2 space (mm), turned as skeleton.repose turned the
    model: each by its bones' changes (the model's bind matrices now over the mesh's own), blended by its weights."""
    cm = convert_model
    p = cm._ue_to_ttt2_points(geo['positions'][vertices]).astype(np.float64) * cm.M_TO_MM
    change = np.asarray(k['bones']['world'])[info['remap']] @ np.linalg.inv(_bind_world(info['mesh']))
    w = geo['weights'][vertices].astype(np.float64)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-12)
    blended = np.einsum('vk,vkij->vij', w, change[geo['joints'][vertices]])
    return np.einsum('vij,vj->vi', blended[:, :3, :3], p) + blended[:, :3, 3]


def _original(k):
    """Each model vertex's number in the parts' meshes as loaded (decimate's 'source'), and each part's first one
    there: (array, {tag: first}), or (None, firsts) when the model does not say."""
    first, base = {}, 0
    for tag, info in k['parts'].items():
        first[tag] = base
        base += info['mesh'].lods[0].num_vertices
    n = len(k['prims'][0]['pos'])
    source = k.get('source')
    if source is not None and len(source) == n:
        return np.asarray(source, np.int64), first
    return (np.arange(n) if n == base else None), first


def _driven(data, sections, sim, local):
    """Which of the drawn vertices (local: their numbers in the part's mesh) the game moves with simulation mesh
    `sim` (catwalk()'s 'driven')."""
    out = np.zeros(len(local), bool)
    for (section, mesh), vertices in data['driven'].items():
        if mesh == sim:
            a = sections[section].base_vertex
            inside = (local >= a) & (local < a + sections[section].num_vertices)
            out[inside] |= np.isin(local[inside] - a, vertices)
    return out


def _hanging(k, info, geo, vertices, root):
    """How a strand hangs (rig's 'down' and 'flowing'): one hung from an arm (its top's skin weights mostly on an
    arm bone: cloth.LIMBS) lies along the arm's nearest segment, toward its end (it hangs when the arm does: straight
    down in the T-pose would point into the body with the arms lowered), however it was modelled; any other hangs
    straight down if modelled tilted more than STRAND_FLOWING."""
    names = k['bones']['names']
    share = np.zeros(len(names))
    np.add.at(share, info['remap'][geo['joints'][vertices]].reshape(-1), geo['weights'][vertices].reshape(-1))
    target = skeleton.t7_weight_target(names[int(share.argmax())], None) or ''
    if not any(x in target for x in cloth_chains.LIMBS):
        return None, STRAND_FLOWING
    at = {n: i for i, n in enumerate(names)}
    world = np.asarray(k['bones']['world'])[:, :3, 3]
    best = None
    for a, b in ARMS:
        if a in at and b in at:
            d = float(cloth_chains._segment_distance(root[None], world[at[a]], world[at[b]])[0])
            if best is None or d < best[0]:
                best = (d, world[at[b]] - world[at[a]])
    if best is None:
        return None, STRAND_FLOWING
    return best[1] / np.linalg.norm(best[1]), 0.0


def find(k, parts, log=print):
    """The strands of the costume's parts Tekken 8 simulates, as convert/cloth.find gives Tekken 7's cloth: [{'part',
    'asset' (Strand), 'vertices' (the drawn vertices in k's streams), 'name', and for rig 'link', 'reach', 'down',
    'flowing'}]. k: the model as model.tekken8_model makes it (decimated, re-posed); parts: [(tag, path)]."""
    out = []
    pos = k['prims'][0]['pos']
    used = np.unique(np.concatenate([p['tris'].reshape(-1) for p in k['prims']]))
    original, first = _original(k)
    for tag, _ in parts:
        info = k['parts'].get(tag)
        if info is None:
            continue
        m = info['mesh']
        data = catwalk(m)
        if data is None:
            if any(s.cloth_mapping for s in m.lods[0].sections):
                log('  %s: its cloth simulation data was not understood: no strands' % tag)
            continue
        geo = m.geometry(0)
        sections = m.lods[0].sections
        drawn = np.unique(np.concatenate([p['tris'].reshape(-1) for p in k['prims'] if p['part'] == tag]))
        local = original[drawn] - first[tag] if original is not None else None
        left, number = [], 0
        for si, moved in sorted(data['moved'].items()):
            s = sections[si]
            base = s.base_vertex
            found = strands(geo['positions'][base:base + s.num_vertices], geo['triangles'][si] - base, moved)
            if not found:
                continue
            everything = _posed(k, info, geo, base + np.arange(s.num_vertices))
            for v, hangs, tris in found:
                points = everything[v]
                _, adjacency = cloth_chains._edges(tris, len(v))
                g, _ = cloth_chains._hang(points, hangs, adjacency)
                reach = float(g[np.isfinite(g)].max())
                sims = data['mesh_of'][si][v]
                sim = int(np.bincount(sims[sims >= 0]).argmax()) if (sims >= 0).any() else -1
                name = '%s strand %d (%s)' % (tag, number, data['meshes'].get(sim, '?').rsplit('|', 1)[-1])
                number += 1
                if reach < STRAND_REACH:
                    left.append('%s %.0f mm long' % (name, reach))
                    continue
                # the drawn vertices following it: the part's the game moves with its simulation mesh, near it and
                # nearer it than the rest of the simulation section
                candidates = drawn[_driven(data, sections, sim, local)] if local is not None and sim >= 0 else drawn
                rest = np.setdiff1d(np.arange(s.num_vertices), v)
                _, d_own = cloth_chains._nearest(pos[candidates], points)
                d_rest = cloth_chains._nearest(pos[candidates], everything[rest])[1] if len(rest) else np.full(
                    len(candidates), np.inf)
                follow = candidates[(d_own <= DRAWN_REACH) & (d_own < d_rest)]
                if not len(follow):
                    left.append('%s: no drawn vertices follow it' % name)
                    continue
                body = np.setdiff1d(used, follow)
                lying = float(np.median(cloth_chains._nearest(points[~hangs], pos[body])[1]))
                if lying < LYING:
                    left.append('%s lies on the body (%.0f mm)' % (name, lying))
                    continue
                down, flowing = _hanging(k, info, geo, base + v[hangs], points[hangs].mean(0))
                vertices = np.stack([points[:, 0], points[:, 2], points[:, 1]], 1) / 10.0
                out.append(dict(part=tag, asset=Strand(vertices, np.where(hangs, 0.0, g / 10.0), tris),
                                vertices=follow, name=name, link=STRAND_LINK, reach=STRAND_REACH, down=down,
                                flowing=flowing))
                log('  %s: a strand %.0f mm long%s, %d drawn vertices' % (
                    name, reach, ' (from an arm: laid along it)' if down is not None else '', len(follow)))
        if left:
            log('  %s: left skinned: %s' % (tag, '; '.join(left)))
    return out
