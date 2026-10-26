"""Tekken 8's cooked USkeletalMesh (Unreal Engine 5.1/5.2, large world coordinates) with tekken7.mesh's interface:
.skeleton, .materials, .lods[0].sections and .geometry(0).

After the unversioned properties (uprops: Skeleton, LODInfo, SamplingInfo, bHasVertexColors, ...) and the u32
object GUID flag, the class's own data:
    FStripDataFlags (u8 global, u8 class), FBoxSphereBounds (origin, extent, radius: 7 f64)
    TArray materials, 40 bytes each: i32 FPackageIndex material, FName slot, u32 imported-name flag (0),
        FMeshUVChannelInfo {bool32 initialised, bool32 override densities, f32 densities[4]}
    reference skeleton: TArray {FName, i32 parent} (parents before their children), TArray local transforms
        {quat x y z w, translation, scale} as 10 f64, TMap<FName, i32>
    bool32 cooked, TArray LODs, u8 inlined LODs, u8 non-optional LODs, then (the _msl meshes) the Catwalk cloth
        data ('CatwalkClothHook', not read here)
A LOD (all inline: bInlined 1, no .ubulk; every fighter mesh has exactly one):
    FStripDataFlags, bool32 cooked out, bool32 inlined, TArray<u16> required bones
    TArray sections: FStripDataFlags, u16 material, u32 first index, u32 triangles, bool32 recompute tangent, u8
        recompute mask channel, bool32 cast shadow, bool32 visible in ray tracing, u32 first vertex, TArray of
        TArray cloth mapping (76 bytes each: empty), TArray<u16> bone map, u32 vertices, i32 max influences, i16
        cloth asset (-1), FGuid clothing, i32 clothing LOD, TArray<u32> duplicated vertices, TArray {u32, u32} per
        vertex (index, length), bool32 disabled
    TArray<u16> active bones, u32 buffers' size, then the buffers:
        FStripDataFlags; indices: u8 size (2 or 4) + bulk array
        positions: u32 stride (12), u32 vertices, bulk array of float3 (cm)
        static vertex buffer: FStripDataFlags, u32 UV sets, u32 vertices, bool32 full-precision UVs, bool32
            high-precision tangents, bulk array {TangentX, TangentZ} (int8 x 4 each, or int16 x 4: value / 127
            (32767), TangentZ.w the bitangent's sign), bulk array of UVs (half2 or float2, per vertex per set)
        skin weights: FStripDataFlags, bool32 variable influences (0), u32 influences (8), u32 influences in all,
            u32 vertices, bool32 16-bit bone indices, bool32 16-bit weights, bulk array of bytes: per vertex its
            bone indices (into its section's bone map) then its weights (summing to 255, or 65535)
        lookup buffer: FStripDataFlags, u32 entries, bulk array<u32> (empty without variable influences)
        [with the mesh property bHasVertexColors: FStripDataFlags, u32 stride (4), u32 vertices, bulk FColor]
        u32 skin weight profiles (0), u32 ray tracing bytes + those bytes, u32 0
(Bulk array = TArray::BulkSerialize: i32 element size, i32 count, the elements.) Units are centimetres, Z up, the
fighter facing +Y with its left at +X, as in Tekken 7.

Simulation proxies (the cloth solver's low-poly copies, skinned like the rest; MATERIAL SIM_MATERIALS) are reported
with cloth_mapping = 1, the way tekken7.mesh reports the simulation's copy of a disabled section, so loaders leave
them out. The _msl meshes (the 550-joint "muscle rig") are the ones to read; the _prp ones are the same geometry
on a 130-joint proportion rig.

Written for this project from the files themselves (no third-party code).
"""
import struct

import numpy as np

from . import uprops, zen
from .zen import ParseError

# materials of the simulation proxies: M_CH_sim_mesh_material (Catwalk cloth pieces, Reina's jacket and hood),
# MI_Cal_Mesh (the "calculation" meshes of other costumes)
SIM_MATERIALS = ('M_CH_sim_mesh_material', 'MI_Cal_Mesh')
MAX_BONES = 65535               # bone map entries are u16
MAX_INFLUENCES = 12             # UE5 allows 12; Tekken 8's meshes have 8
STRIDE_POSITION = 12            # float3


class Reader:
    """Little-endian reads in pkg.data[start:end]."""

    def __init__(self, pkg, start, end):
        self.pkg, self.b, self.p, self.end = pkg, pkg.data, start, end

    def take(self, fmt):
        size = struct.calcsize(fmt)
        if self.p + size > self.end:
            raise ParseError('%s: mesh data ends at %#x, %d bytes wanted at %#x' % (self.pkg.name, self.end, size,
                                                                                   self.p))
        v = struct.unpack_from('<' + fmt, self.b, self.p)
        self.p += size
        return v

    def u8(self):
        return self.take('B')[0]

    def u16(self):
        return self.take('H')[0]

    def i16(self):
        return self.take('h')[0]

    def u32(self):
        return self.take('I')[0]

    def i32(self):
        return self.take('i')[0]

    def bool32(self):
        v = self.u32()
        if v > 1:
            raise ParseError('%s: bool %d at %#x' % (self.pkg.name, v, self.p - 4))
        return bool(v)

    def strip(self):
        return self.take('BB')

    def fname(self):
        i, n = self.take('II')
        return self.pkg.mapped_name(i, n)

    def count(self, limit=1 << 27):
        n = self.i32()
        if not 0 <= n <= limit:
            raise ParseError('%s: count %d at %#x' % (self.pkg.name, n, self.p - 4))
        return n

    def array(self, dtype, n):
        dt = np.dtype(dtype)
        if self.p + dt.itemsize * n > self.end:
            raise ParseError('%s: an array of %d x %d bytes at %#x runs past the mesh data' % (
                self.pkg.name, n, dt.itemsize, self.p))
        a = np.frombuffer(self.b, dt, n, self.p).copy()
        self.p += dt.itemsize * n
        return a

    def tarray(self, dtype):
        return self.array(dtype, self.count())

    def bulk(self, dtype):
        """TArray::BulkSerialize: i32 element size, i32 count, the elements."""
        size, n = self.take('ii')
        dt = np.dtype(dtype)
        if size != dt.itemsize or n < 0:
            raise ParseError('%s: bulk array of %d x %d bytes at %#x, expected elements of %d' % (
                self.pkg.name, n, size, self.p - 8, dt.itemsize))
        return self.array(dt, n)


# ------------------------------------------------------------------------------------------------ sections, LODs
class Section:
    __slots__ = ('material_index', 'base_index', 'num_triangles', 'base_vertex', 'num_vertices', 'bone_map',
                 'max_influences', 'disabled', 'cloth_mapping', 'cloth_section', 'cloth_asset')


def _section(r):
    s = Section()
    r.strip()
    s.material_index = r.u16()
    s.base_index = r.u32()
    s.num_triangles = r.u32()
    r.bool32()                                 # recompute tangent
    r.u8()                                     # its mask channel
    r.bool32()                                 # cast shadow
    r.bool32()                                 # visible in ray tracing
    s.base_vertex = r.u32()
    mapped = 0
    for _ in range(r.count(64)):               # cloth mapping per LOD (Chaos cloth: Tekken 8 has none)
        n = r.count()
        r.array(np.dtype((np.void, 76)), n)
        mapped += n
    s.bone_map = r.tarray('<u2')
    s.num_vertices = r.u32()
    s.max_influences = r.i32()
    s.cloth_asset = r.i16()
    r.array('u1', 16)                          # clothing GUID
    r.i32()                                    # clothing LOD
    r.tarray('<u4')                            # duplicated vertices
    r.tarray('<2u4')
    s.disabled = r.bool32()
    s.cloth_mapping = mapped
    s.cloth_section = -1
    return s


class LOD:
    pass


def _lod(r, has_vertex_colors):
    lod = LOD()
    r.strip()
    cooked_out = r.bool32()
    inlined = r.bool32()
    r.tarray('<u2')                            # required bones
    if cooked_out:
        raise ParseError('%s: a LOD cooked out of the mesh' % r.pkg.name)
    lod.sections = [_section(r) for _ in range(r.count(4096))]
    r.tarray('<u2')                            # active bones
    r.u32()                                    # buffers' size
    if not inlined:
        raise ParseError('%s: LOD data in bulk data (not inline), which Tekken 8\'s fighter meshes do not have'
                         % r.pkg.name)
    r.strip()
    size = r.u8()
    if size not in (2, 4):
        raise ParseError('%s: index size %d' % (r.pkg.name, size))
    lod.indices = r.bulk('<u2' if size == 2 else '<u4').astype(np.uint32)
    stride, nv = r.u32(), r.u32()
    if stride != STRIDE_POSITION:
        raise ParseError('%s: position stride %d' % (r.pkg.name, stride))
    lod.positions = r.bulk('<3f4')
    if len(lod.positions) != nv:
        raise ParseError('%s: %d positions for %d vertices' % (r.pkg.name, len(lod.positions), nv))
    lod.num_vertices = nv
    r.strip()
    nuv, n2 = r.u32(), r.u32()
    full_uv, hp_tangents = r.bool32(), r.bool32()
    t = '<4i2' if hp_tangents else '<4i1'
    lod.tangent_scale = 32767.0 if hp_tangents else 127.0
    lod.tangents = r.bulk(np.dtype([('x', t), ('z', t)]))
    uv = r.bulk('<2f4' if full_uv else '<2f2')
    if n2 != nv or len(lod.tangents) != nv or len(uv) != nv * nuv:
        raise ParseError('%s: vertex buffer of %d vertices x %d UV sets for %d vertices' % (r.pkg.name, n2, nuv, nv))
    lod.uvs = uv.reshape(nv, nuv, 2).astype(np.float32)
    r.strip()
    variable = r.bool32()
    k = r.u32()
    r.u32()                                    # influences in all
    nw = r.u32()
    idx16, w16 = r.bool32(), r.bool32()
    raw = r.bulk('u1')
    if variable:
        raise ParseError('%s: variable skin influences (Tekken 8\'s fighter meshes have a fixed number)' % r.pkg.name)
    if not 1 <= k <= MAX_INFLUENCES or nw != nv:
        raise ParseError('%s: skin weights of %d vertices x %d influences for %d vertices' % (r.pkg.name, nw, k, nv))
    isz, wsz = 2 if idx16 else 1, 2 if w16 else 1
    if len(raw) != nv * k * (isz + wsz):
        raise ParseError('%s: %d bytes of skin weights for %d vertices' % (r.pkg.name, len(raw), nv))
    v = raw.reshape(nv, k * (isz + wsz))
    lod.bone_indices = v[:, :k * isz].copy().view('<u2' if idx16 else 'u1').astype(np.int32)
    lod.bone_weights = (v[:, k * isz:].copy().view('<u2' if w16 else 'u1').astype(np.float32) /
                        (65535.0 if w16 else 255.0))
    r.strip()
    r.u32()
    r.bulk('<u4')                              # lookup (variable influences only)
    lod.colors = None
    if has_vertex_colors:
        r.strip()
        stride, n = r.u32(), r.u32()
        lod.colors = r.bulk('<u4').view(np.uint8).reshape(-1, 4)
        if stride != 4 or n != nv or len(lod.colors) != nv:
            raise ParseError('%s: colour buffer of %d for %d vertices' % (r.pkg.name, n, nv))
    if r.count(64):
        raise ParseError('%s: skin weight profiles (not read)' % r.pkg.name)
    r.array('u1', r.count())                   # ray tracing data
    r.u32()
    return lod


# ------------------------------------------------------------------------------------------------ the mesh
class SkeletalMesh:
    """store: tekken8.store.Store; path: the mesh's package ('/Game/...' or 'Polaris/Content/....uasset')."""

    def __init__(self, store, path):
        pkg = self.package = store.package(path)
        self.export = pkg.find_export('SkeletalMesh') or pkg.main_export()
        e = self.export
        self.name = e.name
        self.props, start = uprops.read_object(pkg, e)
        r = Reader(pkg, e.offset + start, e.offset + e.size)
        r.strip()
        self.bounds = r.take('7d')
        self.materials = []
        for _ in range(r.count(1024)):
            ref = r.i32()
            slot = r.fname()
            r.u32()
            r.take('II4f')                     # UV channel info
            self.materials.append({'material': pkg.reference(ref), 'slot': slot})
        bones = [(r.fname(), r.i32()) for _ in range(r.count(MAX_BONES))]
        n = r.count(MAX_BONES)
        pose = r.array('<f8', 10 * n).reshape(n, 10)
        for _ in range(r.count(MAX_BONES)):
            r.fname(), r.i32()
        if n != len(bones):
            raise ParseError('%s: reference pose of %d bones, skeleton %d' % (pkg.name, n, len(bones)))
        for i, (_, parent) in enumerate(bones):
            if not -1 <= parent < i or (parent < 0) != (i == 0):
                raise ParseError('%s: bone %d has parent %d' % (pkg.name, i, parent))
        self.skeleton = {'names': [b[0] for b in bones], 'parents': [b[1] for b in bones], 'pose': pose}
        r.bool32()                             # cooked
        has_colors = bool(self.props.get('bHasVertexColors', False))
        self.lods = [_lod(r, has_colors) for _ in range(r.count(16))]
        if not self.lods:
            raise ParseError('%s: no LOD' % pkg.name)
        for lod in self.lods:
            for s in lod.sections:
                ref = self.materials[s.material_index]['material'] if s.material_index < len(self.materials) \
                    else None
                if zen.short_name(ref) in SIM_MATERIALS:
                    s.cloth_mapping = max(s.cloth_mapping, 1)

    def material_name(self, index):
        """A material slot's material by its own name ('MI_CH_zbr_bdu_1p_sleeve'), 'None' without one."""
        ref = self.materials[index]['material'] if 0 <= index < len(self.materials) else None
        return zen.short_name(ref) if ref else 'None'

    def geometry(self, lod_index=0):
        """Vertex streams of a LOD (float32): positions (cm), normals, tangents (xyz + bitangent sign), uvs (n, sets,
        2), weights (n, influences, 0..1); joints (reference-skeleton bones) and the triangles of each section."""
        lod = self.lods[lod_index]
        tx = lod.tangents['x'].astype(np.float32) / lod.tangent_scale
        tz = lod.tangents['z'].astype(np.float32) / lod.tangent_scale
        normal = tz[:, :3] / np.maximum(np.linalg.norm(tz[:, :3], axis=1, keepdims=True), 1e-8)
        tangent = tx[:, :3] / np.maximum(np.linalg.norm(tx[:, :3], axis=1, keepdims=True), 1e-8)
        sign = np.where(tz[:, 3] < 0, -1.0, 1.0).astype(np.float32)
        local = lod.bone_indices
        joints = np.zeros(local.shape, np.int32)
        covered = np.zeros(lod.num_vertices, bool)
        for si, s in enumerate(lod.sections):
            a, b = s.base_vertex, s.base_vertex + s.num_vertices
            bm = s.bone_map.astype(np.int32)
            used = local[a:b][lod.bone_weights[a:b] > 0]
            if used.size and (used.max() >= len(bm) or bm[used].max() >= len(self.skeleton['names'])):
                raise ParseError('%s: section %d skins to a bone outside its bone map or the skeleton' % (
                    self.name, si))
            joints[a:b] = bm[np.minimum(local[a:b], max(len(bm) - 1, 0))] if len(bm) else 0
            covered[a:b] = True
        tris = []
        for si, s in enumerate(lod.sections):
            t = lod.indices[s.base_index:s.base_index + 3 * s.num_triangles]
            if len(t) != 3 * s.num_triangles or (len(t) and int(t.max()) >= lod.num_vertices):
                raise ParseError('%s: section %d has triangles outside the mesh' % (self.name, si))
            tris.append(t.reshape(-1, 3))
        if not covered.all():
            raise ParseError('%s: %d vertices in no section' % (self.name, int((~covered).sum())))
        return {'positions': lod.positions.astype(np.float32), 'normals': normal,
                'tangents': np.concatenate([tangent, sign[:, None]], 1), 'uvs': lod.uvs, 'joints': joints,
                'weights': lod.bone_weights.astype(np.float32), 'triangles': tris}
