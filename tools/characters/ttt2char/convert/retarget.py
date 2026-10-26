"""Another game's body motion -> TTT2's 23 body channels (ttt2/animation.py), engine-neutral: the source game's side
(tekken8/anim.py for Tekken 8) supplies its skeleton (a bind pose with its own posture, joint axes and proportions),
the landmark joints the two skeletons are matched by, which of its joints drive which TTT2 bones, and per frame its
joints' world rotations and its root motion; this file turns them into channel values for any TTT2 skeleton
(bone.read: a donor's, or the added fighter's skeleton.build).

Spaces: TTT2's model space (millimetres, Y up, the fighter facing +Z with its left at +X); rotations are 3x3
matrices acting on column vectors (v_parent = R v_child + t, the .bon convention). A source in other axes passes the
3x3 `basis` (its axes -> TTT2's); Tekken 8's are TTT2's.

1. Calibration, once per (source skeleton, TTT2 skeleton), from the two bind poses only: for each driven TTT2 bone b
   with source joint j an anatomical frame F (columns: a primary direction, a secondary one made orthogonal to it,
   their cross product) is built in each skeleton from landmark positions (RULES: the upper arm = shoulder -> elbow
   with the forward axis, the pelvis = hara -> the hips' centre with the hip line, the foot level, heading for the
   toes, the hand in its forearm's frame, ...). TTT2's bone posed as the source's bind is: G_ref = F_src F_ttt2^T
   G_bind; the constant offset O_b = (C S_j_bind)^T G_ref then maps the source joint's world rotation to the bone's at
   any frame. The source's bind posture (Tekken 8's A-pose against TTT2's T-pose) and its joints' axis conventions
   cancel here. (Checked on Tekken 8 clips made from TTT2 animations: the legs and feet, the neck, head, arms and
   hands relative to the chest come out within 0.05-0.2 degrees of the TTT2 originals, p50; the feet aimed at the
   toes were 5 degrees off, the hands aimed at the middle finger 5 degrees.)
2. Per frame: G_b = C S_j(t) O_b, in the model space BEFORE the turn (channel 2 turns the model on top; a source
   whose joints carry its facing must turn them back first). MUNE2 (the chest: it carries the arms and the neck) has
   no channel: MUNE1's is solved so that MUNE2 gets its driver's rotation, G_MUNE1 = G_MUNE2 B_MUNE2^T. HARA_ROT1
   keeps its bind rotation (the identity) unless it has a driver: TTT2's own animations leave it so in most frames
   (half of Jun's frames: exactly), KOSHI and MUNE1 carrying the pelvis and the chest. Any other bone without a
   driver keeps its bind local rotation. Local rotations L_b = G_parent^T G_b; 0x64 values = continuous axis-angle
   triples (animation.axis_angles), 0xC8 values = Euler angles (R = Rz Ry Rx).
3. Root: channel 0 = k C D (the ground displacement; y = 0), channel 1 = k C r (HARA_ROT1's position relative to the
   displaced origin, not turned), both in TTT2's units before the fighter's scale; channel 2 = the turn, a yaw
   (0x64: x = -pi/2, y = 0, z = -yaw: the axis +Y, the local rotation Ry(yaw); 0xC8: (0, yaw, 0)); channel 6 =
   (0, 0, 0): the spine parameter that turns TTT2's spine post-process (sub_069E1168) off, so the chest is the
   source's (most of the game's own frames hold -400: the post-process then leans the chest about 5 degrees, up to
   18; in the frames that hold 0 TTT2's chest is Tekken 8's conversion of it within 0.14 degrees).
   k = root_scale: source units -> TTT2's, e.g. the TTT2 skeleton's leg (leg_length) / the source rig's.

Written for this project from the files themselves (no third-party code).
"""
import numpy as np

from ..ttt2 import animation, bone

# channel 6: x = 0 turns the spine post-process off (the source's chest as it is; the game's own frames mostly hold
# -400, which leans the chest at run time)
SPINE_PARAMETER = (0.0, 0.0, 0.0)
# the TTT2 bones every TTT2 skeleton has at these indices (bones 0..21 animated; the game's channel table names them
# by index: animation.BODY_BONES)
HARA, MUNE1, MUNE2 = 0, 1, 2
ANIMATED = 22
MAX_SHIFT = 7                       # the rotation shift byte's low 7 bits

# ------------------------------------------------------------------------------------------------ landmarks
# a landmark = a joint whose BIND position the anatomical frames are built from ('hips': the hip joints' midpoint);
# a source names the same landmarks in its own skeleton
TTT2_LANDMARKS = {'hara': 'HARA_ROT1', 'chest': 'MUNE2_jnt', 'neck': 'KUBI_jnt', 'head': 'ATAMA_jnt'}
for _s in 'RL':
    TTT2_LANDMARKS.update({'clav_' + _s: 'SAKOTSU_%s_jnt' % _s, 'shoulder_' + _s: 'KATA_%s_jnt' % _s,
                           'elbow_' + _s: 'UDE_%s_jnt' % _s, 'wrist_' + _s: 'TE_%s_jnt' % _s,
                           'hip_' + _s: 'MOMO_%s_jnt' % _s,
                           'knee_' + _s: 'HIZA_%s_jnt' % _s, 'ankle_' + _s: 'ASHI_%s_jnt' % _s,
                           'toe_' + _s: 'TSUMASAKI_%s_jnt' % _s})
# TTT2 bone -> (primary, secondary) direction: a landmark pair (from, to) or a model axis. The foot is level (both
# games bind it flat on the floor; its ankle -> toe line slopes otherwise in each) and the hand keeps its forearm's
# frame (both binds hold it in line with the forearm): what the clips made from TTT2 animations show
RULES = {'HARA_ROT1': (('hara', 'chest'), ('hip_R', 'hip_L')),
         'KOSHI_jnt': (('hara', 'hips'), ('hip_R', 'hip_L')),
         'MUNE2_jnt': (('chest', 'neck'), ('clav_R', 'clav_L')),
         'KUBI_jnt': (('neck', 'head'), ('clav_R', 'clav_L')),
         'ATAMA_jnt': ('up', 'left')}
for _s in 'RL':
    RULES.update({'SAKOTSU_%s_jnt' % _s: (('clav_' + _s, 'shoulder_' + _s), 'fwd'),
                  'KATA_%s_jnt' % _s: (('shoulder_' + _s, 'elbow_' + _s), 'fwd'),
                  'UDE_%s_jnt' % _s: (('elbow_' + _s, 'wrist_' + _s), 'fwd'),
                  'TE_%s_jnt' % _s: (('elbow_' + _s, 'wrist_' + _s), 'fwd'),
                  'MOMO_%s_jnt' % _s: (('hip_' + _s, 'knee_' + _s), 'fwd'),
                  'HIZA_%s_jnt' % _s: (('knee_' + _s, 'ankle_' + _s), 'fwd'),
                  'ASHI_%s_jnt' % _s: ('up', ('ankle_' + _s, 'toe_' + _s))})
AXES = {'up': np.array([0, 1.0, 0]), 'left': np.array([1.0, 0, 0]), 'fwd': np.array([0, 0, 1.0])}


# ------------------------------------------------------------------------------------------------ skeletons
class Skeleton:
    """names, parents (-1: a root), bind local translations t (n, 3), rotations R (n, 3, 3), optional scales s (n, 3)
    (they scale the children's offsets, as in an Unreal / Maya joint chain)."""

    def __init__(self, names, parents, t, R, s=None):
        self.names = list(names)
        self.parents = [int(p) for p in parents]
        self.t = np.asarray(t, np.float64)
        self.R = np.asarray(R, np.float64)
        self.s = np.ones_like(self.t) if s is None else np.asarray(s, np.float64)
        self.index = {n: i for i, n in enumerate(self.names)}
        self.order = self._order()

    def _order(self):
        """Parents before children."""
        done, order = set(), []
        while len(order) < len(self.names):
            before = len(order)
            for i, p in enumerate(self.parents):
                if i not in done and (p < 0 or p in done):
                    done.add(i)
                    order.append(i)
            if len(order) == before:
                raise ValueError('the skeleton\'s parents make a loop')
        return order

    def chain(self, joints):
        """The joints (indices) and all their ancestors, parents first."""
        need = set()
        for j in joints:
            while j >= 0 and j not in need:
                need.add(j)
                j = self.parents[j]
        return [i for i in self.order if i in need]

    def fk(self, local_R=None, local_t=None, joints=None):
        """World rotations (F, n, 3, 3) and positions (F, n, 3) of local rotations / translations (F, n, ...) (None:
        the bind's); with `joints` (indices) only those and their ancestors are computed (the rest left 0)."""
        n = len(self.names)
        LR = self.R[None] if local_R is None else np.asarray(local_R, np.float64)
        Lt = self.t[None] if local_t is None else np.asarray(local_t, np.float64)
        F = max(LR.shape[0], Lt.shape[0])
        LR = np.broadcast_to(LR, (F, n, 3, 3))
        Lt = np.broadcast_to(Lt, (F, n, 3))
        WR = np.zeros((F, n, 3, 3))
        WM = np.zeros((F, n, 3, 3))                      # rotation x scale (for the children's offsets)
        Wp = np.zeros((F, n, 3))
        for i in (self.order if joints is None else self.chain(joints)):
            p = self.parents[i]
            if p < 0:
                WR[:, i] = LR[:, i]
                Wp[:, i] = Lt[:, i]
            else:
                WR[:, i] = WR[:, p] @ LR[:, i]
                Wp[:, i] = Wp[:, p] + np.einsum('fij,fj->fi', WM[:, p], Lt[:, i])
            WM[:, i] = WR[:, i] * self.s[i][None, None, :]
        return WR, Wp

    def bind_world(self):
        WR, Wp = self.fk()
        return WR[0], Wp[0]


def _strip(name):
    return name[4:] if name.startswith('cha:') else name


def ttt2_skeleton(bon):
    """The Skeleton of a TTT2 skeleton (bone.read; names without 'cha:'), .scale its size scale."""
    R = np.array([bone.matrix_from_euler_xyz(np.asarray(r, np.float64)) for r in bon['r']])
    sk = Skeleton([_strip(x) for x in bon['names']], bon['parent'], np.asarray(bon['t'], np.float64), R)
    sk.scale = float(bon['scale'])
    return sk


def leg_length(bon):
    """A TTT2 skeleton's thigh + shin (the knee's and the ankle's offsets, both sides' mean) in its units before the
    size scale: what channels 0 and 1 are measured against (860 in every base skeleton of the game)."""
    names = [_strip(x) for x in bon['names']]
    t = np.asarray(bon['t'], np.float64)
    legs = [np.linalg.norm(t[names.index('HIZA_%s_jnt' % s)]) + np.linalg.norm(t[names.index('ASHI_%s_jnt' % s)])
            for s in 'RL']
    return float(np.mean(legs) / bon['scale'])


# ------------------------------------------------------------------------------------------------ calibration
def _landmarks(sk, table, basis=np.eye(3)):
    _, Wp = sk.bind_world()
    P = {k: basis @ Wp[sk.index[v]] for k, v in table.items() if v in sk.index}
    if 'hip_R' in P and 'hip_L' in P:
        P['hips'] = (P['hip_R'] + P['hip_L']) / 2
    return P


def _direction(P, spec):
    if isinstance(spec, str):
        return AXES[spec].copy()
    a, b = spec
    return P[b] - P[a]


def anatomical_frame(P, rule):
    """Columns: the rule's primary direction, its secondary made orthogonal to it, primary x secondary."""
    p = _direction(P, rule[0])
    p = p / np.linalg.norm(p)
    s = _direction(P, rule[1])
    s = s - p * (s @ p)
    ns = np.linalg.norm(s)
    if ns < 1e-6:
        raise ValueError('the frame rule %s has parallel directions' % (rule,))
    s = s / ns
    return np.stack([p, s, np.cross(p, s)], 1)


class Calibration:
    """src: the source's Skeleton (its bind), src_landmarks {landmark: source joint name}, drivers {TTT2 bone name:
    source joint name}, dst: ttt2_skeleton() of the TTT2 skeleton, basis: the source's axes -> TTT2's (3x3).
    .offsets {TTT2 bone: O_b}, .dst, .src, .drivers."""

    def __init__(self, src, src_landmarks, drivers, dst, basis=np.eye(3)):
        self.src, self.dst, self.C = src, dst, np.asarray(basis, np.float64)
        self.drivers = {b: j for b, j in drivers.items() if b in dst.index}
        missing = sorted(j for j in self.drivers.values() if j not in src.index)
        if missing:
            raise ValueError('the source skeleton has no joint %s' % ', '.join(missing))
        Ps, Pd = _landmarks(src, src_landmarks, self.C), _landmarks(dst, TTT2_LANDMARKS)
        SR, _ = src.bind_world()
        DR, _ = dst.bind_world()
        self.offsets = {}
        for b, j in self.drivers.items():
            G_ref = anatomical_frame(Ps, RULES[b]) @ anatomical_frame(Pd, RULES[b]).T @ DR[dst.index[b]]
            self.offsets[b] = (self.C @ SR[src.index[j]]).T @ G_ref
        self.parents = dst.parents[:ANIMATED]
        self.bind = dst.R[:ANIMATED]


# ------------------------------------------------------------------------------------------------ channels
def _euler(m):
    """Vectorised animation.euler_from_matrix: (..., 3, 3) -> (x, y, z) with R = Rz Ry Rx."""
    m = np.asarray(m, np.float64)
    y = np.arcsin(np.clip(-m[..., 2, 0], -1, 1))
    lock = np.abs(m[..., 2, 0]) >= 1 - 1e-9                    # gimbal lock: x folded into z
    x = np.where(lock, 0.0, np.arctan2(m[..., 2, 1], m[..., 2, 2]))
    z = np.where(lock, np.arctan2(-m[..., 0, 1], m[..., 1, 1]), np.arctan2(m[..., 1, 0], m[..., 0, 0]))
    return np.stack([x, y, z], -1)


def body_channels(cal, world, root, displacement=None, yaw=None, root_scale=1.0, kind=animation.COMPRESSED):
    """TTT2 body channel values (F, 23, 3) (float64; the type `kind`'s rotation values) of a source pose:
    world {source joint name: (F, 3, 3) world rotations, source axes, before the turn} (at least the drivers'),
    root (F, 3): the hara's position relative to the displaced origin, displacement (F, 3) (None: 0), yaw (F,)
    radians about +Y (None: 0), root_scale: source units -> TTT2's before the fighter's scale."""
    root = np.asarray(root, np.float64)
    F = len(root)
    D = np.zeros((F, 3)) if displacement is None else np.asarray(displacement, np.float64)
    yw = np.zeros(F) if yaw is None else np.unwrap(np.asarray(yaw, np.float64))
    dst = cal.dst
    G = {}
    for b, j in cal.drivers.items():
        G[dst.index[b]] = (cal.C @ world[j]) @ cal.offsets[b]
    if MUNE2 in G:
        G[MUNE1] = G.pop(MUNE2) @ cal.bind[MUNE2].T
    W = {}
    top = np.broadcast_to(np.eye(3), (F, 3, 3))
    for i in range(ANIMATED):                                   # parents come first in every TTT2 skeleton
        p = cal.parents[i]
        W[i] = np.broadcast_to(G[i] if i in G else (W[p] if p >= 0 else top) @ cal.bind[i], (F, 3, 3))
    values = np.zeros((F, len(animation.BODY_BONES), 3))
    chans = [c for c, b in enumerate(animation.BODY_BONES) if b >= 0]
    L = np.stack([np.swapaxes(W[cal.parents[b]] if cal.parents[b] >= 0 else top, -1, -2) @ W[b]
                  for b in (animation.BODY_BONES[c] for c in chans)], 1)          # (F, channels, 3, 3)
    values[:, chans] = animation.axis_angles(L) if kind == animation.COMPRESSED else _euler(L)
    k = float(root_scale)
    ch0 = k * (D @ cal.C.T)
    ch0[:, 1] = 0.0
    values[:, 0] = ch0
    values[:, 1] = k * (root @ cal.C.T)
    if kind == animation.COMPRESSED:
        values[:, 2] = np.stack([np.full(F, -np.pi / 2), np.zeros(F), -yw], 1)
    else:
        values[:, 2] = np.stack([np.zeros(F), yw, np.zeros(F)], 1)
    values[:, 6] = SPINE_PARAMETER
    return values


# ------------------------------------------------------------------------------------------------ hand-offs
# TTT2 prepares a move's hand-off: PREBLEND frames before the end of the move's animation it samples the animation of
# the move's transition at its frame 0 (sub_06897540, the transition's id at move +0x30) and over those frames turns
# every bone's rotation to that pose (nlerp of the sampler's quaternions, the hemisphere tested; weight (f - (end -
# PREBLEND)) / PREBLEND) EXCEPT HARA_ROT1's and the turn's, which keep the animation's until the next move starts.
# The game composes the two as world = T^T H L (T = local_rotation(turn), H = HARA_ROT1's, L a child's: MUNE1 or KOSHI;
# T^T because the turn is the inverse of its local rotation: checked in game on the bone records and on 8 of Jun's
# throws' hand-offs into the down moves, all continuous so). TTT2's own animations carry the body's orientation in
# HARA_ROT1 when it is far from upright (lying: 90 degrees), and its throws mostly end with the turn and HARA_ROT1 of
# the down move they hand off to (Jun's 1+3), so the pre-blend moves little. A converted clip keeps HARA_ROT1 upright
# (identity) with the turn the
# source's (Tekken 8: MUKI), KOSHI and MUNE1 carrying the rest: the same world pose in another split. Blending its
# children toward TTT2's while HARA_ROT1 stays upright sat the thrown opponent up over the last 15 frames of each of
# Reina's throws (the head 0.5 m over the hips), and the next move then snapped HARA_ROT1 down (the user: "the enemy
# is weirdly glitching for like 2 frames after grabs"). handoff() re-splits a clip's tail: the same world pose, its
# turn and HARA_ROT1 those of the next animation's frame 0 by the time the pre-blend starts.
PREBLEND = 15                      # frames of the game's pre-blend (Jun's and Reina's throws in game: 15)
HANDOFF_WINDOW = 10                # frames over which the split moves, ending one frame before the pre-blend
HANDOFF_MATCH = 20.0               # degrees: HARA_ROT1 becomes exactly the next's when KOSHI's world is this close
HANDOFF_NEEDED = 10.0              # degrees between the clip's last HARA_ROT1 and the next's that call for a re-split
TURN, HARA_CH, CHILD_CHANNELS = 2, 3, (4, 5)      # channels: the turn, HARA_ROT1, its children MUNE1 and KOSHI


def _quat(m):
    """Unit quaternions (..., 4) (x, y, z, w; w >= 0) of rotation matrices (..., 3, 3) (column vectors)."""
    m = np.asarray(m, np.float64)
    w = np.sqrt(np.clip(1 + m[..., 0, 0] + m[..., 1, 1] + m[..., 2, 2], 0, None)) / 2
    x = np.sqrt(np.clip(1 + m[..., 0, 0] - m[..., 1, 1] - m[..., 2, 2], 0, None)) / 2
    y = np.sqrt(np.clip(1 - m[..., 0, 0] + m[..., 1, 1] - m[..., 2, 2], 0, None)) / 2
    z = np.sqrt(np.clip(1 - m[..., 0, 0] - m[..., 1, 1] + m[..., 2, 2], 0, None)) / 2
    x = np.copysign(x, m[..., 2, 1] - m[..., 1, 2])
    y = np.copysign(y, m[..., 0, 2] - m[..., 2, 0])
    z = np.copysign(z, m[..., 1, 0] - m[..., 0, 1])
    return np.stack([x, y, z, w], -1)


def _matrix(q):
    """Rotation matrices (..., 3, 3) of quaternions (..., 4) (x, y, z, w), column vectors."""
    q = np.asarray(q, np.float64)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    return animation.quaternion_to_matrix(q)


def slerp(Ra, Rb, s):
    """Rotations (..., 3, 3) a fraction s (...) of the way from Ra to Rb (the shorter way)."""
    qa, qb = _quat(Ra), _quat(Rb)
    s = np.asarray(s, np.float64)
    d = (qa * qb).sum(-1)
    qb = np.where((d < 0)[..., None], -qb, qb)
    d = np.abs(d)
    th = np.arccos(np.clip(d, -1, 1))
    small = th < 1e-6
    sin = np.where(small, 1.0, np.sin(th))
    wa = np.where(small, 1 - s, np.sin((1 - s) * th) / sin)
    wb = np.where(small, s, np.sin(s * th) / sin)
    return _matrix(wa[..., None] * qa + wb[..., None] * qb)


def _rotations(v, kind):
    return animation.local_rotation(np.asarray(v, np.float64), kind)


def _turn_values(phi, kind):
    """Turn channel values of the yaw angles phi (local rotation Ry(phi))."""
    phi = np.asarray(phi, np.float64)
    z = np.zeros_like(phi)
    if kind == animation.COMPRESSED:
        return np.stack([np.full_like(phi, -np.pi / 2), z, -phi], -1)
    return np.stack([z, phi, z], -1)


def handoff_mismatch(values, kind, nxt, next_kind):
    """Degrees between HARA_ROT1's rotation at an animation's last frame (values (F, nch, 3) of type `kind`) and at
    the next animation's frame 0 (nxt (nch', 3), `next_kind`): what the pre-blend cannot bring together. 0 for a
    converted clip handing off to another converted clip or to an upright TTT2 move (the pre-blend turns the children
    there, the turn included: checked in game), about 90 for one ending lying and a TTT2 down move."""
    H = _rotations(np.asarray(values, np.float64)[-1, HARA_CH][None], kind)[0]
    Hn = _rotations(np.asarray(nxt, np.float64)[HARA_CH][None], next_kind)[0]
    return float(angle(H, Hn))


def handoff(values, kind, nxt, next_kind, preblend=PREBLEND, window=HANDOFF_WINDOW):
    """Body channel values (F, nch, 3) of an animation of type `kind` whose tail is re-split for the hand-off to an
    animation whose frame 0 has values `nxt` (nch', 3) of type `next_kind` (see PREBLEND): over `window` frames ending
    one frame before the pre-blend the turn goes to the next's and HARA_ROT1 to the next's (or, when the two world
    poses are further apart than HANDOFF_MATCH, to the rotation that gives KOSHI the next's), MUNE1 and KOSHI taking
    the difference, so every world rotation and position stays as it was (HARA_ROT1's own frame aside); the frames
    before the window are unchanged. The returned values are float64; the first frames' rotation values carry on into
    the changed ones (animation.axis_angles' continuity)."""
    v = np.array(values, np.float64)
    F = len(v)
    if F < 2:
        return v
    nxt = np.asarray(nxt, np.float64)
    last = F - 1
    w1 = max(1, last - preblend - 1)
    w0 = max(1, w1 - window)
    T = _rotations(v[:, TURN], kind)
    H = _rotations(v[:, HARA_CH], kind)
    R = np.swapaxes(T, -1, -2) @ H                                # the children's frame (world = T^T H L)
    Wc = {c: R @ _rotations(v[:, c], kind) for c in CHILD_CHANNELS}
    Tn = _rotations(nxt[TURN][None], next_kind)[0]
    Hn = _rotations(nxt[HARA_CH][None], next_kind)[0]
    Rn = Tn.T @ Hn
    Rk = Wc[5][last] @ _rotations(nxt[5][None], next_kind)[0].T  # KOSHI exactly the next's
    R_end = Rn if angle(Rk, Rn) <= HANDOFF_MATCH else Rk
    # the turn's yaw: the clip's (continuous) to the next's (its value: the hemisphere the game samples)
    phi = np.unwrap(np.arctan2(T[:, 0, 2], T[:, 0, 0]))
    phi_n = float(np.arctan2(Tn[0, 2], Tn[0, 0]))
    f = np.arange(F)
    s = np.clip((f - w0) / max(1, w1 - w0), 0.0, 1.0)
    s = s * s * (3 - 2 * s)                                       # smoothstep
    s[f >= w1] = 1.0
    new_phi = (1 - s) * phi + s * phi_n
    R_new = slerp(R, np.broadcast_to(R_end, R.shape), s)
    T_new = _rotations(_turn_values(new_phi, kind), kind)
    H_new = T_new @ R_new
    tail = slice(w0, F)
    out = v.copy()
    out[tail, TURN] = _turn_values(new_phi[tail], kind)
    if kind == animation.COMPRESSED:
        prev = v[w0 - 1, [HARA_CH] + list(CHILD_CHANNELS)]
        mats = np.stack([H_new[tail]] + [np.swapaxes(R_new[tail], -1, -2) @ Wc[c][tail] for c in CHILD_CHANNELS], 1)
        out[tail, [HARA_CH] + list(CHILD_CHANNELS)] = animation.axis_angles(mats, prev)
        # the last frame in the next's hemisphere (the game's pre-blend tests it; its own data never leaves it)
        for k, c in enumerate([HARA_CH] + list(CHILD_CHANNELS)):
            qa = animation.game_quaternion(out[last, c], kind)
            qb = animation.game_quaternion(nxt[c], next_kind)
            if qa @ qb < 0:
                out[tail, c, 2] += 2 * np.pi * (1 if out[last, c, 2] < 0 else -1)
    else:
        out[tail, HARA_CH] = _euler(H_new[tail])
        for c in CHILD_CHANNELS:
            out[tail, c] = _euler(np.swapaxes(R_new[tail], -1, -2) @ Wc[c][tail])
    return out


def rotation_shift(values):
    """The finest 0x64 rotation shift whose states hold every rotation value of body channel values (F, 23, 3)
    without wrapping: shift s steps by 2^s units of pi/32768 (0: 0.0055 degrees) over +-pi 2^s. Retargeted motion is
    smooth floats: at shift 0 the feet and hands stay within 0.13 mm (median of the clips' worst frames; 0.24 p99) of
    the unquantised pose, at the game's usual 4 within 2 mm, with 0.3 mm of frame-to-frame jitter on a planted foot,
    for 0.74 of the size (Reina's clips). The game stores some of its own so too (Jun's stance)."""
    v = np.asarray(values, np.float64)
    rot = [c for c, d in enumerate(animation.BODY_DESCRIPTORS) if animation.is_rotation(d)]
    top = float(np.abs(v[:, rot]).max()) if v.size else 0.0
    shift = 0
    while shift < MAX_SHIFT and np.round(top / (float(animation.ROTATION_UNIT) * (1 << shift))) > 32767:
        shift += 1
    return shift


# the rotation descriptors of a raw body animation: 7 (any axis) for every rotation, as the converter's raw holds
# (arcs.py) that run in game; the game's sampler only tests 4..7
RAW_DESCRIPTORS = tuple(animation.ROTATION if animation.is_rotation(d) else d for d in animation.BODY_DESCRIPTORS)


def encode(values, kind=animation.COMPRESSED, endian='>'):
    """A TTT2 body animation (bytes) of body_channels() values: 0x64 (compressed) or 0xC8 (raw)."""
    if kind == animation.COMPRESSED:
        return animation.encode_compressed(list(animation.BODY_DESCRIPTORS), values, endian,
                                           rotation_shift=rotation_shift(values))
    return animation.encode_raw(list(RAW_DESCRIPTORS), values, endian)


# ------------------------------------------------------------------------------------------------ checking
def pose(sk, values, kind=animation.COMPRESSED, root_motion=True):
    """World rotations (F, n, 3, 3) and positions (F, n, 3) of a TTT2 skeleton (ttt2_skeleton) posed by body channel
    values (F, nch, 3) of an animation of type `kind`: world = T(channel 0 x scale) Ry(turn) [HARA_ROT1 at channel 1
    x scale, the animated bones' local rotations from their channels, the rest the bind's]."""
    v = np.asarray(values, np.float64)
    F = v.shape[0]
    LR = np.repeat(sk.R[None], F, 0)
    Lt = np.repeat(sk.t[None], F, 0)
    for c, b in enumerate(animation.BODY_BONES):
        if b >= 0:
            LR[:, b] = animation.local_rotation(v[:, c], kind)
    Lt[:, HARA] = v[:, 1] * sk.scale
    WR, Wp = sk.fk(LR, Lt)
    if root_motion:
        T = animation.local_rotation(v[:, 2], kind)
        WR = T[:, None] @ WR
        Wp = np.einsum('fij,fnj->fni', T, Wp) + (v[:, 0] * sk.scale)[:, None]
    return WR, Wp


def angle(Ra, Rb):
    """Angles (degrees) between rotations (..., 3, 3), well conditioned near 0: |Ra - Rb| = 2 sqrt(2) sin(a / 2)."""
    d = np.linalg.norm(np.asarray(Ra) - np.asarray(Rb), axis=(-2, -1))
    return np.degrees(2 * np.arcsin(np.clip(d / (2 * np.sqrt(2)), 0, 1)))
