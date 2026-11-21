"""The game's garments fitted to an added fighter (convert/wardrobe.py): made-up skeletons, meshes and lists."""
import struct
import unittest

import numpy as np

from ttt2char.convert import itemdb, wardrobe
from ttt2char.ttt2 import archive, bxml, nud


def el(tag, attrs=(), children=()):
    return dict(tag=tag, attrs=list(attrs), children=list(children))


def skeleton(joints, prefix='cha:'):
    """joints: [(name, parent, world position)] -> a BONE dict (no rotations)."""
    world = np.array([j[2] for j in joints], np.float32)
    parent = [j[1] for j in joints]
    local = np.array([world[i] - (world[p] if p >= 0 else 0) for i, p in enumerate(parent)], np.float32)
    return dict(names=[prefix + j[0] for j in joints], parent=parent, t=local, r=np.zeros_like(local),
                s=np.ones_like(local), opt=[], params=None, scale=1.0)


def mesh(name, points, triangles, bones, weights=None, flags=wardrobe.SKIN_FLAGS, texture=5):
    verts = np.zeros(len(points), nud.vertex_dtype(0x11, 0x10))
    verts['pos'] = points
    verts['bones'][:, 0] = bones
    verts['w'][:, 0] = 1.0 if weights is None else weights
    indices = []
    for t in triangles:
        indices += list(t) + [0xFFFF]
    material = dict(flags=flags, src=0, dst=0, alpha_test=0, alpha_func=0, ref=0, cull=0x405,
                    textures=[dict(id=texture, wrap_s=1, wrap_t=1, min=1, mag=1, mip=1)], props=[(None, [])])
    return dict(name=name, sphere=(0, 0, 0, 1), center=(0, 0, 0), boneflag=4, singlebind=-1,
                polys=[dict(vtype=0x11, uvtype=0x10, pflag=4, indices=np.array(indices[:-1], '>u2'), verts=verts,
                            materials=[material])])


def ring(radius, y, n=12, centre=(0.0, 0.0)):
    a = np.arange(n) * 2 * np.pi / n
    return np.stack([centre[0] + radius * np.sin(a), np.full(n, y), centre[1] + radius * np.cos(a)], 1)


def cap(name, radius, y, bone, centre=(0.0, 0.0), n=12):
    """A cone open at the bottom: the stand-in for a head, its rim the ring."""
    points = np.concatenate([ring(radius, y, n, centre), [[centre[0], y + 50, centre[1]]]])
    return mesh(name, points, [(i, (i + 1) % n, n) for i in range(n)], bone)


def tube(name, radius, top, bottom, top_bone, bottom_bone, n=12):
    points = np.concatenate([ring(radius, top, n), ring(radius, bottom, n)])
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris += [(i, j, n + i), (j, n + j, n + i)]
    return mesh(name, points, tris, [top_bone] * n + [bottom_bone] * n)


SOURCE = skeleton([('HARA', -1, (0, 1000, 0)), ('KUBI_jnt', 0, (0, 1400, 0)), ('ATAMA_jnt', 1, (0, 1500, 0)),
                   ('TE_R_jnt', 0, (-700, 1400, 0))])
TARGET = skeleton([('HARA', -1, (0, 990, 0)), ('KUBI_jnt', 0, (0, 1380, 0)), ('ATAMA_jnt', 1, (0, 1520, 0)),
                   ('TE_R_jnt', 0, (-640, 1400, 0)), ('OPT400_cloth', 0, (0, 900, 0))])


class Archives:
    def __init__(self, entries):
        self.where = dict(entries)

    def has(self, key):
        return key in self.where

    def read(self, key):
        return self.where[key]


class Packs(unittest.TestCase):
    def test_a_members_key_gives_its_pack_back(self):
        for pack, index in ((0x12345678, 0), (0xC0FFEE00, 1), (0x0BADF00D, 601), (0xFFFFFFFF, 4095)):
            self.assertEqual(archive.pack_of(archive.member_key(pack, index), index), pack)

    def test_a_pack_is_found_by_its_members_even_without_member_zero(self):
        pack, other = 0x1101524B, 0x22222222
        entries = {archive.member_key(pack, i): b'right %d' % i for i in (5, 9, 600)}
        entries.update({archive.member_key(other, i): b'wrong %d' % i for i in (5, 9)})
        found = wardrobe.find_pack(Archives(entries), [600, 5, 9], lambda index, data: data == b'right 5')
        self.assertEqual(found, pack)
        self.assertIsNone(wardrobe.find_pack(Archives(entries), [5, 9, 77], lambda index, data: True))

    def test_a_pack_is_told_by_the_members_asked_for_not_only_its_first(self):
        # two packs hold members 5, 9 and 600; the first members pass in both, the second only in the right one
        pack, other = 0x1101524B, 0x22222222
        entries = {archive.member_key(other, 5): b'body', archive.member_key(other, 9): b'two bones',
                   archive.member_key(pack, 5): b'body', archive.member_key(pack, 9): b'body',
                   archive.member_key(other, 600): b'', archive.member_key(pack, 600): b''}
        body = lambda index, data: data == b'body'
        self.assertEqual(wardrobe.find_pack(Archives(entries), [5, 9, 600], body, [5, 9]), pack)
        self.assertIsNone(wardrobe.find_pack(Archives(entries), [5, 9, 600], body, [5, 9, 600]))
        self.assertIn(wardrobe.find_pack(Archives(entries), [5, 9, 600], body), (pack, other))

    def test_a_spring_pack_need_not_agree_bone_for_bone(self):
        def springs(ids):
            return wardrobe.SPRING_MAGIC + bytes(28) + struct.pack('>I', len(ids)) + bytes(12) + \
                b''.join(struct.pack('>I', i) + bytes(92) for i in ids)
        pack, other = 0x66C4E6AD, 0x33333333
        # the skeleton of member 3 has two helper bones (1010, 1011) no spring drives
        bones = {3: [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 1010, 1011], 6: [200, 201]}
        entries = {archive.member_key(pack, 3): springs(bones[3][:10]), archive.member_key(pack, 6): springs([200, 201]),
                   archive.member_key(other, 3): springs([100, 101, 300]), archive.member_key(other, 6): springs([200])}
        self.assertEqual(wardrobe.spring_pack(Archives(entries), bones), pack)
        del entries[archive.member_key(pack, 3)], entries[archive.member_key(pack, 6)]
        self.assertIsNone(wardrobe.spring_pack(Archives(entries), bones))

    def test_the_spring_pack_is_the_one_whose_members_drive_the_garments_own_bones(self):
        def springs(ids, magic=wardrobe.SPRING_MAGIC):
            return magic + bytes(28) + struct.pack('>I', len(ids)) + bytes(12) + \
                b''.join(struct.pack('>I', i) + bytes(92) for i in ids)
        pack, other, third = 0x6DD3B9FF, 0x33333333, 0x44444444
        entries = {archive.member_key(pack, 3): springs([0, 250, 251]), archive.member_key(pack, 6): springs([100])}
        # another fighter's pack has spring files under the same numbers, for other bones
        entries.update({archive.member_key(other, 3): springs([0, 300]), archive.member_key(other, 6): springs([100])})
        entries.update({archive.member_key(third, 3): b'NDP3', archive.member_key(third, 6): springs([100])})
        bones = {3: [0, 250, 251], 6: [100]}
        self.assertEqual(wardrobe.spring_pack(Archives(entries), bones), pack)
        entries[archive.member_key(pack, 6)] = springs([100], b'\x00\x00\xa0\x40')     # the game would stop on it
        self.assertIsNone(wardrobe.spring_pack(Archives(entries), bones))
        self.assertIsNone(wardrobe.spring_pack(Archives(entries), {}))

class Fitting(unittest.TestCase):
    def test_joints_move_by_name_and_a_parts_own_bone_follows_its_parent(self):
        part = skeleton([('HARA', -1, (0, 1000, 0)), ('KUBI_jnt', 0, (0, 1400, 0)), ('ATAMA_jnt', 1, (0, 1500, 0)),
                         ('TE_R_jnt', 0, (-700, 1400, 0)), ('OPT598_sway', 3, (-720, 1400, 0))], prefix='par:cha:')
        shifts = wardrobe.joint_shifts(SOURCE, TARGET, part)
        np.testing.assert_allclose(shifts, [(0, -10, 0), (0, -20, 0), (0, 20, 0), (60, 0, 0), (60, 0, 0)], atol=1e-4)

    def test_a_vertex_moves_by_its_weights(self):
        m = mesh('sleeve', [(-700, 1400, 0), (-350, 1400, 0), (0, 1000, 0)], [(0, 1, 2)], [3, 3, 0])
        m['polys'][0]['verts']['bones'][1] = (3, 0, 0, 0)
        m['polys'][0]['verts']['w'][1] = (0.5, 0.5, 0, 0)
        model = wardrobe.fit(dict(meshes=[m]), wardrobe.joint_shifts(SOURCE, TARGET))
        np.testing.assert_allclose(model['meshes'][0]['polys'][0]['verts']['pos'],
                                   [(-640, 1400, 0), (-320, 1395, 0), (0, 990, 0)], atol=1e-3)
        self.assertAlmostEqual(model['sphere'][3], model['meshes'][0]['sphere'][3])

    def test_the_necks_top_ring_lands_just_inside_the_fighters_rim(self):
        shifts = wardrobe.joint_shifts(SOURCE, TARGET)
        source_face = cap('cha:kao_O_OBJ', 50, 1490, 2)
        target_face = cap('abc_fac', 44, 1516, 2, centre=(0.0, 6.0))       # another head: narrower, set forward
        neck = wardrobe.Neck(source_face, target_face, shifts)
        cut = wardrobe.fit(dict(meshes=[tube('kubiA_O_OBJ', 50, 1490, 1400, 2, 1)]), shifts, neck)
        points = cut['meshes'][0]['polys'][0]['verts']['pos']
        top, bottom = points[:12], points[12:]
        up, inward = wardrobe.NECK_TUCK
        np.testing.assert_allclose(top[:, 1], 1516 + up, atol=0.05)
        np.testing.assert_allclose(np.hypot(top[:, 0], top[:, 2] - 6.0), 44 - inward, atol=1.0)
        np.testing.assert_allclose(bottom, ring(50, 1380), atol=1e-3)      # beyond the reach: only its joint's move

    def test_the_necks_top_ring_is_bound_as_the_fighters_rim_is(self):
        shifts = wardrobe.joint_shifts(SOURCE, TARGET)
        source_face = cap('cha:kao_O_OBJ', 50, 1490, 2)
        target_face = cap('abc_fac', 44, 1516, 2, centre=(0.0, 6.0))
        v = target_face['polys'][0]['verts']
        v['bones'][:12, 1] = 1                      # this head's rim follows the head by 0.7, the neck by 0.3
        v['w'][:12] = (0.7, 0.3, 0, 0)
        cut = wardrobe.fit(dict(meshes=[tube('kubiA_O_OBJ', 50, 1490, 1400, 2, 1)]), shifts,
                           wardrobe.Neck(source_face, target_face, shifts))
        verts = cut['meshes'][0]['polys'][0]['verts']
        for top in verts[:12]:
            self.assertEqual(top['bones'][:2].tolist(), [2, 1])
            np.testing.assert_allclose(top['w'], (0.7, 0.3, 0, 0), atol=1e-6)
        for below in verts[12:]:                    # the rest of the neck keeps its own
            self.assertEqual(int(below['bones'][0]), 1)
            np.testing.assert_allclose(below['w'], (1, 0, 0, 0))

    def test_skin_takes_the_tone_of_the_fighters_plain_face_skin(self):
        source_face, target_face = cap('cha:kao_O_OBJ', 50, 1490, 2, ), cap('abc_fac', 50, 1510, 2)
        target_face['polys'][0]['materials'][0]['textures'][0]['id'] = 6
        made_up = np.full((8, 8, 4), 160, np.uint8)
        made_up[0, 0] = 40                        # make-up and shade: the darker part of a face is not its tone
        target_face['polys'][0]['verts']['uv'][:8, 0] = (0.5, 0.5)         # (5 of its 13 vertices lie in the shade)
        images = {5: np.full((8, 8, 4), 128, np.uint8), 6: made_up}
        gain = wardrobe.skin_gain(source_face, target_face, images)
        np.testing.assert_allclose(gain, [wardrobe._linear(160) / wardrobe._linear(128)] * 3, rtol=1e-6)
        np.testing.assert_allclose(wardrobe.skin_gain(source_face, target_face, {5: images[5]}), 1.0)
        self.assertEqual(wardrobe._srgb8(wardrobe._linear(np.array([0, 77, 255]))).tolist(), [0, 77, 255])

    def test_a_face_not_drawn_as_skin_leaves_the_tone_to_the_outfits_bare_skin(self):
        source_face, painted = cap('cha:kao_O_OBJ', 50, 1490, 2), cap('abc_fac', 50, 1510, 2)
        painted['polys'][0]['materials'][0].update(flags=0x24600099)        # the cloth material: not her tone
        painted['polys'][0]['materials'][0]['textures'][0]['id'] = 6
        arms = cap('abc_bdu', 40, 1300, 0)
        arms['polys'][0]['materials'][0]['textures'][0]['id'] = 7
        cloth = cap('abc_bdu', 60, 1200, 0)
        cloth['polys'][0]['materials'][0].update(flags=0x24400099)
        images = {5: np.full((8, 8, 4), 128, np.uint8), 6: np.full((8, 8, 4), 90, np.uint8),
                  7: np.full((8, 8, 4), 144, np.uint8)}
        self.assertIs(wardrobe.skin_polygon(painted, [cloth, arms]), arms['polys'][0])
        self.assertIsNone(wardrobe.skin_polygon(painted, [cloth]))
        self.assertIs(wardrobe.skin_polygon(source_face, [arms]), source_face['polys'][0])
        gain = wardrobe.skin_gain(source_face, painted, images, [cloth, arms])
        np.testing.assert_allclose(gain, [wardrobe._linear(144) / wardrobe._linear(128)] * 3, rtol=1e-6)
        np.testing.assert_allclose(wardrobe.skin_gain(source_face, painted, images, [cloth]), 1.0)

    def test_a_brightening_gain_eases_toward_white_instead_of_cutting_off(self):
        x = np.array([[0.1, 0.5, 0.9]] * 3).T                   # three levels, the same in each channel
        gain = np.array([0.5, 1.0, 1.8])
        out = wardrobe.toned(x, gain)
        np.testing.assert_allclose(out[:, :2], (x * gain)[:, :2])           # no brightening: the plain product
        np.testing.assert_allclose(out[0, 2], 0.18)                         # under the knee: the plain product
        self.assertTrue(wardrobe.GAIN_KNEE < out[1, 2] < out[2, 2] < 1.0)    # above: still told apart, under white
        self.assertGreaterEqual(out[2, 2], 0.9)                             # and never darker than it was

    def test_skin_without_colour_is_not_the_tone(self):
        face = cap('abc_fac', 50, 1510, 2)
        image = np.zeros((8, 8, 4), np.uint8)
        image[..., :3] = (120, 84, 70)                          # dark skin
        image[:4, :4, :3] = 235                                 # a white beard: brighter, and not skin
        uv = face['polys'][0]['verts']['uv']
        uv[:, 0] = (0.75, 0.75)
        uv[:6, 0] = (0.1, 0.1)
        tone = wardrobe.plain_skin(face, {5: image})
        np.testing.assert_allclose(tone, wardrobe._linear(np.array([120, 84, 70])), rtol=1e-6)

    def test_a_garments_texture_file_holds_the_fighters_skin_under_the_ids_its_polygons_name(self):
        def tex(gidx, value, fmt=0):
            return dict(fmt=fmt, w=4, h=4, mips=[bytes([value]) * 16], gidx=gidx)
        source = dict(textures=[tex(0x10, 1), tex(0x11, 2), tex(0x12, 3)])
        copies = [tex(0x700, 101), tex(0x701, 102)]              # the fighter's copies of 0x10 and 0x11
        ids = {0x10: 0x700, 0x11: 0x701}
        part = dict(textures=[tex(0x900, 9), tex(0x10, 1), tex(0x11, 77), tex(0x12, 3)])
        made = wardrobe.garment_textures(part, source, copies, ids, set(), np.ones(3))
        self.assertEqual([t['gidx'] for t in made], [0x900, 0x700, 0x701, 0x12])
        self.assertIs(made[0], part['textures'][0])               # its cloth: as it is
        self.assertIs(made[1], copies[0])                         # the base model's skin: the fighter's copy
        self.assertEqual(made[2]['mips'], [bytes([77]) * 16])     # its own version of a skin map: kept, renamed
        self.assertIs(made[3], part['textures'][3])               # a base texture no fitted polygon names


def limbed(arm=700.0):
    """A skeleton with the joints girth is measured about: arms along X (the wrist `arm` out), legs and trunk along Y."""
    joints = [('KOSHI_jnt', -1, (0, 1000, 0)), ('MUNE2_jnt', 0, (0, 1200, 0)), ('KUBI_jnt', 1, (0, 1400, 0)),
              ('ATAMA_jnt', 2, (0, 1500, 0))]
    for s, x in (('R', -1.0), ('L', 1.0)):
        base = len(joints)
        joints += [('SAKOTSU_%s_jnt' % s, 1, (x * 100, 1400, 0)), ('KATA_%s_jnt' % s, base, (x * 200, 1400, 0)),
                   ('UDE_%s_jnt' % s, base + 1, (x * 450, 1400, 0)), ('TE_%s_jnt' % s, base + 2, (x * arm, 1400, 0)),
                   ('MOMO_%s_jnt' % s, 0, (x * 100, 900, 0)), ('HIZA_%s_jnt' % s, base + 4, (x * 100, 500, 0)),
                   ('ASHI_%s_jnt' % s, base + 5, (x * 100, 100, 0))]
    return skeleton(joints)


def sleeve(name, radius, bon, joint='KATA_R_jnt', xs=(-250, -300, -350, -400, -500, -550, -600, -650), n=48, flags=wardrobe.SKIN_FLAGS):
    """Rings round the right arm's axis, all bound to one joint."""
    a = np.arange(n) * 2 * np.pi / n
    points = np.concatenate([np.stack([np.full(n, float(x)), 1400 + radius * np.sin(a), radius * np.cos(a)], 1) for x in xs])
    bone = [m.split(':')[-1] for m in bon['names']].index(joint)
    return mesh(name, points, [(0, 1, 2)], bone, flags=flags)


class Girth(unittest.TestCase):
    def test_limbs_are_the_arms_without_hands_the_legs_without_feet_and_the_trunk(self):
        bon = limbed()
        names = [n.split(':')[-1] for n in bon['names']]
        parts = wardrobe.limbs(bon)
        self.assertEqual({names[i] for i in parts['arm R'][1]}, {'KATA_R_jnt', 'UDE_R_jnt'})
        self.assertEqual({names[i] for i in parts['leg L'][1]}, {'MOMO_L_jnt', 'HIZA_L_jnt'})
        self.assertEqual({names[i] for i in parts['trunk'][1]}, {'KOSHI_jnt', 'MUNE2_jnt', 'SAKOTSU_R_jnt', 'SAKOTSU_L_jnt'})
        self.assertEqual(wardrobe.limbs(SOURCE), {})

    def test_a_thicker_bare_arm_is_measured_and_the_trunk_is_the_mean_of_the_limbs(self):
        theirs = wardrobe.skin_patches([sleeve('ude_A_O_OBJ', 50.0, limbed())], limbed())
        ours = wardrobe.skin_patches([sleeve('abc_bdu', 70.0, limbed())], limbed())
        g = wardrobe.girth_of(theirs, ours)
        self.assertAlmostEqual(g['arm'], 1.4, places=3)
        self.assertAlmostEqual(g['leg'], 1.4, places=3)         # (never bared: as the arm)
        self.assertAlmostEqual(g['trunk'], 1.4, places=3)

    def test_cloth_is_not_measured_and_a_like_limb_keeps_the_sources_girth(self):
        theirs = wardrobe.skin_patches([sleeve('ude_A_O_OBJ', 50.0, limbed())], limbed())
        cloth = wardrobe.skin_patches([sleeve('abc_bdu', 90.0, limbed(), flags=0x24400099)], limbed())
        self.assertEqual(wardrobe.girth_of(theirs, cloth), dict(arm=1.0, leg=1.0, trunk=1.0))
        near = wardrobe.skin_patches([sleeve('abc_bdu', 53.0, limbed())], limbed())
        self.assertEqual(wardrobe.girth_of(theirs, near), dict(arm=1.0, leg=1.0, trunk=1.0))
        huge = wardrobe.skin_patches([sleeve('abc_bdu', 150.0, limbed())], limbed())
        self.assertEqual(wardrobe.girth_of(theirs, huge)['arm'], wardrobe.GIRTH_SPAN[1])

    def test_a_limb_off_its_axis_is_measured_by_its_whole_rings(self):
        bon = limbed()
        ours = sleeve('abc_bdu', 40, bon)
        ours['polys'][0]['verts']['pos'][:, 2] += 12               # the same arm, a little in front of its joints
        theirs = wardrobe.skin_patches([sleeve('ude_A_O_OBJ', 40, bon)], bon)
        mine = wardrobe.skin_patches([ours], bon)
        self.assertEqual(wardrobe.girth_of(theirs, mine, rings=True)['arm'], 1.0)
        thick = wardrobe.skin_patches([sleeve('abc_bdu', 52, bon)], bon)
        self.assertAlmostEqual(wardrobe.girth_of(theirs, thick, rings=True)['arm'], 1.3, 2)

    def test_a_longer_arm_is_not_a_thicker_one(self):
        long = limbed(arm=800.0)
        theirs = wardrobe.skin_patches([sleeve('ude_A_O_OBJ', 50.0, limbed())], limbed())
        ours = wardrobe.skin_patches([sleeve('abc_bdu', 50.0, long, xs=(-250, -310, -370, -430, -500, -580, -660, -740))], long)
        self.assertEqual(wardrobe.girth_of(theirs, ours)['arm'], 1.0)

    def test_an_arm_swells_about_its_axis_and_the_hand_and_the_wrist_do_not(self):
        bon = limbed()
        thick = wardrobe.Girth(bon, dict(arm=1.4, leg=1.0, trunk=1.0))
        arm = sleeve('ude_A_O_OBJ', 50.0, bon, xs=(-300, -700))
        hand = sleeve('ude_A_O_OBJ', 50.0, bon, joint='TE_R_jnt', xs=(-750,))
        model = wardrobe.fit(dict(meshes=[arm, hand]), np.zeros((len(bon['names']), 3)), girth=thick.of())
        r = np.linalg.norm(model['meshes'][0]['polys'][0]['verts']['pos'][:, 1:] - (1400.0, 0.0), axis=1)
        np.testing.assert_allclose(r[:48], 70.0, atol=0.01)                 # the upper arm: 1.4 times
        np.testing.assert_allclose(r[48:], 50.0 * 1.4 ** 0.5, atol=0.1)     # at the wrist: eased
        np.testing.assert_allclose(model['meshes'][0]['polys'][0]['verts']['pos'][:48, 0], -300.0, atol=1e-3)
        np.testing.assert_allclose(np.linalg.norm(model['meshes'][1]['polys'][0]['verts']['pos'][:, 1:] - (1400.0, 0.0), axis=1), 50.0, atol=1e-3)

    def test_a_garments_own_bone_swells_with_the_limb_that_holds_it(self):
        bon = limbed()
        part = skeleton([('UDE_R_jnt', -1, (-450, 1400, 0)), ('OPT300_cuff', 0, (-500, 1400, 0)), ('OPT301_tail', -1, (0, 0, 0))])
        thick = wardrobe.Girth(bon, dict(arm=1.2, leg=1.0, trunk=1.0))
        cuff = sleeve('cuff', 60.0, part, joint='OPT300_cuff', xs=(-300,))
        loose = sleeve('cuff', 60.0, part, joint='OPT301_tail', xs=(-300,))
        move = thick.of(part)
        np.testing.assert_allclose(np.linalg.norm(move(cuff['polys'][0]['verts']), axis=1), 12.0, atol=1e-3)
        np.testing.assert_allclose(move(loose['polys'][0]['verts']), 0.0, atol=1e-9)
        self.assertIsNone(wardrobe.Girth(bon, dict(arm=1.0, leg=1.0, trunk=1.0)).of())


class Pieces(unittest.TestCase):
    def test_cut_names(self):
        self.assertTrue(all(wardrobe.is_cut(n) for n in ('kubiA_O_OBJ', 'ude_AB_O_OBJ', 'asi_E_O_OBJ', 'hara_O_OBJ')))
        self.assertFalse(any(wardrobe.is_cut(n) for n in ('cha:kao_O_OBJ', 'abc_bdu_1p', 'belt_O_OBJ')))

    def test_a_body_gives_way_only_as_an_upper_and_a_lower_piece(self):
        tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        two = dict(meshes=[mesh(n, tri, [(0, 1, 2)], 0) for n in ('abc_bdl_1p', 'abc_bdu_1p', 'abc_fac', 'abc_har')])
        found = wardrobe.own_pieces(two, 'abc')
        self.assertEqual({pos: [m['name'] for m in ms] for pos, ms in found.items()},
                         {wardrobe.LOWER: ['abc_bdl_1p'], wardrobe.UPPER: ['abc_bdu_1p']})
        one = dict(meshes=[mesh(n, tri, [(0, 1, 2)], 0) for n in ('abc_bdf_1p', 'abc_fac')])
        self.assertEqual(wardrobe.own_pieces(one, 'abc'), {})

    def test_a_full_body_piece_and_the_piece_worn_with_it_are_the_halves_they_cover(self):
        bon = skeleton([('HARA', -1, (0, 1000, 0)), ('MUNE1_jnt', 0, (0, 1200, 0)), ('KOSHI_jnt', 0, (0, 950, 0)),
                        ('MOMO_R_jnt', 2, (-90, 900, 0)), ('OPT400_hem', 3, (-90, 600, 0))])
        tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        jacket, trousers = mesh('abc_bdf', tri, [(0, 1, 2)], 1), mesh('abc_dep0', tri, [(0, 1, 2)], [3, 4, 4])
        self.assertEqual(wardrobe.lower_share(jacket, bon), 0.0)
        self.assertEqual(wardrobe.lower_share(trousers, bon), 1.0)        # (a bone of its own under a leg joint too)
        found = wardrobe.own_pieces(dict(meshes=[jacket, trousers, mesh('abc_fac', tri, [(0, 1, 2)], 0)]), 'abc', bon)
        self.assertEqual({pos: [m['name'] for m in ms] for pos, ms in found.items()},
                         {wardrobe.UPPER: ['abc_bdf'], wardrobe.LOWER: ['abc_dep0']})
        # a piece that covers both halves stays whole, and so does the body
        whole = mesh('abc_bdf', tri, [(0, 1, 2)], [1, 3, 3])
        self.assertEqual(wardrobe.own_pieces(dict(meshes=[whole, trousers]), 'abc', bon), {})
        self.assertEqual(wardrobe.own_pieces(dict(meshes=[jacket, trousers]), 'abc'), {})      # (no skeleton: names only)

    def test_a_pieces_skeleton_holds_the_bodys_bones_and_only_its_own_extra_ones(self):
        bon = skeleton([('HARA', -1, (0, 1000, 0)), ('KUBI_jnt', 0, (0, 1400, 0)), ('OPT300_hair', 1, (0, 1450, -50)),
                        ('KOSHI_jnt', 0, (0, 950, 0)), ('OPT400_hem', 3, (0, 700, 0)), ('OPT401_hem', 4, (0, 500, 0)),
                        ('OPT800_weapon', 0, (300, 1000, 0))])
        bon['opt'] = [300, 400, 401, 800]
        tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        skirt, shirt = mesh('abc_bdl', tri, [(0, 1, 2)], [3, 5, 5]), mesh('abc_bdu', tri, [(0, 1, 2)], [0, 1, 1])
        lower = wardrobe.piece_skeleton(bon, [skirt])
        self.assertEqual([n.split(':')[-1] for n in lower['names']],
                         ['HARA', 'KUBI_jnt', 'KOSHI_jnt', 'OPT400_hem', 'OPT401_hem'])      # (401's parent with it)
        self.assertEqual(lower['parent'], [-1, 0, 0, 2, 3])
        self.assertEqual(lower['opt'], [400, 401])                 # exactly the extra bones it holds
        self.assertEqual(skirt['polys'][0]['verts']['bones'][:, 0].tolist(), [2, 4, 4])
        np.testing.assert_allclose(lower['t'][4], bon['t'][5])
        upper = wardrobe.piece_skeleton(bon, [shirt])
        self.assertEqual(len(upper['names']), 3)
        self.assertEqual(upper['opt'], [])
        self.assertEqual(shirt['polys'][0]['verts']['bones'][:, 0].tolist(), [0, 1, 1])
        self.assertEqual(len(bon['names']), 7)                     # (the body's skeleton is left as it was)

    @staticmethod
    def springs(entries, capsules, rest=b'REST'):
        """A made-up spring file: entries [(OPT number, [capsule numbers], [linked OPT numbers])], capsules [bone]."""
        head = struct.pack('>f', 5.0) + bytes(28) + struct.pack('>I', len(entries)) + bytes(12)
        body = b''.join(struct.pack('>I', n) + bytes(0x30 - 4) + struct.pack('>III', 8, len(c), len(l)) + bytes(0x24)
                        for n, c, l in entries)
        caps = struct.pack('>I', len(capsules)) + bytes(12) + b''.join(struct.pack('>II', 1, b) + bytes(0x48)
                                                                      for b in capsules)
        pairs = b''.join(struct.pack('>II', n, k) + bytes(8) for n, c, _ in entries for k in c)
        links = b''.join(struct.pack('>IIff', n, m, 0.8, 0.5) + bytes(36) for n, _, l in entries for m in l)
        return head + body + caps + pairs + links + rest

    CHAINS = [('HARA', -1, (0, 1000, 0)), ('KOSHI_jnt', 0, (0, 950, 0)), ('OPT400_tail', 1, (-50, 800, -60)),
              ('OPT401_tail', 2, (-50, 600, -60)), ('OPT402_tail', 1, (50, 800, -60)), ('OPT500_hair', 0, (0, 1500, -50))]

    def test_a_piece_holds_whole_chains_with_the_chains_tied_to_them(self):
        bon = skeleton(self.CHAINS)
        bon['opt'] = [400, 401, 402, 500]
        mop = self.springs([(400, [0], [402]), (401, [], []), (402, [1], [400]), (500, [], [])], [1, 5])
        self.assertEqual(wardrobe.spring_links(mop), {400: {402}, 401: set(), 402: {400}, 500: set()})
        tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        # bound to the tail's lower bone only: its chain up to the hip and the chain tied to it come with it
        alone = wardrobe.piece_skeleton(bon, [mesh('abc_bdf', tri, [(0, 1, 2)], 3)])
        self.assertEqual(alone['opt'], [400, 401])
        held = wardrobe.piece_skeleton(bon, [mesh('abc_bdf', tri, [(0, 1, 2)], 3)], wardrobe.spring_links(mop))
        self.assertEqual(held['opt'], [400, 401, 402])           # (not the hair: nothing ties it to the tails)
        self.assertEqual([n.split(':')[-1] for n in held['names']],
                         ['HARA', 'KOSHI_jnt', 'OPT400_tail', 'OPT401_tail', 'OPT402_tail'])
        # a chain's upper bone alone brings the bones below it
        top = wardrobe.piece_skeleton(bon, [mesh('abc_bdf', tri, [(0, 1, 2)], 2)], {})
        self.assertEqual(top['opt'], [400, 401])

    def test_a_pieces_springs_are_the_bodys_entries_for_the_bones_it_holds(self):
        from ttt2char.convert import cloth
        bon = skeleton(self.CHAINS)
        bon['opt'] = [400, 401, 402, 500]
        mop = self.springs([(400, [0], [402]), (401, [], []), (402, [1, 0], [400]), (500, [1], [])], [1, 5])
        tri = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        piece = wardrobe.piece_skeleton(bon, [mesh('abc_bdf', tri, [(0, 1, 2)], 3)], wardrobe.spring_links(mop))
        out = wardrobe.piece_springs(mop, bon, piece)
        entries, capsules, pairs, links, rest = cloth.parse(out)
        self.assertEqual(out[:cloth.MOP_COUNT], mop[:cloth.MOP_COUNT])
        self.assertEqual([struct.unpack_from('>I', e)[0] for e in entries], [400, 401, 402])
        self.assertEqual([struct.unpack_from('>I', e, 0x30)[0] for e in entries], [8, 8, 8])   # (as they were)
        # the capsule on the hip, its bone numbered as in the piece; the hair's capsule is not the piece's
        self.assertEqual([struct.unpack_from('>II', c) for c in capsules], [(1, 1)])
        self.assertEqual([struct.unpack_from('>II', pairs, 16 * k) for k in range(len(pairs) // 16)],
                         [(400, 0), (402, 0)])
        self.assertEqual([struct.unpack_from('>II', e, 0x34) for e in entries], [(1, 1), (0, 0), (1, 1)])
        self.assertEqual([struct.unpack_from('>II', links, 52 * k) for k in range(len(links) // 52)],
                         [(400, 402), (402, 400)])
        self.assertEqual(rest, b'REST')
        # a piece without extra bones has no spring file
        bare = wardrobe.piece_skeleton(bon, [mesh('abc_dep0', tri, [(0, 1, 2)], 1)], wardrobe.spring_links(mop))
        self.assertIsNone(wardrobe.piece_springs(mop, bon, bare))

    def test_whose_wardrobe(self):
        import types
        tekken7 = dict(TEKKEN7={}, DONOR='lar', CODE='abc', NAME='A')
        self.assertEqual(wardrobe.source_of(types.SimpleNamespace(**tekken7)), 'lar')
        self.assertEqual(wardrobe.source_of(types.SimpleNamespace(WARDROBE=True, **tekken7)), 'lar')
        self.assertIsNone(wardrobe.source_of(types.SimpleNamespace(WARDROBE=False, **tekken7)))
        tekken8 = dict(TEKKEN8_CODE='xyz', DONOR='jun', CODE='abd', NAME='B')
        self.assertEqual(wardrobe.source_of(types.SimpleNamespace(**tekken8)), 'jun')       # (whichever game)
        self.assertIsNone(wardrobe.source_of(types.SimpleNamespace(WARDROBE=False, **tekken8)))
        self.assertIsNone(wardrobe.source_of(types.SimpleNamespace(WITHOUT_OWN_MOVESET=True, **tekken8)))   # (a stand-in)
        # a Tekken 8 costume is one mesh: made two pieces; a Tekken 7 preset in one piece stays whole
        self.assertTrue(wardrobe.splits(types.SimpleNamespace(**tekken8)))
        self.assertFalse(wardrobe.splits(types.SimpleNamespace(**tekken7)))

    BODY = [('HARA', -1, (0, 1000, 0)), ('MUNE1_jnt', 0, (0, 1200, 0)), ('KOSHI_jnt', 0, (0, 950, 0)),
            ('MOMO_R_jnt', 2, (-90, 900, 0)), ('OPT400_tail', 1, (0, 800, -100))]

    @staticmethod
    def triangles(m):
        return sum(len(nud.strip_to_tris(p['indices'])) for p in m['polys'])

    def test_a_one_piece_body_is_parted_only_where_bare_skin_runs_through_the_waist(self):
        bon = skeleton(self.BODY)
        # bare skin from the chest to the thighs: three rings, the middle one half the trunk's, half the hips'
        n = 8
        points = np.concatenate([ring(100, y, n) for y in (1300, 1000, 700)])
        tris = []
        for row in range(2):
            for i in range(n):
                j = (i + 1) % n
                tris += [(row * n + i, row * n + j, row * n + n + i), (row * n + j, row * n + n + j, row * n + n + i)]
        skin = mesh('abc_bdf_1p', points, tris, [1] * n + [1] * n + [3] * n)
        skin['polys'][0]['verts']['bones'][n:2 * n, 1] = 3
        skin['polys'][0]['verts']['w'][n:2 * n, :2] = (0.6, 0.4)
        upper, lower = wardrobe.split_piece(skin, bon)
        self.assertEqual((self.triangles(upper), self.triangles(lower)), (2 * n, 2 * n))
        self.assertLess(lower['polys'][0]['verts']['pos'][:, 1].max(), 1001)
        self.assertGreater(upper['polys'][0]['verts']['pos'][:, 1].min(), 999)
        self.assertEqual(upper['name'], 'abc_bdf_1p')
        self.assertEqual(len(skin['polys'][0]['verts']), 3 * n)                # (the body's mesh is left as it was)
        # the same shape as cloth is one thing: it goes whole to the half that holds most of it
        cloth = mesh('abc_bdf_1p', points, tris, [1] * n + [1] * n + [3] * n, flags=0x24600099)
        upper, lower = wardrobe.split_piece(cloth, bon)
        self.assertEqual(self.triangles(upper), 4 * n)
        self.assertIsNone(lower)

    def test_bare_skin_above_the_waistband_is_the_tops(self):
        bon = skeleton(self.BODY)
        # a bare belly bound to the hips from 900 to 1100, over shorts that end at 1000 (lower in front: 960)
        n = 8
        heights = (1100, 1050, 1000, 950, 900)
        points = np.concatenate([ring(100, y, n) for y in heights])
        tris = []
        for row in range(len(heights) - 1):
            for i in range(n):
                j = (i + 1) % n
                tris += [(row * n + i, row * n + j, row * n + n + i), (row * n + j, row * n + n + j, row * n + n + i)]
        body = mesh('abc_bdf_1p', points, tris, [2] * len(points))
        band = ring(110, 1000, n)
        band[0, 1] = 960                                           # (ring: its first point is in front)
        shorts = np.concatenate([band, ring(110, 800, n)])
        cloth = [(i, (i + 1) % n, n + i) for i in range(n)] + [((i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        body['polys'].append(mesh('x', shorts, cloth, [2] * n + [3] * n, flags=0x24600099)['polys'][0])
        upper, lower = wardrobe.split_piece(body, bon)
        self.assertEqual([p['materials'][0]['flags'] for p in upper['polys']], [wardrobe.SKIN_FLAGS])
        up, low = upper['polys'][0]['verts']['pos'], lower['polys'][0]['verts']['pos']
        self.assertEqual(self.triangles(upper) + self.triangles(lower), len(tris) + len(cloth))
        self.assertEqual(up[:, 1].min(), 950)                      # (in front down to under the dip, no further)
        self.assertEqual(up[up[:, 2] < 0][:, 1].min(), 1000)       # ... and behind to the band
        self.assertLessEqual(low[:, 1].max(), 1000)                # none of the lower piece's skin above the band
        # without cloth of the lower body the hips' skin stays the lower piece's, whole
        bare = mesh('abc_bdf_1p', points, tris, [2] * len(points))
        upper, lower = wardrobe.split_piece(bare, bon)
        self.assertIsNone(upper)
        self.assertEqual(self.triangles(lower), len(tris))

    def test_the_sources_body_and_garments_follow_a_bare_waist(self):
        bon = skeleton([('HARA', -1, (0, 1000, 0)), ('KOSHI_jnt', 0, (0, 1100, 0)), ('MOMO_R_jnt', 1, (-90, 950, 0)),
                        ('MUNE2_jnt', 0, (0, 1250, 0)), ('KUBI_jnt', 3, (0, 1450, 0)),
                        ('SAKOTSU_R_jnt', 3, (-90, 1440, 0)), ('KATA_R_jnt', 5, (-150, 1430, 0))])

        def tube(radius, heights, centre=(0.0, 0.0), n=24):
            return np.concatenate([ring(radius, y, n, centre) for y in heights])
        heights = range(1000, 1241, 20)
        # the fighter's bare waist: 10 mm thicker than the source's and 20 mm further forward
        own = [(tube(110, heights, (0.0, 20.0)), np.zeros(24 * len(heights)))]
        cut = [(tube(100, range(900, 1500, 20)), np.zeros(24 * 30))]
        waist = wardrobe.Waist(bon, own, cut)
        self.assertTrue(waist.found)
        front, back, side = np.array([[0.0, 1100, 105]]), np.array([[0.0, 1100, -105]]), np.array([[105.0, 1100, 0]])
        np.testing.assert_allclose(waist.moves(front, np.zeros(1))[0], (0, 0, 30), atol=3)   # (a garment 5 mm off the
        np.testing.assert_allclose(waist.moves(back, np.zeros(1))[0], (0, 0, 10), atol=3)    #  skin stays 5 mm off it)
        self.assertAlmostEqual(waist.moves(side, np.zeros(1))[0][0], np.sqrt(110 ** 2 - 20 ** 2) - 100, delta=3)
        # an arm beside the waist stays; the shape has run out at the neck's root and well under the bare skin
        np.testing.assert_allclose(waist.moves(front, np.ones(1))[0], (0, 0, 0), atol=1e-9)
        for y in (1450, 1500, 880, 800):
            np.testing.assert_allclose(waist.moves(np.array([[0.0, y, 105]]), np.zeros(1))[0], (0, 0, 0), atol=1e-9)
        half = waist.moves(np.array([[0.0, 1345, 105]]), np.zeros(1))[0][2]
        self.assertTrue(10 < half < 20)                                         # ... evenly: half way, half of it
        # a model is moved through its own skeleton's arms
        shirt = mesh('shirt', [(0, 1100, 105), (0, 1100, -105), (-200, 1100, 0)], [(0, 1, 2)], [1, 1, 6])
        waist.fit(dict(meshes=[shirt], sphere=(0, 0, 0, 1)), bon)
        np.testing.assert_allclose(shirt['polys'][0]['verts']['pos'][:, 2], (135, -95, 0), atol=3)
        np.testing.assert_allclose(shirt['polys'][0]['verts']['pos'][2], (-200, 1100, 0), atol=1e-4)
        # skin bared in front only (an open jacket) is no waist to follow
        open_front = [(p[p[:, 2] > 100], a[p[:, 2] > 100]) for p, a in own]
        self.assertFalse(wardrobe.Waist(bon, open_front, cut).found)
        self.assertFalse(wardrobe.Waist(bon, [], cut).found)

    def test_a_coat_keeps_its_tails_and_a_layer_goes_with_what_it_is_drawn_over(self):
        bon = skeleton(self.BODY)
        # a coat: chest (the trunk's) with a tail on a bone of its own under the trunk and a hem bound to the hips
        points = [(0, 1300, 0), (100, 1300, 0), (0, 1200, 0), (100, 1200, 0), (0, 1000, 0), (100, 1000, 0),
                  (0, 700, 0), (100, 700, 0)]
        tris = [(0, 1, 2), (1, 3, 2), (2, 3, 4), (3, 5, 4), (4, 5, 6), (5, 7, 6)]
        coat = mesh('abc_bdf_1p', points, tris, [1, 1, 1, 1, 1, 1, 3, 3], flags=0x24600099)
        boot = mesh('x', [(0, 100, 0), (50, 100, 0), (0, 0, 0)], [(0, 1, 2)], 3, flags=0x24600099)['polys'][0]
        # its 2P colour layer over the hem only: by itself the hips', but drawn over the coat
        layer = mesh('x', points[4:], [(0, 1, 2), (1, 3, 2)], [1, 1, 3, 3], flags=0x24400099)['polys'][0]
        coat['polys'] += [boot, layer]
        upper, lower = wardrobe.split_piece(coat, bon)
        self.assertEqual([len(nud.strip_to_tris(p['indices'])) for p in upper['polys']], [6, 2])
        self.assertEqual([p['materials'][0]['flags'] for p in upper['polys']], [0x24600099, 0x24400099])
        self.assertEqual(self.triangles(lower), 1)                               # the boot
        # ... and the body gives way as two pieces when asked to part it
        body = dict(meshes=[coat, mesh('abc_fac', points[:3], [(0, 1, 2)], 0)])
        self.assertEqual(wardrobe.own_pieces(body, 'abc', bon), {})
        found = wardrobe.own_pieces(body, 'abc', bon, split=True)
        self.assertEqual(sorted(found), sorted([wardrobe.UPPER, wardrobe.LOWER]))
        self.assertEqual(wardrobe.outfit_meshes(body, 'abc', bon), [coat])

    def test_which_items_are_fitted(self):
        def inst(attrs, kind='clothes'):
            return el('Instance', [], [el('Data', [('EquipType', kind)]),
                                       el('Model', [('section', 'A')], [el('Group', attrs)])])
        self.assertTrue(wardrobe.fits(inst([('mi', '1'), ('ti', '2'), ('bci', '116')])))
        self.assertTrue(wardrobe.fits(el('Instance', [], [el('Model', [('section', 'A')])])))
        self.assertTrue(wardrobe.fits(inst([('mi', '1'), ('bi', '2')])))                  # bones of its own
        self.assertTrue(wardrobe.fits(inst([('mi', '1'), ('tci', '2'), ('bi', '3'), ('pi', '4')])))   # and springs
        self.assertFalse(wardrobe.fits(inst([('mi', '1'), ('gi', '4')])))
        swaying = inst([('mi', '1'), ('tci', '2'), ('bi', '3'), ('pi', '4')])
        still = wardrobe.static(swaying)            # worn without its springs: its bones held by their joints
        self.assertEqual(itemdb.groups(still)[0]['attrs'], [('mi', '1'), ('tci', '2'), ('bi', '3')])
        self.assertEqual(len(itemdb.groups(swaying)[0]['attrs']), 4)
        # the source's own costume: its Instances are the ones the fighter's own outfit is worn as
        self.assertFalse(wardrobe.fits(inst([('mi', '1'), ('ti', '2')], kind=itemdb.DEFAULT_COSTUME)))

    def test_a_garments_skeleton_takes_the_fighters_joints_and_keeps_its_own_bones(self):
        part = skeleton([('HARA', -1, (0, 1000, 0)), ('KUBI_jnt', 0, (0, 1400, 0)), ('ATAMA_jnt', 1, (0, 1500, 0)),
                         ('TE_R_jnt', 0, (-700, 1400, 0)), ('OPT250_hem', 0, (0, 900, 30))], prefix='par:cha:')
        made = wardrobe.part_skeleton(part, TARGET)
        np.testing.assert_allclose(made['t'][:4], TARGET['t'][:4])
        np.testing.assert_allclose(made['t'][4], (0, -100, 30))        # where it hangs from its joint: unchanged
        self.assertEqual(made['names'], part['names'])
        np.testing.assert_allclose(part['t'][3], (-700, 400, 0))       # (the source's is left as it was)


class Shop(unittest.TestCase):
    def setUp(self):
        sale = bxml.write([
            el('Fighter', [('id', '7')], [el('Equipment', [('Position', '1')], [
                el('Item', [('label', 'abc_shirt_set'), ('instances', '8_42_-1|9_36_-1|10_29_-1'),
                            ('colorgara', '5_0_0_91_-1|6_1_0_34_-1')]),
                el('Item', [('label', 'abc_plain'), ('instances', '12_2_-1'), ('colorgara', '')]),
                el('Item', [('label', 'abc_glasses'), ('instances', '5_253_-1'), ('colorgara', '')])])]),
            el('Fighter', [('id', '8')], [el('Equipment', [('Position', '2')], [
                el('Item', [('label', 'xyz_pants_set'), ('instances', '12_77_-1|13_66_-1'),
                            ('colorgara', '8_0_0_96_-1')])])])])
        self.archives = Archives({wardrobe.SALE_KEY: sale})

    def test_rows(self):
        rows = wardrobe.shop_rows(self.archives, ['abc_shirt_set', 'xyz_pants_set', 'nobody'])
        self.assertEqual(sorted(rows), ['abc_shirt_set', 'xyz_pants_set'])
        self.assertEqual(rows['abc_shirt_set'], dict(items=[(8, 42, -1), (9, 36, -1), (10, 29, -1)],
                                                     colours=[(51, 91), (57, 34)]))

    def test_a_fighters_outfit_rows_are_its_rows_for_the_upper_or_lower_body(self):
        self.assertEqual(wardrobe.outfit_rows(self.archives, 'abc'), ['abc_shirt_set', 'abc_plain'])
        self.assertEqual(wardrobe.outfit_rows(self.archives, 'xyz'), ['xyz_pants_set'])
        self.assertEqual(wardrobe.outfit_rows(self.archives, 'ab'), [])
        self.assertEqual(wardrobe.outfit_rows(Archives({}), 'abc'), [])

    def test_record_text(self):
        rows = wardrobe.shop_rows(self.archives, ['abc_shirt_set', 'xyz_pants_set'])
        text = wardrobe.record_text([rows['abc_shirt_set'], rows['xyz_pants_set']], [(0, 5), (8, 1), (12, 2)])
        self.assertEqual(text, '0=5,8=42,9=36,10=29,12=77,13=66,c51=91,c57=34,c66=96')


class ShopList(unittest.TestCase):
    """The pack's own shop list for CUSTOMIZE mode (made-up fighters, rows and items)."""

    def setUp(self):
        def item(label, instances, **more):
            return el('Item', [('id', str(100 + len(label))), ('label', label), ('price', '500'),
                               ('instances', instances)] + sorted(more.items()))
        sale = bxml.write([
            el('Fighter', [('id', '8')], [el('Equipment', [('Position', '7')], [item('xyz_coat', '8_42_-1')])]),
            el('Fighter', [('id', '7')], [
                el('Equipment', [('Position', '7')], [item('abc_shirt_set', '8_42_-1|9_36_-1|10_29_-1'),
                                                      item('abc_coat', '8_53_-1|10_29_-1'),
                                                      item('abc_top', '8_1_-1', defitem='True')]),
                el('Equipment', [('Position', '4')], [item('abc_cmn_glasses', '5_253_-1')]),
                el('Equipment', [('Position', '9')], [item('abc_cmn_bag', '15_300_2'), item('abc_nothing', '')])])])
        self.archives = Archives({wardrobe.SALE_KEY: sale})

    @staticmethod
    def database(indices):
        return bxml.write([el('InstanceInfo', [], [el('Instance', [('label', 'i%d' % i), ('index', str(i))])
                                                    for i in indices]), el('OffsetInfo')])

    def labels(self, shop):
        fighter, = bxml.parse(shop)
        return dict(fighter['attrs']), [(dict(e['attrs'])['Position'], [dict(i['attrs'])['label'] for i in e['children']])
                                        for e in fighter['children']]

    def test_the_sources_rows_whose_every_item_the_database_has_under_the_sources_element(self):
        shop = wardrobe.shop_list(self.archives, 'abc', self.database([1, 2, 5, 29, 36, 42, 253]))
        attrs, rows = self.labels(shop)
        self.assertEqual(attrs, {'id': '7'})
        # (the coat names item 53, the bag 300: not listed; a category with nothing left is not there)
        self.assertEqual(rows, [('7', ['abc_shirt_set', 'abc_top']), ('4', ['abc_cmn_glasses'])])
        item = bxml.parse(shop)[0]['children'][0]['children'][0]
        self.assertEqual(dict(item['attrs'])['id'], str(100 + len('abc_shirt_set')))     # (the source's item id)
        self.assertEqual(dict(item['attrs'])['price'], '500')

    def test_no_list_when_nothing_fits_or_the_game_has_none(self):
        self.assertIsNone(wardrobe.shop_list(self.archives, 'abc', self.database([7, 8])))
        self.assertIsNone(wardrobe.shop_list(self.archives, 'nobody', self.database([1, 42])))
        self.assertIsNone(wardrobe.shop_list(Archives({}), 'abc', self.database([1, 42])))


class Database(unittest.TestCase):
    def test_own_pieces_become_the_default_items_parts_and_garments_keep_their_numbers(self):
        def instance(label, index, pos, groups=(), kind=itemdb.DEFAULT_COSTUME):
            return el('Instance', [('label', label), ('index', str(index))],
                      [el('Data', [('Name', label), ('EquipPos', pos), ('EquipType', kind)]),
                       el('Model', [('section', 'A')], groups), el('Model', [('section', 'B')])])
        offset = el('Offset', [('Name', 'hip'), ('Path', 'lower/hip')], [el('OffsetA', [('Joint', 'KOSHI')])])
        garment = instance('w_upb_shirt', 42, wardrobe.UPPER, [el('Group', [('mi', '90'), ('tci', '7'), ('bci', '600')], [
            el('Offset', [('Path', 'lower/hip'), ('Name', 'hip')])])], kind='clothes')
        source = [el('InstanceInfo', [], [garment]), el('OffsetInfo', [], [offset])]
        db = bxml.write([el('InstanceInfo', [], [instance('d_upb_1p', 1, wardrobe.UPPER), instance('d_lob_1p', 2, wardrobe.LOWER),
                                                  instance('d_hed_1p', 5, 'head')]), el('OffsetInfo')])
        own = {wardrobe.UPPER: [('mi', '900'), ('ti', '900'), ('bi', '900'), ('Filename', 'abc/abc_bdu_1p.nud')]}
        made = wardrobe_db = itemdb.with_wardrobe(db, source, [garment], own)
        info, offsets = bxml.parse(made)[:2]
        by = {dict(i['attrs'])['index']: i for i in info['children']}
        self.assertEqual([dict(g['attrs']).get('mi') for g in itemdb.groups(by['1'])], ['900'])
        self.assertEqual(itemdb.groups(by['2']), [])
        self.assertEqual(dict(itemdb.groups(by['42'])[0]['attrs'])['mi'], '90')
        self.assertEqual(len(offsets['children']), 1)
        again = itemdb.with_wardrobe(wardrobe_db, source, [garment], own)                      # done once
        self.assertEqual(bxml.parse(again), bxml.parse(made))


if __name__ == '__main__':
    unittest.main()
