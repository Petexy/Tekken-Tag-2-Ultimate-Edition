"""Azazel from Tekken 8 (PC), in his one costume, at his Tekken 8 size.

Only names, paths and rules live here; every byte of his model, textures, pictures, voice and moveset is read from
the player's own Tekken 8 and Tekken Tag Tournament 2 files when the importer runs. Tekken 8 keeps its movesets in an
encrypted archive: the running game's own reader saves his (tekken8/autodump.py, import_character.py runs it); the
import needs no Tekken 7.

His size: Tekken 8 plays his clips (made on its standard rig, SKB_CH_got_base_msl: hips 115 cm) on his proportion
pose (PRB_CH_got_msl, which his mesh is bound in: hips 207 cm, legs 1.8 times as long, head joint 359 cm). His TTT2
skeleton is built from that bind (skeleton.build: size scale 2070 / 1150 = 1.8) and his clips' root motion is measured
against the standard rig's legs (tekken8/anim.py: root scale = his skeleton's legs before its scale / the standard
rig's = 1.0), so the game moves him 1.8 times as far as the clips' numbers, as far as his legs step.
"""
NAME = 'Azazel'
SHORT_NAME = 'AZAZEL'         # his name on the 2D screens (TTT2 shows short names: KAZUYA, HEIHACHI)
TEKKEN8_ID = 32               # his FighterId in Tekken 8 (BaseCharacterItem BCI_got_fac; autodump.ROSTER; a boss)
TEKKEN8_CODE = 'got'          # his code in Tekken 8's files (Character/Item/model/unique/got/)
CODE = 'aza'                  # his three-letter code in the pack (not a code TTT2 or another added fighter has)
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
# his Tekken 8 costume: the CustomizeSet CS_got_1p (tekken8/costume.py). Tekken 8 has no 2P set of his (only CS_got_1p):
# player 2 wears the same colours, as in Tekken 8 (no 2P colour layers)
TEKKEN8 = {
    'costume': '1p',
    # his tail: 8 joints from his hips back (4.3 m), Tekken 8's dynamic bones (DYB_CH_got_fac: each joint turning at
    # most 20 to 60 degrees sideways, 20 down and 50 up, colliding with a ground plane): swinging extra bones
    # (tekken8/cloth.py bone_chains). His stance stands high on his toes (ankles 0.6 m up, toe joints 0.3: his claws
    # reach the floor) and leans forward, which would hold the tail a metre over the floor behind him: it rests as
    # Tekken 8's lies in the stance, bent down onto the floor (its joints 150 mm up: the tail is about 300 thick).
    # TTT2 has no floor: its springs let it swing up (about local Z, +) and sideways (about Y) from that rest, not
    # down, pulled down onto it as the hair's are (gravity 70, half way back 30, damped 40). The two short pieces
    # under his feet (PHY_L/R_Foot, 22 cm, also on the ground plane) stay on the feet as modelled: he stands on his
    # toes, they hang under his raised heels
    'bone_chains': [{'root': 'PHY_Hip__a001', 'floor': 150.0,
                     'spring': dict(flags=0x60, parameters=(30.0, 70.0, 40.0), limits=(0.25, -0.25, 0.5, -0.02),
                                    last=0.2)}],
    # his bandages (MI_CH_got_clothbandage): Tekken 8 simulates the drawn section itself (its particles are its own
    # vertices, no proxy mesh), its loose strips (up to 2.4 m long, from his shoulders, arms, chest wrap and legs)
    # moving up to a metre. Skinned as modelled they stood out behind him as long thin rods: they swing as cloth
    # (tekken8/cloth.pieces drawn_sims; the chest wrap itself, half its particles within 6 cm, stays as modelled)
    'drawn_cloth': r'^(cloth_aShape|polySurfaceShape164)$',
    # his crystals and vortices are Tekken 8 projectile rows spawned from his ground origin (limb 125, offsets from the
    # floor): TTT2 spawns from his hips (limb 0), so their up offsets are lowered by his hips' height over the floor at
    # each spawn's frame, as the move's clip has them ('clip': 1140 to 1540 mm as his crystals rise; convert/moveset.py
    # PROJ_GROUND8)
    'projectile_ground': 'clip',
    # his beam (1+2, and the one f,f+1+2 shoots into the opponent held over him): Tekken 8's beam kind 17 as a TTT2
    # laser kind (convert/moveset.py BEAM8; None: a beam with no kind of its own, his intro's); its reach frame by frame
    # is his Tekken 8 pushback the beam names
    'beam': {17: 0, None: 0},
    # how a laser is drawn: a TTT2 fighter's laser effect (and the meshes it draws) copied into his pack as its effect
    # 100 (convert/moveset.py BEAM_LOOK; Lars has none: the beam hit unseen): Devil Jin's red one, its colour tracks
    # tinted violet (Tekken 8's beam: violet, its brightest emitters 0.1-0.25 red to 1 blue)
    'beam_look': ('dvj', (0.55, 0.2, 1.0)),
}

# his height to the port's fight camera (character.ini camera: title/fight_camera.cpp), in mm from his body's lowest
# point (his feet's spheres, 350 mm up as he stands) to the top of his horns and wings (4.3 m over the floor): the
# camera frames him whole, up and back as far as that needs
CAMERA = 3950

# his body's size to the fight (character.ini body: title/giant_body.cpp), times a man's: his skeleton's scale. His hurt
# and push spheres grow with it (no gaps between them, his belly and claws push), and a man-sized fighter counts him
# 600 mm per 1 over a man's bigger in the distance between bodies, as the title's Mushroom Battle counts a grown fighter
BODY = 1.8

# the vertices of his model the game skins (model.VERTEX_BUDGET): his whole body is one mesh of 96127 (Victor's,
# Clive's 56000)
VERTEX_BUDGET = 56000

# part -> (TTT2 mesh name, the bone the mesh is bound to as a whole, draw order): his one part, the face item, holds
# his whole body (SK_CH_got_fac_msl)
MESHES = {
    'fac': ('aza_fac', 'KOSHI_jnt', 0),
}
# (Lars's own effect, a purple lightning: in Victor's moves it came up as a white square a metre wide)
DONOR_EFFECTS = False

# Tekken 8 material instance -> (template, use its normal map, keep the colour texture's alpha); None: left out.
# Only exceptions: tekken8/bake.classify picks the kind from the material's base material and name.
MATERIALS = {
    'MI_CH_got_add_tealine': None,                # the wet line along the lower eyelids (an additive layer)
    'MI_CH_got_ao': None,                         # the eyes' ambient occlusion shell (a blurred dark layer)
    'MI_Cal_Mesh': None,                          # an invisible mesh the game measures the body with
}

# Material templates in the donor's files: Jun's, as for every added fighter (they are only shaders)
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
# his Tekken 8 UI pictures (convert/art.py), each with where his face is in it (the eyes' centre x, y and eyes-to-chin,
# in its pixels). Tekken 8 has no bust, full-body or costume picture of him: his fight HUD's head (512 x 256, on a
# transparent background, his snout to the left) is the bust, the artwork of his Arcade ending (3840 x 2160, with its
# background: the big portraits fade it out at their edges) his whole body (its x left of his eye, 1275: his snout
# stays in the picture), and the costume chooser's picture (124 x 304, standing fighters) is cut from his boss
# interlude's artwork (4408 x 2400, transparent: his head, neck and chest, between his crystal wings)
_UI = '/Game/UI/Rep_Texture'
ART = {
    'bust': (_UI + '/HUD_Character_Icon_L/T_UI_HUD_Character_Icon_L_got', (150, 80, 90)),
    'body': (_UI + '/AC_Clear/T_UI_AC_Clear_got', (1150, 540, 128)),
    'name': _UI + '/HUD_Character_Name/T_UI_HUD_Character_Name_got',
    'costume': ('/Game/UI/Widget/Makuai_got/Texture/T_UI_Makuai_Boss_CH', (980, 200, 2000, 2400)),
}

# ------------------------------------------------------------------------------------------------ voice
# his Tekken 8 voice events (tekken8/voice.py)
VOICE = 'got'

# ------------------------------------------------------------------------------------------------ moveset
MOVESET = {
    'name': '[AZAZEL]',         # the moveset's name (in its header)
    # his throws' victims (and those of some knockdowns) stay where Tekken 8 leaves them as they go down, facing as
    # they lie (convert/moveset.py handoffs8), as for every Tekken 8 fighter since Clive
    'keep_body_handoffs': True,
    # his round-start move (the donor's is kept: its mode checks are Tekken 8's): his alias 0, which no name is known
    # for (moves no name is known for are named by their key, 'key:<+0x00>': it stays when an update of Tekken 8 adds
    # moves, their index does not)
    # and his story intro (warping in: its rows test Tekken 8's story mode only)
    'drop_moves': r'^(key:9599cd3e|key:2f8961ea)$',
    # his three throws (1+3, 2+4, f,f+1+2) have TTT2's generic throw names, which would make them the donor's moves
    # (Lars's grab animation on his giant body: the grab 1.8 to 2.7 m up, over a man's head): they stay his own, with
    # his clips, Tekken 8's hit boxes (his left claw, frames 14 to 17) and his lists
    'own_moves': r'^(key:004b6573|key:7373dc04|key:cecc6eeb)$',
    # d+3+4's first crystal pillar is a projectile: its whiff test (3 pillars after a hit, the 4-pillar chain after a
    # whiff) means the pillar hit no one (convert/moveset.py PROJECTILE_WHIFF; TTT2's whiff test sees the move's own
    # lines only, which never touch)
    'projectile_whiffs': r'^key:c353a395$',
    # in his throws the game moves both bodies by his skeleton's scale (1.8) on the floor and by about 1.19 in height
    # (1.196 with Bob, 1.192 with Kuma, 1.120 with Xiaoyu: measured): the man flew 1.8 times as far from his claw as
    # Tekken 8 has him and 0.7 m too high, and he sank 0.8 m into the floor. His victims' ground paths are divided by
    # 1.8, the heights of his throws' clips scaled by 1.8 / 1.19 and his victims' by 1 / 1.19 (convert/moveset.py
    # THROW_PAIRS8), so the man is in his hand where Tekken 8 has him
    'victim_ground': True,
    'throw_height': 1.19,
    # the donor's round-start list keeps its targets except its own moves: Lars's stance -> his (his alias 1), Lars's
    # intros -> his three (his round-start list's), Lars's win poses -> the one of his intros that stays in place (his
    # moveset has no win pose: Tekken 8's is a scene of its own; the others walk him 1.3 and 0.5 m forward)
    'direct': [(r'^La_sKAM00_$', 'move', ['key:642bbb5e']),
               (r'^(la|mk)_s', 'anim', ['key:a54cf917', 'key:df94551b', 'key:af8628ce']),
               (r'^la_w', 'anim', ['key:af8628ce'])],
    # TTT2 bounds (Tekken 8 has none, and his tornados do not become any): an air hit slams the opponent into the
    # floor once per juggle (convert/move_overrides.py). His bounds are the moves that bound in Tekken 6 (the user's
    # choice), where his moveset has the same inputs, active frames and damage as Tekken 8's: each hit of the strings
    # that bounds there. (Moves no name is known for are named by their key, 'key:<+0x00>': it stays when an update of
    # Tekken 8 adds moves, their index does not.)
    'bounds': {
        'key:5fef6935': True,         # 1 (its hit; not the crystal pillar after it)
        'key:d4171cdc': True,         # u+1, u/f+1 (jumping)
        'key:67f553e3': True,         # u/f+1+2 (jumping)
        'key:d3ac3bf4': True,         # u+1+2, u/b+1, u/b+1+2 (jumping)
        'key:6368546c': True,         # 2,2: the second hit
        'key:b7f95752': True,         # f+2,1+2: the second hit
        'key:1f0f8468': True,         # d+1+2
        'key:96fcb2e8': True,         # u+3, u+4 (jumping)
        'key:256b2955': True,         # d+1, d/b+1
        'key:731f7cde': True,         # d+2
        'key:edbe0423': True,         # d+3
        'key:d8362bdc': True,         # d+3,4
        'key:da453a5c': True,         # d+4, d/b+4
        'key:cdcbba80': True,         # d+4,3
        'key:2c6d9689': True,         # d+4,3,4
        'key:de2b05d6': True,         # d+4,3,4,3
        'key:758adfbc': True,         # d/f+1+2
        'key:9d2081c8': True,         # 3: its three hits
        'key:4381350a': True,
        'key:23a68343': True,
        'key:baed6e79': True,         # u+3+4: each of its distances
        'key:c6b82fe6': True,
        'key:ef8e5d3f': True,
        'key:a74766fa': True,
    },
}

# Two of his attacks hit from his ground origin with a size TTT2's two lines cannot have (Tekken 8 hit boxes with a
# radius): the All Direction Attack's 16 waves (4: a ball of 10 m round his feet, one frame each, 6 frames apart) and the
# crystal prison's ground shock (d/f+3+4: a disc of 4 m, 1 m high, 2.1 m ahead of him, frames 80 to 90). Each is thrown
# as a TTT2 projectile instead (convert/moveset.py thrown_rows): a cylinder that stays where it is spawned (speed 0),
# for the frames Tekken 8's box is active (spawned the frame before: a projectile shows the frame after its row), with
# the move's own hit level and hit condition; offsets from his hips (mm: forward, up; 'floor': up from the floor under
# him), its height half the cylinder's
_WAVES = {'key:291ef025': 200, 'key:34482114': 206, 'key:220ab289': 212, 'key:ac5d15b8': 218, 'key:a42d777c': 224,
          'key:b13675f8': 230, 'key:3bf2a77c': 236, 'key:65fe47f6': 242, 'key:746cccf3': 248, 'key:eb40b767': 254,
          'key:b370c60c': 260, 'key:da2cd72a': 266, 'key:cb390305': 272, 'key:3e5ffb98': 278, 'key:54ccddfe': 284,
          'key:c4ba50e4': 290}
# A wave that hits ends the attack (its list's on-hit row into the stance: convert/moveset.py THROWN_FIRST)
THROWN = {key: dict(frame=f - 1, forward=0, up=0, speed=0, frames=1, radius=10000, height=10000, ends_on_hit=True)
          for key, f in _WAVES.items()}
THROWN['key:477c5f91'] = dict(frame=79, forward=2100, up=500, floor=True, speed=0, frames=11, radius=4000, height=500)

# his tail's sweeps (d/b+3,3: key:f8d22c42 and key:90f6fb65) hit from his hips to a point 2.5 m off them in the frame of
# Tekken 8's Hip joint, which his tail hangs from (convert/summons8.py JOINT POINTS); TTT2 had the hips alone
HIT_JOINTS = {3: ('Hip', 3)}

# his Tekken 8 effects converted (convert/effects8.py): effect id -> TTT2 body part (0 his hips, 5 his head, 13 his left
# hand; 'floor': placed from the floor under it): 10 the beam's charge at his mouth (1+2), 20 the small vortex (d/b+2,1),
# 21 the vertical vortex (b+3+4, d/b+3+4), 22 the large vortex (b+1+2), 23 the crystal prison (d/f+3+4), 26 his warp
# (u+3+4), 31 / 32 the All Direction Attack's charge and release (4)
TEKKEN8_EFFECTS = {10: 5, 20: 13, 21: (0, 'floor'), 22: (0, 'floor'), 23: (0, 'floor'), 26: (0, 'floor'),
                   31: (0, 'floor'), 32: (0, 'floor')}
# how they are drawn (convert/effects8.py): as the emitters' own scripts draw them ('measured': the plain reading drew his
# vortices' wind planes as opaque purple sheets at his feet); animated meshes (VAT_) left out (a still pose of one is
# a blob). 'offset' (cm: ahead, right, up in the frame the effect is spawned in): the crystal prison's emitters 2 m
# ahead of where it is spawned (their SystemLocation modules: 200), on the man it holds; the vertical vortex is spawned
# while he rears up (its frame turned: 150 'ahead' drew its rings 1.5 m higher, 150 'up' behind him), so its rings go
# ahead as -150 'up' (its hits 1 and 2 m ahead; drawn round him without)
TEKKEN8_EFFECT_TUNE = {'measured': True, 'skip_materials': r'^.*VAT_',
                       'offset': {23: (200.0, 0.0, 0.0), 21: (0.0, 0.0, -150.0)},
                       # the prison's darkened floor and the All Direction Attack charge's dark ground (dark discs:
                       # a dark band across the stage, a black column facing the camera) left out, and the prison's
                       # dark swirl (4 m wide, 2.25 m up: edge on to the camera, an opaque dark band across the stage
                       # for 30 frames); the prison's centre glow (a sprite up to 250 m, colours in the tens) smaller
                       # and dimmer and its rings (4 m, white, added up) dimmer: the screen white for 12 frames (the
                       # rest of its flash violet); the large vortex's crystal bits (GPU
                       # emitters drawn white, their mesh scale growing to 75: opaque white polygons up to 1.5 m)
                       # violet as the small vortex's and a tenth of the size
                       'system_roles': {23: ((r'^DarkFloor$', {'drop': True}),
                                             (r'^Center_glow02$', {'dim': 0.02, 'size': 0.4}),
                                             (r'^Swirl_Aura001$', {'drop': True}),
                                             (r'^Ring(_Aura)?$', {'dim': 0.3})),
                                        31: ((r'^Shitaji$', {'drop': True}),),
                                        22: ((r'^BitA$', {'paint': (0.45, 0.15, 1.0), 'scale': 0.1}),)}}

# ------------------------------------------------------------------------------------------------ command list
# his command list in Practice (convert/movelist_rows.py). Tekken 8 has none of his (no .mvl, no texts), so what it shows
# and the names are ours: a move by its name key and the name we give it (a plain string: a title line). Each input
# and demo is walked out of his converted moveset's rows, so they follow his moveset (4 is what his rows make it: the
# All Direction Attack). Not in it: moves his stance has no input for (4 from a side step, f+3 while running), and
# u/f+1+2 from further away (another move on the same input; the list's demos stand 2 m apart). His warp (u+3+4) is
# four moves picked by the distance to the opponent as Tekken 8 picks them (within 3.5 m, from 4 m, from 6.5 m, and
# plain u+3+4 between 3.5 and 4 m): each further one is an entry of its own whose demo stands that far apart
COMMANDS = [
    'Strikes',
    ('key:5fef6935', 'Crystal Pillar'),             # 1, then a pillar 2 m ahead
    ('key:5d8555de', 'Talon'),                      # 2
    ('key:6368546c', 'Talon Combo'),                # 2,2
    ('key:9d2081c8', 'Triple Lash'),                # 3 (three hits)
    ('key:291ef025', 'All Direction Attack'),       # 4
    ('key:756bd583', 'Beam'),                       # 1+2
    ('key:6ecebd8e', 'Snap Claw'),                  # f+1
    ('key:0d526f6e', 'Snap Claw Slam'),             # f+1,2
    ('key:c7d917e5', 'High Talon'),                 # f+2
    ('key:b7f95752', 'Talon Hammer'),               # f+2,1+2
    ('key:68b1c278', 'Rushing Blow'),               # f+1+2
    ('key:e0fd03e3', 'Charging Claw'),              # f,F+1
    ('key:34fcd66e', 'Seizing Claw'),               # b+1
    ('key:b3594e18', 'Hammer Fist'),                # b+2
    ('key:d4171cdc', 'Leaping Claws'),              # u+1
    ('key:d3ac3bf4', 'Diving Claws'),               # u+1+2
    ('key:96fcb2e8', 'Leaping Blow'),               # u+3
    ('key:256b2955', 'Crushing Claw'),              # d+1
    ('key:55316113', 'Crushing Claw Combo'),        # d+1,2
    ('key:731f7cde', 'Downward Talon'),             # d+2
    ('key:edbe0423', 'Talon Kick'),                 # d+3
    ('key:d8362bdc', 'Talon Kick Combo'),           # d+3,4
    ('key:da453a5c', 'Rake'),                       # d+4
    ('key:cdcbba80', 'Double Rake'),                # d+4,3
    ('key:2c6d9689', 'Triple Rake'),                # d+4,3,4
    ('key:de2b05d6', 'Rake Storm'),                 # d+4,3,4,3
    ('key:1f0f8468', 'Sweeping Blow'),              # d+1+2
    ('key:30c54aea', 'Rising Claw'),                # d/f+1
    ('key:188f440d', 'Low Talon'),                  # d/f+2
    ('key:758adfbc', 'Double Hammer'),              # d/f+1+2
    ('key:f8d22c42', 'Tail Sweep'),                 # d/b+3
    ('key:90f6fb65', 'Double Tail Sweep'),          # d/b+3,3
    'Crystal Arts',
    ('key:19ef1f6e', 'Crystal Swipe'),              # d/b+2
    ('key:8237463d', 'Vortex'),                     # d/b+2,1
    ('key:e9ed7dad', 'Great Vortex'),               # b+1+2
    ('key:bbc4871e', 'Rising Vortex'),              # b+3+4
    ('key:b0ccee0a', 'Vortex Wall'),                # d/b+3+4
    ('key:c353a395', 'Crystal Pillars'),            # d+3+4
    ('key:477c5f91', 'Crystal Prison'),             # d/f+3+4
    ('key:ef8e5d3f', 'Warp'),                       # u+3+4 (within 3.5 m)
    ('key:baed6e79', 'Warp Strike', {'distance': 3750}),        # u+3+4 (3.5 to 4 m)
    ('key:c6b82fe6', 'Long Warp', {'distance': 5000}),          # u+3+4 (from 4 m)
    ('key:a74766fa', 'Far Warp', {'distance': 7000}),           # u+3+4 (from 6.5 m)
    'Throws',
    ('key:004b6573', 'Lifting Throw'),              # 1+3
    ('key:7373dc04', 'Hoisting Throw'),             # 2+4
    ('key:cecc6eeb', 'Crushing Ascent'),            # f,f+1+2
]
