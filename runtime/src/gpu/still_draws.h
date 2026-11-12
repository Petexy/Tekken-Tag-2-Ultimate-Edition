#pragma once

// Draws a title wants to see as standing still: in one pass (its vertex
// shader), a polygon's draws read this frame's vertex positions in place of
// last frame's, so the pass sees no motion (TTT2's velocity pass, which its
// motion blur smears fast parts by). The title registers them at start-up
// (null: none, every draw as the title makes it). The renderer tests, for
// each indexed draw, the cheapest things first: the index count (a bit in
// `counts`), then the pass's vertex shader, and only then asks `still`.
// (Read on the renderer's thread; never changed once registered.)

#include <atomic>
#include <cstdint>
#include <vector>

namespace cafe::gpu {

struct StillDraws {
    uint64_t vertex_program = 0;        // the pass: its vertex shader's hash (the renderer's program hash)
    uint32_t current = 0, previous = 0; // its vertex buffer slots: this frame's positions, last frame's
    std::vector<uint64_t> counts;       // bit n: some still polygon has n indices
    // An indexed draw's indices (guest address) and their count, in the pass: true when it draws a still polygon.
    bool (*still)(uint32_t index_address, uint32_t count) = nullptr;
    bool all = false;                   // every draw of the pass left out (tests: no motion at all, the camera's too)

    bool counted(uint32_t count) const { return count / 64 < counts.size() && (counts[count / 64] >> (count % 64)) & 1; }
};

inline std::atomic<const StillDraws*> g_still_draws{nullptr};
inline void set_still_draws(const StillDraws* draws) { g_still_draws.store(draws, std::memory_order_release); }
inline const StillDraws* still_draws() { return g_still_draws.load(std::memory_order_acquire); }

} // namespace cafe::gpu
