"""Builders of made-up Tekken 8 / Unreal Engine 5 files for the tekken8 tests (no game files needed): name batches,
zen packages, container headers, script objects, IoStore containers (.utoc/.ucas), pak files (version 11) and PE
images. The other test_tekken8_* files import this one; its own tests check the builders against the readers'
basics.

    python3 -m unittest discover tools/characters/tests
"""
import os
import struct
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.tekken8 import pak, zen                 # noqa: E402

NULL = 0xFFFFFFFFFFFFFFFF
NONE = 0xFFFFFFFF


def script_index(gi):
    return (gi & ((1 << 62) - 1)) | (1 << 62)


def package_import(package_index, hash_index):
    return (2 << 62) | (package_index << 32) | hash_index


# ---------------------------------------------------------------------------------------------------- zen
def name_batch(names):
    if not names:
        return struct.pack('<I', 0)
    headers, strings = b'', b''
    for n in names:
        try:
            s = n.encode('latin-1')
            headers += struct.pack('>H', len(n))
        except UnicodeEncodeError:
            s = n.encode('utf-16-le')
            headers += struct.pack('>H', 0x8000 | len(n))
        strings += s
    return (struct.pack('<IIQ', len(names), len(strings), 0xC1640000) + bytes(8 * len(names)) + headers + strings)


def zen_package(name, exports, imports=(), hashes=(), bulk=(), imported_packages=0, order=None, cooked_order=None,
                cooked_header_size=1000):
    """A zen package. exports: dicts {name, cls (FPackageObjectIndex), outer (default null), hash (0), data};
    order: the serialize order (default as given); cooked_order: the order of the CookedSerialOffsets (default
    reversed, so that readers relying on them fail); bulk: (offset, size, flags) entries."""
    n = len(exports)
    order = list(range(n)) if order is None else list(order)
    cooked_order = list(reversed(range(n))) if cooked_order is None else list(cooked_order)
    names = [name]
    for e in exports:
        if e['name'] not in names:
            names.append(e['name'])
    nb = name_batch(names)
    bulk_map = struct.pack('<q', 32 * len(bulk)) + b''.join(struct.pack('<qqqII', o, -1, s, f, 0) for o, s, f in bulk)
    o_hashes = 44 + len(nb) + len(bulk_map)
    o_imports = o_hashes + 8 * len(hashes)
    o_exports = o_imports + 8 * len(imports)
    o_bundles = o_exports + 72 * n
    o_graph = o_bundles + 8 * 2 * n
    graph = struct.pack('<QII', 0, 0, 2 * n) + struct.pack('<i', 0) + struct.pack('<i', 0) * imported_packages
    header_size = o_graph + len(graph)
    cooked = {}
    at = cooked_header_size
    for i in cooked_order:
        cooked[i] = at
        at += len(exports[i]['data'])
    emap = b''
    for i, e in enumerate(exports):
        emap += struct.pack('<QQIIQQQQQIB3x', cooked[i], len(e['data']), names.index(e['name']), 0,
                            e.get('outer', NULL), e['cls'], NULL, NULL, e.get('hash', 0), 0, 0)
    bundles = b''.join(struct.pack('<II', i, 0) for i in order) + b''.join(struct.pack('<II', i, 1) for i in order)
    summary = struct.pack('<11I', 0, header_size, 0, 0, 0x80000000, cooked_header_size, o_hashes, o_imports,
                          o_exports, o_bundles, o_graph)
    head = (summary + nb + bulk_map + b''.join(struct.pack('<Q', h) for h in hashes) +
            b''.join(struct.pack('<Q', v) for v in imports) + emap + bundles + graph)
    assert len(head) == header_size
    return head + b''.join(exports[i]['data'] for i in order)


def container_header(container_id, entries):
    """entries: [(package id, [imported package ids])] -> a container header chunk (version 2)."""
    n = len(entries)
    store = bytearray(24 * n)
    tail = bytearray()
    for i, (pid, imported) in enumerate(entries):
        q = 24 * i
        data_at = 24 * n + len(tail)
        struct.pack_into('<iiIIII', store, q, 1, 1, len(imported), data_at - (q + 8) if imported else 0, 0, 0)
        tail += b''.join(struct.pack('<Q', x) for x in imported)
    store += tail
    return (struct.pack('<IIQ', zen.CONTAINER_HEADER_MAGIC, 2, container_id) + struct.pack('<i', n) +
            b''.join(struct.pack('<Q', pid) for pid, _ in entries) + struct.pack('<i', len(store)) + bytes(store) +
            struct.pack('<i', 0) * 4)


def script_objects(objects):
    """objects: [(name, global index, outer index or NULL)] -> a ScriptObjects chunk."""
    names = []
    for nm, _, _ in objects:
        if nm not in names:
            names.append(nm)
    return name_batch(names) + struct.pack('<i', len(objects)) + b''.join(
        struct.pack('<IIQQQ', names.index(nm), 0, gi, outer, 0) for nm, gi, outer in objects)


# ---------------------------------------------------------------------------------------------------- IoStore
def _fstring(s):
    b = s.encode('utf-8') + b'\0'
    return struct.pack('<i', len(b)) + b


def directory_index(mount, files):
    """files: [(path below the mount point, entry index)] -> FIoDirectoryIndexResource bytes."""
    strings, sidx = [], {}

    def string(x):
        if x not in sidx:
            sidx[x] = len(strings)
            strings.append(x)
        return sidx[x]
    dirs, fentries, children = [[NONE, NONE, NONE, NONE]], [], {0: {}}
    for path, entry in files:
        parts = path.split('/')
        d = 0
        for part in parts[:-1]:
            if part not in children[d]:
                nd = len(dirs)
                dirs.append([string(part), NONE, dirs[d][1], NONE])
                dirs[d][1] = nd
                children[d][part] = nd
                children[nd] = {}
            d = children[d][part]
        fentries.append([string(parts[-1]), dirs[d][3], entry])
        dirs[d][3] = len(fentries) - 1
    return (_fstring(mount) + struct.pack('<I', len(dirs)) + b''.join(struct.pack('<4I', *d) for d in dirs) +
            struct.pack('<I', len(fentries)) + b''.join(struct.pack('<3I', *f) for f in fentries) +
            struct.pack('<I', len(strings)) + b''.join(_fstring(s) for s in strings))


def write_container(base, chunks, files, block_size=0x400, compress=True, container_id=1, version=5):
    """Writes <base>.utoc/.ucas. chunks: [(id, type, index, data)]; files: [(path, chunk position)]; blocks are
    zlib-compressed (method 'Zlib') when that makes them smaller."""
    ucas, blocks, offlen, uoff = bytearray(), [], [], 0
    for cid, ctype, cidx, data in chunks:
        offlen.append((uoff, len(data)))
        for i in range(0, len(data), block_size):
            part = data[i:i + block_size]
            c, m = part, 0
            if compress:
                z = zlib.compress(part)
                if len(z) < len(part):
                    c, m = z, 1
            blocks.append((len(ucas), len(c), len(part), m))
            ucas += c + bytes(-len(c) % 16)
        uoff += -(-len(data) // block_size) * block_size
    dindex = directory_index('../../../', files) if files else b''
    flags = 1 | (8 if files else 0)
    header = (b'-==--==--==--==-' + struct.pack('<BBH', version, 0, 0) +
              struct.pack('<9I', 144, len(chunks), len(blocks), 12, 1, 32, block_size, len(dindex), 1) +
              struct.pack('<Q', container_id) + bytes(16) + struct.pack('<BBH', flags, 0, 0) +
              struct.pack('<IQII', 0, NULL, 0, 0) + bytes(40))
    assert len(header) == 144
    body = b''.join(struct.pack('<Q', cid) + struct.pack('>H', cidx) + bytes([0, ctype])
                    for cid, ctype, cidx, _ in chunks)
    body += b''.join(o.to_bytes(5, 'big') + n.to_bytes(5, 'big') for o, n in offlen)
    body += b''.join(o.to_bytes(5, 'little') + c.to_bytes(3, 'little') + u.to_bytes(3, 'little') + bytes([m])
                     for o, c, u, m in blocks)
    body += b'Zlib'.ljust(32, b'\0') + dindex
    with open(base + '.utoc', 'wb') as f:
        f.write(header + body)
    with open(base + '.ucas', 'wb') as f:
        f.write(ucas)


# ---------------------------------------------------------------------------------------------------- pak
def write_pak(path, files, mount='../../../', block_size=0x400, deleted=(), records=(), hash_index=False, seed=7):
    """A version 11 pak. files: {path below the mount point: data} (zlib-compressed in blocks when it is smaller,
    encoded entries); records: paths stored as FPakEntry records instead; deleted: delete records; hash_index:
    a path hash index instead of the full directory index."""
    out = bytearray()
    encoded, recs, loc = bytearray(), [], {}
    for name, data in files.items():
        offset = len(out)
        parts = [data[i:i + block_size] for i in range(0, len(data), block_size)] or [b'']
        comp = [zlib.compress(p) for p in parts]
        method = 1 if sum(map(len, comp)) < len(data) else 0
        if method:
            head_size = pak.RECORD_SIZE + 4 + 16 * len(parts)
            blocks, at = [], head_size
            for c in comp:
                blocks.append((at, at + len(c)))
                at += len(c)
            payload = b''.join(comp)
        else:
            head_size, blocks, payload = pak.RECORD_SIZE, [], data
        record = struct.pack('<qqqI', 0, len(payload), len(data), method) + bytes(20)
        if method:
            record += struct.pack('<i', len(blocks)) + b''.join(struct.pack('<qq', s, t) for s, t in blocks)
        record += struct.pack('<BI', 0, block_size if method else 0)
        assert len(record) == head_size
        out += record + payload
        if name in records:
            loc[name] = -(len(recs) + 1)
            r = struct.pack('<qqqI', offset, len(payload), len(data), method) + bytes(20)
            if method:
                r += struct.pack('<i', len(blocks)) + b''.join(struct.pack('<qq', s, t) for s, t in blocks)
            recs.append(r + struct.pack('<BI', 0, block_size if method else 0))
            continue
        nb = len(blocks) if method else 0
        small = block_size % 2048 == 0 and block_size >> 11 < 0x3f
        bits = (block_size >> 11 if small else 0x3f) | (nb << 6) | (method << 23) | (1 << 29) | (1 << 30) | (1 << 31)
        e = struct.pack('<I', bits) + (b'' if small else struct.pack('<I', block_size))
        e += struct.pack('<III', offset, len(data), len(payload)) if method else struct.pack('<II', offset, len(data))
        if nb > 1:
            e += b''.join(struct.pack('<I', len(c)) for c in comp)
        loc[name] = len(encoded)
        encoded += e
    for name in deleted:
        loc[name] = pak.DELETED
    index_at = len(out)
    tail = struct.pack('<i', len(encoded)) + bytes(encoded) + struct.pack('<i', len(recs)) + b''.join(recs)
    if hash_index:
        sec = struct.pack('<i', len(loc)) + b''.join(struct.pack('<Qi', pak.path_hash(n, seed), v)
                                                     for n, v in loc.items()) + struct.pack('<i', 0)
    else:
        folders = {}
        for n, v in loc.items():
            d, _, f = n.rpartition('/')
            folders.setdefault(d + '/' if d else '/', []).append((f, v))
        sec = struct.pack('<i', len(folders)) + b''.join(
            _fstring(d) + struct.pack('<i', len(fs)) + b''.join(_fstring(f) + struct.pack('<i', v) for f, v in fs)
            for d, fs in folders.items())
    head = _fstring(mount) + struct.pack('<iQ', len(files), seed)
    sec_at = index_at + len(head) + 40 + 4 + len(tail)
    there = struct.pack('<iqq', 1, sec_at, len(sec)) + bytes(20)
    primary = head + (there + struct.pack('<i', 0) if hash_index else struct.pack('<i', 0) + there) + tail
    assert index_at + len(primary) == sec_at
    out += primary + sec
    footer = bytes(16) + struct.pack('<BIiqq', 0, pak.PAK_MAGIC, 11, index_at, len(primary)) + bytes(20) + \
        b'Zlib'.ljust(32, b'\0') + bytes(32 * 4)
    assert len(footer) == pak.FOOTER_SIZE
    with open(path, 'wb') as f:
        f.write(bytes(out) + footer)


# ---------------------------------------------------------------------------------------------------- PE
def pe_image(base, sections, directories):
    """sections: [(name, rva, bytes, characteristics)] (rva page-aligned, ascending); directories: {index: (rva,
    size)} -> a 64-bit PE file (file alignment 0x200)."""
    head = 0x400
    raw, table, data = head, b'', b''
    for name, rva, body, chars in sections:
        size = -(-len(body) // 0x200) * 0x200
        table += struct.pack('<8sIIIIIIHHI', name.encode(), len(body), rva, size, raw, 0, 0, 0, 0, chars)
        data += body + bytes(size - len(body))
        raw += size
    last = sections[-1]
    image = -(-(last[1] + len(last[2])) // 0x1000) * 0x1000
    dirs = b''.join(struct.pack('<II', *directories.get(i, (0, 0))) for i in range(16))
    opt = struct.pack('<HBBIIIIIQIIHHHHHHIIIIHHQQQQII', 0x20b, 14, 0, 0, 0, 0, 0, 0, base, 0x1000, 0x200, 6, 0, 0,
                      0, 6, 0, 0, image, head, 0, 3, 0x8160, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16) + dirs
    assert len(opt) == 240
    coff = b'PE\0\0' + struct.pack('<HHIIIHH', 0x8664, len(sections), 0, 0, 0, len(opt), 0x22)
    dos = b'MZ' + bytes(0x3a) + struct.pack('<I', 0x40)
    headers = dos + coff + opt + table
    assert len(headers) <= head
    return headers + bytes(head - len(headers)) + data


class Builders(unittest.TestCase):
    def test_name_batch(self):
        b = name_batch(['None', 'Texture2D', 'マテリアル_01'])
        names, end = zen.read_name_batch(b, 0)
        self.assertEqual(names, ['None', 'Texture2D', 'マテリアル_01'])
        self.assertEqual(end, len(b))
        self.assertEqual(zen.read_name_batch(name_batch([]), 0), ([], 4))


if __name__ == '__main__':
    unittest.main()
