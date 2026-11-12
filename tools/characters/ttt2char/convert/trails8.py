"""Tekken 8's weapon trails (Kiseki) as TTT2 effects: the flame arc behind Victor's sword.

Tekken 8 starts a trail with property TRAIL (0x831c; value parts << 24 | frames << 16 | tail << 8 | kind) and ends it
with TRAIL_END. `parts` numbers a row of DA_<CODE>_KisekiList: a weapon with two sockets (First: the blade's far end;
Second: its near end, on a joint of the weapons' mesh, offsets in tenths of a metre), a Width and a FrameScale curve
over the age; `kind` a row of DA_<CODE>_KisekiKindList: the materials (M_EF_Ant_Trail_TL instances) of the ribbon. Each
frame the ribbon gets a new slice along the blade; `tail` frames later that slice has gone: FrameScale shrinks it towards
the blade's far end as it ages, and the materials' masks fade it. Their texture U runs across the blade, V along the
ribbon (1 at the head).

TTT2's effects have no ribbon that follows a moving emitter (its strip is a stretched quad), and none is needed: a move's
animation says where the blade will be. So one model particle draws the whole swept surface, in the fighter's level facing
frame at his hips when the trail starts, left where it is (the blade's way baked from the converted animation, root motion
included), its V = -(frame of the slice) / P, and the texture scrolls by 1 / P a frame. What a texel shows then depends
on (the slice's age, the place across the blade), exactly what the ribbon's look depends on, so it is baked once a kind
(bake), with the shrinking in it. The title's samplers repeat, so the texture is clear outside age 0 .. tail: a period P
of more than frames + tail frames shows neither the slices to come nor those gone, and the particle dies with its last
slice.

M_EF_Ant_Trail_TL's graph is not in the files (cooked): its parameters are combined as their names say (`layer`), and what
that cannot give comes from Tekken 8's frames by eye: a fire's colours (`fire`), the rim's shape, what a trail leaves in
the air (Niagara systems in Tekken 8, generated here: `left_behind`).
Written for this project from the files themselves (no third-party code).
"""
import copy
import math

import numpy as np

from . import particles as P, retarget, strips
from ..tekken8 import anmbin, material as material8, panm, texture as texture8, uprops
from ..ttt2 import alo, animation, nud

TRAIL, TRAIL_END = 0x831c, 0x831d
SOCKET_MM = 100.0                   # a socket offset's unit (the knife's tip: 2.4, 24 cm from its joint)
SOCKET_AXES = np.array([1.0, -1.0, 1.0])    # the mesh's joint frame -> the clips' (and so the weapon bones'): y reversed
LIST = '/Game/Character/Trace/%s/DA_%s_KisekiList'
ACROSS, ALONG = 256, 1024           # the baked look's size: across the blade, along the texture's period (ages)
SMALL_BLADE = 700.0                 # a look only blades shorter than this (mm) draw: half that size
RIM = 0.1                           # the look reaches this share of the blade beyond the far socket (its rim's glow)
SLICE_MM = 40.0                     # the far end's way between two slices, at most ...
MAX_SLICES = 16                     # ... with at most this many slices a frame
ROWS = 9                            # rows of vertices across the blade (few draw a shrinking edge as teeth)
TEXTURE_MIP = 128                   # the mip of Tekken 8's textures the look is baked from
EXPOSURE = 0.2                      # a kind's light -> Tekken 8's picture (by its frames)
BLEED = np.array([0.009, 0.009, 0.0012], np.float32)   # the share of a colour's peak the picture's curve spreads to the
                                                    # other channels
FLAME_V = 3.0                       # the flames' textures go back and forth along the ribbon (their blobs' length by
FLAME_ROWS = 0.8                    # Tekken 8's frames), without their last rows (the white foot of a flame sheet)
DARKEST = 0.5                       # (Tekken 8's dark patches are dark red, not black)
RIM_BOOST = 4.0                     # (the rim glows: its colour has no bloom here)
HOT = 0.2, 0.3                      # how much brighter at the head, and the age it is gone at (by Tekken 8's frames)
FIRE_RANGE = 3, 99.5                 # the percentiles of a fire's light (log) that its colours run between
FIRE_RAMP = ((0.0, 0.3, 0.55, 0.75, 0.9, 1.0),      # its colours, by Tekken 8's frames (dark patches are dark red)
             (110, 200, 240, 252, 255, 255), (20, 40, 85, 150, 215, 240), (14, 18, 24, 50, 120, 205))
HEAD = 0.12                         # a rim's head: how far back (age) a round one starts at its ends
RIM_ENDS = (0.6, 0.85)              # the ages its strip fades over
WISP_FRAMES, WISP_SPEED = 4, 150.0  # a fire leaves clouds every so many frames it flies at least this fast (mm a frame):
WISP_LIFE, WISP_SIZE, WISP_SPREAD, WISP_ALPHA = 30, 620.0, 260.0, 0.6   # by Tekken 8's frames
WISP_COLOUR = (1.0, 0.5, 0.22)
FLECK_LIFE, FLECK_SIZE, FLECK_SPREAD = 22, 360.0, 170.0     # by Tekken 8's frames
FLECK_COLOUR = (0.8, 0.9, 1.0)
SPAWN_LAG = 0                       # clip frames from a move's frame - 1 to the head of the trail's first slice
ANCHOR_LAG = 0                      # ... to the hips' place an effect started in that frame takes


def decode(value):
    """A TRAIL row's value -> (parts, frames, tail, kind)."""
    return value >> 24 & 0xFF, value >> 16 & 0xFF, value >> 8 & 0xFF, value & 0xFF


def _asset(store, path):
    pkg = store.package(path.split('.')[0])
    return uprops.read(pkg, pkg.main_export())[0]


def _curve(store, path):
    """A curve asset's FloatCurve keys [(time, value)]."""
    keys = _asset(store, path)['FloatCurve']['Keys']
    return [(float(k.get('Time') or 0.0), float(k.get('Value') or 0.0)) for k in keys]


def assets(store, code):
    """The fighter's trail data: ({parts: {'first': (joint, offset), 'second': (joint, offset), 'width', 'scale': keys}},
    {kind: {'materials': [paths], 'edge': the last material lies on the ribbon's rim}})."""
    parts, kinds = {}, {}
    for n, path in enumerate(_asset(store, LIST % (code, code.upper()))['PartsDataAssetTable']):
        a = _asset(store, path)
        s = a['PartsSettingTable'][0]
        off = lambda o: tuple(float((o or {}).get(c) or 0.0) for c in 'XYZ')
        parts[n] = dict(first=(a['FirstEffectPartsId'], off(a.get('FirstSocketOffset'))),
                        second=(a['SecondEffectPartsId'], off(a.get('SecondSocketOffset'))),
                        width=float(s.get('Width') or 1.0), scale=_curve(store, s['FrameScale']))
        if not kinds:
            for row in _asset(store, s['KindDataAssetList'])['KindSettingTable']:
                k = _asset(store, row['KindDataAsset'])
                mesh = _asset(store, k['MeshSetting'])['SkeletalMesh']
                kinds[int(row.get('TraceKindId') or 0)] = dict(materials=list(k['MaterialArray']),
                                                               edge=mesh.split('.')[0].endswith('_edge'))
    return parts, kinds


def socket(offset):
    """A socket offset -> mm in the weapon bone's frame."""
    return np.asarray(offset, np.float64) * SOCKET_MM * SOCKET_AXES


def weapon_frames(conv, skeleton, values, weapon):
    """(rotations (F, 3, 3), places (F, 3)) of a weapon's bone through a clip (conv.channels' values) in the clip's frame
    (mm; x left, y up, z forward; root motion in them): conv anim.Converter, skeleton its TTT2 skeleton, weapon a
    definition's WEAPONS entry."""
    WR, Wp = retarget.pose(skeleton, values[:, :23], animation.COMPRESSED)
    up = skeleton.index[weapon['parent']]
    channel = 23 + 2 * int(weapon['pair'])
    if channel + 1 < values.shape[1]:
        t = values[:, channel]
        R = animation.local_rotation(values[:, channel + 1], animation.COMPRESSED)
    else:                                       # (a clip that does not move the weapons: their bind)
        t0, R0 = conv.pairs[int(weapon['pair'])]['bind']
        t = np.repeat(np.asarray(t0, np.float64)[None], len(values), 0)
        R = np.repeat(np.asarray(R0, np.float64)[None], len(values), 0)
    return WR[:, up] @ R, Wp[:, up] + np.einsum('fij,fj->fi', WR[:, up], t)


def level_frame(values, skeleton, f):
    """Where a body part 0 effect started at clip frame f sits, in the clip's frame: (its axes as columns (x left, y up,
    z forward), the hips' place). TTT2's level frame is the model root's rotation, the hips' without their own: the
    clip's turn."""
    WR, Wp = retarget.pose(skeleton, values[f:f + 1, :23], animation.COMPRESSED)
    return animation.local_rotation(values[f, 2], animation.COMPRESSED), Wp[0, 0]


class Sampler:
    """The blade's way in a fighter's moves: (move, its frame the trail starts at, frames, TRAIL value) -> a trail
    (dict: far, near (frames + 1, 3) in the effect's frame, tail, kind, scale, width), or None (no clip; no such weapon)."""

    def __init__(self, store, d, k, banks, conv, target):
        self.parts, self.kinds = assets(store, d.TEKKEN8_CODE)
        self.weapons = {w['bone']: w for w in getattr(d, 'WEAPONS', ())}
        self.looks = getattr(d, 'TEKKEN8_TRAIL_LOOKS', {})
        self.sockets = getattr(d, 'TEKKEN8_TRAIL_SOCKETS', {})      # (a joint no weapon has -> (a weapon's bone, offset))
        self.k, self.banks, self.conv = k, banks, conv
        self.skeleton = retarget.ttt2_skeleton(target)
        self._clips = {}

    def clip(self, move):
        key = self.k.anim_ref(move)[0]
        if key not in self._clips:
            blob = self.banks.blob(anmbin.BODY, key) if key is not None else None
            self._clips[key] = self.conv.channels(panm.Animation(blob))[0] if blob else None
        return self._clips[key]

    def __call__(self, move, start, frames, value):
        parts, _, tail, kind = decode(value)
        values = self.clip(move)
        part = self.parts.get(parts)
        if values is None or part is None or kind not in self.kinds:
            return None
        sockets = [self.sockets.get(part[n][0], (part[n][0], (0.0, 0.0, 0.0))) for n in ('first', 'second')]
        sockets = [(j, np.add(o, part[n][1])) for (j, o), n in zip(sockets, ('first', 'second'))]
        if any(j not in self.weapons for j, _ in sockets):
            return None
        first = max(0, start - 1 + SPAWN_LAG)   # (a move's frame f shows its clip's frame f - 1)
        last = min(len(values) - 1, first + frames)
        if last <= first:
            return None
        ends = []
        for joint, offset in sockets:
            R, t = weapon_frames(self.conv, self.skeleton, values[first:last + 1], self.weapons[joint])
            ends.append(t + np.einsum('fij,j->fi', R, socket(offset)))
        R0, p0 = level_frame(values, self.skeleton, max(0, start - 1 + ANCHOR_LAG))
        to_effect = lambda x: (x - p0) @ R0
        # (an emitter started later is placed from the hips of that moment: where the far end is seen from them)
        _, Wp = retarget.pose(self.skeleton, values[first:last + 1, :23], animation.COMPRESSED)
        turns = animation.local_rotation(values[first:last + 1, 2], animation.COMPRESSED)
        seen = np.einsum('fj,fji->fi', ends[0] - Wp[:, 0], turns)
        return dict(far=to_effect(ends[0]), near=to_effect(ends[1]), seen=seen, tail=max(1, tail),
                    kind=dict(self.kinds[kind], **self.looks.get(kind, {})), kind_id=kind, scale=part['scale'], width=part['width'],
                    blade=float(np.linalg.norm(socket(sockets[0][1]) - socket(sockets[1][1])) * part['width']))


def catmull(p, t):
    """Points (n, 3) at a time t in frames (0 .. n - 1), through them (Catmull-Rom)."""
    n = len(p)
    i = min(n - 2, int(t)) if n > 1 else 0
    if n < 2:
        return p[0]
    s = t - i
    a, b, c, d = p[max(0, i - 1)], p[i], p[i + 1], p[min(n - 1, i + 2)]
    return 0.5 * (2 * b + (c - a) * s + (2 * a - 5 * b + 4 * c - d) * s * s + (3 * b - a - 3 * c + d) * s * s * s)


def sweep(far, near):
    """Slices of a ribbon from the blade's far and near end per frame (F, 3): (times [frames], far ends, near ends):
    more than one a frame where the far end flies."""
    times = [0.0]
    for f in range(len(far) - 1):
        n = min(MAX_SLICES, max(1, int(math.ceil(np.linalg.norm(far[f + 1] - far[f]) / SLICE_MM))))
        times += [f + (k + 1) / n for k in range(n)]
    return (np.array(times), np.array([catmull(far, t) for t in times]), np.array([catmull(near, t) for t in times]))


def mesh(times, far, near, period, width):
    """The swept surface: (positions (m, 3), uv (m, 2), triangles (t, 3)): near pulled out to `width` x the blade from
    its far end, RIM beyond the far end; u across (0 beyond the far end .. 1 at the near), v -slice frame / period."""
    span = (near - far) * width
    rows = np.linspace(0.0, 1.0, ROWS)
    pos, uv = [], []
    for k, t in enumerate(times):
        for q in rows:
            pos.append(far[k] + span[k] * (q * (1.0 + RIM) - RIM))
            uv.append((q, -t / period))
    tris = []
    for k in range(len(times) - 1):
        for r in range(ROWS - 1):
            a, b = k * ROWS + r, k * ROWS + r + 1
            c, d = a + ROWS, b + ROWS
            tris += [(a, c, b), (b, c, d)]
    return np.array(pos, np.float32), np.array(uv, np.float32), np.array(tris, np.int64)


# ------------------------------------------------------------------------------------------------ the look
def _sample(img, u, v, wrap=True):
    """Bilinear lookup in an image (h, w, c) at u, v arrays (0 .. 1 the image; repeated, or held at the edges)."""
    h, w = img.shape[:2]
    x, y = u * w - 0.5, v * h - 0.5
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    if wrap:
        ix = lambda a: a % w
        iy = lambda a: a % h
    else:
        ix = lambda a: np.clip(a, 0, w - 1)
        iy = lambda a: np.clip(a, 0, h - 1)
    a = img[iy(y0), ix(x0)] * (1 - fx) + img[iy(y0), ix(x0 + 1)] * fx
    b = img[iy(y0 + 1), ix(x0)] * (1 - fx) + img[iy(y0 + 1), ix(x0 + 1)] * fx
    return a * (1 - fy) + b * fy


def _rotated(u, v, degrees):
    """UV turned about the middle."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    du, dv = u - 0.5, v - 0.5
    return c * du - s * dv + 0.5, s * du + c * dv + 0.5


def keys_at(keys, t):
    """A curve's keys [(time, value)] at times t (linear; held outside them)."""
    return np.interp(t, [k[0] for k in keys], [k[1] for k in keys])


def _image(store, path, cache):
    """A texture as float RGBA, its colour linear; None: a plain white one. (A low mip: at the sizes a ribbon draws them
    Tekken 8's streaks are blobs.)"""
    if not path or 'white' in path.rsplit('/', 1)[-1].lower():
        return None
    if path not in cache:
        t = texture8.Texture2D(store, material8.package_of(path))
        img = t.decode(TEXTURE_MIP).astype(np.float32) / 255.0
        if t.srgb:
            img[..., :3] = img[..., :3] ** 2.2
        cache[path] = img
    return cache[path]


def layer(store, eff, u, v, cache=None):
    """What a M_EF_Ant_Trail_TL instance (material8.effective) draws at texture places u, v: (linear colour (.., 3), its
    opacity (..)), or None when it only bends the picture (Alpha 0, Tekken 8's refraction layer). colour = BaseTexture^
    ColorPower x BaseTexColor x ColorBoost + BaseTexture2^Color2Power x BaseTex2Color x ColorBoost2 (a white one adds a
    plain colour), x HDRBoostColor squared when its switch is on; opacity = MaskTexture (turned by MaskTexRotate)^
    MaskPower x MaskMult x (half) BaseTexture (its switch UseColforAlpha) x Alpha."""
    sc, vec, tex = eff['scalars'], eff['vectors'], eff['textures']
    alpha = float(sc.get('Alpha') or 0.0)
    if alpha <= 0.0:
        return None
    cache = {} if cache is None else cache

    def term(name, tiling, power, colour, boost, floor=0.0):
        c = vec.get(colour) or {}
        rgb = np.array([float(c.get(k) or 0.0) for k in 'rgb'], np.float32) * float(sc.get(boost) or 1.0)
        img = _image(store, tex.get(name), cache)
        if img is None:
            return np.broadcast_to(rgb, u.shape + (3,)), np.ones_like(u)
        along = np.abs((v * FLAME_V * float(sc.get(tiling + 'V') or 1.0) / 2.0) % 1.0 * 2.0 - 1.0) * FLAME_ROWS + 0.02
        got = _sample(img, u * float(sc.get(tiling + 'U') or 1.0), along)[..., 0]
        got = np.maximum(got, 1e-6) ** float(sc.get(power) or 1.0)
        return np.maximum(got, floor)[..., None] * rgb, got
    c1, a1 = term('BaseTexture', 'BaseTexTiling', 'ColorPower', 'BaseTexColor', 'ColorBoost', DARKEST)
    c2, _ = term('BaseTexture2', 'BaseTex2Tiling', 'Color2Power', 'BaseTex2Color', 'ColorBoost2')
    mask = _image(store, tex.get('MaskTexture'), cache)
    opacity = np.ones_like(u)
    if mask is not None:
        opacity = _sample(mask, *_rotated(u, v, float(sc.get('MaskTexRotate') or 0.0)), wrap=False)[..., 0]
    opacity = np.maximum(opacity, 1e-6) ** float(sc.get('MaskPower') or 1.0) * float(sc.get('MaskMult') or 1.0)
    boost = float(sc.get('HDRBoostColor') or 1.0) ** 2 if eff['switches'].get('bUseHDRBoost_Color') else 1.0
    return (c1 + c2) * boost, np.clip(opacity * (0.5 + 0.5 * a1) * alpha, 0.0, 1.0)


def _step(a, b, x):
    """0 below a, 1 above b, smooth between."""
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def shown(colour, exposure):
    """A linear colour as Tekken 8's picture shows it (sRGB 0 .. 1): a filmic curve, whose reds in the tens go orange,
    then cream (BLEED)."""
    e = (colour + colour.max(-1, keepdims=True) * BLEED) * exposure
    return (e / (1.0 + e)) ** (1.0 / 2.8)


def fire(plain, alpha, age):
    """A fire's light -> its picture: how bright it is through the colours of Tekken 8's flames, brighter at the head."""
    lit = np.log1p(np.maximum(plain @ np.array([0.5, 0.4, 0.1], np.float32), 0.0))
    low, high = np.percentile(lit[alpha > 0.5], FIRE_RANGE) if np.any(alpha > 0.5) else (0.0, 1.0)
    t = ((lit - low) / max(high - low, 1e-3) + HOT[0] * (1.0 - _step(0.0, HOT[1], age))) * np.minimum(alpha / 0.4, 1.0)
    return np.stack([np.interp(t, FIRE_RAMP[0], c) for c in FIRE_RAMP[1:]], -1).astype(np.float32) / 255.0


GLASS, GLASS_RIM, GLASS_GLINT = (0.14, 0.2, 0.27), (0.86, 0.93, 0.97), (0.95, 0.98, 1.0)      # by Tekken 8's frames


def glass(store, materials, kind, scale, tails, along, across):
    """A kind (the definition's TEKKEN8_TRAIL_LOOKS 'glass') Tekken 8 draws by bending the picture: its first layer's shape
    as a slate shadow towards the far end, its second's as white glints, a thin pale line outside. Its Mask's U 1 is the
    far end, V 1 the head."""
    age = np.minimum((np.arange(along, dtype=np.float32) + 0.5) / along * tails, 1.0)
    q = (np.arange(across, dtype=np.float32) + 0.5) / across
    a, q = np.meshgrid(age, q, indexing='ij')
    x = q * (1.0 + RIM) - RIM
    inside = x / np.maximum(keys_at(scale, a), 1e-3)
    u, v = np.clip(1.0 - inside, 0.0, 1.0), 1.0 - a
    first, second = [materials.effective(path)['textures'] for path in kind['materials'][:2]]
    cache = {}
    plain = lambda t: _image(store, t, cache)[..., 0:1]
    shade = _sample(plain(first['MaskTexture']), u, v, wrap=False)[..., 0] * \
        _sample(plain(first['BaseTexture']), u, v, wrap=False)[..., 0]
    glint = _sample(plain(second['BaseTexture']), u, v * 2.0)[..., 0] * \
        _sample(plain(second['MaskTexture']), u, v, wrap=False)[..., 0]
    alpha = np.clip(shade ** 0.8 * kind.get('shade', 0.6), 0.0, 1.0) * (inside >= 0.0) * (inside <= 1.0)
    rgb = np.broadcast_to(np.array(GLASS, np.float32), a.shape + (3,)).copy()
    opacity = np.clip((glint - 0.1) * 2.5, 0.0, 0.7) * (inside >= 0.0) * (inside <= 1.0)
    rgb = (rgb * (alpha * (1.0 - opacity))[..., None] + np.array(GLASS_GLINT, np.float32) * opacity[..., None]) / \
        np.maximum(opacity + alpha * (1.0 - opacity), 1e-4)[..., None]
    alpha = opacity + alpha * (1.0 - opacity)
    rim = _step(-0.03, -0.015, inside) * (1.0 - _step(0.0, 0.01, inside)) * (1.0 - _step(0.35, 0.8, a)) * _step(0.0, 0.05, a) * 0.8
    rgb = (rgb * (alpha * (1.0 - rim))[..., None] + np.array(GLASS_RIM, np.float32) * rim[..., None]) / \
        np.maximum(rim + alpha * (1.0 - rim), 1e-4)[..., None]
    alpha = rim + alpha * (1.0 - rim)
    out = np.dstack([rgb, alpha])
    out[0, :, 3] = out[-1, :, 3] = 0.0
    out[a >= 1.0, 3] = 0.0
    out[:, 0, 3] = out[:, -1, 3] = 0.0
    return np.round(np.clip(out, 0.0, 1.0) * 255.0)


def bake(store, materials, kind, scale, tails=1.0, along=ALONG, across=ACROSS, exposure=EXPOSURE):
    """The look of a kind (assets) as RGBA (along, across, 4) 0 .. 255: y the slice's age, `tails` tails from the top to
    the bottom (0 the head), x across the blade (the mesh's u). materials: material8.Materials; scale: the parts'
    FrameScale keys over the age. The layers add up as Tekken 8's translucent ones do (light + what shows through x (1 -
    opacity)). An _edge mesh's last layer lies on a strip round the rim and a round head (its UVs are not readable: their
    shape by Tekken 8's frames, the colour the material's). A kind's 'edge' and 'body' can come from the definition's
    TEKKEN8_TRAIL_LOOKS: body scales the opacity of all but the rim. A fire is coloured by `fire`."""
    age = np.minimum((np.arange(along, dtype=np.float32) + 0.5) / along * tails, 1.0)
    q = (np.arange(across, dtype=np.float32) + 0.5) / across
    if kind.get('glass'):
        return glass(store, materials, kind, scale, tails, along, across)
    a, q = np.meshgrid(age, q, indexing='ij')
    x = q * (1.0 + RIM) - RIM                   # share of the blade from the far end: 0 .. 1 the band
    w = np.maximum(keys_at(scale, a), 1e-3)
    inside = x / w                              # across the shrunk slice
    light = np.zeros(a.shape + (3,), np.float32)
    alpha = np.zeros(a.shape, np.float32)
    cache = {}
    paths = kind['materials']
    drawn = [(n, layer(store, materials.effective(path), np.clip(inside, 0.0, 1.0), 1.0 - a, cache))
             for n, path in enumerate(paths)]
    for n, got in drawn:
        if got is None or kind['edge'] and n == len(paths) - 1:
            continue
        colour, opacity = got
        opacity = opacity * ((inside >= 0.0) & (inside <= 1.0))
        light = colour * opacity[..., None] + light * (1.0 - opacity[..., None])
        alpha = opacity + alpha * (1.0 - opacity)
    light, alpha = light * kind.get('body', 1.0), alpha * kind.get('body', 1.0)
    plain = light / np.maximum(alpha, 1e-3)[..., None]
    peak = np.percentile(plain[alpha > 0.5].reshape(-1, 3), 90, axis=0) if np.any(alpha > 0.5) else np.zeros(3)
    rgb = shown(plain, exposure)
    if peak[0] > 2.0 * peak[2]:                 # a fire
        rgb = fire(plain, alpha, a)
    if kind['edge'] and drawn[-1][1] is not None:
        start = HEAD * (1.0 - np.sqrt(np.maximum(1.0 - (2.0 * np.clip(inside, 0.0, 1.0) - 1.0) ** 2, 0.0)))     # (round)
        alpha = alpha * _step(start, start + 0.015, a)
        edge = _step(-0.05, 0.0, inside) * (1.0 - _step(0.02, 0.12, inside)) * _step(0.0, 0.02, a) * \
            (1.0 - _step(*RIM_ENDS, a))
        round_it = _step(start - 0.01, start, a) * (1.0 - _step(start + 0.015, start + 0.05, a)) * (1.0 - _step(0.4, 0.9, inside))
        opacity = np.maximum(edge, round_it * (inside >= 0.0))
        colour = shown(drawn[-1][1][0] * RIM_BOOST, exposure)
        rgb = colour * opacity[..., None] + rgb * (1.0 - opacity[..., None])
        alpha = opacity + alpha * (1.0 - opacity)
    out = np.dstack([rgb, alpha])
    out[0, :, 3] = out[-1, :, 3] = 0.0          # (clear beyond the head and the tail)
    out[a >= 1.0, 3] = 0.0
    out[:, 0, 3] = out[:, -1, 3] = 0.0
    return np.round(np.clip(out, 0.0, 1.0) * 255.0)


# ------------------------------------------------------------------------------------------------ the files
def model(conv, name, times, far, near, period, width, tex_id):
    """The swept surface as an effect model: writes conv.models[name]."""
    pos, uv, tris = mesh(times, far, near, period, width)
    m = copy.deepcopy(conv.nud_template)
    one = m['meshes'][0]
    poly = one['polys'][0]
    v = np.zeros(len(pos), poly['verts'].dtype)
    v['pos'] = pos
    v['nrm'][:, 1] = v['nrm'][:, 3] = 1.0
    if 'color' in v.dtype.names:
        v['color'] = P.VERTEX_WHITE
    v['uv'][:, 0, :] = uv
    poly['verts'] = v
    poly['indices'] = np.array(strips.stripify(tris), np.uint16)
    for mat in poly['materials']:
        mat['src'], mat['dst'] = P.MODEL_ALPHA
        mat['cull'] = 0                         # (seen from both sides)
        for t in mat['textures']:
            t['id'] = tex_id
    c = (pos.min(0) + pos.max(0)) / 2
    r = float(np.linalg.norm(pos - c, axis=1).max())
    m['sphere'] = one['sphere'] = (float(c[0]), float(c[1]), float(c[2]), r)
    one['center'] = (float(c[0]), float(c[1]), float(c[2]))
    conv.models[name] = nud.write(m)


def emitter(conv, name, tex, life, period):
    """One model particle left where the effect starts, its texture scrolling once in `period` frames."""
    e = copy.deepcopy(conv.model_tmpl)
    alo.unpin(e)
    sp, pa = e['spawner'], e['particle']
    sp['modifiers'] = []
    P._set(sp, '>B', 251, 0)
    P._set(sp, '>I', 136, P.SFLAG_MODEL)
    P._set(sp, '>I', 236, P.MODEL_BLEND_ALPHA)
    P._set(pa, '>I', alo.START_FLAGS, P.PFLAG_DIRECTED)
    P._set(pa, '>B', alo.SHAPE, 0)
    pa.pop('shape', None)
    e['name'] = name
    P._set(sp, '>HH', alo.LIFE, P._u16(life), 0)
    P._set(sp, '>ffff', alo.SIZE, 1.0, 1.0, 0.0, 0.0)
    P._set(sp, '>12f', 164, *([0.0] * 12))
    P._set(sp, '>6f', 212, *([0.0] * 6))
    P._set(sp, '>fff', 12, 0.0, 0.0, 0.0)
    P._set(sp, '>f', 36, 0.0)
    P._set(sp, '>fff', 120, 0.0, 0.0, 0.0)
    alo.set_emitter_colour(e, [1.0, 1.0, 1.0])
    for o, keys in ((alo.COLOUR_TRACK, [[0, 1.0, 1.0, 1.0]]), (alo.ALPHA_TRACK, [[0, 1.0]]), (alo.SIZE_TRACK, [[0, 1.0]]),
                    (84, [[0, 0.0]]), (96, [[0, 0.0]]), (108, [[0, 0.0]])):
        alo._set_keys(sp['tracks'][o], keys)
    for o in (4, 16, 28, 40):
        alo._set_keys(pa['tracks'][o], [[0, 0.0]])
    alo._set_keys(pa['tracks'][64], [[0, 0.0, 0.0, 0.0]])
    P._set(pa, '>fff', 76, 0.0, 0.0, 0.0)
    P._set(e, '>HHHHHH', alo.INTERVAL, 0xFFFF, 0, 1, 0, 0, 0)
    alo._set_keys(pa['tracks'][alo.COUNT_TRACK], [[0, 1]])
    conv._texture(sp, tex, (0.0, P.FPS / float(period)), {}, life)
    return e


def puff(conv, tex, place, delay, life, size, count, spread, speed, additive, alpha):
    """A burst of sprites at `place` in the effect's frame `delay` frames after it starts (alpha: keys over their life)."""
    e = copy.deepcopy(conv.sprite)
    alo.unpin(e)
    sp, pa = e['spawner'], e['particle']
    sp['modifiers'] = []
    P._set(sp, '>B', 251, 0)
    P._set(sp, '>I', 136, P.SFLAG_SPRITE)
    P._set(sp, '>I', 236, P.BLEND_ADD if additive else P.BLEND_ALPHA)
    P._set(pa, '>I', alo.START_FLAGS, P.PFLAG_DIRECTED)
    P._set(pa, '>B', alo.SHAPE, 0)
    pa.pop('shape', None)
    e['name'] = None
    P._set(sp, '>HH', alo.LIFE, P._u16(life), P._u16(life // 3))
    P._set(sp, '>ffff', alo.SIZE, size, size, size * 0.3, size * 0.3)
    P._set(sp, '>12f', 164, 0.0, 0.0, 0.0, 0.0, 0.0, 3.14159, 0.0, 0.0, 0.0, 0.0, 0.0, 0.02)
    P._set(sp, '>6f', 212, *([0.0] * 6))
    P._set(sp, '>fff', 12, 0.0, 0.0, 0.0)
    P._set(sp, '>f', 36, 0.0)
    P._set(sp, '>fff', 120, speed, speed, speed)
    alo.set_emitter_colour(e, [1.0, 1.0, 1.0])
    for o, keys in ((alo.COLOUR_TRACK, [[0, 1.0, 1.0, 1.0]]), (alo.ALPHA_TRACK, alpha), (alo.SIZE_TRACK, [[0, 1.0]]),
                    (84, [[0, 0.0]]), (96, [[0, 0.0]]), (108, [[0, 0.0]])):
        alo._set_keys(sp['tracks'][o], keys)
    for o in (4, 16, 28, 40):
        alo._set_keys(pa['tracks'][o], [[0, 0.0]])
    alo._set_keys(pa['tracks'][64], [[0] + [float(x) for x in place]])
    P._set(pa, '>fff', 76, spread, spread, spread)
    P._set(e, '>HHHHHH', alo.INTERVAL, 0xFFFF, 0, 1, 0, P._u16(delay), 0)
    alo._set_keys(pa['tracks'][alo.COUNT_TRACK], [[0, count]])
    conv._texture(sp, tex, (0.0, 0.0), {}, life)
    return e


def wisp_look(store, materials, kind):
    """Tekken 8's trails leave fire in the air (Niagara's haze, by its frames): RGBA of a cloud of a fire's colour with the
    kind's flames for its grain."""
    body = next(p for p in kind['materials'] if float(materials.effective(p)['scalars'].get('Alpha') or 0.0) > 0.0)
    eff = materials.effective(body)
    n = 128
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.minimum(np.hypot(u - 0.5, v - 0.5) * 2.0, 1.0)
    img = _image(store, eff['textures'].get('BaseTexture2'), {})
    grain = _sample(img, u, v)[..., 0] if img is not None else np.ones_like(u)
    alpha = np.clip((1.0 - r) ** 1.5 * (0.2 + 1.6 * grain), 0.0, 1.0)
    rgb = np.broadcast_to(np.array(WISP_COLOUR, np.float32), u.shape + (3,))
    return np.round(np.dstack([rgb, alpha]) * 255.0)


def fleck_look(store, materials, kind):
    """Tekken 8's karambit leaves crinkled flecks in the air (Niagara's, by its frames): RGBA of pale threads, the kind's
    body texture for their shape."""
    eff = materials.effective(next(p for p in kind['materials'] if float(materials.effective(p)['scalars'].get('Alpha') or 0.0) > 0.0))
    n = 128
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.minimum(np.hypot(u - 0.5, v - 0.5) * 2.0, 1.0)
    img = _image(store, eff['textures'].get('BaseTexture'), {})
    grain = _sample(img, u * 1.5, v * 1.5)[..., 0] if img is not None else np.ones_like(u)
    alpha = np.clip((grain - 0.3) * 3.0, 0.0, 1.0) * (1.0 - r) ** 0.7
    rgb = np.broadcast_to(np.array(FLECK_COLOUR, np.float32), u.shape + (3,))
    return np.round(np.dstack([rgb, alpha]) * 255.0)


def spark_look():
    """A hot speck."""
    n = 32
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.minimum(np.hypot(u - 0.5, v - 0.5) * 2.0, 1.0)
    return np.round(np.dstack([np.full_like(u, 1.0), np.full_like(u, 0.8), np.full_like(u, 0.45), (1.0 - r) ** 2]) * 255.0)


def burning(conv, kind):
    """A kind drawn in a fire's colours."""
    for path in kind['materials']:
        eff = conv.materials.m.effective(path)
        c = eff['vectors'].get('BaseTexColor') or {}
        if float(eff['scalars'].get('Alpha') or 0.0) > 0.0 and float(c.get('r') or 0.0) > 2.0 * float(c.get('b') or 0.0):
            return True
    return False


def left_behind(conv, doc, trail, looks):
    """What a trail leaves along the far end's way, every WISP_FRAMES frames it flies: a fire (burning) clouds and sparks,
    a kind with 'flecks' (the definition's TEKKEN8_TRAIL_LOOKS) flecks of its shine; one with 'clean' (the same) nothing."""
    fire_, flecks = burning(conv, trail['kind']) and not trail['kind'].get('clean'), trail['kind'].get('flecks')
    if not fire_ and not flecks:
        return
    key = ('wisp' if fire_ else 'fleck', trail['kind_id'])
    if key not in looks:
        rgba = (wisp_look if fire_ else fleck_look)(conv.store, conv.materials.m, trail['kind'])
        looks[key] = conv.textures.bake(('trail',) + key, rgba, largest=128)
        looks['spark'] = conv.textures.bake(('trail', 'spark'), spark_look(), largest=32)
    seen, far = trail['seen'], trail['far']
    for f in range(WISP_FRAMES, len(far), WISP_FRAMES):
        if np.linalg.norm(far[f] - far[f - 1]) < WISP_SPEED:
            continue
        place = seen[f]
        if fire_:
            bits = (puff(conv, looks[key], place, f, WISP_LIFE, WISP_SIZE, 2, WISP_SPREAD, 2.0, False,
                         [[0, 0.0], [4, WISP_ALPHA], [WISP_LIFE, 0.0]]),
                    puff(conv, looks['spark'], place, f, 16, 26.0, 10, 250.0, 12.0, True, [[0, 1.0], [10, 1.0], [16, 0.0]]))
        else:
            bits = (puff(conv, looks[key], place, f, FLECK_LIFE, FLECK_SIZE, 2, FLECK_SPREAD, 1.0, True,
                         [[0, 0.0], [3, 1.0], [FLECK_LIFE, 0.0]]),)
        for e, look in zip(bits, (looks[key], looks['spark'])):
            conv._append(doc, e, look[0], None)
            conv.stats['emitters'] += 1


def effects(conv, trails):
    """Trails {id: trail} (Sampler) as effects -> {id: ALO bytes}. conv: effects8.Converter. One look a kind and FrameScale
    curve, its period the longest its trails ask for."""
    key = lambda t: (t['kind_id'], tuple(t['scale']))
    tails, blades = {}, {}
    for t in trails.values():
        tails[key(t)] = max(tails.get(key(t), 1.0), (len(t['far']) + t['tail'] + 2) / float(t['tail']))
        blades[key(t)] = max(blades.get(key(t), 0.0), t['blade'])
    looks, out = {}, {}
    for i, t in sorted(trails.items()):
        k = key(t)
        if k not in looks:
            small = 2 if blades[k] < SMALL_BLADE else 1
            rgba = bake(conv.store, conv.materials.m, t['kind'], t['scale'], tails[k], ALONG // small, ACROSS // small)
            looks[k] = conv.textures.bake(('trail',) + k, rgba, largest=max(ACROSS, ALONG))
        tex = looks[k]
        times, far, near = sweep(t['far'], t['near'])
        name = 'mfm_t7_%03d.nud' % len(conv.models)
        period = tails[k] * t['tail']
        model(conv, name, times, far, near, period, t['width'], tex[1])
        doc = conv._doc()
        conv._append(doc, emitter(conv, name, tex, len(t['far']) + t['tail'] + 1, period), tex[0], name)
        conv.stats['emitters'] += 1
        left_behind(conv, doc, t, looks)
        out[i] = alo.write(doc)
    return out
