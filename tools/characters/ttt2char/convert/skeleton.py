"""The added fighter's TTT2 skeleton: the donor's skeleton with its joints moved to the Tekken 7 fighter's joints,
and which TTT2 bone each Tekken 7 bone's skin weights go to.

* All the donor's bones are kept (names, order, parents, rest rotations, OPT list, parameters): bones 0..137 have the
  same names, order and parents in every TTT2 skeleton and the game drives helpers by index, so nothing is reordered.
* Joint positions move to the Tekken 7 fighter's: animated joints, assists and fingers are anchored to the Tekken 7
  joint with the same role (ANCHOR); limb helpers keep their place along their limb segment (fraction t and a
  sideways offset); everything else moves with its parent.
* Face joints keep the donor's offsets to the head: the face animations set absolute local positions made for the
  donor's face, so a face joint moved to the new face would be pulled back by every face animation (the lips pushed
  into the face).
* Scale = the Tekken 7 BASE joint's height / 1150 (TTT2 puts HARA_ROT1 at 1150 x scale); body bone scales follow it,
  hand and face scales stay the donor's.
* Since build keeps the donor's rest rotations, the model must be bound in the donor's pose (TTT2 skeletons and
  Tekken 7 meshes: a T-pose). A model bound otherwise (Tekken 8's A-pose) is turned into it first: repose().
TTT2 units are millimetres, Y up, the fighter facing +Z with its left at +X.
"""
import numpy as np

from ..ttt2 import bone

# TTT2 bone (name without 'cha:') -> the Tekken 7 bone whose bind position anchors it
ANCHOR = {'HARA_ROT1': 'BASE', 'MUNE1_jnt': 'Spine1', 'MUNE2_jnt': 'Spine2', 'KOSHI_jnt': 'Hip',
          'KUBI_jnt_assist': 'Neck', 'ATAMA_jnt_assist': 'Head', 'KUBI_Joint': 'Neck', 'ATAMA_Joint': 'Head'}
for s in 'RL':
    ANCHOR.update({'SAKOTSU_%s_jnt' % s: '%s_Shoulder' % s, 'KATA_%s_jnt' % s: '%s_Arm' % s,
                   'UDE_%s_jnt' % s: '%s_ForeArm' % s, 'TE_%s_jnt' % s: '%s_Hand' % s,
                   'MOMO_%s_jnt' % s: '%s_UpLeg' % s, 'HIZA_%s_jnt' % s: '%s_Leg' % s,
                   'ASHI_%s_jnt' % s: '%s_Foot' % s, 'TSUMASAKI_%s_jnt' % s: '%s_Toe' % s,
                   'KO_%s_BASE' % s: '%s_Pinky' % s})
    for ttt2, t7 in (('OYA', 'Thumb'), ('HITO', 'Index'), ('NAKA', 'Middle'), ('KUSU', 'Ring'), ('KO', 'Pinky')):
        for k in (1, 2, 3):                       # TTT2 3 = proximal ... 1 = distal; Tekken 7 1 = proximal
            ANCHOR['%s%d_%s' % (ttt2, 4 - k, s)] = '%s_%s%d' % (s, t7, k)
FACE = ['L_Mayu1_Joint', 'L_Mayu2_Joint', 'L_Mayu3_Joint', 'R_Mayu1_Joint', 'R_Mayu2_Joint', 'R_Mayu3_Joint',
        'L_Eye_Joint', 'L_UwaMabuta_Joint', 'L_SitaMabuta_Joint', 'R_Eye_Joint', 'R_UwaMabuta_Joint',
        'R_SitaMabuta_Joint', 'L_LipU_Joint', 'L_LipE_Joint', 'L_LipD_Joint', 'R_LipU_Joint', 'R_LipE_Joint',
        'R_LipD_Joint', 'M_LipU_Joint', 'M_LipD_Joint', 'Jaw_Joint', 'Bero1_Joint', 'Bero2_Joint', 'L_Hana_Joint',
        'L_Hoho_Joint', 'L_Chobo_Joint', 'L_Kobana_Joint', 'R_Hana_Joint', 'R_Hoho_Joint', 'R_Chobo_Joint',
        'R_Kobana_Joint']
# joints that keep the donor's offset to another (already placed) bone instead of an anchor; the face joints keep
# theirs to the head (face animations are made for the donor's face)
KEEP_OFFSET_TO = {'KUBI_jnt': 'KUBI_jnt_assist', 'ATAMA_jnt': 'ATAMA_jnt_assist'}
KEEP_OFFSET_TO.update({f: 'ATAMA_Joint' for f in FACE})
# limb segments (TTT2 names) for helpers
SEGMENTS = []
for s in 'RL':
    SEGMENTS += [('SAKOTSU_%s_jnt' % s, 'KATA_%s_jnt' % s), ('KATA_%s_jnt' % s, 'UDE_%s_jnt' % s),
                 ('UDE_%s_jnt' % s, 'TE_%s_jnt' % s), ('MOMO_%s_jnt' % s, 'HIZA_%s_jnt' % s),
                 ('HIZA_%s_jnt' % s, 'ASHI_%s_jnt' % s), ('ASHI_%s_jnt' % s, 'TSUMASAKI_%s_jnt' % s)]


# the Tekken 7 joints this file names, by their lower-case names: some skeletons spell them otherwise (Gigas's
# 'Base', 'HEAD'); canonical() gives the spelling used here
T7_JOINTS = set(ANCHOR.values()) | set(FACE) | {
    'Head', 'Head__offset', 'ATH_ornaments', 'Neck', 'Neck__offset', 'Neck_back__offset', 'Bero1_Joint_pos',
    'Bero3_Joint', 'Spine2', 'Spine2__offset', 'Spine2up__offset', 'Spine1', 'Spine1__offset', 'Hip', 'Hip__offset',
    'Hip_front__offset', 'BASE'}
_CANONICAL = {n.lower(): n for n in T7_JOINTS}


def canonical(name):
    """A Tekken 7 joint's name as this file spells it (unknown names as they are)."""
    return _CANONICAL.get(name.lower(), name)


def _strip(n):
    return n[4:] if n.startswith('cha:') else n


def t7_weight_target(t7name, part):
    """TTT2 bone name for a weighted T7 bone (None = resolve through the T7 parent)."""
    n = t7name.split('@')[0]
    if n in FACE:
        return n
    if n in ('Head', 'Head__offset'):
        return 'ATAMA_Joint' if part == 'fac' else 'ATAMA_jnt_assist'
    if n == 'ATH_ornaments':
        return 'ATAMA_jnt_assist'
    if n in ('Neck', 'Neck__offset', 'Neck_back__offset'):
        return 'KUBI_jnt_assist'
    if n.endswith('_UpEyelid1') or n.endswith('_UpEyelid2'):
        return n[0] + '_UwaMabuta_Joint'
    if n.endswith('_LowEyelid1') or n.endswith('_LowEyelid2'):
        return n[0] + '_SitaMabuta_Joint'
    if n.endswith('_Eyecorner'):
        return 'ATAMA_Joint'
    if n == 'Bero1_Joint_pos':
        return 'Bero1_Joint'
    if n == 'Bero3_Joint':
        return 'Bero2_Joint'
    if n in ('Spine2', 'Spine2__offset', 'Spine2up__offset'):
        return 'MUNE2_jnt'
    if n in ('Spine1', 'Spine1__offset'):
        return 'MUNE1_jnt'
    if n in ('Hip', 'Hip__offset', 'Hip_front__offset', 'BASE'):
        return 'KOSHI_jnt'
    if 'bust' in n:
        return 'OPT0_busts'
    if len(n) > 2 and n[1] == '_' and n[0] in 'LR' or n.startswith('HLP_'):
        hlp = n.startswith('HLP_')
        s = n[4] if hlp else n[0]
        base = n[6:] if hlp else n[2:]
        base = base.replace('__offset', '')
        lo = s.lower()
        table = {
            'Butt': 'HIP_%s' % s, 'Inguinal': 'MOMO_F0_%s' % s, 'UpLeg': 'MOMO_0_%s' % s,
            'UpLeg_Top': 'MOMO_0_%s' % s, 'UpLeg_Mid': 'MOMO_50_%s' % s, 'Knee': 'HIZA_%s' % s,
            'Leg': 'SUNE_%s' % s, 'Calf_Slide': 'slide_fukura_%s' % lo, 'Foot': 'ASHI_%s_jnt' % s,
            'Ankle': 'ASHI_%s_jnt' % s, 'Toe': 'TSUMASAKI_%s_jnt' % s,
            'Shoulder': 'SAKOTSU_%s_jnt' % s, 'Shldr_B': 'KATA_B0_%s' % s, 'ShldrBlade': 'KENKO_%s_jnt' % s,
            'CollarBone': 'SAKOTSU_0_%s_jnt' % s, 'CollarBone_up': 'SAKOTSU_0_%s_jnt' % s,
            'Shldr_F': 'KATA_F0_%s' % s, 'Pectoral': 'MUNE_%s_jnt' % s,
            'Arm': 'KATA_0_%s_jnt' % s, 'Arm_Top': 'KATA_0_%s_jnt' % s, 'Arm_Mid': 'KATA_50_%s' % s,
            'Arm_Btm': 'KATA_100_%s' % s, 'Bicep_Slide': 'slide_kata_%s' % lo, 'Tricep_Slide': 'slide_hiji_%s' % lo,
            'ForeArm': 'UDE_%s_jnt' % s, 'ForeArm_Slide': 'slide_ude_%s' % lo, 'ForeArm_Mid': 'UDE_50_%s' % s,
            'ForeArm_Btm': 'UDE_100_%s' % s, 'Hand': 'TE_%s_jnt' % s, 'Hand2': 'TE_%s_jnt' % s,
            'FingerBase': 'TE_%s_jnt' % s, 'Middle': 'TE_%s_jnt' % s, 'Ring': 'TE_%s_jnt' % s,
            'Pinky': 'KO_%s_BASE' % s}
        if base in table:
            return table[base]
        for ttt2, t7 in (('OYA', 'Thumb'), ('HITO', 'Index'), ('NAKA', 'Middle'), ('KUSU', 'Ring'), ('KO', 'Pinky')):
            for k in (1, 2, 3):
                if base == '%s%d' % (t7, k):
                    return '%s%d_%s' % (ttt2, 4 - k, s)
    return None


def weight_map(t7bones, ttt2names, part_of_bone=None):
    """Array t7 bone index -> TTT2 bone index (walking up T7 parents for unmapped bones such as cloth/hair OPT and
    'transformNN' bones). part_of_bone: optional function(t7 index) -> part tag ('fac', 'har', ...)."""
    idx = {_strip(n): i for i, n in enumerate(ttt2names)}
    out = np.full(len(t7bones['names']), -1, np.int64)
    via = {}
    for i, n in enumerate(t7bones['names']):
        j, k = i, None
        while j >= 0:
            k = t7_weight_target(t7bones['names'][j], part_of_bone(i) if part_of_bone else None)
            if k is not None and k in idx:      # (a bone the donor lacks, e.g. a male donor's busts: its parent's)
                break
            k = None
            j = t7bones['parents'][j]
        out[i] = idx[k] if k is not None else idx['KOSHI_jnt']
        via[i] = (t7bones['names'][j] if j >= 0 else None, k)
    return out, via


def build(t7bones, donor):
    """t7bones: {'names', 'parents', 'world' (n, 4, 4) bind matrices in TTT2 space}; donor: bone.read() of the
    donor's skeleton. Returns the new skeleton (a bone dict for bone.write)."""
    names = [_strip(n) for n in donor['names']]
    idx = {n: i for i, n in enumerate(names)}
    W = bone.world_matrices(donor)
    P = W[:, :3, 3].copy()
    t7pos = {n: t7bones['world'][i][:3, 3] for i, n in enumerate(t7bones['names'])}
    if 'BASE' not in t7pos:
        raise ValueError('the Tekken 7 skeleton has no BASE joint')
    newP = {}
    n = len(names)
    # 1. anchors
    for i, nm in enumerate(names):
        a = ANCHOR.get(nm)
        if a is not None and a in t7pos:
            newP[i] = t7pos[a].copy()
    # 2. the donor's offsets to an anchored bone
    for nm, ref in KEEP_OFFSET_TO.items():
        i, r = idx[nm], idx[ref]
        newP[i] = newP[r] + (P[i] - P[r])
    # 3. limb helpers along their segment, 4. the rest with their parent (in index order: parents first)
    seg = [(idx[a], idx[b]) for a, b in SEGMENTS]
    for i in range(n):
        if i in newP:
            continue
        best = None
        if i > 21:
            for a, b in seg:
                if a not in newP or b not in newP:
                    continue
                ab = P[b] - P[a]
                t = float((P[i] - P[a]) @ ab / (ab @ ab))
                if -0.15 <= t <= 1.15:
                    lat = P[i] - (P[a] + t * ab)
                    d = float(np.linalg.norm(lat))
                    if d < 80 and (best is None or d < best[0]):
                        best = (d, a, b, t, lat)
        if best is not None:
            d, a, b, t, lat = best
            newP[i] = newP[a] + t * (newP[b] - newP[a]) + lat
        else:
            p = donor['parent'][i]
            newP[i] = P[i] + (newP[p] - P[p]) if p >= 0 else P[i]
    # local translations under the donor's world rotations
    out = dict(donor)
    out['t'] = donor['t'].copy()
    for i in range(n):
        p = donor['parent'][i]
        out['t'][i] = newP[i] if p < 0 else W[p][:3, :3].T @ (newP[i] - newP[p])
    scale = float(t7pos['BASE'][1] / 1150.0)
    out['scale'] = scale
    s = donor['s'].copy()
    body = np.isclose(s, donor['scale'], atol=2e-3)
    s[body] = s[body] * (scale / donor['scale'])
    out['s'] = s
    out['names_raw'] = None
    return out


# ------------------------------------------------------------------------------------------------ re-pose
# Limb segments (Tekken 7 joint -> its child) that turn to point the way the donor's (the TTT2 bones ANCHOR puts
# there) do, from the body out: a turned upper arm carries the forearm, hand and fingers along before they turn.
# The hand turns as a whole: towards the middle finger's base and with its knuckle line (index -> little finger
# base) as the donor's. The last finger joints keep their turn to the one before (no tips to aim with).
REPOSE = [('Spine1', 'Spine2'), ('Spine2', 'Neck'), ('Neck', 'Head')]
for s in 'RL':
    REPOSE += [('%s_Shoulder' % s, '%s_Arm' % s), ('%s_Arm' % s, '%s_ForeArm' % s), ('%s_ForeArm' % s, '%s_Hand' % s),
               ('%s_Hand' % s, '%s_Middle1' % s, '%s_Index1' % s, '%s_Pinky1' % s),
               ('%s_UpLeg' % s, '%s_Leg' % s), ('%s_Leg' % s, '%s_Foot' % s)]
    for f in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
        REPOSE += [('%s_%s1' % (s, f), '%s_%s2' % (s, f)), ('%s_%s2' % (s, f), '%s_%s3' % (s, f))]
# joints that keep their world orientation whatever their parents did: the feet (soles flat on the floor, as the
# donor's: aimed at the toes they would tilt by the difference of the two feet's arches) and the head (looking ahead)
LEVEL = ('Head', 'L_Foot', 'R_Foot')
TTT2_OF = {}                                      # Tekken 7 joint -> the TTT2 bone at it (ANCHOR, first one)
for _b, _t in ANCHOR.items():
    TTT2_OF.setdefault(_t, _b)


def _turn(a, b):
    """The smallest rotation (3x3) turning direction a to direction b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(a @ b)
    s = float(np.linalg.norm(v))
    if s < 1e-12:
        if c > 0:
            return np.eye(3)
        axis = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
        return _rotation(axis / np.linalg.norm(axis), np.pi)
    return _rotation(v / s, np.arctan2(s, c))


def _frame_turn(a1, a2, b1, b2):
    """The rotation turning a1 to b1 and the plane of (a1, a2) to that of (b1, b2)."""
    def frame(x, y):
        x = x / np.linalg.norm(x)
        y = y - x * (x @ y)
        y = y / np.linalg.norm(y)
        return np.stack([x, y, np.cross(x, y)], 1)
    return frame(b1, b2) @ frame(a1, a2).T


def _rotation(axis, angle):
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * (k @ k)


def _share(r, f):
    """Rotation r turned by the share f of its angle (same axis)."""
    angle = np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1))
    if angle < 1e-9:
        return np.eye(3)
    axis = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
    n = np.linalg.norm(axis)
    if n < 1e-9:                                  # 180 degrees: the axis from the symmetric part
        w, v = np.linalg.eigh((r + np.eye(3)) / 2)
        axis = v[:, np.argmax(w)]
    else:
        axis = axis / n
    return _rotation(axis, f * angle)


def _about(r, pivot):
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = pivot - r @ pivot
    return m


def repose(model, donor, log=print):
    """model: model.load_tekken7_model's dict (bind pose and all), bound in another pose than the donor's (Tekken
    8's A-pose); donor: bone.read() of the donor's skeleton. -> the model turned into the donor's bind pose: each
    REPOSE segment points the way the donor's does (LEVEL joints keep their orientation), the vertices follow their
    joints as skinning moves them (each joint carried by its parent, or by model['bones']['follow'][i] = (joint,
    share): it turns with that joint, by that share of its turn), normals and tangents turned with them, bind
    matrices too. Joints the model lacks are left as they are; a model without any is returned unchanged."""
    bones = model['bones']
    nm, parents = bones['names'], bones['parents']
    W = np.asarray(bones['world'], np.float64)
    P = W[:, :3, 3]
    n = len(nm)
    idx = {x: i for i, x in enumerate(nm)}
    dnames = [_strip(x) for x in donor['names']]
    didx = {x: i for i, x in enumerate(dnames)}
    DP = bone.world_matrices(donor)[:, :3, 3]
    specs = {}
    for seg in REPOSE:
        bones_here = [seg[0], seg[1]] + list(seg[2:])
        if all(b in idx and TTT2_OF.get(b) in didx for b in bones_here):
            specs[idx[seg[0]]] = [(idx[b], didx[TTT2_OF[b]]) for b in bones_here]
    for j in LEVEL:
        if j in idx:
            specs[idx[j]] = 'level'
    if not any(v != 'level' for v in specs.values()):
        return model
    follow = bones.get('follow') or [None] * n
    # each joint's change D (world, 4x4): first the REPOSE / LEVEL joints from the body out, each carried by its
    # parent, then the joints that follow another
    D = np.zeros((n, 4, 4))
    own = {}                                      # joint -> (its own turn, its pivot)
    turned = {}
    for i in range(n):
        p = parents[i]
        dp = D[p] if p >= 0 else np.eye(4)
        spec = specs.get(i)
        if spec is None:
            D[i] = dp
            continue
        pivot = dp[:3, :3] @ P[i] + dp[:3, 3]
        if spec == 'level':
            r = dp[:3, :3].T
        else:
            (a, da), (b, db) = spec[0], spec[1]
            cur, goal = dp[:3, :3] @ (P[b] - P[a]), DP[db] - DP[da]
            if len(spec) > 2:
                (c, dc), (e, de) = spec[2], spec[3]
                r = _frame_turn(cur, dp[:3, :3] @ (P[e] - P[c]), goal, DP[de] - DP[dc])
            else:
                r = _turn(cur, goal)
            turned[nm[i]] = np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1)))
        own[i] = (r, pivot)
        D[i] = _about(r, pivot) @ dp
    # (a joint carrying REPOSE joints keeps the change it got from its parent: they were turned from it)
    carries = np.zeros(n, bool)
    for i in specs:
        j = parents[i]
        while j >= 0 and not carries[j]:
            carries[j] = True
            j = parents[j]
    for i in range(n):
        f = follow[i] if i < len(follow) else None
        if i in specs or carries[i]:
            continue
        if f is not None:
            j, share = f
            pj = parents[j]
            dpj = D[pj] if pj >= 0 else np.eye(4)
            r, pivot = own.get(j, (np.eye(3), dpj[:3, :3] @ P[j] + dpj[:3, 3]))
            D[i] = _about(_share(r, share), pivot) @ dpj
        elif parents[i] >= 0:
            D[i] = D[parents[i]]
    # skinning: each vertex by its joints' changes, blended by its weights (as the game skins it)
    out = dict(model)
    out['bones'] = dict(bones, world=D @ W)
    prims = []
    done = {}
    for prim in model['prims']:
        key = id(prim['pos'])
        if key not in done:
            w = prim['weights'] / np.maximum(prim['weights'].sum(1, keepdims=True), 1e-12)
            M = np.einsum('vk,vkij->vij', w, D[prim['joints']])
            pos = np.einsum('vij,vj->vi', M[:, :3, :3], prim['pos']) + M[:, :3, 3]
            nrm = np.einsum('vij,vj->vi', M[:, :3, :3], prim['nrm'])
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
            tan = prim['tan'].copy()
            tan[:, :3] = np.einsum('vij,vj->vi', M[:, :3, :3], prim['tan'][:, :3])
            tan[:, :3] /= np.maximum(np.linalg.norm(tan[:, :3], axis=1, keepdims=True), 1e-12)
            done[key] = dict(pos=pos, nrm=nrm, tan=tan)
        prims.append(dict(prim, **done[key]))
    out['prims'] = prims
    groups = {}
    for name, angle in turned.items():
        g = name[2:] if name[1] == '_' else name
        g = g.rstrip('123') if any(g.startswith(f) for f in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')) else g
        groups[g] = max(groups.get(g, 0.0), angle)
    log('  re-posed to the donor\'s bind pose (largest turn, degrees): %s' % ', '.join(
        '%s %.0f' % (g, a) for g, a in groups.items()))
    return out
