#pragma once

// Everything the launcher knows, as plain data: the model's input. The
// backends fill it (Linux: launcher/core directly; Windows: `main.py --query`
// answers, which are facts only, never sentences: see WindowsState), the
// controllers keep it up to date, and the view builders (views.h) read it to
// say what the player sees. Nothing here draws, starts a process or reads a
// file.

#include "display.h"
#include "keymap.h"
#include "paths.h"
#include "release.h"
#include "status.h"
#include "system.h"

#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace launcher::model {

// ---------------------------------------------------------------- the OS

// The tasks the launcher runs, one at a time. Linux's and Windows' share
// what both do (kImport, kRemove, kShaders, kUpdate: the game program built
// again, Windows' "upgrade" worker); the rest exists on one OS only.
enum class TaskKind {
    kInstall,        // Linux: ttt2-build install (after the preflight)
    kUpdate,         // the game program built again (Linux ttt2-build update, Windows worker "upgrade")
    kImport,         // characters added or updated
    kRemove,         // characters removed
    kUninstall,      // Linux: in-process, no Cancel
    kLauncherUpdate, // the launcher's own update (AppImage, or the Windows worker "launcher")
    kLauncherFiles,  // Windows: a test build's files from its branch (worker "files")
    kPackages,       // Linux: numpy and Pillow downloaded
    kShaders,        // the game's --precompile before Play
    kSetup,          // Windows: Set Up Game (worker "setup")
    kBuild,          // Windows: More > Build / Rebuild
    kInstallSource,  // Windows: More > Install from Wii U Source (worker "install")
    kUpdateInstalled,// Windows: More > Update Installed Game (worker "update")
    kBootstrap,      // Windows: the first start's "Getting the launcher ready"
    kRefusal,        // no task: a refusal shown in the task panel (as a failed one)
};
const char* task_kind_name(TaskKind kind); // "install", ... (the Windows worker's name where there is one)

// What closing the window does while a task runs (spec linux 2.12, windows 1.4).
enum class ClosePolicy {
    kAskStopAndQuit, // Linux: "Stop and quit?" (an uninstall or a stopping task: the window closes once it ends)
    kRefuse,         // Windows: "Task running" (cleaning up and logging must finish), except while the new
                     // launcher opens after an update
};

// What exists on this OS (U1): the views show only what the caps allow; the
// rules are the same on both.
struct Caps {
    bool windows = false;
    // Linux: Install… (choosers) + the preflight checks + Resume of an unfinished install + Installing.
    bool install_flow = false;
    // Windows: Set Up Game… (choosers + its confirmation), Set Up Again… in More.
    bool setup_game = false;
    bool uninstall = false;          // Linux: Uninstall… and its dialog
    bool more_menu = false;          // Windows: More (Build / Rebuild, Install from Wii U Source, ... logs)
    bool folders = false;            // Windows: Settings > Folders
    bool performance_preset = false; // Windows: Settings > Game > Performance "Use"
    bool task_log_file = false;      // Windows: the task panel's Open Log (a log file per task)
    // Linux: the Missing row (gamescope, pactl, MinGW, a C compiler, numpy/Pillow with Download and the
    // package manager's command). Windows: the worker fetches numpy/Pillow/compiler itself; nothing listed.
    bool prerequisites_listed = false;
    bool packages_download = false;  // Linux: Download of numpy and Pillow (get_python_packages.py)
    bool game_error_report = false;  // Linux: "The game stopped with an error (exit code N)..." (Windows: the log)
    bool game_outside = false;       // Linux: a game started outside the launcher is seen (/proc)
    bool branch_updates = false;     // Windows: a test build's files from its branch ("Newer changes are on X")
    std::set<TaskKind> cancellable;  // the tasks whose Cancel works
    ClosePolicy close_policy = ClosePolicy::kAskStopAndQuit;
    // The banner's note: "native Linux program" / "native Windows program".
    const char* platform_name = "Linux";

    static Caps linux_caps();
    static Caps windows_caps();
};

// ---------------------------------------------------------------- the facts

enum class OwnedState { kUnknown, kChecking, kKnown, kFailed };

// Steam's answer to which DLC the account owns (launcher.py owned), kept
// between asks (and in Places::owned_cache between starts).
struct Owned {
    OwnedState state = OwnedState::kUnknown; // asking since Steam last started: not yet, under way, done, failed
    std::map<std::string, bool> answer;      // the last answer: this time's, or the one kept from before
    bool has_answer = false;
    std::string error;                       // why asking failed
    std::map<std::string, std::string> errors; // this time's: each game Steam could not be asked through, why
};

// One thing checked before an install (Linux): what, how it is, and the
// command that installs what is missing.
struct Check {
    bool ok = true;
    std::string title, detail, command;
};

struct Preflight {
    fs::path game, folder;
    bool running = false;
    std::vector<Check> checks;
};

// The task that runs (or none), as far as the views need it.
struct TaskFacts {
    TaskKind kind = TaskKind::kRefusal;
    std::string title; // "Adding Kazumi Mishima"
    bool cancelled = false;
};

// Windows only: what `main.py --query state` answers (facts, never
// sentences: U2). The backend turns its JSON into this; everything the
// player reads is worded by the model.
//   {"protocol": 1, "version": "0.8.0", "files_id": "0.8.0 <40 hex>", "exe": path|null, "commit": hex|null,
//    "branch": name|null, "root", "build", "config": paths,
//    "settings": {"source","title","install","data","packs","saves","tools"},
//    "installed": folder|null, "installed_by": files id|"", "icon": path|null, "logs": path, "latest_log": path|null,
//    "display_file", "keyboard_file": paths, "play": {"argv":[...], "cwd", "env":{...}, "log"} | {"problem": code},
//    "data_problem": ""|"name" (the data folder is not named TTT2Ultimate),
//    "cannot_replace": ""|<the OS's reason, raw>}
// Ids ("0.8.0 <sha>") are given to the model as Facts::game_built / this_build in the kit's form
// ("0.8.0-<sha>"), so that the Linux rules (built_older, update ready) apply unchanged.
struct WindowsState {
    std::string branch;                 // a test build's branch (not main), empty otherwise
    std::string commit;                 // this build's commit (40 hex), empty when not known (project ZIP)
    std::map<std::string, std::string> folders; // Settings > Folders: source, title, install, data, packs, saves, tools
    fs::path logs, latest_log;          // <data>/logs, and its newest *.log (empty: none)
    // Why Play cannot start the game: "" (it can), "exe" (the installed game's program is missing),
    // "source" (a development build without its Wii U source).
    std::string play_problem;
    std::string data_problem;           // "" or "name": the data folder does not end in TTT2Ultimate
    std::string cannot_replace;         // why the .exe's folder cannot be written to (the OS's words), "" when it can
};

// Windows only: what `--query check --action X` answers before a task
// starts, as a code and its raw values (the model says the sentence).
struct SetupProblem {
    // "" (none), "inputs" (no source or install folder), "tools_folder" (no build-windows-tools),
    // "installer_letters" (what, letters, path: letters the installer cannot be given in the ANSI code page),
    // "tools_letters" (what, letters, path: non-ASCII project/tools folder), "project_length" (path),
    // "tools_length" (path), "no_build" (Build the Windows game first), "no_install" (no complete installation),
    // "no_paths" (no source and destination), "no_fighters", "title" (no usable extracted title)
    std::string code;
    std::string what, letters, path;
};

// The launcher's own settings (launcher.ini beside display.ini): new.
struct LauncherSettings {
    bool sounds = false;        // U17: off by default
    bool reduce_motion = false; // U9 (the app sets it from the OS where readable, until chosen)
    int text_size = 100;        // U6: percent (kTextSizes)
    bool operator==(const LauncherSettings&) const = default;
};

inline constexpr int kTextSizes[] = {100, 125, 150};

struct Facts {
    Caps caps = Caps::linux_caps();
    std::string launcher_version; // this launcher's ("0.8.0")

    // The pieces (Linux: find_kit/find_importer/find_python; Windows: the files folder's).
    fs::path kit, importer, python;
    bool builder = false;     // <kit>/bin/ttt2-build exists (Linux) / the build tools can be made (Windows: true)
    std::string this_build;   // kit_version ("0.8.0-1cab8c68f39b"); Windows: files_id in that form
    std::string build_commit; // this build's commit, empty when not known

    // The install.
    Install install;           // state, folder, the unfinished install's .wua
    std::string game_built;    // what built the installed program (built_version / installed_by), empty: unknown
    bool icon = false;         // <folder>/icon.png is there (the banner's)
    fs::path chosen_game;      // a .wua chosen or given (Linux: shown in the card)
    std::optional<Preflight> preflight;
    fs::path installing;       // the folder the install that runs goes to
    bool game_running = false; // the installed program runs (started here or elsewhere)
    bool game_started_here = false;
    std::string game_error;    // why the game could not start or stopped with an error (worded by the model)
    Distro distro;             // for install hints (Linux)
    fs::path saves;            // the saves folder (Places::saves), the uninstall dialog's
    bool saves_custom = false; // ... not the default one ($TTT2_SAVE_DIR): only the game's saves in it go

    // The importer's view of the PC.
    std::optional<ImporterStatus> status;
    std::string status_error;
    bool status_loading = false;
    Owned owned;
    std::map<std::string, bool> outfits; // the outfit boxes clicked, by character
    bool dlc_expanded = false;

    std::optional<TaskFacts> task;           // the task that runs
    std::optional<MainNews> main_news;       // what main (or a test build's branch) has beyond this build
    std::optional<Release> newer;            // a newer release GitHub named
    bool self_update = false;                // AppImage (Linux) / release .exe (Windows): the launcher updates itself
    bool custom_releases = false;            // TTT2_LAUNCHER_RELEASES set (tests): What's New for any page
    bool custom_github = false;              // TTT2_LAUNCHER_GITHUB set (tests)

    WindowsState windows;                    // (Windows only)
};

} // namespace launcher::model
