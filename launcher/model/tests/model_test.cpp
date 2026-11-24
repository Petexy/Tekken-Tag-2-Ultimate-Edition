// model_test GOLDEN_DIR SCRATCH_DIR [--case NAME] [--write DIR]
//
// 1. Goldens: every case of GOLDEN_DIR (dumped from the old GTK app, see
//    golden/README.md) played through the model and compared, dump by dump,
//    with the intended differences of golden/INTENDED.md applied. --write
//    also writes the model's dumps (the same shape) for a look or a diff.
// 2. The same cases with Windows' caps: views build, every id is unique,
//    nothing Linux-only shows (no Tk goldens: see golden/README.md).
// 3. Unit tests of the controllers: tasks, keys, display.ini, the refresh
//    rules, the AppImage's update, preflight, activate(id).

#include "check.h"
#include "fakes.h"
#include "golden.h"
#include "replay.h"
#include "rules.h"
#include "status.h"
#include "units.h"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <functional>
#include <set>
#include <sstream>

using namespace launcher;
using namespace launcher::model;
using namespace launcher::model::testing;

namespace {

std::string read(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    std::stringstream s;
    s << in.rdbuf();
    return s.str();
}

// ---------------------------------------------------------------- intended differences (golden/INTENDED.md)

// I5 Ids the old app gave no element: new ones (U14).
const std::vector<std::string> kNewIds = {"refresh", "details", "uninstall-saves", "uninstall-characters",
                                          "uninstall-cancel", "uninstall-confirm"};

// What the model shows that the old app did not, or differently, on purpose: applied to the golden before
// comparing, each with its reason (INTENDED.md lists them).
// I4 A remove that was cancelled says calmly what is left (the old app gave the signal: "It was stopped:
// Terminated (code 143, see Details)").
const char* const kOldRemoveCancelled = "It was stopped: Terminated (code 143, see Details)";
const char* const kRemoveCancelled = "The characters removed before stay removed, the others are kept.";

std::string intended_said(std::string line) {
    const std::string old = std::string("Removing cancelled: ") + kOldRemoveCancelled;
    if (const size_t at = line.find(old); at != std::string::npos) {
        line.replace(at, old.size(), std::string("Removing cancelled: ") + kRemoveCancelled);
    }
    return line;
}

void intended(Dump& golden, const Dump& model) {
    {
        Section& task = golden["task"];
        for (size_t i = 0; i + 1 < task.size(); ++i) {
            if (task[i].text["t"] == "Removing cancelled" && task[i + 1].text["t"] == kOldRemoveCancelled) {
                task[i + 1].text["t"] = kRemoveCancelled;
            }
        }
        for (Element& e : task) {
            if (e.text.count("t") && e.text.at("t").empty()) e.text.erase("t");
        }
    }
    // I3 Play reads display.ini's "Prepare shaders before playing" when it is pressed (the old app used what
    // Settings last read, nothing before Settings opened): the shaders task's result where the old app had none.
    const Section& task = model.at("task");
    if (golden["task"].empty() && !task.empty() && task[0].text.count("t") && task[0].text.at("t") == "Shaders are ready") {
        golden["task"] = task;
    }
    // I1 Settings is always reachable (U17): a gear beside Install/Resume when the game is not installed.
    Section& game = golden["game"];
    for (size_t i = 0; i < game.size(); ++i) {
        const auto id = game[i].text.find("id");
        if (id == game[i].text.end() || (id->second != "install" && id->second != "resume")) continue;
        const bool there = i + 1 < game.size() && game[i + 1].text.count("id") && game[i + 1].text.at("id") == "settings";
        if (!there) {
            game.insert(game.begin() + static_cast<long>(i) + 1,
                        Element{"button", {{"id", "settings"}, {"icon", "ttt2-settings-symbolic"}, {"tip", "Settings"}},
                                {{"s", true}}});
        }
        break;
    }
    // I2 Settings has the launcher's own section (U6, U9, U17) after Keyboard.
    Section& settings = golden["settings"];
    if (!settings.empty()) {
        const auto add = [&](Element e) { settings.push_back(std::move(e)); };
        add({"label", {{"t", "Ultimate Launcher"}, {"tone", "heading"}}, {}});
        add({"label", {{"t", "How this launcher looks and sounds."}, {"tone", "dim"}}, {}});
        add({"label", {{"t", "Sounds"}}, {}});
        add({"label", {{"t", "Short sounds when moving between and choosing items."}, {"tone", "dim"}}, {}});
        add({"switch", {{"id", "sounds"}}, {{"on", false}, {"s", true}}});
        add({"label", {{"t", "Reduce motion"}}, {}});
        add({"label", {{"t", "No moving backgrounds, and pages change without sliding."}, {"tone", "dim"}}, {}});
        add({"switch", {{"id", "reduce-motion"}}, {{"on", false}, {"s", true}}});
        add({"label", {{"t", "Text size"}}, {}});
        add({"label", {{"t", "How large this launcher's text is."}, {"tone", "dim"}}, {}});
        add({"choice", {{"id", "text-size"}, {"t", "100 %"}}, {{"s", true}}});
    }
}

// ---------------------------------------------------------------- 1. goldens

void goldens(const fs::path& dir, const fs::path& scratch, const std::string& only, const fs::path& write) {
    int cases = 0, dumps = 0;
    for (const auto& entry : fs::directory_iterator(dir)) {
        if (!entry.is_directory() || !fs::exists(entry.path() / "case.json")) continue;
        const std::string name = entry.path().filename().string();
        if (!only.empty() && name != only) continue;
        current = "golden " + name;
        const auto c = json::parse(read(entry.path() / "case.json"));
        CHECK(c.has_value());
        if (!c) continue;
        ++cases;
        const CaseRun run = replay(*c, Caps::linux_caps(), scratch / name);
        for (const std::string& p : run.problems) {
            fail(__FILE__, __LINE__, p);
        }
        if (!write.empty()) {
            fs::create_directories(write / name);
            for (const auto& [shot, dump] : run.dumps) std::ofstream(write / name / (shot + ".json")) << dump_json(dump);
        }
        std::set<std::string> seen;
        for (const auto& file : fs::directory_iterator(entry.path() / "linux")) {
            if (file.path().extension() != ".json") continue;
            const std::string shot = file.path().stem().string();
            seen.insert(shot);
            std::string error;
            auto golden = parse_dump(read(file.path()), &error);
            if (!golden) {
                fail(__FILE__, __LINE__, shot + ": " + error);
                continue;
            }
            const auto made = run.dumps.find(shot);
            if (made == run.dumps.end()) {
                fail(__FILE__, __LINE__, "the model made no " + shot);
                continue;
            }
            ++dumps;
            intended(*golden, made->second);
            const auto diff = compare(*golden, made->second, kNewIds);
            if (!diff.empty()) {
                std::string text = shot + ":";
                for (const std::string& l : diff) text += "\n    " + l;
                fail(__FILE__, __LINE__, text);
            }
        }
        for (const auto& [shot, dump] : run.dumps) {
            if (!seen.count(shot)) {
                fail(__FILE__, __LINE__, "the old app made no " + shot);
            }
        }
        // The task steps' answers, as the old app's test executor said them.
        std::istringstream said(read(entry.path() / "linux/tests.txt"));
        std::vector<std::string> expected;
        for (std::string line; std::getline(said, line);) {
            for (const char* step : {"@test add:", "@test remove:", "@test update ", "@test play ", "@test get-packages ",
                                     "@test uninstall:"}) {
                if (line.starts_with(step) && !line.ends_with(" started")) expected.push_back(intended_said(line));
            }
        }
        CHECK_EQ(run.said.size(), expected.size());
        for (size_t i = 0; i < run.said.size() && i < expected.size(); ++i) CHECK_EQ(run.said[i], expected[i]);
    }
    std::printf("goldens: %d cases, %d dumps compared\n", cases, dumps);
    CHECK(only.empty() ? cases >= 30 : cases == 1);
}

// ---------------------------------------------------------------- 2. what every view keeps to (both OSes)

// Ids only one OS has (U1: the caps decide).
const std::vector<std::string> kLinuxOnly = {"install", "resume", "check-again", "preflight-cancel", "uninstall",
                                             "get-packages", "copy:"};
const std::vector<std::string> kWindowsOnly = {"more", "more:", "setup", "folder:", "save-folders", "performance",
                                               "open-keyboard-file", "open-log"};

bool listed(const std::string& id, const std::vector<std::string>& list) {
    return std::any_of(list.begin(), list.end(), [&](const std::string& l) {
        return l.ends_with(':') ? id.starts_with(l) : id == l;
    });
}

void invariants(const std::string& shot, const std::vector<Action>& actions, const Caps& caps) {
    std::set<std::string> ids;
    for (const Action& a : actions) {
        if (a.id.empty()) {
            fail(__FILE__, __LINE__, shot + ": an item without an id: " + a.label + " " + a.tooltip);
            continue;
        }
        if (!ids.insert(a.id).second) fail(__FILE__, __LINE__, shot + ": two items are " + a.id);
        if (listed(a.id, caps.windows ? kLinuxOnly : kWindowsOnly)) {
            fail(__FILE__, __LINE__, shot + ": " + a.id + " is not " + caps.platform_name + "'s");
        }
        // U7: a disabled item stays, and says why (in the blue side: describe.why).
        if (!a.enabled && a.describe.why.empty()) fail(__FILE__, __LINE__, shot + ": " + a.id + " is disabled without a why");
    }
}

void every_view(const fs::path& dir, const fs::path& scratch, const Caps& caps) {
    int views = 0;
    for (const auto& entry : fs::directory_iterator(dir)) {
        if (!fs::exists(entry.path() / "case.json")) continue;
        const std::string name = entry.path().filename().string();
        current = std::string(caps.platform_name) + " " + name;
        const auto c = json::parse(read(entry.path() / "case.json"));
        if (!c) continue;
        const CaseRun run = replay(*c, caps, scratch / name);
        // (Windows: the steps of Linux-only things are not there to do.)
        if (!caps.windows) {
            for (const std::string& p : run.problems) fail(__FILE__, __LINE__, p);
        }
        for (const auto& [shot, actions] : run.actions) {
            ++views;
            invariants(shot, actions, caps);
        }
    }
    std::printf("%s: %d views checked\n", caps.platform_name, views);
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: model_test GOLDEN_DIR SCRATCH_DIR [--case NAME] [--write DIR]\n");
        return 2;
    }
    const fs::path golden = argv[1], scratch = argv[2];
    std::string only;
    fs::path write;
    for (int i = 3; i + 1 < argc; i += 2) {
        const std::string flag = argv[i];
        if (flag == "--case") only = argv[i + 1];
        else if (flag == "--write") write = argv[i + 1];
    }
#ifdef _WIN32
    // (The goldens are Linux's, with its paths: Windows' views are held to the rules below.)
    std::printf("goldens: not compared on Windows\n");
#else
    goldens(golden, scratch / "goldens", only, write);
#endif
    if (only.empty()) {
        every_view(golden, scratch / "linux", Caps::linux_caps());
        every_view(golden, scratch / "windows", Caps::windows_caps());
        units(golden, scratch / "units");
    }
    if (failures) std::fprintf(stderr, "%d failed\n", failures);
    else std::printf("all passed\n");
    return failures ? 1 : 0;
}
