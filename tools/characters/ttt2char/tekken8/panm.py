"""Tekken 8 animations ('PANM'): the blobs of the animation banks (anmbin.py), decoded to per-joint local transforms
per frame.

A blob is a FlatBuffers buffer (little-endian; a table's field k is vtable slot 4 + 2k, an offset field points at
field position + u32): u32 root table offset, then the identifier 'PANM' at +4.
    Root        f2 u8 version (1)       f3 -> Animation
    Animation   f1 u32 last frame (samples = last + 1)          f2 f32 frames per second (60 in every blob seen)
                f3 u32 (1)              f4 [Group]              f5 u32 data block offset (from the blob's start)
                f6 u32 data block size (f5 + f6 = the blob's size)          f7 = f9 = f6, f8 0, f10 a table of no use
    Group       f1 u32 kind (1 joints, 5 camera)                f2 [Node]
    Node        f1 string: the joint's name (the fighter's skeleton's, SKB_CH_<code>_base_msl)        f2 [Track]
    Track       f1 string channel ('Transform', 'FieldOfView')   f2 u32 value type (1 transform, 3 float)
                f3 u32 storage (1 raw: a sample per frame, 2 constant: one sample, 3 quantised)
                f4 u32 sample count         f5 -> flags {f1 0x01 translation not stored (always 0: the skeleton's),
                f2 0x02 rotation not stored (identity), f3 0x04, f4 0x08 (older animations), f8 0x80 (newer ones)}
                f6 u32 the data's offset in the data block       f7 u32 its size
A transform sample is 11 f32: scale x y z, rotation quaternion x y z w, translation x y z (cm), 0. Values are local
to the parent joint, in the skeleton's joint frames (Y up, x the fighter's left, z forward; a joint's x axis along
its bone), the quaternion's matrix (column vectors) is the joint's local rotation.
Quantised data (little-endian): u16 version 4, u16 channel mask (0x01 scale, 0x02 uniform scale, 0x04 rotation,
0x08 translation), u16 offset of the base sample (the frame-0 sample: 11 f32, or 1 for a float), u16 bits per frame,
u32 stream offset, u32 frames, then 9 channel records (1 for a float) of 16 bytes {f32 min, f32 max, u32 bits, u32 0}:
scale x y z, rotation x y z, translation x y z. A frame is `bits per frame` bits of the stream, LSB first: scale
(one field, scale x, when 0x02 is set, else three), rotation x y z, translation x y z, then one bit, the sign of the
rotation's w (1: negative); a field of n bits holds q: value = min + (max - min) q / (2^n - 1) (n = 0: min), w =
sign sqrt(1 - x^2 - y^2 - z^2). Channels the mask leaves out keep the base sample's value; a float track always reads
its one channel. (Every one of the 4017 blobs of Reina's two banks decodes so, each track's bits and bytes adding
up exactly.)
Body animations (category 0): root motion in Top (the ground displacement x, z from the move's start, y 0), Trans
(the hips' position: Top + Trans is where Rot, Spine1 and the 'hara' of TTT2's skeletons are), Rot (the pelvis's
rotation; it carries the whole body), MUKI (the facing: a yaw, applied to the player, not to the joints below Rot);
Hip is constant. Joints no skeleton has are logic channels the game reads by name: in the older ('legacy',
quantised) animations of the shared bank, which were made from Tekken 7 / TTT2 animations, HARA_ROT1, MUNE_jnt and
KOSI_NULL2 hold TTT2's channels 3, 4 and 6 unchanged, and Top / Trans / MUKI are its channels 0, 1, 2 (/ 10: cm).

Written for this project from the files themselves (no third-party code).
"""
import struct

import numpy as np

IDENTIFIER = b'PANM'
TRANSFORM, FLOAT = 1, 3
RAW, CONSTANT, QUANTISED = 1, 2, 3
NO_TRANSLATION, NO_ROTATION, LEGACY_A, LEGACY_B, NEW = 0x01, 0x02, 0x04, 0x08, 0x80
SAMPLE = 11                                     # floats in a transform sample
FPS = 60.0                                      # TTT2's (and Tekken 7's) one animation frame per game tick
# quantised channel mask bits
Q_SCALE, Q_UNIFORM, Q_ROTATION, Q_TRANSLATION = 0x01, 0x02, 0x04, 0x08
Q_VERSION = 4


class FlatBuffer:
    """Field access to a FlatBuffers buffer (no schema)."""

    def __init__(self, b):
        self.b = b

    def u16(self, o):
        return struct.unpack_from('<H', self.b, o)[0]

    def u32(self, o):
        return struct.unpack_from('<I', self.b, o)[0]

    def i32(self, o):
        return struct.unpack_from('<i', self.b, o)[0]

    def root(self):
        return self.u32(0)

    def field(self, t, k):
        """The position of table t's field k, or None when it is absent."""
        vt = t - self.i32(t)
        if 4 + 2 * k >= self.u16(vt):
            return None
        o = self.u16(vt + 4 + 2 * k)
        return t + o if o else None

    def ref(self, position):
        return position + self.u32(position)

    def scalar(self, t, k, fmt='<I', default=0):
        f = self.field(t, k)
        return struct.unpack_from(fmt, self.b, f)[0] if f is not None else default

    def table(self, t, k):
        f = self.field(t, k)
        return self.ref(f) if f is not None else None

    def string(self, t, k):
        f = self.field(t, k)
        if f is None:
            return None
        s = self.ref(f)
        return bytes(self.b[s + 4:s + 4 + self.u32(s)]).decode('utf-8', 'replace')

    def tables(self, t, k):
        f = self.field(t, k)
        if f is None:
            return []
        v = self.ref(f)
        return [self.ref(v + 4 + 4 * i) for i in range(self.u32(v))]

    def floats(self, t, k, defaults):
        """A sub-table of float fields 0..n-1 (vectors and quaternions of the Phoenix assets), or None."""
        s = self.table(t, k)
        if s is None:
            return None
        return tuple(self.scalar(s, j, '<f', d) for j, d in enumerate(defaults))


# ------------------------------------------------------------------------------------------------ tracks
class Track:
    __slots__ = ('group', 'node', 'channel', 'vtype', 'storage', 'count', 'flags', 'data')

    def __repr__(self):
        return '<Track %s.%s type %d storage %d n %d flags %#x %d bytes>' % (
            self.node, self.channel, self.vtype, self.storage, self.count, self.flags, len(self.data))

    def values(self, frames=None):
        """float64 (samples, 11) for a transform, (samples, 1) for a float; a constant track repeated to `frames`
        samples when given."""
        width = SAMPLE if self.vtype == TRANSFORM else 1
        if self.storage in (RAW, CONSTANT):
            if len(self.data) < 4 * width * self.count:
                raise ValueError('track %s.%s: %d bytes for %d samples' % (self.node, self.channel, len(self.data),
                                                                           self.count))
            v = np.frombuffer(self.data, '<f4', self.count * width).reshape(self.count, width).astype(np.float64)
        elif self.storage == QUANTISED:
            v = dequantise(self.data, width)
        else:
            raise ValueError('track %s.%s: storage %d is not known' % (self.node, self.channel, self.storage))
        if frames is not None and len(v) == 1:
            v = np.repeat(v, frames, 0)
        return v


def dequantise(d, width):
    """Quantised track data -> float64 (frames, width) (see the module docstring)."""
    if len(d) < 16:
        raise ValueError('quantised track of %d bytes' % len(d))
    version, mask, base_at, bpf, stream_at, n = struct.unpack_from('<4H2I', d)
    if version != Q_VERSION:
        raise ValueError('quantised track version %d' % version)
    nch = 9 if width == SAMPLE else 1
    ch = [struct.unpack_from('<2f2I', d, 16 + 16 * i) for i in range(nch)]
    base = np.array(struct.unpack_from('<%df' % width, d, base_at), np.float64)
    need = (n * bpf + 7) // 8
    if stream_at + need > len(d):
        raise ValueError('quantised track: %d frames of %d bits do not fit' % (n, bpf))
    bits = np.unpackbits(np.frombuffer(d, np.uint8, need, stream_at), bitorder='little')[:n * bpf].reshape(n, bpf)
    out = np.tile(base, (n, 1))
    pos = [0]

    def field(width_bits):
        p = pos[0]
        pos[0] += width_bits
        if width_bits == 0:
            return np.zeros(n)
        w = bits[:, p:p + width_bits].astype(np.int64)
        return (w << np.arange(width_bits, dtype=np.int64)).sum(1).astype(np.float64)

    def take(i):
        lo, hi, nb, _ = ch[i]
        q = field(nb)
        return lo + (hi - lo) * q / ((1 << nb) - 1) if nb else np.full(n, float(lo))

    if width == 1:
        out[:, 0] = take(0)
    else:
        if mask & Q_SCALE:
            if mask & Q_UNIFORM:
                out[:, 0:3] = take(0)[:, None]
            else:
                for c in range(3):
                    out[:, c] = take(c)
        if mask & Q_ROTATION:
            for c in range(3):
                out[:, 3 + c] = take(3 + c)
        if mask & Q_TRANSLATION:
            for c in range(3):
                out[:, 7 + c] = take(6 + c)
        if mask & Q_ROTATION:
            sign = np.where(field(1) == 1, -1.0, 1.0)
            xyz = out[:, 3:6]
            out[:, 6] = sign * np.sqrt(np.maximum(0.0, 1.0 - (xyz * xyz).sum(1)))
            out[:, 3:7] /= np.linalg.norm(out[:, 3:7], axis=1, keepdims=True)    # quantised x y z can pass 1
    if pos[0] != bpf:
        raise ValueError('quantised track: %d of %d bits a frame read' % (pos[0], bpf))
    return out


class Joint:
    """One joint's transform track: rotation (frames, 4) quaternions x y z w, translation (frames, 3) cm, scale
    (frames, 3); stored_translation / stored_rotation: False when the track leaves them to the skeleton."""
    __slots__ = ('rotation', 'translation', 'scale', 'stored_translation', 'stored_rotation', 'storage')

    def __init__(self, values, flags, storage):
        self.scale = values[:, 0:3]
        self.rotation = values[:, 3:7]
        self.translation = values[:, 7:10]
        self.stored_translation = not flags & NO_TRANSLATION
        self.stored_rotation = not flags & NO_ROTATION
        self.storage = storage


def frame_count(blob):
    """The clip's sample count (its last frame number + 1) from its header alone (what a move's animation length
    is made of)."""
    blob = bytes(blob)
    if len(blob) < 8 or blob[4:8] != IDENTIFIER:
        raise ValueError('not a PANM animation')
    f = FlatBuffer(blob)
    an = f.table(f.root(), 3)
    if an is None:
        raise ValueError('PANM without an animation')
    return f.scalar(an, 1) + 1


class Animation:
    """A decoded PANM blob: .frames, .fps, .tracks [Track], .joints() {name: Joint} at 60 frames a second."""

    def __init__(self, blob):
        blob = bytes(blob)
        if len(blob) < 8 or blob[4:8] != IDENTIFIER:
            raise ValueError('not a PANM animation')
        f = FlatBuffer(blob)
        root = f.root()
        self.version = f.scalar(root, 2, '<B')
        an = f.table(root, 3)
        if an is None:
            raise ValueError('PANM without an animation')
        self.frames = f.scalar(an, 1) + 1
        self.fps = f.scalar(an, 2, '<f', FPS)
        data_at, data_size = f.scalar(an, 5), f.scalar(an, 6)
        if data_at + data_size > len(blob):
            raise ValueError('PANM data block (%d + %d bytes) outside the blob (%d)' % (data_at, data_size, len(blob)))
        self.tracks = []
        for g in f.tables(an, 4):
            kind = f.scalar(g, 1)
            for node in f.tables(g, 2):
                name = f.string(node, 1)
                for tr in f.tables(node, 2):
                    t = Track()
                    t.group, t.node, t.channel = kind, name, f.string(tr, 1)
                    t.vtype, t.storage, t.count = f.scalar(tr, 2), f.scalar(tr, 3), f.scalar(tr, 4)
                    t.flags = 0
                    fl = f.table(tr, 5)
                    if fl is not None:
                        for k, bit in ((1, 0x01), (2, 0x02), (3, 0x04), (4, 0x08), (8, 0x80)):
                            if f.scalar(fl, k, '<B'):
                                t.flags |= bit
                    o = data_at + f.scalar(tr, 6)
                    t.data = blob[o:o + f.scalar(tr, 7)]
                    self.tracks.append(t)

    @property
    def legacy(self):
        """Made from an older game's animation (quantised tracks; TTT2's channels in HARA_ROT1 / KOSI_NULL2)."""
        return any(t.storage == QUANTISED for t in self.tracks if t.vtype == TRANSFORM)

    def joints(self, fps=FPS):
        """{joint name: Joint} of the transform tracks, every track `frames` samples long (resampled to `fps`)."""
        out = {}
        for t in self.tracks:
            if t.vtype == TRANSFORM and t.channel == 'Transform':
                v = t.values(self.frames)
                if len(v) != self.frames:
                    raise ValueError('track %s: %d samples for %d frames' % (t.node, len(v), self.frames))
                if fps and self.fps and abs(self.fps - fps) > 1e-3:
                    v = resample(v, self.fps, fps)
                out[t.node] = Joint(v, t.flags, t.storage)
        return out

    def frames_at(self, fps=FPS):
        if not fps or not self.fps or abs(self.fps - fps) <= 1e-3:
            return self.frames
        return int(round((self.frames - 1) * fps / self.fps)) + 1


def resample(values, src_fps, fps=FPS):
    """Transform samples (frames, 11) at src_fps -> at fps: linear for scale and translation, normalised linear
    (shorter arc) for the rotation."""
    v = np.asarray(values, np.float64)
    n = len(v)
    m = int(round((n - 1) * fps / src_fps)) + 1
    t = np.minimum(np.arange(m) * src_fps / fps, n - 1)
    i0 = np.minimum(np.floor(t).astype(int), max(n - 2, 0))
    i1 = np.minimum(i0 + 1, n - 1)
    w = (t - i0)[:, None]
    a, b = v[i0], v[i1].copy()
    q_flip = (a[:, 3:7] * b[:, 3:7]).sum(1) < 0
    b[q_flip, 3:7] *= -1
    out = a * (1 - w) + b * w
    q = out[:, 3:7]
    out[:, 3:7] = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    return out
