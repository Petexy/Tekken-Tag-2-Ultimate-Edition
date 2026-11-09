"""Unit tests of the cloth converter (cloth.py) and its spring file on made-up data (no game files needed).

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import chains, cloth          # noqa: E402


def skirt(rows=12, around=24, radius=18.0, top=110.0, step=8.0):
    """A made-up skirt as Tekken 7 keeps a clothing asset (centimetres, Z up): rings of vertices from the waist
    down, the top ring pinned, the max distance growing downward."""
    v, md = [], []
    for r in range(rows):
        for a in range(around):
            t = 2 * np.pi * a / around
            rr = radius + r * 1.5
            v.append((rr * np.cos(t), rr * np.sin(t), top - r * step))
            md.append(0.0 if r == 0 else 10.0 * r)
    tris = []
    for r in range(rows - 1):
        for a in range(around):
            i, j = r * around + a, r * around + (a + 1) % around
            tris += [(i, j, i + around), (j, j + around, i + around)]
    return types.SimpleNamespace(vertices=np.array(v), max_distance=np.array(md), triangles=np.array(tris),
                                 bone_names=['Hip'], bones=np.zeros((len(v), 4), np.int64),
                                 weights=np.tile([1.0, 0, 0, 0], (len(v), 1)))


def model(asset):
    """A loaded model (as load_tekken7_model gives it) whose only vertices are the skirt's, skinned to Hip, and a
    body column inside it."""
    sim = cloth._points(asset.vertices)
    body_r = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    body = np.array([(80 * np.cos(t), y, 80 * np.sin(t)) for y in np.linspace(0, 1500, 30) for t in body_r])
    pos = np.concatenate([sim, body])
    nrm = np.concatenate([np.zeros_like(sim), body * [1, 0, 1]])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    n = len(pos)
    joints = np.zeros((n, 8), np.int64)
    weights = np.zeros((n, 8))
    weights[:, 0] = 1.0
    world = np.tile(np.eye(4), (2, 1, 1))
    world[1, :3, 3] = (0, 1100, 0)
    tris = np.concatenate([asset.triangles, len(sim) + np.array([[0, 1, 2]])])
    prim = dict(part='bdu', material='m', pos=pos, nrm=nrm, tan=np.zeros((n, 4)), uv=np.zeros((n, 2)),
                joints=joints, weights=weights, tris=tris)
    k = {'bones': dict(names=['BASE', 'Hip'], parents=[-1, 0], world=world), 'prims': [prim], 'parts': {}}
    joints[:, 0] = 1
    return k, np.arange(len(sim))


def springs_of(k, chains_):
    """cloth.springs of chains (rig()'s, of k's bones) in a made-up skeleton -> (its result, the chains'
    bone indices in it, its bone names)."""
    names = ['cha:HARA_ROT1', 'cha:KOSHI_jnt', 'cha:HIZA_R_jnt', 'cha:HIZA_L_jnt']
    world = [np.eye(4) for _ in names]
    world[1][1, 3], world[2][1, 3], world[3][1, 3] = 1100, 500, 500
    made, number = [], cloth.OPT_FIRST
    for c, chain in enumerate(chains_):
        idx = []
        for j, b in enumerate(chain['bones']):
            idx.append(len(names))
            names.append('cha:OPT%d_cloth0_%d_%d' % (number, c, j))
            world.append(k['bones']['world'][b])
            number += 1
        made.append(idx)
    for name, y in (('MOMO_R_jnt', 1000), ('MOMO_L_jnt', 1000), ('ASHI_R_jnt', 100), ('ASHI_L_jnt', 100),
                    ('MUNE1_jnt', 1150), ('MUNE2_jnt', 1300), ('KUBI_jnt', 1500), ('ATAMA_jnt', 1600)):
        names.append('cha:' + name)
        world.append(np.eye(4))
        world[-1][:3, 3] = (100 if '_L_' in name else -100 if '_R_' in name else 0, y, 0)
    for name in [a for pair in cloth.OTHER for a in pair]:
        if 'cha:' + name not in names:
            names.append('cha:' + name)
            world.append(np.eye(4))
            world[-1][:3, 3] = (500, 1400, 0)
    world[2][:3, 3], world[3][:3, 3] = (-100, 500, 0), (100, 500, 0)
    skel = dict(names=names, parent=[-1] * len(names))
    body = np.array([(x, y, z) for x in (-100, 100) for y in range(150, 1000, 25) for z in (-60, 60)]
                    + [(x, y, z) for x in (-60, 60) for y in range(1000, 1500, 25) for z in (-90, 90)], float)
    cloth_bone = types.SimpleNamespace(world_matrices=lambda s: np.array(world))
    saved, cloth.bone = cloth.bone, cloth_bone
    try:
        return cloth.springs(skel, made, chains_, body), made, names
    finally:
        cloth.bone = saved


class Rig(unittest.TestCase):
    def setUp(self):
        self.asset = skirt()
        self.k, self.drawn = model(self.asset)
        self.made = cloth.rig(self.k, [dict(part='bdu', asset=self.asset, vertices=self.drawn, name='skirt')],
                              log=lambda s: None)

    def test_chains_round_the_waist_hanging_down(self):
        self.assertGreaterEqual(len(self.made), 6)
        world = self.k['bones']['world']
        for c in self.made:
            ys = [world[b][1, 3] for b in c['bones']]
            self.assertTrue(all(a > b for a, b in zip(ys, ys[1:])))           # each bone below the one before
            self.assertEqual(c['parent'], 1)                                   # hung from Hip
            self.assertEqual(len(c['neighbours']), 2)                          # a closed ring: two neighbours each
            x = world[c['bones'][0]][:3, 0]
            self.assertLess(x[1], -0.8)                                        # local X points down

    def test_skinned_to_the_chains_below_the_waist_only(self):
        s = self.k['prims'][0]
        first = min(b for c in self.made for b in c['bones'])
        sim = self.asset.max_distance
        cloth_w = np.where(s['joints'] >= first, s['weights'], 0).sum(1)[self.drawn]
        np.testing.assert_allclose(s['weights'].sum(1), 1.0, atol=1e-9)
        self.assertTrue(np.all(cloth_w[sim == 0] == 0))                        # the pinned ring keeps Hip
        self.assertTrue(np.all(cloth_w[sim >= 30] > 0.99))                     # the skirt below hangs on chains
        self.assertTrue(np.all((s['weights'] > 0).sum(1) <= 8))

    def test_long_cloth_parents_only_when_named(self):
        chains_ = [{'bones': [1, 2, 3]}, {'bones': [4, 5, 6, 7]}, {'bones': [8, 9, 10, 11], 'spring': {'flags': 1}}]
        names = ['cha:A', 'cha:B', 'cha:CHEST']
        self.assertEqual(cloth.long_cloth_parents(chains_, [0, 1, 1], names, {'links': 4}), [0, 1, 1])
        self.assertEqual(cloth.long_cloth_parents(chains_, [0, 1, 1], names, {'links': 4, 'parent': 'CHEST'}), [0, 2, 1])

    def test_swing_limits_follow_each_links_own_axes(self):
        spring = {'flags': 0x60, 'swing': {'back': (0.0, 0.0, -1.0), 'towards': 0.1, 'against': 0.04, 'across': 0.02}}
        # a link along -Y with its own Y facing back: back is its +Y, reached by a positive angle about Z
        frame = np.eye(4)
        frame[:3, :3] = np.stack([[0.0, -1.0, 0.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]], 1)
        y_up, y_down, z_up, z_down = cloth._swing_limits(spring, frame)['limits']
        self.assertAlmostEqual(z_up, 0.1)
        self.assertAlmostEqual(z_down, -0.04)
        self.assertAlmostEqual(y_up, 0.02)
        self.assertAlmostEqual(y_down, -0.02)
        # its Y facing sideways, its Z forward: back is its -Z, reached by a positive angle about Y
        frame[:3, :3] = np.stack([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], 1)
        y_up, y_down, z_up, z_down = cloth._swing_limits(spring, frame)['limits']
        self.assertAlmostEqual(y_up, 0.1)
        self.assertAlmostEqual(y_down, -0.04)
        self.assertAlmostEqual(z_up, 0.02)
        self.assertAlmostEqual(z_down, -0.02)

    def test_swing_limits_per_length(self):
        spring = {'flags': 0x60, 'swing': {'back': (0.0, 0.0, -1.0), 'towards': 0.1, 'against': 0.04, 'across': 0.02,
                                           'per': 100.0}}
        frame = np.eye(4)
        frame[:3, :3] = np.stack([[0.0, -1.0, 0.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]], 1)
        y_up, y_down, z_up, z_down = cloth._swing_limits(spring, frame, 250.0)['limits']
        self.assertAlmostEqual(z_up, 0.25)                      # a link 2.5 x 'per' long swings 2.5 x as far
        self.assertAlmostEqual(z_down, -0.1)
        self.assertAlmostEqual(y_up, 0.05)
        self.assertAlmostEqual(cloth._swing_limits(spring, frame)['limits'][2], 0.1)    # (no length: as given)
        del spring['swing']['per']
        self.assertAlmostEqual(cloth._swing_limits(spring, frame, 250.0)['limits'][2], 0.1)   # (no 'per': per link)

    def test_long_cloth_takes_the_definitions_spring(self):
        spec = {'links': 4, 'spring': {'flags': 0x60}}
        own = {'flags': 1}
        chains = [{'bones': [1, 2, 3, 4]}, {'bones': [5, 6]}, {'bones': [7, 8, 9, 10, 11], 'spring': own}]
        cloth.long_cloth(chains, spec)
        self.assertIs(chains[0]['spring'], spec['spring'])
        self.assertNotIn('spring', chains[1])
        self.assertIs(chains[2]['spring'], own)

    def test_a_cloths_own_spring_and_body_parent(self):
        k, drawn = model(self.asset)
        k['bones'] = dict(names=['BASE', 'Hip', 'OPT1_bustL'], parents=[-1, 0, 1],
                          world=np.concatenate([k['bones']['world'], k['bones']['world'][1:]]))
        k['prims'][0]['joints'][:, 0] = 2                                  # (skinned to a bone the game swings)
        own = dict(flags=0x60, parameters=(20.0, 70.0, 40.0), limits=(1.0, -1.0, 1.5, -1.5), last=0.2)
        made = cloth.rig(k, [dict(part='bdu', asset=self.asset, vertices=drawn, name='skirt', spring=own)],
                         log=lambda s: None)
        self.assertEqual({c['parent'] for c in made}, {2})
        self.assertTrue(all(c['spring'] is own for c in made))
        k, drawn = model(self.asset)
        k['bones'] = dict(names=['BASE', 'Hip', 'OPT1_bustL'], parents=[-1, 0, 1],
                          world=np.concatenate([k['bones']['world'], k['bones']['world'][1:]]))
        k['prims'][0]['joints'][:, 0] = 2
        made = cloth.rig(k, [dict(part='bdu', asset=self.asset, vertices=drawn, name='skirt', body_parent=True)],
                         log=lambda s: None)
        self.assertEqual({c['parent'] for c in made}, {1})                 # (Hip, not the bust)
        self.assertNotIn('spring', made[0])
        self.assertNotIn('spring', self.made[0])                          # (none of its own: Tekken 7's cloth)

    def test_never_onto_a_chain_of_the_other_leg(self):
        """A skirt hung from the left thigh (its pinned ring skinned to it): its vertices skinned to the right thigh
        alone stay skinned to it (they would join the legs, as Miary Zo's ankle boards did), those skinned to both
        thighs or to the hips go on the chains."""
        k, drawn = model(self.asset)
        world = np.tile(np.eye(4), (4, 1, 1))
        world[1:, :3, 3] = (0, 1100, 0)
        k['bones'] = dict(names=['BASE', 'Hip', 'L_UpLeg', 'R_UpLeg'], parents=[-1, 0, 1, 1], world=world)
        s = k['prims'][0]
        sim, x = self.asset.max_distance, cloth._points(self.asset.vertices)[:, 0]
        s['joints'][drawn[sim == 0], 0] = 2                                 # (the ring: the chains hang from L_UpLeg)
        right = drawn[(sim >= 30) & (x < -5)]
        both = drawn[(sim >= 30) & (np.abs(x) <= 5)]
        s['joints'][right, 0] = 3
        s['joints'][both, 0], s['joints'][both, 1] = 3, 2
        s['weights'][both, 0], s['weights'][both, 1] = 0.5, 0.5
        lines = []
        made = cloth.rig(k, [dict(part='bdu', asset=self.asset, vertices=drawn, name='skirt')], log=lines.append)
        self.assertEqual({c['parent'] for c in made}, {2})
        first = min(b for c in made for b in c['bones'])
        on_chains = np.where(s['joints'] >= first, s['weights'], 0).sum(1)
        self.assertTrue(len(right) and (on_chains[right] == 0).all())
        self.assertTrue((s['joints'][right, 0] == 3).all())
        self.assertTrue(len(both) and (on_chains[both] > 0.99).all())
        self.assertTrue((on_chains[drawn[(sim >= 30) & (x > 5)]] > 0.99).all())
        self.assertTrue(any('%d vertices left skinned to their own arm or leg' % len(right) in l for l in lines))

    def _legged(self, **options):
        """The skirt with its pinned ring on the hips, its left half (x > 0) skinned below it to the left thigh, its
        right half to the right one; -> rig()'s chains, k, the drawn vertices."""
        k, drawn = model(self.asset)
        world = np.tile(np.eye(4), (4, 1, 1))
        world[1:, :3, 3] = (0, 1100, 0)
        k['bones'] = dict(names=['BASE', 'Hip', 'L_UpLeg', 'R_UpLeg'], parents=[-1, 0, 1, 1], world=world)
        s = k['prims'][0]
        free, x = self.asset.max_distance > 0, cloth._points(self.asset.vertices)[:, 0]
        s['joints'][drawn[free & (x > 0)], 0] = 2
        s['joints'][drawn[free & (x < 0)], 0] = 3
        made = cloth.rig(k, [dict(part='bdu', asset=self.asset, vertices=drawn, name='skirt', **options)],
                         log=lambda s: None)
        return made, k, drawn

    def test_a_cloth_skinned_to_a_thigh_hangs_from_it(self):
        """Tekken 8 skins Miary Zo's sarong below her hip to her left thigh alone: hung from the hips, her stance
        turned the thigh into the cloth's rest."""
        made, _, _ = self._legged(leg_parent=True, leg_moves=True)
        parents = {c['parent'] for c in made}
        self.assertEqual(parents, {2, 3})                                  # (each half from its own thigh)
        for c in made:
            self.assertEqual(c['leg'], 'L' if c['parent'] == 2 else 'R')
        made, _, _ = self._legged()
        self.assertEqual({c['parent'] for c in made}, {1})                 # (without it: the hips, as Tekken 7's)
        self.assertNotIn('leg', made[0])

    def test_held_by_no_leg_it_stays_on_the_hips(self):
        """Skinned to the hips (Reina's jacket), or half and half to both thighs: no leg holds it."""
        k, drawn = model(self.asset)
        world = np.tile(np.eye(4), (4, 1, 1))
        world[1:, :3, 3] = (0, 1100, 0)
        k['bones'] = dict(names=['BASE', 'Hip', 'L_UpLeg', 'R_UpLeg'], parents=[-1, 0, 1, 1], world=world)
        s = k['prims'][0]
        free = drawn[self.asset.max_distance > 0]
        s['joints'][free, 0], s['joints'][free, 1], s['joints'][free, 2] = 1, 2, 3
        s['weights'][free, 0], s['weights'][free, 1], s['weights'][free, 2] = 0.2, 0.4, 0.4
        made = cloth.rig(k, [dict(part='bdu', asset=self.asset, vertices=drawn, name='skirt', leg_parent=True)],
                         log=lambda s: None)
        self.assertEqual({c['parent'] for c in made}, {1})

    def test_hung_from_a_thigh_it_keeps_its_own_weights_longer(self):
        """The chain's root rides the thigh: a vertex a link below the waist is still on the chain, one 80 mm below it
        (past BLEND, within LEG_BLEND) keeps its own weights in part."""
        def on_chains(k, drawn, made):
            s = k['prims'][0]
            first = min(b for c in made for b in c['bones'])
            return np.where(s['joints'] >= first, s['weights'], 0).sum(1)[drawn]
        made, k, drawn = self._legged(leg_parent=True)
        hung = on_chains(k, drawn, made)
        made, k, drawn = self._legged()
        plain = on_chains(k, drawn, made)
        row = self.asset.max_distance.astype(int) // 10                    # (10 cm a row, 80 mm apart)
        self.assertTrue((plain[row == 1] > 0.99).all())
        self.assertAlmostEqual(float(np.median(hung[row == 1])), 81.0 / cloth.LEG_BLEND, delta=0.05)
        x = cloth._points(self.asset.vertices)[:, 0]
        self.assertTrue((hung[(row >= 3) & (np.abs(x) > 100)] > 0.99).all())
        self.assertTrue((hung[row == 0] == 0).all() and (plain[row == 0] == 0).all())

    def test_limbs(self):
        names = ['BASE', 'Hip', 'L_UpLeg', 'L_Leg', 'sim_ankle_board', 'R_UpLeg', 'Spine1', 'R_Arm', 'R_Hand']
        k = {'bones': dict(names=names, parents=[-1, 0, 1, 2, 3, 1, 1, 6, 7])}
        got = [cloth._limb(k, i) for i in range(len(names))]
        self.assertEqual(got, [None, None, ('leg', 'L'), ('leg', 'L'), ('leg', 'L'), ('leg', 'R'), None,
                               ('arm', 'R'), ('arm', 'R')])

    def test_spring_entries_pairs_and_links(self):
        sp, made, names = springs_of(self.k, self.made)
        self.assertEqual(len(sp['entries']), sum(map(len, made)))
        tops = {cloth.OPT_FIRST + sum(map(len, made[:c])) for c in range(len(made))}
        self.assertFalse(any(n in tops for n, _ in sp['pairs']))               # top bones touch no capsule
        self.assertTrue(sp['links'])
        self.assertTrue(sp['pairs'])
        self.assertGreaterEqual(len(sp['capsules']), 5)                       # (a made-up body: no hips)
        caps = {names[b]: size for b, _, size in sp['capsules']}
        self.assertGreater(caps['cha:MOMO_R_jnt'][1], cloth.LEG_MARGIN)          # round the thigh: its radius and more
        self.assertEqual({j for _, _, j in sp['links']}, set(range(min(map(len, made)))))


class Hair(unittest.TestCase):
    """What of Tekken 8's hair swings (rig 'hair'): its own spring entries, no capsules."""

    def setUp(self):
        self.asset = skirt()
        self.k, self.drawn = model(self.asset)

    def test_rig_marks_the_hairs_chains_and_leaves_out_what_makes_none(self):
        lines = []
        made = cloth.rig(self.k, [dict(part='har', asset=self.asset, vertices=self.drawn, name='hair', hair=True),
                                  dict(part='har', asset=skirt(rows=2), vertices=np.zeros(0, np.int64), name='short',
                                       hair=True)], log=lines.append)
        self.assertGreaterEqual(len(made), 6)
        self.assertTrue(all(c.get('hair') for c in made))
        self.assertEqual([x.split(':')[0].strip() for x in lines], ['hair'])     # (no line for a cloth making none)
        k, drawn = model(self.asset)
        self.assertNotIn('hair', cloth.rig(k, [dict(part='bdu', asset=self.asset, vertices=drawn, name='skirt')],
                                           log=lambda s: None)[0])

    def test_hair_has_its_own_entries_and_touches_no_capsule(self):
        made = cloth.rig(self.k, [dict(part='bdu', asset=self.asset, vertices=self.drawn, name='skirt')],
                         log=lambda s: None)
        own = dict(flags=0x60, parameters=(20.0, 70.0, 20.0), limits=(0.6, -0.6, 1.2, -0.05), last=0.2)
        mixed = [dict(c, hair=True, spring=own) if i % 2 else c for i, c in enumerate(made)]
        sp, bones, names = springs_of(self.k, mixed)
        number = {i: int(names[i].split('_')[0][7:]) for chain in bones for i in chain}
        hair = {number[i] for c, chain in zip(mixed, bones) if c.get('hair') for i in chain}
        rest = {number[i] for c, chain in zip(mixed, bones) if not c.get('hair') for i in chain}
        self.assertEqual({e[0] for e in sp['entries']}, hair | rest)               # (every bone has its entry ..
        self.assertTrue(all(e[3] is own for e in sp['entries'] if e[0] in hair))   # .. the hair's its own)
        self.assertFalse({n for n, _ in sp['pairs']} & hair)                       # (no pairs for the hair)
        self.assertTrue({n for n, _ in sp['pairs']} & rest)
        world = np.tile(np.eye(4), (3, 1, 1))                     # a chain 130 mm behind the chest ..
        world[:, :3, 3] = [(0, 1200.0 - 60 * j, -130.0) for j in range(3)]
        n = len(self.k['bones']['world'])
        k = dict(self.k, bones=dict(self.k['bones'], world=np.concatenate([self.k['bones']['world'], world])))
        back = dict(part='har', bones=[n, n + 1, n + 2], neighbours=set(), parent=0)
        sizes = lambda sp: [tuple(np.round(c[2], 3)) for c in sp['capsules']]
        plain, _, _ = springs_of(k, made)
        cloth_, _, _ = springs_of(k, made + [back])
        hair_, _, _ = springs_of(k, made + [dict(back, hair=True, spring=own)])
        self.assertNotEqual(sizes(cloth_), sizes(plain))                 # .. as cloth it fits the chest's capsule,
        self.assertEqual(sizes(hair_), sizes(plain))                     # as hair not
        self.assertEqual(len(hair_['pairs']), len(plain['pairs']))
        self.assertGreater(len(cloth_['pairs']), len(plain['pairs']))
        self.assertEqual(len(hair_['entries']), len(plain['entries']) + 3)


def entry(number, pairs=0, links=0):
    e = bytearray(cloth.MOP_ENTRY)
    struct.pack_into('>I11f', e, 0, number, 30, 10, 70, 200, .05, -.05, .2, -.04, 1, 1, .05)
    struct.pack_into('>III', e, 0x30, 0x60, pairs, links)
    return bytes(e)


def mop(entries, capsules=(), tail=b''):
    return (struct.pack('>f', 5.0) + bytes(28) + struct.pack('>I', len(entries)) + bytes(12) + b''.join(entries)
            + struct.pack('>I', len(capsules)) + bytes(12) + b''.join(capsules) + tail)


class SpringFile(unittest.TestCase):
    def template(self):
        caps = [struct.pack('>II', 1, b) + bytes(cloth.MOP_CAPSULE - 8) for b in (26, 25, 52, 56)]
        return mop([entry(cloth.TEMPLATE_FIRST + j) for j in range(cloth.TEMPLATE_LINKS)], caps)

    def test_pairs_before_links_and_capsules_numbered_after_the_old(self):
        old_pair = struct.pack('>II8x', 7, 0)
        old_link = struct.pack('>IIff36x', 7, 8, 0.8, 50.0)
        old = mop([entry(7, 1, 1), entry(8)], [struct.pack('>II', 1, 73) + bytes(cloth.MOP_CAPSULE - 8)],
                  old_pair + old_link)
        sp = dict(entries=[(400, 0, 210.0, None), (401, 1, 190.0, (cloth.OUTWARD, None)), (402, 0, 210.0, None),
                           (403, 1, 190.0, (cloth.OUTWARD, cloth.DRAPED_INWARD))],
                  capsules=[(3, (50.0, 0, 0), (100.0, 150, 120)), (14, (200.0, 0, 0), (240.0, 130, 110)),
                            (17, (200.0, 0, 0), (240.0, 130, 110))],
                  pairs=[(401, 2)], links=[(400, 402, 0), (401, 403, 1)])
        out = cloth.spring_file(old, self.template(), sp)
        entries, capsules, pairs, links, rest = cloth.parse(out)
        self.assertEqual(len(entries), 6)
        self.assertEqual(len(capsules), 4)
        self.assertEqual(struct.unpack_from('>II', capsules[3]), (1, 17))
        self.assertEqual(struct.unpack_from('>3f', capsules[3], 32), (200.0, 0.0, 0.0))
        self.assertEqual(struct.unpack_from('>3f', capsules[3], 48), (240.0, 130.0, 110.0))
        self.assertEqual(rest, b'')
        self.assertEqual(pairs, old_pair + struct.pack('>II8x', 401, 1 + 2))
        self.assertEqual(links[:cloth.MOP_LINK], old_link)
        a, b, stiffness, value = struct.unpack_from('>IIff', links, cloth.MOP_LINK * 2)
        self.assertEqual((a, b, value), (401, 403, 80.0))
        self.assertAlmostEqual(stiffness, 0.8, 6)
        e = {struct.unpack_from('>I', x)[0]: x for x in entries}
        self.assertEqual(struct.unpack_from('>II', e[400], 0x34), (0, 1))
        self.assertEqual(struct.unpack_from('>II', e[401], 0x34), (1, 1))
        self.assertAlmostEqual(struct.unpack_from('>f', e[401], 16)[0], 190.0, 3)
        np.testing.assert_allclose(struct.unpack_from('>4f', e[401], 20), (.05, -.05, cloth.OUTWARD, -.04),
                                   atol=1e-6)                                  # (only the outward limit wider)
        np.testing.assert_allclose(struct.unpack_from('>4f', e[403], 20), (.05, -.05, cloth.OUTWARD,
                                                                          -cloth.DRAPED_INWARD), atol=1e-6)
        np.testing.assert_allclose(struct.unpack_from('>4f', e[400], 20), (.05, -.05, .2, -.04), atol=1e-6)

    def test_a_chains_own_spring_entry(self):
        own = dict(flags=0x60, parameters=(20.0, 70.0, 40.0), limits=(1.05, -1.05, 1.57, -1.57), last=0.2)
        out = cloth.spring_file(mop([]), self.template(), dict(entries=[(400, 0, 80.0, own), (401, 1, 24.0, None)],
                                                                capsules=[], pairs=[], links=[]))
        entries = cloth.parse(out)[0]
        e = struct.unpack('>I11fI', entries[0][:0x34])
        np.testing.assert_allclose(e[1:12], (20, 70, 40, 80, 1.05, -1.05, 1.57, -1.57, 1, 1, 0.2), atol=1e-6)
        self.assertEqual(e[12], 0x60)
        self.assertEqual(entries[1], cloth.parse(cloth.spring_file(                        # (the other: Lars's)
            mop([]), self.template(), dict(entries=[(401, 1, 24.0, None)], capsules=[], pairs=[], links=[])))[0][0])

    def test_hair_entries_keep_the_cloth_pairs_and_links(self):
        cl = cloth.spring_file(mop([]), self.template(), dict(entries=[(400, 0, 200.0, None), (401, 1, 200.0, None)],
                                                               capsules=[(3, (0, 0, 0), (100, 100, 100))],
                                                               pairs=[(401, 0)], links=[]))
        lili = mop([entry(160)], [struct.pack('>II', 1, 73) + bytes(cloth.MOP_CAPSULE - 8)])
        out = chains.spring_file(cl, lili, [800], template=160, links=False)
        entries, capsules, pairs, links, rest = cloth.parse(out)
        self.assertEqual(len(entries), 3)
        self.assertEqual(pairs, struct.pack('>II8x', 401, 0))
        self.assertEqual(rest, b'')


class Drape(unittest.TestCase):
    def test_flowing_chain_hangs_hanging_one_stays(self):
        body = np.array([[0.0, 0.0, 0.0]])
        normals = np.array([[0.0, 0.0, 1.0]])
        flowing = np.array([[0, 1400, 300], [0, 1250, 150], [0, 1100, 0.0]])           # 45 degrees behind
        dirs = cloth._drape(flowing + [0, 0, 500], body, normals)
        self.assertIsNotNone(dirs)
        for d in dirs:
            self.assertLess(np.degrees(np.arccos(-d[1])), np.degrees(cloth.HANG) + 0.1)
        hanging = np.array([[0, 1400, 0], [30, 1200, 0], [60, 1000, 0.0]])            # 8.5 degrees out
        self.assertIsNone(cloth._drape(hanging + [0, 0, 500], body, normals))

    def test_kept_outside_the_body(self):
        body = np.array([[0.0, y, 0.0] for y in range(0, 1500, 20)])
        normals = np.tile([0.0, 0.0, 1.0], (len(body), 1))
        flowing = np.array([[0, 1400, 10], [0, 1300, -90], [0, 1200, -190.0]])        # flowing into the body
        dirs = cloth._drape(flowing, body, normals)
        p = flowing[0].copy()
        for i, d in enumerate(dirs):
            p = p + np.linalg.norm(flowing[i + 1] - flowing[i]) * d
            self.assertGreater(p[2], cloth.MARGIN - 1)


def skeleton():
    """A made-up TTT2 skeleton: the 22 body bones in the game's order, every local frame the world's but the legs'
    (local X down them, as the game's)."""
    from ttt2char.ttt2 import bone
    rows = [('HARA_ROT1', -1, (0, 1100, 0)), ('MUNE1_jnt', 0, (0, 0, 0)), ('MUNE2_jnt', 1, (0, 150, 0)),
            ('KOSHI_jnt', 0, (0, 0, 0)), ('KUBI_jnt', 2, (0, 250, 0)), ('ATAMA_jnt', 4, (0, 100, 0)),
            ('SAKOTSU_R_jnt', 2, (-100, 200, 0)), ('KATA_R_jnt', 6, (-100, 0, 0)), ('UDE_R_jnt', 7, (-300, 0, 0)),
            ('TE_R_jnt', 8, (-250, 0, 0)), ('SAKOTSU_L_jnt', 2, (100, 200, 0)), ('KATA_L_jnt', 10, (100, 0, 0)),
            ('UDE_L_jnt', 11, (300, 0, 0)), ('TE_L_jnt', 12, (250, 0, 0)), ('MOMO_R_jnt', 3, (-100, -100, 0)),
            ('HIZA_R_jnt', 14, (450, 0, 0)), ('ASHI_R_jnt', 15, (450, 0, 0)), ('MOMO_L_jnt', 3, (100, -100, 0)),
            ('HIZA_L_jnt', 17, (450, 0, 0)), ('ASHI_L_jnt', 18, (450, 0, 0)), ('TSUMASAKI_R_jnt', 16, (0, 0, 0)),
            ('TSUMASAKI_L_jnt', 19, (0, 0, 0))]
    down = bone.euler_xyz_from_matrix(np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1.0]]))     # local X -> world -Y
    r = [down if n.startswith('MOMO') else np.zeros(3) for n, _, _ in rows]
    return dict(names=['cha:' + n for n, _, _ in rows], parent=[p for _, p, _ in rows],
                t=np.array([t for _, _, t in rows], float), r=np.array(r))


def legs_and_trunk():
    """Body vertices (mm): legs 70 mm thick round x = +-100, a trunk 120 mm thick."""
    ring = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    legs = [(x + 70 * np.cos(t), y, 70 * np.sin(t)) for x in (-100, 100) for y in range(150, 1000, 25) for t in ring]
    trunk = [(120 * np.cos(t), y, 120 * np.sin(t)) for y in range(1000, 1500, 25) for t in ring]
    return np.array(legs + trunk, float)


class Settle(unittest.TestCase):
    def test_cloth_rests_outside_a_thigh_that_stands_forward(self):
        from ttt2char.ttt2 import animation, bone
        asset = skirt(radius=17.0)
        k, drawn = model(asset)
        made = cloth.rig(k, [dict(part='bdu', asset=asset, vertices=drawn, name='skirt')], log=lambda s: None)
        skel = skeleton()
        values = np.zeros((len(animation.BODY_BONES), 3), np.float32)
        for c, b in enumerate(animation.BODY_BONES):
            if b >= 0:
                values[c] = skel['r'][b]
        values[1] = (0, 1100, 0)
        forward = np.radians(40.0)                                             # the left thigh: knee forward (+z)
        tilt = np.array([[1, 0, 0], [0, np.cos(forward), np.sin(forward)], [0, -np.sin(forward), np.cos(forward)]])
        values[animation.BODY_BONES.index(17)] = bone.euler_xyz_from_matrix(
            tilt @ bone.matrix_from_euler_xyz(skel['r'][17]))
        still = (values, animation.RAW)
        posed = cloth.pose(skel, still)
        self.assertGreater(posed[18][2, 3], 250)                               # (the left knee stands forward)
        before = k['bones']['world'].copy()
        pos = k['prims'][0]['pos'].copy()
        body = legs_and_trunk()
        legs = [c for c in cloth.capsules(skel, body) if skel['names'][c[0]][4:8] in ('MOMO', 'HIZA')]
        to_pose = posed[3] @ np.linalg.inv(bone.world_matrices(skel)[3])

        def outside(world, b, t=1.0):
            p, up = (to_pose @ world[b])[:3, 3], (to_pose @ world[b - 1])[:3, 3]
            p = up + t * (p - up)
            return min(np.linalg.norm(((p - posed[at][:3, 3]) @ posed[at][:3, :3] - offset) /
                                      (size + cloth.SETTLE_MARGIN)) for at, offset, size in legs)
        hit = [c for c in made if min(outside(before, b, t) for b in c['bones'][1:] for t in cloth.SETTLE_ALONG) < 1]
        free = [c for c in made if c not in hit]
        self.assertTrue(hit and free)
        turned, moved = cloth.settle(k, made, skel, [3] * len(made), still, body)
        self.assertGreater(turned, 0)
        self.assertGreater(moved, 0)
        world = k['bones']['world']
        for chain in made:
            for b in chain['bones'][1:]:
                for t in cloth.SETTLE_ALONG:
                    self.assertGreater(outside(world, b, t), 0.99)             # outside the leg, standing
        self.assertTrue(all(c.get('draped') for c in hit))
        self.assertFalse(any(c.get('draped') for c in free))
        for c in hit:                                                          # turned off it, at rest too
            self.assertGreater(max(np.linalg.norm(world[b][:3, 3] - before[b][:3, 3]) for b in c['bones']), 1)
        for c in free:                                                         # clear of it: untouched
            np.testing.assert_allclose(world[c['bones'][-1]], before[c['bones'][-1]])
        self.assertTrue(np.any(np.abs(k['prims'][0]['pos'] - pos) > 20))     # its vertices followed
        np.testing.assert_allclose(k['prims'][0]['pos'][len(drawn):], pos[len(drawn):])   # the body did not


class Capsules(unittest.TestCase):
    def hung(self, x, leg=None):
        """cloth.springs of a chain beside the left shin, `x` mm from the skeleton's middle -> {capsule's bone: sizes}."""
        skel = skeleton()
        n = len(skel['names'])
        places = np.array([(x, -300, 0), (0, -150, 0), (0, -250, 0)], float)    # (hung from KOSHI: y 800, 650, 400)
        skel = dict(names=skel['names'] + ['cha:OPT%d_cloth0_0_%d' % (400 + j, j) for j in range(3)],
                    parent=skel['parent'] + [3, n, n + 1], t=np.concatenate([skel['t'], places]),
                    r=np.concatenate([skel['r'], np.zeros((3, 3))]))
        chain = dict(part='bdf', bones=[0, 1, 2], neighbours=set(), parent=3)
        if leg:
            chain['leg'] = leg
        out = cloth.springs(skel, [[n, n + 1, n + 2]], [chain], legs_and_trunk())
        return {skel['names'][b][4:]: size for b, _, size in out['capsules']}, skel

    def test_cloth_hung_from_a_leg_grows_no_capsule(self):
        """A chain beside the left shin. Not hung from a leg, the capsules scale to reach it: both shins' (and thighs')
        thicker than the body's, up to GROW (her sarong's tip and the other foot's strands made them eggs 23 cm thick,
        reaching across the other leg). Hung from the left leg, nothing grows."""
        plain, skel = self.hung(250)
        hung, _ = self.hung(250, 'L')
        fitted = {skel['names'][b][4:]: size for b, _, size in cloth.capsules(skel, legs_and_trunk())}
        for name in ('HIZA_R_jnt', 'HIZA_L_jnt'):
            self.assertGreater(plain[name][1], 1.5 * fitted[name][1])
            np.testing.assert_allclose(hung[name], fitted[name])
        np.testing.assert_allclose(hung['KOSHI_jnt'], fitted['KOSHI_jnt'])

    def test_a_legs_own_capsule_may_shrink_to_it(self):
        """A chain resting just inside the left shin's capsule: only that capsule shrinks to touch it (a bone wholly
        inside is never pushed), no further than SHRINK; the other leg's stays."""
        _, skel = self.hung(100)
        fitted = {skel['names'][b][4:]: size for b, _, size in cloth.capsules(skel, legs_and_trunk())}
        hung, _ = self.hung(100 + 0.9 * fitted['HIZA_L_jnt'][1], 'L')
        self.assertLess(hung['HIZA_L_jnt'][1], fitted['HIZA_L_jnt'][1])
        self.assertGreaterEqual(hung['HIZA_L_jnt'][1], cloth.SHRINK * fitted['HIZA_L_jnt'][1] - 1e-6)
        np.testing.assert_allclose(hung['HIZA_R_jnt'], fitted['HIZA_R_jnt'])


class Graph(unittest.TestCase):
    def test_geodesic_from_the_pinned(self):
        pts = np.array([[0, 0, 0], [0, -10, 0], [0, -20, 0], [5, -20, 0.0]])
        _, adj = cloth._edges(np.array([[0, 1, 2], [1, 2, 3]]), 4)
        g, src = cloth._hang(pts, np.array([True, False, False, False]), adj)
        np.testing.assert_allclose(g[:3], [0, 10, 20])
        self.assertTrue(np.all(src == 0))

    def test_spread_covers(self):
        pts = np.array([[x, 0, 0] for x in range(0, 1000, 10)], float)
        chosen = cloth._spread(pts, 100)
        d = np.min(np.abs(pts[:, None, 0] - pts[chosen][None, :, 0]), 1)
        self.assertLessEqual(d.max(), 100)
        self.assertLess(len(chosen), 12)


if __name__ == '__main__':
    unittest.main()
