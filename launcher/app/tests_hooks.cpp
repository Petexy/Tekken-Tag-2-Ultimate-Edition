// The test hooks (spec/linux_app.md 6.2, 6.3): TTT2_LAUNCHER_TEST_ACTIONS played one after another through the
// same code as the window's items, each once everything has settled (nothing busy, 400 ms, two frames), with
// "@test <action> started" / "@test <action> ok|failed <words>" on standard error and a picture per step in
// TTT2_LAUNCHER_TEST_SHOTS (00-start, NN-<label>, -running at half the progress, -stopping when a test cancels);
// TTT2_LAUNCHER_TEST_CANCEL=<fraction> and TTT2_LAUNCHER_TEST_CANCEL_FILE=<file> press Cancel. --screenshot saves
// the window once the actions are done and everything has settled, then quits.

#include "app.h"

#include "display.h"
#include "keymap.h"
#include "rules.h"
#include "settings.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>

namespace launcher::app {

using namespace ttt2::ui;

namespace {

std::string one_line(std::string s) {
    for (char& c : s)
        if (c == '\n' || c == '\r') c = ' ';
    return s;
}

bool is_task_action(const std::string& n) {
    return n == "update" || n == "update-launcher" || n == "add" || n == "add-all-base" || n == "add-all" ||
           n == "add-all-owned" || n == "remove" || n == "remove-all" || n == "uninstall" || n == "get-packages";
}

} // namespace

bool App::settled(double t) const {
    return t - idle_since_ >= 0.4 && frames_idle_ >= 2;
}

void App::shot(const std::string& name) {
    if (o_.shots.empty()) return;
    std::string error;
    const fs::path file = o_.shots / (name + ".png");
    if (!window_.screenshot(file.string(), &error)) std::fprintf(stderr, "@test shot failed %s\n", error.c_str());
}

void App::test_said(bool ok, const std::string& message) {
    std::fprintf(stderr, "@test %s %s%s%s\n", test_now_.text.c_str(), ok ? "ok" : "failed", message.empty() ? "" : " ",
                 one_line(message).c_str());
    std::fflush(stderr);
    test_wait_ = TestWait::kSettle;
}

// While a task runs: its picture at half the progress (as the screen shows it), Cancel when the test says so
// (TTT2_LAUNCHER_TEST_CANCEL: at that part of the progress, -1 at the first step; or once ..._CANCEL_FILE exists;
// TTT2_LAUNCHER_TEST_QUIT_AT: see below).
void App::test_watch_task() {
    const m::TaskRunner& r = model_->task();
    if (!r.running()) return;
    const double fraction = task_fraction();
    if (!test_running_shot_ && fraction >= 0.5) {
        test_running_shot_ = true;
        shot(test_label_ + "-running");
    }
    // TTT2_LAUNCHER_TEST_QUIT_AT: the window's Quit at that part of the progress; its question's picture
    // (-quit), then Keep Running (the task goes on).
    if (const char* at = std::getenv("TTT2_LAUNCHER_TEST_QUIT_AT"); at && *at && test_quit_ < 2) {
        if (test_quit_ == 0 && fraction >= std::atof(at)) {
            test_quit_ = 1;
            test_quit_at_ = now() + 0.8;
            activate("quit");
        } else if (test_quit_ == 1 && now() >= test_quit_at_) {
            test_quit_ = 2;
            shot(test_label_ + "-quit");
            std::fprintf(stderr, "@test quit-while-running %s\n", view_.dialog ? "asks" : "does not ask");
            if (view_.dialog) handle(model_->activate("keep-running", now()));
        }
        if (test_quit_ == 1) return;
    }
    if (test_cancelled_) return;
    bool cancel = false;
    if (const char* at = std::getenv("TTT2_LAUNCHER_TEST_CANCEL"); at && *at) {
        const double want = std::atof(at);
        cancel = want < 0 ? !r.progress_state().step().empty() : fraction >= want;
    }
    if (const char* file = std::getenv("TTT2_LAUNCHER_TEST_CANCEL_FILE"); file && *file && now() >= cancel_poll_) {
        cancel_poll_ = now() + 0.25;
        std::error_code ec;
        if (fs::exists(file, ec)) cancel = true;
    }
    if (cancel) {
        test_cancelled_ = true;
        handle(model_->activate("task", now()));
        frame(now());
        shot(test_label_ + "-stopping");
    }
}

void App::test_tick(double t) {
    const bool busy = model_->busy() || working_ > 0 || stage_->animating() || wipe_->active(t) ||
                      readout_.animating(t);
    if (busy) {
        idle_since_ = t;
        frames_idle_ = 0;
    } else {
        ++frames_idle_;
    }
    if (!test_start_shot_) {
        if (!settled(t)) return;
        test_start_shot_ = true;
        shot("00-start");
    }
    switch (test_wait_) {
    case TestWait::kSettle:
        if (!settled(t)) return;
        shot(test_label_);
        if (test_now_.name == "show-uninstall" && view_.dialog) handle(model_->activate("uninstall-cancel", t));
        test_wait_ = TestWait::kNone;
        return;
    case TestWait::kTime:
        if (t < test_until_) return;
        test_said(true, {});
        return;
    case TestWait::kTask: {
        test_watch_task();
        const m::TaskRunner& r = model_->task();
        if (r.running()) {
            test_task_seen_ = true;
            return;
        }
        if (working_ > 0) return;
        const m::TaskResult& last = r.last();
        test_said(last.ok, last.ok ? last.title : last.title + (last.detail.empty() ? "" : ": " + last.detail));
        return;
    }
    case TestWait::kPreflight: {
        const m::Facts& f = model_->facts();
        if (model_->task().running()) {
            test_wait_ = TestWait::kTask;
            return;
        }
        if (working_ > 0 || (f.preflight && f.preflight->running)) return;
        if (f.preflight) {
            test_said(false, model_->said());
        } else {
            const m::TaskView tv = model_->task().view();
            test_said(false, tv.title + (tv.detail.empty() ? "" : ": " + tv.detail));
        }
        return;
    }
    case TestWait::kPlay: {
        test_watch_task();
        const m::TaskRunner& r = model_->task();
        if (r.running() || working_ > 0) return;
        if (t < test_until_) return;
        const std::string& error = model_->facts().game_error;
        test_said(error.empty(), error);
        return;
    }
    case TestWait::kQuitting:
        return;
    case TestWait::kNone: break;
    }
    if (!settled(t)) return;
    if (test_next_ >= o_.tests.size()) {
        if (!o_.screenshot.empty() && !screenshot_done_) {
            screenshot_done_ = true;
            std::string error;
            if (!window_.screenshot(o_.screenshot, &error)) {
                std::fprintf(stderr, "ttt2-launcher: %s\n", error.c_str());
                exit_code_ = 1;
            } else {
                std::fprintf(stderr, "ttt2-launcher: %s (%dx%d points, scale %.2f, %s)\n", o_.screenshot.c_str(),
                             static_cast<int>(window_.points().x), static_cast<int>(window_.points().y),
                             window_.scale(), window_.renderer_name().c_str());
            }
            quit_ = true;
        }
        return;
    }
    // The next action.
    test_now_ = o_.tests[test_next_++];
    ++test_number_;
    char prefix[16];
    std::snprintf(prefix, sizeof prefix, "%02d-", test_number_);
    test_label_ = prefix + test_now_.label();
    test_running_shot_ = test_cancelled_ = test_task_seen_ = false;
    test_since_ = t;
    std::fprintf(stderr, "@test %s started\n", test_now_.text.c_str());
    std::fflush(stderr);
    const std::string& n = test_now_.name;
    const std::vector<std::string>& args = test_now_.args;
    const std::string arg = args.empty() ? std::string() : args[0];
    const auto task_step = [&](const std::string& id) {
        handle(model_->activate(id, t));
        if (view_.dialog && view_.dialog->id == "remove-all") handle(model_->activate("remove-all-confirm", t));
        if (model_->task().running() || working_ > 0) {
            test_wait_ = TestWait::kTask;
        } else {
            const m::TaskView tv = model_->task().view();
            const std::string said = model_->said();
            test_said(false, !said.empty() ? said : tv.title + (tv.detail.empty() ? "" : ": " + tv.detail));
        }
    };
    if (n == "install") {
        slot_folder_ = args.size() > 1 ? fs::path(args[1]) : slot_folder_;
        pending_choose_.clear();
        answer_game(arg);
        test_wait_ = TestWait::kPreflight;
    } else if (n == "update" || n == "get-packages" || n == "update-launcher") {
        if (n == "update" && model_->facts().install.state != InstallState::kInstalled)
            return test_said(false, "no complete install to update");
        task_step(n);
    } else if (n == "add") {
        if (args.size() != 1) return test_said(false, "only one character at a time in this version");
        task_step("fighter:" + arg);
    } else if (n == "add-all-base" || (n == "add-all" && arg == "tekken7")) {
        task_step("add-all");
    } else if (n == "add-all") {
        task_step("add-all:" + arg);
    } else if (n == "add-all-owned") {
        task_step("add-all-owned");
    } else if (n == "remove") {
        task_step("remove:" + arg);
    } else if (n == "remove-all") {
        task_step("remove-all:" + arg);
    } else if (n == "uninstall") {
        if (model_->facts().install.state == InstallState::kNone) return test_said(false, "nothing is installed");
        handle(model_->activate("uninstall", t));
        if (arg == "all") {
            handle(model_->activate("uninstall-saves", t));
            handle(model_->activate("uninstall-characters", t));
        }
        handle(model_->activate("uninstall-confirm", t));
        test_wait_ = TestWait::kTask;
    } else if (n == "play") {
        handle(model_->activate("play", t));
        test_until_ = t + 3;
        test_wait_ = TestWait::kPlay;
    } else if (n == "quit") {
        std::fprintf(stderr, "@test quit ok\n");
        test_wait_ = TestWait::kQuitting;
        handle(model_->request_close(t));
        if (view_.dialog || !quit_) quit_ = true;
    } else if (n == "expand-dlc") {
        if (!model_->facts().dlc_expanded) handle(model_->activate("dlc", t));
        test_said(true, {});
    } else if (n == "expand-log") {
        if (!model_->task().view().details.checked) handle(model_->activate("details", t));
        test_said(true, {});
    } else if (n == "show-uninstall") {
        handle(model_->activate("uninstall", t));
        test_said(view_.dialog.has_value() || model_->view().dialog.has_value(), {});
    } else if (n == "focus") {
        const std::vector<std::string> ids = ui_->focusable_ids();
        if (std::find(ids.begin(), ids.end(), arg) == ids.end()) return test_said(false, "no " + arg + " that can take the focus");
        ui_->focus(arg, true);
        test_said(true, {});
    } else if (n == "toggle") {
        // (As a click: the launcher's own ids too, "slot:game" opens its file browser.)
        activate(arg);
        test_said(true, {});
    } else if (n == "refresh") {
        handle(model_->activate("refresh", t));
        test_said(true, "focus " + (ui_->focused().empty() ? std::string("none") : ui_->focused()));
    } else if (n == "settings") {
        go(Screen::kSettings);
        test_said(model_->page() == m::Page::kSettings, "Settings");
    } else if (n == "back") {
        go(Screen::kHome);
        test_said(model_->page() == m::Page::kMain, "the main page");
    } else if (n == "bind") {
        if (model_->page() != m::Page::kSettings) return test_said(false, "Settings is not open");
        const int input = input_index(arg);
        if (model_->keys().picking() != input) handle(model_->activate("key:" + arg, t));
        std::vector<int> usages;
        const std::string codes = args.size() > 1 ? args[1] : "";
        for (size_t at = 0; at <= codes.size();) {
            const size_t plus = codes.find('+', at);
            usages.push_back(m::usage_of_xkb(std::atoi(codes.substr(at, plus - at).c_str())));
            if (plus == std::string::npos) break;
            at = plus + 1;
        }
        for (const int u : usages) model_->key_down(u, false, t);
        for (auto it = usages.rbegin(); it != usages.rend(); ++it) model_->key_up(*it, t);
        test_said(true, model_->said());
    } else if (n == "reset-keys") {
        handle(model_->activate("restore-keys", t));
        test_said(true, model_->said());
    } else if (n == "fullscreen" || n == "interpolation" || n == "input-delay" || n == "async-shaders" ||
               n == "precompile-shaders" || n == "resolution") {
        if (model_->page() != m::Page::kSettings) go(Screen::kSettings);
        const display::Settings& s = model_->display().settings();
        if (n == "resolution") {
            const auto r = display::resolution_named(arg).value_or(display::Resolution::kAuto);
            const auto& all = display::kResolutions;
            handle(model_->choose("resolution",
                                  static_cast<int>(std::find(std::begin(all), std::end(all), r) - std::begin(all)), t));
        } else {
            const bool on = n == "fullscreen"      ? s.fullscreen
                            : n == "interpolation" ? s.interpolation
                            : n == "input-delay"   ? s.input_delay
                            : n == "async-shaders" ? s.async_shaders
                                                   : s.precompile_shaders;
            if (on != (arg == "yes")) handle(model_->activate(n, t));
        }
        const display::Loaded back = display::load(places_.display());
        if (!back.error.empty()) test_said(false, back.error);
        else test_said(true, m::display_summary(back.settings));
    } else if (n == "wait") {
        test_until_ = t + std::atof(arg.c_str());
        test_wait_ = TestWait::kTime;
    } else if (is_task_action(n)) {
        test_said(false, "not done by this launcher");
    } else {
        test_said(false, "unknown action");
    }
}

} // namespace launcher::app
