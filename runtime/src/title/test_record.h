#pragma once
// A developer's customization record for one fighter (TTT2_TEST_CUSTOMIZE), for testing worn items and colours on
// an added fighter before there is a Customize mode or a save for it.
//
// The title keeps what a fighter wears in a 4096-byte record: byte 0 "holds data"; +4, 21 x s32, the item worn in
// each equip slot (the `index` of an Instance in the fighter's item database `<code>.xml`; none: -1 or 0);
// +568/+570/+572, u16 variants of slots 15/16/7; +576, 14 colour groups x 5 entries of 12 bytes {u32, u32 colour
// number, f32} that set colour registers 26..95 (register = 26 + 5 * group + entry; groups 0 and 1 are stored
// swapped: group 0 at +636, group 1 at +576; colour 0 or 255: the fighter's default; else a colour-grid cell,
// s << 11 | (y - 1) << 6 | (x - 1) for the palette files' `x y s`, s = 9 the cell's own colour). On the select
// screen the title fills a player's working record from the save (sub_0242F438), copies it into the match set-up when the
// costume is confirmed (sub_033E3208), and the fight's loader hands it to the character manager (sub_065D2B0C),
// which queues the items for the model and sets the registers.
//
// The switch replaces the working record's items and the named colours right after the title filled it, so
// everything after that is the title's own path. Text: `<who>:<entry>,<entry>...` where <who> is a pack's code
// (`kzm`) or `#<select id>`, and an entry is `<slot>=<index>` (optionally `<index>/<variant>`) or
// `c<register>=<colour number>`. Example: `kzm:0=5,8=1,12=2,17=333,18=338,5=253,c51=18433`. Slots not named are
// empty: name the fighter's default items too. Nothing here knows an item or a colour: the numbers are the
// tester's.
#include <array>
#include <charconv>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>

namespace cafe::title::test_record {
constexpr uint32_t kSize = 4096, kSlots = 21;
constexpr uint32_t kItems = 4, kColours = 576, kColourGroup = 60, kColourEntry = 12;
constexpr uint32_t kFirstRegister = 26, kRegisters = 70, kGroupEntries = 5;
constexpr int32_t kNone = -1;

struct Spec {
    std::string who;                       // a pack's code, or "#<select id>"
    std::array<int32_t, kSlots> items;     // Instance index by equip slot (kNone: nothing)
    std::array<uint16_t, kSlots> variants; // 0xFFFF: none
    std::map<uint32_t, uint32_t> colours;  // colour register -> colour number
};

// Where the title reads slot `slot`'s variant from, 0 for the slots that have none.
constexpr uint32_t variant_offset(uint32_t slot) { return slot == 7 ? 572 : slot == 15 ? 568 : slot == 16 ? 570 : 0; }

// Where colour register `number`'s entry is (26..95).
constexpr uint32_t colour_offset(uint32_t number) {
    const uint32_t group = (number - kFirstRegister) / kGroupEntries, entry = (number - kFirstRegister) % kGroupEntries;
    const uint32_t stored = group == 0 ? 1 : group == 1 ? 0 : group; // the first two groups are stored swapped
    return kColours + kColourGroup * stored + kColourEntry * entry;
}

namespace detail {
inline bool number(std::string_view text, long& out) {
    if (text.empty()) return false;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), out);
    return error == std::errc{} && end == text.data() + text.size();
}
inline void put32(uint8_t* at, uint32_t v) {
    at[0] = static_cast<uint8_t>(v >> 24), at[1] = static_cast<uint8_t>(v >> 16);
    at[2] = static_cast<uint8_t>(v >> 8), at[3] = static_cast<uint8_t>(v);
}
} // namespace detail

// The switch's text as a Spec; nothing if any part of it is malformed (a half-read record would only mislead).
inline std::optional<Spec> parse(std::string_view text) {
    Spec spec;
    spec.items.fill(kNone);
    spec.variants.fill(0xFFFF);
    const size_t colon = text.find(':');
    if (colon == std::string_view::npos || colon == 0) return std::nullopt;
    spec.who = std::string(text.substr(0, colon));
    text.remove_prefix(colon + 1);
    while (!text.empty()) {
        const size_t comma = text.find(',');
        const std::string_view entry = text.substr(0, comma);
        text.remove_prefix(comma == std::string_view::npos ? text.size() : comma + 1);
        const size_t equals = entry.find('=');
        if (equals == std::string_view::npos) return std::nullopt;
        std::string_view key = entry.substr(0, equals), value = entry.substr(equals + 1);
        long a = 0, b = 0;
        if (!key.empty() && key[0] == 'c') {
            if (!detail::number(key.substr(1), a) || !detail::number(value, b)) return std::nullopt;
            if (a < kFirstRegister || a >= kFirstRegister + kRegisters || b < 0 || b > 0xFFFF) return std::nullopt;
            spec.colours[static_cast<uint32_t>(a)] = static_cast<uint32_t>(b);
            continue;
        }
        long variant = 0xFFFF;
        if (const size_t slash = value.find('/'); slash != std::string_view::npos) {
            if (!detail::number(value.substr(slash + 1), variant) || variant < 0 || variant > 0xFFFF)
                return std::nullopt;
            value = value.substr(0, slash);
        }
        if (!detail::number(key, a) || !detail::number(value, b)) return std::nullopt;
        if (a < 0 || a >= kSlots || b <= 0 || b > 0xFFFF) return std::nullopt;
        if (variant != 0xFFFF && !variant_offset(static_cast<uint32_t>(a))) return std::nullopt;
        spec.items[static_cast<size_t>(a)] = static_cast<int32_t>(b);
        spec.variants[static_cast<size_t>(a)] = static_cast<uint16_t>(variant);
    }
    return spec;
}

// Makes the record (4096 guest bytes, big-endian, as the title initialised it) hold the Spec's items and colours.
// Everything the Spec does not name stays the title's: the other colours (0: the fighter's default), the print
// data, the costume number.
inline void apply(const Spec& spec, uint8_t* record) {
    record[0] = 1;
    for (uint32_t slot = 0; slot < kSlots; ++slot) {
        detail::put32(record + kItems + 4 * slot, static_cast<uint32_t>(spec.items[slot]));
        if (const uint32_t at = variant_offset(slot)) {
            record[at] = static_cast<uint8_t>(spec.variants[slot] >> 8);
            record[at + 1] = static_cast<uint8_t>(spec.variants[slot]);
        }
    }
    for (const auto& [number, colour] : spec.colours) detail::put32(record + colour_offset(number) + 4, colour);
}
} // namespace cafe::title::test_record
