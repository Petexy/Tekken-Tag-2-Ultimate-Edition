// The round call's camera with a giant in the fight (title/round_call.h); made-up fighters.
#include "title/round_call.h"
#include <cassert>
#include <cmath>
#include <cstring>
using namespace cafe::title::round_call;

int main() {
    const float fov = 50, aspect = 16.0f / 9;
    // Two men: the fight's camera 4.6 m away, looking 1042.5 mm over the floor; the round call's shot ends there.
    {
        float eye[3] = {0, 1179, 4600}, target[3] = {0, 1042.5f, 0};
        float eye0[3], target0[3];
        std::memcpy(eye0, eye, sizeof eye);
        std::memcpy(target0, target, sizeof target);
        assert(!raise(eye, target, 0)); // (the fight's camera was not raised: the title's shot, bit for bit)
        assert(!std::memcmp(eye, eye0, sizeof eye) && !std::memcmp(target, target0, sizeof target));
        assert(!raise(eye, target, -5) && !raise(eye, target, NAN) && !raise(eye, target, INFINITY));
        assert(!std::memcmp(eye, eye0, sizeof eye) && !std::memcmp(target, target0, sizeof target));
        const Reach r = reach(eye, target, fov, aspect);
        assert(std::fabs(r.bottom - -164) < 5 && std::fabs(r.top - 2249) < 5); // (two men, the floor near the bottom)
    }
    // A giant 4.3 m tall: the fight's camera went back to 8.5 m and up by 1030 mm (the picture's bottom kept at
    // -164). The title's round call comes round at that distance, but at a man's height.
    {
        const float giant_top = 4300, lift = 1030;
        float eye[3] = {0, 1296, 8511}, target[3] = {0, 1042.5f, 0};
        const Reach before = reach(eye, target, fov, aspect);
        assert(before.top < giant_top - 800); // (the bug: cut off at his shoulders)
        assert(before.bottom < -1000);        // (and a metre of floor under the fighters' feet)
        assert(raise(eye, target, lift));
        assert(eye[0] == 0 && eye[2] == 8511 && target[0] == 0 && target[2] == 0); // (only up)
        assert(eye[1] == 1296 + lift && target[1] == 1042.5f + lift);              // (the direction kept)
        const Reach after = reach(eye, target, fov, aspect);
        assert(after.top >= giant_top);            // (whole)
        assert(std::fabs(after.bottom - -164) < 10); // (the floor where the fight's camera has it)
    }
    // Coming round from further away (the start of the round call), raised the same: he is whole there too.
    {
        float eye[3] = {9691, 1063, 5543}, target[3] = {0, 1042.5f, 0};
        assert(raise(eye, target, 1030));
        assert(reach(eye, target, fov, aspect).top >= 4300);
    }
    // A shot that is not a number stays as it is.
    {
        float eye[3] = {0, NAN, 0}, target[3] = {0, 1042.5f, 0};
        assert(!raise(eye, target, 1030) && target[1] == 1042.5f);
    }
    return 0;
}
