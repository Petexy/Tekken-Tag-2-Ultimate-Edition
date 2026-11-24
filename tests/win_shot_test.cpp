#include "title/win_shot.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace win_shot = cafe::title::win_shot;

void check(bool ok, const char* message) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

// Where `point` is in a shot's picture, in half widths (x) and half heights (y) from its middle.
void picture(const float eye[3], const float target[3], const float point[3], float fov, float aspect, float& x, float& y) {
    float f[3], to[3];
    for (int k = 0; k < 3; ++k) f[k] = target[k] - eye[k], to[k] = point[k] - eye[k];
    const float reach = std::hypot(f[0], f[1], f[2]);
    for (float& v : f) v /= reach;
    const float flat = std::hypot(f[0], f[2]);
    const float r[3] = {-f[2] / flat, 0, f[0] / flat};
    const float u[3] = {r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]};
    const float z = to[0] * f[0] + to[1] * f[1] + to[2] * f[2];
    const float wide = std::tan(fov * 3.14159265f / 360), high = wide / aspect;
    x = (to[0] * r[0] + to[2] * r[2]) / (z * wide);
    y = (to[0] * u[0] + to[1] * u[1] + to[2] * u[2]) / (z * high);
}

bool near(float a, float b, float within = 0.01f) { return std::fabs(a - b) <= within; }

int main() {
    // The moves that film one fighter in its pose, by the names a moveset keeps from its donor (made-up codes).
    check(win_shot::films_one("ab_wem_1", false) && win_shot::films_one("ab_wes_2", false) &&
              win_shot::films_one("ab_wnm_1", false) && win_shot::films_one("ab_wns_1", true),
          "the poses");
    check(!win_shot::films_one("xy_wnm_sp12_cd_2", false) && !win_shot::films_one("ab_wnm_13_2", false) &&
              !win_shot::films_one("ab_wns_01_2", false),
          "not the poses for two");
    check(!win_shot::films_one("ab_wem_2", false) && !win_shot::films_one("ab_wes_1", false), "not the waits");
    check(!win_shot::films_one("ab_wem_3", false) && !win_shot::films_one("ab_wes_3", false), "not a team's last part");
    check(win_shot::films_one("ab_wem_3", true), "a fighter alone holds its pose in the last part");
    check(!win_shot::films_one("ab_srm", true) && !win_shot::films_one("Ab_sKAM00_", false) && !win_shot::films_one("", true),
          "no other move");

    // A head the pose can have reached, and one the fight left 10 m away.
    const float over[3] = {0, win_shot::kManHead, 0};
    const float walked[3] = {150, 1100, -2200}, left[3] = {1400, 1450, 10200}, broken[3] = {0, NAN, 0};
    check(win_shot::plausible(over, over, walked) && !win_shot::plausible(over, over, left) &&
              !win_shot::plausible(over, over, broken),
          "plausible heads");
    // A pose that runs 7.6 m off and leaps: its head stays the fighter's all the way, a stride a frame.
    {
        float last[3] = {over[0], over[1], over[2]};
        bool all = true;
        for (int frame = 1; frame <= 100; ++frame) {
            const float head[3] = {500, 1620 + 20.0f * frame, 90.0f * frame - 1400};
            all = all && win_shot::plausible(over, last, head);
            std::copy(head, head + 3, last);
        }
        check(all && last[2] > 7000, "a head that runs far off is followed");
        const float jumped[3] = {last[0], last[1], last[2] + 3000};
        check(!win_shot::plausible(over, last, jumped), "but not one that is far and elsewhere at once");
    }

    const float fov = 50, aspect = 16.0f / 9;
    // A shot of a man standing at the origin, from 3 m: the fighter has walked 2.2 m and crouched; the shot moved
    // with his head shows it where it showed the man's.
    {
        float eye[3] = {-3000, 1500, 400}, target[3] = {0, 1300, 0};
        float x0, y0, x1, y1;
        picture(eye, target, over, fov, aspect, x0, y0);
        win_shot::follow(eye, target, over, walked);
        picture(eye, target, walked, fov, aspect, x1, y1);
        check(near(x0, x1) && near(y0, y1), "follow keeps the head's place in the picture");
        check(near(eye[0], -2850, 0.5f) && near(eye[1], 980, 0.5f) && near(eye[2], -1800, 0.5f), "follow moves the eye");
        // (and such a shot needs no turn)
        float kept[3] = {target[0], target[1], target[2]};
        check(!win_shot::keep(eye, kept, walked, fov, aspect), "a shot with the head in its middle stays");
        check(kept[0] == target[0] && kept[1] == target[1] && kept[2] == target[2], "unturned");
    }
    // A shot that pans after a donor walking off to the right, the fighter staying at the origin: it turns until
    // his head is within the limits, its eye and its reach unchanged.
    {
        const float eye[3] = {-300, 1630, 3300};
        float target[3] = {2000, -100, -760};
        float x, y;
        picture(eye, target, over, fov, aspect, x, y);
        check(std::fabs(x) > 0.7f || std::fabs(y) > 1, "the donor's shot loses him");
        const float reach = std::hypot(target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]);
        check(win_shot::keep(eye, target, over, fov, aspect), "it turns");
        picture(eye, target, over, fov, aspect, x, y);
        check(std::fabs(x) <= win_shot::kAcross + 0.01f && std::fabs(y) <= win_shot::kUp + 0.01f, "his head is in the picture");
        check(near(std::hypot(target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]), reach, 1), "the reach stays");
    }
    // A fighter behind the shot is turned to as well.
    {
        const float eye[3] = {0, 1600, 3000}, behind[3] = {1500, 1600, 4500};
        float target[3] = {0, 1500, 0};
        check(win_shot::keep(eye, target, behind, fov, aspect), "turns round");
        float x, y;
        picture(eye, target, behind, fov, aspect, x, y);
        check(std::fabs(x) <= win_shot::kAcross + 0.01f && std::fabs(y) <= win_shot::kUp + 0.01f, "and has him");
    }
    // A shot without a direction or a lens is left alone.
    {
        const float eye[3] = {0, 1600, 3000};
        float target[3] = {0, 1600, 3000};
        check(!win_shot::keep(eye, target, over, fov, aspect), "no direction");
    }
    std::puts("win_shot_test ok");
    return 0;
}
