"""A Tekken 8 fighter's gauge HUD (Clive's Zantetsuken gauge): the pictures and animations of its widget, baked into the
pack's gauge/ for runtime/src/title/gauge.cpp (`style ring`). A definition opts in with GAUGE's hud8: where its widget is
and what its parts are called (HUD8_PICTURES, HUD8_LAYERS: the roles below); convert/gauge.py keeps its moves' tests and
costs.

What Tekken 8 draws (its widget's slots, blueprint and animations, read from the player's files as the import runs):
* the gauge is an arc under the life bar (an arc of a circle, its ends found in the mask picture), filled from its end
  by the screen's edge side (on the right side the arc is mirrored, the number not): over a dark back and a pink frame a
  grey-white layer that jumps to the value, over it the pink one that follows over 8 frames (at once when it falls);
* an arc shows one level: (value % one level) / one level, all of it at the last level;
* in its middle the level's number, level + 1 (at most 5);
* a level up (its animations, one for the last level) brings the number in from twice its size, circles spreading out
  and a flash; at the last level two pictures blink over the arc.
The overlay draws upright quads only, so the arc is cut in wedges (one for each step, each picture its wedge's box), and
the frames of an animation are written out as placed pictures.
"""
import math
import struct

import numpy as np

from . import gauge as G

STEPS = 50                      # wedges of an arc: a level of 50 moves its head one wedge a point
CANVAS = 1920 / 3840            # gauge.cpp places pictures on a 1920-wide screen, the widget's layout is 3840 wide
# where it is on the TV image (1280 x 720, the title's HUD at its full size), under the life bars at about 40% of their
# length from the outer end as in Tekken 8; right: mirrored about the bars' middle (their frames' ends: gauge.cpp)
PLACE = (288.8, 90.2)
BARS_MIDDLE = (83.6 + 1190.6) / 2
BLINK_FRAMES = 40               # the widget's M_UI_Blink at Speed 1.5: 1.5 blinks a second
FRAME_RATE = 60
FILL_GAIN, FILL_LIFT = 1.5, (0, 26, 0)      # (measured on Tekken 8's frames) its pink picture to what its material shows
FILL_EDGE = 0.15                # (by eye) how much of the edge light picture its body shows
ATLAS_WIDTH = 2048
OVERLAP = 0.6                   # how far a wedge reaches under the next one's start, in steps: no seam between them
HEAD_WIDTH = 2.5                # (by eye) the bright line at the fill's head, in the arc's texels
# (measured on Tekken 8's frames: 30 over a background of 85) the empty arc, over its picture's half alpha
EMPTY_COLOUR, EMPTY_ALPHA = (16, 16, 26), 0.55
FLASH_COLOUR = (1, .236, .554)  # (the widget's) the level-up flash
SOFTEN = 3                      # the pink picture's patterns held still (its material scrolls them): blurred this many texels


def over(under, top):
    """RGBA float images (0..1 alpha, colours 0..255, not premultiplied): top over under."""
    a = top[..., 3:] + under[..., 3:] * (1 - top[..., 3:])
    rgb = (top[..., :3] * top[..., 3:] + under[..., :3] * under[..., 3:] * (1 - top[..., 3:])) / np.maximum(a, 1e-4)
    return np.concatenate((rgb, a), axis=-1)


def rgba(image):
    """An (H, W, 4) uint8 picture as a float image."""
    out = np.asarray(image, np.float32).copy()
    out[..., 3] /= 255
    return out


def to_bytes(image):
    return np.clip(np.concatenate((image[..., :3], image[..., 3:] * 255), axis=-1) + 0.5, 0, 255).astype(np.uint8)


def arc_of(mask):
    """The arc in a mask picture (bright where it is): its coverage, its centre, and its ends' angles (degrees counter-
    clockwise from the right, y up): (the end it fills from, the end it fills to, going clockwise)."""
    cover = np.asarray(mask, np.float32)[..., 0] / 255
    h, w = cover.shape
    ys, xs = np.nonzero(cover > 0.5)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    angle = np.degrees(np.arctan2(cy - ys, xs - cx)) % 360
    seen = np.zeros(360, bool)
    seen[angle.astype(int)] = True
    # (the gap is the longest run without the mask; the arc starts where it ends, going counter-clockwise)
    gap = best = 0
    at = 0
    for k in range(720):
        if seen[k % 360]:
            gap = 0
        else:
            gap += 1
            if gap > best:
                best, at = gap, k
    first = (at + 1) % 360                      # the arc's first degree, counter-clockwise
    unwrapped = (angle - first) % 360
    low, high = first + float(unwrapped.min()), first + float(unwrapped.max())
    return cover, (cx, cy), high, low           # clockwise: from its high angle down to its low one


def progress(shape, centre, start, end):
    """Each texel's place along the arc: 0 at `start`, 1 at `end`, going clockwise (a little beyond them: outside 0..1)."""
    h, w = shape
    y, x = np.mgrid[0:h, 0:w]
    angle = np.degrees(np.arctan2(centre[1] - y, x - centre[0]))
    gap = (360 - (start - end)) / 2
    return (((start - angle + gap) % 360 - gap) / (start - end)).astype(np.float32)


def soften(rgb, radius):
    """An (H, W, 3) image blurred about `radius` texels (a box, twice)."""
    out = rgb
    for _ in range(2):
        for axis in (0, 1):
            out = sum(np.roll(out, k, axis) for k in range(-radius, radius + 1)) / (2 * radius + 1)
    return out


def pad_rgb(image):
    """The colours spread over its transparent texels, so that no filter or block of the atlas darkens an edge."""
    out = image.copy()
    solid = out[..., 3] > 0.02
    if not solid.any():
        return out
    out[~solid, :3] = out[solid, :3].mean(axis=0)
    return out


class Atlas:
    """Pictures on shelves, on the 4-texel blocks of BC3 (one picture's blocks hold nothing of another's)."""
    def __init__(self):
        self.items = []

    def add(self, image, box=None):
        """Adds a float image (or its part `box` = x0, y0, x1, y1); -> its item number."""
        x0, y0, x1, y1 = box or (0, 0, image.shape[1], image.shape[0])
        self.items.append((pad_rgb(image[y0:y1, x0:x1]), (x0, y0)))
        return len(self.items) - 1

    def build(self):
        """-> (the atlas, uint8), each item's (x, y) texel in it."""
        order = sorted(range(len(self.items)), key=lambda i: -self.items[i][0].shape[0])
        at, x, y, shelf = {}, 0, 0, 0
        for i in order:
            h, w = self.items[i][0].shape[:2]
            if x + w + 4 > ATLAS_WIDTH:
                x, y, shelf = 0, y + shelf + 4, 0
            at[i] = (x, y)
            x = (x + w + 7) & ~3
            shelf = max(shelf, h)
        height = 4
        while height < y + shelf + 4:
            height *= 2
        atlas = np.zeros((height, ATLAS_WIDTH, 4), np.uint8)
        for i, (x, y) in at.items():
            img = to_bytes(self.items[i][0])
            atlas[y:y + img.shape[0], x:x + img.shape[1]] = img
        return atlas, at


class Keys:
    """A channel's keys [(frame, value)], read between them as lines."""
    def __init__(self, keys):
        self.keys = sorted(keys) or [(0, 0)]

    def at(self, frame):
        k = self.keys
        if frame <= k[0][0]:
            return k[0][1]
        for (f0, v0), (f1, v1) in zip(k, k[1:]):
            if frame <= f1:
                return v0 + (v1 - v0) * (frame - f0) / max(f1 - f0, 1e-6)
        return k[-1][1]

    @property
    def end(self):
        return self.keys[-1][0]


def wedges(atlas, fill, t, steps=STEPS):
    """The arc's wedges of the float image `fill`, for its progress t: [(item, x0, y0, x1, y1)]."""
    out = []
    for k in range(steps):
        lo, hi = (k - OVERLAP) / steps if k else -1, (k + 1) / steps if k + 1 < steps else 2
        edge = np.clip((hi - t) * steps * 2.2 + 0.5, 0, 1)      # (its leading edge soft, a texel wide)
        keep = (t >= lo) & (edge > 0) & (fill[..., 3] > 0)
        ys, xs = np.nonzero(keep)
        if not len(xs):
            out.append(None)
            continue
        x0, y0, x1, y1 = max(xs.min() - 2, 0), max(ys.min() - 2, 0), xs.max() + 3, ys.max() + 3
        image = fill.copy()
        image[..., 3] *= edge * keep
        out.append((atlas.add(image, (x0, y0, x1, y1)), x0, y0, x1, y1))
    return out


def heads(atlas, cover, t, span, colour, width, steps=STEPS):
    """The line at the head of the fill (`width` texels about it), for each step 1 .. steps - 1 (a list from step 0:
    None). span: the arc's angle in radians."""
    out = [None]
    h, w = cover.shape
    radius = np.hypot(*np.mgrid[-(h - 1) / 2:(h + 1) / 2, -(w - 1) / 2:(w + 1) / 2])
    for k in range(1, steps):
        along = (t - k / steps) * span * radius           # (t is linear in the angle)
        image = np.zeros((h, w, 4), np.float32)
        image[..., :3] = colour
        image[..., 3] = cover * np.exp(-np.square(along / width))
        image[image[..., 3] < 0.02, 3] = 0
        ys, xs = np.nonzero(image[..., 3])
        x0, y0, x1, y1 = max(xs.min() - 2, 0), max(ys.min() - 2, 0), xs.max() + 3, ys.max() + 3
        out.append((atlas.add(image, (x0, y0, x1, y1)), x0, y0, x1, y1))
    return out


def bake(pictures, up, up_max, log=print):
    """gauge.nut's atlas and gauge.ini's lines. pictures: {role: (H, W, 4) uint8 array} of the widget (HUD8_PICTURES);
    up, up_max: {role: (alpha Keys, scale Keys)} of its level-up animations (HUD8_LAYERS)."""
    size = pictures['mask'].shape[0]
    cover, centre, start, end = arc_of(pictures['mask'])
    t = progress(cover.shape, centre, start, end)
    atlas = Atlas()

    # the back: BG at the widget's half alpha, the empty arc, its frames over it
    back = rgba(pictures['back'])
    back[..., 3] *= 0.5
    empty = np.zeros_like(back)
    empty[..., :3] = EMPTY_COLOUR
    empty[..., 3] = cover * EMPTY_ALPHA
    back = over(over(over(back, empty), rgba(pictures['effect_frame'])), rgba(pictures['normal_frame']))
    # the pink layer: its picture brightened (its material's patterns and light, by eye), its edges' light, its frame
    pink = rgba(pictures['pink'])
    fill = np.zeros_like(pink)
    fill[..., :3] = soften(pink[..., :3], SOFTEN) * FILL_GAIN + np.array(FILL_LIFT, np.float32)
    fill[..., :3] += np.asarray(pictures['edge_light'], np.float32)[..., :3] * FILL_EDGE
    fill[..., 3] = cover
    fill = over(fill, rgba(pictures['frame']))
    fill[..., :3] = np.minimum(fill[..., :3], 255)
    # the white layer under it
    white = rgba(pictures['white'])
    white[..., :3] = np.minimum(white[..., :3] + np.asarray(pictures['white_add'], np.float32)[..., :3], 255)
    white[..., 3] = cover * np.maximum(white[..., 3], 0.5)

    base_item = atlas.add(back)
    fills = wedges(atlas, fill, t)
    whites = wedges(atlas, white, t)
    tips = heads(atlas, cover, t, math.radians(start - end), (255, 225, 245), HEAD_WIDTH)
    flash_item = atlas.add(rgba(pictures['flash']))
    circle_item = atlas.add(rgba(pictures['circle']))
    light_item = atlas.add(rgba(pictures['max_light']))
    glow_item = atlas.add(rgba(pictures['frame_effect']))
    # the numbers: cells of a row (cell 0 empty), the sheets of different sizes
    cell = pictures['num_edge'].shape[0]
    digits = {}
    for n in range(1, 6):
        row = {}
        for name, sheet in (('num', pictures['num']), ('edge', pictures['num_edge']), ('add', pictures['num_add'])):
            c = sheet.shape[0]
            img = rgba(sheet[0:c, n * c:(n + 1) * c])
            if c != cell:                       # (the big sheet: down to the cell's size, as its quads show it)
                k = c // cell
                premult = img.copy()
                premult[..., :3] *= premult[..., 3:]
                small = premult.reshape(cell, k, cell, k, 4).mean(axis=(1, 3))
                small[..., :3] /= np.maximum(small[..., 3:], 1e-4)
                img = small.astype(np.float32)
            row[name] = atlas.add(img)
        digits[n] = row
    built, placed = atlas.build()

    def picture(item, box=None, scale=1.0, mult='FFFFFFFF', add='000000', blend='00', side=0, cells=None):
        """gauge.ini's `q` line for an item: its box of the picture's texels, placed about the middle (0, 0)."""
        x, y = placed[item]
        h, w = atlas.items[item][0].shape[:2]
        wide = cells if cells is not None else size
        x0, y0, x1, y1 = box if box is not None else (0, 0, w, h)
        a = (x0 - wide / 2) * CANVAS * scale, (y0 - wide / 2) * CANVAS * scale
        b = (x1 - wide / 2) * CANVAS * scale, (y1 - wide / 2) * CANVAS * scale
        if side:                                # (mirrored)
            a, b = (-a[0], a[1]), (-b[0], b[1])
        return 'q %.2f %.2f %.2f %.2f %.2f %.2f %.2f %.2f %s %s%s' % (a[0], a[1], b[0], b[1], x, y, x + w, y + h,
                                                                       mult, add, blend)

    def alpha(mult_alpha, colour=(1, 1, 1)):
        return '%02X%02X%02X%02X' % (round(colour[0] * 255), round(colour[1] * 255), round(colour[2] * 255),
                                     round(max(0, min(1, mult_alpha)) * 255))

    lines = ['# made on this machine from the player\'s own Tekken 8',
             '# positions about the gauge\'s middle on a 1920 x 1080 screen; pictures by their texels in gauge.nut',
             'atlas %d %d' % (built.shape[1], built.shape[0]), 'style ring']
    num_cell = cell
    for s, side in enumerate('LR'):
        place = PLACE if not s else (2 * BARS_MIDDLE - PLACE[0], PLACE[1])
        lines.append('place %s %.2f %.2f' % (side, place[0], place[1]))
        def clip(name, frames):
            lines.append('clip %s %s %d' % (side, name, len(frames)))
            for k, rows in enumerate(frames):
                lines.append('frame %s %s %d' % (side, name, k))
                lines.extend(rows)
        clip('base', [[picture(base_item, side=s)]])
        for name, items in (('fill', fills), ('white', whites), ('head', tips)):
            clip(name, [[picture(i[0], i[1:], side=s)] if i else [] for i in items])
        # a level up's circles and flash, its last frame nothing
        for name, keys in (('up', up), ('upmax', up_max)):
            n = int(math.ceil(max(k.end for pair in keys.values() for k in pair if k is not None))) + 1
            frames = []
            for f in range(n):
                rows = []
                for layer, item, colour, blend in (
                        ('circle1', circle_item, (1, 1, 1), 'FF'), ('circle2', circle_item, (1, 1, 1), 'FF'),
                        ('flash', flash_item, FLASH_COLOUR, 'FF')):
                    a, sc = keys[layer]
                    v = a.at(f)
                    if v > 0.004:
                        rows.append(picture(item, scale=sc.at(f) if sc else 1, mult=alpha(v, colour), blend=blend, side=s))
                frames.append(rows)
            clip(name, frames + [[]])
        # the last level's blink (over BLINK_FRAMES, from dark)
        frames = []
        for f in range(BLINK_FRAMES):
            b = 0.5 - 0.5 * math.cos(2 * math.pi * f / BLINK_FRAMES)
            frames.append([picture(light_item, mult=alpha(b), blend='FF', side=s),
                           picture(glow_item, mult=alpha(0.7 * b), blend='FF', side=s)])
        clip('blink', frames)
        # the numbers: as they come in, the last frame at rest (not mirrored)
        for n, row in digits.items():
            keys = up_max if n == 5 else up
            count = int(math.ceil(max(k.end for lay in ('num', 'edge', 'add') for k in keys[lay] if k is not None))) + 1
            frames = []
            if n > 1:
                for f in range(count):
                    rows = []
                    for layer, item, blend in (('num', row['num'], '00'), ('edge', row['edge'], '00'), ('add', row['add'], 'FF')):
                        a, sc = keys[layer]
                        v = a.at(f)
                        if v > 0.004:
                            rows.append(picture(item, scale=sc.at(f) if sc else 1, mult=alpha(v), blend=blend, cells=num_cell))
                    frames.append(rows)
            frames.append([picture(row['num'], cells=num_cell), picture(row['edge'], cells=num_cell)])
            clip('digit%d' % n, frames)
    log('gauge HUD: %d pictures (%dx%d)' % (len(atlas.items), built.shape[1], built.shape[0]))
    return built, lines


# ------------------------------------------------------------------------------------------------ the widget
# The definition names them: hud8 = dict(folder=, picture='..%s', widget=, animations=(level up, last level's level up),
# pictures={role: name}, layers={role: name})
HUD8_PICTURES = ('mask', 'back', 'effect_frame', 'normal_frame', 'pink', 'edge_light', 'frame', 'white', 'white_add', 'flash',
                 'circle', 'max_light', 'frame_effect', 'num', 'num_edge', 'num_add')
HUD8_LAYERS = ('circle1', 'circle2', 'flash', 'num', 'edge', 'add')


def channels(data):
    """The float channels in a movie scene section's bytes: [[(frame at 60 a second, value)]] (each serialised as its
    times, 4 bytes each, then its values, 28 bytes each, both with their element size and count first)."""
    out, at = [], 0
    while at + 16 <= len(data):
        a, n = struct.unpack_from('<ii', data, at)
        if a == 4 and 1 <= n <= 256 and at + 16 + 32 * n <= len(data):
            b, m = struct.unpack_from('<ii', data, at + 8 + 4 * n)
            if b == 28 and m == n:
                times = struct.unpack_from('<%di' % n, data, at + 8)
                values = [struct.unpack_from('<f', data, at + 16 + 4 * n + 28 * k)[0] for k in range(n)]
                out.append([(t * FRAME_RATE / 60000, v) for t, v in zip(times, values)])
                at += 16 + 32 * n
                continue
        at += 1
    return out


def animation(package, name, layers, uprops):
    """{role: (alpha Keys, scale Keys)} of the widget's animation `name` (scale None: it has none); layers: {role: its
    widget's name}."""
    def path(export):
        return str(export.path() if callable(export.path) else export.path)

    def by_path(tail):
        return next((e for e in package.exports if path(e).endswith(tail.split(':')[-1])), None)

    scene = next(e for e in package.exports if e.class_name == 'MovieScene' and e.name == name)
    props, _ = uprops.read(package, scene)
    role_of = {widget: role for role, widget in layers.items()}
    out = {}
    for binding in props.get('ObjectBindings', []):
        alpha = scale = None
        for track in binding.get('Tracks', []):
            export = by_path(track)
            if export is None:
                continue
            for section in uprops.read(package, export)[0].get('Sections', []):
                part = by_path(section)
                found = channels(bytes(part.data() if callable(part.data) else part.data)) if part is not None else []
                if export.class_name == 'MovieSceneColorTrack' and found:
                    alpha = Keys(found[-1])
                elif export.class_name == 'MovieScene2DTransformTrack' and len(found) == 2:
                    scale = Keys(found[0])
        if alpha is not None and binding['BindingName'] in role_of:
            out[role_of[binding['BindingName']]] = (alpha, scale)
    for role in HUD8_LAYERS:
        out.setdefault(role, (Keys([]), None))
    return out


def hud_files(store, defn, log=print):
    """{pack file name: bytes}: gauge/gauge.nut and gauge/gauge.ini, or {} without hud8 in the definition's GAUGE."""
    from ..tekken8 import texture, uprops
    from ..ttt2 import nut
    hud = (G.of(defn) or {}).get('hud8')
    if not hud:
        return {}
    uprops.NATIVE.setdefault('DeprecateSlateVector2D', uprops._fields('<2f', ('X', 'Y')))
    uprops.NATIVE.setdefault('MovieSceneFrameRange', lambda r: dict(zip(('lo_type', 'lo', 'hi_type', 'hi'), (
        r.one('B', 1), r.one('i', 4), r.one('B', 1), r.one('i', 4)))))
    pictures = {role: np.asarray(texture.Texture2D(store, '%s/%s' % (hud['folder'], hud['picture'] % name)).decode())
                for role, name in hud['pictures'].items()}
    package = store.package('%s/%s' % (hud['folder'], hud['widget']))
    up, up_max = (animation(package, name, hud['layers'], uprops) for name in hud['animations'])
    built, lines = bake(pictures, up, up_max, log=log)
    tex = nut.make_texture(built, 0, fmt=2, mips=1)     # BC3, one level (the runtime decodes it: title/image.h)
    return {'gauge/gauge.nut': nut.write([tex]), 'gauge/gauge.ini': ('\n'.join(lines) + '\n').encode('utf-8')}
