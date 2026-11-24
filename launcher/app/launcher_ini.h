#pragma once

// The launcher's own settings (Settings > Launcher: Sounds, Reduce motion, Button prompts, Text size) in
// launcher.ini beside the game's display.ini: "key=value" lines. What cannot be read keeps its default.

#include "facts.h"

#include <filesystem>
#include <string>

namespace launcher::app {

model::LauncherSettings read_launcher_ini(const std::filesystem::path& file);
bool write_launcher_ini(const std::filesystem::path& file, const model::LauncherSettings& settings,
                        std::string* error = nullptr);

} // namespace launcher::app
