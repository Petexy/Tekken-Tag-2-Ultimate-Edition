"""Unit tests of the game's record order for a fighter's skeleton (convert/recordorder.py) and of a still weapon
numbered below 800 (weapons.number_of 'number': Miary Zo's snakes' parent, convert/snakes8.py), on made-up data.

    python3 -m pytest -q tools/characters/tests/test_record_order.py
"""
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from ttt2char import pack  # noqa: E402
from ttt2char.characters import miary_zo  # noqa: E402
from ttt2char.convert import recordorder, snakes8, weapons  # noqa: E402
from ttt2char.ttt2 import bone, nud  # noqa: E402


def skeleton(extra):
    """Two body bones (HARA, UDE_R_jnt) and the OPT bones extra [(number, name, parent index)], in that order."""
    names, parent, opt = ['cha:HARA_ROT1', 'cha:UDE_R_jnt'], [-1, 0], []
    for number, name, up in extra:
        names.append('cha:OPT%d_%s' % (number, name))
        parent.append(up)
        opt.append(number)
    n = len(names)
    rng = np.random.default_rng(3)
    return dict(names=names, parent=parent, opt=opt, t=rng.normal(0, 50, (n, 3)).astype(np.float32),
                r=rng.uniform(-1, 1, (n, 3)).astype(np.float32), s=np.ones((n, 3), np.float32), names_raw=None,
                params=None, scale=1.0)


# her kind: cloth, weapons with points among them, the snakes' parent (599) and the snakes after the weapons
MIXED = [(400, 'cloth0', 0), (401, 'cloth1', 2), (800, 'staff', 1), (850, 'hit79_0', 4), (801, 'tail', 0),
         (599, 'snakes', 1), (600, 'center', 7), (601, 'snake_A', 8), (622, 'dambe', 7)]


def model_of(skel_bones):
    """A one-mesh model whose vertices are skinned to each bone in turn (u32 bones, f32 weights)."""
    verts = np.zeros(len(skel_bones), nud.vertex_dtype(0x13, 0x10))
    verts['bones'][:, 0] = skel_bones
    verts['bones'][:, 1] = 1
    verts['w'][:, 0], verts['w'][:, 1] = 0.75, 0.25
    poly = dict(vtype=0x13, uvtype=0x10, verts=verts)
    return {'meshes': [dict(name='m', singlebind=skel_bones[-1], polys=[poly])]}


class PermutationTest(unittest.TestCase):
    def test_number_order(self):
        s = skeleton(MIXED)
        order = recordorder.permutation(s)
        self.assertEqual([s['opt'][i - 2] for i in order[2:]], sorted(s['opt']))
        self.assertEqual(order[:2], [0, 1])                             # (the body as it is)

    def test_apply_keeps_the_hierarchy(self):
        s = skeleton(MIXED)
        out = recordorder.apply(s, recordorder.permutation(s))
        self.assertEqual(out['opt'], sorted(s['opt']))
        self.assertEqual(out['opt'], [int(x.split('_')[0][7:]) for x in out['names'][2:]])
        before = dict(zip(s['names'], bone.world_matrices(s)))
        after = dict(zip(out['names'], bone.world_matrices(out)))     # (parents first: the world_matrices assert)
        for name in s['names']:
            np.testing.assert_allclose(after[name], before[name], atol=1e-3)
        by = {n: i for i, n in enumerate(out['names'])}
        self.assertEqual(out['parent'][by['cha:OPT600_center']], by['cha:OPT599_snakes'])
        self.assertLess(by['cha:OPT599_snakes'], by['cha:OPT600_center'])

    def test_model_follows(self):
        s = skeleton(MIXED)
        order = recordorder.permutation(s)
        m = model_of(list(range(len(s['names']))))
        names_before = [s['names'][b] for b in m['meshes'][0]['polys'][0]['verts']['bones'][:, 0]]
        single = s['names'][m['meshes'][0]['singlebind']]
        out = recordorder.apply(s, order)
        recordorder.renumber_model(m, order)
        v = m['meshes'][0]['polys'][0]['verts']
        self.assertEqual([out['names'][b] for b in v['bones'][:, 0]], names_before)
        self.assertEqual(set(v['bones'][:, 1]), {1})                     # (a body bone keeps its index)
        self.assertEqual(out['names'][m['meshes'][0]['singlebind']], single)
        self.assertEqual(v['bones'].dtype, np.dtype('>u4'))

    def test_in_order_already(self):
        s = skeleton(sorted(MIXED[:3]))
        m = model_of([0, 1, 2])
        logs = []
        s2, m2 = recordorder.write(s, m, logs.append)
        self.assertIs(s2, s)
        self.assertIs(m2, m)
        self.assertEqual(logs, [])

    def test_parent_after_child_left(self):
        """A bone whose parent's number is higher (as the snakes under OPT 821 were) cannot take the order."""
        s = skeleton([(821, 'snakes', 1), (600, 'center', 2)])
        self.assertIsNone(recordorder.permutation(s))
        logs = []
        s2, _ = recordorder.write(s, model_of([0]), logs.append)
        self.assertIs(s2, s)
        self.assertEqual(len(logs), 1)

    def test_list_not_the_last_bones(self):
        s = skeleton(MIXED)
        s['opt'] = list(reversed(s['opt']))
        self.assertIsNone(recordorder.permutation(s))

    def test_bon_round_trip(self):
        s = skeleton(MIXED)
        s.update(v1=1, v2=100, b0c=b'\0\3\0\6', hdr_tail=bytes(12), tail=b'')
        out = bone.read(bone.write(recordorder.apply(s, recordorder.permutation(s))))
        self.assertEqual(out['opt'], sorted(s['opt']))


class NumberedWeaponTest(unittest.TestCase):
    """A still weapon numbered below 800 ('number'): its bone, character.ini item k = number - 800, the runtime's
    800 + k (uint32) back to the number, and the spring entries of the snakes' bones with it."""

    def test_number_of(self):
        s = skeleton([(400, 'cloth0', 0)])
        self.assertEqual(weapons.number_of(s, {'bone': 'snakes', 'number': 599}), 599)
        with self.assertRaises(ValueError):
            weapons.number_of(skeleton([(599, 'cloth', 0)]), {'bone': 'snakes', 'number': 599})

    def test_of_skeleton_and_ini(self):
        defs = [{'bone': 'snakes', 'parent': 'UDE_R_jnt', 'still': True, 'summon': 4, 'number': 599},
                {'bone': 'staff', 'parent': 'UDE_R_jnt', 'pair': 0, 'summon': 1}]
        s = skeleton([(599, 'snakes', 1), (600, 'center', 2), (800, 'staff', 1), (850, 'hit79_0', 4)])
        items = weapons.of_skeleton(s, defs)
        self.assertEqual(items, [(-201, 1, [], 4), (0, 1, [(0, 0)], 1)])
        d = types.SimpleNamespace(NAME='X', CODE='abc', DONOR='Jun', SEX='f')
        old = pack.revision, pack.game_of
        pack.revision, pack.game_of = (lambda d: 0), (lambda d: 'tekken8')
        try:
            ini = pack.character_ini(d, 0, weapons=items)
        finally:
            pack.revision, pack.game_of = old
        self.assertIn('weapons = -201:1::4 0:1:0:1\n', ini)
        k = (-201) % (1 << 64)                                          # (strtoul of "-201")
        self.assertEqual((800 + (k & 0xFFFFFFFF)) & 0xFFFFFFFF, 599)    # (the runtime's 800 + k, uint32)
        self.assertGreaterEqual(k & 0xFFFFFFFF, 20)                     # (no pair: still)

    def test_parent_index(self):
        s = skeleton([(599, 'snakes', 1)])
        self.assertEqual(weapons.parent_index(s, 'snakes'), 2)

    def test_spring_numbers(self):
        d = types.SimpleNamespace(SNAKES={'necks': (2, 5, 8, 11), 'parent': 'snakes'},
                                  WEAPONS=[{'bone': 'snakes', 'number': 599}])
        s = skeleton([(400, 'cloth0', 0), (599, 'snakes', 1), (600, 'center', 3), (601, 'snake_A', 4),
                      (800, 'staff', 1)])
        self.assertEqual(snakes8.spring_numbers(d, s), [599, 600, 601])

    def test_her_definition(self):
        w = snakes8.weapon(miary_zo)
        self.assertEqual(w['number'], snakes8.PARENT_NUMBER)
        self.assertLess(w['number'], snakes8.OPT_FIRST)
        self.assertGreaterEqual(w['number'], 400 + miary_zo.CLOTH_BONES)  # (after her cloth's numbers)


if __name__ == '__main__':
    unittest.main()
