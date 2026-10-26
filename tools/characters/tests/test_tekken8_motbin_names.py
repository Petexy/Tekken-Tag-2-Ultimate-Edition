"""CityHash32 (tekken8/city32.py) and the Tekken 8 move namer (tekken8/movenames.py) on made-up names and movesets
(test_tekken8_motbin.py's builders).

    python3 -m unittest discover tools/characters/tests
"""
import ctypes
import glob
import os
import random
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_tekken8_motbin as T                       # noqa: E402
from ttt2char.tekken8 import motbin, movenames        # noqa: E402
from ttt2char.tekken8.city32 import city32, city32_many, city32_rows   # noqa: E402

# CityHash32 v1.1 of inputs that take each length path (0-4 with signed bytes, 5-12, 13-24, longer), as the
# system's Abseil library (absl::hash_internal::CityHash32) computes them
KNOWN = [(b'', 0xdc56d17a), (b'a', 0x3c973d4d), (b'abc', 0x2f635ec7), (b'abcd', 0x98b51e95), (b'\xff\x80', 0xdf606262),
         (b'\xe9t\xe9', 0xd971efd0), (b'Ab_12345', 0xdc3676a4), (b'abcdefgh', 0xfd7ec8b9),
         (b'hello world!', 0x3d6b1923), (b'0123456789abcdef0', 0xea2a8a85), (b'x' * 24, 0x56df45eb),
         (b'x' * 25, 0x765df4ad), (b'y' * 40, 0xf0c386e3), (b'z' * 100, 0x12daa043),
         (b'0123456789abcdefghijklmnopqrstuvwxyz0123456789!', 0x7ad8cf9f)]


def _abseil():
    """Abseil's CityHash32 through ctypes, when the system has the library (else None)."""
    for path in sorted(glob.glob('/usr/lib*/libabsl_city.so*') + glob.glob('/usr/lib/*/libabsl_city.so*')):
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        with open(path, 'rb') as f:
            data = f.read()
        tail = b'13hash_internal10CityHash32EPKcm'
        i = data.find(tail)
        if i < 0:
            continue
        try:
            fn = getattr(lib, data[data.rfind(b'_ZN4absl', 0, i):i + len(tail)].decode())
        except AttributeError:
            continue
        fn.restype = ctypes.c_uint32
        fn.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        return fn
    return None


class City32(unittest.TestCase):
    def test_known_values(self):
        for data, h in KNOWN:
            self.assertEqual(city32(data), h, data[:8])
        self.assertEqual(city32('abc'), 0x2f635ec7)            # a str is hashed as Latin-1

    def test_many_and_rows(self):
        strings = [d for d, _ in KNOWN]
        self.assertEqual([int(h) for h in city32_many(strings)], [h for _, h in KNOWN])
        rnd = random.Random(3)
        for n in (0, 1, 4, 5, 12, 13, 24, 25, 44, 45, 77):
            buf = np.array([[rnd.randrange(256) for _ in range(n)] for _ in range(20)], np.uint8).reshape(20, n)
            self.assertEqual([int(h) for h in city32_rows(buf)], [city32(bytes(r)) for r in buf], n)

    def test_against_abseil(self):
        fn = _abseil()
        if fn is None:
            self.skipTest('no libabsl_city on this system')
        rnd = random.Random(8)
        strings = [bytes(rnd.randrange(256) for _ in range(n)) for n in list(range(0, 130)) +
                   [rnd.randrange(130, 1500) for _ in range(30)]]
        many = city32_many(strings)
        for k, s in enumerate(strings):
            self.assertEqual(city32(s), fn(s, len(s)), len(s))
            self.assertEqual(int(many[k]), fn(s, len(s)), len(s))


class Dictionary:
    """A made-up moveset that only has names (what movenames.harvest reads)."""

    def __init__(self, names, anims=()):
        self.names, self.anims = list(names), list(anims) + [''] * (len(names) - len(anims))
        self.tables = {'moves': [{} for _ in self.names]}

    def move_name(self, i):
        return self.names[i]

    def anim_name(self, i):
        return self.anims[i]


CODE = 'xyz'
# (name as laid out in the name block, animation name, name the name key is made of, name the move key is made of,
# animation name the animation key is made of)
MOVES = [('Co_Thing00', 'co_anim_a', None, None, None),        # the dictionary has it
         ('Xyz_sWALK00', 'xyz_walk', None, None, None),        # the dictionary's 'Ab_sWALK00', the prefix made Xyz_
         ('xyz_w01', 'xyz_w01_an', None, None, None),          # ... 'Ab_w01' with the code's lower-case prefix
         ('Xyz_66RK', 'a66rk', None, None, None),              # a command in numpad notation
         ('Xyz_3LPRP_n', 'a3lprp', None, None, None),          # ... with a mark
         ('Xyz_66RKLPLKRK', 'a66b', None, None, None),         # ... four buttons
         ('Xyz_66RKLPLKRKWP', 'a66c', None, None, None),       # a variation of a found name (a button added)
         ('Xyz_66RKLPLKRKWPWK', 'a66d', None, None, None),     # ... of a variation (a second round)
         ('Xyz_66RK_9LK', 'a66e', None, None, None),           # ... a command added
         ('sDm_Fall35B', 'sdm_fall', None, None, None),        # the dictionary's 'sDm_Fall20B', counted through
         ('Co_Other', 'co_other', None, 'Co_Different', None),  # the name key fits, the move key not: no name
         ('Co_Shortx', 'co_short', 'Co_Short', 'Co_Short', None),  # the keys fit a name of another length: none
         ('Q_unknowable_77Z', 'q_anim_xy', None, None, 'co_anim_a')]   # nothing makes it (its animation: yes)
DICTIONARY = ['Co_Thing00', 'Ab_sWALK00', 'Ab_w01', 'sDm_Fall20B', 'Co_Other', 'Co_Short', 'Ab_Lnage_y']


def named_fighter(moves=MOVES, code=CODE):
    offs, block = T.layout_names([(n, a) for n, a, _, _, _ in moves])
    data = T.build({'moves': [T.move(o[0], o[1]) for o in offs], 'requirements': [T.requirement(1100)]}, roster=7,
                   name_block=block)
    prot = [(city32(k or n), city32(ak or a), 0, 0, 7 * 0xFFFF + 1, city32(code.upper() + '_' + (mk or n)))
            for n, a, k, mk, ak in moves]
    return motbin.read(data, T.fields_bin(data, prot), code)


class MoveNames(unittest.TestCase):
    def test_name_moves(self):
        m = named_fighter()
        stats = movenames.name_moves(m, [Dictionary(DICTIONARY, ['co_anim_a'])])
        want = {i: n for i, (n, _, k, mk, _) in enumerate(MOVES) if k is None and mk is None and i != 12}
        self.assertEqual(m.names, want)
        self.assertEqual(m.move_name(10), '')
        self.assertEqual(m.move_name(11), '')
        self.assertEqual(m.move_name(3), 'Xyz_66RK')
        self.assertEqual(stats['dictionary'], 1)
        self.assertEqual(stats['prefix'], 2)
        self.assertEqual(stats['commands'], 3)
        self.assertEqual(stats['numbers'], 1)
        self.assertEqual(stats['variations'], 3)
        self.assertEqual((stats['named'], stats['moves']), (len(want), len(MOVES)))
        self.assertEqual(m.anim_name(0), 'co_anim_a')
        self.assertEqual(m.anim_name(12), 'co_anim_a')
        self.assertEqual(stats['anims'], 2)

    def test_tekken7_adds(self):
        m = named_fighter()
        movenames.name_moves(m, [Dictionary(['Ab_w01'])])
        self.assertNotIn(0, m.names)
        m = named_fighter()
        movenames.name_moves(m, [Dictionary(['Ab_w01'])], tekken7=[Dictionary(['Co_Thing00'])])
        self.assertEqual(m.names[0], 'Co_Thing00')

    def test_keeps_names_already_set(self):
        m = named_fighter()
        m.set_names({12: 'Q_unknowable_77Z'})
        movenames.name_moves(m, [Dictionary(DICTIONARY)])
        self.assertEqual(m.names[12], 'Q_unknowable_77Z')
        self.assertEqual(m.names[3], 'Xyz_66RK')

    def test_steps(self):
        self.assertEqual(movenames.prefixed([b'He_sKAM00_', b'dwDWN'], [b'Xyz_']),
                         {b'Xyz_He_sKAM00_', b'Xyz_sKAM00_', b'Xyz_dwDWN'})
        c = movenames.commands(b'Xyz_', [b'', b'_n'])
        self.assertTrue({b'Xyz_66RK', b'Xyz_3LPRP_n', b'Xyz_RPRPRPRP', b'Xyz_236WK'} <= c)
        self.assertNotIn(b'Xyz_', c)
        g = movenames.counted([b'Co_Ab07', b'Co_X1'], {6, 7, 8})
        self.assertIn(b'Co_Ab42', g[7])
        self.assertIn(b'Co_Ab07_', g[8])
        self.assertIn(b'Co_X12', g[6])                       # a single digit becoming two
        self.assertIn(b'Co_X1_', g[6])
        self.assertTrue(set(g) <= {6, 7, 8} and all(len(s) == k for k in g for s in g[k]))
        v = movenames.variations([b'Xyz_6LP'], b'Xyz_', [b'_y'])
        self.assertTrue({b'Xyz_6LPRK', b'Xyz_6RK', b'Xyz_9LP', b'Xyz_6LP_y', b'Xyz_6LP_2LK', b'Xyz_6LPsWP',
                         b'Xyz_6RP', b'Xyz_6LP0'} <= v)
        self.assertIn(b'_Q7', movenames.marks([b'Ab_Lnage_Q7', b'Cd_Rnage_Q7']))


if __name__ == '__main__':
    unittest.main()
