"""Unit tests of the guards on Tekken 8 values in TTT2 ids (convert/moveset.py FIT, the owner's character tests, the
Tekken 8 requirements made false, the face animations left out, HIT_LOCATION; convert/idmaps.py ttt2_values, distrust,
outvoted), on made-up tables (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_fit.py
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


class Lists:
    """A made-up moveset: requirement rows (condition, param) and extra property rows (id, value)."""

    def __init__(self, reqs=(), props=()):
        self.tables = {'requirements': [dict(condition=c, param=p) for c, p in reqs],
                       'extra_move_properties': [dict(id=i, value=v) for i, v in props],
                       'move_begin_props': [], 'move_end_props': []}


class Fit(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k, req={47: 47, 0: 0, 126: 124, 224: 206, 1036: 647, 442: 46},
                           prop={0x8100: 0x8090, 0x8219: 0x8110, 0x87f0: 0x82f9, 0x860b: 0x82d6})
        self.c.usage['values'] = {'req': {0: {0}, 47: {0}, 124: {0}, 206: {0, 42, 58}, 0x8090: {3, 9}},
                                  'prop': {0x8090: {1, 2, 10}, 0x8110: {0}, 0x82f9: {0x02000001}}}
        self.always = self.k.req((0, 0))

    def conv(self, *rows):
        start, ok = self.c.conv_reqs(self.k.req(*rows))
        return converted(self.c, start) if ok else None

    def xps(self, *rows):
        start = self.c.conv_xps(self.k.props(*rows))
        return [(r['frame'], r['id'], r['value']) for r in self.c.T['extra_move_properties'][start:]]

    def test_requirement_params(self):
        self.assertEqual(self.conv((47, 0), (126, 0)), [(47, 0), (124, 0)])
        self.assertIsNone(self.conv((126, 1)))                             # TTT2 tests 124 with 0 only: false
        self.assertEqual(self.c.stats['requirement with a parameter TTT2 never passes -> false'], 1)

    def test_properties(self):
        self.assertEqual(self.xps((5, 0x8100, 7, self.always), (6, 0x8100, 11, self.always),
                                  (7, 0x8219, 1, self.always), (8, 0x8219, 0, self.always)),
                         [(5, 0x8090, 7), (8, 0x8110, 0), (0, 0, 0)])     # 7 in 1..10 (not one of them) kept
        self.assertEqual(self.c.stats['property dropped: a value TTT2 never passes'], 2)

    def test_action_in_a_requirement_list(self):
        self.assertEqual(self.conv((47, 0), (0x8100, 5)), [(47, 0), (0x8090, 5)])
        self.assertEqual(self.conv((47, 0), (0x8100, 1)), [(47, 0)])      # left out, the list kept
        self.assertEqual(self.c.stats['property left out of a requirement list: a value TTT2 never passes'], 1)

    def test_converted_values_not_tested(self):
        """Values the converter makes itself (here a sound of her own voice) are not FIT's."""
        self.assertEqual(self.xps((5, 0x87f0, 2, self.always, 5)), [(5, 0x82f9, 0x02000005), (0, 0, 0)])

    def test_no_values_no_guard(self):
        del self.c.usage['values']
        self.assertEqual(self.conv((126, 1)), [(124, 1)])
        self.assertEqual(self.xps((6, 0x8100, 11, self.always)), [(6, 0x8090, 11), (0, 0, 0)])

    def test_owner_and_false(self):
        self.assertEqual(self.conv((224, 28), (47, 0)), [(47, 0)])         # "the player is Reina": true
        self.assertIsNone(self.conv((224, 8)))                             # "... is Kazuya": false
        self.assertIsNone(self.conv((1036, 14295)))                        # a Tekken 8 move number, though mapped
        self.assertIsNone(self.conv((442, 1)))                             # Heat variables, though mapped

    def test_face_animations_left_out(self):
        self.assertEqual(self.xps((5, 0x860b, 14858, self.always)), [])
        self.assertEqual(self.c.stats['property dropped: face animation'], 1)

    def test_hit_locations(self):
        self.c.hitbox, self.c.hit_locations = {46: 37}, {}
        self.assertEqual([self.c.hit_location(x) for x in (125, 133, 134, 46, 16)], [70, 0, 0, 37, 16])
        self.c.game = 't7'
        self.assertEqual(self.c.hit_location(125), 125)                    # (Tekken 7's codes as they were)


class Maps(unittest.TestCase):
    def test_ttt2_values(self):
        v = M.ttt2_values([Lists([(47, 0), (0x8090, 3)], [(0x8090, 10)]), Lists([(47, 2)], [(0x8090, 1)])])
        self.assertEqual(v, {'req': {47: {0, 2}, 0x8090: {3}}, 'prop': {0x8090: {1, 10}}})
        self.assertEqual(M.ttt2_usage([Lists([(47, 0)])])['values']['req'], {47: {0}})

    def test_distrust(self):
        """An exception is kept only when most of the fighters' rows pass a value TTT2 passes with its id."""
        m = M.IdMap({0x8040: (0x8030, 50, 50, {}), 0x8050: (0x8040, 50, 50, {}), 0x8049: (0x801d, 10, 10, {}),
                     0x8345: (0x8010, 2, 2, {}), 0x8400: (0x8300, 50, 50, {})})    # (two exceptions)
        m.exc[1100] = (690, 0, 0)                          # (the list end, as build_maps adds it)
        mine = M.source_values([Lists([(1100, 0)], [(0x8049, 71), (0x8049, 2429), (0x8345, 2), (0x8345, 2),
                                                     (0x8345, 0)])])
        theirs = {'req': {}, 'prop': {0x801d: {0, 9, 60}, 0x8010: {2, 3, 4, 5}}}
        self.assertEqual(M.distrust(m, mine, theirs), [0x8049])
        self.assertEqual(m.lookup(0x8049), (None, 'left out'))           # (not 0x8039 between 0x8040 and 0x8050)
        self.assertEqual(m.lookup(0x8345), (0x8010, 'observed-exception'))   # 2 of 3 rows fit
        self.assertEqual(m.lookup(1100), (690, 'observed-exception'))

    def test_outvoted(self):
        """The fighter's own exception (130 -> 46, 8 rows) yields where the references' evidence pairs 130 with 128
        most and their map gives 128 (between 128 -> 126 and 131 -> 129); one their map does not give stays."""
        own = M.IdMap({128: (126, 33, 33, {}), 131: (129, 11, 11, {}), 130: (46, 8, 8, {}), 140: (20, 20, 20, {})})
        wide = M.IdMap({128: (126, 160, 160, {}), 131: (129, 35, 35, {}),
                        130: (128, 92, 154, {128: 92, 46: 62}), 140: (201, 50, 95, {201: 50, 20: 45})})
        self.assertEqual(own.lookup(130), (46, 'observed-exception'))
        self.assertEqual(M.outvoted(own, wide), [130])
        self.assertEqual(M.Combined(own, wide).lookup(130), (128, 'interpolated'))
        self.assertEqual(own.lookup(140), (20, 'observed-exception'))       # theirs not 201 (above the chain): kept


if __name__ == '__main__':
    unittest.main()
