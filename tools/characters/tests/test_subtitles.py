"""The added fighters' own subtitles (convert/subtitles.py) on made-up data (no game files needed): the subtitle
file's table, language containers and text banks written and read back, the donor's intro and win poses shown the
line they stream (Lars-like and Jun-like poses; a line with no text: no subtitle), the clips the streamed tones play
(convert/voice.py), Tekken 8's text banks (tekken8/text.py) and shared/'s file.

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import tempfile
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from test_tekken8_import_moveset import nus3                  # noqa: E402
from ttt2char import pack, shared                              # noqa: E402
from ttt2char.convert import moveset, subtitles as S, voice    # noqa: E402
from ttt2char.tekken8 import text as text8, voice as voice8    # noqa: E402


def header():
    """A made-up one-text bank header (the layout subtitles.bank copies)."""
    h = bytearray(b'\xff' * S.BANK_HEADER)
    h[0:8] = b'NTXB\x00\x02\x02\x01'
    struct.pack_into('>I', h, 8, 0)
    struct.pack_into('>5I', h, 0x0C, *S.BANK_WORDS)
    struct.pack_into('>5I', h, 0x30, 1, 4, 0, 0, 0x12)
    h[0x50:0x60] = bytes.fromhex('000000010030000100000004ffffffff')
    h[0x60:0x64] = bytes(4)
    return bytes(h)


def original(count=3 * S.LINES):
    """A made-up subtitle file: `count` entries, one line (id 1, line 0) said in English and French."""
    entries = [None] * count
    entries[S.LINES] = S.container({1: S.bank(header(), 1, S.markup('Mine.', 10, 90)),
                                    3: S.bank(header(), 3, S.markup('A moi.', 10, 90))})
    return S.write_table(entries)


def clip(name, silent_frames, loud_frames, tail_frames=30, rate=24000):
    step = rate // 60
    a = np.zeros((1, step * (silent_frames + loud_frames + tail_frames)), np.int16)
    a[0, step * silent_frames:step * (silent_frames + loud_frames)] = 8000
    return name, rate, a


class Table(unittest.TestCase):
    def test_round_trip(self):
        data = original()
        entries = S.read_table(data)
        self.assertEqual(len(entries), 3 * S.LINES)
        self.assertEqual(S.write_table(entries), data)
        self.assertEqual(struct.unpack_from('>II', data, 4 + 8 * 0)[1], 4)          # (an empty entry: 4 bytes ff)
        offsets = [struct.unpack_from('>I', data, 4 + 8 * i)[0] for i in range(len(entries))]
        self.assertTrue(all(o % 16 == 0 for o in offsets))

    def test_bank_layout(self):
        text = S.markup('Ready, partner?', 25, 140)
        b = S.bank(header(), 3, text)
        self.assertEqual(b[6], 4)                                   # (language byte: entry + 1)
        self.assertEqual(len(b) % 16, 0)
        self.assertEqual(struct.unpack_from('>I', b, 8)[0], len(b))
        size, _, units = struct.unpack_from('>IHH', b, S.BANK_HEADER)
        key, key4 = struct.unpack_from('>II', b, 0x38)
        self.assertEqual((key4, size), (key + 4, key + 12))
        self.assertEqual(b[S.BANK_HEADER + key:S.BANK_HEADER + key + 8], b'0\0\0\0' + bytes(4))
        self.assertEqual(units, len(text))
        raw = text.encode('utf-8')
        self.assertEqual(b[S.BANK_HEADER + 8 + len(raw):S.BANK_HEADER + 10 + len(raw)], bytes(2))   # (two NULs)
        self.assertEqual(S.unmarked(S.bank_text(b)), ('Ready, partner?', 25, 140))
        self.assertTrue(S.is_template(b))

    def test_markup_limits(self):
        self.assertEqual(S.unmarked(S.markup('x', 0, 0)), ('x', 1, 2))          # (never a NUL, hide after show)
        _, show, hide = S.unmarked(S.markup('x', 70000, 90000))
        self.assertLess(hide, 0xD800)
        self.assertEqual(S.unmarked('plain'), ('plain', None, None))

    def test_table_with_fighters(self):
        lines = {0: {'show': 31, 'hide': 200, 'clip': 'Play_okm_sta_00',
                     'text': {'en': 'By this blade, I promise…', 'fr': 'Sur mon épée.'}},
                 12: {'show': 5, 'hide': 80, 'clip': 'Play_okm_win_00', 'text': {'en': 'Good work.'}}}
        data = S.table(original(), {66: lines})
        entries = S.read_table(data)
        self.assertEqual(len(entries), 67 * S.LINES)
        self.assertEqual(entries[S.LINES], S.read_table(original())[S.LINES])     # (the title's own kept)
        self.assertTrue(all(e is None for e in entries[3 * S.LINES:66 * S.LINES]))   # (ids between: empty)
        banks = S.read_container(entries[66 * S.LINES])
        self.assertEqual(len(banks), 16)
        self.assertEqual(S.unmarked(S.bank_text(banks[1])), ('By this blade, I promise...', 31, 200))
        self.assertEqual(S.unmarked(S.bank_text(banks[3]))[0], 'Sur mon \u00e9p\u00e9e.')   # (no font: kept)
        for i in (0, 2, 4, 5, 6, 7, 8, 9, 10, 15):
            self.assertEqual(banks[i], banks[1])                     # (no text of its own: the English bank)
        self.assertEqual(S.bank_text(S.read_container(entries[66 * S.LINES + 12])[1]).count('Good work.'), 1)
        self.assertIsNone(entries[66 * S.LINES + 1])
        # (the container points the other entries at the English bank's bytes)
        e = entries[66 * S.LINES]
        en = struct.unpack_from('>II', e, 4 + 8 * 1)
        self.assertEqual(struct.unpack_from('>II', e, 4 + 8 * 0), en)
        self.assertNotEqual(struct.unpack_from('>II', e, 4 + 8 * 3), en)
        self.assertEqual(en[0], S.CONTAINER_START)

    def test_no_template(self):
        with self.assertRaises(ValueError):
            S.template([None, None])


class Fit(unittest.TestCase):
    GLYPHS = {ord(c) for c in " !\"'.,?-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZé"}

    def test_font(self):
        self.assertEqual(S.fit('Don’t “go”… café è — ok', self.GLYPHS),
                         'Don\'t "go"... café e - ok')
        self.assertEqual(S.fit('a☃b', self.GLYPHS), 'ab')                    # (no plain form: left out)

    def test_no_font(self):
        self.assertEqual(S.fit('Don’t… café'), "Don't... café")

    def test_one_line(self):
        self.assertEqual(S.fit('  Two\nlines<#invsub>  here\r\n'), 'Two lines here')

    def test_spaces(self):
        glyphs = self.GLYPHS | {0x3000, 0x3042}
        self.assertEqual(S.fit('\u3042\u3000\u3042', glyphs), '\u3042\u3000\u3042')
        self.assertEqual(S.fit('Oui\u00a0!', glyphs), 'Oui !')
        self.assertEqual(S.fit('Oui\u00a0!'), 'Oui !')

    def test_glyph_codes(self):
        nfh = bytearray(0x450 + 64)
        nfh[0:3] = b'NFH'
        struct.pack_into('<I', nfh, 4, 22)
        struct.pack_into('<I', nfh, 8, 2)
        struct.pack_into('>H', nfh, 0x450 + 22, 0x41)
        struct.pack_into('>H', nfh, 0x450 + 32 + 22, 0x2019)
        self.assertEqual(S.glyph_codes(bytes(nfh)), {0x41, 0x2019})
        self.assertIsNone(S.glyph_codes(b'XXX' + bytes(0x500)))


class Lines(unittest.TestCase):
    def test_timing(self):
        self.assertEqual(S.timing(clip('a', 30, 60)), (31, 89 + 27))
        self.assertEqual(S.timing(('a', 24000, np.zeros((2, 2400), np.int16))), (1, 28))

    def test_lines_and_values(self):
        streams = {'rm_Dst': {0: clip('Play_okm_sta_00', 24, 100), 1: clip('Play_okm_sta_01', 24, 50),
                              2: (voice.SILENCE, 24000, np.zeros((1, 10), np.int16)),
                              3: clip('Play_okm_sta_02', 24, 10)},
                   'rm_Dwi': {0: clip('Play_okm_win_00', 10, 120)}}
        texts = {'Play_okm_sta_00': {'en': 'First.', 'fr': 'Premier.', 'xx': 'dropped'},
                 'play_okm_win_00': {'en': 'Won.'},
                 'Play_okm_sta_02': {'fr': 'No English.'}}
        lines = S.lines_of(streams, texts)
        self.assertEqual(sorted(lines), [0, 10])
        self.assertEqual(lines[0]['text'], {'en': 'First.', 'fr': 'Premier.'})
        self.assertEqual((lines[0]['show'], lines[0]['hide'], lines[0]['clip']), (25, 123 + 27, 'Play_okm_sta_00'))
        self.assertEqual(S.values(lines, 85), {0x0D000000: 85 << 8, 0x0D001000: 85 << 8 | 10})

    def test_pack_copy(self):
        lines = {0: {'show': 25, 'hide': 150, 'clip': 'mz_s00', 'text': {'en': 'Café time.'}},
                 10: {'show': 5, 'hide': 50, 'clip': 'mz_w02', 'text': {'en': 'Done.'}}}
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(S.read_lines(folder), {})
            os.makedirs(os.path.join(folder, 'source'))
            with open(os.path.join(folder, 'source', S.FILE), 'wb') as f:
                f.write(S.dumps(lines))
            self.assertEqual(S.read_lines(folder), lines)


class FakeTables(dict):
    END_BEGIN = dict(req=0, id=moveset.TT_END, value=0)
    END_EXTRA = dict(frame=0, id=0, value=0)


def tables(poses):
    """A moveset's three tables from [(subtitle value or None, streamed line value or None, other begin rows)]."""
    B, P, moves = [], [], []
    for sub, stream, other in poses:
        begin = len(B)
        if sub is not None:
            B.append(dict(req=0, id=moveset.SUBTITLE_PROP, value=sub))
        B += [dict(req=0, id=i, value=v) for i, v in other] + [dict(FakeTables.END_BEGIN)]
        extra = len(P)
        P += [dict(frame=0x8001, id=0x82e5, value=0x400a)]
        if stream is not None:
            P.append(dict(frame=0x8001, id=moveset.STREAM_LINE_PROP, value=stream))
        P.append(dict(FakeTables.END_EXTRA))
        moves.append(dict(begin_props=begin, extraprops=extra))
    return {'moves': moves, 'move_begin_props': B, 'extra_move_properties': P}


def begin(t, j):
    B, out, at = t['move_begin_props'], [], t['moves'][j]['begin_props']
    while at is not None and B[at]['id'] != moveset.TT_END:
        out.append((B[at]['id'], B[at]['value']))
        at += 1
    return out


class PoseRewrite(unittest.TestCase):
    """The donor's poses show the fighter's line of the clip they stream (by their 0x8300 line, never by the donor's
    own subtitle number), or none."""

    def test_lars_like(self):
        # la_srm (0x2600, rm_Dst 0), la_slm (0x2601, rm_Dst 1), la_slm_solo (0x2607, rm_Dst 2), la_wnm_1 (0x260A,
        # rm_Dwi 0), a win pose with no subtitle
        t = tables([(0x2600, 0x0D000000, []), (0x2601, 0x0D000001, [(0x8057, 1)]), (0x2607, 0x0D000002, []),
                    (0x260A, 0x0D001000, []), (None, 0x0D001000, [])])
        shown = S.values({0: {}, 1: {}, 10: {}}, 70)                # (no text of rm_Dst 2)
        self.assertEqual(moveset.rewrite_subtitles(t, shown), (3, 1))
        self.assertEqual(begin(t, 0), [(moveset.SUBTITLE_PROP, 70 << 8)])
        self.assertEqual(begin(t, 1), [(moveset.SUBTITLE_PROP, 70 << 8 | 1), (0x8057, 1)])
        self.assertIsNone(t['moves'][2]['begin_props'])             # (no line of it: no subtitle, not Lars's)
        self.assertEqual(begin(t, 3), [(moveset.SUBTITLE_PROP, 70 << 8 | 10)])
        self.assertEqual(begin(t, 4), [])

    def test_jun_like(self):
        # Jun's numbers differ from her tones: ju_srm_01 0x2A02 streams tone 3, ju_srm_02 0x2A04 tone 2
        t = tables([(0x2A00, 0x0D000000, []), (0x2A02, 0x0D000003, []), (0x2A04, 0x0D000002, []),
                    (0x2A03, 0x0D000004, [])])
        shown = S.values({0: {}, 2: {}, 3: {}}, 81)
        self.assertEqual(moveset.rewrite_subtitles(t, shown), (3, 1))
        self.assertEqual([begin(t, j) for j in range(4)],
                         [[(moveset.SUBTITLE_PROP, 81 << 8)], [(moveset.SUBTITLE_PROP, 81 << 8 | 3)],
                          [(moveset.SUBTITLE_PROP, 81 << 8 | 2)], []])

    def test_no_text_at_all(self):
        t = tables([(0x2600, 0x0D000000, []), (0x260A, None, [(0x8057, 1)])])      # (one streams no line)
        self.assertEqual(moveset.rewrite_subtitles(t, {}), (0, 2))
        self.assertIsNone(t['moves'][0]['begin_props'])
        self.assertEqual(begin(t, 1), [(0x8057, 1)])

    def test_shared_lists(self):
        # two poses sharing one begin list but streaming different lines get a list each; the donor's stays
        t = tables([(0x2600, 0x0D000000, [])])
        t['moves'].append(dict(begin_props=0, extraprops=len(t['extra_move_properties'])))
        t['extra_move_properties'] += [dict(frame=0x8001, id=moveset.STREAM_LINE_PROP, value=0x0D000001),
                                       dict(FakeTables.END_EXTRA)]
        before = [dict(r) for r in t['move_begin_props']]
        moveset.rewrite_subtitles(t, S.values({0: {}, 1: {}}, 64))
        self.assertEqual((begin(t, 0), begin(t, 1)), ([(moveset.SUBTITLE_PROP, 64 << 8)],
                                                      [(moveset.SUBTITLE_PROP, 64 << 8 | 1)]))
        self.assertEqual(t['move_begin_props'][:len(before)], before)

    def test_converter(self):
        import collections
        c = moveset.Converter.__new__(moveset.Converter)
        c.T, c.stats = tables([(0x2600, 0x0D000000, []), (0x2601, 0x0D000001, [])]), collections.Counter()
        c.own_subtitles()                                           # (no subtitles given: the donor's as they are)
        self.assertEqual(begin(c.T, 0), [(moveset.SUBTITLE_PROP, 0x2600)])
        c.subtitles = S.values({0: {}}, 64)
        c.own_subtitles()
        self.assertEqual((begin(c.T, 0), begin(c.T, 1)), ([(moveset.SUBTITLE_PROP, 64 << 8)], []))
        self.assertEqual(sorted(c.stats.values()), [1, 1])


class Importer(unittest.TestCase):
    """importer._subtitles: the source's text of the clips the poses stream; silent tones are not asked about."""

    def test_lines(self):
        from ttt2char import importer
        asked = []

        class Source:
            def subtitles(self, d, names, log=None):
                asked.append(names)
                return {'mz_s00': {'en': 'Line one.'}}
        streams = {'rm_Dst': {0: clip('mz_s00', 20, 60), 1: clip('mz_s01', 20, 60),
                              2: (voice.SILENCE, 24000, np.zeros((1, 10), np.int16))},
                   'rm_Dwi': {0: clip('mz_w02', 5, 60)}}
        log = []
        said = importer._subtitles(Source(), None, streams, log.append)
        self.assertEqual(asked, [['mz_s00', 'mz_s01', 'mz_w02']])
        self.assertEqual(list(said), [0])
        self.assertIn('mz_s01: no text', log[0])
        self.assertEqual(importer._subtitles(object(), None, streams, log.append), {})   # (a source without text)

    def test_stand_in(self):
        from ttt2char import importer
        with mock_motbin(tables([(0x2A00, 0x0D000000, []), (0x2A04, 0x0D000002, [])])) as t:
            importer.stand_in_moveset(b'donor', 58, '[X]', S.values({2: {}}, 64))
        self.assertEqual((begin(t, 0), begin(t, 1)), ([], [(moveset.SUBTITLE_PROP, 64 << 8 | 2)]))


def mock_motbin(t):
    """stand_in_moveset on a made-up donor moveset of tables t (motbin's reading and building left out)."""
    import contextlib
    from unittest import mock
    from ttt2char import importer

    @contextlib.contextmanager
    def patched():
        m = types.SimpleNamespace(tables=t)
        header = bytearray(0x200)
        with mock.patch.object(importer.motbin, 'read', return_value=m), \
                mock.patch.object(importer.motbin, 'split', return_value=(bytes(header), b'name\0', b'', None)), \
                mock.patch.object(importer.motbin, 'build', return_value=b'built'):
            yield t
    return patched()


class StreamedTones(unittest.TestCase):
    """voice._build_one gives each streamed tone's clip (build's streams)."""

    def test_tones(self):
        clips = voice8.Clips.__new__(voice8.Clips)
        line = np.full((1, 480), 3000, np.int16)
        clips.kinds = {('intro', None): [('Play_okm_sta_00', 24000, line), ('Play_okm_sta_01', 24000, line)]}
        tones = {}
        data = nus3([('la_s_t2_1p', b'A' * 16, None), ('la_s_t2_2p', b'B' * 16, None),
                     ('la_s_t2_2p_solo', b'C' * 16, None), ('dummy2', b'', None)])
        voice._build_one('rm_Dst', data, clips, 'clv', 24000, {}, tones=tones)
        self.assertEqual({k: v[0] for k, v in tones.items()},
                         {0: 'Play_okm_sta_00', 1: 'Play_okm_sta_01', 2: 'Play_okm_sta_00'})
        silent = {}
        clips.kinds = {('atk', 's'): [('Play_GOT_Attack_S_001', 24000, line)]}
        voice._build_one('rm_Dst', data, clips, 'aza', 24000, {}, tones=silent)
        self.assertEqual({v[0] for v in silent.values()}, {voice.SILENCE})


def gtb(records):
    """A made-up Gryphon text bank's export data: DataSize (6 bytes), the gbtd header, the records."""
    out = bytearray(6) + b'gbtd' + struct.pack('<IHHIII', 0x40, 1, 1, 1, 0, len(records))
    out += bytes(6 + 0x40 - len(out))
    for key, text in records:
        k, v = key.encode() + b'\0', text.encode('utf-8') + b'\0'
        k += bytes(-len(k) % 4)
        v += bytes(-len(v) % 4)
        out += b'text' + struct.pack('<III', 0x10, len(k), len(v)) + bytes(8) + k + v
    return bytes(out)


class FakeStore:
    def __init__(self, banks):
        self.banks = banks              # {path: export data}
        self.read = []

    def find(self, prefix):
        return [p for p in self.banks if p.startswith(prefix)]

    def package(self, path):
        self.read.append(path)
        data = self.banks[path]
        return types.SimpleNamespace(main_export=lambda: types.SimpleNamespace(data=data))


class TextBanks(unittest.TestCase):
    RECORDS = [('TEXT_VO_010_okm_sta_00_000', 'By this blade.'),
               ('TEXT_VO_010_okm_sta_00_vr00_000', 'Against one opponent.'),
               ('TEXT_VO_010_okm_sta_01_000', 'Older words.'),
               ('TEXT_301_VO_okm_sta_01_000', 'Newer words.'),
               ('TEXT_VO_010_okm_win_00a_000', 'First half,'),
               ('TEXT_VO_010_okm_win_00b_000', 'second half.'),
               ('TEXT_VO_010_okm_win_01_001', 'A second part only.'),
               ('TEXT_SYS_menu_000', 'Menu')]

    def test_records(self):
        got = text8.records(gtb(self.RECORDS))
        self.assertEqual(got, dict(self.RECORDS))
        with self.assertRaises(ValueError):
            text8.records(b'nothing here')

    def test_pose_text(self):
        texts = dict(self.RECORDS)
        self.assertEqual(text8.pose_text(texts, 'okm', 'sta', 0), 'By this blade.')
        self.assertEqual(text8.pose_text(texts, 'okm', 'sta', 1), 'Newer words.')       # (the newest update's)
        self.assertEqual(text8.pose_text(texts, 'okm', 'win', 0), 'First half, second half.')
        self.assertIsNone(text8.pose_text(texts, 'okm', 'win', 1))
        self.assertIsNone(text8.pose_text(texts, 'okm', 'win', 3))

    def test_pose_lines(self):
        store = FakeStore({'Polaris/Content/Localize/en/GTB_Upd_010_System02.uasset': gtb(self.RECORDS),
                           'Polaris/Content/Localize/en/GTB_Other.uasset': gtb([('TEXT_SYS_a_000', 'x')]),
                           'Polaris/Content/Localize/fr/GTB_Upd_010_System02.uasset': gtb(
                               [('TEXT_VO_010_okm_sta_00_000', 'Sur mon épée.')]),
                           'Polaris/Content/Localize/fr/GTB_Other.uasset': gtb([])})
        got = text8.pose_lines(store, ['Play_okm_sta_00', 'Play_okm_win_00', 'Play_okm_win_03',
                                       'Play_OKM_Damage_KO_001'])
        self.assertEqual(got, {'Play_okm_sta_00': {'en': 'By this blade.', 'fr': 'Sur mon épée.'},
                               'Play_okm_win_00': {'en': 'First half, second half.'}})
        self.assertNotIn('Polaris/Content/Localize/fr/GTB_Other.uasset', store.read)     # (only banks with lines)


class Tekken7Text(unittest.TestCase):
    def test_saved_folder(self):
        """Tekken 7's texts come from the folder of the files the game read (the importer's --files), English and
        the other languages saved, matched to the clips by name whatever the case."""
        from test_tekken7_subtitles import record, saved
        from ttt2char import source
        with tempfile.TemporaryDirectory() as folder:
            saved(folder, 'abc', record('ab_s00', 'Ready?') + record('ab_w02', 'Over') + record('ab_w02', 'and done.'))
            saved(folder, 'abc', record('ab_s00', 'Pret ?'), 'fr')
            t7 = source.Tekken7Source(types.SimpleNamespace(saved=folder))
            d = types.SimpleNamespace(TEKKEN7_CODE='ABC')
            self.assertEqual(t7.subtitles(d, ['AB_S00', 'ab_w02', 'ab_s01']),
                             {'AB_S00': {'en': 'Ready?', 'fr': 'Pret ?'}, 'ab_w02': {'en': 'Over and done.'}})
            with open(os.path.join(folder, 'Binary', 'subtitles', 'abc', 'us', 'abc_sub.bin'), 'wb') as f:
                f.write(b'\x01')                                     # (a broken file: that language left out)
            logged = []
            self.assertEqual(t7.subtitles(d, ['ab_s00'], log=logged.append), {'ab_s00': {'fr': 'Pret ?'}})
            self.assertEqual(len(logged), 1)


class SharedFile(unittest.TestCase):
    def test_shared(self):
        lines = {0: {'show': 25, 'hide': 150, 'clip': 'Play_okm_sta_00', 'text': {'en': 'Ready.'}}}
        archives = types.SimpleNamespace(read=lambda key: {S.KEY: original()}[key])
        with tempfile.TemporaryDirectory() as folder:
            os.makedirs(os.path.join(folder, 'source'))
            with open(os.path.join(folder, 'source', S.FILE), 'wb') as f:
                f.write(S.dumps(lines))
            d = types.SimpleNamespace(NAME='Clive')
            files = shared.subtitle_file(archives, [(3, d, folder), (5, d, tempfile.gettempdir())])
            self.assertEqual(sorted(files), ['keys/917395eb.bin'])
            entries = S.read_table(files['keys/917395eb.bin'])
            self.assertEqual(len(entries), (pack.place(3)['id'] + 1) * S.LINES)
            text = S.bank_text(S.read_container(entries[pack.place(3)['id'] * S.LINES])[1])
            self.assertEqual(S.unmarked(text), ('Ready.', 25, 150))
            self.assertEqual(shared.subtitle_file(archives, [(5, d, tempfile.gettempdir())]), {})


if __name__ == '__main__':
    unittest.main()
