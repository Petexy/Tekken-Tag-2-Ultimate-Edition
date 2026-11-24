#include "steps.h"

#include "protocol.h"

#include <algorithm>

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
