"""Reina from Tekken 8 (PC), in her default costume.

Only names, paths and rules live here; every byte of her model, textures, pictures, voice and moveset is read from
the player's own Tekken 8 and Tekken Tag Tournament 2 files when the importer runs. Tekken 8 keeps its movesets in an
encrypted archive: the running game's own reader saves hers (tekken8/autodump.py, import_character.py runs it); the
import needs no Tekken 7.
"""
NAME = 'Reina'
SHORT_NAME = 'REINA'          # her name on the 2D screens (TTT2 shows short names: KAZUYA, HEIHACHI)
TEKKEN8_ID = 28               # her FighterId in Tekken 8 (BaseCharacterItem BCI_zbr_bdf_1p)
TEKKEN8_CODE = 'zbr'          # her code in Tekken 8's files (Character/Item/model/unique/zbr/, Sound/Character/ZBR/)
CODE = 'rei'                  # her three-letter code in the pack (not a code TTT2 or another added fighter has)
SEX = 'female'

# The donor: a TTT2 fighter with a similar body. Its skeleton is the base of hers (the face animations set the face
# joints' absolute positions: the skeleton is the moveset's owner's), its moveset gives the generic and tag moves,
# its voice list, sound banks, item database and effects are used for her. Her materials are Jun's (TEMPLATES).
DONOR = 'jun'                 # Jun Kazama: the 139-bone female skeleton
DONOR_ROW = 42                # her motion row (data005 / data006 entry)
# her moveset: 'tekken8' = her own Tekken 8 moveset converted (the files the running game saved: importer.py)
MOVESET_SOURCE = 'tekken8'
# when her Tekken 8 moveset cannot be had (none saved and Tekken 8 could not run to save it: no Steam, or a game
# update the helper does not know yet): the TTT2 fighter (code, motion row) whose moveset she fights with instead,
# as it is (MOVESET_SOURCE 'donor'), the donor of everything then (importer.with_stand_in)
STAND_IN = ('hei', 13)        # Heihachi Mishima
# what packs of her made before lack (pack.revision; the launcher shows "Update ready"): 1: the d/f+1,2 bound
REVISION = 1

# ------------------------------------------------------------------------------------------------ model
# her Tekken 8 costumes: the CustomizeSet CS_zbr_<name> (tekken8/costume.py: its meshes, their merge order and the
# colours of its CustomizeItems), player 1 and player 2 (the same meshes, other colours: convert/colours.py makes
# TTT2's 2P colours from both). 'parts' / 'merge_order' would name the meshes instead of the costume's.
TEKKEN8 = {
    'costume': '1p',
    'costume_2p': '2p',
}

# part -> (TTT2 mesh name, the bone the mesh is bound to as a whole, draw order)
MESHES = {
    'bdf': ('rei_bdf_1p', 'KOSHI_jnt', 0),
    'fac': ('rei_fac', 'ATAMA_Joint', 2),
    'har': ('rei_har_1p', 'ATAMA_jnt_assist', 3),
}

# Tekken 8 material instance -> (template, use its normal map, keep the colour texture's alpha); None: left out.
# Only exceptions: tekken8/bake.classify picks the kind from the material's base material and name.
MATERIALS = {
    'MI_CH_zbr_add_tealine': None,                # the wet line along the lower eyelids (an additive layer)
    'MI_CH_zbr_eye_ao': None,                     # the eyes' ambient occlusion shell (a blurred dark layer)
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
}
# where the templates' own textures are (their average colours fill the slots Tekken 8 has nothing for)
TEMPLATE_TEXTURES = ['jun.nut', 0x24F8AE59, 0x277C7A37, 0xAD9B60F0, 0x900FD8C4]

# ------------------------------------------------------------------------------------------------ pictures
# her Tekken 8 UI pictures (convert/art.py): a bust (the VS screen's, on a transparent background) and her whole
# body (the arena's), each with where her face is in it (the eyes' centre x, y and eyes-to-chin, in its pixels), her
# name, and her costume picture (a fighting stance on a transparent background)
_UI = '/Game/UI/Rep_Texture'
ART = {
    'bust': (_UI + '/Makuai_Character_L/T_UI_Makuai_Character_L_zbr', (899, 1237, 411)),
    'body': (_UI + '_Other/ST01_Arena/Character_Full/T_zbr_1p_C', (750, 207, 100)),
    'name': _UI + '/HUD_Character_Name/T_UI_HUD_Character_Name_zbr',
    'costume': _UI + '/CS_Slot_Thumb/zbr/T_UI_CS_Character_Slot_zbr_1p',  # the costume chooser's picture
}

# ------------------------------------------------------------------------------------------------ voice
# her Tekken 8 voice events (tekken8/voice.py): Play_ZBR_Attack_S_001 .. (shouts, damage, KO, special),
# Play_zbr_sta_00 .. (intro lines), Play_zbr_win_00 .. (win quotes), Play_syvo_name_ZBR (the announcer's call)
VOICE = 'zbr'

# ------------------------------------------------------------------------------------------------ moveset
MOVESET = {
    'name': '[REINA]',          # the moveset's name (in its header)
    # her own moves that are not converted (besides convert/moveset.py's DROP_MOVES): her round-start move
    # Zbr_Direct (the donor's is kept: its mode checks are Tekken 8's). (Zbr_SUPER_0 is her Ki Charge, 1+2+3+4, not
    # her Rage Art: that is #2162, d/f+1+2 during Rage, whose rows are false without Rage)
    'drop_moves': r'^Zbr_Direct$',
    # the donor's round-start list keeps its targets except its own moves: (donor move name pattern, 'move': the
    # cancel goes to her move instead / 'anim': the donor's move stays (its camera, timing, voice) and plays one of
    # her animations, in turn; a win pose takes the one whose quote it plays)
    'direct': [(r'^Ju_sKAM00_$', 'move', ['Zbr_sKAM00_']),                      # Jun's stance -> hers
               (r'^(ju|mk)_s', 'anim', ['zbr_s%02d' % k for k in range(3)]),    # intros
               (r'^ju_w', 'anim', ['zbr_w%02d' % k for k in range(3)])],        # win poses
    # TTT2 bounds besides her Tekken 8 tornados (which convert to bounds by themselves): an air hit slams the
    # opponent into the floor once per juggle (convert/move_overrides.py). d+2 Tecchuu-ate, f+4 Kamadhatu Splits
    # Kick, the same kick out of a dash (Zbr_66RK: f,f+4 by the donor's dash rows; Tekken 8's after a Heat Dash), and
    # d/f+1,2's second hit (Zbr_3LPRP)
    'bounds': {'Zbr_2RP': True, 'Zbr_6RK': True, 'Zbr_66RK': True, 'Zbr_3LPRP': True},
    # tag combos (convert/tagcombo.py picks her launchers): EWGF and WGF for certain, as TTT2's Kazuya has them
    'tag_combos': {'Zbr_shoryu_S': True, 'Zbr_shoryu_N': True},
}
