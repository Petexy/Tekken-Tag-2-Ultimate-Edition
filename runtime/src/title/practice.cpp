// Practice: 3 and - (Select) pressed together put both fighters back where
// the stage put them, as Tekken 8's position reset does. The frame data
// panels, hitboxes and camera from above (title/framedata.cpp) follow the
// fighters' frames, and the pause menu's ULTIMATE SETTINGS row, in the
// place of TOUCH SELECT, sets them up (see the end of this file).
//
// The title starts a Practice round (mode kinds 4 and 5) with its situation
// set-up sub_039C2DB0 for kind 15: its Practice positioner (sub_04F21428)
// places the fighters as the Position Settings say (by default 1 m either
// side of the stage's centre; REVERSE swaps them) and every fighter starts
// over, standing. The reset runs the same set-up from the battle's state
// (GameMode::Impl::state_game_battle, sub_0726DF8C) at the start of a frame,
// with the camera calls of the title's own Practice restart (sub_04A28490):
// the round's start camera, and the 2P one when REVERSE is on.
//
// 3 is the title's own button, after the Controller Setup: the fighter's
// buttons at +2032 (1 to 4 = 0x200 to 0x1000), read from the fighter the
// GamePad drives (its raw buttons at +2052; the training dummy's stay 0).
// The input layer holds - back a moment so that it can join 3
// (cafe::os::arm_select_chord), armed only on the fighters' frames, which
// stop while the pause menu is open; a - that is the chord's never reaches
// the game.

#include "title/framedata.h"
#include "title/gauge.h"

#include "cafe/input.h"
#include "title/practice_checkpoint.h"
#include "cafe/ppc_ops.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <array>
#include <vector>
#include <cstring>
#include <atomic>
#include <mutex>
#include <cstdlib>
#include <span>
#include <string>
#include <string_view>

PPC_FUNC(sub_04F9FB6C); // a select value's cursor set (r3 the cursor, r4 the value's name)
PPC_FUNC(sub_04F9FB8C_orig); // a select value's cursor (r3 the value's name) -> r3 (as it is: see the hook)
PPC_FUNC(sub_04545920); // the menu's entity by name (r3 the menus + 4, r4 the name) -> r3
PPC_FUNC(sub_045590E0); // a select value entry's text (r3 the entry) -> r3

PPC_FUNC(sub_03A45CA4);
PPC_FUNC(sub_03A472A4);

namespace cafe::title::checkpoint {
namespace {
std::atomic<Request> pending{Request::None};
std::atomic<bool> notice_ready{false};
std::mutex notice_mutex;
std::string notice;
}
bool enabled() {
    static const bool on=std::getenv("TTT2_PRACTICE_CHECKPOINT")!=nullptr;
    return on;
}
void request(Request command) { if(enabled()) pending.store(command); }
void status(const char* text) {
    { std::lock_guard lock(notice_mutex); notice=text; }
    notice_ready.store(true);
    std::fprintf(stderr,"checkpoint: %s\n",text);
}
bool take_notice(std::string& text) {
    if(!notice_ready.exchange(false)) return false;
    std::lock_guard lock(notice_mutex); text=notice; return true;
}
} // namespace cafe::title::checkpoint

namespace {

using namespace cafe;

constexpr uint32_t kMatchObject = 0x10872CB8; // *(*(*it + 228) + 228) = the mode manager (sub_06ECB1B0)
constexpr uint32_t kModeKind = 444;
constexpr uint32_t kPracticeKinds[] = {4, 5};                       // as sub_06ECB3CC
constexpr uint32_t kPracticeSettings = 0x108D1C60, kReverse = 100; // sub_04F1BD58; 1: the player on the right
constexpr uint32_t kSidePlayers = 0x1087FB60;                     // per side: its first member (sub_05C5EF14)
constexpr uint32_t kPlayerActive = 7808, kPlayerPartner = 172;
constexpr uint32_t kPlayerButtons = 2032, kButton3 = 0x800, kPlayerPad = 2052;
constexpr uint32_t kPracticeStart = 15; // the situation of a Practice round's start
constexpr uint32_t k2PCamera = 2;

uint32_t load(uint8_t* base, uint32_t address) { return ppc::ld32(base, address); }

bool practice(uint8_t* base) {
    const uint32_t object = load(base, kMatchObject);
    const uint32_t match = object ? load(base, object + 228) : 0;
    const uint32_t mode = match ? load(base, match + 228) : 0;
    if (!mode) return false;
    const uint32_t kind = load(base, mode + kModeKind);
    for (uint32_t k : kPracticeKinds) {
        if (kind == k) return true;
    }
    return false;
}

// The fighter a side has in play (sub_05C5EF14).
uint32_t active_fighter(uint8_t* base, uint32_t side) {
    const uint32_t first = load(base, kSidePlayers + 4 * side);
    if (!first || load(base, first + kPlayerActive)) return first;
    return load(base, first + kPlayerPartner);
}

bool three_held(uint8_t* base) {
    for (uint32_t side = 0; side < 2; ++side) {
        const uint32_t fighter = active_fighter(base, side);
        if (fighter && load(base, fighter + kPlayerPad) && (load(base, fighter + kPlayerButtons) & kButton3)) {
            return true;
        }
    }
    return false;
}

// Calls guest function `f` with arguments (and f1); -> r3. The caller's registers are kept.
uint32_t call(PPCContext& ctx, uint8_t* base, void (*f)(PPCContext&, uint8_t*), std::initializer_list<uint32_t> args,
              double f1 = 0.0) {
    const PPCContext saved = ctx;
    uint32_t r = 3;
    for (uint32_t a : args) ctx.r[r++] = a;
    ctx.f[1] = {f1, f1};
    f(ctx, base);
    const uint32_t result = ctx.r[3];
    ctx = saved;
    return result;
}

// ------------------------------------------------------------ menu texts
// Texts of the loaded banks in guest memory (a record: the key padded to
// four, two bytes, the length in characters, the text padded to four with
// at least two zero bytes), rewritten for a while and put back after: the
// ULTIMATE SETTINGS row in place of TOUCH SELECT (menu texts, which other menus
// may show too) while Practice runs, and the ULTIMATE SETTINGS submenu's texts in
// the HUD Information submenu it borrows while it does. Found once, by a
// scan of MEM2 for the menu bank's key, then near the practice bank's.
struct TextPatch {
    const char* key;
    const char* text;
};

struct TextRecord {
    std::string key;
    uint32_t at = 0;               // the record's key
    std::vector<uint8_t> original; // its header and text space, as loaded
    bool patched = false;
};

std::vector<TextRecord> g_texts;
double g_last_scan = -10;
constexpr uint32_t kScanStart = 0x10000000, kScanEnd = 0x50000000, kScanStep = 1u << 20;
constexpr uint32_t kNear = 1u << 20; // a bank's keys lie within this of each other

double seconds() { return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

// `key` as a record's key at `p`: after the previous record's padding,
// with its own.
bool key_at(const uint8_t* p, std::string_view key) {
    return p[-1] == 0 && std::memcmp(p, key.data(), key.size()) == 0 && p[key.size()] == 0;
}

void add_record(uint8_t* base, const uint8_t* p, std::string_view key) {
    TextRecord t;
    t.key = key;
    t.at = static_cast<uint32_t>(p - base);
    const uint32_t text = t.at + ((static_cast<uint32_t>(key.size()) + 1 + 3) & ~3u) + 4;
    const size_t bytes = std::strlen(reinterpret_cast<const char*>(base + text));
    t.original.assign(base + text - 4, base + text + ((bytes + 2 + 3) & ~size_t{3}));
    g_texts.push_back(std::move(t));
}

// Calls `found(p)` for each place of `pattern` in committed guest memory
// [begin, end).
template <typename Found>
void scan(uint8_t* base, uint32_t begin, uint32_t end, std::string_view pattern, Found&& found) {
    for (uint32_t chunk = begin; chunk < end; chunk += kScanStep) {
        const uint32_t size = std::min(kScanStep, end - chunk);
        if (!guest_memory_committed(chunk, size)) continue;
        const uint8_t* from = base + chunk;
        const bool across = chunk + size < end && guest_memory_committed(chunk + size, 64);
        const size_t length = size + (across ? 64 : 0); // across the chunk's end
        // (string_view's find, as memmem is not in Windows' C library)
        const std::string_view text(reinterpret_cast<const char*>(from), length);
        for (size_t at = text.find(pattern); at != std::string_view::npos; at = text.find(pattern, at + 1)) {
            if (from + at > base + kScanStart) found(from + at);
        }
    }
}

// A bank's texts to change, found near its anchor's key.
struct TextGroup {
    const char* anchor;
    std::span<const TextPatch> patches;
};

void find_texts(uint8_t* base, std::initializer_list<TextGroup> groups) {
    g_texts.clear();
    for (const TextGroup& group : groups) {
        std::vector<uint32_t> banks;
        scan(base, kScanStart, kScanEnd, group.anchor, [&](const uint8_t* p) {
            if (key_at(p, group.anchor)) banks.push_back(static_cast<uint32_t>(p - base));
        });
        for (const TextPatch& t : group.patches) {
            for (const uint32_t bank : banks) {
                const uint32_t from = bank - std::min(bank - kScanStart, kNear), to = std::min(kScanEnd, bank + kNear);
                scan(base, from, to, t.key, [&](const uint8_t* p) {
                    if (key_at(p, t.key)) add_record(base, p, t.key);
                });
            }
        }
    }
}

// Writes the record's text (ASCII) if it fits its space; null: as loaded.
void write_text(uint8_t* base, TextRecord& t, const char* text) {
    uint8_t* header = base + t.at + ((static_cast<uint32_t>(t.key.size()) + 1 + 3) & ~3u);
    if (!text) {
        std::memcpy(header, t.original.data(), t.original.size());
        t.patched = false;
        return;
    }
    const size_t space = t.original.size() - 4, bytes = std::strlen(text);
    if (bytes + 2 > space) return;
    header[2] = static_cast<uint8_t>(bytes >> 8);
    header[3] = static_cast<uint8_t>(bytes);
    std::memset(header + 4, 0, space);
    std::memcpy(header + 4, text, bytes);
    t.patched = true;
}

// Changes the group's texts, or puts them back.
void patch_texts(uint8_t* base, std::span<const TextPatch> patches, bool on) {
    for (const TextPatch& t : patches) {
        for (TextRecord& r : g_texts) {
            if (r.key != t.key || !key_at(base + r.at, r.key) || r.patched == on) continue;
            write_text(base, r, on ? t.text : nullptr);
        }
    }
}

// The ULTIMATE SETTINGS row, in Practice (its label, longer than the
// text's space, is set on the row itself as the pause menu comes: see
// MenuEntitySetText below).
constexpr TextPatch kRowTexts[] = {
    {"Manu_1668", "ULTIMATE"},
    {"Manu_1669", "Frame data, hitboxes and camera settings."},
};
constexpr const char* kRowLabel = "ULTIMATE SETTINGS";

// The ULTIMATE SETTINGS submenu: HUD Information's frame (FramePracticeMenu01-09-04)
// with its header, its first rows' labels and their descriptions (the
// focused row's, and the value's, one for either value; each within the
// space of the text it replaces).
constexpr TextPatch kSubmenuTexts[] = {
    {"practice_1039", "ULTIMATE SETTINGS"},
    {"practice_669", "FRAME DATA"},
    {"practice_824", "Show or hide the frame data panels."},
    {"practice_825", "Show the frame data."},
    {"practice_826", "Show the frame data."},
    {"practice_670", "1P PANEL"},
    {"practice_827", "Show or hide the 1P panel."},
    {"practice_828", "Show the 1P panel."},
    {"practice_829", "Show the 1P panel."},
    {"practice_674", "2P PANEL"},
    {"practice_830", "Show or hide the 2P panel."},
    {"practice_831", "Show the 2P panel."},
    {"practice_832", "Show the 2P panel."},
    {"practice_675", "ADV. COLORS"},
    {"practice_833", "Color the fighters by frame advantage."},
    {"practice_834", "Blue: plus, red: minus"},
    {"practice_835", "Blue: plus, red: minus"},
    {"practice_676", "HITBOXES"},
    {"practice_836", "Show hitboxes and hurtboxes in 3D."},
    {"practice_837", "Red: attacks and hits"},
    {"practice_838", "Red: attacks and hits"},
    {"practice_677", "TOP CAMERA"},
    {"practice_839", "Show the fight from above too."},
    {"practice_840", "Window from above"},
    {"practice_841", "Window from above"},
    {"practice_678", "SLOW MOTION"},
    {"practice_842", "Slow the fighters down to learn moves."},
    {"practice_843", "Half or quarter speed"},
    {"practice_844", "Half or quarter speed"},
};

// HUD Information's rows show the practice settings' HUD words (1 on, from
// +48 a row) through their select values (SelectValuePracticeMenu01-09-04-NN,
// the names at 0x1031C9C8 on, 0x24 apart; cursor 0 ON, 1 OFF), which the
// title sets from the settings as the pause menu opens (MenuSelectValue-
// SetCursor through sub_04F9FB6C: r3 the cursor, r4 the name) and reads
// back (sub_04F9FB8C: r3 the name, -> the cursor). While the frame is
// ULTIMATE SETTINGS they show its settings; the HUD words are kept too, in case
// the title reads the values back meanwhile.
constexpr uint32_t kHudWords = 48, kHudValueNames = 0x1031C9C8, kHudValueNameStride = 0x24;
constexpr title::framedata::Setting kSubmenuRows[] = {title::framedata::kPanels, title::framedata::kPanel1P,
                                                      title::framedata::kPanel2P, title::framedata::kAdvantageColours,
                                                      title::framedata::kHitboxes, title::framedata::kTopCamera,
                                                      title::framedata::kSlowMotion};
constexpr uint32_t kHudRows = 8;

bool g_submenu = false;   // HUD Information's frame shows ULTIMATE SETTINGS
bool g_submenu_in = false; // and has come up, with ULTIMATE SETTINGS' values
bool g_focus_row = false; // the pause menu comes back: focus the ULTIMATE SETTINGS row
bool g_rows_hidden = false; // HUD Information's rows ULTIMATE SETTINGS leaves out are hidden
uint32_t g_hud_words[std::size(kSubmenuRows)], g_hud_cursors[std::size(kSubmenuRows)];

// A select value object: +360 its cursor, +368 its default cursor (as
// MenuSelectSetDefaultCursor sets them). The menus' entities are found as
// the menu natives find them: by name from *(*0x1084FEBC + 744) + 4, once
// made (0x1084FEB8).
constexpr uint32_t kMenusMade = 0x1084FEB8, kMenusHolder = 0x1084FEBC, kMenus = 744, kValueDefault = 368;
constexpr uint32_t kFrameDataDefaults[] = {0, 0, 0, 1, 1, 1, 1}; // the settings to begin with: the panels on (slow motion: its own entries)

uint32_t select_value(PPCContext& ctx, uint8_t* base, uint32_t name) {
    if (!load(base, kMenusMade)) return 0;
    const uint32_t holder = load(base, kMenusHolder), menus = holder ? load(base, holder + kMenus) : 0;
    return menus ? call(ctx, base, sub_04545920, {menus + 4, name}) : 0;
}

void update_texts(uint8_t* base, bool in_practice) {
    const bool loaded = std::any_of(g_texts.begin(), g_texts.end(), [&](const TextRecord& r) { return key_at(base + r.at, r.key); });
    if (in_practice && !loaded && seconds() - g_last_scan > 5) {
        g_last_scan = seconds();
        const double begin = seconds();
        find_texts(base, {{"Manu_1668", kRowTexts}, {"practice_1039", kSubmenuTexts}});
        if (std::getenv("TTT2_TRACE_PRACTICE")) {
            std::fprintf(stderr, "ttt2: practice: %zu menu texts found in %.0f ms\n", g_texts.size(), (seconds() - begin) * 1000);
        }
    }
    patch_texts(base, kRowTexts, in_practice);
}

uint32_t hud_word(size_t row) { return kPracticeSettings + kHudWords + 4 * static_cast<uint32_t>(row); }
uint32_t hud_value(size_t row) { return kHudValueNames + kHudValueNameStride * static_cast<uint32_t>(row); }

// ULTIMATE SETTINGS' settings into the rows' values (as the frame comes, and
// again once it is up: the title may fill them from the HUD words in
// between), and back out of them while it is up.
// A row's cursor for its setting: ON 0, OFF 1; SLOW MOTION's its value
// (OFF, 1/2, 1/4).
uint32_t setting_cursor(size_t row) {
    const uint32_t v = title::framedata::setting(kSubmenuRows[row]);
    return kSubmenuRows[row] == title::framedata::kSlowMotion ? v : v ? 0u : 1u;
}

void show_settings(PPCContext& ctx, uint8_t* base) {
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) call(ctx, base, sub_04F9FB6C, {setting_cursor(i), hud_value(i)});
}

void take_settings(PPCContext& ctx, uint8_t* base) {
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        const uint32_t cursor = call(ctx, base, sub_04F9FB8C_orig, {hud_value(i)});
        if (kSubmenuRows[i] == title::framedata::kSlowMotion) {
            if (cursor <= 2) title::framedata::set_setting(kSubmenuRows[i], cursor);
        } else if (cursor <= 1) {
            title::framedata::set_setting(kSubmenuRows[i], cursor == 0);
        }
    }
}

// The rows' looks: a select value's entries (40 bytes each, from the
// pointer at +348; +36 the id of the entry's text, which holds its colour:
// green for the row's default, yellow otherwise; "styles" here). While a row is
// ULTIMATE SETTINGS', its default (+368) and its entries' styles are those of a
// row whose default is that ULTIMATE SETTINGS row's (on, or off: COMMAND HISTORY's);
// HUD Information gets its own back once it can (the pause menu closed from
// ULTIMATE SETTINGS: when it next shows).
constexpr uint32_t kValueEntries = 348, kEntrySize = 40, kEntryStyle = 36;

struct Look {
    uint32_t default_cursor = 0, styles[2] = {};
    bool changed = false;
};
Look g_looks[std::size(kSubmenuRows)];

void entry_styles(uint8_t* base, uint32_t value, uint32_t styles[2], bool write) {
    const uint32_t entries = load(base, value + kValueEntries);
    for (uint32_t e = 0; e < 2; ++e) {
        const uint32_t at = entries + e * kEntrySize + kEntryStyle;
        if (write) ppc::st32(base, at, styles[e]);
        else styles[e] = load(base, at);
    }
}

// SLOW MOTION has three values where its HUD Information row (ATTACK
// PROPERTIES) has two: while the row is ULTIMATE SETTINGS', its select
// value's entries (a vector: begin, end and capacity at +348, +352, +356;
// 40 bytes each) are three of the port's, and its own come back before
// their looks do (the title frees them). An entry's text is a text of the
// menu's (+32 its kind, +36 its id: the value as drawn, its arrows and its
// colour, green at the row's default, yellow otherwise, in the text's
// control codes), or with those 0 its own string (inline at +4 up to 15
// bytes, else at the pointer at +20; its length at +24, room at +28), read
// through sub_045590E0. OFF is the row's own green OFF (its default, once
// it has the looks of a row whose default is OFF); 1/2 and 1/4 are its
// yellow ON's text with the word changed.
constexpr uint32_t kValueEntriesEnd = 352, kValueEntriesCapacity = 356;
constexpr uint32_t kEntryHeapText = 20, kEntryTextLength = 24, kEntryTextRoom = 28, kEntryTextKind = 32, kEntryTextId = 36;
constexpr uint32_t kSlowTextRoom = 128;
constexpr const char* kSlowSpeeds[] = {" 1/2 ", " 1/4 "};

struct OwnEntries {
    bool swapped = false;
    uint32_t value = 0, begin = 0, end = 0, capacity = 0, default_cursor = 0;
} g_own_entries;

void slow_motion_entries(PPCContext& ctx, uint8_t* base, size_t row) {
    if (g_own_entries.swapped) return;
    const uint32_t value = select_value(ctx, base, hud_value(row));
    if (!value) return;
    const uint32_t begin = load(base, value + kValueEntries), end = load(base, value + kValueEntriesEnd);
    if (end != begin + 2 * kEntrySize) return;
    // Its yellow ON, as text.
    const uint32_t on = call(ctx, base, sub_045590E0, {begin});
    if (!on || !guest_memory_committed(on, kSlowTextRoom)) return;
    const std::string on_text(reinterpret_cast<const char*>(base + on), strnlen(reinterpret_cast<const char*>(base + on), kSlowTextRoom));
    const size_t word = on_text.find(" ON ");
    if (word == std::string::npos) return;
    static const uint32_t entries = system_alloc(3 * kEntrySize);
    static const uint32_t texts = system_alloc(2 * kSlowTextRoom);
    std::memcpy(guest_pointer(entries), guest_pointer(begin + kEntrySize), kEntrySize); // OFF
    for (uint32_t e = 0; e < 2; ++e) {
        const uint32_t at = entries + (e + 1) * kEntrySize, text = texts + e * kSlowTextRoom;
        const std::string t = on_text.substr(0, word) + kSlowSpeeds[e] + on_text.substr(word + 4);
        if (t.size() + 1 > kSlowTextRoom) return;
        std::memcpy(guest_pointer(at), guest_pointer(begin), kEntrySize);
        std::memcpy(guest_pointer(text), t.c_str(), t.size() + 1);
        ppc::st32(base, at + kEntryHeapText, text);
        ppc::st32(base, at + kEntryTextLength, static_cast<uint32_t>(t.size()));
        ppc::st32(base, at + kEntryTextRoom, kSlowTextRoom - 1);
        ppc::st32(base, at + kEntryTextKind, 0);
        ppc::st32(base, at + kEntryTextId, 0);
    }
    g_own_entries = {true, value, begin, end, load(base, value + kValueEntriesCapacity), load(base, value + kValueDefault)};
    const uint32_t entries_end = entries + 3 * kEntrySize;
    ppc::st32(base, value + kValueEntries, entries);
    ppc::st32(base, value + kValueEntriesEnd, entries_end);
    ppc::st32(base, value + kValueEntriesCapacity, entries_end);
    ppc::st32(base, value + kValueDefault, 0);
}

void own_entries_back(PPCContext& ctx, uint8_t* base, size_t row) {
    if (!g_own_entries.swapped) return;
    const OwnEntries& o = g_own_entries;
    g_own_entries.swapped = false;
    if (select_value(ctx, base, hud_value(row)) != o.value) return; // (the menu gone: nothing to give back to)
    ppc::st32(base, o.value + kValueEntries, o.begin);
    ppc::st32(base, o.value + kValueEntriesEnd, o.end);
    ppc::st32(base, o.value + kValueEntriesCapacity, o.capacity);
    ppc::st32(base, o.value + kValueDefault, o.default_cursor);
}

void frame_data_looks(PPCContext& ctx, uint8_t* base) {
    uint32_t values[std::size(kSubmenuRows)] = {}, styles[2][2] = {}; // by default cursor
    bool have[2] = {};
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        values[i] = select_value(ctx, base, hud_value(i));
        Look& look = g_looks[i];
        if (!values[i]) continue;
        if (!look.changed) {
            look.default_cursor = load(base, values[i] + kValueDefault);
            entry_styles(base, values[i], look.styles, false);
        }
        if (look.default_cursor <= 1 && !have[look.default_cursor]) {
            have[look.default_cursor] = true;
            styles[look.default_cursor][0] = look.styles[0], styles[look.default_cursor][1] = look.styles[1];
        }
    }
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        Look& look = g_looks[i];
        const uint32_t wanted = kFrameDataDefaults[i];
        if (!values[i] || look.changed || look.default_cursor == wanted || !have[wanted]) continue;
        look.changed = true;
        ppc::st32(base, values[i] + kValueDefault, wanted);
        entry_styles(base, values[i], styles[wanted], true);
    }
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        if (kSubmenuRows[i] == title::framedata::kSlowMotion) slow_motion_entries(ctx, base, i);
    }
}

void hud_looks(PPCContext& ctx, uint8_t* base) {
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        if (kSubmenuRows[i] == title::framedata::kSlowMotion) own_entries_back(ctx, base, i);
    }
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        Look& look = g_looks[i];
        if (!look.changed) continue;
        const uint32_t value = select_value(ctx, base, hud_value(i));
        if (!value) continue;
        ppc::st32(base, value + kValueDefault, look.default_cursor);
        entry_styles(base, value, look.styles, true);
        look.changed = false;
    }
}

void command_history_looks(PPCContext& ctx, uint8_t* base) {
    const uint32_t history = select_value(ctx, base, hud_value(0)), gauge = select_value(ctx, base, hud_value(1));
    if (!history || !gauge || load(base, gauge + kValueDefault) != 0) return;
    uint32_t styles[2];
    entry_styles(base, gauge, styles, false);
    ppc::st32(base, history + kValueDefault, 0);
    entry_styles(base, history, styles, true);
}

// The ULTIMATE SETTINGS submenu opens: HUD Information's texts and values become
// its own; and closes, giving them back (its settings taken while it was
// up: a pause menu closed from it is gone by now).
void open_submenu(PPCContext& ctx, uint8_t* base) {
    g_submenu = true;
    g_submenu_in = false;
    patch_texts(base, kSubmenuTexts, true);
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        g_hud_words[i] = load(base, hud_word(i));
        g_hud_cursors[i] = call(ctx, base, sub_04F9FB8C_orig, {hud_value(i)});
    }
    show_settings(ctx, base);
}

void close_submenu(PPCContext& ctx, uint8_t* base) {
    if (!g_submenu) return;
    hud_looks(ctx, base);
    g_submenu = g_submenu_in = false;
    for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
        call(ctx, base, sub_04F9FB6C, {g_hud_cursors[i], hud_value(i)});
        ppc::st32(base, hud_word(i), g_hud_words[i]);
    }
    patch_texts(base, kSubmenuTexts, false);
}

// Names the menu's natives take (C strings in guest memory).
struct MenuNames {
    uint32_t hud_frame, menu_frame, row, row_label, hud_rows[kHudRows][2]; // a row's item and its description
};
const MenuNames& names() {
    static const MenuNames n = [] {
        MenuNames m{};
        const auto put = [](const char* text) {
            const uint32_t at = system_alloc(static_cast<uint32_t>(std::strlen(text)) + 1);
            std::memcpy(guest_pointer(at), text, std::strlen(text) + 1);
            return at;
        };
        m.hud_frame = put("FramePracticeMenu01-09-04");
        m.menu_frame = put("FramePracticeMenu01");
        m.row = put("MenuItemPracticeMenu01-13"); // TOUCH SELECT's
        m.row_label = put(kRowLabel);
        for (uint32_t i = 0; i < kHudRows; ++i) {
            char name[40];
            std::snprintf(name, sizeof(name), "MenuItemPracticeMenu01-09-04-%02u", i + 1);
            m.hud_rows[i][0] = put(name);
            std::snprintf(name, sizeof(name), "StaticPracticeDesc01-09-04-%02u", i + 1);
            m.hud_rows[i][1] = put(name);
        }
        return m;
    }();
    return n;
}

// ------------------------------------------------------------ Easy Input and the added fighters
// The Easy Input screen keeps each fighter's four GamePad move slots in a
// table of 59 (0x108638F8, read through sub_02774188, written through
// sub_027741EC); both stop the title on a larger select id, an added
// fighter's. Those get slots of their own here, empty (0xFF), not saved.
constexpr uint32_t kEasyInputFighters = 59, kAddedSlots = 256;

uint32_t added_slots(uint32_t id) {
    static const uint32_t table = [] {
        const uint32_t t = system_alloc(4 * kAddedSlots);
        std::memset(guest_pointer(t), 0xFF, 4 * kAddedSlots);
        return t;
    }();
    return table + 4 * ((id - kEasyInputFighters) % kAddedSlots);
}

namespace checkpoint=cafe::title::checkpoint;
checkpoint::Slot checkpoint_slot;
uint64_t checkpoint_generation=0;

checkpoint::Identity checkpoint_identity(uint8_t* base) {
    checkpoint::Identity id{}; id.generation=checkpoint_generation;
    const uint32_t object=load(base,kMatchObject);
    const uint32_t match=object ? load(base,object+228) : 0;
    id.mode=match ? load(base,match+228) : 0;
    id.kind=id.mode ? load(base,id.mode+kModeKind) : 0;
    for(uint32_t i=0;i<12;++i) {
        const uint32_t p=load(base,kSidePlayers+4*i);
        if(!p || !guest_memory_committed(p,0x2960)) { id.mode=0;return id; }
        const uint32_t animator=load(base,p+7944);
        if(!animator || !guest_memory_committed(animator,20)) { id.mode=0;return id; }
        id.objects[i]={p,load(base,p+84),load(base,p+80),load(base,p+88),
                       load(base,p+172),animator,load(base,animator+8)};
        if(i<4) id.floors[i]=load(base,p+72);
    }
    return id;
}

// Executes only on the fighter simulation thread, never in the SDL input thread.
void process_checkpoint(PPCContext& ctx,uint8_t* base) {
    if(!checkpoint::enabled()) return;
    const auto command=checkpoint::pending.exchange(checkpoint::Request::None);
    if(!practice(base)) {
        checkpoint_slot.clear();
        if(command!=checkpoint::Request::None) checkpoint::status("Checkpoints are available in Practice only");
        return;
    }
    if(command==checkpoint::Request::None) return;
    const auto id=checkpoint_identity(base);
    if(!id.supported()) {
        checkpoint::status("Prototype supports native roster slots only");
        return;
    }
    if(!guest_memory_committed(checkpoint::kScratchBegin,checkpoint::kScratchBytes)) {
        checkpoint::status("Checkpoint recording buffer unavailable");return;
    }
    std::span<uint8_t> scratch(base+checkpoint::kScratchBegin,checkpoint::kScratchBytes);
    if(command==checkpoint::Request::Save) {
        std::vector<uint8_t> before(12*0x2960);
        for(size_t i=0;i<12;++i) std::memcpy(before.data()+i*0x2960,base+id.objects[i].address,0x2960);
        bool changed=false;
        checkpoint::preserve_scratch(scratch,[&] {
            call(ctx,base,sub_03A45CA4,{});
            for(size_t i=0;i<12;++i) changed |= std::memcmp(before.data()+i*0x2960,base+id.objects[i].address,0x2960)!=0;
            if(!changed) checkpoint_slot.save(id,scratch);
        });
        if(changed) { checkpoint_slot.clear();checkpoint::status("Capture rejected: combat objects changed during copying"); }
        else checkpoint::status("Checkpoint saved - F8 to load");
    } else {
        if(!checkpoint_slot.matches(id)) {
            checkpoint::status("No matching checkpoint - F5 to save again");return;
        }
        checkpoint::preserve_scratch(scratch,[&] {
            std::copy(checkpoint_slot.bytes().begin(),checkpoint_slot.bytes().end(),scratch.begin());
            call(ctx,base,sub_03A472A4,{});
        });
        title::framedata::reset(); // discard HUD history from the timeline we just left
        checkpoint::status("Checkpoint loaded - F5 to replace, F8 to repeat");
    }
}

// Investigation-only observer for the title's OWN combat copy/restore pair.
// It reads combat state and logs only when TTT2_CHECKPOINT_OBSERVE is set.
constexpr uint32_t kCombatObjects = 12, kCombatObjectBytes = 0x2960;
bool checkpoint_observing() {
    static const bool enabled = std::getenv("TTT2_CHECKPOINT_OBSERVE") != nullptr;
    return enabled;
}
void observe_combat(const char* event, uint8_t* base) {
    if (!checkpoint_observing() || !practice(base)) return;
    for (uint32_t i = 0; i < kCombatObjects; ++i) {
        const uint32_t p = load(base, kSidePlayers + 4*i);
        if (!p || !guest_memory_committed(p, kCombatObjectBytes)) {
            std::fprintf(stderr,"checkpoint-observe event=%s object=%u unavailable=%08X\n",event,i,p);
            continue;
        }
        const uint32_t move = load(base,p+280), animator=load(base,p+7944);
        uint32_t motion=0;
        if (animator && guest_memory_committed(animator,20)) motion=load(base,animator+12);
        std::fprintf(stderr,
            "checkpoint-observe event=%s object=%u player=%08X id=%u row=%u record=%08X partner=%08X move=%08X frame=%u active=%u owner=%u assist=%u animator=%08X motion=%08X pos=%08X/%08X/%08X floor=%08X damage=%u/%u combo=%u\n",
            event,i,p,load(base,p+84),load(base,p+80),load(base,p+88),load(base,p+172),
            move,load(base,p+212),load(base,p+7808),load(base,p+7808),load(base,p+7816),
            animator,motion,load(base,p),load(base,p+4),load(base,p+8),load(base,p+72),
            load(base,p+1176),load(base,p+1180),load(base,p+0x1cc));
    }
}


} // namespace

PPC_FUNC(sub_039C2DB0_orig);
PPC_FUNC(sub_039C2DB0) { // Any native situation reset starts a new checkpoint generation.
    ++checkpoint_generation;
    const bool had_slot=checkpoint_slot.valid();checkpoint_slot.clear();
    if(had_slot && checkpoint::enabled()) checkpoint::status("Checkpoint cleared by practice reset");
    sub_039C2DB0_orig(ctx,base);
}
PPC_FUNC(sub_05FBD4C8); // -> the camera
PPC_FUNC(sub_05FBB480); // the camera (r3) as at a round's start (r4 = 0)
PPC_FUNC(sub_05FBC0A4); // the camera (r3) of a side (r4 = 2: 2P; f1 = 1, r5 = 1)

// The fighters' frame (not while the pause menu is open): the chord can
// happen, and the frame data panels follow the fighters.
PPC_FUNC(sub_03ADB118_orig);
bool g_fighters_ran = false; // in the battle frame that ran last

PPC_FUNC(sub_03ADB118) {
    const bool in_practice = practice(base);
    g_fighters_ran = true;
    if (in_practice) os::arm_select_chord(three_held(base));
    process_checkpoint(ctx,base);
    if (checkpoint_observing() && practice(base)) {
        static uint64_t ticks=0;
        if (++ticks % 120 == 1) observe_combat("fighter-frame",base);
    }
    sub_03ADB118_orig(ctx, base);
    close_submenu(ctx, base); // (left by closing the pause menu)
    update_texts(base, in_practice);
    const uint32_t fighters[2] = {active_fighter(base, 0), active_fighter(base, 1)};
    title::gauge::fighters_frame(ctx, base, fighters, in_practice);
    if (in_practice) title::framedata::fighters_frame(base, fighters);
}

// SLOW MOTION: while the fighters are in play, the battle's frame (the
// fighters, their pushing and knockback, the camera, effects, the HUD) runs
// every second (1/2) or fourth (1/4) frame only, the title showing the same
// scene in between, as Smash Bros.' training mode steps its frames. Held
// together, nothing moves against anything else. The pad steps with it
// (os::set_input_step): the frames that run are those after a read the
// game saw change, with every press made since, so none is lost (Start
// opens the pause menu; a fighter's buttons register). The pause menu, also
// run from the battle's frame, keeps its speed: the frames are held only
// after one whose fighters ran.
bool battle_frame_held() {
    static constexpr uint32_t kEvery[] = {1, 2, 4};
    const uint32_t every = kEvery[std::min(title::framedata::setting(title::framedata::kSlowMotion), 2u)];
    const bool stepping = every > 1 && g_fighters_ran;
    os::set_input_step(stepping ? every : 1);
    return stepping && !os::input_step_delivered();
}

PPC_FUNC(sub_0726DF8C_orig);
PPC_FUNC(sub_0726DF8C) {
    if (practice(base) ? battle_frame_held() : (os::set_input_step(1), false)) return;
    g_fighters_ran = false;
    if (g_submenu_in) take_settings(ctx, base); // (the battle state runs on in the pause menu)
    if (os::take_select_chord() && practice(base)) {
        const bool reverse = load(base, kPracticeSettings + kReverse) == 1;
        if (std::getenv("TTT2_TRACE_PRACTICE")) {
            std::fprintf(stderr, "ttt2: practice: position reset%s\n", reverse ? " (reversed)" : "");
        }
        call(ctx, base, sub_039C2DB0, {kPracticeStart});
        const uint32_t camera = call(ctx, base, sub_05FBD4C8, {});
        call(ctx, base, sub_05FBB480, {camera, 0});
        if (reverse) call(ctx, base, sub_05FBC0A4, {camera, k2PCamera, 1}, 1.0);
        title::framedata::reset();
    }
    sub_0726DF8C_orig(ctx, base);
    title::gauge::battle_frame(base);
}


// ------------------------------------------------------------ TOUCH SELECT -> ULTIMATE SETTINGS
// The pause menu is a Lumen movie whose script calls the title's natives by
// name. Choosing a row, it switches frames (MenuDelaySwitchFrame,
// sub_085A7C38, the frame's name at r4); entering a frame it puts the focus
// on a row (MenuContainerSetFocusName, sub_085AA2D8: r3 the row, r4 the
// menu). TOUCH SELECT (the GamePad's Easy Input screen) switches to
// FramePracticeEasyInput. In Practice it switches to HUD Information's frame
// instead, as ULTIMATE SETTINGS: its texts and settings changed (open_submenu), the
// rows it does not use hidden (MenuSetVisible, MenuSetFocusable); its back,
// to ADVANCED SETTINGS' frame, goes to the pause menu's own, with the focus
// on the row it came from. The row's label, longer than TOUCH SELECT's
// text, is set on the row as the pause menu's frame comes up
// (MenuEntitySetText: r3 the text, plain ASCII, r4 the entity).

PPC_FUNC(sub_085A919C); // MenuSetVisible (r3 0/1, r4 the entity)
PPC_FUNC(sub_085A9978); // MenuEntitySetText (r3 the text, r4 the entity)
PPC_FUNC(sub_085A9420); // MenuSetFocusable (r3 0/1, r4 the entity)
constexpr uint32_t kEntityArgument = 0x106B98EC, kScript = 0x10862144; // their r5 and r6, as the script passes them

bool named(uint8_t* base, uint32_t at, const char* name) {
    return at >= kScanStart && at < kScanEnd && std::strcmp(reinterpret_cast<const char*>(base + at), name) == 0;
}

PPC_FUNC(sub_085A7C38_orig);
PPC_FUNC(sub_085A7C38) {
    if (practice(base)) {
        if (named(base, ctx.r[4], "FramePracticeEasyInput")) {
            open_submenu(ctx, base);
            ctx.r[4] = names().hud_frame;
        } else if (g_submenu && named(base, ctx.r[4], "FramePracticeMenu01-09")) {
            close_submenu(ctx, base);
            ctx.r[4] = names().menu_frame;
            g_focus_row = true;
        }
    }
    sub_085A7C38_orig(ctx, base);
}

PPC_FUNC(sub_085AA2D8_orig);
PPC_FUNC(sub_085AA2D8) {
    const bool menu = named(base, ctx.r[4], "MenuPracticeMenu01");
    if (g_focus_row && menu) {
        g_focus_row = false;
        ctx.r[3] = names().row;
    }
    const bool hud = named(base, ctx.r[4], "MenuPracticeMenu01-09-04");
    sub_085AA2D8_orig(ctx, base);
    if (menu && practice(base)) call(ctx, base, sub_085A9978, {names().row_label, names().row});
    if (hud && g_submenu) {
        frame_data_looks(ctx, base);
        show_settings(ctx, base);
        g_submenu_in = true;
    } else if (hud) {
        hud_looks(ctx, base);
        command_history_looks(ctx, base);
    }
    // ULTIMATE SETTINGS' unused rows hidden; shown again for HUD Information (they
    // stay as set across frames).
    if (hud && g_submenu != g_rows_hidden) {
        g_rows_hidden = g_submenu;
        const uint32_t shown = g_submenu ? 0 : 1;
        for (uint32_t i = std::size(kSubmenuRows); i < kHudRows; ++i) {
            for (const uint32_t entity : {names().hud_rows[i][0], names().hud_rows[i][1], hud_value(i)}) {
                call(ctx, base, sub_085A919C, {shown, entity, kEntityArgument, kScript});
            }
            call(ctx, base, sub_085A9420, {shown, names().hud_rows[i][0], kEntityArgument, kScript});
        }
    }
}

// The title reads the pause menu's values back (sub_04F9FB8C, from its
// practice code: applying the settings as the pause menu closes, the HUD's
// parts among them) without the menu's script, which shows them through its
// own native. While HUD Information's rows are ULTIMATE SETTINGS', it reads
// their own values instead, as they were when the submenu opened: closed
// from the submenu, the pause menu would otherwise turn on the HUD part
// whose row a setting borrows (ADV. COLORS on: DAMAGE INFO 2's bars), or
// off (HITBOXES off: COMBO INFO).
PPC_FUNC(sub_04F9FB8C) {
    if (g_submenu) {
        for (size_t i = 0; i < std::size(kSubmenuRows); ++i) {
            if (ctx.r[3] == hud_value(i) || named(base, ctx.r[3], reinterpret_cast<const char*>(base + hud_value(i)))) {
                ctx.r[3] = g_hud_cursors[i];
                return;
            }
        }
    }
    sub_04F9FB8C_orig(ctx, base);
}

PPC_FUNC(sub_02774188_orig);
PPC_FUNC(sub_02774188) {
    if (ctx.r[3] >= kEasyInputFighters) {
        ctx.r[3] = added_slots(ctx.r[3]);
        return;
    }
    sub_02774188_orig(ctx, base);
}

PPC_FUNC(sub_027741EC_orig);
PPC_FUNC(sub_027741EC) { // (r3 the fighter, r4 the slot, r5 the move)
    if (ctx.r[3] >= kEasyInputFighters) {
        if (ctx.r[4] < 4) base[added_slots(ctx.r[3]) + ctx.r[4]] = static_cast<uint8_t>(ctx.r[5]);
        return;
    }
    sub_027741EC_orig(ctx, base);
}


// ------------------------------------------------------------ COMMAND HISTORY
// The input history is on to begin with: the practice settings' defaults
// (sub_04F1F270, r3 the settings: as the game starts, and the pause menu's
// DEFAULT) have COMMAND HISTORY (+48) on, and so does a Practice round as it
// starts (the saved settings are copied in before). Its row in HUD Information takes
// the looks of a row whose default is on (HEALTH GAUGE's: its default
// cursor and its entries' texts), so that ON is drawn green as the default.
PPC_FUNC(sub_04F1F270_orig);
PPC_FUNC(sub_04F1F270) {
    const uint32_t settings = ctx.r[3];
    sub_04F1F270_orig(ctx, base);
    ppc::st32(base, settings + kHudWords, 1);
}

// A Practice round starts (sub_04F2544C: the HUD set up from the settings),
// its settings as saved: the input history on, whatever the save has (it
// can be turned off for the session), and its pause menu value too, which
// the menu has filled from the saved settings already (closing the menu
// would read it back).
PPC_FUNC(sub_04F2544C_orig);
PPC_FUNC(sub_04F2544C) {
    ppc::st32(base, kPracticeSettings + kHudWords, 1);
    sub_04F2544C_orig(ctx, base);
    if (load(base, kMenusMade)) call(ctx, base, sub_04F9FB6C, {0, hud_value(0)});
}

// The title turns its command history bar on with sub_04F1EDAC (r3 the
// practice HUD, r4 1: bit 0 of its +4 set, then the bar started), from the
// practice settings' COMMAND HISTORY word (+48) as a round starts and from
// the pause menu's value as it closes. It never turns on: the word, which
// the pause menu shows and sets as before, turns on the input history of
// title/framedata.cpp instead.
PPC_FUNC(sub_04F1EDAC_orig);
PPC_FUNC(sub_04F1EDAC) {
    ppc::st32(base, ctx.r[3] + 4, load(base, ctx.r[3] + 4) & ~1u);
    ctx.r[4] = 0;
    sub_04F1EDAC_orig(ctx, base);
}

// Preserve normal engine behavior. Trace the native demonstration save/restore
// paths so their object lifetimes and animation resync can be validated live.
PPC_FUNC(sub_03A45CA4_orig);
PPC_FUNC(sub_03A45CA4) {
    std::array<uint32_t,kCombatObjects> objects{};
    std::vector<uint8_t> before;
    if (checkpoint_observing() && practice(base)) {
        bool valid=true;
        for (uint32_t i=0;i<kCombatObjects;++i) {
            objects[i]=load(base,kSidePlayers+4*i);
            valid &= objects[i] && guest_memory_committed(objects[i],kCombatObjectBytes);
        }
        if (valid) {
            before.resize(kCombatObjects*kCombatObjectBytes);
            for (uint32_t i=0;i<kCombatObjects;++i)
                std::memcpy(before.data()+i*kCombatObjectBytes,base+objects[i],kCombatObjectBytes);
            observe_combat("native-save-before",base);
        }
    }
    sub_03A45CA4_orig(ctx,base);
    if (!before.empty()) {
        unsigned changed=0;
        for (uint32_t i=0;i<kCombatObjects;++i)
            for (uint32_t b=0;b<kCombatObjectBytes;++b)
                changed += before[i*kCombatObjectBytes+b] != base[objects[i]+b];
        std::fprintf(stderr,"checkpoint-observe native-save source_bytes_changed=%u scratch=108A3C08-108C2E90\n",changed);
    }
}
PPC_FUNC(sub_03A472A4_orig);
PPC_FUNC(sub_03A472A4) {
    observe_combat("native-restore-before",base);
    sub_03A472A4_orig(ctx,base);
    observe_combat("native-restore-after",base);
}
