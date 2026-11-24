// Linux's parts, as Windows has them. The model's preflight and the AppImage's update are Linux's: their pieces of
// launcher/core are in ttt2_launcher_core_linux. Windows never runs them, but the model refers to them: here they
// say so, and free_space is real, for the in-app browser. (In core, not in the app: every Windows program that links
// the model links these too, also its tests built with GCC's linker, which keeps what the model's tables name.)

#include "release.h"
#include "system.h"

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <system_error>
#include <vector>

namespace launcher {

std::vector<std::string> missing_cpu_features() { return {}; }
std::optional<Compiler> find_compiler(std::string* why) {
    if (why) *why = "the Windows setup brings its own compiler";
    return std::nullopt;
}
std::optional<uint64_t> free_space(const fs::path& folder) {
    std::error_code ec;
    fs::path at = folder;
    while (!at.empty() && !fs::exists(at, ec) && at != at.parent_path()) at = at.parent_path();
    const fs::space_info s = fs::space(at, ec);
    if (ec) return std::nullopt;
    return static_cast<uint64_t>(s.available);
}
uint64_t file_system(const fs::path&) { return 0; }
uint64_t size_of(const fs::path& folder) {
    uint64_t total = 0;
    std::error_code ec;
    for (fs::recursive_directory_iterator it(folder, fs::directory_options::skip_permission_denied, ec), end;
         !ec && it != end; it.increment(ec)) {
        if (it->is_regular_file(ec)) total += it->file_size(ec);
    }
    return total;
}
Distro this_distro() { return {}; }
std::string cannot_replace(const fs::path&) { return "Windows updates its launcher with its own worker"; }
std::optional<Downloader> find_downloader() { return std::nullopt; }
std::string make_executable(const fs::path&, const fs::path&) { return "not on Windows"; }
std::string replace_appimage(const fs::path&, const fs::path&) { return "not on Windows"; }
std::string keep_previous(const fs::path&) { return "not on Windows"; }
std::string restore_previous(const fs::path&) { return "not on Windows"; }
void forget_previous(const fs::path&) {}

} // namespace launcher
