"""Tekken 7 2D fighters' gauges (Akuma's Super Combo gauge, Eliza's): the moveset's checks and costs kept, on ids the
runtime handles (runtime/src/title/gauge.cpp), and the HUD Tekken 7 draws for it (its pictures and animations baked
from its HUD movie into the pack's gauge/).

A definition opts in with GAUGE = dict(max, stock, gain=(blocked: the defender's, the attacker's; hit: the defender's,
the attacker's) in percent of the damage, hud=the HUD movie's object path). Facts (Tekken 7's executable):
* requirement 629: the gauge (player +0xcc8) >= param, 635: < param; property 0x81c2 adds its value (signed) and clamps
  it to 0 .. its most (+0xccc);
* property 0x8228 (value 1): the move gains no gauge for its attacks (+0x6b4, read by the gains); 0x8229: the fighter
  lights up (an EX move, a Focus cancel);
* the gains (0x140713f72): Akuma 37 / 75 / 112 / 225, Geese 21 / 85 / 63 / 255, everyone else 50 / 100 / 150 / 300;
* Geese's MAX mode: 176 tests its timer (+0xcd8) running, 0x82a9 adds frames to it (at most 720); no gains meanwhile;
* a super's start slows everything but its fighter down to a stop: 0x828c (slow motion: its value's low 16 bits the
  frames) with 0x828d 1 (the attacker immune), Double Reppuken 70 frames from its 8th, its hit at the 80th;
* as a gain or 0x81c2 takes the gauge from below its most to its most, the game posts event 0x26 (0x14073d980), whose
  listener (0x1402d1db0) plays the common sound SE_battle_spgauge_full for Akuma and Eliza only (character ids 32 and
  36); no move plays it, and a single stock has none. A definition names it as GAUGE full_sound (the runtime plays it
  as an item sound: the gauge line's last field).
"""
# the runtime's requirements: ids no TTT2 moveset uses that TTT2's requirement function takes as false, below 643 (TTT2
# marks cancel rows testing 643 and above as special ones, never tested for a player: sub_040D2300)
AT_LEAST, BELOW, MAX_ON = 190, 191, 192
ADD, NO_GAIN, FLASH = 0x8220, 0x8222, 0x8223  # the runtime's properties (TTT2's interpreter passes over them)
MAX_ADD = 0x8224
STOP = 0x8225                                 # the opponent stops for value frames (title/gauge.cpp)
# A Tekken 7 projectile hits a fighter once (Raging Storm's, allowed 10, deals its 43 once; Eliza's qcf+1+2 is two
# projectiles of one hit each); one that hits more turns into the next on its hit (a cancel row testing 784 with
# option 0x40: Double Reppuken 11 -> 12 -> 13 -> 14 -> 15, five hits of 13). TTT2's projectile deals its hits on
# the frames it touches the opponent, so it is given the chain's length (the hits come faster than Tekken 7's waves).
PROJECTILE_HIT = {'t7': 784, 't8': None}
SLOW_MOTION = {'t7': 0x828c, 't8': None}
SLOW_MOTION_IMMUNE = {'t7': 0x828d, 't8': None}
# Geese's MAX mode (Tekken 7: the timer at player +0xcd8): 176 tests it running, 0x82a9 adds frames to it (activation
# 720, the MAX cancel dash 360; EX moves -160, his supers -720), capped at 720 (0x1434df508)
# Tekken 8's Clive: 738 the gauge (player +0x1c94) >= param, 739 < param; 0x8232 adds its value (convert/gauge8.py)
REQS = {'t7': {629: AT_LEAST, 635: BELOW, 176: MAX_ON}, 't8': {738: AT_LEAST, 739: BELOW}}
PROPS = {'t7': {0x81c2: ADD, 0x8228: NO_GAIN, 0x8229: FLASH, 0x82a9: MAX_ADD}, 't8': {0x8232: ADD}}


def stop_frames(rows, idv, v, game):
    """The frames a super's slow motion (property idv = v among the move's (frame, id, value, ...) rows) stops the
    opponent for, when its fighter is immune to it; else None."""
    if idv != SLOW_MOTION[game] or not v & 0xFFFF:
        return None
    if not any(r[1] == SLOW_MOTION_IMMUNE[game] and r[2] == 1 for r in rows):
        return None
    return v & 0xFFFF


def projectile_hits(k, pi, game, cancels, reqs):
    """The hits Tekken 7 projectile pi of moveset k deals a fighter: one, and one more for each projectile it turns
    into on a hit (cancels(k, i) / reqs(k, i): the id maps' readers)."""
    seen, n = {pi}, 1
    rows = k.tables['projectiles']
    while True:
        nxt = next((c['move_id'] for c in cancels(k, rows[pi]['cancel'])
                    if c['option'] & 0x40 and any(a == PROJECTILE_HIT[game] for a, _ in reqs(k, c['req']))), None)
        if nxt is None or not 0 < nxt < len(rows) or nxt in seen:
            return n
        seen.add(nxt)
        pi, n = nxt, n + 1


def of(defn):
    """The definition's gauge (a dict) or None."""
    return vars(defn).get('GAUGE')


def full_sound(defn):
    """The sound the definition's gauge plays as it fills up (its Tekken 7 event name), or None."""
    return (of(defn) or {}).get('full_sound')


def ini_line(defn, full_sound=None):
    """character.ini's `gauge` line (title/gauge.h), or None; full_sound: its item sound number (the runtime plays it
    as the gauge fills up). A gauge the definition turns off (its 'on' False) is written commented out under a line
    saying how to turn it on: the port reads no `gauge` line then, so the fighter has none (no HUD, no levels)."""
    g = of(defn)
    if not g:
        return None
    line = 'gauge = %d %d %d %d %d %d' % ((g['max'], g['stock']) + tuple(g.get('gain', (50, 100, 150, 300))))
    line += ' %d' % full_sound if full_sound is not None else ''
    if g.get('on', True):
        return line
    return ('# %s: off. To turn it on, delete the # at the start of the next line (put it back to turn it off)\n#%s'
            % (g.get('name', 'gauge'), line))


# ------------------------------------------------------------------------------------------------ the HUD
# Tekken 7's HUD movie for the gauge (SW_UI_HUD_Rage: Akuma's; _ELZ: Eliza's): EX_mc at the bottom of its 1920 x 1080
# screen holds a panel per side, EX_L_mc / EX_R_mc, each with these clips the game's HUD code plays by their labels
# (0x1404c1b90 moves each slot's Bar_mc: a slot of 154 pixels per stock). The gauge fills from the screen's edge: the
# first stock is the outer slot (ExGauge_L2_mc, R2), the second the one by EX / SUPER! (the user, who plays Tekken 7)
SIDES = (('L', 'EX_mc.EX_L_mc'), ('R', 'EX_mc.EX_R_mc'))
# (Eliza's has no text; her outer slot has a cover, EXGauge_cover_mc, placed twice in both panels)
CLIPS = (('base', 'EXBase_%s_mc'), ('slot0', 'ExGauge_%s2_mc'), ('slot1', 'ExGauge_%s1_mc'), ('cover', 'EXGauge_cover_mc'),
         ('text', 'EXText_%s_mc'), ('light', 'EXLight_%s_mc'), ('lightning', 'EXLightning_%s_mc'),
         ('focus', 'EXFocus_%s_mc'))
# each bar: (bar number, the clip it is in, its path in there, its mask's path); a bar moves along its mask's width
BARS = ((0, 'ExGauge_%s2_mc', 'Bar_mc', 'BarMask_mc'), (1, 'ExGauge_%s1_mc', 'Bar_mc', 'BarMask_mc'))
# Geese's (SW_UI_HUD_Rage_MRY, SwfHUDMRYGauge in Tekken 7, 0x1404c7520): a power bar showing the stock being filled
# (424 pixels a stock) with their count beside it (EXNum: Num_01_mc / Num_02_mc at frame n, Up / Down as it changes),
# ExGauge1_MAX and MAXIMUM when every stock is full, the MAX mode timer's bar with MAXMODE while it runs, POWER (an
# unnamed placement)
POWER_CLIPS = (('static', None), ('base1', 'EXBase1_%s_mc'), ('gauge1', 'ExGauge1_%s_mc'), ('max1', 'ExGauge1_MAX_%s_mc'),
               ('text1', 'ExText1_%s_mc'), ('base2', 'EXBase2_%s_mc'), ('gauge2', 'ExGauge2_%s_mc'),
               ('text2', 'ExText2_%s_mc'), ('focus', 'EXFocus_%s_mc')) + \
    tuple(('num%d' % n, 'EXNum_%s_mc') for n in range(6))
POWER_BARS = ((0, 'ExGauge1_%s_mc', 'BarEX1_mc', 'BarMask_mc'),
              (1, 'ExGauge2_%s_mc', 'BarEX2_%s_mc.BarEX2Body_mc', 'BarEX2_%s_mc.BarEX2Mask_mc'))
NUMBERS = ('Num_01_mc', 'Num_02_mc')
ATLAS_WIDTH = 2048
BIG = 512                       # pictures larger than this are kept at half their size (glows),
EFFECTS = {'light', 'lightning', 'focus'}       # as are those only these clips show (bats, flares: soft anyway)


def _movie(paks, path):
    from ..tekken7 import swf, uasset
    pkg = uasset.load(paks, path)
    data = bytes(pkg.data)
    at = data.find(b'GFX')
    if at < 0:
        raise ValueError('%s holds no GFX movie' % path)
    return swf.Movie(data[at:])


def _picture(paks, folder, name):
    from ..tekken7 import texture, uasset
    import numpy as np
    t = texture.Texture2D(uasset.load(paks, folder + '/' + name))
    return np.asarray(t.decode(), np.uint8)


def _hex(c):
    return '%02X%02X%02X%02X' % tuple(int(round(max(0.0, min(1.0, v)) * 255)) for v in c)


def hud_files(paks, defn, log=print):
    """{pack file name: bytes}: gauge/gauge.nut (the pictures the HUD shows, one image) and gauge/gauge.ini (where and
    how, frame by frame, as the movie plays its clips), for runtime/src/title/gauge.cpp."""
    import numpy as np
    from ..tekken7 import swf
    from ..ttt2 import nut
    g = of(defn)
    if not g or not g.get('hud'):
        return {}
    path = g['hud']
    folder = path.rsplit('/', 1)[0]
    movie = _movie(paks, path)
    lines, used, rotated = [], {}, 0
    images, clips_of = {}, {}

    def picture(pic):
        if pic.name not in images:
            img = _picture(paks, folder, pic.name)
            if max(img.shape[:2]) > BIG or clips_of.get(pic.name, set()) <= EFFECTS:
                h, w = img.shape[:2]
                img = img[:h - h % 2, :w - w % 2].reshape(h // 2, 2, w // 2, 2, 4).mean((1, 3)).astype(np.uint8)
            images[pic.name] = img
        return images[pic.name]

    def quad(pic, m, clip):
        """(x0, y0, x1, y1, u0, v0, u1, v1) of a picture placed by matrix m, clipped (u, v in the picture, 0 to 1), or
        None (rotated, or clipped away)."""
        if abs(m[1]) > 1e-3 or abs(m[2]) > 1e-3:
            return None
        x0, y0 = m[4], m[5]
        x1, y1 = x0 + m[0] * pic.width, y0 + m[3] * pic.height
        u0, v0, u1, v1 = 0.0, 0.0, 1.0, 1.0
        if clip is not None:
            lo_x, hi_x, lo_y, hi_y = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
            cx0, cy0, cx1, cy1 = max(lo_x, clip[0]), max(lo_y, clip[1]), min(hi_x, clip[2]), min(hi_y, clip[3])
            if cx0 >= cx1 or cy0 >= cy1:
                return None
            def t(a, lo, hi):
                return (a - lo) / (hi - lo)
            fx0, fx1 = (t(cx0, x0, x1), t(cx1, x0, x1)) if x1 > x0 else (t(cx1, x0, x1), t(cx0, x0, x1))
            fy0, fy1 = (t(cy0, y0, y1), t(cy1, y0, y1)) if y1 > y0 else (t(cy1, y0, y1), t(cy0, y0, y1))
            nx0, nx1 = (cx0, cx1) if x1 > x0 else (cx1, cx0)
            ny0, ny1 = (cy0, cy1) if y1 > y0 else (cy1, cy0)
            x0, x1, y0, y1, u0, u1, v0, v1 = nx0, nx1, ny0, ny1, fx0, fx1, fy0, fy1
        return x0, y0, x1, y1, u0, v0, u1, v1

    power = any(e['name'] == 'EXNum_L_mc' for e in movie.display(movie.find('EX_mc.EX_L_mc')[0], 0).values())
    clips, bars = (POWER_CLIPS, POWER_BARS) if power else (CLIPS, BARS)
    skips = tuple(inside.split('.')[-1] for _, _, inside, _ in bars)

    def child(sprite, matrix, path):
        """The (entry, matrix) a dotted instance path names inside a sprite at its first frame."""
        e = None
        for name in path.split('.'):
            e = next((x for x in movie.display(sprite, 0).values() if x['name'] == name), None)
            if e is None:
                return None, None
            matrix = swf.concat(matrix, e['matrix'])
            sprite = movie.characters[e['char']]
        return e, matrix

    out = [('style', 'power' if power else 'ex')]   # (kind, fields...) with pictures by name, in the atlas at the end
    for side, side_path in SIDES:
        side_sprite, side_matrix = movie.find(side_path)
        shown = movie.display(side_sprite, 0)
        for k, instance, inside, mask_path in bars:
            e = next((x for x in shown.values() if x['name'] == instance % side), None)
            if e is None:
                continue
            matrix = swf.concat(side_matrix, e['matrix'])
            sprite = movie.characters[e['char']]
            bar, bar_matrix = child(sprite, matrix, inside % side if '%s' in inside else inside)
            mask, mask_matrix = child(sprite, matrix, mask_path % side if '%s' in mask_path else mask_path)
            if bar is None or mask is None:
                raise ValueError('%s has no %s / %s' % (instance % side, inside, mask_path))
            rect = movie.bounds(movie.characters[mask['char']], mask_matrix)
            placed = [(pic, quad(pic, m, None)) for pic, m, cx, blend, _ in
                      movie.flatten(movie.characters[bar['char']], 0, bar_matrix)]
            placed = [(pic, q) for pic, q in placed if q]
            if placed:                              # the bar itself (the widest: Geese's bars carry a sheen too)
                pic, q = max(placed, key=lambda pq: abs(pq[1][2] - pq[1][0]))
                used[pic.name] = pic
                clips_of.setdefault(pic.name, set()).add('bar')
                out.append(('bar', side, k, pic.name) + q)
            out.append(('mask', side, k) + rect + (1 if side == 'L' else -1,))
        for clip, instance in clips:
            name = instance % side if instance and '%s' in instance else instance
            entries = [shown[d] for d in sorted(shown) if shown[d]['name'] == name]   # (a clip placed again over itself)
            if not entries:
                continue
            fixed = {n: int(clip[3:]) for n in NUMBERS} if clip.startswith('num') else None
            if instance is None:                    # the unnamed placements, as one still clip
                out.append(('clip', side, clip, 1))
                out.append(('frame', side, clip, 0))
                for e in entries:
                    ch = movie.characters[e['char']]
                    sub = movie.flatten(ch, 0, swf.concat(side_matrix, e['matrix']), e['cx'], e['blend']) \
                        if isinstance(ch, swf.Sprite) else \
                        [(ch, swf.concat(side_matrix, e['matrix']), e['cx'], e['blend'], None)]
                    for pic, m, cx, blend, cl in sub:
                        q = quad(pic, m, cl) if isinstance(pic, swf.Picture) else None
                        if q and cx[0][3] > 0:
                            used[pic.name] = pic
                            clips_of.setdefault(pic.name, set()).add(clip)
                            out.append(('q', pic.name) + q + (_hex(cx[0]), _hex(cx[1][:3] + (0,))[:6],
                                                              'FF' if blend == swf.BLEND_ADD else '00'))
                continue
            entry = entries[0]
            sprite = movie.characters[entry['char']]
            out.append(('clip', side, clip, len(sprite.frames)))
            for label, first in sorted(sprite.labels.items(), key=lambda x: x[1]):
                later = [f for f in sprite.labels.values() if f > first]
                out.append(('label', side, clip, label, first, (min(later) if later else len(sprite.frames)) - 1))
            for f in range(len(sprite.frames)):
                out.append(('frame', side, clip, f))
                placed = []
                for e in entries:
                    placed += movie.flatten(movie.characters[e['char']], f, swf.concat(side_matrix, e['matrix']),
                                            e['cx'], e['blend'], skip=skips, fixed=fixed)
                for pic, m, cx, blend, cl in placed:
                    q = quad(pic, m, cl)
                    if q is None:
                        rotated += abs(m[1]) > 1e-3 or abs(m[2]) > 1e-3
                        continue
                    (mr, mg, mb, ma), (ar, ag, ab, _) = cx
                    if ma <= 0:
                        continue
                    used[pic.name] = pic
                    clips_of.setdefault(pic.name, set()).add(clip)
                    out.append(('q', pic.name) + q + (_hex((mr, mg, mb, ma)), _hex((ar, ag, ab, 0))[:6],
                                                      'FF' if blend == swf.BLEND_ADD else '00'))
    # the atlas: the pictures shown, on shelves
    placed, x, y, shelf = {}, 0, 0, 0
    for name in sorted(used, key=lambda n: -picture(used[n]).shape[0]):
        img = picture(used[name])
        h, w = img.shape[:2]
        if x + w > ATLAS_WIDTH:
            x, y, shelf = 0, y + shelf + 2, 0
        placed[name] = (x, y, w, h)
        x, shelf = x + w + 2, max(shelf, h)
    height = 1
    while height < y + shelf:
        height *= 2
    atlas = np.zeros((height, ATLAS_WIDTH, 4), np.uint8)
    for name, (x, y, w, h) in placed.items():
        atlas[y:y + h, x:x + w] = picture(used[name])
    def uv(name, u0, v0, u1, v1):
        x, y, w, h = placed[name]
        return '%.2f %.2f %.2f %.2f' % (x + u0 * w, y + v0 * h, x + u1 * w, y + v1 * h)
    lines = ['# %s\'s gauge as Tekken 7 shows it (%s), made on this machine from the player\'s own copy' % (
        defn.NAME, path.rsplit('/', 1)[1]),
        '# positions on Tekken 7\'s 1920 x 1080 screen; pictures by their texels in gauge.nut',
        'atlas %d %d' % (ATLAS_WIDTH, height)]
    for o in out:
        if o[0] == 'style':
            lines.append('style %s' % o[1])
        elif o[0] == 'bar':
            _, side, k, name, x0, y0, x1, y1, u0, v0, u1, v1 = o
            lines.append('bar %s %d %.2f %.2f %.2f %.2f %s' % (side, k, x0, y0, x1, y1, uv(name, u0, v0, u1, v1)))
        elif o[0] == 'mask':
            lines.append('mask %s %d %.2f %.2f %.2f %.2f %d' % o[1:])
        elif o[0] == 'clip':
            lines.append('clip %s %s %d' % o[1:])
        elif o[0] == 'label':
            lines.append('label %s %s %s %d %d' % o[1:])
        elif o[0] == 'frame':
            lines.append('frame %s %s %d' % o[1:])
        else:
            _, name, x0, y0, x1, y1, u0, v0, u1, v1, mult, add, blend = o
            lines.append('q %.2f %.2f %.2f %.2f %s %s %s%s' % (x0, y0, x1, y1, uv(name, u0, v0, u1, v1), mult, add,
                                                               blend))
    # BC3, one level (the runtime decodes it: title/image.h)
    tex = nut.make_texture(atlas, 0, fmt=2, mips=1)
    log('gauge HUD: %d pictures (%dx%d), %d placements%s' % (
        len(placed), ATLAS_WIDTH, height, sum(1 for o in out if o[0] == 'q'),
        ', %d rotated ones left out' % rotated if rotated else ''))
    return {'gauge/gauge.nut': nut.write([tex]), 'gauge/gauge.ini': ('\n'.join(lines) + '\n').encode('utf-8')}
