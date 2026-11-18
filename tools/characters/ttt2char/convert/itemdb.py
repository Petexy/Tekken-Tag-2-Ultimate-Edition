"""The added fighter's item database (`<code>.xml`, BXML), made from the donor's.

A fighter's database has two top-level elements: InstanceInfo (one Instance per costume item: its Data, the Model
sections A/B naming part models in the fighter's own packs, effects) and OffsetInfo. The added fighter has no parts
of its own (everything is in its body model), so it keeps only the donor's default-costume Instances (same labels
and indices: upper and lower body, head, the default effects and the rage aura) with their part lists emptied. A
database naming parts the fighter's packs do not have makes the loading screen hang.

Worn items: an Instance whose part models all come from the game's COMMON packs (Group attributes `mci tci bci pci
gci hci eci nci`, and `ci`, which reads the shared "texchange" packs) needs nothing from the fighter's own packs,
so the added fighter can keep it as it is in the donor's database: same label and index (a customization record
names an item by its index, and the donor's shop rows stay valid), with the Offsets its Groups name (Name + Path)
copied into OffsetInfo. An Offset places the item on a joint found by name in the body's skeleton (the first bone
whose name contains the Joint text), and the added skeletons keep the donor's bone names, so the Joint text is
copied unchanged. `ITEMS` lists the labels kept; `common_only` is the test for widening the list.

The fighter's effects: its moves spawn effects by id (move property 0x801f = body part << 8 | id), and the ids mean
the effect files that the worn items' EffectParameters name; the default set's character effect Instance
(`cmn_eff_default`) gets the fighter's ids, naming its effect files by bare name (the title loads
`<code>/alo/<name>.alo` with the fighter's code: copies of the game's own, effects.py).
"""
import copy

from ..ttt2 import bxml

DEFAULT_COSTUME = 'デフォルトコスチューム'       # the EquipType of default-costume items ("default costume")
EFFECT_INSTANCE = 'cmn_eff_default'     # the default set's character effects
ANY_BONE = '指定無し'                  # an effect parameter's bone: "unspecified" (the move's body part)


OWN_PACK = ('mi', 'ti', 'bi', 'pi', 'gi', 'hi', 'ei', 'ni')    # a Group's members of the fighter's own packs
ITEMS = ('cmn_meg_wellington',)         # the donor's worn items the added fighter keeps (labels; common-pack only)


def groups(inst):
    """The part-model Groups of an Instance (both Model sections)."""
    return [g for m in inst['children'] if m['tag'] == 'Model' for g in m['children'] if g['tag'] == 'Group']


def common_only(inst):
    """Whether the Instance has part models and all of them come from the common packs."""
    found = groups(inst)
    return bool(found) and not any(name in OWN_PACK for g in found for name, _ in g['attrs'])


def offsets_named(inst):
    """The (Name, Path) of the Offsets an Instance's Groups are placed by."""
    return {(dict(o['attrs']).get('Name'), dict(o['attrs']).get('Path'))
            for g in groups(inst) for o in g['children'] if o['tag'] == 'Offset'}


def body_only(donor_db, effects=None, items=ITEMS):
    """effects: {effect id: [(effect name, bone or None)]} added to the character effect Instance.
    items: labels of the donor's worn items kept whole (with_items)."""
    info, offsets = bxml.parse(donor_db)[:2]
    instances = []
    for inst in info['children']:
        data = [c for c in inst['children'] if c['tag'] == 'Data']
        if not data or dict(data[0]['attrs']).get('EquipType') != DEFAULT_COSTUME:
            continue
        inst = copy.deepcopy(inst)
        kids = []
        for c in inst['children']:
            if c['tag'] == 'Model' and not any(g['tag'] == 'EffectGroup' for g in c['children']):
                c['children'] = []               # no part model; effect groups stay
            if c['tag'] != 'ModelBConditions':
                kids.append(c)
        inst['children'] = kids
        if effects and dict(inst['attrs']).get('label') == EFFECT_INSTANCE:
            add_effects(inst, effects)
        instances.append(inst)
    return with_items(bxml.write([dict(tag=info['tag'], attrs=info['attrs'], children=instances),
                                  dict(tag=offsets['tag'], attrs=offsets['attrs'], children=[])]), donor_db, items)


def with_items(db, donor_db, items=ITEMS):
    """The database with the donor's worn items `items` (labels) added after its own Instances, as they are in the
    donor's database, and the Offsets they are placed by. Left out: a label the donor does not have, an item that
    needs the donor's own packs, and an index or Offset the database already holds."""
    info, offsets = bxml.parse(db)[:2]
    donor_info, donor_offsets = bxml.parse(donor_db)[:2]
    indices = {dict(i['attrs']).get('index') for i in info['children']}
    placed = set()
    for inst in donor_info['children']:
        attrs = dict(inst['attrs'])
        if attrs.get('label') in items and attrs.get('index') not in indices and common_only(inst):
            info['children'].append(copy.deepcopy(inst))
            indices.add(attrs.get('index'))
            placed |= offsets_named(inst)

    def name(offset):
        return dict(offset['attrs']).get('Name'), dict(offset['attrs']).get('Path')
    placed -= {name(o) for o in offsets['children']}
    offsets['children'] += [copy.deepcopy(o) for o in donor_offsets['children'] if name(o) in placed]
    return bxml.write([info, offsets])


def with_wardrobe(db, source, instances, own_groups):
    """The database with garments fitted to the fighter (wardrobe.py).
    source: the parsed database the garments come from; instances: its Instances to add, as they are (label, index
    and Groups kept: their own-pack members are in the fighter's pack under the same numbers), with the Offsets they
    name; own_groups: {EquipPos: Group attributes}: the part model of the fighter's own outfit piece, given to its
    default-costume Instance of that position (section A), so that the piece is worn as an item and gives way to a
    garment in its slot."""
    info, offsets = bxml.parse(db)[:2]
    for inst in info['children']:
        data = [c for c in inst['children'] if c['tag'] == 'Data']
        attrs = own_groups.get(dict(data[0]['attrs']).get('EquipPos')) if data and \
            dict(data[0]['attrs']).get('EquipType') == DEFAULT_COSTUME else None
        if attrs is None:
            continue
        model = next((c for c in inst['children'] if c['tag'] == 'Model' and dict(c['attrs']).get('section') == 'A'), None)
        if model is not None and not any(dict(g['attrs']).get('mi') == dict(attrs)['mi'] for g in model['children']):
            model['children'].insert(0, dict(tag='Group', attrs=list(attrs), children=[]))
    indices = {dict(i['attrs']).get('index') for i in info['children']}
    placed = set()
    for inst in instances:
        if dict(inst['attrs']).get('index') not in indices:
            info['children'].append(copy.deepcopy(inst))
            indices.add(dict(inst['attrs']).get('index'))
            placed |= offsets_named(inst)

    def name(offset):
        return dict(offset['attrs']).get('Name'), dict(offset['attrs']).get('Path')
    placed -= {name(o) for o in offsets['children']}
    offsets['children'] += [copy.deepcopy(o) for o in source[1]['children'] if name(o) in placed]
    return bxml.write([info, offsets])


def effect_names(donor_db):
    """The bare effect names of the donor's character effect Instance."""
    info = bxml.parse(donor_db)[0]
    for inst in info['children']:
        if dict(inst['attrs']).get('label') == EFFECT_INSTANCE:
            return [dict(g['attrs']).get('Filename') for m in inst['children'] if m['tag'] == 'Model'
                    for g in m['children'] if g['tag'] == 'EffectGroup' and '/' not in dict(g['attrs']).get('Filename', '/')]
    return []


def add_effects(inst, effects):
    """Names the effect files in the Instance's model (section A) and maps the ids to them (in place of the
    donor's effects of the same ids)."""
    model = next(c for c in inst['children'] if c['tag'] == 'Model' and dict(c['attrs']).get('section') == 'A')
    params = next((c for c in inst['children'] if c['tag'] == 'EffectParameters'), None)
    if params is None:
        params = dict(tag='EffectParameters', attrs=[], children=[])
        inst['children'].append(params)
    params['children'] = [c for c in params['children'] if int(dict(c['attrs']).get('id', -1)) not in effects]
    used = {dict(c['attrs']).get('effect') for c in params['children']} | {p for fs in effects.values() for p, _ in fs}
    model['children'] = [c for c in model['children'] if c['tag'] != 'EffectGroup' or
                         dict(c['attrs']).get('Filename') in used]       # effect files no id names any more
    named = {dict(c['attrs']).get('Filename') for c in model['children'] if c['tag'] == 'EffectGroup'}
    for effect_id, files in sorted(effects.items()):
        for path, bone in files:
            if path not in named:
                model['children'].append(dict(tag='EffectGroup', attrs=[('Filename', path)], children=[]))
                named.add(path)
            params['children'].append(dict(tag='Parameter', attrs=[('id', str(effect_id)), ('bone', bone or ANY_BONE),
                                                                   ('effect', path)], children=[]))


def effect_files_named(db):
    """The bare effect names a database's character effect Instance maps ids to (its effect files still in use)."""
    info = bxml.parse(db)[0]
    for inst in info['children']:
        if dict(inst['attrs']).get('label') == EFFECT_INSTANCE:
            return {dict(p['attrs']).get('effect') for c in inst['children'] if c['tag'] == 'EffectParameters'
                    for p in c['children']}
    return set()


def effect_ids(db):
    """The effect ids a database's character effect Instance maps."""
    info = bxml.parse(db)[0]
    for inst in info['children']:
        if dict(inst['attrs']).get('label') == EFFECT_INSTANCE:
            return {int(dict(p['attrs']).get('id')) for c in inst['children'] if c['tag'] == 'EffectParameters'
                    for p in c['children']}
    return set()
