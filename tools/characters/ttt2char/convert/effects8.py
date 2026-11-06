"""Tekken 8's effects (Niagara systems: tekken8/niagara.py) as TTT2 effect files (ALO), for the effects a fighter's
moves spawn that its definition attaches to a body part (TEKKEN8_EFFECTS).

A Tekken 8 move spawns an effect by id with 0x8039 (value: the id) and stops a looping one with 0x8035 (the same
value); the fighter's effect table (DA_CharacterEffect_<CODE>) names the Niagara system of each id. particles.py's
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
Ribbons and lights are left out.

Written for this project from the files themselves (no third-party code).
"""
import math
import re
import struct

import numpy as np

from . import particles as P
from ..tekken7.particles import Distribution, Emitter
from ..tekken8 import material as material8, niagara, staticmesh as staticmesh8, texture as texture8

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
# yaw_rate (a mesh's spin, turns/s), tumble (a mesh's random turn), rate (the spawn by distance, per second).
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


def role(name):
    for pattern, values in ROLES:
        if re.search(pattern, name, re.I):
            return dict(DEFAULT_ROLE, **values)
    return dict(DEFAULT_ROLE)


def cascade(e, r, colour, sm=None, floor=False, alpha=1.0, once=False):
    """The Cascade emitter (tekken7.particles.Emitter of Module stand-ins) particles.Converter converts for Niagara
    emitter e drawn by renderer r. colour: the particles' (linear, before the brightness) when e has no colour array;
    sm: the mesh of a mesh renderer (staticmesh8.StaticMesh); floor: placed from the floor; alpha: the material's
    opacity factor (AlphaMult); once: a spawn rate emits for one loop (looped(): no move stops the system)."""
    ro = role(e.name)
    cpu = cpu_values(e) if not e.gpu else {}
    mesh, mat = (r.meshes[0] if r.kind == 'mesh' and r.meshes else (None, r.material))
    life = cpu.get('life') or ro['life']
    duration = float(e.loop or 1.0)
    looping = (e.rate > 0 or e.per_unit) and not (once and e.loop)
    rate = e.rate if e.rate > 0 else (ro['rate'] if e.per_unit else 0.0)
    mods = [Module('Required', {'Material': mat or (sm.materials[0] if sm is not None and sm.materials else None),
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
        mods.append(Module('ColorOverLife', {}, {'AlphaOverLife': over_life(fade, 1)}))
    speed = ro.get('speed')
    if speed:
        lift = ro.get('lift', 0.0)
        mods.append(Module('Velocity', {}, {'StartVelocity': ranged([0.0, 0.0, lift], list(speed), 3)}))
    if ro.get('drag'):
        mods.append(Module('AccelerationDrag', {}, {'DragCoefficientRaw': ranged(ro['drag'])}))
    if ro.get('box'):
        mods.append(Module('Location', {}, {'StartLocation': ranged([0.0, 0.0, 0.0], list(ro['box']), 3)}))
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


# ------------------------------------------------------------------------------------------------ materials, textures
class Materials:
    """Tekken 8 effect materials described as particles.py reads Tekken 7's (EffectMaterials.describe): textures
    (a mask alone is the shape: BaseTexture), scalars (ColorMult as a colour power), vectors (the tornado family's
    names as the others'), switches, blend (translucent, or additive), base, two_sided; also 'alpha' (AlphaMult)."""
    TEXTURES = {'BaseTex': 'BaseTexture', 'MaskTex': 'MaskTexture'}
    VECTORS = {'BaseTexTile': 'BaseTexTilling'}

    def __init__(self, store):
        self.m = material8.Materials(store)
        self._done = {}

    def describe(self, path):
        if path in self._done:
            return self._done[path]
        eff = self.m.effective(path)
        tex = {self.TEXTURES.get(k, k): v for k, v in eff['textures'].items() if v}
        if not tex.get('BaseTexture') and tex.get('MaskTexture'):
            tex['BaseTexture'] = tex.pop('MaskTexture')
        scalars = dict(eff['scalars'])
        if 'ColorMult' in scalars and 'ColorBoost' not in scalars:
            scalars['ColorBoost'] = scalars['ColorMult']
        vectors = {self.VECTORS.get(k, k): v for k, v in eff['vectors'].items()}
        col = vectors.get('Col1')                 # (the tornado family's colour: its hue, its peak as a power)
        if col and 'add_color' not in vectors:
            peak = max(col['r'], col['g'], col['b'])
            if peak > 0:
                vectors['add_color'] = {'r': col['r'] / peak, 'g': col['g'] / peak, 'b': col['b'] / peak}
                scalars['Color Power'] = min(MAX_BRIGHTNESS, peak)
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


class Textures(P.Textures):
    """particles.Textures reading Tekken 8's textures, lit with their hue kept (lit_texels)."""

    def __init__(self, store, first):
        super().__init__(None, first)
        self.store = store

    def lit(self, src, peak, peak_alpha, additive):
        q = lambda x: round(math.log2(max(x, 1.0 / 64)) * 4) / 4                   # (particles.Textures.lit's steps)
        p = tuple(2.0 ** q(x) if x > 1.0 / 128 else 0.0 for x in peak)
        pa = 2.0 ** q(peak_alpha)
        key = ('lit8', src.key, p, pa, additive)
        if key not in self._by_key:
            self.bake(key, np.round(lit_texels(src.img, p, min(pa, P.MAX_ALPHA_GAIN), additive) * 255.0), src.side)
        return self._by_key[key]

    def image(self, path):
        return texture8.Texture2D(self.store, material8.package_of(path)).decode(TEXTURE_MIP)

    def linear_image(self, path):
        t = texture8.Texture2D(self.store, material8.package_of(path))
        img = t.decode(TEXTURE_MIP).astype(np.float32) / 255.0
        if t.srgb:
            img[..., :3] = img[..., :3] ** P.GAMMA
        return img


# ------------------------------------------------------------------------------------------------ converter
class Converter(P.Converter):
    """Converts a fighter's Tekken 8 Niagara systems (textures and meshes shared by its effects)."""

    def __init__(self, store, archives, first_texture_id, log=None):
        super().__init__(None, archives, first_texture_id, log)
        self.store = store
        self.materials = Materials(store)
        self.textures = Textures(store, first_texture_id)
        self.stats.update({'left out (ribbons, lights)': 0})

    def _static_mesh(self, path):
        if path not in self._meshes:
            try:
                self._meshes[path] = staticmesh8.StaticMesh(self.store, path)
            except (KeyError, ValueError, struct.error) as error:
                self.log('effects: mesh %s not read (%s)' % (path, error))
                self._meshes[path] = None
        return self._meshes[path]

    def system8(self, system, floor=False, cap_frames=None, once=False):
        """-> {file name suffix: ALO bytes} (particles.Converter._write) of a Niagara system (niagara.System), all
        its emitters in the floor's file when `floor`; cap_frames: the frames it may emit for (the stop); once: its
        spawn rates emit for one loop (cascade)."""
        docs = self._docs()
        doc = docs[1] if floor else docs[0]
        colour = palette(system)
        for e in system.emitters:
            if not e.enabled:
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
                    alpha = self.materials.describe(mat)['alpha'] if mat else 1.0
                    made = self.emitter(cascade(e, r, colour, sm, floor, alpha, once), cap_frames)
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


def convert_fighter(store, archives, systems, spec, first_texture_id, copies=None, log=None, stopped=None):
    """The effects a fighter's moves spawn: systems {Tekken 8 id: niagara.System} (systems_of), spec {id: (part,
    floor)} (parts), copies {id: (Tekken 8 id, frames it may emit for)} (moveset.Converter.split_effects), stopped:
    the ids moves stop (looped) -> (pack files {'alo/...': bytes}, {id: [effect names]})."""
    log = log or (lambda s: None)
    conv = Converter(store, archives, first_texture_id, log=log)
    files, names = {}, {}
    for i, (source, cap) in sorted((copies or {i: (i, None) for i in systems}).items()):
        system = systems.get(source)
        if system is None:
            continue
        try:
            made = conv.system8(system, floor=spec.get(source, (0, False))[1], cap_frames=cap,
                                once=not looped(source, stopped))
        except (KeyError, ValueError) as error:
            log('effects: id %d (%s) left out: %s' % (i, system.name, error))
            continue
        for suffix, data in sorted(made.items()):
            name = EFFECT_NAME % i + suffix
            names.setdefault(i, []).append(name)
            files['alo/%s.alo' % name] = data
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
