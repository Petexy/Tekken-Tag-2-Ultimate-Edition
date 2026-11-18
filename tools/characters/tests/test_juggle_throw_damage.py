"""Unit tests of MOVESET['juggle_throw_damage'] (convert/move_overrides.py): an air throw that ends a juggle deals the
definition's damage through a copy of the move, caught only when the opponent is down (TTT2's 124); a jumping
opponent still gets the move as it was. Made-up tables.

    python3 -m unittest tests.test_juggle_throw_damage
"""
import collections
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import move_overrides as O  # noqa: E402
from ttt2char.convert import tagsystem as T  # noqa: E402

ATTEMPT, OTHER_ATTEMPT, AIR, GROUND, STANCE = range(5)


def converter():
    c = types.SimpleNamespace(kn={'air': 10, 'ground': 11}, newidx={10: AIR, 11: GROUND}, stats=collections.Counter(),
                              defn=types.SimpleNamespace(MOVESET={'juggle_throw_damage': {'air': 20}}),
                              strings=b'', str_off={})

    def string(s):
        c.str_off.setdefault(s, len(c.str_off))
        return c.str_off[s]
    c.string = string
    c.T = {'moves': [], 'cancels': [], 'requirements': [], 'hit_conditions': [], 'extra_move_properties': [],
           'group_cancels': []}

    def req(*items):
        return T.write(c.T, 'requirements', [dict(condition=a, param=b) for a, b in items] +
                       [dict(condition=T.TT_END, param=0)])

    def row(target, rq, direction=0):
        return dict(direction=direction, button=0, req=rq, extradata=3, win_start=12, win_end=14, start_frame=12,
                    move_id=target, option=0)
    attempt = T.write(c.T, 'cancels', [row(GROUND, req((3, 1750))), row(AIR, req((27, 2536))),
                                       row(STANCE, req((0, 0)), M.LIST_END)])
    end = T.write(c.T, 'cancels', [row(STANCE, req((0, 0)), M.LIST_END)])
    sound = dict(frame=20, id=0x82f9, value=0x0200000a)
    c.sound = sound
    props = T.write(c.T, 'extra_move_properties', [sound, dict(frame=69, id=0x8058, value=60),
                                                   dict(frame=0, id=0, value=0)])
    hit = T.write(c.T, 'hit_conditions', [dict(req=req(), damage=60, reactions=360)])
    c.T['moves'] = [dict(name=0, cancel=attempt, hit_condition=None, extraprops=None),
                    dict(name=1, cancel=attempt, hit_condition=None, extraprops=None),       # (shares the list)
                    dict(name=2, cancel=end, hit_condition=hit, extraprops=props, anim=7),
                    dict(name=3, cancel=end, hit_condition=hit, extraprops=props, anim=8),
                    dict(name=4, cancel=end, hit_condition=None, extraprops=None)]
    return c


class JuggleThrowDamage(unittest.TestCase):
    def setUp(self):
        self.c = converter()
        self.before = {t: [dict(r) for r in self.c.T[t]] for t in ('cancels', 'requirements', 'hit_conditions',
                                                                   'extra_move_properties')}
        O.juggle_throw_damage(self.c, 'air', 20)
        self.copy = len(self.c.T['moves']) - 1

    def test_copy_deals_the_damage(self):
        """The copy: the move's animation and end, 20 in its hit condition and its points row; its other property
        rows are the move's own rows (one object: later passes renumber effects in both)."""
        c, x = self.c, self.c.T['moves'][self.copy]
        self.assertEqual(self.copy, 5)
        self.assertEqual(x['name'], c.str_off['airJ'])
        self.assertEqual((x['anim'], x['cancel']), (7, c.T['moves'][AIR]['cancel']))
        self.assertEqual([(h['damage'], h['reactions']) for h in T.hits(c.T, x['hit_condition'])], [(20, 360)])
        props = T.props(c.T, x['extraprops'])
        self.assertEqual([(p['frame'], p['id'], p['value']) for p in props],
                         [(20, 0x82f9, 0x0200000a), (69, 0x8058, 20)])
        self.assertIs(props[0], c.sound)

    def test_move_itself_unchanged(self):
        """Tekken 7's 60 stays on the move (a jumping opponent); the tables' earlier rows are untouched."""
        c = self.c
        move = c.T['moves'][AIR]
        self.assertEqual([h['damage'] for h in T.hits(c.T, move['hit_condition'])], [60])
        self.assertEqual([p['value'] for p in T.props(c.T, move['extraprops'])], [0x0200000a, 60])
        for t, rows in self.before.items():
            self.assertEqual(c.T[t][:len(rows)], rows, t)

    def test_catch_row_before_the_move(self):
        """The copy's catch row: the move's row with 'the opponent is down' (124) added, just before it."""
        c = self.c
        rows = T.cancels(c.T, c.T['moves'][ATTEMPT]['cancel'])
        self.assertEqual([r['move_id'] for r in rows], [GROUND, self.copy, AIR, STANCE])
        self.assertEqual([T.reqs(c.T, r['req']) for r in rows[:3]], [[(3, 1750)], [(27, 2536), (124, 0)], [(27, 2536)]])
        self.assertEqual({k: v for k, v in rows[1].items() if k not in ('req', 'move_id')},
                         {k: v for k, v in rows[2].items() if k not in ('req', 'move_id')})
        self.assertEqual(c.stats['air throws: catch rows given a juggle copy'], 1)

    def test_shared_list_stays_shared(self):
        c = self.c
        self.assertEqual(c.T['moves'][ATTEMPT]['cancel'], c.T['moves'][OTHER_ATTEMPT]['cancel'])
        self.assertEqual(c.T['moves'][STANCE]['cancel'], c.T['moves'][AIR]['cancel'])

    def test_through_apply(self):
        """The definition's MOVESET entry runs it (move_overrides.apply)."""
        c = converter()
        c.game, c.map_req = 't7', lambda i: None             # (no string buffer: the strings pass does nothing)
        O.apply(c)
        self.assertEqual(len(c.T['moves']), 6)
        self.assertEqual(c.stats['air throws: juggle copies (their own damage)'], 1)

    def test_refused(self):
        """Not an air throw catch (a ground throw's row), or no points row: an error, not a silent change."""
        with self.assertRaises(ValueError):
            O.juggle_throw_damage(converter(), 'ground', 20)
        c = converter()
        c.T['extra_move_properties'][1]['value'] = 0
        with self.assertRaises(ValueError):
            O.juggle_throw_damage(c, 'air', 20)
        with self.assertRaises(ValueError):
            O.juggle_throw_damage(converter(), 'air', 0)

    def test_gigas(self):
        """Gigas's Claw Hammer (Cz_air_n): 20 when it ends a juggle."""
        from ttt2char.characters import gigas
        self.assertEqual(gigas.MOVESET['juggle_throw_damage'], {'Cz_air_n': 20})


if __name__ == '__main__':
    unittest.main()
