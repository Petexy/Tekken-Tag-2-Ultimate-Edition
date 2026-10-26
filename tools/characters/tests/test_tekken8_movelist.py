"""A Tekken 8 command list -> TTT2's (tekken8/movelist.py), on a made-up MVLT and made-up string tables (no game
files needed).

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char.convert import movelist as ttt2         # noqa: E402
from ttt2char.tekken8 import cityhash, movelist, reflect, zen     # noqa: E402

TEXT_ASSET = '/Script/GryphonLocalization.GryphonTextBinaryAsset'
SCHEMA = {'classes': {TEXT_ASSET: {'name': 'GryphonTextBinaryAsset', 'super': None, 'flags': 0,
                                   'props': [{'n': 'DataSize', 't': 'Int'}]}},
          'structs': {}, 'enums': {}}
HEAT, THROWS = 'TEXT_000_MOVELIST_INDEX_CMN_000', 'TEXT_000_MOVELIST_INDEX_CMN_007'     # section titles


def img(n):
    return '<img id="cmd_%02d"/>' % n


# ---------------------------------------------------------------------------------------------------- builders
def mvlt(entries, demos, inputs, version=5, sub=6):
    """A Tekken 8 MVLT (file form): entries (keys [name, command, reading], kind, demo, count, demo kind, icons),
    demos (setup [7], first input, inputs, rage, state), inputs (4-byte rows {direction, buttons, frames, lit})."""
    strings, at = bytearray(b'\0'), {'': 0}
    for x in entries:
        for k in x['keys']:
            if k not in at:
                at[k] = len(strings)
                strings += k.encode() + b'\0'
    while len(strings) % 4:
        strings.append(0)
    so = 0x28
    eo = so + len(strings)
    do = eo + 372 * len(entries)
    io = do + 24 * len(demos)
    out = bytearray(struct.pack('<4sHHIIIIIIII', b'MVLT', version, sub, len(entries), len(demos), so, eo, do, io,
                                0, 0))
    out += strings
    for x in entries:
        e = bytearray(372)
        offsets = [at[k] if k else 0xFFFFFFFF for k in x['keys']] + [at[x['keys'][1]]] * 9 + [0xFFFFFFFF] * 4
        struct.pack_into('<16I', e, 0, *offsets[:16])
        struct.pack_into('<HHHH', e, 0x44, x.get('demo', 0xFFFF), x.get('count', 1), x.get('kind', 0),
                         x.get('demo_kind', 1))
        struct.pack_into('<I', e, 0x14C, x.get('icons', 0))
        out += e
    for d in demos:
        out += struct.pack('<8HIHH', *d['setup'], d['inputs'], d['first'], d.get('rage', 0), d.get('state', 0))
    for r in inputs:
        out += bytes(r)
    return bytes(out)


def block(records):
    """A string table's 'gbtd' block of {key: text}."""
    out = bytearray(b'gbtd' + struct.pack('<I', 0x40) + bytes(0x38))
    for k, v in records.items():
        kb, vb = k.encode() + b'\0', v.encode() + b'\0'
        kb += bytes(-len(kb) % 4)
        vb += bytes(-len(vb) % 4)
        out += b'text' + struct.pack('<IIIII', 16, len(kb), len(vb), 0x1234, 0x5678) + kb + vb
    return bytes(out)


class Scripts:
    def script_path(self, v):
        return TEXT_ASSET if v == cityhash.script_object_id(TEXT_ASSET) else None


class Store:
    """The part of tekken8.store.Store texts() uses: find(prefix) and package(path), for {path: {key: text}}."""

    def __init__(self, tables):
        self.tables = tables
        self.schema = reflect.Schema(SCHEMA)

    def find(self, prefix):
        return sorted(p for p in self.tables if p.lower().startswith(prefix.lower()))

    def package(self, path):
        b = block(self.tables[path])
        data = struct.pack('<Hi', 0x200 | 0x100, len(b)) + b'\0\0\0\0' + b      # DataSize, the GUID flag, the block
        name = '/Game/' + path.split('/Content/', 1)[1].rsplit('.', 1)[0]
        cls = synth.script_index(cityhash.script_object_id(TEXT_ASSET))
        return zen.Package(synth.zen_package(name, [{'name': name.rsplit('/', 1)[1], 'cls': cls, 'data': data}],
                                             imports=[cls]), path, resolver=Scripts(), store=self)


def read_ttt2(m):
    """-> (entries {strings, demo, count, kind, demo_kind, icons}, demos (setup, inputs, first), input rows)."""
    magic, ver, _, n, nd, so, eo, do, io = struct.unpack_from('>4sHHIIIIII', m, 0)
    assert (magic, ver) == (b'MVLT', 2)
    entries = []
    for i in range(n):
        b = eo + 92 * i
        offs = struct.unpack_from('>12I', m, b)
        demo, count, kind, demo_kind, _, _, _, i1, i2, _ = struct.unpack_from('>HHHH3IHHI', m, b + 64)
        entries.append(dict(strings=[m[so + o:m.index(b'\0', so + o)].decode() for o in offs], demo=demo, count=count,
                            kind=kind, demo_kind=demo_kind, icons=(i1, i2)))
    demos = [struct.unpack_from('>8HI', m, do + 20 * i) for i in range(nd)]
    return entries, [(list(d[:7]), d[7], d[8]) for d in demos], [m[k:k + 4] for k in range(io, len(m), 4)]


# ---------------------------------------------------------------------------------------------------- tests
class Texts(unittest.TestCase):
    def test_glyphs(self):
        t = movelist.text
        self.assertEqual(t(img(3) + img(10) + img(11) + img(18)), '')    # d/b u/f, held
        self.assertEqual(t(img(20) + img(21) + img(23) + img(27) + img(34)), '')
        self.assertEqual(t(img(7) + img(35) + img(4) + img(5) + img(21)), '☆')
        self.assertEqual(t('{cmd_01}%s%s{cmd_02}' % (img(21), img(20))), '【】')
        self.assertEqual(t('%s {cmd_38} during Sentai %s' % (img(23), img(21))),
                         '' + ttt2.ARROW + 'during Sentai ')                  # TTT2: no spaces around
        for left, why in ((img(25), 'need Heat or Rage'), ('{gui_bank0_heat}', 'need Heat or Rage'),
                          ('{gui_rb}', 'need Heat or Rage'), (img(19), 'unknown glyphs'), (img(36), 'unknown glyphs'),
                          ('{cmd_9}', 'unknown glyphs')):
            with self.assertRaises(movelist.LeftOut) as e:
                t('During Heat ' + left)
            self.assertEqual(e.exception.args[0], why)

    def test_records(self):
        b = block({'TEXT_A': 'Muso Basara', 'TEXT_B': '無双伐折羅', 'TEXT_C': 'x'})
        self.assertEqual(movelist.text_records(b), {'TEXT_A': 'Muso Basara', 'TEXT_B': '無双伐折羅', 'TEXT_C': 'x'})
        self.assertEqual(movelist.text_records(b, {'TEXT_B'}), {'TEXT_B': '無双伐折羅'})
        with self.assertRaises(ValueError):
            movelist.text_records(b'dtbg' + b[4:])
        with self.assertRaises(ValueError):
            movelist.text_records(b[:-3])                                        # a record cut short

    def test_tables(self):
        en, ja = 'Polaris/Content/Localize/en/', 'Polaris/Content/Localize/ja/'
        s = Store({en + 'GTB_Movelist.uasset': {'K1': 'one', 'K2': 'two', 'K9': 'not asked'},
                   en + 'GTB_Upd_200_Character.uasset': {'K3': 'three'},
                   en + 'GTB_Upd_003_System.uasset': {'K2': 'two again', 'K4': 'four'},
                   en + 'GTB_System.uasset': {'K5': 'another table'},
                   ja + 'GTB_Movelist.uasset': {'K1': 'いち'}})
        got = movelist.texts(s, {'K1', 'K2', 'K3', 'K4', 'K5'}, log=lambda line: None)
        self.assertEqual(got, {'en': {'K1': 'one', 'K2': 'two again', 'K3': 'three', 'K4': 'four'},
                               'ja': {'K1': 'いち'}})                            # updates after the base, by name


class Convert(unittest.TestCase):
    def setUp(self):
        self.texts = {
            'en': {'T_NORMAL': 'Normal Moves', 'N_FLASH': 'Flash Punch Combo', 'C_FLASH': img(20) * 2 + img(21),
                   'N_PARRY': 'Fusatsujin', 'C_PARRY': 'Time with punch %s%s' % (img(7), img(35)),
                   HEAT: 'Heat Moves', 'N_ENGAGER': 'Muso Basara', 'C_ENGAGER': img(5) + img(20) + img(21),
                   'N_BURST': 'Heat Burst', 'C_BURST': 'When Heat activation available ' + img(25),
                   'N_ART': 'Rage Art', 'C_ART': 'During Rage ' + img(5) + img(22),
                   'T_EMPTY': 'Moves While Down', THROWS: 'Throws', 'N_THROW': 'Gekka Hyojin',
                   'C_THROW': 'Approach opponent ' + img(24), 'N_NOTE': 'Throws', 'C_NOTE': img(24),
                   'N_DRILL': 'Flash Punch Combo', 'N_NONE': 'Ghost'},
            'ja': {'T_NORMAL': '通常技', 'N_FLASH': '閃光烈拳', 'R_FLASH': 'せんこうれっけん',
                   'C_PARRY': 'パンチ攻撃に合わせて %s%s' % (img(7), img(35))},
            'fr': {'C_PARRY': 'Avec un coup de poing %s%s' % (img(7), img(35)), 'T_NORMAL': 'Coups normaux'}}
        entries = [dict(keys=['', 'T_NORMAL', ''], kind=8),
                   dict(keys=['N_FLASH', 'C_FLASH', 'R_FLASH'], demo=0, icons=0x01000300),    # homes, tornado 3rd
                   dict(keys=['N_PARRY', 'C_PARRY', ''], demo=1),
                   dict(keys=['N_NONE', 'C_NONE', ''], demo=0),                              # no command text
                   dict(keys=['N_BURST', 'C_BURST', ''], demo=0),                            # 2+3: Heat Burst
                   dict(keys=['N_ART', 'C_ART', ''], demo=2),                                # needs Rage
                   dict(keys=['', HEAT, ''], kind=8),                                        # all left out
                   dict(keys=['N_ENGAGER', 'C_ENGAGER', ''], demo=0),
                   dict(keys=['', 'T_EMPTY', ''], kind=8),                                   # heads nothing
                   dict(keys=['', THROWS, ''], kind=8),
                   dict(keys=['N_THROW', 'C_THROW', ''], demo=0),
                   dict(keys=['N_DRILL', 'C_FLASH', ''], demo=0, kind=15),                   # a drill: the list ends
                   dict(keys=['N_NOTE', 'C_NOTE', ''])]                                      # Arcade Quest's notes
        demos = [dict(setup=[0, 1500, 0, 0, 0, 0, 0], first=0, inputs=4),
                 dict(setup=[8, 1800, 0, 0, 0, 0, 0], first=4, inputs=2),                  # the opponent punches
                 dict(setup=[0, 1800, 0, 0, 0, 0, 0], first=0, inputs=1, rage=1)]
        inputs = [(0, 0x80, 1, 1), (0, 0, 5, 0), (0x60, 0x10, 1, 2), (0, 0, 1, 0), (0x20, 0, 1, 1), (0, 0, 1, 0)]
        self.mvl = mvlt(entries, demos, inputs)

    def test_convert(self):
        lines = []
        out = movelist.convert(self.mvl, None, log=lines.append, texts_by_language=self.texts)
        entries, demos, rows = read_ttt2(out)
        self.assertEqual([x['strings'][1] for x in entries],
                         ['    ■ Normal Moves ■', 'Flash Punch Combo', 'Fusatsujin', '    ■ Throws ■', 'Gekka Hyojin'])
        self.assertIn('left out: 1 drills, 1 Tekken 8 practice data, 2 in the Heat and Rage sections, 2 need Heat or '
                      'Rage, 1 no text, 1 empty title lines', lines[0])
        title, flash, parry, _, throw = entries
        self.assertEqual(title['strings'][:5], ['    ■ 通常技 ■', '    ■ Normal Moves ■', '    ■ 通常技 ■', '', ''])
        self.assertEqual(title['strings'][5], '    ■ Coups normaux ■')                   # fr
        self.assertEqual(title['strings'][6], '    ■ Normal Moves ■')                    # it: none, the English
        self.assertEqual((title['demo'], title['count'], title['kind']), (0xFFFF, 0, 8))
        self.assertEqual(flash['strings'][:5], ['閃光烈拳', 'Flash Punch Combo', 'せんこうれっけん', '',
                                                ''])
        self.assertEqual(flash['icons'], (0, 0x300))                                      # the tornado: TTT2's bound
        self.assertEqual(parry['strings'][:6], ['Fusatsujin', 'Fusatsujin', 'Fusatsujin', 'パンチ攻撃に合わせて ☆',
                                                'Time with punch ☆', 'Avec un coup de poing ☆'])
        # demos: TTT2's input rows {buttons, direction, frames, lit}, a wait after the last
        setup, n, first = demos[flash['demo']]
        self.assertEqual((setup, n), ([0, 1500, 0, 0, 0, 0, 0], 5))
        self.assertEqual(rows[first:first + n], [bytes([0x80, 0, 1, 1]), bytes([0, 0, 5, 0]), bytes([0x10, 0x60, 1, 2]),
                                                 bytes([0, 0, 1, 0]), bytes([0, 0, movelist.TAIL, 0])])
        setup, n, first = demos[parry['demo']]
        self.assertEqual(setup[0], 9)                                                     # punches: TTT2's 9
        self.assertEqual(rows[first + n - 1], bytes([0, 0, movelist.LONG_TAIL, 0]))       # the opponent acts
        setup, n, first = demos[throw['demo']]
        self.assertEqual(rows[first + n - 1], bytes([0, 0, movelist.LONG_TAIL, 0]))       # in the Throws section

    def test_unknown_action(self):
        m = bytearray(self.mvl)
        do = struct.unpack_from('<I', m, 0x18)[0]
        struct.pack_into('<HHHHH', m, do + 24, 18, 1800, 0, 0, 20)                       # not known here
        lines = []
        entries, demos, _ = read_ttt2(movelist.convert(bytes(m), None, lines.append, self.texts))
        self.assertEqual(demos[entries[2]['demo']][0][:5], [0, 1800, 0, 0, 0])            # the opponent stands
        self.assertIn('1 demos\' opponent actions', lines[1])

    def test_none(self):
        lines = []
        self.assertIsNone(movelist.convert(b'MVLT' + bytes(40), None, lines.append, self.texts))
        self.assertIsNone(movelist.convert(None, None, lines.append, self.texts))
        self.assertIsNone(movelist.convert(self.mvl, None, lines.append, {'ja': self.texts['ja']}))  # no English
        only_heat = {'en': {'N_ART': 'Rage Art', 'C_ART': 'During Rage'}}
        self.assertIsNone(movelist.convert(self.mvl, None, lines.append, only_heat))
        self.assertEqual(len(lines), 4)
        with self.assertRaises(ValueError):
            movelist.read(mvlt([], [], [], version=1000))

    def test_from_store(self):
        en = 'Polaris/Content/Localize/en/'
        s = Store({en + 'GTB_Movelist.uasset': self.texts['en'],
                   'Polaris/Content/Localize/ja/GTB_Movelist.uasset': self.texts['ja']})
        a = movelist.convert(self.mvl, s, log=lambda line: None)
        b = movelist.convert(self.mvl, None, log=lambda line: None,
                             texts_by_language={'en': self.texts['en'], 'ja': self.texts['ja']})
        self.assertEqual(a, b)


class BoundIcons(unittest.TestCase):
    """The definition's bounds on the bound icon (bound_hit): the presses of each entry's demo, walked by `bounds`
    (move_overrides.command_bounds; a table here)."""

    def test_icons(self):
        texts = {'en': {'N_D2': 'Tecchuu-ate', 'C_D2': img(4) + img(21),
                        'N_UF4': 'Silver Gleam', 'C_UF4': img(10) + img(27),
                        'N_SEN': 'Rashomon', 'C_SEN': 'During Sentai (%s%s, etc.) %s' % (img(7), img(23), img(21)),
                        'N_DASH': 'Un Tobi Kaijo-geri', 'C_DASH': img(7) + img(7) + img(15) + img(27),
                        'N_STR': 'Gekirosatsu', 'C_STR': img(5) + img(27) + img(21) + img(23)}}
        entries = [dict(keys=['N_D2', 'C_D2', ''], demo=0),
                   dict(keys=['N_UF4', 'C_UF4', ''], demo=1, icons=0x100),          # a tornado made no bound
                   dict(keys=['N_SEN', 'C_SEN', ''], demo=2),                       # the stance's way in first
                   dict(keys=['N_DASH', 'C_DASH', ''], demo=3),                     # a dash: not walked
                   dict(keys=['N_STR', 'C_STR', ''], demo=4, icons=0x300)]          # keeps its tornado
        demos = [dict(setup=[0, 1800, 0, 0, 0, 0, 0], first=f, inputs=n) for f, n in
                 ((0, 2), (2, 2), (4, 4), (8, 4), (12, 4))]
        inputs = [(0x40, 0x10, 1, 1), (0, 0, 1, 0),
                  (0x30, 0x20, 1, 1), (0, 0, 1, 0),
                  (0x20, 0x40, 1, 1), (0, 0, 10, 0), (0, 0x10, 1, 1), (0, 0, 1, 0),
                  (0x20, 0, 1, 0), (0, 0, 1, 0), (0x20, 0x20, 1, 1), (0, 0, 1, 0),
                  (0x60, 0x20, 1, 1), (0, 0x10, 1, 1), (0, 0x80, 1, 1), (0, 0, 1, 0)]
        marks = {((0x4, 2, 0),): {1: True},
                 ((0x200, 8, 0),): {1: False},
                 ((0x40, 4, 0), (0x20, 2, 11)): {2: True},
                 ((0x8, 8, 0), (0x20, 2, 1), (0x20, 1, 2)): {1: True}}
        walked = []

        def bounds(presses):
            walked.append(presses)
            return marks[tuple(presses)]
        out = movelist.convert(mvlt(entries, demos, inputs), None, log=lambda line: None, texts_by_language=texts,
                               bounds=bounds)
        self.assertEqual([x['icons'] for x in read_ttt2(out)[0]], [(0, 0x100), (0, 0), (0, 0x100), (0, 0),
                                                                    (0, 0x300)])
        self.assertEqual(len(walked), 4)                                            # (not the dash)
        plain = movelist.convert(mvlt(entries, demos, inputs), None, log=lambda line: None, texts_by_language=texts)
        self.assertEqual([x['icons'] for x in read_ttt2(plain)[0]], [(0, 0), (0, 0x100), (0, 0), (0, 0), (0, 0x300)])

    def test_presses(self):
        self.assertEqual(movelist.demo_presses([(0x40, 0x10, 1, 1), (0, 0x90, 3, 1), (0, 0, 1, 0)]),
                         [(0x4, 2, 0), (0x20, 1, 1)])                              # 1 joins 2 held: a press of 1
        self.assertIsNone(movelist.demo_presses([(0x60, 0, 1, 0), (0x60, 0x10, 1, 1)]))
        self.assertEqual(movelist.command_presses('During Sentai (%s%s, etc.) %s' % (img(7), img(23), img(21))), 1)
        self.assertEqual(movelist.command_presses(img(20) + img(22) + img(7)), 2)


if __name__ == '__main__':
    unittest.main()
