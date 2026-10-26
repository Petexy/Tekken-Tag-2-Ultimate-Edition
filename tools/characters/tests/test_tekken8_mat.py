"""Tekken 8 materials, costumes and bakes (tekken8/material.py, costume.py, bake.py, skin.py) on made-up properties
and textures: parameters in effect along an instance chain, costume colour slots, the costume colour formula, the
hair, skin, eye bakes, the template a material becomes, the costume's parts and the reference faces.

Property values are what uprops.read gives (Unreal's vocabulary: colours {'R', 'G', 'B', 'A'}); a made-up store
hands them out by package.

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char import InputError                                # noqa: E402
from ttt2char.convert import skin as convert_skin              # noqa: E402
from ttt2char.tekken8 import bake, costume, material, skin, uprops   # noqa: E402

GREY = 128                          # an sRGB grey texel
LIN = float(material.SRGB_TO_LINEAR[GREY])


def rgba(*c):
    return {'R': c[0], 'G': c[1], 'B': c[2], 'A': c[3] if len(c) > 3 else 1.0}


def col(*c):
    return {'r': c[0], 'g': c[1], 'b': c[2], 'a': 1.0}


def param(name, value):
    return {'ParameterInfo': {'Name': name, 'Association': 0, 'Index': -1}, 'ParameterValue': value}


# ---------------------------------------------------------------------------------------------------- made-up store
class Export:
    def __init__(self, path, cls, size):
        self.path, self.class_name, self.offset, self.size = path, cls, 0, size
        self.name = path.rsplit('/', 1)[-1].split('.')[-1]


class Package:
    def __init__(self, path, cls, ced):
        self.path = path
        self.data = struct.pack('<II', 0, 1) if ced is not None else b''
        self.export = Export(path + '.' + path.rsplit('/', 1)[-1], cls, len(self.data))

    def main_export(self):
        return self.export


class Store:
    """Packages {package path: (class, properties, cached expression data of a base Material or None)}."""

    schema = None

    def __init__(self, packages):
        self.packages = packages

    def package(self, path):
        if path not in self.packages:
            raise KeyError(path)
        cls, _, ced = self.packages[path]
        return Package(path, cls, ced)

    def exists(self, path):
        return material.package_of(path) in self.packages

    def find(self, prefix):
        return sorted(p + '.uasset' for p in self.packages if p.startswith(prefix))

    def package_id(self, path):
        return None                                  # (costume.mesh_materials: no mesh headers here)

    def props(self, pkg, export, *args, **kw):
        return self.packages[pkg.path][1], 0

    def ced(self, pkg, schema, name, start, end):
        return self.packages[pkg.path][2], end

    def patched(self):
        """uprops.read / read_struct answering from the packages."""
        return mock.patch.multiple(uprops, read=self.props, read_struct=self.ced)


class Textures(material.Textures):
    """Images {path: (RGBA uint8 array, sRGB)} through material.Textures' conversions."""

    def __init__(self, images):
        material.Textures.__init__(self, None)
        self.images = images

    def exists(self, path):
        return path in self.images

    def image(self, path, max_size=None):
        return self.images[path]


def flat(h, w, *c, srgb=True):
    a = np.zeros((h, w, 4), np.uint8)
    a[...] = c if len(c) == 4 else tuple(c) + (255,)
    return (a, srgb)


# ---------------------------------------------------------------------------------------------------- materials
BASE = '/Game/Shader/M_CH_ITM_id_RGBA'
PARENT = '/Game/Shader/MI_CH_ITM_AN_LT'
CHILD = '/Game/zbr/MI_CH_zbr_outerwear'
FACE = '/Game/zbr/MI_CH_zbr_face_skin'
SKIN_BASE = '/Game/Shader/M_CH_skin_V3'
SHEER_MI = '/Game/zbr/MI_CH_zbr_stockings'
CED = {'RuntimeEntries[0]': {'ParameterInfoSet': [{'Name': 'Gamma'}, {'Name': 'ID01_DontColorOP'}]},
       'RuntimeEntries[1]': {'ParameterInfoSet': [{'Name': 'ID01_Color'}, {'Name': 'SplitNumberPerChannel'}]},
       'RuntimeEntries[3]': {'ParameterInfoSet': [{'Name': 'BaseColor_A'}, {'Name': 'BaseNormal_A'}]},
       'RuntimeEntries[7]': {'ParameterInfoSet': [{'Name': 'IsFace'}]},
       'ScalarValues': [2.2, 0.0], 'VectorValues': [rgba(0.5, 0.5, 0.5), rgba(1, 0, 0, 0)],
       'TextureValues': ['/Game/T/T_Grey.T_Grey', '/Game/T/T_Flat_N.T_Flat_N'], 'StaticSwitchValues': [False],
       'ReferencedTextures': ['/Game/T/T_Grey.T_Grey', '/Game/T/T_Flat_N.T_Flat_N', '/Game/T/T_Noise.T_Noise']}
PACKAGES = {
    BASE: ('Material', {'BlendMode': 0, 'TwoSided': True}, CED),
    PARENT: ('MaterialInstanceConstant', {
        'Parent': BASE + '.M_CH_ITM_id_RGBA', 'ScalarParameterValues': [param('Gamma', 2.0)],
        'VectorParameterValues': [param('ID01_Color', rgba(0.1, 0.2, 0.3))],
        'BasePropertyOverrides': {'bOverride_BlendMode': True, 'BlendMode': 1, 'bOverride_OpacityMaskClipValue': True,
                                  'OpacityMaskClipValue': 0.25, 'TwoSided': False}}, None),
    CHILD: ('MaterialInstanceConstant', {
        'Parent': PARENT + '.MI_CH_ITM_AN_LT',
        'TextureParameterValues': [param('BaseNormal_A', '/Game/zbr/T_Outer_N.T_Outer_N')],
        'VectorParameterValues': [param('ID01_Color', rgba(0.4, 0.5, 0.6))]}, None),
    SKIN_BASE: ('Material', {}, dict(CED, StaticSwitchValues=[False])),
    FACE: ('MaterialInstanceConstant', {
        'Parent': SKIN_BASE + '.M_CH_skin_V3',
        'StaticParametersRuntime': {'StaticSwitchParameters': [
            {'ParameterInfo': {'Name': 'IsFace'}, 'Value': True, 'bOverride': True}]}}, None),
    SHEER_MI: ('MaterialInstanceConstant', {
        'Parent': BASE + '.M_CH_ITM_id_RGBA',
        'BasePropertyOverrides': {'bOverride_ShadingModel': True, 'ShadingModel': uprops.Enum(2, 'MSM_Subsurface')}},
        None),
}


class Materials(unittest.TestCase):
    def setUp(self):
        self.store = Store(PACKAGES)
        self.patch = self.store.patched()
        self.patch.start()
        self.m = material.Materials(self.store)

    def tearDown(self):
        self.patch.stop()

    def test_chain_and_defaults(self):
        eff = self.m.effective(CHILD + '.MI_CH_zbr_outerwear')
        self.assertEqual(eff['name'], 'MI_CH_zbr_outerwear')
        self.assertEqual(eff['base'], 'M_CH_ITM_id_RGBA')
        self.assertEqual(eff['chain'], ['MI_CH_zbr_outerwear', 'MI_CH_ITM_AN_LT', 'M_CH_ITM_id_RGBA'])
        self.assertEqual(eff['scalars']['Gamma'], 2.0)                     # the parent's over the base's
        self.assertEqual(eff['vectors']['ID01_Color'], col(0.4, 0.5, 0.6))  # the child's last, Tekken 7's keys
        self.assertEqual(eff['vectors']['SplitNumberPerChannel'], {'r': 1.0, 'g': 0.0, 'b': 0.0, 'a': 0.0})
        self.assertEqual(eff['textures']['BaseColor_A'], '/Game/T/T_Grey.T_Grey')
        self.assertEqual(eff['textures']['Normal'], '/Game/zbr/T_Outer_N.T_Outer_N')   # the normal map's key
        self.assertEqual(eff['fixed'], ['/Game/T/T_Noise.T_Noise'])      # sampled, not a parameter
        self.assertEqual(eff['overrides']['BlendMode'], 1)
        self.assertTrue(eff['overrides']['TwoSided'])                     # not overridden: the base's
        self.assertEqual(eff['scalars']['AlphaThreshold'], 0.25)          # masked: the clip value

    def test_costume_colours_win(self):
        colours = {'MI_CH_zbr_outerwear': {'ID01_Color': col(0.9, 0.8, 0.7), 'ID01_DontColorOP': 1.0,
                                           'Pattern': '/Game/T/T_P.T_P'},
                   'MI_CH_other': {'ID01_Color': col(0, 0, 0)}}
        eff = self.m.effective(CHILD, colours)
        self.assertEqual(eff['vectors']['ID01_Color'], col(0.9, 0.8, 0.7))
        self.assertEqual(eff['scalars']['ID01_DontColorOP'], 1.0)
        self.assertEqual(eff['textures']['Pattern'], '/Game/T/T_P.T_P')
        self.assertEqual(self.m.effective(CHILD, None)['vectors']['ID01_Color'], col(0.4, 0.5, 0.6))

    def test_scalp_and_sheer_entries_by_kind(self):
        colours = {material.SCALP: {material.HAIR_SCALP_MASK: '/Game/h/T_SCM.T_SCM',
                                    material.SCALP_COLOUR: col(0.02, 0.02, 0.02)},
                   material.SHEER: {bake.SHEER_COLOUR: col(0.5, 0.2, 0.1)}}
        face = self.m.effective(FACE, colours)
        self.assertTrue(face['switches']['IsFace'])
        self.assertEqual(face['textures'][material.HAIR_SCALP_MASK], '/Game/h/T_SCM.T_SCM')
        self.assertEqual(face['vectors'][material.SCALP_COLOUR], col(0.02, 0.02, 0.02))
        self.assertNotIn(bake.SHEER_COLOUR, face['vectors'])
        cloth = self.m.effective(CHILD, colours)
        self.assertNotIn(material.HAIR_SCALP_MASK, cloth['textures'])
        self.assertNotIn(bake.SHEER_COLOUR, cloth['vectors'])
        sheer = self.m.effective(SHEER_MI, colours)
        self.assertEqual(sheer['overrides']['ShadingModel'], 2)
        self.assertEqual(sheer['vectors'][bake.SHEER_COLOUR], col(0.5, 0.2, 0.1))
        self.assertNotIn('AlphaThreshold', sheer['scalars'])              # opaque
        self.assertNotIn(material.SCALP, material.unpainted(colours))
        self.assertIn(material.SHEER, material.unpainted(colours))
        self.assertEqual(material.unpainted(None), {})

    def test_not_a_costume(self):
        with self.assertRaises(InputError):
            self.m.costume_colours(CHILD)
        self.assertEqual(self.m.costume_colours(None), {})
        self.assertEqual(self.m.costume_colours({'colours': {'a': {}}}), {'a': {}})


# ---------------------------------------------------------------------------------------------------- costumes
CS = '/Game/Character/Item/Customize_Set/zbr/CS_zbr_1p'
IP = '/Game/Character/Item/Item_Prefab/zbr/%s/IP_zbr_%s'
BI = '/Game/Character/Item/Base_Item/zbr/BI_zbr_%s'
BCI = '/Game/Character/Item/Base_Character_Item/zbr/BCI_zbr_%s'
CI = '/Game/Character/Item/Customize_Item/zbr/CI_zbr_%s'
MESH = '/Game/Character/Item/model/unique/zbr/%s/meshes/SK_CH_zbr_%s_msl'
HAIR_MI = '/Game/zbr/MI_CH_zbr_har_1p'
HAIR_BASE = '/Game/Shader/M_Hair_Ver7'


def slot(*c, dont=0.0):
    return {'DesignAssign_Color': {'Assign_Color': rgba(*c), 'Assign_DontColor': dont}}


def ids(*entries):
    """DesignAssignArray entries: (slot number, own colour) or None (an ID left off)."""
    out = []
    for e in entries:
        if e is None:
            out.append({'isEnableId': False})
        elif e == 'source':
            out.append({'isEnableId': True, 'isUseSourceMaterial': True})
        else:
            out.append({'isEnableId': True, 'useSlotNumber': e[0],
                        'DesignAssign_Color': slot(*e[1])['DesignAssign_Color']})
    return out


def prefab(name, mesh_tag, pos, ci=None, forced=(), static=None, scalp=None):
    base = {'SetItemPositionId': pos}
    if static:
        base.update(MeshType=uprops.Enum(costume.STATIC_MESH, 'E_StaticMesh'), SourceStaticMesh=static)
    else:
        base['SourceSkeletalMeshSet'] = {'SourceMuscleRigMesh': MESH % (mesh_tag, mesh_tag) + '.x',
                                         'SourceProportionRigMesh': MESH % (mesh_tag, mesh_tag) + '_prp.x'}
    if scalp:
        base['HairScalpMask'] = scalp
    out = {BI % name: ('BaseItem', base, None),
           BCI % name: ('BaseCharacterItem', {'FighterId': 28, 'AssignTargetDependencyMeshArray': [
               {'TargetMeshPos': p, 'TargetDependencyMuscleRigMesh': m, 'Priority': k} for p, m, k in forced]}, None)}
    ref = {'BaseItemRef': BI % name + '.x', 'BaseCharacterItemRef': BCI % name + '.x'}
    if ci:
        out[CI % name] = ('CustomizeItem', ci, None)
        ref['CustomizeItemRef'] = CI % name + '.x'
    out[IP % (mesh_tag[:3], name)] = ('ItemPrefab', ref, None)
    return out


def costume_packages():
    body_ci = {'DesignAssignSlotArray': [slot(0.1, 0.1, 0.1), slot(0.25, 0.13, 0.92, dont=1.0)],
               'AssignPerMaterialArray': [
                   {'MaterialAssign_Preview': CHILD + '.MI_CH_zbr_outerwear',
                    'DesignAssignArray': ids((1, (0, 0, 0)), (-1, (0.5, 0.6, 0.7)), None, 'source')},
                   {'MaterialAssign_Preview': SHEER_MI + '.x', 'isUseSourceMaterial_All': True,
                    'DesignAssignArray': ids((0, (0, 0, 0)))}]}
    hair_ci = {'DesignAssignSlotArray': [],
               'AssignPerMaterialArray': [{'MaterialAssign_Preview': HAIR_MI + '.MI_CH_zbr_har_1p',
                                           'DesignAssignArray': ids((-1, (0.01, 0.01, 0.01)), (-1, (0.1, 0.1, 0.9)),
                                                                    (-1, (1, 1, 1)))}]}
    p = dict(PACKAGES)
    p[HAIR_BASE] = ('Material', {}, None)
    p[HAIR_MI] = ('MaterialInstanceConstant', {'Parent': HAIR_BASE + '.M_Hair_Ver7'}, None)
    p.update(prefab('bdf_1p', 'bdf_1p', 6, body_ci, forced=[(1, MESH % ('har_1p_I', 'har_1p_I'), 1),
                                                             (1, MESH % ('har_1p_F', 'har_1p_F'), 5)]))
    p.update(prefab('fac', 'fac', 2))
    p.update(prefab('har_1p', 'har_1p', 1, hair_ci, scalp='/Game/zbr/T_CH_zbr_har_1p_SCM.T_CH_zbr_har_1p_SCM'))
    p.update(prefab('gla', 'gla', 4, static='/Game/common/SM_glasses.SM_glasses'))
    p[CS] = ('CustomizeSet', {'ItemPrefabSet': [IP % ('bdf', 'bdf_1p') + '.x', IP % ('fac', 'fac') + '.x',
                                                IP % ('har', 'har_1p') + '.x'],
                              'ItemPrefabAccSet': [IP % ('gla', 'gla') + '.x', None]}, None)
    return p


class Costumes(unittest.TestCase):
    def setUp(self):
        self.store = Store(costume_packages())
        self.patch = self.store.patched()
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_customize_colours(self):
        m = material.Materials(self.store)
        props = self.store.packages[CI % 'bdf_1p'][1]
        c = material.customize_colours(props, m)
        self.assertEqual(set(c), {'MI_CH_zbr_outerwear'})                # the whole-material source one left out
        o = c['MI_CH_zbr_outerwear']
        self.assertEqual(o['ID01_Color'], col(0.25, 0.13, 0.92))        # slot 1's colour and DontColor
        self.assertEqual(o['ID01_DontColorOP'], 1.0)
        self.assertEqual(o['ID02_Color'], col(0.5, 0.6, 0.7))           # its own (slot -1)
        self.assertEqual(o['ID02_DontColorOP'], 0.0)
        self.assertNotIn('ID03_Color', o)                                # off
        self.assertNotIn('ID04_Color', o)                                # the material's own
        hair = material.customize_colours(self.store.packages[CI % 'har_1p'][1], m)['MI_CH_zbr_har_1p']
        self.assertEqual(hair, {'RootColor': col(0.01, 0.01, 0.01), 'TipColor': col(0.1, 0.1, 0.9)})

    def test_costume(self):
        c = costume.costume(self.store, 'zbr', '1p')
        self.assertEqual(c['set'], CS)
        self.assertEqual([t for t, _ in c['parts']], ['fac', 'har', 'bdf'])
        self.assertEqual(c['merge_order'], ['fac', 'bdf', 'har'])
        self.assertEqual(dict(c['parts'])['har'], MESH % ('har_1p_F', 'har_1p_F'))   # the body's variant (priority)
        self.assertEqual(dict(c['parts'])['fac'], MESH % ('fac', 'fac'))              # the muscle rig mesh
        self.assertEqual(c['static'], [('gla', '/Game/common/SM_glasses')])
        self.assertEqual(c['colours']['MI_CH_zbr_outerwear']['ID02_Color'], col(0.5, 0.6, 0.7))
        self.assertEqual(c['colours'][material.SCALP], {
            material.HAIR_SCALP_MASK: '/Game/zbr/T_CH_zbr_har_1p_SCM.T_CH_zbr_har_1p_SCM',
            material.SCALP_COLOUR: col(0.01, 0.01, 0.01)})
        self.assertNotIn(material.SHEER, c['colours'])                   # (no mesh headers: no skin found)
        self.assertEqual(len(c['prefabs']), 4)

    def test_missing_set(self):
        with self.assertRaises(InputError) as e:
            costume.costume(self.store, 'zbr', 'kimono')
        self.assertIn('it has: 1p', str(e.exception))

    def test_sheer_skin_colour(self):
        skin_mi = '/Game/zbr/MI_CH_zbr_body_skin'
        self.store.packages[skin_mi] = ('MaterialInstanceConstant', {
            'Parent': SKIN_BASE + '.x', 'VectorParameterValues': [param('TintColor', rgba(0.5, 1.0, 1.0))],
            'TextureParameterValues': [param('tx01_BaseColor', '/Game/T/T_Body_C.x')]}, None)
        images = {'/Game/T/T_Body_C.x': flat(4, 4, GREY, GREY, GREY)}
        with mock.patch.object(costume, 'mesh_materials', lambda store, mesh: [FACE + '.x', skin_mi + '.x']), \
                mock.patch.object(material, 'Textures', lambda store, size: Textures(images)):
            c = costume.costume(self.store, 'zbr', '1p')
        s = c['colours'][material.SHEER][bake.SHEER_COLOUR]
        self.assertAlmostEqual(s['r'], 0.5 * LIN, 5)                     # the body skin's (not the face's)
        self.assertAlmostEqual(s['g'], LIN, 5)


# ---------------------------------------------------------------------------------------------------- bakes
def costume_eff(split=(1, 1, 0, 0), colours=None, **extra):
    v = {'SplitNumberPerChannel': dict(zip('rgba', map(float, split)))}
    v.update(colours or {})
    eff = {'name': 'MI_CH_test', 'base': 'M_CH_ITM_id_RGBA', 'textures': {'BaseColor_A': 'A', 'ID_Map': 'ID'},
           'vectors': v, 'scalars': {'Gamma': 2.2, 'Degamma': 1 / 2.2}, 'overrides': {'ShadingModel': 1}}
    for k, x in extra.items():
        eff[k].update(x)
    return eff


def id_map(texels):
    """[(R, G, B, A)] -> a 1 x n ID map image (linear)."""
    return (np.array([texels], np.uint8), False)


class Bakes(unittest.TestCase):
    def test_id_levels(self):
        k, m = bake.id_levels(np.array([0, 85, 170, 255, 200, 43], np.uint8), 3)
        self.assertEqual(k.tolist(), [0, 1, 2, 3, 3, 1])
        np.testing.assert_allclose(m, [0, 1, 1, 1, 90 / 255.0, 129 / 255.0], atol=1e-6)
        k, m = bake.id_levels(np.array([255, 51], np.uint8), 5)
        self.assertEqual(k.tolist(), [0, 1])                             # a fifth level holds no ID
        self.assertEqual(float(m[0]), 0.0)

    def test_ab_blend(self):
        a, b = np.float32(0.25), np.float32(0.5)
        self.assertAlmostEqual(float(bake.ab_blend(a, b, 1)), 0.125)
        self.assertAlmostEqual(float(bake.ab_blend(a, b, 2)), 0.75)
        self.assertAlmostEqual(float(bake.ab_blend(a, b, 12)), 0.25)     # overlay, a < 0.5: 2ab
        self.assertAlmostEqual(float(bake.ab_blend(np.float32(0.75), b, 12)), 0.75)   # 1 - 2(1 - a)(1 - b)

    def test_costume_formula(self):
        purple, white = (0.25, 0.13, 0.92), (1.0, 1.0, 1.0)
        tex = Textures({'A': flat(1, 6, GREY, GREY, GREY),
                        'ID': id_map([(255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 0, 0), (128, 0, 0, 0),
                                      (255, 255, 0, 0), (255, 0, 0, 0)])})
        eff = costume_eff(colours={'ID01_Color': col(*purple), 'ID05_Color': col(*white)})
        rgb, alpha = bake.bake_albedo(eff, tex)
        self.assertIsNone(alpha)
        L = LIN                                                          # grey: luma = the value; ** Degamma ** Gamma
        gain = 1 + 20 * (0.92 - 0.9)                                     # max(C) above 0.9: brightened
        np.testing.assert_allclose(rgb[0, 0], np.array(purple) * L * gain, rtol=1e-4)   # ID01: k(C) L C
        np.testing.assert_allclose(rgb[0, 1], np.array(white) * L * 3, rtol=1e-4)   # ID05 white: gain 1 + 20 * 0.1
        np.testing.assert_allclose(rgb[0, 2], [L, L, L], rtol=1e-4)                 # no ID: the detail texture
        half = 1 + 128 / 255.0 * (np.array(purple) - 1)                             # the ramp: lerp(1, C, mask)
        np.testing.assert_allclose(rgb[0, 3], half * L * max(1, 1 + 20 * (half.max() - 0.9)), rtol=1e-4)
        np.testing.assert_allclose(rgb[0, 4], rgb[0, 1], rtol=1e-6)                 # G lies on top of R
        eff = costume_eff(colours={'ID01_Color': col(*purple)}, scalars={'ID01_DontColorOP': 1.0})
        rgb, _ = bake.bake_albedo(eff, tex)
        np.testing.assert_allclose(rgb[0, 0], [L, L, L], rtol=1e-4)                 # DontColor: back to the detail

    def test_masked_and_sheer(self):
        tex = Textures({'A': flat(2, 2, GREY, GREY, GREY), 'ID': id_map([(255, 0, 0, 0)] * 2),
                        'OBD': flat(2, 2, 255, 0, 0, srgb=False)})
        tex.images['OBD'][0][0, 0, 0] = 0
        eff = costume_eff(colours={'ID01_Color': col(0.3, 0.15, 0.1)}, textures={'OBD': 'OBD'})
        self.assertIsNone(bake.bake_albedo(eff, tex)[1])                  # opaque: no alpha
        eff['scalars']['AlphaThreshold'] = 1 / 3.0
        rgb, alpha = bake.bake_albedo(eff, tex)
        self.assertEqual(alpha.tolist(), [[0.0, 1.0], [1.0, 1.0]])        # OBD red
        self.assertEqual(bake.classify('MI_CH_x_skirt', eff, alpha), ('cloth', True, True))
        eff = costume_eff(colours={'ID01_Color': col(0.3, 0.15, 0.1), bake.SHEER_COLOUR: col(0.5, 0.2, 0.15)},
                          overrides={'ShadingModel': uprops.Enum(2, 'MSM_Subsurface')})
        rgb, _ = bake.bake_albedo(eff, tex)
        dark = np.array([0.3, 0.15, 0.1]) * LIN
        np.testing.assert_allclose(rgb[0, 0], dark + bake.SHEER * (np.array([0.5, 0.2, 0.15]) - dark), rtol=1e-4)

    def test_skin(self):
        tex = Textures({'C': flat(2, 2, GREY, GREY, GREY), 'SCM': flat(2, 2, 0, 0, 0, 0),
                        'HAIR': flat(2, 2, 0, 0, 0, 0)})
        tex.images['SCM'][0][0, 0] = (255, 0, 0, 0)                      # R: the brow shadow
        tex.images['HAIR'][0][1, 1] = (0, 0, 0, 255)                     # A: the hair's scalp
        eff = {'name': 'MI_CH_zbr_face_skin', 'base': 'M_CH_skin_V3', 'textures': {
            'tx01_BaseColor': 'C', 'tx11_ScalpMask': 'SCM', material.HAIR_SCALP_MASK: 'HAIR'},
            'vectors': {'TintColor': col(1.0, 0.5, 0.5), 'ScalpColor_Eyebrow': col(0.1, 0.05, 0.0),
                        material.SCALP_COLOUR: col(0.01, 0.01, 0.01)}, 'scalars': {}, 'overrides': {}}
        rgb, alpha = bake.bake_albedo(eff, tex)
        self.assertIsNone(alpha)
        np.testing.assert_allclose(rgb[0, 1], [LIN, LIN / 2, LIN / 2], rtol=1e-5)   # colour x TintColor
        np.testing.assert_allclose(rgb[0, 0], [0.1, 0.05, 0.0], atol=1e-6)
        np.testing.assert_allclose(rgb[1, 1], [0.01, 0.01, 0.01], atol=1e-6)
        self.assertEqual(bake.classify(eff['name'], eff, None), ('skin', True, False))

    def test_hair(self):
        root = np.zeros((1, 2, 4), np.uint8)
        root[0, 1] = 255
        adi = np.zeros((1, 2, 4), np.uint8)
        adi[0, :, 0] = (100, 255)
        tex = Textures({'R': (root, False), 'ADI': (adi, False)})
        eff = {'name': 'MI_CH_zbr_har_1p', 'base': 'M_Hair_Ver7', 'textures': {'Root': 'R', 'ADI Map': 'ADI'},
               'vectors': {'RootColor': col(0.0, 0.0, 0.0), 'TipColor': col(0.1, 0.1, 0.9)},
               'scalars': {'TipPower': 1.0, 'OpacityIntensity': 2.0, 'AlphaThreshold': 0.3}, 'overrides': {}}
        rgb, alpha, _ = bake.hair_colour(eff, tex)
        np.testing.assert_allclose(rgb[0], [[0, 0, 0], [0.1, 0.1, 0.9]], atol=1e-6)   # root to tip
        np.testing.assert_allclose(alpha[0], [200 / 255.0, 1.0], atol=1e-6)          # ADI red x OpacityIntensity
        brow = dict(eff, name='MI_CH_zbr_eyebrow')
        np.testing.assert_allclose(bake.bake_albedo(brow, tex)[0], rgb, atol=1e-6)   # an overlay as it is
        look, _ = bake.bake_albedo(eff, tex)                                        # head hair: TTT2's look
        grey = bake.HAIR_GAIN * (0.0 + bake.HAIR_LIFT) ** bake.HAIR_POWER
        np.testing.assert_allclose(look[0, 0], [grey] * 3, rtol=1e-4)               # black: lifted, as TTT2's
        self.assertGreater(look[0, 1, 2] / look[0, 1, 0], 2)                        # the blue tip: blue still,
        self.assertLess(look[0, 1, 2] / look[0, 1, 0], 9)                           # paler than its base colour
        self.assertEqual(bake.classify(eff['name'], eff, alpha), ('hair', False, True))
        self.assertEqual(bake.classify('MI_CH_zbr_eyelash', eff, alpha), ('overlay', False, True))

    def test_hair_strands(self):
        """The strands' variation (ADI blue: an ID each; value and hue) and shading (ADI green: depth)."""
        adi = np.zeros((1, 4, 4), np.uint8)
        adi[0, :, 0] = 255
        adi[0, :, 2] = (0, 255, 0, 255)                                  # IDs: 0, 1
        adi[0, :, 1] = (255, 255, 0, 0)                                  # depth: on top, deep
        tex = Textures({'ADI': (adi, False)})
        eff = {'name': 'MI_CH_zbr_har_1p', 'base': 'M_Hair_Ver7', 'textures': {'ADI Map': 'ADI'},
               'vectors': {'RootColor': col(0.2, 0.2, 0.2)}, 'overrides': {},
               'scalars': {'RandomValueVariation': 0.5, 'Random_Min': 0.5, 'Random_Max': 1.5,
                           'RandomHueVariation': 0.0, 'TextureAO_Min': 0.4, 'TextureAO_Max': 1.0}}
        rgb, _, _ = bake.hair_colour(eff, tex)
        np.testing.assert_allclose(rgb[0, :2, 0], [0.2 * 0.75, 0.2 * 1.25], rtol=1e-5)   # 1 + 0.5 (lerp - 1)
        look, _ = bake.bake_albedo(eff, tex)
        self.assertGreater(look[0, 0, 0], look[0, 2, 0])                  # the same ID: deep strands darker
        self.assertAlmostEqual(look[0, 0, 0] / look[0, 2, 0], 2.5 ** bake.HAIR_STRANDS, places=4)
        turned = bake.hue_turn(np.array([[1.0, 0.85, 0.85]]), np.array([2 * np.pi / 3]))
        np.testing.assert_allclose(turned, [[0.85, 1.0, 0.85]], atol=1e-6)   # a third of a turn: red -> green

    def test_specular(self):
        """The cloth shine (TTT2's third texture): R = (1 - roughness + SATIN AnisoPower) lerp(1, AO, 0.5),
        G = REFLECTION metallic (1 - roughness), A = gloss from roughness; AnisoPower per ID as the colours layer."""
        rma = np.zeros((1, 4, 4), np.uint8)
        rma[0, :, 0] = (178, 178, 255, 51)                               # roughness 0.7, 0.7, 1, 0.2
        rma[0, :, 1] = (0, 0, 0, 255)                                    # metallic
        rma[0, :, 2] = (255, 255, 0, 255)                                # AO
        tex = Textures({'RMA': (rma, False),
                        'ID': id_map([(255, 0, 0, 0), (0, 0, 0, 0), (255, 255, 0, 0), (0, 0, 0, 0)])})
        eff = costume_eff(scalars={'ID01_AnisoPower': 0.7, 'ID05_AnisoPower': 0.0})
        eff['textures']['RMA_A'] = 'RMA'
        sp = bake.specular(eff, tex).astype(np.float64) / 255
        self.assertEqual(sp.shape, (1, 4, 4))
        r = 1 - 178 / 255.0
        np.testing.assert_allclose(sp[0, :, 0], [r + bake.SATIN * 0.7, r, bake.SATIN * 0.0 * 0.5, 0.8], atol=1 / 255)
        self.assertGreater(sp[0, 0, 0], 2 * sp[0, 1, 0])                 # the satin ID shines; the same roughness
        self.assertEqual(sp[0, 2, 0], 0)                                 # (G lies on top of R: ID05, no satin)
        np.testing.assert_allclose(sp[0, :, 1], [0, 0, 0, bake.REFLECTION * 0.8], atol=1 / 255)
        np.testing.assert_allclose(sp[0, :, 3], bake.GLOSS_TOP - bake.GLOSS_SLOPE * rma[0, :, 0] / 255.0, atol=1 / 255)
        del eff['textures']['ID_Map']                                    # no ID map: roughness alone
        np.testing.assert_allclose(bake.specular(eff, tex)[0, 0, 0] / 255, r, atol=1 / 255)
        del eff['textures']['RMA_A']
        self.assertIsNone(bake.specular(eff, tex))

    def test_eye(self):
        tex = Textures({'S': flat(16, 16, 255, 255, 255), 'I': flat(16, 16, 0, 0, 255)})
        eff = {'name': 'MI_CH_zbr_eye_L', 'base': 'M_CH_Eyes', 'textures': {'Sclera': 'S', 'IrisColor': 'I'},
               'vectors': {'ScleraTint': col(0.9, 0.9, 0.9)}, 'scalars': {'UV_Scale': 2.0}, 'overrides': {}}
        rgb, alpha = bake.bake_albedo(eff, tex)
        self.assertEqual(rgb.shape, (16, 16, 3))
        np.testing.assert_allclose(rgb[8, 8], [0, 0, 1], atol=1e-3)      # the iris in the middle
        np.testing.assert_allclose(rgb[0, 0], [0.9, 0.9, 0.9], atol=1e-3)
        self.assertEqual(bake.classify(eff['name'], eff, None), ('eye', False, False))

    def test_other_bases(self):
        tex = Textures({'M': flat(2, 2, GREY, 0, 0)})
        eff = {'name': 'MI_CH_fac_inner_mouth', 'base': 'M_Ch_Skin_Simple', 'textures': {'BaseColor': 'M'},
               'vectors': {}, 'scalars': {}, 'overrides': {}}
        rgb, alpha = bake.bake_albedo(eff, tex)
        np.testing.assert_allclose(rgb[0, 0], [LIN, 0, 0], atol=1e-6)
        self.assertEqual(bake.classify(eff['name'], eff, None), ('mouth', True, False))
        eff['textures'] = {}
        self.assertEqual(bake.bake_albedo(eff, tex), (None, None))

    def test_classify_left_out(self):
        for name, base in (('MI_Cal_Mesh', 'M_CalculationMesh'), ('MI_CH_zbr_eye_ao', 'M_Eye_Blur_AO'),
                           ('MI_CH_zbr_add_tealine', 'M_Add_Tear'),
                           ('M_CH_sim_mesh_material', 'M_CH_sim_mesh_material'), ('MI_CH_x_tear', 'M_Whatever')):
            self.assertIsNone(bake.classify(name, base, None), name)
        self.assertEqual(bake.classify('MI_CH_x_pants', 'M_CH_ITM_id_RGBA', None), ('cloth', True, False))
        self.assertEqual(bake.classify('MI_CH_x_teeth', 'M_Ch_Skin_Simple', None), ('mouth', False, False))


# ---------------------------------------------------------------------------------------------------- faces
class Faces(unittest.TestCase):
    def test_reference_faces(self):
        women = skin.reference_faces('female')
        men = skin.reference_faces('male')
        self.assertEqual(len(women) + len(men), len(skin.reference_faces()))
        self.assertTrue(all(code in convert_skin.WOMEN for code, _ in women))
        self.assertFalse(any(code in convert_skin.WOMEN for code, _ in men))
        self.assertIn(('jun', '/Game/Character/Item/model/unique/aml/face/aml_fac/materials/MI_CH_aml_face_skin.'
                              'MI_CH_aml_face_skin'), women)
        codes = [code for code, _ in skin.reference_faces()]
        self.assertEqual(len(codes), len(set(codes)))                   # one face per TTT2 fighter

        class Have:
            def exists(self, path):
                return '/aml/' in path
        self.assertEqual([c for c, _ in skin.reference_faces(store=Have())], ['jun'])


if __name__ == '__main__':
    unittest.main()
