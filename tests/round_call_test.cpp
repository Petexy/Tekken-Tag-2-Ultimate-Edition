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
    // The call from above comes down level with its point (the title's own way: over 0 at its end); the fight's
    // camera with the giant has its eye `level` over its point. Raised its own way, the call comes down to the
    // fight camera's tilt, slowing all the way: no tilt in one frame when the round begins, no jolt on the way.
    {
        const float lift = 1030, level = 253.5f, point = 1042.5f, top = level + 2 * lift;
        assert(from_above(0, lift, level) == level && from_above(-40, lift, level) == level); // (the fight camera's)
        assert(std::fabs(from_above(top, lift, level) - (top - lift)) < 0.01f);  // (meets the title's own way)
        assert(from_above(5000, lift, level) == 5000 - lift);                    // (high up: the title's own eye)
        assert(from_above(100, 0, level) == 100 && from_above(100, NAN, level) == 100 && std::isnan(from_above(NAN, lift, level)));
        assert(from_above(100, lift, -2 * lift) == 100); // (a fight camera looking up at its point: not this)
        // The title's own call from above, easing down to level over 100 frames (made-up, as it does).
        float last_eye = INFINITY, last_speed = INFINITY;
        const float h = 1;
        for (float over = top + 2000; over >= 0; over -= h) {
            float eye[3] = {0, point + over, 8500}, target[3] = {0, point, 0};
            const float own = over;
            assert(raise(eye, target, lift, level));
            eye[1] = target[1] + from_above(own, lift, level);
            const float above_own = eye[1] - (point + own);
            assert(above_own >= -0.01f && above_own <= lift + level + 0.01f); // (never far over the title's way)
            if (own >= top) assert(std::fabs(above_own) < 0.01f);             // (high up: its very way)
            assert(eye[1] <= last_eye + 0.001f);                              // (comes down, never up again)
            // its speed against the title's: 1 high up, slowing smoothly to 0 at the end (no step, never faster again)
            if (last_eye != INFINITY) {
                const float speed = (last_eye - eye[1]) / h;
                assert(speed >= -0.001f && speed <= 1.001f && speed <= last_speed + 0.002f);
                if (last_speed != INFINITY) assert(std::fabs(speed - last_speed) < 0.01f);
                last_speed = speed;
            }
            last_eye = eye[1];
        }
        assert(last_speed < 0.01f);
        // its end: the fight camera's view (eye `level` over the point, both raised by `lift`), he whole in it
        float eye[3] = {0, point, 8500}, target[3] = {0, point, 0};
        assert(raise(eye, target, lift, level));
        eye[1] = target[1] + from_above(0, lift, level);
        const float fight_eye[3] = {0, point + lift + level, 8500}, fight_target[3] = {0, point + lift, 0};
        for (int k = 0; k < 3; ++k) assert(std::fabs(eye[k] - fight_eye[k]) < 0.01f && target[k] == fight_target[k]);
        assert(reach(eye, target, fov, aspect).top >= 4300);
    }
    // A shot that is not a number stays as it is.
    {
        float eye[3] = {0, NAN, 0}, target[3] = {0, 1042.5f, 0};
        assert(!raise(eye, target, 1030, 253.5f) && target[1] == 1042.5f);
    }
    return 0;
}
