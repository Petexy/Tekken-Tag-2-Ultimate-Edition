"""The item database's worn items (convert/itemdb.py): a made-up donor database."""
import unittest

from ttt2char.convert import itemdb
from ttt2char.ttt2 import bxml


def el(tag, attrs=(), children=()):
    return dict(tag=tag, attrs=list(attrs), children=list(children))


def instance(label, index, equip_type, groups=(), extra=()):
    return el('Instance', [('label', label), ('index', str(index))],
              [el('Data', [('Name', label), ('EquipType', equip_type)]),
               el('Model', [('section', 'A')], groups), el('Model', [('section', 'B')])] + list(extra))


def group(attrs, offset=None):
    return el('Group', list(attrs) + [('Filename', 'x.nud')],
              [el('Offset', [('Path', offset[1]), ('Name', offset[0]), ('Condition', 'Normal')])] if offset else [])


def offset(name, path, joint):
    part = [('Joint', joint), ('tx', '1.5'), ('rw', '0.4867402')]
    return el('Offset', [('Name', name), ('Path', path)], [el('OffsetA', part), el('OffsetB', part)])


def donor():
    return bxml.write([
        el('InstanceInfo', [], [
            instance('abc_upb_1p', 1, itemdb.DEFAULT_COSTUME, [group([('mi', '20'), ('tci', '7')])],
                     [el('ModelBConditions', [], [el('ModelBCondition', [('Name', 'x')])])]),
            instance('cmn_glasses', 253, 'shared', [group([('mci', '297'), ('tci', '403')], ('eyes', 'head/glasses'))]),
            instance('cmn_tail', 300, 'shared', [group([('mci', '5'), ('bci', '6'), ('pci', '7')], ('hip', 'lower/hip'))]),
            instance('cmn_flag', 301, 'shared', [group([('mci', '8'), ('ci', '13')], ('back', 'upper/back'))]),
            instance('abc_hat', 302, 'shared', [group([('mi', '59'), ('tci', '9')], ('top', 'head/top'))]),
            instance('cmn_mixed', 303, 'shared', [group([('mci', '1')]), group([('mci', '2'), ('ei', '3')])]),
            instance('cmn_aura', 304, 'effect'),
        ]),
        el('OffsetInfo', [], [offset('eyes', 'head/glasses', 'ATAMA_jnt_assist'), offset('eyes', 'head/other', 'KUBI'),
                              offset('hip', 'lower/hip', 'KOSHI'), offset('back', 'upper/back', 'MUNE2'),
                              offset('top', 'head/top', 'ATAMA_jnt')]),
    ])


def labels(db):
    return [dict(i['attrs'])['label'] for i in bxml.parse(db)[0]['children']]


def find(db, label):
    return next(i for i in bxml.parse(db)[0]['children'] if dict(i['attrs'])['label'] == label)


class CommonOnly(unittest.TestCase):
    def test_common_packs_only(self):
        info = bxml.parse(donor())[0]['children']
        got = {dict(i['attrs'])['label']: itemdb.common_only(i) for i in info}
        self.assertEqual(got, {'abc_upb_1p': False, 'cmn_glasses': True, 'cmn_tail': True, 'cmn_flag': True,
                               'abc_hat': False, 'cmn_mixed': False, 'cmn_aura': False})

    def test_every_own_pack_attribute_counts(self):
        for name in ('mi', 'ti', 'bi', 'pi', 'gi', 'hi', 'ei', 'ni'):
            self.assertFalse(itemdb.common_only(instance('x', 1, 'shared', [group([('mci', '1'), (name, '2')])])), name)


class BodyOnly(unittest.TestCase):
    def test_no_items_is_the_body_alone(self):
        db = itemdb.body_only(donor(), items=())
        self.assertEqual(labels(db), ['abc_upb_1p'])
        self.assertEqual(bxml.parse(db)[1]['children'], [])
        self.assertEqual(itemdb.groups(find(db, 'abc_upb_1p')), [])      # the default costume's part list emptied

    def test_item_kept_whole_with_its_offset(self):
        db = itemdb.body_only(donor(), items=('cmn_glasses',))
        self.assertEqual(labels(db), ['abc_upb_1p', 'cmn_glasses'])
        self.assertEqual(find(db, 'cmn_glasses'), find(donor(), 'cmn_glasses'))      # label, index, Groups: unchanged
        offsets = bxml.parse(db)[1]['children']
        self.assertEqual(offsets, [o for o in bxml.parse(donor())[1]['children']
                                   if dict(o['attrs']) == {'Name': 'eyes', 'Path': 'head/glasses'}])
        self.assertEqual(dict(offsets[0]['children'][0]['attrs'])['Joint'], 'ATAMA_jnt_assist')

    def test_own_pack_items_and_unknown_labels_are_left_out(self):
        db = itemdb.body_only(donor(), items=('abc_hat', 'cmn_mixed', 'cmn_aura', 'no_such_item', 'cmn_tail'))
        self.assertEqual(labels(db), ['abc_upb_1p', 'cmn_tail'])
        self.assertEqual([dict(o['attrs'])['Name'] for o in bxml.parse(db)[1]['children']], ['hip'])

    def test_default_list_is_what_the_importer_writes(self):
        self.assertEqual(itemdb.body_only(donor()), itemdb.body_only(donor(), items=itemdb.ITEMS))

    def test_effects_still_go_into_the_effect_instance(self):
        d = bxml.parse(donor())
        d[0]['children'].append(instance(itemdb.EFFECT_INSTANCE, 333, itemdb.DEFAULT_COSTUME))
        db = itemdb.body_only(bxml.write(d), {7: [('eff_x', None)]}, items=('cmn_glasses',))
        self.assertEqual(itemdb.effect_ids(db), {7})
        self.assertIn('cmn_glasses', labels(db))


class WithItems(unittest.TestCase):
    def test_adding_to_a_made_database_gives_the_importers(self):
        items = ('cmn_glasses', 'cmn_flag')
        self.assertEqual(itemdb.with_items(itemdb.body_only(donor(), items=()), donor(), items),
                         itemdb.body_only(donor(), items=items))

    def test_twice_changes_nothing(self):
        once = itemdb.with_items(itemdb.body_only(donor(), items=()), donor(), ('cmn_glasses', 'cmn_tail'))
        self.assertEqual(itemdb.with_items(once, donor(), ('cmn_glasses', 'cmn_tail')), once)

    def test_shared_offset_copied_once(self):
        d = bxml.parse(donor())
        d[0]['children'].append(instance('cmn_glasses2', 254, 'shared', [group([('mci', '9')], ('eyes', 'head/glasses'))]))
        db = itemdb.body_only(bxml.write(d), items=('cmn_glasses', 'cmn_glasses2'))
        self.assertEqual(len(bxml.parse(db)[1]['children']), 1)


if __name__ == '__main__':
    unittest.main()
