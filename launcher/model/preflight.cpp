#include "preflight.h"

#include "protocol.h"

#include <algorithm>
#include <cctype>

namespace launcher::model {

std::vector<Check> run_checks(const fs::path& game, const fs::path& folder, const fs::path& work, Probe& probe) {
    std::vector<Check> checks;
    if (probe.exists(game))
        checks.push_back({true, "Game", game.filename().string(), {}});
    else
        checks.push_back({false, "Game", game.string() + " does not exist", {}});

    const auto missing = probe.missing_cpu_features();
    if (missing.empty()) {
        checks.push_back({true, "Processor", "Has what the game program is built for (x86-64-v3)", {}});
    } else {
        std::string names;
        for (size_t i = 0; i < missing.size() && i < 6; ++i) names += (i ? ", " : "") + missing[i];
        checks.push_back({false,
                          "Processor",
                          "Lacks " + names + (missing.size() > 6 ? " and more" : "") +
                              ": the game program needs an x86-64-v3 processor (Intel Haswell, AMD Excavator or newer)",
                          {}});
    }

    std::string why;
    if (const auto compiler = probe.find_compiler(&why)) {
        checks.push_back({true, "C++ compiler", compiler->name + " (" + compiler->path.string() + ")", {}});
    } else {
        const Distro distro = probe.distro();
        const std::string command = install_command(distro, {Package::kCompiler});
        if (!why.empty()) why[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(why[0])));
        why += ". The game program is compiled on this PC";
        if (image_based(distro))
            why += ". " + image_based_hint("Clang (or GCC 15 or newer)");
        else if (command.empty())
            why += ": install Clang (or GCC 15 or newer) with your distribution's packages.";
        else
            why += ": install Clang with";
        checks.push_back({false, "C++ compiler", why, command});
    }

    // Space for the game (what is not copied yet) and for building, on one
    // file system or two.
    uint64_t needed = kGameBytes - std::min(kGameBytes - 300'000'000, probe.size_of(folder / "game"));
    const bool together = probe.file_system(folder) == probe.file_system(work);
    if (together) needed += kBuildBytes;
    const auto space = [&](const fs::path& where, uint64_t bytes, const char* title, const std::string& what) {
        const auto free = probe.free_space(where);
        if (!free) return Check{true, title, "Unknown for " + where.string(), {}};
        return Check{*free >= bytes,
                     title,
                     gigabytes(*free) + " free, about " + gigabytes(bytes) + " needed " + what +
                         (*free >= bytes ? "" : ": make room on that disk, or choose a folder on another"),
                     {}};
    };
    checks.push_back(
        space(folder, needed, "Free space", together ? "(the game, and building its program)" : "(the game)"));
    if (!together) checks.push_back(space(work, kBuildBytes, "Free space for building", "in " + work.string()));
    return checks;
}

std::string failed_check(const std::vector<Check>& checks) {
    for (const Check& c : checks) {
        if (!c.ok) return c.title + ": " + c.detail;
    }
    return {};
}

std::string stopped_text(int code, const std::string& log_end, const fs::path& log, bool log_there) {
    std::string text = "The game stopped with an error (exit code " + std::to_string(code) + ").";
    const std::vector<std::string> said = last_words(log_end, 3);
    if (!said.empty()) text += " Its last lines:";
    for (const std::string& line : said) text += "\n" + line;
    if (log_there) text += "\nAll it wrote is in " + log.string() + ".";
    return text;
}

} // namespace launcher::model
