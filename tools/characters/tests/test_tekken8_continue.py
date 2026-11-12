"""Unit tests of Tekken 8's continued moves (convert/moveset.py CONTINUE8): a move that goes on from a frame of its clip
(0x8339, value minus the frame the move before left it at) gets TTT2's no-op row TT_CONTINUE at frame 0x8001 with the
frame it starts at, which the runtime sets (roster.cpp "continued moves"), and a speed with a frame of no plain number
is left out (ODD_SPEED), on made-up tables (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_continue.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import Source8, converter  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402

CONTINUE = moveset.CONTINUE8['t8']


class ContinuedMoves(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k, req={0: 0})
        self.always = self.k.req((0, 0))

    def rows(self, *props):
        start = self.c.conv_xps(self.k.props(*[r + (self.always,) for r in props]), 0)
        rows = self.c.T['extra_move_properties'][start:] if start is not None else []
        rows = rows[:next((n for n, r in enumerate(rows) if r['id'] == 0), len(rows))]
        return [(r['frame'], r['id'], r['value']) for r in rows]

    def test_the_move_starts_one_frame_after_the_one_it_goes_on_from(self):
        # (Burning Rain's landing: the slam leaves its clip at frame 29, the landing shows frame 30 first)
        self.assertEqual(self.rows((0x8001, CONTINUE, 0xFFFFFFE3)),
                         [(moveset.arcs.BAKED_FRAME, moveset.TT_CONTINUE, 30)])

    def test_a_signed_value_reads_the_same(self):
        self.assertEqual(self.rows((0x8001, CONTINUE, -46)), [(moveset.arcs.BAKED_FRAME, moveset.TT_CONTINUE, 47)])

    def test_a_start_before_frame_1_is_dropped(self):
        self.assertEqual(self.rows((0x8001, CONTINUE, 5)), [])
        self.assertEqual(self.c.stats['property dropped: a clip start before frame 1'], 1)


class OddSpeeds(unittest.TestCase):
    # (ODD_SPEED) Tekken 8's speed 0x8246 -> TTT2's 0x812A: kept on plain frames, left out whole where a row's frame
    # has no plain number (Clive's jumps: 0x960 at 0x8001, 0x1000 at 0x4008)
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k, req={0: 0}, prop={0x8246: moveset.TT_SPEED, 0x8100: 0x8100})
        self.always = self.k.req((0, 0))

    rows = ContinuedMoves.rows

    def test_a_speed_on_plain_frames_is_kept(self):
        self.assertEqual(self.rows((0x8001, 0x8246, 0xC80), (20, 0x8246, 0x1000)),
                         [(0x8001, moveset.TT_SPEED, 0xC80), (20, moveset.TT_SPEED, 0x1000)])

    def test_a_speed_reset_on_a_frame_of_no_plain_number_leaves_the_speed_out(self):
        self.assertEqual(self.rows((0x8001, 0x8246, 0x960), (5, 0x8100, 7), (0x4008, 0x8246, 0x1000)),
                         [(5, 0x8100, 7)])
        self.assertEqual(self.c.stats['speed left out: a frame TTT2 reads its own way (ODD_SPEED)'], 1)


if __name__ == '__main__':
    unittest.main()
