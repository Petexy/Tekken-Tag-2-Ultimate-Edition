#pragma once

// The fighters' intro and win subtitles in Polish, which the title has
// none of (see language.h).
//
// The title's subtitle file (entry 917395eb; with added fighters the
// importer's copy, shared/keys/) holds a language container per line (a
// fighter id's 30 lines): u32 16, 16 x {u32 offset, u32 size} of its text
// banks, one bank per text language (entry = the title's text language -
// 1: 1 English, 3 French, ... 9 Russian; 10 to 15 the title leaves unused,
// a " " each). A bank holds the line's text (one or more, spoken in turn)
// with its timing: U+FFFB show U+FFFC hide U+FFF5 U+0001, the words,
// U+FFFB U+0001 U+FFFC U+FFFF. The file itself (big-endian): u32 count,
// count x {u32 offset, u32 size}, each entry 16-aligned; an empty one is
// four bytes 0xFF.
//
// With Polish the title runs in English (entry 1); each line's entry 1
// then shows Polish where there is one: the added fighters' own (the
// importer writes it to entry 10: a timed text there), else ours for the
// title's own lines (subtitles_polish.inc, by entry), with the English
// line's timing (roster.h: prepare_subtitles serves it).

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string_view>
#include <vector>

namespace cafe::title::subtitles {

// The subtitle file's entry in the title's archives.
inline constexpr uint32_t kFile = 0x917395EB;

// The container entry an added fighter's Polish line is in.
inline constexpr size_t kPolishEntry = 10;

// A line of ours: `key` the file's entry ("12"), or its k-th text ("12.1").
struct Line {
    std::string_view key, text;
};

// Our Polish for the title's own lines (subtitles_polish.inc).
std::span<const Line> polish_lines();

struct Polish {
    std::vector<uint8_t> file;
    size_t ours = 0;  // the title's lines shown in our Polish
    size_t added = 0; // lines shown in their own Polish (entry 10)
};

// The subtitle file with each line's English entry showing its Polish (see
// above); nothing when the file is not as described.
std::optional<Polish> in_polish(const std::vector<uint8_t>& file, std::span<const Line> ours = polish_lines());

} // namespace cafe::title::subtitles
