"""Clive Rosfield from Tekken 8 (PC), in his default costume.

Only names, paths and rules live here; every byte of his model, textures, pictures, voice and moveset is read from
the player's own Tekken 8 and Tekken Tag Tournament 2 files when the importer runs. Tekken 8 keeps its movesets in an
encrypted archive: the running game's own reader saves his (tekken8/autodump.py, import_character.py runs it); the
import needs no Tekken 7.
"""
NAME = 'Clive Rosfield'
SHORT_NAME = 'CLIVE'          # his name on the 2D screens (TTT2 shows short names: KAZUYA, HEIHACHI)
TEKKEN8_ID = 36               # his FighterId in Tekken 8 (BaseCharacterItem BCI_okm_*; autodump.ROSTER; a DLC fighter)
TEKKEN8_CODE = 'okm'          # his code in Tekken 8's files (Character/Item/model/unique/okm/)
CODE = 'clv'                  # his three-letter code in the pack (not a code TTT2 or another added fighter has)
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
# his Tekken 8 costumes: the CustomizeSet CS_okm_<name> (tekken8/costume.py), player 1 and player 2
TEKKEN8 = {
    'costume': '1p',
    'costume_2p': '2p',
    # his 2P colours: the mantle alone. On his dark armour, trousers and corset (a quarter of the texels change, sRGB
    # 40-60 -> 90-110) a layer draws them far brighter than the bake, with hard black holes where it stops
    'layers': ('MI_CH_okm_bdf_1p_d',),
    # the layer darkens: 2 s^2.2 A^2.2 in the game where colours.fit takes 2 s A. A dark colour drawn so goes black, his mantle's
    # folds with it (the palette's gain, measured in the game against Tekken 8's frames)
    'layer_lift': {'MI_CH_okm_bdf_1p_d': 4.66},
    'layer_holes': ('MI_CH_okm_bdf_1p_d',),       # (his mantle's torn hem: MATERIALS)
    # his mantle's pale wear specks went to the ochre group (2P: pale yellow flecks over the red): each texel its own blend of
    # the two (convert/layerfit.py); the layer's values into its holes before sizing (dark rims round them otherwise); and where
    # the layer is out (the hem's dirt, specks both players share) the base drawn as bright as the layer draws: the lift over
    # the layer's own darkening (4.66 / 2^1.2), else those texels show as black patches
    'layer_blend': ('MI_CH_okm_bdf_1p_d',),
    'layer_bleed': ('MI_CH_okm_bdf_1p_d',),
    'base_lift': {'MI_CH_okm_bdf_1p_d': 2.03},
    # his mantle's sheen: TTT2 draws little of its folds' highlights at the shine Tekken 8's roughness gives (brightest 1%
    # 58 against Tekken 8's 119 on the same stage): its shine's strength x2.5
    'shine_gain': {'MI_CH_okm_bdf_1p_d': 2.5},
    'hair_thick': {'MI_CH_okm_har_1p': 3},        # (tekken8/bake.py thick_hair: his hair's clumps under an alpha test)
    # the shell under his armour's plates: black in its texture, seen from nowhere, and flecks through them once decimated
    # (convert/covered.py); his mantle moves, so it neither goes nor hides what is under it
    'covered': {'parts': ('bdf',), 'moving': ('MI_CH_okm_bdf_1p_d',)},
    # his neck and chest in his open collar: lit unshaded from above in TTT2 they came out twice as bright as his face and
    # orange; darkened by how much his costume shades them and, his upper chest, by how far it faces up into TTT2's light
    # (convert/occlusion.py; his face stays as it is). In the game then: neck and chest about his face's tone
    'skin_occlusion': {'materials': ('MI_CH_okm_fac_skin', 'MI_CH_okm_body_skin'), 'parts': ('bdf',),
                       'open': 0.8, 'power': 1.5, 'up': 0.9, 'keep': ('Head',)},
    # his stubble's strands whole (fah), his face apart from the rest (decimate); his hair gives up less than the default
    # his mantle's chains (1.36 m; 5 of 10 links, 4 of 8 once his summons took bone room), one sheet behind him: Lars's
    # limits per link curl it into a black ball round him (with 8 links: a ball for ~20 frames at a round's start), and
    # limits about each chain's own axes fan it out (its hem 2 m wide, its outer edge over his raised arm). Its swing per
    # 150 mm of chain (as tuned on 10 links: ~1 rad behind him in all, Tekken 8's ~60 degrees in his kicks), any length;
    # the strands (2-3 links) keep theirs
    'long_cloth': {'links': 5, 'parent': 'MUNE2_jnt',
                   'spring': dict(flags=0x60, parameters=(30.0, 10.0, 70.0), last=0.05,
                                  swing=dict(back=(0.0, 0.0, -1.0), towards=0.10, against=0.04, across=0.02, per=150.0))},
    'part_vertices': {'fah': 3060, 'fac': 6000, 'wpn1': 1700, 'wpn2': 600},
    # (the armour's many pieces give up more than the default before his hair and face do)
    'part_classes': {'big': 0.1, 'reach': 10.0, 'small': 0.2, 'lying': 3.0},
    'part_weights': {'har': 0.3},
    # his armour's metal: TTT2's reflections on a bright stage go far brighter than Tekken 8's on these plates
    'shine': {m: (None, 0.7, 0.4, None) for m in ('MI_CH_okm_bdf_1p_a', 'MI_CH_okm_bdf_1p_b', 'MI_CH_okm_bdf_1p_c')},
    # (metal's colour, strength, reflection, other greys' colour) of his swords (tekken8/bake.py dark_metal)
    'dark_metal': {'MI_CH_okm_exp_1p': (0.08, 0.3, 0.2, 0.3)},
    # his corset's red leather (ID02) and the shirt's edges in its V (ID04): the bake gives them a dull brown and near black
    # (sRGB 68 40 40, 46 44 43) where Tekken 8 shows red and white: their texels' linear means (and the shirt's folds half as
    # deep: convert/idlook.py)
    'id_look': {'MI_CH_okm_bdf_1p_a': {2: (0.12, 0.016, 0.016), 4: (0.45, 0.43, 0.41, 0.5)}},
    # (a 1 pressed early, which a later move tests: d/b+1+2,1's third hit, d+4,1,1's damage, both its hits: lasting 3
    # moves; summons8.vars_as_slots. Its variable: 4, whose id only a test of three extra properties maps to, at frame
    # 170 of his Rage Art, which TTT2's extra properties have no conditions for anyway: moveset.flag8_slots)
    'var_slots': {3: (9, 3)},
    'free_flag_vars': (4,),
}

# the vertices of his model the game skins (model.VERTEX_BUDGET): his sword and summons among them (Noctis's 56000); his
# body, face, hair, sword and 2P layer come to about 44000, his summons 25000 (80 bytes each streamed: two of him and two
# Noctises are 20 MB of the port's 84 MiB, roster.cpp kSkinningRoom)
VERTEX_BUDGET = 69000
# his hair's colours x this (model's GAIN, linear): baked as TTT2's black hairs are (sRGB ~55) it still reads brown with pale
# tips under TTT2's hair shader beside Tekken 8's black
GAIN = {'MI_CH_okm_har_1p': 0.5}
# (his cloth, weapons and creatures: Miary Zo's bound, which ran a mirror match)
SKELETON_BONES = 307

# part -> (TTT2 mesh name, the bone the mesh is bound to as a whole, draw order); fah his stubble (his sword's mesh,
# the costume's ex0: WEAPONS)
MESHES = {
    'bdf': ('clv_bdf_1p', 'KOSHI_jnt', 0),
    'fac': ('clv_fac', 'ATAMA_Joint', 2),
    'har': ('clv_har_1p', 'ATAMA_jnt_assist', 3),
    'fah': ('clv_fah_1p', 'ATAMA_jnt_assist', 4),
}

# ------------------------------------------------------------------------------------------------ weapons
# His objects (convert/summons8.py), the costume's ex0 mesh, each shown by its bone (BP_Character_OKM_Component
# SetWeaponVisibility). His moves show and hide them with the masks 0x83a6 / 0x83a7, bit n = summon n: 0 the sword in
# his right hand, 1 the sword in its scabbard on his back; 2, 3, 4, 5 are the Phoenix blades and the pike of other
# meshes (not drawn yet), 6 the wings.
_EXP = '/Game/Character/Item/model/unique/okm/extra/okm_exp_%s/meshes/SK_CH_okm_exp_%s'
_EX0 = _EXP % ('1p', '1p')
_PYA, _PIK = _EXP % ('pya', 'pya'), _EXP % ('pik', 'pik')
# his creatures, each its own mesh and clips (convert/prefabs8.py): 'kinds' the clip tables that move it, 'bones' and
# 'vertices' what it keeps. In the order that keeps part 3 of the motion pack small: a clip carries every bone before its
# creature's too
_PREFAB_MODELS = [
    # (Garuda's talons whole: at 400 vertices their feather cards' corners could not stay and the claw came out a dark
    # lump; each 3346)
    {'name': 'kal', 'weapon': 'pf_kal', 'mesh': _EXP % ('pka', 'pka_L'), 'kinds': ('pka', 'pka_l'), 'summon': 7,
     'bones': 6, 'vertices': 3400},
    {'name': 'pse', 'weapon': 'pf_pse', 'mesh': _EXP % ('pse', 'pse'), 'kinds': ('*body',), 'summon': 6, 'bones': 12,
     'vertices': 1665, 'body_clips': True, 'top': 'Spine2', 'under': 'MUNE2_jnt',
     # (two membranes under about a thousand torn feather pieces and their bones: decimated to its vertices they came out
     # as hard flat shards; each wing drawn instead as a picture of all its pieces, alpha-tested, on a low grid that
     # its bones move, the right wing the left one's picture mirrored. Lit, the side turned from the light came out
     # dark smoke and the lit one blown out white where Tekken 8's are alike from every side: drawn unlit ('glow_cut'). They
     # form and go as Tekken 8's do, by the alpha test the runtime raises over the fade (not scaled): convert/lace8.py.
     # Tekken 8's shape is whole a quarter into its fade in (10 frames: by its 3rd) and gone a quarter into its fade out
     # (25: by its 6th); the rest of each is its icy tint, its effects')
     'lace': {'texture': (512, 256), 'kind': 'glow_cut', 'dissolve': True, 'dissolve_share': 0.25}},
    # (the phoenix's wing: each feather piece needs its corners (prefabs8.thinned: vertices / 8 pieces); at 1400 175 of
    # its 1036 were kept, a sparse fan in 1+2)
    {'name': 'pho', 'weapon': 'pf_pho', 'mesh': _EXP % ('pho', 'pho'), 'kinds': ('pho',), 'summon': 8,
     'bones': 12, 'vertices': 8400},
    {'name': 'kar', 'weapon': 'pf_kar', 'mesh': _EXP % ('pka', 'pka_R'), 'kinds': ('pka', 'pka_r'), 'summon': 9,
     'bones': 6, 'vertices': 3400},
    {'name': 'smf', 'weapon': 'pf_smf', 'mesh': _EXP % ('smf', 'smf'), 'kinds': ('smf',), 'summon': 10,
     'bones': 26, 'vertices': 2500},
    {'name': 'pko', 'weapon': 'pf_pko', 'mesh': _EXP % ('pko', 'pko'), 'kinds': ('pko',), 'summon': 11,
     'bones': 6, 'vertices': 700,
     # (Shiva's ice veils: decimated to 400 they were straight-edged triangles, their torn hems gone; as grids over
     # their UV layout, a node every 20 cm, the torn outline cut back by its alpha, each with its own back face, as
     # the wings: convert/remesh8.py; 300 vertices of Torgal's for it)
     'remesh': {'step_cm': 20, 'min_area_m2': 0.05, 'one_side': True, 'mirror': True}},
    {'name': 'pts', 'weapon': 'pf_pts', 'mesh': _EXP % ('pts', 'pts'), 'kinds': ('pts',), 'summon': 12,
     # (Titan's fist and arm: 56 rocks, each on its own bone, 14352 vertices. At 12 bones the merges moved a rock up
     # to 21 cm off its path, at 24 7 cm (the cloth's room stays over its 40 bones); at 1308 vertices the big rocks,
     # the forearm's 1.2 m shell among them, came out as flat grey sheets)
     'bones': 24, 'vertices': 3000},
    {'name': 'pmi', 'weapon': 'pf_pmi', 'mesh': _EXP % ('pmi', 'pmi'), 'kinds': ('pmi',), 'summon': 13,
     'bones': 8, 'vertices': 700, 'under': 'TE_L_jnt'},      # (Leviathan: Tekken 8 holds it in his left hand)
]
PREFABS = {
    'tables': '/Game/Character/Blueprints/DataTable/MissileAnimData/okm/MAD_okm_%s',
    # the kinds of his moves' rows, by number (his blueprint's GetPcaAnim)
    'kinds_order': ('pho', 'pka', 'pts', 'pko', 'pka_l', 'pka_r', 'pmi', 'smf', 'pho_l', 'pho_r', 'pts_l', 'pts_r'),
    'dependent': {13: 3, 14: 4, 15: 5, 16: 6},      # the fades of the body rig's summons (their rows' slot 3)
    'hold_joints': ('R_Have', 'L_Have'),            # the joints the hold clips move
    'bases': ('M_CH_okm_pca', 'M_CH_okm_exp_smf', 'M_CH_okm_pmi_wave'),     # his summons' base materials (prefabs8.bake)
    'flat_colours': {'M_CH_okm_pmi_wave': (0.05, 0.11, 0.17)},  # the water round d/f+3,1's serpent: a cubemap in Tekken 8
    # Bahamut's wings: a rough metal, as pale lit in Tekken 8 as their colour; darkened by their metal share they came
    # out near black in TTT2 (prefabs8.bake)
    'metal_lit': ('MI_CH_okm_exp_pse_body',),
    # ... and in Tekken 8's frames olive-grey membranes with faint teal lines over them between teal fingers and spikes
    # (on screen about sRGB 112 117 108 and 70 135 135, its sparks up to 155 185 190); drawn unlit (the 'glow_cut' template):
    # measured on the same stage (round 4) the mean frame was sRGB 55 94 98, too dark, and the mean membrane 100 113 112,
    # too blue (a pale grey-blue sheet): each channel taken to Tekken 8's by its ratio in linear light. Drawn unlit (the
    # 'glow_cut' template): the membranes 1.45 1.66 1.84 times their colour, the frame (metal share 0.35 to 0.5 and
    # over) 0.41 1.1 1.12 times its colour, the bones' glow 1.8 times over their metal share, the scrolling tiles' lines
    # over the membranes 0.35 times (prefabs8.bake)
    'veins': {'MI_CH_okm_exp_pse_body': ((1.45, 1.66, 1.84), 1.8, 0.35, (0.41, 1.1, 1.12), (0.35, 0.5))},
    # glows baked as one still frame of their scrolling tiles, not the tiles' mean: Titan's fist's gold lines (the
    # crackling tiles along its UV1, lighting its glow colour there) and Leviathan's streaks of water
    'still_flow': ('MI_CH_okm_exp_pts', 'MI_CH_okm_exp_pmi_body'),
    # summons drawn unlit (MATERIALS 'glow', 'glow_add', 'glow_blend'): their glow and this share of their colour.
    # Titan's fist: solid dark stone under its gold lines, as Tekken 8's (its stone sRGB ~62 41 34 to 96 75 63, the
    # lines ~233 210 181): added, its lines alone over the stage, it hardly showed. Torgal: his fur's grey and white
    # a little brighter than its texture, as Tekken 8's sunlit wolf (lit by TTT2's stages it came out dark purple-blue)
    'glowing': {'MI_CH_okm_exp_pmi_body': 1.0, 'MI_CH_okm_exp_pts': 0.6, 'MI_CH_okm_exp_pho_hair': 1.0,
                'MI_CH_okm_exp_pho_feather_a': 0.55, 'MI_CH_okm_exp_pho_feather_b': 1.0, 'MI_CH_okm_exp_pko_body': 1.0,
                'MI_CH_okm_exp_pka_feather': 1.0, 'MI_CH_okm_exp_pik_body': 0.3,
                **{'MI_CH_okm_exp_smf_' + m: 1.3 for m in ('body_a', 'body_b', 'body_c', 'hair', 'hair_tail', 'hair_hs')}},
    # the phoenix's feathers: their glow's red-to-gold ramp (its colour texture along the feathers) this much brighter
    # than the bake's exposure, over a little more than half their flat red: Tekken 8's wing is red with gold-white
    # shafts and roots (its clip's brightest tenth orange to near white), where one flat red came out before; Ramuh's
    # staff darker (with 'glowing' 0.3): dark in Tekken 8 with violet glints, where its glow's mean came out lavender
    'glow_gain': {'MI_CH_okm_exp_pho_feather_a': 10.0, 'MI_CH_okm_exp_pik_body': 0.3},
    # summons whose template's shader draws twice the colour they are baked in (TTT2's unlit summon shaders: Shiva's
    # veil, baked at Tekken 8's pale blue, came out white; Ramuh's staff and the phoenix twice as bright as baked;
    # Titan's gold lines washed white; Garuda's feathers added at 1.9 times their texture's blue): baked at half
    # (prefabs8.bake), so they show the colours above
    'drawn_doubled': ('MI_CH_okm_exp_pko_body', 'MI_CH_okm_exp_pho_feather_a', 'MI_CH_okm_exp_pho_feather_b',
                      'MI_CH_okm_exp_pho_hair', 'MI_CH_okm_exp_pik_body', 'MI_CH_okm_exp_pts',
                      'MI_CH_okm_exp_pka_feather',
                      *('MI_CH_okm_exp_smf_' + m for m in ('body_a', 'body_b', 'body_c', 'hair', 'hair_tail', 'hair_hs'))),
    # the colours Tekken 8's clips show them in (linear), where the bake leaves out what makes it: Leviathan's water
    # (a blue layer over a flesh-coloured texture), Shiva's veils (a pale texture tinted blue: the colour that, covering
    # 55% of what is behind, gives the mean of her whole veil, its lit parts too, over Tekken 8's sky in d/b+2,1's clip,
    # a pale sky blue: in TTT2 it came out a faint white wisp; now the colour that, covering 80%, gives her veil's own
    # blue in d/b+2,1's and Vanagandr's clips, its median sRGB 94 139 207 over a sky of 159 177 187), Garuda's talons (a
    # rough metal, near black under Tekken 8's sky, about their green glow)
    'seen_colours': {'MI_CH_okm_exp_pmi_body': (0.045, 0.065, 0.091), 'MI_CH_okm_exp_pko_body': (0.076, 0.223, 0.658),
                     # (Titan's stone: dark grey-violet in its texture, warm dark brown in Tekken 8's frames, lit by its
                     # orange rim (Fresnel_Emissive_Color 1, 0.22, 0.06), which TTT2's unlit template has no term for:
                     # the brown that, as 'glowing' 0.6 of it, gives its stone's sRGB ~80 58 48)
                     'MI_CH_okm_exp_pts': (0.13, 0.07, 0.05),
                     'MI_CH_okm_exp_pka_body': (0.021, 0.019, 0.023)},
    # how much of what is behind them the blended ones cover (MATERIALS 'glow_blend'; times their own cut-outs)
    'see_through': {'MI_CH_okm_exp_pmi_body': 0.85, 'MI_CH_okm_exp_pko_body': 0.8, 'MI_CH_okm_exp_pho_hair': 1.0,
                    'MI_CH_okm_exp_pho_feather_a': 1.0, 'MI_CH_okm_exp_pho_feather_b': 1.0,
                    # (Torgal's fur cards: their strands' alpha averages 0.21; lit they were cut where it passed 150/255:
                    # times 2 they cover about as much, their edges soft)
                    'MI_CH_okm_exp_smf_hair': 2.0, 'MI_CH_okm_exp_smf_hair_tail': 2.0, 'MI_CH_okm_exp_smf_hair_hs': 2.0},
    'texture_size': 256,
    'models': _PREFAB_MODELS,
    # what reaches in these moves is a later box: the middle of the blade's sweep, not its tip (u/f+1 follow-ups, up,
    # d/f+2 hit on ground), and the hand's point half a metre out (u/f+2's last); d/b+2,1's ice spikes (0.74 to 2.01 m
    # ahead, not the fist's point: it fell 0.2 to 0.4 m short of an opponent splatted on the wall)
    'hit_boxes': {'#1475': (0, 2), '#1477': (0, 2), 'Okm_9RPRP': (2, 3), 'Okm_1RPLP': (2, 3)},
    # u/f+4, in the air: the toe's line to a point past the knee (TTT2 has no such points)
    'hit_spots': {'#1495': (16, 0, ('joint', 'R_Foot', (75.2, -151.5, 0.0), (0.0, 0.0, 0.0)),
                            ('joint', 'R_LowerLeg', (0.0, 500.0, 200.0), (0.0, 0.0, 0.0)))},
    # the last hit of phoenix 3,2: she is launched further than in Tekken 8 here; the path is 800 mm longer ahead (the same)
    'scene_reach': {'#1667': 800.0},
    # the loops of Wings of Light and of its walks: no row of their own, nothing hides the wings; clip 0 is as long (80)
    'body_clip_moves': {'#1602': 0, '#1604': 0, '#1605': 0, '#1606': 0, '#1607': 0},
    # the throws with Torgal: their scene stays where they began (prefabs8 HELD SCENES). 1+3 takes him 4.4 m back
    # while Torgal bites the victim 1.6 m ahead of the scene's origin; followed, the dog played 4.4 m short. #1923 is
    # its version from the opponent's left side (1+3 or 2+4)
    'held_moves': ('Okm_FLnage_n', '#1923'),
    # .. and their scene cut (prefabs8 SCENE CUTS): 2.26 m of that is one frame, 66, where Tekken 8 cuts to Torgal (he
    # teleported); taken back, and the victim thrown that much further from frame 40, where his push starts, so the
    # bite and the slash meet as in Tekken 8. #1924 is #1923's victim
    'scene_cuts': {'Okm_FLnage_n': (66, 'Okm_FLnage_y', 40), '#1923': (66, '#1924', 40)},
}
WEAPONS = [
    {'mesh': _EX0, 'bone': 'ATH_swordR_1st', 'parent': 'TE_R_jnt', 'pair': 0, 'summon': 0,
     'weights': ('ATH_swordR_1st', 'ATH_swordR_2nd')},
    {'mesh': _EX0, 'bone': 'ATH_saya_2nd', 'parent': 'MUNE2_jnt', 'pair': 1},
    {'mesh': _EX0, 'bone': 'ATH_sword_back', 'parent': 'ATH_saya_2nd', 'still': True, 'summon': 1},
    # (hit-only: his hit codes' frames; the sword's tip a point of its own, other offsets root points following them)
    {'bone': 'R_Have', 'parent': 'TE_R_jnt', 'pair': 2, 'summon': 63, 'points': {0x79: ({'offset': (0, 1000, 0)}, 0)}},
    {'bone': 'L_Have', 'parent': 'TE_L_jnt', 'pair': 3, 'summon': 63},
    # Odin's blades and Ramuh's staff: other meshes, on the same rig (the body clips carry their joints)
    {'mesh': _PYA, 'bone': 'ATH_pyaR_1st', 'parent': 'TE_R_jnt', 'pair': 4, 'summon': 3,
     'weights': ('ATH_pyaR_1st', 'ATH_pyaR_2nd')},
    {'mesh': _PYA, 'bone': 'ATH_pyaR_B_1st', 'parent': 'TE_R_jnt', 'pair': 5, 'summon': 4,
     'weights': ('ATH_pyaR_B_1st', 'ATH_pyaR_B_2nd')},
    {'mesh': _PYA, 'bone': 'ATH_pyaL_1st', 'parent': 'TE_L_jnt', 'pair': 6, 'summon': 2,
     'weights': ('ATH_pyaL_1st', 'ATH_pyaL_2nd')},
    {'mesh': _PIK, 'bone': 'ATH_pikL_1st', 'parent': 'TE_L_jnt', 'pair': 7, 'summon': 5},
    # the origin his creatures play at (convert/prefabs8.py); out always (summon 62: REST_SUMMONS)
    # (numbered below the creatures' weapons: the game makes inverse binds in number order; posed by pair 8)
    # Where he is, not held where the move began: Tekken 8 plays their clips at him (Shiva's veil hangs from his
    # shoulders all through d/b+2,1 as he lunges 1.75 m; 1+2's wing stays on his back): held at the start, the wing
    # was left 1.1 m behind him and Shiva 1.5 m
    {'bone': 'pf_ground', 'parent': 'HARA_ROT1', 'number': 591, 'channels': 8, 'summon': 62, 'ground': True,
     'held': False, 'prefab': True},
] + [
    # each creature under a still weapon of its own: numbered before its bones, shown with its summon
    {'bone': m['weapon'], 'parent': m.get('under', m.get('ground', 'pf_ground')), 'still': True, 'summon': m['summon'],
     'number': 599 - n, 'prefab': True}
    for n, m in enumerate(_PREFAB_MODELS)
]
SUMMON_MASKS = True                      # his moves' 0x83a6 / 0x83a7 rows (convert/summons8.py split_masks)
REST_SUMMONS = (0, 62)                   # out when no move says otherwise: the sword in his right hand (his generic
                                         # moves show it and hide all the rest; no reaction shows the one on his back)
                                         # and the ground origin his creatures play at (62)
WEAPON_DISMISS = r'^Okm_sKAM00_$'        # his stance starts with them so (moveset.dismiss_at_start)
# meshes TTT2's motion blur leaves out (character.ini `unblurred`: the port's title/unblurred.h): his creatures, Bahamut's
# wings on his back (pse) and the summoned blades and staff (wpn1, wpn2: WEAPONS' meshes in order), drawn sharp in Tekken
# 8, smeared into blocks by the blur as they swept past (the wings' teal fingers into soft blobs over the stage as he
# dives: round 5's crops, the same moments with and without); his body, coat, hair and sword blur as TTT2's fighters do
UNBLURRED = tuple('%s_%s' % (CODE, m['name']) for m in _PREFAB_MODELS) + ('%s_wpn1' % CODE, '%s_wpn2' % CODE)
# His own hit codes, read in a joint's frame with offsets (summons8.joint_spots): 121 the right hand's holding joint
# (y along the blade: (0, 1000, 0) is the sword's tip, (0, 1300, 0) the longer blades'), 120 the left hand's
# (the holding joints leave the hands in 18 moves, up to 3 m: Dia's shot, Garuda's claw: 'joint': summons8.AT_JOINT)
HIT_JOINTS = {121: ('R_Have', 'joint'), 120: ('L_Have', 'joint'),
              127: ('R_Have', 'joint'),     # (127: #1697, the blade's tip as on 121)
              12: ('L_Hand', 12)}           # (Leviathan's shots: lines up to 4 m from his left hand, d/b+1,1, d/f+3,1)
# his Tekken 8 effects converted (convert/effects8.py): effect id -> TTT2 body part (0 his hips, 8 / 12 his right / left
# forearm, 9 / 13 his right / left hand, 15 his right knee; Tekken 8's 120, his left hand's holding joint: 13). 2 is only
# ever stopped (it keeps this path and the trails on); the rest are the ones no recipe of TEKKEN8_DISKS draws (ids under
# 230: the projectiles' start there): Gigaflare
# (49, 226, 48: the charges; its beams, 255 and 47, are TEKKEN8_DISKS'), Deadly Embrace (60, 167, 168, 169), Leviathan's water (69, 70,
# 71, 73, 78, 79), the downthrust's fire trail (181), Scarlet Cyclone's start (28), Shiva's aura (54), Ramuh's (68),
# Heatwave's slashes (15, 16), Garuda's (77), Titan's (89), Shiva's trail (178), the wind as the wings of light open (40),
# the sparks off Odin's blade as Zantetsuken's levels 2 to 4 end (218, on his right hand's holding joint: 9)
TEKKEN8_EFFECTS = {2: 0, 49: 0, 226: 0, 48: 0, 60: 13, 167: 12, 168: 13, 169: 13,
                   69: 12, 70: 13, 71: 13, 73: 0, 78: 0, 79: 12, 181: 0, 28: 0, 54: 8, 68: 13, 15: 0, 16: 0,
                   77: 0, 89: 13, 178: 15, 40: 0, 218: 9}
TEKKEN8_TRAILS = True                   # his sword's trails (0x831c; convert/trails8.py)
# (kind 0: Tekken 8 bends the picture: clear, a slate band, white glints; kind 1, the long blades': a thin line, by Tekken 8's frames)
TEKKEN8_TRAIL_LOOKS = {0: dict(glass=True), 1: dict(clean=True)}
# (the longer blades' far joints: no weapon of their own, at a fixed place from the near ones through the moves that trail them)
# the near joints' places here make it only the last 2.5 cm of the blade: Tekken 8's is a thin line at its tip
TEKKEN8_TRAIL_SOCKETS = {'ATH_pyaR_2nd': ('ATH_pyaR_1st', (14.4, 0.0, 0.0)), 'ATH_pyaR_B_2nd': ('ATH_pyaR_B_1st', (15.4, 0.0, 0.0)),
                         'ATH_pyaR_1st': ('ATH_pyaR_1st', (14.15, 0.0, 0.0)), 'ATH_pyaR_B_1st': ('ATH_pyaR_B_1st', (15.15, 0.0, 0.0))}
# his big slash arcs (convert/disks8.py): id -> look. Requirement 1028 (by Tekken 8's clips: Heat) 1 picks the flame arcs that
# 2,2,1 and d/f+2 only have in it; TTT2 has no Heat
TEKKEN8_DISKS = {'looks': {30: 'ink', 36: 'ink', 37: 'ink', 94: 'ink', 2: 'fire', 4: 'fire', 5: 'fire', 6: 'fire', 19: 'line', 20: 'line',
                           34: 'ink',        # (2,2,1+2's swirl round both fighters as Odin's blade spins: round the blade's swing)
                           61: 'wind', 62: 'wind', 74: 'wind',
                           # bursts of flames over his body in the clip (his Phoenix Shift's shell is a mesh of 44000 vertices)
                           # (26: what is left where he went out of sight: a dark haze with thin red streaks along his
                           # path, bursts8's 'cloud'; his body burns as he goes: 'skins')
                           21: ('body', 9), 26: ('cloud', 20), 23: ('appear', 8), 22: ('feet', 10),
                           12: ('blade', 30), 1: ('jet', 8), 227: ('jet', 8), 183: ('jet', 8), 59: ('strike', 10),
                           63: ('gust', 8),
                           # Updraft's leap: Garuda's aura (66, round his body) a dark wind streak behind him as he rises
                           # and feathers, its floor's (65) a pale swirl where he leaves the floor (by Tekken 8's frames;
                           # white feathers alone were lost against the sky)
                           65: ('updraft_floor', 16), 66: ('updraft', 16),
                           # Burning Rain's fire pillar where the sword strikes the floor (Tekken 8's grows to ~3 m, f90-120)
                           182: ('column', 30),
                           58: ('swing', 27), 17: ('floor', 16), 18: ('blade', 20), 35: ('spark', 14), 29: 'fire',
                           81: ('thunder', 36), 32: ('bolts_right', 8), 33: ('bolts_right', 8),
                           # (81: Ramuh's lightning out of the sky down to his staff, Tekken 8's from f3 until the staff goes, f41)
                           83: ('bolts', 14), 82: ('bolts', 8), 84: ('bolts', 10), 87: ('bolts', 6), 88: ('bolts', 6),
                           56: ('hand', 14), 27: ('hand', 14), 13: ('ground', 16), 14: ('pillar', 12),
                           92: ('hand', 14), 93: ('jet', 10),
                           # Shiva's ice out of the floor ahead (d/b+2,1's field, phoenix 3,2's): it grows, stands, shatters
                           52: ('ice', 50), 50: ('ice', 56),
                           # Wings of Light 1 and 2's shots (Dia, Impulse): the balls of light their missile clips fly the
                           # right hand's holding joint along (convert/missiles8.py: projectiles carrying these looks);
                           # Impulse's ball going out at its path's end when no follow-up caught the victim (46)
                           189: ('missile', 'dia', 'R_Have'), 45: ('missile', 'impulse', 'R_Have'),
                           46: ('missile', 'impulse', 'R_Have'),
                           # the wings of light: their icy flash as they rise over him (on the wings' slots, 0.4 s), the ice
                           # they shatter into as they go
                           42: ('wing', 24), 43: ('wing_right', 24), 246: ('vanish', 8),
                           # Gigaflare's beam: one blue beam straight ahead from in front of him (Tekken 8's loops 0.78 s)
                           255: ('beam', 48), 47: ('beam', 78),     # (47: Follow Up Flare's, Tekken 8's loops 1.3 s)
                           # f+2,2,2's last hit: the sword's fire as a thin line of fire round the swing (Tekken 8's; its
                           # meshes were a tall striped column over him in TTT2); the wall of fire rising ahead (10, Tekken
                           # 8's a sheet rising out of the floor)
                           11: 'line', 10: ('rise', 30),
                           # Pile Driver's (80): violet lightning up from where the staff strikes; Stone Smite's hit (67):
                           # golden fire where Titan's fist lands (both a white-out over half the screen as Niagara systems)
                           80: ('zap', 18), 67: ('blast', 14),
                           # Zantetsuken's levels 2 to 4: the red aura on Odin's blade (251), the lines of level 4 (253),
                           # the dark aura as Odin's blade appears in Ultimate Zantetsuken (39, on its weapon slot): their own
                           # systems as the generic ids' (ids from 230 up, and a weapon slot's spawn, take this path)
                           251: ('niagara', 200), 253: ('niagara', 60), 39: ('niagara', 100),
                           # Ultimate Zantetsuken (level 5): its systems' colours are their materials' (HDR blue-white),
                           # out of the generic route's reach (nothing of 96, 98 and 99 was drawn, 38 a small glow): the blue
                           # slash as Odin's blade is drawn (99), Odin's sigil behind him as he waits (38), the flurry of
                           # slashes over the victim (98), the last cut through him (96)
                           99: ('zan_trail', 30), 38: ('zan_sigil', 60), 98: ('zan_ranbu', 24), 96: ('zan_last', 24),
                           # Torgal's heat as he bites (199: domes of heat haze with glowing edges): a thin golden ellipse
                           199: ('heat', 30)},
                 # the way each band's head runs round its disk (by the blades' ways in the moves that spawn them)
                 'ways': {2: 1, 5: 1, 19: 1, 4: -1, 6: -1, 20: -1, 30: -1, 36: -1, 37: -1, 61: -1, 62: -1, 74: -1, 94: -1},
                 # (61's rows give no turn; by Tekken 8's frames it stands up, as 62's rows turn it)
                 'turns': {61: (-97, 0, 0)},
                 # (the fire bands' and lines' pictures from 2's and 19's systems: 11's, the sword's fire trail, has no
                 # such emitters)
                 'source': {'ink': 30, 'blaze': 10, 'feathers': 65, 'bolts': 84, 'wing': 42, 'looks': {'fire': 2, 'line': 19},
                            'emitters': dict(base='Base', lit='Emissive', smoke='Black', blaze='Pole', feather='Base006', bolt='Core',
                                             ice='Ice_model', wing='Wing')},
                 'blades': (('R_Have', (0.0, 1000.0, 0.0)), ('L_Have', (0.0, 1000.0, 0.0))), 'conditions': {1028: 0},
                 # his body burning as the Phoenix Shift starts (Tekken 8's body look 0: his material; here flames on
                 # his body parts that go with him). Tekken 8's look burns him until he vanishes (#1649: f1-9 a molten
                 # body, hidden from f10): 9 frames of flames (each lives 12 more) and none of a move that does not hide
                 # him. Hidden, TTT2's hide leaves nothing where Tekken 8 has a dark haze and his body forming: his hides
                 # last 5 frames. The look's 60 frames go on into the moves out of it (from its f15): Tekken 8's clips
                 # show him molten through their first ~18 frames (PHX.2, .4: f50-66), fading by ~f70 (its last ~30
                 # frames: plain), so 60 - 15 - 30 = 15 frames of flames there (carry: skin8_carried); Heatwave (#1650)
                 # sets its own 30 frames (his body forming, grey): none
                 'skins': {0: dict(look='hand', parts=(2, 3, 5, 7, 8, 9, 11, 12, 13, 15, 16, 18, 19), burn=9,
                               with_hide=True, hidden=5, carry=30)},
                 # where the bursts start (convert/bursts8.py): Tekken 8's parts past TTT2's (120 / 121: the holding joints of
                 # his left / right hand) and its weapon slots (0x839d: 1 / 2 his sword, 3 / 4 the wings, 5 / 6 Odin's blade, 7 its left one) ->
                 # TTT2's parts; the sword's and the staff's ends, for the fire along one and the lightning along the other
                 'anchors': {'parts': {120: 13, 121: 9}, 'weapons': {1: 9, 2: 9, 3: 2, 4: 2, 5: 9, 6: 9, 7: 13},
                             'tools': {'sword': ('R_Have', (0.0, 1000.0, 0.0)), 'staff': ('L_Have', (0.0, 1000.0, 0.0))}},
                 # (his effects take more ids than TTT2's spare ones: these are free in his pack, the donor's are skipped)
                 'more_ids': range(3, 100)}
# (left out: Shiva's auras' (54, 178) sprites stretched along their way, in TTT2 big flat white sheets; Titan's glowing
# discs (89), in TTT2 a white flash over him)
# by Tekken 8's frames: Leviathan's spiral (73) a faint swirl round him, in TTT2 thick rings
# (a GPU emitter's role, as effects8.ROLES' sparks: a definition's role replaces the built-in one whole)
SPARKS = dict(life=(0.4, 0.15), size=(3.0, 1.0), speed=(150.0, 150.0, 150.0), lift=40.0, drag=3.0, box=(5.0, 5.0, 25.0),
              rate=40.0)
TEKKEN8_EFFECT_TUNE = {'measured': True, 'skip_materials': 'pkoAura03|Aura14',
                       'system_roles': {73: (('Splash|Core', {'alpha': 0.35}),),
                                        # (Garuda's lightning as Deadly Embrace starts: green and light, in TTT2 white
                                        # opaque bands)
                                        # its lightning planes (6 m, HDR white) are the big white starburst: smaller,
                                        # green; the wind lines green; its glows (GPU: white, the system's brightest)
                                        # a green flash; its 40 sparks (GPU: no speed read, white at 16 times) one
                                        # white disc at the hit: green sparks flying apart, as 167's at his other hand
                                        # (Tekken 8's a green flash, thin green lightning, green and teal sparks)
                                        168: (('Last_Scwv', {'colour': (0.012, 0.06, 0.018), 'add': True, 'size': 0.4}),
                                              ('^Base$', {'colour': (0.06, 0.08, 0.06), 'dim': 0.7}),
                                              ('Shitaji', {'alpha': 0.85, 'dim': 0.7, 'palette': (0.9, 3.0, 1.2), 'size': (50.0, 8.0)}),
                                              ('Particle', dict(SPARKS, palette=(0.06, 0.19, 0.08)))),
                                        167: (('Particle', dict(SPARKS, palette=(0.05, 0.17, 0.15))),),
                                        # (Gigaflare's charge: its tornado meshes and lines were white and teal streaks
                                        # fanning out over the screen in TTT2, its lightning sphere (2 m across) and its
                                        # frost shockwave (a shell growing to 3 m) glassy white bubbles round him; Tekken
                                        # 8's charge is lightning and flares at his hands)
                                        49: (('^Tornade|^Line$|^Shockwave$', {'drop': True}),),
                                        226: (('^Line$|^Lightning(02)?$|^Circle$', {'drop': True}),),
                                        48: (('^Line$|^Lightning(02)?$|^Circle$', {'drop': True}),),
                                        # (the wind as the wings come (40): Tekken 8's a thin pink arc round him, in TTT2
                                        # an opaque white dome over him: its lightning line pink and dimmer, its wave (a
                                        # heat haze in Tekken 8, a glassy white dome in TTT2 even dimmed) left out)
                                        40: (('^Core003$', {'colour': (1.0, 0.25, 0.42), 'dim': 0.4}),
                                             ('^Core004$', {'drop': True}))}}
# (Lars's own effect, a purple lightning: in Victor's moves it came up as a white square a metre wide)
DONOR_EFFECTS = False

# Tekken 8 material instance -> (template, use its normal map, keep the colour texture's alpha); None: left out.
# Only exceptions: tekken8/bake.classify picks the kind from the material's base material and name.
MATERIALS = {
    'MI_CH_okm_add_tealine': None,                # the wet line along the lower eyelids (an additive layer)
    'MI_CH_okm_eye_ao': None,                     # the eyes' ambient occlusion shell (a blurred dark layer)
    'MI_Cal_Mesh': None,                          # an invisible mesh the game measures the body with
    # his stubble: strand cards with a base material of its own, blended (alpha-tested, as hair, each strand solid and dark)
    'MI_CH_okm_fah_1p': ('overlay', False, True),
    'MI_CH_okm_bdf_1p_d': ('cloth', True, True),  # his mantle: 1.5% of it cut away, all of it the torn hem (classify's rule: 2%)
    'MI_CH_okm_exp_smf_body_d': None,             # Torgal's crests of another form: not on him in the moves that use him
    'MI_CH_okm_exp_smf_add_tealine': None,        # (an additive layer, as the fighter's)
    # his summons, drawn unlit (Tekken 8 lights them mostly by their own glow; TTT2's lit cloth made them dark grey
    # lumps under its motion blur): their colour and glow as prefabs8.bake makes them (PREFABS 'glowing', 'seen_colours',
    # 'see_through'). Titan's fist and Garuda's feathers are added to the picture (their lines of light over what is
    # behind); the phoenix's feathers, Leviathan's water and Shiva's veils are blended over it (see-through, but in
    # their own colour: added, the bright stage behind them washed them out to white); the talons, the blades and
    # Titan's fist solid. Torgal too (lit, TTT2's stages turned his grey fur dark purple-blue; Tekken 8's is a pale
    # sunlit wolf): his body solid, his fur cards blended (their alpha; the cut template has no alpha test)
    'MI_CH_okm_exp_pmi_body': ('glow_blend', False, False),
    'MI_CH_okm_exp_pmi_wave': ('glow_add', False, False),     # (the water round the serpent: a flat colour)
    'MI_CH_okm_exp_pts': ('glow', False, False),
    'MI_CH_okm_exp_smf_body_a': ('glow', False, False),
    'MI_CH_okm_exp_smf_body_b': ('glow', False, False),
    'MI_CH_okm_exp_smf_body_c': ('glow', False, False),
    'MI_CH_okm_exp_smf_hair': ('glow_blend', False, True),
    'MI_CH_okm_exp_smf_hair_tail': ('glow_blend', False, True),
    'MI_CH_okm_exp_smf_hair_hs': ('glow_blend', False, True),
    'MI_CH_okm_exp_pho_hair': ('glow_blend', False, True),
    'MI_CH_okm_exp_pho_feather_a': ('glow_blend', False, True),
    'MI_CH_okm_exp_pho_feather_b': ('glow_blend', False, True),
    'MI_CH_okm_exp_pko_body': ('glow_blend', False, True),
    'MI_CH_okm_exp_pka_feather': ('glow_add', False, True),
    'MI_CH_okm_exp_pka_body': ('glow', False, False),
    'MI_CH_okm_exp_pya_body': ('glow', False, False),
    'MI_CH_okm_exp_pik_body': ('glow', False, False),
    'MI_CH_okm_exp_pik_crystal': ('glow', False, False),
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
    # his summons (MATERIALS): TTT2's own light spear, cmn_opu_LightSpear in data017, its glow layer (poly 2: unlit,
    # added to the picture: src 1, dst 162) and its core (poly 1: unlit, solid); and Devil Jin's glow on his face (poly
    # 9: the spear's flags and vertex type, blended: src 1, dst 1)
    'glow_add': (0x285AE2C4, 'cmn_opu_LightSpear', 2),
    'glow': (0x285AE2C4, 'cmn_opu_LightSpear', 1),
    'glow_blend': ('dvj.nud', 'cha:kao_O_OBJ', 9),
    # Bahamut's wings (the pse lace pictures, PREFABS 'lace' kind): unlit, so alike from every side as Tekken 8's. TTT2's
    # own wings (Devil Jin's, the angel, fairy and butterfly wings) are doubled one-sided sheets of its lit cloth
    # shaders, dark or translucent; its alpha-tested glows (Panda's pan_upb_Def1pGlow: 0x21001001, alpha test 2/4) are
    # unlit, and a skinned one of theirs is Mokujin's sword's core, mok_1p_sword in data014 (poly 1: 0x21001001, src 0,
    # dst 0, weighted vertices); the alpha test is the cloth's ('colour_alpha'), which the dissolve raises
    'glow_cut': (0xC27C81BA, 'mok_1p_sword_O_OBJ_nomerge', 1),
}
# where the templates' own textures are (their average colours fill the slots Tekken 8 has nothing for)
TEMPLATE_TEXTURES = ['jun.nut', 0x24F8AE59, 0x277C7A37, 0xAD9B60F0, 0x900FD8C4]

# ------------------------------------------------------------------------------------------------ pictures
# his Tekken 8 UI pictures (convert/art.py): a bust, his whole body, each with where his face is in it (the eyes'
# centre x, y and eyes-to-chin, in its pixels), his name, and his costume picture
_UI = '/Game/UI/Rep_Texture'
ART = {
    'bust': (_UI + '/Makuai_Character_L/T_UI_Makuai_Character_L_okm', (890, 1260, 425)),
    'body': (_UI + '_Other/ST01_Arena/Character_Full/T_okm_1p_C', (743, 237, 98)),
    'name': _UI + '/HUD_Character_Name/T_UI_HUD_Character_Name_okm',
    'costume': _UI + '/CS_Slot_Thumb/okm/T_UI_CS_Character_Slot_okm_1p',  # the costume chooser's picture
}

# ------------------------------------------------------------------------------------------------ voice
# his Tekken 8 voice events (tekken8/voice.py)
VOICE = 'okm'

# ------------------------------------------------------------------------------------------------ moveset
MOVESET = {
    'name': '[CLIVE]',          # the moveset's name (in its header)
    # his round-start move (the donor's is kept: its mode checks are Tekken 8's)
    'drop_moves': r'^Okm_Direct$|^#20(0[89]|1[013])$',
    # the donor's round-start list keeps its targets except its own moves
    'direct': [(r'^La_sKAM00_$', 'move', ['Okm_sKAM00_']),                      # Lars's stance -> his
               (r'^(la|mk)_s', 'anim', ['okm_s%02d' % k for k in range(3)]),    # intros
               (r'^la_w', 'anim', ['okm_w%02d' % k for k in range(3)])],        # win poses
    # TTT2 bounds (Tekken 8 has none, and his tornados do not become any): an air hit slams the opponent into the
    # floor once per juggle (convert/move_overrides.py). f+3 Knight's Gambit, f,F+2 Soul Cleave, f+2,2,2's last hit
    # (Burning Chain) and jump 1 (Griffin Hunter) out of every jump, on time or late (bake_air8's copies of the air
    # moves are made after the bounds, so they bound alike). (Moves no name is known for are '#<index>': indices of
    # the game build the names were read from.)
    'bounds': {
        'Okm_6LK': True,       # f+3
        'Okm_66RP': True,      # f,F+2
        '#1632': True,         # f+2,2,2, last hit
        '#1451': True,         # jump 1: straight up
        '#1452': True,         # ... straight up, late
        '#1453': True,         # ... forward (u/f+1 too)
        '#1454': True,         # ... forward, late
        '#1455': True,         # ... out of #1423, late
        '#1456': True,         # ... back (u/b+1 too)
        '#1457': True,         # ... back, late
    },
    # the generic throw keeps the donor's row, active at 12 only: Tekken 8's frames
    'active_frames': {'Thrmv_B2_01': (15, 17),
                       # f,f+2: pushed back from where Tekken 8 lets him run in, the blade comes down one frame later
                       'Okm_66RP': (19, 21)},
}

# ------------------------------------------------------------------------------------------------ ZAN gauge
# His gauge (convert/gauge.py), its numbers as Tekken 8's executable gives them for his fighter id: five levels of 50 (its
# practice setter's 0 .. 200), nothing from damage: only his moves' 0x8232 fill and empty it. Off unless the player turns
# it on in his character.ini (the user's choice): without it his 1+4 is its plain version
GAUGE = dict(max=200, stock=50, gain=(0, 0, 0, 0), on=False, name='ZAN gauge (his meter)',
             # its HUD (convert/gauge8.py)
             hud8=dict(folder='/Game/UI/Widget/HUD/PowIcon/okm', picture='T_UI_HUD_Pow_okm_%s', widget='WBP_UI_HUD_Pow_okm',
                       animations=('Anim_LevelUp', 'Anim_LevelUp_Max'),
                       pictures=dict(mask='Gauge_Mask', back='Gauge_BG', effect_frame='Gauge_Effect_Frame',
                                     normal_frame='Gauge_Normal_Frame', pink='Gauge_Pink', edge_light='Gauge_Edge_Light',
                                     frame='Gauge_Frame', white='Gauge_White', white_add='Gauge_White_Add', flash='Gauge_Add',
                                     circle='Gauge_LvUP_Effect_SingleLine', max_light='Gauge_Max_Light',
                                     frame_effect='Gauge_Frame_Effect', num='Num', num_edge='Num_Edge', num_add='Num_Add'),
                       layers=dict(circle1='Image_CircleLine_1', circle2='Image_CircleLine_2',
                                   flash='MI_UI_HUD_Pow_okm_Gauge_Add', num='MI_UI_HUD_Pow_okm_Num',
                                   edge='MI_UI_HUD_Pow_okm_Num_Edge', add='MI_UI_HUD_Pow_okm_Num_Edge_Eff')))
# 452: Heat activation not locked, never locked here. It is in his 1+4's rows (the level moves, the gain on contact); every other
# list naming it also needs Heat (1028, 442), which stay false
MOVESET['true_requirements'] = ((452, 0),)
# His 1+4 at a level: two amounts (plain, Phoenix) under a flag slot's test, its ticks and the victim's last points
MOVESET['gated_damage8'] = True
