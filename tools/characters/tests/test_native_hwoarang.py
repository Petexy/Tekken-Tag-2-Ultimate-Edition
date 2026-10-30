"""Native replacement keeps group offsets, tag routes and roster identity separate."""
import unittest
import copy
import collections
from types import SimpleNamespace
from ttt2char.native_hwoarang import redirect_native_references, tornado_moves, restore_native_jfsr_sparks, filtered_conditional_props, validate_conditional_props, native_voice_categories, restore_native_hunting_hawk_air, Replacement, KEYS, ROW
from ttt2char.convert import idmaps as M


class NativeHwoarang(unittest.TestCase):
    def test_rfs_df4_extends_only_private_capsule_and_tag_twin(self):
        from ttt2char.native_hwoarang import extend_rfs_df4_collision, BOUND_FINISHERS
        self.assertEqual(BOUND_FINISHERS['#1766'], (0x893d3e73, 9, 13))
        names = ['Hw_#1878', 'Hw_#1878T', 'Hw_#1878T2', 'Hw_#18780', 'Hw_#1878Tfoo']
        rows = [dict(hitbox=bytes((16, 0, 38, 15)), first_active=20, last_active=21, hitlevel=99) for _ in names]
        c = SimpleNamespace(T={'moves': rows}, move_name=lambda i: names[i], stats=collections.Counter())
        extend_rfs_df4_collision(c)
        for i, row in enumerate(rows):
            self.assertEqual(row['hitbox'], bytes((16, 0, 70 if i < 3 else 38, 15)))
            self.assertEqual((row['first_active'], row['last_active'], row['hitlevel']), (20, 21, 99))
        self.assertEqual(sum(c.stats.values()), 3)

    def test_flamingo_uf4_matches_hits_but_retains_block_damage_and_timing(self):
        from ttt2char.native_hwoarang import match_flamingo_uf4_reactions
        from ttt2char.convert import tagsystem as T
        requirements = [dict(condition=T.AIR,param=0),dict(condition=T.TT_END,param=0)]
        reactions = [dict(default=30,block=10,crouch_block=11,pb_block=12),
                     dict(default=40,block=20,crouch_block=21,pb_block=22),
                     dict(default=50,block=60,crouch_block=61,pb_block=62)]
        tables = dict(requirements=requirements,reactions=reactions,
                      hit_conditions=[dict(req=0,damage=20,reactions=0),dict(req=1,damage=20,reactions=1),
                                      dict(req=0,damage=25,reactions=2),dict(req=1,damage=25,reactions=2)],
                      moves=[dict(hit_condition=0,first_active=17),dict(hit_condition=2,first_active=19)])
        source = SimpleNamespace(tables={'moves':[dict(name_key=0x6250d9d0),dict(name_key=0x26ac3cae)]},
                                 name_lengths=lambda i: ((9,21),(9,18))[i])
        c = SimpleNamespace(T=tables,k=source,kn={'#1865':0,'#1906':1},newidx={0:0,1:1},
                            move_name=lambda i: ('Hw_#1865','Hw_#1906')[i],stats=collections.Counter())
        def add(table,row):
            index=len(tables[table]);tables[table].append(row);return index
        c.add=add
        match_flamingo_uf4_reactions(c)
        hits=T.hits(tables,tables['moves'][1]['hit_condition'])
        self.assertEqual([tables['reactions'][h['reactions']]['default'] for h in hits],[30,40])
        self.assertEqual([h['damage'] for h in hits],[25,25])
        for hit in hits:
            reaction=tables['reactions'][hit['reactions']]
            self.assertEqual((reaction['block'],reaction['crouch_block'],reaction['pb_block']),(60,61,62))
        self.assertEqual(tables['moves'][1]['first_active'],19)
        self.assertEqual(tables['moves'][0]['hit_condition'],0)

    def test_assist_chase_is_restored_once_without_changing_attacks(self):
        from ttt2char.native_hwoarang import restore_native_assist_follow
        chase=dict(direction=0,button=0,move_id=94,req=8,extradata=20,win_start=2,win_end=32767,start_frame=2,option=0)
        end=dict(direction=M.LIST_END,button=0,move_id=0,req=0)
        attack=dict(direction=0x40,button=0x40000008,move_id=15,req=0)
        native={'moves':[dict(cancel=0),dict(cancel=0)],'cancels':[chase,end]}
        tables={'moves':[dict(cancel=0),dict(cancel=2)],'cancels':[dict(chase),dict(end),dict(attack),dict(end)]}
        c=SimpleNamespace(d=SimpleNamespace(tables=native),dn={'DA_KamDash':94,'Hw_sKAM00_':0,'Hw_sKAMR00_':1},
                          T=tables,kn={'Hw_sKAM00_':0,'Hw_sKAMR00_':1},newidx={0:0,1:1},stats=collections.Counter())
        restore_native_assist_follow(c)
        from ttt2char.convert import tagsystem as T
        rows=T.cancels(tables,tables['moves'][1]['cancel'])
        self.assertEqual(rows,[chase,attack,end])
        first=tables['moves'][1]['cancel']
        restore_native_assist_follow(c)
        self.assertEqual(tables['moves'][1]['cancel'],first)
        self.assertEqual(sum(c.stats.values()),1)

    def test_only_move_references_are_redirected(self):
        rows = [{'direction': 0, 'move_id': 3},
                {'direction': M.GROUP, 'move_id': 3},
                {'direction': M.LIST_END, 'move_id': 3},
                {'direction': 0, 'move_id': 0x8001}]
        groups = [{'direction': 0, 'move_id': 3}, {'direction': M.GROUP_END, 'move_id': 3}]
        tables = {'cancels': rows, 'group_cancels': groups,
                  'moves': [{'transition': 3}, {'transition': 0x8001}],
                  'reactions': [{'default': 3}]}
        aliases = [0, 3, 0x8001]
        self.assertEqual(redirect_native_references(tables, aliases, {3: 1500}), [0, 1500, 0x8001])
        self.assertEqual([r['move_id'] for r in rows], [1500, 3, 3, 0x8001])
        self.assertEqual([r['move_id'] for r in groups], [1500, 3])
        self.assertEqual([r['transition'] for r in tables['moves']], [1500, 0x8001])
        self.assertEqual(tables['reactions'], [{'default': 3}])
        self.assertEqual(aliases, [0, 3, 0x8001])

    def test_tornado_detection_uses_source_requirements_not_guessed_move_names(self):
        from ttt2char.tekken8.motbin import Moveset8
        k = Moveset8()
        k.tables = {
            'moves': [{'hit_condition': 0}, {'hit_condition': 2}, {'hit_condition': None}],
            'requirements': [{'condition': 724, 'param': 0}, {'condition': 1100, 'param': 0},
                             {'condition': 723, 'param': 0}, {'condition': 1100, 'param': 0},
                             {'condition': 1100, 'param': 0}],
            'hit_conditions': [{'req': 0, 'damage': 20, 'reactions': 0},
                               {'req': 4, 'damage': 20, 'reactions': 0},
                               {'req': 2, 'damage': 20, 'reactions': 0},
                               {'req': 4, 'damage': 20, 'reactions': 0}]}
        self.assertEqual(tornado_moves(k), {0})

    def test_native_sparks_only_change_just_frame_sky_rocket(self):
        from ttt2char.convert import tagsystem as T
        end = dict(frame=0, id=0, value=0)
        original = [dict(frame=1, id=0x8192, value=1),
                    dict(frame=11, id=0x801f, value=0x0e63),
                    dict(frame=1, id=0x8100, value=7), end]
        native = [dict(frame=32769, id=0x8192, value=1),
                  dict(frame=14, id=0x8031, value=0x0f14),
                  dict(frame=14, id=0x803e, value=0x0f10), end]
        tables = {'moves': [{'extraprops': 0}, {'extraprops': 0}],
                  'extra_move_properties': copy.deepcopy(original)}
        c = SimpleNamespace(T=tables, kn={'Hw_agerkFAST': 8}, newidx={8: 0},
                            dn={'Hw_agerkFAST': 0}, stats=collections.Counter(),
                            d=SimpleNamespace(tables={'moves': [{'extraprops': 0}],
                                                     'extra_move_properties': native}))
        restore_native_jfsr_sparks(c)
        fixed = T.props(c.T, c.T['moves'][0]['extraprops'])
        self.assertIn(dict(frame=14, id=0x8031, value=0x0f14), fixed)
        self.assertIn(dict(frame=1, id=0x8100, value=7), fixed)
        self.assertFalse(any(p['id']==0x801f and p['value']&255==99 for p in fixed))
        self.assertEqual(T.props(c.T, c.T['moves'][1]['extraprops']), original[:-1])

    def test_empty_conditional_property_lists_are_null(self):
        tables = {'move_end_props': [{'req': 0, 'id': 690, 'value': 0}]}
        self.assertIsNone(filtered_conditional_props(tables, 'move_end_props', None))
        self.assertIsNone(filtered_conditional_props(tables, 'move_end_props', 0))
        self.assertEqual(len(tables['move_end_props']), 1)

    def test_conditional_properties_keep_requirement_links_and_690_terminator(self):
        tables = {'move_end_props': [{'req': 3, 'id': 0x8001, 'value': 2},
                                    {'req': 0, 'id': 0x8193, 'value': 1},
                                    {'req': 0, 'id': 690, 'value': 0}]}
        start = filtered_conditional_props(tables, 'move_end_props', 0)
        self.assertEqual(tables['move_end_props'][start:],
                         [{'req': 3, 'id': 0x8001, 'value': 2}, {'req': 0, 'id': 690, 'value': 0}])

    def test_bad_zero_terminator_is_rejected_before_install(self):
        from ttt2char import InputError
        tables = {'moves': [{'begin_props': None, 'end_props': 0}],
                  'move_begin_props': [], 'move_end_props': [{'req': None, 'id': 0, 'value': 0}],
                  'requirements': [{'condition': 690, 'param': 0}]}
        with self.assertRaisesRegex(InputError, 'invalid requirement pointer'):
            validate_conditional_props(tables)
        tables['move_end_props'] = [{'req': 0, 'id': 690, 'value': 0}]
        validate_conditional_props(tables)

    def test_voice_categories_use_native_list_indices_not_bank_tone_ids(self):
        vlist = [(0x20, 70), (0x20, 90), (0x40, 120), (0x40, 140)]
        kinds = {70: ('atk','s'), 90: ('atk','l'), 120: ('dmg','s'), 140: ('dmg','l')}
        voices, shouts, damage = native_voice_categories(vlist, kinds.__getitem__)
        self.assertEqual((shouts, damage), (2,2))
        self.assertEqual(voices[17,0], [0x02000000])
        self.assertEqual(voices[17,2], [0x02000001])
        self.assertEqual(voices[17,3], [0x03000001])
        self.assertEqual(voices[17,4], [0x03000000])

    def test_t8_mute_does_not_silence_native_automatic_shouts(self):
        from ttt2char.tekken8.motbin import Moveset8
        from ttt2char.convert import moveset
        from ttt2char.convert import tagsystem as T
        k = Moveset8()
        k.tables = {'voiceclips': [{'value': moveset.UNSAID8}, {'value': 0xffffffff},
                                  {'value': moveset.UNSAID8}, {'value': 0x02000003}, {'value': 0xffffffff}]}
        c = SimpleNamespace(k=k, T={'voiceclips': []}, donor_clips={0x02000003}, own_voice=lambda v: False)
        self.assertIsNone(Replacement.conv_voiceclips(c,0))
        start = Replacement.conv_voiceclips(c,2)
        self.assertEqual(T.voices(c.T,start), [0x02000003,0xffffffff])

    def test_hunting_hawk_native_air_reaction_covers_tag_twins_only(self):
        from ttt2char.convert import tagsystem as T
        reqs = [{'condition': flag, 'param': 0} for flag in (466,690,467,690,468,690,690)]
        original = [dict(req=0,damage=20,reactions=0), dict(req=2,damage=20,reactions=0),
                    dict(req=4,damage=20,reactions=0), dict(req=6,damage=20,reactions=0)]
        names = ['Hw_#1529','Hw_#1538','Hw_#1529T','Hw_#1538T2','OtherAttack']
        tables = {'moves': [dict(hit_condition=0) for name in names],
                  'requirements': reqs, 'reactions': [{'default': 1}],
                  'hit_conditions': copy.deepcopy(original)}
        native = {'requirements': reqs, 'moves': [dict(hit_condition=0)],
                  'hit_conditions': [dict(req=0,damage=25,reactions=0), dict(req=6,damage=25,reactions=0)],
                  'reactions': [{'default': 7, 'crouch': 11}]}
        c = SimpleNamespace(T=tables, d=SimpleNamespace(tables=native), dn={'Hw_rsk02': 0},
                            stats=collections.Counter(), move_name=lambda i:names[i])
        def add(table,row):
            index=len(tables[table]);tables[table].append(row);return index
        c.add=add
        restore_native_hunting_hawk_air(c)
        for move in tables['moves'][:4]:
            hits=T.hits(tables,move['hit_condition'])
            self.assertEqual(tables['reactions'][hits[0]['reactions']],native['reactions'][0])
            self.assertEqual([hit['damage'] for hit in hits],[20]*4)
            self.assertEqual([hit['reactions'] for hit in hits[1:]],[0,0,0])
        self.assertEqual(T.hits(tables,tables['moves'][4]['hit_condition']),original)

    def test_no_new_roster_slot_or_model_keys(self):
        self.assertEqual(ROW, 6)
        self.assertEqual(KEYS, (0xc5b3cee7, 0xaadc2a27, 0x776053e5))


if __name__ == '__main__':
    unittest.main()
