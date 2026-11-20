#pragma once

// The win scene's camera, and the added fighters.
//
// A fighter's win pose is filmed by a camera animation of its motion pack
// (move property 0x82F7): a path through the place the pose starts in, made
// for that pose (the title's fighters walk a step or two in theirs and the
// shot goes with them). An added fighter's moveset keeps its donor's win
// moves and camera animations and plays its own pose from Tekken 7 or 8 in
// them, which was made for another camera and travels elsewhere (one walks
// in from 1.5 m away and 2.2 m on, another kneels down). The donor's shot
// then showed the floor the donor would have stood on, or the fighter's legs
// at the picture's edge.
//
// Here the shot goes with the fighter: it is moved by as far as his head is
// from where a man's head would be over the place his pose started in
// (follow), and should it still look past him (the donor's shot pans after
// the donor) it turns until his head is inside the middle of the picture
// (keep). The last part of a team's win, for which the title stands the two
// fighters side by side, is right as it is.
//
// Pure geometry (millimetres, y up); title/fight_camera.cpp reads the game's
// camera and fighters and applies it. The title's own fighters' shots are
// not touched.

#include <algorithm>
#include <cmath>
#include <string_view>

namespace cafe::title::win_shot {

constexpr float kManHead = 1620;   // a man's head over the floor, as the title's shots look at it
constexpr float kAway = 0.2f;      // radians: the head at most this far from the shot's middle,
constexpr float kAcross = 0.45f;   // this far across the picture's half width
constexpr float kUp = 0.75f;       // and up its half height

// Whether a move films one fighter in its pose, by its name (an added fighter's moveset keeps its donor's:
// `ju_wem_1`): the winner's part of a team's win `_wem_1`, the partner's `_wes_2`, the other form's `_wnm_` / `_wns_`
// moves and, for a fighter `alone`, the hold after its pose (`_wem_3`). Not the waits (`_wem_2`, `_wes_1`: the
// fighter is put away) nor a team's last part (`_wem_3`, `_wes_3`: the title stands the two side by side, and its
// shot of them is right as it is).
constexpr bool films_one(std::string_view name, bool alone) {
    const auto has = [&](std::string_view s) { return name.find(s) != std::string_view::npos; };
    return has("_wem_1") || has("_wes_2") || has("_wnm_") || has("_wns_") || (alone && has("_wem_3"));
}

// Whether `head` can be the head of a fighter whose pose started at the place a man's head `expected` stands over:
// within kReach of it (a fighter's body spheres are still where the fight left them when the scene starts).
constexpr float kReach = 5000;
inline bool plausible(const float expected[3], const float head[3]) {
    for (int k = 0; k < 3; ++k)
        if (!std::isfinite(head[k])) return false;
    return std::hypot(head[0] - expected[0], head[1] - expected[1], head[2] - expected[2]) <= kReach;
}

// The shot moved by as far as `subject` is from `reference`.
inline void follow(float eye[3], float target[3], const float reference[3], const float subject[3]) {
    for (int k = 0; k < 3; ++k) {
        eye[k] += subject[k] - reference[k];
        target[k] += subject[k] - reference[k];
    }
}

// The shot turned (its eye stays) until `point` is within `away` radians of its middle and within `across` of the
// picture's half width and `up` of its half height (`fov`: the horizontal field of view in degrees; `aspect`: the
// picture's width over its height). -> whether it turned.
inline bool keep(const float eye[3], float target[3], const float point[3], float fov, float aspect,
                 float away = kAway, float across = kAcross, float up = kUp) {
    bool turned = false;
    float look[3], to[3];
    for (int k = 0; k < 3; ++k) {
        look[k] = target[k] - eye[k];
        to[k] = point[k] - eye[k];
    }
    const float reach = std::hypot(look[0], look[1], look[2]), far = std::hypot(to[0], to[1], to[2]);
    if (!(reach > 1) || !(far > 1)) return false;
    const float cosine = (look[0] * to[0] + look[1] * to[1] + look[2] * to[2]) / (reach * far);
    const float angle = std::acos(std::clamp(cosine, -1.0f, 1.0f));
    if (angle > away && angle < 3.1f) {
        const float turn = angle - away, a = std::sin(angle - turn) / std::sin(angle), b = std::sin(turn) / std::sin(angle);
        for (int k = 0; k < 3; ++k) target[k] = eye[k] + reach * (a * look[k] / reach + b * to[k] / far);
        turned = true;
    }
    if (!(fov > 1 && fov < 170) || !(aspect > 0.1f)) return turned;
    float f[3];
    for (int k = 0; k < 3; ++k) f[k] = (target[k] - eye[k]) / reach;
    const float flat = std::hypot(f[0], f[2]);
    const float wide = std::tan(fov * 3.14159265f / 360), high = wide / aspect;
    const float z = to[0] * f[0] + to[1] * f[1] + to[2] * f[2];
    if (!(flat > 0.2f) || !(z > 1)) return turned;
    const float r[3] = {-f[2] / flat, 0, f[0] / flat};
    const float u[3] = {r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]};
    const float x = (to[0] * r[0] + to[2] * r[2]) / (z * wide), y = (to[0] * u[0] + to[1] * u[1] + to[2] * u[2]) / (z * high);
    const float x2 = std::clamp(x, -across, across), y2 = std::clamp(y, -up, up);
    if (x2 == x && y2 == y) return turned;
    // (the line the shot now looks along: the point moved back to (x2, y2) of the picture)
    float along[3];
    for (int k = 0; k < 3; ++k) along[k] = to[k] - r[k] * x2 * z * wide - u[k] * y2 * z * high;
    const float n = std::hypot(along[0], along[1], along[2]);
    if (!(n > 1)) return turned;
    for (int k = 0; k < 3; ++k) target[k] = eye[k] + reach * along[k] / n;
    return true;
}

} // namespace cafe::title::win_shot
