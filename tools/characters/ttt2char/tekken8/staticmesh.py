"""Cooked UStaticMesh of Tekken 8 (Unreal Engine 5): the first LOD's triangles, positions, normals, UVs and vertex
colours, for its effects' mesh particles (rings, tornados, wind shards, planes; convert/effects8.py). The interface is
tekken7/staticmesh.py's.

The render data follows the properties; its first LOD's buffers are found by the position buffer's header (u32 stride
12, u32 count n, then its bulk array: u32 element size 12, u32 count n, n x FVector3f), and read on from there:
    vertices: FStripDataFlags (2 bytes), u32 UV sets, u32 count, u32 full-precision UVs, u32 high-precision tangents,
        bulk array of {tangent X, tangent Z} (FPackedNormal: 4 x int8 / 127; 8 bytes a vertex), bulk array of UVs
        (half2 or float2 per set)
    colours: FStripDataFlags, u32 stride (0 or 4), u32 count, [bulk array of FColor (B, G, R, A)]
    indices: u32 32-bit, bulk array of bytes (u16 or u32 indices)
Units are centimetres, Z up.

Written for this project from the files themselves (no third-party code).
"""
import struct

import numpy as np

from . import uprops

MAX_VERTICES = 1 << 20


class StaticMesh:
    def __init__(self, store, path):
        self.pkg = pkg = store.package(path.split('.')[0])
        self.export = ex = next((e for e in pkg.exports if e.class_name == 'StaticMesh'), None)
        if ex is None:
            raise KeyError('%s has no static mesh' % path)
        self.name = ex.name
        props, end = uprops.read(pkg, ex)
        self.materials = [m.get('MaterialInterface') for m in props.get('StaticMaterials') or []]
        b = pkg.data[ex.offset:ex.offset + ex.size]
        at = next((o for o in range(end, len(b) - 16) if _position_header(b, o)), None)
        if at is None:
            raise ValueError('%s: no vertex positions found' % self.name)
        n = struct.unpack_from('<I', b, at + 4)[0]
        q = at + 16
        self.positions = np.frombuffer(b, '<f4', 3 * n, q).reshape(n, 3).astype(np.float32)
        q += 12 * n + 2
        sets, count, full, precise = struct.unpack_from('<4I', b, q)
        q += 16
        if count != n or not 0 < sets <= 8:
            raise ValueError('%s: %d vertices, %d UV sets for %d positions' % (self.name, count, sets, n))
        size, k = struct.unpack_from('<2I', b, q)
        q += 8
        if size != (16 if precise else 8) or k != n:
            raise ValueError('%s: tangent element %d x %d' % (self.name, size, k))
        tangents = np.frombuffer(b, '<i2' if precise else 'i1', 8 * n, q).reshape(n, 2, 4).astype(np.float32)
        tangents /= 32767.0 if precise else 127.0
        q += size * n
        size, k = struct.unpack_from('<2I', b, q)
        q += 8
        uv_type = '<f4' if full else '<f2'
        if size * k != n * sets * 2 * (4 if full else 2):
            raise ValueError('%s: UV data %d x %d' % (self.name, size, k))
        self.uvs = np.frombuffer(b, uv_type, n * sets * 2, q).reshape(n, sets, 2).astype(np.float32)
        q += size * k + 2
        stride, k = struct.unpack_from('<2I', b, q)
        q += 8
        self.colors = None
        if k:
            size, k2 = struct.unpack_from('<2I', b, q)
            q += 8
            if size != 4 or k2 != n:
                raise ValueError('%s: colour element %d x %d' % (self.name, size, k2))
            self.colors = np.frombuffer(b, 'u1', 4 * n, q).reshape(n, 4)[:, [2, 1, 0, 3]].copy()
            q += 4 * n
        wide, size, k = struct.unpack_from('<3I', b, q)
        q += 12
        self.indices = np.frombuffer(b, '<u4' if wide else '<u2', size * k // (4 if wide else 2), q).astype(np.uint32)
        if not len(self.indices) or len(self.indices) % 3 or self.indices.max() >= n:
            raise ValueError('%s: %d indices for %d vertices' % (self.name, len(self.indices), n))
        nz = tangents[:, 1, :3]
        self.normals = nz / np.maximum(np.linalg.norm(nz, axis=1, keepdims=True), 1e-8)

    def triangles(self):
        """[(material slot, (k, 3) vertex indices)]: one section (the effect meshes have one)."""
        return [(0, self.indices.reshape(-1, 3))]


def _position_header(b, o):
    s, n, size, k = struct.unpack_from('<4I', b, o)
    return s == 12 and size == 12 and n == k and 0 < n < MAX_VERTICES and o + 16 + 12 * n <= len(b)
