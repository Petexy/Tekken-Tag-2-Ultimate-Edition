"""TTT2 Wii U movesets ("motbin", data006: one per motion row), read into the common moveset form (movesets.py)
and written back byte for byte.

    0x000 u32, "COM\\0", 4 x u32 string offsets (name, creator, date, full date), u16 aliases[56] @0x18,
          u16 current aliases[56] @0x88, u16 unknown[36] @0xF8 (the last four: the character id as
          id-1, -(id-1), id, -id), 19 x {u32 offset, u32 count} @0x140 (the tables), 13 x u32 @0x1D8 (embedded
          MOTAs, 0: none); offsets count from BASE (0x20C)
    BASE: the string block (names), the 19 tables (big-endian, layouts in movesets.TTT2), the embedded MOTAs.
The game keeps the 13 slots at the moveset's +0x1D8 in memory: slot 2 (HAND_SHAPES) is the fighter's hand shapes, a
hands container (ttt2/motion.py) of one animation whose frames are the shapes; a move's 0x82d6 / 0x82d7 (left /
right hand) shows frame value >> 8 of it, 0x82d9 both hands' default (left frame 1, right frame 2), and so does a
hand animation number without 0x4000 (0x82db / 0x82dc, the game's sub_037F3690); slot 3, empty in the file, is
the motion pack's hands container then (the number with 0x4000).
"""
import struct

from ..movesets import TABLE_ORDER, TTT2, Moveset, pack_table, read_table

BASE = 0x20C
HAND_SHAPES = 2


def read(d):
    if d[4:8] != b'COM\0':
        raise ValueError('not a TTT2 moveset')
    m = Moveset()
    m.game = 'ttt2'
    m.raw = d
    m.namebuf = d[BASE:]
    m.aliases = list(struct.unpack_from('>56H', d, 0x18))
    m.table_info, m.tables = {}, {}
    for k, t in enumerate(TABLE_ORDER):
        off, cnt = struct.unpack_from('>II', d, 0x140 + 8 * k)
        m.table_info[t] = (off, cnt)
        m.tables[t] = read_table(d, BASE + off, cnt, TTT2[t], '>')
    m.motalist = list(struct.unpack_from('>13I', d, 0x1D8))
    m.name_offsets = struct.unpack_from('>4I', d, 8)
    return m


def split(m):
    """(header, string block, MOTA blob, MOTA slots relative to the blob) of a read moveset."""
    d = m.raw
    first = m.table_info['reactions'][0]
    end = max(p + n * TTT2[t][0] for t, (p, n) in m.table_info.items())
    used = [o for o in m.motalist if o]
    mstart = min(used) if used else end
    return d[:BASE], d[BASE:BASE + first], d[BASE + mstart:], [(o - mstart) if o else None for o in m.motalist]


def slot_bytes(m, k):
    """The bytes of a read moveset's embedded MOTA slot k (up to the next slot's), None if the slot is empty."""
    _, _, blob, slots = split(m)
    if slots[k] is None:
        return None
    return blob[slots[k]:min([o for o in slots if o is not None and o > slots[k]] + [len(blob)])]


def with_slot(blob, slots, k, data):
    """(MOTA blob, slots) as split gives them, with slot k's bytes (up to the next slot's) replaced by data; the
    others keep their bytes and order, each 4-aligned."""
    if slots[k] is None or sum(o == slots[k] for o in slots) > 1:
        raise ValueError('MOTA slot %d is empty or shared' % k)
    starts = sorted(set(o for o in slots if o is not None))
    ends = dict(zip(starts, starts[1:] + [len(blob)]))
    out, moved = bytearray(), {}
    for o in starts:
        while len(out) % 4:
            out.append(0)
        moved[o] = len(out)
        out += data if o == slots[k] else blob[o:ends[o]]
    return bytes(out), [None if o is None else moved[o] for o in slots]


def build(header, strings, tables, mota_blob, mota_slots, name_offsets=None):
    """A motbin from its pieces: the header's table and MOTA pointers are rewritten (and the four string offsets
    with name_offsets); the tables follow the string block (padded to 4), the MOTAs the tables."""
    hdr = bytearray(header[:BASE])
    body = bytearray(strings)
    while len(body) % 4:
        body.append(0)
    ptrs = []
    for t in TABLE_ORDER:
        ptrs.append((len(body), len(tables[t])))
        body += pack_table(tables[t], TTT2[t])
    mota_base = len(body)
    body += mota_blob
    for k, (p, n) in enumerate(ptrs):
        struct.pack_into('>II', hdr, 0x140 + 8 * k, p, n)
    for k in range(13):
        s = mota_slots[k] if k < len(mota_slots) else None
        struct.pack_into('>I', hdr, 0x1D8 + 4 * k, 0 if s is None else mota_base + s)
    if name_offsets is not None:
        struct.pack_into('>4I', hdr, 8, *name_offsets)
    return bytes(hdr + body)
