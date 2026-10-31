// The gauge of an added Tekken 7 2D fighter, as Tekken 7 keeps it (its
// executable's rules; the moveset only names the costs and checks).
//
// - A fighter's gauge (player +0xcc8 in Tekken 7) holds 0 to its most
//   (+0xccc: 1000, two stocks of 500; Geese's 1500). Requirement 629 tests
//   it >= param, 635 < param; property 0x81c2 adds its value (EX moves
//   -500, supers -1000, a parry +300) and clamps it (0x14071d1b4).
// - Every frame (0x140713f72), for each fighter that took damage, both it
//   and its opponent gain gauge in percent of that damage: of a blocked
//   attack's damage (+0x7c8; the defender's +0x754 bit 8 set) 50 for the
//   defender and 100 for the attacker, of the health a hit took (+0x7d4)
//   150 and 300; Akuma 37 / 75 / 112 / 225 (Tekken 7's 2019 patch cut his
//   gain by a quarter), Geese 21 / 85 / 63 / 255. The attacker gains none
//   while its move set 0x8228 (+0x6b4: EX moves, Focus Attack, supers).
// - The gauge empties at a match's start (0x140759a50 for the start kinds
//   0-3, 11-15, 17, 19-21), not at a round's.
// - As a gain or 0x81c2 takes the gauge from below its most to its most,
//   Tekken 7 posts event 0x26 (0x14073d980), whose listener (0x1402d1db0)
//   plays the common sound SE_battle_spgauge_full for Akuma and Eliza (its
//   character ids 32 and 36); no move plays it, and a single stock has none.
// - 0x8229 lights the fighter up (an EX move, a cancel: effect 38 at its
//   body, the fighter drawn yellow a moment).
// The converted moveset uses this file's ids for them (gauge.h); the gains
// follow the title's own state after each fighters' frame: the health a
// fighter lost (+96, 16 bits) and, on the frame it blocked (+1152 bit
// 0x20000000), the blocked attack's damage (+1180).
//
// The HUD is Tekken 7's (its HUD movie SW_UI_HUD_Rage: a panel at each
// bottom corner, a slot per stock that fills from one end and lights up
// when full, EX or SUPER! beside them), baked by the importer into the
// pack's gauge/: gauge.nut its pictures, gauge.ini each clip's frames as
// placed pictures on Tekken 7's 1920 x 1080 screen, the slots' bars and
// their masks (slot 0 the outer one: the gauge fills from the screen's
// edge). The clips play as Tekken 7's HUD code (0x1404c1940 on) plays
// them: a slot that fills plays EX then EX_MAX_01 and stays lit, a
// full gauge plays every slot's EX_MAX_02 and then loops their Super (the
// panel's and the text's too, lightning running), a slot that empties
// shows Normal; EXLight's Start runs as a stock fills, EXFocus's as the
// gauge is spent. A slot's bar is moved along its mask by how full it is
// (0x1404c1b90: 154 pixels a stock).

#include "title/gauge.h"

#include "gpu/overlay.h"
#include "title/framedata.h"
#include "title/image.h"
#include "title/roster.h"

#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <vector>
// A player's item sound (r3 its number, r4 1: the player's own list, by its
// select id; r5 the player), played; title/roster.cpp lends an added fighter
// its list. TTT2's property 0x82f9 (12 << 24 | 1 << 12 | n) ends here.
PPC_FUNC(sub_077537D0);

namespace cafe::title::gauge {
namespace {

namespace fs = std::filesystem;

constexpr uint32_t kHealth = 96, kHitDamage = 1180, kEvents = 1152, kBlocked = 0x20000000, kMove = 280;
constexpr uint32_t kOwnColour = 7840; // four floats the title multiplies the fighter's colours by
constexpr uint32_t kPhase = 2048; // the fighter's round: 0 before it (its intro), 1 READY, 2 FIGHT (Practice: 2 at once)

// The flash: the fighter's colours times yellow, full for a few frames,
// then fading.
constexpr int kFlashFrames = 18, kFlashHold = 4;
constexpr float kYellow[3] = {2.4f, 2.0f, 0.35f};
// Geese's MAX mode: a light blue tint, pulsing slowly while it runs.
constexpr float kLightBlue[3] = {0.75f, 1.15f, 1.85f};
constexpr int kPulseFrames = 60;

constexpr float kScale = gpu::overlay::kWidth / 1920.0f; // Tekken 7's HUD is 1920 x 1080
// Geese's MAX mode (Tekken 7's player +0xcd8, in hundredths of a frame): at
// most 720 frames (0x1434df508, set at start-up), one less every frame
// (0x14078e1e4); the fighter builds no gauge while it runs (0x140714138).
constexpr int32_t kMaxTimer = 720;
// A super's time stop (Tekken 7's 0x828c, slow motion: its value's low 16
// bits the frames, from the frame it is at; 0x828d: the attacker immune):
// the opponent stops, its own frame not run (sub_0414FA10: its move,
// animation, inputs) and held where it is against the battle's pushing and
// knockback, until the frames are over or a fighter is hit. Its hit stun
// waits meanwhile, so a super cancelled into from a string connects
// (Geese's 1,2,1,2 into Double Reppuken: the hit comes at frame 80).
// Tekken 7 shows the attacker meanwhile through a camera of its own (the
// move's 0x8439 / 0x843a: camera animations); here a close-up from the
// side the camera is on, turning and closing in slowly, then the title's
// camera again.
struct Stop {
    uint32_t fighter = 0;
    int frames = 0;
    uint32_t place[3] = {};      // its x, y, z (as they are)
    int16_t health[2] = {};      // the fighters' then
    uint32_t attacker = 0;
    int total = 0;
    float side = 0;              // the camera's side of the attacker (+1, -1; 0: not known yet)
};
Stop g_stop;
uint32_t g_active[2] = {}; // the fighters in play, as of the last fighters' frame
bool stopped(uint32_t fighter) { return g_stop.frames > 0 && fighter == g_stop.fighter; }

// The camera that renders the scene (title/framedata.cpp has its fields):
// eye, target, up at +0x10, +0x20, +0x30, projection +0xA0, view +0xE0
// (row vectors, looking down its -z), the two multiplied at +0x60.
constexpr uint32_t kCameraHolder = 0x1084FEBC, kCameraManager = 732, kRenderCamera = 392;
constexpr uint32_t kEye = 0x10, kTarget = 0x20, kUp = 0x30, kViewProjection = 0x60, kProjection = 0xA0, kView = 0xE0;
constexpr uint32_t kBodySpheres = 2168, kBodySphereSize = 24, kBodySphereCount = 14;
// The close-up: this far from the attacker's chest (mm), from this angle off
// its line to the opponent (radians), a little above it, over the stop.
constexpr float kStopDistance[2] = {3200, 2400}, kStopAngle[2] = {1.05f, 0.55f}, kStopAbove = 150;

float ldf(uint8_t* base, uint32_t at) {
    const uint32_t bits = ppc::ld32(base, at);
    float v;
    std::memcpy(&v, &bits, 4);
    return v;
}
void stf(uint8_t* base, uint32_t at, float v) {
    uint32_t bits;
    std::memcpy(&bits, &v, 4);
    ppc::st32(base, at, bits);
}

void stop_camera(uint8_t* base) {
    const uint32_t holder = ppc::ld32(base, kCameraHolder);
    const uint32_t manager = holder ? ppc::ld32(base, holder + kCameraManager) : 0;
    const uint32_t camera = manager ? ppc::ld32(base, manager + kRenderCamera) : 0;
    if (!camera || !g_stop.attacker) return;
    // The attacker's chest (its body spheres' middle, up to halfway to the
    // highest) and its line to the opponent.
    float middle[3] = {}, top = -1e9f;
    for (uint32_t i = 0; i < kBodySphereCount; ++i) {
        const uint32_t at = g_stop.attacker + kBodySpheres + kBodySphereSize * i;
        for (int k = 0; k < 3; ++k) middle[k] += ldf(base, at + 4 * k) / kBodySphereCount;
        top = std::max(top, ldf(base, at + 4));
    }
    const float chest = (middle[1] + top) / 2;
    float fx = ldf(base, g_stop.fighter) - middle[0], fz = ldf(base, g_stop.fighter + 8) - middle[2];
    const float length = std::hypot(fx, fz);
    if (length < 1) return;
    fx /= length, fz /= length;
    const float sx = -fz, sz = fx; // (its side)
    if (g_stop.side == 0) {
        const float ex = ldf(base, camera + kEye) - middle[0], ez = ldf(base, camera + kEye + 8) - middle[2];
        g_stop.side = ex * sx + ez * sz >= 0 ? 1.0f : -1.0f;
    }
    const float t = 1.0f - float(g_stop.frames) / float(std::max(1, g_stop.total)); // 0 to 1 over the stop
    const float ease = t * t * (3 - 2 * t);
    const float distance = kStopDistance[0] + (kStopDistance[1] - kStopDistance[0]) * ease;
    const float angle = kStopAngle[0] + (kStopAngle[1] - kStopAngle[0]) * ease;
    const float target[3] = {middle[0], chest, middle[2]};
    const float eye[3] = {target[0] + (fx * std::cos(angle) + g_stop.side * sx * std::sin(angle)) * distance,
                          chest + kStopAbove,
                          target[2] + (fz * std::cos(angle) + g_stop.side * sz * std::sin(angle)) * distance};
    // Its axes: back from the target to the eye, right = up x back, up = back x right.
    float back[3] = {eye[0] - target[0], eye[1] - target[1], eye[2] - target[2]};
    const float bl = std::hypot(back[0], back[1], back[2]);
    for (float& v : back) v /= bl;
    float right[3] = {back[2], 0, -back[0]};
    const float rl = std::hypot(right[0], right[2]);
    right[0] /= rl, right[2] /= rl;
    const float up[3] = {back[1] * right[2] - back[2] * right[1], back[2] * right[0] - back[0] * right[2],
                         back[0] * right[1] - back[1] * right[0]};
    const float* axes[3] = {right, up, back};
    float view[16], projection[16];
    for (int r = 0; r < 3; ++r) {
        for (int c = 0; c < 3; ++c) view[4 * r + c] = axes[c][r];
        view[4 * r + 3] = 0;
    }
    for (int c = 0; c < 3; ++c) view[12 + c] = -(axes[c][0] * eye[0] + axes[c][1] * eye[1] + axes[c][2] * eye[2]);
    view[15] = 1;
    for (int i = 0; i < 16; ++i) projection[i] = ldf(base, camera + kProjection + 4 * i);
    for (int k = 0; k < 3; ++k) {
        stf(base, camera + kEye + 4 * k, eye[k]);
        stf(base, camera + kTarget + 4 * k, target[k]);
        stf(base, camera + kUp + 4 * k, k == 1 ? 1.0f : 0.0f);
    }
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c) {
            float v = 0;
            for (int k = 0; k < 4; ++k) v += view[4 * r + k] * projection[4 * k + c];
            stf(base, camera + kView + 4 * (4 * r + c), view[4 * r + c]);
            stf(base, camera + kViewProjection + 4 * (4 * r + c), v);
        }
}
// Tekken 7 draws it in its screen's bottom corners, under its long life
// bars. Here each side's sits under its own life bar: its outer end (the
// left one's left, the right one's right) where that bar's frame ends,
// its bottom a little above the title's own texts along the screen's
// bottom (Survival's WINS: n, the highest of them; Arcade's stage, time
// and Promotion Chance; the mode's name), as the panel shows at rest.
// Practice has none of those texts: there its bottom is a little above
// the line its frame data panels stand on (its hints and DAMAGE INFO 2's
// bars are below it), so the panels, above it, stay under the title's
// DAMAGE readout. The left one moves right of Practice's input history,
// should that reach further. The places are the title's HUD's at its full
// size, on the TV image (1280 x 720; its life bars are not quite
// mirrored): its HUD size option draws its HUD smaller about the screen's
// middle (sub_052EA750 shrinks the viewport), the life bars with it. The
// texts were seen at the option's default only, and not every title text
// follows the option (Practice's DAMAGE readout stays put): the gauge
// never goes lower than where it clears them at the default. The gauge
// keeps Tekken 7's size.
constexpr uint32_t kHudScale = 0x107C9908; // the HUD size: (85 + the option's n) / 100, 0.86 by default (n 1)
constexpr float kDefaultHudSize = 0.86f;
constexpr float kLifeBarLeft = 83.6f, kLifeBarRight = 1190.6f; // the life bars' frames' outer ends
constexpr float kTextsTop = 622.6f, kAboveTexts = 8, kBesideHistory = 6;
float g_shift = 0, g_lift = 0; // (this frame's side's, Tekken 7's units: right, up)
float g_tops[2] = {};                            // the sides' tops as last shown (0: none)
std::chrono::steady_clock::time_point g_tops_until; // and until when they show
constexpr int kMaxSlots = 4;

// ------------------------------------------------------------------------------------- the HUD's data
struct Picture {
    float x0 = 0, y0 = 0, x1 = 0, y1 = 0; // on Tekken 7's screen (x1 < x0: mirrored)
    float u0 = 0, v0 = 0, u1 = 0, v1 = 0; // texels of gauge.nut
    uint32_t mult = 0xFFFFFFFF, add = 0;  // as overlay::Quad's
};
struct Clip {
    std::vector<std::vector<Picture>> frames;
    std::map<std::string, std::pair<int, int>> labels; // first and last frame
    std::pair<int, int> label(const std::string& name) const {
        const auto it = labels.find(name);
        return it == labels.end() ? std::pair{-1, -1} : it->second;
    }
};
struct Bar {
    bool present = false;
    Picture picture;                      // full
    float mask[4] = {};                   // x0 y0 x1 y1
    float slide = 1;                      // the way it moves as it fills
};
struct Side {
    std::map<std::string, Clip> clips;
    Bar bars[kMaxSlots];
    // The panel at rest (its clips' last frames, not the effects; their
    // visible texels): across its frame (its bars and base clips), up and
    // down all it shows.
    float left = 0, right = 0, top = 0, bottom = 0;
};
struct Hud {
    Side sides[2];
    bool power = false;    // Geese's power gauge (else Akuma's / Eliza's slots)
    Rgba image;            // gauge.nut's picture
    uint32_t atlas_y = 0;  // where it is in the HUD layer's atlas
};

// What a clip shows: frames `frame` to `last`, then `next` (a range looped;
// -1: the last frame held).
struct Play {
    int frame = 0, last = 0, next_first = -1, next_last = -1;
    bool hidden = false;
    void still(int at) { frame = last = at, next_first = -1, hidden = false; }
    void hide() { hidden = true; }
    void run(std::pair<int, int> from, std::pair<int, int> to, bool loop) {
        if (from.first < 0 || to.first < 0) return;
        frame = from.first, last = to.second, hidden = false;
        next_first = loop ? to.first : -1, next_last = to.second;
    }
    void step() {
        if (hidden) return;
        if (frame < last) ++frame;
        else if (next_first >= 0) frame = next_first, last = next_last;
    }
};

struct Player {
    int32_t value = 0;
    int slot = -1;
    int16_t health = 0;
    bool health_known = false;
    uint32_t no_gain_move = 0; // the move kNoGain was set in (0: none)
    int flash = 0;             // frames of the flash left
    uint32_t colour = 0;       // its colour while it flashes (guest, four floats)
    // the HUD
    int32_t shown = -1;        // the value drawn last (-1: none yet)
    int full = 0;              // its stocks full then
    bool max_shown = false;    // the MAX mode drawn then
    std::map<std::string, Play> plays; // the clips', by name
    int32_t max_timer = 0;     // Geese's MAX mode: frames left
    int32_t heard = -1;        // the value the full sound saw last (-1: none yet)
};
std::map<uint32_t, Player> g_players; // by fighter

struct Fighter {
    Config config;
    std::optional<Hud> hud;
};
std::map<int, Fighter> g_fighters; // by slot
uint32_t g_atlas_width = 0, g_atlas_height = 0;
bool g_atlas_set = false;
// The HUD shows with the title's own, as Tekken 7's shows with its other
// HUD: from READY (the fighters' round phase, not in intros nor the select
// screen's previews), not while a fighter is knocked out.

const Fighter* fighter_of(int slot) {
    const auto it = g_fighters.find(slot);
    return it == g_fighters.end() || it->second.config.max <= 0 ? nullptr : &it->second;
}

bool read_picture(std::istringstream& s, Picture& p) {
    std::string mult, add;
    if (!(s >> p.x0 >> p.y0 >> p.x1 >> p.y1 >> p.u0 >> p.v0 >> p.u1 >> p.v1)) return false;
    if (s >> mult >> add) {
        p.mult = static_cast<uint32_t>(std::strtoul(mult.c_str(), nullptr, 16));
        p.add = static_cast<uint32_t>(std::strtoul(add.c_str(), nullptr, 16));
    }
    return true;
}

// Where a picture shows on Tekken 7's screen: the box of its texels at
// least half covering (an added picture's by their brightness; soft glows'
// faint edges left out), x0 y0 x1 y1 (mirrored pictures too). Nowhere:
// x0 = y0 = 1e9, x1 = y1 = -1e9.
std::array<float, 4> visible_box(const Rgba& image, const Picture& p) {
    constexpr std::array<float, 4> kNowhere = {1e9f, 1e9f, -1e9f, -1e9f};
    if (p.u0 == p.u1 || p.v0 == p.v1) return kNowhere;
    const auto texel = [](float a, uint32_t size) { return static_cast<uint32_t>(std::clamp(a, 0.0f, float(size))); };
    const uint32_t u0 = texel(std::min(p.u0, p.u1), image.width), u1 = texel(std::max(p.u0, p.u1), image.width);
    const uint32_t v0 = texel(std::min(p.v0, p.v1), image.height), v1 = texel(std::max(p.v0, p.v1), image.height);
    const bool added = (p.add & 0xFF) == 0xFF;
    const auto shows = [&](const uint8_t* t) {
        uint32_t cover = t[3] * (p.mult & 0xFF) / 255;
        if (added) cover = cover * std::max({t[0], t[1], t[2]}) / 255;
        return cover >= 128;
    };
    int column0 = INT32_MAX, column1 = -1, row0 = -1, row1 = -1;
    for (uint32_t v = v0; v < v1; ++v)
        for (uint32_t u = u0; u < u1; ++u)
            if (shows(image.at(u, v))) {
                if (row0 < 0) row0 = static_cast<int>(v);
                row1 = static_cast<int>(v);
                column0 = std::min(column0, static_cast<int>(u)), column1 = std::max(column1, static_cast<int>(u));
            }
    if (row0 < 0) return kNowhere;
    const auto x = [&](float u) { return p.x0 + (u - p.u0) / (p.u1 - p.u0) * (p.x1 - p.x0); };
    const auto y = [&](float v) { return p.y0 + (v - p.v0) / (p.v1 - p.v0) * (p.y1 - p.y0); };
    const float xa = x(float(column0)), xb = x(float(column1 + 1)), ya = y(float(row0)), yb = y(float(row1 + 1));
    return {std::min(xa, xb), std::min(ya, yb), std::max(xa, xb), std::max(ya, yb)};
}

std::optional<Hud> read_hud(const fs::path& directory) {
    std::ifstream in(directory / "gauge.ini");
    std::ifstream nut(directory / "gauge.nut", std::ios::binary);
    if (!in || !nut) return std::nullopt;
    const std::vector<uint8_t> file((std::istreambuf_iterator<char>(nut)), std::istreambuf_iterator<char>());
    const auto textures = ntp3::parse(file);
    auto image = textures && !textures->empty() ? ntp3::decode((*textures)[0]) : std::nullopt;
    if (!image) return std::nullopt;
    Hud hud;
    hud.image = std::move(*image);
    std::vector<Picture>* frame = nullptr;
    std::string line;
    while (std::getline(in, line)) {
        line = line.substr(0, line.find('#'));
        std::istringstream s(line);
        std::string kind, side_name, clip;
        if (!(s >> kind)) continue;
        if (kind == "style") {
            std::string style;
            s >> style;
            hud.power = style == "power";
            continue;
        }
        if (kind == "q") {
            Picture p;
            if (frame && read_picture(s, p)) frame->push_back(p);
            continue;
        }
        if (!(s >> side_name)) continue;
        Side& side = hud.sides[side_name == "R"];
        if (kind == "bar" || kind == "mask") {
            int k;
            if (!(s >> k) || k < 0 || k >= kMaxSlots) continue;
            Bar& bar = side.bars[k];
            if (kind == "bar" && !bar.present) bar.present = read_picture(s, bar.picture);
            else s >> bar.mask[0] >> bar.mask[1] >> bar.mask[2] >> bar.mask[3] >> bar.slide;
        } else if (kind == "clip") {
            size_t frames = 0;
            if (s >> clip >> frames) side.clips[clip].frames.resize(std::min<size_t>(frames, 1000));
        } else if (kind == "label") {
            std::string label;
            int first, last;
            if (s >> clip >> label >> first >> last) side.clips[clip].labels[label] = {first, last};
        } else if (kind == "frame") {
            size_t n;
            frame = nullptr;
            if (s >> clip >> n && n < side.clips[clip].frames.size()) frame = &side.clips[clip].frames[n];
        }
    }
    for (Side& side : hud.sides) { // the panel's extent at rest
        float box[4] = {1e9f, 1e9f, -1e9f, -1e9f}, frame[2] = {1e9f, -1e9f};
        const auto take = [&](const Picture& p, bool in_frame) {
            const auto b = visible_box(hud.image, p);
            for (int k = 0; k < 2; ++k) box[k] = std::min(box[k], b[k]), box[k + 2] = std::max(box[k + 2], b[k + 2]);
            if (in_frame) frame[0] = std::min(frame[0], b[0]), frame[1] = std::max(frame[1], b[2]);
        };
        for (const Bar& bar : side.bars)
            if (bar.present) take(bar.picture, true);
        for (const auto& [name, clip] : side.clips) // (Geese's last frames: "Stay")
            if (!clip.frames.empty() && name != "light" && name != "lightning" && name != "focus")
                for (const Picture& p : clip.frames.back())
                    take(p, name == "base" || name == "base1" || name == "static" || name == "num0");
        if (frame[1] > frame[0]) side.left = frame[0], side.right = frame[1];
        if (box[3] > box[1]) side.top = box[1], side.bottom = box[3];
    }
    return hud;
}

// Every slot's pictures, one under another, as the HUD layer's atlas.
void set_atlas() {
    uint32_t width = 0, height = 0;
    for (auto& [slot, f] : g_fighters) {
        if (!f.hud) continue;
        f.hud->atlas_y = height;
        width = std::max(width, f.hud->image.width);
        height += f.hud->image.height;
    }
    if (!height) return;
    auto atlas = std::make_shared<gpu::overlay::Atlas>();
    atlas->width = width;
    atlas->height = height;
    atlas->pixels.assign(size_t{width} * height * 4, 0);
    for (auto& [slot, f] : g_fighters) {
        if (!f.hud) continue;
        const Rgba& image = f.hud->image;
        for (uint32_t y = 0; y < image.height; ++y)
            std::memcpy(&atlas->pixels[(size_t{f.hud->atlas_y + y} * width) * 4], image.at(0, y), size_t{image.width} * 4);
    }
    g_atlas_width = width;
    g_atlas_height = height;
    gpu::overlay::set_hud_atlas(std::move(atlas));
}

int32_t clamp(int32_t value, int32_t max) { return std::clamp(value, 0, max); }

// TTT2_TRACE_GAUGE, read once (Windows' getenv takes a lock and walks the
// whole environment; the tests run per requirement every frame).
bool trace_gauge() {
    static const bool trace = std::getenv("TTT2_TRACE_GAUGE") != nullptr;
    return trace;
}

// What a gauge holds at a match's start: none (TTT2_GAUGE_START, for tests).
int32_t start_value() {
    const char* v = std::getenv("TTT2_GAUGE_START");
    return v ? std::atoi(v) : 0;
}

Player& entry(uint32_t address) {
    const auto [it, made] = g_players.try_emplace(address);
    if (made) it->second.value = start_value();
    return it->second;
}

Player& player(uint32_t address, int slot) {
    Player& p = entry(address);
    p.slot = slot;
    if (const Fighter* f = fighter_of(slot)) p.value = clamp(p.value, f->config.max);
    return p;
}

// --------------------------------------------------------------------------------------- the flash
// The fighter's own colours times `tint` (`t`: 0 none, 1 all of it).
void write_colour(uint32_t fighter, Player& p, const float (&tint)[3], float t) {
    if (!p.colour) p.colour = system_alloc(16);
    for (int i = 0; i < 4; ++i) {
        uint32_t bits = ppc::ld32(guest_base(), fighter + kOwnColour + 4 * i);
        float own;
        std::memcpy(&own, &bits, 4);
        const float value = own * (i < 3 ? 1.0f + (tint[i] - 1.0f) * t : 1.0f);
        std::memcpy(&bits, &value, 4);
        ppc::st32(guest_base(), p.colour + 4 * i, bits);
    }
}

// ------------------------------------------------------------------------------------------ the HUD
void add_quad(std::vector<gpu::overlay::Quad>& out, const Hud& hud, Picture p, const float* mask = nullptr) {
    if (mask) { // (an unmirrored picture)
        const float x0 = std::max(p.x0, std::min(mask[0], mask[2])), x1 = std::min(p.x1, std::max(mask[0], mask[2]));
        const float y0 = std::max(p.y0, std::min(mask[1], mask[3])), y1 = std::min(p.y1, std::max(mask[1], mask[3]));
        if (x0 >= x1 || y0 >= y1) return;
        const auto at = [](float a, float lo, float hi, float ulo, float uhi) {
            return ulo + (uhi - ulo) * (a - lo) / (hi - lo);
        };
        const Picture q = p;
        p.u0 = at(x0, q.x0, q.x1, q.u0, q.u1), p.u1 = at(x1, q.x0, q.x1, q.u0, q.u1);
        p.v0 = at(y0, q.y0, q.y1, q.v0, q.v1), p.v1 = at(y1, q.y0, q.y1, q.v0, q.v1);
        p.x0 = x0, p.x1 = x1, p.y0 = y0, p.y1 = y1;
    }
    if (p.x1 < p.x0) std::swap(p.x0, p.x1), std::swap(p.u0, p.u1);
    if (p.y1 < p.y0) std::swap(p.y0, p.y1), std::swap(p.v0, p.v1);
    gpu::overlay::Quad q;
    q.x0 = (p.x0 + g_shift) * kScale, q.y0 = (p.y0 - g_lift) * kScale;
    q.x1 = (p.x1 + g_shift) * kScale, q.y1 = (p.y1 - g_lift) * kScale;
    q.u0 = p.u0 / g_atlas_width, q.u1 = p.u1 / g_atlas_width;
    q.v0 = (hud.atlas_y + p.v0) / g_atlas_height, q.v1 = (hud.atlas_y + p.v1) / g_atlas_height;
    q.top = q.bottom = p.mult;
    q.add = p.add;
    out.push_back(q);
}

void add_clip(std::vector<gpu::overlay::Quad>& out, const Hud& hud, const Side& side, const char* name,
              const Play& play) {
    const auto it = side.clips.find(name);
    if (play.hidden || it == side.clips.end() || it->second.frames.empty()) return;
    const auto& frames = it->second.frames;
    for (const Picture& p : frames[std::clamp<size_t>(play.frame, 0, frames.size() - 1)]) add_quad(out, hud, p);
}

// A bar `fill` (0 to 1) along its mask, from where it starts.
void add_bar(std::vector<gpu::overlay::Quad>& out, const Hud& hud, const Bar& bar, float fill) {
    if (!bar.present || fill <= 0) return;
    Picture moved = bar.picture;
    const float dx = (std::min(fill, 1.0f) - 1) * std::fabs(bar.mask[2] - bar.mask[0]) * bar.slide;
    moved.x0 += dx, moved.x1 += dx;
    add_quad(out, hud, moved, bar.mask);
}

// Akuma's and Eliza's: a slot per stock, lit when full (CSwfHUDRage, BSwfHUDELZGauge).
void plays_ex(const Side& side, const Config& config, Player& p) {
    const auto clip = [&](const std::string& name) -> const Clip& {
        static const Clip none;
        const auto it = side.clips.find(name);
        return it == side.clips.end() ? none : it->second;
    };
    const auto play = [&](const std::string& name) -> Play& { return p.plays[name]; };
    const int stocks = std::clamp(config.max / std::max(1, config.stock), 1, kMaxSlots);
    const int full = std::min(stocks, p.value / std::max(1, config.stock));
    const auto slot = [](int k) { return "slot" + std::to_string(k); };
    if (p.shown < 0) { // a new fighter or match: the clips as the gauge is
        for (const char* name : {"base", "cover", "text"}) play(name).still(0);
        for (const char* name : {"light", "focus", "lightning"}) play(name).hide(); // (their first frames: effects)
        for (int k = 0; k < stocks; ++k) play(slot(k)).still(0);
        p.full = 0;
    }
    if (full != p.full) {
        if (full == stocks) { // every slot: EX_MAX_02, then Super looped
            for (int k = 0; k < stocks; ++k) play(slot(k)).run(clip(slot(k)).label("EX_MAX_02"), clip(slot(k)).label("Super"), true);
            for (const char* name : {"base", "text"}) play(name).run(clip(name).label("Super"), clip(name).label("Super"), true);
            play("lightning").run(clip("lightning").label("On"), clip("lightning").label("On"), true);
        } else {
            for (int k = 0; k < stocks; ++k) {
                const Clip& c = clip(slot(k));
                if (k >= full) play(slot(k)).still(0);
                else if (k >= p.full || p.full == stocks) { // newly full (or no longer every one): lit
                    const auto max1 = c.label("EX_MAX_01");
                    play(slot(k)).run(c.label("EX"), max1.first >= 0 ? max1 : c.label("EX"), false);
                }
            }
            play("base").still(0);
            play("lightning").hide();
            if (full == 0) play("text").still(0);
            else play("text").run(clip("text").label("EX"), clip("text").label("EX"), false);
        }
        if (full > p.full) play("light").run(clip("light").label("Start"), clip("light").label("Start"), false);
    }
    p.full = full;
}

// Geese's: a power bar for the stock being filled with their count beside it, MAXIMUM when they are all full, the
// MAX mode's timer and MAXMODE (SwfHUDMRYGauge, 0x1404c7520: 424 pixels a stock).
void plays_power(const Side& side, const Config& config, Player& p) {
    const auto clip = [&](const std::string& name) -> const Clip& {
        static const Clip none;
        const auto it = side.clips.find(name);
        return it == side.clips.end() ? none : it->second;
    };
    const auto play = [&](const std::string& name) -> Play& { return p.plays[name]; };
    const auto stay = [&](const std::string& name) { play(name).run(clip(name).label("Start"), clip(name).label("Stay"), false); };
    const int stocks = std::max(1, config.max / std::max(1, config.stock));
    const int count = std::min(5, p.value / std::max(1, config.stock));
    const bool max_on = p.max_timer > 0;
    if (p.shown < 0) {
        for (const char* name : {"static", "gauge1"}) play(name).still(0);
        stay("base1");
        for (const char* name : {"max1", "text1", "base2", "gauge2", "text2", "focus"}) play(name).hide();
        p.full = -1, p.max_shown = false; // (a full gauge's MAXIMUM shows from the start)
    }
    for (int n = 0; n <= 5; ++n) // the count shown: its own clip (the number set in it)
        if (n != count) play("num" + std::to_string(n)).hide();
    Play& number = play("num" + std::to_string(count));
    if (count != p.full || number.hidden) {
        const auto& c = clip("num" + std::to_string(count));
        if (count == p.full) number.still(0);
        else if (p.full < 0) number.still(0);
        else number.run(c.label(count > p.full ? "Up" : "Down"), c.label(count > p.full ? "Up" : "Down"), false);
        if (count >= stocks && p.full < stocks) {
            play("max1").run(clip("max1").label("Normal"), clip("max1").label("Normal"), true);
            stay("text1");
        } else if (count < stocks) {
            play("max1").hide(), play("text1").hide();
        }
    }
    if (max_on != p.max_shown) {
        if (max_on) {
            stay("base2"), stay("text2");
            play("gauge2").run(clip("gauge2").label("Normal"), clip("gauge2").label("Normal"), true);
        } else {
            for (const char* name : {"base2", "gauge2", "text2"}) play(name).hide();
        }
    }
    p.full = count, p.max_shown = max_on;
}

void draw(std::vector<gpu::overlay::Quad>& out, const Hud& hud, const Config& config, Player& p, int s) {
    const Side& side = hud.sides[s];
    const int32_t value = p.value;
    if (hud.power) plays_power(side, config, p);
    else plays_ex(side, config, p);
    if (p.shown >= 0 && value < p.shown) {
        const auto it = side.clips.find("focus");
        if (it != side.clips.end()) p.plays["focus"].run(it->second.label("Start"), it->second.label("Start"), false);
    }
    p.shown = value;
    const auto clip = [&](const std::string& name) { add_clip(out, hud, side, name.c_str(), p.plays[name]); };
    if (hud.power) {
        const int stock = std::max(1, config.stock);
        const float fill = value >= config.max ? 1.0f : float(value % stock) / float(stock);
        clip("base1");
        add_bar(out, hud, side.bars[0], fill);
        for (const char* name : {"gauge1", "max1", "text1", "base2"}) clip(name);
        add_bar(out, hud, side.bars[1], float(p.max_timer) / float(kMaxTimer));
        for (const char* name : {"gauge2", "text2"}) clip(name);
        for (int n = 0; n <= 5; ++n) clip("num" + std::to_string(n));
        clip("static");
        clip("focus");
    } else {
        const int stocks = std::clamp(config.max / std::max(1, config.stock), 1, kMaxSlots);
        clip("base");
        for (int k = 0; k < stocks; ++k) {
            add_bar(out, hud, side.bars[k],
                    std::clamp(float(value - k * config.stock) / float(config.stock), 0.0f, 1.0f));
            clip("slot" + std::to_string(k));
        }
        for (const char* name : {"cover", "text", "light", "lightning", "focus"}) clip(name);
    }
    for (auto& [name, play] : p.plays) {
        play.step();
        // effects that ran once go
        if ((name == "light" || name == "focus") && play.frame >= play.last && play.next_first < 0) play.hide();
    }
}

} // namespace

bool parse(const std::string& value, Config& config) {
    std::istringstream s(value);
    Config c;
    if (!(s >> c.max >> c.stock)) return false;
    for (int32_t& g : c.gain)
        if (!(s >> g)) break;
    if (!(s >> c.full_sound)) c.full_sound = -1; // (a failed read stores 0)
    if (c.max <= 0 || c.stock <= 0) return false;
    config = c;
    return true;
}

void configure(int slot, const Config& config, const fs::path& pack) {
    Fighter& f = g_fighters[slot];
    f.config = config;
    f.hud = read_hud(pack / "gauge");
    if (!f.hud) std::fprintf(stderr, "ttt2: %s has a gauge but no gauge/ pictures; it is not shown\n",
                             pack.filename().string().c_str());
    g_atlas_set = false;
}

bool requirement(uint32_t address, int slot, uint32_t kind, uint32_t param, bool& result) {
    if (kind == kMaxOn) { // (Tekken 7's 176 tests the timer > 0 whatever its parameter)
        result = fighter_of(slot) && player(address, slot).max_timer > 0;
        return true;
    }
    if (kind != kAtLeast && kind != kBelow) return false;
    const Fighter* f = fighter_of(slot);
    const int32_t value = f ? player(address, slot).value : 0;
    result = kind == kAtLeast ? value >= static_cast<int32_t>(param) : value < static_cast<int32_t>(param);
    if (trace_gauge()) {
        static uint32_t last_key = 0;
        const uint32_t key = address ^ (kind << 20) ^ param ^ (result << 31) ^ uint32_t(value) << 8;
        if (key != last_key)
            std::fprintf(stderr, "ttt2: gauge: test %08X slot %d %s %u: %d -> %d\n", address, slot,
                         kind == kAtLeast ? ">=" : "<", param, value, result);
        last_key = key;
    }
    return true;
}

bool property(uint32_t address, int slot, uint32_t id, uint32_t value) {
    if (id != kAdd && id != kNoGain && id != kFlash && id != kMaxAdd && id != kStop) return false;
    if (id == kStop) {
        const int s = address == g_active[0] ? 0 : address == g_active[1] ? 1 : -1;
        if (s < 0 || !g_active[1 - s]) return true;
        uint8_t* base = guest_base();
        g_stop = {g_active[1 - s], static_cast<int>(value & 0xFFFF)};
        g_stop.attacker = address, g_stop.total = g_stop.frames;
        for (int i = 0; i < 3; ++i) g_stop.place[i] = ppc::ld32(base, g_stop.fighter + 4 * i);
        for (int k = 0; k < 2; ++k) g_stop.health[k] = static_cast<int16_t>(ppc::ld16(base, g_active[k] + kHealth));
        if (trace_gauge())
            std::fprintf(stderr, "ttt2: gauge: %08X stops %08X for %d frames\n", address, g_stop.fighter, g_stop.frames);
        return true;
    }
    const Fighter* f = fighter_of(slot);
    if (!f) return true;
    Player& p = player(address, slot);
    if (id == kAdd) {
        p.value = clamp(p.value + static_cast<int32_t>(value), f->config.max);
        if (trace_gauge())
            std::fprintf(stderr, "ttt2: gauge: %08X %+d -> %d\n", address, static_cast<int32_t>(value), p.value);
    } else if (id == kMaxAdd) {
        p.max_timer = std::clamp(p.max_timer + static_cast<int32_t>(value), 0, kMaxTimer);
        if (trace_gauge())
            std::fprintf(stderr, "ttt2: gauge: %08X MAX %+d -> %d\n", address, static_cast<int32_t>(value), p.max_timer);
    } else if (id == kNoGain) {
        p.no_gain_move = value ? ppc::ld32(guest_base(), address + kMove) : 0;
    } else {
        p.flash = kFlashFrames;
    }
    return true;
}

void situation(uint32_t kind) {
    // The kinds that keep the gauge: the title's round end (26: the battle's
    // state 5, sub_03A49AA0, and sub_03A5BED0, after every KO), its next
    // round (4, 6) and a match won (7), as Tekken 7 keeps it between rounds
    // (its 0x140759a50 keeps 4-10, 16 and 18). Every other kind empties it:
    // 0 / 1 / 3 a match's first round (Arcade's next stage too), 12 / 15
    // Practice, 23 the fighters' load before a match, 24 the start.
    static constexpr uint32_t kKeep[] = {4, 5, 6, 7, 8, 9, 10, 16, 18, 26};
    if (trace_gauge()) std::fprintf(stderr, "ttt2: gauge: situation %u\n", kind);
    const bool keep = std::find(std::begin(kKeep), std::end(kKeep), kind) != std::end(kKeep);
    for (auto& [address, p] : g_players) {
        p.max_timer = 0; // (a round's start ends a MAX mode)
        p.no_gain_move = 0;
        p.flash = 0;
        p.health_known = false; // (the fighters' health is set anew)
        if (keep) continue;
        p.value = start_value();
        p.shown = -1;
        p.heard = -1;
    }
    g_stop = {};
}

void fighters_frame(PPCContext& ctx, uint8_t* base, const uint32_t fighters[2], bool practice) {
    if (g_fighters.empty()) return;
    g_active[0] = fighters[0], g_active[1] = fighters[1];
    if (g_stop.frames > 0) { // (over early when a fighter is hit, or another is in play)
        bool over = --g_stop.frames <= 0 || (g_stop.fighter != fighters[0] && g_stop.fighter != fighters[1]);
        for (int k = 0; k < 2; ++k)
            over |= fighters[k] && static_cast<int16_t>(ppc::ld16(base, fighters[k] + kHealth)) < g_stop.health[k];
        if (over) g_stop = {};
    }
    if (trace_gauge()) { // the moves, as they start
        static uint32_t shown[2] = {};
        static const auto start = std::chrono::steady_clock::now();
        for (int s = 0; s < 2; ++s) {
            const uint32_t move = fighters[s] ? ppc::ld32(base, fighters[s] + kMove) : 0;
            if (move == shown[s]) continue;
            shown[s] = move;
            const uint32_t name = move ? ppc::ld32(base, move) : 0;
            std::fprintf(stderr, "ttt2: gauge: %.2f s side %d %s (gauge %d)\n",
                         std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count(), s,
                         name ? reinterpret_cast<const char*>(base + name) : "?",
                         fighters[s] ? entry(fighters[s]).value : 0);
        }
    }
    // The gains: each fighter that took damage, and its opponent.
    int32_t gains[2] = {0, 0};
    const Fighter* who[2] = {nullptr, nullptr};
    int slots[2] = {-1, -1};
    for (int s = 0; s < 2; ++s) {
        slots[s] = title::added_slot(fighters[s]);
        who[s] = fighter_of(slots[s]);
    }
    for (int s = 0; s < 2; ++s) {
        const uint32_t defender = fighters[s], attacker = fighters[1 - s];
        if (!defender) continue;
        Player& d = entry(defender);
        const int16_t health = static_cast<int16_t>(ppc::ld16(base, defender + kHealth));
        const int32_t lost = d.health_known ? d.health - health : 0;
        d.health = health;
        d.health_known = true;
        const bool blocked = ppc::ld32(base, defender + kEvents) & kBlocked;
        const int32_t damage = blocked ? static_cast<int32_t>(ppc::ld32(base, defender + kHitDamage)) : lost;
        if (damage <= 0) continue;
        const int32_t before[2] = {gains[0], gains[1]};
        if (who[s] && d.max_timer <= 0) gains[s] += damage * who[s]->config.gain[blocked ? 0 : 2] / 100;
        if (attacker && who[1 - s]) {
            Player& a = entry(attacker);
            const bool no_gain = (a.no_gain_move && a.no_gain_move == ppc::ld32(base, attacker + kMove)) ||
                                 a.max_timer > 0;
            if (!no_gain) gains[1 - s] += damage * who[1 - s]->config.gain[blocked ? 1 : 3] / 100;
        }
        if (trace_gauge())
            std::fprintf(stderr, "ttt2: gauge: side %d %s %d at frame %u: defender +%d, attacker +%d\n", s,
                         blocked ? "blocked" : "lost", damage, ppc::ld32(base, attacker ? attacker + 212 : defender + 212),
                         gains[s] - before[s], gains[1 - s] - before[1 - s]);
    }
    for (int s = 0; s < 2; ++s) {
        if (!who[s] || !gains[s]) continue;
        Player& p = player(fighters[s], slots[s]);
        p.value = clamp(p.value + gains[s], who[s]->config.max);
    }
    // The full sound: as a gauge reaches its most from below (this frame's
    // costs, adds and gains done), as Tekken 7's gauge-full event plays it.
    for (int s = 0; s < 2; ++s) {
        if (!who[s]) continue;
        Player& p = player(fighters[s], slots[s]);
        const int32_t n = who[s]->config.full_sound, most = who[s]->config.max;
        if (n >= 0 && p.heard >= 0 && p.heard < most && p.value >= most) {
            const PPCContext saved = ctx;
            ctx.r[3] = static_cast<uint32_t>(n), ctx.r[4] = 1, ctx.r[5] = fighters[s];
            sub_077537D0(ctx, base);
            ctx = saved;
            if (trace_gauge())
                std::fprintf(stderr, "ttt2: gauge: %08X full: item sound %d\n", fighters[s], n);
        }
        p.heard = p.value;
    }
    // The MAX modes run down.
    for (auto& [address, p] : g_players)
        if (p.max_timer > 0) --p.max_timer;
    // The flashes, and the MAX modes' tint (fading out over their last frames).
    for (auto& [address, p] : g_players) {
        if (p.flash > 0) {
            const int fade = kFlashFrames - kFlashHold;
            write_colour(address, p, kYellow, p.flash >= fade ? 1.0f : float(p.flash) / float(fade));
            --p.flash;
        } else if (p.max_timer > 0) {
            const float pulse = 0.75f + 0.25f * std::cos(6.2831853f * float(p.max_timer % kPulseFrames) / kPulseFrames);
            write_colour(address, p, kLightBlue, pulse * std::min(1.0f, float(p.max_timer) / 12.0f));
        }
    }
    // The HUD.
    if (!fighters[0] || !fighters[1]) return;
    const auto phase = [&](uint32_t f) { return ppc::ld32(base, f + kPhase); };
    const auto down = [&](uint32_t f) { return static_cast<int16_t>(ppc::ld16(base, f + kHealth)) <= 0; };
    if ((phase(fighters[0]) == 0 && phase(fighters[1]) == 0) || down(fighters[0]) || down(fighters[1])) return;
    if (!g_atlas_set) {
        set_atlas();
        g_atlas_set = true;
    }
    if (!g_atlas_height) return;
    std::vector<gpu::overlay::Quad> quads;
    const auto now = std::chrono::steady_clock::now();
    g_tops[0] = g_tops[1] = 0;
    g_tops_until = now + std::chrono::milliseconds(250);
    // The title's HUD size (as its viewport takes it: smaller only).
    const float hud_size = ldf(base, kHudScale), scale = hud_size > 0.5f && hud_size < 1.0f ? hud_size : 1.0f;
    const auto hud_x = [&](float x) { return gpu::overlay::kWidth / 2 + (x - gpu::overlay::kWidth / 2) * scale; };
    const auto hud_y = [](float y, float size) { return gpu::overlay::kHeight / 2 + (y - gpu::overlay::kHeight / 2) * size; };
    const float texts_top = practice ? framedata::kPanelsBottom
                                     : std::min(hud_y(kTextsTop, scale), hud_y(kTextsTop, kDefaultHudSize));
    for (int s = 0; s < 2; ++s) {
        if (!who[s] || !who[s]->hud) continue;
        const Side& side = who[s]->hud->sides[s];
        const bool framed = side.right > side.left;
        // Under its life bar, above the title's texts.
        const float under_bar = !framed ? 0
                              : s == 0 ? hud_x(kLifeBarLeft) / kScale - side.left : hud_x(kLifeBarRight) / kScale - side.right;
        g_lift = side.bottom > side.top ? side.bottom - (texts_top - kAboveTexts) / kScale : 0;
        float beside = 0; // right of Practice's input history, should that reach further
        if (const float right = framedata::history_right(); right && s == 0 && framed)
            beside = (right + kBesideHistory) / kScale - side.left;
        // (a frame Practice's history is not reported, as Geese's MAX activation stops the game, keeps the place)
        static struct { float shift = 0; std::chrono::steady_clock::time_point at; } kept[2];
        if (beside != 0) kept[s] = {beside, now};
        else if (now - kept[s].at < std::chrono::milliseconds(500)) beside = kept[s].shift;
        g_shift = s == 0 ? std::max(under_bar, beside) : under_bar;
        if (side.bottom > side.top) g_tops[s] = (side.top - g_lift) * kScale;
        draw(quads, *who[s]->hud, who[s]->config, player(fighters[s], slots[s]), s);
    }
    gpu::overlay::show_hud(std::move(quads), 0.1);
}

uint32_t colour(uint32_t fighter) {
    const auto it = g_players.find(fighter);
    if (it == g_players.end() || !it->second.colour) return 0;
    return it->second.flash > 0 || it->second.max_timer > 0 ? it->second.colour : 0;
}

void battle_frame(uint8_t* base) {
    if (g_stop.frames <= 0) return;
    for (int i = 0; i < 3; ++i) ppc::st32(base, g_stop.fighter + 4 * i, g_stop.place[i]);
    stop_camera(base);
}

float top(int side) { return std::chrono::steady_clock::now() < g_tops_until ? g_tops[side & 1] : 0; }

} // namespace cafe::title::gauge

// A fighter's own frame (r3 the fighter, r4 its opponent): not run while a
// super's time stop holds it.
PPC_FUNC(sub_0414FA10_orig);
PPC_FUNC(sub_0414FA10) {
    if (cafe::title::gauge::stopped(ctx.r[3])) return;
    sub_0414FA10_orig(ctx, base);
}

// The title's situation set-up (r3: the situation's kind; Practice's 15 too,
// for its start and its position reset).
PPC_FUNC(sub_039C2DB0_orig);
PPC_FUNC(sub_039C2DB0) {
    cafe::title::gauge::situation(ctx.r[3]);
    sub_039C2DB0_orig(ctx, base);
}
