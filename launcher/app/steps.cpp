#include "steps.h"

#include "i18n.h"
#include "protocol.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>

namespace launcher::app {

namespace {

using i18n::tr;

// The builder's steps (core/protocol.cpp's table: the same ids and, when the builder gives no words or the launcher's
// language is not English, these).
struct Known {
    const char* id;
    std::string name, text;
};
std::vector<Known> known_steps() {
    return {{"check", tr("step.check_short", "Checking"), tr("step.check", "Checking the game")},
            {"extract", tr("step.extract_short", "Extracting"), tr("step.extract", "Reading the game's code")},
            {"recompile", tr("step.recompile_short", "Recompiling"), tr("step.recompile", "Translating the game's code")},
            {"compile", tr("step.compile_short", "Compiling"), tr("step.compile", "Compiling the game program")},
            {"link", tr("step.link_short", "Linking"), tr("step.link", "Linking the game program")},
            {"copy", tr("step.copy_short", "Copying"), tr("step.copy", "Copying the game")},
            {"finish", tr("step.finish", "Finishing"), tr("step.finish", "Finishing")}};
}

} // namespace

std::vector<StepLine> build_steps(const std::vector<std::string>& log, bool ended, bool ok) {
    std::vector<StepLine> steps;
    const std::vector<Known> known = known_steps();
    for (const Known& k : known) steps.push_back({k.id, k.name, k.text, StepLine::State::kPending, 0, {}, {}});
    int at = -1;
    for (const std::string& text : log) {
        const Line l = parse_line(text);
        if (l.kind == Line::Kind::kStep) {
            int found = -1;
            for (size_t i = 0; i < steps.size(); ++i)
                if (steps[i].id == l.word) found = static_cast<int>(i);
            if (found < 0) {
                steps.push_back({l.word, i18n::capitalized(l.word), l.text.empty() ? i18n::capitalized(l.word) : l.text,
                                 StepLine::State::kPending, 0, {}, {}});
                found = static_cast<int>(steps.size()) - 1;
            }
            // (The builder's words are English: its own only when the launcher's language is; a worker's are in
            // the launcher's language already, for steps the launcher does not know.)
            if (!l.text.empty() && (i18n::english() || static_cast<size_t>(found) >= known.size()))
                steps[static_cast<size_t>(found)].text = l.text;
            // Steps before it are done (the builder skips some: an update has no copy of the game).
            for (int i = 0; i < found; ++i) {
                steps[static_cast<size_t>(i)].state = StepLine::State::kDone;
                steps[static_cast<size_t>(i)].fraction = 1;
            }
            at = found;
            steps[static_cast<size_t>(found)].state = StepLine::State::kCurrent;
            steps[static_cast<size_t>(found)].fraction = 0;
            steps[static_cast<size_t>(found)].count.clear();
            steps[static_cast<size_t>(found)].slash.clear();
        } else if (l.kind == Line::Kind::kProgress && at >= 0 && l.total > 0) {
            StepLine& s = steps[static_cast<size_t>(at)];
            s.fraction = std::min(1.0, static_cast<double>(l.done) / static_cast<double>(l.total));
            s.count = tr("progress.of", "{done} of {total}", {{"done", thousands(l.done)}, {"total", thousands(l.total)}});
            s.slash = thousands(l.done) + " / " + thousands(l.total);
        }
    }
    if (ended) {
        if (ok) {
            for (StepLine& s : steps) {
                s.state = StepLine::State::kDone;
                s.fraction = 1;
            }
        } else if (at >= 0) {
            steps[static_cast<size_t>(at)].state = StepLine::State::kFailed;
        }
    }
    return steps;
}

int current_step(const std::vector<StepLine>& steps) {
    int last = 0;
    for (size_t i = 0; i < steps.size(); ++i) {
        if (steps[i].state == StepLine::State::kCurrent || steps[i].state == StepLine::State::kFailed)
            return static_cast<int>(i) + 1;
        if (steps[i].state == StepLine::State::kDone) last = static_cast<int>(i) + 1;
    }
    return last;
}

} // namespace launcher::app

namespace launcher::app {

BootstrapProgress bootstrap_progress(const std::string& log) {
    BootstrapProgress p;
    const size_t start = log.rfind("@step check");
    if (start == std::string::npos) return p;
    // (Lines end in \n or \r\n; curl's bar rewrites its line with \r.)
    size_t at = start;
    while (at < log.size()) {
        size_t end = log.find_first_of("\r\n", at);
        if (end == std::string::npos) end = log.size();
        const std::string line = log.substr(at, end - at);
        at = end + 1;
        if (line.starts_with("@step ")) {
            const size_t sp = line.find(' ', 6);
            p.step = line.substr(6, sp == std::string::npos ? std::string::npos : sp - 6);
            p.text = sp == std::string::npos ? std::string() : line.substr(sp + 1);
            while (!p.text.empty() && (p.text.back() == ' ' || p.text.back() == '\t')) p.text.pop_back();
            continue;
        }
        if (p.step != "download") continue;
        // curl --progress-bar: "#####          12.3%"
        const size_t pct = line.rfind('%');
        if (pct == std::string::npos) continue;
        size_t b = pct;
        while (b > 0 && (std::isdigit(static_cast<unsigned char>(line[b - 1])) || line[b - 1] == '.' ||
                         line[b - 1] == ',')) --b;
        if (b == pct) continue;
        std::string number = line.substr(b, pct - b);
        std::replace(number.begin(), number.end(), ',', '.');
        const double v = std::atof(number.c_str());
        if (v >= 0 && v <= 100) p.download = v / 100;
    }
    // The download is most of it; checking and unpacking the rest.
    if (p.step == "check") p.fraction = 0;
    else if (p.step == "download") p.fraction = 0.05 + 0.75 * std::max(0.0, p.download);
    else if (p.step == "verify") p.fraction = 0.82;
    else if (p.step == "unpack") p.fraction = 0.88;
    else if (p.step == "ready") p.fraction = 1;
    return p;
}

} // namespace launcher::app
