// Tekken 7's warps (Noctis's Warp-Strike, his teleports and escapes): move
// property 0x82ae (the importer's 0x822A, in extra properties and in end
// lists) makes the fighter vanish or appear. Its value: out << 24 | flash <<
// 16 | T << 8 | N. Out (1): the fighter fades out over T frames (Tekken 7
// dithers him away), else in over T frames; with flash 1 and N > 1 his
// warp's light (a rim light all over him, emissive) fades over N - 1
// frames. His warp moves vanish as the thrown sword hits (0x01011616 or
// 0x01012121 at their start: 22 or 33 frames) and the move it leads to
// appears at its frame 10 (0x0001050a).
//
// The renderer draws him in a look meanwhile (gpu/looks.h): his colour
// carries its number. As Tekken 7's clips show it (local reference sheets
// of Warp-Strike on hit and on guard): fading out, his whole body turns a
// flat sky blue at once (lighter and darker blue only, bright edges), an
// ordered dither eats him as the blue goes grey, and the last frames are a
// sparse grey ghost; then he is gone (title/roster.cpp collapses his model
// to a point as well: no shadow, nothing left to draw). Fading in, the first
// frames are hidden still (the moves that appear fade in at their frame 10
// and take him to the opponent at 11), then he is solid blue for two frames;
// arriving with a hit he stays half dithered through Tekken 7's pause on it
// (the port's hit does not pause his move), turns indigo, then his own
// colours tinted violet; else only his edges show, then his own colours
// dither back in. A fade runs on the frames his move runs on (a pause of
// the title's holds it). His hit and hurt boxes stay as they are, and so do
// the effects on him.
//
// A fighter shows again at the situation set-up (a round's start, Practice's
// position reset), when hit (the importer has every donor move, the
// reactions among them, appear at once; the reactions of his own moves and
// of the opponent's moveset have nothing of the kind: he shows as his health
// drops) and kOutFrames after vanishing.
// TTT2_TRACE_WARP=1 logs the warps.
//
// The place a warp starts at aims the streak of light he appears with
// (0x82b0, title/roster.cpp): Tekken 7 records it as he vanishes and again in
// the move he appears with (0x82b1, kStart), and keeps it however old; here
// a start older than kStartFrames aims nothing (his blocked Warp-Strike
// appears without having vanished: Tekken 7 would aim it from the warp
// before), and the streak keeps his facing.

#include "title/warp.h"

#include "gpu/looks.h"

#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>

namespace cafe::title::warp {
namespace {

constexpr uint32_t kOwnColour = 7840; // four floats the title multiplies the fighter's colours by
constexpr uint32_t kMove = 280, kMoveFrame = 212;
constexpr uint32_t kHealth = 96;      // 16 bits
constexpr int kOutFrames = 120;       // a fighter vanished shows again after these frames (his longest: 70)
constexpr int kStartFrames = 60;      // a warp's start aims an effect this long (his longest: 36, the Rage Art)
constexpr float kShown = 0.3f;        // fading in, the share of the fade from which a fighter is drawn
constexpr int kSolid = 2;             // ... then drawn whole in the warp's light first (and fading out fast)
constexpr int kShort = 8;             // fades out of up to these frames are fast (his warps past a guard)
constexpr int kArrivalPause = 14;     // Tekken 7's pause on an arrival's hit, which holds his fade half way in
constexpr int kLinger = 10;           // frames the renderer still looks for looks after the last warp

struct Warp {
    bool out = false;
    int fade = 0, flash = 0;            // T, N (0: no flash)
    int frame = 0;                      // frames the fighter's move ran since the property
    int frames = 0;                     // fighters' frames since it
    uint32_t move = 0, move_frame = 0;  // the fighter's move then
    int health = 0;                     // ... and his health
    uint32_t look = 0, number = 0;      // its look (gpu/looks.h) and its number
};
std::map<uint32_t, Warp> g_warps;       // by player
std::map<uint32_t, uint32_t> g_colours; // by player: guest, four floats: its colour carrying its look
int g_linger = 0;

struct Start {
    float place[3];
    int frame = 0; // since it was recorded
};
std::map<uint32_t, Start> g_starts; // by player

bool trace() {
    static const bool on = std::getenv("TTT2_TRACE_WARP") != nullptr;
    return on;
}

uint32_t look(float opacity, float glow, float rim, uint32_t flags) {
    const auto byte = [](float x) { return static_cast<uint32_t>(std::lround(std::clamp(x, 0.0f, 1.0f) * 255.0f)); };
    return byte(opacity) << gpu::looks::kOpacity | byte(glow) << gpu::looks::kGlow | byte(rim) << gpu::looks::kRim |
           flags;
}

// The look on the warp's frame w.frame (from 1), and whether the warp is over.
//   Out: drawn whole the first frame (two of a fast fade), then the dither
//   takes 60% of him by 40% of the fade while the light goes grey by half of
//   it, then the rest evenly; the edges stay lit, less and less, to the end.
//   In, arriving with a hit (a fade shorter than its flash: Warp-Strike's at
//   the opponent): drawn whole, then half dithered through Tekken 7's pause
//   on the hit, then whole in indigo, then his own colours tinted violet.
//   In, others (his warps past a guard, behind or up): drawn whole, then only
//   his edges, then his own colours dithering back in, the edges fading.
uint32_t look_at(const Warp& w, bool& over) {
    using namespace gpu::looks;
    over = false;
    if (w.out) {
        over = w.frames > kOutFrames;
        const int whole = w.fade > kShort ? 1 : kSolid; // (a short fade: drawn whole for two frames)
        const float u =
            w.fade > whole ? std::min(1.0f, float(std::max(0, w.frame - whole)) / float(w.fade - whole)) : 1.0f;
        if (u >= 1) return look(0, 0, 0, kHidden);
        return look(u < 0.4f ? 1 - 1.5f * u : (1 - u) * (0.4f / 0.6f), 1 - 2 * u, 1 - u, 0);
    }
    const int first = std::max(1, static_cast<int>(std::ceil(kShown * float(w.fade)))); // the first frame drawn
    const int j = w.frame - first, k = j - kSolid;
    if (j < 0) return look(1, 1, 1, kAppearing | kHidden);
    if (k < 0) return look(1, 1, 1, kAppearing | (j == 0 ? kStill : 0));
    if (w.flash > w.fade) {
        if (k < kArrivalPause) return look(0.5f, 1, 1, kAppearing);
        if (k < kArrivalPause + 2) return look(1, 0.5f, 0.5f, kAppearing);
        over = k >= kArrivalPause + 5;
        return look(1, 0.4f * float(kArrivalPause + 5 - k) / 3, 0, kAppearing);
    }
    const int edges = std::max(2, static_cast<int>(std::lround(float(w.fade) / 4)));
    const int back = std::max(2, w.fade - first - kSolid - edges);
    if (k < edges) return look(0, 1, 1, kAppearing);
    const float t = float(k - edges + 1) / float(back);
    over = t >= 1;
    return look(t, 0.3f * (1 - t), 1 - t, kAppearing);
}

} // namespace

void property(uint32_t player, uint32_t value) {
    if (trace()) {
        const uint32_t move = ppc::ld32(guest_base(), player + kMove);
        const uint32_t name = move ? ppc::ld32(guest_base(), move) : 0;
        std::fprintf(stderr, "ttt2: warp: %08X property %08X in %s frame %u%s\n", player, value,
                     name ? reinterpret_cast<const char*>(guest_pointer(name)) : "?",
                     ppc::ld32(guest_base(), player + kMoveFrame), vanished(player) ? " (was not drawn)" : "");
    }
    const bool out = (value >> 24 & 0xFF) == kOut;
    const auto it = g_warps.find(player);
    if (!out && (value >> 8 & 0xFF) == 0) {
        if (it != g_warps.end()) g_warps.erase(it); // (shown at once)
        return;
    }
    if (out && it != g_warps.end() && it->second.out) return; // (going or gone already)
    Warp& w = g_warps[player];
    w.out = out;
    w.fade = int(value >> 8 & 0xFF);
    w.flash = (value >> 16 & 0xFF) == 1 && (value & 0xFF) > 1 ? int(value & 0xFF) : 0;
    w.frame = w.frames = 0;
    w.move = w.move_frame = 0;
    w.health = static_cast<int16_t>(ppc::ld16(guest_base(), player + kHealth));
}

void situation() {
    g_warps.clear();
    g_starts.clear();
}

void fighters_frame(uint8_t* base) {
    for (auto it = g_starts.begin(); it != g_starts.end();)
        it = ++it->second.frame > kStartFrames ? g_starts.erase(it) : std::next(it);
    for (auto it = g_warps.begin(); it != g_warps.end();) {
        Warp& w = it->second;
        const int health = static_cast<int16_t>(ppc::ld16(base, it->first + kHealth));
        if (health < w.health) { // (hit: shown at once)
            if (trace())
                std::fprintf(stderr, "ttt2: warp: %08X hit (health %d > %d): shown\n", it->first, w.health, health);
            it = g_warps.erase(it);
            continue;
        }
        w.health = health;
        const uint32_t move = ppc::ld32(base, it->first + kMove), move_frame = ppc::ld32(base, it->first + kMoveFrame);
        if (w.frame == 0 || move != w.move || move_frame != w.move_frame) ++w.frame;
        w.move = move, w.move_frame = move_frame;
        ++w.frames;
        bool over = false;
        w.look = look_at(w, over);
        w.number = gpu::looks::number(w.look, w.number);
        if (trace())
            std::fprintf(stderr, "ttt2: warp: %08X %s frame %d/%d (%d, move frame %u) opacity %u glow %u%s%s\n",
                         it->first, w.out ? "out" : "in", w.frame, w.fade, w.frames, move_frame,
                         w.look >> gpu::looks::kOpacity & 0xFF, w.look >> gpu::looks::kGlow & 0xFF,
                         w.look & gpu::looks::kHidden ? " (not drawn)" : "",
                         w.look & gpu::looks::kStill ? " (still)" : "");
        uint32_t& colour = g_colours[it->first];
        if (!colour) colour = system_alloc(16);
        uint32_t words[4];
        for (int i = 0; i < 4; ++i) words[i] = ppc::ld32(base, it->first + kOwnColour + 4 * i);
        gpu::looks::mark(words, w.number);
        for (int i = 0; i < 4; ++i) ppc::st32(base, colour + 4 * i, words[i]);
        it = over ? g_warps.erase(it) : std::next(it);
    }
    g_linger = g_warps.empty() ? std::max(0, g_linger - 1) : kLinger;
    gpu::looks::set_active(g_linger > 0);
}

bool warping() { return !g_warps.empty(); }

bool vanished(uint32_t player) {
    const auto it = g_warps.find(player);
    if (it == g_warps.end()) return false;
    // (before its first frame: hidden while appearing, the first frames being so)
    return it->second.frame > 0 ? (it->second.look & gpu::looks::kHidden) != 0 : !it->second.out;
}

uint32_t colour(uint32_t fighter) {
    const auto it = g_warps.find(fighter);
    return it != g_warps.end() && it->second.frame > 0 ? g_colours[fighter] : 0;
}

void start(uint32_t player, const float place[3]) {
    Start& s = g_starts[player];
    std::copy(place, place + 3, s.place);
    s.frame = 0;
}

bool take_start(uint32_t player, float place[3]) {
    const auto it = g_starts.find(player);
    if (it == g_starts.end()) return false;
    std::copy(it->second.place, it->second.place + 3, place);
    g_starts.erase(it);
    return true;
}

} // namespace cafe::title::warp
