"""Tekken 8 materials and costume colours.

A MaterialInstanceConstant's properties (uprops) hold Parent (a Material or another instance), ScalarParameterValues,
VectorParameterValues and TextureParameterValues ({ParameterInfo {Name, Association, Index}, ParameterValue}),
StaticParametersRuntime.StaticSwitchParameters and BasePropertyOverrides (each of BlendMode, TwoSided,
OpacityMaskClipValue, ShadingModel counts where its bOverride_ flag is set; the other values are the parent's copied).
A base Material keeps its parameter defaults after its properties: u32 0 (no GUID), u32 1 (cached expression data
saved), then FMaterialCachedExpressionData (unversioned): RuntimeEntries[t].ParameterInfoSet names the parameters of
type t (0 scalar, 1 vector, 3 texture, 7 static switch) in the order of ScalarValues, VectorValues, TextureValues (soft
object paths) and StaticSwitchValues. The values in effect: base defaults < instance chain (child last) < the
costume's colours; blend mode, two-sidedness and the opacity mask cut: the base Material's properties < the
instances' overrides.

Costume colours: a CustomizeItem (CI_<code>_<part>_1p / _2p, the item prefab's CustomizeItemRef) holds
DesignAssignSlotArray (the costume's colour slots: DesignAssign_Color {Assign_Color (linear), Assign_DontColor, hue
shifts}) and AssignPerMaterialArray [{MaterialAssign_Preview (the material instance), MaterialAssign_Override,
DesignAssignArray[ID - 1] {DesignAssign_Color, isEnableId, isUseSourceMaterial, useSlotNumber}}]: ID n of that
material takes slot useSlotNumber's colour and DontColor (its own when -1) as IDnn_Color and IDnn_DontColorOP,
unless the ID is off (isEnableId) or keeps the material's own values (isUseSourceMaterial). A hair material (M_Hair*:
hair, brows, lashes) has no ID parameters: ID 1 is its RootColor and ID 2 its TipColor (CI_zbr_har_1p's equal
MI_CH_zbr_har_1p's own). The hue shifts (Assign_EnableChangeHue ...) are off in the default costumes and not applied.
Two entries apply to materials by kind rather than name: SCALP, for the face skin (static switch IsFace): the hair's
BaseItem names a scalp mask in the face's UV layout (HairScalpMask), painted with the hair's root colour
(ScalpColor_Hair01; bake.py); SHEER, for sheer cloth (ShadingModel Subsurface): the colour of the skin under it.

Written for this project from the files themselves (no third-party code).
"""
import struct

import numpy as np

from .. import InputError
from . import texture, uprops, zen

# Material class defaults (a property a package leaves out has its class default)
MATERIAL_DEFAULTS = {'BlendMode': 0, 'TwoSided': False, 'OpacityMaskClipValue': 1.0 / 3.0, 'ShadingModel': 1}
OVERRIDES = ('BlendMode', 'TwoSided', 'OpacityMaskClipValue', 'ShadingModel')
BLEND_OPAQUE, BLEND_MASKED, BLEND_TRANSLUCENT, BLEND_ADDITIVE = 0, 1, 2, 3
# FMaterialCachedExpressionData.RuntimeEntries index -> (effective key, values array)
PARAMETER_TYPES = ((0, 'scalars', 'ScalarValues'), (1, 'vectors', 'VectorValues'), (3, 'textures', 'TextureValues'),
                   (7, 'switches', 'StaticSwitchValues'))
MAX_DEPTH = 10                      # instance chain length (Tekken 8's are 1-3)
BAKE_SIZE = 1024                    # mip decoded for a bake: the first whose longest side is at most this (mip 1 of
                                    # Tekken 8's 2048 maps; TTT2 keeps 512 at most, its 2P colour fit likes more)
DIRECT_SIZE = 512                   # mip decoded for a texture copied as it is (normal maps): TTT2's largest
HAIR_IDS = {1: 'RootColor', 2: 'TipColor'}      # a hair material's costume IDs
SCALP = '*scalp'                    # colours entry: the hair's scalp painting, for the face skin (switch IsFace)
HAIR_SCALP_MASK = 'HairScalpMask'   # (the BaseItem property's name) the hair's mask, painted ScalpColor_Hair01
SCALP_COLOUR = 'ScalpColor_Hair01'  # the face skin's colour for its scalp mask's alpha (the hair's root colour)
SHEER = '*sheer'                    # colours entry for sheer cloth (ShadingModel Subsurface): the skin colour under it
SHADING_SUBSURFACE = 2              # EMaterialShadingModel MSM_Subsurface
# normal map parameter by base material family (the key Tekken 7's vocabulary calls Normal)
NORMALS = ('BaseNormal_A', 'tx04_Normal', 'Normal', 'NormalMap', 'tx02_Normal')


def short(path):
    """'/Game/X/MI_Y.MI_Y' -> 'MI_Y'."""
    return zen.short_name(path) if path else path


def package_of(path):
    """An object path's package ('/Game/X/Y.Y' -> '/Game/X/Y')."""
    return path.split('.', 1)[0] if path else path


def colour(c):
    """Unreal's {'R', 'G', 'B', 'A'} -> Tekken 7's {'r', 'g', 'b', 'a'}."""
    return {'r': float(c.get('R', 0.0)), 'g': float(c.get('G', 0.0)), 'b': float(c.get('B', 0.0)),
            'a': float(c.get('A', 1.0))}


def _name(p):
    info = p.get('ParameterInfo') or {}
    return info.get('Name')


def _srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


UNORM = (np.arange(256) / 255.0).astype(np.float32)                 # 8-bit texel -> 0..1
SRGB_TO_LINEAR = _srgb_to_linear(np.arange(256) / 255.0).astype(np.float32)   # (a table: 10x faster than the formula)


# ---------------------------------------------------------------------------------------------------- textures
class Textures:
    """Tekken 8 textures by object path (model.Textures' interface), decoded once at the mip a use needs (only that
    mip's bytes are read: texture.py): get() for a texture copied as it is (a normal map; DIRECT_SIZE), linear() and
    image() for a bake (BAKE_SIZE). An ID map has one mip, whatever its size."""

    def __init__(self, store, max_size=BAKE_SIZE, direct_size=DIRECT_SIZE):
        self.store, self.max_size, self.direct_size = store, max_size, direct_size
        self._cache = {}
        self._exists = {}

    def exists(self, path):
        if not path:
            return False
        if path not in self._exists:
            self._exists[path] = self.store.exists(package_of(path))
        return self._exists[path]

    def image(self, path, max_size=None):
        """-> (RGBA uint8 array, sRGB flag) of the largest mip at most max_size (default: the bake size) on a side"""
        key = (path, max_size or self.max_size)
        if key not in self._cache:
            t = texture.Texture2D(self.store, package_of(path))
            self._cache[key] = (t.decode(key[1]), t.srgb)
        return self._cache[key]

    def get(self, path, max_size=None):
        """-> (RGBA uint8 array, sRGB flag) of a texture copied as it is (TTT2 keeps 512 at most)"""
        return self.image(path, max_size or self.direct_size)

    def linear(self, path, max_size=None):
        """-> (linear RGB float32, alpha float32) at the bake size"""
        img, srgb = self.image(path, max_size)
        return (SRGB_TO_LINEAR if srgb else UNORM)[img[..., :3]], UNORM[img[..., 3]]


class Materials:
    def __init__(self, store):
        self.store = store
        self._objects = {}
        self._defaults = {}

    def _read(self, path):
        pkg = self.store.package(package_of(path))
        ex = pkg.main_export()
        props, end = uprops.read(pkg, ex)
        return pkg, ex, props, end

    def instance(self, path):
        """One material object -> {'path', 'name', 'cls', 'parent', 'scalars', 'vectors', 'textures', 'switches',
        'overrides' (the ones whose bOverride_ flag is set), 'props'}."""
        key = package_of(path)
        if key not in self._objects:
            pkg, ex, props, _ = self._read(path)
            m = {'path': ex.path, 'name': ex.name, 'cls': ex.class_name, 'parent': props.get('Parent'), 'props': props,
                 'scalars': {}, 'vectors': {}, 'textures': {}, 'switches': {}, 'overrides': {}}
            for p in props.get('ScalarParameterValues') or []:
                m['scalars'][_name(p)] = float(p.get('ParameterValue', 0.0))
            for p in props.get('VectorParameterValues') or []:
                m['vectors'][_name(p)] = colour(p.get('ParameterValue') or {})
            for p in props.get('TextureParameterValues') or []:
                m['textures'][_name(p)] = p.get('ParameterValue')
            static = props.get('StaticParametersRuntime') or {}
            for p in static.get('StaticSwitchParameters') or [] if isinstance(static, dict) else []:
                if p.get('bOverride', True):
                    m['switches'][_name(p)] = bool(p.get('Value'))
            ov = props.get('BasePropertyOverrides') or {}
            for k in OVERRIDES:
                if ov.get('bOverride_' + k):
                    m['overrides'][k] = ov.get(k, MATERIAL_DEFAULTS[k])
            self._objects[key] = m
        return self._objects[key]

    def base_defaults(self, path):
        """A base Material's parameter defaults and blend properties -> {'scalars', 'vectors', 'textures', 'switches',
        'properties' {BlendMode, TwoSided, OpacityMaskClipValue, ShadingModel}, 'fixed' (textures its graph samples
        that are not parameters)}."""
        key = package_of(path)
        if key not in self._defaults:
            pkg, ex, props, end = self._read(path)
            out = {'scalars': {}, 'vectors': {}, 'textures': {}, 'switches': {}, 'fixed': [],
                   'properties': {k: props.get(k, MATERIAL_DEFAULTS[k]) for k in OVERRIDES}}
            at = ex.offset + end
            if at + 8 <= ex.offset + ex.size and struct.unpack_from('<II', pkg.data, at) == (0, 1):
                ced, _ = uprops.read_struct(pkg, self.store.schema, 'MaterialCachedExpressionData', at + 8,
                                            ex.offset + ex.size)
                for t, k, values in PARAMETER_TYPES:
                    names = [p.get('Name') for p in (ced.get('RuntimeEntries[%d]' % t) or {}).get('ParameterInfoSet')
                             or []]
                    vals = ced.get(values) or []
                    for n, v in zip(names, vals):
                        out[k][n] = colour(v) if k == 'vectors' else float(v) if k == 'scalars' else v
                used = set(out['textures'].values())
                out['fixed'] = [x for x in ced.get('ReferencedTextures') or [] if x and x not in used]
            self._defaults[key] = out
        return self._defaults[key]

    def chain(self, path):
        """The instance chain from `path` to its base Material (or as far as it goes)."""
        out, cur = [], path
        while cur and len(out) < MAX_DEPTH:
            m = self.instance(cur)
            out.append(m)
            if m['cls'] != 'MaterialInstanceConstant':
                break
            cur = m['parent']
        return out

    def effective(self, path, colours=None):
        """Parameters in effect for a material: base defaults < instance chain < costume colours (colours: the
        object costume_colours returns). -> {'name', 'base' (base material name), 'chain', 'vectors' {p: {r, g, b,
        a}}, 'scalars', 'textures' {p: object path}, 'switches', 'overrides' (blend properties in effect),
        'fixed'}, in Tekken 7's vocabulary besides: the normal map also under 'Normal', a masked material's cut
        under scalar 'AlphaThreshold' (0..1)."""
        ch = self.chain(path)
        base = ch[-1]
        dfl = self.base_defaults(base['path']) if base['cls'] == 'Material' else \
            {'scalars': {}, 'vectors': {}, 'textures': {}, 'switches': {}, 'fixed': [], 'properties': {}}
        eff = {'name': ch[0]['name'], 'base': base['name'] if base['cls'] == 'Material' else short(base['parent']),
               'chain': [m['name'] for m in ch], 'fixed': list(dfl['fixed'])}
        for k in ('scalars', 'vectors', 'textures', 'switches'):
            eff[k] = dict(dfl[k])
        props = dict(MATERIAL_DEFAULTS)
        props.update(dfl['properties'])
        for m in reversed(ch):
            if m['cls'] == 'MaterialInstanceConstant':
                for k in ('scalars', 'vectors', 'textures', 'switches'):
                    eff[k].update(m[k])
                props.update(m['overrides'])
        eff['overrides'] = props
        params = {}
        if eff['switches'].get('IsFace'):                 # the hair's scalp painting (face skin only)
            params.update((colours or {}).get(SCALP) or {})
        if props['ShadingModel'] == SHADING_SUBSURFACE:   # sheer cloth: the skin under it
            params.update((colours or {}).get(SHEER) or {})
        params.update((colours or {}).get(eff['name']) or {})
        for param, v in params.items():
            if isinstance(v, dict):
                eff['vectors'][param] = dict(v)
            elif isinstance(v, str) or v is None:
                eff['textures'][param] = v
            else:
                eff['scalars'][param] = float(v)
        for n in NORMALS:
            if eff['textures'].get(n):
                eff['textures'].setdefault('Normal', eff['textures'][n])
                break
        if props['BlendMode'] == BLEND_MASKED:
            eff['scalars']['AlphaThreshold'] = float(props['OpacityMaskClipValue'])
        return eff

    # ------------------------------------------------------------------------------------------- costume colours
    def costume_colours(self, costume):
        """The colours object effective() takes: {material name: {parameter: value}} (vectors {r, g, b, a}, scalars,
        texture paths) from a costume: costume.costume()'s dict, a CustomizeSet, ItemPrefab or CustomizeItem path, or
        a list of them (a later one wins); None: {} (the materials' own colours)."""
        if not costume:
            return {}
        if isinstance(costume, dict):
            return costume.get('colours') or {}
        if isinstance(costume, (list, tuple)):
            out = {}
            for c in costume:
                for name, params in self.costume_colours(c).items():
                    out.setdefault(name, {}).update(params)
            return out
        pkg = self.store.package(package_of(costume))
        ex = pkg.main_export()
        props, _ = uprops.read(pkg, ex)
        if ex.class_name == 'CustomizeSet':
            return self.costume_colours([p for p in props.get('ItemPrefabSet') or [] if p] +
                                        [p for p in props.get('ItemPrefabAccSet') or [] if p])
        if ex.class_name == 'ItemPrefab':
            out = self.costume_colours(props.get('CustomizeItemRef'))
            scalp = self.scalp(props.get('BaseItemRef'), out)
            if scalp:
                out[SCALP] = scalp
            return out
        if ex.class_name == 'CustomizeItem':
            return customize_colours(props, self)
        raise InputError('%s is a %s, not a Tekken 8 costume (CustomizeSet, ItemPrefab or CustomizeItem)' % (
            costume, ex.class_name))

    def scalp(self, base_item, colours):
        """The scalp painting a hair BaseItem asks of the face -> {HairScalpMask: its mask, ScalpColor_Hair01: the
        hair's root colour (the costume's, else its material's)}, or {} (an item that is not hair)."""
        if not base_item:
            return {}
        pkg = self.store.package(package_of(base_item))
        props, _ = uprops.read(pkg, pkg.main_export())
        mask = props.get('HairScalpMask')
        if not mask:
            return {}
        out = {HAIR_SCALP_MASK: mask}
        for name, params in colours.items():
            if HAIR_IDS[1] in params:
                out[SCALP_COLOUR] = dict(params[HAIR_IDS[1]])
                break
        return out


def unpainted(colours):
    """Costume colours without the hair's scalp painting: what a face's own colour is measured with for the skin
    gain (skin.gain bakes the reference faces with none, and TTT2's faces have no hair painted on them; the painted
    scalp darkens Reina's face by a third)."""
    return {k: v for k, v in (colours or {}).items() if k != SCALP}


def customize_colours(props, materials=None):
    """A CustomizeItem's properties -> {material name: {'IDnn_Color': {r, g, b, a}, 'IDnn_DontColorOP': 0/1}} (a
    hair material's IDs 1/2 as RootColor/TipColor when `materials` can tell its base)."""
    slots = [(s.get('DesignAssign_Color') or {}) for s in props.get('DesignAssignSlotArray') or []]
    out = {}
    for m in props.get('AssignPerMaterialArray') or []:
        target = m.get('MaterialAssign_Override') or m.get('MaterialAssign_Preview')
        if not target or m.get('isUseSourceMaterial_All'):
            continue
        hair = False
        if materials is not None:
            try:
                hair = materials.effective(target)['base'].startswith('M_Hair')
            except (KeyError, ValueError, zen.ParseError):
                hair = False
        params = {}
        for i, a in enumerate(m.get('DesignAssignArray') or []):
            if not a.get('isEnableId') or a.get('isUseSourceMaterial'):
                continue
            col = a.get('DesignAssign_Color') or {}
            u = a.get('useSlotNumber', -1)
            src = slots[u] if 0 <= u < len(slots) else col
            c = colour(src.get('Assign_Color') or {})
            if hair:
                if i + 1 in HAIR_IDS:
                    params[HAIR_IDS[i + 1]] = c
                continue
            params['ID%02d_Color' % (i + 1)] = c
            params['ID%02d_DontColorOP' % (i + 1)] = float(src.get('Assign_DontColor', 0.0))
        for name in {short(target), short(m.get('MaterialAssign_Preview'))}:
            if name:
                out.setdefault(name, {}).update(params)
    return out
