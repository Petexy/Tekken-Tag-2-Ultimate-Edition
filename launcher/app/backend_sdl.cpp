// What the launcher asks of the OS through SDL, the same on Linux and Windows (backend.h).

#include "backend.h"
#include "utf8_path.h"
#include "i18n.h"

#include "keymap.h"
#include "settings.h"

#include <cctype>
#include <cmath>
#include <memory>

namespace launcher::app {

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
#ifdef _WIN32
    // (file:///C:/Users/...: forward slashes, the drive's colon kept; a share \\host\x is file://host/x.)
    const std::u8string u8 = path.generic_u8string();
    std::string text(u8.begin(), u8.end());
    std::string url = "file:///";
    if (text.starts_with("//")) {
        url = "file://";
        text.erase(0, 2);
    }
    const size_t drive = text.size() > 1 && text[1] == ':' ? 1 : std::string::npos;
#else
    const std::string text = path.string();
    std::string url = "file://";
    const size_t drive = std::string::npos;
#endif
    for (size_t i = 0; i < text.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(text[i]);
        if (std::isalnum(c) || c == '/' || c == '-' || c == '_' || c == '.' || c == '~' || i == drive) {
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
    const fs::path chosen = files && files[0] ? utf8_path(files[0]) : fs::path();
    auto done = std::move(pick->done);
    pick->post([done, chosen] { done(chosen); });
}

void show(SDL_FileDialogType type, SDL_Window* window, const fs::path& start, const char* title, const char* accept,
          bool filters, Post post, std::function<void(fs::path)> done) {
    // (SDL keeps the filters' pointers until the dialog ends: these stay, set again for each dialog.)
    static std::string archive, all;
    archive = launcher::i18n::tr("picker.filter_wua", "Wii U game archive (.wua)");
    all = launcher::i18n::tr("picker.filter_all", "All files");
    static SDL_DialogFileFilter kFilters[2];
    kFilters[0] = {archive.c_str(), "wua"};
    kFilters[1] = {all.c_str(), "*"};
    const SDL_PropertiesID props = SDL_CreateProperties();
    SDL_SetPointerProperty(props, SDL_PROP_FILE_DIALOG_WINDOW_POINTER, window);
    if (filters) {
        SDL_SetPointerProperty(props, SDL_PROP_FILE_DIALOG_FILTERS_POINTER, kFilters);
        SDL_SetNumberProperty(props, SDL_PROP_FILE_DIALOG_NFILTERS_NUMBER, 2);
    }
    const std::string location = path_utf8(start);
    if (!location.empty()) SDL_SetStringProperty(props, SDL_PROP_FILE_DIALOG_LOCATION_STRING, location.c_str());
    SDL_SetStringProperty(props, SDL_PROP_FILE_DIALOG_TITLE_STRING, title);
    if (accept) SDL_SetStringProperty(props, SDL_PROP_FILE_DIALOG_ACCEPT_STRING, accept);
    SDL_ShowFileDialogWithProperties(type, picked, new Pick{std::move(post), std::move(done)}, props);
    SDL_DestroyProperties(props);
}

} // namespace

void system_pick_game(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done) {
    const std::string title = launcher::i18n::tr("picker.choose_wua_title", "Choose the game's .wua");
    show(SDL_FILEDIALOG_OPENFILE, window, start, title.c_str(), nullptr, true, std::move(post), std::move(done));
}

void system_pick_folder(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done) {
    const std::string title = launcher::i18n::tr("picker.where_title", "Choose where to install {game}",
                                                 {{"game", "Tekken Tag Tournament 2"}});
    const std::string accept = launcher::i18n::tr("picker.install_here", "Install Here");
    show(SDL_FILEDIALOG_OPENFOLDER, window, start, title.c_str(), accept.c_str(), false, std::move(post),
         std::move(done));
}

} // namespace launcher::app
