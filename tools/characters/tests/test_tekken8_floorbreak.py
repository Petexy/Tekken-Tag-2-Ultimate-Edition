"""Unit tests of Tekken 8's floor breaks (convert/moveset.py FLOOR_BREAK8, Converter.floor_break_rows): the whole-move
mark with a strength, or a throw victim's ground impact, becomes TTT2's floor break row at the moment the victim hits
the floor, on made-up tables (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_floorbreak.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import Source8, converter  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402
from ttt2char.movesets import REACTION_MOVE_FIELDS  # noqa: E402
from ttt2char.ttt2 import animation  # noqa: E402

MARK, IMPACT, LANDING = moveset.FLOOR_BREAK8['t8'], moveset.FLOOR_IMPACT8, moveset.LANDING


def falling(frames, lands):
    """A made-up animation (ground, hips, turn channels): the hips at 1000 mm, then down to 100 mm from frame `lands`
    on (None: lying from the start)."""
    v = np.zeros((frames, 3, 3), np.float32)
    v[:, 1, 1] = 100.0 if lands is None else [1000.0 if f < lands else 100.0 for f in range(frames)]
    return animation.encode_raw([11, 11, 5], v)


class FloorBreaks(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k, req={0: 0}, prop={LANDING: LANDING})
        self.always = self.k.req((0, 0))
        self.anim(falling(200, 60))

    def anim(self, buf):
        self.c.move_anim = lambda i: moveset.ANIM_PACK
        self.c.animation_bytes = lambda aid: (buf, '>', 0)

    def breaks(self, *rows, move=0):
        """The TTT2 floor break rows (frame, value) of source move `move` with extra properties (frame, id, value)."""
        start = self.c.conv_xps(self.k.props(*[r + (self.always,) for r in rows]), move)
        rows = self.c.T['extra_move_properties'][start:] if start is not None else []
        rows = rows[:next((n for n, r in enumerate(rows) if r['id'] == 0), len(rows))]
        return [(r['frame'], r['value']) for r in rows if r['id'] == moveset.FLOOR_BREAK]

    def test_after_the_impact(self):
        # a throw victim's move: marked 80 for its whole length, the body hits the floor at 81 (impact and landing
        # rows): TTT2's row, a thrown fall, FLOOR_BREAK_WAIT frames later (TTT2's own throw breaks at 100)
        self.assertEqual(self.breaks((0x8001, MARK, 80), (81, LANDING, 1), (81, IMPACT, 0), (82, IMPACT + 1, 0)),
                         [(81 + moveset.FLOOR_BREAK_WAIT, 1)])
        self.assertEqual(self.c.stats['floor breaks (after its impact)'], 1)

    def test_impact_before_landing(self):
        # a later impact than the landing (a throw that slams the victim again) takes the impact
        self.assertEqual(self.breaks((97, LANDING, 1), (131, IMPACT, 0), (0x8001, MARK, 80)), [(151, 1)])

    def test_after_the_landing(self):
        # no impact row: the landing row
        self.assertEqual(self.breaks((0x8001, MARK, 80), (76, LANDING, 1)), [(96, 1)])
        self.assertEqual(self.c.stats['floor breaks (after its landing)'], 1)

    def test_own_frame(self):
        # a row of its own frame (and a strength of at least FLOOR_BREAK8_MIN) keeps it
        self.assertEqual(self.breaks((0x8001, MARK, 80), (59, IMPACT, 0), (80, MARK, 100)), [(80, 1)])
        self.assertEqual(self.c.stats['floor breaks (after their own frame)'], 1)

    def test_animation_landing(self):
        # no row says when: the animation's hips coming down (frame 60), then the wait
        self.assertEqual(self.breaks((0x8001, MARK, 90)), [(80, 1)])
        self.assertEqual(self.c.stats['floor breaks (after its animation\'s landing)'], 1)

    def test_last_frame(self):
        # past the animation's end the row would never fire: its last frame
        self.anim(falling(70, 60))
        self.assertEqual(self.breaks((0x8001, MARK, 80)), [(69, 1)])

    def test_no_landing(self):
        # an animation that never comes down from standing height (lying from the start): no row
        self.anim(falling(100, None))
        self.assertEqual(self.breaks((0x8001, MARK, 80), (5, 0x8003, 0)), [])
        self.assertEqual(self.c.stats['floor breaks left out: no moment the victim lands'], 1)

    def test_spikes(self):
        # 70 (a spike, a stagger: the victim stays on its feet) and 50 are below a floor's strength: no row
        self.assertEqual(self.breaks((0x8001, MARK, 70), (20, IMPACT, 0)), [])
        self.assertEqual(self.breaks((0x8001, MARK, 50)), [])
        self.assertEqual(self.c.stats['floor breaks left out: weaker than a floor (spikes, staggers)'], 2)

    def test_one_row(self):
        # one row a move, however many marks
        self.assertEqual(self.breaks((0x8001, MARK, 80), (0x8001, MARK, 80), (81, IMPACT, 0), (95, IMPACT, 0)),
                         [(101, 1)])

    def test_requirement(self):
        # a mark under a condition TTT2 cannot attach (Heat) is left out like any row
        heat = self.k.req((999, 1))
        start = self.c.conv_xps(self.k.props((0x8001, MARK, 80, heat), (81, IMPACT, 0, self.always)), 0)
        rows = self.c.T['extra_move_properties'][start:] if start is not None else []
        self.assertNotIn(moveset.FLOOR_BREAK, [r['id'] for r in rows])

    def thrown_into(self, hitlevel):
        """Move 1 of the source: an attack of `hitlevel` whose one hit condition puts the opponent in move 0."""
        moves = self.k.tables['moves']
        while len(moves) < 2:
            moves.append(dict(anim=len(moves), anim_len=0, airborne_start=0))
        r = dict((f, None) for f in REACTION_MOVE_FIELDS)
        r['default'] = r['back'] = 0
        self.k.tables['reactions'].append(r)
        self.k.tables['hit_conditions'].append(dict(req=self.k.req(), damage=20, h_0c=0,
                                                    reactions=len(self.k.tables['reactions']) - 1))
        moves[1].update(hitlevel=hitlevel, hit_condition=len(self.k.tables['hit_conditions']) - 1)
        self.c._throw_victims = None

    def test_throw_impact(self):
        # a throw's victim with an impact row and no mark (Reina's SSH CH 3 attack throw, King's Jaguar Bombs): the
        # row as for a marked one, FLOOR_BREAK_WAIT frames after the impact
        self.thrown_into(moveset.THROW_LEVEL)
        self.assertEqual(self.breaks((82, 0x8004, 0), (83, IMPACT, 0), (96, IMPACT + 1, 0)),
                         [(83 + moveset.FLOOR_BREAK_WAIT, 1)])
        self.assertEqual(self.c.stats['floor breaks of throws marked by their impact only'], 1)
        self.assertEqual(self.c.stats['floor breaks (after its impact)'], 1)

    def test_throw_level_high_bits(self):
        # the hit level's high half (0x200a00, 0x800a00: other throws) does not matter
        self.thrown_into(0x800000 | moveset.THROW_LEVEL)
        self.assertEqual(self.breaks((50, IMPACT, 0)), [(70, 1)])

    def test_hit_impact(self):
        # a hit's reaction with an impact and no mark (a spike on a standing opponent: Reina's d+2 on counter hit):
        # no row (Tekken 8 breaks floors with spikes on airborne opponents only)
        self.thrown_into(0x10F)
        self.assertEqual(self.breaks((4, LANDING, 2), (6, IMPACT, 0), (7, IMPACT + 1, 0)), [])

    def test_throw_without_impact(self):
        # a throw's victim with neither mark nor impact (a throw that does not break floors): no row
        self.thrown_into(moveset.THROW_LEVEL)
        self.assertEqual(self.breaks((46, 0x8003, 0), (84, LANDING, 1)), [])

    def test_marked_toss(self):
        # a throw's victim marked 80 with a landing but no impact (Reina's u/f+1+2, a toss that breaks balconies):
        # no row, though a hit's reaction marked so has one (test_after_the_landing)
        self.thrown_into(moveset.THROW_LEVEL)
        self.assertEqual(self.breaks((0x8001, MARK, 80), (76, LANDING, 1)), [])
        self.assertEqual(self.breaks((0x8001, MARK, 80)), [])
        self.assertEqual(self.c.stats['floor breaks left out: a throw without an impact (a toss: balcony breaks)'], 2)

    def test_marked_throw(self):
        # marked with an impact (Reina's 1+3): the impact, as for a hit's reaction
        self.thrown_into(moveset.THROW_LEVEL)
        self.assertEqual(self.breaks((97, LANDING, 1), (131, IMPACT, 0), (0x8001, MARK, 80)), [(151, 1)])
        self.assertEqual(self.c.stats['floor breaks of throws marked by their impact only'], 0)

    def test_throw_weak_mark(self):
        # a mark below a floor's strength keeps its word, impact or not
        self.thrown_into(moveset.THROW_LEVEL)
        self.assertEqual(self.breaks((0x8001, MARK, 70), (72, IMPACT, 0)), [])

    def test_not_a_victim(self):
        # the throw's own move (the thrower's) with an impact row: no row
        self.thrown_into(moveset.THROW_LEVEL)
        self.assertEqual(self.breaks((83, IMPACT, 0), move=1), [])

    def test_tekken7_unchanged(self):
        # Tekken 7's floor break (0x81e4) is TTT2's row already: the id maps carry it, nothing here
        self.assertIsNone(moveset.FLOOR_BREAK8['t7'])
        self.assertNotIn(MARK, moveset.PROP_OVERRIDE['t8'])


if __name__ == '__main__':
    unittest.main()
