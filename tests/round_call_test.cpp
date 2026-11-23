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
        assert(!raise(eye, target, 0, 136.5f)); // (the fight's camera was not raised: the title's shot, bit for bit)
        assert(!std::memcmp(eye, eye0, sizeof eye) && !std::memcmp(target, target0, sizeof target));
        assert(!raise(eye, target, -5, 136.5f) && !raise(eye, target, NAN, 136.5f) && !raise(eye, target, INFINITY, 136.5f));
        assert(!raise(eye, target, 1030, NAN));
        assert(!std::memcmp(eye, eye0, sizeof eye) && !std::memcmp(target, target0, sizeof target));
        const Reach r = reach(eye, target, fov, aspect);
        assert(std::fabs(r.bottom - -164) < 5 && std::fabs(r.top - 2249) < 5); // (two men, the floor near the bottom)
    }
    // A giant 4.3 m tall: the fight's camera went back to 8.5 m and up by 1030 mm (the picture's bottom kept at
    // -164). The title's round call comes round at that distance, but at a man's height.
    {
        const float giant_top = 4300, lift = 1030, level = 253.5f;
        float eye[3] = {0, 1296, 8511}, target[3] = {0, 1042.5f, 0};
        const Reach before = reach(eye, target, fov, aspect);
        assert(before.top < giant_top - 800); // (the bug: cut off at his shoulders)
        assert(before.bottom < -1000);        // (and a metre of floor under the fighters' feet)
        assert(raise(eye, target, lift, level));
        assert(eye[0] == 0 && eye[2] == 8511 && target[0] == 0 && target[2] == 0); // (only up)
        assert(eye[1] == 1296 + lift && target[1] == 1042.5f + lift);              // (the direction kept)
        const Reach after = reach(eye, target, fov, aspect);
        assert(after.top >= giant_top);            // (whole)
        assert(std::fabs(after.bottom - -164) < 10); // (the floor where the fight's camera has it)
    }
    // Coming round from further away (the start of the round call), raised the same: he is whole there too.
    {
        float eye[3] = {9691, 1063, 5543}, target[3] = {0, 1042.5f, 0};
        assert(raise(eye, target, 1030, 253.5f));
        assert(eye[1] == 1063 + 1030 && target[1] == 1042.5f + 1030); // (under the fight camera's height: all of it)
        assert(reach(eye, target, fov, aspect).top >= 4300);
    }
    // A call that opens from above: the eye comes down from 10 m over the point. High up it is the title's own
    // (no place the title's camera does not go through); it never goes up again on its way down, never leaves the
    // title's way by more than the lift, and ends on the fight's camera.
    {
        const float lift = 1030, level = 253.5f;
        float last = INFINITY;
        for (float over = 10000; over >= level; over -= 12.5f) {
            float eye[3] = {0, 1042.5f + over, 8000}, target[3] = {0, 1042.5f, 0};
            assert(raise(eye, target, lift, level));
            assert(target[1] == 1042.5f + lift); // (the point: all through)
            const float up = eye[1] - (1042.5f + over);
            assert(up >= 0 && up <= lift);
            if (over >= level + 2 * lift) assert(up == 0); // (the title's own way down)
            assert(eye[1] > 1042.5f + level + lift - 0.01f); // (never under the fight's camera)
            assert(eye[1] <= 1042.5f + level + 2 * lift + 0.01f || up == 0); // (raised only near the end)
            assert(eye[1] <= last);                                         // (comes down, never up again)
            last = eye[1];
        }
        float eye[3] = {0, 1042.5f + level, 8000}, target[3] = {0, 1042.5f, 0};
        assert(raise(eye, target, lift, level));
        assert(eye[1] <= last && std::fabs(eye[1] - (1042.5f + level + lift)) < 0.01f); // (ends on the fight's camera)
        assert(share(level, lift, level) == 1 && share(level - 300, lift, level) == 1 && share(level + lift, lift, level) == 0.5f);
        assert(share(level + 2 * lift, lift, level) == 0 && share(5000, 0, level) == 0);
    }
    // A shot that is not a number stays as it is.
    {
        float eye[3] = {0, NAN, 0}, target[3] = {0, 1042.5f, 0};
        assert(!raise(eye, target, 1030, 253.5f) && target[1] == 1042.5f);
    }
    return 0;
}
