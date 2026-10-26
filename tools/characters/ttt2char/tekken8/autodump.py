"""Tekken 8 movesets saved in the background: a fighter's moveset files as the game reads them, without the player doing
anything.

Tekken 8 keeps its movesets in an encrypted archive (Polaris/Content/Binary/pak/tkdata.bin) that this importer never
opens: the running game's own reader reads a fighter's files. The game runs where nobody sees or hears it, with nothing
pressed, as Tekken 7 does for tekken7/autodump.py (whose Steam, process, sound and helper machinery this module uses):
* Proton runs it inside gamescope's headless backend (no window, no output) with its sound sent to a silent sink of
  its own;
* t8helper.exe (tools/characters/t8helper, built with MinGW, or the launcher's prebuilt one that $TTT2_T8HELPER names)
  runs next to it in its Wine prefix: it asks Steam, as the game does, which DLC the player owns (only owned fighters
  are saved; the base roster always is), and once the game sits on its start-up screens it has the game's archive
  reader read each file (one request at a time, only while the reader is idle) and turns the six protected fields of
  every move into plain values with the game's own callback and getter; the helper knows those four functions and
  checks their first bytes before calling any (another build of the game is refused, not crashed), and takes no
  address from outside. The exe's file holds the same bytes: a build the helper would refuse (a game update it does
  not know yet) is told from the file before anything is started (known_build), and the game is not started then.
No menu, key or screen is involved, and Tekken 7 is not needed. Nothing is written into the game's files, its saves or
its prefix (but the helper's copy at C:\\t8helper.exe). A session ends what it started and nothing else (Session.close;
also on the SIGTERM of the launcher's Cancel, see signals.py): a Tekken 8 the player starts from Steam meanwhile goes
on, and what a killed importer left running is ended by the next session. Steam from Flatpak or Snap is found, but
Tekken 8 is not run through it (not supported yet).

What is saved, in MOVESETS (or another folder), per fighter (by its Tekken 8 code: zbr = Reina):
    <code>.motbin             the moveset (Binary/mothead/bin/<code>.motbin in the archive), in its file form:
                              "TEK\\0" at 8, byte 2 zero (the game sets it once offsets are pointers), roster id x
                              0xFFFF + 1 at 0x160, the moves (0x448 bytes each) at 0x318 + the u64 at 0x230, their
                              count at 0x238; plain but for six 32-byte fields of every move
    <code>.motbin.fields.bin  those six fields' plain values: u32 moves, u32 move size (0x448), u32 the moves' offset
                              (the u64 at 0x230), then per move 6 u32: the fields at +0x00 +0x20 +0x58 +0x78 +0xd0
                              +0xf0 (+0xd0 is the roster id x 0xFFFF + 1 again in every move)
    <code>.anmbin             the fighter's animation bank (Binary/mothead/bin/<code>.anmbin): six u32 entry counts at
                              4, six u64 entry list offsets at 0x38 (entries of 0x38 bytes)
    <code>.mvl                the command list (Binary/mothead/movelist/<code>.mvl): "MVLT" at 0
and once for all fighters:
    com.anmbin                the shared animation bank (552 MB; an entry's 256-bit mask at +0x18 names the fighters
                              that use it by roster id), in the anmbin layout
    manifest.json             {"game": {"build", "exe_size", "exe_mtime"}, "fighters": {code: {"id", "name",
                              "motbin_only", "files": {name: size}}}, "common": {name: size}, "before": {"fighters",
                              "common"}}: what was saved from which version of the game (its Steam build and its
                              exe); an update makes all of it stale, and the next dump reads it again. "before"
                              keeps what is still there of what earlier versions saved (saved_files falls back on
                              it until this version's is saved: an update, or a dump that fails, leaves a fighter
                              the moveset saved before; a whole one needs the shared bank it was saved with, which
                              a dump saving another fighter whole for this version replaces)
A fighter's files are put in place only once the game has handed all of them over and they are checked: a dump that
fails leaves the ones saved before as they were. A reference (dump's `references`, dump_tekken8.py --motbin-only) is
saved with its motbin and fields alone: what the id maps take from other fighters ("motbin_only" in the manifest;
saving it whole later replaces that); a fighter saved whole, for this version or before, is saved whole again, never
replaced by its motbin alone.

Written for this project from the files themselves (no third-party code).
"""
import atexit
import collections
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import time

from .. import signals
from ..tekken7 import autodump as t7
from ..tekken7.autodump import (DumpError, steams, steam_running, _text, _libraries, _processes, _ancestors, _cmdline,
                                _same_folder, _new_tag, _owner_alive, _kill, _wait_gone, _wineserver_kill, _pactl,
                                _free_port, _until)

APP_ID = 1778820
STEAM_FOLDER = 'TEKKEN 8'                        # its folder below steamapps/common when the manifest names none
LAUNCHER = 'TEKKEN 8.exe'                        # what Steam starts (it starts the game)
EXE = 'Polaris/Binaries/Win64/Polaris-Win64-Shipping.exe'
GAME_COMM = 'Polaris-Win64-S'                    # the game's Linux process name (the exe's name, 15 characters)
GAME_THREAD = 'GameThread'                       # ... once its main thread has its name (within a second)
STEAMWORKS = 'Polaris/Binaries/Win64/steam_api64.dll'
SINK = 'ttt2_tekken8_silent'
SINK_NAME = 'Tekken 8 (silent, for Tekken Tag Tournament 2)'      # (in the sound settings meanwhile)
SESSION_TAG = 'TTT2_T8_SESSION'     # in the environment of all a session starts (Proton and Wine pass it on)
RUNNING = 'Tekken 8 is running: close it first'
BUSY = 'Tekken 8 is busy with another import (or check of your DLC)'

# Tekken 8's fighters: roster id -> (code, name). The id is the game's (its loader's id -> code switch; a motbin names
# it at 0x160); the code names the fighter's files. 32 (Azazel, a boss: no command list of his own) and the story
# mode's fighters (0x74 on) are left out.
ROSTER = {
    0: ('grf', 'Paul'), 1: ('pig', 'Law'), 2: ('pgn', 'King'), 3: ('cml', 'Yoshimitsu'), 4: ('snk', 'Hwoarang'),
    5: ('rat', 'Xiaoyu'), 6: ('ant', 'Jin'), 7: ('cht', 'Bryan'), 8: ('grl', 'Kazuya'), 9: ('bsn', 'Steve'),
    10: ('ccn', 'Jack-8'), 11: ('der', 'Asuka'), 12: ('swl', 'Devil Jin'), 13: ('klw', 'Feng'), 14: ('hms', 'Lili'),
    15: ('kmd', 'Dragunov'), 16: ('ghp', 'Leo'), 17: ('lzd', 'Lars'), 18: ('mnt', 'Alisa'), 19: ('ctr', 'Claudio'),
    20: ('hrs', 'Shaheen'), 21: ('kal', 'Nina'), 22: ('wlf', 'Lee'), 23: ('rbt', 'Kuma'), 24: ('ttr', 'Panda'),
    25: ('crw', 'Zafina'), 26: ('jly', 'Leroy'), 27: ('aml', 'Jun'), 28: ('zbr', 'Reina'), 29: ('cat', 'Azucena'),
    30: ('lon', 'Victor'), 31: ('bbn', 'Raven'),
    33: ('dog', 'Eddy'), 34: ('cbr', 'Lidia'), 35: ('bee', 'Heihachi'), 36: ('okm', 'Clive'), 37: ('kgr', 'Anna'),
    38: ('tgr', 'Fahkumram'), 39: ('knk', 'Armor King'), 40: ('wkz', 'Miary Zo'), 41: ('ker', 'Kunimitsu'),
    42: ('usi', 'Bob'),
}
# Tekken 8's DLC fighters: their roster ids and the Steam app ids of the DLC that has them (Steam's public lists)
DLC = {33: 2732280, 34: 2891170, 35: 3024980, 36: 3145880, 37: 3417000, 38: 3564540, 39: 3775990, 40: 4001560,
       41: 4129100, 42: 4536140}
COMMON = 'com'                                   # the shared animation bank's code (the loader's id 0xff)
FIGHTER_FILES = (('Binary/mothead/bin/%s.motbin', '%s.motbin'), ('Binary/mothead/bin/%s.anmbin', '%s.anmbin'),
                 ('Binary/mothead/movelist/%s.mvl', '%s.mvl'))
FIELDS_SUFFIX = '.fields.bin'
NEW_SUFFIX = '.new'                              # a file being saved, until all of a fighter's are there and checked
MANIFEST = 'manifest.json'

# the files' layouts (above) as far as the checks of what the game handed over go
MOTBIN_MAGIC = b'TEK\0'
MOTBIN_BASE = 0x318                              # the header's size: table offsets count from here
MOTBIN_ROSTER = 0x160                            # u32 roster id x ROSTER_STEP + 1
MOTBIN_MOVES = 0x230                             # u64 offset of the moves (from MOTBIN_BASE), u64 their count at +8
MOVE_SIZE = 0x448
ROSTER_STEP = 0xFFFF                             # move ids are roster id x 0xFFFF + 1 + the move's index
FIELD_OFFSETS = (0x00, 0x20, 0x58, 0x78, 0xd0, 0xf0)
FIELD_ROSTER = 4                                 # +0xd0: the motbin's roster value, in every move
ANMBIN_CATEGORIES = 6
ANMBIN_ENTRY = 0x38
ANMBIN_HEAD = 0x68                               # the counts (4) and the list offsets (0x38) end here
MVL_MAGIC = b'MVLT'

# the build of the game the helper knows: the four functions it calls (t8helper.c's ALLOCATE, REQUEST_FILE,
# PROTECT_FIELDS, READ_FIELD) as its `attach` checks them, (address at the exe's preferred base, bytes, their 64-bit
# FNV-1a hash); known_build reads them from the exe's file
PREFERRED_BASE = 0x140000000
HELPER_FUNCTIONS = ((0x142cd0070, 16, 0x9A0F7237C356D9F4), (0x1459f9c50, 16, 0xAD224657991D6490),
                    (0x1418acfb0, 16, 0xEF46830222BE4AC8), (0x141809d00, 16, 0x4C7611802A9CD63B))
REFUSED = 'this Tekken 8 build is not the one the helper knows'       # (its attach's answer for another build)
UNKNOWN_BUILD = ('this Tekken 8 build (Steam build %s, a game update) is not the one the helper knows: Tekken 8 is not '
                 'started (a later version of Tekken Tag 2 Ultimate Edition will know it)')

# the movesets saved, and the helper's build and its run's logs ($XDG_CACHE_HOME/ttt2 as the game's and the
# launcher's caches)
MOVESETS = os.path.join(os.path.expanduser('~/.local/share'), 'ttt2', 'tekken8', 'movesets')
CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'ttt2', 'tekken8')
HELPER_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 't8helper', 't8helper.c')
SOCKET_TIMEOUT = 300            # s: the helper waits up to 30 s for the reader to be idle and 120 s for a request
CHUNK = 4 << 20                 # bytes of a file copied from the helper to its file at once
START_TIMEOUT = 420             # s until the game runs (52 s on an SSD; the first start in a prefix takes longer)
ATTACH_TIMEOUT = 120            # s until its code is mapped
READY_TIMEOUT = 300             # s until it has opened its moveset archive (19 s after attaching)


# ---------------------------------------------------------------- the roster

def _word(text):
    return re.sub(r'[\s_\-.]+', '', text.lower())


def fighter_id(word):
    """The roster id a word names: an id ('28'), a code ('zbr') or a name in any case, with or without its spaces,
    '_' or '-' ('Reina', 'armor_king', 'jack8'); None when it names none."""
    word = word.strip()
    if word.isdigit():
        return int(word) if int(word) in ROSTER else None
    w = _word(word)
    for fid, (code, name) in ROSTER.items():
        if w in (code, _word(name)):
            return fid
    return None


def archive_paths(code, motbin_only=False):
    """[(path in the moveset archive, name of the file saved)] of a fighter's files (its code: ROSTER)."""
    files = FIGHTER_FILES[:1] if motbin_only else FIGHTER_FILES
    return [(path % code, name % code) for path, name in files]


def common_paths():
    """[(path in the moveset archive, name of the file saved)] of the shared animation bank."""
    return [(FIGHTER_FILES[1][0] % COMMON, FIGHTER_FILES[1][1] % COMMON)]


# ---------------------------------------------------------------- finding the game

class Tekken8:
    def __init__(self, steam, library, game, prefix, proton):
        self.steam, self.library, self.game, self.prefix, self.proton = steam, library, game, prefix, proton


def _tekken8_library():
    """(Steam's folder, its sandbox (None, 'flatpak', 'snap'), the library Tekken 8 is installed in, its folder)."""
    found = steams()
    if not found:
        raise DumpError('Steam is not installed (no ~/.local/share/Steam, nor Steam from Flatpak or Snap)')
    for steam, sandbox in found:
        for lib in _libraries(steam, sandbox):
            acf = os.path.join(lib, 'steamapps', 'appmanifest_%d.acf' % APP_ID)
            if not os.path.isfile(acf):
                continue
            m = re.search(r'"installdir"\s+"([^"]+)"', _text(acf))
            return steam, sandbox, lib, os.path.join(lib, 'steamapps', 'common', m.group(1) if m else STEAM_FOLDER)
    raise DumpError('Tekken 8 is not installed in any Steam library')


def tekken8_library():
    """(Steam's folder, the Steam library Tekken 8 is installed in, its installation folder), through Steam's files:
    what checking the saved files needs (find_tekken8: running it)."""
    steam, _, lib, game = _tekken8_library()
    return steam, lib, game


def find_tekken8():
    """Tekken 8's install, its Proton prefix and the Proton it uses, through Steam's files."""
    steam, sandbox, lib, game = _tekken8_library()
    if sandbox:
        raise DumpError('Tekken 8 is installed through Steam from %s, which is not supported yet: running Tekken 8 '
                        'hidden needs Steam from your distribution\'s packages' % t7.SANDBOX_NAMES[sandbox])
    prefix = os.path.join(lib, 'steamapps', 'compatdata', str(APP_ID))
    info = os.path.join(prefix, 'config_info')
    if not os.path.isdir(os.path.join(prefix, 'pfx')) or not os.path.isfile(info):
        raise DumpError('Tekken 8 has not run with Proton yet: start it once from Steam, then try again')
    proton = next((l.split('/files/')[0] for l in _text(info).splitlines() if '/files/' in l), None)
    if not proton or not os.path.isfile(os.path.join(proton, 'proton')):
        raise DumpError('the Proton Tekken 8 last ran with is gone; start the game once from Steam')
    return Tekken8(steam, lib, game, prefix, proton)


def game_version(game, library=None):
    """{'build': Steam's build id of the installation (from the library's app manifest; None without one),
    'exe_size', 'exe_mtime'}: what the saved files are checked against (an update changes them)."""
    build = None
    acf = os.path.join(library, 'steamapps', 'appmanifest_%d.acf' % APP_ID) if library else None
    if acf and os.path.isfile(acf):
        m = re.search(r'"buildid"\s+"(\d+)"', _text(acf))
        build = m.group(1) if m else None
    try:
        st = os.stat(os.path.join(game, EXE))
    except OSError:
        raise DumpError('Tekken 8\'s program is missing (%s): verify the integrity of its files in Steam' % EXE)
    return {'build': build, 'exe_size': st.st_size, 'exe_mtime': int(st.st_mtime)}


def _fnv1a(data):
    h = 0xcbf29ce484222325
    for b in data:
        h = ((h ^ b) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h


def known_build(game):
    """Whether the Tekken 8 in `game` is the build the helper knows: HELPER_FUNCTIONS' bytes, read from the exe's file
    (its sections as the PE header lays them out) as the helper's attach checks them in the running game. False when
    they differ (a game update), or the exe cannot be read. Nothing is started; a few bytes are read."""
    try:
        with open(os.path.join(game, EXE), 'rb') as f:
            head = f.read(0x1000)
            if head[:2] != b'MZ':
                return False
            pe, = struct.unpack_from('<I', head, 0x3C)
            count, = struct.unpack_from('<H', head, pe + 6)
            optional, = struct.unpack_from('<H', head, pe + 20)
            # (virtual size, address, size in the file, offset in the file) of each section
            sections = [struct.unpack_from('<IIII', head, pe + 24 + optional + 40 * i + 8) for i in range(count)]
            for address, length, hash64 in HELPER_FUNCTIONS:
                rva = address - PREFERRED_BASE
                raw = next((raw + rva - va for vsize, va, size, raw in sections
                            if va <= rva and rva + length <= va + min(vsize, size)), None)
                if raw is None:
                    return False
                f.seek(raw)
                if _fnv1a(f.read(length)) != hash64:
                    return False
    except (OSError, struct.error):
        return False
    return True


def ready_helper(cache):
    """A t8helper.exe that needs no building: the prebuilt one $TTT2_T8HELPER names (the launcher's kit has one), or
    the one built into `cache` when it is newer than its source; else None."""
    prebuilt = os.environ.get('TTT2_T8HELPER')
    if prebuilt and os.path.isfile(prebuilt):
        return prebuilt
    exe = os.path.join(cache, 't8helper.exe')
    src = os.path.normpath(HELPER_SOURCE)
    if os.path.isfile(exe) and os.path.isfile(src) and os.path.getmtime(exe) >= os.path.getmtime(src):
        return exe
    return None


def build_helper(cache):
    """t8helper.exe: a ready one (ready_helper), else built with MinGW into `cache`."""
    ready = ready_helper(cache)
    if ready:
        return ready
    exe = os.path.join(cache, 't8helper.exe')
    gcc = shutil.which('x86_64-w64-mingw32-gcc')
    if gcc is None:
        raise DumpError('building the helper needs MinGW (x86_64-w64-mingw32-gcc; Arch: mingw-w64-gcc, '
                        'Debian/Ubuntu: gcc-mingw-w64-x86-64)')
    os.makedirs(cache, exist_ok=True)
    subprocess.run([gcc, '-O2', '-mwindows', '-o', exe, os.path.normpath(HELPER_SOURCE), '-lws2_32'], check=True)
    return exe


# ---------------------------------------------------------------- what is saved

def _load(folder):
    """The folder's manifest as it was written (None without one), its 'fighters', 'common' and 'before' there."""
    try:
        with open(os.path.join(folder, MANIFEST), encoding='utf-8') as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    before = manifest.get('before') if isinstance(manifest.get('before'), dict) else {}
    for part in (manifest, before):
        for key in ('fighters', 'common'):
            if not isinstance(part.get(key), dict):
                part[key] = {}
    manifest['before'] = {'fighters': before['fighters'], 'common': before['common']}
    return manifest


def read_manifest(folder, version):
    """The folder's manifest for this version of the game. What was saved from another version (or nothing) gives an
    empty one, which keeps under 'before' what is still there of it and of what it kept (the newer of a fighter's,
    each fighter's files all there, the shared bank when it is), for saved_files to fall back on."""
    stored = _load(folder)
    if stored is not None and stored.get('game') == version:
        return stored
    manifest = {'game': version, 'fighters': {}, 'common': {}, 'before': {'fighters': {}, 'common': {}}}
    for kept in (stored['before'], stored) if stored is not None else ():
        manifest['before']['fighters'].update((code, entry) for code, entry in kept['fighters'].items()
                                              if isinstance(entry, dict) and _all_there(folder, entry.get('files')))
        if common_saved(folder, kept):
            manifest['before']['common'] = kept['common']
    return manifest


def write_manifest(folder, manifest):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, MANIFEST)
    with open(path + '.part', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    os.replace(path + '.part', path)


def _all_there(folder, files):
    return isinstance(files, dict) and bool(files) and all(os.path.isfile(os.path.join(folder, name)) and
                               os.path.getsize(os.path.join(folder, name)) == size for name, size in files.items())


def is_saved(folder, manifest, code, motbin_only=False):
    """Whether the manifest (read_manifest) has the fighter's files, all of them there with their sizes (a motbin
    alone does for motbin_only)."""
    entry = manifest['fighters'].get(code)
    return bool(entry) and (motbin_only or not entry.get('motbin_only')) and _all_there(folder, entry.get('files'))


def common_saved(folder, manifest):
    return _all_there(folder, manifest['common'])


def saved_files(code, folder=None, version=None):
    """{'motbin', 'fields', 'anmbin', 'mvl', 'common'} paths of a fighter's saved files (only 'motbin' and 'fields' when
    it was saved with motbin_only), or None when they are not all saved: for `version` (game_version) when given,
    else for the version the manifest is of, or before it (read_manifest's 'before': a moveset an earlier version of
    the game saved, with the shared bank it was saved with)."""
    folder = folder or MOVESETS
    manifest = _load(folder)
    if manifest is None or (version is not None and manifest.get('game') != version):
        return None
    for saved in (manifest,) if version is not None else (manifest, manifest['before']):
        if not is_saved(folder, saved, code, motbin_only=True):
            continue
        out = {'motbin': os.path.join(folder, '%s.motbin' % code),
               'fields': os.path.join(folder, '%s.motbin%s' % (code, FIELDS_SUFFIX))}
        if not saved['fighters'][code].get('motbin_only'):
            if not common_saved(folder, saved):
                continue
            out.update(anmbin=os.path.join(folder, '%s.anmbin' % code), mvl=os.path.join(folder, '%s.mvl' % code),
                       common=os.path.join(folder, common_paths()[0][1]))
        return out
    return None


def whole(files):
    """Whether saved_files' answer is a fighter saved whole (its own animations, its command list and the shared
    bank): what converting its moveset needs (a reference's motbin alone does not do)."""
    return files is not None and 'anmbin' in files


def saved_codes(folder=None):
    """The codes of the fighters whose files the folder's manifest has, for its version or before it (saved_files
    tells which are all there), in code order: the fighter imported and the references saved with it."""
    manifest = _load(folder or MOVESETS)
    return sorted(set(manifest['fighters']) | set(manifest['before']['fighters'])) if manifest is not None else []


# ---------------------------------------------------------------- checks of what the game handed over

def check_motbin(head):
    """The roster value of a motbin (its first MOTBIN_BASE bytes at least): roster id x ROSTER_STEP + 1. DumpError when
    it is no motbin in its file form."""
    if len(head) < MOTBIN_BASE or head[8:12] != MOTBIN_MAGIC or head[2]:
        raise DumpError('the game handed over something that is not a moveset in its file form')
    return struct.unpack_from('<I', head, MOTBIN_ROSTER)[0]


def motbin_roster_id(value):
    """The roster id a motbin's roster value names (or None when it is none)."""
    return (value - 1) // ROSTER_STEP if value and (value - 1) % ROSTER_STEP == 0 else None


def check_fields(motbin, moves, stride, moves_offset, table):
    """Checks the helper's field table (moves x 6 u32) against its motbin (bytes, its header at least): the same moves
    table, and the moves' roster field (+0xd0) mostly the motbin's roster value: else the game's getter gave no plain
    values. DumpError when it fails."""
    offset, count = struct.unpack_from('<QQ', motbin, MOTBIN_MOVES)
    if (moves, stride, moves_offset) != (count, MOVE_SIZE, offset) or len(table) != moves * len(FIELD_OFFSETS) * 4:
        raise DumpError('the protected fields the game gave are not the moveset\'s (%d moves of %#x bytes at %#x; '
                        'the moveset has %d at %#x)' % (moves, stride, moves_offset, count, offset))
    if not moves:
        return
    roster = struct.unpack_from('<%dI' % (moves * len(FIELD_OFFSETS)), table)[FIELD_ROSTER::len(FIELD_OFFSETS)]
    value, n = collections.Counter(roster).most_common(1)[0]
    if value != check_motbin(motbin) or 2 * n < moves:
        raise DumpError('the game did not give the protected fields\' plain values')


def check_anmbin(head, size):
    """DumpError unless `head` (the first ANMBIN_HEAD bytes at least) starts an animation bank of `size` bytes."""
    if len(head) < ANMBIN_HEAD:
        raise DumpError('the game handed over something that is not an animation bank')
    counts = struct.unpack_from('<%dI' % ANMBIN_CATEGORIES, head, 4)
    lists = struct.unpack_from('<%dQ' % ANMBIN_CATEGORIES, head, 0x38)
    if not any(counts) or any(n and (o < ANMBIN_HEAD or o + n * ANMBIN_ENTRY > size) for n, o in zip(counts, lists)):
        raise DumpError('the game handed over something that is not an animation bank')


def check_mvl(head):
    if head[:4] != MVL_MAGIC:
        raise DumpError('the game handed over something that is not a command list')


def _head(path, n):
    with open(path, 'rb') as f:
        return f.read(n)


# ---------------------------------------------------------------- the helper

class Helper(t7.Helper):
    """A connection to t8helper.exe (serve <port> <secret>): the Tekken 7 helper's protocol (dlc, attach, ready, quit),
    the moveset archive's files written to their files as they come (save), the protected fields (protected)."""

    def __init__(self, port, secret, timeout=90):
        t7.Helper.__init__(self, port, secret, timeout)
        self.s.settimeout(SOCKET_TIMEOUT)

    def _copy(self, n, f):
        """Writes the next n bytes of the connection to f."""
        take = self.buf[:n]
        self.buf = self.buf[len(take):]
        f.write(take)
        n -= len(take)
        chunk = memoryview(bytearray(min(n, CHUNK)))
        while n:
            got = self.s.recv_into(chunk, min(n, CHUNK))
            if not got:
                raise DumpError('the helper stopped')
            f.write(chunk[:got])
            n -= got

    def save(self, paths, targets):
        """Has the game read the files (paths in the moveset archive) and writes each to its target (put in place once
        whole): [size, or None where the game did not read one], in order."""
        for p in paths:
            self._answer('want ' + p)
        self.send('fetch')
        out = []
        while True:
            line = self._line()
            if line == 'end':
                return out
            if line.startswith('error'):
                raise DumpError(line[6:])
            _, ok, n = line.split()
            if len(out) == len(targets):
                raise DumpError('the helper answered more files than asked for')
            target = targets[len(out)]
            if ok != '1':
                out.append(None)
                continue
            try:
                with open(target + '.part', 'wb') as f:
                    self._copy(int(n), f)
                os.replace(target + '.part', target)
            except BaseException:
                if os.path.exists(target + '.part'):
                    os.remove(target + '.part')
                raise
            out.append(int(n))

    def protected(self, path):
        """(moves, move size, the moves' offset, the table: moves x 6 u32 as bytes) of a motbin read before (save):
        its six protected fields' plain values."""
        self.send('protected ' + path)
        line = self._line()
        if line.startswith('error'):
            raise DumpError(line[6:])
        _, moves, stride, offset = line.split()
        return int(moves), int(stride), int(offset), self._exact(int(moves) * len(FIELD_OFFSETS) * 4)


# ---------------------------------------------------------------- the hidden session

INSIDE = r'''#!/bin/sh
# Run by gamescope (headless); the session lasts as long as this script.
if [ "$WITH_GAME" = 1 ]; then
  ( cd "$T8DIR" && PULSE_SINK="$SINK" "$PROTON" run "$T8DIR/%(launcher)s" > "$RUN/game.log" 2>&1 ) &
  i=0
  while [ $i -lt %(polls)d ]; do
    for f in /proc/[0-9]*/comm; do
      # (the game names its main thread within a second of its start, which renames the process: either name)
      read -r c 2>/dev/null < "$f" || continue
      [ "$c" = "%(comm)s" ] || [ "$c" = "%(thread)s" ] || continue
      p=${f#/proc/}; p=${p%%/comm}
      # (this session's game, not one the player started)
      tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qxF "%(tag)s=$%(tag)s" &&
        echo $p > "$RUN/game.pid"
    done
    [ -s "$RUN/game.pid" ] && break
    i=$((i + 1)); sleep 0.5
  done
  [ -s "$RUN/game.pid" ] || exit 1
  # (without the game's app id: Steam would count the helper as the game)
  env -u SteamAppId -u SteamGameId -u STEAM_COMPAT_APP_ID "$PROTON" run 'C:\t8helper.exe' serve "$PORT" "$SECRET" \
    > "$RUN/helper.log" 2>&1 &
  while kill -0 "$(cat "$RUN/game.pid")" 2>/dev/null; do sleep 1; done
  exit 0
fi
exec "$PROTON" run 'C:\t8helper.exe' serve "$PORT" "$SECRET" > "$RUN/helper.log" 2>&1
''' % {'launcher': LAUNCHER, 'comm': GAME_COMM, 'thread': GAME_THREAD, 'tag': SESSION_TAG, 'polls': 2 * START_TIMEOUT}


def _lock_path(prefix):
    """The prefix's lock file (as tekken7/autodump.py's): the same for every importer run, whatever its cache."""
    folder = os.environ.get('XDG_RUNTIME_DIR')
    if not folder or not os.path.isdir(folder):
        import tempfile
        folder = tempfile.gettempdir()
    name = hashlib.sha1(os.path.realpath(prefix).encode('utf-8', 'surrogateescape')).hexdigest()[:16]
    return os.path.join(folder, 'ttt2-tekken8-%d-%s.lock' % (os.getuid(), name))


def _lock(path, timeout=300):
    """The prefix's lock, waited for (tekken7/autodump.py's _lock): one session at a time."""
    try:
        return t7._lock(path, timeout)
    except DumpError:
        raise DumpError('%s for %d s: try again when it is done' % (BUSY, timeout))


# Whose processes are whose (as for Tekken 7): what a session starts has SESSION_TAG in its environment; the player's
# own Tekken 8 is started by Steam (its launch of the app id, Proton's processes in the prefix, the game).

def _players(prefix, processes):
    """The pids of the processes that are the player's Tekken 8 (or anything else using its prefix): no session's,
    not this program or what started it."""
    mine = _ancestors(os.getpid())
    app = str(APP_ID)
    out = []
    for pid, (comm, env) in processes.items():
        if pid in mine or SESSION_TAG in env:
            continue
        if comm == GAME_COMM or app in (env.get('SteamAppId'), env.get('SteamGameId'), env.get('STEAM_COMPAT_APP_ID')) \
                or _same_folder(env.get('STEAM_COMPAT_DATA_PATH'), prefix) \
                or _same_folder(env.get('WINEPREFIX'), os.path.join(prefix, 'pfx')) \
                or (comm == 'reaper' and 'AppId=%s' % app in _cmdline(pid)):
            out.append(pid)
    return out


def tekken8_running(t8):
    """Whether the player's own Tekken 8 runs (or is being started): a session would share its prefix."""
    return bool(_players(t8.prefix, _processes()))


def _tagged(prefix, processes):
    """{tag: [pids]} of the processes of the sessions in the prefix."""
    out = {}
    for pid, (_, env) in processes.items():
        if SESSION_TAG in env and _same_folder(env.get('STEAM_COMPAT_DATA_PATH'), prefix):
            out.setdefault(env[SESSION_TAG], []).append(pid)
    return out


def _end(t8, tags, gamescope=None):
    """Ends the processes of the sessions `tags` (as tekken7/autodump.py's _end): the prefix's Wine when nothing else
    uses it, gamescope, then whatever of theirs is left."""
    processes = _processes()
    if not _players(t8.prefix, processes) and all(t in tags or not _owner_alive(t)
                                                   for t in _tagged(t8.prefix, processes)):
        _wineserver_kill(t8)
    if gamescope is not None and gamescope.poll() is None:
        gamescope.terminate()
        try:
            gamescope.wait(5)
        except subprocess.TimeoutExpired:
            gamescope.kill()
            try:
                gamescope.wait(5)
            except subprocess.TimeoutExpired:
                pass
    left = [pid for t, pids in _tagged(t8.prefix, _processes()).items() if t in tags for pid in pids]
    _kill(left)
    _wait_gone(left, 5)


def _sink_modules():
    """The pactl module numbers of the silent outputs sessions loaded."""
    return [line.split('\t')[0] for line in _pactl('list', 'short', 'modules').splitlines()
            if '\tmodule-null-sink\t' in line and 'sink_name=%s' % SINK in line]


_open = []                              # the sessions not closed yet


@atexit.register
def close_all():
    """Closes the sessions still open: at exit, after an exception that came between a session's start and its
    caller's `try` (a signal: signals.py)."""
    for s in list(_open):
        s.close()


class Session:
    """Tekken 8's prefix inside gamescope's headless backend: the helper alone, or the game and the helper (as
    tekken7/autodump.py's Session). close() ends it, and only what it started."""

    def __init__(self, t8, helper_exe, run, with_game):
        for tool in ('gamescope', 'pactl') if with_game else ('gamescope',):
            if shutil.which(tool) is None:
                raise DumpError('Tekken 8 runs hidden in gamescope, with its sound sent to a silent output (pactl, of '
                                'PipeWire or PulseAudio): install %s with your distribution\'s packages' % tool)
        self.t8, self.run, self.closed = t8, run, False
        self.lock = self.gamescope = self.helper = self.sink_module = None
        self.tag = _new_tag()
        _open.append(self)
        try:
            self._start(helper_exe, with_game)
        except BaseException:
            self.close()
            raise

    def _start(self, helper_exe, with_game):
        t8, run = self.t8, self.run
        os.makedirs(run, exist_ok=True)
        self.lock = _lock(_lock_path(t8.prefix))
        left = list(_tagged(t8.prefix, _processes()))           # (what a killed session left: ended first)
        if any(_owner_alive(tag) for tag in left):
            raise DumpError('%s: try again when it is done' % BUSY)
        if left:
            _end(t8, left)
        for module in _sink_modules():
            _pactl('unload-module', module)
        if _players(t8.prefix, _processes()):
            raise DumpError(RUNNING)
        if os.path.exists(os.path.join(run, 'game.pid')):
            os.remove(os.path.join(run, 'game.pid'))
        shutil.copyfile(helper_exe, os.path.join(t8.prefix, 'pfx', 'drive_c', 't8helper.exe'))
        if with_game:
            self.sink_module = _pactl('load-module', 'module-null-sink', 'sink_name=' + SINK,
                                      'sink_properties=\'device.description="%s"\'' % SINK_NAME).strip() or None
        inside = os.path.join(run, 'inside.sh')
        with open(inside, 'w') as f:
            f.write(INSIDE)
        os.chmod(inside, 0o755)
        self.port, self.secret = _free_port(), secrets.token_hex(16)
        env = dict(os.environ, STEAM_COMPAT_CLIENT_INSTALL_PATH=t8.steam, STEAM_COMPAT_DATA_PATH=t8.prefix,
                   SteamAppId=str(APP_ID), SteamGameId=str(APP_ID), STEAM_COMPAT_APP_ID=str(APP_ID),
                   PROTON=os.path.join(t8.proton, 'proton'), T8DIR=t8.game, RUN=run, SINK=SINK, PORT=str(self.port),
                   SECRET=self.secret, WITH_GAME='1' if with_game else '0')
        env[SESSION_TAG] = self.tag
        with open(os.path.join(run, 'gamescope.log'), 'w') as log:
            self.gamescope = subprocess.Popen(
                ['gamescope', '--backend', 'headless', '-W', '1280', '-H', '720', '-w', '1280', '-h', '720', '-r', '60',
                 '--', inside], env=env, stdout=log, stderr=subprocess.STDOUT)

    def wait_game(self, timeout=START_TIMEOUT):
        end = time.time() + timeout
        while time.time() < end:
            p = os.path.join(self.run, 'game.pid')
            if os.path.isfile(p) and _text(p).strip():
                return int(_text(p))
            if self.gamescope.poll() is not None:
                raise DumpError('the hidden session ended (see %s)' % self.run)
            time.sleep(0.5)
        raise DumpError('Tekken 8 did not start within %d s' % timeout)

    def connect(self):
        self.helper = Helper(self.port, self.secret)
        return self.helper

    def close(self):
        """Ends the session (a signal meanwhile waits for its end: signals.deferred)."""
        if self.closed:
            return
        self.closed = True
        with signals.deferred():
            try:
                if self.helper:
                    self.helper.quit()
                if self.lock is not None:       # (else another session may be running, and this one started nothing)
                    _end(self.t8, [self.tag], self.gamescope)
                if self.sink_module:
                    _pactl('unload-module', self.sink_module, timeout=5)
            finally:
                if self in _open:
                    _open.remove(self)
                if self.lock:
                    self.lock.close()


# ---------------------------------------------------------------- dumping

def owned_dlc(t8, helper_exe, run):
    """{DLC app id: owned} as the game asks Steam."""
    if tekken8_running(t8):                 # (Session checks again, once no other session runs)
        raise DumpError(RUNNING)
    s = Session(t8, helper_exe, run, False)
    try:
        h = s.connect()
        return {a: owned for a, owned, _ in h.dlc('Z:' + os.path.join(t8.game, STEAMWORKS))}
    finally:
        s.close()


def unowned(fighters, cache=None):
    """{roster id: reason} of the fighters (roster ids) whose DLC the player's Steam account does not own, as Steam
    tells the game (Steam must be running). Base-game fighters are always owned."""
    dlc = [fid for fid in fighters if fid in DLC]
    if not dlc:
        return {}
    if not steam_running():
        raise DumpError('Steam is not running: start it, then try again (it tells which fighters you own)')
    cache = cache or CACHE
    owned = owned_dlc(find_tekken8(), build_helper(cache), os.path.join(cache, 'run'))
    return {fid: 'its DLC is not owned' for fid in dlc if not owned.get(DLC[fid], False)}


def _remove(folder, names):
    for name in names:
        try:
            os.remove(os.path.join(folder, name))
        except OSError:
            pass


def _save_fighter(h, fid, out, motbin_only, log):
    """Has the game read a fighter's files and saves them, checked, beside the ones saved before in `out` (NEW_SUFFIX):
    -> ({name: size}, the files to _put in place). DumpError (what it wrote removed, the files saved before as they
    were) when the game does not read one or hands over something else."""
    code, name = ROSTER[fid]
    paths = archive_paths(code, motbin_only)
    names = [n for _, n in paths]
    fields = names[0] + FIELDS_SUFFIX
    new = [n + NEW_SUFFIX for n in names + [fields]]
    try:
        sizes = h.save([p for p, _ in paths], [os.path.join(out, n) for n in new[:-1]])
        for (path, _), size in zip(paths, sizes):
            if size is None:
                raise DumpError('Tekken 8 did not read %s' % path)
        motbin = _head(os.path.join(out, new[0]), MOTBIN_BASE)
        found = motbin_roster_id(check_motbin(motbin))
        if found != fid:
            log('  (%s\'s moveset names roster id %s, not %d)' % (name, found, fid))
        moves, stride, offset, table = h.protected(paths[0][0])
        check_fields(motbin, moves, stride, offset, table)
        with open(os.path.join(out, new[-1] + '.part'), 'wb') as f:
            f.write(struct.pack('<III', moves, stride, offset))
            f.write(table)
        os.replace(os.path.join(out, new[-1] + '.part'), os.path.join(out, new[-1]))
        if not motbin_only:
            check_anmbin(_head(os.path.join(out, new[1]), ANMBIN_HEAD), sizes[1])
            check_mvl(_head(os.path.join(out, new[2]), len(MVL_MAGIC)))
    except BaseException:
        _remove(out, new + [new[-1] + '.part'])
        raise
    files = dict(zip(names, sizes))
    files[fields] = os.path.getsize(os.path.join(out, new[-1]))
    return files, new


def _put(out, new):
    """Puts files saved beside the ones saved before (NEW_SUFFIX) in their places (a signal meanwhile waits)."""
    with signals.deferred():
        for n in new:
            os.replace(os.path.join(out, n), os.path.join(out, n[:-len(NEW_SUFFIX)]))


def _save_common(h, out):
    """Has the game read the shared animation bank and saves it, checked, into `out` (put in place once checked: the
    one saved before stays when it fails): -> {name: size}."""
    (path, name), = common_paths()
    new = name + NEW_SUFFIX
    try:
        size, = h.save([path], [os.path.join(out, new)])
        if size is None:
            raise DumpError('Tekken 8 did not read %s' % path)
        check_anmbin(_head(os.path.join(out, new), ANMBIN_HEAD), size)
        _put(out, [new])
    except BaseException:
        _remove(out, [new])
        raise
    return {name: size}


def _whole(fighters, references, manifest):
    """The roster ids a dump saves whole: the fighters, then the references saved whole for this version or before
    (read_manifest's 'before'), which their motbin alone would not replace."""
    def saved_whole(fid):
        entries = (manifest['fighters'].get(ROSTER[fid][0]), manifest['before']['fighters'].get(ROSTER[fid][0]))
        return any(isinstance(e, dict) and not e.get('motbin_only') for e in entries)
    return list(dict.fromkeys([fid for fid in fighters if fid in ROSTER] +
                              [fid for fid in references if fid in ROSTER and saved_whole(fid)]))


def plan(fighters, references, manifest, folder, force=False):
    """What a dump has to read: ([(roster id, motbin_only)] in order, whether the shared bank too, {roster id:
    reason} of what cannot be saved). Fighters are saved whole; references (roster ids) only their motbin and fields
    (unless among the fighters, or saved whole before: _whole); what the manifest has saved already is not read again
    (but with force), and the shared bank goes with the first fighter saved whole."""
    skipped = {fid: 'not a fighter of Tekken 8 that can be saved' for fid in list(fighters) + list(references)
               if fid not in ROSTER}
    whole = _whole(fighters, references, manifest)
    alone = list(dict.fromkeys(fid for fid in references if fid in ROSTER and fid not in whole))
    todo = [(fid, motbin_only) for fids, motbin_only in ((whole, False), (alone, True)) for fid in fids
            if force or not is_saved(folder, manifest, ROSTER[fid][0], motbin_only)]
    common = bool(whole) and (force or not common_saved(folder, manifest))
    return todo, common, skipped


def dump(fighters, out=None, log=print, cache=None, references=(), force=False):
    """Saves the fighters' moveset files (roster ids: ROSTER) into `out` (MOVESETS), with the shared animation bank
    once, and the references' (roster ids) motbin and fields alone (what the id maps take from other fighters), as the
    module docstring says, in one session. Owned fighters only (base-game ones always are). What is saved for this
    version of the game already is not read again (but with force). A fighter saved whole takes its place once the
    shared bank of this version is there (saved before, or now: when that fails, the files saved before stay). Nothing
    is started for a build the helper does not know (known_build). -> ({roster id: [paths]} saved now or before,
    {roster id: reason} skipped)."""
    out = os.path.abspath(out or MOVESETS)
    t8 = find_tekken8()
    version = game_version(t8.game, t8.library)
    manifest = read_manifest(out, version)
    todo, common, skipped = plan(fighters, references, manifest, out, force)

    def paths(fid):
        return [os.path.join(out, n) for n in sorted(manifest['fighters'][ROSTER[fid][0]]['files'])]

    def put(fid, motbin_only, files, new):
        code, name = ROSTER[fid]
        _put(out, new)
        manifest['fighters'][code] = {'id': fid, 'name': name, 'motbin_only': motbin_only, 'files': files}
        manifest['before']['fighters'].pop(code, None)          # (its files are this version's now)
        write_manifest(out, manifest)
        saved[fid] = paths(fid)

    whole = _whole(fighters, references, manifest)
    saved = {fid: paths(fid) for fid in dict.fromkeys(whole + [fid for fid in references if fid in ROSTER])
             if fid not in dict(todo)}
    if not todo and not common:
        return saved, skipped
    if not known_build(t8.game):
        raise DumpError(UNKNOWN_BUILD % (version['build'] or 'unknown'))
    if not steam_running():
        raise DumpError('Steam is not running: start it, then try again (Tekken 8 needs it)')
    if tekken8_running(t8):
        raise DumpError(RUNNING)
    cache = cache or CACHE
    run = os.path.join(cache, 'run')
    helper_exe = build_helper(cache)
    log('Tekken 8: %s (Proton: %s)' % (t8.game, os.path.basename(t8.proton)))
    if any(fid in DLC for fid, _ in todo):
        owned = owned_dlc(t8, helper_exe, run)
        for fid, _ in todo:
            if fid in DLC and not owned.get(DLC[fid], False):
                skipped[fid] = 'its DLC is not owned'
        todo = [(fid, motbin_only) for fid, motbin_only in todo if fid not in skipped]
        common = common and any(fid not in skipped for fid in whole)
        if not todo and not common:
            return saved, skipped
    log('Starting Tekken 8 in the background (no window, no sound) ...')
    started = time.time()
    pending = {}                    # {roster id: (files, the files beside)}: saved whole, waiting for the shared bank
    s = Session(t8, helper_exe, run, True)
    try:
        s.wait_game()
        h = s.connect()
        log('  the game runs after %.0f s' % (time.time() - started))
        end = time.time() + ATTACH_TIMEOUT
        while True:                                      # (the game's code may not be mapped at once)
            try:
                h.attach()
                break
            except DumpError as error:
                if time.time() > end or str(error).startswith(REFUSED):     # (another build: no use waiting)
                    raise
                time.sleep(1)
        _until('Tekken 8 did not open its moveset files', h.ready, READY_TIMEOUT)
        log('  ready after %.0f s' % (time.time() - started))
        os.makedirs(out, exist_ok=True)
        for fid, motbin_only in todo:
            code, name = ROSTER[fid]
            t = time.time()
            try:
                files, new = _save_fighter(h, fid, out, motbin_only, log)
            except DumpError as e:
                h.ready()                               # (a helper that stopped ends the session: no fighter is read)
                skipped[fid] = str(e)
                log('  %s: %s' % (name, e))
                continue
            if motbin_only:
                put(fid, motbin_only, files, new)
            else:
                pending[fid] = (files, new)
            log('  %s (%s)%s: %.1f MB in %.1f s' % (name, code, ', its moveset alone' if motbin_only else '',
                                                   sum(files.values()) / 1e6, time.time() - t))
        why = 'the shared animations are not saved'
        if common and (pending or any(fid in saved for fid in whole)):     # (not when none of them could be saved)
            t = time.time()
            try:
                manifest['common'] = _save_common(h, out)
            except DumpError as e:
                why = 'the shared animations could not be saved: %s' % e
                log('  %s' % why)
            else:
                manifest['before']['common'] = {}               # (what was saved before had the earlier one)
                write_manifest(out, manifest)
                log('  the shared animations (%s): %.0f MB in %.1f s' % (', '.join(manifest['common']),
                                                                        sum(manifest['common'].values()) / 1e6,
                                                                        time.time() - t))
        for fid in list(pending):
            files, new = pending.pop(fid)
            if common_saved(out, manifest):
                put(fid, False, files, new)
            else:
                _remove(out, new)
                skipped[fid] = why
    finally:
        for files, new in pending.values():             # (stopped before they took their places)
            _remove(out, new)
        s.close()
    log('Done in %.0f s.' % (time.time() - started))
    return saved, skipped
