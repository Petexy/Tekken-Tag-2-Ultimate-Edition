"""Tekken Tag Tournament 2's own garments on an added fighter (its Customize outfits, fitted at import).

How the game dresses its own fighters (what this follows):
  * A fighter's base model (`<code>.nud`) is a face plus the bare body cut in every way a garment can leave it
    showing: `kubiA..E_O_OBJ` (neck), `ude_*_O_OBJ` (arms and hands), `asi_*_O_OBJ` (legs and feet), `hara_O_OBJ`
    (midriff). The game draws one cut of each family, chosen by mesh NAME from the worn items' ShapeType words, and
    none of a family for a default-costume item (empty ShapeTypes).
  * Everything worn, the default costume too, is an item: an Instance of the item database whose Groups name part
    models in packs (`mi ti bi pi`: the fighter's own; `mci tci bci pci`: the common ones). A garment is modelled on
    its fighter's body, in that body's bind pose, and may carry that body's skin (chest, shoulders).
  * A part's vertices are bound through the BODY's skeleton (measured: moving a joint in a part's own skeleton file
    changes nothing), so a garment made for another body follows the wearer's joints but keeps the other body's
    bind-pose shape: on a body with other joints it must be re-posed first.

So an added fighter, whose body is one imported model with its own outfit in it, gets:
  1. `fit`: the source fighter's cuts and garments moved from the source's bind pose to the fighter's, each vertex by
     its own weights' blend of the joints' shifts (the skeletons share bones 0..137 by name, with the same rest
     rotations; helper joints sit in proportion along the limbs, so the blend stretches a limb evenly);
     and made as thick as the fighter where it is not the source's build (`girth_of`: its own outfits' bare skin
     against the source's bare body, patch by patch: Akuma's arms are half again as thick as Lars's);
  2. the cuts appended to its body model with copies of the source's skin textures, their colours scaled to the
     fighter's own skin (`skin_gain`: its face's plain skin against the source's), and the neck's top ring moved
     onto the head's open rim (`Neck`: tucked just inside it, so no gap opens);
  3. its own imported outfit taken OUT of the body model and made the parts of the default-costume Instances
     (`<code>_bdu*` meshes: the upper body item, `<code>_bdl*`: the lower; a full-body piece and the piece worn
     with it by the half they cover: own_pieces), each with a skeleton of its own (piece_skeleton). Worn by
     default it looks as it did; a record that puts a garment in that slot does not load it, exactly as the game
     drops a default costume: nothing of it can show under or through the garment (a record that leaves the
     slot empty, or names an item the database lacks, gets the default item from the game: seen in fights, the
     body cannot go missing that way);
  4. the garments as own-pack parts under the SOURCE's member numbers with the source's Instances as they are (labels
     and indices kept: records and shop rows name items by index), their common-pack members left to the game.

What an outfit is comes from the game's shop list (key C0810D5D: a row names the Instances of one purchase, such as
a T-shirt with its sleeves and gloves, and its default colours); every row of the source fighter that dresses the
upper or the lower body is fitted (`outfit_rows`), except its own default costumes.

A garment with bones of its own (`bi`: a skeleton that is the source's body plus the garment's swaying bones, held
by the body's joints) keeps them: the bones' places are relative to the body joint that holds them, so the skeleton
is written with the fighter's joints under the same member number. Its springs (`pi`: a spring file naming those
bones by number, with the capsules of the body they slide over) are copied as they are under the same member number:
a hakama's legs and a necktie swing on the fighter as on the source. The game's loader of a part's springs stops the
game on a member that does not begin as a spring file does (`SPRING_MAGIC`: its own check, a write to address 0 in
sub_02102D68), so only such members are copied, and when the source's spring pack is not found the garments are
worn without springs (`static`: the bones stay where their joints hold them) rather than with a wrong file.

Whose wardrobe: the fighter's donor's (`source_of`: the default items and the Instances its own outfit is worn as
are the donor's, so the donor's shop rows mean the same items in its database; women: Jun, men: Lars). A definition
says `WARDROBE = False` to have none; there is no list of garments or of fighters anywhere: what is fitted is read
from the player's game by the rules here, and a fighter is left without a wardrobe by rule too: one that is not the
source's size (HUMAN_REACH: the giants), one whose body is not an upper piece, a lower piece and a face (a preset
outfit in one piece keeps its body whole), one from Tekken 8 (not yet). A pack without a shop list (SHOP_FILE) is
one CUSTOMIZE mode cannot be entered with: the port's grid passes it and its face there is grey (art.greyed).

Not done here (say so to the player rather than guess): hair and head items, items with the rarer own-pack members
(`fits`), garments whose own bones are numbered like bones of the fighter's body (left out, not renumbered), a
source other than the donor. Girth is the limbs' and the trunk's only (`Girth`): the muscles' shapes, the hands and
the feet stay the source's.
"""
import copy
import struct

import numpy as np

from ..ttt2 import bone as bonefile, bxml, mop as mopfile, nud as nudfile, nut as nutfile
from ..ttt2.archive import key_of, member_key, pack_of
from . import itemdb

SALE_KEY = 0xC0810D5D               # the shop list (BXML: a Fighter element per fighter, Equipment/Item rows)
SHOP_FILE = 'shop.bxml'             # a pack's own shop list: what CUSTOMIZE mode offers the fighter (shop_list)
FACE_MESH = 'cha:kao_O_OBJ'         # the game's face mesh (not copied: the fighter keeps its own head)
CUT_PREFIXES = ('kubi', 'ude_', 'asi_', 'hara')     # the bare-body families of a base model
SKIN_FLAGS = 0x20A00099             # the body-skin material
FACE_SKIN_FLAGS = (0x20A00099, 0x20A201D9)      # ... and a face's skin as the importer and the game write it
FIRST_TEXTURE = 0x700               # the copied skin textures' ids in the fighter's range (model.py's come first,
                                    # the effects' from particles.FIRST_ID = 0x800)
OWN_STEP = 4                        # ... a body's pieces take up to this many numbers (preset outfits: the next)
OWN_FIRST = 900                     # own-pack member numbers of the fighter's own outfit pieces (the source's
                                    # garments keep the source's numbers, all far below)
UPPER, LOWER = '上半身(胴体)', '下半身'    # EquipPos of the upper-body and lower-body items
OWN_PIECES = (('_bdu', UPPER), ('_bdl', LOWER))     # the imported body's meshes (model.py's names) -> the item
OWN_OTHERS = ('_bdf', '_dep')       # ... and its pieces that are the one or the other by what they cover (own_pieces)
LOWER_ROOT = 'KOSHI_jnt'            # the joint the lower body hangs from (a piece bound to it and below is a lower)
PIECE_SIDE = 0.75                   # the share of a piece's weights on one half of the body that makes it that half's
HUMAN_REACH = 200.0                 # mm a joint may lie from the source's for the source's clothes to be fitted
                                    # (the human-sized fighters' joints: up to about 130; the giants': 250 and more)
BODY_SLOTS = (8, 12)                 # the record's slots of the upper-body and the lower-body garment
NECK_REACH = 45.0                   # mm from the head's rim over which the neck is drawn toward it
NECK_TUCK = (2.0, 1.5)              # mm the neck's top ring goes up and inward of the rim
GAIN_SPAN = (0.1, 2.5)              # the skin gain is kept within this
LUMA = np.array([0.2126, 0.7152, 0.0722])
GAIN_KNEE = 0.6                     # linear level above which a brightened skin texture is eased toward white
                                    # instead of cut off at it (toned)
SKIN_SATURATION = 0.15              # the least saturation (of the 8-bit colour) of a texel counted as skin (plain_skin)
SPRING_MAGIC = b'\x40\xa0\x00\x00'  # how a spring file begins (5.0): the game's loader insists on it
TEXTURE_CHECKS = 6                  # how many of a texture pack's files are held against their models (source_packs)
SPRING_MATCH = 0.8                  # how well a spring pack's files must agree with their skeletons (spring_pack)
GIRTH_BINS = 4                      # girth is measured in this many stretches of each bone of a limb's axis ...
GIRTH_SECTORS = 6                   # ... and this many directions round it (a patch of skin is held against the same patch)
GIRTH_SAMPLES = 4                   # vertices of each body a patch needs
GIRTH_PATCHES = 6                   # patches a limb needs to be measured at all
GIRTH_SPAN = (0.8, 1.5)             # a limb is made this much thinner or thicker at most
GIRTH_SAME = 0.12                   # a limb within this of the source's keeps the source's girth
GIRTH_SHARE = 0.7                   # the share of a vertex's weights on a limb's bones that makes it a sample of it
GIRTH_END = 0.8                     # from here along a limb its girth eases toward the hand's or foot's (unchanged)
HALVED = 2                          # texture format (BC3: normal and specular maps) stored at half size


# ------------------------------------------------------------------------------------------------ the game's packs
def find_pack(archives, indices, accepts, check=None):
    """The key of the pack holding members `indices` (a pack's key is compiled into the game, not made from a name;
    a member's key is the pack's continued over the member's number, which can be undone: so every archive entry is
    tried as the first member, and the pack is the one whose other members exist and whose members `check`
    (default: the first) all pass `accepts(index, data)`. None when there is none."""
    indices = sorted(set(indices))
    if not indices:
        return None
    check = indices[:1] if check is None else sorted(set(check) & set(indices)) or indices[:1]
    found = []
    for key in archives.where:
        k = pack_of(key, indices[0])
        if all(archives.has(member_key(k, i)) for i in indices[1:]):
            found.append(k)
    for k in found:
        try:
            if all(accepts(i, archives.read(member_key(k, i))) for i in check):
                return k
        except (ValueError, AssertionError, KeyError, IndexError, struct.error):
            continue
    return None


def spring_pack(archives, bones):
    """The key of the pack whose members are the spring files of the garments: `bones` = {member number: the
    extra bones' numbers of the skeleton the same Group names}. Every member must begin as a spring file does (the
    game stops on one that does not), and the members must drive the bones of their skeletons: many packs hold
    spring files under the same few numbers, and another fighter's would be loaded without complaint and throw the
    cloth about. A file and its skeleton need not agree bone for bone (a skeleton also has helper bones no spring
    drives; a file may name a bone more), so the pack is the one whose files agree best with their skeletons
    (SPRING_MATCH of the bones on average at least). None when there is none."""
    indices = sorted(bones)
    if not indices:
        return None
    best, best_score = None, 0.0
    for key in archives.where:
        pack = pack_of(key, indices[0])
        try:
            if not all(archives.has(member_key(pack, i)) for i in indices):
                continue
            score = 0.0
            for i in indices:
                data = archives.read(member_key(pack, i))
                if data[:4] != SPRING_MAGIC:
                    raise ValueError
                ids, mine = set(mopfile.read(data)['opt_ids']), set(bones[i])
                score += len(ids & mine) / max(len(ids | mine), 1)
        except (ValueError, AssertionError, KeyError, IndexError, struct.error):
            continue
        if score / len(indices) > best_score:
            best, best_score = pack, score / len(indices)
    return best if best_score >= SPRING_MATCH else None


def _attrs(el):
    return dict(el['attrs'])


def _group_members(db_info, kind):
    """{member index: (Instance label, Filename)} of the Groups naming own-pack members of `kind` ('mi', 'ti'..)."""
    out = {}
    for inst in db_info['children']:
        for g in itemdb.groups(inst):
            a = _attrs(g)
            if kind in a:
                out.setdefault(int(a[kind]), (_attrs(inst).get('label'), a.get('Filename', '')))
    return out


def source_packs(archives, db_info, base_nut):
    """The source fighter's own model and texture packs' keys, the common bone pack's, and the source's own bone
    and spring packs': (model, texture, bones, own bones, springs), None for one not found.
    The model pack is the one whose member is the mesh an Instance's Filename names; the texture pack the one whose
    member holds the textures a model of the same Group draws; a bone pack one whose member is the source's
    skeleton again (an own one: with more bones after it); the spring pack the one whose members drive the spring
    bones of the skeletons their Groups name (`spring_pack`)."""
    models = _group_members(db_info, 'mi')

    def is_model(index, data):
        name = models[index][1].rsplit('/', 1)[-1].replace('.nud', '')
        return data[:4] == b'NDP3' and any(m['name'] == name for m in nudfile.read(data)['meshes'])
    model_pack = find_pack(archives, models, is_model, sorted(models)[:TEXTURE_CHECKS])
    texture_pack = bone_pack = own_bone_pack = None
    pairs, bones, own_bones, springs, body_bones = {}, set(), set(), {}, set()
    for inst in db_info['children']:
        for g in itemdb.groups(inst):
            a = _attrs(g)
            if 'mi' in a and 'ti' in a:
                pairs.setdefault(int(a['ti']), int(a['mi']))
            if 'bci' in a:
                bones.add(int(a['bci']))
                if 'mi' in a:               # (a model of the fighter's own: bound to the fighter's skeleton)
                    body_bones.add(int(a['bci']))
            if 'bi' in a:
                own_bones.add(int(a['bi']))
            if 'pi' in a and 'bi' in a:
                springs.setdefault(int(a['pi']), int(a['bi']))
    if model_pack is not None and pairs:
        def is_textures(index, data):
            ids = {t['gidx'] for t in nutfile.read(data)['textures']}
            drawn = _texture_ids(nudfile.read(archives.read(member_key(model_pack, pairs[index]))))
            return len(ids & drawn) * 2 > len(drawn)
        # (other fighters' texture packs hold files under the same numbers, with a texture or two in common:
        # the pack is the one whose files hold most of what their models draw, for several of them)
        texture_pack = find_pack(archives, pairs, is_textures, sorted(pairs)[:TEXTURE_CHECKS])
    if bones or own_bones:
        base = bonefile.read(base_nut) if isinstance(base_nut, bytes) else base_nut

        def is_bones(index, data):
            b = bonefile.read(data)
            n = len(base['names'])
            return len(b['names']) >= n and [x.split(':')[-1] for x in b['names'][:n]] == \
                [x.split(':')[-1] for x in base['names']] and np.abs(b['t'][:n] - base['t']).max() < 0.01
        # (the common bone pack also holds the accessories' few bones under the numbers between: the skeletons
        # the fighter's own models are bound to are the ones to tell it by)
        bone_pack = find_pack(archives, bones, is_bones, body_bones)
        own_bone_pack = find_pack(archives, own_bones, is_bones)
    springs_of = None
    if own_bone_pack is not None:
        springs_of = spring_pack(archives, {pi: bonefile.read(archives.read(member_key(own_bone_pack, bi)))['opt']
                                            for pi, bi in springs.items()})
    return model_pack, texture_pack, bone_pack, own_bone_pack, springs_of


def _texture_ids(model):
    return {t['id'] for m in model['meshes'] for p in m['polys'] for mat in p['materials'] for t in mat['textures']}


# ------------------------------------------------------------------------------------------------ the shop list
def shop_rows(archives, labels):
    """{label: {'items': [(slot, Instance index, variant)], 'colours': [(register, number)]}} of the shop list's
    rows `labels`. A row's `instances` is `slot_index_variant|...`; its `colorgara` `group_entry_x_colour_s|...`
    sets colour register 26 + 5 * group + entry."""
    out = {}
    if not archives.has(SALE_KEY):
        return out
    want = set(labels)
    for fighter in bxml.parse(archives.read(SALE_KEY)):
        for equipment in fighter['children']:
            for item in equipment['children']:
                a = _attrs(item)
                if a.get('label') in want and a['label'] not in out:
                    items = [tuple(int(x) for x in part.split('_')) for part in a.get('instances', '').split('|') if part]
                    colours = []
                    for part in a.get('colorgara', '').split('|'):
                        f = part.split('_')
                        if len(f) >= 4:
                            colours.append((26 + 5 * int(f[0]) + int(f[1]), int(f[3])))
                    out[a['label']] = dict(items=items, colours=colours)
    return out


def outfit_rows(archives, code):
    """The labels of fighter `code`'s shop rows that dress the upper or the lower body (its rows are the ones
    labelled `<code>_...`), in the list's order."""
    out = []
    if not archives.has(SALE_KEY):
        return out
    for fighter in bxml.parse(archives.read(SALE_KEY)):
        for equipment in fighter['children']:
            for item in equipment['children']:
                a = _attrs(item)
                slots = [part.split('_')[0] for part in a.get('instances', '').split('|') if part]
                if a.get('label', '').startswith(code + '_') and any(s in slots for s in map(str, BODY_SLOTS)) \
                        and a['label'] not in out:
                    out.append(a['label'])
    return out


def shop_list(archives, source_code, db):
    """The fighter's own shop list for CUSTOMIZE mode (SHOP_FILE, the game's format: one Fighter element): the
    source fighter's rows whose every item is an Instance of the fighter's database `db` (bytes), under the source's
    element id, item ids and labels, so that the game's names, prices, ownership and unlocks of those rows are the
    source's. A row is only listed when all it wears can be loaded (the mode waits for ever on a missing one).
    -> bytes, or None when the game has no list for the source or nothing of it fits."""
    if not archives.has(SALE_KEY):
        return None
    have = {int(_attrs(i)['index']) for i in bxml.parse(db)[0]['children'] if i['tag'] == 'Instance'}
    for fighter in bxml.parse(archives.read(SALE_KEY)):
        labels = [_attrs(item).get('label', '') for e in fighter['children'] for item in e['children']]
        if not any(label.startswith(source_code + '_') for label in labels):
            continue
        kept = []
        for equipment in fighter['children']:
            rows = []
            for item in equipment['children']:
                parts = [part.split('_') for part in _attrs(item).get('instances', '').split('|') if part]
                if parts and all(len(f) >= 2 and f[1].lstrip('-').isdigit() and int(f[1]) in have for f in parts):
                    rows.append(item)
            if rows:
                kept.append(dict(equipment, children=rows))
        return bxml.write([dict(fighter, children=kept)]) if kept else None
    return None


def record_text(rows, defaults=()):
    """The developer switch's text (TTT2_TEST_CUSTOMIZE, after `<code>:`) for wearing the shop rows `rows` (what
    shop_rows returns for them) over `defaults` [(slot, index)] (the default items of the slots they leave)."""
    slots = dict(defaults)
    colours = {}
    for row in rows:
        for slot, index, _ in row['items']:
            slots[slot] = index
        colours.update(dict(row['colours']))
    return ','.join(['%d=%d' % kv for kv in sorted(slots.items())] + ['c%d=%d' % kv for kv in sorted(colours.items())])


# ------------------------------------------------------------------------------------------------ fitting
def joint_shifts(source_bon, target_bon, part_bon=None):
    """Per bone of `part_bon` (default: the source's skeleton), how far the joint of that name moves from the
    source's bind pose to the target's (model space, mm). A part's own bones (spring bones the body does not have)
    move with their nearest ancestor the body has."""
    part = source_bon if part_bon is None else part_bon
    src = dict(zip((n.split(':')[-1] for n in source_bon['names']), bonefile.world_matrices(source_bon)[:, :3, 3]))
    dst = dict(zip((n.split(':')[-1] for n in target_bon['names']), bonefile.world_matrices(target_bon)[:, :3, 3]))
    out = np.zeros((len(part['names']), 3))
    for i, name in enumerate(part['names']):
        j = i
        while j >= 0 and part['names'][j].split(':')[-1] not in dst:
            j = part['parent'][j]
        if j >= 0:
            n = part['names'][j].split(':')[-1]
            if n in src:
                out[i] = dst[n] - src[n]
    return out


def _moved(verts, shifts):
    """How far each skinned vertex moves: its weights' blend of its bones' shifts."""
    bones = np.minimum(verts['bones'].astype(np.int64), len(shifts) - 1)
    w = verts['w'].astype(np.float64)
    total = w.sum(1, keepdims=True)
    w = np.where(total > 0, w / np.maximum(total, 1e-9), 0.0)
    return (shifts[bones] * w[..., None]).sum(1)


def fit(model, shifts, neck=None, girth=None):
    """`model` (a NUD's dict, changed in place) moved to the target's bind pose; `neck` also draws what lies near
    the source head's rim to the target head's; `girth` (a Girth.of: per vertex array, how far its limb's girth
    moves it) makes its limbs and trunk as thick as the fighter's."""
    for mesh in model['meshes']:
        points = []
        for poly in mesh['polys']:
            v = poly['verts']
            if 'bones' not in v.dtype.names:
                continue
            old = v['pos'].astype(np.float64)
            new = old + _moved(v, shifts)
            if girth is not None:
                new += girth(v)
            if neck is not None:
                new += neck.pull(old)
            v['pos'] = new
            points.append(new)
        if points:
            sphere = nudfile.bounding_sphere(np.concatenate(points))
            mesh['sphere'] = sphere
            mesh['center'] = sphere[:3]
    every = [p['verts']['pos'] for m in model['meshes'] for p in m['polys']]
    if every:
        model['sphere'] = nudfile.bounding_sphere(np.concatenate(every))
    return model


# ------------------------------------------------------------------------------------------------ girth
def _short(name):
    return name.split(':')[-1]


def limbs(bon):
    """The limbs girth is measured and changed on, of a body skeleton: {name: (kind, bone numbers, [3 points])}:
    each arm (the joints from the shoulder to the wrist and their helper bones; the hand is not in it), each leg
    (hip to ankle; not the foot) and the trunk (everything else but the neck, the head, the hands and the feet),
    with the three joints its axis runs through. {} for a skeleton without those joints."""
    names = [_short(n) for n in bon['names']]
    where = {n: i for i, n in enumerate(names)}
    parent = bon['parent']
    wanted = ['KOSHI_jnt', 'MUNE2_jnt', 'KUBI_jnt'] + [n % s for s in 'RL' for n in (
        'SAKOTSU_%s_jnt', 'KATA_%s_jnt', 'UDE_%s_jnt', 'TE_%s_jnt', 'MOMO_%s_jnt', 'HIZA_%s_jnt', 'ASHI_%s_jnt')]
    if any(n not in where for n in wanted):
        return {}
    world = bonefile.world_matrices(bon)[:, :3, 3]

    def under(root, stop=()):
        out = set()
        for i in range(len(names)):
            j = i
            while j >= 0 and names[j] not in stop:
                if names[j] == root:
                    out.add(i)
                    break
                j = parent[j]
        return out
    out, taken = {}, set()
    for s in 'RL':
        hand, foot = under('TE_%s_jnt' % s), under('ASHI_%s_jnt' % s)
        # (the collar bone, the shoulder blade and the shoulder's front and back helpers are the trunk's)
        arm = under('KATA_%s_jnt' % s, ('TE_%s_jnt' % s,)) | {i for i in under('SAKOTSU_%s_jnt' % s) - hand
                                                               if names[i].startswith(('KATA_50', 'KATA_100', 'slide_'))}
        leg = under('MOMO_%s_jnt' % s, ('ASHI_%s_jnt' % s,)) | {where[n] for n in ('MOMO_50_%s' % s,) if n in where}
        out['arm ' + s] = ('arm', arm, world[[where[n % s] for n in ('KATA_%s_jnt', 'UDE_%s_jnt', 'TE_%s_jnt')]])
        out['leg ' + s] = ('leg', leg, world[[where[n % s] for n in ('MOMO_%s_jnt', 'HIZA_%s_jnt', 'ASHI_%s_jnt')]])
        taken |= arm | leg | hand | foot
    taken |= under('KUBI_jnt') | under('KUBI_jnt_assist')
    out['trunk'] = ('trunk', set(range(len(names))) - taken, world[[where[n] for n in ('KOSHI_jnt', 'MUNE2_jnt', 'KUBI_jnt')]])
    return out


def _round_axis(pos, points):
    """Where each position is about a limb's axis (3 joints): (how far along it, 0..2: the joint it is past plus
    the share of the way to the next; the vector from the axis to it; which of GIRTH_SECTORS directions round the
    axis it lies in)."""
    along = np.zeros(len(pos))
    out = np.zeros((len(pos), 3))
    sector = np.zeros(len(pos), np.int64)
    first = points[1] - points[0]
    past = (pos - points[1]) @ first > 0
    for k in range(2):
        d = points[k + 1] - points[k]
        length = max(float(np.linalg.norm(d)), 1e-6)
        d = d / length
        pick = past if k else ~past
        t = (pos[pick] - points[k]) @ d
        r = pos[pick] - points[k] - t[:, None] * d
        ref = np.array((0.0, 0.0, 1.0)) if abs(d[2]) < 0.9 else np.array((0.0, 1.0, 0.0))
        u = ref - (ref @ d) * d
        u /= np.linalg.norm(u)
        angle = np.arctan2(r @ np.cross(d, u), r @ u)
        along[pick] = k + np.clip(t / length, 0.0, 1.0)
        out[pick] = r
        sector[pick] = np.minimum(((angle + np.pi) / (2 * np.pi) * GIRTH_SECTORS).astype(np.int64), GIRTH_SECTORS - 1)
    return along, out, sector


def _weights(v):
    w = v['w'].astype(np.float64)
    return w / np.maximum(w.sum(1, keepdims=True), 1e-9)


def skin_patches(meshes, bon):
    """The bare skin of a body in patches: {(limb, stretch along it, direction round it): [sum of the distances
    from the limb's axis, vertices]} over the skin polygons of `meshes` (bound through skeleton `bon`)."""
    out = {}
    parts = limbs(bon)
    for mesh in meshes:
        for poly in mesh['polys']:
            v = poly['verts']
            if 'bones' not in v.dtype.names or not poly['materials'] or poly['materials'][0]['flags'] != SKIN_FLAGS:
                continue
            pos, w, bones = v['pos'].astype(np.float64), _weights(v), v['bones'].astype(np.int64)
            for name, (_, mine, points) in parts.items():
                pick = (w * np.isin(bones, list(mine))).sum(1) > GIRTH_SHARE
                if not pick.any():
                    continue
                along, r, sector = _round_axis(pos[pick], points)
                stretch = np.minimum((along * GIRTH_BINS).astype(np.int64), 2 * GIRTH_BINS - 1)
                for key, dist in zip(zip(stretch.tolist(), sector.tolist()), np.linalg.norm(r, axis=1)):
                    cell = out.setdefault((name,) + key, [0.0, 0])
                    cell[0] += dist
                    cell[1] += 1
    return out


def girth_of(source, target):
    """How much thicker than the source's the fighter's arms, legs and trunk are: {kind: factor}, from the two
    bodies' skin_patches (the fighter's: of every outfit it has). A patch of bare skin both show is held against
    the same patch (a rolled sleeve shows one stretch of the arm); a limb's factor is the median over its patches.
    An arm or a leg the fighter never bares takes the other's (a man with thin bare forearms has thin legs in his
    trousers; 1 for one who bares neither). The trunk's factor is for its top, the shoulders, and is the mean of the
    two (what a collar bares of a trunk is the neck's root more than the chest, and measures as anything); toward
    the hips a trunk takes the legs' (Girth). Within GIRTH_SAME of the source a factor is 1 (the
    source's girth as it is); kept within GIRTH_SPAN."""
    ratios = {}
    for key, (total, count) in target.items():
        theirs = source.get(key)
        if theirs is not None and count >= GIRTH_SAMPLES and theirs[1] >= GIRTH_SAMPLES and theirs[0] > 0:
            ratios.setdefault(key[0].split(' ')[0], []).append((total / count) / (theirs[0] / theirs[1]))
    seen = {kind: float(np.median(ratios[kind])) for kind in ('arm', 'leg') if len(ratios.get(kind, ())) >= GIRTH_PATCHES}
    rest = float(np.mean(list(seen.values()))) if seen else 1.0
    raw = {kind: seen.get(kind, rest) for kind in ('arm', 'leg')}
    raw['trunk'] = (raw['arm'] + raw['leg']) / 2
    out = {}
    for kind, f in raw.items():
        f = float(np.clip(f, *GIRTH_SPAN))
        out[kind] = 1.0 if abs(f - 1.0) < GIRTH_SAME else f
    return out


def own_skin(body, code, bon):
    """skin_patches of a fighter's own outfit in a body model (every `<code>_bd..` mesh, whole or in pieces)."""
    return skin_patches([m for m in body['meshes'] if m['name'].startswith(code + '_bd')], bon)


def pack_girth(archives, code, source_code, bodies):
    """girth_of a fighter against its wardrobe's source, over all its bodies ([(model bytes, skeleton bytes)]: an
    arm one outfit covers is bare in another), or None when the game has no such source."""
    if not archives.has(key_of(source_code + '.nud')) or not archives.has(key_of(source_code + '.bon')):
        return None
    source = nudfile.read(archives.read_name(source_code + '.nud'))
    theirs = skin_patches([m for m in source['meshes'] if is_cut(m['name'])],
                          bonefile.read(archives.read_name(source_code + '.bon')))
    ours = {}
    for model, skeleton in bodies:
        for key, (total, count) in own_skin(nudfile.read(model), code, bonefile.read(skeleton)).items():
            cell = ours.setdefault(key, [0.0, 0])
            cell[0] += total
            cell[1] += count
    return girth_of(theirs, ours)


class Girth:
    """Makes the source's bare body and garments as thick as the fighter (factors: girth_of): each vertex moves
    away from (or toward) its limb's axis in the source's bind pose, by the limb's factor times the share of its
    weights on the limb's bones, so a limb's girth runs out smoothly into the hand, the foot and the neck, which
    keep the source's. The trunk goes from the legs' factor at the hips to its own at the shoulders. Toward an
    arm's or a leg's far end (GIRTH_END) the factor eases to its square root: a thick forearm
    narrows to the wrist of a hand that is not made thicker."""

    def __init__(self, source_bon, factors):
        self.source = source_bon
        self.factors = factors
        self.parts = limbs(source_bon) if any(f != 1.0 for f in factors.values()) else {}
        self.known = {_short(n) for n in source_bon['names']}
        self.kind = {}                  # bone name -> limb (the hands', the feet's, the neck's and the head's: none)
        for name, (_, mine, _) in self.parts.items():
            for i in mine:
                self.kind[_short(source_bon['names'][i])] = name

    def of(self, part_bon=None):
        """The mover for models bound through skeleton `part_bon` (default: the source's): a garment's own bones
        belong to the limb of their nearest ancestor the body has. -> f(verts) -> how far each moves, or None
        when nothing changes."""
        if not self.parts:
            return None
        bon = self.source if part_bon is None else part_bon
        member = []
        for i in range(len(bon['names'])):
            j = i
            while j >= 0 and _short(bon['names'][j]) not in self.known:
                j = bon['parent'][j]
            member.append(self.kind.get(_short(bon['names'][j])) if j >= 0 else None)

        def moved(v):
            pos, w = v['pos'].astype(np.float64), _weights(v)
            bones = v['bones'].astype(np.int64)
            out = np.zeros((len(pos), 3))
            for name, (kind, _, points) in self.parts.items():
                f = self.factors[kind]
                if f == 1.0 and (kind != 'trunk' or self.factors['leg'] == 1.0):
                    continue
                mine = [i for i, m in enumerate(member) if m == name]
                share = (w * np.isin(bones, mine)).sum(1)
                pick = share > 0
                if not pick.any():
                    continue
                along, r, _ = _round_axis(pos[pick], points)
                if kind == 'trunk':             # (the legs' girth at the hips, its own at the shoulders)
                    factor = self.factors['leg'] + (f - self.factors['leg']) * along / 2.0
                else:
                    ease = np.clip((along / 2.0 - GIRTH_END) / (1.0 - GIRTH_END), 0.0, 1.0)
                    factor = f + (np.sqrt(f) - f) * ease
                out[pick] += r * ((factor - 1.0) * share[pick])[:, None]
            return out
        return moved


# ------------------------------------------------------------------------------------------------ the neck
def _mesh_points(mesh):
    """(positions, triangles, the polygon and the vertex within it of each position) of a mesh."""
    pos, tris, owner, off = [], [], [], 0
    for k, poly in enumerate(mesh['polys']):
        n = len(poly['verts'])
        pos.append(poly['verts']['pos'].astype(np.float64))
        tris += [(a + off, b + off, c + off) for a, b, c in nudfile.strip_to_tris(poly['indices'])]
        owner += [(k, i) for i in range(n)]
        off += n
    return np.concatenate(pos), np.array(tris, np.int64).reshape(-1, 3), owner


def open_loops(mesh):
    """The mesh's open edges as loops: [indices into _mesh_points' positions] (one vertex per welded point)."""
    pos, tris, _ = _mesh_points(mesh)
    _, first, welded = np.unique(np.round(pos, 2), axis=0, return_index=True, return_inverse=True)
    welded = welded.reshape(-1)
    t = welded[tris]
    edges = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    edges = edges[edges[:, 0] != edges[:, 1]]
    edges.sort(1)
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    neighbours = {}
    for a, b in uniq[counts == 1]:
        neighbours.setdefault(int(a), []).append(int(b))
        neighbours.setdefault(int(b), []).append(int(a))
    loops, seen = [], set()
    for start in neighbours:
        if start in seen:
            continue
        loop, stack = [], [start]
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                loop.append(x)
                stack += neighbours[x]
        loops.append([int(first[x]) for x in loop])
    return loops


def neck_loop(mesh):
    """The face mesh's rim around the neck: its widest open loop -> (points in order of angle about the loop's
    centre seen from above, their indices as _mesh_points numbers them)."""
    pos, _, _ = _mesh_points(mesh)
    loops = [l for l in open_loops(mesh) if len(l) >= 6]
    if not loops:
        raise ValueError('the face mesh %s has no open rim' % mesh['name'])
    loop = max(loops, key=lambda l: np.ptp(pos[l][:, [0, 2]], axis=0).sum())
    pts = pos[loop]
    centre = pts.mean(0)
    order = np.argsort(np.arctan2(pts[:, 0] - centre[0], pts[:, 2] - centre[2]))
    return pts[order], [loop[i] for i in order]


class _Ring:
    """A closed loop as a function of the angle about its centre (seen from above)."""

    def __init__(self, points):
        self.centre = points.mean(0)
        angle = np.arctan2(points[:, 0] - self.centre[0], points[:, 2] - self.centre[2])
        order = np.argsort(angle)
        self.angle = np.concatenate([angle[order][-1:] - 2 * np.pi, angle[order], angle[order][:1] + 2 * np.pi])
        self.points = np.concatenate([points[order][-1:], points[order], points[order][:1]])

    def at(self, angle):
        return np.stack([np.interp(angle, self.angle, self.points[:, k]) for k in range(3)], -1)

    def angle_of(self, points):
        return np.arctan2(points[:, 0] - self.centre[0], points[:, 2] - self.centre[2])


class Neck:
    """The seam between the fighter's own head and the source's neck.

    source_face / target_face: the two face meshes (the source's `cha:kao_O_OBJ`, the fighter's `<code>_fac`), each
    with an open rim where the neck joins; shifts: joint_shifts of the source's skeleton. The source's neck cuts end
    on the source rim; after the fit they would end where that rim lands on the fighter's joints, which is not
    where the fighter's head ends (another head). pull() moves what lies within NECK_REACH of the source rim by the
    rim's own error, fading with distance, so the cuts' top ring lands on the fighter's rim, NECK_TUCK inside it."""

    def __init__(self, source_face, target_face, shifts):
        pts, idx = neck_loop(source_face)
        _, _, owner = _mesh_points(source_face)
        landed = pts.copy()
        for n, i in enumerate(idx):
            poly, v = owner[i]
            landed[n] += _moved(source_face['polys'][poly]['verts'][v:v + 1], shifts)[0]
        self.source = _Ring(pts)
        target_pts, self.target_index = neck_loop(target_face)
        self.target = _Ring(target_pts)
        up, inward = NECK_TUCK
        angle = self.source.angle_of(pts)
        # the same place on the two rims: the same angle about each rim's own centre
        goal = self.target.at(angle)
        radial = goal - self.target.centre
        radial[:, 1] = 0
        radial /= np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1e-6)
        goal = goal + np.array([0.0, up, 0.0]) - radial * inward
        self.error = _Ring.__new__(_Ring)
        order = np.argsort(angle)
        a = angle[order]
        self.error.centre = self.source.centre
        self.error.angle = np.concatenate([a[-1:] - 2 * np.pi, a, a[:1] + 2 * np.pi])
        e = (goal - landed)[order]
        self.error.points = np.concatenate([e[-1:], e, e[:1]])
        self.worst = float(np.linalg.norm(goal - landed, axis=1).max())

    def pull(self, points):
        """How far source-pose points move toward the fighter's rim (zero beyond NECK_REACH of the source rim)."""
        out = np.zeros_like(points)
        near = np.abs(points - self.source.centre).max(1) < NECK_REACH * 4
        if not near.any():
            return out
        p = points[near]
        angle = self.source.angle_of(p)
        d = np.linalg.norm(p - self.source.at(angle), axis=1)
        f = np.clip(1.0 - d / NECK_REACH, 0.0, 1.0)
        f = f * f * (3 - 2 * f)
        out[near] = self.error.at(angle) * f[:, None]
        return out


# ------------------------------------------------------------------------------------------------ skin tone
def plain_skin(face, textures):
    """The linear colour of a face's plain skin: its skin polygon (the one with the most vertices) sampled at its
    vertices; of the samples that have a skin's colour at all (SKIN_SATURATION: a white beard, grey stubble and
    the whites painted round the eyes have none), the mean of the brighter half (make-up, lips, brows and the
    shaded rim under the chin are the darker half). None without a texture."""
    poly = max(face['polys'], key=lambda p: len(p['verts']))
    return _plain(poly, textures)


def skin_polygon(face, pieces=()):
    """The polygon to take a fighter's skin tone from: its face's skin (the face mesh's polygon with the most
    vertices), unless that one is not drawn as skin (Kunimitsu II's face is drawn with the cloth material, which
    shows a texture about twice as bright: its texture is not her tone); then the largest skin polygon of its own
    outfit (`pieces`: meshes; bare arms, a neckline), None if it has none."""
    poly = max(face['polys'], key=lambda p: len(p['verts']))
    if poly['materials'] and poly['materials'][0]['flags'] in FACE_SKIN_FLAGS:
        return poly
    others = [p for m in pieces for p in m['polys'] if p['materials'] and p['materials'][0]['flags'] == SKIN_FLAGS
              and len(p['verts']) >= 8]
    return max(others, key=lambda p: len(p['verts'])) if others else None


def _plain(poly, textures):
    image = textures.get(poly['materials'][0]['textures'][0]['id']) if poly is not None and poly['materials'] and \
        poly['materials'][0]['textures'] else None
    if image is None or 'uv' not in poly['verts'].dtype.names or len(poly['verts']) < 8:
        return None
    h, w = image.shape[:2]
    uv = poly['verts']['uv'][:, 0].astype(np.float64)
    x = ((uv[:, 0] % 1.0) * w).astype(np.int64) % w
    y = ((uv[:, 1] % 1.0) * h).astype(np.int64) % h
    rgb = image[y, x, :3].astype(np.float64)
    top = np.maximum(rgb.max(1), 1.0)
    skin = ((top - rgb.min(1)) / top >= SKIN_SATURATION) & (rgb[:, 0] >= rgb[:, 1]) & (rgb[:, 1] >= rgb[:, 2])
    if skin.sum() * 5 >= len(rgb):
        rgb = rgb[skin]
    colours = _linear(rgb)
    luma = colours @ LUMA
    return colours[luma >= np.median(luma)].mean(0)


def skin_gain(source_face, target_face, textures, pieces=()):
    """The per-channel gain (linear colour) that gives the source's body skin the fighter's skin tone: the ratio of
    the two faces' plain skin (the game paints a fighter's body in its face's tone, and a player sees the body
    beside the face: a gain measured only where head and neck meet, a shaded strip, left a fair face on a darker
    body). textures: {id: decoded image} of what is sampled; pieces: the fighter's own outfit's meshes, for a
    fighter whose face is not drawn as skin (skin_polygon). 1 when it cannot be measured."""
    theirs, ours = plain_skin(source_face, textures), _plain(skin_polygon(target_face, pieces), textures)
    if theirs is None or ours is None or (theirs < 1e-4).any():
        return np.ones(3)
    return np.clip(ours / theirs, *GAIN_SPAN)


def _linear(rgb8):
    x = np.asarray(rgb8, np.float64) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _srgb8(linear):
    x = np.clip(linear, 0.0, 1.0)
    return np.clip(np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055) * 255.0 + 0.5, 0, 255).astype(np.uint8)


def toned(linear, gain):
    """Linear colours (.., 3) times the skin `gain`. A channel that is made brighter is eased toward white above
    GAIN_KNEE (never below what it was) rather than cut off there: a pale fighter's gain (Noctis: 1.6 to 1.9)
    turned the lit half of the source's muscles into one flat white, which the game's lights then burnt out."""
    x = np.asarray(linear, np.float64)
    y = x * gain
    room = 1.0 - GAIN_KNEE
    eased = np.maximum(GAIN_KNEE + room * (1.0 - np.exp(-(y - GAIN_KNEE) / room)), np.minimum(x, 1.0))
    return np.where((np.asarray(gain) > 1.0) & (y > GAIN_KNEE), eased, y)


# ------------------------------------------------------------------------------------------------ textures
def skin_textures(source_nut, wanted, colour_ids, gain, first_id):
    """Copies of the source's base textures `wanted` (ids) under new ids from `first_id`: the skin's colour
    textures (`colour_ids`) times `gain`, the BC3 maps at half size, the rest as they are.
    -> ([textures], {old id: new id})."""
    out, ids = [], {}
    for t in source_nut['textures']:
        if t['gidx'] not in wanted or t['gidx'] in ids:
            continue
        new = first_id + len(out)
        ids[t['gidx']] = new
        out.append(_skin_copy(t, new, gain if t['gidx'] in colour_ids else None))
    return out, ids


def _skin_copy(t, new, gain):
    """Texture `t` under the id `new`: a colour texture times `gain` (None: not one), a BC3 map at half size."""
    levels = len(t['mips'])
    if gain is not None and t['fmt'] in (0, 2):
        rgba = nutfile.decode(t)
        rgba[..., :3] = _srgb8(toned(_linear(rgba[..., :3]), gain))
        return nutfile.make_texture(rgba, new, t['fmt'], mips=min(levels, 3))
    if t['fmt'] == HALVED and levels > 1 and min(t['w'], t['h']) >= 64:
        return dict(fmt=t['fmt'], w=t['w'] // 2, h=t['h'] // 2, mips=list(t['mips'][1:]), gidx=new)
    return dict(fmt=t['fmt'], w=t['w'], h=t['h'], mips=list(t['mips'][:3]), gidx=new)


def garment_textures(part_nut, source_nut, copies, ids, colour_ids, gain):
    """A garment's own texture file for the fighter. The game's garments carry, beside their cloth, the body skin
    textures their own skin polygons draw, under the base model's ids (a part finds its textures in its own file:
    a skin polygon whose textures are only in the body's file is drawn black or with whatever was drawn before it).
    The fitted garments' skin polygons name the fighter's copies (`ids` {source id: new id}), so those textures go
    in under the new ids: the fighter's copy (`copies`) where the garment's is the base model's, else the
    garment's own version treated the same way. -> [textures]."""
    base = {t['gidx']: t for t in source_nut['textures']}
    mine = {t['gidx']: t for t in copies}
    out = []
    for t in part_nut['textures']:
        new = ids.get(t['gidx'])
        if new is None:
            out.append(t)
        elif t['gidx'] in base and t['mips'] == base[t['gidx']]['mips'] and new in mine:
            out.append(mine[new])
        else:
            out.append(_skin_copy(t, new, gain if t['gidx'] in colour_ids else None))
    return out


def renumber(model, ids):
    """The model's materials with texture ids replaced by `ids` {old: new}."""
    for mesh in model['meshes']:
        for poly in mesh['polys']:
            for mat in poly['materials']:
                for t in mat['textures']:
                    t['id'] = ids.get(t['id'], t['id'])
    return model


# ------------------------------------------------------------------------------------------------ the item database
def fits(inst):
    """Whether an Instance can be fitted here: every own-pack member of its Groups is a model, a texture, a
    skeleton or springs (none of the rarer kinds), and it is not a default costume (the source's own outfit: its
    Instances are the ones the fighter's own outfit is worn as)."""
    data = [c for c in inst['children'] if c['tag'] == 'Data']
    if data and _attrs(data[0]).get('EquipType') == itemdb.DEFAULT_COSTUME:
        return False
    return not any(name in ('gi', 'hi', 'ei', 'ni', 'ci') for g in itemdb.groups(inst) for name, _ in g['attrs'])


def static(inst):
    """A copy of the Instance without its Groups' own spring files (`pi`): worn with its own bones held still
    (for a source whose spring pack was not found)."""
    out = copy.deepcopy(inst)
    for g in itemdb.groups(out):
        g['attrs'] = [(name, value) for name, value in g['attrs'] if name != 'pi']
    return out


def part_skeleton(part, target):
    """A garment's own skeleton (`bi`: the source's body and the garment's bones) with the fighter's joints: every
    bone the fighter's skeleton has by name takes its place there; the garment's own bones keep theirs, which are
    relative to the joint that holds them."""
    out = dict(part)
    out['t'], out['r'], out['s'] = part['t'].copy(), part['r'].copy(), part['s'].copy()
    where = {n.split(':')[-1]: i for i, n in enumerate(target['names'])}
    for i, name in enumerate(part['names']):
        j = where.get(name.split(':')[-1])
        if j is not None:
            out['t'][i], out['r'][i], out['s'][i] = target['t'][j], target['r'][j], target['s'][j]
    return out


def piece_skeleton(bon, meshes):
    """The skeleton of one of the fighter's own outfit pieces (a part's `bi`), made from the body's (`bon`, parsed):
    the body's bones without the extra (OPT) bones the piece's `meshes` are not bound to; the meshes' bone numbers
    are changed to match (in place). -> the skeleton.

    What the game was seen to do with a part's skeleton (fights loaded or not, 2026-11-19): it must list (its `opt`
    numbers) exactly the extra bones it holds (the body's whole skeleton with an empty list, or with a part of the
    list: the fight never finishes loading), and the parts worn together must not list too many (two pieces with
    the body's 86 cloth bones each: a null read under sub_0491B558 while the fight loads; 55 each, or 86 in one
    piece and none in the other: fine). A part is bound through the body's skeleton by its bones' names, and the
    body's springs move the bones, so a piece only needs the bones it uses."""
    def number(name):
        short = name.split(':')[-1]
        digits = short[3:].split('_')[0] if short.startswith('OPT') else ''
        return int(digits) if digits.isdigit() else None
    used = set()
    for mesh in meshes:
        for poly in mesh['polys']:
            v = poly['verts']
            if 'bones' in v.dtype.names:
                used |= set(v['bones'][v['w'] > 0].tolist())
    keep = {i for i, name in enumerate(bon['names']) if number(name) is None}
    for i in used:
        while 0 <= i < len(bon['names']) and i not in keep:
            keep.add(i)
            i = bon['parent'][i]
    order = sorted(keep)
    new = {old: i for i, old in enumerate(order)}
    numbers = {number(bon['names'][i]) for i in order} - {None}
    out = dict(bon, names=[bon['names'][i] for i in order], parent=[new.get(bon['parent'][i], -1) for i in order],
               t=bon['t'][order], r=bon['r'][order], s=bon['s'][order], opt=[n for n in bon['opt'] if n in numbers])
    out.pop('names_raw', None)
    table = np.array([new.get(i, 0) for i in range(len(bon['names']))])
    for mesh in meshes:
        for poly in mesh['polys']:
            v = poly['verts']
            if 'bones' in v.dtype.names:
                v['bones'] = table[np.minimum(v['bones'].astype(np.int64), len(table) - 1)]
    return out


def is_cut(name):
    return name.endswith('_O_OBJ') and name.startswith(CUT_PREFIXES) and name != FACE_MESH


def source_of(d):
    """The code of the fighter of the game whose wardrobe definition `d` is fitted with, or None for none.
    A definition's `WARDROBE`: False = no wardrobe (the fighter cannot be entered in CUSTOMIZE mode); left out (or
    True) = its donor's (`DONOR`: the Instances its own outfit is worn as and its default items are the donor's, so
    the donor's shop rows mean the same items in its database). Tekken 7 fighters only so far."""
    from ..characters import game_of
    choice = getattr(d, 'WARDROBE', True)
    if choice is False or choice is None or game_of(d) != 'tekken7':
        return None
    return d.DONOR


def lower_share(mesh, bon):
    """The share of a mesh's skin weights that are on the lower body's joints (LOWER_ROOT and what hangs from it)."""
    names = [n.split(':')[-1] for n in bon['names']]
    below = np.zeros(len(names) + 1, bool)
    for i, name in enumerate(names):
        j = i
        while j >= 0 and names[j] != LOWER_ROOT:
            j = bon['parent'][j]
        below[i] = j >= 0
    lower = total = 0.0
    for poly in mesh['polys']:
        v = poly['verts']
        if 'bones' not in v.dtype.names:
            continue
        w = v['w'].astype(np.float64)
        lower += float((w * below[np.minimum(v['bones'].astype(np.int64), len(names))]).sum())
        total += float(w.sum())
    return lower / total if total else 0.0


def own_pieces(body, code, bon=None):
    """{EquipPos: [meshes]} of the fighter's own outfit in its body model (model.py's part names), or {} unless it
    has both an upper and a lower piece (a one-piece body cannot give way to one garment). A piece named as an
    upper or a lower body is one; a full-body piece or one worn with it (Noctis's jacket and the trousers it
    comes with) is the half that holds PIECE_SIDE of its weights (`bon`: the body's skeleton), and neither when it
    covers both (the body stays whole then)."""
    out = {}
    for mesh in body['meshes']:
        for tag, pos in OWN_PIECES:
            if mesh['name'].startswith(code + tag):
                out.setdefault(pos, []).append(mesh)
        if bon is not None and mesh['name'].startswith(tuple(code + tag for tag in OWN_OTHERS)):
            share = lower_share(mesh, bon)
            if PIECE_SIDE <= share:
                out.setdefault(LOWER, []).append(mesh)
            elif share <= 1 - PIECE_SIDE:
                out.setdefault(UPPER, []).append(mesh)
            else:
                return {}
    return out if len(out) == len(OWN_PIECES) else {}


def for_pack(archives, d, contents, outfit_codes=(), log=print):
    """The wardrobe of a fighter's whole pack: its body and each preset outfit's body (a complete body of its own
    under another code, sharing the fighter's part packs: its own pieces get the next member numbers).
    d: the definition (CODE, SEX); contents: the pack's files {suffix or name: bytes}. -> files to add / replace."""
    source_code = source_of(d)
    if source_code is None:
        return {}
    girth = pack_girth(archives, d.CODE, source_code, [(contents[c + '.nud'], contents[c + '.bon'])
                                                       for c in ('',) + tuple(outfit_codes)])
    out = build(archives, d.CODE, source_code, {s: contents[s] for s in ('.nud', '.nut', '.bon', '.xml')}, log=log,
                girth=girth)
    if not out:
        return {}
    base = min(t['gidx'] for t in nutfile.read(contents['.nut'])['textures']) & ~0xFFF
    for k, code in enumerate(outfit_codes):
        files = {s: contents[code + s] for s in ('.nud', '.nut', '.bon', '.xml')}
        # (the garments' own skin names the copied skin textures by id: every body holds them under the first's)
        more = build(archives, d.CODE, source_code, files, own_first=OWN_FIRST + OWN_STEP * (k + 1),
                     log=lambda s: None, texture_base=base, girth=girth)
        if not more:
            log('wardrobe: preset %s keeps its body whole (no outfits on it)' % code)
            continue
        for name, data in more.items():           # (the garments are the ones fitted to the fighter's first body)
            if name.startswith('.'):
                out[code + name] = data
            else:
                out.setdefault(name, data)
    # what CUSTOMIZE mode offers: the rows the body it shows can wear (the port shows the first preset outfit's
    # body when there are presets, as a saved slot is worn on it in a fight)
    first = (outfit_codes[0] + '.xml') if outfit_codes else '.xml'
    shop = shop_list(archives, source_code, out[first]) if first in out else None
    if shop is None:
        log('wardrobe: no shop list (CUSTOMIZE mode stays closed for this fighter)')
    else:
        out[SHOP_FILE] = shop
    return out


def build(archives, code, source_code, files, own_first=OWN_FIRST, labels=None, log=print, texture_base=None,
          girth=None):
    """Fits the source fighter's outfits to the added fighter.

    files: the body's {'.nud', '.nut', '.bon', '.xml'} (bytes, as the importer made them);
    texture_base: the copied skin textures are numbered from texture_base + FIRST_TEXTURE (default: the id range
    the body's own textures are in);
    own_first: the first own-pack member number for its own outfit pieces;
    labels: the shop rows to fit (default: outfit_rows of the source);
    girth: how much thicker than the source the fighter is (girth_of; default: measured on this body alone).
    -> {file name: bytes} to add to the pack's files (the four changed, and `parts/...`), or {} when it cannot be
    done for this fighter (said through log)."""
    labels = outfit_rows(archives, source_code) if labels is None else labels
    body = nudfile.read(files['.nud'])
    target_bon = bonefile.read(files['.bon'])
    pieces = own_pieces(body, code, target_bon)
    face = next((m for m in body['meshes'] if m['name'] == code + '_fac'), None)
    if not pieces or face is None:
        log('wardrobe: no outfits: the body is not an upper piece, a lower piece and a face')
        return {}
    for key in (source_code + '.nud', source_code + '.nut', source_code + '.bon', source_code + '.xml'):
        if not archives.has(key_of(key)):
            log('wardrobe: no outfits: the game has no %s' % key)
            return {}
    source = nudfile.read(archives.read_name(source_code + '.nud'))
    source_nut = nutfile.read(archives.read_name(source_code + '.nut'))
    source_bon = bonefile.read(archives.read_name(source_code + '.bon'))
    source_db = bxml.parse(archives.read_name(source_code + '.xml'))
    shifts = joint_shifts(source_bon, target_bon)
    if np.abs(shifts).max() > HUMAN_REACH:
        log('wardrobe: no outfits: not %s\'s size (a joint %.0f mm from its place on %s)'
            % (source_code, np.abs(shifts).max(), source_code))
        return {}
    source_face = next((m for m in source['meshes'] if m['name'] == FACE_MESH), None)
    if source_face is None:
        log('wardrobe: no outfits: %s has no face mesh' % source_code)
        return {}
    rows = shop_rows(archives, labels)
    by_index = {int(_attrs(i)['index']): i for i in source_db[0]['children']}
    model_pack, texture_pack, bone_pack, own_bone_pack, spring_pack = source_packs(archives, source_db[0], source_bon)
    if model_pack is None:
        log('wardrobe: no outfits: %s\'s part models were not found in the game' % source_code)
        return {}
    missing = [kind for kind, pack in (('ti', texture_pack), ('bi', own_bone_pack), ('bci', bone_pack))
               if pack is None]
    # a garment's own bones are numbered (springs name them by number): one whose numbers the fighter's body already
    # uses for bones of its own (hair, cloth) cannot be worn with it
    taken = set(target_bon['opt']) - set(source_bon['opt'])

    def clashes(inst):
        for g in itemdb.groups(inst):
            a = _attrs(g)
            if 'mi' not in a:
                continue
            pack, index = (own_bone_pack, a.get('bi')) if 'bi' in a else (bone_pack, a.get('bci'))
            if pack is not None and index is not None and \
                    set(bonefile.read(archives.read(member_key(pack, int(index))))['opt']) & taken:
                return True
        return False
    wanted = []                     # the Instances the rows name, each once, in row order
    for label in labels:
        row = rows.get(label)
        if row is None:
            log('wardrobe: the shop list has no %s' % label)
            continue
        insts = [by_index.get(index) for _, index, _ in row['items']]
        if any(i is None or not fits(i) or any(name in missing for g in itemdb.groups(i) for name, _ in g['attrs'])
               for i in insts):
            if not all(i is not None and _attrs([c for c in i['children'] if c['tag'] == 'Data'][0]).get('EquipType')
                       == itemdb.DEFAULT_COSTUME for i in insts):
                log('wardrobe: %s left out (an item this cannot fit)' % label)
            rows.pop(label)
            continue
        if any(clashes(i) for i in insts):
            log('wardrobe: %s left out (its own bones\' numbers are taken by bones of %s\'s body)' % (label, code))
            rows.pop(label)
            continue
        wanted += [i for i in insts if i not in wanted]

    neck = Neck(source_face, face, shifts)
    if girth is None:
        girth = girth_of(skin_patches([m for m in source['meshes'] if is_cut(m['name'])], source_bon),
                         own_skin(body, code, target_bon))
    thick = Girth(source_bon, girth)
    # skin: the textures the cuts draw, and the garments' own skin, copied with the fighter's tone
    base_ids = {t['gidx'] for t in source_nut['textures']}
    cuts = [m for m in source['meshes'] if is_cut(m['name'])]
    garments = {}                   # member number -> model
    garment_bones = {}
    for inst in wanted:
        for g in itemdb.groups(inst):
            a = _attrs(g)
            if 'mi' in a:
                garments[int(a['mi'])] = nudfile.read(archives.read(member_key(model_pack, int(a['mi']))))
                if 'bi' in a:               # (its own skeleton: what its vertices' bone numbers mean)
                    garment_bones[int(a['mi'])] = bonefile.read(archives.read(member_key(own_bone_pack, int(a['bi']))))
                elif 'bci' in a and bone_pack is not None:
                    garment_bones[int(a['mi'])] = bonefile.read(archives.read(member_key(bone_pack, int(a['bci']))))
    used = set()
    colour_ids = set()
    for model in [dict(meshes=cuts)] + list(garments.values()):
        used |= _texture_ids(model) & base_ids
        colour_ids |= {mat['textures'][0]['id'] for m in model['meshes'] for p in m['polys'] for mat in p['materials']
                       if mat['flags'] == SKIN_FLAGS and mat['textures']}
    own_nut = nutfile.read(files['.nut'])
    images = {}
    own_meshes = [m for ms in pieces.values() for m in ms]
    sampled = skin_polygon(face, own_meshes)
    for nut, polys in ((source_nut, source_face['polys']), (own_nut, [sampled] if sampled is not None else [])):
        ids = {p['materials'][0]['textures'][0]['id'] for p in polys if p['materials'] and p['materials'][0]['textures']}
        for t in nut['textures']:
            if t['gidx'] in ids and t['fmt'] in (0, 1, 2):
                images[t['gidx']] = nutfile.decode(t)
    gain = skin_gain(source_face, face, images, own_meshes)
    if texture_base is None:
        texture_base = min(t['gidx'] for t in own_nut['textures']) & ~0xFFF
    textures, ids = skin_textures(source_nut, used, colour_ids, gain, texture_base + FIRST_TEXTURE)
    log('wardrobe: %s\'s bare body and %d outfits fitted (joints moved up to %.0f mm, neck ring %.0f mm); skin gain '
        '%.2f %.2f %.2f; %d skin textures, %.1f MB' % (source_code, len(rows), np.abs(shifts).max(), neck.worst,
                                                     gain[0], gain[1], gain[2], len(textures),
                                                     sum(len(m) for t in textures for m in t['mips']) / 2 ** 20))
    log('wardrobe: girth against %s: arms %.2f, legs %.2f, trunk %.2f' % (source_code, girth['arm'], girth['leg'],
                                                                         girth['trunk']))

    out = {}
    # the body: the fighter's own pieces leave it, the cuts join it
    cut_model = renumber(fit(dict(meshes=copy.deepcopy(cuts), sphere=source['sphere']), shifts, neck, thick.of()),
                         ids)
    moved = [m for ms in pieces.values() for m in ms]
    body['meshes'] = [m for m in body['meshes'] if not any(m is x for x in moved)] + cut_model['meshes']
    body['bone_first'] = body['bone_last'] = None
    out['.nud'] = nudfile.write(body)
    groups = {}
    number = own_first
    kept = _texture_ids(body)
    drawn = {pos: _texture_ids(dict(meshes=pieces[pos])) for _, pos in OWN_PIECES}
    gone = set()
    for _, pos in OWN_PIECES:
        meshes = pieces[pos]
        out['parts/bone/%d.bon' % number] = bonefile.write(piece_skeleton(target_bon, meshes))
        piece = dict(version=body.get('version', 0x0201), meshes=meshes,
                     sphere=nudfile.bounding_sphere(np.concatenate([p['verts']['pos'] for m in meshes for p in m['polys']])),
                     bone_first=None, bone_last=None)
        out['parts/model/%d.nud' % number] = nudfile.write(piece)
        # its textures: a part finds its textures in its own texture file, so every one it draws is in it (a
        # part model without a texture member never finishes loading); those nothing left in the body draws leave
        # the body's file
        mine = [t for t in own_nut['textures'] if t['gidx'] in drawn[pos]]
        gone |= drawn[pos] - kept
        if not mine:
            mine = sorted(own_nut['textures'], key=lambda t: sum(len(m) for m in t['mips']))[:1]
        out['parts/texture/%d.nut' % number] = nutfile.write(mine)
        groups[pos] = [('mi', str(number)), ('ti', str(number)), ('bi', str(number)),
                       ('Filename', '%s/%s.nud' % (code, meshes[0]['name']))]
        number += 1
    own_nut['textures'] = [t for t in own_nut['textures'] if t['gidx'] not in gone] + textures
    out['.nut'] = nutfile.write(own_nut)
    # the garments: fitted, under the source's member numbers; their own textures as they are
    for index, model in sorted(garments.items()):
        part = garment_bones.get(index)
        s = shifts if part is None else joint_shifts(source_bon, target_bon, part)
        if part is None and nudfile.used_bones(model)[1] >= len(shifts):
            s = np.concatenate([shifts, np.zeros((nudfile.used_bones(model)[1] + 1 - len(shifts), 3))])
        out['parts/model/%d.nud' % index] = nudfile.write(renumber(fit(model, s, neck, thick.of(part)), ids))
    for inst in wanted:
        for g in itemdb.groups(inst):
            a = _attrs(g)
            if 'ti' in a:
                out['parts/texture/%s.nut' % a['ti']] = nutfile.write(garment_textures(
                    nutfile.read(archives.read(member_key(texture_pack, int(a['ti'])))), source_nut, textures, ids,
                    colour_ids, gain))
            if 'bi' in a:
                out['parts/bone/%s.bon' % a['bi']] = bonefile.write(part_skeleton(
                    bonefile.read(archives.read(member_key(own_bone_pack, int(a['bi'])))), target_bon))
            if 'pi' in a and spring_pack is not None:
                out['parts/mop/%s.mop' % a['pi']] = archives.read(member_key(spring_pack, int(a['pi'])))
    if spring_pack is None and any('pi' in _attrs(g) for i in wanted for g in itemdb.groups(i)):
        log('wardrobe: %s\'s spring files were not found in the game: its garments are worn without springs'
            % source_code)
        wanted = [static(i) for i in wanted]
    out['.xml'] = itemdb.with_wardrobe(files['.xml'], source_db, wanted, groups)
    out['wardrobe.txt'] = ''.join('%s: %s\n' % (label, record_text([rows[label]])) for label in labels
                                  if label in rows).encode('utf-8')
    return out
