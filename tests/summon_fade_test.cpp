// Fades of a Tekken 8 fighter's summoned weapons (title/summon_fade.h) on made-up values.
#include "title/summon_fade.h"
#include <array>
#include <cassert>
#include <cmath>
#include <cstring>
#include <vector>
using namespace cafe::title::summon_fade;

namespace {
// the scales drawn over the frames after a row, as the posing reads them (step, then scale)
std::vector<float> run(Fades& fades, uint32_t n, int frames) {
    std::vector<float> out;
    for (int i = 0; i < frames; ++i) {
        step(fades);
        out.push_back(fades[n].running() ? fades[n].scale() : -1.0f); // -1: no fade (whole when shown, else gone)
    }
    return out;
}
bool near(const std::vector<float>& a, const std::vector<float>& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
        if (std::fabs(a[i] - b[i]) > 1e-5f) return false;
    return true;
}
std::array<uint32_t, 16> matrix(const std::array<float, 16>& m) {
    std::array<uint32_t, 16> out{};
    std::memcpy(out.data(), m.data(), sizeof(out));
    return out;
}
float at(const std::array<uint32_t, 16>& m, int i) {
    float v;
    std::memcpy(&v, &m[i], 4);
    return v;
}
} // namespace

int main() {
    // values: n | frames << 8 (Tekken 7 fighters' values have no frames)
    assert(split(4 | 10 << 8).n == 4 && split(4 | 10 << 8).frames == 10);
    assert(split(3).n == 3 && split(3).frames == 0);
    assert(split(16).n == 16 && split(16).frames == 0); // (dismiss all)

    // shown over 5 frames: drawn at 1/5 .. 4/5, whole at the 5th; dismissed over 10: 9/10 .. 1/10, gone at the 10th
    Fades fades{};
    start(fades, 1, 5, true, false);
    assert(near(run(fades, 1, 6), {0.2f, 0.4f, 0.6f, 0.8f, -1.0f, -1.0f}));
    start(fades, 1, 10, false, true);
    assert(near(run(fades, 1, 11), {0.9f, 0.8f, 0.7f, 0.6f, 0.5f, 0.4f, 0.3f, 0.2f, 0.1f, -1.0f, -1.0f}));

    // frames 0 or 1: at once (and a running fade of that summon ends)
    start(fades, 2, 0, true, false);
    assert(!fades[2].running());
    start(fades, 2, 5, true, false);
    step(fades);
    start(fades, 2, 1, false, true);
    assert(!fades[2].running());

    // a show of a shown summon / a dismissal of one not out: nothing
    start(fades, 3, 5, true, true);
    assert(!fades[3].running());
    start(fades, 3, 10, false, false);
    assert(!fades[3].running());

    // a row fading the same way as the running fade: left alone (Tekken 8's queue)
    start(fades, 4, 5, true, false);
    step(fades);
    step(fades);
    start(fades, 4, 5, true, true);
    assert(std::fabs(fades[4].scale() - 0.4f) < 1e-5f);

    // turned round: a dismissal during the show goes out from the scale it has
    start(fades, 4, 10, false, true);
    assert(!fades[4].in && std::fabs(fades[4].scale() - 0.4f) < 1e-5f);
    assert(near(run(fades, 4, 5), {0.3f, 0.2f, 0.1f, -1.0f, -1.0f}));

    // ramps: the rows a ramp names scaled (a staff along y: x and z), the position kept
    const std::array<float, 16> local{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 20, 30, 1};
    auto m = matrix(local);
    ramp_local(m, 1 | 4, 0.5f);
    assert(at(m, 0) == 0.5f && at(m, 5) == 1.0f && at(m, 10) == 0.5f);
    assert(at(m, 12) == 10.0f && at(m, 13) == 20.0f && at(m, 14) == 30.0f);

    // under a ramped weapon (kRampUnder): S L S^-1, the parent's scale cancelled (its rows of the child's local are
    // columns here): a link rotated 90 degrees about x under a link scaled in y and z
    const std::array<float, 16> link{1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 200, 0, 1};
    auto l = matrix(link);
    ramp_local(l, 2 | 4 | kRampUnder, 0.25f);
    // rows: x row unscaled (columns y, z cancelled: 0 there anyway); the y row (0, 0, 1): scaled 0.25 then / 0.25
    assert(at(l, 0) == 1.0f && at(l, 6) == 1.0f && at(l, 9) == -1.0f);
    // the position (row 3): not scaled by its own row, its y column divided by the parent's scale
    assert(std::fabs(at(l, 13) - 800.0f) < 1e-3f && at(l, 12) == 0.0f);
    // composed with the parent's scale (diag 1, s, s): the link's world = S_link L (no compounding)
    {
        const float s = 0.25f;
        const float parent[3] = {1, s, s};
        // world axes of the link = local rows (3x3) x diag(parent)
        for (int r = 0; r < 3; ++r) {
            float len = 0;
            for (int c = 0; c < 3; ++c) len += at(l, 4 * r + c) * parent[c] * at(l, 4 * r + c) * parent[c];
            const float want = r == 0 ? 1.0f : s;
            assert(std::fabs(std::sqrt(len) - want) < 1e-5f);
        }
        // its origin in the parent's unscaled frame: 200 along y, as before the fade
        assert(std::fabs(at(l, 13) * parent[1] - 200.0f) < 1e-3f);
    }
    return 0;
}
