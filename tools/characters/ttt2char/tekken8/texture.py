"""Cooked UTexture2D (Unreal Engine 5.2) from Tekken 8.

The export's data, after the unversioned properties (ImportedSize, LODGroup, SRGB (default True: missing = sRGB, a
zero = linear), CompressionSettings, ...):
    u32 bSerializeGuid (0), FStripDataFlags UTexture (u8 global, u8 class), FStripDataFlags UTexture2D, u32 bCooked (1)
    per platform data: FName pixel format ('None' ends the list), i64 SkipOffset (counted from its own position: where
        the next FName is), 16 bytes (derived data placeholder, zero), i32 SizeX, i32 SizeY, u32 PackedData (bits 0-29
        slices, bit 30 OptData follows, bit 31 cube map), FString pixel format ('PF_BC7'), [OptData: u32 ExtData,
        u32 NumMipsInTail], i32 FirstMipToSerialize, i32 NumMips,
        mips: i32 bulk data map index, [the payload, when that entry is inline (BULK_INLINE)], i32 SizeX, SizeY, SizeZ
        u32 bIsVirtual (virtual textures are not read)
A mip's bytes are where the package's bulk data map entry says (zen.py): inline in the export, or in the package's
.ubulk chunk. Tekken 8 keeps most character textures inline (2-16 MB packages; the top mip and its chain), newer
(patch) textures put their large mips in the .ubulk. Only what is used is read (the containers decompress in 64 KB
blocks): the package header, the export up to its first inline mip, the few bytes around each mip's payload that say
its size, and the payload of the mip decoded; a 1024 mip of a 2048 texture reads about a quarter of its package. Some
textures do not cook their top mip (T_CH_zbr_fac_VM: 1024 x 1024 by its size, mips from 512): a mip's own size is
the one used.

Character formats seen: BC7 sRGB (face colour, eyes, hair), DXT1 (costume colour and mask maps), BC5 (normal maps:
R = X, G = Y, as Tekken 7's), DXT5 (scalp masks, in alpha), G8 (hair root maps), B8G8R8A8 (ID maps: one mip).

Written for this project from the files themselves (no third-party code).
"""
import struct

import numpy as np

from .. import bc
from . import uprops, zen

PF_NONE = 'None'
OPT_DATA, CUBE = 1 << 30, 1 << 31            # PackedData bits
SLICES = (1 << 30) - 1
WINDOW = 4096                                # bytes a read past the export's head takes at once (a mip's size, the
                                             # next one's index and the small mips' payloads come in one)


def _decode_rgba8(data, w, h):
    return np.frombuffer(data, np.uint8, count=w * h * 4).reshape(h, w, 4).copy()


def _decode_g16(data, w, h):
    a = (np.frombuffer(data, '<u2', count=w * h).reshape(h, w) >> 8).astype(np.uint8)
    return np.stack([a, a, a, np.full_like(a, 255)], -1)


def _decode_rgba16f(data, w, h):
    a = np.frombuffer(data, '<f2', count=w * h * 4).reshape(h, w, 4).astype(np.float32)
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


# pixel formats Tekken 8 has beyond bc.DECODERS' (UI and effect textures)
DECODERS = dict(bc.DECODERS, PF_R8G8B8A8=_decode_rgba8, PF_G16=_decode_g16, PF_FloatRGBA=_decode_rgba16f)


class Mip:
    __slots__ = ('width', 'height', 'depth', 'bulk', 'data')

    def __init__(self, width, height, depth, bulk, data):
        self.width, self.height, self.depth, self.bulk, self.data = width, height, depth, bulk, data

    def __repr__(self):
        return '<mip %dx%d>' % (self.width, self.height)


class _Data:
    """A reader over an export's bytes at absolute package offsets: from `head` (the package read up to the first
    inline mip) where it has them, beyond it through small reads of the package file; skip() passes over a payload
    without reading it."""

    def __init__(self, store, file, head, name, start, end):
        self.store, self.file, self.head, self.name, self.p, self.end = store, file, head, name, start, end
        self.window = (0, b'')                       # the last small read beyond the head: (offset, bytes)

    def bytes(self, at, size):
        if at + size <= len(self.head):
            return self.head[at:at + size]
        w0, w = self.window
        if not (w0 <= at and at + size <= w0 + len(w)):
            w = self.store.read(self.file, at, max(size, min(WINDOW, self.end - at)))
            if len(w) < size:
                raise zen.ParseError('%s: texture data runs past its package' % self.name)
            self.window = (w0, w) = (at, w)
        return w[at - w0:at - w0 + size]

    def take(self, fmt, size):
        if self.p + size > self.end:
            raise zen.ParseError('%s: texture data runs past its export' % self.name)
        v = struct.unpack(fmt, self.bytes(self.p, size))
        self.p += size
        return v

    def skip(self, size):
        if self.p + size > self.end:
            raise zen.ParseError('%s: texture data runs past its export' % self.name)
        self.p += size

    def i32(self):
        return self.take('<i', 4)[0]

    def u32(self):
        return self.take('<I', 4)[0]

    def fname(self, pkg):
        i, n = self.take('<II', 8)
        return pkg.mapped_name(i, n)

    def fstring(self):
        n = self.i32()
        if n < 0:
            return bytes(self.take('<%ds' % (-2 * n), -2 * n)[0]).decode('utf-16-le').rstrip('\0')
        return bytes(self.take('<%ds' % n, n)[0]).decode('utf-8', 'replace').rstrip('\0') if n else ''


def _head(ex, size):
    """An export cut to its first `size` bytes (what uprops.read sees of a texture: its properties come first)."""
    e = zen.Export()
    for k in zen.Export.__slots__:
        setattr(e, k, getattr(ex, k))
    e.size, e._data = size, None
    return e


class Texture2D:
    def __init__(self, store, path):
        """store: store.Store; path: the texture's package or object path."""
        self.store, self.path = store, path
        file = self.file = store.file_path(path)
        pid = store.package_id(path) if file else None
        header = store.package_header(pid) if pid is not None else None
        if header is None:
            raise KeyError(path)
        pkg = zen.Package(header, file, pid, store.resolver, store)
        ex = pkg.find_export('Texture2D') or pkg.main_export()
        if ex is None or ex.class_name != 'Texture2D':
            raise zen.ParseError('%s is not a Texture2D' % path)
        inline = [e.offset for e in pkg.bulk_map if e.flags & zen.BULK_INLINE and not e.flags & zen.BULK_SEPARATE and
                  0 < e.offset < ex.size]
        head = store.read(file, 0, ex.offset + min(inline + [ex.size]))
        pkg = self.pkg = zen.Package(head, file, pid, store.resolver, store)
        ex = self.export = pkg.exports[ex.index]
        self.name = ex.name
        self.props, end = uprops.read(pkg, _head(ex, len(head) - ex.offset))
        r = _Data(store, file, head, self.name, ex.offset + end, ex.offset + ex.size)
        if r.u32():
            r.take('<16s', 16)                       # an object GUID (none in cooked textures)
        r.take('<4B', 4)                             # strip flags: UTexture, UTexture2D
        if not r.u32():
            raise zen.ParseError('%s is not a cooked texture' % self.name)
        self.pixel_format, self.mips, self.width, self.height = None, [], 0, 0
        while True:
            pf = r.fname(pkg)
            if pf == PF_NONE:
                break
            at = r.p
            skip = r.take('<q', 8)[0]
            r.take('<16s', 16)
            sx, sy, packed = r.take('<iiI', 12)
            fmt = r.fstring()
            if packed & OPT_DATA:
                r.take('<II', 8)
            r.i32()                                  # FirstMipToSerialize
            mips = []
            for _ in range(r.i32()):
                index = r.i32()
                if not 0 <= index < len(pkg.bulk_map):
                    raise zen.ParseError('%s: mip bulk data index %d beyond the map' % (self.name, index))
                e = pkg.bulk_map[index]
                if e.flags & zen.BULK_INLINE and not e.flags & zen.BULK_SEPARATE:
                    if ex.offset + e.offset != r.p:
                        raise zen.ParseError('%s: inline mip at %#x, its bulk entry says %#x' % (
                            self.name, r.p - ex.offset, e.offset))
                    r.skip(e.size)
                w, h, d = r.take('<iii', 12)
                mips.append(Mip(w, h, d, e, None))
            if r.u32():
                raise NotImplementedError('%s is a virtual texture' % self.name)
            if at + skip != r.p:
                raise zen.ParseError('%s: platform data ends at %#x, its offset says %#x' % (self.name, r.p, at + skip))
            if self.pixel_format is None:            # the first platform's (PC has one)
                self.pixel_format, self.mips, self.width, self.height = fmt, mips, sx, sy
        if self.pixel_format is None:
            raise zen.ParseError('%s has no platform data' % self.name)
        self.mips = [m for m in self.mips if m.bulk.size > 0 and not m.bulk.flags & zen.BULK_UNUSED]
        if not self.mips:
            raise zen.ParseError('%s: no mip has data' % self.name)

    @property
    def srgb(self):
        return bool(self.props.get('SRGB', True))

    def level(self, max_size=None):
        """The index of the largest mip whose longest side is at most max_size (None: the top one; the smallest when
        none is that small, as an ID map's only mip)."""
        if max_size is not None:
            for i, m in enumerate(self.mips):
                if max(m.width, m.height) <= max_size:
                    return i
            return len(self.mips) - 1
        return 0

    def mip_bytes(self, m):
        """A mip's payload (its own bytes alone are read, from the package or its .ubulk)."""
        if m.data is None:
            e = m.bulk
            if e.flags & zen.BULK_ZLIB or e.flags & zen.BULK_AT_END and not e.flags & zen.BULK_SEPARATE:
                raise NotImplementedError('%s: mip bulk data with flags %#x' % (self.name, e.flags))
            if e.flags & zen.BULK_SEPARATE:
                ctype = (zen.CHUNK_OPTIONAL_BULK if e.flags & zen.BULK_OPTIONAL else
                         zen.CHUNK_MEMORY_MAPPED_BULK if e.flags & zen.BULK_MEMORY_MAPPED else zen.CHUNK_BULK)
                m.data = self.store.chunk(self.pkg.package_id, ctype, 0, e.offset, e.size)
            else:
                m.data = self.store.read(self.file, self.export.offset + e.offset, e.size)
            if len(m.data) != e.size:
                raise zen.ParseError('%s: mip data lies past its package or bulk chunk' % self.name)
        return m.data

    def decode(self, max_size=None):
        """The largest mip whose longest side is at most max_size (None: the top one) as an (H, W, 4) uint8 RGBA
        array."""
        m = self.mips[self.level(max_size)]
        fn = DECODERS.get(self.pixel_format)
        if fn is None:
            raise NotImplementedError('%s: texture pixel format %s is not supported' % (self.name, self.pixel_format))
        return fn(self.mip_bytes(m), m.width, m.height)
