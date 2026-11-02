"""Unit tests of two Tekken 7 cancel-list rules of the converter (convert/moveset.py): counted holds (COUNT_VAR: a
player variable counting a move's frames -> TTT2's fourth latch; Noctis's blocked Warp-Strikes) and effects at a
weapon's point (EFFECT_AT: 0x802e / 0x803f values -> the weapon point's TTT2 location), plus the requirement rows of
a cancel list (idmaps.cancel_reqs, where a hit's sounds are), on made-up tables.

    python3 -m pytest -q tools/characters/tests/test_counted_holds.py
"""
import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import moveset, tagcombo  # noqa: E402
from ttt2char.movesets import Moveset  # noqa: E402

END7 = M.END_REQ['t7']
VAR = 29                                  # the player variable the made-up hold counts with
STAND, MISS = 2, 1                        # move numbers: the stance, the warp forward (Mz_rp01F_Miss)


class Source7(Moveset):
    """A made-up Tekken 7 moveset: requirement lists (end 881), cancel extradata values, cancel lists."""
    game = 't7'
    character_id = 40

    def __init__(self):
        self.tables = collections.defaultdict(list)

    def move_name(self, i):
        return 'Mz_%d' % i

    def req(self, *rows):
        start = len(self.tables['requirements'])
        self.tables['requirements'] += [dict(condition=c, param=p) for c, p in rows + ((END7, 0),)]
        return start

    def extra(self, value):
        self.tables['cancel_extras'].append(dict(value=value))
        return len(self.tables['cancel_extras']) - 1

    def cancels(self, *rows, table='cancels', end=M.LIST_END):
        """A cancel list of (direction, requirement list, extradata value, move id) rows and its end row."""
        start = len(self.tables[table])
        for direction, req, extra, move in rows + ((end, self.req((0, 0)), 0x80, STAND),):
            self.tables[table].append(dict(direction=direction, button=0, req=req, extradata=self.extra(extra),
                                           win_start=1, win_end=32767, start_frame=1, move_id=move, option=0))
        return start


class Map:
    """An id map stub: {id: TTT2 id} observed, anything else a gap."""

    def __init__(self, pairs):
        self.pairs = pairs

    def lookup(self, x):
        return (self.pairs[x], 'observed') if x in self.pairs else (None, 'gap')


class Defn:
    MOVESET = {'name': '[TEST]'}


def converter(k):
    """A bare Converter of Tekken 7 moveset k (its run() parts not needed by the tests left out; cancel targets kept
    as they are)."""
    req, prop = {0: 0, 44: 46}, {0x8261: 0x81a0, 0x802e: 0x801d, 0x803f: 0x8028}
    c = moveset.Converter.__new__(moveset.Converter)
    c.k, c.game, c.end = k, 't7', END7
    c.req_map, c.prop_map = Map(req), Map(prop)
    c.usage = {'req': set(req.values()), 'prop': set(prop.values())}
    c.T = {'requirements': [], 'cancel_extras': [], 'group_cancels': []}
    c.cache, c.stats, c.unmapped = {}, collections.Counter(), collections.Counter()
    c.defn, c.extra_index, c.hit_locations, c.opt_anims = Defn(), {}, {}, {}
    c.donor_sound = collections.defaultdict(set)
    c.target = lambda mid, input_target=False: mid
    return c


def reqs(c, start):
    """The conditions of a converted requirement list (its end row left out)."""
    out, t = [], c.T['requirements']
    while t[start]['condition'] != moveset.TT_END:
        out.append((t[start]['condition'], t[start]['param']))
        start += 1
    return out


class CountedHolds(unittest.TestCase):
    def hold(self, keep=tagcombo.KEEP_FRAMES | 1, test=True, add=1):
        """Mz_rp00F_GRD's list: leave for the warp once the variable is 9; count a frame (back into itself)."""
        k = Source7()
        leave = k.req((359, VAR << 16 | 9) if test else (0, 0))
        count = k.req((0x8261, 0), (0x8107, VAR << 16 | add))
        k.tables['moves'] = [dict(cancel=0), dict(cancel=None), dict(cancel=None)]
        k.cancels((0, leave, 0x84080, MISS), (0, count, keep, 0))
        return k, converter(k)

    def test_the_hold_counts_its_frames_in_the_fourth_latch(self):
        k, c = self.hold()
        rows = c.conv_cancel_list(0)
        self.assertEqual([(r['move_id'], reqs(c, r['req'])) for r in rows],
                         [(MISS, [(316, 9)]), (0x8001, [(0x81a0, 0), (0x80a0, 1)]), (STAND, [(0, 0)])])
        self.assertEqual(c.T['cancel_extras'][rows[1]['extradata']]['value'], tagcombo.ACTION_ONLY)
        self.assertEqual(c.stats['counted holds'], 1)

    def test_the_variable_outside_the_hold_stays_false(self):
        k, c = self.hold()
        c.conv_cancel_list(0)
        self.assertEqual(c.conv_reqs(k.tables['cancels'][0]['req']), (None, False))     # (not the hold's cache)
        self.assertEqual(c.conv_reqs(k.tables['cancels'][1]['req']), (None, False))

    def test_other_shapes_are_not_holds(self):
        for kw in (dict(keep=1), dict(test=False), dict(add=2)):       # its frame not kept; no test; another amount
            k, c = self.hold(**kw)
            rows = c.conv_cancel_list(0)
            self.assertEqual([r['move_id'] for r in rows], [STAND] if kw.get('test', True) else [MISS, STAND], kw)
            self.assertFalse(c.stats['counted holds'])

    def test_a_row_into_another_move_or_with_a_condition_is_not_a_count(self):
        k, c = self.hold()
        k.tables['moves'][MISS]['cancel'] = 7
        k.tables['cancels'][1]['move_id'] = MISS
        self.assertFalse(c.counting_rows(0))
        k, c = self.hold()
        k.tables['requirements'][k.tables['cancels'][1]['req']]['condition'] = 44
        self.assertFalse(c.counting_rows(0))

    def test_a_group_is_converted_without_the_hold(self):
        k, c = self.hold()
        group = k.cancels((0, k.req((359, VAR << 16 | 9)), 0, MISS), table='group_cancels', end=M.GROUP_END)
        k.tables['cancels'].insert(2, dict(k.tables['cancels'][0], direction=M.GROUP, req=k.req((0, 0)), move_id=group))
        rows = c.conv_cancel_list(0)
        self.assertEqual([r['move_id'] for r in rows][:2], [MISS, 0x8001])
        self.assertEqual([r['move_id'] for r in c.T['group_cancels']], [STAND])        # its 359 row: false

    def test_tekken8_has_none(self):
        self.assertEqual(moveset.COUNT_VAR['t8'], ())
        self.assertEqual(moveset.COUNT_TTT2, (316, 0x809f, 0x80a0))


class EffectsAtWeaponPoints(unittest.TestCase):
    def test_weapon_points_take_their_ttt2_location(self):
        c = converter(Source7())
        c.hit_locations = {0x63: 70, 0x73: 13}            # (a sword tip; a definition's HIT_LOCATIONS)
        self.assertEqual(c.conv_value(0x802e, 0x63), 70)
        self.assertEqual(c.conv_value(0x803f, 0x73), 13)
        self.assertEqual(c.conv_value(0x802e, 7), 7)     # a bone: as it is
        self.assertEqual(c.conv_value(0x8261, 0x63), 0x63)

    def test_in_a_hits_requirement_list(self):
        k = Source7()
        c = converter(k)
        c.hit_locations = {0x63: 70}
        start, ok = c.conv_reqs(k.req((44, 0), (0x802e, 0x63)))
        self.assertEqual(reqs(c, start), [(46, 0), (0x801d, 70)])


class CancelRequirements(unittest.TestCase):
    def test_a_lists_and_its_groups_requirement_rows(self):
        k = Source7()
        group = k.cancels((0, k.req((0x84c4, 15 << 24 | 430)), 0, 0), table='group_cancels', end=M.GROUP_END)
        start = k.cancels((0, k.req((44, 0), (0x84c4, 7 << 24 | 16)), 0, 0), (M.GROUP, None, 0, group))
        self.assertEqual(M.cancel_reqs(k, start),
                         [(44, 0), (0x84c4, 7 << 24 | 16), (0x84c4, 15 << 24 | 430), (0, 0), (0, 0)])
        self.assertEqual(M.cancel_reqs(k, None), [])


if __name__ == '__main__':
    unittest.main()
