"""Azucena from Tekken 8 (PC), in her default costume.

Only names, paths and rules live here; every byte of her model, textures, pictures, voice and moveset is read from
the player's own Tekken 8 and Tekken Tag Tournament 2 files when the importer runs. Tekken 8 keeps its movesets in an
encrypted archive: the running game's own reader saves hers (tekken8/autodump.py, import_character.py runs it); the
import needs no Tekken 7.
"""
NAME = 'Azucena'
SHORT_NAME = 'AZUCENA'        # her name on the 2D screens (TTT2 shows short names: KAZUYA, HEIHACHI)
TEKKEN8_ID = 29               # her FighterId in Tekken 8 (BaseCharacterItem BCI_cat_bdf_1p)
TEKKEN8_CODE = 'cat'          # her code in Tekken 8's files (Character/Item/model/unique/cat/, Sound/Character/CAT/)
CODE = 'azu'                  # her three-letter code in the pack (not a code TTT2 or another added fighter has)
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
# what packs of her made before lack (pack.revision; the launcher shows "Update ready"): 1: her bounds; 2: Tekken 8's
# limb hit points, on-hit follow-ups (1,1 into Libertador), air reactions (d+2,3), slams after the bound, wall
# pushbacks, the run's contact stop, her u/f+1+2's catch; 3: her select cell's and fight faces' colours as her whole
# body's
REVISION = 3

# ------------------------------------------------------------------------------------------------ model
# her Tekken 8 costumes: the CustomizeSet CS_cat_<name> (tekken8/costume.py: its meshes, their merge order and the
# colours of its CustomizeItems), player 1 and player 2 (the same meshes, other colours: convert/colours.py makes
# TTT2's 2P colours from both)
TEKKEN8 = {
    'costume': '1p',
    'costume_2p': '2p',
}

# part -> (TTT2 mesh name, the bone the mesh is bound to as a whole, draw order); ex0 is the feathers and beads in her
# hair (cat_exp_1p)
MESHES = {
    'bdf': ('azu_bdf_1p', 'KOSHI_jnt', 0),
    'fac': ('azu_fac', 'ATAMA_Joint', 2),
    'har': ('azu_har_1p', 'ATAMA_jnt_assist', 3),
    'ex0': ('azu_exp_1p', 'ATAMA_jnt_assist', 4),
}

# Tekken 8 material instance -> (template, use its normal map, keep the colour texture's alpha); None: left out.
# Only exceptions: tekken8/bake.classify picks the kind from the material's base material and name.
MATERIALS = {
    'MI_CH_cat_add_tealine': None,                # the wet line along the lower eyelids (an additive layer)
    'MI_CH_cat_eye_ao': None,                     # the eyes' ambient occlusion shell (a blurred dark layer)
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
    'bust': (_UI + '/Makuai_Character_L/T_UI_Makuai_Character_L_cat', (864, 1248, 414)),
    'body': (_UI + '_Other/ST01_Arena/Character_Full/T_cat_1p_C', (750, 199, 101)),
    'name': _UI + '/HUD_Character_Name/T_UI_HUD_Character_Name_cat',
    'costume': _UI + '/CS_Slot_Thumb/cat/T_UI_CS_Character_Slot_cat_1p',  # the costume chooser's picture
}

# ------------------------------------------------------------------------------------------------ voice
# her Tekken 8 voice events (tekken8/voice.py): Play_CAT_Attack_S_001 .. (shouts, damage, KO, special),
# Play_cat_sta_00 .. (intro lines), Play_cat_win_00 .. (win quotes), Play_syvo_name_CAT (the announcer's call)
VOICE = 'cat'

# ------------------------------------------------------------------------------------------------ moveset
MOVESET = {
    'name': '[AZUCENA]',        # the moveset's name (in its header)
    # her own moves that are not converted (besides convert/moveset.py's DROP_MOVES): her round-start move
    # Cat_Direct (the donor's is kept: its mode checks are Tekken 8's)
    'drop_moves': r'^Cat_Direct$',
    # the donor's round-start list keeps its targets except its own moves: (donor move name pattern, 'move': the
    # cancel goes to her move instead / 'anim': the donor's move stays (its camera, timing, voice) and plays one of
    # her animations, in turn; a win pose takes the one whose quote it plays)
    'direct': [(r'^Ju_sKAM00_$', 'move', ['Cat_sKAM00_']),                      # Jun's stance -> hers
               (r'^(ju|mk)_s', 'anim', ['cat_s%02d' % k for k in range(3)]),    # intros
               (r'^ju_w', 'anim', ['cat_w%02d' % k for k in range(3)])],        # win poses
    # TTT2 bounds (Tekken 8 has none, and her tornados do not become any): an air hit slams the opponent into the
    # floor once per juggle (convert/move_overrides.py). d+1 Hand Drip Hammer, d/f+1,4,1~2's last hit (Full Body
    # Grande Combo), Libertador 3,1's 1 (Blend Reganar), Libertador 4,2's 2 (Blend Martillo), u/f+4 Tacones Drip,
    # u/f+3+4's second kick (Ortiz Molino: #1620 kicks first) and f,f+4 Demitasse Molino. (Moves no name is known
    # for are '#<index>', 'Cat_#<index>' in her TTT2 moveset: indices of the game build the names were read from.)
    'bounds': {'Cat_t_slp00': True, '#1807': True, '#1677': True, '#1696': True, 'Cat_jprk00F': True,
               '#1621': True, 'Cat_66rk': True},
    # her reactions that keep Tekken 8's move (convert/moveset.py Converter.target): f+2,1,4's and d/b+3+4's launch
    # away from her (#391, from behind #392), which the reaction evidence (only Feng's f+2,1,4 has the same notation)
    # made ym_y01L, a flip back over her: both launch, so neither the fall classes nor the frames tell them apart
    'own_reactions': ('#391', '#392'),
    # u/f+1+2 (Thrmv_B1_R0): Tekken 8's catch point is the left hand (13, 0)(13, 1), but her animation reaches with the
    # right one (TE_R 670 mm ahead of her at the catch frame, TE_L 400 ahead and 400 to the side), so TTT2's catch
    # at the left hand never touched anyone: the right hand, the chest kept
    'hitboxes': {'Thrmv_B1_R0': (9, 0, 9, 1)},
}
