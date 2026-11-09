"""Miary Zo from Tekken 8 (PC), in her default costume.

Only names, paths and rules live here; every byte of her model, textures, pictures, voice and moveset is read from
the player's own Tekken 8 and Tekken Tag Tournament 2 files when the importer runs. Tekken 8 keeps its movesets in an
encrypted archive: the running game's own reader saves hers (tekken8/autodump.py, import_character.py runs it); the
import needs no Tekken 7.
"""
NAME = 'Miary Zo'
SHORT_NAME = 'MIARY ZO'       # her name on the 2D screens (TTT2 shows short names: KAZUYA, HEIHACHI)
TEKKEN8_ID = 40               # her FighterId in Tekken 8 (autodump.ROSTER; a DLC fighter)
TEKKEN8_CODE = 'wkz'          # her code in Tekken 8's files (Character/Item/model/unique/wkz/)
CODE = 'mzo'                  # her three-letter code in the pack (not a code TTT2 or another added fighter has)
SEX = 'female'

# The donor: a TTT2 fighter with a similar body. Its skeleton is the base of hers (the face animations set the face
# joints' absolute positions: the skeleton is the moveset's owner's), its moveset gives the generic and tag moves,
# its voice list, sound banks, item database and effects are used for her. Her materials are Jun's (TEMPLATES).
DONOR = 'jun'                 # Jun Kazama: the 139-bone female skeleton
DONOR_ROW = 42                # her motion row (data005 / data006 entry)
# her moveset: 'tekken8' = her own Tekken 8 moveset converted (the files the running game saved: importer.py)
MOVESET_SOURCE = 'tekken8'
# when her Tekken 8 moveset cannot be had: the TTT2 fighter (code, motion row) whose moveset she fights with instead
STAND_IN = ('hei', 13)        # Heihachi Mishima

# ------------------------------------------------------------------------------------------------ model
# her Tekken 8 costumes: the CustomizeSet CS_wkz_<name> (tekken8/costume.py), player 1 and player 2
# (part_weights: her face keeps its eyes and lips at 0.1, the hair its cards at 1.0, as Reina's 8.4k face; her summons'
# staffs and tail give up most: their fur and staffs are smooth; part_vertices: the horn (2213, a cone 3.5 cm wide and
# 19 cm long the passes would leave 75 of) decimated alone to 300 first (its 225 more come out of her face's 6.4k);
# part_classes: her costume is most of what is seen of her, its shape kept closer than model.PART_CLASSES': from her
# face's 8k, and its wires (the necklace's two loops, the laces round her calves) reduced as whole rings within 2 mm
# (decimate.py's Wires: collapsed, the necklace became two twisted flat ribbons 6 mm wide; 140 more vertices);
# face_classes: her face gives up more than Reina's, its skin moving by 0.4 mm at most so that what it keeps goes where
# its shape is: left to its errors the same count left lumps at the chin)
TEKKEN8 = {
    'costume': '1p',
    'costume_2p': '2p',
    'part_weights': {'fac': 0.1, 'har': 1.0, 'wpn0': 2.0, 'wpn1': 2.0},
    'part_classes': {'reach': 3.0, 'tubes': 2.0},
    'face_classes': {'skin_reach': 0.4},
    'part_vertices': {'wpn2': 300},
}
# the vertices of her model the game skins (model.VERTEX_BUDGET), her summons' meshes among them (Noctis's 56000)
VERTEX_BUDGET = 56000
# her skeleton's bones at most (convert/cloth.py SKELETON: 249 for the others, the largest skeleton of TTT2's own, a
# cautious bound, not the game's: a pack of hers with 307 bones ran a fight and a mirror match, its whole palette
# uploaded) and her cloth's (cloth.MAX_BONES 100): her body 139, her cloth at its natural spacing 124 (the hair 66,
# the waist cloths 34, the 12 strands at her shins 24), her weapons and points 21, her snakes 23
SKELETON_BONES = 307
CLOTH_BONES = 124

# ------------------------------------------------------------------------------------------------ summons
# Her summoned objects (convert/summons8.py): Tekken 8 shows them with property 0x8410, value bit 1 << n = summon n,
# as slave meshes of her rig (BI_wkz_ex0_1p's DependencySkeletalMeshSetArray), each shown by its ATH bone
# (SetWeaponMeshVisibleImpl): 1 the left staff, 2 the right one, 4 the tail, 8 the horn, 16 the snakes (another actor
# with its own skeleton and animations: SNAKES). Her moves hit from 121 (the summoned object's attack point: the tail's
# lead, the snakes' heads; never both out at once, one slot), 35 (the horn's tip) and 125 (her ground origin:
# summons8's root points).
_EX0 = '/Game/Character/Item/model/unique/wkz/extra/wkz_exp_%s/meshes/SK_CH_wkz_exp_%s_msl'
_STAFFS, _TAIL, _HORN = _EX0 % ('1p', '1p'), _EX0 % ('mtail', 'mtail'), _EX0 % ('mhorn', 'mhorn')
_TAIL_LINKS = ['ATH_tail_%02d' % n for n in range(1, 17, 2)]        # 8 links: each odd joint with the even one after
WEAPONS = [
    # the staffs, each 2.4 m in her hand (its second segment rigid with it), posed by her animations' joints
    {'mesh': _STAFFS, 'bone': 'ATH_L_spear', 'parent': 'TE_L_jnt', 'pair': 0, 'summon': 0,
     'weights': ('ATH_L_spear', 'ATH_L_spear_2nd')},
    {'mesh': _STAFFS, 'bone': 'ATH_R_spear', 'parent': 'TE_R_jnt', 'pair': 1, 'summon': 1,
     'weights': ('ATH_R_spear', 'ATH_R_spear_2nd')},
    # the snakes' heads, the point 121 hits from: in a move starting a clip of theirs the most forward head
    # (convert/snakes8.py), else (and when nothing is out: the runtime fills a slot no shown weapon wrote from the
    # first weapon with it in character.ini, whose order is the bones' numbers: a pair below the tail's puts it first)
    # its bind 1.2 m out along her right forearm
    {'bone': 'snake', 'parent': 'UDE_R_jnt', 'pair': 2, 'snakes': True, 'summon': 4,
     'at': {'along': ('UDE_R_jnt', 'TE_R_jnt'), 'cm': 120}, 'points': {0x79: ('origin', 0)}},
] + [
    # the tail: a chain of links from her hips, each under the one before
    {'mesh': _TAIL, 'bone': j, 'parent': 'KOSHI_jnt' if n == 0 else _TAIL_LINKS[n - 1], 'pair': 3 + n, 'summon': 2,
     'weights': (j, 'ATH_tail_%02d' % (2 * n + 2))} for n, j in enumerate(_TAIL_LINKS)
] + [
    # the tail's lead: its most forward joint of the second half, or its tip 13 cm past the last (9LK reaches 1.48 m
    # ahead of her; 2LK curls its tip back and hits with tail_10, 0.82 m ahead)
    {'bone': 'tail_lead', 'parent': 'KOSHI_jnt', 'pair': 11, 'summon': 2,
     'lead': ['ATH_tail_%02d' % n for n in range(8, 17)], 'tip_cm': 13, 'points': {0x79: ('origin', 0)}},
    # the horn on her forehead, rigid on her head; its tip hits as 35
    {'mesh': _HORN, 'bone': 'horn', 'joint': 'Head', 'parent': 'ATAMA_jnt', 'summon': 3, 'weights': ('Head',),
     'points': {0x23: ('tip', 1)}},
    # the snakes' own bones hang under this one (SNAKES['parent']): at her forearm, shown with them (summon 4);
    # numbered 599, before theirs (OPT 600..): the game makes its bones' world matrices in number order, and theirs
    # made before their parent's would be a frame behind her arm (convert/snakes8.py)
    {'bone': 'snakes', 'parent': 'UDE_R_jnt', 'still': True, 'summon': 4, 'number': 599},
]
# Her snakes (convert/snakes8.py): Tekken 8's Org actor on her right forearm, its own mesh and skeleton, its 16 clips
# (the MissileAnimData table's) started by her moves (0x83aa, stopped by 0x83ab) -> extra bones OPT 600.. under the
# 'snakes' weapon above, played from part 3 of her motion pack. Kept of their skeleton: the centre, the coil (dambe),
# each snake's base, necks 2, 5, 8 and 11, head and jaw (23 bones: every vertex within 3.8 cm (p99) of the full
# skinning over the 16 clips); meshes decimated to 'vertices' (the snakes, the coil).
_MWSH = '/Game/Character/Item/model/unique/wkz/extra/wkz_exp_mwsh/meshes/SK_CH_wkz_exp_mwsh'
SNAKES = {
    'mesh': _MWSH,
    'animations': '/Game/Character/Blueprints/DataTable/MissileAnimData/wkz/MAD_wkz_org',
    'parent': 'snakes',
    'necks': (2, 5, 8, 11),
    'vertices': {'snk': 2000, 'dmb': 300},
}

# part -> (TTT2 mesh name, the bone the mesh is bound to as a whole, draw order); hed is the ribbon in her hair,
# ex1 her earrings
MESHES = {
    'bdf': ('mzo_bdf_1p', 'KOSHI_jnt', 0),
    'fac': ('mzo_fac', 'ATAMA_Joint', 2),
    'har': ('mzo_har_1p', 'ATAMA_jnt_assist', 3),
    'hed': ('mzo_hed_1p', 'ATAMA_jnt_assist', 4),
    'ex1': ('mzo_exp_1p', 'ATAMA_jnt_assist', 5),
}

# Tekken 8 material instance -> (template, use its normal map, keep the colour texture's alpha); None: left out.
# Only exceptions: tekken8/bake.classify picks the kind from the material's base material and name.
MATERIALS = {
    'MI_CH_wkz_add_tealine': None,                # the wet line along the lower eyelids (an additive layer)
    'MI_CH_wkz_eye_ao': None,                     # the eyes' ambient occlusion shell (a blurred dark layer)
    'MI_Cal_Mesh': None,                          # an invisible mesh the game measures the body with
}

# Material templates in the donor's files: (archive entry name or key, mesh, polygon); Jun's, as for every woman
TEMPLATES = {
    'skin': ('jun.nud', 'ude_A_O_OBJ', 0),        # skin with a normal map
    'mouth': ('jun.nud', 'cha:kao_O_OBJ', 0),     # mouth and teeth
    'eye': ('jun.nud', 'cha:kao_O_OBJ', 2),
    'overlay': ('jun.nud', 'cha:kao_O_OBJ', 7),   # a blended layer over the face
    'cloth': (0xD4F28D09, 'jun_upb_1p_b', 0),     # a costume part of Jun's (her model pack, member 95)
    'hair': (0x5F412CA4, 'jun_hed_1p', 1),        # (member 7): alpha-tested, two-sided
    'colour': (0xD4F28D09, 'jun_upb_1p_b', 2),    # colourable cloth (2P colour layers)
    'colour_alpha': (0xD4F28D09, 'jun_upb_1p_b', 1),   # its alpha-tested variant (the layers take its alpha test)
    # her glowing summons (staffs, tail, horn, snakes: tekken8/bake.py bake_emissive, their glow baked into the
    # colour): the unlit textured core of TTT2's own light spear, cmn_opu_LightSpear in data017 (poly 1: 0x21000001,
    # src 0, dst 160). In a fight her right staff's pixels came out sRGB median 62 130 202 with it (Tekken 8's
    # 70 149 209); Jun's lit costume material gave 62 112 168, greyer and shaded.
    'glow': (0x285AE2C4, 'cmn_opu_LightSpear', 1),
}
# where the templates' own textures are (their average colours fill the slots Tekken 8 has nothing for)
TEMPLATE_TEXTURES = ['jun.nut', 0x24F8AE59, 0x277C7A37, 0xAD9B60F0, 0x900FD8C4]

# ------------------------------------------------------------------------------------------------ effects
# her Tekken 8 effects converted (convert/effects8.py): effect id -> TTT2 body part, {summon: part} (at the part of
# the summon the move shows or hides, ending with it; the first listed when the move does neither), or (part,
# 'floor') (placed from the floor under it). The staffs (summons 0 left, 1 right: bone records 13 TE_L, 9 TE_R):
# appearing (40 CaneStart), the aura while out (42 Cane01), the swirl at her feet (43 CaneGround) and vanishing
# (41 CaneFinish); the tail (summon 2, from her hips: 3 KOSHI) appearing (15 TailStart) and vanishing (17
# TailFinish); the horn (summon 3, on her head: 5 ATAMA) appearing (30 CornerStart) and vanishing (31
# CornerFinish). Left out: the tail's aura while out (16 Tail01: along four tail bones, 1.6 m; at the hips it would
# be a glow on her back), the horn's (32 Corner01: 14 emitters), her other effects. {}: none.
_FX_STAFF, _FX_TAIL, _FX_HORN = {1: 9, 0: 13}, {2: 3}, {3: 5}
TEKKEN8_EFFECTS = {40: _FX_STAFF, 41: _FX_STAFF, 42: _FX_STAFF, 43: (_FX_STAFF, 'floor'), 15: _FX_TAIL, 17: _FX_TAIL,
                   30: _FX_HORN, 31: _FX_HORN}

# ------------------------------------------------------------------------------------------------ pictures
# her Tekken 8 UI pictures (convert/art.py): a bust, her whole body, each with where her face is in it (the eyes'
# centre x, y and eyes-to-chin, in its pixels), her name, and her costume picture
_UI = '/Game/UI/Rep_Texture'
ART = {
    'bust': (_UI + '/Makuai_Character_L/T_UI_Makuai_Character_L_wkz', (975, 1240, 412)),   # (x estimated: 900..975)
    'body': (_UI + '_Other/ST01_Arena/Character_Full/T_wkz_1p_C', (729, 197, 100)),
    'name': _UI + '/HUD_Character_Name/T_UI_HUD_Character_Name_wkz',
    'costume': _UI + '/CS_Slot_Thumb/wkz/T_UI_CS_Character_Slot_wkz_1p',  # the costume chooser's picture
}

# ------------------------------------------------------------------------------------------------ voice
# her Tekken 8 voice events (tekken8/voice.py)
VOICE = 'wkz'

# ------------------------------------------------------------------------------------------------ moveset
MOVESET = {
    'name': '[MIARY_ZO]',       # the moveset's name (in its header)
    # her round-start move (the donor's is kept: its mode checks are Tekken 8's)
    'drop_moves': r'^Wkz_Direct$',
    # the donor's round-start list keeps its targets except its own moves (Wkz_Direct picks 3 intros wkz_s00..02 and 3
    # win poses wkz_w00..02; s98/s99 are special)
    'direct': [(r'^Ju_sKAM00_$', 'move', ['Wkz_sKAM00_']),                      # Jun's stance -> hers
               (r'^(ju|mk)_s', 'anim', ['wkz_s%02d' % k for k in range(3)]),    # intros
               (r'^ju_w', 'anim', ['wkz_w%02d' % k for k in range(3)])],        # win poses
    # TTT2 bounds (Tekken 8 has none, and her tornados do not become any): an air hit slams the opponent into the
    # floor once per juggle (convert/move_overrides.py). d+2 Famakin'naina, d/f+1,1,2's last hit (Famakin'ny Ala),
    # b+1+2 Ampinga Afo, Morengy Miroso 1+2 (Tafika Maitso) and ws3 Daka Manorana; d+2 and d/f+1,1,2 go on from frame
    # 24 in a copy of themselves under Tekken 8's requirement 126, which bounds alike. (Moves no name is known for are
    # '#<index>': indices of the game build the names were read from.)
    'bounds': {
        'Wkz_2RP': True,       # d+2
        '#1663': True,         # d+2, its copy
        'Wkz_3LPLPRP': True,   # d/f+1,1,2, last hit
        '#1672': True,         # d/f+1,1,2, its copy
        'Wkz_4WP': True,       # b+1+2
        'Wkz_6LK_WP': True,    # MOR 1+2
        '#1705': True,         # ws3
    },
}
