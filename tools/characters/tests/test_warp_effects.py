"""Unit tests of the warp effects' pieces (aimed effects, the weapons' particles, the warp streak's filaments) on made-up
data (no game files needed).

    python3 -m unittest discover tools/characters/tests
"""
import collections
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import moveset, particles as P            # noqa: E402
from ttt2char.tekken7.particles import Emitter, Module           # noqa: E402


def converter(**defn):
    c = moveset.Converter.__new__(moveset.Converter)
    c.defn = type('Definition', (), defn)
    c.effect_ids, c.aimed_effects, c.effect_rows, c.weapon_rows = set(), set(), [], []
    c.stats = collections.Counter()
    c.frames_left = lambda move, f: None
    return c


def uniform(objects, name, lo, hi):
    """A module's vector property: uniform between lo and hi (its object added to objects)."""
    objects['/x:' + name] = ('DistributionVectorUniform', {'Min': dict(zip('xyz', lo)), 'Max': dict(zip('xyz', hi))})
    return {'Distribution': "DistributionVectorUniform'/x:%s'" % name}


def emitter(count=1000, size=(1.0, 1.0, 1.0), along=(-500.0, 0.0, 0.0), origin=(0.0, 0.0, 20.0), bone=None):
    """A GPU emitter bursting `count` dots of `size` (cm) between its origin and `along` from it."""
    objects = {}
    start, sized = uniform(objects, 'start', (0.0, 0.0, 0.0), along), uniform(objects, 'size', size, size)
    modules = [Module('ParticleModuleRequired', {'EmitterOrigin': dict(zip('xyz', origin))}, objects),
               Module('ParticleModuleSpawn', {'BurstList': [{'Count': count}]}, objects),
               Module('ParticleModuleSize', {'StartSize': sized}, objects),
               Module('ParticleModuleLocation', {'StartLocation': start}, objects)]
    if bone is not None:
        modules.append(Module('PM_CharacterBone2', {'bUpdatePositionEachFrame': bone}, objects))
    return Emitter('e', {}, modules)


class AimedEffects(unittest.TestCase):
    def test_row_at_the_part_staying(self):
        c = converter()
        rows = c.aimed_rows(13, 9 << 16 | 101)
        self.assertEqual(rows, [dict(frame=13, id=moveset.EFFECT_PROP, value=0x965)])   # the right hand, effect 101
        self.assertEqual(c.aimed_effects, {101})
        self.assertEqual(c.effect_ids, {101})
        self.assertIs(c.effect_rows[0][0], rows[0])

    def test_unplaced_part_at_the_base_and_too_big_ids(self):
        c = converter()
        self.assertEqual(c.aimed_rows(1, (moveset.EFFECT_PARTS + 1) << 16 | 101)[0]['value'], 101)
        self.assertEqual(c.aimed_rows(1, 0x1234), [])
        self.assertEqual(c.effect_ids, {101})


class WeaponEffects(unittest.TestCase):
    def rows(self, c, pairs):
        out = []
        for effect, summon in pairs:
            out.append(dict(frame=1, id=moveset.EFFECT_PROP, value=9 << 8 | effect))
            c.effect_ids.add(effect)
            c.weapon_rows.append((out[-1], summon))
        return out

    def test_each_weapon_its_own_effect(self):
        c = converter(EFFECTS={'weapon_flashes': True})
        rows = self.rows(c, [(104, 3), (104, 3), (104, 2), (102, 3)])
        copies = {104: (104, 60)}
        out = c.weapon_effects(copies, used={229})
        self.assertEqual(out, {102: 3, 104: 3, 228: 2})         # the sword keeps 104 (two rows), the second a copy
        self.assertEqual(copies[228], (104, 60))                 # ... of the same source, as long
        self.assertEqual([r['value'] for r in rows], [0x968, 0x968, 9 << 8 | 228, 0x966])
        self.assertIn(228, c.effect_ids)

    def test_off_without_the_option(self):
        c = converter()
        rows = self.rows(c, [(104, 3), (104, 2)])
        self.assertEqual(c.weapon_effects({}, used=set()), {})
        self.assertEqual([r['value'] for r in rows], [0x968, 0x968])


class Marks(unittest.TestCase):
    def doc(self, **kw):
        """The level, staying and weapon marks of a new effect's root."""
        c = P.Converter.__new__(P.Converter)
        c.root = {'raw': bytes(720)}
        raw = c._doc(**kw)['root']['raw']
        return tuple(struct.unpack_from('>I', raw, at)[0] for at in (P.LEVEL_MARK[0], P.STAY_MARK[0], P.WEAPON_MARK[0]))

    def test_marks(self):
        self.assertEqual(self.doc(), (P.LEVEL_MARK[1], 0, 0))
        self.assertEqual(self.doc(staying=True), (P.LEVEL_MARK[1], P.STAY_MARK[1], 0))
        self.assertEqual(self.doc(summon=3), (P.LEVEL_MARK[1], 0, P.WEAPON_MARK[1] | 3))
        self.assertEqual(self.doc(summon=0)[2], P.WEAPON_MARK[1])     # summon 0 is a weapon too


class Lines(unittest.TestCase):
    def test_a_burst_of_dots_along_a_line(self):
        a, b = P._line_of(emitter())
        self.assertTrue(np.allclose(a, (-500.0, 0.0, 20.0)))     # from its far end, the origin added
        self.assertTrue(np.allclose(b, (0.0, 0.0, 20.0)))

    def test_not_lines(self):
        self.assertIsNone(P._line_of(emitter(count=64)))                    # a burst TTT2 draws as it is
        self.assertIsNone(P._line_of(emitter(size=(5.0, 5.0, 5.0))))        # big particles
        self.assertIsNone(P._line_of(emitter(along=(-50.0, 0.0, 0.0))))     # short
        self.assertIsNone(P._line_of(emitter(along=(-500.0, 100.0, 0.0))))  # a sheet, not a line

    def test_filament_model(self):
        c = P.Converter.__new__(P.Converter)
        c._mesh_names, made = {}, []
        c._model = lambda p, n, uv, colors, tris, tex_id, blend, what, wrap=None: made.append((p, uv, tris, wrap)) \
            or 'm.nud'
        line = ((-500.0, 0.0, 20.0), (0.0, 0.0, 20.0))
        wave = dict(amplitude=10.0, wavelength=100.0, phase=0.0, turn=0.0, width=1.0, jag=0.0, crawl=0.0, seed=1)
        self.assertEqual(c._filament_nud(line, wave, 0), 'm.nud')
        self.assertEqual(c._filament_nud(line, wave, 0), 'm.nud')
        self.assertEqual(len(made), 1)                                       # made once
        p, uv, tris, wrap = made[0]
        self.assertEqual(wrap, 1)                                            # its dashes repeat along it
        self.assertEqual(len(p) % 6, 0)                                      # three ribbons, two edges each
        self.assertEqual(len(tris), 2 * (len(p) - 6))                        # both sides of each ribbon's quads
        self.assertLessEqual(float(np.abs(p[:, 1]).max()), 10.0 + P.FILAMENT_WIDTH)      # waves 10 cm across
        self.assertGreater(float(np.abs(p[:, 1]).max()), 8.0)
        at_him = p[:, 0] > -1.0
        self.assertLessEqual(float(np.abs(p[at_him][:, 1]).max()), P.FILAMENT_WIDTH)   # no wave at the fighter
        self.assertTrue(np.allclose(uv[:, 0], -p[:, 0] / P.DASH_REPEAT, atol=0.03))   # U along it

    def test_straight_without_a_field(self):
        pos, nrm, uv, tris = P._filament(((-500.0, 0.0, 20.0), (0.0, 0.0, 20.0)),
                                         dict(amplitude=0.0, wavelength=100.0, phase=0.0, turn=0.0, width=1.0,
                                              jag=0.0, crawl=0.0, seed=1))
        self.assertTrue(np.allclose(np.hypot(pos[:, 1], pos[:, 2] - 20.0), P.FILAMENT_WIDTH / 2, atol=1e-3))

    def test_waves_of_a_field(self):
        em = emitter()
        self.assertEqual([w['amplitude'] for a, b, w in P._waves(em, 0.7)], [0.0])          # no field: straight
        objects = {}
        field = Module('ParticleModuleVectorFieldLocal', {'Intensity': 30.0, 'RelativeScale3D': [100, 20, 40],
                                                           'RelativeTranslation': {'x': -50.0}}, objects)
        em.modules.append(field)
        (first, last, wave), = P._waves(em, 0.7)
        self.assertEqual((first, last), (0.0, 1.0))
        self.assertEqual(wave['wavelength'], 200.0)                       # twice the field's size along the line
        self.assertAlmostEqual(wave['amplitude'], P.WAVE_GAIN * 30 * 0.35, places=1)   # to its middle, 0.35 s
        self.assertAlmostEqual(wave['phase'], round(2 * np.pi * 0.75, 3))

    def test_stage_alpha(self):
        keys = P._stage_alpha(0.0, 0.35, 0.1, None, 40)
        self.assertEqual([round(a, 3) for t, a in keys], [1.0, 1.0, 0.0, 0.0])   # straight first, gone by 0.35
        keys = P._stage_alpha(0.175, 1.0, 0.1, None, 40)
        self.assertEqual(keys[0][1], 0.0)                                         # waves after that
        self.assertEqual(keys[-1][1], 1.0)

    def test_rim_colours(self):
        # a flat board (thin along z): its faces dim, its edges lit
        pos = np.array([[x, y, z] for x in (-50, 50) for y in (-3, 3) for z in (-0.2, 0.2)], np.float64)
        nrm = np.array([[0, 0, 1], [0, 0, -1], [1, 0, 0], [0, 1, 0]] * 2, np.float64)
        rgba = P._rim_colours(pos, nrm)
        self.assertAlmostEqual(int(rgba[0, 0]), P.SHELL_FACE * 255, delta=1)
        self.assertAlmostEqual(int(rgba[1, 0]), P.SHELL_FACE * 255, delta=1)
        self.assertEqual(list(rgba[2]), [255, 255, 255, 255])

    def test_follows_bone(self):
        self.assertTrue(P._follows_bone(emitter(bone=True)))
        self.assertFalse(P._follows_bone(emitter(bone=False)))
        self.assertFalse(P._follows_bone(emitter()))


def table(*entries):
    """A distribution property: a curve through `entries` (vectors or floats) evenly over the life."""
    rows = [list(e) if isinstance(e, (list, tuple)) else [e] for e in entries]
    return {'Table': {'Op': 1, 'EntryCount': len(rows), 'EntryStride': len(rows[0]),
                      'TimeScale': float(max(1, len(rows) - 1)), 'Values': [x for r in rows for x in r]}}


class WeaponParticles(unittest.TestCase):
    def test_range_as_a_box(self):
        # shards along a blade: an offset 60 cm along it and a range of 70 cm along it, 20 cm across
        em = Emitter('e', {}, [Module('PM_CharacterBone', {'LocationOffset': {'Table': {
            'Op': 2, 'EntryCount': 1, 'EntryStride': 6, 'SubEntryStride': 3,
            'Values': [-10.0, -20.0, -20.0, 130.0, 20.0, 20.0]}}}, {})])
        c = P.Converter.__new__(P.Converter)
        for box in (False, True):
            pa = {'raw': bytes(1280), 'tracks': {64: {'keys': [[0, 0.0, 0.0, 0.0]]}}}
            c._location(em, pa, box=box)
            self.assertEqual(pa['tracks'][64]['keys'], [[0, 0.0, 0.0, 600.0]])          # (mm, along TTT2's z)
            spread = struct.unpack_from('>3f', pa['raw'], 76)
            if box:
                self.assertEqual(pa['raw'][P.alo.SHAPE], P.BOX_SHAPE)
                self.assertEqual(struct.unpack('>6f', pa['shape']['raw']), (400.0, 400.0, 1400.0, 0.0, 0.0, 0.0))
                self.assertEqual(spread, (0.0, 0.0, 0.0))
            else:
                self.assertEqual(pa['raw'][P.alo.SHAPE], 0)
                self.assertNotIn('shape', pa)
                self.assertEqual(spread, (200.0, 200.0, 700.0))

    def test_flash_colour(self):
        # Noctis's shards: 58-600 times a cyan, red-tinted (x3, x0.3, x0.3) a tenth into their life; opacity halved
        # by the middle, gone at the end
        em = Emitter('e', {}, [Module('ParticleModuleColor', {'StartColor': table((58.0, 69.0, 100.0)),
                                                              'StartAlpha': table(1.0)}, {}),
                               Module('ParticleModuleColorScaleOverLife', {
                                   'ColorScaleOverLife': table((1.0, 1.0, 1.0), (3.0, 0.3, 0.3), (6.0, 6.0, 6.0)),
                                   'AlphaScaleOverLife': table(1.0, 0.5, 0.0)}, {})])
        lit = []
        c = P.Converter.__new__(P.Converter)
        c.textures = type('Textures', (), {'lit': lambda self, src, peak, peak_a, additive: lit.append(peak) or
                                           ('t.nut', 0, 1, 1)})()
        src = P.Source(('white',), None, 1)
        e = {'raw': bytes(P.alo.NODE_SIZE), 'spawner': {'raw': bytes(P.alo.SPAWNER_SIZE), 'tracks': {
            P.alo.COLOUR_TRACK: {'keys': [[0, 1.0, 1.0, 1.0]]}, P.alo.ALPHA_TRACK: {'keys': [[0, 1.0]]}}}}
        c._colour(em, e, src, True, 30, display=True)
        colour = e['spawner']['tracks'][P.alo.COLOUR_TRACK]['keys']
        alpha = e['spawner']['tracks'][P.alo.ALPHA_TRACK]['keys']
        self.assertEqual([round(k[1], 2) for k in alpha], [1.0, 0.5, 0.0])     # the opacity Tekken 7 gives it
        self.assertTrue(all(min(k[1:]) > 0.9 for k in colour))                # shown white throughout, never red
        peak, = lit
        self.assertAlmostEqual(max(peak), P.SHELL_PEAK)                         # baked at the cap, its hue kept
        self.assertAlmostEqual(peak[0] / peak[2], 0.58, places=2)

    def test_shells_by_blend(self):
        # a glow (added, its edges lit) and a layer of colour (blended over the weapon): a shell model each
        c = P.Converter.__new__(P.Converter)
        c._mesh_names, made = {}, []
        board = np.array([[x, y, z] for x in (-50, 50) for y in (-3, 3) for z in (-0.2, 0.2)], np.float64)
        c.weapon_shell = lambda weapon: (board, np.tile([[0.0, 0.0, 1.0]], (8, 1)), np.zeros((8, 2)),
                                         np.array([[0, 1, 2]]))
        c._model = lambda p, n, uv, colors, tris, tex_id, blend, what, wrap=None: made.append((colors, blend)) or \
            'm%d.nud' % len(made)
        weapon = {'mesh': 'M', 'bone': 'B'}
        self.assertEqual(c._shell_nud(weapon, 0, P.MODEL_ADD), 'm1.nud')
        self.assertEqual(c._shell_nud(weapon, 1, P.MODEL_ALPHA), 'm2.nud')
        self.assertEqual(c._shell_nud(weapon, 2, P.MODEL_ADD), 'm1.nud')       # one for every emitter of it
        self.assertIsNotNone(made[0][0])                                          # rim colours
        self.assertEqual((made[1][0], made[1][1]), (None, P.MODEL_ALPHA))


if __name__ == '__main__':
    unittest.main()
