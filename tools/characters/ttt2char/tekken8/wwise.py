"""Tekken 8 PC's Wwise sound data (Wwise's Unreal Engine 5 integration, bank version 145), read-only.

Tekken 7 kept a fighter's voice in one bank with the audio inside (tekken7/wwise.py); Tekken 8 has one small bank
per event and its audio as loose files, both in the pak files (store.Store reads them):
    Polaris/Content/WwiseAudio/Event/<event name>.bnk     the event's bank (the name as the game spells it:
                                                           Play_ZBR_Attack_S_001, Play_zbr_win_00)
    Polaris/Content/WwiseAudio/Media/<media id>.wem       a medium, by its id in decimal
    bank: chunks {4-byte tag, u32 size} (little-endian): BKHD (u32 version, u32 bank id = the event's id, ...),
          HIRC (u32 count, objects {u8 type, u32 size, u32 id, body}); no DIDX/DATA (no media inside)
    HIRC: type 4 event (u8 action count (version 118, Tekken 7's: u32), u32 action ids), type 3 action (u16
          action type: 0x04xx Play, 0x05xx Play and continue; u32 target: a sound or a container), type 2 sound
          (u32 codec plugin: 0x00010001 PCM; u8 stream type; u32 media id; u32 media size; ...), containers whose
          bodies list their children by id: 5 random/sequence, 6 switch, 9 layer (sounds that play together: an
          intro's or win pose's voice line, mono, with its foley track, stereo), 7 actor-mixer (parents)
    ids are not names: an event's (and its bank's) is the 32-bit FNV-1 hash of its lower-case name
A medium is a RIFF WAVE file: format tag 0xFFFE (WAVE_FORMAT_EXTENSIBLE; cbSize 6 holding Wwise's channel
configuration) or 1, 16-bit little-endian PCM, channels interleaved, in the `data` chunk (also `hash`, `junk`
chunks). Every fighter's voice is PCM at 48, 36 or 32 kHz; other codecs are refused (ValueError).

Written for this project from the files themselves (no third-party code).
"""
import struct

import numpy as np

EVENT_BANK = 'Polaris/Content/WwiseAudio/Event/%s.bnk'
MEDIA = 'Polaris/Content/WwiseAudio/Media/%d.wem'
SOUND, ACTION, EVENT = 2, 3, 4
CONTAINERS = (5, 6, 9)                      # random/sequence, switch, layer: their children are sounds or containers
PLAY_ACTIONS = (0x0400, 0x0500)             # Play, Play and continue (action type & 0xFF00); others (Stop, ...) not
PCM_PLUGIN = 0x00010001
PCM_TAGS = (1, 0xFFFE)                      # WAVE_FORMAT_PCM, WAVE_FORMAT_EXTENSIBLE (Wwise's)
MAX_DEPTH = 6                               # containers inside containers followed this deep


def fnv(name):
    """A Wwise object id: FNV-1 (32 bits) of the lower-case name."""
    h = 2166136261
    for c in name.lower().encode('latin1'):
        h = ((h * 16777619) & 0xFFFFFFFF) ^ c
    return h


def _chunks(d, pos, align):
    out = {}
    while pos + 8 <= len(d):
        tag, size = d[pos:pos + 4], struct.unpack_from('<I', d, pos + 4)[0]
        out.setdefault(tag, (pos + 8, size))
        pos += 8 + size + (size & 1 if align else 0)
    return out


# ---------------------------------------------------------------------------------------------------- banks
class Bank:
    def __init__(self, d):
        self.d = d
        self.ch = _chunks(d, 0, False)
        if b'BKHD' not in self.ch or self.ch[b'BKHD'][1] < 8:
            raise ValueError('not a Wwise sound bank')
        self.version, self.bank_id = struct.unpack_from('<II', d, self.ch[b'BKHD'][0])
        self.objects = {}
        if b'HIRC' in self.ch:
            p, size = self.ch[b'HIRC']
            end = min(p + size, len(d))
            n, = struct.unpack_from('<I', d, p)
            q = p + 4
            for _ in range(n):
                if q + 9 > end:
                    raise ValueError('the bank\'s object list is cut short')
                kind, size, oid = struct.unpack_from('<BII', d, q)
                self.objects[oid] = (kind, d[q + 9:q + 5 + size])
                q += 5 + size

    def has_event(self, name):
        o = self.objects.get(fnv(name))
        return o is not None and o[0] == EVENT

    def actions(self, name):
        """An event's action ids. The count is a u8 in version 145 (a u32 in Tekken 7's 118): the body is exactly
        the count and the ids, which tells the two apart."""
        kind, body = self.objects.get(fnv(name), (None, None))
        if kind != EVENT:
            raise KeyError(name)
        if body and len(body) == 1 + 4 * body[0]:
            return list(struct.unpack_from('<%dI' % body[0], body, 1))
        n, = struct.unpack_from('<I', body, 0) if len(body) >= 4 else (0,)
        if len(body) != 4 + 4 * n:
            raise ValueError('event %s: an action list of %d bytes' % (name, len(body)))
        return list(struct.unpack_from('<%dI' % n, body, 4))

    def event_sounds(self, name):
        """The sound objects an event's Play actions reach (through containers), in order."""
        out = []
        for aid in self.actions(name):
            akind, abody = self.objects.get(aid, (None, b''))
            if akind != ACTION or len(abody) < 6:
                continue
            atype, target = struct.unpack_from('<HI', abody, 0)
            if atype & 0xFF00 not in PLAY_ACTIONS:
                continue
            for s in self._sounds(target, 0):
                if s not in out:
                    out.append(s)
        return out

    def _sounds(self, oid, depth):
        kind, body = self.objects.get(oid, (None, b''))
        if kind == SOUND:
            return [oid]
        if kind not in CONTAINERS or depth > MAX_DEPTH:
            return []
        out = []
        # the children: the ids of sounds and containers of this bank in the body, in order (the body's other
        # fields are small numbers, floats and ids of objects in other banks: busses, the actor-mixer parent)
        for off in range(len(body) - 3):
            v, = struct.unpack_from('<I', body, off)
            if v != oid and v not in out and self.objects.get(v, (None,))[0] in (SOUND,) + CONTAINERS:
                out += [s for s in self._sounds(v, depth + 1) if s not in out]
        return out

    def sound(self, oid):
        """A sound object -> (codec plugin id, stream type, media id, media size)."""
        kind, body = self.objects[oid]
        if kind != SOUND:
            raise KeyError(oid)
        return struct.unpack_from('<IBII', body, 0)

    def event_media(self, name):
        """The media ids an event plays, in order."""
        out = []
        for s in self.event_sounds(name):
            media = self.sound(s)[2]
            if media not in out:
                out.append(media)
        return out


# ---------------------------------------------------------------------------------------------------- media
def wem_format(w):
    """A WEM's (format tag, channels, sample rate, bits per sample) from its header."""
    if w[:4] != b'RIFF' or w[8:12] != b'WAVE':
        raise ValueError('not a WEM file')
    c = _chunks(w, 12, True)
    if b'fmt ' not in c:
        raise ValueError('a WEM file without a format')
    tag, channels, rate, _, _, bits = struct.unpack_from('<HHIIHH', w, c[b'fmt '][0])
    return tag, channels, rate, bits


def decode_wem(w):
    """A PCM WEM -> (sample rate, int16 array [channels, samples])."""
    tag, channels, rate, bits = wem_format(w)
    if tag not in PCM_TAGS or bits != 16 or not channels:
        raise ValueError('WEM codec %#x (%d bits) is not 16-bit PCM' % (tag, bits))
    c = _chunks(w, 12, True)
    if b'data' not in c:
        raise ValueError('a WEM file without audio')
    p, size = c[b'data']
    n = min(size, len(w) - p) // (2 * channels)
    a = np.frombuffer(w, '<i2', n * channels, p)
    return rate, a.reshape(n, channels).T.astype(np.int16)


class Events:
    """Events of the installation by name (store: store.Store): their banks and media."""

    def __init__(self, store):
        self.store = store

    def path(self, name):
        """The event's bank as the store names it, or None."""
        return self.store.file_path(EVENT_BANK % name)

    def name(self, name):
        """The event's name as the game spells it (its bank's file name), or None."""
        p = self.path(name)
        return p.rsplit('/', 1)[-1][:-4] if p else None

    def media(self, name):
        """The media ids event `name` plays, in order; KeyError when it has no bank."""
        p = self.path(name)
        if p is None:
            raise KeyError(name)
        return Bank(self.store.read(p)).event_media(name)

    def wem(self, media):
        """A medium's bytes; KeyError when the installation has none."""
        return self.store.read(MEDIA % media)
