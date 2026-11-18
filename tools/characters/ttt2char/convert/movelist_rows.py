"""A command list (TTT2's MVLT, `<code>.mvl`: the practice mode's list) made from a fighter's converted moveset, for a
fighter whose game has no command list of its own (Tekken 8's Azazel: autodump.NO_COMMAND_LIST).

The definition's COMMANDS lists what the list shows, in order: a move (named as MOVESET names them: its name, or its
name key 'key:<8 hex digits>' for a Tekken 8 move) with the name we give it, or a plain string, a title line. The
names are the definition's own words; the inputs and the demos are not written anywhere: they are walked out of the
converted moveset's input rows, so a later change of a move's input shows in the list.

    COMMANDS = ['Strikes', ('key:0a1b2c3d', 'Claw'), ('key:4e5f6a7b', 'Claw Combo'), ...]
    (an entry may add options: ('key:...', 'Long Warp', {'distance': 7000}): the demo's distance in mm)

The walk (paths): from the stance (alias 1) the fewest presses that reach the move. A press is a cancel row of the
current move (its groups inline) with buttons (a direction too, or any), a dash row (0x8001 f,f / 0x8002 b,b, the
moves they start take the next press) or an input-sequence row (0x800D + k: its inputs); automatic rows (no input,
requirements that always hold) are followed for free (a string's part the game goes on to by itself). A press is taken
by the first row of the list that fits it (direction, buttons, window), as in the game: a row whose requirements
always hold in the demo (ALWAYS, the player's own rows of TTT2's CPU test, a distance test that holds at the demo's
distance) takes it before the row walked, any other row is taken to be situational and passes it on. The row walked
may itself have requirements the walk does not know (the attack connected, ...: logged); it is never one that is false
in Practice (a CPU row, an item worn, a distance test failing at the demo's distance). Of the presses that take a row
the list shows the plainest: neutral, then f b d, d/f d/b, u, u/f, u/b; fewer buttons.

The command text is TTT2's glyphs (convert/movelist.py's: U+E000 + 0..7 the directions d/b d d/f b f u/b u u/f, + 8 the
same held, U+E014 + mask the buttons), the same in every language (no words: nothing to translate); a dash's second
tap is shown held (f,F+2) when the press goes on holding it, as TTT2's own lists show it. The names stand in all
three name strings (Japanese, English, the reading). The demo plays the presses as TTT2's own demos do (one frame each,
the direction with the buttons, a dash as f, neutral, f), each follow-up at frame GAP of its move (or its window),
then waits for the last move to end (its list's end row; the moves its automatic rows go on to too: a throw's
connected part), at least TAIL frames (a throw LONG_TAIL), MOST at most. The demo stands DISTANCE apart, a throw (a
move with a row for the throw connecting) THROW_DISTANCE, or the entry's own distance option. Bound icons: an entry whose presses are
all plain ones is walked by convert/movelist.bound_hit like the converted lists.

Written for this project (no third-party code).
"""
import heapq

from . import idmaps as M
from . import tagsystem as TS
from .movelist import KIND_MOVE, KIND_TITLE, bound_hit, drop_empty_titles, summary, title_strings, write

STANDING = 0x8001                       # the stance's alias slot
DASH_FORWARD, DASH_BACK = 0x8001, 0x8002
SEQ0 = 0x800D                           # a cancel direction from here on names input sequence (direction - SEQ0)
PRESS_BITS, ANY_OF, RELEASE = 0x1FF, 0x20000000, 0x80000000
HELD_BITS = 0x1FF << 9                  # buttons a row needs held (not walked)
TAG = 0x100                             # the tag button (not in a command list)
ALWAYS = 0
CPU = 214                               # TTT2's "CPU-controlled" test: param 0 = a player's row (Tekken 8's 228)
NEAR, FAR = 35, 36                      # the opponent at most / at least param mm away
ITEM = 459                              # an item worn (an added fighter wears none)
NEUTRAL = 0x20
# a cancel row's stick bits in the order the list prefers them (neutral first: no glyph)
STICKS = [NEUTRAL, 0x40, 0x10, 0x4, 0x8, 0x2, 0x100, 0x200, 0x80]
GLYPH = {0x2: 0, 0x4: 1, 0x8: 2, 0x10: 3, 0x40: 4, 0x80: 5, 0x100: 6, 0x200: 7}       # U+E000 + n, + 8 held
HELD_GLYPH = 8
DEMO_STICK = {NEUTRAL: 0, 0x40: 0x20, 0x10: 0x80, 0x4: 0x40, 0x100: 0x10, 0x8: 0x60, 0x2: 0xC0, 0x200: 0x30,
              0x80: 0x90}               # a stick bit -> the demo input's (convert/movelist.DEMO_STICK the other way)
DEMO_BUTTON = {1: 0x80, 2: 0x10, 4: 0x40, 8: 0x20}
THROWS = (5, 10)                        # 1+3, 2+4 (the long wait)
DISTANCE = 2000                         # the demo's distance (TTT2's own demos 1500 to 3000)
THROW_CONTACT = frozenset(range(3, 10))  # a row's "the throw connected from a side, within param mm": a throw
THROW_DISTANCE = 1000                   # a throw's demo distance: close (big bodies stop where they touch: 1.6 m)
GAP = 7                                 # a follow-up's press frame (TTT2's converted demos: a press, 5 neutral)
TAIL, LONG_TAIL, MOST = 120, 200, 600   # frames waited after the last press (at least / a throw / at most)
END = 30                                # ... and after the last move's end
NONE = 0xFFFF                           # an entry without a demo
FRAMES = 255                            # a demo input's frames at most


def _button_glyph(buttons):
    return chr(0xE014 + buttons)


def _stick_glyph(stick, held=False):
    return chr(0xE000 + GLYPH[stick] + (HELD_GLYPH if held else 0))


class Walk:
    """The input rows of a converted moveset (tables, aliases as movesets.py reads them) as the walk sees them."""

    def __init__(self, tables, aliases, distance=DISTANCE):
        self.T, self.aliases, self.distance = tables, aliases, distance

    def rows(self, i):
        for r in TS.cancels(self.T, self.T['moves'][i]['cancel']):
            if r['direction'] == M.GROUP:
                yield from TS.chain(self.T['group_cancels'], r['move_id'], lambda g: g['direction'] == M.GROUP_END)
            elif r['direction'] != M.LIST_END:
                yield r

    def throw(self, move):
        """Whether the move is a throw: a row of it goes on when the throw connected (THROW_CONTACT)."""
        return any(c in THROW_CONTACT for r in self.rows(move) for c, _ in TS.reqs(self.T, r['req']))

    def target(self, r):
        t = TS.resolve(self.aliases, r['move_id'])
        return t if t < len(self.T['moves']) else None

    def _truth(self, condition, param):
        """True / False when the walk knows the requirement in Practice's demo, else None."""
        if condition == ALWAYS:
            return True
        if condition == CPU:
            return param == 0
        if condition == NEAR:
            return self.distance <= param
        if condition == FAR:
            return self.distance >= param
        if condition == ITEM:
            return False
        return None

    def holds(self, r):
        """Every requirement of the row always holds in the demo (it takes a press before the row walked)."""
        return all(self._truth(c, p) is True for c, p in TS.reqs(self.T, r['req']))

    def possible(self, r):
        """(no requirement of the row is false in the demo: it can be walked, the requirements the walk does not
        know)."""
        truths = [(c, self._truth(c, p)) for c, p in TS.reqs(self.T, r['req'])]
        return all(t is not False for _, t in truths), [c for c, t in truths if t is None]

    # ------------------------------------------------------------------------------------------------ steps
    @staticmethod
    def kind(r):
        """'press', 'dash', 'sequence', 'auto' or None (a row the walk does not take: direction only, held buttons,
        the tag button, a release)."""
        d, b = r['direction'], r['button']
        if d in (DASH_FORWARD, DASH_BACK):
            return 'dash' if not b else None
        if d >= SEQ0 and d not in (M.GROUP, M.GROUP_END):
            return 'sequence' if not b else None
        if d >= M.LIST_END:
            return None
        if not b:
            return 'auto' if not d else None
        if b & (RELEASE | HELD_BITS) or not b & PRESS_BITS or b & TAG:
            return None
        return 'press'

    def presses(self, r):
        """The (stick, buttons) presses a press row fits, plainest first."""
        bits = r['button'] & PRESS_BITS
        buttons = [1 << k for k in range(4) if bits & (1 << k)] if r['button'] & ANY_OF else [bits]
        sticks = [s for s in STICKS if not r['direction'] or r['direction'] & s]
        return [(s, b) for b in buttons for s in sticks]

    def takes(self, r, step, frame):
        kind = self.kind(r)
        if kind is None or kind == 'auto' or not r['win_start'] <= frame <= r['win_end']:
            return False
        if step[0] != kind:
            return False
        if kind == 'press':
            stick, buttons = step[1]
            bits = r['button'] & PRESS_BITS
            return bool((not r['direction'] or r['direction'] & stick)
                        and (bits & buttons if r['button'] & ANY_OF else bits == buttons))
        return r['direction'] == step[1]

    def first(self, move, step, frame, walked):
        """The row of `move` that takes the step at that frame: `walked` when no earlier row that always holds does."""
        for r in self.rows(move):
            if r is walked:
                return True
            if self.takes(r, step, frame) and self.holds(r):
                return False
        return False

    def sequence(self, d):
        """[(stick, buttons)] of input sequence row direction d (buttons 0: a direction only)."""
        s = self.T['input_sequences'][d - SEQ0]
        out = []
        for x in self.T['inputs'][s['inputs']:s['inputs'] + s['amount']] if s['inputs'] is not None else []:
            b = x['button']
            out.append((x['direction'] & 0x3FE, 0 if b & RELEASE else b & PRESS_BITS))
        return out

    def edges(self, move, entered):
        """The steps out of a move: [(rank, target, step, frame, start, unknown)]: the step (None: an automatic row)
        made at that frame of `move`, the frame of `move` the target begins at, the requirements of the row the walk
        does not know; entered: the step that began `move` (after a dash the next press is made at once)."""
        out = []
        for r in self.rows(move):
            kind, t = self.kind(r), self.target(r)
            if kind is None or t is None:
                continue
            if kind == 'auto':
                if self.holds(r):
                    out.append(((0, 0, 0), t, None, r['win_start'], max(r['win_start'], r['start_frame']), ()))
                continue
            ok, unknown = self.possible(r)
            if not ok:
                continue
            if kind == 'press':
                steps = [('press', p) for p in self.presses(r)]
            elif kind == 'dash':
                steps = [('dash', r['direction'])]
            else:
                inputs = self.sequence(r['direction'])
                if not inputs or not inputs[-1][1] or not all(s in DEMO_STICK or not s for s, _ in inputs):
                    continue
                steps = [('sequence', r['direction'])]
            for step in steps:
                frame = self.frame(r, move, entered)
                if frame is None or not self.first(move, step, frame, r):
                    continue
                if step[0] == 'press':
                    rank = (1, STICKS.index(step[1][0]), bin(step[1][1]).count('1'))
                else:
                    rank = (2 if step[0] == 'dash' else 1, 0, 0)
                out.append((rank, t, step, frame, max(frame, r['start_frame']), tuple(unknown)))
                break
        return out

    def end(self, move, depth=4):
        """The frame a move ends at (its list's end row's, else its animation's length), or that of the moves its
        automatic rows go on to (a string's later hits, a throw's connected part), whichever is later."""
        done = [r['win_start'] for r in TS.cancels(self.T, self.T['moves'][move]['cancel'])
                if r['direction'] == M.LIST_END and r['win_start']]
        last = max(done + [self.T['moves'][move].get('anim_len') or 0])
        stances = {TS.resolve(self.aliases, a) for a in (STANDING, STANDING + 1)}
        if depth:
            for r in self.rows(move):
                t = self.target(r)
                if self.kind(r) == 'auto' and t is not None and t not in stances and t != move \
                        and self.possible(r)[0]:
                    last = max(last, max(r['win_start'], r['start_frame']) - 1 + self.end(t, depth - 1))
        return last

    def frame(self, r, move, entered):
        """The frame of `move` a step is made at (None: none fits the row's window)."""
        if move == TS.resolve(self.aliases, STANDING):
            want = 1
        elif entered is not None and entered[0] == 'dash':
            want = 2                        # (a dash's follow-up: at once, the stick still held)
        else:
            want = GAP
        frame = min(max(want, r['win_start']), r['win_end'])
        return frame if r['win_start'] <= frame <= r['win_end'] else None


def paths(walk, targets):
    """{target move: [(step, frame, start, from move, unknown requirements)]}: the fewest presses from the stance
    that reach each target (the plainest when several do); a target the walk cannot reach is left out."""
    start = TS.resolve(walk.aliases, STANDING)
    best = {start: (0, 0, 0)}
    heap = [((0, 0, 0), 0, start, None, [])]
    count = 1
    found = {}
    while heap and len(found) < len(targets):
        cost, _, move, entered, path = heapq.heappop(heap)
        if best.get(move) != cost:
            continue
        if move in targets and path and move not in found:
            found[move] = path
        for rank, t, step, frame, begin, unknown in walk.edges(move, entered):
            c = tuple(a + b for a, b in zip(cost, rank))
            if t in best and best[t] <= c:
                continue
            best[t] = c
            count += 1
            heapq.heappush(heap, (c, count, t, step if step is not None else entered,
                                  path + [(step, frame, begin, move, unknown)]))
    return found


# ------------------------------------------------------------------------------------------------ text and demo
def render(walk, path):
    """(command text, demo inputs [bytes], plain presses [(stick, buttons, demo frame)] or None (a dash or an input
    sequence on the way: no bound icon), the demo frame after the last input, the demo frame the last move began at)
    of a walked path."""
    glyphs, inputs, plain = [], [], []
    now = 0                                  # the next free demo frame
    begun = 0                                # the demo frame the current move's frame 1 is at
    ahead = [s[0] for s in path]

    def wait(n):
        while n > 0:
            inputs.append(bytes([0, 0, min(n, FRAMES), 0]))
            n -= FRAMES

    def tap(stick, buttons, lit):
        inputs.append(bytes([sum(v for b, v in DEMO_BUTTON.items() if buttons & b), DEMO_STICK[stick], 1, lit]))

    dashed = None                            # the stick of the dash just made (its second tap shown held)
    for n, (step, frame, start, _, _) in enumerate(path):
        if step is None:                     # an automatic row: the next move begins at its frame
            begun += start - 1
            continue
        at = max(begun + frame - 1, now)
        wait(at - now)
        kind = step[0]
        if kind == 'dash':
            stick = 0x40 if step[1] == DASH_FORWARD else 0x10
            following = next((s for s in ahead[n + 1:] if s is not None), None)
            held = following is not None and following[0] == 'press' and following[1][0] == stick
            glyphs += [_stick_glyph(stick), _stick_glyph(stick, held)]
            tap(stick, 0, 1)
            tap(NEUTRAL, 0, 0)
            tap(stick, 0, 1)
            last = at + 2                    # (the row is taken at the second tap)
            plain, dashed = None, (stick if held else None)
        elif kind == 'sequence':
            seq = walk.sequence(step[1])
            for stick, buttons in seq:
                stick = stick or NEUTRAL
                shown = stick != NEUTRAL
                if shown:
                    glyphs.append(_stick_glyph(stick))
                if buttons:
                    glyphs.append(_button_glyph(buttons))
                tap(stick, buttons, int(shown) + bool(buttons))
            last = at + len(seq) - 1
            plain, dashed = None, None
        else:
            stick, buttons = step[1]
            lit = 1
            if stick != NEUTRAL and stick != dashed:
                glyphs.append(_stick_glyph(stick))
                lit = 2
            glyphs.append(_button_glyph(buttons))
            tap(stick, buttons, lit)
            if plain is not None:
                plain.append((stick, buttons, at))
            last = at
            dashed = None
        now = last + 1
        begun += max(last - begun + 1, start) - 1      # (later than planned when a press had to wait)
    return ''.join(glyphs), inputs, plain, now, begun


# ------------------------------------------------------------------------------------------------ the list
def entries_of(commands, index_of, log=print):
    """The definition's COMMANDS -> [title text | (move index, name, options)]; a move the moveset does not have
    (index_of(ref) None: not found, or dropped) is logged and left out."""
    out = []
    for x in commands:
        if isinstance(x, str):
            out.append(x)
            continue
        ref, name = x[0], x[1]
        options = x[2] if len(x) > 2 else {}
        i = index_of(ref)
        if i is None:
            log('command list: %s (%s) is not in the moveset: left out' % (ref, name))
            continue
        out.append((i, name, options))
    return out


def convert(tables, aliases, entries, log=print, bounds=None):
    """The TTT2 command list (MVLT bytes) of entries (entries_of's) walked through a converted moveset (tables and
    aliases as movesets.py reads them); None when no move entry is left. bounds: the definition's bound moves for the
    bound icons (move_overrides.command_bounds; None: no icons)."""
    probe = Walk(tables, aliases)
    entries = [x if isinstance(x, str) else (x[0], x[1], dict(x[2], distance=x[2].get(
        'distance', THROW_DISTANCE if probe.throw(x[0]) else DISTANCE))) for x in entries]
    walked = {}                              # distance -> {move: path or None}
    for x in entries:
        if not isinstance(x, str):
            walked.setdefault(x[2]['distance'], {})[x[0]] = None
    walks = {}
    for distance, found in walked.items():
        walks[distance] = Walk(tables, aliases, distance)
        found.update(paths(walks[distance], set(found)))
    out, demos, all_inputs = [], [], []
    dropped = {'no input from the stance': 0, 'empty title lines': 0}
    for x in entries:
        if isinstance(x, str):
            out.append(dict(strings=title_strings([x] * 9), demo=NONE, count=0, kind=KIND_TITLE, demo_kind=0,
                            icons=(0, 0)))
            continue
        move, name, options = x
        distance = options['distance']
        path = walked[distance][move]
        if not path:
            log('command list: no input from the stance reaches %s (move %d): left out' % (name, move))
            dropped['no input from the stance'] += 1
            continue
        unknown = sorted({c for s in path for c in s[4]})
        if unknown:
            log('command list: %s: walked through rows with requirements %s (taken to hold)'
                % (name, ', '.join(map(str, unknown))))
        text, inputs, plain, now, begun = render(walks[distance], path)
        last = next(s[0] for s in reversed(path) if s[0] is not None)
        least = LONG_TAIL if probe.throw(move) or last[0] == 'press' and last[1][1] in THROWS else TAIL
        tail = min(max(begun + walks[distance].end(move) - now + END, least), MOST)
        while tail > 0:
            inputs.append(bytes([0, 0, min(tail, FRAMES), 0]))
            tail -= FRAMES
        hit = bound_hit(bounds, plain, len(plain)) if bounds is not None and plain else 0
        demos.append(([0, distance, 0, 0, 0, 0, 0], len(inputs), len(all_inputs)))
        all_inputs.extend(inputs)
        out.append(dict(strings=[name, name, name] + [text] * 9, demo=len(demos) - 1, count=1, kind=KIND_MOVE,
                        demo_kind=1, icons=(0, hit << 8)))
    kept, dropped['empty title lines'] = drop_empty_titles(out)
    if not any(x['kind'] != KIND_TITLE for x in kept):
        log('command list: no move of COMMANDS has an input: none made')
        return None
    log(summary(kept, demos, dropped))
    return write(kept, demos, all_inputs)
