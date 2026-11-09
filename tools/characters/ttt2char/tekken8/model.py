"""A Tekken 8 costume's skeletal meshes -> one skinned model in TTT2 space, the dict convert/model.py's
load_tekken7_model makes of a Tekken 7 costume (the TTT2 side of model.convert takes either).

* Each part (body, face, hair: the _msl meshes) is read with tekken8.mesh, its joints renamed with names.canonical
  (Tekken 7's names, a name of its own for every joint), the skeletons merged by name (model.merge_skeletons: the
  face mesh's joints first, as the definition's merge order says).
* Parts bound to another rig than the first part's are re-bound to it first (rebind): Azucena's body and hair
  extras are bound to a rig of her own proportions (hips 3 cm, head 4.3 cm higher, the control joints Top / Trans /
  Rot anywhere), her face and hair to the standard one; Tekken 8 skins each mesh over its own bind, but merged by
  name every disagreeing joint of the body became a copy the re-pose did not turn (her arms stayed in the A-pose
  on T-pose bones). The standard rig is the one her animations are retargeted from (anim.load_skeleton).
* The simulation proxies (the cloth solver's copies, mesh.SIM_MATERIALS) are left out, as the Tekken 7 loader
  leaves out a cloth's simulation copy.
* Coordinates as for Tekken 7 (same units and axes: centimetres, Z up, facing +Y, left +X): Y and Z swapped,
  centimetres -> millimetres by way of float32 metres; the swap is a reflection, so the bitangent sign flips and
  triangles turn round.
* The bind pose stays Tekken 8's: an A-pose (upper arms 45 degrees down, forearms 15 degrees forward, legs 6
  degrees out); skeleton.repose turns it into the donor's T-pose before skeleton.build. bones['follow'] tells it
  which joints turn with a limb other than their parent's (names.follow), as (merged bone, share) or None.
* Tekken 8 may draw the fighter in a "proportion pose" (PRB_CH_<code>_msl: Reina taller by 2.5-2.9 cm, her head
  1.071 times larger); whether the game applies it is not known, so it is not applied: the mesh as it is bound.

Written for this project from the files themselves (no third-party code).
"""
from types import SimpleNamespace

import numpy as np

from .. import InputError
from ..convert import model as convert_model
from ..tekken7 import mesh as t7mesh
from . import bake, material as t8material, mesh as t8mesh, names, staticmesh, zen


class WornItem:
    """A costume's static mesh worn rigidly on the head (Victor's glasses) with a skeletal mesh's interface, so that it
    is merged, decimated and drawn as one part of the costume. Tekken 8 models it in the body's axes about the joint
    (its offset slot's rotation only undoes the joint's own; Victor's lenses come 3 cm in front of his eyes, his temples
    reach his ears), so the joint's bind position and the slot's scale place it."""
    JOINT = 'Head'

    def __init__(self, store, path, scale=1.0, ref=None):
        self.mesh = staticmesh.StaticMesh(store, path)
        self.name = self.mesh.name
        self.scale = scale
        self.materials = [{'material': ref_, 'slot': None} for ref_ in self.mesh.materials]
        self.props = {}
        self.skeleton = dict(ref) if ref is not None else None
        n = len(self.mesh.positions)
        self.lods = [SimpleNamespace(num_vertices=n, sections=[
            SimpleNamespace(material_index=slot, cloth_mapping=0, cloth_asset=None, base_vertex=0, num_vertices=n)
            for slot, _ in self.mesh.triangles()])]

    def material_name(self, index):
        ref = self.materials[index]['material'] if 0 <= index < len(self.materials) else None
        return zen.short_name(ref) if ref else 'None'

    def geometry(self, lod_index=0):
        g = t7mesh.global_matrices(self.skeleton['pose'], self.skeleton['parents'])
        at = self.skeleton['names'].index(self.JOINT)
        sm = self.mesh
        n = len(sm.positions)
        joints = np.zeros((n, 1), np.int32)
        joints[:] = at
        return {'positions': (sm.positions * self.scale + g[at][:3, 3]).astype(np.float32),
                'normals': sm.normals.astype(np.float32), 'tangents': sm.tangents.astype(np.float32), 'uvs': sm.uvs,
                'joints': joints, 'weights': np.ones((n, 1), np.float32),
                'triangles': [t for _, t in sm.triangles()]}


def _weighted(geo):
    return set(np.unique(geo['joints'][geo['weights'] > 0]).tolist())


def _near(m):
    """A bind change too small to matter (convert/model.merge_skeletons's test: 0.05 cm, 1e-3)."""
    return np.abs(m[:3, 3]).max() < 0.05 and np.abs(m[:3, :3] - np.eye(3)).max() < 1e-3


def rebind(skel, geo, ref):
    """A part bound to another rig than ref (a skeleton dict: names, parents, pose) -> (its skeleton with ref's joint
    poses, its geometry moved with them: each vertex by its joints' changes of bind, blended by its weights; normals
    and tangents turned), or (skel, geo) as they are when every joint skinned agrees. A joint ref lacks (or under
    another parent) keeps its place under its parent."""
    g = t7mesh.global_matrices(skel['pose'], skel['parents'])
    rg = t7mesh.global_matrices(ref['pose'], ref['parents'])
    at = {nm.lower(): i for i, nm in enumerate(ref['names'])}
    new = np.empty_like(g)
    for i, nm in enumerate(skel['names']):
        p, j = skel['parents'][i], at.get(nm.lower())
        same_parent = j is not None and ((p < 0 and ref['parents'][j] < 0) or (
            p >= 0 and ref['parents'][j] >= 0 and ref['names'][ref['parents'][j]].lower() == skel['names'][p].lower()))
        new[i] = rg[j] if same_parent else (new[p] @ np.linalg.inv(g[p]) @ g[i] if p >= 0 else g[i])
    change = new @ np.linalg.inv(g)
    if all(_near(change[i]) for i in _weighted(geo)):
        return skel, geo
    w = geo['weights'].astype(np.float64)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-12)
    blend = np.einsum('vk,vkij->vij', w, change[geo['joints']])
    out = dict(geo)
    out['positions'] = (np.einsum('vij,vj->vi', blend[:, :3, :3], geo['positions'].astype(np.float64))
                        + blend[:, :3, 3]).astype(np.float32)

    def turned(d):
        t = np.einsum('vij,vj->vi', blend[:, :3, :3], d.astype(np.float64))
        return (t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)).astype(np.float32)
    out['normals'] = turned(geo['normals'][:, :3])
    out['tangents'] = np.concatenate([turned(geo['tangents'][:, :3]), geo['tangents'][:, 3:]], 1)
    pose = np.array([t7mesh.matrix_to_pose(np.linalg.inv(new[p]) @ new[i] if p >= 0 else new[i])
                     for i, p in enumerate(skel['parents'])], np.float32)
    return dict(skel, pose=pose), out


def section_uvs(materials, m, geo):
    """A mesh's texture coordinates (n, 2): UV0, but a section whose material lays its colour out along another set
    ('Use UV1 for BaseColor': Miary Zo's tail, a strip along its length in UV1, its UV0 the dissolve's layout) takes
    that set (bake.uv_set). materials: tekken8.material.Materials."""
    uv = geo['uvs'][:, 0].copy()
    for si, s in enumerate(m.lods[0].sections):
        ref = m.materials[s.material_index]['material'] if 0 <= s.material_index < len(m.materials) else None
        if not ref or geo['uvs'].shape[1] < 2:
            continue
        try:
            k = bake.uv_set(materials.effective(ref), 'BaseColor')
        except (KeyError, ValueError, InputError):       # (a material it cannot read: UV0, as before)
            continue
        if 0 < k < geo['uvs'].shape[1]:
            used = np.unique(geo['triangles'][si])
            uv[used] = geo['uvs'][used, k]
    return uv


def load_model(store, parts, merge_order, log=print, worn=None):
    """The costume's meshes as one skinned mesh in TTT2 space (model.load_tekken7_model's dict).
    store: tekken8.store.Store; parts: [(tag, skeletal mesh path)] in mesh order; merge_order: the tags in
    skeleton-merge order (the face's first: its joints own the face); worn: {tag: size} of the parts that are static
    meshes worn on the head (WornItem), after the others in parts. Returns {'bones': {'names', 'parents', 'world'
    (n, 4, 4) bind matrices, mm, 'follow'}, 'prims': [{'part', 'material', 'pos' (mm), 'nrm', 'tan', 'uv', 'joints'
    (n, 8), 'weights' (n, 8), 'tris'}] (prims share the vertex arrays), 'parts': {tag: {'names', 'parents', 'remap'
    (part bone -> merged bone), 'mesh' (its SkeletalMesh), 'first' (its first vertex in the streams), 'source_names'
    (Tekken 8's joint names)}}}."""
    cm = convert_model
    materials = t8material.Materials(store)
    loaded = []
    worn = worn or {}
    for tag, path in parts:
        if tag in worn:                          # (on the first part's rig, which is the costume's)
            m = WornItem(store, path, worn[tag], next(x[1] for x in loaded if x[0] == merge_order[0]).skeleton)
            loaded.append((tag, m, m.geometry(0), list(m.skeleton['names'])))
            continue
        m = t8mesh.SkeletalMesh(store, path)
        source = list(m.skeleton['names'])
        m.skeleton['names'] = [names.canonical(n) for n in source]
        geo = m.geometry(0)
        if geo['weights'].shape[1] > 8:
            raise ValueError('%s: %d skin influences (8 at most)' % (m.name, geo['weights'].shape[1]))
        loaded.append((tag, m, geo, source))
    # parts bound to another rig than the first's: re-bound to it (the meshes keep their own skeletons: cloth.py
    # moves their vertices by the merged bind over the mesh's own)
    rigs, ref = {}, None
    for tag, m, geo, source in sorted(loaded, key=lambda x: merge_order.index(x[0])):
        if ref is None:
            ref = m.skeleton
            continue
        rig, rebound = rebind(m.skeleton, geo, ref)
        if rebound is not geo:
            log('  %s: bound to another rig than %s\'s: re-bound to it (vertices moved %.1f cm at most)' % (
                tag, merge_order[0], float(np.abs(rebound['positions'] - geo['positions']).max())))
            rigs[tag] = SimpleNamespace(skeleton=rig)
            loaded[[x[0] for x in loaded].index(tag)] = (tag, m, rebound, source)
    by_tag = {tag: (m, geo) for tag, m, geo, _ in loaded}
    merged, remaps = cm.merge_skeletons([(t, rigs.get(t, by_tag[t][0]), _weighted(by_tag[t][1]))
                                         for t in merge_order])
    pos, nrm, tan, uvs, jnt, wts, sections = [], [], [], [], [], [], []
    base, first, left_out, unknown = 0, {}, [], {}
    for tag, m, geo, source in loaded:
        n = len(geo['positions'])
        first[tag] = base
        pos.append(geo['positions'])
        nrm.append(geo['normals'])
        tan.append(geo['tangents'])
        uvs.append(section_uvs(materials, m, geo))
        j, w = remaps[tag][geo['joints']], geo['weights']
        if w.shape[1] < 8:
            pad = 8 - w.shape[1]
            j = np.concatenate([j, np.zeros((n, pad), j.dtype)], 1)
            w = np.concatenate([w, np.zeros((n, pad), w.dtype)], 1)
        jnt.append(j)
        wts.append(w)
        for si, s in enumerate(m.lods[0].sections):
            if s.cloth_mapping:                  # a simulation proxy
                left_out.append('%s %s (%d vertices)' % (tag, m.material_name(s.material_index), s.num_vertices))
                continue
            sections.append((tag, m.material_name(s.material_index), geo['triangles'][si] + base))
        share = np.zeros(len(source))
        np.add.at(share, geo['joints'].reshape(-1), geo['weights'].reshape(-1))
        for i in np.nonzero(share)[0]:
            if names.target(source[i]) is None:
                unknown[source[i]] = unknown.get(source[i], 0.0) + float(share[i])
        base += n
    if left_out:
        log('  Tekken 8 simulation proxies left out: %s' % ', '.join(left_out))
    if unknown:
        log('  Tekken 8 joints without a role (their weights go to their parent\'s bone): %s' % ', '.join(
            '%s %.0f' % (k, v) for k, v in sorted(unknown.items(), key=lambda x: -x[1])))
    p = cm._ue_to_ttt2_points(np.concatenate(pos)).astype(np.float64) * cm.M_TO_MM
    nr = cm._ue_to_ttt2_dirs(np.concatenate(nrm)).astype(np.float32).astype(np.float64)
    tg = np.concatenate(tan).astype(np.float32).copy()
    tg[:, :3] = cm._ue_to_ttt2_dirs(tg[:, :3])
    tg[:, 3] = -tg[:, 3]                         # the axis swap is a reflection: the bitangent sign flips
    uv = np.concatenate(uvs).astype(np.float32).astype(np.float64)
    weights = np.concatenate(wts).astype(np.float32)
    weights = weights / np.maximum(weights.sum(1, keepdims=True), 1e-8)
    joints = np.where(weights > 0, np.concatenate(jnt), 0).astype(np.uint16).astype(np.int64)
    streams = dict(pos=p, nrm=nr, tan=tg.astype(np.float64), uv=uv, joints=joints, weights=weights.astype(np.float64))
    prims = [dict(part=tag, material=mat, tris=tri.astype(np.uint32)[:, [0, 2, 1]].astype(np.int64), **streams)
             for tag, mat, tri in sections]
    g = t7mesh.global_matrices(merged['pose'], merged['parents'])
    ibm = np.linalg.inv(cm._ue_to_ttt2_matrix(g)).astype(np.float32)
    world = np.linalg.inv(ibm.astype(np.float64))
    world[:, :3, 3] *= cm.M_TO_MM
    # which merged bone each joint turns with in the re-pose (names.follow), in the part that has the joint
    follow = [None] * len(merged['names'])
    for tag, m, _, source in loaded:
        index = {nm: i for i, nm in enumerate(source)}
        for i, nm in enumerate(source):
            f = names.follow(nm)
            if f is not None and f[0] in index and follow[remaps[tag][i]] is None:
                follow[remaps[tag][i]] = (int(remaps[tag][index[f[0]]]), float(f[1]))
    skeletons = {tag: dict(names=m.skeleton['names'], parents=m.skeleton['parents'], remap=remaps[tag], mesh=m,
                           first=first[tag], source_names=source)
                 for tag, m, _, source in loaded}
    return {'bones': dict(names=merged['names'], parents=merged['parents'], world=world, follow=follow),
            'prims': prims, 'parts': skeletons}
