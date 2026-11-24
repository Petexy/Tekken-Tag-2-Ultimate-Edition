// model_test's unit tests of the controllers (no goldens): keys (U4),
// display.ini, the task runner, the refresh rules, closing while a task runs,
// the AppImage's update, activate(id) (U14).

#include "units.h"

#include "check.h"
#include "fakes.h"
#include "replay.h"
#include "preflight.h"
#include "self_update.h"
#include "settings.h"
#include "status.h"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <sstream>

namespace launcher::model::testing {

namespace {

constexpr int kK = 14, kL = 15, kQ = 20, kF11 = 68, kCtrl = 224, kShift = 225;

std::string read(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    std::stringstream s;
    s << in.rdbuf();
    return s.str();
}

// ---------------------------------------------------------------- keys (spec linux 3.3, U4)

void keys() {
    current = "keys";
    const int bottom = input_index("face_bottom"), right = input_index("face_right");
    MemoryKeys store;
    KeyCapture k(store);
    k.load();
    CHECK_EQ(k.keymap().key(bottom), kK);
    CHECK_EQ(k.keymap().key(right), kL);
    double now = 100;

    // A key taken: saved at once.
    k.pick(bottom, Device::kKeyboard, now);
    CHECK_EQ(k.picking(), bottom);
    CHECK(k.key_down(kQ, false, now));
    k.key_up(kQ, now);
    CHECK(k.taken().ok);
    CHECK_EQ(k.taken().text, std::string("Bottom button is Q"));
    CHECK_EQ(store.saves, 1);
    CHECK_EQ(k.picking(), -1);

    // The key of another input: swapped, said on that row for 3 s.
    k.pick(bottom, Device::kKeyboard, now);
    k.key_down(kL, false, now);
    k.key_up(kL, now);
    CHECK_EQ(k.taken().text, std::string("Bottom button is L, swapped with Right button"));
    CHECK_EQ(k.keymap().key(right), kQ);
    CHECK(k.row_notes().count(right) && k.row_notes().at(right).tone == Tone::kOk);
    k.tick(now + KeyCapture::kSwappedSeconds - 0.1);
    CHECK(k.row_notes().count(right));
    k.tick(now + KeyCapture::kSwappedSeconds + 0.1);
    CHECK(!k.row_notes().count(right));

    // A reserved key: refused on the row (4 s), still choosing.
    k.pick(bottom, Device::kKeyboard, now);
    k.key_down(kF11, false, now);
    k.key_up(kF11, now);
    CHECK(!k.taken().ok);
    CHECK_EQ(k.taken().text, std::string("F11 toggles full screen"));
    CHECK_EQ(k.picking(), bottom);
    CHECK(k.row_notes().count(bottom) && k.row_notes().at(bottom).tone == Tone::kError);
    // Esc stops (and the refusal goes with it).
    k.key_down(kEscape, false, now);
    k.key_up(kEscape, now);
    CHECK_EQ(k.picking(), -1);
    CHECK_EQ(k.taken().text, std::string("cancelled with Esc"));
    CHECK(!k.row_notes().count(bottom));

    // A modifier alone: taken when let go.
    k.pick(bottom, Device::kKeyboard, now);
    CHECK(k.key_down(kShift, false, now));
    CHECK_EQ(k.picking(), bottom);
    k.key_up(kShift, now);
    CHECK_EQ(k.picking(), -1);
    CHECK_EQ(k.keymap().key(bottom), kShift);

    // A shortcut (Ctrl+Q) stops choosing, and the key goes on.
    k.pick(bottom, Device::kKeyboard, now);
    CHECK(k.key_down(kCtrl, false, now));
    CHECK(!k.key_down(kQ, false, now));
    CHECK_EQ(k.picking(), -1);
    CHECK_EQ(k.keymap().key(bottom), kShift);
    k.key_up(kQ, now);
    k.key_up(kCtrl, now);
    CHECK_EQ(k.keymap().key(bottom), kShift);

    // A held key's repeats are not taken; nor a key let go that was pressed before choosing started.
    k.key_down(kK, false, now); // (the keycap clicked with K held)
    k.pick(bottom, Device::kKeyboard, now);
    CHECK(k.key_down(kK, true, now));
    CHECK_EQ(k.picking(), bottom);
    k.key_up(kK, now);
    CHECK_EQ(k.picking(), bottom);
    k.key_down(kShift, false, now - 1); // (Shift held before ...)
    k.stop();
    k.pick(bottom, Device::kKeyboard, now);
    k.key_up(kShift, now);              // (... let go after: not taken)
    CHECK_EQ(k.picking(), bottom);

    // A again on the same keycap stops.
    k.pick(bottom, Device::kPad, now);
    CHECK_EQ(k.picking(), -1);

    // Started from the pad: the keyboard is ignored 250 ms.
    k.pick(bottom, Device::kPad, now);
    k.key_down(kK, false, now + 0.1);
    k.key_up(kK, now + 0.1);
    CHECK_EQ(k.picking(), bottom);
    k.key_down(kK, false, now + KeyCapture::kIgnoreAfterPad + 0.01);
    k.key_up(kK, now + 0.3);
    CHECK_EQ(k.picking(), -1);
    CHECK_EQ(k.keymap().key(bottom), kK);

    // Without a key being chosen nothing is used (navigation).
    CHECK(!k.key_down(kQ, false, now));
    k.key_up(kQ, now);

    // Saving fails: the error, and the keys stay as the game has them.
    store.fail = "Permission denied";
    k.pick(bottom, Device::kKeyboard, now);
    k.key_down(kQ, false, now);
    k.key_up(kQ, now);
    CHECK(!k.taken().ok);
    CHECK_EQ(k.error(), std::string("The keys cannot be saved: Permission denied"));
    CHECK_EQ(k.keymap().key(bottom), kK);
    store.fail.clear();

    // Restore Defaults: saved, the rows that changed flash.
    k.pick(right, Device::kKeyboard, now);
    k.key_down(kShift, false, now);
    k.key_up(kShift, now);
    CHECK(k.restorable());
    k.restore(now);
    CHECK(k.keymap().is_default());
    CHECK(k.error().empty());
    CHECK(k.row_notes().count(right) && k.row_notes().at(right).flash);
    k.tick(now + KeyCapture::kRestoredSeconds + 0.1);
    CHECK(k.row_notes().empty());
    CHECK(!k.restorable());

    // keyboard.ini with two inputs on one key: said when Settings opens.
    store.text = "face_bottom = 14\nface_right = 14\n";
    k.load();
    CHECK(!k.note().empty());
    CHECK(k.restorable());

    // XKB keycodes of the old test actions (bind:<input>:<keycode>).
    CHECK_EQ(usage_of_xkb(9), kEscape);
    CHECK_EQ(usage_of_xkb(45), kK);
    CHECK_EQ(usage_of_xkb(50), kShift);
    CHECK_EQ(usage_of_xkb(3), 0);
}

// ---------------------------------------------------------------- display.ini

void display(const fs::path& scratch) {
    current = "display";
    std::error_code ec;
    fs::remove_all(scratch, ec);
    fs::create_directories(scratch, ec);
    const fs::path file = scratch / "display.ini";
    DisplayController d(file);
    d.load();
    // (No file: the game's defaults, no note.)
    CHECK(d.note().empty());
    CHECK(!d.settings().fullscreen);
    CHECK(d.settings().interpolation);
    CHECK(d.set("fullscreen", 1));
    CHECK(d.settings().fullscreen);
    CHECK(read(file).find("fullscreen = yes") != std::string::npos);
    CHECK(d.set("resolution", 2));
    CHECK(d.settings().resolution == display::Resolution::k1080);
    CHECK(!d.set("volume", 1));
    CHECK(d.performance());
    CHECK(d.settings().resolution == display::Resolution::k720);
    CHECK(!d.settings().interpolation);
    // What Play reads is the file's, when it is read.
    std::ofstream(file) << "precompile_shaders = yes\n";
    CHECK(d.read().precompile_shaders);
    CHECK(!d.settings().precompile_shaders);

    // Saving fails (display.ini is a folder): the error, and the controls show what the game reads.
    fs::remove(file, ec);
    fs::create_directories(file / "x", ec);
    d.load();
    CHECK(d.note().starts_with("display.ini cannot be read ("));
    CHECK(d.note().ends_with("): the game uses its defaults. Changing a setting here writes it anew."));
    const display::Settings before = d.settings();
    CHECK(!d.set("fullscreen", !before.fullscreen));
    CHECK(d.error().starts_with("The display settings cannot be saved: "));
    CHECK(d.settings() == before);
}

// ---------------------------------------------------------------- the task runner

struct Ended {
    int count = 0;
    TaskResult last;
};

void task_runner() {
    current = "task runner";
    FakeStarter starter;
    TaskRunner t(starter, Caps::linux_caps());
    t.set_names({{"kazumi", "Kazumi Mishima"}});
    Ended ended;
    t.on_end = [&](const TaskResult& r) {
        ++ended.count;
        ended.last = r;
    };
    const auto import = [](std::string title) {
        TaskSpec s;
        s.kind = TaskKind::kImport;
        s.title = std::move(title);
        s.command.argv = {"python3", "import_character.py", "kazumi"};
        s.subject = "Kazumi Mishima";
        s.names = {"kazumi"};
        return s;
    };
    double now = 10;
    starter.set_script([](Run& r) {
        r.lines = {{"@step fighter kazumi 1 1", false}, {"@added kazumi", false}, {"@done", false}};
    });
    CHECK(t.start(import("Adding Kazumi Mishima"), now));
    CHECK(t.running());
    CHECK(t.cancellable());
    CHECK_EQ(t.view().title, std::string("Adding Kazumi Mishima"));
    CHECK_EQ(t.view().button.label, std::string("Cancel"));
    starter.pump();
    t.tick(now);
    CHECK(!t.running());
    CHECK_EQ(ended.count, 1);
    CHECK(ended.last.ok);
    CHECK_EQ(ended.last.title, std::string("Added Kazumi Mishima"));
    CHECK_EQ(t.view().button.label, std::string("Close"));
    // A success hides after 12 s ...
    t.tick(now + TaskRunner::kShownSeconds - 0.5);
    CHECK(t.shown());
    t.tick(now + TaskRunner::kShownSeconds + 0.5);
    CHECK(!t.shown());

    // ... but not while Details is open.
    now = 100;
    CHECK(t.start(import("Adding Kazumi Mishima"), now));
    t.set_details(true);
    starter.pump();
    t.tick(now + 30);
    CHECK(t.shown());
    t.set_details(false);

    // A failure stays, with the last @error.
    now = 200;
    starter.set_script([](Run& r) {
        r.lines = {{"@error The pack could not be written", false}};
        r.code = 1;
    });
    CHECK(t.start(import("Adding Kazumi Mishima"), now));
    starter.pump();
    t.tick(now + 60);
    CHECK(t.shown());
    CHECK(!ended.last.ok);
    CHECK_EQ(ended.last.title, std::string("Adding Kazumi Mishima failed"));
    CHECK_EQ(ended.last.detail, std::string("The pack could not be written"));
    CHECK(t.view().failed);

    // Cancel: "Stopping…" until it ended, then the calm result.
    now = 300;
    starter.set_script([](Run& r) {
        r.lines = {{"@step fighter kazumi 1 1", false}};
        r.held = true;
    });
    CHECK(t.start(import("Adding Kazumi Mishima"), now));
    starter.pump();
    t.cancel();
    CHECK(t.running());
    CHECK_EQ(t.view().button.label, std::string("Stopping…"));
    CHECK(!t.view().button.enabled);
    starter.pump();
    t.tick(now);
    CHECK(!t.running());
    CHECK(ended.last.cancelled);
    CHECK_EQ(ended.last.title, std::string("Adding cancelled"));
    CHECK_EQ(ended.last.detail, std::string("The characters added before stay."));

    // A program that cannot start: said in the panel.
    starter.fail = "No such file or directory";
    CHECK(!t.start(import("Adding Kazumi Mishima"), 400));
    CHECK(!t.running());
    CHECK(t.view().failed);
    CHECK(t.view().detail.find("No such file or directory") != std::string::npos);

    // A refusal with nothing running: shown as a failed task, ended as one.
    const int before = ended.count;
    t.refuse("Cannot add characters", "Tekken 7 is not installed.", 500);
    CHECK(t.shown());
    CHECK_EQ(t.view().title, std::string("Cannot add characters"));
    CHECK_EQ(t.view().detail, std::string("Tekken 7 is not installed."));
    CHECK_EQ(ended.count, before + 1);
    CHECK(ended.last.kind == TaskKind::kRefusal);

    // Signals and codes, as the old app said them.
    CHECK_EQ(stopped_why(Caps::linux_caps(), 2), std::string("It stopped with code 2 (see Details)"));
    CHECK(stopped_why(Caps::linux_caps(), 137).starts_with("It was stopped: Killed (code 137"));
}

// ---------------------------------------------------------------- the AppImage's update

std::string release_json(const std::string& version, const std::string& digest = {}) {
    return "{\"tag_name\": \"v" + version + "\", \"html_url\": \"https://example.com/v" + version +
           "\", \"assets\": [{\"name\": \"Ultimate_Launcher-x86_64.AppImage\", \"state\": \"uploaded\", "
           "\"size\": 1000, \"browser_download_url\": \"https://example.com/U.AppImage\"" +
           (digest.empty() ? "" : ", \"digest\": \"sha256:" + digest + "\"") + "}]}";
}

struct UpdateRig {
    FakeStarter starter;
    FakeFiles files;
    TaskRunner runner{starter, Caps::linux_caps()};
    SelfUpdate update;
    std::string answer = release_json("0.9.0");
    std::string says = "Ultimate Launcher 0.9.0"; // what the new one's --version prints
    bool version_hangs = false;
    std::vector<Command> opened;
    explicit UpdateRig()
        : update(runner, starter, files,
                 SelfUpdate::Config{fs::path("/home/player/Ultimate_Launcher-x86_64.AppImage"), "0.8.0",
                                    "https://api.example.com/latest", false, "ttt2-launcher/0.8.0", 42}) {
        starter.set_script([this](Run& r) {
            const auto& argv = r.command.argv;
            const auto has = [&](const std::string& a) { return std::find(argv.begin(), argv.end(), a) != argv.end(); };
            if (has("--version")) {
                if (version_hangs) r.held = true;
                else r.lines = {{says, false}};
            } else if (argv[0] == "/home/player/Ultimate_Launcher-x86_64.AppImage") {
                opened.push_back(r.command);
                r.held = true;
            } else if (has("Accept: application/vnd.github+json")) {
                r.lines = {{answer, false}};
            }
        });
    }
};

void self_update() {
    current = "self-update";
    {
        UpdateRig rig;
        ReleaseAnswer seen;
        rig.update.on_release = [&](const ReleaseAnswer& a) { seen = a; };
        CHECK(!rig.update.start(1));
        CHECK(rig.runner.running());
        CHECK_EQ(rig.runner.view().title, std::string("Updating the launcher"));
        rig.starter.pump();
        CHECK(seen.release && seen.release->version == "0.9.0");
        CHECK(!rig.runner.running());
        CHECK(rig.runner.last().ok);
        CHECK_EQ(rig.runner.last().title, std::string("Updated to 0.9.0"));
        CHECK(rig.update.opened());
        CHECK(rig.opened.size() == 1 && rig.opened[0].env.at(kReplacesVariable) == "42");
    }
    {
        UpdateRig rig;
        rig.answer = release_json("0.8.0");
        rig.update.start(1);
        rig.starter.pump();
        CHECK(rig.runner.last().ok);
        CHECK_EQ(rig.runner.last().title, std::string("The launcher is up to date"));
        CHECK_EQ(rig.runner.last().detail, std::string("Version 0.8.0 is the newest."));
        CHECK(!rig.update.opened());
    }
    {
        UpdateRig rig;
        rig.answer = release_json("0.9.0", std::string(64, 'f'));
        rig.update.start(1);
        rig.starter.pump();
        CHECK(!rig.runner.last().ok);
        CHECK_EQ(rig.runner.last().detail,
                 std::string("The download of version 0.9.0 is damaged: its SHA-256 is not GitHub's."));
        CHECK(!rig.files.removed.empty());
        CHECK(rig.opened.empty());
    }
    {
        UpdateRig rig;
        rig.says = "Ultimate Launcher 0.8.5";
        rig.update.start(1);
        rig.starter.pump();
        CHECK_EQ(rig.runner.last().detail, std::string("The AppImage released as version 0.9.0 is version 0.8.5."));
    }
    {
        UpdateRig rig;
        rig.version_hangs = true;
        rig.update.start(1);
        rig.starter.pump();
        CHECK(rig.runner.running());
        rig.update.tick(1 + SelfUpdate::kVersionSeconds + 1);
        rig.starter.pump();
        CHECK(!rig.runner.running());
        CHECK_EQ(rig.runner.last().detail,
                 std::string("Version 0.9.0 does not start: it did not answer within 60 seconds."));
    }
    {
        UpdateRig rig;
        rig.files.cannot = "Read-only file system";
        const auto refused = rig.update.start(1);
        CHECK(refused && refused->why.find("cannot be written to (Read-only file system)") != std::string::npos);
        CHECK(!rig.runner.running());
    }
    {
        UpdateRig rig;
        rig.files.downloader = false;
        const auto refused = rig.update.start(1);
        CHECK(refused && refused->why.starts_with("Downloading needs curl or wget: install curl"));
    }
    {
        UpdateRig rig;
        rig.update.start(1);
        rig.runner.cancel();
        rig.starter.pump();
        CHECK(!rig.runner.running());
        CHECK(rig.runner.last().cancelled);
        CHECK_EQ(rig.runner.last().title, std::string("Update cancelled"));
        CHECK(rig.opened.empty());
    }
}

// ---------------------------------------------------------------- preflight (before an install, Linux)

struct FakeProbe final : Probe {
    bool game = true;
    std::vector<std::string> missing;
    bool compiler = true;
    uint64_t free = 100'000'000'000, work_system = 1;
    bool exists(const fs::path&) override { return game; }
    std::vector<std::string> missing_cpu_features() override { return missing; }
    std::optional<Compiler> find_compiler(std::string* why) override {
        if (compiler) return Compiler{"/usr/bin/clang++", "clang++ 21.1.6"};
        if (why) *why = "no C++ compiler was found";
        return std::nullopt;
    }
    Distro distro() override { return Distro{"arch", "Arch Linux", "", {"arch"}, false}; }
    std::optional<uint64_t> free_space(const fs::path&) override { return free; }
    uint64_t file_system(const fs::path& folder) override { return folder.filename() == "build" ? work_system : 1; }
    uint64_t size_of(const fs::path&) override { return 0; }
};

void preflight() {
    current = "preflight";
    const fs::path game = "/home/player/TTT2.wua", folder = "/home/player/Games/Tekken Tag Tournament 2",
                   work = "/home/player/.cache/ttt2/build";
    FakeProbe probe;
    auto checks = run_checks(game, folder, work, probe);
    CHECK_EQ(checks.size(), size_t(4));
    CHECK(failed_check(checks).empty());
    CHECK_EQ(checks[0].detail, std::string("TTT2.wua"));
    CHECK_EQ(checks[2].detail, std::string("clang++ 21.1.6 (/usr/bin/clang++)"));
    CHECK(checks[3].detail.ends_with("needed (the game, and building its program)"));

    probe.game = false;
    probe.missing = {"avx2", "bmi2", "fma"};
    probe.compiler = false;
    probe.free = 1'000'000'000;
    probe.work_system = 2;
    checks = run_checks(game, folder, work, probe);
    CHECK_EQ(checks.size(), size_t(5));
    CHECK_EQ(failed_check(checks), std::string("Game: /home/player/TTT2.wua does not exist"));
    CHECK(checks[1].detail.starts_with("Lacks avx2, bmi2, fma: the game program needs an x86-64-v3 processor"));
    CHECK_EQ(checks[2].detail, std::string("No C++ compiler was found. The game program is compiled on this PC: install "
                                           "Clang with"));
    CHECK_EQ(checks[2].command, std::string("sudo pacman -S --needed clang"));
    CHECK(checks[3].detail.ends_with("needed (the game): make room on that disk, or choose a folder on another"));
    CHECK_EQ(checks[4].title, std::string("Free space for building"));

    const std::string stopped = stopped_text(139, "one\ntwo\nSegmentation fault\n", "/home/player/game.log", true);
    CHECK(stopped.starts_with("The game stopped with an error (exit code 139). Its last lines:\n"));
    CHECK(stopped.ends_with("\nAll it wrote is in /home/player/game.log."));
}

// ---------------------------------------------------------------- the model, from golden cases' fixtures

json::Value fixture(const fs::path& golden, const std::string& name) {
    return json::parse(read(golden / name / "case.json")).value_or(json::Value());
}

int count_started(const FakeStarter& s, const std::string& what) {
    return static_cast<int>(std::count_if(s.started.begin(), s.started.end(), [&](const Command& c) {
        return std::find(c.argv.begin(), c.argv.end(), what) != c.argv.end();
    }));
}

void model_rules(const fs::path& golden, const fs::path& scratch) {
    const json::Value installed = fixture(golden, "installed");

    current = "refresh coalescing";
    replay(installed, Caps::linux_caps(), scratch / "a", {0, [](Harness& h) {
        const int before = count_started(h.starter, "status");
        CHECK_EQ(before, 1);
        // Asked three times while the first answer is coming: once more after it, not three times.
        h.model.activate("refresh", h.now);
        h.model.activate("refresh", h.now);
        h.model.activate("refresh", h.now);
        CHECK(h.model.facts().status_loading);
        h.settle();
        CHECK_EQ(count_started(h.starter, "status"), before + 2);
        CHECK(!h.model.facts().status_loading);
        // Back in the window: looked at again after 5 s, not before.
        h.now += 1;
        h.model.activated(h.now);
        h.settle();
        CHECK_EQ(count_started(h.starter, "status"), before + 2);
        h.now += LauncherModel::kStatusSeconds + 1;
        h.model.activated(h.now);
        h.settle();
        CHECK_EQ(count_started(h.starter, "status"), before + 3);
        // GitHub (main's news) again only after hours.
        const int main = count_started(h.starter, "main");
        h.now += LauncherModel::kReleaseSeconds + 1;
        h.model.activated(h.now);
        h.settle();
        CHECK_EQ(count_started(h.starter, "main"), main + 1);
    }});

    current = "ownership asked";
    replay(installed, Caps::linux_caps(), scratch / "a", {0, [](Harness& h) {
        CHECK_EQ(count_started(h.starter, "owned"), 1);
        CHECK(h.model.facts().owned.state == OwnedState::kKnown);
        // Not again on a refresh once known.
        h.model.activate("refresh", h.now);
        h.settle();
        CHECK_EQ(count_started(h.starter, "owned"), 1);
    }});
    current = "ownership not asked without Steam";
    replay(fixture(golden, "steam-closed"), Caps::linux_caps(), scratch / "a", {0, [](Harness& h) {
        CHECK_EQ(count_started(h.starter, "owned"), 0);
    }});
    current = "ownership asked again after it failed";
    replay(fixture(golden, "owned-failed"), Caps::linux_caps(), scratch / "a", {0, [](Harness& h) {
        CHECK_EQ(count_started(h.starter, "owned"), 1);
        h.model.activate("refresh", h.now);
        h.settle();
        CHECK_EQ(count_started(h.starter, "owned"), 2);
    }});

    current = "Play reads display.ini when pressed";
    replay(installed, Caps::linux_caps(), scratch / "b", {0, [&](Harness& h) {
        std::ofstream(scratch / "b/display.ini") << "precompile_shaders = yes\n";
        h.model.activate("play", h.now);
        CHECK(h.model.task().running());
        CHECK(h.model.task().spec().kind == TaskKind::kShaders);
        CHECK(count_started(h.starter, "--precompile") == 1);
        h.settle();
        CHECK(h.model.facts().game_started_here);
    }});

    current = "close while a task runs (Linux)";
    replay(fixture(golden, "add-ok"), Caps::linux_caps(), scratch / "c", {0, [](Harness& h) {
        h.starter.set_script([](Run& r) {
            r.lines = {{"@step fighter kazumi 1 1", false}};
            r.held = true;
        });
        h.model.activate("fighter:kazumi", h.now);
        CHECK(h.model.task().running());
        CHECK(h.model.request_close(h.now).empty());
        CHECK(h.model.view().dialog && h.model.view().dialog->id == "stop-and-quit");
        // Keep running: nothing stops.
        h.model.activate("keep-running", h.now);
        CHECK(!h.model.view().dialog);
        CHECK(h.model.task().running());
        h.model.request_close(h.now);
        h.model.activate("stop-and-quit", h.now);
        h.settle();
        CHECK(!h.model.task().running());
        CHECK(std::any_of(h.effects.begin(), h.effects.end(),
                          [](const Effect& e) { return e.kind == Effect::Kind::kQuit; }));
    }});
    current = "close while a task runs (Windows)";
    replay(fixture(golden, "add-ok"), Caps::windows_caps(), scratch / "c", {0, [](Harness& h) {
        h.starter.set_script([](Run& r) { r.held = true; });
        h.model.activate("fighter:kazumi", h.now);
        CHECK(h.model.task().running());
        CHECK(h.model.request_close(h.now).empty());
        CHECK(h.model.view().dialog && h.model.view().dialog->id != "stop-and-quit");
        CHECK(h.model.task().running());
    }});
    current = "close with nothing running";
    replay(installed, Caps::linux_caps(), scratch / "c", {0, [](Harness& h) {
        const auto e = h.model.request_close(h.now);
        CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kQuit);
    }});

    current = "the uninstall dialog's ids";
    replay(installed, Caps::linux_caps(), scratch / "d", {0, [](Harness& h) {
        h.model.activate("uninstall", h.now);
        auto d = h.model.view().dialog;
        CHECK(d && d->id == "uninstall");
        h.model.activate("uninstall-saves", h.now);
        h.model.activate("uninstall-characters", h.now);
        const auto all = actions_of(h.model.view());
        int on = 0;
        for (const Action& a : all) on += (a.id == "uninstall-saves" || a.id == "uninstall-characters") && a.checked;
        CHECK_EQ(on, 2);
        const auto e = h.model.activate("uninstall-confirm", h.now);
        CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kUninstall);
    }});

    current = "a refused add says why";
    replay(fixture(golden, "older-game"), Caps::linux_caps(), scratch / "e", {0, [](Harness& h) {
        h.model.activate("fighter:kazumi", h.now);
        CHECK(!h.model.task().running());
        CHECK_EQ(h.model.task().view().title, std::string("Cannot add characters"));
    }});

    current = "install flow";
    replay(fixture(golden, "not-installed"), Caps::linux_caps(), scratch / "h", {0, [](Harness& h) {
        auto e = h.model.activate("install", h.now);
        CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kChooseGame);
        e = h.model.chosen_game("/home/player/TTT2.wua", h.now);
        CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kChooseFolder);
        e = h.model.chosen_folder("/home/player/Games", h.now);
        CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kRunPreflight);
        CHECK(h.model.facts().preflight && h.model.facts().preflight->running);
        CHECK(h.model.view().game.state == GameState::kChecking);
        // A check failed: said, shown, and nothing starts.
        h.model.preflight_done({{false, "Game", "/home/player/TTT2.wua does not exist", {}}}, h.now);
        CHECK_EQ(h.model.said(), std::string("Game: /home/player/TTT2.wua does not exist"));
        CHECK(!h.model.task().running());
        bool again = false;
        for (const Action& a : actions_of(h.model.view())) again = again || a.id == "check-again";
        CHECK(again);
        // All pass: the install starts (its started record first, for Resume).
        h.model.activate("check-again", h.now);
        h.model.preflight_done({{true, "Game", "TTT2.wua", {}}}, h.now);
        CHECK(h.model.task().running());
        CHECK(h.model.task().spec().kind == TaskKind::kInstall);
        CHECK_EQ(h.env.records.size(), size_t(1));
        const auto& argv = h.model.task().spec().command.argv;
        CHECK(argv.size() == 4 && argv[1] == "install" && argv[2] == "/home/player/TTT2.wua");
    }});

    current = "unknown ids";
    replay(installed, Caps::linux_caps(), scratch / "f", {0, [](Harness& h) {
        h.model.activate("no-such-thing", h.now);
        CHECK_EQ(h.model.said(), std::string("no no-such-thing to activate"));
    }});
}

int activated = 0;

// Every focusable item of every case's first view does something (U14): activated in a fresh replay, it is
// never "no <id> to activate".
void every_id(const fs::path& golden, const fs::path& scratch, const Caps& caps) {
    for (const auto& entry : fs::directory_iterator(golden)) {
        if (!fs::exists(entry.path() / "case.json")) continue;
        const std::string name = entry.path().filename().string();
        current = std::string("every id ") + caps.platform_name + " " + name;
        const json::Value c = fixture(golden, name);
        const CaseRun first = replay(c, caps, scratch / "g", {0, {}});
        std::vector<std::string> ids;
        for (const Action& a : first.actions.at("00-start")) {
            if (!a.id.empty()) ids.push_back(a.id);
        }
        // Settings' too (the same page in every case but for the game's state and the files: in three; its
        // switches write files, slow on a disk).
        if (name == "installed" || name == "not-installed" || name == "settings-files") {
            replay(c, caps, scratch / "g", {0, [&](Harness& h) {
                h.model.activate("settings", h.now);
                for (const Action& a : actions_of(h.model.view())) {
                    if (!a.id.empty() && std::find(ids.begin(), ids.end(), a.id) == ids.end()) ids.push_back(a.id);
                }
            }});
        }
        for (const std::string& id : ids) {
            const bool settings = std::find_if(first.actions.at("00-start").begin(), first.actions.at("00-start").end(),
                                               [&](const Action& a) { return a.id == id; }) ==
                                  first.actions.at("00-start").end();
            replay(c, caps, scratch / "g", {0, [&](Harness& h) {
                if (settings) h.model.activate("settings", h.now);
                h.model.activate(id, h.now);
                ++activated;
                if (h.model.said().starts_with("no ") && h.model.said().ends_with(" to activate")) {
                    fail(__FILE__, __LINE__, id + ": " + h.model.said());
                }
            }});
        }
    }
}

} // namespace

void units(const fs::path& golden, const fs::path& scratch) {
    const int before = failures, made = checks;
    keys();
    display(scratch / "display");
    task_runner();
    self_update();
    preflight();
    model_rules(golden, scratch / "model");
    every_id(golden, scratch / "ids", Caps::linux_caps());
    every_id(golden, scratch / "ids", Caps::windows_caps());
    std::printf("units: %d checks, %d ids activated, %d failed\n", checks - made, activated, failures - before);
}

} // namespace launcher::model::testing
