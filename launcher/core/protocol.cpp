// The progress lines and the bar made of them (see protocol.h).

#include "protocol.h"

#include "i18n.h"

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdio>

namespace launcher {
namespace {

// The builder's steps in their order, with a share of the whole bar each
// (about the share of the time they take: compiling and copying the game's
// 16 GB are most of it).
struct BuildStep {
    const char* id;
    double weight;
};
constexpr std::array kBuildSteps = {
    BuildStep{"check", 1}, BuildStep{"extract", 2}, BuildStep{"recompile", 4}, BuildStep{"compile", 55},
    BuildStep{"link", 4},  BuildStep{"copy", 32},   BuildStep{"finish", 2},
};

// A build step's text in the launcher's language: the builder's own (English) only when the launcher's is English.
std::string build_step_text(std::string_view id, const std::string& said) {
    using i18n::tr;
    if (i18n::english() && !said.empty()) return said;
    if (id == "check") return tr("step.check", "Checking the game");
    if (id == "extract") return tr("step.extract", "Reading the game's code");
    if (id == "recompile") return tr("step.recompile", "Translating the game's code");
    if (id == "compile") return tr("step.compile", "Compiling the game program");
    if (id == "link") return tr("step.link", "Linking the game program");
    if (id == "copy") return tr("step.copy", "Copying the game");
    if (id == "finish") return tr("step.finish", "Finishing");
    return said.empty() ? std::string(id) : said;
}

// "{done} of {total}" with its unit, in the launcher's language.
std::string of_text(const std::string& done, const std::string& total) {
    return i18n::tr("progress.of", "{done} of {total}", {{"done", done}, {"total", total}});
}

// The share of the bar the fighters take; what they share comes last.
constexpr double kFighters = 0.95;

// The word at the start of `s`, and `s` after it and the spaces that follow.
std::string_view word(std::string_view& s) {
    const size_t space = std::min(s.find(' '), s.size());
    const std::string_view w = s.substr(0, space);
    s.remove_prefix(space);
    while (!s.empty() && s.front() == ' ') s.remove_prefix(1);
    return w;
}

bool number(std::string_view text, uint64_t& out) {
    const auto [end, ec] = std::from_chars(text.data(), text.data() + text.size(), out);
    return ec == std::errc() && end == text.data() + text.size();
}

// The game's reports every 10 s: frames per second, video memory, presentation, threads' CPU.
bool report(std::string_view line) {
    for (const std::string_view start : {"ttt2: present: ", "ttt2: gpu: video memory: ", "ttt2: cpu: ", "pacing: "}) {
        if (line.starts_with(start)) return true;
    }
    constexpr std::string_view gpu = "ttt2: gpu: "; // (its other lines are errors: "ttt2: gpu: cannot compile ...")
    return line.starts_with(gpu) && line.size() > gpu.size() && line[gpu.size()] >= '0' && line[gpu.size()] <= '9';
}

} // namespace

Line parse_line(std::string_view text) {
    while (!text.empty() && (text.back() == '\r' || text.back() == '\n')) text.remove_suffix(1);
    Line line;
    line.text = std::string(text);
    if (!text.starts_with('@')) return line;
    std::string_view rest = text.substr(1);
    const std::string_view w = word(rest);
    Line out;
    if (w == "step" && !rest.empty()) {
        out.kind = Line::Kind::kStep;
        out.word = std::string(word(rest));
        out.text = std::string(rest);
    } else if (w == "progress") {
        out.kind = Line::Kind::kProgress;
        if (!number(word(rest), out.done) || !number(word(rest), out.total)) return line;
    } else if (w == "folder" && !rest.empty()) {
        out.kind = Line::Kind::kFolder;
        out.text = std::string(rest);
    } else if (w == "error") {
        out.kind = Line::Kind::kError;
        out.text = std::string(rest);
    } else if (w == "done" && rest.empty()) {
        out.kind = Line::Kind::kDone;
    } else if (w == "ok" && rest.empty()) {
        out.kind = Line::Kind::kOk;
    } else if (w == "added" && !rest.empty()) {
        out.kind = Line::Kind::kAdded;
        out.word = std::string(word(rest));
    } else if (w == "removed" && !rest.empty()) {
        out.kind = Line::Kind::kRemoved;
        out.word = std::string(word(rest));
    } else if (w == "skipped" && !rest.empty()) {
        out.kind = Line::Kind::kSkipped;
        out.word = std::string(word(rest));
        out.text = std::string(rest);
    } else if (w == "stand-in" && !rest.empty()) {
        // (A Tekken 8 fighter added with a stand-in's moves, and why.)
        out.kind = Line::Kind::kStandIn;
        out.word = std::string(word(rest));
        out.text = std::string(rest);
    } else {
        return line;
    }
    return out;
}

std::string thousands(uint64_t n) {
    // (The group separator as the launcher's language writes it: a comma in English, a space in the others, a
    // no-break one so that a number stays on one line.)
    const std::string separator = i18n::english() || i18n::language() == i18n::kPseudo ? "," : "\u00A0";
    std::string digits = std::to_string(n), out;
    for (size_t i = 0; i < digits.size(); ++i) {
        if (i > 0 && (digits.size() - i) % 3 == 0) out += separator;
        out += digits[i];
    }
    return out;
}

std::string gigabytes(uint64_t bytes) {
    return i18n::tr("units.gb", "{amount} GB", {{"amount", i18n::decimal(static_cast<double>(bytes) / 1e9, 1)}});
}

std::string Progress::name(const std::string& fighter) const {
    const auto it = names_.find(fighter);
    return it != names_.end() ? it->second : fighter;
}

bool Progress::feed(const Line& line) {
    switch (line.kind) {
    case Line::Kind::kStep:
        if (kind_ == Kind::kBuild) build_step(line);
        else if (kind_ == Kind::kImport) import_step(line);
        else {
            step_ = line.word == "shaders" && (line.text.empty() || !i18n::english())
                        ? i18n::tr("model.preparing_shaders", "Preparing shaders")
                    : line.text.empty() ? line.word
                                        : line.text;
            detail_.clear();
            fraction_ = -1;
        }
        return true;
    case Line::Kind::kProgress:
        if (line.total == 0) return false;
        if (kind_ == Kind::kBuild) {
            const double part = static_cast<double>(std::min(line.done, line.total)) / static_cast<double>(line.total);
            if (step_weight_ > 0) fraction_ = step_start_ + step_weight_ * part;
            if (step_id_ == "copy") {
                detail_ = i18n::tr("progress.gb", "{done} of {total} GB",
                                   {{"done", i18n::decimal(static_cast<double>(line.done) / 1e9, 1)},
                                    {"total", i18n::decimal(static_cast<double>(line.total) / 1e9, 1)}});
            } else if (step_id_ == "compile") {
                detail_ = i18n::trn("progress.files", static_cast<long long>(line.total), "{done} of {total} file",
                                    "{done} of {total} files",
                                    {{"done", thousands(line.done)}, {"total", thousands(line.total)}});
            } else {
                detail_ = of_text(thousands(line.done), thousands(line.total));
            }
        } else if (kind_ == Kind::kDownload) {
            fraction_ = static_cast<double>(std::min(line.done, line.total)) / static_cast<double>(line.total);
            detail_ = i18n::tr("progress.mb", "{done} of {total} MB",
                               {{"done", i18n::decimal(static_cast<double>(line.done) / 1e6, 1)},
                                {"total", i18n::decimal(static_cast<double>(line.total) / 1e6, 1)}});
        } else {
            fraction_ = static_cast<double>(std::min(line.done, line.total)) / static_cast<double>(line.total);
            detail_ = of_text(thousands(line.done), thousands(line.total));
        }
        return true;
    case Line::Kind::kAdded:
        if (kind_ == Kind::kImport && step_weight_ > 0) {
            fraction_ = step_start_ + step_weight_;
            return true;
        }
        return false;
    case Line::Kind::kDone:
        fraction_ = 1;
        detail_.clear();
        return true;
    default: return false;
    }
}

void Progress::build_step(const Line& line) {
    step_id_ = line.word;
    detail_.clear();
    double start = 0, total = 0;
    for (const BuildStep& s : kBuildSteps) total += s.weight;
    for (const BuildStep& s : kBuildSteps) {
        if (line.word == s.id) {
            step_ = build_step_text(s.id, line.text);
            step_start_ = start / total;
            step_weight_ = s.weight / total;
            fraction_ = step_start_;
            return;
        }
        start += s.weight;
    }
    // A step this launcher does not know: the bar stays where it is.
    step_ = line.text.empty() ? line.word : line.text;
    step_weight_ = 0;
}

void Progress::import_step(const Line& line) {
    step_id_ = line.word;
    detail_.clear();
    step_weight_ = 0;
    if (line.word == "dump") {
        // Tekken 7 takes as long as it takes: no fraction.
        step_ = line.text.empty() ? i18n::tr("step.dump", "Saving the characters' moves from Tekken 7") : line.text;
        fraction_ = -1;
    } else if (line.word == "fighter") {
        std::string_view rest = line.text;
        const std::string fighter(word(rest));
        uint64_t i = 0, n = 0;
        step_ = i18n::tr("model.adding", "Adding {what}", {{"what", name(fighter)}});
        if (number(word(rest), i) && number(word(rest), n) && n > 0 && i >= 1 && i <= n) {
            step_start_ = kFighters * static_cast<double>(i - 1) / static_cast<double>(n);
            step_weight_ = kFighters / static_cast<double>(n);
            fraction_ = step_start_;
            if (n > 1) detail_ = of_text(std::to_string(i), std::to_string(n));
        }
    } else if (line.word == "shared") {
        step_ = line.text.empty() ? i18n::tr("step.shared", "Updating what the added characters share") : line.text;
        fraction_ = kFighters;
    } else {
        step_ = line.text.empty() ? line.word : line.text;
    }
}

std::vector<std::string> last_words(std::string_view output, size_t count) {
    std::vector<std::string> lines;
    while (!output.empty() && lines.size() < count) {
        const size_t start = output.rfind('\n');
        std::string_view line = output.substr(start == std::string_view::npos ? 0 : start + 1);
        output.remove_suffix(line.size() + (start == std::string_view::npos ? 0 : 1));
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.remove_suffix(1);
        if (line.empty() || line.front() == ' ' || line.front() == '\t' || line.starts_with("guest backtrace") ||
            report(line)) {
            continue;
        }
        lines.emplace(lines.begin(), line.substr(0, 300));
    }
    return lines;
}

} // namespace launcher
