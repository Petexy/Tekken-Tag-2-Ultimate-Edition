#pragma once

// What the launcher does first, before SDL or any window (ARCHITECTURE
// section 1, C6, C12, C15); the program calls begin() as the first thing in
// main() and ends at once when it says so.
//
//  1. --version anywhere: "ttt2-launcher <version>\n" on standard output, 0
//     (an update asks the new launcher this before putting it in place);
//     --help / -h: the usage, 0; Windows: --unpack DIR, the release .exe's
//     files into DIR and nothing else (tests), 0; an unknown option: an error
//     and the usage on standard error, 2.
//  2. TTT2_LAUNCHER_AFTER=<pid> (set by the launcher this one replaces): the
//     variable is removed (its programs must not see it) and that launcher is
//     waited for (Linux: until /proc says it is gone or a zombie, 10 s;
//     Windows: 60 s). The release .exe also deletes <its name>.old.exe (what
//     the update replaced).
//  3. One launcher per user (single_instance.h): a start while one runs hands
//     over its arguments (files made absolute) and activation token and ends
//     WITHOUT unpacking; when the running one's files differ from this .exe's,
//     the player is told to close it to switch. With TTT2_LAUNCHER_AFTER this
//     start never hands over. An old GTK launcher is asked to show itself.
//  4. Windows release .exe: its files into the files folder (payload.h), under
//     the mutex Local\TTT2UltimateLauncherFiles; TTT2_LAUNCHER_EXE names this
//     .exe and TTT2_LAUNCHER_UI_PID this process for the Python workers (the
//     update reopens the launcher after this pid ends, C3).
//
// Then the program runs, with Start::instance telling it of later starts.

#include "single_instance.h"

#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace launcher::startup {

namespace fs = std::filesystem;

struct Program {
    std::string name = "ttt2-launcher";
    std::string version;                             // --version prints "<name> <version>"
    std::string usage;                               // --help (standard output); after a usage error (standard error)
    std::vector<std::pair<std::string, int>> options; // the program's own options, each with how many values it takes
    bool unique = true;                              // false (test runs: --screenshot, test actions): no single instance
    std::string instance_name;                       // "" the launcher's (single_instance.h); tests give their own
    double after_seconds = -1;                       // < 0: the contract's waits (10 s Linux, 60 s Windows)
    std::function<void()> wake;                      // a later start arrived (listening thread): the app's event
    // A sentence for the player while there is no window. Default: standard error, and on Windows a message box.
    std::function<void(const std::string&)> tell;
};

struct Start {
    int exit = -1;                            // >= 0: end now with this code
    std::vector<std::string> args;            // the arguments (UTF-8, without the program's name)
    std::unique_ptr<SingleInstance> instance; // this user's launcher: later starts arrive here (none: not unique)
    fs::path files;                           // Windows release: the folder its files are in; "" otherwise
    std::string files_digest;                 // their digest ("" none)
    std::string note;                         // for the log: why it runs without being the one launcher, ...
};

// The program's arguments as UTF-8 (Windows: read from its wide command line; argv is in the ANSI code page).
std::vector<std::string> arguments(int argc, char** argv);

Start begin(const std::vector<std::string>& args, const Program& program);

// Pieces, also for tests.
// Waits until process `pid` is gone; true when it is (or never was).
bool wait_for_exit(int64_t pid, double seconds);
// The activation token a desktop gave this start (XDG_ACTIVATION_TOKEN, else DESKTOP_STARTUP_ID; "" none).
std::string activation_token();

} // namespace launcher::startup
