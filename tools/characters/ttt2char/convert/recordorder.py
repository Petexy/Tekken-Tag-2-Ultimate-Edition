"""A fighter's skeleton in the order the game keeps its bone records, with its model's bone indices to match.

The game's bone container keeps the records of a skeleton's OPT bones (the .bon's last bones, the ones its OPT list
numbers) in ascending NUMBER order, whatever their order in the .bon, with their parents remapped (seen in a fight:
Miary Zo's records 263..285 were her OPT 600..622, written after her weapons OPT 800.. in the .bon, every record's
world its local times its parent record's), and it makes their world matrices in that record order: a bone whose
record comes before its parent's takes the parent's world of the frame before (one frame behind it). The GPU palette
of the model (vertex uniform block 9) is that record order too: entry i = record i's inverse bind times its world.

write() puts the OPT bones in that order in the skeleton itself and renumbers the model's vertex bone indices and
single binds alike, so the .bon's index of a bone is the index of its record (whatever the game does with the indices
of a .bon in another order). The bones before the OPT list keep their places, and so does every OPT bone of a skeleton
already in number order (TTT2's own skeletons, nearly all; Reina's, Azucena's). A parent must still come before its
children in number order (the importer numbers bones so: convert/snakes8.py PARENT_NUMBER); a skeleton where it does
not is left as it is.

Written for this project from the files themselves (no third-party code).
"""
import numpy as np


def _number(name):
    head = name.split('_', 1)[0]
    if head.startswith('cha:OPT') and head[7:].isdigit():
        return int(head[7:])
    return None


def permutation(skel):
    """[old index] of each new place (the identity when nothing moves), or None when the skeleton's OPT bones are not
    its last bones named by its OPT list, or a parent would come after its child."""
    names, opt = list(skel['names']), list(skel['opt'])
    n = len(names)
    first = n - len(opt)
    if first < 0 or [_number(x) for x in names[first:]] != opt:
        return None
    order = list(range(first)) + [first + i for i in sorted(range(len(opt)), key=lambda i: (opt[i], i))]
    new = {old: k for k, old in enumerate(order)}
    if any(skel['parent'][old] >= 0 and new[skel['parent'][old]] >= k for k, old in enumerate(order)):
        return None
    return order


def apply(skel, order):
    """The skeleton (bone.read's dict) with its bones in `order` (permutation()'s)."""
    new = {old: k for k, old in enumerate(order)}
    s = dict(skel)
    s['names'] = [skel['names'][i] for i in order]
    s['parent'] = [-1 if skel['parent'][i] < 0 else new[skel['parent'][i]] for i in order]
    s['opt'] = [_number(x) for x in s['names'][len(order) - len(skel['opt']):]]
    for key in ('t', 'r', 's'):
        s[key] = np.asarray(skel[key])[order].copy()
    raw = skel.get('names_raw')
    s['names_raw'] = [raw[i] for i in order] if raw is not None and len(raw) == len(order) else None
    return s


def renumber_model(model, order):
    """The model (nud.read / model.convert's dict) with its vertex bone indices and meshes' single binds of the new
    order, in place."""
    new = np.zeros(len(order), np.int64)
    new[np.asarray(order)] = np.arange(len(order))
    for mesh in model['meshes']:
        if 0 <= mesh.get('singlebind', -1) < len(order):
            mesh['singlebind'] = int(new[mesh['singlebind']])
        for p in mesh['polys']:
            if p['vtype'] & 0xF0:
                b = p['verts']['bones']
                p['verts']['bones'] = new[np.clip(b.astype(np.int64), 0, len(order) - 1)].astype(b.dtype)
    return model


def write(skel, model, log=print):
    """(skeleton, model) in the game's record order (see the notes)."""
    order = permutation(skel)
    if order is None:
        log('  bones: the OPT bones cannot take the game\'s record order (a parent after its child): left as they are')
        return skel, model
    moved = sum(1 for k, old in enumerate(order) if k != old)
    if not moved:
        return skel, model
    log('  bones: %d OPT bones put in the game\'s record order (by number)' % moved)
    return apply(skel, order), renumber_model(model, order)
