"""A Tekken 7 fighter's sound effects (its special moves', weapon hits' and projectiles' sounds) -> tones of its se_Chr
bank that its moves play as item sounds.

Tekken 7 plays a move's sound effect with property 0x84c4 / 0x84c6 = bank << 24 | n (an extra property, or an action
in a cancel row's requirement list: a hit's sounds); bank 15 is the common sound manager's list of sounds
(BP_TekkenCommonSoundManager's BattleSysTones: n -> an AkAudioEvent, e.g. 57 mrx_hadou01_shot, Akuma's fireball, 71
SE_battle_spgauge_start, an EX move's start, 72 SE_battle_spcombo_start, a super's start, 404 se_mry_rep_shot,
Geese's Reppuken, 430 se_mrz_hit_sword, Noctis's sword hits). The events are in AkBankBattle.bnk or the fighter's own
AkBankVoice<CODE>.bnk (Geese's). A projectile's hit sound is its missile blueprint's (the events it names: the one
ending _hit or _hit_flame; _hit_ground is its hitting the floor, Guard01 a block), the missile being the projectile
row's field 2 (tekken7/particles.py missile_systems).

TTT2 plays a fighter's item sound n with 0x82f9 = 12 << 24 | 1 << 12 | n (type 12, kind 1: its own item sound list,
by its select id; kind 0 is a common list), and the runtime gives an added fighter the donor's list, then one sound
for each tone of character.ini's sound_extra. So each effect becomes a tone appended to the fighter's se_Chr bank
(convert/voice.py) and its moves' value 12 << 24 | 1 << 12 | (the donor's item sounds + its number).
"""
import re

from ..tekken7.uasset import load, read_properties
from ..tekken7.particles import export_properties, short_ref
from ..tekken7.wwise import Bank as WwiseBank, decode_wem

SOUND_MANAGER = '/Game/Sound/Common/BP_TekkenCommonSoundManager'
BATTLE_BANK = 'TekkenGame/Content/WwiseAudio/Windows/AkBankBattle.bnk'
VOICE_BANK = 'TekkenGame/Content/WwiseAudio/Windows/AkBankVoice%s.bnk'
TABLE_BANK = 15                       # Tekken 7's sound bank number of the BattleSysTones list
ITEM_SOUND = 12                       # TTT2's sound type of item sounds ...
OWN_LIST = 1                          # ... and their kind: the player's own list (by its select id)
ITEM_SOUNDS = 0x107D4044              # the title's item sound lists: 63 x {sound ids*, count}, by select id
CODES = 0x107C57F4                    # 63 x char*: each fighter's code, by select id
STORY = re.compile(r'_ch\d\d|^se_ch\d\d')   # story mode's sounds (its own moves): left out
# the moves whose sounds are left out: those the importer drops (Rage Arts, story moves, ...: moveset.DROP_MOVES)
LEFT_OUT = re.compile(r'RageArt|_7CS$|^Story|Chapter|^FACE|^b7_|^vra_|^SE_')


def event_name(ref):
    """An AkAudioEvent reference ("AkAudioEvent'/Game/Sound/Battle/mrx/X.X'") -> its event name X, or None."""
    m = re.search(r"([A-Za-z0-9_]+)'?$", ref or '')
    return m.group(1).split('.')[-1] if m else None


def table(paks):
    """Bank 15's sounds: [event name or None] by n."""
    package = load(paks, SOUND_MANAGER)
    defaults = package.find_export(name='Default__BP_TekkenCommonSoundManager_C')
    tones = read_properties(package.export_reader(defaults)).get('BattleSysTones') if defaults else None
    return [event_name(t) if t else None for t in tones or []]


def missile_hits(paks, code):
    """{missile number: the event its missile plays on a hit} of a fighter's character blueprint."""
    try:
        props = export_properties(load(paks, '/Game/Character/CharacterBlueprints/BP_Character_%s' % code.upper()))
    except KeyError:
        return {}
    out = {}
    for _, p in props:
        for info in (p or {}).get('MissileInfo') or []:
            cls = short_ref(info.get('MissileClass'))
            if not cls or info.get('EffectID') is None:
                continue
            try:
                package = load(paks, cls.split('.')[0])
            except KeyError:
                continue
            names = [imp.name for imp in package.imports if imp.class_name == 'AkAudioEvent']
            hit = next((n for n in names if re.search(r'_hit(_flame)?$', n, re.I)), None)
            if hit:
                out[int(info['EffectID'])] = hit
    return out


def item_count(rpx, donor):
    """The donor's item sounds' count (the title's list, by select id)."""
    codes = [rpx.read(rpx.u32(CODES + 4 * i), 4).split(b'\0')[0].decode('latin1') for i in range(63)]
    return rpx.u32(ITEM_SOUNDS + 8 * codes.index(donor) + 4)


def move_sounds(names, moveset, xps, kept=lambda name: True, actions=None):
    """The bank 15 sounds (names: table()'s) the kept moves of a Tekken 7 moveset play, in order: their properties'
    and, with actions(moveset, move) -> the (id, value) rows of the move's cancel rows' requirement lists, those
    lists' (a hit's sounds are there: Noctis's sword hits `[(44), (0x802e, 99), (0x84c4, 15 << 24 | 430)]`,
    se_mrz_hit_sword)."""
    out = []
    for i, mv in enumerate(moveset.tables['moves']):
        if not kept(moveset.move_name(i) or ''):
            continue
        rows = [(pid, v) for _, pid, v in xps(moveset, mv['extraprops'])]
        rows += list(actions(moveset, mv)) if actions else []
        out += [names[v & 0xFFFFFF] for pid, v in rows
                if pid in (0x84c4, 0x84c6) and v >> 24 == TABLE_BANK and (v & 0xFFFFFF) < len(names)]
    return out


class Effects:
    """The fighter's sound effects its moves (bank 15) and projectiles (their missiles' hits) play: names in order,
    clips (event name, rate, int16 [channels, samples]) and their values for moves (value())."""

    def __init__(self, paks, code, moveset, xps, kept=lambda name: True, extra=(), actions=None):
        """moveset: its tkmvst; xps(moveset, i) -> a move's (frame, id, value) properties; kept(move name): the
        importer converts the move (Rage Arts and story moves' sounds are left out); extra: sounds the fighter plays
        besides its moves' (its gauge's full sound, convert/gauge.py), after the others; actions (move_sounds)."""
        self.table = table(paks)
        banks = [WwiseBank(paks.read(VOICE_BANK % code.upper()))]
        try:
            banks.append(WwiseBank(paks.read(BATTLE_BANK)))
        except (KeyError, OSError, ValueError):
            pass
        wanted = move_sounds(self.table, moveset, xps, kept, actions)
        self.hits = missile_hits(paks, code)
        wanted += list(self.hits.values()) + list(extra)
        self.names, self.clips = [], []
        for name in wanted:
            if not name or name in self.names or STORY.search(name.lower()):
                continue
            for bank in banks:
                if bank.has_event(name):
                    media = bank.event_media(name)
                    if media:
                        rate, audio = decode_wem(bank.media[media[0]])
                        self.names.append(name)
                        self.clips.append((name, rate, audio))
                    break
        self.base = 0                  # the donor's item sounds' count (the importer's)

    def value(self, name):
        """A sound effect's TTT2 sound value, or None (not one of the fighter's)."""
        if name not in self.names:
            return None
        return ITEM_SOUND << 24 | OWN_LIST << 12 | (self.base + self.names.index(name))

    def number(self, name):
        """A sound effect's item sound number (its value's n), or None."""
        v = self.value(name)
        return None if v is None else v & 0xFFF

    def move_value(self, v):
        """A move's Tekken 7 sound value (bank << 24 | n) -> its TTT2 one, or None."""
        n = v & 0xFFFFFF
        return self.value(self.table[n]) if v >> 24 == TABLE_BANK and n < len(self.table) else None

    def hit_value(self, missile):
        """A projectile's hit sound (its missile's) -> its TTT2 sound value, or None."""
        return self.value(self.hits.get(missile))
