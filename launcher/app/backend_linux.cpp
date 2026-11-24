#include "backend_linux.h"

#include "keymap.h"
#include "paths.h"
#include "release.h"
#include "settings.h"
#include "sha256.h"
#include "status.h"
#include "system.h"

#include <unistd.h>

#include <cmath>
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

void LinuxEnvironment::look(model::Facts& facts) {
    facts.install = find_install(places_);
    const bool installed = facts.install.state == InstallState::kInstalled;
    facts.game_built = installed ? built_version(facts.install.folder) : std::string();
    facts.icon = installed && there(facts.install.folder / "icon.png");
    if (!facts.game_started_here)
        facts.game_running = facts.install.state != InstallState::kNone && program_running(facts.install.folder);
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

std::string sdl_key_label(int usage) {
    const Key* key = key_by_usage(usage);
    if (key && key->typed) {
        const SDL_Keycode k = SDL_GetKeyFromScancode(static_cast<SDL_Scancode>(usage), SDL_KMOD_NONE, false);
        const char* name = k != SDLK_UNKNOWN ? SDL_GetKeyName(k) : nullptr;
        if (name && *name) return name;
    }
    return model::us_key_label(usage);
}

std::vector<Monitor> sdl_monitors() {
    std::vector<Monitor> out;
    int n = 0;
    SDL_DisplayID* ids = SDL_GetDisplays(&n);
    for (int i = 0; ids && i < n; ++i) {
        const SDL_DisplayMode* mode = SDL_GetDesktopDisplayMode(ids[i]);
        Monitor m;
        if (mode) {
            const float density = mode->pixel_density > 0 ? mode->pixel_density : 1;
            m.height = static_cast<uint32_t>(std::lround(mode->h * density));
            if (mode->refresh_rate_denominator > 0)
                m.refresh = static_cast<int>(std::llround(1000.0 * mode->refresh_rate_numerator /
                                                          mode->refresh_rate_denominator));
            else
                m.refresh = static_cast<int>(std::lround(mode->refresh_rate * 1000));
        }
        out.push_back(m);
    }
    SDL_free(ids);
    return out;
}

std::string file_url(const fs::path& path) {
    static const char* const kHex = "0123456789ABCDEF";
    std::string url = "file://";
    for (const unsigned char c : path.string()) {
        if (std::isalnum(c) || c == '/' || c == '-' || c == '_' || c == '.' || c == '~') {
            url += static_cast<char>(c);
        } else {
            url += '%';
            url += kHex[c >> 4];
            url += kHex[c & 15];
        }
    }
    return url;
}

bool open_with_desktop(const std::string& url, std::string* error) {
    if (SDL_OpenURL(url.c_str())) return true;
    if (error) *error = SDL_GetError();
    return false;
}

namespace {

struct Pick {
    Post post;
    std::function<void(fs::path)> done;
};

void SDLCALL picked(void* data, const char* const* files, int) {
    std::unique_ptr<Pick> pick(static_cast<Pick*>(data));
    const fs::path chosen = files && files[0] ? fs::path(files[0]) : fs::path();
    auto done = std::move(pick->done);
    pick->post([done, chosen] { done(chosen); });
}

void show(SDL_FileDialogType type, SDL_Window* window, const fs::path& start, const char* title, const char* accept,
          bool filters, Post post, std::function<void(fs::path)> done) {
    static const SDL_DialogFileFilter kFilters[] = {{"Wii U game archive (.wua)", "wua"}, {"All files", "*"}};
    const SDL_PropertiesID props = SDL_CreateProperties();
    SDL_SetPointerProperty(props, SDL_PROP_FILE_DIALOG_WINDOW_POINTER, window);
    if (filters) {
        SDL_SetPointerProperty(props, SDL_PROP_FILE_DIALOG_FILTERS_POINTER, const_cast<SDL_DialogFileFilter*>(kFilters));
        SDL_SetNumberProperty(props, SDL_PROP_FILE_DIALOG_NFILTERS_NUMBER, 2);
    }
    const std::string location = start.string();
    if (!location.empty()) SDL_SetStringProperty(props, SDL_PROP_FILE_DIALOG_LOCATION_STRING, location.c_str());
    SDL_SetStringProperty(props, SDL_PROP_FILE_DIALOG_TITLE_STRING, title);
    if (accept) SDL_SetStringProperty(props, SDL_PROP_FILE_DIALOG_ACCEPT_STRING, accept);
    SDL_ShowFileDialogWithProperties(type, picked, new Pick{std::move(post), std::move(done)}, props);
    SDL_DestroyProperties(props);
}

} // namespace

void system_pick_game(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done) {
    show(SDL_FILEDIALOG_OPENFILE, window, start, "Choose the game's .wua", nullptr, true, std::move(post),
         std::move(done));
}

void system_pick_folder(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done) {
    show(SDL_FILEDIALOG_OPENFOLDER, window, start, "Choose where to install Tekken Tag Tournament 2", "Install Here",
         false, std::move(post), std::move(done));
}

} // namespace launcher::app
