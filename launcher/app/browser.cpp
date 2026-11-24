#include "browser.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <system_error>

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

int count_items(const fs::path& folder) {
    std::error_code ec;
    fs::directory_iterator it(folder, fs::directory_options::skip_permission_denied, ec);
    if (ec) return -1;
    int n = 0;
    for (const fs::directory_iterator end; it != end; it.increment(ec)) {
        if (ec) break;
        if (it->path().filename().string().starts_with('.')) continue;
        if (++n >= 9999) break;
    }
    return n;
}

} // namespace

std::vector<Place> places(const fs::path& home, const std::string& user) {
    std::vector<Place> out;
    out.push_back({"home", "Home", home, "stroke:home"});
    if (is_dir(home / "Downloads")) out.push_back({"downloads", "Downloads", home / "Downloads", "stroke:down"});
    if (is_dir(home / "Games")) out.push_back({"games", "Games", home / "Games", "stroke:folder"});
    // Mounted drives (SD cards, other disks) as the desktop mounts them.
    if (!user.empty()) {
        for (const fs::path base : {fs::path("/run/media") / user, fs::path("/media") / user}) {
            std::error_code ec;
            fs::directory_iterator it(base, fs::directory_options::skip_permission_denied, ec);
            if (ec) continue;
            std::vector<fs::path> drives;
            for (const fs::directory_iterator end; it != end; it.increment(ec)) {
                if (ec) break;
                if (is_dir(it->path())) drives.push_back(it->path());
            }
            std::sort(drives.begin(), drives.end());
            for (const fs::path& d : drives)
                out.push_back({"drive:" + d.filename().string(), d.filename().string(), d, "stroke:drive"});
        }
    }
    out.push_back({"root", "Computer", "/", "stroke:drive"});
    return out;
}

std::vector<Entry> list_folder(const fs::path& folder, bool folders_only, std::string* error) {
    std::vector<Entry> folders, files;
    std::vector<Entry> out;
    const fs::path parent = folder.parent_path();
    if (folder != folder.root_path() && !parent.empty()) {
        Entry up;
        up.kind = Entry::Kind::kUp;
        up.path = parent;
        const std::string pname = parent == parent.root_path() ? parent.string() : parent.filename().string();
        up.name = ".. (up to " + pname + ")";
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
        const std::string name = p.filename().string();
        if (name.starts_with('.')) continue;
        std::error_code e2;
        if (fs::is_directory(p, e2)) {
            Entry d;
            d.kind = Entry::Kind::kFolder;
            d.name = name;
            d.path = p;
            d.items = count_items(p);
            folders.push_back(d);
        } else if (!folders_only && fs::is_regular_file(p, e2)) {
            Entry f;
            f.kind = Entry::Kind::kFile;
            f.name = name;
            f.path = p;
            f.size = fs::file_size(p, e2);
            if (e2) f.size = 0;
            f.wua = lower(p.extension().string()) == ".wua";
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
    char buf[32];
    if (bytes >= 1000ull * 1000 * 1000) std::snprintf(buf, sizeof buf, "%.1f GB", bytes / 1e9);
    else if (bytes >= 1000ull * 1000) std::snprintf(buf, sizeof buf, "%.0f MB", bytes / 1e6);
    else if (bytes >= 1000) std::snprintf(buf, sizeof buf, "%.0f KB", bytes / 1e3);
    else std::snprintf(buf, sizeof buf, "%llu B", static_cast<unsigned long long>(bytes));
    return buf;
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
