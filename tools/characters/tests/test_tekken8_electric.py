"""Unit tests of the electrics of a Tekken 8 fighter (convert/moveset.py: the electric marker, Kazuya's lightning on
the striking limb, the hits' sound actions in requirement lists; importer.py: the lightning's effect file in the
pack), on made-up tables (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_electric.py
"""
import collections
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_tekken8_convert import END8, Source8, converted, converter  # noqa: E402
from ttt2char import importer  # noqa: E402
from ttt2char.characters import definition  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402

HIT = 44                    # Tekken 8's "the attack hit" (TTT2's 46 by the id maps)


def electric_source(*moves):
    """A Tekken 8 moveset of moves (name, hitlevel, first active frame, hit box, electric marker or None)."""
    k = Source8({i: m[0] for i, m in enumerate(moves)}, [(i, 'own') for i in range(len(moves))])
    always = k.req((0, 0))
    for i, (name, hitlevel, first, hitbox, mark) in enumerate(moves):
        rows = [(2, 0x87f0, 1, always, 43)]                     # the common spark sound, bank 1 n 43
        if mark is not None:
            rows.append((0x8001, moveset.ELECTRIC_MARK['t8'], mark, always))
        k.tables['moves'][i].update(hitlevel=hitlevel, first_active=first, last_active=first + 1, hitbox=hitbox,
                                    extraprops=k.props(*rows))
    return k


def electric_converter(k):
    c = converter(k, req={HIT: 46, 0: 0}, prop={0x87f0: 0x82f9, 0x8003: 0x8003})
    c.hit_locations, c.hitbox, c.electric_moves = {}, {}, []
    c.donor_sound[0x82f9] |= {0x0100002B, 0x01000018, 0x07000010}
    return c


def rows_of(c, start):
    rows = c.T['extra_move_properties'][start:]
    return [(r['frame'], r['id'], r['value']) for r in rows[:next(i for i, r in enumerate(rows) if r['id'] == 0)]]


class Lightning(unittest.TestCase):
    def test_electric_wind_god_fist(self):
        # Reina's EWGF (hit points: right hand, forearm; active from 11): the marker becomes TTT2's 0x8192 = 1 and
        # Kazuya's lightning (ELECTRIC_EFFECT) appears on the right shoulder 5 frames before the hit, as his
        # 0x801d 7 at frame 6 does; the common spark sound stays
        k = electric_source(('Zbr_shoryu_S', 0x2c0512, 11, bytes([9, 0, 9, 8]), 1))
        c = electric_converter(k)
        start = c.conv_xps(k.tables['moves'][0]['extraprops'], 0)
        self.assertEqual(rows_of(c, start), [(2, 0x82f9, 0x0100002B), (0x8001, moveset.ELECTRIC_PROP, 1),
                                             (6, moveset.EFFECT_PROP, 7 << 8 | moveset.ELECTRIC_EFFECT)])
        self.assertEqual(c.electric_moves, ['Zbr_shoryu_S'])
        self.assertEqual(c.stats['electrics given Kazuya\'s lightning'], 1)

    def test_limbs(self):
        # the root of the limb of the first hit point: a left kick (foot, knee) on the left thigh, a left punch on the
        # left shoulder; frame 1 at the earliest
        k = electric_source(('Zbr_step_LK_S', 0x217, 15, bytes([19, 0, 18, 15]), 1),
                            ('#1747', 0x20010f, 3, bytes([13, 0, 0, 0]), 1))
        c = electric_converter(k)
        kick = rows_of(c, c.conv_xps(k.tables['moves'][0]['extraprops'], 0))[-1]
        punch = rows_of(c, c.conv_xps(k.tables['moves'][1]['extraprops'], 1))[-1]
        self.assertEqual(kick, (10, moveset.EFFECT_PROP, 17 << 8 | moveset.ELECTRIC_EFFECT))
        self.assertEqual(punch, (1, moveset.EFFECT_PROP, 11 << 8 | moveset.ELECTRIC_EFFECT))

    def test_no_lightning(self):
        # no marker (the plain Wind God Fist), a marker of 0, an electric that does not strike (a Heat transition) or
        # strikes with no limb (a throw's hit box), and a list with no move: no lightning
        k = electric_source(('Zbr_shoryu_N', 0x2c0512, 11, bytes([9, 0, 9, 8]), None),
                            ('Zbr_x', 0x2c0512, 11, bytes([9, 0, 9, 8]), 0),
                            ('#1827', 0, 0, bytes(4), 1),
                            ('#2112', 0xa00, 0, bytes(4), 1))
        c = electric_converter(k)
        for i in range(4):
            rows = rows_of(c, c.conv_xps(k.tables['moves'][i]['extraprops'], i))
            self.assertNotIn(moveset.EFFECT_PROP, [r[1] for r in rows])
        self.assertEqual(rows_of(c, c.conv_xps(k.tables['moves'][2]['extraprops'])),
                         [(2, 0x82f9, 0x0100002B), (0x8001, moveset.ELECTRIC_PROP, 1)])
        self.assertEqual(c.electric_moves, [])

    def test_tekken7_unchanged(self):
        self.assertIsNone(moveset.ELECTRIC_MARK['t7'])
        self.assertNotIn(moveset.ELECTRIC_MARK['t8'], moveset.PROP_OVERRIDE['t7'])
        self.assertEqual(moveset.PROP_OVERRIDE['t8'][moveset.ELECTRIC_MARK['t8']], moveset.ELECTRIC_PROP)


class RequirementSounds(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = electric_converter(self.k)

    def req(self, *rows):
        """A requirement list of (condition, param, param2, param3)."""
        start = len(self.k.tables['requirements'])
        for r in rows + ((END8, 0, 0, 0),):
            self.k.tables['requirements'].append(dict(condition=r[0], param=r[1], param2=r[2], param3=r[3], param4=0))
        return start

    def test_hit_sounds(self):
        # the EWGF's first cancel row: on the hit, the lightning punch (bank 1 n 24) and the hit sound (bank 7 n 16)
        # as actions; Tekken 8 splits their values as in property rows (bank in param, n in param3)
        start, ok = self.c.conv_reqs(self.req((HIT, 0, 0, 0), (0x8003, 0, 0, 0), (0x87f0, 1, 0, 24),
                                              (0x87f0, 7, 0, 16)))
        self.assertTrue(ok)
        self.assertEqual(converted(self.c, start), [(46, 0), (0x8003, 0), (0x82f9, 0x01000018), (0x82f9, 0x07000010)])

    def test_left_out(self):
        # a sound the donor never plays and a kind's voice said by a chance below CHANCE8 are left out, the list kept
        c = self.c
        c.voices8, c.voice_turns = {(17, 0): [0x02000000]}, collections.Counter()
        start, ok = c.conv_reqs(self.req((HIT, 0, 0, 0), (0x87f0, 15, 0, 4096), (0x87f0, 17, 40, 0)))
        self.assertTrue(ok)
        self.assertEqual(converted(c, start), [(46, 0)])
        self.assertEqual(c.stats['property left out of a requirement list'], 2)
        start, ok = c.conv_reqs(self.req((0x87f0, 17, 60, 0)))
        self.assertEqual(converted(c, start), [(0x82f9, 0x02000000)])

    def test_value(self):
        c = self.c
        self.assertEqual(c.req_value(dict(condition=0x87f2, param=7, param2=0, param3=17)), 0x07000011)
        self.assertEqual(c.req_value(dict(condition=HIT, param=3, param2=0, param3=9)), 3)
        c.game = 't7'                                       # Tekken 7's values are whole
        self.assertEqual(c.req_value(dict(condition=0x84c4, param=0x01000018)), 0x01000018)


class ImporterEffect(unittest.TestCase):
    """_converted_tekken8_moveset gives the pack Kazuya's lightning (a copy of his TTT2 effect file under
    ELECTRIC_EFFECT) when the converter gave electrics the lightning, else the donor's effects alone."""

    def run_step(self, electric_moves):
        d = definition('reina')
        k = mock.Mock(character_id=28)
        files = {'anmbin': 'own.anmbin', 'common': 'com.anmbin', 'mvl': 'zbr.mvl'}
        archives = mock.Mock()
        archives.entry.side_effect = lambda what, row: (what, row)
        c = mock.Mock(projectile_effects={}, electric_moves=electric_moves)
        c.write.return_value = (b'moves', b'motions')
        c.summary.return_value = []
        lines = []
        kaz = b'ALO.AL_EFFECT\0tfm_kaz00.nut\0'               # (an effect file names its textures at its end)
        copied = ({'alo/eff_koyuu00.alo': b'jun', 'alo/eff_koyuu00_kaz.alo': kaz, 'alo/texture/tfm_kaz00.nut': b't'},
                  {moveset.ELECTRIC_EFFECT: [('eff_koyuu00_kaz', None)]}, ['eff_koyuu00'])
        with mock.patch('ttt2char.tekken8.movenames.ttt2_movesets', return_value=['row'] * 66), \
                mock.patch('ttt2char.tekken8.movenames.name_moves'), \
                mock.patch('ttt2char.tekken8.movenames.harvest', return_value=(set(), set())), \
                mock.patch('ttt2char.tekken8.motbin.read_bank', side_effect=lambda p: p), \
                mock.patch('ttt2char.tekken8.anmbin.Bank'), \
                mock.patch('ttt2char.tekken8.anim.load_skeleton'), \
                mock.patch('ttt2char.tekken8.anim.Converter'), \
                mock.patch('ttt2char.tekken8.anim.originals', return_value={}), \
                mock.patch('ttt2char.tekken8.movelist.convert', return_value=b'mvl'), \
                mock.patch.object(importer, '_read', side_effect=lambda p: p.encode()), \
                mock.patch.object(importer.idmaps, 'tekken8_maps', return_value=('r', 'p', 'rr', 'hb', 'ev')), \
                mock.patch.object(importer.idmaps, 'ttt2_usage'), \
                mock.patch.object(importer.tagsystem, 'TagStates'), \
                mock.patch.object(importer.moveset, 'Converter', return_value=c), \
                mock.patch.object(importer, '_options'), \
                mock.patch.object(importer.bone, 'read'), \
                mock.patch.object(importer.itemdb, 'effect_names', return_value=['eff_koyuu00']), \
                mock.patch.object(importer.itemdb, 'body_only', return_value=b'db') as body_only, \
                mock.patch.object(importer.itemdb, 'effect_files_named',
                                  return_value={'eff_koyuu00', 'eff_koyuu00_kaz'}), \
                mock.patch.object(importer.fx, 'copy_files', return_value=copied) as copy_files:
            out = importer._converted_tekken8_moveset(
                mock.Mock(store='store'), archives, d, {'row': 70}, (k, files, []), b'<jun/>',
                {'alo/eff_koyuu00.alo': b'jun'}, {}, 'vlist', (), b'bon', lines.append, lambda s: None, {})
        return out, body_only, copy_files, lines

    def test_lightning(self):
        out, body_only, copy_files, lines = self.run_step(['Zbr_shoryu_S'])
        self.assertEqual(copy_files.call_args[0][1:], ('jun', ['eff_koyuu00'],
                                                       {moveset.ELECTRIC_EFFECT: [(moveset.ELECTRIC_LOOK, None)]}))
        self.assertEqual(body_only.call_args[0], (b'<jun/>', {moveset.ELECTRIC_EFFECT: [('eff_koyuu00_kaz', None)]}))
        self.assertEqual(sorted(out[3]), ['alo/eff_koyuu00.alo', 'alo/eff_koyuu00_kaz.alo',
                                          'alo/texture/tfm_kaz00.nut'])
        self.assertTrue(any('Zbr_shoryu_S' in line for line in lines))

    def test_none(self):
        out, body_only, copy_files, _ = self.run_step([])
        copy_files.assert_not_called()
        self.assertEqual(body_only.call_args[0], (b'<jun/>', None))
        self.assertEqual(out[3], {'alo/eff_koyuu00.alo': b'jun'})


if __name__ == '__main__':
    unittest.main()
