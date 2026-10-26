#pragma once

// What the importer tells about the player's PC (launcher.py status and
// owned, see tools/characters/launcher.py), read into plain structures.

#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace launcher {

// The games characters come from, as the importer names them.
inline constexpr const char* kTekken7 = "tekken7";
inline constexpr const char* kTekken8 = "tekken8";

struct Fighter {
    std::string name;            // the importer's name: "kazumi"
    std::string display;         // "Kazumi Mishima"
    std::string game = kTekken7; // the game they come from
    int64_t dlc = 0;             // the Steam app id of their game's DLC that has them, 0 for the game's own
    bool installed = false; // their pack is there
    // Their pack is an older importer's: the game skips it, and adding them
    // again replaces it. (Only with `installed`.)
    bool outdated = false;
    // Their pack is a newer importer's: the game skips it too (it needs
    // updating), and this importer does not replace it. (Only with
    // `installed`, never with `outdated`.)
    bool newer = false;
    // Their pack is in the game, but an older version made it: adding them
    // again gives them what this version adds (outfits, fixes). (Only with
    // `added()`.)
    bool update = false;
    // Their moveset is saved (a Tekken 8 fighter's: their own, whole), so
    // adding them needs neither Steam nor their game running.
    bool moveset_saved = false;
    // (Tekken 8) Their pack fights with a stand-in's moves (Heihachi's): their
    // own could not be saved when they were added. `update` tells whether
    // their own can be had now. (Only with `added()`.)
    bool stand_in = false;

    // In the game: a pack it loads.
    bool added() const { return installed && !outdated && !newer; }
    bool of(std::string_view g) const { return game == g; }
};

struct ImporterStatus {
    std::string python_version;
    bool numpy = false, pillow = false;
    std::string gamescope, pactl; // their paths, empty when missing
    std::string helper;           // "prebuilt", "mingw", or empty: no way to make Tekken 7's helper
    std::string tekken8_helper;   // the same for Tekken 8's helper
    std::string cc;               // the C compiler Tekken 8's import builds two small parts with, empty: none
    bool steam_installed = false, steam_running = false;
    bool tekken7_found = false;
    std::string tekken7_path;
    std::string tekken7_error; // why Tekken 7 is not usable, empty when it is
    // Its files are there: what the packs share is made from them, even
    // when it cannot run (unknown: taken as usable).
    bool tekken7_readable = false;
    bool tekken8_found = false;
    std::string tekken8_path;
    std::string tekken8_error; // why Tekken 8's files cannot be read, empty when they can
    // Whether it is the build the helper knows, so that a moveset not saved
    // yet can be saved; none when no character needs one.
    std::optional<bool> tekken8_build_known;
    std::string tekken8_run_error; // why it cannot run hidden to save movesets, empty when it can
    std::string packs_folder;
    bool heihachi_saved = true; // his Tekken 7 moveset, which Tekken 7's imports need (unknown: taken as saved)
    std::string game_error;     // with --game: why the importer cannot read that install
    std::vector<Fighter> fighters;

    // Whether Tekken 7 can be used: found, nothing wrong with it.
    bool tekken7_usable() const { return tekken7_found && tekken7_error.empty(); }
    // Whether Tekken 8's files can be read (its characters added from them).
    bool tekken8_usable() const { return tekken8_found && tekken8_error.empty(); }
    // Whether that game's files can be read, as what the packs share needs.
    bool readable(std::string_view game) const { return game == kTekken8 ? tekken8_usable() : tekken7_readable; }
    bool found(std::string_view game) const { return game == kTekken8 ? tekken8_found : tekken7_found; }
};

std::optional<ImporterStatus> parse_status(std::string_view json, std::string* error = nullptr);

// launcher.py owned: the DLC fighters' ownership, or why it is not known.
struct Ownership {
    std::map<std::string, bool> owned;
    std::string error;
};

Ownership parse_owned(std::string_view json);

// Steam's last answer, kept (Places::owned_cache) so that the next start
// shows it at once: Steam's first answer after a boot takes most of a
// minute. Only an answer without an error is saved; none when there is none
// or it is not readable.
bool save_ownership(const std::filesystem::path& file, std::string_view json);
std::optional<Ownership> saved_ownership(const std::filesystem::path& file);

} // namespace launcher
