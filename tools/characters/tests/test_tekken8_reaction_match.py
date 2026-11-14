"""A Tekken 8 reaction of an opponent on its feet keeps a TTT2 move only when it floats and comes to rest as Tekken
8's does, else Tekken 8's own is converted; a TTT2 move guarding from other frames is copied with Tekken 8's guard rows
(convert/moveset.py FLOAT8, GUARD_FROM8, Converter.target(reaction=True)). Air rows, downed and wall slots, other
targets and Tekken 7 keep what they had. Synthetic movesets only."""
import collections
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ttt2char.convert import idmaps as M, moveset
from ttt2char.movesets import Moveset, REACTION_MOVE_FIELDS

STAND = 'Xx_sKAM00_'
GUARD = {'t8': moveset.GUARD_FROM8, 't7': moveset.GUARD_FROM8, 'ttt2': moveset.TT_GUARD_FROM}


def moves(game, spec):
    """spec: (name, (airborne start, end, ground fall), transition (index) or None, guard-from frames, other property
    rows [(frame, id, value)]) per move -> a Moveset (no hit rows yet)."""
    m = Moveset()
    m.game, m.character_id = game, 44
    m.namebuf, m.aliases = b'', [0] * 56
    m.tables = dict(moves=[], cancels=[], requirements=[], hit_conditions=[], reactions=[],
                    extra_move_properties=[], input_sequences=[])
    for name, (a, b, f), to, guards, other in spec:
        offset = len(m.namebuf)
        m.namebuf += name.encode() + b'\0'
        rows = [dict(frame=g, id=GUARD[game], value=1) for g in guards] + [dict(frame=fr, id=i, value=v)
                                                                             for fr, i, v in other]
        xp = None
        if rows:
            xp = len(m.tables['extra_move_properties'])
            m.tables['extra_move_properties'] += rows + [dict(frame=0, id=0, value=0)]
        m.tables['moves'].append(dict(name=offset, cancel=None, transition=to if to is not None else 0x8000,
                                      airborne_start=a, airborne_end=b, ground_fall=f, hitlevel=0, extraprops=xp,
                                      hit_condition=None))
    return m


def hit_rows(m, rows):
    """rows: [(requirement ids, {slot: move})] -> the hit-condition list of one attack (the last row, no
    requirements, ends it); slots not given hold move 0."""
    end = M.END_REQ[m.game]
    start = len(m.tables['hit_conditions'])
    for reqs, slots in rows:
        req = len(m.tables['requirements'])
        m.tables['requirements'] += [dict(condition=c, param=0) for c in reqs] + [dict(condition=end, param=0)]
        m.tables['reactions'].append({f: slots.get(f, 0) for f in REACTION_MOVE_FIELDS})
        m.tables['hit_conditions'].append(dict(req=req, damage=10, reactions=len(m.tables['reactions']) - 1))
    m.tables['moves'].append(dict(m.tables['moves'][0], hit_condition=start, hitlevel=0x217))
    return len(m.tables['moves']) - 1


ZERO = (0, 0, 0)
# the source (Tekken 8): 0 stance, 1 a 30-frame launch landing face down, 2 a launch with the donor's float, 3 the
# same launch landing face down, 4 an air reaction, 5 a down hit, 6 a jab reaction guarding never, 7 one guarding from
# 14, 8 Tekken 8's own sDm_KAO10FLP (guarding never), 9 a stagger guarding as the donor's, 10 / 11 lying face up / down
SOURCE = [(STAND, ZERO, None, (), ()), ('dw_He_shoryu', (1, 30, 29), 11, (), ()), ('#285', (1, 52, 51), 10, (), ()),
          ('#286', (1, 52, 51), 11, (), ()), ('#41', (1, 1, 1), 11, (), ()), ('#414', (1, 22, 0), 10, (), ()),
          ('#1529', ZERO, 0, (), ()), ('sDm_HAR00M14G', ZERO, 0, (14,), ()), ('sDm_KAO10FLP', ZERO, 0, (), ()),
          ('#1616', ZERO, 0, (10,), ()), ('dwDWN_01U', ZERO, None, (), ()), ('dwDWN_01D', ZERO, None, (), ())]
# the donor (TTT2): 0 motOrigin, 1 stance, 2 the 52-frame launch, 3 an air reaction, 4 a down hit, 5 sDm_KAO10FLP
# guarding from 20 (Lars's) beside another property, 6 sDm_KAO00L (no guard row), 7 sDm_KAO00MG guarding from 10,
# 8 / 9 lying face up / down
DONOR = [('motOrigin', ZERO, None, (), ()), (STAND, ZERO, None, (), ()), ('sDw_UP_01_', (1, 52, 51), 8, (), ()),
         ('aDw_ym_y01R', (1, 38, 37), 9, (), ()), ('dDwrOUC00_', (1, 33, 32), 9, (), ()),
         ('sDm_KAO10FLP', ZERO, 1, (20,), ((0x8001, 0x8053, 7),)), ('sDm_KAO00L', ZERO, 1, (), ()),
         ('sDm_KAO00MG', ZERO, 1, (10,), ()), ('dwDWN_01U', ZERO, None, (), ()), ('dwDWN_01D', ZERO, None, (), ())]
REMAP = {'dw_He_shoryu': 'sDw_UP_01_', '#285': 'sDw_UP_01_', '#286': 'sDw_UP_01_', '#41': 'aDw_ym_y01R',
         '#414': 'dDwrOUC00_', '#1529': 'sDm_KAO10FLP', 'sDm_HAR00M14G': 'sDm_KAO00L', '#1616': 'sDm_KAO00MG'}


def converter(game='t8'):
    k, d = moves(game, SOURCE), moves('ttt2', DONOR)
    # the attacks: launches and staggers on the standing slots, an air row [723] with #41 (on a standing opponent's
    # slot too), a downed slot with #414
    hit_rows(k, [((), {'default': 1, 'ch': 2, 'crouch': 3, 'crouch_ch': 4, 'left': 6, 'right': 7, 'back': 8,
                       'crouch_back': 9})])
    hit_rows(k, [((moveset.T7_AIR[game],), {'default': 4}), ((), {'default': 1, 'downed': 5})])
    c = moveset.Converter.__new__(moveset.Converter)
    c.k, c.d, c.game, c.prefix = k, d, game, 'Xx'
    c.stats, c.cache = collections.Counter(), {}
    c.newidx, c.delta_move = {}, {}
    c.dn = {d.move_name(i): i for i in range(len(d.tables['moves']))}
    c.react_remap = dict(REMAP)
    c.cls = ['K', 'T', 'N', 'N', 'N', 'N', 'N', 'T', 'G', 'N', 'G', 'G', 'K', 'K']
    c.queue, c.alloc_ok, c.linking = [], 1, 0          # (conv_reaction's)
    c.T = copy.deepcopy(d.tables)
    c.strings, c.str_off = bytearray(d.namebuf), {}
    c.conv_move = lambda i: dict(name=k.tables['moves'][i]['name'])
    c.is_state = lambda i: False
    return c


def guards(c, i):
    return c.guard_rows(c.T, i, moveset.TT_GUARD_FROM)


class Tekken8ReactionMatch(unittest.TestCase):
    def test_standing_reactions(self):
        c = converter()
        self.assertFalse(c.standing8(0))                    # (the slots no reaction fills)
        self.assertEqual(c._standing8, {1, 2, 3, 6, 7, 8, 9})
        self.assertFalse(c.standing8(4))                    # an air row's, though a standing slot's too
        self.assertFalse(c.standing8(5))                    # a downed slot's

    def test_lands8(self):
        c = converter()
        self.assertEqual([c.lands8(c.k, i, c.name) for i in (0, 1, 2, 3, 6)], ['stand', 'D', 'U', 'D', 'stand'])
        self.assertEqual([c.lands8(c.d, i, c.d.move_name) for i in (1, 2, 3)], ['stand', 'U', 'D'])
        self.assertIsNone(c.lands8(c.d, 0, c.d.move_name))  # motOrigin reaches no rest

    def test_a_launch_of_another_float_is_converted(self):
        c = converter()
        self.assertEqual(c.target(1, reaction=True), len(c.d.tables['moves']))      # Tekken 8's own, new
        self.assertEqual(c.queue, [1])
        self.assertEqual(c.stats['reaction remap refused (a TTT2 move floating or landing otherwise: Tekken 8\'s '
                                 'own kept)'], 1)

    def test_a_launch_landing_on_the_other_side_is_converted(self):
        c = converter()
        self.assertEqual(c.target(3, reaction=True), len(c.d.tables['moves']))      # 1-52 as TTT2's, face down
        self.assertEqual(c.queue, [3])

    def test_a_launch_of_the_same_float_keeps_ttt2s(self):
        c = converter()
        self.assertEqual(c.target(2, reaction=True), 2)     # 1-52 face up: TTT2's sDw_UP_01_ itself
        self.assertEqual(c.queue, [])

    def test_air_down_and_mixed_reactions_keep_ttt2s(self):
        c = converter()
        self.assertEqual(c.target(4, reaction=True), 3)     # the air row's (1-1, landing face down)
        self.assertEqual(c.target(5, reaction=True), 4)     # the downed slot's (1-22 against 1-33)
        self.assertEqual((c.queue, len(c.T['moves'])), ([], len(c.d.tables['moves'])))

    def test_guard_copies(self):
        c = converter()
        n = len(c.d.tables['moves'])
        jab = c.target(6, reaction=True)                    # #1529 -> Lars's sDm_KAO10FLP without its guard row
        c.guard_copies_final8()
        self.assertEqual((jab, guards(c, jab), guards(c, 5)), (n, [], [(20, 1)]))
        self.assertEqual([(r['frame'], r['id'], r['value']) for r in c.extra_rows(c.T, jab)], [(0x8001, 0x8053, 7)])
        self.assertEqual(c.move_name(jab), 'Xx_#1529')
        self.assertEqual(c.T['moves'][jab]['cancel'], c.T['moves'][5]['cancel'])     # the rest is TTT2's
        own = c.target(8, reaction=True)                    # Tekken 8's sDm_KAO10FLP: the donor's name, prefixed
        hara = c.target(7, reaction=True)                   # guarding from 14 where sDm_KAO00L never does
        c.guard_copies_final8()
        self.assertEqual((own, c.move_name(own), guards(c, own)), (n + 1, 'Xx_sDm_KAO10FLP', []))
        self.assertEqual((hara, c.move_name(hara), guards(c, hara)), (n + 2, 'sDm_HAR00M14G', [(14, 1)]))
        self.assertEqual(c.target(9, reaction=True), 7)     # the same guard frame: TTT2's own
        self.assertEqual(c.target(6, reaction=True), jab)   # (once per reaction)
        self.assertEqual((c.queue, c.stats['reactions guarding from Tekken 8\'s frame (a copy of the TTT2 move)']),
                         ([], 3))

    def test_guard_copy_follows_the_donor_move(self):
        c = converter()
        jab = c.target(6, reaction=True)
        # a pass after the conversion gives the donor's move another list and a property row (rebuild_hubs,
        # dismiss_when_hit): the copy has them too, the guard rows still Tekken 8's
        c.T['moves'][5]['cancel'] = 77
        c.T['moves'][5]['extraprops'] = len(c.T['extra_move_properties'])
        c.T['extra_move_properties'] += [dict(frame=20, id=moveset.TT_GUARD_FROM, value=1),
                                         dict(frame=0x8001, id=0x822f, value=16), dict(frame=0, id=0, value=0)]
        c.guard_copies_final8()
        self.assertEqual((c.T['moves'][jab]['cancel'], c.move_name(jab), guards(c, jab)), (77, 'Xx_#1529', []))
        self.assertEqual([(r['frame'], r['id']) for r in c.extra_rows(c.T, jab)], [(0x8001, 0x822f)])

    def test_guard_set_by_a_cancel_row(self):
        c = converter()
        k = c.k
        # Clive's #1529: no property row, but a cancel row back into the stance from 24 that sets GUARD_FROM8
        k.namebuf += b'#1531\0'
        req = len(k.tables['requirements'])
        k.tables['requirements'] += [dict(condition=0x81fc, param=2114), dict(condition=moveset.GUARD_FROM8, param=1),
                                     dict(condition=M.END_REQ['t8'], param=0)]
        k.tables['cancels'] += [dict(direction=0x3ec, req=req, win_start=24, win_end=32767, start_frame=24, move_id=0),
                                dict(direction=M.LIST_END, req=None, win_start=25, win_end=32767, start_frame=25,
                                     move_id=0)]
        mid = len(k.tables['moves'])
        k.tables['moves'].append(dict(k.tables['moves'][6], name=len(k.namebuf) - 6,
                                      cancel=len(k.tables['cancels']) - 2))
        hit_rows(k, [((), {'default': mid})])
        c.cls += ['N', 'K']
        c.react_remap['#1531'] = 'sDm_KAO10FLP'
        jab = c.target(mid, reaction=True)
        c.guard_copies_final8()
        self.assertEqual((c.move_name(jab), guards(c, jab)), ('Xx_#1531', [(24, 1)]))

    def test_other_targets_keep_the_remap(self):
        c = converter()
        self.assertEqual([c.target(i) for i in (3, 6, 7, 8)], [2, 5, 6, 5])     # not a reaction slot's move
        self.assertEqual((c.queue, len(c.T['moves'])), ([], len(c.d.tables['moves'])))

    def test_tekken7_is_unchanged(self):
        c = converter('t7')
        self.assertEqual([c.target(i, reaction=True) for i in (3, 6, 7, 8)], [2, 5, 6, 5])
        self.assertEqual((c.queue, len(c.T['moves'])), ([], len(c.d.tables['moves'])))


if __name__ == '__main__':
    unittest.main()
