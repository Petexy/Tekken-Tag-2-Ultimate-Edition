"""Unit tests of the cancel and requirement rules of a Tekken 8 fighter's conversion (convert/moveset.py): the latches
(LATCHES: Tekken 8's per-move variables 1..4 = TTT2's 313..316 / 0x8096..), the contact test 43, the throw-break
state (460 / 461), and the donor rows the fighter's own list answers (OWN_INPUT), on made-up tables.

    python3 -m pytest -q tools/characters/tests/test_tekken8_cancels.py
"""
import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import Source8, converter, converted  # noqa: E402
from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402
from ttt2char.movesets import Moveset  # noqa: E402

TAG = 0x40000100


class Latches(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        # the id maps' own (wrong) pairs of the latches: the overrides win
        self.c = converter(self.k, req={0: 0, 358: 313, 360: 313, 0x80cb: 0x8096, 131: 129, 44: 46})

    def conv(self, *rows):
        start, ok = self.c.conv_reqs(self.k.req(*rows))
        return converted(self.c, start) if ok else None

    def test_latch_tests(self):
        """358..361 test the latches 1..4 (hellsweep, 2: `[(358, 1), (359, 0)] -> d/f+4,2`)."""
        self.assertEqual(self.conv((358, 1), (359, 0)), [(313, 1), (314, 0)])
        self.assertEqual(self.conv((360, 2)), [(315, 2)])
        self.assertEqual(self.conv((361, 0)), [(316, 0)])

    def test_latch_actions(self):
        """0x80c5 + 3k (+1, +2) set (add to, subtract from) latch k; in requirement lists and as properties."""
        self.assertEqual(self.conv((358, 0), (0x80c5, 1)), [(313, 0), (0x8096, 1)])
        self.assertEqual(self.conv((359, 0), (0x80c8, 1)), [(314, 0), (0x8099, 1)])
        self.assertEqual(self.conv((360, 0), (0x80cb, 1), (0x80cf, 2)), [(315, 0), (0x809c, 1), (0x80a0, 2)])
        self.assertEqual(self.c.map_prop(0x80d0), 0x80a1)

    def test_variable_value_forms(self):
        """476 (variable, value) and 0x8152..0x8154 (variable, value): latches 1..4; the others never set (0)."""
        self.assertEqual(self.conv((476, 2, 1), (0x8152, 2, 2)), [(314, 1), (0x8099, 2)])
        self.assertEqual(self.conv((0x8153, 4, 3), (0x8154, 1, 1)), [(0x80a0, 3), (0x8098, 1)])
        self.assertEqual(self.conv((476, 16, 0)), [])                     # variable 16: always 0, true
        self.assertIsNone(self.conv((476, 16, 1)))
        self.assertEqual(self.c.stats['latch tests and actions (variable, value) -> TTT2\'s latches'], 4)

    def test_contact_and_throw_break(self):
        self.assertEqual(self.conv((43, 0)), [(46, 0)])                    # 44 without its bit-3 condition
        self.assertEqual(self.conv((461, 0), (131, 0)), [(129, 0)])        # the break window everyone has
        self.assertIsNone(self.conv((460, 0), (131, 0)))

    def test_tekken7_unchanged(self):
        self.assertNotIn(358, moveset.REQ_OVERRIDE['t7'])
        self.assertNotIn(43, moveset.REQ_OVERRIDE['t7'])
        self.assertNotIn(0x80c5, moveset.PROP_OVERRIDE['t7'])
        self.assertFalse(moveset.OWN_INPUT['t7'])


def row(direction, button, move_id=0, req=None):
    return dict(direction=direction, button=button, req=req, extradata=None, win_start=1, win_end=32767,
                start_frame=1, move_id=move_id, option=0)


class Donor(Moveset):
    """A made-up TTT2 donor: moves by name, cancel and group lists."""
    game = 'ttt2'

    def __init__(self, names):
        self.names = list(names)
        self.tables = collections.defaultdict(list)
        self.tables['moves'] = [dict(cancel=None) for _ in self.names]

    def move_name(self, i):
        return self.names[i]


class OwnInput(unittest.TestCase):
    """OWN_INPUT: a Tekken 8 fighter's hub gets only the donor's TTT2-only rows its own list does not answer."""

    def setUp(self):
        self.d = Donor(['stance', 'Co_jplp00F', 'Co_StChgOutF', 'Ju_SUPER_0', 'her_9LP', 'her_SUPER'])
        dg = self.d.tables['group_cancels']
        # a TTT2-only group: u/f+1 jump punch, the Tag button, 1+2+3+4
        dg += [row(0x200, 0x40000001, 1), row(0, TAG, 2), row(0, 0x4000000f, 3), row(M.GROUP_END, 0)]
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k)
        self.c.d = self.d
        self.c.T = {'group_cancels': [dict(r) for r in dg], 'cancels': [], 'moves': self.d.tables['moves']}
        self.c.ttt2_only_generic = {'Co_jplp00F', 'Co_StChgOutF', 'Ju_SUPER_0'}

    def merged(self, own, donor):
        out = self.c.merge_donor_extras(own + [row(M.LIST_END, 0)], donor + [row(M.LIST_END, 0)])
        return out[:-1]

    def test_answered(self):
        answered = self.c.answered_by([row(0x200 | 0x100, 0x40000001), row(0, 0x4000000f), row(M.LIST_END, 0)])
        self.assertTrue(answered(row(0x200, 0x40000001)))       # u/f+1: her u/f, u rows
        self.assertFalse(answered(row(0x80, 0x40000001)))       # u/b+1: not hers
        self.assertTrue(answered(row(0x10, 0x4000000f)))        # her 1+2+3+4 has every direction
        self.assertFalse(answered(row(0, TAG)))                 # Tekken 8 has no Tag
        self.assertFalse(answered(row(0, 0)))                   # automatic rows stay

    def test_group_filtered(self):
        own = [row(0x200, 0x40000001, 4), row(0, 0x4000000f, 5)]
        out = self.merged(own, [row(M.GROUP, 0, 0)])
        groups = [r for r in out if r['direction'] == M.GROUP]
        self.assertEqual(len(groups), 1)
        g = groups[0]['move_id']
        rows = []
        while self.c.T['group_cancels'][g]['direction'] != M.GROUP_END:
            rows.append(self.c.T['group_cancels'][g])
            g += 1
        self.assertEqual([(r['direction'], r['button'], r['move_id']) for r in rows], [(0, TAG, 2)])
        self.assertEqual(self.c.stats['donor rows the fighter answers itself, left out (OWN_INPUT)'], 2)

    def test_group_kept_whole(self):
        out = self.merged([row(0x8, 0x40000004, 4)], [row(M.GROUP, 0, 0)])
        self.assertEqual([r['move_id'] for r in out if r['direction'] == M.GROUP], [0])

    def test_plain_rows(self):
        out = self.merged([row(0x200, 0x40000001, 4)], [row(0x200, 0x40000001, 1), row(0, TAG, 2)])
        self.assertEqual([(r['button'], r['move_id']) for r in out], [(TAG, 2), (0x40000001, 4)])

    def test_tekken7_keeps_every_row(self):
        self.c.game = 't7'
        out = self.merged([row(0x200, 0x40000001, 4)], [row(0x200, 0x40000001, 1)])
        self.assertEqual([r['move_id'] for r in out], [1, 4])


if __name__ == '__main__':
    unittest.main()
