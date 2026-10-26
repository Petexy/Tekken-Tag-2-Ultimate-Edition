"""Tekken 8's background dumper (tekken8/autodump.py) and its command line (dump_tekken8.py), with the game, Steam
and the helper made up: the roster, the files' names, what is read again, the checks of what the game hands over,
the helper's protocol.

    python3 -m unittest discover tools/characters/tests
"""
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import dump_tekken8                                   # noqa: E402
from ttt2char.tekken8 import autodump                 # noqa: E402

REINA, KAZUYA, JIN, EDDY = 28, 8, 6, 33


def write(path, data=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


# ---------------------------------------------------------------- made-up files in the layouts the dumper checks

def motbin(fid, moves=3, magic=b'TEK\0'):
    """A motbin in its file form: the header, then the moves table at MOTBIN_BASE + 0x40."""
    head = bytearray(autodump.MOTBIN_BASE)
    head[8:12] = magic
    struct.pack_into('<I', head, autodump.MOTBIN_ROSTER, fid * autodump.ROSTER_STEP + 1)
    struct.pack_into('<QQ', head, autodump.MOTBIN_MOVES, 0x40, moves)
    return bytes(head) + bytes(0x40 + moves * autodump.MOVE_SIZE)


def fields(fid, moves=3, roster=None):
    """The helper's table: per move the six fields, +0xd0 the roster value."""
    value = fid * autodump.ROSTER_STEP + 1 if roster is None else roster
    return b''.join(struct.pack('<6I', 0x1000 + i, 0x2000 + i, 2114, 0, value, 0x3000 + i) for i in range(moves))


def anmbin(entries=2):
    head = bytearray(autodump.ANMBIN_HEAD)
    struct.pack_into('<6I', head, 4, entries, 0, 0, 0, 0, 0)
    struct.pack_into('<6Q', head, 0x38, autodump.ANMBIN_HEAD, 0, 0, 0, 0, 0)
    return bytes(head) + bytes(entries * autodump.ANMBIN_ENTRY)


MVL = b'MVLT\x05\x00\x06\x00' + bytes(8)


class FakeHelper:
    """The helper's answers (save, protected) from made-up files, keeping what was asked."""

    def __init__(self, files=None, tables=None):
        self.files = files or {}
        self.tables = tables or {}
        self.asked = []

    def attach(self):
        return 'ok'

    def ready(self):
        return True

    def save(self, paths, targets):
        out = []
        for path, target in zip(paths, targets):
            self.asked.append(path)
            data = self.files.get(path)
            if data is not None:
                write(target, data)
            out.append(None if data is None else len(data))
        return out

    def protected(self, path):
        moves, table = self.tables[path]
        return moves, autodump.MOVE_SIZE, 0x40, table


def game_files(*fids, moves=3):
    """FakeHelper's files and tables for the fighters (and the shared bank)."""
    files, tables = {autodump.common_paths()[0][0]: anmbin(5)}, {}
    for fid in fids:
        code = autodump.ROSTER[fid][0]
        (mot, _), (anm, _), (mvl, _) = autodump.archive_paths(code)
        files.update({mot: motbin(fid, moves), anm: anmbin(), mvl: MVL})
        tables[mot] = (moves, fields(fid, moves))
    return files, tables


# ---------------------------------------------------------------- the roster and the files' names

class Roster(unittest.TestCase):
    def test_words_name_fighters(self):
        for word in ('Reina', 'reina', ' REINA ', 'zbr', '28'):
            self.assertEqual(autodump.fighter_id(word), REINA, word)
        self.assertEqual(autodump.fighter_id('armor king'), 39)
        self.assertEqual(autodump.fighter_id('Armor_King'), 39)
        self.assertEqual(autodump.fighter_id('jack8'), 10)
        self.assertEqual(autodump.fighter_id('Devil-Jin'), 12)
        self.assertEqual(autodump.fighter_id('grl'), KAZUYA)

    def test_unknown_words(self):
        for word in ('', 'nobody', '32', '43', '999', 'jack'):
            self.assertIsNone(autodump.fighter_id(word), word)

    def test_table(self):
        codes = [code for code, _ in autodump.ROSTER.values()]
        self.assertEqual(len(set(codes)), len(codes))
        self.assertTrue(all(len(c) == 3 and c.isalpha() and c.islower() for c in codes))
        self.assertNotIn(autodump.COMMON, codes)
        self.assertTrue(set(autodump.DLC) <= set(autodump.ROSTER))
        base = [fid for fid in autodump.ROSTER if fid not in autodump.DLC]
        self.assertEqual(base, list(range(32)))             # (the base game's 32 fighters always are owned)
        self.assertEqual(len(set(autodump.DLC.values())), len(autodump.DLC))
        self.assertEqual(autodump.ROSTER[REINA], ('zbr', 'Reina'))

    def test_file_names(self):
        self.assertEqual(autodump.archive_paths('zbr'), [('Binary/mothead/bin/zbr.motbin', 'zbr.motbin'),
                                                         ('Binary/mothead/bin/zbr.anmbin', 'zbr.anmbin'),
                                                         ('Binary/mothead/movelist/zbr.mvl', 'zbr.mvl')])
        self.assertEqual(autodump.archive_paths('grl', motbin_only=True),
                         [('Binary/mothead/bin/grl.motbin', 'grl.motbin')])
        self.assertEqual(autodump.common_paths(), [('Binary/mothead/bin/com.anmbin', 'com.anmbin')])


# ---------------------------------------------------------------- the checks of what the game hands over

class Checks(unittest.TestCase):
    def test_motbin(self):
        data = motbin(REINA)
        self.assertEqual(autodump.check_motbin(data), 1834981)            # (28 x 0xFFFF + 1)
        self.assertEqual(autodump.motbin_roster_id(1834981), REINA)
        self.assertEqual(autodump.motbin_roster_id(1), 0)
        self.assertIsNone(autodump.motbin_roster_id(0))
        self.assertIsNone(autodump.motbin_roster_id(1834982))
        for bad in (motbin(REINA, magic=b'TEX\0'), data[:0x100], b'\0\0\1' + data[3:]):
            with self.assertRaisesRegex(autodump.DumpError, 'not a moveset'):
                autodump.check_motbin(bad)

    def test_fields(self):
        data = motbin(REINA, moves=4)
        autodump.check_fields(data, 4, autodump.MOVE_SIZE, 0x40, fields(REINA, 4))
        mixed = fields(REINA, 2) + fields(KAZUYA, 1)                      # (a borrowed move or so: most do)
        autodump.check_fields(motbin(REINA), 3, autodump.MOVE_SIZE, 0x40, mixed)
        with self.assertRaisesRegex(autodump.DumpError, 'not the moveset'):
            autodump.check_fields(data, 3, autodump.MOVE_SIZE, 0x40, fields(REINA, 3))
        with self.assertRaisesRegex(autodump.DumpError, 'not the moveset'):
            autodump.check_fields(data, 4, autodump.MOVE_SIZE, 0x48, fields(REINA, 4))
        with self.assertRaisesRegex(autodump.DumpError, 'not the moveset'):
            autodump.check_fields(data, 4, autodump.MOVE_SIZE, 0x40, fields(REINA, 4)[:-4])
        with self.assertRaisesRegex(autodump.DumpError, 'plain values'):    # (still the game's own form)
            autodump.check_fields(data, 4, autodump.MOVE_SIZE, 0x40, fields(REINA, 4, roster=0x5a5a5a5a))

    def test_anmbin_and_mvl(self):
        data = anmbin(3)
        autodump.check_anmbin(data, len(data))
        for head, size in ((data, len(data) - 1), (bytes(autodump.ANMBIN_HEAD), 0x1000), (data[:0x40], len(data))):
            with self.assertRaisesRegex(autodump.DumpError, 'animation bank'):
                autodump.check_anmbin(head, size)
        autodump.check_mvl(MVL)
        with self.assertRaisesRegex(autodump.DumpError, 'command list'):
            autodump.check_mvl(b'TEK\0')


# ---------------------------------------------------------------- finding the game, its version, the helper

class Game(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.steam, self.lib = os.path.join(d, 'Steam'), os.path.join(d, 'Library')
        self.proton = os.path.join(self.steam, 'steamapps', 'common', 'Proton - Experimental')
        write(os.path.join(self.proton, 'proton'))
        write(os.path.join(self.steam, 'steamapps', 'libraryfolders.vdf'),
              ('"libraryfolders"\n{\n "0"\n {\n  "path"  "%s"\n }\n "1"\n {\n  "path"  "%s"\n }\n}\n'
               % (self.steam, self.lib)).encode())
        write(os.path.join(self.lib, 'steamapps', 'appmanifest_1778820.acf'),
              b'"AppState"\n{\n "appid" "1778820"\n "installdir" "TEKKEN 8"\n "buildid" "25221600"\n}\n')
        self.game = os.path.join(self.lib, 'steamapps', 'common', 'TEKKEN 8')
        write(os.path.join(self.game, autodump.EXE), b'MZ' * 50)
        self.prefix = os.path.join(self.lib, 'steamapps', 'compatdata', '1778820')
        os.makedirs(os.path.join(self.prefix, 'pfx'))
        write(os.path.join(self.prefix, 'config_info'),
              ('11.0-100\n%s/files/share/fonts/\n%s/files/lib/\n' % (self.proton, self.proton)).encode())

    def tearDown(self):
        self.tmp.cleanup()

    def test_found_through_steams_files(self):
        with mock.patch.object(autodump, 'steams', return_value=[(self.steam, None)]):
            t8 = autodump.find_tekken8()
            self.assertEqual(autodump.tekken8_library(), (self.steam, self.lib, self.game))
        prefix, proton = (self.game, 'Windows') if os.name == 'nt' else (self.prefix, self.proton)
        self.assertEqual((t8.game, t8.prefix, t8.proton, t8.library), (self.game, prefix, proton, self.lib))

    def test_not_usable(self):
        if os.name == 'nt':
            os.remove(os.path.join(self.game, autodump.EXE))
            with mock.patch.object(autodump, 'steams', return_value=[(self.steam, None)]):
                with self.assertRaisesRegex(autodump.DumpError, 'shipping executable is missing'):
                    autodump.find_tekken8()
            return
        with mock.patch.object(autodump, 'steams', return_value=[(self.steam, 'flatpak')]):
            with self.assertRaisesRegex(autodump.DumpError, 'Flatpak'):
                autodump.find_tekken8()
        os.remove(os.path.join(self.prefix, 'config_info'))
        with mock.patch.object(autodump, 'steams', return_value=[(self.steam, None)]):
            with self.assertRaisesRegex(autodump.DumpError, 'start it once'):
                autodump.find_tekken8()
        with mock.patch.object(autodump, 'steams', return_value=[]):
            with self.assertRaisesRegex(autodump.DumpError, 'not installed'):
                autodump.find_tekken8()

    def test_version(self):
        v = autodump.game_version(self.game, self.lib)
        self.assertEqual((v['build'], v['exe_size']), ('25221600', 100))
        self.assertEqual(autodump.game_version(self.game)['build'], None)
        with self.assertRaisesRegex(autodump.DumpError, 'verify'):
            autodump.game_version(self.lib, self.lib)

    def test_helper_built_once(self):
        cache = os.path.join(self.tmp.name, 'cache')
        exe = os.path.join(self.tmp.name, 'prebuilt.exe')
        write(exe)
        with mock.patch.dict(os.environ, TTT2_T8HELPER=exe):
            self.assertEqual(autodump.build_helper(cache), exe)
        with mock.patch.dict(os.environ, TTT2_T8HELPER=''), \
                mock.patch.object(autodump.shutil, 'which', return_value=None):
            self.assertIsNone(autodump.ready_helper(cache))
            with self.assertRaisesRegex(autodump.DumpError, 'CLANG64' if os.name == 'nt' else 'MinGW'):
                autodump.build_helper(cache)
            write(os.path.join(cache, 't8helper.exe'))                    # (newer than its source: no MinGW)
            self.assertEqual(autodump.build_helper(cache), os.path.join(cache, 't8helper.exe'))
            os.utime(os.path.join(cache, 't8helper.exe'), (0, 0))         # (older: built again)
            self.assertIsNone(autodump.ready_helper(cache))

    @unittest.skipIf(os.name == 'nt', 'Linux file lock; Windows sessions use a named mutex')
    def test_one_session_at_a_time(self):
        lock = os.path.join(self.tmp.name, 'session.lock')
        first = autodump._lock(lock)
        with self.assertRaisesRegex(autodump.DumpError, 'Tekken 8 is busy'):
            autodump._lock(lock, timeout=0)
        first.close()
        autodump._lock(lock, timeout=0).close()
        self.assertIn('ttt2-tekken8-', autodump._lock_path(self.prefix))

    def test_the_sessions_game_by_either_name(self):
        """The hidden session finds its game by its process name, which the game changes to its main thread's within
        a second of its start (a poll every half second could miss the first): either name, with the session's tag."""
        either = '[ "$c" = "%s" ] || [ "$c" = "%s" ]' % (autodump.GAME_COMM, autodump.GAME_THREAD)
        self.assertIn(either, autodump.INSIDE)
        self.assertIn('"%s=$%s"' % (autodump.SESSION_TAG, autodump.SESSION_TAG), autodump.INSIDE)

    def test_players_and_sessions(self):
        ours = {'SteamAppId': '1778820', autodump.SESSION_TAG: '1.2.3', 'STEAM_COMPAT_DATA_PATH': self.prefix}
        processes = {900001: ('Polaris-Win64-S', {}), 900002: ('wine64', {'STEAM_COMPAT_DATA_PATH': self.prefix}),
                     900003: ('Polaris-Win64-S', ours), 900004: ('TekkenGame-Win6', {'SteamAppId': '389730'})}
        self.assertEqual(autodump._players(self.prefix, processes), [900001, 900002])
        self.assertEqual(autodump._tagged(self.prefix, processes), {'1.2.3': [900003]})


# ---------------------------------------------------------------- what is saved, what is read again

class Saved(unittest.TestCase):
    VERSION = {'build': '1', 'exe_size': 10, 'exe_mtime': 20}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, code, names, motbin_only=False, common=True):
        m = autodump.read_manifest(self.out, self.VERSION)
        files = {}
        for name in names:
            write(os.path.join(self.out, name), b'1234')
            files[name] = 4
        m['fighters'][code] = {'id': autodump.fighter_id(code), 'name': code, 'motbin_only': motbin_only,
                               'files': files}
        if common:
            write(os.path.join(self.out, 'com.anmbin'), b'12')
            m['common'] = {'com.anmbin': 2}
        autodump.write_manifest(self.out, m)
        return m

    def test_saved_files(self):
        self.save('zbr', ['zbr.motbin', 'zbr.motbin.fields.bin', 'zbr.anmbin', 'zbr.mvl'])
        self.save('grl', ['grl.motbin', 'grl.motbin.fields.bin'], motbin_only=True)
        got = autodump.saved_files('zbr', self.out, self.VERSION)
        self.assertEqual(sorted(got), ['anmbin', 'common', 'fields', 'motbin', 'mvl'])
        self.assertEqual(got['fields'], os.path.join(self.out, 'zbr.motbin.fields.bin'))
        self.assertEqual(sorted(autodump.saved_files('grl', self.out)), ['fields', 'motbin'])
        self.assertIsNone(autodump.saved_files('ant', self.out))
        self.assertIsNone(autodump.saved_files('zbr', self.out, dict(self.VERSION, build='2')))   # (an update)
        write(os.path.join(self.out, 'zbr.mvl'), b'123')                   # (not what was saved)
        self.assertIsNone(autodump.saved_files('zbr', self.out))

    def test_update_forgets_all(self):
        self.save('zbr', ['zbr.motbin'])
        self.assertIn('zbr', autodump.read_manifest(self.out, self.VERSION)['fighters'])
        m = autodump.read_manifest(self.out, dict(self.VERSION, exe_mtime=21))
        self.assertEqual(m['fighters'], {})
        self.assertEqual(m['common'], {})
        write(os.path.join(self.out, autodump.MANIFEST), b'{not json')
        self.assertEqual(autodump.read_manifest(self.out, self.VERSION)['fighters'], {})

    def test_plan(self):
        m = self.save('grl', ['grl.motbin', 'grl.motbin.fields.bin'], motbin_only=True, common=False)
        todo, common, skipped = autodump.plan([REINA, KAZUYA, REINA], [JIN, KAZUYA, 32], m, self.out)
        self.assertEqual(todo, [(REINA, False), (KAZUYA, False), (JIN, True)])   # (Kazuya whole now)
        self.assertTrue(common)
        self.assertEqual(list(skipped), [32])
        todo, common, _ = autodump.plan([], [KAZUYA, JIN], m, self.out)
        self.assertEqual((todo, common), ([(JIN, True)], False))         # (a reference needs no shared bank)
        m = self.save('zbr', ['zbr.motbin', 'zbr.anmbin'])
        self.assertEqual(autodump.plan([REINA], [KAZUYA], m, self.out), ([], False, {}))
        self.assertEqual(autodump.plan([REINA], [], m, self.out, force=True), ([(REINA, False)], True, {}))
        os.remove(os.path.join(self.out, 'com.anmbin'))
        self.assertEqual(autodump.plan([REINA], [], m, self.out), ([], True, {}))


# ---------------------------------------------------------------- a dump, with a made-up game

class FakeSession:
    started = []

    def __init__(self, t8, helper_exe, run, with_game):
        FakeSession.started.append(with_game)

    def wait_game(self):
        return 1

    def connect(self):
        return FakeSession.helper

    def close(self):
        pass


class Dump(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game = os.path.join(self.tmp.name, 'TEKKEN 8')
        write(os.path.join(game, autodump.EXE), b'MZ')
        self.t8 = autodump.Tekken8('steam', self.tmp.name, game, 'prefix', 'proton')
        self.out = os.path.join(self.tmp.name, 'movesets')
        FakeSession.started = []
        self.patches = [mock.patch.object(autodump, 'find_tekken8', return_value=self.t8),
                        mock.patch.object(autodump, 'tekken8_running', return_value=False),
                        mock.patch.object(autodump, 'build_helper', return_value='t8helper.exe'),
                        mock.patch.object(autodump, 'known_build', return_value=True),
                        mock.patch.object(autodump, 'Session', FakeSession)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def dump(self, fighters, references=(), owned=(), steam=True, **kw):
        with mock.patch.object(autodump, 'steam_running', return_value=steam) as running, \
                mock.patch.object(autodump, 'owned_dlc', return_value={a: a in owned for a in autodump.DLC.values()}):
            out = autodump.dump(fighters, self.out, log=lambda *a: None, cache=self.tmp.name,
                                references=references, **kw)
        return out, running

    def test_fighter_and_references_in_one_session(self):
        files, tables = game_files(REINA, KAZUYA, JIN)
        FakeSession.helper = h = FakeHelper(files, tables)
        (saved, skipped), _ = self.dump([REINA], [KAZUYA, JIN])
        self.assertEqual(skipped, {})
        self.assertEqual(FakeSession.started, [True])
        self.assertEqual(h.asked, ['Binary/mothead/bin/zbr.motbin', 'Binary/mothead/bin/zbr.anmbin',
                                   'Binary/mothead/movelist/zbr.mvl', 'Binary/mothead/bin/grl.motbin',
                                   'Binary/mothead/bin/ant.motbin', 'Binary/mothead/bin/com.anmbin'])
        self.assertEqual(sorted(os.listdir(self.out)), ['ant.motbin', 'ant.motbin.fields.bin', 'com.anmbin',
                                                        'grl.motbin', 'grl.motbin.fields.bin', 'manifest.json',
                                                        'zbr.anmbin', 'zbr.motbin', 'zbr.motbin.fields.bin',
                                                        'zbr.mvl'])
        self.assertEqual(sorted(saved), [JIN, KAZUYA, REINA])
        with open(os.path.join(self.out, 'zbr.motbin.fields.bin'), 'rb') as f:
            head = f.read(12)
            self.assertEqual(struct.unpack('<III', head), (3, 0x448, 0x40))
            self.assertEqual(f.read(), tables['Binary/mothead/bin/zbr.motbin'][1])
        with open(os.path.join(self.out, 'manifest.json')) as f:
            m = json.load(f)
        self.assertEqual(m['game']['build'], None)
        self.assertEqual(m['fighters']['zbr']['id'], REINA)
        self.assertFalse(m['fighters']['zbr']['motbin_only'])
        self.assertTrue(m['fighters']['grl']['motbin_only'])
        self.assertEqual(m['common'], {'com.anmbin': len(files['Binary/mothead/bin/com.anmbin'])})
        self.assertEqual(autodump.saved_files('zbr', self.out)['common'], os.path.join(self.out, 'com.anmbin'))

        # (saved: nothing read again, Steam not even asked)
        (saved, skipped), running = self.dump([REINA], [KAZUYA], steam=False)
        self.assertEqual((sorted(saved), skipped, FakeSession.started), ([KAZUYA, REINA], {}, [True]))
        running.assert_not_called()
        # (a fighter later: the shared bank stays)
        FakeSession.helper = h = FakeHelper(*game_files(KAZUYA))
        self.dump([KAZUYA])
        self.assertEqual(h.asked, [p for p, _ in autodump.archive_paths('grl')])

    def test_owned_fighters_only(self):
        FakeSession.helper = h = FakeHelper(*game_files(REINA, EDDY))
        (saved, skipped), _ = self.dump([EDDY, REINA])
        self.assertEqual(skipped, {EDDY: 'its DLC is not owned'})
        self.assertEqual(list(saved), [REINA])
        self.assertNotIn('Binary/mothead/bin/dog.motbin', h.asked)
        FakeSession.helper = h = FakeHelper(*game_files(EDDY))
        (saved, skipped), _ = self.dump([EDDY], owned={autodump.DLC[EDDY]})
        self.assertEqual((list(saved), skipped), ([EDDY], {}))
        # (the DLC unowned alone: no game started)
        FakeSession.started = []
        (saved, skipped), _ = self.dump([], [35])
        self.assertEqual((saved, skipped, FakeSession.started), ({}, {35: 'its DLC is not owned'}, []))

    def test_what_the_game_does_not_hand_over(self):
        files, tables = game_files(REINA, KAZUYA)
        files['Binary/mothead/bin/grl.motbin'] = b'\0' * 0x400                  # (not a motbin)
        del files['Binary/mothead/movelist/zbr.mvl']                            # (not read)
        FakeSession.helper = FakeHelper(files, tables)
        (saved, skipped), _ = self.dump([REINA], [KAZUYA])
        self.assertEqual(saved, {})
        self.assertEqual(skipped, {REINA: 'Tekken 8 did not read Binary/mothead/movelist/zbr.mvl',
                                   KAZUYA: 'the game handed over something that is not a moveset in its file form'})
        self.assertEqual(sorted(os.listdir(self.out)), [])                     # (no shared bank for nobody)

    def test_no_steam(self):
        with self.assertRaisesRegex(autodump.DumpError, 'Steam is not running'):
            self.dump([REINA], steam=False)


# ---------------------------------------------------------------- the helper's protocol

class Protocol(unittest.TestCase):
    """autodump.Helper against a made-up t8helper on a local socket."""

    def serve(self, answer):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        self.lines = []

        def run():
            c, _ = listener.accept()
            buf = b''
            while True:
                while b'\n' not in buf:
                    got = c.recv(4096)
                    if not got:
                        c.close()
                        return
                    buf += got
                line, buf = buf.split(b'\n', 1)
                self.lines.append(line.decode())
                if line == b'quit':
                    c.close()
                    return
                if len(self.lines) == 1:                                    # (the secret: no answer)
                    continue
                for part in answer(line.decode()):
                    c.sendall(part)
                    time.sleep(0.001)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.addCleanup(listener.close)
        return listener.getsockname()[1]

    def test_files_and_fields(self):
        big = bytes(range(256)) * 40000                                         # (more than a chunk of the socket)
        wanted = []

        def answer(line):
            if line.startswith('want '):
                wanted.append(line[5:])
                return [b'ok\n']
            if line == 'fetch':
                out = []
                for p in wanted:
                    data = {'Binary/a.motbin': big, 'Binary/b.mvl': MVL}.get(p)
                    out += [b'file 1 %d\n' % len(data), data[:1000], data[1000:]] if data else [b'file 0 0\n']
                wanted.clear()
                return out + [b'end\n']
            if line == 'protected Binary/a.motbin':
                return [b'protected 2 1096 64\n', fields(REINA, 2)]
            if line == 'protected Binary/x.motbin':
                return [b'error that motbin was not read this session\n']
            return [b'error ' + line.encode() + b'\n']

        h = autodump.Helper(self.serve(answer), 'secret', timeout=5)
        with tempfile.TemporaryDirectory() as d:
            targets = [os.path.join(d, n) for n in ('a', 'gone', 'b')]
            self.assertEqual(h.save(['Binary/a.motbin', 'Binary/gone', 'Binary/b.mvl'], targets),
                             [len(big), None, len(MVL)])
            with open(targets[0], 'rb') as f:
                self.assertEqual(f.read(), big)
            with open(targets[2], 'rb') as f:
                self.assertEqual(f.read(), MVL)
            self.assertEqual(sorted(os.listdir(d)), ['a', 'b'])
        self.assertEqual(h.protected('Binary/a.motbin'), (2, 1096, 64, fields(REINA, 2)))
        with self.assertRaisesRegex(autodump.DumpError, 'not read this session'):
            h.protected('Binary/x.motbin')
        h.quit()
        self.assertEqual(self.lines[:4], ['secret', 'want Binary/a.motbin', 'want Binary/gone', 'want Binary/b.mvl'])

    def test_dlc_attach_ready(self):
        answers = {'attach': [b'error this Tekken 8 build is not the one the helper knows\n'], 'ready': [b'1\n'],
                   'dlc Z:/g/steam_api64.dll': [b'2732280 1 TEKKEN 8 - Eddy Gordo\n',
                                                b'2891170 0 TEKKEN 8 - Lidia Sobieska\n', b'end\n']}
        h = autodump.Helper(self.serve(lambda line: answers[line]), 'secret', timeout=5)
        self.assertEqual(h.dlc('Z:/g/steam_api64.dll'), [(2732280, True, 'TEKKEN 8 - Eddy Gordo'),
                                                         (2891170, False, 'TEKKEN 8 - Lidia Sobieska')])
        with self.assertRaisesRegex(autodump.DumpError, 'not the one'):
            h.attach()
        self.assertTrue(h.ready())
        h.quit()


# ---------------------------------------------------------------- the command line

class CommandLine(unittest.TestCase):
    def run_main(self, *argv):
        with mock.patch.object(autodump, 'dump', return_value=({}, {})) as dump, \
                mock.patch('ttt2char.signals.stop_on_signals'), mock.patch('sys.stdout'):
            self.assertEqual(dump_tekken8.main(list(argv) + ['--out', '/nowhere']), 0)
        (fighters, out), kw = dump.call_args
        return fighters, kw['references'], kw['force'], out

    def test_fighters_and_references(self):
        self.assertEqual(self.run_main('Reina'), ([REINA], [], False, '/nowhere'))
        self.assertEqual(self.run_main('zbr', '--references', 'kazuya, ant,6', '--force'),
                         ([REINA], [KAZUYA, JIN, JIN], True, '/nowhere'))
        self.assertEqual(self.run_main('--motbin-only', 'grl', 'Jin', '--references', 'paul'),
                         ([], [KAZUYA, JIN, 0], False, '/nowhere'))
        fighters, references, _, _ = self.run_main('--all')
        self.assertEqual((fighters, references), (list(autodump.ROSTER), []))
        self.assertEqual(self.run_main('--all', '--motbin-only')[:2], ([], list(autodump.ROSTER)))

    def test_wrong_words(self):
        for argv in ([], ['nobody'], ['reina', '--references', 'azazel']):
            with mock.patch.object(autodump, 'dump') as dump, mock.patch('ttt2char.signals.stop_on_signals'), \
                    mock.patch('sys.stderr'):
                with self.assertRaises(SystemExit):
                    dump_tekken8.main(argv)
            dump.assert_not_called()

    def test_errors_and_skipped(self):
        with mock.patch.object(autodump, 'dump', side_effect=autodump.DumpError('Tekken 8 is running')), \
                mock.patch('ttt2char.signals.stop_on_signals'), mock.patch('sys.stderr') as err:
            self.assertEqual(dump_tekken8.main(['reina']), 1)
        self.assertIn('Tekken 8 is running', ''.join(c.args[0] for c in err.write.call_args_list))
        with mock.patch.object(autodump, 'dump', return_value=({REINA: []}, {EDDY: 'its DLC is not owned'})), \
                mock.patch('ttt2char.signals.stop_on_signals'), mock.patch('sys.stdout') as out:
            self.assertEqual(dump_tekken8.main(['reina', 'eddy']), 0)
        self.assertIn('Skipped Eddy: its DLC is not owned.', ''.join(c.args[0] for c in out.write.call_args_list))


if __name__ == '__main__':
    unittest.main()
