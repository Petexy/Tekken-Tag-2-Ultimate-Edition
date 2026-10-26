"""Tekken 8 movesets (Binary/mothead/bin/<code>.motbin, as the game's own reader hands it over: the file form, before
the game fixes it up in memory) read into the common moveset form (movesets.py) with Tekken 7's field names and
encodings wherever the meaning is the same, so the Tekken 7 converter's evidence and rules apply. Requirement and
property ids stay in Tekken 8's numbering (Tekken 7's with insertions; the converter maps them).

    0x000 u16 0, u8 fixed (0: file form), u8, u32 version (a date), "TEK\\0" @0x08, 4 x u64 string offsets @0x10
          (the strings themselves are not shipped), u16 aliases[60] @0x30, u16 current aliases[60] @0xA8,
          u16 unknown[32] @0x120 (as Tekken 7's), u32 id range @0x160 (roster id * 0xFFFF + 1, the next fighter's),
          reactions {u64 offset @0x168, u64 name block size @0x170, u64 count @0x178}, then {u64 offset, u64 count}
          of the other 19 tables @0x180 + 0x10 k (TABLE_ORDER after 'reactions', then the pose table), 13 x u64 @0x2B0
          (0: filled at run time)
    BASE (0x318): the 20 tables back to back; a link inside a row is a row index of its table (-1: none)
    move (0x448): 32-byte protected fields @0x00 name key, 0x20 anim key, 0x58 vuln, 0x78 hit level, 0xD0 owner
          id, 0xF0 move key (their plain values come from the dump's <code>.motbin.fields.bin), u64 name, anim
          name @0x40/0x48 (offsets into the stripped name block, so their differences give the names' lengths),
          u32 anim @0x50 (index into the animation bank's per-move key list; bits 14, 15: flags), cancel lists
          @0x98 (u64), 0xA0, 0xB0, 0xC0 (with u32 counts @0xA8, 0xB8, 0xC8; 0: none), u16 transition, m_56 @0xCC,
          u64 hit conditions @0x110,
          s16 @0x118, u32 first animation frame @0x11C, u32 animation length @0x120 (0: computed at load),
          u32 airborne start, end, ground fall @0x124, u64 voice clips, extra properties, begin, end properties
          @0x130, u32 bitfield, flags, first and last active frame @0x150, 8 hit boxes of 0x30 @0x160 {u32 first,
          last frame, u8 location, location 2, u16, f32 radius, height, vec3 offsets a, b, u32}, u16 m_a8, distance
          @0x2E0, 8 frame-keyed parameter blocks of 0x2C @0x2E4 {i32 frame, i32, i32 kind, f32 x 3, u32, f32,
          u32 x 3}, u32 @0x444
    fields.bin: u32 move count, u32 move size, u32 moves table offset, then per move the six protected fields'
          plain u32 values in the order above
    tables whose rows differ from Tekken 7's: requirement 0x14 {condition, param, param2..4}, end 1100;
          extra property 0x28 {frame, u32, u64 requirement list, id, value, value2..5}, end frame 0 and id 0;
          begin / end property 0x20 {u64 requirement list, id, value, value2..5}, end id 1100; voice clip 0xC
          {channel, u32, id} (Tekken 7: one u32 channel << 24 | id), end all 0xFFFFFFFF; projectile 0xE0 (Tekken
          7's 0xA8 with words inserted @0x38, 0xA8, 0xB8, its sounds as {bank, 0, id} triples @0x50 + 12 k, links
          @0x90/0x98 with 0 = none); pose choice 0x18 {u16 kind, u16 slot, u32, u64 requirement list, u32 name key
          of the intro / win pose move, u32}; the others (reactions, hit conditions, pushbacks, cancels, input
          sequences, inputs, camera data, throw cameras) have Tekken 7's layout with u64 links (a reaction's vertical
          pushback @0x4C and its 15 moves @0x4E as Tekken 7's: the same values on 2603 same-named hit conditions)
    commands (a cancel's direction): Tekken 7's bits; specials 0x8000 list end, 0x8001 / 0x8002 dash forward /
          back, 0x8005 / 0x8006 up / down tap (Tekken 7 0x8003 / 0x8004), 0x8012 / 0x8013 group / group end (Tekken
          7 0x800B / 0x800C), 0x8014 + k input sequence k (Tekken 7 0x800D + k); Tekken 8-only 0x8003 / 0x8004 (a
          second dash forward / back), 0x8007 (side step), 0x800A / 0x800B (side walks): their rows are left out
    aliases: Tekken 8 slots 0-25 = Tekken 7's 0-25, 26-28 new, 29-56 = Tekken 7's 26-53, 57 = 54, 58 new, 59 = 55;
          a move id 0x8000 + k (Tekken 8 slot k) becomes Tekken 7's slot id, or the move itself for a new slot
    animations: a move's animation is the bank's category-0 key at the move's anim index (the fighter's own bank,
          <code>.anmbin); the key's entry holds the animation when it has data, else the common bank (com.anmbin)
          holds it for every fighter whose bit is set in the entry's 256-bit mask. Bank: u32 index size @0,
          6 x u32 entry counts @4, 6 x u32 key counts @0x1C, 6 x u64 entry lists @0x38, 6 x u64 key lists @0x68;
          entry 0x38 {u32 key, u32, u64 data offset, u64 path offset, u32 mask[8]}

Names: the file has none; a move's name, its fighter's code and the name's length are checked against the keys
(tekken8/movenames.py). Written for this project from the files themselves (no third-party code).
"""
import collections
import struct

from .. import InputError
from ..movesets import TABLE_ORDER, Moveset

BASE = 0x318
MAGIC = b'TEK\0'
MOVE_SIZE = 0x448
ALIASES = 60                       # Tekken 8's alias slots (Tekken 7: 56)
T7_ALIASES = 56
END_REQ = 1100                     # requirement / property list end (Tekken 7 881, TTT2 690)
POSES = 'poses'                    # the 20th table (intro / win pose choices), after TABLE_ORDER's 19
ORDER = TABLE_ORDER + [POSES]
HEADER_TABLES = {'reactions': (0x168, 0x178)}       # (offset field, count field); 0x170 = the name block's size
HEADER_TABLES.update({t: (0x180 + 0x10 * k, 0x188 + 0x10 * k) for k, t in enumerate(ORDER[1:])})
NAME_BLOCK = 0x170
PROTECTED = ['name_key', 'anim_key', 'vuln', 'hitlevel', 'owner_id', 'move_key']   # fields.bin order (move offset)
FIELDS_HEADER = 12

# ---------------------------------------------------------------------------------------------------- commands
LIST_END = 0x8000
GROUP, GROUP_END = 0x800B, 0x800C          # Tekken 7's group / group end (what the rows carry after reading)
SEQ0 = 0x800D                              # Tekken 7: direction SEQ0 + k = input sequence k
T8_SEQ0 = 0x8014
# Tekken 8 special -> Tekken 7's (dashes keep their codes)
COMMANDS = {0x8012: GROUP, 0x8013: GROUP_END, 0x8005: 0x8003, 0x8006: 0x8004}
# Tekken 8-only specials (their rows are left out): a second dash forward / back (the same moves as 0x8001 /
# 0x8002), a side step and the side walks; Tekken 7 and TTT2 step and walk with their own rows of the hub moves
T8_ONLY_COMMANDS = {0x8003: 'second dash forward', 0x8004: 'second dash back', 0x8007: 'side step',
                    0x800A: 'side walk', 0x800B: 'side walk'}
# Tekken 8 alias slot -> Tekken 7's (slots 26-28 and 58 are new; 57 holds what Tekken 7's 54 holds)
ALIAS_SLOTS = dict([(k, k) for k in range(26)] + [(k, k - 3) for k in range(29, 57)] + [(57, 54), (59, 55)])
# requirements whose param is a move id (Tekken 7's 0x81dc; convert/moveset.py resolves it as a move)
MOVE_PARAMS = {0x824c}

# ---------------------------------------------------------------------------------------------------- rows
# A field: (name, offset, struct code (little-endian), link): link names the table a u64 / u32 indexes (-1: none),
# 'move' a move id, None a plain value.
_REACTION_MOVES = ['standing', 'default', 'crouch', 'ch', 'crouch_ch', 'left', 'crouch_left', 'right',
                   'crouch_right', 'back', 'crouch_back', 'block', 'crouch_block', 'wallslump', 'downed']
_REACTIONS = ([(n, 8 * k, 'Q', 'pushbacks') for k, n in enumerate(
                  ['pb_front', 'pb_back', 'pb_left', 'pb_right', 'pb_front_ch', 'pb_downed', 'pb_block'])]
              + [(n, 0x38 + 2 * k, 'H', None) for k, n in enumerate(
                  ['dir_front', 'dir_back', 'dir_left', 'dir_right', 'dir_front_ch', 'dir_downed'])]
              + [('r_int1', 0x44, 'I', None), ('r_int2', 0x48, 'I', None), ('vertical_pushback', 0x4C, 'H', None)]
              + [(n, 0x4E + 2 * k, 'H', 'move') for k, n in enumerate(_REACTION_MOVES)]
              + [('r_6c', 0x6C, 'I', None)])
_CANCEL = [('direction', 0, 'I', None), ('button', 4, 'I', None), ('req', 8, 'Q', 'requirements'),
           ('extradata', 0x10, 'Q', 'cancel_extras'), ('win_start', 0x18, 'I', None), ('win_end', 0x1C, 'I', None),
           ('start_frame', 0x20, 'I', None), ('move_id', 0x24, 'H', 'move'),
           ('option', 0x26, 'H', None)]       # 0 in the file (the game derives it at load)
_VALUES = ['value', 'value2', 'value3', 'value4', 'value5']
_PROPS = [('req', 0, 'Q', 'requirements'), ('id', 8, 'I', None)] + [(n, 0xC + 4 * k, 'I', None)
                                                                     for k, n in enumerate(_VALUES)]
LAYOUTS = {
    'reactions': (0x70, _REACTIONS),
    'requirements': (0x14, [('condition', 0, 'I', None), ('param', 4, 'I', None), ('param2', 8, 'I', None),
                            ('param3', 0xC, 'I', None), ('param4', 0x10, 'I', None)]),
    'hit_conditions': (0x18, [('req', 0, 'Q', 'requirements'), ('damage', 8, 'I', None), ('h_0c', 0xC, 'I', None),
                              ('reactions', 0x10, 'Q', 'reactions')]),
    'projectiles': (0xE0, [('words', 0, '56I', None)]),          # split into fields by _projectile
    'pushbacks': (0x10, [('duration', 0, 'H', None), ('displacement', 2, 'H', None), ('loops', 4, 'I', None),
                         ('extradata', 8, 'Q', 'pushback_extras')]),
    'pushback_extras': (0x2, [('value', 0, 'H', None)]),
    'cancels': (0x28, _CANCEL),
    'group_cancels': (0x28, _CANCEL),
    'cancel_extras': (0x4, [('value', 0, 'I', None)]),
    'extra_move_properties': (0x28, [('frame', 0, 'I', None), ('x_04', 4, 'I', None), ('req', 8, 'Q', 'requirements'),
                                     ('id', 0x10, 'I', None)] + [(n, 0x14 + 4 * k, 'I', None)
                                                                 for k, n in enumerate(_VALUES)]),
    'move_begin_props': (0x20, _PROPS),
    'move_end_props': (0x20, _PROPS),
    'moves': (MOVE_SIZE, [
        ('name', 0x40, 'Q', None), ('anim_name', 0x48, 'Q', None), ('anim', 0x50, 'I', None),
        ('anim_hi', 0x54, 'I', None),
        ('cancel', 0x98, 'Q', 'cancels'), ('cancel2', 0xA0, 'Q', None), ('c2_int', 0xA8, 'I', None),
        ('m_34', 0xAC, 'I', None), ('cancel3', 0xB0, 'Q', None), ('c3_int', 0xB8, 'I', None), ('m_44', 0xBC, 'I', None),
        ('cancel4', 0xC0, 'Q', None), ('c4_int', 0xC8, 'I', None), ('transition', 0xCC, 'H', 'move'),
        ('m_56', 0xCE, 'H', None), ('hit_condition', 0x110, 'Q', 'hit_conditions'),
        ('m_118', 0x118, 'h', None),          # -1, else (3 moves) the game skips the hit-condition walk
        ('m_11a', 0x11A, 'H', None),
        ('anim_start', 0x11C, 'I', None),     # the first animation frame played (1: from the start)
        ('anim_len', 0x120, 'I', None),       # 0 in the file (set_anim_lengths)
        ('airborne_start', 0x124, 'I', None), ('airborne_end', 0x128, 'I', None), ('ground_fall', 0x12C, 'I', None),
        ('voiceclip', 0x130, 'Q', 'voiceclips'), ('extraprops', 0x138, 'Q', 'extra_move_properties'),
        ('begin_props', 0x140, 'Q', 'move_begin_props'), ('end_props', 0x148, 'Q', 'move_end_props'),
        ('bitfield', 0x150, 'I', None), ('m_154', 0x154, 'I', None),
        ('first_active', 0x158, 'I', None), ('last_active', 0x15C, 'I', None),
        ('m_a8', 0x2E0, 'H', None), ('distance', 0x2E2, 'H', None), ('m_444', 0x444, 'I', None)]),
    'voiceclips': (0xC, [('channel', 0, 'I', None), ('v_04', 4, 'I', None), ('id', 8, 'I', None)]),
    'input_sequences': (0x10, [('window', 0, 'H', None), ('amount', 2, 'H', None), ('s_04', 4, 'I', None),
                               ('inputs', 8, 'Q', 'inputs')]),
    'inputs': (0x8, [('direction', 0, 'I', None), ('button', 4, 'I', None)]),
    # Tekken 7: global move ids; Tekken 8: move keys of any fighter's moves (lists ending with 0)
    'parry_related': (0x4, [('value', 0, 'I', None)]),
    'camera_data': (0xC, [('c_0', 0, 'I', None), ('c_4', 4, 'H', None), ('left', 6, 'H', None), ('right', 8, 'H', None),
                          ('c_a', 0xA, 'H', None)]),
    'throw_cameras': (0x10, [('side', 0, 'Q', None), ('camera_data', 8, 'Q', 'camera_data')]),
    POSES: (0x18, [('kind', 0, 'H', None), ('slot', 2, 'H', None), ('p_04', 4, 'I', None),
                   ('req', 8, 'Q', 'requirements'), ('name_key', 0x10, 'I', None), ('p_14', 0x14, 'I', None)]),
}
HITBOXES, HITBOX_AT, HITBOX_SIZE = 8, 0x160, 0x30
Hitbox = collections.namedtuple('Hitbox', 'first last loc loc2 loc_pad radius height a b pad')
_HITBOX = struct.Struct('<IIBBHff3f3fI')
# frame-keyed parameter changes (99 of Reina's moves, mostly Tekken 8-only falls and big hits; the game sorts them
# by frame, kind 0/1/2 picks a parameter set, -1 / -1.0 keep the default; probably camera keyframes)
FRAME_PARAMS, FRAME_PARAM_AT, FRAME_PARAM_SIZE = 8, 0x2E4, 0x2C
FrameParam = collections.namedtuple('FrameParam', 'frame end kind x y z flag w u20 u24 u28')
_FRAME_PARAM = struct.Struct('<iii3fIfIII')
NO_LINK = (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF)

# Projectile words (u32, Tekken 8 row) -> Tekken 7's row (42 u32, what convert/moveset.py reads as 'raw'): (Tekken 7
# word, Tekken 8 word, count). Effect, the five words after it, delay, speeds, hits, life, shape, radius and height
# stay; Tekken 8 inserts a word before the hit level (0x3C, Tekken 7 0x38); the sounds become bank << 24 | id; then
# the hit conditions / cancels (Tekken 7 0x60 / 0x68 as 64-bit links), the team words (0x70 / 0x74 <- 0xA0 / 0xA4),
# hit width / height (0x78 / 0x7C <- 0xAC / 0xB0: 0 in the file, the game sets twice the radius and the height),
# 0x80 <- 0xB4 and 0x84.. <- 0xBC.. (Tekken 8 inserts 0xA8 and 0xB8). Value for value on Tekken 8 rows 1-4 = Tekken 7
# Heihachi's rows 2-5.
PROJ_COPY = [(0, 0, 14), (14, 15, 1), (15, 16, 4), (28, 40, 2), (30, 43, 3), (33, 47, 9)]
PROJ_SOUND_WORD, PROJ_SOUND_AT, PROJ_SOUNDS = 19, 0x50 // 4, 5     # Tekken 7 words 19..23 <- triples at 0x50 + 12 k
PROJ_LINKS = (0x90 // 4, 0x98 // 4)     # hit conditions, cancels (u64; 0: none)
PROJ_T7_LINKS = (24, 26)                # ... Tekken 7's (u64; -1: none)
PROJ_WIDTH = (30, 31)                   # Tekken 7's hit width / height
PROJ_T7_WORDS = 42


def _compile(layout):
    """(row size, struct, [(name, link)]) of a layout; the fields in offset order with the gaps skipped."""
    size, fields = layout
    fmt, names, pos = '<', [], 0
    for name, off, code, link in sorted(fields, key=lambda f: f[1]):
        if off < pos:
            raise ValueError('overlapping fields at %#x' % off)
        if off > pos:
            fmt += '%dx' % (off - pos)
        fmt += code
        pos = off + struct.calcsize('<' + code)
        names.append((name, link, len(struct.unpack('<' + code, bytes(struct.calcsize('<' + code))))))
    if pos > size:
        raise ValueError('fields run past the row')
    return size, struct.Struct(fmt), names


COMPILED = {t: _compile(l) for t, l in LAYOUTS.items()}


def _read_table(d, at, count, table):
    size, st, names = COMPILED[table]
    single = all(n == 1 for _, _, n in names)
    links = [k for k, (_, link, _) in enumerate(names) if link not in (None, 'move')]
    keys = [name for name, _, _ in names]
    out = []
    for i in range(count):
        v = st.unpack_from(d, at + i * size)
        if not single:
            row, k = {}, 0
            for name, _, n in names:
                row[name] = v[k] if n == 1 else v[k:k + n]
                k += n
            out.append(row)
            continue
        if links:
            v = list(v)
            for k in links:
                if v[k] in NO_LINK:
                    v[k] = None
        out.append(dict(zip(keys, v)))
    return out


# ---------------------------------------------------------------------------------------------------- banks
BANK_ENTRY = 0x38
CATEGORIES = 6


class Bank:
    """The index of an animation bank (.anmbin: the fighter's own or the common one): what a move's anim index
    names. head: the file's first bytes, at least the index (index_size(head) bytes)."""

    def __init__(self, head):
        if len(head) < 0x98:
            raise InputError('this animation bank is too short to be one')
        self.size, = struct.unpack_from('<I', head, 0)
        if len(head) < self.size:
            raise InputError('this animation bank is cut off (%d of its %d index bytes)' % (len(head), self.size))
        self.counts = struct.unpack_from('<6I', head, 4)
        key_counts = struct.unpack_from('<6I', head, 0x1C)
        lists = struct.unpack_from('<6Q', head, 0x38)
        key_lists = struct.unpack_from('<6Q', head, 0x68)
        self.entries, self.keys = [], []
        for c in range(CATEGORIES):
            if lists[c] + self.counts[c] * BANK_ENTRY > self.size or key_lists[c] + 4 * key_counts[c] > self.size:
                raise InputError('this animation bank\'s index runs past its end')
            cat = {}
            for j in range(self.counts[c]):
                o = lists[c] + j * BANK_ENTRY
                key, = struct.unpack_from('<I', head, o)
                data, path = struct.unpack_from('<QQ', head, o + 8)
                cat.setdefault(key, (j, data, path, struct.unpack_from('<8I', head, o + 0x18)))
            self.entries.append(cat)
            self.keys.append(list(struct.unpack_from('<%dI' % key_counts[c], head, key_lists[c])))

    def entry(self, category, key):
        """(index, data offset, path offset, mask) of a key's entry, or None."""
        return self.entries[category].get(key)

    def holds(self, category, key, fighter=None):
        """The bank has the key's animation data (for the fighter's roster id: its bit is set in the mask)."""
        e = self.entries[category].get(key)
        if e is None or not e[1]:
            return False
        return fighter is None or bool(e[3][fighter >> 5] >> (fighter & 31) & 1)


def index_size(head):
    """How many bytes of a bank its index takes (from the first 4)."""
    return struct.unpack_from('<I', head, 0)[0]


def read_bank(path):
    """A bank's index read from its file (the animation data is not read)."""
    with open(path, 'rb') as f:
        head = f.read(4)
        if len(head) < 4:
            raise InputError('%s is not an animation bank' % path)
        f.seek(0)
        return Bank(f.read(max(index_size(head), 0x98)))


# ---------------------------------------------------------------------------------------------------- moveset
class Moveset8(Moveset):
    """A Tekken 8 moveset in the common form: tables (TABLE_ORDER and 'poses'), aliases (Tekken 7's 56 slots),
    aliases8 (Tekken 8's 60), character_id (the roster id), code, own_prefix ('Zbr': the fighter's own moves'
    prefix); move names from set_names (movenames.py): move_name / anim_name are '' for a move not named (label
    gives a stand-in for messages)."""
    game = 't8'
    end_req = END_REQ

    def name(self, off):
        """The name stored at an offset of the (stripped) name block, when it is known."""
        return self._by_offset.get(off, '')

    def move_name(self, i):
        return self.names.get(i, '')

    def anim_name(self, i):
        return self.anim_names.get(i, '')

    def label(self, i):
        """Move i's name, or '#<index>:<name key>' when it has none (for messages)."""
        return self.names.get(i) or '#%d:%08x' % (i, self.tables['moves'][i]['name_key'])

    def name_lengths(self, i):
        """(name length, animation name length) of move i, from the name block's offsets (None: unknown)."""
        mv = self.tables['moves']
        a, b = mv[i]['name'], mv[i]['anim_name']
        c = mv[i + 1]['name'] if i + 1 < len(mv) else self.name_block
        return (b - a - 1 if b > a else None), (c - b - 1 if c > b else None)

    def set_names(self, names, anim_names=None):
        """Move names {index: name} (and animation names {index: name}) found for this moveset."""
        self.names = dict(names)
        if anim_names is not None:
            self.anim_names = dict(anim_names)
        self._by_offset = {}
        for i, mv in enumerate(self.tables['moves']):
            self._by_offset[mv['name']] = self.move_name(i)
            self._by_offset.setdefault(mv['anim_name'], self.anim_name(i))

    def named(self):
        """How many moves have a name."""
        return len(self.names)

    def attach_banks(self, own, common=None):
        """The fighter's own animation bank and the common one (Bank objects) that anim_ref looks keys up in."""
        self.banks = (own, common)

    def anim_ref(self, i):
        """(animation key, bank) of move i: bank 'own' (the fighter's .anmbin), 'com' (com.anmbin) or None (neither
        has the animation)."""
        own, common = self.banks
        if own is None:
            raise ValueError('no animation banks attached (attach_banks)')
        k = self.tables['moves'][i]['anim'] & 0xFFFF3FFF            # the bits above are flags the game strips
        keys = own.keys[0]
        if k >= len(keys):
            return None, None
        key = keys[k]
        if own.holds(0, key):
            return key, 'own'
        if common is not None and common.holds(0, key, self.character_id):
            return key, 'com'
        return key, None

    def set_anim_lengths(self, frames):
        """anim_len of every move as the game sets it when loading: frames(key, bank) = the animation's last frame
        number (its PANM header) or None; length = frames + 1 - (first frame - 1)."""
        for i, mv in enumerate(self.tables['moves']):
            key, bank = self.anim_ref(i)
            n = frames(key, bank) if bank is not None else None
            mv['anim_len'] = max(0, n + 2 - max(mv['anim_start'], 1)) if n is not None else 0

    def hitboxes(self, i):
        """The hit boxes move i uses (an active window or a location)."""
        return [h for h in self.tables['moves'][i]['hitboxes'] if h.first or h.last or h.loc or h.loc2]

    def reqs(self, i):
        """[(condition, param, param2, param3, param4)] of the requirement list at i."""
        if i is None:
            return []
        return [(r['condition'], r['param'], r['param2'], r['param3'], r['param4'])
                for _, r in self.iter_list('requirements', i, lambda r: r['condition'] == END_REQ)
                if r['condition'] != END_REQ]

    def sequence(self, direction):
        """(window, [(direction, button)]) of an input-sequence direction (Tekken 7 numbering), or None."""
        k = direction - SEQ0
        if not 0 <= k < len(self.tables['input_sequences']):
            return None
        s = self.tables['input_sequences'][k]
        return s['window'], [(x['direction'], x['button'])
                             for x in self.tables['inputs'][s['inputs']:s['inputs'] + s['amount']]]

    def move_by_key(self, key):
        """The index of the move with this name key, or None."""
        return self._by_key.get(key)

    def move_by_move_key(self, key):
        """The index of the move with this move key (how the command list and other fighters name a move), or
        None."""
        return self._by_move_key.get(key)


def read_fields(data, moves=None, moves_offset=None):
    """The six protected fields per move from a fields.bin: [(name key, anim key, vuln, hit level, owner id, move
    key)]; with moves / moves_offset given, checked against the moveset it must belong to."""
    if data is None or len(data) < FIELDS_HEADER:
        raise InputError('the protected move fields (<code>.motbin.fields.bin) are missing: dump the fighter again')
    n, stride, offset = struct.unpack_from('<III', data, 0)
    if len(data) < FIELDS_HEADER + 24 * n or stride != MOVE_SIZE or (moves is not None and n != moves) or \
            (moves_offset is not None and offset != moves_offset):
        raise InputError('the protected move fields (<code>.motbin.fields.bin) do not belong to this moveset '
                         '(%d moves of %d bytes at %#x): dump the fighter again' % (n, stride, offset))
    v = struct.unpack_from('<%dI' % (6 * n), data, FIELDS_HEADER)
    return [v[6 * i:6 * i + 6] for i in range(n)]


def _projectile(row):
    """Tekken 8 projectile words -> named fields and its links (the Tekken 7 row comes later: _projectile_raw)."""
    w = row.pop('words')
    hc, cl = (w[PROJ_LINKS[0]] | w[PROJ_LINKS[0] + 1] << 32), (w[PROJ_LINKS[1]] | w[PROJ_LINKS[1] + 1] << 32)
    row['hit_condition'] = hc or None
    row['cancel'] = cl or None
    row.update(effect=w[0], delay=w[6], speed_fwd=w[7], speed_up=w[8], hits=w[9], lifetime=w[10], shape=w[11],
               radius=w[12], height=w[13], p_38=w[14], hitlevel=w[15],
               sounds=[w[PROJ_SOUND_AT + 3 * k:PROJ_SOUND_AT + 3 * k + 3] for k in range(PROJ_SOUNDS)],
               team_own=w[40], team_other=w[41], p_a8=w[42], hit_width=w[43], hit_height=w[44], p_b8=w[46], words8=w)
    return row


def _projectile_raw(row):
    """A projectile's Tekken 7 row (42 u32: 'raw', what convert/moveset.py reads) from its Tekken 8 words, with the
    row's links as they are after the cancel rows left out (_drop_commands)."""
    w = row['words8']
    t7 = [0] * PROJ_T7_WORDS
    for to, fr, n in PROJ_COPY:
        t7[to:to + n] = w[fr:fr + n]
    for k, (bank, _, sid) in enumerate(row['sounds']):
        t7[PROJ_SOUND_WORD + k] = (bank & 0xFF) << 24 | (sid & 0xFFFFFF) if (bank or sid) else 0
    for at7, v in zip(PROJ_T7_LINKS, (row['hit_condition'], row['cancel'])):
        t7[at7:at7 + 2] = (0xFFFFFFFF, 0xFFFFFFFF) if v is None else (v & 0xFFFFFFFF, v >> 32)
    if not t7[PROJ_WIDTH[0]]:
        t7[PROJ_WIDTH[0]] = 2 * row['radius']
    if not t7[PROJ_WIDTH[1]]:
        t7[PROJ_WIDTH[1]] = row['height']
    row['raw'] = struct.pack('<%dI' % PROJ_T7_WORDS, *t7)


def _command(d, nseq):
    """A Tekken 8 cancel direction in Tekken 7's encoding, or None (a Tekken 8-only or unknown special)."""
    if d < 0x8000 or d in (LIST_END, 0x8001, 0x8002):
        return d
    if d in COMMANDS:
        return COMMANDS[d]
    if T8_SEQ0 <= d < T8_SEQ0 + nseq:
        return d - T8_SEQ0 + SEQ0
    return None


def _drop_commands(m, nseq):
    """Commands -> Tekken 7's; the rows of Tekken 8-only (or unknown) specials are left out, and the links into the
    cancel tables follow the rows that stay (a link to a row left out goes to the next row of its list)."""
    remap = {}
    for t in ('cancels', 'group_cancels'):
        rows, keep = m.tables[t], []
        for i, c in enumerate(rows):
            d = _command(c['direction'], nseq)
            if d is None:
                m.dropped[(t, c['direction'])] += 1
                continue
            c['direction'] = d
            keep.append(i)
        index, k = [], 0                       # old row -> the first row kept at or after it
        for i in range(len(rows) + 1):
            while k < len(keep) and keep[k] < i:
                k += 1
            index.append(k)
        remap[t] = index
        m.tables[t] = [rows[i] for i in keep]
        m.rows8[t] = keep

    def link(table, v):
        return None if v is None else remap[table][min(v, len(remap[table]) - 1)]
    for mv in m.tables['moves']:
        for f in ('cancel', 'cancel2', 'cancel3', 'cancel4'):
            mv[f] = link('cancels', mv[f])
    for p in m.tables['projectiles']:
        p['cancel'] = link('cancels', p['cancel'])
    for c in m.tables['cancels']:
        if c['direction'] == GROUP:
            c['move_id'] = link('group_cancels', c['move_id'])


def own_prefix(code):
    """The prefix of a fighter's own move names: its code with a capital ('zbr' -> 'Zbr', as in 'Zbr_sKAM00_')."""
    return code[:1].upper() + code[1:].lower()


def read(data, fields, code):
    """A Tekken 8 moveset: data = the .motbin as the game's reader returns it, fields = its fields.bin (the plain
    values of the protected move fields), code = the fighter's Tekken 8 code ('zbr'). Moves have no names until
    movenames.name_moves (or set_names) gives them; anim_ref needs the banks (attach_banks)."""
    d = bytes(data)
    if len(d) < BASE or d[8:12] != MAGIC:
        raise InputError('this is not a Tekken 8 moveset (.motbin)')
    if d[2]:
        raise InputError('this Tekken 8 moveset was saved after the game set it up in memory (links, not row '
                         'numbers): dump the fighter again')
    m = Moveset8()
    m.code = code
    m.character_name = code
    m.own_prefix = own_prefix(code)
    # what the Tekken 7 form has and a Tekken 8 moveset has not: names (movenames.py), animations (anim_ref: the
    # banks), the command list (<code>.mvl, a file of its own)
    m.namebuf, m.animbuf, m.anim_offsets, m.anim_size, m.movelist = b'', b'', [], {}, b''
    m.header = h = {}
    h['version'], = struct.unpack_from('<I', d, 4)
    h['strings'] = struct.unpack_from('<4Q', d, 0x10)
    m.aliases8 = list(struct.unpack_from('<%dH' % ALIASES, d, 0x30))
    m.current_aliases8 = list(struct.unpack_from('<%dH' % ALIASES, d, 0x30 + 2 * ALIASES))
    m.unknown_aliases = list(struct.unpack_from('<32H', d, 0x120))
    h['id_lo'], h['id_hi'] = struct.unpack_from('<II', d, 0x160)
    m.character_id = (h['id_lo'] - 1) // 0xFFFF
    m.name_block, = struct.unpack_from('<Q', d, NAME_BLOCK)
    m.tables, m.offsets = {}, {}
    for t in ORDER:
        po, co = HEADER_TABLES[t]
        off, = struct.unpack_from('<Q', d, po)
        n, = struct.unpack_from('<Q', d, co)
        if BASE + off + n * LAYOUTS[t][0] > len(d):
            raise InputError('this Tekken 8 moveset is cut off (its %s run past the end)' % t)
        m.offsets[t] = off
        m.tables[t] = _read_table(d, BASE + off, n, t)
    moves = m.tables['moves']
    prot = read_fields(fields, len(moves), m.offsets['moves'])
    for i, (mv, p) in enumerate(zip(moves, prot)):
        mv.update(zip(PROTECTED, p))
        o = BASE + m.offsets['moves'] + i * MOVE_SIZE
        mv['hitboxes'] = tuple(Hitbox(*v[:5], v[5], v[6], v[7:10], v[10:13], v[13]) for v in
                               (_HITBOX.unpack_from(d, o + HITBOX_AT + HITBOX_SIZE * k) for k in range(HITBOXES)))
        mv['frame_params'] = tuple(FrameParam(*_FRAME_PARAM.unpack_from(d, o + FRAME_PARAM_AT + FRAME_PARAM_SIZE * k))
                                   for k in range(FRAME_PARAMS))
        hb = mv['hitboxes']
        mv['hitbox'] = bytes((hb[0].loc, hb[0].loc2, hb[1].loc, hb[1].loc2))   # Tekken 7's 4-byte summary
        g = mv['owner_id'] + i                                     # Tekken 7's global move id: owner id + index
        mv['move_id_lo'], mv['move_id_hi'] = g & 0xFFFF, g >> 16 & 0xFFFF
        mv['m_5c'] = mv['m_5e'] = mv['m_ac'] = 0
        for f, n in (('cancel2', 'c2_int'), ('cancel3', 'c3_int'), ('cancel4', 'c4_int')):
            if not mv[n] or mv[f] in NO_LINK:                      # the game links these only with a count
                mv[f] = None
    m.tables['projectiles'] = [_projectile(p) for p in m.tables['projectiles']]
    for v in m.tables['voiceclips']:
        end = v['channel'] == 0xFFFFFFFF
        v['value'] = 0xFFFFFFFF if end else (v['channel'] & 0xFF) << 24 | (v['id'] & 0xFFFFFF)
    m.dropped = collections.Counter()
    m.rows8 = {}
    _drop_commands(m, len(m.tables['input_sequences']))
    _move_ids(m)
    for p in m.tables['projectiles']:
        _projectile_raw(p)
    m.names, m.anim_names, m.banks = {}, {}, (None, None)
    m._by_key, m._by_move_key = {}, {}
    for i, mv in enumerate(moves):
        m._by_key.setdefault(mv['name_key'], i)
        m._by_move_key.setdefault(mv['move_key'], i)
    for p in m.tables[POSES]:
        p['move'] = m._by_key.get(p['name_key'])
    m.set_names({})
    return m


def _move_ids(m):
    """Alias slots: Tekken 7's 56 from Tekken 8's 60, and every move id through the slot map."""
    a8, nm = m.aliases8, len(m.tables['moves'])
    m.direct_aliases = collections.Counter()
    m.aliases = [0] * T7_ALIASES
    for s8, s7 in ALIAS_SLOTS.items():
        m.aliases[s7] = a8[s8]

    def mid(v):
        if v < 0x8000:
            return v
        k = v - 0x8000
        if k in ALIAS_SLOTS:
            return 0x8000 + ALIAS_SLOTS[k]
        if k < ALIASES and a8[k] < nm:
            m.direct_aliases[k] += 1                  # a Tekken 8-only slot: the move it holds
            return a8[k]
        return v
    for r in m.tables['reactions']:
        for f in _REACTION_MOVES:
            r[f] = mid(r[f])
    for mv in m.tables['moves']:
        mv['transition'] = mid(mv['transition'])
    for t in ('cancels', 'group_cancels'):
        for c in m.tables[t]:
            if c['direction'] != GROUP:
                c['move_id'] = mid(c['move_id'])
    for r in m.tables['requirements']:
        if r['condition'] in MOVE_PARAMS:
            r['param'] = mid(r['param'])
