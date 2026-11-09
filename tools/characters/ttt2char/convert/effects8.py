"""Tekken 8's effects (Niagara systems: tekken8/niagara.py) as TTT2 effect files (ALO), for the effects a fighter's
moves spawn that its definition attaches to a body part (TEKKEN8_EFFECTS).

A Tekken 8 move spawns an effect by id with 0x8039 (value: the id) and stops a looping one with 0x8035 or 0x8036 (the
same value); the fighter's effect table (DA_CharacterEffect_<CODE>) names the Niagara system of each id. particles.py's
converter writes them: each Niagara emitter (one per renderer: a sprite or a mesh) is described to it as the Cascade
emitter Tekken 7 would have, with its Required, Spawn, Lifetime, Size, SizeMultiplyLife, Color, ColorOverLife,
Velocity, Location, rotation and TypeDataMesh modules, from what the files say:

    read from the files                                     approximated (ROLES: by the emitter's name)
    renderer: sprite or mesh, material, mesh, sub-images    GPU emitters' lifetime, size, speed and spawn spread
    bursts (time, count), spawn rate, loop length              (compiled into their compute shaders: not readable)
    curves over the particle's life: opacity, size          the spawn rate of a spawn by distance (moving staff)
    colour arrays (their brightest entry)                   the colour of an emitter without a colour array (the
    CPU emitters' literals: lifetime, scale ranges,            system's, lighter) and the GPU colours' brightness
        colour scale                                        a mesh's turn (rings laid down)
    materials: textures, mask, blend, scroll, tiling, alpha power (tekken8/material.py)

TTT2's effects stop by themselves: the frames from a spawn to the stop of its id in the same property list become
its emitting time (moveset.Converter.effect8_rows and split_effects: a copy for each end). An effect is placed at the
definition's body part in the fighter's level facing frame (LEVEL_MARK), or from the floor under it (FLOOR_MARK).
Ribbons and lights are left out. A weapon's trail (0x831c, not an effect of the table) is convert/trails8.py's.

A definition's TEKKEN8_EFFECT_TUNE 'measured' (Victor) replaces the guesses for CPU emitters by what their own scripts
do (tekken8/niagarasim.py runs them: real lifetime, colour, scale, path, orientation: measure, measured_cascade), draws
what the material draws (Materials._drawn: a plain white texture is no shape, a masked material's noise is cut at its
clip value, the shape only a graph makes is generated), keeps Tekken 8's white-hot look (hot_texels), keeps flat quads as
thin models, and leaves out whatever would still be a flat coloured box (Converter.flat_box). Other fighters' effects
do not change.

Written for this project from the files themselves (no third-party code).
"""
import math
import re
import struct

import numpy as np

from . import particles as P, trails8
from ..tekken7.particles import Distribution, Emitter
from ..tekken8 import material as material8, niagara, niagarasim, staticmesh as staticmesh8, texture as texture8

EFFECT_NAME = 'eff_t8_%d'            # the converted effect of a Tekken 8 id, in the pack's alo/
SPAWN, STOP = 0x8039, 0x8035         # Tekken 8's effect properties (value: the effect id)
FLOOR = 'floor'                      # TEKKEN8_EFFECTS: {id: part, or (part, FLOOR): placed from the floor}; a part
                                     # may be {summon: part} (moveset.Converter.effect8_rows)
CURVE_POINTS = 16                    # samples of a curve over the particle's life (particles.py keeps 8 keys)
GPU_BRIGHTNESS = 2.0                 # GPU emitters' colour scale (compiled in; the materials' HDR boost is 2)
MAX_BRIGHTNESS = 8.0                 # (a CPU emitter's colour scale, its ScaleColor literal: at most this)
DEFAULT_COLOUR = (0.6, 0.8, 1.0)     # an emitter's colour when its system has no colour array
TEXTURE_MIP = 512                    # the mip decoded for an effect texture (baked at 128 or 256: particles.py)

# The approximations by role (the first name pattern that matches, case aside): life (s, half range), size (a
# sprite's, cm, half range), scale (a mesh's), speed (cm/s: half range per axis, X ahead, Y right, Z up; lift: up),
# drag, box (spawn spread, cm half sizes), spin (a sprite's random turn), turn (a mesh's: roll, pitch, yaw degrees),
# yaw_rate (a mesh's spin, turns/s), tumble (a mesh's random turn), rate (the spawn by distance, per second); a
# definition's may also say at (the spawn place, cm), emit (its emitting seconds).
ROLES = (
    (r'tornad', dict(life=(0.6, 0.1), scale=1.0, yaw_rate=1.5)),
    (r'ring', dict(life=(0.6, 0.1), scale=6.0, turn=(0.0, 90.0, 0.0), rate=0.0)),
    (r'burst|wind', dict(life=(0.5, 0.1), size=(30.0, 10.0), scale=3.0, box=(30.0, 30.0, 5.0), tumble=True,
                         speed=(20.0, 20.0, 0.0), lift=30.0)),
    (r'spark', dict(life=(0.4, 0.15), size=(3.0, 1.0), speed=(150.0, 150.0, 150.0), lift=40.0, drag=3.0,
                    box=(5.0, 5.0, 25.0), rate=40.0)),
    (r'aura', dict(life=(0.45, 0.1), size=(40.0, 10.0), speed=(10.0, 10.0, 10.0), lift=20.0, box=(8.0, 8.0, 30.0),
                   spin=True, rate=20.0)),
    (r'shitaji|light|flare|glow', dict(life=(0.3, 0.05), size=(10.0, 2.0), spin=True)),
)
DEFAULT_ROLE = dict(life=(0.4, 0.1), size=(20.0, 5.0), scale=1.0, rate=20.0)
SKIPPED_CURVES = re.compile(r'BySpeed|Rotation Rate|Index \d+ Param|Param\d', re.I)
SIZE_CURVES = re.compile(r'ScaleSpriteSize|ScaleMeshSize|VectorFromCurve', re.I)
ALPHA_CURVES = re.compile(r'Scale Alpha|Alpha', re.I)


def parts(d):
    """A definition's TEKKEN8_EFFECTS -> {effect id: (body part, or {summon: body part}, placed from the floor)}."""
    out = {}
    for i, spec in (getattr(d, 'TEKKEN8_EFFECTS', None) or {}).items():
        part, where = (spec, None) if isinstance(spec, (int, dict)) else (spec[0], spec[1] if len(spec) > 1 else None)
        part = {int(n): int(p) for n, p in part.items()} if isinstance(part, dict) else int(part)
        out[int(i)] = (part, where == FLOOR)
    return out


# ------------------------------------------------------------------------------------------------ Cascade stand-ins
class Module:
    """A Cascade module as particles.Converter reads one (tekken7/particles.Module's get and dist), its
    distributions given whole."""

    def __init__(self, cls, props=None, dists=None):
        self.cls, self.props, self.dists = cls, props or {}, dists or {}

    def get(self, name, default=None):
        return self.props.get(name, default)

    def dist(self, name, dim=1, default=None):
        d = self.dists.get(name)
        if d is not None:
            return d
        return Distribution.constant(default, dim) if default is not None else None


def ranged(mean, half=0.0, dim=1):
    """A constant distribution: mean +- half (numbers or lists of dim)."""
    m = [float(x) for x in mean] if isinstance(mean, (list, tuple)) else [float(mean)] * dim
    h = [float(x) for x in half] if isinstance(half, (list, tuple)) else [float(half)] * dim
    return Distribution([(0.0, [a - b for a, b in zip(m, h)], [a + b for a, b in zip(m, h)])], len(m))


def over_life(curve, dim=1, points=CURVE_POINTS):
    """A Niagara curve (niagara.Emitter.curves' (channels, samples, (min time, max time))) as a distribution over the
    particle's life 0..1: its samples spread over its time range, held outside it; a one-channel curve fills every
    dimension."""
    ch, samples, (t0, t1) = curve
    n = len(samples)
    times = [t0 + (t1 - t0) * k / max(1, n - 1) for k in range(n)]
    out = []
    for k in range(points):
        t = k / (points - 1)
        if n == 1 or t <= times[0]:
            v = samples[0]
        elif t >= times[-1]:
            v = samples[-1]
        else:
            j = min(n - 2, int((t - times[0]) / max(1e-9, times[1] - times[0])))
            a = (t - times[j]) / max(1e-9, times[j + 1] - times[j])
            v = [x + (y - x) * a for x, y in zip(samples[j], samples[j + 1])]
        v = [float(v[c if c < len(v) else 0]) for c in range(dim)] if ch > 1 else [float(v[0])] * dim
        out.append((t, v, list(v)))
    return Distribution(out, dim)


def size_curve(e, mesh=False):
    """The curve scaling an emitter's particles over their life, or None: a size module's, else a FloatFromCurve that
    grows past 1.5, or, for a mesh, one that grows from nothing to about 1 (a ring, a wind swirl opening out)."""
    named = [(k, c) for k, c in e.curves.items() if SIZE_CURVES.search(k) and not SKIPPED_CURVES.search(k)]
    if named:
        return named[0][1]
    for k, c in e.curves.items():
        v = [s[0] for s in c[1]]
        if 'FloatFromCurve' in k and v and max(v) > 1.5 and v[-1] > v[0]:
            return c
    for k, c in e.curves.items() if mesh else ():
        v = [s[0] for s in c[1]]
        if 'FloatFromCurve' in k and v and v[0] <= 0.05 and 0.9 <= v[-1] <= 1.5 and v[-1] == max(v):
            return c
    return None


def alpha_curve(e):
    """The curve of an emitter's opacity over the particle's life, or None: 'Scale Alpha', else a FloatFromCurve
    within 0..1.5 that fades out (its end under half its peak)."""
    named = [c for k, c in e.curves.items() if ALPHA_CURVES.search(k) and not SKIPPED_CURVES.search(k)]
    if named:
        return named[0]
    for k, c in e.curves.items():
        v = [s[0] for s in c[1]]
        if 'FloatFromCurve' in k and v and max(v) <= 1.5 and v[-1] < 0.5 * max(v) and not SIZE_CURVES.search(k):
            return c
    return None


def brightest(colours):
    """The brightest colour (r, g, b) of an emitter's colour arrays, or None."""
    best = None
    for array in colours.values():
        for c in array:
            if best is None or max(c[:3]) > max(best):
                best = tuple(float(x) for x in c[:3])
    return best


def palette(system):
    """A system's colour for its emitters without a colour array: its brightest, lighter (half way to white at its
    peak), or DEFAULT_COLOUR."""
    c = None
    for e in system.emitters:
        b = brightest(e.colours)
        if b is not None and (c is None or max(b) > max(c)):
            c = b
    if c is None or max(c) <= 0.0:
        return DEFAULT_COLOUR
    peak = max(c)
    return tuple(0.5 * (x + peak) for x in c)


def cpu_values(e):
    """A CPU emitter's values its particle scripts' literals give: {'life': (mean, half), 'scale': (mean, half),
    'brightness': x} (InitializeParticle's random ranges add(lo, random(range)): lifetime, then size or scale; the
    ScaleMeshSize / ScaleSpriteSize factor; the ScaleColor factor)."""
    out = {}
    init = next((v for k, v in e.literals.items() if k.startswith('InitializeParticle')), [])
    pairs = [(init[k][1], init[k + 1][1]) for k in range(len(init) - 1)
             if init[k][0] == 'random' and init[k + 1][0] == 'add']
    if pairs:
        out['life'] = (pairs[0][1] + pairs[0][0] / 2.0, pairs[0][0] / 2.0)
    if len(pairs) > 1:
        out['scale'] = (pairs[1][1] + pairs[1][0] / 2.0, pairs[1][0] / 2.0)
    for k, v in e.literals.items():
        mul = next((x for op, x in v if op == 'mul'), None)
        if mul is None:
            continue
        if k.startswith(('ScaleMeshSize', 'ScaleSpriteSize')) and 'scale' in out:
            out['scale'] = (out['scale'][0] * mul, out['scale'][1] * mul)
        elif k.startswith('ScaleColor'):
            out['brightness'] = min(MAX_BRIGHTNESS, mul)
    return out


def role(name, roles=()):
    """An emitter's role by its name: a definition's first (TEKKEN8_EFFECT_TUNE, which may also say 'alpha', a factor
    of its opacity), then ROLES."""
    for pattern, values in tuple(roles) + ROLES:
        if re.search(pattern, name, re.I):
            return dict(DEFAULT_ROLE, **values)
    return dict(DEFAULT_ROLE)


def cascade(e, r, colour, sm=None, floor=False, alpha=1.0, once=False, roles=(), fade_alpha=False, offset=None,
            mat_key=None):
    """The Cascade emitter (tekken7.particles.Emitter of Module stand-ins) particles.Converter converts for Niagara
    emitter e drawn by renderer r. colour: the particles' (linear, before the brightness) when e has no colour array;
    sm: the mesh of a mesh renderer (staticmesh8.StaticMesh); floor: placed from the floor; alpha: the material's
    opacity factor (AlphaMult); once: a spawn rate emits for one loop (looped(): no move stops the system); roles: a
    definition's (role)."""
    ro = role(e.name, roles)
    alpha *= ro.get('alpha', 1.0)
    cpu = cpu_values(e) if not e.gpu else {}
    mesh, mat = (r.meshes[0] if r.kind == 'mesh' and r.meshes else (None, r.material))
    life = cpu.get('life') or ro['life']
    duration = float(ro.get('emit') or e.loop or 1.0)
    looping = (e.rate > 0 or e.per_unit) and not (once and e.loop)
    rate = e.rate if e.rate > 0 else (ro['rate'] if e.per_unit else 0.0)
    mods = [Module('Required', {'Material': mat_key or mat or (sm.materials[0] if sm is not None and sm.materials
                                                               else None),
                                'EmitterDuration': duration, 'EmitterLoops': 0 if looping else 1,
                                'bUseLocalSpace': e.local, 'SubImages_Horizontal': r.sub_images[0],
                                'SubImages_Vertical': r.sub_images[1]}),
            Module('Spawn', {'BurstList': [{'Count': n, 'CountLow': -1, 'Time': min(1.0, t / duration)}
                                           for t, n in e.bursts]}, {'Rate': ranged(rate)})]
    if mesh is not None:
        mods.append(Module('TypeDataMesh', {'Mesh': mesh, 'bOverrideMaterial': mat is not None},
                           {'RollPitchYawRange': ranged(list(ro.get('turn', (0.0, 0.0, 0.0))), dim=3)}))
    mods.append(Module('Lifetime', {}, {'Lifetime': ranged(*life)}))
    plane = P._plane(sm) if sm is not None else None
    if mesh is not None and plane is None:                  # a model: one scale
        s, h = cpu.get('scale') or (ro.get('scale', 1.0), 0.0)
        mods.append(Module('Size', {}, {'StartSize': ranged(s, h, 3)}))
    else:                                                   # a sprite (or a quad drawn as one: its size / extent)
        s, h = ro['size']
        if 'scale' in cpu:
            s, h = cpu['scale']
        if plane is not None:
            s, h = s / max(plane), h / max(plane)
        mods.append(Module('Size', {}, {'StartSize': ranged(s, h, 3)}))
    grow = size_curve(e, mesh is not None and plane is None)
    if grow is not None:
        mods.append(Module('SizeMultiplyLife', {}, {'LifeMultiplier': over_life(grow, 3)}))
    rgb = brightest(e.colours) or colour
    bright = cpu.get('brightness', GPU_BRIGHTNESS if e.gpu else 1.0)
    mods.append(Module('Color', {}, {'StartColor': ranged([x * bright for x in rgb], dim=3),
                                     'StartAlpha': ranged(alpha)}))
    fade = alpha_curve(e)
    if fade is not None:
        d = over_life(fade, 1)
        if fade_alpha:
            d = Distribution([(t, [a * alpha for a in lo], [a * alpha for a in hi]) for t, lo, hi in d.samples], 1)
        mods.append(Module('ColorOverLife', {}, {'AlphaOverLife': d}))
    speed = ro.get('speed')
    if speed:
        lift = ro.get('lift', 0.0)
        mods.append(Module('Velocity', {}, {'StartVelocity': ranged([0.0, 0.0, lift], list(speed), 3)}))
    if ro.get('drag'):
        mods.append(Module('AccelerationDrag', {}, {'DragCoefficientRaw': ranged(ro['drag'])}))
    if ro.get('box') or offset or ro.get('at'):
        at = [a + b for a, b in zip(offset or (0.0, 0.0, 0.0), ro.get('at') or (0.0, 0.0, 0.0))]
        mods.append(Module('Location', {}, {'StartLocation': ranged(at, list(ro.get('box') or (0.0, 0.0, 0.0)), 3)}))
    if mesh is None or plane is not None:
        if ro.get('spin'):
            mods.append(Module('Rotation', {}, {'StartRotation': ranged(0.5, 0.5)}))
    else:
        if ro.get('tumble'):
            mods.append(Module('MeshRotation', {}, {'StartRotation': ranged([0.5] * 3, [0.5] * 3, 3)}))
        if ro.get('yaw_rate'):
            mods.append(Module('MeshRotationRate', {}, {'StartRotationRate': ranged([0.0, 0.0, ro['yaw_rate']],
                                                                                    dim=3)}))
    if floor:
        mods.append(Module('FloorHeight'))
    return Emitter(e.name, {}, mods)


# ------------------------------------------------------------------------------------------------ measured emitters
# A definition's TEKKEN8_EFFECT_TUNE 'measured' runs each CPU emitter's own particle scripts (tekken8/niagarasim.py)
# and describes what they did: life, colour and opacity over the life, scale per axis, path, spread, orientation.
# GPU emitters stay approximated (ROLES): their numbers are compiled into shaders.
FLAT_MESH_VERTICES = 64              # at most this many vertices: strips and planes (flat faces)
RANDOM_TURN = 0.2                    # a quaternion component's spread above which a particle's turn is random
DRIFT_CLONES = 4                     # the emitters of one whose particles fly apart (TTT2's random speed is along its
                                     # one direction; every file of the game has it on z only, x and y fly off wrongly)
HOT_BRIGHTNESS = 1.5                 # a translucent emitter brighter than this draws additively: Tekken 8 adds its
                                     # emissive colour however thin the alpha, its fringe glows


def quat_rotator(q):
    """A particle's mesh orientation (x, y, z, w) -> (roll, pitch, yaw) degrees of frotation's matrix."""
    x, y, z, w = [float(v) for v in q]
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    m00, m01, m02 = 1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)
    m12, m22 = 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)
    return (math.degrees(math.atan2(-m12, m22)), math.degrees(math.asin(max(-1.0, min(1.0, m02)))),
            math.degrees(math.atan2(m01, m00)))


def _quat_mul(a, b):
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


class Measured:
    """What a CPU emitter's scripts do to its particles: life (mean, half) seconds; times over the life; colour
    [(r, g, b)], alpha [a], scale [(x, y, z)] (a mesh's) or size [(w, h)] (a sprite's, cm); path [(x, y, z)] cm (the
    mean place), start_half, speed_half (cm, cm/s: the random spread), scale_half (a factor's); pre: a fixed turn
    (roll, pitch, yaw), turn_half: random turn (turns, per axis), spin, spin_half (turns per second, per axis)."""

    def __init__(self, run):
        h = run.history
        life = run.lifetime if run.lifetime is not None and len(run.lifetime) else np.array([1.0])
        self.life = (float((life.max() + life.min()) / 2.0), float((life.max() - life.min()) / 2.0))
        frames = len(next(iter(h.values()))) if h else 1
        self.times = [k / (CURVE_POINTS - 1) for k in range(CURVE_POINTS)]
        last = max(1.0, self.life[0] * P.FPS)
        at = [min(frames - 1, int(round(t * last))) for t in self.times]
        fade = np.clip(np.asarray(h['Color']), 0.0, None) if 'Color' in h else None
        self.colour = [tuple(float(x) for x in fade[f, :, :3].mean(0)) for f in at] if fade is not None else None
        self.alpha = [float(fade[f, :, 3].mean()) for f in at] if fade is not None else None
        self.scale = self.size = None
        self.scale_half = 0.0
        if 'Scale' in h:
            v = np.asarray(h['Scale'])
            self.scale = [tuple(float(x) for x in np.abs(v[f]).mean(0)) for f in at]
            big = at[len(at) // 2]
            self.scale_half = min(0.9, float((v[big].std(0) / np.maximum(1e-3, np.abs(v[big]).mean(0))).mean()) * 1.7)
        if 'SpriteSize' in h:
            v = np.asarray(h['SpriteSize'])
            self.size = [tuple(float(x) for x in np.abs(v[f]).mean(0)) for f in at]
            big = at[len(at) // 2]
            self.scale_half = min(0.9, float((v[big].std(0) / np.maximum(1e-3, np.abs(v[big]).mean(0))).mean()) * 1.7)
        self.path = [(0.0, 0.0, 0.0)] * len(at)
        self.start_half = self.speed_half = (0.0, 0.0, 0.0)
        self.drifts = []
        if 'Position' in h:
            v = np.asarray(h['Position'])
            self.path = [tuple(float(x) for x in v[f].mean(0)) for f in at]
            self.start_half = tuple(float(x) * 1.7 for x in v[0].std(0))
            drift = (v[at[-1]] - v[0]) / max(1.0 / P.FPS, self.life[0])
            self.speed_half = tuple(float(x) * 1.7 for x in drift.std(0))
            some = drift[np.linspace(0, len(drift) - 1, DRIFT_CLONES).astype(int)]
            self.drifts = [tuple(float(x) for x in d) for d in some - some.mean(0)]
        self.sprite_turn = None
        if 'SpriteRotation' in h:
            v = np.asarray(h['SpriteRotation'])[0, :, 0]
            self.sprite_turn = (float(v.mean()) / 360.0, min(0.5, float(v.std()) * 1.7 / 360.0))
        self.pre = (0.0, 0.0, 0.0)
        self.turn_half = (0.0, 0.0, 0.0)
        self.spin = self.spin_half = (0.0, 0.0, 0.0)
        if 'MeshOrientation' in h:
            q = np.asarray(h['MeshOrientation'], np.float64)
            q0 = q[0] / np.maximum(1e-9, np.linalg.norm(q[0], axis=1, keepdims=True))
            if np.linalg.norm(q0.mean(0)) > 0.05 or q0.std(0).max() < RANDOM_TURN:
                if q0.std(0).max() < RANDOM_TURN:
                    self.pre = quat_rotator(q0.mean(0))
            spread = q0.std(0)[:3]
            self.turn_half = tuple(0.5 if x > RANDOM_TURN else 0.0 for x in spread)
            f = min(frames - 1, max(1, int(round(last / 2))))
            q1 = q[f] / np.maximum(1e-9, np.linalg.norm(q[f], axis=1, keepdims=True))
            rel = _quat_mul(q1, q0 * np.array([-1.0, -1.0, -1.0, 1.0]))
            rel = rel * np.where(rel[:, 3:4] < 0, -1.0, 1.0)            # (the short way round)
            angle = 2.0 * np.arctan2(np.linalg.norm(rel[:, :3], axis=1), rel[:, 3])
            axis = rel[:, :3] / np.maximum(1e-9, np.linalg.norm(rel[:, :3], axis=1, keepdims=True))
            turns = axis * angle[:, None] / (2.0 * math.pi) / (f / P.FPS)
            self.spin = tuple(float(x) for x in turns.mean(0))
            self.spin_half = tuple(float(x) * 1.7 for x in turns.std(0))


def measure(e):
    """Measured of a CPU emitter, or None (a GPU emitter's, one its scripts cannot run for)."""
    if e.gpu or not getattr(e, 'scripts', None):
        return None
    try:
        return Measured(niagarasim.simulate(e.scripts[0], e.scripts[1], e.curves, e.arrays))
    except (KeyError, ValueError, IndexError, ZeroDivisionError, NotImplementedError, TypeError):
        return None


def keyed(times, values):
    """A distribution over the life 0..1 of [values...]."""
    return Distribution([(t, [float(x) for x in v], [float(x) for x in v]) for t, v in zip(times, values)],
                        len(values[0]))


def tuned(name, roles):
    """What a definition says of a measured emitter by its name (the first pattern that matches): at (added to its
    place, cm), thin (a factor on the scale across its X), size (a factor on its size), pre (its mesh's turn: roll,
    pitch, yaw), alpha (a factor), colour (a factor per channel), turn (random turn: half range in turns, per axis),
    add (drawn additively whatever its brightness: Tekken 8's dim glows light the picture, they do not darken it),
    dim (a factor on its light on the screen: dimmed), wh (its size as a sprite, cm: the GPU's numbers are out of
    reach), fade (its alpha falls from the start to the end of its life: Tekken 8 gives it none)."""
    for pattern, values in roles:
        if re.search(pattern, name, re.I):
            return values
    return {}


def dimmed(emitter, factor):
    """An emitter's light x factor, on the screen (a definition's `dim`): its colour track, which TTT2 adds to the
    picture as it is. A factor on its alpha (`alpha`) goes through the bake's tone mapping, which lifts low light: a
    colour in the tens at an alpha of a hundredth still shows at half the screen's brightness."""
    for key in emitter['spawner']['tracks'][P.alo.COLOUR_TRACK]['keys']:
        key[1:4] = [x * factor for x in key[1:4]]


def measured_cascade(e, r, m, sm=None, floor=False, alpha=1.0, once=False, offset=(0.0, 0.0, 0.0), mat=None,
                     sprite=False, over=None, drift=None, share=1.0):
    """The Cascade emitter of a CPU emitter from what its scripts do (m: Measured). mat: the material as drawn
    (Materials.describe's key); offset: added to its place (cm: the system's muzzle, say); sprite: its mesh drawn
    as a camera-facing sprite of the mesh's size; over: a definition's corrections (tuned); drift: a velocity of
    its particles (cm/s, one of Measured.drifts); share: its part of the spawn counts."""
    over = over or {}
    alpha *= over.get('alpha', 1.0)
    offset = [a + b for a, b in zip(offset, over.get('at') or (0.0, 0.0, 0.0))]
    mesh, _ = (r.meshes[0] if r.kind == 'mesh' and r.meshes else (None, r.material))
    if sprite:
        mesh = None
    duration = float(e.loop or 1.0)
    looping = (e.rate > 0 or e.per_unit) and not (once and e.loop)
    rate = (e.rate if e.rate > 0 else (30.0 if e.per_unit else 0.0)) * share
    mods = [Module('Required', {'Material': mat, 'EmitterDuration': duration, 'EmitterLoops': 0 if looping else 1,
                                'bUseLocalSpace': e.local, 'SubImages_Horizontal': r.sub_images[0],
                                'SubImages_Vertical': r.sub_images[1]}),
            Module('Spawn', {'BurstList': [{'Count': max(1, int(round(n * share))), 'CountLow': -1,
                                            'Time': min(1.0, t / duration)}
                                           for t, n in e.bursts]}, {'Rate': ranged(rate)})]
    t = m.times
    if mesh is not None:
        mods.append(Module('TypeDataMesh', {'Mesh': mesh, 'bOverrideMaterial': True},
                           {'RollPitchYawRange': ranged(list(over.get('pre') or m.pre), dim=3)}))
    mods.append(Module('Lifetime', {}, {'Lifetime': ranged(*m.life)}))
    if mesh is not None:
        scale = m.scale or m.size and [(a, b, a) for a, b in m.size] or [(1.0, 1.0, 1.0)] * len(t)
        grow, thin = over.get('size', 1.0), over.get('thin', 1.0)
        scale = [(a * grow, b * grow * thin, c * grow * thin) for a, b, c in scale]
        mods.append(Module('Size', {}, {'StartSize': ranged(1.0, m.scale_half, 3)}))
        mods.append(Module('SizeMultiplyLife', {}, {'LifeMultiplier': keyed(t, scale)}))
    else:
        size = m.size or [(20.0, 20.0)] * len(t)
        if sm is not None and sprite:       # a mesh drawn as a sprite (Materials.SPRITE_FAMILIES): its size
            ext = float((sm.positions.max(0) - sm.positions.min(0)).max())
            mesh_scale = m.scale or [(1.0, 1.0, 1.0)] * len(t)
            size = [(ext * a, ext * b) for a, b, _ in mesh_scale]
        size = [(a * over.get('size', 1.0), b * over.get('size', 1.0)) for a, b in size]
        if over.get('wh'):                  # (a size of its own: the emitter's come from the GPU, out of reach)
            size = [tuple(over['wh'])] * len(t)
        w, h = max(1e-3, max(x[0] for x in size)), max(1e-3, max(x[1] for x in size))
        mods.append(Module('Size', {}, {'StartSize': ranged([w, h, w], [w * m.scale_half, h * m.scale_half, 0.0])}))
        mods.append(Module('SizeMultiplyLife', {}, {'LifeMultiplier': keyed(
            t, [(a / w, b / h, a / w) for a, b in size])}))
    rgb = m.colour or [(1.0, 1.0, 1.0)] * len(t)
    tint = over.get('colour') or (1.0, 1.0, 1.0)
    rgb = [tuple(a * b for a, b in zip(c, tint)) for c in rgb]
    fade = [1.0 - x for x in t] if over.get('fade') else m.alpha or [1.0] * len(t)
    mods.append(Module('Color', {}, {'StartColor': ranged(list(rgb[0]), dim=3), 'StartAlpha': ranged(alpha)}))
    mods.append(Module('ColorOverLife', {}, {'ColorOverLife': keyed(t, rgb),
                                             'AlphaOverLife': keyed(t, [[a * alpha] for a in fade])}))
    path = [[a + b for a, b in zip(p, offset)] for p in m.path]
    mods.append(Module('LocationDirect', {}, {'Location': keyed(t, path)}))
    if any(m.start_half):
        mods.append(Module('Location', {}, {'StartLocation': ranged([0.0] * 3, list(m.start_half), 3)}))
    if drift is not None:
        mods.append(Module('Velocity', {}, {'StartVelocity': ranged(list(drift), 0.0, 3)}))
    if mesh is None and m.sprite_turn is not None and any(m.sprite_turn):
        mods.append(Module('Rotation', {}, {'StartRotation': ranged(*m.sprite_turn)}))
    if mesh is not None:
        turn_half = over.get('turn') or m.turn_half
        if any(turn_half):
            mods.append(Module('MeshRotation', {}, {'StartRotation': ranged([0.0] * 3, list(turn_half), 3)}))
        if any(m.spin) or any(m.spin_half):
            mods.append(Module('MeshRotationRate', {}, {'StartRotationRate': ranged(list(m.spin), list(m.spin_half),
                                                                                    3)}))
    if floor:
        mods.append(Module('FloorHeight'))
    return Emitter(e.name, {}, mods)


def measured_palette(system):
    """The colour of a system's emitters that do not say theirs (GPU emitters): its brightest measured emitter's
    (at the role's usual brightness), or None."""
    best = None
    for e in system.emitters:
        m = measure(e) if e.enabled else None
        for c in (m.colour or []) if m is not None else []:
            if best is None or max(c) > max(best):
                best = c
    if best is None or max(best) <= 0.0:
        return None
    return tuple(x / max(best) for x in best)


def peak_brightness(m, power, colour=None):
    """The brightest channel a measured emitter reaches, with its material's colour factor."""
    rgb = (m.colour if m is not None else None) or [colour or (1.0, 1.0, 1.0)]
    return max(max(c) for c in rgb) * power


# ------------------------------------------------------------------------------------------------ materials, textures
class Materials:
    """Tekken 8 effect materials described as particles.py reads Tekken 7's (EffectMaterials.describe): textures
    (a mask alone is the shape: BaseTexture), scalars (ColorMult as a colour power), vectors (the tornado family's
    names as the others'), switches, blend (translucent, or additive), base, two_sided; also 'alpha' (AlphaMult)."""
    TEXTURES = {'BaseTex': 'BaseTexture', 'MaskTex': 'MaskTexture'}
    VECTORS = {'BaseTexTile': 'BaseTexTilling'}
    # measured (a definition's TEKKEN8_EFFECT_TUNE): what a material draws, with no plain white texture posing as one
    WHITE_TEXTURE = re.compile(r'white', re.I)        # T_EF__COL_white8, T_white_01_hn, T_EF_COL_White_01
    NOT_DRAWN = re.compile(r'^VAT_pos|^TexPos|Yugami|Distortion|Distition', re.I)
    DRAWN_NAMES = {'EmissiveColorTexture': 'BaseTexture', 'AlphaMaskTexture': 'MaskTexture', 'Mask Texture': 'BaseTexture'}
    GENERATED = ((re.compile(r'BLD_Lon_Flare01'), 'gen:flare'),     # the family's shape is its graph's: generated
                 (re.compile(r'BLD_Lon_Dome'), 'gen:rim'))
    SPRITE_FAMILIES = re.compile(r'BLD_Lon_Dome')     # spheres lit at the rim: the rim on a sprite of their size
    EMISSIVE = ('EmessiveColor', 'EmissiveColor')     # a material's own colour: as a particle colour factor
    ADDITIVE = '#additive'                            # a material's key, drawn additively (hot emitters)

    def __init__(self, store, measured=False):
        self.m = material8.Materials(store)
        self._done = {}
        self.measured = measured

    def _drawn(self, eff, tex):
        """The measured look's textures: plain white and graph-only ones out; a mask over white is the shape; a
        masked material's noise cut at its clip value; a shape only a graph draws generated."""
        out = {self.DRAWN_NAMES.get(k, k): v for k, v in tex.items()
               if not self.WHITE_TEXTURE.search(v.rsplit('/', 1)[-1]) and not self.NOT_DRAWN.search(k)}
        base = (eff['base'] or '').rsplit('/', 1)[-1]
        for pattern, name in self.GENERATED:
            if pattern.search(base):
                return {'BaseTexture': name}
        props = eff['overrides']
        clip = props.get('OpacityMaskClipValue')
        if int(props.get('BlendMode') or 0) == material8.BLEND_MASKED and clip and out.get('Param'):
            return {'BaseTexture': 'clip:%.3f:%s' % (float(clip), out['Param'])}
        if not out.get('BaseTexture') and out.get('MaskTexture'):
            out['BaseTexture'] = out.pop('MaskTexture')
        return out

    def describe(self, path):
        if path in self._done:
            return self._done[path]
        if path.endswith(self.ADDITIVE):
            out = dict(self.describe(path[:-len(self.ADDITIVE)]), blend='BLEND_Additive')
            self._done[path] = out
            return out
        eff = self.m.effective(path)
        tex = {self.TEXTURES.get(k, k): v for k, v in eff['textures'].items() if v}
        if self.measured:
            tex = self._drawn(eff, tex)
        if not tex.get('BaseTexture') and tex.get('MaskTexture'):
            tex['BaseTexture'] = tex.pop('MaskTexture')
        scalars = dict(eff['scalars'])
        if 'ColorMult' in scalars and 'ColorBoost' not in scalars:
            scalars['ColorBoost'] = scalars['ColorMult']
        vectors = {self.VECTORS.get(k, k): v for k, v in eff['vectors'].items()}
        if self.measured and str(tex.get('BaseTexture')).startswith('gen:'):
            vectors.pop('BaseTexTilling', None)           # (a generated shape is whole: no tiling of the graph's)
        col = vectors.get('Col1')                 # (the tornado family's colour: its hue, its peak as a power)
        if col and 'add_color' not in vectors:
            peak = max(col['r'], col['g'], col['b'])
            if peak > 0:
                vectors['add_color'] = {'r': col['r'] / peak, 'g': col['g'] / peak, 'b': col['b'] / peak}
                scalars['Color Power'] = min(MAX_BRIGHTNESS, peak)
        if self.measured:
            own = next((vectors[k] for k in self.EMISSIVE if vectors.get(k)), None)
            peak = max(own['r'], own['g'], own['b']) if own else 0.0
            if peak > 0:
                shift = vectors.get('GlitchColor_1') or {}      # (its colour fringe, in the same dashes on screen)
                mix = {c: own[c] + 0.5 * peak * float(shift.get(c) or 0.0) for c in 'rgb'}
                top = max(mix.values())
                vectors['add_color'] = {c: mix[c] / top for c in 'rgb'}
                scalars['Color Power'] = top
        props = eff['overrides']
        out = {'name': eff['name'], 'base': eff['base'], 'textures': tex, 'scalars': scalars, 'vectors': vectors,
               'switches': dict(eff['switches']),
               'blend': 'BLEND_Additive' if int(props.get('BlendMode') or 0) == material8.BLEND_ADDITIVE else
               'BLEND_Translucent', 'two_sided': bool(props.get('TwoSided')),
               'alpha': float(scalars.get('AlphaMult') or 1.0)}
        self._done[path] = out
        return out


def lit_texels(img, peak, peak_alpha, additive):
    """particles.lit_texels with the hue kept: the brightest channel of each texel is tone mapped (the same ACES
    fit) and the others scaled with it. Tekken 8's effect colours are saturated blues far above 1 (her staffs'
    (0, 0.51, 1) x 2): tone mapped channel by channel they turn cyan (sRGB 0, 230, 245); her sparkles in the game's
    pictures are azure (0, 188, 255 at full colour; kept: 0, 181, 245)."""
    e = img[..., :3] * np.asarray(peak, np.float32) * P.EXPOSURE
    a = np.clip(img[..., 3:4] * peak_alpha, 0.0, 1.0)
    if additive:
        e = e * a
        a = np.ones_like(a)
    m = e.max(axis=-1, keepdims=True)
    tm = np.clip(m * (2.51 * m + 0.03) / (m * (2.43 * m + 0.59) + 0.14), 0.0, 1.0)
    rgb = np.clip(e * tm / np.maximum(m, 1e-6), 0.0, 1.0)
    return np.concatenate([rgb ** (1.0 / P.GAMMA), a], axis=-1)


HOT_FROM, HOT_TO, HOT_WHITE = 4.0, 64.0, 0.8     # the brightness over which a colour burns to (this share of) white
HOT_EXPOSURE = 0.25                 # (Tekken 8's frames: its colours in the tens stay coloured and show their texture)


def hot_texels(img, peak, peak_alpha, additive):
    """lit_texels with Tekken 8's bloom: where a texel's brightness is far above 1 its colour burns towards white
    (the white cores of the bullet and the sparks, their blue only at the edges)."""
    e = img[..., :3] * np.asarray(peak, np.float32) * HOT_EXPOSURE
    a = np.clip(img[..., 3:4] * peak_alpha, 0.0, 1.0)
    if additive:
        e = e * a
        a = np.ones_like(a)
    m = e.max(axis=-1, keepdims=True)
    tm = np.clip(m * (2.51 * m + 0.03) / (m * (2.43 * m + 0.59) + 0.14), 0.0, 1.0)
    rgb = np.clip(e * tm / np.maximum(m, 1e-6), 0.0, 1.0)
    burn = HOT_WHITE * np.clip((np.log2(np.maximum(m, 1e-6)) - math.log2(HOT_FROM))
                               / (math.log2(HOT_TO) - math.log2(HOT_FROM)), 0.0, 1.0)
    rgb = rgb + (tm - rgb) * burn
    return np.concatenate([np.clip(rgb, 0.0, 1.0) ** (1.0 / P.GAMMA), a], axis=-1)


BLACK_TEXEL = 8.0                   # below this every channel of a block texture's colours rounds to 0
GENERATED_SIDE = 128
CLIP_SOFTNESS = 3.0                 # a masked material's noise over its cut: to full opacity within a third
CLIP_SIDE = 256                     # ... baked this large (its thin lines)


def generated_mask(kind):
    """A shape only a material's graph draws, as a linear RGBA image (made here, nothing of the game's): 'flare' a
    soft star-like glow, 'rim' a sphere's lit rim seen from any side."""
    n = GENERATED_SIDE
    y, x = np.mgrid[0:n, 0:n] + 0.5
    u, v = (x - n / 2) / (n / 2), (y - n / 2) / (n / 2)
    r = np.hypot(u, v)
    if kind == 'flare':
        a = np.clip(1.0 - r, 0.0, 1.0) ** 3 + 0.5 * np.clip(1.0 - r, 0.0, 1.0) ** 8 \
            + 0.35 * np.clip(1.0 - np.abs(u) * 18.0, 0.0, 1.0) * np.clip(1.0 - np.abs(v), 0.0, 1.0) ** 2 \
            + 0.35 * np.clip(1.0 - np.abs(v) * 18.0, 0.0, 1.0) * np.clip(1.0 - np.abs(u), 0.0, 1.0) ** 2
    elif kind == 'rim':
        z = np.sqrt(np.clip(1.0 - r * r, 0.0, 1.0))             # (a sphere's facing: the rim where it turns away)
        a = np.where(r < 1.0, (1.0 - z) ** 3, 0.0)
        a = a * np.clip((1.0 - r) * 24.0, 0.0, 1.0)
    else:
        raise ValueError('no generated shape ' + kind)
    img = np.ones((n, n, 4), np.float32)
    img[..., 3] = np.clip(a, 0.0, 1.0)
    return img


class Textures(P.Textures):
    """particles.Textures reading Tekken 8's textures, lit with their hue kept (lit_texels); hot: burning to white
    (hot_texels); also a material's generated shapes (Materials.GENERATED, 'gen:...') and cut noise ('clip:...')."""

    def __init__(self, store, first, hot=False):
        super().__init__(None, first)
        self.store = store
        self.hot = hot

    def lit(self, src, peak, peak_alpha, additive):
        q = lambda x: round(math.log2(max(x, 1.0 / 64)) * 4) / 4                   # (particles.Textures.lit's steps)
        p = tuple(2.0 ** q(x) if x > 1.0 / 128 else 0.0 for x in peak)
        pa = 2.0 ** q(peak_alpha)
        key = ('lit8hot' if self.hot else 'lit8', src.key, p, pa, additive)
        if key not in self._by_key:
            bake = hot_texels if self.hot else lit_texels
            side = CLIP_SIDE if self.hot and str(src.key[0]).startswith('clip:') else src.side
            texels = np.round(bake(src.img, p, min(pa, P.MAX_ALPHA_GAIN), additive) * 255.0)
            if self.hot and (texels[..., :3].max() < BLACK_TEXEL or (texels[..., :3] * texels[..., 3:4]).max() < 255.0):
                raise P.Invisible()         # (no light at all; and a block texture of black draws white in the game)
            self.bake(key, texels, side)
        return self._by_key[key]

    def image(self, path):
        return texture8.Texture2D(self.store, material8.package_of(path)).decode(TEXTURE_MIP)

    def linear_image(self, path):
        if path.startswith('gen:'):
            return generated_mask(path[4:])
        if path.startswith('clip:'):                # a masked material's noise, cut at its clip value
            _, cut, source = path.split(':', 2)
            t = texture8.Texture2D(self.store, material8.package_of(source))
            img = t.decode(TEXTURE_MIP).astype(np.float32) / 255.0     # (as stored: the cut is the graph's)
            out = np.ones_like(img)
            out[..., 3] = np.clip((img[..., :3].max(axis=-1) - float(cut)) * CLIP_SOFTNESS, 0.0, 1.0)
            return out
        t = texture8.Texture2D(self.store, material8.package_of(path))
        img = t.decode(TEXTURE_MIP).astype(np.float32) / 255.0
        if t.srgb:
            img[..., :3] = img[..., :3] ** P.GAMMA
        if self.hot and float(np.ptp(img[..., 3])) >= 8 / 255.0 and P._grey(img[..., :3]):
            img[..., 3] *= img[..., :3].max(axis=-1)    # (Tekken 8 draws colour x alpha: both are the dot's falloff)
        return img


# ------------------------------------------------------------------------------------------------ converter
class TwoSidedMesh:
    """A static mesh whose triangles are drawn from both sides (a measured look's strips and planes: TTT2's model
    material culls the back)."""

    def __init__(self, sm):
        self.sm = sm

    def __getattr__(self, name):
        return getattr(self.sm, name)

    def triangles(self):
        return [(m, np.concatenate([t, t[:, ::-1]])) for m, t in self.sm.triangles()]


class Converter(P.Converter):
    """Converts a fighter's Tekken 8 Niagara systems (textures and meshes shared by its effects)."""

    def __init__(self, store, archives, first_texture_id, log=None):
        super().__init__(None, archives, first_texture_id, log)
        self.store = store
        self.materials = Materials(store)
        self.textures = Textures(store, first_texture_id)
        self.tune = {}                  # a definition's TEKKEN8_EFFECT_TUNE (convert_fighter)
        self.stats.update({'left out (ribbons, lights)': 0, 'left out (a flat box)': 0})

    def set_tune(self, tune):
        """A definition's TEKKEN8_EFFECT_TUNE: 'measured' turns on the measured look (measure, Materials._drawn,
        hot_texels)."""
        self.tune = tune or {}
        self.measured = bool(self.tune.get('measured'))
        self.materials.measured = self.textures.hot = self.flat_models = self.measured

    def flat_box(self, mat, sm, sprite):
        """Whether an emitter would draw as a flat coloured box: its material has no shape (a texture that fills it
        or none) and it is drawn on a sprite or flat faces. A round or tapering model is its own shape; a sprite with no
        texture at all is a soft glow (particles.Converter._plain)."""
        if sm is None or sprite or len(sm.positions) > FLAT_MESH_VERTICES:
            if sm is None or sprite:
                src = P.material_source(self.textures, mat)
                return src is not None and float((src.img[..., 3] > 0.75).mean()) > 0.9
            return False
        src = P.material_source(self.textures, mat)
        if src is not None and float((src.img[..., 3] > 0.75).mean()) <= 0.9:
            return False
        faces = {tuple(np.round(n, 1)) for n in sm.normals}
        return len(faces) <= 6

    def _measured(self, e, r, mesh, sm, mat, floor, once, colour, offset, cap_frames, roles=()):
        """The converted emitters of one renderer, as the emitter's scripts draw it (GPU emitters: its role)."""
        desc = self.materials.describe(mat) if mat else None
        sprite = bool(desc and sm is not None and Materials.SPRITE_FAMILIES.search(desc['base'] or ''))
        if desc is None or self.flat_box(desc, sm, sprite):
            self.log('effects: %s drawn as a flat box: left out' % e.name)
            self.stats['left out (a flat box)'] += 1
            return []
        alpha, power = desc['alpha'], P._power(desc)[0]
        for pattern, factor in self.tune.get('material_alpha', ()):     # (one material of an emitter's two)
            if re.search(pattern, mat):
                alpha *= factor
        m = measure(e)
        rgb = brightest(e.colours) or colour
        over = tuned(e.name, roles)
        hot = over.get('add') or \
            peak_brightness(m, power, rgb) * (1.0 if m is not None else GPU_BRIGHTNESS) > HOT_BRIGHTNESS
        key = mat + Materials.ADDITIVE if hot and desc['blend'] != 'BLEND_Additive' else mat
        if m is None:
            em = cascade(e, r, colour, None if sprite else sm, floor, alpha, once, roles, fade_alpha=True,
                         offset=offset, mat_key=key)
            made = self.emitter(em, cap_frames)
        else:
            drifts = m.drifts if max(m.speed_half) > 1.0 else [None]
            made = []
            for drift in drifts:
                made += self.emitter(measured_cascade(e, r, m, sm, floor, alpha, once, offset or (0.0, 0.0, 0.0), key,
                                                      sprite, over, drift, 1.0 / len(drifts)), cap_frames)
        if over.get('dim'):
            for done in made:
                dimmed(done[0], over['dim'])
        return made

    def _static_mesh(self, path):
        if path not in self._meshes:
            try:
                self._meshes[path] = staticmesh8.StaticMesh(self.store, path)
                if getattr(self, 'measured', False) and len(self._meshes[path].positions) <= FLAT_MESH_VERTICES:
                    self._meshes[path] = TwoSidedMesh(self._meshes[path])
            except (KeyError, ValueError, struct.error) as error:
                self.log('effects: mesh %s not read (%s)' % (path, error))
                self._meshes[path] = None
        return self._meshes[path]

    def system8(self, system, floor=False, cap_frames=None, once=False, source=None):
        """-> {file name suffix: ALO bytes} (particles.Converter._write) of a Niagara system (niagara.System), all
        its emitters in the floor's file when `floor`; cap_frames: the frames it may emit for (the stop); once: its
        spawn rates emit for one loop (cascade); source: its Tekken 8 id (the tune's per id values)."""
        docs = self._docs()
        doc = docs[1] if floor else docs[0]
        colour = palette(system)
        measured = getattr(self, 'measured', False)
        offset = (self.tune.get('offset') or {}).get(source)
        if measured:
            colour = measured_palette(system) or colour
        for e in system.emitters:
            if not e.enabled or (self.tune.get('skip') and re.search(self.tune['skip'], e.name)):
                continue
            for r in e.renderers:
                if not r.enabled:
                    continue
                if r.kind not in ('sprite', 'mesh'):
                    self.stats['left out (ribbons, lights)'] += 1
                    continue
                try:
                    mesh = r.meshes[0] if r.kind == 'mesh' and r.meshes else None
                    if r.kind == 'mesh' and mesh is None:
                        raise ValueError('a mesh renderer without a mesh')
                    sm = self._static_mesh(mesh[0]) if mesh else None
                    if mesh and sm is None:
                        raise ValueError('mesh %s not read' % mesh[0])
                    mat = mesh[1] if mesh else r.material
                    if mat and self.tune.get('skip_materials') and re.search(self.tune['skip_materials'], str(mat)):
                        continue
                    if measured:
                        roles = tuple((self.tune.get('system_roles') or {}).get(source, ())) + \
                            tuple(self.tune.get('roles', ()))
                        made = self._measured(e, r, mesh, sm, mat, floor, once, colour, offset, cap_frames, roles)
                    else:
                        alpha = self.materials.describe(mat)['alpha'] if mat else 1.0
                        made = self.emitter(cascade(e, r, colour, sm, floor, alpha, once, self.tune.get('roles', ())),
                                            cap_frames)
                except P.Invisible:
                    continue
                except (KeyError, ValueError, ZeroDivisionError, NotImplementedError, struct.error) as error:
                    self.log('effects: %s: emitter %s left out (%s)' % (system.name, e.name, error))
                    self.stats['dropped'] += 1
                    continue
                for em, tname, mname in made:
                    if len(doc['emitters']) >= P.MAX_EMITTERS:
                        break
                    self._append(doc, em, tname, mname)
        return self._write(docs)


def looped(i, stopped):
    """Whether effect i's spawn rates run until a move stops it: the emitters' loop behaviour (once or endless) is
    not read (a parameter of their EmitterState), so an id some move stops (stopped: moveset.Converter.
    effects8_stopped; None: all) loops, the others emit for one loop of each emitter (her horn's ring, 0.2 s)."""
    return stopped is None or i in stopped


def emitting_frames(systems, stopped=None):
    """{id: the frames after its start until which a Niagara system emits (rate and per-distance emitters: endless,
    particles.LOOP_CAP, or one loop when it is not looped(); later bursts), None when it only bursts at its start}
    (moveset.Converter.split_effects)."""
    out = {}
    for i, s in systems.items():
        end = 0.0
        for e in s.emitters:
            if not e.enabled:
                continue
            if e.rate > 0 or e.per_unit:
                end = max(end, P.LOOP_CAP if looped(i, stopped) or not e.loop else e.loop)
            for t, _ in e.bursts:
                end = max(end, t)
        out[i] = int(math.ceil(end * P.FPS)) if end * P.FPS > 2 else None
    return out


def systems_of(store, code, ids, log=None):
    """{id: niagara.System} of a fighter's effect ids (the ones its table names and that read)."""
    log = log or (lambda s: None)
    table = niagara.effect_table(store, code)
    out, read = {}, {}
    for i in sorted(ids):
        entry = table.get(i)
        if entry is None:
            log('effects: id %d is not in %s\'s effect table' % (i, code))
            continue
        path = entry['system']
        if path not in read:
            try:
                read[path] = niagara.read(store, path)
            except (KeyError, ValueError, NotImplementedError, struct.error) as error:
                log('effects: id %d (%s) not read: %s' % (i, path.rsplit('/', 1)[-1], error))
                read[path] = None
        if read[path] is not None:
            out[i] = read[path]
    return out


def convert_fighter(store, archives, systems, spec, first_texture_id, copies=None, log=None, stopped=None, tune=None,
                    trails=None):
    """The effects a fighter's moves spawn: systems {Tekken 8 id: niagara.System} (systems_of), spec {id: (part,
    floor)} (parts), copies {id: (Tekken 8 id, frames it may emit for)} (moveset.Converter.split_effects), stopped:
    the ids moves stop (looped), tune: the definition's TEKKEN8_EFFECT_TUNE ({'skip': emitter names left out,
    'skip_materials': renderers' materials left out, 'roles':
    its role()s}), trails: the weapon trails {id: trail} (moveset.Converter.assign_trails, trails8.py) -> (pack files
    {'alo/...': bytes}, {id: [effect names]})."""
    log = log or (lambda s: None)
    conv = Converter(store, archives, first_texture_id, log=log)
    conv.set_tune(tune)
    files, names = {}, {}
    for i, (source, cap) in sorted((copies or {i: (i, None) for i in systems}).items()):
        system = systems.get(source)
        if system is None:
            continue
        try:
            made = conv.system8(system, floor=spec.get(source, (0, False))[1], cap_frames=cap,
                                once=not looped(source, stopped), source=source)
        except (KeyError, ValueError) as error:
            log('effects: id %d (%s) left out: %s' % (i, system.name, error))
            continue
        for suffix, data in sorted(made.items()):
            name = EFFECT_NAME % i + suffix
            names.setdefault(i, []).append(name)
            files['alo/%s.alo' % name] = data
    for i, data in trails8.effects(conv, trails or {}).items():
        names[i] = [EFFECT_NAME % i]
        files['alo/%s.alo' % names[i][0]] = data
    for name, data in conv.textures.files.items():
        files['alo/texture/' + name] = data
    for name, data in conv.models.items():
        files['alo/model/' + name] = data
    log('effects: %d ids (%d of them copies; %d files, %d emitters, %d left out, %d ribbons and lights), %d textures '
        '(%d KB), %d meshes (%d KB)' % (len(names), sum(1 for i in names if (copies or {}).get(i, (i,))[0] != i),
                                        sum(map(len, names.values())), conv.stats['emitters'], conv.stats['dropped'],
                                        conv.stats['left out (ribbons, lights)'], len(conv.textures.files),
                                        sum(map(len, conv.textures.files.values())) // 1024, len(conv.models),
                                        sum(map(len, conv.models.values())) // 1024))
    return files, names
