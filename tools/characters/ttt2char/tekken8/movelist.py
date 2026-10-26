"""A Tekken 8 fighter's command list (its saved `<code>.mvl`, MVLT) -> a TTT2 command list (`<code>.mvl`).

Tekken 8's MVLT as its reader hands it over (autodump.py; little-endian, the file form: version 5, sub-version
2..6, which the game turns into Tekken 7's version 1000 when it loads it) has Tekken 7's layout (convert/movelist.py)
with the texts as keys into the game's string tables:
    header {"MVLT", u16 5, u16 sub-version, u32 entries, u32 demos, u32 string block, u32 entries offset, u32 demos
        offset, u32 inputs offset}; sub-version 6 adds u32 groups and u32 records offsets (the drills' moves), u32 0
    entry 372 bytes: 16 x u32 string offsets from the string block: [0] the name's text key
        (TEXT_000_MOVELIST_NAME_ZBR_026; '' none), [1] the command's (a title line's: its text), [2] the reading's,
        [3] the remarks', [4..11] the command's again, [13] [14] the developers' Japanese name and command, [12] and
        [15] unused (not always valid offsets); u16 first demo @0x44 (0xFFFF none), u16 demo count, u16 kind @0x48
        (0 move, 8 title line, 10 sample combo, 14 key move, 15 punishment drill, 16 Heat tips, 17..21 Tekken 8's
        other practice data), u16 demo kind (1 most moves, 0 sample combos, counter hits, side throws: kept, TTT2
        has both); u32 icons @0x14C (Tekken 7's: byte 0 power crush, byte 1 the hit that tornados (Tekken 7: screws),
        byte 3 another hit number), u32 @0x150 (byte 0 the hit that engages Heat, byte 1 a combo's damage)
    demo 24 bytes: 7 x u16 setup (opponent action, distance, angle, own state, the opponent's delay, back turned,
        0), u16 inputs, u32 first input, u16 needs Rage, u16 needs Heat (0x100; 0x200 / 0x300 other Tekken 8 states)
    input 4 bytes {direction, buttons, frames, glyphs lit} (Tekken 7's); a demo ends one frame after its last press:
        Tekken 8 waits for the moves to end, TTT2 plays the inputs and starts again, so a wait is added (TAIL)
The texts are in the string tables Polaris/Content/Localize/<language>/GTB_Movelist.uasset and the updates'
GTB_Upd_<nnn>_<part>.uasset (the keys they add; a later one wins), each a GryphonTextBinaryAsset: property DataSize,
then (after the object's GUID flag) a block of DataSize bytes: "gbtd", u32 header size (0x40), ..., then records
{"text", u32 16 (the size of the rest of the record header), u32 key size, u32 text size, u32 key hash, u32, the key
(ASCII, NUL-padded to 4), the text (UTF-8, NUL-padded to 4)} to the end. A command's glyphs are tags:
<img id="cmd_NN"/> 03..10 the directions d/b d d/f b f u/b u u/f, 11..18 the same held, 20..34 the buttons (19 +
the mask 1 2 4 8 of 1 2 3 4), 35 neutral; {cmd_01} {cmd_02} the brackets of a quick input, {cmd_38} the arrow
between a combo's parts; {gui_bank0_heat}, {gui_bank0_rage} and {gui_rb} buttons of Tekken 8's own controls.
TTT2 has the same glyphs (U+E000 + 0..15 the directions, U+E014 + mask the buttons, U+E063 the arrow, written
without the spaces around it) but writes neutral as a star (Tekken 7: U+E034).

The texts in TTT2's command languages are Tekken 8's own (a language without one gets the English), the names in
Japanese and English and the reading in kana; demos are pad inputs played through the fighter's own moveset.
Left out: what TTT2 has no counterpart for: the drills, key moves, Heat tips and other practice data (kinds 14 to
21) and all after the first of them (the game modes' lists: Arcade Quest's notes, Tekken Ball's moves, as moves
without demos), the Heat Moves and Rage Moves sections, entries whose demo needs Heat or Rage or whose text uses
Heat or Rage buttons (2+3 is Heat Burst or Heat Smash in Tekken 8), entries without text or with glyphs not known
here, and title lines left empty. Tornados are bounds in the converted moveset; the tornado hit becomes TTT2's
bound icon. The definition's own bounds (MOVESET['bounds']) set or clear it: an entry's first demo walked through
the converted moveset gives the press that reaches such a move (bound_hit).

Written for this project (no third-party code).
"""
import re
import struct

from ..convert.movelist import ARROW, KIND_TITLE, drop_empty_titles, summary, title_strings, write
from . import uprops

ENTRY_SIZE, DEMO_SIZE, INPUT_SIZE = 372, 24, 4
NONE = 0xFFFF
SUB_VERSIONS = range(2, 7)                       # the game's own check
KIND_MOVE, KIND_COMBO, KIND_KEY_MOVE, KIND_DRILL = 0, 10, 14, 15
KEPT_KINDS = (KIND_MOVE, KIND_TITLE, KIND_COMBO)
# Tekken 8's languages for TTT2's command languages (jp en fr it de es ru ko zh: simplified Chinese)
LANGUAGES = ['ja', 'en', 'fr', 'it', 'de', 'es', 'ru', 'ko', 'zh-CN']
ENGLISH = 'en'
TABLES = 'Polaris/Content/Localize/%s/'
TABLE_NAMES = ('GTB_Movelist.', 'GTB_Upd_')      # the command lists' tables and the updates' (all their parts)
# the sections of Tekken 8's own systems (common to every fighter): Heat Moves (the Heat Engagers, also listed with
# the fighter's other moves, and moves during Heat), Rage Moves
SYSTEM_SECTIONS = ('TEXT_000_MOVELIST_INDEX_CMN_000', 'TEXT_000_MOVELIST_INDEX_CMN_001')
LONG_SECTIONS = ('TEXT_000_MOVELIST_INDEX_CMN_007', 'TEXT_000_MOVELIST_INDEX_CMN_008')     # Throws, Attack Reversal
HEAT_BUTTON = 25                                 # cmd_25, 2+3: Heat Burst / Heat Smash
NEUTRAL = '☆'                                    # TTT2's neutral (Tekken 7's U+E034 is not in TTT2's lists)
BRACKETS = {'cmd_01': '【', 'cmd_02': '】'}      # a quick input's
COMBO_ARROW = 'cmd_38'
TAG = re.compile(r'<img id="cmd_(\d+)"/>|\{(\w+)\}')
# Tekken 8's demo opponent actions -> TTT2's (0 none, 3 guards, 5 lies down, 7 attacks: counter hit, 9 punches,
# 10 attacks high or mid, 13 attacks low); another is not known here: the opponent stands
OPPONENT_ACTION = {0: 0, 3: 3, 5: 5, 7: 7, 8: 9, 10: 10, 13: 13}
# frames waited after a demo's last input (TTT2's own demos wait 80 to 135 after a move, 140 to 250 after a throw);
# the long wait after a throw or reversal (LONG_SECTIONS, a throw's buttons last) or when the opponent acts
TAIL, LONG_TAIL = 120, 200
THROWS = (0xC0, 0x30)                            # input buttons 1+3, 2+4 (1 0x80, 2 0x10, 3 0x40, 4 0x20)
# a demo input's stick (0x10 u, 0x20 f, 0x40 d, 0x80 b) and buttons as a cancel row's direction and press bits (the
# definition's bounds: bound_hit); the glyphs of the buttons (cmd_20..34)
DEMO_STICK = {0: 0x20, 0x20: 0x40, 0x80: 0x10, 0x40: 0x4, 0x10: 0x100, 0x60: 0x8, 0xC0: 0x2, 0x30: 0x200, 0x90: 0x80}
DEMO_BUTTONS = {0x80: 1, 0x10: 2, 0x40: 4, 0x20: 8}
BUTTON_GLYPHS = range(20, 35)


class LeftOut(Exception):
    """An entry TTT2 cannot show (args[0]: why, a key of convert's counts)."""


# ---------------------------------------------------------------------------------------------------- the MVLT
def _cstr(m, o):
    end = m.find(b'\0', o)
    if o >= len(m) or end < 0:
        raise ValueError('a string offset past the command list')
    return m[o:end].decode('utf-8')


def read(m):
    """-> (entries, demos, inputs) of a Tekken 8 MVLT (its file form): entries {keys [name, command, reading]
    (text keys, '' none), demo, count, kind, demo_kind, icons}, demos {setup [7], inputs, first, rage, state},
    inputs the bytes from the inputs offset."""
    if len(m) < 32:
        raise ValueError('not a Tekken 8 command list (%d bytes)' % len(m))
    magic, version, sub, n, ndemos, so, eo, do, io = struct.unpack_from('<4sHHIIIIII', m, 0)
    if magic != b'MVLT' or version != 5 or sub not in SUB_VERSIONS:
        raise ValueError('not a Tekken 8 command list (MVLT 5, sub-version 2 to 6)')
    if eo + ENTRY_SIZE * n > len(m) or do + DEMO_SIZE * ndemos > len(m) or io > len(m):
        raise ValueError('a Tekken 8 command list cut short (%d bytes)' % len(m))
    entries = []
    for i in range(n):
        b = eo + ENTRY_SIZE * i
        offsets = struct.unpack_from('<3I', m, b)
        demo, count, kind, demo_kind = struct.unpack_from('<HHHH', m, b + 0x44)
        entries.append(dict(keys=[_cstr(m, so + o) if o != 0xFFFFFFFF else '' for o in offsets], demo=demo,
                            count=count, kind=kind, demo_kind=demo_kind,
                            icons=struct.unpack_from('<I', m, b + 0x14C)[0]))
    demos = []
    for i in range(ndemos):
        r = struct.unpack_from('<8HIHH', m, do + DEMO_SIZE * i)
        demos.append(dict(setup=list(r[:7]), inputs=r[7], first=r[8], rage=r[9], state=r[10]))
    return entries, demos, m[io:]


# ---------------------------------------------------------------------------------------------------- texts
def text_records(block, keys=None):
    """{key: text} of a string table's 'gbtd' block (only `keys` when given)."""
    if block[:4] != b'gbtd' or len(block) < 8:
        raise ValueError('not a text block (%r)' % bytes(block[:4]))
    p = struct.unpack_from('<I', block, 4)[0]
    out = {}
    while p + 16 <= len(block):
        tag, rest, key_size, text_size = struct.unpack_from('<4sIII', block, p)
        start = p + 8 + rest
        if tag != b'text' or rest < 8 or start + key_size + text_size > len(block):
            raise ValueError('a bad text record at %#x' % p)
        key = bytes(block[start:start + key_size]).split(b'\0')[0].decode('ascii')
        if keys is None or key in keys:
            out[key] = bytes(block[start + key_size:start + key_size + text_size]).split(b'\0')[0].decode('utf-8')
        p = start + key_size + text_size
    return out


def table(pkg, keys=None):
    """{key: text} of a GryphonTextBinaryAsset package (only `keys` when given)."""
    e = pkg.main_export()
    props, at = uprops.read_object(pkg, e)
    size = props.get('DataSize')
    if not isinstance(size, int) or at + size > e.size:
        raise ValueError('%s: no text block' % pkg.name)
    return text_records(memoryview(e.data)[at:at + size], keys)


def texts(store, keys, log=print):
    """{language: {key: text}} of the text keys asked for, from the game's command list tables (LANGUAGES; a
    language without them is left out, a table that cannot be read is logged and skipped)."""
    out = {}
    for lang in LANGUAGES:
        names = [p for p in store.find(TABLES % lang)
                 if p.rsplit('/', 1)[-1].startswith(TABLE_NAMES) and p.lower().endswith('.uasset')]
        names.sort(key=lambda p: (not p.rsplit('/', 1)[-1].startswith(TABLE_NAMES[0]), p.lower()))
        t = {}
        for p in names:
            try:
                t.update(table(store.package(p), keys))
            except (KeyError, ValueError, UnicodeDecodeError) as e:
                log('command list: %s left out (%s)' % (p, e))
        if t:
            out[lang] = t
    return out


def glyph(n):
    """TTT2's glyph of Tekken 8's command tag cmd_<n>, or None (none known)."""
    if 3 <= n <= 18:
        return chr(0xE000 + n - 3)                   # d/b d d/f b f u/b u u/f, then the same held
    if 20 <= n <= 34:
        return chr(0xE014 + n - 19)                  # the buttons by mask
    return NEUTRAL if n == 35 else None


def text(t):
    """A Tekken 8 text (a name, a command, a title line) -> TTT2's (its glyphs); LeftOut when TTT2 cannot show it."""
    def one(m):
        if m.group(1) is not None:
            n = int(m.group(1))
            if n == HEAT_BUTTON:
                raise LeftOut('need Heat or Rage')
            g = glyph(n)
            if g is None:
                raise LeftOut('unknown glyphs')
            return g
        name = m.group(2)
        if name.startswith('gui_'):
            raise LeftOut('need Heat or Rage')
        if name == COMBO_ARROW:
            return ARROW
        if name in BRACKETS:
            return BRACKETS[name]
        raise LeftOut('unknown glyphs')
    return TAG.sub(one, t).replace(' ' + ARROW + ' ', ARROW)


def _english(tables, key):
    """A text key's English text for TTT2; LeftOut when there is none or TTT2 cannot show it."""
    en = tables.get(ENGLISH, {}).get(key) if key else None
    if not en:
        raise LeftOut('no text')
    return text(en)


def _or(t, fallback):
    """A language's text for TTT2, else (none, or TTT2 cannot show it) the fallback."""
    try:
        return text(t) if t else fallback
    except LeftOut:
        return fallback


def _strings(x, tables):
    """An entry's 12 TTT2 strings ([0] jp name, [1] en name, [2] reading, [3..11] the command by language);
    LeftOut when TTT2 cannot show it."""
    name, command, reading = x['keys']
    english = _english(tables, command)
    commands = [_or(tables.get(lang, {}).get(command), english) for lang in LANGUAGES]
    if x['kind'] == KIND_TITLE:
        return title_strings(commands)
    en = _english(tables, name)
    ja = tables.get('ja', {})
    jp = _or(ja.get(name), en)
    return [jp, en, _or(ja.get(reading), jp)] + commands


# ---------------------------------------------------------------------------------------------------- bound icons
def demo_presses(records):
    """[(stick, buttons, frame)] of a demo's presses (a cancel row's direction and press bits, the frame from 0);
    None when the stick moves without a press (a dash or a motion input: not walked)."""
    out, held, frame = [], 0, 0
    for direction, buttons, frames, _ in records:
        new = buttons & ~held
        if new:
            out.append((DEMO_STICK.get(direction & 0xF0, 0),
                        sum(bit for demo, bit in DEMO_BUTTONS.items() if new & demo), frame))
        elif direction:
            return None
        held = buttons
        frame += max(1, frames)
    return out


def command_presses(command):
    """How many presses a command shows: its button glyphs, less the ones in brackets (a stance's way in: "During
    Sentai ([07][23], etc.) [23]")."""
    return sum(1 for m in TAG.finditer(re.sub(r'\([^)]*\)', '', command or ''))
               if m.group(1) and int(m.group(1)) in BUTTON_GLYPHS)


def bound_hit(tornado, bounds, presses, command):
    """The hit TTT2's bound icon names: Tekken 8's tornado hit, unless the definition's bounds say otherwise.
    bounds(presses) -> {press number: bound} for the presses that reach a move the definition makes a bound or not
    (move_overrides.command_bounds); the presses of the demo before the command's own (a stance's way in) are not
    counted. A tornado hit made no bound loses the icon; without one, the first press made a bound gets it."""
    if not presses:
        return tornado
    before = len(presses) - command_presses(command)
    if before < 0:
        return tornado
    marks = {n - before: bound for n, bound in bounds(presses).items() if n > before}
    if marks.get(tornado) is False:
        tornado = 0
    return tornado or min((n for n, bound in marks.items() if bound), default=0)


# ---------------------------------------------------------------------------------------------------- converting
def convert(mvl, store, log=print, texts_by_language=None, bounds=None):
    """The TTT2 command list (MVLT bytes) of a Tekken 8 command list `mvl` (its saved bytes), its texts read from
    the store (or given: {language: {key: text}}); None when there is none to make. bounds: the definition's bound
    moves for the bound icons (bound_hit; move_overrides.command_bounds), None: Tekken 8's tornados only."""
    try:
        entries, demos, inputs = read(mvl or b'')
    except ValueError as e:
        log('command list: %s: none made' % e)
        return None
    tables = texts_by_language
    if tables is None:
        tables = texts(store, {k for x in entries for k in x['keys'] if k}, log)
    if ENGLISH not in tables:
        log('command list: Tekken 8\'s English texts are missing: none made')
        return None
    out, out_demos, out_inputs = [], [], []
    dropped = {'drills': 0, 'Tekken 8 practice data': 0, 'in the Heat and Rage sections': 0, 'need Heat or Rage': 0,
               'no text': 0, 'unknown glyphs': 0, 'broken demos': 0, 'empty title lines': 0}
    standing = 0
    section = long_section = practice = False       # in a section of Tekken 8's own systems / of throws; past
    for x in entries:                                # the command list (practice data from its first entry on)
        if x['kind'] == KIND_TITLE:
            section, long_section = x['keys'][1] in SYSTEM_SECTIONS, x['keys'][1] in LONG_SECTIONS
        practice = practice or x['kind'] not in KEPT_KINDS
        if practice:
            dropped['drills' if x['kind'] in (KIND_KEY_MOVE, KIND_DRILL) else 'Tekken 8 practice data'] += 1
            continue
        if section:
            dropped['in the Heat and Rage sections'] += 1
            continue
        own = [demos[x['demo'] + k] for k in range(x['count'])] \
            if x['demo'] != NONE and x['demo'] + x['count'] <= len(demos) else []
        rows = [[inputs[INPUT_SIZE * (d['first'] + k):INPUT_SIZE * (d['first'] + k + 1)] for k in range(d['inputs'])]
                for d in own]
        try:
            if (x['demo'] != NONE and len(own) != x['count']) or any(len(r) != INPUT_SIZE for rs in rows for r in rs):
                raise LeftOut('broken demos')
            if any(d['rage'] or d['state'] for d in own):
                raise LeftOut('need Heat or Rage')
            strings = _strings(x, tables)
        except LeftOut as e:
            dropped[e.args[0]] += 1
            continue
        first = len(out_demos) if own else NONE
        for d, rs in zip(own, rows):
            setup = list(d['setup'])
            action = OPPONENT_ACTION.get(setup[0])
            if action is None:
                standing += 1
                setup[0] = setup[4] = 0
            else:
                setup[0] = action
            presses = [r for r in rs if r[1]]
            wait = LONG_TAIL if long_section or setup[0] or (presses and presses[-1][1] in THROWS) else TAIL
            converted = [bytes([r[1], r[0], r[2], r[3]]) for r in rs]
            while wait > 0:
                converted.append(bytes([0, 0, min(wait, 255), 0]))
                wait -= 255
            out_demos.append((setup, len(converted), len(out_inputs)))
            out_inputs.extend(converted)
        tornado = (x['icons'] >> 8) & 0xFF
        if bounds is not None and own and x['kind'] == KIND_MOVE:
            tornado = bound_hit(tornado, bounds, demo_presses(rows[0]), tables[ENGLISH].get(x['keys'][1]))
        out.append(dict(strings=strings, demo=first, count=len(own), kind=x['kind'], demo_kind=x['demo_kind'],
                        icons=(0, tornado << 8)))
    kept, dropped['empty title lines'] = drop_empty_titles(out)
    if not any(x['kind'] != KIND_TITLE for x in kept):
        log('command list: nothing TTT2 can show: none made')
        return None
    log(summary(kept, out_demos, dropped))
    if standing:
        log('command list: %d demos\' opponent actions are not known here: the opponent stands' % standing)
    return write(kept, out_demos, out_inputs)
