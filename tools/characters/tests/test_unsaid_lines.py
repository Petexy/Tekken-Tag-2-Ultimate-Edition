"""A fighter with no line of a kind (Tekken 8's Azazel: no intro line, win quote or name call) never speaks with the
donor's voice: the donor's tones of that kind play silence (convert/voice.py), and the donor's intros and win poses it
plays leave the donor's lines and their subtitles out, its intros saying what its own intro says
(convert/moveset.py), on made-up banks and tables (no game files needed).

    python3 -m unittest discover tools/characters/tests
"""
import io
import os
import sys
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from test_tekken8_import_moveset import nus3                  # noqa: E402
from ttt2char.convert import moveset, voice                    # noqa: E402
from ttt2char.tekken8 import voice as voice8                   # noqa: E402
from ttt2char.ttt2 import nus3bank                             # noqa: E402


def samples(audio):
    """A tone's audio (a WAVE) as int16 samples."""
    with wave.open(io.BytesIO(audio)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), '<i2')


class SilentTones(unittest.TestCase):
    """The donor's intro lines (rm_Dst) with and without intro clips of the fighter's."""

    LINE = np.full((1, 480), 3000, np.int16)

    def build(self, kinds, which='rm_Dst', tones=(('la_s_t2_1p', b'L' * 16, None), ('dummy2', b'', None))):
        clips = voice8.Clips.__new__(voice8.Clips)
        clips.kinds = kinds
        written, used, placed, _ = voice._build_one(which, nus3(list(tones)), clips, 'aza', 24000, {})
        return nus3bank.Bank(written), used, placed

    def test_no_intro_line_is_silence(self):
        b, used, placed = self.build({('atk', 's'): [('Play_GOT_Attack_S_001', 24000, self.LINE)]})
        self.assertFalse(samples(b.audio[0]).any())             # (silence, not the donor's audio)
        self.assertEqual(len(samples(b.audio[0])), 5)            # (as long as the donor's line: 10 at 48 kHz)
        self.assertEqual(used, ['la_s_t2_1p<-' + voice.SILENCE])
        self.assertEqual(placed, {})
        self.assertEqual(b.audio[1], b'')                       # (an empty tone stays empty)

    def test_own_intro_line(self):
        b, used, _ = self.build({('intro', None): [('Play_zbr_sta_00', 24000, self.LINE)]})
        self.assertTrue((samples(b.audio[0]) == 3000).all())
        self.assertEqual(used, ['la_s_t2_1p<-Play_zbr_sta_00'])

    def test_unsaid(self):
        clips = voice8.Clips.__new__(voice8.Clips)
        clips.kinds = {('atk', 's'): [('Play_GOT_Attack_S_001', 24000, self.LINE)]}
        self.assertEqual(voice.unsaid(clips), {'intro', 'win'})
        clips.kinds[('win', None)] = [('Play_zbr_win_00', 24000, self.LINE)]
        self.assertEqual(voice.unsaid(clips), {'intro'})

    def test_name_call_link(self):
        # the announcer's call of the donor's name (a link tone and its two audio tones) is silent too
        b, used, _ = self.build({('atk', 's'): [('Play_GOT_Attack_S_001', 24000, self.LINE)]}, 'se_Chr',
                                (('lnk_syvo_name_lar', b'N' * 16, None), ('lnk_syvo_name_lar_Copy', b'N' * 16, None),
                                 ('syvo_name_lar', None, [0, 1]), ('lar_item00', b'I' * 16, None)))
        self.assertFalse(samples(b.audio[0]).any() or samples(b.audio[1]).any())
        self.assertEqual(b.audio[3], b'I' * 16)                 # (a tone of no kind: as it was)
        self.assertEqual(sorted(used), ['lnk_syvo_name_lar<-' + voice.SILENCE,
                                        'lnk_syvo_name_lar_Copy<-' + voice.SILENCE])


class PoseLines(unittest.TestCase):
    """The donor's pose parts' property lists: the donor's lines left out, the fighter's own intro voice at its frames."""

    END = dict(frame=0, id=0, value=0)

    def converter(self):
        c = moveset.Converter.__new__(moveset.Converter)
        P = [dict(frame=0x8001, id=0x82e5, value=0x400a), dict(frame=0x8001, id=0x8300, value=0x0D000000),
             dict(frame=151, id=0x8057, value=0), self.END,
             # the fighter's own intro move (Tekken 8's, converted): a special shout at 40, a damage voice at 8,
             # an item sound and a laser at 42
             dict(frame=40, id=0x82f9, value=0x0200000B), dict(frame=8, id=0x82f9, value=0x03000007),
             dict(frame=42, id=0x82f9, value=0x0C00100B), dict(frame=42, id=0x8145, value=0), self.END,
             # a win pose: its quote (a se_Dwi tone), its streamed quote, a shout of the fighter's
             dict(frame=0x8001, id=0x82f9, value=0x0E003005), dict(frame=0x8001, id=0x8300, value=0x0D001000),
             dict(frame=10, id=0x82fa, value=0x0200000C), self.END]
        c.T = {'extra_move_properties': P, 'moves': [dict(extraprops=0), dict(extraprops=4), dict(extraprops=9)]}
        c.newidx = {77: 1}
        import collections
        c.stats = collections.Counter()
        return c

    def rows(self, c, start):
        P, out = c.T['extra_move_properties'], []
        while start is not None and P[start] != self.END:
            out.append((P[start]['frame'], P[start]['id'], P[start]['value']))
            start += 1
        return out

    def test_own_voices(self):
        c = self.converter()
        self.assertEqual([(r['frame'], r['value']) for r in c.own_voices(77)], [(40, 0x0200000B), (8, 0x03000007)])
        self.assertEqual(c.own_voices(78), [])

    def test_intro(self):
        c = self.converter()
        start = c.unsaid_lines(0, c.own_voices(77))
        self.assertEqual(self.rows(c, start), [(0x8001, 0x82e5, 0x400a), (8, 0x82f9, 0x03000007),
                                               (40, 0x82f9, 0x0200000B), (151, 0x8057, 0)])

    def test_own_intro_voices(self):
        # (after the links: the intro part, already without the donor's line, gets its own move's voice)
        c = self.converter()
        c.T['moves'][0]['extraprops'] = c.unsaid_lines(0, [])
        c.intro_voices = {0: 77}
        c.own_intro_voices()
        self.assertEqual(self.rows(c, c.T['moves'][0]['extraprops']),
                         [(0x8001, 0x82e5, 0x400a), (8, 0x82f9, 0x03000007), (40, 0x82f9, 0x0200000B),
                          (151, 0x8057, 0)])

    def test_win(self):
        c = self.converter()
        start = c.unsaid_lines(9, [])
        self.assertEqual(self.rows(c, start), [(10, 0x82fa, 0x0200000C)])      # (his own shout stays)

    def test_nothing_to_leave_out(self):
        c = self.converter()
        self.assertEqual(c.unsaid_lines(4, []), 4)
        self.assertEqual(c.unsaid_lines(None, []), None)

    def test_pose_kind(self):
        self.assertEqual([moveset.POSE_KIND.match(n).group(1) for n in ('la_srm', 'la_slm_solo', 'la_wnm_1', 'ju_wem_1')],
                         ['s', 's', 'w', 'w'])



class FakeDonor:
    """A donor moveset of named moves with no cancels (pose_sequence: one part a pose)."""

    def __init__(self, names):
        self.names = names
        self.tables = {'moves': [dict(cancel=None, anim=0, extraprops=None) for _ in names]}

    def move_name(self, j):
        return self.names[j]

    def anim_name(self, j):
        return self.names[j] + '(DVD)'


class PoseSubtitles(unittest.TestCase):
    """The donor's subtitle (0x8180 in a move's begin properties: Lars's first intro line is 0x2600) is
    left out of the donor's poses of a kind the fighter has no line of, and only of those."""

    END = dict(req=0, id=moveset.TT_END, value=0)
    NAMES = ['la_srm', 'la_wnm_1', 'mk_srm']

    def converter(self, unsaid):
        c = moveset.Converter.__new__(moveset.Converter)
        B = [self.END, dict(req=0, id=moveset.SUBTITLE_PROP, value=0x2600), self.END,
             dict(req=0, id=moveset.SUBTITLE_PROP, value=0x260A), dict(req=0, id=0x8057, value=1), self.END]
        c.d = FakeDonor(self.NAMES)
        c.T = {'move_begin_props': B, 'extra_move_properties': [dict(frame=0, id=0, value=0)],
               'moves': [dict(begin_props=1, extraprops=None, anim=0, anim_name=0),
                         dict(begin_props=3, extraprops=None, anim=0, anim_name=0),
                         dict(begin_props=0, extraprops=None, anim=0, anim_name=0)]}
        import collections
        c.stats = collections.Counter()
        c.unsaid, c.posed, c.posed_hands, c.intro_voices, c.shown = frozenset(unsaid), set(), {}, {}, False
        c.move_anim = lambda t7: 0
        c.string = lambda name: 0
        c.k = FakeDonor(['own_intro'])
        c.summon_rows = lambda rows, t7: []
        return c

    def begin(self, c, j):
        B, out, at = c.T['move_begin_props'], [], c.T['moves'][j]['begin_props']
        while at is not None and B[at]['id'] != moveset.TT_END:
            out.append((B[at]['id'], B[at]['value']))
            at += 1
        return out

    def test_no_lines(self):
        c = self.converter({'intro', 'win'})
        for j in range(3):
            c.pose_sequence(j, 0)
        self.assertEqual(self.begin(c, 0), [])                          # (Azazel's intro: no Lars subtitle)
        self.assertEqual(self.begin(c, 1), [(0x8057, 1)])               # (a win pose keeps its other properties)
        self.assertEqual(self.begin(c, 2), [])
        self.assertEqual(c.T['move_begin_props'][:6], self.converter(()).T['move_begin_props'])  # (the donor's lists)

    def test_own_intro_line(self):
        # a fighter with intro lines but no win quote: its intros keep the subtitle property, its win poses lose it
        c = self.converter({'win'})
        for j in range(2):
            c.pose_sequence(j, 0)
        self.assertEqual(self.begin(c, 0), [(moveset.SUBTITLE_PROP, 0x2600)])
        self.assertEqual(self.begin(c, 1), [(0x8057, 1)])

    def test_every_line(self):
        c = self.converter(())
        for j in range(3):
            c.pose_sequence(j, 0)
        self.assertEqual([c.T['moves'][j]['begin_props'] for j in range(3)], [1, 3, 0])
        self.assertEqual(len(c.T['move_begin_props']), 6)

    def test_nothing_left(self):
        c = self.converter(())
        self.assertIsNone(c.unsaid_subtitles(1))
        self.assertEqual(c.unsaid_subtitles(0), 0)
        self.assertIsNone(c.unsaid_subtitles(None))


if __name__ == '__main__':
    unittest.main()
