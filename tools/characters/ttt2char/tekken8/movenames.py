"""Tekken 8 move names, found on the player's machine. A Tekken 8 moveset ships no names (tekken8/motbin.py), but each
move keeps
    name key  (+0x00)  CityHash32 of its name as written ('dwDWN_00U', 'Zbr_66RK'; tekken8/city32.py)
    move key  (+0xF0)  CityHash32 of the fighter's code in capitals, '_' and the name ('ZBR_Zbr_66RK')
    length             of the name, from the stripped name block's offsets (Moveset8.name_lengths)
and a candidate names a move only when all three agree: two independent 32-bit keys and the length leave no room
for a false name. Nothing is shipped; the candidates are made at import time:
    1. the move and animation names of the installed TTT2's movesets (and of Tekken 7's, when the player has them):
       Tekken 8 keeps Tekken 7's generic names (dwDWN_00U, Co_UkerF00, sDm_...), most of them TTT2's as well
    2. each of them with its fighter's prefix (He_, Kz_) made this fighter's ('Zbr_'; 'zbr_' for intros and wins)
    3. the fighter's own commands in numpad notation: '<Code>_' + directions + buttons + a mark ('Zbr_66RK',
       'Zbr_3LPRP', 'Zbr_4LPRK_E', 'Zbr_6RPLK_EX_n')
    4. step 1's names with a number counted through ('sDm_ha37B' -> 'sDm_ha35B'), '_' added or the last character
       dropped
    5. variations of the names found so far (a number counted through, a character added, dropped or changed, left
       and right or a button swapped, a command added to a command), again for the names they find, until a round
       finds none
name_moves reports how many moves each step named ('dictionary', 'prefix', 'commands', 'numbers', 'variations').
Animations keep a name key too (+0x20, with the animation name's length): checked against step 1's names only (one
key and the length: the many variations could fit one by chance).

    from ttt2char.tekken8 import motbin, movenames
    m = motbin.read(data, fields, 'zbr')
    found = movenames.name_moves(m, movenames.ttt2_movesets(archives), tekken7=[tkmvst.read(p) ...])

Written for this project from the files themselves (no third-party code).
"""
import collections
import re

import numpy as np

from .city32 import city32, city32_rows

# ---------------------------------------------------------------------------------------------------- notation
# Numpad notation, as the fighters' own move names write commands: directions as on a keypad (6 forward, 4 back, 2
# down, 3 down-forward ...; 66 a dash, 236 a quarter circle), buttons LP RP LK RK (1 2 3 4) and WP / WK (both punches
# / both kicks); buttons pressed together or one after another are written one after another ('RPLK', 'LPRPRP')
DIRECTIONS = ['', '1', '2', '3', '4', '6', '7', '8', '9', '66', '666', '44', '444', '22', '33', '11', '99', '88',
              '236', '214', '623', '421', '41236', '63214', '2146', '6321']
BUTTONS = ['LP', 'RP', 'LK', 'RK', 'WP', 'WK']
PRESSES = 4                          # buttons in a generated command (longer strings come from variations)
# Marks after a command: a throw's victim / thrower (_n / _y, as TTT2's own throws), an enhanced version (_E, _EX),
# Tekken 8's Heat follow-ups, a second version (2), and other short marks such names end with; more are harvested
# from the dictionary's names (MARKS_HARVESTED)
MARKS = ['', '_n', '_y', '_E', '_EX', '_EX_n', '_EX_y', '_Heat', 'GS', '_GS', '2', '_2', '_r', '_S', '_hit']
MARKS_HARVESTED = 40                 # the most common last tokens ('_xx' up to 4 characters) of the dictionary's names
MARK_RE = re.compile(rb'_[A-Za-z0-9]{1,4}$')
SEPARATORS = ['', '_', 's']          # between a command and the one added to it ('Zbr_6WP_9LK', 'Zbr_RPsLP')

# ---------------------------------------------------------------------------------------------------- variations
CHARS = b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_'
SWAPS = [(b'L', b'R'), (b'R', b'L'), (b'F', b'B'), (b'B', b'F'), (b'l', b'r'), (b'r', b'l'), (b'U', b'D'),
         (b'D', b'U'), (b'p', b'k'), (b'k', b'p'), (b'0', b'1'), (b'1', b'0'), (b'n', b'y'), (b'y', b'n')]
INSERT_UP_TO = 14                    # names this long get a character inserted anywhere (longer: too many tries)
ROUNDS = 6                           # variation rounds at most (each varies the names the round before found)
NUMBER_RE = re.compile(rb'\d+')
BUTTON_RE = re.compile(rb'LP|RP|LK|RK|WP|WK')
PREFIX_RE = re.compile(rb'^([A-Za-z][A-Za-z0-9]{0,2})_(.+)$')     # a fighter's or a generic prefix and the stem
MAX_NAME = 64                        # longer strings are no move names (Tekken 8's longest has 30-odd characters)


# ---------------------------------------------------------------------------------------------------- candidates
def harvest(movesets):
    """(move names, animation names) of movesets (TTT2's, Tekken 7's: anything with move_name / anim_name) as two
    sets of bytes."""
    moves, anims = set(), set()
    for m in movesets:
        for i in range(len(m.tables['moves'])):
            for out, s in ((moves, m.move_name(i)), (anims, m.anim_name(i))):
                if s and len(s) <= MAX_NAME:
                    out.add(s.encode('latin1', 'replace'))
    return moves, anims


def ttt2_movesets(archives):
    """Every moveset of the installed TTT2 (the data006 rows: one per motion row), read (ttt2/motbin.py)."""
    from ..ttt2 import motbin as ttt2_motbin
    out = []
    for row in range(len(archives.indices['data006'])):
        d = archives.entry('data006', row)
        if d[4:8] == b'COM\0':
            out.append(ttt2_motbin.read(d))
    return out


def prefixed(names, prefixes):
    """Each name with its prefix ('He_', 'Co_') replaced by each of prefixes, and each name behind them."""
    out = set()
    for s in names:
        g = PREFIX_RE.match(s)
        for p in prefixes:
            out.add(p + s)
            if g:
                out.add(p + g.group(2))
    return out


def marks(names, count=MARKS_HARVESTED):
    """MARKS and the most common last tokens of names (bytes)."""
    c = collections.Counter(g.group() for g in map(MARK_RE.search, names) if g)
    return list(dict.fromkeys([x.encode() for x in MARKS] + [t for t, _ in c.most_common(count)]))


def commands(prefix, extra_marks=()):
    """'<prefix>' + directions + 1..PRESSES buttons + a mark: the fighter's own commands in numpad notation."""
    presses, level = [b''], [b'']
    for _ in range(PRESSES):
        level = [a + b.encode() for a in level for b in BUTTONS]
        presses += level
    presses = presses[1:]
    out = set()
    for d in DIRECTIONS:
        head = prefix + d.encode()
        for p in presses:
            hp = head + p
            for k in extra_marks:
                out.add(hp + k)
    return out


def variations(names, prefix, extra_marks=()):
    """Variations of names (bytes): numbers counted through, a character appended, dropped, changed or (short
    names) inserted, letters swapped (left / right, front / back ...), a button changed, removed or added, a mark
    added; the fighter's own commands (prefix) also get a command added."""
    out = set()
    tails = [s.encode() + d.encode() + b.encode() for s in SEPARATORS for d in DIRECTIONS for b in BUTTONS]
    for s in names:
        for g in NUMBER_RE.finditer(s):
            w = g.end() - g.start()
            for v in range(100 if w <= 2 else 1000):
                out.add(s[:g.start()] + (b'%0*d' % (w, v)) + s[g.end():])
        for c in CHARS:
            ch = bytes((c,))
            out.add(s + ch)
            out.add(s[:-1] + ch)
        out.add(s[:-1])
        if len(s) <= INSERT_UP_TO:
            for k in range(len(s) + 1):
                for c in CHARS:
                    out.add(s[:k] + bytes((c,)) + s[k:])
        for a, b in SWAPS:
            k = s.find(a)
            while k >= 0:
                out.add(s[:k] + b + s[k + 1:])
                k = s.find(a, k + 1)
        for g in BUTTON_RE.finditer(s):
            for t in BUTTONS + ['']:
                t = t.encode()
                out.add(s[:g.start()] + t + s[g.end():])
                out.add(s[:g.end()] + t + s[g.end():])
        for k in extra_marks:
            out.add(s + k)
        if s.startswith(prefix):
            for t in tails:
                out.add(s + t)
    return out


def counted(names, lengths):
    """Every number in names (bytes) counted through, one number at a time (Tekken 7's 'sDm_ha37B' -> Tekken 8's
    'sDm_ha35B'), and each name with '_' added or its last character dropped -> {length: [bytes]} of the lengths
    asked for (the dictionary is big: only the cheapest variations)."""
    digits = {w: [b'%0*d' % (w, v) for v in range(10 ** min(w, 3))] for w in range(1, 6)}
    wider = [b'%d' % v for v in range(10, 100)]                 # a single digit becoming two
    groups, seen = collections.defaultdict(list), set()
    for s in names:
        for t in (s + b'_', s[:-1]):
            if len(t) in lengths:
                groups[len(t)].append(t)
        for g in NUMBER_RE.finditer(s):
            pre, w, suf = s[:g.start()], g.end() - g.start(), s[g.end():]
            if w > 5 or (pre, w, suf) in seen:
                continue
            seen.add((pre, w, suf))
            n = len(pre) + w + len(suf)
            if n in lengths:
                groups[n] += [pre + d + suf for d in digits[w]]
            if w == 1 and n + 1 in lengths:
                groups[n + 1] += [pre + d + suf for d in wider]
    return groups


# ---------------------------------------------------------------------------------------------------- checking
class Keys:
    """The keys of a moveset's moves still unnamed, by name length: check(candidates) names those all three keys
    agree on."""

    def __init__(self, m):
        self.m = m
        self.code = m.code.upper().encode('latin1') + b'_'
        self.names, self.anim_names = dict(m.names), dict(m.anim_names)
        self.by_len, self.anim_by_len = collections.defaultdict(dict), collections.defaultdict(dict)
        for i, mv in enumerate(m.tables['moves']):
            n, a = m.name_lengths(i)
            if n and i not in self.names:
                self.by_len[n].setdefault(mv['name_key'], []).append(i)
            if a and i not in self.anim_names:
                self.anim_by_len[a].setdefault(mv['anim_key'], []).append(i)
        self.arrays = {n: np.array(sorted(d), np.uint32) for n, d in self.by_len.items()}
        self.anim_arrays = {n: np.array(sorted(d), np.uint32) for n, d in self.anim_by_len.items()}

    @staticmethod
    def _hits(cands, by_len, arrays):
        """(candidate, its key) of the candidates (bytes, or {length: [bytes]}) whose length and name key some move
        has."""
        if isinstance(cands, dict):
            groups = cands
        else:
            groups = collections.defaultdict(list)
            for s in cands:
                if len(s) in arrays:
                    groups[len(s)].append(s)
        for n, ss in groups.items():
            if n not in arrays or not ss:
                continue
            h = city32_rows(np.frombuffer(b''.join(ss), np.uint8).reshape(len(ss), n))
            for j in np.nonzero(np.isin(h, arrays[n]))[0]:
                yield ss[j], int(h[j])

    def lengths(self):
        """The name lengths some unnamed move has."""
        return set(self.arrays)

    def check(self, cands):
        """Name the moves candidates (bytes, or {length: [bytes]}) fit -> the names found ([bytes])."""
        found = []
        moves = self.m.tables['moves']
        for s, h in self._hits(cands, self.by_len, self.arrays):
            for i in self.by_len[len(s)][h]:
                if i not in self.names and moves[i]['move_key'] == city32(self.code + s):
                    self.names[i] = s.decode('latin1')
                    found.append(s)
        return found

    def check_anims(self, cands):
        """Name the animations candidates fit (key and length) -> how many moves got an animation name."""
        n = 0
        for s, h in self._hits(cands, self.anim_by_len, self.anim_arrays):
            for i in self.anim_by_len[len(s)][h]:
                if i not in self.anim_names:
                    self.anim_names[i] = s.decode('latin1')
                    n += 1
        return n


def name_moves(m, ttt2, tekken7=(), rounds=ROUNDS, log=None):
    """Name a Tekken 8 moveset's moves (m: motbin.read) from the installed TTT2's movesets (ttt2: ttt2_movesets) and,
    when given, Tekken 7's (tekken7: tkmvst.read of the player's .tkmvst files); sets m's names (set_names) ->
    {'dictionary', 'prefix', 'commands', 'numbers', 'variations': moves each step named, 'named': all, 'moves': how
    many, 'anims': moves whose animation got a name}."""
    keys = Keys(m)
    names, anims = harvest(list(ttt2) + list(tekken7))
    own = m.own_prefix.encode('latin1') + b'_'
    lower = own.lower()
    extra = marks(names)
    stats = collections.OrderedDict()
    found = keys.check(names)
    stats['dictionary'] = len(found)
    found += keys.check(prefixed(names, [own, lower]))
    stats['prefix'] = len(found) - stats['dictionary']
    n = len(found)
    found += keys.check(commands(own, extra))
    stats['commands'] = len(found) - n
    n = len(found)
    found += keys.check(counted(names, keys.lengths()))
    stats['numbers'] = len(found) - n
    n = len(found)
    frontier = list(keys.names[i].encode('latin1') for i in keys.names)
    for _ in range(rounds):
        frontier = keys.check(variations(frontier, own, extra))
        if not frontier:
            break
    stats['variations'] = len(keys.names) - len(m.names) - n
    stats['anims'] = keys.check_anims(names | anims)
    m.set_names(keys.names, keys.anim_names)
    stats['named'], stats['moves'] = len(m.names), len(m.tables['moves'])
    if log:
        log('Tekken 8 move names: %d of %d moves (%s)' % (stats['named'], stats['moves'], ', '.join(
            '%s %d' % (k, stats[k]) for k in ('dictionary', 'prefix', 'commands', 'numbers', 'variations'))))
    return stats


def name_known(m, names):
    """Name a moveset's moves from known names alone (names: bytes, such as harvest's move names of TTT2's
    movesets), step 1 of name_moves: what the id maps need of another fighter's moveset (its moves the TTT2
    movesets name too; a fifth of name_moves' time) -> how many it named."""
    keys = Keys(m)
    found = keys.check(names)
    m.set_names(keys.names, keys.anim_names)
    return len(found)
