"""The added fighters' pictures and names on TTT2's 2D screens, made from their Tekken 7 or Tekken 8 UI pictures.

TTT2 shows a fighter's pictures in three ways, all by its UI position (its row in tables of 59):
* labels of sprites in the 2D layouts (LMB, data007): a per-fighter sprite has one label per fighter
  (`chara_face_yoko_jun`) whose frame shows that fighter's shape. Every layout with such sprites gets a label with
  the added fighter's code beside Paul's (`chara_face_yoko_kzm`), showing a picture of it made for that place;
  the select grids get its cell. The port (runtime/src/title/roster.cpp, "art") gives the added fighter Paul's UI
  position and puts its label names in Paul's place while the game shows it.
* the big portraits (356x612, frame and all): container 6ccdfc60 (data003) for the select screen, two per UI
  position (player 1 red, player 2 blue, mirrored), gets the added fighter's two after the 118; the loading and VS
  screens load the same pictures as single textures by keys from tables, for which the pack has its own
  (`art/portrait_*.nut`, also the other frame kinds).
* (in fights) textures of a NUT by id: not done here yet.

Each picture is made the same way: the pictures every fighter has at that place give the frame (pixels all of
them share), the background (their darkest, most transparent pixels) and the area a picture covers; the fighter's
own picture is scaled and placed so that its face sits where faces sit in that kind of picture, cut to that
area, laid over the background, under the frame. In the big portraits it also fades into the dark background
towards the frame, as every fighter there does (edge_fade).

What every added fighter shares (layouts, the big portraits' container, the HUD's pictures) is made for all of them
together, in the order of their places (shared_files, for shared/): layouts and the container whole
(`keys/<key>.bin`); the new texture pages go into `keys/<container key>.add`, which the port appends to the title's
container. What is a fighter's own (the loading and VS screens' portraits, the costume chooser's picture) goes into
its pack (pack_files).

The fighter's own pictures come from its game through a picture source: anything with picture(path) -> (H, W, 4)
uint8 and `game` ('tekken7', 'tekken8'; source.py's sources), or Tekken 7's paks as such (Tekken7Pictures). Its
definition's ART names them: a bust (head and shoulders), its whole body, its name and its costume, with where the
face is in the first two. Some kinds have a glow around the fighter that TTT2's pictures do not have, taken off
(GLOWS): Tekken 7's whole-body pictures a pale one, Tekken 8's busts a pink rim light. Tekken 8's busts are also
cooler and pinker than its whole-body pictures, whose colours the big portraits show: theirs are warmed (GRADES).
They also show more of the fighter below the face than TTT2's pictures do: the pictures cut from them show the face
bigger (BUST_FRAME). Tekken 7's costume picture is a render on a grey panel, Tekken 8's one on a transparent
background (cut_out takes either).

Nothing of either game is in this file: it reads the player's files.
"""
import re
import struct

import numpy as np
from PIL import Image, ImageFilter

from ..tekken7.texture import Texture2D
from ..tekken7.uasset import load
from ..pack import place
from ..ttt2 import lmb, nut
from ..ttt2.archive import key_of
from .model import linear_to_srgb, srgb_to_linear

PAUL = 'pau'                      # UI position 0: the runtime shows the added fighter in Paul's place
LAYOUTS = 'data007'               # the 2D layouts (LMB), each followed by its texture container (NTP3)
# The select grids' new cells (roster.cpp kCells, pack.place): at a fighter's panel (`anchor`) moved some columns
# over (the columns' pitch: between the panels of PITCH_FROM), in the top row (with its card frame where
# GRID_BESIDE's panel has its: the top row's panels draw their card at their place, the other rows' 6 higher), a row
# above it (the rows' pitch: between the panels of ROW_PITCH_FROM, the cursor's 65, sub_06F4D7B8) or the anchor's own
# row; drawn in the rows' order (each row over the one above it, as the title's are).
GRID_BESIDE = 'vio'
PITCH_FROM = ('rog', 'rav')       # grid row 1, columns 0 and 1
ROW_PITCH_FROM = ('rog', 'mok')   # column 0, grid rows 1 and 2
# The select grid with a new top row (when a fighter's place is past pack.CELLS): grid row -1 for added fighters where
# the title's top row is, under the team bars (its empty cells show the background); the title's three rows move down
# a row into the space under the grid (ROWS_DOWN; roster.cpp kRowsCursorRow: the cursor's row 1 follows them), and
# what is under the grid with them; the '?' panel is stretched down over the four rows; the banner under the grid is
# left out (the button guide moves down where it was: roster.cpp kRowsGuideDown). The grid's top line, the portraits,
# team bars and dialogs stay. Layout units: 720p pixels, y down.
# Only the select's frames change (the stage select uses the same sprite from STAGE_LABEL on).
ROWS_DOWN = 65
STAGE_LABEL, OUT_LABEL = 'stage_in', 'face_all_out'     # (the select rests at OUT_LABEL; the faces go out after it,
                                                        # the stage cards come in)
GRID_LINE = re.compile(r'^face_waku_up_line')
RANDOM_PANEL = re.compile(r'^(sentaku_)?random_face_panel')
LEFT_OUT = ('choose_your_character_moji',)
UNDER_LINE = ('face_waku_under_line',)
SPACERS = ('spacer_left', 'spacer_right')
# Labels whose pictures the game puts in itself (the big portraits' frames): copied, not drawn; they end on
# the fighter's name, which is drawn.
GAME_DRAWN = re.compile(r'^p[12]_chara_waku_$')
PORTRAITS = 0x6CCDFC60            # the big portraits' container (data003): count, {offset, size}, NTP3s
PORTRAIT_SIZE = (356, 612)
# The loading and VS screens' portraits: key tables of the title (roster.cpp kKeyTables): the pack's file for
# each, and the fighter's pictures of that kind in Paul's row of the table (UI position 0) to make it like.
PORTRAIT_FILES = [('art/portrait_1p.nut', 0x10529004, False), ('art/portrait_2p.nut', 0x10529008, True),
                  ('art/portrait_mono.nut', 0x105291DC, False), ('art/portrait_green.nut', 0x105293B4, False),
                  ('art/portrait_green2.nut', 0x1052958C, False)]
# The fights' HUD: its texture container (data003) has per UI position a name (40 pixels tall) and two faces (140 x
# 140, player 1's and player 2's, mirrored), at numbers from a table of the title (roster.cpp kHudPaul: Paul's
# 30, 105, 164; the faces are 59 apart). The fighter's three go after the container's own, in that order.
HUD = 0x7C476BDE
HUD_PAUL = (30, 105, 164)
# The select screen's costume chooser: per select id a texture container of costume pictures (124 x 304, one per
# costume; their keys in a table of the title by select id). The fighter has one costume; its picture is made from
# its game's costume picture (Tekken 7's costume slot: a full-body render on a grey panel between white margins;
# Tekken 8's: on a transparent background): the fighter cut out and stood in the room the title's pictures share,
# with its reflection on the floor. roster.cpp kCostumeFile.
COSTUME_PREVIEWS = 0x10161590
COSTUME_FILE = 'art/costumes.nut'
SELECT_IDS = 59
COSTUME_TOP, COSTUME_HEIGHT = 0.04, 0.84       # where the fighter's head is and how tall it stands (of the picture)
PAGE_WIDTH = 1024                 # new texture pages: at most this wide, as tall as needed
UI_ROWS = 59                      # UI positions (rows of the title's tables)

# Where a face sits in each kind of picture: (eyes' centre x, y as fractions of the picture, eyes-to-chin as a
# fraction of its height, which of the fighter's pictures: 'bust' or 'body'). Measured on the TTT2 pictures.
FACE_TALL = (0.52, 0.40, 0.21, 'bust')          # 56x88, 100x136: head and shoulders
FACE_SQUARE = (0.40, 0.38, 0.20, 'bust')        # 140x140
FACE_STRIP = (0.46, 0.42, 0.36, 'bust')         # 160x56: eyes and mouth, faded at the sides
FACE_BAR = (0.15, 0.40, 0.36, 'bust')           # 120x40 .. 200x48: a face at the left end of a bar
FACE_BANNER = (0.56, 0.43, 0.29, 'bust')        # 548x140
FACE_BODY = (0.45, 0.13, 0.08, 'body')          # 460x480: the whole fighter
FACE_PORTRAIT = (0.47, 0.17, 0.105, 'body')     # 356x612: down to the hips
FACE_HUD = (0.50, 0.42, 0.24, 'bust')           # 140x140 in fights: head and shoulders


def face_place(w, h):
    a = w / h
    if w >= 300 and h >= 300:
        return FACE_BODY if a > 0.75 else FACE_PORTRAIT
    if a >= 3.2 and h >= 100:
        return FACE_BANNER
    if a >= 2.4:
        return FACE_STRIP if a < 3.0 and h >= 50 else FACE_BAR
    if a >= 0.85:
        return FACE_SQUARE
    return FACE_TALL


# ------------------------------------------------------------------------------------------------ pictures

def _float(img):
    return np.asarray(img, np.float32) / 255.0


def _uint8(a):
    return np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)


def _premultiplied(a):
    out = a.copy()
    out[..., :3] *= out[..., 3:4]
    return out


def _straight(p):
    out = p.copy()
    alpha = out[..., 3:4]
    out[..., :3] = np.where(alpha > 1e-4, out[..., :3] / np.maximum(alpha, 1e-4), 0.0)
    return out


def _resize(a, w, h):
    """An RGBA float picture resized (premultiplied, so edges do not darken or bleed)."""
    p = _premultiplied(a)
    chans = [np.asarray(Image.fromarray(p[..., c]).resize((w, h), Image.LANCZOS)) for c in range(4)]
    return _straight(np.clip(np.stack(chans, -1), 0.0, 1.0))


class Tekken7Pictures:
    """Tekken 7's UI pictures by object path, from its paks (tekken7.pak.Paks): the picture source of the calls
    that pass the paks themselves."""

    game = 'tekken7'

    def __init__(self, paks):
        self.paks = paks

    def picture(self, path):
        return Texture2D(load(self.paks, path)).decode()


def picture_source(source):
    """`source` as a picture source: one (it has picture()), or Tekken 7's paks."""
    return source if hasattr(source, 'picture') else Tekken7Pictures(source)


def source_of(sources, slot, d):
    """Fighter d's picture source in shared_files' `source`: one source (or paks) for every fighter, a mapping
    {slot or d.CODE: source (or paks)}, or a function of the definition that gives it (source.Sources)."""
    if isinstance(sources, dict):
        return picture_source(sources[slot] if slot in sources else sources[d.CODE])
    if callable(sources) and not hasattr(sources, 'picture'):
        return picture_source(sources(d))
    return picture_source(sources)


class Sources:
    """The fighter's pictures (d.ART: from its game through `source`, see picture_source), as RGBA floats, with
    where its face is in each."""

    def __init__(self, source, d):
        source = picture_source(source)
        glows = GLOWS.get(getattr(source, 'game', None), {})
        grades = GRADES.get(getattr(source, 'game', None), {})
        zoom, drop = BUST_FRAME.get(getattr(source, 'game', None), (1.0, 0.0))
        self.pictures, self.faces = {}, {}
        for kind in ('bust', 'body'):
            path, face = d.ART[kind]
            img = _float(source.picture(path))
            if kind in glows:
                img = glows[kind](img)
            if kind in grades:
                img = grades[kind](img)
            if kind == 'bust' and (zoom, drop) != (1.0, 0.0):
                face = (face[0], face[1] - drop * face[2], face[2] / zoom)
            self.pictures[kind], self.faces[kind] = img, face
        if 'bust' in grades:                # (the bust's face as it is: its eyes-to-chin as BUST_FRAME takes it)
            ex, ey, ec = d.ART['bust'][1]
            self.pictures['bust'] = skin_matched(self.pictures['bust'], (ex, ey, ec / zoom), self.pictures['body'],
                                                 self.faces['body'])
        self.name = _float(source.picture(d.ART['name']))

    def framed(self, place, w, h, mirror=False):
        """The fighter's picture scaled and moved so that its face sits at `place` in a w x h picture."""
        fx, fy, chin, kind = place
        img = self.pictures[kind]
        ex, ey, ec = self.faces[kind]
        if mirror:
            img = img[:, ::-1]
            ex = img.shape[1] - ex
            fx = 1.0 - fx
        scale = chin * h / ec
        sw, sh = max(1, round(img.shape[1] * scale)), max(1, round(img.shape[0] * scale))
        scaled = _resize(img, sw, sh)
        out = np.zeros((h, w, 4), np.float32)
        x0, y0 = round(ex * scale - fx * w), round(ey * scale - fy * h)      # the picture's corner in `scaled`
        sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x0 + w, sw), min(y0 + h, sh)
        if sx1 > sx0 and sy1 > sy0:
            out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = scaled[sy0:sy1, sx0:sx1]
        return out

    def title_name(self, w, h):
        """The fighter's name for a w x h name picture of the title: in the title's own letters (see Letters) as
        wide as it needs, else its game's name picture fitted in w x h."""
        letters = getattr(self, 'letters', None)
        text = getattr(self, 'short_name', None)
        pic = letters.picture(text) if letters is not None and text else None
        if pic is None:
            return self.name_picture(w, h)
        if pic.shape[0] != h:
            pic = _resize(pic, max(1, round(pic.shape[1] * h / pic.shape[0])), h)
        return pic

    def name_picture(self, w, h, height=0.6):
        """The fighter's name (its game's name picture, cut to its letters) centred in a w x h picture, the
        letters `height` of it tall."""
        a = self.name
        ys, xs = np.nonzero(a[..., 3] > 0.05)
        if not len(xs):
            return np.zeros((h, w, 4), np.float32)
        a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        nh = max(1, round(h * height))
        nw = max(1, round(a.shape[1] * nh / a.shape[0]))
        if nw > w - 2:
            nw, nh = w - 2, max(1, round(a.shape[0] * (w - 2) / a.shape[1]))
        out = np.zeros((h, w, 4), np.float32)
        x0, y0 = (w - nw) // 2, (h - nh) // 2
        out[y0:y0 + nh, x0:x0 + nw] = _resize(a, nw, nh)
        return out


def deglow(img):
    """Tekken 7's select screen pictures have a soft white glow around the fighter; TTT2's have none: the glow's
    half-transparent pale pixels lose their alpha."""
    out = img.copy()
    alpha = out[..., 3]
    pale = out[..., :3].min(-1)
    glow = (alpha < 0.97) & (pale > 0.55)
    out[..., 3] = np.where(glow, np.clip((alpha - 0.6) / 0.4, 0.0, 1.0) * alpha, alpha)
    return out


# Tekken 8's busts (Makuai_Character_L) have a rim light around the fighter: a band of one colour (pink-red, about
# 240, 60, 100 on every fighter measured) fading out over ~100 pixels at alpha 0.15 and less (0.3 to 0.45 at most,
# where it meets the hair). Most of the faintest pixels are that colour; pixels near it that are half transparent
# lose their alpha, those a little different (the hair the light falls on) keep it.
RIM_FAINT = 0.1        # the faint pixels (alpha below this) whose commonest colour is the rim light's
RIM_SHARE = 0.25       # ... when at least this share of them have it (else the picture has no rim light)
RIM_BIN = 16           # colours are counted in steps of this (of 255)
RIM_NEAR, RIM_FAR = 0.06, 0.25           # colour distance (largest channel difference): all rim light .. none
RIM_SOLID = (0.35, 0.6)                  # alpha from which a pixel is taken less and less for rim light .. never


def deglow_rim(img):
    """A picture without its rim light (see RIM_FAINT): its colour found among the faintest pixels, the
    half-transparent pixels of that colour made transparent."""
    alpha = img[..., 3]
    faint = img[(alpha > 0.0) & (alpha < RIM_FAINT)][:, :3]
    if len(faint) < 64:
        return img
    q = np.minimum((faint * 255.0) // RIM_BIN, 255 // RIM_BIN).astype(np.int64)
    keys = (q[:, 0] * 256 + q[:, 1]) * 256 + q[:, 2]
    values, counts = np.unique(keys, return_counts=True)
    if counts.max() < RIM_SHARE * len(faint):
        return img
    key = values[counts.argmax()]
    colour = faint[keys == key].mean(0)
    distance = np.abs(img[..., :3] - colour).max(-1)
    near = np.clip((RIM_FAR - distance) / (RIM_FAR - RIM_NEAR), 0.0, 1.0)
    lo, hi = RIM_SOLID
    thin = 1.0 - np.clip((alpha - lo) / (hi - lo), 0.0, 1.0)
    out = img.copy()
    out[..., 3] = alpha * (1.0 - near * thin)
    return out


# Tekken 8's busts are graded cooler and pinker than its whole-body pictures (the arena's, whose colours the big
# portraits show): their greys have a blue cast (Victor's hair b* -6, his whole body's about 0) and their warm
# colours lean to magenta (the skin's hue about 20 degrees against the whole body's 47, b* 10 to 17 lower;
# Azucena's top and feathers pink and red, not red and orange; Miary Zo's hair red, not brown; all five fighters,
# 2026-11-10; Tekken 7's two pictures agree). Their colours taken back, in CIELAB (warmed): blue's share of the light
# (linear) times BUST_BLUE (the cast greys come out grey); warm hues turned towards yellow (BUST_TURN: by that many
# degrees at that hue, less and less to none that far from it; greys and other hues stay) where they are no
# stronger than skin (BUST_STRONG: all up to that chroma, less and less to none at the next: Azucena's top turns
# red, not orange); the colour (chroma) times BUST_CHROMA. Then each fighter's skin is taken the rest of the way to
# its whole body's (skin_matched): the warm hues turned and their chroma scaled until the skin's mean hue and chroma
# are the whole body's, within SKIN_TURN degrees and SKIN_CHROMA times, for colours about as strong as the skin only
# (SKIN_STRONG: all up to that many times its mean chroma, less and less to none at the next). Reina's and Azucena's
# skin is lit paler than in their whole bodies, Clive's richer; Victor's has too little colour to measure a hue by
# and stays about as warmed leaves it.
BUST_BLUE = 0.85
BUST_TURN = (20.0, 20.0, 70.0)            # (degrees turned, at hue, none from this far)
BUST_STRONG = (25.0, 45.0)
BUST_CHROMA = 1.2
SKIN_TURN, SKIN_CHROMA = 15.0, (0.8, 1.4)
SKIN_STRONG = (1.5, 2.5)
SKIN_BOX = (-0.55, -0.1, 0.55, 0.85)      # the skin measured: from the eyes, in eyes-to-chin lengths (x0, y0, x1, y1)
SKIN_PIXELS = 500                         # fewer opaque pixels there in either picture: no match
_XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
_WHITE = _XYZ.sum(1)              # D65
_EDGE = 6.0 / 29.0


def _lab(linear):
    """Linear RGB (..., 3) as CIELAB."""
    t = (linear @ _XYZ.T) / _WHITE
    f = np.where(t > _EDGE ** 3, np.cbrt(t), t / (3 * _EDGE ** 2) + 4.0 / 29.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _linear(lab):
    """CIELAB (..., 3) as linear RGB."""
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], -1)
    t = np.where(f > _EDGE, f ** 3, 3 * _EDGE ** 2 * (f - 4.0 / 29.0))
    return (t * _WHITE) @ np.linalg.inv(_XYZ).T


def _turned(lab, at, turn, gain, reach, strong=None):
    """CIELAB colours with the hues near `at` (degrees) turned by `turn` and their chroma times `gain`, less and
    less to none `reach` degrees from it; strong (c0, c1): only colours of chroma up to c0, less and less to none at
    c1."""
    hue = np.degrees(np.arctan2(lab[..., 2], lab[..., 1]))
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    off = (hue - at + 180.0) % 360.0 - 180.0
    near = np.where(np.abs(off) < reach, 0.5 + 0.5 * np.cos(np.pi * off / reach), 0.0)
    if strong is not None:
        near = near * np.clip((strong[1] - chroma) / (strong[1] - strong[0]), 0.0, 1.0)
    hue = np.radians(hue + turn * near)
    chroma = chroma * (1.0 + (gain - 1.0) * near)
    out = lab.copy()
    out[..., 1], out[..., 2] = chroma * np.cos(hue), chroma * np.sin(hue)
    return out


def warmed(img):
    """A Tekken 8 bust in the colours of Tekken 8's whole-body pictures (see BUST_BLUE)."""
    lab = _lab(srgb_to_linear(img[..., :3]) * np.array([1.0, 1.0, BUST_BLUE], np.float32))
    turn, at, reach = BUST_TURN
    lab = _turned(lab, at, turn, 1.0, reach, BUST_STRONG)
    lab[..., 1:] *= BUST_CHROMA
    out = img.copy()
    out[..., :3] = linear_to_srgb(_linear(lab))
    return out


def _skin(img, face):
    """CIELAB colours (n, 3) of img's opaque pixels in SKIN_BOX of the face at `face` (eyes' x, y, eyes-to-chin)."""
    ex, ey, ec = face
    x0, y0, x1, y1 = SKIN_BOX
    h, w = img.shape[:2]
    a = img[max(0, int(ey + y0 * ec)):min(h, int(ey + y1 * ec)), max(0, int(ex + x0 * ec)):min(w, int(ex + x1 * ec))]
    return _lab(srgb_to_linear(a[a[..., 3] > 0.98][:, :3]))


def _hue_chroma(lab):
    """The mean hue (degrees) and chroma of CIELAB colours (n, 3)."""
    a, b = lab[:, 1:].mean(0)
    return float(np.degrees(np.arctan2(b, a))), float(np.hypot(lab[:, 1], lab[:, 2]).mean())


def skin_matched(bust, bust_face, body, body_face):
    """The bust with its skin's warm hues and chroma taken to the whole body's (see SKIN_TURN); faces: (eyes' x, y,
    eyes-to-chin) in each."""
    mine, theirs = _skin(bust, bust_face), _skin(body, body_face)
    if len(mine) < SKIN_PIXELS or len(theirs) < SKIN_PIXELS:
        return bust
    reach = BUST_TURN[2]
    at, own = _hue_chroma(mine)
    strong = (own * SKIN_STRONG[0], own * SKIN_STRONG[1])
    hue, chroma = _hue_chroma(theirs)
    turn, gain = 0.0, 1.0
    for _ in range(6):                    # (the skin's hues spread round its mean: not all turn and scale fully)
        now = _hue_chroma(_turned(mine, at, turn, gain, reach, strong))
        turn = float(np.clip(turn + (hue - now[0] + 180.0) % 360.0 - 180.0, -SKIN_TURN, SKIN_TURN))
        gain = float(np.clip(gain * chroma / max(now[1], 1e-3), *SKIN_CHROMA))
    out = bust.copy()
    out[..., :3] = linear_to_srgb(_linear(_turned(_lab(srgb_to_linear(bust[..., :3])), at, turn, gain, reach,
                                                  strong)))
    return out


# The glows taken off each game's pictures, by kind, and the grades they are given after (a graded bust is then
# skin_matched to the whole body)
GLOWS = {'tekken7': {'body': deglow}, 'tekken8': {'bust': deglow_rim}}
GRADES = {'tekken8': {'bust': warmed}}
# How the pictures cut from each game's bust (its select screen cells, the faces in fights) frame the face against
# FACE_*'s measures: (how much bigger, how much lower in eyes-to-chin lengths of the bust). Tekken 8's busts show a
# front-facing head with much of the jacket below, and the definitions' eyes-to-chin (ART) ends on the neck, about
# 1.25 times the face's (all five, 2026-11-10): framed 1.25 times bigger, the face is as big as TTT2's and the
# shoulders show as in theirs (1.5 showed only the head, user 2026-11-10; 1.0 a small head, user 2026-10-26)
BUST_FRAME = {'tekken8': (1.25, 0.1)}


def compose(others, picture, fade=None):
    """A picture like `others` (N, h, w, 4 floats: every fighter's picture for the place) with `picture` (h, w, 4)
    in it: where all of them agree (a frame, a background they share) theirs, elsewhere `picture` cut to the area
    theirs cover, over their darkest and most transparent pixels; `fade` (h, w, see edge_fade): how much of
    `picture` shows at each pixel."""
    n = len(others)
    spread = others.std(0).max(-1)
    shared = spread < 0.04
    mean = others.mean(0)
    # the background: per pixel, the mean of the quarter of the pictures darkest there (transparent is darkest)
    weight = others[..., 3] * (0.25 + others[..., :3].mean(-1))
    order = np.argsort(weight, axis=0)[:max(1, n // 4)]
    background = np.take_along_axis(others, order[..., None], 0).mean(0)
    cover = np.percentile(others[..., 3], 85, axis=0)
    p = picture.copy()
    p[..., 3] *= cover
    if fade is not None:
        p[..., 3] *= fade
        shared &= fade <= 0.0       # (where the picture fades out, theirs differ too little to tell apart)
    out = _over(p, background)
    out[shared] = mean[shared]
    return out


FADE_REACH = 64        # how far into a window (pixels) its edges' fade is measured


def edge_fade(others):
    """How much of a fighter shows at each pixel (h, w floats, 0 to 1) in pictures like `others` (N, h, w, 4) whose
    fighters fade into a dark background towards the edges of their window (the big portraits): the window is
    where the pictures differ much; how much they differ at each distance from its edge, against how much they
    differ deep inside, gives the fade by distance."""
    premultiplied = np.concatenate([others[..., :3] * others[..., 3:], others[..., 3:]], -1)
    spread = premultiplied.std(0).max(-1)
    much = np.percentile(spread, 90)
    if much <= 0.0:
        return np.ones(spread.shape, np.float32)
    rough = Image.fromarray(np.where(spread > 0.3 * much, 255, 0).astype(np.uint8))
    window = np.asarray(rough.filter(ImageFilter.GaussianBlur(3))) > 127     # (its edges smoothed)
    if not window.any():
        return np.ones(spread.shape, np.float32)
    # distance from the window's edge: up inside, down outside
    inside = np.minimum(_distances(~window, FADE_REACH), FADE_REACH)
    outside = np.minimum(_distances(window, FADE_REACH), FADE_REACH)
    at = np.round(np.where(window, inside - 0.5, 0.5 - outside)).astype(np.int64)
    steps = np.arange(at.min(), at.max() + 1)
    deep = spread[at >= min(FADE_REACH - 8, int(at.max() * 0.7))]
    level = np.zeros(len(steps))
    for i, step in enumerate(steps):
        here = spread[at == step]
        if len(here) >= 8:
            level[i] = np.median(here) / max(np.median(deep), 1e-6)
    # it only grows inwards, and is whole a little before the measured differences settle (the median there ~0.95)
    level = np.clip(np.maximum.accumulate(level) / 0.95, 0.0, 1.0)
    return np.interp(at, steps, level).astype(np.float32)


def _over(top, bottom):
    a = top[..., 3:4] + bottom[..., 3:4] * (1.0 - top[..., 3:4])
    rgb = top[..., :3] * top[..., 3:4] + bottom[..., :3] * bottom[..., 3:4] * (1.0 - top[..., 3:4])
    return np.concatenate([np.where(a > 1e-4, rgb / np.maximum(a, 1e-4), 0.0), a], -1)


def mirrored(a, b):
    """Whether picture b is rather a mirror image of a than a copy."""
    if a.shape != b.shape:
        return False
    return np.abs(a[:, ::-1] - b).mean() < np.abs(a - b).mean()


# ------------------------------------------------------------------------------------------------ names

# The fighters' names as the select screen's name pictures spell them, by the code of their labels: the added
# fighter's name is put together from letters cut out of these pictures (the title's own lettering: silver
# letters with a soft black shadow). The frames' labels (`p1_chara_waku_<code>`) end on the fighter's name.
NAME_TEXTS = {
    'ali': 'ALISA', 'amk': 'ARMOR KING', 'ann': 'ANNA', 'ask': 'ASUKA', 'bae': 'BAEK', 'bob': 'BOB', 'bru': 'BRUCE',
    'bry': 'BRYAN', 'chr': 'CHRISTIE', 'dra': 'DRAGUNOV', 'dvj': 'DEVIL JIN', 'edd': 'EDDY', 'fen': 'FENG',
    'gan': 'GANRYU', 'hei': 'HEIHACHI', 'hwo': 'HWOARANG', 'jac': 'JACK-6', 'jc': 'JAYCEE', 'jin': 'JIN', 'jun': 'JUN',
    'kaz': 'KAZUYA', 'kin': 'KING', 'kum': 'KUMA', 'lar': 'LARS', 'law': 'MARSHALL LAW', 'lee': 'LEE', 'lei': 'LEI',
    'leo': 'LEO', 'lil': 'LILI', 'mar': 'MARDUK', 'mig': 'MIGUEL', 'mok': 'MOKUJIN', 'nin': 'NINA', 'ogr': 'OGRE',
    'pan': 'PANDA', 'pau': 'PAUL', 'rav': 'RAVEN', 'rog': 'ROGER Jr.', 'ste': 'STEVE', 'wan': 'WANG', 'xia': 'XIAOYU',
    'yos': 'YOSHIMITSU', 'jnp': 'JINPACHI', 'knm': 'KUNIMITSU', 'sli': 'SLIM BOB', 'flw': 'FOREST LAW',
    'mih': 'MIHARU', 'cbt': 'COMBOT', 'ang': 'ANGEL', 'mic': 'MICHELLE', 'pja': 'P.JACK', 'alx': 'ALEX',
    'gre': 'ANCIENT OGRE', 'vio': 'VIOLET', 'bcv': 'DR. BOSCONOVITCH', 'seb': 'SEBASTIAN', 'tig': 'TIGER',
}
NAME_LABEL = re.compile(r'^p1_chara_waku_([a-z]+)$')
OPAQUE = 0.95          # the letters' pixels are opaque, their shadow's are not
BRIGHT = 0.35          # a letter's column has pixels at least this bright (colour times alpha)
SHADOW = 12            # how far (pixels) the shadow is measured


def _distances(mask, limit):
    """Per pixel, the distance to the nearest pixel of `mask` (inf beyond `limit`): first down each column (at most
    limit + 1, meaning farther), then the nearest of the columns around."""
    h, w = mask.shape
    far = float(limit + 1)
    column = np.empty(mask.shape)
    for rows in (range(h), range(h - 1, -1, -1)):
        run = np.full(w, far)
        for y in rows:
            run = np.where(mask[y], 0.0, np.minimum(run + 1.0, far))
            column[y] = run if rows.step > 0 else np.minimum(column[y], run)
    column *= column
    out = column.copy()
    for dx in range(1, limit + 1):
        out[:, dx:] = np.minimum(out[:, dx:], column[:, :-dx] + dx * dx)
        out[:, :-dx] = np.minimum(out[:, :-dx], column[:, dx:] + dx * dx)
    return np.where(out <= limit * limit, np.sqrt(out), np.inf)


class Letters:
    """The title's lettering for names, learnt from the fighters' name pictures: each letter cut out (between the
    middles of the gaps around it), the gap between letters, a space's width and the shadow (colour and alpha by
    distance from the letters)."""

    def __init__(self):
        self.glyphs = {}               # letter: [(cut from a name with touching letters, letter's offset, width, cut)]
        self.gaps, self.spaces, self.margins = [], [], []
        self.ring_sum = np.zeros((SHADOW + 1, 4))
        self.ring_count = np.zeros(SHADOW + 1)

    def learn(self, text, pic):
        """Cuts the letters of name picture `pic` (h, w, 4 floats) that spells `text`."""
        chars = [c for c in text if c != ' ']
        bright = ((pic[..., :3].mean(-1) * pic[..., 3]) > BRIGHT).sum(0)
        runs, start = [], None
        for x, v in enumerate(list(bright >= 2) + [False]):
            if v and start is None:
                start = x
            if not v and start is not None:
                runs.append([start, x])
                start = None
        touching = False
        while 0 < len(runs) < len(chars):      # letters that touch (YA, WA): split the widest at its faintest column
            i = max(range(len(runs)), key=lambda k: runs[k][1] - runs[k][0])
            a, b = runs[i]
            lo, hi = a + (b - a) // 5, b - (b - a) // 5
            if hi <= lo:
                return
            x = lo + int(np.argmin(bright[lo:hi]))
            runs[i:i + 1] = [[a, x], [x, b]]
            touching = True
        if not runs or len(runs) != len(chars):
            return
        ink = np.nonzero(pic[..., 3].max(0) > 0.02)[0]
        cuts = [int(ink[0])] + [(runs[i][1] + runs[i + 1][0]) // 2 for i in range(len(runs) - 1)] + [int(ink[-1]) + 1]
        for i, ch in enumerate(chars):
            self.glyphs.setdefault(ch, []).append((touching, runs[i][0] - cuts[i], runs[i][1] - runs[i][0],
                                                   pic[:, cuts[i]:cuts[i + 1]].copy()))
        spaces, at = set(), 0
        for word in text.split(' ')[:-1]:
            at += len(word)
            spaces.add(at)                     # a space between letters at - 1 and at
        for i in range(1, len(runs)):
            if i in spaces:
                self.spaces.append(runs[i][0] - runs[i - 1][1])
            elif not touching:
                self.gaps.append(runs[i][0] - runs[i - 1][1])
        solid = pic[..., 3] > OPAQUE
        if solid.any():
            cols = np.nonzero(solid.any(0))[0]
            self.margins.append((int(cols[0]), pic.shape[1] - 1 - int(cols[-1])))
            d = _distances(solid, SHADOW)
            ring = np.where(solid | ~np.isfinite(d), 0, np.round(np.where(np.isfinite(d), d, 0))).astype(np.int64)
            ok = (ring <= SHADOW) & (ring >= 1)
            np.add.at(self.ring_sum, ring[ok], np.concatenate([pic[..., :3] * pic[..., 3:], pic[..., 3:]], -1)[ok])
            np.add.at(self.ring_count, ring[ok], 1)

    def glyph(self, ch):
        found = self.glyphs.get(ch)
        if not found:
            return None
        clean = [g for g in found if not g[0]] or found
        return sorted(clean, key=lambda g: g[2])[len(clean) // 2]       # the one of middle width

    def picture(self, text):
        """`text` in the title's lettering (h, w, 4 floats), or None when a letter of it is missing."""
        if not self.glyphs or not self.gaps:
            return None
        parts = [None if c == ' ' else self.glyph(c) for c in text]
        if any(p is None for c, p in zip(text, parts) if c != ' '):
            return None
        gap = int(np.median(self.gaps))
        space = int(np.median(self.spaces)) if self.spaces else 4 * gap
        left, right = (int(np.median([m[k] for m in self.margins])) for k in (0, 1))
        h = parts[[c != ' ' for c in text].index(True)][3].shape[0]
        x, placed = left, []
        for c, p in zip(text, parts):
            if p is None:
                x += space - gap
                continue
            _, offset, width, cut = p
            placed.append((x - offset, cut))
            x += width + gap
        w = x - gap + right
        pad = SHADOW
        letters = np.zeros((h, w + 2 * pad, 4), np.float32)
        for x0, cut in placed:
            x0 += pad
            solid = cut[..., 3:] > OPAQUE
            area = letters[:, x0:x0 + cut.shape[1]]
            area[:] = np.where(solid, cut, area)
        letters = letters[:, pad:pad + w]
        solid = letters[..., 3] > OPAQUE
        # the shadow, by distance from the letters, as measured on the title's names
        d = np.round(_distances(solid, SHADOW))
        n = np.maximum(self.ring_count, 1)[:, None]
        mean = self.ring_sum / n
        out = letters.copy()
        for k in range(1, SHADOW + 1):
            at = (d == k) & ~solid
            alpha = mean[k, 3]
            if alpha > 0:
                out[at] = np.concatenate([mean[k, :3] / alpha, [alpha]])
        return out

    @classmethod
    def of_layout(cls, layout):
        """The letters of a layout's name pictures (None when it has none)."""
        lm = layout.lm
        letters = cls()
        for sprite in lm.sprites():
            labels = lm.labels_of(sprite)
            for name in labels:
                m = NAME_LABEL.match(name)
                if not m or m.group(1) not in NAME_TEXTS:
                    continue
                frame = layout.label_frame(sprite, labels, name, True)
                for c in (frame.children if frame else []):
                    shape = lm.char(c.char) if isinstance(c, lmb.Place) and c.mode != lmb.MODE_MOVE else None
                    if isinstance(shape, lmb.Shape) and shape.graphics and shape.graphics[0].atlas in layout.atlases:
                        letters.learn(NAME_TEXTS[m.group(1)], layout.shape_picture(shape)[0])
            if letters.glyphs:
                return letters
        return None


# ------------------------------------------------------------------------------------------------ layouts

def code_label(label, code):
    """`label` with Paul's code token replaced: face_pau_lose -> face_<code>_lose (None if it has none)."""
    m = re.search(r'(?:^|(?<=_))%s(?=_|$)' % PAUL, label)
    return None if m is None else label[:m.start()] + code + label[m.end():]


class Layout:
    """One LMB layout and its texture container, with the fighter's labels and pictures added."""

    def __init__(self, lm, textures, sources, code, codes, cell):
        self.lm, self.textures, self.sources, self.code, self.codes = lm, textures, sources, code, codes
        self.cell = cell              # the new grid cell: pack.place's dict (anchor, columns, grid_row)
        self.atlases = {t['gidx']: t for t in textures['textures']}
        self.decoded = {}
        self.new = []                  # (shape id, Paul's shape, picture): pictures waiting for a page
        self.changed = False

    # -- the title's pictures
    def atlas(self, aid):
        if aid not in self.decoded:
            self.decoded[aid] = _float(nut.decode(self.atlases[aid]))
        return self.decoded[aid]

    def shape_picture(self, shape):
        """A shape's picture (its first graphic's region of its atlas), and the region's size in texels."""
        g = shape.graphics[0]
        a = self.atlas(g.atlas)
        h, w = a.shape[:2]
        u0, v0, u1, v1 = g.uv_box()
        x0, y0, x1, y1 = round(u0 * w), round(v0 * h), round(u1 * w), round(v1 * h)
        return a[y0:y1, x0:x1], (x1 - x0, y1 - y0)

    def label_frame(self, sprite, labels, name, last):
        """What label `name` shows: its keyframe (the display list at the label), or with `last` its last frame
        when the label plays on (None when it does not)."""
        if not last:
            return sprite.frame(labels[name], True)
        start, end = self.lm.label_span(sprite, name)
        return sprite.frame(end - 1) if end - start > 1 else None

    def fighters_pictures(self, sprite, labels, prefix, suffix, depth, size, last=False):
        """Every fighter's picture at `depth` of its label (prefix + code + suffix), resized to `size`."""
        out = []
        for code in self.codes:
            name = prefix + code + suffix
            if name not in labels:
                continue
            key = self.label_frame(sprite, labels, name, last)
            hits = [c for c in (key.children if key else []) if isinstance(c, lmb.Place) and c.depth == depth
                    and c.mode != lmb.MODE_MOVE]
            shape = self.lm.char(hits[0].char) if hits else None
            if not isinstance(shape, lmb.Shape) or not shape.graphics or shape.graphics[0].atlas not in self.atlases:
                continue
            pic, _ = self.shape_picture(shape)
            if pic.size:
                out.append(pic if pic.shape[1::-1] == size else _resize(pic, *size))
        return np.stack(out) if out else None

    # -- the fighter's labels
    def add_labels(self):
        lm = self.lm
        for sprite in lm.sprites():
            labels = lm.labels_of(sprite)
            for paul in [n for n in labels if code_label(n, self.code)]:
                new = code_label(paul, self.code)
                if new in labels:
                    continue
                prefix, suffix = paul.split(PAUL, 1) if paul.startswith(PAUL) else re.split(
                    r'(?<=_)%s(?=_|$)' % PAUL, paul, maxsplit=1)
                char_map = self.own_shapes(sprite, labels, paul, prefix, suffix)
                lm.add_label_like(sprite, paul, new, char_map)
                self.changed = True

    def own_shapes(self, sprite, labels, paul, prefix, suffix):
        """{Paul's shape: the fighter's new shape} for each depth where the fighters' shapes differ, in what the
        label shows at once and, when it plays on, at its end (the frames' labels end on the fighter's name)."""
        lm = self.lm
        names = [prefix + c + suffix for c in self.codes if c != PAUL and prefix + c + suffix in labels]
        char_map = {}
        for last in (False, True):
            mine = self.label_frame(sprite, labels, paul, last)
            if mine is None or (GAME_DRAWN.match(prefix) and not last):
                continue                                    # the game draws the frames' portraits itself
            others = [self.label_frame(sprite, labels, n, last) for n in names]
            for c in mine.children:
                shape = lm.char(c.char) if isinstance(c, lmb.Place) and c.mode != lmb.MODE_MOVE else None
                if not isinstance(shape, lmb.Shape) or shape.id in char_map:
                    continue
                theirs = [[x.char for x in o.children if isinstance(x, lmb.Place) and x.depth == c.depth
                           and x.mode != lmb.MODE_MOVE] for o in others if o]
                if theirs and all(t == [shape.id] for t in theirs):
                    continue                                # every fighter shows this one: a frame, a background
                if not shape.graphics or shape.graphics[0].atlas not in self.atlases:
                    continue
                pic, size = self.shape_picture(shape)
                if not min(size):
                    continue
                if 'name' in prefix or (last and GAME_DRAWN.match(prefix)):
                    char_map[shape.id] = self.new_shape(shape, self.sources.title_name(*size))
                    continue
                stack = self.fighters_pictures(sprite, labels, prefix, suffix, c.depth, size, last)
                mirror = False
                if 'p2' in prefix:                          # player 2's pictures: mirrored if player 1's are
                    one = prefix.replace('p2', 'p1')
                    if one + PAUL + suffix in labels:
                        ref = self.fighters_pictures(sprite, labels, one, suffix, c.depth, size, last)
                        mirror = ref is not None and mirrored(ref[0], pic)
                mine_pic = self.sources.framed(face_place(*size), size[0], size[1], mirror)
                picture = compose(stack, mine_pic) if stack is not None and len(stack) >= 3 else mine_pic
                char_map[shape.id] = self.new_shape(shape, picture)
        return char_map

    def new_shape(self, like, picture):
        """A shape like `like` (same geometry; as wide as `picture` needs, about the same centre: names) that will
        show `picture` (placed on a page in pages())."""
        _, (w, _) = self.shape_picture(like)
        scale = picture.shape[1] / w if w else 1.0
        if abs(scale - 1.0) > 1e-6:
            x0, _, x1, _ = like.graphics[0].xy_box()
            cx = (x0 + x1) / 2
            graphics = [lmb.Graphic(g.atlas, [[cx + (x - cx) * scale, y, u, v] for x, y, u, v in g.verts],
                                    list(g.indices), g.fill) for g in like.graphics]
            like = lmb.Shape(like.id, like.bounds, graphics, like.unk1, like.unk3)
        cid = self.lm.take_id()
        self.new.append((cid, like, picture))
        # placeholder: the real graphics come in pages(); reserve the id now
        self.lm.add_shape(cid, [lmb.Graphic(like.graphics[0].atlas, [list(v) for v in like.graphics[0].verts],
                                            list(like.graphics[0].indices), like.graphics[0].fill)])
        return cid

    # -- the select grid's new cell
    def add_cell(self):
        lm = self.lm
        below = lm.find_named('face_panel_' + self.cell['anchor'])
        beside = lm.find_named('face_panel_' + GRID_BESIDE)
        pitch = [lm.find_named('face_panel_' + c) for c in PITCH_FROM]
        rows = [lm.find_named('face_panel_' + c) for c in ROW_PITCH_FROM]
        if not below or not beside or not all(pitch) or not all(rows) or lm.find_named('face_panel_' + self.code):
            return
        grid, _, place = below[0]
        panel = lm.char(place.char)
        other = lm.char(beside[0][2].char)
        if not isinstance(panel, lmb.Sprite) or not isinstance(other, lmb.Sprite):
            return
        # the panel's own picture: the shapes it shows that the neighbour's panel does not
        theirs = {c.char for _, c in other.all_children() if isinstance(c, lmb.Place)}
        char_map = {}
        stack = self.panel_pictures()
        for _, c in panel.all_children():
            shape = lm.char(c.char) if isinstance(c, lmb.Place) else None
            if isinstance(shape, lmb.Shape) and shape.id not in theirs and shape.id not in char_map:
                pic, size = self.shape_picture(shape)
                mine = self.sources.framed(face_place(*size), size[0], size[1])
                ok = stack is not None and stack.shape[1:3] == (size[1], size[0])
                char_map[shape.id] = self.new_shape(shape, compose(stack, mine) if ok else mine)
        xs = [_place_xy(lm, p[0][2])[0] for p in pitch]
        top = _place_xy(lm, beside[0][2])[1]
        ys = [_place_xy(lm, r[0][2])[1] for r in rows]
        if top is None or None in xs or None in ys:
            return
        sid = lm.take_id(below=grid.id, above=max(panel.id, max(char_map.values())))
        lm.clone_sprite(panel.id, sid, char_map)
        dx = (xs[1] - xs[0]) * self.cell['columns']
        in_top = self.cell['grid_row'] <= 0
        row_pitch = ys[1] - ys[0]
        # (the top row's card frame where the top row has its; above it: rows' pitches higher)
        y = top + _card_offset(lm, panel, other) + row_pitch * self.cell['grid_row'] if in_top \
            else _place_xy(lm, place)[1]
        # in the grid: everything the panel below does, at a new depth after the panels of its row and the rows
        # above it (a row's panels draw over the row above them)
        panels = [(c.depth, _place_xy(lm, c)[1]) for _, c in grid.all_children() if isinstance(c, lmb.Place)
                  and c.mode == lmb.MODE_PLACE and c.name and lm.symbols[c.name].startswith('face_panel_')]
        above = [d for d, py in panels if py is not None and py <= y + row_pitch / 2]
        depth = max(above) + 1 if above else min(d for d, _ in panels)
        lm.insert_depth(grid, depth)

        def to_cell(m):
            m[4] += dx
            if in_top:
                m[5] = y
            return m

        def to_cell_position(p):
            p[0] += dx
            if in_top:
                p[1] = y
            return p
        lm.clone_depth(grid, place.depth, depth, char=sid, name='face_panel_' + self.code,
                       matrix_fn=to_cell, position_fn=to_cell_position)
        self.changed = True

    def panel_pictures(self):
        """Every fighter's grid panel picture (the shape its panel shows and the next fighter's does not)."""
        lm = self.lm
        sprites = []
        for code in self.codes:
            hit = lm.find_named('face_panel_' + code)
            if hit and isinstance(lm.char(hit[0][2].char), lmb.Sprite):
                sprites.append(lm.char(hit[0][2].char))
        shapes = []
        for i, sp in enumerate(sprites):
            nxt = sprites[(i + 1) % len(sprites)]
            theirs = {c.char for _, c in nxt.all_children() if isinstance(c, lmb.Place)}
            own = [lm.char(c.char) for _, c in sp.all_children() if isinstance(c, lmb.Place)
                   and isinstance(lm.char(c.char), lmb.Shape) and c.char not in theirs]
            if own:
                shapes.append(own[0])
        if len(shapes) < 3:
            return None
        pics = [self.shape_picture(s) for s in shapes]
        size = max(set(p[1] for p in pics), key=[p[1] for p in pics].count)
        return np.stack([p[0] for p in pics if p[1] == size])

    # -- texture pages
    def pages(self):
        """Puts the new pictures on new texture pages; returns the pages' textures."""
        if not self.new:
            return []
        items = sorted(self.new, key=lambda n: -n[2].shape[0])
        placed, x, y, row, width = [], 0, 0, 0, 0
        for cid, like, pic in items:
            h, w = pic.shape[:2]
            if x + w > PAGE_WIDTH:
                x, y, row = 0, y + row + 4, 0
            placed.append((cid, like, pic, x, y))
            x += w + 4
            row = max(row, h)
            width = max(width, x)
        pw, ph = (width + 3) & ~3, (y + row + 3) & ~3
        page = np.zeros((ph, pw, 4), np.float32)
        aid = self.lm.add_atlas(pw, ph)
        for cid, like, pic, px, py in placed:
            h, w = pic.shape[:2]
            page[py:py + h, px:px + w] = pic
            shape = self.lm.char(cid)
            shape.graphics = [self.remap(g, like.graphics[0], (px / pw, py / ph, (px + w) / pw, (py + h) / ph))
                              for g in like.graphics]
        tex = nut.make_texture(_uint8(page), aid, fmt=2, mips=1)
        return [tex]

    @staticmethod
    def remap(g, first, box):
        """A copy of graphic g with its texture coordinates moved from `first`'s region to `box` on a new page."""
        u0, v0, u1, v1 = first.uv_box()
        nu0, nv0, nu1, nv1 = box
        verts = []
        for x, y, u, v in g.verts:
            su = (u - u0) / (u1 - u0) if u1 > u0 else 0.0
            sv = (v - v0) / (v1 - v0) if v1 > v0 else 0.0
            verts.append([x, y, nu0 + su * (nu1 - nu0), nv0 + sv * (nv1 - nv0)])
        return lmb.Graphic(None, verts, list(g.indices), g.fill)


def four_rows(lm):
    """Layout `lm` (a select screen's, with the grid panels) made for the grid with a new top row (see ROWS_DOWN).
    -> whether it was one."""
    def y_of(name):
        hit = lm.find_named(name)
        return lm.matrices[hit[0][2].posid][5] if hit and hit[0][2].posflags == lmb.POS_MATRIX else None

    hit = lm.find_named('face_panel_' + ROW_PITCH_FROM[0])
    random = lm.find_named('random_face_panel')
    if not hit or not random or None in _place_xy(lm, random[0][2]):
        return False
    grid = hit[0][0]
    y0, y1 = _y_extent(lm, random[0][2].char)
    old = (_place_xy(lm, random[0][2])[1] + y0, _place_xy(lm, random[0][2])[1] + y1)   # the '?' panel: three rows
    new = (old[0], old[1] + ROWS_DOWN)                                                 # four
    scale = (new[1] - new[0]) / (old[1] - old[0])
    line = y_of('face_waku_up_line_2')
    labels = lm.labels_of(grid)
    stage, out = labels.get(STAGE_LABEL, 1 << 30), labels.get(OUT_LABEL, 1 << 30)
    symbols = lm.symbols

    def kind_of(c, y, index):
        """How an object placed at y in frame `index` moves: ('dy', amount), ('stretch',) or None (it stays)."""
        name = symbols[c.name] if c.name else ''
        if not name and index >= out:
            return None                                     # (the stage cards coming in)
        if name.startswith('face_panel_'):
            return 'dy', ROWS_DOWN
        if GRID_LINE.match(name) or (not name and line is not None and abs(y - line) <= 3):
            return None                                     # (the new row is where the top row was)
        if RANDOM_PANEL.match(name) or (not name and old[0] <= y <= old[1]
                                        and _height(lm, c.char) >= 0.8 * (old[1] - old[0])):
            return ('stretch',)                             # the '?' panel, the grid's end caps
        if name in LEFT_OUT:
            return 'dy', 1000.0
        if name in UNDER_LINE:
            return 'dy', ROWS_DOWN
        if name in SPACERS or (not name and y >= old[0]):  # (the cells' flashes as the grid comes in, the band
            return 'dy', ROWS_DOWN                          # under the grid)
        return None

    def position(c):
        if c.posflags == lmb.POS_MATRIX:
            return lm.matrices[c.posid][5]
        if c.posflags == lmb.POS_POSITION:
            return lm.positions[c.posid][1]
        return None

    def move(c, kind):
        if kind is None or c.posflags == lmb.POS_NONE:
            return
        if kind[0] == 'dy':
            if c.posflags == lmb.POS_MATRIX:
                m = list(lm.matrices[c.posid])
                m[5] += kind[1]
                c.posid = lm.add_record(lmb.T_MATRICES, m)
            else:
                p = list(lm.positions[c.posid])
                p[1] += kind[1]
                c.posid = lm.add_record(lmb.T_POSITIONS, p)
            return
        if c.posflags == lmb.POS_MATRIX:
            m = list(lm.matrices[c.posid])
        else:
            x, y = lm.positions[c.posid][:2]
            m = [1.0, 0.0, 0.0, 1.0, x, y]
            c.posflags = lmb.POS_MATRIX
        m[1] *= scale
        m[3] *= scale
        m[5] = new[0] + (m[5] - old[0]) * scale
        c.posid = lm.add_record(lmb.T_MATRICES, m)

    kinds = {}                                              # depth: how its object moves (frames in order)
    for f in sorted(grid.frames, key=lambda f: f.index):
        if f.index >= stage:
            break
        for c in f.children:
            if isinstance(c, lmb.Remove):
                kinds.pop(c.depth, None)
            elif isinstance(c, lmb.Place):
                y = position(c)
                if c.mode == lmb.MODE_PLACE and y is not None:
                    kinds[c.depth] = kind_of(c, y, f.index)
                move(c, kinds.get(c.depth))
    for f in grid.keyframes:                                # (each the whole state of its frame)
        if f.index >= stage:
            continue
        for c in f.children:
            y = position(c) if isinstance(c, lmb.Place) else None
            if y is not None:
                move(c, kind_of(c, y, f.index))
    return True


def _place_xy(lm, c):
    """Where placement c puts its object: (x, y), or (None, None)."""
    if c.posflags == lmb.POS_MATRIX:
        return tuple(lm.matrices[c.posid][4:6])
    if c.posflags == lmb.POS_POSITION:
        return tuple(lm.positions[c.posid][:2])
    return None, None


def _y_extent(lm, cid, depth=0):
    """(top, bottom) of character cid (its first frame's shapes, through its sprites; (0, 0) for nothing)."""
    ch = lm.char(cid)
    if isinstance(ch, lmb.Shape):
        boxes = [g.xy_box() for g in ch.graphics]
        return (min(b[1] for b in boxes), max(b[3] for b in boxes)) if boxes else (0.0, 0.0)
    if not isinstance(ch, lmb.Sprite) or not ch.frames or depth > 8:
        return 0.0, 0.0
    ends = []
    for c in ch.frames[0].children:
        if isinstance(c, lmb.Place) and c.mode == lmb.MODE_PLACE:
            top, bottom = _y_extent(lm, c.char, depth + 1)
            scale = lm.matrices[c.posid][3] if c.posflags == lmb.POS_MATRIX else 1.0
            y = _place_xy(lm, c)[1] or 0.0
            ends += [y + top * scale, y + bottom * scale]
    return (min(ends), max(ends)) if ends else (0.0, 0.0)


def _height(lm, cid):
    """How tall character cid is."""
    top, bottom = _y_extent(lm, cid)
    return abs(bottom - top)


def _card_offset(lm, panel, other):
    """How much lower panel sprite `panel` must be placed for the card frame it shares with sprite `other` (a
    character both show, in any of their frames: their labels differ in order) to be where `other` has it (0 when
    they share none)."""
    def places(sprite):
        out = {}
        for f in sorted(sprite.frames, key=lambda f: f.index):
            for c in f.children:
                if isinstance(c, lmb.Place) and c.mode == lmb.MODE_PLACE and _place_xy(lm, c)[1] is not None:
                    out.setdefault(c.char, _place_xy(lm, c)[1])
        return out
    mine, theirs = places(panel), places(other)
    common = [cid for cid in mine if cid in theirs]
    return theirs[common[0]] - mine[common[0]] if common else 0.0


# ------------------------------------------------------------------------------------------------ portraits

def portrait(sources, others, player2, fade):
    """A big portrait (356x612) like `others` (every fighter's of that kind; fade: edge_fade(others))."""
    w, h = PORTRAIT_SIZE
    mine = sources.framed(FACE_PORTRAIT, w, h, mirror=player2)
    return compose(others, mine, fade)


def container_frames(d):
    n, = struct.unpack_from('>I', d, 0)
    return [struct.unpack_from('>II', d, 4 + 8 * i) for i in range(n)]


def with_frames(d, frames):
    """Container `d` with NTP3s `frames` added after its own."""
    old = [d[o:o + s] for o, s in container_frames(d)]
    allf = old + frames
    head = (4 + 8 * len(allf) + 15) & ~15
    out = bytearray(head)
    struct.pack_into('>I', out, 0, len(allf))
    for i, f in enumerate(allf):
        struct.pack_into('>II', out, 4 + 8 * i, len(out), len(f))
        out += f
        out += bytes(-len(out) % 16)
    return bytes(out)


def _texture_picture(d):
    return _float(nut.decode(nut.read(d)['textures'][0]))


def _one_texture(picture):
    return nut.write([nut.make_texture(_uint8(picture), 0, fmt=2, mips=1)])


def like_texture(texture, picture):
    """A copy of one of the title's textures (its header as it is) with `picture` (same size) in it."""
    out = dict(texture)
    out['mips'] = nut.make_texture(_uint8(picture), texture['gidx'], fmt=texture['fmt'], mips=1)['mips']
    return out


def portrait_files(sources, archives, rpx):
    """The loading and VS screens' portraits: for each key table, a texture like Paul's (its first row) with the
    fighter in it, made like every fighter's of that table."""
    files = {}
    for name, table, player2 in PORTRAIT_FILES:
        keys = [rpx.u32(table + 8 * u) for u in range(UI_ROWS)]
        keys = [k for k in keys if k and archives.has(k)]
        if not keys or keys[0] != rpx.u32(table):
            continue
        paul = nut.read(archives.read(keys[0]))['textures'][0]
        pics = []
        for k in keys:
            t = nut.read(archives.read(k))['textures'][0]
            if (t['w'], t['h']) == (paul['w'], paul['h']):
                pics.append(_float(nut.decode(t)))
        pics = np.stack(pics)
        mine = compose(pics, sources.framed(FACE_PORTRAIT, paul['w'], paul['h'], mirror=player2), edge_fade(pics))
        files[name] = nut.write([like_texture(paul, mine)])
    return files


CUT_TRANSPARENT = 0.01      # a costume picture with more than this share of pixels under half alpha has its
                            # background transparent (Tekken 8's); Tekken 7's are opaque (alpha 242 at the least)
CUT_ALPHA = 8               # ... and its fighter is where alpha is at least this (of 255)


def cut_out(img):
    """A costume picture (H, W, 4 uint8) -> the fighter alone (h, w, 4 floats) cut to it, or None. On a
    transparent background (Tekken 8's) the fighter is what is not transparent. On Tekken 7's costume-slot panel
    the background is a smooth neutral grey (red = green, blue a little higher), reached from the panel's edges in
    small steps; everything else on the panel is the fighter."""
    if (img[..., 3] < 128).mean() > CUT_TRANSPARENT:
        ys, xs = np.nonzero(img[..., 3] >= CUT_ALPHA)
        if not len(ys):
            return None
        return _float(img[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    rgb = img[..., :3].astype(np.int32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    white = (rgb > 240).all(-1)
    cols, rows = np.nonzero((~white).mean(0) > 0.5)[0], np.nonzero((~white).mean(1) > 0.5)[0]
    if not len(cols) or not len(rows):
        return None
    x0, x1, y0, y1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
    grey = (np.abs(r - g) <= 2) & (b - r >= 3) & (b - r <= 24)
    background = np.zeros(grey.shape, bool)
    edge = np.zeros(grey.shape, bool)
    edge[y0, x0:x1] = edge[y1 - 1, x0:x1] = edge[y0:y1, x0] = edge[y0:y1, x1 - 1] = True
    stack = list(zip(*np.nonzero(edge & grey)))
    for y, x in stack:
        background[y, x] = True
    while stack:
        y, x = stack.pop()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if (y0 <= yy < y1 and x0 <= xx < x1 and not background[yy, xx] and grey[yy, xx]
                    and np.abs(rgb[yy, xx] - rgb[y, x]).max() <= 10):
                background[yy, xx] = True
                stack.append((yy, xx))
    fighter = ~background
    fighter[:y0] = fighter[y1:] = False
    fighter[:, :x0] = fighter[:, x1:] = False
    ys, xs = np.nonzero(fighter)
    if not len(ys):
        return None
    out = np.concatenate([rgb / 255.0, fighter[..., None]], -1).astype(np.float32)
    return out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def costume_previews(source, archives, rpx, d, slot):
    """The chooser's container for the fighter: one picture, its costume (NTP3 bytes), or None. source: its
    picture source (or Tekken 7's paks). The definition's ART 'costume' is the picture's path, or (path, (x0, y0, x1,
    y1)): the part of it (pixels) the fighter is cut from (a wide artwork: Azazel has no picture standing)."""
    path = d.ART.get('costume') if hasattr(d, 'ART') else None
    path, box = path if isinstance(path, tuple) else (path, None)
    if not path:
        return None
    picture = picture_source(source).picture(path)
    if box is not None:
        x0, y0, x1, y1 = box
        picture = picture[y0:y1, x0:x1]
    fighter = cut_out(picture)
    if fighter is None:
        return None
    textures = []
    for sid in range(SELECT_IDS):
        key = rpx.u32(COSTUME_PREVIEWS + 4 * sid)
        if archives.has(key):
            textures += nut.read(archives.read(key))['textures']
    like = textures[0]
    w, h = like['w'], like['h']
    pics = np.stack([_float(nut.decode(t)) for t in textures if (t['w'], t['h']) == (w, h)])
    # the room: per pixel, the darkest twentieth of the title's pictures (the fighters are lit, the room is not)
    order = np.argsort(pics[..., :3].mean(-1), 0)[:max(1, len(pics) // 20)]
    out = np.take_along_axis(pics, order[..., None], 0).mean(0)
    out[..., 3] = 1.0
    height = round(COSTUME_HEIGHT * h)
    width = max(1, round(fighter.shape[1] * height / fighter.shape[0]))
    small = _resize(fighter, width, height)
    top, left = round(COSTUME_TOP * h), (w - width) // 2

    def put(picture, x, y):
        ph, pw = picture.shape[:2]
        sx, sy, dx0, dy0 = max(0, -x), max(0, -y), max(0, x), max(0, y)
        dx1, dy1 = min(w, x + pw), min(h, y + ph)
        if dx1 > dx0 and dy1 > dy0:
            out[dy0:dy1, dx0:dx1] = _over(picture[sy:sy + dy1 - dy0, sx:sx + dx1 - dx0], out[dy0:dy1, dx0:dx1])

    reflection = small[::-1][:h // 12].copy()                 # on the floor below the feet, fading out
    reflection[..., 3] *= np.linspace(0.3, 0.0, len(reflection))[:, None]
    put(reflection, left, top + height)
    put(small, left, top)
    texture = like_texture(like, out)
    texture['gidx'] = max(t['gidx'] for t in textures) + 1 + slot    # an id no other costume picture has
    texture.pop('ext', None)
    return nut.write([texture])


# ------------------------------------------------------------------------------------------------ build

def hud_textures(sources, archives):
    """The added fighters' HUD names and faces, as textures to add to the HUD's container (NTP3 bytes): three per
    place up to the last one with a fighter (sources: {slot: Sources}; an empty place gets Paul's)."""
    textures = nut.read(archives.read(HUD))['textures']
    pictures = []
    for slot in range(max(sources) + 1):
        if slot not in sources:
            pictures += [_float(nut.decode(textures[n])) for n in HUD_PAUL]
            continue
        name_tex = textures[HUD_PAUL[0]]
        name = sources[slot].title_name(name_tex['w'], name_tex['h'])
        if name.shape[1] % 4:
            name = np.concatenate([name, np.zeros((name.shape[0], 4 - name.shape[1] % 4, 4), np.float32)], 1)
        pictures.append(name)
        for player, first in enumerate(HUD_PAUL[1:]):
            others = np.stack([_float(nut.decode(textures[first + ui])) for ui in range(UI_ROWS)])
            h, w = others.shape[1:3]
            pictures.append(compose(others, sources[slot].framed(FACE_HUD, w, h, mirror=player == 1)))
    return nut.write([nut.make_texture(_uint8(p), len(textures) + 1 + i, fmt=2, mips=1)
                      for i, p in enumerate(pictures)])


def layout_entries(archives):
    """[(LMB index, key, NTP3 key)] of the 2D layouts."""
    idx = archives.indices[LAYOUTS]
    out = []
    for i in range(len(idx) - 1):
        out.append((i, idx[i][0], idx[i + 1][0]))
    return out


def codes_in(lm):
    """The fighter codes of a layout's per-fighter labels (the code tokens that Paul's labels have beside them)."""
    found = set()
    for s in lm.symbols:
        m = re.match(r'^(?:.*_)?face_panel_([a-z]{3})$', s) or re.match(r'^face_([a-z]{3})$', s)
        if m:
            found.add(m.group(1))
    return found


def pack_files(source, archives, rpx, d, slot, log=None):
    """The fighter's own pictures for its pack: the loading and VS screens' portraits and the costume chooser's
    picture. -> {file name: bytes}. source: the fighter's picture source (or Tekken 7's paks)."""
    source = picture_source(source)
    sources = Sources(source, d)
    files = portrait_files(sources, archives, rpx)
    costumes = costume_previews(source, archives, rpx, d, slot)
    if costumes is not None:
        files[COSTUME_FILE] = costumes
    if log:
        log('%d loading and VS screen portraits%s' % (
            len(files) - (costumes is not None), '; the costume chooser\'s picture' if costumes is not None else ''))
    return files


def shared_files(source, archives, rpx, fighters, log=None, new_row=False):
    """What the added fighters share, for fighters [(slot, definition)]: the 2D layouts with every fighter's labels
    and grid cell, the big portraits' container with two frames per place, the HUD's pictures by place.
    -> {file name: bytes}. source: the fighters' picture source (one for all, by slot or code, or by definition:
    source_of; or Tekken 7's paks); rpx: the title's executable (ttt2.rpx); new_row: the select grid with a new top
    row (four_rows), for fighters past pack.CELLS."""
    fighters = sorted(fighters, key=lambda f: f[0])
    files = {}
    # the game's fighters' codes: from every layout's labels `face_<code>` and `face_panel_<code>`
    entries = layout_entries(archives)
    blobs = {}
    codes = set()
    for i, key, tkey in entries:
        data = archives.entry(LAYOUTS, i)
        if data[:4] != b'LMB\0':
            continue
        blobs[i] = data
        codes |= codes_in(lmb.Lmb.read(data))
    codes -= {d.CODE for _, d in fighters}
    codes = [PAUL] + sorted(codes - {PAUL})
    sources = {}
    for slot, d in fighters:
        sources[slot] = Sources(source_of(source, slot, d), d)
        sources[slot].short_name = getattr(d, 'SHORT_NAME', d.NAME.split()[0].upper())
    # the fighters' names in the title's lettering, learnt from the select screen's names
    letters = None
    for i, key, tkey in entries:
        if i in blobs and b'p1_chara_waku_' + PAUL.encode() in blobs[i]:
            nxt = archives.entry(LAYOUTS, i + 1)
            if nxt[:4] == b'NTP3':
                any_sources = sources[fighters[0][0]]
                letters = Letters.of_layout(Layout(lmb.Lmb.read(blobs[i]), nut.read(nxt), any_sources, PAUL, codes,
                                                   place(0)))
            if letters is not None:
                break
    for slot, d in fighters:
        sources[slot].letters = letters
        if log:
            made = letters.picture(sources[slot].short_name) if letters else None
            log('%s in the title\'s letters: %s' % (d.NAME, '%d x %d' % made.shape[1::-1] if made is not None
                                                   else 'no (its game\'s name picture instead)'))
    count = 0
    for i, key, tkey in entries:
        if i not in blobs:
            continue
        nxt = archives.entry(LAYOUTS, i + 1)
        if nxt[:4] != b'NTP3':
            continue
        lm = lmb.Lmb.read(blobs[i])
        textures = nut.read(nxt)
        pages, changed = [], False
        for slot, d in fighters:
            cell = place(slot)
            if cell['anchor'] is None:
                continue                          # no cell left in the grid
            if not any(code_label(s, d.CODE) for s in lm.symbols) and 'face_panel_' + cell['anchor'] not in lm.symbols:
                continue
            layout = Layout(lm, textures, sources[slot], d.CODE, codes, cell)
            layout.add_labels()
            layout.add_cell()
            if not layout.changed:
                continue
            changed = True
            new = layout.pages()
            for tex in new:
                for shape in lm.shapes():
                    for g in shape.graphics:
                        if g.atlas is None:
                            g.atlas = tex['gidx']
            pages += new
        if not changed:
            continue
        if new_row:
            four_rows(lm)
        files['keys/%08x.bin' % key] = lm.write()
        if pages:
            files['keys/%08x.add' % tkey] = nut.write(pages)
        count += 1
    # the big portraits: two frames per place (Paul's for a place with no fighter)
    cont = archives.read(PORTRAITS)
    frames = container_frames(cont)
    pics = np.stack([_texture_picture(cont[o:o + s]) for o, s in frames])
    fades = [edge_fade(pics[p::2]) for p in (0, 1)]
    new = []
    for slot in range(max(sources) + 1):
        if slot in sources:
            new += [_one_texture(portrait(sources[slot], pics[p::2], p == 1, fades[p])) for p in (0, 1)]
        else:
            new += [cont[o:o + s] for o, s in frames[:2]]
    files['keys/%08x.bin' % PORTRAITS] = with_frames(cont, new)
    files['keys/%08x.add' % HUD] = hud_textures(sources, archives)
    if log:
        log('pictures in %d layouts; the big select portraits; the names and faces in fights' % count)
    return files


# ------------------------------------------------------------------------------------------------ kept

class Blank:
    """A picture source whose pictures are empty: what shared_files makes with it for a fighter has the places and
    sizes of what it makes from the fighter's own pictures (those come from the title's pictures and lettering), to
    be filled from an earlier shared/'s (keep)."""

    game = None

    @staticmethod
    def picture(path):
        return np.zeros((4, 4, 4), np.uint8)


class Lost(Exception):
    """An earlier shared/ lacks a kept fighter's pictures, or has them at other sizes (args: the fighter's
    definition, which pictures)."""


def fighter_pages(lm, code, pages):
    """The texture pages (atlas ids of `pages`) the added fighter `code` has in layout lm: those of the shapes its
    labels (Paul's with its code: Layout.add_labels) and its grid cell (face_panel_<code>: Layout.add_cell) show."""
    chars = set()
    for sprite in lm.sprites():
        labels = lm.labels_of(sprite)
        for name in labels:
            if re.search(r'(?:^|_)%s(?:_|$)' % code, name):
                start, end = lm.label_span(sprite, name)
                chars |= {c.char for f in sprite.frames + sprite.keyframes if start <= f.index < end
                          for c in f.children if isinstance(c, lmb.Place)}
    for _, _, place_ in lm.find_named('face_panel_' + code):
        cell = lm.char(place_.char)
        if isinstance(cell, lmb.Sprite):
            chars |= {c.char for _, c in cell.all_children() if isinstance(c, lmb.Place)}
    found = set()
    for shape in lm.shapes():
        if shape.id in chars:
            found |= {g.atlas for g in shape.graphics if g.atlas in pages}
    return found


def keep(files, earlier, kept, archives):
    """shared_files' `files`, made with Blank pictures for fighters `kept` [(slot, definition)], with their pictures
    as an earlier shared_files made them (earlier(file name) -> its bytes, or None): their texture page in each
    layout, their two big portraits and three HUD pictures (by place), as they are (BC3 blocks and all). Lost
    when the earlier ones lack any of them or have them at other sizes."""
    if not kept:
        return files
    for i, key, tkey in layout_entries(archives):
        name, pages_name = 'keys/%08x.bin' % key, 'keys/%08x.add' % tkey
        if pages_name not in files:
            continue
        lm, pages = lmb.Lmb.read(files[name]), nut.read(files[pages_name])
        textures = {t['gidx']: t for t in pages['textures']}
        before = None
        for slot, d in kept:
            mine = fighter_pages(lm, d.CODE, textures)
            if not mine:
                continue
            if before is None:
                old_lm, old_pages = earlier(name), earlier(pages_name)
                if old_lm is None or old_pages is None:
                    raise Lost(d, 'layout %08x' % key)
                old_textures = {t['gidx']: t for t in nut.read(old_pages)['textures']}
                before = lmb.Lmb.read(old_lm), old_textures
            theirs = fighter_pages(before[0], d.CODE, before[1])
            if len(mine) != 1 or len(theirs) != 1:
                raise Lost(d, 'its page of layout %08x' % key)
            new, old = textures[mine.pop()], before[1][theirs.pop()]
            if (new['fmt'], new['w'], new['h'], len(new['mips'])) != (old['fmt'], old['w'], old['h'], len(old['mips'])):
                raise Lost(d, 'its page of layout %08x at %dx%d, now %dx%d' % (key, old['w'], old['h'], new['w'],
                                                                              new['h']))
            new['mips'] = old['mips']
        files[pages_name] = nut.write(pages)
    # the big portraits: two frames per place after the title's (Paul's own for a place no fighter had)
    title = archives.read(PORTRAITS)
    first = len(container_frames(title))
    name = 'keys/%08x.bin' % PORTRAITS
    old = earlier(name)
    frames = [files[name][o:o + s] for o, s in container_frames(files[name])]
    old_frames = [old[o:o + s] for o, s in container_frames(old)] if old else []
    paul = [title[o:o + s] for o, s in container_frames(title)[:2]]
    for slot, d in kept:
        at = first + 2 * slot
        theirs = old_frames[at:at + 2]
        if len(theirs) < 2 or theirs == paul:
            raise Lost(d, 'its big portraits')
        frames[at:at + 2] = theirs
    files[name] = with_frames(title, frames[first:])
    # the HUD's three per place
    name = 'keys/%08x.add' % HUD
    old = earlier(name)
    pages = nut.read(files[name])
    old_textures = nut.read(old)['textures'] if old else []
    for slot, d in kept:
        for at in range(3 * slot, 3 * slot + 3):
            if at >= len(old_textures) or (old_textures[at]['w'], old_textures[at]['h']) != (
                    pages['textures'][at]['w'], pages['textures'][at]['h']):
                raise Lost(d, 'its HUD pictures')
            pages['textures'][at]['mips'] = old_textures[at]['mips']
    files[name] = nut.write(pages)
    return files
