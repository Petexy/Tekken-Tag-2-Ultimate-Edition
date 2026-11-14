// A giant's body in the fight. TTT2 sizes the bodies of its fighters by
// their select ids, for a man's size (Kuma, Panda and Ogre a little more);
// an added fighter gets its donor's. Tekken 8's Azazel, kept at his own
// size, has a skeleton 1.8 times a man's: the title places his spheres on
// his bones, 1.8 times as far apart, and leaves them a man's size, so his
// body has gaps an attack passes through, and his opponent stands in his
// claws.
//
// The title has a giant of its own: Mushroom Battle grows a fighter by the
// float at player +1652 (1 otherwise; sub_02C38B1C eases it). It makes the
// fighter's 14 hurt spheres (sub_03D6B9F4: the radii from his select id's
// row, times the size) and his 8 push spheres (sub_03A40400 pushes two
// fighters apart where r_a s_a + r_b s_b passes the spheres' distance) as
// big, and counts him 600 (size - 1) mm bigger in the distance between
// bodies (sub_03AD994C: the fighters' distance on the floor less both
// bodies' sizes, at least 0, for each two of the four players at player
// +1456 + 4 the other's number) that throws (requirements 3..9: their
// reach at least that distance), moves' distance requirements and the
// computer player go by. The same size also grows his model, which a giant
// added fighter already has, so the size itself is never set for him.
//
// An added fighter with a body scale S (character.ini `body`; configure())
// gets the rest of it: his hurt and push spheres S times as big (after
// sub_03D6B9F4 and sub_03D6B544, which roster.cpp has run with his donor's
// select id), and, to every fighter of a man's size, a body 600 (S - 1) mm
// bigger in the distance between bodies. His own moves (Tekken 8's, made
// for his size: his throws reach 2.5 m where a man's reach 1.6) keep the
// distance as the title counts a man's; between two giants, too.
//
// TTT2_TRACE_BODY=1 logs the first sizes and gaps.

#include "title/giant_body.h"

#include "title/roster.h"

#include "cafe/ppc_ops.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>

namespace cafe::title::giant_body {
namespace {

constexpr uint32_t kPlayers = 0x1087FB60;                            // the four players (their structs)
constexpr uint32_t kHurtSpheres = 2168, kHurtSphereSize = 24, kHurtSphereCount = 14; // +12 radius, +16 its square, +20 radius
constexpr uint32_t kPushSpheres = 2504, kPushSphereSize = 16, kPushSphereCount = 8;  // +12 radius
constexpr uint32_t kGaps = 1456;                                     // + 4 the other player's number: distance between bodies
constexpr float kSizeGrowth = 600;                                   // mm of body a Mushroom Battle size step adds (0x101CE02C)

std::map<int, float> g_scales; // by slot

int trace() {
    static const int level = [] {
        const char* v = std::getenv("TTT2_TRACE_BODY");
        return v ? std::max(1, std::atoi(v)) : 0;
    }();
    return level;
}

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

int g_traced = 0; // lines logged (TTT2_TRACE_BODY)

} // namespace

void configure(int slot, float scale) {
    if (scale > 1) g_scales[slot] = scale;
    else g_scales.erase(slot);
    std::fprintf(stderr, "ttt2: giant body: the added fighter %d is %.2f times a man's size\n", slot, scale);
}

float scale_of(uint32_t player) {
    if (!player || g_scales.empty()) return 1;
    const auto it = g_scales.find(added_slot(player));
    return it == g_scales.end() ? 1 : it->second;
}

void hurt_spheres_sized(uint8_t* base, uint32_t player) {
    const float s = scale_of(player);
    if (s == 1) return;
    for (uint32_t i = 0; i < kHurtSphereCount; ++i) {
        const uint32_t at = player + kHurtSpheres + kHurtSphereSize * i;
        const float r = ldf(base, at + 12) * s, outer = ldf(base, at + 20) * s;
        stf(base, at + 12, r);
        stf(base, at + 20, outer);
        stf(base, at + 16, outer * outer);
    }
    if (trace() && g_traced < 8) {
        ++g_traced;
        std::fprintf(stderr, "ttt2: giant body: hurt spheres x%.2f (head %.0f, hips %.0f mm)\n", s,
                     ldf(base, player + kHurtSpheres + kHurtSphereSize * 8 + 12),
                     ldf(base, player + kHurtSpheres + kHurtSphereSize * 12 + 12));
    }
}

void push_spheres_sized(uint8_t* base, uint32_t player) {
    const float s = scale_of(player);
    if (s == 1) return;
    for (uint32_t i = 0; i < kPushSphereCount; ++i) {
        const uint32_t at = player + kPushSpheres + kPushSphereSize * i + 12;
        stf(base, at, ldf(base, at) * s);
    }
}

} // namespace cafe::title::giant_body

using namespace cafe;
using namespace cafe::title::giant_body;

// The distances between bodies (no arguments): every two of the four players.
PPC_FUNC(sub_03AD994C_orig);
PPC_FUNC(sub_03AD994C) {
    sub_03AD994C_orig(ctx, base);
    if (g_scales.empty()) return;
    uint32_t players[4];
    float scales[4];
    bool any = false;
    for (uint32_t i = 0; i < 4; ++i) {
        players[i] = ppc::ld32(base, kPlayers + 4 * i);
        scales[i] = scale_of(players[i]);
        any = any || scales[i] > 1;
    }
    if (!any) return;
    for (uint32_t i = 0; i < 4; ++i) {
        if (!players[i] || scales[i] > 1) continue; // (a giant's own moves count the distance as the title does)
        for (uint32_t j = 0; j < 4; ++j) {
            if (j == i || scales[j] <= 1) continue;
            const uint32_t at = players[i] + kGaps + 4 * j;
            const float gap = ldf(base, at), less = std::max(gap - kSizeGrowth * (scales[j] - 1), 0.0f);
            stf(base, at, less);
            if (trace() && g_traced < 16 && (++g_traced, true))
                std::fprintf(stderr, "ttt2: giant body: gap from player %u to the giant %u: %.0f -> %.0f\n", i, j, gap, less);
        }
    }
}
