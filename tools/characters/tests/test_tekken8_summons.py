"""Unit tests of a Tekken 8 fighter's summoned weapons and root points (convert/summons8.py, the weapon pairs of
tekken8/anim.py, retarget.descriptors / encode with pairs, weapons.append_tekken8, the moveset converter's hooks) on
made-up data (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_summons.py
"""
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from ttt2char.convert import model, moveset, retarget as RT, summons8, weapons  # noqa: E402
from ttt2char.tekken8 import anim as T8, panm  # noqa: E402
from ttt2char.ttt2 import animation, bone  # noqa: E402
import test_retarget as TR  # noqa: E402
import test_tekken8_anim as TA  # noqa: E402

GENERIC = ((-100.0, 1000.0, 750.0), (-100.0, 1000.0, 300.0))


# ------------------------------------------------------------------------------------------------ made-up movesets
class Box:
    def __init__(self, loc, a, loc2, b):
        self.loc, self.a, self.loc2, self.b = loc, a, loc2, b


def move(boxes, key):
    """A Tekken 8 move of hit boxes [(loc, a, loc2, b)] (the first two: its summary codes) playing clip `key`."""
    hb = [Box(*x) for x in boxes] + [Box(0, (0, 0, 0), 0, (0, 0, 0))] * (2 - len(boxes))
    codes = [hb[0].loc, hb[0].loc2, hb[1].loc, hb[1].loc2]
    return dict(hitboxes=hb, hitbox=bytes(codes), key=key)


class Moveset:
    def __init__(self, moves, extra=(), end=()):
        self.tables = dict(moves=list(moves), extra_move_properties=[dict(r) for r in extra],
                           move_begin_props=[], move_end_props=[dict(r) for r in end])

    def anim_ref(self, i):
        return self.tables['moves'][i]['key'], 'com'


def definition(*weapons_):
    return types.SimpleNamespace(WEAPONS=[dict(w) for w in weapons_])


STAFF = dict(bone='staff', parent='TE_R_jnt', pair=0, summon=1)
TAIL = dict(bone='tail', parent='KOSHI_jnt', pair=3, summon=2)


class SummonsTest(unittest.TestCase):
    def test_summon_of(self):
        self.assertEqual([summons8.summon_of(b) for b in (1, 2, 4, 8, 16)], [0, 1, 2, 3, 4])
        self.assertEqual([summons8.summon_of(b) for b in (0, 3, 32, 64, -1)], [None] * 5)

    def test_show_rows(self):
        """0x8410 bit, value2 1 / 0 -> the summon / dismiss id, value the summon number, in every property table;
        bits past the summons stay as they are (dropped later)."""
        k = Moveset([], extra=[dict(id=0x8410, value=4, value2=1), dict(id=0x8410, value=32, value2=1),
                               dict(id=0x8001, value=4, value2=1)],
                    end=[dict(id=0x8410, value=1, value2=0)])
        log = []
        summons8.prepare(k, definition(STAFF), log=log.append)
        ex, end = k.tables['extra_move_properties'], k.tables['move_end_props']
        self.assertEqual((ex[0]['id'], ex[0]['value']), (summons8.SUMMON, 2))
        self.assertEqual((ex[1]['id'], ex[1]['value']), (0x8410, 32))
        self.assertEqual((ex[2]['id'], ex[2]['value']), (0x8001, 4))
        self.assertEqual((end[0]['id'], end[0]['value']), (summons8.DISMISS, 0))
        self.assertTrue(any('left out' in line for line in log))

    def test_show_rows_need_summoned_weapons(self):
        k = Moveset([], extra=[dict(id=0x8410, value=4, value2=1)])
        summons8.prepare(k, definition(), log=lambda s: None)
        self.assertEqual(k.tables['extra_move_properties'][0]['id'], 0x8410)

    def test_the_summon_ids_become_ttt2s(self):
        """The moveset converter's overrides take the summon / dismiss ids (end properties too) to TTT2's."""
        self.assertEqual(moveset.PROP_OVERRIDE['t8'][summons8.SUMMON], moveset.TT_SUMMON)
        self.assertEqual(moveset.PROP_OVERRIDE['t8'][summons8.DISMISS], moveset.TT_DISMISS)
        self.assertEqual((moveset.HIT_POINT8[138], moveset.HIT_POINT8[139], moveset.HIT_POINT8[22]), (40, 39, 5))

    def test_roots(self):
        """Each clip of a move hitting from the ground origin: its first two distinct offsets; another move of the
        clip with other offsets is a conflict, its codes the nearest of the clip's."""
        far = ((-100.0, 1400.0, 1200.0), (-100.0, 550.0, 500.0))
        k = Moveset([move([(125, GENERIC[0], 125, GENERIC[1])], 7),
                     move([(9, (0, 0, 0), 37, (0, 0, 0))], 8),
                     move([(125, far[0], 125, far[1])], 7),
                     move([(125, (0, 1300, 280), 0, (0, 0, 0)), (125, (0, 1300, 160), 0, (0, 0, 0))], 9)])
        r = summons8.roots(k)
        self.assertEqual(dict(r), {7: list(GENERIC), 9: [(0.0, 1300.0, 280.0), (0.0, 1300.0, 160.0)]})
        self.assertEqual(r.moves, {0: 7, 2: 7, 3: 9})
        self.assertEqual(dict(r.conflicts), {7: 1})
        self.assertTrue(summons8.uses_roots(k))
        got = summons8.prepare(k, definition(), log=lambda s: None)
        self.assertEqual(got, dict(r))
        hb = [bytes(m['hitbox']) for m in k.tables['moves']]
        self.assertEqual(hb[0], bytes([0xFA, 0xFB, 0, 0]))
        self.assertEqual(hb[1], bytes([9, 37, 0, 0]))
        self.assertEqual(hb[2], bytes([0xFA, 0xFB, 0, 0]))       # (1.4 m up 1.2 m ahead -> A, 0.55 m up -> B)
        self.assertEqual(hb[3], bytes([0xFA, 0, 0xFB, 0]))

    def test_no_roots(self):
        k = Moveset([move([(9, (0, 0, 0), 37, (0, 0, 0))], 8)])
        self.assertFalse(summons8.uses_roots(k))
        self.assertEqual(summons8.prepare(k, definition(), log=lambda s: None), {})
        self.assertEqual(summons8.weapons(definition(STAFF), k), [STAFF])

    def test_root_weapons(self):
        """The root points' two hit-only weapons: under HARA_ROT1, pairs after the definition's, never summoned,
        their points the root codes at slots 2 / 3."""
        k = Moveset([move([(125, GENERIC[0], 125, GENERIC[1])], 7)])
        w = summons8.weapons(definition(STAFF, TAIL), k)
        self.assertEqual(w[:2], [STAFF, TAIL])
        self.assertEqual([(x['bone'], x['parent'], x['pair'], x['summon'], x['root']) for x in w[2:]],
                         [('root_a', 'HARA_ROT1', 4, 63, 0), ('root_b', 'HARA_ROT1', 5, 63, 1)])
        self.assertEqual(w[2]['points'], {0xFA: ('origin', 2)})
        self.assertEqual(w[3]['points'], {0xFB: ('origin', 3)})
        self.assertEqual(summons8.weapons(definition(), k)[0]['pair'], 0)
        with self.assertRaises(ValueError):
            summons8.weapons(definition(dict(STAFF, pair=19)), k)

    def test_tolerates_other_movesets(self):
        self.assertFalse(summons8.uses_roots(object()))
        self.assertEqual(summons8.prepare(object(), definition(STAFF), log=lambda s: None), {})


# ------------------------------------------------------------------------------------------------ channels
class DescriptorsTest(unittest.TestCase):
    def test_descriptors(self):
        self.assertEqual(RT.descriptors(23), tuple(animation.BODY_DESCRIPTORS))
        self.assertEqual(RT.descriptors(27), tuple(animation.BODY_DESCRIPTORS) + RT.PAIR_DESCRIPTORS * 2)
        self.assertEqual(RT.descriptors(25, animation.RAW)[:23], RT.RAW_DESCRIPTORS)
        for bad in (22, 24):
            with self.assertRaises(ValueError):
                RT.descriptors(bad)

    def test_encode_with_pairs(self):
        rng = np.random.default_rng(5)
        v = TR.smooth_values(12)
        pairs = np.zeros((12, 4, 3))
        pairs[:, 0] = rng.uniform(-300, 300, (12, 3))
        pairs[:, 1] = rng.uniform(-1, 1, (12, 3))
        pairs[:, 2] = rng.uniform(-300, 300, (12, 3))
        pairs[:, 3] = rng.uniform(-1, 1, (12, 3))
        values = np.concatenate([v, pairs], 1)
        for kind in (animation.COMPRESSED, animation.RAW):
            vals = values if kind == animation.COMPRESSED else animation.to_raw(
                list(RT.descriptors(27)), values, animation.COMPRESSED)
            a = animation.decode(RT.encode(vals, kind))
            self.assertEqual(a['values'].shape, (12, 27, 3))
            self.assertEqual(list(a['descriptors']), list(RT.descriptors(27, kind)))
            np.testing.assert_allclose(a['values'][:, 23::2], vals[:, 23::2], atol=0.5)
            got = animation.local_rotation(a['values'][:, 24::2], kind)
            want = animation.local_rotation(vals[:, 24::2], kind)
            self.assertLess(RT.angle(got, want).max(), 1e-2)
        self.assertEqual(animation.header(RT.encode(v))['nch'], 23)

    def test_shift_counts_the_pairs(self):
        v = np.concatenate([TR.smooth_values(4) * 0.1, np.zeros((4, 2, 3))], 1)
        quiet = RT.rotation_shift(v)
        v[:, 24, 0] = np.pi
        self.assertGreater(RT.rotation_shift(v), quiet)
        self.assertEqual(RT.rotation_shift(v[:, :23]), quiet)


# ------------------------------------------------------------------------------------------------ weapon pairs
def rotations(rng, n):
    return np.array([TR.random_rotation(rng) for _ in range(n)])


class PairValuesTest(unittest.TestCase):
    """pair_values against the runtime's convention: the weapon bone's world = its TTT2 parent's world x the pair."""

    def setUp(self):
        rng = np.random.default_rng(11)
        self.F = F = 5
        names = ['Drv', 'Anc', 'Joint', 'Link', 'Tip']
        self.idx = {n: i for i, n in enumerate(names)}
        self.WR = np.stack([rotations(rng, len(names)) for _ in range(F)])
        self.Wp = rng.uniform(-500, 1500, (F, len(names), 3))
        self.O = TR.random_rotation(rng)
        self.values = TR.smooth_values(F)
        self.bind = (np.array([1.0, 2.0, 3.0]), TR.random_rotation(rng))
        self.pairs = [dict(kind='joint', joint='Joint', driver='Drv', offset=self.O, anchor='Anc'),
                      dict(kind='joint', joint='Link', up='Joint'),
                      dict(kind='lead', joints=['Joint', 'Link', 'Tip'], tip=130.0, driver='Drv', offset=self.O,
                           anchor='Anc'),
                      None,
                      dict(kind='root', root=1, bind=self.bind),
                      dict(kind='still', bind=self.bind)]
        self.conv = types.SimpleNamespace(sub=types.SimpleNamespace(index=self.idx), pairs=self.pairs, scale=0.98,
                                          kind=animation.COMPRESSED)

    def local(self, out, p):
        R = animation.local_rotation(out[:, 2 * p + 1], animation.COMPRESSED)
        return R, out[:, 2 * p]

    def test_joint_and_link(self):
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, 1.0, None, 5)
        self.assertEqual(out.shape, (self.F, 10, 3))
        i = self.idx
        PR, Pp = self.WR[:, i['Drv']] @ self.O, self.Wp[:, i['Anc']]             # the TTT2 parent's world
        R, t = self.local(out, 0)
        self.assertLess(RT.angle(PR @ R, self.WR[:, i['Joint']]).max(), 1e-6)
        np.testing.assert_allclose(Pp + np.einsum('fij,fj->fi', PR, t), self.Wp[:, i['Joint']], atol=1e-6)
        R, t = self.local(out, 1)                                                # under the weapon before it
        self.assertLess(RT.angle(self.WR[:, i['Joint']] @ R, self.WR[:, i['Link']]).max(), 1e-6)
        np.testing.assert_allclose(self.Wp[:, i['Joint']] + np.einsum('fij,fj->fi', self.WR[:, i['Joint']], t),
                                   self.Wp[:, i['Link']], atol=1e-6)

    def test_lead(self):
        """The most forward of the joints and the tip past the last one (along its x), the parent's rotation."""
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, 1.0, None, 5)
        i = self.idx
        tip = self.Wp[:, i['Tip']] + 130.0 * self.WR[:, i['Tip']][:, :, 0]
        cands = np.stack([self.Wp[:, i['Joint']], self.Wp[:, i['Link']], self.Wp[:, i['Tip']], tip], 1)
        want = cands[np.arange(self.F), np.argmax(cands[:, :, 2], 1)]
        PR, Pp = self.WR[:, i['Drv']] @ self.O, self.Wp[:, i['Anc']]
        R, t = self.local(out, 2)
        np.testing.assert_allclose(Pp + np.einsum('fij,fj->fi', PR, t), want, atol=1e-6)
        self.assertLess(RT.angle(R, np.eye(3)[None]).max(), 1e-9)

    def test_gap_and_root(self):
        """A pair no weapon takes: the identity; a root point: at the ground origin's offset (the root scale and
        the size scale as the body's root), else its bind."""
        o = [(0.0, 1300.0, 280.0), (0.0, 1300.0, 160.0)]
        k = 1.07
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, k, o, 5)
        R, t = self.local(out, 3)
        np.testing.assert_allclose(t, 0)
        self.assertLess(RT.angle(R, np.eye(3)[None]).max(), 1e-9)
        R, t = self.local(out, 4)
        H = animation.local_rotation(self.values[:, RT.HARA_CH], animation.COMPRESSED)
        world = 0.98 * self.values[:, 1] + np.einsum('fij,fj->fi', H, t)          # HARA_ROT1 x the pair
        np.testing.assert_allclose(world, np.repeat([np.multiply(0.98 * k, o[1])], self.F, 0), atol=1e-6)
        self.assertLess(RT.angle(R, np.eye(3)[None]).max(), 1e-9)
        out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, k, None, 5)
        R, t = self.local(out, 4)
        np.testing.assert_allclose(t, np.repeat(self.bind[0][None], self.F, 0), atol=1e-9)
        self.assertLess(RT.angle(R, self.bind[1][None]).max(), 1e-6)

    def test_still(self):
        """A still pair (a hit-only weapon holding its place in the order): its bind in every frame, offsets or not."""
        for roots in (None, [(0.0, 1300.0, 280.0)]):
            out = T8.pair_values(self.conv, self.WR, self.Wp, self.values, 1.0, roots, 6)
            R, t = self.local(out, 5)
            np.testing.assert_allclose(t, np.repeat(self.bind[0][None], self.F, 0), atol=1e-9)
            self.assertLess(RT.angle(R, self.bind[1][None]).max(), 1e-6)


def target_with(weapons_):
    """A TTT2 skeleton (test_retarget's) with KOSHI and the weapons' bones appended as append_tekken8 names them."""
    bon = TR.ttt2_bon()
    bon['opt'] = [0] * len(bon['names'])
    for w in weapons_:
        hw = bone.world_matrices(bon)
        world = hw[weapons.parent_index(bon, w['parent'])].copy()
        pts = [(code, slot, world[:3, 3]) for code, (where, slot) in sorted(w.get('points', {}).items())]
        bon = weapons.append_tekken8(bon, w, world, pts)[0]
    return bon


class PairSpecsTest(unittest.TestCase):
    def setUp(self):
        self.sk = types.SimpleNamespace(index={n: i for i, n in enumerate(
            ['C_Leg', 'Rot', 'R_Hand', 'ATH_staff', 'tail_01', 'tail_03', 'tail_05'])})
        self.cal = types.SimpleNamespace(drivers={'KOSHI_jnt': 'C_Leg', 'TE_R_jnt': 'R_Hand'},
                                         offsets={'KOSHI_jnt': np.eye(3), 'TE_R_jnt': np.eye(3)})
        self.weapons = [dict(bone='ATH_staff', parent='TE_R_jnt', pair=0),
                        dict(bone='tail_01', parent='KOSHI_jnt', pair=1),
                        dict(bone='tail_03', parent='tail_01', pair=2),
                        dict(bone='lead', parent='KOSHI_jnt', pair=3, lead=('tail_03', 'tail_05'), tip_cm=13),
                        dict(bone='root_b', parent='HARA_ROT1', pair=5, root=1, points={0xFB: ('origin', 3)}),
                        dict(bone='snake', parent='TE_R_jnt', pair=4, still=True, points={0x79: ('origin', 0)}),
                        dict(bone='horn', parent='TE_R_jnt', points={0x23: ('origin', 1)})]

    def test_kinds(self):
        specs = T8.pair_specs(self.sk, target_with(self.weapons), self.weapons, self.cal)
        self.assertEqual(len(specs), 6)
        self.assertEqual([s['kind'] for s in specs], ['joint', 'joint', 'joint', 'lead', 'still', 'root'])
        self.assertEqual((specs[0]['driver'], specs[0]['anchor']), ('R_Hand', 'R_Hand'))
        self.assertEqual((specs[1]['driver'], specs[1]['anchor']), ('C_Leg', 'Rot'))    # (KOSHI sits at Rot)
        self.assertEqual(specs[2]['up'], 'tail_01')
        self.assertEqual((specs[3]['joints'], specs[3]['tip']), (['tail_03', 'tail_05'], 130.0))
        self.assertEqual(specs[5]['root'], 1)
        self.assertEqual(T8.pair_joints(specs), sorted(['ATH_staff', 'C_Leg', 'R_Hand', 'Rot', 'tail_01',
                                                         'tail_03', 'tail_05']))

    def test_errors(self):
        target = target_with(self.weapons)
        with self.assertRaises(ValueError):                     # no bone for it
            T8.pair_specs(self.sk, target, self.weapons + [dict(bone='x', parent='TE_R_jnt', pair=7)], self.cal)
        bad = [dict(bone='root_a', parent='TE_R_jnt', pair=0, root=0)]
        with self.assertRaises(ValueError):                     # a root point under another bone
            T8.pair_specs(self.sk, target_with(bad), bad, self.cal)
        bad = [dict(bone='ATH_none', parent='TE_R_jnt', pair=0)]
        with self.assertRaises(ValueError):                     # no such joint
            T8.pair_specs(self.sk, target_with(bad), bad, self.cal)


class RootConverterTest(unittest.TestCase):
    """A made-up fighter's clip with root points: 23 channels without offsets, the pairs with them; the points
    posed as the runtime poses them sit at the offsets (scaled as the body's root)."""

    def test_root_pairs(self):
        roots = [dict(bone='root_a', parent='HARA_ROT1', pair=0, root=0, summon=63, points={0xFA: ('origin', 2)}),
                 dict(bone='root_b', parent='HARA_ROT1', pair=1, root=1, summon=63, points={0xFB: ('origin', 3)})]
        bon = target_with(roots)
        fighter = TA.Fighter(TR.ttt2_bon())
        cv = T8.Converter(fighter.sk, bon, weapons=roots)
        clip = panm.Animation(fighter.clip(TR.smooth_values(10)))
        plain, info = cv.channels(clip)
        self.assertEqual((plain.shape[1], info['pairs']), (23, 0))
        out, info = cv.channels(clip, list(GENERIC))
        self.assertEqual((out.shape[1], info['pairs']), (27, 2))
        np.testing.assert_allclose(out[:, :23], plain, atol=1e-9)
        H = animation.local_rotation(out[:, RT.HARA_CH], animation.COMPRESSED)
        for r in range(2):
            world = cv.scale * out[:, 1] + np.einsum('fij,fj->fi', H, out[:, 23 + 2 * r])
            np.testing.assert_allclose(world, np.repeat([np.multiply(cv.scale * info['root_scale'], GENERIC[r])],
                                                        10, 0), atol=1e-6)
        a = animation.decode(cv.animation(fighter.clip(TR.smooth_values(10)), roots=list(GENERIC)))
        self.assertEqual(a['values'].shape[1], 27)
        self.assertEqual(cv.last_pairs, 2)

    def test_provider_roots(self):
        """Clips of root moves are converted with their offsets, even where TTT2 has the clip's original."""
        calls = []
        conv = types.SimpleNamespace(animation=lambda blob, roots=None: calls.append(roots) or b'x', pairs=[1],
                                     last_pairs=2)
        banks = types.SimpleNamespace(blob=lambda cat, key: b'clip', where=lambda cat, key: 'own')
        p = T8.Animations(banks, conv, originals={5: 0x123, 6: 0x456}, roots={5: list(GENERIC)})
        self.assertEqual(p(5, 'com'), b'x')
        self.assertEqual(p(6, 'com'), 0x456)
        self.assertEqual(p(7, 'own'), b'x')
        self.assertEqual(calls, [list(GENERIC), None])
        self.assertEqual(p.stats['body animations with weapon pairs (root points too)'], 1)


# ------------------------------------------------------------------------------------------------ skeleton
class AppendTest(unittest.TestCase):
    def test_append_tekken8(self):
        bon = TR.ttt2_bon()
        bon['opt'] = [0] * len(bon['names'])
        world = np.eye(4)
        world[:3, :3] = TR.random_rotation(np.random.default_rng(3))
        world[:3, 3] = (100.0, 900.0, 50.0)
        tip = np.array([100.0, 900.0, 330.0])
        skel, index, number, used = weapons.append_tekken8(bon, dict(bone='horn', parent='MUNE2_jnt', summon=3),
                                                           world, [(0x23, 1, tip)])
        self.assertEqual((number, used), (weapons.STILL_FIRST, [weapons.POINT_FIRST]))
        self.assertEqual(skel['names'][-2:], ['cha:OPT820_horn', 'cha:OPT850_hit23_1'])
        hw = bone.world_matrices(skel)
        np.testing.assert_allclose(hw[index], world, atol=1e-3)
        np.testing.assert_allclose(hw[-1][:3, 3], tip, atol=1e-3)
        self.assertEqual(weapons.points_of(skel['names']), {0x23: 71})
        with self.assertRaises(ValueError):
            weapons.append_tekken8(bon, dict(bone='x', parent='MUNE2_jnt'), world, [(0x23, 4, tip)])
        w = [dict(bone='staff', mesh='a', points={1: ('tip', 0)}), dict(bone='staff2', mesh='a'),
             dict(bone='tail', mesh='b', points={2: ('origin', 1), 3: ('origin', 2)}), dict(bone='root')]
        self.assertEqual(model.weapon_parts(w), [('wpn0', 'a'), ('wpn1', 'b')])
        self.assertEqual(model.weapon_bones(w), 1 + 1 + 1 + 1 + 2 + 1)


class NaniteOverrideTest(unittest.TestCase):
    """tekken8/uprops.py reads a material instance's NaniteOverrideMaterial (Miary Zo's horn): 28 bytes."""

    def test_read(self):
        import struct
        import test_tekken8_uprops as TU
        from ttt2char.tekken8 import reflect, uprops
        data = TU.name('/Game/Test/Item') + TU.name('Item') + struct.pack('<i', 0) + struct.pack('<Ii', 1, 0) + b'\x7f'
        k = TU.package(data)
        at = k.exports[0].offset
        v, end = uprops.read_struct(k, reflect.Schema(TU.SCHEMA), 'MaterialOverrideNanite', at, at + len(data))
        self.assertEqual(end - at, 28)
        self.assertEqual(v, {'OverrideMaterialRef': '/Game/Test/Item.Item', 'bEnableOverride': True,
                             'OverrideMaterial': None})
        empty = TU.name('None') + TU.name('None') + struct.pack('<iIi', 0, 0, 0)
        k = TU.package(empty)
        at = k.exports[0].offset
        v, end = uprops.read_struct(k, reflect.Schema(TU.SCHEMA), 'MaterialOverrideNanite', at)
        self.assertEqual((v['OverrideMaterialRef'], v['bEnableOverride'], end - at), (None, False, 28))


class PartVerticesTest(unittest.TestCase):
    """model.tekken8_model: a part with TEKKEN8['part_vertices'] is decimated alone first, then kept as it is; the
    model's 'source' still numbers the vertices as loaded."""

    def test_small_part_first(self):
        from unittest import mock
        import test_source as TS
        from ttt2char.convert import decimate, skeleton
        src = mock.Mock(game='tekken8')
        src.costume.return_value = {'parts': [('bdf', 'b')], 'merge_order': ['bdf'], 'colours': 'c'}
        src.load_model.return_value = TS.small_model([('bdf', 'b'), ('wpn0', 'w')])
        calls = []

        def reduce(k, target, weights, log, poses=None, classes=None):
            calls.append((target, dict(weights)))
            if len(calls) < 3:                  # (the part's triangle loses a corner each pass: 2, then 1 left)
                left = [[3, 4, 4]] if len(calls) == 1 else [[3, 3, 3]]
                prims = [dict(p, tris=np.array(left)) if p['part'] == 'wpn0' else p for p in k['prims']]
                return dict(k, prims=prims, source=np.array([5, 0, 1, 2, 3] if len(calls) == 1 else [0, 1, 2, 4]))
            return dict(k, source=np.array([1, 3]))
        d = types.SimpleNamespace(TEKKEN8={'costume': '1p', 'part_vertices': {'wpn0': 1}})
        with mock.patch.object(decimate, 'decimate', side_effect=reduce), \
                mock.patch.object(decimate, 'vertex_target', return_value=4), \
                mock.patch.object(skeleton, 'repose', side_effect=lambda k, donor, log: k):
            k, worn, _, _ = model.tekken8_model(src, d, {}, log=lambda s: None, weapons=[{'mesh': 'w', 'bone': 'x'}])
        self.assertEqual(worn, [('bdf', 'b'), ('wpn0', 'w')])
        self.assertEqual(calls, [(6 - 2, {'bdf': 0.0, 'wpn0': 1.0}), (5 - 1, {'bdf': 0.0, 'wpn0': 1.0}),
                                 (4, {'bdf': 1.0, 'wpn0': 0.0})])
        self.assertEqual(k['source'].tolist(), [0, 3])


if __name__ == '__main__':
    unittest.main()
