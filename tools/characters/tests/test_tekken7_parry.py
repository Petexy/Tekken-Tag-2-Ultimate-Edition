"""Unit tests of a Tekken 7 fighter's parries and counters (convert/moveset.py PARRY_TESTS): the requirement that the
opponent's attack hits now, by its hit level and limb (Tekken 7's 859..866), is TTT2's 678..685 with the limb as TTT2
numbers it, so the no-input cancel rows into the parry's move stay (Leroy's b+2, Geese's counters, Negan's bat stance),
on made-up tables.

    python3 -m unittest tests.test_tekken7_parry
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_cancels import row  # noqa: E402
from test_tekken8_convert import converted  # noqa: E402
from test_tekken7_requirements import Source7, converter  # noqa: E402
from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402


class ParryTests(unittest.TestCase):
    def setUp(self):
        self.k = Source7()
        self.c = converter(self.k, req={0: 0, 2: 2})       # (the id maps never pair 859..866: Heihachi has none)
        self.c.hit_locations, self.c.hitbox = {}, {21: 19, 80: 64}

    def conv(self, *rows):
        start, ok = self.c.conv_reqs(self.k.req(*rows))
        return converted(self.c, start) if ok else None

    def test_levels_in_order(self):
        """859 high, 860 mid, 861 low, 862 high or mid (the attacker facing), 863..866 (its back turned) -> 678..685."""
        for k in range(8):
            self.assertEqual(self.conv((859 + k, 13)), [(678 + k, 13)])
        self.assertEqual(self.c.stats["parry tests (the opponent's attack by its level and limb)"], 8)

    def test_limb(self):
        """0 (any limb), 64 (kisses, lasers, mist) and the body's bones stay as they are (21 is not the fighter's own
        hit box 21 -> 19); a point past them as the fighter's hit boxes are converted."""
        self.assertEqual(self.conv((859, 0)), [(678, 0)])
        self.assertEqual(self.conv((859, 64)), [(678, 64)])
        self.assertEqual(self.conv((860, 21)), [(679, 21)])
        self.assertEqual(self.conv((859, 0x2c)), [(678, 37)])           # Leroy's 44: the left foot's point
        self.assertEqual(self.conv((863, 0x23)), [(682, 4)])            # the head's
        self.assertEqual(self.conv((861, 80)), [(680, 64)])             # as the fighter's hit boxes have it

    def test_other_requirements_kept(self):
        self.assertEqual(self.conv((2, 0), (860, 9)), [(2, 0), (679, 9)])

    def test_parry_lists_stay_false(self):
        """817 / 823 (the opponent's move in a parry list: Tekken 7's own move ids) are not converted."""
        self.assertIsNone(self.conv((817, 3)))
        self.assertIsNone(self.conv((859, 13), (823, 1)))

    def test_cancel_rows(self):
        """b+2's rows: no input, the parry tests, into the parry's moves; the row on a parry list is left out."""
        self.c.T.update(cancels=[], cancel_extras=[])
        self.c.extra_index, self.c.target = {}, lambda m, input_target=False: m
        self.k.tables['cancels'] = [row(0, 0, 1, self.k.req((859, 13))), row(0, 0, 2, self.k.req((860, 9))),
                                    row(0, 0, 3, self.k.req((817, 3))), row(M.LIST_END, 0)]
        out = self.c.conv_cancel_list(0)[:-1]
        self.assertEqual([(r['move_id'], converted(self.c, r['req'])) for r in out],
                         [(1, [(678, 13)]), (2, [(679, 9)])])

    def test_tekken8_untouched(self):
        """Tekken 8's parry tests (1078..1085) go through the id maps as before."""
        self.assertEqual(moveset.PARRY_TESTS['t8'], {})
        self.assertNotIn(1078, moveset.REQ_OVERRIDE['t8'])


if __name__ == '__main__':
    unittest.main()
