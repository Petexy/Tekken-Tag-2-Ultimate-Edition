"""numpy and Pillow got without pip (python_packages.py, get_python_packages.py), with made-up wheels from a made-up
lock (file:// URLs): nothing is downloaded.

    python3 -m unittest discover tools/characters/tests
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, HERE)

from ttt2char import InputError                       # noqa: E402
from ttt2char import python_packages                  # noqa: E402

TAG = 'cp%d%d' % sys.version_info[:2]
LINUX = sys.platform == 'linux' and python_packages.glibc() is not None


def wheel(folder, name, files):
    """A made-up wheel for this Python (manylinux 2.17) holding `files` ({path: text}) -> its lock entry."""
    path = os.path.join(folder, '%s-0.1-%s-%s-manylinux_2_17_x86_64.manylinux2014_x86_64.whl' % (name, TAG, TAG))
    with zipfile.ZipFile(path, 'w') as z:
        for member, text in files.items():
            z.writestr(member, text)
    with open(path, 'rb') as f:
        data = f.read()
    return {'name': name, 'version': '0.1', 'url': 'file://' + path, 'size': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


class PythonPackages(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.entries = [
            wheel(self.dir, 'numpy', {'numpy/__init__.py': "__version__ = '0.1'\n",
                                      'numpy-0.1.dist-info/METADATA': 'Name: numpy\n',
                                      'numpy-0.1.data/platlib/numpy_extra.py': 'X = 1\n',
                                      'numpy-0.1.data/scripts/f2py': '#!/bin/sh\n'}),
            wheel(self.dir, 'Pillow', {'PIL/__init__.py': "__version__ = '0.2'\n", 'PIL/Image.py': '\n'})]
        self.lock = self.write_lock({python_packages.python(): self.entries})
        self.folder = os.path.join(self.dir, 'data', 'python', TAG)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write_lock(self, pins):
        path = os.path.join(self.dir, 'lock-%d.json' % len(os.listdir(self.dir)))
        with open(path, 'w') as f:
            json.dump(pins, f)
        return path

    def test_needs_glibc(self):
        self.assertEqual(python_packages.needs_glibc(
            'numpy-2.5.4-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl'), (2, 27))
        self.assertEqual(python_packages.needs_glibc(
            'numpy-2.2.6-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl'), (2, 17))
        self.assertEqual(python_packages.needs_glibc('x-1-cp313-cp313-manylinux2010_x86_64.whl'), (2, 12))
        self.assertIsNone(python_packages.needs_glibc('x-1-cp313-cp313-musllinux_1_2_x86_64.whl'))
        self.assertIsNone(python_packages.needs_glibc('x-1-cp313-cp313-manylinux_2_28_aarch64.whl'))

    def test_the_lock_pins_every_python_it_names(self):
        pinned = python_packages.load()
        self.assertIn('3.13', pinned)
        for version, entries in pinned.items():
            self.assertEqual([e['name'] for e in entries], list(python_packages.PACKAGES), version)
            tag = 'cp' + version.replace('.', '')
            for e in entries:
                name = os.path.basename(e['url'])
                self.assertTrue(e['url'].startswith('https://files.pythonhosted.org/'), name)
                self.assertIn('-%s-%s-' % (tag, tag), name)
                self.assertIn('-%s-' % e['version'], name)
                self.assertEqual(len(e['sha256']), 64, name)
                self.assertGreater(e['size'], 0)
                self.assertLessEqual(python_packages.needs_glibc(name), (2, 28), name)

    @unittest.skipUnless(LINUX, 'Linux with glibc')
    def test_get(self):
        log = []
        progress = []
        versions = python_packages.get(self.folder, lock=self.lock, log=log.append,
                                       progress=lambda *words: progress.append(words))
        self.assertEqual(versions, {'numpy': '0.1', 'Pillow': '0.2'})
        for path in ('numpy/__init__.py', 'numpy_extra.py', 'PIL/Image.py', 'numpy-0.1.dist-info/METADATA',
                     '.ttt2-packages.json'):
            self.assertTrue(os.path.isfile(os.path.join(self.folder, path)), path)
        self.assertFalse(os.path.exists(os.path.join(self.folder, 'f2py')))         # (a .data folder's scripts)
        self.assertEqual(os.listdir(os.path.dirname(self.folder)), [TAG])           # (nothing left beside it)
        self.assertEqual([w[:2] for w in progress if w[0] == 'step'],
                         [('step', 'download'), ('step', 'unpack'), ('step', 'check')])
        total = sum(e['size'] for e in self.entries)
        self.assertEqual(progress[-3], ('progress', total, total))
        # again: replaced whole
        with open(os.path.join(self.folder, 'stale.py'), 'w') as f:
            f.write('\n')
        python_packages.get(self.folder, lock=self.lock, log=log.append)
        self.assertFalse(os.path.exists(os.path.join(self.folder, 'stale.py')))

    @unittest.skipUnless(LINUX, 'Linux with glibc')
    def test_a_file_that_is_not_the_pinned_one_changes_nothing(self):
        python_packages.get(self.folder, lock=self.lock, log=lambda *_: None)
        before = sorted(os.listdir(self.folder))
        bad = [dict(self.entries[0], sha256='0' * 64), self.entries[1]]
        with self.assertRaisesRegex(InputError, 'SHA-256'):
            python_packages.get(self.folder, lock=self.write_lock({python_packages.python(): bad}),
                                log=lambda *_: None)
        self.assertEqual(sorted(os.listdir(self.folder)), before)
        self.assertEqual(os.listdir(os.path.dirname(self.folder)), [TAG])

    @unittest.skipUnless(LINUX, 'Linux with glibc')
    def test_a_path_out_of_the_folder_is_refused(self):
        evil = wheel(self.dir, 'numpy', {'../../evil.py': '\n'})
        with self.assertRaisesRegex(InputError, 'must not'):
            python_packages.get(self.folder, lock=self.write_lock({python_packages.python(): [evil]}),
                                log=lambda *_: None)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'evil.py')))
        self.assertFalse(os.path.exists(self.folder))

    @unittest.skipUnless(LINUX, 'Linux with glibc')
    def test_what_the_launcher_cannot_get(self):
        other = self.write_lock({'3.1': self.entries})
        with self.assertRaisesRegex(InputError, 'Python 3.1 only, not %s' % python_packages.python()):
            python_packages.wheels(other)
        self.assertIn('not %s' % python_packages.python(), python_packages.status(other)['error'])
        self.assertIsNone(python_packages.status(self.lock)['error'])
        self.assertEqual(python_packages.status(self.lock)['size'], sum(e['size'] for e in self.entries))
        with mock.patch.object(python_packages, 'glibc', return_value=(2, 12)):
            with self.assertRaisesRegex(InputError, 'needs glibc 2.17 or newer, and this system has glibc 2.12'):
                python_packages.wheels(self.lock)
        with mock.patch.object(python_packages, 'glibc', return_value=None):
            with self.assertRaisesRegex(InputError, 'no glibc'):
                python_packages.wheels(self.lock)

    @unittest.skipUnless(LINUX, 'Linux with glibc')
    def test_the_importer_finds_them_before_the_system_packages(self):
        python_packages.get(self.folder, lock=self.lock, log=lambda *_: None)
        env = dict(os.environ, XDG_DATA_HOME=os.path.join(self.dir, 'home'))
        env.pop('TTT2_DATA_DIR', None)
        os.makedirs(os.path.join(self.dir, 'home', 'ttt2', 'python'))
        os.rename(self.folder, os.path.join(self.dir, 'home', 'ttt2', 'python', TAG))
        code = 'import sys; sys.path.insert(0, sys.argv[1]); import ttt2char, numpy; print(numpy.__version__)'
        out = subprocess.run([sys.executable, '-c', code, HERE], env=env, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), '0.1')
        # without the folder: as before (the system's numpy, or none)
        env['XDG_DATA_HOME'] = os.path.join(self.dir, 'nowhere')
        out = subprocess.run([sys.executable, '-c', code.replace('print(numpy.__version__)', 'print(sys.path)'), HERE],
                             env=env, capture_output=True, text=True)
        self.assertNotIn(os.path.join(self.dir, 'nowhere'), out.stdout)


if __name__ == '__main__':
    unittest.main()
