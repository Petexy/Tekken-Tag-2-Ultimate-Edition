#include "browser.h"
#include "utf8_path.h"

#include "i18n.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <system_error>

#ifndef _WIN32
#include <sys/stat.h>
#endif

namespace launcher::app {

namespace {

bool is_dir(const fs::path& p) {
    std::error_code ec;
    return !p.empty() && fs::is_directory(p, ec);
}

std::string lower(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

bool hidden_name(const fs::path& p) { return path_utf8(p.filename()).starts_with('.'); }

// The folders right inside `base` (at most `limit` looked at), by name.
std::vector<fs::path> subfolders(const fs::path& base, size_t limit = 256) {
    std::vector<fs::path> out;
    // (A look first: most of the places looked in are not there, and opening a folder can wait on a disk.)
    if (!is_dir(base)) return out;
    std::error_code ec;
    fs::directory_iterator it(base, fs::directory_options::skip_permission_denied, ec);
    if (ec) return out;
    size_t seen = 0;
    for (const fs::directory_iterator end; it != end && seen < limit; it.increment(ec), ++seen) {
        if (ec) break;
        std::error_code e2;
        if (it->is_directory(e2)) out.push_back(it->path());
    }
    std::sort(out.begin(), out.end());
    return out;
}

#ifndef _WIN32
// Another file system is mounted on it (a drive), not just a folder of its parent's.
bool mount_point(const fs::path& p) {
    struct stat a {}, b {};
    return ::stat(p.c_str(), &a) == 0 && ::stat(p.parent_path().c_str(), &b) == 0 && S_ISDIR(a.st_mode) &&
           a.st_dev != b.st_dev;
}
#endif

} // namespace

int count_items(const fs::path& folder, bool hidden) {
    std::error_code ec;
    fs::directory_iterator it(folder, fs::directory_options::skip_permission_denied, ec);
    if (ec) return -1;
    int n = 0;
    for (const fs::directory_iterator end; it != end; it.increment(ec)) {
        if (ec) break;
        if (!hidden && hidden_name(it->path())) continue;
        if (++n >= 9999) break;
    }
    return n;
}

std::vector<fs::path> wine_prefixes(const fs::path& home, size_t limit) {
    std::vector<fs::path> found;
    const auto prefix = [](const fs::path& p) { return is_dir(p / "drive_c"); };
    if (prefix(home / ".wine")) found.push_back(home / ".wine");
    // (winetricks, Bottles native and Flatpak, Lutris' and Heroic's game folders, Faugus.)
    for (const fs::path& base : {home / ".local/share/wineprefixes", home / ".local/share/bottles/bottles",
                                 home / ".var/app/com.usebottles.bottles/data/bottles/bottles", home / "Games",
                                 home / "Games/Heroic/Prefixes", home / "Games/Heroic/Prefixes/default",
                                 home / "Faugus"}) {
        for (const fs::path& p : subfolders(base))
            if (prefix(p)) found.push_back(p);
    }
    std::sort(found.begin(), found.end(), [](const fs::path& a, const fs::path& b) {
        const std::string x = lower(path_utf8(a.filename())), y = lower(path_utf8(b.filename()));
        return x != y ? x < y : a < b;
    });
    found.erase(std::unique(found.begin(), found.end()), found.end());
    if (found.size() > limit) found.resize(limit);
    return found;
}

std::vector<Place> places(const fs::path& home, const std::string& user) {
    std::vector<Place> out;
    using i18n::tr;
    out.push_back({"home", tr("places.home", "Home"), home, "stroke:home", ""});
    if (is_dir(home / "Downloads"))
        out.push_back({"downloads", tr("places.downloads", "Downloads"), home / "Downloads", "stroke:down", ""});
    if (is_dir(home / "Games")) out.push_back({"games", tr("places.games", "Games"), home / "Games", "stroke:folder", ""});
#ifdef _WIN32
    // Windows: each drive (C:, D:, ...).
    (void)user;
    for (char d = 'A'; d <= 'Z'; ++d) {
        const fs::path root = std::string(1, d) + ":\\";
        if (is_dir(root))
            out.push_back({std::string("drive:") + d, std::string(1, d) + ":", root, "stroke:drive", ""});
    }
    return out;
#else
    // Where games and their files are that a file manager hides (dot folders): Steam's, Flatpak apps', Wine's.
    for (const fs::path& steam : {home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"}) {
        if (!is_dir(steam)) continue;
        out.push_back({"steam", "Steam", steam, "stroke:folder", ""});
        break;
    }
    for (const fs::path& steam : {home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
                                  home / ".var/app/com.valvesoftware.Steam/data/Steam"}) {
        if (!is_dir(steam)) continue;
        out.push_back({"steam-flatpak", "Steam (Flatpak)", steam, "stroke:folder", ""});
        break;
    }
    if (is_dir(home / ".var/app"))
        out.push_back({"flatpak", tr("places.flatpak", "Flatpak apps"), home / ".var/app", "stroke:folder", ""});
    for (const fs::path& p : wine_prefixes(home)) {
        const std::string name = p == home / ".wine" ? std::string("Wine") : path_utf8(p.filename());
        out.push_back({"wine:" + path_utf8(p), name, p, "stroke:folder", "Wine"});
    }
    // Mounted drives (SD cards, other disks) as the desktop mounts them, and drives mounted right under /run/media,
    // /media or /mnt (the Steam Deck's SD card on older SteamOS: /run/media/mmcblk0p1).
    std::vector<fs::path> drives;
    if (!user.empty()) {
        for (const fs::path& base : {fs::path("/run/media") / user, fs::path("/media") / user})
            for (const fs::path& d : subfolders(base, 64)) drives.push_back(d);
    }
    for (const fs::path& base : {fs::path("/run/media"), fs::path("/media"), fs::path("/mnt")})
        for (const fs::path& d : subfolders(base, 64))
            if ((user.empty() || d.filename() != user) && mount_point(d)) drives.push_back(d);
    for (const fs::path& d : drives) {
        const std::string id = "drive:" + path_utf8(d);
        if (std::any_of(out.begin(), out.end(), [&](const Place& p) { return p.id == id; })) continue;
        out.push_back({id, path_utf8(d.filename()), d, "stroke:drive", ""});
    }
    out.push_back({"root", tr("places.computer", "Computer"), "/", "stroke:drive", ""});
    return out;
#endif
}

std::vector<Entry> list_folder(const fs::path& folder, bool folders_only, std::string* error, bool hidden,
                               bool count) {
    std::vector<Entry> folders, files;
    std::vector<Entry> out;
    const fs::path parent = folder.parent_path();
    if (folder != folder.root_path() && !parent.empty()) {
        Entry up;
        up.kind = Entry::Kind::kUp;
        up.path = parent;
        const std::string pname = parent == parent.root_path() ? path_utf8(parent) : path_utf8(parent.filename());
        up.name = i18n::tr("picker.up_to", ".. (up to {folder})", {{"folder", pname}});
        out.push_back(up);
    }
    std::error_code ec;
    fs::directory_iterator it(folder, fs::directory_options::skip_permission_denied, ec);
    if (ec) {
        if (error) *error = ec.message();
        return out;
    }
    for (const fs::directory_iterator end; it != end; it.increment(ec)) {
        if (ec) break;
        const fs::path p = it->path();
        const std::string name = path_utf8(p.filename());
        if (!hidden && name.starts_with('.')) continue;
        std::error_code e2;
        // (The entry's own type, read with the folder: no stat per entry unless it is a link.)
        if (it->is_directory(e2)) {
            Entry d;
            d.kind = Entry::Kind::kFolder;
            d.name = name;
            d.path = p;
            d.items = count ? count_items(p, hidden) : kNotCounted;
            folders.push_back(d);
        } else if (!folders_only && it->is_regular_file(e2)) {
            Entry f;
            f.kind = Entry::Kind::kFile;
            f.name = name;
            f.path = p;
            f.size = it->file_size(e2);
            if (e2) f.size = 0;
            f.wua = lower(path_utf8(p.extension())) == ".wua";
            files.push_back(f);
        }
    }
    const auto by_name = [](const Entry& a, const Entry& b) {
        const std::string x = lower(a.name), y = lower(b.name);
        return x != y ? x < y : a.name < b.name;
    };
    std::sort(folders.begin(), folders.end(), by_name);
    std::sort(files.begin(), files.end(), by_name);
    out.insert(out.end(), folders.begin(), folders.end());
    out.insert(out.end(), files.begin(), files.end());
    return out;
}

std::string size_text(uint64_t bytes) {
    using i18n::tr;
    if (bytes >= 1000ull * 1000 * 1000) return tr("units.gb", "{amount} GB", {{"amount", i18n::decimal(bytes / 1e9, 1)}});
    if (bytes >= 1000ull * 1000) return tr("units.mb", "{amount} MB", {{"amount", i18n::decimal(bytes / 1e6, 0)}});
    if (bytes >= 1000) return tr("units.kb", "{amount} KB", {{"amount", i18n::decimal(bytes / 1e3, 0)}});
    return tr("units.bytes", "{amount} B", {{"amount", bytes}});
}

fs::path start_folder(const fs::path& current, const std::vector<fs::path>& fallbacks) {
    if (is_dir(current)) return current;
    for (fs::path p = current; !p.empty() && p != p.root_path(); p = p.parent_path()) {
        if (is_dir(p)) return p;
    }
    for (const fs::path& f : fallbacks)
        if (is_dir(f)) return f;
    return "/";
}

} // namespace launcher::app
