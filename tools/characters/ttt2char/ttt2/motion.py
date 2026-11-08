"""Animations: MOTA containers, TTT2's motion packs, and the byte-order conversion of one animation (Tekken 7 PC
stores them little-endian, the Wii U big-endian; the animations themselves are the same format).

Motion pack (data005: one per motion row): little-endian u32 count (6), count x {u32 offset, u32 size}, items
16-byte aligned from 0x40: body MOTA, hands, face, (empty), camera, extra.
MOTA: "MOTA", u8, u8 (byte order: 0 1 big-endian, 1 0 little-endian), u16, u32 0x14, u32 count @0xC, u32, then
count x u32 offsets (from the MOTA's start) at 0x14.
Hands (item 1: the fingers' animations, which moves play with 0x82db / 0x82dc, value 0x4000 | number): little-endian
u16 1, u16 count, u16 15, u16 15, count x u32 offsets (from the item's start; numbers may share one), the fingers'
15 joints (15 x u16 8, then 0..14), then the animations (u16 frames, ...), 4-aligned; an animation holds no offsets
(the same bytes stand at other offsets in other fighters' packs).
Animation: u16 type, u16 channel count, then
    type 0xC8 (raw): u32 frames, nch x u32 descriptors, frames x nch x 3 f32
    type 0x64 (compressed): nch x u16 descriptors, u16 frames, u8, u8, u16 n, n x u32, per channel 3 x i16
        (descriptors 4..7) or 3 x f32 (others), ((frames + 14) >> 4) x u32 keyframe offsets, then a byte stream.
"""
import array
import struct


def pack_items(d):
    """[(offset, size)] of a motion pack's items."""
    n, = struct.unpack_from('<I', d, 0)
    return [struct.unpack_from('<II', d, 4 + 8 * k) for k in range(n)]


def build_pack(items):
    out = bytearray(0x40)
    struct.pack_into('<I', out, 0, len(items))
    for k, it in enumerate(items):
        while len(out) % 16:
            out.append(0)
        struct.pack_into('<II', out, 4 + 8 * k, len(out), len(it))
        out += it
    return bytes(out)


def mota_offsets(b, o=0):
    """(byte order, [animation offsets]) of the MOTA at b[o:]."""
    if b[o:o + 4] != b'MOTA':
        raise ValueError('not a MOTA')
    e = '<' if b[o + 4] == 1 else '>'
    cnt, = struct.unpack_from(e + 'I', b, o + 0xC)
    return e, list(struct.unpack_from(e + '%dI' % cnt, b, o + 0x14)) if cnt else []


def extend_mota(m, anims):
    """A big-endian MOTA with big-endian animations appended (each padded to 4)."""
    if m[:4] != b'MOTA' or m[4] != 0:
        raise ValueError('not a big-endian MOTA')
    cnt, = struct.unpack_from('>I', m, 0xC)
    offs = list(struct.unpack_from('>%dI' % cnt, m, 0x14))
    data_start = 0x14 + 4 * cnt
    if cnt and offs[0] != data_start:
        raise ValueError('MOTA animations do not follow its offsets')
    body = bytearray(m[data_start:])
    while len(body) % 4:
        body.append(0)
    n2 = cnt + len(anims)
    new_offs = [o + 4 * len(anims) for o in offs]
    at = 0x14 + 4 * n2 + len(body)
    for a in anims:
        new_offs.append(at)
        a = bytes(a) + bytes(-len(a) % 4)
        body += a
        at += len(a)
    hdr = bytearray(m[:0x14])
    struct.pack_into('>I', hdr, 0xC, n2)
    return bytes(hdr) + struct.pack('>%dI' % n2, *new_offs) + bytes(body)


def replace_mota(m, anims):
    """A big-endian MOTA with m's header and only `anims` (big-endian)."""
    if m[:4] != b'MOTA' or m[4] != 0:
        raise ValueError('not a big-endian MOTA')
    return extend_mota(m[:0xC] + bytes(4) + m[0x10:0x14], anims)


HANDS_HEADER = 8


def _hands(h):
    """(count, [offsets], where the offsets end) of a hands container."""
    one, cnt = struct.unpack_from('<HH', h, 0)
    offs = list(struct.unpack_from('<%dI' % cnt, h, HANDS_HEADER))
    end = HANDS_HEADER + 4 * cnt
    if one != 1 or any(o < end or o >= len(h) for o in offs):
        raise ValueError('not a hands container')
    return cnt, offs, end


def hand_animations(h):
    """[bytes] of a hands container's animations, by number (each to where the next one starts)."""
    _, offs, _ = _hands(h)
    starts = sorted(set(offs)) + [len(h)]
    size = {a: b - a for a, b in zip(starts, starts[1:])}
    return [bytes(h[o:o + size[o]]) for o in offs]


def extend_hands(h, anims):
    """A hands container with animations appended (numbered from its count on, each padded to 4)."""
    cnt, offs, end = _hands(h)
    body = bytearray(h[end:])
    while len(body) % 4:
        body.append(0)
    new_offs = [o + 4 * len(anims) for o in offs]
    at = end + 4 * len(anims) + len(body)
    for a in anims:
        new_offs.append(at)
        a = bytes(a) + bytes(-len(a) % 4)
        body += a
        at += len(a)
    hdr = bytearray(h[:HANDS_HEADER])
    struct.pack_into('<H', hdr, 2, len(new_offs))
    return bytes(hdr) + struct.pack('<%dI' % len(new_offs), *new_offs) + bytes(body)


# ------------------------------------------------------------------------------------------------ hand animations
# A hand animation (little-endian; the moveset's hand shapes, slot 2, are a hands container of one too), n = 45 values
# (15 joints: thumb, index, middle, ring, little, each 3, 2, 1 from the hand out, x y z, the bone's local rotation as
# 0x64's axis-angle, i16 = 2 pi / 65536): u16 frames, n x i16 frame 0, n x i16 the last frame, ((frames + 14) >> 4) x
# u16 word offsets (x 2 = bytes from the animation's start) of a block for frames 1..16, 17..32, ... Each value of a
# block starts from its frame 0 value, in a chunk: u16, its low 9 bits the chunk's length in words with this one, its
# high 7 the first bits of an LSB-first stream with the words after it. A frame takes a 4-bit code, or goes on with
# the code before: a code from 8 up is code - 8 for 2 + (next 4 bits) frames. Code 0 keeps the value, 1..6 add
# (6 bits) - 84, (4) - 20, (2) - 4, (2) + 1, (4) + 5, (6) + 21 (x 16), 7 sets it to a signed 12 bits (x 16).
HAND_VALUES = 45
HAND_DELTAS = {1: (6, -84), 2: (4, -20), 3: (2, -4), 4: (2, 1), 5: (4, 5), 6: (6, 21)}


def _s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def _hand_table(frames):
    return (frames + 14) >> 4


def decode_hand_animation(a):
    """(frames, HAND_VALUES) list of a hand animation's i16 values, as the game samples them at whole frames."""
    n = HAND_VALUES
    word = lambda o: struct.unpack_from('<H', a, o)[0] if o + 2 <= len(a) else 0     # (it reads a word ahead)
    frames = word(0)
    first = [_s16(word(2 + 2 * i)) for i in range(n)]
    last = [_s16(word(2 + 2 * n + 2 * i)) for i in range(n)]
    out = [first] if frames > 1 else []
    for b in range(_hand_table(frames)):
        if 16 * b + 1 >= frames - 1:                    # (the last frame stands apart; no block is read for it)
            break
        p = word(2 + 4 * n + 2 * b) * 2
        rows = [[] for _ in range(16)]
        for i in range(n):
            head = word(p)
            nxt, acc, have, q = p + 2 * (head & 0x1FF), head >> 9, 7, p + 2
            val, run, code = first[i], 0, 0
            for step in range(16):
                if 16 * b + step + 1 >= frames - 1:
                    break
                if have < 16:
                    acc += word(q) << have
                    q, have = q + 2, have + 16
                if run == 0:
                    code, acc, have = acc & 15, acc >> 4, have - 4
                    if code >= 8:
                        run, acc, have = (acc & 15) + 1, acc >> 4, have - 4
                        code -= 8
                else:
                    run -= 1
                if code == 7:
                    if have < 12:
                        acc += word(q) << have
                        q, have = q + 2, have + 16
                    x = acc & 0xFFF
                    acc, have = acc >> 12, have - 12
                    val = (x - 0x1000 if x & 0x800 else x) << 4
                elif code:
                    w, base = HAND_DELTAS[code]
                    x = acc & ((1 << w) - 1)
                    acc, have = acc >> w, have - w
                    val = _s16(val + ((x + base) << 4))
                rows[step].append(val)
            p = nxt
        out += [r for r in rows if r]
    return out + [last]


def _hand_chunk(start, targets):
    """A chunk (bytes): the values `targets` from `start`, each within 8 of its target (the stored step is 16)."""
    steps = []                                          # (code, payload bits, width)
    val = start
    for t in targets:
        d = _s16(t - val)
        k = (d + 8) >> 4                                # (the nearest step)
        if k == 0:
            steps.append((0, 0, 0))
        elif -84 <= k <= 84:
            code = next(c for c, (w, base) in HAND_DELTAS.items() if base <= k < base + (1 << w))
            w, base = HAND_DELTAS[code]
            steps.append((code, k - base, w))
            val = _s16(val + (k << 4))
        else:
            x = (t + 8) >> 4
            x = max(-2048, min(2047, x))
            steps.append((7, x & 0xFFF, 12))
            val = x << 4
    bits, width = 0, 0

    def put(v, w):
        nonlocal bits, width
        bits |= v << width
        width += w
    i = 0
    while i < len(steps):
        j = i
        while j + 1 < len(steps) and steps[j + 1][0] == steps[i][0] and j - i < 16:
            j += 1
        count = j - i + 1
        if count >= 3:                                  # (two cost the same either way)
            put(steps[i][0] + 8, 4)
            put(count - 2, 4)
        else:
            count = 1
            put(steps[i][0], 4)
        for code, v, w in steps[i:i + count]:
            put(v, w)
        i += count
    # the header's 7 bits, then whole words
    words = 1 + max(0, width - 7 + 15) // 16
    head = words | (bits & 0x7F) << 9
    bits >>= 7
    return struct.pack('<%dH' % words, head, *[(bits >> (16 * k)) & 0xFFFF for k in range(words - 1)])


def encode_hand_animation(values):
    """A hand animation (bytes) of values (frames, HAND_VALUES) of i16 (decode_hand_animation gives them back within
    8 at the frames between the first and the last, exactly at those two)."""
    v = [[int(x) for x in row] for row in values]
    frames = len(v)
    if not 1 <= frames <= 0xFFFF or any(len(row) != HAND_VALUES for row in v):
        raise ValueError('a hand animation has 1 to 65535 frames of %d values' % HAND_VALUES)
    head = struct.pack('<H', frames) + struct.pack('<%dh' % HAND_VALUES, *v[0]) + \
        struct.pack('<%dh' % HAND_VALUES, *v[-1])
    count = _hand_table(frames)
    at = len(head) + 2 * count
    table, body = [], bytearray()
    for b in range(count):
        table.append((at + len(body)) // 2)
        for i in range(HAND_VALUES):
            body += _hand_chunk(v[0][i], [v[f][i] for f in range(16 * b + 1, min(16 * b + 17, frames - 1))])
    if table and table[-1] > 0xFFFF:
        raise ValueError('a hand animation too long for its offsets')
    return head + struct.pack('<%dH' % count, *table) + bytes(body) + bytes(8)     # (the reader looks a word ahead)


def with_hand_frames(h, frames):
    """A hand shapes container (slot 2: a hands container of one animation) with some of its frames' values replaced
    (frames: {frame: HAND_VALUES values}); the other frames as they decode, each within 8 of what they were."""
    cnt, offs, end = _hands(h)
    if cnt != 1:
        raise ValueError('hand shapes are one animation')
    values = decode_hand_animation(h[offs[0]:])
    for f, row in frames.items():
        values[f] = list(row)
    a = encode_hand_animation(values)
    a += bytes(-len(a) % 4)
    out = bytearray(h[:offs[0]]) + a
    return bytes(out)


def _swap(b, o, w):
    b[o:o + w] = b[o:o + w][::-1]


def swap_animation(src, src_endian):
    """A copy of the animation at the start of src in the other byte order (bytes after its swapped part are
    copied as they are)."""
    e = src_endian
    b = bytearray(src)
    typ, nch = struct.unpack_from(e + 'HH', src, 0)
    if typ == 0x64:
        desc = struct.unpack_from(e + '%dH' % nch, src, 4)
        o = 4 + 2 * nch
        frames, = struct.unpack_from(e + 'H', src, o)
        niter, = struct.unpack_from(e + 'H', src, o + 4)
        for p in range(0, o, 2):
            _swap(b, p, 2)
        _swap(b, o, 2)
        _swap(b, o + 4, 2)
        o += 6
        for _ in range(niter):
            _swap(b, o, 4)
            o += 4
        for d in desc:
            w = 2 if 4 <= d <= 7 else 4
            for _ in range(3):
                _swap(b, o, w)
                o += w
        for _ in range((frames + 14) >> 4):
            _swap(b, o, 4)
            o += 4
        return bytes(b)
    if typ == 0xC8:
        frames, = struct.unpack_from(e + 'I', src, 4)
        _swap(b, 0, 2)
        _swap(b, 2, 2)
        _swap(b, 4, 4)
        words = array.array('I', bytes(b[8:8 + 4 * (nch + frames * nch * 3)]))
        words.byteswap()
        b[8:8 + 4 * len(words)] = words.tobytes()
        return bytes(b)
    raise ValueError('animation type %#x' % typ)
