"""A Tekken 8 fighter's summoned creatures (Clive's: the moves' prefabs, each with a mesh, a skeleton and clips of its
own, played where the move was authored, not on his body) -> extra bones of the fighter's, played from part 3 of its
motion pack (the runtime's extra bones: title/roster.cpp; convert/tiger.py, convert/snakes8.py). A definition's PREFABS
asks for it; a fighter without one is not touched.

* ROWS. Tekken 8 starts a clip with START_PROP (value slot << 16 | kind << 8 | clip; the definition's 'kinds' name its
  table MissileAnimData <kind>), shows the prefab with SHOW_ROW (value slot, value2 the fade's frames, value3 the kind)
  and hides it with HIDE_ROW, stops the clips with STOP_PROP. A clip starts as its row fires (frame 0 there: the three
  moves playing the dog's lunge hit in clip frames 28-41 whatever frame they are entered at), and a row whose frame the
  move was entered past fires as the move is entered. A row's frame is a body frame, or (0x8000 + n) the n-th frame
  after the move's entry. prepare() makes START_PROP a part-3 animation, SHOW_ROW a dismissal (at once) and a summon
  fading in, HIDE_ROW a dismissal fading out, STOP_PROP the REST animation. Slot SLOT_DEPENDENT of SHOW_ROW / HIDE_ROW
  fades a summon of the body's rig instead (the definition's 'dependent' {kind: summon}; its mask rows only say whether
  it may be drawn: summons8.split_masks): the fade's row takes the place of the plain summon.
* ONE ANIMATOR. A fighter has one part-3 animator, so a move starting two clips (or starting one while a clip of the
  move before is still shown: its HIDE_ROW names a kind it does not start) plays them as one animation.
* PLACE. Clips and body are authored in one scene, whose origin is where the body clip's Top is at its frame 0 (the dog
  meets the opponent where the sword left him, though Clive has stepped a metre by then). A bone at that origin hangs
  under HARA_ROT1: the definition's weapon with 'ground' (posed by its 'channels' pair, only in the clips of the moves
  showing a prefab: tekken8/anim.py pair_values). Under it each prefab has a still weapon (summon: collapsed while it is
  off, with all under it) at 'place', the middle of its bones where the clips show it: the fade scales the prefab about
  that point. All are numbered in order, ground < still weapons < OPT_FIRST: the game makes its inverse binds in number
  order, and a bone numbered before its parent gets a zero one (seen in a fight: the palette's entries were all zero,
  with all below them, while their worlds were right), which is also why ground has channels and not a number 800 + k.
* A WING. Another of his summons is a mesh on the body's rig (Bahamut's wings: 'body_clips') that no body clip moves:
  BODY_CLIP_PROP names a clip of bank category 3 (the fighter's own list 3, by index) with the mesh's joints, as long as
  the move's body clip and played in step with it (shown from the frame the clip stops scaling them from 0). BodyRig:
  its bones hang under a still weapon under MUNE2_jnt, in the joints' frames as weapons are: a root's local is O^T M (O the
  calibration offset, M the bone in Spine2's frame), and they take the same part-3 animations. A stance's loops have
  no row but go on showing the mesh: the definition's 'body_clip_moves' names their clip.
* HIT POINTS. HOLD_CLIP_PROP names a clip of the same list with only the holding joints (R_Have, L_Have), which there
  move in the scene's space beside the prefab (the dog's lunge: 8 m along with its head): boxes on those joints hit from
  that path while the move plays (scene_spots: spots convert/summons8.py hands to tekken8/anim.py pair_values). TTT2's
  lines have no radius: a box with one becomes the line across it, sideways, which the path sweeps forward.
  MISSILE_CLIP_PROP names such a clip too, with no prefab: a missile, the joints flying straight ahead metres out (Clive's
  Wings of Light 1 and 2); the same spots, and convert/missiles8.py shows what flies.
* HELD SCENES. The ground follows him (a definition's ground weapon 'held': False: Tekken 8 plays most clips where he
  is). A throw's scene stays where it began: its victim's clip is in it, and the attacker's clip takes him metres
  away (Clive's 1+3 cuts him 4.4 m back while Torgal bites the victim 1.6 m ahead of the origin; followed, the dog
  played 4.4 m short of the victim). The definition's PREFABS 'held_moves' names them: their clips pose the ground
  as held (tekken8/anim.py pair_values: his travel taken back), the runtime's ground left as it is.
* SCENE CUTS. Tekken 8 cuts its throw scenes with the camera, and a clip may jump there: Clive's 1+3 moves him 2.26 m
  back in one frame (66) as the camera cuts to Torgal. TTT2 has no cut: he teleported. The definition's PREFABS
  'scene_cuts' names such moves with the cut's frame, the victim's move and the frame his push away from the
  attacker starts (scene_cuts()): the attacker's clip has the jump taken back from the cut on (his Top's path,
  tekken8/anim.py channels' shift), the victim's clip the same, grown with his push (he is thrown that much further,
  so the gap after the cut is Tekken 8's), and the held scene stands where the cut leaves it all through the move
  (pair_values poses it from the clip's own path, moved by the jump): Torgal meets them as in Tekken 8.
* TWISTS. A throw may leave the victim on his back, head toward the thrower: TTT2's downs lie feet toward the
  fighter's facing, so he faces away, and its get-up from there sits him up turned away and spins him round (Clive's
  1+3; TTT2's own throws leave him feet toward the thrower, and he rises straight). The definition's PREFABS
  'twists' {victim move: (first frame, last frame, degrees[, flat])} turn him that much about his hips over those
  frames, in the air (twists(); convert/retarget.py twist: his turn grows, smoothly, and stays, for his facing; the
  game takes the turn into his facing and draws the body from it, HARA_ROT1 turning the body): he lands the other way
  round. A victim who somersaults gives the frame he lies by (flat): the body then turns in his hips' own frame, so
  his spin carries on (a turn about the vertical reversed it, Clive's 1+3), into a turn about the vertical as he lies.
  The hand-off into the down state (convert/moveset.py handoffs8) keeps his body and the facing it lies in
  (retarget.handoff keep_body, as every clip's of a definition with MOVESET 'keep_body_handoffs') where the default
  sweeps the turn to the down move's own, which would spin him back on the ground.
* LEAD-INS. Such a cut also hides where a creature comes from: Torgal is parked under the floor (his clip's scale
  0.001) until the cut, then leaps 2 m up at the victim; TTT2 showed him out of nowhere. A model's 'lead_ins' {kind:
  {clip: lead}} gives that clip a way in from another of its clips (lead_in()): the donor's run-up (lead 'run': its
  frames, the last one in the air), turned and moved so that it leaves the ground along the way the creature goes at
  the cut, then a flight of lead 'flight' frames: the mover (the bone that carries it) on an arc that meets the cut's
  place, speed and height under one pull down, its pose from the donor's as it leaves the ground into the cut's (the
  donor's own flight may be another: Torgal's pounce somersaults).
* BONES. Each prefab keeps the definition's count of bones: reduced() merges the weighted bone whose vertices move
  least if it goes into its nearest kept ancestor, over its clips, until the count is reached.
* SPACE. Prefab space (UE: x left, y forward, z up, cm) -> TTT2's (x, y up, z forward, mm): P swaps y and z; a bone
  under a kept bone has the local P L P as Miary Zo's snakes.

Written for this project from the files themselves (no third-party code).
"""
import collections

import numpy as np

from ..tekken7 import mesh as t7mesh
from ..ttt2 import bone
from . import snakes8, tiger

START_PROP, STOP_PROP = 0x83aa, 0x83ab
SHOW_ROW, HIDE_ROW = 0x83ef, 0x83f0
BODY_CLIP_PROP, HOLD_CLIP_PROP = 0x8683, 0x8685     # value: index in the bank's list 3
MISSILE_CLIP_PROP = 0x8684                          # (the same: a missile's path, HIT POINTS)
BODY_CLIP = '*body'                         # the kind of a model moved by BODY_CLIP_PROP
LIST3 = 3
THICK = 100                                 # mm: a box's radius from here on is a line across (HIT POINTS)
SUMMON, DISMISS = 0x8317, 0x8318            # (summons8's)
REST = snakes8.REST
AT_START = snakes8.AT_START
RELATIVE = 0x8000                           # a row's frame from here on: frames after the move's entry
KEEP_FRAMES = 0x400                         # cancel extradata bit: the next move goes on from the frames (tagcombo.py)
SLOT_DEPENDENT = 3
OPT_FIRST = tiger.OPT_FIRST
NAME_LENGTH = tiger.NAME_LENGTH
LEAD = snakes8.LEAD
P = snakes8.P
A = snakes8.D @ P                           # snakes8.ttt2_locals' offset that reads a root in TTT2's ground frame
GROUP, LIST_END = 0x800B, 0x8000
PROP_END = lambda r: r['id'] == 0 and r['frame'] == 0     # noqa: E731
SAMPLE_VERTICES, SAMPLE_FRAMES = 3000, 240  # what reduced() measures with
PARKED_MM = 20000.0                         # a prefab's bone further than this from the scene's origin is not out
CARD_VERTICES = 8                           # vertices a separate piece is given room for


def spec(d):
    return getattr(d, 'PREFABS', None)


def models(d):
    s = spec(d)
    return s['models'] if s else []


def vertices(d):
    """The vertices the prefabs' meshes are decimated to (0 without them)."""
    return sum(int(m['vertices']) for m in models(d))


def bone_count(d):
    return sum(int(m['bones']) for m in models(d))


def with_channels(weapons, ini_weapons):
    """character.ini weapons (summonfade.ramps') with the channels of a weapon asking for them (its definition's
    'channels': a bone numbered below 800, posed by that pair), the others as they are; the ground (its 'ground')
    anchored too: the runtime holds it in the world where each move's first frame puts it (roster.cpp anchor_weapon:
    the title stops him short of the clip's travel where Tekken 8 lets him overlap the opponent, and the scene went
    back with him), unless it says 'held': False (its pair puts it where his Top is each frame, not at the scene's
    origin: tekken8/anim.py pair_values; Clive's: Tekken 8 plays his creatures' clips at him); with a held ground, the
    root points (summons8.weapons' 'root': the boxes at the ground origin and the summons' paths, all the scene's)
    anchored 2: they hit where the held ground takes the scene, where the summon is drawn (roster.cpp pose_weapons)."""
    from . import weapons as weapons_mod
    of_number = {w['number'] - weapons_mod.OPT_FIRST: (w['channels'],) + ((1,) if w.get('ground') and w.get('held', True)
                                                                         else ()) for w in weapons
                 if w.get('number') is not None and w.get('channels') is not None}
    if any(w.get('ground') and w.get('held', True) for w in weapons):
        of_number.update({w['pair']: (None, 2) for w in weapons if w.get('root') is not None and w.get('pair') is not None})
    return [tuple(w) + of_number[w[0]] if w[0] in of_number else w for w in ini_weapons]


def spring_numbers(d, skel):
    """The OPT numbers of the prefabs' bones and still weapons below 800 ([] without them): each gets a still spring
    entry (a bone in the OPT list without one swings under gravity)."""
    if not spec(d):
        return []
    own = {w['number'] for w in getattr(d, 'WEAPONS', []) if w.get('number') is not None and w.get('prefab')}
    n = bone_count(d)
    return [o for o in skel['opt'] if OPT_FIRST <= o < OPT_FIRST + n or o in own]


# ------------------------------------------------------------------------------------------------ rigs
def table_of(d, kind):
    return spec(d)['tables'] % kind


def reduced(names, parents, worlds, binds, geo, target, log=None):
    """The weighted bones kept of a mesh's: [bone] (sorted), target of them where it can be. worlds (frames, bones, 4,
    4): the mesh bones' worlds through its clips; binds (bones, 4, 4); geo: its streams (mesh.geometry). -> (kept,
    {bone: [(place in kept, 1.0)]} for snakes8.remap_weights, worst vertex displacement of the last merge (cm))."""
    joints, weights = np.asarray(geo['joints'], np.int64), np.asarray(geo['weights'], np.float64)
    pos = np.asarray(geo['positions'], np.float64)
    step = max(len(pos) // SAMPLE_VERTICES, 1)
    joints, weights, pos = joints[::step], weights[::step], pos[::step]
    n = len(names)
    W = np.zeros((len(pos), n))
    for c in range(joints.shape[1]):
        np.add.at(W, (np.arange(len(pos)), joints[:, c]), weights[:, c])
    S = worlds @ np.linalg.inv(binds)           # (frames, bones, 4, 4)
    keep = {b for b in range(n) if W[:, b].sum() > 0}

    def up(b):
        p = parents[b]
        while p >= 0 and p not in keep:
            p = parents[p]
        return p

    def cost(b):
        a = up(b)
        if a < 0:
            return np.inf
        v = np.flatnonzero(W[:, b] > 0.01)
        if not len(v):
            return 0.0
        d = (S[:, b, :3, :3] - S[:, a, :3, :3]) @ pos[v].T + (S[:, b, :3, 3] - S[:, a, :3, 3])[:, :, None]
        return float((np.linalg.norm(d, axis=1) * W[v, b]).max())
    costs = {b: cost(b) for b in keep}
    worst = 0.0
    while len(keep) > target:
        b = min(keep, key=lambda x: costs[x])
        if not np.isfinite(costs[b]):
            break
        a = up(b)
        worst = max(worst, costs[b])
        W[:, a] += W[:, b]
        W[:, b] = 0.0
        keep.discard(b)
        del costs[b]
        for c in keep:                          # (the bones now under a, and a itself)
            if c == a or up(c) == a:
                costs[c] = cost(c)
    kept = sorted(keep)
    at = {b: k for k, b in enumerate(kept)}
    table = {}
    for b in range(n):
        p = b
        while p >= 0 and p not in at:
            p = parents[p]
        table[b] = [(at[p], 1.0)] if p >= 0 else []
    return kept, table, worst


def _geometry(mesh, spec_, log=print):
    """The mesh's geometry; its large sheets made again as grids when the definition's model asks ('remesh': step_cm,
    min_area_m2, one_side, mirror; convert/remesh8.py)."""
    geo = mesh.geometry(0)
    r = spec_.get('remesh')
    if r:
        from . import remesh8
        names = [mesh.material_name(s.material_index) for s in mesh.lods[0].sections]
        geo = remesh8.remesh(geo, names, float(r['step_cm']), float(r['min_area_m2']), bool(r.get('one_side', True)),
                             log=log, mirror=bool(r.get('mirror', False)))
    return geo


class Rig:
    """One prefab: its mesh, skeleton, the bones kept and its clips' TTT2 locals. spec: the definition's model entry."""

    def __init__(self, store, d, spec_, log=print):
        from ..tekken8 import mesh as t8mesh, ue5anim
        self.store, self.d, self.spec, self.log = store, d, spec_, log
        self.name = spec_['name']
        self.mesh = t8mesh.SkeletalMesh(store, spec_['mesh'])
        self.skeleton = ue5anim.read_skeleton(store, str(self.mesh.props['Skeleton']).split('.')[0])
        self.names = list(self.mesh.skeleton['names'])
        self.parents = list(self.mesh.skeleton['parents'])
        self.tables = {kind: snakes8.clip_paths(store, table_of(d, kind)) for kind in spec_['kinds']}
        self._clips = {}
        sk_index = {n: i for i, n in enumerate(self.skeleton['names'])}
        self.to_sk = [sk_index[n] for n in self.names]
        G = t7mesh.global_matrices(np.asarray(self.mesh.skeleton['pose'], np.float64), self.parents)
        self.binds = G
        self.geo = _geometry(self.mesh, spec_, log)
        worlds = self._worlds()
        self.kept, self.table, worst = reduced(self.names, self.parents, worlds, G, self.geo, int(spec_['bones']))
        self.keep_sk = [self.to_sk[b] for b in self.kept]
        self.up = snakes8.kept_parents(self.parents, self.kept)
        log('  prefab %s: %d bones kept of %d (%d weighted), the last merge moves a vertex %.1f cm at most' % (
            self.name, len(self.kept), len(self.names), sum(1 for b in self.table if self.table[b]), worst))

    def _world_of(self, kind, clip):
        from ..tekken8 import ue5anim
        c = ue5anim.read_clip(self.store, self.tables[kind][clip])
        pose = ue5anim.local_poses(c, self.skeleton)
        return snakes8.world_poses(pose, self.skeleton['parents'])

    def _worlds(self):
        """The mesh bones' worlds through (a sample of) every clip of its kinds."""
        out = []
        for kind, paths in self.tables.items():
            for clip, path in enumerate(paths):
                if path:
                    out.append(self._world_of(kind, clip))
        G = np.concatenate(out, 0)
        G = G[::max(len(G) // SAMPLE_FRAMES, 1)]
        return G[:, self.to_sk]

    def place(self):
        """The middle (TTT2 ground space, mm) of the prefab's kept bones over the frames its clips show it (a clip parks
        the creature hundreds of metres away while it is not out: Torgal under the floor before he runs in)."""
        at = []
        for kind, paths in self.tables.items():
            for clip, path in enumerate(paths):
                if path:
                    G = self._world_of(kind, clip)[:, self.keep_sk][:, :, :3, 3].reshape(-1, 3) * snakes8.CM
                    at.append(G[np.max(np.abs(G), 1) < PARKED_MM])
        at = np.concatenate(at, 0)
        return at.mean(0)[[0, 2, 1]] if len(at) else np.zeros(3)

    def locals_of(self, kind, clip, place):
        """(frames, kept, 4, 4) TTT2 locals of a clip: roots relative to the still weapon at `place` (cached); with
        its way in when the model's 'lead_ins' gives one (LEAD-INS)."""
        key = kind, clip
        if key not in self._clips:
            W = self._world_of(kind, clip)
            lead = self.spec.get('lead_ins', {}).get(kind, {}).get(clip)
            if lead:
                W = lead_in(W, self._world_of(kind, lead['donor']), self.skeleton['parents'],
                            list(self.skeleton['names']).index(lead['mover']), lead['run'], lead['flight'])
                self.log('  prefab %s: clip %d led in by clip %d\'s run-up (frames %d-%d) and a %d-frame flight' % (
                    self.name, clip, lead['donor'], lead['run'][0], lead['run'][1], lead['flight']))
            L = snakes8.ttt2_locals(W, self.skeleton['parents'], self.keep_sk, A)
            for k, u in enumerate(self.up):
                if u < 0:
                    L[:, k, :3, 3] -= place
            self._clips[key] = L
        return self._clips[key]

    def bind_locals(self, place):
        L = snakes8.ttt2_locals(self.binds, self.parents, self.kept, A)
        for k, u in enumerate(self.up):
            if u < 0:
                L[k, :3, 3] -= place
        return L


class HandRig(Rig):
    """A prefab Tekken 8 attaches to one of his joints (the serpent: its centre is bound at L_Hand, and its clips leave
    the centre where the actor is, its head still all through them): its clips play in that joint's frame, so its
    bones hang under a still weapon at the TTT2 joint that joint drives (the model's 'under'), as Miary Zo's snakes
    do (convert/snakes8.py PLACE): O the TTT2 joint's calibration offset."""
    O = None

    def place(self):
        return None                      # (the still weapon sits at its joint)

    def offset(self, skel):
        if self.O is None:
            from ..tekken8 import anim
            from . import retarget
            cal = retarget.Calibration(anim.load_skeleton(self.store, self.d.TEKKEN8_CODE), anim.LANDMARKS, anim.DRIVERS,
                                       retarget.ttt2_skeleton(skel))
            self.O = np.asarray(cal.offsets[self.spec['under']], np.float64)
        return self.O

    def locals_of(self, kind, clip, place):
        key = kind, clip
        if key not in self._clips:
            if self.O is None:
                raise ValueError('prefab %s: its joint\'s offset is not known before its model' % self.name)
            self._clips[key] = snakes8.ttt2_locals(self._world_of(kind, clip), self.skeleton['parents'], self.keep_sk,
                                                   self.O)
        return self._clips[key]

    def bind_locals(self, place):
        return snakes8.ttt2_locals(self.binds, self.parents, self.kept, self.O)

    def streams(self, W, skel):
        """The mesh's streams in the model's bind (W: the still weapon's world)."""
        return snakes8.mesh_streams(self.geo, self.kept, self.table, W, self.offset(skel))


class BodyRig:
    """A mesh on the body's rig moved by list-3 clips (A WING above). banks: the fighter's own animation bank."""

    def __init__(self, store, d, spec_, log=print):
        from ..tekken8 import mesh as t8mesh
        self.store, self.d, self.spec, self.log = store, d, spec_, log
        self.name = spec_['name']
        self.mesh = t8mesh.SkeletalMesh(store, spec_['mesh'])
        self.names = list(self.mesh.skeleton['names'])
        self.parents = list(self.mesh.skeleton['parents'])
        self.geo = _geometry(self.mesh, spec_, log)
        U = t7mesh.global_matrices(np.asarray(self.mesh.skeleton['pose'], np.float64), self.parents)
        top = self.names.index(spec_['top'])
        self.S_top, self.P_top = P @ U[top, :3, :3] @ snakes8.D, P @ U[top, :3, 3]
        M = np.repeat(np.eye(4)[None], len(self.names), 0)
        self.under = set()
        for b in range(len(self.names)):
            p = b
            while p >= 0 and p != top:
                p = self.parents[p]
            if p == top and b != top:
                self.under.add(b)
                M[b, :3, :3] = self.S_top.T @ P @ U[b, :3, :3] @ snakes8.D
                M[b, :3, 3] = self.S_top.T @ (P @ U[b, :3, 3] - self.P_top)
        self.bind = M
        self.locals_bind = {}
        for b in self.under:
            q = self.parents[b]
            self.locals_bind[b] = np.linalg.inv(M[q]) @ M[b] if q in self.under else M[b]
        self.top = top
        self._clips = {}
        self.O = None
        keys = list(self.clip_indices())
        Ws = [self._world(self._local(i)) for i in keys]
        G = np.concatenate(Ws, 0)
        G = G[::max(len(G) // SAMPLE_FRAMES, 1)]
        geo = dict(self.geo, positions=(np.asarray(self.geo['positions'], np.float64) @ P - self.P_top) @ self.S_top)
        self.kept, self.table, worst = reduced(self.names, self.parents, G, M, geo, int(spec_['bones']))
        self.up = snakes8.kept_parents(self.parents, self.kept)
        log('  prefab %s: %d bones kept of %d, the last merge moves a vertex %.1f cm at most' % (
            self.name, len(self.kept), len(self.names), worst))

    def _bank(self):
        from ..tekken8 import anmbin
        if not hasattr(self, '_bank_'):
            self._bank_ = anmbin.Bank(self.spec['bank']())
        return self._bank_

    def clip_indices(self):
        """The indices in list 3 of the clips moving this mesh's bones."""
        from ..tekken8 import panm
        bank = self._bank()
        out = []
        for n, key in enumerate(bank.key_lists[LIST3]):
            blob = bank.blob(LIST3, key)
            if blob is None:
                continue
            J = panm.Animation(blob).joints()
            if any(self.names[b] in J for b in self.under):
                out.append(n)
        return out

    def _local(self, index):
        """(frames, bones, 4, 4) the bones' locals (cm) through clip `index` of list 3, the others' their bind's."""
        from ..tekken8 import anim, panm
        from ..ttt2 import animation
        bank = self._bank()
        a = panm.Animation(bank.blob(LIST3, bank.key_lists[LIST3][index]))
        J = a.joints()
        L = np.repeat(np.eye(4)[None, None], a.frames, 0).repeat(len(self.names), 1)
        for b in self.under:
            L[:, b] = self.locals_bind[b]
            j = J.get(self.names[b])
            if j is None:
                continue
            if j.stored_rotation:
                L[:, b, :3, :3] = animation.quaternion_to_matrix(anim._quaternions(j.rotation))
            if j.stored_translation:
                L[:, b, :3, 3] = j.translation
            if j.scale is not None:
                L[:, b, :3, :3] = L[:, b, :3, :3] * np.asarray(j.scale, np.float64)[:, None, :]
        return L

    def _world(self, L):
        G = L.copy()
        for b in sorted(self.under):
            q = self.parents[b]
            if q in self.under:
                G[:, b] = G[:, q] @ L[:, b]
        return G

    def offset(self, skel):
        """The calibration offset of the TTT2 bone the still weapon hangs under."""
        if self.O is None:
            from ..tekken8 import anim
            from . import retarget
            cal = retarget.Calibration(anim.load_skeleton(self.store, self.d.TEKKEN8_CODE), anim.LANDMARKS, anim.DRIVERS,
                                       retarget.ttt2_skeleton(skel))
            self.O = np.asarray(cal.offsets[self.spec['under']], np.float64)
        return self.O

    def _ttt2(self, L, single=False):
        """TTT2 locals (.., kept, 4, 4) (mm) of the kept bones from locals L (.., bones, 4, 4) (cm)."""
        shape = L.shape[:-3]
        out = np.zeros(shape + (len(self.kept), 4, 4))
        out[..., 3, 3] = 1.0
        for k, b in enumerate(self.kept):
            stop = self.kept[self.up[k]] if self.up[k] >= 0 else self.top
            M = L[..., b, :, :]
            q = self.parents[b]
            while q != stop:
                M = L[..., q, :, :] @ M
                q = self.parents[q]
            if self.up[k] < 0:
                out[..., k, :3, :3] = self.O.T @ M[..., :3, :3]
                out[..., k, :3, 3] = (M[..., :3, 3] @ self.O) * snakes8.CM
            else:
                out[..., k, :3, :3] = M[..., :3, :3]
                out[..., k, :3, 3] = M[..., :3, 3] * snakes8.CM
        return out

    def bind_locals(self, place):
        L = np.repeat(np.eye(4)[None], len(self.names), 0)
        for b in self.under:
            L[b] = self.locals_bind[b]
        return self._ttt2(L)

    def locals_of(self, kind, clip, place):
        if clip not in self._clips:
            self._clips[clip] = self._ttt2(self._local(clip))
        return self._clips[clip]

    def streams(self, W, skel):
        """The mesh's streams in the model's bind (W: the still weapon's world)."""
        self.offset(skel)
        turn = self.O.T @ self.S_top.T @ P
        place = W.copy()
        place[:3, 3] = W[:3, 3] - W[:3, :3] @ (self.O.T @ self.S_top.T @ self.P_top) * snakes8.CM
        A_ = snakes8.D @ turn.T
        return snakes8.mesh_streams(self.geo, self.kept, self.table, place, A_)


_rigs = {}
_bank_paths = {}


def rigs(store, d, log=print):
    """[Rig] of the definition's models (kept for the import's later steps)."""
    out = []
    for m in models(d):
        key = id(store), m['name'], m['mesh'], m['bones']
        if key not in _rigs:
            if m.get('body_clips'):
                _rigs[key] = BodyRig(store, d, dict(m, bank=lambda: _bank_paths[id(store)]), log)
            elif m.get('under'):
                _rigs[key] = HandRig(store, d, m, log)
            else:
                _rigs[key] = Rig(store, d, m, log)
        out.append(_rigs[key])
    return out


def use_bank(store, path):
    """The fighter's own animation bank (a file the import has, for BodyRig and the hold clips)."""
    _bank_paths[id(store)] = path


def placed(store, d, weapons, log=print):
    """The weapons with each prefab's still weapon's 'place' (Rig.place)."""
    of = {m['weapon']: r for m, r in zip(models(d), rigs(store, d, log))}
    out = []
    for w in weapons:
        w = dict(w)
        if w['bone'] in of and hasattr(of[w['bone']], 'place') and of[w['bone']].place() is not None:
            w['place'] = of[w['bone']].place()
        out.append(w)
    return out


# ------------------------------------------------------------------------------------------------ colours
def bakes(d, eff):
    """Whether the definition's prefabs bake material `eff` (material.effective's) here."""
    sp = spec(d)
    return bool(sp) and (eff.get('base') or '').startswith(tuple(sp.get('bases', ())))


SHINE_SIZE = 64


def _rma(eff, textures, size):
    """(roughness, metallic, ambient occlusion) (H, W) of a summon's RMA map as its base pass takes them: roughness and
    metallic between the material's Min and Max (Tekken 8's pca shader: saturate(lerp(Min, Max, R / G))), or None."""
    t, s = eff['textures'], eff.get('scalars') or {}
    rma = t.get('RMA') or t.get('RMA_A')
    if not textures.exists(rma):
        return None
    r = textures.image(rma, size)[0][..., :3].astype(np.float32) / 255.0

    def between(name, x):
        lo, hi = float(s.get(name + '_Min', 0.0)), float(s.get(name + '_Max', 1.0))
        return np.clip(lo + (hi - lo) * x, 0.0, 1.0)
    return between('Roughness', r[..., 0]), between('Metallic', r[..., 1]), r[..., 2]


def shine(d, eff, textures):
    """A summon's shine as a costume's (tekken8/bake.py specular), from its map named 'RMA' here, its roughness and
    metal between the material's Min and Max (_rma); without one, none at all (the template's average is a polished
    suit's: the wings came out as chrome)."""
    from ..tekken8 import bake as bake8
    terms = _rma(eff, textures, SHINE_SIZE)
    if terms is None:
        out = np.zeros((4, 4, 4), np.uint8)
        out[..., 3] = int(255 * (bake8.GLOSS_TOP - bake8.GLOSS_SLOPE))
        return out
    rough, metal, ao = terms
    out = np.zeros(rough.shape + (4,), np.float32)
    out[..., 0] = bake8.SPECULAR * (1.0 - rough) * (0.5 + 0.5 * ao)
    out[..., 1] = bake8.REFLECTION * metal * (1.0 - rough)
    out[..., 3] = bake8.GLOSS_TOP - bake8.GLOSS_SLOPE * rough
    out = (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
    from . import lace8
    lace = lace8.card(eff.get('name'))
    return out if lace is None else lace.resample(out)      # (laid out as a lace model's pictures: convert/lace8.py)


def _flow(s, sw, tex, samples=65536):
    """The mean of a pca material's scrolling glow: min((F0 x I0 + F1 x I1)^FlowTile_Power, 1) x FlowTile_Intensity
    (F the tiles, scrolling apart: texels drawn at random from each, a fixed seed)."""
    rng = np.random.default_rng(0)
    total = np.zeros(samples, np.float32)
    for n in range(FLOWS):
        tile = tex('Flow%d_Tile' % n) if n == 0 or sw.get('Use EmisiveFlow%d' % n) else None
        if tile is not None:
            texels = tile[..., 0].ravel()
            total += texels[rng.integers(0, len(texels), samples)] * float(s.get('Flow%d_EmissiveIntensity' % n, 0.0))
    share = np.minimum(np.power(total, float(s.get('FlowTile_Power', 1.0))), 1.0)
    return float(share.mean()) * float(s.get('FlowTile_Intensity', 0.0))


STILL_SUPERSAMPLE = 4   # a still flow's glow drawn this many times finer, then averaged (bake)
FLOWS = 4               # the pca material's scrolling tiles (Flow0_Tile .. Flow3_Tile; 1 .. 3 each by its switch)


def _still_flow(s, sw, tex, uv):
    """One still frame of _flow's glow (h, w) at the layout points uv (h, w, 2) the tiles go along: each tile at
    uv x (TileScale_U, TileScale_V) + (TileOffset_U, TileOffset_V) (its scrolling at time 0)."""
    from . import uvmap8
    total = np.zeros(uv.shape[:2], np.float32)
    for n in range(FLOWS):
        tile = tex('Flow%d_Tile' % n) if n == 0 or sw.get('Use EmisiveFlow%d' % n) else None
        if tile is None:
            continue
        g = lambda k, default: float(s.get('Flow%d_%s' % (n, k), default))
        at = uv * np.array([g('TileScale_U', 1.0), g('TileScale_V', 1.0)]) + np.array([g('TileOffset_U', 0.0),
                                                                                      g('TileOffset_V', 0.0)])
        total += uvmap8.sample(tile[..., :1], at)[..., 0] * g('EmissiveIntensity', 0.0)
    share = np.minimum(np.power(np.maximum(total, 0.0), float(s.get('FlowTile_Power', 1.0))), 1.0)
    return (share * float(s.get('FlowTile_Intensity', 0.0))).astype(np.float32)


def bake(d, eff, textures, name=None):
    """(linear rgb, alpha or None) of a summon's material, at most the definition's 'texture_size': its colour (a colour
    laid out along UV1, which the converted mesh does not keep: its mean) times its mask's two colours and its tint,
    plus its steady glow through Tekken 8's tone curve (tekken8/bake.py's notes); the mask's holes as alpha (and, for
    material `name` of a remeshed model, its source layout: remesh8.coverage)."""
    from ..tekken8 import bake as bake8
    t, v, s, sw = eff['textures'], eff['vectors'], eff['scalars'], eff.get('switches') or {}
    size = int(spec(d).get('texture_size', 256))
    from . import lace8
    lace = lace8.card(name)
    if lace is not None:                # (a lace model's pictures sample this bake: convert/lace8.py)
        size = lace.source_size

    def tex(slot):
        return textures.linear(t[slot], size)[0] if textures.exists(t.get(slot)) else None

    def colour(name, default=(0.0, 0.0, 0.0)):
        c = v.get(name)
        return np.array(default, np.float32) if c is None else bake8._col(c)
    base = next((x for x in (tex('Basecolor'), tex('BaseColor'), tex('BaseColor_A')) if x is not None), None)
    mask = tex('Basecolor_Mask')
    if base is None:                # (a surface with no colour of its own: the definition's, from Tekken 8's clips)
        flat = spec(d).get('flat_colours', {}).get(eff.get('base'))
        return (None, None) if flat is None else (np.full((4, 4, 3), flat, np.float32), None)
    far = bool(sw.get('Use BaseColor_UV1'))
    shape = (mask if far and mask is not None else base).shape[:2]
    from . import uvmap8
    uv1 = uvmap8.uv1_of(name, shape) if name is not None else None

    def laid(x, along_uv1, at=shape):
        """Texture x at the texels of a bake of shape `at`: x itself (resized), or, laid along UV1, sampled through
        the model's map (uvmap8), without one its mean."""
        if not along_uv1:
            return bake8._resize(x, at)
        far_uv = uvmap8.uv1_of(name, at) if name is not None else None
        if far_uv is not None:
            return uvmap8.sample(x, far_uv).astype(np.float32)
        return np.broadcast_to(x.reshape(-1, x.shape[-1]).mean(0), tuple(at) + (x.shape[-1],)).astype(np.float32)
    rgb = laid(base, True) if far else base
    if sw.get('Use BaseColorMask') and mask is not None:
        m = bake8._resize(mask, shape)[..., 1:2]
        rgb = rgb * (colour('BasecolorMask_MinColor', (1, 1, 1)) * (1 - m) + colour('BasecolorMask_MaxColor', (1, 1, 1)) * m)
    if sw.get('Use BaseColor Tint'):
        hsv = colour('Base_Color_Tint_HSV')
        grey = rgb.mean(-1, keepdims=True)
        rgb = np.clip(grey + (rgb - grey) * (1 + hsv[1]), 0, None) * max(1 + float(hsv[2]), 0.0)
    seen = spec(d).get('seen_colours', {}).get(name)
    if seen is not None:            # (the colour Tekken 8's clips show it in: its texture's detail around that colour)
        rgb = seen_colour(rgb, seen)
    terms = _rma(eff, textures, max(shape))
    # (a metal's own colour is what it reflects: lit, only its non-metal share shows; but for the definition's
    # 'metal_lit' materials, rough metals under an open sky in Tekken 8, that blurred reflection is as bright as the
    # colour itself, and TTT2 has no such sky to give it back: their colour stays whole)
    if terms is not None and name not in spec(d).get('metal_lit', ()):
        rgb = rgb * (1.0 - bake8._resize(terms[1], shape))[..., None]
    # the steady glow, Tekken 8's pca base pass (read from its compiled shader):
    #     E = (M x M_UV1)^EmissiveMask_Power x C x BaseEmissive_Intensity x (flow + AddEmisive_Intensity) x Emissive_Scale
    # M the mask ('Use EmissiveMask'; 1 without), M_UV1 the second mask along UV1 ('Use AddEmissiveUV1map'), C the mask's
    # colour texture ('Use EmissiveMaskColor', along UV1 with 'Use EmissiveMaskColor_UV1') else BaseEmissive_Color;
    # flow the scrolling tiles (_flow: their mean). A definition's 'still_flow' materials take one still frame of the
    # tiles instead, drawn STILL_SUPERSAMPLE times finer and averaged after the tone curve (their lines are finer
    # than the summon's texels)
    still = name in spec(d).get('still_flow', ())
    # (a definition's 'glow_gain': that glow's exposure times this, before the tone curve: summons whose Tekken 8 clips
    # show their glow ramp brighter than the bake makes it, the phoenix's feathers gold-white along their shafts)
    gain = float(spec(d).get('glow_gain', {}).get(name, 1.0))

    def glow(at, flows=None):
        """The glow at a bake of shape `at`: flows None the material's own ('still_flow' or the mean), 'still' one still
        frame of the tiles, 'none' without them."""
        M = np.ones(tuple(at) + (1,), np.float32)
        lit = False
        if sw.get('Use EmissiveMask') and tex('EmissiveMask') is not None:
            M, lit = M * bake8._resize(tex('EmissiveMask'), at)[..., :1], True
        if sw.get('Use AddEmissiveUV1map') and tex('EmissiveMask_UV1') is not None:
            M, lit = M * laid(tex('EmissiveMask_UV1'), True, at)[..., :1], True
        C = colour('BaseEmissive_Color')
        if sw.get('Use EmissiveMaskColor') and tex('EmissiveMaskColor') is not None:
            C, lit = laid(tex('EmissiveMaskColor'), bool(sw.get('Use EmissiveMaskColor_UV1')), at), True
        if not lit:
            return np.zeros(tuple(at) + (3,), np.float32)
        if flows == 'none':
            flow = 0.0
        elif flows == 'still' or (flows is None and still):
            far_uv = uvmap8.uv1_of(name, at) if name is not None and sw.get('Use Flowmap_UV1') else None
            flow = _still_flow(s, sw, tex, far_uv if far_uv is not None else uvmap8.texel_uv(at))[..., None]
        else:
            flow = _flow(s, sw, tex)
        E = np.power(np.clip(M, 0, 1), float(s.get('EmissiveMask_Power', 1.0))) * C * float(
            s.get('BaseEmissive_Intensity', 0.0)) * (flow + float(s.get('AddEmisive_Intensity', 0.0))) * float(
            s.get('Emissive_Scale', 1.0))
        return bake8.aces(E * bake8.GLOW_EXPOSURE * gain)
    if still:
        k = STILL_SUPERSAMPLE
        g = glow((shape[0] * k, shape[1] * k)).reshape(shape[0], k, shape[1], k, 3).mean((1, 3))
    else:
        g = glow(shape)
    # a definition's 'veins' materials, {name: (membrane gain, vein gain[, line gain[, frame gain[, (lo, hi)]]])}: their glow mask
    # covers the whole surface, but what glows in Tekken 8's frames is the metal (the RMA map's metal share: the bones),
    # the rest (rough, not metal: the membranes) shows pale with thin glowing lines over it; so the glow goes by the
    # metal share times the vein gain, the colour of the rest is lit by the membrane gain and the metal's own colour by
    # the frame gain (1 without), and over the rest go the lines of one still frame of the scrolling tiles (their glow
    # less the glow without them, drawn as 'still_flow' draws it) times the line gain (a look matched to Tekken 8's
    # frames, not its shader). The membrane and frame gains: one for all channels or (r, g, b); a fifth item (lo, hi)
    # makes the frame share of the colour a sharper one, the metal share from lo (none) to hi (all frame): a picture
    # of many small pieces averages its metal to about half, which would leave the frame membrane-coloured
    veins = spec(d).get('veins', {}).get(name)
    if veins is not None and terms is not None:
        metal = bake8._resize(terms[1], shape)[..., None]
        framed = metal
        if len(veins) > 4 and veins[4]:
            lo, hi = (float(x) for x in veins[4])
            framed = np.clip((metal - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
        rgb = rgb * (np.asarray(veins[0], np.float32) * (1.0 - framed)
                     + (np.asarray(veins[3], np.float32) if len(veins) > 3 else 1.0) * framed)
        g = g * metal * float(veins[1])
        if len(veins) > 2 and veins[2]:
            k = STILL_SUPERSAMPLE
            fine = (shape[0] * k, shape[1] * k)
            lines = (glow(fine, 'still') - glow(fine, 'none')).reshape(shape[0], k, shape[1], k, 3).mean((1, 3))
            g = g + np.clip(lines, 0.0, None) * (1.0 - metal) * float(veins[2])
    glows = spec(d).get('glowing', {})
    if name in glows:               # (drawn unlit and added to the picture: its glow, and that share of its colour)
        out = np.clip(rgb * float(glows[name]) + g, 0, 1)
    else:
        out = np.clip(rgb + g, 0, 1)
    alpha = None
    obd = next((x for x in (tex('OBD'), tex('OMA'), tex('OSM_Map')) if x is not None), None)
    if obd is not None:
        a = bake8._resize(obd[..., 0], shape)
        if sw.get('Use Dither Mask'):
            a = dithered(a, s)
        if float(a.min()) < 0.5:
            alpha = a
    if name is not None:
        from . import remesh8
        cov = remesh8.coverage(name, shape)
        if cov is not None:
            alpha = cov if alpha is None else alpha * cov
    see = spec(d).get('see_through', {}).get(name)
    if see is not None:             # (drawn blended over the picture: this share of it covers what is behind)
        alpha = np.full(shape, float(see), np.float32) if alpha is None else (alpha * float(see)).astype(np.float32)
    if name in spec(d).get('drawn_doubled', ()):    # (its template's shader draws twice its colour: baked at half)
        out = out * 0.5
    if lace is not None:
        return lace.texture(out, alpha)
    return out.astype(np.float32), alpha


def lace(name):
    """Whether material `name` is drawn as a lace model's pictures (convert/lace8.py)."""
    from . import lace8
    return lace8.card(name) is not None


def lace_kind(name):
    """The template kind a lace model's 'kind' gives material `name`, or None (its classification's)."""
    from . import lace8
    c = lace8.card(name)
    return None if c is None else c.kind


def lace_ref(name):
    """The alpha test reference of a dissolving lace material `name` (lace8.DISSOLVE_REF), or None."""
    from . import lace8
    c = lace8.card(name)
    return None if c is None or c.order is None else lace8.DISSOLVE_REF


RAMP_DISSOLVE = 16      # a weapon's ramp bit: its summon's pictures dissolve (lace8), not scaled (the runtime's)


def with_fades(d, ini_weapons):
    """character.ini weapons with RAMP_DISSOLVE on the root weapon of each lace model that dissolves (its scale ramp
    kept: a runtime without the bit scales it as before), and no ramp on the other models' root weapons: those are
    drawn whole wherever their clips put them while shown. Scaled, a creature grew out of its still weapon, the
    middle of all its clips (PLACE), and shrank back into it: Garuda's talons in d/b+1+2,1 came half a metre above
    and behind where Tekken 8 forms them, over a fade of 10 frames. Tekken 8 dissolves them in where they are."""
    from . import weapons as weapons_mod
    number = {w['bone']: w.get('number') for w in getattr(d, 'WEAPONS', []) if w.get('prefab')}
    roots = {number[m['weapon']] - weapons_mod.OPT_FIRST: bool((m.get('lace') or {}).get('dissolve'))
             for m in models(d) if number.get(m['weapon']) is not None}
    out = []
    for w in ini_weapons:
        if w[0] in roots and len(w) > 4 and w[4]:
            w = tuple(w[:4]) + ((w[4] | RAMP_DISSOLVE) if roots[w[0]] else 0,) + tuple(w[5:])
        out.append(w)
    return out


def seen_colour(rgb, seen):
    """rgb (h, w, 3) linear brought to the linear colour `seen` on average, its detail kept: each texel's brightness
    over the mean brightness times that colour (a definition's 'seen_colours': summons whose look in Tekken 8 comes
    from layers the bake leaves out, Leviathan's water over its flesh-coloured texture)."""
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    return np.clip((luma / max(float(luma.mean()), 1e-6))[..., None] * np.asarray(seen, np.float32), 0, 1)


def two_sided(name):
    """Whether material `name` lost a sheet behind it to a remesh (drawn from both sides then)."""
    from . import remesh8
    return remesh8.two_sided(name)


DITHER_SPAN = 5.0 / 6.0     # Tekken 8's dither offsets: (a noise texel + (x + 2y) mod 5) / 6, so 0 .. 5/6
TEMPLATE_CUT = 150 / 255.0  # the alpha-tested template's cut ('colour_alpha', Jun's)


def dithered(a, s):
    """A dithered summon's opacity (its depth pass: a^Opacity_Power + OpacityDitherBlend x (offset - 1/2) drawn above
    AlphaThreshold) as the share of its pixels drawn, scaled so that the template's cut keeps what Tekken 8 draws half
    the time or more (the plain mask cut there kept the feathers' cores only: sparse strands)."""
    a = np.power(np.clip(a, 0.0, 1.0), float(s.get('Opacity_Power', 1.0)))
    blend, cut = float(s.get('OpacityDitherBlend', 0.0)), float(s.get('AlphaThreshold', 1.0 / 3.0))
    drawn = (a > cut).astype(np.float32) if blend <= 0 else np.clip((DITHER_SPAN - 0.5 - (cut - a) / blend) / DITHER_SPAN, 0, 1)
    return np.clip(drawn * TEMPLATE_CUT / 0.5, 0.0, 1.0).astype(np.float32)


# ------------------------------------------------------------------------------------------------ model
def thinned(prims, pos, goal, log=print):
    """The prims without their smallest separate pieces (by surface), when they have more than goal / CARD_VERTICES:
    the decimation leaves a separate piece at least its corners (feathers and fur are thousands of cards)."""
    pos = np.asarray(pos, np.float64)
    _, point = np.unique(np.round(pos, 1), axis=0, return_inverse=True)  # (positions in mm: a seam's sides are one)
    point = np.asarray(point).reshape(-1)
    parent = np.arange(point.max() + 1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    all_tris = np.concatenate([q['tris'] for q in prims], 0)
    t = point[all_tris]
    for a, b, c in t:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[rc] = ra
    roots = np.array([find(x) for x in range(len(parent))])
    piece_of = roots[point]
    tri_piece = piece_of[all_tris[:, 0]]
    area = np.linalg.norm(np.cross(pos[all_tris[:, 1]] - pos[all_tris[:, 0]], pos[all_tris[:, 2]] - pos[all_tris[:, 0]]),
                          axis=1) * 0.5
    pieces, inverse = np.unique(tri_piece, return_inverse=True)
    sizes = np.bincount(inverse, area)
    room = max(goal // CARD_VERTICES, 1)
    if len(pieces) <= room:
        return prims
    kept = set(pieces[np.argsort(-sizes)[:room]].tolist())
    out = []
    for q in prims:
        mine = np.isin(piece_of[q['tris'][:, 0]], list(kept))
        if mine.any():
            out.append(dict(q, tris=q['tris'][mine]))
    log('  prefab: %d of %d separate pieces kept (%.0f%% of the surface)' % (
        len(kept), len(pieces), 100.0 * sizes[np.isin(pieces, list(kept))].sum() / max(sizes.sum(), 1e-9)))
    return out


def free_normals(prims, streams):
    """The prims with one normal per point (a hard edge's two normals are two vertices the decimation has to keep)."""
    pos = np.asarray(streams['pos'], np.float64)
    _, point = np.unique(np.round(pos, 1), axis=0, return_inverse=True)
    point = np.asarray(point).reshape(-1)
    n = np.zeros((point.max() + 1, 3))
    np.add.at(n, point, np.asarray(streams['nrm'], np.float64))
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    nrm = n[point].astype(np.asarray(streams['nrm']).dtype)
    return [dict(q, nrm=nrm) for q in prims]


def _append(skel, names, up, locals_, parent, number):
    """The skeleton with bones cha:OPT<number + k>_<name>: roots under `parent`, others under their kept parents.
    -> (skeleton, first index)."""
    first = len(skel['names'])
    s = dict(skel)
    for key in ('names', 'parent', 'opt'):
        s[key] = list(skel[key])
    s['names_raw'] = None
    ts, rs, ss = list(skel['t']), list(skel['r']), list(skel['s'])
    for k, name in enumerate(names):
        t, r, _ = snakes8.decompose(locals_[k])
        s['names'].append(('cha:OPT%d_%s' % (number + k, name))[:NAME_LENGTH])
        s['parent'].append(parent if up[k] < 0 else first + up[k])
        s['opt'].append(number + k)
        ts.append(t)
        rs.append(r)
        ss.append(np.ones(3))
    s['t'], s['r'], s['s'] = np.array(ts, np.float32), np.array(rs, np.float32), np.array(ss, np.float32)
    return s, first


def model(source, d, skel, log=print):
    """The prefabs as extra bones of skel (with its weapons) and their meshes. -> (skeleton, [(tag, mesh path, first
    bone index, bones)], prims)."""
    from . import decimate, weapons as weapons_mod
    left = {name for name, kind in getattr(d, 'MATERIALS', {}).items() if kind is None}
    number = OPT_FIRST
    parts, prims = [], []
    worlds = bone.world_matrices(skel)
    for rig in rigs(source.store, d, log):
        tag = rig.name
        host = weapons_mod.parent_index(skel, rig.spec['weapon'])
        place = worlds[host][:3, 3].copy()
        if hasattr(rig, 'streams'):
            streams, lost, flip = rig.streams(worlds[host], skel)
        else:
            streams, lost, flip = snakes8.mesh_streams(rig.geo, rig.kept, rig.table, np.eye(4), A)
        L = rig.bind_locals(place)
        skel, first = _append(skel, [rig.names[b] for b in rig.kept], rig.up, L, host, number)
        number += len(rig.kept)
        one = []
        for si, s in enumerate(rig.mesh.lods[0].sections):
            name = rig.mesh.material_name(s.material_index)
            if s.cloth_mapping or name in left:
                continue
            tri = np.asarray(rig.geo['triangles'][si], np.int64)
            if 'uvs' in rig.geo:                # (its second UV layout, for the bakes of what lies along it)
                from . import uvmap8
                uvmap8.register(name, rig.geo['uvs'], tri)
            one.append(dict(part=tag, material=name, tris=tri[:, [0, 2, 1]] if flip else tri, **streams))
        goal = int(rig.spec['vertices'])
        before = decimate.count({'prims': one})
        if rig.spec.get('lace'):                # (its pieces drawn as a picture on low grids: convert/lace8.py)
            from . import lace8
            one = lace8.cards(one, rig.up, goal, rig.spec['lace'], log)
        else:
            one = free_normals(thinned(one, streams['pos'], goal, log), streams)
        m = {'bones': {'names': rig.names}, 'prims': one}
        kept_cos = decimate.NORMAL_COS
        decimate.NORMAL_COS = -2.0              # (feathers and fur: no corner of a card is worth a vertex)
        try:
            for _ in range(4):
                if decimate.count(m) <= goal:
                    break
                m = decimate.decimate(m, goal, {tag: 1.0}, log=log)
        finally:
            decimate.NORMAL_COS = kept_cos
        log('  prefab %s: %d bones OPT %d.. under %s, %d -> %d vertices%s' % (
            tag, len(rig.kept), number - len(rig.kept), skel['names'][host], before, decimate.count(m),
            ', skin weight %.1f on no kept bone' % lost if lost > 1e-3 else ''))
        prims += m['prims']
        parts.append((tag, rig.spec['mesh'], first, len(rig.kept)))
    return skel, parts, prims


# ------------------------------------------------------------------------------------------------ moves
class Plan:
    """prepare()'s result: keys, the body animation keys whose clips carry the ground pair; held, those of them whose
    scene stays where the move began (HELD SCENES); clips [(members)] by START value (a member (model places, kind,
    clip, offset: frames the clip started before this animation))."""

    def __init__(self):
        self.keys = set()
        self.held = set()
        self.clips = []
        self.stats = collections.Counter()

    def value_of(self, members):
        members = tuple(sorted(members))
        if members not in self.clips:
            self.clips.append(members)
        return self.clips.index(members)

    def part3(self, store, d, skel, log=print):
        """(part-3 animations [bytes], {START value: index}) of the plan's animations and REST (skel: the fighter's
        skeleton, bone.read())."""
        rs = rigs(store, d, log)
        first = next(i for i, n in enumerate(skel['names']) if n.startswith('cha:OPT%d_' % OPT_FIRST))
        counts = [len(r.kept) for r in rs]
        starts = np.cumsum([0] + counts)
        total = int(starts[-1])
        rest = np.repeat(np.eye(4)[None], total, 0)
        for b in range(total):
            rest[b] = bone.local_matrix(skel, first + b)
            if skel['parent'][first + b] < first:            # a root: folded away
                rest[b, :3, :3] = 0.0
        places = {}
        for r in rs:
            up = skel['parent'][first + int(starts[rs.index(r)])]
            places[r.name] = bone.world_matrices(skel)[up][:3, 3].copy()
            if hasattr(r, 'offset'):
                r.offset(skel)
        anims, index = [], {}

        def add(value, L):                                   # (led by frame 0 again, ended by REST's pose)
            t, a, s = snakes8.decompose(np.concatenate([L[:1]] * LEAD + [L, rest[None][:, :L.shape[1]]], 0))
            chans = []
            for b in range(L.shape[1]):
                chans += [(11, t[:, b]), (7, a[:, b]), (3, s[:, b])]
            index[value] = len(anims)
            anims.append(tiger.raw_animation(chans))
        for value, members in enumerate(self.clips):
            frames, last = 0, 0
            parts = []
            for places_, kind, clip, offset in members:
                for p in places_:
                    r = rs[p]
                    L = r.locals_of(kind, clip, places[r.name])
                    parts.append((p, L, offset))
                    frames = max(frames, len(L) - offset)
                    last = max(last, int(starts[p]) + len(r.kept))
            out = np.repeat(rest[None], frames, 0)[:, :last].copy()
            for p, L, offset in parts:
                late = max(-offset, 0)                       # (it starts this many frames into the animation)
                L = L[max(offset, 0):]
                out[late:late + len(L), starts[p]:starts[p] + L.shape[1]] = L
            add(value, out)
        add(REST, rest[None])
        log('  prefabs: %d part-3 animations, %d frames, %d bones, %d bytes' % (
            len(anims), sum(int.from_bytes(a[4:8], 'big') for a in anims), total, sum(len(a) for a in anims)))
        return anims, index


def _table(k, name):
    t = getattr(k, 'tables', None)
    return t.get(name, []) if isinstance(t, dict) else []


def _start_of(k, c):
    """The frame a cancel enters its move at: its start_frame only if its extradata keeps the frames; else the first (a
    cancel to a move with a clip of its own: 3,2's dog after the slash, entered at 1 by a row with start_frame 27)."""
    extra = c.get('extradata')
    if extra is None or not _table(k, 'cancel_extras')[extra]['value'] & KEEP_FRAMES:
        return 1
    return c.get('start_frame') or 1


def _entries(k):
    """{move: [its entry frames by cancels (_start_of)]}."""
    out = collections.defaultdict(list)
    moves = _table(k, 'moves')
    for mv in moves:
        if mv.get('cancel') is None:
            continue
        for _, c in k.iter_list('cancels', mv['cancel'], lambda c: c['direction'] == LIST_END):
            if c['direction'] in (LIST_END, GROUP):
                continue
            j = c['move_id']
            if j is None:
                continue
            if j >= 0x8000 and hasattr(k, 'resolve_alias'):
                j = k.resolve_alias(j)
            s = _start_of(k, c)
            if s < 0x4000:
                out[j].append(s)
    return out


def _sources(k):
    """{move: [(the move cancelling into it, the frame it enters at)]}."""
    out = collections.defaultdict(list)
    moves = _table(k, 'moves')
    for i, mv in enumerate(moves):
        if mv.get('cancel') is None:
            continue
        for _, c in k.iter_list('cancels', mv['cancel'], lambda c: c['direction'] == LIST_END):
            if c['direction'] in (LIST_END, GROUP) or c['move_id'] is None:
                continue
            j = k.resolve_alias(c['move_id']) if c['move_id'] >= 0x8000 and hasattr(k, 'resolve_alias') \
                else c['move_id']
            out[j].append((i, _start_of(k, c)))
    return out


def _extras(k, i):
    mv = k.tables['moves'][i]
    if mv.get('extraprops') is None:
        return []
    return [r for _, r in k.iter_list('extra_move_properties', mv['extraprops'], PROP_END) if not PROP_END(r)]


def _named_body_clips(k, sp, stats):
    """The definition's PREFABS['body_clip_moves'] {move: clip}: a BODY_CLIP_PROP row for moves that have none of their
    own but go on showing a body rig's mesh (a stance's loops), in a copy of the move's list at the table's end."""
    named = dict(sp.get('body_clip_moves', {}))
    if not named:
        return
    table = _table(k, 'extra_move_properties')
    model = next((r for r in table if r['id'] == BODY_CLIP_PROP), None)
    end = next(r for r in table if PROP_END(r))
    for i, mv in enumerate(_table(k, 'moves')):
        clip = named.pop(k.move_name(i) or '#%d' % i, None)
        if clip is None:
            continue
        rows = [dict(r) for r in _extras(k, i)]
        mv['extraprops'] = len(table)
        table += rows + [dict(model, frame=AT_START, value=clip), dict(end)]
        stats['moves showing a body rig\'s clip the definition names'] += 1
    if named:
        raise ValueError('body_clip_moves of moves not found: %s' % sorted(named))


def _entry_of(entries):
    """The frame a move is entered at, by its cancels (the most common; none: 1)."""
    if not entries:
        return 1
    return collections.Counter(entries).most_common(1)[0][0]


def _plain(frame, entry):
    """A row's frame -> AT_START or a plain body frame; RELATIVE + n: the n-th frame after the entry."""
    if frame == AT_START:
        return AT_START
    if frame >= RELATIVE:
        return entry + frame - RELATIVE - 1
    return frame


def _fired(frame, entry):
    """The body frame a row of `frame` (_plain's) fires at."""
    return entry if frame == AT_START else max(frame, entry)


def _on_entry(frame, entry):
    """A row's frame for TTT2 (_plain's): a row the entry has passed fires as the move is entered in Tekken 8, where
    TTT2 goes past it: it takes the frame of the move's first (1+2's wing, shown again on the hit's move at its 12)."""
    return AT_START if frame != AT_START and frame < entry else frame


def prepare(k, d, log=print):
    """Tekken 8 moveset k (its banks attached; summons8.prepare has split its masks) made ready for the converter, in
    place, for the definition's prefabs. -> Plan, or None without them."""
    sp = spec(d)
    if sp is None:
        return None
    plan = Plan()
    stats = plan.stats
    kinds = list(sp['kinds_order'])
    by_kind = collections.defaultdict(list)
    for place, m in enumerate(sp['models']):
        for kind in m['kinds']:
            by_kind[kind].append(place)
    dependent = dict(sp.get('dependent', {}))
    held, found = set(sp.get('held_moves', ())), set()     # (HELD SCENES)
    # (a dissolving lace model's summon: its fades over the share of Tekken 8's frames its lace names, dissolve_frames)
    shapes = {m['summon']: (m.get('lace') or {}).get('dissolve_share', 1.0) for m in sp['models']
              if (m.get('lace') or {}).get('dissolve') and m.get('summon') is not None}

    def fade(n, frames):
        if n in shapes and frames and frames > 1:
            stats['fades of dissolving summons shortened to their shapes\''] += 1
            frames = dissolve_frames(frames, shapes[n])
        return _fade(n, frames)
    moves = _table(k, 'moves')
    _named_body_clips(k, sp, stats)
    entries, sources = _entries(k), _sources(k)
    starts = {}                                 # move -> [(kind, clip, row)]
    for i in range(len(moves)):
        got = []
        for r in _extras(k, i):
            if r['id'] == START_PROP:
                got.append((kinds[r['value'] >> 8 & 0xFF], r['value'] & 0xFF, r))
            elif r['id'] == BODY_CLIP_PROP and by_kind[BODY_CLIP]:
                got.append((BODY_CLIP, r['value'], r))
        if got:
            starts[i] = got

    def summons_of(kind):
        return [sp['models'][p]['summon'] for p in by_kind[kind]]

    def rewrite(rows, i, entry):
        """A list's rows with its prefab rows made the converter's."""
        out = []
        own = starts.get(i, [])
        value, first_at = None, None
        if own:
            at = [_fired(_plain(r['frame'], entry), entry) for _, _, r in own]
            first_at = min(at)
            members = []
            for (kind, clip, _), t in zip(own, at):
                # (a kind of no model of the definition's: not drawn)
                if kind == BODY_CLIP:           # (in step with the body: frame x of the clip on its frame x)
                    members.append((tuple(by_kind[kind]), kind, clip, first_at - 1))
                elif by_kind[kind]:
                    members.append((tuple(by_kind[kind]), kind, clip, first_at - t))
            started = {kind for kind, _, _ in own}
            for r in rows:                      # (a clip of the move before still shown: its hide row here)
                if r['id'] == HIDE_ROW and r['value'] != SLOT_DEPENDENT and r['value3'] < len(kinds):
                    kind = kinds[r['value3']]
                    if kind in started or not by_kind[kind]:
                        continue
                    for s, at_in in sources.get(i, ()):
                        hit = next(((c, q) for w, c, q in starts.get(s, ()) if w == kind), None)
                        if hit:
                            s_entry = _entry_of(entries.get(s))
                            began = _fired(_plain(hit[1]['frame'], s_entry), s_entry)
                            members.append((tuple(by_kind[kind]), kind, hit[0], first_at - began))
                            started.add(kind)
                            stats['clips a move plays on with the one it starts'] += 1
                            break
            if members:
                value = plan.value_of(members)
        fades = {}
        for r in rows:
            if r['id'] == SHOW_ROW and r['value'] == SLOT_DEPENDENT and r['value3'] in dependent:
                fades[dependent[r['value3']]] = _plain(r['frame'], entry)
        placed_start = False
        for r in rows:
            idv = r['id']
            if idv == START_PROP or idv == BODY_CLIP_PROP and by_kind[BODY_CLIP]:
                if placed_start or value is None:
                    continue
                placed_start = True
                frame = AT_START if first_at <= entry else first_at
                out.append(dict(r, id=START_PROP, frame=frame, value=value))
                stats['clips started'] += 1
            elif idv == STOP_PROP:
                if r['value'] == 0 or not any(q['id'] == STOP_PROP and q['value'] == 0 for q in rows):
                    out.append(dict(r, id=START_PROP, value=REST, frame=_plain(r['frame'], entry)))
                    stats['clips stopped'] += 1
            elif idv in (SHOW_ROW, HIDE_ROW):
                slot, frames, kind = r['value'], r['value2'], r['value3']
                frame = _plain(r['frame'], entry)
                if slot == SLOT_DEPENDENT:
                    n = dependent.get(kind)
                    if n is None:
                        continue
                    frame = _on_entry(frame, entry)
                    if idv == SHOW_ROW:
                        out.append(dict(r, id=DISMISS, value=n, value2=0, value3=0, frame=frame))
                    out.append(dict(r, id=SUMMON if idv == SHOW_ROW else DISMISS, value=fade(n, frames), value2=0,
                                    value3=0, frame=frame))
                    stats['fades of the body rig\'s summons'] += 1
                elif kind < len(kinds):
                    frame = _on_entry(frame, entry)
                    for n in summons_of(kinds[kind]):
                        if idv == SHOW_ROW:
                            out.append(dict(r, id=DISMISS, value=n, value2=0, value3=0, frame=frame))
                        out.append(dict(r, id=SUMMON if idv == SHOW_ROW else DISMISS, value=fade(n, frames),
                                        value2=0, value3=0, frame=frame))
                    stats['prefab shows and hides'] += 1
            elif idv == SUMMON and r['value'] in fades:     # (the mask's: the fade's row shows it)
                if r['frame'] == AT_START or r['frame'] <= _fired(fades[r['value']], 0):
                    stats['plain summons a fade replaces'] += 1
                    continue
                out.append(r)
            elif idv in (SUMMON, DISMISS) and r['frame'] < RELATIVE:
                out.append(dict(r, frame=_on_entry(r['frame'], entry)))
            else:
                out.append(r)
        return out
    extra = _table(k, 'extra_move_properties')
    made = {}
    for i, mv in enumerate(moves):
        start = mv.get('extraprops')
        if start is None:
            continue
        rows = _extras(k, i)
        entry = _entry_of(entries.get(i))
        if not any(r['id'] in (START_PROP, STOP_PROP, SHOW_ROW, HIDE_ROW) or r['id'] == BODY_CLIP_PROP and
                   by_kind[BODY_CLIP] or r['id'] in (SUMMON, DISMISS) and r['frame'] < entry for r in rows):
            continue
        key = start, entry, i if i in starts else None
        if key not in made:
            new = rewrite(rows, i, entry)
            made[key] = len(extra)
            end = next((r for _, r in k.iter_list('extra_move_properties', start, PROP_END) if PROP_END(r)), None)
            extra += new + [dict(end) if end is not None else dict(rows[-1], id=0, frame=0, value=0)]
        mv['extraprops'] = made[key]
        ref = k.anim_ref(i)[0]
        if ref is not None and any(r['id'] in (START_PROP, SHOW_ROW) and r['value'] != SLOT_DEPENDENT or
                                   r['id'] == HIDE_ROW and r['value'] != SLOT_DEPENDENT for r in rows):
            plan.keys.add(ref)
            if (k.move_name(i) or '#%d' % i) in held:
                found.add(k.move_name(i) or '#%d' % i)
                plan.held.add(ref)
                stats['moves whose scene stays where they began (held_moves)'] += 1
    for row in _table(k, 'move_end_props'):     # (hides as a move ends)
        if row['id'] == HIDE_ROW:
            slot, frames, kind = row['value'], row['value2'], row['value3']
            n = dependent.get(kind) if slot == SLOT_DEPENDENT else (summons_of(kinds[kind])[:1] or [None])[0] \
                if kind < len(kinds) else None
            if n is None:
                continue
            row.update(id=DISMISS, value=fade(n, frames), value2=0, value3=0)
            stats['hides as a move ends'] += 1
    if held - found:
        raise ValueError('held_moves that show no prefab: ' + ', '.join(sorted(held - found)))
    for line, n in sorted(stats.items()):
        log('%s: %d' % (line, n))
    log('prefabs: %d animations, %d body animations carry the ground pair' % (len(plan.clips), len(plan.keys)))
    return plan


def dissolve_frames(frames, share):
    """The frames a dissolving summon (convert/lace8.py) forms or goes over for a Tekken 8 fade of `frames`: Tekken 8's
    shape is whole (or gone) after `share` of its fade, its tint (effects) going on after; at least 2 (a fade)."""
    return max(2, int(frames * min(max(float(share), 0.0), 1.0) + 0.5))


def _fade(n, frames):
    from .summons8 import fade_value
    return fade_value(n, frames)


# ------------------------------------------------------------------------------------------------ scene cuts
CUT_LEAST = 1000.0              # mm: a scene cut's one-frame jump of the attacker's Top is at least this long


def scene_cuts(k, d, path, log=print):
    """{body clip key: (frames, 3) mm added to its Top's path} for the definition's PREFABS 'scene_cuts' (SCENE CUTS:
    {attacker move: (cut frame, victim move, the frame his push starts)}): the attacker's clip the jump at the cut
    (beyond the steps either side of it) taken back from that frame on, the victim's the same jump, grown with his
    travel along it from the push's first frame to the cut. k: Tekken 8 moveset; path: body clip key -> its Top's path (frames, 3) mm in its scene, y up
    (anim.Converter.pose's)."""
    cuts = (spec(d) or {}).get('scene_cuts', {})
    if not cuts:
        return {}
    index = {k.move_name(i) or '#%d' % i: i for i in range(len(_table(k, 'moves')))}
    out = {}
    for name, (cut, victim, push) in sorted(cuts.items()):
        missing = [n for n in (name, victim) if n not in index]
        if missing:
            raise ValueError('scene_cuts: no move %s' % ', '.join(missing))
        keys = [k.anim_ref(index[n])[0] for n in (name, victim)]
        A, V = (np.asarray(path(key), np.float64) for key in keys)
        if not (2 <= cut < len(A) - 1 and 0 <= push < cut < len(V)):
            raise ValueError('scene_cuts: %s: cut at %d, push from %d, of %d and %d frames' % (
                name, cut, push, len(A), len(V)))
        jump = A[cut - 1] + (A[cut - 1] - A[cut - 2] + A[cut + 1] - A[cut]) / 2.0 - A[cut]
        jump[1] = 0.0
        size = float(np.linalg.norm(jump))
        if size < CUT_LEAST:
            raise ValueError('scene_cuts: %s moves %.0f mm at frame %d, no cut' % (name, size, cut))
        away = (V[push:cut + 1] - V[push]) @ (jump / size)
        if away[-1] <= 0:
            raise ValueError('scene_cuts: %s does not move away from frame %d to %d' % (victim, push, cut))
        grow = np.zeros(len(V))
        grow[push:cut + 1] = np.clip(np.maximum.accumulate(away) / away[-1], 0.0, 1.0)
        grow[cut + 1:] = 1.0
        shift = np.zeros_like(A)
        shift[cut:] = jump
        out[keys[0]], out[keys[1]] = shift, grow[:, None] * jump
        log('scene cut: %s at frame %d, %.0f mm taken back; %s pushed that much further from frame %d (his own push: '
            '%.0f mm)' % (name, cut, size, victim, push, away[-1]))
    return out


def twists(k, d, log=print):
    """{body clip key: (first frame, last frame, radians, flat frame or None)} for the definition's PREFABS 'twists'
    (TWISTS: {move: (first frame, last frame, degrees[, flat frame])}): the clip's turn about his hips over those
    frames (tekken8/anim.py channels' twist; retarget.twist's flat). k: Tekken 8 moveset."""
    spec_ = (spec(d) or {}).get('twists', {})
    if not spec_:
        return {}
    index = {k.move_name(i) or '#%d' % i: i for i in range(len(_table(k, 'moves')))}
    out = {}
    for name, entry in sorted(spec_.items()):
        first, last, degrees = entry[:3]
        flat = entry[3] if len(entry) > 3 else None
        if name not in index:
            raise ValueError('twists: no move %s' % name)
        if not 0 < first < last or flat is not None and flat < last:     # (retarget.twist: after the first)
            raise ValueError('twists: %s: frames %d to %d (flat by %s)' % (name, first, last, flat))
        out[k.anim_ref(index[name])[0]] = (int(first), int(last), float(np.radians(degrees)),
                                           None if flat is None else int(flat))
        log('twist: %s turned %g degrees about his hips over frames %d-%d%s' % (
            name, degrees, first, last, '' if flat is None else ', in their own frame, flat by %d' % flat))
    return out


# ------------------------------------------------------------------------------------------------ lead-ins
UP = 2                          # the prefabs' worlds: Unreal's, z up


def _locals_of(W, parents):
    """Local matrices (..., bones, 4, 4) of worlds."""
    L = W.copy()
    for b, p in enumerate(parents):
        if p >= 0:
            L[..., b, :, :] = np.linalg.inv(W[..., p, :, :]) @ W[..., b, :, :]
    return L


def _worlds_of(L, parents):
    W = L.copy()
    for b, p in enumerate(parents):
        if p >= 0:
            W[..., b, :, :] = W[..., p, :, :] @ L[..., b, :, :]
    return W


def _mix(A, B, w):
    """Matrices (..., 4, 4) of a uniform scale a fraction w (broadcast over the leading axes) of the way from A to B:
    the rotation the shorter way, the translation and the scale straight."""
    from .retarget import slerp
    w = np.asarray(w, np.float64)
    sa, sb = (np.linalg.norm(M[..., :3, 0], axis=-1) for M in (A, B))
    out = np.zeros(np.broadcast_shapes(A.shape[:-2], B.shape[:-2], w.shape) + (4, 4))
    out[..., :3, :3] = slerp(A[..., :3, :3] / sa[..., None, None], B[..., :3, :3] / sb[..., None, None], w) * \
        ((1 - w) * sa + w * sb)[..., None, None]
    out[..., :3, 3] = (1 - w[..., None]) * A[..., :3, 3] + w[..., None] * B[..., :3, 3]
    out[..., 3, 3] = 1.0
    return out


def lead_in(W, D, parents, mover, run, flight):
    """Worlds (frames, bones, 4, 4) of a clip W whose creature shows only from a cut on (its mover's scale tiny before
    it), with a way in before the cut (LEAD-INS): D the donor clip's worlds (the same skeleton), mover the bone that
    carries the creature (the bones above it as at the cut), run (first, last) the donor's run-up frames (the last one
    in the air, the flight's first), flight the frames from there to the cut."""
    W, D = np.array(W, np.float64), np.asarray(D, np.float64)
    size = np.linalg.norm(W[:, mover, :3, 0], axis=1)
    shown = size > 0.1 * size.max()
    cut = int(np.argmax(shown))
    first = cut - flight - (run[1] - run[0])
    if not (0 < cut < len(W) - 1 and not shown[:cut].any() and first >= 0 and flight >= 1 and
            0 <= run[0] < run[1] < len(D) - 1):
        raise ValueError('lead-in: cut at %d of %d frames, run %s, flight %d, donor of %d frames' % (
            cut, len(W), run, flight, len(D)))
    at = W[cut, mover, :3, 3]
    v = W[cut + 1, mover, :3, 3] - at
    src = D[:, mover, :3, 3]
    pull = 2.0 * (at[UP] - v[UP] * flight - src[run[1], UP]) / flight ** 2
    if pull <= 0:
        raise ValueError('lead-in: the cut is no higher than the run-up leaves the ground')
    t = np.arange(-flight, 0, dtype=np.float64)
    path = at + t[:, None] * v
    path[:, UP] = at[UP] + v[UP] * t - 0.5 * pull * t ** 2
    flat = np.ones(3)
    flat[UP] = 0.0
    a, b = (src[run[1] + 1] - src[run[1]]) * flat, v * flat
    x, y = [i for i in range(3) if i != UP]
    turn = np.arctan2(b[y], b[x]) - np.arctan2(a[y], a[x])
    G = np.eye(4)
    G[[x, x, y, y], [x, y, x, y]] = np.cos(turn), -np.sin(turn), np.sin(turn), np.cos(turn)
    G[:3, 3] = (path[0] - G[:3, :3] @ src[run[1]]) * flat
    under = [b_ for b_ in range(len(parents)) if b_ != mover and _below(parents, b_, mover)]
    Lc, Ld = _locals_of(W[cut], parents), _locals_of(D, parents)
    up = np.linalg.inv(W[cut, parents[mover]])
    L = np.repeat(Lc[None], cut - first, 0)
    k = run[1] - run[0]
    L[:k, under] = Ld[run[0]:run[1]][:, under]
    L[:k, mover] = up @ G @ D[run[0]:run[1], mover]
    w = np.arange(flight) / flight
    w = w * w * (3 - 2 * w)                                             # (from leaving the ground into the cut's pose)
    L[k:, under] = _mix(Ld[run[1]][None, under], Lc[None, under], w[:, None])
    M = _mix((G @ D[run[1], mover])[None], W[cut, mover][None], w)
    M[:, :3, 3] = path
    L[k:, mover] = up @ M
    W[first:cut] = _worlds_of(L, parents)
    return W


def _below(parents, b, top):
    while b >= 0:
        if b == top:
            return True
        b = parents[b]
    return False


# ------------------------------------------------------------------------------------------------ hit points
class HoldClips:
    """The holding joints' paths of list 3's clips. bank: the fighter's own animation bank (anmbin.Bank)."""

    def __init__(self, bank):
        self.bank = bank
        self.cache = {}

    def __call__(self, index, joint):
        """(positions (frames, 3) mm, rotations (frames, 3, 3)) of the joint through clip `index`."""
        key = index, joint
        if key not in self.cache:
            from ..tekken8 import anim, panm
            from ..ttt2 import animation
            bl = self.bank
            j = panm.Animation(bl.blob(LIST3, bl.key_lists[LIST3][index])).joints()[joint]
            self.cache[key] = (np.asarray(j.translation, np.float64) * snakes8.CM,
                               animation.quaternion_to_matrix(anim._quaternions(j.rotation)))
        return self.cache[key]


def scene_spots(k, d, stats):
    """The moves with a HOLD_CLIP_PROP or MISSILE_CLIP_PROP row (k: Tekken 8 moveset, summons8.prepare's hit box
    summaries made): their boxes on the definition's holding joints hit from the clip's path (HIT POINTS above):
    mv['spots'] with ('scene', joint, offset, delta, clip index, the body frame its row fires at); a box with a radius
    takes the summary's second line, and with no other box both, as the line across it."""
    sp = spec(d)
    if sp is None:
        return
    joints = {loc: j for loc, (j, _) in getattr(d, 'HIT_JOINTS', {}).items() if j in sp.get('hold_joints', ())}
    entries = _entries(k)
    for i, mv in enumerate(_table(k, 'moves')):
        hb = mv.get('hitboxes') or ()
        rows = [r for r in _extras(k, i) if r['id'] in (HOLD_CLIP_PROP, MISSILE_CLIP_PROP)]
        if not rows or len(hb) < 2:
            continue
        ours = [h for h in hb if h.loc in joints and (h.loc or h.loc2)]
        if not ours:
            continue
        entry = _entry_of(entries.get(i))
        index = int(rows[0]['value'])
        fired = _fired(_plain(rows[0]['frame'], entry), entry)

        reach = float(sp.get('scene_reach', {}).get(k.move_name(i) or '#%d' % i, 0.0))

        def spot(h, off, delta):
            delta = (float(delta[0]), float(delta[1]), float(delta[2]) + reach)
            return ('scene', joints[h.loc], tuple(float(x) for x in off), delta, index, fired)
        thick = max(ours, key=lambda h: float(h.radius))
        r = float(thick.radius)
        if r >= THICK:
            line = [spot(thick, thick.a, (-r, 0.0, 0.0)), spot(thick, thick.a, (r, 0.0, 0.0))]
        else:
            b = thick.b if thick.loc2 == thick.loc else thick.a
            line = [spot(thick, thick.a, (0.0, 0.0, 0.0)), spot(thick, b, (0.0, 0.0, 0.0))]
        other = next((h for h in hb if (h.loc or h.loc2) and h.loc not in joints and h.loc2 not in joints), None)
        if other is not None:
            mv['summary'] = (other, thick)
            mv['spots'] = [other.loc, other.loc2] + line
            mv['hitbox'] = bytes((other.loc, other.loc2, thick.loc, thick.loc2))
        else:
            mv['summary'] = (thick, thick)
            mv['spots'] = line + line
            mv['hitbox'] = bytes((thick.loc, thick.loc2 or thick.loc, thick.loc, thick.loc2 or thick.loc))
        stats['moves hitting from a hold clip\'s path'] += 1


def summaries(k, d, stats):
    """The definition's PREFABS['hit_boxes'] {move: (box, box)}: the two boxes a move's TTT2 summary takes where what
    reaches is not boxes 0 and 1 (mv['summary'], which summons8.prepare's later steps read)."""
    named = dict((spec(d) or {}).get('hit_boxes', {}))
    for i, mv in enumerate(_table(k, 'moves')):
        pick = named.pop(k.move_name(i) or '#%d' % i, None)
        if pick is None:
            continue
        hb = mv['hitboxes']
        mv['summary'] = (hb[pick[0]], hb[pick[1]])
        mv['hitbox'] = bytes((hb[pick[0]].loc, hb[pick[0]].loc2, hb[pick[1]].loc, hb[pick[1]].loc2))
        stats['moves whose summary takes the boxes the definition names'] += 1
    if named:
        raise ValueError('hit_boxes of moves not found: %s' % sorted(named))


def named_spots(k, d, stats):
    """The definition's PREFABS['hit_spots'] {move: its four ends}, each a Tekken 8 hit code or a root point
    (summons8.joint_spots' forms), for an end TTT2 has no code of. After joint_spots: these win over a joint's."""
    named = dict((spec(d) or {}).get('hit_spots', {}))
    for i, mv in enumerate(_table(k, 'moves')):
        spots = named.pop(k.move_name(i) or '#%d' % i, None)
        if spots is not None:
            mv['spots'] = list(spots)
            mv['hitbox'] = bytes(s if isinstance(s, int) else 125 for s in spots)
            stats['moves hitting from the spots the definition names'] += 1
    if named:
        raise ValueError('hit_spots of moves not found: %s' % sorted(named))


def thick_roots(k, stats):
    """A summary box at the ground origin with a radius (Clive's d/f+1+2's: a metre across, half a metre up and down)
    has no TTT2 form: its line would be upright or no line at all, and the victim's spheres are what reach. It hits
    along the line across it, ahead to behind at its middle height (mv['spots'] of the same form as joint_spots')."""
    from . import summons8
    ROOT = summons8.ROOT_CODE
    for mv in _table(k, 'moves'):
        if len(mv.get('hitboxes') or ()) < 2:
            continue
        boxes = summons8._boxes(mv)
        thick = [n for n, h in enumerate(boxes) if h.loc == ROOT and h.loc2 in (ROOT, 0) and float(h.radius) >= THICK]
        if not thick:
            continue
        spots = list(mv.get('spots') or ())
        if not spots:
            for h in boxes:
                for loc, off in ((h.loc, h.a), (h.loc2, h.b)):
                    spots.append(tuple(float(x) for x in off) if loc == ROOT else loc)
        for n in thick:
            h = boxes[n]
            r = float(h.radius)
            a = np.asarray(h.a, np.float64)
            b = np.asarray(h.b, np.float64) if h.loc2 == ROOT else a
            mid = (a + b) / 2
            spots[2 * n] = (float(mid[0]), float(mid[1]), float(min(a[2], b[2]) - r))
            spots[2 * n + 1] = (float(mid[0]), float(mid[1]), float(max(a[2], b[2]) + r))
        if thick == [0, 1] and np.allclose(spots[0][:2], spots[2][:2], atol=1.0):
            # (both on one line, d/b+2,1's ice spikes 1 m and 1.75 m ahead: a clip has two root points, so one line
            # from the nearest end to the farthest; its four ends fell to two, 0.74 to 1.26 m)
            ends = sorted(spots[:4], key=lambda x: x[2])
            spots[:4] = [ends[0], ends[-1], ends[0], ends[-1]]
            stats['moves hitting across two thick boxes on one line at the ground origin'] += 1
        mv['spots'] = spots
        mv['hitbox'] = bytes(ROOT if isinstance(s, tuple) else s for s in spots)
        stats['moves hitting across a thick box at the ground origin'] += 1


def root_windows(k, found, stats):
    """found (summons8.RootPoints): a clip whose moves hit from other root points gets each move's in the frames it
    hits (root point ('windows', [(first index, end index, spot)])): 3,2 plays one clip for the sword's hit and the
    dog's, each from its own points. Those moves' hit codes are written here and they leave found.moves."""
    from . import summons8
    by_clip = collections.defaultdict(list)
    for i, key in found.moves.items():
        by_clip[key].append(i)
    moves = _table(k, 'moves')
    for key, members in by_clip.items():
        own = {i: summons8._offsets(moves[i])[:2] for i in members}
        if len({tuple(o) for o in own.values()}) < 2:
            continue
        members.sort(key=lambda i: (moves[i]['last_active'], moves[i]['first_active']))
        slices = []
        end = 0
        for i in members:
            stop = int(moves[i]['last_active']) + 1         # (index of the frame after it: its path's last end)
            if stop <= end:
                continue
            slices.append((end, stop, i))
            end = stop
        if not slices:
            continue
        last = slices[-1]
        slices[-1] = (last[0], 1 << 20, last[2])
        found[key] = [('windows', [(a, b, own[i][min(r, len(own[i]) - 1)]) for a, b, i in slices])
                      for r in range(len(summons8.ROOT_CODES))]
        played = {i for _, _, i in slices}
        for i in members:
            mv = moves[i]
            source = i if i in played else next(j for _, _, j in slices if moves[j]['last_active'] >= mv['last_active'])
            spots = own[source]
            codes = list(mv['hitbox'])
            if 'spots' in mv:
                for c, spot in enumerate(mv['spots']):
                    if isinstance(spot, tuple):
                        codes[c] = summons8.ROOT_CODES[spots.index(spot)] if spot in spots else summons8.ROOT_CODES[-1]
                    else:
                        codes[c] = spot
            else:
                hb = summons8._boxes(mv)
                at = [(hb[0].loc, hb[0].a), (hb[0].loc2, hb[0].b), (hb[1].loc, hb[1].a), (hb[1].loc2, hb[1].b)]
                for c, (loc, off) in enumerate(at):
                    if loc == summons8.ROOT_CODE and codes[c] == summons8.ROOT_CODE:
                        plain = [n for n, s in enumerate(spots) if not isinstance(s[0], str)] or [0]
                        near = min(plain, key=lambda n: np.linalg.norm(np.subtract(off, spots[n])))
                        codes[c] = summons8.ROOT_CODES[near]
            mv['hitbox'] = bytes(codes)
            del found.moves[i]
            stats['moves hitting from root points of their own frames in a shared clip'] += 1
