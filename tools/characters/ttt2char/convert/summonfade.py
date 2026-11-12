"""How a Tekken 8 fighter's summoned objects appear and vanish (Miary Zo's staffs, tail and horn): the TTT2 side of
Tekken 8's fade (convert/summons8.py; runtime title/roster.cpp, weapons).

* Tekken 8 dissolves a summoned object in over the frames its show row gives (value3: 5 for most) and out again over
  its hide row's (10), a linear ramp of its material's Transition: the object fills from its middle, the part facing
  the camera, out to its silhouette, a cyan band at the edge, and a hidden one is drawn until its fade ends. TTT2's
  materials have no per-draw parameter, so the runtime scales the object instead: the summon / dismissal value
  carries the frames (summons8.fade_value: n | frames << 8; frames 0 or 1 at once, as every pack before), and a
  weapon with a RAMP (character.ini `weapons`' fifth field) has the axes of its bone's local that the ramp names scaled
  by the fade's share each frame. The hit points are made from the unscaled locals and a dismissed summon stops
  hitting at once, as before: only the drawing changes.
* ramps() picks each summoned weapon's ramp from its own vertices in its bone's frame: the axis they run along keeps
  its length and the two across it are scaled (a THICKNESS ramp: a staff grows from a line to its full width, as
  Tekken 8's fills from its middle); a mesh not centred on that axis shrinks to its bone's origin (RAMP_ALL). A weapon
  under another weapon of its summon (the tail's links, each under the one before) takes its parent's ramp with
  RAMP_UNDER: the runtime cancels the parent's scale in its local (S L S^-1), so each link thins about its own axis
  and the chain keeps its curve (scaled at its root alone, a curled tail would straighten as it thins).
* A summoned weapon with no mesh of its own but bones under it carrying one (Miary Zo's snakes: their skeleton hangs
  under a still weapon at her elbow) takes RAMP_ALL: the bones under it shrink to its origin with it, over the same
  frames (Tekken 8 fades the snakes with the same Transition ramp as the staffs and the tail).
* still_frame() gives a weapon no animation poses (the horn, rigid on her head) the frame of its own mesh (origin on
  its axis at its base, y along it), so that its ramp is a thickness ramp too (at the head joint's frame the horn
  sits 14-28 cm off every axis). Its vertices and points stay where they are: the bone is still.

Written for this project from the files themselves (no third-party code).
"""
import numpy as np

from ..ttt2 import bone, nud
from . import weapons as weapons_mod

RAMP_X, RAMP_Y, RAMP_Z = 1, 2, 4    # the local's rows (the bone's axes) the fade scales
RAMP_ALL = RAMP_X | RAMP_Y | RAMP_Z
RAMP_UNDER = 8                      # under a ramped weapon of the same summon: its scale cancelled (S L S^-1)
CENTRED = 0.25                      # a mesh whose centre lies farther off its axis than this share of its mean
                                    # radius is not centred on it: RAMP_ALL
MAIN_WEIGHT = 0.5                   # a vertex belongs to the bone carrying at least this share of it


def still_frame(points, parent_origin):
    """The bind frame (4x4, TTT2 space, mm; a rotation) of a still weapon from its mesh's vertices (n, 3): y along
    their principal axis, pointing away from its parent's origin (base -> tip), the origin on that axis at the
    vertices' end nearest the parent, x the model's x made square to y (else z)."""
    p = np.asarray(points, np.float64)
    c = p.mean(0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    y = vt[0]
    far = p[np.argmax(np.linalg.norm(p - np.asarray(parent_origin, np.float64), axis=1))]
    if (far - c) @ y < 0:
        y = -y
    ref = np.array([1.0, 0.0, 0.0]) if abs(y[0]) < 0.9 else np.array([0.0, 0.0, 1.0])
    x = ref - (ref @ y) * y
    x /= np.linalg.norm(x)
    z = np.cross(x, y)
    out = np.eye(4)
    out[:3, 0], out[:3, 1], out[:3, 2] = x, y, z
    out[:3, 3] = c + y * float(((p - c) @ y).min())
    return out


def part_points(k, tag, joints):
    """The positions (n, 3) of a model dict's (tekken8.model.load_model's) vertices of part `tag` skinned to any of
    `joints` (merged bone indices)."""
    s0 = k['prims'][0]
    tris = np.concatenate([p['tris'].reshape(-1) for p in k['prims'] if p['part'] == tag])
    used = np.unique(tris)
    mine = (np.isin(s0['joints'][used], joints) & (s0['weights'][used] > 0)).any(1)
    return np.asarray(s0['pos'][used[mine]], np.float64)


def mesh_ramp(local):
    """The ramp of a weapon from its vertices in its bone's frame (n, 3): its two axes across the one the vertices
    run along, or RAMP_ALL when they are not centred on that axis (or there are none)."""
    local = np.asarray(local, np.float64)
    if len(local) < 3:
        return RAMP_ALL
    along = int(np.argmax(local.max(0) - local.min(0)))
    cross = [a for a in range(3) if a != along]
    radius = float(np.sqrt((local[:, cross] ** 2).sum(1)).mean())
    off = float(np.linalg.norm(local[:, cross].mean(0)))
    if radius <= 0 or off > CENTRED * radius:
        return RAMP_ALL
    return sum(1 << a for a in cross)


def weapon_vertices(model, index):
    """The bind positions (n, 3) of a NUD model's vertices (nud.read) carried by bone `index` (its main weight), or
    by any of the bones a list `index` names."""
    bones = np.atleast_1d(np.asarray(index, np.int64))
    out = []
    for m in model['meshes']:
        for p in m['polys']:
            v = p['verts']
            if 'bones' not in v.dtype.names:
                continue
            main = np.argmax(v['w'], 1)
            sel = np.isin(v['bones'][np.arange(len(v)), main], bones) & (v['w'].max(1) >= MAIN_WEIGHT)
            out.append(np.asarray(v['pos'][sel][:, :3], np.float64))
    return np.concatenate(out) if out else np.zeros((0, 3))


def bones_under(skel, index, stop=()):
    """The bones under bone `index` (its descendants, sorted), neither taking the bones in `stop` (other weapons:
    they fade by their own ramps) nor going below them."""
    children = {}
    for b, up in enumerate(skel['parent']):
        children.setdefault(up, []).append(b)
    out, todo = [], list(children.get(index, ()))
    while todo:
        b = todo.pop()
        if b in stop:
            continue
        out.append(b)
        todo.extend(children.get(b, ()))
    return sorted(out)


def ramps(skel, model, ini_weapons):
    """character.ini weapons (weapons.of_skeleton's [(k, parent, points, summon)]) with their ramps:
    [(k, parent, points, summon, ramp)] (ramp 0: none, the weapon drawn at full size while shown; a summon numbered
    summons8.ROOT_SUMMON or more is never shown). skel: the pack's skeleton (bone.read), model: its NUD (bytes, read
    only when a weapon is summoned, or nud.read's dict)."""
    from .summons8 import ROOT_SUMMON
    ini_weapons = list(ini_weapons)
    if not any(s is not None and 0 <= s < ROOT_SUMMON for _, _, _, s in ini_weapons):
        return [tuple(w) + (0,) for w in ini_weapons]
    if isinstance(model, (bytes, bytearray)):
        model = nud.read(model)
    numbers = weapons_mod._numbers(skel)
    world = bone.world_matrices(skel)
    weapon_bones = {i for n, i in numbers.items() if weapons_mod.OPT_FIRST <= n < weapons_mod.POINT_FIRST}
    by_index, out = {}, []
    for k, parent, points, summon in ini_weapons:
        index = numbers.get(weapons_mod.OPT_FIRST + k)
        ramp = 0
        if index is not None and summon is not None and 0 <= summon < ROOT_SUMMON:
            up = skel['parent'][index]
            if up in by_index and by_index[up][0] == summon and by_index[up][1]:
                ramp = (by_index[up][1] & RAMP_ALL) | RAMP_UNDER
            else:
                pos = weapon_vertices(model, index)
                if len(pos):
                    inv = np.linalg.inv(world[index])
                    ramp = mesh_ramp(pos @ inv[:3, :3].T + inv[:3, 3])
                elif len(weapon_vertices(model, bones_under(skel, index, weapon_bones))):
                    ramp = RAMP_ALL     # (no mesh of its own, bones under it carrying one: the snakes)
            by_index[index] = (summon, ramp)
        out.append((k, parent, points, summon, ramp))
    return out
