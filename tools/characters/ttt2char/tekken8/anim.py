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

Written for this project from the files themselves (no third-party code).
"""
import collections
import time

import numpy as np

from .. import InputError
from ..convert import retarget
from ..ttt2 import animation, motion
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

    def __init__(self, sk, target, kind=animation.COMPRESSED):
        self.sk, self.kind = sk, kind
        self.cal = retarget.Calibration(sk, LANDMARKS, DRIVERS, retarget.ttt2_skeleton(target))
        self.leg, self.own_leg = retarget.leg_length(target), bind_leg(sk)
        # the joints the channels need, and their ancestors: a small skeleton of its own
        want = [sk.index[j] for j in set(DRIVERS.values()) | {TOP, TRANS, ROT}]
        chain = sk.chain(want)
        at = {j: k for k, j in enumerate(chain)}
        self.sub = retarget.Skeleton([sk.names[j] for j in chain],
                                     [at[sk.parents[j]] if sk.parents[j] >= 0 else -1 for j in chain],
                                     sk.t[chain], sk.R[chain], sk.s[chain])

    def pose(self, anim):
        """The clip's source pose: (world rotations {joint: (F, 3, 3)}, root (F, 3) mm, displacement (F, 3) mm,
        yaw (F,), the leg (mm) its root is measured against, joints {name: panm.Joint}). The joints keep the
        fighter's own lengths (the clip's other translations are its authoring rig's); only the root moves."""
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
            if j.stored_translation and name in ROOT:
                Lt[:, i] = j.translation * CM
        WR, Wp = sub.fk(LR, Lt)
        world = {n: WR[:, sub.index[n]] for n in set(DRIVERS.values())}
        D = Wp[:, sub.index[TOP]]
        root = Wp[:, sub.index[ROT]] - D
        if FACING in J and J[FACING].stored_rotation:
            m = animation.quaternion_to_matrix(_quaternions(J[FACING].rotation))
            yaw = np.arctan2(m[:, 0, 2], m[:, 2, 2])
        else:
            yaw = np.zeros(F)
        return world, root, D, yaw, LEGACY_LEG if anim.legacy else self.own_leg, J

    def channels(self, anim):
        """(TTT2 body channel values (F, 23, 3), info {'frames', 'leg', 'root_scale'}) of a panm.Animation."""
        world, root, D, yaw, leg, _ = self.pose(anim)
        k = self.leg / leg
        values = retarget.body_channels(self.cal, world, root, D, yaw, k, self.kind)
        return values, dict(frames=anim.frames, leg=leg, root_scale=k)

    def animation(self, blob, endian='>'):
        """A TTT2 body animation (bytes) of a body clip's blob."""
        values, _ = self.channels(panm.Animation(blob))
        return retarget.encode(values, self.kind, endian)


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
    clip is converted once; .stats counts them, .seconds the time taken."""

    def __init__(self, banks, converter, originals=None):
        self.banks, self.converter = banks, converter
        self.originals = dict(originals or {})
        self.cache = {}
        self.stats = collections.Counter()
        self.seconds = 0.0

    def __call__(self, key, bank=None):
        if isinstance(key, tuple):
            key, bank = key
        if key in self.cache:
            return self.cache[key]
        if key in self.originals:
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
                out = self.converter.animation(blob)
                self.stats['body animations converted (%s)' % self.banks.where(anmbin.BODY, key)] += 1
            except ValueError as e:
                self.stats['body animations not converted (%s)' % e] += 1
            self.seconds += time.time() - t
        self.cache[key] = out
        return out
