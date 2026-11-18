"""Cloth Tekken 8 simulates (coats, fringes, cords, strap ends) -> the cloth convert/cloth.py turns into swinging chains.

Tekken 8 moves a costume's cloth with Catwalk Cloth, its own solver. A skeletal mesh with cloth carries:
* simulation meshes: sections of its own, skinned like the rest, in a material nobody sees (mesh.SIM_MATERIALS;
  Reina's body: MI_Cal_Mesh, 3123 vertices: her jacket, hood, sleeves, socks, boots' laces, the hood's strings,
  the hem's three cords and the sleeve straps' loose ends; Azucena's: her jacket's hem, hood, sleeves with their
  fringes, necklaces), or a drawn section simulated itself (Azucena's leggings: barely);
* after its LODs, the Catwalk hook (`CatwalkClothHook` in the name map): a header naming the cloth's variations
  (Reina's: v0, sta1, select, zbrvscbr_00_c1; Azucena's: v0), then per variation its solver data; this module reads
  the first variation's:
      u32 1, u32 the number of simulation meshes, then per simulation mesh in its number's order, among more solver
          data not read: the PARTICLES' block, five arrays of u32 n + n elements (PARTICLE_ARRAYS; n = the mesh's
          vertices welded by position: Azucena's sleeves, 1485 vertices, are 1339 particles), the first the
          particle's MAX DISTANCE (f32 cm: how far it may leave where its skin weights put it; 0 = pinned; painted
          as smooth gradients: Azucena's sleeves 0 at the shoulder, 15 at the cuffs, 28 at the fringes' tips; Reina's
          jacket 0 down to her waist, 35 at its hem, 60 at its back cord's end), ..., later the particles'
          TRIANGLES (u32 t, t x (u16 a, b, c, u16 flags)) in the order of the simulation section's triangles: the
          two lists aligned number the section's vertices' particles (a reordered copy of it comes first);
      u32 count, count x {u32 length, that many bytes (a NUL-terminated Maya path:
          '|zbr_bdu_1p_gp_msl|sim_mesh_group_bdu_msl|sim_mesh_zbr_1p_string_002|..Shape'), u32 the mesh's number}
      u32 count, count x {u32 N, N x u32 body, u32 m, u32 section, u32 simulation mesh's number, u32 kind}
  kind 0: the vertices of `section` (a simulation section) the solver moves for that simulation mesh: N = n (2 + m),
      n vertex numbers (in the section, ascending), n x u32 whose high 16 bits are how much the solver moves the
      vertex (0..65535: 0 = it follows its skin weights, 65535 = wholly simulated: a hood string's top 0, then 0.41,
      0.74, 0.92, then 1; every Azucena's 1; a vertex of the section in no list follows its skin), then m x n u32
      (u16 a triangle of the simulation mesh, u16 a weight: each vertex on its triangles, the weights summing to
      65535; not read);
  kind 1: the vertices of a drawn section that follow that simulation mesh: n vertex numbers, n x u32 (high 16 bits:
      how much the vertex follows the simulation, 0..1), then the same m x n triangles and weights (not read).
Read for Reina from her body (47 lists in each of 4 variations, every one parsing to the byte), her hair the same;
Azucena's body, hair and hair extras too (particles() aligns every simulation mesh but her leggings' and tank top's).

TTT2 has no cloth solver: what swings in it are chains of extra bones with spring entries (convert/cloth.py, after
Lars's coat). pieces() makes Tekken 8's cloth into convert/cloth.add's cloths from the max distances, as
convert/cloth.find does Tekken 7's APEX cloth: per island of a simulation mesh's particles, the particles moving at
most the HOLD level stay on the body (skinned), the rest hang from them in pieces (connected particles):
* a wide piece (a coat's tails) that may move at least cloth.FREE_MIN swings as Tekken 7's cloth does (Reina's
  jacket below her chest), less stays (Azucena's cropped jacket's hem, 9.6 cm; the hoods, the necklaces, the hair);
  the strands sewn onto it (strands(): Reina's hem cords, modelled sticking out) are taken out and hang on their own;
* a narrow piece (a strand: a cord, a fringe strip, a strap end) swings when it may move at least SWING of its
  length and does not lie on the body (LYING: a boot's lace ends);
* on an arm the hold level rises (_hold) till all that swings off it is strands: a sleeve is a tube round the arm,
  and chains hung from where it starts to move would pull the forearm's sleeve off the elbow; Azucena's sleeves stay
  on the arms up to 13 cm and their 18 fringes swing, Reina's up to 2 cm and their strap ends swing.
A strand's chains have links STRAND_LINK long and are kept from STRAND_REACH; it hangs (rig drapes it): straight down
when modelled tilted more than STRAND_FLOWING (the cords; the hood's strings lean on the chest as modelled and keep
it); from an arm as modelled if Tekken 8 models it hanging in its own pose (ARM_HANGING: the fringes), along the arm
if not (the strap ends: straight down in the T-pose would point into the body with the arms lowered), with ARM_SPRING
entries (Lars's coat's hardly let a chain move: the fringes stood out like spikes with her arms raised). Chains hang
from body joints, not from the busts (rig 'body_parent'). The simulation meshes whose particles are not aligned keep
the strands() rules of before: islands the solver moves wholly (FULL), hanging from vertices it does not move (PINNED)
or sewn onto another island (WELD), narrow (NARROW), at least STRAND_REACH long, with drawn vertices within
DRAWN_REACH, not lying on the body. convert/cloth.py skins the drawn vertices to the chains and gives TTT2's spring
file their entries and the legs' capsules. Tekken 8's solver moves the cloth from where its skin weights put it, so a
wide piece skinned mostly to a thigh (Miary Zo's sarong below her hip, its flap, her right hip's scarf with its tassels)
hangs from that thigh (rig 'leg_parent'): on the hips her stance turned the thigh off the cloth's rest, the thigh went
through it and the sarong fell between and behind her legs, the tassels' strings sank into the thigh with only their
beads showing. Cloth hung from a leg grows no capsule (rig 'leg_moves'). Its standing pose (settle) is Tekken 7's only
(from the .tkmvst). What of
the hair swings (HAIR_PARTS; Reina's and Azucena's hair moves 3 cm at most and stays skinned; Miary Zo's front braids,
with their gold ornaments, and her back hair swing) has HAIR_SPRING entries and touches no capsule (convert/cloth.py
'hair'): Lars's coat's entries hardly let it swing sideways, Lili's hair entry (Tekken 7's hanging hair, chains.py)
holds it rigid on the head.

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
                                # boot's lace ends). The hair's strands lie on the body, not on the hair's other
                                # layers (with its cards kept as strands, decimate.py's Hair strands, Miary Zo's two
                                # long back strands came within 9..13 mm of the hair under them and stopped swinging)
STRAND_FLOWING = np.radians(50.0)   # a strand tilted more than this from straight down was modelled flowing: it
                                # hangs (rig's FLOWING for Tekken 7's cloth: 30; a hood's strings lean 44 degrees on
                                # the chest as modelled, the hem's cords stand out 58-60)
DRAWN_FREE = 10.0               # cm: an island of a drawn simulation mesh half of whose particles may move less is held
                                # up to this, its loose ends swinging (pieces drawn_sims: Azazel's chest bandage, half
                                # within 6 cm, hung whole as cloth it tore; his loose strips: half 26 to 56 cm)
DRAWN_LINKS = 5                 # links of a chain of a drawn simulation mesh's wide piece at most (pieces drawn_sims:
                                # Azazel's bandage strips, up to 2.9 m: at TTT2's 150 mm, 13 pieces took 127 bones)
HOLD_STEP = 0.5                 # cm: cloth on an arm is held on it up to a max distance raised by this till all that
                                # swings off it is strands (Azucena's sleeves: 13 cm, the cuffs; their fringes swing)
SWING = 0.5                     # a strand swings when it may move at least this share of its length (a boot's 6 cm
                                # lace loops may move 6 cm, Reina's hood strings 9 of 15)
ARM_HANGING = np.radians(70.0)  # a strand on an arm modelled at most this far from straight down in Tekken 8's own pose
                                # (the arms 45 degrees down) hangs as modelled (Azucena's fringes: 24..58 degrees);
                                # one sticking out further lies along the arm (Reina's strap ends: _hanging)
ARM_SPRING = dict(flags=0x60, parameters=(20.0, 70.0, 20.0), limits=(1.57, -1.57, 1.57, -1.57), last=0.2)
                                # the spring entry of a strand's chain hung from an arm, after TTT2's own sleeve
                                # fringes' (common item wcm_etl_fringe: 20 70 10..40, limits 1.05 / 1.57 rad, 0.2), its
                                # limits a quarter turn every way. In game (Azucena's fringes, the angle root to tip
                                # from straight down, standing / walking / Libertador; held rigid 56 / 42 / 60): this
                                # 23 / 15 / 15; with 20 70 40, Y 1.05: 37 / 23 / 30; Lars's coat's entry (30 10 70,
                                # 0.05 / 0.2 rad) 47 / 34 / 57, the spikes the user saw; 10 50 100 rigid with any limits
HAIR_PARTS = ('har',)           # the costume's hair: what of it swings is hair (rig 'hair': no capsules) ..
HAIR_SPRING = dict(flags=0x60, parameters=(50.0, 70.0, 50.0), limits=(0.3, -0.3, cloth_chains.OUTWARD, -0.05),
                   last=0.2)    # .. with these entries: hanging (ARM_SPRING's gravity, 70), half-way back to rest (50),
                                # damped (50: TTT2's own entries have 20..40 for cloth, 100 on a fixed bone, 0 and less
                                # on bones meant to whip); sideways (about local Y) 0.3 rad per link, out from the body
                                # cloth.OUTWARD, in toward it 0.05 (the hair rests on the back and chest). In game (Miary
                                # Zo, a side step, the hair tips sideways off where the head would hold them, peak of
                                # any chain, mm, braids / 45 cm strands / back pieces / back base): Lars's coat's
                                # entries 28 / 91 / 54 / 77, these 68 / 240 / 132 / 235, settled 0.5 s later to Lars's
                                # rest band; damped 20: the strands kept swinging 100-150 mm (no decay in 2.5 s); 20 and
                                # pull back 20 with 0.6 rad: idle swings of 230 mm. Lili's hair entry (flag 0, 10 50 100,
                                # no limits: Tekken 7's hanging hair) held them rigid on the head, 0.0 mm off
ARMS = (('L_Arm', 'L_ForeArm'), ('L_ForeArm', 'L_Hand'), ('R_Arm', 'R_ForeArm'), ('R_ForeArm', 'R_Hand'))
KIND_SIMULATED, KIND_DRIVEN = 0, 1
MAX_LISTS = 1 << 16
PARTICLE_ARRAYS = (4, 4, 4, 8, 4)   # bytes an element of the per-particle arrays: max distance (f32 cm), a painted
                                # map (u16 pair), a per-mesh log value (f32), 4 x u16 anchors (the particles it is
                                # tied to, its own number for fewer), f32 (only the first is used)
MAX_PARTICLES = 1 << 16         # (u16 particle numbers)
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
    'driven': {(drawn section, simulation mesh): its vertices}, 'solver': (offset, offset): where the first
    variation's solver data lies in the package (before its name map: particles())}; None for a mesh without (or an
    unknown layout)."""
    sections = m.lods[0].sections
    if not any(s.cloth_mapping for s in sections):
        return None
    start, end = hook_offset(m)
    first = start
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
    at = p - 4 - sum(9 + len(name) for name in names.values())    # (where the name map starts)
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
    return {'meshes': names, 'moved': moved, 'mesh_of': mesh_of, 'driven': driven, 'solver': (first, at)}


# ------------------------------------------------------------------------------------------------ particles
def _weld(positions):
    """Each vertex's particle (vertices at one place are one particle), numbered in order of first appearance."""
    out, seen = np.empty(len(positions), np.int64), {}
    for i, p in enumerate(np.ascontiguousarray(positions, np.float32)):
        out[i] = seen.setdefault(p.tobytes(), len(seen))
    return out, len(seen)


def _block(b, p, end, n):
    """Where the first per-particle block of n particles starts in b[p:end] (PARTICLE_ARRAYS, each u32 n first; the
    max distances finite and >= 0, the anchors particles), or None."""
    pattern = struct.pack('<I', n)
    o = b.find(pattern, p, end)
    while o >= 0:
        q, at = o, []
        for size in PARTICLE_ARRAYS:
            if q + 4 + n * size > end or b[q:q + 4] != pattern:
                break
            at.append(q + 4)
            q += 4 + n * size
        else:
            distance = np.frombuffer(b, '<f4', n, at[0])
            anchors = np.frombuffer(b, '<u2', 4 * n, at[3])
            if np.isfinite(distance).all() and (distance >= 0).all() and (anchors < n).all():
                return o
        o = b.find(pattern, o + 1, end)
    return None


def _triangles(b, p, end, welded, n):
    """The particles' triangle list in b[p:end]: u32 t, then t x (u16 a, b, c, u16 flags) in the order of the
    simulation section's triangles (welded: those (t, 3) in _weld's numbering) -> (each welded particle's number in
    the solver's, the offset after the list), or (None, None) when no list there aligns with them."""
    t = len(welded)
    pattern = struct.pack('<I', t)
    o = b.find(pattern, p, end)
    while 0 <= o and o + 4 + 8 * t <= end:
        q = np.frombuffer(b, '<u2', 4 * t, o + 4).reshape(t, 4)[:, :3].astype(np.int64)
        if q.max(initial=0) < n:
            number = np.full(n, -1, np.int64)
            number[welded.reshape(-1)] = q.reshape(-1)
            if (number >= 0).all() and (number[welded] == q).all() and len(np.unique(number)) == n:
                return number, o + 4 + 8 * t
        o = b.find(pattern, o + 1, end)
    return None, None


def particles(m, data, geo):
    """The simulation meshes' particles as the solver keeps them, in its first variation (catwalk()'s 'solver'):
    {simulation mesh: {'section', 'of' (the section's vertices' particle numbers, -1 off the mesh), 'vertex' (a
    section vertex of each particle), 'triangles' (t, 3), 'max_distance' (n,) cm}}. geo: m.geometry(0). A mesh
    whose block or triangles are not found (a simulation section that is also drawn: Azucena's leggings) is left
    out."""
    if not data.get('solver'):
        return {}
    b = m.package.data
    p, end = data['solver']
    sections = m.lods[0].sections
    out = {}
    for sim in sorted(set(int(x) for mesh_of in data['mesh_of'].values() for x in np.unique(mesh_of) if x >= 0)):
        si = next(s for s, mesh_of in sorted(data['mesh_of'].items()) if (mesh_of == sim).any())
        s = sections[si]
        vertices = np.nonzero(data['mesh_of'][si] == sim)[0]
        welded, n = _weld(geo['positions'][s.base_vertex + vertices])
        if n >= MAX_PARTICLES:
            continue
        at = np.full(s.num_vertices, -1, np.int64)
        at[vertices] = np.arange(len(vertices))
        tris = geo['triangles'][si] - s.base_vertex
        tris = at[tris[(at[tris] >= 0).all(1)]]
        o = _block(b, p, end, n)
        if o is None:
            continue
        number, after = _triangles(b, o, end, welded[tris], n) if len(tris) else (None, None)
        if number is None:                                         # (the next mesh's block is after this one)
            p = o + 4 * len(PARTICLE_ARRAYS) + n * sum(PARTICLE_ARRAYS)
            continue
        of = np.full(s.num_vertices, -1, np.int64)
        of[vertices] = number[welded]
        vertex = np.zeros(n, np.int64)
        vertex[of[vertices][::-1]] = vertices[::-1]                # (the first vertex of each)
        out[sim] = dict(section=si, of=of, vertex=vertex, triangles=number[welded[tris]],
                        max_distance=np.frombuffer(b, '<f4', n, o + 4).astype(np.float64))
        p = after
    return out


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
    p = _bind_points(geo, vertices)
    change = np.asarray(k['bones']['world'])[info['remap']] @ np.linalg.inv(_bind_world(info['mesh']))
    w = geo['weights'][vertices].astype(np.float64)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-12)
    blended = np.einsum('vk,vkij->vij', w, change[geo['joints'][vertices]])
    return np.einsum('vij,vj->vi', blended[:, :3, :3], p) + blended[:, :3, 3]


def _bind_points(geo, vertices):
    """A part's mesh vertices (its geometry() numbering) where Tekken 8 models them, in TTT2's axes (mm)."""
    cm = convert_model
    return cm._ue_to_ttt2_points(geo['positions'][vertices]).astype(np.float64) * cm.M_TO_MM


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


def _on_arm(k, info, geo, vertices):
    """Whether the vertices' (a part's mesh numbering) skin weights mostly go to an arm bone (cloth.LIMBS)."""
    names = k['bones']['names']
    share = np.zeros(len(names))
    np.add.at(share, info['remap'][geo['joints'][vertices]].reshape(-1), geo['weights'][vertices].reshape(-1))
    target = skeleton.t7_weight_target(names[int(share.argmax())], None) or ''
    return any(x in target for x in cloth_chains.LIMBS)


def _hanging(k, info, geo, vertices, root):
    """How a strand hangs (rig's 'down' and 'flowing'): one hung from an arm (its top's skin weights mostly on an
    arm bone: cloth.LIMBS) lies along the arm's nearest segment, toward its end (it hangs when the arm does: straight
    down in the T-pose would point into the body with the arms lowered), however it was modelled; any other hangs
    straight down if modelled tilted more than STRAND_FLOWING."""
    if not _on_arm(k, info, geo, vertices):
        return None, STRAND_FLOWING
    names = k['bones']['names']
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


def _components(free, adjacency):
    """Each particle's connected part of the free particles (joined by edges through free particles), -1 for others."""
    out = np.full(len(free), -1, np.int64)
    number = 0
    for start in np.nonzero(free)[0]:
        if out[start] >= 0:
            continue
        out[start] = number
        stack = [start]
        while stack:
            x = stack.pop()
            for y in adjacency[x]:
                if free[y] and out[y] < 0:
                    out[y] = number
                    stack.append(y)
        number += 1
    return out


def _spread(points):
    """The points' principal spreads (one sigma, largest first)."""
    if len(points) < 2:
        return np.zeros(3)
    return np.sqrt(np.maximum(np.linalg.eigvalsh(np.cov((points - points.mean(0)).T)), 0.0))[::-1]


def _hold(points, max_distance, members, adjacency, arm):
    """The hold level (cm) of an island of particles (members), its free pieces' numbers (_components) and which
    particles it holds: PINNED_CM; on an arm raised by HOLD_STEP till every free piece reaching STRAND_REACH is
    narrow (a strand), then on while the strands split further (Azucena's sleeves: 12.5 cm leaves two fringes joined,
    13 cm all nine of a sleeve apart)."""
    def level(hold):
        held = members & (max_distance <= hold)
        piece = _components(members & ~held, adjacency)
        g, _ = cloth_chains._hang(points, held, adjacency)
        reaching, wide = 0, False
        for i in range(piece.max() + 1):
            on = piece == i
            reach = g[on][np.isfinite(g[on])]
            if len(reach) and reach.max() >= STRAND_REACH:
                reaching += 1
                wide |= _spread(points[on])[1] > NARROW
        return (hold, piece, held), reaching, wide

    top = max_distance[members].max()
    now, count, wide = level(cloth_chains.PINNED)
    if not arm:
        return now
    hold = cloth_chains.PINNED
    while wide and hold < top:
        hold += HOLD_STEP
        now, count, wide = level(hold)
    while hold < top:
        after, more, wide = level(hold + HOLD_STEP)
        if wide or more <= count:
            break
        hold += HOLD_STEP
        now, count = after, more
    return now


def _sewn(geo, data, d, sim, base):
    """The strands sewn onto simulation mesh `sim` (strands() of its section, base: the section's first vertex; Reina's
    jacket's hem cords, modelled sticking out from it) in its particles' numbers (d: particles()'): [(the strand's
    particles, those it hangs from)]."""
    si = d['section']
    moved = data['moved'].get(si)
    if moved is None:
        return []
    out = []
    for v, hangs, _ in strands(geo['positions'][base:base + len(moved)], geo['triangles'][si] - base, moved):
        number = d['of'][v]
        if (data['mesh_of'][si][v] != sim).any() or (number < 0).any():
            continue
        strand = np.zeros(len(d['max_distance']), bool)
        strand[number] = True
        hang = np.zeros_like(strand)
        hang[number[hangs]] = True
        out.append((strand, hang))
    return out


def _own_reach(points, held, on, triangles):
    """How far (mm, along its own triangles: the asset rig() gets) a piece's particles (on) reach from the held ones
    it hangs from; a piece joined to them only through other particles' triangles (Miary Zo's two short back-hair
    strands, sewn on with the cloth's welded particles) reaches no further than its own triangles go."""
    g = cloth_chains._hang(points, held, cloth_chains._edges(triangles, len(points))[1])[0][on]
    return float(g[np.isfinite(g)].max()) if np.isfinite(g).any() else 0.0


def pieces(k, tag, info, geo, data, solver, drawn, local, used, log=print, drawn_sims=None):
    """The pieces of a part's simulated cloth that swing (find() with particles()' solver data): per simulation
    mesh, per island of its particles, the hold level (_hold), then each free piece (_components) that
    * is narrow (_spread across it at most NARROW: a cord, a fringe strip, a strap end), reaches STRAND_REACH, may
      move at least SWING of its own length (above the hold level) and does not lie on the body (LYING: a boot's
      lace ends), or
    * is wide (a coat's tails, a skirt) and may move at least cloth.FREE_MIN, as Tekken 7's cloth must; the strands
      sewn onto it (_sewn) are pieces of their own, hanging from where they are sewn on, moving their max distance;
    -> [cloth for convert/cloth.add]: its asset the piece and the held particles it hangs from (their max distance 0,
    the piece's its max distance above the hold level), its drawn vertices those the game moves with this simulation
    mesh whose nearest particle of the part's (in Tekken 8's own bind: _bind_points) is one of these, 'body_parent'. A narrow piece has strand chains (link
    STRAND_LINK, reach STRAND_REACH): on an arm with ARM_SPRING entries, its modelled shape kept if Tekken 8 models it
    hanging (in its own pose: tilted at most ARM_HANGING from straight down: Azucena's fringes), laid along the arm if
    not (_hanging: Reina's strap ends); elsewhere hung if modelled tilted more than STRAND_FLOWING. A wide one has
    Tekken 7's, and hangs from the thigh its vertices are skinned to ('leg_parent'). A piece that reaches its shortest
    chain only through other pieces' triangles makes none: left. The hair's (HAIR_PARTS) are 'hair' with HAIR_SPRING
    entries.
    drawn_sims (a definition's TEKKEN8['drawn_cloth']): a pattern of simulation mesh names whose particles are a
    drawn section's own vertices (no proxy: Azazel's bandages); those vertices follow it too (else only the
    vertices catwalk()'s 'driven' gives do, none for such a mesh: it stays skinned, as modelled), it is held only
    where Tekken 8 pins it, on an arm too (free strips 1.5 m long, not sleeves: no hold raised by HOLD_STEP), an
    island mostly held (a wrap) up to DRAWN_FREE, and its wide pieces' chains have DRAWN_LINKS links."""
    if not solver:
        return []
    pos = k['prims'][0]['pos']
    sections = info['mesh'].lods[0].sections
    sims = sorted(solver)
    posed = {sim: _posed(k, info, geo, sections[solver[sim]['section']].base_vertex + solver[sim]['vertex'])
             for sim in sims}
    every = np.concatenate([posed[sim] for sim in sims])
    owner_sim = np.concatenate([np.full(len(posed[sim]), sim) for sim in sims])
    owner = np.concatenate([np.arange(len(posed[sim])) for sim in sims])
    # the drawn vertices go to their nearest particles where Tekken 8 models them (its own bind: geo's positions),
    # not where the re-posing put them: turned into a donor's bind with the feet closer together, two wide pieces
    # worn on the ankles (Miary Zo's boards) meet at the middle, so some of the right one's vertices took the left
    # leg's strand (and the left's the right's): a stick from ankle to ankle once the legs parted
    own_bind = np.concatenate([_bind_points(geo, sections[solver[sim]['section']].base_vertex + solver[sim]['vertex'])
                               for sim in sims]) if local is not None else None
    out, still = [], []
    for sim in sims:
        d = solver[sim]
        points, distance = posed[sim], d['max_distance']
        base = sections[d['section']].base_vertex
        mesh = data['meshes'].get(sim, '?').rsplit('|', 1)[-1]
        itself = bool(drawn_sims and re.search(drawn_sims, mesh) and not sections[d['section']].cloth_mapping)
        if local is not None:
            driven = _driven(data, sections, sim, local)
            if itself:                                               # (its own drawn vertices)
                inside = (local >= base) & (local < base + len(d['of']))
                driven[inside] |= d['of'][local[inside] - base] >= 0
            candidates = drawn[driven]
            nearest = cloth_chains._nearest(_bind_points(geo, local[driven]), own_bind)[0] if len(candidates) \
                else np.zeros(0, np.int64)
        else:
            candidates = drawn
            nearest = cloth_chains._nearest(pos[candidates], every)[0] if len(candidates) else np.zeros(0, np.int64)
        mine = owner_sim[nearest] == sim
        candidates, nearest = candidates[mine], owner[nearest[mine]]
        body = pos[np.setdiff1d(used, drawn if tag in HAIR_PARTS else candidates)]   # (LYING)
        _, adjacency = cloth_chains._edges(d['triangles'], len(points))
        island = _islands(d['triangles'], len(points))
        swing, left, lines, holds = [], [], [], []
        sewn = None
        for i in np.unique(island[island >= 0]):
            members = island == i
            if distance[members].max() <= cloth_chains.PINNED:
                continue
            arm = not itself and _on_arm(k, info, geo, base + d['vertex'][members])
            if itself and np.median(distance[members]) < DRAWN_FREE:      # (a wrap on the body: its loose ends)
                held = members & (distance <= DRAWN_FREE)
                hold, piece = DRAWN_FREE, _components(members & ~held, adjacency)
            else:
                hold, piece, held = _hold(points, distance, members, adjacency, arm)
                if hold > cloth_chains.PINNED:
                    holds.append(hold)
            found = []                                               # [(piece, what it hangs from, hold level)]
            for j in range(piece.max() + 1):
                on = piece == j
                if _spread(points[on])[1] > NARROW:                  # (the strands sewn on it hang on their own)
                    sewn = _sewn(geo, data, d, sim, base) if sewn is None else sewn
                    for strand, hang in sewn:
                        if (strand & on).sum() * 2 > strand.sum():
                            on = on & ~(strand & ~hang)
                            found.append((strand & ~hang, hang, 0.0))   # (it swings as far as it may move)
                found.append((on, held, hold))
            for on, hangs, level in found:
                g, _ = cloth_chains._hang(points, hangs, adjacency)
                reach = g[on][np.isfinite(g[on])]
                if not len(reach) or reach.max() < STRAND_REACH:
                    continue
                reach = float(reach.max())
                moves = float(distance[on].max()) - level
                narrow = _spread(points[on])[1] <= NARROW
                what = '%s %.0f mm long' % ('a strand' if narrow else 'cloth', reach)
                if narrow and moves * 10.0 < SWING * reach or not narrow and moves < cloth_chains.FREE_MIN:
                    left.append('%s moving %.0f cm' % (what, moves))
                    continue
                if narrow:
                    lying = float(np.median(cloth_chains._nearest(points[on], body)[1])) if len(body) else np.inf
                    if lying < LYING:
                        left.append('%s lying on the body (%.0f mm)' % (what, lying))
                        continue
                ring = np.zeros(len(points), bool)                   # (and the held particles it hangs from)
                for x in np.nonzero(on)[0]:
                    ring[[y for y in adjacency[x] if hangs[y]]] = True
                keep = on | ring
                number = np.full(len(points), -1, np.int64)
                number[keep] = np.arange(keep.sum())
                tris = number[d['triangles'][keep[d['triangles']].all(1)]]
                follow = candidates[keep[nearest]]
                if not len(follow):
                    left.append('%s: no drawn vertices follow it' % what)
                    continue
                p = points[keep]
                own = _own_reach(p, ring[keep], on[keep], tris)
                if own < (STRAND_REACH if narrow else cloth_chains.REACH):     # (no chain: rig drops it)
                    left.append('%s, %.0f mm of it joined to where it hangs' % (what, own))
                    continue
                vertices = np.stack([p[:, 0], p[:, 2], p[:, 1]], 1) / 10.0
                free = np.maximum(distance[keep] - level, 2 * cloth_chains.PINNED)
                c = dict(part=tag, asset=Strand(vertices, np.where(on[keep], free, 0.0), tris), vertices=follow,
                         name='%s %s piece %d' % (tag, mesh, len(swing)), body_parent=True)
                how = ''
                if narrow:
                    c.update(link=STRAND_LINK, reach=STRAND_REACH, down=None, flowing=STRAND_FLOWING)
                    if arm:                                          # (modelled hanging in Tekken 8's own pose?)
                        c['spring'] = ARM_SPRING
                        raw = geo['positions'][base + d['vertex']].astype(np.float64)
                        tip = raw[np.nonzero(on)[0][np.argmax(g[on])]] - raw[ring].mean(0)
                        if tip[2] < -np.cos(ARM_HANGING) * np.linalg.norm(tip):
                            c['flowing'], how = np.pi, ' (from an arm: as modelled)'
                        else:
                            c['down'], c['flowing'] = _hanging(k, info, geo, base + d['vertex'][ring],
                                                               points[ring].mean(0))
                            how = ' (from an arm: laid along it)'
                elif itself:                                         # (a drawn strip metres long: few links)
                    c['link'] = max(cloth_chains.LINK, reach / DRAWN_LINKS)
                if tag in HAIR_PARTS:                                # (hair: its own entries, no capsules)
                    c.update(hair=True, spring=HAIR_SPRING)
                    how += ' (hair)'
                else:                                                # (hung from a leg it moves with it; a wide
                    c['leg_moves'] = True                            # piece Tekken 8 skins to a thigh hangs from it)
                    c['leg_parent'] = not narrow
                swing.append(c)
                lines.append('    %s: %s, moving %.0f cm, %d drawn vertices%s' % (c['name'], what, moves,
                                                                                 len(follow), how))
        if swing:
            log('  %s %s: %d piece%s swing%s%s' % (
                tag, mesh, len(swing), '' if len(swing) == 1 else 's', ' (held up to %s cm on the arm)' % '/'.join(
                    '%.1f' % h for h in holds) if holds else '', '; left skinned: %s' % '; '.join(left) if left else ''))
            for line in lines:
                log(line)
        else:
            still.append('%s (%.0f cm)' % (mesh, distance.max()))
        out += swing
    if still:
        log('  %s: simulated, moving too little to swing, skinned: %s' % (tag, ', '.join(still)))
    return out


def find(k, parts, log=print, drawn_sims=None):
    """The cloth of the costume's parts Tekken 8 simulates and that swings, as convert/cloth.find gives Tekken 7's:
    [{'part', 'asset' (Strand), 'vertices' (the drawn vertices in k's streams), 'name', and for rig 'link', 'reach',
    'down', 'flowing' (strands)}]: pieces() of the simulation meshes whose particles the solver data gives
    (particles()), strands() of the others. k: the model as model.tekken8_model makes it (decimated, re-posed);
    parts: [(tag, path)]."""
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
        solver = particles(m, data, geo)
        out += pieces(k, tag, info, geo, data, solver, drawn, local, used, log, drawn_sims)
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
                if sim in solver:                                    # (its particles are read: pieces())
                    continue
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
                body = np.setdiff1d(used, drawn if tag in HAIR_PARTS else follow)          # (LYING)
                lying = float(np.median(cloth_chains._nearest(points[~hangs], pos[body])[1])) if len(body) else np.inf
                if lying < LYING:
                    left.append('%s lies on the body (%.0f mm)' % (name, lying))
                    continue
                down, flowing = _hanging(k, info, geo, base + v[hangs], points[hangs].mean(0))
                vertices = np.stack([points[:, 0], points[:, 2], points[:, 1]], 1) / 10.0
                out.append(dict(part=tag, asset=Strand(vertices, np.where(hangs, 0.0, g / 10.0), tris),
                                vertices=follow, name=name, link=STRAND_LINK, reach=STRAND_REACH, down=down,
                                flowing=flowing))
                if tag in HAIR_PARTS:
                    out[-1].update(hair=True, spring=HAIR_SPRING)
                else:
                    out[-1]['leg_moves'] = True
                log('  %s: a strand %.0f mm long%s, %d drawn vertices' % (
                    name, reach, ' (from an arm: laid along it)' if down is not None else '', len(follow)))
        if left:
            log('  %s: left skinned: %s' % (tag, '; '.join(left)))
    return out


# ------------------------------------------------------------------------------------------------ dynamic bones
# Some costumes swing chains of their own joints with Tekken 8's dynamic bones (BaseItem PhoenixDynamicBoneBinariesItem
# -> DYB_CH_<code>_<part>, 'PDYB' data naming each joint with its angle limits and a ground plane it lies on): Azazel's
# tail, PHY_Hip__a001..008 from his hips back along the floor, 4.3 m. Their skin weights are the costume's own: the
# chain's joints become extra bones with spring entries (convert/cloth.py, as the cloth's chains), resting where the
# costume is modelled (TTT2's springs swing about the bind) and touching no capsule. A definition names them
# (TEKKEN8['bone_chains']: [{'root': the first joint, 'spring': its entries (convert/cloth.py springs)}]); without it
# such joints stay as they were (their weights go to their parent's bone, rigid). TTT2 has no floor for them: a chain
# with a 'floor' (mm) rests as Tekken 8's lies in the fighter's stance (lay_on_floor): its links bent down from where
# they are modelled, each at most FLOOR_BEND more than the one before (the DYB's down limit), till they lie that high.
CHAIN_JOINT = re.compile(r'^(.*?)(\d+)$')
FLOOR_BEND = np.radians(20.0)
CHAIN_CLOTH = 90                # the joints are named as the cloth's bones (convert/cloth.py NAME: cloth, chain,
                                # link; springs() numbers them by it), as cloth number CHAIN_CLOTH + the chain's


def bone_chains(k, specs, log=print):
    """The definition's dynamic-bone chains of model k (tekken8_model's: merged bones, bind frames in TTT2 space) as
    convert/cloth.rig's chains: [{'part', 'bones' (k's bone indices, root first), 'neighbours', 'parent', 'spring',
    'hair', 'vertices' (the vertices mostly skinned to them)}]. Each joint's bind frame becomes one with X along its
    link (the last link's for the last joint), Y the world's up across it, so that the spring's limits about Y swing
    it sideways and about Z up (+) and down (-); positions stay. Changes k's bind matrices in place."""
    names, parents = list(k['bones']['names']), list(k['bones']['parents'])
    world = k['bones']['world']
    s0 = k['prims'][0]
    out = []
    for n, spec in enumerate(specs):
        root = spec['root']
        if root not in names:
            raise ValueError('the costume has no joint %s for a dynamic-bone chain' % root)
        stem = CHAIN_JOINT.match(root).group(1)
        chain = [names.index(root)]
        while True:
            kids = [j for j, p in enumerate(parents) if p == chain[-1] and CHAIN_JOINT.match(names[j])
                    and CHAIN_JOINT.match(names[j]).group(1) == stem]
            if not kids:
                break
            chain.append(kids[0])
        if len(chain) < 2:
            raise ValueError('the dynamic-bone chain %s has one joint' % root)
        at = [world[b][:3, 3].copy() for b in chain]
        for i, b in enumerate(chain):
            x = at[i + 1] - at[i] if i + 1 < len(chain) else at[i] - at[i - 1]
            m = np.eye(4)
            m[:3, :3] = cloth_chains._frame(x, np.array([0.0, 1.0, 0.0]))
            m[:3, 3] = at[i]
            world[b] = m
        held = (np.isin(s0['joints'], chain) * s0['weights']).sum(1)
        vertices = np.nonzero(held > 0.5)[0]
        part = collections_part(k, vertices)
        out.append(dict(part=part, bones=chain, neighbours=set(), parent=parents[chain[0]], name=root,
                        spring=spec['spring'], hair=True, vertices=vertices, floor=spec.get('floor')))
        length = sum(float(np.linalg.norm(at[i + 1] - at[i])) for i in range(len(at) - 1))
        log('  %s: a chain of %d joints Tekken 8 swings (dynamic bones), %.0f mm, from %s; %d vertices on it' % (
            root, len(chain), length, names[parents[chain[0]]].split('@')[0], len(vertices)))
        k['bones']['names'] = list(k['bones']['names'])      # (its own list: a second try's model shares the first's)
        for j, b in enumerate(chain):
            k['bones']['names'][b] = cloth_chains.NAME % (CHAIN_CLOTH + n, 0, j)
    return out


def collections_part(k, vertices):
    """The part most of the vertices' primitives belong to (k's prims share one vertex array)."""
    count = {}
    want = set(int(v) for v in vertices)
    for p in k['prims']:
        hit = len(want.intersection(np.unique(p['tris']).tolist()))
        count[p['part']] = count.get(p['part'], 0) + hit
    return max(count, key=count.get)


def stance(store, d, moveset, files):
    """A function: the fighter's TTT2 skeleton (skeleton.build's, its chains not yet added) -> its world matrices in
    the first frame of its stance (alias 1's clip, converted as its moves' are, tekken8/anim.py; its root where the
    game plays it: the root channel times the skeleton's scale), for lay_on_floor. moveset: its Tekken 8 moveset,
    files: its saved files (importer tekken8_moveset)."""
    from . import anim, anmbin, panm
    banks = anmbin.Banks(anmbin.Bank(files['anmbin']), anmbin.Bank(files['common']), moveset.character_id)
    key = banks.anim_key(moveset.tables['moves'][moveset.resolve_alias(0x8001)]['anim'] & ~0xC000)
    clip = panm.Animation(banks.blob(anmbin.BODY, key))
    rig = anim.load_skeleton(store, d.TEKKEN8_CODE)

    def posed(skel):
        conv = anim.Converter(rig, skel)
        values = np.array(conv.channels(clip)[0][0], np.float64)
        values[:2] *= skel['scale']
        return cloth_chains.pose(skel, (values, conv.kind))
    return posed


def lay_on_floor(k, chains, skel, parents, posed):
    """The chains with a 'floor' (bone_chains) bent to rest on the floor in the stance (posed: stance()'s matrices of
    skel, the skeleton without the chains; parents: each chain's parent in it): in the stance at rest on its parent, each
    link keeps its heading and tilts down as far as reaches `floor` mm above the floor, at most FLOOR_BEND more than
    the link before it; one modelled below that rises to it. Changes k's bind matrices and vertex streams in place.
    -> [(chain root, [joint heights in the stance, mm])], vertices moved."""
    from ..convert import chains as hanging
    from ..ttt2 import bone
    names = list(k['bones']['names'])
    world = k['bones']['world']
    before = world.copy()
    bind = bone.world_matrices(skel)
    laid = []
    for chain, parent in zip(chains, parents):
        floor = chain.get('floor')
        if floor is None:
            continue
        to_pose = posed[parent] @ np.linalg.inv(bind[parent])        # (at rest on its parent)
        frames = [to_pose @ before[b] for b in chain['bones']]
        tilt = None                                                  # (the link before's, rad: + up)
        for j in range(1, len(frames)):
            pivot = frames[j - 1][:3, 3].copy()
            link = frames[j][:3, 3] - pivot
            length = float(np.linalg.norm(link))
            flat = np.array([link[0], 0.0, link[2]])
            if np.linalg.norm(flat) < 1e-6:
                flat = np.array([frames[j - 1][0, 2], 0.0, frames[j - 1][2, 2]])
            flat = flat / np.linalg.norm(flat)
            now = float(np.arcsin(np.clip(link[1] / length, -1.0, 1.0)))
            reach = -float(np.arcsin(np.clip((pivot[1] - floor) / length, -1.0, 1.0)))   # (its end on the floor)
            want = max(reach, min(now, (now if tilt is None else tilt) - FLOOR_BEND))
            if now < reach:
                want = reach
            tilt = want
            r = hanging.turn(link / length, flat * np.cos(want) + np.array([0.0, 1.0, 0.0]) * np.sin(want))
            for f in frames[j - 1:]:                                 # (the link's bone turns, and all below it)
                f[:3, :3] = r @ f[:3, :3]
                f[:3, 3] = pivot + r @ (f[:3, 3] - pivot)
        back = np.linalg.inv(to_pose)
        for b, f in zip(chain['bones'], frames):
            world[b] = back @ f
        laid.append((chain.get('name', names[chain['bones'][0]]), [float(f[1, 3]) for f in frames]))
    changed = [b for chain in chains if chain.get('floor') is not None for b in chain['bones']]
    return laid, hanging.follow(k, before, changed) if changed else 0
