"""Unit tests of Tekken 8's later recovery on block (BLOCK_RECOVERY8: property 0x8401 with value 1 = value2 frames more
recovery when the move was blocked; convert/moveset.py block_recovery8: a block goes on in a copy of the move with the
later end row, as TTT2's own Lw_2RLKiCDE -> Lw_2RLKiCDE_G), on made-up tables.

    python3 -m unittest tools/characters/tests/test_tekken8_block_recovery.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import converter, converted  # noqa: E402
from test_tekken8_flags import Flags8, flagged, row  # noqa: E402
from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import moveset, tagcombo, tagsystem  # noqa: E402

RECOVERY = 0x8401


class BlockRecovery(unittest.TestCase):
    def setUp(self):
        self.k = Flags8(refs=[(0, 'own')] * 3)
        self.k.tables['cancel_extras'] = [dict(value=0x80)]
        self.c = flagged(converter(self.k, req={0: 0}), {})
        self.c.strings, self.c.str_off = b'', {}

    def move(self, *props, rows=(), end=54, active=(19, 20)):
        """Tekken 8 move 2 with start properties `props` ((id, value, value2)) and a cancel list of `rows` and an end
        row at `end`, converted as move 0 of the TTT2 tables (active frames `active`)."""
        mv = self.k.tables['moves'][2]
        mv['extraprops'] = self.k.props(*[(0x8001, p, v, self.k.req((0, 0)), v2) for p, v, v2 in props]) \
            if props else None
        i = len(self.k.tables['cancels'])
        self.k.tables['cancels'] += list(rows) + [dict(row(1, None, direction=M.LIST_END, win=(end, 32767)),
                                                       extradata=0)]
        self.c.newidx = {2: 0}
        self.c.T['moves'] = [dict(cancel=tagsystem.write(self.c.T, 'cancels', self.c.conv_cancel_list(i)),
                                  extraprops=None, begin_props=7, voiceclip=5, first_active=active[0],
                                  last_active=active[1], anim=9, name=self.c.string('Wkz_2WP'))]

    def shown(self, n=0):
        out = []
        for r in tagsystem.cancels(self.c.T, self.c.T['moves'][n]['cancel']):
            out.append(((r['win_start'], r['win_end']), r['start_frame'], hex(r['direction']), r['move_id'],
                        converted(self.c, r['req']) if r['req'] is not None else None))
        return out

    def test_later_end_on_block(self):
        """d+1+2 (0x8401 0 / 1, value2 3, active 19-20, end row 54): a hit or a whiff goes on as converted (its end row
        at 54); a block in 19-20 goes on in the copy (move 1, Wkz_2WPG: the same clip from that frame on, no active
        frames, no voice or begin properties) whose end row is at 57."""
        self.move((RECOVERY, 0, 3), (RECOVERY, 1, 3), rows=[row(1, self.k.req((0, 0)))])
        self.c.block_recovery8()
        self.assertEqual(self.shown(), [
            ((1, 32767), 1, '0x0', 1, [(0, 0)]),
            ((19, 20), 19, '0x0', 1, [(49, 0)]),
            ((54, 32767), 54, hex(M.LIST_END), 1, None)])
        self.assertEqual(len(self.c.T['moves']), 2)
        self.assertEqual(self.shown(1), [
            ((1, 32767), 1, '0x0', 1, [(0, 0)]),
            ((57, 32767), 57, hex(M.LIST_END), 1, None)])
        copy = self.c.T['moves'][1]
        self.assertEqual((copy['anim'], copy['first_active'], copy['last_active'], copy['begin_props'],
                          copy['voiceclip'], copy['extraprops']), (9, 0, 0, None, None, None))
        self.assertEqual(self.c.move_name(1), 'Wkz_2WPG')
        into = tagsystem.cancels(self.c.T, self.c.T['moves'][0]['cancel'])[1]      # (keeping the frame count)
        self.assertTrue(self.c.T['cancel_extras'][into['extradata']]['value'] & tagcombo.KEEP_FRAMES)
        self.assertEqual(self.c.stats['Tekken 8 recovery on block: moves recovering later when blocked'], 1)

    def test_rows_kept(self):
        """The list's other rows stay in both (an on-hit follow-up at 30); the copy's end row value2 (2) later."""
        self.move((RECOVERY, 1, 2), rows=[dict(row(2, self.k.req((51, 0)), win=(30, 30)), extradata=0)])
        self.c.block_recovery8()
        self.assertEqual(self.shown()[-2:], [((19, 20), 19, '0x0', 1, [(49, 0)]),
                                             ((54, 32767), 54, hex(M.LIST_END), 1, None)])
        self.assertEqual(self.shown(1)[:-1], self.shown()[:-2])
        self.assertEqual(self.shown(1)[-1][0], (56, 32767))

    def test_copy_properties(self):
        """The copy keeps the property rows after the last active frame (20), not the start rows or earlier ones (a
        summon at the start, sounds at 10 and 20)."""
        self.move((RECOVERY, 1, 3), rows=[row(1, self.k.req((0, 0)))])
        rows = [dict(frame=0x8001, id=0x822E, value=1), dict(frame=10, id=0x801F, value=2),
                dict(frame=20, id=0x801F, value=3), dict(frame=43, id=0x822F, value=4)]
        self.c.T['moves'][0]['extraprops'] = tagsystem.write(self.c.T, 'extra_move_properties',
                                                             rows + [dict(frame=0, id=0, value=0)])
        self.c.block_recovery8()
        self.assertEqual(tagsystem.props(self.c.T, self.c.T['moves'][1]['extraprops']), [rows[3]])
        self.assertEqual(tagsystem.props(self.c.T, self.c.T['moves'][0]['extraprops']), rows)

    def test_unchanged(self):
        """Value 0 alone (+0xE54, not the block's), no property, Tekken 7, or no active frames before the end row: the
        list as converted, no copy."""
        for props, active, end in [(((RECOVERY, 0, 3),), (19, 20), 54), ((), (19, 20), 54),
                                   (((RECOVERY, 1, 3),), (0, 0), 54), (((RECOVERY, 1, 3),), (19, 20), 20)]:
            self.move(*props, rows=[row(1, self.k.req((0, 0)))], active=active, end=end)
            before = self.c.T['moves'][0]['cancel']
            self.c.block_recovery8()
            self.assertEqual((self.c.T['moves'][0]['cancel'], len(self.c.T['moves'])), (before, 1))
        self.move((RECOVERY, 1, 3), rows=[row(1, self.k.req((0, 0)))])
        before = self.c.T['moves'][0]['cancel']
        self.c.game = 't7'
        self.c.block_recovery8()
        self.assertEqual(self.c.T['moves'][0]['cancel'], before)


if __name__ == '__main__':
    unittest.main()
