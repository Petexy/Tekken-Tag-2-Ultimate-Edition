"""Victor Chevalier from Tekken 8 (PC), in his default costume.

Only names, paths and rules live here; every byte of his model, textures, pictures, voice and moveset is read from
the player's own Tekken 8 and Tekken Tag Tournament 2 files when the importer runs. Tekken 8 keeps its movesets in an
encrypted archive: the running game's own reader saves his (tekken8/autodump.py, import_character.py runs it); the
import needs no Tekken 7.
"""
NAME = 'Victor Chevalier'
SHORT_NAME = 'VICTOR'         # his name on the 2D screens (TTT2 shows short names: KAZUYA, HEIHACHI)
TEKKEN8_ID = 30               # his FighterId in Tekken 8 (BaseCharacterItem BCI_lon_ex0_1p; autodump.ROSTER)
TEKKEN8_CODE = 'lon'          # his code in Tekken 8's files (Character/Item/model/unique/lon/)
CODE = 'vic'                  # his three-letter code in the pack (not a code TTT2 or another added fighter has)
SEX = 'male'

# The donor: a TTT2 fighter with a similar body. Its skeleton is the base of his, its moveset gives the generic and
# tag moves, its voice list, sound banks, item database and effects are used for him.
DONOR = 'lar'                 # Lars Alexandersson: a slim male skeleton
DONOR_ROW = 38
# his moveset: 'tekken8' = his own Tekken 8 moveset converted (the files the running game saved: importer.py)
MOVESET_SOURCE = 'tekken8'
# when his Tekken 8 moveset cannot be had: the TTT2 fighter (code, motion row) whose moveset he fights with instead
STAND_IN = ('hei', 13)        # Heihachi Mishima

# ------------------------------------------------------------------------------------------------ model
# his Tekken 8 costumes: the CustomizeSet CS_lon_<name> (tekken8/costume.py), player 1 and player 2
TEKKEN8 = {
    'costume': '1p',
    'costume_2p': '2p',
    'wide_root_boxes': True,    # (IAI.d+2's column 1.1 m ahead of him: box 2, boxes 0 and 1 his fist: summons8.summary)
    # (metal's colour, strength, reflection, other greys' colour) of his weapons and of the emblem on the back of his
    # gloves (tekken8/bake.py dark_metal)
    'dark_metal': {'MI_CH_lon_exp_1p_weapons': (0.08, 0.3, 0.2, 0.3), 'MI_CH_lon_exp_1p_blade': (0.08, 0.3, 0.2, 0.3),
                   'MI_CH_lon_bdu_1p_glove': (0.6, 0.5, 0.3, 1.0)},
    'var_slots': {3: (9, 2)},   # (2,2's last 2, pressed early, for its third hit to test: summons8.vars_as_slots)
}

# the vertices of his model the game skins (model.VERTEX_BUDGET): his weapons and glasses among them (Noctis's 56000)
VERTEX_BUDGET = 56000

# part -> (TTT2 mesh name, the bone the mesh is bound to as a whole, draw order); fah his beard, gla his glasses (his
# weapons' mesh, the costume's ex0: WEAPONS)
MESHES = {
    'bdf': ('vic_bdf_1p', 'KOSHI_jnt', 0),
    'fac': ('vic_fac', 'ATAMA_Joint', 2),
    'har': ('vic_har_1p', 'ATAMA_jnt_assist', 3),
    'fah': ('vic_fah_1p', 'ATAMA_jnt_assist', 4),
    'gla': ('vic_gla_1p', 'ATAMA_jnt_assist', 6),
}

# ------------------------------------------------------------------------------------------------ weapons
# His objects (convert/summons8.py), one mesh of 22 rigid pieces on ATH_ joints, each hand's and each holster's copy of
# them shown by its bone (SetWeaponMeshVisibleImpl; a hidden bone hides what hangs under it). His moves show and hide
# them with the masks 0x83a6 / 0x83a7, bit n = summon n: 2 the scabbard at his hip, 3 the hilt in it, 4 the gun at his
# thigh, 5 the karambit at his thigh, 6 the scabbard in his left hand, 7 the hilt in it, 8 the knife in his left hand,
# 9 the karambit in his right, 10 the grenade, 11 the flashlight, 12 the sword, 13 the gun in his right hand (0, 1 name
# no joint of the mesh, 14 swaps the Rage Art's mesh: dropped).
_EX0 = '/Game/Character/Item/model/unique/lon/extra/lon_exp_1p/meshes/SK_CH_lon_exp_1p'
WEAPONS = [
    {'mesh': _EX0, 'bone': 'ATH_L_knife', 'parent': 'TE_L_jnt', 'pair': 0, 'summon': 8,
     'points': {0x80: ({'offset': (0, -160, 80)}, 1)}},
    {'mesh': _EX0, 'bone': 'ATH_R_karambit', 'parent': 'TE_R_jnt', 'pair': 1, 'summon': 9,
     'points': {0x81: ({'offset': (-30, -180, 0)}, 0)}},
    {'mesh': _EX0, 'bone': 'ATH_R_katana', 'parent': 'TE_R_jnt', 'pair': 2, 'summon': 12,
     'points': {0x83: ({'offset': (0, 730, 0)}, 0)}},
    {'mesh': _EX0, 'bone': 'ATH_L_saya01', 'parent': 'TE_L_jnt', 'pair': 3, 'summon': 6,
     'weights': ('ATH_L_saya01', 'ATH_L_saya02'), 'points': {0x82: ({'offset': (0, 250, 0)}, 1)}},
    {'mesh': _EX0, 'bone': 'ATH_L_saya03', 'parent': 'ATH_L_saya01', 'pair': 4, 'summon': 6},
    {'mesh': _EX0, 'bone': 'ATH_L_saya04', 'parent': 'ATH_L_saya03', 'pair': 5, 'summon': 6},
    {'mesh': _EX0, 'bone': 'ATH_L_tsuka', 'parent': 'ATH_L_saya01', 'still': True, 'summon': 7},
    {'mesh': _EX0, 'bone': 'ATH_Hip_saya01', 'parent': 'KOSHI_jnt', 'pair': 6, 'summon': 2,
     'weights': ('ATH_Hip_saya01', 'ATH_Hip_saya02')},
    {'mesh': _EX0, 'bone': 'ATH_Hip_saya03', 'parent': 'ATH_Hip_saya01', 'pair': 7, 'summon': 2},
    {'mesh': _EX0, 'bone': 'ATH_Hip_saya04', 'parent': 'ATH_Hip_saya03', 'pair': 8, 'summon': 2},
    {'mesh': _EX0, 'bone': 'ATH_Hip_tsuka', 'parent': 'ATH_Hip_saya01', 'still': True, 'summon': 3},
    {'mesh': _EX0, 'bone': 'ATH_R_handgun01', 'parent': 'TE_R_jnt', 'pair': 9, 'summon': 13},
    {'mesh': _EX0, 'bone': 'ATH_R_handgun02', 'parent': 'ATH_R_handgun01', 'pair': 10, 'summon': 13},
    {'mesh': _EX0, 'bone': 'ATH_R_grenade', 'parent': 'TE_R_jnt', 'pair': 11, 'summon': 10},
    {'mesh': _EX0, 'bone': 'ATH_R_flashlight', 'parent': 'TE_R_jnt', 'still': True, 'summon': 11},
    {'mesh': _EX0, 'bone': 'ATH_R_Thigh_handgun01', 'parent': 'MOMO_R_jnt', 'still': True, 'summon': 4,
     'weights': ('ATH_R_Thigh_handgun01', 'ATH_R_Thigh_handgun02')},
    {'mesh': _EX0, 'bone': 'ATH_R_Thigh_karambit', 'parent': 'MOMO_R_jnt', 'still': True, 'summon': 5},
    # (the holsters at his thigh are always out)
    {'mesh': _EX0, 'bone': 'ATH_R_Thigh_handgun_holster', 'parent': 'MOMO_R_jnt', 'still': True,
     'weights': ('ATH_R_Thigh_handgun_holster', 'ATH_R_Thigh_karambit_saya')},
]
SUMMON_MASKS = True                      # his moves' 0x83a6 / 0x83a7 rows (convert/summons8.py split_masks)
# out when no move says otherwise, also while he is hit or thrown (the attacker's moves say nothing of them): the
# scabbard and its hilt at his hip, the gun at his thigh, the knife and the karambit in his hands (his generic moves'
# reset rows and the rows of his moves that hide and show them again)
REST_SUMMONS = (2, 3, 4, 8, 9)
WEAPON_DISMISS = r'^Lon_sKAM00_$'        # his stance starts with them so (moveset.dismiss_at_start)
# His own hit codes, each read in a joint's frame with offsets (summons8.joint_spots): 121 the right hand's (the gun's
# lines, the grenades' spheres, the flashlight), 128 the knife's, 129 the karambit's, 130 the scabbard's, 131 the sword's
HIT_JOINTS = {121: ('R_Hand', 9), 128: ('ATH_L_knife', None), 129: ('ATH_R_karambit', None),
              130: ('ATH_L_saya01', None), 131: ('ATH_R_katana', None)}

# his Tekken 8 effects converted (convert/effects8.py): effect id -> TTT2 body part (3 his waist, 9 his right hand, 12
# his left hand, 8 his right forearm): 5, 6 the warp of his teleports and stance changes, 13 AuraGazerN, 21, 22, 29 the
# grenades' bombs, 23 the gun's flash, 24 its bullet, 25, 26, 37 the bomb punch, 35 Tsuki01
TEKKEN8_EFFECTS = {5: 3, 6: 3, 13: 9, 21: 9, 22: 9, 23: 9, 24: 9, 25: 9, 26: 9, 29: 9, 35: 12, 37: 8}
TEKKEN8_TRAILS = True                   # his weapons' trails (convert/trails8.py): the flame arc of his sword
# (the sheath's: Tekken 8's frames only ever show it from its edge, a thin white line: that line with little of the sheet;
# the karambit's wide one: clear glass with a white rim round it, leaving flecks in the air)
TEKKEN8_TRAIL_LOOKS = {2: dict(edge=True, body=0.15), 4: dict(edge=True, body=0.6, flecks=True)}
# (Lars's own effect, a purple lightning: in Victor's moves it came up as a white square a metre wide)
DONOR_EFFECTS = False
# (Tekken 8's dome is pale and shows the fight through it: the bombs' rings add up to white if drawn at their numbers)
_BOMB_ROLES = ((r'^Ring_Aura002$', dict(dim=0.1)), (r'^Ring_AuraBack$', dict(dim=0.15)),
               (r'^Ring_Aura001$', dict(dim=0.4)), (r'^Ring_Aura$', dict(dim=0.3)),
               (r'^Shitaji$', dict(add=True, dim=0.2)),
               (r'^Dome_Aura$', dict(add=True, colour=(0.4, 0.7, 1.0), dim=0.25)),
               # (its hexagons: Tekken 8 bends the picture with them; here they are a faint light)
               (r'^Dome_Distortion$', dict(add=True, fade=True, colour=(0.3, 0.6, 1.0), dim=0.04)))
TEKKEN8_EFFECT_TUNE = {
    'measured': True,                               # (effects8: what the emitters' own scripts do)
    'skip': r'^(?!Dome_)\w*Distortion|^Ring_hosoi$|^Dome_Dark$',     # (refraction: nothing to see in TTT2's blend; a dissolve; a
                                                        # faint darkening: as a translucent quad it draws a white square)
    'skip_materials': r'^.*VAT_',                   # (animated meshes: a still pose is a blob)
    'offset': {23: (28.0, 0.0, 4.0), 24: (28.0, 0.0, 4.0)},     # his hand -> the gun's muzzle (cm: ahead, right, up)
    # GPU emitters' numbers are not in the files: by the look of the frames of Tekken 8 (sparkles along the bullet's way)
    'roles': ((r'^glitch0[01]$', dict(pre=(0.0, 0.0, 90.0))),
              (r'^Flare', dict(alpha=0.1, size=0.4)),       # (its core is small and white in Tekken 8, no ball of light)
              (r'^Center_glow', dict(alpha=0.3, size=0.6)),
              (r'^Core$', dict(alpha=0.2, size=0.5)),
              (r'^(Glow|Shitaji)', dict(add=True, colour=(1.0, 1.0, 1.0), alpha=0.12)),       # (a faint blue haze)
              (r'^Dome_Aura$', dict(add=True, colour=(1.0, 6.0, 12.0)))),                    # (its rim: pale blue)
    'system_roles': {6: ((r'^glitch01003$', dict(alpha=0.2, size=0.5)),
                         (r'^glitch01006$', dict(alpha=0.5))),
                     21: _BOMB_ROLES, 29: _BOMB_ROLES,
                     # (the flare before the bomb: small, white-hot, a streak across it; its numbers are not in the files)
                     22: ((r'^Glow001$', dict(add=True, dim=0.25, size=0.5)),
                          (r'^Flare002$', dict(alpha=0.1, size=0.3)),
                          (r'^Horizon_streaks01001$', dict(wh=(110.0, 5.0)))),
                     25: ((r'^Wind$', dict(dim=0.3)), (r'^WindGlow$', dict(dim=0.06)),
                          (r'^RingWindWhite$', dict(dim=0.12)), (r'^Wind002$', dict(alpha=0.08))),
                     23: ((r'^BurstCore001$', dict(thin=0.5)),
                          (r'^Spark$', dict(alpha=0.2)),
                          (r'^Ring_Aura002$', dict(alpha=0.25)),
                          (r'^Spark_card001$', dict(turn=(0.5, 0.0, 0.0)))),
                     24: ((r'^BurstCore$', dict(thin=0.3, at=(170.0, 0.0, 0.0))),
                          (r'^Yoin$', dict(life=(0.05, 0.0), scale=0.01)),
                          (r'^Particle$', dict(life=(0.3, 0.1), size=(2.5, 1.0), box=(300.0, 0.5, 0.5),
                                               at=(300.0, 0.0, 0.0), emit=0.25)),
                          (r'^Spark_card', dict(life=(0.2, 0.08), size=(2.0, 0.8), box=(300.0, 1.0, 1.0),
                                                at=(300.0, 0.0, 0.0), emit=0.25)))},
}

# Tekken 8 material instance -> (template, use its normal map, keep the colour texture's alpha); None: left out.
# Only exceptions: tekken8/bake.classify picks the kind from the material's base material and name.
MATERIALS = {
    'MI_CH_lon_add_tearline': None,               # the wet line along the lower eyelids (an additive layer)
    'MI_CH_lon_ao': None,                         # the eyes' ambient occlusion shell (a blurred dark layer)
    'MI_Cal_Mesh': None,                          # an invisible mesh the game measures the body with
    # his lenses: Tekken 8 dithers them at the alpha of their colour texture; here a blended layer over his eyes
    'MI_CH_lon_gla_1p_glasses_lens': ('lens', False, True),
}

# a material's baked colours x this in linear (model's GAIN): the lens is pale blue, Tekken 8 darkens it with what it blends
GAIN = {'MI_CH_lon_gla_1p_glasses_lens': 0.3}

# Material templates in the donor's files: Jun's, as for every added fighter (they are only shaders)
TEMPLATES = {
    'skin': ('jun.nud', 'ude_A_O_OBJ', 0),        # skin with a normal map
    'mouth': ('jun.nud', 'cha:kao_O_OBJ', 0),     # mouth and teeth
    'eye': ('jun.nud', 'cha:kao_O_OBJ', 2),
    'overlay': ('jun.nud', 'cha:kao_O_OBJ', 7),   # a blended layer over the face
    'lens': ('bry.nud', 'kubiA_O_OBJ', 2),        # a plain blended layer (the face's above shows silver on a flat lens)
    'cloth': (0xD4F28D09, 'jun_upb_1p_b', 0),     # a costume part of Jun's (her model pack, member 95)
    'hair': (0x5F412CA4, 'jun_hed_1p', 1),        # (member 7): alpha-tested, two-sided
    'colour': (0xD4F28D09, 'jun_upb_1p_b', 2),    # colourable cloth (2P colour layers)
    'colour_alpha': (0xD4F28D09, 'jun_upb_1p_b', 1),   # its alpha-tested variant (the layers take its alpha test)
}
# where the templates' own textures are (their average colours fill the slots Tekken 8 has nothing for)
TEMPLATE_TEXTURES = ['jun.nut', 0x24F8AE59, 0x277C7A37, 0xAD9B60F0, 0x900FD8C4]

# ------------------------------------------------------------------------------------------------ pictures
# his Tekken 8 UI pictures (convert/art.py): a bust, his whole body, each with where his face is in it (the eyes'
# centre x, y and eyes-to-chin, in its pixels), his name, and his costume picture
_UI = '/Game/UI/Rep_Texture'
ART = {
    'bust': (_UI + '/Makuai_Character_L/T_UI_Makuai_Character_L_lon', (905, 1250, 410)),
    'body': (_UI + '_Other/ST01_Arena/Character_Full/T_lon_1p_C', (752, 212, 100)),
    'name': _UI + '/HUD_Character_Name/T_UI_HUD_Character_Name_lon',
    'costume': _UI + '/CS_Slot_Thumb/lon/T_UI_CS_Character_Slot_lon_1p',  # the costume chooser's picture
}

# ------------------------------------------------------------------------------------------------ voice
# his Tekken 8 voice events (tekken8/voice.py)
VOICE = 'lon'

# ------------------------------------------------------------------------------------------------ moveset
MOVESET = {
    'name': '[VICTOR]',         # the moveset's name (in its header)
    # his throws' victims (and those of some knockdowns) stay where Tekken 8 leaves them as they go down, facing as
    # they lie (convert/moveset.py handoffs8): the hand-off's turn sweep spun them 45 to 755 degrees on the ground
    'keep_body_handoffs': True,
    # his round-start move (the donor's is kept: its mode checks are Tekken 8's)
    # and his Rage Art (no cancel leads to it here: Tekken 8's entry rows test rage, 159)
    'drop_moves': r'^Lon_Direct$|^#20(6[0-6])$',
    # the donor's round-start list keeps its targets except its own moves
    'direct': [(r'^La_sKAM00_$', 'move', ['Lon_sKAM00_']),                      # Lars's stance -> his
               (r'^(la|mk)_s', 'anim', ['lon_s%02d' % k for k in range(3)]),    # intros
               (r'^la_w', 'anim', ['lon_w%02d' % k for k in range(3)])],        # win poses
    # TTT2 bounds (Tekken 8 has none, and his tornados do not become any): an air hit slams the opponent into the
    # floor once per juggle (convert/move_overrides.py). Iai Stance 1,2,2's last hit (Clarent), Perfumer 1+2
    # (Hengroen), f+1+2 Durandal and u+1+2 Caliburnus. (Moves no name is known for are '#<index>': indices of the
    # game build the names were read from.)
    'bounds': {
        '#1667': True,         # IAI 1,2,2, last hit
        '#1709': True,         # PRF 1+2
        '#1758': True,         # f+1+2
        'Lon_8WP': True,       # u+1+2
    },
}
