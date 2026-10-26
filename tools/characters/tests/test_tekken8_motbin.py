"""The Tekken 8 moveset reader (tekken8/motbin.py) on made-up movesets, built here at the offsets the reader's
docstring gives (the builders are shared with test_tekken8_motbin_names.py).

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char import InputError                       # noqa: E402
from ttt2char.convert import idmaps                   # noqa: E402
from ttt2char.tekken8 import motbin                   # noqa: E402
from ttt2char.tekken8.city32 import city32            # noqa: E402

NULL = 0xFFFFFFFFFFFFFFFF
BASE = 0x318
ORDER = ['reactions', 'requirements', 'hit_conditions', 'projectiles', 'pushbacks', 'pushback_extras', 'cancels',
         'group_cancels', 'cancel_extras', 'extra_move_properties', 'move_begin_props', 'move_end_props', 'moves',
         'voiceclips', 'input_sequences', 'inputs', 'parry_related', 'camera_data', 'throw_cameras', 'poses']
ROW = {'reactions': 0x70, 'requirements': 0x14, 'hit_conditions': 0x18, 'projectiles': 0xE0, 'pushbacks': 0x10,
       'pushback_extras': 2, 'cancels': 0x28, 'group_cancels': 0x28, 'cancel_extras': 4,
       'extra_move_properties': 0x28, 'move_begin_props': 0x20, 'move_end_props': 0x20, 'moves': 0x448,
       'voiceclips': 0xC, 'input_sequences': 0x10, 'inputs': 8, 'parry_related': 4, 'camera_data': 0xC,
       'throw_cameras': 0x10, 'poses': 0x18}
JUNK = bytes(range(0xA0, 0xC0))          # what a protected 32-byte field holds in the file (never read)


# ---------------------------------------------------------------------------------------------------- builders
def q(v):
    """A u64 link: None -> -1."""
    return NULL if v is None else v


def requirement(cond, param=0, *more):
    return struct.pack('<5I', cond, param, *(list(more) + [0] * (3 - len(more))))


def cancel(direction, move_id=0, button=0, req=0, extra=None, start=1, end=32767, frame=1):
    return struct.pack('<IIQQIIIHH', direction, button, q(req), q(extra), start, end, frame, move_id, 0)


def hitbox(first=0, last=0, loc=0, loc2=0, radius=0.0, height=0.0, a=(0.0, 0.0, 0.0), b=(0.0, 0.0, 0.0)):
    return struct.pack('<IIBBHff3f3fI', first, last, loc, loc2, 0, radius, height, *(tuple(a) + tuple(b) + (0,)))


def move(name, anim_name, anim=0, cancel_=None, transition=0x8001, hit_condition=0, voice=None, xp=None, bp=None,
         ep=None, hitboxes=(), bitfield=0, active=(0, 0), airborne=(0, 0, 0), distance=0, anim_start=1):
    """A move row; name / anim_name: offsets into the (stripped) name block."""
    b = bytearray(0x448)
    for off in (0x00, 0x20, 0x58, 0x78, 0xD0, 0xF0):
        b[off:off + 32] = JUNK
    struct.pack_into('<QQII', b, 0x40, name, anim_name, anim, 0)
    struct.pack_into('<Q', b, 0x98, q(cancel_))
    struct.pack_into('<QII', b, 0xA0, NULL, 0, 0)
    struct.pack_into('<QII', b, 0xB0, 0, 0, 0)
    struct.pack_into('<QI', b, 0xC0, 0, 0)
    struct.pack_into('<HH', b, 0xCC, transition, 7)
    struct.pack_into('<QhHII', b, 0x110, hit_condition, -1, 0, anim_start, 0)
    struct.pack_into('<III', b, 0x124, *airborne)
    struct.pack_into('<4Q', b, 0x130, q(voice), q(xp), q(bp), q(ep))
    struct.pack_into('<IIII', b, 0x150, bitfield, 0, active[0], active[1])
    for k, h in enumerate(hitboxes):
        b[0x160 + 0x30 * k:0x190 + 0x30 * k] = h
    struct.pack_into('<HH', b, 0x2E0, 2, distance)
    for k in range(8):
        struct.pack_into('<iii3fIfIII', b, 0x2E4 + 0x2C * k, -1, -1, -1, -1.0, -1.0, -1.0, 0, -1.0, 0, 0, 0)
    return bytes(b)


def layout_names(names):
    """Offsets of names and their animation names in a name block as Tekken 8 lays it out (four header strings,
    then each move's name and animation name, NUL-terminated) -> ([(name offset, anim offset)], block size)."""
    off = 8 + 14 + 16 + 29                     # the header strings (7, 13, 15 and 28 characters)
    out = []
    for n, a in names:
        out.append((off, off + len(n) + 1))
        off += len(n) + 1 + len(a) + 1
    return out, off


def build(tables, aliases=None, roster=5, name_block=0, fixed=0):
    """A Tekken 8 .motbin (file form) from {table: [row bytes]} (missing tables: empty)."""
    aliases = list(aliases or [0] * 60)
    head = bytearray(BASE)
    struct.pack_into('<HBBI4s', head, 0, 0, fixed, 0, 20240719, b'TEK\0')
    struct.pack_into('<4Q', head, 0x10, 0, 8, 22, 38)
    struct.pack_into('<60H', head, 0x30, *aliases)
    struct.pack_into('<60H', head, 0xA8, *aliases)
    struct.pack_into('<II', head, 0x160, roster * 0xFFFF + 1, (roster + 1) * 0xFFFF + 1)
    body = bytearray()
    for k, t in enumerate(ORDER):
        rows = tables.get(t, [])
        for r in rows:
            assert len(r) == ROW[t], (t, len(r))
        if t == 'reactions':
            struct.pack_into('<QQQ', head, 0x168, len(body), name_block, len(rows))
        else:
            struct.pack_into('<QQ', head, 0x180 + 0x10 * (k - 1), len(body), len(rows))
        body += b''.join(rows)
    return bytes(head + body)


def fields_bin(data, protected):
    """A fields.bin for the moveset `data`: protected = [(name key, anim key, vuln, hit level, owner, move key)]."""
    moves_at, = struct.unpack_from('<Q', data, 0x180 + 0x10 * (ORDER.index('moves') - 1))
    return struct.pack('<III', len(protected), 0x448, moves_at) + b''.join(struct.pack('<6I', *p) for p in protected)


def bank(categories):
    """An animation bank's index: categories = [(entries [(key, data offset, path offset, mask words)], keys)]."""
    cats = list(categories) + [([], [])] * (6 - len(categories))
    entries = b''
    keys = b''
    lists, key_lists = [], []
    at = 0x98
    for ents, _ in cats:
        lists.append(at)
        for key, data, path, mask in ents:
            entries += struct.pack('<IIQQ8I', key, 0, data, path, *(list(mask) + [0] * (8 - len(mask))))
        at += 0x38 * len(ents)
    for _, ks in cats:
        key_lists.append(at)
        keys += struct.pack('<%dI' % len(ks), *ks)
        at += 4 * len(ks)
    head = struct.pack('<I6I6I', at, *([len(e) for e, _ in cats] + [len(k) for _, k in cats]))
    head += bytes(0x38 - len(head)) + struct.pack('<6Q6Q', *(lists + key_lists))
    return head + bytes(0x98 - len(head)) + entries + keys


# ---------------------------------------------------------------------------------------------------- a fighter
CODE = 'abc'
NAMES = [('Abc_sKAM00_', 'xx_stance'), ('Abc_66RK', 'xx_66rk'), ('Abc_3LP_n', 'xx_throw_n'), ('Co_Thing00', 'co_a')]
SEQ = 0x8014                             # Tekken 8: input sequence 0


def fighter():
    """(motbin bytes, fields.bin bytes, names) of a made-up four-move fighter with one of everything."""
    offs, block = layout_names(NAMES)
    T = {}
    T['requirements'] = [requirement(0), requirement(1100),                       # 0-1: always
                         requirement(220, 5), requirement(1100),                  # 2-3: "is character 5"
                         requirement(0x824c, 0x8000 + 30), requirement(1100),     # 4-5: param = a move id (slot 30)
                         requirement(325, 1, 2), requirement(1100)]               # 6-7: extra params
    T['pushback_extras'] = [struct.pack('<H', 10), struct.pack('<H', 0)]
    T['pushbacks'] = [struct.pack('<HHIQ', 3, 100, 1, 0)]
    T['reactions'] = [struct.pack('<7Q6HIIH15HI', *([0] * 7 + list(range(6)) + [11, 12, 0xFE70]
                                                     + [1, 2, 3, 0x8000 + 29, 3, 3, 3, 3, 3, 3, 3, 3, 3,
                                                        0x8000 + 27, 2] + [0]))]
    T['hit_conditions'] = [struct.pack('<QIIQ', 2, 25, 0, 0), struct.pack('<QIIQ', 1, 10, 0, 0)]  # 1: none
    T['cancel_extras'] = [struct.pack('<I', 0x80)]
    # cancels: move 0's list [up tap -> move 1, side step (Tekken 8 only), group 0, sequence 0, end];
    # move 1's list starts with a second dash (Tekken 8 only: its link moves to the next row)
    T['cancels'] = [cancel(0x8005, 1), cancel(0x8007, 2), cancel(0x8012, 0), cancel(SEQ, 2, req=4),
                    cancel(0x8000, 0x8001),
                    cancel(0x8003, 0x8002), cancel(0x40, 2, button=8, extra=0), cancel(0x8000, 0x8001)]
    T['group_cancels'] = [cancel(0x10, 3, button=1), cancel(0x8013, 0)]
    T['extra_move_properties'] = [struct.pack('<IIQ6I', 0x8001, 0, 2, 0x8039, 0x501, 7, 8, 9, 10),
                                  struct.pack('<IIQ6I', 0, 0, NULL, 0, 0, 0, 0, 0, 0)]
    T['move_begin_props'] = [struct.pack('<Q6I', 0, 0x8385, 1, 2, 3, 4, 0), struct.pack('<Q6I', NULL, 1100, 0, 0,
                                                                                         0, 0, 0)]
    T['move_end_props'] = [struct.pack('<Q6I', NULL, 1100, 0, 0, 0, 0, 0)]
    T['voiceclips'] = [struct.pack('<3I', 2, 0, 0x9986), struct.pack('<3I', 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)]
    T['inputs'] = [struct.pack('<II', 0x40, 0), struct.pack('<II', 0x40, 0)]
    T['input_sequences'] = [struct.pack('<HHIQ', 12, 2, 0, 0)]
    T['parry_related'] = [struct.pack('<I', city32('XYZ_Co_Other')), struct.pack('<I', 0)]
    T['camera_data'] = [struct.pack('<IHHHH', 0x16, 0, 0x819, 0x819, 0)]
    T['throw_cameras'] = [struct.pack('<QQ', 1, 0)]
    words = [0] * 56
    words[0], words[6], words[7], words[9], words[10], words[12], words[13], words[15] = 0x3c, 0, 160, 1, 40, 150, \
        250, 0x217
    words[0x68 // 4], words[0x68 // 4 + 2] = 7, 0x10            # a sound on hit: bank 7, id 0x10
    words[0x90 // 4] = 1                                        # hit condition 1
    words[0x98 // 4] = 6                                        # cancel row 6 (row 5 is left out: it becomes 5)
    words[40], words[41] = 0, 1
    T['projectiles'] = [struct.pack('<56I', *([0] * 56)), struct.pack('<56I', *words)]
    T['poses'] = [struct.pack('<HHIQII', 0, 1, 0, 0, city32('Abc_sKAM00_'), 157)]
    T['moves'] = [
        move(offs[0][0], offs[0][1], anim=0, cancel_=0, transition=0x8001, voice=0, bp=0, ep=0,
             hitboxes=[hitbox(10, 12, 16, 19, 4.5, 2.0, (1.0, 2.0, 3.0)), hitbox(10, 12, 9, 13)],
             bitfield=0x8000000, active=(10, 12), airborne=(1, 2, 3), distance=0xC64D),
        move(offs[1][0], offs[1][1], anim=1, cancel_=5, transition=0x8000 + 30, hit_condition=0, xp=0),
        move(offs[2][0], offs[2][1], anim=2, cancel_=None, transition=0x8000 + 58),
        move(offs[3][0], offs[3][1], anim=3 | 0x4000, transition=0x8000 + 59)]
    aliases = list(range(60))
    aliases = [k % 4 for k in aliases]
    aliases[27], aliases[58] = 2, 3                             # Tekken 8-only slots
    data = build(T, aliases, roster=5, name_block=block)
    prot = [(city32(n), city32(a), 0x842 + i, 0x217 * (i == 1), 5 * 0xFFFF + 1, city32(CODE.upper() + '_' + n))
            for i, (n, a) in enumerate(NAMES)]
    return data, fields_bin(data, prot), NAMES


def read(data=None, fields=None):
    if data is None:
        data, fields, _ = fighter()
    return motbin.read(data, fields, CODE)


# ---------------------------------------------------------------------------------------------------- tests
class Reader(unittest.TestCase):
    def setUp(self):
        self.data, self.fields, _ = fighter()
        self.m = read(self.data, self.fields)

    def test_header(self):
        m = self.m
        self.assertEqual(m.game, 't8')
        self.assertEqual(m.character_id, 5)
        self.assertEqual(m.own_prefix, 'Abc')
        self.assertEqual(m.header['version'], 20240719)
        self.assertEqual(m.name_block, layout_names(NAMES)[1])
        self.assertEqual(len(m.tables['moves']), 4)
        self.assertEqual(set(m.tables), set(ORDER))

    def test_protected_fields(self):
        mv = self.m.tables['moves']
        self.assertEqual(mv[1]['name_key'], city32('Abc_66RK'))
        self.assertEqual(mv[1]['move_key'], city32('ABC_Abc_66RK'))
        self.assertEqual(mv[1]['anim_key'], city32('xx_66rk'))
        self.assertEqual([x['vuln'] for x in mv], [0x842, 0x843, 0x844, 0x845])
        self.assertEqual([x['hitlevel'] for x in mv], [0, 0x217, 0, 0])
        self.assertEqual(mv[2]['owner_id'], 5 * 0xFFFF + 1)
        g = 5 * 0xFFFF + 1 + 2                                  # Tekken 7's global move id: owner + index
        self.assertEqual((mv[2]['move_id_hi'] << 16) | mv[2]['move_id_lo'], g)
        self.assertEqual(self.m.move_by_key(city32('Co_Thing00')), 3)
        self.assertEqual(self.m.move_by_move_key(city32('ABC_Abc_3LP_n')), 2)

    def test_move_fields(self):
        x = self.m.tables['moves'][0]
        self.assertEqual((x['airborne_start'], x['airborne_end'], x['ground_fall']), (1, 2, 3))
        self.assertEqual((x['first_active'], x['last_active'], x['bitfield']), (10, 12, 0x8000000))
        self.assertEqual((x['distance'], x['m_a8'], x['m_56'], x['anim_start'], x['anim_len']), (0xC64D, 2, 7, 1, 0))
        self.assertEqual(x['hitbox'], bytes((16, 19, 9, 13)))     # Tekken 7's summary: hit boxes 0 and 1
        self.assertEqual(len(x['hitboxes']), 8)
        h = x['hitboxes'][0]
        self.assertEqual((h.first, h.last, h.loc, h.loc2, h.radius, h.height, h.a), (10, 12, 16, 19, 4.5, 2.0,
                                                                                     (1.0, 2.0, 3.0)))
        self.assertEqual(len(self.m.hitboxes(0)), 2)
        self.assertEqual(x['frame_params'][0].frame, -1)
        self.assertIsNone(x['cancel2'])                          # a count of 0: no list
        self.assertEqual(x['hit_condition'], 0)
        self.assertEqual(self.m.tables['moves'][3]['anim'], 3 | 0x4000)

    def test_name_lengths(self):
        for i, (n, a) in enumerate(NAMES):
            self.assertEqual(self.m.name_lengths(i), (len(n), len(a)))

    def test_names_unknown_until_set(self):
        m = self.m
        self.assertEqual(m.move_name(1), '')
        self.assertEqual(m.label(1), '#1:%08x' % city32('Abc_66RK'))
        m.set_names({1: 'Abc_66RK'}, {1: 'xx_66rk'})
        self.assertEqual((m.move_name(1), m.anim_name(1), m.named()), ('Abc_66RK', 'xx_66rk', 1))
        self.assertEqual(m.name(m.tables['moves'][1]['name']), 'Abc_66RK')

    def test_aliases(self):
        m = self.m
        self.assertEqual(len(m.aliases8), 60)
        self.assertEqual(len(m.aliases), 56)
        a8 = m.aliases8
        self.assertEqual(m.aliases[:26], a8[:26])
        self.assertEqual(m.aliases[26:54], a8[29:57])
        self.assertEqual((m.aliases[54], m.aliases[55]), (a8[57], a8[59]))
        mv = m.tables['moves']
        self.assertEqual(mv[0]['transition'], 0x8001)
        self.assertEqual(mv[1]['transition'], 0x8000 + 27)        # Tekken 8 slot 30 -> Tekken 7's 27
        self.assertEqual(mv[2]['transition'], 3)                  # slot 58 (Tekken 8 only) -> the move it holds
        self.assertEqual(mv[3]['transition'], 0x8000 + 55)        # 59 -> 55
        self.assertEqual(m.resolve_alias(mv[1]['transition']), a8[30])
        r = m.tables['reactions'][0]
        self.assertEqual((r['standing'], r['ch'], r['wallslump'], r['downed']), (1, 0x8000 + 26, 2, 2))
        self.assertEqual(r['vertical_pushback'], 0xFE70)
        self.assertEqual((r['dir_front'], r['dir_downed'], r['r_int1'], r['r_int2']), (0, 5, 11, 12))
        self.assertEqual(m.tables['requirements'][4]['param'], 0x8000 + 27)   # a move id parameter (0x824c)
        self.assertEqual(m.direct_aliases[58] + m.direct_aliases[27], 2)

    def test_commands(self):
        m = self.m
        c = m.tables['cancels']
        self.assertEqual([x['direction'] for x in c], [0x8003, 0x800B, 0x800D, 0x8000, 0x40, 0x8000])
        self.assertEqual(m.dropped, {('cancels', 0x8007): 1, ('cancels', 0x8003): 1})
        self.assertEqual(m.rows8['cancels'], [0, 2, 3, 4, 6, 7])
        self.assertEqual(m.tables['moves'][1]['cancel'], 4)        # pointed at the left-out row 5: now row 6's
        self.assertEqual(m.tables['projectiles'][1]['cancel'], 4)
        self.assertEqual(c[1]['move_id'], 0)                       # the group link stays a group row
        self.assertEqual(m.tables['group_cancels'][1]['direction'], 0x800C)
        self.assertEqual(m.sequence(c[2]['direction']), (12, [(0x40, 0), (0x40, 0)]))
        self.assertEqual(c[2]['req'], 4)
        self.assertEqual(c[4]['extradata'], 0)

    def test_lists(self):
        m = self.m
        self.assertEqual(m.reqs(2), [(220, 5, 0, 0, 0)])
        self.assertEqual(m.reqs(6), [(325, 1, 2, 0, 0)])
        self.assertEqual(idmaps.reqs(m, 2), [(220, 5)])
        self.assertEqual(idmaps.hitconds(m, 0), [([(220, 5)], 25, 0), ([], 10, 0)])
        x = m.tables['extra_move_properties'][0]
        self.assertEqual((x['frame'], x['req'], x['id'], x['value'], x['value2'], x['value5']),
                         (0x8001, 2, 0x8039, 0x501, 7, 10))
        self.assertEqual(idmaps.xps(m, 0), [(0x8001, 0x8039, 0x501), (0, 0, 0)])
        self.assertEqual(idmaps.props(m, 'move_begin_props', 0), [([(0, 0)], 0x8385, 1), ([], 1100, 0)])
        self.assertEqual(m.tables['move_begin_props'][0]['value4'], 4)
        self.assertEqual(idmaps.voices(m, 0), [0x2009986, 0xFFFFFFFF])     # channel << 24 | id, the end
        self.assertEqual(m.tables['voiceclips'][0]['id'], 0x9986)
        self.assertEqual(m.tables['pushbacks'][0], {'duration': 3, 'displacement': 100, 'loops': 1, 'extradata': 0})
        self.assertEqual(m.tables['throw_cameras'][0], {'side': 1, 'camera_data': 0})
        self.assertEqual(m.tables['poses'][0]['move'], 0)
        self.assertEqual(m.tables['parry_related'][0]['value'], city32('XYZ_Co_Other'))

    def test_projectile(self):
        p = self.m.tables['projectiles'][1]
        self.assertEqual((p['effect'], p['speed_fwd'], p['hits'], p['lifetime'], p['radius'], p['height'],
                          p['hitlevel']), (0x3c, 160, 1, 40, 150, 250, 0x217))
        self.assertEqual((p['hit_condition'], p['cancel']), (1, 4))
        w = struct.unpack('<42I', p['raw'])                      # Tekken 7's row
        self.assertEqual((w[0], w[7], w[9], w[10], w[12], w[13], w[14]), (0x3c, 160, 1, 40, 150, 250, 0x217))
        self.assertEqual(w[21], 0x7000010)                        # the sound on hit: bank << 24 | id
        self.assertEqual((w[24] | w[25] << 32, w[26] | w[27] << 32), (1, 4))
        self.assertEqual((w[28], w[29], w[30], w[31]), (0, 1, 300, 250))   # hit width / height: 2 x radius, height
        empty = self.m.tables['projectiles'][0]
        self.assertEqual((empty['hit_condition'], empty['cancel']), (None, None))
        self.assertEqual(struct.unpack('<4I', empty['raw'][96:112]), (0xFFFFFFFF,) * 4)

    def test_bank_and_anim_ref(self):
        m = self.m
        own = motbin.Bank(bank([([(100, 0x1000, 0, [1 << 5]), (101, 0, 0, []), (102, 0, 0, []), (103, 0, 0, [])],
                                 [100, 101, 102, 103])]))
        com = motbin.Bank(bank([([(101, 0x2000, 0, [1 << 5]), (102, 0x3000, 0, [1 << 6])], [])]))
        with self.assertRaises(ValueError):
            m.anim_ref(0)
        m.attach_banks(own, com)
        self.assertEqual(m.anim_ref(0), (100, 'own'))
        self.assertEqual(m.anim_ref(1), (101, 'com'))             # the common bank, for roster id 5 (mask bit 5)
        self.assertEqual(m.anim_ref(2), (102, None))              # in the common bank for another fighter only
        self.assertEqual(m.anim_ref(3), (103, None))              # (the flag bit 0x4000 is no part of the index)
        m.set_anim_lengths(lambda key, where: 59)
        self.assertEqual(m.tables['moves'][0]['anim_len'], 60)
        self.assertEqual(m.tables['moves'][2]['anim_len'], 0)

    def test_bank_errors(self):
        with self.assertRaises(InputError):
            motbin.Bank(b'\0' * 16)
        b = bank([([(1, 2, 0, [])], [1])])
        with self.assertRaises(InputError):
            motbin.Bank(b[:-4])

    def test_bad_files(self):
        with self.assertRaises(InputError):
            motbin.read(b'\0' * 0x400, self.fields, CODE)
        fixed = bytearray(self.data)
        fixed[2] = 1
        with self.assertRaises(InputError):
            motbin.read(bytes(fixed), self.fields, CODE)
        with self.assertRaises(InputError):
            motbin.read(self.data[:-0x100], self.fields, CODE)
        with self.assertRaises(InputError):
            motbin.read(self.data, None, CODE)
        with self.assertRaises(InputError):
            motbin.read(self.data, self.fields[:-24], CODE)
        wrong = bytearray(self.fields)
        struct.pack_into('<I', wrong, 8, 0x10)
        with self.assertRaises(InputError):
            motbin.read(self.data, bytes(wrong), CODE)


if __name__ == '__main__':
    unittest.main()
