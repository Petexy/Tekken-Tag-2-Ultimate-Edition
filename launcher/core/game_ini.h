#pragma once

// The game's own settings that are not about the picture: game.ini, beside
// display.ini and keyboard.ini (the same folder on both systems: Linux
// $XDG_CONFIG_HOME/ttt2, else ~/.config/ttt2; Windows
// %LOCALAPPDATA%\TTT2Ultimate\config). What the launcher's Settings > Game
// writes there, the game reads when it starts.
//
// The file: UTF-8 text, a line per setting ("key = value"), `#` starting a
// comment at the start of a line or after a space (as in display.ini). A
// setting given twice: the later line counts. The launcher changes only the
// lines of the settings it writes: every other line (comments, settings it
// does not know) stays as it was.
//
// player_name: the name the game shows for the player instead of its own
// default ("Player"). A missing file, a missing key or an empty value: the
// default.
// language: the language the game shows its texts and menus in, by its code
// (cafe::host::game::kLanguages: en, fr, ...). A missing file, a missing key,
// an empty value or a code the game does not have: English.

#include "paths.h"

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace launcher::game_ini {

// game.ini in the folder of `display_file` (display.ini: wherever the game reads that one from).
fs::path beside(const fs::path& display_file);

inline constexpr std::string_view kNameKey = "player_name";
inline constexpr std::string_view kLanguageKey = "language";
// What the game calls the player without a name of their own.
inline constexpr const char* kDefaultName = "Player";

// ---- what a name may be (the one place to change when the game's limits are known better)

// The most characters a name has (after its spaces at both ends are left out).
inline constexpr std::size_t kNameMost = 16;
// A character a name may have: printable ASCII (space to ~), but `#`, which
// would start a comment in the file.
bool name_character(char32_t c);
// The rule as the Settings page says it.
std::string name_rule();

// The name as it is kept: without the spaces at both ends.
std::string tidy_name(std::string_view name);
// Why `name` (tidied) cannot be kept, "" when it can (an empty one can: the game's default).
std::string name_problem(std::string_view name);
// The first character of `text` a name cannot have (a whole UTF-8 sequence, or the byte that is not one), "" when
// there is none.
std::string first_refused(std::string_view text);

// ---- the file

struct Settings {
    std::string player_name; // as the file has it (tidied), "" for none
    std::string language;    // as the file has it (any case, maybe a code the game does not have), "" for none
    bool operator==(const Settings&) const = default;
};

struct Loaded {
    Settings settings;
    bool exists = false;
    std::string text;              // the file's text (written back with the changes)
    std::string error;             // why it cannot be read ("cannot read <file>: ...", "<file> is not a file")
    std::vector<std::string> log;  // lines for the launcher's log
};

// What `file` says; a missing file is not an error (the defaults).
Loaded load(const fs::path& file);
// What a file's text says.
Settings parse(std::string_view text);

// `text` with player_name set to `name`: its line replaced (the first one; any later ones left out), or added at the
// end; an empty `name` leaves the key out. Every other line kept as it was. A new file (empty `text`) gets a short
// header saying what it is.
std::string with_name(std::string_view text, std::string_view name);
// Saves `name` (tidied) into `file`, keeping the rest of what it has (written anew when it cannot be read).
bool save_name(const fs::path& file, std::string_view name, std::string* error = nullptr);

// `text` with language set to `code`: the line that counts (the later one, when there are several) takes it, the
// earlier ones are left out, or a line is added at the end; an empty `code` leaves the key out. Every other line kept
// as it was; a new file (empty `text`) gets the short header.
std::string with_language(std::string_view text, std::string_view code);
// Saves `code` (a code of cafe::host::game::kLanguages, also "en": the choice is written) into `file`, keeping the
// rest of what it has (written anew when it cannot be read).
bool save_language(const fs::path& file, std::string_view code, std::string* error = nullptr);

} // namespace launcher::game_ini
