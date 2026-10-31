"""The fighter's source (source.py) and what the importer does with a Tekken 8 fighter, on stand-ins: which game a
definition is read from, Reina's definition, the sources opened per game (shared/ with fighters of both games), Tekken
8 found through a made-up Steam library, the donor's moveset standing in for hers (its header retargeted as
moveset.Converter.write retargets it), the Tekken 8 model steps (decimated with the part weights, re-posed to the
donor's skeleton), import_character.py and launcher.py with a Tekken 8 fighter. No game files needed.

    python3 -m unittest discover tools/characters/tests
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, HERE)

import launcher                                       # noqa: E402
from ttt2char import InputError, importer, pack, source   # noqa: E402
from ttt2char.characters import CHARACTERS, definition, game_of   # noqa: E402
from ttt2char.convert import art, decimate, model, skeleton, skin   # noqa: E402
from ttt2char.movesets import TABLE_ORDER             # noqa: E402
from ttt2char.tekken7 import autodump                 # noqa: E402
from ttt2char.tekken8 import autodump as dump8        # noqa: E402
from ttt2char.ttt2 import motbin                      # noqa: E402

spec = importlib.util.spec_from_file_location('import_character', os.path.join(HERE, 'import_character.py'))
import_character = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_character)

TTT2_CODES = set(art.NAME_TEXTS) | {'dek', 'pra', 'zka', 'zkb'}     # the title's own fighters' codes (and its dummies)


def write(path, text=''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


class Definitions(unittest.TestCase):
    def test_which_game(self):
        self.assertEqual(game_of(definition('reina')), 'tekken8')
        self.assertEqual(game_of(definition('kazumi')), 'tekken7')
        self.assertEqual(game_of(mock.Mock(CODE='kzm')), 'tekken7')     # (a stand-in has every name: not a code)

    def test_reina(self):
        d = definition('reina')
        self.assertEqual((d.NAME, d.SHORT_NAME, d.TEKKEN8_CODE, d.TEKKEN8_ID, d.SEX), ('Reina', 'REINA', 'zbr', 28,
                                                                                         'female'))
        self.assertEqual((d.DONOR, d.DONOR_ROW, d.MOVESET_SOURCE, d.STAND_IN), ('jun', 42, 'tekken8', ('hei', 13)))
        self.assertFalse(importer.stand_in(d))
        self.assertTrue(importer.converts_tekken8(d))
        self.assertTrue(importer.stand_in(importer.with_stand_in(d)))
        self.assertFalse(importer.stand_in(definition('kazumi')))
        self.assertFalse(importer.converts_tekken8(definition('kazumi')))
        self.assertEqual(set(d.MESHES), {'bdf', 'fac', 'har'})
        self.assertEqual(d.MESHES['fac'][1], 'ATAMA_Joint')
        self.assertEqual(d.TEKKEN8['costume'], '1p')
        for kind in ('bust', 'body'):
            path, face = d.ART[kind]
            self.assertTrue(path.startswith('/Game/UI/'))
            self.assertEqual(len(face), 3)
        self.assertEqual(d.MOVESET['name'], '[REINA]')
        self.assertEqual(set(d.TEMPLATES), set(definition('kazumi').TEMPLATES))      # (Jun's, as for every woman)

    def test_every_code_is_free(self):
        codes = [definition(name).CODE for name in CHARACTERS]
        self.assertEqual(len(codes), len(set(codes)))
        for code in codes:
            self.assertRegex(code, '^[a-z]{3}$')
            self.assertNotIn(code, TTT2_CODES)

    def test_definitions_import_nothing(self):
        for name in CHARACTERS:
            path = os.path.join(HERE, 'ttt2char', 'characters', name + '.py')
            with open(path) as f:
                tree = ast.parse(f.read())
            self.assertFalse([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))], name)


class Sources(unittest.TestCase):
    def test_paks_become_a_tekken7_source(self):
        paks = object()
        s = source.of(paks)
        self.assertIsInstance(s, source.Tekken7Source)
        self.assertIs(s.paks, paks)
        self.assertIs(source.of(s), s)
        t8 = source.Tekken8Source(object())
        self.assertIs(source.of(t8), t8)

    def test_one_source_per_game(self):
        reina, kazumi, chloe = definition('reina'), definition('kazumi'), definition('chloe')
        opened = []
        with mock.patch.object(source, 'source_of', side_effect=lambda d, t7, t8, files: opened.append(
                (game_of(d), t7, t8)) or mock.Mock(game=game_of(d))):
            s = source.Sources('t7', 't8')
            self.assertIs(s(kazumi), s(chloe))
            self.assertIsNot(s(reina), s(kazumi))
        self.assertEqual(opened, [('tekken7', 't7', 't8'), ('tekken8', 't7', 't8')])
        self.assertEqual(s.games(), ['tekken7', 'tekken8'])

    def test_the_import_s_own_source_is_used(self):
        mine = mock.Mock(game='tekken8')
        with mock.patch.object(source, 'source_of', side_effect=AssertionError('opened again')):
            self.assertIs(source.Sources(None, None, opened=[mine])(definition('reina')), mine)

    def test_a_tekken7_fighter_needs_tekken7(self):
        with self.assertRaises(InputError) as caught:
            source.Sources(None, 't8')(definition('kazumi'))
        self.assertIn('give --tekken7', str(caught.exception))
        self.assertIn('Kazumi', str(caught.exception))
        with self.assertRaises(InputError):
            source.source_of(definition('chloe'))

    def test_a_tekken8_fighter_opens_tekken8(self):
        with mock.patch.object(source, 'open_tekken8', return_value='store') as opened:
            self.assertEqual(source.source_of(definition('reina'), None, '/games/TEKKEN 8'), 'store')
        opened.assert_called_once_with('/games/TEKKEN 8')

    def test_tekken8_through_steam(self):
        with tempfile.TemporaryDirectory() as d:
            library = os.path.join(d, 'library')
            with mock.patch.object(source, 'steam_libraries', return_value=[os.path.join(d, 'other'), library]):
                self.assertIsNone(source.find_tekken8())
                write(os.path.join(library, 'steamapps', 'appmanifest_%d.acf' % source.TEKKEN8_APP_ID),
                      '"AppState"\n{\n "installdir"  "TEKKEN 8"\n}\n')
                self.assertIsNone(source.find_tekken8())                 # (listed, its folder gone)
                game = os.path.join(library, 'steamapps', 'common', 'TEKKEN 8')
                os.makedirs(game)
                self.assertEqual(source.find_tekken8(), game)

    def test_no_tekken8(self):
        with mock.patch.object(source, 'find_tekken8', return_value=None):
            with self.assertRaises(InputError) as caught:
                source.tekken8_folder(None)
        self.assertIn('--tekken8', str(caught.exception))

    def test_material_paths(self):
        s = source.Tekken8Source(mock.Mock())
        meshes = {'a': [{'material': '/Game/x/MI_CH_zbr_face_skin.MI_CH_zbr_face_skin'}, {'material': None}],
                  'b': [{'material': '/Game/y/MI_CH_zbr_face_skin.MI_CH_zbr_face_skin'},
                        {'material': '/Game/y/MI_CH_zbr_har_1p'}]}
        with mock.patch.object(s, 'mesh', side_effect=lambda path: types.SimpleNamespace(materials=meshes[path])):
            self.assertEqual(s.material_paths([('fac', 'a'), ('har', 'b')]),
                             {'MI_CH_zbr_face_skin': '/Game/x/MI_CH_zbr_face_skin.MI_CH_zbr_face_skin',
                              'MI_CH_zbr_har_1p': '/Game/y/MI_CH_zbr_har_1p'})

    def test_skin_faces_of_her_sex(self):
        store = mock.Mock()
        store.exists.side_effect = lambda path: 'gone' not in path
        faces = [('jun', '/Game/jun'), ('hei', '/Game/hei'), ('nin', '/Game/gone'), ('ask', '/Game/ask')]
        with mock.patch('ttt2char.tekken8.skin.reference_faces', return_value=faces):
            s = source.Tekken8Source(store)
            self.assertEqual(s.skin_faces('female'), [('jun', '/Game/jun'), ('ask', '/Game/ask')])
            self.assertEqual(s.skin_faces('male'), [('hei', '/Game/hei')])

    def test_skin_gain_asks_the_source(self):
        src = mock.Mock(NO_COLOURS=None)
        src.skin_faces.return_value = [('jun', '/Game/jun')]
        materials = mock.Mock()
        materials.effective.side_effect = KeyError('none')
        skin.gain(src, None, 'female', materials, None)
        src.skin_faces.assert_called_once_with('female')
        materials.effective.assert_called_once_with('/Game/jun', None)


def donor_moveset():
    """A small TTT2 moveset: its name '[HEIHACHI]' and creator, aliases, no table rows, one embedded MOTA."""
    hdr = bytearray(motbin.BASE)
    hdr[4:8] = b'COM\0'
    strings = b'[HEIHACHI]\0MAX\0'
    struct.pack_into('>4I', hdr, 8, 0, 11, 11, 11)
    struct.pack_into('>56H', hdr, 0x18, *range(100, 156))
    struct.pack_into('>56H', hdr, 0x88, *range(200, 256))
    struct.pack_into('>4H', hdr, 0xF8 + 64, 12, -12 & 0xFFFF, 13, -13 & 0xFFFF)
    return motbin.build(hdr, strings, {t: [] for t in TABLE_ORDER}, b'MOTA' + bytes(28), [0] + [None] * 12)


class StandInMoveset(unittest.TestCase):
    def test_retargeted_to_her_row(self):
        donor = donor_moveset()
        made = importer.stand_in_moveset(donor, 58, '[REINA]')
        m, h = motbin.read(made), motbin.read(donor)
        self.assertEqual(struct.unpack_from('>4H', made, 0xF8 + 64), (57, -57 & 0xFFFF, 58, -58 & 0xFFFF))
        self.assertEqual(made[0x18:0xF8], donor[0x18:0xF8])                 # (both alias lists: the donor's)
        self.assertEqual(made[0xF8:0xF8 + 64], donor[0xF8:0xF8 + 64])
        name = m.name_offsets[0]
        self.assertEqual(m.namebuf[name:m.namebuf.index(b'\0', name)], b'[REINA]')
        self.assertEqual(m.name_offsets[1:], h.name_offsets[1:])
        self.assertEqual(m.namebuf[:15], h.namebuf[:15])                     # (the donor's strings stay where they are)
        self.assertEqual(m.tables, h.tables)
        self.assertEqual(motbin.split(m)[2], motbin.split(h)[2])            # (its motions)
        self.assertEqual(importer.MOVESET_HEADER_ID, 0xF8 + 32 * 2)


class RunStandIn(unittest.TestCase):
    """importer.run for Reina on stand-ins, her Tekken 8 moveset not saved: her STAND_IN's moveset (data006 row 13,
    retargeted) and motions (data005 row 13) in the pack, no command list, its item database, a warning; shared/ gets
    her source and Tekken 7's folders."""

    @contextlib.contextmanager
    def reina(self, **run):
        """importer.run('reina', ..., **run) on the stand-ins below -> (target, lines, opened, build, made, src, motion),
        while its output folder lasts."""
        motion = b'MOTION PACK'
        archives = mock.Mock()
        archives.has.return_value = True
        archives.read_name.side_effect = lambda name: {'hei.xml': b'<hei/>', 'hei.bon': b'bon'}[name]
        archives.entry.side_effect = lambda what, row: {('data006', 13): donor_moveset(),
                                                         ('data005', 13): motion}[(what, row)]
        src = mock.Mock(game='tekken8', NAME='Tekken 8')
        src.clips.return_value = 'clips'
        banks = {'se_Chr_rei.nus3bank': b'chr', 'se_Dwi_rei.nus3bank': b'dwi', 'rm_Dst_rei.nus3bank': b'dst',
                 'rm_Dwi_rei.nus3bank': b'rdwi'}
        made = []
        patches = [mock.patch.object(importer, 'tekken8_folder', return_value='/games/TEKKEN 8'),
                   mock.patch.object(importer, 'ttt2_folder', return_value='/games/ttt2'),
                   mock.patch.object(importer, '_archives', return_value=archives),
                   mock.patch.object(importer, '_rpx', return_value='rpx'),
                   mock.patch.object(importer, 'find_movesets', side_effect=AssertionError('no Tekken 7 movesets')),
                   mock.patch.object(importer, 'tekken8_moveset', return_value=(None, 'not saved')),
                   mock.patch.object(importer.model, 'convert', return_value=(b'nud', b'nut', b'bon', None, None)),
                   mock.patch.object(importer.fx, 'copy_files', return_value=({'alo/eff.alo': b'fx'}, None, None)),
                   mock.patch.object(importer.fx, 'still_named', side_effect=lambda files, names: files),
                   mock.patch.object(importer.itemdb, 'effect_names', return_value=[]),
                   mock.patch.object(importer.itemdb, 'effect_files_named', return_value=[]),
                   mock.patch.object(importer.itemdb, 'body_only', side_effect=lambda xml: xml + b' body'),
                   mock.patch.object(importer, 'spring_file', return_value=None),
                   mock.patch.object(importer.art, 'pack_files', return_value={'art/x.nut': b'art'}),
                   mock.patch.object(importer.voice, 'voice_list', return_value='vlist'),
                   mock.patch.object(importer.voice, 'merge', return_value=(b'merged', 39)),
                   mock.patch.object(importer.bone, 'read', return_value={}),
                   mock.patch.object(importer.face, 'retarget', side_effect=lambda moves, motions, *rest: (
                       moves, motions, 0, {})),
                   mock.patch.object(importer.weapons, 'of_skeleton', return_value=()),
                   mock.patch.object(importer, '_shared', side_effect=lambda s, *rest: made.append(s))]
        with tempfile.TemporaryDirectory() as out, contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            opened = stack.enter_context(mock.patch.object(source, 'open_tekken8', return_value=src))
            build = stack.enter_context(mock.patch.object(importer.voice, 'build',
                                                          return_value=(dict(banks), [], {}, (), ())))
            lines = []
            target = importer.run('reina', None, None, 'g', out, log=lines.append, files='/saved', tekken8='t8', **run)
            yield target, lines, opened, build, made, src, motion

    def test_run(self):
        with self.reina() as (target, lines, opened, build, made, src, motion):
            files = set(os.listdir(target))
            with open(os.path.join(target, 'rei.moveset'), 'rb') as f:
                moves = f.read()
            with open(os.path.join(target, 'rei.motion'), 'rb') as f:
                self.assertEqual(f.read(), motion)
            with open(os.path.join(target, 'rei.xml'), 'rb') as f:
                self.assertEqual(f.read(), b'<hei/> body')
            ini = pack.read_ini(os.path.join(target, 'character.ini'))
        opened.assert_called_once_with('/games/TEKKEN 8')
        self.assertIs(build.call_args[0][0], 'clips')
        src.clips.assert_called_once()
        self.assertNotIn('rei.mvl', files)
        self.assertLessEqual({'rei.nud', 'rei.nut', 'rei.bon', 'se_Chr_rei.nus3bank', 'rm_Dst_rei.nus3bank',
                              'alo', 'art'}, files)
        self.assertEqual((ini['donor'], ini['code'], ini['slot']), ('hei', 'rei', '0'))
        self.assertEqual(ini['stand_in'], 'hei')                    # (the launcher offers an update for her own)
        self.assertTrue(any(line.startswith('WARNING: Reina\'s own moveset cannot be had: not saved') for line in lines))
        row = pack.place(0)['row']
        self.assertEqual(struct.unpack_from('>4H', moves, 0xF8 + 64),
                         (row - 1, -(row - 1) & 0xFFFF, row, -row & 0xFFFF))
        sources, = made                                # (her source as it is; Tekken 7's saved files for its fighters)
        self.assertIs(sources(definition('reina')), src)
        self.assertEqual(sources.files, '/saved')

    def test_outfits_only_when_asked(self):
        """run(outfits=): a definition's preset outfits made into the pack, or left out. (The parameter once had the
        name of the module that makes them, which it hid: every import with outfits failed.)"""
        own = definition('reina')
        with_presets = types.ModuleType(own.__name__)
        with_presets.__dict__.update(vars(own))
        with_presets.PRESETS = (('DefaultCos1P', 'Default'), ('cos2', 'Second'))
        for asked in (True, False):
            with mock.patch.object(importer, 'definition', return_value=with_presets), \
                    mock.patch.object(importer.outfits, 'build',
                                      return_value={'raa.nud': b'outfit', 'rab.nud': b'outfit'}) as made, \
                    mock.patch.object(importer.outfits, 'codes', return_value=['raa', 'rab']), \
                    self.reina(outfits=asked) as (target, *_):
                ini = pack.read_ini(os.path.join(target, 'character.ini'))
                files = set(os.listdir(target))
            self.assertEqual(made.called, asked)
            self.assertEqual(ini.get('outfits'), 'raa rab' if asked else None)
            self.assertEqual('raa.nud' in files, asked)


class RunOwnVoice(unittest.TestCase):
    """importer.run for Reina with her Tekken 8 moveset saved: the lines her moves say join her clips before the
    banks are built (add_lines), and the TTT2 voice of each of her moves' voices (move_voices on voice_values of
    those clips and the donor's voice list) reaches the moveset's conversion."""

    def test_run(self):
        archives = mock.Mock()
        archives.has.return_value = True
        archives.read_name.side_effect = lambda name: {'jun.xml': b'<jun/>', 'jun.bon': b'bon'}[name]
        k = mock.Mock(name='her moveset')
        src = mock.Mock(game='tekken8', NAME='Tekken 8')
        clips = src.clips.return_value
        order = []
        clips.add_lines.side_effect = lambda m: order.append('lines')
        banks = {'se_Chr_rei.nus3bank': b'chr', 'se_Dwi_rei.nus3bank': b'dwi', 'rm_Dst_rei.nus3bank': b'dst',
                 'rm_Dwi_rei.nus3bank': b'rdwi'}
        patches = [mock.patch.object(importer, 'tekken8_folder', return_value='/games/TEKKEN 8'),
                   mock.patch.object(importer, 'ttt2_folder', return_value='/games/ttt2'),
                   mock.patch.object(importer, '_archives', return_value=archives),
                   mock.patch.object(importer, '_rpx', return_value='rpx'),
                   mock.patch.object(importer, 'tekken8_moveset', return_value=((k, {}, []), None)),
                   mock.patch.object(importer.model, 'convert', return_value=(b'nud', b'nut', b'bon', None, None)),
                   mock.patch.object(importer.fx, 'copy_files', return_value=({}, None, None)),
                   mock.patch.object(importer.itemdb, 'effect_names', return_value=[]),
                   mock.patch.object(importer, 'spring_file', return_value=None),
                   mock.patch.object(importer.art, 'pack_files', return_value={}),
                   mock.patch.object(importer.voice, 'voice_list', return_value='vlist'),
                   mock.patch.object(importer.voice, 'merge', return_value=(b'merged', 39)),
                   mock.patch.object(importer.bone, 'read', return_value={}),
                   mock.patch.object(importer.face, 'retarget', side_effect=lambda moves, motions, *rest: (
                       moves, motions, 0, {})),
                   mock.patch.object(importer.weapons, 'of_skeleton', return_value=()),
                   mock.patch.object(importer, '_shared')]
        with tempfile.TemporaryDirectory() as out, contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(mock.patch.object(source, 'open_tekken8', return_value=src))
            stack.enter_context(mock.patch.object(importer.voice, 'build', side_effect=lambda *a: (
                order.append('banks'), (dict(banks), [], {}, (), ()))[1]))
            values = stack.enter_context(mock.patch.object(importer.voice, 'voice_values', return_value='values'))
            convert = stack.enter_context(mock.patch.object(
                importer, '_converted_tekken8_moveset', return_value=(b'moves', b'motions', b'<jun/> body', {}, None)))
            importer.run('reina', None, None, 'g', out, log=lambda s: None, tekken8='t8')
        clips.add_lines.assert_called_once_with(k)
        self.assertEqual(order, ['lines', 'banks'])
        self.assertEqual(values.call_args, mock.call(clips, 'vlist'))
        clips.move_voices.assert_called_once_with('values')
        self.assertIs(convert.call_args[0][-1], clips.move_voices.return_value)


def small_model(parts):
    """A model dict (load_tekken7_model's shape) with one triangle per part."""
    n = 3 * len(parts)
    s0 = {'pos': np.zeros((n, 3), np.float32)}
    prims = [dict(s0, tris=np.array([[3 * i, 3 * i + 1, 3 * i + 2]]), part=tag, material='MI_%s' % tag)
             for i, (tag, _) in enumerate(parts)]
    return {'bones': {'names': ['BASE'], 'parents': [-1], 'world': np.eye(4)[None]}, 'prims': prims, 'parts': {}}


class Tekken8Model(unittest.TestCase):
    def test_steps(self):
        parts = [('fac', 'f'), ('har', 'h'), ('bdf', 'b')]
        loaded, decimated, reposed = small_model(parts), small_model(parts), small_model(parts)
        src = mock.Mock(game='tekken8')
        src.costume.side_effect = lambda d, which: {'parts': parts, 'merge_order': ['fac', 'bdf', 'har'],
                                                    'colours': 'colours ' + which}
        src.load_model.return_value = loaded
        d = types.SimpleNamespace(TEKKEN8={'costume': '1p', 'costume_2p': '2p'})
        donor = {'names': ['hei']}
        with mock.patch.object(decimate, 'vertex_target', return_value=1234) as target, \
                mock.patch.object(decimate, 'decimate', return_value=decimated) as reduce, \
                mock.patch.object(skeleton, 'repose', return_value=reposed) as repose:
            k, worn, colours, colours_2p = model.tekken8_model(src, d, donor, log=lambda s: None)
        self.assertIs(k, reposed)
        self.assertEqual((worn, colours, colours_2p), (parts, 'colours 1p', 'colours 2p'))
        src.load_model.assert_called_once()
        self.assertEqual(src.load_model.call_args[0][:2], (parts, ['fac', 'bdf', 'har']))
        self.assertIs(target.call_args[0][0], loaded)
        self.assertEqual(target.call_args[1]['budget'], model.VERTEX_BUDGET)
        self.assertEqual(reduce.call_args[0][:3], (loaded, 1234, {'fac': 0.3, 'har': 0.7, 'bdf': 1.0}))
        self.assertEqual(repose.call_args[0][:2], (decimated, donor))

    def test_explicit_parts_and_weights(self):
        parts = [('fac', 'f'), ('bdu', 'u')]
        src = mock.Mock(game='tekken8')
        src.costume.return_value = {'parts': [], 'merge_order': [], 'colours': 'c'}
        src.load_model.return_value = small_model(parts)
        d = types.SimpleNamespace(TEKKEN8={'parts': parts, 'costume': '1p', 'part_weights': {'bdu': 0.5}})
        with mock.patch.object(decimate, 'decimate', side_effect=lambda k, t, w, log: k) as reduce, \
                mock.patch.object(skeleton, 'repose', side_effect=lambda k, donor, log: k):
            _, worn, colours, colours_2p = model.tekken8_model(src, d, {}, log=lambda s: None)
        self.assertEqual((worn, colours, colours_2p), (parts, 'c', None))
        self.assertEqual(src.load_model.call_args[0][1], ['fac', 'bdu'])
        self.assertEqual(reduce.call_args[0][2], {'fac': 0.3, 'bdu': 0.5})


class ImportTekken8(unittest.TestCase):
    """import_character.py reina --tekken8 DIR: Tekken 7 is never asked for (unless a Tekken 7 pack is installed and
    what the packs share is made again)."""

    def add(self, folder, fighters, tekken7=None, steam_tekken7=None, tekken8='/games/TEKKEN 8'):
        runs, shared = [], []
        args = mock.Mock(tekken7=tekken7, tekken8=tekken8, movesets=os.path.join(folder, '.m'),
                         files=os.path.join(folder, '.f'), game='g', out=folder, no_shared=False,
                         tekken8_movesets=None, outfits=set())

        def run(name, t7, movesets, game, out, make_shared=True, files=None, tekken8=None, outfits=True):
            runs.append((name, t7, tekken8, make_shared))
            return pack.write(folder, definition(name), {'.nud': b'nud'}, 0)

        def tekken8_folder(f):                       # (as store.game_folder: once is enough; none: not in Steam)
            if not f:
                raise InputError('Tekken 8 is not installed in any Steam library')
            return f if f.endswith('/checked') else f + '/checked'

        library = mock.Mock(side_effect=autodump.DumpError('no Steam')) if steam_tekken7 is None else \
            mock.Mock(return_value=(None, None, steam_tekken7))
        with mock.patch.object(import_character, 'needs_packages'), \
                mock.patch.object(autodump, 'dump', side_effect=AssertionError('Tekken 7 would run')), \
                mock.patch.object(autodump, 'tekken7_library', library), \
                mock.patch.object(importer, 'tekken7_paks'), \
                mock.patch.object(importer, 'tekken8_folder', side_effect=tekken8_folder), \
                mock.patch.object(import_character, 'tekken7_ready',      # (owned, movesets saved: test_packs's)
                                  side_effect=lambda fighters, *rest, **kw: fighters), \
                mock.patch.object(import_character, 'tekken8_ready'), \
                mock.patch.object(importer, 'run', side_effect=run), \
                mock.patch.object(importer, 'make_shared', side_effect=lambda t7, game, out, files=None, tekken8=None:
                                  shared.append((t7, tekken8))), \
                contextlib.redirect_stdout(io.StringIO()):
            import_character.add(args, list(fighters), import_character.Progress(False))
        return runs, shared

    def test_reina_alone(self):
        with tempfile.TemporaryDirectory() as d:
            runs, shared = self.add(d, ['reina'])
        self.assertEqual(runs, [('reina', None, '/games/TEKKEN 8/checked', False)])
        self.assertEqual(shared, [(None, '/games/TEKKEN 8/checked')])

    def test_a_tekken7_pack_installed_needs_tekken7_for_shared(self):
        with tempfile.TemporaryDirectory() as d:
            pack.write(d, definition('kazumi'), {'.nud': b'nud'}, 1)
            with self.assertRaises(SystemExit) as caught:
                self.add(d, ['reina'])
            self.assertIn('give --tekken7', str(caught.exception.code))
            self.assertIn('the Tekken 7 fighters added (Kazumi Mishima) need it', str(caught.exception.code))
            self.assertEqual(os.listdir(d), ['kzm'])                    # (nothing was changed: no pack of hers)
            runs, shared = self.add(d, ['reina'], steam_tekken7='/games/TEKKEN 7')     # (found through Steam)
        self.assertEqual(shared, [('/games/TEKKEN 7', '/games/TEKKEN 8/checked')])

    def test_a_tekken8_pack_installed_needs_tekken8_for_shared(self):
        with tempfile.TemporaryDirectory() as d:
            pack.write(d, definition('reina'), {'.nud': b'nud'}, 0)
            with mock.patch.object(source, 'find_tekken8', return_value=None), \
                    self.assertRaises(SystemExit) as caught:
                self.add(d, ['kazumi'], tekken7='/games/TEKKEN 7', tekken8=None)
            self.assertIn('Tekken 8 is not installed in any Steam library, and the Tekken 8 fighters added (Reina) '
                          'need it', str(caught.exception.code))
            self.assertEqual(os.listdir(d), ['rei'])                    # (nothing was changed: no pack of hers)

    def test_no_tekken8_skips_her_beside_tekken7_fighters(self):
        with tempfile.TemporaryDirectory() as d:
            runs, shared = self.add(d, ['kazumi', 'reina'], tekken7='/games/TEKKEN 7', tekken8=None)
            self.assertEqual([r[0] for r in runs], ['kazumi'])
            self.assertEqual(shared, [('/games/TEKKEN 7', None)])
            with self.assertRaises(SystemExit) as caught:                    # (alone: no Tekken 8 is an error)
                self.add(d, ['reina'], tekken8=None)
            self.assertIn('not installed', str(caught.exception.code))

    def test_character_ini(self):
        text = pack.character_ini(definition('reina'), 4)
        self.assertTrue(text.startswith('# Reina, from Tekken 8 '))
        self.assertIn('code = rei\ndonor = jun\nsex = female\nslot = 4\n', text)
        self.assertIn('from Tekken 7 ', pack.character_ini(definition('kazumi'), 4))


class Launcher(unittest.TestCase):
    def test_status_lists_reina(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, HOME=d, TTT2_CHARACTERS=os.path.join(d, 'packs')), \
                mock.patch.object(source, 'find_tekken8', return_value=None):
            s = launcher.status(None, os.path.join(d, 'movesets'), os.path.join(d, 'movesets8'))
            json.dumps(s)
        fighters = {f['name']: f for f in s['fighters']}
        self.assertEqual(fighters['reina'], {'name': 'reina', 'display': 'Reina', 'dlc': None, 'installed': False,
                                             'outdated': False, 'newer': False, 'update': False,
                                             'moveset_saved': False, 'outfits': 0, 'outfits_added': False,
                                             'stand_in': False, 'game': 'tekken8'})
        self.assertNotIn('game', fighters['kazumi'])
        self.assertEqual(s['tekken8'], {'found': False, 'path': None,
                                        'error': 'Tekken 8 is not installed in any Steam library',
                                        'run_error': None, 'build_known': None})

    def test_tekken8_found(self):
        with tempfile.TemporaryDirectory() as d:
            ran = mock.Mock(side_effect=dump8.DumpError('Tekken 8 has not run with Proton yet'))
            with mock.patch.object(source, 'find_tekken8', return_value=d), \
                    mock.patch.object(dump8, 'find_tekken8', ran):
                self.assertFalse(launcher.tekken8()['found'])
                os.makedirs(os.path.join(d, 'Polaris', 'Content', 'Paks'))
                self.assertEqual(launcher.tekken8(), {'found': True, 'path': d, 'error': None,
                                                      'run_error': 'Tekken 8 has not run with Proton yet'})
                ran.side_effect = None
                self.assertIsNone(launcher.tekken8()['run_error'])

    def test_owned_asks_for_tekken7_dlc_only(self):
        with mock.patch.object(autodump, 'unowned', return_value={}) as unowned:
            launcher.owned()
        self.assertTrue(all(isinstance(app, int) for app in unowned.call_args[0][0]))


if __name__ == '__main__':
    unittest.main()
