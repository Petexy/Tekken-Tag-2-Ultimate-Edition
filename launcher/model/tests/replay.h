#pragma once

// A golden case (tests/golden/<case>/case.json) played through the model as
// the old GTK app's test executor played it (spec linux 6.3): the same
// fixture answers from FakeStarter, the same steps, a dump at the same
// moments (00-start, each step, -running at half the progress, -stopping).

#include "fakes.h"
#include "golden.h"
#include "json.h"

#include <functional>
#include <map>
#include <string>
#include <vector>

namespace launcher::model::testing {

struct CaseRun {
    std::map<std::string, Dump> dumps; // "00-start", "01-add-kazumi-running", ...
    std::map<std::string, std::vector<Action>> actions; // each dump's focusable items
    std::vector<std::string> said;     // "@test <step> ok|failed <text>" for task steps
    std::vector<std::string> problems; // what the replay could not do
};

// The model of a replay and what it was given, for a test to go on with.
struct Harness {
    LauncherModel& model;
    FakeStarter& starter;
    FakeEnvironment& env;
    double& now;
    std::function<void()> settle; // every program's lines and end delivered, then a tick
    std::vector<Effect>& effects;  // what the model wanted done after programs ended (take_effects)
};

struct ReplayOptions {
    int steps = -1; // only the first n steps (-1: all)
    std::function<void(Harness&)> at_end; // after the steps
};

// `scratch`: a folder for display.ini and keyboard.ini.
CaseRun replay(const json::Value& c, const Caps& caps, const fs::path& scratch, const ReplayOptions& options = {});

// What the fixture's programs answer (launcher.py status/owned/main, import_character.py's steps, ...).
void fixture_answer(const json::Value& c, Run& run);

// JSON text of a parsed value (the fixture's answers as the stub printed them).
std::string to_json(const json::Value& v);

} // namespace launcher::model::testing
