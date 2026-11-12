"""A Tekken 8 fighter's gauge: its ids through the converter, damage under a flag slot's test (GATED_DAMAGE8) and the HUD
bake (convert/gauge8.py), on made-up tables and pictures.

    python3 -m pytest -q tools/characters/tests/test_tekken8_gauge.py
"""
import math
import os
import struct
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import converter  # noqa: E402
from test_tekken8_flags import SLOT_TEST, STATE, Flags8, flagged  # noqa: E402
from ttt2char.convert import gauge as G  # noqa: E402
from ttt2char.convert import gauge8 as G8  # noqa: E402
from ttt2char.convert import tagsystem  # noqa: E402
from ttt2char.movesets import REACTION_MOVE_FIELDS  # noqa: E402

AMOUNT, DEAL, ROUND_DEAL, DIRECT, LEVEL_TEST, GAUGE_ADD = 0x828b, 0x828c, 0x838a, 0x808e, 738, 0x8232


class Ids(unittest.TestCase):
    def setUp(self):
        self.k = Flags8(refs=[(0, 'own')])
        self.c = converter(self.k, req={0: 0})
        self.c.gauge = dict(max=200, stock=50)

    def test_level_test_and_add(self):
        start, ok = self.c.conv_reqs(self.k.req((LEVEL_TEST, 150)))
        self.assertTrue(ok)
        self.assertEqual(tagsystem.reqs(self.c.T, start)[0], (G.AT_LEAST, 150))
        rows = tagsystem.props(self.c.T, self.c.conv_xps(self.k.props((23, GAUGE_ADD, 10, self.k.req((0, 0))))))
        self.assertEqual([(r['frame'], r['id'], r['value']) for r in rows if r['id'] != 0][:1], [(23, G.ADD, 10)])

    def test_an_add_under_a_test_is_an_action_row(self):
        c = flagged(self.c, {})
        latch_test = c.conv_reqs(self.k.req((0, 0)))[0]
        c.conv_reqs = lambda req: (latch_test + 1, True)
        c.always = lambda r: False
        c.flag8_gated = lambda req: False
        c.conv_xps(self.k.props((23, GAUGE_ADD, 10, self.k.req((0, 0)))), 2)
        self.assertEqual([(f, [(p['frame'], p['id'], p['value']) for p in props]) for f, _, props in c.flag8_moves[2]],
                         [(23, [(23, G.ADD, 10)])])

    def test_without_a_gauge_they_are_not_gauge_ids(self):
        self.c.gauge = None
        start, ok = self.c.conv_reqs(self.k.req((LEVEL_TEST, 150)))
        self.assertFalse(ok and tagsystem.reqs(self.c.T, start)[0] == (G.AT_LEAST, 150))


class GatedDamage(unittest.TestCase):
    """Two amounts under a slot's test, each with its deals (0 percent: the rest), a deal at the move's end in the id
    the other fighters' throws read, the victim's direct damage."""

    def setUp(self):
        self.k = Flags8(refs=[(0, 'own')])
        self.c = flagged(converter(self.k, req={0: 0}, prop={STATE: 0x80f8}), {0: 7})
        plain, other = self.k.req((SLOT_TEST, 0, 0)), self.k.req((SLOT_TEST, 0, 1))
        always = self.k.req((0, 0))
        self.xp = self.k.props((0x8001, AMOUNT, 40, plain), (10, DEAL, 25, plain), (20, DEAL, 0, plain),
                               (0x8001, AMOUNT, 30, other), (10, DEAL, 10, other), (20, DEAL, 0, other),
                               (30, ROUND_DEAL, 0, always))
        self.victim = self.k.props((10, STATE, 1, always), (30, STATE, 2, always), (20, DIRECT, 9, always))
        # move 2 (the attacker) puts its victim in move 3 by its hit's reaction
        self.k.tables['moves'] = [dict(hit_condition=None, extraprops=None)] * 2 + [
            dict(hit_condition=0, extraprops=self.xp), dict(hit_condition=None, extraprops=self.victim)]
        self.k.tables['hit_conditions'] = [dict(req=self.k.req(), damage=10, reactions=0)]
        self.k.tables['reactions'] = [dict({f: None for f in REACTION_MOVE_FIELDS}, standing=3)]

    def rows(self, i, move=2):
        return [(r['frame'], r['id'], r['value']) for r in tagsystem.props(self.c.T, self.c.conv_xps(i, move))]

    def test_on_each_test_its_own_points(self):
        self.c.gated_damage8 = True
        self.assertEqual([r for r in self.rows(self.xp) if r[1] == 0x8058], [(20, 0x8058, 9)])    # (only the victim's)
        held = [(f, [(p['id'], p['value']) for p in props]) for f, gate, props in self.c.flag8_moves[2] if props]
        self.assertEqual(held, [(10, [(0x8058, 10)]), (20, [(0x8058, 30)]), (10, [(0x8058, 3)]), (20, [(0x8058, 27)])])

    def test_the_victims_direct_damage_from_the_attacker(self):
        self.c.gated_damage8 = True
        self.assertEqual([r for r in self.rows(self.victim, 3) if r[1] == 0x8058], [])
        self.assertEqual([r for r in self.rows(self.xp) if 0 < r[0] < 0x8000], [(20, 0x8058, 9)])
        xp = self.k.props((10, STATE, 1, self.k.req((0, 0))), (30, STATE, 2, self.k.req((0, 0))))
        self.assertEqual([r[0] for r in self.rows(xp) if 0 < r[0] < 0x8000], [10, 20, 30])          # (in order)

    def test_off_as_before(self):
        self.c.gated_damage8 = False
        self.assertIn((30, 0x8058, 40), self.rows(self.xp))
        self.assertFalse([p for _, _, props in self.c.flag8_moves[2] for p in props if p['id'] == 0x8058])
        self.assertFalse([r for r in self.rows(self.victim, 3) if r[1] == 0x8058])


def arc_mask(size=64, low=225, high=315, inner=20, outer=28):
    """An arc from the angle `high` clockwise... through the gap: bright where it is (RGBA)."""
    y, x = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2
    radius = np.hypot(x - c, y - c)
    angle = np.degrees(np.arctan2(c - y, x - c)) % 360
    on = (radius >= inner) & (radius <= outer) & (angle >= low) & (angle <= high)
    image = np.zeros((size, size, 4), np.uint8)
    image[on] = 255
    return image


def pictures(size=64):
    solid = np.full((size, size, 4), 128, np.uint8)
    out = {role: solid.copy() for role in G8.HUD8_PICTURES}
    out['mask'] = arc_mask(size)
    big, small = np.full((32, 192, 4), 200, np.uint8), np.full((16, 96, 4), 200, np.uint8)
    out.update(num=big, num_edge=small, num_add=small.copy())
    return out


def keys():
    return {role: (G8.Keys([(0, 0), (4, 1), (9, 0)]), G8.Keys([(0, 2), (9, 1)])) for role in G8.HUD8_LAYERS}


def parsed(lines):
    out = {}
    frame = None
    for line in lines:
        p = line.split()
        if p[0] == 'clip':
            out[p[1], p[2]] = [[] for _ in range(int(p[3]))]
        elif p[0] == 'frame':
            frame = out[p[1], p[2]][int(p[3])]
        elif p[0] == 'q':
            frame.append([float(a) for a in p[1:9]] + p[9:])
    return out


class Bake(unittest.TestCase):
    def setUp(self):
        self.atlas, self.lines = G8.bake(pictures(), keys(), keys(), log=lambda s: None)
        self.clips = parsed(self.lines)

    def test_arc_and_progress(self):
        cover, centre, start, end = G8.arc_of(arc_mask())
        self.assertAlmostEqual(start, 315, delta=2)
        self.assertAlmostEqual(end, 225, delta=2)
        t = G8.progress(cover.shape, centre, start, end)
        on = cover > .5
        self.assertAlmostEqual(float(t[on].min()), 0, delta=.05)
        self.assertAlmostEqual(float(t[on].max()), 1, delta=.05)

    def test_clips(self):
        self.assertIn('style ring', self.lines)
        for side in 'LR':
            self.assertEqual(len(self.clips[side, 'fill']), G8.STEPS)
            self.assertEqual(len(self.clips[side, 'white']), G8.STEPS)
            self.assertEqual(len(self.clips[side, 'head']), G8.STEPS)
            self.assertEqual(len(self.clips[side, 'blink']), G8.BLINK_FRAMES)
            self.assertFalse(self.clips[side, 'up'][-1])                # a level up ends with nothing
            for n in range(1, 6):
                self.assertTrue(self.clips[side, 'digit%d' % n][-1])    # a number at rest
            self.assertEqual(len(self.clips[side, 'digit1']), 1)        # 1: never comes in

    def test_right_side_mirrors_the_arc_and_not_the_number(self):
        for a, b in zip(self.clips['L', 'fill'], self.clips['R', 'fill']):
            for p, q in zip(a, b):
                self.assertAlmostEqual(p[0], -q[0], places=2)
                self.assertEqual(p[4:8], q[4:8])
        self.assertEqual(self.clips['L', 'digit3'][-1], self.clips['R', 'digit3'][-1])

    def test_places_mirror_about_the_bars(self):
        places = dict((p.split()[1], [float(v) for v in p.split()[2:]]) for p in self.lines if p.startswith('place'))
        self.assertAlmostEqual(places['L'][0] + places['R'][0], 2 * G8.BARS_MIDDLE, places=1)
        self.assertEqual(places['L'][1], places['R'][1])

    def test_pictures_are_on_blocks_and_in_the_atlas(self):
        h, w = self.atlas.shape[:2]
        for frames in self.clips.values():
            for rows in frames:
                for q in rows:
                    self.assertEqual(q[4] % 4, 0)
                    self.assertEqual(q[5] % 4, 0)
                    self.assertLessEqual(q[6], w)
                    self.assertLessEqual(q[7], h)

    def test_no_hud_without_the_definitions_folder(self):
        self.assertEqual(G8.hud_files(None, types.SimpleNamespace(GAUGE=dict(max=200, stock=50))), {})


class Channels(unittest.TestCase):
    def test_keys_from_bytes(self):
        def channel(times, values):
            n = len(times)
            return (struct.pack('<ii', 4, n) + struct.pack('<%di' % n, *times) + struct.pack('<ii', 28, n)
                    + b''.join(struct.pack('<f', v) + bytes(24) for v in values))
        data = b'\xff' * 7 + channel((0, 12000), (0.25, 1.5)) + b'\x00' * 3 + channel((60000,), (2.0,))
        self.assertEqual(G8.channels(data), [[(0, 0.25), (12, 1.5)], [(60, 2.0)]])


if __name__ == '__main__':
    unittest.main()
