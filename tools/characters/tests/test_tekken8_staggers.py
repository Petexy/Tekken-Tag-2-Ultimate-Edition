"""A reaction never takes a TTT2 move that does another kind of thing to the opponent: a stagger, a crumple, a launch
(convert/moveset.py REST, Converter.rest, fall, other_fall; Tekken 7 and Tekken 8 alike): synthetic movesets only."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from ttt2char.convert import moveset  # noqa: E402


class Moves:
    """A moveset of named moves [(name, transition (index or None), airborne)]; alias 0x8000 is move 0."""

    def __init__(self, rows):
        self.names = [r[0] for r in rows]
        self.tables = {'moves': [{'transition': r[1] if r[1] is not None else 0x8000,
                                  'airborne_start': 3 if r[2] else 0} for r in rows]}

    def resolve_alias(self, t):
        return 0 if t == 0x8000 else None

    def move_name(self, i):
        return self.names[i]


def other_fall(k, mid, d, j):
    c = SimpleNamespace(k=k, d=d, name=k.move_name, rest=moveset.Converter.rest, fall=moveset.Converter.fall)
    return moveset.Converter.other_fall(c, mid, j)


class Staggers(unittest.TestCase):
    def setUp(self):
        # the source: a stagger back to the stance, one into a crouch, an air reaction, a launch named as a down state
        # (Tekken 8's dw_He_shoryu, airborne itself), a crumple, a trip (airborne on the way to the floor)
        self.k = Moves([('Cat_sKAM00_', None, False), ('sDm_KAOLee', 0, False), ('#405', 3, False),
                        ('cKAM__00_', None, False), ('#37', 5, True), ('dwKAM_00U', None, False),
                        ('dw_He_shoryu', None, True), ('#386', 8, False), ('dwDWN_101D', None, False),
                        ('sDm_DownL00', 8, True)])
        # TTT2's donor: a knock-down, a launch, an air reaction, a stagger, a crumple, a flip launch
        self.d = Moves([('Ju_sKAM00_', None, False), ('sDw_KAO00_', 4, False), ('sDw_UP_11_', 3, True),
                        ('Dw_AIR00_', 4, True), ('dwKAM_00U', None, False), ('sDm_KAO10FLP', 0, False),
                        ('sDm_KAKCca', 7, False), ('dwKAM_00D', None, False), ('ym_y01L', 4, True)])

    def test_rest(self):
        self.assertEqual(moveset.Converter.rest(self.k, 1, self.k.move_name), ('stand', False))
        self.assertEqual(moveset.Converter.rest(self.k, 2, self.k.move_name), ('crouch', False))
        self.assertEqual(moveset.Converter.rest(self.d, 2, self.d.move_name), ('down', True))
        self.assertEqual(moveset.Converter.rest(self.d, 1, self.d.move_name), ('down', False))
        # the resting move's own airborne frames count too
        self.assertEqual(moveset.Converter.rest(self.k, 6, self.k.move_name), ('down', True))

    def test_fall(self):
        self.assertEqual([moveset.Converter.fall(moveset.Converter.rest(self.k, i, self.k.move_name))
                          for i in (1, 2, 4, 6, 7, 9)], ['feet', 'feet', 'air', 'air', 'down', 'air'])

    def test_a_stagger_is_not_felled(self):
        self.assertTrue(other_fall(self.k, 1, self.d, 1))      # stagger -> knock-down: refused
        self.assertTrue(other_fall(self.k, 2, self.d, 2))      # stagger into a crouch -> launch: refused
        self.assertFalse(other_fall(self.k, 1, self.d, 5))     # stagger -> stagger: kept

    def test_a_launch_is_not_grounded(self):
        self.assertTrue(other_fall(self.k, 6, self.d, 6))      # launch -> crumple: refused
        self.assertTrue(other_fall(self.k, 9, self.d, 5))      # trip -> stagger: refused
        self.assertFalse(other_fall(self.k, 6, self.d, 2))     # launch -> launch: kept

    def test_a_crumple_is_not_stood_up_or_launched(self):
        self.assertTrue(other_fall(self.k, 7, self.d, 5))      # crumple -> stagger: refused
        self.assertTrue(other_fall(self.k, 7, self.d, 8))      # crumple -> flip launch: refused
        self.assertFalse(other_fall(self.k, 7, self.d, 6))     # crumple -> crumple: kept
        self.assertFalse(other_fall(self.k, 7, self.d, 1))     # crumple -> knock-down without a float: kept

    def test_air_and_down_reactions_keep_ttt2s(self):
        self.assertFalse(other_fall(self.k, 4, self.d, 2))     # the source's air reaction -> TTT2's launch: kept
        self.assertFalse(other_fall(self.k, 4, self.d, 3))     # ... -> TTT2's air reaction: kept

    def test_unknown_counts_as_the_same(self):
        k = Moves([('Cat_sKAM00_', None, False), ('#1', 2, False), ('#2', 1, False)])    # (a loop: no REST)
        self.assertFalse(other_fall(k, 1, self.d, 1))
        self.assertFalse(other_fall(self.k, 1, k, 1))


if __name__ == '__main__':
    unittest.main()
