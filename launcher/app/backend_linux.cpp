#include "backend_linux.h"

#include "keymap.h"
#include "paths.h"
#include "release.h"
#include "settings.h"
#include "sha256.h"
#include "status.h"
#include "system.h"

#include <unistd.h>

#include <cstdlib>
#include <fstream>
#include <memory>

namespace launcher {
extern const char* const kBuildCommit; // (build_commit.cpp, made by CMake)
}

namespace launcher::app {

namespace {

bool there(const fs::path& p) {
    std::error_code ec;
    return !p.empty() && fs::exists(p, ec);
}

} // namespace

fs::path program_file() {
    std::error_code ec;
    const fs::path p = fs::read_symlink("/proc/self/exe", ec);
    return ec ? fs::path() : p;
}

fs::path home_folder() {
    const char* h = std::getenv("HOME");
    return h && *h ? fs::path(h) : fs::path("/");
}

model::Facts start_facts(const Places& places, const fs::path& here, const fs::path& chosen_game,
                         std::optional<fs::path>* appimage, std::string* banner) {
    model::Facts f;
    f.caps = model::Caps::linux_caps();
    f.launcher_version = TTT2_LAUNCHER_VERSION;
    f.kit = find_kit(here, TTT2_LAUNCHER_BUILD_KIT);
    f.importer = find_importer(here, TTT2_LAUNCHER_SOURCE_IMPORTER);
    f.python = find_python(here);
    f.builder = there(f.kit / "bin/ttt2-build");
    f.this_build = kit_version(f.kit);
    f.build_commit = *kBuildCommit ? kBuildCommit : build_commit(f.this_build);
    f.chosen_game = chosen_game;
    f.distro = this_distro();
    f.saves = places.saves;
    std::error_code ec;
    f.saves_custom = normal(places.saves) != normal(places.default_saves()) &&
                     !fs::equivalent(places.saves, places.default_saves(), ec);
    // Steam's last answer to which DLC is owned, until it is asked again.
    if (const auto saved = saved_ownership(places.owned_cache())) {
        f.owned.answer = saved->owned;
        f.owned.has_answer = true;
    }
    const std::optional<fs::path> image = running_appimage(program_file(), std::getenv("APPIMAGE"), std::getenv("APPDIR"));
    f.self_update = image.has_value();
    f.custom_releases = std::getenv("TTT2_LAUNCHER_RELEASES") != nullptr;
    f.custom_github = std::getenv("TTT2_LAUNCHER_GITHUB") != nullptr;
    if (appimage) *appimage = image;
    if (banner) {
        *banner = std::string("ttt2-launcher ") + TTT2_LAUNCHER_VERSION + ": kit " +
                  (f.kit.empty() ? "(none)" : f.kit.string()) + ", importer " +
                  (f.importer.empty() ? "(none)" : f.importer.string()) + ", python " +
                  (f.python.empty() ? "(none)" : f.python.string()) + ", AppImage " +
                  (image ? image->string() : "(none)");
    }
    return f;
}

void appimage_first_frame() {
    if (const auto image = running_appimage(program_file(), std::getenv("APPIMAGE"), std::getenv("APPDIR")))
        forget_previous(*image);
}

std::string appimage_no_window() {
    const auto image = running_appimage(program_file(), std::getenv("APPIMAGE"), std::getenv("APPDIR"));
    std::error_code ec;
    if (!image || !fs::exists(previous_file(*image), ec)) return {};
    if (const std::string why = restore_previous(*image); !why.empty()) {
        return "\n\nThe version before this update is kept as " + previous_file(*image).string() + ": rename it to " +
               image->filename().string() + " to go back to it (" + why + ").";
    }
    std::fprintf(stderr, "ttt2-launcher: the version before this update is back in %s\n", image->c_str());
    return "\n\nThe launcher went back to the version it was before this update: start it again.";
}

void LinuxEnvironment::look(model::Facts& facts) {
    facts.install = find_install(places_);
    const bool installed = facts.install.state == InstallState::kInstalled;
    facts.game_built = installed ? built_version(facts.install.folder) : std::string();
    facts.icon = installed && there(facts.install.folder / "icon.png");
    if (!facts.game_started_here) facts.game_running = game_runs(facts);
}

bool LinuxEnvironment::game_runs(const model::Facts& facts) {
    // (/proc's programs, about a millisecond: the model asks every 2 s while a game started elsewhere runs.)
    return facts.install.state != InstallState::kNone && program_running(facts.install.folder);
}

std::optional<fs::path> LinuxEnvironment::install_target(const fs::path& chosen, std::string* why) {
    return launcher::install_target(chosen, why);
}

void LinuxEnvironment::write_started_record(const fs::path& folder, const fs::path& game) {
    launcher::write_started_record(places_, folder, game);
}

bool LinuxEnvironment::started(const fs::path& folder) { return there(folder / kStarted); }

void LinuxEnvironment::forget_started_record() {
    std::error_code ec;
    fs::remove(places_.started_record(), ec);
}

std::string LinuxEnvironment::log_end(const fs::path& file) {
    std::ifstream in(file, std::ios::binary | std::ios::ate);
    const std::streamoff size = in ? static_cast<std::streamoff>(in.tellg()) : 0;
    if (size <= 0) return {};
    const std::streamoff from = std::max<std::streamoff>(0, size - 65536);
    std::string text(static_cast<size_t>(size - from), '\0');
    in.seekg(from);
    in.read(text.data(), static_cast<std::streamsize>(text.size()));
    text.resize(static_cast<size_t>(std::max<std::streamsize>(0, in.gcount())));
    return text;
}

bool LinuxEnvironment::exists(const fs::path& path) { return there(path); }

std::string LinuxUpdateFiles::sha256(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) return {};
    Sha256 h;
    std::unique_ptr<char[]> buf(new char[1 << 20]);
    while (in) {
        in.read(buf.get(), 1 << 20);
        const std::streamsize n = in.gcount();
        if (n > 0) h.update(buf.get(), static_cast<size_t>(n));
    }
    if (in.bad()) return {};
    const auto digest = h.finish();
    return hex(digest.data(), digest.size());
}

} // namespace launcher::app
