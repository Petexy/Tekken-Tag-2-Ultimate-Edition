// Which draws may be left out while their shader is made in the background (gpu/vulkan/leave_out.h).
#include "gpu/vulkan/leave_out.h"
#include <cassert>
using namespace cafe::gpu::vk;

int main() {
    // A thing in the 3D scene, into targets drawn every frame: a few frames late is all it costs.
    const LateDraw scene{.depth_tested = true, .redrawn = true};
    assert(may_leave_out(scene));
    static_assert(may_leave_out(LateDraw{.depth_tested = true, .redrawn = true}));

    // Each of the others waits for its shader.
    LateDraw d = scene;
    d.stream_out = true; // the fighters' skinned vertices
    assert(!may_leave_out(d));
    d = scene;
    d.replaying = true; // an extra frame
    assert(!may_leave_out(d));
    d = scene;
    d.depth_tested = false; // blur, glow, copies, the menus' and the HUD's layers
    assert(!may_leave_out(d));
    d = scene;
    d.redrawn = false; // a picture drawn once and kept
    assert(!may_leave_out(d));
    d = scene;
    d.cpu_reads = true; // what the title reads back
    assert(!may_leave_out(d));

    assert(!may_leave_out(LateDraw{}));
    return 0;
}
