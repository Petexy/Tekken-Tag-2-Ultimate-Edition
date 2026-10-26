"""A Tekken 8 fighter's costume: which meshes it wears and in which colours.

Character/Item/Customize_Set/<code>/CS_<code>_<name> (CustomizeSet; 1p and 2p are the default costume's two colour
sets, others 1p_v1.., kimono, sp01 ...) lists ItemPrefabSet (and ItemPrefabAccSet) item prefabs. An ItemPrefab
(Item_Prefab/<code>/<slot>/IP_*) names three assets:
    BaseItemRef (BaseItem): SetItemPositionId (1 hair, 2 face, 4 glasses, 6 full body, 9 extra head item ...),
        SourceSkeletalMeshSet {SourceMuscleRigMesh (the _msl mesh: the full rig, the one to use),
        SourceProportionRigMesh (_prp: the 130-bone proportion rig)}, or MeshType E_StaticMesh + SourceStaticMesh
        (a rigid item on a socket: glasses), HairScalpMask (a hair's mask painted on the face), cloth and bones
    BaseCharacterItemRef (BaseCharacterItem): FighterId, AssignTargetDependencyMeshArray [{TargetMeshPos (a position
        id), TargetDependencyMuscleRigMesh, Priority}]: a worn item that makes another position wear a variant (a hood
        or a head item: the hair's _I / _F mesh); the highest Priority wins
    CustomizeItemRef (CustomizeItem): the colours (material.py)
The 2P set differs from the 1P one in its body CustomizeItem only (the same meshes and materials).

Written for this project from the files themselves (no third-party code).
"""
from .. import InputError
from . import bake, material, uprops, zen

SET = '/Game/Character/Item/Customize_Set/%s/CS_%s_%s'
# tag order: the parts as the mesh lists them (face first, then hair and head items, then the body); merge order:
# face, body, then the rest (Tekken 8's _msl meshes all carry the whole 550-bone rig, so it matters little)
PART_ORDER = ('fac', 'har', 'hed', 'ex0', 'bdu', 'bdl', 'bdf', 'btm', 'fah', 'gla', 'acc')
MERGE_ORDER = ('fac', 'bdf', 'bdu', 'bdl', 'btm', 'har', 'hed', 'ex0', 'fah', 'gla', 'acc')
STATIC_MESH = 2                     # EBaseItemMeshType E_StaticMesh
SKIN_PROBE = 64                     # mip of a skin texture its mean colour is taken from (sheer cloth's skin colour)


def _props(store, path):
    pkg = store.package(material.package_of(path))
    ex = pkg.main_export()
    props, _ = uprops.read(pkg, ex)
    return ex.class_name, props


def set_path(store, code, which):
    """The CustomizeSet of `which` ('1p', '2p', '1p_v1', 'kimono' ... or a /Game/ path); InputError when the game has
    no such set (the message lists the ones it has)."""
    path = which if which.startswith('/') else SET % (code, code, which)
    if store.exists(path):
        return material.package_of(path)
    have = sorted(p.rsplit('/', 1)[-1][len('CS_%s_' % code):-len('.uasset')]
                  for p in store.find('/Game/Character/Item/Customize_Set/%s/' % code) if p.endswith('.uasset'))
    raise InputError('Tekken 8 has no costume %s for %s (it has: %s); verify the integrity of Tekken 8\'s files in '
                     'Steam if it should' % (which, code, ', '.join(have) or 'none'))


def costume(store, code, which='1p', materials=None):
    """A costume's parts and colours -> {'parts': [(tag, skeletal mesh path)], 'merge_order': [tags], 'colours': the
    object material.Materials.effective takes, 'set': the CustomizeSet path, 'static': [(tag, static mesh path)]
    (rigid socket items, not converted), 'prefabs': [item prefab paths]}. A tag is the item's slot folder (bdf,
    fac, har, ...; a second item of a slot gets a number). materials: a material.Materials to share its cache."""
    cs = set_path(store, code, which)
    cls, props = _props(store, cs)
    if cls != 'CustomizeSet':
        raise InputError('%s is a %s, not a Tekken 8 costume set' % (cs, cls))
    prefabs = [p for p in (props.get('ItemPrefabSet') or []) + (props.get('ItemPrefabAccSet') or []) if p]
    items, forced, static = [], {}, []
    for ip in prefabs:
        _, prefab = _props(store, ip)
        slot = material.package_of(ip).rsplit('/', 2)[-2]
        base = _props(store, prefab['BaseItemRef'])[1] if prefab.get('BaseItemRef') else {}
        if prefab.get('BaseCharacterItemRef'):
            for a in _props(store, prefab['BaseCharacterItemRef'])[1].get('AssignTargetDependencyMeshArray') or []:
                pos, mesh = a.get('TargetMeshPos'), a.get('TargetDependencyMuscleRigMesh')
                if mesh and (pos not in forced or a.get('Priority', 0) > forced[pos][0]):
                    forced[pos] = (a.get('Priority', 0), mesh)
        mesh = (base.get('SourceSkeletalMeshSet') or {}).get('SourceMuscleRigMesh')
        if base.get('MeshType') == STATIC_MESH or (not mesh and base.get('SourceStaticMesh')):
            static.append((slot, material.package_of(base.get('SourceStaticMesh'))))
            continue
        if mesh:
            items.append((slot, base.get('SetItemPositionId'), mesh))
    parts, seen = [], {}
    for slot, pos, mesh in items:
        if pos in forced:                         # (worn under another item: its variant)
            mesh = forced[pos][1]
        seen[slot] = seen.get(slot, 0) + 1
        tag = slot if seen[slot] == 1 else '%s%d' % (slot, seen[slot])
        parts.append((tag, material.package_of(mesh)))

    def rank(order):
        return lambda tag: (order.index(tag.rstrip('0123456789')) if tag.rstrip('0123456789') in order
                            else len(order), tag)
    parts.sort(key=lambda p: rank(PART_ORDER)(p[0]))
    if not parts:
        raise InputError('Tekken 8\'s costume %s has no skeletal meshes' % cs)
    materials = materials or material.Materials(store)
    colours = materials.costume_colours(prefabs)
    skin = skin_colour(store, materials, [path for _, path in parts])
    if skin is not None:
        colours[material.SHEER] = {bake.SHEER_COLOUR: skin}
    return {'parts': parts, 'merge_order': sorted((t for t, _ in parts), key=rank(MERGE_ORDER)),
            'colours': colours, 'set': cs, 'static': static, 'prefabs': [material.package_of(p) for p in prefabs]}


def mesh_materials(store, path):
    """The material instances a mesh package imports (object paths), from its header alone."""
    pid = store.package_id(path)
    header = store.package_header(pid) if pid is not None else None
    if header is None:
        return []
    pkg = zen.Package(header, store.file_path(path), pid, store.resolver, store)
    return [name + '.' + obj for name, obj in (i for i in pkg.imports if isinstance(i, tuple))
            if obj and not name.startswith('?') and zen.short_name(obj).startswith('MI_') and ':' not in obj]


def skin_colour(store, materials, meshes):
    """The mean linear colour ({r, g, b, a}) of the body skin the meshes wear (a skin material that is not the
    face's: the one named body first), or None."""
    found = []
    for mesh in meshes:
        for path in mesh_materials(store, mesh):
            try:
                eff = materials.effective(path)
            except (KeyError, ValueError, zen.ParseError):
                continue
            if eff['base'].startswith(bake.SKIN_BASES) and not eff['switches'].get('IsFace'):
                found.append((0 if 'body' in eff['name'].lower() else 1, eff['name'], eff))
    if not found:
        return None
    eff = min(found, key=lambda f: f[:2])[2]
    rgb, _ = bake.bake_skin(eff, material.Textures(store, SKIN_PROBE))
    m = rgb.reshape(-1, 3).mean(0)
    return {'r': float(m[0]), 'g': float(m[1]), 'b': float(m[2]), 'a': 1.0}
