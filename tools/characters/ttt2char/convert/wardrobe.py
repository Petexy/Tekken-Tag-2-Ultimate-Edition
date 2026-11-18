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
  2. the cuts appended to its body model with copies of the source's skin textures, their colours scaled to the
     fighter's own skin (`skin_gain`: its face's plain skin against the source's), and the neck's top ring moved
     onto the head's open rim (`Neck`: tucked just inside it, so no gap opens);
  3. its own imported outfit taken OUT of the body model and made the parts of the default-costume Instances
     (`<code>_bdu*` meshes: the upper body item, `<code>_bdl*`: the lower), bound to its skeleton as before. Worn by
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

Not done here (say so to the player rather than guess): hair and head items, items with the rarer own-pack members
(`fits`), fighters whose imported body is one mesh (Tekken 8), giants.
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
FIRST_TEXTURE = 0x700               # the copied skin textures' ids in the fighter's range (model.py's come first,
                                    # the effects' from particles.FIRST_ID = 0x800)
OWN_STEP = 4                        # ... a body's pieces take up to this many numbers (preset outfits: the next)
OWN_FIRST = 900                     # own-pack member numbers of the fighter's own outfit pieces (the source's
                                    # garments keep the source's numbers, all far below)
UPPER, LOWER = '上半身(胴体)', '下半身'    # EquipPos of the upper-body and lower-body items
OWN_PIECES = (('_bdu', UPPER), ('_bdl', LOWER))     # the imported body's meshes (model.py's names) -> the item
SOURCES = {'female': 'jun'}         # whose wardrobe a fighter of that sex is fitted with
BODY_SLOTS = (8, 12)                 # the record's slots of the upper-body and the lower-body garment
NECK_REACH = 45.0                   # mm from the head's rim over which the neck is drawn toward it
NECK_TUCK = (2.0, 1.5)              # mm the neck's top ring goes up and inward of the rim
GAIN_SPAN = (0.5, 2.0)              # the skin gain is kept within this
LUMA = np.array([0.2126, 0.7152, 0.0722])
SPRING_MAGIC = b'\x40\xa0\x00\x00'  # how a spring file begins (5.0): the game's loader insists on it
HALVED = 2                          # texture format (BC3: normal and specular maps) stored at half size


# ------------------------------------------------------------------------------------------------ the game's packs
def find_pack(archives, indices, accepts):
    """The key of the pack holding members `indices` (a pack's key is compiled into the game, not made from a name;
    a member's key is the pack's continued over the member's number, which can be undone: so every archive entry is
    tried as the first member, and the pack is the one whose other members exist and whose first member
    `accepts(index, data)`). None when there is none."""
    indices = sorted(set(indices))
    if not indices:
        return None
    found = []
    for key in archives.where:
        k = pack_of(key, indices[0])
        if all(archives.has(member_key(k, i)) for i in indices[1:]):
            found.append(k)
    for k in found:
        try:
            if accepts(indices[0], archives.read(member_key(k, indices[0]))):
                return k
        except (ValueError, AssertionError, KeyError, IndexError):
            continue
    return None


def spring_pack(archives, bones):
    """The key of the pack whose members are the spring files of the garments: `bones` = {member number: the
    spring bones' numbers of the skeleton the same Group names}. Every member must begin as a spring file does (the
    game stops on one that does not) and drive every spring bone of its skeleton: many packs hold spring files under
    the same few numbers, and another fighter's would be loaded without complaint and throw the cloth about.
    None when there is none."""
    def fits_bones(index, data):
        return data[:4] == SPRING_MAGIC and set(bones[index]) <= set(mopfile.read(data)['opt_ids'])
    indices = sorted(bones)
    if not indices:
        return None
    for key in archives.where:
        pack = pack_of(key, indices[0])
        try:
            if all(archives.has(member_key(pack, i)) for i in indices) and \
                    all(fits_bones(i, archives.read(member_key(pack, i))) for i in indices):
                return pack
        except (ValueError, AssertionError, KeyError, IndexError, struct.error):
            continue
    return None


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
    model_pack = find_pack(archives, models, is_model)
    texture_pack = bone_pack = own_bone_pack = None
    pairs, bones, own_bones, springs = {}, set(), set(), {}
    for inst in db_info['children']:
        for g in itemdb.groups(inst):
            a = _attrs(g)
            if 'mi' in a and 'ti' in a:
                pairs.setdefault(int(a['ti']), int(a['mi']))
            if 'bci' in a:
                bones.add(int(a['bci']))
            if 'bi' in a:
                own_bones.add(int(a['bi']))
            if 'pi' in a and 'bi' in a:
                springs.setdefault(int(a['pi']), int(a['bi']))
    if model_pack is not None and pairs:
        def is_textures(index, data):
            ids = {t['gidx'] for t in nutfile.read(data)['textures']}
            drawn = _texture_ids(nudfile.read(archives.read(member_key(model_pack, pairs[index]))))
            return bool(ids & drawn)
        texture_pack = find_pack(archives, pairs, is_textures)
    if bones or own_bones:
        base = bonefile.read(base_nut) if isinstance(base_nut, bytes) else base_nut

        def is_bones(index, data):
            b = bonefile.read(data)
            n = len(base['names'])
            return len(b['names']) >= n and [x.split(':')[-1] for x in b['names'][:n]] == \
                [x.split(':')[-1] for x in base['names']] and np.abs(b['t'][:n] - base['t']).max() < 0.01
        bone_pack = find_pack(archives, bones, is_bones)
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


def fit(model, shifts, neck=None):
    """`model` (a NUD's dict, changed in place) moved to the target's bind pose; `neck` also draws what lies near
    the source head's rim to the target head's."""
    for mesh in model['meshes']:
        points = []
        for poly in mesh['polys']:
            v = poly['verts']
            if 'bones' not in v.dtype.names:
                continue
            old = v['pos'].astype(np.float64)
            new = old + _moved(v, shifts)
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
    vertices, the mean of the brighter half (make-up, lips, brows and the shaded rim under the chin are the
    darker half). None without a texture."""
    poly = max(face['polys'], key=lambda p: len(p['verts']))
    image = textures.get(poly['materials'][0]['textures'][0]['id']) if poly['materials'] and \
        poly['materials'][0]['textures'] else None
    if image is None or 'uv' not in poly['verts'].dtype.names or len(poly['verts']) < 8:
        return None
    h, w = image.shape[:2]
    uv = poly['verts']['uv'][:, 0].astype(np.float64)
    x = ((uv[:, 0] % 1.0) * w).astype(np.int64) % w
    y = ((uv[:, 1] % 1.0) * h).astype(np.int64) % h
    colours = _linear(image[y, x, :3])
    luma = colours @ LUMA
    return colours[luma >= np.median(luma)].mean(0)


def skin_gain(source_face, target_face, textures):
    """The per-channel gain (linear colour) that gives the source's body skin the fighter's skin tone: the ratio of
    the two faces' plain skin (the game paints a fighter's body in its face's tone, and a player sees the body
    beside the face: a gain measured only where head and neck meet, a shaded strip, left a fair face on a darker
    body). textures: {id: decoded image} of both faces."""
    theirs, ours = plain_skin(source_face, textures), plain_skin(target_face, textures)
    if theirs is None or ours is None or (theirs < 1e-4).any():
        return np.ones(3)
    return np.clip(ours / theirs, *GAIN_SPAN)


def _linear(rgb8):
    x = np.asarray(rgb8, np.float64) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _srgb8(linear):
    x = np.clip(linear, 0.0, 1.0)
    return np.clip(np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055) * 255.0 + 0.5, 0, 255).astype(np.uint8)


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
        rgba[..., :3] = _srgb8(_linear(rgba[..., :3]) * gain)
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


def is_cut(name):
    return name.endswith('_O_OBJ') and name.startswith(CUT_PREFIXES) and name != FACE_MESH


def own_pieces(body, code):
    """{EquipPos: [meshes]} of the fighter's own outfit in its body model (model.py's part names), or {} unless it
    has both an upper and a lower piece (a one-piece body cannot give way to one garment)."""
    out = {}
    for mesh in body['meshes']:
        for tag, pos in OWN_PIECES:
            if mesh['name'].startswith(code + tag):
                out.setdefault(pos, []).append(mesh)
    return out if len(out) == len(OWN_PIECES) else {}


def for_pack(archives, d, contents, outfit_codes=(), log=print):
    """The wardrobe of a fighter's whole pack: its body and each preset outfit's body (a complete body of its own
    under another code, sharing the fighter's part packs: its own pieces get the next member numbers).
    d: the definition (CODE, SEX); contents: the pack's files {suffix or name: bytes}. -> files to add / replace."""
    source_code = SOURCES.get(d.SEX)
    if source_code is None:
        log('wardrobe: no outfits for a %s fighter yet' % d.SEX)
        return {}
    out = build(archives, d.CODE, source_code, {s: contents[s] for s in ('.nud', '.nut', '.bon', '.xml')}, log=log)
    if not out:
        return {}
    base = min(t['gidx'] for t in nutfile.read(contents['.nut'])['textures']) & ~0xFFF
    for k, code in enumerate(outfit_codes):
        files = {s: contents[code + s] for s in ('.nud', '.nut', '.bon', '.xml')}
        # (the garments' own skin names the copied skin textures by id: every body holds them under the first's)
        more = build(archives, d.CODE, source_code, files, own_first=OWN_FIRST + OWN_STEP * (k + 1),
                     log=lambda s: None, texture_base=base)
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


def build(archives, code, source_code, files, own_first=OWN_FIRST, labels=None, log=print, texture_base=None):
    """Fits the source fighter's outfits to the added fighter.

    files: the body's {'.nud', '.nut', '.bon', '.xml'} (bytes, as the importer made them);
    texture_base: the copied skin textures are numbered from texture_base + FIRST_TEXTURE (default: the id range
    the body's own textures are in);
    own_first: the first own-pack member number for its own outfit pieces;
    labels: the shop rows to fit (default: outfit_rows of the source).
    -> {file name: bytes} to add to the pack's files (the four changed, and `parts/...`), or {} when it cannot be
    done for this fighter (said through log)."""
    labels = outfit_rows(archives, source_code) if labels is None else labels
    body = nudfile.read(files['.nud'])
    pieces = own_pieces(body, code)
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
    target_bon = bonefile.read(files['.bon'])
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
    missing = [kind for kind, pack in (('ti', texture_pack), ('bi', own_bone_pack)) if pack is None]
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
        wanted += [i for i in insts if i not in wanted]

    shifts = joint_shifts(source_bon, target_bon)
    neck = Neck(source_face, face, shifts)
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
    for nut, mesh in ((source_nut, source_face), (own_nut, face)):
        ids = {p['materials'][0]['textures'][0]['id'] for p in mesh['polys'] if p['materials'] and p['materials'][0]['textures']}
        for t in nut['textures']:
            if t['gidx'] in ids and t['fmt'] in (0, 1, 2):
                images[t['gidx']] = nutfile.decode(t)
    gain = skin_gain(source_face, face, images)
    if texture_base is None:
        texture_base = min(t['gidx'] for t in own_nut['textures']) & ~0xFFF
    textures, ids = skin_textures(source_nut, used, colour_ids, gain, texture_base + FIRST_TEXTURE)
    log('wardrobe: %s\'s bare body and %d outfits fitted (joints moved up to %.0f mm, neck ring %.0f mm); skin gain '
        '%.2f %.2f %.2f; %d skin textures, %.1f MB' % (source_code, len(rows), np.abs(shifts).max(), neck.worst,
                                                     gain[0], gain[1], gain[2], len(textures),
                                                     sum(len(m) for t in textures for m in t['mips']) / 2 ** 20))

    out = {}
    # the body: the fighter's own pieces leave it, the cuts join it
    cut_model = renumber(fit(dict(meshes=copy.deepcopy(cuts), sphere=source['sphere']), shifts, neck), ids)
    moved = [m for ms in pieces.values() for m in ms]
    body['meshes'] = [m for m in body['meshes'] if not any(m is x for x in moved)] + cut_model['meshes']
    body['bone_first'] = body['bone_last'] = None
    out['.nud'] = nudfile.write(body)
    groups = {}
    number = own_first
    out['parts/bone/%d.bon' % own_first] = files['.bon']       # the pieces' skeleton: the body's own, as it is
    kept = _texture_ids(body)
    drawn = {pos: _texture_ids(dict(meshes=pieces[pos])) for _, pos in OWN_PIECES}
    gone = set()
    for _, pos in OWN_PIECES:
        meshes = pieces[pos]
        piece = dict(version=body.get('version', 0x0201), meshes=meshes,
                     sphere=nudfile.bounding_sphere(np.concatenate([p['verts']['pos'] for m in meshes for p in m['polys']])),
                     bone_first=None, bone_last=None)
        out['parts/model/%d.nud' % number] = nudfile.write(piece)
        # its textures: those nothing else draws leave the body's file with it (a part model without a texture
        # member never finishes loading; a piece all of whose textures something else draws takes a copy of one)
        others = kept | set().union(*[ids_ for p_, ids_ in drawn.items() if p_ != pos])
        mine = [t for t in own_nut['textures'] if t['gidx'] in drawn[pos] - others]
        gone |= {t['gidx'] for t in mine}
        if not mine:
            mine = sorted((t for t in own_nut['textures'] if t['gidx'] in drawn[pos]),
                          key=lambda t: sum(len(m) for m in t['mips']))[:1]
        out['parts/texture/%d.nut' % number] = nutfile.write(mine)
        groups[pos] = [('mi', str(number)), ('ti', str(number)), ('bi', str(own_first)),
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
        out['parts/model/%d.nud' % index] = nudfile.write(renumber(fit(model, s, neck), ids))
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
            if 'pi' in a and 'bi' in a and spring_pack is not None:
                out['parts/mop/%s.mop' % a['pi']] = archives.read(member_key(spring_pack, int(a['pi'])))
    if any('pi' in _attrs(g) and ('bi' not in _attrs(g) or spring_pack is None)
           for i in wanted for g in itemdb.groups(i)):
        log('wardrobe: %s\'s spring files were not found in the game: its garments are worn without springs'
            % source_code)
        wanted = [static(i) for i in wanted]
    out['.xml'] = itemdb.with_wardrobe(files['.xml'], source_db, wanted, groups)
    out['wardrobe.txt'] = ''.join('%s: %s\n' % (label, record_text([rows[label]])) for label in labels
                                  if label in rows).encode('utf-8')
    return out
