"""A Tekken 8 fighter's voice clips by kind, for convert/voice.py (which puts them into the donor's TTT2 banks).

Every regular fighter's voice follows one naming (the code in upper case, the intros' and wins' in lower case):
    Play_<CODE>_Attack_S_001 .., _M_001 .., _L_001 ..   shouts, short, medium and long          ('atk', s/m/l)
    Play_<CODE>_Attack_SP_001 ..                        special shouts                          ('org', None)
    Play_<CODE>_Damage_S_001 .., _L_001 ..              damage voices (there is no medium one)  ('dmg', s/l)
    Play_<CODE>_Damage_KO_001 ..                        KO screams                              ('ko', None)
    Play_<code>_sta_00 ..                               intro lines                             ('intro', None)
    Play_<code>_win_00 ..                               win quotes                              ('win', None)
    Play_syvo_name_<CODE>                               the announcer calling the fighter       ('name', None)
(the fighter's own SDA_BankChara<CODE> maps the animations' keys <code>_s00 / <code>_w00 to the intro and win
events by these numbers; variants such as Play_<code>_win_00_vr00 are left out, as are the spoken move lines
Attack_Line_*, Charge, Yell, RageArt, Laugh and the Stun/Wall/Choke/Faint damage voices). Most fighters have 9, 6
and 4 shouts of the sizes, 4 special ones, 10 short and 5 long damage voices, 3 KO screams, 3 intros and 3 wins;
King, Kuma, Panda, Azazel and knk fewer (5, 4, 2 shouts, 2 special ones, 6 or 7 short and 3 or 5 long damage voices;
Azazel no intro, win or name call). Numbers can have gaps; each kind is in number order.
Each event is a bank of tekken8/wwise.py; an intro's or win pose's plays a layer container: the voice line (mono)
with its foley (stereo): the clip is the mono medium (the voice), else the event's first. Intro and win lines are
padded with digital silence to the timing of Tekken 8's own scenes; they play on the donor's animations here, so the
padding is cut down (trim).

Tekken 8's moves name their voice by sound id, not by number (Tekken 7's shout n): a sound property (0x87f0 player,
0x87f1, 0x87f2 opponent: the bank in `value`, the number in `value3`) of bank 16 (VOICE_BANK) plays the event the
fighter's sound data asset (SDA_BankChara<CODE>, a PolarisSoundDataAsset) lists with that SoundID in its
SoundDataVoiceTone (Reina's 13393 Play_ZBR_Attack_M_002, her Wind God Fist's; 13342 Play_ZBR_Attack_Line_001, her
Electric Wind God Fist's; ids are unique across fighters: some story moves play another fighter's); bank 17
(CATEGORY_BANK) plays one of a kind (CATEGORIES; `value2` the chance in percent: the shared moves' way, a wake-up
kick's short shout half the time). Bank 2 (Tekken 7's shout n) is left only in the SE_KIAI_n test moves and two throw
escapes. Her moves also say lines of other kinds (Attack_Line_*, Charge, Laugh, Other_*, ...): add_lines makes the
ones the moves of a moveset play clips of their own ('line'), shouts after hers; move_voices gives the converter the
TTT2 voice of each.

Written for this project from the files themselves (no third-party code).
"""
import collections
import re
import struct

import numpy as np

from .. import InputError
from . import uprops, wwise, zen

# (pattern of an event name with the fighter's code in it, its kind); a size letter is group 1 when the kind has one
KINDS = [(r'Play_%(code)s_Attack_([SML])_(\d+)', 'atk'),
         (r'Play_%(code)s_Attack_SP_(\d+)', 'org'),
         (r'Play_%(code)s_Damage_([SML])_(\d+)', 'dmg'),
         (r'Play_%(code)s_Damage_KO_(\d+)', 'ko'),
         (r'Play_%(code)s_sta_(\d+)', 'intro'),
         (r'Play_%(code)s_win_(\d+)', 'win')]
EVENTS = 'Polaris/Content/WwiseAudio/Event/Play_%s_'      # where a fighter's event banks are (a name prefix)
NAME_CALL = 'Play_syvo_name_%s'
# Intro and win lines come padded to their scenes (Reina's: 0.4 to 2.2 s of silence before the line, 0.2 to 1.8 s
# after; zeros): cut to these margins (seconds before, after). TTT2's own lines start 0.4 s in or later (Heihachi's),
# and a win line fills several of the donor's win tones: its padding would make the banks far bigger than the
# donor's (the title's sound memory is sized for its own).
TRIMMED = ('intro', 'win')
LINE_MARGINS = (0.4, 0.25)
SILENT = 16                         # samples no louder than this are silence (of 32767; the padding is 0)
# The moves' voices (see above): the sound properties, their banks, the sound data asset (its SoundDataVoiceTone:
# [{SoundID, AudioEvent (the event's object path), ...}]) and the kinds bank 17 plays one of by number: a kind of
# clips, or the name of a line's kind. Read off the moves that play them (Reina's use these numbers only): 0 the
# wake-up kicks' (where TTT2's play shout 0), 3 a thrown or downed fighter's (TTT2's damage voice 0), 6 with a wall
# hit's sound, 8 with another fighter's Stun line, 10 a jump's, 11 a parried attack's or a throw escape's; 1, 2, 4
# and 5 by their places among these (1 and 2 in her own attacks, 4 a downed fighter hit's, 5 a fall's)
SOUND_PROPERTIES = (0x87f0, 0x87f1, 0x87f2)
VOICE_BANK, CATEGORY_BANK = 16, 17
SOUND_DATA = 'Polaris/Content/Sound/Character/%s/SDA_BankChara%s'
CATEGORIES = {0: ('atk', 's'), 1: ('atk', 'm'), 2: ('atk', 'l'), 3: ('dmg', 's'), 4: ('dmg', 'l'), 5: ('ko', None),
              6: 'Damage_Wall', 8: 'Damage_Stun', 10: 'Yell', 11: 'Surprise'}
LINE = ('line', None)               # the kind of the other lines moves say (add_lines)
UNSAID = ('RageArt',)               # line kinds only Rage Arts say (not converted: the definitions' drop_moves)
LIST_END = 1100                     # a begin or end property list's last row
ROUND_START = 0                     # the alias slot of the round-start move


class Clips:
    """The Tekken 8 fighter's clips by kind: {(category, size): [(event name, rate, int16 [channels, samples])]}
    (the interface of convert.voice.Clips). store: store.Store; code: the fighter's Tekken 8 code ('zbr')."""

    # convert/voice.py stores a clip given to several tones once (they share it): a donor's win quote tones are
    # more than the fighter has lines (Jun's 7 tones of her own, Reina's 3 lines of 6 s), so her lines would fill
    # se_Dwi several times over: 2070 KB at the lowest rate, 24 kHz, against the 1972 KB (Jun's 1933 + 2 %) build()
    # keeps a bank within (the title's sound memory is sized for its own banks); stored once, 48 kHz fits
    STORED_ONCE = True

    def __init__(self, store, code):
        self.events = wwise.Events(store)
        self.kinds = {}
        self.skipped = []                  # (event name, why) of events found whose audio could not be read
        rules = [(re.compile(r'^%s$' % (pattern % {'code': re.escape(code)}), re.I), kind) for pattern, kind in KINDS]
        found = {}
        for path in store.find(EVENTS % code):
            name = path.rsplit('/', 1)[-1]
            if not name.lower().endswith('.bnk'):
                continue
            name = name[:-4]
            for rx, kind in rules:
                m = rx.match(name)
                if m:
                    size = m.group(1).lower() if kind in ('atk', 'dmg') else None
                    found.setdefault((kind, size), []).append((int(m.groups()[-1]), name))
                    break
        for kind, names in sorted(found.items(), key=lambda kv: (kv[0][0], kv[0][1] or '')):
            clips = [c for c in (self.clip(n, kind[0]) for _, n in sorted(names)) if c is not None]
            if clips:
                self.kinds[kind] = clips
        name = self.events.name(NAME_CALL % code.upper())
        clip = self.clip(name) if name else None
        if clip is not None:
            self.kinds[('name', None)] = [clip]
        if not self.kinds:
            raise InputError('Tekken 8 has no voice of the fighter %s (no Wwise events %s*.bnk): verify the '
                             'integrity of Tekken 8\'s files in Steam' % (code, EVENTS % code))
        self.code = code
        self.sound_ids = sound_data(store, code, self.skipped)     # SoundID -> event name: the moves' voices

    def clip(self, name, kind=None):
        """Event `name`'s clip (name, rate, int16 [channels, samples]): its mono medium (a voice line played with
        its stereo foley), else its first, trimmed when its kind is an intro's or a win's; None (noted in .skipped)
        when there is none it can read."""
        try:
            media = self.events.media(name)
            wems = [(m, self.events.wem(m)) for m in media]
            if not wems:
                raise KeyError('no sound')
            picked = next((w for m, w in wems if wwise.wem_format(w)[1] == 1), wems[0][1])
            rate, audio = wwise.decode_wem(picked)
        except (KeyError, ValueError) as error:
            self.skipped.append((name, str(error)))
            return None
        return name, rate, trim(audio, rate) if kind in TRIMMED else audio

    def kiai(self):
        """The shouts in the order a move numbers them (shout n is the n-th; taken as Tekken 7's: short, medium,
        long, then the special ones), then the other lines the moves say (add_lines)."""
        return [c for size in 'sml' for c in self.kinds.get(('atk', size), [])] + self.kinds.get(('org', None), []) + \
            self.kinds.get(LINE, [])

    def add_lines(self, k):
        """The lines the moves of Tekken 8 moveset k say (played: its moves' voices, through the sound data asset)
        that are no clip of a kind here (Attack_Line_*, Charge, Laugh, Other_*, a kind bank 17 plays such as Yell)
        become clips of their own (LINE), in the order the moves first say them: shouts after the fighter's own
        (kiai). Its Rage Art's lines are left out (UNSAID)."""
        have = {c[0].lower() for clips in self.kinds.values() for c in clips}
        unsaid = re.compile(r'^Play_%s_(%s)_' % (re.escape(self.code), '|'.join(UNSAID)), re.I)
        names = []
        for bank, n in played(k):
            if bank == VOICE_BANK:
                events = [self.sound_ids.get(n)]
            elif isinstance(CATEGORIES.get(n), str):
                events = self.events_of(CATEGORIES[n])
            else:
                continue
            for event in events:
                if event and event.lower() not in have and not unsaid.match(event):
                    have.add(event.lower())
                    names.append(event)
        clips = [c for c in (self.clip(self.events.name(n) or n) for n in names) if c is not None]
        if clips:
            self.kinds[LINE] = self.kinds.get(LINE, []) + clips

    def events_of(self, kind):
        """The fighter's voice events of a line's kind ('Yell': Play_ZBR_Yell_001 ..), in name order."""
        rx = re.compile(r'^Play_%s_%s_\d+$' % (re.escape(self.code), kind), re.I)
        return sorted((e for e in self.sound_ids.values() if rx.match(e)), key=str.lower)

    def move_voices(self, values):
        """{(bank, number): [TTT2 voice values]}: what the converter plays for Tekken 8's voices (moveset.Converter
        .voices8). Bank 16 (VOICE_BANK): a sound id's event's voice; bank 17 (CATEGORY_BANK): the voices of a kind's
        clips (the converter takes them in turn). values: {clip name: TTT2 voice value} (convert.voice.voice_values:
        how the banks it builds play each clip)."""
        low = {name.lower(): v for name, v in values.items()}
        out = {}
        for sid, event in self.sound_ids.items():
            if event.lower() in low:
                out[(VOICE_BANK, sid)] = [low[event.lower()]]
        for n, kind in sorted(CATEGORIES.items()):
            if isinstance(kind, str):
                names = [e.lower() for e in self.events_of(kind)]
            else:
                names = [c[0].lower() for c in self.kinds.get(kind, [])]
            voices = [low[e] for e in names if e in low]
            if voices:
                out[(CATEGORY_BANK, n)] = voices
        return out

    def damage(self, sizes):
        """The damage voices of the sizes, in that order of preference."""
        return [c for size in sizes for c in self.kinds.get(('dmg', size), [])]

    def pick(self, kind, counter):
        """The next clip of a kind (round robin), falling back to the nearest size (Tekken 8 has no medium damage
        voice: a medium one is a short one)."""
        cat, size = kind
        order = [size] + [s for s in ('m', 's', 'l', None) if s != size] if cat in ('atk', 'dmg') else [size]
        for s in order:
            lst = self.kinds.get((cat, s))
            if lst:
                k = counter.get((cat, s), 0)
                counter[(cat, s)] = k + 1
                return lst[k % len(lst)]
        return None


def trim(audio, rate, margins=LINE_MARGINS):
    """int16 [channels, samples] without the silence before and after its sound beyond `margins` (seconds before,
    after); all silent: as it is."""
    loud = np.nonzero(np.abs(audio.astype(np.int32)).max(0) > SILENT)[0]
    if not len(loud):
        return audio
    start = max(0, loud[0] - int(round(margins[0] * rate)))
    end = min(audio.shape[1], loud[-1] + 1 + int(round(margins[1] * rate)))
    return audio[:, start:end]


def sound_data(store, code, skipped=None):
    """{SoundID: event name} of the fighter's sound data asset's SoundDataVoiceTone (the voices its moves play by
    sound id); {} (noted in `skipped`) when the installation has none it can read."""
    path = SOUND_DATA % (code.upper(), code.upper())
    try:
        pkg = store.package(path)
        props, _ = uprops.read(pkg, pkg.main_export())
    except (KeyError, ValueError, OSError, struct.error, zen.ParseError) as error:
        if skipped is not None:
            skipped.append((path, str(error) or 'not read'))
        return {}
    out = {}
    for tone in props.get('SoundDataVoiceTone') or []:
        event = tone.get('AudioEvent')
        if tone.get('SoundID') is not None and event:
            out[tone['SoundID']] = event.rsplit('.', 1)[-1]          # ('/Game/Sound/.../Play_X.Play_X')
    return out


def played(k):
    """The voices [(bank, number)] the moves of Tekken 8 moveset k play (its sound properties of banks VOICE_BANK
    and CATEGORY_BANK), each once, in the order of the moves it reaches from its alias slots through cancels, group
    cancels, transitions and the reactions of its hits; not from its round-start move (alias slot 0: TTT2 plays the
    donor's), the only way to its story scenes. A line said against one fighter only (moveset.VERSUS8) or a kind's
    by a low chance (CHANCE8) is not: the converter leaves them out."""
    from ..convert import idmaps as M
    from ..convert.moveset import CHANCE8, VERSUS8
    from ..movesets import REACTION_MOVE_FIELDS
    moves = k.tables['moves']
    seen, out, groups = {k.resolve_alias(0x8000 + ROUND_START)}, [], {}
    todo = collections.deque(k.resolve_alias(0x8000 + s) for s in range(len(k.aliases)) if s != ROUND_START)
    while todo:
        i = todo.popleft()
        if i is None or not 0 <= i < len(moves) or i in seen:
            continue
        seen.add(i)
        mv = moves[i]
        rows = []
        for table, field, end in (('extra_move_properties', 'extraprops', lambda x: x['id'] == 0 and x['frame'] == 0),
                                  ('move_begin_props', 'begin_props', lambda x: x['id'] == LIST_END),
                                  ('move_end_props', 'end_props', lambda x: x['id'] == LIST_END)):
            if mv.get(field) is not None:
                rows += [x for _, x in k.iter_list(table, mv[field], end)]
        for x in rows:
            voice = (x['value'] & 0xFF, x.get('value3', 0) & 0xFFFFFF)
            if x['id'] not in SOUND_PROPERTIES or voice[0] not in (VOICE_BANK, CATEGORY_BANK) or voice in out:
                continue
            if x.get('req') and [c for c, _ in M.reqs(k, x['req'])] == [VERSUS8[0]] or \
                    voice[0] == CATEGORY_BANK and x.get('value2', 0) < CHANCE8:
                continue
            out.append(voice)
        todo.append(k.resolve_alias(mv['transition']) if mv.get('transition') is not None else None)
        for field in ('cancel', 'cancel2', 'cancel3', 'cancel4'):
            for c in M.cancels(k, mv.get(field)):
                if c['direction'] == M.GROUP:
                    if c['move_id'] not in groups:
                        groups[c['move_id']] = M.cancels(k, c['move_id'], 'group_cancels', M.GROUP_END)
                    todo += [k.resolve_alias(g['move_id']) for g in groups[c['move_id']]
                             if g['direction'] != M.GROUP_END]
                elif c['direction'] != M.LIST_END:
                    todo.append(k.resolve_alias(c['move_id']))
        for _, _, r in M.hitconds(k, mv.get('hit_condition')):
            if r is not None and r < len(k.tables['reactions']):
                todo += [k.resolve_alias(k.tables['reactions'][r][f]) for f in REACTION_MOVE_FIELDS
                         if k.tables['reactions'][r].get(f) is not None]
    return out


# the intro and win moves that play these lines (<code>_s00, <code>_w00: the fighter's SDA_BankChara<CODE> pairs
# their animations' keys with the events by these numbers)
POSE_EVENT = re.compile(r'^Play_([A-Za-z0-9]+)_(sta|win)_(\d+)$')


def pose_move(event):
    """The intro or win move ('zbr_s00', 'zbr_w01') whose line an event plays ('Play_zbr_sta_00', 'Play_zbr_win_01'),
    or None."""
    m = POSE_EVENT.match(event)
    if m is None:
        return None
    return '%s_%s%02d' % (m.group(1).lower(), 's' if m.group(2) == 'sta' else 'w', int(m.group(3)))
