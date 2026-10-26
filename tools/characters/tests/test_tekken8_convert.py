"""Unit tests of the converter's Tekken 8 path (convert/moveset.py: classify8, the Tekken 8-only requirements, split
sound values, extra properties with their own requirement lists, the animation provider, unnamed moves) and of the id
maps' Tekken 8 parts (convert/idmaps.py: the wide alignment, near_anchors, Chained / Combined), on made-up tables (no
game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_convert.py
"""
import collections
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_movement import moveset_of, ttt2_fighter  # noqa: E402
from test_tagsystem import Tables  # noqa: E402
from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import moveset, specialcancels  # noqa: E402
from ttt2char.movesets import Moveset  # noqa: E402
from ttt2char.ttt2 import animation, motion  # noqa: E402

END8 = M.END_REQ['t8']


class Source8(Moveset):
    """A made-up Tekken 8 moveset as tekken8/motbin.py reads one: names by index ('' unnamed), anim_ref per move,
    requirement rows with param2..4 (end 1100), extra properties with a requirement list and value2..5."""
    game = 't8'
    code = 'zbr'
    character_id = 28

    def __init__(self, names=None, refs=None):
        self.names, self.refs = dict(names or {}), list(refs or [])
        self.aliases = [0] * 56
        self.tables = collections.defaultdict(list)
        self.tables['moves'] = [dict(anim=i, anim_len=0) for i in range(len(self.refs))]

    def move_name(self, i):
        return self.names.get(i, '')

    def anim_name(self, i):
        return ''

    def anim_ref(self, i):
        return self.refs[i]

    def req(self, *rows):
        """A requirement list of (condition, param[, param2]) -> its index."""
        start = len(self.tables['requirements'])
        for r in rows + ((END8, 0),):
            self.tables['requirements'].append(dict(condition=r[0], param=r[1], param2=r[2] if len(r) > 2 else 0,
                                                    param3=0, param4=0))
        return start

    def props(self, *rows):
        """An extra property list of (frame, id, value, requirement list[, value3]) -> its index."""
        start = len(self.tables['extra_move_properties'])
        for r in rows:
            self.tables['extra_move_properties'].append(dict(frame=r[0], id=r[1], value=r[2], req=r[3], value2=0,
                                                             value3=r[4] if len(r) > 4 else 0, value4=0, value5=0))
        self.tables['extra_move_properties'].append(dict(frame=0, id=0, value=0, req=None, value2=0, value3=0,
                                                         value4=0, value5=0))
        return start


class Map:
    """An id map stub: {id: TTT2 id} observed, anything else a gap."""

    def __init__(self, pairs):
        self.pairs = pairs

    def lookup(self, x):
        return (self.pairs[x], 'observed') if x in self.pairs else (None, 'gap')


class Defn:
    MOVESET = {'name': '[TEST]'}


def converter(k, req=None, prop=None):
    """A bare Converter of Tekken 8 moveset k (its run() parts not needed by the tests left out)."""
    c = moveset.Converter.__new__(moveset.Converter)
    c.k, c.game, c.end, c.prefix = k, 't8', END8, moveset.own_prefix(k)
    c.req_map, c.prop_map = Map(req or {}), Map(prop or {})
    c.usage = {'req': set((req or {}).values()), 'prop': set((prop or {}).values())}
    c.T = {'requirements': [], 'extra_move_properties': []}
    c.cache, c.stats, c.unmapped = {}, collections.Counter(), collections.Counter()
    c.defn, c.k_id, c.newid = Defn(), k.character_id, 70
    c.summons, c.effect_ids, c.effect_rows, c.opt_anims = {}, set(), [], {}
    c.donor_sound, c.voice, c.shouts = collections.defaultdict(set), True, 15
    return c


def converted(c, start):
    """The conditions of a converted requirement list (its end row left out)."""
    out, t = [], c.T['requirements']
    while t[start]['condition'] != moveset.TT_END:
        out.append((t[start]['condition'], t[start]['param']))
        start += 1
    return out


class Classes(unittest.TestCase):
    def test_classify8(self):
        d = Tables()
        d.move('Co_dwupL')
        d.move('Ju_sKAM00_')
        k = Source8({0: 'Co_dwupL', 1: 'Tco_dwupR50', 2: 'Zbr_lp00'},
                    [(1, 'com'), (2, 'com'), (3, 'own'), (4, 'own'), (5, 'com'), (6, None)])
        self.assertEqual(moveset.classify8(k, moveset_of(d)), ['G', 'T', 'K', 'K', 'N', 'N'])

    def test_names(self):
        k = Source8({0: 'Zbr_sWALKF', 1: 'sWALK_00B'}, [(0, 'own')] * 3)
        c = converter(k)
        self.assertEqual([c.name(i) for i in range(3)], ['Zbr_sWALKF', 'sWALK_00B', '#2'])
        self.assertEqual(c.ttt2_name(2), 'Zbr_#2')          # an unnamed move in the TTT2 moveset
        self.assertEqual(c.state_label(0), 'sWALKF')         # the tag system's state: the own prefix left out
        self.assertEqual(c.state_label(1), 'sWALK_00B')


class Requirements(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k, req={47: 47, 0: 0})

    def conv(self, *rows):
        start, ok = self.c.conv_reqs(self.k.req(*rows))
        return converted(self.c, start) if ok else None

    def test_variables(self):
        self.assertEqual(self.conv((476, 16, 0), (47, 0)), [(47, 0)])       # player variable 16 == 0: true
        self.assertIsNone(self.conv((476, 16, 2)))                         # == 2: never in TTT2
        self.assertEqual(self.conv((439, 0xF0000)), [])                    # the opponent's variable 15 == 0
        self.assertIsNone(self.conv((439, 0xF0001)))

    def test_heat_and_modes(self):
        self.assertIsNone(self.conv((1028, 1), (47, 0)))                   # Heat available: no Heat in TTT2
        self.assertEqual(self.conv((1028, 0)), [])
        self.assertEqual(self.conv((667, 0), (801, 0)), [])                # not in game mode 4 / 14
        self.assertIsNone(self.conv((801, 1)))
        self.assertEqual(self.conv((453, 3)), [])                          # buttons held: the row's own again
        self.assertIsNone(self.conv((452, 0)))                             # not in REQ_T8ONLY, not mapped: false
        self.assertEqual(self.c.unmapped[('req', 452)], 1)

    def test_owner(self):
        self.assertEqual(self.conv((220, 28), (47, 0)), [(47, 0)])         # "is Reina": the owner, true
        self.assertIsNone(self.conv((221, 28)))                            # "is not Reina": false
        self.assertIsNone(self.conv((222, 5)))                             # the opponent is another fighter
        self.assertEqual(self.c.stats['owner character requirements folded true'], 1)

    def test_false_and_end(self):
        self.assertIsNone(self.conv((1018, 0)))                            # Tekken 7's 806 (CPU / mode)
        self.assertEqual(self.conv(), [])


class Properties(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k, req={47: 47, 0: 0}, prop={0x8100: 0x8090, 0x87f0: 0x82f9})

    def test_split_sound(self):
        self.assertEqual(self.c.prop_value(dict(id=0x87f0, value=2, value3=5)), 0x02000005)
        self.assertEqual(self.c.prop_value(dict(id=0x8100, value=2, value3=5)), 2)

    def test_row_conditions(self):
        always, heat, hit = self.k.req((0, 0)), self.k.req((1028, 1)), self.k.req((47, 0))
        start = self.c.conv_xps(self.k.props((5, 0x8100, 7, always), (6, 0x8100, 8, heat), (7, 0x8100, 9, hit),
                                             (8, 0x87f0, 2, always, 5), (9, 0x8039, 0x0103, always)))
        rows = self.c.T['extra_move_properties'][start:]
        self.assertEqual([(r['frame'], r['id'], r['value']) for r in rows],
                         [(5, 0x8090, 7), (8, 0x82f9, 0x02000005), (0, 0, 0)])  # a shout of her own voice kept
        self.assertEqual(self.c.stats['property dropped: requirement'], 1)
        self.assertEqual(self.c.stats['property dropped: a condition TTT2 cannot attach'], 1)
        self.assertEqual(self.c.stats['property dropped: effect (Tekken 8 effects are not converted)'], 1)

    def test_voices(self):
        # Tekken 8 names a voice by sound id (bank 16) or plays one of a kind (bank 17): the TTT2 voice of the same
        # line (voices8, the importer's), a kind's in turn; other voices are left out (another fighter's line)
        c = self.c
        c.voices8, c.voice_turns = {(16, 13342): [0x0200002B], (17, 0): [0x02000000, 0x02000001]}, collections.Counter()
        self.assertEqual(c.prop_value(dict(id=0x87f1, value=16, value3=13342)), 0x1000341E)    # (0x87f1 split too)
        self.assertEqual(c.conv_value(0x87f0, c.prop_value(dict(id=0x87f0, value=16, value3=13342))), 0x0200002B)
        self.assertEqual([c.conv_value(0x87f0, 17 << 24) for _ in range(3)], [0x02000000, 0x02000001, 0x02000000])
        self.assertIsNone(c.conv_value(0x87f0, 16 << 24 | 7754))
        # the opponent's (0x87f2) plays through its own voice list: a cry of a kind Tekken 8 gives it, damage voice 0
        self.assertEqual(c.conv_value(0x87f2, 17 << 24 | 3), 0x03000000)
        self.assertIsNone(c.conv_value(0x87f2, 17 << 24 | 0))
        self.assertIsNone(c.conv_value(0x87f2, 16 << 24 | 13342))
        self.assertIsNone(c.conv_value(0x87f0, 17 << 24 | 9))
        self.assertEqual(c.conv_value(0x87f0, 0x02000005), 0x02000005)          # her own shout n (SE_KIAI_n) kept

    def test_versus_lines(self):
        # a line said against one fighter (505: the opponent is Heihachi, 35) is left out, its line against the
        # others (506) said always; other conditions as any row's
        c = self.c
        c.voices8, c.voice_turns = {(16, 1): [0x02000020], (16, 2): [0x02000021]}, collections.Counter()
        always, vs, others = self.k.req((0, 0)), self.k.req((505, 35)), self.k.req((506, 35))
        heat = self.k.req((1028, 1))
        start = c.conv_xps(self.k.props((16, 0x87f0, 16, vs, 1), (16, 0x87f0, 16, others, 2), (20, 0x87f0, 16, heat, 1),
                                        (24, 0x87f0, 16, always, 1)))
        rows = c.T['extra_move_properties'][start:]
        self.assertEqual([(r['frame'], r['id'], r['value']) for r in rows],
                         [(16, 0x82f9, 0x02000021), (24, 0x82f9, 0x02000020), (0, 0, 0)])
        self.assertEqual(c.stats['property dropped: requirement'], 1)

    def test_chance(self):
        # a kind's voice said by chance (value2): from CHANCE8 on always, below it not (her jabs' 40 %)
        c = self.c
        c.voices8, c.voice_turns = {(17, 0): [0x02000000]}, collections.Counter()
        always = self.k.req((0, 0))
        start = self.k.props((2, 0x87f0, 17, always, 0), (3, 0x87f0, 17, always, 0), (4, 0x87f0, 17, always, 0))
        for row, chance in zip(self.k.tables['extra_move_properties'][start:], (40, 50, 100)):
            row['value2'] = chance
        rows = c.T['extra_move_properties'][c.conv_xps(start):]
        self.assertEqual([(r['frame'], r['value']) for r in rows], [(3, 0x02000000), (4, 0x02000000), (0, 0)])

    def test_voice_clips(self):
        # Tekken 8's mark of a move saying nothing as it starts (shout 0x9986) is TTT2's (shout 999), even where the
        # donor's moves have none: a move with no shout in its list gets a random one from the title; the damage
        # voice mark has no TTT2 use (left out), her own shout n stays; a Tekken 7 list as before
        c, end = self.c, {'value': 0xFFFFFFFF}
        self.k.tables['voiceclips'] = [{'value': 0x02009986}, end, {'value': 0x03009986}, end, {'value': 0x02000005},
                                       end]
        c.T['voiceclips'], c.donor_clips = [], {0x0100001A}
        self.assertEqual([v['value'] for v in c.T['voiceclips'][c.conv_voiceclips(0):]], [0x020003E7, 0xFFFFFFFF])
        self.assertIsNone(c.conv_voiceclips(2))
        self.assertEqual([v['value'] for v in c.T['voiceclips'][c.conv_voiceclips(4):]], [0x02000005, 0xFFFFFFFF])
        c.game = 't7'
        self.assertIsNone(c.conv_voiceclips(0))


class Animations(unittest.TestCase):
    def test_provider(self):
        k = Source8(refs=[(10, 'com'), (11, 'own'), (12, 'com'), (13, 'own'), (11, 'own')])
        d = Tables()
        d.move('Ju_sKAM00_', anim=0x4002)
        d.aliases[1] = 0
        c = converter(k)
        c.d, c.pack0_count, c.new_anims, c.anim_id = moveset_of(d), 30, [], {}
        c.generic_anim = {10: 0x8000 | 7}                     # a 'G' move of the fighter plays animation 10
        answers = {(11, 'own'): b'ANIM', (12, 'com'): 0x8000 | 9, (13, 'own'): None}
        c.animations = lambda ref: answers[ref]
        self.assertEqual([c.anim8(i) for i in range(5)], [0x8007, 0x4000 | 30, 0x8009, 0x4002, 0x4000 | 30])
        self.assertEqual(c.new_anims, [b'ANIM'])              # appended once (move 4 has the same key)
        self.assertEqual(c.stats['animations: none (the donor stance\'s)'], 1)

    def test_generic_animations(self):
        """Only common-bank clips of 'G' moves play the donor's animation: a 'G' move playing the fighter's own clip
        (Reina's sWALK_00BMv plays her stance) leaves that clip to her own moves."""
        k = Source8(refs=[(10, 'com'), (20, 'own'), (10, 'com'), (30, None), (20, 'own')])
        donor = {0: 0x4001, 1: 0x4002, 2: 0x4003, 3: 0x4004}
        out = moveset.generic_animations(k, ['G', 'G', 'G', 'G', 'K'], donor.get)
        self.assertEqual(out, {10: 0x4001})                   # the first 'G' move's; own and missing clips left out

    def test_hold(self):
        """A pose part holding the last frame of a Tekken 8 move's (provider-made) animation, in place."""
        values = np.zeros((4, 3, 3), np.float32)
        values[:, 0, 0] = [0, 10, 20, 30]                    # ground displacement (left out of the hold)
        values[:, 1, 1] = [1, 2, 3, 4]
        made = animation.encode_raw([1, 2, 3], values)
        empty = b'MOTA\0\1\0\0' + struct.pack('>III', 0x14, 0, 0)
        pack = motion.build_pack([motion.extend_mota(empty, [made])] + [b''] * 5)    # the donor's one animation
        c = converter(Source8(refs=[(5, 'own')]))
        c.donor_pack, c.pack0_count, c.new_anims, c.anim_id, c.generic_anim = pack, 1, [], {}, {}
        c.animations = lambda ref: made
        aid = c.hold(0, 6)
        self.assertEqual(c.anim8(0), 0x4001)                  # the move's own animation, appended first
        self.assertEqual(aid, 0x4002)
        a = animation.decode(c.new_anims[1])
        self.assertEqual(a['values'].shape, (6, 3, 3))
        self.assertTrue(np.allclose(a['values'][:, 1, 1], 4) and np.allclose(a['values'][:, 0, 0], 0))

    def handoff_converter(self, rows):
        """A converter with one converted clip (new_anims[0], 0x4001: HARA_ROT1 upright, ending turned) and the donor
        pack's one animation (0x4000): a down move's start, HARA_ROT1 lying, the same world pose."""
        from test_retarget import lying_next, smooth_values
        from ttt2char.convert import retarget
        v = smooth_values(40)
        v[:, 3] = 0.0
        v[:, 2, 2] = np.linspace(0, -5.5, 40)
        v[:, 6] = retarget.SPINE_PARAMETER
        nxt = lying_next(None, v)
        empty = b'MOTA\0\1\0\0' + struct.pack('>III', 0x14, 0, 0)
        down = retarget.encode(np.repeat(nxt[None], 2, 0))
        c = converter(Source8())
        c.donor_pack = motion.build_pack([motion.extend_mota(empty, [down])] + [b''] * 5)
        c.pack0_count, c.new_anims, c.converted8, c.aliases = 1, [retarget.encode(v)], {0}, []
        c.T['moves'] = [dict(anim=a, transition=t) for a, t in rows]
        c.handoffs8()
        return c, animation.decode(down)['values'][0]

    def test_handoff(self):
        """A converted clip handing off to a TTT2 down move is re-split for it (retarget.handoff): at its end the
        turn and HARA_ROT1 are the down move's."""
        from ttt2char.convert import retarget
        c, down = self.handoff_converter([(0x4001, 1), (0x4000, 1)])
        self.assertEqual(len(c.new_anims), 1)                   # the clip's only user: changed in place
        out = animation.decode(c.new_anims[0])['values']
        self.assertLess(retarget.handoff_mismatch(out, animation.COMPRESSED, down, animation.COMPRESSED), 0.1)
        self.assertLess(retarget.angle(animation.local_rotation(out[-1, 2]), animation.local_rotation(down[2])), 0.1)
        self.assertEqual(c.stats['hand-offs: converted clips re-split for the next move\'s HARA_ROT1'], 1)

    def test_handoff_copy(self):
        """A clip played by a move handing off to a down move and by one handing off upright: a copy for the first."""
        from ttt2char.convert import retarget
        c, down = self.handoff_converter([(0x4001, 1), (0x4000, 1), (0x4001, 3), (0x4001, 3)])
        self.assertEqual(len(c.new_anims), 2)
        self.assertEqual([r['anim'] for r in c.T['moves']], [0x4002, 0x4000, 0x4001, 0x4001])
        out = animation.decode(c.new_anims[1])['values']
        self.assertLess(retarget.handoff_mismatch(out, animation.COMPRESSED, down, animation.COMPRESSED), 0.1)
        self.assertEqual(c.stats['hand-offs: re-split copies of converted clips (one per next move)'], 1)

    def test_no_provider(self):
        c = converter(Source8(refs=[(1, 'own')]))
        c.generic_anim, c.anim_id, c.animations = {}, {}, None
        with self.assertRaises(ValueError):
            c.anim8(0)


class Maps(unittest.TestCase):
    def test_near_anchors(self):
        anc = {10: (10, 100, 100, {}), 20: (20, 100, 100, {}), 30: (25, 100, 100, {}),
               25: (22, 55, 100, {}),           # between 20 -> 20 and 30 -> 25 (two offsets), 55 %: mapped
               26: (19, 55, 100, {}),           # 19 would break the chain's order: not
               27: (23, 11, 20, {})}            # 55 % of too few observations: not
        m = M.IdMap(anc)
        self.assertEqual(m.lookup(25), (None, 'gap'))
        self.assertEqual(M.near_anchors(m), 1)
        self.assertEqual(m.lookup(25), (22, 'observed-exception'))
        self.assertEqual(m.lookup(26)[1], 'gap')
        self.assertEqual(m.lookup(27)[1], 'gap')

    def test_own_prefixes(self):
        k = Source8({0: 'Zbr_lp00', 1: 'Zbr_rp00', 2: 'Co_dwupL', 3: 'Nj_step_00F'}, [(0, 'own')] * 4)
        self.assertEqual(M.own_prefixes([k, ttt2_fighter('Ju')]), ['Zbr', 'Ju'])     # Co_ / Nj_ in both: generic
        self.assertEqual(M.canonical(ttt2_fighter('Ju'))[0], 'Ju_sKAM00_')            # (no own_prefix set)

    def test_chained_combined(self):
        first, through = Map({1: 101, 2: 102}), M.Chained(Map({3: 30, 4: 40}), Map({30: 103}))
        both = M.Combined(first, through)
        self.assertEqual([both.lookup(x) for x in (1, 3, 4, 5)],
                         [(101, 'observed'), (103, 'chained'), (None, 'gap'), (None, 'gap')])

    def test_wide_alignment(self):
        """Moves pair by the stem behind each moveset's own prefix (Zbr_sKAM00_ <-> Ju_sKAM00_) and by generic
        names; unnamed moves never pair; an unnamed reaction move's evidence is under '#<index>'."""
        k = Source8({0: 'Zbr_sKAM00_', 1: 'Co_dwupL', 3: 'Co_Dm'}, [(0, 'own')] * 4)
        k.own_prefix = 'Zbr'
        t = k.tables
        t['hit_conditions'] = [dict(req=k.req((723, 0)), damage=10, reactions=0), dict(req=k.req(), damage=0,
                                                                                         reactions=None)]
        t['reactions'] = [dict({f: 3 for f in M.REACTION_MOVE_FIELDS}, default=2)]
        t['cancels'] = [dict(direction=0, button=1, req=k.req((500, 0)), move_id=1),
                        dict(direction=M.LIST_END, button=0, req=None, move_id=0),
                        dict(direction=0, button=2, req=k.req((600, 0)), move_id=1),
                        dict(direction=M.LIST_END, button=0, req=None, move_id=0)]
        t['moves'] = [dict(cancel=0, hit_condition=0, extraprops=None, begin_props=None, end_props=None,
                           hitbox=b'\0\0\0\0'), dict(cancel=2, hit_condition=None, extraprops=None, begin_props=None,
                                                     end_props=None, hitbox=b'\0\0\0\0')] + \
            [dict(cancel=None, hit_condition=None, extraprops=None, begin_props=None, end_props=None,
                  hitbox=b'\0\0\0\0')] * 2
        b = Tables()
        hc = b.hits((b.req((466, 0)), 10, b.reaction(2)), (b.req(), 0, None))
        b.move('Ju_sKAM00_', cancel=b.cancels(dict(button=1, req=b.req((300, 0)), move_id=1), b.end()),
               hit_condition=hc)
        b.move('Co_dwupL', cancel=b.cancels(dict(button=2, req=b.req((400, 0)), move_id=1), b.end()))
        b.move('Co_DmA')
        tt = moveset_of(b)
        tt.own_prefix = 'Ju'
        ev = collections.defaultdict(M.Evidence)
        M.align(k, tt, ev)                              # (wide: a Tekken 8 moveset)
        self.assertEqual(ev['req'].pairs[(500, 300)], 1)  # the stem pair's cancel rows
        self.assertEqual(ev['req'].pairs[(600, 400)], 1)  # the generic pair's
        self.assertEqual(ev['req'].pairs[(723, 466)], 1)  # their hit conditions
        self.assertEqual(ev['react.move'].pairs[('#2', 'Co_DmA')], 1)
        self.assertEqual(M.reaction_remap(ev)['#2'], 'Co_DmA')


class SpecialCancels(unittest.TestCase):
    def test_source_ids(self):
        self.assertEqual(specialcancels.SOURCE_IDS['t7']['special'], 346)
        self.assertIsNone(specialcancels.SOURCE_IDS['t8']['special'])    # none found: no row matches
        c = converter(Source8({0: 'Zbr_lp00'}, [(0, 'own')]))
        c.kn, c.newidx = {'Zbr_lp00': 0}, {0: 0}
        specialcancels.restore_unbuffered_normal_strings(c)              # (returns: Tekken 8 has no such buffer)
        self.assertFalse(c.stats)


if __name__ == '__main__':
    unittest.main()
