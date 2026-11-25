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
//   language = <code>      the language the game shows its texts in: a code
//                          of kLanguages (en, fr, ...; any case). None, an
//                          empty value or a code it does not have: English.
//
// No SDL here, as in display_settings.h.

#include <cstddef>
#include <cstdint>
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

// The languages the game can be shown in: the European Wii U game has its
// texts in these. `wiiu`: the console's language number for it (the
// system setting cafe.language the title reads), `name`: in English, as
// the launcher lists it. English first: the game's own.
struct Language {
    std::string_view code, name;
    uint32_t wiiu;
};
inline constexpr Language kLanguages[] = {
    {"en", "English", 1}, {"fr", "French", 2},  {"de", "German", 3},
    {"it", "Italian", 4}, {"es", "Spanish", 5}, {"ru", "Russian", 10},
};

// The language of `code` (any case, no spaces); nullptr when the game has
// none such.
const Language* find_language(std::string_view code);

struct Settings {
    std::string player_name; // clean_name()'s; empty: the game's own
    std::string language;    // a code of kLanguages other than "en"; empty: English
    bool operator==(const Settings&) const = default;
};

// The language `settings` show the game in (English when none is set).
const Language& language_of(const Settings& settings);

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
