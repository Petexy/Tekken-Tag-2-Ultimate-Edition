"""Tekken 7's battle subtitles: the saved files' records (tekken7/subtitles.py), the helper's answer and their saving
(tekken7/autodump.py), and the import asking the game for the ones not saved yet. Made-up bytes only."""
import contextlib
import importlib.util
import io
import os
import socket
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, HERE)

from ttt2char import importer, source                                # noqa: E402
from ttt2char.tekken7 import autodump, subtitles                     # noqa: E402

spec = importlib.util.spec_from_file_location('import_character', os.path.join(HERE, 'import_character.py'))
import_character = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_character)


def record(key, text, start=10, end=100, voice=None, language=b'us'):
    """One record as the game's files have it (text NUL-ended, padded to 4 bytes)."""
    body = text.encode('utf-8') + b'\0'
    body += bytes(-len(body) % 4)
    head = struct.pack('<3I4s20s20s', 0x38 + len(body), start, end, language, (voice or key).encode(), key.encode())
    return head + body


def saved(folder, code, data, language='us'):
    path = subtitles.saved_path(code, language, folder)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


class Records(unittest.TestCase):
    def test_records_in_order(self):
        data = record('ab_s00', 'Ready?', 5, 80) + record('ab_w01', 'Over.', 0, 60, voice='ep_abc_001')
        self.assertEqual(subtitles.parse(data), [subtitles.Part('ab_s00', 'ab_s00', 5, 80, 'Ready?'),
                                                 subtitles.Part('ab_w01', 'ep_abc_001', 0, 60, 'Over.')])
        self.assertEqual(subtitles.parse(b''), [])

    def test_the_key_is_the_pose_not_the_voice_line(self):
        # (a pose may play a voice line of another name: the game looks the pose's subtitle up by the key)
        data = record('ab_s04', 'Lunch.', voice='ep_abc_xyz_001')
        self.assertEqual(subtitles.parse(data)[0].key, 'ab_s04')

    def test_a_full_length_name(self):
        key = 'ab_spstart0123456789'                                # (20 characters: no NUL in its field)
        self.assertEqual(len(key), 20)
        self.assertEqual(subtitles.parse(record(key, 'x'))[0].key, key)

    def test_text_is_utf8(self):
        self.assertEqual(subtitles.parse(record('ab_s00', 'Wait… café — よ'))[0].text,
                         'Wait… café — よ')

    def test_not_a_subtitle_file(self):
        good = record('ab_s00', 'Ready?')
        for bad in (good[:-4], good + b'\1\0\0\0', struct.pack('<I', 8) + good[4:], struct.pack('<I', 0x3a) + good[4:]):
            with self.subTest(bad=bad[:4]), self.assertRaises(ValueError):
                subtitles.parse(bad)


class Lines(unittest.TestCase):
    def test_all_saved(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(autodump, 'SUBTITLE_LANGUAGES', ('us', 'fr')):
            self.assertFalse(subtitles.all_saved('abc', d))
            saved(d, 'abc', b'')                                                    # (an empty one: the game has none)
            self.assertFalse(subtitles.all_saved('abc', d))                         # (not in French)
            saved(d, 'abc', b'', 'fr')
            self.assertTrue(subtitles.all_saved('abc', d))

    def test_every_language_the_port_shows(self):
        """Saved: English, French, German, Italian, Spanish, Russian (game.ini's languages) and Japanese. Files an
        earlier version saved (English only) are not all."""
        self.assertEqual(sorted(autodump.SUBTITLE_LANGUAGES), sorted(('us', 'fr', 'de', 'it', 'es', 'ru', 'jp')))
        self.assertEqual(autodump.SUBTITLE_LANGUAGES[0], 'us')       # (first: a stopped save has English)
        self.assertTrue(set(autodump.SUBTITLE_LANGUAGES) <= set(subtitles.LANGUAGES))
        with tempfile.TemporaryDirectory() as d:
            saved(d, 'abc', b'')
            self.assertEqual(subtitles.saved_languages('abc', d), ('us',))
            self.assertFalse(subtitles.all_saved('abc', d))
            for language in autodump.SUBTITLE_LANGUAGES:
                saved(d, 'abc', b'', language)
            self.assertEqual(subtitles.saved_languages('abc', d), autodump.SUBTITLE_LANGUAGES)
            self.assertTrue(subtitles.all_saved('abc', d))

    def test_lines_of_a_saved_file(self):
        data = (record('ab_s00', 'Ready?') + record('ab_s01', 'One...', 15, 100) +
                record('ab_s01', " two and\nthree.", 104, 269) + record('ab_w00', '\nOver  and out. '))
        with tempfile.TemporaryDirectory() as d:
            saved(d, 'ABC', data)                                   # (the game's code may be upper case)
            self.assertEqual(subtitles.lines('abc', folder=d),
                             {'ab_s00': 'Ready?', 'ab_s01': 'One... two and three.',
                              'ab_w00': 'Over and out.'})
            self.assertEqual(subtitles.parts('abc', folder=d)['ab_s01'],
                             [(15, 100, 'One...'), (104, 269, ' two and\nthree.')])
            self.assertTrue(subtitles.saved('abc', folder=d))
            self.assertEqual(subtitles.lines('abc', 'fr', folder=d), {})         # (not saved in French)

    def test_japanese_parts_joined_without_spaces(self):
        data = record('ab_s00', '\u3088\u3057\n\u3044\u304f') + record('ab_s00', '\u305e\u3002', 120, 200)
        with tempfile.TemporaryDirectory() as d:
            saved(d, 'abc', data, 'jp')
            self.assertEqual(subtitles.lines('abc', 'jp', folder=d), {'ab_s00': '\u3088\u3057\u3044\u304f\u305e\u3002'})

    def test_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(subtitles.lines('abc', folder=d), {})              # (not saved)
            self.assertFalse(subtitles.saved('abc', folder=d))
            saved(d, 'abc', b'')                                                # (the game has none)
            self.assertEqual(subtitles.lines('abc', folder=d), {})
            self.assertTrue(subtitles.saved('abc', folder=d))

    def test_a_broken_file_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            path = saved(d, 'abc', record('ab_s00', 'Ready?')[:-4])
            with self.assertRaisesRegex(ValueError, path):
                subtitles.lines('abc', folder=d)

    def test_where_they_are_saved(self):
        self.assertEqual(subtitles.saved_path('MRY', 'us', '/f'),
                         os.path.join('/f', 'Binary', 'subtitles', 'mry', 'us', 'mry_sub.bin'))
        with mock.patch.object(autodump, 'FILES', '/saved'):
            self.assertTrue(subtitles.saved_path('mry').startswith(os.path.join('/saved', 'Binary', 'subtitles')))


class HelperAnswer(unittest.TestCase):
    """autodump.Helper.subtitles reading the helper's answer."""

    def test_answer(self):
        here, there = socket.socketpair()
        self.addCleanup(here.close)
        self.addCleanup(there.close)
        h = autodump.Helper.__new__(autodump.Helper)
        h.s, h.buf = here, b''
        data = record('ab_s00', 'Ready?')
        there.sendall(b'file 1 %d ABC\n' % len(data) + data + b'file 0 0 xyz\nlate qrs\nfile 0 0 -\nend\n')
        self.assertEqual(h.subtitles('us', [20, 25, 26, 300]),
                         [('ABC', data), ('xyz', None), ('qrs', autodump.LATE), (None, None)])
        self.assertEqual(there.recv(100), b'subtitles us 20 25 26 300\n')
        there.sendall(b'error not a language or too many fighters\n')
        with self.assertRaisesRegex(autodump.DumpError, 'not a language'):
            h.subtitles('xx', [20])


class Saving(unittest.TestCase):
    def test_saved_as_the_game_reads_them(self):
        data = record('ab_s00', 'Ready?')

        class Helper:
            def __init__(self):
                self.asked = []

            def subtitles(self, language, fighters):
                self.asked.append((language, list(fighters)))
                answers = {20: ('ABC', data), 25: ('xyz', None), 26: (None, None), 27: ('qqq', data)}
                return [answers[f] for f in fighters]

        h = Helper()
        fighters = {20: ('abc', 'Abc'), 25: ('xyz', 'Xyz'), 26: ('nop', 'Nop'), 27: ('rst', 'Rst')}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(autodump, 'SUBTITLE_BATCH', 3):
            failed = autodump._save_subtitles(h, fighters, d, ('us',))
            with open(subtitles.saved_path('abc', 'us', d), 'rb') as f:
                self.assertEqual(f.read(), data)
            self.assertEqual(os.path.getsize(subtitles.saved_path('xyz', 'us', d)), 0)    # (the game has none)
            self.assertFalse(subtitles.saved('nop', folder=d) or subtitles.saved('rst', folder=d))
        self.assertEqual(h.asked, [('us', [20, 25, 26]), ('us', [27])])
        self.assertEqual(failed, {26: 'Tekken 7 does not know the fighter',
                                  27: 'Tekken 7 calls the fighter qqq, not rst'})

    class Answers:
        """The game's answers: a record in every language, none in English (no file, or one it could not read)."""
        def __init__(self):
            self.asked = []

        def subtitles(self, language, fighters):
            self.asked.append((language, list(fighters)))
            return [('abc', None if language == 'us' else record('ab_s00', 'Line in ' + language))] * len(fighters)

    def test_only_the_languages_not_saved_yet(self):
        """An earlier version's English file (with records) and the game answering none in English: the other
        languages are saved, English is not asked for again and keeps its records."""
        english = record('ab_s00', 'Made-up line.')
        h = self.Answers()
        with tempfile.TemporaryDirectory() as d:
            saved(d, 'abc', english)
            src = source.Tekken7Source(types.SimpleNamespace(saved=d))
            failed = autodump._save_subtitles(h, {20: ('abc', 'Abc')}, d, autodump.SUBTITLE_LANGUAGES)
            with open(subtitles.saved_path('abc', 'us', d), 'rb') as f:
                self.assertEqual(f.read(), english)
            self.assertTrue(subtitles.all_saved('abc', d))
            self.assertEqual(src.subtitles(types.SimpleNamespace(TEKKEN7_CODE='abc'), ['ab_s00'])['ab_s00']['en'],
                             'Made-up line.')
        self.assertEqual(failed, {})
        self.assertEqual([language for language, _ in h.asked], list(autodump.SUBTITLE_LANGUAGES[1:]))

    def test_never_an_empty_answer_over_saved_records(self):
        """Asked again (as for a file not saved), an empty answer leaves a saved file with records as it is; it is
        saved over an empty one (the game has none) and where none is saved."""
        english = record('ab_s00', 'Made-up line.')
        with tempfile.TemporaryDirectory() as d, mock.patch.object(subtitles, 'saved', return_value=False):
            saved(d, 'abc', english)
            saved(d, 'abc', b'', 'fr')
            self.assertEqual(autodump._save_subtitles(self.Answers(), {20: ('abc', 'Abc')}, d, ('us', 'fr', 'de')), {})
            with open(subtitles.saved_path('abc', 'us', d), 'rb') as f:
                self.assertEqual(f.read(), english)
            for language in ('fr', 'de'):
                with open(subtitles.saved_path('abc', language, d), 'rb') as f:
                    self.assertEqual(f.read(), record('ab_s00', 'Line in ' + language))


class NotReadInTime(unittest.TestCase):
    """A file the game had not read in time (the helper's "late") is not saved, so it is asked for again, and a pack
    made meanwhile lacks that language; the game's "none" ("file 0") is still saved as an empty file."""

    class Game:
        """The helper's answers per language: {language: {code: LATE, None (the game has none) or bytes}}, a record of
        its own for the rest."""
        def __init__(self, answers=None):
            self.answers, self.asked = answers or {}, []

        def subtitles(self, language, fighters):
            self.asked.append((language, list(fighters)))
            codes = {20: 'abc', 25: 'xyz', 27: 'rst'}
            return [(codes[f], self.answers.get(language, {}).get(
                codes[f], record('ab_s00', 'Line in %s of %s' % (language, codes[f])))) for f in fighters]

    FIGHTERS = {20: ('abc', 'Abc'), 25: ('xyz', 'Xyz'), 27: ('rst', 'Rst')}

    def test_late_is_not_saved_and_asked_again(self):
        english = record('ab_s00', 'Made-up line.')
        late = {'fr': {'abc': autodump.LATE, 'xyz': autodump.LATE}, 'jp': {'abc': autodump.LATE},
                'de': {'xyz': None}}
        with tempfile.TemporaryDirectory() as d:
            saved(d, 'abc', english)                                # (English saved before: never asked again)
            game = self.Game(late)
            failed = autodump._save_subtitles(game, self.FIGHTERS, d, autodump.SUBTITLE_LANGUAGES)
            self.assertEqual(failed, {20: 'Tekken 7 did not read them in time in fr jp (asked for again by the next '
                                          'import or update)',
                                      25: 'Tekken 7 did not read them in time in fr (asked for again by the next '
                                          'import or update)'})
            for code, language in (('abc', 'fr'), ('abc', 'jp'), ('xyz', 'fr')):
                self.assertFalse(os.path.exists(subtitles.saved_path(code, language, d)), (code, language))
                self.assertFalse(os.path.exists(subtitles.saved_path(code, language, d) + '.part'))
            self.assertEqual(os.path.getsize(subtitles.saved_path('xyz', 'de', d)), 0)  # ("file 0": the game has none)
            with open(subtitles.saved_path('abc', 'us', d), 'rb') as f:
                self.assertEqual(f.read(), english)
            self.assertEqual(subtitles.saved_languages('abc', d), ('us', 'de', 'it', 'es', 'ru'))
            self.assertEqual(subtitles.saved_languages('xyz', d), ('us', 'de', 'it', 'es', 'ru', 'jp'))
            self.assertTrue(subtitles.all_saved('rst', d))
            self.assertFalse(subtitles.all_saved('abc', d) or subtitles.all_saved('xyz', d))
            # (the pack made now says which: character.ini subtitle_languages, launcher.py's partial_subtitles)
            src = source.Tekken7Source(types.SimpleNamespace(saved=d))
            self.assertEqual(src.subtitle_languages(types.SimpleNamespace(TEKKEN7_CODE='abc')),
                             ('en', 'de', 'it', 'es', 'ru'))
            self.assertEqual(src.subtitle_languages(types.SimpleNamespace(TEKKEN7_CODE='xyz')),
                             ('en', 'de', 'it', 'es', 'ru', 'ja'))
            self.assertEqual(game.asked[0], ('us', [25, 27]))
            # the next import or update: only the late ones are asked for, and saved now
            again = self.Game()
            self.assertEqual(autodump._save_subtitles(again, self.FIGHTERS, d, autodump.SUBTITLE_LANGUAGES), {})
            self.assertEqual(again.asked, [('fr', [20, 25]), ('jp', [20])])
            self.assertTrue(subtitles.all_saved('abc', d) and subtitles.all_saved('xyz', d))
            self.assertEqual(subtitles.lines('abc', 'fr', d), {'ab_s00': 'Line in fr of abc'})
            self.assertEqual(os.path.getsize(subtitles.saved_path('xyz', 'de', d)), 0)    # (not asked again)
            with open(subtitles.saved_path('abc', 'us', d), 'rb') as f:
                self.assertEqual(f.read(), english)

    def test_late_never_replaces_a_saved_file(self):
        """Asked again (as for a file not saved), a late answer leaves what was saved as it is, records or none."""
        english = record('ab_s00', 'Made-up line.')
        with tempfile.TemporaryDirectory() as d, mock.patch.object(subtitles, 'saved', return_value=False):
            saved(d, 'abc', english)
            saved(d, 'abc', b'', 'fr')
            game = self.Game({'us': {'abc': autodump.LATE}, 'fr': {'abc': autodump.LATE}})
            autodump._save_subtitles(game, {20: ('abc', 'Abc')}, d, ('us', 'fr'))
            with open(subtitles.saved_path('abc', 'us', d), 'rb') as f:
                self.assertEqual(f.read(), english)
            self.assertEqual(os.path.getsize(subtitles.saved_path('abc', 'fr', d)), 0)

    def test_the_dump_logs_it(self):
        """dump() of the subtitles alone: the late languages named in the log, the rest saved."""
        helper = types.SimpleNamespace(attach=lambda: 'ok', ready=lambda: True,
                                       subtitles=self.Game({'ru': {'abc': autodump.LATE}}).subtitles)
        session = types.SimpleNamespace(wait_game=lambda: 1, connect=lambda: helper, close=lambda: None)
        lines = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(autodump, 'steam_running', return_value=True), \
                mock.patch.object(autodump, 'find_tekken7', return_value=autodump.Tekken7('s', 't7', 'p', 'proton')), \
                mock.patch.object(autodump, 'tekken7_running', return_value=False), \
                mock.patch.object(autodump, 'build_helper'), \
                mock.patch.object(autodump, 'owned_dlc', return_value={}), \
                mock.patch.object(autodump, 'session', return_value=session):
            self.assertEqual(autodump.dump({}, os.path.join(d, 'movesets'), log=lines.append,
                                           subtitles={20: ('abc', 'Abc'), 27: ('rst', 'Rst')}, saved=d), ({}, {}))
            self.assertEqual(subtitles.saved_languages('abc', d), ('us', 'fr', 'de', 'it', 'es', 'jp'))
            self.assertTrue(subtitles.all_saved('rst', d))
        self.assertIn('  battle subtitles of 1 fighter(s), as the game reads them', lines)
        self.assertIn('  WARNING: the subtitles of Abc were not saved: Tekken 7 did not read them in time in ru (asked '
                      'for again by the next import or update)', lines)


class TheImportAsks(unittest.TestCase):
    """import_character.tekken7_ready asks the game for the subtitles not saved yet, in the dump of the rest."""

    def ready(self, files, have=None, **dump):
        with mock.patch.object(autodump, 'unowned', return_value={}), \
                mock.patch.object(importer, 'tekken7_paks'), mock.patch('ttt2char.tekken7.pak.Paks'), \
                mock.patch.object(importer, 'saved_movesets', return_value=have or {43: 'g', 8: 'h'}), \
                mock.patch.object(autodump, 'unsaved_files', return_value=[]), \
                mock.patch.object(autodump, 'dump', **(dump or {'return_value': ({}, {})})) as dumped, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            fighters = import_character.tekken7_ready(['geese'], 't7', 'movesets', files,
                                                      import_character.Progress(False))
        self.assertEqual(fighters, ['geese'])
        self.out = out.getvalue()
        return dumped

    def test_not_saved_yet(self):
        with tempfile.TemporaryDirectory() as d:
            dumped = self.ready(d)
        dumped.assert_called_once()
        self.assertEqual(dumped.call_args[1]['subtitles'], {43: ('mry', 'Geese Howard')})
        self.assertEqual(dumped.call_args[1]['saved'], d)

    def test_saved(self):
        with tempfile.TemporaryDirectory() as d:
            for language in autodump.SUBTITLE_LANGUAGES:
                saved(d, 'mry', b'', language)
            self.ready(d).assert_not_called()                       # (nothing to ask the game for)

    def test_saved_in_english_only(self):
        """Saved by an earlier version (English only): the game is asked for them (the languages not saved yet:
        Saving.test_only_the_languages_not_saved_yet)."""
        with tempfile.TemporaryDirectory() as d:
            saved(d, 'mry', b'')
            self.ready(d).assert_called_once()

    def test_not_saved_without_steam(self):
        """Only the subtitles wanted and Tekken 7 cannot run (Steam not started): imported all the same, warned."""
        with tempfile.TemporaryDirectory() as d:
            self.ready(d, side_effect=autodump.DumpError('Steam is not running')).assert_called_once()
        self.assertIn('WARNING: the Tekken 7 subtitles of Geese Howard were not saved (Steam is not running)',
                      self.out)

    def test_moveset_wanted_without_steam(self):
        """A moveset not saved yet still needs the game: that fails as before."""
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            self.ready(d, have={8: 'h'}, side_effect=autodump.DumpError('Steam is not running'))


if __name__ == '__main__':
    unittest.main()
