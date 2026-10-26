"""A Tekken 8 fighter's own moveset in the import, on made-up data (no game files needed): the id maps' references
(other Tekken 8 fighters: their partners in TTT2, their evidence filling the fighter's own gaps, their unnamed moves
left out), naming a reference from known names, the older shared clips TTT2 has the originals of, the animation
provider called as the converter calls it, the fighter's own lower-case moves, voice audio stored once, the intro and
win moves of the voice events, the stand-in definition, the saved files the importer finds, the conversion step's
wiring and import_character.py's saving of Tekken 8 movesets.

    python3 -m pytest -q tools/characters/tests/test_tekken8_import_moveset.py
"""
import collections
import contextlib
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

import test_tekken8_motbin_names as N  # noqa: E402
from test_movement import moveset_of  # noqa: E402
from test_tagsystem import Tables  # noqa: E402
from test_tekken8_anim import bank, clip, sample  # noqa: E402
from test_tekken8_convert import Source8  # noqa: E402
from ttt2char import importer  # noqa: E402
from ttt2char.characters import definition  # noqa: E402
from ttt2char.convert import idmaps as M, moveset, voice  # noqa: E402
from ttt2char.tekken8 import anim, anmbin, autodump as dump8, movenames, panm, voice as voice8  # noqa: E402
from ttt2char.ttt2 import animation, motion, nus3bank  # noqa: E402

import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location('import_character', os.path.join(HERE, '..', 'import_character.py'))
import_character = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_character)


# ------------------------------------------------------------------------------------------------ made-up movesets
def t8_fighter(code, moves, prefix=None):
    """A Tekken 8 moveset (Source8) of moves [(name, requirement of its one cancel row, hit location)]: each move's
    one cancel goes to the first move."""
    k = Source8({i: n for i, (n, _, _) in enumerate(moves) if n}, [(i, 'own') for i in range(len(moves))])
    k.code, k.own_prefix = code, prefix
    t = k.tables
    for i, (_, req, hit) in enumerate(moves):
        t['cancels'] += [dict(direction=0, button=1, req=k.req((req, 0)), move_id=0),
                         dict(direction=M.LIST_END, button=0, req=None, move_id=0)]
        t['moves'][i].update(cancel=2 * i, hit_condition=None, extraprops=None, begin_props=None, end_props=None,
                             hitbox=bytes([hit, 0, 0, 0]))
    return k


def ttt2_moveset(moves):
    """A TTT2 moveset of moves [(name, requirement of its one cancel row, hit location)], laid out as t8_fighter's."""
    b = Tables()
    for i, (name, req, hit) in enumerate(moves):
        b.move(name, cancel=b.cancels(dict(button=1, req=b.req((req, 0)), move_id=0), b.end()),
               hitbox=bytes([hit, 0, 0, 0]))
    return moveset_of(b)


GENERIC = [('Co_dwupL', 300, 0), ('Co_dwupR', 310, 0)]


class References(unittest.TestCase):
    """Her own evidence maps 500 -> 300 and 510 -> 310 (generic moves); a reference (Tekken 8 Jun) and TTT2 Jun's
    own moves give 600 -> 400 and 610 -> 410 and their hit locations, and disagree on 500."""

    def setUp(self):
        self.her = t8_fighter('zbr', [('Co_dwupL', 500, 0), ('Co_dwupR', 510, 0), ('Zbr_kk00', 600, 0)], 'Zbr')
        jun = [('Ju_lp00', 600, 12), ('Ju_rp00', 610, 12), ('Ju_lk00', 500, 12)]
        self.ref = t8_fighter('aml', [('Co_dwupL', 500, 0)] + jun)
        self.ttt2 = [ttt2_moveset(GENERIC + [('Ju_lp00', 400, 11), ('Ju_rp00', 410, 11), ('Ju_lk00', 350, 11)])] + \
            [ttt2_moveset(GENERIC + [('X%d_zz%d' % (n, n), 300, 0)]) for n in range(3)]
        for m in self.ttt2:
            m.own_prefix = None

    def lookups(self, maps, ids=(500, 510, 600, 610)):
        return [maps[0].lookup(x)[0] if maps[0].lookup(x)[1] in M.MAPPED else None for x in ids]

    def test_partners(self):
        with mock.patch.object(M, 'PARTNER_MIN', 3):
            self.assertEqual(M.partners(self.ref, self.ttt2), self.ttt2[:1])    # (Co_ names are generic)
            self.assertEqual(M.partners(self.her, self.ttt2), [])

    def test_fill_the_gaps(self):
        alone = M.tekken8_maps([self.her], self.ttt2)
        self.assertEqual(self.lookups(alone), [300, 310, None, None])
        with mock.patch.object(M, 'PARTNER_MIN', 3):
            both = M.tekken8_maps([self.her], self.ttt2, references=[self.ref])
        self.assertEqual(self.lookups(both), [300, 310, 400, 410])          # (500: hers, not the reference's 350)
        self.assertEqual(both[3], {12: 11})                                 # hit locations: the references' too
        self.assertEqual(self.ref.own_prefix, None)                         # (aligned under its partner's prefix)

    def test_unnamed_reactions(self):
        """A reference's unnamed reaction move is another fighter's index: no '#<index>' evidence."""
        for k in (self.her, self.ref):                  # (move 0, Co_dwupL, hit: the unnamed move last)
            t = k.tables
            t['reactions'] = [{f: len(t['moves']) for f in M.REACTION_MOVE_FIELDS}]
            t['hit_conditions'] = [dict(req=k.req((700, 0)), damage=1, reactions=0),
                                   dict(req=k.req(), damage=0, reactions=None)]
            t['moves'][0]['hit_condition'] = 0
            k.refs.append((99, 'own'))
            t['moves'].append(dict(anim=99, cancel=None, hit_condition=None, extraprops=None, begin_props=None,
                                   end_props=None, hitbox=b'\0\0\0\0'))
        b = Tables()
        hit = b.hits((b.req((450, 0)), 1, b.reaction(4)), (b.req(), 0, None))
        b.move('Co_dwupL', hit_condition=hit)
        b.move('Ju_lp00')
        b.move('Ju_rp00')
        b.move('Ju_lk00')
        b.move('Co_DmA')
        self.ttt2[0] = moveset_of(b)
        self.ttt2[0].own_prefix = None
        with mock.patch.object(M, 'PARTNER_MIN', 1):
            ev = M.tekken8_maps([self.her], self.ttt2, references=[self.ref])[4]
        self.assertEqual(ev['react.move'].pairs[('#3', 'Co_DmA')], 1)      # hers
        self.assertNotIn(('#4', 'Co_DmA'), ev['react.move'].pairs)        # (the reference's #4)
        ev = collections.defaultdict(M.Evidence)
        M.align(self.ref, self.ttt2[0], ev, wide=True)                     # (as a fighter converted: it would)
        self.assertEqual(ev['react.move'].pairs[('#4', 'Co_DmA')], 1)

    def test_canonical_with_a_prefix(self):
        self.assertEqual(M.canonical(self.ref, 'Ju')[1], '@lp00')
        self.assertEqual(M.canonical(self.her)[2], '@kk00')


class NameKnown(unittest.TestCase):
    def test_dictionary_only(self):
        m = N.named_fighter()
        n = movenames.name_known(m, movenames.harvest([N.Dictionary(N.DICTIONARY)])[0])
        self.assertEqual((n, m.names), (1, {0: 'Co_Thing00'}))              # (no prefixes, commands, variations)


class OwnMoves(unittest.TestCase):
    def test_lower_case_prefix(self):
        """Her intros and win poses (zbr_s00, zbr_w01) are her own moves."""
        d = Tables()
        d.move('Ju_sKAM00_')
        k = Source8({0: 'zbr_w01', 1: 'Zbr_lp00', 2: 'xzbr_w01'}, [(0, 'own')] * 3)
        self.assertEqual(moveset.classify8(k, moveset_of(d)), ['K', 'K', 'T'])


# ------------------------------------------------------------------------------------------------ animations
def mota(frames):
    """A big-endian MOTA with one raw animation per frame count."""
    empty = b'MOTA\0\1\0\0' + struct.pack('>III', 0x14, 0, 0)
    return motion.extend_mota(empty, [animation.encode_raw([1, 2], np.full((f, 2, 3), f, np.float32))
                                      for f in frames])


def body_clip(frames, legacy=True):
    v = [sample()] * frames
    return clip([('A', v, panm.QUANTISED if legacy else panm.RAW, panm.NO_TRANSLATION if legacy else panm.NEW,
                  'Transform')], frames)


class Originals(unittest.TestCase):
    """Clips 10..15 of the shared bank, her moves' names, TTT2's movesets (row 1 the donor's): an older clip pairs
    with the TTT2 animation of its move's name and frame count (common: its id; the donor's pack: its id; another
    pack: its bytes); a newer clip, other frame counts or an unnamed move do not."""

    def setUp(self):
        shared = [(10, body_clip(5), [28]), (11, body_clip(6), [28]), (12, body_clip(7), [28]),
                  (13, body_clip(5, legacy=False), [28]), (14, body_clip(5), [28]), (15, body_clip(4), [28])]
        self.banks = anmbin.Banks(anmbin.Bank(bank([[] for _ in range(6)])),
                                  anmbin.Bank(bank([shared] + [[] for _ in range(5)])), 28)
        self.k = Source8({0: 'Co_a', 1: 'Co_b', 2: 'Co_c', 3: 'Co_d', 5: 'Co_e'},
                         [(10, 'com'), (11, 'com'), (12, 'com'), (13, 'com'), (14, 'com'), (15, 'com')])
        self.common = mota([3, 5, 8])
        self.packs = {1: motion.build_pack([mota([4])] + [b''] * 5), 2: motion.build_pack([mota([2, 6])] + [b''] * 5)}
        rows = []
        for moves in ([('Co_a', 0x8001), ('Co_c', 0x8002), ('Co_d', 0x8001)], [('Co_e', 0x4000)],
                      [('Co_b', 0x4001)]):
            b = Tables()
            for name, aid in moves:
                b.move(name, anim=aid)
            rows.append(moveset_of(b))
        self.rows = rows

    def test_pairs(self):
        got = anim.originals(self.k, self.banks, self.rows, self.common, self.packs.__getitem__, 1)
        self.assertEqual(set(got), {10, 11, 15})
        self.assertEqual((got[10], got[15]), (0x8001, 0x4000))             # common; the donor's pack
        e, offs = motion.mota_offsets(self.packs[2], motion.pack_items(self.packs[2])[0][0])
        self.assertEqual(animation.decode(got[11])['frames'], 6)            # another pack's, as bytes
        self.assertEqual(got[11], animation.encode_raw([1, 2], np.full((6, 2, 3), 6, np.float32)))

    def test_provider(self):
        converter = mock.Mock()
        converter.animation.return_value = b'CONVERTED'
        p = anim.Animations(self.banks, converter, {10: 0x8001})
        self.assertEqual(p((10, 'com')), 0x8001)                            # (the converter's one tuple)
        self.assertEqual(p(13, 'com'), b'CONVERTED')
        self.assertEqual(p((13, 'com')), b'CONVERTED')                      # converted once
        converter.animation.assert_called_once()
        self.assertIsNone(p((99, None)))
        self.assertEqual(p.stats['body animations TTT2 has (an older shared clip\'s original)'], 1)


# ------------------------------------------------------------------------------------------------ voice
def nus3(tones):
    """A NUS3BANK of tones [(name, audio bytes or None, linked tone indices)] (test_formats' layout)."""
    entries, pack, at = [], b'', 0
    for name, audio, link in tones:
        n = name.encode() + b'\0'
        head = (bytes(4) + b'\x7f' + bytes(3)) if link else (bytes(4) + bytes([0xff, 0xff, 0x27, 0x84]) + b'\x7f' +
                                                             bytes(3))
        t = bytearray(head + bytes([len(n)]) + n)
        while len(t) % 4:
            t.append(0)
        if link:
            t += b'\xff\xff\xff\xff' + struct.pack('<II', len(link), 1) + b''.join(
                struct.pack('<fIIII', 1.0, k, 0, 0, 0) for k in link)
        else:
            t += struct.pack('<IIII', 0, 8, at, len(audio)) + bytes(16) + b'\xff\xff\xff\xff' + struct.pack(
                '<III', 48000, 1, 10) + bytes(8)
            pack += audio
            at += len(audio)
        entries.append(bytes(t))
    table, body = struct.pack('<I', len(entries)), b''
    for t in entries:
        table += struct.pack('<II', 4 + 8 * len(entries) + len(body), len(t))
        body += t
    chunks = [(b'BINF', struct.pack('<II', 0, 3) + bytes([5]) + b'test\0' + bytes(2) + struct.pack('<I', 7)),
              (b'TONE', table + body), (b'PACK', pack)]
    toc = struct.pack('<I', len(chunks)) + b''.join(t + struct.pack('<I', len(d)) for t, d in chunks)
    rest = b'BANKTOC ' + struct.pack('<I', len(toc)) + toc + b''.join(t + struct.pack('<I', len(d)) + d
                                                                     for t, d in chunks)
    return b'NUS3' + struct.pack('<I', len(rest)) + rest


class StoredOnce(unittest.TestCase):
    """Her one win line on a donor's win quote tones (a stereo pair, two more): stored once with Tekken 8's clips,
    once per tone with Tekken 7's (as before)."""

    def bank(self, clips):
        data = nus3([('w_t2_1pR', b'R' * 16, None), ('w_t2_1pL', b'L' * 16, None), ('w_t2_1p', None, [0, 1]),
                     ('w_t2_1p_3', b'3' * 16, None), ('sp_w_t2_1p', b'S' * 16, None)])
        clips.kinds = {('win', None): [('Play_zbr_win_00', 24000, np.arange(480, dtype=np.int16)[None])]}
        written, used, placed, _ = voice._build_one('se_Dwi', data, clips, 'rei', 24000, {})
        b = nus3bank.Bank(written)
        return len(set(b.source[i] for i in (0, 1, 3, 4))), len(b.chunk(b'PACK')), placed

    def test_tekken8_shares(self):
        copies, size, placed = self.bank(voice8.Clips.__new__(voice8.Clips))
        self.assertEqual(copies, 1)
        self.assertEqual(placed, {'Play_zbr_win_00': 2})
        self.assertEqual(self.bank(voice.Clips.__new__(voice.Clips))[:2], (4, 4 * size + 3 * (-size % 16)))

    def test_pose_moves(self):
        self.assertEqual([voice8.pose_move(e) for e in ('Play_zbr_win_01', 'Play_zbr_sta_00', 'Play_ZBR_Attack_S_001')],
                         ['zbr_w01', 'zbr_s00', None])


# ------------------------------------------------------------------------------------------------ the import
class StandIn(unittest.TestCase):
    def test_with_stand_in(self):
        d = definition('reina')
        s = importer.with_stand_in(d)
        self.assertEqual((s.DONOR, s.DONOR_ROW, s.MOVESET_SOURCE), ('hei', 13, 'donor'))
        self.assertEqual((s.CODE, s.NAME, s.TEMPLATES), (d.CODE, d.NAME, d.TEMPLATES))
        self.assertEqual((d.DONOR, d.DONOR_ROW), ('jun', 42))                # (the definition itself unchanged)
        self.assertTrue(importer.stand_in(s) and not importer.converts_tekken8(s))


def saved(folder, fighters, common=True):
    """A saved-movesets folder: {code: motbin_only} with files of a byte, and its manifest."""
    man = {'game': {'build': '1'}, 'fighters': {}, 'common': {'com.anmbin': 1} if common else {}}
    names = ['com.anmbin'] if common else []
    for code, only in fighters.items():
        files = ['%s.motbin' % code, '%s.motbin.fields.bin' % code] + ([] if only else ['%s.anmbin' % code,
                                                                                           '%s.mvl' % code])
        man['fighters'][code] = {'id': 0, 'name': code, 'motbin_only': only, 'files': {n: 1 for n in files}}
        names += files
    for n in names:
        with open(os.path.join(folder, n), 'wb') as f:
            f.write(b'x')
    with open(os.path.join(folder, dump8.MANIFEST), 'w') as f:
        json.dump(man, f)


class SavedFiles(unittest.TestCase):
    def test_her_moveset_and_references(self):
        d = definition('reina')
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(importer.tekken8_moveset(d, folder)[0], None)
            saved(folder, {'zbr': False, 'aml': True, 'grl': True})
            self.assertEqual(dump8.saved_codes(folder), ['aml', 'grl', 'zbr'])
            with mock.patch('ttt2char.tekken8.motbin.read', return_value='her moveset') as read:
                (k, files, refs), why = importer.tekken8_moveset(d, folder)
            self.assertEqual((k, why), ('her moveset', None))
            self.assertEqual(read.call_args[0], (b'x', b'x', 'zbr'))
            self.assertEqual(set(files), {'motbin', 'fields', 'anmbin', 'mvl', 'common'})
            self.assertEqual([r[0] for r in refs], ['aml', 'grl'])
            self.assertTrue(refs[0][1].endswith('aml.motbin') and refs[0][2].endswith('aml.motbin.fields.bin'))
            with mock.patch('ttt2char.tekken8.motbin.read', side_effect=importer.InputError('cut off')):
                k, why = importer.tekken8_moveset(d, folder)
            self.assertIsNone(k)
            self.assertIn('cannot be read (cut off)', why)

    def test_only_her_motbin(self):
        with tempfile.TemporaryDirectory() as folder:
            saved(folder, {'zbr': True})
            self.assertIn('not saved', importer.tekken8_moveset(definition('reina'), folder)[1])


class ConvertStep(unittest.TestCase):
    """_converted_tekken8_moveset's wiring: names, references, maps, banks, the converter's options, the command
    list (a failure of its conversion leaves the donor's)."""

    def test_wiring(self):
        d = definition('reina')
        k, other = mock.Mock(character_id=28), mock.Mock()
        files = {'anmbin': 'own.anmbin', 'common': 'com.anmbin', 'mvl': 'zbr.mvl'}
        archives = mock.Mock()
        archives.entry.side_effect = lambda what, row: (what, row)
        ttt2 = ['row %d' % r for r in range(66)]
        c = mock.Mock(projectile_effects={}, electric_moves=[])
        c.write.return_value = (b'moves', b'motions')
        c.summary.return_value = ['tables: ...']
        lines = []
        with mock.patch('ttt2char.tekken8.movenames.ttt2_movesets', return_value=ttt2), \
                mock.patch('ttt2char.tekken8.movenames.name_moves') as name_moves, \
                mock.patch('ttt2char.tekken8.movenames.harvest', return_value=({b'Co_a'}, set())), \
                mock.patch('ttt2char.tekken8.movenames.name_known') as name_known, \
                mock.patch('ttt2char.tekken8.motbin.read', return_value=other), \
                mock.patch('ttt2char.tekken8.motbin.read_bank', side_effect=lambda p: 'index of ' + p), \
                mock.patch('ttt2char.tekken8.anmbin.Bank') as Bank, \
                mock.patch('ttt2char.tekken8.anim.load_skeleton', return_value='her skeleton'), \
                mock.patch('ttt2char.tekken8.anim.Converter') as AnimConverter, \
                mock.patch('ttt2char.tekken8.anim.originals', return_value={1: 0x8001}), \
                mock.patch('ttt2char.tekken8.movelist.convert', side_effect=ValueError('bad list')), \
                mock.patch.object(importer, '_read', side_effect=lambda p: p.encode()), \
                mock.patch.object(importer.idmaps, 'tekken8_maps', return_value=('req', 'prop', 'rr', 'hb', 'ev')) \
                as maps, \
                mock.patch.object(importer.idmaps, 'ttt2_usage', return_value='usage'), \
                mock.patch.object(importer.tagsystem, 'TagStates', return_value='states'), \
                mock.patch.object(importer.moveset, 'Converter', return_value=c) as Converter, \
                mock.patch.object(importer, '_options') as options, \
                mock.patch.object(importer.bone, 'read', return_value='bon read'), \
                mock.patch.object(importer.itemdb, 'body_only', side_effect=lambda xml, effects=None: xml + b' body'), \
                mock.patch.object(importer.itemdb, 'effect_files_named', return_value=[]), \
                mock.patch.object(importer.fx, 'still_named', side_effect=lambda files, names: files):
            out = importer._converted_tekken8_moveset(
                mock.Mock(store='store'), archives, d, {'row': 70}, (k, files, [('aml', 'aml.motbin', 'aml.f')]),
                b'<jun/>', {'alo/x': b'fx'}, {'Play_zbr_win_01': 2, 'other': 3}, 'vlist', ('extra',), b'bon',
                lines.append, lambda s: None, {(16, 13342): [0x02000028]})
        self.assertEqual(out, (b'moves', b'motions', b'<jun/> body', {'alo/x': b'fx'}, None))
        name_moves.assert_called_once()
        self.assertIs(name_moves.call_args[0][0], k)
        name_known.assert_called_once_with(other, {b'Co_a'})
        self.assertEqual(maps.call_args, mock.call([k], ttt2, references=[other]))
        args = Converter.call_args[0]
        self.assertEqual(args[:5], (k, None, 'row 42', ('data005', 42), 'row 13'))
        self.assertEqual(args[6:9], (('req', 'prop', 'rr', 'hb'), 'usage', 70))
        self.assertIs(args[9], d)
        k.attach_banks.assert_called_once_with('index of own.anmbin', 'index of com.anmbin')
        self.assertEqual(AnimConverter.call_args[0], ('her skeleton', 'bon read'))
        self.assertIsInstance(c.animations, anim.Animations)
        self.assertEqual(c.animations.originals, {1: 0x8001})
        self.assertEqual(options.call_args[0][3], {'zbr_w01': 2, 'other': 3})    # the win quotes by her moves
        self.assertEqual(c.voices8, {(16, 13342): [0x02000028]})     # (her moves' voices, set before the run)
        c.run.assert_called_once()
        self.assertEqual(Bank.return_value.close.call_count, 2)
        self.assertTrue(any('could not be converted (bad list)' in line for line in lines))


class ImportTekken8(unittest.TestCase):
    """import_character.py: her moveset saved first when it is not saved for this version (with every other fighter
    as a reference); nothing runs when it is saved or Tekken 8 cannot run; the folder reaches importer.run."""

    def ready(self, saved_files, dump=None, find=None):
        progress = import_character.Progress(False)
        t8 = types.SimpleNamespace(game='/games/TEKKEN 8', library='/lib')
        with mock.patch.object(dump8, 'find_tekken8', side_effect=find, return_value=t8), \
                mock.patch.object(dump8, 'game_version', return_value='v1'), \
                mock.patch.object(dump8, 'known_build', return_value=True), \
                mock.patch.object(dump8, 'saved_files', side_effect=saved_files) as files, \
                mock.patch.object(dump8, 'dump', side_effect=dump, return_value=({}, {})) as run, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            import_character.tekken8_ready(['reina'], '/saved', progress)
        return files, run, out.getvalue()

    def test_saved_already(self):
        files, run, _ = self.ready(lambda code, folder, version: {'motbin': 'm', 'anmbin': 'a'})
        self.assertEqual(files.call_args, mock.call('zbr', '/saved', 'v1'))
        run.assert_not_called()

    def test_saved_first(self):
        _, run, out = self.ready(lambda code, folder, version: None)
        self.assertEqual(run.call_args[0], ([28], '/saved'))
        refs = run.call_args[1]['references']
        self.assertNotIn(28, refs)
        self.assertEqual(set(refs) | {28}, set(dump8.ROSTER))
        self.assertIn('Saving 1 Tekken 8 moveset', out)

    def test_cannot_run(self):
        _, run, out = self.ready(lambda *a: None, find=dump8.DumpError('Steam is not installed'))
        run.assert_not_called()
        self.assertIn('cannot run to save movesets (Steam is not installed)', out)
        _, _, out = self.ready(lambda *a: None, dump=dump8.DumpError('Steam is not running'))
        self.assertIn('could not be saved (Steam is not running)', out)

    def test_folder_reaches_the_import(self):
        runs = []
        args = mock.Mock(tekken7=None, tekken8='/games/TEKKEN 8', movesets=None, files=None, game='g', out=None,
                         no_shared=True, tekken8_movesets='~/t8')
        with tempfile.TemporaryDirectory() as out_dir:
            args.out = out_dir

            def run(name, t7, movesets, game, out, make_shared=True, files=None, tekken8=None):
                runs.append((name, movesets, tekken8))
                return importer.pack.write(out_dir, definition(name), {'.nud': b'nud'}, 0)
            with mock.patch.object(import_character, 'needs_packages'), \
                    mock.patch.object(importer, 'tekken8_folder', side_effect=lambda f: f), \
                    mock.patch.object(import_character, 'tekken8_ready') as ready, \
                    mock.patch.object(importer, 'run', side_effect=run), \
                    mock.patch.object(importer, 'make_shared'), \
                    contextlib.redirect_stdout(io.StringIO()):
                import_character.add(args, ['reina'], import_character.Progress(False))
        self.assertEqual(runs, [('reina', os.path.expanduser('~/t8'), '/games/TEKKEN 8')])
        self.assertEqual(ready.call_args[0][:2], (['reina'], os.path.expanduser('~/t8')))


if __name__ == '__main__':
    unittest.main()
