"""Tekken 8 body animations (category-0 PANM clips of the fighter's banks: anmbin.py, panm.py) -> TTT2 body
animations for the converter's motion pack: the fighter's own skeleton read from the player's Tekken 8, each clip's
rotations retargeted onto a TTT2 skeleton (convert/retarget.py), its root motion scaled from the fighter's own
proportions to that skeleton's, written as type 0x64 (compressed, big-endian: what motion.extend_mota appends) or
0xC8.

The fighter's skeleton, SKB_CH_<code>_base_msl (Character/Item/shared/skeleton/<code>/): its main export's RawData
is a FlatBuffers buffer (field k = vtable slot 4 + 2k), identifier 'PSKS' at +4:
    root f3 -> {f1 [bone], f3 [rig driver node]}
    bone {f2 string name, f4 u16 parent (0xFFFF: none), f5 translation {f0 x, f1 y, f2 z} (cm), f6 rotation
          {x, y, z, w} (w defaults to 1), f7 scale (defaults to 1)}: local to the parent, Y up, x the fighter's left,
          z forward (TTT2's axes), the clips' joint frames; the same joints, names and order as the _msl meshes

Conventions, checked on the shared bank's older clips, which were made from TTT2 / Tekken 7 animations (778 of the
859 Reina's moves use pair with the TTT2 animation of the same name; their HARA_ROT1 / MUNE_jnt / KOSI_NULL2 nodes
hold TTT2's channels 3, 4 and 6):
    Top x, z = channel 0 / 10, Trans = channel 1 / 10 (the same frame: not turned; within 4 mm, their quantisation),
    MUKI's local rotation = channel 2's yaw (0.09 degrees p90); the joints' world rotations (forward kinematics from
    Top, MUKI left out) = TTT2's before the turn: Rot = KOSHI_jnt (median 0.1 degrees from a constant offset),
    UpperLeg = MOMO (0.1), Spine2 = MUNE2 within 5.7 (median; 16.7 p99: the conversion had TTT2's spine
    post-process in it, which a TTT2 animation's MUNE1 channel does not), the arms and the head alike (they hang
    from the chest). Top's y is 0 (2.7e-3 at most), Rot carries no translation, Hip and C_Leg are constant, the
    HARA_ROT1 node of the newer clips is the identity (a logic channel; the game looks it up by name).
So the drivers (DRIVERS): C_Leg (the legs' parent) -> KOSHI, Spine2 -> MUNE2 (through MUNE1's channel), Neck, Head,
Shoulder, UpperArm, LowerArm, Hand, UpperLeg, LowerLeg, Foot -> their TTT2 bones; HARA_ROT1 keeps the identity
(retarget.py); fingers and toes are not body channels (fingers: category-1 clips; TTT2's toes keep their bind).
Root: channel 0 = k Top (x, z), channel 1 = k Trans (Rot's position above the displaced origin), channel 2 = MUKI's
yaw, k = the TTT2 skeleton's thigh + shin (before its scale) / the fighter's own (its bind's). The game plays every
clip on the fighter's own bone lengths with the root as stored: a clip's translations are its authoring rig's (220 of
Reina's 258 own clips her proportion pose's, PRB_CH_<code>_msl: legs 88.44 cm, 25 a rig of 90.2, 11 of 88.0; her
bind 86.24), but only on her bind do the feet meet the floor: the lowest sole point (ATH_*_Foot_Btm / _Toe_Btm) of a
clip, median over the clips, -4.1, -4.7, +9.2 mm on her bind for those three rigs (+10.2 for the shared bank's 163
clips of 90.2), -34, -36, -13 (-29) on their own rigs or the proportion pose; TTT2's own animations on Jun: -8.6.
The older shared clips (rotations only) hold their root in TTT2's units: they are measured against TTT2's leg
(LEGACY_LEG), which gives back the TTT2 originals' channels 0 and 1 on a base skeleton.

Weapons (convert/weapons.py, convert/summons8.py; Miary Zo's staffs, tail and the hit points): a fighter whose
skeleton has weapon bones posed by animation pairs (OPT 800 + k) gets, in each clip that moves one of their joints
(or that a move's root points need), extra (translation, rotation) pairs after the 23 body channels, pair k the local
transform of weapon bone k in its TTT2 parent's frame as the runtime writes it into the bone's record (roster.cpp,
weapons), every pair below the highest one present (pairs are positional: pair k = channels 23 + 2k, 24 + 2k; a pair
whose weapon the clip does not move holds the bone's bind). A weapon bone's frame is its Tekken 8 joint's (the PSKS
frame: weapons.append_tekken8), so with S, P the joints' world rotations / positions of the clip (forward kinematics
as for the drivers) and O_b the calibration offset of the TTT2 parent b (its world G_b = S_driver O_b):
    a weapon under a body bone b:           R = O_b^T S_driver^T S_joint,   t = O_b^T S_driver^T (P_joint - P_anchor)
                                            (P_anchor: the driver's, or the joint at b's origin: ANCHORS)
    a link under the weapon before it:      R = S_up^T S_joint,             t = S_up^T (P_joint - P_up)
    a hit-only 'lead' under b:              R = I, t as a weapon's for the most forward (+z) of its joints, or the
                                            point tip_cm past the last one along that joint's x (its chain's axis)
    a 'root' point under HARA_ROT1:         R = I, t = H^T (s k o - s ch1): o the move's hit box offset (mm; the
                                            fighter's frame before the turn, x left, y up, z forward), k the clip's
                                            root scale, s the skeleton's size scale, ch1 / H HARA_ROT1's channel 1
                                            and rotation (channel 3)
    a 'snakes' head under b:                R = I, t = the most forward (+z) of the heads of the summoned model's
                                            clip the move starts, given in b's frame (convert/snakes8.py: heads),
                                            from its start frame on (before it: the clip's first frame)
The re-pose of the model (convert/skeleton.py) cancels out: the mesh skinned to a weapon bone follows its Tekken 8
joint exactly wherever the TTT2 parent is driven. The joints' own scale channels are left out (the record takes a
rotation), and the clip's stored translations of the weapons' joints are used.

Written for this project from the files themselves (no third-party code).
"""
import collections
import time

import numpy as np

from .. import InputError
from ..convert import retarget
from ..ttt2 import animation, bone, motion
from . import anmbin, panm, uprops

SKELETON_PATH = 'Polaris/Content/Character/Item/shared/skeleton/%s/SKB_CH_%s_base_msl'
CM = 10.0                                   # Tekken 8's centimetres -> TTT2's millimetres
# the leg (thigh + shin, mm) the older shared clips' root is measured against: their root motion is TTT2's own
# channels / 10, so their rig is TTT2's: 860 in every base skeleton before its scale (retarget.leg_length)
LEGACY_LEG = 860.0
NO_PARENT = 0xFFFF

LANDMARKS = {'hara': 'Spine1', 'chest': 'Spine2', 'neck': 'Neck', 'head': 'Head'}
DRIVERS = {'KOSHI_jnt': 'C_Leg', 'MUNE2_jnt': 'Spine2', 'KUBI_jnt': 'Neck', 'ATAMA_jnt': 'Head'}
for _s in 'RL':
    LANDMARKS.update({'clav_' + _s: '%s_Shoulder' % _s, 'shoulder_' + _s: '%s_UpperArm' % _s,
                      'elbow_' + _s: '%s_LowerArm' % _s, 'wrist_' + _s: '%s_Hand' % _s, 'hip_' + _s: '%s_UpperLeg' % _s,
                      'knee_' + _s: '%s_LowerLeg' % _s, 'ankle_' + _s: '%s_Foot' % _s, 'toe_' + _s: '%s_Toe' % _s})
    DRIVERS.update({'SAKOTSU_%s_jnt' % _s: '%s_Shoulder' % _s, 'KATA_%s_jnt' % _s: '%s_UpperArm' % _s,
                    'UDE_%s_jnt' % _s: '%s_LowerArm' % _s, 'TE_%s_jnt' % _s: '%s_Hand' % _s,
                    'MOMO_%s_jnt' % _s: '%s_UpperLeg' % _s, 'HIZA_%s_jnt' % _s: '%s_LowerLeg' % _s,
                    'ASHI_%s_jnt' % _s: '%s_Foot' % _s})
TOP, TRANS, ROT, FACING = 'Top', 'Trans', 'Rot', 'MUKI'
ROOT = (TOP, TRANS, ROT)                    # the joints whose translations a clip moves
LEGS = [('%s_LowerLeg' % s, '%s_Foot' % s) for s in 'LR']       # the knee's and the ankle's offsets


# ------------------------------------------------------------------------------------------------ skeleton
def _quaternions(q):
    q = np.asarray(q, np.float64)
    return q / np.maximum(np.linalg.norm(q, axis=-1, keepdims=True), 1e-12)   # (f32 data: norms off by ~1e-7)


def read_skeleton(raw):
    """A PSKS buffer -> dict(names, parents, t (n, 3) cm, q (n, 4) x y z w, s (n, 3))."""
    raw = bytes(raw)
    if len(raw) < 8 or raw[4:8] != b'PSKS':
        raise InputError('the fighter\'s skeleton is not one Tekken 8 has (no PSKS data)')
    f = panm.FlatBuffer(raw)
    top = f.table(f.root(), 3)
    bones = f.tables(top, 1) if top is not None else []
    if not bones:
        raise InputError('the fighter\'s skeleton has no joints')
    names, parents, t, q, s = [], [], [], [], []
    for b in bones:
        names.append(f.string(b, 2))
        p = f.scalar(b, 4, '<H', NO_PARENT)
        parents.append(-1 if p == NO_PARENT else p)
        t.append(f.floats(b, 5, (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0))
        q.append(f.floats(b, 6, (0.0, 0.0, 0.0, 1.0)) or (0.0, 0.0, 0.0, 1.0))
        s.append(f.floats(b, 7, (1.0, 1.0, 1.0)) or (1.0, 1.0, 1.0))
    if any(not -1 <= p < len(names) for p in parents):
        raise InputError('the fighter\'s skeleton has a joint whose parent does not exist')
    return dict(names=names, parents=parents, t=np.array(t), q=_quaternions(q), s=np.array(s))


def skeleton(psks):
    """retarget.Skeleton (millimetres) of read_skeleton()'s dict."""
    return retarget.Skeleton(psks['names'], psks['parents'], np.asarray(psks['t']) * CM,
                             animation.quaternion_to_matrix(psks['q']), psks['s'])


def _raw_data(store, path):
    try:
        pkg = store.package(path)
        props, _ = uprops.read(pkg, pkg.main_export(), store.schema)
    except (OSError, KeyError, ValueError) as e:
        raise InputError('%s cannot be read from Tekken 8 (%s)' % (path, e))
    raw = props.get('RawData')
    if raw is None:
        raise InputError('%s holds no skeleton data' % path)
    return bytes(raw)


def load_skeleton(store, code):
    """The fighter's skeleton (skeleton()) from the player's Tekken 8 (store: tekken8.store.Store)."""
    return skeleton(read_skeleton(_raw_data(store, SKELETON_PATH % (code, code))))


# ------------------------------------------------------------------------------------------------ clips
def bind_leg(sk):
    """The skeleton's thigh + shin (mm; the mean of both sides): what its clips' root motion is measured against."""
    return float(np.mean([np.linalg.norm(sk.t[sk.index[k]]) + np.linalg.norm(sk.t[sk.index[a]]) for k, a in LEGS]))


class Converter:
    """Clips of a fighter -> TTT2 body animations. sk: the fighter's skeleton (load_skeleton / skeleton()); target:
    bone.read() of the TTT2 skeleton they will play on (the added fighter's, skeleton.build); kind: 0x64
    (animation.COMPRESSED) or 0xC8 (animation.RAW)."""

    def __init__(self, sk, target, kind=animation.COMPRESSED, weapons=()):
        self.sk, self.kind = sk, kind
        dst = retarget.ttt2_skeleton(target)
        self.cal = retarget.Calibration(sk, LANDMARKS, DRIVERS, dst)
        self.leg, self.own_leg = retarget.leg_length(target), bind_leg(sk)
        self.scale = dst.scale
        # weapons posed by pairs (pair_specs; none: the 23 body channels only)
        self.pairs = pair_specs(sk, target, weapons, self.cal) if weapons else []
        # the joints the channels need, and their ancestors: a small skeleton of its own
        body = sk.chain([sk.index[j] for j in set(DRIVERS.values()) | {TOP, TRANS, ROT}])
        want = body + [sk.index[j] for j in pair_joints(self.pairs)]
        chain = sk.chain(want)
        at = {j: k for k, j in enumerate(chain)}
        self.sub = retarget.Skeleton([sk.names[j] for j in chain],
                                     [at[sk.parents[j]] if sk.parents[j] >= 0 else -1 for j in chain],
                                     sk.t[chain], sk.R[chain], sk.s[chain])
        self.moved = {sk.names[j] for j in chain if j not in set(body)}     # the weapons' joints (pairs)

    def fk(self, anim):
        """(joints {name: panm.Joint}, world rotations (F, n, 3, 3), positions (F, n, 3) mm) of the clip on the small
        skeleton: the root's and the weapons' joints' stored translations, the others' the bind's."""
        J = anim.joints()
        sub, F = self.sub, anim.frames
        LR = np.repeat(sub.R[None], F, 0)
        Lt = np.repeat(sub.t[None], F, 0)
        for name, j in J.items():
            i = sub.index.get(name)
            if i is None:
                continue
            if j.stored_rotation:
                LR[:, i] = animation.quaternion_to_matrix(_quaternions(j.rotation))
            if j.stored_translation and (name in ROOT or name in self.moved):
                Lt[:, i] = j.translation * CM
        WR, Wp = sub.fk(LR, Lt)
        return J, WR, Wp

    def pose(self, anim):
        """The clip's source pose: (world rotations {joint: (F, 3, 3)}, root (F, 3) mm, displacement (F, 3) mm,
        yaw (F,), the leg (mm) its root is measured against, joints {name: panm.Joint}). The joints keep the
        fighter's own lengths (the clip's other translations are its authoring rig's); only the root moves."""
        J, WR, Wp = self.fk(anim)
        sub, F = self.sub, anim.frames
        world = {n: WR[:, sub.index[n]] for n in set(DRIVERS.values())}
        D = Wp[:, sub.index[TOP]]
        root = Wp[:, sub.index[ROT]] - D
        if FACING in J and J[FACING].stored_rotation:
            m = animation.quaternion_to_matrix(_quaternions(J[FACING].rotation))
            yaw = np.arctan2(m[:, 0, 2], m[:, 2, 2])
        else:
            yaw = np.zeros(F)
        return world, root, D, yaw, LEGACY_LEG if anim.legacy else self.own_leg, J

    def channels(self, anim, roots=None, snakes=None):
        """(TTT2 body channel values (F, 23, 3), info {'frames', 'leg', 'root_scale', 'pairs'}) of a panm.Animation;
        with weapon pairs (F, 23 + 2 n, 3) when the clip moves a weapon's joint or `roots` (the move's root point
        offsets, mm: summons8.roots) or `snakes` (the heads its move's summoned clip moves and the frame it starts at:
        convert/snakes8.py) are given (pair_values)."""
        world, root, D, yaw, leg, J = self.pose(anim)
        k = self.leg / leg
        values = retarget.body_channels(self.cal, world, root, D, yaw, k, self.kind)
        count = 0
        if self.pairs:
            moving = any(n in self.moved and (j.stored_rotation or j.stored_translation) for n, j in J.items())
            count = max([p + 1 for p, s in enumerate(self.pairs) if s is not None and
                         (s['kind'] == 'root' and roots is not None or s['kind'] in ('joint', 'lead') and moving or
                          s['kind'] == 'snakes' and snakes is not None)]
                        or [0])
        if count:
            _, WR, Wp = self.fk(anim)
            values = np.concatenate([values, pair_values(self, WR, Wp, values, k, roots, count, snakes)], 1)
        return values, dict(frames=anim.frames, leg=leg, root_scale=k, pairs=count)

    def animation(self, blob, endian='>', roots=None, snakes=None):
        """A TTT2 body animation (bytes) of a body clip's blob (roots, snakes: channels())."""
        values, info = self.channels(panm.Animation(blob), roots, snakes)
        self.last_pairs = info['pairs']
        return retarget.encode(values, self.kind, endian)


# ------------------------------------------------------------------------------------------------ weapon pairs
WEAPON_FIRST = 800                          # weapons.OPT_FIRST: bone OPT 800 + k takes pair k
NAME_LENGTH = 31                            # weapons.NAME_LENGTH (with 'cha:')
ROOT_PARENT = 'HARA_ROT1'
# the Tekken 8 joint at a TTT2 bone's origin where that is not its driver's (skeleton.ANCHOR through tekken8/names.py):
# KOSHI sits at HARA_ROT1 (Rot, 112.7 cm up in her bind), its driver C_Leg 16 cm below (a weapon's translation is
# measured from it: her tail hung 16 cm too high from C_Leg)
ANCHORS = {'KOSHI_jnt': ROT}


def _short(name):
    return name[4:] if name.startswith('cha:') else name


def pair_specs(sk, target, weapons, cal):
    """[spec or None by pair k] of the weapons posed by pairs (definition entries: 'bone', 'pair', and 'joint' (the
    Tekken 8 joint, default the bone), 'lead' [joints] + 'tip_cm', 'root' (0 / 1: the move's first / second root
    offset), or 'still' (a hit-only weapon at its bind: a pair only for its place in the weapons' order, which the
    runtime's point slots go by: Miary Zo's snakes' point before her tail's)), each {'kind': 'joint' / 'lead' / 'root' /
    'still', 'bind': (t, R) of the TTT2 bone's bind local, ...}; their bones are found in the TTT2 skeleton `target`
    (bone.read) as weapons.append_tekken8 named them."""
    names = [_short(n) for n in target['names']]
    of_name = {}
    for w in weapons:
        if w.get('pair') is not None:
            of_name[('cha:OPT%d_%s' % (WEAPON_FIRST + w['pair'], w['bone']))[:NAME_LENGTH][4:]] = w
    out = {}
    for name, w in of_name.items():
        if name not in names:
            raise ValueError('the skeleton has no bone %s for weapon %s' % (name, w['bone']))
        b = names.index(name)
        up = names[target['parent'][b]]
        spec = dict(bind=(np.asarray(target['t'][b], np.float64),
                          bone.matrix_from_euler_xyz(np.asarray(target['r'][b], np.float64))))
        if w.get('still'):
            spec.update(kind='still')
        elif w.get('root') is not None:
            if up != ROOT_PARENT:
                raise ValueError('a root point\'s weapon hangs under %s, not %s' % (up, ROOT_PARENT))
            spec.update(kind='root', root=int(w['root']))
        elif up in of_name:                                      # a link under the weapon before it
            spec.update(kind='joint', joint=w.get('joint', w['bone']), up=of_name[up].get('joint', of_name[up]['bone']))
        else:
            if up not in cal.drivers:
                raise ValueError('weapon %s hangs under %s, which no Tekken 8 joint drives' % (w['bone'], up))
            spec.update(driver=cal.drivers[up], offset=cal.offsets[up], anchor=ANCHORS.get(up, cal.drivers[up]))
            if w.get('lead'):
                spec.update(kind='lead', joints=list(w['lead']), tip=float(w.get('tip_cm', 0.0)) * CM)
            elif w.get('snakes'):                                # (the snakes' heads: convert/snakes8.py)
                spec.update(kind='snakes')
            else:
                spec.update(kind='joint', joint=w.get('joint', w['bone']))
        for j in pair_joints([spec]):
            if j not in sk.index:
                raise ValueError('the fighter\'s skeleton has no joint %s (weapon %s)' % (j, w['bone']))
        out[w['pair']] = spec
    return [out.get(k) for k in range(max(out) + 1)] if out else []


def pair_joints(specs):
    """The Tekken 8 joints the specs' pairs are made of."""
    out = []
    for s in specs:
        if s is None or s['kind'] in ('root', 'still'):
            continue
        out += s['joints'] if s['kind'] == 'lead' else [] if s['kind'] == 'snakes' else [s['joint']]
        out += [x for x in (s.get('driver'), s.get('up'), s.get('anchor')) if x]
    return sorted(set(out))


def pair_values(conv, WR, Wp, values, k, roots, count, snakes=None):
    """The extra channels (F, 2 count, 3) of pairs 0 .. count - 1 (conv.pairs; see the module's notes) of a clip:
    WR, Wp its forward kinematics (Converter.fk), values its body channels, k its root scale, roots its root point
    offsets (or None: those pairs hold their bind), snakes (heads (G, m, 3) mm in the parent's frame, the frame
    index the summoned clip starts at) or None."""
    F = len(values)
    idx = conv.sub.index
    T = np.zeros((F, count, 3))
    R = np.repeat(np.eye(3)[None, None], F, 0).repeat(count, 1)

    def frame(s):                                       # (F, 3, 3) the TTT2 parent's frame from its driver: (S O)^T
        return np.swapaxes(WR[:, idx[s['driver']]] @ s['offset'], -1, -2)
    for p in range(count):
        s = conv.pairs[p]
        if s is None:
            continue
        if s['kind'] == 'joint':
            w = idx[s['joint']]
            if 'up' in s:
                q = idx[s['up']]
                A, origin = np.swapaxes(WR[:, q], -1, -2), Wp[:, q]
            else:
                A, origin = frame(s), Wp[:, idx[s['anchor']]]
            R[:, p] = A @ WR[:, w]
            T[:, p] = np.einsum('fij,fj->fi', A, Wp[:, w] - origin)
        elif s['kind'] == 'lead':
            last = idx[s['joints'][-1]]
            cands = [Wp[:, idx[j]] for j in s['joints']] + [Wp[:, last] + s['tip'] * WR[:, last][:, :, 0]]
            P = np.stack(cands, 1)                                              # (F, m, 3)
            lead = P[np.arange(F), np.argmax(P[:, :, 2], 1)]
            T[:, p] = np.einsum('fij,fj->fi', frame(s), lead - Wp[:, idx[s['anchor']]])
        elif s['kind'] == 'snakes' and snakes is not None:                      # the snakes' most forward head
            H, start = snakes
            H = np.asarray(H, np.float64)
            g = np.clip(np.arange(F) - int(start), 0, len(H) - 1)
            at = H[g]                                                           # (F, m, 3) in the parent's frame
            ahead = np.einsum('fij,fmj->fmi', WR[:, idx[s['driver']]] @ s['offset'], at)[:, :, 2]
            T[:, p] = at[np.arange(F), np.argmax(ahead, 1)]
        elif s['kind'] == 'root' and roots is not None:                         # a root point
            o = np.asarray(roots[min(s['root'], len(roots) - 1)], np.float64)
            H = animation.local_rotation(values[:, retarget.HARA_CH], conv.kind)
            T[:, p] = np.einsum('fji,fj->fi', H, conv.scale * (k * o[None] - values[:, 1]))
        else:
            T[:, p], R[:, p] = s['bind']
    out = np.zeros((F, 2 * count, 3))
    out[:, 0::2] = T
    out[:, 1::2] = animation.axis_angles(R) if conv.kind == animation.COMPRESSED else retarget._euler(R)
    return out


def convert_body(blob, sk, target, kind=animation.COMPRESSED):
    """One Tekken 8 body clip (its PANM blob) -> a TTT2 body animation (bytes, big-endian; see Converter)."""
    return Converter(sk, target, kind).animation(blob)


# A TTT2 move's animation id: index i of the common motions (data004) or of its fighter's own motion pack (data005)
COMMON, PACK = 0x8000, 0x4000


def originals(m, banks, movesets, common, pack_of, donor_row):
    """TTT2's own animations of the older shared clips the fighter's moves play: {clip key: animation}. Those clips
    were made from TTT2's animations (778 of the 859 Reina's moves play pair with one by name), and converted back
    their chest is about 6 degrees off: TTT2's own is exact. A clip pairs with the animation of a TTT2 move named as
    a move of the fighter's that plays it, with as many frames; the animation is an id the converter takes as it is
    (COMMON | i, or PACK | i of the donor's motion pack; preferred in that order) or its bytes (big-endian) from
    another fighter's motion pack. (A clip a move the donor has plays is the donor's move's animation already:
    moveset.Converter's generic moves; Reina's other moves pair 9 more.) m: the fighter's moveset
    (tekken8.motbin.read, named, its banks attached); banks: anmbin.Banks; movesets: TTT2's by motion row
    (ttt2/motbin.read); common: data004's common motions; pack_of(row): data005's motion pack of that row;
    donor_row: the donor's motion row."""
    by_name = collections.defaultdict(list)
    for row, t in enumerate(movesets):
        for i in range(len(t.tables['moves'])):
            aid = t.tables['moves'][i]['anim']
            if aid & (COMMON | PACK):
                by_name[t.move_name(i)].append((row, aid))
    names = collections.defaultdict(set)                       # clip key -> the names of the moves playing it
    for i in range(len(m.tables['moves'])):
        key, bank = m.anim_ref(i)
        if bank == anmbin.SHARED and m.move_name(i) in by_name:
            names[key].add(m.move_name(i))
    motas = {}

    def mota(row):
        """(buffer, byte order, [animation offsets]) of the common motions (row None) or a row's body MOTA."""
        if row not in motas:
            if row is None:
                e, offs = motion.mota_offsets(common, 0)
                motas[row] = (common, e, offs)
            else:
                pk = pack_of(row)
                o0 = motion.pack_items(pk)[0][0]
                e, offs = motion.mota_offsets(pk, o0)
                motas[row] = (pk, e, [o0 + o for o in offs])
        return motas[row]
    out = {}
    for key, ns in names.items():
        found = sorted({c for n in ns for c in by_name[n]}, key=lambda c: (not c[1] & COMMON, c[0] != donor_row, c))
        blob = banks.blob(anmbin.BODY, key)
        if not found or blob is None:
            continue
        clip = panm.Animation(blob)
        if not clip.legacy:
            continue
        for row, aid in found:
            buf, e, offs = mota(None if aid & COMMON else row)
            n = aid & 0x3FFF
            if n >= len(offs):
                continue
            h = animation.header(buf, e, offs[n])
            if h['frames'] != clip.frames_at():
                continue
            if aid & COMMON or row == donor_row:
                out[key] = aid
            else:
                a = buf[offs[n]:offs[n] + h['size']]
                out[key] = bytes(a) if e == '>' else motion.swap_animation(a, e)
            break
    return out


class Animations:
    """The converter's animation provider for a Tekken 8 fighter: called with a move's anim_ref (key, bank), as one
    tuple (moveset.Converter) or two arguments -> the TTT2 animation (bytes, big-endian) of its body clip, TTT2's own
    (an id or bytes: originals, when given), or None (no such clip). banks: anmbin.Banks; converter: a Converter. Each
    clip is converted once; .stats counts them, .seconds the time taken. roots: {clip key: root point offsets} of the
    clips whose moves hit from root points (convert/summons8.py): converted with those pairs (TTT2's own original
    left aside); snakes: {clip key: (heads, start)} of the clips whose moves start a summoned model's clip
    (convert/snakes8.py), likewise."""

    def __init__(self, banks, converter, originals=None, roots=None, snakes=None):
        self.banks, self.converter = banks, converter
        self.originals = dict(originals or {})
        self.roots = dict(roots or {})
        self.snakes = dict(snakes or {})
        self.cache = {}
        self.stats = collections.Counter()
        self.seconds = 0.0

    def __call__(self, key, bank=None):
        if isinstance(key, tuple):
            key, bank = key
        if key in self.cache:
            return self.cache[key]
        if key in self.originals and key not in self.roots and key not in self.snakes:
            self.stats['body animations TTT2 has (an older shared clip\'s original)'] += 1
            self.cache[key] = self.originals[key]
            return self.cache[key]
        blob = self.banks.blob(anmbin.BODY, key)
        out = None
        if blob is None:
            self.stats['body animations missing from both banks'] += 1
        else:
            t = time.time()
            try:
                extra = dict(roots=self.roots[key]) if key in self.roots else {}
                if key in self.snakes:          # (the snakes' heads: convert/snakes8.py)
                    extra['snakes'] = self.snakes[key]
                out = self.converter.animation(blob, **extra)
                self.stats['body animations converted (%s)' % self.banks.where(anmbin.BODY, key)] += 1
                if getattr(self.converter, 'pairs', None) and getattr(self.converter, 'last_pairs', 0):
                    self.stats['body animations with weapon pairs (%s)' % (
                        'root points too' if key in self.roots else 'snakes\' heads too' if key in self.snakes else
                        'weapons')] += 1
            except ValueError as e:
                self.stats['body animations not converted (%s)' % e] += 1
            self.seconds += time.time() - t
        self.cache[key] = out
        return out
