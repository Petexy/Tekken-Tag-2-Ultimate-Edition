"""Tekken 8 PC's pak files (version 11, Unreal Engine 5), read-only: the game's files that are not packages.

Most of Tekken 8's .pak files are stubs next to their IoStore containers; the real ones (pakchunk0-Windows.pak,
pakchunk50*, pakchunk500*) hold the Wwise sound banks and media (Polaris/Content/WwiseAudio/...) and other loose
files. A path in a `*_P.pak` patch pak replaces the same path in the base paks (higher patch numbers win).

    footer (last 221 bytes): FGuid encryption key (16), u8 index encrypted, u32 magic 0x5A6F12E1, i32 version (11),
        i64 index offset, i64 index size, 20-byte SHA-1 of the index, 5 x 32-byte compression method names (an
        entry numbers them from 1; 0 = stored)
    primary index: FString mount point ('../../../'), i32 entry count, u64 path hash seed, i32 has path hash index
        [i64 offset, i64 size, 20-byte hash], i32 has full directory index [i64 offset, i64 size, 20-byte hash],
        TArray<u8> encoded entries, i32 count + FPakEntry records of the entries that could not be encoded
    full directory index: i32 directories, each {FString directory below the mount point ('/', 'Polaris/.../'),
        i32 files, each {FString name, i32 location}}; location >= 0: byte offset into the encoded entries, < 0:
        -(i + 1) = index into the records, -2^31: deleted (a patch pak's way of removing the file)
    path hash index: i32 count, {u64 hash, i32 location}; hash = FNV-1a (64 bits, offset basis + seed) of the path
        below the mount point in lower case as UTF-16LE (used when a pak has no full directory index: then a path
        can be read but not listed)
    encoded entry: u32 bits {0-5: block size >> 11 (0x3f: a u32 block size follows), 6-21: block count, 22:
        encrypted, 23-28: compression method, 29: compressed size fits 32 bits, 30: size fits 32 bits, 31: offset
        fits 32 bits}, [u32 block size], offset (u32 or i64), size (u32 or i64), [compressed size, when compressed],
        [u32 compressed size per block, when there is more than one block]
    FPakEntry record: i64 offset, i64 compressed size, i64 size, u32 compression method, 20-byte SHA-1,
        [compressed: i32 n + n x {i64 start, i64 end} relative to the entry's offset], u8 flags (1 encrypted),
        u32 block size
At its offset each entry's data starts with its own FPakEntry record (53 bytes, + 4 + 16 per block when
compressed), then the data or its blocks one after the other; each block decompresses to the block size (the last
one to the rest). Tekken 8 compresses with Oodle (tekken8/oodle.c); the codec comes from the caller (`inflate`).
Nothing is encrypted: the ground rules of this importer (no keys, no decryption) are kept by refusing what would be.

Written for this project from the files themselves (no third-party code).
"""
import os
import struct
import zlib

PAK_MAGIC = 0x5A6F12E1
PAK_VERSIONS = (10, 11)                     # the encoded index (version 10+); Tekken 8 has 11 (path hashes as 11's)
FOOTER_SIZE = 221                           # version 11: GUID 16 + 1 + 4 + 4 + 8 + 8 + 20 + 5 x 32 method names
METHOD_NAMES = 5
METHOD_NAME_SIZE = 32
FNV_OFFSET = 0xcbf29ce484222325
FNV_PRIME = 0x00000100000001b3
RECORD_SIZE = 53                            # FPakEntry without blocks: 3 x i64, u32 method, SHA-1, u8, u32
BLOCK_RECORD = 16
DELETED = -(1 << 31)                        # FPakEntryLocation::Invalid: a patch's delete record


class EncryptedError(Exception):
    """A pak or entry Tekken 8 keeps encrypted (the message names it); this importer does not decrypt."""


def _fstring(b, o):
    """FString: i32 length (negative: UTF-16 code units), the characters including a NUL."""
    n, = struct.unpack_from('<i', b, o)
    o += 4
    if n == 0:
        return '', o
    if n < 0:
        return b[o:o - 2 * n].decode('utf-16-le').rstrip('\0'), o - 2 * n
    return b[o:o + n].decode('utf-8', 'replace').rstrip('\0'), o + n


def path_hash(path, seed):
    """The path hash index's key of a path below the mount point."""
    h = (FNV_OFFSET + seed) & 0xFFFFFFFFFFFFFFFF
    for c in path.lower().encode('utf-16-le'):
        h = ((h ^ c) * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return h


def stored(method, data, size):
    """The default `inflate`: stored and zlib data (Tekken 8's Oodle comes from store.Store)."""
    if not method:
        return data[:size]
    if method.lower() == 'zlib':
        return zlib.decompress(data)
    raise NotImplementedError('pak compression %s' % method)


def pak_names(folder):
    """The pak files in a folder, base paks first, then patches in patch order (a listing, not a glob: a Steam
    library's path may hold [ ] * ?)."""
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith('.pak')]
    except OSError:
        return []
    return sorted(names, key=patch_order)


def patch_order(name):
    """Sort key of a container or pak file name: base ones first, then '_<n>_P' patches by n."""
    stem = os.path.splitext(os.path.basename(name))[0]
    if stem.endswith('_P'):
        parts = stem[:-2].rsplit('_', 1)
        n = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0
        return 1, n, stem.lower()
    return 0, 0, stem.lower()


class Entry:
    __slots__ = ('pak', 'path', 'offset', 'size', 'raw_size', 'method', 'blocks', 'block_size', 'encrypted')

    def __repr__(self):
        return '<pak entry %s: %d bytes (%s %d) at %d in %s>' % (
            self.path, self.raw_size, self.method or 'stored', self.size, self.offset, os.path.basename(self.pak.path))


class Pak:
    """One pak file's index: .files = {path below the game folder ('Polaris/Content/...'): location}, .deleted =
    the paths a patch pak removes."""

    def __init__(self, path):
        self.path = path
        self.files = {}
        self.deleted = set()
        self.hashes = {}
        self._file = None
        size = os.path.getsize(path)
        if size < FOOTER_SIZE:
            raise ValueError('%s is too small for a pak file' % path)
        with open(path, 'rb') as f:
            f.seek(size - FOOTER_SIZE)
            foot = f.read(FOOTER_SIZE)
            magic, self.version, index_offset, index_size = struct.unpack_from('<IiQQ', foot, 17)
            if magic != PAK_MAGIC:
                raise ValueError('%s is not a pak file of Unreal Engine 5' % path)
            if self.version not in PAK_VERSIONS:
                raise ValueError('%s: pak version %d (Tekken 8 has version 11)' % (path, self.version))
            if foot[16]:
                raise EncryptedError(path)
            self.methods = [''] + [foot[61 + METHOD_NAME_SIZE * i:61 + METHOD_NAME_SIZE * (i + 1)]
                                   .split(b'\0', 1)[0].decode('latin-1') for i in range(METHOD_NAMES)]
            if index_offset + index_size > size:
                raise ValueError('%s: the index lies outside the file' % path)
            f.seek(index_offset)
            index = f.read(index_size)
            self.mount, p = _fstring(index, 0)
            self.mount = self.mount.replace('../../../', '')
            self.count, self.seed = struct.unpack_from('<iQ', index, p)
            p += 12
            has_hashes, = struct.unpack_from('<i', index, p)
            p += 4
            hash_at = None
            if has_hashes:
                hash_at = struct.unpack_from('<qq', index, p)
                p += 36
            has_dirs, = struct.unpack_from('<i', index, p)
            p += 4
            dirs_at = None
            if has_dirs:
                dirs_at = struct.unpack_from('<qq', index, p)
                p += 36
            n, = struct.unpack_from('<i', index, p)
            p += 4
            self.encoded = index[p:p + n]
            p += n
            n, = struct.unpack_from('<i', index, p)
            p += 4
            self.records = []
            for _ in range(n):
                rec, p = self._record(index, p)
                self.records.append(rec)
            if dirs_at:
                f.seek(dirs_at[0])
                self._directories(f.read(dirs_at[1]))
            elif hash_at:
                f.seek(hash_at[0])
                d = f.read(hash_at[1])
                n, = struct.unpack_from('<i', d, 0)
                for i in range(n):
                    h, loc = struct.unpack_from('<Qi', d, 4 + 12 * i)
                    if loc != DELETED:
                        self.hashes[h] = loc

    def _directories(self, d):
        q = 0
        nd, = struct.unpack_from('<i', d, q)
        q += 4
        for _ in range(nd):
            folder, q = _fstring(d, q)
            folder = folder.lstrip('/')
            nf, = struct.unpack_from('<i', d, q)
            q += 4
            for _ in range(nf):
                name, q = _fstring(d, q)
                loc, = struct.unpack_from('<i', d, q)
                q += 4
                if loc == DELETED:
                    self.deleted.add(self.mount + folder + name)
                else:
                    self.files[self.mount + folder + name] = loc

    @staticmethod
    def _record(b, p):
        """An FPakEntry record -> ((offset, size, raw size, method, blocks relative, flags, block size), end)."""
        offset, size, raw_size, method = struct.unpack_from('<qqqI', b, p)
        p += 28 + 20
        blocks = []
        if method:
            n, = struct.unpack_from('<i', b, p)
            blocks = [struct.unpack_from('<qq', b, p + 4 + BLOCK_RECORD * i) for i in range(n)]
            p += 4 + BLOCK_RECORD * n
        flags, block_size = struct.unpack_from('<BI', b, p)
        return (offset, size, raw_size, method, blocks, flags, block_size), p + 5

    def location(self, path):
        """The location of a path (as .files names it, or any case through the path hash index), or None."""
        loc = self.files.get(path)
        if loc is None and self.hashes:
            rel = path[len(self.mount):] if path.startswith(self.mount) else path
            loc = self.hashes.get(path_hash(rel, self.seed))
        return loc

    def entry(self, path, location=None):
        """The Entry of a path (KeyError when the pak has none)."""
        loc = self.location(path) if location is None else location
        if loc is None:
            raise KeyError(path)
        e = Entry()
        e.pak, e.path = self, path
        if loc < 0:
            offset, size, raw_size, method, blocks, flags, block_size = self.records[-loc - 1]
            e.offset, e.size, e.raw_size, e.block_size = offset, size, raw_size, block_size
            e.method, e.encrypted = self.methods[method], bool(flags & 1)
            e.blocks = [(offset + s, offset + t) for s, t in blocks]
            if not method:
                e.blocks = [(offset + RECORD_SIZE, offset + RECORD_SIZE + size)]
            return e
        b = self.encoded
        bits, = struct.unpack_from('<I', b, loc)
        q = loc + 4
        if bits & 0x3f == 0x3f:
            block_size, = struct.unpack_from('<I', b, q)
            q += 4
        else:
            block_size = (bits & 0x3f) << 11

        def number(fits32):
            nonlocal q
            v, = struct.unpack_from('<I' if fits32 else '<q', b, q)
            q += 4 if fits32 else 8
            return v
        method = (bits >> 23) & 0x3f
        e.offset = number(bits & (1 << 31))
        e.raw_size = number(bits & (1 << 30))
        e.size = number(bits & (1 << 29)) if method else e.raw_size
        e.encrypted = bool(bits & (1 << 22))
        e.method = self.methods[method]
        nblocks = (bits >> 6) & 0xffff
        e.block_size = e.raw_size if nblocks == 1 else block_size
        start = e.offset + RECORD_SIZE + ((4 + BLOCK_RECORD * nblocks) if method else 0)
        if not method:
            e.blocks = [(start, start + e.size)]
        elif nblocks == 1 and not e.encrypted:
            e.blocks = [(start, start + e.size)]
        else:
            align = 16 if e.encrypted else 1
            e.blocks = []
            for i in range(nblocks):
                n, = struct.unpack_from('<I', b, q + 4 * i)
                e.blocks.append((start, start + n))
                start += (n + align - 1) // align * align
        return e

    def read(self, entry, inflate=stored):
        """An entry's (or path's) data; inflate(method name, data, size) -> bytes decompresses a block."""
        e = entry if isinstance(entry, Entry) else self.entry(entry)
        if e.encrypted:
            raise EncryptedError('%s in %s' % (e.path, self.path))
        if self._file is None:
            self._file = open(self.path, 'rb')
        f = self._file
        if not e.blocks:
            return b''
        first, last = e.blocks[0][0], e.blocks[-1][1]
        f.seek(first)
        span = f.read(last - first)
        if len(span) != last - first:
            raise IOError('%s: short read of %s' % (self.path, e.path))
        if not e.method:
            return span[:e.raw_size]
        out = bytearray()
        for i, (s, t) in enumerate(e.blocks):
            want = min(e.block_size, e.raw_size - i * e.block_size)
            d = inflate(e.method, span[s - first:t - first], want)
            if len(d) != want:
                raise ValueError('%s: block %d decompressed to %d bytes, not %d' % (e.path, i, len(d), want))
            out += d
        return bytes(out)

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None
