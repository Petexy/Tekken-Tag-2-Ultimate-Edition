"""A Tekken 7 or Tekken 8 fighter's default costume -> the added fighter's body files: model (.nud), textures (.nut)
and skeleton (.bon). Everything goes into the body files, no costume parts.

1. Tekken 7 side: the costume's skeletal meshes are read from the paks and merged into one skinned mesh with a union
   skeleton. Coordinates go to TTT2's: Y and Z swapped, centimetres -> millimetres, by way of metres in float32 (the
   precision the converted files have always had). Each material's colour is baked into one albedo texture with the
   costume's colours (the formulas of Tekken 7's character shaders, recovered from their compiled pixel shaders).
2. TTT2 side: the donor's skeleton gets the Tekken 7 joint positions (skeleton.py); skin weights go to TTT2 bones
   (four per vertex); triangles become strips; each material is a copy of one of the donor's materials (flags,
   shader properties, texture slots) with new textures: the baked albedo, the normal map, and flat textures of the
   template's own average colour for the other slots.
Textures are at most 512 texels on a side, with at most 3 mip levels (longer chains make the game bind garbage).

A Tekken 8 fighter's side comes from its source (source.py, tekken8/: the same model dict, effective materials and
bakes): its costume's meshes have one level of detail of ~78k vertices, reduced to the budget (decimate.py, the
face's and hair's parts giving up less than the body: PART_WEIGHTS; the body's skin and large pieces keeping a share
of their vertices, its small pieces few: PART_CLASSES; the hair's cards reduced as strands: HAIR_CLASSES; the
skin's folds at elbows, knees, ... kept for
skeleton.bend_poses' test poses; the target from what the 2P colour layers, trimmed to the triangles they draw,
really take: convert decimates a second time when it was far off), and are bound in an A-pose, turned to the
donor's T-pose first (skeleton.repose: skeleton.build keeps the donor's rotations and moves positions only). Its hair
is drawn as TTT2 draws hair: TTT2's hair shader reads the template's second texture (ramps from the cards' roots at
v = 0 along v, the highlights' noise; the same in every TTT2 hair) and Tekken 8 has nothing like it, so the
template's own texture fills that slot, and the hair's cards, which Tekken 8 lays from their tips at v = 0, are
turned over (UVs and texture: tips_first); its narrow cards' texture is halved last when the textures are over
budget. Textures that bake alike are one (Reina's eyebrows and lashes).
"""
import collections
import copy
import hashlib
import re
import time

import numpy as np
from PIL import Image

from .. import source as sources
from ..tekken7 import mesh as t7mesh
from ..tekken7.material import short_ref
from ..tekken7.staticmesh import StaticMesh
from ..tekken7.texture import Texture2D
from ..tekken7.uasset import export_properties, load
from ..ttt2 import bone, nud, nut
from ..ttt2.archive import key_of
from . import chains as hanging, cloth, colours as colours2p, skeleton, skin, strips, summonfade, tiger
from . import weapons as weapons_mod

GIDX_BASE = 0x10408000          # texture ids above every id the game's own textures use (0x10404fac at most)
SLOT_GIDX = 0x1000              # each place's added fighter its own range of texture ids (they meet in fights)
MAX_TEX = 512                   # longest side of a converted texture
MIPS = 3                        # mip levels per texture (the game's own fighter textures have 3 or 1)
# a fighter's texture bytes at most: the game's own fighters have 3.4-4.7 MB (a fight's memory is sized for them;
# 12 MB showed a black model on busy stages); the largest textures are halved (normal maps first) until they fit
TEXTURE_BUDGET = 4 << 20
M_TO_MM = 1000.0


# ------------------------------------------------------------------------------------------------ Tekken 7 side
def _ue_to_ttt2_points(p):
    """UE centimetres (x, y, z) -> (x, z, y) metres in float32 (multiply by M_TO_MM for TTT2)."""
    p = np.asarray(p, np.float32)
    return np.stack([p[..., 0], p[..., 2], p[..., 1]], axis=-1) * 0.01


def _ue_to_ttt2_dirs(d):
    d = np.asarray(d, np.float32)
    return np.stack([d[..., 0], d[..., 2], d[..., 1]], axis=-1)


_SWAP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], np.float64)


def _ue_to_ttt2_matrix(m):
    out = (_SWAP @ m @ _SWAP).copy()
    out[..., :3, 3] *= 0.01
    return out


def merge_skeletons(parts):
    """Union skeleton of several meshes by bone name (names are case-insensitive). parts: [(tag, mesh, weighted
    bone set)] with the owners first (face joints from the face mesh, body joints from the body meshes).

    A part's bone maps to a merged bone of the same name and parent if their bind matrices agree (0.05 cm, 1e-3)
    or if nothing is skinned to it; a weighted bone that disagrees becomes a copy '<name>@<tag>'. Other bones keep
    their part's bind matrix under the (shared) parent. Generic cloth bone names (transform9, Hair_OPT001, ...) are
    reused by different items under different parents, hence the parent test.
    Returns ({'names', 'parents', 'pose' (float32)}, {tag: part bone -> merged bone})."""
    names, parents, poses, by_name, glob = [], [], [], {}, []
    remaps = {}
    for tag, m, weighted in parts:
        sk = m.skeleton
        g = t7mesh.global_matrices(sk['pose'], sk['parents'])
        remap = np.zeros(len(sk['names']), np.int32)
        for i, nm in enumerate(sk['names']):
            par = sk['parents'][i]
            par_new = int(remap[par]) if par >= 0 else -1
            j = by_name.get(nm.lower())
            if j is not None:
                same = (np.abs(glob[j][:3, 3] - g[i][:3, 3]).max() < 0.05 and
                        np.abs(glob[j][:3, :3] - g[i][:3, :3]).max() < 1e-3)
                if parents[j] == par_new and (same or i not in weighted):
                    remap[i] = j
                    continue
                nm = '%s@%s' % (nm, tag)
                pose = t7mesh.matrix_to_pose(np.linalg.inv(glob[par_new]) @ g[i] if par_new >= 0 else g[i])
            elif par_new >= 0:
                pose = t7mesh.matrix_to_pose(np.linalg.inv(glob[par_new]) @ g[i])
            else:
                pose = sk['pose'][i]
            by_name[nm.lower()] = len(names)
            remap[i] = len(names)
            names.append(nm)
            parents.append(par_new)
            poses.append(np.asarray(pose, np.float32))
            gl = t7mesh.local_matrices(np.asarray(pose)[None])[0]
            glob.append(glob[par_new] @ gl if par_new >= 0 else gl)
        remaps[tag] = remap
    return {'names': names, 'parents': parents, 'pose': np.array(poses)}, remaps


def costume_ccis(paks, set_path, follow=True):
    """The CustomizeCharacterItem paths of a costume set: its items and (follow) the items they depend on
    (DependencyItems: worn with them, as Noctis's trousers and boots with his jacket)."""
    cs = export_properties(load(paks, set_path))[0][1] or {}
    out = []
    todo = [short_ref(ref).split('.')[0] for ref in cs.get('CustomCharacterItems', []) if short_ref(ref)]
    while todo:
        path = todo.pop(0)
        if path in out:
            continue
        out.append(path)
        cci = export_properties(load(paks, path))[0][1] or {}
        if follow:
            todo += [short_ref(ref).split('.')[0] for ref in cci.get('DependencyItems') or [] if short_ref(ref)]
    return out


def costume_items(paks, set_path, follow=False):
    """The CharacterItem properties of each item of a costume set (follow: with the items they depend on)."""
    out = []
    for path in costume_ccis(paks, set_path, follow):
        cci = export_properties(load(paks, path))[0][1] or {}
        if short_ref(cci.get('CharacterItem')):
            out.append(export_properties(load(paks, short_ref(cci['CharacterItem']).split('.')[0]))[0][1] or {})
    return out


def dependency_parts(items, parts):
    """[(tag, skeletal mesh)] of the costume's items its definition's parts do not list (items another depends on:
    Noctis's trousers and boots), tagged dep0, dep1, ..."""
    listed = {path.lower() for _, path in parts}
    meshes = [short_ref(ci.get('SourceSkeletalMesh')).split('.')[0] for ci in items
              if ci.get('MeshType') == 'SkeletalMeshAnim' and short_ref(ci.get('SourceSkeletalMesh'))]
    return [('dep%d' % n, path) for n, path in enumerate(m for m in meshes if m.lower() not in listed)]


def dependency_meshes(items):
    """The DependencyMesh of each costume item: the variant of another item's mesh (in that mesh's folder) that
    Tekken 7 draws instead of it while this item is worn, cut to fit under it (Shaheen's hair inside his scarf,
    Josie's under her hair band)."""
    return [short_ref(ci['DependencyMesh']).split('.')[0] for ci in items if short_ref(ci.get('DependencyMesh'))]


def socket_items(items):
    """The costume's static meshes worn on a socket (Leroy's sunglasses): [(static mesh path, ItemOffsets)]. Items
    without a SocketPosition sit on the head: Tekken 7 models them in its body axes about the Head joint (glasses
    without offsets are modelled 12 cm in front of it), the offsets (UE transform: scale, rotation, translation) in
    those axes."""
    return [(short_ref(ci['SourceStaticMesh']).split('.')[0], ci.get('ItemOffsets') or {}) for ci in items
            if ci.get('MeshType') == 'StaticMeshSocket' and short_ref(ci.get('SourceStaticMesh')) and
            ci.get('SocketPosition', 'UNSET_SOCKET') == 'UNSET_SOCKET']


def worn_parts(parts, dependencies):
    """parts [(tag, mesh path)] with each mesh that has a dependency mesh in its folder replaced by it (folders
    compared ignoring case: the game's references and the definitions spell them differently)."""
    by_folder = {p.rsplit('/', 1)[0].lower(): p for p in dependencies}
    return [(tag, by_folder.get(path.rsplit('/', 1)[0].lower(), path)) for tag, path in parts]


def in_front(points, cover, cell=2.0, margin=2.0):
    """Which points (n, 3) lie in front of (+z, the fighter's front) the front surface of the triangles cover (m, 3, 3),
    or less than margin behind it, where it is seen from the front: its largest z on a grid of cell mm squares."""
    lo = cover[..., :2].reshape(-1, 2).min(0)
    size = np.ceil((cover[..., :2].reshape(-1, 2).max(0) - lo) / cell).astype(int) + 1
    front = np.full(size, -np.inf)
    for t in cover:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-9:                            # seen edge-on
            continue
        i0, j0 = np.floor((t[:, :2].min(0) - lo) / cell).astype(int)
        i1, j1 = np.floor((t[:, :2].max(0) - lo) / cell).astype(int) + 1
        x, y = np.meshgrid(lo[0] + (np.arange(i0, i1) + 0.5) * cell, lo[1] + (np.arange(j0, j1) + 0.5) * cell,
                           indexing='ij')
        l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
        l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
        l3 = 1 - l1 - l2
        z = np.where((l1 >= 0) & (l2 >= 0) & (l3 >= 0), l1 * az + l2 * bz + l3 * cz, -np.inf)
        front[i0:i1, j0:j1] = np.maximum(front[i0:i1, j0:j1], z)
    ij = np.floor((points[:, :2] - lo) / cell).astype(int)
    inside = ((ij >= 0) & (ij < size)).all(1)
    z = np.full(len(points), -np.inf)
    z[inside] = front[ij[inside, 0], ij[inside, 1]]
    return np.isfinite(z) & (points[:, 2] > z - margin)


def load_tekken7_model(paks, parts, merge_order):
    """The costume's meshes as one skinned mesh in TTT2 space.
    parts: [(tag, skeletal mesh path)] in mesh order; merge_order: the tags in skeleton-merge order.
    Returns {'bones': {'names', 'parents', 'world' (n, 4, 4) bind matrices, mm}, 'prims': [{'part', 'material',
    'pos' (mm), 'nrm', 'tan', 'uv', 'joints' (n, 8), 'weights' (n, 8), 'tris'}] (prims share the vertex arrays),
    'parts': {tag: {'names', 'parents', 'remap' (part bone -> merged bone), 'mesh' (its SkeletalMesh), 'first' (its
    first vertex in the streams)}}}."""
    loaded = []
    for tag, path in parts:
        m = t7mesh.SkeletalMesh(load(paks, path))
        m.skeleton['names'] = [skeleton.canonical(n) for n in m.skeleton['names']]
        loaded.append((tag, m, m.geometry(0)))
    by_tag = {tag: (m, geo) for tag, m, geo in loaded}
    merged, remaps = merge_skeletons(
        [(t, by_tag[t][0], set(np.unique(by_tag[t][1]['joints'][by_tag[t][1]['weights'] > 0]).tolist()))
         for t in merge_order])
    pos, nrm, tan, uvs, jnt, wts, sections = [], [], [], [], [], [], []
    base, first = 0, {}
    for tag, m, geo in loaded:
        n = len(geo['positions'])
        first[tag] = base
        pos.append(geo['positions'])
        nrm.append(geo['normals'])
        tan.append(geo['tangents'])
        uvs.append(geo['uvs'][:, 0])
        j, w = remaps[tag][geo['joints']], geo['weights']
        if w.shape[1] == 4:
            j = np.concatenate([j, np.zeros_like(j)], 1)
            w = np.concatenate([w, np.zeros_like(w)], 1)
        jnt.append(j)
        wts.append(w)
        for si, s in enumerate(m.lods[0].sections):
            if s.cloth_mapping:                  # the cloth simulation's copy of a disabled section
                continue
            ref = m.materials[s.material_index]['material']
            sections.append((tag, short_ref(ref).split('.')[-1] if ref else 'None', geo['triangles'][si] + base))
        base += n
    # the precision of the vertex streams: float32 metres, normalised float32 weights
    p = _ue_to_ttt2_points(np.concatenate(pos)).astype(np.float64) * M_TO_MM
    nr = _ue_to_ttt2_dirs(np.concatenate(nrm)).astype(np.float32).astype(np.float64)
    tg = np.concatenate(tan).astype(np.float32).copy()
    tg[:, :3] = _ue_to_ttt2_dirs(tg[:, :3])
    tg[:, 3] = -tg[:, 3]                         # the axis swap is a reflection: the bitangent sign flips
    uv = np.concatenate(uvs).astype(np.float32).astype(np.float64)
    weights = np.concatenate(wts).astype(np.float32)
    weights = weights / np.maximum(weights.sum(1, keepdims=True), 1e-8)
    joints = np.where(weights > 0, np.concatenate(jnt), 0).astype(np.uint16).astype(np.int64)
    streams = dict(pos=p, nrm=nr, tan=tg.astype(np.float64), uv=uv, joints=joints, weights=weights.astype(np.float64))
    prims = [dict(part=tag, material=mat, tris=tri.astype(np.uint32)[:, [0, 2, 1]].astype(np.int64), **streams)
             for tag, mat, tri in sections]
    # bind matrices: the inverse bind matrices are kept in float32
    g = t7mesh.global_matrices(merged['pose'], merged['parents'])
    ibm = np.linalg.inv(_ue_to_ttt2_matrix(g)).astype(np.float32)
    world = np.linalg.inv(ibm.astype(np.float64))
    world[:, :3, 3] *= M_TO_MM
    skeletons = {tag: dict(names=m.skeleton['names'], parents=m.skeleton['parents'], remap=remaps[tag],
                           mesh=m, first=first[tag])
                 for tag, m, _ in loaded}
    return {'bones': dict(names=merged['names'], parents=merged['parents'], world=world), 'prims': prims,
            'parts': skeletons}


def load_socket_item(paks, model, tag, path, offsets):
    """A static mesh worn on the head (socket_items) as prims of the model, rigid on its Head joint: placed by the
    item's offsets in Tekken 7's body axes about the joint, scaled with it (its bind scale, 0.98 for Leroy)."""
    sm = StaticMesh(load(paks, path))
    names = model['bones']['names']
    head = names.index('Head')
    world = model['bones']['world'][head]
    scale = float(np.linalg.norm(world[:3, 0]))
    pose = np.array([list(offsets.get('Rotation', (0, 0, 0, 1))) + list(offsets.get('Translation', (0, 0, 0))) +
                     list(offsets.get('Scale3D', (1, 1, 1)))], np.float64)
    m = t7mesh.local_matrices(pose)[0]
    lin = m[:3, :3]
    p = sm.positions.astype(np.float64) @ lin.T + m[:3, 3]           # UE centimetres about the joint
    pos = world[:3, 3] + scale * _ue_to_ttt2_points(p).astype(np.float64) * M_TO_MM
    nrm = _ue_to_ttt2_dirs(sm.normals.astype(np.float64) @ np.linalg.inv(lin))      # (inverse transpose)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    tan = np.concatenate([_ue_to_ttt2_dirs(sm.tangents[:, :3].astype(np.float64) @ lin.T),
                          -sm.tangents[:, 3:].astype(np.float64)], 1)  # (the axis swap flips the bitangent sign)
    tan[:, :3] /= np.maximum(np.linalg.norm(tan[:, :3], axis=1, keepdims=True), 1e-9)
    n = len(pos)
    joints = np.zeros((n, 8), np.int64)
    joints[:, 0] = head
    weights = np.zeros((n, 8))
    weights[:, 0] = 1.0
    streams = dict(pos=pos, nrm=nrm, tan=tan, uv=sm.uvs[:, 0].astype(np.float64), joints=joints, weights=weights)
    return [dict(part=tag, material=short_ref(sm.materials[slot]).split('.')[-1] if sm.materials[slot] else 'None',
                 tris=tri.astype(np.int64)[:, [0, 2, 1]], **streams) for slot, tri in sm.triangles() if len(tri)]


# ------------------------------------------------------------------------------------------------ albedo baking
MASK_MATERIALS = ('M_CH_Aniso', 'M_CH_aniso', 'M_CH_Base', 'M_CH_Base_mask', 'M_CH_Aniso_machieru',
                  'M_CH_Base_machieru')


def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


class Textures:
    """Tekken 7 textures by object path, decoded once."""

    def __init__(self, paks):
        self.paks = paks
        self._cache = {}

    def exists(self, path):
        return bool(path) and self.paks.find(path) is not None

    def get(self, path):
        """-> (RGBA uint8 array, sRGB flag)"""
        if path not in self._cache:
            t = Texture2D(load(self.paks, path))
            self._cache[path] = (t.decode(), t.srgb)
        return self._cache[path]

    def linear(self, path):
        """-> (linear RGB float32, alpha float32)"""
        img, srgb = self.get(path)
        a = img.astype(np.float32) / 255.0
        return (srgb_to_linear(a[..., :3]) if srgb else a[..., :3]), a[..., 3]


def _col(v):
    return np.array([v['r'], v['g'], v['b']], np.float32)


def _resize_to(a, shape):
    if a.shape[:2] == shape:
        return a
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32)).resize((shape[1], shape[0]), Image.BILINEAR))
    return np.stack([_resize_to(a[..., c], shape) for c in range(a.shape[-1])], -1)


def bake_albedo(eff, textures, grey=False):
    """Linear albedo (H, W, 3) and alpha (H, W) of a material instance with its parameters in effect, or (None,
    None) without a colour texture.

    Colour-customisable materials (MF_CH_ColorCustomize):
        C = lerp(lerp(lerp(Color02, Color01, M.r), Color03, M.g), Color04, M.b)    (M = mask texture)
        k = max(1, 1 + 20 (max(M.r, M.g, M.b) - 0.9))
        albedo = D (1 - M.a) + k D C M.a          (the pattern layer is empty in default costumes)
      The *_machieru ones also multiply by Multiply * lerp(DetalDiffuse(uv * Detail_Normal_Scale), 1,
      detail_diffuse_pow).
    Hair (pass 1): lo = sat(BaseLowerContrast); s = (min(Up, 0) + min(Lo, 0) + 1) / (1 - (sat(Up) + sat(Lo)));
        albedo = sat((T - lo) s - min(Lo, 0)) * Color01; Noctis's (HairTipsAdd, a fixed gradient texture G):
        albedo = sat(T + HairTipsAdd G) * Color01.
    Skin: lerp(D, luma(D), Desaturation) * Multiply (the view-dependent terms left out).
    Anything else: its colour texture as it is.
    grey: a colour-customisable material's colour texture taken by its brightness alone (D's luma), its colours giving
    the hue (a definition's GREY: Noctis's outfit, blue-grey in Tekken 7 where its textures are mauve)."""
    base = eff['base']
    t, v, s = eff['textures'], eff['vectors'], eff['scalars']
    masked = base in MASK_MATERIALS or (not base.startswith('M_CH_AnisoHair') and t.get('DiffuseMap')
                                        and t.get('MaskMap') and 'Color01' in v and 'Color02' in v)
    if masked:                               # (M_CH_Aniso_mask, M_CH_Base_machieru_mask and the like too)
        D, Da = textures.linear(t['DiffuseMap'])
        if grey:
            D = np.repeat((D * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True), 3, -1)
        M, Ma = textures.linear(t['MaskMap'])
        M, Ma = _resize_to(M, D.shape[:2]), _resize_to(Ma, D.shape[:2])
        C = _col(v['Color02'])[None, None] + M[..., 0:1] * (_col(v['Color01']) - _col(v['Color02']))
        C = C + M[..., 1:2] * (_col(v['Color03']) - C)
        C = C + M[..., 2:3] * (_col(v['Color04']) - C)
        k = np.maximum(1.0, 1.0 + 20.0 * (M.max(-1, keepdims=True) - 0.9))
        out = D * (1 - Ma[..., None]) + k * D * C * Ma[..., None]
        if 'machieru' in base and t.get('DetalDiffuse'):
            det, _ = textures.linear(t['DetalDiffuse'])
            scale = s.get('Detail_Normal_Scale', 1.0)
            h, w = D.shape[:2]
            yy = ((np.arange(h) + 0.5) / h * scale * det.shape[0]).astype(np.int64) % det.shape[0]
            xx = ((np.arange(w) + 0.5) / w * scale * det.shape[1]).astype(np.int64) % det.shape[1]
            dt = det[yy][:, xx]
            p = s.get('detail_diffuse_pow', 0.0)
            out = out * s.get('Multiply', 1.0) * (dt + p * (1 - dt))
        return np.clip(out, 0, 1), Da
    if base.startswith('M_CH_AnisoHair'):
        T, Ta = textures.linear(t['ColorTexture'])
        lo_, up_ = s.get('BaseLowerContrast', 0.0), s.get('BaseUpperContrast', 0.0)
        lo = np.clip(lo_, 0, 1)
        sc = (min(up_, 0) + min(lo_, 0) + 1) / (1 - (np.clip(up_, 0, 1) + np.clip(lo_, 0, 1)))
        T = np.clip((T - lo) * sc - min(lo_, 0), 0, 1)
        tips = [x for x in eff.get('fixed', []) if textures.exists(x)]
        if s.get('HairTipsAdd') and tips:        # lighter tips: a gradient along the strands (Noctis's hair shader)
            G, _ = textures.linear(tips[0])
            T = np.clip(T + s['HairTipsAdd'] * _resize_to(G, T.shape[:2]), 0, 1)
        return T * _col(v['Color01']), Ta
    if base == 'M_CH_skin_wet_SSP':
        D, Da = textures.linear(t['Diffuse'])
        luma = (D * np.array([0.3, 0.59, 0.11], np.float32)).sum(-1, keepdims=True)
        out = (D + s.get('Desaturation', 0.0) * (luma - D)) * s.get('Multiply', 1.0)
        return np.clip(out, 0, 1), Da
    for slot in ('DiffuseMap', 'Diffuse', 'Diffuse_Map', 'Color', 'ColorTexture'):    # (Diffuse_Map: M_CH_Prop's)
        if textures.exists(t.get(slot)):
            return textures.linear(t[slot])
    for name in sorted(v):                       # no texture but a glow: its colour (Akuma's eyes)
        if 'emissive' in name.lower():
            return np.clip(np.full((32, 32, 3), _col(v[name]), np.float32), 0, 1), None
    return None, None


def albedo_image(rgb, alpha):
    """The baked albedo as an 8-bit sRGB image (RGBA only where some texel is not opaque)."""
    a = (linear_to_srgb(rgb) * 255 + 0.5).astype(np.uint8)
    if alpha is not None and (alpha < 1).any():
        a = np.concatenate([a, (np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8)[..., None]], -1)
    return Image.fromarray(a)


# ------------------------------------------------------------------------------------------------ TTT2 side
def pow2_size(w, h, cap=MAX_TEX):
    def p2(x):
        return 1 << max(2, int(round(np.log2(max(4, x)))))
    s = min(1.0, cap / max(w, h))
    return min(cap, p2(w * s)), min(cap, p2(h * s))


class TextureBank:
    """The new textures, numbered from `first` in the order they are made; identical requests share one."""

    def __init__(self, first=GIDX_BASE):
        self.first, self.textures, self.by_key = first, [], {}
        self.sources, self.normals = [], set()          # each texture's image; the normal maps' indices
        self.kept = set()                               # the indices of textures fit() halves after all others
        self.solid = {}                                 # index -> make_texture's solid (image(): bright hair)

    def add(self, key, rgba, fmt, solid=None):
        if key not in self.by_key:
            self.by_key[key] = self.first + len(self.textures)
            if key[0] == 'nrm':
                self.normals.add(len(self.textures))
            if solid is not None:
                self.solid[len(self.textures)] = solid
            self.sources.append(np.asarray(rgba, np.uint8))
            self.textures.append(nut.make_texture(rgba, self.by_key[key], fmt, mips=MIPS, solid=solid))
        return self.by_key[key]

    def keep(self, ids):
        """Keeps only the textures `ids` (numbered again from `first`, in their order) -> {old id: new id}."""
        order = sorted(set(ids))
        new = {old: self.first + i for i, old in enumerate(order)}
        at = [old - self.first for old in order]
        self.textures = [dict(self.textures[i], gidx=new[old]) for i, old in zip(at, order)]
        self.sources = [self.sources[i] for i in at]
        self.normals = {j for j, i in enumerate(at) if i in self.normals}
        self.kept = {j for j, i in enumerate(at) if i in self.kept}
        self.solid = {j: self.solid[i] for j, i in enumerate(at) if i in self.solid}
        self.by_key = {key: new[v] for key, v in self.by_key.items() if v in new}
        return new

    def fit(self, budget, dry=False):
        """Halves the largest textures (a normal map before an image of its size; the kept ones last) until all fit in
        `budget` bytes -> how many were halved; dry: none, only {index: how many times fit would halve it} (each
        halving takes a quarter of a texture's bytes: its smallest mip level is 16 texels or more)."""
        sizes = {i: sum(len(m) for m in t['mips']) for i, t in enumerate(self.textures)}
        sides = {i: (t['w'], t['h']) for i, t in enumerate(self.textures)}
        total, halved, times = sum(sizes.values()), 0, collections.Counter()
        while total > budget:
            big = [i for i in sides if min(sides[i]) > 64]
            if not big:
                break
            i = max(big, key=lambda i: (i not in self.kept, sizes[i] * (2 if i in self.normals else 1), i))
            before = sizes[i]
            if dry:
                sizes[i] = before // 4
            else:
                t = self.textures[i]
                self.sources[i] = self.halved(i, 1)
                self.textures[i] = dict(nut.make_texture(self.sources[i], t['gidx'], t['fmt'], mips=len(t['mips']),
                                                         solid=self.solid.get(i)),
                                        **{k: v for k, v in t.items() if k not in ('fmt', 'w', 'h', 'mips', 'gidx')})
                sizes[i] = sum(len(m) for m in self.textures[i]['mips'])
            sides[i] = (sides[i][0] // 2, sides[i][1] // 2)
            total += sizes[i] - before
            halved += 1
            times[i] += 1
        return dict(times) if dry else halved

    def halved(self, i, times):
        """Texture i's image (h, w, 4) halved `times` times as fit() halves it (each texel the mean of four)."""
        out = self.sources[i]
        for _ in range(times):
            h, w = out.shape[:2]
            out = (out.reshape(h // 2, 2, w // 2, 2, 4).astype(np.float32).mean((1, 3)) + 0.5).astype(np.uint8)
        return out

    def constant(self, rgba, fmt, size=32):
        img = np.zeros((size, size, 4), np.uint8)
        img[:] = rgba
        return self.add(('const', tuple(int(x) for x in rgba), fmt), img, fmt)

    def image(self, key, im, fmt, alpha, solid=None):
        """solid: the alpha test's reference of an image with its colours filled in under its alpha (bright hair: bake.
        fill_under): colour and alpha resized apart (an RGBA resize weighs colours by alpha: black where it is 0), its
        mips kept opaque (nut.make_texture)."""
        if ('img', key, fmt, alpha) in self.by_key:
            return self.by_key[('img', key, fmt, alpha)]
        im = im.convert('RGBA')
        if solid is None:
            a = np.array(im.resize(pow2_size(*im.size), Image.LANCZOS))
        else:
            a = np.array(Image.merge('RGBA', [c.resize(pow2_size(*im.size), Image.LANCZOS) for c in im.split()]))
        if not alpha:
            a[..., 3] = 255
        return self.add(('img', key, fmt, alpha), a, fmt, solid=solid)

    def normal(self, key, im):
        """A Tekken 7 normal map (R = X, G = Y towards +v) -> TTT2's BC3 layout (A = X, G = Y towards -v)."""
        if ('nrm', key) in self.by_key:
            return self.by_key[('nrm', key)]
        im = im.convert('RGB')
        w, h = pow2_size(*im.size)
        a = np.array(im.resize((w, h), Image.LANCZOS))
        out = np.zeros((h, w, 4), np.uint8)
        out[..., 3] = a[..., 0]
        out[..., 1] = 255 - a[..., 1]
        return self.add(('nrm', key), out, 2)


def find_mesh(model, name):
    for m in model['meshes']:
        if m['name'] == name:
            return m
    raise ValueError('the donor model has no mesh %s' % name)


def load_templates(archives, templates, texture_sources):
    """Material templates from the donor's files. templates: {kind: (entry name or key, mesh name, polygon)};
    texture_sources: NUTs (names or keys) holding the templates' textures (a later one wins).
    -> {kind: (material, vertex type, slots [{'fmt', 'mean' RGBA or None, 'texture' (its NUT texture) or None}])}"""
    def read(ref):
        return archives.read(key_of(ref) if isinstance(ref, str) else ref)
    found = {}
    for src in texture_sources:
        for t in nut.read(read(src))['textures']:
            found[t['gidx']] = t
    models, out = {}, {}
    for kind, (src, mesh_name, poly_index) in templates.items():
        if src not in models:
            models[src] = nud.read(read(src))
        poly = find_mesh(models[src], mesh_name)['polys'][poly_index]
        slots = []
        for t in poly['materials'][0]['textures']:
            tex = found.get(t['id'])
            mean = nut.decode(tex).reshape(-1, 4).mean(0).round().astype(int) if tex is not None else None
            slots.append(dict(fmt=tex['fmt'] if tex is not None else 0, mean=mean, texture=tex))
        out[kind] = (copy.deepcopy(poly['materials'][0]), poly['vtype'], slots)
    return out


# draw order in a mesh ('glow_add': a summon added to the picture, 'glow_blend': one blended over it, 'glow_cut': an
# unlit alpha-tested one, a lace model's pictures: lace8.py)
ORDER = {'mouth': 0, 'skin': 0, 'cloth': 0, 'glow': 0, 'glow_cut': 0, 'colour': 0.5, 'eye': 1, 'hair': 2,
         'overlay': 3, 'lens': 3, 'glow_add': 3, 'glow_blend': 3}
WRAP_REPEAT = 1                 # a NUD texture's wrap mode that repeats (the templates' 3 clamps)
HOLES = 0.02                    # cloth whose colour texture is transparent over more than this share has holes (lace)


def normal_slot(slot, strict=True):
    """Whether a template's texture slot (load_templates) holds a normal map (TTT2's BC3 layout: R = 0, G = Y, B = 0,
    A = X): its mean near a flat normal's; strict = False: any BC3 texture with R and B empty (Jun's jacket's normal
    map, the cloth template's, averages G 117: the strict test leaves the cloth without its own normal map, a flat
    constant in its place; Tekken 8 fighters take the loose one)."""
    m = slot['mean']
    if m is None:
        return False
    if strict:
        return abs(m[1] - 128) < 8 and abs(m[3] - 128) < 8
    return slot['fmt'] == 2 and m[0] < 8 and m[2] < 8 and abs(m[1] - 128) < 32 and abs(m[3] - 128) < 32


def tips_first(prim):
    """Whether a hair's cards run from their tips at v = 0 to their roots (v rising with the vertices' height), as
    Tekken 8's do; TTT2's hair runs from its roots at v = 0 (its hair shader's second texture ramps down v)."""
    used = np.unique(prim['tris'])
    v, y = prim['uv'][used, 1], prim['pos'][used, 1]
    return bool(v.std() > 0 and y.std() > 0 and np.corrcoef(v, y)[0, 1] > 0)


def classify(name, base, alpha):
    """What a Tekken 7 material becomes when the definition's MATERIALS does not say: (template kind, normal map?,
    alpha-tested?) or None (left out), from its parent material `base` and its name; alpha: its colour texture's
    alpha (None: opaque)."""
    n = name.lower()
    if base in ('M_CH_Eye_ADD', 'M_CH_tear') or 'tear' in n.split('_') or n.endswith('_add'):
        return None                                   # reflections and wet layers over the eyes
    if base == 'M_CH_Eye_IN' or n.endswith(('_eyes', '_eye')) or '_eyes_' in n:
        return ('eye', False, False)
    if 'teeth' in n:
        return ('mouth', False, False)
    if 'mouth' in n or 'tongue' in n:
        return ('mouth', True, False)
    if base == 'M_CH_skin_wet_SSP' or '_skin_' in n:
        return ('skin', True, False)
    if base in ('M_CH_trans', 'M_CH_simple_trans', 'M_CH_lip'):
        return ('overlay', False, True)                # eyebrows, lashes, shadow, lips: blended over the face
    if base.startswith('M_CH_AnisoHair'):
        return ('hair', False, True)
    holes = alpha is not None and float((alpha < 0.5).mean()) > HOLES
    return ('cloth', True, holes)
VERTEX_BUDGET = 42000           # vertices of a fighter's model the game skins: each frame it streams the skinned
                                # vertices of the fighters on screen (and some stages' animals) into a stream-out
                                # buffer, 80 bytes each, and in a match's first frame those of all four (the port
                                # makes the buffers 28 MiB: roster.cpp; its own fighters have 20-34k): over it, 2P
                                # colour layers are left out, the largest first (a definition's VERTEX_BUDGET: its
                                # own, Noctis's with his weapons; its DECIMATE: a Tekken 7 model decimated to fit)
LAYER_OFFSET = 1.0              # mm: how far the 2P colour layer sits outside the polygon it covers (less flickers:
                                # the depth buffer cannot tell them apart at fighting distance)
# a Tekken 8 part's share of the vertices it gives up to the budget against the body's 1 (decimate.decimate's
# part_weights; by the tag's first three letters, a definition's TEKKEN8['part_weights'] first): the face's eyes,
# lips and nose keep their shapes at 0.3, the hair's cards their strands at 0.7 (Reina 77.8k -> 26.9k: body 10.4k,
# face 8.2k, hair 8.3k), a beard's its few at 0.2 (Victor's 4.3k cards as a body part: 2k with holes)
PART_WEIGHTS = {'fac': 0.3, 'har': 0.7, 'fah': 0.2}
# the classes of a Tekken 8 costume's other parts (not the face, the hair or the weapons: decimate.decimate's
# classes; a definition's TEKKEN8['part_classes'] over them): each skin material keeps at least 0.4 of its vertices
# and each large piece (a bikini top, a sarong, a jacket) 0.25 while anything else can give, each small piece (a
# bead, a stud, a buckle) 6 + 0.5 per mm of its length. Without them the errors took the smooth skin first (the
# cheapest to take) and the small pieces' locks held: Miary Zo's skin 10.5k -> 680 vertices (a see-through chest,
# faceted limbs); Reina's hands 2406 -> 267. A point of a piece lying on the skin or another piece moves by at most
# 'lying' times its height over it (her straps under the bust and the band's lower edge had sunk into the skin,
# hidden) and any point of a piece not small by 'reach' mm, of the skin by 'skin_reach' mm (a floor says how many
# vertices, not where: her bikini top's bounded points had taken its floor and its cups flattened by 14 mm). The face
# and the hair pay for what the body needs past its floors: Reina's and Azucena's keep what they had at these; a
# definition whose costume is most of what is seen can hold it closer (Miary Zo's 'reach'), or reduce its wires as
# whole rings ('tubes': decimate.py's Wires; Miary Zo's necklace)
PART_CLASSES = {'skin': 0.4, 'big': 0.25, 'small': 0.5, 'lying': 1.0, 'reach': 4.0, 'skin_reach': 1.0}
# the classes of a Tekken 8 costume's hair (decimate.decimate's; a definition's TEKKEN8['hair_classes'] over them): its
# cards' strips are reduced as strands (decimate.py's Hair strands), their rows within 5 mm of the bends (centre
# parting, curved fringe, crown) while anything else can give. Collapsed like any surface, Miary Zo's 440 strips
# kept 3..23 vertices each (her 38996 -> 5099, 2060 of them tufts hidden at the back): straight planks from root to
# tip, a fringe lock over her right eye, chords through the skull (the scalp showing at the crown)
HAIR_CLASSES = {'strands': 5.0}
HAIR_SOLID_REF = 85             # bright hair's alpha test reference when its material names none (Tekken 8's 1/3)


def clear_of_dissolve(ref):
    """An alpha test reference the converter writes, kept off a dissolving material's (lace8.DISSOLVE_REF, which the
    runtime raises while that summon fades: title/summon_fade.h): a step under it (Tekken 7's 0.42 -> 107)."""
    from . import lace8
    return ref - 1 if ref == lace8.DISSOLVE_REF else ref
LAYER_MARGIN = 2                # texels round the texels a 2P colour layer draws (its alpha test) whose triangles it
                                # keeps: its next mip level reaches so far (at fighting distance a texel is about a
                                # pixel at 1440p, 2 at 720p; a level further down only a thin rim could differ)
LAYER_SLACK = 200               # vertices: a Tekken 8 model this far under the budget or over it (its layers trimmed:
                                # convert) is decimated again to fit it


def weapon_parts(weapons):
    """[(tag, mesh path)] of a Tekken 8 fighter's weapon meshes (its WEAPONS' 'mesh', each once, in order): parts
    'wpn0', 'wpn1', ... of its model (tekken8_model), re-posed and decimated with the costume."""
    out = []
    for w in weapons:
        if w.get('mesh') and w['mesh'] not in [p for _, p in out]:
            out.append(('wpn%d' % len(out), w['mesh']))
    return out


def tekken8_model(source, d, donor, log=print, weapons=(), cache=None, fill=None):
    """A Tekken 8 fighter's costume (d.TEKKEN8: its 'costume' and 'costume_2p', tekken8.costume's names, or 'parts'
    and 'merge_order') as the model dict (load_tekken7_model's shape), with its weapons' meshes (weapon_parts),
    reduced to the vertex budget (leaving room for the 2P colour layers: decimate.vertex_target) and posed like the
    donor's skeleton (skeleton.repose) -> (model, parts [(tag, mesh path)], player 1's colours, player 2's or None).
    cache: a dict keeping the model as loaded for a second call (convert's), with `fill` (_fill_target)."""
    from . import decimate
    if cache is not None and 'tekken8' in cache:
        k, parts, colours, colours_2p, weights, target, poses, source_index = cache['tekken8']
        return _tekken8_decimated(k, d, donor, log, weights, target, poses, source_index, fill), parts, \
            colours, colours_2p
    spec = d.TEKKEN8
    worn = {}
    if spec.get('parts'):
        parts, merge_order = list(spec['parts']), list(spec.get('merge_order') or [t for t, _ in spec['parts']])
        colours = source.costume(d, spec['costume'])['colours'] if spec.get('costume') else None
    else:
        costume = source.costume(d, spec.get('costume', '1p'))
        parts, merge_order, colours = list(costume['parts']), list(costume['merge_order']), costume['colours']
        for tag, path in costume.get('static') or []:
            if tag in d.MESHES:
                worn[tag] = costume['scales'][tag]
                parts.append((tag, path))
                merge_order.append(tag)
            else:
                log('  %s (%s): a rigid item of the costume, left out (the definition\'s MESHES do not name it)' % (
                    path.split('/')[-1], tag))
    colours_2p = source.costume(d, spec['costume_2p'])['colours'] if spec.get('costume_2p') else None
    armed = weapon_parts(weapons)                # (bound to other rigs: re-bound to the costume's as its parts)
    twice = {tag for tag, path in parts if any(path.lower() == p.lower() for _, p in armed)}
    parts = [p for p in parts if p[0] not in twice]      # (a costume part that is a weapons' mesh: Victor's ex0)
    merge_order = [tag for tag in merge_order if tag not in twice]
    parts, merge_order = parts + armed, merge_order + [tag for tag, _ in armed]
    k = source.load_model(parts, merge_order, log=log, worn=worn)
    # the materials the definition leaves out (MATERIALS None: the tear lines, the eyes' shadow shells) go before
    # decimating: model.py drops them, and the vertices the decimation left them were lost (Miary Zo's 210)
    left = {name for name, kind in getattr(d, 'MATERIALS', {}).items() if kind is None}
    if any(p['material'] in left for p in k['prims']):
        k = dict(k, prims=[p for p in k['prims'] if p['material'] not in left])
    log('  Tekken 8 model: %d bones, %d sections, %d vertices (%s)' % (
        len(k['bones']['names']), len(k['prims']), decimate.count(k),
        ', '.join('%s %d' % (tag, decimate.count({'prims': [p for p in k['prims'] if p['part'] == tag]}))
                  for tag, _ in parts)))
    own = spec.get('part_weights', {})
    weights = {tag: own.get(tag, PART_WEIGHTS.get(tag[:3], 1.0)) for tag, _ in parts}
    budget = getattr(d, 'VERTEX_BUDGET', VERTEX_BUDGET)
    from . import snakes8                        # (her snakes' meshes come after: convert/snakes8.py)
    budget -= snakes8.vertices(d)
    from . import prefabs8                       # (its summoned creatures' meshes: convert/prefabs8.py)
    budget -= prefabs8.vertices(d)
    target = decimate.vertex_target(k, budget=budget)
    log('  vertex target %d (the budget %d less room for 2P colour layers; part weights %s)' % (
        target, budget, ', '.join('%s %.1f' % (tag, weights[tag]) for tag, _ in parts)))
    # a small part the passes would leave a sliver of (each pass takes up to decimate.MOST_REMOVED of every part not
    # yet stuck, whatever its weight: Miary Zo's horn, 2213 -> 75): decimated alone to its TEKKEN8['part_vertices']
    # count first, then kept as it is (the vertices it keeps over the sliver come from the parts still free in the
    # last passes: her face)
    # bent test poses (elbows, knees, ... turned: skeleton.bend_poses): the decimator keeps the vertices where the
    # skin folds when they bend (without them a bent elbow or knee is a flat plank from the shoulder or hip)
    poses = skeleton.bend_poses(k['bones'])
    sources_of = source
    source = None
    for tag, n in sorted((spec.get('part_vertices') or {}).items()):
        if tag not in weights:
            continue
        for _ in range(4):                       # (a first pass also welds the other parts' equal wedges, which
            size = decimate.count({'prims': [p for p in k['prims'] if p['part'] == tag]})   # count to its target)
            if size <= n:
                break
            k = decimate.decimate(k, decimate.count(k) - (size - int(n)),
                                  {t: 1.0 if t == tag else 0.0 for t in weights}, log=log, poses=poses)
            source = k['source'] if source is None else source[k['source']]
        weights[tag] = 0.0
    if spec.get('covered'):                      # (the surfaces under a costume's own plates: covered.py)
        from . import covered
        paths_, materials_, textures_ = sources_of.material_paths(parts), sources_of.materials(), sources_of.textures()

        def luma(name):
            rgb, _ = sources_of.bake_albedo(materials_.effective(paths_[name], colours), textures_)
            return linear_to_srgb(np.clip(rgb, 0, 1)) @ np.array((0.3, 0.6, 0.1), np.float32)
        k, shown = covered.mark(k, spec['covered'], poses, luma, log=log)
        if cache is not None:
            cache['shown'] = shown
    if spec.get('skin_occlusion') and cache is not None:     # (skin the costume shades: occlusion.py)
        from . import occlusion
        cache['occlusion'] = occlusion.mark(k, spec['skin_occlusion'], log=log)
    if cache is not None:
        cache['tekken8'] = (k, parts, colours, colours_2p, weights, target, poses, source)
    return _tekken8_decimated(k, d, donor, log, weights, target, poses, source), parts, colours, colours_2p


def _counts(k):
    """The vertices of each material of model dict k (decimate.count's)."""
    out = collections.Counter()
    for p in k['prims']:
        out[p['material']] += len(np.unique(p['tris']))
    return out


def _fill_target(decimated, target, fill, log):
    """convert's second try: the decimation of target `target` (decimated(target) -> model dict) whose model with its
    2P colour layers comes within LAYER_SLACK / 2 of fill['budget'], by the last try's measures (fill: its 'target',
    'total' (vertices in the end), 'counts' (_counts of its decimated model) and 'layers' (each layered material's
    trimmed layer vertices)): a material's layer takes the share of its vertices it took then -> the model dict
    (fill['used']: the target it was decimated to)."""
    share = {m: n / float(max(fill['counts'].get(m, 0), 1)) for m, n in fill['layers'].items()}

    def total(k):                                # (what the model would end with)
        now = _counts(k)
        return fill['total'] + sum((now[m] - fill['counts'].get(m, 0)) * (1.0 + share.get(m, 0.0))
                                   for m in set(now) | set(fill['counts']))
    goal = fill['budget'] - LAYER_SLACK // 2
    seen = [(fill['target'], fill['total'])]
    for _ in range(3):
        k = decimated(target)
        fill['used'] = target
        got = total(k)
        log('  vertex target %d: the model ends with about %d vertices of the budget %d (the 2P colour layers '
            'trimmed)' % (target, got, fill['budget']))
        if abs(got - goal) <= LAYER_SLACK // 2:
            break
        (t0, n0), seen = seen[-1], seen + [(target, got)]
        slope = (got - n0) / float(target - t0) if target != t0 else 1.0
        target = int(round(target + (goal - got) / min(max(slope, 1.0), 2.0)))
    return k


def _tekken8_decimated(k, d, donor, log, weights, target, poses, source, fill=None):
    """tekken8_model's loaded model k decimated to `target` (the costume's parts but the face, the hair and the
    weapons with PART_CLASSES, the face with the definition's TEKKEN8['face_classes'] if any, the hair with
    HAIR_CLASSES; with `fill` to the target _fill_target finds) and re-posed; source: its vertices' numbers as loaded,
    or None when they are k's."""
    from . import decimate
    spec = d.TEKKEN8
    own = dict(PART_CLASSES, **spec['part_classes']) if 'part_classes' in spec else PART_CLASSES
    classes = {tag: own for tag in weights if tag[:3] not in PART_WEIGHTS and not tag.startswith('wpn')}
    if 'face_classes' in spec:
        classes.update((tag, spec['face_classes']) for tag in weights if tag[:3] == 'fac')
    hair = dict(HAIR_CLASSES, **spec['hair_classes']) if 'hair_classes' in spec else HAIR_CLASSES
    classes.update((tag, hair) for tag in weights if tag[:3] in ('har', 'fah'))

    def decimated(t):
        out = decimate.decimate(k, t, weights, log=log, poses=poses, classes=classes)
        if 'free' in k and out is not k:         # (a definition's TEKKEN8['covered'])
            from . import covered
            out = covered.trim(out, k['free'], k.get('under'))
        return out
    if fill is None:
        out = decimated(target)
    else:
        out = _fill_target(decimated, fill['target'] + fill['room'], fill, log)
    if out is k:                                 # (within the target already: k as it is, kept for a second call)
        out = dict(k, source=source) if source is not None else dict(k)
    elif source is not None:                     # (the vertices' numbers as loaded: tekken8/cloth.py)
        out['source'] = source[out['source']]
    return skeleton.repose(out, donor, log=log)


def weapon_bones(weapons):
    """The extra bones a Tekken 8 fighter's weapons take: a bone and its points each."""
    return sum(1 + len(w.get('points', {})) for w in weapons)


def weapon_point(k, skel, w, where, world, weights):
    """The model-space position (mm) of a Tekken 8 weapon's point (convert/summons8.py): 'origin' (the weapon
    bone's), 'tip' (its mesh's vertex farthest from it: Miary Zo's horn), {'along': (bone, bone), 'cm': x} (x cm past
    the second TTT2 bone on the line from the first), {'offset': (x, y, z)} (mm in the weapon's frame: its Tekken 8
    joint's, as the fighter's hit boxes give them: Victor's)."""
    if where == 'origin':
        return world[:3, 3]
    if isinstance(where, dict) and 'offset' in where:
        return world[:3, 3] + world[:3, :3] @ np.asarray(where['offset'], np.float64)
    if where == 'tip':
        s0 = k['prims'][0]
        tris = np.concatenate([p['tris'].reshape(-1) for p in k['prims'] if p['part'] == w['tag']])
        joints = s0['joints'][tris]
        mine = np.isin(joints, weights) & (s0['weights'][tris] > 0)
        pos = s0['pos'][tris[mine.any(1)]]
        if not len(pos):
            raise ValueError('weapon %s has no vertices for its tip point' % w['bone'])
        return pos[np.argmax(np.linalg.norm(pos - world[:3, 3], axis=1))]
    if isinstance(where, dict) and 'along' in where:
        hw = bone.world_matrices(skel)
        names = [n[4:] if n.startswith('cha:') else n for n in skel['names']]
        a, b = (hw[names.index(x)][:3, 3] for x in where['along'])
        return b + (b - a) / np.linalg.norm(b - a) * float(where['cm']) * 10.0
    raise ValueError('weapon %s: a point %r is none Tekken 8 weapons take' % (w['bone'], where))


def tekken8_weapons(skel, k, d, weapons, weight_maps, mesh_order, log=print):
    """A Tekken 8 fighter's weapons (convert/summons8.py) appended to its skeleton: each one's bone at its Tekken 8
    joint's frame ('joint', default 'bone': weapons.joint_frame of the re-posed model) or, hit-only, at its lead
    joints' most forward ('lead'), its parent's ('origin' only points), or a root point's bind ('root':
    summons8.ROOT_BIND); its mesh's vertices (the part of its 'mesh': weapon_parts) skinned to it from its 'weights'
    joints (default its joint); its points {code: (where, slot)} (weapon_point). -> the skeleton."""
    from . import summons8
    tags = dict((p, t) for t, p in weapon_parts(weapons))
    kidx = {n: i for i, n in enumerate(k['bones']['names'])}
    drawn = collections.Counter()
    for n, w in enumerate(weapons):
        w = dict(w, tag=tags.get(w.get('mesh')))
        joint = w.get('joint', w['bone'])
        if w.get('root') is not None:
            world = np.eye(4)
            world[:3, 3] = summons8.ROOT_BIND[w['root']]
        elif w.get('ground'):                    # (the scene's origin a fighter's prefabs play at: convert/prefabs8.py)
            world = np.eye(4)
        elif w.get('place') is not None:
            world = np.eye(4)
            world[:3, 3] = w['place']
        elif w.get('lead'):
            at = [weapons_frame(k, j)[:3, 3] for j in w['lead']]
            world = np.eye(4)
            world[:3, 3] = max(at, key=lambda p: p[2])
        elif joint in kidx:
            world = weapons_frame(k, joint)
        else:                                    # (a hit-only weapon at its parent, or its 'at' point there)
            hw = bone.world_matrices(skel)
            world = hw[weapons_mod.parent_index(skel, w['parent'])].copy()
            if w.get('at'):                      # (Miary Zo's snakes' heads: 1.2 m along her forearm at rest)
                world[:3, 3] = weapon_point(k, skel, w, w['at'], world, [])
        weights = [kidx[j] for j in w.get('weights', (joint,)) if j in kidx]
        if w.get('pair') is None and w['tag'] and weights:     # (a still mesh: its own frame, for its fade's ramp)
            world = summonfade.still_frame(summonfade.part_points(k, w['tag'], weights), world[:3, 3])
        points = [(code, slot, weapon_point(k, skel, w, where, world, weights))
                  for code, (where, slot) in sorted(w.get('points', {}).items())]
        skel, index, number, used = weapons_mod.append_tekken8(skel, w, world, points)
        if w['tag']:
            weight_maps[w['tag']][weights] = index
            if not drawn[w['tag']]:             # (the mesh's parent: its first weapon's)
                up = skel['names'][skel['parent'][index]]
                mesh_order[w['tag']] = ('%s_%s' % (d.CODE, w['tag']), up[4:] if up.startswith('cha:') else up,
                                         100 + int(w['tag'][3:]))
            drawn[w['tag']] += 1
        log('  weapon %s: OPT %d under %s (%s%s), hit points OPT %s%s' % (
            w['bone'], number, w['parent'], 'pair %d' % w['pair'] if w.get('pair') is not None else 'still',
            ', summon %d' % w['summon'] if w.get('summon') is not None else '', used,
            ', drawn: %s' % w['tag'] if w['tag'] else ''))
    for tag in drawn:
        tris = np.concatenate([p['tris'].reshape(-1) for p in k['prims'] if p['part'] == tag])
        log('  weapon mesh %s: %d vertices, %d bones' % (tag, len(np.unique(tris)), drawn[tag]))
    return skel


def weapons_frame(k, joint):
    return weapons_mod.joint_frame(k['bones'], joint)


def convert(source, archives, d, slot=0, log=print, standing=None, weapons=None):
    """_convert. A Tekken 8 fighter's target leaves room for its 2P colour layers by an estimate (vertex_target: as if
    they took all the vertices of their materials); trimmed to the triangles they draw they take less (Miary Zo: 10k
    of 16.4k), so when the model ends more than LAYER_SLACK under the budget (or over it) it is made again, its loaded
    model kept (tekken8_model's cache), decimated to the target whose model with its layers fills the budget by the
    first try's measures (_fill_target). Those measures miss by a few hundred (what a layer draws changes with the
    triangles), so a second try over the budget (it would lose a layer: _convert) is made once more by its own
    measures; only the last try's log is shown."""
    source = sources.of(source)
    cache, lines = {}, []
    t0 = time.time()
    out = _convert(source, archives, d, slot, lines.append, standing, weapons, cache)
    tries = 0
    while isinstance(out, dict):
        log('  model: %d vertices of the budget %d with the 2P colour layers trimmed to what they draw (%d of them; '
            'target %d, %.0f s): made again to fill it' % (out['total'], out['budget'], sum(out['layers'].values()),
                                                             out['target'], time.time() - t0))
        tries += 1
        out['last'] = tries == 2
        lines = []
        out = _convert(source, archives, d, slot, lines.append, standing, weapons, cache, out)
    for line in lines:
        log(line)
    return out


def _convert(source, archives, d, slot=0, log=print, standing=None, weapons=None, cache=None, fill=None):
    """source: the fighter's game (source.py; Tekken 7's paks as such too: outfits.py's), d: the character definition,
    slot: its number (pack.place), standing: the fighter's standing pose (cloth.standing; the cloth rests outside its
    legs there), weapons: its weapons (None: the definition's WEAPONS; a Tekken 8 fighter's with its root points:
    summons8.weapons). -> (nud bytes, nut bytes, bon bytes, colours, cloth): colours = None without 2P colour layers
    (colours.py), else {palette number: (player 1's rgb, player 2's rgb)} (shared.py puts them in the colour grid);
    cloth = None, else the cloth's spring entries (cloth.springs). cache (convert's: a Tekken 8 fighter's loaded
    model): a Tekken 8 model more than LAYER_SLACK off the budget returns its measures instead (fill None: the first
    try), or is decimated to fill it by them (fill: those measures), returning its own when it ends over the budget
    (unless fill['last']).
    A Tekken 8 fighter (tekken8_model) has none of what only Tekken 7's reading makes: costume items worn with
    others, socket items, hanging chains or a tiger; its cloth is the strands its source finds, its weapons
    (tekken8_weapons) the meshes of its definition's WEAPONS, made parts of its model, and hit-only points."""
    source = sources.of(source)
    donor = bone.read(archives.read_name(d.DONOR + '.bon'))
    weapons = list(getattr(d, 'WEAPONS', []) if weapons is None else weapons)
    armed = []                                   # (Tekken 8: the weapons' meshes, parts of its model)
    if source.game == 'tekken8':
        k, worn, colours, colours_2p = tekken8_model(source, d, donor, log, weapons, cache, fill)
        counted = _counts(k)                     # (convert's second try: _fill_target)
        armed = [tag for tag, _ in weapon_parts(weapons)]
        paks, items, extra, chains = None, [], [], []
        # the strands Tekken 8 simulates (cords, strap ends: tekken8/cloth.py), as cloth.find gives Tekken 7's cloth
        cloths = source.cloth(k, [p for p in worn if p[0] not in armed], log) if getattr(d, 'CLOTH', True) else []
    else:
        paks = source.paks
        t7 = d.TEKKEN7
        follow = getattr(d, 'DEPENDENCY_ITEMS', False)     # (a definition's: items worn with others, Noctis's trousers)
        items = getattr(d, 'PRESET_ITEMS', None)
        if items is None:
            items = costume_items(paks, t7['costume'], follow)
        extra = dependency_parts(items, t7['parts']) if follow else []
        for tag, path in extra:
            log('  %s: worn with the costume (an item another depends on)' % path.split('/')[-1])
        worn = worn_parts(list(t7['parts']) + extra, dependency_meshes(items))
        for (_, path), (_, now) in zip(t7['parts'], worn):
            if now != path:
                log('  %s: drawn as %s (worn under the costume\'s other items)' % (path.split('/')[-1],
                                                                                   now.split('/')[-1]))
        k = load_tekken7_model(paks, worn, list(t7['merge_order']) + [tag for tag, _ in extra])
        log('  Tekken 7 model: %d bones, %d sections' % (len(k['bones']['names']), len(k['prims'])))
        chains = [(part, hanging.find(k, part, root), directions)
                  for part, root, directions in getattr(d, 'CHAINS', [])]
        if chains:                               # hair and tails Tekken 7 simulates: posed hanging (chains.py)
            moved = hanging.drape(k, [(bones, directions) for _, bones, directions in chains])
        # cloth Tekken 7 simulates: chains of bones like Lars's coat tails (cloth.py); a definition's CLOTH = False:
        # none
        cloths = cloth.find(paks, k, worn, log) if getattr(d, 'CLOTH', True) else []
    if cloths:                                   # (the room the other extra bones leave: weapons up to 4 each)
        from . import snakes8, prefabs8          # (a definition's own SKELETON_BONES: Miary Zo's, with her snakes')
        room = getattr(d, 'SKELETON_BONES', cloth.SKELETON) - len(donor['names']) - sum(
            len(bones) for _, bones, _ in chains) - (
            4 * len(weapons) if source.game == 'tekken7' else weapon_bones(weapons)) - (
            len(t7mesh.SkeletalMesh(load(paks, d.TIGER['mesh'])).skeleton['names'])
            if getattr(d, 'TIGER', None) else 0) - (snakes8.bone_count(d) if source.game == 'tekken8' else 0) - (
            prefabs8.bone_count(d) if source.game == 'tekken8' else 0)
        spare = (getattr(d, 'TEKKEN8', {}) or {}).get('cloth_spare') if source.game == 'tekken8' else None
        if spare and room < cloth.MAX_BONES:     # (weapons take bones the cloth would have: these pieces go first)
            kept = [c for c in cloths if not re.search(spare, c.get('name', ''))]
            log('  cloth: %d pieces left out for the weapons\' bones (%s; room for %d)' % (
                len(cloths) - len(kept), spare, room))
            cloths = kept
        cloth_chains = cloth.add(k, cloths, room, log, most=getattr(d, 'CLOTH_BONES', cloth.MAX_BONES))
    else:
        cloth_chains = []
    skel = skeleton.build(k['bones'], donor)
    weight_maps = {tag: skeleton.weight_map(k['bones'], skel['names'], lambda i, tag=tag: tag)[0]
                   for tag, _ in worn}
    if chains:                                   # ... and swinging extra bones
        parents = [int(weight_maps[part][k['bones']['parents'][bones[0]]]) for part, bones, _ in chains]
        skel, made = hanging.append_bones(skel, k, [bones for _, bones, _ in chains], parents)
        if hanging.OPT_FIRST + sum(map(len, made)) > cloth.OPT_FIRST:
            raise ValueError('more hanging chain bones than OPT %d..%d hold' % (hanging.OPT_FIRST, cloth.OPT_FIRST))
        for (_, bones, _), new in zip(chains, made):
            for wm in weight_maps.values():
                wm[bones] = new
        log('  hanging chains: %s (%d bones, OPT %d..; %d vertices moved)' % (
            ', '.join(root for _, root, _ in d.CHAINS), sum(map(len, made)), hanging.OPT_FIRST, moved))
    cloth_springs = None
    if cloth_chains:                             # ... and the cloth's
        parents = [int(weight_maps[c['part']][c['parent']]) for c in cloth_chains]
        if (getattr(d, 'TEKKEN8', None) or {}).get('long_cloth'):
            parents = cloth.long_cloth_parents(cloth_chains, parents, skel['names'], d.TEKKEN8['long_cloth'])
        s0 = k['prims'][0]
        body = np.zeros(len(s0['pos']), bool)
        body[np.concatenate([p['tris'].reshape(-1) for p in k['prims']])] = True
        for c in cloths:
            body[c['vertices']] = False
        body = s0['pos'][body]
        if standing is not None:                 # (resting outside the legs as the fighter stands)
            turned, moved = cloth.settle(k, cloth_chains, skel, parents, standing, body)
            log('  cloth: %d links turned off the legs in the standing pose (%d vertices moved)' % (turned, moved))
        skel, made = hanging.append_bones(skel, k, [c['bones'] for c in cloth_chains], parents, cloth.OPT_FIRST)
        for c, new in zip(cloth_chains, made):
            for wm in weight_maps.values():
                wm[c['bones']] = new
        if (getattr(d, 'TEKKEN8', None) or {}).get('long_cloth'):
            cloth.long_cloth(cloth_chains, d.TEKKEN8['long_cloth'])
        cloth_springs = cloth.springs(skel, made, cloth_chains, body)
        log('  cloth: %d chains, %d bones (OPT %d..), %d capsules (%s), %d pairs, %d links between chains' % (
            len(made), sum(map(len, made)), cloth.OPT_FIRST, len(cloth_springs['capsules']),
            ', '.join('%s %s' % (skel['names'][b][4:], '/'.join('%.0f' % x for x in size))
                      for b, _, size in cloth_springs['capsules']),
            len(cloth_springs['pairs']), len(cloth_springs['links'])))
    hidden = None
    if getattr(d, 'HIDE', None):                 # chains left out: the triangles skinned to them
        bones = [b for part, root in d.HIDE for b in hanging.find(k, part, root)]
        s0 = k['prims'][0]
        hidden = ((np.isin(s0['joints'], bones) & (s0['weights'] > 0)) * s0['weights']).sum(1) > 0.5
        log('  left out: %s (%d vertices)' % (', '.join(root for _, root in d.HIDE), int(hidden.sum())))
    covered = {}                                 # part -> its vertices in front of an item worn over it (COVERED)
    for part, material in getattr(d, 'COVERED', []):
        s0 = k['prims'][0]
        tris = np.concatenate([p['tris'] for p in k['prims'] if p['material'] == material])
        if hidden is not None:
            tris = tris[~hidden[tris].any(1)]
        front = in_front(s0['pos'], s0['pos'][tris])
        covered[part] = front if part not in covered else covered[part] | front
        log('  %s: %d triangles in front of %s left out' % (part, sum(
            int(front[p['tris']].any(1).sum()) for p in k['prims'] if p['part'] == part), material))
    shrink = getattr(d, 'DECIMATE', None) if source.game == 'tekken7' else None
    if shrink:                                   # (a definition's: a model too big to skin every frame, Noctis's)
        from . import decimate
        weights = {tag: PART_WEIGHTS.get(tag[:3], 1.0) for tag, _ in worn}
        k = decimate.decimate(k, shrink['body'], weights, log=log)
        if 'source' in k:                        # the masks above on the streams left
            hidden = hidden[k['source']] if hidden is not None else None
            covered = {part: front[k['source']] for part, front in covered.items()}
    parts, prims = list(worn), list(k['prims'])
    sockets = [('item%d' % n, path, offsets) for n, (path, offsets) in enumerate(socket_items(items))]
    for tag, path, offsets in sockets:           # static meshes worn on the head (glasses): rigid on its Head joint
        prims += load_socket_item(paks, k, tag, path, offsets)
        weight_maps[tag] = skeleton.weight_map(k['bones'], skel['names'], lambda i, tag=tag: tag)[0]
        log('  %s: worn on %s (offsets %s)' % (path.split('/')[-1],
                                               skel['names'][weight_maps[tag][k['bones']['names'].index('Head')]],
                                               offsets))
    if getattr(d, 'TIGER', None):                # a summoned model: extra bones of the fighter's (tiger.py)
        tk = load_tekken7_model(paks, [('tiger', d.TIGER['mesh'])], ['tiger'])
        skel, first = tiger.append_bones(skel, tk['bones'])
        weight_maps['tiger'] = first + np.arange(len(tk['bones']['names']))
        parts.append(('tiger', d.TIGER['mesh']))
        prims += [dict(p, pos=tiger.hidden(p['pos'])) for p in tk['prims']]
        log('  tiger: %d extra bones (OPT %d..), %d sections' % (len(tk['bones']['names']), tiger.OPT_FIRST,
                                                               len(tk['prims'])))
    mesh_order = dict(d.MESHES)
    for n, (tag, _) in enumerate(extra + [p for p in worn if p[0] not in d.MESHES and source.game == 'tekken8']):
        mesh_order.setdefault(tag, ('%s_%s' % (d.CODE, tag), 'KOSHI_jnt', 40 + n))
    for n, (tag, _, _) in enumerate(sockets):
        mesh_order.setdefault(tag, ('%s_%s' % (d.CODE, tag), 'ATAMA_jnt_assist', 50 + n))
    loaded = {}                                  # weapon meshes by path
    from . import prefabs8
    if source.game == 'tekken8' and prefabs8.spec(d):
        weapons = prefabs8.placed(source.store, d, weapons, log)
    if source.game == 'tekken8' and weapons:     # (its own: tekken8_weapons)
        skel = tekken8_weapons(skel, k, d, weapons, weight_maps, mesh_order, log)
    # --- a Tekken 8 summoned model with its own skeleton (Miary Zo's snakes: convert/snakes8.py) ---
    from . import snakes8
    if source.game == 'tekken8' and snakes8.spec(d):
        skel, first, snake_prims, snake_parts = snakes8.model(source, d, skel, log)
        up = skel['names'][skel['parent'][first]]
        for n, (tag, path) in enumerate(snake_parts):
            weight_maps[tag] = first + np.arange(snakes8.bone_count(d))
            parts.append((tag, path))
            mesh_order[tag] = ('%s_%s' % (d.CODE, tag), up[4:] if up.startswith('cha:') else up, 120 + n)
        prims += snake_prims
    # --- end of the summoned model ---
    if source.game == 'tekken8' and prefabs8.spec(d):         # (its summoned creatures: convert/prefabs8.py)
        skel, made, made_prims = prefabs8.model(source, d, skel, log)
        for n, (tag, path, first, count) in enumerate(made):
            weight_maps[tag] = first + np.arange(count)
            parts.append((tag, path))
            up = skel['names'][skel['parent'][first]]
            mesh_order[tag] = ('%s_%s' % (d.CODE, tag), up[4:] if up.startswith('cha:') else up, 130 + n)
        prims += made_prims
    for n, w in enumerate(weapons if source.game == 'tekken7' else []):   # weapons its animations pose: extra bones
        tag = 'weapon%d' % n
        if w.get('mesh'):
            if w['mesh'] not in loaded:
                loaded[w['mesh']] = load_tekken7_model(paks, [(tag, w['mesh'])], [tag])
            wk = loaded[w['mesh']]
        else:                                    # a weapon only hitting: its bones are the costume's
            wk = k
        skel, index, number, points = weapons_mod.append_bones(skel, wk['bones'], w)
        kept = []
        if w.get('mesh') and w.get('draw', True):
            weight_maps[tag] = np.full(len(wk['bones']['names']), index, np.int64)
            own = wk['bones']['names'].index(w['bone'])
            kept = [dict(q, part=tag) for q in (weapons_mod.triangles(q, own) for q in wk['prims']) if len(q['tris'])]
            if kept and shrink and shrink.get('weapons'):    # (a share of its vertices, or as few as its hard
                one = dict(wk, prims=kept)                    # edges leave: what is left is no warning)
                kept = decimate.decimate(one, int(decimate.count(one) * shrink['weapons']),
                                         log=lambda line: None if 'WARNING' in line else log(line))['prims']
            parts.append((tag, w['mesh']))
            prims += kept
            up = skel['names'][skel['parent'][index]]          # (w['parent'], or the weapon it is carried in)
            mesh_order[tag] = ('%s_wpn%d' % (d.CODE, n), up[4:] if up.startswith('cha:') else up, 100 + n)
        log('  weapon %s: OPT %d under %s (%s), hit points OPT %s, %d triangles drawn' % (
            w['bone'], number, w['parent'], 'pair %d' % w['pair'] if w.get('pair') is not None else 'still', points,
            sum(len(q['tris']) for q in kept)))
    names = [n[4:] if n.startswith('cha:') else n for n in skel['names']]
    bidx = {n: i for i, n in enumerate(names)}
    templates = load_templates(archives, d.TEMPLATES, d.TEMPLATE_TEXTURES)
    materials = source.materials()
    if source.game == 'tekken7':                 # (Tekken 8's come with its costume: tekken8_model)
        colours = materials.costume_colours(t7['costume'])
        colours_2p = materials.costume_colours(t7['costume_2p']) if t7.get('costume_2p') else None
    palette = colours2p.Palette(archives.read(colours2p.KEY_GRID),
                                [archives.read(k).decode('utf-8') for k in (colours2p.KEY_1P, colours2p.KEY_2P)]) \
        if colours_2p else None
    textures = source.textures()
    mat_paths = source.material_paths(parts)
    for _, path, _ in sockets:
        for ref in StaticMesh(load(paks, path)).materials:
            if short_ref(ref):
                mat_paths.setdefault(short_ref(ref).split('.')[-1], short_ref(ref))
    face = sorted((name for name in mat_paths if any(w in name.lower() for w in source.FACE_WORDS)), key=len)
    own = None
    if face:                                      # its face's colour picks the gain (skin.py)
        # (a Tekken 8 face without the hair painted on its scalp, as the reference faces are measured)
        face_colours = colours
        if source.game == 'tekken8':
            from ..tekken8.material import unpainted
            face_colours = unpainted(colours)
        rgb, _ = source.bake_albedo(materials.effective(mat_paths[face[0]], face_colours), textures)
        own = rgb.reshape(-1, 3).mean(0) if rgb is not None else None
    skin_gain, skin_hue = skin.gain(source, archives, d.SEX, materials, lambda eff: source.bake_albedo(eff, textures),
                                    own=own, log=log)
    if getattr(d, 'SKIN_HUE', None) == 'own':    # (Gigas is red)
        skin_hue = None
    bank = TextureBank(GIDX_BASE + SLOT_GIDX * slot)
    built = {}
    shines = {}                     # Tekken 8 cloth -> its shine texture (tekken8.bake.specular) or None
    bright_hairs = set()            # Tekken 8 hair baked solid (tekken8.bake.bright_hair)
    cutoffs = {}                    # hair material -> Tekken 7's alpha threshold (0..255)
    layers, palettes = {}, {}       # material -> its 2P colour layer (fit, palette numbers); the palette entries

    kinds = {}
    flat = getattr(d, 'FLAT', {})
    # Tekken 7 lights its fighters with rim terms besides the colour (Fresnel on M_CH_Base and its kin, its hair's)
    # that TTT2's templates do not have: an outfit and hair as dark as Noctis's (colours 0.02..0.06 of the textures')
    # are black in TTT2, their prints and lighter tips gone; a definition's GAIN {template kind or material name: linear
    # gain} lifts them
    gains = dict(getattr(d, 'GAIN', {}))
    grey = set(getattr(d, 'GREY', ()))
    dark_metal = getattr(d, 'TEKKEN8', {}).get('dark_metal', {}) if source.game == 'tekken8' else {}
    # a material's metal without dark_metal's colours: (unused, its strength, its reflection, unused) x bake.specular's
    shine = getattr(d, 'TEKKEN8', {}).get('shine', {}) if source.game == 'tekken8' else {}
    # the materials given 2P colour layers: every cloth's, or a definition's TEKKEN8['layers']
    layered = getattr(d, 'TEKKEN8', {}).get('layers') if source.game == 'tekken8' else None
    # layered materials whose palette makes up for the layer's darkening (bake.layer_colour), by their linear gains: a dark
    # colour with no satin
    layer_lift = getattr(d, 'TEKKEN8', {}).get('layer_lift', {}) if source.game == 'tekken8' else {}
    hair_thick = getattr(d, 'TEKKEN8', {}).get('hair_thick', {}) if source.game == 'tekken8' else {}
    layer_holes = getattr(d, 'TEKKEN8', {}).get('layer_holes', ()) if source.game == 'tekken8' else ()
    # (layerfit.py) layers fitted texel by texel, layers whose values go into their holes before sizing, and the bases under
    # a layer brightened by a linear gain as the layer's lift brightens what it draws (where the layer is out, the base shows)
    layer_blend = getattr(d, 'TEKKEN8', {}).get('layer_blend', ()) if source.game == 'tekken8' else ()
    layer_bleed = getattr(d, 'TEKKEN8', {}).get('layer_bleed', ()) if source.game == 'tekken8' else ()
    base_lift = getattr(d, 'TEKKEN8', {}).get('base_lift', {}) if source.game == 'tekken8' else {}
    # cloths whose shine's strength (its R) a gain lifts
    shine_gain = getattr(d, 'TEKKEN8', {}).get('shine_gain', {}) if source.game == 'tekken8' else {}
    # costume IDs brought to the colours Tekken 8 shows them in (convert/idlook.py)
    id_look = getattr(d, 'TEKKEN8', {}).get('id_look', {}) if source.game == 'tekken8' else {}

    def bake(name, eff):
        """bake_albedo, or for a material the definition's FLAT names (one without a colour texture: Leroy's lenses)
        that colour parameter of it, flat."""
        if name in flat:
            return np.full((32, 32, 3), np.clip(_col(eff['vectors'][flat[name]]), 0, 1), np.float32), None
        if prefabs8.bakes(d, eff):
            return prefabs8.bake(d, eff, textures, name)
        return source.bake_albedo(eff, textures, grey=name in grey)

    # --- glowing parts (Tekken 8 summons: tekken8/bake.py bake_emissive), the definition's 'glow' template ---
    def glow_kind(name, eff, kind):
        """classify()'s kind, or 'glow' for a part that glows (its emission share: bake.emission_share) when the
        definition has the 'glow' template (else it stays lit, logged)."""
        from ..tekken8 import bake as bake8
        share = bake8.emission_share(eff, textures)
        glow = bake8.classify(name, eff['base'], None, share) if share is not None else None
        if not glow or glow[0] != 'glow':
            return kind
        if 'glow' not in templates:
            log('  material %s glows (emission %.0f%%) but the definition has no glow template: lit' % (
                name, 100 * share))
            return kind
        log('  material %s glows (emission %.0f%% of its look): its glow baked into its colour' % (name, 100 * share))
        return glow

    def glow_bake(eff):
        from ..tekken8 import bake as bake8
        return bake8.bake_emissive(eff, textures)

    def glow_two_sided(name):
        return bool(materials.effective(mat_paths[name], colours)['overrides'].get('TwoSided'))
    # --- end of glowing parts ---

    def kind_of(name):
        """The definition's MATERIALS entry, else classify()."""
        if name in d.MATERIALS:
            return d.MATERIALS[name]
        if name not in kinds:
            eff = materials.effective(mat_paths[name], colours)
            try:
                rgb, al = bake(name, eff)
            except (KeyError, ValueError):
                rgb, al = None, None
            kinds[name] = source.classify(name, eff['base'], al) if rgb is not None else None   # nothing to draw
            if kinds[name] is not None and source.game == 'tekken8':
                kinds[name] = glow_kind(name, eff, kinds[name])
            if kinds[name] is not None and prefabs8.bakes(d, eff):
                kinds[name] = (kinds[name][0], False, kinds[name][2])       # (small textures: no normal map)
            if kinds[name] is not None and prefabs8.lace_kind(name) in templates:
                kinds[name] = (prefabs8.lace_kind(name), False, True)       # (a lace model's 'kind': lace8.py)
            log('  material %s (%s): %s' % (name, eff['base'], kinds[name]))
        return kinds[name]

    def build_material(name, turned=False):
        """The material of a polygon of `name`; turned: a hair's texture upside down (its UVs turned: tips_first)."""
        kind, use_normal, alpha = kind_of(name)
        mat, vtype, slots = templates[kind]
        if name not in built:
            eff = materials.effective(mat_paths[name], colours)
            # (a lace model's pictures, or a summon the definition's prefabs bake, drawn with a 'glow' template as
            # baked: prefabs8.bake)
            rgb, al = bake(name, eff) if kind != 'glow' or prefabs8.lace(name) or prefabs8.bakes(d, eff) else glow_bake(eff)
            if rgb is None:
                raise ValueError('material %s has no colour texture' % name)
            if name in id_look:                  # (a definition's: IDs at Tekken 8's look)
                from . import idlook
                rgb = idlook.apply(rgb, eff, textures, id_look[name])
            if cache is not None and name in cache.get('shown', ()):    # (a definition's TEKKEN8['covered'])
                from . import covered
                rgb = covered.paint(rgb, cache['shown'][name])
            if cache is not None and name in cache.get('occlusion', ()):    # (a definition's TEKKEN8['skin_occlusion'])
                from . import occlusion
                rgb = occlusion.apply(rgb, cache['occlusion'][name])
            if name in dark_metal:
                from ..tekken8 import bake as bake8
                rgb = bake8.dark_metal(rgb, eff, textures, dark_metal[name])
            if source.game == 'tekken8' and kind == 'hair':
                from ..tekken8 import bake as bake8
                if bake8.is_bright_hair(rgb, al, eff):
                    bright_hairs.add(name)
                elif name in hair_thick:
                    rgb, al = bake8.thick_hair(rgb, al, eff, hair_thick[name])
                    bright_hairs.add(name)
            if kind == 'skin':                   # TTT2's skin colours (skin.py)
                rgb = skin.hue(skin.gained(rgb, skin_gain), skin_hue)
            elif name in gains or kind in gains:  # (a definition's GAIN)
                rgb = np.clip(rgb * gains.get(name, gains.get(kind)), 0, 1)
            built[name] = albedo_image(rgb, al), eff['textures'].get('Normal') if use_normal else None
            if source.game == 'tekken8' and kind == 'cloth':
                from ..tekken8 import bake as bake8
                shines[name] = (prefabs8.shine(d, eff, textures) if prefabs8.bakes(d, eff)
                                else bake8.specular(eff, textures, dark=dark_metal.get(name) or shine.get(name)))
                if name in shine_gain and shines[name] is not None:     # (a definition's: a cloth's sheen)
                    lifted = shines[name].astype(np.float32)
                    lifted[..., 0] *= shine_gain[name]
                    shines[name] = (np.clip(lifted, 0, 255) + 0.5).astype(np.uint8)
            if 'AlphaThreshold' in eff['scalars']:
                cutoffs[name] = clear_of_dissolve(int(round(255 * min(max(eff['scalars']['AlphaThreshold'], 0.0), 1.0))))
            if colours_2p is not None and kind == 'cloth' and 'colour' in templates and (layered is None or name in layered):
                eff2 = materials.effective(mat_paths[name], colours_2p)
                rgb2, _ = bake(name, eff2)
                if name in dark_metal:
                    from ..tekken8 import bake as bake8
                    rgb2 = bake8.dark_metal(rgb2, eff2, textures, dark_metal[name])
                rgb2 = np.clip(rgb2 * gains.get(name, gains.get(kind, 1.0)), 0, 1)
                c1 = np.asarray(built[name][0].convert('RGB'), np.float64) / 255.0
                c2 = np.asarray(albedo_image(rgb2, None).convert('RGB'), np.float64) / 255.0
                # (Tekken 8's grey-detail costumes: texels two groups miss left out; Tekken 7's fitted as before)
                satin, lift = None, None
                if source.game == 'tekken8':
                    from ..tekken8 import bake as bake8
                    satin = bake8.satin_cloth(eff, textures, c1.shape[:2])
                    lift = None if satin is None else bake8.satin_lift(eff, textures, satin.shape)
                    if lift is None and name in layer_lift:   # (a definition's: the layer's own darkening made up for)
                        lift = lambda group, rgb, texels, g=layer_lift[name]: bake8.layer_colour(rgb, g)
                if name in layer_blend and satin is None:    # (a definition's: each texel its own blend of the groups)
                    from . import layerfit
                    f = layerfit.fit(c1, c2, palette, max_error=colours2p.MAX_ERROR, lift=lift)
                else:
                    f = colours2p.fit(c1, c2, palette, max_error=colours2p.MAX_ERROR if source.game == 'tekken8' else None,
                                      satin=satin, lift=lift)
                if f is not None and name in base_lift:   # (a definition's: the base as bright as the layer draws)
                    built[name] = albedo_image(np.clip(rgb * base_lift[name], 0, 1), al), built[name][1]
                if f is not None:
                    nn = colours2p.FIRST_PALETTE + 2 * len(layers)
                    layers[name] = (f, (nn, nn + 1))
                    for k, (_, rgb1, _, rgb2) in enumerate(f['groups']):
                        palettes[nn + k] = ([float(x) for x in rgb1], [float(x) for x in rgb2])
        albedo, normal = built[name]
        mat = copy.deepcopy(mat)
        if (kind == 'glow' or prefabs8.bakes(d, materials.effective(mat_paths[name], colours))) and glow_two_sided(name):
            mat['cull'] = 0                      # (a two-sided glowing part: the tail's fur cards)
        elif source.game == 'tekken8' and prefabs8.two_sided(name):
            mat['cull'] = 0                      # (a summon's sheet whose back layer a remesh left out: convert/remesh8.py)
        if kind == 'hair' and mat['alpha_test'] and name in cutoffs:
            mat['ref'] = cutoffs[name]  # where Tekken 7 cuts its strands (the template's own cut is higher)
        if (kind == 'cloth' or prefabs8.lace(name)) and alpha and not mat['alpha_test'] and 'colour_alpha' in templates:
            for key in ('alpha_test', 'alpha_func', 'ref'):    # cloth with holes (lace, frills): alpha-tested
                mat[key] = templates['colour_alpha'][0][key]
            if prefabs8.lace_ref(name) is not None:            # (a dissolving lace model's: convert/lace8.py)
                mat['ref'] = prefabs8.lace_ref(name)
        ids = []
        for i, slot in enumerate(slots):
            if i == 0:
                image, key = (albedo.transpose(Image.FLIP_TOP_BOTTOM) if turned else albedo), name
                if source.game == 'tekken8':      # (materials baking alike share one: Reina's eyebrows and lashes)
                    key = ('pixels', image.mode, image.size, hashlib.sha1(image.tobytes()).hexdigest())
                ids.append(bank.image(key, image, 2 if alpha else 0, alpha,
                                      solid=cutoffs.get(name, HAIR_SOLID_REF) if name in bright_hairs else None))
                if source.game == 'tekken8' and (kind == 'hair' or (kind == 'skin' and name.endswith('face_skin'))
                                                 or prefabs8.lace(name)):
                    # (halved after all others: the hair's narrow cards, Tekken 8's strands would blur; the face's
                    # painted eyes, at 256 texels Miary Zo's eyeshadow edge and winged eyeliner went to DXT blocks;
                    # a lace summon's pictures, its pieces' holes and torn edges, at 256 texels a blur of blocks)
                    bank.kept.add(ids[-1] - bank.first)
            elif kind == 'hair' and source.game == 'tekken8' and slot['texture'] is not None:
                # Tekken 8 has nothing like the template's other textures (the hair shader's ramps from the roots
                # along v and its highlights' noise, the same in TTT2's hair textures): the template's own
                ids.append(bank.add(('template', slot['texture']['gidx']), nut.decode(slot['texture']), slot['fmt']))
            elif i == 2 and shines.get(name) is not None:
                # (Tekken 8's cloth: its shine from its own roughness and metal, not the template's average)
                ids.append(bank.add(('shine', name), shines[name], slot['fmt']))
            elif i == 1 and normal_slot(slot, strict=source.game != 'tekken8'):
                # a normal map slot (R = 0, G = Y, B = 0, A = X)
                if textures.exists(normal):
                    ids.append(bank.normal(normal, Image.fromarray(textures.get(normal)[0])))
                else:
                    ids.append(bank.constant((0, 128, 0, 128), 2))
            else:
                mean = slot['mean'] if slot['mean'] is not None else np.array([128, 128, 128, 255])
                ids.append(bank.constant(tuple(mean), slot['fmt']))
        for t, gid in zip(mat['textures'], ids):
            t['id'] = gid
            t['wrap_s'] = t['wrap_t'] = WRAP_REPEAT        # Tekken 7 repeats textures (UVs run past 0..1)
        return mat, vtype, kind

    def layer_material(name):
        """The colourable, alpha-tested material of a 2P colour layer."""
        f, nns = layers[name]
        albedo, normal = built[name]
        mat, vtype, slots = templates['colour']
        mat = copy.deepcopy(mat)
        alpha_from = templates.get('colour_alpha', templates['colour'])[0]
        for key in ('src', 'dst', 'alpha_test', 'alpha_func', 'ref'):
            mat[key] = alpha_from[key]
        size = pow2_size(*albedo.size)

        def image(a, mode):
            return np.asarray(Image.fromarray(a, mode).resize(size, Image.LANCZOS))
        cut = f['alpha']
        if name in layer_holes and albedo.mode == 'RGBA':   # (a definition's: the base's holes through the layer as well)
            cut = cut * (np.asarray(albedo.getchannel('A')) >= 128)
        shade_f, b_f = f['shade'], f['b']
        if name in layer_bleed:              # (a definition's: no black mixed in round the holes when sized)
            from . import layerfit
            shade_f, b_f = layerfit.bleed(cut > 0.5, shade_f), layerfit.bleed(cut > 0.5, b_f)
        grey = (np.clip(shade_f, 0, 1) * 255 + 0.5).astype(np.uint8)
        shade = np.stack([image(grey, 'L')] * 3 + [image((cut * 255).astype(np.uint8), 'L')], -1)
        mask = np.zeros(shade.shape, np.uint8)
        mask[..., 0] = 255
        mask[..., 2] = image((np.clip(b_f, 0, 1) * 255 + 0.5).astype(np.uint8), 'L')
        mask[..., 3] = 255
        ids = []
        for i, slot in enumerate(slots):
            if i == 0:
                ids.append(bank.add(('layer-shade', name), shade, 2))
            elif i == 1 and textures.exists(normal):
                ids.append(bank.normal(normal, Image.fromarray(textures.get(normal)[0])))
            elif i == 3:
                ids.append(bank.add(('layer-mask', name), mask, 0))
            elif i == 2 and shines.get(name) is not None:       # (it shines as the cloth under it)
                ids.append(bank.add(('shine', name), shines[name], slot['fmt']))
            else:
                mean = slot['mean'] if slot['mean'] is not None else np.array([128, 128, 128, 255])
                ids.append(bank.constant(tuple(mean), slot['fmt']))
        for t, gid in zip(mat['textures'], ids):
            t['id'] = gid
            t['wrap_s'] = t['wrap_t'] = WRAP_REPEAT        # Tekken 7 repeats textures (UVs run past 0..1)
        (_, a1, _, _), (_, b1, _, _) = f['groups']
        props = []
        for n, v in mat['props']:
            if n == 'NU_vReg_04':
                v = list(a1) + [float(colours2p.ID_BASE + nns[0])]
            elif n == 'NU_vReg_07':
                v = list(b1) + [float(colours2p.ID_BASE + nns[1])]
            props.append((n, [float(x) for x in v]))
        mat['props'] = props
        return mat, vtype

    meshes, dropped = {}, []
    seen = set()                    # the triangles drawn so far (a hair material's second pass draws them again)
    for prim in prims:
        name = prim['material']
        if kind_of(name) is None:
            dropped.append(name)
            continue
        if hidden is not None and len(hidden) == len(prim['pos']):
            prim = dict(prim, tris=prim['tris'][~hidden[prim['tris']].any(1)])
            if not len(prim['tris']):
                continue
        if prim['part'] in covered and len(covered[prim['part']]) == len(prim['pos']):
            prim = dict(prim, tris=prim['tris'][~covered[prim['part']][prim['tris']].any(1)])
            if not len(prim['tris']):
                continue
        corners = np.sort(np.round(prim['pos'][prim['tris']], 1).reshape(len(prim['tris']), -1), 1)
        shape = hash(corners[np.lexsort(corners.T[::-1])].tobytes())
        if shape in seen:
            dropped.append(name + ' (a second pass)')
            continue
        seen.add(shape)
        # Tekken 8's hair cards run from their tips at the top of their textures: turned over, as TTT2's run
        turned = source.game == 'tekken8' and kind_of(name)[0] == 'hair' and tips_first(prim)
        mat, vtype, kind = build_material(name, turned)
        # Tekken 7 splits vertices its meshes share (copies with the same position, normal, uv and skin weights);
        # they are welded: the game skins a fighter's vertices into a buffer made for its own fighters' (~30k)
        used = np.unique(prim['tris'])
        same = np.concatenate([np.round(prim['pos'][used], 3), np.round(prim['nrm'][used], 4),
                               np.round(prim['uv'][used], 6), weight_maps[prim['part']][prim['joints'][used]],
                               np.round(prim['weights'][used], 4)], 1)
        _, first, which = np.unique(same, axis=0, return_index=True, return_inverse=True)
        remap = np.full(len(prim['pos']), -1, np.int64)
        remap[used] = which.reshape(-1)
        tris = remap[prim['tris']]
        tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])]
        used = used[first]
        n = len(used)
        if n >= 0xFFFF:
            raise ValueError('section of %s has too many vertices for one NUD polygon' % name)
        pos = prim['pos'][used]
        nrm = prim['nrm'][used]
        # winding: TTT2's front faces are counter-clockwise around the vertex normal; orient by the normals
        g = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
        if float(((g * nrm[tris].sum(1)).sum(1) < 0).mean()) > 0.5:
            tris = tris[:, [0, 2, 1]]
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        uv = prim['uv'][used]
        if turned:
            uv = uv * (1.0, -1.0) + (0.0, 1.0)
        # skin weights: Tekken 7 bones -> TTT2 bones, merged, the four largest, renormalised
        tj = weight_maps[prim['part']][prim['joints'][used]]
        tw = prim['weights'][used]
        bones = np.zeros((n, 4), np.int64)
        wts = np.zeros((n, 4))
        for v in range(n):
            acc = {}
            for j, w in zip(tj[v], tw[v]):
                if w > 0:
                    acc[int(j)] = acc.get(int(j), 0.0) + float(w)
            top = sorted(acc.items(), key=lambda x: -x[1])[:4]
            s = sum(w for _, w in top)
            for q, (j, w) in enumerate(top):
                bones[v, q] = j
                wts[v, q] = w / s
            for q in range(len(top), 4):
                bones[v, q] = top[0][0]
        # tangent frame: TTT2's tangent is +dP/du, its bitangent -dP/dv
        tan = prim['tan'][used][:, :3]
        tan = tan - nrm * (tan * nrm).sum(1, keepdims=True)
        tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
        a, b, c = tris.T
        e1, e2 = pos[b] - pos[a], pos[c] - pos[a]
        du1, dv1 = uv[b, 0] - uv[a, 0], uv[b, 1] - uv[a, 1]
        du2, dv2 = uv[c, 0] - uv[a, 0], uv[c, 1] - uv[a, 1]
        det = du1 * dv2 - du2 * dv1
        ok = np.abs(det) > 1e-12
        dPdv = (e2 * du1[:, None] - e1 * du2[:, None]) / np.where(ok, det, 1)[:, None]
        acc = np.zeros((n, 3))
        for col in (a, b, c):
            np.add.at(acc, col[ok], dPdv[ok])
        bit = np.cross(nrm, tan)
        bit *= np.where((bit * -acc).sum(1) >= 0, 1.0, -1.0)[:, None]
        # the template's vertex type when it has float bone weights, else 0x13 (u32 bones, f32 weights,
        # f32 normal / bitangent / tangent)
        vt = vtype if (vtype & 0xF0) == 0x10 else 0x13
        verts = np.zeros(n, nud.vertex_dtype(vt, 0x10))
        verts['pos'] = pos
        if 'pw' in verts.dtype.names:
            verts['pw'] = 100.0                      # what the game's files store
        verts['nrm'][:, :3] = nrm
        verts['nrm'][:, 3] = 1.0
        if 'tan' in verts.dtype.names:
            verts['tan'][:, :3] = tan
            verts['tan'][:, 3] = 1.0
            verts['bitan'][:, :3] = bit
            verts['bitan'][:, 3] = 1.0
        verts['bones'] = bones
        verts['w'] = wts
        verts['uv'][:, 0, :] = uv
        strip = strips.stripify(tris)
        if not strips.check(tris, strip) or len(strip) >= 0x10000:
            raise ValueError('could not make triangle strips for %s' % name)
        meshes.setdefault(prim['part'], []).append(dict(vtype=vt, uvtype=0x10, pflag=4, tail=bytes(12),
                                                        indices=np.array(strip, np.uint16), verts=verts,
                                                        materials=[mat], _order=ORDER[kind]))
        if name in layers:
            lmat, lvtype = layer_material(name)
            lverts = verts.copy()
            lverts['pos'] = pos + nrm * LAYER_OFFSET
            meshes[prim['part']].append(dict(vtype=vt, uvtype=0x10, pflag=4, tail=bytes(12),
                                             indices=np.array(strip, np.uint16), verts=lverts, materials=[lmat],
                                             _order=ORDER['colour'], _layer=name, _trim=(uv, tris)))
    # each layer over the triangles it draws (colours.drawn_triangles: its alpha test passes somewhere in them, at
    # its texture's size once the textures fit their budget, LAYER_MARGIN texels round included): a layer is a copy
    # of its polygon's vertices, and over a costume whose colours change only in places most of them drew nothing
    # (Miary Zo: 16.4k layer vertices of her 54.5k, 10.1k of them drawing)
    halvings = bank.fit(TEXTURE_BUDGET, dry=True)
    for tag in meshes:
        kept = []
        for p in meshes[tag]:
            if '_trim' in p:
                uv, tris = p.pop('_trim')
                mat = p['materials'][0]
                i = mat['textures'][0]['id'] - bank.first
                alpha = bank.halved(i, halvings.get(i, 0))[..., 3]
                drawn = colours2p.drawn_triangles(uv, tris, alpha, mat['ref'], LAYER_MARGIN)
                if not drawn.any():
                    continue
                used, ltris = np.unique(tris[drawn], return_inverse=True)
                ltris = ltris.reshape(-1, 3)
                strip = strips.stripify(ltris)
                if not strips.check(ltris, strip) or len(strip) >= 0x10000:
                    raise ValueError('could not make triangle strips for the 2P colour layer of %s' % p['_layer'])
                p['verts'], p['indices'] = p['verts'][used], np.array(strip, np.uint16)
            kept.append(p)
        meshes[tag] = kept
    empty = sorted(set(layers) - {p['_layer'] for polys in meshes.values() for p in polys if p.get('_layer')})
    for name in empty:
        layers.pop(name, None)
    if empty:
        log('  2P colours: no layer over %s (none of its triangles draws any of it)' % ', '.join(empty))
    total = sum(len(p['verts']) for polys in meshes.values() for p in polys)
    by_size = collections.Counter()
    for polys in meshes.values():
        for p in polys:
            if p.get('_layer'):
                by_size[p['_layer']] += len(p['verts'])
    budget = getattr(d, 'VERTEX_BUDGET', VERTEX_BUDGET)
    if source.game == 'tekken8' and cache is not None and (
            abs(budget - total) > LAYER_SLACK if fill is None else total > budget and not fill['last']):
        # (convert: made again, decimated to fill the budget by these measures)
        return dict(total=total, budget=budget, layers=dict(by_size), counts=counted,
                    target=fill['used'] if fill else cache['tekken8'][5], room=budget - LAYER_SLACK // 2 - total)
    def used_textures():
        return {t['id'] for polys in meshes.values() for p in polys for m in p['materials'] for t in m['textures']}

    plain = []
    for name, n in by_size.most_common():
        if total <= budget:
            break
        for tag in meshes:
            meshes[tag] = [p for p in meshes[tag] if p.get('_layer') != name]
        total -= n
        plain.append(name)
        layers.pop(name, None)
    if plain:
        log('  over %d vertices: no 2P colour layers over %s (player 2 has player 1\'s colours there)' % (
            budget, ', '.join(plain)))
    # the textures the materials use (a left-out layer's are not), numbered again
    renumber = bank.keep(used_textures())
    slots = {id(t): t for polys in meshes.values() for p in polys for m in p['materials'] for t in m['textures']}
    for t in slots.values():
        t['id'] = renumber[t['id']]
    for polys in meshes.values():
        for p in polys:
            p.pop('_layer', None)
    nmeshes = []
    for tag in sorted(meshes, key=lambda p: mesh_order[p][2]):
        mname, singlebind, _ = mesh_order[tag]
        polys = sorted(meshes[tag], key=lambda p: p['_order'])
        for p in polys:
            del p['_order']
        sph = nud.bounding_sphere(np.concatenate([p['verts']['pos'] for p in polys]))
        nmeshes.append(dict(name=mname, sphere=sph, center=sph[:3], sort_bias=0.0, zero=0, boneflag=0x2c,
                            singlebind=bidx[singlebind], polys=polys))
    allp = np.concatenate([p['verts']['pos'] for m in nmeshes for p in m['polys']])
    before = sum(len(m) for t in bank.textures for m in t['mips'])
    halved = bank.fit(TEXTURE_BUDGET)
    if halved:
        log('  textures: %d KB, more than the game\'s own fighters have: %d halved (%d KB)' % (
            before // 1024, halved, sum(len(m) for t in bank.textures for m in t['mips']) // 1024))
    if len(allp) > budget:
        log('  WARNING: %d vertices: more than the game skins for a fighter (about %d); the other fighters in a fight '
            'may break' % (len(allp), budget))
    model = dict(version=0x0201, sphere=nud.bounding_sphere(allp), bone_first=None, meshes=nmeshes)
    log('  model: %d meshes, %d polygons, %d vertices, %d textures (dropped: %s)' % (
        len(nmeshes), sum(len(m['polys']) for m in nmeshes), len(allp), len(bank.textures),
        ', '.join(dropped) or 'none'))
    if layers:
        log('  2P colours: layers over %s; palette numbers %s' % (', '.join(sorted(layers)), sorted(palettes)))
    out = palettes if layers else None
    if source.game == 'tekken8':                 # (the game's record order: convert/recordorder.py)
        from . import recordorder
        skel, model = recordorder.write(skel, model, log)
    return nud.write(model), nut.write(bank.textures), bone.write(skel), out, cloth_springs
