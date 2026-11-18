"""Unit tests of the converter's Tekken 8 projectile rows and slow throws (convert/moveset.py: PROJ_SHAPE8, PROJ_GROUND8,
THROW_LATE8 in contact_unseen, THROWN_FIRST; Azazel's crystals, vortices, throws and waves), on made-up tables (no game
files needed).

    python3 -m unittest tests/test_tekken8_projectiles.py      (from tools/characters)
"""
import os
import struct
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import Source8, converter  # noqa: E402
from ttt2char.convert import idmaps, moveset  # noqa: E402
from ttt2char.ttt2 import animation  # noqa: E402

LIMB8, SPAWN8 = moveset.PROJ_BONE['t8'], moveset.PROJ_SPAWN['t8']


def projectile(shape, radius, height):
    """A Tekken 8 projectile row (Tekken 7's form: 42 u32): flying 500 mm a frame, one hit, 5 frames, the shape."""
    v = [0] * 42
    v[7], v[9], v[10], v[11], v[12], v[13], v[14] = 500, 1, 5, shape, radius, height, 0x31f
    return dict(raw=struct.pack('<42I', *v), hit_condition=None, cancel=None)


class Projectiles(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k)
        self.c.T['projectiles'], self.c.T['hit_conditions'] = [dict(raw=bytes(136))], []
        self.c.gauge, self.c.known_sounds, self.c.effects = None, set(), None
        self.k.tables['projectiles'] = [projectile(0, 0, 0), projectile(2, 600, 600), projectile(1, 600, 150)]

    def row(self, i):
        return struct.unpack('>34I', self.c.T['projectiles'][self.c.conv_projectile(i)]['raw'])

    def test_shape_two_is_a_cylinder(self):
        # Azazel's vortices: shape 2, which TTT2's hit test never hits with -> the cylinder of its radius and height
        v = self.row(1)
        self.assertEqual((v[6], v[7], v[8]), (1, 600, 600))
        self.assertEqual(self.c.stats['Tekken 8 projectiles of a shape TTT2 has not made cylinders'], 1)

    def test_cylinder_kept(self):
        v = self.row(2)
        self.assertEqual((v[6], v[7], v[8]), (1, 600, 150))
        self.assertEqual(self.c.stats['Tekken 8 projectiles of a shape TTT2 has not made cylinders'], 0)

    def test_look_placed_where_spawned(self):
        # his crystal pillar (missile 30: an id of his effect table), spawned 2.5 m ahead of his ground origin: a look
        # of its own (PROJECTILE_EFFECTS ..) at the hips' part, its place for the importer; the same again: that id
        self.k.tables['projectiles'][1] = projectile(1, 600, 150)
        raw = list(struct.unpack('<42I', self.k.tables['projectiles'][1]['raw']))
        raw[2] = 30
        self.k.tables['projectiles'][1]['raw'] = struct.pack('<42I', *raw)
        self.c.projectile_effects = {}
        at = {LIMB8: moveset.PROJ_GROUND8, LIMB8 + 1: 2500, LIMB8 + 2: 0, LIMB8 + 3: 0}
        self.assertEqual(self.c.projectile_look(1, at), moveset.PROJECTILE_EFFECTS)
        self.assertEqual(self.c.projectile_look(1, at), moveset.PROJECTILE_EFFECTS)
        self.assertEqual(self.c.projectile_look(1, {**at, LIMB8 + 1: 3500}), moveset.PROJECTILE_EFFECTS + 1)
        self.assertEqual(self.c.projectile_effects[moveset.PROJECTILE_EFFECTS],
                         dict(missile=30, life=5, at=(2500, 0, 0)))

    def test_no_look_without_a_missile(self):
        # his vortices (missile 0): Tekken 8 shows none; the moves' own effects do
        self.c.projectile_effects = {}
        self.assertIsNone(self.c.projectile_look(1, {LIMB8: moveset.PROJ_GROUND8}))
        self.assertEqual(self.c.projectile_effects, {})

    def spawn(self, limb, up):
        start = self.c.conv_xps(self.k.props((30, LIMB8, limb, None), (30, LIMB8 + 1, 2000, None),
                                             (30, LIMB8 + 2, up, None), (30, LIMB8 + 3, 0, None)), 0)
        rows = self.c.T['extra_move_properties'][start:]
        rows = rows[:next(n for n, r in enumerate(rows) if r['id'] == 0)]
        return {r['id']: r['value'] for r in rows}

    def test_ground_origin_from_the_hips(self):
        # spawned from his ground origin (limb 125), 1 m up: from his hips (limb 0), 1 m less his hips' height up
        self.c.proj_ground8 = 1600
        out = self.spawn(moveset.PROJ_GROUND8, 1000)
        self.assertEqual(out[moveset.TT_PROJ_LIMB], 0)
        self.assertEqual(out[moveset.TT_PROJ_OFFSETS[0]], 2000)
        self.assertEqual(out[moveset.TT_PROJ_OFFSETS[1]], (1000 - 1600) & 0xFFFF)

    def test_other_limb_or_no_height_as_before(self):
        self.c.proj_ground8 = 1600
        self.assertEqual(self.spawn(9, 1000)[moveset.TT_PROJ_OFFSETS[1]], 1000)
        self.c.proj_ground8 = None
        out = self.spawn(moveset.PROJ_GROUND8, 1000)
        self.assertEqual((out[moveset.TT_PROJ_LIMB], out[moveset.TT_PROJ_OFFSETS[1]]), (moveset.PROJ_GROUND8, 1000))

    def clip(self, heights, scale=1.8):
        """The move's clip: hips (channel 1) at heights[f] / scale over the root, frame by frame (a RAW animation)."""
        vals = np.zeros((len(heights), 3, 3), np.float32)
        vals[:, 1, 1] = np.asarray(heights, np.float32) / scale
        buf = animation.encode_raw([1, 2, 3], vals)
        self.c.move_anim = lambda move: 0x4001
        self.c.animation_bytes = lambda aid: (buf, '>', 0)
        self.c.animations = types.SimpleNamespace(converter=types.SimpleNamespace(scale=scale))

    def test_ground_from_the_clip(self):
        # 'clip': the hips' height of the spawn's frame (move frame 30 shows clip frame 29), not a constant
        self.c.proj_ground8 = moveset.PROJ_GROUND_CLIP
        self.clip([1600] * 29 + [1199] + [1600] * 10)
        out = self.spawn(moveset.PROJ_GROUND8, 1000)
        self.assertEqual(out[moveset.TT_PROJ_LIMB], 0)
        self.assertEqual(out[moveset.TT_PROJ_OFFSETS[1]], (1000 - 1199) & 0xFFFF)
        self.assertEqual(self.c.clip_hips(0, 1), 1600)
        self.assertEqual(self.c.clip_hips(0, 80), 1600)      # (past its end: its last frame, as the game holds it)

    def test_ground_from_the_clip_needs_a_move(self):
        self.c.proj_ground8 = moveset.PROJ_GROUND_CLIP
        with self.assertRaises(ValueError):
            self.c.ground_hips(None, 30)


class SlowThrows(unittest.TestCase):
    def setUp(self):
        self.c = converter(Source8(refs=[(0, 'own')]))
        self.c.T['requirements'] = [dict(condition=3, param=2500), dict(condition=moveset.TT_END, param=0)]

    def unseen(self, window, donor, own, game='t8'):
        self.c.game = game
        cl = [dict(direction=0, button=0, req=0, win_start=window[0], win_end=window[1])]
        return self.c.contact_unseen(cl, dict(first_active=donor[0], last_active=donor[1]),
                                     dict(first_active=own[0], last_active=own[1]))

    def test_late_throw_takes_its_frames(self):
        # Azazel's 1+3: i14-17 in Tekken 8, its rows at 14-17; Lars's grab 12-14 (f,f+1+2: 12 alone)
        self.assertTrue(self.unseen((14, 17), (12, 14), (14, 17)))
        self.assertTrue(self.unseen((14, 17), (12, 12), (14, 17)))

    def test_same_frames_or_tekken7_unchanged(self):
        self.assertFalse(self.unseen((12, 14), (12, 14), (12, 14)))
        self.assertFalse(self.unseen((12, 14), (12, 14), (12, 16)))      # (the rows see the donor's first frame)
        self.assertFalse(self.unseen((14, 17), (12, 14), (14, 17), game='t7'))


class WavesEndOnHit(unittest.TestCase):
    def setUp(self):
        self.c = converter(Source8(refs=[(0, 'own')]))
        self.c.T['requirements'] = [dict(condition=46, param=0), dict(condition=moveset.TT_END, param=0),
                                    dict(condition=moveset.TT_END, param=0)]

    def rows(self, *rows):
        self.c.T['cancels'] = [dict(direction=d, button=0, req=r, extradata=0, win_start=w, win_end=32767, start_frame=w,
                                    move_id=m, option=0) for d, r, w, m in rows]
        return dict(cancel=0)

    def order(self, row):
        return [c['move_id'] for c in moveset.tagsystem.cancels(self.c.T, row['cancel'])]

    def test_on_hit_row_first(self):
        # an All Direction Attack wave: the next wave at 201, the stance on a hit, the list's end (the stance at 480)
        row = self.rows((0, 1, 201, 7), (0, 0, 1, 1), (idmaps.LIST_END, 1, 480, 1))
        self.c.own_contact_first(row)
        self.assertEqual(self.order(row), [1, 7, 1])
        self.assertEqual(self.c.stats["thrown moves ending on their projectile's hit (on-hit rows first)"], 1)

    def test_action_only_row_leaves(self):
        # Tekken 8's hit row only runs its actions (0x2800, its action 0x803f not TTT2's): it ends the move as the
        # list's end does (its extradata); the next wave's row keeps its own
        self.c.T['cancel_extras'] = [dict(value=0x480), dict(value=moveset.tagcombo.ACTION_ONLY), dict(value=0x80)]
        row = self.rows((0, 1, 201, 7), (0, 0, 1, 1), (idmaps.LIST_END, 1, 480, 1))
        for c, x in zip(self.c.T['cancels'], (0, 1, 2)):
            c['extradata'] = x
        self.c.own_contact_first(row)
        rows = moveset.tagsystem.cancels(self.c.T, row['cancel'])
        self.assertEqual([(c['move_id'], c['extradata']) for c in rows], [(1, 2), (7, 0), (1, 2)])
        # already first: the row still leaves
        row = self.rows((0, 0, 1, 1), (0, 1, 201, 7), (idmaps.LIST_END, 1, 480, 1))
        for c, x in zip(self.c.T['cancels'], (1, 0, 2)):
            c['extradata'] = x
        self.c.own_contact_first(row)
        self.assertEqual([c['extradata'] for c in moveset.tagsystem.cancels(self.c.T, row['cancel'])], [2, 0, 2])

    def test_already_first_or_none(self):
        row = self.rows((0, 0, 1, 1), (0, 1, 201, 7), (idmaps.LIST_END, 2, 0, 0))
        self.c.own_contact_first(row)
        self.assertEqual(row['cancel'], 0)
        row = self.rows((0, 1, 201, 7), (idmaps.LIST_END, 2, 0, 0))
        self.c.own_contact_first(row)
        self.assertEqual(row['cancel'], 0)


class Beams(unittest.TestCase):
    """BEAM8: Tekken 8's beam (0x8262 kind, 0x8263 a pushback index, 0x8264 end) as TTT2's laser (0x8145 .. 0x8147)
    when the definition gives TEKKEN8['beam']."""

    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k)
        self.c.gauge, self.c.known_sounds, self.c.effects = None, set(), None
        self.k.tables['pushbacks'] = [dict(duration=0, displacement=0, loops=1, extradata=None)] * 3 + [
            dict(duration=0, displacement=0, loops=2, extradata=0)]
        self.k.tables['pushback_extras'] = [dict(value=800), dict(value=800)]
        self.c.T.update(pushbacks=[dict(duration=20, displacement=1300, loops=20, extradata=None)] * 5,
                        pushback_extras=[dict(value=1)])

    def beam(self, *rows):
        start = self.c.conv_xps(self.k.props(*rows), 0)
        if start is None:                   # (nothing left of the list)
            return []
        out = self.c.T['extra_move_properties'][start:]
        return [(r['frame'], r['id'], r['value']) for r in out[:next(n for n, r in enumerate(out) if r['id'] == 0)]]

    def test_beam_by_the_definition(self):
        # Azazel's 1+2: kind 17 at 36, his pushback 3 (the reach: 800 a frame) at 36, the end at 75
        self.c.beam8 = {17: 0, None: 0}
        rows = self.beam((36, 0x8262, 17, None), (36, 0x8263, 3, None), (75, 0x8264, 0, None))
        self.assertEqual(rows, [(36, 0x8145, 0), (36, 0x8146, 5), (75, 0x8147, 0)])
        self.assertEqual(self.c.T['pushbacks'][5], dict(duration=0, displacement=0, loops=2, extradata=1))
        self.assertEqual([x['value'] for x in self.c.T['pushback_extras'][1:3]], [800, 800])

    def test_beam_without_a_kind_gets_the_default(self):
        # his intro: a beam with no 0x8262 row of its own
        self.c.beam8 = {17: 9, None: 9}
        rows = self.beam((42, 0x8263, 3, None), (58, 0x8264, 0, None))
        self.assertEqual(rows, [(42, 0x8145, 9), (42, 0x8146, 5), (58, 0x8147, 0)])

    def test_kind_the_definition_has_not(self):
        self.c.beam8 = {17: 0}
        rows = self.beam((50, 0x8262, 21, None), (50, 0x8263, 3, None))
        self.assertEqual(rows, [(50, 0x8146, 5)])
        self.assertEqual(self.c.stats["property dropped: a Tekken 8 beam kind TEKKEN8['beam'] has not"], 1)

    def test_without_the_definition_as_before(self):
        self.c.beam8 = None
        rows = self.beam((36, 0x8262, 17, None), (36, 0x8263, 3, None))
        self.assertNotIn((36, 0x8146, 5), rows)


if __name__ == '__main__':
    unittest.main()
