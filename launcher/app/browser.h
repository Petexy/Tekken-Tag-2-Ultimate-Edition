#pragma once

// The in-app file and folder browser's folders (no SDL): the places it starts from, a folder's entries in the order
// shown, and what it says of a file (the controller's way to choose the game's .wua and where to install; the
// system's picker stays for mouse users). Everything here may read slow disks: the app calls it off the UI thread
// (list_folder, count_items, places) and posts the answer back.

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace launcher::app {

namespace fs = std::filesystem;

struct Place {
    std::string id, name; // "home", "Home"
    fs::path path;
    std::string icon;     // the toolkit's line icon ("stroke:home")
    std::string kind;     // what the row says beside the name ("Wine", "Drive"; "" for none)
};
// Home, Downloads, Games (when there); on Linux also the folders players look in that a file manager hides (no
// path can be typed): Steam (~/.local/share/Steam, else ~/.steam/steam; Flatpak Steam's too), Flatpak apps
// (~/.var/app), the Wine prefixes found (~/.wine, winetricks', Bottles', Lutris'/Heroic's under ~/Games, Faugus'), and
// every drive mounted for the player (under /run/media/<user> and /media/<user>, and a mount point right under
// /run/media, /media or /mnt: the Steam Deck's SD card); Computer (/) last. Windows: each drive (C:, D:, ...).
std::vector<Place> places(const fs::path& home, const std::string& user);
// The Wine prefixes in the places (each a folder with a drive_c in it), at most `limit`, by name.
std::vector<fs::path> wine_prefixes(const fs::path& home, size_t limit = 8);

struct Entry {
    enum class Kind { kUp, kFolder, kFile };
    Kind kind = Kind::kFile;
    std::string name; // as shown (".. (up to Games)" for kUp)
    fs::path path;
    uint64_t size = 0; // files
    int items = -1;    // folders: how many entries they hold (-1: not readable, kNotCounted: not counted yet)
    bool wua = false;  // a .wua (any case)
};
inline constexpr int kNotCounted = -2;
// A folder's entries: up (unless at /), folders, then files (only folders when `folders_only`), each by name
// without case; hidden ones (".name") only when `hidden`. `count`: each folder's items counted here (one more
// directory read per folder), else left kNotCounted for count_items. `error`: why it could not be read (then only
// "up").
std::vector<Entry> list_folder(const fs::path& folder, bool folders_only, std::string* error = nullptr,
                               bool hidden = false, bool count = true);
// How many entries a folder holds as list_folder shows them (hidden ones only when `hidden`; 9999 at most), -1 when
// it cannot be read.
int count_items(const fs::path& folder, bool hidden = false);

// "15.8 GB", "340 MB", "2 KB", "0 B".
std::string size_text(uint64_t bytes);
// The folder a browser starts in: the one of `current` when it is there, else the first of `fallbacks` that is.
fs::path start_folder(const fs::path& current, const std::vector<fs::path>& fallbacks);

} // namespace launcher::app
