"""THROW_PAIRS8 (convert/moveset.py Converter.throw_pairs8): a giant's throws, placed for the game's throw scale: his
victims' ground paths divided by his skeleton's scale (MOVESET 'victim_ground'), the heights of his throw moves' and his
victims' clips scaled by scale / F and 1 / F (MOVESET 'throw_height' F)."""
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_retarget import smooth_values  # noqa: E402
from test_tekken8_convert import Source8, converter  # noqa: E402
from ttt2char.convert import moveset, retarget  # noqa: E402
from ttt2char.ttt2 import animation  # noqa: E402


class ThrowPairs(unittest.TestCase):
    def make(self, rows, victims=(), throwers=(), ground=True, height=None, scale=1.8):
        """A converter with two converted clips (0x4001, 0x4002: ground paths of 1..1.5 m, the hips 0.9 m up) and moves
        `rows` (their animation ids); `victims` the rows his throws put the opponent in, `throwers` his THROW_LEVEL
        moves' rows."""
        c = converter(Source8(refs=[None] * 4))
        c.defn.MOVESET = dict(c.defn.MOVESET, victim_ground=ground)
        if height:
            c.defn.MOVESET['throw_height'] = height
        clips = []
        for n in range(2):
            v = smooth_values(30, seed=5 + n)
            v[:, 0] = 0.0
            v[:, 0, 0] = np.linspace(0, 1000 + 500 * n, 30)
            v[:, 0, 2] = np.linspace(0, -800, 30)
            v[:, 1] = 0.0
            v[:, 1, 1] = np.linspace(900, 1300, 30)
            clips.append(retarget.encode(v))
        c.pack0_count, c.new_anims = 1, list(clips)
        self.before = [animation.decode(x)['values'] for x in clips]
        c.animations = types.SimpleNamespace(converter=types.SimpleNamespace(scale=scale))
        c.T['moves'] = [dict(anim=a, transition=0x8001) for a in rows]
        for r in throwers:
            c.k.tables['moves'][r]['hitlevel'] = moveset.THROW_LEVEL
        c.newidx = {r: r for r in range(len(rows))}
        c._throw_victims = set(victims)
        c.throw_pairs8()
        return c

    def values(self, c, n):
        return animation.decode(c.new_anims[n])['values']

    def test_victim_ground(self):
        """A victim's own clip: x and z of the ground path / 1.8, its height and rotations as they were; others kept."""
        c = self.make([0x4001, 0x4002], victims=[0])
        out = self.values(c, 0)
        self.assertTrue(np.allclose(out[:, 0, 0], self.before[0][:, 0, 0] / 1.8, atol=2))
        self.assertTrue(np.allclose(out[:, 0, 2], self.before[0][:, 0, 2] / 1.8, atol=2))
        self.assertTrue(np.allclose(out[:, 1], self.before[0][:, 1], atol=2))
        self.assertTrue(np.allclose(out[:, 2:], self.before[0][:, 2:], atol=1e-3))
        self.assertTrue(np.allclose(self.values(c, 1), self.before[1], atol=1e-3))
        self.assertEqual([r['anim'] for r in c.T['moves']], [0x4001, 0x4002])

    def test_heights(self):
        """'throw_height' F: the victim's height / F (and its ground / 1.8), the thrower's height x 1.8 / F (his ground
        as it was)."""
        c = self.make([0x4001, 0x4002], victims=[0], throwers=[1], height=1.2)
        vic, his = self.values(c, 0), self.values(c, 1)
        self.assertTrue(np.allclose(vic[:, 1, 1], self.before[0][:, 1, 1] / 1.2, atol=2))
        self.assertTrue(np.allclose(vic[:, 0, 0], self.before[0][:, 0, 0] / 1.8, atol=2))
        self.assertTrue(np.allclose(his[:, 1, 1], self.before[1][:, 1, 1] * 1.5, atol=2))
        self.assertTrue(np.allclose(his[:, 0], self.before[1][:, 0], atol=2))
        self.assertTrue(np.allclose(his[:, 2:], self.before[1][:, 2:], atol=1e-3))
        self.assertEqual(c.stats['throw pairs: thrower clips placed for the game\'s throw scale (THROW_PAIRS8)'], 1)

    def test_shared_copy(self):
        """A clip a victim shares with one of his other moves: the victim gets a changed copy, his move the original."""
        c = self.make([0x4001, 0x4001], victims=[1])
        self.assertEqual(len(c.new_anims), 3)
        self.assertEqual([r['anim'] for r in c.T['moves']], [0x4001, 0x4003])
        self.assertTrue(np.allclose(self.values(c, 0), self.before[0], atol=1e-3))
        self.assertTrue(np.allclose(self.values(c, 2)[:, 0, 0], self.before[0][:, 0, 0] / 1.8, atol=2))

    def test_ttt2_animation(self):
        """A victim move playing a TTT2 animation keeps it."""
        c = self.make([0x8123, 0x4002], victims=[0], throwers=[1], height=1.2)
        self.assertEqual(c.T['moves'][0]['anim'], 0x8123)
        self.assertEqual(c.stats['throw pairs: a TTT2 animation, left as it is'], 1)

    def test_gated(self):
        """Without the definition's keys, or at scale 1 without a height, nothing changes."""
        for c in (self.make([0x4001, 0x4002], victims=[0], throwers=[1], ground=False),
                  self.make([0x4001, 0x4002], victims=[0], throwers=[1], scale=1.0)):
            self.assertEqual(len(c.new_anims), 2)
            for n in range(2):
                self.assertTrue(np.allclose(self.values(c, n), self.before[n], atol=1e-3))


if __name__ == '__main__':
    unittest.main()
