#include "replay.h"

#include "fakes.h"
#include "status.h"
#include "test_actions.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>

namespace launcher::model::testing {

namespace {

const char* const kHome = "/home/player";

std::string quoted(const std::string& s) {
    std::string o = "\"";
    for (const unsigned char c : s) {
        if (c == '"' || c == '\\') {
            o += '\\';
            o += static_cast<char>(c);
        } else if (c == '\n') {
            o += "\\n";
        } else if (c < 0x20) {
            char b[8];
            std::snprintf(b, sizeof b, "\\u%04x", c);
            o += b;
        } else {
            o += static_cast<char>(c);
        }
    }
    return o + "\"";
}

} // namespace

std::string to_json(const json::Value& v) {
    switch (v.type()) {
    case json::Value::Type::kNull: return "null";
    case json::Value::Type::kBool: return v.boolean() ? "true" : "false";
    case json::Value::Type::kNumber: {
        const double n = v.number();
        char b[32];
        if (std::floor(n) == n && std::fabs(n) < 1e15)
            std::snprintf(b, sizeof b, "%.0f", n);
        else
            std::snprintf(b, sizeof b, "%.17g", n);
        return b;
    }
    case json::Value::Type::kString: return quoted(v.string());
    case json::Value::Type::kArray: {
        std::string o = "[";
        for (size_t i = 0; i < v.items().size(); ++i) o += (i ? ", " : "") + to_json(v.items()[i]);
        return o + "]";
    }
    case json::Value::Type::kObject: {
        std::string o = "{";
        for (size_t i = 0; i < v.keys().size(); ++i)
            o += (i ? ", " : "") + quoted(v.keys()[i]) + ": " + to_json(v.values()[i]);
        return o + "}";
    }
    }
    return "null";
}

// The stand-ins the old app ran with (launcher.py answering the fixture, import_character.py printing its
// steps), as C++.
void fixture_answer(const json::Value& c, Run& run) {
    std::vector<std::string> argv = run.command.argv;
    if (argv.empty()) return;
    // (Windows: main.py --query X answers as launcher.py X; main.py --worker import|remove runs the importer, whose
    // lines it passes on; its other workers build.)
    const auto flag = std::find(argv.begin(), argv.end(), "--query");
    if (flag != argv.end() && flag + 1 != argv.end()) argv = {argv[0], "launcher.py", *(flag + 1)};
    const auto worker = std::find(argv.begin(), argv.end(), "--worker");
    if (worker != argv.end() && worker + 1 != argv.end()) {
        const std::string action = *(worker + 1);
        if (action != "import" && action != "remove") {
            run.lines.push_back({"@step build Building", false});
            return;
        }
        const auto outfits = std::find(argv.begin(), argv.end(), "--outfits");
        std::vector<std::string> names(outfits + 2, argv.end());
        argv = {argv[0], "import_character.py"};
        if (action == "remove") argv.push_back("--remove");
        argv.insert(argv.end(), names.begin(), names.end());
    }
    const std::string script = argv.size() > 1 ? fs::path(argv[1]).filename().string() : "";
    if (script == "launcher.py") {
        const std::string what = argv.size() > 2 ? argv[2] : "";
        if (what == "status" && c["status_fail"].is_string()) {
            run.lines.push_back({"Traceback (most recent call last):", true});
            run.lines.push_back({c["status_fail"].string(), true});
            run.code = 1;
            return;
        }
        const json::Value& a = c[what];
        if (a.is_null()) {
            run.lines.push_back({"{\"error\": \"not in the fixture\"}", false});
            run.code = what == "main" ? 1 : 0;
            return;
        }
        run.lines.push_back({to_json(a), false});
        return;
    }
    if (script == "import_character.py") {
        const bool remove = argv.size() > 2 && argv[2] == "--remove";
        std::vector<std::string> names;
        for (size_t i = remove ? 3 : 2; i < argv.size() && !argv[i].starts_with("--"); ++i) names.push_back(argv[i]);
        std::vector<std::string> sorted = names;
        std::sort(sorted.begin(), sorted.end());
        std::string key;
        for (const std::string& n : sorted) key += (key.empty() ? "" : ",") + n;
        const json::Value& scripts = c["import_script"];
        const json::Value& plan = !scripts[key].is_null() ? scripts[key] : scripts["*"];
        for (size_t i = 0; i < names.size(); ++i) {
            run.lines.push_back(
                {"@step fighter " + names[i] + " " + std::to_string(i + 1) + " " + std::to_string(names.size()),
                 false});
        }
        run.lines.push_back({"@step shared", false});
        for (const json::Value& l : plan["lines"].items()) run.lines.push_back({l.string(), false});
        run.code = static_cast<int>(plan["exit"].number(0));
        if (run.code == 0) {
            for (const std::string& n : names)
                run.lines.push_back({std::string(remove ? "@removed " : "@added ") + n, false});
            run.lines.push_back({"@done", false});
        }
        if (c["env"]["TTT2_LAUNCHER_TEST_CANCEL"].is_string()) {
            run.held = true;
            run.terminate_code = run.code;
        }
        return;
    }
    const std::string program = fs::path(argv[0]).filename().string();
    if (program == "ttt2-build") {
        run.lines.push_back({"@step build Building", false});
        return;
    }
    if (program == "get_python_packages.py" || script == "get_python_packages.py") {
        run.lines.push_back({"@step download Downloading numpy and Pillow", false});
        run.lines.push_back({"@progress 30000000 41200000", false});
        run.lines.push_back({"@progress 41200000 41200000", false});
        run.lines.push_back({"@done", false});
        return;
    }
    if (program == "Tekken Tag Tournament 2") {
        if (argv.size() > 1 && argv[1] == "--precompile")
            run.lines.push_back({"@step shaders Preparing shaders", false});
        else
            run.held = true; // (the game runs on)
        return;
    }
    if (program == "curl" || program == "wget") {
        run.lines.push_back({to_json(c["release"]), false});
        return;
    }
}

CaseRun replay(const json::Value& c, const Caps& caps, const fs::path& scratch, const ReplayOptions& options) {
    CaseRun out;
    const fs::path home = kHome;
    std::error_code ec;
    fs::remove_all(scratch, ec);
    fs::create_directories(scratch, ec);
    const fs::path display_file = scratch / "display.ini", keyboard_file = scratch / "keyboard.ini";
    if (c["display_ini_dir"].boolean())
        fs::create_directories(display_file, ec);
    else if (c["display_ini"].is_string())
        std::ofstream(display_file) << c["display_ini"].string();
    if (c["keyboard_ini"].is_string()) std::ofstream(keyboard_file) << c["keyboard_ini"].string();

    Facts facts;
    facts.caps = caps;
    facts.launcher_version = "0.8.0";
    facts.kit = home / "kit";
    facts.importer = home / "stub";
    facts.python = "/usr/bin/python3";
    facts.builder = true;
    facts.this_build = c["kit_version"].string();
    facts.build_commit = build_commit(facts.this_build);
    facts.distro = Distro{"arch", "Arch Linux", "", {"arch"}, false};
    facts.saves = home / "saves";
    facts.saves_custom = true;
    if (c["owned_cache"].is_object()) {
        const Ownership cached = parse_owned(to_json(c["owned_cache"]));
        facts.owned.answer = cached.owned;
        facts.owned.has_answer = true;
    }
    if (caps.windows) {
        // (As the Tk window's run had them: tests/golden/README.md.)
        const std::string state = c["install"].string();
        facts.windows.folders = {{"source", ""},
                                 {"title", ""},
                                 {"install", state == "installed" || state == "unfinished"
                                                 ? (home / "Games/Tekken Tag Tournament 2").string()
                                                 : ""},
                                 {"data", (home / "TTT2Ultimate").string()},
                                 {"packs", (home / "TTT2Ultimate/characters").string()},
                                 {"saves", (home / "saves").string()},
                                 {"tools", (home / "tools").string()}};
        facts.windows.logs = home / "TTT2Ultimate/logs";
    }

    FakeEnvironment env;
    const std::string install = c["install"].string();
    const fs::path folder = home / "Games/Tekken Tag Tournament 2";
    if (install == "installed")
        env.install = {InstallState::kInstalled, folder, {}};
    else if (install == "unfinished")
        env.install = {InstallState::kUnfinished, folder, {}};
    env.built = c["built"].string();

    FakeStarter starter([&c](Run& run) { fixture_answer(c, run); });
    LinuxCommands linux_commands;
    linux_commands.game_log = home / ".cache/ttt2/game.log";
    WindowsCommands windows_commands;
    int stamps = 0;
    windows_commands.stamp = [&stamps] { return "20261124-140000-" + std::to_string(++stamps); };
    Commands& commands = caps.windows ? static_cast<Commands&>(windows_commands) : linux_commands;
    if (caps.windows) {
        // (The launcher's files and the game as the Tk run had them.)
        facts.windows.root = home / "repo";
        facts.windows.build = home / "repo/build-windows-tools";
        facts.windows.config = home / "repo/local/windows-launcher.json";
        if (install == "installed") {
            facts.windows.play =
                Command{{(folder / "TTT2 Ultimate.exe").string()}, {}, folder, {}, {}, Command::Mode::kDetached};
        }
    }
    KeyFile keys(keyboard_file);
    FakeFiles files;
    LauncherModel::Parts parts{commands, starter, env, keys, nullptr, {}, {}, us_key_label, {}, {}};
    parts.display_file = display_file;
    if (c["appimage"].boolean() && !caps.windows) {
        facts.self_update = true;
        facts.custom_releases = true;
        parts.update_files = &files;
        parts.update.appimage = home / "Ultimate_Launcher-x86_64.AppImage";
        parts.update.version = "0.8.0";
        parts.update.releases = "file://" + (home / "release.json").string();
        parts.update.custom_releases = true;
        parts.update.user_agent = "ttt2-launcher/0.8.0";
    }
    LauncherModel model(facts, parts);
    model.set_monitors({Monitor{720, 0}});

    double now = 1000;
    std::vector<Effect> effects; // what the model wanted done after programs ended
    const auto settle = [&](const std::function<void()>& after_each = {}) {
        for (int i = 0; i < 1000; ++i) {
            starter.pump(after_each);
            model.tick(now);
            if (starter.idle()) break;
        }
        for (Effect& e : model.take_effects()) effects.push_back(std::move(e));
    };
    const auto shot = [&](const std::string& name) {
        const View v = model.view();
        out.dumps[name] = flatten(v);
        out.actions[name] = actions_of(v);
    };
    const auto end = [&] {
        if (!options.at_end) return;
        Harness h{model, starter, env, now, [&] { settle(); }, effects};
        options.at_end(h);
    };

    model.start(now);
    settle();
    shot("00-start");

    std::string error;
    const auto actions = parse_test_actions(c["steps"].string(), &error);
    if (!actions) {
        out.problems.push_back("steps: " + error);
        return out;
    }
    const json::Value& cancel_at = c["env"]["TTT2_LAUNCHER_TEST_CANCEL"];
    int number = 0;
    for (const TestAction& a : *actions) {
        if (options.steps >= 0 && number >= options.steps) break;
        ++number;
        now += 0.5; // (the old app's steps: one after another once settled, 400 ms)
        char prefix[16];
        std::snprintf(prefix, sizeof prefix, "%02d-", number);
        const std::string label = prefix + a.label();
        bool running_shot = false, cancelled = false;
        const auto watch = [&] {
            const TaskRunner& t = model.task();
            if (!t.running()) return;
            const double fraction = t.progress_state().fraction();
            if (!running_shot && fraction >= 0.5) {
                running_shot = true;
                shot(label + "-running");
            }
            if (cancel_at.is_string() && !cancelled && fraction >= std::atof(cancel_at.string().c_str())) {
                cancelled = true;
                model.activate("task", now);
                shot(label + "-stopping");
            }
        };
        bool task_step = false;
        if (a.name == "expand-dlc") {
            if (!model.facts().dlc_expanded) model.activate("dlc", now);
        } else if (a.name == "toggle") {
            model.activate(a.args[0], now);
        } else if (a.name == "settings" || a.name == "back") {
            model.activate(a.name, now);
        } else if (a.name == "add") {
            task_step = true;
            if (a.args.size() == 1)
                model.activate("fighter:" + a.args[0], now);
            else
                out.problems.push_back("add of several: not replayed");
        } else if (a.name == "remove") {
            task_step = true;
            model.activate("remove:" + a.args[0], now);
        } else if (a.name == "bind") {
            const int input = input_index(a.args[0]);
            if (model.keys().picking() != input) model.activate("key:" + a.args[0], now);
            std::vector<int> usages;
            std::string codes = a.args[1];
            for (size_t at = 0; at <= codes.size();) {
                const size_t plus = codes.find('+', at);
                usages.push_back(usage_of_xkb(std::atoi(codes.substr(at, plus - at).c_str())));
                if (plus == std::string::npos) break;
                at = plus + 1;
            }
            for (const int u : usages) model.key_down(u, false, now);
            for (auto it = usages.rbegin(); it != usages.rend(); ++it) model.key_up(*it, now);
        } else if (a.name == "reset-keys") {
            model.activate("restore-keys", now);
        } else if (a.name == "fullscreen" || a.name == "interpolation" || a.name == "input-delay" ||
                   a.name == "async-shaders" || a.name == "precompile-shaders") {
            const display::Settings& s = model.display().settings();
            const bool on = a.name == "fullscreen"      ? s.fullscreen
                            : a.name == "interpolation" ? s.interpolation
                            : a.name == "input-delay"   ? s.input_delay
                            : a.name == "async-shaders" ? s.async_shaders
                                                        : s.precompile_shaders;
            if (on != (a.args[0] == "yes")) model.activate(a.name, now);
        } else if (a.name == "resolution") {
            const auto r = display::resolution_named(a.args[0]).value_or(display::Resolution::kAuto);
            const auto& all = display::kResolutions;
            model.choose("resolution", static_cast<int>(std::find(std::begin(all), std::end(all), r) - std::begin(all)),
                         now);
        } else if (a.name == "show-uninstall") {
            model.activate("uninstall", now);
            settle();
            shot(label);
            model.activate("uninstall-cancel", now);
            continue;
        } else if (a.name == "update" || a.name == "play" || a.name == "get-packages") {
            task_step = true;
            model.activate(a.name, now);
        } else if (a.name == "uninstall") {
            task_step = true;
            model.activate("uninstall", now);
            if (a.args[0] == "all") {
                model.activate("uninstall-saves", now);
                model.activate("uninstall-characters", now);
            }
            for (const Effect& e : model.activate("uninstall-confirm", now)) {
                if (e.kind != Effect::Kind::kUninstall) continue;
                UninstallReport report;
                report.folder_removed = true;
                env.install = {};
                env.built.clear();
                model.uninstall_done(report, now);
            }
        } else if (a.name == "focus" || a.name == "wait") {
            // (focus is the UI's)
        } else {
            out.problems.push_back("step not replayed: " + a.text);
        }
        settle(watch);
        if (task_step && a.name == "play") {
            out.said.push_back("@test play " + std::string(model.facts().game_error.empty()
                                                               ? "ok"
                                                               : "failed " + model.facts().game_error));
        } else if (task_step) {
            const TaskResult& r = model.task().last();
            out.said.push_back(
                "@test " + a.text + " " +
                (r.ok ? "ok " + r.title : "failed " + r.title + (r.detail.empty() ? "" : ": " + r.detail)));
        }
        shot(label);
    }
    end();
    return out;
}

} // namespace launcher::model::testing
