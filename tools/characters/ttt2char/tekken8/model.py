"""A Tekken 8 costume's skeletal meshes -> one skinned model in TTT2 space, the dict convert/model.py's
load_tekken7_model makes of a Tekken 7 costume (the TTT2 side of model.convert takes either).

* Each part (body, face, hair: the _msl meshes) is read with tekken8.mesh, its joints renamed with names.canonical
  (Tekken 7's names, a name of its own for every joint), the skeletons merged by name (model.merge_skeletons: the
  face mesh's joints first, as the definition's merge order says).
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
import numpy as np

from ..convert import model as convert_model
from ..tekken7 import mesh as t7mesh
from . import mesh as t8mesh, names


def _weighted(geo):
    return set(np.unique(geo['joints'][geo['weights'] > 0]).tolist())


def load_model(store, parts, merge_order, log=print):
    """The costume's meshes as one skinned mesh in TTT2 space (model.load_tekken7_model's dict).
    store: tekken8.store.Store; parts: [(tag, skeletal mesh path)] in mesh order; merge_order: the tags in
    skeleton-merge order (the face's first: its joints own the face). Returns {'bones': {'names', 'parents', 'world'
    (n, 4, 4) bind matrices, mm, 'follow'}, 'prims': [{'part', 'material', 'pos' (mm), 'nrm', 'tan', 'uv', 'joints'
    (n, 8), 'weights' (n, 8), 'tris'}] (prims share the vertex arrays), 'parts': {tag: {'names', 'parents', 'remap'
    (part bone -> merged bone), 'mesh' (its SkeletalMesh), 'first' (its first vertex in the streams), 'source_names'
    (Tekken 8's joint names)}}}."""
    cm = convert_model
    loaded = []
    for tag, path in parts:
        m = t8mesh.SkeletalMesh(store, path)
        source = list(m.skeleton['names'])
        m.skeleton['names'] = [names.canonical(n) for n in source]
        geo = m.geometry(0)
        if geo['weights'].shape[1] > 8:
            raise ValueError('%s: %d skin influences (8 at most)' % (m.name, geo['weights'].shape[1]))
        loaded.append((tag, m, geo, source))
    by_tag = {tag: (m, geo) for tag, m, geo, _ in loaded}
    merged, remaps = cm.merge_skeletons([(t, by_tag[t][0], _weighted(by_tag[t][1])) for t in merge_order])
    pos, nrm, tan, uvs, jnt, wts, sections = [], [], [], [], [], [], []
    base, first, left_out, unknown = 0, {}, [], {}
    for tag, m, geo, source in loaded:
        n = len(geo['positions'])
        first[tag] = base
        pos.append(geo['positions'])
        nrm.append(geo['normals'])
        tan.append(geo['tangents'])
        uvs.append(geo['uvs'][:, 0])
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
