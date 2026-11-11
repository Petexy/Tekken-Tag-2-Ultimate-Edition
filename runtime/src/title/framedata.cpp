// Practice: frame data and combat information, as Tekken 8's Practice shows
// it: a panel for each side at the bottom of the screen, the player's
// attacks' damage and properties above, frame data, posture and distance
// below. They look like the title's own boxes (the main menu's player box:
// dark glass, a teal rim, chamfered corners), drawn here once as a
// nine-slice, with the title's fonts: the plain one for labels, the bold
// italic one for values. They show over the title's image (gpu/overlay.h)
// only while Practice's fighters' frames run, so not in the pause menu.
// The pause menu's ULTIMATE SETTINGS row
// (title/practice.cpp) opens a submenu of the title's own kind with their
// settings: the panels at all, 1P's, 2P's, and, off to begin with, the
// advantage colours, the hitboxes and the camera from above (see the
// hitboxes' and TOP CAMERA's sections). The advantage colours: as in
// Tekken 8, from a hit or a block until both
// fighters can act again, the one ahead in frames is blue, the one behind
// red. The title colours a fighter by a colour it multiplies the fighter's
// with (four floats, white as it is; the accessor sub_04E1A0FC, r3 the
// fighter: its own at +7840, or, with HIT ANALYSIS on, a blue one while it
// can be hit); the accessor returns one of two colours here instead.
//
// Everything comes from the fighters' state the title keeps (player
// structs, 10592 bytes each from 0x10884B50), read after each fighters'
// frame:
// - the move in play (+280) and its frame (+212); a move record holds its
//   first and last active frames (+0x64, +0x68: the startup and the active
//   window) and its hit level (+0x10, second byte: 1 low, 2 mid, 4 special
//   low, 5 high);
// - a frame's hit events (+1152, for the frame of the hit only), on the
//   fighter hit: 0x800000 an attack hit it, 0x20000000 it blocked,
//   0x80000 a counter hit (0x20000 one the Counter setting makes); its
//   bits 12-15 hold the state of its reaction for as long as it lasts (6
//   the hit's frame, 1 after it, 7 from the frame it meets the wall, 8 the
//   floor). +2704 bit 0x10000 marks a punish (it was hit during its own
//   attack's recovery), for the same frame. The title's HIT INFO shows
//   COUNTER, PUNISH and WALL HIT from these; its CLEAN marker was not found,
//   so that badge stays dim;
// - damage: a hit's base damage (+1180), the combo's damage so far as dealt
//   (+488, after the title's multipliers: 120% for a solo fighter, 120%
//   more on a counter hit), health (+96) and its recoverable ceiling (+100,
//   equal to it for a solo fighter);
// - the posture (+872, low byte: 1-3 standing, 5-7 crouching, 8/9 getting
//   up, 12/13/15 down, 14 juggled, 24-27 airborne);
// - whether the fighter can act (+1160 bit 0x100: lit from the first frame
//   its move can be cancelled into any other, or the first frame back in
//   its neutral move), and the move's last frame before that (+522, 16
//   bits). The frame advantage after a hit or a block is the number of
//   frames the defender becomes free after the attacker: Jun's jab +8 on
//   hit and +1 on block, as Tekken's frame data has it. It shows on the
//   frame of the hit, from both moves' last frames (the defender's being
//   its hit or block reaction's), and is checked by counting until both
//   are free, which corrects it where the defender goes on through other
//   moves (knocked down).
// Positions (+0, +8) are in millimetres.
//
// The input history, after Tekken 8's, takes the place of the title's
// COMMAND HISTORY bar (title/practice.cpp keeps the title's HUD from
// showing that) while its setting is on: a column on the left, the newest
// input on top, each row an input held (its direction and buttons, drawn
// with the title's own icons) and the frames it was held. The player's
// fighter's buttons are at +2032 (1 to 4 held: 0x200 to 0x1000) and its
// direction at +2036 (bit n for numpad direction n, forward being 6, as it
// faces); the player's side is the one the GamePad drives (+2052, its raw
// buttons, nonzero while it holds any). A fighter's own moveset is at
// +136 (+272 is the one in use: a fighter hit plays the attacker's
// reactions, from the attacker's moveset).

#include "title/framedata.h"
#include "title/gauge.h"
#include "title/warp.h"

#include "gpu/overlay.h"
#include "host/window.h"
#include "title/draw.h"
#include "title/font.h"
#include "title/image.h"
#include "title/presentation.h"

#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

namespace cafe::title::framedata {
namespace {

using gpu::overlay::Quad;

// ------------------------------------------------------------- the fighters

constexpr uint32_t kX = 0, kZ = 8, kMoveset = 136, kMove = 280, kFrame = 212; // its own moveset (+272: the one in use)
constexpr uint32_t kHealth = 96, kHealthCeiling = 100; // 16 bits
constexpr uint32_t kComboDamage = 488, kHitDamage = 1180;
constexpr uint32_t kEvents = 1152, kHit = 0x800000, kBlocked = 0x20000000, kCounter = 0x80000 | 0x20000;
constexpr uint32_t kKind = 0xF000, kWall = 0x7000;
constexpr uint32_t kHitFlags = 2704, kPunish = 0x10000;
constexpr uint32_t kCancel = 1160, kFree = 0x100, kLastBusyFrame = 522;
constexpr uint32_t kPosture = 872;
constexpr uint32_t kButtonsHeld = 2032, kDirection = 2036, kPadButtons = 2052;
constexpr uint32_t kMoveHitLevel = 0x10, kMoveFirstActive = 0x64, kMoveLastActive = 0x68;
constexpr uint32_t kPracticeSettings = 0x108D1C60;              // sub_04F1BD58
constexpr uint32_t kCommandHistory = 48;                         // its HUD Information row (1: on)
constexpr uint32_t kMeasureFrames = 300; // how long an advantage is waited for

struct Fighter {
    uint32_t player = 0, moveset = 0, move = 0, frame = 0;
    uint32_t first_active = 0, last_active = 0, level = 0; // of the move
    uint32_t events = 0, hit_flags = 0, cancel = 0, posture = 0;
    int last_busy = 0; // the move's last frame before it can act
    uint32_t direction = 5, buttons = 0, pad = 0; // numpad direction, 1-4 held (bits 0-3), raw buttons
    int health = 0, ceiling = 0, combo = 0, hit_damage = 0;
    float x = 0, z = 0;
};

float ldf(uint8_t* base, uint32_t address) {
    const uint32_t v = ppc::ld32(base, address);
    float f;
    std::memcpy(&f, &v, sizeof(f));
    return f;
}

Fighter read(uint8_t* base, uint32_t p) {
    Fighter f;
    f.player = p;
    f.moveset = ppc::ld32(base, p + kMoveset);
    f.move = ppc::ld32(base, p + kMove);
    f.frame = ppc::ld32(base, p + kFrame);
    if (f.move) {
        f.first_active = ppc::ld32(base, f.move + kMoveFirstActive);
        f.last_active = ppc::ld32(base, f.move + kMoveLastActive);
        f.level = (ppc::ld32(base, f.move + kMoveHitLevel) >> 8) & 0xFF;
    }
    f.events = ppc::ld32(base, p + kEvents);
    f.hit_flags = ppc::ld32(base, p + kHitFlags);
    f.cancel = ppc::ld32(base, p + kCancel);
    f.last_busy = static_cast<int16_t>(ppc::ld16(base, p + kLastBusyFrame));
    const uint32_t direction = ppc::ld32(base, p + kDirection);
    for (uint32_t n = 1; n <= 9; ++n) {
        if (direction & (1u << n)) f.direction = n;
    }
    f.buttons = (ppc::ld32(base, p + kButtonsHeld) >> 9) & 0xF;
    f.pad = ppc::ld32(base, p + kPadButtons);
    f.posture = ppc::ld32(base, p + kPosture) & 0xFF;
    f.health = static_cast<int16_t>(ppc::ld16(base, p + kHealth));
    f.ceiling = static_cast<int16_t>(ppc::ld16(base, p + kHealthCeiling));
    f.combo = static_cast<int32_t>(ppc::ld32(base, p + kComboDamage));
    f.hit_damage = static_cast<int32_t>(ppc::ld32(base, p + kHitDamage));
    f.x = ldf(base, p + kX);
    f.z = ldf(base, p + kZ);
    return f;
}

// The hit levels Jun's moveset has (the fourth: her crouching jabs).
const char* level_name(uint32_t level) {
    switch (level) {
    case 0: return "";
    case 1: return "Low";
    case 2: return "Mid";
    case 4: return "S.Low";
    case 5: return "High";
    default: return "---";
    }
}

const char* posture_name(uint32_t posture) {
    switch (posture) {
    case 5: case 6: case 7: case 11: return "Crouching";
    case 8: case 9: case 12: case 13: case 15: return "Down";
    case 14: case 24: case 25: case 26: case 27: return "Airborne";
    default: return "Standing";
    }
}

bool grounded_or_juggled(uint32_t posture) { return posture >= 12 && posture <= 15; }

// ------------------------------------------------------------- what the panels show

// A side's figures: its attacks on the other.
struct Side {
    int total = 0, max_combo = 0;
    uint32_t level = 0;                              // hit level of its last attack
    uint32_t startup = 0, first = 0, last = 0;       // and its frames (0: none yet)
    int damage = -1, multiplier = 0;                 // its last hit: as dealt, % of its base
    int recoverable = 0, recoverable_share = 0;      // of that, recoverable (% of the hit)
    bool clean = false, counter = false, punish = false, wall = false;
    bool in_combo = false; // its hit put the other in a reaction it has not left
    bool advantage_known = false;
    int advantage = 0;
    const char* note = "";
};

// After a hit or block: the frames until each fighter is free again.
struct Measure {
    bool on = false;
    uint32_t frames = 0;
    int attacker = 0;
    int free_at[2] = {-1, -1};
    bool down = false;
    const char* note = "";
};

// An input held, and for how many frames.
struct Input {
    uint32_t direction = 5, buttons = 0, frames = 0;
};
constexpr size_t kHistoryRows = 27;

// An attack's line segment as tested, in the world (by side `side`), and
// the frames since.
struct AttackLine {
    float ends[6] = {};
    int side = 0;
    uint32_t age = 0;
};
constexpr uint32_t kBodySphereCount = 14;
constexpr uint32_t kAttackLinger = 20; // frames an attack's line stays, fading, after it was tested

// The fighters the advantage colours show on, until a time.
struct Colours {
    uint32_t ahead = 0, behind = 0;
    double until = 0;
};

struct Session {
    bool failed = false;
    std::vector<Input> history; // newest last
    int player = 0;             // the side the GamePad drives
    uint32_t settings[kSettings] = {1, 1, 1, 0, 0, 0, 0};
    Side sides[2];
    Fighter previous[2];
    bool have_previous = false;
    Measure measure;
    Colours colours;
    // The camera from above as it moves: its middle, the fighters' line
    // (a unit vector) and its height, eased towards where they are.
    struct TopCamera {
        bool placed = false;
        float x = 0, z = 0, ax = 1, az = 0, height = 0;
    } top;
    std::vector<AttackLine> attack_lines;
    uint32_t body_hits[2][kBodySphereCount] = {}; // frames since a line crossed the sphere (from kAttackLinger + 1: none)
    bool history_shown = false; // the input history's column as last shown
    double panels_until = 0;   // and until when it shows
};
Session g;

void start_over_hitboxes() {
    g.attack_lines.clear();
    std::fill(&g.body_hits[0][0], &g.body_hits[0][0] + 2 * kBodySphereCount, kAttackLinger + 1);
}

void start_over() {
    g.top.placed = false;
    g.sides[0] = g.sides[1] = Side{};
    g.measure = Measure{};
    start_over_hitboxes();
}

// The hit's multiplier in percent, as the title's own damage display shows
// it: dealt = base x multiplier, rounded down, with a solo fighter's 120%
// and a counter hit's 120% more (144%); else (a juggle's scaling, say) the
// ratio itself.
int multiplier(int base, int dealt, bool counter) {
    if (base <= 0) return 0;
    static constexpr int kCounterHit[] = {144, 120}, kHit[] = {120, 100};
    for (int m : counter ? kCounterHit : kHit) {
        if (base * m / 100 == dealt) return m;
    }
    return static_cast<int>(std::lround(100.0 * dealt / base));
}

void attack_started(Side& s, const Fighter& f) {
    s.level = f.level;
    s.startup = f.first_active;
    s.first = f.first_active;
    s.last = f.last_active;
}

// The frames until the fighter can act, by its move.
int busy_frames(const Fighter& f) { return std::max(0, f.last_busy + 1 - static_cast<int>(f.frame)); }

// `s`'s attack reached the other fighter this frame (hit or blocked).
void connected(int s, const Fighter& attacker, const Fighter& defender, const Fighter& before) {
    Side& a = g.sides[s];
    const bool hit = defender.events & kHit;
    // The hit's properties last the combo, as the title's HIT INFO shows them.
    const bool counter = hit && (defender.events & kCounter), punish = hit && (defender.hit_flags & kPunish);
    if (!hit || before.combo == 0) a.counter = a.punish = a.clean = a.wall = false;
    a.counter |= counter;
    a.punish |= punish;
    a.in_combo = hit;
    if (hit) {
        const int dealt = defender.combo - (before.combo <= defender.combo ? before.combo : 0);
        a.damage = dealt;
        a.multiplier = multiplier(defender.hit_damage, dealt, counter);
        a.total += dealt;
        a.max_combo = std::max(a.max_combo, defender.combo);
        const int lost = before.health - defender.health, ceiling_lost = before.ceiling - defender.ceiling;
        a.recoverable = std::clamp(lost - ceiling_lost, 0, std::max(dealt, 0));
        a.recoverable_share = dealt > 0 ? static_cast<int>(std::lround(100.0 * a.recoverable / dealt)) : 0;
    } else {
        a.damage = a.multiplier = a.recoverable = a.recoverable_share = 0;
    }
    g.measure = Measure{};
    g.measure.on = true;
    g.measure.attacker = s;
    g.measure.note = !hit ? "Block" : counter ? "Counter" : "Hit";
    const int advantage = busy_frames(defender) - busy_frames(attacker);
    Side& d = g.sides[1 - s];
    a.advantage_known = d.advantage_known = true;
    a.advantage = advantage;
    d.advantage = -advantage;
    a.note = d.note = grounded_or_juggled(defender.posture) ? "KND" : g.measure.note;
}

void measure(const Fighter now[2]) {
    Measure& m = g.measure;
    if (!m.on) return;
    for (int i = 0; i < 2; ++i) {
        if (m.free_at[i] < 0 && (now[i].cancel & kFree)) m.free_at[i] = static_cast<int>(m.frames);
    }
    const int a = m.attacker, d = 1 - a;
    m.down |= grounded_or_juggled(now[d].posture);
    if (m.free_at[0] >= 0 && m.free_at[1] >= 0) {
        const int advantage = m.free_at[d] - m.free_at[a];
        const char* note = m.down ? "KND" : m.note;
        g.sides[a].advantage_known = g.sides[d].advantage_known = true;
        g.sides[a].advantage = advantage;
        g.sides[d].advantage = -advantage;
        g.sides[a].note = g.sides[d].note = note;
        m.on = false;
    } else if (++m.frames > kMeasureFrames) {
        m.on = false; // (the value from the moves stays)
    }
}

double seconds() { return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

// While a hit's or block's advantage plays out: the fighter that can act
// first is ahead (known once one can and the other not; before, by the
// moves' advantage). An even one colours neither.
void update_colours(const Fighter now[2]) {
    g.colours = Colours{};
    const Measure& m = g.measure;
    if (!g.settings[kAdvantageColours] || !m.on) return;
    const bool free0 = m.free_at[0] >= 0, free1 = m.free_at[1] >= 0;
    const int advantage = free0 != free1 ? (free0 ? 1 : -1) : g.sides[0].advantage;
    if (advantage == 0) return;
    const int ahead = advantage > 0 ? 0 : 1;
    // Until the next fighters' frame, and a little longer (as the panels).
    g.colours = {now[ahead].player, now[1 - ahead].player, seconds() + 0.25};
}

// ------------------------------------------------------------- the atlas

// The panel nine-slice drawn here, when the title's own is not found: at
// kDetail atlas texels per screen pixel (the TV image's 1280 x 720), kPanel
// pixels square with kCorner pixel corners.
constexpr uint32_t kDetail = 4, kPanel = 40, kCorner = 12;

// A nine-slice in the atlas: its uv, its edges' widths in its texels
// (left, right, top, bottom) and on the screen, its size in texels.
struct NineSlice {
    float uv[4] = {};
    float texels[4] = {}, pixels[4] = {};
    float width = 0, height = 0;
};

struct GlyphUv {
    float u0 = 0, v0 = 0, u1 = 0, v1 = 0;
    font::PlacedGlyph glyph;
};
struct Face {
    uint32_t size = 0;
    std::vector<GlyphUv> glyphs = std::vector<GlyphUv>(128); // ASCII; zero size: missing
};

// The title's icons in the main font: the directions (bold), by numpad
// direction (none for 5), and the Tekken button pictures, by buttons held.
constexpr uint16_t kArrows[10] = {0, 0xE008, 0xE009, 0xE00A, 0xE00B, 0, 0xE00C, 0xE00D, 0xE00E, 0xE00F};
constexpr uint16_t kButtonPictures = 0xE014; // + the buttons held (1: bit 0 ... 4: bit 3)

struct Icon {
    float u0 = 0, v0 = 0, u1 = 0, v1 = 0;
    uint32_t width = 0, height = 0; // in the font's texture
};

// The position reset's tooltip, in the look of the title's own (as
// Defensive Training's "Select + button: Start"): Select's icon, "+", the
// button picture of 3 (bit 2), text; the icons as the title shows them for
// the controller in use (the main font's texture with the port's icons:
// neutral, PlayStation).
constexpr uint16_t kSelectIcon = 0xE037, kButton3Picture = kButtonPictures + 4;

struct Atlas {
    Icon arrows[10], buttons[16];
    Icon tip_select[2], tip_button[2]; // neutral, PlayStation
    float white[4] = {};                    // uv of a white block
    NineSlice panel[2];                     // 1P's, 2P's
    Face labels, values;
};
Atlas g_atlas;

// Packs images into rows of an atlas `width` wide, a texel apart.
struct Packer {
    uint32_t width, x = 1, y = 1, row = 0;
    std::vector<std::pair<Rgba, std::pair<uint32_t, uint32_t>>> placed;
    explicit Packer(uint32_t w) : width(w) {}
    std::pair<uint32_t, uint32_t> add(Rgba image) {
        if (x + image.width + 1 > width) {
            x = 1;
            y += row + 1;
            row = 0;
        }
        const std::pair<uint32_t, uint32_t> at{x, y};
        x += image.width + 1;
        row = std::max(row, image.height);
        placed.push_back({std::move(image), at});
        return at;
    }
};

// The panel: dark glass, darker downwards, a teal rim with a dark line
// inside it, a faint sheen at the top, the top left and bottom right
// corners cut off. 2P's is the same in a muted red, to tell the sides apart.
Rgba panel_image(bool red = false) {
    using namespace draw;
    const uint32_t n = kPanel * kDetail;
    const double d = kDetail, e = 0.5 * d, cut = 7 * d, small_cut = 4 * d, end = n - e;
    const Shape body = Shape::polygon(n, n, {{cut, e}, {end, e}, {end, end - small_cut}, {end - small_cut, end}, {e, end},
                                             {e, cut}});
    const Shape rim = body.outline(1.25 * d);
    const Shape inner = body.outline(2.25 * d) - rim;
    Canvas c(n, n);
    c.fill(body, red ? Paint(Colour::rgb(0x2C1414, 0.80), Colour::rgb(0x0E0505, 0.88))
                     : Paint(Colour::rgb(0x0F1D28, 0.80), Colour::rgb(0x03080D, 0.88)));
    c.fill(Shape::polygon(n, n, {{cut, e}, {end, e}, {end, 10 * d}, {e, 10 * d}, {e, cut}}) - rim,
           Paint(Colour::rgb(red ? 0xFFD0C8 : 0xBFE9FF, 0.10), Colour::rgb(red ? 0xFFD0C8 : 0xBFE9FF, 0.0)));
    c.fill(inner, Colour::rgb(0x000000, 0.55));
    c.fill(rim, red ? Paint(Colour::rgb(0xD8918A, 0.95), Colour::rgb(0xA0544E, 0.95))
                    : Paint(Colour::rgb(0x5CC9DC, 0.95), Colour::rgb(0x2E8FA3, 0.95)));
    return c.result();
}

// The panel as the title draws it: the main menu's player box (its name,
// battle records), from data007's menu textures (800 x 116, BC3; drawn as
// light over the scene, black around it). It becomes a nine-slice: its
// edges at their size, the top left corner's cut, its inner step and the
// bottom right's notch whole, the middles from a plain stretch of rim.
// Black reached from its edges (around the box, the notch) becomes
// transparent; the rest is the box's dark glass (the scene seen through
// it, darkened, as on the main menu) and its rim, opaque. 2P's has its
// colours turned to their opposites: the teal rim red.
constexpr const char* kMenuArchive = "content/hdd/data007";
constexpr uint32_t kMenuTextures[] = {0x0631A962, 0x4E387D75};
constexpr uint32_t kBoxWidth = 800, kBoxHeight = 116;
constexpr uint32_t kBoxX0 = 116, kBoxX1 = 772, kBoxY0 = 20, kBoxY1 = 100; // the box in it, its glow too
constexpr uint32_t kBoxLeft = 38, kBoxRight = 102, kBoxTop = 12, kBoxBottom = 15; // its edges (the notch whole)
constexpr uint32_t kBoxMiddleX = 420, kBoxMiddleY = 50, kBoxMiddle = 8;            // plain rim and glass
constexpr uint32_t kNotchY = 96, kNotchX0 = 678, kNotchX1 = 734;                   // where the glass ends in the notch
constexpr int kRimBright = 60; // the rim's line: brighter than its glow and the glass
constexpr float kBoxGlass = 0.72f;
constexpr uint32_t kBoxDetail = 4; // texels per texel of the title's: smooth edges on larger screens

std::optional<Rgba> menu_box(bool red) {
    std::optional<ntp3::Texture> found;
    for (uint32_t key : kMenuTextures) {
        const auto file = game_file(kMenuArchive, key);
        const auto textures = file ? ntp3::parse(*file) : std::nullopt;
        if (!textures) continue;
        for (const ntp3::Texture& t : *textures) {
            if (t.width == kBoxWidth && t.height == kBoxHeight) found = t;
        }
        if (found) break;
    }
    const auto box = found ? ntp3::decode(*found) : std::nullopt;
    if (!box) return std::nullopt;
    // Outside the box: what its edges reach without crossing the rim's
    // line (the glow round it, as bright as the glass, is outside), the
    // notch closed where the glass ends in it.
    const uint32_t rw = kBoxX1 - kBoxX0, rh = kBoxY1 - kBoxY0;
    const Rgba region = crop(*box, kBoxX0, kBoxY0, rw, rh);
    std::vector<uint8_t> region_outside(size_t{rw} * rh, 0);
    {
        const auto open = [&](uint32_t x, uint32_t y) {
            if (y + kBoxY0 == kNotchY && x + kBoxX0 >= kNotchX0 && x + kBoxX0 <= kNotchX1) return false;
            const uint8_t* p = region.at(x, y);
            return std::max({p[0], p[1], p[2]}) < kRimBright;
        };
        std::vector<std::pair<uint32_t, uint32_t>> todo;
        for (uint32_t x = 0; x < rw; ++x) todo.push_back({x, 0}), todo.push_back({x, rh - 1});
        for (uint32_t y = 0; y < rh; ++y) todo.push_back({0, y}), todo.push_back({rw - 1, y});
        while (!todo.empty()) {
            const auto [x, y] = todo.back();
            todo.pop_back();
            if (region_outside[size_t{y} * rw + x] || !open(x, y)) continue;
            region_outside[size_t{y} * rw + x] = 1;
            if (x > 0) todo.push_back({x - 1, y});
            if (x + 1 < rw) todo.push_back({x + 1, y});
            if (y > 0) todo.push_back({x, y - 1});
            if (y + 1 < rh) todo.push_back({x, y + 1});
        }
    }
    // The nine pieces (and which of their pixels are outside), side by side.
    const uint32_t xs[3][2] = {{0, kBoxLeft}, {kBoxMiddleX - kBoxX0, kBoxMiddle}, {rw - kBoxRight, kBoxRight}};
    const uint32_t ys[3][2] = {{0, kBoxTop}, {kBoxMiddleY - kBoxY0, kBoxMiddle}, {rh - kBoxBottom, kBoxBottom}};
    const uint32_t w = kBoxLeft + kBoxMiddle + kBoxRight, h = kBoxTop + kBoxMiddle + kBoxBottom;
    Rgba out = blank(w, h);
    std::vector<uint8_t> outside(size_t{w} * h, 0);
    uint32_t oy = 0;
    for (const auto& y : ys) {
        uint32_t ox = 0;
        for (const auto& x : xs) {
            put(out, crop(region, x[0], y[0], x[1], y[1]), ox, oy);
            for (uint32_t j = 0; j < y[1]; ++j) {
                for (uint32_t i = 0; i < x[1]; ++i) {
                    outside[size_t{oy + j} * w + ox + i] = region_outside[size_t{y[0] + j} * rw + x[0] + i];
                }
            }
            ox += x[1];
        }
        oy += y[1];
    }
    // At kBoxDetail times the size, filtered (the colours, and the box's
    // outline, which then cuts smoothly where it was a staircase).
    const uint32_t k = kBoxDetail, W = w * k, H = h * k;
    const auto sample = [&](float fx, float fy, auto value) {
        fx = std::clamp(fx, 0.0f, static_cast<float>(w - 1)), fy = std::clamp(fy, 0.0f, static_cast<float>(h - 1));
        const uint32_t x0 = static_cast<uint32_t>(fx), y0 = static_cast<uint32_t>(fy);
        const uint32_t x1 = std::min(x0 + 1, w - 1), y1 = std::min(y0 + 1, h - 1);
        const float tx = fx - x0, ty = fy - y0;
        return (value(x0, y0) * (1 - tx) + value(x1, y0) * tx) * (1 - ty) + (value(x0, y1) * (1 - tx) + value(x1, y1) * tx) * ty;
    };
    Rgba fine = blank(W, H);
    for (uint32_t y = 0; y < H; ++y) {
        for (uint32_t x = 0; x < W; ++x) {
            const float fx = (x + 0.5f) / k - 0.5f, fy = (y + 0.5f) / k - 0.5f;
            const float inside = sample(fx, fy, [&](uint32_t sx, uint32_t sy) { return outside[size_t{sy} * w + sx] ? 0.0f : 1.0f; });
            const float edge = std::clamp((inside - 0.3f) / 0.4f, 0.0f, 1.0f);
            float rgb[3];
            for (int c = 0; c < 3; ++c) {
                rgb[c] = sample(fx, fy, [&](uint32_t sx, uint32_t sy) { return static_cast<float>(out.at(sx, sy)[c]); });
            }
            const float bright = std::max({rgb[0], rgb[1], rgb[2]});
            if (red) {
                const float grey = (rgb[0] + rgb[1] + rgb[2]) / 3;
                for (float& v : rgb) v = std::clamp(2 * grey - v, 0.0f, 255.0f);
            }
            // Inside, glass and rim; outside, the glow as light (its
            // brightness the cover, its colour at full strength), the two
            // mixed across the outline.
            const float glass = std::max(kBoxGlass, std::min(1.0f, bright / 60.0f));
            const float glow = std::min(1.0f, bright / 255.0f), lift = bright > 1 ? 255.0f / bright : 0.0f;
            const float cover = edge * glass + (1 - edge) * glow;
            uint8_t* p = fine.at(x, y);
            for (int c = 0; c < 3; ++c) {
                const float v = cover > 0 ? (edge * glass * rgb[c] + (1 - edge) * glow * rgb[c] * lift) / cover : 0;
                p[c] = static_cast<uint8_t>(std::clamp(v, 0.0f, 255.0f) + 0.5f);
            }
            p[3] = static_cast<uint8_t>(255 * cover + 0.5f);
        }
    }
    return fine;
}

// A font of the title: its glyphs for ASCII from data003.
struct FontFiles {
    uint32_t glyphs, texture;
};
constexpr const char* kFontArchive = "content/hdd/data003";
constexpr FontFiles kLabelFont{0x46B70814, 0x335915C9}; // the Japanese gothic font (help panels: upright Latin too)
constexpr FontFiles kValueFont{0x3A27BC43, 0x4FC9A19E}; // the main font (bold italic)

// The icons: packed after the fonts, (atlas index, code) in `at`.
bool add_icons(Packer& packer, std::vector<std::pair<uint32_t, uint16_t>>& at,
               std::vector<std::pair<uint32_t, Icon*>>& tip_at) {
    const auto table = game_file(kFontArchive, kValueFont.glyphs);
    const auto file = game_file(kFontArchive, kValueFont.texture);
    const auto metrics = table ? font::parse_metrics(*table) : std::nullopt;
    const auto glyphs = table ? font::parse(*table) : std::nullopt;
    const auto textures = file ? ntp3::parse(*file) : std::nullopt;
    const auto texture = textures && !textures->empty() ? ntp3::decode(textures->front()) : std::nullopt;
    if (!metrics || !glyphs || !texture) return false;
    // The tooltip's icons, from the textures the title draws with.
    const font::Font main{*glyphs, *texture};
    const Rgba variants[2] = {font::neutral_icons(main), font::playstation_icons(main)};
    for (int v = 0; v < 2; ++v) {
        for (const auto& [code, icon] : {std::pair{kSelectIcon, &g_atlas.tip_select[v]}, std::pair{kButton3Picture, &g_atlas.tip_button[v]}}) {
            const auto it = metrics->glyphs.find(code);
            if (it == metrics->glyphs.end()) return false;
            const font::Glyph& g = it->second.box;
            if (!g.width || !g.height || g.x + g.width > variants[v].width || g.y + g.height > variants[v].height) return false;
            packer.add(crop(variants[v], g.x, g.y, g.width, g.height));
            tip_at.push_back({static_cast<uint32_t>(packer.placed.size() - 1), icon});
        }
    }
    std::vector<uint16_t> codes;
    for (uint16_t c : kArrows) {
        if (c) codes.push_back(c);
    }
    for (uint16_t b = 0; b < 16; ++b) codes.push_back(static_cast<uint16_t>(kButtonPictures + b));
    for (uint16_t c : codes) {
        const auto it = metrics->glyphs.find(c);
        if (it == metrics->glyphs.end()) return false;
        const font::Glyph& g = it->second.box;
        if (!g.width || !g.height || g.x + g.width > texture->width || g.y + g.height > texture->height) return false;
        packer.add(crop(*texture, g.x, g.y, g.width, g.height));
        at.push_back({static_cast<uint32_t>(packer.placed.size() - 1), c});
    }
    return true;
}

bool add_font(Packer& packer, const FontFiles& files, Face& face, std::vector<std::pair<uint32_t, uint16_t>>& at) {
    const auto table = game_file(kFontArchive, files.glyphs);
    const auto file = game_file(kFontArchive, files.texture);
    const auto metrics = table ? font::parse_metrics(*table) : std::nullopt;
    const auto textures = file ? ntp3::parse(*file) : std::nullopt;
    const auto texture = textures && !textures->empty() ? ntp3::decode(textures->front()) : std::nullopt;
    if (!metrics || !texture || metrics->size == 0) return false;
    face.size = metrics->size;
    for (uint16_t c = 0x20; c < 0x7F; ++c) {
        const auto it = metrics->glyphs.find(c);
        if (it == metrics->glyphs.end()) continue;
        const font::Glyph& b = it->second.box;
        if (b.x + b.width > texture->width || b.y + b.height > texture->height) continue;
        face.glyphs[c].glyph = it->second;
        if (b.width == 0 || b.height == 0) continue;
        packer.add(crop(*texture, b.x, b.y, b.width, b.height));
        at.push_back({static_cast<uint32_t>(packer.placed.size() - 1), c});
    }
    // No space glyph (the title spaces words itself): a third of the size.
    font::Placement& space = face.glyphs[' '].glyph.placement;
    if (space.advance <= 0) space.advance = face.size / 3.0;
    return true;
}

bool build_atlas() {
    Packer packer(1024);
    Rgba white = blank(4, 4);
    std::fill(white.pixels.begin(), white.pixels.end(), uint8_t{255});
    packer.add(white);
    // The title's box, else the one drawn here.
    auto box = menu_box(false), red_box = menu_box(true);
    const bool title_box = box && red_box;
    if (!title_box) std::fprintf(stderr, "ttt2: warning: the main menu's box is not where expected; frame data panels drawn instead\n");
    packer.add(title_box ? std::move(*box) : panel_image());
    packer.add(title_box ? std::move(*red_box) : panel_image(true));
    std::vector<std::pair<uint32_t, uint16_t>> labels, values;
    std::vector<std::pair<uint32_t, uint16_t>> icons;
    std::vector<std::pair<uint32_t, Icon*>> tip_icons;
    if (!add_font(packer, kLabelFont, g_atlas.labels, labels) || !add_font(packer, kValueFont, g_atlas.values, values) ||
        !add_icons(packer, icons, tip_icons)) {
        return false;
    }
    auto atlas = std::make_shared<gpu::overlay::Atlas>();
    atlas->width = packer.width;
    atlas->height = packer.y + packer.row + 1;
    Rgba out = blank(atlas->width, atlas->height);
    for (const auto& [image, xy] : packer.placed) put(out, image, xy.first, xy.second);
    atlas->pixels = std::move(out.pixels);
    const float w = static_cast<float>(atlas->width), h = static_cast<float>(atlas->height);
    const auto uv = [&](uint32_t i, float* to) {
        const auto& [image, xy] = packer.placed[i];
        to[0] = xy.first / w;
        to[1] = xy.second / h;
        to[2] = (xy.first + image.width) / w;
        to[3] = (xy.second + image.height) / h;
    };
    // The white block's middle only, so filtering never reaches its edge.
    const auto& [_, wxy] = packer.placed[0];
    g_atlas.white[0] = g_atlas.white[2] = (wxy.first + 2) / w;
    g_atlas.white[1] = g_atlas.white[3] = (wxy.second + 2) / h;
    for (int side = 0; side < 2; ++side) {
        NineSlice& n = g_atlas.panel[side];
        uv(1 + side, n.uv);
        if (title_box) {
            constexpr float d = kBoxDetail;
            n = {{n.uv[0], n.uv[1], n.uv[2], n.uv[3]},
                 {kBoxLeft * d, kBoxRight * d, kBoxTop * d, kBoxBottom * d},
                 {kBoxLeft, kBoxRight, kBoxTop, kBoxBottom},
                 (kBoxLeft + kBoxMiddle + kBoxRight) * d,
                 (kBoxTop + kBoxMiddle + kBoxBottom) * d};
        } else {
            constexpr float t = kCorner * kDetail, p = kCorner, size = kPanel * kDetail;
            n = {{n.uv[0], n.uv[1], n.uv[2], n.uv[3]}, {t, t, t, t}, {p, p, p, p}, size, size};
        }
    }
    for (auto [list, face] : {std::pair{&labels, &g_atlas.labels}, std::pair{&values, &g_atlas.values}}) {
        for (const auto& [i, c] : *list) {
            float r[4];
            uv(i, r);
            GlyphUv& g = face->glyphs[c];
            g.u0 = r[0], g.v0 = r[1], g.u1 = r[2], g.v1 = r[3];
        }
    }
    for (const auto& [i, c] : icons) {
        Icon* icon = nullptr;
        for (uint32_t n = 0; n < 10; ++n) {
            if (kArrows[n] == c) icon = &g_atlas.arrows[n];
        }
        if (c >= kButtonPictures && c < kButtonPictures + 16) icon = &g_atlas.buttons[c - kButtonPictures];
        float r[4];
        uv(i, r);
        *icon = {r[0], r[1], r[2], r[3], packer.placed[i].first.width, packer.placed[i].first.height};
    }
    for (const auto& [i, icon] : tip_icons) {
        float r[4];
        uv(i, r);
        *icon = {r[0], r[1], r[2], r[3], packer.placed[i].first.width, packer.placed[i].first.height};
    }
    gpu::overlay::set_atlas(std::move(atlas));
    return true;
}

// ------------------------------------------------------------- the layout

constexpr uint32_t kLabel = 0xE2F4FFFF, kValue = 0xFFFFFFFF, kShadow = 0x000000C0;
constexpr uint32_t kPositive = 0x4ADE80FF, kNegative = 0xF87171FF;
constexpr uint32_t kFlagOff = 0xA0B4C359, kFlagOn = 0x00F0FFFF, kCounterOn = 0xFFC83CFF;
constexpr float kWidth = 270, kMargin = 226, kRow = 15, kGap = 5; // (kMargin: from the screen's side)
// Room inside a panel, clear of the box's top left step and bottom right notch.
constexpr float kPadTop = 10, kPadBottom = 14, kPadSide = 14;
constexpr float kLabelPx = 12.5f, kValuePx = 13.5f; // text heights (the font's size scaled to)
// The hint line: the title's hints' height and size (Defensive Training's at
// x 138, y 643 to 666), the panels above it.
constexpr float kTipY = 654.5f, kTipIcon = 23, kTipButton = 19, kTipPx = 21, kTipSide = 138; // (kPanelsBottom: framedata.h)
constexpr float kAboveGauge = 8; // (and above a 2D fighter's gauge)
constexpr float kTipSpacing = -1.0f; // added to each glyph's advance
constexpr uint32_t kTipOutline = 0x000000B0;

class Layout {
public:
    std::vector<Quad> quads;

    void rect(float x0, float y0, float x1, float y1, uint32_t top, uint32_t bottom) {
        quads.push_back({x0, y0, x1, y1, g_atlas.white[0], g_atlas.white[1], g_atlas.white[2], g_atlas.white[3], top,
                         bottom});
    }

    // Side `side`'s nine-slice over x0..x1, y0..y1 (its edges smaller in a
    // smaller box).
    void panel(int side, float x0, float y0, float x1, float y1) {
        const NineSlice& n = g_atlas.panel[side];
        const float* p = n.uv;
        const float fx = std::min(1.0f, (x1 - x0) / (n.pixels[0] + n.pixels[1]));
        const float fy = std::min(1.0f, (y1 - y0) / (n.pixels[2] + n.pixels[3]));
        const float du = (p[2] - p[0]) / n.width, dv = (p[3] - p[1]) / n.height;
        const float xs[4] = {x0, x0 + n.pixels[0] * fx, x1 - n.pixels[1] * fx, x1};
        const float ys[4] = {y0, y0 + n.pixels[2] * fy, y1 - n.pixels[3] * fy, y1};
        const float us[4] = {p[0], p[0] + n.texels[0] * du, p[2] - n.texels[1] * du, p[2]};
        const float vs[4] = {p[1], p[1] + n.texels[2] * dv, p[3] - n.texels[3] * dv, p[3]};
        for (int j = 0; j < 3; ++j) {
            for (int i = 0; i < 3; ++i) {
                quads.push_back({xs[i], ys[j], xs[i + 1], ys[j + 1], us[i], vs[j], us[i + 1], vs[j + 1], 0xFFFFFFFF,
                                 0xFFFFFFFF});
            }
        }
    }

    // An icon `height` pixels high, its left edge at x, centred on y.
    void icon(const Icon& i, float x, float y, float height) {
        if (!i.height) return;
        const float w = height * static_cast<float>(i.width) / static_cast<float>(i.height);
        quads.push_back({x, y - height / 2, x + w, y + height / 2, i.u0, i.v0, i.u1, i.v1, 0xFFFFFFFF, 0xFFFFFFFF});
    }

    // As the title draws its hints: a dark outline round each glyph, set a
    // little tighter than the font's advances.
    static float hint_width(const Face& face, float px, const std::string& text) {
        return width(face, px, text) + kTipSpacing * static_cast<float>(text.size());
    }
    void hint_text(const Face& face, float px, float x, float y, const std::string& text, uint32_t colour) {
        // The outline (and a shadow down and right), then the text.
        static constexpr float kAround[][2] = {{-1, -1}, {0, -1}, {1, -1}, {-1, 0}, {1, 0},  {-1, 1},
                                               {0, 1},   {1, 1},  {1.5f, 1.5f}, {0, 0}};
        const float s = px / static_cast<float>(face.size);
        for (const auto& d : kAround) {
            const bool fill = d[0] == 0 && d[1] == 0;
            const uint32_t c = fill ? colour : kTipOutline;
            float pen = x + d[0];
            for (unsigned char ch : text) {
                if (ch >= 128) continue;
                const GlyphUv& g = face.glyphs[ch];
                const font::PlacedGlyph& pg = g.glyph;
                if (pg.box.width > 0 && pg.box.height > 0) {
                    const float gx = pen + static_cast<float>(pg.placement.left) * s;
                    const float gy = y + d[1] - static_cast<float>(pg.placement.top) * s;
                    quads.push_back({gx, gy, gx + pg.box.width * s, gy + pg.box.height * s, g.u0, g.v0, g.u1, g.v1, c, c});
                }
                pen += static_cast<float>(pg.placement.advance) * s + kTipSpacing;
            }
        }
    }

    static float width(const Face& face, float px, const std::string& text) {
        const float s = px / static_cast<float>(face.size);
        float w = 0;
        for (unsigned char c : text) {
            if (c < 128) w += static_cast<float>(face.glyphs[c].glyph.placement.advance) * s;
        }
        return w;
    }

    // `text` with its baseline at y, from x (or ending there, right-aligned),
    // over a soft shadow.
    void text(const Face& face, float px, float x, float y, const std::string& text, uint32_t colour, bool right = false) {
        if (right) x -= width(face, px, text);
        for (const auto& [dx, dy, c] : {std::tuple{1.0f, 1.0f, kShadow}, std::tuple{0.0f, 0.0f, colour}}) {
            const float s = px / static_cast<float>(face.size);
            float pen = x + dx;
            for (unsigned char ch : text) {
                if (ch >= 128) continue;
                const GlyphUv& g = face.glyphs[ch];
                const font::PlacedGlyph& pg = g.glyph;
                if (pg.box.width > 0 && pg.box.height > 0) {
                    const float gx = pen + static_cast<float>(pg.placement.left) * s;
                    const float gy = y + dy - static_cast<float>(pg.placement.top) * s;
                    // Shadows a little fainter where colours are faint (dim flags).
                    const uint32_t tint = dx != 0 ? (c & 0xFFFFFF00) | ((c & 0xFF) * (colour & 0xFF) / 255) : c;
                    quads.push_back({gx, gy, gx + pg.box.width * s, gy + pg.box.height * s, g.u0, g.v0, g.u1, g.v1, tint,
                                     tint});
                }
                pen += static_cast<float>(pg.placement.advance) * s;
            }
        }
    }
};

std::string number(int v) { return std::to_string(v); }

std::string signed_number(int v) { return v > 0 ? "+" + std::to_string(v) : std::to_string(v); }

void lay_out_side(Layout& l, int s, const Fighter now[2], float bottom) {
    const Side& side = g.sides[s];
    const Atlas& a = g_atlas;
    const float x0 = s == 0 ? kMargin : gpu::overlay::kWidth - kMargin - kWidth, x1 = x0 + kWidth;
    const float lower_h = 4 * kRow + kPadTop + kPadBottom, upper_h = 6 * kRow + kPadTop + kPadBottom;
    const float lower_top = bottom - lower_h, upper_top = lower_top - kGap - upper_h;
    l.panel(s, x0, upper_top, x1, lower_top - kGap);
    l.panel(s, x0, lower_top, x1, bottom);
    const float lx = x0 + kPadSide, rx = x1 - kPadSide;
    auto row = [&](float top, int i, const char* label, const std::string& value, uint32_t colour) {
        const float base = top + kPadTop + kRow * static_cast<float>(i) + kRow * 0.78f;
        l.text(a.labels, kLabelPx, lx, base, label, kLabel);
        if (!value.empty()) l.text(a.values, kValuePx, rx, base, value, colour, true);
    };
    row(upper_top, 0, "Total Damage", number(side.total), kValue);
    row(upper_top, 1, "Max Combo Damage", number(side.max_combo), kValue);
    row(upper_top, 2, "Hit Properties", level_name(side.level), kValue);
    const auto with_share = [](int v, int share) { return std::to_string(v) + " (" + std::to_string(share) + "%)"; };
    row(upper_top, 3, "Damage", side.damage < 0 ? "0 (0%)" : with_share(side.damage, side.multiplier), kValue);
    row(upper_top, 4, "Recoverable Damage", with_share(side.recoverable, side.recoverable_share), kValue);
    // The hit's properties, lit when it had them.
    const float flags = upper_top + kPadTop + kRow * 5 + kRow * 0.78f;
    float fx = lx;
    for (const auto& [name, lit, on] : {std::tuple{"Clean", side.clean, kFlagOn}, std::tuple{"Counter", side.counter, kCounterOn},
                                        std::tuple{"Punish", side.punish, kFlagOn}, std::tuple{"Wall", side.wall, kFlagOn}}) {
        const float w = Layout::width(a.labels, kLabelPx, name);
        if (lit) l.rect(fx - 4, flags - kRow * 0.78f, fx + w + 4, flags + kRow * 0.22f, (on & 0xFFFFFF00) | 0x40, (on & 0xFFFFFF00) | 0x18);
        l.text(a.labels, kLabelPx, fx, flags, name, lit ? on : kFlagOff);
        fx += w + 16;
    }
    std::string startup = "---";
    if (side.startup) startup = number(static_cast<int>(side.startup));
    row(lower_top, 0, "Attack Startup Frames",
        startup + " (" + number(static_cast<int>(side.first)) + " - " + number(static_cast<int>(side.last)) + ")", kValue);
    const uint32_t advantage_colour = !side.advantage_known || side.advantage == 0 ? kValue
                                      : side.advantage > 0                         ? kPositive
                                                                                   : kNegative;
    row(lower_top, 1, "Frame Advantage",
        side.advantage_known ? signed_number(side.advantage) + " (" + side.note + ")" : "--- (---)", advantage_colour);
    row(lower_top, 2, "Status", posture_name(now[s].posture), kValue);
    char distance[16];
    std::snprintf(distance, sizeof(distance), "%.2f",
                  std::hypot(now[0].x - now[1].x, now[0].z - now[1].z) / 1000.0);
    row(lower_top, 3, "Distance from Opponent", distance, kValue);
}

// The input history: rows from the top down, newest first, along the left
// edge from under the 1P name tag.
constexpr float kHistoryX0 = 8, kHistoryX1 = 98, kHistoryTop = 182, kHistoryRow = 19;
constexpr uint32_t kSeparator = 0xFFFFFF50, kCountBand = 0x0000006C;

void lay_out_history(Layout& l) {
    const Atlas& a = g_atlas;
    float y = kHistoryTop;
    for (auto it = g.history.rbegin(); it != g.history.rend(); ++it, y += kHistoryRow) {
        const float middle = y + kHistoryRow / 2;
        l.rect(kHistoryX1 - 40, y + 1, kHistoryX1, y + kHistoryRow - 1, kCountBand, kCountBand);
        l.rect(kHistoryX0, y + kHistoryRow - 1, kHistoryX1, y + kHistoryRow, kSeparator, kSeparator);
        if (it->direction != 5) l.icon(a.arrows[it->direction], kHistoryX0 + 4, middle, 16);
        if (it->buttons) l.icon(a.buttons[it->buttons], kHistoryX0 + 28, middle, 18);
        l.text(a.values, 13, kHistoryX1 - 5, middle + 5, std::to_string(std::min(it->frames, 999u)), kValue, true);
    }
}

void record_input(const Fighter now[2]) {
    for (int s = 0; s < 2; ++s) {
        if (now[s].pad) g.player = s;
    }
    const Fighter& f = now[g.player];
    if (!g.history.empty() && g.history.back().direction == f.direction && g.history.back().buttons == f.buttons) {
        ++g.history.back().frames;
        return;
    }
    g.history.push_back({f.direction, f.buttons, 1});
    if (g.history.size() > kHistoryRows) g.history.erase(g.history.begin());
}

// The hitboxes: where the title tests attacks against bodies. Each fighter
// has 14 spheres over its body (+2168, 24 bytes each: the centre, the
// radius at +20; placed on its bones every frame), and an attack it makes
// tests line segments (+2072, 24 bytes each: two ends, from the move's
// hitbox bones: a fist, a forearm, a shin) against the other's spheres,
// +1158 of them (at most four) on the frames the move is active
// (sub_039C0948 -> sub_039C0508, the test sub_039C006C). They are drawn as
// solids in the world (gpu/overlay.h), as the camera that renders the scene
// sees them: the camera manager (*(*0x1084FEBC + 732)) keeps it at +392,
// its view-projection matrix at +0x60 (row vectors).
constexpr uint32_t kBodySpheres = 2168, kBodySphereSize = 24, kBodySphereRadius = 20;
constexpr uint32_t kAttackLines = 2072, kAttackLineSize = 24, kAttackLineCount = 1158; // (a byte)
constexpr uint32_t kCameraHolder = 0x1084FEBC, kCameraManager = 732, kRenderCamera = 392, kViewProjection = 0x60;
constexpr uint32_t kBodyColours[2] = {0x4FD8FFFF, 0xFFD84AFF}; // 1P's, 2P's
constexpr uint32_t kBodyHit = 0xFF4040FF, kAttack = 0xFF3030FF;
constexpr float kBodyAlpha = 0.3f, kAttackRadius = 25; // (the title's lines have no thickness)

struct Camera {
    float m[16] = {};
};

uint32_t render_camera(uint8_t* base) {
    const uint32_t holder = ppc::ld32(base, kCameraHolder);
    const uint32_t manager = holder ? ppc::ld32(base, holder + kCameraManager) : 0;
    return manager ? ppc::ld32(base, manager + kRenderCamera) : 0;
}

bool read_camera(uint8_t* base, Camera& c) {
    const uint32_t camera = render_camera(base);
    if (!camera) return false;
    for (uint32_t i = 0; i < 16; ++i) c.m[i] = ldf(base, camera + kViewProjection + 4 * i);
    return std::all_of(c.m, c.m + 16, [](float v) { return std::isfinite(v); });
}

// The camera from above (TOP CAMERA), in a window between the panels: the
// renderer draws the title's frame again with the camera's matrix replaced
// (gpu/overlay.h) and shows the middle of it. Over the middle of the
// fighters, looking down, their line across the screen (1P's end on the
// left), high enough that both and room round them fill that middle, with
// the render camera's own projection (+0xA0; row vectors, the view looking
// down its -z).
constexpr uint32_t kProjection = 0xA0;
constexpr float kTopRoom = 1000;                          // mm round the fighters
constexpr float kTopEase = 1.0f / 6, kTopZoomEase = 1.0f / 10; // of the way to its place a frame: following, height
constexpr float kWindowWidth = 260, kWindowHeight = 146; // (16:9)
constexpr float kCrop[4] = {320, 180, 960, 540};         // the middle half

bool top_view(uint8_t* base, uint32_t camera, const Fighter now[2], float view_projection[16]) {
    float projection[16];
    for (uint32_t i = 0; i < 16; ++i) projection[i] = ldf(base, camera + kProjection + 4 * i);
    if (!(projection[0] > 0) || !std::isfinite(projection[0])) return false;
    float ax = now[1].x - now[0].x, az = now[1].z - now[0].z;
    const float distance = std::hypot(ax, az);
    if (distance < 1) ax = g.top.ax, az = g.top.az;
    else ax /= distance, az /= distance;
    const float share = (kCrop[2] - kCrop[0]) / 1280; // of the width the window shows
    const float height = projection[0] * (distance / 2 + kTopRoom) / share;
    // Eased, from where it was placed when the window came up: following
    // the fighters within about a third of a second, rising and sinking
    // within about half of one.
    auto& t = g.top;
    const float ease = t.placed ? kTopEase : 1.0f, zoom_ease = t.placed ? kTopZoomEase : 1.0f;
    t.x += ((now[0].x + now[1].x) / 2 - t.x) * ease;
    t.z += ((now[0].z + now[1].z) / 2 - t.z) * ease;
    t.height += (height - t.height) * zoom_ease;
    // (Turned through the shorter way; the line's ends keep their sides.)
    float tx = t.ax + (ax - t.ax) * ease, tz = t.az + (az - t.az) * ease;
    const float length = std::hypot(tx, tz);
    if (length > 1e-3f) t.ax = tx / length, t.az = tz / length;
    else t.ax = ax, t.az = az;
    t.placed = true;
    ax = t.ax, az = t.az;
    const float eye[3] = {t.x, t.height, t.z};
    const float right[3] = {ax, 0, az}, up[3] = {az, 0, -ax}, back[3] = {0, 1, 0};
    const float* axes[3] = {right, up, back};
    float view[16];
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c) view[4 * r + c] = axes[c][r];
        view[4 * r + 3] = 0;
    }
    for (int c = 0; c < 3; ++c) view[12 + c] = -(axes[c][0] * eye[0] + axes[c][1] * eye[1] + axes[c][2] * eye[2]);
    view[15] = 1;
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            float v = 0;
            for (int k = 0; k < 4; ++k) v += view[4 * r + k] * projection[4 * k + c];
            view_projection[4 * r + c] = v;
        }
    }
    return std::all_of(view_projection, view_projection + 16, [](float v) { return std::isfinite(v); });
}

std::shared_ptr<const gpu::overlay::Window> top_window(uint8_t* base, const Fighter now[2], float bottom) {
    const uint32_t camera = render_camera(base);
    if (!camera) return nullptr;
    auto w = std::make_shared<gpu::overlay::Window>();
    for (uint32_t i = 0; i < 16; ++i) w->from[i] = ldf(base, camera + kViewProjection + 4 * i);
    if (!top_view(base, camera, now, w->to)) return nullptr;
    // The middle half seen in the window: twice as large.
    std::copy(w->to, w->to + 16, w->view_projection);
    for (int r = 0; r < 4; ++r) w->view_projection[4 * r] *= 2, w->view_projection[4 * r + 1] *= 2;
    const float x0 = 640 - kWindowWidth / 2;
    const float y1 = bottom - 14; // (its frame's notch below it, level with the panels)
    const float rect[4] = {x0, y1 - kWindowHeight, x0 + kWindowWidth, y1};
    std::copy(rect, rect + 4, w->rect);
    std::copy(kCrop, kCrop + 4, w->crop);
    return w;
}

struct Sphere {
    float c[3] = {}, r = 0;
};

void read_body(uint8_t* base, uint32_t player, Sphere (&body)[kBodySphereCount]) {
    for (uint32_t i = 0; i < kBodySphereCount; ++i) {
        const uint32_t at = player + kBodySpheres + kBodySphereSize * i;
        body[i] = {{ldf(base, at), ldf(base, at + 4), ldf(base, at + 8)}, ldf(base, at + kBodySphereRadius)};
    }
}

// The line crosses the sphere, as the title's test has it.
bool crosses(const float* e, const Sphere& s) {
    const float d[3] = {e[3] - e[0], e[4] - e[1], e[5] - e[2]};
    const float dd = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
    float t = dd > 0 ? ((s.c[0] - e[0]) * d[0] + (s.c[1] - e[1]) * d[1] + (s.c[2] - e[2]) * d[2]) / dd : 0;
    t = std::clamp(t, 0.0f, 1.0f);
    float distance = 0;
    for (int k = 0; k < 3; ++k) {
        const float v = s.c[k] - (e[k] + d[k] * t);
        distance += v * v;
    }
    return distance <= s.r * s.r;
}

// 1 for the frame of a test, then fading.
float strength(uint32_t age) {
    return age == 0 ? 1.0f : age > kAttackLinger ? 0.0f : 0.7f * (1 - static_cast<float>(age) / (kAttackLinger + 1));
}

uint32_t with_alpha(uint32_t rgba, float alpha) {
    return (rgba & 0xFFFFFF00) | static_cast<uint32_t>(255 * std::clamp(alpha, 0.0f, 1.0f));
}

// This frame's attack lines join the earlier ones, which age, and mark the
// spheres they cross.
void update_attack_lines(uint8_t* base, const Fighter now[2], const Sphere (&bodies)[2][kBodySphereCount]) {
    for (AttackLine& line : g.attack_lines) ++line.age;
    std::erase_if(g.attack_lines, [](const AttackLine& line) { return line.age > kAttackLinger; });
    for (auto& side : g.body_hits) {
        for (uint32_t& age : side) age = std::min(age + 1, kAttackLinger + 1);
    }
    for (int s = 0; s < 2; ++s) {
        const uint32_t lines = std::min<uint32_t>(base[now[s].player + kAttackLineCount], 4);
        for (uint32_t i = 0; i < lines; ++i) {
            AttackLine line;
            line.side = s;
            for (uint32_t k = 0; k < 6; ++k) line.ends[k] = ldf(base, now[s].player + kAttackLines + kAttackLineSize * i + 4 * k);
            for (uint32_t b = 0; b < kBodySphereCount; ++b) {
                if (crosses(line.ends, bodies[1 - s][b])) g.body_hits[1 - s][b] = 0;
            }
            g.attack_lines.push_back(line);
        }
    }
}

// The bodies in their side's colour (red where an attack's line crosses
// them, for a while), the attack lines in front of everything, fading.
std::shared_ptr<const gpu::overlay::Scene> hitbox_scene(const Camera& camera,
                                                        const Sphere (&bodies)[2][kBodySphereCount]) {
    auto scene = std::make_shared<gpu::overlay::Scene>();
    std::copy(camera.m, camera.m + 16, scene->view_projection);
    for (int s = 0; s < 2; ++s) {
        for (uint32_t i = 0; i < kBodySphereCount; ++i) {
            const Sphere& b = bodies[s][i];
            if (!(b.r > 0)) continue;
            const float hit = strength(g.body_hits[s][i]);
            const uint32_t colour = hit > 0 ? with_alpha(kBodyHit, kBodyAlpha + 0.3f * hit) : with_alpha(kBodyColours[s], kBodyAlpha);
            scene->solids.push_back({{b.c[0], b.c[1], b.c[2]}, {b.c[0], b.c[1], b.c[2]}, b.r, colour, false});
        }
    }
    for (const AttackLine& line : g.attack_lines) {
        const float* e = line.ends;
        scene->solids.push_back({{e[0], e[1], e[2]}, {e[3], e[4], e[5]}, kAttackRadius,
                                 with_alpha(kAttack, strength(line.age)), true});
    }
    return scene;
}

// The position reset's tooltip, on the title's hint line, at the right
// (the title's own hints are at the left).
void lay_out_tooltip(Layout& l) {
    const int v = host::active_controller() == host::Controller::kPlayStation ? 1 : 0;
    const Atlas& a = g_atlas;
    const Icon &select = a.tip_select[v], &button = a.tip_button[v];
    const auto icon_width = [](const Icon& i, float h) { return i.height ? h * i.width / i.height : 0.0f; };
    const char* text = "Reset Position";
    const float plus_w = Layout::hint_width(a.labels, kTipPx, "+"), text_w = Layout::hint_width(a.labels, kTipPx, text);
    const float w = icon_width(select, kTipIcon) + 2 + plus_w + 2 + icon_width(button, kTipButton) + 6 + text_w;
    float x = gpu::overlay::kWidth - kTipSide - w;
    l.icon(select, x, kTipY, kTipIcon);
    x += icon_width(select, kTipIcon) + 2;
    l.hint_text(a.labels, kTipPx, x, kTipY + kTipPx * 0.36f, "+", kValue);
    x += plus_w + 2;
    l.icon(button, x, kTipY, kTipButton);
    x += icon_width(button, kTipButton) + 6;
    l.hint_text(a.labels, kTipPx, x, kTipY + kTipPx * 0.36f, text, kValue);
}

void publish(uint8_t* base, const Fighter now[2]) {
    const bool history = ppc::ld32(base, kPracticeSettings + kCommandHistory) == 1;
    // Above the line along the bottom where the title puts its hints (and
    // DAMAGE INFO 2's bars), and the position reset's tooltip.
    const float bottom = kPanelsBottom;
    Layout l;
    l.quads.reserve(1600);
    std::shared_ptr<const gpu::overlay::Scene> scene;
    Camera camera;
    if (g.settings[kHitboxes] && read_camera(base, camera)) {
        Sphere bodies[2][kBodySphereCount];
        for (int s = 0; s < 2; ++s) read_body(base, now[s].player, bodies[s]);
        update_attack_lines(base, now, bodies);
        scene = hitbox_scene(camera, bodies);
    } else {
        start_over_hitboxes();
    }
    g.history_shown = history;
    g.panels_until = seconds() + 0.25;
    // A side's above its 2D fighter's gauge (title/gauge.cpp), when that shows.
    const auto side_bottom = [&](int s) {
        const float top = gauge::top(s);
        return top ? std::min(bottom, top - kAboveGauge) : bottom;
    };
    if (g.settings[kPanels] && g.settings[kPanel1P]) lay_out_side(l, 0, now, side_bottom(0));
    if (g.settings[kPanels] && g.settings[kPanel2P]) lay_out_side(l, 1, now, side_bottom(1));
    if (history) lay_out_history(l);
    // Until the next fighters' frame, and a little longer: frames can come
    // late; once they stop (the pause menu, the round left) the panels go.
    // (level with the higher of the sides' panels: above a 2D fighter's
    // gauge, which can reach under it, as Geese's does)
    std::shared_ptr<const gpu::overlay::Window> window =
        g.settings[kTopCamera] ? top_window(base, now, std::min(side_bottom(0), side_bottom(1))) : nullptr;
    if (!window) g.top.placed = false; // (placed at once when it comes up)
    if (window) {
        // Its frame, under the picture; a label above it.
        const float* r = window->rect;
        l.panel(0, r[0] - 7, r[1] - 26, r[2] + 8, r[3] + 14);
        l.text(g_atlas.labels, kLabelPx, r[0] + 12, r[1] - 7, "Top View", kLabel);
    }
    lay_out_tooltip(l);
    gpu::overlay::show(std::move(l.quads), 0.25, std::move(scene), std::move(window));
}

} // namespace

void fighters_frame(uint8_t* base, const uint32_t fighters[2]) {
    if (g.failed || !fighters[0] || !fighters[1]) return;
    static bool atlas_built = false;
    if (!atlas_built) {
        atlas_built = true;
        if (!build_atlas()) {
            std::fprintf(stderr, "ttt2: warning: the game's fonts are not where expected; no frame data panels\n");
            g.failed = true;
            return;
        }
    }
    const Fighter now[2] = {read(base, fighters[0]), read(base, fighters[1])};
    // Other fighters loaded (a new Practice round): a new session.
    if (g.have_previous && (now[0].moveset != g.previous[0].moveset || now[1].moveset != g.previous[1].moveset)) {
        start_over();
        g.history.clear();
        g.have_previous = false;
    }
    if (g.have_previous) {
        for (int s = 0; s < 2; ++s) {
            const Fighter& f = now[s];
            const Fighter& before = g.previous[s];
            if ((f.move != before.move || f.frame < before.frame) && f.first_active > 0 && f.level != 0) {
                attack_started(g.sides[s], f);
            }
        }
        for (int s = 0; s < 2; ++s) {
            const uint32_t events = now[1 - s].events;
            if (events & (kHit | kBlocked)) connected(s, now[s], now[1 - s], g.previous[1 - s]);
            // Met the wall in a combo (the first splat too, before any wall
            // hit event; an attacker's word has the state too, after its hit).
            Side& side = g.sides[s];
            if (side.in_combo && (events & kKind) == kWall && (g.previous[1 - s].events & kKind) != kWall) side.wall = true;
            if (now[1 - s].cancel & kFree) side.in_combo = false;
        }
        measure(now);
    }
    update_colours(now);
    record_input(now);
    g.previous[0] = now[0];
    g.previous[1] = now[1];
    g.have_previous = true;
    publish(base, now);
}

void reset() { start_over(); }

uint32_t setting(Setting s) { return g.settings[s]; }

float history_right() { return seconds() < g.panels_until && g.history_shown ? kHistoryX1 : 0; }

void set_setting(Setting s, uint32_t value) { g.settings[s] = s == kSlowMotion ? std::min(value, 2u) : value ? 1 : 0; }

// The colour the title draws a fighter in (r3 the fighter) -> r3, four
// floats (red, green, blue, alpha).
uint32_t colour(uint32_t fighter) {
    const Colours& c = g.colours;
    if (!fighter || (fighter != c.ahead && fighter != c.behind) || seconds() > c.until) return 0;
    static const uint32_t colours = [] {
        static constexpr float kAhead[4] = {0.25f, 0.4f, 1.8f, 1}, kBehind[4] = {1.7f, 0.2f, 0.2f, 1};
        const uint32_t at = system_alloc(sizeof(kAhead) + sizeof(kBehind));
        for (int i = 0; i < 4; ++i) {
            uint32_t v;
            std::memcpy(&v, &kAhead[i], sizeof(v));
            ppc::st32(guest_base(), at + 4 * i, v);
            std::memcpy(&v, &kBehind[i], sizeof(v));
            ppc::st32(guest_base(), at + 16 + 4 * i, v);
        }
        return at;
    }();
    return fighter == c.ahead ? colours : colours + 16;
}

} // namespace cafe::title::framedata

PPC_FUNC(sub_04E1A0FC_orig);
PPC_FUNC(sub_04E1A0FC) {
    const uint32_t fighter = ctx.r[3];
    sub_04E1A0FC_orig(ctx, base);
    if (const uint32_t warping = cafe::title::warp::colour(fighter)) ctx.r[3] = warping; // (title/warp.cpp)
    else if (const uint32_t colour = cafe::title::framedata::colour(fighter)) ctx.r[3] = colour;
    else if (const uint32_t flash = cafe::title::gauge::colour(fighter)) ctx.r[3] = flash; // (title/gauge.cpp)
}
