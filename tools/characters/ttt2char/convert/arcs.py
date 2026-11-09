"""Tekken 7's 2D (Street Fighter style) jumps and air moves -> TTT2.

Tekken 7 moves a few fighters (Akuma, Eliza; also Geese and Noctis) through the air by physics instead of by
their animations: move property 0x8226, value bytes (A, B, C, 0), starts an arc with take-off speed A mm/frame and
gravity B/10 mm/frame^2 (C: the horizontal speed in percent, 100 on the jumps, which keep their horizontal speed in
the move's 'distance' field as in TTT2). B = 60 is TTT2's own gravity (6.0). It fires on the frame the jump's
animation reaches its flat airborne pose (frame 9 neutral, 5 forward and back); the animation then holds that pose
(its hips stay at one height) and the move holds its last frame (airborne_end == ground_fall == the last frame)
until the arc lands, then its landing cancel runs. An air move cancelled out of the jump (0x8227 at frame 0x8001:
air normals, air specials) continues the arc; one with its own 0x8226 (a dive kick: A = 0, B = 120..220) starts a
new one where the fighter is.

TTT2 has neither (its property interpreter does nothing with 0x8226; its jumps carry their arcs in the animation's
hips channel, the fighter's own height stays 0), so:

* a move that starts the arc on the ground (the jumps, Akuma's hyakki) plays a new raw animation: its Tekken 7
  animation with the arc added to the hips height from the 0x8226 frame on (n = frame - f0: y = n A - g n (n + 1)
  / 2, the sum TTT2's physics would make), extended until the arc lands by repeating the held frame; its
  airborne_end, ground_fall and landing cancels move by the frames added. Forward and back jumps whose Tekken 7
  animations are deltas ("_sabun" over the neutral jump; Akuma) get the delta made absolute first: its rotations
  are absolute, its hips height between the take-off and the last two frames is relative to the neutral jump's
  air height. So does an animation of no such name whose hips turn relative at the arc's frame (Akuma's Demon
  Flip: relative_hips). Such a move also gets 0x822D at frame 0x8001 (value A, B, C, f0) so the runtime knows the
  arc when an air move is cancelled out of it.
* 0x8227 becomes 0x822C at frame 0x4001 (every frame from 1 on: a cancel may start a move past its frame 1), and an
  air move's 0x8226 stays as it is. The runtime (runtime/src/title/roster.cpp, "2D arcs") flies those moves with
  the fighter's own height and vertical speed, holds them on their ground_fall frame and lands them.

TTT2's property interpreter ignores 0x8226, 0x822C and 0x822D, and no TTT2 moveset uses them.

Tekken 8 flies Clive Rosfield's jumps and air moves the same way, with the ids 0x8296 (an arc, the same value bytes:
his jumps 110, 60, 100 at frame 9) and 0x8297 (at frame 0x8001: this air move continues the arc); its other fighters
carry their jumps' arcs in their animations, as TTT2 does. They convert as Tekken 7's do, and then the air moves are
baked too (moveset.bake_air8): TTT2 turns a queued cancel's pose toward the next move's first frame before that move
starts, and with the jump's arc baked and the air attack's not (its hips flat: physics lifted it) u/f+1 pressed early
sank him from 1.9 m to 1.0 m by its jump frame 17, then he leapt back up. Each way into an air move (a cancel of a baked
move, at its start frame) gives the height, vertical speed and gravity it starts with; fly() flies it from there as
the runtime would, its own 0x8226 restarting the arc, and bake_air() puts that in its hips: held on its ground_fall
frame until the touchdown or, landing before it, cut to it there (the runtime goes to ground_fall at the touchdown).
An air move whose clip a ground move goes on with (moveset.CONTINUE8: Burning Rain's slam, its landing the same clip
from frame 30) is on the floor by its ground_fall, its flight brought down to it (land_by).
"""
import re

import numpy as np

from ..ttt2 import animation as A

ARC, AIR_MOVE = 0x8226, 0x8227            # Tekken 7: start an arc; this air move continues the arc
ARC8, AIR_MOVE8 = 0x8296, 0x8297          # Tekken 8's
BAKED, AIR_MARK = 0x822D, 0x822C          # TTT2 (no-op ids): a baked ground arc; a 2D air move
AIR_MARK_FRAME, BAKED_FRAME = 0x4001, 0x8001


def height(n, a, g):
    """The arc's height n frames after its start (TTT2's integration: vy -= g, then y += vy, once a frame)."""
    return n * a - g * n * (n + 1) / 2.0


def touchdown(a, g):
    """Frames from the arc's start to its landing (height <= 0)."""
    n = 1
    while height(n, a, g) > 0:
        n += 1
    return n


def params(value):
    """0x8226's value -> (A take-off speed, g gravity, C horizontal %)."""
    value &= 0xFFFFFFFF
    return value >> 24, ((value >> 16) & 0xFF) / 10.0, (value >> 8) & 0xFF


def is_ground_arc(air, frame):
    """An arc to bake: the move starts on the ground (not an air move) and the arc's frame is a move frame."""
    return not air and frame < 0x4000


def decode_t7(k, off):
    return A.decode(k.animbuf[off:off + k.anim_size[off]], '<')


def absolute_sabun(delta, whole):
    """A "_sabun" animation (decoded) made absolute against the whole animation it is a delta of: its hips height
    (channel 1 y) is relative to the whole's flat air height on the frames where it is small (the airborne
    frames; the take-off and the landing frames are absolute)."""
    wy = whole['values'][:, 1, 1]
    base = float(np.median(wy[wy > 0.8 * wy.max()]))
    v = delta['values'].copy()
    rel = np.abs(v[:, 1, 1]) < 0.5 * base
    v[rel, 1, 1] += base
    return dict(delta, values=v), base, int(rel.sum())


def relative_hips(dec, f0):
    """Whether an animation's hips height (decoded: channel 1 y) is relative from the arc's frame f0 on, as the
    "_sabun" jumps' airborne frames are: under half the frame before's (Akuma's Demon Flip, mxyt_sp_100ki: 898 mm,
    then 11). The animations that hold their flat airborne pose (the other 2D fighters' jumps) keep their height."""
    y = dec['values'][:, 1, 1]
    return 1 <= f0 < len(y) and y[f0 - 1] > 0 and abs(float(y[f0])) < 0.5 * float(y[f0 - 1])


def bake(dec, f0, a, g, hold):
    """(descriptors, values (frames', nch, 3), frames added) of a raw animation: dec (decoded) with the arc from
    frame f0 added to the hips height, the frame `hold` repeated until the arc lands."""
    values = A.to_raw(dec['descriptors'], dec['values'], dec['type'])
    desc = [7 if A.is_rotation(d) and dec['type'] != A.RAW else d for d in dec['descriptors']]
    frames = dec['frames']
    hold = min(hold, frames - 1)
    ext = max(0, f0 + touchdown(a, g) - hold)
    out = np.concatenate([values[:hold + 1]] + [values[hold:hold + 1]] * ext + [values[hold + 1:]], 0).copy()
    for f in range(f0, out.shape[0]):
        out[f, 1, 1] += max(0.0, height(f - f0, a, g))
    return desc, out.astype(np.float32), ext


def whole_name(sabun_name):
    return re.sub(r'_[fb]_sabun', '', sabun_name, flags=re.I)


def encode(descriptors, values):
    """The raw TTT2 (big-endian) animation."""
    return A.encode_raw(descriptors, values, '>')


def fly(y, vy, g, restarts, limit=600):
    """[(height, vertical speed, gravity)] of an air move's frames from 0 to its touchdown, flown from its frame 0
    with the state it was entered with: each frame vy -= g, then y += vy (TTT2's integration, as height()), then the
    move's own arcs at that frame (restarts {frame: (A, g)}) start (vy = A); the last frame is the touchdown (height
    <= 0, made 0)."""
    out = []
    for k in range(limit):
        if k:
            vy -= g
            y += vy
            if y <= 0:
                out.append((0.0, 0.0, g))
                break
        if k in restarts:
            vy, g = restarts[k]
        out.append((y, vy, g))
    return out


def land_by(flight, t):
    """fly()'s flight brought down to touch down at frame t (< its own touchdown): its heights less a ramp from 0 at
    frame 0 to its height at t (an arc stays above the ramp: no frame goes under the floor), the speeds their steps."""
    top = flight[t][0]
    ys = [y - top * k / t for k, (y, _, _) in enumerate(flight[:t])]
    return [(y, y - ys[k - 1] if k else flight[0][1], flight[k][2]) for k, y in enumerate(ys)] + \
        [(0.0, 0.0, flight[t][2])]


def bake_air(dec, heights, hold):
    """(descriptors, values (frames', nch, 3), shift) of a raw animation: dec (decoded) with `heights` (one a frame
    from frame 0, the last the touchdown: fly()) added to the hips height, timed as the runtime flies an air move: the
    frame `hold` (its ground_fall) repeated until the touchdown, or, landing before it, the frames from the touchdown
    to it left out (the touchdown shows the frame `hold`). shift: the frames added at `hold` (< 0: left out)."""
    values = A.to_raw(dec['descriptors'], dec['values'], dec['type'])
    desc = [7 if A.is_rotation(d) and dec['type'] != A.RAW else d for d in dec['descriptors']]
    hold = min(hold, dec['frames'] - 1)
    t = len(heights) - 1
    shift = t - hold
    if shift >= 0:
        out = np.concatenate([values[:hold + 1]] + [values[hold:hold + 1]] * shift + [values[hold + 1:]], 0).copy()
    else:
        out = np.concatenate([values[:t], values[hold:]], 0).copy()
    out[:t + 1, 1, 1] += np.asarray(heights, np.float32)
    return desc, out.astype(np.float32), shift


def moved(frame, hold, shift, held=False):
    """A move frame after bake_air() (hold, shift): past `hold` (from it on: held=True, ground_fall and
    airborne_end) it moves by `shift`; cut (shift < 0), the frames left out come at the touchdown."""
    if shift >= 0:
        return frame + shift if frame > hold or (held and frame == hold) else frame
    t = hold + shift
    return frame if frame < t else t if frame < hold else frame + shift

