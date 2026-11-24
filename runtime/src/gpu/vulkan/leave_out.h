#pragma once

// With shaders compiled in the background: may a draw whose shader or
// pipeline is still in the making be left out of its frame? Only one whose
// absence costs a few frames of picture and nothing else (draw.cpp, where
// the rule is applied, says why for each).

namespace cafe::gpu::vk {

struct LateDraw {
    bool stream_out = false;   // writes memory later draws and the title read
    bool replaying = false;    // an extra frame draws what its frame drew
    bool depth_tested = false; // a thing in the 3D scene, not a pass that makes a whole image
    bool redrawn = false;      // every target was drawn into the frame before as well
    bool cpu_reads = false;    // the title reads what is rendered (a target written back to its memory)
};

constexpr bool may_leave_out(const LateDraw& d) {
    return !d.stream_out && !d.replaying && d.depth_tested && d.redrawn && !d.cpu_reads;
}

} // namespace cafe::gpu::vk
