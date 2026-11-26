#include "preflight.h"
#include "utf8_path.h"

#include "protocol.h"

#include <algorithm>
#include <cctype>

namespace launcher::model {

std::vector<Check> run_checks(const fs::path& game, const fs::path& folder, const fs::path& work, Probe& probe) {
    std::vector<Check> checks;
    const std::string game_title = tr("preflight.game", "Game");
    if (probe.exists(game))
        checks.push_back({true, game_title, path_utf8(game.filename()), {}});
    else
        checks.push_back({false, game_title, tr("preflight.no_game", "{path} does not exist", {{"path", path_utf8(game)}}), {}});

    const auto missing = probe.missing_cpu_features();
    const std::string processor = tr("preflight.processor", "Processor");
    if (missing.empty()) {
        checks.push_back({true, processor, tr("preflight.processor_ok", "Has what the game program is built for (x86-64-v3)"), {}});
    } else {
        std::string names;
        for (size_t i = 0; i < missing.size() && i < 6; ++i) names += (i ? ", " : "") + missing[i];
        checks.push_back({false, processor,
                          missing.size() > 6
                              ? tr("preflight.processor_lacks_more",
                                   "Lacks {features} and more: the game program needs an x86-64-v3 processor (Intel "
                                   "Haswell, AMD Excavator or newer)",
                                   {{"features", names}})
                              : tr("preflight.processor_lacks",
                                   "Lacks {features}: the game program needs an x86-64-v3 processor (Intel Haswell, AMD "
                                   "Excavator or newer)",
                                   {{"features", names}}),
                          {}});
    }

    std::string why;
    const std::string compiler_title = tr("preflight.compiler", "C++ compiler");
    if (const auto compiler = probe.find_compiler(&why)) {
        checks.push_back({true, compiler_title, compiler->name + " (" + path_utf8(compiler->path) + ")", {}});
    } else {
        const Distro distro = probe.distro();
        const std::string command = install_command(distro, {Package::kCompiler});
        const i18n::Args args = {{"why", i18n::capitalized(why)}};
        if (image_based(distro))
            why = tr("preflight.compiler_image", "{why}. The game program is compiled on this PC. {hint}",
                     {{"why", i18n::capitalized(why)}, {"hint", image_based_hint("Clang (or GCC 15 or newer)")}});
        else if (command.empty())
            why = tr("preflight.compiler_packages",
                     "{why}. The game program is compiled on this PC: install Clang (or GCC 15 or newer) with your "
                     "distribution's packages.",
                     args);
        else
            why = tr("preflight.compiler_command", "{why}. The game program is compiled on this PC: install Clang with",
                     args);
        checks.push_back({false, compiler_title, why, command});
    }

    // Space for the game (what is not copied yet) and for building, on one
    // file system or two.
    uint64_t needed = kGameBytes - std::min(kGameBytes - 300'000'000, probe.size_of(folder / "game"));
    const bool together = probe.file_system(folder) == probe.file_system(work);
    if (together) needed += kBuildBytes;
    const auto space = [&](const fs::path& where, uint64_t bytes, const std::string& title, const std::string& what) {
        const auto free = probe.free_space(where);
        if (!free) return Check{true, title, tr("preflight.space_unknown", "Unknown for {path}", {{"path", path_utf8(where)}}), {}};
        const i18n::Args args = {{"free", gigabytes(*free)}, {"needed", gigabytes(bytes)}, {"what", what}};
        return Check{*free >= bytes,
                     title,
                     *free >= bytes ? tr("preflight.space", "{free} free, about {needed} needed {what}", args)
                                    : tr("preflight.space_short",
                                         "{free} free, about {needed} needed {what}: make room on that disk, or choose a "
                                         "folder on another",
                                         args),
                     {}};
    };
    checks.push_back(space(folder, needed, tr("preflight.free_space", "Free space"),
                           together ? tr("preflight.for_both", "(the game, and building its program)")
                                    : tr("preflight.for_game", "(the game)")));
    if (!together)
        checks.push_back(space(work, kBuildBytes, tr("preflight.free_space_building", "Free space for building"),
                               tr("preflight.in_folder", "in {path}", {{"path", path_utf8(work)}})));
    return checks;
}

std::string failed_check(const std::vector<Check>& checks) {
    for (const Check& c : checks) {
        if (!c.ok) return tr("common.title_detail", "{title}: {detail}", {{"title", c.title}, {"detail", c.detail}});
    }
    return {};
}

std::string stopped_text(int code, const std::string& log_end, const fs::path& log, bool log_there) {
    const std::vector<std::string> said = last_words(log_end, 3);
    std::string text = said.empty() ? tr("preflight.game_stopped", "The game stopped with an error (exit code {code}).",
                                         {{"code", code}})
                                    : tr("preflight.game_stopped_lines",
                                         "The game stopped with an error (exit code {code}). Its last lines:",
                                         {{"code", code}});
    for (const std::string& line : said) text += "\n" + line;
    if (log_there) text += "\n" + tr("preflight.all_in_log", "All it wrote is in {path}.", {{"path", path_utf8(log)}});
    return text;
}

} // namespace launcher::model
