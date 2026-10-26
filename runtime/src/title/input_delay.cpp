// The title's input delay: the fighters act on their buttons two frames
// after the game reads them, in every mode (the Wii U game's own, which
// Cemu's "Reduce input lag" graphic pack takes away).
//
// Each frame a fighter's input (sub_03F536C8) puts the pad's buttons at the
// front of its side's queue in the object at *0x107B391C (sub_02EF7DC8) and
// takes from it the buttons of as many frames back as the object's first
// word says (sub_02EF8828). That word is set (sub_02EF9010) when a mode
// starts (sub_06ECC76C, sub_06EDCD8C) to the title's default delay, which
// only sub_05C5D7B0 reads (the word at 0x107CDE3C: 2 frames), and by
// Practice's Input Delay setting (sub_04F24EFC: 1 to 5 bars give 15, 10, 8,
// 5 and 3 frames, off the default).
//
// display.ini's input_delay = no (the default) or TTT2_INPUT_DELAY puts
// another default in its place: with 0 the fighters act on the buttons of
// the frame they are read in. Practice's bars still delay as they say.
// TTT2_TRACE_INPUT_DELAY=1 logs each delay the queues get.

#include "cafe/ppc_ops.h"
#include "host/display_settings.h"

#include <cstdio>
#include <cstdlib>

PPC_FUNC(sub_05C5D7B0_orig);
PPC_FUNC(sub_05C5D7B0) {
    sub_05C5D7B0_orig(ctx, base);
    const std::optional<uint32_t> frames = cafe::host::display::active().input_delay;
    if (!frames) return;
    // (Said once: a mode's start asks again.)
    static bool said = false;
    if (!said) {
        said = true;
        std::fprintf(stderr, "ttt2: input delay: %u frames in place of the game's %u\n", *frames,
                     static_cast<uint32_t>(ctx.r[3]));
    }
    ctx.r[3] = *frames;
}

PPC_FUNC(sub_02EF9010_orig); // the queues' delay (r4: frames)
PPC_FUNC(sub_02EF9010) {
    static const bool trace = std::getenv("TTT2_TRACE_INPUT_DELAY") != nullptr;
    if (trace) std::fprintf(stderr, "ttt2: input delay: the queues wait %u frames\n", static_cast<uint32_t>(ctx.r[4]));
    sub_02EF9010_orig(ctx, base);
}
