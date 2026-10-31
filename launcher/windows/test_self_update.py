"""The Windows launcher's own update (self_update.py), against a stand-in for
GitHub on this PC. Nothing is run that needs Windows."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
import hashlib
import io
import json
import os
import struct
import tempfile
import threading
import unittest
import zipfile

import self_update
from self_update import Cancelled, UpdateError, compare_versions, parse_release, version_in

def fake_exe(body=b'', files=True, after=b'', version='99.0.0'):
    """A 64-bit Windows program's header, then `body`, then files (of launcher `version`, when one) with their
    trailer when `files`, then `after` (files in a resource: more of the program follows)."""
    head = bytearray(0x80); head[:2] = b'MZ'; struct.pack_into('<I', head, 0x3C, 0x40)
    head[0x40:0x46] = b'PE\0\0\x64\x86'
    named = {'launcher/windows/main.py': b'some files'}
    if version: named['launcher/builder/CMakeLists.txt'] = b'set(TTT2_LAUNCHER_VERSION %s)\n' % version.encode()
    stored = b''.join(struct.pack('<I', len(p)) + p.encode() + struct.pack('<Q', len(d)) + d for p, d in named.items())
    trailer = self_update.TRAILER.pack(len(stored), len(named), hashlib.sha256(stored).digest(), self_update.MAGIC)
    return bytes(head) + body + (stored + trailer if files else b'') + after

class Release(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(compare_versions('v0.3.1', '0.3.1'), 0)
        self.assertEqual(compare_versions('0.3', '0.3.0'), 0)
        self.assertLess(compare_versions('0.3.1', '0.10.0'), 0)
        self.assertGreater(compare_versions('1.0', '0.99.9'), 0)
        self.assertIsNone(compare_versions('0.3-beta', '0.3'))
        self.assertIsNone(compare_versions('', '0.3'))
        self.assertEqual(self_update.version(), self_update.version(self_update.ROOT))
    def test_exe_of_newest_release(self):
        assets = [dict(name='Ultimate_Launcher-x86_64.AppImage', browser_download_url='https://x/a', size=5),
                  dict(name='Ultimate_Launcher-x86_64.exe', browser_download_url='https://x/e', size=7,
                       digest='sha256:' + 'A' * 64)]
        answer = parse_release(json.dumps(dict(tag_name='v0.4.0', html_url='https://x/r', assets=assets)))
        self.assertEqual((answer.release.version, answer.release.url, answer.release.size, answer.release.sha256),
                         ('0.4.0', 'https://x/e', 7, 'a' * 64))
        plain = parse_release(json.dumps(dict(tag_name='0.4', assets=[dict(name='Launcher.exe', browser_download_url='u')])))
        self.assertEqual(plain.release.asset, 'Launcher.exe')
        two = [dict(name='a.exe', browser_download_url='u'), dict(name='b.exe', browser_download_url='u')]
        self.assertIn('no Windows launcher', parse_release(json.dumps(dict(tag_name='v1', assets=two))).error)
        self.assertIn('no Windows launcher', parse_release(json.dumps(dict(tag_name='v1', assets=assets[:1]))).error)
        uploading = [dict(assets[1], state='starter')]
        self.assertIn('no Windows launcher', parse_release(json.dumps(dict(tag_name='v1', assets=uploading))).error)
    def test_github_errors(self):
        self.assertTrue(parse_release('{"message": "Not Found"}').none)
        self.assertIn('try again later', parse_release('{"message": "API rate limit exceeded for 1.2.3.4"}').error)
        self.assertIn('not named as a version', parse_release('{"tag_name": "latest"}').error)
        self.assertIn('not readable', parse_release('<html>').error)
    def test_launcher_exe_and_its_version(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'a.exe'
            exe.write_bytes(fake_exe(b'program')); self.assertTrue(self_update.is_launcher_exe(exe))
            exe.write_bytes(fake_exe(b'program', files=False)); self.assertFalse(self_update.is_launcher_exe(exe))
            exe.write_bytes(fake_exe(b'program', after=b'resources after them')); self.assertTrue(self_update.is_launcher_exe(exe))
            # (The word in the launcher's code, or files whose SHA-256 is not the trailer's: no launcher.)
            exe.write_bytes(fake_exe(self_update.MAGIC + b'code', files=False)); self.assertFalse(self_update.is_launcher_exe(exe))
            exe.write_bytes(fake_exe(b'program').replace(b'some files', b'sOme files'))
            self.assertFalse(self_update.is_launcher_exe(exe))
            exe.write_bytes(b'<html>not found</html>'); self.assertFalse(self_update.is_launcher_exe(exe))
            # (Its version as its files say, read: as its --version says it, built from them.)
            exe.write_bytes(fake_exe(b'program', after=b'resources', version='0.4.3'))
            self.assertEqual(self_update.files_version(self_update.stored_files(exe)), '0.4.3')
            self.assertEqual(self_update.stored_files(exe)['launcher/windows/main.py'], b'some files')
            exe.write_bytes(fake_exe(b'program', version=None))
            self.assertEqual(self_update.files_version(self_update.stored_files(exe)), '')
        self.assertEqual(version_in('ttt2-launcher 0.4.0\r\n'), '0.4.0')
        self.assertEqual(version_in('Python 3.13'), '')

class GitHub(BaseHTTPRequestHandler):
    """The release (`answer`) and its .exe (`files`), as GitHub gives them."""
    answer, status, files = b'', 200, {}
    def do_GET(self):
        body, status = (self.answer, self.status) if self.path == '/latest' else (self.files.get(self.path), 200)
        if body is None: body, status = b'{"message": "Not Found"}', 404
        self.send_response(status); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass

class Update(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.exe = self.folder / 'Ultimate_Launcher-x86_64.exe'; self.exe.write_bytes(fake_exe(b'old'))
        self.new = fake_exe(b'new' * 100000)
        handler = type('Handler', (GitHub,), dict(files={'/new.exe': self.new}))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler); self.handler = handler
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:%d' % self.server.server_port
        environment = mock.patch.dict(os.environ, TTT2_LAUNCHER_RELEASES=self.base + '/latest'); environment.start()
        self.addCleanup(environment.stop)
        self.lines = []
    def release(self, version='99.0.0', sha256=None, size=None, status=200):
        asset = dict(name='Ultimate_Launcher-x86_64.exe', browser_download_url=self.base + '/new.exe',
                     size=len(self.new) if size is None else size,
                     digest='sha256:' + (sha256 or hashlib.sha256(self.new).hexdigest()))
        self.handler.answer = json.dumps(dict(tag_name='v' + version, html_url=self.base, assets=[asset])).encode()
        self.handler.status = status
    def update(self, cancelled=lambda: False):
        # (Nothing is started for it: what was downloaded is read.)
        with mock.patch('subprocess.Popen', side_effect=AssertionError('a program was started')):
            return self_update.update(self.exe, cancelled, self.lines.append)
    def assertUnchanged(self):
        self.assertEqual(self.exe.read_bytes(), fake_exe(b'old'))
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), [self.exe.name])
    def test_newer_release_replaces_exe(self):
        self.release()
        self.assertEqual(self.update(), '99.0.0')
        self.assertEqual(self.exe.read_bytes(), self.new)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), [self.exe.name])
        self.assertIn('@launcher-updated 99.0.0', self.lines)
        self.assertTrue(any(line.startswith('@progress ') for line in self.lines))
    def test_newest_already(self):
        self.release(self_update.version())
        self.assertIsNone(self.update()); self.assertUnchanged()
        self.handler.answer, self.handler.status = b'{"message": "Not Found"}', 404
        self.assertIsNone(self.update()); self.assertUnchanged()
    def test_damaged_or_wrong_download_changes_nothing(self):
        for release, version, why in [(dict(sha256='0' * 64), '99.0.0', 'damaged'),
                                      (dict(size=len(self.new) + 1), '99.0.0', 'incomplete'),
                                      ({}, '98.0.0', 'is version 98.0.0'),
                                      ({}, None, 'names no version')]:
            with self.subTest(why):
                self.new = self.handler.files['/new.exe'] = fake_exe(b'new' * 100000, version=version)
                self.release(**release)
                with self.assertRaisesRegex(UpdateError, why): self.update()
                self.assertUnchanged()
        self.handler.files = {'/new.exe': b'<html>'}; self.release(sha256=hashlib.sha256(b'<html>').hexdigest(), size=6)
        with self.assertRaisesRegex(UpdateError, 'not a Windows launcher'): self.update()
        self.assertUnchanged()
    def test_cancel_and_failures_leave_exe(self):
        self.release()
        with self.assertRaises(Cancelled): self.update(cancelled=lambda: True)
        self.assertUnchanged()
        self.handler.answer, self.handler.status = b'{"message": "API rate limit exceeded"}', 403
        with self.assertRaisesRegex(UpdateError, 'try again later'): self.update()
        with mock.patch.dict(os.environ, TTT2_LAUNCHER_RELEASES='http://127.0.0.1:9/latest'):
            with self.assertRaisesRegex(UpdateError, 'GitHub cannot be reached'): self.update()
        self.assertUnchanged()
    def test_old_exe_back_when_new_cannot_take_its_place(self):
        update = self_update.update_file(self.exe); update.write_bytes(self.new)
        real = os.replace
        def refuse(source, target):
            if Path(source) == update: raise PermissionError(13, 'Access is denied')
            real(source, target)
        with mock.patch('os.replace', side_effect=refuse), self.assertRaises(PermissionError):
            self_update.replace(update, self.exe)
        self.assertEqual(self.exe.read_bytes(), fake_exe(b'old'))
        self.assertFalse(self_update.old_file(self.exe).exists())

class Answers(BaseHTTPRequestHandler):
    """GitHub's answers by path: (status, body)."""
    answers = {}
    def do_GET(self):
        status, body = self.answers.get(self.path, (404, b'{"message": "Not Found"}'))
        self.send_response(status); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass

OLD, HEAD = 'a' * 40, 'b' * 40
PROJECT = {'launcher/windows/main.py': b'new main', 'launcher/windows/self_update.py': b'new update',
           'launcher/builder/CMakeLists.txt': b'set(TTT2_LAUNCHER_VERSION 0.4.0)\n',
           'Start Ultimate Launcher.cmd': b'@echo off\n:start\n', 'tools/added.py': b'added'}

def archive(files, commit=HEAD, others=()):
    """GitHub's ZIP of a commit: its files in one folder, the commit in its comment (and `others`, by their
    names in the ZIP)."""
    data, top = io.BytesIO(), 'Tekken-Tag-2-Ultimate-Edition-' + HEAD + '/'
    with zipfile.ZipFile(data, 'w') as z:
        z.comment = commit.encode()
        z.writestr(top, b'')
        for path, content in files.items(): z.writestr(top + path, content)
        for name in others: z.writestr(name, b'x')
    return data.getvalue()

class Files(unittest.TestCase):
    """A test build's files updated in place from its branch (update_files)."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.old = {'launcher/windows/main.py': b'old main', 'launcher/windows/self_update.py': b'old update',
                    'launcher/builder/CMakeLists.txt': b'set(TTT2_LAUNCHER_VERSION 0.4.0)\n',
                    'Start Ultimate Launcher.cmd': b'@echo off\r\n', 'tools/removed.py': b'gone',
                    self_update.BUILD_COMMIT: (OLD + '\n').encode(), self_update.BUILD_BRANCH: b'dev-0-4-0\n'}
        for path, data in self.old.items(): (self.root / path).parent.mkdir(parents=True, exist_ok=True); (self.root / path).write_bytes(data)
        self.stamp = 'f' * 64 + '\n' + ''.join(path + '\n' for path in sorted(self.old))
        (self.root / 'local').mkdir(); (self.root / self_update.STAMP).write_text(self.stamp)
        (self.root / 'build-windows-tools').mkdir(); (self.root / 'build-windows-tools/game.exe').write_bytes(b'built')
        handler = type('Handler', (Answers,), dict(answers={}))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler); self.answers = handler.answers
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        environment = mock.patch.dict(os.environ, TTT2_LAUNCHER_GITHUB='http://127.0.0.1:%d' % server.server_port)
        environment.start(); self.addCleanup(environment.stop)
        self.lines = []
    def github(self, ahead=2, data=None):
        repo = '/repos/' + self_update.REPOSITORY
        self.answers[repo + '/compare/%s...dev-0-4-0' % OLD] = (200, json.dumps({'ahead_by': ahead}).encode())
        self.answers[repo + '/branches/dev-0-4-0'] = (200, json.dumps({'commit': {'sha': HEAD}}).encode())
        self.answers['/archive/%s.zip' % HEAD] = (200, archive(PROJECT) if data is None else data)
    def update(self):
        return self_update.update_files(self.root, 'dev-0-4-0', say=self.lines.append)
    def assertUnchanged(self):
        for path, data in self.old.items(): self.assertEqual((self.root / path).read_bytes(), data, path)
        self.assertFalse((self.root / 'tools/added.py').exists())
        self.assertEqual((self.root / self_update.STAMP).read_text(), self.stamp)
    def test_newer_commit_replaces_files(self):
        self.assertEqual(self_update.test_branch(self.root), 'dev-0-4-0')
        self.assertEqual(self_update.files_id(self.root), '0.4.0 ' + OLD)
        self.github()
        self.assertEqual(self.update(), HEAD)
        self.assertEqual((self.root / 'launcher/windows/main.py').read_bytes(), b'new main')
        self.assertEqual((self.root / 'tools/added.py').read_bytes(), b'added')
        self.assertEqual((self.root / 'Start Ultimate Launcher.cmd').read_bytes(), b'@echo off\r\n:start\r\n')
        self.assertFalse((self.root / 'tools/removed.py').exists())
        self.assertEqual((self.root / 'build-windows-tools/game.exe').read_bytes(), b'built')
        self.assertEqual(self_update.build_commit(self.root), HEAD)
        self.assertEqual(self_update.files_id(self.root), '0.4.0 ' + HEAD)
        self.assertEqual(self_update.shown_id(self_update.files_id(self.root)), '0.4.0 (bbbbbbb)')
        # (The .exe's SHA-256 stays: it opens these files, instead of unpacking its own over them.)
        stamp = (self.root / self_update.STAMP).read_text().splitlines()
        self.assertEqual(stamp[0], 'f' * 64)
        self.assertEqual(sorted(stamp[1:]), sorted(set(PROJECT) | {self_update.BUILD_COMMIT, self_update.BUILD_BRANCH}))
        self.assertIn('@launcher-updated bbbbbbb', self.lines)
        self.assertEqual(sorted(p.name for p in (self.root / 'local').iterdir()), ['launcher-files.txt'])
    def test_nothing_newer(self):
        self.github(ahead=0)
        self.assertIsNone(self.update()); self.assertUnchanged()
    def test_wrong_downloads_change_nothing(self):
        for data, why in [(b'<html>', 'not a ZIP'), (archive(PROJECT, commit=OLD), 'another commit'),
                          (archive(PROJECT, others=['Tekken-Tag-2-Ultimate-Edition-%s/../escape.py' % HEAD]),
                           'not a plain file'),
                          (archive(PROJECT, others=['another-folder/a.py']), 'not a plain file'),
                          (archive({k: v for k, v in PROJECT.items() if 'main.py' not in k}), 'lacks')]:
            with self.subTest(why):
                self.github(data=data)
                with self.assertRaisesRegex(UpdateError, why): self.update()
                self.assertUnchanged()
        self.answers.clear()
        with self.assertRaisesRegex(UpdateError, 'no branch dev-0-4-0 with this build'): self.update()
        self.assertUnchanged()
    def test_stopped_half_way_unpacks_again(self):
        self.github()
        real = self_update.write_file
        def fail(file, data):
            if file.name == 'self_update.py': raise PermissionError(13, 'Access is denied')
            real(file, data)
        with mock.patch.object(self_update, 'write_file', side_effect=fail), \
                self.assertRaisesRegex(UpdateError, 'start the launcher again'):
            self.update()
        # (No .exe's SHA-256 in the stamp: the .exe unpacks its own files again, and deletes the new ones.)
        stamp = (self.root / self_update.STAMP).read_text().splitlines()
        self.assertEqual(stamp[0], 'updating')
        self.assertIn('tools/added.py', stamp)
    def test_its_release_is_newer(self):
        with mock.patch.object(self_update, 'version', return_value='0.4.0'):
            self.assertTrue(self_update.newer_release('0.4.0', self.root))
            self.assertFalse(self_update.newer_release('0.3.1', self.root))
            (self.root / self_update.BUILD_BRANCH).write_text('main\n')
            self.assertFalse(self_update.newer_release('0.4.0', self.root))
            self.assertTrue(self_update.newer_release('0.4.1', self.root))
    def test_not_a_test_build(self):
        (self.root / self_update.BUILD_BRANCH).write_text('main\n')
        self.assertIsNone(self_update.test_branch(self.root))
        (self.root / self_update.BUILD_BRANCH).write_text('dev-0-4-0\n'); (self.root / self_update.STAMP).unlink()
        self.assertIsNone(self_update.test_branch(self.root))
        with self.assertRaisesRegex(UpdateError, 'not unpacked from the launcher .exe'): self.update()

if __name__ == '__main__': unittest.main()
