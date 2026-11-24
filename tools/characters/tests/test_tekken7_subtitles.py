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
import unittest
from unittest import mock

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, HERE)

from ttt2char import importer                                        # noqa: E402
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
        there.sendall(b'file 1 %d ABC\n' % len(data) + data + b'file 0 0 xyz\nfile 0 0 -\nend\n')
        self.assertEqual(h.subtitles('us', [20, 25, 300]), [('ABC', data), ('xyz', None), (None, None)])
        self.assertEqual(there.recv(100), b'subtitles us 20 25 300\n')
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
            saved(d, 'mry', b'')
            self.ready(d).assert_not_called()                       # (nothing to ask the game for)

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
