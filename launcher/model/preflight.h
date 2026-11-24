#pragma once

// Before an install (Linux): the game file, the processor, a C++ compiler and
// the free space, each a Check with what to do (game.cpp's run_checks), and
// the game's end when it stopped with an error (stopped_text). What is
// looked at comes through a Probe: the PC's (SystemProbe), or a test's.

#include "facts.h"

#include <optional>
#include <string>
#include <vector>

namespace launcher::model {

inline constexpr uint64_t kGameBytes = 16'200'000'000;
inline constexpr uint64_t kBuildBytes = 3'000'000'000;

struct Probe {
    virtual ~Probe() = default;
    virtual bool exists(const fs::path& path) = 0; // a file or a folder
    virtual std::vector<std::string> missing_cpu_features() = 0;
    virtual std::optional<Compiler> find_compiler(std::string* why) = 0;
    virtual Distro distro() = 0;
    virtual std::optional<uint64_t> free_space(const fs::path& folder) = 0;
    virtual uint64_t file_system(const fs::path& folder) = 0;
    virtual uint64_t size_of(const fs::path& folder) = 0;
};

struct SystemProbe final : Probe {
    bool exists(const fs::path& path) override;
    std::vector<std::string> missing_cpu_features() override { return launcher::missing_cpu_features(); }
    std::optional<Compiler> find_compiler(std::string* why) override { return launcher::find_compiler(why); }
    Distro distro() override { return this_distro(); }
    std::optional<uint64_t> free_space(const fs::path& folder) override { return launcher::free_space(folder); }
    uint64_t file_system(const fs::path& folder) override { return launcher::file_system(folder); }
    uint64_t size_of(const fs::path& folder) override { return launcher::size_of(folder); }
};

// The checks for installing `game` into `folder`, building in `work` (run off the UI thread: it may read disks).
std::vector<Check> run_checks(const fs::path& game, const fs::path& folder, const fs::path& work, Probe& probe);
// The first check that fails, as "<title>: <detail>" (the install test action's answer); empty when none.
std::string failed_check(const std::vector<Check>& checks);

// The game stopped with an error: the code, its last lines (from the end of its log) and where all it wrote is.
std::string stopped_text(int code, const std::string& log_end, const fs::path& log, bool log_there);

} // namespace launcher::model
