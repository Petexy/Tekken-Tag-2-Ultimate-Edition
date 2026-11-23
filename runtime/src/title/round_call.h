#pragma once

// The round call's camera with a giant in the fight.
//
// While "ROUND 1", "READY" and "FIGHT" are on the screen the title's win
// camera (tcb_camera_win_t in its round call states) films the two fighters:
// it comes round them to where the fight's camera is, as far away as that
// camera, but looking at its own point between them, at the height the title
// frames two men from (1042.5 mm over the floor). The fight's camera with a
// giant in the fight (title/fight_camera.cpp) is further away AND higher:
// the title's picture, its bottom kept, grown upwards. From its distance at a
// man's height the picture is half floor and cuts the giant off at his
// shoulders, and jumps up when the round starts.
//
// The round call's shot is raised by what the fight's camera was raised, so
// that it ends as the fight's camera begins. The point it looks at goes up
// all through. Its eye goes up only as it comes down to the fight camera's
// own height over its point: a call that opens from high above the fighters
// (the win camera's state 0x12) keeps the title's own way down, through
// places the title's camera goes through on every stage, and no others (a
// metre higher on that way it went through a hall's gallery: a black
// picture).
//
// The call from above comes down level with the point it looks at, as the
// fight's camera of two men is; with a giant the fight's camera looks down at
// it from `level` higher (the title's direction, further back), and the
// picture tilted down in one frame when the round began. That call's eye
// comes down to the fight camera's height over its point instead, slowing into
// it (from_above()). The call round the side (0x11) and the third (0x13) end
// with the fight camera's own tilt already, their eyes never higher over
// their points than it.

#include <algorithm>
#include <cmath>

namespace cafe::title::round_call {

// How much of the fight camera's `lift` the shot's eye takes, `over` mm over
// the point it looks at; `level`: the fight camera's eye over its point. All
// of it at that height and under it, none 2 * lift higher: there the raised
// eye still comes down, at half the title's speed.
inline float share(float over, float lift, float level) {
    if (!(lift > 0)) return 0;
    return std::clamp(1 - (over - level) / (2 * lift), 0.0f, 1.0f);
}

// The shot (its eye, the point it looks at) raised for a fight camera that
// went up by `lift` mm this frame (0: not at all) and has its eye `level` mm
// over its point. -> whether it was raised.
inline bool raise(float eye[3], float target[3], float lift, float level) {
    if (!(lift > 0) || !std::isfinite(lift) || !std::isfinite(level) || !std::isfinite(eye[1]) || !std::isfinite(target[1]))
        return false;
    eye[1] += lift * share(eye[1] - target[1], lift, level);
    target[1] += lift;
    return true;
}

// The call from above, raised: its eye's height over the raised point, for
// its own `over` (the title's eye over the title's point), a fight camera
// raised by `lift` with its eye `level` over its point. From `top` = level +
// 2 * lift up the title's own eye (over - lift: the point alone goes up);
// under it the eye takes ever more of the lift, all of it and `level` more
// where the title's call has come down level: level + lift * (over / top)^k,
// k = top / lift, meets the title's way at `top` at its speed and comes down
// to the fight camera's tilt slowing all the way, as the title's own does
// (a share of the lift in a straight ramp halved its speed in one frame; the
// eye stopping at `level` would have been a second jolt). Its eye is never
// over the title's own by more than lift + level, and only near the end.
inline float from_above(float over, float lift, float level) {
    const float top = level + 2 * lift;
    if (!(lift > 0) || !std::isfinite(lift) || !std::isfinite(level) || !std::isfinite(over) || !(top > lift))
        return over;
    if (over >= top) return over - lift;
    return level + lift * std::pow(std::max(over, 0.0f) / top, top / lift);
}

// How high the picture of a shot reaches where it looks (at the point's
// distance): its top and its bottom. `fov` its horizontal field of view in
// degrees, `aspect` its width over its height.
struct Reach {
    float top, bottom;
};
inline Reach reach(const float eye[3], const float target[3], float fov, float aspect) {
    const float distance = std::hypot(target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]);
    const float half = distance * std::tan(fov * 3.14159265f / 360) / aspect;
    return {target[1] + half, target[1] - half};
}

} // namespace cafe::title::round_call
