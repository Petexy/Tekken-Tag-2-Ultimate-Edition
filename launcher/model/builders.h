#pragma once

// The view builders: pure functions from the facts to what the player sees
// (view.h). Every text is the old launchers' (spec/linux_app.md, the GTK
// app's sources; Windows-only parts from launcher/windows/window.py), and
// the goldens (tests/golden) hold them to it.

#include "facts.h"
#include "view.h"

#include <string>

namespace launcher::model {

// "Another task is running: wait for it to end, then install." and the like:
// the refusal a disabled item would give, as one sentence for its why.
std::string refusal_sentence(const std::string& title, const std::string& why);

Banner banner_view(const Facts& facts);
Header header_view(const Facts& facts, bool in_settings);
GameView game_view(const Facts& facts);
// A path as the window shows it: the home folder ($HOME) as "~".
std::string shown_path(const fs::path& path);
CharactersView characters_view(const Facts& facts);
NoticeView notice_view(const Facts& facts);

// Dialogs.
struct UninstallChoice {
    bool saves = false, characters = false;
};
Dialog uninstall_view(const Facts& facts, const fs::path& saves, bool saves_custom, const UninstallChoice& choice);
Dialog remove_all_view(const Facts& facts, const std::string& game);
Dialog stop_and_quit_view(const std::string& task_title);
Dialog task_running_view(); // Windows: closing refused while a task runs
Dialog setup_confirm_view();
Dialog message_view(const std::string& title, const std::string& text); // a refusal while a task runs

// The command (or hint) that installs `packages` on this distribution: a
// command line, or a text when there is none (image_based_hint / fallback).
Line install_hint(const Distro& distro, const std::vector<Package>& packages, const std::string& what,
                  const char* fallback);

} // namespace launcher::model
