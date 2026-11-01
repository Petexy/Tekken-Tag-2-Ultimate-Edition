"""Recovery recipes retain native equipment IDs and isolate swimsuit packs."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ttt2char import swimsuits
from ttt2char.ttt2 import bxml


def item(label, position, default=True, model='old'):
    return dict(tag='Instance', attrs=[('label', label), ('index', '17')], children=[
        dict(tag='Data', attrs=[('EquipPos', position), ('EquipType', swimsuits.DEFAULT if default else 'DLC')], children=[]),
        dict(tag='Model', attrs=[('section', 'A')], children=[
            dict(tag='Group', attrs=[('Filename', model)], children=[])]),
        dict(tag='ModelBConditions', attrs=[], children=[]),
    ])


def database(items):
    return bxml.write([dict(tag='InstanceInfo', attrs=[], children=items),
                       dict(tag='OffsetInfo', attrs=[], children=[])])


class Swimsuits(unittest.TestCase):
    def test_catalog_namespace_and_registry(self):
        self.assertEqual(len(swimsuits.PROFILES), 45)
        bodies = [swimsuits.body_code(p, i) for p in swimsuits.PROFILES for i in range(len(p['items']))]
        self.assertEqual(len(bodies), 48)
        self.assertEqual(len(set(bodies)), 48)
        self.assertTrue(set(bodies).isdisjoint(swimsuits.BY_CODE))
        for profile in swimsuits.PROFILES:
            self.assertEqual(set(profile['textures']), {str(i) for i in range(20)})
            self.assertEqual(set(profile['parts']), {'6', '7', '8', '9', '10', '11', '12', '13', '15'})

    def test_full_body_replaces_clothing_but_keeps_head_and_equipment_ids(self):
        raw = database([item('upper', swimsuits.UPPER), item('lower', swimsuits.LOWER),
                        item('hair', swimsuits.HEAD), item('swim', '上半身下半身', False, 'swimsuit')])
        result, _ = swimsuits.recipe(raw, 'swim')
        items = bxml.parse(result)[0]['children']
        self.assertEqual([dict(i['attrs'])['label'] for i in items], ['upper', 'lower', 'hair'])
        self.assertTrue(all(dict(i['attrs'])['index'] == '17' for i in items))
        self.assertEqual(dict(items[0]['children'][1]['children'][0]['attrs'])['Filename'], 'swimsuit')
        self.assertFalse(items[1]['children'][1]['children'])
        self.assertEqual(dict(items[2]['children'][1]['children'][0]['attrs'])['Filename'], 'old')

    def test_ogre_accessory_replaces_only_head(self):
        raw = database([item('upper', swimsuits.UPPER), item('head', swimsuits.HEAD),
                        item('swim', swimsuits.HEAD, False, 'float')])
        result, _ = swimsuits.recipe(raw, 'swim')
        items = bxml.parse(result)[0]['children']
        self.assertEqual(dict(items[0]['children'][1]['children'][0]['attrs'])['Filename'], 'old')
        self.assertEqual(dict(items[1]['children'][1]['children'][0]['attrs'])['Filename'], 'float')

    def test_missing_target_slot_is_rejected(self):
        with self.assertRaisesRegex(Exception, 'equipment slot'):
            swimsuits.recipe(database([item('swim', '上半身下半身', False)]), 'swim')

    def test_remove_swimsuits_keeps_native_imports_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            native = Path(folder) / 'native/knm'
            target = Path(folder) / 'swimsuits/knm'
            native.mkdir(parents=True)
            target.mkdir(parents=True)
            (native / 'native.ini').write_text('original import')
            (target / 'native.ini').write_text('swimsuit')
            swimsuits.remove(folder, ['knm'])
            self.assertFalse(target.exists())
            self.assertEqual((native / 'native.ini').read_text(), 'original import')
            self.assertEqual(len(list(target.parent.glob('.knm-backup-*'))), 1)


if __name__ == '__main__':
    unittest.main()
