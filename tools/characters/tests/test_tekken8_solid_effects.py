"""Unit tests of a Tekken 8 effect's solid meshes and a projectile look's place in the measured look
(convert/effects8.py: roles 'solid' and 'dissolve', SOLID_*, ShadedMesh, system8's `at`) on made-up data (no game files
needed).

    python3 -m unittest tests.test_tekken8_solid_effects
"""
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import effects8 as E8, particles as P     # noqa: E402


def measured(dynamic=None, n=E8.CURVE_POINTS):
    """A Measured stand-in: one particle a second, still, white, a mesh scale of 1."""
    m = types.SimpleNamespace(times=[k / (n - 1) for k in range(n)], life=(1.0, 0.0), colour=[(0.7, 0.1, 1.0)] * n,
                              alpha=[1.0] * n, scale=[(1.0, 1.0, 1.0)] * n, size=None, scale_half=0.0,
                              path=[(0.0, 0.0, 0.0)] * n, start_half=(0.0, 0.0, 0.0), speed_half=(0.0, 0.0, 0.0),
                              drifts=[], sprite_turn=None, pre=(0.0, 0.0, 0.0), turn_half=(0.0, 0.0, 0.0),
                              spin=(0.0, 0.0, 0.0), spin_half=(0.0, 0.0, 0.0), dynamic=dynamic)
    return m


def emitter(name='CrystalPillar'):
    return types.SimpleNamespace(name=name, gpu=False, loop=None, rate=0.0, per_unit=False, bursts=[(0.0, 1)],
                                 local=False)


def mesh_renderer(mesh='/Game/SM_Pillar.SM_Pillar', mat='/Game/MI_Crystal.MI_Crystal'):
    return types.SimpleNamespace(kind='mesh', meshes=[(mesh, mat)], material=None, sub_images=(1, 1))


def module(em, cls):
    return next((m for m in em.modules if m.cls == cls), None)


class Solid(unittest.TestCase):
    def test_a_solid_keeps_its_own_colours_and_its_mesh_key(self):
        m = measured()
        em = E8.measured_cascade(emitter(), mesh_renderer(), m, mat='/Game/MI_Crystal.MI_Crystal#solid',
                                 over={'solid': True}, mesh_key=E8.SOLID_MESH + '/Game/SM_Pillar.SM_Pillar')
        self.assertEqual(module(em, 'TypeDataMesh').get('Mesh'), 'solid:/Game/SM_Pillar.SM_Pillar')
        colours = module(em, 'ColorOverLife').dist('ColorOverLife', 3).samples
        self.assertTrue(all(lo == [1.0, 1.0, 1.0] for _, lo, _ in colours))        # (not the particle's violet)
        plain = E8.measured_cascade(emitter(), mesh_renderer(), m, mat='/Game/MI_Crystal.MI_Crystal')
        self.assertEqual(module(plain, 'TypeDataMesh').get('Mesh'), '/Game/SM_Pillar.SM_Pillar')
        self.assertEqual(module(plain, 'ColorOverLife').dist('ColorOverLife', 3).samples[0][1], [0.7, 0.1, 1.0])

    def test_dissolve_follows_the_threshold(self):
        n = E8.CURVE_POINTS
        dynamic = [3.0] * (n - 4) + [1.0, 0.5, 0.0, -0.3]
        alpha = lambda over, d: [lo[0] for _, lo, _ in module(E8.measured_cascade(
            emitter(), mesh_renderer(), measured(d), over=over), 'ColorOverLife').dist('AlphaOverLife', 1).samples]
        self.assertEqual(alpha({'dissolve': True}, dynamic), [1.0] * (n - 3) + [0.5, 0.0, 0.0])
        self.assertEqual(alpha({}, dynamic), [1.0] * n)                            # (only when the definition says)
        self.assertEqual(alpha({'dissolve': True}, None), [1.0] * n)               # (no dynamic parameter: whole)

    def test_shaded_mesh_is_lit_from_above(self):
        sm = types.SimpleNamespace(normals=np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]], np.float32),
                                   positions=np.zeros((3, 3), np.float32), colors=None)
        shaded = E8.ShadedMesh(sm)
        grey = shaded.colors[:, 0].astype(int)
        self.assertGreater(grey[0], grey[2])
        self.assertEqual(grey[1], int(round(E8.SOLID_AMBIENT * 255)))              # (facing away: the ambient only)
        self.assertTrue((shaded.colors[:, 3] == 255).all())
        self.assertIs(shaded.positions, sm.positions)                              # (its shape is the mesh's)

    def test_the_converter_reads_a_solid_mesh_as_its_mesh_lit(self):
        conv = E8.Converter.__new__(E8.Converter)
        sm = types.SimpleNamespace(normals=np.array([[0.0, 0.0, 1.0]], np.float32), positions=np.zeros((1, 3)))
        conv._meshes = {'/Game/SM.SM': sm}
        solid = conv._static_mesh(E8.SOLID_MESH + '/Game/SM.SM')
        self.assertIsInstance(solid, E8.ShadedMesh)
        self.assertIs(solid.sm, sm)
        self.assertIs(conv._static_mesh('/Game/SM.SM'), sm)                        # (the plain one unchanged)

    def test_solid_material_and_texture(self):
        mats = E8.Materials.__new__(E8.Materials)
        mats._done, mats.measured = {}, True
        mats.m = types.SimpleNamespace(effective=lambda path: {'base': 'M_EF_CH_ITM_id4_x'})
        desc = mats.describe('/Game/MI_Crystal.MI_Crystal' + E8.Materials.SOLID)
        self.assertEqual(desc['textures'], {'BaseTexture': E8.SOLID_TEXTURE + '/Game/MI_Crystal.MI_Crystal'})
        self.assertEqual((desc['blend'], desc['alpha'], desc['base']), ('BLEND_Translucent', 1.0, 'M_EF_CH_ITM_id4_x'))
        tex = E8.Textures(None, 0x1000, hot=True)
        albedo = np.zeros((8, 8, 4), np.float32)
        albedo[..., 0], albedo[..., 2], albedo[..., 3] = 0.25, 0.5, 1.0
        tex._solid['/Game/MI_Crystal.MI_Crystal'] = albedo
        src = types.SimpleNamespace(key=(E8.SOLID_TEXTURE + '/Game/MI_Crystal.MI_Crystal',), img=None, side=128)
        name, gidx, w, h = tex.lit(src, (1.0, 1.0, 1.0), 1.0, False)
        self.assertEqual((gidx, w, h), (0x1000, 16, 16))                           # (baked once, at least 16 px)
        self.assertIs(tex.lit(src, (1.0, 1.0, 1.0), 1.0, False)[0], name)
        from ttt2char.ttt2 import nut
        texels = np.asarray(nut.decode(nut.read(tex.files[name])['textures'][0]))
        self.assertGreater(texels[..., 3].min(), 250)                              # opaque: not its brightness
        self.assertGreater(texels[..., 2].mean(), texels[..., 0].mean())           # its own colours (sRGB)
        self.assertTrue(np.array_equal(tex.linear_image(src.key[0]), albedo))


class Pitched(unittest.TestCase):
    @staticmethod
    def runtime(pitch):
        """The runtime's pitch (title/roster.cpp: ahead -> ahead cos + up sin, up -> up cos - ahead sin) in Cascade
        axes, v' = R v."""
        c, s = np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
        return np.array([[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]])

    def test_counter_pitch_undoes_the_runtimes(self):
        for pitch in (90.0, 30.0, -45.0):
            self.assertTrue(np.allclose(self.runtime(pitch) @ E8.counter_pitch(pitch), np.eye(3)))
        # 2 m ahead on the floor, as converted, is 2 m ahead after the runtime's 90 degrees (not 2 m up)
        place = E8.counter_pitch(90.0) @ np.array([200.0, 0.0, 0.0])
        self.assertTrue(np.allclose(self.runtime(90.0) @ place, [200.0, 0.0, 0.0]))
        self.assertTrue(np.allclose(place, [0.0, 0.0, -200.0]))

    def test_rotator_round_trip(self):
        for roll, pitch, yaw in ((0.0, 0.0, 0.0), (10.0, 20.0, 30.0), (-40.0, 75.0, 170.0), (0.0, -90.0, 25.0)):
            m = P.frotation(pitch, yaw, roll)
            self.assertTrue(np.allclose(P.frotation(*(lambda r: (r[1], r[2], r[0]))(E8.rotator_of(m))), m, atol=1e-9))

    def test_turned_emitter(self):
        m = measured()
        m.path = [(10.0 * k, 0.0, -5.0 * k) for k in range(len(m.times))]
        m.turn_half = (0.0, 0.0, 0.5)                                   # a random yaw (about up)
        m.spin = (0.0, 0.0, -0.5)
        em = E8.measured_cascade(emitter(), mesh_renderer(), m, offset=(200.0, 0.0, 0.0), drift=(30.0, 0.0, 0.0))
        E8.turned(em, E8.counter_pitch(90.0))
        back = self.runtime(90.0)
        path = module(em, 'LocationDirect').dist('Location', 3).samples
        for (t, lo, hi), want in zip(path, m.path):
            self.assertTrue(np.allclose(back @ np.asarray(lo), np.asarray(want) + [200.0, 0.0, 0.0]))
        vel = module(em, 'Velocity').dist('StartVelocity', 3).samples[0]
        self.assertTrue(np.allclose(back @ np.asarray(vel[1]), [30.0, 0.0, 0.0]))
        pre = module(em, 'TypeDataMesh').dist('RollPitchYawRange', 3).samples[0][1]
        self.assertTrue(np.allclose(P.frotation(pre[1], pre[2], pre[0]), E8.counter_pitch(90.0).T))   # (v @ T^T)
        turn = module(em, 'MeshRotation').dist('StartRotation', 3).samples[0]
        self.assertTrue(np.allclose(turn[1], [-0.5, 0.0, 0.0]) and np.allclose(turn[2], [0.5, 0.0, 0.0]))
        spin = module(em, 'MeshRotationRate').dist('StartRotationRate', 3).samples[0][1]
        self.assertTrue(np.allclose(spin, [-0.5, 0.0, 0.0]))            # (about the axis now along its up)

    def test_only_a_named_system_is_turned(self):
        conv = E8.Converter.__new__(E8.Converter)
        conv.turn = None
        conv.tune = {'pitched': {30: 90.0}}
        seen = []
        conv._system8 = lambda *a: seen.append(None if conv.turn is None else conv.turn.copy()) or {}
        conv.system8(types.SimpleNamespace(emitters=[]), source=30)
        conv.system8(types.SimpleNamespace(emitters=[]), source=21)
        self.assertTrue(np.allclose(seen[0], E8.counter_pitch(90.0)))
        self.assertIsNone(seen[1])
        self.assertIsNone(conv.turn)                                    # (only while that system is converted)


class Place(unittest.TestCase):
    def test_a_looks_place_reaches_the_measured_emitters(self):
        conv = E8.Converter.__new__(E8.Converter)
        conv.tune, conv.measured, conv.stats = {'measured': True, 'offset': {30: (0.0, 0.0, 5.0)}}, True, {}
        conv._docs = lambda: ({'emitters': []}, {'emitters': []})
        conv._write = lambda docs: {}
        conv._static_mesh = lambda path: types.SimpleNamespace(positions=np.zeros((100, 3)))
        seen = []
        conv._measured = lambda e, r, mesh, sm, mat, floor, once, colour, offset, cap, roles: seen.append(offset) or []
        r = types.SimpleNamespace(kind='mesh', enabled=True, meshes=[('/Game/SM.SM', '/Game/MI.MI')], material=None)
        e = types.SimpleNamespace(name='CrystalPillar', enabled=True, gpu=False, renderers=[r], colours={})
        system = types.SimpleNamespace(emitters=[e])
        old = E8.measured_palette
        E8.measured_palette = lambda s: None
        try:
            conv.system8(system, floor=True, once=True, source=30, at=(200.0, 0.0, 0.0))
            conv.system8(system, floor=True, once=True, source=30)
            conv.tune = {'measured': True}
            conv.system8(system, floor=True, once=True, source=30, at=(250.0, 10.0, 0.0))
            conv.system8(system, floor=True, once=True, source=30)
        finally:
            E8.measured_palette = old
        self.assertEqual(seen, [(200.0, 0.0, 5.0), (0.0, 0.0, 5.0), (250.0, 10.0, 0.0), None])


if __name__ == '__main__':
    unittest.main()
