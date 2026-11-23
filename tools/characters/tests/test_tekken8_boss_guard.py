"""Unit tests of Tekken 8's boss guard (convert/moveset.py vuln8, BOSS_GUARD8): Azazel's walks, dashes and back steps
guard highs, mids and lows in Tekken 8 (their state 0xe81a); converted they guard as every other fighter's (forward:
nothing, back: highs and mids), on made-up moves (no game files needed).

    python3 -m unittest tests.test_tekken8_boss_guard
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import moveset  # noqa: E402

STAND_GUARD, CROUCH_GUARD = 0x10, 0x8          # the state's guard bits (TTT2's stance 0x1952, crouch 0x3929)


def converter(game, vulns):
    """A Converter with only what conv_move reads, over made-up source moves of these vuln words."""
    c = moveset.Converter.__new__(moveset.Converter)
    c.game = game
    moves = [dict(vuln=v, hitlevel=0, m_56=0, airborne_start=0, airborne_end=0, ground_fall=0, bitfield=0,
                  hitbox=[0, 0, 0, 0], first_active=0, last_active=0, m_a8=0, distance=0) for v in vulns]
    c.k = types.SimpleNamespace(tables={'moves': moves}, anim_name=lambda i: 'anim%d' % i)
    c.string = lambda s: s
    c.ttt2_name = lambda i: 'move%d' % i
    c.move_anim = lambda i: 0
    c.hit_location = lambda x: x
    return c


class BossGuard(unittest.TestCase):
    # Azazel's Tekken 8 moves (got, build 26155785) -> what the same moves of Tekken 8's other fighters have
    BOSS = {0x1e81a: 0x10842,       # walk forward 1305 / 1307, the dash's second part 1309
            0x9e81a: 0x90842,       # f,f dash 1308 (Bryan's, Kazuya's, Heihachi's, Hwoarang's dash: 0x90842)
            0x2e81a: 0x21052,       # walk back 1310 / 1312, back steps and back dashes 1313-1316
            0xe81a: 0x1052}         # 1703 (after his story intro): no direction, standing and guarding highs, mids

    def test_boss_state_becomes_an_ordinary_fighters(self):
        for boss, ordinary in self.BOSS.items():
            self.assertTrue(boss & STAND_GUARD and boss & CROUCH_GUARD)
            self.assertEqual(moveset.vuln8(boss), ordinary, hex(boss))
            self.assertFalse(moveset.vuln8(boss) & CROUCH_GUARD)

    def test_forward_guards_nothing_back_highs_and_mids(self):
        self.assertEqual(moveset.vuln8(0x1e81a) & (STAND_GUARD | CROUCH_GUARD), 0)
        self.assertEqual(moveset.vuln8(0x2e81a) & (STAND_GUARD | CROUCH_GUARD), STAND_GUARD)

    def test_other_states_untouched(self):
        for v in (0x842, 0x1052, 0x1952, 0x3929, 0x10842, 0x21052, 0x90842, 0x23029, 0x2821, 0x7402, 0x6084, 0xa000,
                  0xc842, 0x1c842, 0x1007402, 0x40a000):
            self.assertEqual(moveset.vuln8(v), v, hex(v))

    def test_conv_move_tekken8_only(self):
        vulns = [0x1e81a, 0x2e81a, 0x1952]
        self.assertEqual([converter('t8', vulns).conv_move(i)['vuln'] for i in range(3)], [0x10842, 0x21052, 0x1952])
        self.assertEqual([converter('t7', vulns).conv_move(i)['vuln'] for i in range(3)], vulns)


if __name__ == '__main__':
    unittest.main()
