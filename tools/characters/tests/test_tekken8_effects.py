"""Unit tests of a Tekken 8 fighter's effects (tekken8/niagara.py, tekken8/staticmesh.py, convert/effects8.py, the
moveset converter's effect rows) on made-up data (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_effects.py
"""
import collections
import os
import struct
import sys
import types
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import effects8, moveset, particles as P     # noqa: E402
from ttt2char.tekken8 import niagara, staticmesh as SM              # noqa: E402

BASE = 64                       # made-up scripts' first literal offset (engine values and parameters before it)


# ------------------------------------------------------------------------------------------------ made-up VM code
def op(name):
    return bytes([niagara.OPS.index(name)])


def u16(*v):
    return struct.pack('<%dH' % len(v), *v)


def lit(k):
    """The constant offset of literal word k."""
    return BASE + 4 * k


class Code:
    """Builds VM bytecode and its literals: scopes by name, math ops with one constant each."""

    def __init__(self):
        self.code, self.words, self.scopes = b'', [], []

    def word(self, v):
        self.words.append(struct.pack('<I', v) if isinstance(v, int) else struct.pack('<f', v))
        return lit(len(self.words) - 1)

    def enter(self, name):
        if name not in self.scopes:
            self.scopes.append(name)
        self.code += op('enter_stat_scope') + u16(self.word(self.scopes.index(name)))
        return self

    def exit(self):
        self.code += op('exit_stat_scope')
        return self

    def math(self, name, value):
        """r1 = name(r0, constant value) (select: r1 = select(r0, constant, r2); a unary op: name(constant))."""
        c = self.word(value)
        if name == 'select':
            self.code += op(name) + bytes([0b010]) + u16(0, c, 2, 1)
        elif name in niagara.UNARY:
            self.code += op(name) + bytes([0b1]) + u16(c, 1)
        else:
            self.code += op(name) + bytes([0b10]) + u16(0, c, 1)
        return self

    def module(self, name, *ops):
        self.enter(name)
        for o, v in ops:
            self.math(o, v)
        return self.exit()

    def props(self):
        return {'CachedScriptVM': {'ByteCode': {'Data': self.code + op('done')},
                                   'ScriptLiterals': b''.join(self.words),
                                   'StatScopes': [{'FriendlyName': n} for n in self.scopes]}}


def system_update():
    """A made-up system update script: emitter Aura a burst of 50 at 0.25 s, a rate of 25/s and a loop of 0.5 s
    (its EmitterState also selects an enum: an int word), emitter Spark spawned by distance."""
    c = Code().enter('Main')
    c.module('SpawnBurst_Instantaneous_Aura', ('sub', 0.25), ('mul', 50.0))
    c.module('SpawnRate_Aura', ('mul', 25.0))
    c.module('EmitterState_Aura', ('select', 1), ('select', 0.5))
    c.module('SpawnPerUnit_Spark', ('mul', 3.0))
    return c.exit()


class VM(unittest.TestCase):
    def test_scopes_and_literals(self):
        s = niagara.Script(system_update().props())
        self.assertEqual(s.base, BASE)
        self.assertEqual(s.floats(s.module('SpawnRate_Aura')), [('mul', 25.0)])
        self.assertEqual([o for o, _ in s.floats(s.module('SpawnBurst_Instantaneous_Aura'))], ['sub', 'mul'])
        self.assertEqual({sc[-1] for sc, _ in s.scoped() if sc} - {'Main'},
                         {'SpawnBurst_Instantaneous_Aura', 'SpawnRate_Aura', 'EmitterState_Aura', 'SpawnPerUnit_Spark'})
        self.assertIsNone(s.word(BASE - 4))            # an engine value: not a literal
        self.assertIsNone(s.word(BASE + 2))            # (not on a word)

    def test_spawn_modules(self):
        s = niagara.Script(system_update().props())
        aura, spark = niagara.Emitter('Aura'), niagara.Emitter('Spark')
        niagara._spawn_modules(s, aura)
        niagara._spawn_modules(s, spark)
        self.assertEqual(aura.bursts, [(0.25, 50)])
        self.assertAlmostEqual(aura.rate, 25.0)
        self.assertAlmostEqual(aura.loop, 0.5)          # the enum's int word (a denormal float) is no length
        self.assertTrue(spark.per_unit)
        self.assertEqual((spark.bursts, spark.rate), ([], 0.0))

    def test_external_calls_and_data_ops(self):
        code = (op('external_func_call') + bytes([0]) + u16(0x8003, lit(0), 7) + op('inputdata_float') + u16(0, 4, 9)
                + op('outputdata_float') + bytes([1]) + u16(0, 2, lit(0), 5) + op('done'))
        ins = niagara.disassemble(code, externals=[(2, 1)])
        self.assertEqual([i.op for i in ins], ['external_func_call', 'inputdata_float', 'outputdata_float', 'done'])
        self.assertEqual(ins[0].constant_inputs(), [lit(0)])        # bit 15: a register
        self.assertEqual(ins[0].outputs, [7])
        self.assertEqual(ins[1].outputs, [9])
        self.assertEqual(ins[2].constant_inputs(), [lit(0)])

    def test_bad_code(self):
        with self.assertRaises(ValueError):
            niagara.disassemble(bytes([250]))
        with self.assertRaises(ValueError):
            niagara.disassemble(op('mul') + bytes([0]) + u16(1))     # ends inside the instruction
        with self.assertRaises(ValueError):
            niagara.disassemble(op('external_func_call') + bytes([3]), externals=[(1, 1)])


# ------------------------------------------------------------------------------------------------ made-up packages
class Export:
    def __init__(self, path, cls, props=None):
        self.path, self.class_name, self.name, self.props = path, cls, path.rsplit('.', 1)[-1].split(':')[-1], props


class Package:
    def __init__(self, exports):
        self.exports = exports

    def main_export(self):
        return self.exports[0]


class Store:
    def __init__(self, packages):
        self.packages = packages

    def package(self, path):
        if path not in self.packages:
            raise KeyError(path)
        return self.packages[path]


def read_props(pkg, ex, *args, **kw):
    return dict(ex.props or {}), 0


SYS = '/Game/Effect/NS_Made'


def made_system():
    """A made-up system: a GPU sprite emitter Aura (curves, colours) and a CPU mesh emitter Spark, following bone B."""
    p = lambda name: '%s.NS_Made:%s' % (SYS, name)
    update = system_update().props()
    update['CachedDefaultDataInterfaces'] = [{'Name': 'Sample.Mesh', 'DataInterface': p('SkelDI')}]
    spawn = Code().enter('Main').enter('InitializeParticle_Emitter').math('random', 0.2).math('add', 0.4) \
        .math('random', 1.5).math('add', 1.5).exit().enter('ScaleColor002_Emitter').math('mul', 40.0).exit().exit()
    spawn_props = spawn.props()
    spawn_props['CachedDefaultDataInterfaces'] = [
        {'Name': 'Emitter.ScaleSpriteSize001.Uniform Curve Sprite Scale', 'DataInterface': p('Curve')},
        {'Name': 'Emitter.Pick.Color Selection Array', 'DataInterface': p('Colours')}]
    spawn_props['CachedScriptVM']['Attributes'] = [{'Name': 'Particles.Lifetime.Value'}]
    exports = [
        Export(p('NS_Made'), 'NiagaraSystem', {
            'SystemUpdateScript': p('Update'), 'bFixedBounds': True,
            'FixedBounds': {'Min': {'X': -1, 'Y': -2, 'Z': 0}, 'Max': {'X': 1, 'Y': 2, 'Z': 3}},
            'EmitterHandles': [{'VersionedInstance': {'Emitter': p('Aura')}},
                               {'VersionedInstance': {'Emitter': p('Spark')}, 'bIsEnabled': False}]}),
        Export(p('Update'), 'NiagaraScript', update),
        Export(p('SkelDI'), 'NiagaraDataInterfaceSkeletalMesh', {'FilteredBones': ['B']}),
        Export(p('Aura'), 'NiagaraEmitter', {'UniqueEmitterName': 'Aura', 'VersionData': [{
            'SimTarget': 1, 'RendererProperties': [p('Sprite')], 'SpawnScriptProps': {'Script': p('Spawn')}}]}),
        Export(p('Sprite'), 'NiagaraSpriteRendererProperties', {'Material': '/Game/M.M', 'SubImageSize': {'X': 2.0,
                                                                                                         'Y': 2.0}}),
        Export(p('Spawn'), 'NiagaraScript', spawn_props),
        Export(p('Curve'), 'NiagaraDataInterfaceCurve', {'ShaderLUT': [0.0, 0.5, 1.0], 'LUTNumSamplesMinusOne': 2.0}),
        Export(p('Colours'), 'NiagaraDataInterfaceArrayColor', {'ColorData': [{'R': 0.0, 'G': 0.5, 'B': 1.0}]}),
        Export(p('Spark'), 'NiagaraEmitter', {'UniqueEmitterName': 'Spark', 'VersionData': [{
            'SimTarget': 0, 'bLocalSpace': True, 'SpawnScriptProps': {'Script': p('Spawn')},
            'RendererProperties': [p('Mesh')]}]}),
        Export(p('Mesh'), 'NiagaraMeshRendererProperties', {'Meshes': [{'Mesh': '/Game/SM.SM'}],
                                                             'bOverrideMaterials': True,
                                                             'OverrideMaterials': [{'ExplicitMat': '/Game/M2.M2'}]}),
    ]
    table = Export('/Game/DA.DA', 'DataAsset', {'CharacterEffect': {
        '40': {'ParticleAsset': p('NS_Made'), 'isAttachedCharacter': True}, '41': {'ParticleAsset': None}}})
    return Store({SYS: Package(exports),
                  '/Game/Effect/PolarisXYZwork/Character/xyz/DA_CharacterEffect_XYZ': Package([table])})


class Reader(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(niagara.uprops, 'read', side_effect=read_props)
        patch.start()
        self.addCleanup(patch.stop)

    def test_system(self):
        s = niagara.read(made_system(), SYS + '.NS_Made')
        self.assertEqual((s.name, s.bones, s.bounds), ('NS_Made', ['B'], ([-1, -2, 0], [1, 2, 3])))
        aura, spark = s.emitters
        self.assertEqual((aura.name, aura.gpu, aura.enabled, spark.gpu, spark.local, spark.enabled),
                         ('Aura', True, True, False, True, False))
        self.assertEqual((aura.bursts, aura.rate, aura.loop), ([(0.25, 50)], 25.0, 0.5))
        r = aura.renderers[0]
        self.assertEqual((r.kind, r.material, r.sub_images), ('sprite', '/Game/M.M', (2, 2)))
        m = spark.renderers[0]
        self.assertEqual((m.kind, m.meshes), ('mesh', [('/Game/SM.SM', '/Game/M2.M2')]))
        ch, samples, span = aura.curves['ScaleSpriteSize001.Uniform Curve Sprite Scale']
        self.assertEqual((ch, samples, span), (1, [[0.0], [0.5], [1.0]], (0.0, 1.0)))
        self.assertEqual(aura.colours['Pick.Color Selection Array'], [(0.0, 0.5, 1.0, 1.0)])
        self.assertEqual(aura.literals, {})                          # a GPU emitter's constants are its shader's
        self.assertEqual([o for o, _ in spark.literals['InitializeParticle']], ['random', 'add', 'random', 'add'])
        self.assertIn('Lifetime', spark.modules)

    def test_effect_table(self):
        t = niagara.effect_table(made_system(), 'xyz')
        self.assertEqual(list(t), [40])                              # an entry without a system: none
        self.assertTrue(t[40]['attached'])
        self.assertEqual(niagara.effect_table(Store({}), 'xyz'), {})


# ------------------------------------------------------------------------------------------------ converter pieces
def emitter(name='Aura', gpu=True, **kw):
    e = niagara.Emitter(name)
    e.gpu = gpu
    for k, v in kw.items():
        setattr(e, k, v)
    return e


class Pieces(unittest.TestCase):
    def test_parts(self):
        d = types.SimpleNamespace(TEKKEN8_EFFECTS={40: 9, 41: {1: 9, 0: 13}, 43: ({1: 9}, 'floor'), 44: (5, 'floor')})
        self.assertEqual(effects8.parts(d), {40: (9, False), 41: ({1: 9, 0: 13}, False), 43: ({1: 9}, True),
                                             44: (5, True)})
        self.assertEqual(effects8.parts(types.SimpleNamespace()), {})

    def test_over_life(self):
        d = effects8.over_life((1, [[0.0], [1.0]], (0.5, 1.0)), dim=3, points=5)
        self.assertEqual([round(lo[0], 3) for _, lo, _ in d.samples], [0.0, 0.0, 0.0, 0.5, 1.0])
        self.assertEqual(d.samples[-1][1], [1.0, 1.0, 1.0])            # one channel fills every dimension

    def test_curves_picked(self):
        fade = (1, [[1.0], [0.6], [0.1]], (0.0, 1.0))
        grow = (1, [[0.5], [2.0], [5.0]], (0.0, 1.0))
        e = emitter(curves={'FloatFromCurve.FloatCurve': fade, 'FloatFromCurve002.FloatCurve': grow,
                            'Index 0 Param 1.FloatCurve': (1, [[0.0], [9.0]], (0.0, 1.0))})
        self.assertIs(effects8.alpha_curve(e), fade)
        self.assertIs(effects8.size_curve(e), grow)
        opens = (1, [[0.0], [0.5], [1.0]], (0.0, 1.0))
        ring = emitter(curves={'FloatFromCurve007.FloatCurve': opens})
        self.assertIsNone(effects8.size_curve(ring))
        self.assertIs(effects8.size_curve(ring, mesh=True), opens)     # a mesh opening out from nothing

    def test_colours(self):
        a = emitter(colours={'x': [(0.0, 0.05, 0.08, 1.0), (0.0, 0.5, 1.0, 1.0)]})
        self.assertEqual(effects8.brightest(a.colours), (0.0, 0.5, 1.0))
        system = types.SimpleNamespace(emitters=[a, emitter('Spark')])
        self.assertEqual(effects8.palette(system), (0.5, 0.75, 1.0))   # half way to white at its peak
        self.assertEqual(effects8.palette(types.SimpleNamespace(emitters=[])), effects8.DEFAULT_COLOUR)

    def test_lit_keeps_the_hue(self):
        white = np.ones((1, 1, 4), np.float32)
        out = effects8.lit_texels(white, (0.0, 1.02, 2.0), 1.0, False)[0, 0]
        per_channel = P.lit_texels(white, (0.0, 1.02, 2.0), 1.0, False)[0, 0]
        self.assertAlmostEqual(out[2], per_channel[2], places=5)               # the brightest channel: the same
        self.assertLess(out[1], per_channel[1] - 0.05)                          # azure, not cyan
        lin = out[:3] ** P.GAMMA
        self.assertAlmostEqual(lin[1] / lin[2], 0.51, places=2)
        grey = effects8.lit_texels(white, (0.5, 0.5, 0.5), 1.0, True)[0, 0]
        np.testing.assert_allclose(grey, P.lit_texels(white, (0.5, 0.5, 0.5), 1.0, True)[0, 0], atol=1e-6)

    def test_cpu_values(self):
        e = emitter('Burst', gpu=False, literals={
            'InitializeParticle': [('random', 0.2), ('add', 0.4), ('random', 1.5), ('add', 1.5)],
            'ScaleMeshSize002': [('mul', 2.0)], 'ScaleColor002': [('mul', 40.0)]})
        v = effects8.cpu_values(e)
        self.assertAlmostEqual(v['life'][0], 0.5)
        self.assertAlmostEqual(v['life'][1], 0.1)
        self.assertEqual(v['scale'], (4.5, 1.5))                       # (1.5 + 0.75, 0.75) x 2
        self.assertEqual(v['brightness'], effects8.MAX_BRIGHTNESS)

    def test_emitting_frames(self):
        once = emitter(bursts=[(0.0, 50)])
        late = emitter(bursts=[(0.0, 5), (0.5, 5)])
        rate = emitter(rate=25.0)
        off = emitter(rate=25.0, enabled=False)
        sys_ = lambda *e: types.SimpleNamespace(emitters=list(e))
        self.assertEqual(effects8.emitting_frames({1: sys_(once), 2: sys_(once, late), 3: sys_(rate), 4: sys_(off)}),
                         {1: None, 2: 30, 3: int(P.LOOP_CAP * P.FPS), 4: None})

    def test_once_unless_stopped(self):
        ring = emitter('Circle', rate=50.0, loop=0.2)
        aura = emitter('Aura', rate=25.0)                                       # (no loop length read)
        sys_ = lambda *e: types.SimpleNamespace(emitters=list(e))
        cap = int(P.LOOP_CAP * P.FPS)
        self.assertEqual(effects8.emitting_frames({30: sys_(ring), 16: sys_(aura)}, stopped={42}),
                         {30: 12, 16: cap})                                      # one loop; no length: endless
        self.assertEqual(effects8.emitting_frames({30: sys_(ring)}, stopped={30}), {30: cap})
        self.assertEqual(effects8.emitting_frames({30: sys_(ring)}), {30: cap})        # (no stops known: all loop)
        r = niagara.Renderer('NiagaraSpriteRendererProperties', {'Material': '/Game/M.M'})
        once = effects8.cascade(ring, r, (1.0, 1.0, 1.0), once=True).module('Required')
        self.assertEqual((once.get('EmitterLoops'), once.get('EmitterDuration')), (1, 0.2))
        self.assertEqual(effects8.cascade(ring, r, (1.0, 1.0, 1.0)).module('Required').get('EmitterLoops'), 0)

    def test_cascade_sprite(self):
        e = emitter('Spark', bursts=[(0.0, 150), (0.25, 50)], loop=0.5,
                    curves={'Scale Alpha.FloatCurve': (1, [[1.0], [0.0]], (0.0, 1.0))})
        r = niagara.Renderer('NiagaraSpriteRendererProperties', {'Material': '/Game/M.M'})
        em = effects8.cascade(e, r, (0.2, 0.4, 0.8), floor=True)
        req, spawn = em.module('Required'), em.module('Spawn')
        self.assertEqual((req.get('Material'), req.get('EmitterLoops'), req.get('EmitterDuration')),
                         ('/Game/M.M', 1, 0.5))
        self.assertEqual([(b['Count'], b['Time']) for b in spawn.get('BurstList')], [(150, 0.0), (50, 0.5)])
        self.assertEqual(spawn.dist('Rate').mean(), [0.0])
        self.assertEqual(em.module('Lifetime').dist('Lifetime').mean(), [effects8.role('Spark')['life'][0]])
        c = em.module('Color').dist('StartColor', 3).mean()
        self.assertEqual(c, [x * effects8.GPU_BRIGHTNESS for x in (0.2, 0.4, 0.8)])   # (no colour array: given)
        self.assertIsNotNone(em.module('ColorOverLife'))
        self.assertIsNotNone(em.module('FloorHeight'))
        self.assertIsNone(em.module('TypeDataMesh'))

    def test_cascade_mesh_rate(self):
        e = emitter('Tornade_Glow001', rate=10.0)
        r = niagara.Renderer('NiagaraMeshRendererProperties', {'Meshes': [{'Mesh': '/Game/SM.SM'}]})
        em = effects8.cascade(e, r, (1.0, 1.0, 1.0))
        self.assertEqual(em.module('Required').get('EmitterLoops'), 0)              # emits until stopped
        self.assertEqual(em.module('Spawn').dist('Rate').mean(), [10.0])
        self.assertEqual(em.module('TypeDataMesh').get('Mesh'), '/Game/SM.SM')
        self.assertEqual(em.module('MeshRotationRate').dist('StartRotationRate', 3).mean(), [0.0, 0.0, 1.5])


# ------------------------------------------------------------------------------------------------ moveset rows
def converter(effects):
    class K:
        tables = {'moves': [{'anim_len': 60}]}
    c = moveset.Converter.__new__(moveset.Converter)
    c.game, c.k, c.effects8 = 't8', K(), effects
    c.effect_rows, c.effect_ids, c.effects8_stopped, c.stats = [], set(), set(), collections.Counter()
    return c


SHOW, HIDE = 0x8317, 0x8318                     # summons8.SUMMON, DISMISS (the rows its prepare made)
STAFF = {1: 9, 0: 13}


class Rows(unittest.TestCase):
    def test_summon_part_and_its_end(self):
        c = converter({42: STAFF, 41: STAFF})
        t8 = [(14, SHOW, 1, None), (14, moveset.EFFECT8_SPAWN, 42, None), (40, HIDE, 1, None),
              (40, moveset.EFFECT8_SPAWN, 41, None)]
        rows = []
        for f, idv, v, _ in t8:
            if idv == moveset.EFFECT8_SPAWN:
                c.effect8_rows(rows, t8, f, idv, v, 0)
        self.assertEqual([(r['frame'], r['id'], r['value']) for r in rows],
                         [(14, moveset.EFFECT_PROP, 9 << 8 | 42), (40, moveset.EFFECT_PROP, 9 << 8 | 41)])
        self.assertEqual([left for _, _, left in c.effect_rows], [26, 20])     # to the hide; the move's 20 left
        self.assertEqual(c.effect_ids, {41, 42})
        out = c.split_effects({42: 120, 41: None}, used=set())
        self.assertEqual(out[42], (42, 30))                                   # 26 -> rounded up to 30

    def test_left_staff_and_part_bits(self):
        c = converter({40: STAFF, 32: 5})
        t8 = [(1, SHOW, 0, None), (48, HIDE, 0, None)]
        rows = []
        c.effect8_rows(rows, t8, 1, moveset.EFFECT8_SPAWN, 40, 0)
        c.effect8_rows(rows, t8, 0x8001, moveset.EFFECT8_SPAWN, 27 << 8 | 32, 0)     # Tekken 8's own part: ours
        self.assertEqual([r['value'] for r in rows], [13 << 8 | 40, 5 << 8 | 32])
        self.assertEqual([left for _, _, left in c.effect_rows], [47, 60])

    def test_stop_row_and_no_summon(self):
        c = converter({42: STAFF})
        t8 = [(5, moveset.EFFECT8_SPAWN, 42, None), (20, moveset.EFFECT8_STOPS[0], 42, None)]
        rows = []
        c.effect8_rows(rows, t8, 5, moveset.EFFECT8_SPAWN, 42, 0)
        c.effect8_rows(rows, t8, 20, moveset.EFFECT8_STOPS[0], 42, 0)               # a stop: no row of its own
        self.assertEqual([r['value'] for r in rows], [9 << 8 | 42])             # no summon in the list: the first
        self.assertEqual(c.effect_rows[0][2], 15)
        self.assertEqual(c.effects8_stopped, {42})                              # it loops until stopped

    def test_the_other_stop_is_no_spawn(self):
        c = converter({42: STAFF})
        t8 = [(5, moveset.EFFECT8_SPAWN, 42, None), (30, 0x8036, 42, None)]
        rows = []
        c.effect8_rows(rows, t8, 5, moveset.EFFECT8_SPAWN, 42, 0)
        c.effect8_rows(rows, t8, 30, 0x8036, 42, 0)
        self.assertEqual([r['value'] for r in rows], [9 << 8 | 42])
        self.assertEqual(c.effect_rows[0][2], 25)


# ------------------------------------------------------------------------------------------------ static meshes
def mesh_bytes():
    """A made-up cooked static mesh: junk, then one triangle's buffers (positions, tangents, half UVs, no colours,
    16-bit indices)."""
    b = b'\0' * 8
    pos = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 0.0, 5.0)]
    b += struct.pack('<4I', 12, 3, 12, 3) + b''.join(struct.pack('<3f', *p) for p in pos)
    b += b'\0\0' + struct.pack('<4I', 1, 3, 0, 0)
    b += struct.pack('<2I', 8, 3) + bytes([127, 0, 0, 0, 0, 0, 127, 127]) * 3       # tangent X, normal Z
    b += struct.pack('<2I', 4, 3) + np.array([0, 0, 1, 0, 0, 1], '<f2').tobytes()
    b += b'\0\0' + struct.pack('<2I', 0, 0)
    b += struct.pack('<3I', 0, 2, 3) + struct.pack('<3H', 0, 1, 2)
    return b


class StaticMesh(unittest.TestCase):
    def test_read(self):
        data = mesh_bytes()
        ex = types.SimpleNamespace(class_name='StaticMesh', name='SM_Made', offset=0, size=len(data))
        pkg = types.SimpleNamespace(exports=[ex], data=data)
        with mock.patch.object(SM.uprops, 'read', return_value=({'StaticMaterials': [{'MaterialInterface': 'M'}]},
                                                                0)):
            sm = SM.StaticMesh(types.SimpleNamespace(package=lambda path: pkg), '/Game/SM_Made.SM_Made')
        self.assertEqual(sm.materials, ['M'])
        self.assertEqual(sm.positions.tolist(), [[0, 0, 0], [10, 0, 0], [0, 0, 5]])
        self.assertEqual(sm.uvs[:, 0].tolist(), [[0, 0], [1, 0], [0, 1]])
        self.assertEqual(sm.normals[0].tolist(), [0.0, 0.0, 1.0])
        self.assertIsNone(sm.colors)
        self.assertEqual(sm.triangles()[0][1].tolist(), [[0, 1, 2]])

    def test_no_positions(self):
        ex = types.SimpleNamespace(class_name='StaticMesh', name='SM_Empty', offset=0, size=64)
        pkg = types.SimpleNamespace(exports=[ex], data=b'\0' * 64)
        with mock.patch.object(SM.uprops, 'read', return_value=({}, 0)), self.assertRaises(ValueError):
            SM.StaticMesh(types.SimpleNamespace(package=lambda path: pkg), '/Game/SM_Empty')


if __name__ == '__main__':
    unittest.main()
