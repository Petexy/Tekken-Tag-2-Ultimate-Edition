"""The added fighter's face animations: moved with its face joints, its eyelids turned as far as its own game turns them.

TTT2's face animations (a moveset's embedded MOTA 4 and its motion pack's item 2: 70 channels, the 31 face joints'
(translation, rotation) pairs in skeleton.FACE's order, then 2 x 3 + 6 x 11 that are no joint's) set the face joints'
ABSOLUTE local translations and rotations, made for the donor's face. An added fighter's are its donor's, changed:
* Pivots. Its face joints sit at its own face's (skeleton.build), where its mesh is weighted around: a blink, a glance
  and the jaw turn about its own eyelids, eyes and jaw (the donor's eye centres are 12 mm from Lidia's, 42 mm from
  Noctis's). So every face animation moves each joint's translation by its offset (the joint's local translation less
  the donor's): the joints move by the donor's deltas from their own places.
* Eyelids. How far a lid turns to close the eye depends on the face: Tekken 7 turns Lidia's upper lids 44 degrees at
  most, Noctis's 29, Kazumi's 72, where Jun's animations turn them 63 and Lars's 57. Turned the donor's way, a lid
  overshot the eye and hung down the cheek, its painted underside showing (Lidia's mauve, lit blue in TTT2). So each
  eyelid joint's turns (UwaMabuta upper, SitaMabuta lower) are scaled by the fighter's largest turn in its own game's
  face animations (from its usual, open pose) over the donor's (from the bind pose, where TTT2's lids are open), down
  only: a lid turned further than the donor's sinks into the eyeball (TTT2 blends a lid's skin weights linearly), and
  Tekken 7's largest turns beyond the donor's are squeezed eyes (Chloe's 89 degrees showed her eyeball through the lid,
  where the donor's turn closes it).

* Tekken 8's eyelids (lid_turns_on_meshes). Tekken 8 blinks with a control joint posed at run time, so its face
  animations hold no turn to measure. And the donor's turns are made for its own lids: TTT2 weights a lid's margin
  about half to its eyelid joint (Jun's at most 0.53 upper, 0.71 lower), where Tekken 8 weights it fully, so with
  the skin's linear blend Jun's margin turns about half as far as her joint: her closed eyes are 51.6 degrees, her
  squeezed ones 63, but a Tekken 8 face closes at about 30 (Miary Zo 32, Reina 36, Azucena 29). Turned the donor's
  way, the lid went 20 degrees past the lower one, sank into the eyeball, and its narrow eyeshadow band stretched
  over the whole eye: a dark smear where a closed eye should be. So both faces are measured as the game skins them
  (lid_motion: each eye's opening, and how far each lid's margin closes per degree its joint turns), and each lid is
  scaled so that it closes the same share of the fighter's opening as the donor's lid of the donor's: Jun's closed
  eyes close hers, her squeezed ones just meet.

A compressed (0x64) animation's translations are its frame-0 values plus deltas: moving them changes the frame-0
values (3 floats in place); a raw (0xC8) one has every frame's. Turned lids re-encode the animation with its own
quantisation (animation.compression_params: the other channels decode as before, bit for bit) and rebuild its MOTA.
(The game's face animations are all compressed: a raw one keeps its lids' turns.)

Written for this project from the games' data (no third-party code).
"""
import struct

import numpy as np

from . import skeleton
from ..ttt2 import animation, bone, motbin, motion, nud

CHANNELS = 70                   # a face animation's channels
MOTBIN_SLOT = 4                 # the moveset's embedded face MOTA
PACK_ITEM = 2                   # the motion pack's face MOTA
MIN_OFFSET = 1e-3               # mm: a joint closer to the donor's place keeps its channels
LIDS = ('L_UwaMabuta_Joint', 'R_UwaMabuta_Joint', 'L_SitaMabuta_Joint', 'R_SitaMabuta_Joint')
# Tekken 7's face animations (tkmvst.face_animations: 43 joints' (translation, rotation) pairs, then 4 x 3, in the
# same order for every fighter): the eyelids' rotation channels
TEKKEN7_CHANNELS = 90
TEKKEN7_LIDS = {'R_UwaMabuta_Joint': 17, 'L_UwaMabuta_Joint': 23, 'R_SitaMabuta_Joint': 33, 'L_SitaMabuta_Joint': 39}
LID_SCALES = (0.25, 1.0)        # a lid's scale stays within these (a face whose animations never blink keeps it moving)
SAME_SCALE = 0.02               # a scale this near 1 leaves the lid as the donor turns it
SAMPLE = 400                    # rotations sampled to find a lid's usual pose
# a face's eyes measured on its mesh (lid_motion): a lid's margin = its points weighted at least MARGIN of its joint's
# largest weight; of these, the ones in the middle of the eye (along the lid's axis within MIDDLE of the lids' span
# around its middle) and over the eyeball (at least FRONT of the farthest one's distance from the axis: not the
# socket's inside)
MARGIN = 0.9
MIDDLE = 0.3
FRONT = 0.8


def _names(s):
    return [n[4:] if n.startswith('cha:') else n for n in s['names']]


def offsets(skel, donor):
    """{channel: local offset (3,)} of the face joints of `skel` (the added fighter's skeleton, bone.read) away from the
    donor's (its translation channels' numbers: 2 k for skeleton.FACE[k])."""
    mine, theirs = _names(skel), _names(donor)
    out = {}
    for k, name in enumerate(skeleton.FACE):
        if name not in mine or name not in theirs:
            continue
        d = np.asarray(skel['t'][mine.index(name)], np.float64) - np.asarray(donor['t'][theirs.index(name)], np.float64)
        if float(np.abs(d).max()) > MIN_OFFSET:
            out[2 * k] = d
    return out


def _angle(a, b):
    """Degrees between rotation matrices a and b (broadcast)."""
    c = (np.trace(np.swapaxes(a, -1, -2) @ b, axis1=-2, axis2=-1) - 1) / 2
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


def tekken7_lids(anims):
    """{eyelid joint: its largest turn (degrees) from its usual pose} over a Tekken 7 fighter's face animations
    (tkmvst.face_animations); {} without any."""
    anims = [v for v in anims if v.ndim == 3 and v.shape[1] == TEKKEN7_CHANNELS and len(v)]
    out = {}
    for name, c in TEKKEN7_LIDS.items() if anims else ():
        R = animation.local_rotation(np.concatenate([v[:, c] for v in anims]).astype(np.float64))
        sample = R[::max(1, len(R) // SAMPLE)]
        usual = sample[int(np.argmin([np.median(_angle(r, sample)) for r in sample]))]   # nearest most others
        out[name] = float(_angle(usual, R).max())
    return out


def _is_face(h):
    d = h['descriptors']
    return h['nch'] == CHANNELS and all(d[2 * k] == animation.TRANSLATION for k in range(len(skeleton.FACE)))


def _lid_channels():
    return {name: 2 * skeleton.FACE.index(name) + 1 for name in LIDS}


def _move(buf, h, moves, endian):
    """The face animation buf (a bytearray, changed in place; h: its header) with its translation channels {channel:
    offset} moved."""
    if h['type'] == animation.RAW:
        for f in range(h['frames']):
            for c, d in moves.items():
                at = h['data'] + 12 * (h['nch'] * f + c)
                v = np.array(struct.unpack_from(endian + '3f', buf, at), np.float64) + d
                struct.pack_into(endian + '3f', buf, at, *v)
        return
    at = 4 + 2 * h['nch'] + 6 + 4 * len(h['scales'])         # the frame-0 values
    for c, dsc in enumerate(h['descriptors']):
        if c in moves:
            v = np.array(struct.unpack_from(endian + '3f', buf, at), np.float64) + moves[c]
            struct.pack_into(endian + '3f', buf, at, *v)
        at += 6 if animation.is_rotation(dsc) else 12


def _turn(buf, h, turns, endian):
    """The compressed face animation buf re-encoded with its rotation channels' angles {channel: scale} scaled."""
    params = animation.compression_params(buf, endian)
    v = animation.decode(buf, endian)['values'].astype(np.float64)
    first = [list(x) for x in params['first']]
    for c, s in turns.items():
        v[:, c, 2] *= s
        first[c][2] = int(np.clip(round(first[c][2] * s), -0x8000, 0x7FFF))
    return animation.encode_compressed(h['descriptors'], v, endian, params=dict(params, first=first))


def _animations(buf, start, end):
    """(byte order, [each entry's animation number], [the animations' bytes]) of the MOTA at buf[start:end]: entries
    may share an animation (Jun's moveset's last 13 one)."""
    endian, offs = motion.mota_offsets(buf, start)
    at = sorted(set(offs))
    bounds = [start + o for o in at] + [end]
    return endian, [at.index(o) for o in offs], [bytes(buf[a:b]) for a, b in zip(bounds, bounds[1:])]


def _mota(header, entries, anims):
    """A big-endian MOTA: header (its first 0x14 bytes), each entry's animation number, the animations."""
    at, offs = 0x14 + 4 * len(entries), []
    body = b''.join(a + bytes(-len(a) % 4) for a in anims)
    for a in anims:
        offs.append(at)
        at += len(a) + (-len(a) % 4)
    hdr = bytearray(header[:0x14])
    struct.pack_into('>I', hdr, 0xC, len(entries))
    return bytes(hdr) + struct.pack('>%dI' % len(entries), *[offs[k] for k in entries]) + body


def _donor_lids(anims):
    """{eyelid joint: its largest turn (degrees) from the bind pose} over TTT2 face animations [(byte order, bytes)]."""
    out = dict.fromkeys(LIDS, 0.0)
    for endian, a in anims:
        h = animation.header(a, endian)
        if h['type'] != animation.COMPRESSED or not _is_face(h):
            continue
        v = animation.decode(a, endian)['values']
        for name, c in _lid_channels().items():
            out[name] = max(out[name], float(np.degrees(np.abs(v[:, c, 2]).max())))   # (the angle about its axis)
    return out


def lid_scales(lids, donor_turns):
    """{eyelid joint: scale} of the fighter's lid turns (tekken7_lids) over the donor's, one scale for both eyes' upper
    lids and one for their lower lids (both sides' largest turns: the eyes blink alike; a side's own largest is often
    a one-sided expression); scales within SAME_SCALE of 1 left out."""
    out = {}
    for pair in (LIDS[:2], LIDS[2:]):
        mine, theirs = max(lids.get(n, 0.0) for n in pair), max(donor_turns.get(n, 0.0) for n in pair)
        if mine > 0 and theirs > 0:
            s = float(np.clip(mine / theirs, *LID_SCALES))
            if abs(s - 1) > SAME_SCALE:
                out.update(dict.fromkeys(pair, s))
    return out


def lid_axes(anims):
    """(axes, turns) of TTT2 face animations [(byte order, bytes)]: axes {eyelid joint: the unit axis, in its parent's
    frame, a positive turn about which closes the eye}, turns {eyelid joint: its largest turn about it (degrees)};
    ({}, {}) without face animations."""
    best = {}
    for endian, a in anims:
        h = animation.header(a, endian)
        if h['type'] != animation.COMPRESSED or not _is_face(h):
            continue
        v = animation.decode(a, endian)['values'].astype(np.float64)
        for name, c in _lid_channels().items():
            k = int(np.argmax(np.abs(v[:, c, 2])))
            if abs(v[k, c, 2]) > best.get(name, (0.0, None))[0]:
                # (the game turns a joint by -z about rotation_axis: animation.local_rotation)
                best[name] = (abs(v[k, c, 2]), animation.rotation_axis(v[k, c]) * -np.sign(v[k, c, 2]))
    if len(best) < len(LIDS):
        return {}, {}
    return ({name: x / np.linalg.norm(x) for name, (_, x) in best.items()},
            {name: float(np.degrees(t)) for name, (t, _) in best.items()})


def _on_joint(model, joint):
    """(bind positions (n, 3), weights (n,)) of the model's (nud.read) vertices weighted to bone `joint`."""
    pos, weight = [np.zeros((0, 3))], [np.zeros(0)]
    for mesh in model['meshes']:
        for p in mesh['polys']:
            v = p['verts']
            if 'bones' not in (v.dtype.names or ()):
                continue
            w = np.asarray(v['w'], np.float64)
            w = (w * (np.asarray(v['bones']) == joint)).sum(1) / np.maximum(w.sum(1), 1e-9)   # (u8: 255ths)
            pos.append(np.asarray(v['pos'], np.float64)[w > 0])
            weight.append(w[w > 0])
    return np.concatenate(pos), np.concatenate(weight)


def _turned(axis, degrees):
    """The rotation matrix of `degrees` about the unit `axis` (column vectors)."""
    a = np.radians(degrees)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(a) * k + (1 - np.cos(a)) * k @ k


def lid_motion(model, skel, axes, turns):
    """(opening, rates) of a face's eyes as the game skins them (each vertex the linear blend of its bones): opening =
    the degrees, about the upper lid's axis, from the upper lid's lowest margin point to the lower lid's highest in the
    middle of the eye; rates {eyelid joint: the degrees its margin points there close (median) per degree the joint
    turns, at turns[joint]}; both the mean over the eyes. (None, {}) when no eye's lids are found. model: nud.read's,
    skel: bone.read's (lid joints with no bind turn, as TTT2's), axes / turns: lid_axes'."""
    names, world = _names(skel), bone.world_matrices(skel)
    openings, rates = [], {}
    for upper, lower in zip(LIDS[:2], LIDS[2:]):
        if upper not in names or lower not in names:
            continue
        lids = {}                               # joint: (pivot, closing axis (world), margin points, their weights)
        for name in (upper, lower):
            j = names.index(name)
            axis = world[skel['parent'][j]][:3, :3] @ axes[name]
            x, w = _on_joint(model, j)
            keep = w >= MARGIN * w.max() if len(w) else w > 0
            lids[name] = (world[j][:3, 3], axis / np.linalg.norm(axis), x[keep], w[keep])
        if not len(lids[upper][2]) or not len(lids[lower][2]):
            continue
        pivot, axis = lids[upper][:2]
        # angles about the upper lid's axis, from the lids' mean direction, the upper lid's side positive
        f = np.concatenate([lids[upper][2], lids[lower][2]]).mean(0) - pivot
        f -= axis * (f @ axis)
        f /= np.linalg.norm(f)
        g = np.cross(axis, f)

        def polar(x):
            q = x - pivot
            return q @ axis, np.degrees(np.arctan2(q @ g, q @ f)), np.hypot(q @ g, q @ f)
        (lu, au, ru), (ll, al, rl) = polar(lids[upper][2]), polar(lids[lower][2])
        side = 1.0 if np.median(au) > np.median(al) else -1.0
        au, al = side * au, side * al
        span = np.concatenate([lu, ll])
        mid, half = (span.min() + span.max()) / 2, MIDDLE * (span.max() - span.min()) / 2
        su, sl = np.abs(lu - mid) <= half, np.abs(ll - mid) <= half
        if not su.any() or not sl.any():
            continue
        su &= ru >= FRONT * ru[su].max()
        sl &= rl >= FRONT * rl[sl].max()
        openings.append(au[su].min() - al[sl].max())
        for name, sel, sense in ((upper, su, -side), (lower, sl, side)):
            pv, ax, x, w = lids[name]
            x, w = x[sel], w[sel]
            moved = (1 - w)[:, None] * x + w[:, None] * ((x - pv) @ _turned(ax, turns[name]).T + pv)
            closed = sense * (polar(moved)[1] - polar(x)[1])
            rates.setdefault(name[2:], []).append(float(np.median(closed)) / turns[name])
    if not openings:
        return None, {}
    return float(np.mean(openings)), {name: float(np.mean(r)) for name, r in rates.items()}


def lid_turns_on_meshes(model, skel, donor_model, donor, anims):
    """{eyelid joint: scale} of the donor's lid turns for the face of `model` / `skel` (NUD bytes or nud.read's /
    bone.read's), so that each lid closes the same share of the eye's opening as the donor's does (lid_motion, at the
    donor's largest turns): the donor's rate over the fighter's, times the fighter's opening over the donor's; one
    scale for both eyes' upper lids and one for their lower lids, within LID_SCALES; scales within SAME_SCALE of 1
    left out, {} when either face's lids are not found."""
    model, donor_model = (nud.read(m) if isinstance(m, (bytes, bytearray)) else m for m in (model, donor_model))
    axes, turns = lid_axes(anims)
    if not axes:
        return {}
    (mine, my_rates), (theirs, their_rates) = (lid_motion(model, skel, axes, turns),
                                               lid_motion(donor_model, donor, axes, turns))
    out = {}
    for pair in (LIDS[:2], LIDS[2:]):
        key = pair[0][2:]                       # (the rates go by lid, both eyes': 'UwaMabuta_Joint', ...)
        # (a rate below 0: the donor's largest turn of that lid opens the eye; the same axis for both faces)
        if not mine or not theirs or my_rates.get(key, 0) * their_rates.get(key, 0) <= 0:
            continue
        s = float(np.clip(their_rates[key] / my_rates[key] * mine / theirs, *LID_SCALES))
        if abs(s - 1) > SAME_SCALE:
            out.update(dict.fromkeys(pair, s))
    return out


def _with_mota(moveset, slot, mota):
    """The moveset with its MOTA slot `slot` replaced (the MOTAs after it moved along)."""
    slots = list(struct.unpack_from('>13I', moveset, 0x1D8))
    start = slots[slot]
    end = min([o for o in slots if o > start], default=len(moveset) - motbin.BASE)
    mota = bytes(mota) + bytes(-len(mota) % 4)
    out = bytearray(moveset[:motbin.BASE + start]) + mota + moveset[motbin.BASE + end:]
    for k, o in enumerate(slots):
        if o > start:
            struct.pack_into('>I', out, 0x1D8 + 4 * k, o + len(mota) - (end - start))
    return bytes(out)


def retarget(moveset, pack, skel, donor, lids=None, meshes=None):
    """The fighter's moveset (motbin bytes) and motion pack with their face animations moved for its face joints and
    their eyelids turned as its own game turns them (skel: its skeleton, donor: the donor's, bone.read; lids: its
    tekken7_lids; without them, meshes: (its model, the donor's: NUD bytes or nud.read's) for lid_turns_on_meshes
    (Tekken 8); neither: the donor's turns kept) -> (moveset, pack, face animations changed, {eyelid joint: scale})."""
    moves = offsets(skel, donor)
    slot, = struct.unpack_from('>I', moveset, 0x1D8 + 4 * MOTBIN_SLOT)
    at, size = motion.pack_items(pack)[PACK_ITEM]
    motas = {}                    # 'moveset' / 'pack': (MOTA start, its byte order, entries, animations: _animations)
    if slot:
        used = [o for o in struct.unpack_from('>13I', moveset, 0x1D8) if o > slot]
        end = motbin.BASE + (min(used) if used else len(moveset) - motbin.BASE)
        motas['moveset'] = (motbin.BASE + slot,) + _animations(moveset, motbin.BASE + slot, end)
    motas['pack'] = (at,) + _animations(pack, at, at + size)
    face_anims = [(e, a) for _, e, _, anims in motas.values() for a in anims]
    if lids:
        scales = lid_scales(lids, _donor_lids(face_anims))
    elif meshes is not None:
        scales = lid_turns_on_meshes(meshes[0], skel, meshes[1], donor, face_anims)
    else:
        scales = {}
    turns = {_lid_channels()[name]: s for name, s in scales.items()}
    if not moves and not turns:
        return moveset, pack, 0, scales
    changed = 0
    for where, (start, endian, entries, anims) in motas.items():
        out = []
        for a in anims:
            h = animation.header(a, endian)
            if not _is_face(h):
                out.append(a)
                continue
            a = bytearray(a)
            _move(a, h, moves, endian)
            if turns and h['type'] == animation.COMPRESSED:
                a = _turn(bytes(a), h, turns, endian)
            out.append(bytes(a))
            changed += 1
        container = moveset if where == 'moveset' else pack
        mota = _mota(container[start:start + 0x14], entries, out)
        if where == 'moveset':
            moveset = _with_mota(moveset, MOTBIN_SLOT, mota)
        else:
            items = [pack[o:o + s] for o, s in motion.pack_items(pack)]
            items[PACK_ITEM] = mota
            pack = motion.build_pack(items)
    return moveset, pack, changed, scales


def same_joints(bon, reference):
    """A preset outfit's skeleton (BONE bytes) with the face joints of the fighter's own (reference): the outfits
    share its face animations, moved for its face joints."""
    skel, ref = bone.read(bon), bone.read(reference)
    mine, theirs = _names(skel), _names(ref)
    t = skel['t'].copy()
    for name in skeleton.FACE:
        if name in mine and name in theirs:
            t[mine.index(name)] = ref['t'][theirs.index(name)]
    if np.array_equal(t, skel['t']):
        return bon
    skel['t'] = t
    return bone.write(skel)
