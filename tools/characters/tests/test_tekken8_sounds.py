"""A Tekken 8 fighter's sound effects (tekken8/sounds.py, tekken8/wwise.py's parameters and event_tree, the converter's
rows), on made-up banks, media and moves (no game files needed).

    python3 -m pytest -q tools/characters/tests/test_tekken8_sounds.py
"""
import collections
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_tekken8_voice as tv                                 # noqa: E402
from test_tekken8_convert import END8, Source8, converted, converter    # noqa: E402
from ttt2char.convert import idmaps as M, voice as convert_voice      # noqa: E402
from ttt2char.tekken8 import sounds, voice, wwise               # noqa: E402
from ttt2char.ttt2 import dsp, nus3bank                          # noqa: E402

HIT = 44
PARENT = 0x700


def params(*pairs):
    """Node parameters: no effects, no bus, the bank's actor-mixer as the parent, the properties (id, value)."""
    ids = bytes(p[0] for p in pairs)
    return bytes(5) + struct.pack('<II', 0, PARENT) + b'\x00' + bytes((len(pairs),)) + ids + \
        b''.join(struct.pack('<f', p[1]) for p in pairs) + b'\x00'


def sound(media, *pairs):
    return struct.pack('<IBIIB', wwise.PCM_PLUGIN, 0, media, 0, 0) + params(*pairs)


def container(children, *pairs):
    return params(*pairs) + struct.pack('<I', len(children)) + b''.join(struct.pack('<I', c) for c in children)


def effect_bank(name, objects, target):
    objects = objects + [(7, PARENT, bytes(16)), (3, 0x600, tv.action(target)), (4, wwise.fnv(name), tv.event([0x600]))]
    return tv.bank(name, objects)


class Events:
    """Banks and media in memory (the interface of wwise.Events)."""

    def __init__(self, banks, media):
        self.banks, self.media_ = banks, media

    def bank(self, name):
        return wwise.Bank(self.banks[name])

    def wem(self, media):
        return self.media_[media]


def wave_of(value, n=3200, rate=32000):
    return tv.wem(np.full((1, n), value, np.int16), rate)


class Tree(unittest.TestCase):
    def test_parameters(self):
        # volume, make-up, pitch and delay of a sound, after its source and the node's effects, bus and parent
        b = wwise.Bank(effect_bank('E', [(2, 0x100, sound(5, (wwise.VOLUME, -4.0), (wwise.PITCH, 200.0)))], 0x100))
        self.assertEqual(b.parameters(0x100), {wwise.VOLUME: -4.0, wwise.PITCH: 200.0})
        # a layout not understood: nothing rather than noise (the parent read is no object of the bank)
        plain = wwise.Bank(tv.simple_bank('F', [5]))
        self.assertEqual(plain.parameters(0x100), {})

    def test_tree_adds_up(self):
        a, b_, c, d, e = 0x11110100, 0x11110101, 0x11110102, 0x11110200, 0x11110300     # (ids look like hashes)
        objects = [(2, a, sound(5, (wwise.VOLUME, -4.0))), (2, b_, sound(6, (wwise.DELAY, 0.25))),
                   (2, c, sound(7, (wwise.MAKEUP, 2.0))),
                   (5, d, container([b_, c], (wwise.VOLUME, 1.0))),
                   (9, e, container([a, d], (wwise.VOLUME, 3.0), (wwise.PITCH, -100.0)))]
        b = wwise.Bank(effect_bank('E', objects, e))
        self.assertEqual(b.event_tree('E'), ('all', [('all', [
            ('sound', a, -1.0, -100.0, 0.0),
            ('one', [('sound', b_, 4.0, -100.0, 0.25), ('sound', c, 6.0, -100.0, 0.0)])])]))


class Clip(unittest.TestCase):
    def clip(self, objects, target, media):
        return sounds.clip(Events({'E': effect_bank('E', objects, target)}, media), 'E')

    def test_volume(self):
        name, rate, a = self.clip([(2, 0x100, sound(5, (wwise.VOLUME, -6.0)))], 0x100, {5: wave_of(10000)})
        self.assertEqual((name, rate, a.shape[0]), ('E', convert_voice.EFFECT_RATE, 1))
        self.assertAlmostEqual(a[0, 1000] / 10000.0, 10 ** ((-6.0 - sounds.LEVEL) / 20), 2)

    def test_too_loud_is_scaled_not_clipped(self):
        # +12 dB of a normalised sound does not fit 16 bits
        _, _, a = self.clip([(2, 0x100, sound(5, (wwise.VOLUME, 12.0)))], 0x100, {5: wave_of(30000)})
        self.assertLessEqual(np.abs(a).max(), 32767 * sounds.PEAK + 1)
        self.assertGreater(np.abs(a).max(), 32767 * sounds.PEAK * 0.98)

    def test_layer_mixes_and_delays(self):
        objects = [(2, 0x100, sound(5)), (2, 0x101, sound(6, (wwise.DELAY, 0.05))),
                   (9, 0x300, container([0x100, 0x101]))]
        _, _, a = self.clip(objects, 0x300, {5: wave_of(1000), 6: wave_of(2000)})
        gain = 10 ** (-sounds.LEVEL / 20)
        self.assertAlmostEqual(a[0, 800] / 1000.0, gain, 1)                  # the first alone
        self.assertAlmostEqual(a[0, 2000] / 3000.0, gain, 1)                 # both
        self.assertEqual(a.shape[1], 1600 + 3200)

    def test_random_takes_the_loudest(self):
        objects = [(2, 0x100, sound(5)), (2, 0x101, sound(6)), (5, 0x300, container([0x100, 0x101]))]
        _, _, a = self.clip(objects, 0x300, {5: wave_of(500), 6: wave_of(4000)})
        self.assertAlmostEqual(a[0, 1000] / 4000.0, 10 ** (-sounds.LEVEL / 20), 1)

    def test_rate_and_pitch(self):
        # 48 kHz to the effects' rate; an octave up is half as long
        _, _, a = self.clip([(2, 0x100, sound(5))], 0x100, {5: wave_of(1000, 4800, 48000)})
        self.assertEqual(a.shape[1], 3200)
        _, _, b = self.clip([(2, 0x100, sound(5, (wwise.PITCH, 1200.0)))], 0x100, {5: wave_of(1000, 3200)})
        self.assertEqual(b.shape[1], 1600)

    def test_silent_tail_cut(self):
        w = np.zeros((1, 32000), np.int16)
        w[0, :1000] = 9000
        _, _, a = self.clip([(2, 0x100, sound(5))], 0x100, {5: tv.wem(w, 32000)})
        self.assertEqual(a.shape[1], 1000 + int(sounds.TAIL * 32000))


def moveset():
    """Alias slot 0: a round start (a story scene's sound 900); slot 1: a stance whose cancel starts an attack: a swing
    at frame 5 (100), a hit's sound in its first cancel row (101, at the opponent's body 102), a group's row (103), which
    ends in a dropped move (104); a voice (bank 16) and a generic sound (bank 7) that are no effects."""
    k = Source8(refs=[(0, 'own')] * 5)
    always = k.req((0, 0))
    hit = k.req((HIT, 0))
    start = len(k.tables['requirements'])
    k.tables['requirements'] += [dict(condition=c, param=p, param2=0, param3=p3, param4=0) for c, p, p3 in
                                 ((HIT, 0, 0), (0x87f0, 15, 101), (0x87f2, 15, 102), (END8, 0, 0))]
    group = len(k.tables['requirements'])
    k.tables['requirements'] += [dict(condition=c, param=p, param2=0, param3=p3, param4=0) for c, p, p3 in
                                 ((0x87f0, 15, 103), (END8, 0, 0))]
    story = k.props((5, 0x87f0, 15, always, 900))
    attack = k.props((5, 0x87f0, 15, always, 100), (6, 0x87f0, 16, always, 500), (7, 0x87f0, 7, always, 16))
    last = k.props((5, 0x87f0, 15, always, 104))
    k.tables['group_cancels'] = k.tables.get('group_cancels', []) + [
        dict(direction=0x20, button=1, req=group, move_id=4), dict(direction=M.GROUP_END, button=0, req=None, move_id=0)]
    k.tables['cancels'] += [dict(direction=0x20, button=1, req=always, move_id=2),
                            dict(direction=M.LIST_END, button=0, req=None, move_id=0),
                            dict(direction=0, button=0, req=start, move_id=3),
                            dict(direction=M.GROUP, button=0, req=always, move_id=0),
                            dict(direction=M.LIST_END, button=0, req=None, move_id=0)]
    moves = ((story, None, 0), (None, 0, 1), (attack, 2, 3), (None, None, 1), (last, None, 1))
    for i, (xp, cancel, transition) in enumerate(moves):
        k.tables['moves'][i].update(extraprops=xp, begin_props=None, end_props=None, cancel=cancel,
                                    transition=transition, hit_condition=None)
    k.aliases = [0] + [1] * 55
    return k


class Selection(unittest.TestCase):
    def test_moves_sounds(self):
        k = moveset()
        self.assertEqual(sounds.move_sounds(k), [100, 101, 102, 103, 104])    # (not the round start's, 900)
        self.assertEqual(sounds.move_sounds(k, lambda i: i != 4), [100, 101, 102, 103])

    def effects(self, table, k=None):
        e = sounds.Effects.__new__(sounds.Effects)
        e.table, e.names, e.base = table, [n for n in table.values() if n], 6
        return e

    def test_values(self):
        e = self.effects({100: 'Play_SE_TST_Gun', 3: 'Play_SE_Swish_Homing'})
        self.assertEqual(e.move_value(15 << 24 | 100), 12 << 24 | 1 << 12 | 6)
        self.assertEqual(e.move_value(15 << 24 | 3), 12 << 24 | 1 << 12 | 7)
        self.assertIsNone(e.move_value(15 << 24 | 4))                          # not its own
        self.assertIsNone(e.move_value(7 << 24 | 100))                         # a generic sound's
        self.assertIsNone(e.hit_value(1))

    def test_rules(self):
        self.assertTrue(sounds.TITLE_HAS.match('Play_SE_Wall_Hit'))
        self.assertTrue(sounds.TITLE_HAS.match('Play_SE_HP_Recover_Long'))
        self.assertFalse(sounds.TITLE_HAS.match('Play_SE_Swish_Homing'))


class Rows(unittest.TestCase):
    def setUp(self):
        self.k = Source8(refs=[(0, 'own')])
        self.c = converter(self.k, req={HIT: 46, 0: 0}, prop={0x87f0: 0x82f9, 0x87f2: 0x82fb, 0x8003: 0x8003})
        self.c.effects = sounds.Effects.__new__(sounds.Effects)
        self.c.effects.table = {100: 'A', 101: 'B'}
        self.c.effects.names, self.c.effects.base = ['A', 'B'], 6
        self.c.voices8, self.c.voice_turns = {}, collections.Counter()

    def req(self, *rows):
        start = len(self.k.tables['requirements'])
        for r in rows + ((END8, 0, 0, 0),):
            self.k.tables['requirements'].append(dict(condition=r[0], param=r[1], param2=r[2], param3=r[3], param4=0))
        return start

    def test_hit_sound_in_a_cancel_row(self):
        # the hit's own sound after its test; at the opponent's body it stays the player's list (TTT2's opponent sound
        # would look it up in the opponent's item sounds)
        start, ok = self.c.conv_reqs(self.req((HIT, 0, 0, 0), (0x87f0, 15, 0, 100), (0x87f2, 15, 0, 101)))
        self.assertTrue(ok)
        self.assertEqual(converted(self.c, start), [(46, 0), (0x82f9, 12 << 24 | 1 << 12 | 6),
                                                    (0x82f9, 12 << 24 | 1 << 12 | 7)])

    def test_others_of_bank_15_left_out(self):
        start, ok = self.c.conv_reqs(self.req((HIT, 0, 0, 0), (0x87f0, 15, 0, 999)))
        self.assertEqual(converted(self.c, start), [(46, 0)])

    def test_own_effect_only_for_effects(self):
        self.assertEqual(self.c.own_effect(0x87f2, 15 << 24 | 100), 0x87f0)
        self.assertEqual(self.c.own_effect(0x87f2, 7 << 24 | 16), 0x87f2)      # a generic sound stays the opponent's
        self.assertEqual(self.c.own_effect(0x87f0, 15 << 24 | 100), 0x87f0)


class EffectTones(unittest.TestCase):
    """Tekken 8's effects sound the same whoever the donor is; Tekken 7's stay copies of the donor's first item tone."""

    @staticmethod
    def bank():
        from test_tekken8_import_moveset import nus3
        idsp = dsp.idsp([np.full(3200, 1000, np.int16)], 32000)
        b = nus3bank.Bank(nus3([('sho_00', idsp, None), ('itm_x_03', idsp, None), ('itm_x_00', idsp, None)]))
        b.set_mix(1, 4.0, 0.0)
        b.set_mix(2, 3.0, -200.0)
        return b

    @staticmethod
    def mix(b, i):
        t = bytes(b.tones[i])
        o = nus3bank.Bank._fields(t)
        return struct.unpack_from('<f', t, o + 16)[0], struct.unpack_from('<f', t, o + 24)[0]

    def clips(self):
        return [('E', convert_voice.EFFECT_RATE, np.full((1, 1600), 500, np.int16))]

    def test_plain(self):
        b = self.bank()
        tones = convert_voice.append_effects(b, self.clips(), True)
        self.assertEqual(b.name(tones[0]), 'itm_x_A0')
        self.assertAlmostEqual(self.mix(b, tones[0])[0], convert_voice.EFFECT_VOLUME, 3)
        self.assertEqual(self.mix(b, tones[0])[1], 0.0)
        self.assertEqual(self.mix(b, 2), (3.0, -200.0))                     # (the donor's own tone is not touched)
        self.assertEqual(nus3bank.Bank(b.write()).format(tones[0])[0], convert_voice.EFFECT_RATE)

    def test_tekken7_keeps_the_copy(self):
        b = self.bank()
        tones = convert_voice.append_effects(b, self.clips())
        self.assertEqual(self.mix(b, tones[0]), (4.0, 0.0))                 # itm_x_03, the bank's first item tone


class VoiceUnchanged(unittest.TestCase):
    def test_reached_order(self):
        # played walks reached: the round start's left out, its order the reaching order
        k = moveset()
        self.assertEqual(list(voice.reached(k)), [1, 2, 3, 4])
        self.assertEqual(voice.played(k), [(16, 500)])


if __name__ == '__main__':
    unittest.main()
