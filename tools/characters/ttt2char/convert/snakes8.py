"""A Tekken 8 fighter's summoned model with a skeleton and animations of its own (Miary Zo's snakes: summon 16, an
actor Tekken 8 attaches to her right forearm) -> extra bones of the fighter's played from part 3 of its motion pack,
the TTT2 side of what the runtime already does for a Tekken 7 summoned model (convert/tiger.py; title/roster.cpp,
extra bones):

* MESH. The definition's SNAKES['mesh'] (SK_CH_wkz_exp_mwsh): the three snakes and a coil Tekken 8 calls the dambe
  (shown in one clip only), on their own skeleton: Root, ATH_center, per snake X (A, B, C) ATH_snake_X,
  ATH_neck_X_01..12, ATH_head_X, ATH_jaw_X, and ATH_snake_dambe. The bones kept (kept()): the center, the dambe,
  each snake's base, the necks SNAKES['necks'], its head and jaw (23 with necks 2, 5, 8, 11: every vertex within 3.8
  cm (p99) of the full skinning over the 16 clips; without the jaws 14 cm more: they open wide). A neck left out
  gives its weights to the kept joints before and after it on its snake, linearly by place (base 0, necks 1..12,
  head 13); Root holds no vertices. Each section (the snakes 'snk', the dambe 'dmb': by the bones it is weighted to)
  is decimated alone to its SNAKES['vertices'].
* PLACE. Tekken 8 attaches the snakes' component to her R_LowerArm with the relative transform kept, the identity:
  its space is her forearm joint's frame (UE axes). In TTT2 their roots hang under a still weapon bone
  (SNAKES['parent'], at UDE_R_jnt, the identity local, summoned with summon 4: the runtime collapses it while the
  summon is off, and every bone under it with it), numbered PARENT_NUMBER (the definition's 'number'): the game makes
  the world matrices of a fighter's OPT bones in number order (convert/recordorder.py), so the parent comes before
  them (as OPT 821 their roots took its world of the frame before: 0.2-0.4 m behind her arm, median, in a fight).
  Her UE joint frames are P R D (P swaps y and z, D = diag(1, -1,
  1): tekken8/anim.py) and UDE_R_jnt's world rotation is S_driver O (O: its calibration offset, driver R_LowerArm),
  so a point x (cm) of the snakes' space is O^T D x * 10 (mm) in UDE_R_jnt's frame, a kept root bone of world G
  (rotation R, position t: the snakes' space) has the local (O^T D R P, O^T D t * 10) and a kept bone under kept
  bone q the local P (G_q^-1 G) P (its translation * 10). The bind takes the same form with any rotation for O (the
  calibration as the model step has it): the vertices are bound with it, so where the bind puts them is no matter.
* ANIMATIONS. The data table SNAKES['animations'] (MissileAnimData) lists the clips by index (AnimDatas[k]
  ['Animation']); each is an AnimSequence of the per-track codec (tekken8/ue5anim.py) that locks the root
  (bForceRootLock: Root keeps its reference pose). Each becomes a raw part-3 animation (tiger.raw_animation: per
  kept bone translation, rotation, scale), led by its first frame once more and ended by REST's pose: the
  runtime shows index int(animator frame) (title/roster.cpp, sub_069D8B30), 1 on the start property's frame (seen
  in a fight: the bones' locals = index int(frame), 1e-7), so index 1 is the clip's frame 0 (LEAD), and it writes
  the last frame again after the end; REST (the roots' scale 0) folds them all into the elbow. Every clip of hers
  outlasts the snakes' show (seen in fights: hidden well before their clip's last frame), so a clip's end frame is
  seen only when its animation ends early: the animator reset by a KO's replay (the move replayed from a later
  frame) or a round's start with the snakes still summoned, where its last frame would leave them drawn, still,
  till a move dismisses them (seen: 320 frames into the next round).
* MOVES (prepare). Tekken 8 starts clip k with START_PROP (value k; at a frame, AT_START its first) and stops it with
  STOP_PROP: STOP_PROP becomes START_PROP REST, and the converter turns START_PROP into 0x82de 0x4000 + the
  animation's index in part 3 (moveset.TIGER_PROP['t8'], Converter.opt_anims). A continuation (a cancel into a move
  of the same body animation from a start frame on, with no start of its own: 2RP's #1663, 3LPLPRP's #1672) starts
  a copy of the clip from where the move it continues would be (COPY_FIRST + n), whether the end properties of the
  move before stopped it or not; one starting before the clip does gets its start row as it is. A cancel into a
  continuation whose window opens before its start frame (21..24, start 24: 2RP's #1663 on a downed opponent) is
  taken where it opens, and its end properties (REST) run then while the move plays on to the start frame: the
  snakes folded away for those frames (3 in a fight); its window is made to open at the start frame.
* HIT POINT. Her snake moves hit from 121 (the snakes' heads); the snake weapon's pair (a definition weapon with
  'snakes': True, under UDE_R_jnt) carries, in each body animation whose move starts a clip, the most forward of
  the heads in UDE_R_jnt's frame (tekken8/anim.py pair_values, heads()), from the clip's start frame on (before it:
  its first frame); FRAME_OFFSET is how many frames after its property's frame the runtime shows a part-3
  animation's frame 0 beyond the body's (0: on move frame x the body shows its frame index x - 1, seen in a fight
  through the pair's record, and LEAD puts the clip's frame x - 1 - start there too).

Written for this project from the files themselves (no third-party code).
"""
import collections

import numpy as np

from ..tekken7 import mesh as t7mesh
from ..ttt2 import bone
from . import retarget, tiger

START_PROP, STOP_PROP = 0x83aa, 0x83ab      # Tekken 8: start the summoned object's animation k / stop it
REST = 0xFFFF                               # START_PROP value prepare() gives STOP_PROP rows (the REST animation)
PARENT_NUMBER = 599                         # the still weapon they hang under: before OPT_FIRST (character.ini
                                            # k = -201: weapons.number_of)
COPY_FIRST = 0x1000                         # START_PROP values of the continuations' copies (COPY_FIRST + n)
AT_START = 0x8001                           # a property frame: the move's first
FRAME_OFFSET = 0                            # frames between a part-3 start property's frame and its first frame shown
LEAD = 1                                    # frames before a part-3 animation's frame 0 (index 0: never shown)
OPT_FIRST = tiger.OPT_FIRST                 # the first bone's number (cha:OPT600_..)
NAME_LENGTH = tiger.NAME_LENGTH
CHAINS = 'ABC'
NECKS = 12                                  # neck joints of a snake
CENTER, DAMBE = 'ATH_center', 'ATH_snake_dambe'
CM = 10.0                                   # cm -> mm
P = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
D = np.diag([1.0, -1.0, 1.0])
PROP_TABLES = ('extra_move_properties', 'move_begin_props', 'move_end_props')
GROUP, LIST_END = 0x800B, 0x8000            # a cancel row of a group / a cancel list's end (idmaps)


def spec(d):
    """The definition's SNAKES, or None."""
    return getattr(d, 'SNAKES', None)


def bone_count(d):
    """The extra bones the snakes take (0 without them): the center, the dambe, per snake its base, kept necks, head
    and jaw."""
    s = spec(d)
    return 0 if not s else 2 + len(CHAINS) * (len(s['necks']) + 3)


def vertices(d):
    """The vertices the snakes' meshes are decimated to (0 without them)."""
    s = spec(d)
    return 0 if not s else int(sum(s['vertices'].values()))


def spring_numbers(d, skel):
    """The OPT numbers of the snakes' bones and their parent below 800 (PARENT_NUMBER) in skeleton skel ([] without
    them): each gets a still spring entry (flag 8, as a tiger's: the importer's spring_file; a bone in the OPT list
    without one swings under gravity)."""
    if not spec(d):
        return []
    w = next((w for w in getattr(d, 'WEAPONS', []) if w['bone'] == spec(d).get('parent')), None)
    up = w.get('number') if w else None
    return [n for n in skel['opt'] if OPT_FIRST <= n < OPT_FIRST + bone_count(d) or up is not None and n == up]


# ------------------------------------------------------------------------------------------------ skeleton
def chain_place(name):
    """(snake, place: 0 its base, 1..12 its necks, 13 its head, 14 its jaw) of a snake bone, else None."""
    for s in CHAINS:
        if name == 'ATH_snake_' + s:
            return s, 0
        if name == 'ATH_head_' + s:
            return s, NECKS + 1
        if name == 'ATH_jaw_' + s:
            return s, NECKS + 2
        if name.startswith('ATH_neck_%s_' % s) and name[-2:].isdigit():
            return s, int(name[-2:])
    return None


def chain_name(s, q):
    return 'ATH_snake_%s' % s if q == 0 else 'ATH_head_%s' % s if q == NECKS + 1 else \
        'ATH_jaw_%s' % s if q == NECKS + 2 else 'ATH_neck_%s_%02d' % (s, q)


def kept(names, necks):
    """The indices of the bones kept (in the skeleton's order: parents first)."""
    want = {CENTER, DAMBE}
    for s in CHAINS:
        want |= {chain_name(s, q) for q in [0] + sorted(necks) + [NECKS + 1, NECKS + 2]}
    out = [i for i, n in enumerate(names) if n in want]
    if len(out) != len(want):
        raise ValueError('the snakes\' skeleton has no %s' % ', '.join(sorted(want - {names[i] for i in out})))
    return out


def kept_parents(parents, keep):
    """Each kept bone's nearest kept ancestor (its place in keep), or -1 (a root: under the weapon bone)."""
    at = {b: k for k, b in enumerate(keep)}
    out = []
    for b in keep:
        p = parents[b]
        while p >= 0 and p not in at:
            p = parents[p]
        out.append(at[p] if p >= 0 else -1)
    return out


def remap(names, parents, keep):
    """{bone: [(place in keep, share)]}: a kept bone itself, a neck left out the kept joints before and after it on
    its snake (linearly by place), a jaw left out its head, any other bone its nearest kept ancestor (none: [])."""
    at = {b: k for k, b in enumerate(keep)}
    index = {n: i for i, n in enumerate(names)}
    out = {}
    for b, n in enumerate(names):
        if b in at:
            out[b] = [(at[b], 1.0)]
            continue
        cp = chain_place(n)
        if cp is not None and cp[1] == NECKS + 2:
            cp = (cp[0], NECKS + 1)
            if index.get(chain_name(*cp)) in at:
                out[b] = [(at[index[chain_name(*cp)]], 1.0)]
                continue
        if cp is not None:
            s, q = cp
            have = [r for r in range(NECKS + 2) if index.get(chain_name(s, r)) in at]
            lo, hi = [r for r in have if r < q], [r for r in have if r > q]
            if lo and hi:
                a, c = lo[-1], hi[0]
                f = (q - a) / float(c - a)
                out[b] = [(at[index[chain_name(s, a)]], 1.0 - f), (at[index[chain_name(s, c)]], f)]
                continue
        p = parents[b]
        while p >= 0 and p not in at:
            p = parents[p]
        out[b] = [(at[p], 1.0)] if p >= 0 else []
    return out


def remap_weights(joints, weights, table, count, influences=8):
    """Skin weights on the skeleton's bones -> on the kept ones (remap()'s table, count of them): the largest
    `influences`, normalised. -> (joints (n, influences), weights (n, influences), weight lost on bones mapped to
    nothing)."""
    n = len(joints)
    dense = np.zeros((n, count))
    lost = 0.0
    for b in np.unique(joints[weights > 0]):
        w = np.where(joints == b, weights, 0.0).sum(1)
        if not table.get(int(b)):
            lost += float(w.sum())
            continue
        for k, share in table[int(b)]:
            dense[:, k] += w * share
    order = np.argsort(-dense, 1, kind='stable')[:, :influences]
    top = np.take_along_axis(dense, order, 1)
    total = top.sum(1, keepdims=True)
    top = np.where(total > 0, top / np.maximum(total, 1e-12), 0.0)
    top[total[:, 0] <= 0, 0] = 1.0
    return order.astype(np.int64), top, lost


def ttt2_locals(G, parents, keep, O):
    """TTT2 locals (..., kept, 4, 4) (mm) of the kept bones from their worlds G (..., bones, 4, 4) in the snakes'
    space (cm): a root under the weapon bone (O: UDE_R_jnt's offset) (O^T D R P, O^T D t * 10), a bone under kept
    bone q P (G_q^-1 G) P (translation * 10)."""
    G = np.asarray(G, np.float64)
    up = kept_parents(parents, keep)
    A = np.asarray(O, np.float64).T @ D
    out = np.zeros(G.shape[:-3] + (len(keep), 4, 4))
    out[..., 3, 3] = 1.0
    for k, b in enumerate(keep):
        if up[k] < 0:
            out[..., k, :3, :3] = A @ G[..., b, :3, :3] @ P
            out[..., k, :3, 3] = np.einsum('ij,...j->...i', A, G[..., b, :3, 3]) * CM
        else:
            L = np.linalg.inv(G[..., keep[up[k]], :, :]) @ G[..., b, :, :]
            out[..., k, :3, :3] = P @ L[..., :3, :3] @ P
            out[..., k, :3, 3] = np.einsum('ij,...j->...i', P, L[..., :3, 3]) * CM
    return out


def decompose(L):
    """Locals (..., 4, 4) -> (translations, rotations as TTT2's angles (R = Rz Ry Rx), scales): the scale of each
    column (the runtime scales the record's rows: tiger.py)."""
    s = np.linalg.norm(L[..., :3, :3], axis=-2)
    R = L[..., :3, :3] / np.maximum(s[..., None, :], 1e-12)
    return L[..., :3, 3].copy(), retarget._euler(R), s


def world_poses(pose, parents):
    """(frames, bones, 4, 4) worlds of (frames, bones, 10) local poses (t7mesh's pose rows)."""
    F, n = pose.shape[:2]
    L = t7mesh.local_matrices(pose.reshape(-1, 10)).reshape(F, n, 4, 4)
    G = np.empty_like(L)
    for i, p in enumerate(parents):
        if p >= i:
            raise ValueError('bone %d has its parent %d after it' % (i, p))
        G[:, i] = L[:, i] if p < 0 else G[:, p] @ L[:, i]
    return G


def locked(pose, parents, reference):
    """Local poses (frames, bones, 10) with the roots' translation and rotation at the reference pose's
    (bForceRootLock)."""
    pose = np.array(pose, np.float64)
    for i, p in enumerate(parents):
        if p < 0:
            pose[:, i, 0:7] = reference[i, 0:7]
    return pose


# ------------------------------------------------------------------------------------------------ model
def offset_of(source, d, skel):
    """UDE_R_jnt's calibration offset (tekken8/anim.py's Converter on skel: the TTT2 skeleton the snakes hang from),
    and its driver's name."""
    from ..tekken8 import anim
    parent = weapon(d)['parent']
    cal = retarget.Calibration(anim.load_skeleton(source.store, d.TEKKEN8_CODE), anim.LANDMARKS, anim.DRIVERS,
                               retarget.ttt2_skeleton(skel))
    if parent not in cal.offsets:
        raise ValueError('the snakes\' weapon hangs under %s, which no Tekken 8 joint drives' % parent)
    return np.asarray(cal.offsets[parent], np.float64), cal.drivers[parent]


def weapon(d):
    """The still weapon the snakes hang under (the definition's WEAPONS entry named SNAKES['parent'])."""
    name = spec(d)['parent']
    w = next((w for w in getattr(d, 'WEAPONS', []) if w['bone'] == name), None)
    if w is None:
        raise ValueError('no weapon %s for the snakes to hang under' % name)
    return w


def heads_in(G, heads, O):
    """(frames, len(heads), 3) positions (mm) in UDE_R_jnt's frame of the bones `heads` of worlds G (frames, bones,
    4, 4) in the snakes' space (cm). (Indexed in two steps: G[:, heads, :3, 3] would put the heads' axis first.)"""
    G = np.asarray(G, np.float64)
    return np.einsum('ij,fmj->fmi', np.asarray(O, np.float64).T @ D, G[:, list(heads)][:, :, :3, 3]) * CM


def mesh_streams(geo, keep, table, W, A):
    """The snakes' vertex streams in TTT2 model space (mm): v -> W (A^T D v * 10) (W: the weapon bone's bind world,
    A its offset), normals and tangents turned alike (a reflection: the bitangent sign flips), skin weights on the
    kept bones (remap()'s table). -> (streams, lost weight)."""
    M = W[:3, :3] @ (np.asarray(A, np.float64).T @ D)
    pos = (np.asarray(geo['positions'], np.float64) * CM) @ M.T + W[:3, 3]
    nrm = np.asarray(geo['normals'], np.float64)[:, :3] @ M.T
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    tan = np.asarray(geo['tangents'], np.float64).copy()
    tan[:, :3] = tan[:, :3] @ M.T
    tan[:, :3] /= np.maximum(np.linalg.norm(tan[:, :3], axis=1, keepdims=True), 1e-12)
    if np.linalg.det(M) < 0:
        tan[:, 3] = -tan[:, 3]
    joints, weights, lost = remap_weights(np.asarray(geo['joints'], np.int64), np.asarray(geo['weights'], np.float64),
                                          table, len(keep))
    uv = np.asarray(geo['uvs'], np.float64)
    uv = uv[:, 0] if uv.ndim == 3 else uv
    return dict(pos=pos, nrm=nrm, tan=tan, uv=uv, joints=joints, weights=weights), lost, np.linalg.det(M) < 0


def append_bones(skel, names, up, locals_, parent):
    """The skeleton with the kept bones after its own (cha:OPT600_<name>.., listed in its OPT list): roots under bone
    `parent`, the others under their kept parents (up: kept_parents), at their bind locals (mm, scale left out).
    -> (skeleton, first index)."""
    first = len(skel['names'])
    s = dict(skel)
    for key in ('names', 'parent', 'opt'):
        s[key] = list(skel[key])
    s['names_raw'] = None
    ts, rs, ss = list(skel['t']), list(skel['r']), list(skel['s'])
    for k, name in enumerate(names):
        t, r, _ = decompose(locals_[k])
        s['names'].append(('cha:OPT%d_%s' % (OPT_FIRST + k, name))[:NAME_LENGTH])
        s['parent'].append(parent if up[k] < 0 else first + up[k])
        s['opt'].append(OPT_FIRST + k)
        ts.append(t)
        rs.append(r)
        ss.append(np.ones(3))
    s['t'], s['r'], s['s'] = np.array(ts, np.float32), np.array(rs, np.float32), np.array(ss, np.float32)
    return s, first


def model(source, d, skel, log=print):
    """The snakes as extra bones of skel (the fighter's skeleton with its weapons) and their meshes. -> (skeleton,
    first bone index, prims (parts 'snk' / 'dmb', the model dict's form, their own streams, skin joints = places
    among the kept bones), parts [(tag, mesh path)])."""
    from . import decimate, weapons as weapons_mod
    from ..tekken8 import mesh as t8mesh
    sp = spec(d)
    m = t8mesh.SkeletalMesh(source.store, sp['mesh'])
    names, parents = list(m.skeleton['names']), list(m.skeleton['parents'])
    keep = kept(names, sp['necks'])
    up = kept_parents(parents, keep)
    table = remap(names, parents, keep)
    host = weapons_mod.parent_index(skel, weapon(d)['bone'])
    head = skel['names'][host].split('_', 1)[0]
    if not (head.startswith('cha:OPT') and head[7:].isdigit() and int(head[7:]) < OPT_FIRST):
        log('  snakes: WARNING: their parent %s is numbered after them: a frame behind it in the game' % (
            skel['names'][host]))
    W = bone.world_matrices(skel)[host]
    try:                                         # (any rotation would do: the vertices are bound with it)
        A, _ = offset_of(source, d, skel)
    except (ValueError, KeyError) as e:
        log('  snakes: bound with the forearm\'s nominal offset (%s)' % e)
        A = np.diag([1.0, -1.0, -1.0])
    G = t7mesh.global_matrices(np.asarray(m.skeleton['pose'], np.float64), parents)
    scales = np.linalg.norm(G[:, :3, :3], axis=1)
    if np.abs(scales[keep] - 1.0).max() > 1e-3:
        raise ValueError('the snakes\' bind has scaled bones (%.4f..%.4f)' % (scales.min(), scales.max()))
    binds = ttt2_locals(G, parents, keep, A)
    skel, first = append_bones(skel, [names[b] for b in keep], up, binds, host)
    geo = m.geometry(0)
    streams, lost, flip = mesh_streams(geo, keep, table, W, A)
    if lost > 1e-3:
        log('  snakes: WARNING: skin weight %.1f on bones without a kept one (left on the strongest)' % lost)
    at_dambe = keep.index(names.index(DAMBE))
    prims = []
    for si, s in enumerate(m.lods[0].sections):
        if s.cloth_mapping:
            continue
        tri = np.asarray(geo['triangles'][si], np.int64)
        used = np.unique(tri)
        share = float(np.where(streams['joints'][used] == at_dambe, streams['weights'][used], 0.0).sum() / max(
            len(used), 1))
        prims.append(dict(part='dmb' if share > 0.5 else 'snk', material=m.material_name(s.material_index),
                          tris=tri[:, [0, 2, 1]] if flip else tri, **streams))
    one = {'bones': {'names': names}, 'prims': prims}
    before = {tag: decimate.count({'prims': [p for p in prims if p['part'] == tag]}) for tag in ('snk', 'dmb')}
    for tag, n in sorted(sp['vertices'].items(), key=lambda x: x[1]):
        size = decimate.count({'prims': [p for p in one['prims'] if p['part'] == tag]})
        if size > n:
            one = decimate.decimate(one, decimate.count(one) - (size - int(n)),
                                    {t: 1.0 if t == tag else 0.0 for t in sp['vertices']}, log=log)
    prims = one['prims']
    after = {tag: decimate.count({'prims': [p for p in prims if p['part'] == tag]}) for tag in ('snk', 'dmb')}
    log('  snakes: %d extra bones (OPT %d..%d, of their %d) under %s, %s' % (
        len(keep), OPT_FIRST, OPT_FIRST + len(keep) - 1, len(names), skel['names'][host],
        ', '.join('%s %d -> %d vertices' % (tag, before[tag], after[tag]) for tag in ('snk', 'dmb'))))
    return skel, first, prims, [('snk', sp['mesh']), ('dmb', sp['mesh'])]


# ------------------------------------------------------------------------------------------------ animations
def clip_paths(store, table):
    """The clip paths of a MissileAnimData table (AnimDatas[k]['Animation']), by index."""
    from ..tekken8 import uprops
    pkg = store.package(table)
    ex = next((e for e in pkg.exports if e.class_name == 'MissileAnimDataAsset'), pkg.exports[0])
    props, _ = uprops.read(pkg, ex)
    out = []
    for a in props.get('AnimDatas') or []:
        path = (a or {}).get('Animation')
        out.append(path.split('.')[0] if isinstance(path, str) and path else None)
    return out


class Snakes:
    """The snakes' clips on their kept bones (store: tekken8.store.Store, d: the definition, O: UDE_R_jnt's
    calibration offset of the Converter the body animations are made with)."""

    def __init__(self, store, d, O, log=print):
        from ..tekken8 import mesh as t8mesh, ue5anim
        sp = spec(d)
        self.store, self.O, self.log = store, np.asarray(O, np.float64), log
        m = t8mesh.SkeletalMesh(store, sp['mesh'])
        self.skeleton = ue5anim.read_skeleton(store, str(m.props['Skeleton']).split('.')[0])
        names = self.skeleton['names']
        keep_mesh = kept(list(m.skeleton['names']), sp['necks'])
        self.names = [m.skeleton['names'][b] for b in keep_mesh]
        self.keep = [names.index(n) for n in self.names]
        self.heads = [names.index(chain_name(s, NECKS + 1)) for s in CHAINS]
        self.paths = clip_paths(store, sp['animations'])
        self._local = {}

    def locals_of(self, k):
        """(frames, kept, 4, 4) TTT2 locals of clip k (cached)."""
        if k not in self._local:
            from ..tekken8 import ue5anim
            sk = self.skeleton
            clip = ue5anim.read_clip(self.store, self.paths[k])
            pose = locked(ue5anim.local_poses(clip, sk), sk['parents'], np.asarray(sk['pose'], np.float64))
            G = world_poses(pose, sk['parents'])
            self._local[k] = (ttt2_locals(G, sk['parents'], self.keep, self.O), heads_in(G, self.heads, self.O))
        return self._local[k][0]

    def heads_of(self, k):
        """(frames, 3, 3) the heads' positions (mm) in UDE_R_jnt's frame through clip k."""
        self.locals_of(k)
        return self._local[k][1]

    def pairs(self, plan):
        """{body animation key: (heads (frames, 3, 3), start frame)} for tekken8/anim.Animations (plan: prepare's)."""
        return {key: (self.heads_of(k), start + FRAME_OFFSET) for key, (k, start) in plan.by_key.items()
                if 0 <= k < len(self.paths) and self.paths[k]}

    def part3(self, plan, skel):
        """(part-3 animations [bytes], {START_PROP value: index}) of the clips, REST and the plan's copies (skel: the
        fighter's skeleton, bone.read(): REST holds the bones' binds)."""
        anims, index = [], {}
        first = next(i for i, n in enumerate(skel['names']) if n.startswith('cha:OPT%d_' % OPT_FIRST))
        n = len(self.keep)
        rest = np.repeat(np.eye(4)[None], n, 0)
        for b in range(n):
            rest[b] = bone.local_matrix(skel, first + b)
            if skel['parent'][first + b] < first:            # a root: folded away
                rest[b, :3, :3] = 0.0

        def add(value, L):                                   # (led by frame 0 again, ended by REST's pose)
            t, r, s = decompose(np.concatenate([L[:1]] * LEAD + [L, rest[None]], 0))
            chans = []
            for b in range(L.shape[1]):
                chans += [(11, t[:, b]), (7, r[:, b]), (3, s[:, b])]
            index[value] = len(anims)
            anims.append(tiger.raw_animation(chans))
        for k, path in enumerate(self.paths):
            if path:
                L = self.locals_of(k)
                add(k, L)
                self.log('  snakes animation %d: %s, %d frames' % (k, path.rsplit('/', 1)[-1], len(L)))
        add(REST, np.repeat(rest[None], 1, 0))
        for c, (k, at) in enumerate(plan.copies):
            add(COPY_FIRST + c, self.locals_of(k)[at:])
        self.log('  snakes: %d part-3 animations (%d clips, REST, %d continuations\' copies), %d bytes' % (
            len(anims), sum(1 for p in self.paths if p), len(plan.copies), sum(len(a) for a in anims)))
        return anims, index


# ------------------------------------------------------------------------------------------------ moves
class Plan:
    """prepare()'s result: by_key {body animation key: (clip, start frame index)} (the heads' pairs), copies
    [(clip, first frame)] (part-3 animations COPY_FIRST + n), moves {move: (clip, start frame index)}."""

    def __init__(self):
        self.by_key, self.copies, self.moves = {}, [], {}
        self.stats = collections.Counter()


def _table(k, name):
    t = getattr(k, 'tables', None)
    return t.get(name, []) if isinstance(t, dict) else []


def start_index(frame):
    """A property frame -> the body frame index (0-based) it acts at, or None."""
    if frame == AT_START:
        return 0
    if 0 < frame < 0x8000:
        return frame - 1
    return None


def _extras(k, i):
    """[(table index, row)] of move i's extra properties (without the list's end)."""
    mv = k.tables['moves'][i]
    if mv.get('extraprops') is None:
        return []
    return [(j, r) for j, r in k.iter_list('extra_move_properties', mv['extraprops'],
                                           lambda r: r['id'] == 0 and r['frame'] == 0)
            if not (r['id'] == 0 and r['frame'] == 0)]


def _cancels(k, i):
    """Move i's cancel rows (not its groups')."""
    mv = k.tables['moves'][i]
    if mv.get('cancel') is None:
        return []
    return [c for _, c in k.iter_list('cancels', mv['cancel'], lambda c: c['direction'] == LIST_END)
            if c['direction'] not in (LIST_END, GROUP)]


def _target(k, mid):
    if mid is None:
        return None
    if mid >= 0x8000 and hasattr(k, 'resolve_alias'):
        return k.resolve_alias(mid)
    return mid


def prepare(k, d, log=print):
    """Tekken 8 moveset k (its banks attached) made ready for the converter, in place, for the definition's snakes:
    STOP_PROP rows -> START_PROP REST; each continuation of a move starting a clip -> its extra properties with a
    copy of the clip from its start frame on (a new list at the table's end). -> Plan, or None without snakes."""
    if spec(d) is None:
        return None
    plan = Plan()
    stats = plan.stats
    for table in PROP_TABLES:
        for row in _table(k, table):
            if row['id'] == STOP_PROP:
                row['id'], row['value'] = START_PROP, REST
                stats['%s rows made %s %d (REST, %s)' % (hex(STOP_PROP), hex(START_PROP), REST, table)] += 1
    moves = _table(k, 'moves')
    rows = {}                                   # move -> its start row
    for i in range(len(moves)):
        for _, r in _extras(k, i):
            if r['id'] == START_PROP and r['value'] != REST and i not in plan.moves:
                at = start_index(r['frame'])
                if at is None:
                    stats['start rows at a frame %#x (left as they are)' % r['frame']] += 1
                    continue
                plan.moves[i], rows[i] = (int(r['value']), at), r
    key = {}

    def key_of(i):
        if i not in key:
            key[i] = k.anim_ref(i)[0]
        return key[i]
    starters = sorted(plan.moves)
    for i in starters:
        kk = key_of(i)
        if kk is None:
            continue
        if kk in plan.by_key and plan.by_key[kk] != plan.moves[i]:
            stats['body animations two moves start other clips in (the first kept)'] += 1
            continue
        plan.by_key[kk] = plan.moves[i]
    # continuations: cancels into a move of the same body animation with a start frame and no start of its own
    todo = list(starters)
    seen = set(starters)
    copies = {}
    while todo:
        i = todo.pop(0)
        clip, at = plan.moves[i]
        for c in _cancels(k, i):
            j = _target(k, c['move_id'])
            if j is None or j in seen or not 0 <= j < len(moves) or key_of(j) != key_of(i) or key_of(j) is None:
                continue
            s = c.get('start_frame') or 0
            if s <= 0:
                continue
            seen.add(j)
            if c.get('win_start') is not None and c['win_start'] < s <= c.get('win_end', s):
                c['win_start'] = s              # (taken where it opens, the end properties' REST would run then)
                stats['continuations\' cancel windows made to open at their start frame'] += 1
            first = s - at                      # (move frame x shows clip frame x - 1 - at: LEAD)
            src = rows[i]
            if first <= 0:                       # (it starts before the clip: the clip's own start row)
                new = dict(src)
            else:
                if (clip, first) not in copies:
                    copies[(clip, first)] = len(plan.copies)
                    plan.copies.append((clip, first))
                new = dict(src, frame=AT_START, value=COPY_FIRST + copies[(clip, first)])
            extra = _table(k, 'extra_move_properties')
            end = next((r for _, r in k.iter_list('extra_move_properties', moves[i]['extraprops'],
                                                 lambda r: r['id'] == 0 and r['frame'] == 0)
                        if r['id'] == 0 and r['frame'] == 0), None)
            own = [dict(r) for _, r in _extras(k, j)]
            start = len(extra)
            extra += own + [new] + ([dict(end)] if end is not None else [dict(src, id=0, frame=0, value=0)])
            moves[j]['extraprops'] = start
            plan.moves[j] = (clip, at)
            rows[j] = src
            todo.append(j)
            stats['continuations given the clip (%s)' % ('a copy from its start frame' if first > 0 else
                                                         'its start row')] += 1
    for line, n in sorted(stats.items()):
        log('%s: %d' % (line, n))
    log('moves starting the snakes\' clips: %d (%d body animations)' % (len(starters), len(plan.by_key)))
    return plan

