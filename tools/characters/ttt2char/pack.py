"""Character packs: what the port loads to add a fighter (runtime/src/title/roster.cpp).

A pack is a folder `<code>/` in the characters folder (default_folder: $TTT2_CHARACTERS, else
$XDG_DATA_HOME/ttt2/characters, else ~/.local/share/ttt2/characters, as the port finds it):
    character.ini              format = PACK_FORMAT, code = <three letters>, donor = <a TTT2 fighter's code>,
                               sex = female | male, slot = its number k (place(k): select id 64 + k, its motion
                               row and grid cell), chr_tones = its voice bank's shout tones (the win quotes' come
                               after), revision = revision(d) (the port ignores it), and stand_in = <a TTT2
                               fighter's code> when the fighter fights with that one's moveset because its own could
                               not be had when it was imported (importer.with_stand_in; the launcher offers to update
                               the pack once it can be had; the port ignores this too)
    <code>.xml                 item database (BXML)
    <code>.nud .nut .bon       body model, textures, skeleton
    <code>.mop                 spring entries of its extra bones (Kazumi's tiger)
    <code>.moveset .motion     moveset (motbin) and motion pack
    <code>.mvl                 the practice command list (MVLT)
    se_Chr_<code>.nus3bank     its voice: shouts, damage voices, the announcer's call, then its win quotes (the first
                               chr_tones tones are the shouts'); intro lines (rm_Dst_); the long win quote one win
    rm_Dst_<code>.nus3bank     pose streams (rm_Dwi_)
    rm_Dwi_<code>.nus3bank
    art/                       its pictures for the loading and VS screens and the costume chooser (the port shows
                               its art when the pack has this folder)
    colours.json               its player 2 colours (palette number: 1P and 2P colour), for shared/
    source/                    what shared/ takes from its game, saved by its import (shared.source_files): the
                               pictures (PNG, named after their objects: source_name) and its name call
                               (name_call.wav), so that shared/ is made again without its game (the port skips it)
    <outfit>.nud .nut .bon     optional complete preset bodies, with matching .xml and .mop;
                               character.ini outfits lists their three-letter codes in preview order
                               (up to fourteen). art/costumes.nut then has one texture per preset.
The packs share `shared/keys/` (made for all of them together, shared.py): changed copies of the title's own entries
(2D layouts with every added fighter's pictures, the big portraits' container, the costume palettes and colour grid,
the select screen's name calls; `<key>.bin`) and texture pages to add to its texture containers (`<key>.add`).
Files a pack leaves out (<code>.mop, .havok.xml: spring bones and cloth collision; <code>.mvl: the practice
command list; the sound banks) are the donor's (a fighter fighting with its donor's moveset for now, MOVESET_SOURCE
'donor', has no .mvl: the donor's command list). A pack holds the other game's assets: it is for the player's own
use only.

A pack is current when its `format` is PACK_FORMAT. The port loads current packs only, and shared/ is made for them
only: an older importer's pack keeps its place, unloaded, until its fighter is imported again (the launcher offers it:
launcher.py status "outdated"). A pack without a `format` line is format 1 unless it has its own `keys/` (the earliest
packs, made one by one before shared/: the port would join those to shared/'s), which is format 0; a newer importer's
pack (a format above PACK_FORMAT) is not loaded either, nor replaced by this one's. PACK_FORMAT goes up when packs
made before cannot work with the port's or shared/'s new design. A current pack whose `revision` (none: 0) is below
revision(d) is loaded but misses what a new import gives (the launcher offers to update it: launcher.py status
"update"); REVISION goes up for changes every fighter gets, a definition's REVISION for its fighter's alone.
character.ini is read as the port reads it: a line is `key = value` ('#' starts a comment), and numbers (format, slot,
revision) are ASCII digits only, else none.
"""
import os
import re
import shutil
import stat
import struct
import subprocess
import sys

from . import InputError, signals, paths
from .convert import gauge
from .characters import GAMES, game_of

FILES = ('.xml', '.nud', '.nut', '.bon', '.moveset', '.motion')
SHARED = 'shared'               # the packs' shared title entries
SOURCE = 'source'               # a pack's copy of what shared/ takes from its game
PACK_FORMAT = 1                 # character.ini `format` of the packs made now (the port's kPackFormat, roster.cpp)
REVISION = 8                    # what packs made before lack, for every fighter (1: cloth, outfits, move fixes;
                                # 2: tag combos; Reina's throws, bounds and icon; 3: face animations and eyelids;
                                # 5: main sync; 6: the definitions' bounds alone, Tekken 7's after the Bound Mod:
                                # screws, tornados and slams no longer bound; 7: hit reactions that keep what they
                                # do: no stagger, crumple or launch replaced by another kind, the source's own flips,
                                # launches and stun falls; Tekken 7's hit points past the limbs and in the trunk,
                                # Negan's 0x72; Tekken 7's contact tests and moveset variables, Starburst and the
                                # cane, the opponent's move by its own id; the Tag Assault's incoming partner
                                # attacks with its own d/f+1, a string's continued bound move can Tag Assault;
                                # 8: a group cancel row counts its own group's rows, not the source's)
# Added fighter k's place as the port gives it (roster.cpp): select id 64 + k, a motion row (what the moveset's
# fighter fields hold: the rows no fighter has first, then 69 on) and a select grid cell (roster.cpp kCells): the free
# ends of the top row, then columns beyond the grid's ends (-1 and 23, then -2 and 24), then (ROW_CELLS) a new top row
# over the title's three, from the '?' column outwards: the grid has it only while a fighter's place is past CELLS
# (needs_new_row; art.four_rows moves the grid down for it, shared/grid.ini tells the port). A cell is (column, grid
# row, anchor, columns from it): its picture goes where the grid panel of fighter `anchor` (in grid row 1, or the
# cell's own row) is, that many columns over, in the cell's row (row 0: at the top row's height; above it: rows'
# pitches higher).
FIRST_ID = 64
DIRECT_ROWS = (58, 64, 61, 62, 65)
FIRST_VIRTUAL_ROW = 69
CELLS = ((19, 0, 'edd', 0), (2, 0, 'bru', 0), (20, 0, 'lee', 0), (1, 0, 'rav', 0), (21, 0, 'lei', 0), (0, 0, 'rog', 0),
         (22, 0, 'kum', 0),
         (23, 0, 'kum', 1), (-1, 0, 'rog', -1), (23, 1, 'kum', 1), (-1, 1, 'rog', -1), (23, 2, 'pan', 1),
         (-1, 2, 'mok', -1),
         (24, 1, 'kum', 2), (-2, 1, 'rog', -2), (24, 2, 'pan', 2), (-2, 2, 'mok', -2), (24, 0, 'kum', 2),
         (-2, 0, 'rog', -2))
# right of the '?' column, then left, outwards (columns 0-10 from Roger's panel, 12-24 from Kuma's)
ROW_CELLS = tuple(cell for right, left in zip(range(12, 25), range(10, -3, -1))
                  for cell in ((right, -1, 'kum', right - 22), (left, -1, 'rog', left)))


def needs_new_row(slots):
    """Whether the select grid needs its new top row for fighters in these places."""
    return any(k >= len(CELLS) for k in slots)


MAX_FIGHTERS = 128              # (the port's kMaxFighters: places 0 to 127)
CODE = re.compile(r'[a-z]{3}')  # a pack's code, as the port takes it
REPOSITORY = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))


def place(k):
    """dict(id, row, column, grid_row, anchor, columns) of added fighter k (the cell's fields None when the grid is
    full)."""
    row = DIRECT_ROWS[k] if k < len(DIRECT_ROWS) else FIRST_VIRTUAL_ROW + k - len(DIRECT_ROWS)
    every = CELLS + ROW_CELLS
    column, grid_row, anchor, columns = every[k] if k < len(every) else (None, None, None, None)
    return dict(id=FIRST_ID + k, row=row, column=column, grid_row=grid_row, anchor=anchor, columns=columns)


def default_folder():
    if os.environ.get('TTT2_CHARACTERS'):
        return os.environ['TTT2_CHARACTERS']
    return os.path.join(paths.data_root(), 'characters')


def output_folder(folder):
    """Where packs go (`folder`, else default_folder()); never a folder of the repository that git would commit."""
    folder = os.path.abspath(os.path.expanduser(folder or default_folder()))
    real = os.path.realpath(folder)       # through symbolic links, which could lead into the repository
    # (installed, in <prefix>/share/ttt2/characters as in the AppImage, the importer is in no repository)
    try:
        inside = os.path.normcase(os.path.commonpath([real, REPOSITORY])) == os.path.normcase(REPOSITORY)
    except ValueError:
        inside = False
    if os.path.exists(os.path.join(REPOSITORY, '.git')) and inside and not git_ignores(real):
        raise InputError('the pack would go into the repository (%s): packs hold Namco\'s assets and must stay out '
                         'of it; leave out --out (the default is %s)' % (folder, default_folder()))
    return folder


def git_ignores(folder):
    """Whether git ignores `folder` itself (as it does local/) in the repository (False when git cannot tell): a
    name no ignore pattern covers, in that folder."""
    # The portable Windows launcher need not have the development app's Git
    # on PATH. Recognize only the explicit private /local/ cache exclusion.
    local = os.path.abspath(os.path.join(REPOSITORY, 'local'))
    try:
        canonical_local = os.path.realpath(local)
        inside_local = os.path.normcase(os.path.commonpath([os.path.realpath(folder), canonical_local])) == os.path.normcase(canonical_local)
        plain_local = os.path.normcase(canonical_local) == os.path.normcase(local)
        with open(os.path.join(REPOSITORY, '.gitignore'), encoding='utf-8') as rules:
            patterns = [line.strip() for line in rules]
        if inside_local and plain_local and '/local/' in patterns and not any(p.startswith('!') for p in patterns):
            return True
    except (OSError, ValueError):
        pass
    try:
        probe = os.path.join(folder, 'ttt2-pack-probe')
        return subprocess.run(['git', '-C', REPOSITORY, 'check-ignore', '-q', probe],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def remove(path):
    """Deletes a pack folder (an installed() path): its character.ini first, so that a folder left half deleted is no
    pack to the port. A link to a pack goes, not what it links to. The other packs keep their places (their files are
    made for them: model ids, motion row, pictures); the next fighter imported takes the first free one. What a
    write() that was killed left beside it goes too (a leftover that cannot be deleted is only reported: the pack is
    gone all the same)."""
    if os.path.islink(path):
        os.remove(path)
    else:
        delete_pack(path)
    for left in _working(path):
        try:
            delete_pack(left)
        except OSError as error:
            _cannot_delete(left, error)


def _working(target):
    """write()'s folders beside pack folder `target`: the pack being made and the one it replaces (hidden: neither
    the port nor installed() takes them for packs)."""
    parent, name = os.path.split(target)
    return os.path.join(parent, '.%s.part' % name), os.path.join(parent, '.%s.old' % name)


def delete_path(path):
    """Deletes a file, a link (not what it leads to) or a folder with all in it, also folders of it that are read-only
    (an earlier pack copied from a read-only place); what its owner cannot change (another user's) raises OSError."""
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        try:
            shutil.rmtree(path)
        except PermissionError:
            for top, folders, _ in os.walk(path):
                for name in folders:
                    folder = os.path.join(top, name)
                    if not os.path.islink(folder):
                        try:
                            os.chmod(folder, stat.S_IMODE(os.lstat(folder).st_mode) | stat.S_IRWXU)
                        except OSError:
                            pass
            os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IRWXU)
            shutil.rmtree(path)


def delete_pack(path):
    """delete_path() for a pack folder: its character.ini first, so that what is left if deleting stops halfway is no
    pack (recover() never takes it for one)."""
    ini = os.path.join(path, 'character.ini')
    if os.path.isdir(path) and not os.path.islink(path) and os.path.lexists(ini):
        try:
            os.remove(ini)
        except PermissionError:
            os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | stat.S_IRWXU)
            os.remove(ini)
    delete_path(path)


def _cannot_delete(path, error):
    sys.stderr.write('import_character: warning: cannot delete %s (%s): delete it yourself (it may need root); the '
                     'game and the importer ignore it until then, but a new pack of that fighter cannot be written\n'
                     % (path, error.strerror or error))


def remove_shared(folder):
    """Deletes <folder>/shared/ (no pack the importer knows is left to share it) and what a remake of it left (a link
    goes, not what it leads to)."""
    for path in (os.path.join(folder, SHARED + end) for end in ('', '.part', '.old')):
        delete_path(path)


def source_pictures(d):
    """The objects of fighter d's game whose pictures shared/ is made from (convert/art.py's Sources: d.ART's bust,
    body and name)."""
    return [d.ART['bust'][0], d.ART['body'][0], d.ART['name']]


def source_name(path):
    """The file in a pack's source/ of the picture of object `path` ('/Game/UI/CS_CH_L/CS_CH_L_KZM' ->
    'CS_CH_L_KZM.png'): a definition that names other pictures finds none of its pack's."""
    return path.rsplit('/', 1)[-1].split('.')[0] + '.png'


def carries_source(path, d):
    """Whether pack folder `path` of fighter d has its copy of every picture shared/ takes from d's game (packs made
    before source/ have none: shared/ needs their game, or keeps what it has of them)."""
    return all(os.path.isfile(os.path.join(path, SOURCE, source_name(p))) for p in source_pictures(d))


def holds(folder, codes):
    """The fighters of `codes` that shared/ in characters folder `folder` has pictures of: a 2D layout of
    shared/keys/ with their grid cell (the symbol face_panel_<code>, LMB's {u32 length, name, NUL}), which a
    fighter whose game is gone keeps from there."""
    keys = os.path.join(folder, SHARED, 'keys')
    wanted = {code: struct.pack('>I', len('face_panel_' + code)) + ('face_panel_%s\0' % code).encode('latin1')
              for code in codes}
    found = set()
    for name in sorted(os.listdir(keys)) if os.path.isdir(keys) else ():
        if not name.endswith('.bin') or len(found) == len(wanted):
            continue
        with open(os.path.join(keys, name), 'rb') as f:
            if f.read(4) != b'LMB\0':
                continue
            data = f.read()
        found |= {code for code, symbol in wanted.items() if symbol in data}
    return found


def revision(d):
    """The character.ini `revision` of fighter d's pack made now: REVISION and the definition's own (each only goes
    up, so a pack made before has a lower one)."""
    return REVISION + vars(d).get('REVISION', 0)


def character_ini(d, slot, chr_tones=0, voice_extra=(), weapons=(), outfits=(), sound_extra=(), gauge_sound=None):
    """voice_extra: the se_Chr tones of the shouts past the donor's (the port appends them to the voice list);
    sound_extra: the se_Chr tones of its sound effects (the port appends them to its item sounds: convert/sounds.py);
    gauge_sound: the item sound its gauge plays as it fills up (convert/gauge.py);
    weapons: weapons.of_skeleton's [(k, parent bone, [(point number, slot)], summon)] (the port poses them), or with
    a ramp (convert/summonfade.ramps: how a fading summon is scaled):
    k:parent:points[:summon[:ramp[:channels[:anchored]]]], a point `n` hitting as slot n, else `n>slot`; channels: the
    pair posing a bone numbered below 800 (empty: its own), anchored 1: held in the world from each move's first frame,
    2: a hit point following the held one (convert/prefabs8.with_channels); the definition's REST_SUMMONS (the summons out when no move says otherwise,
    through hits and throws too: roster.cpp) as rest_summons; the definition's UNBLURRED (mesh names the port's motion blur
    leaves out: title/unblurred.h) as unblurred."""
    def item(k, parent, points, summon, ramp=0, channels=None, anchored=0):
        return '%d:%d:%s' % (k, parent, ','.join('%d' % n if n == slot else '%d>%d' % (n, slot) for n, slot in points)) \
            + (':%d' % summon if summon is not None else (':' if ramp or channels is not None or anchored else '')) \
            + (':%d' % ramp if ramp or channels is not None or anchored else '') \
            + (':%d' % channels if channels is not None else (':' if anchored else '')) \
            + (':%d' % anchored if anchored else '')
    return ('# %s, from %s (made on this machine from the player\'s own copy)\n'
            'format = %d\ncode = %s\ndonor = %s\nsex = %s\nslot = %d\nchr_tones = %d\nrevision = %d\n'
            % (d.NAME.split(' (')[0], GAMES[game_of(d)], PACK_FORMAT, d.CODE, d.DONOR, d.SEX, slot, chr_tones,
               revision(d))
            + ('stand_in = %s\n' % d.DONOR if getattr(d, 'WITHOUT_OWN_MOVESET', False) else '')
            + ('voice_extra = %s\n' % ' '.join(map(str, voice_extra)) if voice_extra else '')
            + ('sound_extra = %s\n' % ' '.join(map(str, sound_extra)) if sound_extra else '')
            + ('weapons = %s\n' % ' '.join(item(*w) for w in weapons) if weapons else '')
            + ('rest_summons = %s\n' % ' '.join(map(str, d.REST_SUMMONS))
               if isinstance(getattr(d, 'REST_SUMMONS', None), tuple) else '')
            + ('unblurred = %s\n' % ' '.join(d.UNBLURRED)
               if isinstance(getattr(d, 'UNBLURRED', None), tuple) and d.UNBLURRED else '')
            + ('outfits = %s\n' % ' '.join(outfits) if outfits else '')
            + (gauge.ini_line(d, gauge_sound) + '\n' if gauge.ini_line(d) else ''))


def read_ini(path):
    """{key: value} of a character.ini, as the port reads it: lines end at '\n' only, '#' starts a comment, and keys
    and values lose spaces, tabs and '\r' around them (nothing else)."""
    out = {}
    with open(path, encoding='utf-8', errors='replace', newline='') as f:
        for line in f.read().split('\n'):
            line = line.split('#', 1)[0]
            if '=' in line:
                k, v = line.split('=', 1)
                out[k.strip(' \t\r')] = v.strip(' \t\r')
    return out


def number(value):
    """A character.ini number as the port reads it: ASCII digits only and below 2**31, else None."""
    return int(value) if re.fullmatch(r'[0-9]+', value or '') and int(value) < 2 ** 31 else None


def installed(folder):
    """The packs in the characters folder: [{'path', 'code', 'donor', 'slot' (None if it names none), 'format' (0:
    an older importer's; see above), 'revision' (0 without one), 'stand_in' (the code of the fighter whose moveset
    it fights with because its own could not be had, '' for none), 'outfits' (how many preset outfits it has),
    'valid' (the port takes it: a three-letter code and a donor), 'current' (valid and of PACK_FORMAT: the port loads
    it), 'newer' (valid and of a later format)}], by folder name. A folder whose name starts with a dot is none
    (write()'s pack being made, or the one it replaces; the port skips them too)."""
    out = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        ini = os.path.join(path, 'character.ini')
        if name.startswith('.') or not os.path.isdir(path) or not os.path.isfile(ini):
            continue
        v = read_ini(ini)
        if 'format' in v:
            form = number(v['format']) or 0
        else:
            form = 0 if os.path.isdir(os.path.join(path, 'keys')) else 1
        valid = bool(CODE.fullmatch(v.get('code', ''))) and v.get('donor', '') != ''
        out.append(dict(path=path, code=v.get('code', ''), donor=v.get('donor', ''), slot=number(v.get('slot', '')),
                        format=form, revision=number(v.get('revision', '')) or 0, stand_in=v.get('stand_in', ''),
                        outfits=len(v.get('outfits', '').split()), valid=valid,
                        current=valid and form == PACK_FORMAT, newer=valid and form > PACK_FORMAT))
    return out


def placed(packs):
    """[(place, pack)] of installed() packs, by place, as the port gives them (roster.cpp prepare_roster): every pack
    it takes (valid), also those it does not load (they keep their places); first each at the slot it names (below
    MAX_FIGHTERS, the first pack naming it), then the others at the first free places (none when all are taken)."""
    at = {}
    valid = [p for p in packs if p['valid']]
    for p in valid:
        if p['slot'] is not None and p['slot'] < MAX_FIGHTERS and p['slot'] not in at:
            at[p['slot']] = p
    for p in valid:
        if any(q is p for q in at.values()):
            continue
        free = next((k for k in range(MAX_FIGHTERS) if k not in at), None)
        if free is not None:
            at[free] = p
    return sorted(at.items(), key=lambda item: item[0])


def loaded(packs):
    """[(place, pack)] of the packs the port loads, by place: current ones, of each code the first by place."""
    out, codes = [], set()
    for k, p in placed(packs):
        if p['current'] and p['code'] not in codes:
            codes.add(p['code'])
            out.append((k, p))
    return out


def places_of(packs):
    """{pack code: place} as the port gives them (placed()): a code's place is that of its pack the port loads, else
    (no current pack of it) its first pack's, which a re-import of its fighter keeps."""
    out = {p['code']: k for k, p in loaded(packs)}
    for k, p in placed(packs):
        out.setdefault(p['code'], k)
    return out


def choose_slot(folder, code):
    """The place for a fighter being (re)imported: its pack's, else the first one no pack has; None when all are
    taken. (A write() killed between its renames is put right first: its earlier pack keeps its place.)"""
    recover(folder)
    packs = installed(folder)
    places = places_of(packs)
    if code in places:
        return places[code]
    used = {k for k, _ in placed(packs)}
    return next((k for k in range(MAX_FIGHTERS) if k not in used), None)


def recover(folder):
    """A write() stopped between its two renames (killed, the power lost) leaves a fighter's earlier pack only as
    .<code>.old, which the port does not load and whose place another fighter could take: it is put back. (The new
    pack, .<code>.part, was never added: the next write() deletes it.)"""
    if not os.path.isdir(folder):
        return
    for name in os.listdir(folder):
        code = name[1:-len('.old')]
        if not (name.startswith('.') and name.endswith('.old')) or not code or code.startswith('.'):
            continue
        old, real = os.path.join(folder, name), os.path.join(folder, code)
        if not os.path.lexists(real) and not os.path.islink(old) and os.path.isfile(os.path.join(old, 'character.ini')):
            try:
                os.replace(old, real)
            except OSError:
                pass


def target_of(folder, d):
    """The folder write() replaces with d's pack: <folder>/<code>, or when that is a link to a folder, the folder it
    leads to, if that is empty or holds d's pack (InputError otherwise: a link aimed at other packs, or at any other
    folder, is never replaced; nor a newer importer's pack)."""
    target = os.path.join(folder, d.CODE)
    real = target
    if os.path.islink(target) and os.path.isdir(target):
        real = os.path.realpath(target)
        ini = os.path.join(real, 'character.ini')
        try:
            empty = not os.listdir(real)
        except OSError:
            empty = False
        if not empty and not (os.path.isfile(ini) and read_ini(ini).get('code') == d.CODE):
            raise InputError('%s is a link to %s, which is not %s\'s pack (it holds no character.ini of code %s): it '
                             'is not replaced; delete the link, or point it at that pack\'s folder'
                             % (target, real, d.NAME, d.CODE))
    for p in installed(folder):
        if p['code'] == d.CODE and p['newer']:
            raise InputError('%s\'s pack in %s was made by a newer importer (pack format %d; this one makes %d): it is '
                             'not replaced by an older one; update Tekken Tag 2 Ultimate Edition'
                             % (d.NAME, p['path'], p['format'], PACK_FORMAT))
    return real


def write(folder, d, files, slot, chr_tones=0, voice_extra=(), weapons=(), outfits=(), sound_extra=(),
          gauge_sound=None):
    """Writes the pack <folder>/<code>/ from files {suffix or file name: bytes} (a suffix starts with '.': the file
    is <code><suffix>); returns its path. The pack is made whole in a hidden folder beside its place first
    (.<code>.part, character.ini last), which then takes the place of the fighter's earlier pack: that one goes
    whole, so nothing of an older importer's pack stays (its own keys/, files no longer made). A write that stops (the
    launcher's Cancel, a full disk) leaves an earlier pack as it was, and a new one not there; a signal waits for
    the swap. A link to a pack stays: the pack it leads to is replaced (target_of: only a pack of this fighter)."""
    recover(folder)
    target = os.path.join(folder, d.CODE)
    real = target_of(folder, d)
    part, old = _working(real)
    out = {(d.CODE + name if name.startswith('.') else name): data for name, data in files.items()}
    out.pop('character.ini', None)
    out['character.ini'] = character_ini(d, slot, chr_tones, voice_extra, weapons, outfits,
                                         sound_extra, gauge_sound).encode('utf-8')
    os.makedirs(os.path.dirname(real), exist_ok=True)
    for path in (part, old):                        # (a killed write's, or one that could not be deleted)
        try:
            delete_pack(path)
        except OSError as error:
            raise InputError('cannot delete %s, left beside %s\'s pack by an earlier import (%s): delete it yourself '
                             '(it may need root), then add %s again' % (path, d.NAME, error.strerror or error, d.NAME))
    try:
        for name, data in out.items():
            path = os.path.join(part, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    try:
        with signals.deferred():                    # (renames only: the earlier pack goes and the new one comes)
            if os.path.lexists(real):
                os.replace(real, old)
            try:
                os.replace(part, real)
            except OSError:
                if os.path.lexists(old):
                    os.replace(old, real)           # (the earlier pack back)
                raise
    finally:
        if os.path.lexists(real):                   # (else both are kept: one of them is the fighter's pack)
            for path in (part, old):
                try:
                    delete_pack(path)
                except OSError as error:            # (the pack is written: the next write() says it cannot)
                    _cannot_delete(path, error)
    return target
