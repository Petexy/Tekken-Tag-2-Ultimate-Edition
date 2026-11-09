"""Bursts of a definition's TEKKEN8_DISKS (disks8.py) placed from the body part Tekken 8 spawns them at.

Tekken 8 spawns an effect at a body part (0x8039: part << 8 | id; its parts 0 .. 21 are TTT2's, 120 / 121 the hands'
holding joints) or on a weapon (0x839d: slot << 16 | id), and its effect table says whether the effect then follows that
part. TTT2 moves an effect with its body part every frame (roster.cpp, level effects: the part's place, the fighter's
level turn), and a sprite takes the effect's place of the frame it starts in, then stays in the air. So a burst whose
sprites start over several frames (flames along a blade as it swings, along his body as he dashes) is put on the part
Tekken 8 names and each sprite is placed from where that part is in the move's clip at the frame the sprite starts
(Placer): the fire on his sword stays on the sword, the fist's jet leaves the fist, the flames of his Phoenix Shift go
with him. The recipes' looks are disks8's; disks8.Sampler.anchored gives the clip's points.

Written for this project from the files themselves (no third-party code).
"""
import math

import numpy as np

from . import disks8, particles as P, trails8

HIPS, CHEST = 0, 2                   # TTT2's body parts: the hips (the model's root), the chest
FOREARMS = {8: 9, 12: 13}            # a forearm's part -> its hand's
FEET = (16, 19)
BODY = (3, 2, 5, 9, 13, 8, 12, 15, 18, 16, 19)     # the parts a burning body burns at (disks8's JOINTS)
STAFF = 120                          # Tekken 8's part of his left hand's holding joint (the staff in it)


class Placer:
    """A clip's points -> places from the burst's body part at a frame from its spawn (the effect's level frame then)."""

    def __init__(self, clip):
        self.at, self.levels, self.parts, self.tools = clip['at'], clip['levels'], clip['parts'], clip['tools']
        self.n = len(self.levels)

    def frame(self, f):
        return min(max(int(f), 0), self.n - 1)

    def __call__(self, x, f):
        f = self.frame(f)
        return (np.asarray(x, np.float64) - self.at[f]) @ self.levels[f]

    def part(self, p, f):
        return self.parts[self.frame(f), p]

    def level(self, offset, f=0):
        """An offset in the level frame of frame f (x left, y up, z ahead) -> the clip's frame."""
        return self.levels[self.frame(f)] @ np.asarray(offset, np.float64)

    def tool(self, name, f, q):
        """A point a share q of the way from a weapon's near end to its far end (the definition's 'tools')."""
        near, far = self.tools[name]
        f = self.frame(f)
        return near[f] + (far[f] - near[f]) * q

    def floor(self):
        """The floor's height under him in the clip (its feet's lowest)."""
        return float(min(self.parts[:, p, 1].min() for p in FEET))


def same_anywhere(look, clip):
    """Whether a burst looks the same at its part in any move (one effect for all of them)."""
    recipe, part, (kind, n) = look[0], clip['part'], clip['anchor']
    if recipe in ('appear', 'bolts_right', 'thunder', 'glow', 'glow_right', 'wing', 'wing_right'):
        return True
    if recipe == 'feet':
        return part in FEET
    if recipe == 'hand':
        return part not in FOREARMS
    if recipe == 'bolts':
        return not (kind == 'part' and n == STAFF and 'staff' in clip['tools'])
    if recipe in ('gust', 'feathers', 'niagara', 'updraft', 'updraft_floor', 'heat'):
        return True
    return False


def files(conv, d, system_of):
    """A burst with a clip (disks8.Sampler.anchored) -> ALO bytes, or None when its recipe is not placed so."""
    recipe, frames = d['burst'][:2]
    name = d['burst'][2] if len(d['burst']) > 2 else 'blaze'
    if recipe == 'niagara':                                 # (its own Niagara system, as the generic ids': an id the
        made = conv.system8(system_of(d['id']), cap_frames=frames, once=True, source=d['id'])    # generic route cannot take)
        return made.get('')
    if recipe not in RECIPES:
        return None
    fires = conv.__dict__['disk_fires'] = disks8.fire_textures(conv, system_of, d['source'])
    out = Bits(conv, disks8._flames(conv, fires, name))
    RECIPES[recipe](out, conv, d, Placer(d['clip']), frames, system_of, fires)
    doc = conv._doc()
    for e, tex, model in out.bits[:P.MAX_EMITTERS]:
        conv._append(doc, e, tex[0], model)
        conv.stats['emitters'] += 1
    return disks8.alo.write(doc)


class Bits:
    """The emitters of a burst being made: flames, sparks, any sprite."""

    def __init__(self, conv, flames):
        self.conv, self.flames, self.bits = conv, flames, []
        self.spark = conv.textures.bake(('trail', 'spark'), trails8.spark_look(), largest=32)
        self.smoke = conv.textures.bake(('burst', 'smoke'), disks8.smoke_look(), largest=64)

    @staticmethod
    def upright(e, lean=0.0):
        """A sprite keeps its picture's way up (lean: by up to this many radians either way)."""
        P._set(e['spawner'], '>12f', 164, 0.0, 0.0, -lean, 0.0, 0.0, 2.0 * lean, *([0.0] * 6))
        return e

    def flame(self, place, delay, life, size, count, spread, speed=2.0, k=0, flames=None):
        tex = (flames or self.flames)[k % 4]
        e = trails8.puff(self.conv, tex, place, delay, life, size, count, spread, speed, False, disks8.FLAME_KEYS(life))
        self.bits.append((self.upright(e, 0.35), tex, None))

    def sparks(self, place, delay, life, size, count, spread, speed, colour=None):
        e = trails8.puff(self.conv, self.spark, place, delay, life, size, count, spread, speed, True, [[0, 1.0], [life // 2, 1.0], [life, 0.0]])
        if colour is not None:
            disks8.alo._set_keys(e['spawner']['tracks'][disks8.alo.COLOUR_TRACK], [[0] + list(colour)])
        self.bits.append((e, self.spark, None))

    def sprite(self, tex, place, delay, life, size, count, spread, speed, additive, alpha, lean=None, local=False, colour=None, grow=None):
        e = trails8.puff(self.conv, tex, place, delay, life, size, count, spread, speed, additive, alpha)
        if local:                                           # (they go with the part, as on his back)
            P._set(e['spawner'], '>I', 136, P.SFLAG_SPRITE | P.SFLAG_LOCAL)
        if colour is not None:
            disks8.alo._set_keys(e['spawner']['tracks'][disks8.alo.COLOUR_TRACK], [[0] + list(colour)])
        if grow is not None:                                # (its size at the end of its life, a share of its start's)
            disks8.alo._set_keys(e['spawner']['tracks'][disks8.alo.SIZE_TRACK], [[0, 1.0], [life, float(grow)]])
        self.bits.append((self.upright(e, lean) if lean is not None else e, tex, None))

    def bar(self, tex, place, delay, life, wide, high, additive, alpha, colour=None):
        """One sprite `wide` x `high` mm, its picture's way up, left where it starts."""
        e = trails8.puff(self.conv, tex, place, delay, life, wide, 1, 0.0, 0.0, additive, alpha)
        P._set(e['spawner'], '>ffff', disks8.alo.SIZE, wide, high, 0.0, 0.0)
        if colour is not None:
            disks8.alo._set_keys(e['spawner']['tracks'][disks8.alo.COLOUR_TRACK], [[0] + list(colour)])
        self.bits.append((self.upright(e), tex, None))

    def turned(self, angle):
        """The last sprite turned `angle` radians in the picture (each of its particles alike)."""
        P._set(self.bits[-1][0]['spawner'], '>12f', 164, 0.0, 0.0, float(angle), *([0.0] * 9))

    def grown(self, life, factor):
        """The last sprite `factor` times its size by the end of its life."""
        track = self.bits[-1][0]['spawner']['tracks'][disks8.alo.SIZE_TRACK]
        disks8.alo._set_keys(track, [[0, 1.0], [life, float(factor)]])


# ------------------------------------------------------------------------------------------------ the recipes
def _blade(out, conv, d, at, frames, system_of, fires):
    """Fire along the blade: new flames every frame where the blade is then, each gone in a few frames (a sprite stays where
    it starts: flames that lived longer would hang in the air behind a swing; Tekken 8's burn on the blade)."""
    spots = BLADE_SPOTS if frames * len(BLADE_SPOTS) <= disks8.P.MAX_EMITTERS else BLADE_SPOTS[:1]
    for f in range(frames):
        for k, (q, size) in enumerate(spots):
            out.flame(at(at.tool('sword', f, q), f), f, BLADE_LIFE, size, 2, BLADE_SPREAD, 1.0, f + k)


def _body(out, conv, d, at, frames, system_of, fires):
    """His body goes up in flames, at each part where it is as the flames start."""
    for f in range(0, frames, 3):
        for k, p in enumerate(BODY):
            out.flame(at(at.part(p, f), f), f, 10, 330.0, 1, 70.0, 3.0, f + k)
    out.sparks(at(at.part(HIPS, 0), 0), 0, 26, 28.0, 24, 500.0, 16.0)


def _cloud(out, conv, d, at, frames, system_of, fires):
    """What he leaves as he dashes in his shift (Tekken 8's 26): a dark haze along his way, thin red streaks of fire across it
    (lines left in the air around his body as he passes), a little fire on the floor, embers."""
    floor = at.floor()
    for f in range(0, max(1, frames - 4), 3):
        out.sprite(out.smoke, at(at.part(HIPS, f), f), f, 14, 1300.0, 1, 80.0, 0.0, False, [[0, 0.0], [3, 0.75], [8, 0.6], [14, 0.0]])
    lines = conv.textures.bake(('burst', 'streaks'), streak_look(), largest=256)
    for f in range(0, max(1, frames - 4), STREAK_EVERY):
        place = at.part(HIPS, f) + at.level((0.0, STREAK_UP, 0.0))
        out.bar(lines, at(place, f), f, STREAK_LIFE, STREAK_WIDE, STREAK_HIGH, False,
                [[0, 0.0], [2, STREAK_ALPHA], [STREAK_LIFE - 4, STREAK_ALPHA * 0.8], [STREAK_LIFE, 0.0]])
    for f in range(0, max(1, frames - 4), 4):
        hips = at.part(HIPS, f)
        out.flame(at(np.array((hips[0], floor + 150.0, hips[2])), f), f, 12, 460.0, 1, 300.0, 3.0, f)
    out.sparks(at(at.part(HIPS, 2), 2), 2, 30, 26.0, 24, 700.0, 10.0)


def streak_look():
    """Phoenix Shift's streaks (made here: no texture of theirs): thick glowing lines of red fire across the picture, a
    white-hot core in the brightest, their ends thin and faint (by Tekken 8's frames)."""
    n = 256
    noise = np.random.RandomState(26)
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    heat = np.zeros((n, n), np.float32)
    for _ in range(STREAK_LINES):
        row, thick = noise.uniform(0.1, 0.9), noise.uniform(0.004, 0.011)
        start, length, strength = noise.uniform(-0.1, 0.6), noise.uniform(0.3, 0.8), noise.uniform(0.5, 1.0)
        along = np.clip(np.minimum(u - start, start + length - u) / (0.25 * length), 0.0, 1.0)
        heat = np.maximum(heat, np.exp(-((v - row) / thick) ** 2) * along * strength)
    glow = np.exp(-((v - 0.5) / 0.3) ** 2) * np.clip(np.minimum(u, 1.0 - u) * 4.0, 0.0, 1.0)
    t = np.clip(heat, 0.0, 1.0) * np.clip(np.minimum(u, 1.0 - u) * 8.0, 0.0, 1.0)     # (none cut off at the picture's edge)
    rgb = np.stack([np.interp(t, STREAK[0], c) for c in STREAK[1:]], -1).astype(np.float32) / 255.0
    a = np.clip(t * 1.6, 0.0, 1.0) + glow * 0.05 * (1.0 - np.clip(t * 1.6, 0.0, 1.0))
    rgb = rgb * np.clip(t * 1.6, 0.0, 1.0)[..., None] + np.array((0.55, 0.08, 0.05), np.float32) * (a - np.clip(t * 1.6, 0.0, 1.0))[..., None]
    rgb = rgb / np.maximum(a[..., None], 1e-3)
    return np.round(np.dstack([np.clip(rgb, 0.0, 1.0), a]) * 255.0)


STREAK_LINES = 16                   # (Phoenix Shift's streaks: lines in a picture, how wide and high a picture is (mm), how
STREAK_WIDE, STREAK_HIGH, STREAK_LIFE = 1200.0, 850.0, 10       # long one stays (frames), a new one every so many frames,
STREAK_EVERY, STREAK_ALPHA, STREAK_UP = 4, 0.6, 250.0           # how strong, mm over his hips: by Tekken 8's frames, about
                                                                # his body's size around him, never a sheet over the screen)
STREAK = ((0.0, 0.45, 0.8, 1.0), (150, 235, 255, 255), (20, 60, 150, 225), (15, 35, 90, 180))      # dark red .. orange .. white-hot


def _appear(out, conv, d, at, frames, system_of, fires):
    """He comes back: sparks all over him."""
    out.sparks(np.zeros(3), 0, 24, 26.0, 28, 520.0, 14.0)


def _feet(out, conv, d, at, frames, system_of, fires):
    """Flames at his foot (the part Tekken 8 names; both feet when it names none)."""
    part = d['clip']['part']
    for f in range(0, frames, 2):
        for k, p in enumerate((part,) if part in FEET else FEET):
            out.flame(at(at.part(p, f), f), f, 12, 340.0, 1, 50.0, 3.0, f + k)


def _hand(out, conv, d, at, frames, system_of, fires):
    """Wisps round the hand or along the forearm Tekken 8 names (its forearm's part: from the elbow to the fist)."""
    part = d['clip']['part']
    for f in range(0, frames, 2):
        if part in FOREARMS:
            elbow, wrist = at.part(part, f), at.part(FOREARMS[part], f)
            for k, q in enumerate((0.45, 0.8, 1.1)):
                out.flame(at(elbow + (wrist - elbow) * q, f), f, 10, 200.0, 1, 40.0, 3.0, f + k)
        else:
            out.flame(np.zeros(3), f, 12, 240.0, 1, 50.0, 3.0, f)


def _jet(out, conv, d, at, frames, system_of, fires):
    """A burst forward from the fist Tekken 8 names (left in the air where it starts)."""
    fist, ahead = at.part(d['clip']['part'], 0), at.level((0.0, 0.0, 1.0), 0)
    for k, (far, size) in enumerate(((0.0, 460.0), (160.0, 400.0), (340.0, 340.0), (560.0, 270.0), (800.0, 190.0))):
        out.flame(at(fist + ahead * far, k // 2), k // 2, 10 + frames // 2, size, 1, 25.0, 1.0, k)
    out.sparks(at(fist, 0), 0, 18, 24.0, 16, 300.0, 22.0)


def _strike(out, conv, d, at, frames, system_of, fires):
    """The big blow: a white flash at his back, sparks, pink wisps ahead of the striking hand (left in the air)."""
    part = d['clip']['part'] or disks8.PART_TE_R
    chest, hand = at.part(CHEST, 2), at.part(part, 2)
    pink = disks8._flames(conv, fires, 'pink')
    for k in range(5):
        out.flame(at(chest + at.level((0.0, 200.0 * k - 200.0, -250.0)), k // 2), k // 2, 10, 900.0 - 100.0 * k, 1, 120.0, 2.0, k)
    out.sparks(at(chest, 0), 0, 24, 26.0, 28, 500.0, 18.0)
    for k in range(8):
        tex = pink[k % 4]
        out.sprite(tex, at(hand + at.level((0.0, 150.0 * (k % 4) - 200.0, 300.0 + 40.0 * k)), k), k, 14, 300.0, 1, 170.0, 2.0, False,
                   [[0, 0.0], [2, 0.7], [7, 0.6], [14, 0.0]])


def _floor(out, conv, d, at, frames, system_of, fires):
    """Fire and sparks on the floor where the rows say (or the effect's own offset), left there."""
    spot = _spot(d, at, system_of) + np.array((0.0, 60.0, 0.0))
    for k in range(5):
        out.flame(at(spot, k // 2), k // 2, 14, 400.0, 1, 280.0, 3.0, k)
    out.sparks(at(spot, 0), 0, 22, 26.0, 24, 520.0, 18.0)


def _column(out, conv, d, at, frames, system_of, fires):
    """Burning Rain's fire pillar (Tekken 8's 182: its fire pole grows to some 3 m where the sword strikes the floor, its
    system's own offset ahead of him): a white-hot streak up from the floor first, then a column of golden flames from the
    floor up, its pieces rising in turn, burning a while, thinning and burning out from the top down; embers and sparks;
    left there."""
    spot = _spot(d, at, system_of) - np.array((0.0, 60.0, 0.0))
    gold = disks8._flames(conv, fires, 'blaze')
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    piece = COLUMN_HIGH / COLUMN_PIECES
    out.bar(glow, at(spot + np.array((0.0, COLUMN_HIGH * 0.5, 0.0)), 0), 0, COLUMN_STREAK, COLUMN_WIDE * 0.35,
            COLUMN_HIGH * 1.05, True, [[0, 0.0], [1, 1.0], [COLUMN_STREAK, 0.0]], COLUMN_HOT)
    burn = max(COLUMN_EVERY + 2, frames - COLUMN_EVERY)
    for f in range(1, burn, COLUMN_EVERY):
        q = f / float(burn)
        for k in range(COLUMN_PIECES):
            if q > 1.0 - 0.25 * k:                          # (its top burns out first)
                continue
            life = COLUMN_EVERY + 3
            delay = f + (k if f == 1 else 0)                # (its pieces rise in turn as it comes)
            wide = COLUMN_WIDE * (1.0 - 0.22 * k) * (1.0 - 0.45 * q)
            out.bar(gold[(f // COLUMN_EVERY + k) % 4], at(spot + np.array((0.0, piece * (k + 0.5), 0.0)), delay), delay, life,
                    wide, piece * 1.35, False, [[0, 0.0], [1, 0.95], [life - 2, 0.85], [life, 0.0]])
    for k in range(3):
        out.flame(at(spot + np.array((0.0, 120.0, 0.0)), 2 * k), 2 * k, 14, 520.0, 1, 220.0, 3.0, k)
        out.sparks(at(spot + np.array((0.0, 400.0 + 700.0 * k, 0.0)), 3 * k), 3 * k, 22, 26.0, 18, 300.0, 14.0)


COLUMN_HIGH, COLUMN_PIECES = 3000.0, 3      # (Burning Rain's pillar: mm from the floor, pieces one over another; by Tekken 8's
COLUMN_WIDE, COLUMN_EVERY = 750.0, 3        # frames a column some 0.7 m wide to past the top of the picture), new pieces every
COLUMN_STREAK = 6                           # so many frames; the white-hot streak's frames
COLUMN_HOT = (1.0, 0.92, 0.75)


def _spot(d, at, system_of):
    """Where on the floor a burst goes: where the rows in front of its spawn say, else its system's own offset."""
    place = d['clip']['place']
    if place is not None:
        (_, forward, sideways), _ = place
        spot = at.part(HIPS, 0) + at.level((sideways, 0.0, forward))
    else:
        user = system_of(d['id']).user.get('User.OffsetPos') or (0.0, 0.0, 0.0)
        spot = at.part(HIPS, 0) + at.level(np.array((-user[1], 0.0, user[0])) * 10.0)
    return np.array((spot[0], at.floor() + 60.0, spot[2]))


def _spark(out, conv, d, at, frames, system_of, fires):
    """Sparks off the floor where the blade strikes it: pink sparks and crimson lightning low over the floor, left there."""
    spot = _spot(d, at, system_of)
    for k in range(3):
        f = k * frames // 3
        out.sparks(at(spot, f), f, 16, 30.0, 18, 380.0, 20.0, SPARK_PINK)
    source = d['source']
    path = disks8._named(disks8._textures(conv, system_of(source['bolts'])), source['emitters']['bolt'])['BaseTexture']
    for f in range(0, frames, 2):
        tex = conv.textures.bake(('burst', 'bolts_right', f // 2 % 4), disks8.bolt_look(conv.store, path, f // 2 % 4, disks8.RAMPS['crimson']),
                                 largest=256)
        out.sprite(tex, at(spot + np.array((0.0, 40.0, 0.0)), f), f, 5, 420.0, 1, 220.0, 0.0, False, [[0, 1.0], [3, 0.8], [5, 0.0]])


def _pillar(out, conv, d, at, frames, system_of, fires):
    """Flames going up from the floor round where he stood."""
    hips = at.part(HIPS, 0)
    floor = np.array((hips[0], at.floor(), hips[2]))
    for k in range(24):
        q = k / 23.0
        turn = k * 2.399963
        f = int(q * frames)
        spot = floor + at.level((math.cos(turn) * 260.0 * (1.0 - q), 2800.0 * q, math.sin(turn) * 260.0 * (1.0 - q)))
        out.flame(at(spot, f), f, 16, 620.0 - 300.0 * q, 1, 80.0, 3.0, k)
    out.sparks(at(floor, 2), 2, 26, 24.0, 24, 500.0, 16.0)


def _ground(out, conv, d, at, frames, system_of, fires):
    """Wisps over the floor round where he stood."""
    hips = at.part(HIPS, 0)
    spot = np.array((hips[0], at.floor() + 180.0, hips[2]))
    for f in range(0, frames, 3):
        for k in range(2):
            out.flame(at(spot, f), f, 16, 560.0, 1, 520.0, 3.0, f + k)


def _bolts(out, conv, d, at, frames, system_of, fires):
    """Lightning crawling round the part Tekken 8 names; along the staff when it names the staff's holding joint."""
    recipe = d['burst'][0]
    colours, size = disks8.BOLTS[recipe][1:]
    source = d['source']
    path = disks8._named(disks8._textures(conv, system_of(source['bolts'])), source['emitters']['bolt'])['BaseTexture']
    bolts = [conv.textures.bake(('burst', recipe, k), disks8.bolt_look(conv.store, path, k, disks8.RAMPS[colours]), largest=256)
             for k in range(4)]
    kind, n = d['clip']['anchor']
    staff = kind == 'part' and n == STAFF and 'staff' in d['clip']['tools']
    for f in range(0, frames, 2):
        for k in range(3):
            tex = bolts[(f + k) % 4]
            place = at(at.tool('staff', f, 0.15 + 0.35 * k), f) if staff else np.zeros(3)
            out.sprite(tex, place, f, 6, size * BOLT_SIZE * (1.0 - 0.19 * k), 1, size * (0.05 + 0.08 * k), 0.0, False,
                       [[0, 1.0], [3, 0.9], [6, 0.0]])


def _thunder(out, conv, d, at, frames, system_of, fires):
    """A column of lightning out of the sky down to the part (the staff's hand)."""
    source = d['source']
    path = disks8._named(disks8._textures(conv, system_of(source['bolts'])), source['emitters']['bolt'])['BaseTexture']
    tall = [conv.textures.bake(('burst', 'bolts', k), disks8.bolt_look(conv.store, path, k, disks8.RAMPS['thunder']), largest=256)
            for k in disks8.THUNDER_CELLS]
    size = disks8.THUNDER_HIGH / disks8.THUNDER_PIECES
    for f in range(0, frames, disks8.THUNDER_EVERY):
        for k in range(disks8.THUNDER_PIECES):
            tex = tall[(f // disks8.THUNDER_EVERY + k) % len(tall)]
            every = disks8.THUNDER_EVERY
            out.sprite(tex, np.array((0.0, size * (k + 0.5), 0.0)), f, every + 2, size * 1.15, 1, size * 0.05, 0.0, False,
                       [[0, 1.0], [every, 0.9], [every + 2, 0.0]], lean=0.12)


def _feathers(out, conv, d, at, frames, system_of, fires):
    """White feathers shed round him (at the part Tekken 8 names, his chest when none); a gust: all at once."""
    tex = disks8.feather_texture(conv, system_of, d['source'])
    place = disks8.CHEST if d['clip']['part'] == HIPS else np.zeros(3)
    if d['burst'][0] == 'gust':
        out.sprite(tex, place, 2, 26, disks8.FEATHER_SIZE, 10, 500.0, 2.5, False, disks8.FEATHER_KEYS)
        return
    for f in range(0, frames, 4):
        out.sprite(tex, place, f, 26, disks8.FEATHER_SIZE, 5, 420.0, 2.5, False, disks8.FEATHER_KEYS)


BLADE_SPOTS = ((0.3, 260.0), (0.75, 200.0))         # (along the blade: share of its length, flame size mm)
BLADE_LIFE, BLADE_SPREAD = 4, 140.0  # (frames a blade's flame lives; mm its flames scatter round a spot)
BOLT_SIZE = 0.7                     # (lightning round a part: tight to it, as Tekken 8's round the staff)
def glow_look():
    """A soft white glow, a little blue (made here: no texture of theirs)."""
    n = 64
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.minimum(np.hypot(u - 0.5, v - 0.5) * 2.0, 1.0)
    a = (1.0 - r) ** 2.2
    return np.round(np.dstack([np.full_like(u, 0.92), np.full_like(u, 0.96), np.ones_like(u), a]) * 255.0)


def _glow(out, conv, d, at, frames, system_of, fires):
    """A white glow where a wing meets his back (its part: the chest; left or right by the recipe's name): a flash as the
    wing opens, then a steady glow that goes with him."""
    tex = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    side = -1.0 if d['burst'][0] == 'glow_right' else 1.0
    root = np.array((side * WING_ROOT[0], WING_ROOT[1], WING_ROOT[2]))
    out.sprite(tex, root, 0, 10, 900.0, 1, 0.0, 0.0, True, [[0, 0.0], [2, 1.0], [10, 0.0]], local=True)
    for f in range(0, max(1, frames - 6), 6):
        out.sprite(tex, root, f, 12, 380.0, 1, 20.0, 0.0, True, [[0, 0.0], [3, 0.8], [9, 0.8], [12, 0.0]], local=True)


def _tiled(img, tiles, n):
    """A greyscale picture repeated tiles = (across, down) times over n x n texels."""
    h, w = img.shape
    v, u = np.meshgrid(np.arange(n), np.arange(n), indexing='ij')
    return img[(v * int(round(tiles[1])) * h // n) % h, (u * int(round(tiles[0])) * w // n) % w]


def veins_look(store, textures, tiles):
    """A wing's icy flash: Tekken 8's wing flash's branching lines (its Mask2Texture) frosted with its grain (BaseTexture
    and TouchTexture at the tilings its material gives, tiles {texture: (across, down)}): white along the lines and where
    the grain peaks, a blue frost round them, soft at the picture's edges; the lines branch upward from the middle of its
    foot, as a wing's from its root."""
    img = disks8._image(store, textures['Mask2Texture'], {})[..., 0]
    k = max(1, img.shape[0] // VEINS_SIDE)
    n = img.shape[0] // k
    x = img[:n * k, :n * k].reshape(n, k, n, k).max(axis=(1, 3))       # (thin lines kept)
    grain = np.ones((n, n), np.float32)
    for name in ('BaseTexture', 'TouchTexture'):
        if textures.get(name):
            grain = grain * _tiled(disks8._image(store, textures[name], {})[..., 0], tiles.get(name, (1, 1)), n)
    grain = np.clip(grain / max(float(np.percentile(grain, 99)), 1e-3), 0.0, 1.0)
    lines = np.clip(x * 1.6, 0.0, 1.0)
    frost = np.clip(disks8._spread(x, VEINS_GLOW) * 1.4, 0.0, 1.0)
    a = np.clip(frost * (0.25 + 0.9 * grain) + lines * 0.5, 0.0, 1.0)
    t = np.clip(lines + 0.6 * grain * frost, 0.0, 1.0)[..., None]
    rgb = np.asarray(ICE_WHITE, np.float32) * t + np.asarray(ICE_BLUE, np.float32) * (1.0 - t)
    edge = np.minimum.outer(np.minimum(np.arange(n), np.arange(n)[::-1]), np.minimum(np.arange(n), np.arange(n)[::-1])) / (n * 0.1)
    return np.round(np.dstack([rgb, a * np.clip(edge, 0.0, 1.0)]) * 255.0)


def ring_look():
    """A soft white ring (made here: no texture of theirs)."""
    n = 128
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.hypot(u - 0.5, v - 0.5) * 2.0
    a = np.exp(-((r - 0.8) / 0.1) ** 2) * (r < 1.0)
    return np.round(np.dstack([np.full_like(u, 0.94), np.full_like(u, 0.97), np.ones_like(u), a]) * 255.0)


def _veins(conv, d, system_of):
    source = d['source']
    want = source['emitters']['wing']
    for e in system_of(source['wing']).emitters:          # (the wing flash's emitter and its material in effect)
        for r in (e.renderers if e.enabled and e.name.startswith(want) else ()):
            mat = r.meshes[0][1] if r.kind == 'mesh' and r.meshes else r.material
            if mat:
                eff = conv.materials.m.effective(mat)
                tiles = {name: (v['r'], v['g']) for name, v in
                         (('BaseTexture', eff['vectors'].get('BaseTexTilling')), ('TouchTexture', eff['vectors'].get('TouchTexTilling'))) if v}
                return conv.textures.bake(('burst', 'veins'), veins_look(conv.store, eff['textures'], tiles), largest=VEINS_SIDE)
    raise KeyError(want)


def _wing(out, conv, d, at, frames, system_of, fires):
    """A wing's icy flash as it rises over him (Tekken 8's, on the wing's slot: in TTT2 on the chest, the left wing or the
    right by the recipe's name): white branching lines in a blue glow up the wing from its root, growing as they fade
    (Tekken 8's wing flash: alpha 1 to 0, size 1 to 1.2), then back along it as it sweeps behind him, drawn over the
    stage; a white ring and a glow at the root, pale sparks; all going with him."""
    side = -1.0 if d['burst'][0] == 'wing_right' else 1.0
    root = np.array((side * WING_ROOT[0], WING_ROOT[1], WING_ROOT[2]))
    way = np.array((side * WING_OUT, 1.0, -WING_BACK))
    way = way / np.linalg.norm(way)
    veins = _veins(conv, d, system_of)
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    ring = conv.textures.bake(('burst', 'ring'), ring_look(), largest=128)
    for k, (along, size) in enumerate(WING_SHEETS):
        life = frames - k
        out.sprite(veins, root + way * along, k, life, size, 1, 0.0, 0.0, WING_ADDED,
                   [[0, 0.0], [1, 1.0], [life // 2, 0.45], [life, 0.0]], lean=0.0, local=True, grow=1.2)
    # (then the frost goes with the wing as it sweeps back behind him, Tekken 8's frames 106 to 116: white over its breadth)
    back = np.array((side * WING_OUT, WING_SWEEP[0], -WING_SWEEP[1]))
    back = back / np.linalg.norm(back)
    for k, (along, size) in enumerate(WING_SWEPT):
        start = WING_SWEEP_AT + k
        life = frames - start
        if life > 1:
            out.sprite(veins, root + back * along, start, life, size, 1, 0.0, 0.0, WING_ADDED,
                       [[0, 0.0], [1, 0.9], [life // 2, 0.5], [life, 0.0]], lean=0.0, local=True, grow=1.15)
    out.sprite(ring, root, 0, WING_RING_LIFE, WING_RING, 1, 0.0, 0.0, True, [[0, 0.0], [1, 0.4], [WING_RING_LIFE, 0.0]],
               lean=0.0, local=True, grow=2.0)
    out.sprite(glow, root, 0, 12, 800.0, 1, 0.0, 0.0, True, [[0, 0.0], [1, 0.9], [12, 0.0]], lean=0.0, local=True, colour=ICE_BLUE)
    for k in range(2):
        out.sparks(root + way * (700.0 + 600.0 * k), 2 * k, 18, 24.0, 14, 500.0, 5.0, VANISH_BLUE)


def _vanish(out, conv, d, at, frames, system_of, fires):
    """A wing goes: where the rows say (up, forward, sideways from his chest: one spawn each wing) it shatters into ice: a
    faint frost over the wing's breadth for a few frames, rising, and a glitter of white and pale blue sparks rising as the
    wing does and lingering after it (Tekken 8's: some 200 sparks over 0.3 s; the wing's own icy dissolve is its
    model's); left there."""
    place = d['clip']['place']
    (up, forward, sideways), _ = place if place is not None else ((600.0, 0.0, 0.0), None)
    spot = at.part(HIPS, 0) + at.level((sideways, up + disks8.BONE_ABOVE_HIPS, forward))
    if 'wing' in d['source']:
        veins = _veins(conv, d, system_of)
        out.sprite(veins, at(spot, 0), 0, VANISH_FROST, VANISH_SHEET * 0.75, 1, 0.0, 0.0, True,
                   [[0, 0.0], [1, 0.5], [VANISH_FROST // 2, 0.4], [VANISH_FROST, 0.0]], lean=0.0, grow=1.15)
        for k in range(VANISH_BURSTS):
            out.sparks(at(spot + at.level((0.0, VANISH_RISE * k, 0.0)), 2 * k), 2 * k, VANISH_LIFE, VANISH_GLINT,
                       VANISH_COUNT, VANISH_SHEET * 0.5, 4.0, ICE_WHITE if k % 2 == 0 else VANISH_BLUE)
        return
    for k in range(3):
        out.sparks(at(spot, 2 * k), 2 * k, 20, 22.0, 20, 500.0, 6.0, VANISH_BLUE)


def _offset(d, system_of, at):
    """Where a burst goes from his hips (level frame of its spawn: x left, y up, z ahead, mm): where the rows in front
    of its spawn say (from the bone they count from), else its system's own User.OffsetPos (Tekken 8: cm ahead, right, up)."""
    place = d['clip']['place']
    if place is not None:
        (up, forward, sideways), _ = place
        return at.part(HIPS, 0) + at.level((sideways, up + disks8.BONE_ABOVE_HIPS, forward))
    user = system_of(d['id']).user.get('User.OffsetPos') or (0.0, 0.0, 0.0)
    return at.part(HIPS, 0) + at.level(np.array((-user[1], user[2], user[0])) * 10.0)


def beam_core_look():
    """Gigaflare's beam seen from its side (made here: no texture of theirs): across it (u) a dark navy core with brighter
    blue streaks along it and small white specks, edges that waver along it (v), a broad white-blue sheath round the
    core fading to blue and to nothing at the picture's edges; it repeats along v."""
    w, h = 64, 256
    rs = np.random.RandomState(7)

    def noise(cells_v, cells_u):                            # (smooth: between random values; repeating along v)
        g = rs.rand(cells_v, cells_u + 1).astype(np.float32)
        y = np.arange(h, dtype=np.float32) * cells_v / h
        x = np.arange(w, dtype=np.float32) * cells_u / (w - 1.0)
        y0, x0 = y.astype(int), np.minimum(x.astype(int), cells_u - 1)
        fy, fx = (y - y0)[:, None], (x - x0)[None, :]
        fy, fx = fy * fy * (3.0 - 2.0 * fy), fx * fx * (3.0 - 2.0 * fx)
        y1 = (y0 + 1) % cells_v
        top = g[y0][:, x0] * (1.0 - fx) + g[y0][:, x0 + 1] * fx
        low = g[y1][:, x0] * (1.0 - fx) + g[y1][:, x0 + 1] * fx
        x = top * (1.0 - fy) + low * fy
        return (x - x.min()) / max(float(x.max() - x.min()), 1e-4)
    v, u = np.meshgrid((np.arange(h, dtype=np.float32) + 0.5) / h, (np.arange(w, dtype=np.float32) + 0.5) / w, indexing='ij')
    d = np.abs(u - 0.5) * 2.0                               # (0 on the beam's line, 1 at its edge)
    streaks = np.clip((0.6 * noise(3, 9) + 0.4 * noise(6, 14) - 0.45) / 0.35, 0.0, 1.0) ** 1.5     # (long along it)
    rim_at = BEAM_RIM_AT + BEAM_WAVER * (noise(BEAM_WAVES, 1)[:, :1] - 0.5)
    specks = np.zeros((h, w), np.float32)
    for sv, su, s in zip(rs.rand(BEAM_SPECKS), rs.rand(BEAM_SPECKS), 0.3 + 0.5 * rs.rand(BEAM_SPECKS)):
        dv = ((v - sv + 0.5) % 1.0 - 0.5) * h / 2.5         # (a little longer along it; wrapping round its ends)
        du = (u - (0.5 + (su - 0.5) * BEAM_RIM_AT)) * w
        specks = np.maximum(specks, s * np.exp(-(dv * dv + du * du)))
    core = np.asarray(BEAM_CORE, np.float32) * (1.0 - streaks[..., None]) + np.asarray(BEAM_STREAK, np.float32) * streaks[..., None]
    core = core + np.asarray(BEAM_RIM, np.float32) * specks[..., None]
    inside = np.clip((rim_at - d) / 0.05, 0.0, 1.0)
    out = np.clip(1.0 - (d - rim_at) / BEAM_SHEATH, 0.0, 1.0)[..., None]     # (white at the core, blue further out)
    sheath = np.exp(-(np.maximum(d - rim_at, 0.0) / BEAM_SHEATH) ** 2) * (1.0 - inside)
    rgb = core * inside[..., None] + (np.asarray(BEAM_RIM, np.float32) * out + np.asarray(BEAM_GLOW, np.float32) * (1.0 - out)) * (1.0 - inside[..., None])
    a = np.clip(inside * 0.97 + sheath, 0.0, 1.0)
    return np.round(np.dstack([np.clip(rgb, 0.0, 1.0), a]) * 255.0)


def beam_piece(start, ahead, up, near, far, high_near, high_far, along=0.0):
    """A piece of the beam as a model from `near` to `far` mm along it from `start`, `high_near` to `high_far` mm from its
    line to its edges: one standing quad (TTT2's camera sees it from the side; a lying one crossed with it showed as a
    line along its middle). -> (positions in the clip's frame, uv (u across, v along: BEAM_TILE mm a picture, `along`
    mm on), triangles)."""
    pos, uv = [], []
    for z, high in ((near, high_near), (far, high_far)):
        for q in (0.0, 1.0):
            pos.append(start + ahead * z + up * high * (2.0 * q - 1.0))
            uv.append((q, (z + along) / BEAM_TILE))
    return np.array(pos, np.float64), np.array(uv, np.float32), np.array([(0, 2, 1), (1, 2, 3)], np.int64)


def _beam(out, conv, d, at, frames, system_of, fires):
    """Gigaflare's beam: from in front of him (its system's offset) straight ahead along his level, the pieces one after
    another as it shoots out, left in the air (Tekken 8's is not attached): a dark navy core streaked with blue in
    a white-blue sheath, wide at the orb and narrowing to a point far off (models, its pictures running out along it), a
    blue glow round it that throbs, a blue orb where it starts, lightning round the orb, blue sparks along it."""
    start, ahead = _offset(d, system_of, at), at.level((0.0, 0.0, 1.0))
    up = at.level((0.0, 1.0, 0.0))
    core = conv.textures.bake(('burst', 'beam', 'core'), beam_core_look(), largest=256)
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    step = BEAM_PIECE * (1.0 - 2.0 * BEAM_ENDS * 0.8)
    length = step * BEAM_PIECES
    high = lambda z: max(BEAM_HIGH_NEAR * (1.0 - z / length) ** BEAM_TAPER, BEAM_HIGH_FAR)
    for k in range(BEAM_PIECES):
        f = k // 2
        life = max(4, frames - f)
        near, far = step * k, step * (k + 1)
        pos, uv, tris = beam_piece(start, ahead, up, near, far, high(near), high(far), -BEAM_RUN * f * BEAM_TILE)
        colour = [(255, 255, 255, 255 if (k < BEAM_PIECES - 1 or i < 2) else 0) for i in range(len(pos))]   # (its pictures in step
        # with the pieces before it, which started running sooner; the last piece's far end fades)
        name = 'mfm_t7_%03d.nud' % len(conv.models)
        disks8.write_model(conv, name, np.asarray(at(pos, f), np.float32), uv, colour, tris, core[1])
        e = trails8.emitter(conv, name, core, life, 1e9)
        sp = e['spawner']
        disks8.alo._set_keys(sp['tracks'][disks8.alo.ALPHA_TRACK], [[0, 0.0], [1, 1.0], [life - 8, 0.95], [life, 0.0]])
        disks8.alo._set_keys(sp['layers'][0]['uvs'][0]['tracks'][8], [[0, 0.0, -BEAM_RUN]])     # (its pictures run out along it)
        P._set(e, '>HHHHHH', disks8.alo.INTERVAL, 0xFFFF, 0, 1, 0, P._u16(f), 0)
        out.bits.append((e, core, name))
        if k % 2 == 0:                                      # (a blue glow round it that throbs)
            centre = start + ahead * (near + step * 0.5)
            pulse = [[0, 0.0]] + [[t, 0.4 if (t // 3) % 2 else 0.25] for t in range(2, life - 6, 3)] + [[life, 0.0]]
            out.bar(glow, at(centre + ahead * step * 0.5, f), f, life, BEAM_PIECE * 1.8, high(near) * 2.0 * BEAM_GLOW_HIGH, True, pulse, BEAM_TINT)
    orb = [[0, 0.0], [2, 1.0]] + [[t, 0.8 if (t // 2) % 2 else 1.0] for t in range(4, frames - 6, 2)] + [[frames, 0.0]]
    out.sprite(glow, at(start, 0), 0, frames, 900.0, 1, 0.0, 0.0, True, orb, lean=0.0, colour=BEAM_TINT)
    out.sprite(glow, at(start, 0), 0, frames, 450.0, 1, 0.0, 0.0, True, orb, lean=0.0)
    source = d['source']
    path = disks8._named(disks8._textures(conv, system_of(source['bolts'])), source['emitters']['bolt'])['BaseTexture']
    bolts = [conv.textures.bake(('burst', 'bolts', k), disks8.bolt_look(conv.store, path, k, disks8.RAMPS['thunder']), largest=256)
             for k in range(4)]
    for f in range(0, max(1, frames - 4), 4):
        out.sprite(bolts[f // 4 % 4], at(start, f), f, 6, 900.0, 1, 120.0, 0.0, False, [[0, 1.0], [3, 0.9], [6, 0.0]])
    for k in range(4):
        f = k * frames // 4
        out.sparks(at(start + ahead * (600.0 + 1500.0 * k), f), f, 16, 26.0, 18, 400.0, 12.0, VANISH_BLUE)


def _zap(out, conv, d, at, frames, system_of, fires):
    """Pile Driver's: where the staff strikes the floor (the rows' place), a column of violet lightning up from it, a
    small flash and glow there, violet sparks; left there (no disc of light: in TTT2 it was a white-out)."""
    spot = _spot(d, at, system_of) - np.array((0.0, 60.0, 0.0))
    source = d['source']
    path = disks8._named(disks8._textures(conv, system_of(source['bolts'])), source['emitters']['bolt'])['BaseTexture']
    tall = [conv.textures.bake(('burst', 'bolts', 'violet', k), disks8.bolt_look(conv.store, path, k, disks8.RAMPS['violet']), largest=256)
            for k in disks8.THUNDER_CELLS]
    size = ZAP_HIGH / ZAP_PIECES
    for f in range(0, frames, 3):                           # (narrower than its pictures: Tekken 8's column is thin)
        for k in range(ZAP_PIECES):
            out.bar(tall[(f // 3 + k) % len(tall)], at(spot + np.array((0.0, size * (k + 0.5), 0.0)), f), f, 5, size * ZAP_THIN,
                    size * 1.15, False, [[0, 1.0], [3, 0.9], [5, 0.0]])
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    out.sprite(glow, at(spot + np.array((0.0, 80.0, 0.0)), 0), 0, 8, 520.0, 1, 0.0, 0.0, True, [[0, 0.0], [1, 0.9], [8, 0.0]], lean=0.0)
    out.sprite(glow, at(spot + np.array((0.0, 60.0, 0.0)), 0), 0, frames, 900.0, 1, 0.0, 0.0, True,
               [[0, 0.0], [2, 0.6], [frames - 6, 0.45], [frames, 0.0]], lean=0.0, colour=ZAP_VIOLET)
    for k in range(2):
        out.sparks(at(spot + np.array((0.0, 100.0, 0.0)), 3 * k), 3 * k, 18, 26.0, 20, 450.0, 16.0, ZAP_VIOLET)


def _blast(out, conv, d, at, frames, system_of, fires):
    """Stone Smite's hit: golden flames bursting where the rows put it, a gold glow (a modest one: in TTT2 its disc was a
    white-out over half the screen), gold sparks; left there."""
    spot = _offset(d, system_of, at)
    gold = disks8._flames(conv, fires, 'blaze')
    for k in range(8):
        f = k // 2
        out.flame(at(spot, f), f, 12, 720.0 - 40.0 * k, 1, 260.0, 3.0, k, gold)
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    out.sprite(glow, at(spot, 0), 0, 12, 1000.0, 1, 0.0, 0.0, True, [[0, 0.0], [1, 0.7], [4, 0.45], [12, 0.0]], lean=0.0,
               colour=BLAST_GOLD)
    for k in range(2):
        out.sparks(at(spot, 2 * k), 2 * k, 20, 28.0, 24, 520.0, 18.0, BLAST_GOLD)


def _rise(out, conv, d, at, frames, system_of, fires):
    """The Phoenix's wall of fire (E16's 10): a wall of flames rising out of the floor ahead of him (its offset), row
    over row as it climbs, leaning away from him as it rises, then burning out from the floor up."""
    spot = _offset(d, system_of, at)
    base = np.array((spot[0], at.floor(), spot[2]))
    ahead = at.level((0.0, 0.0, 1.0))
    for r in range(RISE_ROWS):
        q = r / (RISE_ROWS - 1.0)
        f = int(q * RISE_CLIMB)
        life = max(6, frames - f - int((1.0 - q) * 8))
        for c, across in enumerate(RISE_ACROSS):
            p = base + ahead * (across * (1.0 - 0.5 * q) + RISE_LEAN * q ** 1.5) + np.array((0.0, 120.0 + RISE_HIGH * q, 0.0))
            out.flame(at(p, f), f, life, RISE_SIZE * (1.0 - 0.35 * q), 1, 90.0, 4.0, r * 3 + c)
    for k in range(2):
        out.sparks(at(base + np.array((0.0, 300.0 + 900.0 * k, 0.0)), 2 + 3 * k), 2 + 3 * k, 22, 26.0, 22, 600.0, 18.0)


# ------------------------------------------------------------------------------------------------ Ultimate Zantetsuken
def slash_look(bend=0.0):
    """A sword's slash of light (made here: no texture of theirs): a thin white line along the picture (u) in a blue glow,
    thin and faint at both ends; `bend`: how far its middle bows off its ends (a share of the picture's height)."""
    w, h = 512, 64
    v, u = np.meshgrid((np.arange(h, dtype=np.float32) + 0.5) / h, (np.arange(w, dtype=np.float32) + 0.5) / w, indexing='ij')
    mid = 0.5 + bend * (1.0 - (2.0 * u - 1.0) ** 2) - bend * 0.5
    d = np.abs(v - mid)
    ends = np.sin(np.pi * u) ** 0.8
    core = np.exp(-(d / (SLASH_CORE * (0.3 + 0.7 * ends))) ** 2) * ends
    glow = np.exp(-(d / SLASH_GLOW) ** 2) * ends * SLASH_GLOW_ALPHA
    a = np.clip(core + glow, 0.0, 1.0) * np.clip(np.minimum(v, 1.0 - v) * 12.0, 0.0, 1.0)
    white = np.clip((core - 0.3) / 0.6, 0.0, 1.0)[..., None]       # (white where the line is, blue round it)
    rgb = np.asarray(ZAN_WHITE, np.float32) * white + np.asarray(ZAN_BLUE, np.float32) * (1.0 - white)
    return np.round(np.dstack([np.clip(rgb, 0.0, 1.0), a]) * 255.0)


def crescent_look():
    """A disk of blue light as a blade is drawn round (made here): a crescent, thickest at its top and gone at its ends, a
    white line along its outer rim, blue inside it fading towards the inner edge, streaked along its way round."""
    n = 256
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    x, y = u - 0.5, 0.5 - v
    outer = CRESCENT[0] - np.hypot(x, y)                    # (inside the outer circle: > 0)
    inner = np.hypot(x, y + CRESCENT[2]) - CRESCENT[1]      # (outside the inner one: > 0)
    body = np.clip(outer * n / 2.0, 0.0, 1.0) * np.clip(inner * n / 2.0, 0.0, 1.0)
    share = np.clip(outer / np.maximum(outer + inner, 1e-4), 0.0, 1.0)     # (0 at the outer rim, 1 at the inner edge)
    turn = np.arctan2(y, x)
    streaks = 0.65 + 0.35 * np.sin(turn * 23.0 + 2.0 * np.sin(turn * 7.0)) * np.sin(share * 9.0 + turn * 3.0)
    thick = np.clip((outer + inner) / (CRESCENT[0] - CRESCENT[1] + CRESCENT[2]) * 1.6, 0.0, 1.0)  # (1 at its top, 0 at its ends)
    rim = np.exp(-(outer * n / 3.0) ** 2) * np.clip(inner * n / 2.0, 0.0, 1.0) * thick
    a = np.clip(body * (1.0 - share) * streaks * 0.85 + rim, 0.0, 1.0)
    white = np.clip(rim + (1.0 - share) ** 6, 0.0, 1.0)[..., None]
    rgb = np.asarray(ZAN_WHITE, np.float32) * white + np.asarray(ZAN_BLUE, np.float32) * (1.0 - white)
    return np.round(np.dstack([np.clip(rgb, 0.0, 1.0), a]) * 255.0)


def sigil_look(store, path):
    """Odin's sigil (Tekken 8's mask texture of it, its lines white): pale blue lines, opaque where the mask is bright."""
    img = disks8._image(store, path, {})
    x = img[..., 0]
    a = np.clip(x * 1.5, 0.0, 1.0)
    rgb = np.broadcast_to(np.asarray(ZAN_SIGIL, np.float32), img.shape[:2] + (3,))
    return np.round(np.dstack([rgb, a]) * 255.0)


def _zan_target(at, f=0):
    """Where his blow lands in Ultimate Zantetsuken: the victim's chest ahead of him (the clip's frame)."""
    spot = at.part(HIPS, f) + at.level((0.0, 0.0, ZAN_AHEAD), f)
    return np.array((spot[0], at.floor() + ZAN_HIGH, spot[2]))


def _zan_trail(out, conv, d, at, frames, system_of, fires):
    """Ultimate Zantetsuken's blue slash (Tekken 8's 99, TrailBlue: a disk of blue light round him as Odin's blade is
    drawn, its colour the material's, out of the converter's reach): a crescent of white-blue light round his chest, a
    little ahead, fading; blue sparks; left in the air."""
    tex = conv.textures.bake(('burst', 'zan', 'crescent'), crescent_look(), largest=256)
    chest = at.part(CHEST, 0) + at.level((0.0, 0.0, ZAN_TRAIL_AHEAD))
    out.sprite(tex, at(chest, 0), 0, frames, ZAN_TRAIL_SIZE, 1, 0.0, 0.0, True,
               [[0, 0.0], [1, 1.0], [6, 0.9], [frames, 0.0]], lean=0.0)
    out.turned(ZAN_TRAIL_TILT)
    out.sparks(at(chest, 1), 1, 18, 24.0, 20, 600.0, 14.0, VANISH_BLUE)


def _zan_sigil(out, conv, d, at, frames, system_of, fires):
    """Odin's sigil as the blade is sheathed (Tekken 8's 38: its Logo001, a sprite on the GPU, came out 20 cm at his
    hips): the sigil behind him, a blue flash, a blue glow on the floor under him; they stay while he waits."""
    path = disks8._named(disks8._textures(conv, system_of(d['id'])), 'Logo')['MaskTexture']
    sigil = conv.textures.bake(('burst', 'zan', 'sigil'), sigil_look(conv.store, path), largest=256)
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    back = at.part(CHEST, 0) + at.level((0.0, 100.0, -150.0))
    keys = [[0, 0.0], [6, 0.9], [frames - 12, 0.75], [frames, 0.0]]
    out.sprite(sigil, at(back, 0), 0, frames, ZAN_SIGIL_SIZE, 1, 0.0, 0.0, True, keys, lean=0.0)
    out.sprite(glow, at(back, 0), 0, 16, ZAN_SIGIL_SIZE * 0.8, 1, 0.0, 0.0, True, [[0, 0.0], [2, 0.8], [16, 0.0]], lean=0.0,
               colour=ZAN_BLUE)
    hips = at.part(HIPS, 0)
    out.bar(glow, at(np.array((hips[0], at.floor() + 40.0, hips[2])), 0), 0, frames, ZAN_SIGIL_SIZE * 1.2, 360.0, True,
            [[0, 0.0], [6, 0.6], [frames - 12, 0.5], [frames, 0.0]], ZAN_BLUE)


def _zan_ranbu(out, conv, d, at, frames, system_of, fires):
    """Ultimate Zantetsuken's flurry (Tekken 8's 98, ZantetsuRanbu: thin rings of blue-white light, 3 at once then 50 a
    second for 0.2 s, placed by the camera): thin slashes of white-blue light over the victim at every angle, a few
    at once then one a frame or so, each gone in a few frames; a blue flash; sparks."""
    slashes = [conv.textures.bake(('burst', 'zan', 'slash', b), slash_look(b), largest=512) for b in SLASH_BENDS]
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    rs = np.random.RandomState(98)
    centre = _zan_target(at)
    for k in range(ZAN_SLASHES):
        f = 0 if k < 3 else int(round(1 + (k - 3) * ZAN_RANBU_EVERY))
        p = centre + at.level((0.0, rs.uniform(*ZAN_RANBU_UP), rs.uniform(-ZAN_RANBU_ACROSS, ZAN_RANBU_ACROSS)))
        out.bar(slashes[k % len(slashes)], at(p, f), f, ZAN_SLASH_LIFE, rs.uniform(*ZAN_SLASH_LONG), ZAN_SLASH_HIGH, True,
                [[0, 0.0], [1, 1.0], [4, 0.9], [ZAN_SLASH_LIFE, 0.0]])
        out.turned(rs.uniform(-math.pi / 2.0, math.pi / 2.0))
    out.sprite(glow, at(centre, 0), 0, 10, 1400.0, 1, 0.0, 0.0, True, [[0, 0.0], [1, 0.7], [10, 0.0]], lean=0.0, colour=ZAN_BLUE)
    for f in (0, 5, 10):
        out.sparks(at(centre, f), f, 16, 24.0, 16, 700.0, 16.0, VANISH_BLUE)


def _zan_last(out, conv, d, at, frames, system_of, fires):
    """Ultimate Zantetsuken's last cut (Tekken 8's 96, ZantetsuLast: a line of blue-white light, a shockwave, 200 sparks):
    one long level line of light through the victim, a white core in it, a flash, a blue ring growing out, sparks."""
    slash = conv.textures.bake(('burst', 'zan', 'slash', SLASH_BENDS[0]), slash_look(SLASH_BENDS[0]), largest=512)
    glow = conv.textures.bake(('burst', 'glow'), glow_look(), largest=64)
    ring = conv.textures.bake(('burst', 'ring'), ring_look(), largest=128)
    centre = _zan_target(at)
    centre[1] = at.floor() + ZAN_LAST_HIGH
    out.bar(slash, at(centre, 0), 0, 14, ZAN_LAST_LONG, ZAN_SLASH_HIGH * 2.0, True, [[0, 0.0], [1, 1.0], [5, 0.9], [14, 0.0]])
    out.bar(slash, at(centre, 1), 1, 8, ZAN_LAST_LONG * 0.8, ZAN_SLASH_HIGH, True, [[0, 0.0], [1, 1.0], [8, 0.0]])
    out.sprite(glow, at(centre, 0), 0, 12, 1600.0, 1, 0.0, 0.0, True, [[0, 0.0], [1, 1.0], [12, 0.0]], lean=0.0, colour=ZAN_BLUE)
    out.sprite(ring, at(centre, 1), 1, 14, 700.0, 1, 0.0, 0.0, True, [[0, 0.9], [14, 0.0]], lean=0.0, colour=ZAN_BLUE, grow=5.0)
    for k in range(2):
        out.sparks(at(centre, 2 * k), 2 * k, 22, 26.0, 32, 900.0, 20.0, VANISH_BLUE)


# ------------------------------------------------------------------------------------------------ Garuda, Torgal
def wind_streak_look():
    """Garuda's wind as he leaps (made here: no texture of theirs): a dark grey-green brush stroke along the picture,
    streaked along its length, thicker at its head (u 1), a thin pale green line along it."""
    w, h = 512, 128
    rs = np.random.RandomState(66)
    v, u = np.meshgrid((np.arange(h, dtype=np.float32) + 0.5) / h, (np.arange(w, dtype=np.float32) + 0.5) / w, indexing='ij')
    ends = np.sin(np.pi * u) ** 0.6 * (0.35 + 0.65 * u)
    across = np.exp(-((v - 0.5) / (0.3 * (0.3 + 0.7 * ends) + 1e-3)) ** 2)
    lines = np.zeros_like(u)
    for _ in range(18):
        row, thick, start = rs.uniform(0.25, 0.75), rs.uniform(0.01, 0.04), rs.uniform(-0.2, 0.5)
        lines = np.maximum(lines, np.exp(-((v - row) / thick) ** 2) * np.clip((u - start) * 4.0, 0.0, 1.0) * rs.uniform(0.5, 1.0))
    a = np.clip(across * (0.55 + 0.45 * lines) * ends * 2.0, 0.0, 1.0) * WIND_STREAK_ALPHA
    line = np.exp(-((v - 0.6 + 0.08 * (1.0 - u)) / 0.016) ** 2) * ends * np.clip(u * 3.0 - 0.6, 0.0, 1.0)
    rgb = np.asarray(WIND_DARK, np.float32) * (1.0 - line[..., None]) + np.asarray(WIND_LINE, np.float32) * line[..., None]
    a = np.maximum(a, line * 0.9) * np.clip(np.minimum(v, 1.0 - v) * 12.0, 0.0, 1.0)
    return np.round(np.dstack([np.clip(rgb, 0.0, 1.0), a]) * 255.0)


def _updraft(out, conv, d, at, frames, system_of, fires):
    """Updraft's leap (Tekken 8's 66, Garuda's aura round his body, and 65's on the floor): a dark wind streak left
    behind him every other frame as he rises (each lingers a little: a trail along his way), white feathers, and a
    pale swirl of wind on the floor ahead where he leaves it (its offset, Tekken 8's 1.2 m). One for all the moves
    (their leaps alike): places from where his hips are."""
    streak = conv.textures.bake(('burst', 'wind', 'streak'), wind_streak_look(), largest=512)
    if d['burst'][0] == 'updraft':
        for f in range(0, frames, 2):
            out.bar(streak, np.array((0.0, UPDRAFT_UP, -UPDRAFT_BEHIND)), f, UPDRAFT_LIFE, UPDRAFT_WIDE, UPDRAFT_HIGH, False,
                    [[0, 0.0], [1, 0.85], [UPDRAFT_LIFE // 2, 0.7], [UPDRAFT_LIFE, 0.0]])
        _feathers(out, conv, dict(d, burst=('feathers',) + tuple(d['burst'][1:])), at, frames, system_of, fires)
        return
    swirl = conv.textures.bake(('burst', 'wind', 'swirl'), swirl_look(), largest=256)
    hips = at.part(HIPS, 0)
    floor = at(np.array((hips[0], at.floor() + 40.0, hips[2])) + at.level((0.0, 0.0, UPDRAFT_SWIRL_AHEAD)), 0)
    for k in range(3):
        out.bar(swirl, floor, 2 * k, 16, UPDRAFT_SWIRL * (1.0 + 0.3 * k), UPDRAFT_SWIRL * 0.3, False,
                [[0, 0.0], [2, UPDRAFT_SWIRL_ALPHA], [10, UPDRAFT_SWIRL_ALPHA * 0.6], [16, 0.0]], WIND_PALE)
        out.grown(16, 1.6)
    out.bar(streak, floor + np.array((0.0, 150.0, 0.0)), 0, 12, UPDRAFT_WIDE * 0.8, UPDRAFT_HIGH * 0.6, False,
            [[0, 0.0], [1, 0.6], [12, 0.0]])
    _feathers(out, conv, dict(d, burst=('gust',) + tuple(d['burst'][1:])), at, frames, system_of, fires)


def swirl_look():
    """Wisps of wind round a swirl (made here): broken soft arcs of a ring, thicker and thinner along it."""
    n = 256
    rs = np.random.RandomState(65)
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    x, y = u - 0.5, v - 0.5
    r, turn = np.hypot(x, y) * 2.0, np.arctan2(y, x)
    a = np.zeros_like(u)
    for _ in range(7):
        at, wide, start, span = rs.uniform(0.45, 0.9), rs.uniform(0.02, 0.06), rs.uniform(-np.pi, np.pi), rs.uniform(0.8, 2.2)
        along = np.clip(np.sin(np.clip(((turn - start) % (2.0 * np.pi)) / span, 0.0, 1.0) * np.pi), 0.0, 1.0)
        a = np.maximum(a, np.exp(-((r - at - 0.05 * np.sin(turn * 3.0 + start)) / wide) ** 2) * along * rs.uniform(0.5, 1.0))
    a = a * (r < 1.0)
    return np.round(np.dstack([np.ones_like(u), np.ones_like(u), np.ones_like(u), np.clip(a, 0.0, 1.0)]) * 255.0)


def thin_ring_look():
    """A thin soft ring (made here)."""
    n = 256
    v, u = np.meshgrid((np.arange(n, dtype=np.float32) + 0.5) / n, (np.arange(n, dtype=np.float32) + 0.5) / n, indexing='ij')
    r = np.hypot(u - 0.5, v - 0.5) * 2.0
    a = np.exp(-((r - 0.9) / 0.025) ** 2) + 0.25 * np.exp(-((r - 0.9) / 0.08) ** 2)
    return np.round(np.dstack([np.ones_like(u), np.ones_like(u), np.ones_like(u), np.clip(a, 0.0, 1.0) * (r < 1.0)]) * 255.0)


def _heat(out, conv, d, at, frames, system_of, fires):
    """Torgal's heat as he strikes (Tekken 8's 199, smf_wind03_Heat: two domes of a heat haze whose edges glow orange;
    TTT2 cannot bend the picture, a dome's edge it can): a thin tall golden ellipse round where he strikes, growing a
    little, fading. One for all the moves (on the part Tekken 8 names)."""
    ring = conv.textures.bake(('burst', 'ring', 'thin'), thin_ring_look(), largest=256)
    spot = np.array(HEAT_AT)
    keys = [[0, 0.0], [2, 0.9], [frames - 8, 0.6], [frames, 0.0]]
    out.bar(ring, spot, 0, frames, HEAT_WIDE, HEAT_HIGH, True, keys, HEAT_GOLD)
    out.grown(frames, 1.25)
    out.turned(HEAT_TILT)


BEAM_PIECES, BEAM_PIECE = 6, 1400.0  # (its pieces, each one's length, mm: by Tekken 8's frames)
BEAM_ENDS = 0.14                    # (the share of a piece's picture its soft ends take)
BEAM_RIM_AT = 0.24                  # (where its core's edges are: a share of its breadth from its line)
BEAM_CORE, BEAM_RIM, BEAM_GLOW = (0.05, 0.05, 0.3), (0.86, 0.94, 1.0), (0.35, 0.55, 1.0)     # by Tekken 8's frames
BEAM_STREAK = (0.15, 0.3, 0.95)     # (the core's streaks)
BEAM_SPECKS = 40                    # (the core's white specks in a picture)
BEAM_SHEATH = 0.4                   # (how far its sheath reaches out from the core: a share of its breadth)
BEAM_HIGH_NEAR, BEAM_HIGH_FAR = 300.0, 20.0     # (mm from its line to its glow's edge at the orb, and at its far end: by Tekken 8's frames)
BEAM_TAPER = 1.0                    # (it narrows to a point at its far end, evenly)
BEAM_TILE, BEAM_RUN = 1200.0, 0.08  # (mm along it a picture; pictures a frame its pictures run out along it)
BEAM_WAVER = 0.1                    # (how far its core's edges waver: a share of its breadth)
BEAM_WAVES = 8                      # (its edges' waves in a picture's length)
BEAM_GLOW_HIGH = 2.4                # (its glow's height, times the beam's)
BEAM_TINT = (0.45, 0.62, 1.0)
ZAP_HIGH, ZAP_PIECES = 2600.0, 4    # (mm: Pile Driver's lightning from the floor up past his head; by Tekken 8's frames)
ZAP_THIN = 0.5                      # (its pictures' width, a share of their height)
ZAP_VIOLET = (0.72, 0.5, 1.0)
BLAST_GOLD = (1.0, 0.8, 0.38)
RISE_ROWS, RISE_CLIMB, RISE_HIGH = 9, 6, 3000.0      # (rows of flames; the frames the wall takes to rise; mm it rises to)
RISE_ACROSS = (-350.0, 0.0, 350.0)  # (mm ahead of its place: its breadth as the camera sees it)
RISE_LEAN, RISE_SIZE = 500.0, 760.0
SPARK_PINK = (1.0, 0.4, 0.6)        # (a spark's colour: by Tekken 8's frames)
VANISH_BLUE = (0.75, 0.9, 1.0)
WING_ROOT = (130.0, 80.0, -140.0)   # (mm from the chest, level frame: a wing's root on his back, left; by Tekken 8's frames)
WING_OUT, WING_BACK = 0.35, 0.6     # (the way a rising wing goes from its root: out to its side and back for each up; by Tekken 8's frames)
WING_SHEETS = ((450.0, 1000.0), (1100.0, 1100.0), (1750.0, 1000.0))     # (its flash's pictures: mm along it, size)
WING_RING, WING_RING_LIFE = 700.0, 18                    # (the ring at its root: mm at the start, frames)
WING_ADDED = False                  # (its frost drawn over the stage, white on any: added light vanished on a bright one)
WING_SWEEP, WING_SWEEP_AT = (0.55, 1.0), 5    # (the way the wing sweeps back: up, back for each; from its flash's frame 5)
WING_SWEPT = ((700.0, 1200.0), (1400.0, 1400.0), (2100.0, 1300.0))     # (its frost's pictures then: mm along it, size)
VANISH_SHEET = 1500.0               # (mm: a wing's breadth as it shatters)
VANISH_BURSTS, VANISH_COUNT = 6, 36  # (its glitter: bursts two frames apart, sparks a burst)
VANISH_GLINT, VANISH_LIFE = 45.0, 24  # (mm a spark, frames it lingers)
VANISH_FROST = 10                   # (frames its frost shows)
VANISH_RISE = 150.0                 # (mm higher each burst: rising with the wing)
VEINS_SIDE, VEINS_GLOW = 256, 14     # (the flash's picture: texels, and how far its glow spreads round a line)
ICE_WHITE, ICE_BLUE = (0.9, 0.97, 1.0), (0.4, 0.62, 1.0)
# Ultimate Zantetsuken (made here: Tekken 8's colours are its materials' BaseColor, HDR blue-white; places by its
# clips' fighters: the victim stands about a metre ahead of him as he waits)
ZAN_WHITE, ZAN_BLUE, ZAN_SIGIL = (1.0, 1.0, 1.0), (0.45, 0.65, 1.0), (0.78, 0.9, 1.0)
ZAN_AHEAD, ZAN_HIGH = 1100.0, 1100.0                # (mm ahead of his hips, over the floor: the victim's chest)
ZAN_TRAIL_AHEAD, ZAN_TRAIL_SIZE, ZAN_TRAIL_TILT = 300.0, 2400.0, -0.35      # (Tekken 8's disk at 2x its scale, turned 20 degrees)
ZAN_SIGIL_SIZE = 1800.0
ZAN_SLASHES, ZAN_RANBU_EVERY = 13, 0.9              # (3 at once, then 10: Tekken 8's 3 + 50 a second for 0.2 s)
ZAN_RANBU_UP, ZAN_RANBU_ACROSS = (-450.0, 500.0), 500.0
ZAN_SLASH_LONG, ZAN_SLASH_HIGH, ZAN_SLASH_LIFE = (2200.0, 3400.0), 200.0, 12
ZAN_LAST_LONG, ZAN_LAST_HIGH = 5200.0, 950.0
SLASH_CORE, SLASH_GLOW, SLASH_GLOW_ALPHA = 0.045, 0.16, 0.55
SLASH_BENDS = (0.0, 0.12, 0.25)
CRESCENT = (0.46, 0.42, 0.08)       # (its outer circle's radius, the inner one's, how far that one is below it: shares of the picture)
# Updraft's wind (by Tekken 8's frames: a dark streak behind him as he rises, a pale swirl on the floor)
WIND_DARK, WIND_LINE, WIND_PALE = (0.1, 0.12, 0.11), (0.62, 0.95, 0.68), (0.85, 0.97, 0.9)
WIND_STREAK_ALPHA = 0.95
UPDRAFT_UP, UPDRAFT_BEHIND, UPDRAFT_WIDE, UPDRAFT_HIGH, UPDRAFT_LIFE = 50.0, 800.0, 2200.0, 800.0, 10
UPDRAFT_SWIRL, UPDRAFT_SWIRL_AHEAD, UPDRAFT_SWIRL_ALPHA = 1400.0, 300.0, 0.4
# Torgal's heat (by Tekken 8's frames: a thin golden ellipse between him and the victim, floor to over the head,
# its top leaning ahead)
HEAT_AT, HEAT_WIDE, HEAT_HIGH, HEAT_TILT = (0.0, 0.0, 1500.0), 1000.0, 2400.0, -0.15
HEAT_GOLD = (1.0, 0.72, 0.38)
RECIPES = {'glow': _glow, 'glow_right': _glow, 'wing': _wing, 'wing_right': _wing, 'vanish': _vanish, 'spark': _spark, 'blade': _blade, 'body': _body, 'cloud': _cloud, 'appear': _appear, 'feet': _feet, 'hand': _hand, 'jet': _jet,
           'strike': _strike, 'floor': _floor, 'pillar': _pillar, 'ground': _ground, 'bolts': _bolts, 'bolts_right': _bolts,
           'thunder': _thunder, 'gust': _feathers, 'feathers': _feathers, 'beam': _beam, 'zap': _zap, 'blast': _blast,
           'rise': _rise, 'column': _column, 'zan_trail': _zan_trail, 'zan_sigil': _zan_sigil, 'zan_ranbu': _zan_ranbu,
           'zan_last': _zan_last, 'updraft': _updraft, 'updraft_floor': _updraft, 'heat': _heat}
