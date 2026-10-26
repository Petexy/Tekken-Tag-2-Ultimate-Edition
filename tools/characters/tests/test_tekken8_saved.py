"""Tekken 8 movesets saved, and what the import does when a fighter's own cannot be had, on made-up files (no game, no
Steam): a reference's motbin alone is no moveset saved, a second fighter's import keeps hers, a dump that fails keeps
the files saved before (also after a game update: the manifest's 'before'), a build the helper does not know starts
nothing (the exe's file read as the helper's attach reads the game), --all with Tekken 8 alone there, the stand-in's
pack marked and the launcher offering to update it, tekken8/__init__.py naming every module.

    python3 -m pytest -q tools/characters/tests/test_tekken8_saved.py
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

import launcher                                       # noqa: E402
from test_tekken8_autodump import JIN, KAZUYA, REINA, FakeHelper, FakeSession, game_files, write   # noqa: E402
from ttt2char import importer, pack, source           # noqa: E402
from ttt2char.characters import CHARACTERS, definition, game_of   # noqa: E402
from ttt2char.tekken7 import autodump as dump7        # noqa: E402
from ttt2char.tekken8 import autodump as dump8        # noqa: E402

spec = importlib.util.spec_from_file_location('import_character', os.path.join(HERE, '..', 'import_character.py'))
import_character = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_character)


def fnv1a(data):
    h = 0xcbf29ce484222325
    for b in data:
        h = ((h ^ b) * 0x100000001b3) % (1 << 64)
    return h


def exe(functions, va=0x1000, raw=0x400, size=0x2000):
    """A Windows program with one section (at `va`, its bytes at `raw` in the file) holding functions {address at
    the preferred base: bytes}."""
    head = bytearray(raw)
    head[:2] = b'MZ'
    pe = 0x80
    struct.pack_into('<I', head, 0x3C, pe)
    head[pe:pe + 4] = b'PE\0\0'
    struct.pack_into('<H', head, pe + 6, 1)                         # sections
    struct.pack_into('<H', head, pe + 20, 0xF0)                     # the optional header's size
    section = pe + 24 + 0xF0
    head[section:section + 8] = b'.text\0\0\0'
    struct.pack_into('<IIII', head, section + 8, size, va, size, raw)
    body = bytearray(size)
    for address, data in functions.items():
        o = address - dump8.PREFERRED_BASE - va
        body[o:o + len(data)] = data
    return bytes(head) + bytes(body)


def write_saved(folder, fighters, version, common=True):
    """A saved-movesets folder for `version`: {code: motbin_only} with small files, and its manifest."""
    man = {'game': version, 'fighters': {}, 'common': {'com.anmbin': 3} if common else {}}
    files = {'com.anmbin': b'com'} if common else {}
    for code, only in fighters.items():
        names = ['%s.motbin' % code, '%s.motbin.fields.bin' % code] + ([] if only else ['%s.anmbin' % code,
                                                                                           '%s.mvl' % code])
        man['fighters'][code] = {'id': 0, 'name': code, 'motbin_only': only, 'files': {n: 4 for n in names}}
        files.update((n, b'1234') for n in names)
    for name, data in files.items():
        write(os.path.join(folder, name), data)
    write(os.path.join(folder, dump8.MANIFEST), json.dumps(man).encode())


# ---------------------------------------------------------------- the build the helper knows

class KnownBuild(unittest.TestCase):
    def test_the_helpers_functions(self):
        with open(os.path.join(HERE, '..', 't8helper', 't8helper.c'), encoding='utf-8') as f:
            c = f.read()
        found = {name: (int(address, 16), int(n), int(h, 16)) for name, address, n, h in re.findall(
            r'static const struct Function (\w+) = \{(0x[0-9a-fA-F]+)ull, (\d+), (0x[0-9a-fA-F]+)ull\};', c)}
        self.assertEqual(tuple(found[name] for name in ('ALLOCATE', 'REQUEST_FILE', 'PROTECT_FIELDS', 'READ_FIELD')),
                         dump8.HELPER_FUNCTIONS)
        self.assertIn('#define PREFERRED_BASE 0x%xull' % dump8.PREFERRED_BASE, c)
        self.assertIn('"error %s\\n"' % dump8.REFUSED, c)

    def test_exe_read_as_the_helper_checks_the_game(self):
        code = {dump8.PREFERRED_BASE + 0x1010: bytes(range(16)), dump8.PREFERRED_BASE + 0x2000: b'\x48\x89' * 8}
        table = tuple((address, 16, fnv1a(data)) for address, data in code.items())
        with tempfile.TemporaryDirectory() as game, mock.patch.object(dump8, 'HELPER_FUNCTIONS', table):
            path = os.path.join(game, dump8.EXE)
            self.assertFalse(dump8.known_build(game))                           # (no exe)
            write(path, exe(code))
            self.assertTrue(dump8.known_build(game))
            write(path, exe({**code, dump8.PREFERRED_BASE + 0x2000: b'\x90'}))
            self.assertFalse(dump8.known_build(game))                           # (another build)
            write(path, exe(code)[:0x1100])
            self.assertFalse(dump8.known_build(game))                           # (cut off)
            write(path, b'ZM' + exe(code)[2:])
            self.assertFalse(dump8.known_build(game))
            with mock.patch.object(dump8, 'HELPER_FUNCTIONS', table + ((dump8.PREFERRED_BASE + 0x9000, 16, 0),)):
                write(path, exe(code))
                self.assertFalse(dump8.known_build(game))                       # (outside the sections)


# ---------------------------------------------------------------- dumps that fail, updates

class Redump(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = os.path.join(self.tmp.name, 'TEKKEN 8')
        write(os.path.join(self.game, dump8.EXE), b'MZ')
        self.t8 = dump8.Tekken8('steam', self.tmp.name, self.game, 'prefix', 'proton')
        self.out = os.path.join(self.tmp.name, 'movesets')
        FakeSession.started = []
        self.patches = [mock.patch.object(dump8, 'find_tekken8', return_value=self.t8),
                        mock.patch.object(dump8, 'tekken8_running', return_value=False),
                        mock.patch.object(dump8, 'build_helper', return_value='t8helper.exe'),
                        mock.patch.object(dump8, 'known_build', return_value=True),
                        mock.patch.object(dump8, 'Session', FakeSession)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def dump(self, fighters, references=(), files=None, moves=3, leave_out=(), **kw):
        """A dump with the game handing over `files` (game_files of the fighters and references) but `leave_out`."""
        made, tables = game_files(*dict.fromkeys(list(fighters) + list(references)), moves=moves)
        for path in leave_out:
            del made[path]
        FakeSession.helper = h = FakeHelper(made, tables)
        with mock.patch.object(dump8, 'steam_running', return_value=True), \
                mock.patch.object(dump8, 'owned_dlc', return_value={}):
            saved, skipped = dump8.dump(fighters, self.out, log=lambda *a: None, cache=self.tmp.name,
                                        references=references, **kw)
        return saved, skipped, h

    def update(self):
        """A game update: another exe."""
        path = os.path.join(self.game, dump8.EXE)
        write(path, b'MZ' + bytes(os.path.getsize(path)))

    def files(self):
        out = {}
        for name in sorted(os.listdir(self.out)):
            with open(os.path.join(self.out, name), 'rb') as f:
                out[name] = f.read()
        return out

    def manifest(self):
        with open(os.path.join(self.out, dump8.MANIFEST)) as f:
            return json.load(f)

    def test_a_failed_dump_keeps_the_files_saved_before(self):
        self.dump([REINA], [KAZUYA])
        before = self.files()
        _, skipped, _ = self.dump([REINA], [KAZUYA], moves=5, force=True,
                                  leave_out=['Binary/mothead/movelist/zbr.mvl'])
        self.assertEqual(skipped, {REINA: 'Tekken 8 did not read Binary/mothead/movelist/zbr.mvl'})
        now = self.files()
        self.assertEqual({n: d for n, d in now.items() if n.startswith('zbr') or n == 'com.anmbin'},
                         {n: d for n, d in before.items() if n.startswith('zbr') or n == 'com.anmbin'})
        self.assertNotEqual(now['grl.motbin'], before['grl.motbin'])                  # (the reference, saved again)
        self.assertTrue(dump8.whole(dump8.saved_files('zbr', self.out, dump8.game_version(self.game, self.tmp.name))))
        self.assertFalse([n for n in now if n.endswith(dump8.NEW_SUFFIX) or n.endswith('.part')])

    def test_after_an_update_her_moveset_saved_before_is_used(self):
        self.dump([REINA], [KAZUYA])
        hers = {n: d for n, d in self.files().items() if n.startswith('zbr') or n == 'com.anmbin'}
        self.update()
        version = dump8.game_version(self.game, self.tmp.name)
        _, skipped, _ = self.dump([REINA], [KAZUYA, JIN], moves=5, leave_out=['Binary/mothead/movelist/zbr.mvl'])
        self.assertEqual(list(skipped), [REINA])
        m = self.manifest()
        self.assertEqual((m['game'], sorted(m['fighters']), sorted(m['before']['fighters'])),
                         (version, ['ant', 'grl'], ['zbr']))                  # (Kazuya's: this version's now)
        self.assertEqual(m['before']['common'], {'com.anmbin': len(hers['com.anmbin'])})
        self.assertEqual({n: d for n, d in self.files().items() if n in hers}, hers)  # (hers, as they were)
        self.assertIsNone(dump8.saved_files('zbr', self.out, version))              # (not for this version)
        files = dump8.saved_files('zbr', self.out)
        self.assertTrue(dump8.whole(files))
        self.assertEqual(dump8.saved_codes(self.out), ['ant', 'grl', 'zbr'])
        self.assertEqual(dump8.saved_files('grl', self.out), dump8.saved_files('grl', self.out, version))
        with mock.patch('ttt2char.tekken8.motbin.read', return_value='her moveset'):
            (k, found, references), why = importer.tekken8_moveset(definition('reina'), self.out)
        self.assertEqual((k, found, [r[0] for r in references]), ('her moveset', files, ['ant', 'grl']))
        self.assertEqual(dump8.saved_files('grl', self.out, version)['motbin'], os.path.join(self.out, 'grl.motbin'))

        # (a second update: what is still there of both is kept)
        self.update()
        m = dump8.read_manifest(self.out, dump8.game_version(self.game, self.tmp.name))
        self.assertEqual((m['fighters'], sorted(m['before']['fighters'])), ({}, ['ant', 'grl', 'zbr']))
        self.assertEqual(m['before']['common'], {'com.anmbin': len(hers['com.anmbin'])})

        # (saved for this version at last: what was kept from before goes)
        self.dump([REINA], [KAZUYA, JIN])
        m = self.manifest()
        self.assertEqual((sorted(m['fighters']), m['before']), (['ant', 'grl', 'zbr'], {'fighters': {}, 'common': {}}))
        self.assertTrue(dump8.whole(dump8.saved_files('zbr', self.out, m['game'])))

    def test_the_shared_bank_not_saved_keeps_hers(self):
        self.dump([REINA])
        hers = self.files()
        self.update()
        _, skipped, _ = self.dump([REINA], moves=5, leave_out=['Binary/mothead/bin/com.anmbin'])
        self.assertEqual(skipped, {REINA: 'the shared animations could not be saved: Tekken 8 did not read '
                                          'Binary/mothead/bin/com.anmbin'})
        self.assertEqual({n: d for n, d in self.files().items() if n != dump8.MANIFEST},
                         {n: d for n, d in hers.items() if n != dump8.MANIFEST})
        self.assertTrue(dump8.whole(dump8.saved_files('zbr', self.out)))

    def test_a_second_fighter_keeps_hers(self):
        self.dump([REINA])
        others = [fid for fid in dump8.ROSTER if fid != KAZUYA]
        _, _, h = self.dump([KAZUYA], others)                   # (as import_character.py saves another fighter)
        self.assertFalse([p for p in h.asked if '/zbr.' in p])
        self.assertFalse(self.manifest()['fighters']['zbr']['motbin_only'])
        self.assertTrue(dump8.whole(dump8.saved_files('zbr', self.out)))
        # (after an update: saved whole again, not as a reference alone)
        self.update()
        _, skipped, h = self.dump([KAZUYA], [REINA, JIN], moves=5)
        self.assertEqual(skipped, {})
        self.assertIn('Binary/mothead/bin/zbr.anmbin', h.asked)
        self.assertFalse(self.manifest()['fighters']['zbr']['motbin_only'])
        self.assertTrue(dump8.whole(dump8.saved_files('zbr', self.out, self.manifest()['game'])))
        # (a reference saved whole is not saved again as its motbin alone, also with force)
        todo, _, _ = dump8.plan([], [REINA, JIN], dump8.read_manifest(self.out, self.manifest()['game']), self.out,
                                force=True)
        self.assertEqual(todo, [(REINA, False), (JIN, True)])

    def test_a_build_the_helper_does_not_know_starts_nothing(self):
        with mock.patch.object(dump8, 'known_build', return_value=False), \
                mock.patch.object(dump8, 'steam_running') as running:
            with self.assertRaisesRegex(dump8.DumpError, 'not the one the helper knows'):
                dump8.dump([REINA], self.out, log=lambda *a: None, cache=self.tmp.name)
        self.assertEqual(FakeSession.started, [])
        running.assert_not_called()

    def test_a_refused_attach_is_not_waited_for(self):
        class Refusing(FakeHelper):
            attached = 0

            def attach(self):
                Refusing.attached += 1
                raise dump8.DumpError(dump8.REFUSED)
        FakeSession.helper = Refusing(*game_files(REINA))
        with mock.patch.object(dump8, 'steam_running', return_value=True), \
                mock.patch.object(dump8, 'ATTACH_TIMEOUT', 3):
            with self.assertRaisesRegex(dump8.DumpError, 'not the one the helper knows'):
                dump8.dump([REINA], self.out, log=lambda *a: None, cache=self.tmp.name)
        self.assertEqual(Refusing.attached, 1)


class Manifest(unittest.TestCase):
    def test_before_is_what_is_still_there(self):
        with tempfile.TemporaryDirectory() as folder:
            write_saved(folder, {'zbr': False, 'grl': True}, {'build': '1'})
            self.assertEqual(dump8.read_manifest(folder, {'build': '1'})['before'], {'fighters': {}, 'common': {}})
            os.remove(os.path.join(folder, 'grl.motbin'))
            m = dump8.read_manifest(folder, {'build': '2'})
            self.assertEqual((m['fighters'], m['common'], list(m['before']['fighters'])), ({}, {}, ['zbr']))
            self.assertEqual(m['before']['common'], {'com.anmbin': 3})
            self.assertTrue(dump8.whole(dump8.saved_files('zbr', folder)))
            self.assertIsNone(dump8.saved_files('grl', folder))
            write(os.path.join(folder, 'com.anmbin'), b'other')                 # (not what she was saved with)
            self.assertEqual(dump8.read_manifest(folder, {'build': '2'})['before']['common'], {})
            self.assertIsNone(dump8.saved_files('zbr', folder))
            write(os.path.join(folder, dump8.MANIFEST), json.dumps({'game': {}, 'fighters': [], 'before': 7}).encode())
            self.assertEqual((dump8.saved_codes(folder), dump8.saved_files('zbr', folder)), ([], None))


# ---------------------------------------------------------------- import_character.py

class Ready(unittest.TestCase):
    """tekken8_ready: what is saved for this version, whole, is not saved again; a motbin alone is; nothing runs for a
    build the helper does not know."""

    def ready(self, folder, known=True):
        t8 = types.SimpleNamespace(game='/games/TEKKEN 8', library='/lib')
        with mock.patch.object(dump8, 'find_tekken8', return_value=t8), \
                mock.patch.object(dump8, 'game_version', return_value={'build': '1'}), \
                mock.patch.object(dump8, 'known_build', return_value=known) as checked, \
                mock.patch.object(dump8, 'dump', return_value=({}, {})) as run, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            import_character.tekken8_ready(['reina'], folder, import_character.Progress(False))
        return run, checked, out.getvalue()

    def test_her_motbin_alone_is_no_moveset_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            write_saved(folder, {'zbr': True}, {'build': '1'})
            run, _, _ = self.ready(folder)
            self.assertEqual(run.call_args[0], ([REINA], folder))
            write_saved(folder, {'zbr': False}, {'build': '1'})
            run, checked, _ = self.ready(folder)
            run.assert_not_called()
            checked.assert_not_called()                     # (nothing to save: the exe is not even read)

    def test_unknown_build(self):
        with tempfile.TemporaryDirectory() as folder:
            run, _, out = self.ready(folder, known=False)
        run.assert_not_called()
        self.assertIn('Tekken 8 cannot run to save movesets (this Tekken 8 build (Steam build 1, a game update) is '
                      'not the one the helper knows', out)


class OnlyTekken8(unittest.TestCase):
    """--all with Tekken 8 there and no Tekken 7: its fighters are skipped, Reina is imported (as the other way
    round)."""

    def add(self, folder, fighters):
        runs = []
        args = mock.Mock(tekken7=None, tekken8=None, movesets=None, files=None, game='g', out=folder, no_shared=False,
                         tekken8_movesets=None, all=True, remove=False)

        def run(name, t7, movesets, game, out, make_shared=True, files=None, tekken8=None):
            runs.append(name)
            return pack.write(folder, definition(name), {'.nud': b'nud'}, 0)
        with mock.patch.object(import_character, 'needs_packages'), \
                mock.patch.object(dump7, 'tekken7_library', side_effect=dump7.DumpError('Tekken 7 is not installed in '
                                                                                      'any Steam library')), \
                mock.patch.object(importer, 'tekken8_folder', side_effect=lambda f: '/games/TEKKEN 8'), \
                mock.patch.object(import_character, 'tekken7_ready', side_effect=AssertionError('Tekken 7 asked')), \
                mock.patch.object(import_character, 'tekken8_ready'), \
                mock.patch.object(importer, 'run', side_effect=run), \
                mock.patch.object(importer, 'make_shared') as shared, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            import_character.add(args, list(fighters), import_character.Progress(True))
        return runs, shared, out.getvalue()

    def test_all(self):
        args = mock.Mock(remove=False, tekken8=None)
        with mock.patch.object(source, 'find_tekken8', return_value='/games/TEKKEN 8'):
            everyone = import_character.everyone(args)
        self.assertEqual(everyone, list(CHARACTERS))
        with tempfile.TemporaryDirectory() as d:
            runs, shared, out = self.add(d, everyone)
        self.assertEqual(runs, ['reina'])
        self.assertEqual(shared.call_args[0][0], None)                      # (no Tekken 7 for what the packs share)
        t7 = [f for f in CHARACTERS if game_of(definition(f)) == 'tekken7']
        self.assertEqual([line for line in out.splitlines() if line.startswith('@skipped')],
                         ['@skipped %s Tekken 7 is not installed' % f for f in t7])
        self.assertIn('@added reina', out)

    def test_tekken7_fighters_alone_need_tekken7(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as caught:
                self.add(d, ['kazumi'])
        self.assertIn('give --tekken7', str(caught.exception.code))


# ---------------------------------------------------------------- the stand-in's pack, the launcher

class StandInPack(unittest.TestCase):
    def test_marked(self):
        d = definition('reina')
        self.assertIn('revision = %d\nstand_in = hei\n' % pack.revision(d),
                      pack.character_ini(importer.with_stand_in(d), 4))
        self.assertNotIn('stand_in', pack.character_ini(d, 4))
        self.assertNotIn('stand_in', pack.character_ini(definition('kazumi'), 4))
        with tempfile.TemporaryDirectory() as folder:
            pack.write(folder, importer.with_stand_in(d), {'.nud': b'nud'}, 0)
            pack.write(folder, definition('kazumi'), {'.nud': b'nud'}, 1)
            self.assertEqual({p['code']: p['stand_in'] for p in pack.installed(folder)}, {'rei': 'hei', 'kzm': ''})


class LauncherStatus(unittest.TestCase):
    """Her pack fighting with the stand-in's moveset: "update" once her own can be had (saved, or Tekken 8 a build
    the helper knows); "moveset_saved": her own saved whole."""

    def status(self, stand_in=True, saved=None, tekken8=False, known=False):
        with tempfile.TemporaryDirectory() as d:
            packs, movesets8, game = (os.path.join(d, n) for n in ('packs', 'movesets8', 'TEKKEN 8'))
            r = definition('reina')
            pack.write(packs, importer.with_stand_in(r) if stand_in else r, {'.nud': b'nud'}, 0)
            if saved is not None:
                write_saved(movesets8, {'zbr': saved}, {'build': 'old'})
            os.makedirs(os.path.join(game, 'Polaris', 'Content', 'Paks'))
            with mock.patch.dict(os.environ, HOME=d, TTT2_CHARACTERS=packs), \
                    mock.patch.object(source, 'find_tekken8', return_value=game if tekken8 else None), \
                    mock.patch.object(dump8, 'known_build', return_value=known) as checked:
                s = launcher.status(None, os.path.join(d, 'movesets'), movesets8)
                json.dumps(s)
        self.tekken8 = s['tekken8']
        f = {f['name']: f for f in s['fighters']}['reina']
        return (f['stand_in'], f['update'], f['moveset_saved']), checked

    def test_update_once_her_moveset_can_be_had(self):
        self.assertEqual(self.status()[0], (True, False, False))
        self.assertEqual(self.status(saved=True)[0], (True, False, False))        # (a reference's motbin alone)
        self.assertEqual(self.status(saved=False)[0], (True, True, True))         # (another version's: it is used)
        self.assertEqual(self.status(tekken8=True)[0], (True, False, False))      # (a build the helper refuses)
        got, checked = self.status(tekken8=True, known=True)
        self.assertEqual(got, (True, True, False))                                # (Steam running saves it)
        self.assertEqual(checked.call_count, 1)

    def test_build_known_while_her_moveset_is_to_be_saved(self):
        """tekken8.build_known: the exe read only while a fighter's own moveset is not saved (to add her with it)."""
        for stand_in, saved, known, want in ((False, None, True, True), (False, None, False, False),
                                             (True, None, False, False), (False, False, True, None)):
            self.status(stand_in=stand_in, saved=saved, tekken8=True, known=known)
            self.assertEqual(self.tekken8['build_known'], want)
        self.status(tekken8=False)
        self.assertIsNone(self.tekken8['build_known'])                 # (no Tekken 8: nothing to tell)

    def test_her_own_pack(self):
        got, checked = self.status(stand_in=False, saved=False, tekken8=True, known=True)
        self.assertEqual(got, (False, False, True))
        checked.assert_not_called()


# ---------------------------------------------------------------- the package

class Package(unittest.TestCase):
    def test_every_module_named(self):
        from ttt2char import tekken8
        folder = os.path.dirname(tekken8.__file__)
        modules = {n for n in os.listdir(folder) if n.endswith(('.py', '.c')) and n != '__init__.py'}
        named = set(re.findall(r'^ {4}(\w+\.(?:py|c)) ', tekken8.__doc__, re.M))
        self.assertEqual(named, modules)


if __name__ == '__main__':
    unittest.main()
