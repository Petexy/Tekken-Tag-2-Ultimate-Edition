#pragma once

// The player's game settings that are not about the picture: game.ini,
// beside display.ini and keyboard.ini (the same folder on both systems),
// which the launcher's Settings write and the game reads when it starts.
// Lines are `key = value`, `#` starts a comment (at the start of a line or
// after a space), as in display.ini; of a key given twice the later line
// counts. Keys the game does not know are left out with a warning (the
// launcher keeps them in the file).
//
//   player_name = <name>   the name the game shows for the player in place
//                          of its own ("Player", in the game's language):
//                          up to 16 characters of printable ASCII. None, or
//                          an empty value: the game's own.
//
// No SDL here, as in display_settings.h.

#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace cafe::host::game {

// The most characters a name keeps. The title keeps a player's name in
// 20-byte fields, copied in with strncpy (a name of 20 bytes or more would
// lose its terminating zero there); 16 ASCII characters always fit.
inline constexpr size_t kMaxNameLength = 16;

// `text` as a name the title can show: without the spaces and tabs at both
// ends, each character outside printable ASCII (a whole UTF-8 sequence, or
// a byte that is not one) as '?', cut to kMaxNameLength characters (and no
// space left at the end). Empty when nothing is left.
std::string clean_name(std::string_view text);

struct Settings {
    std::string player_name; // clean_name()'s; empty: the game's own
    bool operator==(const Settings&) const = default;
};

// A line left out or changed, and why.
struct Warning {
    size_t line; // from 1
    std::string text;
};

struct Parsed {
    Settings settings;
    std::vector<Warning> warnings;
};

Parsed parse(std::string_view text);

// game.ini in display.ini's folder (display::file_path()).
std::filesystem::path file_path();

struct Loaded {
    Settings settings;
    std::vector<std::string> log; // the warnings, then a summary ("game: ...")
    std::string error;            // why a file that is there cannot be read; empty otherwise
};

// The settings from `file`; the defaults when it is missing or unreadable.
Loaded load(const std::filesystem::path& file);

} // namespace cafe::host::game
