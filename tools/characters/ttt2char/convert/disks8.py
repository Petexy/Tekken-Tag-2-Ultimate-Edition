"""Tekken 8's big slash arcs (a definition's TEKKEN8_DISKS) as TTT2 effects.

Some Tekken 8 fighters' swings do not draw their sword's ribbon only (trails8.py): a move spawns a Niagara system whose
emitters are one still mesh, a band of about 255 degrees round its middle (the size in the system's User.Scale, metres a
1), whose materials move a streaked mask along it: at a time t its picture at the place (u across the band, v along it)
is Mask(u, v + s(t)), with s falling fast until the mask's head (its V 1) has run to the band's far end, then slowly until
it fades. So: one model particle, the band baked in the fighter's level facing frame at his hips when the move spawns it
(as trails8 does, so it stays in the air), and a texture that scrolls along V: first fast, then slowly.

The band lies where the rows in front of a spawn put it: EFFECT8_OFFSET (up, forward, sideways in mm from the fighter's
chest bone, a little above the hips, in the axes of the clip: its turn does not count) and two rows of turns: first about
the forward axis, then up, then sideways, the disk flat at no turns. Its head starts behind him in the disk's own frame and
runs the way its id says (a definition's 'ways'). (A spawn without those rows: the circle through the blade's far end, from
the move's clip, and the blade's way round it.)

The materials' graphs are cooked: the layers are combined as their parameters' names say, their colours by Tekken 8's
frames. Written for this project from the files themselves (no third-party code).
"""
import copy
import math

import numpy as np

from . import missiles8, particles as P, strips, trails8
from ..tekken8 import material as material8, texture as texture8
from ..ttt2 import alo, nud

ACROSS, ALONG = 512, 1024           # the look's size
SPREAD = 2.5                        # the texture's height in mask lengths (clear beyond 1: its samplers repeat)
ARC = 255.0                         # the band's angle (degrees)
INNER = 0.3                         # the band's inner radius, a share of the outer
START = 0.85                        # the mask's place at the start (s(0): its head enters the band's first 15 %)
SLOW = 0.0255                       # s's fall per frame after the head's run (the material's parameter by Niagara's script)
HEAD_RATE = 0.1075                  # ... and in the run: 27 degrees a frame, what a blade makes of it comes from its clip
RATES = 14.0, 60.0                  # degrees a frame a band's head may run
HOLD, FADE = 16, 5                  # frames after the head's run until it starts fading, and to gone
SWING_FRAMES = 14                   # the frames from the spawn in which the blade's way is looked for
SEGMENTS = 96                       # slices along the band
ROWS = 7                            # rows of vertices across it
TEXTURE_SIDE = 1024                 # the mip of Tekken 8's textures it is baked from
BONE_ABOVE_HIPS = 150.0             # the height (mm) of the bone a spawn's place counts from, over the hips
HEAD_START = -75.0                  # where a band's head is at the start, degrees in its disk's frame from x towards z


def _image(store, path, cache):
    """A texture as float RGBA (its colour as stored: masks are data)."""
    if path not in cache:
        t = texture8.Texture2D(store, material8.package_of(path))
        cache[path] = t.decode(TEXTURE_SIDE).astype(np.float32) / 255.0
    return cache[path]


def _sample(img, u, v, wrap=False):
    return trails8._sample(img, u, v, wrap=wrap)


def _over(rgb, alpha, colour, opacity):
    """A layer over what is there, straight alpha."""
    out = opacity + alpha * (1.0 - opacity)
    c = colour * opacity[..., None] + rgb * (alpha * (1.0 - opacity))[..., None]
    return c / np.maximum(out, 1e-4)[..., None], out


def ink_look(store, tex, along=ALONG, across=ACROSS, colours=None, density=0.88, bolts=1.0, water=0.8):
    """A band of dark ink with pale water and red lightning. tex: {'streaks', 'wedge', 'cells', 'noise', 'lightning',
    'marble'}: texture paths -> RGBA 0 .. 255 (y 0 is the mask's head). colours: other colours for its INK, WATER, BOLT,
    BOLT_HOT and LINE."""
    INK, WATER, BOLT, BOLT_HOT, LINE = colours or INK_COLOURS
    cache = {}
    y = (np.arange(along, dtype=np.float32) + 0.5) / along * SPREAD
    q = (np.arange(across, dtype=np.float32) + 0.5) / across
    m, u = np.meshgrid(1.0 - y, q, indexing='ij')
    inside = (m >= 0.0) & (m <= 1.0)
    img = lambda k: _image(store, tex[k], cache)
    streaks = _sample(img('streaks'), u, m)[..., 0]
    wedge = _sample(img('wedge'), u, m)[..., 0]
    noise = _sample(img('noise'), u, m * 2.0 - 0.6, wrap=True)[..., 0]
    cells = _sample(img('cells'), u, m * 2.0, wrap=True)[..., 0]
    bolt = _sample(img('lightning'), u * 1.5, m * 2.0, wrap=True)[..., 0]
    marble = _sample(img('marble'), u * 3.0, m * 0.35, wrap=True)[..., 0]      # (long along the band: it erodes the ink)
    fine = _sample(img('streaks'), (u * 2.3 + 0.13) % 1.0, m * 0.8 + 0.2)[..., 0]
    rgb = np.zeros(m.shape + (3,), np.float32)
    alpha = np.zeros(m.shape, np.float32)
    # the ink: black, streaked; where it is thin the sky shows through as slate
    a = np.clip(streaks * (0.45 + 0.75 * fine) * (0.55 + 1.3 * marble), 0.0, 1.0) * density
    rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(INK, np.float32), rgb.shape), a)
    # the pale water in its wake
    a = np.clip(wedge * np.clip(noise * 2.0, 0.0, 1.0) * np.clip(cells * 5.0, 0.0, 1.0) * 1.4 - 0.12, 0.0, water)
    rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(WATER, np.float32), rgb.shape), a)
    # the lightning: thicker than its texture (a thread would flicker at this size), with a red glow
    wide = _spread(bolt, 2)
    among = np.clip(streaks * 2.5 + wedge * 0.25 - 0.1, 0.0, 1.0)
    glow = np.clip((wide - 0.12) * 1.6, 0.0, 0.55) * np.clip(noise * 3.0 - 0.3, 0.0, 1.0) * among * bolts
    rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(BOLT, np.float32), rgb.shape), glow)
    a = np.clip((bolt - 0.22) * 3.5, 0.0, 1.0) * np.clip(noise * 3.0 - 0.3, 0.0, 1.0) * among * bolts
    rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(BOLT_HOT, np.float32), rgb.shape), a)
    # the thin line round the far rim
    line = np.exp(-(((1.0 - u) * across - 3.0) / 1.5) ** 2) * np.clip(m * 1.5, 0.0, 1.0)
    rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(LINE, np.float32), rgb.shape), line)
    alpha = alpha * inside * np.minimum(1.0, u * across / 2.0)
    return np.round(np.dstack([rgb, alpha]) * 255.0)


def _spread(img, n):
    """A greyscale image's maximum over its neighbours, n texels round."""
    out = img
    for axis in (0, 1):
        for k in range(1, n + 1):
            out = np.maximum(out, np.maximum(np.roll(img, k, axis), np.roll(img, -k, axis)) * (1.0 - k / (n + 1.0)))
    return out


def fire_look(store, tex, along=ALONG, across=ACROSS, smoke=True):
    """A band of fire: black smoke with embers in its tail (when `smoke`: a system with an emitter for it), flames towards its
    head, a white-hot line round the far rim."""
    cache = {}
    y = (np.arange(along, dtype=np.float32) + 0.5) / along * SPREAD
    q = (np.arange(across, dtype=np.float32) + 0.5) / across
    m, u = np.meshgrid(1.0 - y, q, indexing='ij')
    inside = (m >= 0.0) & (m <= 1.0)
    img = lambda k: _image(store, tex[k], cache)
    streaks = _sample(img('streaks'), u, m)[..., 0]
    fine = _sample(img('streaks'), (u * 2.3 + 0.13) % 1.0, m * 0.8 + 0.2)[..., 0]
    wedge = _sample(img('wedge'), u, m)[..., 0]
    flame = _sample(img('flame'), u * 3.1, m * 2.4, wrap=True)[..., 0]      # (finer across than along: they streak)
    licks = _sample(img('flame2'), u * 5.0 + 0.3, m * 1.3, wrap=True)[..., 0]
    cells = _sample(img('cells'), u, m, wrap=True)[..., 0]
    rgb = np.zeros(m.shape + (3,), np.float32)
    alpha = np.zeros(m.shape, np.float32)
    # the smoke inside the flames: a faint grey haze, streaked, near the band's head only (it thins to the line behind
    # it), and what still burns in it (by Tekken 8's frames: the fighter behind it stays in sight)
    if smoke:
        band = np.exp(-((u - FIRE_SMOKE_AT) / FIRE_SMOKE_WIDE) ** 2) * trails8._step(*FIRE_SMOKE_HEAD, m)
        body = FIRE_SMOKE_BODY * trails8._step(0.0, 0.3, m)
        a = np.clip((body + streaks * (0.45 + 0.75 * fine) * 1.5) * band, 0.0, 1.0) * FIRE_SMOKE_ALPHA
        rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(FIRE_SMOKE, np.float32), rgb.shape), a)
        a = np.clip(cells * 6.0 - 0.3, 0.0, 1.0) * np.clip(flame * 3.0 - 0.3, 0.0, 1.0) * np.clip(streaks * 3.0, 0.0, 1.0) * band
        rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(EMBER, np.float32), rgb.shape), a * FIRE_EMBERS)
    # the flames: wisps round the hot line, over its first part most, the colours of a fire by how bright its texture is
    # (a ring with smoke: Tekken 8's are a bright orange line with licks off it, a line's thinner still: the colours of FLAME)
    ramp, gain, wide = (FIRE_FLAME, FIRE_GAIN, FIRE_WIDE) if smoke else (FLAME, 2.6, 0.07)
    t = np.clip(flame * (0.3 + 1.3 * licks) * gain * (0.25 + wedge) * (0.25 + 1.0 * trails8._step(0.15, 0.8, m)), 0.0, 1.0)
    colour = np.stack([np.interp(t, ramp[0], c) for c in ramp[1:]], -1).astype(np.float32) / 255.0
    a = np.clip((t - 0.24) * 3.5, 0.0, 1.0) * np.exp(-((u - FIRE_LINE_AT + 0.05) / wide) ** 2)
    rgb, alpha = _over(rgb, alpha, colour, a)
    # the hot line
    at = (FIRE_LINE_AT - u) * across
    line = np.exp(-(at / 3.5) ** 2) * trails8._step(0.05, 0.5, m)
    glow = np.exp(-(at / 12.0) ** 2) * trails8._step(0.2, 0.7, m) * 0.6
    rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(RIM_GLOW, np.float32), rgb.shape), glow)
    rgb, alpha = _over(rgb, alpha, np.broadcast_to(np.array(RIM_HOT, np.float32), rgb.shape), line)
    alpha = alpha * inside * np.minimum(1.0, u * across / 2.0)
    return np.round(np.dstack([rgb, alpha]) * 255.0)


FIRE_LINE_AT, FIRE_SMOKE_AT = 0.86, 0.6                         # across a band: its hot line and its smoke, by Tekken 8's frames
FIRE_SMOKE_WIDE, FIRE_SMOKE_ALPHA = 0.1, 0.42                   # (its smoke a faint grey haze with embers in it, inside the line,
FIRE_SMOKE_BODY = 0.2                                           # strongest at the band's head, gone by its tail: an opaque black
FIRE_SMOKE_HEAD = (0.35, 0.85)                                  # band hid the fighter behind it; by Tekken 8's frames)
FIRE_SMOKE = (0.17, 0.15, 0.14)
FIRE_EMBERS = 0.5
FIRE_WIDE, FIRE_GAIN = 0.11, 3.2    # how far a ring's flames reach either side of its line (a share of the band), how hot: by Tekken 8's frames
# a ring's flames: bright orange to white-hot, no dark red (by Tekken 8's frames)
FIRE_FLAME = ((0.0, 0.25, 0.5, 0.75, 1.0), (240, 252, 255, 255, 255), (105, 145, 188, 226, 250), (40, 60, 100, 168, 232))
SMOKE = (0.035, 0.03, 0.03)         # by Tekken 8's frames
EMBER = (0.9, 0.2, 0.06)
RIM_GLOW = (1.0, 0.55, 0.2)
RIM_HOT = (1.0, 0.93, 0.82)
FLAME = ((0.0, 0.25, 0.5, 0.75, 1.0), (190, 240, 255, 255, 255), (55, 100, 155, 205, 245), (45, 75, 115, 175, 230))
STRIPE = ((0.0, 0.5, 1.0), (235, 250, 255), (70, 110, 205), (55, 85, 170))        # coral, a hot core: by Tekken 8's frames
RAMPS = {'fire': FLAME,                                         # by Tekken 8's frames
         'blaze': ((0.0, 0.2, 0.45, 0.7, 1.0), (225, 248, 255, 255, 255), (85, 120, 165, 215, 248), (25, 45, 85, 150, 220)),
         'pink': ((0.0, 0.3, 0.6, 1.0), (120, 215, 245, 255), (60, 95, 155, 235), (200, 180, 235, 255)),
         'wind': ((0.0, 0.3, 0.6, 1.0), (40, 120, 200, 245), (90, 180, 235, 255), (55, 110, 180, 235)),
         'thunder': ((0.0, 0.3, 0.6, 1.0), (90, 150, 215, 250), (60, 110, 190, 245), (190, 245, 255, 255)),
         'sheet': ((0.0, 0.25, 0.5, 0.75, 1.0), (225, 250, 255, 255, 255), (70, 115, 170, 225, 250), (20, 40, 85, 165, 235)),
         'violet': ((0.0, 0.3, 0.6, 1.0), (45, 105, 205, 250), (30, 45, 100, 215), (185, 235, 255, 255)),
         'crimson': ((0.0, 0.3, 0.6, 1.0), (110, 170, 225, 255), (15, 25, 70, 200), (70, 90, 150, 245))}
# by Tekken 8's frames: ink, water, lightning's glow and core, the rim's line. The ink is a translucent slate grey with
# darker streaks, the fighters seen through it (an ink near black at 0.88 drew an opaque dark wheel over them); the
# wind's body a darker grey-green with pale streaks (a pale one was lost against the sky and the snow)
INK_COLOURS = (0.16, 0.18, 0.22), (0.80, 0.88, 0.94), (0.92, 0.22, 0.30), (1.0, 0.78, 0.82), (0.98, 0.62, 0.70)
INK_DENSITY, INK_WATER = 0.55, 0.5
WIND_COLOURS = (0.24, 0.30, 0.28), (0.86, 0.95, 0.92), (0.45, 0.75, 0.45), (0.92, 1.0, 0.86), (0.98, 0.78, 0.55)
WIND_DENSITY = 0.5


# ------------------------------------------------------------------------------------------------ where it lies
def turns(a, b, c):
    """The disk's axes as columns in the fighter's frame (x left, y up, z forward), for a spawn's turns (degrees); its
    normal is the second."""
    a, b, c = math.radians(a), math.radians(b), math.radians(c)
    x = np.array([[1.0, 0.0, 0.0], [0.0, math.cos(b), -math.sin(b)], [0.0, math.sin(b), math.cos(b)]])
    y = np.array([[math.cos(c), 0.0, math.sin(c)], [0.0, 1.0, 0.0], [-math.sin(c), 0.0, math.cos(c)]])
    z = np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]])
    return z @ y @ x


def circle(tips):
    """The circle through points (n, 3): (centre, unit normal, radius), the normal by the right hand rule of the way they
    go; or None when they do not make one (a thrust)."""
    middle = tips.mean(0)
    _, sv, vt = np.linalg.svd(tips - middle)
    if sv[1] < sv[0] * 0.12 or len(tips) < 3:
        return None
    a, b, n = vt
    if np.cross(tips[:-1] - middle, tips[1:] - middle).sum(0) @ n < 0.0:
        n, b = -n, -b
    x, y = (tips - middle) @ a, (tips - middle) @ b
    m = np.column_stack([2.0 * x, 2.0 * y, np.ones_like(x)])
    (cx, cy, c), *_ = np.linalg.lstsq(m, x * x + y * y, rcond=None)
    radius = math.sqrt(max(c + cx * cx + cy * cy, 1.0))
    return middle + cx * a + cy * b, n, radius


class Sampler:
    """The swings of a fighter's moves: (move, frame of the spawn, Tekken 8 id) -> a band for the effect ({'band': ...}:
    centre, axes, radius of the blade's circle in the effect's frame), or None. trails: its trails8.Sampler (the clips);
    a definition's TEKKEN8_DISKS {'looks': {id: look}, 'ways': {id: 1 or -1, the way its head runs round the disk's normal},
    'blades': ((weapon's bone, far end in mm in its frame), ..), 'turns': {id: (a, b, c), when its rows place it but do not turn it}, 'source': where
    the looks' pictures come from: {'ink', 'flames', 'feathers', 'bolts': a Tekken 8 id each, 'emitters': {role: its emitter's
    name's start}}}."""

    def __init__(self, trails, spec):
        self.trails, self.spec = trails, spec
        self.blades = [(trails.weapons[bone], np.asarray(reach, np.float64)) for bone, reach in spec['blades']]
        self.weapon, self.reach = self.blades[0]

    def __call__(self, move, start, eid, place=None, anchor=None):
        """place: what the rows in front of the spawn say, ((up, forward, sideways), (a, b, c)), or None; anchor: where
        Tekken 8 spawns it, ('part', n) or ('weapon', hi), or None."""
        values = self.trails.clip(move)
        if values is None:
            return None
        first = max(0, start - 1)
        look = self.spec['looks'][eid]
        if place is not None and not any(place[1]) and eid in self.spec.get('turns', ()):   # (no row turns it: its own emitter does)
            place = (place[0], self.spec['turns'][eid])
        if not isinstance(look, str):                       # (a burst of flames over a body in a clip: burst)
            made = self.body(values, first, eid, look, place)
            if made is not None and look[0] in ANCHORED and 'anchors' in self.spec:
                self.anchored(made, values, first, look, anchor, place, move, start)
            return made
        R0, p0 = trails8.level_frame(values, self.trails.skeleton, first)
        if place is not None:                               # (the same place in the same turn: one effect for all the moves)
            return dict(band=self.placed(R0, place, self.spec['ways'].get(eid, -1), look, move, start), id=eid,
                        key=('disk', eid, place, tuple(np.round(R0[0], 1))))
        last = min(len(values) - 1, first + SWING_FRAMES)
        if last - first < 3:
            return None
        ways = []
        for weapon, reach in self.blades:                   # (the hand that swings: the far end that goes furthest)
            R, t = trails8.weapon_frames(self.trails.conv, self.trails.skeleton, values[first:last + 1], weapon)
            ways.append(t + np.einsum('fij,j->fi', R, reach))
        far = max(ways, key=lambda w: np.linalg.norm(w[1:] - w[:-1], axis=1).sum())
        speed = np.linalg.norm(far[1:] - far[:-1], axis=1)
        fast = np.flatnonzero(speed > speed.max() * 0.3)
        if not len(fast):
            return None
        got = circle(far[fast[0]:fast[-1] + 2])
        if got is None:
            return None
        centre, normal, radius = got
        out = lambda x: (x - p0) @ R0
        centre, normal = out(centre), normal @ R0
        along = out(far)
        seen = along - centre
        seen = seen - np.outer(seen @ normal, normal)
        ex = seen[0] / max(np.linalg.norm(seen[0]), 1e-3)
        ey = np.cross(normal, ex)
        angles = np.unwrap(np.arctan2(seen @ ey, seen @ ex))
        if angles[min(fast[-1] + 1, len(angles) - 1)] < angles[0]:      # (the blade's way round is the head's)
            normal, ey, angles = -normal, -ey, -angles
        frames = min(8, len(angles) - 1)
        rate = math.degrees(abs(angles[frames] - angles[0])) / frames
        return dict(band=dict(centre=centre, ex=ex, ey=ey, radius=radius, rate=float(np.clip(rate, *RATES)), look=look, source=self.spec['source'],
                              move=move, start=start), id=eid)

    def placed(self, R0, place, way, look, move, start):
        """A band where the rows in front of its spawn put it, in the effect's frame (the clip's, turned by R0)."""
        (up, forward, sideways), angles = place
        M = turns(*angles)
        at = math.radians(HEAD_START)
        return dict(centre=np.array((sideways, up + BONE_ABOVE_HIPS, forward), np.float64) @ R0,
                    ex=(M @ np.array((math.cos(at), 0.0, math.sin(at)))) @ R0,
                    ey=(M @ np.array((-math.sin(at), 0.0, math.cos(at)))) @ R0 * way,
                    radius=0.0, rate=HEAD_RATE * ARC, look=look, source=self.spec['source'], move=move, start=start)

    def body(self, values, first, eid, look, place=None):
        """A burst: {'burst': (recipe, frames), 'id', 'far', 'near' (F, 3) the blade, 'joints': {name: (F, 3)}} in the effect's
        frame."""
        last = min(len(values) - 1, first + BURST_FRAMES)
        skeleton = self.trails.skeleton
        _, Wp = trails8.retarget.pose(skeleton, values[first:last + 1, :23], trails8.animation.COMPRESSED)
        R, t = trails8.weapon_frames(self.trails.conv, skeleton, values[first:last + 1], self.weapon)
        R0, p0 = trails8.level_frame(values, skeleton, first)
        out = lambda x: (x - p0) @ R0
        joints = {n: out(Wp[:, skeleton.index[n]]) for n in JOINTS if n in skeleton.index}
        made = dict(burst=tuple(look), id=eid, source=self.spec['source'], far=out(t + np.einsum('fij,j->fi', R, self.reach)), near=out(t),
                    joints=joints, turn=R0)
        if look[0] in ANY_MOVE:                             # (whose place follows no clip: one effect for all the moves)
            made['key'] = ('disk', eid)
        elif look[0] in BOLTS:                              # (on a body part: one effect for all the moves)
            made.update(key=('disk', tuple(look)), part=BOLTS[look[0]][0])
        elif look[0] == 'thunder':                          # (down to the left hand: one effect for all the moves)
            made.update(key=('disk', eid, PART_TE_L), part=PART_TE_L)
        elif look[0] == 'hand':
            part = PART_TE_R if _hand(joints, 0) is joints['TE_R_jnt'] else PART_TE_L
            made.update(key=('disk', eid, part), part=part)
        elif look[0] == 'floor' and place is not None:      # (where the rows say: not over his hips)
            (_, forward, sideways), _ = place
            made.update(at=np.array((sideways, 0.0, forward), np.float64) @ R0, key=('disk', eid, forward, sideways))
        return made

    def anchored(self, made, values, first, look, anchor, place, move, start):
        """A burst on the body part Tekken 8 spawns it at (0x8039's part, 0x839d's weapon; a definition's TEKKEN8_DISKS
        'anchors': {'parts': {Tekken 8 part above LAST_PART: TTT2 part}, 'weapons': {slot: TTT2 part}}: Tekken 8 numbers
        the body's parts 0 .. 21 as TTT2 does, 120 / 121 the hands' holding joints). The runtime moves an effect with its
        part every frame, so a sprite started f frames in starts from where the part is then, in that frame's level
        turn: made['clip'] keeps the clip's points (mm, the clip's own frame) frame by frame from the spawn, the part's
        place and level turns, for burst_files to place each sprite from them (_Placer)."""
        spec = self.spec['anchors']
        kind, n = anchor or ('part', 0)
        if kind == 'part':
            part = n if n <= LAST_PART else spec.get('parts', {}).get(n, 0)
        else:
            part = spec.get('weapons', {}).get(n, PART_TE_R)
        last = min(len(values) - 1, first + BURST_FRAMES)
        skeleton = self.trails.skeleton
        _, Wp = trails8.retarget.pose(skeleton, values[first:last + 1, :23], trails8.animation.COMPRESSED)
        levels = np.array([trails8.animation.local_rotation(values[f, 2], trails8.animation.COMPRESSED)
                           for f in range(first, last + 1)])
        tools = {}
        for name, (bone, reach) in spec.get('tools', {}).items():      # (a weapon's near and far end: the sword, the staff)
            if bone in self.trails.weapons:
                R, t = trails8.weapon_frames(self.trails.conv, skeleton, values[first:last + 1], self.trails.weapons[bone])
                tools[name] = (t, t + np.einsum('fij,j->fi', R, np.asarray(reach, np.float64)))
        made['clip'] = dict(at=Wp[:, part], levels=levels, parts=Wp[:, :LAST_PART + 1], tools=tools, anchor=(kind, n),
                            part=part, place=place)
        made['part'] = part
        from . import bursts8                               # (bursts8 calls this module)
        if bursts8.same_anywhere(look, made['clip']):       # (the same at its part in any move: one effect)
            made['key'] = ('disk', tuple(look), part)
        else:
            made['key'] = (self.trails.k.anim_ref(move)[0], start, 'disk', made['id'], place, part)


# ------------------------------------------------------------------------------------------------ bursts
BURST_FRAMES = 60                   # the frames of a clip a burst may look at
JOINTS = ('KOSHI_jnt', 'MUNE2_jnt', 'ATAMA_jnt', 'TE_R_jnt', 'TE_L_jnt', 'UDE_R_jnt', 'UDE_L_jnt', 'HIJI_R_jnt', 'HIJI_L_jnt',
          'HIZA_R_jnt', 'HIZA_L_jnt', 'ASHI_R_jnt', 'ASHI_L_jnt')
FEET = ('ASHI_R_jnt', 'ASHI_L_jnt')
PART_TE_R, PART_TE_L = 9, 13         # TTT2's body parts
LAST_PART = 21                       # (Tekken 8's body parts up to this one are TTT2's: Sampler.anchored)
# the recipes placed from the part Tekken 8 spawns them at when a definition gives 'anchors' (bursts8.py)
ANCHORED = ('glow', 'glow_right', 'wing', 'wing_right', 'vanish', 'spark', 'blade', 'body', 'cloud', 'appear', 'feet', 'hand', 'jet', 'strike', 'floor', 'pillar', 'ground', 'bolts',
            'bolts_right', 'thunder', 'gust', 'feathers', 'beam', 'zap', 'blast', 'rise', 'niagara', 'column',
            'zan_trail', 'zan_sigil', 'zan_ranbu', 'zan_last', 'updraft', 'updraft_floor', 'heat')
ANY_MOVE = ('feathers', 'gust', 'updraft', 'updraft_floor', 'heat')     # bursts whose place does not follow a clip: one effect for all a fighter's moves
BOLTS = {'bolts': (PART_TE_L, 'thunder', 420.0), 'bolts_right': (PART_TE_R, 'crimson', 280.0)}    # lightning's recipes: body part, colours, size
CHEST = np.array((0.0, 350.0, 0.0))                 # (their middle, from the hips)
FLAME_KEYS = lambda life: [[0, 0.0], [2, 1.0], [life // 2, 0.9], [life, 0.0]]


def blaze_look(store, textures, cell, ramp=None):
    """A tongue of fire: pieces of Tekken 8's fire pictures (textures: fire_textures) stretched upward, narrowing to the top,
    hottest low in the middle. Cell 0 .. 3: another piece each."""
    ramp = ramp or RAMPS['blaze']
    n = 192
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    cache = {}
    off = 0.13 + 0.29 * cell
    at = lambda name, su, sv, o: _sample(_image(store, textures[name], cache), (u * su + o) % 1.0, (v * sv + o * 0.61) % 1.0, True)[..., 0]
    half = 0.12 + 0.34 * v ** 0.8
    shape = np.clip(1.0 - ((u - 0.5) / half) ** 2, 0.0, 1.0) * np.clip(v * 3.0, 0.0, 1.0) * np.clip((1.0 - v) * 3.5, 0.0, 1.0)
    heat = (at('threads', 1.0, 0.42, off) * 1.5 + at('fine', 1.2, 0.5, off + 0.3) * 0.9 + at('cloud', 0.8, 0.35, off + 0.6) * 0.6) * shape * (0.7 + 0.7 * v)
    t = np.clip(heat, 0.0, 1.0)
    rgb = np.stack([np.interp(t, ramp[0], c) for c in ramp[1:]], -1).astype(np.float32) / 255.0
    return np.round(np.dstack([rgb, np.clip(t * 2.0, 0.0, 1.0) ** 1.25]) * 255.0)


def wall_look(store, textures, seed=0.0, ramp=None, side=512, patches=0.0):
    """A fire picture for a mesh: Tekken 8's fire pictures (fire_textures) on the mesh's UV, fading to its edges. seed: where
    in the pictures it starts (each copy of a wall its own). patches: how much of the fire's dim part to leave out."""
    ramp = ramp or RAMPS['blaze']
    v, u = np.meshgrid((np.arange(side, dtype=np.float32) + 0.5) / side, (np.arange(side, dtype=np.float32) + 0.5) / side, indexing='ij')
    cache = {}
    at = lambda name, su, sv, off=0.0: _sample(_image(store, textures[name], cache), (u * su + off) % 1.0, (v * sv + off * 0.61) % 1.0, True)[..., 0]
    across = np.clip(u * 3.0, 0.0, 1.0) * np.clip((1.0 - u) * 3.0, 0.0, 1.0)
    fade = at('edge', 1.0, 1.0) * across ** 1.5
    threads = at('threads', 1.3, 1.1, seed + 0.1)
    fine = at('fine', 1.8, 1.5, seed + 0.4)
    cloud = at('cloud', 1.1, 0.9, seed + 0.7)
    heat = threads * (0.6 + 1.6 * cloud) * (0.7 + 1.2 * fine) * 2.6 * fade     # (where they meet: the fire has holes)
    t = np.clip((heat - patches) / (1.0 - patches), 0.0, 1.0)
    rgb = np.stack([np.interp(t, ramp[0], c) for c in ramp[1:]], -1).astype(np.float32) / 255.0
    return np.round(np.dstack([rgb, trails8._step(0.06, 0.42, t)]) * 255.0)


def stripes_look():
    """Thin horizontal streaks of fire, as Phoenix's shift leaves them in the air (made here: no texture of theirs)."""
    n = 512
    noise = np.random.RandomState(8)
    img = np.zeros((n, n), np.float32)
    for row in np.flatnonzero(noise.rand(n) < 0.16):                # (lines of their own lengths and strengths)
        start, length, strength = noise.uniform(0.0, 0.7) * n, noise.uniform(0.15, 0.7) * n, noise.uniform(0.35, 1.0)
        line = np.clip(np.minimum(np.arange(n) - start, start + length - np.arange(n)) / (0.08 * n), 0.0, 1.0) * strength
        img[row] = np.maximum(img[row], line)
        img[min(row + 1, n - 1)] = np.maximum(img[min(row + 1, n - 1)], line * 0.6)
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    ends = np.clip(1.0 - (abs(u - 0.5) * 2.0) ** 2, 0.0, 1.0) * np.clip(1.0 - (abs(v - 0.5) * 2.0) ** 2, 0.0, 1.0)
    colour = np.stack([np.interp(img, STRIPE[0], c) for c in STRIPE[1:]], -1).astype(np.float32) / 255.0
    return np.round(np.dstack([colour, img * ends]) * 255.0)


THUNDER_HIGH = 3400.0               # (mm over the hand) where a column of lightning comes down from: off the top of the picture
THUNDER_PIECES, THUNDER_EVERY = 5, 3                            # its pictures one over another, and new ones every so many frames
THUNDER_CELLS = (2, 3)              # the cells of Tekken 8's texture whose bolts run up and down


def bolt_look(store, tex, cell, ramp):
    """Lightning: quarter `cell` of a texture of bolts, opaque where it is bright."""
    img = _image(store, tex, {})
    n = img.shape[0] // 2
    x = img[(cell // 2) * n:(cell // 2 + 1) * n, (cell % 2) * n:(cell % 2 + 1) * n, 0]
    x = np.maximum(x, _spread(x, 2) * 0.5)
    t = np.clip(x * 1.8, 0.0, 1.0)
    rgb = np.stack([np.interp(t, ramp[0], c) for c in ramp[1:]], -1).astype(np.float32) / 255.0
    edge = np.minimum.outer(np.minimum(np.arange(n), np.arange(n)[::-1]), np.minimum(np.arange(n), np.arange(n)[::-1])) / (n * 0.08)
    return np.round(np.dstack([rgb, t * np.clip(edge, 0.0, 1.0)]) * 255.0)


def smoke_look():
    """A dark soft cloud."""
    n = 64
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.minimum(np.hypot(u - 0.5, v - 0.5) * 2.0, 1.0)
    return np.round(np.dstack([np.full_like(u, SMOKE[0]), np.full_like(u, SMOKE[1]), np.full_like(u, SMOKE[2]), (1.0 - r) ** 1.5]) * 255.0)


def _hand(joints, f):
    """The hand further forward at frame f (the one that strikes)."""
    pair = [joints[n] for n in ('TE_R_jnt', 'TE_L_jnt')]
    return max(pair, key=lambda a: a[min(f, len(a) - 1), 2])


def burst_files(conv, d, system_of):
    """A burst's doc -> ALO bytes: its recipe's sprites at their places in the effect's frame."""
    if d['burst'][0] == missiles8.MISSILE:                  # (a missile's look, riding its projectile)
        return missiles8.files(conv, d, system_of)
    if 'clip' in d:                                         # (placed from the body part Tekken 8 spawns it at: bursts8.py)
        from . import bursts8
        made = bursts8.files(conv, d, system_of)
        if made is not None:
            return made
    recipe, frames = d['burst'][:2]
    name = d['burst'][2] if len(d['burst']) > 2 else 'blaze'
    fires = conv.__dict__['disk_fires'] = fire_textures(conv, system_of, d['source'])
    flames = _flames(conv, fires, name)
    spark = conv.textures.bake(('trail', 'spark'), trails8.spark_look(), largest=32)
    smoke = conv.textures.bake(('burst', 'smoke'), smoke_look(), largest=64)
    doc = conv._doc()
    bits = []

    def upright(e, lean=0.0):
        """A sprite keeps its picture's way up (lean: by up to this many radians either way)."""
        P._set(e['spawner'], '>12f', 164, 0.0, 0.0, -lean, 0.0, 0.0, 2.0 * lean, *([0.0] * 6))
        return e

    def flame(place, delay, life, size, count, spread, speed=2.0, k=0):
        bits.append((upright(trails8.puff(conv, flames[k % 4], place, delay, life, size, count, spread, speed, False, FLAME_KEYS(life)), 0.35),
                     flames[k % 4]))

    def sparks(place, delay, life, size, count, spread, speed):
        bits.append((trails8.puff(conv, spark, place, delay, life, size, count, spread, speed, True,
                                  [[0, 1.0], [life // 2, 1.0], [life, 0.0]]), spark))
    J, far, near = d['joints'], d['far'], d['near']
    at = lambda a, f: a[min(f, len(a) - 1)]
    hips = J['KOSHI_jnt'][0]
    floor = np.array((hips[0], min(J[n][:, 1].min() for n in FEET), hips[2]))
    if recipe == 'blade':                                   # fire along the blade: each spot burns a few frames
        for f in range(0, frames, 2 if frames <= 16 else 3):
            for k, q in enumerate((0.15, 0.4, 0.65, 0.9)):
                flame(at(near, f) + (at(far, f) - at(near, f)) * q, f, 6, 240.0 - 100.0 * q, 1, 30.0, 1.0, f + k)
    elif recipe == 'body':                                  # the body goes up in flames
        for f in range(0, frames, 3):
            for k, (n, a) in enumerate(sorted(J.items())):
                flame(at(a, f), f, 10, 330.0, 1, 70.0, 3.0, f + k)
        sparks(hips, 0, 26, 28.0, 24, 500.0, 16.0)
    elif recipe == 'cloud':                                 # what is left where he was: smoke, embers, fire on the floor
        bits.append((trails8.puff(conv, smoke, hips, 0, frames, 1900.0, 1, 40.0, 0.0, False,
                                  [[0, 0.0], [4, 0.8], [frames - 6, 0.7], [frames, 0.0]]), smoke))
        lines = conv.textures.bake(('burst', 'stripes'), stripes_look(), largest=512)
        for k, up in enumerate((-100.0, 150.0)):
            bits.append((upright(trails8.puff(conv, lines, hips + np.array((0.0, up, 200.0 * k)), 2 + 2 * k, frames - 4, 1500.0 - 200.0 * k, 1, 30.0, 0.0,
                                              False, [[0, 0.0], [2, 0.9], [frames - 10, 0.7], [frames - 4, 0.0]])), lines))
        for f in range(0, frames - 6, 3):
            for k in range(3):
                flame(floor + np.array((0.0, 180.0, 0.0)), f, 14, 620.0, 1, 500.0, 3.0, f + k)
        sparks(hips, 2, 30, 26.0, 24, 700.0, 10.0)
    elif recipe == 'appear':                                # he comes back: sparks all over him
        sparks(hips, 0, 24, 26.0, 28, 520.0, 14.0)
    elif recipe == 'feet':                                  # flames at his feet
        for f in range(0, frames, 2):
            for k, n in enumerate(FEET):
                flame(at(J[n], f), f, 12, 340.0, 1, 50.0, 3.0, f + k)
    elif recipe == 'hand':                                  # wisps round the striking hand (the effect is on its body part)
        for f in range(0, frames, 2):
            flame(np.zeros(3), f, 12, 240.0, 1, 50.0, 3.0, f)
    elif recipe == 'jet':                                   # a burst forward from the striking hand
        hand = _hand(J, 0)
        for k, (ahead, size) in enumerate(((0.0, 460.0), (160.0, 400.0), (340.0, 340.0), (560.0, 270.0), (800.0, 190.0))):
            flame(at(hand, 0) + np.array([0.0, 0.0, ahead]), k // 2, 10 + frames // 2, size, 1, 25.0, 1.0, k)
        sparks(at(hand, 0), 0, 18, 24.0, 16, 300.0, 22.0)
    elif recipe == 'wall':                                  # the sheet of flame: Tekken 8's mesh, in its place from him
        for e, tex, name in _mesh_flames(conv, d, system_of(d['source']['blaze']), frames, ((0.0, 0, 0, 'sheet', 0.0), (0.37, 2, 6, 'sheet', 0.0))):
            conv._append(doc, e, tex[0], name)
            conv.stats['emitters'] += 1
        sparks(np.array((0.0, 300.0, 2000.0)) @ d['turn'], 0, 26, 24.0, 28, 900.0, 18.0)
    elif recipe == 'swing':                                 # the column of flame: Tekken 8's mesh, violet in its fire, fire on the floor;
        for e, tex, name in _mesh_flames(conv, d, system_of(d['id']), frames, swing_copies(frames)):   # turning as it burns
            conv._append(doc, e, tex[0], name)
            conv.stats['emitters'] += 1
        ahead = np.array((0.0, 0.0, 1200.0)) @ d['turn']
        for k in range(10):
            flame(floor + ahead * (0.4 + 0.2 * (k % 5)) + np.array((0.0, 150.0, 0.0)), k, 16, 520.0 - 20.0 * k, 1, 260.0, 3.0, k)
        sparks(floor + ahead + np.array((0.0, 1900.0, 0.0)) - ahead * 1.2, 2, 26, 26.0, 28, 800.0, 16.0)
    elif recipe == 'floor':                                 # fire and sparks on the floor: where the rows say, or the effect's own offset
        user = system_of(d['id']).user.get('User.OffsetPos') or (0.0, 0.0, 0.0)
        at = d['at'] if 'at' in d else np.array((-user[1], 0.0, user[0])) * 10.0 @ d['turn']
        at = np.array((at[0], floor[1] + 120.0, at[2]))
        for k in range(5):
            flame(at, k // 2, 14, 400.0, 1, 280.0, 3.0, k)
        sparks(at, 0, 22, 26.0, 24, 520.0, 18.0)
    elif recipe == 'strike':                                # the big blow: a white flash at his back, sparks, pink wisps ahead
        chest = J['MUNE2_jnt'][min(2, len(J['MUNE2_jnt']) - 1)] if 'MUNE2_jnt' in J else hips
        hand = _hand(J, 2)
        pink = _flames(conv, fires, 'pink')
        for k in range(5):
            flame(chest + np.array([0.0, 200.0 * k - 200.0, -250.0]), k // 2, 10, 900.0 - 100.0 * k, 1, 120.0, 2.0, k)
        sparks(chest, 0, 24, 26.0, 28, 500.0, 18.0)
        for k in range(8):
            bits.append((trails8.puff(conv, pink[k % 4], at(hand, 2) + np.array([0.0, 150.0 * (k % 4) - 200.0, 300.0 + 40.0 * k]), k, 14, 300.0, 1,
                                      170.0, 2.0, False, [[0, 0.0], [2, 0.7], [7, 0.6], [14, 0.0]]), pink[k % 4]))
    elif recipe == 'feathers':                              # white feathers shed round him
        tex = feather_texture(conv, system_of, d['source'])
        for f in range(0, frames, 4):
            bits.append((trails8.puff(conv, tex, CHEST, f, 26, FEATHER_SIZE, 5, 420.0, 2.5, False, FEATHER_KEYS), tex))
    elif recipe == 'gust':                                  # feathers blown off him at once
        tex = feather_texture(conv, system_of, d['source'])
        bits.append((trails8.puff(conv, tex, CHEST, 2, 26, FEATHER_SIZE, 10, 500.0, 2.5, False, FEATHER_KEYS), tex))
    elif recipe == 'pillar':                                # flames going up from the floor round him
        for k in range(24):
            q = k / 23.0
            turn = k * 2.399963
            flame(floor + np.array((math.cos(turn) * 260.0 * (1.0 - q), 2800.0 * q, math.sin(turn) * 260.0 * (1.0 - q))), int(q * frames), 16,
                  620.0 - 300.0 * q, 1, 80.0, 3.0, k)
        sparks(floor, 2, 26, 24.0, 24, 500.0, 16.0)
    elif recipe in BOLTS:                                   # lightning crawling round the hand of a weapon of his (on its body part)
        path = _named(_textures(conv, system_of(d['source']['bolts'])), d['source']['emitters']['bolt'])['BaseTexture']
        bolts = [conv.textures.bake(('burst', recipe, k), bolt_look(conv.store, path, k, RAMPS[BOLTS[recipe][1]]), largest=256) for k in range(4)]
        for f in range(0, frames, 2):
            for k in range(3):
                tex = bolts[(f + k) % 4]
                bits.append((trails8.puff(conv, tex, np.zeros(3), f, 6, BOLTS[recipe][2] * (1.0 - 0.19 * k), 1, BOLTS[recipe][2] * (0.1 + 0.21 * k), 0.0, False,
                                          [[0, 1.0], [3, 0.9], [6, 0.0]]), tex))
    elif recipe == 'thunder':                               # a column of lightning out of the sky down to the staff in his left hand
        # (on its body part: the column comes down where the hand is in the fight, not where the clip has it; the clip's
        # way forward runs past a fighter he is pressed against)
        path = _named(_textures(conv, system_of(d['source']['bolts'])), d['source']['emitters']['bolt'])['BaseTexture']
        tall = [conv.textures.bake(('burst', 'bolts', k), bolt_look(conv.store, path, k, RAMPS['thunder']), largest=256) for k in THUNDER_CELLS]
        size = THUNDER_HIGH / THUNDER_PIECES
        for f in range(0, frames, THUNDER_EVERY):
            for k in range(THUNDER_PIECES):
                tex = tall[(f // THUNDER_EVERY + k) % len(tall)]
                place = np.array((0.0, size * (k + 0.5), 0.0))
                bits.append((upright(trails8.puff(conv, tex, place, f, THUNDER_EVERY + 2, size * 1.15, 1, size * 0.05, 0.0, False,
                                                  [[0, 1.0], [THUNDER_EVERY, 0.9], [THUNDER_EVERY + 2, 0.0]]), 0.12), tex))
    elif recipe == 'ground':                                # wisps over the floor round him
        for f in range(0, frames, 3):
            for k in range(2):
                flame(floor + np.array((0.0, 180.0, 0.0)), f, 16, 560.0, 1, 520.0, 3.0, f + k)
    elif recipe == 'ice':                                   # a field of ice out of the floor ahead: it grows, stands, shatters
        for e, tex, name in _ice(conv, d, system_of(d['id']), frames, floor):
            conv._append(doc, e, tex[0], name)
            conv.stats['emitters'] += 1
    for e, tex in bits[:P.MAX_EMITTERS]:
        conv._append(doc, e, tex[0], None)
        conv.stats['emitters'] += 1
    return alo.write(doc)


# ------------------------------------------------------------------------------------------------ the files
def model(conv, name, band, outer, inner, tex_id):
    """The band as an effect model: writes conv.models[name]. Its end frays by vertex alpha: the mask's head stops there."""
    centre, ex, ey = (np.asarray(band[k], np.float64) for k in ('centre', 'ex', 'ey'))
    pos, uv, colour = [], [], []
    for k in range(SEGMENTS + 1):
        v = k / SEGMENTS
        theta = math.radians((v - (1.0 - START)) * ARC)
        way = ex * math.cos(theta) + ey * math.sin(theta)
        ends = min(1.0, v / 0.03) * min(1.0, (1.0 - v) / 0.06)
        for r in range(ROWS):
            q = r / (ROWS - 1)
            pos.append(centre + way * (inner + (outer - inner) * q))
            uv.append((q, (1.0 - v - START) / SPREAD))
            colour.append((255, 255, 255, int(round(255 * ends))))
    tris = []
    for k in range(SEGMENTS):
        for r in range(ROWS - 1):
            a, b = k * ROWS + r, k * ROWS + r + 1
            c, d = a + ROWS, b + ROWS
            tris += [(a, c, b), (b, c, d)]
    write_model(conv, name, np.array(pos, np.float32), np.array(uv, np.float32), colour, np.array(tris, np.int64), tex_id)


def write_model(conv, name, pos, uv, colour, tris, tex_id):
    """Vertices (positions, uv, colours) and triangles as an effect model: writes conv.models[name]."""
    m = copy.deepcopy(conv.nud_template)
    one = m['meshes'][0]
    poly = one['polys'][0]
    vert = np.zeros(len(pos), poly['verts'].dtype)
    vert['pos'] = pos
    vert['nrm'][:, 1] = vert['nrm'][:, 3] = 1.0
    if 'color' in vert.dtype.names:
        vert['color'] = colour
    vert['uv'][:, 0, :] = uv
    poly['verts'] = vert
    poly['indices'] = np.array(strips.stripify(tris), np.uint16)
    for mat in poly['materials']:
        mat['src'], mat['dst'] = P.MODEL_ALPHA
        mat['cull'] = 0
        for t in mat['textures']:
            t['id'] = tex_id
    c = (pos.min(0) + pos.max(0)) / 2
    r = float(np.linalg.norm(pos - c, axis=1).max())
    m['sphere'] = one['sphere'] = (float(c[0]), float(c[1]), float(c[2]), r)
    one['center'] = (float(c[0]), float(c[1]), float(c[2]))
    conv.models[name] = nud.write(m)


def emitter(conv, name, tex, rate):
    """One model particle left where the effect starts; its texture's V runs at `rate` (of the band a frame) until the head
    has reached the far end, then slowly; then it fades."""
    run = int(math.ceil(START / rate))
    life = run + HOLD + FADE
    e = trails8.emitter(conv, name, tex, life, 1.0)
    sp = e['spawner']
    alo._set_keys(sp['tracks'][alo.ALPHA_TRACK], [[0, 1.0], [run + HOLD, 1.0], [life, 0.0]])
    slot = sp['layers'][0]['uvs'][0]
    alo._set_keys(slot['tracks'][8], [[0, 0.0, rate / SPREAD], [run, 0.0, rate / SPREAD],
                                      [run + 1, 0.0, SLOW / SPREAD]])
    return e


def effects(conv, bands, system_of):
    """Bands {id: {'band': .., 'id': Tekken 8 id}} (Sampler) -> {id: ALO bytes}. system_of: Tekken 8 id -> its niagara.System."""
    looks, out = {}, {}
    for i, d in sorted(bands.items()):
        if 'burst' in d:
            out[i] = burst_files(conv, d, system_of)
            continue
        band, system = d['band'], system_of(d['id'])
        scale = float((system.user.get('User.Scale') or [1.0])[0])
        if band['look'] not in looks:                     # (one picture a look: from the system 'source' names for it, else the band's)
            own = band['source'].get('looks', {}).get(band['look'])
            rgba = LOOKS[band['look']](conv, system if own is None else system_of(own), system_of, band['source'])
            looks[band['look']] = conv.textures.bake(('disk', band['look']), rgba, largest=max(ACROSS, ALONG))
        tex = looks[band['look']]
        outer = max(scale * 1000.0, band['radius'] * 1.1)
        conv.log('effects: arc %d: Tekken 8 id %d on move %d frame %d: %s, blade circle %d mm, %d degrees a frame, band %d mm'
                 % (i, d['id'], band['move'], band['start'], band['look'], band['radius'], band['rate'], outer))
        name = 'mfm_t7_%03d.nud' % len(conv.models)
        model(conv, name, band, outer, outer * INNER, tex[1])
        doc = conv._doc()
        conv._append(doc, emitter(conv, name, tex, band['rate'] / ARC), tex[0], name)
        conv.stats['emitters'] += 1
        for e, sprite in BESIDES.get(band['look'], lambda *_: ())(conv, band, outer, system_of):
            conv._append(doc, e, sprite[0], None)
            conv.stats['emitters'] += 1
        out[i] = alo.write(doc)
    return out


def _on_band(band, v, radius):
    """A place on a band's circle at its v (0 .. 1 along it), and the frames its head takes to get there."""
    centre, ex, ey = (np.asarray(band[k], np.float64) for k in ('centre', 'ex', 'ey'))
    theta = math.radians((v - (1.0 - START)) * ARC)
    return centre + (ex * math.cos(theta) + ey * math.sin(theta)) * radius, max(0, int(round((v - (1.0 - START)) * ARC / band['rate'])))


def _licks(conv, band, outer, system_of):
    """Flames off the outer edge of a fire's band, each as its head goes by."""
    flames = _flames(conv, fire_textures(conv, system_of, band['source']), 'fire')
    out = []
    for k, v in enumerate(np.linspace(0.2, 0.95, LICKS)):
        place, delay = _on_band(band, float(v), outer * (1.0 + 0.04 * (k % 3)))
        tex = flames[k % 4]
        out.append((trails8.puff(conv, tex, place, delay, 14, outer * 0.13, 1, outer * 0.04, 1.5, False, FLAME_KEYS(14)), tex))
    return out


def _feathers(conv, band, outer, system_of):
    """White feathers left along a wind's band."""
    tex = feather_texture(conv, system_of, band['source'])
    out = []
    for k, v in enumerate(np.linspace(0.2, 0.9, FEATHERS)):
        place, delay = _on_band(band, float(v), outer * (0.8 - 0.15 * (k % 3)))
        place[1] = max(place[1], FEATHER_FLOOR)
        out.append((trails8.puff(conv, tex, place, delay, 26, FEATHER_SIZE, 2, 90.0, 2.5, False, FEATHER_KEYS), tex))
    return out


def fire_textures(conv, system_of, source):
    """Tekken 8's fire pictures, from the materials of the mesh `source` names: {'threads', 'fine', 'cloud', 'edge': path}."""
    system = system_of(source['blaze'])
    pole = next(e for e in system.emitters if e.name == source['emitters']['blaze'])
    mats = [conv.materials.m.effective(m[1])['textures'] for r in pole.renderers for m in r.meshes]
    threads, cloud = mats[1], mats[2]
    return dict(threads=threads['BaseTexture'], fine=threads['TouchTexture'], edge=threads['MaskTexture'], cloud=cloud['BaseTexture'])


def _flames(conv, fires, name):
    """The four flame sprites of a ramp: baked once."""
    done = conv.__dict__.setdefault('disk_flames', {})
    if name not in done:
        done[name] = [conv.textures.bake(('burst', name, k), blaze_look(conv.store, fires, k, RAMPS[name]), largest=192) for k in range(4)]
    return done[name]


def swing_copies(frames):
    """The swing's column as _mesh_flames copies: SWING_STEPS leans from SWING_LEAN's first to its last over its turn, each
    shown until the next has come (a turn in steps: a model particle's own spin turns it round the effect's middle, not
    round its foot), a sheet and a violet one at each; the last burns to the end."""
    first, last, turn = SWING_LEAN
    copies = []
    for k in range(SWING_STEPS):
        q = k / float(SWING_STEPS - 1)
        start = int(round(q * turn))
        end = frames if k == SWING_STEPS - 1 else int(round((k + 1) / float(SWING_STEPS - 1) * turn)) + SWING_OVERLAP
        life = max(2, end - start)
        lean = first + (last - first) * q
        come = 0.0 if k == 0 else 0.6                       # (a step comes in over the one before)
        keys = [[0, come], [1, 1.0], [life // 2, 0.85], [life, 0.0]] if k == SWING_STEPS - 1 else \
            [[0, come], [1, 1.0], [max(1, life - SWING_OVERLAP), 1.0], [life, 0.0]]
        for ramp, seed, patches, alpha in SWING_LAYERS:
            copies.append((seed if ramp != 'sheet' else seed * (k % 2), start, frames - start - life, ramp, patches, lean,
                           [[t, a * alpha] for t, a in keys]))
    return tuple(copies)


SWING_LEAN = (22.0, 10.0, 12)       # Heatwave's column: degrees more toward him than Tekken 8's mesh at the start, at the end,
SWING_STEPS, SWING_OVERLAP = 4, 2   # frames it turns over (by Tekken 8's frames: ~40 degrees from upright, still ~30 by f82,
                                    # a straight diagonal column rising over the opponent); steps, frames one stays over the next
# its layers: (ramp, where in the fire's pictures, patches left out, alpha): an orange-white fire with violet in it that the
# opponent shows through (by Tekken 8's frames; at full alpha both were an opaque column of orange and violet stripes)
SWING_LAYERS = (('sheet', 0.37, 0.25, 0.55), ('violet', 0.61, 0.45, 0.4))


def _leaned(pos, degrees):
    """A mesh's points (the effect's level frame: x left, y up, z ahead, mm) leaned toward him round the line across its foot
    (its lowest points' middle)."""
    if not degrees:
        return pos
    y0 = pos[:, 1].min()
    foot = pos[pos[:, 1] < y0 + 0.05 * (pos[:, 1].max() - y0)]
    z0 = float(foot[:, 2].mean())
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    out = pos.copy()
    out[:, 1] = y0 + (pos[:, 1] - y0) * c + (pos[:, 2] - z0) * s
    out[:, 2] = z0 + (pos[:, 2] - z0) * c - (pos[:, 1] - y0) * s
    return out


def _mesh_flames(conv, d, system, frames, copies):
    """A mesh of Tekken 8's where its system has it, on fire. copies: (where in the fire's pictures, frames late, frames sooner gone,
    ramp, patches[, lean toward him (degrees), alpha keys]) each: their pictures differ, one burning out as another does."""
    from . import effects8                                  # (effects8 calls this module)
    source = d['source']
    pole = next(e for e in system.emitters if e.name == source['emitters']['blaze'])
    run = effects8.measure(pole)
    path = pole.renderers[0].meshes[0][0]
    sm = conv._static_mesh(path)
    p = np.asarray(sm.positions, np.float64) * np.asarray(run.scale[0], np.float64)
    tilt, turn = math.radians(run.pre[0]), math.radians(run.pre[2])
    c, z = math.cos(tilt), math.sin(tilt)
    y, up = p[:, 1] * c + p[:, 2] * z, p[:, 2] * c - p[:, 1] * z
    c, z = math.cos(turn), math.sin(turn)
    x, y = p[:, 0] * c - y * z, p[:, 0] * z + y * c
    at = np.asarray(run.path[0], np.float64) + np.asarray(system.user.get('User.OffsetPos') or (0.0, 0.0, 0.0), np.float64)
    level = np.stack([-(y + at[1]), up + at[2], x + at[0]], 1) * 10.0 + np.array((0.0, BONE_ABOVE_HIPS, 0.0))  # (cm, Unreal's axes)
    uv = np.asarray(sm.uvs[:, 0], np.float32)
    tris = np.array([t for _, part in sm.triangles() for t in part], np.int64)
    textures = conv.__dict__['disk_fires']
    out = []
    for k, copy in enumerate(copies):
        seed, delay, sooner, ramp, patches = copy[:5]
        lean, keys = (copy[5], copy[6]) if len(copy) > 6 else (0.0, None)
        pos = _leaned(level, lean) @ d['turn']
        tex = conv.textures.bake(('burst', 'wall', seed, ramp), wall_look(conv.store, textures, seed, RAMPS[ramp], patches=patches), largest=512)
        life = frames - sooner if keys is None else frames - sooner - delay
        name = 'mfm_t7_%03d.nud' % len(conv.models)
        write_model(conv, name, pos, uv, [(255, 255, 255, 255)] * len(pos), tris, tex[1])
        e = trails8.emitter(conv, name, tex, life, 1e9)
        sp = e['spawner']
        alo._set_keys(sp['tracks'][alo.ALPHA_TRACK], keys or [[0, 0.0], [2, 1.0], [life // 2, 0.85], [life, 0.0]])
        alo._set_keys(sp['tracks'][alo.SIZE_TRACK], [[0, 1.0], [life, 1.1]])
        alo._set_keys(sp['layers'][0]['uvs'][0]['tracks'][8], [[0, 0.0, 0.0]])
        P._set(e, '>HHHHHH', alo.INTERVAL, 0xFFFF, 0, 1, 0, P._u16(delay), 0)
        out.append((e, tex, name))
    return out


# Ice: Tekken 8's ice is an emitter of mesh particles ('ice' of the source's emitters) whose meshes are Houdini vertex
# animations of rigid pieces: frame 0 the whole field (the mesh as stored), then its pieces flying apart (each piece a
# column of the position and rotation textures, half floats, at its vertices' UV1 u; rotations xyz, w implied). Its
# scripts grow it in ICE_GROW frames to its full scale and stand it; by Tekken 8's frames it shatters near its life's end.
# Here: the whole field as one model per mesh, grown by the size track and standing, then ICE_SHATTER frames of its
# animation in turn, fading. Coloured from its material's ice colours over its frost picture, lit by its normals.
ICE_GROW = 4                         # frames to its full size (its scale's first key)
ICE_SHATTER = ((2, 3), (4, 4), (6, 5))      # (frame of the animation, frames shown) after it stands, each in turn: by Tekken 8's
                                     # frames its pieces drop near where they stood (later frames throw them metres off)
ICE_STANDS = 0.7                     # the share of the effect's frames it stands whole
ICE_LIGHT = np.array((0.3, 0.8, 0.5))   # (TTT2's axes: from above, ahead) the light its facets are shaded by
ICE_ALPHA = 0.92
ICE_BODY = 1.8                       # (how far the frost lifts the dark ice colour towards the light: by Tekken 8's frames)
ICE_LINE = (0.78, 0.93, 1.0)         # its glowing lines (its material's BaseColor, far over 1: white-blue once toned)
ICE_LINE_WIDEN, ICE_LINE_GAIN = 2, 2.5      # times the lines are blurred over their neighbours, and brightened after


def _vat(conv, path):
    """A vertex animation texture as stored: (frames, columns, 4) floats."""
    cache = conv.__dict__.setdefault('disk_vat', {})
    if path not in cache:
        t = texture8.Texture2D(conv.store, material8.package_of(path))
        m = t.mips[0]
        cache[path] = np.frombuffer(t.mip_bytes(m), '<f2').reshape(m.height, m.width, 4).astype(np.float32)
    return cache[path]


def ice_frame(sm, pos_tex, rot_tex, frame):
    """The vertex animation's positions of mesh sm at a frame (frame 0: as stored), and the vertices that belong to it
    (the pieces' UV1 v is under a half; its bounds' markers lie at v 1)."""
    pieces = max(1, int(np.count_nonzero(np.abs(pos_tex[0, :, :3]).sum(1) > 0)))
    uv1 = np.asarray(sm.uvs[:, 1], np.float64)
    col = np.minimum(np.floor(uv1[:, 0] * pieces).astype(int), pieces - 1)
    kept = uv1[:, 1] < 0.5
    if frame == 0:
        return np.asarray(sm.positions, np.float64), kept

    def turn(q, v):
        u, w = q[:, :3], q[:, 3:4]
        t = 2.0 * np.cross(u, v)
        return v + w * t + np.cross(u, t)

    def quat(f):
        x = rot_tex[f, col, :3].astype(np.float64)
        return np.concatenate([x, np.sqrt(np.clip(1.0 - (x * x).sum(1), 0.0, 1.0))[:, None]], 1)
    q0 = quat(0) * np.array((-1.0, -1.0, -1.0, 1.0))
    local = turn(q0, np.asarray(sm.positions, np.float64) - pos_tex[0, col, :3])
    f = min(frame, len(pos_tex) - 1)
    return pos_tex[f, col, :3] + turn(quat(f), local), kept


def ice_look(store, frost, colours, lines=None, side=256):
    """Ice: its dark and light colours over the frost picture (sRGB), the frost's white in its bright parts; `lines`
    (texture, tiling, mask texture, its tiling, its power): the glowing lines in it, its material's BaseTexture under
    its MaskTexture, ICE_LINE's colour."""
    dark, light, white = (np.asarray(c, np.float32) ** (1 / 2.2) for c in colours)
    cache = {}
    v, u = np.meshgrid((np.arange(side, dtype=np.float32) + 0.5) / side, (np.arange(side, dtype=np.float32) + 0.5) / side, indexing='ij')

    def tile(path, n):
        t = _sample(_image(store, path, cache), (u * n) % 1.0, (v * n) % 1.0, True)[..., 0]
        return np.clip((t - t.min()) / max(float(t.max() - t.min()), 1e-3), 0.0, 1.0)
    t = tile(frost, 1)
    rgb = dark + (light - dark) * (np.clip(t * ICE_BODY, 0.0, 1.0) ** 1.3)[..., None]
    rgb = rgb + (white - rgb) * (np.clip(t * 2.0 - 1.0, 0.0, 1.0) ** 1.5)[..., None]
    if lines:
        path, n, mask, m, power = lines
        a = np.clip(tile(path, n) * 1.6, 0.0, 1.0) * np.clip(tile(mask, m) ** power * 3.0, 0.0, 1.0)
        for _ in range(ICE_LINE_WIDEN):                     # (widened: the field repeats the picture many times, its
            a = (a * 2.0 + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 6.0
        a = np.clip(a * ICE_LINE_GAIN, 0.0, 1.0)            # smaller mips lose a line a texel wide)
        rgb = rgb + (np.asarray(ICE_LINE, np.float32) - rgb) * a[..., None]
    return np.round(np.dstack([rgb, np.full_like(u, ICE_ALPHA)]) * 255.0)


def _ice(conv, d, system, frames, floor):
    """The ice field's emitters: (emitter, texture, model name) each."""
    from . import effects8                                  # (effects8 calls this module)
    source = d['source']
    e = next(x for x in system.emitters if x.name.startswith(source['emitters']['ice']))
    run = effects8.measure(e)
    scale = np.asarray(run.scale[-1], np.float64)          # (its scale once grown)
    grown = float(np.mean(np.asarray(run.scale[0], np.float64) / scale))
    tilt, yaw = math.radians(run.pre[0]), math.radians(run.pre[2])
    at = np.asarray(run.path[0], np.float64) + np.asarray(system.user.get('User.OffsetPos') or (0.0, 0.0, 0.0), np.float64)
    stands = max(ICE_GROW + 2, int(frames * ICE_STANDS))
    out, seen = [], set()
    for r in e.renderers:
        if r.kind != 'mesh' or not r.meshes:
            continue
        path, mat = r.meshes[0]
        if path in seen:
            continue
        seen.add(path)
        eff = conv.materials.m.effective(mat)
        t, vec = eff['textures'], eff['vectors']
        if not (t.get('Position Texture') and t.get('Rotation Texture') and t.get('IceNoise')):
            continue
        sm = conv._static_mesh(path)
        if sm is None or sm.uvs.shape[1] < 2:
            continue
        col = lambda name, default: tuple(float(vec.get(name, {}).get(k, x)) for k, x in zip('rgb', default))
        colours = (col('IceColor01', (0.03, 0.05, 0.1)), col('IceColor02', (0.15, 0.45, 0.75)), col('NoiseColor', (0.4, 0.7, 1.0)))
        tiling = lambda name: float(vec.get(name, {}).get('r', 1.0))
        lines = ((t['BaseTexture'], tiling('BaseTexTilling'), t['MaskTexture'], tiling('MaskTexTilling'),
                  float(eff['scalars'].get('MaskPower', 1.0))) if t.get('BaseTexture') and t.get('MaskTexture') else None)
        tex = conv.textures.bake(('burst', 'ice', t['IceNoise'], lines), ice_look(conv.store, t['IceNoise'], colours, lines),
                                 largest=256)
        pos_tex, rot_tex = _vat(conv, t['Position Texture']), _vat(conv, t['Rotation Texture'])
        nrm0 = np.asarray(sm.normals, np.float64)

        def placed(p):
            p = p * scale
            c, z = math.cos(tilt), math.sin(tilt)
            y, up = p[:, 1] * c + p[:, 2] * z, p[:, 2] * c - p[:, 1] * z
            c, z = math.cos(yaw), math.sin(yaw)
            x, y = p[:, 0] * c - y * z, p[:, 0] * z + y * c
            return (np.stack([-(y + at[1]), up + at[2], x + at[0]], 1) * 10.0 + np.array((0.0, floor[1], 0.0))) @ d['turn']
        tris_all = np.array([tri for _, part in sm.triangles() for tri in part], np.int64)
        base = placed(np.zeros((1, 3)))[0]                   # (where it stands: it grows about there)
        for k, (frame, shown) in enumerate(((0, stands),) + ICE_SHATTER):
            p, kept = ice_frame(sm, pos_tex, rot_tex, frame)
            tris = tris_all[kept[tris_all].all(1)]
            pos = placed(p)
            n = placed(np.asarray(p) + nrm0) - pos               # (its normals, turned as it is: frame 0's)
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)
            light = 0.55 + 0.45 * np.abs(n @ (ICE_LIGHT / np.linalg.norm(ICE_LIGHT)))
            shade = [(int(255 * s), int(255 * s), int(255 * s), 255) for s in light]
            name = 'mfm_t7_%03d.nud' % len(conv.models)
            write_model(conv, name, (pos - base).astype(np.float32), np.asarray(sm.uvs[:, 0], np.float32), shade, tris, tex[1])
            delay = 0 if k == 0 else stands + sum(s for _, s in ICE_SHATTER[:k - 1])
            e2 = trails8.emitter(conv, name, tex, shown, 1e9)
            alo._set_keys(e2['particle']['tracks'][64], [[0] + [float(x) for x in base]])
            sp = e2['spawner']
            if k == 0:
                alo._set_keys(sp['tracks'][alo.ALPHA_TRACK], [[0, 1.0], [shown, 1.0]])
                alo._set_keys(sp['tracks'][alo.SIZE_TRACK], [[0, grown], [ICE_GROW, 1.0], [shown, 1.0]])
            else:
                last = k == len(ICE_SHATTER)
                alo._set_keys(sp['tracks'][alo.ALPHA_TRACK], [[0, 1.0 - 0.15 * (k - 1)], [shown, 0.0 if last else 0.85 - 0.15 * (k - 1)]])
                alo._set_keys(sp['tracks'][alo.SIZE_TRACK], [[0, 1.0], [shown, 1.0]])
            alo._set_keys(sp['layers'][0]['uvs'][0]['tracks'][8], [[0, 0.0, 0.0]])
            P._set(e2, '>HHHHHH', alo.INTERVAL, 0xFFFF, 0, 1, 0, P._u16(delay), 0)
            out.append((e2, tex, name))
    return out


def feather_texture(conv, system_of, source):
    """A feather sprite from a material that draws one on a mesh, here its brightness is its opacity. Squeezed: on their meshes
    Tekken 8's turn in the air and mostly show as slivers; a sprite shown flat is a ball."""
    path = _named(_textures(conv, system_of(source['feathers'])), source['emitters']['feather'])['BaseTexture']
    img = _image(conv.store, path, {})
    n = 128
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    x = _sample(img, u, np.clip(0.5 + (v - 0.5) * 3.5, 0.0, 1.0))[..., 0] * (abs(v - 0.5) * 3.5 < 0.5)
    rgba = np.dstack([np.full((n, n), 0.86, np.float32), np.full((n, n), 0.93, np.float32), np.ones((n, n), np.float32), np.clip(x * 1.6, 0.0, 1.0)])
    return conv.textures.bake(('burst', 'feather'), np.round(rgba * 255.0), largest=128)


LICKS, FEATHERS = 20, 8             # how many a band has
FEATHER_KEYS = [[0, 0.0], [3, 1.0], [18, 0.9], [26, 0.0]]
FEATHER_SIZE, FEATHER_FLOOR = 55.0, -500.0          # mm; how far below the hips one may be left
BESIDES = {'fire': _licks, 'wind': _feathers}


def _textures(conv, system):
    """{emitter's name: its first material's textures} of a system."""
    out = {}
    for e in system.emitters:
        if not e.enabled:
            continue
        for r in e.renderers:
            mat = r.meshes[0][1] if r.kind == 'mesh' and r.meshes else r.material
            if mat and e.name not in out:
                out[e.name] = conv.materials.m.effective(mat)['textures']
    return out


def _named(textures, prefix):
    """The textures of the first emitter whose name starts so."""
    return next(t for name, t in textures.items() if name.startswith(prefix))


def _ink(conv, system, system_of, source, colours=None, **thin):
    thin = dict(dict(density=INK_DENSITY, water=INK_WATER), **thin)
    x = _textures(conv, system_of(source['ink']))
    names = source['emitters']
    base, lit = _named(x, names['base']), _named(x, names['lit'])
    return ink_look(conv.store, dict(streaks=base['MaskTexture'], wedge=lit['MaskTexture'], cells=lit['BaseMaskTexture'],
                                     noise=lit['BaseTexture'], lightning=lit['EmissiveTexture'], marble=base['VanishTexture']),
                    colours=colours, **thin)


def _wind(conv, system, system_of, source):
    return _ink(conv, system, system_of, source, WIND_COLOURS, density=WIND_DENSITY, bolts=0.2, water=0.8)


def _fire(conv, system, system_of, source, smoke=True):
    x = _textures(conv, system)
    names = source['emitters']
    base = _named(x, names['base'])
    black = next((t for name, t in x.items() if name.startswith(names['smoke'])), {})
    ink = _named(_textures(conv, system_of(source['ink'])), names['base'])
    return fire_look(conv.store, dict(streaks=ink['MaskTexture'], wedge=base['ScrollTexture'], flame=base['BaseTexture'],
                                      flame2=base['HLTexture'], cells=black.get('MaskTexture') or base['HLTexture']), smoke=smoke)


def _line(conv, system, system_of, source):
    return _fire(conv, system, system_of, source, smoke=False)


LOOKS = {'ink': _ink, 'fire': _fire, 'wind': _wind, 'line': _line}
