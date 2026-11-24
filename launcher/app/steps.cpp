#include "steps.h"

#include "protocol.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>

namespace launcher::app {

namespace {

// The builder's steps (core/protocol.cpp's table: the same ids and, when the builder gives no words, these).
struct Known {
    const char* id;
    const char* name;
    const char* text;
};
constexpr Known kSteps[] = {{"check", "Checking", "Checking the game"},
                            {"extract", "Extracting", "Reading the game's code"},
                            {"recompile", "Recompiling", "Translating the game's code"},
                            {"compile", "Compiling", "Compiling the game program"},
                            {"link", "Linking", "Linking the game program"},
                            {"copy", "Copying", "Copying the game"},
                            {"finish", "Finishing", "Finishing"}};

std::string capitalised(std::string s) {
    if (!s.empty() && s[0] >= 'a' && s[0] <= 'z') s[0] = static_cast<char>(s[0] - 'a' + 'A');
    return s;
}

} // namespace

std::vector<StepLine> build_steps(const std::vector<std::string>& log, bool ended, bool ok) {
    std::vector<StepLine> steps;
    for (const Known& k : kSteps) steps.push_back({k.id, k.name, k.text, StepLine::State::kPending, 0, {}});
    int at = -1;
    for (const std::string& text : log) {
        const Line l = parse_line(text);
        if (l.kind == Line::Kind::kStep) {
            int found = -1;
            for (size_t i = 0; i < steps.size(); ++i)
                if (steps[i].id == l.word) found = static_cast<int>(i);
            if (found < 0) {
                steps.push_back({l.word, capitalised(l.word), l.text.empty() ? capitalised(l.word) : l.text,
                                 StepLine::State::kPending, 0, {}});
                found = static_cast<int>(steps.size()) - 1;
            }
            if (!l.text.empty()) steps[static_cast<size_t>(found)].text = l.text;
            // Steps before it are done (the builder skips some: an update has no copy of the game).
            for (int i = 0; i < found; ++i) {
                steps[static_cast<size_t>(i)].state = StepLine::State::kDone;
                steps[static_cast<size_t>(i)].fraction = 1;
            }
            at = found;
            steps[static_cast<size_t>(found)].state = StepLine::State::kCurrent;
            steps[static_cast<size_t>(found)].fraction = 0;
            steps[static_cast<size_t>(found)].count.clear();
        } else if (l.kind == Line::Kind::kProgress && at >= 0 && l.total > 0) {
            StepLine& s = steps[static_cast<size_t>(at)];
            s.fraction = std::min(1.0, static_cast<double>(l.done) / static_cast<double>(l.total));
            s.count = thousands(l.done) + " of " + thousands(l.total);
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
