// model_test GOLDEN_DIR SCRATCH_DIR [--case NAME] [--write DIR] [--tk-report NAME|all]
//
// 1. GTK goldens: every case of GOLDEN_DIR (dumped from the old GTK app, see
//    golden/README.md) played through the model and compared, dump by dump,
//    with the intended differences of golden/INTENDED.md applied. --write
//    also writes the model's dumps (the same shape) for a look or a diff.
// 2. The same cases with Linux's and Windows' caps: every view's ids are
//    unique, of its OS, and a disabled item says why.
// 3. Tk goldens: the model's Windows views say what the old Tk window said,
//    but for INTENDED.md's W rules (--tk-report lists every difference).
// 4. Unit tests of the controllers: tasks, keys, display.ini, the refresh
//    rules, the AppImage's update, closing, activate(id) for every id.

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
#include <regex>
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

// I5 Ids the old app gave no element: new ones.
const std::vector<std::string> kNewIds = {
    "refresh", "details", "uninstall-saves", "uninstall-characters", "uninstall-cancel", "uninstall-confirm"};

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

// `display_ini`: the case's display.ini ("" for none).
void intended(Dump& golden, const Dump& model, const std::string& display_ini) {
    // I6 "Prepare shaders before playing" is on by default (the old app's was off): where the case's display.ini
    // does not say, the golden's switch is on.
    if (display_ini.find("precompile_shaders") == std::string::npos) {
        for (auto& [name, section] : golden)
            for (Element& e : section)
                if (e.kind == "switch" && e.text.count("id") && e.text.at("id") == "precompile-shaders")
                    e.flags["on"] = true;
    }
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
    if (golden["task"].empty() && !task.empty() && task[0].text.count("t") &&
        task[0].text.at("t") == "Shaders are ready") {
        golden["task"] = task;
    }
    // I7 Home's UPDATE: where something is to bring up to date (the launcher, the game program, characters), one
    // Update does all of it and takes Play's place as the suggested item; Play stays as an ordinary one, and the
    // game program's own Update goes (UPDATE does it). The model's element as it is: units.cpp checks its parts.
    if (const auto m = model.find("game"); m != model.end()) {
        const auto id_is = [](const Element& e, const char* id) {
            const auto it = e.text.find("id");
            return it != e.text.end() && it->second == id;
        };
        const auto all = std::find_if(m->second.begin(), m->second.end(),
                                      [&](const Element& e) { return id_is(e, "update-everything"); });
        Section& g = golden["game"];
        if (all != m->second.end()) {
            size_t place = SIZE_MAX;
            for (size_t i = 0; i < g.size();) {
                if (id_is(g[i], "update")) {
                    if (g[i].text.count("cls") && g[i].text.at("cls") == "primary") place = i;
                    g.erase(g.begin() + static_cast<long>(i));
                    continue;
                }
                if (id_is(g[i], "play")) {
                    if (place == SIZE_MAX) place = i;
                    g[i].text.erase("cls");
                }
                ++i;
            }
            if (place != SIZE_MAX) g.insert(g.begin() + static_cast<long>(std::min(place, g.size())), *all);
            // (The launcher's notice says that UPDATE gets the new version first.)
            static const std::regex notice("You have (.*)\\. Update replaces this AppImage with it and opens it\\.");
            for (Element& e : golden["notice"]) {
                std::smatch have;
                if (e.text.count("t") && std::regex_match(e.text.at("t"), have, notice)) {
                    e.text["t"] = "You have " + have[1].str() +
                                  ". Update on Home gets it first, then brings the game program and the fighters up "
                                  "to date.";
                }
            }
        }
    }
    // I8 Fighters' Add All Owned for every game's characters at once (one button that adds them all): the model's
    // element as it is, where the model has it (units.cpp add_all_everything checks what it adds).
    if (const auto m = model.find("characters"); m != model.end()) {
        for (size_t i = 0; i < m->second.size(); ++i) {
            const auto id = m->second[i].text.find("id");
            if (id == m->second[i].text.end() || id->second != "add-all-owned:all") continue;
            Section& c = golden["characters"];
            c.insert(c.begin() + static_cast<long>(std::min(i, c.size())), m->second[i]);
            break;
        }
    }
    // I1 Settings is always reachable: a gear beside Install/Resume when the game is not installed.
    Section& game = golden["game"];
    for (size_t i = 0; i < game.size(); ++i) {
        const auto id = game[i].text.find("id");
        if (id == game[i].text.end() || (id->second != "install" && id->second != "resume")) continue;
        const bool there =
            i + 1 < game.size() && game[i + 1].text.count("id") && game[i + 1].text.at("id") == "settings";
        if (!there) {
            game.insert(game.begin() + static_cast<long>(i) + 1,
                        Element{"button",
                                {{"id", "settings"}, {"icon", "ttt2-settings-symbolic"}, {"tip", "Settings"}},
                                {{"s", true}}});
        }
        break;
    }
    // I9 Settings has a Game section first: the player's name and the language of the game's texts (game.ini) and the
    // input delay, which leaves the display section (now called Display); display.ini's notes go with it too. (No
    // case has a game.ini: no name, English.)
    Section& settings = golden["settings"];
    const auto is_label = [](const Element& e, const char* t, const char* tone = nullptr) {
        return e.kind == "label" && e.text.count("t") && e.text.at("t") == t &&
               (!tone || (e.text.count("tone") && e.text.at("tone") == tone));
    };
    if (!settings.empty() && is_label(settings[0], "Game", "heading")) {
        settings[0].text["t"] = "Display";
        Section game = {
            {"label", {{"t", "Game"}, {"tone", "heading"}}, {}},
            {"label",
             {{"t", "Your name in the game, the language of its texts, and how it takes your presses. The game uses "
                    "these when it starts."},
              {"tone", "dim"}},
             {}}};
        // (display.ini's notes: between its section's words and its first setting.)
        for (size_t i = 2; i < settings.size() && !is_label(settings[i], "Fullscreen"); ++i) game.push_back(settings[i]);
        game.push_back({"label", {{"t", "Player name"}}, {}});
        game.push_back({"label", {{"t", "The name the game shows for you, in place of Player."}, {"tone", "dim"}}, {}});
        game.push_back({"label",
                        {{"t", "Up to 16 characters: the letters A to Z, digits, spaces and the punctuation of an "
                               "English keyboard but #. Left empty, the game's own name in its language (Player in "
                               "English)."},
                         {"tone", "dim"}},
                        {}});
        game.push_back({"entry", {{"id", "player-name"}}, {{"s", true}}});
        game.push_back({"label", {{"t", "Language"}}, {}});
        game.push_back({"label", {{"t", "The game's texts and menus show in this language."}, {"tone", "dim"}}, {}});
        game.push_back({"choice", {{"id", "language"}, {"t", "English"}}, {{"s", true}}});
        for (size_t i = 0; i + 2 < settings.size(); ++i) {
            if (!is_label(settings[i], "Input delay")) continue;
            game.insert(game.end(), settings.begin() + static_cast<long>(i), settings.begin() + static_cast<long>(i) + 3);
            settings.erase(settings.begin() + static_cast<long>(i), settings.begin() + static_cast<long>(i) + 3);
            break;
        }
        settings.insert(settings.begin(), game.begin(), game.end());
    }
    // I2 Settings has the launcher's own section after Keyboard.
    if (!settings.empty()) {
        const auto add = [&](Element e) { settings.push_back(std::move(e)); };
        add({"label", {{"t", "Golden Fist Launcher"}, {"tone", "heading"}}, {}});
        add({"label", {{"t", "How this launcher looks and sounds."}, {"tone", "dim"}}, {}});
        add({"label", {{"t", "Language"}}, {}});
        add({"label",
             {{"t", "The language of this launcher's texts. System: the one your system shows, when the launcher has "
                    "it, else English."},
              {"tone", "dim"}},
             {}});
        add({"choice", {{"id", "launcher-language"}, {"t", "System (English)"}}, {{"s", true}}});
        add({"label", {{"t", "Sounds"}}, {}});
        add({"label", {{"t", "Short sounds when moving between and choosing items."}, {"tone", "dim"}}, {}});
        add({"switch", {{"id", "sounds"}}, {{"on", true}, {"s", true}}});
        add({"label", {{"t", "Reduce motion"}}, {}});
        add({"label", {{"t", "No moving backgrounds, and pages change without sliding."}, {"tone", "dim"}}, {}});
        add({"switch", {{"id", "reduce-motion"}}, {{"on", false}, {"s", true}}});
        add({"label", {{"t", "Button prompts"}}, {}});
        add({"label",
             {{"t", "The buttons the prompts show: those of the last device used, or always these."}, {"tone", "dim"}},
             {}});
        add({"choice", {{"id", "prompts"}, {"t", "Automatic"}}, {{"s", true}}});
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
            for (const auto& [shot, dump] : run.dumps)
                std::ofstream(write / name / (shot + ".json")) << dump_json(dump);
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
            intended(*golden, made->second, (*c)["display_ini"].is_string() ? (*c)["display_ini"].string() : "");
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
            for (const char* step : {"@test add:", "@test remove:", "@test update ", "@test play ",
                                     "@test get-packages ", "@test uninstall:"}) {
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

// Ids only one OS has (the caps decide).
const std::vector<std::string> kLinuxOnly = {"install",   "resume",       "check-again", "preflight-cancel",
                                             "uninstall", "get-packages", "copy:"};
const std::vector<std::string> kWindowsOnly = {
    "more", "more:", "setup", "folder:", "save-folders", "performance", "open-keyboard-file", "open-log"};

bool listed(const std::string& id, const std::vector<std::string>& list) {
    return std::any_of(list.begin(), list.end(),
                       [&](const std::string& l) { return l.ends_with(':') ? id.starts_with(l) : id == l; });
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
        // Every item has its describe block (the blue side): what it is at least.
        if (a.describe.title.empty()) fail(__FILE__, __LINE__, shot + ": " + a.id + " has no describe block");
        // A disabled item stays, and says why (in the blue side: describe.why).
        if (!a.enabled && a.describe.why.empty())
            fail(__FILE__, __LINE__, shot + ": " + a.id + " is disabled without a why");
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

// ---------------------------------------------------------------- 4. Windows: what the Tk window showed

// The texts a section shows (labels, buttons, pills, check boxes, lists, folder fields), each once per showing.
// Not tooltips: the new window has none (an item's describe block says it), and not icons.
std::multiset<std::string> texts_of(const Section& section) {
    std::multiset<std::string> out;
    for (const Element& e : section) {
        const auto it = e.text.find("t");
        if (e.kind != "icon" && it != e.text.end() && !it->second.empty()) out.insert(it->second);
    }
    return out;
}

std::vector<std::string> minus(const std::multiset<std::string>& a, const std::multiset<std::string>& b) {
    std::vector<std::string> out;
    std::multiset<std::string> rest = b;
    for (const std::string& t : a) {
        const auto it = rest.find(t);
        if (it == rest.end())
            out.push_back(t);
        else
            rest.erase(it);
    }
    return out;
}

// The model's Windows views of the Tk dumps' moments: the start page with the DLC list open, Settings.
std::map<std::string, Dump> windows_views(const json::Value& c, const fs::path& scratch) {
    std::map<std::string, Dump> out;
    replay(c, Caps::windows_caps(), scratch, {0, [&](Harness& h) {
                                                  if (!h.model.facts().dlc_expanded) h.model.activate("dlc", h.now);
                                                  h.settle();
                                                  out["00-start"] = flatten(h.model.view());
                                                  h.model.activate("settings", h.now);
                                                  out["01-settings"] = flatten(h.model.view());
                                              }});
    return out;
}

// What the model's Windows views say differently from the Tk window, on purpose (golden/INTENDED.md): every
// difference of the texts must match one of these.
struct TkDifference {
    bool tk_only; // a text Tk showed that the model does not (else: the model's, not Tk's)
    const char* section;
    const char* pattern; // the whole text
    const char* rule;    // INTENDED.md
};
const TkDifference kTkDifferences[] = {
    // W0 Tk's layout, not its words: the section title above the game card, the shoulder buttons' glyphs.
    {true, "game", "Game", "W0"},
    {true, "settings", "L|R|ZL|ZR", "W0"},
    // I2 The launcher's own settings.
    {false, "settings",
     "Golden Fist Launcher|How this launcher looks and sounds\\.|Language|The language of this launcher's texts\\. "
     "System: the one your system shows, when the launcher has it, else English\\.|System \\(English\\)|Sounds|Short "
     "sounds when moving between and choosing "
     "items\\.|Reduce motion|No moving backgrounds, and pages change without sliding\\.|Button prompts|The buttons "
     "the prompts show: those of the last device used, or always these\\.|Automatic|Text size|How large this "
     "launcher's text is\\.|100 %",
     "I2"},
    // W6 Linux's words where Tk's had drifted (or Tk had none).
    {false, "settings", "Automatic: enough to cover the .*", "W6"},
    {false, "settings", "keyboard\\.ini, changed by hand, gives a key to two inputs, .*", "W6"},
    {false, "settings", "display\\.ini cannot be read \\(.*", "W6"},
    {true, "characters", "Your Steam account owns \\d+ of them\\.", "W6"},
    {false, "characters", "Your Steam account owns \\d+ of them: only those can be added\\.", "W6"},
    {true, "characters", "Start Steam to add them: it tells which of them you own\\.", "W6"},
    {false, "characters", "Start Steam to see which DLC you own: only those can be added\\.", "W6"},
    {false, "characters",
     "Your Steam account owned \\d+ of them last time Steam was asked\\. Start Steam to add them: it "
     "checks again\\.",
     "W6"},
    {true, "characters", "Which of them you own is not known yet\\.", "W6"},
    {false, "characters", "Which DLC you own is not known: .*", "W6"},
    {true, "characters", "Steam could not tell which you own \\(.*\\): adding one asks it again\\.", "W6"},
    {false, "characters",
     "Steam could not be asked again \\(.*\\)\\. It said last time that your account owns \\d+ of "
     "them\\.",
     "W6"},
    {true, "characters", "Tekken 7 is not installed\\.|Tekken 8 is not installed in any Steam library|Not installed",
     "W6"},
    {false, "characters", "Not installed|Not installed: Tekken 7 and Tekken 8 for PC come from Steam", "W6"},
    {true, "characters",
     "Start Steam to add characters: Tekken 7 needs it the first time, and it tells which DLC you "
     "own\\.",
     "W6"},
    {false, "characters",
     "Start Steam to add characters: Tekken 7 and Tekken 8 need it the first time, and it tells "
     "which DLC you own\\.",
     "W6"},
    {true, "characters", "The importer cannot read the installed game: .*", "W6"},
    {false, "characters", "The importer cannot read it: .*|Game", "W6"},
    {true, "characters", "Importing outfits can drastically prolong adding and updating characters: .*", "W6"},
    // W7 Linux's rules where Tk's had drifted: a DLC fighter not owned has no Add (Not owned says it); the count of
    // DLC fighters and the owned ones; the update offer also while the game cannot be used; Tekken 8's stand-ins
    // and packs from another version.
    {true, "characters", "Add", "W7"},
    {false, "characters", "\\d+|\\d+ of \\d+ owned|Owned|Not owned", "W7"},
    {false, "characters", ".+ was made by an older version: update them to get what this one adds\\.|Update", "W7"},
    {true, "characters", ".+ was made by an older version: update them to get what this one adds\\.", "W7"},
    {false, "characters",
     ".+ fights with Heihachi's moves for now: .*|.+ was made by a newer version of Golden Fist "
     "Launcher and is not in the game: .*|.+ was made by an older version and is not in the game: "
     "add them again\\.|Remove|Remove All",
     "W7"},
    {false, "characters",
     "Their moves cannot be saved from Tekken 8 now: .*|Tekken 8 was updated to a version that "
     "Golden Fist Launcher cannot save moves from yet: .*",
     "W7"},
    // I7 Home's UPDATE (the launcher, the game program and the characters in one) where Play was the suggested item.
    {false, "game", "Update", "I7"},
    {false, "notice", "You have .*\\. Update on Home gets it first, then brings the game program and the fighters up to "
     "date\\.", "I7"},
    {true, "notice", "You have .*\\. Update replaces this launcher with it and opens it\\.", "I7"},
    // I8 Add All Owned for every game's characters.
    {false, "characters", "Add All Owned", "I8"},
    // I9 Settings' Game section: the player's name, the language; the display section called Display.
    {false, "settings",
     "Display|Player name|The name the game shows for you, in place of Player\\.|Up to 16 characters: the letters A "
     "to Z, digits, spaces and the punctuation of an English keyboard but #\\. Left empty, the game's own name in its "
     "language \\(Player in English\\)\\.|Language|English|The game's texts and menus show in this language\\.|Your "
     "name in the game, the language of its texts, and how it takes your presses\\. The game uses these when it "
     "starts\\.",
     "I9"},
    // W8 Linux's sentence with Windows' action.
    {true, "characters", "Set up the game first: characters are made from it\\.", "W8"},
    {false, "characters",
     "Set up the game first: the characters are made from it and from your Tekken 7 or Tekken "
     "8\\.",
     "W8"},
};

const TkDifference* tk_intended(bool tk_only, const std::string& section, const std::string& text) {
    for (const TkDifference& d : kTkDifferences) {
        if (d.tk_only == tk_only && section == d.section && std::regex_match(text, std::regex(d.pattern))) return &d;
    }
    return nullptr;
}

// The Tk goldens: the model's Windows views say what the Tk window said, but for kTkDifferences.
void tk_goldens(const fs::path& dir, const fs::path& scratch) {
    int cases = 0, dumps = 0, intended = 0;
    for (const auto& entry : fs::directory_iterator(dir)) {
        const std::string name = entry.path().filename().string();
        if (!fs::exists(entry.path() / "windows/00-start.json")) continue;
        current = "tk " + name;
        const auto c = json::parse(read(entry.path() / "case.json"));
        if (!c) continue;
        ++cases;
        const auto made = windows_views(*c, scratch / name);
        for (const auto& [shot, model] : made) {
            const auto tk = parse_dump(read(entry.path() / "windows" / (shot + ".json")));
            if (!tk) {
                fail(__FILE__, __LINE__, shot + ": not a dump");
                continue;
            }
            ++dumps;
            for (const char* section : kSections) {
                const auto a = texts_of(tk->count(section) ? tk->at(section) : Section{});
                const auto b = texts_of(model.count(section) ? model.at(section) : Section{});
                for (const bool tk_only : {true, false}) {
                    for (const std::string& t : tk_only ? minus(a, b) : minus(b, a)) {
                        if (tk_intended(tk_only, section, t)) {
                            ++intended;
                            continue;
                        }
                        fail(__FILE__, __LINE__,
                             shot + " " + section +
                                 (tk_only ? ": Tk said, the model does not: " : ": the model says, Tk did not: ") + t);
                    }
                }
            }
        }
    }
    std::printf("tk goldens: %d cases, %d dumps compared, %d intended differences\n", cases, dumps, intended);
    CHECK(cases >= 30);
}

void tk_report(const fs::path& dir, const fs::path& scratch, const std::string& only) {
    for (const auto& entry : fs::directory_iterator(dir)) {
        const std::string name = entry.path().filename().string();
        if (!fs::exists(entry.path() / "windows/00-start.json") || (!only.empty() && name != only)) continue;
        const auto c = json::parse(read(entry.path() / "case.json"));
        if (!c) continue;
        const auto made = windows_views(*c, scratch / name);
        for (const auto& [shot, model] : made) {
            const auto tk = parse_dump(read(entry.path() / "windows" / (shot + ".json")));
            if (!tk) continue;
            for (const char* section : kSections) {
                const auto a = texts_of(tk->count(section) ? tk->at(section) : Section{});
                const auto b = texts_of(model.count(section) ? model.at(section) : Section{});
                for (const bool tk_only : {true, false}) {
                    for (const std::string& t : tk_only ? minus(a, b) : minus(b, a)) {
                        const TkDifference* d = tk_intended(tk_only, section, t);
                        std::printf("%s\t%s\t%s\t%s\t%s\t%s\n", name.c_str(), shot.c_str(), section,
                                    tk_only ? "tk-only" : "model-only", d ? d->rule : "-", t.c_str());
                    }
                }
            }
        }
    }
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: model_test GOLDEN_DIR SCRATCH_DIR [--case NAME] [--write DIR]\n");
        return 2;
    }
    const fs::path golden = argv[1], scratch = argv[2];
    // (The launcher's texts in English, the goldens' language, whatever this PC's is: Settings' "System (English)".)
    for (const char* name : {"LANGUAGE", "LC_ALL", "LC_MESSAGES"}) unsetenv(name);
    setenv("LANG", "C", 1);
    launcher::i18n::set_language("en");
    std::string only;
    fs::path write;
    for (int i = 3; i + 1 < argc; i += 2) {
        const std::string flag = argv[i];
        if (flag == "--case")
            only = argv[i + 1];
        else if (flag == "--write")
            write = argv[i + 1];
        else if (flag == "--tk-report") {
            tk_report(golden, scratch / "tk", argv[i + 1] == std::string("all") ? "" : argv[i + 1]);
            return 0;
        }
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
        tk_goldens(golden, scratch / "tk");
        units(golden, scratch / "units");
    }
    if (failures)
        std::fprintf(stderr, "%d failed\n", failures);
    else
        std::printf("all passed\n");
    return failures ? 1 : 0;
}
