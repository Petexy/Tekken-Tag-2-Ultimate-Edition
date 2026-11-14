"""Unit tests of a Tekken 8 beam's look (convert/effects.py: the meshes an effect file names; importer.py: the
definition's TEKKEN8['beam_look'], a TTT2 fighter's laser effect copied into the pack as effect 100), on made-up
files (no game files needed).

    python3 -m unittest tests.test_beam_look
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_tekken8_electric as electric  # noqa: E402
from ttt2char.characters import definition  # noqa: E402
from ttt2char.convert import effects as fx, moveset  # noqa: E402
from ttt2char.ttt2 import alo  # noqa: E402
from ttt2char.ttt2.archive import key_of  # noqa: E402

BEAM = b'OELA..' + fx.ALO_END + b'tfm_dvj00.nut\0mfm_dvjbeam00.nud\0mfm_dvjbeam01.nud\0'


class Archives:
    def __init__(self, files):
        self.files = {key_of(name): data for name, data in files.items()}

    def has(self, key):
        return key in self.files

    def read_name(self, name):
        return self.files[key_of(name)]


class Meshes(unittest.TestCase):
    def setUp(self):
        self.archives = Archives({'dvj/alo/eff_koyuu_beam00.alo': BEAM, 'dvj/alo/texture/tfm_dvj00.nut': b't',
                                  'dvj/alo/model/mfm_dvjbeam00.nud': b'm0', 'dvj/alo/model/mfm_dvjbeam01.nud': b'm1'})

    def test_named(self):
        self.assertEqual(fx.models_of(BEAM), ['mfm_dvjbeam00.nud', 'mfm_dvjbeam01.nud'])
        self.assertEqual(fx.textures_of(BEAM), ['tfm_dvj00.nut'])
        self.assertEqual(fx.models_of(b'no end'), [])

    def test_copied_with_models(self):
        files, names, _ = fx.copy_files(self.archives, 'lar', [], {100: [('dvj/alo/eff_koyuu_beam00.alo', None)]},
                                        models=True)
        self.assertEqual(names, {100: [('eff_koyuu_beam00', None)]})
        self.assertEqual(files, {'alo/eff_koyuu_beam00.alo': BEAM, 'alo/texture/tfm_dvj00.nut': b't',
                                 'alo/model/mfm_dvjbeam00.nud': b'm0', 'alo/model/mfm_dvjbeam01.nud': b'm1'})
        kept = fx.still_named(files, {'eff_koyuu_beam00'})
        self.assertEqual(kept, files)
        self.assertEqual(fx.still_named(files, {'eff_other'}), {})

    def test_without_models_as_before(self):
        files, _, _ = fx.copy_files(self.archives, 'lar', [], {100: [('dvj/alo/eff_koyuu_beam00.alo', None)]})
        self.assertEqual(sorted(files), ['alo/eff_koyuu_beam00.alo', 'alo/texture/tfm_dvj00.nut'])


class ImporterBeam(unittest.TestCase):
    """The importer copies TEKKEN8['beam_look']'s laser effect (with its meshes) as effect 100 and names it."""

    def run_step(self, look):
        d = definition('reina')
        t8 = dict(d.TEKKEN8, beam_look=look) if look else dict(d.TEKKEN8)
        with mock.patch.object(d, 'TEKKEN8', t8):
            return electric.ImporterEffect.run_step(self, [])

    def test_beam_look(self):
        out, body_only, copy_files, lines = self.run_step('dvj')
        self.assertEqual(copy_files.call_args[0][1:], ('jun', [], {moveset.BEAM_EFFECT: [
            ('dvj/alo/eff_koyuu_beam00.alo', None)]}))
        self.assertTrue(copy_files.call_args[1]['models'])
        self.assertIn(moveset.ELECTRIC_EFFECT, body_only.call_args[0][1])    # (the mock's names, passed on)
        self.assertTrue(any('beams drawn with dvj/alo/eff_koyuu_beam00.alo' in line for line in lines))

    def test_none(self):
        out, body_only, copy_files, _ = self.run_step(None)
        copy_files.assert_not_called()
        self.assertEqual(body_only.call_args[0], (b'<jun/>', None))

    def test_tinted(self):
        with mock.patch.object(electric.importer.fx, 'tinted', side_effect=lambda files, tint: files) as tinted:
            out, _, copy_files, lines = self.run_step(('dvj', (0.5, 0.2, 1.0)))
        self.assertEqual(copy_files.call_args[0][3], {moveset.BEAM_EFFECT: [('dvj/alo/eff_koyuu_beam00.alo', None)]})
        self.assertEqual(tinted.call_args[0][1], (0.5, 0.2, 1.0))
        self.assertTrue(any('tinted (0.5, 0.2, 1.0)' in line for line in lines))


class Tint(unittest.TestCase):
    def test_colour_tracks(self):
        doc = alo.new()
        doc['emitters'] = [alo.new_emitter(), alo.new_emitter()]
        doc['emitters'][1]['spawner']['tracks'][alo.COLOUR_TRACK]['keys'] = [[0, 0.8, 0.25, 0.25], [30, 1, 1, 1]]
        files = fx.tinted({'alo/eff_koyuu_beam00.alo': alo.write(doc), 'alo/model/mfm_dvjbeam00.nud': b'm'},
                          (0.5, 0.25, 1.0))
        keys = [[k[1:] for k in e['spawner']['tracks'][alo.COLOUR_TRACK]['keys']]
                for e in alo.read(files['alo/eff_koyuu_beam00.alo'])['emitters']]
        self.assertEqual(keys, [[[0.5, 0.25, 1.0]], [[0.5, 0.25, 1.0], [0.5, 0.25, 1.0]]])
        self.assertEqual(files['alo/model/mfm_dvjbeam00.nud'], b'm')


if __name__ == '__main__':
    unittest.main()
