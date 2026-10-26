#include "cafe/input.h"
#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <stdexcept>

PPC_FUNC(imp_vpad_VPADRead);

namespace {
using namespace cafe;
using namespace cafe::os;
constexpr uint32_t kStatus = 0x10000, kError = 0x10100;

void check(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

struct Sample {
    uint32_t hold, trigger, release;
    float lx, ly, rx, ry;
};

Sample read(GamepadState state) {
    set_gamepad_state(state);
    PPCContext ctx{};
    ctx.r[3] = 0;
    ctx.r[4] = kStatus;
    ctx.r[5] = 1;
    ctx.r[6] = kError;
    auto* base = guest_base();
    imp_vpad_VPADRead(ctx, base);
    check(ctx.r[3] == 1 && ppc::ld32(base, kError) == 0, "VPADRead succeeds");
    auto axis = [&](uint32_t offset) { return ppc::load_single(ppc::ld32(base, kStatus + offset)); };
    return {ppc::ld32(base, kStatus), ppc::ld32(base, kStatus + 4), ppc::ld32(base, kStatus + 8),
            static_cast<float>(axis(12)), static_cast<float>(axis(16)),
            static_cast<float>(axis(20)), static_cast<float>(axis(24))};
}
}

int main() {
    try {
        reserve_guest_memory();
        commit_guest_memory(kStatus, 4096);
        // A leverless can report either a digital hat (DP) or a left stick
        // (LS). Combat must receive the same movement in both modes.
        struct Direction { uint32_t button, emulation; float x, y; };
        constexpr std::array directions{
            Direction{vpad::kLeft, 0x40000000, -1, 0},
            Direction{vpad::kRight, 0x20000000, 1, 0},
            Direction{vpad::kUp, 0x10000000, 0, 1},
            Direction{vpad::kDown, 0x08000000, 0, -1},
            Direction{vpad::kLeft | vpad::kUp, 0x50000000, -1, 1},
            Direction{vpad::kRight | vpad::kUp, 0x30000000, 1, 1},
            Direction{vpad::kLeft | vpad::kDown, 0x48000000, -1, -1},
            Direction{vpad::kRight | vpad::kDown, 0x28000000, 1, -1},
        };
        constexpr uint32_t attacks = vpad::kA | vpad::kB | vpad::kX | vpad::kY;
        for (const auto& d : directions) {
            read({});
            const uint32_t expected = d.button | d.emulation | attacks;
            const auto dp = read({d.button | attacks});
            check(dp.lx == d.x && dp.ly == d.y, "digital leverless directions also reach stick axes");
            check(dp.hold == expected && dp.trigger == expected && dp.release == 0,
                  "digital directions, Wii U stick flags and attacks press together");
            const auto held = read({d.button | attacks});
            check(held.hold == expected && held.trigger == 0 && held.release == 0, "holding does not retrigger");
            const auto released = read({});
            check(released.hold == 0 && released.release == expected && released.lx == 0 && released.ly == 0,
                  "releasing clears movement and emits release flags");
            const auto ls = read({attacks, d.x, d.y});
            check(ls.lx == dp.lx && ls.ly == dp.ly && ls.hold == expected && ls.trigger == expected,
                  "LS mode produces the D-pad bits combat needs, matching DP mode");
            const auto ls_released = read({});
            check(ls_released.hold == 0 && ls_released.release == expected,
                  "releasing LS mode releases the synthesized D-pad bits too");
        }
        const auto opposite = read({vpad::kLeft | vpad::kRight | vpad::kUp | vpad::kDown | attacks});
        check(opposite.hold == attacks && opposite.lx == 0 && opposite.ly == 0,
              "simultaneous opposite digital directions are neutral");
        const auto diagonal = read({vpad::kLeft | vpad::kRight | vpad::kDown});
        check(diagonal.lx == 0 && diagonal.ly == -1 && diagonal.hold == (vpad::kDown | 0x08000000),
              "horizontal opposites preserve vertical movement");
        const auto analog = read({vpad::kStickL | vpad::kStickR, 0.25f, -0.75f, -0.8f, 0.9f});
        check(analog.lx == 0.25f && analog.ly == -0.75f && analog.rx == -0.8f && analog.ry == 0.9f,
              "analog precision and the right stick are preserved");
        check(analog.hold == (vpad::kStickL | vpad::kStickR | vpad::kDown | 0x08000000 | 0x04000000 | 0x01000000),
              "both sticks have independent direction flags and thumb clicks");
        const auto neutral = read({0, 0.1f, -0.1f, 0.1f, -0.1f});
        check(neutral.hold == 0, "small analog movement does not emit digital direction flags");
        const auto right_only = read({0, 0, 0, 1, -1});
        check((right_only.hold & (vpad::kLeft | vpad::kRight | vpad::kUp | vpad::kDown)) == 0,
              "the right stick does not move the fighter");
        const auto mixed = read({vpad::kRight, -0.2f, 0.25f});
        check(mixed.lx == 1 && mixed.ly == 0.25f, "digital axis overrides analog drift without changing the other axis");
        read({});
        arm_select_chord(true);
        const auto chord = read({vpad::kMinus | vpad::kB, -1, 0});
        check(!(chord.hold & vpad::kMinus) && (chord.hold & vpad::kLeft),
              "practice Select chord is consumed while leverless movement remains available");
        check(take_select_chord() && !take_select_chord(), "practice chord is delivered exactly once");
        read({});
        const auto start = read({vpad::kPlus, 1, 0});
        check((start.hold & vpad::kPlus) && (start.hold & vpad::kRight),
              "Start remains available alongside leverless movement");
        std::puts("VPAD leverless DP/LS, diagonals, attacks, transitions, opposite directions, analog input and Select chord passed");
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "FAIL: %s\n", e.what());
        return 1;
    }
}
