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

#include <SDL3/SDL.h>

#include <algorithm>
#include <cmath>
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

// --ui-smoke-test FILE (CI's source ZIP check, build_launcher.py) / TTT2_LAUNCHER_TEST_SMOKE (a start as a player's):
// {"program": "ttt2-launcher", "version", the start's facts, "frame": "video=<driver> renderer=<name> colours=<crimson
// side>,<blue side>" (or ""), "error": why there is no frame (or "")}. Called before the frame is shown.
bool App::smoke(const std::string& error) {
    if (smoke_done_) return true;
    smoke_done_ = true;
    std::string frame;
    if (error.empty()) {
        const Vec2 px = window_.pixels();
        std::string colours;
        for (const float at : {0.08f, 0.92f}) {
            const SDL_Rect r{static_cast<int>(px.x * at), static_cast<int>(px.y * 0.55f), 1, 1};
            SDL_Surface* pixel = SDL_RenderReadPixels(window_.renderer(), &r);
            Uint8 red = 0, green = 0, blue = 0, alpha = 0;
            if (pixel) SDL_ReadSurfacePixel(pixel, 0, 0, &red, &green, &blue, &alpha);
            SDL_DestroySurface(pixel);
            char text[16];
            std::snprintf(text, sizeof text, "%s%02x%02x%02x", colours.empty() ? "" : ",", red, green, blue);
            colours += text;
        }
        const auto word = [](const char* w) {
            std::string t = w && *w ? w : "-";
            std::replace(t.begin(), t.end(), ' ', '_');
            return t;
        };
        frame = "video=" + word(SDL_GetCurrentVideoDriver()) + " renderer=" + word(SDL_GetRendererName(window_.renderer())) +
                " colours=" + colours;
    }
    const auto quoted = [](const std::string& text) {
        std::string out = "\"";
        for (const char ch : text) {
            if (ch == '"' || ch == '\\') out += '\\';
            if (static_cast<unsigned char>(ch) < 0x20) {
                char escape[8];
                std::snprintf(escape, sizeof escape, "\\u%04x", static_cast<unsigned>(ch));
                out += escape;
            } else {
                out += ch;
            }
        }
        return out + "\"";
    };
    std::string json = "{\"program\": \"ttt2-launcher\", \"version\": " + quoted(TTT2_LAUNCHER_VERSION);
    if (!o_.smoke_start.empty()) json += ", " + o_.smoke_start;
    json += ", \"frame\": " + quoted(frame) + ", \"error\": " + quoted(error) + "}\n";
#ifdef _WIN32
    std::FILE* file = _wfopen(o_.smoke.c_str(), L"wb");
#else
    std::FILE* file = std::fopen(o_.smoke.c_str(), "wb");
#endif
    if (!file || std::fputs(json.c_str(), file) < 0) {
        const std::u8string name = o_.smoke.u8string();
        std::fprintf(stderr, "ttt2-launcher: cannot write %s\n", std::string(name.begin(), name.end()).c_str());
        exit_code_ = 1;
    }
    if (file) std::fclose(file);
    std::fprintf(stderr, "ttt2-launcher: smoke test: %s\n", frame.empty() ? error.c_str() : frame.c_str());
    if (!error.empty()) exit_code_ = 1;
    return true;
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

// Every frame of a test run: nothing of a half closer to its seam than the gutter (it would leave its plate), a
// highlight on whatever has the focus. Each problem is said once ("@audit failed <step>: <problem>").
void App::test_audit(double t) {
    std::vector<std::string> problems = ui_->audit();
    // Once it has settled (this frame too: a change that came without input, as checks' results, starts a move):
    // the highlight on the focused item, and something focused when anything can be (FEEDBACK F1/F6: no empty or
    // stale focus frame until the next input).
    if (settled(t) && !ui_->animating() && !stage_->animating()) {
        const Rect h = painted_highlight_, f = painted_focus_rect_;
        if (!painted_focus_.empty() && !f.empty() &&
            (std::fabs(h.x - f.x) > 1 || std::fabs(h.y - f.y) > 1 || std::fabs(h.w - f.w) > 1 ||
             std::fabs(h.h - f.h) > 1))
            problems.push_back("the highlight is not on " + painted_focus_ + " once settled");
        if (painted_focus_.empty() && !ui_->focusable_ids().empty()) problems.push_back("nothing has the focus");
    }
    for (const std::string& p : problems) {
        ++audit_failures_;
        if (std::find(audit_seen_.begin(), audit_seen_.end(), p) != audit_seen_.end()) continue;
        if (audit_seen_.size() >= 40) continue;
        audit_seen_.push_back(p);
        std::fprintf(stderr, "@audit failed %s: %s\n", audit_where_.empty() ? "start" : audit_where_.c_str(),
                     p.c_str());
    }
}

// --frames: the frames after the last action at the times asked for (the clock held and stepped), then the frame
// once everything has settled; each one is saved and checked: the audit, and the highlight exactly on the focused
// item (no empty or stale frame, FEEDBACK F1).
void App::test_capture(double t) {
    const auto check = [&](const std::string& name) {
        std::string error;
        if (!window_.screenshot((o_.frames / (name + ".png")).string(), &error))
            std::fprintf(stderr, "@frames %s failed %s\n", name.c_str(), error.c_str());
        std::vector<std::string> problems = ui_->audit();
        // (As painted: events move the focus after the frame.)
        const Rect h = painted_highlight_, f = painted_focus_rect_;
        if (!painted_focus_.empty() && !f.empty() &&
            (std::fabs(h.x - f.x) > 1 || std::fabs(h.y - f.y) > 1 || std::fabs(h.w - f.w) > 1 ||
             std::fabs(h.h - f.h) > 1)) {
            char b[200];
            std::snprintf(b, sizeof b, "the highlight %.0f,%.0f %.0fx%.0f is not on %s at %.0f,%.0f %.0fx%.0f", h.x,
                          h.y, h.w, h.h, painted_focus_.c_str(), f.x, f.y, f.w, f.h);
            problems.push_back(b);
        }
        if (painted_focus_.empty()) problems.push_back("nothing has the focus");
        std::string all;
        for (const std::string& p : problems) all += (all.empty() ? "" : "; ") + p;
        std::fprintf(stderr, "@frames %s %s%s%s (focus %s, seam %.1f)\n", name.c_str(),
                     problems.empty() ? "ok" : "failed", all.empty() ? "" : " ", all.c_str(), painted_focus_.c_str(),
                     static_cast<double>(stage_->seam_now().c));
        std::fflush(stderr);
    };
    const auto at = [&](size_t i) { return capture_t0_ + o_.frames_at[i] / 1000.0; };
    if (capture_i_ < o_.frames_at.size()) {
        if (t + 1e-6 >= at(capture_i_)) {
            char name[16];
            std::snprintf(name, sizeof name, "f%04d", o_.frames_at[capture_i_]);
            check(name);
            ++capture_i_;
        }
        const double next = capture_i_ < o_.frames_at.size() ? std::min(t + 1.0 / 60, at(capture_i_)) : t + 1.0 / 60;
        clock_.hold(next);
        return;
    }
    if (!settled(t) && t - capture_t0_ < 10) {
        clock_.hold(t + 1.0 / 60);
        return;
    }
    check("idle");
    capturing_ = false;
    clock_.release();
    if (o_.screenshot.empty()) quit_ = true;
}

// Input of a test step, through the router like the devices': press:<key> (an SDL scancode name: Return, Escape,
// Q, E, Down...), pad:<button> (south east west north lb rb lt rt up down left right start back), steam:<button>
// (the Steam Controller in desktop mode: the pad's button AND the key Steam types for it, at the same moment),
// click:<id> / hover:<id> (the mouse on an item's centre).
bool App::test_input(const std::string& name, const std::vector<std::string>& args, double t) {
    const std::string arg = args.empty() ? std::string() : args[0];
    const auto key = [&](const std::string& k, double at) {
        // ("Ctrl+H": with Ctrl held.)
        const bool ctrl = k.starts_with("Ctrl+") && k.size() > 5;
        const SDL_Scancode code = SDL_GetScancodeFromName(ctrl ? k.c_str() + 5 : k.c_str());
        if (code == SDL_SCANCODE_UNKNOWN) return false;
        RawEvent down;
        down.kind = RawEvent::KeyDown;
        down.device = Device::Keyboard;
        down.ctrl = ctrl;
        down.code = static_cast<int>(code);
        RawEvent up = down;
        up.kind = RawEvent::KeyUp;
        test_raw_.push_back({at, down});
        test_raw_.push_back({at + 0.06, up});
        return true;
    };
    struct PadName {
        const char* name;
        int button;
        const char* key;  // what Steam types for it in desktop mode
    };
    static const PadName pads[] = {{"south", pad::South, "Return"},      {"east", pad::East, "Escape"},
                                   {"west", pad::West, ""},              {"north", pad::North, ""},
                                   {"lb", pad::LeftShoulder, ""},        {"rb", pad::RightShoulder, ""},
                                   {"lt", pad::LeftTrigger, ""},         {"rt", pad::RightTrigger, ""},
                                   {"up", pad::DpadUp, "Up"},            {"down", pad::DpadDown, "Down"},
                                   {"left", pad::DpadLeft, "Left"},      {"right", pad::DpadRight, "Right"},
                                   {"start", pad::Start, ""},            {"back", pad::Back, ""}};
    const auto button = [&](const std::string& b, double at) -> const PadName* {
        for (const PadName& p : pads) {
            if (b != p.name) continue;
            RawEvent down;
            down.kind = RawEvent::ButtonDown;
            down.device = Device::Gamepad;
            down.device_id = 7;
            down.code = p.button;
            down.pad_kind = Glyphs::Xbox;
            RawEvent up = down;
            up.kind = RawEvent::ButtonUp;
            test_raw_.push_back({at, down});
            test_raw_.push_back({at + 0.06, up});
            return &p;
        }
        return nullptr;
    };
    if (name == "press") {
        if (!key(arg, t)) test_said(false, "no key named " + arg);
        else test_said(true, {});
        return true;
    }
    if (name == "pad") {
        if (!button(arg, t)) test_said(false, "no pad button " + arg);
        else test_said(true, {});
        return true;
    }
    if (name == "steam") {
        const PadName* p = button(arg, t);
        if (!p || !*p->key) return test_said(false, "Steam types no key for " + arg), true;
        key(p->key, t + 0.004);
        test_said(true, {});
        return true;
    }
    if (name == "click" || name == "hover") {
        const Rect r = ui_->rect(arg);
        if (r.empty()) return test_said(false, "no " + arg + " on the screen"), true;
        const Vec2 c = r.center();
        RawEvent move;
        move.kind = RawEvent::MouseMove;
        move.device = Device::Mouse;
        move.pos = c;
        move.delta = {12, 0};
        test_raw_.push_back({t, move});
        // (Real motion: far enough to count, and after the keyboard's navigation pause.)
        move.delta = {12, 0};
        test_raw_.push_back({t + 0.02, move});
        if (name == "click") {
            RawEvent down = move;
            down.kind = RawEvent::MouseDown;
            down.code = 1;
            RawEvent up = down;
            up.kind = RawEvent::MouseUp;
            test_raw_.push_back({t + 0.05, down});
            test_raw_.push_back({t + 0.1, up});
        }
        test_said(true, {});
        return true;
    }
    return false;
}

void App::test_tick(double t) {
    // (The browser reading its places, a folder, its folders' counts: off the UI thread.)
    const bool reading = picker_ && (picker_->loading || picker_->counting || !picker_->places_ready);
    const bool busy = model_->busy() || working_ > 0 || stage_->animating() || wipe_->active(t) ||
                      readouts_animating(t) || !test_raw_.empty() || reading;
    if (busy) {
        idle_since_ = t;
        frames_idle_ = 0;
    } else {
        ++frames_idle_;
    }
    if (capturing_) return test_capture(t);
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
    audit_where_ = test_label_;
    test_running_shot_ = test_cancelled_ = test_task_seen_ = false;
    // --frames: the last action starts the capture (the clock held from now on).
    if (!o_.frames.empty() && test_next_ == o_.tests.size()) {
        capturing_ = true;
        capture_t0_ = t;
        capture_i_ = 0;
        clock_.hold(t);
    }
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
        // (A browser row not in view is not declared: it is when it has the focus.)
        const bool row = picker_ && arg.starts_with("pe:") &&
                         std::strtoul(arg.c_str() + 3, nullptr, 10) < picker_->entries.size();
        if (!row && std::find(ids.begin(), ids.end(), arg) == ids.end())
            return test_said(false, "no " + arg + " that can take the focus");
        ui_->focus(arg, true);
        test_said(true, {});
    } else if (n == "rows") {
        // The rows of a list in view (inside their scroll container's view, as painted): how many, how wide.
        const std::string& prefix = arg;
        const float least = static_cast<float>(std::atof(args.size() > 1 ? args[1].c_str() : "0"));
        int shown = 0, narrow = 0, declared = 0;
        float lo = 1e9f, hi = 0;
        std::string first_narrow;
        const Rect view = ui_->rect(picker_ ? "pk/crimson" : "");
        for (const std::string& id : ui_->focusable_ids()) {
            if (!id.starts_with(prefix)) continue;
            ++declared;
            const Rect r = ui_->rect(id);
            if (!view.empty() && (r.y < view.y - .5f || r.bottom() > view.bottom() + .5f)) continue;
            ++shown;
            lo = std::min(lo, r.w);
            hi = std::max(hi, r.w);
            if (r.w < least && narrow++ == 0) first_narrow = id;
        }
        char said[200];
        std::snprintf(said, sizeof said, "%d in view of %d declared, %.0f-%.0f points wide%s%s", shown, declared,
                      shown ? lo : 0.f, hi, narrow ? ", narrower than wanted: " : "", first_narrow.c_str());
        test_said(shown > 0 && narrow == 0, said);
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
        const display::Loaded back = display::load(display_file_);
        if (!back.error.empty()) test_said(false, back.error);
        else test_said(true, m::display_summary(back.settings));
    } else if (test_input(n, args, t)) {
    } else if (n == "tab") {
        // (As the shoulder buttons: Q / E.)
        const int to = arg == "next"       ? (static_cast<int>(screen_) + 1) % 3
                       : arg == "prev"     ? (static_cast<int>(screen_) + 2) % 3
                       : arg == "fighters" ? 1
                       : arg == "settings" ? 2
                                           : 0;
        go(static_cast<Screen>(to));
        test_said(true, {});
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
