"""Unit tests of Tekken 8's strands (tekken8/cloth.py) and what convert/cloth.py does with them, on made-up data (no
game files needed).

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char import source as sources                       # noqa: E402
from ttt2char.convert import cloth, model as convert_model     # noqa: E402
from ttt2char.tekken8 import cloth as cloth8                   # noqa: E402


def hook(names, lists, junk=b''):
    """A Catwalk hook as the meshes keep it: junk, the simulation meshes' name map, then the vertex lists
    [(section, simulation mesh, kind, vertices, shares 0..1, m)] (m constraint words a vertex: 0xFFFF)."""
    b = bytearray(junk)
    b += struct.pack('<I', len(names))
    for i, name in enumerate(names):
        raw = name.encode('ascii') + b'\0'
        b += struct.pack('<I', len(raw)) + raw + struct.pack('<I', i)
    b += struct.pack('<I', len(lists))
    for section, sim, kind, vertices, shares, m in lists:
        words = [int(round(s * 65535)) << 16 for s in shares]
        body = list(vertices) + words + [0xFFFF] * (len(vertices) * m)
        b += struct.pack('<I', len(body)) + struct.pack('<%dI' % len(body), *body)
        b += struct.pack('<4I', m, section, sim, kind)
    return bytes(b + b'\x01\x00\x00\x00tail')


class Hook(unittest.TestCase):
    NAMES = ['|a_gp|sim_mesh_group|sim_mesh_jacket|sim_mesh_jacketShape', '|a_gp|sim_mesh_group|sim_mesh_cord|cS']
    LISTS = [(1, 0, 0, [0, 1, 2, 5], [0.0, 1.0, 1.0, 0.5], 8), (1, 1, 0, [6, 7], [0.0, 1.0], 4),
             (0, 0, 1, [3, 9, 10], [0.2, 0.2, 0.2], 6)]

    def test_name_map_and_lists(self):
        b = hook(self.NAMES, self.LISTS)
        names, p = cloth8._name_map(b, 0, len(b))
        self.assertEqual(names, {0: self.NAMES[0], 1: self.NAMES[1]})
        lists = cloth8._lists(b, p, len(b), [20, 8])
        self.assertEqual([(s, m, k, v.tolist()) for s, m, k, v, _ in lists],
                         [(1, 0, 0, [0, 1, 2, 5]), (1, 1, 0, [6, 7]), (0, 0, 1, [3, 9, 10])])
        self.assertEqual(((lists[0][4] >> 16) / 65535.0).round(3).tolist(), [0.0, 1.0, 1.0, 0.5])

    def test_look_alikes_before_it_are_skipped(self):
        junk = struct.pack('<II', 1, 4) + b'abc\0' + struct.pack('<I', 7) + b'\0' * 9    # number 7 of one name
        b = hook(self.NAMES, self.LISTS, junk)
        names, p = cloth8._name_map(b, 0, len(b))
        self.assertEqual(sorted(names), [0, 1])
        self.assertIsNotNone(cloth8._lists(b, p, len(b), [20, 8]))

    def test_lists_out_of_their_section_do_not_parse(self):
        b = hook(self.NAMES, self.LISTS)
        _, p = cloth8._name_map(b, 0, len(b))
        self.assertIsNone(cloth8._lists(b, p, len(b), [20, 7]))           # section 1 has only 7 vertices
        self.assertIsNone(cloth8._lists(b, p, len(b) - 40, [20, 8]))      # cut short

    def test_catwalk_shares_meshes_and_driven_vertices(self):
        b = hook(self.NAMES, self.LISTS)
        sections = [types.SimpleNamespace(num_vertices=20, cloth_mapping=0),
                    types.SimpleNamespace(num_vertices=8, cloth_mapping=1)]
        m = types.SimpleNamespace(lods=[types.SimpleNamespace(sections=sections)],
                                  package=types.SimpleNamespace(data=b))
        saved = cloth8.hook_offset
        cloth8.hook_offset = lambda mesh: (0, len(b))
        try:
            data = cloth8.catwalk(m)
        finally:
            cloth8.hook_offset = saved
        self.assertEqual(sorted(data['moved']), [1])
        self.assertEqual(data['moved'][1].round(3).tolist(), [0, 1, 1, 0, 0, 0.5, 0, 1])
        self.assertEqual(data['mesh_of'][1].tolist(), [0, 0, 0, -1, -1, 0, 1, 1])
        self.assertEqual(data['driven'][(0, 0)].tolist(), [3, 9, 10])
        sections[1].cloth_mapping = 0
        self.assertIsNone(cloth8.catwalk(m))                                # no simulation section: no hook read


# ------------------------------------------------------------------------------------------------ made-up costume
def ladder(start, step, rungs, across=(0.0, 3.0, 0.0)):
    """A strip two vertices wide (cm): rung r at start + r * step, its two sides `across` apart."""
    v = [np.asarray(start, float) + r * np.asarray(step, float) + s * np.asarray(across, float)
         for r in range(rungs) for s in (0, 1)]
    t = [(2 * r + a, 2 * r + b, 2 * r + c) for r in range(rungs - 1) for a, b, c in ((0, 1, 2), (1, 3, 2))]
    return np.array(v), np.array(t)


def sheet(x0, x1, z0, z1, n=5):
    """A flat grid in the x-z plane (cm, y 0): a jacket's front."""
    v = np.array([(x, 0.0, z) for z in np.linspace(z1, z0, n) for x in np.linspace(x0, x1, n)])
    t = [(r * n + c, r * n + c + 1, (r + 1) * n + c) for r in range(n - 1) for c in range(n - 1)]
    t += [(r * n + c + 1, (r + 1) * n + c + 1, (r + 1) * n + c) for r in range(n - 1) for c in range(n - 1)]
    return v, np.array(t)


class Strands(unittest.TestCase):
    def test_a_cord_sewn_on_the_jacket_is_found(self):
        jacket, jt = sheet(-20, 20, 90, 140)                               # a corner at (20, 0, 90)
        cord, ct = ladder((20, 0, 90), (2.5, 0, -2.5), 8)                  # out and down, sewn on at its top
        loose, lt = ladder((0, 15, 120), (3, 0, 0), 8)                     # nothing holds it
        half, ht = ladder((-20, 0, 90), (-2.5, 0, -2.5), 8)                # the solver moves it half at most
        parts = [(jacket, jt), (cord, ct), (loose, lt), (half, ht)]
        pos, tris, base = [], [], 0
        for v, t in parts:
            pos.append(v)
            tris.append(t + base)
            base += len(v)
        pos, tris = np.concatenate(pos), np.concatenate(tris)
        moved = np.ones(len(pos))
        moved[:5] = 0.0                                                    # the jacket's top row follows the skin
        a = len(jacket) + len(cord) + len(loose)
        moved[a:] = 0.5
        found = cloth8.strands(pos, tris, moved)
        self.assertEqual(len(found), 1)                                    # the jacket is wide, not a strand
        v, hangs, t = found[0]
        self.assertEqual(v.tolist(), list(range(len(jacket), len(jacket) + len(cord))))
        self.assertEqual(np.nonzero(hangs)[0].tolist(), [0])               # hung from its sewn-on corner
        self.assertEqual(len(t), len(ct))


def costume():
    """A made-up Tekken 8 body mesh: a drawn section (a jacket front with a cord sticking out from its corner, as
    drawn) and a simulation section (the same shapes), as tekken8.mesh reads one, and the model tekken8.model makes
    of it (one joint, Hip, at the origin: the re-pose changes nothing)."""
    jacket, jt = sheet(-20, 20, 90, 140)
    cord, ct = ladder((20, 0, 90), (3.0, 0, -1.5), 9)                      # 27 cm out and down, 63 degrees
    sim = np.concatenate([jacket, cord])
    simt = np.concatenate([jt, ct + len(jacket)])
    drawn = sim + (0, 0.3, 0)                                              # drawn just in front of it
    positions = np.concatenate([drawn, sim]).astype(np.float32)
    n = len(sim)
    sections = [types.SimpleNamespace(num_vertices=n, base_vertex=0, cloth_mapping=0, material_index=0),
                types.SimpleNamespace(num_vertices=n, base_vertex=n, cloth_mapping=1, material_index=1)]
    geo = {'positions': positions, 'normals': np.tile(np.float32([0, 1, 0]), (2 * n, 1)),
           'joints': np.zeros((2 * n, 8), np.int64), 'weights': np.tile(np.float32([1, 0, 0, 0, 0, 0, 0, 0]),
                                                                          (2 * n, 1)),
           'triangles': [simt, simt + n]}
    pose = np.array([[0, 0, 0, 1, 0, 0, 0, 1, 1, 1]], np.float64)
    mesh = types.SimpleNamespace(lods=[types.SimpleNamespace(sections=sections, num_vertices=2 * n)],
                                 skeleton={'names': ['Hip'], 'parents': [-1], 'pose': pose},
                                 geometry=lambda lod=0: geo)
    moved = np.ones(n)
    moved[:5] = 0.0
    data = {'meshes': {0: '|g|sim_mesh_jacket|sim_mesh_jacketShape'}, 'moved': {1: moved},
            'mesh_of': {1: np.zeros(n, np.int64)}, 'driven': {(0, 0): np.arange(n)}}
    cm = convert_model
    pos = cm._ue_to_ttt2_points(positions).astype(np.float64) * cm.M_TO_MM
    nrm = np.tile([0.0, 0.0, 1.0], (2 * n, 1))
    joints = np.zeros((2 * n, 8), np.int64)
    weights = np.zeros((2 * n, 8))
    weights[:, 0] = 1.0
    prim = dict(part='bdf', material='MI_jacket', pos=pos, nrm=nrm, tan=np.zeros((2 * n, 4)), uv=np.zeros((2 * n, 2)),
                joints=joints, weights=weights, tris=simt[:, [0, 2, 1]])
    k = {'bones': dict(names=['Hip'], parents=[-1], world=cloth8._bind_world(mesh)), 'prims': [prim],
         'parts': {'bdf': dict(mesh=mesh, remap=np.array([0]), first=0)}}
    return k, data, len(jacket), len(cord)


class Find(unittest.TestCase):
    def setUp(self):
        self.k, data, self.jacket, self.cord = costume()
        self.saved = cloth8.catwalk
        cloth8.catwalk = lambda mesh: data

    def tearDown(self):
        cloth8.catwalk = self.saved

    def test_the_cord_with_its_drawn_vertices(self):
        found = cloth8.find(self.k, [('bdf', '/Game/x')], log=lambda s: None)
        self.assertEqual(len(found), 1)
        c = found[0]
        self.assertEqual((c['part'], c['link'], c['reach'], c['down']), ('bdf', cloth8.STRAND_LINK,
                                                                          cloth8.STRAND_REACH, None))
        cord = set(range(self.jacket, self.jacket + self.cord))
        self.assertTrue(set(c['vertices'].tolist()) <= cord)               # the jacket's own stay
        self.assertGreater(len(c['vertices']), self.cord - 3)
        self.assertEqual(c['asset'].max_distance[0], 0.0)                  # hung from its top
        np.testing.assert_allclose(cloth._points(c['asset'].vertices)[0],
                                   self.k['prims'][0]['pos'][self.jacket] - (0, 0, 3.0), atol=1e-3)

    def test_it_hangs_after_cloth_add(self):
        found = cloth8.find(self.k, [('bdf', '/Game/x')], log=lambda s: None)
        before = self.k['prims'][0]['pos'].copy()
        made = cloth.add(self.k, found, 100, log=lambda s: None)
        self.assertEqual(len(made), 1)
        world = self.k['bones']['world']
        bones = made[0]['bones']
        self.assertGreaterEqual(len(bones), 4)                             # 27 cm in links of 8
        top, tip = world[bones[0]][:3, 3], world[bones[-1]][:3, 3]
        d = (tip - top) / np.linalg.norm(tip - top)
        self.assertLess(np.degrees(np.arccos(-d[1])), np.degrees(cloth.HANG) + 3)      # down (off the body)
        after = self.k['prims'][0]['pos']
        v = found[0]['vertices']
        far = v[before[v, 0] > 300]                                        # the cord's outer end, as drawn
        self.assertTrue(len(far))
        self.assertTrue((after[far, 0] < 260).all())                       # now below its top (x 200 mm)
        self.assertTrue((after[far, 1] < before[far, 1]).all())
        np.testing.assert_allclose(after[:self.jacket], before[:self.jacket])           # the jacket as it was

    def test_a_strand_lying_on_the_body_or_too_short_stays(self):
        saved = cloth8.LYING, cloth8.STRAND_REACH
        try:
            cloth8.LYING = 1e6
            self.assertEqual(cloth8.find(self.k, [('bdf', '/Game/x')], log=lambda s: None), [])
            cloth8.LYING, cloth8.STRAND_REACH = saved[0], 400.0
            self.assertEqual(cloth8.find(self.k, [('bdf', '/Game/x')], log=lambda s: None), [])
        finally:
            cloth8.LYING, cloth8.STRAND_REACH = saved

    def test_hung_from_an_arm_it_lies_along_it(self):
        k = self.k
        world = np.tile(np.eye(4), (3, 1, 1))
        world[1, :3, 3] = (150, 1400, 0)
        world[2, :3, 3] = (400, 1400, 0)
        k['bones'] = dict(names=['Hip', 'L_Arm', 'L_ForeArm'], parents=[-1, 0, 1], world=world)
        info = dict(k['parts']['bdf'], remap=np.array([1]))
        mesh = info['mesh']
        down, flowing = cloth8._hanging(k, info, mesh.geometry(), np.array([0]), np.array([200.0, 1400, 0]))
        np.testing.assert_allclose(down, [1, 0, 0])
        self.assertEqual(flowing, 0.0)
        info['remap'] = np.array([0])
        self.assertEqual(cloth8._hanging(k, info, mesh.geometry(), np.array([0]), np.zeros(3)),
                         (None, cloth8.STRAND_FLOWING))

    def test_the_source_finds_them(self):
        got = sources.Tekken8Source(None).cloth(self.k, [('bdf', '/Game/x')], log=lambda s: None)
        self.assertEqual(len(got), 1)


class Rig(unittest.TestCase):
    """rig with a cloth's own link, reach, flowing and down; without them Tekken 7's as before."""

    def cloth(self, **own):
        k, data, jacket, cord = costume()
        saved = cloth8.catwalk
        cloth8.catwalk = lambda mesh: data
        try:
            c = cloth8.find(k, [('bdf', '/Game/x')], log=lambda s: None)[0]
        finally:
            cloth8.catwalk = saved
        for key in ('link', 'reach', 'flowing', 'down'):
            c.pop(key)
        c.update(own)
        made = cloth.rig(k, [c], log=lambda s: None)
        return k, made

    def test_defaults_are_tekken_7s(self):
        k1, m1 = self.cloth()
        k2, m2 = self.cloth(link=cloth.LINK, reach=cloth.REACH, flowing=cloth.FLOWING, down=None)
        self.assertEqual([c['bones'] for c in m1], [c['bones'] for c in m2])
        np.testing.assert_array_equal(k1['bones']['world'], k2['bones']['world'])
        np.testing.assert_array_equal(k1['prims'][0]['pos'], k2['prims'][0]['pos'])

    def test_own_link_and_reach(self):
        _, made = self.cloth(link=40.0)
        _, default = self.cloth()
        self.assertGreater(len(made[0]['bones']), len(default[0]['bones']))
        _, made = self.cloth(reach=500.0)
        self.assertEqual(made, [])

    def test_own_flowing_and_down(self):
        k, made = self.cloth(flowing=np.radians(80.0))                     # 63 degrees: modelled hanging, kept
        w = k['bones']['world']
        d = w[made[0]['bones'][-1]][:3, 3] - w[made[0]['bones'][0]][:3, 3]
        self.assertGreater(np.degrees(np.arccos(-d[1] / np.linalg.norm(d))), 40)
        k, made = self.cloth(flowing=0.0, down=np.array([1.0, 0.0, 0.0]))    # laid along +x (an arm)
        w = k['bones']['world']
        d = w[made[0]['bones'][-1]][:3, 3] - w[made[0]['bones'][0]][:3, 3]
        self.assertLess(np.degrees(np.arccos(d[0] / np.linalg.norm(d))), np.degrees(cloth.HANG) + 3)


if __name__ == '__main__':
    unittest.main()
