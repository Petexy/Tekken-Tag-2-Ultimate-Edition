"""The player's Tekken 8 PC installation, read-only: its IoStore containers (.utoc/.ucas) and pak files (.pak).

The game folder ('TEKKEN 8' in a Steam library) holds Polaris/ (the project; Content/Paks/ has the containers,
Binaries/Win64/Polaris-Win64-Shipping.exe the program) and Engine/. Files are named by their path below it:
'Polaris/Content/Character/....uasset' (packages also by their names, '/Game/Character/...', or without the
extension), 'Polaris/Content/WwiseAudio/Media/<id>.wem' (pak files).

.utoc (TOC version 5; UE 5.1-5.3), header (144 bytes): 16-byte magic '-==--==--==--==-', u8 version, u8, u16,
u32 header size, u32 entry count, u32 compression block count, u32 block entry size (12), u32 method name count,
u32 method name length, u32 compression block size, u32 directory index size, u32 partition count, u64 container
id, FGuid encryption key, u8 flags (1 compressed, 2 encrypted, 4 signed, 8 indexed), u8, u16, u32 perfect hash
seed count, u64 partition size, u32 count of chunks without a perfect hash, u32, 5 x u64. Then:
    chunk ids, 12 bytes each: u64 id (a package's: its package id), u16 big-endian index, u8, u8 type (1 package,
        2 .ubulk, 3 .uptnl, 4 .m.ubulk, 5 script objects, 6 container header, 8/9 shaders, ...)
    offset and length, 10 bytes each: 5-byte big-endian offset into the container's uncompressed space, 5-byte
        big-endian length
    i32 perfect hash seeds, i32 indices of the chunks without one (version 5)
    compression blocks, 12 bytes each: 5-byte offset in the .ucas, 3-byte compressed size, 3-byte uncompressed
        size, u8 method (0 stored, else the method names' index + 1) (little-endian); the stored block is padded
        to 16 bytes; block i holds uncompressed bytes [i x block size, (i + 1) x block size)
    method names (count x length bytes, NUL-padded): 'Oodle'
    [signed: i32 hash size, two signatures, 20-byte SHA-1 per block]
    directory index (indexed): FString mount point ('../../../'), TArray of directories {u32 name, u32 first
        child, u32 next sibling, u32 first file} (directory 0 is the root; 0xFFFFFFFF none), TArray of files {u32
        name, u32 next file, u32 entry index}, TArray<FString> names
A `*_P` container patches the base ones (its chunks and paths win; higher patch numbers win). Tekken 8 encrypts
none of its containers; an encrypted one would be left out (no keys, no decryption here), as is every read of
the moveset archive (Polaris/Content/Binary/pak/tkdata.bin, a loose encrypted file that this importer never opens).

Compressed blocks are Oodle (Kraken), decompressed by the game's own code (oodle.c, built by ../native.py on first
use, loaded once per process). Pak files: pak.py.

Written for this project from the files themselves (no third-party code).
"""
import bisect
import ctypes
import fnmatch
import mmap
import os
import re
import struct
import threading

import numpy as np

from .. import InputError, native
from . import pak, zen

TOC_MAGIC = b'-==--==--==--==-'
TOC_HEADER_SIZE = 144
TOC_VERSIONS = range(3, 9)                  # partition size (3) .. IoHash (8); Tekken 8 has 5 (perfect hash +
                                            # overflow); later ones only add data after the directory index
TOC_COMPRESSED, TOC_ENCRYPTED, TOC_SIGNED, TOC_INDEXED = 1, 2, 4, 8
NONE = 0xFFFFFFFF
BLOCK_ALIGN = 16                            # a stored compressed block is padded to the AES block size
EXE = os.path.join('Polaris', 'Binaries', 'Win64', 'Polaris-Win64-Shipping.exe')
PAKS = os.path.join('Polaris', 'Content', 'Paks')
STEAM_FOLDER = 'TEKKEN 8'                   # the game's folder below steamapps/common
MOUNTS = {'/Game/': 'Polaris/Content/', '/Engine/': 'Engine/Content/'}
PACKAGE_EXTENSIONS = ('.uasset', '.umap')
NEVER_READ = ('tkdata.bin',)                # Tekken 8's encrypted moveset archive: never opened (ground rule)
SLACK = 64                                  # spare bytes after a decompression target


# ---------------------------------------------------------------------------------------------------- Oodle
class Oodle:
    """Tekken 8's own OodleLZ_Decompress through oodle.c (one per process: the library maps the exe once)."""

    _lock = threading.Lock()
    _instance = None

    def __init__(self, exe):
        if not os.path.isfile(exe):
            raise InputError('Tekken 8\'s program %s is missing, and it is needed to unpack the game\'s files: '
                             'verify the integrity of Tekken 8\'s files in Steam' % exe)
        lib = ctypes.CDLL(native.build('oodle', os.path.join('tekken8', 'oodle.c'), libs=('-lpthread',),
                                      dependencies=(os.path.join('tekken8', 'oodle_windows.h'),)))
        lib.oodle8_open.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        lib.oodle8_open.restype = ctypes.c_int
        lib.oodle8_decompress.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_ssize_t]
        lib.oodle8_decompress.restype = ctypes.c_ssize_t
        lib.oodle8_error.restype = ctypes.c_char_p
        lib.oodle8_function_rva.restype = ctypes.c_uint64
        err = ctypes.create_string_buffer(512)
        if lib.oodle8_open(os.fsencode(exe), err, len(err)) != 0:
            raise InputError('Tekken 8\'s decompressor could not be loaded from %s (%s): verify the integrity of '
                             'Tekken 8\'s files in Steam; if this persists, the game update changed it and the '
                             'importer needs an update' % (exe, err.value.decode('utf-8', 'replace')))
        self.lib, self.exe = lib, exe
        self.function_rva = lib.oodle8_function_rva()

    @classmethod
    def get(cls, exe):
        with cls._lock:
            if cls._instance is None:
                cls._instance = Oodle(exe)
            return cls._instance

    def into(self, src, src_offset, src_size, dst, dst_offset, dst_size):
        """Decompress src[src_offset:+src_size] into dst[dst_offset:+dst_size] (bytearrays; dst must have SLACK
        bytes to spare after it)."""
        if src_offset + src_size > len(src) or dst_offset + dst_size > len(dst):
            raise ValueError('decompression range outside its buffers')
        s = (ctypes.c_char * len(src)).from_buffer(src)
        d = (ctypes.c_char * len(dst)).from_buffer(dst)
        try:
            got = self.lib.oodle8_decompress(ctypes.addressof(s) + src_offset, src_size,
                                             ctypes.addressof(d) + dst_offset, dst_size)
        finally:
            del s, d
        if got != dst_size:
            raise IOError('Oodle could not decompress a block (%s)' % self.lib.oodle8_error().decode('utf-8',
                                                                                                    'replace'))

    def decompress(self, data, size):
        src = bytearray(data)
        dst = bytearray(size + SLACK)
        self.into(src, 0, len(src), dst, 0, size)
        del dst[size:]
        return bytes(dst)


# ---------------------------------------------------------------------------------------------------- .utoc
def _be40(a):
    """(n, 5) uint8 -> int64 big-endian values."""
    a = a.astype(np.int64)
    return (a[:, 0] << 32) | (a[:, 1] << 24) | (a[:, 2] << 16) | (a[:, 3] << 8) | a[:, 4]


def _fstring(b, o):
    n, = struct.unpack_from('<i', b, o)
    o += 4
    if n < 0:
        return bytes(b[o:o - 2 * n]).decode('utf-16-le').rstrip('\0'), o - 2 * n
    return bytes(b[o:o + n]).decode('utf-8', 'replace').rstrip('\0'), o + n


class Toc:
    """One IoStore container: its chunk ids, where they are, its compression blocks and its directory index."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        with open(path, 'rb') as f:
            self.raw = b = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if len(b) < TOC_HEADER_SIZE or b[:16] != TOC_MAGIC:
            raise ValueError('%s is not an IoStore table of contents' % path)
        self.version = b[16]
        if self.version not in TOC_VERSIONS:
            raise ValueError('%s: IoStore TOC version %d (Tekken 8 has 5)' % (path, self.version))
        (header_size, n, nblocks, block_entry, nmethods, method_len, self.block_size, dir_size,
         self.partitions) = struct.unpack_from('<9I', b, 20)
        self.container_id, = struct.unpack_from('<Q', b, 56)
        self.flags = b[80]
        seeds, = struct.unpack_from('<I', b, 84)
        self.partition_size, = struct.unpack_from('<Q', b, 88)
        overflow, = struct.unpack_from('<I', b, 96)
        if self.version < 4:
            seeds = 0
        if self.version < 5:
            overflow = 0
        p = header_size
        ids = np.frombuffer(b, np.dtype([('id', '<u8'), ('index', '>u2'), ('pad', 'u1'), ('type', 'u1')]), n, p)
        self.chunk_ids, self.chunk_index, self.chunk_type = ids['id'], ids['index'], ids['type']
        p += 12 * n
        ol = np.frombuffer(b, np.uint8, 10 * n, p).reshape(n, 10)
        self.offsets, self.lengths = _be40(ol[:, :5]), _be40(ol[:, 5:])
        p += 10 * n + 4 * seeds + 4 * overflow
        self.block_entry = block_entry
        self.blocks_at = p
        self.nblocks = nblocks
        p += block_entry * nblocks
        self.methods = [bytes(b[p + method_len * i:p + method_len * (i + 1)]).split(b'\0', 1)[0].decode('latin-1')
                        for i in range(nmethods)]
        p += nmethods * method_len
        if self.flags & TOC_SIGNED:
            hash_size, = struct.unpack_from('<i', b, p)
            p += 4 + 2 * hash_size + 20 * nblocks
        self.files = []                         # (path, entry index)
        if self.flags & TOC_INDEXED and dir_size and not self.flags & TOC_ENCRYPTED:
            self._directory(b, p, dir_size)
        self._ucas = {}
        self._read_lock = threading.Lock()
        self.header = None                      # its container header ({package id: store entry}), when read

    def _directory(self, b, p, size):
        end = p + size
        mount, p = _fstring(b, p)
        mount = mount.replace('../../../', '')
        nd, = struct.unpack_from('<I', b, p)
        dirs = np.frombuffer(b, '<u4', 4 * nd, p + 4).reshape(nd, 4).tolist()
        p += 4 + 16 * nd
        nf, = struct.unpack_from('<I', b, p)
        files = np.frombuffer(b, '<u4', 3 * nf, p + 4).reshape(nf, 3).tolist()
        p += 4 + 12 * nf
        ns, = struct.unpack_from('<I', b, p)
        p += 4
        names = []
        for _ in range(ns):
            s, p = _fstring(b, p)
            names.append(s)
        if p > end:
            raise ValueError('%s: the directory index runs past its size' % self.path)
        stack = [(0, mount)] if nd else []
        while stack:
            d, prefix = stack.pop()
            name, child, sibling, f = dirs[d]
            if sibling != NONE:
                stack.append((sibling, prefix))
            here = prefix + (names[name] + '/' if name != NONE else '')
            while f != NONE:
                fname, f, entry = files[f]
                self.files.append((here + names[fname], entry))
            if child != NONE:
                stack.append((child, here))

    def block(self, i):
        """Compression block i -> (.ucas offset, compressed size, size, method name or '')."""
        q = self.blocks_at + self.block_entry * i
        e = self.raw[q:q + 12]
        m = e[11]
        return (int.from_bytes(e[0:5], 'little'), int.from_bytes(e[5:8], 'little'), int.from_bytes(e[8:11], 'little'),
                self.methods[m - 1] if m else '')

    def _fd(self, partition):
        fd = self._ucas.get(partition)
        if fd is None:
            base = os.path.splitext(self.path)[0]
            name = base + ('.ucas' if partition == 0 else '_s%d.ucas' % partition)
            fd = self._ucas[partition] = os.open(name, os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) |
                                               getattr(os, 'O_BINARY', 0))
        return fd

    def read(self, entry, inflate, offset=0, size=None):
        """Bytes [offset, offset + size) of chunk `entry` (all of it by default)."""
        start, length = int(self.offsets[entry]), int(self.lengths[entry])
        if size is None or offset + size > length:
            size = max(0, length - offset)
        if size == 0:
            return b''
        bs = self.block_size
        first, last = (start + offset) // bs, (start + offset + size - 1) // bs
        blocks = [self.block(i) for i in range(first, last + 1)]
        total = sum(b[2] for b in blocks)
        out = bytearray(total + SLACK)
        at = 0
        i = 0
        while i < len(blocks):                  # runs of blocks lying back to back in one .ucas partition
            part = blocks[i][0] // self.partition_size if self.partitions > 1 else 0
            j = i + 1
            while (j < len(blocks) and blocks[j][0] == blocks[j - 1][0] + _padded(blocks[j - 1][1]) and
                   (self.partitions <= 1 or blocks[j][0] // self.partition_size == part)):
                j += 1
            lo = blocks[i][0]
            hi = blocks[j - 1][0] + blocks[j - 1][1]
            span = bytearray(hi - lo)
            position = lo - part * self.partition_size if self.partitions > 1 else lo
            if hasattr(os, 'preadv'):
                got = os.preadv(self._fd(part), [span], position)
            else:
                # Windows has no preadv; protect the seek/read pair so parallel
                # reads of different chunks cannot move each other's cursor.
                with self._read_lock:
                    fd = self._fd(part)
                    os.lseek(fd, position, os.SEEK_SET)
                    data = os.read(fd, len(span))
                got = len(data)
                span[:got] = data
            if got != len(span):
                raise IOError('%s: short read' % self.path)
            for boff, csize, usize, method in blocks[i:j]:
                s = boff - lo
                if not method:
                    out[at:at + usize] = span[s:s + usize]
                else:
                    inflate(method, span, s, csize, out, at, usize)
                at += usize
            i = j
        s = (start + offset) - first * bs
        del out[s + size:]
        if s:
            del out[:s]
        return bytes(out)

    def close(self):
        for fd in self._ucas.values():
            os.close(fd)
        self._ucas = {}
        # These arrays reference the mapping. Release them before closing it;
        # Windows otherwise keeps the TOC file locked even after Store.close().
        self.chunk_ids = self.chunk_index = self.chunk_type = None
        self.raw.close()


def _padded(n):
    return (n + BLOCK_ALIGN - 1) // BLOCK_ALIGN * BLOCK_ALIGN


# ---------------------------------------------------------------------------------------------------- paths
def mount_to_package(path):
    """'Polaris/Content/X/Y.uasset' -> '/Game/X/Y'; 'Engine/Content/...' -> '/Engine/...'; a plugin's
    '.../<Plugin>/Content/...' -> '/<Plugin>/...'; None for paths outside a Content folder."""
    p = path.replace('\\', '/')
    p = p[9:] if p.startswith('../../../') else p
    for name, prefix in MOUNTS.items():
        if p.startswith(prefix):
            return name + os.path.splitext(p[len(prefix):])[0]
    parts = p.split('/')
    if 'Content' in parts[1:]:
        i = parts.index('Content', 1)
        return '/' + '/'.join([parts[i - 1]] + parts[i + 1:]).rsplit('.', 1)[0]
    return None


def game_folder(folder):
    """The game folder (the one holding Polaris/Content/Paks) for a folder the player picked: that folder, one of
    its parents (Polaris/, Content/, Paks/, Binaries/, the exe), or a Steam library holding Tekken 8."""
    if not folder:
        raise InputError('No Tekken 8 folder given: pick the \'%s\' folder (in Steam: right-click Tekken 8 > '
                         'Manage > Browse local files)' % STEAM_FOLDER)
    start = os.path.abspath(os.path.expanduser(folder))
    tries = []
    p = start
    for _ in range(6):
        tries.append(p)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    for sub in (os.path.join('steamapps', 'common', STEAM_FOLDER), os.path.join('common', STEAM_FOLDER),
                STEAM_FOLDER):
        tries.append(os.path.join(start, sub))
    for t in tries:
        if os.path.isdir(os.path.join(t, PAKS)):
            return t
    raise InputError('%s is not a Tekken 8 installation (it has no %s): pick the \'%s\' folder (in Steam: '
                     'right-click Tekken 8 > Manage > Browse local files)' % (folder, PAKS.replace(os.sep, '/'),
                                                                               STEAM_FOLDER))


# ---------------------------------------------------------------------------------------------------- the store
class Store:
    """Every file of the installation: path -> the container entry or pak entry that counts (patches win)."""

    def __init__(self, folder):
        self.folder = game_folder(folder)
        self.exe = os.path.join(self.folder, EXE)
        pak_dir = os.path.join(self.folder, PAKS)
        names = os.listdir(pak_dir)
        self.tocs, self.skipped = [], []
        for n in sorted((n for n in names if n.lower().endswith('.utoc')), key=pak.patch_order):
            try:
                t = Toc(os.path.join(pak_dir, n))
            except (ValueError, OSError) as ex:
                self.skipped.append((n, str(ex)))
                continue
            if t.flags & TOC_ENCRYPTED:
                self.skipped.append((n, 'encrypted'))
                continue
            self.tocs.append(t)
        if not self.tocs:
            raise InputError('%s has no readable IoStore containers (.utoc/.ucas): verify the integrity of '
                             'Tekken 8\'s files in Steam' % pak_dir)
        self.files = {}                         # lower-case path -> (path, toc index, entry index)
        self.chunks = {}                        # (id, type, index) -> (toc index, entry index)
        for ti, t in enumerate(self.tocs):
            keys = zip(t.chunk_ids.tolist(), t.chunk_type.tolist(), t.chunk_index.tolist())
            self.chunks.update(zip(keys, ((ti, e) for e in range(len(t.chunk_ids)))))
            for path, e in t.files:
                self.files[path.lower()] = (path, ti, e)
        self.paks = []
        self.pak_files = {}                     # lower-case path -> (path, pak index, location)
        for n in pak.pak_names(pak_dir):
            try:
                k = pak.Pak(os.path.join(pak_dir, n))
            except (ValueError, OSError, pak.EncryptedError) as ex:
                self.skipped.append((n, str(ex)))
                continue
            if not k.files and not k.deleted:
                continue
            ki = len(self.paks)
            self.paks.append(k)
            for path in k.deleted:
                self.pak_files.pop(path.lower(), None)
            for path, loc in k.files.items():
                self.pak_files[path.lower()] = (path, ki, loc)
        self._sorted = None
        self._plugins = None
        self._resolver = None
        self._schema = None
        self._oodle = None
        self._by_id = None

    def __repr__(self):
        return '<Tekken 8 store %s: %d containers, %d files, %d pak files>' % (
            self.folder, len(self.tocs), len(self.files), len(self.pak_files))

    # ------------------------------------------------------------------------------------------- decompression
    def oodle(self):
        if self._oodle is None:
            self._oodle = Oodle.get(self.exe)
        return self._oodle

    def _inflate(self, method, src, src_offset, src_size, dst, dst_offset, dst_size):
        if method == 'Oodle':
            self.oodle().into(src, src_offset, src_size, dst, dst_offset, dst_size)
        else:
            d = pak.stored(method, bytes(src[src_offset:src_offset + src_size]), dst_size)
            if len(d) != dst_size:
                raise IOError('a %s block decompressed to %d bytes, not %d' % (method, len(d), dst_size))
            dst[dst_offset:dst_offset + dst_size] = d

    def _pak_inflate(self, method, data, size):
        if method == 'Oodle':
            return self.oodle().decompress(data, size)
        return pak.stored(method, data, size)

    # ------------------------------------------------------------------------------------------- paths
    def plugin_mounts(self):
        """{'/<Plugin>/': '<its Content folder>/'} of the plugins with files."""
        if self._plugins is None:
            self._plugins = {}
            for path, _, _ in self.files.values():
                parts = path.split('/', 1)
                if parts[0] in ('Polaris', 'Engine') and path.split('/')[1] == 'Content':
                    continue
                i = path.find('/Content/')
                if i > 0:
                    head = path[:i]
                    self._plugins.setdefault('/%s/' % head.rsplit('/', 1)[-1], head + '/Content/')
        return self._plugins

    def file_path(self, path):
        """The stored path ('Polaris/Content/....uasset' as the store names it) of a path, package name
        ('/Game/X/Y'), object path ('/Game/X/Y.Y') or path without extension; None when there is none."""
        p = path.replace('\\', '/')
        if p.startswith('../../../'):
            p = p[9:]
        if os.path.basename(p).lower() in NEVER_READ:
            return None
        cands = []
        if p.startswith('/'):
            head = p.split('/', 2)
            mount = '/%s/' % head[1] if len(head) > 2 else None
            base = MOUNTS.get(mount) or self.plugin_mounts().get(mount)
            if base is None:
                return None
            rest = p[len(mount):]
            last = rest.rsplit('/', 1)
            obj = last[-1].split('.', 1)[0].split(':', 1)[0]
            rest = (last[0] + '/' if len(last) > 1 else '') + obj
            cands = [base + rest + ext for ext in PACKAGE_EXTENSIONS]
        else:
            cands = [p]
            if '.' not in os.path.basename(p):
                cands += [p + ext for ext in PACKAGE_EXTENSIONS]
        for c in cands:
            k = c.lower()
            hit = self.files.get(k) or self.pak_files.get(k)
            if hit:
                return hit[0]
        return None

    def exists(self, path):
        return self.file_path(path) is not None

    def find(self, pattern):
        """The stored paths (sorted) under a prefix ('Polaris/Content/Sound/Character/ZBR/' or '/Game/...') or
        matching a glob ('*' also crosses '/'), in any case."""
        if self._sorted is None:
            self._sorted = sorted(set(v[0] for v in self.files.values()) | set(v[0] for v in self.pak_files.values()),
                                  key=str.lower)
            self._sorted_lower = [p.lower() for p in self._sorted]
        p = pattern.replace('\\', '/')
        if p.startswith('/'):
            head = p.split('/', 2)
            mount = '/%s/' % head[1] if len(head) > 2 else None
            base = MOUNTS.get(mount) or self.plugin_mounts().get(mount)
            if base is None:
                return []
            p = base + p[len(mount):]
        if any(c in p for c in '*?['):
            rx = re.compile(fnmatch.translate(p.lower()))
            return [q for q, ql in zip(self._sorted, self._sorted_lower) if rx.match(ql)]
        lo = p.lower()
        i = bisect.bisect_left(self._sorted_lower, lo)
        out = []
        while i < len(self._sorted) and self._sorted_lower[i].startswith(lo):
            out.append(self._sorted[i])
            i += 1
        return out

    # ------------------------------------------------------------------------------------------- reading
    def read(self, path, offset=0, size=None):
        """A file's bytes (or `size` bytes from `offset`); KeyError when there is no such file."""
        p = self.file_path(path)
        if p is None:
            raise KeyError(path)
        hit = self.files.get(p.lower())
        if hit is not None:
            _, ti, e = hit
            t = self.tocs[ti]
            ti, e = self.chunks[(int(t.chunk_ids[e]), int(t.chunk_type[e]), int(t.chunk_index[e]))]  # patches win
            return self.tocs[ti].read(e, self._inflate, offset, size)
        _, ki, loc = self.pak_files[p.lower()]
        k = self.paks[ki]
        d = k.read(k.entry(p, loc), self._pak_inflate)
        return d[offset:] if size is None else d[offset:offset + size]

    def has_chunk(self, chunk_id, chunk_type, index=0):
        return (chunk_id, chunk_type, index) in self.chunks

    def chunk(self, chunk_id, chunk_type, index=0, offset=0, size=None):
        """A chunk's bytes by (id (a package's: its package id), type, index); KeyError when there is none."""
        ti, e = self.chunks[(chunk_id, chunk_type, index)]
        return self.tocs[ti].read(e, self._inflate, offset, size)

    def package_id(self, path):
        """The package id of a package's path or name, or None."""
        p = self.file_path(path)
        hit = self.files.get(p.lower()) if p else None
        if hit is None:
            return None
        t = self.tocs[hit[1]]
        e = hit[2]
        return int(t.chunk_ids[e]) if t.chunk_type[e] == zen.CHUNK_EXPORT_BUNDLE else None

    def package(self, path):
        """The zen.Package of a package path or name (KeyError when there is none)."""
        p = self.file_path(path)
        if p is None or not p.lower().endswith(PACKAGE_EXTENSIONS):
            raise KeyError(path)
        return zen.Package(self.read(p), p, self.package_id(p), self.resolver, self)

    # ------------------------------------------------------------------------------------------- names (Resolver)
    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = zen.Resolver(self)
        return self._resolver

    @property
    def schema(self):
        """The class and struct schemas of the game's program (reflect.Schema; cached on disk)."""
        if self._schema is None:
            from . import reflect
            self._schema = reflect.Schema.load(self.exe)
        return self._schema

    def script_objects_data(self):
        for (cid, ctype, index), (ti, e) in self.chunks.items():
            if ctype == zen.CHUNK_SCRIPT_OBJECTS:
                return self.tocs[ti].read(e, self._inflate)
        return None

    def container_header(self, toc):
        """A container's header: {package id: (export count, bundle count, imported package ids)}."""
        if toc.header is None:
            toc.header = {}
            for e in np.nonzero(toc.chunk_type == zen.CHUNK_CONTAINER_HEADER)[0].tolist():
                toc.header.update(zen.container_header(toc.read(e, self._inflate)))
        return toc.header

    def imported_package_ids(self, package_id):
        hit = self.chunks.get((package_id, zen.CHUNK_EXPORT_BUNDLE, 0))
        if hit is None:
            return ()
        entry = self.container_header(self.tocs[hit[0]]).get(package_id)
        return entry[2] if entry else ()

    def package_path(self, package_id):
        """The stored path of a package id's .uasset/.umap, or None."""
        if self._by_id is None:
            self._by_id = {}
            for path, ti, e in self.files.values():
                t = self.tocs[ti]
                if t.chunk_type[e] == zen.CHUNK_EXPORT_BUNDLE:
                    self._by_id[int(t.chunk_ids[e])] = path
        return self._by_id.get(package_id)

    def package_name(self, package_id):
        p = self.package_path(package_id)
        return mount_to_package(p) if p else None

    def package_header(self, package_id):
        hit = self.chunks.get((package_id, zen.CHUNK_EXPORT_BUNDLE, 0))
        if hit is None:
            return None
        t = self.tocs[hit[0]]
        d = t.read(hit[1], self._inflate, 0, zen.HEADER_PEEK)
        if len(d) >= 8:
            header_size, = struct.unpack_from('<I', d, 4)
            if header_size > len(d):
                d = t.read(hit[1], self._inflate, 0, header_size)
        return d

    def close(self):
        for t in self.tocs:
            t.close()
        for k in self.paks:
            k.close()
