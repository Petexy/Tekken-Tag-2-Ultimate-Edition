"""A Tekken 7 super's time stop: slow motion its fighter is immune to stops the opponent (convert/gauge.py)."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest
from ttt2char.convert import gauge as G


class TimeStop(unittest.TestCase):
    def test_slow_motion_the_attacker_is_immune_to_stops_the_opponent(self):
        rows = [(8, 0x81c2, -1000, None), (8, 0x828c, 0x10046, None), (8, 0x828d, 1, None)]
        self.assertEqual(G.stop_frames(rows, 0x828c, 0x10046, 't7'), 70)

    def test_slow_motion_for_both_or_other_ids_is_not_a_stop(self):
        self.assertIsNone(G.stop_frames([(8, 0x828c, 0x10046, None)], 0x828c, 0x10046, 't7'))
        self.assertIsNone(G.stop_frames([(8, 0x828d, 1, None)], 0x81c2, -1000, 't7'))
        self.assertIsNone(G.stop_frames([(8, 0x828d, 1, None)], 0x828c, 0x10000, 't7'))
        self.assertIsNone(G.stop_frames([(8, 0x828d, 1, None)], 0x828c, 0x10046, 't8'))


class ProjectileHits(unittest.TestCase):
    # a projectile's cancel rows: (requirement ids, option, the projectile it turns into)
    ROWS = {1: [((784,), 0x41, 2), ((787,), 0x41, 5)], 2: [((784,), 0x41, 3)], 3: [((784,), 0x01, 0)], 4: [], 5: []}

    def hits(self, pi):
        k = type('K', (), {'tables': {'projectiles': [{'cancel': i} for i in range(6)]}})()
        cancels = lambda k_, i: [dict(req=r, option=o, move_id=m) for r, o, m in self.ROWS[i]]
        reqs = lambda k_, r: [(a, 0) for a in r]
        return G.projectile_hits(k, pi, 't7', cancels, reqs)

    def test_a_projectile_hits_once_and_once_more_for_each_it_turns_into_on_a_hit(self):
        self.assertEqual(self.hits(1), 3)       # 1 -> 2 -> 3 on hits (5 on a block: not counted)
        self.assertEqual(self.hits(4), 1)

    def test_a_chain_back_to_itself_ends(self):
        self.ROWS = {**self.ROWS, 3: [((784,), 0x41, 1)]}
        self.assertEqual(self.hits(1), 3)


class SoundEffects(unittest.TestCase):
    def effects(self):
        from ttt2char.convert import sounds
        e = sounds.Effects.__new__(sounds.Effects)
        e.table = [None] * 72 + ['SE_battle_spcombo_start']
        e.table[57] = 'mrx_hadou01_shot'
        e.names, e.hits, e.base = ['mrx_hadou01_shot', 'SE_battle_spcombo_start', 'mrx_hadou01_hit'], \
            {5: 'mrx_hadou01_hit'}, 6
        return e

    def test_bank_15_sounds_are_the_fighters_item_sounds_after_the_donors(self):
        e = self.effects()
        self.assertEqual(e.move_value(15 << 24 | 57), 12 << 24 | 1 << 12 | 6)      # Akuma's fireball throw
        self.assertEqual(e.move_value(15 << 24 | 72), 12 << 24 | 1 << 12 | 7)      # a super's start
        self.assertIsNone(e.move_value(15 << 24 | 60))                             # one it does not have
        self.assertIsNone(e.move_value(7 << 24 | 57))                              # another bank

    def test_a_projectile_hits_with_its_missiles_sound(self):
        e = self.effects()
        self.assertEqual(e.hit_value(5), 12 << 24 | 1 << 12 | 8)
        self.assertIsNone(e.hit_value(4))

    def test_an_effects_item_sound_number(self):
        e = self.effects()
        self.assertEqual(e.number('mrx_hadou01_hit'), 8)
        self.assertIsNone(e.number('SE_battle_spgauge_full'))

    def test_a_moves_sounds_and_its_hits_in_its_cancel_rows(self):
        from ttt2char.convert import sounds
        names = [None] * 430 + ['se_mrz_hit_sword']
        names[57] = 'mrx_hadou01_shot'
        k = type('K', (), {'tables': {'moves': [{'extraprops': 0, 'cancel': 0}, {'extraprops': 1, 'cancel': 1}]},
                           'move_name': lambda self, i: ['Mz_rush01', 'Mz_RageArt00'][i]})()
        xps = lambda m, i: [(1, 0x84c4, 15 << 24 | 57), (1, 0x84c4, 7 << 24 | 16)]
        actions = lambda m, mv: [(44, 0), (0x802e, 99), (0x84c6, 15 << 24 | 430)]       # a sword hit's row
        kept = lambda name: not sounds.LEFT_OUT.search(name)
        self.assertEqual(sounds.move_sounds(names, k, xps, kept, actions), ['mrx_hadou01_shot', 'se_mrz_hit_sword'])
        self.assertEqual(sounds.move_sounds(names, k, xps, kept), ['mrx_hadou01_shot'])

    def test_the_moves_the_converter_leaves_out_play_none(self):
        """(the importer's kept(): a Rage Drive, _EX, is left out without a gauge, an EX move kept with one)"""
        import types
        from ttt2char.convert import moveset
        d = types.SimpleNamespace(MOVESET={'drop_moves': r'^Ka_Fly'})
        self.assertTrue(moveset.drop_moves(d).search('Ka_66rp_EX'))
        self.assertTrue(moveset.drop_moves(d).search('Ka_Fly00'))
        self.assertFalse(moveset.drop_moves(d).search('Ka_66rp'))
        d.GAUGE = {'full_sound': None}
        self.assertFalse(moveset.drop_moves(d).search('Ka_66rp_EX'))


class FullSound(unittest.TestCase):
    """Tekken 7 plays SE_battle_spgauge_full as Akuma's and Eliza's gauges fill up; the gauge line's last field."""
    def test_the_gauge_line_ends_in_its_full_sound_when_it_has_one(self):
        from ttt2char.characters import definition
        akuma = definition('akuma')
        self.assertEqual(G.ini_line(akuma), 'gauge = 1000 500 37 75 112 225')
        self.assertEqual(G.ini_line(akuma, 18), 'gauge = 1000 500 37 75 112 225 18')

    def test_a_gauge_turned_off_is_written_commented_out_under_how_to_turn_it_on(self):
        d = type('D', (), {'GAUGE': dict(max=300, stock=100, gain=(1, 2, 3, 4), on=False, name='Spark meter')})
        self.assertEqual(G.ini_line(d), '# Spark meter: off. To turn it on, delete the # at the start of the next line '
                                        '(put it back to turn it off)\n#gauge = 300 100 1 2 3 4')
        d.GAUGE['on'] = True
        self.assertEqual(G.ini_line(d), 'gauge = 300 100 1 2 3 4')

    def test_akuma_and_eliza_name_it_and_geese_does_not(self):
        from ttt2char.characters import definition
        self.assertEqual(G.full_sound(definition('akuma')), 'SE_battle_spgauge_full')
        self.assertEqual(G.full_sound(definition('eliza')), 'SE_battle_spgauge_full')
        self.assertIsNone(G.full_sound(definition('geese')))


if __name__ == '__main__':
    unittest.main()
