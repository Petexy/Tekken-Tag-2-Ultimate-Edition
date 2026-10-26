"""Tekken 8 skeletal meshes and their way into TTT2 (tekken8/mesh.py, names.py, model.py, convert/skeleton.repose) on
made-up data: a SkeletalMesh package with two sections (one a cloth simulation proxy), 8-bit and 16-bit skin
weights, vertex colours; joint names to Tekken 7 roles and TTT2 bones; an A-pose arm turned into a donor's T-pose.

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from ttt2char.convert import skeleton                  # noqa: E402
from ttt2char.tekken8 import cityhash, mesh, model, names, reflect, zen   # noqa: E402

SKMESH = '/Script/Engine.SkeletalMesh'
MATERIAL = '/Script/Engine.MaterialInstanceConstant'
CLASSES = {cityhash.script_object_id(SKMESH): SKMESH, cityhash.script_object_id(MATERIAL): MATERIAL}
SCHEMA = {'classes': {SKMESH: {'name': 'SkeletalMesh', 'super': None, 'flags': 0, 'props': [
    {'n': 'bHasVertexColors', 't': 'Bool'}]}}, 'structs': {}, 'enums': {}}
PACKAGE = '/Game/T/SK_Test'
# the package's names: the package and its exports first (as synth.zen_package lays them out), then the rest
NAMES = [PACKAGE, 'SK_Test', 'MI_Body', 'M_CH_sim_mesh_material', 'None', 'body', 'sim', 'Root', 'Hip',
         'L_UpperArm', 'ADR_L_DeltioidUp_bnd', 'ADR_L_UpperArm_twt_b']
# the skeleton: (name, parent, translation cm); identity rotations
BONES = [('Root', -1, (0, 0, 0)), ('Hip', 0, (0, 0, 97)), ('L_UpperArm', 1, (15, 0, 46)),
         ('ADR_L_DeltioidUp_bnd', 1, (15, 0, 46)), ('ADR_L_UpperArm_twt_b', 3, (10, 0, -10))]
POS = np.array([[0, 0, 100], [10, 0, 100], [0, 0, 110], [20, 0, 140], [30, 0, 140], [20, 1, 130]], np.float32)


class Scripts:
    def script_path(self, v):
        return CLASSES.get(v)


class Store:
    """What SkeletalMesh asks of a store: package(), schema."""

    def __init__(self):
        self.schema = reflect.Schema(SCHEMA)
        self.pkg = None

    def package(self, path):
        return self.pkg


def _name(n):
    return struct.pack('<II', NAMES.index(n), 0)


def _bulk(dtype, a):
    dt = np.dtype(dtype)
    b = (a if isinstance(a, np.ndarray) and a.dtype.fields else np.ascontiguousarray(a, dt.base)).tobytes()
    return struct.pack('<ii', dt.itemsize, len(b) // dt.itemsize) + b


def _tarray(fmt, values):
    return struct.pack('<i', len(values)) + b''.join(struct.pack('<' + fmt, v) for v in values)


def _section(material, first_index, triangles, first_vertex, vertices, bone_map, disabled=False):
    d = b'\0\0' + struct.pack('<HII', material, first_index, triangles)
    d += struct.pack('<IBII', 0, 0, 1, 1) + struct.pack('<I', first_vertex)
    d += struct.pack('<i', 0)                                              # no cloth mapping
    d += _tarray('H', bone_map) + struct.pack('<Ii', vertices, 8) + struct.pack('<h', -1) + bytes(16)
    d += struct.pack('<i', 0) + _tarray('I', []) + _tarray('Q', []) + struct.pack('<I', int(disabled))
    return d


def mesh_package(store, wide=False, colours=False, parents=None, cut=0):
    """A SkeletalMesh package: section 0 (MI_Body: vertices 0-2, skinned to Hip and the upper arm's twist joint
    through its bone map [1, 4]), section 1 (the simulation proxy: vertices 3-5 on L_UpperArm). wide: 16-bit bone
    indices, weights, triangle indices and tangents and float UVs; colours: a vertex colour buffer."""
    props = struct.pack('<H', 0x300) + b'\x01' if colours else struct.pack('<H', 0x100)
    d = bytearray(props + struct.pack('<I', 0))                            # GUID flag
    d += b'\0\0' + struct.pack('<7d', 0, 0, 90, 30, 30, 90, 100)
    d += struct.pack('<i', 2)
    for ref, slot in ((2, 'body'), (3, 'sim')):
        d += struct.pack('<i', ref) + _name(slot) + struct.pack('<I', 0) + struct.pack('<II4f', 1, 0, 1, 1, 1, 1)
    parents = parents or [b[1] for b in BONES]
    d += struct.pack('<i', len(BONES)) + b''.join(_name(b[0]) + struct.pack('<i', p) for b, p in zip(BONES, parents))
    d += struct.pack('<i', len(BONES)) + b''.join(struct.pack('<10d', 0, 0, 0, 1, *b[2], 1, 1, 1) for b in BONES)
    d += struct.pack('<i', len(BONES)) + b''.join(_name(b[0]) + struct.pack('<i', i) for i, b in enumerate(BONES))
    d += struct.pack('<I', 1) + struct.pack('<i', 1)                       # cooked, one LOD
    d += b'\0\0' + struct.pack('<II', 0, 1) + _tarray('H', [0, 1, 2])
    d += struct.pack('<i', 2) + _section(0, 0, 1, 0, 3, [1, 4]) + _section(1, 3, 1, 3, 3, [2])
    d += _tarray('H', [1, 2, 4]) + struct.pack('<I', 0)
    tris = [0, 1, 2, 3, 4, 5]
    d += b'\0\0' + struct.pack('<B', 4 if wide else 2) + _bulk('<u4' if wide else '<u2', tris)
    d += struct.pack('<II', 12, 6) + _bulk('<3f4', POS)
    scale = 32767 if wide else 127
    tx = np.tile([scale, 0, 0, 0], (6, 1))
    tz = np.tile([0, 0, scale, scale], (6, 1))
    tz[2, 3] = -scale                                                      # vertex 2: a mirrored bitangent
    t = np.zeros(6, [('x', '<4i2' if wide else '<4i1'), ('z', '<4i2' if wide else '<4i1')])
    t['x'], t['z'] = tx, tz
    uv = np.zeros((6, 2, 2), np.float32)
    uv[:, 0, 0] = np.arange(6) / 8.0
    uv[:, 1, 1] = 0.5
    d += b'\0\0' + struct.pack('<IIII', 2, 6, int(wide), int(wide)) + _bulk(t.dtype, t)
    d += _bulk('<2f4' if wide else '<2f2', uv.reshape(-1, 2))
    # skin weights: per vertex 8 bone indices (into its section's bone map), then 8 weights
    top = 65535 if wide else 255
    local = np.zeros((6, 8), np.int64)
    w = np.zeros((6, 8), np.int64)
    local[1, 1] = local[2, 0] = 1
    w[:, 0] = top
    w[1, 0], w[1, 1] = top // 2 + 1, top // 2                             # vertex 1: half Hip, half the twist
    raw = np.concatenate([local.astype('<u2' if wide else 'u1').view(np.uint8).reshape(6, -1),
                          w.astype('<u2' if wide else 'u1').view(np.uint8).reshape(6, -1)], 1)
    d += b'\0\0' + struct.pack('<IIIIII', 0, 8, 48, 6, int(wide), int(wide)) + _bulk('u1', raw.reshape(-1))
    d += b'\0\0' + struct.pack('<I', 0) + _bulk('<u4', [])
    if colours:
        d += b'\0\0' + struct.pack('<II', 4, 6) + _bulk('<u4', np.arange(6) * 0x01010101)
    d += struct.pack('<i', 0) + struct.pack('<i', 3) + b'xyz' + struct.pack('<I', 0)
    if cut:
        d = d[:-cut]
    cls = {c: synth.script_index(cityhash.script_object_id(c)) for c in (SKMESH, MATERIAL)}
    data = synth.zen_package(PACKAGE, [{'name': 'SK_Test', 'cls': cls[SKMESH], 'data': bytes(d)},
                                       {'name': 'MI_Body', 'cls': cls[MATERIAL], 'data': b'\0' * 8},
                                       {'name': 'M_CH_sim_mesh_material', 'cls': cls[MATERIAL], 'data': b'\0' * 8}])
    pkg = zen.Package(data, 'Polaris/Content/T/SK_Test.uasset', 5, Scripts(), store)
    pkg.names = NAMES
    store.pkg = pkg
    return pkg


# ------------------------------------------------------------------------------------------------ mesh
class Meshes(unittest.TestCase):
    def check(self, wide, colours):
        s = Store()
        mesh_package(s, wide=wide, colours=colours)
        m = mesh.SkeletalMesh(s, PACKAGE)
        self.assertEqual(m.skeleton['names'], [b[0] for b in BONES])
        self.assertEqual(m.skeleton['parents'], [-1, 0, 1, 1, 3])
        self.assertEqual(m.skeleton['pose'].shape, (5, 10))
        self.assertEqual(tuple(m.skeleton['pose'][2, 4:7]), (15, 0, 46))
        self.assertEqual([m.material_name(i) for i in range(3)], ['MI_Body', 'M_CH_sim_mesh_material', 'None'])
        self.assertEqual(m.materials[0]['material'], PACKAGE + '.MI_Body')
        secs = m.lods[0].sections
        self.assertEqual([(x.material_index, x.base_vertex, x.num_vertices) for x in secs], [(0, 0, 3), (1, 3, 3)])
        self.assertEqual([x.cloth_mapping for x in secs], [0, 1])            # the proxy: left out by loaders
        self.assertEqual(m.lods[0].colors is not None, colours)
        g = m.geometry(0)
        np.testing.assert_array_equal(g['positions'], POS)
        np.testing.assert_allclose(g['normals'], np.tile([0, 0, 1.0], (6, 1)))
        np.testing.assert_allclose(g['tangents'][:, :3], np.tile([1.0, 0, 0], (6, 1)))
        self.assertEqual(g['tangents'][:, 3].tolist(), [1, 1, -1, 1, 1, 1])
        self.assertEqual(g['uvs'].shape, (6, 2, 2))
        np.testing.assert_allclose(g['uvs'][:, 0, 0], np.arange(6) / 8.0)
        np.testing.assert_allclose(g['uvs'][:, 1, 1], 0.5)
        # bone map indices -> skeleton bones: section 0's [1, 4], section 1's [2]
        self.assertEqual(g['joints'][:, :2].tolist(), [[1, 1], [1, 4], [4, 1], [2, 2], [2, 2], [2, 2]])
        np.testing.assert_allclose(g['weights'].sum(1), 1.0, atol=1e-6)
        self.assertAlmostEqual(float(g['weights'][1, 0]), 0.5, 2)
        self.assertEqual([t.tolist() for t in g['triangles']], [[[0, 1, 2]], [[3, 4, 5]]])

    def test_narrow(self):
        self.check(False, False)

    def test_wide_with_colours(self):
        self.check(True, True)

    def test_errors(self):
        s = Store()
        mesh_package(s, parents=[-1, 0, 3, 1, 3])                          # a parent after its child
        with self.assertRaises(zen.ParseError):
            mesh.SkeletalMesh(s, PACKAGE)
        mesh_package(s, cut=6)                                             # cut short
        with self.assertRaises(zen.ParseError):
            mesh.SkeletalMesh(s, PACKAGE)


# ------------------------------------------------------------------------------------------------ names
def ttt2(joint, part='bdf'):
    return skeleton.t7_weight_target(names.canonical(joint), part)


class Names(unittest.TestCase):
    def test_main_joints(self):
        for t8, t7 in (('Trans', 'BASE'), ('Rot', 'Hip'), ('L_UpperArm', 'L_Arm'), ('R_LowerArm', 'R_ForeArm'),
                       ('L_UpperLeg', 'L_UpLeg'), ('R_LowerLeg', 'R_Leg'), ('L_Thumb0', 'L_Thumb1'),
                       ('L_Thumb2', 'L_Thumb3'), ('L_Index0', 'L_FingerBase'), ('R_Pinky0', 'R_Pinky'),
                       ('R_Middle2', 'R_Middle2'), ('Head', 'Head')):
            self.assertEqual(names.canonical(t8), t7, t8)
        # Tekken 8's Hip (the legs' pivot) and C_Leg give their weights to KOSHI but anchor nothing
        self.assertEqual(names.canonical('Hip'), 'Hip__offset@Hip')
        self.assertEqual(ttt2('Hip'), 'KOSHI_jnt')
        self.assertEqual(ttt2('C_Leg'), 'KOSHI_jnt')

    def test_helpers_go_to_their_limb(self):
        for joint, bone in (('ADR_L_UpperArm_twt_a', 'KATA_0_L_jnt'), ('ADR_L_UpperArm_twt_b', 'KATA_50_L'),
                            ('ADR_R_UpperArm_twt_c', 'KATA_100_R'), ('ADR_L_DeltioidUp_bnd', 'KATA_0_L_jnt'),
                            ('ADR_L_Forearm_twt_a', 'UDE_L_jnt'), ('ADR_R_Forearm_twt_c', 'UDE_100_R'),
                            ('ADR_L_Thigh_bnd', 'MOMO_0_L'), ('ADR_L_Thigh_twt_a', 'MOMO_0_L'),
                            ('ADR_R_Thigh_twt_b', 'MOMO_50_R'), ('ADR_R_Shin_twt_b', 'SUNE_R'),
                            ('ADR_L_Knee_hlf', 'HIZA_L'), ('ADR_L_Calf_mus', 'slide_fukura_l'),
                            ('ADR_R_Biceps_mus', 'slide_kata_r'), ('ADR_L_TrapsSide_bnd', 'SAKOTSU_L_jnt'),
                            ('ADR_L_Clavicle_mus', 'SAKOTSU_0_L_jnt'), ('ADR_R_PecMajor_mus', 'MUNE_R_jnt'),
                            ('ADR_L_Index2_hlf', 'HITO2_L'), ('ADR_R_Thumb0_mus', 'OYA3_R'),
                            ('ADR_L_Pinky3Inflat_mus', 'KO1_L'), ('ADR_NeckSpine_twt_b', 'KUBI_jnt_assist'),
                            ('SWG_L_Bust', 'OPT0_busts'), ('L_Have', 'TE_L_jnt')):
            self.assertEqual(ttt2(joint), bone, joint)

    def test_face(self):
        for joint, bone in (('L_Brow1', 'L_Mayu1_Joint'), ('R_Brow4', 'R_Mayu3_Joint'), ('L_SubBrow2', 'L_Mayu2_Joint'),
                            ('L_Eye', 'L_Eye_Joint'), ('R_UpEyelid3', 'R_UwaMabuta_Joint'),
                            ('ADS_L_LowEyelid2', 'L_SitaMabuta_Joint'), ('L_LipCorner', 'L_LipE_Joint'),
                            ('C_UpLip', 'M_LipU_Joint'), ('L_UpLip01Zipper', 'M_LipU_Joint'),
                            ('R_UpLip2', 'R_LipU_Joint'), ('C_LowLip', 'M_LipD_Joint'), ('L_LowLip2', 'L_LipD_Joint'),
                            ('C_LowJaw', 'Jaw_Joint'), ('C_LowTeeth', 'Jaw_Joint'), ('C_Tongue1', 'Bero1_Joint'),
                            ('C_Tongue3', 'Bero2_Joint'), ('L_Nose1', 'L_Hana_Joint'), ('R_Nose2', 'R_Kobana_Joint'),
                            ('L_Cheek7', 'L_Hoho_Joint'), ('R_Cheek2', 'R_Chobo_Joint'), ('C_Nose1', 'ATAMA_Joint'),
                            ('L_Forehead1', 'ATAMA_Joint'), ('C_Jaw_Root', 'ATAMA_Joint'), ('L_UpEar', 'ATAMA_Joint'),
                            ('C_UpTeeth', 'ATAMA_Joint')):
            self.assertEqual(ttt2(joint, 'fac'), bone, joint)
        self.assertEqual(ttt2('C_UpTeeth', 'har'), 'ATAMA_jnt_assist')    # the head of a hair or body part

    def test_names_are_unique_and_unknowns_stay(self):
        joints = ['Trans', 'Rot', 'MUKI', 'Hip', 'C_Leg', 'L_UpperArm', 'ADR_L_UpperArm_twt_a', 'ADR_L_DeltioidUp_bnd',
                  'ADR_L_Deltoid_drv', 'L_UpEyelid1', 'L_UpEyelid2', 'ADS_L_UpEyelid1', 'PHY_Hip_Skirt1']
        out = [names.canonical(j) for j in joints]
        self.assertEqual(len(set(out)), len(out))
        self.assertEqual(names.canonical('PHY_Hip_Skirt1'), 'PHY_Hip_Skirt1')   # unknown: its parent's bone
        self.assertIsNone(names.target('PHY_Hip_Skirt1'))
        self.assertIsNone(names.target('ADR_L_Something_new'))

    def test_follow(self):
        self.assertEqual(names.follow('ADR_L_DeltioidUp_bnd'), ('L_UpperArm', 1.0))
        self.assertEqual(names.follow('ADR_R_Thigh_bnd'), ('R_UpperLeg', 1.0))
        self.assertEqual(names.follow('ADR_R_Knee_hlf'), ('R_LowerLeg', 0.5))
        self.assertEqual(names.follow('ADR_L_Index2_hlf'), ('L_Index2', 0.5))
        self.assertEqual(names.follow('ADR_Head_bnd_hlf'), ('Head', 0.5))
        self.assertIsNone(names.follow('L_UpperArm'))
        self.assertIsNone(names.follow('ADR_L_UpperArm_twt_b'))           # moves with its parent


# ------------------------------------------------------------------------------------------------ load_model
class Loading(unittest.TestCase):
    def test_load_model(self):
        s = Store()
        mesh_package(s)
        logs = []
        k = model.load_model(s, [('bdf', PACKAGE)], ['bdf'], log=logs.append)
        b = k['bones']
        self.assertEqual(b['names'], ['MODEL_00', 'Hip__offset@Hip', 'L_Arm', 'HLP_L_Arm_Top__offset@'
                                      'ADR_L_DeltioidUp_bnd', 'HLP_L_Arm_Mid__offset@ADR_L_UpperArm_twt_b'])
        np.testing.assert_allclose(b['world'][1][:3, 3], [0, 970, 0], atol=1e-3)          # mm, Y up
        np.testing.assert_allclose(b['world'][4][:3, 3], [250, 1330, 0], atol=1e-3)
        self.assertEqual(b['follow'], [None, None, None, (2, 1.0), None])
        self.assertEqual([(p['part'], p['material']) for p in k['prims']], [('bdf', 'MI_Body')])
        self.assertTrue(any('M_CH_sim_mesh_material' in x for x in logs))                 # the proxy left out
        p = k['prims'][0]
        np.testing.assert_allclose(p['pos'][1], [100, 1000, 0], atol=1e-3)
        self.assertEqual(p['tris'].tolist(), [[0, 2, 1]])                                  # turned round
        np.testing.assert_allclose(p['nrm'][0], [0, 1, 0])
        self.assertEqual(p['tan'][:3, 3].tolist(), [-1, -1, 1])                          # the swap mirrors
        self.assertEqual(p['joints'][1, :2].tolist(), [1, 4])
        self.assertEqual(sorted(k['parts']), ['bdf'])
        self.assertEqual(k['parts']['bdf']['source_names'][1], 'Hip')


# ------------------------------------------------------------------------------------------------ repose
def donor():
    """A TTT2-like skeleton in a T-pose: (name, parent, world position mm), no rotations."""
    rows = [('HARA_ROT1', -1, (0, 1150, 0)), ('KOSHI_jnt', 0, (0, 1150, 0)), ('MUNE1_jnt', 1, (0, 1250, 0)),
            ('MUNE2_jnt', 2, (0, 1350, 0)), ('SAKOTSU_L_jnt', 3, (30, 1450, 0)), ('KATA_L_jnt', 4, (150, 1450, 0)),
            ('UDE_L_jnt', 5, (400, 1450, 0)), ('TE_L_jnt', 6, (650, 1450, 0))]
    pos = np.array([r[2] for r in rows], np.float64)
    parent = [r[1] for r in rows]
    t = np.array([pos[i] - (pos[p] if p >= 0 else 0) for i, p in enumerate(parent)], np.float32)
    return {'names': ['cha:' + r[0] for r in rows], 'parent': parent, 't': t, 'r': np.zeros((len(rows), 3), np.float32),
            's': np.ones((len(rows), 3), np.float32)}


def a_pose():
    """A model whose left arm hangs 45 degrees down (upper arm and forearm in line), with a twist helper hung from
    the shoulder that follows the upper arm, and vertices on it."""
    c = np.sqrt(0.5)
    rows = [('BASE', -1, (0, 1100, 0)), ('Hip', 0, (0, 1100, 0)), ('Spine1', 1, (0, 1200, 0)),
            ('Spine2', 2, (0, 1300, 0)), ('L_Shoulder', 3, (20, 1400, 0)), ('L_Arm', 4, (140, 1400, 0)),
            ('L_ForeArm', 5, (140 + 200 * c, 1400 - 200 * c, 0)), ('L_Hand', 6, (140 + 400 * c, 1400 - 400 * c, 0)),
            ('HLP_L_Arm_Top__offset@ADR_L_DeltioidUp_bnd', 4, (140, 1400, 0)),
            ('HLP_L_Arm_Mid__offset@ADR_L_UpperArm_twt_b', 8, (140 + 100 * c, 1400 - 100 * c, 0))]
    world = np.repeat(np.eye(4)[None], len(rows), 0)
    world[:, :3, 3] = [r[2] for r in rows]
    follow = [None] * len(rows)
    follow[8] = (5, 1.0)
    pos = np.array([[140 + 100 * c, 1400 - 100 * c, 30], [140 + 300 * c, 1400 - 300 * c, 0], [0, 1250, 50]])
    joints = np.zeros((3, 8), np.int64)
    weights = np.zeros((3, 8))
    joints[:, 0] = [9, 6, 2]
    weights[:, 0] = 1
    prim = dict(part='bdf', material='m', pos=pos, nrm=np.tile([0, 0, 1.0], (3, 1)),
                tan=np.tile([c, -c, 0, 1.0], (3, 1)), uv=np.zeros((3, 2)), joints=joints, weights=weights,
                tris=np.array([[0, 1, 2]]))
    return {'bones': {'names': [r[0] for r in rows], 'parents': [r[1] for r in rows], 'world': world,
                      'follow': follow}, 'prims': [prim], 'parts': {}}


class Repose(unittest.TestCase):
    def test_arm_to_t_pose(self):
        out = skeleton.repose(a_pose(), donor(), log=lambda *a: None)
        w = out['bones']['world']
        P = w[:, :3, 3]
        np.testing.assert_allclose(P[5], [140, 1400, 0], atol=1e-6)                        # the shoulder joint stays
        np.testing.assert_allclose(P[6], [340, 1400, 0], atol=1e-6)                        # elbow: level, same length
        np.testing.assert_allclose(P[7], [540, 1400, 0], atol=1e-6)
        np.testing.assert_allclose(P[9], [240, 1400, 0], atol=1e-6)                        # the helper follows
        np.testing.assert_allclose(w[5][:3, :3] @ [np.sqrt(0.5), -np.sqrt(0.5), 0], [1, 0, 0], atol=1e-9)
        p = out['prims'][0]
        np.testing.assert_allclose(p['pos'][0], [240, 1400, 30], atol=1e-6)               # on the helper
        np.testing.assert_allclose(p['pos'][1], [440, 1400, 0], atol=1e-6)                # on the forearm
        np.testing.assert_allclose(p['pos'][2], [0, 1250, 50], atol=1e-6)                 # the spine: unturned
        np.testing.assert_allclose(p['tan'][0], [1, 0, 0, 1], atol=1e-9)
        np.testing.assert_allclose(p['nrm'][0], [0, 0, 1], atol=1e-9)
        self.assertEqual(out['prims'][0]['tris'].tolist(), [[0, 1, 2]])

    def test_half_share(self):
        k = a_pose()
        k['bones']['follow'][8] = (5, 0.5)                                 # a '_hlf' joint: half the turn
        out = skeleton.repose(k, donor(), log=lambda *a: None)
        a = np.radians(22.5)                                              # 45 degrees down -> 22.5
        np.testing.assert_allclose(out['bones']['world'][9][:3, 3], [140 + 100 * np.cos(a), 1400 - 100 * np.sin(a), 0],
                                   atol=1e-6)

    def test_a_model_in_the_donors_pose_stays(self):
        k = a_pose()
        out = skeleton.repose(k, donor(), log=lambda *a: None)
        again = skeleton.repose(out, donor(), log=lambda *a: None)
        np.testing.assert_allclose(again['prims'][0]['pos'], out['prims'][0]['pos'], atol=1e-6)
        np.testing.assert_allclose(again['bones']['world'], out['bones']['world'], atol=1e-6)

    def test_nothing_to_turn(self):
        k = a_pose()
        k['bones']['names'] = ['x%d' % i for i in range(len(k['bones']['names']))]
        self.assertIs(skeleton.repose(k, donor(), log=lambda *a: None), k)


if __name__ == '__main__':
    unittest.main()
