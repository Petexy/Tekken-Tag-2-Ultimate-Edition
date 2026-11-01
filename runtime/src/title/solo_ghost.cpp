// Solo Ghost Battle (see solo_ghost.h): Ghost Battle one on one.
//
// The Offline menu's rows start their modes from their OnEnter scripts:
// GHOST BATTLE's asks the mode manager for the Offline entry with flags 9
// (ModeManager::Impl::requestChangeMode, sub_0738E098: r4 the mode, 17 the
// Offline entry, r5 its argument), whose bit 8 makes Ghost Battle (kind 12,
// sub_028A28D4) and opens the select screen. The SOLO GHOST BATTLE row is a
// copy of it, so the session is told apart by the row the Offline menu has
// focused at that request (the menus stay made, with their cursors, from
// start-up on): also when the pause menu's CHARACTER SELECT asks for the
// Offline entry again, with the same flags. A request for the main menu
// (16) ends it.

#include "title/solo_ghost.h"

#include "title/archive.h"
#include "title/menudata.h"
#include "title/presentation.h"

#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"
#include "cafe/vfs.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

PPC_FUNC(sub_04545920); // the menu's entity by name (r3 the menus + 4, r4 the name) -> r3

namespace {

using namespace cafe;

constexpr uint32_t kMenuData = 0x4615C394; // the menus' file (menudata.h)
constexpr const char* kArchives[] = {"content/hdd/data100", "content/hdd/data000"}; // the update's copy first

constexpr uint32_t kMatchObject = 0x10872CB8; // *(*(*it + 228) + 228) = the mode manager (sub_06ECB1B0)
constexpr uint32_t kModeKind = 444, kGhostBattle = 12;
constexpr uint32_t kOfflineEntry = 17, kMainMenu = 16, kGhostFlags = 9; // requestChangeMode's modes, GHOST BATTLE's flags

// The menus' entities are found as the menu natives find them: by name from
// *(*0x1084FEBC + 744) + 4, once made (0x1084FEB8). A menu (a container)
// has its children's vector at +160/+164 and its cursor at +172.
constexpr uint32_t kMenusMade = 0x1084FEB8, kMenusHolder = 0x1084FEBC, kMenus = 744;
constexpr uint32_t kChildren = 160, kChildrenEnd = 164, kCursor = 172;

std::atomic<bool> g_chosen{false}; // the session was started from the SOLO GHOST BATTLE row

uint32_t load(const uint8_t* base, uint32_t address) { return ppc::ld32(base, address); }

// Calls guest function `f` with arguments; -> r3. The caller's registers are kept.
uint32_t call(PPCContext& ctx, uint8_t* base, void (*f)(PPCContext&, uint8_t*), std::initializer_list<uint32_t> args) {
    const PPCContext saved = ctx;
    uint32_t r = 3;
    for (uint32_t a : args) ctx.r[r++] = a;
    f(ctx, base);
    const uint32_t result = ctx.r[3];
    ctx = saved;
    return result;
}

uint32_t guest_text(const char* text) {
    const uint32_t at = system_alloc(static_cast<uint32_t>(std::strlen(text)) + 1);
    std::memcpy(guest_pointer(at), text, std::strlen(text) + 1);
    return at;
}

// An entity by its name (a guest string).
uint32_t entity(PPCContext& ctx, uint8_t* base, uint32_t name) {
    if (!load(base, kMenusMade)) return 0;
    const uint32_t holder = load(base, kMenusHolder), menus = holder ? load(base, holder + kMenus) : 0;
    return menus ? call(ctx, base, sub_04545920, {menus + 4, name}) : 0;
}

bool solo_row_focused(PPCContext& ctx, uint8_t* base) {
    static const uint32_t menu_name = guest_text(title::menudata::kOfflineMenu);
    static const uint32_t row_name = guest_text(title::menudata::kSoloGhostRow);
    const uint32_t menu = entity(ctx, base, menu_name), row = menu ? entity(ctx, base, row_name) : 0;
    if (!row) return false;
    const uint32_t begin = load(base, menu + kChildren), end = load(base, menu + kChildrenEnd), cursor = load(base, menu + kCursor);
    return end > begin && cursor < (end - begin) / 4 && load(base, begin + 4 * cursor) == row;
}

bool trace() {
    static const bool on = std::getenv("TTT2_TRACE_SOLO_GHOST") != nullptr;
    return on;
}

} // namespace

namespace cafe::title {

void prepare_solo_ghost_battle() {
    for (const char* archive : kArchives) {
        uint8_t flags[8] = {};
        const auto file = game_file(archive, kMenuData, &flags);
        if (!file) continue;
        const auto changed = menudata::add_solo_ghost_row(*file);
        if (!changed || !vfs::set_archive_entries(archive, {{kMenuData, archive::pack(*changed, kMenuData, flags)}})) {
            std::fprintf(stderr, "ttt2: warning: the Offline menu is not as expected; no SOLO GHOST BATTLE row\n");
        } else if (trace()) {
            std::fprintf(stderr, "ttt2: solo ghost battle: the Offline menu's row added (%s)\n", archive);
        }
        return;
    }
    std::fprintf(stderr, "ttt2: warning: the game has no menus' file; no SOLO GHOST BATTLE row\n");
}

bool solo_ghost_battle() {
    if (!g_chosen) return false;
    const uint8_t* base = guest_base();
    const uint32_t object = load(base, kMatchObject);
    const uint32_t match = object ? load(base, object + 228) : 0;
    const uint32_t mode = match ? load(base, match + 228) : 0;
    return mode && load(base, mode + kModeKind) == kGhostBattle;
}

} // namespace cafe::title

// The mode manager's requests: the Offline entry's (a row of the Offline
// menu, or the pause menu's CHARACTER SELECT) is a Solo Ghost Battle when
// Ghost Battle's flags come with the SOLO GHOST BATTLE row focused.
PPC_FUNC(sub_0738E098_orig);
PPC_FUNC(sub_0738E098) {
    if (ctx.r[4] == kOfflineEntry || ctx.r[4] == kMainMenu) {
        const bool chosen = ctx.r[4] == kOfflineEntry && ctx.r[5] == kGhostFlags && solo_row_focused(ctx, base);
        if (trace() && chosen != g_chosen) std::fprintf(stderr, "ttt2: solo ghost battle: %s\n", chosen ? "on" : "off");
        g_chosen = chosen;
    }
    sub_0738E098_orig(ctx, base);
}

// The select screen asks whether the mode is Mushroom Battle (sub_02C23554,
// through to sub_06ECBD98) in its Tag/Solo popup (sub_033E3DC8: its cursor
// gets SOLO, sub_033E1010(cursor, 2), and the popup is done before it shows)
// and for its help bar (no PRESET TAG). Solo Ghost Battle answers yes there.
constexpr uint32_t kPopupLeft = 0x033E3EA4, kPopupRight = 0x033E3EC8, kHelpBar = 0x033E5E48;
PPC_FUNC(sub_02C23554_orig);
PPC_FUNC(sub_02C23554) {
    if ((ctx.lr == kPopupLeft || ctx.lr == kPopupRight || ctx.lr == kHelpBar) && cafe::title::solo_ghost_battle()) {
        ctx.r[3] = 1;
        return;
    }
    sub_02C23554_orig(ctx, base);
}

// Whether a ghost's partner (fighter r3) is available (sub_06EE94D0): when
// it is not, its card shows the ghost's fighter alone (sub_028A2B8C, through
// the thunk 028AA478) and the fight puts the ghost's own fighter in the
// partner's place (sub_06EEF064: the partner's block, then the side's second
// member and record). The strong ghosts' draw (sub_028A2DA8) asks too and
// keeps its answer.
constexpr uint32_t kGhostCardPartner = 0x028A2BE0, kGhostFightPartner = 0x06EEFA9C;
PPC_FUNC(sub_06EE94D0_orig);
PPC_FUNC(sub_06EE94D0) {
    if ((ctx.lr == kGhostCardPartner || ctx.lr == kGhostFightPartner) && cafe::title::solo_ghost_battle()) {
        ctx.r[3] = 0;
        return;
    }
    sub_06EE94D0_orig(ctx, base);
}

// The title's texts (sub_04D49F5C: r3 the texts, r4 the bank's number << 24
// | the text's; -> r3 the text, UTF-8): the fight's corner (sub_033DB714 and
// sub_033DAEAC, every frame) names the mode by common 144, GHOST BATTLE.
constexpr uint32_t kModeName = 0x03000090, kCornerName[] = {0x033DBFE4, 0x033DAF74};
PPC_FUNC(sub_04D49F5C_orig);
PPC_FUNC(sub_04D49F5C) {
    if (ctx.r[4] == kModeName && (ctx.lr == kCornerName[0] || ctx.lr == kCornerName[1]) &&
        cafe::title::solo_ghost_battle()) {
        // as a text of a bank: its length in characters before it
        static const uint32_t name = [] {
            constexpr char kName[] = "SOLO GHOST BATTLE";
            const uint32_t at = system_alloc(4 + sizeof kName);
            std::memset(guest_pointer(at), 0, 4);
            guest_pointer(at)[3] = static_cast<uint8_t>(sizeof kName - 1);
            std::memcpy(guest_pointer(at + 4), kName, sizeof kName);
            return at + 4;
        }();
        ctx.r[3] = name;
        return;
    }
    sub_04D49F5C_orig(ctx, base);
}
