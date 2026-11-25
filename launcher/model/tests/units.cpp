// model_test's unit tests of the controllers (no goldens): keys,
// display.ini, the task runner, the refresh rules, closing while a task runs,
// the AppImage's update, activate(id).

#include "units.h"

#include "builders.h"
#include "check.h"
#include "fakes.h"
#include "replay.h"
#include "preflight.h"
#include "rules.h"
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

// ---------------------------------------------------------------- keys

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
    k.key_up(kShift, now); // (... let go after: not taken)
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
    CHECK(d.settings().precompile_shaders);  // (on by default)
    std::ofstream(file) << "precompile_shaders = no\n";
    CHECK(!d.read().precompile_shaders);
    CHECK(d.settings().precompile_shaders);

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
    starter.set_script(
        [](Run& r) { r.lines = {{"@step fighter kazumi 1 1", false}, {"@added kazumi", false}, {"@done", false}}; });
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
           "\", \"assets\": [{\"name\": \"Golden_Fist_Launcher-x86_64.AppImage\", \"state\": \"uploaded\", "
           "\"size\": 1000, \"browser_download_url\": \"https://example.com/U.AppImage\"" +
           (digest.empty() ? "" : ", \"digest\": \"sha256:" + digest + "\"") + "}]}";
}

struct UpdateRig {
    FakeStarter starter;
    FakeFiles files;
    TaskRunner runner{starter, Caps::linux_caps()};
    SelfUpdate update;
    std::string answer = release_json("0.9.0");
    std::string says = "Golden Fist Launcher 0.9.0"; // what the new one's --version prints
    bool version_hangs = false;
    std::vector<Command> opened;
    explicit UpdateRig()
        : update(runner, starter, files,
                 SelfUpdate::Config{fs::path("/home/player/Golden_Fist_Launcher-x86_64.AppImage"), "0.8.0",
                                    "https://api.example.com/latest", false, "ttt2-launcher/0.8.0", 42}) {
        starter.set_script([this](Run& r) {
            const auto& argv = r.command.argv;
            const auto has = [&](const std::string& a) { return std::find(argv.begin(), argv.end(), a) != argv.end(); };
            if (has("--version")) {
                if (version_hangs)
                    r.held = true;
                else
                    r.lines = {{says, false}};
            } else if (argv.size() > 4 && argv[0] == "/bin/sh" &&
                       argv[4] == "/home/player/Golden_Fist_Launcher-x86_64.AppImage") {
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
        CHECK(rig.opened.size() == 1 && rig.opened[0].mode == Command::Mode::kDetached); // (it outlives this one)
        // (This version kept before the new one is put in its place; the new one opened through the way back.)
        CHECK((rig.files.steps == std::vector<std::string>{"keep", "replace"}));
        CHECK(rig.opened.size() == 1 &&
              rig.opened[0].argv == open_with_rollback("/home/player/Golden_Fist_Launcher-x86_64.AppImage", "0.9.0"));
        CHECK(rig.opened.size() == 1 && rig.opened[0].argv[5] ==
                                            "/home/player/.Golden_Fist_Launcher-x86_64.AppImage.previous");
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
        rig.says = "Golden Fist Launcher 0.8.5";
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
        // (No copy kept: told in the log, the update goes on.)
        UpdateRig rig;
        rig.files.keep_error = "No space left on device";
        rig.update.start(1);
        rig.starter.pump();
        CHECK(rig.runner.last().ok && rig.opened.size() == 1);
        const auto& log = rig.runner.log();
        CHECK(std::find(log.begin(), log.end(),
                        "No copy of this version is kept to go back to (No space left on device).") != log.end());
    }
    {
        // (It cannot be replaced: the copy kept goes too.)
        UpdateRig rig;
        rig.files.replace_error = "Read-only file system";
        rig.update.start(1);
        rig.starter.pump();
        CHECK(!rig.runner.last().ok && rig.opened.empty());
        CHECK(std::find(rig.files.removed.begin(), rig.files.removed.end(),
                        fs::path("/home/player/.Golden_Fist_Launcher-x86_64.AppImage.previous")) !=
              rig.files.removed.end());
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
    {
        // A test build's newer changes: Update gets its files, never its .exe's program.
        Facts f;
        f.caps = Caps::windows_caps();
        f.self_update = true;
        f.launcher_version = "0.9.0";
        f.windows.branch = "dev-test";
        f.windows.commit = std::string(40, 'a');
        f.main_news = MainNews{};
        f.main_news->ahead = 2;
        f.main_news->changes = {"Faster"};
        NoticeView n = notice_view(f);
        CHECK(n.shown && n.title == "Newer changes are on dev-test");
        CHECK(n.detail.ends_with(". Update gets them.") && n.detail.find("without a new .exe") == std::string::npos);
        f.program_in_exe = true;
        n = notice_view(f);
        CHECK(n.detail.ends_with("Update gets them; changes to the launcher program itself need a new test build."));
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
    CHECK_EQ(checks[2].detail,
             std::string("No C++ compiler was found. The game program is compiled on this PC: install "
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
                                                              // Asked three times while the first answer is coming:
                                                              // once more after it, not three times.
                                                              h.model.activate("refresh", h.now);
                                                              h.model.activate("refresh", h.now);
                                                              h.model.activate("refresh", h.now);
                                                              CHECK(h.model.facts().status_loading);
                                                              h.settle();
                                                              CHECK_EQ(count_started(h.starter, "status"), before + 2);
                                                              CHECK(!h.model.facts().status_loading);
                                                              // Back in the window: looked at again after 5 s, not
                                                              // before.
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
        // Kept for when Steam is closed next time (cache/ttt2/dlc-owned.json, written by the app).
        const auto saved = std::find_if(h.effects.begin(), h.effects.end(),
                                        [](const Effect& e) { return e.kind == Effect::Kind::kSaveOwned; });
        CHECK(saved != h.effects.end() && saved->text.starts_with("{\"owned\": {"));
                                                              // Not again on a refresh once known.
                                                              h.model.activate("refresh", h.now);
                                                              h.settle();
                                                              CHECK_EQ(count_started(h.starter, "owned"), 1);
                                                          }});
    current = "ownership not asked without Steam";
    replay(fixture(golden, "steam-closed"), Caps::linux_caps(), scratch / "a",
           {0, [](Harness& h) { CHECK_EQ(count_started(h.starter, "owned"), 0); }});
    current = "ownership asked again after it failed";
    replay(fixture(golden, "owned-failed"), Caps::linux_caps(), scratch / "a",
           {0, [](Harness& h) {
                CHECK_EQ(count_started(h.starter, "owned"), 1);
                h.model.activate("refresh", h.now);
                h.settle();
                CHECK_EQ(count_started(h.starter, "owned"), 2);
            }});

    current = "Play reads display.ini when pressed";
    replay(installed, Caps::linux_caps(), scratch / "b", {0, [&](Harness& h) {
                                                              std::ofstream(scratch / "b/display.ini")
                                                                  << "precompile_shaders = yes\n";
                                                              h.model.activate("play", h.now);
                                                              CHECK(h.model.task().running());
                                                              CHECK(h.model.task().spec().kind == TaskKind::kShaders);
                                                              CHECK(count_started(h.starter, "--precompile") == 1);
                                                              h.settle();
                                                              CHECK(h.model.facts().game_started_here);
                                                          }});
    current = "Play without the shaders when display.ini says no";
    replay(installed, Caps::linux_caps(), scratch / "b2", {0, [&](Harness& h) {
                                                               std::ofstream(scratch / "b2/display.ini")
                                                                   << "precompile_shaders = no\n";
                                                               h.model.activate("play", h.now);
                                                               CHECK(count_started(h.starter, "--precompile") == 0);
                                                               CHECK(h.model.facts().game_started_here);
                                                           }});
    current = "Play prepares the shaders when display.ini does not say (on by default)";
    replay(installed, Caps::linux_caps(), scratch / "b3", {0, [&](Harness& h) {
                                                               fs::remove(scratch / "b3/display.ini");
                                                               h.model.activate("play", h.now);
                                                               CHECK(h.model.task().spec().kind == TaskKind::kShaders);
                                                               CHECK(count_started(h.starter, "--precompile") == 1);
                                                               h.settle();
                                                               CHECK(h.model.facts().game_started_here);
                                                           }});

    current = "close while a task runs (Linux)";
    replay(fixture(golden, "add-ok"), Caps::linux_caps(), scratch / "c",
           {0, [](Harness& h) {
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
    replay(fixture(golden, "add-ok"), Caps::windows_caps(), scratch / "c",
           {0, [](Harness& h) {
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
    replay(installed, Caps::linux_caps(), scratch / "d",
           {0, [](Harness& h) {
                h.model.activate("uninstall", h.now);
                auto d = h.model.view().dialog;
                CHECK(d && d->id == "uninstall");
                h.model.activate("uninstall-saves", h.now);
                h.model.activate("uninstall-characters", h.now);
                const auto all = actions_of(h.model.view());
                int on = 0;
                for (const Action& a : all)
                    on += (a.id == "uninstall-saves" || a.id == "uninstall-characters") && a.checked;
                CHECK_EQ(on, 2);
                const auto e = h.model.activate("uninstall-confirm", h.now);
                CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kUninstall);
            }});

    current = "a refused add says why";
    replay(fixture(golden, "older-game"), Caps::linux_caps(), scratch / "e",
           {0, [](Harness& h) {
                h.model.activate("fighter:kazumi", h.now);
                CHECK(!h.model.task().running());
                CHECK_EQ(h.model.task().view().title, std::string("Cannot add characters"));
            }});

    current = "install flow";
    replay(fixture(golden, "not-installed"), Caps::linux_caps(), scratch / "h",
           {0, [](Harness& h) {
                auto e = h.model.activate("install", h.now);
                CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kChooseGame);
                e = h.model.chosen_game("/home/player/TTT2.wua", h.now);
                CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kChooseFolder);
                e = h.model.chosen_folder("/home/player/Games", h.now);
                CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kRunPreflight);
                CHECK(h.model.facts().preflight && h.model.facts().preflight->running);
                CHECK(h.model.view().game.state == GameState::kChecking);
                // A check failed: said, shown, and nothing starts.
                h.model.preflight_done({{false, "Game", "/home/player/TTT2.wua does not exist", {}}}, h.now,
                                       e[0].generation);
                CHECK_EQ(h.model.said(), std::string("Game: /home/player/TTT2.wua does not exist"));
                CHECK(!h.model.task().running());
                bool again = false;
                for (const Action& a : actions_of(h.model.view())) again = again || a.id == "check-again";
                CHECK(again);
                // All pass: the install starts (its started record first, for Resume).
                e = h.model.activate("check-again", h.now);
                CHECK(e.size() == 1 && e[0].kind == Effect::Kind::kRunPreflight);
                h.model.preflight_done({{true, "Game", "TTT2.wua", {}}}, h.now, e[0].generation);
                CHECK(h.model.task().running());
                CHECK(h.model.task().spec().kind == TaskKind::kInstall);
                CHECK_EQ(h.env.records.size(), size_t(1));
                const auto& argv = h.model.task().spec().command.argv;
                CHECK(argv.size() == 4 && argv[1] == "install" && argv[2] == "/home/player/TTT2.wua");
            }});

    // An answer goes with its request only.
    current = "a preflight's answer for another folder is dropped";
    replay(fixture(golden, "not-installed"), Caps::linux_caps(), scratch / "h",
           {0, [](Harness& h) {
                h.model.chosen_game("/home/player/TTT2.wua", h.now);
                const auto a = h.model.chosen_folder("/home/player/A", h.now);
                const auto b = h.model.chosen_folder("/home/player/B", h.now);
                CHECK(a.size() == 1 && b.size() == 1 && a[0].generation != b[0].generation);
                // A's checks pass after B was chosen: nothing starts, B is still being checked.
                h.model.preflight_done({{true, "Free space", "A has room", {}}}, h.now, a[0].generation);
                CHECK(!h.model.task().running());
                CHECK(h.model.facts().preflight && h.model.facts().preflight->running &&
                      h.model.facts().preflight->folder == fs::path("/home/player/B/Tekken Tag Tournament 2"));
                // B's: the install goes into B.
                h.model.preflight_done({{true, "Free space", "B has room", {}}}, h.now, b[0].generation);
                CHECK(h.model.task().running());
                const auto& argv = h.model.task().spec().command.argv;
                CHECK(argv.size() == 4 && argv[3] == "/home/player/B/Tekken Tag Tournament 2");
            }});
    current = "a preflight checked again: the earlier answer is dropped";
    replay(fixture(golden, "not-installed"), Caps::linux_caps(), scratch / "h",
           {0, [](Harness& h) {
                h.model.chosen_game("/home/player/TTT2.wua", h.now);
                const auto first = h.model.chosen_folder("/home/player/Games", h.now);
                const auto again = h.model.activate("check-again", h.now);
                CHECK(again.size() == 1 && again[0].generation != first[0].generation);
                h.model.preflight_done({{false, "Free space", "full", {}}}, h.now, first[0].generation);
                CHECK(h.model.facts().preflight && h.model.facts().preflight->running);
                CHECK(h.model.facts().preflight->checks.empty());
                h.model.preflight_done({{true, "Free space", "room", {}}}, h.now, again[0].generation);
                CHECK(h.model.task().running());
                // (An answer that comes twice starts nothing more.)
                h.model.preflight_done({{true, "Free space", "room", {}}}, h.now, again[0].generation);
                CHECK_EQ(count_started(h.starter, "install"), 1);
            }});
    current = "a preflight passing while a task runs starts no install";
    replay(fixture(golden, "not-installed"), Caps::linux_caps(), scratch / "h",
           {0, [](Harness& h) {
                h.model.chosen_game("/home/player/TTT2.wua", h.now);
                const auto e = h.model.chosen_folder("/home/player/Games", h.now);
                TaskSpec other;
                other.kind = TaskKind::kUpdate;
                other.title = "Another task";
                other.command.argv = {"sleep", "100"};
                h.model.task().start(std::move(other), h.now);
                CHECK(h.model.task().running());
                h.model.preflight_done({{true, "Game", "TTT2.wua", {}}}, h.now, e[0].generation);
                CHECK(h.model.task().spec().title == "Another task");
                CHECK_EQ(count_started(h.starter, "install"), 0);
                CHECK_EQ(h.model.said(), std::string("Wait for it to end, then install."));
                // The checks stay, Check Again starts it later.
                CHECK(h.model.facts().preflight && !h.model.facts().preflight->running);
            }});

    // A game started elsewhere is watched until it ends (every kGameWatchSeconds, cheaply).
    current = "a game started elsewhere is watched";
    replay(installed, Caps::linux_caps(), scratch / "a",
           {0, [](Harness& h) {
                CHECK(!h.model.facts().game_running);
                CHECK(h.model.next_tick(h.now) > 1e17);
                h.env.running_outside = true;
                h.model.activate("refresh", h.now);
                h.settle();
                CHECK(h.model.facts().game_running && !h.model.facts().game_started_here);
                CHECK_EQ(h.model.view().game.pill.text, std::string("Running"));
                h.model.tick(h.now);
                const int looks = h.env.game_looks;
                CHECK(looks >= 1);
                CHECK(h.model.next_tick(h.now) <= h.now + LauncherModel::kGameWatchSeconds + 1e-9);
                // It ends: seen within kGameWatchSeconds, without a refresh.
                h.env.running_outside = false;
                h.now += 1;
                h.model.tick(h.now);
                CHECK(h.model.facts().game_running);
                CHECK_EQ(h.env.game_looks, looks);
                h.now += LauncherModel::kGameWatchSeconds;
                h.model.tick(h.now);
                CHECK(!h.model.facts().game_running);
                CHECK_EQ(h.env.game_looks, looks + 1);
                CHECK_EQ(h.model.view().game.pill.text, std::string("Installed"));
                // Nothing to watch now: no more looks.
                h.now += 10;
                h.model.tick(h.now);
                CHECK_EQ(h.env.game_looks, looks + 1);
                CHECK(h.model.next_tick(h.now) > 1e17);
            }});
    current = "a game started here is not looked for";
    replay(installed, Caps::linux_caps(), scratch / "a",
           {0, [](Harness& h) {
                h.model.activate("play", h.now);
                h.settle();  // (the shaders first: on by default)
                CHECK(h.model.facts().game_running && h.model.facts().game_started_here);
                const int looks = h.env.game_looks;
                h.now += 10;
                h.model.tick(h.now);
                CHECK_EQ(h.env.game_looks, looks);
                CHECK(h.model.next_tick(h.now) > 1e17);
            }});

    current = "Windows' commands";
    {
        Facts f;
        f.caps = Caps::windows_caps();
        f.python = "/w/python/python.exe";
        f.windows.root = "/w/files";
        f.windows.build = "/w/files/build-windows-tools";
        f.windows.config = "/w/files/local/windows-launcher.json";
        f.windows.logs = "/w/TTT2Ultimate/logs";
        WindowsCommands w;
        w.stamp = [] { return std::string("20261124-140501-123456"); };
        const Command import = w.import(f, {"kazumi", "geese"}, "geese");
        const std::vector<std::string> expected = {"/w/python/python.exe",
                                                   "-u",
                                                   "/w/files/launcher/windows/main.py",
                                                   "--build-dir",
                                                   "/w/files/build-windows-tools",
                                                   "--config",
                                                   "/w/files/local/windows-launcher.json",
                                                   "--worker",
                                                   "import",
                                                   "--cancel-file",
                                                   "/w/TTT2Ultimate/logs/import-20261124-140501-123456.cancel",
                                                   "--outfits",
                                                   "geese",
                                                   "kazumi",
                                                   "geese"};
        CHECK(import.argv == expected);
        CHECK_EQ(import.log_file.string(), std::string("/w/TTT2Ultimate/logs/import-20261124-140501-123456.log"));
        CHECK_EQ(import.cwd.string(), std::string("/w/files"));
        const auto status = w.status(f);
        CHECK(status && status->argv.size() == 9 && status->argv[7] == "--query" && status->argv[8] == "status");
        CHECK(!w.main_news(f)); // (no commit known: a project ZIP)
        CHECK(w.worker(f, TaskKind::kSetup)->argv[8] == "setup");
        CHECK(w.worker(f, TaskKind::kUpdate)->argv[8] == "upgrade");
        CHECK(w.worker(f, TaskKind::kUpdateInstalled)->argv[8] == "update");
        CHECK(!w.worker(f, TaskKind::kUninstall));
        CHECK(w.remove(f, {"kazumi"}).argv.back() == "kazumi");
        // The new launcher's other questions (launcher/windows/query.py).
        CHECK(!w.release(f)); // (no release .exe: nothing to update)
        f.self_update = true;
        CHECK(w.release(f) && w.release(f)->argv.back() == "release" && w.release(f)->argv[7] == "--query");
        const Command check = w.check(f, "import", {"kazumi", "geese"});
        const std::vector<std::string> check_tail = {"--query", "check", "--action", "import", "kazumi", "geese"};
        CHECK(std::vector<std::string>(check.argv.end() - 6, check.argv.end()) == check_tail);
        CHECK(check.input.empty() && check.mode == Command::Mode::kTask);
        const Command save = w.save_settings(f, {{"data", "C:\\Users\\Jos\xc3\xa9\\TTT2Ultimate"}, {"packs", "a\"b"}});
        CHECK_EQ(save.argv.back(), std::string("save-settings"));
        CHECK_EQ(save.input, std::string("{\"data\": \"C:\\\\Users\\\\Jos\\u00e9\\\\TTT2Ultimate\", \"packs\": \"a\\\"b\"}"));
        CHECK_EQ(json::quote("\xf0\x9f\x8e\xae\x01\xff"), std::string("\"\\ud83c\\udfae\\u0001\\ufffd\""));
        // How each runs (core/subprocess.h): the update workers never in a job nor killed, the rest tasks.
        CHECK(import.mode == Command::Mode::kTask && status->mode == Command::Mode::kTask);
        CHECK(w.worker(f, TaskKind::kLauncherUpdate)->mode == Command::Mode::kSelfUpdate);
        CHECK(w.worker(f, TaskKind::kLauncherFiles)->mode == Command::Mode::kSelfUpdate);
        CHECK(w.worker(f, TaskKind::kSetup)->mode == Command::Mode::kTask);
        // (A test build's files update: told when the program is the .exe's, which only opens newer files:
        // self_update.py then refuses changes to the program.)
        CHECK(!w.worker(f, TaskKind::kLauncherFiles)->env.count("TTT2_LAUNCHER_PROGRAM_IN_EXE"));
        f.program_in_exe = true;
        CHECK_EQ(w.worker(f, TaskKind::kLauncherFiles)->env.at("TTT2_LAUNCHER_PROGRAM_IN_EXE"), std::string("1"));
        CHECK(!w.worker(f, TaskKind::kLauncherUpdate)->env.count("TTT2_LAUNCHER_PROGRAM_IN_EXE"));
        f.program_in_exe = false;
        Facts linux_facts;
        linux_facts.install.folder = "/games/ttt2";
        LinuxCommands l;
        CHECK(l.play(linux_facts)->mode == Command::Mode::kDetached); // (the game outlives the launcher)
    }
    replay(fixture(golden, "add-ok"), Caps::windows_caps(), scratch / "i",
           {0, [](Harness& h) {
                h.model.activate("fighter:kazumi", h.now);
                CHECK(h.model.task().running());
                CHECK(!h.model.task().spec().command.cancel_file.empty());
                h.settle();
                CHECK(h.model.task().last().ok);
                CHECK_EQ(h.model.task().last().title, std::string("Added Kazumi Mishima"));
                // Linux-only items are not there to activate.
                h.model.activate("get-packages", h.now);
                CHECK_EQ(h.model.said(), std::string("no get-packages to activate"));
                h.model.activate("uninstall", h.now);
                CHECK(!h.model.view().dialog);
            }});

    current = "unknown ids";
    replay(installed, Caps::linux_caps(), scratch / "f", {0, [](Harness& h) {
                                                              h.model.activate("no-such-thing", h.now);
                                                              CHECK_EQ(h.model.said(),
                                                                       std::string("no no-such-thing to activate"));
                                                          }});
}

int activated = 0;

// Every focusable item of every case's first view does something: activated in a fresh replay, it is
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
            replay(c, caps, scratch / "g",
                   {0, [&](Harness& h) {
                        h.model.activate("settings", h.now);
                        for (const Action& a : actions_of(h.model.view())) {
                            if (!a.id.empty() && std::find(ids.begin(), ids.end(), a.id) == ids.end())
                                ids.push_back(a.id);
                        }
                    }});
        }
        for (const std::string& id : ids) {
            const bool settings =
                std::find_if(first.actions.at("00-start").begin(), first.actions.at("00-start").end(),
                             [&](const Action& a) { return a.id == id; }) == first.actions.at("00-start").end();
            replay(c, caps, scratch / "g",
                   {0, [&](Harness& h) {
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

// Windows: Set Up Game's folders saved and every task checked (main.py --query save-settings / check) before it
// starts, each refusal in the player's words; the launcher's own update cannot be cancelled once it is replacing.
void windows_before(const fs::path& scratch) {
    current = "Windows: saved and checked before a task";
    Facts f;
    f.caps = Caps::windows_caps();
    f.python = "/w/python/python.exe";
    f.windows.root = "/w/files";
    f.windows.build = "/w/files/build-windows-tools";
    f.windows.config = "/w/files/local/windows-launcher.json";
    f.windows.logs = "/w/TTT2Ultimate/logs";
    f.windows.folders = {{"source", ""}, {"install", ""}, {"data", "/w/TTT2Ultimate"}};
    FakeEnvironment env;
    std::vector<std::string> queries; // (each program's --query or --worker word)
    std::string check_code, save_code;
    FakeStarter starter([&](Run& r) {
        const auto& a = r.command.argv;
        for (size_t i = 0; i + 1 < a.size(); ++i)
            if (a[i] == "--query" || a[i] == "--worker") queries.push_back(a[i + 1]);
        r.lines = {{"Some line a module printed first", false}, {"answer", false}};
    });
    WindowsCommands commands;
    commands.stamp = [] { return std::string("20261124-190000-1"); };
    fs::create_directories(scratch);
    KeyFile keys(scratch / "keyboard.ini");
    LauncherModel::Parts parts{commands, starter, env, keys, nullptr, {}, {}, us_key_label, {}, {}};
    parts.read_save = [&](const std::string& out, std::string*) -> std::optional<SetupProblem> {
        if (out.find("answer") == std::string::npos) return std::nullopt;
        return SetupProblem{save_code, save_code.empty() ? "" : "data", "", ""};
    };
    parts.read_check = [&](const std::string& out, std::string*) -> std::optional<SetupProblem> {
        if (out.find("answer") == std::string::npos) return std::nullopt;
        return SetupProblem{check_code, "", "", ""};
    };
    LauncherModel model(f, parts);
    double now = 100;
    const auto settle = [&] {
        for (int i = 0; i < 50; ++i) {
            starter.pump();
            model.tick(now += 0.05);
        }
    };
    settle();
    queries.clear();

    // Set Up Game: the folders chosen, confirmed: saved, checked, then the worker.
    model.chosen_game("/w/Downloads/TTT2.wua", now);
    model.chosen_folder("/w/Games/TTT2", now);
    CHECK(model.view().dialog && model.view().dialog->id == "setup");
    check_code = "installer_letters";
    model.activate("setup-confirm", now);
    settle();
    CHECK(queries.size() == 2 && queries[0] == "save-settings" && queries[1] == "check");
    CHECK(!model.task().running());
    CHECK_EQ(model.task().view().title, std::string("Setting up the game: not started"));
    CHECK(!model.task().view().detail.empty());

    check_code.clear();
    queries.clear();
    model.activate("setup-confirm", now); // (the dialog is gone: nothing)
    model.chosen_folder("/w/Games/TTT2", now);
    model.activate("setup-confirm", now);
    settle();
    // (then the status asked again: what the task changed)
    CHECK(queries.size() >= 3 && queries[0] == "save-settings" && queries[1] == "check" && queries[2] == "setup");
    CHECK_EQ(model.task().view().title, std::string("The game is set up"));

    // A refused save says which folder, in words.
    save_code = "data_name";
    queries.clear();
    model.chosen_folder("/w/Games/TTT2", now);
    model.activate("setup-confirm", now);
    settle();
    CHECK(queries.size() == 1 && queries[0] == "save-settings");
    CHECK_EQ(model.task().view().title, std::string("Setting up the game: not started"));

    current = "Windows: every check's sentence";
    for (const char* code : {"inputs", "tools_folder", "installer_letters", "tools_letters", "project_length",
                             "tools_length", "no_build", "no_install", "no_paths", "no_fighters", "title"}) {
        const std::string text = setup_problem_text({code, "install", "é", "C:/Games/é"});
        CHECK(!text.empty() && text.back() == '.' && text.find(code) == std::string::npos);
    }
    CHECK(setup_problem_text({"installer_letters", "install", "é", "C:/Games/é"}).find("é") != std::string::npos);
    for (const char* code : {"data_name", "relative"}) {
        const std::string text = save_problem_text({code, "data", "", ""});
        CHECK(!text.empty() && text.back() == '.' && text.find(code) == std::string::npos);
    }

    current = "Windows: no Cancel once the new launcher is put in place";
    FakeStarter held;
    held.set_script([](Run& r) {
        r.lines = {{"@step update Downloading the new launcher", false}, {"@step update Putting it in place", false}};
        r.held = true;
    });
    TaskRunner t(held, Caps::windows_caps());
    TaskSpec spec;
    spec.kind = TaskKind::kLauncherUpdate;
    spec.title = "Updating the launcher";
    spec.command.argv = {"python.exe", "main.py", "--worker", "launcher"};
    CHECK(t.start(spec, now));
    held.pump();
    t.tick(now);
    CHECK(!t.cancellable());
    CHECK(t.view().button.label.empty());
}

// ---------------------------------------------------------------- Home's UPDATE (the launcher, the game, the fighters)

const Action* action_in(const View& v, const std::string& id) {
    for (const Action& a : v.game.actions)
        if (a.id == id) return &a;
    return nullptr;
}

bool has_arg(const Command& c, const std::string& a) {
    return std::find(c.argv.begin(), c.argv.end(), a) != c.argv.end();
}
bool is_build(const Command& c) { return !c.argv.empty() && fs::path(c.argv[0]).filename() == "ttt2-build"; }
bool is_import(const Command& c) {
    return std::any_of(c.argv.begin(), c.argv.end(),
                       [](const std::string& a) { return fs::path(a).filename() == "import_character.py"; });
}
int count_runs(const FakeStarter& s, const std::function<bool(const Command&)>& which) {
    return static_cast<int>(std::count_if(s.started.begin(), s.started.end(), which));
}

void update_all(const fs::path& golden, const fs::path& scratch) {
    // -- the plan, each combination
    current = "update plan: the fighters alone";
    const json::Value installed = fixture(golden, "installed");
    replay(installed, Caps::linux_caps(), scratch / "p1", {0, [](Harness& h) {
        const UpdatePlan p = update_plan(h.model.facts());
        CHECK(!p.launcher && !p.game && p.fighters == std::vector<std::string>{"josie"} && p.later.empty());
        const View v = h.model.view();
        const Action* all = action_in(v, "update-everything");
        const Action* play = action_in(v, "play");
        CHECK(all && all->primary && all->enabled && all->label == "Update");
        CHECK(play && !play->primary && play->enabled); // (an ordinary entry)
        CHECK(!action_in(v, "update"));                  // (nothing of the game's own to update)
        CHECK(v.game.update.size() == 1 && v.game.update[0].kind == "fighters");
        CHECK_EQ(v.game.update[0].text,
                 display_name(h.model.facts(), "josie") + " gets the newest pack, made from your own Tekken 7.");
        CHECK_EQ(all->describe.explain, std::string("One part to bring up to date:"));
    }});
    current = "update plan: the game program and the fighters";
    replay(fixture(golden, "update-ready"), Caps::linux_caps(), scratch / "p2", {0, [](Harness& h) {
        const UpdatePlan p = update_plan(h.model.facts());
        CHECK(!p.launcher && p.game && p.game_for == "0.8.0" && p.fighters.size() == 1);
        const View v = h.model.view();
        CHECK(!action_in(v, "update")); // (UPDATE does the game's: no second Update competes)
        CHECK(action_in(v, "play") && !action_in(v, "play")->primary);
        CHECK(v.game.update.size() == 2 && v.game.update[0].kind == "game" && v.game.update[1].kind == "fighters");
        CHECK(v.game.update.size() == 2 && v.game.update[0].text == "Built again for 0.8.0, from the game in its "
                                                                     "folder: a few minutes. Saves and settings stay.");
        CHECK_EQ(action_in(v, "update-everything")->describe.explain,
                 std::string("2 parts, brought up to date one after another:"));
    }});
    current = "update plan: the launcher, the game program and the fighters";
    replay(fixture(golden, "newer-release"), Caps::linux_caps(), scratch / "p3", {0, [](Harness& h) {
        const UpdatePlan p = update_plan(h.model.facts());
        CHECK(p.launcher && p.launcher_from == "0.8.0" && p.launcher_to == "0.9.0");
        CHECK(p.game && p.game_for == "0.9.0"); // (the new launcher builds it again for itself)
        const View v = h.model.view();
        CHECK(v.game.update.size() == 3 && v.game.update[0].title == "Golden Fist Launcher 0.8.0 → 0.9.0");
        CHECK(v.game.update.size() == 3 &&
              v.game.update[0].text == "Downloads 0.9.0 in place of this AppImage, which then restarts by itself and "
                                       "goes on.");
        CHECK(v.game.update.size() == 3 && v.game.update[1].text.starts_with("Built again by the new launcher, "));
        // (The notice's Update is the launcher's alone: Home's says it does all, and the app shows only that one.)
        CHECK(v.notice.shown && v.notice.whole);
        CHECK(v.notice.detail.ends_with("Update on Home gets it first, then brings the game program and the fighters "
                                        "up to date."));
    }});
    current = "update plan: an older game (no Play)";
    replay(fixture(golden, "older-game"), Caps::linux_caps(), scratch / "p4", {0, [](Harness& h) {
        const UpdatePlan p = update_plan(h.model.facts());
        // (Its fighters wait for the game no more: the game's part comes first.)
        CHECK(p.game && p.fighters.size() == 1 && p.later.empty());
        const View v = h.model.view();
        CHECK(!action_in(v, "play") && !action_in(v, "update"));
        CHECK(action_in(v, "update-everything") && action_in(v, "update-everything")->primary);
    }});
    current = "update plan: fighters partly left for later";
    replay(installed, Caps::linux_caps(), scratch / "p5", {0, [](Harness& h) {
        Facts f = h.model.facts();
        f.status->steam_running = false;
        f.status->heihachi_saved = true;
        std::string dlc_name;
        for (Fighter& x : f.status->fighters) {
            if (x.name == "josie") x.moveset_saved = true; // (saved before: no Steam needed)
            if (x.dlc != 0 && !x.of(kTekken8) && dlc_name.empty() && owns(f, x) == true) {
                x.installed = x.update = true;
                x.outdated = x.newer = false;
                dlc_name = x.name;
            }
        }
        CHECK(!dlc_name.empty());
        const UpdatePlan p = update_plan(f);
        CHECK(p.fighters == std::vector<std::string>{"josie"});
        CHECK(p.later.size() == 1 && p.later[0].first == display_name(f, dlc_name) &&
              p.later[0].second == "Start Steam: it checks that you own their DLC");
        const auto parts = update_parts(f, p);
        CHECK(parts.size() == 2 && parts[1].kind == "later" && parts[1].title == "Left for later" &&
              parts[1].text == display_name(f, dlc_name) + " (Start Steam: it checks that you own their DLC).");
        // (Only fighters that cannot be done: nothing for UPDATE, Play is suggested again.)
        for (Fighter& x : f.status->fighters)
            if (x.name == "josie") x.moveset_saved = false;
        CHECK(update_plan(f).empty() && update_plan(f).later.size() == 2);
        // (Steam runs, but which DLC is owned is not known: that is why, not Steam. Not owned: not listed.)
        f.status->steam_running = true;
        for (Fighter& x : f.status->fighters)
            if (x.name == "josie") x.update = false;
        const std::string dlc = [&] {
            for (const Fighter& x : f.status->fighters)
                if (display_name(f, x.name) == p.later[0].first) return x.name;
            return std::string();
        }();
        f.owned.answer.erase(dlc);
        f.owned.errors.clear();
        f.owned.state = OwnedState::kKnown;
        CHECK(update_plan(f).fighters.empty() && update_plan(f).later.size() == 1 &&
              update_plan(f).later[0].second == "Which Tekken 7 DLC you own is not known yet");
        f.owned.errors["tekken7"] = "the helper failed";
        CHECK(update_plan(f).later.size() == 1 &&
              update_plan(f).later[0].second ==
                  "Steam could not be asked through Tekken 7 (the helper failed): Refresh asks it again");
        f.owned.answer[dlc] = false;
        CHECK(update_plan(f).fighters.empty() && update_plan(f).later.empty());
        f.owned.answer[dlc] = true;
        CHECK(update_plan(f).fighters == std::vector<std::string>{dlc} && update_plan(f).later.empty());
    }});
    current = "update plan: nothing pending";
    replay(fixture(golden, "appimage-current"), Caps::linux_caps(), scratch / "p6", {0, [](Harness& h) {
        Facts f = h.model.facts();
        for (Fighter& x : f.status->fighters) x.update = false;
        CHECK(update_plan(f).empty());
    }});

    // -- the chain
    const json::Value ready = fixture(golden, "update-ready");
    current = "update chain: the game program, then the fighters";
    replay(ready, Caps::linux_caps(), scratch / "c1", {0, [&](Harness& h) {
        bool hold = true;
        h.starter.set_script([&](Run& r) {
            fixture_answer(ready, r);
            if (is_build(r.command) && hold) r.held = true;
        });
        h.model.activate("update-everything", h.now);
        CHECK(h.model.task().running() && h.model.task().spec().kind == TaskKind::kUpdate);
        CHECK(h.model.in_update() && h.model.update_goes_on());
        TaskView::Chain ch = h.model.view().task.chain;
        CHECK(ch.at == 1 && ch.count == 2 && ch.part == "The game program" && ch.next.size() == 1 &&
              ch.next[0].kind == "fighters" && !ch.done && !ch.waiting);
        hold = false;
        h.starter.set_script([&](Run& r) { fixture_answer(ready, r); });
        // (The held build ends.)
        h.model.task().cancel();
        h.settle();
        CHECK(!h.model.task().running());
        ch = h.model.view().task.chain;
        CHECK(ch.stopped && ch.at == 1 && !ch.done);
        CHECK_EQ(count_runs(h.starter, is_import), 0); // (a stopped part: the next never starts)
        // Try Again: from the part that stopped.
        h.model.activate("task", h.now); // (Close, as the app does first)
        h.model.activate("update-resume", h.now);
        h.settle();
        ch = h.model.view().task.chain;
        CHECK(ch.done && ch.count == 2 && !h.model.update_goes_on());
        CHECK_EQ(ch.summary, "Updated: the game program and " + display_name(h.model.facts(), "josie"));
        CHECK_EQ(count_runs(h.starter, is_build), 2);
        CHECK_EQ(count_runs(h.starter, is_import), 1);
        CHECK_EQ(h.model.updates_done(), 1); // (one sound for the whole update)
        CHECK(h.model.task().last().ok);
    }});
    current = "update chain: a failed part, Try Again goes on from it";
    replay(ready, Caps::linux_caps(), scratch / "c2", {0, [&](Harness& h) {
        int imports = 0;
        h.starter.set_script([&](Run& r) {
            fixture_answer(ready, r);
            if (is_import(r.command) && imports++ == 0) {
                r.lines = {{"@error Tekken 7 did not answer", false}};
                r.code = 1;
            }
        });
        h.model.activate("update-everything", h.now);
        h.settle();
        TaskView::Chain ch = h.model.view().task.chain;
        CHECK(ch.stopped && ch.at == 2 && ch.count == 2 && ch.part == "Fighters" && !ch.done);
        CHECK(!h.model.task().last().ok && !h.model.update_goes_on());
        CHECK_EQ(h.model.updates_done(), 0);
        h.model.activate("task", h.now);
        h.model.activate("update-resume", h.now);
        h.settle();
        ch = h.model.view().task.chain;
        CHECK(ch.done && ch.at == 2 && ch.count == 2);
        CHECK_EQ(count_runs(h.starter, is_build), 1); // (the game's part done stays done)
        CHECK_EQ(count_runs(h.starter, is_import), 2);
        CHECK_EQ(h.model.updates_done(), 1);
    }});
    current = "update chain: Cancel between two parts";
    replay(ready, Caps::linux_caps(), scratch / "c3", {0, [&](Harness& h) {
        h.model.activate("update-everything", h.now);
        // (The build's lines and end, without the tick that starts the next part.)
        h.starter.pump();
        CHECK(!h.model.task().running());
        CHECK(h.model.view().task.chain.waiting && h.model.in_update());
        h.model.activate("task", h.now);
        h.settle();
        const TaskView::Chain ch = h.model.view().task.chain;
        CHECK(ch.stopped && ch.at == 2 && !ch.waiting);
        CHECK_EQ(count_runs(h.starter, is_import), 0);
        // A new UPDATE starts from its first part again.
        h.model.activate("task", h.now);
        h.model.activate("update-everything", h.now);
        CHECK(h.model.view().task.chain.at == 1);
    }});
    current = "update chain: another task between, the result is not the update's";
    replay(installed, Caps::linux_caps(), scratch / "c4", {0, [&](Harness& h) {
        h.model.activate("update-everything", h.now);
        h.settle();
        CHECK(h.model.view().task.chain.done && h.model.view().task.chain.count == 1);
        h.model.activate("task", h.now);
        h.model.activate("get-packages", h.now);
        h.settle();
        CHECK_EQ(h.model.view().task.chain.count, 0);
    }});

    // -- the launcher's part (Linux: the AppImage) and the hand-over
    const json::Value newer = fixture(golden, "newer-release");
    const auto appimage_script = [&](std::vector<Command>& opened) {
        return [&](Run& r) {
            if (has_arg(r.command, "--version")) {
                r.lines = {{"Golden Fist Launcher 0.9.0", false}};
            } else if (r.command.argv.size() > 4 && r.command.argv[0] == "/bin/sh") {
                opened.push_back(r.command);
                r.held = true;
            } else {
                fixture_answer(newer, r);
            }
        };
    };
    current = "update chain: the launcher's part hands over to the new launcher";
    replay(newer, Caps::linux_caps(), scratch / "c5", {0, [&](Harness& h) {
        std::vector<Command> opened;
        h.starter.set_script(appimage_script(opened));
        h.model.activate("update-everything", h.now);
        CHECK(h.model.task().spec().kind == TaskKind::kLauncherUpdate);
        CHECK(h.model.view().task.chain.at == 1 && h.model.view().task.chain.count == 3);
        h.settle();
        CHECK(opened.size() == 1 && opened[0].env.count(kContinueVariable) &&
              opened[0].env.at(kContinueVariable) == "update");
        CHECK(opened.size() == 1 && opened[0].env.count(kReplacesVariable));
        CHECK(h.model.view().task.chain.handed_over && h.model.update_goes_on());
        CHECK_EQ(h.model.updates_done(), 0); // (the sound is the new launcher's, at its end)
        CHECK(std::any_of(h.effects.begin(), h.effects.end(),
                          [](const Effect& e) { return e.kind == Effect::Kind::kQuit; }));
        CHECK_EQ(count_runs(h.starter, is_build), 0); // (the new one builds it for itself)
    }});
    current = "update chain: the header's Update alone opens the new launcher without going on";
    replay(newer, Caps::linux_caps(), scratch / "c6", {0, [&](Harness& h) {
        std::vector<Command> opened;
        h.starter.set_script(appimage_script(opened));
        h.model.activate("notice-update", h.now);
        h.settle();
        CHECK(opened.size() == 1 && !opened[0].env.count(kContinueVariable));
        CHECK_EQ(h.model.view().task.chain.count, 0);
    }});
    current = "update chain: Windows' launcher part opens the new .exe to go on";
    replay(newer, Caps::windows_caps(), scratch / "c7", {0, [&](Harness& h) {
        Facts& f = h.model.mutable_facts();
        f.self_update = true;
        if (!f.newer) f.newer = Release{"0.9.0", "v0.9.0", "https://example.com/v0.9.0", "a.exe", "", 1000, ""};
        h.starter.set_script([&](Run& r) {
            fixture_answer(newer, r);
            if (has_arg(r.command, "launcher")) r.lines = {{"@launcher-updated 0.9.0", false}};
        });
        CHECK(update_plan(h.model.facts()).launcher);
        h.model.activate("update-everything", h.now);
        h.settle();
        const auto open = std::find_if(h.effects.begin(), h.effects.end(),
                                       [](const Effect& e) { return e.kind == Effect::Kind::kOpenUpdated; });
        CHECK(open != h.effects.end() && open->go_on && open->text == "0.9.0");
        CHECK(h.model.view().task.chain.handed_over);
        // (It could not be opened: the update stops here.)
        h.model.opened_updated("The file is in use", h.now);
        CHECK(h.model.view().task.chain.stopped && !h.model.view().task.chain.handed_over);
    }});

    // -- the new launcher goes on (kContinueVariable)
    current = "update continued: the rest starts by itself once the launcher has looked";
    replay(ready, Caps::linux_caps(), scratch / "k1", {0, [&](Harness& h) {
        h.starter.set_script([&](Run& r) {
            fixture_answer(ready, r);
            if (is_build(r.command)) r.held = true;
        });
        h.model.continue_update(h.now);
        h.model.tick(h.now);
        CHECK(h.model.task().running() && h.model.task().spec().kind == TaskKind::kUpdate);
        const TaskView::Chain ch = h.model.view().task.chain;
        CHECK(ch.at == 2 && ch.count == 3 && ch.part == "The game program");
        CHECK(ch.next.size() == 1 && ch.next[0].kind == "fighters");
    }});
    current = "update continued: not without the variable";
    replay(ready, Caps::linux_caps(), scratch / "k2", {0, [&](Harness& h) {
        h.now += 10;
        h.model.tick(h.now);
        CHECK(!h.model.task().running() && !h.model.in_update());
    }});
    current = "update continued: never the launcher's part again (a newer release listed)";
    replay(newer, Caps::linux_caps(), scratch / "k3", {0, [&](Harness& h) {
        std::vector<Command> opened;
        h.starter.set_script(appimage_script(opened));
        h.model.continue_update(h.now);
        h.settle();
        CHECK(opened.empty() && h.model.task().last().kind == TaskKind::kImport);
        const TaskView::Chain ch = h.model.view().task.chain;
        CHECK(ch.done && ch.count == 2);
        CHECK_EQ(ch.summary, "Updated: launcher 0.8.0 and " + display_name(h.model.facts(), "josie"));
        CHECK_EQ(h.model.updates_done(), 1);
    }});
    current = "update continued: waits while something is asked, gives up in time";
    replay(ready, Caps::linux_caps(), scratch / "k4", {0, [&](Harness& h) {
        h.model.activate("uninstall", h.now); // (a dialog open: not settled)
        h.model.continue_update(h.now);
        h.model.tick(h.now);
        CHECK(!h.model.task().running());
        h.now += LauncherModel::kContinueSeconds + 1;
        h.model.tick(h.now);
        h.model.activate("uninstall-cancel", h.now);
        h.model.tick(h.now);
        CHECK(!h.model.task().running() && !h.model.in_update());
    }});
}

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
    windows_before(scratch / "windows-before");
    update_all(golden, scratch / "update-all");
    std::printf("units: %d checks, %d ids activated, %d failed\n", checks - made, activated, failures - before);
}

} // namespace launcher::model::testing
