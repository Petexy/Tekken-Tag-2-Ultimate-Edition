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
// The round call's shot is raised by what the fight's camera was raised
// (its eye and the point it looks at alike: the shot keeps its direction),
// so that it ends as the fight's camera begins.

#include <cmath>

namespace cafe::title::round_call {

// The shot (its eye, the point it looks at) raised by `lift` mm (what the
// fight's camera was raised by this frame; 0: not at all). -> whether it
// was raised.
inline bool raise(float eye[3], float target[3], float lift) {
    if (!(lift > 0) || !std::isfinite(lift) || !std::isfinite(eye[1]) || !std::isfinite(target[1])) return false;
    eye[1] += lift;
    target[1] += lift;
    return true;
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
