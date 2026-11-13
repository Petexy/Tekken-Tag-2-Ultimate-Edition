"""Unit tests of hit points on a cloth link (weapons.parent_index / append_tekken8 / points_of / of_skeleton: Azazel's
tail) and of grabs that only a hit starts (move_overrides.hit_grab: his b+1), on made-up data (no game files needed).

    python3 -m unittest tests.test_tail_points
"""
import collections
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from ttt2char.convert import idmaps as M, move_overrides as O, tagsystem as T, weapons  # noqa: E402
from ttt2char.ttt2 import bone  # noqa: E402
import test_retarget as TR  # noqa: E402


def with_link(number=400):
    """test_retarget's TTT2 skeleton with a made-up cloth link cha:OPT<number>_cloth90_0_7 under KOSHI_jnt."""
    bon = TR.ttt2_bon()
    bon['opt'] = [0] * len(bon['names'])
    hw = bone.world_matrices(bon)
    world = hw[weapons.parent_index(bon, 'KOSHI_jnt')].copy()
    world[:3, 3] += (0.0, -300.0, -2500.0)
    out = weapons.append_tekken8(bon, dict(bone='cloth90_0_7', parent='KOSHI_jnt', number=number), world)
    return out[0], out[1]


class LinkPointTest(unittest.TestCase):
    def test_a_point_under_a_cloth_link(self):
        bon, link = with_link()
        hw = bone.world_matrices(bon)
        w = dict(bone='tail_tip', parent='cloth90_0_7', points={25: ('origin', 0)})     # (the link by its name)
        self.assertEqual(weapons.parent_index(bon, 'cloth90_0_7'), link)
        bon, index, number, used = weapons.append_tekken8(bon, w, hw[link], [(25, 0, hw[link][:3, 3])])
        self.assertEqual((bon['parent'][index], number, used), (link, weapons.STILL_FIRST, [weapons.POINT_FIRST]))
        self.assertEqual(weapons.points_of(bon['names']), {25: weapons.POINT_LOCATION})
        self.assertEqual(weapons.of_skeleton(bon, [w]), [(20, link, [(0, 0)], None)])  # (the link itself: no climb)
        point = bone.world_matrices(bon)[index + 1][:3, 3]
        self.assertTrue(np.allclose(point, hw[link][:3, 3], atol=1e-3))

    def test_a_point_under_a_weapon_is_still_refused(self):
        bon, _ = with_link()
        hw = bone.world_matrices(bon)
        sheath = dict(bone='sheath', parent='KOSHI_jnt')
        bon, s, _, _ = weapons.append_tekken8(bon, sheath, hw[weapons.parent_index(bon, 'KOSHI_jnt')])
        with self.assertRaises(ValueError):
            weapons.append_tekken8(bon, dict(bone='sword', parent='sheath'), bone.world_matrices(bon)[s],
                                   [(0x23, 1, np.zeros(3))])


class HitGrabTest(unittest.TestCase):
    def setUp(self):
        c = types.SimpleNamespace(kn={'b1': 0, 'hold': 1, 'f1': 2}, newidx={0: 0, 1: 1, 2: 2},
                                  stats=collections.Counter())
        c.T = {'requirements': [], 'cancels': [], 'hit_conditions': [], 'reactions': []}

        def req(*items):
            n = len(c.T['requirements'])
            c.T['requirements'] += [dict(condition=a, param=b) for a, b in items] + [dict(condition=T.TT_END, param=0)]
            return n

        def add(table, value):
            c.T[table].append(value)
            return len(c.T[table]) - 1
        c.add = add
        always, empty, air = req((0, 0)), req(), req((466, 0))
        row = dict(direction=0, button=0, req=always, move_id=1, win_start=12, win_end=12, start_frame=12,
                   extradata=0, option=0)
        end = dict(row, direction=M.LIST_END, req=always, move_id=0x8001, win_start=55, win_end=32767, start_frame=55)
        c.T['cancels'] = [row, end]
        c.T['reactions'] = [dict(default=10, ch=10, crouch=10, block=10, crouch_block=11, pb_block=3, pb_front=3),
                            dict(default=20, ch=20, crouch=20, block=21, crouch_block=22, pb_block=4, pb_front=5),
                            dict(default=30, block=0, crouch_block=0, pb_block=0)]
        c.T['hit_conditions'] = [dict(req=empty, damage=0, reactions=0),
                                 dict(req=air, damage=12, reactions=2), dict(req=empty, damage=12, reactions=1)]
        c.T['moves'] = [dict(cancel=0, hit_condition=0, first_active=12, last_active=12),
                        dict(cancel=0, hit_condition=0, first_active=0, last_active=0),
                        dict(cancel=0, hit_condition=1, first_active=11, last_active=11)]
        self.c = c
        self.before = {k: [dict(r) for r in v] for k, v in c.T.items() if k != 'moves'}

    def test_the_hold_needs_a_hit_and_a_block_is_a_guard(self):
        c = self.c
        O.hit_grab(c, 'b1', {'grab': 'hold', 'guard_as': 'f1'})
        rows = T.cancels(c.T, c.T['moves'][0]['cancel'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(T.reqs(c.T, rows[0]['req']), [(46, 0)])
        self.assertEqual((rows[0]['win_start'], rows[0]['win_end'], rows[0]['start_frame'], rows[0]['move_id']),
                         (12, 13, 12, 1))
        self.assertEqual(rows[1]['move_id'], 0x8001)
        hit = T.hits(c.T, c.T['moves'][0]['hit_condition'])
        self.assertEqual(len(hit), 1)
        r = c.T['reactions'][hit[0]['reactions']]
        self.assertEqual((r['default'], r['ch'], r['crouch'], r['pb_front']), (10, 10, 10, 3))   # (the hold on hit)
        self.assertEqual((r['block'], r['crouch_block'], r['pb_block']), (21, 22, 4))            # (f1's guard)
        self.assertEqual(c.T['moves'][1]['hit_condition'], 0)                                    # (the hold's own)
        for k, v in self.before.items():                                                         # (lists shared)
            self.assertEqual(c.T[k][:len(v)], v)
        self.assertEqual(c.stats['grabs that only a hit starts (hit_grabs)'], 1)

    def test_a_window_of_its_own_and_no_second_time(self):
        c = self.c
        O.hit_grab(c, 'b1', {'grab': 'hold', 'guard_as': 'f1', 'window': (10, 14)})
        row = T.cancels(c.T, c.T['moves'][0]['cancel'])[0]
        self.assertEqual((row['win_start'], row['win_end'], row['start_frame']), (10, 14, 12))   # (its own: later)
        with self.assertRaises(ValueError):                                 # (already tests the hit)
            O.hit_grab(c, 'b1', {'grab': 'hold', 'guard_as': 'f1'})

    def test_a_later_window_enters_the_hold_at_its_first_frame(self):
        c = self.c
        O.hit_grab(c, 'b1', {'grab': 'hold', 'guard_as': 'f1', 'window': (13, 18)})
        row = T.cancels(c.T, c.T['moves'][0]['cancel'])[0]
        self.assertEqual((row['win_start'], row['win_end'], row['start_frame']), (13, 18, 13))
        c.T['moves'][0]['cancel'] = 0
        c.T['requirements'] = c.T['requirements'][:len(self.before['requirements'])]
        O.hit_grab(c, 'b1', {'grab': 'hold', 'guard_as': 'f1', 'window': (13, 18), 'start_frame': 15})
        self.assertEqual(T.cancels(c.T, c.T['moves'][0]['cancel'])[0]['start_frame'], 15)

    def test_apply_runs_it_after_the_active_frames(self):
        c = self.c
        c.defn = types.SimpleNamespace(MOVESET={'active_frames': {'b1': (11, 12)},
                                                'hit_grabs': {'b1': {'grab': 'hold', 'guard_as': 'f1'}}})
        c.dn, c.game, c.map_req = {}, 't8', lambda i: None
        c.T['moves'][0]['first_active'] = 15
        O.apply(c)
        row = T.cancels(c.T, c.T['moves'][0]['cancel'])[0]
        self.assertEqual((row['win_start'], row['win_end']), (11, 13))


if __name__ == '__main__':
    unittest.main()
