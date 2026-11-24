#pragma once

// What the launcher asks of Linux (as the GTK app did; spec/linux_app.md 2.0, 8): the pieces it runs and their
// versions (the facts at start), the install and the game (Environment), the AppImage's files, monitors and key
// names from SDL, opening a folder or a page, the system's file pickers.

#include "model.h"

#include <SDL3/SDL.h>

#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace launcher::app {

namespace fs = std::filesystem;

// The facts before anything is asked (spec 2.0): kit, importer, Python, this build, the AppImage, the .wua given,
// Steam's last answer kept, the distribution, the saves. `banner`: the stderr line the GTK app printed.
model::Facts start_facts(const Places& places, const fs::path& program_dir, const fs::path& chosen_game,
                         std::optional<fs::path>* appimage, std::string* banner);
fs::path program_file(); // /proc/self/exe
fs::path home_folder();  // $HOME, else /

class LinuxEnvironment final : public model::Environment {
public:
    explicit LinuxEnvironment(Places places) : places_(std::move(places)) {}
    void look(model::Facts& facts) override;
    std::optional<fs::path> install_target(const fs::path& chosen, std::string* why) override;
    void write_started_record(const fs::path& folder, const fs::path& game) override;
    bool started(const fs::path& folder) override;
    void forget_started_record() override;
    std::string log_end(const fs::path& log) override;
    bool exists(const fs::path& path) override;
    fs::path build_work() override { return places_.build_work(); }

private:
    Places places_;
};

struct LinuxUpdateFiles final : model::RealUpdateFiles {
    std::string sha256(const fs::path& file) override;
};

// The key's name in the keyboard layout in use (SDL's, with video started); the US name when SDL has none.
std::string sdl_key_label(int usage);
// The desktop's monitors (height in pixels, refresh in millihertz).
std::vector<Monitor> sdl_monitors();

// Opens a folder in the file manager or a page in the browser (xdg-open through SDL: the portal under Flatpak).
bool open_with_desktop(const std::string& url, std::string* error);
std::string file_url(const fs::path& path);

// The system's picker (the desktop portal, zenity or kdialog), for mouse users: `done` gets the path, or "" when
// none was chosen, and is called on the UI thread by the app's queue (`post`).
using Post = std::function<void(std::function<void()>)>;
void system_pick_game(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done);
void system_pick_folder(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done);

} // namespace launcher::app
