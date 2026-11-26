"""The added fighters' intro and win subtitles: their own lines' text in the title's subtitle file.

The donor's intro and win poses an added fighter plays (convert/moveset.py) stream a line of its rm_Dst bank (an
intro: the pose's extra property 0x8300 = 0x0D000000 | n, tone n) or its rm_Dwi bank (a match win: 0x0D001000 | n);
convert/voice.py puts the fighter's own clips on those tones. The pose shows a subtitle with its begin property
0x8180 = fighter id << 8 | k: entry id * 30 + k of the subtitle file (title entry 917395eb), whatever the line says,
so the donor's poses showed the DONOR's text (Lars's first intro line) over the fighter's voice. Each
added fighter now has lines of its own in that file under its own select id (64 + its place): line n for the clip on
rm_Dst tone n, WIN_LINE + n for the one on rm_Dwi tone n (lines_of), with the text its source game shows for that
clip (source.py: Tekken 8's text banks, tekken8/text.py; Tekken 7's subtitle files, tekken7/subtitles.py), and its
poses' 0x8180 name those lines (moveset.rewrite_subtitles); a pose whose clip has no text loses its subtitle (never
the donor's text). The pack keeps its lines (source/subtitles.json: read_lines/dumps) and shared.py writes the file
for every pack together (table: shared/keys/917395eb.bin, which the port serves in place of the title's).

The subtitle file (big-endian): u32 count (the title's: 59 fighter ids x LINES), count x {u32 offset, u32 size}
(from the file's start), then each entry 16-aligned, zero padding; an empty entry is 4 bytes ff (sub_04D32CA8 shows
nothing for it, nor for an index past the count, so ids up to the count are all the file has to cover). An entry is
a language container: u32 16, 16 x {u32 offset, u32 size} (from the container's start), then the text banks, the
first at 0x90; the title shows entry (text language - 1): 0 Japanese, 1 English (2 English again), 3 French,
4 Italian, 5 German, 6 Spanish, 7 Korean, 8 Chinese, 9 Russian, 10-15 unused (" "). The entry shown follows the
game's language (the port's game.ini `language`: English, French, German, Italian, Spanish or Russian), so a line has
a bank in each language its source game has a text in (lines_of: the import reads source.SUBTITLE_LANGUAGES), and
every entry without a text of its own points at the English bank (a line is English where its game has no text).
Polish, which the title has none of, is entry 10 (its bank's language byte 11): the port, with game.ini's Polish,
shows it in the English entry's place (runtime title/subtitles.h); Tekken 8 has its own, a Tekken 7 fighter's is
ours (tekken7/polish.py: Tekken 7 has none).
A text bank (NTXB) of one text: a 0x70-byte header ("NTXB", u16 2, u8 language + 1, u8 1, u32 bank size, the table
offsets 0x30 0x30 0x50 0x60 0x70, the index of its one key with the key's offset at 0x38 and 0x3C, and words this
copies from a bank of the title's own file: template), then the record at 0x70: u32 record size, u16 (a checksum of
the title's tools the game does not read: set to CRC-16/CCITT of the text here), u16 the text's length in UTF-16
units, the text in UTF-8 padded with at least two zero bytes to 4, the key "0" (4 bytes), u32 0, 4 bytes ff (the
record size counts them); ff to a multiple of 16 after 4 more bytes. The text carries the timing (markup): U+FFFB
show U+FFFC hide U+FFF5 U+0001, the line, U+FFFB U+0001 U+FFFC U+FFFF; show and hide are frames (1/60 s) from the
line's start, each one UTF-16 unit (the title's lines: show at the voice's onset, hide about 27 frames after it ends).

The title draws the subtitles with glyph table 46b70814 (the only title font holding every character of its own
subtitles in its languages, Cyrillic too): a character it lacks becomes a plain one (fit: curly quotes straight, an
ellipsis three dots, a dash a hyphen, accents dropped) or is left out, and so does one the port draws as a button icon
in that font (CARRIERS, presentation.cpp: guillemets become straight quotes).

Written for this project from the files themselves (no third-party code, no game data: the template and the font
are read from the player's own game when shared/ is made).
"""
import json
import os
import re
import struct
import unicodedata

import numpy as np

KEY = 0x917395EB                    # the subtitle file's title entry
LINES = 30                          # lines per fighter id (index = id * LINES + line)
WIN_LINE = 10                       # line of rm_Dwi tone 0 (the title's own: Lars's 0x260A, Jun's 0x2A0A)
LANGUAGES = 16                      # entries of a language container
ENGLISH = 1                         # the entry every language without a text of its own shows
ENTRY = {'ja': 0, 'en': 1, 'fr': 3, 'it': 4, 'de': 5, 'es': 6, 'ko': 7, 'zh': 8, 'ru': 9, 'pl': 10}  # (Polish: ours)
STREAM_VALUE, WIN_STREAM = 0x0D000000, 0x1000   # a pose's streamed line (0x8300): rm_Dst n, rm_Dwi 0x1000 | n
FONT = 0x46B70814                   # the glyph table the subtitles are drawn with
FILE = 'subtitles.json'             # a pack's line list, in its source/
EMPTY = b'\xff\xff\xff\xff'
CONTAINER_START = 0x90
BANK_HEADER = 0x70
BANK_WORDS = (0x30, 0x30, 0x50, 0x60, 0x70)     # a one-text bank's table offsets (others hold 2 or 3 texts)
FPS = 60
SHOW_AFTER, HIDE_AFTER = 1, 27      # frames after the voice's onset / end (the title's own lines: tools in notes)
LOUD = 0.05                         # a frame is voice when its peak is above this share of the clip's
LAST_UNIT = 0xD7FF                  # timing units stay below the surrogates and the control codes (U+FFF0 on)
SHOW, HIDE, START, PLAIN = '￻', '￼', '￵', '\x01'
END = '￻\x01￼￿'
# a character the font lacks -> plain ones (tried in turn)
PLAIN_FORMS = {'‘': "'", '’': "'", '‚': "'", '‛': "'", '′': "'", '´': "'",
               '“': '"', '”': '"', '„': '"', '‟': '"', '″': '"', '«': '"',
               '»': '"', '‹': "'", '›': "'", '…': '...', '—': '-', '–': '-', '‒': '-', '‐': '-',
               '‑': '-', '―': '-', '−': '-', ' ': ' ', ' ': ' ', ' ': ' ',
               '　': ' ', '〜': '~', '～': '~'}
# the code points the port draws as button icons in the title's fonts, this one too (runtime/src/title/text.h's
# carriers, presentation.cpp): never kept, made plain or left out
CARRIERS = frozenset('\u00a3\u00a5\u00a2\u00aa\uff3c\u00b3\u00bb')
TAG = re.compile(r'<[#/]?[A-Za-z_][^<>]*>')     # the source games' markup in a text (Tekken 7's <#...>)
# a guillemet's partner when it opens a quotation (« … » French and Russian, » … « German): _quoted
GUILLEMETS = {'«': '»', '»': '«'}
SPACES = re.compile(r'[ \t\r\n\f\v]+')


# ------------------------------------------------------------------------------------------------ the file
def read_table(data):
    """The subtitle file -> [entry bytes, or None for an empty one]."""
    count, = struct.unpack_from('>I', data, 0)
    out = []
    for i in range(count):
        offset, size = struct.unpack_from('>II', data, 4 + 8 * i)
        out.append(None if size <= len(EMPTY) else bytes(data[offset:offset + size]))
    return out


def _pad(out, align=16):
    out += bytes(-len(out) % align)


def write_table(entries):
    """[entry bytes or None] -> the subtitle file (the title's own layout: read_table(write_table(x)) == x)."""
    out = bytearray(struct.pack('>I', len(entries)) + bytes(8 * len(entries)))
    _pad(out)
    for i, entry in enumerate(entries):
        data = EMPTY if entry is None else entry
        struct.pack_into('>II', out, 4 + 8 * i, len(out), len(data))
        out += data
        _pad(out)
    return bytes(out)


def read_container(entry):
    """A language container -> its 16 banks (bytes; entries sharing a bank give the same bytes)."""
    count, = struct.unpack_from('>I', entry, 0)
    return [bytes(entry[o:o + z]) for o, z in (struct.unpack_from('>II', entry, 4 + 8 * i) for i in range(count))]


def container(banks):
    """{entry: bank bytes} (ENGLISH required) -> a language container whose other entries point at the English
    bank."""
    out = bytearray(struct.pack('>I', LANGUAGES) + bytes(8 * LANGUAGES))
    _pad(out)
    at = {}
    for i in sorted(banks, key=lambda i: (i != ENGLISH, i)):
        at[i] = (len(out), len(banks[i]))
        out += banks[i]
        _pad(out)
    for i in range(LANGUAGES):
        struct.pack_into('>II', out, 4 + 8 * i, *at.get(i, at[ENGLISH]))
    return bytes(out)


# ------------------------------------------------------------------------------------------------ text banks
def is_template(bank):
    """Whether a bank is a one-text bank whose header can be copied (template)."""
    return (len(bank) > BANK_HEADER + 8 and bank[:4] == b'NTXB' and
            struct.unpack_from('>5I', bank, 0x0C) == BANK_WORDS and
            struct.unpack_from('>I', bank, 0x30)[0] == 1)


def template(entries):
    """The header of the first one-text bank of the file's entries (read_table) -> 0x70 bytes; ValueError if none."""
    for entry in entries:
        if entry is None:
            continue
        for bank in read_container(entry):
            if is_template(bank):
                return bytes(bank[:BANK_HEADER])
    raise ValueError('the subtitle file has no text bank of one text')


def crc16(data):
    """CRC-16/CCITT-FALSE."""
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = (c << 1 ^ 0x1021) & 0xFFFF if c & 0x8000 else c << 1 & 0xFFFF
    return c


def bank(header, entry, text):
    """A text bank of one text for container entry `entry` (its language byte), from a template header."""
    raw = text.encode('utf-8')
    units = len(text.encode('utf-16-be')) // 2
    body = raw + bytes(2 + -(len(raw) + 2) % 4)          # (at least two zero bytes, to 4)
    record = bytearray(struct.pack('>IHH', 0, crc16(raw), units) + body)
    key = len(record)
    record += b'0\0\0\0' + bytes(4) + EMPTY
    struct.pack_into('>I', record, 0, len(record))
    out = bytearray(header) + record
    out += EMPTY
    out += b'\xff' * (-len(out) % 16)
    struct.pack_into('>B', out, 6, entry + 1)
    struct.pack_into('>I', out, 8, len(out))
    struct.pack_into('>II', out, 0x38, key, key + 4)
    return bytes(out)


def bank_text(data):
    """The text of a one-text bank (bank's inverse)."""
    return data[BANK_HEADER + 8:].split(b'\0')[0].decode('utf-8')


def markup(text, show, hide):
    """A line's text with its timing (frames from the line's start)."""
    show = min(max(1, int(show)), LAST_UNIT - 1)
    hide = min(max(show + 1, int(hide)), LAST_UNIT)
    return SHOW + chr(show) + HIDE + chr(hide) + START + PLAIN + text + END


def unmarked(text):
    """(text, show, hide) of a marked-up line (markup's inverse), or (text, None, None)."""
    if len(text) >= 6 + len(END) and text[0] == SHOW and text[2] == HIDE and text[4:6] == START + PLAIN and \
            text.endswith(END):
        return text[6:-len(END)], ord(text[1]), ord(text[3])
    return text, None, None


# ------------------------------------------------------------------------------------------------ the font
def font_glyphs(archives):
    """The code points of the subtitles' glyph table in the player's game (FONT), or None when it cannot be read."""
    try:
        data = archives.read(FONT)
    except (KeyError, OSError, ValueError, struct.error):
        return None
    return glyph_codes(data)


def glyph_codes(nfh):
    """The code points of a glyph table ("NFH": the glyph count at 8, in the table's byte order; 32-byte records
    from 0x450, each's code point big-endian at 22), or None if it is not one."""
    if len(nfh) < 0x450 or nfh[:3] != b'NFH':
        return None
    count, = struct.unpack_from('>I' if nfh[4] == 0 else '<I', nfh, 8)
    if 0x450 + 32 * count > len(nfh):
        return None
    return {nfh[0x450 + 32 * i + 22] << 8 | nfh[0x450 + 32 * i + 23] for i in range(count)}


def _quoted(text):
    """Guillemets as straight quotes: paired from the left, each opening mark closed by its partner (GUILLEMETS: « … »
    French and Russian, » … « German, either way in one text, one pair inside another), the spaces inside a pair
    dropped; a mark with no partner is a straight quote too, without the spaces after it when it starts the text or
    before it when it ends it (a quotation going on from the line before, or on in the next)."""
    if not any(ch in GUILLEMETS for ch in text):
        return text
    opened, pairs = [], []                  # [(index, the closing mark)] of the marks open; [(open, close)]
    for i, ch in enumerate(text):
        if ch not in GUILLEMETS:
            continue
        if opened and ch == opened[-1][1]:
            pairs.append((opened.pop()[0], i))
        else:
            opened.append((i, GUILLEMETS[ch]))
    dropped = set()

    def drop(i, step, end):                 # the spaces from i on (step 1) or back (step -1), up to end
        while i != end and text[i].isspace():
            dropped.add(i)
            i += step
    for a, b in pairs:
        drop(a + 1, 1, b)
        drop(b - 1, -1, a)
    for i, _ in opened:
        if not text[:i].strip():
            drop(i + 1, 1, len(text))
        elif not text[i + 1:].strip():
            drop(i - 1, -1, -1)
    return ''.join('"' if ch in GUILLEMETS else ch for i, ch in enumerate(text) if i not in dropped)


def fit(text, glyphs=None):
    """A source game's text as the subtitles can show it: one line (line breaks and runs of spaces one space), no
    markup, every character one the font has (glyphs; None: typographic ones made plain, the rest kept) and none
    the port draws as an icon (CARRIERS: guillemets become straight quotes, without the spaces inside a pair:
    _quoted), others made plain (PLAIN_FORMS, then without accents) or left out (an ideographic space stays where the
    font has it, as in the title's own Japanese lines; a no-break space, which it lacks, becomes a space)."""
    text = _quoted(SPACES.sub(' ', TAG.sub('', text)).strip(' '))
    out = []
    for ch in text:
        if ord(ch) > 0xFFFF or unicodedata.category(ch) in ('Cc', 'Cf', 'Co', 'Cs'):
            continue
        if glyphs is None and ch not in CARRIERS:
            out.append(PLAIN_FORMS.get(ch, ch))
            continue
        if glyphs is not None and ord(ch) in glyphs and ch not in CARRIERS:
            out.append(ch)
            continue
        for plain in (PLAIN_FORMS.get(ch), ''.join(c for c in unicodedata.normalize('NFKD', ch)
                                                    if not unicodedata.combining(c))):
            if plain and plain != ch and not CARRIERS.intersection(plain) and \
                    (glyphs is None or all(ord(c) in glyphs for c in plain)):
                out.append(plain)
                break
    return SPACES.sub(' ', ''.join(out)).strip(' ')


# ------------------------------------------------------------------------------------------------ the lines
def timing(clip):
    """(show, hide) frames of a clip (name, rate, int16 [channels, samples]) streamed from the line's start: the
    frame after its voice starts, HIDE_AFTER frames after it ends (a frame is voice above LOUD of the loudest)."""
    _, rate, a = clip
    a = np.abs(np.asarray(a, np.int32)).max(0) if np.ndim(a) == 2 else np.abs(np.asarray(a, np.int32))
    step = rate / float(FPS)
    frames = int(np.ceil(len(a) / step)) if len(a) else 0
    peaks = np.array([a[int(round(k * step)):int(round((k + 1) * step))].max(initial=0) for k in range(frames)])
    loud = np.nonzero(peaks > LOUD * peaks.max())[0] if frames and peaks.max() > 0 else []
    if not len(loud):
        return SHOW_AFTER, SHOW_AFTER + HIDE_AFTER
    return int(loud[0]) + SHOW_AFTER, int(loud[-1]) + HIDE_AFTER


def lines_of(streams, texts):
    """The fighter's lines: {line: {'show', 'hide', 'clip', 'text': {language: text}}}. streams: {'rm_Dst': {tone:
    clip}, 'rm_Dwi': {tone: clip}} (convert/voice.build: the clip each tone plays); texts: {clip name: {language:
    text}} (its source's; a clip without an English text has no line)."""
    low = {name.lower(): t for name, t in texts.items()}
    out = {}
    for which, first, room in (('rm_Dst', 0, WIN_LINE), ('rm_Dwi', WIN_LINE, LINES - WIN_LINE)):
        for tone, clip in sorted(streams.get(which, {}).items()):
            text = low.get(clip[0].lower()) or {}
            if tone >= room or not text.get('en'):
                continue
            show, hide = timing(clip)
            out[first + tone] = {'show': show, 'hide': hide, 'clip': clip[0],
                                 'text': {lang: t for lang, t in sorted(text.items()) if lang in ENTRY and t}}
    return out


def values(lines, select_id):
    """{a pose's streamed line (0x8300's value): its subtitle (0x8180's value)} of the fighter's lines."""
    return {STREAM_VALUE | (WIN_STREAM | line - WIN_LINE if line >= WIN_LINE else line): select_id << 8 | line
            for line in lines}


def dumps(lines):
    """The pack's copy of its lines (source/subtitles.json)."""
    return json.dumps({'lines': {str(line): v for line, v in sorted(lines.items())}}, ensure_ascii=False,
                      indent=1, sort_keys=True).encode('utf-8')


def read_lines(folder):
    """A pack's lines (dumps) from its source/ (`folder` the pack's), {} when it has none."""
    path = os.path.join(folder, 'source', FILE)
    if not os.path.isfile(path):
        return {}
    with open(path, 'rb') as f:
        got = json.loads(f.read().decode('utf-8'))
    return {int(line): v for line, v in got.get('lines', {}).items()
            if line.isdigit() and int(line) < LINES and (v.get('text') or {}).get('en')}


def table(original, fighters, glyphs=None):
    """The subtitle file with the added fighters' lines: original (the title's file) with its count raised to
    cover the highest id, the ids between empty; fighters {select id: lines (lines_of)}; glyphs: the font's
    (font_glyphs)."""
    entries = read_table(original)
    header = template(entries)
    need = (max(fighters) + 1) * LINES if fighters else 0
    entries += [None] * (need - len(entries))
    for select_id, lines in sorted(fighters.items()):
        for line, v in sorted(lines.items()):
            banks = {}
            for lang, text in sorted(v['text'].items()):
                text = fit(text, glyphs)
                if lang in ENTRY and text:
                    banks[ENTRY[lang]] = bank(header, ENTRY[lang], markup(text, v['show'], v['hide']))
            entries[select_id * LINES + line] = container(banks) if ENGLISH in banks else None
    return write_table(entries)
