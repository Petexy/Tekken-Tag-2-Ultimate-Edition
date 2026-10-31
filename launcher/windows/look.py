"""How the Windows launcher looks: as the Linux launcher (launcher/app/widgets.cpp), in Tk.

Its colours are the Linux launcher's, dark as it is. Rounded shapes and icons are drawn here
as small PNGs, which Tk 8.6 shows with their transparency, so nothing beyond Python's own
library and Tk is needed. Sizes are given at 96 DPI and scaled to the screen's (px).
"""
import base64
import ctypes
import math
import struct
import sys
import tkinter as tk
import zlib
from tkinter import font as tkfont, ttk

# The Linux launcher's colours, as GTK draws them dark.
WINDOW, HEADER, HEADER_LINE = '#212123', '#2c2c2e', '#171718'
CARD, CARD_LINE = '#2a2a2b', '#38383a'
LIST, LIST_LINE, ROW_LINE = '#303031', '#434344', '#3a3a3b'
TEXT, DIM, FAINT = '#ffffff', '#b9b9ba', '#8a8a8c'
BUTTON, BUTTON_HOVER, BUTTON_PRESSED, BUTTON_LINE = '#3a3a3b', '#454547', '#505052', '#4a4a4c'
ACCENT, ACCENT_HOVER, ACCENT_PRESSED, FOCUS = '#15529c', '#1b61b5', '#11457f', '#3584e4'
OK, WARN, BAD = '#3ad08c', '#f0b72f', '#f66151'
PILLS = {'ok': ('#2a4539', OK), 'warn': ('#4f4329', WARN), 'bad': ('#4c2b2b', BAD), 'neutral': ('#414143', '#e6e6e6')}
BANNER_RED, BANNER_MID = '#7a1c20', '#411e22'
NOTICE, NOTICE_LINE, NOTICE_ICON = '#222d3b', '#2c5288', '#7fb0f0'
TASK, TASK_LINE, LOG = '#2a2a2c', '#3b3b3d', '#19191a'
SWITCH_OFF, KEYCAP, KEYCAP_LINE = '#4a4a4c', '#3c3c3d', '#5a5a5c'
RED, WHITE = '#e01b24', '#f2f2f2'
SURFACES = {'window': WINDOW, 'header': HEADER, 'card': CARD, 'list': LIST, 'notice': NOTICE, 'task': TASK}


def dpi_aware():
    """Sharp text on a scaled screen: otherwise Windows stretches the window's picture."""
    if sys.platform != 'win32': return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except Exception: pass


def dark_title_bar(window):
    """The window's own title bar dark too (Windows 10 1809 and newer; elsewhere nothing changes)."""
    if sys.platform != 'win32': return
    try:
        window.update_idletasks()
        handle = ctypes.windll.user32.GetParent(window.winfo_id())
        on = ctypes.c_int(1)
        for attribute in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE (19 before Windows 10 20H1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, attribute, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except Exception:
        pass


def rgb(color):
    return int(color[1:3], 16) / 255, int(color[3:5], 16) / 255, int(color[5:7], 16) / 255


def mix(a, b, amount):
    """`a` moved `amount` (0 to 1) towards `b`."""
    x, y = rgb(a), rgb(b)
    return '#%02x%02x%02x' % tuple(round((p + (q - p) * amount) * 255) for p, q in zip(x, y))


# ---------------------------------------------------------------- drawing

def png(width, height, rgba):
    """`rgba` (4 bytes a pixel, rows top to bottom) as a PNG, base64 for PhotoImage(data=...)."""
    stride = width * 4
    rows = b''.join(b'\0' + rgba[y * stride:(y + 1) * stride] for y in range(height))
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return base64.b64encode(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


class Painter:
    """A small RGBA picture of anti-aliased shapes: each polygon is filled over what is there
    (or cuts it away), four rows of samples a pixel, exact across."""
    SAMPLES = 4

    def __init__(self, width, height):
        self.width, self.height = width, height
        n = width * height
        self.r, self.g, self.b, self.a = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n   # premultiplied

    def coverage(self, polygon):
        w, ss, cover = self.width, self.SAMPLES, {}
        edges = [(x0, y0, x1, y1) for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]) if y0 != y1]
        if not edges: return cover
        top = max(0, int(min(p[1] for p in polygon) * ss))
        bottom = min(self.height * ss, int(max(p[1] for p in polygon) * ss) + 1)
        for sy in range(top, bottom):
            y = (sy + 0.5) / ss
            xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0) for x0, y0, x1, y1 in edges if (y0 <= y) != (y1 <= y))
            base = (sy // ss) * w
            for i in range(0, len(xs) - 1, 2):
                a, b = max(xs[i], 0.0), min(xs[i + 1], float(w))
                if b <= a: continue
                ia, ib = int(a), int(b)
                if ia == ib:
                    cover[base + ia] = cover.get(base + ia, 0.0) + (b - a) / ss
                    continue
                cover[base + ia] = cover.get(base + ia, 0.0) + (ia + 1 - a) / ss
                for x in range(ia + 1, ib): cover[base + x] = cover.get(base + x, 0.0) + 1 / ss
                if ib < w: cover[base + ib] = cover.get(base + ib, 0.0) + (b - ib) / ss
        return cover

    def fill(self, polygon, color, alpha=1.0):
        cr, cg, cb = rgb(color)
        for i, c in self.coverage(polygon).items():
            k = min(c, 1.0) * alpha
            self.r[i] = cr * k + self.r[i] * (1 - k)
            self.g[i] = cg * k + self.g[i] * (1 - k)
            self.b[i] = cb * k + self.b[i] * (1 - k)
            self.a[i] = k + self.a[i] * (1 - k)

    def cut(self, polygon):
        for i, c in self.coverage(polygon).items():
            k = 1 - min(c, 1.0)
            self.r[i] *= k; self.g[i] *= k; self.b[i] *= k; self.a[i] *= k

    def stroke(self, points, width, color, closed=False):
        """A line through `points`, `width` wide, with round joins and ends."""
        pairs = list(zip(points, points[1:] + (points[:1] if closed else [])))
        for (x0, y0), (x1, y1) in pairs:
            length = math.hypot(x1 - x0, y1 - y0) or 1
            dx, dy = (y0 - y1) / length * width / 2, (x1 - x0) / length * width / 2
            self.fill([(x0 + dx, y0 + dy), (x1 + dx, y1 + dy), (x1 - dx, y1 - dy), (x0 - dx, y0 - dy)], color)
        for x, y in points: self.fill(circle(x, y, width / 2), color)

    def photo(self):
        out = bytearray(self.width * self.height * 4)
        for i, a in enumerate(self.a):
            if a <= 0: continue
            out[i * 4:i * 4 + 4] = bytes((round(min(self.r[i] / a, 1) * 255), round(min(self.g[i] / a, 1) * 255),
                                          round(min(self.b[i] / a, 1) * 255), round(min(a, 1) * 255)))
        return tk.PhotoImage(data=png(self.width, self.height, bytes(out)))


def circle(cx, cy, r):
    n = max(16, int(r * 5))
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rounded(x0, y0, x1, y1, r):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r == 0: return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    out, steps = [], max(4, int(r * 2))
    for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(steps + 1):
            t = math.radians(start + 90 * i / steps)
            out.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return out


def turned(points, quarter, centre=8):
    """`points` turned clockwise by `quarter` quarters round the box's centre."""
    for _ in range(quarter % 4): points = [(2 * centre - y, x) for x, y in points]
    return points


def draw_icon(p, name, s, color):
    """The launcher's icons in a box 16 units wide (scaled by `s`), as the GTK theme's symbolic ones."""
    S = lambda pts: [(x * s, y * s) for x, y in pts]
    if name == 'play':
        p.fill(S([(4.4, 2.6), (13.4, 8), (4.4, 13.4)]), color)
    elif name == 'settings':
        for k in range(8):
            t = math.radians(k * 45)
            c, d = math.cos(t), math.sin(t)
            pts = [(8 + c * r - d * w, 8 + d * r + c * w) for r, w in ((4.2, -1.35), (7.4, -1.1), (7.4, 1.1), (4.2, 1.35))]
            p.fill(S(pts), color)
        p.fill(S(circle(8, 8, 5.3)), color)
        p.cut(S(circle(8, 8, 2.1)))
    elif name == 'back':
        p.stroke(S([(10.2, 2.8), (5, 8), (10.2, 13.2)]), 1.9 * s, color)
    elif name == 'refresh':
        arc = [(8 + 5.4 * math.cos(math.radians(a)), 8 + 5.4 * math.sin(math.radians(a))) for a in range(-50, 236, 15)]
        p.stroke(S(arc), 1.8 * s, color)
        p.fill(S([(13.9, 0.9), (14.6, 7.2), (8.6, 4.6)]), color)
    elif name == 'update':
        p.stroke(S([(8, 1.8), (8, 8.2)]), 1.9 * s, color)
        p.fill(S([(3.9, 6.4), (12.1, 6.4), (8, 10.9)]), color)
        p.stroke(S([(2.4, 10.2), (2.4, 13.6), (13.6, 13.6), (13.6, 10.2)]), 1.8 * s, color)
    elif name == 'folder':
        p.fill(S(rounded(1.2, 2.6, 7.6, 6.4, 1.2)), color)
        p.fill(S(rounded(1.2, 4.4, 14.8, 13.6, 1.6)), color)
    elif name == 'info':
        p.fill(S(circle(8, 8, 7)), color)
        p.cut(S(circle(8, 8, 5.5)))
        p.fill(S(circle(8, 4.9, 1.05)), color)
        p.fill(S(rounded(7.15, 6.9, 8.85, 11.8, 0.5)), color)
    elif name == 'warning':
        p.fill(S([(8, 1.2), (15.2, 14.4), (0.8, 14.4)]), color)
        p.cut(S(rounded(7.15, 5.3, 8.85, 10.4, 0.5)))
        p.cut(S(circle(8, 12.2, 1.05)))
    elif name in ('expanded', 'collapsed'):
        p.fill(S(turned([(4, 6), (12, 6), (8, 11)], 0 if name == 'expanded' else 3)), color)


def draw_input(p, name, s):
    """The Wii U GamePad's inputs, in a box 20 units wide, as launcher/app/icons/ttt2-input-*.svg."""
    S = lambda pts: [(x * s, y * s) for x, y in pts]
    group, _, which = name.partition('_')
    quarter = {'up': 0, 'right': 1, 'down': 2, 'left': 3}
    if group == 'dpad':
        p.fill(S(rounded(6.8, 1.2, 13.2, 18.8, 1.6)), WHITE)
        p.fill(S(rounded(1.2, 6.8, 18.8, 13.2, 1.6)), WHITE)
        p.fill(S(turned([(7.6, 2.0), (12.4, 2.0), (12.4, 7.2), (10, 9.4), (7.6, 7.2)], quarter[which], 10)), RED)
    elif group == 'face':
        spots = {'top': (10, 3.6), 'bottom': (10, 16.4), 'left': (3.6, 10), 'right': (16.4, 10)}
        for spot, (x, y) in spots.items(): p.fill(S(circle(x, y, 3.1)), RED if spot == which else WHITE)
    elif group == 'stick':
        p.fill(S(circle(10, 10, 8.8)), WHITE)
        p.fill(S(turned([(10, 3.2), (15.2, 9.2), (12.2, 9.2), (12.2, 16.2), (7.8, 16.2), (7.8, 9.2), (4.8, 9.2)],
                        quarter[which], 10)), RED)
    elif name in ('plus', 'minus', 'home'):
        p.fill(S(circle(10, 10, 8.8)), WHITE)
        if name != 'home': p.cut(S(rounded(5.2, 9.0, 14.8, 11.0, 0.6)))
        if name == 'plus': p.cut(S(rounded(9.0, 5.2, 11.0, 14.8, 0.6)))
        if name == 'home': p.cut(S([(10, 4.6), (15.4, 9.6), (13.8, 9.6), (13.8, 14.8), (6.2, 14.8), (6.2, 9.6), (4.6, 9.6)]))
    else:                                   # (l, r, zl, zr: the letters are the label's text over it)
        p.fill(S(rounded(1.2, 4.2, 18.8, 15.8, 3.2)), WHITE)


# ---------------------------------------------------------------- the look

class Look:
    """Fonts, pictures and ttk styles for one window, at its screen's scale."""

    def __init__(self, root):
        self.root = root
        self.scale = max(1.0, root.winfo_fpixels('1i') / 96)
        self.images = {}
        families = set(tkfont.families(root))
        sans = next((f for f in ('Segoe UI', 'Inter', 'Cantarell', 'Noto Sans', 'DejaVu Sans', 'Tahoma')
                     if f in families), 'TkDefaultFont')
        mono = next((f for f in ('Cascadia Mono', 'Consolas', 'Noto Sans Mono', 'DejaVu Sans Mono', 'Courier New')
                     if f in families), 'TkFixedFont')
        f = lambda size, *style: (sans, -self.px(size), *style)
        self.fonts = dict(normal=f(14), bold=f(14, 'bold'), small=f(13), small_bold=f(12, 'bold'),
                          title=f(26, 'bold'), edition=f(12.5, 'bold'), section=f(15, 'bold'), card=f(16, 'bold'),
                          header=f(14, 'bold'), notice=f(14, 'bold'), task=f(14, 'bold'), key=f(13, 'bold'),
                          mono=(mono, -self.px(13)), log=(mono, -self.px(12)))
        root.configure(bg=WINDOW)
        root.option_add('*Font', self.fonts['normal'])
        for option, value in (('background', LIST), ('foreground', TEXT), ('selectBackground', ACCENT),
                              ('selectForeground', TEXT)):
            root.option_add('*TCombobox*Listbox.' + option, value)
        self.style = ttk.Style(root)
        self.style.theme_use('clam')
        self._styles()

    def px(self, n):
        return max(1, round(n * self.scale))

    # -- pictures

    def _photo(self, key, width, height, draw):
        if key not in self.images:
            p = Painter(width, height)
            draw(p)
            self.images[key] = p.photo()
        return self.images[key]

    def icon(self, name, size=16, color=TEXT):
        n = self.px(size)
        return self._photo(('icon', name, n, color), n, n, lambda p: draw_icon(p, name, n / 16, color))

    def input_icon(self, name, size=20):
        n = self.px(size)
        return self._photo(('input', name, n), n, n, lambda p: draw_input(p, name, n / 20))

    def frame_image(self, radius, fill, line=None, ring=None, bottom=0, middle=32):
        """A rounded box for 9-slice backgrounds: its border is (r, r, r, r + bottom). ttk tiles the
        middle and the edges, one copy of the picture's middle at a time: a large one keeps that a
        few copies a widget."""
        r = self.px(radius)
        size = 2 * r + 2 + middle + bottom
        def draw(p):
            inset = 0.0
            for color, width in ((ring, self.px(2)), (line, 1)):
                if color:
                    p.fill(rounded(inset, inset, size - inset, size - inset, r - inset), color)
                    inset += width
            p.fill(rounded(inset, inset, size - inset, size - inset - (bottom if line else 0), r - inset), fill)
        return self._photo(('frame', r, fill, line, ring, bottom, middle), size, size, draw), (r + 1, r + 1, r + 1, r + 1 + bottom)

    # -- styles

    def _element(self, name, images, border):
        """A 9-slice element of state images: [(state, (image, border)) ...] with the default first."""
        default = images[0][1][0]
        specs = [(state, image) for state, (image, _) in images[1:]]
        # (At least its corners, else as large as its picture.)
        self.style.element_create(name, 'image', default, *specs, border=border, sticky="nsew", padding=0,
                                  width=border[0] + border[2] + 1, height=border[1] + border[3] + 1)

    def _styles(self):
        st, px = self.style, self.px
        st.configure('.', background=WINDOW, foreground=TEXT, font=self.fonts['normal'], borderwidth=0,
                     focuscolor=FOCUS, troughcolor=WINDOW)
        for surface, bg in SURFACES.items():
            st.configure(surface.capitalize() + '.TFrame', background=bg)
            # Buttons: normal, suggested (Play, Update), flat (Remove, the header's icons).
            kinds = {'normal': (BUTTON, BUTTON_HOVER, BUTTON_PRESSED, TEXT),
                     'suggested': (ACCENT, ACCENT_HOVER, ACCENT_PRESSED, TEXT),
                     'flat': (bg, mix(bg, '#ffffff', 0.08), mix(bg, '#ffffff', 0.14), TEXT)}
            for kind, (fill, hover, pressed, fg) in kinds.items():
                name = '%s.%s.TButton' % (kind.capitalize(), surface.capitalize())
                frames = [(None, self.frame_image(7, fill)), ('disabled', self.frame_image(7, mix(fill, bg, 0.45))),
                          ('pressed', self.frame_image(7, pressed)), ('active', self.frame_image(7, hover)),
                          ('focus', self.frame_image(7, fill, ring=FOCUS))]
                self._element(name + '.bg', frames, frames[0][1][1])
                st.layout(name, [(name + '.bg', {'sticky': 'nsew', 'children': [('Button.padding', {
                    'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
                st.configure(name, background=bg, foreground=fg, padding=(px(14), px(6)), anchor='center',
                             font=self.fonts['bold' if kind == 'suggested' else 'normal'])
                # (clam gives its own light colour behind a button in these states: the surface's instead.)
                states = [(state, bg) for state in ('disabled', 'pressed', 'active', 'focus')]
                st.map(name, foreground=[('disabled', mix(fg, bg, 0.55))], background=states)
                icon_name = 'Icon' + name
                st.layout(icon_name, st.layout(name))
                st.configure(icon_name, background=bg, foreground=fg, padding=(px(8), px(7)), anchor='center')
                st.map(icon_name, background=states)
            for kind, (fill, fg) in PILLS.items():
                name = '%s.%s.Pill.TLabel' % (kind.capitalize(), surface.capitalize())
                image, border = self.frame_image(11, fill)
                self.style.element_create(name + '.bg', 'image', image, border=border, sticky="nsew", padding=0,
                                          width=border[0] + border[2] + 1, height=border[1] + border[3] + 1)
                st.layout(name, [(name + '.bg', {'sticky': 'nsew', 'children': [('Label.padding', {
                    'sticky': 'nsew', 'children': [('Label.label', {'sticky': 'nsew'})]})]})])
                st.configure(name, background=bg, foreground=fg, padding=(px(11), px(2)), font=self.fonts['small_bold'])
        # Rounded boxes: cards, the lists in them, the update notice, the banner's frame.
        for name, radius, fill, line, bg in (('Card', 12, CARD, CARD_LINE, WINDOW), ('List', 10, LIST, LIST_LINE, CARD),
                                             ('Notice', 12, NOTICE, NOTICE_LINE, WINDOW)):
            image, border = self.frame_image(radius, fill, line, middle=96)
            st.element_create(name + '.box', 'image', image, border=border, sticky="nsew", padding=0,
                              width=border[0] + border[2] + 1, height=border[1] + border[3] + 1)
            st.layout(name + '.TFrame', [(name + '.box', {'sticky': 'nsew'})])
            st.configure(name + '.TFrame', background=bg)
        # The keys' caps (a key's shape: a thicker edge below), and the switches.
        frames = [(None, self.frame_image(7, KEYCAP, KEYCAP_LINE, bottom=2)),
                  ('pressed', self.frame_image(7, mix(KEYCAP, '#ffffff', 0.14), KEYCAP_LINE)),
                  ('active', self.frame_image(7, mix(KEYCAP, '#ffffff', 0.07), KEYCAP_LINE, bottom=2)),
                  ('focus', self.frame_image(7, KEYCAP, FOCUS, bottom=2)),
                  ('selected', self.frame_image(7, mix(LIST, FOCUS, 0.18), FOCUS, bottom=2))]
        frames.insert(1, frames.pop())          # (picking a key shows first)
        self._element('Keycap.bg', frames, frames[0][1][1])
        st.layout('Keycap.TButton', [('Keycap.bg', {'sticky': 'nsew', 'children': [('Button.padding', {
            'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
        st.configure('Keycap.TButton', background=LIST, foreground=TEXT, padding=(px(10), px(4), px(10), px(4)),
                     font=self.fonts['key'], width=-7, anchor='center')
        st.map('Keycap.TButton', background=[(s, LIST) for s in ('disabled', 'pressed', 'active', 'focus', 'selected')])
        w, h = px(44), px(24)
        def switch(on, focus=False, disabled=False):
            def draw(p):
                track = ACCENT if on else SWITCH_OFF
                if focus: p.fill(rounded(0, 0, w, h, h / 2), FOCUS)
                inset = px(2) if focus else 0
                p.fill(rounded(inset, inset, w - inset, h - inset, h / 2 - inset), mix(track, LIST, 0.5) if disabled else track)
                knob = h / 2 - px(3)
                p.fill(circle(w - h / 2 if on else h / 2, h / 2, knob), mix(WHITE, LIST, 0.4) if disabled else WHITE)
            return self._photo(('switch', on, focus, disabled, w), w, h, draw)
        st.element_create('Switch.track', 'image', switch(False),
                          ('disabled', 'selected', switch(True, disabled=True)), ('disabled', switch(False, disabled=True)),
                          ('focus', 'selected', switch(True, True)), ('selected', switch(True)), ('focus', switch(False, True)),
                          sticky='')
        st.layout('Switch.TCheckbutton', [('Switch.track', {'sticky': ''})])
        st.configure('Switch.TCheckbutton', background=LIST, padding=0)
        st.map('Switch.TCheckbutton', background=[(s, LIST) for s in ('disabled', 'pressed', 'active', 'focus')])
        # Check boxes with a label (the outfits'): ticked, a dash for some of several (alternate), empty.
        b = px(16)
        def check(mark, focus=False, disabled=False):
            def draw(p):
                inset = px(2) if focus else 0
                if focus: p.fill(rounded(0, 0, b, b, px(5)), FOCUS)
                fill, line = (ACCENT, ACCENT) if mark else (BUTTON, BUTTON_LINE)
                if disabled: fill, line = mix(fill, LIST, 0.5), mix(line, LIST, 0.5)
                p.fill(rounded(inset, inset, b - inset, b - inset, px(4) - inset), line)
                p.fill(rounded(inset + px(1), inset + px(1), b - inset - px(1), b - inset - px(1), px(3) - inset), fill)
                white = mix(WHITE, LIST, 0.4) if disabled else WHITE
                if mark == 'on': p.stroke([(b * 0.27, b * 0.52), (b * 0.44, b * 0.69), (b * 0.74, b * 0.35)], px(2), white)
                if mark == 'some': p.fill(rounded(b * 0.27, b * 0.44, b * 0.73, b * 0.56, px(1)), white)
            return self._photo(('check', mark, focus, disabled, b), b, b, draw)
        st.element_create('Check.box', 'image', check(None),
                          ('disabled', 'alternate', check('some', disabled=True)),
                          ('disabled', 'selected', check('on', disabled=True)), ('disabled', check(None, disabled=True)),
                          ('focus', 'alternate', check('some', True)), ('alternate', check('some')),
                          ('focus', 'selected', check('on', True)), ('selected', check('on')),
                          ('focus', check(None, True)), width=b + px(7), sticky='w')
        for surface, bg in SURFACES.items():
            name = 'Check.%s.TCheckbutton' % surface.capitalize()
            st.layout(name, [('Checkbutton.padding', {'sticky': 'nsew', 'children': [
                ('Check.box', {'side': 'left', 'sticky': ''}), ('Checkbutton.label', {'side': 'left', 'sticky': 'nsew'})]})])
            st.configure(name, background=bg, foreground=TEXT, padding=0)
            st.map(name, background=[(s, bg) for s in ('disabled', 'pressed', 'active', 'focus')],
                   foreground=[('disabled', mix(TEXT, bg, 0.55))])
        # The rest from clam, recoloured.
        st.configure('TCombobox', fieldbackground=BUTTON, background=BUTTON, foreground=TEXT, arrowcolor=TEXT,
                     bordercolor=BUTTON_LINE, lightcolor=BUTTON, darkcolor=BUTTON, selectbackground=BUTTON,
                     selectforeground=TEXT, padding=(px(8), px(4)), arrowsize=px(13))
        st.map('TCombobox', fieldbackground=[('readonly', BUTTON)], foreground=[('readonly', TEXT)],
               background=[('active', BUTTON_HOVER)], bordercolor=[('focus', FOCUS)])
        st.configure('TEntry', fieldbackground=LOG, foreground=TEXT, insertcolor=TEXT, bordercolor=BUTTON_LINE,
                     lightcolor=LOG, darkcolor=LOG, padding=(px(8), px(5)))
        st.map('TEntry', bordercolor=[('focus', FOCUS)])
        # (clam's thumb is -arrowsize thick, and so the bar: the layout below has no arrows.)
        st.configure('Vertical.TScrollbar', background='#4a4a4c', troughcolor=WINDOW, bordercolor=WINDOW,
                     lightcolor='#4a4a4c', darkcolor='#4a4a4c', gripcount=0, arrowsize=px(10))
        st.configure('Log.Vertical.TScrollbar', troughcolor=LOG, bordercolor=LOG)     # (the task log's, in its box)
        st.map('Vertical.TScrollbar', background=[('active', '#5d5d5f')])
        st.layout('Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
            ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        st.configure('Horizontal.TProgressbar', background=FOCUS, troughcolor='#3a3a3c', bordercolor=TASK,
                     lightcolor=FOCUS, darkcolor=FOCUS, thickness=px(8))

    # -- widgets

    def label(self, parent, text='', kind='normal', bg=None, wrap=False, **options):
        """A line of text on its parent's surface: kind normal, bold, dim, small, path, title ...
        A wrapping one takes its parent's width (pack or grid it to fill across)."""
        fonts = dict(dim='normal', small='small', path='mono', error='normal', warn='normal', ok='normal')
        colours = dict(dim=DIM, small=DIM, path=DIM, error=BAD, warn=WARN, ok=OK, edition='#e8d4d4', note='#dcc9ca')
        settings = dict(text=text, bg=bg or surface_of(parent), fg=colours.get(kind, TEXT), justify='left', anchor='w',
                        font=self.fonts.get(fonts.get(kind, kind), self.fonts['normal']), bd=0, padx=0, pady=0)
        settings.update(options)
        widget = tk.Label(parent, **settings)
        if wrap:
            def fit(event):
                if abs(int(widget.cget('wraplength') or 0) - event.width) > 2: widget.configure(wraplength=event.width)
            widget.bind('<Configure>', fit, add='+')
        return widget

    def button(self, parent, text='', command=None, kind='normal', icon=None, surface=None, tip=None, **options):
        """A rounded button on its parent's surface; `icon` alone makes a square one."""
        surface = surface or surface_name(parent)
        style = '%s%s.%s.TButton' % ('Icon' if icon and not text else '', kind.capitalize(), surface.capitalize())
        if icon:
            colour = TEXT
            options.update(image=self.icon(icon, 16, colour), compound='left' if text else 'image')
            if text: text = ' ' + text
        widget = ttk.Button(parent, text=text, command=command, style=style, takefocus=True, **options)
        if tip: Tooltip(widget, tip, self)
        return widget

    def pill(self, parent, text, kind='neutral', tip=None):
        widget = ttk.Label(parent, text=text, style='%s.%s.Pill.TLabel' % (kind.capitalize(), surface_name(parent).capitalize()))
        if tip: Tooltip(widget, tip, self)
        return widget

    def box(self, parent, kind):
        """A rounded box (Card, List, Notice): a frame its contents go in, on its own surface."""
        widget = ttk.Frame(parent, style=kind + '.TFrame')
        widget.surface = {'Card': 'card', 'List': 'list', 'Notice': 'notice'}[kind]
        return widget

    def frame(self, parent, surface=None):
        widget = tk.Frame(parent, bg=SURFACES[surface] if surface else surface_of(parent), bd=0, highlightthickness=0)
        widget.surface = surface or surface_name(parent)
        return widget


def surface_name(widget):
    while widget is not None:
        name = getattr(widget, 'surface', None)
        if name: return name
        widget = widget.master
    return 'window'


def surface_of(widget):
    return SURFACES[surface_name(widget)]


class Tooltip:
    """Why a button cannot be pressed, and the like: shown while the pointer rests on it."""

    def __init__(self, widget, text, look):
        self.widget, self.text, self.look, self.window, self.pending = widget, text, look, None, None
        widget.bind('<Enter>', self.soon, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        widget.tooltip = self

    def soon(self, _event=None):
        self.pending = self.widget.after(600, self.show)

    def show(self):
        if not self.text or self.window: return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.configure(bg=CARD_LINE)
        tk.Label(self.window, text=self.text, bg='#1d1d1f', fg=TEXT, font=self.look.fonts['small'], justify='left',
                 wraplength=self.look.px(360), padx=self.look.px(9), pady=self.look.px(6)).pack(padx=1, pady=1)
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + self.look.px(6)
        self.window.wm_geometry('+%d+%d' % (x, y))

    def hide(self, _event=None):
        if self.pending: self.widget.after_cancel(self.pending)
        self.pending = None
        if self.window: self.window.destroy()
        self.window = None


class Page(tk.Frame):
    """A page of the window: a column at most `width` wide (760, as the Linux launcher's), in its
    middle, scrolling. Its contents go in `column`. The column is placed in the page and moved to
    scroll (a frame in a canvas, Tk's usual way, lays out many times slower under Wine). As GTK's,
    it scrolls by the wheel, its bar and PgUp/PgDn/Home/End (here the arrow keys too), and keeps
    the control Tab moves to in view. It also drags by its background, with the mouse or a finger
    (which Windows makes the mouse): GTK's drags by a finger only."""

    def __init__(self, master, look, width=760):
        super().__init__(master, bg=WINDOW, bd=0, highlightthickness=0)
        self.look, self.width, self.offset, self.steps, self.moving, self.painting = look, width, 0, 0, None, False
        self.dragging = self.target = None
        # The wheel: X11's is buttons 4 and 5 in Tk 8.6. Elsewhere those are the mouse's side buttons, back and
        # forward (Windows' Tk, and X11's from Tk 9 on, which sends the wheel as a MouseWheel).
        self.wheels = [('<MouseWheel>', None)]
        if self.tk.call('tk', 'windowingsystem') == 'x11' and float(self.getvar('tk_version')) < 9:
            self.wheels += [('<Button-4>', -1), ('<Button-5>', 1)]
        self.column = tk.Frame(self, bg=WINDOW, bd=0, highlightthickness=0)
        self.column.surface = 'window'
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.yview)
        self.take_wheel(self.bar)
        self.bind('<Configure>', self._place)
        self.column.bind('<Configure>', self._place)
        for wheel, steps in self.wheels:
            self.bind_all(wheel, lambda e, steps=steps: self._wheel(e, steps), add='+')
        for key, how in (('Prior', ('scroll', -1, 'pages')), ('Next', ('scroll', 1, 'pages')),
                         ('Up', ('scroll', -1, 'units')), ('Down', ('scroll', 1, 'units')),
                         ('Home', ('moveto', 0)), ('End', ('moveto', 1))):
            self.bind_all('<KeyPress-%s>' % key, lambda e, how=how: self._key(e, how), add='+')
        # (Sent by Tab and Shift+Tab only, tk::TabToWindow: a click never moves the page under the pointer.)
        self.bind_all('<<TraverseIn>>', lambda e: self._mine(e.widget) and self.see(e.widget), add='+')
        self.bind_all('<ButtonPress-1>', self._grab, add='+')
        self.bind_all('<B1-Motion>', self._drag, add='+')

    def _total(self):
        return self.column.winfo_reqheight() + self.look.px(24 + 32)

    def _place(self, event=None):
        px = self.look.px
        width, view = self.winfo_width(), self.winfo_height()
        column = max(min(width - 2 * px(24), px(self.width)), px(200))
        total = self._total()
        self.offset = max(0, min(self.offset, total - view))
        self.column.place(x=(width - column) // 2, y=px(24) - self.offset, width=column)
        # Over the page's edge, as GTK's: shown or not, the column keeps its width.
        if total > view > 1:
            self.bar.place(relx=1, rely=0, relheight=1, anchor='ne')
            self.bar.lift()
            self.bar.set(self.offset / total, (self.offset + view) / total)
        else:
            self.bar.place_forget()

    def yview(self, *args):
        total, view = self._total(), self.winfo_height()
        if args[0] == 'moveto': self.offset = int(float(args[1]) * total)
        elif args[0] == 'scroll':
            step = view * 0.9 if args[2] == 'pages' else self.look.px(40)
            self.offset += int(args[1]) * int(step)
        self._place()
        self._paint()

    def keep(self, offset):
        """Back at `offset` (as far as the column now reaches) once what was made again in it is laid out. Tk lays
        out an emptied box before the boxes made in it are full, and the column, short for a moment, scrolls up."""
        self.update_idletasks()
        self.offset = offset
        self._place()

    def _paint(self):
        """What a move uncovered drawn now, before more input. Tk draws when it is idle, which it
        is not while the wheel turns or the scroll bar is dragged: the uncovered stripe would show
        what was there before (white under Wine) until the scrolling stops."""
        if self.painting: return
        self.painting = True
        try:
            if sys.platform == 'win32':
                # (Its paint messages now, not once the queue is empty: RDW_UPDATENOW | RDW_ALLCHILDREN.)
                ctypes.windll.user32.RedrawWindow(self.winfo_id(), None, None, 0x0100 | 0x0080)
            self.update()
        except tk.TclError:
            pass
        finally:
            self.painting = False

    def _shown(self):
        return self.winfo_ismapped() and self.bar.winfo_ismapped()

    def _mine(self, widget):
        """Whether `widget` (a name for those Tk makes itself) is in the page, and not a list's popdown."""
        name = str(widget)
        return (name == str(self) or name.startswith(str(self) + '.')) and '.popdown' not in name

    def _scroll(self, steps):
        # (The wheel's steps of a frame's time moved at once: one move a frame at most.)
        if not self._shown(): return
        self.steps += steps
        if not self.moving: self.moving = self.after(16, self._move)

    def _move(self):
        steps, self.steps, self.moving = self.steps, 0, None
        if self.target is not None:
            self.offset, self.target = self.target, None
            self._place()
            self._paint()
        if steps: self.yview('scroll', steps * 2, 'units')

    def _wheel(self, event, steps=None):
        if not self._mine(event.widget): return       # (the log's, the header's: not the page's)
        # (Tk 8.6 on Windows sends whole notches of 120, several in one when the wheel spins.)
        notches = max(1, abs(event.delta) // 120)
        self._scroll(steps or (-notches if event.delta > 0 else notches))

    def take_wheel(self, widget):
        """The wheel over `widget`, in the page, scrolls the page only: not the bar's own steps on top
        of the page's, nor a list's choice, which would change as the pointer passed over it."""
        for wheel, steps in self.wheels:
            widget.bind(wheel, lambda e, steps=steps: self._wheel(e, steps) or 'break')

    def _key(self, event, how):
        # (Not while typing or choosing in a list, whose keys they are: a Combobox is an Entry. Nor in another window:
        # a list's popdown, or Tk's own file dialog or message box on X11. A keycap waiting for a key takes it first.)
        widget = event.widget
        if (self._shown() and str(self.tk.call('winfo', 'toplevel', widget)) == str(self.winfo_toplevel())
                and not isinstance(widget, (tk.Text, tk.Entry, ttk.Entry))):
            self.yview(*how)

    def see(self, widget):
        """Scrolls so that `widget` (in the column) is in view, a little in from the page's edges."""
        if not self._shown(): return
        # (Where it is in the column, at the page's offset: not where the column is now, which moves once Tk is idle.
        # A second Tab handled while the first one's move is painted would move the page twice as far.)
        y = widget.winfo_rooty() - self.column.winfo_rooty() + self.look.px(24) - self.offset
        height, view, margin = widget.winfo_height(), self.winfo_height(), self.look.px(12)
        if y < margin: self.offset += y - margin
        elif y + height > view - margin: self.offset += min(y + height - (view - margin), y - margin)
        else: return
        self._place()
        self._paint()

    def _grab(self, event):
        # (On its background: a label, a box, the banner. A control keeps its own drag.)
        widget = event.widget
        background = isinstance(widget, (tk.Frame, tk.Label, tk.Canvas, ttk.Frame, ttk.Label))
        self.dragging = (event.y_root, self.offset, False) if self._shown() and self._mine(widget) and background else None

    def _drag(self, event):
        if not self.dragging: return
        y, offset, moving = self.dragging
        # (From a few pixels away only, as GTK's: a click on a label that wobbles a pixel is not a drag.)
        if not moving and abs(event.y_root - y) <= self.look.px(4): return
        self.dragging = y, offset, True
        self.target = offset - (event.y_root - y)
        if not self.moving: self.moving = self.after(16, self._move)     # (as the wheel's: a move a frame)


class Banner(tk.Canvas):
    """The game's name on its red banner, as the Linux launcher's: the game's icon once installed."""

    def __init__(self, master, look, note):
        super().__init__(master, bg=WINDOW, bd=0, highlightthickness=0, height=look.px(150))
        self.look, self.note, self.icon = look, note, None
        self.bind('<Configure>', lambda e: self.draw())

    def set_icon(self, image):
        self.icon = image
        self.draw()

    def draw(self):
        px, look = self.look.px, self.look
        width = self.winfo_width()
        if width < 10: return
        self.delete('all')
        x0 = px(24) + (self.icon.width() + px(20) if self.icon else 0)
        text_width = max(px(120), width - x0 - px(24))
        note = self.create_text(x0, 0, text=self.note, anchor='nw', width=text_width, font=look.fonts['small'], fill='#dcc9ca')
        note_height = self.bbox(note)[3] - self.bbox(note)[1]
        height = px(22) + px(34) + px(22) + px(6) + note_height + px(22)
        self.delete(note)
        self.configure(height=height)
        # The red, fading to the window's colour across (as the Linux banner's gradient), with its corners rounded.
        steps = max(2, width // 3)
        for i in range(steps):
            t = i / (steps - 1)
            colour = mix(BANNER_RED, BANNER_MID, t / 0.55) if t < 0.55 else mix(BANNER_MID, WINDOW, min(1, (t - 0.55) / 0.30))
            x = round(width * i / steps)
            self.create_rectangle(x, 0, round(width * (i + 1) / steps), height, fill=colour, outline='')
        corner = self._corner()
        n = corner.width()
        for x, y, part in ((0, 0, 'tl'), (width - n, 0, 'tr'), (0, height - n, 'bl'), (width - n, height - n, 'br')):
            self.create_image(x, y, image=self._corner(part), anchor='nw')
        if self.icon: self.create_image(px(24), height // 2, image=self.icon, anchor='w')
        y = px(20)
        title = self.create_text(x0, y, text='Tekken Tag Tournament 2', anchor='nw', font=look.fonts['title'], fill=TEXT)
        y = self.bbox(title)[3] + px(2)
        edition = self.create_text(x0, y, text=' '.join('ULTIMATE EDITION').replace('   ', '    '),
                                   anchor='nw', font=look.fonts['edition'], fill='#e8d4d4')
        y = self.bbox(edition)[3] + px(8)
        self.create_text(x0, y, text=self.note, anchor='nw', width=text_width, font=look.fonts['small'], fill='#dcc9ca')

    def _corner(self, part='tl'):
        """A rounded corner of the banner: the window's colour outside its curve, nothing inside."""
        r = self.look.px(14)
        def draw(p):
            p.fill([(0, 0), (r, 0), (r, r), (0, r)], WINDOW)
            cx, cy = {'tl': (r, r), 'tr': (0, r), 'bl': (r, 0), 'br': (0, 0)}[part]
            p.cut(circle(cx, cy, r))
        return self.look._photo(('corner', part, r), r, r, draw)
