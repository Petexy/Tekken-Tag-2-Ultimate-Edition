"""Tekken 8's UE5 animation assets besides the fighters' own clips (those are PANM: panm.py): a USkeleton's bones
and reference pose, and an AnimSequence compressed with the per-track codec (AnimCompress_PerTrackCompression_2), as
Miary Zo's snakes' 16 clips are (convert/snakes8.py).

USkeleton (its export's class data after the properties): u32 GUID flag (a 16-byte GUID follows when 1), TArray of
{FName, i32 parent} (the bones, parents first), TArray of 10 f64 a bone (the reference pose: rotation x, y, z, w,
translation x, y, z (cm), scale x, y, z), local to the parent.

AnimSequence (after the properties): u32 GUID flag (+16 bytes when 1), the skeleton's 16-byte GUID, u16 strip flags,
bool32 compressed (1), i32 raw size, TArray<i32> track -> skeleton bone, TArray of curve names (none here), i32
stream bytes, u32 0, the stream, FString codec (an AnimCompress_PerTrackCompression_<n> object's name), FString
curve codec path, i32
curve bytes and them, then i32 frames (the sampled frames: length x 60 + 1), 4 x u8 (2 = per-track keys, then 3
bytes), i32 data bytes, i32 count of the translation / rotation offsets (2 a track), i32 count of the scale offsets,
i32 scale strip (1: scale offsets present), i32 1.
The stream: i32 offsets into the data (translation, rotation of each track), i32 scale offsets (one a track), then
the data; an offset -1: no data (a translation of 0, the identity rotation, or the reference pose's scale).
A track's data: u32 header (keys = low 24 bits; bits 24..27 flags: 0..2 which of x, y, z are stored (the others
0), 3 a frame table follows; top 4 bits the format: 1 Float96NoW = f32 a stored component, 2 Fixed48NoW = u16 a
stored component, 3 IntervalFixed32NoW = f32 (min, range) a stored component, then a u32 a key), its keys, padding
(0x55) to 4 bytes, then a timed track's frame table (a u8 a key when the clip has fewer than 256 frames, else u16)
and padding to 4 again. Fixed48: a rotation component (q - 32767) / 32767 (w >= 0 made from x, y, z), a vector's
q - 255 (scale 256 = 1; checked against the same bones' Float96 tracks in other clips). Keys between frames are
interpolated linearly (rotations normalised).
Checked on the 16 clips: every one of their 2228 tracks ends exactly where the next one starts; frame tables start
at 0, end at the last frame and increase; untimed multi-key tracks have one key a frame.

Written for this project from the files themselves (no third-party code).
"""
import struct

import numpy as np

from .mesh import Reader

FLOAT96, FIXED48, INTERVAL32 = 1, 2, 3
CODEC = 'AnimCompress_PerTrackCompression'   # (its objects' names: _1, _2)
FIXED48_ROTATION = 32767.0
FIXED48_VECTOR = 255.0
INTERVAL_BITS = (10, 11, 11)        # a vector's x, y, z widths in an IntervalFixed32 key (x the top bits: unverified;
                                    # the one such track, a hidden dambe's scale, reads 0.0001..0.001 either way)


class Clip:
    """A decoded clip: frames, tracks {skeleton bone: (translation (F, 3) or None, rotation (F, 4) x y z w or None,
    scale (F, 3) or None)}."""

    def __init__(self, frames, tracks):
        self.frames, self.tracks = frames, tracks


def _fstring(b, p):
    n, = struct.unpack_from('<i', b, p)
    if n >= 0:
        return b[p + 4:p + 4 + n].rstrip(b'\0').decode('latin-1'), p + 4 + n
    return b[p + 4:p + 4 - 2 * n].decode('utf-16-le').rstrip('\0'), p + 4 - 2 * n


def layout(b, end):
    """Where an AnimSequence export's parts are (b: the export's bytes, end: where its properties end)."""
    p = end
    flag, = struct.unpack_from('<I', b, p)
    p += 4 + (16 if flag else 0) + 16 + 2
    compressed, = struct.unpack_from('<I', b, p)
    if compressed != 1:
        raise ValueError('an animation without compressed data')
    p += 4
    _, n = struct.unpack_from('<ii', b, p)
    p += 8
    track_map = list(struct.unpack_from('<%di' % n, b, p))
    p += 4 * n
    curves, = struct.unpack_from('<i', b, p)
    if curves:
        raise ValueError('an animation with %d curves (not read)' % curves)
    stream_bytes, _ = struct.unpack_from('<iI', b, p + 4)
    stream = p + 12
    p = stream + stream_bytes
    codec, p = _fstring(b, p)
    if not codec.startswith(CODEC):
        raise ValueError('codec %s (only %s is read)' % (codec, CODEC))
    _, p = _fstring(b, p)
    curve_bytes, = struct.unpack_from('<i', b, p)
    p += 4 + curve_bytes
    frames, = struct.unpack_from('<i', b, p)
    data_bytes, ntrack, nscale, strip, _ = struct.unpack_from('<5i', b, p + 8)
    if 4 * ntrack + 4 * nscale + data_bytes != stream_bytes or ntrack != 2 * len(track_map):
        raise ValueError('an animation stream of an unknown layout')
    return dict(track_map=track_map, stream=stream, frames=frames, data_bytes=data_bytes, ntrack=ntrack,
                nscale=nscale, strip=strip)


def _interval(raw):
    """u32 keys -> (n, 3) fractions 0..1 (INTERVAL_BITS)."""
    bx, by, bz = INTERVAL_BITS
    z = raw & ((1 << bz) - 1)
    y = (raw >> bz) & ((1 << by) - 1)
    x = (raw >> (bz + by)) & ((1 << bx) - 1)
    return np.stack([x / ((1 << bx) - 1), y / ((1 << by) - 1), z / ((1 << bz) - 1)], 1)


def read_track(d, off, frames, rotation):
    """One track at data offset off -> ((frames, 3 or 4) values, the offset after it)."""
    h, = struct.unpack_from('<I', d, off)
    keys, flags, fmt = h & 0xFFFFFF, (h >> 24) & 15, h >> 28
    comps = [c for c in range(3) if flags >> c & 1]
    p = off + 4
    vals = np.zeros((keys, 3))
    if fmt == FLOAT96:
        raw = np.frombuffer(d, '<f4', keys * len(comps), p).reshape(keys, len(comps)).astype(np.float64)
        p += 4 * raw.size
        vals[:, comps] = raw
    elif fmt == FIXED48:
        raw = np.frombuffer(d, '<u2', keys * len(comps), p).reshape(keys, len(comps)).astype(np.float64)
        p += 2 * raw.size
        vals[:, comps] = (raw - FIXED48_ROTATION) / FIXED48_ROTATION if rotation else raw - FIXED48_VECTOR
    elif fmt == INTERVAL32:
        mr = struct.unpack_from('<%df' % (2 * len(comps)), d, p)
        p += 8 * len(comps)
        q = _interval(np.frombuffer(d, '<u4', keys, p).astype(np.int64))
        p += 4 * keys
        for i, c in enumerate(comps):
            vals[:, c] = mr[2 * i] + mr[2 * i + 1] * q[:, c]
    else:
        raise ValueError('track format %d at %d' % (fmt, off))
    p = (p + 3) & ~3
    at = None
    if flags & 8:
        if frames < 256:
            at = np.frombuffer(d, np.uint8, keys, p).astype(np.float64)
            p += keys
        else:
            at = np.frombuffer(d, '<u2', keys, p).astype(np.float64)
            p += 2 * keys
        p = (p + 3) & ~3
    if rotation:
        w = np.sqrt(np.clip(1.0 - (vals ** 2).sum(1), 0.0, 1.0))
        vals = np.concatenate([vals, w[:, None]], 1)
    if keys == 1:
        out = np.repeat(vals, frames, 0)
    elif at is None and keys == frames:
        out = vals
    else:
        t = np.linspace(0, frames - 1, keys) if at is None else at
        out = np.stack([np.interp(np.arange(frames), t, vals[:, c]) for c in range(vals.shape[1])], 1)
    if rotation:
        out = out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
    return out, p


def decode(b, end):
    """An AnimSequence export's bytes (b) whose properties end at `end` -> Clip."""
    L = layout(b, end)
    s = L['stream']
    offs = struct.unpack_from('<%di' % L['ntrack'], b, s)
    soffs = struct.unpack_from('<%di' % L['nscale'], b, s + 4 * L['ntrack']) if L['nscale'] else ()
    first = s + 4 * L['ntrack'] + 4 * L['nscale']
    d = bytes(b[first:first + L['data_bytes']])
    frames = L['frames']
    tracks = {}
    for t, bone in enumerate(L['track_map']):
        to, ro = offs[2 * t], offs[2 * t + 1]
        so = soffs[t] if L['strip'] == 1 and t < len(soffs) else -1
        tracks[bone] = (read_track(d, to, frames, False)[0] if to >= 0 else None,
                        read_track(d, ro, frames, True)[0] if ro >= 0 else None,
                        read_track(d, so, frames, False)[0] if so >= 0 else None)
    return Clip(frames, tracks)


def read_clip(store, path):
    """The AnimSequence at path (tekken8.store.Store) -> Clip."""
    from . import uprops
    pkg = store.package(path)
    ex = next((e for e in pkg.exports if e.class_name == 'AnimSequence'), None)
    if ex is None:
        raise ValueError('%s has no AnimSequence' % path)
    _, end = uprops.read(pkg, ex)
    return decode(bytes(pkg.data[ex.offset:ex.offset + ex.size]), end)


def read_skeleton(store, path):
    """The USkeleton at path -> {'names', 'parents', 'pose' (n, 10) float64}."""
    from . import uprops
    pkg = store.package(path)
    ex = next((e for e in pkg.exports if e.class_name == 'Skeleton'), None)
    if ex is None:
        raise ValueError('%s has no Skeleton' % path)
    _, end = uprops.read(pkg, ex)
    r = Reader(pkg, ex.offset + end, ex.offset + ex.size)
    if r.u32():
        r.take('16s')
    bones = [(r.fname(), r.i32()) for _ in range(r.count(65535))]
    n = r.count(65535)
    if n != len(bones):
        raise ValueError('%s: %d bones, %d poses' % (path, len(bones), n))
    pose = np.array(r.take('%dd' % (10 * n)), np.float64).reshape(n, 10)
    return {'names': [b[0] for b in bones], 'parents': [b[1] for b in bones], 'pose': pose}


def local_poses(clip, skeleton):
    """(frames, bones, 10) local poses of a clip on its skeleton: a bone without a track keeps the reference pose; a
    track without translation / rotation data has 0 / the identity there, without scale the reference pose's."""
    P = np.repeat(np.asarray(skeleton['pose'], np.float64)[None], clip.frames, 0)
    for bone, (tr, rot, sc) in clip.tracks.items():
        P[:, bone, 4:7] = 0.0 if tr is None else tr
        P[:, bone, 0:4] = (0.0, 0.0, 0.0, 1.0) if rot is None else rot
        if sc is not None:
            P[:, bone, 7:10] = sc
    return P
