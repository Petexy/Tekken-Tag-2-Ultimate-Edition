"""A command list walked out of a converted moveset (convert/movelist_rows.py), on synthetic movesets."""
import struct
import unittest

from ttt2char.convert import movelist_rows as R

END = 690                                # TTT2's requirement list end
GROUP, GROUP_END, LIST_END = 0x800B, 0x800C, 0x8000


class Moveset:
    """A synthetic TTT2 moveset in the readers' form: tables of rows, aliases (slot 1: the stance)."""

    def __init__(self):
        self.T = {'moves': [], 'cancels': [], 'group_cancels': [], 'requirements': [], 'input_sequences': [],
                  'inputs': []}
        self.stance = self.move([])
        self.aliases = [0, self.stance]

    def req(self, conditions=((0, 0),)):
        i = len(self.T['requirements'])
        self.T['requirements'] += [dict(condition=c, param=p) for c, p in conditions]
        self.T['requirements'].append(dict(condition=END, param=0))
        return i

    def row(self, direction, button, target, reqs=((0, 0),), window=(1, 32767), start=1):
        return dict(direction=direction, button=button, req=self.req(reqs), extradata=None, win_start=window[0],
                    win_end=window[1], start_frame=start, move_id=target, option=0)

    def move(self, rows, anim_len=60, end=1):
        i = len(self.T['moves'])
        self.T['moves'].append(dict(cancel=None, anim_len=anim_len))
        self.set_rows(i, rows, end)
        return i

    def set_rows(self, i, rows, end=1):
        """The move's cancel list: rows, then the list's end (back to the stance from frame `end`)."""
        self.T['moves'][i]['cancel'] = len(self.T['cancels'])
        self.T['cancels'] += rows + [self.row(LIST_END, 0, self.aliases[1] if hasattr(self, 'aliases') else 0,
                                              window=(end, 32767), start=end)]

    def group(self, rows):
        i = len(self.T['group_cancels'])
        self.T['group_cancels'] += rows + [self.row(GROUP_END, 0, 0)]
        return self.row(GROUP, 0, i)

    def sequence(self, inputs, window=20):
        k = len(self.T['input_sequences'])
        self.T['input_sequences'].append(dict(s_00=0, window=window, amount=len(inputs),
                                              inputs=len(self.T['inputs'])))
        self.T['inputs'] += [dict(direction=d, button=b) for d, b in inputs]
        return R.SEQ0 + k


def read_mvlt(m):
    """(header, entries [{strings, demo, count, kind, icons}], demos [(setup, inputs [bytes])]) of TTT2 MVLT bytes."""
    magic, version, sub, n, nd, so, eo, do, io = struct.unpack_from('>4sHHIIIIII', m, 0)
    entries = []
    for i in range(n):
        b = eo + 92 * i
        offsets = struct.unpack_from('>12I', m, b)
        demo, count, kind, demo_kind = struct.unpack_from('>HHHH', m, b + 64)
        icons = struct.unpack_from('>HH', m, b + 84)
        entries.append(dict(strings=[m[so + o:m.index(b'\0', so + o)].decode('utf-8') for o in offsets], demo=demo,
                            count=count, kind=kind, demo_kind=demo_kind, icons=icons))
    demos = []
    for i in range(nd):
        r = struct.unpack_from('>8HI', m, do + 20 * i)
        demos.append((list(r[:7]), [m[io + 4 * k:io + 4 * k + 4] for k in range(r[8], r[8] + r[7])]))
    return (magic, version, sub, n, nd), entries, demos


ONE, TWO, THREE, FOUR = 1, 2, 4, 8
ONLY = 0x40000000


def glyphs(*parts):
    """Command text from parts: ('d', n) a direction glyph U+E000 + n, ('b', mask) a button glyph U+E014 + mask."""
    return ''.join(chr((0xE000 if kind == 'd' else 0xE014) + n) for kind, n in parts)


def frames(inputs):
    """The demo frame of each input with buttons or a stick, by its bytes."""
    out, at = [], 0
    for x in inputs:
        if x[0] or x[1]:
            out.append((at, bytes(x)))
        at += x[2]
    return out


class Walked(unittest.TestCase):
    def setUp(self):
        self.ms = Moveset()
        self.logs = []

    def stance_rows(self, rows):
        self.ms.set_rows(self.ms.stance, rows)

    def walk(self, commands, bounds=None):
        names = {}

        def index_of(ref):
            return names.get(ref)
        for x in commands:
            if not isinstance(x, str):
                names[x[0]] = x[0] if isinstance(x[0], int) else None
        entries = R.entries_of(commands, index_of, log=self.logs.append)
        out = R.convert(self.ms.T, self.ms.aliases, entries, log=self.logs.append, bounds=bounds)
        return read_mvlt(out) if out is not None else None

    def test_press_from_the_stance(self):
        jab = self.ms.move([])
        kick = self.ms.move([], anim_len=200)
        self.stance_rows([self.ms.row(0, ONLY | ONE, jab), self.ms.row(0x8, ONLY | THREE | FOUR, kick)])
        header, entries, demos = self.walk([(jab, 'Jab'), (kick, 'Low Kick')])
        self.assertEqual(header[:5], (b'MVLT', 2, 0, 2, 2))
        self.assertEqual(entries[0]['strings'], ['Jab'] * 3 + [glyphs(('b', ONE))] * 9)
        self.assertEqual(entries[1]['strings'][3], glyphs(('d', 2), ('b', THREE | FOUR)))     # d/f+3+4
        self.assertEqual(entries[1]['strings'][1], 'Low Kick')
        self.assertEqual((entries[0]['kind'], entries[0]['demo'], entries[0]['count'], entries[0]['demo_kind']),
                         (0, 0, 1, 1))
        setup, inputs = demos[1]
        self.assertEqual(setup, [0, R.DISTANCE, 0, 0, 0, 0, 0])
        self.assertEqual(inputs[0], bytes([0x60, 0x60, 1, 2]))            # 3+4 with d/f, two glyphs lit
        self.assertEqual(sum(x[2] for x in inputs[1:]), 200 + R.END - 1)  # the move's end, then END frames
        self.assertEqual(sum(x[2] for x in demos[0][1][1:]), R.TAIL)      # (a short move: TAIL)

    def test_the_first_row_that_fits_takes_the_press(self):
        any4, f4 = self.ms.move([]), self.ms.move([])
        jump_punch, rising = self.ms.move([]), self.ms.move([])
        self.stance_rows([self.ms.row(0, ONLY | FOUR, any4, reqs=((214, 0),)),     # a player's row: takes f+4 too
                          self.ms.row(0x40, ONLY | FOUR, f4),
                          self.ms.row(0x100, ONLY | ONE, jump_punch, reqs=((69, 0),)),     # unknown: passes it on
                          self.ms.row(0x100, ONLY | ONE, rising)])
        header, entries, demos = self.walk([(any4, 'Burst'), (f4, 'Step Kick'), (rising, 'Rising Claw')])
        self.assertEqual([x['strings'][1] for x in entries], ['Burst', 'Rising Claw'])
        self.assertEqual(entries[0]['strings'][3], glyphs(('b', FOUR)))       # any direction: shown neutral
        self.assertEqual(entries[1]['strings'][3], glyphs(('d', 6), ('b', ONE)))
        self.assertTrue(any('Step Kick' in s and 'left out' in s for s in self.logs))

    def test_rows_false_in_practice_are_not_walked(self):
        cpu, item, kick = self.ms.move([]), self.ms.move([]), self.ms.move([])
        self.stance_rows([self.ms.row(0, ONLY | FOUR, cpu, reqs=((214, 1),)),
                          self.ms.row(0, ONLY | FOUR, item, reqs=((459, 29),)),
                          self.ms.row(0, ONLY | FOUR, kick)])
        header, entries, demos = self.walk([(cpu, 'CPU'), (item, 'Item'), (kick, 'Kick')])
        self.assertEqual([x['strings'][1] for x in entries], ['Kick'])

    def test_the_plainest_input_is_shown(self):
        claw = self.ms.move([])
        self.stance_rows([self.ms.group([self.ms.row(0x200, ONLY | THREE, claw), self.ms.row(0x2, ONLY | ONE, claw),
                                         self.ms.row(0x380, ONLY | THREE, claw)]),
                          self.ms.row(0x100, ONLY | ONE | TWO, claw)])
        header, entries, demos = self.walk([(claw, 'Claw')])
        self.assertEqual(entries[0]['strings'][3], glyphs(('d', 0), ('b', ONE)))     # d/b before u, u/f, u/b
        self.ms.set_rows(self.ms.stance, [self.ms.group([self.ms.row(0x200, ONLY | THREE, claw),
                                                         self.ms.row(0x380, ONLY | THREE, claw)]),
                                          self.ms.row(0x100, ONLY | ONE | TWO, claw)])
        header, entries, demos = self.walk([(claw, 'Claw')])
        self.assertEqual(entries[0]['strings'][3], glyphs(('d', 6), ('b', THREE)))   # u, fewer buttons

    def test_strings_wait_for_the_move_the_last_press_began(self):
        three = self.ms.move([], anim_len=40)
        two = self.ms.move([self.ms.row(0, ONLY | ONE, three, window=(1, 20))], anim_len=50)
        one = self.ms.move([self.ms.row(0, ONLY | TWO, two, window=(1, 29), start=29)])
        self.stance_rows([self.ms.row(0, ONLY | ONE, one)])
        header, entries, demos = self.walk([(one, 'Claw'), (two, 'Claw Combo'), (three, 'Claw Rush')])
        self.assertEqual(entries[2]['strings'][3], glyphs(('b', ONE), ('b', TWO), ('b', ONE)))
        presses = frames(demos[2][1])
        # 1 at once, 2 at the first move's frame 7 (it goes on at its frame 29), 1 at the second move's frame 7
        self.assertEqual([at for at, _ in presses], [0, 6, 28 + 6])
        self.assertEqual([x[3] for _, x in presses], [1, 1, 1])

    def test_automatic_rows_are_followed(self):
        pillar = self.ms.move([])
        punch = self.ms.move([self.ms.row(0, 0, pillar, window=(25, 25), start=25)])
        self.stance_rows([self.ms.row(0, ONLY | ONE, punch)])
        header, entries, demos = self.walk([(pillar, 'Crystal Pillar')])
        self.assertEqual(entries[0]['strings'][3], glyphs(('b', ONE)))

    def test_a_dash_and_its_follow_up_holding_forward(self):
        dash_claw, dash_punch = self.ms.move([]), self.ms.move([])
        dash = self.ms.move([self.ms.row(0x40, ONLY | ONE, dash_claw, window=(1, 20)),
                             self.ms.row(0x20, ONLY | TWO, dash_punch, window=(1, 20))])
        self.stance_rows([self.ms.row(R.DASH_FORWARD, 0, dash)])
        header, entries, demos = self.walk([(dash_claw, 'Dash Claw'), (dash_punch, 'Dash Punch')])
        self.assertEqual(entries[0]['strings'][3], glyphs(('d', 4), ('d', 12), ('b', ONE)))     # f,F+1
        self.assertEqual(entries[1]['strings'][3], glyphs(('d', 4), ('d', 4), ('b', TWO)))      # f,f 2
        self.assertEqual(demos[0][1][:4], [bytes([0, 0x20, 1, 1]), bytes([0, 0, 1, 0]), bytes([0, 0x20, 1, 1]),
                                           bytes([0x80, 0x20, 1, 1])])
        self.assertEqual(entries[0]['icons'], (0, 0))

    def test_an_input_sequence(self):
        throw = self.ms.move([])
        seq = self.ms.sequence([(0x20, 0x80000000), (0x40, 0x80000000), (0x20, 0x80000000), (0x40, ONLY | 3)])
        self.stance_rows([self.ms.row(seq, 0, throw)])
        header, entries, demos = self.walk([(throw, 'Crushing Ascent')])
        self.assertEqual(entries[0]['strings'][3], glyphs(('d', 4), ('d', 4), ('b', ONE | TWO)))   # f,f+1+2
        self.assertEqual(demos[0][1][:4], [bytes([0, 0, 1, 0]), bytes([0, 0x20, 1, 1]), bytes([0, 0, 1, 0]),
                                           bytes([0x90, 0x20, 1, 2])])

    def test_distance_tests_at_the_demo_distance(self):
        far, near = self.ms.move([]), self.ms.move([])
        self.stance_rows([self.ms.row(0x100, ONLY | THREE | FOUR, far, reqs=((36, 4000),)),
                          self.ms.row(0x100, ONLY | THREE | FOUR, near, reqs=((35, 3500),))])
        header, entries, demos = self.walk([(near, 'Warp'), (far, 'Long Warp', {'distance': 5000})])
        self.assertEqual([x['strings'][1] for x in entries], ['Warp', 'Long Warp'])
        self.assertEqual([d[0][1] for d in demos], [R.DISTANCE, 5000])
        self.assertIsNone(self.walk([(far, 'Long Warp')]))           # (at the demo's 2 m: none)
        self.assertTrue(any('Long Warp' in s and 'left out' in s for s in self.logs))

    def test_throws_are_shown_closer(self):
        held = self.ms.move([], anim_len=50)
        throw = self.ms.move([self.ms.row(0, 0, held, reqs=((5, 2500),), window=(14, 17), start=14)], anim_len=0,
                             end=39)
        dash_throw = self.ms.move([self.ms.row(0, 0, held, reqs=((3, 2500),), window=(14, 17), start=14)])
        jab = self.ms.move([], anim_len=20)
        self.stance_rows([self.ms.row(0, ONLY | ONE | THREE, throw), self.ms.row(0x40, ONLY | ONE | TWO, dash_throw),
                          self.ms.row(0, ONLY | ONE, jab)])
        header, entries, demos = self.walk([(throw, 'Throw'), (dash_throw, 'Far Throw', {'distance': 1500}),
                                            (jab, 'Jab')])
        self.assertEqual([d[0][1] for d in demos], [R.THROW_DISTANCE, 1500, R.DISTANCE])
        self.assertEqual(sum(x[2] for x in demos[1][1][1:]), R.LONG_TAIL)       # (a throw by f+1+2 waits too)
        self.assertEqual(sum(x[2] for x in demos[2][1][1:]), R.TAIL)

    def test_situational_rows_are_walked_and_logged(self):
        finish = self.ms.move([])
        kick = self.ms.move([self.ms.row(0, ONLY | FOUR, finish, reqs=((81, 0),))])
        self.stance_rows([self.ms.row(0, ONLY | THREE, kick)])
        header, entries, demos = self.walk([(finish, 'Kick Combo')])
        self.assertEqual(entries[0]['strings'][3], glyphs(('b', THREE), ('b', FOUR)))
        self.assertTrue(any('Kick Combo' in s and '81' in s for s in self.logs))

    def test_titles_and_missing_moves(self):
        jab = self.ms.move([])
        self.stance_rows([self.ms.row(0, ONLY | ONE, jab)])
        header, entries, demos = self.walk(['Strikes', ('key:0a1b2c3d', 'Gone'), (jab, 'Jab'), 'Throws'])
        self.assertEqual([x['kind'] for x in entries], [8, 0])                # the empty title line left out
        self.assertEqual(entries[0]['strings'][1], '    ■ Strikes ■')
        self.assertEqual(entries[0]['demo'], 0xFFFF)
        self.assertTrue(any('key:0a1b2c3d' in s for s in self.logs))

    def test_nothing_to_show(self):
        jab = self.ms.move([])
        self.assertIsNone(self.walk(['Strikes', (jab, 'Jab')]))

    def test_bound_icons_and_throw_waits(self):
        two = self.ms.move([], anim_len=40)
        one = self.ms.move([self.ms.row(0, ONLY | TWO, two, window=(1, 29))])
        throw = self.ms.move([], anim_len=60)
        self.stance_rows([self.ms.row(0, ONLY | ONE, one), self.ms.row(0, ONLY | ONE | THREE, throw)])
        walked = []

        def bounds(presses):
            walked.append(presses)
            return {2: True} if len(presses) == 2 else {}
        header, entries, demos = self.walk([(two, 'Combo'), (throw, 'Throw')], bounds=bounds)
        self.assertEqual(entries[0]['icons'], (0, 2 << 8))
        self.assertEqual(walked[0], [(0x20, ONE, 0), (0x20, TWO, 6)])
        self.assertEqual(sum(x[2] for x in demos[1][1][1:]), R.LONG_TAIL)

    def test_the_demo_waits_for_the_moves_after_the_last_press(self):
        held = self.ms.move([], anim_len=0, end=300)           # (converted moves: no length, the list's end row's)
        throw = self.ms.move([self.ms.row(0, 0, held, reqs=((3, 2500),), window=(14, 17), start=14)],
                             anim_len=0, end=39)
        self.stance_rows([self.ms.row(0, ONLY | ONE | TWO, throw)])
        header, entries, demos = self.walk([(throw, 'Lifting Throw')])
        self.assertEqual(sum(x[2] for x in demos[0][1][1:]), 13 + 300 - 1 + R.END)



class References(unittest.TestCase):
    """importer._command_ref: a COMMANDS reference -> the converted moveset's move"""

    def test_keys_names_and_moves_the_donor_took(self):
        from types import SimpleNamespace
        from ttt2char import importer
        moves = [{'name_key': 0x11111111}, {'name_key': 0x22222222}, {'name_key': 0x33333333}]
        names = ['Own_move', 'ThrowGeneric', 'Dropped']
        c = SimpleNamespace(k=SimpleNamespace(tables={'moves': moves}), kn={n: i for i, n in enumerate(names)},
                            newidx={0: 900}, dn={'ThrowGeneric': 40}, name=lambda i: names[i])
        ref = importer._command_ref(c)
        self.assertEqual(ref('key:11111111'), 900)
        self.assertEqual(ref('Own_move'), 900)
        self.assertEqual(ref('key:22222222'), 40)            # converted into the donor's move of its name
        self.assertIsNone(ref('key:33333333'))               # not converted
        self.assertIsNone(ref('key:44444444'))               # no such move
        self.assertIsNone(ref('Nothing'))


if __name__ == '__main__':
    unittest.main()
