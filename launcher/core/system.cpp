// The checks of the player's PC (see system.h).

#include "system.h"

#include "paths.h"

#include <fcntl.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/wait.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <map>
#include <set>
#include <sstream>

extern char** environ;

namespace launcher {
namespace {

int major_version(std::string_view version) {
    int major = 0;
    for (char c : version) {
        if (c < '0' || c > '9') break;
        major = major * 10 + (c - '0');
    }
    return major;
}

std::string version_of(const fs::path& compiler, const char* option) {
    std::string out = run_output({compiler.string(), option}).value_or("");
    while (!out.empty() && (out.back() == '\n' || out.back() == ' ')) out.pop_back();
    return out;
}

// The versions N of the programs "<prefix>N" in $PATH ("clang++-18" where
// clang-18 is installed without its unversioned links), newest first.
std::set<int, std::greater<>> versions(const std::string& prefix) {
    std::set<int, std::greater<>> found;
    const char* path = std::getenv("PATH");
    std::istringstream folders(path && *path ? path : "/usr/local/bin:/usr/bin:/bin");
    for (std::string folder; std::getline(folders, folder, ':');) {
        std::error_code ec;
        if (folder.empty()) continue;
        for (const auto& entry : fs::directory_iterator(folder, ec)) {
            const std::string name = entry.path().filename().string();
            if (name.size() > prefix.size() && name.starts_with(prefix) &&
                name.find_first_not_of("0123456789", prefix.size()) == std::string::npos) {
                found.insert(std::atoi(name.c_str() + prefix.size()));
            }
        }
    }
    return found;
}

// The nearest of the folder and its parents that exists.
fs::path existing(fs::path folder) {
    std::error_code ec;
    folder = normal(folder);
    while (folder.has_relative_path() && !fs::exists(folder, ec)) folder = folder.parent_path();
    return folder;
}

} // namespace

std::vector<std::string> missing_cpu_features() {
    std::ifstream in("/proc/cpuinfo");
    std::stringstream text;
    text << in.rdbuf();
    return missing_cpu_features(text.str());
}

std::optional<Compiler> find_compiler(std::string* why) {
    if (const char* cxx = std::getenv("CXX"); cxx && *cxx) {
        // (It may hold a launcher first: "ccache clang++".)
        std::istringstream words(cxx);
        std::string first;
        words >> first;
        if (const auto path = find_in_path(first)) return Compiler{*path, cxx};
        if (why) *why = "$CXX is " + std::string(cxx) + ", which is not installed";
        return std::nullopt;
    }
    // In the builder's order (launcher/builder/src/host.cpp): Clang, then
    // GCC, each by its plain name and then by its versioned ones.
    std::vector<std::string> names{"clang++"};
    for (const int v : versions("clang++-")) names.push_back("clang++-" + std::to_string(v));
    names.emplace_back("g++");
    for (const int v : versions("g++-")) names.push_back("g++-" + std::to_string(v));
    std::string too_old;
    for (const std::string& name : names) {
        const auto program = find_in_path(name);
        if (!program) continue;
        const bool clang = name.starts_with("clang");
        const int needed = clang ? 13 : 15;
        const std::string version = version_of(*program, clang ? "-dumpversion" : "-dumpfullversion");
        if (major_version(version) >= needed) return Compiler{*program, name + " " + version};
        if (too_old.empty()) {
            too_old = name + " " + version + " is too old (" + std::to_string(needed) + " or newer is needed)";
        }
    }
    if (why) *why = too_old.empty() ? "no C++ compiler is installed" : too_old;
    return std::nullopt;
}

std::optional<uint64_t> free_space(const fs::path& folder) {
    struct statvfs s {};
    if (statvfs(existing(folder).c_str(), &s) != 0) return std::nullopt;
    return static_cast<uint64_t>(s.f_bavail) * s.f_frsize;
}

uint64_t file_system(const fs::path& folder) {
    struct stat s {};
    return stat(existing(folder).c_str(), &s) == 0 ? static_cast<uint64_t>(s.st_dev) : 0;
}

uint64_t size_of(const fs::path& folder) {
    uint64_t bytes = 0;
    std::error_code ec;
    for (auto it = fs::recursive_directory_iterator(folder, ec); !ec && it != fs::recursive_directory_iterator();
         it.increment(ec)) {
        if (it->is_regular_file(ec) && !it->is_symlink(ec)) bytes += it->file_size(ec);
    }
    return bytes;
}

Distro this_distro() {
    Distro d;
    for (const char* file : {"/etc/os-release", "/usr/lib/os-release"}) {
        std::ifstream in(file);
        if (!in) continue;
        std::stringstream text;
        text << in.rdbuf();
        d = parse_os_release(text.str());
        break;
    }
    std::error_code ec;
    d.ostree = fs::exists("/run/ostree-booted", ec);
    return d;
}

std::optional<std::string> run_output(const std::vector<std::string>& argv) {
    if (argv.empty()) return std::nullopt;
    int pipe_fds[2];
    if (::pipe2(pipe_fds, O_CLOEXEC) != 0) return std::nullopt;
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, pipe_fds[1], STDOUT_FILENO);
    posix_spawn_file_actions_addopen(&actions, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
    posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0);
    std::vector<char*> args;
    for (const std::string& a : argv) args.push_back(const_cast<char*>(a.c_str()));
    args.push_back(nullptr);
    pid_t pid = 0;
    const int spawned = posix_spawnp(&pid, args[0], &actions, nullptr, args.data(), environ);
    posix_spawn_file_actions_destroy(&actions);
    ::close(pipe_fds[1]);
    std::string out;
    if (spawned == 0) {
        char buffer[4096];
        for (;;) {
            const ssize_t n = ::read(pipe_fds[0], buffer, sizeof buffer);
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) break;
            out.append(buffer, static_cast<size_t>(n));
        }
    }
    ::close(pipe_fds[0]);
    if (spawned != 0) return std::nullopt;
    int status = 0;
    while (::waitpid(pid, &status, 0) < 0 && errno == EINTR) {
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) return std::nullopt;
    return out;
}

} // namespace launcher
