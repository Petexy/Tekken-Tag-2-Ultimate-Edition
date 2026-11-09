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
                                            and rotation (channel 3); a joint's point (summons8.JOINT_SPOT):
                                            o = C (P_joint + S_joint offset - P_Top) + delta, each frame (C: the
                                            source's frame to this one, retarget.Calibration)
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
from ..convert import retarget, skeleton as model_skeleton
from ..ttt2 import animation, bone, motion
from . import anmbin, names, panm, uprops

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
    (animation.COMPRESSED) or 0xC8 (animation.RAW); hands: the hands' calibration exact (HandFrames)."""

    def __init__(self, sk, target, kind=animation.COMPRESSED, weapons=(), hands=False):
        self.sk, self.kind = sk, kind
        dst = retarget.ttt2_skeleton(target)
        self.cal = retarget.Calibration(sk, LANDMARKS, DRIVERS, dst)
        self.hands = HandFrames(sk, target) if hands else None
        if self.hands:                                  # the hand exactly where Tekken 8's is (HandFrames)
            self.cal.offsets.update(self.hands.wrists())
        self.leg, self.own_leg = retarget.leg_length(target), bind_leg(sk)
        self.scale = dst.scale
        # weapons posed by pairs (pair_specs; none: the 23 body channels only)
        self.pairs = pair_specs(sk, target, weapons, self.cal) if weapons else []
        grounds = [s for s in self.pairs if s is not None and s['kind'] == 'ground']
        self.follows = bool(grounds) and all(s['follow'] for s in grounds)     # the scene is where he is (root_point)
        # the joints the channels need, and their ancestors: a small skeleton of its own
        body = sk.chain([sk.index[j] for j in set(DRIVERS.values()) | {TOP, TRANS, ROT}])
        want = body + [sk.index[j] for j in pair_joints(self.pairs)]
        chain = sk.chain(want)
        at = {j: k for k, j in enumerate(chain)}
        self.sub = retarget.Skeleton([sk.names[j] for j in chain],
                                     [at[sk.parents[j]] if sk.parents[j] >= 0 else -1 for j in chain],
                                     sk.t[chain], sk.R[chain], sk.s[chain])
        self.moved = {sk.names[j] for j in chain if j not in set(body)}     # the weapons' joints (pairs)
        self.scene = None                               # the hold clips (convert/prefabs8.py HoldClips)

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

    def channels(self, anim, roots=None, snakes=None, ground=False, shift=None):
        """(TTT2 body channel values (F, 23, 3), info {'frames', 'leg', 'root_scale', 'pairs'}) of a panm.Animation;
        with weapon pairs (F, 23 + 2 n, 3) when the clip moves a weapon's joint or `roots` (the move's root point
        offsets, mm: summons8.roots) or `snakes` (the heads its move's summoned clip moves and the frame it starts at:
        convert/snakes8.py) are given (pair_values). shift: (F, 3) mm added to his Top's path (a scene cut taken back:
        convert/prefabs8.py SCENE CUTS); his scene stands where the shift leaves it, all through the clip."""
        world, root, D, yaw, leg, J = self.pose(anim)
        k = self.leg / leg
        travel = None
        if shift is not None:
            if len(shift) != len(D):
                raise ValueError('a shift of %d frames for a clip of %d' % (len(shift), len(D)))
            travel = retarget.body_channels(self.cal, world, root, D + shift - shift[-1], yaw, k, self.kind)[:, 0]
            D = D + shift
        values = retarget.body_channels(self.cal, world, root, D, yaw, k, self.kind)
        count = 0
        if self.pairs:
            moving = any(n in self.moved and (j.stored_rotation or j.stored_translation) for n, j in J.items())
            count = max([p + 1 for p, s in enumerate(self.pairs) if s is not None and
                         (s['kind'] == 'root' and roots is not None or s['kind'] in ('joint', 'lead') and moving or
                          s['kind'] == 'snakes' and snakes is not None or s['kind'] == 'ground' and ground)]
                        or [0])
        if count:
            _, WR, Wp = self.fk(anim)
            values = np.concatenate([values, pair_values(self, WR, Wp, values, k, roots, count, snakes, ground,
                                                         travel)], 1)
        return values, dict(frames=anim.frames, leg=leg, root_scale=k, pairs=count)

    def animation(self, blob, endian='>', roots=None, snakes=None, ground=False, shift=None):
        """A TTT2 body animation (bytes) of a body clip's blob (roots, snakes, ground, shift: channels())."""
        values, info = self.channels(panm.Animation(blob), roots, snakes, ground, shift)
        self.last_pairs = info['pairs']
        return retarget.encode(values, self.kind, endian)


# ------------------------------------------------------------------------------------------------ hand clips
# A Tekken 8 fighter keeps Tekken 8's hands: its moves' hand properties
# name category-1 clips (one hand's L_ / R_ finger joints; values: list 1 of the bank's keys), as long as the move's
# body clip in almost all moves, and TTT2 plays the same kind of thing (ttt2/motion.py, hand animations). A finger's
# TTT2 bone follows its joint exactly: with S_j, D_j the joint's bind world rotation and the re-pose's turn of it
# (convert/skeleton.py) and B_b the bone's bind world rotation, the mesh on b is on j when G_b = A_j O_j, O_j = S_j^T
# D_j^T B_b, A_j the joint's world rotation. So the wrist's offset is exact too (the calibration's anatomical frame is 5
# degrees off the hand, and the weapon, posed by its joint, did not sit in it), and a finger's channel is
# L_b = O_p^T A_p^T A_j O_j, p the parent's joint or bone. The metacarpals (Index0 ..) have no bone: the first bone of
# a finger takes their turn too. The game applies a right hand's values as they are and a left hand's as (-x, y, -z)
# (measured: the bones' local matrices in game against the clip, 0 degrees off on all 30), so one set of numbers makes
# a fist on either hand.
HAND_JOINTS = (('OYA3', 'Thumb0'), ('OYA2', 'Thumb1'), ('OYA1', 'Thumb2'),
               ('HITO3', 'Index1'), ('HITO2', 'Index2'), ('HITO1', 'Index3'),
               ('NAKA3', 'Middle1'), ('NAKA2', 'Middle2'), ('NAKA1', 'Middle3'),
               ('KUSU3', 'Ring1'), ('KUSU2', 'Ring2'), ('KUSU1', 'Ring3'),
               ('KO3', 'Pinky1'), ('KO2', 'Pinky2'), ('KO1', 'Pinky3'))                 # the channels' order
WRISTS = {'R': 'TE_R_jnt', 'L': 'TE_L_jnt'}
HAND_UNIT = 32768.0 / np.pi


class HandFrames:
    """The frames that put a TTT2 hand on a Tekken 8 hand. sk: the fighter's skeleton; target: bone.read() of the TTT2
    skeleton (the fighter's own, with the model re-posed on it)."""

    def __init__(self, sk, target):
        self.sk = sk
        SR, SP = sk.bind_world()
        n = len(sk.names)
        W = np.zeros((n, 4, 4))
        W[:, :3, :3], W[:, :3, 3], W[:, 3, 3] = SR, SP, 1.0
        follow = [None] * n
        for i, x in enumerate(sk.names):
            f = names.follow(x)
            if f is not None and f[0] in sk.index:
                follow[i] = (sk.index[f[0]], float(f[1]))
        done = model_skeleton.repose(dict(bones=dict(names=[names.canonical(x) for x in sk.names], parents=sk.parents,
                                                     world=W, follow=follow), prims=[]), target,
                                     log=lambda *_: None)
        D = done['bones']['world'][:, :3, :3] @ np.swapaxes(SR, -1, -2)
        self.dst = retarget.ttt2_skeleton(target)
        B, _ = self.dst.bind_world()

        def offset(joint, b):
            i = sk.index[joint]
            return SR[i].T @ D[i].T @ B[self.dst.index[b]]
        self.wrist = {s: offset('%s_Hand' % s, w) for s, w in WRISTS.items()}
        self.fingers = {s: [offset('%s_%s' % (s, j), '%s_%s' % (b, s)) for b, j in HAND_JOINTS] for s in WRISTS}
        # (the little finger hangs from a base bone that holds its bind)
        self.base = {s: self.dst.R[self.dst.index['KO_%s_BASE' % s]] for s in WRISTS}

    def wrists(self):
        """{TTT2 hand bone: its calibration offset}"""
        return {WRISTS[s]: self.wrist[s] for s in WRISTS}

    def values(self, anim):
        """(F, 45) i16 of a hand clip (panm.Animation): TTT2's hand animation of the same pose."""
        J = anim.joints()
        sides = {name[0] for name in J if name[:2] in ('L_', 'R_')}
        if len(sides) != 1:
            raise ValueError('a hand clip holds one hand\'s joints')
        s = sides.pop()
        sk, F = self.sk, anim.frames
        hand = sk.index['%s_Hand' % s]
        local = {}

        def rel(i):                                     # the joint's rotation in the hand's frame, per frame
            if i == hand:
                return np.broadcast_to(np.eye(3), (F, 3, 3))
            if i not in local:
                j = J.get(sk.names[i])
                r = animation.quaternion_to_matrix(_quaternions(j.rotation)) \
                    if j is not None and j.stored_rotation else np.broadcast_to(sk.R[i], (F, 3, 3))
                local[i] = rel(sk.parents[i]) @ r
            return local[i]
        L = np.zeros((F, len(HAND_JOINTS), 3, 3))
        O = self.fingers[s]
        for c, (b, joint) in enumerate(HAND_JOINTS):
            A = rel(sk.index['%s_%s' % (s, joint)])
            if b[-1] == '3':                            # under the hand
                up = self.wrist[s] @ self.base[s] if b == 'KO3' else self.wrist[s]
                L[:, c] = up.T @ A @ O[c]
            else:
                up = rel(sk.index['%s_%s' % (s, HAND_JOINTS[c - 1][1])])
                L[:, c] = O[c - 1].T @ np.swapaxes(up, -1, -2) @ A @ O[c]
        # (from no turn: the triple TTT2's own hands have, a curl about +z, its axis not at the wrap of the i16s)
        v = np.rint(animation.axis_angles(L, np.zeros((len(HAND_JOINTS), 3))) * HAND_UNIT).astype(np.int64).reshape(F, -1)
        if s == 'L':                                    # (the game reads a left hand's values as -x, y, -z)
            v[:, 0::3] *= -1
            v[:, 2::3] *= -1
        return ((v + 32768) & 0xFFFF) - 32768


class HandClips:
    """A fighter's hand clips by the value its moves' hand properties give: banks (anmbin.Banks), frames: HandFrames."""

    def __init__(self, banks, frames):
        self.banks, self.frames = banks, frames
        self.keys = banks.own.key_lists[anmbin.HANDS]
        self.cache = {}
        self.stats = collections.Counter()

    def values(self, value):
        """(F, 45) i16 of clip `value`, None if neither bank has it."""
        if value not in self.cache:
            out = None
            blob = self.banks.blob(anmbin.HANDS, self.keys[value]) if 0 <= value < len(self.keys) else None
            if blob is None:
                self.stats['hand clips missing from both banks'] += 1
            else:
                out = self.frames.values(panm.Animation(blob))
                self.stats['hand clips converted (%s)' % self.banks.where(anmbin.HANDS, self.keys[value])] += 1
            self.cache[value] = out
        return self.cache[value]

    def body_frames(self, key):
        """The frames of a move's body clip (0: not in the banks)."""
        blob = self.banks.blob(anmbin.BODY, key)
        return panm.Animation(blob).frames if blob is not None else 0

    def animation(self, value, frames=0):
        """A TTT2 hand animation of clip `value` (None: no clip), at least `frames` long (its last frame held: a hand
        animation starts over at its end, which Tekken 8's hand never shows)."""
        v = self.values(value)
        if v is None:
            return None
        if len(v) < frames:
            v = np.concatenate([v, np.repeat(v[-1:], frames - len(v), 0)])
        return motion.encode_hand_animation(v.tolist())

    def hold(self, value):
        """A TTT2 hand animation holding clip `value`'s last frame (None: no clip)."""
        v = self.values(value)
        return None if v is None else motion.encode_hand_animation(np.repeat(v[-1:], 2, 0).tolist())


# ------------------------------------------------------------------------------------------------ weapon pairs
WEAPON_FIRST = 800                          # weapons.OPT_FIRST: bone OPT 800 + k takes pair k
NAME_LENGTH = 31                            # weapons.NAME_LENGTH (with 'cha:')
ROOT_PARENT = 'HARA_ROT1'
HELD = 'held'                               # a clip's ground: its scene stays where the move began (prefabs8 HELD SCENES)
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
        elif w.get('channels') is not None:                      # (a bone numbered below 800, posed by that pair)
            of_name[('cha:OPT%d_%s' % (w['number'], w['bone']))[:NAME_LENGTH][4:]] = w
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
        elif w.get('ground'):                                    # (convert/prefabs8.py)
            spec.update(kind='ground', follow=not w.get('held', True))
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
        out[w['pair'] if w.get('pair') is not None else w['channels']] = spec
    return [out.get(k) for k in range(max(out) + 1)] if out else []


def pair_joints(specs):
    """The Tekken 8 joints the specs' pairs are made of."""
    out = []
    for s in specs:
        if s is None or s['kind'] in ('root', 'still', 'ground'):
            continue
        out += s['joints'] if s['kind'] == 'lead' else [] if s['kind'] == 'snakes' else [s['joint']]
        out += [x for x in (s.get('driver'), s.get('up'), s.get('anchor')) if x]
    return sorted(set(out))


def root_point(conv, WR, Wp, values, k, o, follows=None, travel=None):
    """(F, 3) a root point of a clip through its frames: an offset from the ground origin, a joint's point, or a hold
    clip's path (prefabs8.py), in HARA's frame. follows: whether the scene is where he is (default conv.follows);
    travel: the root channel the scene keeps to (default his: values[:, 0])."""
    F = len(values)
    idx = conv.sub.index
    H = animation.local_rotation(values[:, retarget.HARA_CH], conv.kind)
    if o[0] == 'scene':
        at, turn_of = conv.scene(o[4], o[1])
        g = np.clip(np.arange(F) - (int(o[5]) - 1), 0, len(at) - 1)
        X = at[g] + np.einsum('fij,j->fi', turn_of[g], np.asarray(o[2], np.float64)) + np.asarray(o[3], np.float64)
        turn = animation.local_rotation(values[:, retarget.TURN], conv.kind)
        if follows is None:
            follows = getattr(conv, 'follows', False)
        back = 0 if follows else conv.scale * (values[:, 0] if travel is None else travel)  # (where he is: Top's)
        return np.einsum('fji,fj->fi', H, np.einsum('fij,fj->fi', turn, X - back) - conv.scale * values[:, 1])
    if isinstance(o[0], str):                                                   # a joint's point, frame by frame
        j = idx[o[1]]
        o = (Wp[:, j] + np.einsum('fij,j->fi', WR[:, j], np.asarray(o[2], np.float64)) - Wp[:, idx[TOP]]) @ \
            conv.cal.C.T + np.asarray(o[3], np.float64)
    else:
        o = np.asarray(o, np.float64)[None]
    return np.einsum('fji,fj->fi', H, conv.scale * (k * o - values[:, 1]))


def pair_values(conv, WR, Wp, values, k, roots, count, snakes=None, ground=False, travel=None):
    """The extra channels (F, 2 count, 3) of pairs 0 .. count - 1 (conv.pairs; see the module's notes) of a clip:
    WR, Wp its forward kinematics (Converter.fk), values its body channels, k its root scale, roots its root point
    offsets (or None: those pairs hold their bind), snakes (heads (G, m, 3) mm in the parent's frame, the frame
    index the summoned clip starts at) or None; ground: True to pose the ground (where his Top is with a following
    ground), HELD to pose it where the move began all the same (its scene's root points with it); travel: the root
    channel the scene keeps to when his own was shifted (channels' shift: where the shift leaves it), else None."""
    F = len(values)
    idx = conv.sub.index
    follows = getattr(conv, 'follows', False) and ground != HELD
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
            o = roots[min(s['root'], len(roots) - 1)]
            if o[0] == 'windows':                                               # other points from frame to frame
                for start, stop, spot in o[1]:                                  # (prefabs8.root_windows)
                    T[start:stop, p] = root_point(conv, WR, Wp, values, k, spot, follows, travel)[start:stop]
            else:
                T[:, p] = root_point(conv, WR, Wp, values, k, o, follows, travel)
        elif s['kind'] == 'ground' and ground:                                  # the scene's origin: where Top is at
            H = animation.local_rotation(values[:, retarget.HARA_CH], conv.kind)   # the clip's frame 0, not turned
            turn = animation.local_rotation(values[:, retarget.TURN], conv.kind)
            x = values[:, 0] if travel is None else travel
            back = 0 if s.get('follow') and ground != HELD else np.einsum('fij,fj->fi', turn, -x)
            T[:, p] = np.einsum('fji,fj->fi', H, conv.scale * (back - values[:, 1]))   # (follow: where Top is now,
            R[:, p] = np.swapaxes(H, -1, -2) @ turn                                     # his body's creatures)
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
    (convert/snakes8.py), likewise; shifts: {clip key: (frames, 3) mm added to its Top's path} (prefabs8.scene_cuts)."""

    def __init__(self, banks, converter, originals=None, roots=None, snakes=None, ground=None, held=None,
                 shifts=None):
        self.banks, self.converter = banks, converter
        self.ground = set(ground or ())    # (the clips of moves showing a prefab: convert/prefabs8.py)
        self.held = set(held or ())        # (... of those, the ones whose scene stays where the move began)
        self.shifts = dict(shifts or {})   # (clip key -> its Top's shift: prefabs8.scene_cuts)
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
        if key in self.originals and key not in self.roots and key not in self.snakes and key not in self.ground \
                and key not in self.shifts:
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
                if key in self.ground:
                    extra['ground'] = HELD if key in self.held else True
                if key in self.shifts:
                    extra['shift'] = self.shifts[key]
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
