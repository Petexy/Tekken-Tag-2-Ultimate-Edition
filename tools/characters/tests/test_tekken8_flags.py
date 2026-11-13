"""Unit tests of the Tekken 8 flag slots (FLAG8: 507 tests a slot's value, 0x815a sets a slot for a number of moves;
TTT2 keeps a slot in a moveset variable counted down as each of the fighter's moves starts), the wall tests (WALL8:
Tekken 8's 194..201 -> TTT2's 174..181) and the contact tests 51 / 49 (the move hit kept in a latch: HIT_HELD)
(convert/moveset.py), on made-up tables.

    python3 -m pytest -q tools/characters/tests/test_tekken8_flags.py
"""
import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import END8, Source8, converter, converted  # noqa: E402
from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import moveset, tagcombo, tagsystem  # noqa: E402

SLOT_TEST, SLOT_SET = 507, 0x815a
STATE = 0x81fa                          # a move-start state value (TTT2 0x80f8 through the stub id map)


class Flags8(Source8):
    """Source8 whose requirement rows take param3 and whose property rows take value2."""

    def req(self, *rows):
        start = len(self.tables['requirements'])
        for r in rows + ((END8, 0),):
            r = tuple(r) + (0, 0, 0)
            self.tables['requirements'].append(dict(condition=r[0], param=r[1], param2=r[2], param3=r[3], param4=0))
        return start

    def props(self, *rows):
        """(frame, id, value, requirement list[, value2, value3]) rows -> the list's index."""
        start = len(self.tables['extra_move_properties'])
        for r in rows:
            r = tuple(r) + (0, 0)
            self.tables['extra_move_properties'].append(dict(frame=r[0], id=r[1], value=r[2], req=r[3], value2=r[4],
                                                             value3=r[5], value4=0, value5=0))
        self.tables['extra_move_properties'].append(dict(frame=0, id=0, value=0, req=None, value2=0, value3=0,
                                                         value4=0, value5=0))
        return start


class Donor:
    def __init__(self, reqs=(), props=()):
        self.tables = {'requirements': [dict(condition=c, param=0) for c in reqs],
                       'extra_move_properties': [dict(id=p, value=0, frame=1) for p in props],
                       'move_begin_props': [], 'move_end_props': []}


def flagged(c, slots):
    """Converter c with flag slots `slots` ({slot: variable}) and the tables flag8_rows needs."""
    c.flag8 = dict(slots)
    c.flag8_moves = collections.defaultdict(list)
    c.T.update(cancels=[], cancel_extras=[], moves=[], move_end_props=[])
    c.extra_index = {}
    c.newidx = {}
    c.target = lambda m, input_target=False: m
    return c


def row(move_id=0, req=None, direction=0, button=0, win=(1, 32767)):
    return dict(direction=direction, button=button, req=req, extradata=None, win_start=win[0], win_end=win[1],
                start_frame=win[0], move_id=move_id, option=0)


class Slots(unittest.TestCase):
    """flag8_slots: a variable for each slot both set (value 0 / 1) and tested, in FLAG8_VARS order, none taken."""

    def source(self):
        k = Flags8(refs=[(0, 'own')])
        k.req((SLOT_TEST, 0, 1), (SLOT_SET, 0, 2, 1), (SLOT_TEST, 1, 0), (SLOT_TEST, 2, 1), (SLOT_SET, 3, 1, 1))
        k.req((SLOT_TEST, 5, 1), (SLOT_SET, 5, 1, 2))     # a value TTT2 cannot keep
        k.props((0x8001, SLOT_SET, 1, None, 2, 1))       # slot 1 set as an extra property
        return k

    def slots(self, k, donor=None, req=None, flags=None):
        c = converter(k, req=req)
        c.d = donor or Donor()
        if flags:
            c.flag_props = flags
        return c.flag8_slots(), c

    def test_set_and_tested(self):
        """Slot 2 is only tested (never set), slot 3 only set, slot 5 set to 2: none of them gets a variable."""
        got, c = self.slots(self.source())
        self.assertEqual(got, {0: 7, 1: 6})
        self.assertEqual(c.stats['Tekken 8 flag slots set to values TTT2 cannot keep (left never set)'], 1)

    def test_taken_variables(self):
        """A state_flags variable of the definition, a variable the donor's moveset tests or one the fighter's ids map
        to (here var 5's set through the stub map) are not taken."""
        got, _ = self.slots(self.source(), flags={0x81bf: 6})
        self.assertEqual(got, {0: 7, 1: 5})
        got, _ = self.slots(self.source(), donor=Donor(reqs=[moveset.var_ids(7)[1]]))
        self.assertEqual(got, {0: 6, 1: 5})
        k = self.source()
        k.req((47, 0))
        got, _ = self.slots(k, req={47: moveset.var_ids(7)[0]})
        self.assertEqual(got, {0: 6, 1: 5})

    def test_variable_ids(self):
        """TTT2's ids of variables 4..10 (>=, <=, ==, set, add, subtract)."""
        self.assertEqual(moveset.var_ids(4), (236, 265, 294, 0x806C, 0x806D, 0x806E))
        self.assertEqual(moveset.var_ids(7), (239, 268, 297, 0x8075, 0x8076, 0x8077))
        self.assertEqual(moveset.var_ids(8), (243, 272, 301, 0x8081, 0x8082, 0x8083))
        self.assertEqual(moveset.var_ids(10), (245, 274, 303, 0x8087, 0x8088, 0x8089))
        self.assertEqual(moveset.VAR_SET[4:], (0x806C, 0x806F, 0x8072))


class Requirements(unittest.TestCase):
    def setUp(self):
        self.k = Flags8(refs=[(0, 'own')])
        self.c = flagged(converter(self.k, req={0: 0}), {0: 7, 1: 6})

    def conv(self, *rows):
        start, ok = self.c.conv_reqs(self.k.req(*rows))
        return converted(self.c, start) if ok else None

    def test_tests(self):
        """Value 1: the variable above 0; value 0: at 0; another value never; a slot never set has value 0."""
        self.assertEqual(self.conv((SLOT_TEST, 0, 1)), [(239, 1)])
        self.assertEqual(self.conv((SLOT_TEST, 1, 0)), [(267, 0)])
        self.assertIsNone(self.conv((SLOT_TEST, 0, 2)))
        self.assertEqual(self.conv((SLOT_TEST, 4, 0)), [])
        self.assertIsNone(self.conv((SLOT_TEST, 4, 1)))

    def test_sets(self):
        """b+2's `3 [(507, 0, 0), (0x815a, 0, 1, 1)]`: set slot 0 for 1 move; value 0 clears; no variable: left out."""
        self.assertEqual(self.conv((SLOT_TEST, 0, 0), (SLOT_SET, 0, 1, 1)), [(268, 0), (0x8075, 1)])
        self.assertEqual(self.conv((SLOT_SET, 1, 2, 0)), [(0x8072, 0)])
        self.assertEqual(self.conv((44, 0), (SLOT_SET, 3, 2, 1)), None)          # (44 unmapped here: false)
        self.assertEqual(self.conv((0, 0), (SLOT_SET, 3, 2, 1)), [(0, 0)])

    def test_tekken7_unchanged(self):
        self.assertIsNone(moveset.FLAG8_REQ['t7'])
        self.assertIsNone(moveset.FLAG8_PROP['t7'])
        self.assertEqual(moveset.WALL8['t7'], {})
        self.assertNotIn(49, moveset.REQ_OVERRIDE['t7'])
        self.assertEqual(moveset.REQ_OR['t7'], {43: (46, 49)})


class Countdown(unittest.TestCase):
    """The rows in front of every converted cancel list, and the properties that set or test a slot."""

    def setUp(self):
        self.k = Flags8(refs=[(0, 'own')] * 3)
        self.c = flagged(converter(self.k, req={0: 0, 44: 46}, prop={STATE: 0x80f8}), {0: 7, 1: 6})

    def cancels(self, *rows):
        start = len(self.k.tables['cancels'])
        self.k.tables['cancels'] += list(rows) + [row(direction=M.LIST_END)]
        return start

    def shown(self, start):
        """A converted cancel list -> [(window, move, conditions, extradata value)] (its end row left out)."""
        out = []
        for r in tagsystem.cancels(self.c.T, start)[:-1]:
            ex = self.c.T['cancel_extras'][r['extradata']]['value'] if r['extradata'] is not None else None
            out.append(((r['win_start'], r['win_end']), r['move_id'], converted(self.c, r['req']), ex))
        return out

    def test_countdown_rows(self):
        """Per variable an action row at frame 1: above 0, take 1 off (unsigned: never below 0)."""
        cl = self.c.conv_cancel_list(self.cancels(row(1, self.k.req((44, 0)))))
        start = tagsystem.write(self.c.T, 'cancels', cl)
        self.assertEqual(self.shown(start), [
            ((1, 1), 0x8001, [(238, 1), (0x8074, 1)], tagcombo.ACTION_ONLY),
            ((1, 1), 0x8001, [(239, 1), (0x8077, 1)], tagcombo.ACTION_ONLY),
            ((1, 32767), 1, [(46, 0)], None)])
        self.assertEqual(self.c.conv_cancel_list(self.cancels(), 'group_cancels', M.LIST_END)[:-1], [])
        c = flagged(converter(self.k, req={0: 0}), {})
        self.assertEqual(len(c.conv_cancel_list(self.cancels(row(1, None)))), 2)    # no slots: nothing added

    def test_property_rows(self):
        """Reina's d/f+1,2: 0x81fa 13 as the move starts when slot 0 is set (by d/f+1's hit) -> an action row after
        the countdown, [(slot 0's variable >= 1), (0x80f8, 13)]; a set as an extra property at frame 5 -> one at 5."""
        xp = self.k.props((0x8001, STATE, 13, self.k.req((SLOT_TEST, 0, 1))), (0x8001, STATE, 7, self.k.req((0, 0))),
                          (5, SLOT_SET, 1, self.k.req((0, 0)), 2, 1))
        rows = self.c.conv_xps(xp, 2)
        self.assertEqual([(x['frame'], x['id'], x['value']) for x in moveset.tagsystem.props(self.c.T, rows)],
                         [(0x8001, 0x80f8, 7)])
        cl = self.c.conv_cancel_list(self.cancels(row(1, self.k.req((44, 0)))))
        self.c.newidx = {2: 0}
        self.c.T['moves'] = [dict(cancel=tagsystem.write(self.c.T, 'cancels', cl))]
        self.c.flag8_rows()
        self.assertEqual(self.shown(self.c.T['moves'][0]['cancel']), [
            ((1, 1), 0x8001, [(238, 1), (0x8074, 1)], tagcombo.ACTION_ONLY),
            ((1, 1), 0x8001, [(239, 1), (0x8077, 1)], tagcombo.ACTION_ONLY),
            ((1, 1), 0x8001, [(239, 1), (0x80f8, 13)], tagcombo.ACTION_ONLY),
            ((5, 5), 0x8001, [(0x8072, 2)], tagcombo.ACTION_ONLY),
            ((1, 32767), 1, [(46, 0)], None)])

    def test_end_props(self):
        """b+2,3's end properties clear its slots: a set of 0."""
        self.k.tables['move_end_props'] = [dict(id=SLOT_SET, value=1, value2=0, value3=0, req=None),
                                           dict(id=SLOT_SET, value=4, value2=0, value3=0, req=None),
                                           dict(id=END8, value=0, value2=0, value3=0, req=None)]
        start = self.c.conv_props('move_end_props', 0)
        self.assertEqual([(r['id'], r['value']) for r in self.c.T['move_end_props'][start:]],
                         [(0x8072, 0), (M.END_REQ['ttt2'], 0)])


class Walls(unittest.TestCase):
    def setUp(self):
        self.k = Flags8(refs=[(0, 'own')])
        self.c = converter(self.k, req={0: 0})

    def test_wall_tests(self):
        """Mikisaka Malaky's (196, 950) (a wall behind within 950) -> TTT2's (176, 950 << 8 | 90); 198 / 200 the sides
        (+x / -x), the odd ids none."""
        for t8, tt in ((194, 174), (196, 176), (197, 177), (198, 178), (200, 180), (201, 181)):
            start, ok = self.c.conv_reqs(self.k.req((t8, 1250)))
            self.assertTrue(ok)
            self.assertEqual(converted(self.c, start), [(tt, 1250 << 8 | 90)])


class Contact(unittest.TestCase):
    def setUp(self):
        self.k = Flags8(refs=[(0, 'own')] * 3)
        self.k.tables['cancel_extras'] = [dict(value=0x80)]
        self.c = flagged(converter(self.k, req={0: 0}), {})

    def cancels(self, *rows):
        i = len(self.k.tables['cancels'])
        self.k.tables['cancels'] += list(rows) + [row(direction=M.LIST_END)]
        return i

    def shown(self, out):
        return [((r['win_start'], r['win_end']), r['move_id'], converted(self.c, r['req'])) for r in out[:-1]]

    def test_hit_and_contact(self):
        """51 (the move hit) is 46 outside a cancel list, 49 (hit or block) too; in a cancel list 49 is one row on the
        hit (kept in a latch: HIT_HELD) and one on 49."""
        start, ok = self.c.conv_reqs(self.k.req((51, 0)))
        self.assertEqual(converted(self.c, start), [(46, 0)])
        start, ok = self.c.conv_reqs(self.k.req((49, 0)))
        self.assertEqual(converted(self.c, start), [(46, 0)])
        i = self.cancels(dict(row(2, self.k.req((49, 0)), button=0x4000_0001, win=(1, 20)), extradata=0))
        self.assertEqual(self.shown(self.c.conv_cancel_list(i)), [
            ((1, 32767), 0x8001, [(46, 0), (0x8096 + 9, 1)]), ((1, 20), 2, [(316, 1)]), ((1, 20), 2, [(49, 0)])])

    def test_hit_held(self):
        """u+4's `[(51)] 17-17 -> Baobab Mihira` (the hit on frame 16, TTT2's 46 true on that frame only): the list's
        first row sets a latch none of its rows uses on the hit's frame, the row tests it; its own latch 3 (361) taken,
        latch 2 (315); its action ids alike (0x80c5 + 3k, 0x8152 by number); a list without the test gets nothing."""
        i = self.cancels(dict(row(2, self.k.req((51, 0)), direction=0x3ee, win=(17, 17)), extradata=0))
        self.assertEqual(self.shown(self.c.conv_cancel_list(i)), [
            ((1, 32767), 0x8001, [(46, 0), (0x8096 + 9, 1)]), ((17, 17), 2, [(316, 1)])])
        self.assertEqual(self.c.stats['Tekken 8 "the move hit": cancel lists keeping it in a latch'], 1)
        i = self.cancels(row(1, self.k.req((361, 0), (0x80c5 + 3 * 2, 1))), row(2, self.k.req((51, 0)), win=(17, 17)))
        self.assertEqual(self.shown(self.c.conv_cancel_list(i))[0], ((1, 32767), 0x8001, [(46, 0), (0x8096 + 3, 1)]))
        i = self.cancels(row(1, self.k.req((476, 2, 1), (0x8152, 1, 1))), row(2, self.k.req((51, 0)), win=(17, 17)))
        self.assertEqual(self.shown(self.c.conv_cancel_list(i))[0], ((1, 32767), 0x8001, [(46, 0), (0x8096 + 9, 1)]))
        i = self.cancels(row(1, self.k.req((0, 0))))
        self.assertEqual(self.shown(self.c.conv_cancel_list(i)), [((1, 32767), 1, [(0, 0)])])

    def test_hit_held_kept_46(self):
        """Every latch taken, or a group list (shared by moves): 46 as before; a list whose only such row is false
        gets no action row."""
        i = self.cancels(row(1, self.k.req((358, 0), (359, 0), (360, 0), (361, 0))), row(2, self.k.req((51, 0))))
        self.assertEqual(self.shown(self.c.conv_cancel_list(i)), [((1, 32767), 1, [(313, 0), (314, 0), (315, 0), (316, 0)]),
                                                                ((1, 32767), 2, [(46, 0)])])
        g = len(self.k.tables['group_cancels'])
        self.k.tables['group_cancels'] += [row(2, self.k.req((51, 0))), row(direction=M.GROUP_END)]
        self.assertEqual(converted(self.c, self.c.conv_cancel_list(g, 'group_cancels', M.GROUP_END)[0]['req']), [(46, 0)])
        i = self.cancels(row(2, self.k.req((51, 0), (777, 0))), row(1, self.k.req((0, 0))))
        self.assertEqual(self.shown(self.c.conv_cancel_list(i)), [((1, 32767), 1, [(0, 0)])])

    def test_projectile_whiff(self):
        """A projectile_whiffs move's list (Azazel's d+3+4: `[(48)] 25-40 -> 4 pillars, 40-40 -> 3`): the whiff test is
        the hit latch still 0, decided at the window's end, the latch set on the hit's frame first; another list's 48
        stays the id maps' (PROJECTILE_WHIFF)."""
        rows = (dict(row(2, self.k.req((48, 0)), win=(25, 40)), start_frame=40),
                dict(row(1, self.k.req((0, 0)), win=(40, 40)), start_frame=40))
        self.c = flagged(converter(self.k, req={0: 0, 48: 51}), {})
        i = self.cancels(*rows)
        self.assertEqual(self.shown(self.c.conv_cancel_list(i)), [((25, 40), 2, [(51, 0)]), ((40, 40), 1, [(0, 0)])])
        j = self.cancels(*rows)
        self.c.proj_whiffs = frozenset({j})
        out = self.c.conv_cancel_list(j)
        self.assertEqual(self.shown(out), [((1, 32767), 0x8001, [(46, 0), (0x8096 + 9, 1)]),
                                           ((40, 40), 2, [(316, 0)]), ((40, 40), 1, [(0, 0)])])
        self.assertEqual([r['start_frame'] for r in out[1:3]], [40, 40])
        self.assertEqual(self.c.stats['Tekken 8 whiff tests of projectile moves -> "the move hit" latch still 0'], 1)
        self.assertFalse(self.c.whiff_list)


if __name__ == '__main__':
    unittest.main()
