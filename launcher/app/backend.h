#pragma once

// What the launcher asks of the OS on any of them (backend_sdl.cpp, through SDL): key names, monitors, opening a
// folder or a page, the system's file pickers; and per OS (backend_linux.cpp / backend_windows.cpp) this program's
// file and the home folder. The rest of each OS's part: backend_linux.h, backend_windows.h.

#include "model.h"

#include <SDL3/SDL.h>

#include <filesystem>
#include <functional>
#include <string>
#include <vector>

namespace launcher::app {

namespace fs = std::filesystem;

fs::path program_file(); // this program (Linux: /proc/self/exe; Windows: GetModuleFileNameW)
fs::path home_folder();  // Linux: $HOME, else /; Windows: %USERPROFILE%

// The key's name in the keyboard layout in use (SDL's, with video started); the US name when SDL has none.
std::string sdl_key_label(int usage);
// The desktop's monitors (height in pixels, refresh in millihertz).
std::vector<Monitor> sdl_monitors();

// Opens a folder in the file manager or a page in the browser (Linux: xdg-open through SDL, the portal under
// Flatpak; Windows: the shell).
bool open_with_desktop(const std::string& url, std::string* error);
std::string file_url(const fs::path& path);

// The system's picker (Linux: the desktop portal, zenity or kdialog; Windows: the common dialog), for mouse users:
// `done` gets the path, or "" when none was chosen, and is called on the UI thread by the app's queue (`post`).
using Post = std::function<void(std::function<void()>)>;
void system_pick_game(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done);
void system_pick_folder(SDL_Window* window, const fs::path& start, Post post, std::function<void(fs::path)> done);

} // namespace launcher::app
