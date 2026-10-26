// Integration with the player's generated game, using only its input
// conversion routine. No game data or instruction encodings live in this test.
#include "cafe/input.h"
#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"

#include <array>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>

PPC_FUNC(imp_vpad_VPADRead);
PPC_FUNC(sub_03F52F20); // converts a pad's buttons into the fighter's directions

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("expected the matching Tekken.rpx path");
        std::ifstream file(argv[1], std::ios::binary);
        if (!file) throw std::runtime_error("cannot read Tekken.rpx");
        const std::vector<uint8_t> rpx{std::istreambuf_iterator<char>(file), {}};
        cafe::reserve_guest_memory();
        cafe::load_image(rpx);
        cafe::commit_guest_memory(0x10000, 0x10000);
        auto* base = cafe::guest_base();
        struct Direction { float x, y; uint32_t dpad, fighter; };
        using namespace cafe::os;
        constexpr std::array directions{
            Direction{0, 0, 0, 1u << 5},
            Direction{-1, 0, vpad::kLeft, 1u << 4},
            Direction{1, 0, vpad::kRight, 1u << 6},
            Direction{0, 1, vpad::kUp, 1u << 8},
            Direction{0, -1, vpad::kDown, 1u << 2},
            Direction{-1, 1, vpad::kLeft | vpad::kUp, 1u << 7},
            Direction{1, 1, vpad::kRight | vpad::kUp, 1u << 9},
            Direction{-1, -1, vpad::kLeft | vpad::kDown, 1u << 1},
            Direction{1, -1, vpad::kRight | vpad::kDown, 1u << 3},
        };
        // The usual Wii U control scheme, normally filled by static
        // constructors. Initialize this fixture without starting the game.
        constexpr std::array layout{
            vpad::kLeft | vpad::kDown, vpad::kDown, vpad::kRight | vpad::kDown,
            vpad::kLeft, 0u, vpad::kRight, vpad::kLeft | vpad::kUp,
            vpad::kUp, vpad::kRight | vpad::kUp,
        };
        for (size_t i = 0; i < layout.size(); ++i) cafe::ppc::st32(base, 0x107c41a0 + 4 * i, layout[i]);
        for (const bool analog : {true, false}) {
            for (const auto& d : directions) {
                set_gamepad_state(analog ? GamepadState{0, d.x, d.y} : GamepadState{d.dpad});
                cafe::PPCContext ctx{};
                ctx.r[1] = 0x1f000;
                ctx.r[3] = 0;
                ctx.r[4] = 0x10000;
                ctx.r[5] = 1;
                ctx.r[6] = 0x10100;
                imp_vpad_VPADRead(ctx, base);
                const uint32_t buttons = cafe::ppc::ld32(base, 0x10000);
                ctx.r[3] = 0x12000; // zeroed scratch fighter
                ctx.r[4] = 0;       // first control scheme
                ctx.r[5] = buttons;
                ctx.r[6] = buttons;
                ctx.r[7] = 0x11000; // no ancillary button data
                sub_03F52F20(ctx, base);
                const uint32_t actual = cafe::ppc::ld32(base, 0x12000 + 2036);
                if (actual != d.fighter) {
                    std::fprintf(stderr, "FAIL: %s (%g,%g): VPAD=%08X fighter direction=%08X expected=%08X\n",
                                 analog ? "LS" : "DP", d.x, d.y, buttons, actual, d.fighter);
                    return 1;
                }
            }
        }
        std::puts("Original combat input routine accepts all eight directions in leverless LS and DP modes");
        return 0;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "FAIL: %s\n", e.what());
        return 1;
    }
}
