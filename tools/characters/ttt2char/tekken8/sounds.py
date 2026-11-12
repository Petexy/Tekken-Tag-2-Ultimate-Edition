"""A Tekken 8 fighter's sound effects (its weapons', special moves' and hits' sounds) -> tones of its se_Chr bank that
its moves play as item sounds (the way of convert/sounds.py for Tekken 7; convert/voice.py append_effects).

Tekken 8's moves play them with the sound properties (tekken8/voice.py SOUND_PROPERTIES: the bank in `value`, n in
`value3`) of bank 15 (TABLE_BANK): n is a SoundID in the SoundDataBattleSysTone of a sound data asset, the fighter's own
(SDA_BankChara<CODE>: its Play_SE_<CODE>_* events, Victor's 3200 Play_SE_LON_Gun_Shot) or the common one
(SDA_BankBattleCom: Play_SE_Swish_Homing, Play_SE_Pcrash_Invoke, ...). A property row at its frame plays a swing's or a
shot's sound whatever happens; a hit's sound is an action in a requirement list of the move's cancel rows, after the
test that the move hit (`[(44), (0x8002), (0x87f0, 15, 3204)]`: his Gun_Hit), so both whiffs and hits come out right by
converting the rows. The row is the player's (0x87f0), or the opponent's (0x87f2) for a sound placed at the opponent's
body, still from the attacker's data: TTT2's opponent sound would look it up in the opponent's item sounds, so it
becomes the player's (Converter.own_effect).

The sounds taken are those of the moves the importer converts: reached as tekken8/voice.py's walk finds them (no story
scene) and not left out by the definition's drop_moves. Left out:
    Play_SE_<CODE>_Rage_*           Rage Arts' (as their lines: tekken8/voice.py UNSAID)
    TITLE_HAS                       the common sounds of what TTT2 sounds or has not by itself: its own wall hits,
                                    Tekken 8's tornado and its recoverable health's
    bank 12 (its SoundDataItemTone) the customisation items' moves: an added fighter wears none of them
An event is one sound or a layer or random container (tekken8/wwise.py Bank.event_tree); it becomes one mono clip: a
layer's sounds mixed, of a random container's the loudest. Wwise's per-sound values are applied: volume and make-up gain
(dB), pitch (cents), initial delay. Its low and high pass filters are not.

Levels: TTT2 and Tekken 8 share recordings of their generic hit sounds, and the sample levels agree within 0..3 dB when
Tekken 8's volume is added (RES_BANK_PCH_LT02 identical, 0 dB; FX_HIT_* identical, +3 dB; RES_BANK_DWN_HVY01 identical,
0 dB). TTT2's mix plays those generic tones at about -10.5 dB (measured in its output), its effect tones at -6 dB
(convert/voice.py EFFECT_VOLUME), and its own item tones sit about 6 dB below Tekken 8's effects (loudest 100 ms
-12..-14 dBFS, theirs -5..-9): a clip keeps its Tekken 8 sample level with volume added, less LEVEL dB, which puts both
the balance with the generic hits and the level of TTT2's own item sounds about right, and is scaled down only as far
as it would otherwise pass PEAK (many effects are normalised and carry +3..+12 dB in Wwise, more than 16-bit samples
hold).

Written for this project from the files themselves (no third-party code).
"""
import re

import numpy as np

from .. import InputError
from ..convert.sounds import ITEM_SOUND, OWN_LIST
from ..convert.voice import EFFECT_RATE
from . import uprops, voice, wwise, zen

TABLE_BANK = 15
COMMON_DATA = 'Polaris/Content/Sound/BattleCom/SDA_BankBattleCom'
TITLE_HAS = re.compile(r'^Play_SE_(Wall_Hit|Air_Tornado_EFX|HP_Recover|Heat_Timer_Recover)', re.I)
RAGE_ART = r'^Play_SE_%s_Rage_'
PEAK = 0.97                 # of full scale
LEVEL = 6.0                 # dB below Tekken 8's level (see above)
TAIL = 0.05                 # seconds kept after a clip's last sound
SILENT = 16                 # samples no louder than this are silence (of 32767)


def _tones(store, path, skipped):
    """{SoundID: event name} of a sound data asset's SoundDataBattleSysTone (a later row of an id wins: the assets list
    some ids twice, first without an event); {} (noted in `skipped`) when the installation has none it can read."""
    try:
        pkg = store.package(path)
        props, _ = uprops.read(pkg, pkg.main_export())
    except (KeyError, ValueError, OSError, zen.ParseError) as error:
        skipped.append((path, str(error) or 'not read'))
        return {}
    out = {}
    for tone in props.get('SoundDataBattleSysTone') or []:
        if tone.get('SoundID') is not None and tone.get('AudioEvent'):
            out[tone['SoundID']] = tone['AudioEvent'].rsplit('.', 1)[-1]
    return out


STOP_EVENT = 'Stop_'                # an event that plays nothing


def table(store, code, skipped=None):
    """Bank 15's sounds as the fighter hears them: {n: event name}; the fighter's own first."""
    skipped = [] if skipped is None else skipped
    return {**_tones(store, COMMON_DATA, skipped),
            **_tones(store, voice.SOUND_DATA % (code.upper(), code.upper()), skipped)}


def move_sounds(k, kept=lambda i: True):
    """The bank 15 sounds [n] the kept moves of Tekken 8 moveset k play (reached by voice.reached; kept(move index)), in
    order, each once: their property lists' and the requirement lists' of their cancel rows and groups."""
    from ..convert import idmaps as M
    out = []
    for i in voice.reached(k):
        if not kept(i):
            continue
        mv = k.tables['moves'][i]
        rows = [(x['id'], x['value'], x.get('value3', 0)) for x in voice.property_rows(k, mv)]
        lists = [c['req'] for c in M.cancels(k, mv.get('cancel'))]
        for c in M.cancels(k, mv.get('cancel')):
            if c['direction'] == M.GROUP:
                lists += [g['req'] for g in M.cancels(k, c['move_id'], 'group_cancels', M.GROUP_END)]
        for r in lists:
            if r is not None:
                rows += [(q['condition'], q['param'], q.get('param3', 0)) for _, q in
                         k.iter_list('requirements', r, lambda q: q['condition'] == voice.LIST_END)]
        for pid, bank, n in rows:
            if pid in voice.SOUND_PROPERTIES and bank & 0xFF == TABLE_BANK and n not in out:
                out.append(n)
    return out


def _resampled(x, rate):
    """float samples at `rate` -> at EFFECT_RATE, band-limited (their top is what a swing's or a shot's sound has most
    of: plain interpolation folds it down)."""
    n = int(round(len(x) * EFFECT_RATE / rate))
    if n == len(x) or not n:
        return x
    pad = 256                               # (the transform is circular: no wrap of the ends)
    f = np.fft.rfft(np.concatenate((x, np.zeros(pad))))
    m = int(round((len(x) + pad) * EFFECT_RATE / rate))
    size = m // 2 + 1
    g = np.zeros(size, dtype=complex)
    k = min(size, len(f))
    g[:k] = f[:k]
    if k > 16:
        g[k - k // 16:k] *= np.linspace(1, 0, k // 16)
    return np.fft.irfft(g, m)[:n] * (m / (len(x) + pad))


def _loudness(x):
    """The loudest 100 ms' mean square."""
    n = min(len(x), EFFECT_RATE // 10)
    if not n:
        return 0.0
    c = np.cumsum(np.concatenate(((0.0,), x * x)))
    return float((c[n:] - c[:-n]).max() / n)


def _render(events, bank, node):
    """A node of Bank.event_tree -> mono float samples at EFFECT_RATE."""
    if node[0] == 'sound':
        _, oid, gain, pitch, delay = node
        rate, audio = wwise.decode_wem(events.wem(bank.sound(oid)[2]))
        x = _resampled(audio.astype(np.float64).mean(0), rate * 2 ** (pitch / 1200.0))
        return np.concatenate((np.zeros(int(round(delay * EFFECT_RATE))), x * 10 ** (gain / 20.0)))
    parts = [_render(events, bank, n) for n in node[1]]
    if not parts:
        return np.zeros(0)
    if node[0] == 'one':
        return max(parts, key=_loudness)
    out = np.zeros(max(len(p) for p in parts))
    for p in parts:
        out[:len(p)] += p
    return out


def clip(events, name):
    """Event `name` -> (name, EFFECT_RATE, int16 [1, samples]); KeyError or ValueError when it has no sound it can read."""
    bank = events.bank(name)
    x = _render(events, bank, bank.event_tree(name)) * 10 ** (-LEVEL / 20.0)
    if not len(x):
        raise KeyError('no sound')
    peak = np.abs(x).max()
    if peak > PEAK * 32767:
        x = x * (PEAK * 32767 / peak)
    loud = np.nonzero(np.abs(x) > SILENT)[0]
    x = x[:loud[-1] + 1 + int(TAIL * EFFECT_RATE)] if len(loud) else x[:1]
    return name, EFFECT_RATE, np.round(x).astype(np.int16)[None]


class Effects:
    """The fighter's sound effects its moves play: names in order, clips (event name, rate, int16 [channels, samples])
    and their TTT2 values (the interface of convert/sounds.Effects). k: its moveset; kept(move index): the importer
    converts it."""

    def __init__(self, store, code, k, kept=lambda i: True):
        self.skipped = []                  # (event or asset, why) of what could not be read
        self.left_out = []                 # (event, why) of sounds found and not taken (the rules above)
        self.table = table(store, code, self.skipped)
        rage = re.compile(RAGE_ART % re.escape(code), re.I)
        events = wwise.Events(store)
        self.names, self.clips = [], []
        for n in move_sounds(k, kept):
            name = self.table.get(n)
            if name is None:               # (a story scene's or another fighter's id: no sound of this fighter's)
                self.left_out.append((n, 'not in its sound data'))
            elif rage.match(name):
                self.left_out.append((name, 'a Rage Art\'s'))
            elif TITLE_HAS.match(name):
                self.left_out.append((name, 'the title has its own'))
            elif name.startswith(STOP_EVENT):      # (no sound: it ends a loop; TTT2's clips end by themselves)
                self.left_out.append((name, 'it only stops a sound'))
            elif name not in self.names:
                try:
                    self.clips.append(clip(events, events.name(name) or name))
                except (KeyError, ValueError) as error:
                    self.skipped.append((name, str(error)))
                    continue
                self.names.append(name)
        self.base = 0                      # the donor's item sounds' count (the importer's)

    def value(self, name):
        """A sound effect's TTT2 sound value, or None (not one of the fighter's)."""
        if name not in self.names:
            return None
        return ITEM_SOUND << 24 | OWN_LIST << 12 | (self.base + self.names.index(name))

    def move_value(self, v):
        """A move's Tekken 8 sound value (bank << 24 | n) -> its TTT2 one, or None."""
        return self.value(self.table.get(v & 0xFFFFFF)) if v >> 24 == TABLE_BANK else None

    def hit_value(self, missile):
        """(Tekken 7's missiles: Tekken 8 has no such sound.)"""
        return None
