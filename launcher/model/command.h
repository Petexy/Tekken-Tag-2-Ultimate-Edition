#pragma once

#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace launcher {
namespace fs = std::filesystem; // (as core's paths.h)
}

namespace launcher::model {

// A program to run: its arguments, the variables added to the launcher's
// environment, its folder (empty: the launcher's) and, on Windows, its log.
struct Command {
    std::vector<std::string> argv;
    std::map<std::string, std::string> env;
    fs::path cwd;
    fs::path log_file;
    // Windows' workers: created to cancel one (it stops what it started itself, then ends; the backend's Job
    // ends it for good once it has, C7). Empty: Cancel terminates the program.
    fs::path cancel_file;
    // How it runs (core/subprocess.h): a task's program or a question (its lines read; Cancel stops it), on its
    // own (the game, the updated launcher: it outlives this one; log_file is its output), or one of Windows' own
    // update workers (C3: in no job that ends with the launcher, never killed; Cancel only makes cancel_file).
    enum class Mode { kTask, kDetached, kSelfUpdate };
    Mode mode = Mode::kTask;
    bool operator==(const Command&) const = default;
};

} // namespace launcher::model
