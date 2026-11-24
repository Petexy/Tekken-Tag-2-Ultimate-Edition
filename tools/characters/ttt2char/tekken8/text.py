"""Tekken 8's text banks: what its subtitles say for a fighter's intro and win lines (convert/subtitles.py).

Tekken 8 keeps its text per language in Polaris/Content/Localize/<language>/GTB_*.uasset (class
GryphonTextBinaryAsset, plugin GryphonLocalization; 95 banks a language, plaintext). A bank's export data: its
DataSize property (6 bytes), then "gbtd", u32 header size (0x40), u16 1, u16 1, u32 1, u32 0, u32 the record count,
zeros to the header's end; then the records (to the data's end), each "text", u32 0x10, u32 the key's size, u32
the text's size (both padded with zeros), 8 bytes (hashes), the key (ASCII), the text (UTF-8).

An intro or win pose's line is the voice event Play_<code>_sta_NN / Play_<code>_win_NN (tekken8/voice.py); its
subtitle is the record TEXT_VO_<update>_<code>_sta_NN_000 (the base roster's in GTB_Ingame_Sub, update 000; a later
fighter's in its update's bank: Clive's TEXT_VO_010_okm_*), spelled TEXT_<update>_VO_<code>_... by some updates.
Variants are left out: lines said against one opponent (..._NN_vrMM_000), the later parts of a line said in parts
(_001 ..: only with variants); a line Tekken 8 shows in two halves (Victor's lon_win_00a / _00b) is its halves
joined. A line with no record (Clive's win_03) has no subtitle.

Written for this project from the files themselves (no third-party code).
"""
import re
import struct

from .voice import POSE_EVENT

FOLDER = 'Polaris/Content/Localize/%s/'
LANGUAGES = ('en', 'fr', 'de', 'it', 'es', 'ja')        # Tekken 8's of the subtitle languages TTT2 shows
MAGIC, RECORD = b'gbtd', b'text'
RECORD_HEADER = 24


def records(data):
    """{key: text} of a text bank's export data (ValueError if it is none)."""
    at = data.find(MAGIC, 0, 64)
    if at < 0:
        raise ValueError('not a Gryphon text bank (no %r)' % MAGIC)
    size, = struct.unpack_from('<I', data, at + 4)
    o, out = at + size, {}
    while data[o:o + 4] == RECORD and o + RECORD_HEADER <= len(data):
        _, key_size, text_size = struct.unpack_from('<3I', data, o + 4)
        if o + RECORD_HEADER + key_size + text_size > len(data):
            raise ValueError('text record %d runs past the bank\'s end' % len(out))
        key = data[o + RECORD_HEADER:o + RECORD_HEADER + key_size].split(b'\0')[0].decode('ascii', 'replace')
        start = o + RECORD_HEADER + key_size
        out[key] = data[start:start + text_size].split(b'\0')[0].decode('utf-8', 'replace')
        o = start + text_size
    return out


def pose_key(code, kind, number):
    """The regular expression of the keys of a pose line's records: groups (update, half, part)."""
    return re.compile(r'^TEXT_(?:VO_)?(\d+)_(?:VO_)?%s_%s_%02d([a-z]?)_(\d{3})$' % (re.escape(code), kind, number),
                      re.I)


def pose_text(texts, code, kind, number):
    """The text of a pose line (code 'okm', kind 'sta' or 'win', its number) in a language's records {key: text},
    or None: the line's own record (_000; the newest update's if several), else its halves (a, b, ...) joined."""
    rx = pose_key(code, kind, number)
    found = {}
    for key, text in texts.items():
        m = rx.match(key)
        if m and text.strip():
            found.setdefault((m.group(2).lower(), int(m.group(3))), []).append((int(m.group(1)), text))
    whole = found.get(('', 0))
    if whole:
        return max(whole)[1]
    halves = sorted(h for h, part in found if h and part == 0)
    if halves:
        return ' '.join(max(found[(h, 0)])[1].strip() for h in halves)
    return None


def pose_lines(store, events, languages=LANGUAGES, log=None):
    """{event name: {language: text}} of intro and win line events ('Play_okm_sta_00') in Tekken 8's text banks
    (store: store.Store), in the languages it has; events with no text are left out. The banks holding the English
    records are read in the other languages too (only those)."""
    wanted = {}
    for event in events:
        m = POSE_EVENT.match(event)
        if m:
            wanted[event] = (m.group(1), m.group(2).lower(), int(m.group(3)))
    if not wanted:
        return {}
    codes = {code.lower() for code, _, _ in wanted.values()}
    out, banks = {}, None
    for lang in languages:
        paths = sorted(p for p in store.find(FOLDER % lang) if p.lower().endswith('.uasset'))
        if banks is not None:
            paths = [p for p in paths if p.rsplit('/', 1)[-1] in banks]
        texts = {}
        holding = set()
        for path in paths:
            try:
                got = records(store.package(path).main_export().data)
            except (KeyError, ValueError, IndexError, struct.error) as error:
                if log:
                    log('Tekken 8 text bank %s not read (%s)' % (path, error))
                continue
            if any(any('_%s_' % c in k.lower() for c in codes) for k in got):
                texts.update(got)
                holding.add(path.rsplit('/', 1)[-1])
        if banks is None:
            banks = holding
        for event, (code, kind, number) in wanted.items():
            text = pose_text(texts, code, kind, number)
            if text:
                out.setdefault(event, {})[lang] = text
        if banks is not None and not banks:
            break
    return out
