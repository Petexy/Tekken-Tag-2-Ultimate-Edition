#pragma once

// The in-app file and folder browser's folders (no SDL): the places it starts from, a folder's entries in the order
// shown, and what it says of a file (the controller's way to choose the game's .wua and where to install; the
// system's picker stays for mouse users).

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
};
// Home, Downloads, Games (when there), each mounted drive under /run/media/<user> and /media/<user>, Computer (/).
std::vector<Place> places(const fs::path& home, const std::string& user);

struct Entry {
    enum class Kind { kUp, kFolder, kFile };
    Kind kind = Kind::kFile;
    std::string name; // as shown (".. (up to Games)" for kUp)
    fs::path path;
    uint64_t size = 0; // files
    int items = -1;    // folders: how many entries they hold (-1: not readable)
    bool wua = false;  // a .wua (any case)
};
// A folder's entries: up (unless at /), folders, then files (only folders when `folders_only`), each by name
// without case, hidden ones (".name") left out. `error`: why it could not be read (then only "up").
std::vector<Entry> list_folder(const fs::path& folder, bool folders_only, std::string* error = nullptr);

// "15.8 GB", "340 MB", "2 KB", "0 B".
std::string size_text(uint64_t bytes);
// The folder a browser starts in: the one of `current` when it is there, else the first of `fallbacks` that is.
fs::path start_folder(const fs::path& current, const std::vector<fs::path>& fallbacks);

} // namespace launcher::app
