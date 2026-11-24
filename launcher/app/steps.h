#pragma once

// The install's steps as the task screen lists them (no SDL): each of the builder's steps (check, extract,
// recompile, compile, link, copy, finish) with its own part done, from the task's log (the builder's @step and
// @progress lines, which the task runner keeps as they came).

#include <string>
#include <vector>

namespace launcher::app {

struct StepLine {
    enum class State { kPending, kCurrent, kDone, kFailed };
    std::string id, name; // "compile", "Compiling" (one word, as the list shows it)
    std::string text;     // the builder's words for it ("Compiling the game's code"), else a longer name
    State state = State::kPending;
    double fraction = 0;  // of this step
    std::string count;    // "1,705 of 2,310", "" when none
};

// `ended`: the task is over (`ok`: it succeeded: every step done; else the current one failed, or stopped).
std::vector<StepLine> build_steps(const std::vector<std::string>& log, bool ended, bool ok);
// The step the task is at (or stopped at), 1-based; 0 when none began.
int current_step(const std::vector<StepLine>& steps);

} // namespace launcher::app

namespace launcher::app {

// Windows' first start (C9): how far "Start Ultimate Launcher.cmd --check" is, from its log
// (local\windows-bootstrap.log: its "@step <id> <text>" lines since the last "@step check", curl's progress bar).
struct BootstrapProgress {
    std::string step;      // "check", "download", "verify", "unpack", "ready" ("" none yet)
    std::string text;      // its words ("Downloading Python for the launcher")
    double fraction = -1;  // the whole first start's part done, -1 when not known
    double download = -1;  // the download's own part (curl's last percentage), -1 when none
};
BootstrapProgress bootstrap_progress(const std::string& log);

} // namespace launcher::app
