// The launcher's own updates, what only the AppImage (Linux) needs of them
// (see release.h): the AppImage it runs from, its folder, curl or wget, the
// new file made executable and renamed over it (the old one kept until the new
// one drew its first frame), and /proc.

#include "release.h"

#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <fstream>

namespace launcher {

std::optional<fs::path> running_appimage(const fs::path& program, const char* appimage, const char* appdir) {
    if (!appimage || !*appimage || !appdir || !*appdir || program.empty()) return std::nullopt;
    const fs::path file = appimage;
    std::error_code ec;
    if (!file.is_absolute() || !fs::is_regular_file(file, ec) || !inside(program, appdir)) return std::nullopt;
    return normal(file);
}

std::string cannot_replace(const fs::path& appimage) {
    const fs::path folder = appimage.parent_path();
    if (::access(folder.c_str(), W_OK | X_OK) != 0) return std::strerror(errno);
    return {};
}

std::optional<Downloader> find_downloader() {
    if (const auto curl = find_in_path("curl")) return Downloader{*curl, true};
    if (const auto wget = find_in_path("wget")) return Downloader{*wget, false};
    return std::nullopt;
}

std::string make_executable(const fs::path& update, const fs::path& appimage) {
    struct stat old = {};
    const mode_t mode = ::stat(appimage.c_str(), &old) == 0 ? (old.st_mode & 07777) : 0755;
    if (::chmod(update.c_str(), mode | S_IRUSR | S_IWUSR | S_IXUSR) != 0) return std::strerror(errno);
    return {};
}

std::string replace_appimage(const fs::path& update, const fs::path& appimage) {
    if (::rename(update.c_str(), appimage.c_str()) != 0) return std::strerror(errno);
    return {};
}

std::string keep_previous(const fs::path& appimage) {
    const fs::path previous = previous_file(appimage);
    ::unlink(previous.c_str());
    if (::link(appimage.c_str(), previous.c_str()) == 0) return {};
    // (A file system without hard links: a copy, as executable as the AppImage.)
    std::error_code ec;
    if (fs::copy_file(appimage, previous, fs::copy_options::overwrite_existing, ec)) {
        fs::permissions(previous, fs::status(appimage, ec).permissions(), ec);
        if (!ec) return {};
    }
    const std::string why = ec ? ec.message() : std::string("it cannot be copied");
    ::unlink(previous.c_str());
    return why;
}

std::string restore_previous(const fs::path& appimage) {
    if (::rename(previous_file(appimage).c_str(), appimage.c_str()) != 0) return std::strerror(errno);
    return {};
}

void forget_previous(const fs::path& appimage) { ::unlink(previous_file(appimage).c_str()); }

bool process_alive(int pid) {
    if (pid <= 0) return false;
    std::ifstream in("/proc/" + std::to_string(pid) + "/stat");
    std::string stat;
    if (!std::getline(in, stat)) return false;
    // "<pid> (<name>) <state> ...": the name may hold anything, ')' too.
    const size_t close = stat.rfind(')');
    if (close == std::string::npos || close + 2 >= stat.size()) return false;
    const char state = stat[close + 2];
    return state != 'Z' && state != 'X' && state != 'x';
}

} // namespace launcher
