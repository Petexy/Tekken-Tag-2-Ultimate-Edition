#pragma once

// Tekken 7's warps (Noctis): an added fighter vanishes and appears again,
// turning the warp's sky blue and dithering away or back in over a few
// frames (title/warp.cpp).

#include <cstdint>

namespace cafe::title::warp {

// The move property the importer turns Tekken 7's 0x82ae into, its value
// Tekken 7's: out << 24 | flash << 16 | fade frames << 8 | flash frames
// (out kOut vanishes, 0 appears). With kStart << 24 it is Tekken 7's 0x82b1
// instead: where the warp starts (title/roster.cpp aims an effect from there),
// no fade (`property` is not called with it).
constexpr uint32_t kProperty = 0x822A;
constexpr uint32_t kOut = 1, kStart = 2;
void property(uint32_t player, uint32_t value);

// The title's situation set-up (sub_039C2DB0: a round's start, Practice's
// position reset): every fighter shows.
void situation();

// After the fighters' frame: the fades and flashes run on a frame.
void fighters_frame(uint8_t* base);

// A fighter is fading or flashing; `player` is not drawn at all
// (title/roster.cpp collapses its model).
bool warping();
bool vanished(uint32_t player);

// The colour the title draws `fighter` in while it warps (a guest address
// of four floats: its own, carrying its look for the renderer: gpu/looks.h),
// else 0.
uint32_t colour(uint32_t fighter);

// Where a player's warp started (title/roster.cpp: his hips as he vanishes or
// at kStart), for the effect aimed along it: `take_start` gives it once, and
// only within kStartFrames of its start.
void start(uint32_t player, const float place[3]);
bool take_start(uint32_t player, float place[3]);

} // namespace cafe::title::warp
