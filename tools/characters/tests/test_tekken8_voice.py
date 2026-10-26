"""Tekken 8's Wwise banks and media (tekken8/wwise.py) and a fighter's voice clips (tekken8/voice.py), on made-up
banks and media in a made-up installation's pak file (no game files needed).

    python3 -m unittest discover tools/characters/tests
"""
import os
import shutil
import struct
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import test_tekken8_synth as synth                    # noqa: E402
from test_tekken8_convert import Source8              # noqa: E402
from ttt2char import InputError                       # noqa: E402
from ttt2char.convert import idmaps as M, voice as convert_voice     # noqa: E402
from ttt2char.tekken8 import cityhash, store, voice, wwise, zen     # noqa: E402

NULL = synth.NULL
ACTOR_MIXER = 0x090251B4                    # a parent outside the bank (its id appears in the sounds' bodies)
BUS = 0x5C49D3C5


# ---------------------------------------------------------------------------------------------------- builders
def wem(samples, rate=48000, tag=0xFFFE):
    """A WEM: int16 [channels, n] as 16-bit PCM in Wwise's RIFF layout (fmt with its extension, hash, junk, data)."""
    a = np.asarray(samples, np.int16)
    channels = a.shape[0]
    fmt = struct.pack('<HHIIHH', tag, channels, rate, rate * 2 * channels, 2 * channels, 16)
    fmt += struct.pack('<HHI', 6, 16, 0x4101 if channels == 1 else 0x3)
    data = a.T.astype('<i2').tobytes()
    body = b'WAVE'
    for tag_, chunk in ((b'fmt ', fmt), (b'hash', bytes(16)), (b'junk', bytes(3)), (b'data', data)):
        body += tag_ + struct.pack('<I', len(chunk)) + chunk + bytes(len(chunk) & 1)
    return b'RIFF' + struct.pack('<I', len(body)) + body


def sound(media, size=0):
    """A sound object's body: PCM codec, stream type 0, media id and size, then node parameters naming a bus and
    the actor-mixer parent (ids of objects not in the bank)."""
    return (struct.pack('<IBIIB', wwise.PCM_PLUGIN, 0, media, size, 0) + bytes(5) + struct.pack('<II', BUS, ACTOR_MIXER)
            + b'\x00\x01\x00' + struct.pack('<f', -1.5) + bytes(8))


def layer(children):
    return bytes(9) + struct.pack('<f', 6.0) + bytes(6) + struct.pack('<I', len(children)) + \
        b''.join(struct.pack('<I', c) for c in children) + bytes(4)


def action(target, kind=0x0403):
    return struct.pack('<HI', kind, target) + b'\x00' + struct.pack('<II', 4, 0x1234)


def event(actions, u8=True):
    head = struct.pack('<B', len(actions)) if u8 else struct.pack('<I', len(actions))
    return head + b''.join(struct.pack('<I', a) for a in actions)


def bank(name, objects, version=145):
    """A one-event bank: BKHD (version, the event's id) and HIRC [(type, id, body)]."""
    bkhd = struct.pack('<II', version, wwise.fnv(name)) + bytes(16)
    hirc = struct.pack('<I', len(objects)) + b''.join(struct.pack('<BII', kind, len(body) + 4, oid) + body
                                                      for kind, oid, body in objects)
    return b'BKHD' + struct.pack('<I', len(bkhd)) + bkhd + b'HIRC' + struct.pack('<I', len(hirc)) + hirc


def simple_bank(name, media):
    """An event playing one sound of each medium in `media` (one Play action per sound)."""
    objects, actions = [], []
    for k, m in enumerate(media):
        sid, aid = 0x100 + k, 0x200 + k
        objects += [(2, sid, sound(m)), (3, aid, action(sid))]
        actions.append(aid)
    return bank(name, objects + [(4, wwise.fnv(name), event(actions))])


def layered_bank(name, media):
    """An event playing a layer container of the media's sounds (an intro or win line with its foley)."""
    sids = [0x300 + k for k in range(len(media))]
    objects = [(2, s, sound(m)) for s, m in zip(sids, media)]
    objects += [(7, ACTOR_MIXER, struct.pack('<I', 0x500)), (9, 0x400, layer(sids)), (3, 0x401, action(0x400)),
                (4, wwise.fnv(name), event([0x401]))]
    return bank(name, objects)


def tone(value, n=40, channels=1):
    return np.full((channels, n), value, np.int16)


# ---------------------------------------------------------------------------------------------------- tests
class Banks(unittest.TestCase):
    def test_fnv(self):
        self.assertEqual(wwise.fnv('Play_ZBR_Attack_S_001'), wwise.fnv('play_zbr_attack_s_001'))
        h = 2166136261
        for c in b'ab':
            h = ((h * 16777619) & 0xFFFFFFFF) ^ c
        self.assertEqual(wwise.fnv('AB'), h)

    def test_event_media(self):
        b = wwise.Bank(simple_bank('Play_A', [11, 12]))
        self.assertEqual((b.version, b.bank_id), (145, wwise.fnv('Play_A')))
        self.assertTrue(b.has_event('play_a'))
        self.assertFalse(b.has_event('Play_B'))
        self.assertEqual(b.event_media('Play_A'), [11, 12])
        self.assertEqual(b.sound(0x100)[:3], (wwise.PCM_PLUGIN, 0, 11))
        with self.assertRaises(KeyError):
            b.event_media('Play_B')

    def test_layer_container(self):
        # a layer container's children are found by id in its body; the bus and parent ids in the sounds are not
        # objects of the bank (the actor-mixer is, but it is no sound or container)
        self.assertEqual(wwise.Bank(layered_bank('Play_W', [21, 22])).event_media('Play_W'), [21, 22])

    def test_action_count_widths(self):
        # version 145 counts an event's actions in a u8, Tekken 7's 118 in a u32: the body's size tells
        objects = [(2, 1, sound(5)), (3, 2, action(1)), (3, 3, action(1, kind=0x0102))]      # 0x01xx: Stop
        for u8 in (True, False):
            b = wwise.Bank(bank('E', objects + [(4, wwise.fnv('E'), event([2, 3], u8))], 145 if u8 else 118))
            self.assertEqual(b.actions('E'), [2, 3])
            self.assertEqual(b.event_media('E'), [5])                  # (the Stop action plays nothing)
        bad = wwise.Bank(bank('E', [(4, wwise.fnv('E'), b'\x02\x00\x00')]))
        with self.assertRaises(ValueError):
            bad.actions('E')

    def test_not_a_bank(self):
        with self.assertRaises(ValueError):
            wwise.Bank(b'RIFF....')


class Media(unittest.TestCase):
    def test_decode(self):
        a = np.array([[1, -2, 30000, -32768, 5], [7, 8, -9, 10, 32767]], np.int16)
        rate, out = wwise.decode_wem(wem(a, 36000))
        self.assertEqual(rate, 36000)
        self.assertEqual(out.dtype, np.int16)
        np.testing.assert_array_equal(out, a)
        self.assertEqual(wwise.wem_format(wem(a[:1], 32000)), (0xFFFE, 1, 32000, 16))
        _, mono = wwise.decode_wem(wem(a[:1, :3], tag=1))              # plain WAVE_FORMAT_PCM too
        np.testing.assert_array_equal(mono, a[:1, :3])

    def test_refused(self):
        with self.assertRaises(ValueError):
            wwise.decode_wem(wem(tone(1), tag=0xFFFF))                 # Wwise Vorbis
        with self.assertRaises(ValueError):
            wwise.decode_wem(b'RIFX' + bytes(40))


class Clips(unittest.TestCase):
    """A made-up fighter 'tst' in a made-up installation: its events' banks and media in a pak file."""

    EVENTS = {                                                         # event: (media id, sample value)
        'Play_TST_Attack_S_002': (2, 102), 'Play_TST_Attack_S_001': (1, 101), 'Play_TST_Attack_S_010': (10, 110),
        'Play_TST_Attack_M_001': (31, 201), 'Play_TST_Attack_L_001': (41, 301), 'Play_TST_Attack_SP_001': (51, 401),
        'Play_TST_Damage_S_001': (61, 501), 'Play_TST_Damage_S_002': (62, 502), 'Play_TST_Damage_L_001': (71, 601),
        'Play_TST_Damage_KO_001': (81, 701), 'Play_TST_Damage_Stun_001': (91, 801),
        'Play_TST_Attack_Line_001': (92, 802), 'Play_tst_win_00_vr00': (93, 803), 'Play_syvo_name_TST': (94, 804),
        'Play_TST_Attack_M_002': (95, 805), 'Play_TSTX_Attack_S_001': (96, 806)}

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        game = os.path.join(cls.dir, 'TEKKEN 8')
        paks = os.path.join(game, 'Polaris', 'Content', 'Paks')
        os.makedirs(paks)
        engine = cityhash.script_object_id('/Script/Engine')
        synth.write_container(os.path.join(paks, 'global'), [
            (0, zen.CHUNK_SCRIPT_OBJECTS, 0, synth.script_objects([('/Script/Engine', engine, NULL)]))], [])
        files = {}
        for name, (media, value) in cls.EVENTS.items():
            files['Polaris/Content/WwiseAudio/Event/%s.bnk' % name] = simple_bank(name, [media])
            files['Polaris/Content/WwiseAudio/Media/%d.wem' % media] = wem(tone(value), 48000)
        # M_002's medium is not PCM (left out, noted); intros and wins: a stereo foley layered with the mono voice
        files['Polaris/Content/WwiseAudio/Media/95.wem'] = wem(tone(805), tag=0xFFFF)
        for name, (foley, line), value in (('Play_tst_sta_00', (111, 112), 901), ('Play_tst_win_00', (113, 114), 902),
                                           ('Play_tst_win_01', (115, 116), 903)):
            files['Polaris/Content/WwiseAudio/Event/%s.bnk' % name] = layered_bank(name, [foley, line])
            files['Polaris/Content/WwiseAudio/Media/%d.wem' % foley] = wem(tone(-1, 80, 2))
            files['Polaris/Content/WwiseAudio/Media/%d.wem' % line] = wem(tone(value, 60), 32000)
        # win_01's line padded with a second of silence on both sides (as Tekken 8 pads them to its scenes)
        files['Polaris/Content/WwiseAudio/Media/116.wem'] = wem(np.pad(tone(903, 60), ((0, 0), (32000, 32000))), 32000)
        # a shout's silence is left as it is
        files['Polaris/Content/WwiseAudio/Media/41.wem'] = wem(np.pad(tone(301), ((0, 0), (4800, 4800))), 48000)
        synth.write_pak(os.path.join(paks, 'pakchunk0-Windows.pak'), files)
        cls.store = store.Store(game)
        cls.clips = voice.Clips(cls.store, 'tst')

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        shutil.rmtree(cls.dir)

    def values(self, clips):
        return [int(a[0, np.flatnonzero(a[0])[0]]) for _, _, a in clips]

    def test_kinds(self):
        k = self.clips.kinds
        self.assertEqual(sorted(k), sorted([('atk', 's'), ('atk', 'm'), ('atk', 'l'), ('org', None), ('dmg', 's'),
                                            ('dmg', 'l'), ('ko', None), ('intro', None), ('win', None),
                                            ('name', None)]))
        self.assertEqual(self.values(k[('atk', 's')]), [101, 102, 110])          # in number order, gaps and all
        self.assertEqual([n for n, _, _ in k[('atk', 's')]], ['Play_TST_Attack_S_001', 'Play_TST_Attack_S_002',
                                                              'Play_TST_Attack_S_010'])
        self.assertEqual(self.values(k[('atk', 'm')]), [201])                    # M_002's codec: not read
        self.assertEqual(self.clips.skipped[0][0], 'Play_TST_Attack_M_002')
        self.assertEqual(self.values(k[('ko', None)]), [701])                    # (not a damage voice)
        self.assertEqual(self.values(k[('win', None)]), [902, 903])              # (not the variant _vr00)
        self.assertEqual(self.values(k[('name', None)]), [804])

    def test_layered_voice(self):
        # an intro's event plays a stereo foley and the mono voice line together: the clip is the voice line
        name, rate, a = self.clips.kinds[('intro', None)][0]
        self.assertEqual((name, rate, a.shape), ('Play_tst_sta_00', 32000, (1, 60)))
        self.assertEqual(int(a[0, 0]), 901)

    def test_trimmed_lines(self):
        # intro and win lines keep LINE_MARGINS of their silence (0.4 s before, 0.25 s after at 32 kHz); shouts all
        _, rate, a = self.clips.kinds[('win', None)][1]
        self.assertEqual(a.shape, (1, 12800 + 60 + 8000))
        self.assertEqual((int(a[0, 12799]), int(a[0, 12800]), int(a[0, 12859]), int(a[0, 12860])), (0, 903, 903, 0))
        self.assertEqual(self.clips.kinds[('atk', 'l')][0][2].shape, (1, 4800 + 40 + 4800))
        self.assertEqual(self.clips.kinds[('intro', None)][0][2].shape, (1, 60))       # nothing to cut
        quiet = np.zeros((2, 100), np.int16)
        self.assertIs(voice.trim(quiet, 32000), quiet)
        loud = np.zeros((2, 1000), np.int16)
        loud[1, 500] = voice.SILENT + 1                                 # either channel's sound counts
        np.testing.assert_array_equal(voice.trim(loud, 100, (0.02, 0.03)), loud[:, 498:504])

    def test_order_and_fallback(self):
        c = self.clips
        self.assertEqual(self.values(c.kiai()), [101, 102, 110, 201, 301, 401])      # short, medium, long, special
        self.assertEqual(self.values(c.damage('sml')), [501, 502, 601])
        counter = {}
        # no medium damage voice in Tekken 8: a medium one is a short one, in turn
        self.assertEqual([int(c.pick(('dmg', 'm'), counter)[2][0, 0]) for _ in range(3)], [501, 502, 501])
        self.assertEqual(int(c.pick(('win', None), counter)[2][0, 0]), 902)
        self.assertIsNone(c.pick(('nothing', None), {}))

    def test_no_voice(self):
        with self.assertRaises(InputError):
            voice.Clips(self.store, 'abc')

    def test_no_sound_data(self):
        # without its sound data asset the moves' voices are not known (no sound ids; noted)
        self.assertEqual(self.clips.sound_ids, {})
        self.assertIn(voice.SOUND_DATA % ('TST', 'TST'), [n for n, _ in self.clips.skipped])

    SOUND_IDS = {100: 'Play_TST_Attack_Line_001', 101: 'Play_TST_Attack_S_002', 102: 'Play_TST_Damage_Stun_001',
                 103: 'Play_TST_Other_001', 104: 'Play_TST_Attack_Line_009'}

    def moveset(self):
        """A Tekken 8 moveset: alias slot 0 its round-start move (its story scene's line, sound id 103), slot 1 its
        stance, whose cancel leads to an attack saying 100 and 101 (and a sound effect, bank 15), which goes on to a
        move playing a Stun voice (bank 17, kind 8), a Yell by a low chance (kind 10, 35 %) and a line against one
        fighter only (104)."""
        k = Source8(refs=[(0, 'own')] * 4)
        always, versus = k.req((0, 0)), k.req((505, 35))
        story = k.props((5, 0x87f0, 16, always, 103))
        attack = k.props((2, 0x87f0, 16, always, 100), (9, 0x87f0, 16, always, 101), (12, 0x87f0, 15, always, 4096))
        after = k.props((3, 0x87f0, 17, always, 8), (4, 0x87f0, 17, always, 10), (5, 0x87f0, 16, versus, 104))
        for row, chance in zip(k.tables['extra_move_properties'][after:], (100, 35)):
            row['value2'] = chance
        k.tables['cancels'] += [dict(direction=0x20, button=1, req=always, move_id=2),
                                dict(direction=M.LIST_END, button=0, req=None, move_id=0)]
        moves = ((story, None, 0), (None, 0, 1), (attack, None, 3), (after, None, 1))     # (props, cancel, transition)
        for i, (xp, cancel, transition) in enumerate(moves):
            k.tables['moves'][i].update(extraprops=xp, begin_props=None, end_props=None, cancel=cancel,
                                        transition=transition, hit_condition=None)
        k.aliases = [0] + [1] * 55
        return k

    def test_move_lines(self):
        # the voices the moves play by sound id: the lines of no kind (Attack_Line_001; the Stun voices bank 17
        # plays) become shouts after hers; the round-start move's story line and the line against one fighter not
        k = self.moveset()
        self.assertEqual(voice.played(k), [(16, 100), (16, 101), (17, 8)])
        c = voice.Clips(self.store, 'tst')
        c.sound_ids = dict(self.SOUND_IDS)
        c.add_lines(k)
        self.assertEqual([n for n, _, _ in c.kinds[voice.LINE]],
                         ['Play_TST_Attack_Line_001', 'Play_TST_Damage_Stun_001'])
        self.assertEqual(self.values(c.kiai()), [101, 102, 110, 201, 301, 401, 802, 801])
        # the banks' numbering (two shouts and three damage voices of the donor's): shout n is kiai's n-th, damage
        # voice n the n-th from the end of hers (long, short); a kind's voices, those of its clips
        vlist = [(0x21, 10), (0x21, 11), (0x44, 12), (0x48, 13), (0x48, 14), (0x90, 15)]
        values = convert_voice.voice_values(c, vlist)
        self.assertEqual(values['Play_TST_Attack_Line_001'], 0x02000006)
        self.assertEqual([values['Play_TST_Damage_%s' % n] for n in ('L_001', 'S_002', 'S_001')],
                         [0x03000000, 0x03000001, 0x03000002])
        voices = c.move_voices(values)
        self.assertEqual({key: voices[key] for key in voices if key[0] == 16},
                         {(16, 100): [0x02000006], (16, 101): [0x02000001], (16, 102): [0x02000007]})
        self.assertEqual(voices[(17, 0)], [0x02000000, 0x02000001, 0x02000002])        # the short shouts
        self.assertEqual(voices[(17, 3)], [0x03000002, 0x03000001])                    # the short damage voices
        self.assertEqual(voices[(17, 8)], [0x02000007])
        self.assertNotIn((17, 5), voices)                                              # (KO screams: no number)


if __name__ == '__main__':
    unittest.main()
