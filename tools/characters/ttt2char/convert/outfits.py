"""Preset model definitions read from the player's T7 costume sets.

Keep gameplay definitions intact: a preset changes only the model inputs.
"""
import types
from pathlib import Path
import numpy as np

from . import art, chains, face, model, tiger, weapons
from ..tekken7.material import short_ref
from ..tekken7.pak import EncryptedError
from ..ttt2 import bone, nud, nut
from ..ttt2.archive import key_of

MAX_PRESETS = 14  # native builder caps total rows at fourteen, including customization rows
TEXTURE_STRIDE = 16
# Pack metadata persists these codes: never derive them from roster ordering.
PREFIXES = {
    'kzm': 'kz', 'dnc': 'ob', 'elz': 'oc', 'ita': 'od', 'mrx': 'oe',
    'crz': 'of', 'mut': 'og', 'ltn': 'oh', 'frv': 'oi', 'arb': 'oj',
    'nsc': 'fk', 'nsb': 'ol', 'nsd': 'om', 'kmi': 'on', 'nsa': 'oo',
    'mry': 'op', 'mrz': 'oq',
}


def blueprint_items(paks, items):
    """Include component meshes in wearable blueprints (Chloe tail, Katarina glasses)."""
    out = list(items)
    for item in items:
        blueprint = short_ref(item.get('ItemBlueprint'))
        if not blueprint:
            continue
        seen = {short_ref(item.get(key)) for key in ('SourceSkeletalMesh', 'SourceStaticMesh')}
        for _, props in model.export_properties(model.load(paks, blueprint.split('.')[0])):
            if not props:
                continue
            for key, source, kind in (('SkeletalMesh', 'SourceSkeletalMesh', 'SkeletalMeshAnim'),
                                      ('StaticMesh', 'SourceStaticMesh', 'StaticMeshSocket')):
                ref = short_ref(props.get(key))
                if not ref or ref in seen:
                    continue
                seen.add(ref)
                out.append(dict(item, MeshType=kind, **{source: props[key]}))
    return out


def definition(paks, base, costume):
    """Copy a fighter definition, deriving every worn mesh from a preset set."""
    items = blueprint_items(paks, model.costume_items(paks, costume, follow=True))
    parts = []
    meshes = dict(base.MESHES)
    categories = {'Face': 'fac', 'Lower': 'bdl', 'Upper': 'bdu',
                  'Hair': 'har', 'Face_Hair': 'fah', 'Head': 'hed', 'Full_Body': 'bdf',
                  'Full_Head': 'hef', 'Glasses': 'gla', 'Hair_Acc': 'oph', 'Lower_Acc': 'tail', 'Extra': 'ext'}
    seen = set()
    for item in items:
        # Some T7 items (Katarina's face) omit the default MeshType.
        if item.get('MeshType') not in (None, 'SkeletalMeshAnim'):
            continue
        ref = short_ref(item.get('SourceSkeletalMesh'))
        if not ref:
            continue
        path = ref.split('.')[0]
        if path.lower() in seen:
            continue
        seen.add(path.lower())
        category = next((tag for folder, tag in categories.items()
                         if '/%s/' % folder.lower() in path.lower()), None)
        if category is None:
            raise ValueError('unsupported preset mesh category: %s' % path)
        if category == 'ext' and '_har' in path.lower():
            category = 'har'
        tag = category
        if any(t == tag for t, _ in parts):
            tag += str(len(parts))
        parts.append((tag, path))
        parent = meshes[category][1] if category in meshes else (
            'KOSHI_jnt' if category in ('bdf', 'bdl', 'tail') else
            'MUNE2_jnt' if category == 'bdu' else 'ATAMA_jnt_assist')
        meshes.setdefault(tag, (base.CODE + '_' + tag, parent, 0 if category == 'bdf' else 50 + len(parts)))
    if not parts:
        raise ValueError('preset has no skeletal meshes: %s' % costume)
    order = [t for t in base.TEKKEN7['merge_order'] if any(t == tag for tag, _ in parts)]
    order += [tag for tag, _ in parts if tag not in order]
    copied = {key: value for key, value in vars(base).items() if key.isupper()}
    copied.update(TEKKEN7={'costume': costume, 'parts': parts, 'merge_order': order},
                  MESHES=meshes, DEPENDENCY_ITEMS=True, PRESET_ITEMS=items)
    if any(getattr(base, key, ()) for key in ('CHAINS', 'HIDE', 'COVERED')):
        # Alternate hairstyles/masks need only the rules whose bones and
        # materials are actually present. Never mutate the base definition.
        skeletons, materials = {}, set()
        for tag, path in parts:
            mesh = model.t7mesh.SkeletalMesh(model.load(paks, path))
            skeletons[tag] = set(mesh.skeleton['names'])
            materials.update(short_ref(m['material']).split('.')[-1]
                             for m in mesh.materials if short_ref(m['material']))
        for key in ('CHAINS', 'HIDE'):
            copied[key] = [rule for rule in getattr(base, key, ())
                           if rule[0] in skeletons and rule[1] in skeletons[rule[0]]]
        copied['COVERED'] = [rule for rule in getattr(base, 'COVERED', ())
                             if rule[0] in skeletons and rule[1] in materials]
    return types.SimpleNamespace(**copied)


def codes(base):
    """Reserved three-letter body codes; these are not additional roster fighters."""
    if base.CODE not in PREFIXES:
        raise ValueError('preset body codes have not been assigned for %s' % base.CODE)
    if not 1 <= len(base.PRESETS) <= MAX_PRESETS:
        raise ValueError('expected one to fourteen preset outfits')
    return [PREFIXES[base.CODE] + chr(ord('a') + i) for i, _ in enumerate(base.PRESETS)]


def check_tiger_skeleton(skeleton, reference):
    """The shared tiger animations pose its bones by number (the port's part-3 channels: OPT 600 + channel), so every
    outfit has the base fighter's tiger bones, parents and bind transforms, wherever its cloth puts them."""
    if reference is None:
        raise ValueError('tiger presets require the base skeleton for compatibility checks')
    def layout(s):
        prefixes = tuple('cha:OPT%d_' % n for n in s['opt'] if tiger.OPT_FIRST <= n < weapons.OPT_FIRST)
        bones = [i for i, name in enumerate(s['names']) if name.startswith(prefixes)]
        parent = lambda i: s['names'][s['parent'][i]] if 0 <= s['parent'][i] < len(s['names']) else None
        return bones, [(s['names'][i], parent(i)) for i in bones]
    (mine, names), (theirs, reference_names) = layout(skeleton), layout(reference)
    if names != reference_names:
        raise ValueError('preset tiger bones differ from the base animation skeleton')
    if not theirs:
        raise ValueError('base skeleton has no tiger bones')
    for field in ('t', 'r', 's'):
        if not np.allclose(skeleton[field][mine], reference[field][theirs], atol=1e-4):
            raise ValueError('preset tiger bind transforms differ from the base skeleton')


def relocate(model_bytes, texture_bytes, first):
    """Give each preset its own texture namespace, including in mirror matches."""
    mesh = nud.read(model_bytes)
    textures = nut.read(texture_bytes)['textures']
    mapping = {t['gidx']: first + i for i, t in enumerate(textures)}
    for part in mesh['meshes']:
        for poly in part['polys']:
            for material in poly['materials']:
                for texture in material['textures']:
                    texture['id'] = mapping.get(texture['id'], texture['id'])
    for texture in textures:
        texture['gidx'] = mapping[texture['gidx']]
        texture.pop('ext', None)
    return nud.write(mesh), nut.write(textures)


def build(paks, archives, rpx, base, slot, xml, springs, body, standing=None, log=print, reference_bon=None, cached=None):
    """Build complete preset bodies and previews, sharing the base fighter's gameplay.

    springs(bon, cloth springs) -> a body's spring entries (.mop) or None (importer.spring_file); body: the base
    fighter's (nud, nut, bon, mop), the preset of its own costume (its 2P colours' palette entries are the base
    fighter's: the presets made here have none); standing: the pose the cloth rests in (cloth.standing).
    A preset needing an encrypted file Tekken 7 did not hand over is left out with a warning (no files of its code).
    No installed pack is changed here. Caller writes the returned files atomically.
    """
    files, previews = {}, []
    preview_suffixes = {'DefaultCos1P': '01', 'DefaultCos2P': '02'}
    for i, ((preset, label), code) in enumerate(zip(base.PRESETS, codes(base))):
        log('preset %d/%d: %s' % (i + 1, len(base.PRESETS), label))
        source_code = base.TEKKEN7_CODE.upper()
        costume = '/Game/Character/Item/Sets/%s/CS_%s_%s' % (source_code, source_code, preset)
        try:
            if cached is not None:
                d = definition(paks, base, costume)
                folder = Path(cached) / preset
                mesh, textures, skeleton = [(folder / (base.CODE + ext)).read_bytes()
                                           for ext in ('.nud', '.nut', '.bon')]
                saved_springs = folder / (base.CODE + '.mop')
                mop = saved_springs.read_bytes() if saved_springs.is_file() else springs(skeleton, None)
            elif costume == base.TEKKEN7['costume']:
                d = types.SimpleNamespace(**{key: value for key, value in vars(base).items() if key.isupper()})
                mesh, textures, skeleton, mop = body
            else:
                d = definition(paks, base, costume)
                mesh, textures, skeleton, _, cloth_springs = model.convert(paks, archives, d, slot, log=log,
                                                                           standing=standing)
                mop = springs(skeleton, cloth_springs)
            d.ART = dict(base.ART, costume=base.ART['costume'].rsplit('_', 1)[0] + '_' +
                         preview_suffixes.get(preset, getattr(base, 'PRESET_PREVIEWS', {}).get(preset, preset.upper())))
            picture = art.costume_previews(paks, archives, rpx, d, slot)
        except EncryptedError as error:
            # Codes are per preset and the chooser follows character.ini's list, so a gap is fine (nothing of this
            # preset is kept yet: one preview per outfit listed).
            log('WARNING: preset %s left out: Tekken 7 keeps %s encrypted and it is not saved (add the fighter again '
                'once Tekken 7 reads it)' % (label, error.args[0]))
            continue
        if picture is None:
            raise ValueError('missing preset preview: %s' % preset)
        if reference_bon is not None:
            skeleton = face.same_joints(skeleton, reference_bon)
        mesh, textures = relocate(mesh, textures, 0x10500000 + (slot * TEXTURE_STRIDE + i) * 0x1000)
        files.update({code + '.nud': mesh, code + '.nut': textures, code + '.bon': skeleton, code + '.xml': xml})
        skel = bone.read(skeleton)
        if reference_bon is not None and getattr(base, 'WEAPONS', ()):
            if weapons.of_skeleton(skel, base.WEAPONS) != weapons.of_skeleton(bone.read(reference_bon), base.WEAPONS):
                raise ValueError('preset weapon bindings differ from the base fighter')
        if getattr(base, 'TIGER', None):
            check_tiger_skeleton(skel, bone.read(reference_bon) if reference_bon is not None else None)
        if mop is None:                           # (the port needs each preset's own .mop)
            mop = (archives.read_name(base.DONOR + '.mop') if archives.has(key_of(base.DONOR + '.mop')) else
                   chains.empty_spring_file(archives.read_name(tiger.SPRING_TEMPLATE[0] + '.mop')))
        files[code + '.mop'] = mop
        texture = nut.read(picture)['textures'][0]
        texture['gidx'] += 128 + slot * TEXTURE_STRIDE + i
        texture.pop('ext', None)
        previews.append(texture)
    files['art/costumes.nut'] = nut.write(previews)
    return files
