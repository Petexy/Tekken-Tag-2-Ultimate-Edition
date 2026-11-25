// The player's name (see player_name.h).
//
// The title asks for the local player's name every frame (sub_021ECCFC):
// online, the network account's; offline, its text common 1599 ("Player",
// "Joueur", ...: sub_04D49F5C with r4 = the language's bank << 24 | 1599,
// through the thunk sub_020044AC). Everything that shows the name or keeps
// it gets it from there: the menus' name objects (sub_05816540, by the
// player's id, then sub_0581677C) and the records filled at start-up
// (sub_02262AE8, then sub_058168E8) copy it with strncpy into 20-byte
// fields, and those fields are copied whole into a mode's records
// (sub_0380470C). So the offline text is answered with game.ini's name, at
// most 16 bytes (host::game::kMaxNameLength), which always leaves those
// fields their terminating zero. The text getter's other callers (the
// tuning data dialog's "Player", sub_025043DC) keep the title's text.

#include "title/player_name.h"

#include "host/game_settings.h"

#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

namespace {

using namespace cafe;

constexpr uint32_t kPlayerText = 1599;            // common 1599 (the bank's number is above bit 24)
constexpr uint32_t kLocalPlayerName = 0x021ECDD4; // the return into sub_021ECCFC, its offline name

// The name as a text of a bank: UTF-8 with a terminating zero, its length
// in characters (big-endian) in the two bytes before it. 0: the title's own.
std::atomic<uint32_t> g_name{0};

} // namespace

namespace cafe::title {

void prepare_player_name() {
    const host::game::Loaded loaded = host::game::load(host::game::file_path());
    for (const std::string& line : loaded.log) std::fprintf(stderr, "ttt2: %s\n", line.c_str());
    const std::string& name = loaded.settings.player_name;
    if (name.empty() || name.size() > host::game::kMaxNameLength) return;
    const uint32_t record = system_alloc(static_cast<uint32_t>(4 + name.size() + 1));
    uint8_t* bytes = guest_pointer(record);
    std::memset(bytes, 0, 4 + name.size() + 1);
    bytes[2] = static_cast<uint8_t>(name.size() >> 8); // (ASCII: one byte a character)
    bytes[3] = static_cast<uint8_t>(name.size());
    std::memcpy(bytes + 4, name.data(), name.size());
    g_name = record + 4;
}

} // namespace cafe::title

// The thunk to the title's texts (sub_04D49F5C: r3 the texts, r4 the bank's
// number << 24 | the text's; -> r3 the text) in the code of sub_021ECCFC.
PPC_FUNC(sub_020044AC_orig);
PPC_FUNC(sub_020044AC) {
    const uint32_t name = g_name.load(std::memory_order_relaxed);
    if (name != 0 && ctx.lr == kLocalPlayerName && (ctx.r[4] & 0x00FFFFFFu) == kPlayerText) {
        ctx.r[3] = name;
        return;
    }
    sub_020044AC_orig(ctx, base);
}
