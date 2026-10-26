"""Unit tests of the definition's bounds (MOVESET['bounds']: convert/move_overrides.py) on a converted Tekken 8 shape,
and of the command list's bound marks (move_overrides.command_bounds), on made-up tables (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_bounds.py
"""
import collections
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from test_tagsystem import Tables  # noqa: E402
from ttt2char.convert import idmaps as M, move_overrides, tagsystem as TS  # noqa: E402


class Base(unittest.TestCase):
    """A converter's tables (the donor's bound shape, a stance) and the parts move_overrides reads."""

    def setUp(self):
        T = Tables()
        self.T = T
        self.bound, self.after, self.air, self.ground = (T.reaction(n) for n in (10, 11, 12, 13))
        self.r467, self.r466, self.never = T.req((467, 0)), T.req((466, 0)), T.req()
        self.stance = T.move('Zbr_sKAM00_')
        T.aliases[1] = self.stance
        self.c = types.SimpleNamespace(T=T.t, aliases=T.aliases, game='t8', stats=collections.Counter(),
                                       bound_req=self.r467, bound_reaction=self.bound,
                                       after_bound_reaction=self.after, map_req=lambda i: None, kn={}, newidx={},
                                       defn=types.SimpleNamespace(MOVESET={'bounds': {}}))

    def move(self, name, *hits, **fields):
        i = self.T.move(name, hit_condition=self.T.hits(*hits) if hits else None, **fields)
        self.c.kn[name] = 1000 + i                      # (her Tekken 8 index -> the converted one)
        self.c.newidx[1000 + i] = i
        return i

    def hits(self, i):
        return [(h['req'], h['damage'], h['reactions'])
                for h in TS.hits(self.c.T, self.c.T['moves'][i]['hit_condition'])]


class Bounds(Base):
    def test_made_a_bound(self):
        """Tekken 8's d+2 shape [air][default] -> TTT2's [467 -> bound][466 -> air][default], the air entry's damage."""
        i = self.move('Zbr_2RP', (self.r466, 17, self.air), (self.never, 18, self.ground))
        self.c.defn.MOVESET['bounds'] = {'Zbr_2RP': True}
        move_overrides.apply(self.c)
        self.assertEqual(self.hits(i), [(self.r467, 17, self.bound), (self.r466, 17, self.air),
                                        (self.never, 18, self.ground)])
        self.assertEqual(self.c.stats['explicit bound enabled'], 1)

    def test_one_bound_entry(self):
        """A tornado already converted to a bound keeps one bound entry."""
        i = self.move('Zbr_4RK', (self.r467, 20, self.bound), (self.r466, 20, self.air), (self.never, 20, self.ground))
        self.c.defn.MOVESET['bounds'] = {'Zbr_4RK': True}
        move_overrides.apply(self.c)
        self.assertEqual([h[0] for h in self.hits(i)], [self.r467, self.r466, self.never])

    def test_bound_removed(self):
        """False: no 467 entry; an air entry with the bound reaction plays the donor's air hit after a bound."""
        i = self.move('Zbr_9RK', (self.r467, 13, self.bound), (self.r466, 13, self.T.reaction(10)),
                      (self.never, 13, self.ground))
        self.c.defn.MOVESET['bounds'] = {'Zbr_9RK': False}
        move_overrides.apply(self.c)
        self.assertEqual(self.hits(i), [(self.r466, 13, self.after), (self.never, 13, self.ground)])


class CommandBounds(Base):
    """The presses of a command walked through the converted moveset from standing."""

    def setUp(self):
        super().setUp()
        T = self.T
        heat = T.req((1028, 1))
        self.d2 = self.move('Zbr_2RP')
        self.f4 = self.move('Zbr_6RK')
        self.f4_heat = self.move('Zbr_6RK_EX')
        self.jab = self.move('Zbr_lp00')
        self.jab2 = self.move('Zbr_LPLP')
        group = TS.write(T.t, 'group_cancels', [
            dict(direction=0x4, button=0x40000002, req=self.always(), extradata=0, win_start=1, win_end=32767,
                 start_frame=1, move_id=self.d2, option=0),
            dict(direction=0x40, button=0x40000008, req=heat, extradata=0, win_start=1, win_end=32767,
                 start_frame=1, move_id=self.f4_heat, option=0),           # Heat: not walked
            dict(direction=0x40, button=0x40000008, req=self.always(), extradata=0, win_start=1, win_end=32767,
                 start_frame=1, move_id=self.f4, option=0),
            dict(direction=M.GROUP_END, button=0, req=0, extradata=0, win_start=0, win_end=0, start_frame=0,
                 move_id=0, option=0)])
        T.t['moves'][self.stance]['cancel'] = T.cancels(
            dict(direction=0x20, button=0x40000001, req=self.always(), move_id=self.jab),
            dict(direction=M.GROUP, move_id=group), T.end())
        T.t['moves'][self.jab]['cancel'] = T.cancels(
            dict(direction=0, button=0x40000001, req=self.always(), win_start=3, win_end=12, move_id=self.jab2),
            T.end(30))

    def always(self):
        return self.T.req((0, 0))

    def test_none_without_bounds(self):
        self.assertIsNone(move_overrides.command_bounds(self.c))

    def test_marks(self):
        self.c.defn.MOVESET['bounds'] = {'Zbr_2RP': True, 'Zbr_6RK': True, 'Zbr_LPLP': False}
        marks = move_overrides.command_bounds(self.c)
        self.assertEqual(marks([(0x4, 2, 0)]), {1: True})                     # d+2
        self.assertEqual(marks([(0x40, 8, 0)]), {1: True})                    # f+4, past the Heat row
        self.assertEqual(marks([(0x20, 1, 0), (0x20, 1, 5)]), {2: False})     # 1,1: its 2nd hit
        self.assertEqual(marks([(0x20, 1, 0), (0x20, 1, 20)]), {})            # too late for the window
        self.assertEqual(marks([(0x20, 2, 0)]), {})                           # no row takes 2


if __name__ == '__main__':
    unittest.main()
