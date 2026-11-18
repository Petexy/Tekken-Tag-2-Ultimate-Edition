"""The game's garments fitted to an added fighter (convert/wardrobe.py): made-up skeletons, meshes and lists."""
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
