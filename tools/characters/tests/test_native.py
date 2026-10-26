"""Building the C helpers shipped as source (native.py), with a made-up source.

    python3 -m unittest discover tools/characters/tests
"""
import os
import shutil
import sys
import subprocess
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char import InputError                       # noqa: E402
from ttt2char import native                           # noqa: E402

SOURCE = 'int answer(void) { return %d; }\n'


class Native(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.src = os.path.join(self.dir, 'answer.c')
        with open(self.src, 'w') as f:
            f.write(SOURCE % 42)
        self.cache = os.path.join(self.dir, 'cache')

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_build_reuse_rebuild(self):
        if native.compiler() is None:
            self.skipTest('no C compiler')
        out = native.build('answer', self.src, cache=self.cache)
        self.assertEqual(out, native.output_path('answer', cache=self.cache))
        # Windows keeps a loaded DLL locked until the loading process exits.
        subprocess.run([sys.executable, '-c', 'import ctypes, sys; assert ctypes.CDLL(sys.argv[1]).answer() == 42',
                        out], check=True)
        stamp = os.path.getmtime(out)
        self.assertEqual(native.build('answer', self.src, cache=self.cache), out)
        self.assertEqual(os.path.getmtime(out), stamp)          # up to date: not rebuilt
        time.sleep(0.05)
        with open(self.src, 'w') as f:
            f.write(SOURCE % 7)
        os.utime(self.src, (stamp + 10, stamp + 10))
        native.build('answer', self.src, cache=self.cache)
        self.assertGreater(os.path.getmtime(out), stamp)          # newer source: rebuilt
        native.build('answer', self.src, flags=('-O1',), cache=self.cache)
        with open(out + '.cmd') as f:
            self.assertIn('-O1', f.read())                       # other options: rebuilt with them

    def test_prebuilt_override(self):
        fake = os.path.join(self.dir, 'prebuilt.so')
        with open(fake, 'wb') as f:
            f.write(b'\x7fELF')
        with mock.patch.dict(os.environ, {'TTT2_NATIVE_ANSWER': fake}):
            self.assertEqual(native.build('answer', self.src, cache=self.cache), fake)
        with mock.patch.dict(os.environ, {'TTT2_NATIVE_ANSWER': fake + '.missing'}):
            with self.assertRaises(InputError):
                native.build('answer', self.src, cache=self.cache)

    def test_header_change_rebuilds(self):
        if native.compiler() is None:
            self.skipTest('no C compiler')
        header = os.path.join(self.dir, 'answer.h')
        with open(header, 'w') as f:
            f.write('#define ANSWER 42\n')
        with open(self.src, 'w') as f:
            f.write('#include "answer.h"\nint answer(void) { return ANSWER; }\n')
        out = native.build('answer', self.src, cache=self.cache, dependencies=(header,))
        with open(header, 'w') as f:
            f.write('#define ANSWER 7\n')
        os.utime(header, (os.path.getmtime(out) + 10,) * 2)
        native.build('answer', self.src, cache=self.cache, dependencies=(header,))
        subprocess.run([sys.executable, '-c', 'import ctypes, sys; assert ctypes.CDLL(sys.argv[1]).answer() == 7',
                        out], check=True)

    def test_no_compiler(self):
        env = dict(os.environ)
        env.pop('CC', None)
        env.pop('TTT2_NATIVE_ANSWER', None)
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(native.shutil, 'which',
                                                                            return_value=None):
            with self.assertRaises(InputError) as cm:
                native.build('answer', self.src, cache=self.cache)
        self.assertIn('install gcc', str(cm.exception))

    def test_compile_error(self):
        if native.compiler() is None:
            self.skipTest('no C compiler')
        with open(self.src, 'w') as f:
            f.write('this is not C\n')
        with self.assertRaises(InputError):
            native.build('answer', self.src, cache=self.cache)
        self.assertFalse(os.path.exists(os.path.join(self.cache, 'answer.so')))


if __name__ == '__main__':
    unittest.main()
