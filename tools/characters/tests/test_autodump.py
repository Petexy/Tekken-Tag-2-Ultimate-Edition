"""Unit tests of the background dumper's decisions (tekken7/autodump.py), with Steam's answers made up, and of what
an encrypted file the game does not read does to an import (made-up paths and helper: nothing real is started).

    python3 -m unittest discover tools/characters/tests
"""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ttt2char import importer                         # noqa: E402
from ttt2char.tekken7 import autodump, memdump        # noqa: E402
from test_formats import write_pak                    # noqa: E402

spec = importlib.util.spec_from_file_location('import_character', os.path.join(HERE, 'import_character.py'))
import_character = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_character)

PACKAGE = b'\xc1\x83\x2a\x9e' + bytes(12)              # a plain package's start
EXTRA = 'TekkenGame/Content/Character/Item/Sets/ABC/CS_ABC_extra.uasset'


class Ownership(unittest.TestCase):
    def unowned(self, fighters, apps):
        """autodump.unowned(fighters) with Steam saying the DLC `apps` are owned."""
        answer = {app: app in apps for app in autodump.DLC.values()}
        with mock.patch.object(autodump, 'steam_running', return_value=True), \
                mock.patch.object(autodump, 'find_tekken7'), mock.patch.object(autodump, 'build_helper'), \
                mock.patch.object(autodump, 'owned_dlc', return_value=answer):
            return autodump.unowned(fighters)

    def test_unowned_dlc_fighters_are_skipped(self):
        self.assertEqual(self.unowned([26, 36, 50, 56], {autodump.DLC[50]}),          # Negan's DLC only
                         {36: 'its DLC is not owned', 56: 'its DLC is not owned'})

    def test_base_fighters_need_no_steam(self):
        with mock.patch.object(autodump, 'steam_running', return_value=False), \
                mock.patch.object(autodump, 'owned_dlc') as asked:
            self.assertEqual(autodump.unowned([26, 22, 8]), {})               # Kazumi, Lucky Chloe, Heihachi
            asked.assert_not_called()

    def test_dlc_fighters_need_steam(self):
        with mock.patch.object(autodump, 'steam_running', return_value=False):
            with self.assertRaises(autodump.DumpError):
                autodump.unowned([50])


class Helper:
    """The helper as dump() uses it: the game reads `answers` ({pak path: bytes, or None}); every fighter loads."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def attach(self):
        return 'ok'

    def ready(self):
        return True

    def files(self, paths):
        self.asked += paths
        return [self.answers[p] for p in paths]

    def common(self):
        return 0x1000

    def u64(self, address):
        return 1

    def load(self, fighter):
        return 0x2000 + fighter, 'abc'

    def fixup(self, record, common):
        return 0x3000, 0x4000

    def read(self, address, size):
        return bytes(size)


class Session:
    def __init__(self, helper):
        self.helper, self.closed = helper, False

    def wait_game(self):
        return 1

    def connect(self):
        return self.helper

    def close(self):
        self.closed = True


def entry(path, usize):
    return types.SimpleNamespace(path=path, usize=usize)


class UnreadFiles(unittest.TestCase):
    """A file the game does not hand over plain and whole is named, with why; the others are saved, and the movesets
    are dumped all the same."""

    def dump(self, refused, saved, out):
        """dump() of fighter Abc, two of his files read whole and `refused` ({pak path: the game's answer}) not."""
        good = {'TekkenGame/Content/Character/Item/Sets/ABC/CS_ABC_1.uasset': PACKAGE,
                'TekkenGame/Content/WwiseAudio/Windows/AkBankVoiceABC.bnk': b'BKHD' + bytes(4)}
        entries = [entry(p, len(d)) for p, d in good.items()] + [entry(p, len(PACKAGE)) for p in refused]
        paks = types.SimpleNamespace(saved_path=lambda e: os.path.join(saved, *e.path.split('/')))
        helper, lines, written = Helper(dict(good, **refused)), [], []
        with mock.patch.object(autodump, 'steam_running', return_value=True), \
                mock.patch.object(autodump, 'find_tekken7', return_value=autodump.Tekken7('s', 't7', 'p', 'proton')), \
                mock.patch.object(autodump, 'tekken7_running', return_value=False), \
                mock.patch.object(autodump, 'build_helper'), \
                mock.patch.object(autodump, 'owned_dlc', return_value={}), \
                mock.patch.object(autodump, 'session', return_value=Session(helper)), \
                mock.patch.object(memdump, 'read_moveset', return_value=[]), \
                mock.patch.object(memdump, 'write_tkmvst', side_effect=lambda path, *a: written.append(path)), \
                mock.patch.dict(autodump.unread, clear=True):
            dumped, skipped = autodump.dump({26: ('abc', 'Abc')}, out, log=lines.append,
                                            files={26: ('Abc', entries)}, paks=paks)
            unread = dict(autodump.unread)
        for p, d in good.items():
            with open(paks.saved_path(entry(p, 0)), 'rb') as f:
                self.assertEqual(f.read(), d)
        self.assertFalse([p for p in refused if os.path.exists(paks.saved_path(entry(p, 0)))])
        self.assertEqual(helper.asked, [e.path for e in entries])
        self.assertEqual((sorted(dumped), skipped), ([8, 26], {}))         # (the movesets: Heihachi's too)
        self.assertEqual(len(written), 2)
        return lines, unread

    def test_each_failure_says_why(self):
        for extra, why in ((None, 'the game could not open it'),
                           (PACKAGE[:3], 'the game gave 3 bytes, its pak entry has 16 (a pak in a subfolder of %s, '
                                         'such as a mod, may replace it)' % os.path.join('TekkenGame', 'Content',
                                                                                         'Paks')),
                           (b'\x09\xf8\x48\xc6' + bytes(12), 'the game gave it still encoded')):
            with self.subTest(why=why), tempfile.TemporaryDirectory() as d:
                lines, unread = self.dump({EXTRA: extra}, os.path.join(d, 'files'), os.path.join(d, 'movesets'))
                self.assertIn('  WARNING: Tekken 7 did not read %s: %s' % (EXTRA, why), lines)
                self.assertIn('  Abc: 1 of the 3 files not saved, asked for again on the next import (an import '
                              'fails only on one it needs, naming it)', lines)
                self.assertEqual(unread, {EXTRA: why})

    def test_many_failures_name_a_few(self):
        refused = {'TekkenGame/Content/Character/Item/Meshes/abc/T_abc_%d.uasset' % n: None for n in range(8)}
        with tempfile.TemporaryDirectory() as d:
            lines, unread = self.dump(refused, os.path.join(d, 'files'), os.path.join(d, 'movesets'))
        named = [line for line in lines if line.startswith('  WARNING: Tekken 7 did not read ')]
        self.assertEqual(named, ['  WARNING: Tekken 7 did not read %s: the game could not open it' % p
                                 for p in list(refused)[:autodump.UNREAD_SHOWN]])
        self.assertIn('  WARNING: ... and 3 more', lines)
        self.assertIn('  Abc: 8 of the 10 files not saved, asked for again on the next import (an import fails only '
                      'on one it needs, naming it)', lines)
        self.assertEqual(unread, dict.fromkeys(refused, 'the game could not open it'))     # (every one kept)

    def test_the_import_says_which_file_and_why(self):
        with mock.patch.dict(autodump.unread, {EXTRA: 'the game could not open it'}, clear=True):
            text = str(importer._not_saved(EXTRA, 'geese'))
            self.assertTrue(text.startswith('Geese Howard needs %s, which Tekken 7 did not read: the game could not '
                                            'open it. Let Steam verify' % EXTRA), text)
            self.assertNotIn('dump_tekken7', text)
            self.assertIn('An added fighter needs', str(importer._not_saved(EXTRA)))
        with mock.patch.dict(autodump.unread, clear=True):          # (not asked of the game in this run)
            self.assertIn('run dump_tekken7.py geese', str(importer._not_saved(EXTRA, 'geese')))


class FightersWithUnreadFiles(unittest.TestCase):
    def ready(self, paks_dir, unsaved):
        """import_character.tekken7_ready(['geese']) with his moveset saved and `unsaved` his files not saved, which
        the made-up dump does not read either -> (fighters, printed)."""
        out = io.StringIO()
        with mock.patch.object(autodump, 'unowned', return_value={}), \
                mock.patch.object(importer, 'tekken7_paks', return_value=paks_dir), \
                mock.patch('ttt2char.tekken7.pak.Paks'), \
                mock.patch.object(importer, 'saved_movesets', return_value={43: 'g', 8: 'h'}), \
                mock.patch.object(autodump, 'unsaved_files', return_value=unsaved), \
                mock.patch.object(autodump, 'dump', return_value=({}, {})) as dumped, \
                contextlib.redirect_stdout(out):
            fighters = import_character.tekken7_ready(['geese'], 't7', 'movesets', 'files',
                                                      import_character.Progress(False))
        dumped.assert_called_once()
        return fighters, out.getvalue()

    def test_a_fighter_with_his_moveset_is_imported(self):
        # (the import reads his files as it needs them: importer.run fails on one it needs, naming it)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.ready(d, [entry(EXTRA, 16)])[0], ['geese'])

    def test_a_mod_pak_below_the_paks_folder_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            write_pak(os.path.join(d, 'pakchunk0-WindowsNoEditor.pak'), {EXTRA: PACKAGE})
            os.makedirs(os.path.join(d, '~mods', 'more'))
            holding, other = os.path.join(d, '~mods', 'abc_P.pak'), os.path.join(d, '~mods', 'more', 'xyz_P.PAK')
            write_pak(holding, {EXTRA: PACKAGE[:3]})
            write_pak(other, {'TekkenGame/Content/Character/Item/Sets/XYZ/CS_XYZ.uasset': PACKAGE})
            with open(os.path.join(d, '~mods', 'broken.pak'), 'wb') as f:
                f.write(b'not a pak')
            fighters, printed = self.ready(d, [entry(EXTRA, 16)])
        self.assertEqual(fighters, ['geese'])
        lines = printed.splitlines()
        self.assertIn('WARNING: Tekken 7 also reads %s (a mod?), which has 1 of the encrypted files it is asked for '
                      '(%s): ' % (holding, EXTRA), '\n'.join(lines))
        self.assertIn('WARNING: Tekken 7 also reads %s (a mod?): the import reads only the paks at the top of %s'
                      % (other, d), lines)
        self.assertTrue(any(l.startswith('WARNING: Tekken 7 also reads %s (a mod?), whose list of files cannot be '
                                         'read' % os.path.join(d, '~mods', 'broken.pak')) for l in lines), lines)
        self.assertFalse(any('pakchunk0' in l for l in lines))


if __name__ == '__main__':
    unittest.main()
