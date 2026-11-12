"""convert/missiles8.py: a missile's projectiles and their looks, on a made-up path and made-up converter parts."""
import collections
import os
import struct
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from ttt2char.convert import missiles8, prefabs8, trails8  # noqa: E402

CLIP = 7


class _Trails:
    """A sampler's trails: the scene's holding joint stands 1 m ahead and 1.05 m up for 10 path points, then flies ahead
    300 mm a point."""
    skeleton = None

    def __init__(self):
        at = [(0.0, 1050.0, 1000.0)] * 10 + [(0.0, 1050.0, 1000.0 + 300.0 * g) for g in range(1, 21)]
        self.path = np.array(at)
        self.conv = type('Conv', (), {'scene': lambda conv, clip, joint: (self.path, None)})()

    def clip(self, move):
        return np.zeros((40, 30))


class _Recorded:
    """trails8.puff's stand-in: records each sprite's start, size and blending."""

    def __init__(self):
        self.made = []

    def __call__(self, conv, tex, place, delay, life, size, count, spread, speed, additive, alpha):
        tracks = collections.defaultdict(lambda: {'keys': []})
        e = {'raw': bytes(256), 'spawner': {'raw': bytes(512), 'tracks': tracks},
             'particle': {'raw': bytes(512), 'tracks': tracks}}
        self.made.append(dict(delay=delay, size=size, additive=additive, alpha=alpha, tex=tex, place=tuple(place), e=e))
        return e

    @staticmethod
    def local(m):
        return bool(struct.unpack_from('>I', m['e']['spawner']['raw'], 136)[0] & missiles8.P.SFLAG_LOCAL)

class Missiles8Test(unittest.TestCase):
    def patch(self, target, name, value):
        """target.name is value until the test ends (pytest's monkeypatch.setattr)."""
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def made_up(self):
        """A sampler of _Trails, the missile's clip started at frame 2 of every move."""
        self.patch(prefabs8, '_extras', lambda k, move: [dict(id=prefabs8.MISSILE_CLIP_PROP, frame=2, value=CLIP)])
        self.patch(prefabs8, '_entries', lambda k: {})
        self.patch(trails8, 'level_frame', lambda values, skeleton, f: (np.eye(3), np.zeros(3)))
        missiles8._ENTRIES.clear()
        return type('Sampler', (), {'trails': _Trails()})()

    def test_a_holding_ball_s_projectile_creeps_ahead_and_the_flight_goes_at_the_path_s_speed(self):
        made_up = self.made_up()
        hold, flight = missiles8.plan(made_up, object(), 1, 2, (missiles8.MISSILE, 'impulse', 'R_Have'), [])
        assert hold['phase'] == 'hold' and flight['phase'] == 'flight'
        assert hold['place'] == (1000.0, 1050.0, 0.0)            # (ahead, up: where the path stands)
        # moving, if only a little: roster.cpp keeps a look at its body part (the hips) until its projectile moves
        assert 0.0 < hold['speed'][0] <= 2.0 and hold['speed'][1] == 0.0
        assert hold['speed'][0] * hold['life'] < 50.0            # (it stays where it charges)
        assert flight['speed'] == (300.0, 0.0)
        assert flight['frame'] == hold['frame'] + hold['life']    # (the flight takes over as the hold ends)

    def test_a_spawn_where_the_path_has_run_to_is_a_still_burst_at_its_end(self):
        made_up = self.made_up()
        (end,) = missiles8.plan(made_up, object(), 1, 35, (missiles8.MISSILE, 'impulse', 'R_Have'), [])
        assert end['phase'] == 'end' and end['life'] == missiles8.END_LIFE
        assert end['place'] == (7000.0, 1050.0, 0.0)              # (the path's last point)
        assert end['frame'] == 34 and 0.0 < end['speed'][0] <= 2.0

    def test_no_sprite_of_a_look_shows_in_its_first_frame_and_the_ball_is_drawn_over_the_stage(self):
        self.patch(missiles8, '_tinted', lambda conv, system, role, tint, white: ('added', role, tint))
        self.patch(missiles8, '_drawn', lambda conv, kind, tint: ('drawn', kind, tint))
        for recipe in sorted(missiles8.RECIPES):
            with self.subTest(recipe=recipe), mock.patch.object(trails8, 'puff', _Recorded()) as made:
                bits = missiles8.RECIPES[recipe](None, None, 12)
                assert len(bits) == len(made.made) <= missiles8.P.MAX_EMITTERS
                assert all(m['delay'] >= missiles8.SHOWN >= 1 for m in made.made)    # (its first frame: the hips)
                over = [m for m in made.made if not m['additive']]
                assert {m['tex'][1] for m in over} >= {'orb', 'halo', 'ring'}
                assert all(m['tex'][0] == 'drawn' for m in over)

    def test_a_flying_ball_s_tail_is_a_streak_riding_behind_it_whatever_its_speed(self):
        self.patch(missiles8, '_tinted', lambda conv, system, role, tint, white: ('added', role, tint))
        self.patch(missiles8, '_drawn', lambda conv, kind, tint: ('drawn', kind, tint))
        for missile in ('dia', 'impulse'):
            with self.subTest(missile=missile), mock.patch.object(trails8, 'puff', _Recorded()) as made:
                missiles8.RECIPES[(missile, 'flight')](None, None, 12)
                streak = [m for m in made.made if _Recorded.local(m) and m['place'][2] < 0.0]
                backs = [-m['place'][2] for m in streak]
                assert len(streak) >= 3 and backs == sorted(backs)
                # (one after another closer than their size: no gaps between them, beads a frame's flight apart)
                assert all(b - a < m['size'] for a, b, m in zip([0.0] + backs, backs, streak))
                assert [m['size'] for m in streak] == sorted((m['size'] for m in streak), reverse=True)   # (thinning)
                assert all(m['additive'] and m['delay'] >= missiles8.SHOWN for m in streak)

    def test_the_drawn_pictures(self):
        n = missiles8.TEXTURE_SIDE
        blue = missiles8.ORB_BLUE
        orb, halo, ring = (missiles8.drawn(k, blue) for k in ('orb', 'halo', 'ring'))
        for p in (orb, halo, ring):
            assert p.shape == (n, n, 4) and p.min() >= 0 and p.max() <= 255
            assert p[0, 0, 3] == 0 and p[n // 2, 0, 3] < 20          # (nothing at its edge)
        c = n // 2
        assert (orb[c, c, :3] > 250).all() and orb[c, c, 3] > 250    # (a white core, whole)
        rim = int(c + c * 0.8)                                       # (its rim the tint's colour)
        assert orb[c, rim, 2] > 200 and orb[c, rim, 0] < 120
        assert halo[c, c, 3] > 240 and tuple(halo[c, c, :3]) == tuple(np.round(np.asarray(blue) * 255.0))
        across = ring[c, c:, 3]
        peak = int(np.argmax(across))
        assert abs(peak / c - missiles8.RING_AT) < 0.06 and across[0] < 10   # (a ring, empty inside)
        with self.assertRaises(KeyError):
            missiles8.drawn('square', blue)


if __name__ == '__main__':
    unittest.main()
