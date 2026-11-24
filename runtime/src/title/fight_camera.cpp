// The fight camera with a giant in the fight. TTT2's camera is made for
// fighters of up to about two metres; Tekken 8's Azazel, kept at his own
// size, has his head at 3.6 m and his horns at 4.2 m.
//
// The title's fight camera (the game camera's frame, sub_060B1BAC; the
// throw camera's, sub_0612ED10 -> sub_0612E1C0) asks the 2-character camera
// (sub_05FC085C: r3 the camera it makes, r4 r5 the cameras it starts from,
// r6 r7 the two fighters in play) for the camera that frames them: its eye
// (+0), the point it looks at (+16), its horizontal field of view in
// degrees (+56: 50, the picture 16:9). The camera that renders the scene
// eases towards it. The point is between the two fighters, as high as the
// middle of their focus points (sub_05FB6FEC: 1042.5 mm over the floor for
// a fighter in its stance; its body's root, if higher, otherwise), lifted
// a little as the camera goes further; the eye is about level with it, as
// far away as the fighters need (sub_05F3D2E0: their distance apart + 800
// mm across the picture, the focus points' difference in height + 1600 mm
// up it, 4600 mm at least, 10000 at most). Two fighters standing close
// together are framed from 0.16 m below the floor to 2.25 m above it.
//
// An added fighter with a camera height H (character.ini `camera`, in mm;
// configure()) who is one of the two fighters it frames, on either side,
// is framed whole: the picture reaches H above his body's lowest point (his
// 14 spheres, on his bones: his feet's while he stands, higher in a jump or
// a juggle; rising, where it will be 4 frames on, as the camera eases after
// what it is given; and a sixth of H over the spheres' highest point,
// should that be higher), as far down as the title had it (and at least
// that 0.16 m below the floor), and has his body's middle (his spheres'
// mean) at least 0.65 H in from its sides (his wings); his opponent, launched or thrown up,
// stays in it too, below the health bars (his body's highest point, rising
// where he will be 4 frames on, at most 85% of the way up the picture). The camera keeps the title's direction
// and tilt and goes up and back as far as that needs (15 m at most): the floor
// stays near the bottom of the picture and the opponent stands smaller in
// it, as Tekken 8 frames Azazel. Meanwhile, for the 2-character camera
// only, his focus point takes his root as a fighter of TTT2's size (1900
// mm) would have it (his height above the floor times 1900 / H): the title
// would focus on his stance at 1042.5 mm and on his root, near twice as
// high, as soon as he moves, and the camera would bob between the two. A
// tag partner waiting outside counts only once the camera frames him.
//
// The camera animations (tcb_camera_motion_t: intros, win poses, a move's
// camera animation; the donor's, made for a man's size, looking at a man's
// head) play for a giant scaled by his body's size (character.ini `body`:
// his skeleton's scale, giant_body.h; H / 1900 without one) about his head:
// what the shot had at a man's head 1.62 m over the floor where the
// animation started, it has at his head (the highest of his spheres, eased
// a quarter of the way each frame): the same shot of a bigger man, wherever
// his head is; a shot that looks more than 11.5 degrees away from his head,
// or has it further out than 0.45 of the picture's half width or 0.75 of its
// half height, turns towards it until it does not (the donor's win poses pan
// after the donor walking off, and he walks elsewhere); a shot closer than
// his head, horns and shoulders (the picture at his head under H / 2 tall:
// the donor's close-up of a man's face) goes back along its line. (Scaled
// about his place on the floor, the shots looked over him: Tekken 8's
// Azazel stoops, his head 2.2 to 2.4 m up as he stands, and comes down from
// the sky in his intro.)
//
// An added fighter of a man's size has the win poses' camera animations go
// with him (title/win_shot.h, win_scene() below): the donor's shot is made
// for the donor's pose, and his own goes elsewhere.
//
// The intros stand each fighter before an LED wall (an effect of the
// "entry" scene: sub_07AD75C8 sets it up for a side, sub_07AD60F0, and
// places it, 6 m behind the fighter and as big as a man's shots need). The
// effect takes its place and size once, as it starts: moving it later does
// not move what is drawn. A giant's scaled intro shots looked past it: a lit
// band or rectangle in black, with him over its edges. A giant's wall is
// placed as it is set up as his shots are: about his head, as much bigger
// (giant_wall(): the same scaling of the scene about the same points shows
// what a man's shot shows), and kWallMargin bigger again (his shots also
// turn to his head and go back for a close-up).
//
// The KO's slow motion and replays (tcb_camera_replay_t) and the throws'
// camera (tcb_camera_throw_t) frame a man from a man's distance: with a
// giant in the fight their shots go up and back until both fighters are in
// the picture (contain()).
//
// The round call ("ROUND 1", "READY", "FIGHT": tcb_camera_win_t in its
// states 0x11 to 0x13, sub_061A9D34) comes round the two fighters to where
// the fight's camera is, at its distance but at the title's own height for
// two men: its shot goes up by what the fight's camera went up, and the call
// from above (0x12), which comes down level with its point, comes down to
// the fight camera's tilt: it ends where that begins (title/round_call.h).
//
// Fights without such a fighter, and the win camera's other states (the win
// scene), are the title's own.
//
// TTT2_TRACE_CAMERA=1 logs each change; 2 also every camera the
// 2-character camera makes.

#include "title/fight_camera.h"
#include "title/round_call.h"

#include "title/giant_body.h"
#include "title/roster.h"
#include "title/win_shot.h"

#include "cafe/ppc_ops.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string_view>
#include <vector>

namespace cafe::title::fight_camera {
namespace {

constexpr uint32_t kPlayerSelectId = 84, kPlayerFloor = 72, kPlayerMove = 280, kPlayerMoveFrame = 212; // (+72 f32)
constexpr uint32_t kBodySpheres = 2168, kBodySphereSize = 24, kBodySphereRadius = 20, kBodySphereCount = 14;
constexpr uint32_t kCameraEye = 0, kCameraTarget = 16, kCameraFov = 56; // the 2-character camera's
constexpr uint32_t kCameraHolder = 0x1084FEBC, kCameraManager = 732, kRenderCamera = 392, kRenderAspect = 0x50;
constexpr float kFocus = 1042.5f;   // the title's focus height over the floor (0x10433174)
constexpr float kNearest = 4600;    // its nearest camera (0x1042B40C)
constexpr float kManHeight = 1900;  // a TTT2 fighter's height, to his focus
constexpr float kOverBody = 1.0f / 6; // of H, over his body's highest point
constexpr float kManInPicture = 0.85f; // his opponent's highest point at most this far up the picture (the health bars
                                       // cover its top tenth)
constexpr float kInFromSide = 0.65f; // of H, his body's middle from the picture's sides (his wings reach 2.2 m behind
                                     // it and flap out further walking back: tg2 at 0.6 cut a tip)
constexpr float kFarthest = 15000;
constexpr float kLead = 4;          // frames: rising, he is framed where he will be (the camera eases after its goal)
// The camera animations' camera (tcb_camera_motion_t: intros, win poses, throws' cameras): its shot (+304 eye, +320
// the point it looks at, world places once its frame ran), the fighter it plays for (+444), its frame (+404).
constexpr uint32_t kMotionShot = 304, kMotionTarget = 320, kMotionFov = 360, kMotionPlayer = 444, kMotionFrame = 404;
constexpr float kManHead = 1620;    // a man's head over the floor, as the donor's shots look at it
constexpr float kHeadEase = 0.25f;  // of the way to his head each frame
constexpr float kAwayFromHead = 0.2f; // radians (11.5 degrees): his head at most this far from the shot's middle
constexpr float kHeadAcross = 0.45f, kHeadUp = 0.75f; // and at most this far out of the picture's middle (of its half
                                                      // width, height: what 11.5 degrees is through the title's 50)
constexpr float kCloseUp = 0.5f;    // of H: the picture at his head at least this tall (his head, horns and shoulders;
                                    // the donor's intro close-up, 0.6 m of a man at 1.7 m with a 33 degree lens, scaled
                                    // by his skeleton showed only his crown)
constexpr uint32_t kSidePlayers = 0x1087FB60, kPlayerPartner = 172; // per side: its first member; +172 its partner

std::map<int, float> g_heights; // by slot

int trace() {
    static const int level = [] {
        const char* v = std::getenv("TTT2_TRACE_CAMERA");
        return v ? std::max(1, std::atoi(v)) : 0;
    }();
    return level;
}

float ldf(uint8_t* base, uint32_t at) {
    const uint32_t bits = ppc::ld32(base, at);
    float v;
    std::memcpy(&v, &bits, 4);
    return v;
}
void stf(uint8_t* base, uint32_t at, float v) {
    uint32_t bits;
    std::memcpy(&bits, &v, 4);
    ppc::st32(base, at, bits);
}

// The camera height of a fighter (0: none).
float height_of(uint32_t player) {
    if (!player) return 0;
    const auto it = g_heights.find(added_slot(player));
    return it == g_heights.end() ? 0 : it->second;
}

// His body's highest and lowest points (its spheres' tops and bottoms, as large as a man's spheres: a giant's body
// grows them, giant_body.h; none: -inf, +inf).
struct Extent {
    float top = -INFINITY, bottom = INFINITY;
};
Extent body_extent(uint8_t* base, uint32_t player) {
    Extent e;
    const float grown = giant_body::scale_of(player);
    for (uint32_t i = 0; i < kBodySphereCount; ++i) {
        const uint32_t at = player + kBodySpheres + kBodySphereSize * i;
        const float y = ldf(base, at + 4), r = ldf(base, at + kBodySphereRadius) / grown;
        if (!std::isfinite(y) || !std::isfinite(r) || r < 0 || r >= 5000) continue;
        e.top = std::max(e.top, y + r);
        e.bottom = std::min(e.bottom, y - r);
    }
    return e;
}
float body_top(uint8_t* base, uint32_t player) { return body_extent(base, player).top; }

// How fast a giant's lowest point rises (mm a frame; his frames: his move's frame or his move changes). A rise counts
// from its second frame on: what it rose in one frame and not the next is a new pose (his body's spheres take the
// round's stance a frame after the round puts him in place: 0.33 m up from the intro's last pose, and the round
// call's second frame went 2.5 m further out for that frame).
struct Rise {
    uint32_t move = 0, frame = 0;
    float lowest = NAN, rose = 0, speed = 0;
};
std::map<uint32_t, Rise> g_rises; // by fighter

float rising(uint8_t* base, uint32_t player, float lowest) {
    Rise& r = g_rises[player];
    const uint32_t move = ppc::ld32(base, player + kPlayerMove), frame = ppc::ld32(base, player + kPlayerMoveFrame);
    if (move != r.move || frame != r.frame) {
        const float rose = std::isnan(r.lowest) ? 0.0f : std::clamp(lowest - r.lowest, 0.0f, 1000.0f);
        r.speed = std::min(rose, r.rose);
        r.rose = rose;
        r.move = move;
        r.frame = frame;
        r.lowest = lowest;
    }
    return r.speed;
}

// A fighter's body's middle across the floor: the mean of his spheres (inside a move his body runs up to a metre
// ahead of or behind his position, which the title moves on at the move's end), or his position while his spheres
// are still where the title took him from: they follow a new place (a round's start, his position more than a metre
// away at once) only a frame later, and at the start of a round after a knockout 10 m away the camera went out to
// its 15 m limit for the round call's first frame. (The camera runs several times in that frame, his move changing
// in between: so it goes by his spheres, which stay as they were until they follow.)
struct Place {
    float x = NAN, z = NAN, stale_x = NAN, stale_z = NAN;
};
std::map<uint32_t, Place> g_places; // by fighter

void body_middle(uint8_t* base, uint32_t player, float& x, float& z) {
    float mx = 0, mz = 0;
    int n = 0;
    for (uint32_t i = 0; i < kBodySphereCount; ++i) {
        const uint32_t at = player + kBodySpheres + kBodySphereSize * i;
        const float sx = ldf(base, at), sz = ldf(base, at + 8);
        if (!std::isfinite(sx) || !std::isfinite(sz)) continue;
        mx += sx;
        mz += sz;
        ++n;
    }
    const float px = ldf(base, player), pz = ldf(base, player + 8);
    Place& q = g_places[player];
    if (std::hypot(px - q.x, pz - q.z) > 1000) { // (put in a new place: his spheres where he was)
        q.stale_x = mx;
        q.stale_z = mz;
    }
    q.x = px;
    q.z = pz;
    if (n && mx == q.stale_x && mz == q.stale_z) {
        x = px;
        z = pz;
        return;
    }
    q.stale_x = q.stale_z = NAN;
    x = n ? mx / n : px;
    z = n ? mz / n : pz;
}

// The giants the 2-character camera frames now (while it runs).
uint32_t g_giants[2] = {};
float g_scales[2] = {};
int g_depth = 0;

float scale_in_scope(uint32_t player) {
    if (!g_depth || !player) return 0;
    for (int k = 0; k < 2; ++k)
        if (g_giants[k] == player) return g_scales[k];
    return 0;
}

// The picture's width over its height (the render camera's; 16:9 without one).
float picture_aspect(uint8_t* base) {
    const uint32_t holder = ppc::ld32(base, kCameraHolder);
    const uint32_t manager = holder ? ppc::ld32(base, holder + kCameraManager) : 0;
    const uint32_t render = manager ? ppc::ld32(base, manager + kRenderCamera) : 0;
    if (render) {
        const float a = ldf(base, render + kRenderAspect);
        if (a > 0.5f && a < 4) return a;
    }
    return 16.0f / 9;
}

// How far up the 2-character camera's last result went for a giant (mm; 0: it was the title's own).
// g_level: that camera's eye over the point it looks at.
float g_lift = 0, g_level = 0;

// The 2-character camera's result `camera` with the giants in it.
void frame(uint8_t* base, uint32_t camera, const uint32_t fighters[2], const float heights[2]) {
    float eye[3], target[3];
    for (int k = 0; k < 3; ++k) {
        eye[k] = ldf(base, camera + kCameraEye + 4 * k);
        target[k] = ldf(base, camera + kCameraTarget + 4 * k);
    }
    const float fov = ldf(base, camera + kCameraFov);
    float forward[3] = {target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]};
    const float distance = std::hypot(forward[0], forward[1], forward[2]);
    if (!std::isfinite(distance) || distance < 100 || !(fov > 1 && fov < 170)) return;
    for (float& v : forward) v /= distance;
    const float across = std::hypot(forward[0], forward[2]);
    if (across < 0.5f) return; // (looking down from above: not a fight camera)
    const float right[2] = {-forward[2] / across, forward[0] / across};
    const float wide = std::tan(fov * 3.14159265f / 360), high = wide / picture_aspect(base); // tangents of the half angles
    // The picture at the point's distance: the title's, then what each giant needs.
    float bottom = target[1] - distance * high, top = target[1] + distance * high;
    float needed = distance;
    for (int k = 0; k < 2; ++k) {
        if (heights[k] <= 0) continue;
        const uint32_t p = fighters[k];
        const float floor = ldf(base, p + kPlayerFloor);
        bottom = std::min(bottom, floor + kFocus - kNearest * high);
        // (H over his lowest point, standing or off the floor in a jump or a juggle: his wings and horns reach
        // well over his body's spheres, which follow his bones.)
        const Extent body = body_extent(base, p);
        const float lowest = std::isfinite(body.bottom) ? std::max(body.bottom, floor) : floor;
        top = std::max({top, lowest + rising(base, p, lowest) * kLead + heights[k], body.top + heights[k] * kOverBody});
        float mx, mz; // (his body's middle across the floor)
        body_middle(base, p, mx, mz);
        const float x = mx - target[0], z = mz - target[2];
        const float side = std::fabs(x * right[0] + z * right[1]), depth = x * forward[0] + z * forward[2];
        needed = std::max(needed, (side + heights[k] * kInFromSide) / wide - depth);
    }
    for (int k = 0; k < 2; ++k) {
        // (his opponent, launched or thrown higher than the title's camera looks for a man: his throws lift a man 3.4
        // to 5.6 m, his launchers send one over his head)
        if (heights[k] > 0 || heights[1 - k] <= 0) continue;
        const uint32_t p = fighters[k];
        const Extent body = body_extent(base, p);
        if (!std::isfinite(body.top)) continue;
        const float lowest = std::max(body.bottom, ldf(base, p + kPlayerFloor));
        const float highest = body.top + rising(base, p, lowest) * kLead;
        top = std::max(top, bottom + (highest - bottom) / kManInPicture);
    }
    needed = std::min(std::max(needed, (top - bottom) / (2 * high)), kFarthest);
    if (needed <= distance + 0.5f) {
        if (trace() >= 2) std::fprintf(stderr, "ttt2: camera: the title's frames the giant (%.0f to %.0f)\n", bottom, top);
        return;
    }
    const float middle = bottom + needed * high; // the picture's bottom kept
    g_lift = middle - target[1];
    g_level = -forward[1] * needed;
    for (int k = 0; k < 3; ++k) {
        const float t = target[k] + (k == 1 ? middle - target[1] : 0);
        stf(base, camera + kCameraTarget + 4 * k, t);
        stf(base, camera + kCameraEye + 4 * k, t - forward[k] * needed);
    }
    if (trace())
        std::fprintf(stderr, "ttt2: camera: giant (sid %u %u, %.0f to %.0f): distance %.0f -> %.0f, height %.0f -> %.0f\n",
                     fighters[0] ? ppc::ld32(base, fighters[0] + kPlayerSelectId) : 0,
                     fighters[1] ? ppc::ld32(base, fighters[1] + kPlayerSelectId) : 0, bottom, top, distance, needed,
                     target[1], middle);
}

// One of the four fighters (a camera's player field can hold anything else).
bool is_player(uint8_t* base, uint32_t player) {
    if (!player) return false;
    for (uint32_t side = 0; side < 2; ++side) {
        const uint32_t first = ppc::ld32(base, kSidePlayers + 4 * side);
        if (first && (player == first || player == ppc::ld32(base, first + kPlayerPartner))) return true;
    }
    return false;
}

// The two fighters the 2-character camera framed last (the fight's two in play).
uint32_t g_pair[2] = {};

// A camera's shot with the two fighters in play in it when one is a giant: the KO's slow motion and the replays
// (tcb_camera_replay_t: its shot at +304 eye, +320 the point it looks at, +360 its horizontal field of view) look at
// the man knocked out from a man's distance, 0.3 to 3 m off the floor, and showed a giant's shins and an arm; the
// throw camera (camera 4, tcb_camera_throw_t: the fight's camera with one of its three throw shots, +424 +428 +432;
// its view as the fight's camera takes it while a throw shot plays: +16 eye, +32 the point, +72 the field of view,
// no further than 10 m, sub_06130C84) picked a low side shot for his throws that lift a man 4 to 6 m: the man over
// the picture's top, he cut at its bottom. The shot keeps its direction and goes up (along the picture's up) and back
// (along its line) as little as both need: the giant whole (H from his lowest point, 0.5 H either side of his body's
// middle for his wings), the other fighter's 14 spheres, within kInShot of the picture's sides and bottom and `top` of
// the way from its middle to its top.
constexpr float kInShot = 0.9f;
constexpr float kGiantHalfWidth = 0.5f; // of H
struct View {
    uint32_t eye, target, fov; // offsets in the camera
    float top;                 // of the picture's upper half
};
constexpr View kReplayView = {304, 320, 360, kInShot};
constexpr View kThrowView = {16, 32, 72, 2 * kManInPicture - 1}; // (below the health bars, as frame() keeps a man)
struct Point {
    float at[3], across, up; // its place, then how far it reaches across the picture and up and down it
};
// The shot each such camera made (its own) and the one written in its place: a camera that keeps its shot (one not
// playing, a still shot) is contained from its own shot again, never from the last contained one (which went further
// out every frame the fighters walked out of it).
struct Contained {
    uint32_t own[6] = {}, written[6] = {};
};
std::map<uint32_t, Contained> g_contained; // by camera

void contain(uint8_t* base, uint32_t camera, const View& view) {
    uint32_t now[6];
    for (int k = 0; k < 3; ++k) {
        now[k] = ppc::ld32(base, camera + view.eye + 4 * k);
        now[3 + k] = ppc::ld32(base, camera + view.target + 4 * k);
    }
    const auto kept = g_contained.find(camera);
    const bool unchanged = kept != g_contained.end() && std::equal(now, now + 6, kept->second.written);
    if (unchanged) std::copy(kept->second.own, kept->second.own + 6, now);
    auto put = [&](const uint32_t shot[6]) {
        for (int k = 0; k < 3; ++k) {
            ppc::st32(base, camera + view.eye + 4 * k, shot[k]);
            ppc::st32(base, camera + view.target + 4 * k, shot[3 + k]);
        }
    };
    float heights[2] = {};
    for (int k = 0; k < 2; ++k)
        if (is_player(base, g_pair[k])) heights[k] = height_of(g_pair[k]);
    if (heights[0] <= 0 && heights[1] <= 0) {
        if (unchanged) put(now); // (its own shot back)
        g_contained.erase(camera);
        return;
    }
    Contained& record = g_contained[camera];
    std::copy(now, now + 6, record.own);
    std::copy(now, now + 6, record.written);
    float eye[3], target[3];
    for (int k = 0; k < 3; ++k) {
        std::memcpy(&eye[k], &now[k], 4);
        std::memcpy(&target[k], &now[3 + k], 4);
    }
    if (unchanged) put(now);
    const float fov = ldf(base, camera + view.fov);
    float f[3] = {target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]};
    const float reach = std::hypot(f[0], f[1], f[2]);
    if (!std::isfinite(reach) || reach < 1 || !(fov > 1 && fov < 170)) return;
    for (float& v : f) v /= reach;
    const float flat = std::hypot(f[0], f[2]);
    if (flat < 0.2f) return; // (straight down: no picture's up to go along)
    const float r[3] = {-f[2] / flat, 0, f[0] / flat};                                    // the picture's right
    const float u[3] = {r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]}; // its up
    const float wide = std::tan(fov * 3.14159265f / 360), high = wide / picture_aspect(base); // (tangents, half picture)
    std::vector<Point> points;
    for (int k = 0; k < 2; ++k) {
        const uint32_t p = g_pair[k];
        if (!is_player(base, p)) continue;
        if (heights[k] > 0) {
            const Extent body = body_extent(base, p);
            const float floor = ldf(base, p + kPlayerFloor);
            const float lowest = std::isfinite(body.bottom) ? std::max(body.bottom, floor) : floor;
            float mx = 0, mz = 0;
            int n = 0;
            for (uint32_t i = 0; i < kBodySphereCount; ++i) {
                const uint32_t at = p + kBodySpheres + kBodySphereSize * i;
                const float sx = ldf(base, at), sz = ldf(base, at + 8);
                if (!std::isfinite(sx) || !std::isfinite(sz)) continue;
                mx += sx, mz += sz, ++n;
            }
            if (!n) mx = ldf(base, p), mz = ldf(base, p + 8), n = 1;
            const float half = heights[k] * kGiantHalfWidth;
            points.push_back({{mx / n, lowest, mz / n}, half, 0});
            points.push_back({{mx / n, lowest + heights[k], mz / n}, half, 0});
        } else {
            for (uint32_t i = 0; i < kBodySphereCount; ++i) {
                const uint32_t at = p + kBodySpheres + kBodySphereSize * i;
                const float c[3] = {ldf(base, at), ldf(base, at + 4), ldf(base, at + 8)}, radius = ldf(base, at + kBodySphereRadius);
                if (!std::isfinite(c[0]) || !std::isfinite(c[1]) || !std::isfinite(c[2]) || !(radius >= 0 && radius < 5000))
                    continue;
                points.push_back({{c[0], c[1], c[2]}, radius, radius});
            }
        }
    }
    if (points.empty()) return;
    // How far back the shot needs to go, raised by `lift` along its up (a convex function of the lift).
    auto back_for = [&](float lift) {
        float need = -INFINITY;
        for (const Point& q : points) {
            const float d[3] = {q.at[0] - eye[0], q.at[1] - eye[1], q.at[2] - eye[2]};
            const float z = d[0] * f[0] + d[1] * f[1] + d[2] * f[2], x = d[0] * r[0] + d[2] * r[2],
                        y = d[0] * u[0] + d[1] * u[1] + d[2] * u[2] - lift;
            need = std::max({need, (std::fabs(x) + q.across) / (wide * kInShot) - z, (q.up - y) / (high * kInShot) - z,
                             (y + q.up) / (high * view.top) - z});
        }
        return need;
    };
    if (back_for(0) <= 0) return; // (both in the picture already)
    float lo = 0, hi = std::max(heights[0], heights[1]);
    for (int i = 0; i < 40; ++i) {
        const float a = lo + (hi - lo) / 3, b = hi - (hi - lo) / 3;
        if (back_for(a) <= back_for(b)) hi = b;
        else lo = a;
    }
    const float lift = (lo + hi) / 2, back = std::clamp(back_for(lift), 0.0f, kFarthest);
    for (int k = 0; k < 3; ++k) {
        stf(base, camera + view.eye + 4 * k, eye[k] - f[k] * back + u[k] * lift);
        stf(base, camera + view.target + 4 * k, target[k] + u[k] * lift);
        record.written[k] = ppc::ld32(base, camera + view.eye + 4 * k);
        record.written[3 + k] = ppc::ld32(base, camera + view.target + 4 * k);
    }
    if (trace())
        std::fprintf(stderr, "ttt2: camera: %s shot with a giant (sid %u %u): up %.0f, back %.0f (eye %.0f %.0f %.0f, fov %.1f)\n",
                     view.eye == kReplayView.eye ? "replay" : "throw", ppc::ld32(base, g_pair[0] + kPlayerSelectId),
                     ppc::ld32(base, g_pair[1] + kPlayerSelectId), lift, back, eye[0], eye[1], eye[2], fov);
}

// The round call's shot (the win camera's, +304 eye, +320 the point it looks at, as it comes round the two fighters
// in play) with a giant among them: up by what the fight's camera went up, its eye only as it comes down to that
// camera's height (round_call.h).
constexpr uint32_t kWinShot = 304, kWinTarget = 320, kWinState = 408;
constexpr uint32_t kCallFromAbove = 0x12;

void round_call_after(uint8_t* base, uint32_t camera) {
    bool giant = false;
    for (const uint32_t p : g_pair)
        if (is_player(base, p) && height_of(p) > 0) giant = true;
    if (!giant) return;
    float eye[3], target[3];
    for (int k = 0; k < 3; ++k) {
        eye[k] = ldf(base, camera + kWinShot + 4 * k);
        target[k] = ldf(base, camera + kWinTarget + 4 * k);
    }
    const uint32_t state = ppc::ld32(base, camera + kWinState);
    const float over = eye[1] - target[1]; // (the title's own)
    if (!round_call::raise(eye, target, g_lift, g_level)) return;
    if (state == kCallFromAbove) eye[1] = target[1] + round_call::from_above(over, g_lift, g_level);
    stf(base, camera + kWinShot + 4, eye[1]);
    stf(base, camera + kWinTarget + 4, target[1]);
    if (trace())
        std::fprintf(stderr, "ttt2: camera: round call with a giant (sid %u %u, state %u): up %.0f, level %.0f (eye %.0f %.0f %.0f, point %.0f %.0f %.0f)\n",
                     ppc::ld32(base, g_pair[0] + kPlayerSelectId), ppc::ld32(base, g_pair[1] + kPlayerSelectId), state,
                     g_lift, g_level, eye[0], eye[1], eye[2], target[0], target[1], target[2]);
}

// A camera animation's camera playing for a giant: its shot as the animation made it (restored before its next frame,
// so the camera never runs on a scaled shot), scaled about his place on the floor as its animation started.
struct Motion {
    uint32_t player = 0, frame = 0;
    float centre[3] = {}, head[3] = {};
    float shot[6] = {};
    bool scaled = false;
    uint32_t move = 0; // (win_scene)
    float seen[3] = {}; // (win_scene) his head as last read
};
std::map<uint32_t, Motion> g_motions; // by camera

// The intros' LED wall: the effect of the wall's object (sub_07AD75C8's scene +608, the effect at +228); an effect's
// place (+944, or +1028 for one its file marks so: +92 bit 0x80, as sub_08BE5688 puts it) and scale (+1024,
// sub_08BE5FC4's: its matrix's, sub_08BDE41C) count as it starts.
constexpr uint32_t kSceneWall = 608, kWallEffect = 228;
constexpr uint32_t kEffectFile = 932, kEffectScale = 1024, kEffectPlace = 944, kEffectPlaceMarked = 1028;
constexpr uint32_t kFileFlags = 92, kFileMarked = 0x80;
constexpr uint32_t kPlayerActive = 7808; // 0: the side's first member is out, its partner plays (sub_05C5EF14)
constexpr float kWallMargin = 1.4f;      // the giant's wall this much bigger again, about his head

// The wall of a side's intro (sub_07AD75C8 set it up for the side's fighter in play): for a giant, placed and sized
// as his intro shots are scaled (motion_after(): what a man's shot has at a man's head, his shot has at his head,
// his body's size times as far).
void giant_wall(uint8_t* base, uint32_t scene, uint32_t side) {
    if (side > 1) return;
    uint32_t player = ppc::ld32(base, kSidePlayers + 4 * side);
    if (player && !ppc::ld32(base, player + kPlayerActive)) player = ppc::ld32(base, player + kPlayerPartner);
    if (!is_player(base, player)) return;
    const float scale = giant_body::scale_of(player);
    if (!(scale > 1)) return;
    const uint32_t wall = ppc::ld32(base, scene + kSceneWall);
    const uint32_t effect = wall ? ppc::ld32(base, wall + kWallEffect) : 0;
    const uint32_t file = effect ? ppc::ld32(base, effect + kEffectFile) : 0;
    if (!file) return;
    const uint32_t at = ppc::ld32(base, file + kFileFlags) & kFileMarked ? kEffectPlaceMarked : kEffectPlace;
    const float centre[3] = {ldf(base, player), ldf(base, player + kPlayerFloor), ldf(base, player + 8)};
    // His head: as his standing pose has it (the highest of his spheres; a man's head grown by his size if that is
    // not between a man's and that).
    float head[3] = {centre[0], centre[1] + kManHead * scale, centre[2]}, highest = -INFINITY;
    for (uint32_t i = 0; i < kBodySphereCount; ++i) {
        const uint32_t s = player + kBodySpheres + kBodySphereSize * i;
        const float c[3] = {ldf(base, s), ldf(base, s + 4), ldf(base, s + 8)};
        if (std::isfinite(c[0]) && std::isfinite(c[1]) && std::isfinite(c[2]) && c[1] > highest) {
            highest = c[1];
            if (c[1] - centre[1] > kManHead && c[1] - centre[1] < kManHead * scale) std::copy(c, c + 3, head);
        }
    }
    float place[3];
    for (int k = 0; k < 3; ++k) {
        const float from = centre[k] + (k == 1 ? kManHead : 0);
        place[k] = head[k] + scale * (ldf(base, effect + at + 4 * k) - from);
    }
    const float was = ldf(base, effect + kEffectScale), grown = was * scale * kWallMargin;
    if (!std::isfinite(place[0]) || !std::isfinite(place[1]) || !std::isfinite(place[2]) || !std::isfinite(grown)) return;
    if (trace())
        std::fprintf(stderr, "ttt2: camera: the intro's LED wall for a giant (sid %u, head %.0f %.0f %.0f): %.0f %.0f %.0f "
                     "scale %.2f (the title's %.0f %.0f %.0f scale %.2f)\n", ppc::ld32(base, player + kPlayerSelectId),
                     head[0], head[1], head[2], place[0], place[1], place[2], grown, ldf(base, effect + at),
                     ldf(base, effect + at + 4), ldf(base, effect + at + 8), was);
    for (int k = 0; k < 3; ++k) stf(base, effect + at + 4 * k, place[k]);
    stf(base, effect + kEffectScale, grown);
}

void motion_before(uint8_t* base, uint32_t camera) {
    const auto it = g_motions.find(camera);
    if (it == g_motions.end() || !it->second.scaled) return;
    for (int k = 0; k < 3; ++k) {
        stf(base, camera + kMotionShot + 4 * k, it->second.shot[k]);
        stf(base, camera + kMotionTarget + 4 * k, it->second.shot[3 + k]);
    }
    it->second.scaled = false;
}

// The win scene's shot of an added fighter of a man's size (title/win_shot.h): the donor's camera animation, made
// for the donor's pose, goes with the fighter's own. -> whether the camera's shot is such a one (its Motion is then
// kept: motion_before puts the animation's shot back before the camera's next frame).
constexpr uint32_t kPlayerAlone = 1012; // nonzero: no team (+172 is set all the same)
constexpr uint32_t kHeadSphere = 8;     // of a fighter's 14: its head's

bool win_scene(uint8_t* base, uint32_t camera, uint32_t player) {
    if (!is_player(base, player) || added_slot(player) < 0) return false;
    const uint32_t move = ppc::ld32(base, player + kPlayerMove), name = move ? ppc::ld32(base, move) : 0;
    if (!name) return false;
    const char* text = reinterpret_cast<const char*>(base + name);
    if (!win_shot::films_one(std::string_view(text, strnlen(text, 64)), ppc::ld32(base, player + kPlayerAlone) != 0))
        return false;

    Motion& m = g_motions[camera];
    const uint32_t frame = ppc::ld32(base, camera + kMotionFrame);
    const bool starts = m.player != player || m.move != move || frame < m.frame;
    m.player = player, m.move = move, m.frame = frame, m.scaled = false;
    // Where the shot expects a head (a man's, over the fighter's place: its pose leaves that where it is) and where
    // his is (his place's, until his body's spheres are his pose's: they are the last scene's for a frame).
    const float expected[3] = {ldf(base, player), ldf(base, player + kPlayerFloor) + win_shot::kManHead, ldf(base, player + 8)};
    const uint32_t at = player + kBodySpheres + kBodySphereSize * kHeadSphere;
    float head[3] = {ldf(base, at), ldf(base, at + 4), ldf(base, at + 8)};
    if (starts) std::copy(expected, expected + 3, m.seen);
    if (win_shot::plausible(expected, m.seen, head)) std::copy(head, head + 3, m.seen);
    else std::copy(expected, expected + 3, head);
    for (int k = 0; k < 3; ++k) m.head[k] = starts ? expected[k] : m.head[k] + kHeadEase * (head[k] - m.head[k]);
    for (int k = 0; k < 3; ++k) {
        m.shot[k] = ldf(base, camera + kMotionShot + 4 * k);
        m.shot[3 + k] = ldf(base, camera + kMotionTarget + 4 * k);
    }
    for (float v : m.shot)
        if (!std::isfinite(v)) return true;
    float eye[3], target[3];
    std::copy(m.shot, m.shot + 3, eye);
    std::copy(m.shot + 3, m.shot + 6, target);
    const float fov = ldf(base, camera + kMotionFov);
    win_shot::follow(eye, target, expected, m.head);
    // (his head as it is, not as the shot's move has eased it: a pose that runs leaves the eased one behind)
    const bool turned = win_shot::keep(eye, target, head, fov, picture_aspect(base));
    for (int k = 0; k < 3; ++k) {
        stf(base, camera + kMotionShot + 4 * k, eye[k]);
        stf(base, camera + kMotionTarget + 4 * k, target[k]);
    }
    m.scaled = true;
    if (trace() && (trace() >= 2 || starts || frame % 10 == 0))
        std::fprintf(stderr, "ttt2: camera: win shot for sid %u frame %u%s: head %.0f %.0f %.0f, expected %.0f %.0f %.0f%s, fov %.1f: eye %.0f %.0f %.0f target %.0f %.0f %.0f -> eye %.0f %.0f %.0f target %.0f %.0f %.0f\n",
                     ppc::ld32(base, player + kPlayerSelectId), frame, starts ? " (starts)" : "", m.head[0], m.head[1],
                     m.head[2], expected[0], expected[1], expected[2], turned ? ", turned" : "", fov, m.shot[0],
                     m.shot[1], m.shot[2], m.shot[3], m.shot[4], m.shot[5], eye[0], eye[1], eye[2], target[0],
                     target[1], target[2]);
    return true;
}

void motion_after(uint8_t* base, uint32_t camera) {
    const uint32_t player = ppc::ld32(base, camera + kMotionPlayer);
    const float height = is_player(base, player) ? height_of(player) : 0;
    if (height <= 0) {
        if (!win_scene(base, camera, player)) g_motions.erase(camera);
        return;
    }
    Motion& m = g_motions[camera];
    const uint32_t frame = ppc::ld32(base, camera + kMotionFrame);
    const bool starts = m.player != player || frame < m.frame;
    if (starts) {
        m.player = player;
        m.centre[0] = ldf(base, player);
        m.centre[1] = ldf(base, player + kPlayerFloor);
        m.centre[2] = ldf(base, player + 8);
    }
    // His head: the centre of his highest sphere (the floor's man's head if none).
    float head[3] = {m.centre[0], m.centre[1] + kManHead, m.centre[2]};
    float highest = -INFINITY;
    for (uint32_t i = 0; i < kBodySphereCount; ++i) {
        const uint32_t at = player + kBodySpheres + kBodySphereSize * i;
        const float c[3] = {ldf(base, at), ldf(base, at + 4), ldf(base, at + 8)};
        if (std::isfinite(c[0]) && std::isfinite(c[1]) && std::isfinite(c[2]) && c[1] > highest) {
            highest = c[1];
            std::copy(c, c + 3, head);
        }
    }
    for (int k = 0; k < 3; ++k) m.head[k] = starts ? head[k] : m.head[k] + kHeadEase * (head[k] - m.head[k]);
    m.frame = frame;
    const float grown = giant_body::scale_of(player), scale = grown > 1 ? grown : height / kManHeight;
    for (int k = 0; k < 3; ++k) {
        m.shot[k] = ldf(base, camera + kMotionShot + 4 * k);
        m.shot[3 + k] = ldf(base, camera + kMotionTarget + 4 * k);
    }
    for (float v : m.shot)
        if (!std::isfinite(v)) return;
    float eye[3], target[3];
    for (int k = 0; k < 3; ++k) {
        const float from = m.centre[k] + (k == 1 ? kManHead : 0); // (a man's head where the animation started)
        eye[k] = m.head[k] + scale * (m.shot[k] - from);
        target[k] = m.head[k] + scale * (m.shot[3 + k] - from);
    }
    // A shot that looks away from him (the donor's win pose follows the donor walking off) turns to keep his head
    // within kAwayFromHead of the middle of the picture.
    float look[3], to_head[3];
    for (int k = 0; k < 3; ++k) {
        look[k] = target[k] - eye[k];
        to_head[k] = m.head[k] - eye[k];
    }
    const float reach = std::hypot(look[0], look[1], look[2]), head_far = std::hypot(to_head[0], to_head[1], to_head[2]);
    if (reach > 1 && head_far > 1) {
        const float cosine = (look[0] * to_head[0] + look[1] * to_head[1] + look[2] * to_head[2]) / (reach * head_far);
        const float away = std::acos(std::clamp(cosine, -1.0f, 1.0f));
        if (away > kAwayFromHead && away < 3.1f) {
            const float turn = away - kAwayFromHead, a = std::sin(away - turn) / std::sin(away), b = std::sin(turn) / std::sin(away);
            for (int k = 0; k < 3; ++k) target[k] = eye[k] + reach * (a * look[k] / reach + b * to_head[k] / head_far);
        }
    }
    // ... and, through a narrower lens (the donor's win pose la_wnm_1: 25.5 degrees, his head at its left edge as he
    // walks off the other way), within kHeadAcross of the picture's half width and kHeadUp of its half height.
    if (const float fov = ldf(base, camera + kMotionFov); fov > 1 && fov < 170 && reach > 1) {
        float f[3];
        for (int k = 0; k < 3; ++k) f[k] = (target[k] - eye[k]) / reach;
        const float flat = std::hypot(f[0], f[2]);
        const float wide = std::tan(fov * 3.14159265f / 360), high = wide / picture_aspect(base);
        const float d[3] = {m.head[0] - eye[0], m.head[1] - eye[1], m.head[2] - eye[2]};
        const float z = d[0] * f[0] + d[1] * f[1] + d[2] * f[2];
        if (flat > 0.2f && z > 1) {
            const float r[3] = {-f[2] / flat, 0, f[0] / flat};
            const float u[3] = {r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]};
            const float x = (d[0] * r[0] + d[2] * r[2]) / (z * wide), y = (d[0] * u[0] + d[1] * u[1] + d[2] * u[2]) / (z * high);
            const float x2 = std::clamp(x, -kHeadAcross, kHeadAcross), y2 = std::clamp(y, -kHeadUp, kHeadUp);
            if (x2 != x || y2 != y) {
                // (the point the shot now looks along: his head moved back to (x2, y2) of the picture)
                float to[3];
                for (int k = 0; k < 3; ++k) to[k] = d[k] - r[k] * x2 * z * wide - u[k] * y2 * z * high;
                const float n = std::hypot(to[0], to[1], to[2]);
                if (n > 1)
                    for (int k = 0; k < 3; ++k) target[k] = eye[k] + reach * to[k] / n;
            }
        }
    }
    // A shot closer than a close-up of his head and shoulders (the donor's close-up of a man's face) goes back along
    // its own line until the picture at his head is kCloseUp H tall.
    float pulled = 0;
    if (const float fov = ldf(base, camera + kMotionFov); fov > 1 && fov < 170) {
        float look_dir[3];
        for (int k = 0; k < 3; ++k) look_dir[k] = target[k] - eye[k];
        const float reach = std::hypot(look_dir[0], look_dir[1], look_dir[2]);
        if (reach > 1) {
            for (float& v : look_dir) v /= reach;
            const float depth = (m.head[0] - eye[0]) * look_dir[0] + (m.head[1] - eye[1]) * look_dir[1] +
                                (m.head[2] - eye[2]) * look_dir[2];
            const float high = std::tan(fov * 3.14159265f / 360) / picture_aspect(base);
            const float wanted = kCloseUp * height / (2 * high);
            if (depth > 0 && depth < wanted) {
                pulled = wanted - depth;
                for (int k = 0; k < 3; ++k) eye[k] -= look_dir[k] * pulled;
            }
        }
    }
    for (int k = 0; k < 3; ++k) {
        stf(base, camera + kMotionShot + 4 * k, eye[k]);
        stf(base, camera + kMotionTarget + 4 * k, target[k]);
    }
    m.scaled = true;
    if (trace() && (trace() >= 2 || frame % 10 == 0))
        std::fprintf(stderr, "ttt2: camera: animation for sid %u frame %u (from %.0f %.0f %.0f, head %.0f %.0f %.0f, x%.2f, back %.0f, fov %.1f): eye %.0f %.0f %.0f target %.0f %.0f %.0f | origin %.0f %.0f %.0f | at %.0f %.0f %.0f\n",
                     ppc::ld32(base, player + kPlayerSelectId), frame, m.centre[0], m.centre[1], m.centre[2], m.head[0],
                     m.head[1], m.head[2], scale, pulled, ldf(base, camera + kMotionFov),
                     m.shot[0], m.shot[1], m.shot[2], m.shot[3], m.shot[4], m.shot[5], ldf(base, camera + 424),
                     ldf(base, camera + 428), ldf(base, camera + 432), ldf(base, player), ldf(base, player + 4),
                     ldf(base, player + 8));
}

} // namespace

void configure(int slot, float height) {
    if (height > 0) g_heights[slot] = height;
    else g_heights.erase(slot);
    std::fprintf(stderr, "ttt2: fight camera: the added fighter %d is framed %.0f mm tall\n", slot, height);
}

} // namespace cafe::title::fight_camera

using namespace cafe;
using namespace cafe::title::fight_camera;

PPC_FUNC(sub_05FBE5B4_orig); // the camera animations' camera's frame (r3 the camera)
PPC_FUNC(sub_05FBE5B4) {
    const uint32_t camera = ctx.r[3];
    motion_before(base, camera);
    sub_05FBE5B4_orig(ctx, base);
    motion_after(base, camera);
}

PPC_FUNC(sub_07AD75C8_orig); // the intros' LED wall of a side (r3 the entry scene, r4 the side): set up and placed
PPC_FUNC(sub_07AD75C8) {
    const uint32_t scene = ctx.r[3], side = ctx.r[4];
    sub_07AD75C8_orig(ctx, base);
    giant_wall(base, scene, side);
}

PPC_FUNC(sub_060B44E4_orig); // the replay camera's frame (r3 the camera): the KO's slow motion, replays
PPC_FUNC(sub_060B44E4) {
    const uint32_t camera = ctx.r[3];
    sub_060B44E4_orig(ctx, base);
    contain(base, camera, kReplayView);
}

PPC_FUNC(sub_06130C84_orig); // the throw camera's view from its shot (r3 the camera, r4 its view +16, r5 its shot +304)
PPC_FUNC(sub_06130C84) {
    const uint32_t camera = ctx.r[3];
    sub_06130C84_orig(ctx, base);
    // (while one of its three throw shots plays, as sub_061308BC tells the fight's camera; its shot is the fight's
    // camera's otherwise, which frame() made)
    bool playing = false;
    for (const uint32_t at : {424u, 428u, 432u})
        if (const uint32_t shot = ppc::ld32(base, camera + at); shot && ppc::ld32(base, shot + 764)) playing = true;
    if (playing) contain(base, camera, kThrowView);
}

PPC_FUNC(sub_061A9D34_orig); // the win camera's frame in the round call (r3 the camera; its states 0x11 to 0x13)
PPC_FUNC(sub_061A9D34) {
    const uint32_t camera = ctx.r[3];
    sub_061A9D34_orig(ctx, base);
    // (still calling: the frame that ends the round call puts the camera's idle shot there)
    if (const uint32_t state = ppc::ld32(base, camera + kWinState); state >= 0x11 && state <= 0x13)
        round_call_after(base, camera);
}

PPC_FUNC(sub_05FB6FEC_orig); // a fighter's focus point (r3 out: x y z, r4 &fighter)
PPC_FUNC(sub_05FB6FEC) {
    const uint32_t out = ctx.r[3], player = ctx.r[4] ? ppc::ld32(base, ctx.r[4]) : 0;
    sub_05FB6FEC_orig(ctx, base);
    if (const float scale = scale_in_scope(player); scale > 1) {
        const float floor = ldf(base, player + kPlayerFloor), y = ldf(base, out + 4);
        stf(base, out + 4, floor + std::max((y - floor) / scale, kFocus));
    }
}

PPC_FUNC(sub_05FC085C_orig); // the 2-character camera (r3 out, r4 r5 cameras, r6 r7 the fighters, r8, r9)
PPC_FUNC(sub_05FC085C) {
    const uint32_t camera = ctx.r[3], fighters[2] = {ctx.r[6], ctx.r[7]};
    const float heights[2] = {height_of(fighters[0]), height_of(fighters[1])};
    if (fighters[0] && fighters[1]) g_pair[0] = fighters[0], g_pair[1] = fighters[1], g_lift = 0;
    // (Without both fighters and their moves the title makes no camera: sub_05FC085C returns at once.)
    const bool giant = fighters[0] && fighters[1] && (heights[0] > 0 || heights[1] > 0) &&
                       ppc::ld32(base, fighters[0] + kPlayerMove) && ppc::ld32(base, fighters[1] + kPlayerMove);
    if (giant) {
        for (int k = 0; k < 2; ++k) {
            g_giants[k] = heights[k] > 0 ? fighters[k] : 0;
            g_scales[k] = heights[k] / kManHeight;
        }
        ++g_depth;
    }
    sub_05FC085C_orig(ctx, base);
    if (giant) {
        --g_depth;
        frame(base, camera, fighters, heights);
    }
    if (trace() >= 2 && fighters[0] && fighters[1])
        std::fprintf(stderr, "ttt2: camera: 2-character eye %.1f %.1f %.1f target %.1f %.1f %.1f fov %.1f | sid %u top %.0f | sid %u top %.0f\n",
                     ldf(base, camera), ldf(base, camera + 4), ldf(base, camera + 8), ldf(base, camera + 16),
                     ldf(base, camera + 20), ldf(base, camera + 24), ldf(base, camera + kCameraFov),
                     ppc::ld32(base, fighters[0] + kPlayerSelectId), body_top(base, fighters[0]),
                     ppc::ld32(base, fighters[1] + kPlayerSelectId), body_top(base, fighters[1]));
}
