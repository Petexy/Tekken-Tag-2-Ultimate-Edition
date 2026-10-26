"""Tekken 8's cooked Unreal Engine 5 packages ("zen" packages in IoStore containers), read-only.

A package is one chunk (type 1, ExportBundleData: the .uasset of the containers' directory index); its chunk id is
its package id (cityhash.package_id of its name). Layout (UE 5.1/5.2, every Tekken 8 package):
    FZenPackageSummary (44 bytes): u32 bHasVersioningInfo (0: unversioned), u32 HeaderSize, FMappedName Name
        (the package name, '/Game/...'), u32 PackageFlags, u32 CookedHeaderSize, i32 offsets of the imported
        public export hashes, the import map, the export map, the export bundle entries and the graph data
    name map (a name batch) at 44: u32 count, [u32 string bytes, u64 hash version, u64 hashes[count], u16
        big-endian headers[count] (bit 15 UTF-16, low 15 bits length), the strings back to back (Latin-1 or
        UTF-16LE, not aligned)]; FMappedName / FName = u32 index (low 30 bits) + u32 number (n > 0: '<name>_<n-1>')
    bulk data map (UE 5.2): i64 byte size, FBulkDataMapEntry[] (32 bytes: i64 SerialOffset, i64
        DuplicateSerialOffset, i64 SerialSize, u32 Flags, u32 pad)
    u64 ImportedPublicExportHashes[]; FPackageObjectIndex ImportMap[] (u64: bits 62-63 type: 0 export (an
        export's index), 1 script import (cityhash.script_object_id), 2 package import (bits 32-61 imported package
        index, bits 0-31 index into the public export hashes), all bits set: null)
    FExportMapEntry[] (72 bytes): u64 CookedSerialOffset, u64 CookedSerialSize, FMappedName ObjectName,
        FPackageObjectIndex Outer, Class, Super, Template, u64 PublicExportHash, u32 ObjectFlags, u8 FilterFlags,
        3 pad
    FExportBundleEntry[] (8 bytes): u32 export index, u32 command (0 create, 1 serialize)
    graph data up to HeaderSize: FExportBundleHeader[] {u64 SerialOffset, u32 FirstEntryIndex, u32 EntryCount}
        (as many as cover the bundle entries), i32 n + n x {i32 from bundle, i32 to bundle}, then per imported
        package i32 n + n x {i32 import index, u8 command, i32 to bundle} (9 bytes)
    export data, from HeaderSize: the exports in the order of the bundles' serialize entries, a bundle's first
        at HeaderSize + its SerialOffset (CookedSerialOffset is the cooker's legacy layout: in most multi-export
        packages the order differs, and the bundle order is the one the data has)
Property data refers to objects by FPackageIndex (i32: 0 null, < 0 import -i-1, > 0 export i-1).

Bulk data (texture mips, ...): a bulk data map entry with flag 0x100 (PayloadInSeperateFile) is in the package's
.ubulk (chunk type 2; 0x800 Optional: .uptnl type 3; 0x1000 MemoryMapped: .m.ubulk type 4) at SerialOffset; one
with 0x40 (ForceInlinePayload) is inside the export that serialises it (right after the entry's index, an i32),
SerialOffset counted from that export's start; size 0 or 0x20 (Unused) is empty.

Imports are resolved store-wide (Resolver): the imported packages' ids are in the store entry of the container
header (chunk type 6) of the container holding the package: 'IoCn' (0x496f436e), u32 version (2), u64 container
id, TArray<u64> package ids, TArray<u8> store entries (24 bytes each: i32 export count, i32 export bundle count,
{u32 n, u32 offset from this field} imported package ids, {u32 n, u32 offset} shader map hashes); an import names
the export of that package whose PublicExportHash is the one it lists. Script imports (the exe's classes and
their default objects) are named by global.utoc's ScriptObjects chunk (type 5): a name batch, i32 n, n x {FMappedName
name, u64 global index, u64 outer index, u64 CDO class index}.

Object paths are Unreal's: '/Game/Dir/Package.Object', a sub-object of an asset after ':' ('...Package.Object:Sub'),
deeper ones after '.'; script objects '/Script/Engine.Texture2D'.

Written for this project from the files themselves (no third-party code).
"""
import struct

SUMMARY_SIZE = 44
EXPORT_ENTRY_SIZE = 72
BULK_ENTRY_SIZE = 32
BUNDLE_ENTRY_SIZE = 8
SERIALIZE = 1                              # FExportBundleEntry command (0 create)
EXTERNAL_ARC_SIZE = 9
NULL_INDEX = 0xFFFFFFFFFFFFFFFF
NAME_INDEX_MASK = 0x3FFFFFFF               # FMappedName: bits 30-31 say which name map (package / global)
CONTAINER_HEADER_MAGIC = 0x496f436e        # 'nCoI' as stored
STORE_ENTRY_SIZE = {2: 24, 3: 16}          # container header version -> store entry size (3 dropped the counts)
CHUNK_EXPORT_BUNDLE, CHUNK_BULK, CHUNK_OPTIONAL_BULK, CHUNK_MEMORY_MAPPED_BULK = 1, 2, 3, 4
CHUNK_SCRIPT_OBJECTS, CHUNK_CONTAINER_HEADER = 5, 6
BULK_AT_END, BULK_ZLIB, BULK_UNUSED, BULK_INLINE = 0x1, 0x2, 0x20, 0x40
BULK_SEPARATE, BULK_OPTIONAL, BULK_MEMORY_MAPPED = 0x100, 0x800, 0x1000
HEADER_PEEK = 65536                        # bytes read to get an imported package's header (one IoStore block)


class ParseError(Exception):
    pass


def read_name_batch(b, p):
    """A name batch at b[p:] -> (names, end offset)."""
    n, = struct.unpack_from('<I', b, p)
    p += 4
    if n == 0:
        return [], p
    nbytes, = struct.unpack_from('<I', b, p)
    p += 4 + 8 + 8 * n                       # string bytes, hash version, hashes
    headers = b[p:p + 2 * n]
    p += 2 * n
    start = s = p
    names = []
    for i in range(n):
        h = (headers[2 * i] << 8) | headers[2 * i + 1]
        length = h & 0x7FFF
        if h & 0x8000:
            names.append(b[s:s + 2 * length].decode('utf-16-le'))
            s += 2 * length
        else:
            names.append(b[s:s + length].decode('latin-1'))
            s += length
    if s > start + nbytes:
        raise ParseError('name batch strings run past their size')
    return names, start + nbytes


def index_type(v):
    """FPackageObjectIndex -> 'export', 'script', 'package' or None (null)."""
    if v == NULL_INDEX:
        return None
    return ('export', 'script', 'package', None)[v >> 62]


def join_path(package, parts):
    """'/Game/X/Pkg' + ['Obj', 'Sub', 'Deeper'] -> '/Game/X/Pkg.Obj:Sub.Deeper'."""
    if not parts:
        return package
    out = (package + '.' if package else '') + parts[0]
    if len(parts) > 1:
        out += ':' + parts[1] + ''.join('.' + p for p in parts[2:])
    return out


def short_name(path):
    """The object's own name in an object path ('/Script/Engine.Texture2D' -> 'Texture2D')."""
    if path is None:
        return None
    for sep in ':.':
        path = path.rsplit(sep, 1)[-1]
    return path.rsplit('/', 1)[-1]


# ---------------------------------------------------------------------------------------------------- packages
class Export:
    __slots__ = ('package', 'index', 'name', 'outer_index', 'class_index', 'super_index', 'template_index',
                 'public_hash', 'object_flags', 'filter_flags', 'cooked_offset', 'size', 'offset', '_data',
                 '_class_path')

    def __repr__(self):
        return '<export %d %s : %s, %d bytes at %#x>' % (self.index, self.name, self.class_name, self.size,
                                                         self.offset)

    @property
    def outer(self):
        """The export this one is inside, or None (a package-level object)."""
        if index_type(self.outer_index) == 'export':
            return self.package.exports[self.outer_index]
        return None

    @property
    def relative_path(self):
        """Its outer chain below the package: ['Obj', 'Sub']."""
        parts, e, seen = [], self, set()
        while e is not None and e.index not in seen:
            seen.add(e.index)
            parts.append(e.name)
            e = e.outer
        return parts[::-1]

    @property
    def path(self):
        return join_path(self.package.name, self.relative_path)

    @property
    def class_path(self):
        if self._class_path is None:
            self._class_path = self.package.index_path(self.class_index) or ''
        return self._class_path or None

    @property
    def class_name(self):
        return short_name(self.class_path)

    @property
    def data(self):
        """The export's serialised bytes."""
        if self._data is None:
            if self.offset + self.size > len(self.package.data):
                raise ParseError('%s: export %s lies past the data read (%d bytes)' % (
                    self.package.name, self.name, len(self.package.data)))
            self._data = bytes(self.package.data[self.offset:self.offset + self.size])
        return self._data


class BulkEntry:
    __slots__ = ('index', 'offset', 'duplicate_offset', 'size', 'flags')

    def __repr__(self):
        return '<bulk %d: %d bytes at %d, flags %#x>' % (self.index, self.size, self.offset, self.flags)


class Package:
    def __init__(self, data, path=None, package_id=None, resolver=None, store=None):
        """data: the package chunk (at least its header); path: its file path in the store; resolver
        (Resolver) names imports; store (store.Store) gives bulk data chunks."""
        b = self.data = data
        if len(b) < SUMMARY_SIZE:
            raise ParseError('%s: too short for a package' % path)
        (self.has_versioning, self.header_size, ni, nn, self.flags, self.cooked_header_size, o_hashes, o_imports,
         o_exports, o_bundles, o_graph) = struct.unpack_from('<11I', b, 0)
        self.path, self.package_id, self.resolver, self.store = path, package_id, resolver, store
        if self.has_versioning:
            raise ParseError('%s: a versioned package (Tekken 8 cooks them unversioned)' % path)
        if not (SUMMARY_SIZE <= o_hashes <= o_imports <= o_exports <= o_bundles <= o_graph <= self.header_size
                <= len(b)):
            raise ParseError('%s: the package summary is not Unreal Engine 5.1/5.2\'s' % path)
        self.names, p = read_name_batch(b, SUMMARY_SIZE)
        self.name = self.mapped_name(ni, nn)
        self.bulk_map = []
        if p < o_hashes:
            size, = struct.unpack_from('<q', b, p)
            p += 8
            for i in range(size // BULK_ENTRY_SIZE):
                e = BulkEntry()
                e.index = i
                e.offset, e.duplicate_offset, e.size, e.flags = struct.unpack_from('<qqqI', b, p + BULK_ENTRY_SIZE * i)
                self.bulk_map.append(e)
            p += size
        if p != o_hashes:
            raise ParseError('%s: name and bulk data maps end at %#x, the export hashes start at %#x' % (
                path, p, o_hashes))
        self.imported_hashes = struct.unpack_from('<%dQ' % ((o_imports - o_hashes) // 8), b, o_hashes)
        self.import_map = struct.unpack_from('<%dQ' % ((o_exports - o_imports) // 8), b, o_imports)
        self.exports = []
        for i in range((o_bundles - o_exports) // EXPORT_ENTRY_SIZE):
            e = Export()
            (e.cooked_offset, e.size, eni, enn, e.outer_index, e.class_index, e.super_index, e.template_index,
             e.public_hash, e.object_flags, e.filter_flags) = struct.unpack_from(
                '<QQIIQQQQQIB', b, o_exports + EXPORT_ENTRY_SIZE * i)
            e.package, e.index, e.name = self, i, self.mapped_name(eni, enn)
            e.offset = self.header_size + e.cooked_offset - self.cooked_header_size     # unless a bundle has it
            e._data = e._class_path = None
            self.exports.append(e)
        self.bundle_entries = [struct.unpack_from('<II', b, o_bundles + BUNDLE_ENTRY_SIZE * i)
                               for i in range((o_graph - o_bundles) // BUNDLE_ENTRY_SIZE)]
        self._graph(o_graph)
        for serial_offset, first, count in self.bundles:
            at = self.header_size + serial_offset
            for i, command in self.bundle_entries[first:first + count]:
                if command == SERIALIZE and i < len(self.exports):
                    self.exports[i].offset = at
                    at += self.exports[i].size
        self._imports = None
        self._bulk_chunks = {}

    def __repr__(self):
        return '<package %s: %d exports, %d imports>' % (self.name, len(self.exports), len(self.import_map))

    def mapped_name(self, index, number):
        i = index & NAME_INDEX_MASK
        if i >= len(self.names):
            raise ParseError('%s: name index %d beyond the %d names' % (self.path, i, len(self.names)))
        s = self.names[i]
        return s if number == 0 else '%s_%d' % (s, number - 1)

    def _graph(self, p):
        b, end = self.data, self.header_size
        self.bundles = []
        covered = 0
        while covered < len(self.bundle_entries):
            so, first, count = struct.unpack_from('<QII', b, p)
            if count == 0 or first != covered:
                raise ParseError('%s: export bundle headers do not cover the bundle entries' % self.path)
            self.bundles.append((so, first, count))
            covered += count
            p += 16
        n, = struct.unpack_from('<i', b, p)
        p += 4
        self.internal_arcs = [struct.unpack_from('<ii', b, p + 8 * i) for i in range(n)]
        p += 8 * n
        self.external_arcs = []
        while p < end:
            n, = struct.unpack_from('<i', b, p)
            p += 4
            self.external_arcs.append([struct.unpack_from('<iBi', b, p + EXTERNAL_ARC_SIZE * i) for i in range(n)])
            p += EXTERNAL_ARC_SIZE * n
        if p != end:
            raise ParseError('%s: the graph data runs past the header (%#x > %#x)' % (self.path, p, end))

    # ------------------------------------------------------------------------------------------- objects
    def index_path(self, v):
        """The object path an FPackageObjectIndex names (None for null)."""
        t = index_type(v)
        if t is None:
            return None
        if t == 'export':
            return self.exports[v].path if v < len(self.exports) else None
        if t == 'script':
            path = self.resolver.script_path(v) if self.resolver else None
            return path or 'script:%016x' % v
        pkg, obj = self.import_of(v)
        return join_path(pkg, obj.replace(':', '.').split('.')) if obj else pkg

    def import_of(self, v):
        """A package import (FPackageObjectIndex) -> (package name, object path below it, e.g. 'Obj' or 'Obj:Sub');
        names unknown to the store come out as '?<hex id>'."""
        pi, hi = (v >> 32) & NAME_INDEX_MASK, v & 0xFFFFFFFF
        h = self.imported_hashes[hi] if hi < len(self.imported_hashes) else 0
        if self.resolver is None:
            return 'package#%d' % pi, '?%016x' % h
        return self.resolver.import_of(self, pi, h)

    @property
    def imports(self):
        """The import map resolved: (package name, object path below it) for package imports, the script path
        ('/Script/Engine.Texture2D') for script imports, None for null entries."""
        if self._imports is None:
            out = []
            for v in self.import_map:
                t = index_type(v)
                if t == 'package':
                    out.append(self.import_of(v))
                elif t is None:
                    out.append(None)
                else:
                    out.append(self.index_path(v))
            self._imports = out
        return self._imports

    def import_path(self, i):
        """Import map entry i as an object path ('/Game/X/Pkg.Obj', '/Script/Engine.Texture2D'), or None."""
        return self.index_path(self.import_map[i]) if 0 <= i < len(self.import_map) else None

    def reference(self, index):
        """An FPackageIndex (as property data stores object references) -> object path, or None for 0."""
        if index == 0:
            return None
        if index < 0:
            return self.import_path(-index - 1)
        return self.exports[index - 1].path if index - 1 < len(self.exports) else None

    def find_export(self, class_name=None, name=None):
        """The first export of that class (short or full path) and/or name, or None."""
        for e in self.exports:
            if class_name is not None and class_name not in (e.class_name, e.class_path):
                continue
            if name is not None and e.name != name:
                continue
            return e
        return None

    def main_export(self):
        """The asset: the package-level export named like the package, else the first package-level export (not a
        class default object), else export 0."""
        base = self.name.rsplit('/', 1)[-1]
        top = [e for e in self.exports if e.outer is None]
        for e in top:
            if e.name == base:
                return e
        for e in top:
            if not e.name.startswith('Default__'):
                return e
        return self.exports[0] if self.exports else None

    # ------------------------------------------------------------------------------------------- bulk data
    def bulk(self, index, export=None):
        """Bulk data map entry `index`'s payload (bytes). An inline payload is inside `export` (default: the export
        that serialises it, bulk_owner), the others in the package's bulk chunk."""
        e = self.bulk_map[index]
        if e.size == 0 or e.flags & BULK_UNUSED:
            return b''
        if e.flags & BULK_ZLIB:
            raise NotImplementedError('%s: zlib-compressed bulk data (flags %#x)' % (self.name, e.flags))
        if e.flags & BULK_SEPARATE:
            ctype = (CHUNK_OPTIONAL_BULK if e.flags & BULK_OPTIONAL else
                     CHUNK_MEMORY_MAPPED_BULK if e.flags & BULK_MEMORY_MAPPED else CHUNK_BULK)
            chunk = self.bulk_chunk(ctype)
            if e.offset + e.size > len(chunk):
                raise ParseError('%s: bulk data %d lies past its chunk' % (self.name, index))
            return chunk[e.offset:e.offset + e.size]
        if e.flags & BULK_AT_END:
            raise NotImplementedError('%s: bulk data at the end of the package (flags %#x)' % (self.name, e.flags))
        x = export if export is not None else self.bulk_owner(e)
        if e.offset + e.size > x.size:
            raise ParseError('%s: inline bulk data %d lies outside export %s' % (self.name, index, x.name))
        return bytes(self.data[x.offset + e.offset:x.offset + e.offset + e.size])

    def bulk_owner(self, entry):
        """The export an inline payload is in: the one that has the entry's index (i32) right before it (the
        main export when that does not decide)."""
        main = self.main_export()
        hits = [x for x in self.exports if 4 <= entry.offset and entry.offset + entry.size <= x.size and
                x.offset + entry.offset <= len(self.data) and
                struct.unpack_from('<i', self.data, x.offset + entry.offset - 4)[0] == entry.index]
        if len(hits) == 1 or (hits and main not in hits):
            return hits[0]
        return main

    def bulk_chunk(self, chunk_type=CHUNK_BULK):
        """The package's bulk data chunk (2 .ubulk, 3 .uptnl, 4 .m.ubulk) as bytes (read once)."""
        if chunk_type not in self._bulk_chunks:
            if self.store is None or self.package_id is None:
                raise ParseError('%s: bulk data needs the store' % self.name)
            self._bulk_chunks[chunk_type] = self.store.chunk(self.package_id, chunk_type)
        return self._bulk_chunks[chunk_type]


# ---------------------------------------------------------------------------------------------------- store-wide
def script_objects(data):
    """global.utoc's ScriptObjects chunk -> {global index: object path ('/Script/Engine.Texture2D')}."""
    names, p = read_name_batch(data, 0)
    n, = struct.unpack_from('<i', data, p)
    p += 4
    raw = {}
    for i in range(n):
        ni, nn, gi, outer, _ = struct.unpack_from('<IIQQQ', data, p + 32 * i)
        s = names[ni & NAME_INDEX_MASK]
        raw[gi] = (s if nn == 0 else '%s_%d' % (s, nn - 1), outer)
    out = {}

    def path(gi):
        if gi in out:
            return out[gi]
        chain, g = [], gi
        while g in raw and len(chain) < 64:
            chain.append(raw[g][0])
            g = raw[g][1]
        chain.reverse()
        out[gi] = full = join_path(chain[0], chain[1:]) if chain[0].startswith('/') else join_path('', chain)
        return full
    for gi in raw:
        path(gi)
    return out


def container_header(data):
    """A container header chunk -> {package id: (export count, export bundle count, imported package ids)}
    (counts None from version 3 on)."""
    sig, version, _ = struct.unpack_from('<IIQ', data, 0)
    if sig != CONTAINER_HEADER_MAGIC:
        raise ParseError('not a container header')
    size = STORE_ENTRY_SIZE.get(version)
    if size is None:
        raise ParseError('container header version %d (Tekken 8 has 2)' % version)
    n, = struct.unpack_from('<i', data, 16)
    ids = struct.unpack_from('<%dQ' % n, data, 20)
    p = 20 + 8 * n
    nb, = struct.unpack_from('<i', data, p)
    p += 4
    out = {}
    for i, pid in enumerate(ids):
        q = p + size * i
        counts = (None, None)
        if size == 24:
            counts = struct.unpack_from('<ii', data, q)
            q += 8
        num, off = struct.unpack_from('<II', data, q)
        imported = struct.unpack_from('<%dQ' % num, data, q + off) if num else ()
        out[pid] = counts + (imported,)
    return out


class Resolver:
    """Names of imports and classes across the store. `store` gives: script_objects_data() -> bytes (global.utoc's
    ScriptObjects) or None, imported_package_ids(package id) -> its container header's list, package_name(package
    id) -> '/Game/...' or None, package_header(package id) -> bytes holding at least the package's header, or
    None."""

    def __init__(self, store):
        self.store = store
        self._scripts = None
        self._exports = {}

    def script_path(self, v):
        if self._scripts is None:
            d = self.store.script_objects_data()
            self._scripts = script_objects(d) if d else {}
        return self._scripts.get(v)

    def exports_of(self, pid):
        """(package name, {public export hash: object path below the package}) of a package id."""
        if pid not in self._exports:
            name, table = None, {}
            data = self.store.package_header(pid)
            if data is not None:
                try:
                    k = Package(data, package_id=pid)
                    name = k.name
                    for e in k.exports:
                        if e.public_hash:
                            table[e.public_hash] = join_path('', e.relative_path)
                except (ParseError, struct.error):
                    pass
            self._exports[pid] = (name or self.store.package_name(pid), table)
        return self._exports[pid]

    def import_of(self, pkg, package_index, export_hash):
        ids = self.store.imported_package_ids(pkg.package_id) if pkg.package_id is not None else ()
        if package_index >= len(ids):
            return '?package#%d' % package_index, '?%016x' % export_hash
        pid = ids[package_index]
        name, table = self.exports_of(pid)
        return name or '?%016x' % pid, table.get(export_hash, '?%016x' % export_hash)
