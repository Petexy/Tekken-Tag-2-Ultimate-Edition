#pragma once

// What the launcher asks of Windows (ARCHITECTURE 6, C8, C9): Python only where it already lives. The launcher's
// files (the release .exe's files folder, or the project a CMake build is in) hold launcher/windows/main.py, which
// answers `--query NAME` (one JSON object on its last line, launcher/backend/windows_backend.h) and runs the
// `--worker` tasks; the private Python is local\windows-tools\python-runtime. Its first start without that Python
// runs "Start Golden Fist Launcher.cmd --check" hidden, its progress read from local\windows-bootstrap.log (the .exe
// never downloads anything itself, C9). Natively here: display.ini, keyboard.ini, opening folders and pages, Play.

#include "backend.h"
#include "steps.h"
#include "windows_backend.h"

#include <functional>
#include <memory>
#include <optional>
#include <string>

namespace launcher::app {

// Where the launcher's files are and what runs them.
struct WindowsFiles {
    fs::path root;   // the launcher's files (main.py's project folder)
    fs::path build;  // root\build-windows-tools (main.py's --build-dir), or the --build-dir the launcher was given
    fs::path config; // the --config the launcher was given (main.py's launcher.json), "" main.py's own
    fs::path python; // TTT2_PYTHON, else the private Python (maybe not there yet), else one on PATH (a CMake build)
    bool release = false;       // the release .exe's files folder (then the private Python is gotten first)
    bool python_needed = false; // the private Python is not there yet: the first start's bootstrap runs first
    fs::path bootstrap_log() const { return root / "local" / "windows-bootstrap.log"; }
};
// The program's own folders (the source ZIP's bridge, launcher/windows/build_launcher.py, passes them): --files DIR
// (these files, no payload), --build-dir DIR and --config FILE (only when not the files' usual ones).
struct WindowsArgs {
    fs::path files, build, config;
};
// `release_files`: startup's Start::files ("" not a release .exe). Without it, --files, else the folder of this
// program or one above it that has launcher\windows\main.py (a CMake build:
// <project>\build-windows-tools\launcher\ttt2-launcher.exe).
WindowsFiles windows_files(const fs::path& release_files, const WindowsArgs& args = {});

// The facts before --query state answered: Windows' caps, this launcher's version, Python, the files.
model::Facts windows_start_facts(const WindowsFiles& files, const fs::path& chosen_game);

// The first `--query state` (main.py finds its own launcher.json: the answer then names it for every later one).
model::Command first_state_query(const WindowsFiles& files);
// "Start Golden Fist Launcher.cmd --check", hidden, in the files folder.
model::Command bootstrap_command(const WindowsFiles& files);

class WindowsEnvironment final : public model::Environment {
public:
    explicit WindowsEnvironment(fs::path build) : build_(std::move(build)) {}
    // (The install, what built it and its icon are --query state's: the app asks it again after each task.)
    void look(model::Facts&) override {}
    std::optional<fs::path> install_target(const fs::path& chosen, std::string*) override { return chosen; }
    void write_started_record(const fs::path&, const fs::path&) override {}
    bool started(const fs::path&) override { return false; }
    void forget_started_record() override {}
    std::string log_end(const fs::path& log) override;
    bool exists(const fs::path& path) override;
    fs::path build_work() override { return build_; }

private:
    fs::path build_;
};

// Getting ready before the window can show the launcher (the model needs --query state's folders and files):
// the first start's Python (C9), then the state, its protocol checked (C6: these files and this .exe must be the
// same version's).
class WindowsReady {
public:
    enum class Stage { kBootstrap, kState, kDone, kFailed };
    struct Failure {
        std::string title, text; // the player's words
        std::string detail;      // the raw reason, the last lines (for the blue side)
        fs::path log;            // a log to open ("" none)
        bool retry = true;       // Try Again helps (a protocol mismatch: start the launcher again instead)
    };

    WindowsReady(WindowsFiles files, model::Starter& starter) : files_(std::move(files)), starter_(starter) {}
    // The release .exe's own files written again ("" done, else why not): set for a release .exe's files. When the
    // state's protocol is another one (a test build's Update got files of a newer program, REVIEW2_compat #3), they
    // are put back once and the state asked again; restored() then says the other files' protocol.
    std::function<std::string()> restore_files;
    const std::string& restored() const { return restored_; }
    void start(double now);
    void tick(double now);
    void retry(double now) { start(now); }
    void cancel();

    Stage stage() const { return stage_; }
    const Failure& failure() const { return failure_; }
    const BootstrapProgress& progress() const { return progress_; }
    const backend::WindowsStateAnswer& answer() const { return *answer_; }
    const WindowsFiles& files() const { return files_; }

private:
    void run_state(double now);
    void fail(Failure f);

    WindowsFiles files_;
    model::Starter& starter_;
    Stage stage_ = Stage::kBootstrap;
    std::unique_ptr<model::Job> job_;
    std::string out_, err_;
    int code_ = -1;
    bool ended_ = false;
    double next_read_ = 0, since_ = 0;
    BootstrapProgress progress_;
    std::optional<backend::WindowsStateAnswer> answer_;
    Failure failure_;
    std::string restored_;
};

} // namespace launcher::app
