"""Tekken 8's missiles (a definition's TEKKEN8_DISKS looks (MISSILE, recipe, joint)) as TTT2 projectiles carrying their look.

A Tekken 8 move may shoot without a projectile row: a MISSILE_CLIP_PROP row (prefabs8.py, HIT POINTS) names a clip that flies
a holding joint straight ahead in the scene's space, metres out, and the move's hit boxes on that joint hit from its path
(prefabs8.scene_spots: the move's own hit, so its cancels on contact, its counter hits and its guard stay Tekken 8's). What
shows the missile is an effect the move spawns on that joint (EFFECT8_SPAWN, part 121), and TTT2 has no body part there. So
the spawn of such an effect becomes TTT2 projectiles that hit no one (neither team field set), spawned from the hips (limb 0)
with the offsets of the path's place, and the look riding each (particles.py PROJECTILE_MARK: roster.cpp keeps it where the
projectile is and out of sight once it is gone):
* while the path stands where the effect starts (a ball charging ahead of the hand), a projectile that stays there (creeping
  ahead HOLD_CREEP a frame: roster.cpp keeps a look at its body part until its projectile moves), with the recipe's 'hold'
  look, until the flight starts;
* from the frame the path runs at its speed, one flying straight ahead at that speed until the list stops the effect (or the
  path stops), with the recipe's 'flight' look.
The hits of these paths come at the frames Tekken 8 has them (LAG 0, read from the game: Dia's hit line 4.04 m out at
its 26th frame, the path's 25th point), and a TTT2 projectile shows the frame after the row that spawns it (SPAWN_DELAY),
at its place: so each row comes a frame early, placed where the path is when it shows.

The looks are sprites, in colours picked from Tekken 8's frames: a ball that rides the projectile (pictures drawn here,
drawn over the stage, so that it shows on a bright stage too, under a glow and a star with the pictures of the effect's own
Niagara emitters (by their names, MISSILE_SOURCES) added over them), a tail left in the air behind it, and a flash where it
is fired; none drawn in the look's first frame (still at the hips then). Written for this project from the files
themselves (no third-party code).
"""
import numpy as np

from . import particles as P, prefabs8, trails8
from ..tekken8 import material as material8, texture as texture8
from ..ttt2 import alo

MISSILE = 'missile'                 # (MISSILE, recipe, the holding joint the hit boxes ride)
FLY_SHARE = 0.8                     # the flight starts at the path's first step this share of its fastest
HOLD_FRAMES = 3                     # a hold shorter than this is no part of its own
LAG = 0                             # frames the path's hits come after Tekken 8's (none: read from the game)
SPAWN_DELAY = 1                     # a projectile shows this many frames after its spawn row
PART_HIPS = 0                       # limb 0: the hips
TEXTURE_SIDE = 128
# the emitters (name, renderer) of a recipe's system whose BaseTexture its sprites use
MISSILE_SOURCES = {'star': ('Flare', 0), 'glow': ('Flare', 1)}
BLUE, PALE, WARM, ICE = (0.28, 0.5, 1.0), (0.78, 0.9, 1.0), (1.0, 0.42, 0.12), (0.6, 0.82, 1.0)
TAIL = 6                            # frames a glow left behind a flying ball lasts (its tail)
HOLD_CREEP = 1.0                    # mm a frame a holding ball's projectile goes ahead: moving, its look leaves the hips
SHOWN = 1                           # a look's sprites start this many frames in (its first frame is at the hips)
# the ball's pictures (mm across; by Tekken 8's frames: Impulse's ball a white swirl about a head wide in a blue glow, Dia's
# a smaller comet: DIA times as large)
ORB, RING, HALO, GLOW, STAR, TAIL_SIZE, FLASH = 230.0, 330.0, 520.0, 640.0, 480.0, 300.0, 800.0
BIG, DIA = 1.0, 0.7
TAIL_BACK = 200.0                   # (mm: the tail's glows start up to twice this behind the ball, a streak, not beads)
# glows riding the ball behind it, its tail's streak whatever its speed (the glows left in the air are a frame's flight
# apart: Dia's 380 mm, beads round 210 mm glows): (mm behind it, its size's share, alpha)
STREAK = ((120.0, 0.9, 0.8), (240.0, 0.75, 0.6), (360.0, 0.6, 0.45), (480.0, 0.45, 0.3))
HOLD_GROW = 6                       # frames a holding ball takes to grow to its size
END_LIFE = 12                       # frames the burst of a ball at its path's end shows
ORB_BLUE = (0.2, 0.45, 1.0)
ORB_CORE, ORB_RIM = 0.3, 0.7        # (the orb picture: white to this radius, its rim's colour from this)
RING_AT, RING_WIDE = 0.72, 0.07


def is_missile(look):
    return isinstance(look, tuple) and len(look) > 2 and look[0] == MISSILE


_ENTRIES = {}


def _entry(k, move):
    if id(k) not in _ENTRIES:
        _ENTRIES.clear()
        _ENTRIES[id(k)] = prefabs8._entries(k)
    return prefabs8._entry_of(_ENTRIES[id(k)].get(move))


def plan(sampler, k, move, f, look, stops):
    """The projectiles showing a missile. sampler: disks8.Sampler (its trails' clips; the animation converter's hold clips);
    k: the Tekken 8 moveset; f: the spawn row's frame; look: (MISSILE, recipe, joint); stops: the frames of the rows that
    stop the effect. -> [{'phase': 'hold', 'flight' or 'end', 'frame': the spawn row's move frame, 'life' (frames shown), 'place':
    (forward, up, side) mm from the hips in his facing, 'speed': (forward, up) mm a frame}] (none: no such path)."""
    rows = [r for r in prefabs8._extras(k, move) if r['id'] == prefabs8.MISSILE_CLIP_PROP]
    trails = sampler.trails
    scene, values = getattr(trails.conv, 'scene', None), trails.clip(move)
    if not rows or scene is None or values is None:
        return []
    entry = _entry(k, move)
    fired = prefabs8._fired(prefabs8._plain(rows[0]['frame'], entry), entry)
    plain = lambda g: entry if prefabs8._plain(g, entry) == prefabs8.AT_START else prefabs8._plain(g, entry)
    at = np.asarray(scene(int(rows[0]['value']), look[2])[0], np.float64)
    shift = fired + LAG                         # path index g shows at move frame g + shift
    placed = np.any(np.abs(at) > 1e-3, axis=1)  # (before the clip places the joint: the scene's origin)
    both = placed[:-1] & placed[1:]
    step = np.linalg.norm(at[1:] - at[:-1], axis=1)
    if not both.any() or step[both].max() <= 0.0:
        return []
    start = plain(f)
    g0 = int(np.clip(start - shift, 0, len(at) - 1))

    def place(g, m):
        R0, p0 = trails8.level_frame(values, trails.skeleton, int(np.clip(m - 1, 0, len(values) - 1)))
        x, y, z = (at[g] - p0) @ R0
        return (float(z), float(y), 0.0), R0
    fast = [g for g in range(g0, len(step)) if both[g] and step[g] >= FLY_SHARE * step[both].max()]
    if not fast:                                # (spawned where the path has run to: a burst there, a still ball's)
        if not placed[g0]:
            return []
        return [dict(phase='end', frame=max(1, start - SPAWN_DELAY), life=END_LIFE, place=place(g0, start)[0],
                     speed=(HOLD_CREEP, 0.0))]
    gf = fast[0]
    ge = gf
    while ge + 1 < len(at) and ge < len(step) and both[ge] and step[ge] >= FLY_SHARE * step[both].max():
        ge += 1
    end = min([plain(s) + LAG for s in stops if plain(s) > start] + [ge + shift + 1])
    out = []
    flight = max(start, gf + shift)
    if placed[g0] and flight - start >= HOLD_FRAMES:
        out.append(dict(phase='hold', frame=max(1, start - SPAWN_DELAY), life=flight - start, place=place(g0, start)[0],
                        speed=(HOLD_CREEP, 0.0)))
    gf += flight - (gf + shift)
    if end - flight < 1 or gf >= ge:
        return out
    where, R0 = place(gf, flight)
    v = (at[ge] - at[gf]) @ R0 / float(ge - gf)
    out.append(dict(phase='flight', frame=max(1, flight - SPAWN_DELAY), life=end - flight, place=where,
                    speed=(float(v[2]), float(v[1]))))
    return out


# ------------------------------------------------------------------------------------------------ the looks
def _texture_path(conv, system, name, renderer):
    """The BaseTexture of the material of an emitter's renderer (by the emitter's name), or None."""
    for e in system.emitters:
        if e.name != name:
            continue
        mats = [r.material or (r.meshes[0][1] if r.meshes else None) for r in e.renderers]
        mats = [m for m in mats if m]
        if renderer < len(mats):
            return conv.materials.m.effective(mats[renderer])['textures'].get('BaseTexture')
    return None


def _tinted(conv, system, role, tint, white):
    """An additive sprite picture: the role's Tekken 8 picture in a colour, its brightest part white. Its brightness is
    taken to its own brightest (Tekken 8 draws these pictures many times over at an exposure TTT2 has not: as they are,
    a flare's mean is 3% grey and its glow's peak 40%, and the ball they make showed nowhere)."""
    path = _texture_path(conv, system, *MISSILE_SOURCES[role])
    key = ('missile', path, tint, white)
    if path is None:
        img = trails8.spark_look() / 255.0
        lum = img[..., 3]
    else:
        img = texture8.Texture2D(conv.store, material8.package_of(path)).decode(TEXTURE_SIDE).astype(np.float32) / 255.0
        lum = img[..., :3].max(-1)
    lum = np.clip(lum / max(float(lum.max()), 1e-3), 0.0, 1.0)
    w = lum ** 2 * white
    rgb = np.asarray(tint, np.float32) * (1.0 - w[..., None]) + w[..., None]
    rgba = np.dstack([rgb, np.clip(lum * 1.4, 0.0, 1.0)]) * 255.0
    return conv.textures.bake(key, np.round(rgba), largest=TEXTURE_SIDE)


def drawn(kind, tint, n=TEXTURE_SIDE):
    """RGBA 0..255 (n, n) of a picture made here (no texture of theirs), drawn over the stage (alpha-blended: it shows on
    a bright stage, where light added to it does not): 'orb' a white core in a rim of the tint, 'halo' a soft disc of
    the tint, 'ring' a thin white ring in three swirling arms with the tint round it (Tekken 8's Impulse ball)."""
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.minimum(np.hypot(u - 0.5, v - 0.5) * 2.0, 1.0)
    tint = np.asarray(tint, np.float32)
    if kind == 'orb':
        t = np.clip((r - ORB_CORE) / (ORB_RIM - ORB_CORE), 0.0, 1.0)[..., None]
        rgb = (1.0 - t) + t * tint
        a = np.clip((1.0 - r) / (1.0 - ORB_RIM), 0.0, 1.0) ** 1.5
    elif kind == 'halo':
        rgb = np.broadcast_to(tint, r.shape + (3,))
        a = (1.0 - r) ** 2
    elif kind == 'ring':
        turn = np.arctan2(v - 0.5, u - 0.5)
        arms = 0.55 + 0.45 * np.cos(3.0 * turn + 6.0 * r)
        line = np.exp(-((r - RING_AT) / RING_WIDE) ** 2) * arms
        rgb = tint + (1.0 - tint) * np.clip(line * 1.5, 0.0, 1.0)[..., None]
        a = np.clip(line + 0.35 * np.exp(-((r - RING_AT) / (3.0 * RING_WIDE)) ** 2), 0.0, 1.0) * (r < 1.0)
    else:
        raise KeyError(kind)
    return np.round(np.dstack([rgb, a]) * 255.0)


def _drawn(conv, kind, tint):
    return conv.textures.bake(('missile drawn', kind, tuple(tint)), drawn(kind, tint), largest=TEXTURE_SIDE)


def _sprite(conv, tex, life, size, count=1, place=(0.0, 0.0, 0.0), spread=(0.0, 0.0, 0.0), speed=0.0, delay=SHOWN,
            every=None, frames=None, local=False, alpha=None, sizes=None, additive=True):
    """Sprites (additive, or drawn over the stage): a burst (every None) or `count` every `every` frames for `frames`
    frames, from `delay` frames on (SHOWN: the look's first frame is at the hips, its projectile not yet moved: roster.cpp
    projectile_look_place); local ones ride the effect (the projectile), the others stay in the air where they were
    made."""
    e = trails8.puff(conv, tex, np.asarray(place, np.float64), delay, life, size, count, 0.0, speed, additive,
                     alpha or [[0, 1.0], [life, 1.0]])
    sp, pa = e['spawner'], e['particle']
    P._set(sp, '>I', 136, P.SFLAG_SPRITE | (P.SFLAG_LOCAL if local else 0))
    P._set(sp, '>HH', alo.LIFE, P._u16(life), 0)
    P._set(sp, '>ffff', alo.SIZE, size, size, size * (0.0 if local else 0.25), size * (0.0 if local else 0.25))
    P._set(pa, '>fff', 76, *[float(x) for x in spread])
    if sizes:
        alo._set_keys(sp['tracks'][alo.SIZE_TRACK], sizes)
    if every:
        P._set(e, '>HHHHHH', alo.INTERVAL, every, 0, P._u16(frames or life), 0, P._u16(delay), 0)
    return e, tex


def _ball(conv, system, life, k, grow=0, out=False):
    """The ball itself, riding its projectile: a blue halo and a white core in a blue rim drawn over the stage, a swirling
    ring round it, a blue glow and a white star added over them (Tekken 8's: a white swirl in a blue glow about a head
    wide). grow: frames it takes to grow to its size (a charging ball); out: fading out and swelling over its life (a
    ball going out at its path's end)."""
    star, glow = _tinted(conv, system, 'star', PALE, 0.9), _tinted(conv, system, 'glow', BLUE, 0.3)
    shown = life + 2
    sizes = [[0, 0.3], [grow, 1.0], [shown, 1.0]] if grow else [[0, 1.0], [life, 1.6]] if out else None
    if grow:
        fade = lambda peak: [[0, 0.0], [max(grow // 2, 1), peak], [shown, peak]]
    elif out:
        fade = lambda peak: [[0, peak], [life // 3, peak], [life, 0.0]]
    else:
        fade = lambda peak: [[0, peak], [shown, peak]]
    return [_sprite(conv, _drawn(conv, 'halo', ORB_BLUE), shown, HALO * k, local=True, alpha=fade(0.6), sizes=sizes,
                    additive=False),
            _sprite(conv, glow, shown, GLOW * k, local=True, alpha=fade(0.9), sizes=sizes),
            _sprite(conv, _drawn(conv, 'ring', ORB_BLUE), shown, RING * k, local=True, alpha=fade(0.9), sizes=sizes,
                    additive=False),
            _sprite(conv, _drawn(conv, 'orb', ORB_BLUE), shown, ORB * k, local=True, alpha=fade(1.0), sizes=sizes,
                    additive=False),
            _sprite(conv, star, shown, STAR * k, local=True, alpha=fade(1.0), sizes=sizes)]


def _flight(conv, system, life, big):
    """A ball of light flying (Tekken 8's Dia: a small blue-white comet, a white burst at the palm as it leaves): the ball,
    a streak of blue glows riding behind it, a tail of blue glows left in the air and warm sparks, a flash where it
    starts. `big`: Impulse's (Dia's
    DIA times as large)."""
    warm, flash = _tinted(conv, system, 'glow', WARM, 0.5), _tinted(conv, system, 'star', PALE, 1.0)
    glow = _tinted(conv, system, 'glow', BLUE, 0.3)
    k = BIG if big else DIA
    streak = [_sprite(conv, glow, life + 2, TAIL_SIZE * share * k, place=(0.0, 0.0, -back * k), local=True,
                      alpha=[[0, alpha], [life + 2, alpha]]) for back, share, alpha in STREAK]
    return _ball(conv, system, life, k) + streak + [
        _sprite(conv, _drawn(conv, 'halo', ORB_BLUE), TAIL, TAIL_SIZE * k, count=3, place=(0.0, 0.0, -TAIL_BACK),
                spread=(15.0, 15.0, TAIL_BACK), every=1, frames=life, alpha=[[0, 0.55], [TAIL, 0.0]],
                sizes=[[0, 1.0], [TAIL, 0.35]], additive=False),
        _sprite(conv, glow, TAIL, TAIL_SIZE * k, count=2, place=(0.0, 0.0, -TAIL_BACK),
                spread=(15.0, 15.0, TAIL_BACK), every=1, frames=life, alpha=[[0, 0.7], [TAIL, 0.0]],
                sizes=[[0, 1.0], [TAIL, 0.3]]),
        _sprite(conv, warm, 4, 160.0 * k, count=2, place=(0.0, 0.0, -100.0), spread=(15.0, 15.0, 100.0), every=1,
                frames=life, alpha=[[0, 0.9], [4, 0.0]]),
        _sprite(conv, _drawn(conv, 'orb', PALE), 4, FLASH * 0.6 * k, alpha=[[0, 0.9], [4, 0.0]], additive=False),
        _sprite(conv, flash, 5, FLASH * k, alpha=[[0, 1.0], [5, 0.0]])]


def _hold(conv, system, life):
    """A ball of light charging where it stands (Tekken 8's Impulse, ahead of his reaching hand): the ball growing,
    ice-blue sparks thrown off it."""
    spark = _tinted(conv, system, 'star', ICE, 0.8)
    return _ball(conv, system, life, BIG, grow=HOLD_GROW) + [
        _sprite(conv, spark, 10, 90.0, count=5, spread=(220.0, 220.0, 220.0), speed=14.0, every=2, frames=life,
                alpha=[[0, 1.0], [10, 0.0]])]


def _end(conv, system, life, big):
    """A ball going out where its path ends (Tekken 8's Impulse: the white swirl in its blue glow, fading, white and
    ice-blue sparks thrown off it)."""
    k = BIG if big else DIA
    spark = _tinted(conv, system, 'star', ICE, 0.8)
    return _ball(conv, system, life, k, out=True) + [
        _sprite(conv, _drawn(conv, 'ring', PALE), life, RING * k, alpha=[[0, 0.9], [life, 0.0]],
                sizes=[[0, 1.0], [life, 2.5]], additive=False),
        _sprite(conv, spark, 10, 90.0, count=12, spread=(200.0, 200.0, 200.0), speed=18.0, alpha=[[0, 1.0], [10, 0.0]])]


RECIPES = {('dia', 'flight'): lambda conv, s, life: _flight(conv, s, life, False),
           ('impulse', 'flight'): lambda conv, s, life: _flight(conv, s, life, True),
           ('impulse', 'hold'): _hold, ('dia', 'hold'): _hold,
           ('impulse', 'end'): lambda conv, s, life: _end(conv, s, life, True),
           ('dia', 'end'): lambda conv, s, life: _end(conv, s, life, False)}


def files(conv, d, system_of):
    """A missile look's doc (moveset.Converter.missile_rows: 'burst' (MISSILE, life, recipe, phase), 'id' its Tekken 8 effect)
    -> ALO bytes: the recipe's sprites, riding the projectile."""
    _, life, recipe, phase = d['burst']
    doc = conv._doc(projectile=True)
    for e, tex in RECIPES[recipe, phase](conv, system_of(d['id']), int(life)):
        conv._append(doc, e, tex[0], None)
        conv.stats['emitters'] += 1
    return alo.write(doc)
