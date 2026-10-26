"""Tekken 8's joint names -> the Tekken 7 names convert/skeleton.py works with, and how each joint moves when the
model is re-posed (skeleton.repose).

Tekken 8's fighter rig (the _msl "muscle rig" meshes, 550 joints for Reina) has the Tekken 7 skeleton's roles under
other names, plus ~250 face joints and ~245 helpers:
* Root / Top / Trans / Rot / MUKI instead of Tekken 7's MODEL_00 / BODY_SCALE__group / BASE: Trans and Rot sit
  where Tekken 7's BASE and Hip do (112.7 cm), MUKI ("facing") too. Tekken 8's Hip is the pelvis below them
  (97 cm, the legs' pivot, parent of Spine1 and C_Leg): Rot anchors KOSHI_jnt (Tekken 7's Hip), Hip and C_Leg
  only give it their skin weights.
* UpperArm / LowerArm / UpperLeg / LowerLeg = Arm / ForeArm / UpLeg / Leg; fingers count from 0, the metacarpal
  (Index0 = FingerBase, Middle0 / Ring0 / Pinky0 = Middle / Ring / Pinky), the thumb's 0..2 are Tekken 7's 1..3.
* ADR_ helpers (twist, muscle and half-rotation joints) hold most of the body's skin weight, under parents that are
  not the limb they follow: the upper arm's twist joints hang under L_Shoulder (through ADR_L_DeltioidUp_bnd), the
  thigh's under C_Leg (ADR_L_Thigh_bnd). Each goes by name to the Tekken 7 helper of its place (HELPERS: twist
  joints at a quarter / half / three quarters of a segment -> Arm_Top / Arm_Mid / Arm_Btm and the like), so its
  weights land on the TTT2 bone that follows that limb, never on its parent's. Checked by their bind positions: each
  sits on the segment of the TTT2 bone its weights go to.
* The face rig is new: brows, eyelids, lips, cheeks, jaw, tongue and nose joints under Head_scale_null. They go by
  role to the TTT2 face bones Tekken 7's meshes carry (skeleton.FACE): brows -> Mayu1..3 (by place, inner to
  outer), upper / lower eyelids -> UwaMabuta / SitaMabuta, upper / lower lip and their zipper joints -> LipU / LipD
  (the middle ones M_LipU / M_LipD), lip corners -> LipE, jaw, lower teeth and chin -> Jaw_Joint, tongue -> Bero1 /
  Bero2, the nose's sides -> Hana / Kobana, the cheeks -> Hoho (upper) / Chobo (beside the mouth), the rest
  (forehead, eyelid creases, temples, ears, upper teeth, the nose's middle) -> the head, so blinks and mouth
  movements of the donor's face animations move the right skin and the rest stays still.
* Hair has no joints (Tekken 8 moves it as cloth): it is skinned to Head and a few neck and ear joints.

canonical() gives every joint a name of its own: a main joint its Tekken 7 name (what skeleton.ANCHOR places the
TTT2 bones by), any other '<Tekken 7 name>@<Tekken 8 name>' (skeleton.t7_weight_target reads the part before '@');
joints this file does not know keep their name (weights go to their parent's bone).

follow() tells skeleton.repose how a joint moves when the limbs turn from Tekken 8's A-pose to the donor's T-pose:
joints left out move with their parent; the helpers above follow their limb; '_hlf' joints (at a joint, carrying
the skin around it) turn half as far as the joint they sit on, as Tekken 8's rig turns them.

Written for this project from the files themselves (no third-party code).
"""
import re

SIDES = 'LR'
FINGERS = ('Index', 'Middle', 'Ring', 'Pinky')

# main joints: Tekken 8 -> Tekken 7 (the names skeleton.ANCHOR and skeleton.t7_weight_target know)
MAIN = {'Root': 'MODEL_00', 'Top': 'BODY_SCALE__group', 'Trans': 'BASE', 'Rot': 'Hip', 'Spine1': 'Spine1',
        'Spine2': 'Spine2', 'Neck': 'Neck', 'Head': 'Head'}
for _s in SIDES:
    MAIN.update({'%s_Shoulder' % _s: '%s_Shoulder' % _s, '%s_UpperArm' % _s: '%s_Arm' % _s,
                 '%s_LowerArm' % _s: '%s_ForeArm' % _s, '%s_Hand' % _s: '%s_Hand' % _s,
                 '%s_UpperLeg' % _s: '%s_UpLeg' % _s, '%s_LowerLeg' % _s: '%s_Leg' % _s,
                 '%s_Foot' % _s: '%s_Foot' % _s, '%s_Toe' % _s: '%s_Toe' % _s,
                 '%s_Index0' % _s: '%s_FingerBase' % _s, '%s_Middle0' % _s: '%s_Middle' % _s,
                 '%s_Ring0' % _s: '%s_Ring' % _s, '%s_Pinky0' % _s: '%s_Pinky' % _s})
    for _k in (1, 2, 3):
        for _f in FINGERS:
            MAIN['%s_%s%d' % (_s, _f, _k)] = '%s_%s%d' % (_s, _f, _k)
        MAIN['%s_Thumb%d' % (_s, _k - 1)] = '%s_Thumb%d' % (_s, _k)       # Tekken 8 thumb 0..2 = Tekken 7 1..3

# other body joints by exact name -> Tekken 7 name ({s}: the side)
OTHER = {'MUKI': 'BASE', 'Hip': 'Hip__offset', 'C_Leg': 'Hip__offset', 'Head_scale_null': 'Head__offset',
         'ATH_LR_AutoLooking': 'Head__offset', 'ADR_Head_bnd_hlf': 'Head__offset', 'C_UpThroat': 'Neck',
         'L_throat': 'Neck', 'R_throat': 'Neck'}
SIDED = {'{s}_Have': '{s}_Hand', '{s}_Have2': '{s}_Hand',                 # hold points
         'SWG_{s}_Bust': 'OPT0_bust{s}', 'SWG_{s}_BustTip': 'OPT1_bust{s}', 'ADR_{s}_Bust_drv': 'OPT0_bust{s}',
         'PMP_{s}_Shoulder': '{s}_Shoulder', 'PMP_{s}_UpperArm': '{s}_Arm', 'PMP_{s}_LowerArm': '{s}_ForeArm',
         'PMP_{s}_LowerArm_fore': 'HLP_{s}_ForeArm_Mid__offset', 'PMP_{s}_Chest': 'HLP_{s}_Pectoral__offset',
         'PMP_{s}_UpperLeg': '{s}_UpLeg', 'PMP_{s}_LowerLeg': '{s}_Leg'}
for _s in SIDES:
    OTHER.update({k.format(s=_s): v.format(s=_s) for k, v in SIDED.items()})
# ADR_<side>_ helpers: (pattern of the rest of the name, Tekken 7 helper); twist joints sit at 1/4, 1/2 and 3/4
# of their segment (Tekken 7's Top / Mid / Btm: TTT2 KATA_0 / 50 / 100, UDE_50 / 100, MOMO_0 / 50)
HELPERS = [
    (r'UpperArm_twt_a(_drv)?|UpperArm_twtOut_a|DeltioidUp_bnd|DeltoidUp_(mus|space)|Deltoid_(bnd_hlf|drv)',
     'HLP_{s}_Arm_Top__offset'),
    (r'UpperArm_twt_b(_drv)?', 'HLP_{s}_Arm_Mid__offset'),
    (r'UpperArm_twt_c(_drv)?|Elbow_hlf|ElbowBack_mus|ElbowFront_mus', '{s}_Arm_Btm__offset'),
    (r'Biceps_mus|BicepsFront_mus|Brachialis_mus', '{s}_Bicep_Slide__offset'),
    (r'Triceps_mus', '{s}_Tricep_Slide__offset'),
    (r'DeltoidFront_(mus|space)|PecMinor_mus', 'HLP_{s}_Shldr_F__offset'),
    (r'DeltoidBack_(mus|space)', 'HLP_{s}_Shldr_B__offset'),
    (r'Forearm_twt_a(_drv)?', '{s}_ForeArm'),
    (r'Forearm_twt_b(_drv)?', 'HLP_{s}_ForeArm_Mid__offset'),
    (r'Forearm_twt_c(_drv)?|Forearm_bnd_hlf|WristIN_mus|WristOUT_mus', 'HLP_{s}_ForeArm_Btm__offset'),
    (r'ForearmBack_mus|ForearmFront_mus|ForearmUp_mus', '{s}_ForeArm_Slide__offset'),
    (r'TrapsSide_bnd|TrapsSideTop_(bnd_hlf|mus)|Shoulder_drv(_plv_trg)?', '{s}_Shoulder'),
    (r'Clavicle_(drv|mus|drv_aim_trg|drv_plv_trg)', 'HLP_{s}_CollarBone__offset'),
    (r'PecMajor_(mus|space)', 'HLP_{s}_Pectoral__offset'),
    (r'Lat_(mus|space)', 'HLP_{s}_ShldrBlade__offset'),
    (r'Thigh_bnd|Thigh_twt_a|PelvisSide_mus', 'HLP_{s}_UpLeg_Top__offset'),
    (r'Thigh_twt_[bc]|ThighFront_mus|ThightFront_mus|ThighBack_mus', 'HLP_{s}_UpLeg_Mid__offset'),
    (r'PelvisFront_(bnd_hlf|mus)|Ingruinal_mus', 'HLP_{s}_Inguinal__offset'),
    (r'Butt_mus', 'HLP_{s}_Butt__offset'),
    (r'Knee_hlf|KneeFront_mus|KneeBack_mus', 'HLP_{s}_Knee__offset'),
    (r'Shin_twt_[abc]', '{s}_Leg__offset'),
    (r'Calf_mus', '{s}_Calf_Slide__offset'),
    (r'Ankle_bnd_hlf|AnkleFront_mus|AnkleBack_mus', '{s}_Ankle__offset'),
    (r'Eye_(aim|up|clc)', '{s}_Eye_Joint'),
]
FINGER_HELPER = re.compile(r'(Thumb|Index|Middle|Ring|Pinky)(\d)(_hlf|Up_mus|Inflat_mus|_mus)$')
NECK_HELPER = re.compile(r'ADR_(NeckSpine_twt_[abc]|Nape_mus|Throat_mus|NeckBack_(bnd_hlf|mus)|NeckFront_mus)$')

# face joints (<side>_<role>, side L, R or C; ADS_ copies alike) -> TTT2 face bone ({s}: the side) or Head
BROWS = {1: 1, 2: 2, 3: 3, 4: 3}            # Brow1..4 (1.2 / 2.6 / 4.8 / 5.5 cm out) -> Mayu1..3 (1.5 / 3.4 / 5.2)
FACE_RULES = [
    (r'(Sub)?Brow([1-4])', None),            # (BROWS)
    (r'Eye|EyePupil', '{s}_Eye_Joint'),
    (r'UpEyelid\d?', '{s}_UwaMabuta_Joint'),
    (r'(Sub)?LowEyelid\d?', '{s}_SitaMabuta_Joint'),
    (r'LipCorner', '{s}_LipE_Joint'),
    (r'UpLip01Zipper', 'M_LipU_Joint'),
    (r'Up(Mid)?Lip\d*(Zipper)?', '{s}_LipU_Joint'),       # (C_: M_LipU_Joint)
    (r'LowLip01Zipper', 'M_LipD_Joint'),
    (r'Low(Mid)?Lip\d*(Zipper)?', '{s}_LipD_Joint'),      # (C_: M_LipD_Joint)
    (r'LowJaw|LowTeeth|LowChin\d?|UpChin\d?|LipChin', 'Jaw_Joint'),
    (r'Tongue1', 'Bero1_Joint'),
    (r'Tongue[23]', 'Bero2_Joint'),
    (r'Nose1', '{s}_Hana_Joint'),            # (C_: the head)
    (r'Nose2', '{s}_Kobana_Joint'),
    # cheeks: the upper ones (under the eye, by the nose: 0.5-0.75 of the way from the mouth corner to the eye) rise
    # with the donor's Hoho, the ones beside the mouth and its line go with Chobo; Cheek5 (the outer cheekbone,
    # level with the temple) stays with the head
    (r'Cheek[3678]', '{s}_Hoho_Joint'),
    (r'Cheek[124]|CheekLine[12]', '{s}_Chobo_Joint'),
    # the eyelid crease (DoubleEyelid), forehead, temples, ears, upper jaw and teeth, the nose's middle, Cheek5:
    # still (a crease or forehead moved with the lid or brow folds the skin around it)
    (r'DoubleEyelid\d|Forehead\d?|Temple|UpEar|LowEar|Jaw_Root|UpJaw|UpTeeth|Nose[34]|Cheek5', 'Head__offset'),
]
FACE_RULES = [(re.compile('(?:%s)$' % rx), t) for rx, t in FACE_RULES]
FACE_JOINT = re.compile(r'(ADS_)?([LRC])_(.+)$')

# skeleton.repose: helpers that follow another joint than their parent: (pattern, joint ({s}: the side), share)
FOLLOW = [
    (r'ADR_{s}_DeltioidUp_bnd', '{s}_UpperArm', 1.0),     # the upper arm's twist joints hang under it
    (r'ADR_{s}_Thigh_bnd', '{s}_UpperLeg', 1.0),          # the thigh's
    (r'ADR_{s}_TrapsSide_bnd', '{s}_Shoulder', 1.0),      # the trapezius' side, aimed at the shoulder
    (r'ADR_{s}_Deltoid_bnd_hlf', '{s}_UpperArm', 0.5),
    (r'ADR_{s}_Elbow_hlf', '{s}_LowerArm', 0.5),
    (r'ADR_{s}_Forearm_bnd_hlf', '{s}_Hand', 0.5),
    (r'ADR_{s}_TrapsSideTop_bnd_hlf', '{s}_Shoulder', 0.5),
    (r'ADR_{s}_PelvisFront_bnd_hlf', '{s}_UpperLeg', 0.5),
    (r'ADR_{s}_Knee_hlf', '{s}_LowerLeg', 0.5),
    (r'ADR_{s}_Ankle_bnd_hlf', '{s}_Foot', 0.5),
    (r'ADR_{s}_(Thumb|Index|Middle|Ring|Pinky)(\d)_hlf', '{s}_{1}{2}', 0.5),
    (r'ADR_NeckBack_bnd_hlf', 'Neck', 0.5),
    (r'ADR_Head_bnd_hlf', 'Head', 0.5),
]
FOLLOW = [(re.compile(rx.format(s='(?P<s>[LR])') + '$'), joint, share) for rx, joint, share in FOLLOW]


def _face(name):
    m = FACE_JOINT.match(name)
    if not m:
        return None
    s, role = m.group(2), m.group(3)
    for rx, t in FACE_RULES:
        if not rx.match(role):
            continue
        if t is None:
            return '%s_Mayu%d_Joint' % (s, BROWS[int(re.search(r'\d', role).group())]) if s in SIDES else None
        if '{s}' in t and s not in SIDES:   # a middle joint: the lips' middles, else the head
            return {'{s}_LipU_Joint': 'M_LipU_Joint', '{s}_LipD_Joint': 'M_LipD_Joint'}.get(t, 'Head__offset')
        return t.format(s=s)
    return None


def target(name):
    """The Tekken 7 joint a Tekken 8 joint stands for (its role), or None (a joint this file does not know)."""
    if name in MAIN:
        return MAIN[name]
    if name in OTHER:
        return OTHER[name]
    if NECK_HELPER.match(name):
        return 'Neck'
    m = re.match(r'ADR_([LR])_(.+)$', name)
    if m:
        s, rest = m.groups()
        f = FINGER_HELPER.match(rest)
        if f:                                # finger helpers: their finger joint (Tekken 7's thumb counts from 1)
            return '%s_%s%d' % (s, f.group(1), int(f.group(2)) + (f.group(1) == 'Thumb'))
        for rx, t in HELPERS:
            if re.fullmatch(rx, rest):
                return t.format(s=s)
        return None
    return _face(name)


def canonical(name):
    """A Tekken 8 joint's name in the importer's skeleton: a main joint's Tekken 7 name, '<Tekken 7 name>@<Tekken 8
    name>' for the others it knows (each joint keeps a name of its own), unknown joints as they are."""
    if name in MAIN:
        return MAIN[name]
    t = target(name)
    return name if t is None else '%s@%s' % (t, name)


def follow(name):
    """(Tekken 8 joint, share) a joint turns with when the model is re-posed, or None: it moves with its parent."""
    for rx, joint, share in FOLLOW:
        m = rx.match(name)
        if m:
            return joint.format(*m.groups(), s=m.group('s') if 's' in rx.groupindex else ''), share
    return None
