"""A Tekken 8 reaction the remap would replace by TTT2's empty move 0 or by a guard or stagger that frees the opponent
on another frame is converted itself (Converter.target(reaction=True)); launches, other games and other targets keep
the remap. Synthetic movesets only."""
import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ttt2char.convert import idmaps as M, moveset
from ttt2char.movesets import Moveset

STAND = 'Xx_sKAM00_'


def moves(game, spec):
    """spec: (name, end frame or None, transition (index) or None, airborne) per move -> a Moveset."""
    m = Moveset()
    m.game, m.character_id = game, 44
    m.namebuf, m.aliases = b'', [0] * 56
    m.tables = dict(moves=[], cancels=[], requirements=[dict(condition=881, param=0)], input_sequences=[])
    for name, end, to, air in spec:
        offset = len(m.namebuf)
        m.namebuf += name.encode() + b'\0'
        cancel = len(m.tables['cancels'])
        m.tables['cancels'].append(dict(direction=M.LIST_END, button=0, req=0, extradata=0, win_start=end or 0,
                                        win_end=32767, start_frame=end or 0, move_id=0x8001, option=0))
        m.tables['moves'].append(dict(name=offset, cancel=cancel, transition=to if to is not None else 0x8000,
                                      airborne_start=1 if air else 0, hitlevel=0))
    return m


def converter(game='t8', cls=None):
    # the source: two guards (28 and 19 frames), a hit stagger whose TTT2 name is the empty move, a launch, its own
    # guard, a stance; the donor: TTT2's empty move 0, a 19-frame guard, a 64-frame launch, its stance
    k = moves(game, [('sGrd_long28', 28, 5, False), ('sGrd_same19', 19, 5, False), ('sDm_empty30', 30, 5, False),
                     ('dw_launch50', 50, 5, True), ('Xx_ownGuard', 26, 5, False), (STAND, None, None, False)])
    d = moves('ttt2', [('motOrigin', None, None, False), ('sGrd_generic19', 19, 3, False),
                       ('sDw_launch64', 64, 3, True), (STAND, None, None, False)])
    c = moveset.Converter.__new__(moveset.Converter)
    c.k, c.d, c.game = k, d, game
    c.stats, c.cache = collections.Counter(), {}
    c.newidx, c.delta_move = {}, {}
    c.dn = {'motOrigin': 0, 'sGrd_generic19': 1, 'sDw_launch64': 2, STAND: 3}
    c.react_remap = {'sGrd_long28': 'sGrd_generic19', 'sGrd_same19': 'sGrd_generic19', 'sDm_empty30': 'motOrigin',
                     'dw_launch50': 'sDw_launch64', 'Xx_ownGuard': 'sGrd_generic19'}
    c.cls = cls or ['T', 'T', 'T', 'T', 'K', 'G']
    c.queue, c.alloc_ok, c.linking = [], 1, 0          # (conv_reaction's)
    c.T = dict(moves=[])
    c.conv_move = lambda i: dict(name=k.tables['moves'][i]['name'])
    c.is_state = lambda i: False
    return c


def refused(c):
    return sum(n for s, n in c.stats.items() if s.startswith('reaction remap refused'))


class Tekken8ReactionStun(unittest.TestCase):
    def test_a_guard_of_another_length_is_converted(self):
        c = converter()
        self.assertEqual(c.target(0, reaction=True), 0)         # the first new move: Tekken 8's own 28 frames
        self.assertEqual(c.queue, [0])
        self.assertEqual(c.target(0, reaction=True), 0)         # (once)
        self.assertEqual(len(c.T['moves']), 1)
        self.assertEqual(refused(c), 1)

    def test_a_guard_of_the_same_length_keeps_the_remap(self):
        c = converter()
        self.assertEqual(c.target(1, reaction=True), 1)
        self.assertEqual((c.queue, refused(c)), ([], 0))

    def test_the_empty_move_is_never_a_reaction(self):
        c = converter()
        self.assertEqual(c.target(2, reaction=True), 0)         # converted, not the donor's move 0
        self.assertEqual(c.queue, [2])
        self.assertEqual(c.stats['reaction remap refused (TTT2 has no move there, motOrigin: Tekken 8\'s own kept)'], 1)

    def test_a_launch_keeps_the_remap(self):
        c = converter()
        self.assertEqual(c.target(3, reaction=True), 2)         # air time, not a stun: other_fall's
        self.assertEqual(c.queue, [])

    def test_own_and_unconvertible_moves_keep_the_remap(self):
        c = converter()
        self.assertEqual(c.target(4, reaction=True), 1)         # 'K': target() would not convert it
        c = converter(cls=['T', 'T', 'T', 'T', 'K', 'G'])
        c.k.namebuf = c.k.namebuf.replace(b'sGrd_long28', b'Story_long')
        c.react_remap['Story_long'] = 'sGrd_generic19'
        self.assertEqual(c.target(0, reaction=True), 1)         # dropped by DROP_T_RE: the remap stays
        self.assertEqual(c.queue, [])

    def test_other_targets_keep_the_remap(self):
        c = converter()
        self.assertEqual(c.target(0), 1)                        # not a reaction slot's move
        self.assertEqual(c.target(2), 0)
        self.assertEqual((c.queue, refused(c)), ([], 0))

    def test_tekken7_is_unchanged(self):
        c = converter('t7')
        self.assertEqual(c.target(0, reaction=True), 1)
        self.assertEqual(c.target(2, reaction=True), 0)
        self.assertEqual(c.target(3, reaction=True), 2)
        self.assertEqual((c.queue, refused(c)), ([], 0))

    def test_end_frame_and_other_stun(self):
        c = converter()
        self.assertEqual([moveset.Converter.end_frame(c.k, i) for i in range(4)], [28, 19, 30, 50])
        self.assertTrue(c.other_stun(0, 1))
        self.assertFalse(c.other_stun(1, 1))
        self.assertFalse(c.other_stun(3, 2))                    # both leave the ground
        self.assertFalse(c.other_stun(0, 0))                    # the empty move reaches no rest: unknown

    def test_reaction_slots_ask_for_reaction_targets(self):
        c = converter()
        seen = []
        c.target = lambda mid, **kw: seen.append((mid, kw)) or 7
        c.conv_pushback = lambda i: 0
        c.add = lambda table, row: len(seen)
        names = [nm for nm, _, _, link in moveset.TTT2['reactions'][1] if link == 'move']
        c.k.tables['reactions'] = [{nm: (3 if link == 'move' else 0)
                                    for nm, _, _, link in moveset.TTT2['reactions'][1]}]
        c.conv_reaction(0)
        self.assertEqual(len(seen), len(names))
        self.assertTrue(all(kw == {'reaction': True} for _, kw in seen))


if __name__ == '__main__':
    unittest.main()
