"""Tekken 8's tornado entry (724) in a string whose earlier hit lifted a standing opponent (convert/moveset.py
LIFTED_SCREW, lifted_screws, lift_rows, conv_hitconds): it tests "opponent airborne" and that the string began on an
opponent on its feet, and plays its own reaction; every other tornado entry stays false (REQ_FALSE), among them one
that another way enters too (a command of the stance, a transition, a shared group or hit-condition list, a lifting
attack entered past its first active frame), and Tekken 7's screws are not looked at. Made-up movesets only.

    python3 -m unittest tests/test_tekken8_tornado.py
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
from ttt2char.movesets import REACTION_MOVE_FIELDS, Moveset  # noqa: E402
import test_tekken8_flags  # noqa: E402

AIR8, AIR = 723, 466                 # Tekken 8's "opponent airborne" and TTT2's (the id maps' pair)
SCREW8 = moveset.SCREW['t8']


class Strings(Source8):
    """A made-up Tekken 8 moveset with hit conditions, reactions and cancel lists."""

    def __init__(self):
        super().__init__()
        for t in ('moves', 'cancels', 'group_cancels', 'hit_conditions', 'reactions'):
            self.tables[t] = []
        self.stand = self.move()
        self.up = self.move(air=1)                          # a reaction with airborne frames (a lift)
        self.flat = self.move()                             # a reaction on the ground

    def move(self, air=0, hit=None, first_active=0, hitlevel=0):
        self.tables['moves'].append(dict(anim=0, anim_len=0, airborne_start=air, airborne_end=0, ground_fall=0,
                                         transition=0x8000, hit_condition=hit, first_active=first_active,
                                         hitlevel=hitlevel, cancel=None))
        return len(self.tables['moves']) - 1

    def reaction(self, default, ch=None):
        r = dict.fromkeys(REACTION_MOVE_FIELDS, self.flat)
        r.update(default=default, ch=self.flat if ch is None else ch)
        self.tables['reactions'].append(r)
        return len(self.tables['reactions']) - 1

    def hits(self, *entries):
        """[(requirement rows, reaction)] -> the hit-condition list's index (the last entry: no requirement)."""
        start = len(self.tables['hit_conditions'])
        for rows, rx in entries:
            self.tables['hit_conditions'].append(dict(req=self.req(*rows), damage=10, reactions=rx))
        return start

    def attack(self, default, ch=None):
        """An attack, active from frame 10, whose hit plays reaction moves default (ch on a counter hit)."""
        return self.move(hit=self.hits(((), self.reaction(default, ch))), first_active=10, hitlevel=4)

    def tornado(self):
        """A follow-up with a tornado entry, then an air entry and the standing one."""
        return self.move(hit=self.hits((((SCREW8, 1, 40),), 900), (((AIR8, 0),), 901), ((), 902)))

    def cancels(self, mv, *rows, table='cancels'):
        """rows: (move id, window start, window end[, starting frame, keeping the frame]) or ('group', its index) ->
        the move's cancel list."""
        end = M.GROUP_END if table == 'group_cancels' else M.LIST_END
        start = len(self.tables[table])
        for r in rows:
            d, mid, ws, we = (M.GROUP, r[1], 1, 1) if r[0] == 'group' else (16, r[0], r[1], r[2])
            extra = None
            if len(r) > 4 and r[4]:
                extra = len(self.tables['cancel_extras'])
                self.tables['cancel_extras'].append(dict(value=moveset.tagcombo.KEEP_FRAMES | 1))
            self.tables[table].append(dict(direction=d, button=0, req=None, extradata=extra, win_start=ws, win_end=we,
                                           start_frame=r[3] if len(r) > 3 else ws, move_id=mid, option=0))
        self.tables[table].append(dict(direction=end, button=0, req=None, extradata=None, win_start=0, win_end=0,
                                       start_frame=0, move_id=0, option=0))
        if mv is not None:
            self.tables['moves'][mv]['cancel'] = start
        return start


class Lifted(unittest.TestCase):
    def setUp(self):
        k = Strings()
        self.k = k
        self.launcher, self.poke = k.attack(k.up), k.attack(k.flat)
        self.counter = k.attack(k.flat, ch=k.up)                     # lifts on a counter hit only (Miary Zo's b+1)
        self.after_launch, self.after_poke, self.after_ch, self.variant, self.in_group, self.alone = (
            k.tornado() for _ in range(6))
        group = k.cancels(None, (self.in_group, 12, 30), table='group_cancels')
        k.cancels(self.launcher, (self.after_launch, 10, 21),       # open at the first active frame: after the hit
                  (self.variant, 5, 8),                             # before it: picks a variant (#1675)
                  ('group', group))
        k.cancels(self.poke, (self.after_poke, 10, 21))
        k.cancels(self.counter, (self.after_ch, 16, 16))
        # tornado moves a lifting attack's list enters after its hit, and another way too: a command of the stance
        # (Azazel's d+1+2), a transition, a group another list has, a move with the same hit-condition list; and one
        # whose lifting attack a row enters keeping its frame past the first active one (frame 12 of 10), one whose
        # attack a row enters keeping frame 8 (kept), one a second lifting attack enters before its hit (kept; that
        # attack's list gets the lift rows too)
        self.command, self.goes_on, self.grouped, self.shared, self.after_late, self.after_jump, self.with_variant = (
            k.tornado() for _ in range(7))
        self.lifters2 = [k.attack(k.up) for _ in range(8)]
        stance, other, ends, late, jump = k.move(), k.move(), k.move(), k.move(), k.move()
        group2 = k.cancels(None, (self.grouped, 12, 30), table='group_cancels')
        for attack, mv in zip(self.lifters2, (self.command, self.goes_on, self.shared, self.after_late, self.after_jump,
                                              self.with_variant)):
            k.cancels(attack, (mv, 10, 21))
        k.cancels(self.lifters2[6], ('group', group2))
        k.cancels(self.lifters2[7], (self.with_variant, 1, 1))
        k.cancels(stance, (self.command, 1, 32767))
        k.tables['moves'][ends]['transition'] = self.goes_on
        k.cancels(other, ('group', group2))
        k.move(hit=k.tables['moves'][self.shared]['hit_condition'])
        k.cancels(late, (self.lifters2[3], 1, 12, 1, True))
        k.cancels(jump, (self.lifters2[4], 1, 8, 8, True))

    def hc(self, *moves):
        return {self.k.tables['moves'][i]['hit_condition'] for i in moves}

    def cl(self, *moves):
        return {self.k.tables['moves'][i]['cancel']: 10 for i in moves}

    def test_lifted_screws(self):
        hcs = self.hc(self.after_launch, self.in_group, self.after_ch, self.after_jump, self.with_variant)
        self.assertEqual(moveset.lifted_screws(self.k, SCREW8), (hcs, self.cl(
            self.launcher, self.counter, self.lifters2[4], self.lifters2[5], self.lifters2[7])))

    def test_lifting_list_first_active(self):
        """A list two lifting attacks with different first active frames share: neither's (no window for both)."""
        k = self.k
        k.tables['moves'][k.attack(k.up)]['cancel'] = k.tables['moves'][self.launcher]['cancel']
        k.tables['moves'][-1]['first_active'] = 12
        hcs, lifters = moveset.lifted_screws(k, SCREW8)
        self.assertNotIn(k.tables['moves'][self.launcher]['cancel'], lifters)
        self.assertNotIn(k.tables['moves'][self.after_launch]['hit_condition'], hcs)

    def test_no_screws(self):
        self.assertEqual(moveset.lifted_screws(self.k, 615), (set(), {}))

    def converter(self, free=(2, 7)):
        c = converter(self.k, req={AIR8: AIR})
        c.T.update(hit_conditions=[], reactions=[], cancel_extras=[])
        c.conv_reaction = lambda rx: rx
        c.bound_reaction = c.after_bound_reaction = None
        c.free_vars, c.extra_index = list(free), {}
        return c

    def conv(self, mv, free=(2, 7)):
        c = self.converter(free)
        start = c.conv_hitconds(self.k.tables['moves'][mv]['hit_condition'])
        return [(converted(c, h['req']), h['reactions']) for h in c.T['hit_conditions'][start:]], c

    def test_tornado_after_a_lift_launches(self):
        """The tornado entry tests "opponent airborne" (parameter 1, 40: the hit's side effect, left out) and that the
        string began on an opponent on its feet (variable 2, LIFT_VAR, the first free one), and keeps its reaction:
        the launch, with no tornado state."""
        hits, c = self.conv(self.after_launch)
        began = (moveset.var_ids(2)[0], 1)
        self.assertEqual(hits, [([(AIR, 0), began], 900), ([(AIR, 0)], 901), ([], 902)])
        self.assertEqual(c.stats['Tekken 8 tornado entries of a string that lifts -> "opponent airborne"'], 1)

    def test_other_tornados_stay_false(self):
        """A tornado no lift leads into (a juggle's), or one another way enters too: its air entry plays, as
        before. Azazel's d+1+2 is a command of his stance too: after his 1517 lifted, the variable could still be set
        in the juggle, past the bound, where Tekken 8's counter is spent."""
        for mv in (self.after_poke, self.variant, self.alone, self.command, self.goes_on, self.grouped, self.shared,
                   self.after_late):
            hits, c = self.conv(mv)
            self.assertEqual(hits, [([(AIR, 0)], 901), ([], 902)])
            self.assertEqual(c.stats['hit condition entry dropped'], 1)

    def test_no_free_variable(self):
        """Without a free moveset variable the string's tornado entry stays false too."""
        hits, c = self.conv(self.after_launch, free=())
        self.assertEqual(hits, [([(AIR, 0)], 901), ([], 902)])
        self.assertEqual(c.lift_rows(self.k.tables['moves'][self.launcher]['cancel']), [])

    def test_lift_rows(self):
        """The lifting attacks' cancel lists start with two action rows on the frames up to the first active one
        (10): the variable set to LIFT_FRAMES, then to 0 when the opponent is airborne (in a juggle). Other lists get
        none."""
        c = self.converter()
        rows = c.lift_rows(self.k.tables['moves'][self.launcher]['cancel'])
        put = moveset.var_ids(2)[3]
        self.assertEqual([converted(c, r['req']) for r in rows], [[(put, moveset.LIFT_FRAMES)], [(AIR, 0), (put, 0)]])
        self.assertEqual({(r['win_start'], r['win_end'], r['start_frame'], r['move_id']) for r in rows},
                         {(1, 10, 1, 0x8001)})
        self.assertEqual({c.T['cancel_extras'][r['extradata']]['value'] for r in rows}, {moveset.tagcombo.ACTION_ONLY})
        self.assertEqual(c.lift_rows(self.k.tables['moves'][self.counter]['cancel'])[0]['req'], rows[0]['req'])
        self.assertEqual(c.lift_rows(self.k.tables['moves'][self.poke]['cancel']), [])

    def test_flag_variable(self):
        """Without LIFT_VAR, a variable the flag slots left: its own ids."""
        hits, _ = self.conv(self.after_launch, free=(10,))
        self.assertEqual(hits[0][0], [(AIR, 0), (moveset.var_ids(10)[0], 1)])

    def test_tekken7_screws_untouched(self):
        """Tekken 7's screws stay false everywhere: its moves are not looked at, its lists converted as before."""
        self.assertFalse(moveset.LIFTED_SCREW['t7'])
        self.assertIn(moveset.SCREW['t7'], moveset.REQ_FALSE['t7'])
        t7 = Moveset()
        t7.game = 't7'
        t7.tables = {'requirements': [], 'hit_conditions': []}
        for conds, rx in (([moveset.SCREW['t7']], 5), ([], 6)):
            ri = len(t7.tables['requirements'])
            t7.tables['requirements'] += [dict(condition=c, param=0) for c in conds + [M.END_REQ['t7']]]
            t7.tables['hit_conditions'].append(dict(req=ri, damage=10, reactions=rx))
        c = moveset.Converter.__new__(moveset.Converter)
        self.assertEqual(c.game, 't7')
        c.k, c.T, c.stats = t7, dict(hit_conditions=[], reactions=[]), collections.Counter()
        calls = []
        c.conv_reqs = lambda i, overrides=None: calls.append(overrides) or (0, bool(i))     # (the screw: false)
        c.conv_reaction = lambda rx: rx
        c.bound_reaction = None
        orig = moveset.lifted_screws
        moveset.lifted_screws = lambda *a: self.fail('Tekken 7 moves looked at')
        try:
            start = c.conv_hitconds(0)
            self.assertEqual(c.lift_rows(0), [])
        finally:
            moveset.lifted_screws = orig
        self.assertEqual(calls, [None, None])
        self.assertEqual([h['reactions'] for h in c.T['hit_conditions'][start:]], [6])


class Variables(test_tekken8_flags.Slots):
    """flag8_slots also leaves the variables LIFTED_SCREW can take: LIFT_VAR (counted down each frame) when no state
    flag, the donor's moveset or the fighter's ids use it, then what the flag slots left."""
    test_set_and_tested = test_taken_variables = test_variable_ids = None

    def test_free_vars(self):
        _, c = self.slots(self.source())                                   # (slots 0 and 1 take 7 and 6)
        self.assertEqual(c.free_vars, [2, 5, 10, 4])
        _, c = self.slots(self.source(), donor=test_tekken8_flags.Donor(reqs=[moveset.var_ids(2)[0]]))
        self.assertEqual(c.free_vars, [5, 10, 4])
        k = self.source()
        k.req((47, 0))
        _, c = self.slots(k, req={47: moveset.var_ids(2)[3]})
        self.assertEqual(c.free_vars, [5, 10, 4])
        _, c = self.slots(self.source(), flags={0x81bf: 2})                # (a state flag of the definition)
        self.assertEqual(c.free_vars, [5, 10, 4])

    def test_lift_var_ids(self):
        self.assertEqual(moveset.LIFT_VAR, 2)
        self.assertEqual(moveset.var_ids(2), (234, 263, 292, 0x8066))


if __name__ == '__main__':
    unittest.main()
