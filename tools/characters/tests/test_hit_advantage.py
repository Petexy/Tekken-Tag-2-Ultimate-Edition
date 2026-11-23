"""Unit tests of a hit's set advantage (move_overrides.hit_advantage: Azazel's d/f+3+4, whose hold Tekken 8 keeps for
170 frames), on made-up data (no game files needed), and of his definition's entry.

    python3 -m unittest tests.test_hit_advantage
"""
import collections
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from ttt2char import pack  # noqa: E402
from ttt2char.characters import azazel  # noqa: E402
from ttt2char.convert import idmaps as M, move_overrides as O, tagsystem as T  # noqa: E402

STANCE = 0x8001


def converter(thrown=True):
    """A made-up moveset: move 0 the attack (its end row at 130; thrown: its projectile's row at 79, else active
    from 80), move 1 the hold (end row at 170), move 2 the lying opponent's reaction, move 3 another attack."""
    c = types.SimpleNamespace(kn={'prison': 0, 'hold': 1, 'down': 2, 'other': 3}, newidx={0: 0, 1: 1, 2: 2, 3: 3},
                              stats=collections.Counter(), thrown={})
    if thrown:
        c.thrown = {'prison': dict(frame=79)}
    c.T = {'requirements': [dict(condition=0, param=0), dict(condition=T.TT_END, param=0),      # 0: always
                            dict(condition=T.TT_END, param=0),                                  # 2: empty
                            dict(condition=466, param=0), dict(condition=T.TT_END, param=0)]}   # 3: in the air

    def end(at):
        return dict(direction=M.LIST_END, button=0, req=0, move_id=STANCE, win_start=at, win_end=32767, start_frame=at,
                    extradata=0, option=0)
    c.T['cancels'] = [end(130), end(170), end(60), end(40)]
    held = dict.fromkeys(O.GROUND_HITS, 1)
    c.T['reactions'] = [dict(held, block=1, crouch_block=1, wallslump=2, downed=2, pb_front=7),   # 0: on the ground
                        dict(dict.fromkeys(O.REACTION_MOVES, 2), pb_front=8),                     # 1: in the air
                        dict(dict.fromkeys(O.REACTION_MOVES, 2), pb_front=9)]                     # 2: the other attack's
    c.T['hit_conditions'] = [dict(req=3, damage=20, reactions=1), dict(req=2, damage=20, reactions=0),
                             dict(req=2, damage=10, reactions=2)]
    first = (0, 0) if thrown else (80, 90)
    c.T['moves'] = [dict(cancel=0, hit_condition=0, first_active=first[0], last_active=first[1]),
                    dict(cancel=1, hit_condition=None, first_active=0, last_active=0),
                    dict(cancel=2, hit_condition=None, first_active=0, last_active=0),
                    dict(cancel=3, hit_condition=2, first_active=12, last_active=13)]
    return c


class HitAdvantageTest(unittest.TestCase):
    def check(self, c, frames, at):
        before = {k: [dict(r) for r in v] for k, v in c.T.items()}
        O.hit_advantage(c, 'prison', {'reaction': 'hold', 'frames': frames})
        rows = T.cancels(c.T, c.T['moves'][1]['cancel'])
        self.assertEqual(len(rows), 2)
        # the opponent can act from the end row on: his move's end row (130) - the frame his hit lands (80) + frames
        self.assertEqual((rows[1]['direction'], rows[1]['win_start'], rows[1]['win_end'], rows[1]['start_frame'],
                          rows[1]['move_id']), (M.LIST_END, at, 32767, at, STANCE))
        # ... and one who does nothing stands 10 frames later (a row taken by the game, once)
        self.assertTrue(T.is_automatic(rows[0]))
        self.assertEqual((rows[0]['win_start'], rows[0]['win_end'], rows[0]['start_frame'], rows[0]['move_id']),
                         (at + O.END_BLEND, at + O.END_BLEND, 1, STANCE))
        self.assertEqual(T.reqs(c.T, rows[0]['req']), [(0, 0)])
        for k, v in before.items():                 # (nothing else: the attack, its hits, the other moves' lists)
            if k == 'moves':
                self.assertEqual([m for i, m in enumerate(c.T[k]) if i != 1], [m for i, m in enumerate(v) if i != 1])
                self.assertEqual({f: x for f, x in c.T[k][1].items() if f != 'cancel'},
                                 {f: x for f, x in v[1].items() if f != 'cancel'})
            else:
                self.assertEqual(c.T[k][:len(v)], v)
        self.assertEqual(c.stats['hit reactions ended for a set advantage (hit_advantage)'], 1)

    def test_a_thrown_hit_lands_the_frame_after_its_row(self):
        self.check(converter(), 15, 130 - 80 + 15)

    def test_a_hit_of_its_own_lands_on_its_first_active_frame(self):
        self.check(converter(thrown=False), 15, 130 - 80 + 15)

    def test_even_and_behind(self):
        self.check(converter(), 0, 50)
        self.check(converter(), -10, 40)

    def test_a_hold_another_move_uses_is_refused(self):
        c = converter()
        c.T['reactions'][2]['ch'] = 1
        with self.assertRaises(ValueError):
            O.hit_advantage(c, 'prison', {'reaction': 'hold', 'frames': 15})

    def test_a_reaction_the_attack_does_not_give_is_refused(self):
        with self.assertRaises(ValueError):                 # (only a lying opponent's)
            O.hit_advantage(converter(), 'prison', {'reaction': 'down', 'frames': 15})
        with self.assertRaises(ValueError):
            O.hit_advantage(converter(), 'other', {'reaction': 'hold', 'frames': 15})

    def test_no_longer_hold_and_no_second_time(self):
        with self.assertRaises(ValueError):                 # (the hold would have to last past its own end row)
            O.hit_advantage(converter(), 'prison', {'reaction': 'hold', 'frames': 120})
        c = converter()
        O.hit_advantage(c, 'prison', {'reaction': 'hold', 'frames': 15})
        with self.assertRaises(ValueError):                 # (it has its own ending row already)
            O.hit_advantage(c, 'prison', {'reaction': 'hold', 'frames': 10})

    def test_apply_runs_it(self):
        c = converter()
        c.defn = types.SimpleNamespace(MOVESET={'hit_advantage': {'prison': {'reaction': 'hold', 'frames': 15}}})
        c.dn, c.game, c.map_req = {}, 't8', lambda i: None
        O.apply(c)
        self.assertEqual(T.cancels(c.T, c.T['moves'][1]['cancel'])[-1]['win_start'], 65)


class AzazelPrisonTest(unittest.TestCase):
    def test_his_crystal_prison_leaves_him_15_frames_ahead(self):
        self.assertEqual(azazel.MOVESET['hit_advantage'],
                         {'key:477c5f91': {'reaction': 'key:bbbf54b2', 'frames': 15}})
        self.assertIn('key:477c5f91', azazel.THROWN)        # (thrown: its hit lands the frame after the row's)
        self.assertEqual(azazel.THROWN['key:477c5f91']['frame'], 79)

    def test_packs_made_before_are_offered_an_update(self):
        self.assertEqual(azazel.REVISION, 1)
        self.assertEqual(pack.revision(azazel), pack.REVISION + 1)


if __name__ == '__main__':
    unittest.main()
