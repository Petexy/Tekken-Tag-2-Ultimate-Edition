"""Tekken 7 fighters' battle subtitles: the texts of their intro and win lines.

Only the game's own data file has them (Binary/subtitles/<code>/<language>/<code>_sub.bin inside Binary/tkdata.bin,
one file per fighter and language); autodump.py has the running game read them with its own reader of that file and
saves them below its FILES folder under that path (an empty file: the game has none for the fighter).
This module reads the saved files.

A file is a run of records, little-endian, each:
    u32 size (of the record, a multiple of 4) | u32 start | u32 end (the frames, from the pose's start, it is shown
    between) | char[4] language | char[20] the voice line's name | char[20] key | UTF-8 text from 0x38, NUL, zero pad.
The key is what the game looks the subtitle up by when a pose plays: the pose's move name, not its animation's (a
win pose <prefix>_w02 may play an animation <prefix>_w02_n: its key is <prefix>_w02), which is the name of its voice
line in the fighter's sound bank too (<VOICE_PREFIX>_s00.. intro lines, _w00.. win lines: convert/voice.py's
clips). A key may have several records, parts shown one after another; a text may hold line breaks ('\\n'), and no
other markup. (The language field is not to be trusted: some fighters' files in other languages say 'us' there.)
"""
import collections
import os
import struct

# the game's text languages, as its subtitle folders name them ('us': English, the one it falls back to)
LANGUAGES = ('jp', 'us', 'br', 'ns', 'fr', 'it', 'de', 'es', 'ru', 'ar', 'tw', 'kr')
RECORD = struct.Struct('<3I4s20s20s')           # size, start, end, language, voice line, key
TEXT = 0x38                                     # (= RECORD.size)

Part = collections.namedtuple('Part', 'key voice start end text')


def saved_path(code, language='us', folder=None):
    """Where a fighter's (Tekken 7 code) subtitle file is saved: below `folder` (None: autodump.FILES) under the
    game's own path of it."""
    if folder is None:
        from .autodump import FILES as folder
    c = code.lower()
    return os.path.join(folder, 'Binary', 'subtitles', c, language, '%s_sub.bin' % c)


def saved(code, language='us', folder=None):
    """Whether the fighter's subtitle file was saved (an empty one too: the game has none)."""
    return os.path.isfile(saved_path(code, language, folder))


def all_saved(code, folder=None):
    """Whether the fighter's subtitle files are saved in every language the import has the game read
    (autodump.SUBTITLE_LANGUAGES). Its pack shows them only then; else the pack is made without them and says so
    (character.ini without_subtitles), and launcher.py status offers to update it."""
    from .autodump import SUBTITLE_LANGUAGES
    return all(saved(code, language, folder) for language in SUBTITLE_LANGUAGES)


def _name(b):
    return b.split(b'\0', 1)[0].decode('latin1')


def parse(data):
    """A subtitle file's records: [Part(key, voice, start, end, text)] in its order. ValueError when it is not one."""
    out = []
    at = 0
    while at < len(data):
        if len(data) - at < TEXT:
            raise ValueError('a subtitle record cut short at %d' % at)
        size, start, end, _, voice, key = RECORD.unpack_from(data, at)
        if size < TEXT or size % 4 or at + size > len(data):
            raise ValueError('a subtitle record of %d bytes at %d (the file has %d)' % (size, at, len(data)))
        text = data[at + TEXT:at + size].split(b'\0', 1)[0].decode('utf-8')
        out.append(Part(_name(key), _name(voice), start, end, text))
        at += size
    return out


def read(code, language='us', folder=None):
    """The fighter's saved subtitle records (parse); [] when none are saved or the game has none. ValueError (naming
    the file) when the saved file is not one."""
    path = saved_path(code, language, folder)
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        return []
    try:
        return parse(data)
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError('%s: %s' % (path, e)) from None


def parts(code, language='us', folder=None):
    """{key: [(start, end, text)] of its parts, in order} of the fighter's saved subtitles ({} when none)."""
    out = {}
    for p in read(code, language, folder):
        out.setdefault(p.key, []).append((p.start, p.end, p.text))
    return out


def one_line(texts):
    """Parts' texts as one line: line breaks and runs of spaces become one space (for the languages written with
    spaces: English)."""
    return ' '.join(' '.join(texts).split())


def lines(code, language='us', folder=None):
    """{key (a pose's move name = its voice line's event name: <prefix>_s00, <prefix>_w02): its text, its parts
    joined on one line} of the fighter's saved subtitles; {} when none are saved or the game has none."""
    return {key: one_line(t for _, _, t in ps) for key, ps in parts(code, language, folder).items()}
