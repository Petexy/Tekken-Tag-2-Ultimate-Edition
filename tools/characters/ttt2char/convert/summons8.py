"""A Tekken 8 fighter's summoned weapons and the points its moves hit from (Miary Zo's staffs, tail, horn and snakes;
every Tekken 8 fighter's hit boxes placed from its ground origin), the TTT2 side of what the runtime already poses
for Tekken 7 fighters (title/roster.cpp, weapons; convert/weapons.py):

* SUMMONS. Tekken 8 shows and hides an object of the fighter's with one property, SHOW_PROP: its value one bit (the
  object), value2 1 show / 0 hide, value3 the fade in frames; extra properties at a frame and end properties (hide as
  the move ends). Bit 1 << n is summon n of the fighter's weapons (Miary Zo: 1 the left staff, 2 the right one, 4 the
  tail, 8 the horn, 16 the snakes' point); prepare() rewrites each row into the Tekken 8 summon / dismiss ids the
  converter already turns into TTT2's (moveset.SUMMON_PROPS: 0x822E / 0x822F n, which the runtime reads, the end
  properties through PROP_OVERRIDE), value n. Bits past MAX_SUMMON (her Rage Art's cinematic objects) are left as
  they are (dropped: no TTT2 meaning).
* ROOT POINTS. A Tekken 8 hit box names two points (loc, loc2) with offsets a, b (mm); code ROOT_CODE is the
  fighter's ground origin, the offsets in its frame (x left, y up, z forward): the generic moves every fighter has
  hit from (125, 125) a (-100, 1000, 750) b (-100, 1000, 300) (1 m high, 0.3 .. 0.75 m ahead), Miary Zo's snake and
  staff sweeps from up to 2.3 m ahead. TTT2 has no such location (moveset.HIT_LOCATION sent it to the held item's
  slot 70, which nothing writes for an added fighter): roots() gives each move hitting from it (its summary's
  two hit boxes) its two first distinct offsets, and the fighter two hit-only weapons under HARA_ROT1 (weapons():
  pairs after the definition's, ROOT_SUMMON: never summoned, so never drawn and never cut at the held reach; the
  runtime writes the points of a weapon not shown into the slots no shown one wrote) whose pairs the clip of each
  such move carries (tekken8/anim.py pair_values: the offset from the ground origin each frame); prepare() writes
  ROOT_CODES into the move's hit box summary in place of the code (the nearest of the two offsets), which the
  weapons' points map to slots ROOT_SLOTS (weapons.points_of). A clip without the pairs (TTT2's own, a generic move's
  donor animation) leaves the points at ROOT_BIND, the generic moves' offsets from a standing fighter.
* THE SUMMARY. TTT2 tests two lines per move, its four hit bytes, with no radius, offsets or frames of their own
  (sub_03C74F50: a point and the other point, or 0, the point's path since the last frame); Tekken 8 gives a move up
  to eight hit boxes, and motbin.read keeps boxes 0 and 1 (Tekken 7's summary, the id maps' evidence). prepare(place)
  keeps box 0 and box 1 unless that one is empty or on box 0's TTT2 line (the same points: their offsets are lost; or
  two points TTT2 has one place for, a toe on its foot's bone: moveset.HIT_POINT8): then the first later box on
  another line (summary). Miary Zo's u/f+3 highs had the tail's lead twice, (121, 0) and (121, 0) with offsets, and
  missed the head their (121, 125) and (121, 33) reach; her b+1,4 the foot's path twice, its toe's on the foot.

Written for this project from the files themselves (no third-party code).
"""
import collections

import numpy as np

SHOW_PROP = 0x8410                  # Tekken 8: show / hide an object of the fighter's (value bit, value2 1 / 0)
SUMMON, DISMISS = 0x8317, 0x8318    # the Tekken 8 summon ids moveset.SUMMON_PROPS converts (unused by Tekken 8 itself)
MAX_SUMMON = 4                      # bits 1 .. 16: summons 0 .. 4 (16 is the runtime's "dismiss all" as a value of
                                    # 0x822F, so no summon may be 16)
PROP_TABLES = ('extra_move_properties', 'move_begin_props', 'move_end_props')
ROOT_CODE = 125                     # Tekken 8's hit location of the fighter's ground origin
ROOT_CODES = (0xFA, 0xFB)           # the codes its two offsets get in the summary (no Tekken 8 hit box uses > 191)
ROOT_SLOTS = (2, 3)                 # their points' slots (TTT2 locations 72, 73)
ROOT_SUMMON = 63                    # never summoned (runtime: summon numbers < 64)
ROOT_PARENT = 'HARA_ROT1'
# where the root points sit without their pairs: the generic moves' offsets (every Tekken 8 fighter's #7xx moves) from
# a fighter's ground origin, as model-space positions of the bind (mm)
ROOT_BIND = (np.array([-100.0, 1000.0, 750.0]), np.array([-100.0, 1000.0, 300.0]))
MAX_PAIRS = 20                      # runtime: weapon bones OPT 800 .. 819 are posed by pairs
# Tekken 8 limb points TTT2 has no place for, made the points of TTT2's (moveset.HIT_POINT8 takes them): 138 / 139 the
# right / left arm's far point (paired with 9 / 37 and 13 / 39 in every fighter: the fists' front points, as 37 -> 40),
# 22 a head point (paired with the hips, the chest and the head: ATAMA)
HIT_POINTS = {138: 40, 139: 39, 22: 5}


def _table(k, name):
    """Tekken 8 moveset k's table `name` ([] when it has none)."""
    t = getattr(k, 'tables', None)
    return t.get(name, []) if isinstance(t, dict) else []


def line(h, place, roots=True):
    """The TTT2 line of Tekken 8 hit box h: (its point, its other point or 0), a point place(code) or at the ground
    origin ('origin', offset); None for a box on no point, or at the ground origin without root points (roots)."""
    if not h.loc and not h.loc2:
        return None
    ends = []
    for loc, off in ((h.loc, h.a), (h.loc2, h.b)):
        if loc == ROOT_CODE:
            if not roots:
                return None
            ends.append(('origin', tuple(float(x) for x in off)))
        else:
            ends.append(place(loc) if loc else 0)
    return tuple(ends)


def summary(boxes, place, roots=True):
    """The two of a Tekken 8 move's hit boxes its TTT2 summary takes: box 0, and box 1 unless that one is empty or on
    box 0's line (line(..., place, roots); a line is the same both ways round, and one point of it is on it), else
    the first later box on another line (none: box 1)."""
    first = line(boxes[0], place, roots)
    same = {first, first[::-1] if first and 0 not in first else first}

    def other(h):
        x = line(h, place, roots)
        return x is not None and x not in same and not (first and x[0] == x[1] and x[0] in first)
    if other(boxes[1]):
        return boxes[0], boxes[1]
    return boxes[0], next((h for h in boxes[2:] if other(h)), boxes[1])


def _boxes(mv):
    """A Tekken 8 move's two summary hit boxes (prepare's summary, else boxes 0 and 1)."""
    return mv.get('summary') or mv['hitboxes'][:2]


def _offsets(mv):
    """The distinct offsets (mm) of a Tekken 8 move's summary hit boxes' points at the ground origin, in order."""
    out = []
    for h in _boxes(mv):
        for loc, off in ((h.loc, h.a), (h.loc2, h.b)):
            if loc == ROOT_CODE:
                o = tuple(float(x) for x in off)
                if o not in out:
                    out.append(o)
    return out


def uses_roots(k):
    """Whether a move of Tekken 8 moveset k hits from the ground origin (its summary hit boxes)."""
    return any(_offsets(mv) for mv in _table(k, 'moves'))


def roots(k):
    """RootPoints {clip key: [offset A, offset B?]} of the clips of Tekken 8 moveset k's moves (its banks attached)
    hitting from the ground origin: their first two distinct offsets; a clip two such moves play with other offsets
    keeps the first's (.conflicts counts the others, whose codes take the nearest of those), a move whose summary
    took a later box counting after the others (its clip's points stay where boxes 0 and 1 put them: Miary Zo's u+3
    follow-ups, an area 0.6 m up, after the box from the floor up in front of her); .moves {move: its clip key}."""
    out = RootPoints()
    for i, mv in sorted(enumerate(_table(k, 'moves')), key=lambda x: 'summary' in x[1]):
        off = _offsets(mv)
        if not off:
            continue
        key = k.anim_ref(i)[0]
        if key is None:
            continue
        if key in out and out[key] != off[:2]:
            out.conflicts[key] += 1             # (its codes still take the clip's nearest points: prepare)
        else:
            out[key] = off[:2]
        out.moves[i] = key
    return out


class RootPoints(dict):
    def __init__(self):
        super().__init__()
        self.moves = {}                 # move index -> its clip key
        self.conflicts = collections.Counter()


def weapons(d, k=None):
    """A Tekken 8 fighter's weapons: its definition's WEAPONS, then (k: its Tekken 8 moveset) the two root points'
    hit-only weapons when its moves hit from the ground origin (roots)."""
    out = [dict(w) for w in getattr(d, 'WEAPONS', [])]
    if k is None or not uses_roots(k):
        return out
    first = max([w['pair'] for w in out if w.get('pair') is not None] + [-1]) + 1
    if first + len(ROOT_CODES) > MAX_PAIRS:
        raise ValueError('no animation pairs left for the root points (%d used of %d)' % (first, MAX_PAIRS))
    for r, (code, slot) in enumerate(zip(ROOT_CODES, ROOT_SLOTS)):
        out.append(dict(bone='root_%s' % 'ab'[r], parent=ROOT_PARENT, pair=first + r, summon=ROOT_SUMMON, root=r,
                        points={code: ('origin', slot)}))
    return out


def summon_of(bit):
    """The summon number of a SHOW_PROP value (one bit), or None."""
    if bit <= 0 or bit & (bit - 1):
        return None
    n = int(bit).bit_length() - 1
    return n if n <= MAX_SUMMON else None


# --- fades (convert/summonfade.py): a summon or dismissal value carries Tekken 8's fade frames (value3) ---
FADE_SHIFT = 8                      # value = n | frames << FADE_SHIFT (the runtime: frames 0 or 1 at once)
FADE_MAX = 0xFF
SUMMON_MASK = (1 << FADE_SHIFT) - 1  # the summon number's bits of a value


def fade_value(n, frames):
    """The TTT2 summon / dismissal value of summon n fading over `frames` frames (Tekken 8's value3; 0 or 1: at
    once, the value n as before)."""
    frames = min(max(int(frames or 0), 0), FADE_MAX)
    return n | frames << FADE_SHIFT if frames > 1 else n
# --- end of fades ---


def prepare(k, d, log=print, place=None):
    """Tekken 8 moveset k (motbin.read, its id maps made) made ready for the converter, in place: SHOW_PROP rows
    -> SUMMON / DISMISS n (a definition with summoned weapons), each move's summary hit boxes (place: a hit location
    code -> TTT2's, the converter's hit_location; None keeps boxes 0 and 1) and their codes, those from the ground
    origin -> ROOT_CODES (roots). -> {clip key: root offsets} (roots) for the animation provider."""
    stats = collections.Counter()
    if place is not None:
        at_root = uses_roots(k)                 # (as the model step found it: its root points, or none)
        for mv in _table(k, 'moves'):
            hb = mv.get('hitboxes') or ()
            if len(hb) < 2:
                continue
            pick = summary(hb, place, at_root)
            if pick[1] is not hb[1]:
                mv['summary'] = pick
                mv['hitbox'] = bytes((pick[0].loc, pick[0].loc2, pick[1].loc, pick[1].loc2))
                stats['moves whose summary takes a later hit box (box 1 empty or on box 0\'s line)'] += 1
    if any(w.get('summon') is not None for w in getattr(d, 'WEAPONS', [])):
        for table in PROP_TABLES:
            for row in _table(k, table):
                if row['id'] != SHOW_PROP:
                    continue
                n = summon_of(row['value'])
                if n is None:
                    stats['%s rows left out (bit %d: no summon)' % (hex(SHOW_PROP), row['value'])] += 1
                    continue
                row['id'] = SUMMON if row.get('value2') else DISMISS
                row['value'] = fade_value(n, row.get('value3', 0))
                stats['%s rows made summons / dismissals (%s)' % (hex(SHOW_PROP), table)] += 1
                if row['value'] != n:
                    stats['%s rows fading (%s over %d frames)' % (hex(SHOW_PROP), 'in' if row.get('value2') else 'out',
                                                                  row['value'] >> FADE_SHIFT)] += 1
    found = roots(k)
    if len(weapons(d, k)) > len(getattr(d, 'WEAPONS', [])):
        for i, key in found.moves.items():
            mv = k.tables['moves'][i]
            off = [np.asarray(o) for o in found[key]]
            codes = list(mv['hitbox'])
            hb = _boxes(mv)
            spots = [(hb[0].loc, hb[0].a), (hb[0].loc2, hb[0].b), (hb[1].loc, hb[1].a), (hb[1].loc2, hb[1].b)]
            for c, (loc, at) in enumerate(spots):
                if loc == ROOT_CODE and codes[c] == ROOT_CODE:
                    near = int(np.argmin([np.linalg.norm(np.asarray(at, np.float64) - o) for o in off]))
                    codes[c] = ROOT_CODES[near]
            mv['hitbox'] = bytes(codes)
            stats['moves hitting from root points'] += 1
        if found.conflicts:
            stats['moves hitting from root points another move\'s clip has elsewhere (the nearest taken)'] += sum(
                found.conflicts.values())
    for key, n in sorted(stats.items()):
        log('%s: %d' % (key, n))
    return dict(found)
