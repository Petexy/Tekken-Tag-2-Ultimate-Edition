// Home in every state of the game (installed, playing, an update ready, an older game, the first run with its two
// slots, an unfinished install, the checks before an install) and the task screen of an install, an update, the
// uninstall and the launcher's update (its steps, its percentage, its end). Crimson: what is chosen from; blue: the
// game, and what the focused item does or why it cannot.

#include "app.h"
#include "utf8_path.h"

#include "builders.h"
#include "rules.h"

#include <algorithm>
#include <cmath>

namespace launcher::app {

using namespace ttt2::ui;
namespace c = theme::color;
namespace tx = theme::text;

namespace {

Box fit(Box b, SeamFit f) {
    b.fit = f;
    return b;
}

Tone pill_tone(m::PillKind k) {
    switch (k) {
    case m::PillKind::kOk: return Tone::Ok;
    case m::PillKind::kWarn: return Tone::Warn;
    case m::PillKind::kBad: return Tone::Bad;
    default: return Tone::Neutral;
    }
}

void edition(Ui& ui, const std::string& id, const Box& box) {
    TextEngine& te = ui.text();
    Box b = box;
    b.h = Size::fixed(34);
    b.hug = true;
    ui.leaf(
        id, b, [&te](float) { return Vec2{te.width(tx::kEdition, "Ultimate Edition") + 44, 34}; },
        [](PaintContext& ctx) {
            const Rect r = ctx.rect;
            surface(ctx.canvas, r, Gradient::css(r, 90, {{0, rgb(0xe8173f)}, {.5f, rgb(0x7c1a6a)}, {1, rgb(0x1f5fe8)}}),
                    rgba(255, 255, 255, .35f));
            ctx.text.draw(ctx.canvas, tx::kEdition, "Ultimate Edition",
                          {r.x + 20, r.y + (r.h - ctx.text.line_height(tx::kEdition)) / 2}, rgb(0xffffff));
        });
}

Focus crimson_focus(bool is_default = false, bool disabled = false) {
    Focus f;
    f.group = -1;
    f.is_default = is_default;
    f.disabled = disabled;
    return f;
}

Focus blue_focus() {
    Focus f;
    f.group = 1;
    return f;
}

const Color kValue = rgb(0xdbe3f1);

} // namespace

float App::share() const {
    if (picker_) return theme::split::kPicker;
    if (screen_ == Screen::kFighters) return theme::split::kFighters;
    if (screen_ == Screen::kSettings) return theme::split::kSettings;
    if (task_screen_) return theme::split::kSetup;
    const m::GameState s = view_.game.state;
    if (s == m::GameState::kChecking || s == m::GameState::kCannotInstall || s == m::GameState::kNotInstalled ||
        s == m::GameState::kInstalling)
        return theme::split::kSetup;
    return theme::split::kHome;
}

bool App::tall() const { return screen_ == Screen::kHome && task_screen_ && !picker_; }

std::string App::slot_target() const {
#ifdef _WIN32
    return m::shown_path(slot_folder_);
#else
    std::string why;
    const auto t = launcher::install_target(slot_folder_, &why);
    return m::shown_path(t ? *t : slot_folder_ / "Tekken Tag Tournament 2");
#endif
}

void App::home(const Box& crimson, const Box& blue) {
    if (task_screen_) return home_task(crimson, blue);
    switch (view_.game.state) {
    case m::GameState::kInstalled: return home_installed(crimson, blue);
    case m::GameState::kNotFinished: return home_unfinished(crimson, blue);
    case m::GameState::kChecking:
    case m::GameState::kCannotInstall: return home_preflight(crimson, blue);
    default: return model_->facts().caps.setup_game ? home_setup(crimson, blue) : home_first_run(crimson, blue);
    }
}

// The blue side's top: the game, its state and its name.
void App::game_head(const std::string& kick) {
    Ui& ui = *ui_;
    section_label(ui, "home/game-label", "The game", Half::Blue, {}, fit({}, SeamFit::BlueRect));
    {
        auto k = ui.open("home/kick", fit(Box{.layout = Layout::Row, .h = Size::fixed(26), .margin = {0, 0, 0, 10},
                                              .gap = 12, .align = Align::Center},
                                          SeamFit::BlueRect));
        const bool live = view_.game.pill.text == "Running" || view_.game.pill.text == "Checking";
        pill(ui, "home/pill", view_.game.pill.text, live ? Tone::Blue : pill_tone(view_.game.pill.kind), live);
        TextSpec ks{kick, tx::kKick, c::kBlueDim};
        text(ui, "home/kv", ks, Box{.w = Size::grow()});
    }
    text(ui, "home/t1", TextSpec{.text = "Tekken Tag", .style = tx::kTitleLine, .chroma = 4, .autofit_min = 30},
         fit({}, SeamFit::BlueRect));
    text(ui, "home/t2", TextSpec{.text = "Tournament 2", .style = tx::kTitleLine, .chroma = 4, .autofit_min = 30},
         fit({}, SeamFit::BlueRect));
    edition(ui, "home/edition", fit(Box{.margin = {4, 12, 0, 16}}, SeamFit::BlueSkewed));
}

// What the focused item does (or why it cannot), below the game's facts.
void App::home_readout(const std::string& key) {
    Ui& ui = *ui_;
    readout_.show(key, last_dy_, ui.now());
    readout_.build(ui, "home/ro", Box{}, [&](const std::string& k) {
        const m::Facts& f = model_->facts();
        std::string title, body, why;
        bool notes = false;
        if (const m::Action* a = action(k)) {
            title = a->describe.title.empty() ? a->label : a->describe.title;
            if (title.ends_with("…")) title.resize(title.size() - std::string("…").size());
            body = a->describe.explain.empty() ? a->tooltip : a->describe.explain;
            why = a->why;
            notes = a->primary || k == "update";
        } else if (k == "fighters") {
            title = "Fighters";
            if (f.install.state == InstallState::kInstalled && f.status) {
                int added = 0, update = 0;
                for (const Fighter& x : f.status->fighters) {
                    added += x.added();
                    update += x.added() && x.update;
                }
                body = "Tekken 7's and Tekken 8's characters, made from your own games: " + std::to_string(added) +
                       " of " + std::to_string(f.status->fighters.size()) + " added" +
                       (update ? ", " + std::to_string(update) + " to update." : ".");
            } else if (f.install.state == InstallState::kInstalled) {
                body = "Tekken 7's and Tekken 8's characters, made from your own games.";
            } else {
                body = "See which characters can be added: they are made from your Tekken 7 and Tekken 8 once the "
                       "game is installed.";
            }
        } else if (k == "slot:game") {
            title = "Game file";
            body = f.chosen_game.empty()
                       ? "Choose your .wua with the file browser: it works with a controller too."
                       : path_utf8(f.chosen_game.filename()) + ", in " + m::shown_path(f.chosen_game.parent_path()) +
                             ". Choose another one with the file browser.";
        } else if (k == "slot:folder") {
            title = "Install folder";
            body = "The game goes into " + slot_target() + ". Choose another place with the folder browser.";
        } else {
            return;
        }
        describe_panel(ui, "home/xpl", title, body, fit({}, SeamFit::BlueSkewed));
        if (!why.empty())
            note(ui, "home/why", Tone::Warn, why, fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect), "stroke:warn");
        int n = 0;
        for (const m::Line& l : view_.game.body) {
            const bool error = l.tone == m::Tone::kError;
            if (!error && (!notes || l.kind != m::Line::Kind::kNote)) continue;
            const std::string id = "home/note" + std::to_string(n++);
            const Tone tone = error ? Tone::Bad : l.icon == m::Icon::kWarning ? Tone::Warn : Tone::Blue;
            note(ui, id, tone, l.text.empty() ? l.title : l.text, fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect),
                 tone == Tone::Blue ? "stroke:info" : "stroke:warn");
        }
    });
}

// The launcher's own update, on the blue side under the game.
void App::notice_card() {
    // A framed row as the mock's: the arrow, what is out and what Update does, then its two buttons stacked.
    if (!view_.notice.shown) return;
    Ui& ui = *ui_;
    auto card = ui.open(
        "notice/card",
        fit(Box{.layout = Layout::Row, .pad = {20, 12, 14, 12}, .margin = {0, 12, 0, 2}, .gap = 16,
                .align = Align::Center},
            SeamFit::BlueSkewed),
        [](PaintContext& ctx) {
            const Rect r = ctx.rect;
            surface(ctx.canvas, r,
                    Gradient::css(r, 100, {{0, rgba(45, 128, 255, .22f)}, {1, rgba(8, 14, 34, .55f)}}),
                    rgba(140, 190, 255, .38f));
        });
    ui.leaf(
        "notice/icon", Box{.w = Size::fixed(34), .h = Size::fixed(34)}, [](float) { return Vec2{34, 34}; },
        [](PaintContext& ctx) {
            const Rect r = ctx.rect;
            surface(ctx.canvas, r, rgba(45, 128, 255, .35f), rgba(140, 190, 255, .5f), 0);
            icon(ctx.canvas, ctx.icons, "stroke:update", {r.x + 7, r.y + 7, 20, 20}, c::kCyan);
        });
    {
        auto col = ui.open("notice/text", Box{.w = Size::grow(), .gap = 4});
        text(ui, "notice/title", TextSpec{view_.notice.title, tx::kExplainTitle, rgb(0xe9edf5)});
        text(ui, "notice/detail",
             TextSpec{.text = view_.notice.detail, .style = tx::kParaSmall, .color = c::kBlueDim, .wrap = true});
    }
    auto btns = ui.open("notice/btns", Box{.gap = 6, .align = Align::End});
    if (view_.notice.page) {
        ButtonSpec b;
        b.label = view_.notice.page->label;
        b.size = ButtonSize::Tiny;
        button(ui, "release-page", b, blue_focus());
    }
    ButtonSpec u;
    u.label = view_.notice.update.label;
    u.kind = ButtonKind::Blue;
    u.size = ButtonSize::Tiny;
    u.disabled = !view_.notice.update.enabled;
    Focus uf = blue_focus();
    uf.disabled = u.disabled;
    button(ui, "notice-update", u, uf);
}

void App::home_installed(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::Facts& f = model_->facts();
    const m::Action* primary = nullptr;
    for (const m::Action& a : view_.game.actions)
        if (a.primary) primary = &a;
    int added = 0, total = 0, update = 0;
    if (f.status) {
        total = static_cast<int>(f.status->fighters.size());
        for (const Fighter& x : f.status->fighters) {
            added += x.added();
            update += x.added() && x.update;
        }
    }
    {
        auto g = ui.open("home/crimson", crimson);
        section_label(ui, "home/menu-label", "Menu", Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (primary) {
            SlabSpec s;
            if (primary->id == "update") s = {"Update", "then play", "a few minutes"};
            else s = {primary->label, "Tekken Tag", "Tournament 2"};
            s.mid = s.big.size() > 6;
            s.disabled = !primary->enabled;
            slab(ui, primary->id, s, crimson_focus(true, !primary->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        menu_row(ui, "fighters",
                 {"stroke:users", "Fighters", f.status ? std::to_string(added) + " of " + std::to_string(total) : ""},
                 crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", "Settings"}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        for (const m::Action& a : view_.game.actions) {
            if (a.id == "update" && !a.primary) {
                MenuRowSpec u{"stroke:update", "Update the game", "Ready"};
                u.value_tone = Tone::Warn;
                u.disabled = !a.enabled;
                menu_row(ui, "update", u, crimson_focus(false, !a.enabled), fit({}, SeamFit::CrimsonSkewed));
            }
        }
        if (action("open-folder"))
            menu_row(ui, "open-folder", {"stroke:folder", "Open the game folder"}, crimson_focus(),
                     fit({}, SeamFit::CrimsonSkewed));
        if (const m::Action* more = action("more")) {
            MenuRowSpec s{"stroke:dots", "More", "Build, install, logs"};
            s.disabled = !more->enabled;
            menu_row(ui, "more", s, crimson_focus(false, !more->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
        if (const m::Action* un = action("uninstall")) {
            MenuRowSpec s{"stroke:trash", "Uninstall"};
            s.danger = true;
            s.disabled = !un->enabled;
            menu_row(ui, "uninstall", s, crimson_focus(false, !un->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
    }
    auto g = ui.open("home/blue", blue);
    const std::string kick = f.game_built.empty()
                                 ? std::string("Not built by this launcher")
                                 : "Game " + std::string(launcher_version(f.game_built)) + " · built on this PC";
    game_head(kick);
    std::vector<Run> fighters_runs;
    if (f.status) {
        fighters_runs.push_back({std::to_string(added) + " of " + std::to_string(total) + " added", kValue});
        if (update) {
            fighters_runs.push_back({" · ", kValue});
            fighters_runs.push_back({std::to_string(update) + " to update", c::kWarn});
        }
    } else {
        fighters_runs.push_back({f.status_loading ? "Looking…" : "Not known", c::kBlueDim});
    }
    const Fact list[] = {
        {"Version", {{f.game_built.empty() ? "Unknown" : m::shown_build(f.game_built), kValue}}},
        {"Folder", {{m::shown_path(f.install.folder), kValue}}},
        {"Fighters", fighters_runs, false}};
    // (Drilled into More: its entries and what the focused one does take the facts' place.)
    if (drilled() && drill_->opener == "more") return more_view();
    facts(ui, "home/facts", list, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    notice_card();
    const std::string& fo = ui.focused();
    if (!fo.empty() && (ui.rect(fo).x < stage_->seam_now().x_at(ui.rect(fo).center().y) ||
                        fo == "notice-update" || fo == "release-page"))
        readout_key_ = fo;
    home_readout(readout_key_);
}

// Windows before Set Up Game (window.py's card): Set Up Game asks for the archive and the folder (the in-app
// browser), then confirms; More has the developers' and the logs' entries.
void App::home_setup(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::Facts& f = model_->facts();
    const m::Action* setup = action("setup");
    {
        auto g = ui.open("home/crimson", crimson);
        section_label(ui, "home/menu-label", "Set Up", Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (setup) {
            SlabSpec s{"Set Up", "from your", "own .wua"};
            s.mid = true;
            s.disabled = !setup->enabled;
            slab(ui, "setup", s, crimson_focus(true, !setup->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        menu_row(ui, "fighters", {"stroke:users", "Fighters"}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", "Settings"}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        if (const m::Action* more = action("more")) {
            MenuRowSpec s{"stroke:dots", "More", "Build, install, logs"};
            s.disabled = !more->enabled;
            menu_row(ui, "more", s, crimson_focus(false, !more->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
    }
    auto g = ui.open("home/blue", blue);
    game_head("Native PC port · built from your own copy");
    const auto folder = [&](const char* key) {
        const auto it = f.windows.folders.find(key);
        return it == f.windows.folders.end() ? std::string() : it->second;
    };
    const std::string source = folder("source"), install = folder("install");
    section_label(ui, "home/needs-label", "What the setup needs", Half::Blue, {},
                  fit(Box{.margin = {0, 4, 0, 0}}, SeamFit::BlueRect));
    const Fact list[] = {
        {"Your copy", {{"TEKKEN TAG TOURNAMENT 2 WII U EDITION: European, update 16, as a .wua archive", kValue}}, false},
        {"Archive", {{source.empty() ? "Chosen when you set up" : m::shown_path(utf8_path(source)), source.empty() ? c::kBlueDim
                                                                                                      : kValue}},
         !source.empty()},
        {"Folder", {{install.empty() ? "Chosen when you set up" : m::shown_path(utf8_path(install)), install.empty() ? c::kBlueDim
                                                                                                        : kValue}},
         !install.empty()},
        {"Space", {{"About 30 GB and internet: the tools are downloaded once", kValue}}, false}};
    // (Drilled into More: its entries and what the focused one does take the facts' place.)
    if (drilled() && drill_->opener == "more") return more_view();
    facts(ui, "home/facts", list, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    notice_card();
    const std::string& fo = ui.focused();
    if (!fo.empty() && (ui.rect(fo).x < stage_->seam_now().x_at(ui.rect(fo).center().y) ||
                        fo == "notice-update" || fo == "release-page"))
        readout_key_ = fo;
    home_readout(readout_key_);
}

// Windows' More, drilled into from its row: its entries on the blue side (the crimson side locked, F4).
void App::more_view() {
    Ui& ui = *ui_;
    section_label(ui, "more/label", "More", Half::Blue, {}, fit(Box{.margin = {0, 6, 0, 8}}, SeamFit::BlueRect));
    for (const m::Action& a : view_.game.more) screen_actions_[a.id] = a;
    more_describe();
    // (In rows that wrap: six entries never run below the plate.)
    auto col = ui.open("more/list", fit(Box{.layout = Layout::Row, .margin = {0, 12, 0, 0}, .gap = 10, .line_gap = 10,
                                            .wrap = true},
                                        SeamFit::BlueRect));
    for (const m::Action& a : view_.game.more) {
        ButtonSpec b;
        b.label = a.label;
        b.kind = ButtonKind::Blue;
        b.size = ButtonSize::Small;
        b.disabled = !a.enabled;
        Focus fo;
        fo.group = 1;
        fo.disabled = !a.enabled;
        button(ui, a.id, b, fo);
    }
}

// What the focused More entry does (its row's words, else the launcher's), and why it cannot now.
void App::more_describe() {
    Ui& ui = *ui_;
    const m::Action* a = action(ui.focused());
    if (a && ui.focused().starts_with("more:")) {
        std::string body = a->describe.explain.empty() ? a->tooltip : a->describe.explain;
        if (body.empty()) {
            const std::string& id = a->id;
            body = id == "more:build"           ? "Builds the Windows game program again from the extracted game (a while)."
                   : id == "more:install"       ? "Installs the built game into the installation folder."
                   : id == "more:update"        ? "Puts the newest built program into the installed game."
                   : id == "more:setup-again"   ? "Set Up Game again: another archive or folder."
                   : id == "more:open-logs"     ? "Opens the folder of every task's log."
                                                : "Opens the newest task's log.";
        }
        describe_panel(ui, "more/xpl", a->label, body, fit({}, SeamFit::BlueSkewed));
        if (!a->enabled && !a->why.empty())
            note(ui, "more/why", Tone::Warn, a->why, fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect),
                 "stroke:warn");
    }
}

void App::home_first_run(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::Facts& f = model_->facts();
    const m::Action* install = action("install");
    {
        auto g = ui.open("home/crimson", crimson);
        section_label(ui, "home/menu-label", "Install", Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (install) {
            SlabSpec s{"Install", "from your", "own .wua"};
            s.mid = true;
            s.disabled = !install->enabled;
            slab(ui, "install", s, crimson_focus(true, !install->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        MenuRowSpec one;
        one.number = 1;
        one.caption = "Game file";
        one.title = f.chosen_game.empty() ? "Choose your .wua" : path_utf8(f.chosen_game.filename());
        one.ok = !f.chosen_game.empty();
        one.mono_title = !f.chosen_game.empty();
        menu_row(ui, "slot:game", one, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        MenuRowSpec two;
        two.number = 2;
        two.caption = "Install folder";
        two.title = slot_target();
        two.mono_title = true;
        two.ok = true;
        menu_row(ui, "slot:folder", two, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "fighters", {"stroke:users", "Fighters"}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", "Settings"}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
    }
    auto g = ui.open("home/blue", blue);
    game_head("Native PC port · built from your own copy");
    section_label(ui, "home/needs-label", "What the install needs", Half::Blue, {},
                  fit(Box{.margin = {0, 4, 0, 0}}, SeamFit::BlueRect));
    const Fact list[] = {
        {"Your copy", {{"TEKKEN TAG TOURNAMENT 2 WII U EDITION: European, update 16, as a .wua archive", kValue}}, false},
        {"Game file",
         {{f.chosen_game.empty() ? "Not chosen yet" : path_utf8(f.chosen_game.filename()),
           f.chosen_game.empty() ? c::kWarn : kValue}},
         !f.chosen_game.empty()},
        {"Space", {{"About 16 GB, plus 3 GB while building", kValue}}, false},
        {"This PC", {{"A C++ compiler and an x86-64-v3 processor: checked first", kValue}}, false}};
    facts(ui, "home/facts", list, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    for (const m::Line& l : view_.game.body) {
        if (l.tone != m::Tone::kError) continue;
        note(ui, "home/error", Tone::Bad, l.text, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect), "stroke:warn");
        break;
    }
    notice_card();
    const std::string& fo = ui.focused();
    if (!fo.empty() && (ui.rect(fo).x < stage_->seam_now().x_at(ui.rect(fo).center().y) ||
                        fo == "notice-update" || fo == "release-page"))
        readout_key_ = fo;
    home_readout(readout_key_);
}

void App::home_unfinished(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::Facts& f = model_->facts();
    {
        auto g = ui.open("home/crimson", crimson);
        section_label(ui, "home/menu-label", "Menu", Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (const m::Action* r = action("resume")) {
            SlabSpec s{"Resume", "the install", "not finished"};
            s.mid = true;
            s.disabled = !r->enabled;
            slab(ui, "resume", s, crimson_focus(true, !r->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        menu_row(ui, "fighters", {"stroke:users", "Fighters"}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", "Settings"}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        if (const m::Action* un = action("uninstall")) {
            MenuRowSpec s{"stroke:trash", "Uninstall"};
            s.danger = true;
            s.disabled = !un->enabled;
            menu_row(ui, "uninstall", s, crimson_focus(false, !un->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
    }
    auto g = ui.open("home/blue", blue);
    game_head("Stopped before it was complete");
    const Fact list[] = {{"Folder", {{m::shown_path(f.install.folder), kValue}}},
                         {"Game file",
                          {{f.install.game.empty() ? "Asked for when it resumes" : m::shown_path(f.install.game),
                            kValue}},
                          !f.install.game.empty()}};
    facts(ui, "home/facts", list, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    notice_card();
    const std::string& fo = ui.focused();
    if (!fo.empty() && (ui.rect(fo).x < stage_->seam_now().x_at(ui.rect(fo).center().y) ||
                        fo == "notice-update" || fo == "release-page"))
        readout_key_ = fo;
    home_readout(readout_key_);
}

std::string App::check_copy(const std::string& row) const {
    if (!row.starts_with("check:")) return {};
    const size_t want = std::strtoul(row.c_str() + 6, nullptr, 10);
    size_t i = 0;
    for (const m::Line& l : view_.game.body) {
        if (l.kind != m::Line::Kind::kCheck) continue;
        if (i++ != want) continue;
        for (const m::Action& a : l.actions)
            if (a.id.starts_with("copy:")) return a.id;
        return {};
    }
    return {};
}

// The checks before an install: each check on the crimson side, the focused one's details (and its command to
// copy) on the blue side. Accept on a check with a command goes to its Copy button (the drill-in lock).
void App::home_preflight(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::Facts& f = model_->facts();
    const bool running = view_.game.state == m::GameState::kChecking;
    std::vector<const m::Line*> checks;
    for (const m::Line& l : view_.game.body)
        if (l.kind == m::Line::Kind::kCheck) checks.push_back(&l);
    {
        auto g = ui.open("home/crimson", crimson);
        section_label(ui, "pre/label", "Before the install", Half::Crimson,
                      running ? "" : std::to_string(checks.size()) + " checks",
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        auto rows = ui.open("pre/rows", Box{.gap = 8});
        if (running) {
            MenuRowSpec s{"stroke:dots", "Checking this PC…"};
            s.compact = true;
            menu_row(ui, "check:0", s, crimson_focus(true), fit({}, SeamFit::CrimsonSkewed));
        }
        int first_bad = -1;
        for (size_t i = 0; i < checks.size(); ++i)
            if (first_bad < 0 && checks[i]->icon_tone == m::Tone::kError) first_bad = static_cast<int>(i);
        for (size_t i = 0; i < checks.size(); ++i) {
            const m::Line& l = *checks[i];
            const bool ok = l.icon_tone != m::Tone::kError;
            MenuRowSpec s{ok ? "stroke:check" : "stroke:cross", l.title, ok ? "Ready" : "Missing"};
            s.value_tone = ok ? Tone::Ok : Tone::Bad;
            s.compact = true;
            menu_row(ui, "check:" + std::to_string(i), s,
                     crimson_focus(static_cast<int>(i) == (first_bad < 0 ? 0 : first_bad)),
                     fit({}, SeamFit::CrimsonSkewed));
        }
        if (!running) {
            auto b = ui.open("pre/btns", fit(Box{.layout = Layout::Row, .margin = {0, 10, 0, 0}, .gap = 12,
                                                 .line_gap = 12, .wrap = true},
                                             SeamFit::CrimsonRect));
            ButtonSpec again;
            again.label = "Check Again";
            again.kind = ButtonKind::Primary;
            again.prompt = Prompt::Accept;
            again.half = Half::Crimson;
            button(ui, "check-again", again, crimson_focus());
            ButtonSpec cancel;
            cancel.label = "Cancel";
            cancel.prompt = Prompt::Back;
            cancel.half = Half::Crimson;
            button(ui, "preflight-cancel", cancel, crimson_focus());
        }
    }
    auto g = ui.open("home/blue", blue);
    const std::string& fo = ui.focused();
    int index = -1;
    if (fo.starts_with("check:")) index = std::atoi(fo.c_str() + 6);
    else if (fo.starts_with("copy:") || fo == "check-again" || fo == "preflight-cancel") index = -2;
    if (index >= 0) pre_index_ = index;
    else index = pre_index_;
    const std::string key = running ? "running" : "check:" + std::to_string(index);
    readout_.show(key, last_dy_, ui.now());
    readout_.build(ui, "pre/ro", Box{}, [&](const std::string& k) {
        if (k == "running" || checks.empty()) {
            section_label(ui, "pre/c-label", "Checking", Half::Blue, {}, fit({}, SeamFit::BlueRect));
            text(ui, "pre/c-title", TextSpec{.text = "This PC", .style = tx::kBig, .chroma = 3, .autofit_min = 30},
                 fit({}, SeamFit::BlueRect));
            text(ui, "pre/c-text",
                 TextSpec{.text = "The game file, the processor, a C++ compiler and the free space are checked "
                                  "before the install starts.",
                          .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect));
            return;
        }
        const size_t i = std::min(checks.size() - 1, static_cast<size_t>(std::max(0, std::atoi(k.c_str() + 6))));
        const m::Line& l = *checks[i];
        const bool ok = l.icon_tone != m::Tone::kError;
        section_label(ui, "pre/c-label", "Check " + std::to_string(i + 1) + " of " + std::to_string(checks.size()),
                      Half::Blue, {}, fit({}, SeamFit::BlueRect));
        pill(ui, "pre/c-pill", ok ? "Ready" : "Missing", ok ? Tone::Ok : Tone::Bad, false,
             fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        text(ui, "pre/c-title", TextSpec{.text = l.title, .style = tx::kBig, .chroma = 3, .autofit_min = 28},
             fit({}, SeamFit::BlueRect));
        text(ui, "pre/c-text", TextSpec{.text = l.text, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 8, 0, 10}}, SeamFit::BlueRect));
        for (const m::Action& a : l.actions) {
            if (!a.id.starts_with("copy:")) continue;
            const std::string command = a.id.substr(5);
            text(ui, "pre/c-cmd",
                 TextSpec{.text = command, .style = tx::kFactValue, .color = rgb(0xe9f1ff), .wrap = true},
                 fit(Box{.pad = {12, 10, 12, 10}, .margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
            ButtonSpec b;
            b.label = "Copy";
            b.kind = ButtonKind::Blue;
            b.size = ButtonSize::Small;
            button(ui, a.id, b, blue_focus(), fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        }
        if (!ok) {
            text(ui, "pre/c-then",
                 TextSpec{.text = "Then Check Again: the install starts once everything is ready.",
                          .style = tx::kParaSmall, .color = c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
        }
    });
    if (f.preflight) {
        const Fact list[] = {{"Game file", {{m::shown_path(f.preflight->game), kValue}}},
                             {"Into", {{m::shown_path(f.preflight->folder), kValue}}}};
        facts(ui, "pre/facts", list, fit(Box{.margin = {0, 12, 0, 0}}, SeamFit::BlueRect));
    }
}

// The task that fills Home: its steps (crimson), its progress and end (blue).
double App::task_fraction() const {
    const m::TaskRunner& r = model_->task();
    const bool running = r.running();
    if (!running && r.last().ok) return 1.0;
    if (task_kind_ != m::TaskKind::kInstall && task_kind_ != m::TaskKind::kUpdate) return r.progress_state().fraction();
    // (A build's whole: its steps, each one share.)
    const std::vector<StepLine> steps = build_steps(r.log(), !running, false);
    if (steps.empty()) return r.progress_state().fraction();
    double sum = 0;
    for (const StepLine& l : steps)
        sum += l.state == StepLine::State::kDone ? 1 : l.state == StepLine::State::kPending ? 0 : l.fraction;
    return sum / static_cast<double>(steps.size());
}

void App::home_task(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::Facts& f = model_->facts();
    const m::TaskRunner& r = model_->task();
    const bool running = r.running();
    const m::TaskResult& last = r.last();
    const bool ok = !running && last.ok;
    const bool stopped = !running && last.cancelled;
    const bool failed = !running && !ok && !stopped;
    const bool build = task_kind_ == m::TaskKind::kInstall || task_kind_ == m::TaskKind::kUpdate;
    std::vector<StepLine> steps;
    if (build) {
        steps = build_steps(r.log(), !running, ok);
    } else {
        StepLine s;
        s.name = running ? r.progress_state().step() : last.title;
        if (s.name.empty()) s.name = task_title_;
        s.state = running ? StepLine::State::kCurrent : ok ? StepLine::State::kDone : StepLine::State::kFailed;
        s.fraction = running ? std::max(0.0, r.progress_state().fraction()) : 1;
        steps.push_back(s);
    }
    const int at = current_step(steps);
    const double fraction = task_fraction();
    {
        auto g = ui.open("home/crimson", crimson);
        section_label(ui, "task/steps-label",
                      build ? std::to_string(steps.size()) + " steps" : std::string("Steps"), Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        {
            auto rows = ui.open("task/rows", Box{.gap = 6});
            for (size_t i = 0; i < steps.size(); ++i) {
                StepRowSpec s;
                s.name = steps[i].name;
                s.count = steps[i].state == StepLine::State::kDone     ? std::string("Done")
                          : steps[i].state == StepLine::State::kFailed ? std::string("Stopped")
                                                                       : steps[i].count;
                if (const size_t of = s.count.find(" of "); of != std::string::npos) s.count.replace(of, 4, " / ");
                s.fraction = static_cast<float>(steps[i].fraction);
                s.number = static_cast<int>(i) + 1;
                s.state = steps[i].state == StepLine::State::kDone      ? StepState::Done
                          : steps[i].state == StepLine::State::kCurrent ? StepState::Current
                          : steps[i].state == StepLine::State::kFailed  ? StepState::Failed
                                                                        : StepState::Pending;
                step_row(ui, "task/step" + std::to_string(i), s, fit({}, SeamFit::CrimsonSkewed));
            }
        }
        auto b = ui.open("task/btns", fit(Box{.layout = Layout::Row, .margin = {0, 14, 0, 0}, .gap = 12,
                                              .line_gap = 12, .wrap = true},
                                          SeamFit::CrimsonRect));
        const bool can_play = ok && (task_kind_ == m::TaskKind::kInstall || task_kind_ == m::TaskKind::kUpdate) &&
                              action("play") && action("play")->enabled;
        if (running) {
            ButtonSpec cancel;
            cancel.label = view_.task.button.label.empty() ? "Cancel" : view_.task.button.label;
            cancel.prompt = Prompt::Back;
            cancel.half = Half::Crimson;
            cancel.disabled = !view_.task.button.enabled;
            button(ui, "task", cancel, crimson_focus(true, cancel.disabled));
        } else {
            if (can_play) {
                ButtonSpec play;
                play.label = "Play";
                play.kind = ButtonKind::Primary;
                play.prompt = Prompt::Accept;
                play.half = Half::Crimson;
                button(ui, "task/play", play, crimson_focus(true));
            }
            if (failed || stopped) {
                ButtonSpec again;
                again.label = "Try Again";
                again.kind = ButtonKind::Primary;
                again.prompt = Prompt::Accept;
                again.half = Half::Crimson;
                button(ui, "task/again", again, crimson_focus(true));
            }
            ButtonSpec close;
            close.label = "Close";
            close.prompt = Prompt::Back;
            close.half = Half::Crimson;
            button(ui, "task/close", close, crimson_focus(!can_play && !failed && !stopped));
        }
        ButtonSpec details;
        details.label = view_.task.details.checked ? "Hide Details" : "Details";
        details.prompt = Prompt::Context2;
        details.half = Half::Crimson;
        button(ui, "details", details, crimson_focus());
    }
    auto g = ui.open("home/blue", blue);
#ifdef _WIN32
    const fs::path folder = task_kind_ == m::TaskKind::kLauncherUpdate && !exe_.empty() ? exe_.parent_path()
                                                                                        : f.install.folder;
#else
    const fs::path folder = task_kind_ == m::TaskKind::kInstall && !f.installing.empty() ? f.installing
                            : task_kind_ == m::TaskKind::kLauncherUpdate && appimage_    ? appimage_->parent_path()
                                                                                         : f.install.folder;
#endif
    section_label(ui, "task/label", running ? "Progress" : "What happened", Half::Blue, {}, fit({}, SeamFit::BlueRect));
    {
        auto k = ui.open("task/kick", fit(Box{.layout = Layout::Row, .h = Size::fixed(26), .margin = {0, 0, 0, 8},
                                              .gap = 12, .align = Align::Center},
                                          SeamFit::BlueRect));
        if (running) pill(ui, "task/pill", r.view().button.label == "Stopping…" ? "Stopping" : "Running", Tone::Blue, true);
        else pill(ui, "task/pill", ok ? "Done" : stopped ? "Stopped" : "Failed", ok ? Tone::Ok : stopped ? Tone::Warn : Tone::Bad);
        text(ui, "task/folder", TextSpec{m::shown_path(folder), tx::kKick, c::kBlueDim}, Box{.w = Size::grow()});
    }
    const char* doing = task_kind_ == m::TaskKind::kInstall      ? "Installing"
                        : task_kind_ == m::TaskKind::kUpdate     ? "Updating"
                        : task_kind_ == m::TaskKind::kUninstall  ? "Uninstalling"
                                                                 : "Updating";
    const std::string big = running ? doing : last.title;
    text(ui, "task/title", TextSpec{.text = big, .style = tx::kBig, .chroma = 3, .autofit_min = 26},
         fit({}, SeamFit::BlueRect));
    text(ui, "task/game",
         TextSpec{task_kind_ == m::TaskKind::kLauncherUpdate ? "Ultimate Launcher" : "Tekken Tag Tournament 2",
                  tx::kLastName, rgb(0xe9edf5)},
         fit(Box{.margin = {0, 0, 0, 4}}, SeamFit::BlueRect));
    const std::string pct = fraction >= 0 ? std::to_string(static_cast<int>(std::floor(fraction * 100 + 1e-6))) + "%"
                                          : std::string("…");
    // The big number with where it is beside it ("Step 4 of 7 / Compiling"), the bar, then what the step does.
    std::string where, step_name;
    if (build && at > 0) {
        where = running ? "Step " + std::to_string(at) + " of " + std::to_string(steps.size())
                : ok    ? "All " + std::to_string(steps.size()) + " steps"
                        : "Stopped at step " + std::to_string(at) + " of " + std::to_string(steps.size());
        step_name = ok ? std::string("Done") : steps[static_cast<size_t>(at - 1)].name;
    } else if (!running) {
        where = ok ? "Done" : stopped ? "Stopped" : "Failed";
    }
    {
        auto row = ui.open("task/numbers", fit(Box{.layout = Layout::Row, .gap = 22, .align = Align::Center},
                                               SeamFit::BlueRect));
        text(ui, "task/pct", TextSpec{.text = pct, .style = tx::kPercent, .chroma = 3});
        auto col = ui.open("task/where-col", Box{.w = Size::grow(), .gap = 4});
        if (!where.empty())
            text(ui, "task/where", TextSpec{where, tx::kLabelEm, ok ? c::kOk : failed ? c::kBad : c::kCyan});
        if (!step_name.empty())
            text(ui, "task/step", TextSpec{.text = step_name, .style = tx::kGroupTitle, .autofit_min = 16});
    }
    progress_bar(ui, "task/bar", static_cast<float>(fraction), ok ? Tone::Ok : failed ? Tone::Bad : Tone::Blue,
                 fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
    std::string headline, detail;
    if (running) {
        headline = build && at > 0 ? steps[static_cast<size_t>(at - 1)].text : r.progress_state().step();
        const std::string count = build && at > 0 ? steps[static_cast<size_t>(at - 1)].count : std::string();
        if (!count.empty()) headline += (headline.empty() ? "" : "  ·  ") + count;
        else if (!r.progress_state().detail().empty())
            headline += (headline.empty() ? "" : "  ·  ") + r.progress_state().detail();
        if (headline.empty()) headline = view_.task.detail;
    } else {
        if (build && at > 0 && !ok) {
            const StepLine& l = steps[static_cast<size_t>(at - 1)];
            headline = "Stopped at: " + l.text + (l.count.empty() ? "" : "  ·  " + l.count);
        }
        detail = last.detail;
    }
    if (!headline.empty())
        text(ui, "task/headline", TextSpec{.text = headline, .style = tx::kFileName, .color = rgb(0xe9edf5)},
             fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    if (!detail.empty())
        text(ui, "task/detail", TextSpec{.text = detail, .style = tx::kParaSmall, .color = c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
    if (view_.task.details.checked) {
        log_view(ui, "task/log", log_, fit(Box{.h = Size::fixed(220), .margin = {0, 4, 0, 0}}, SeamFit::BlueRect));
        return;
    }
    if (running && task_kind_ == m::TaskKind::kInstall) {
        describe_panel(ui, "task/xpl", "While it runs",
                       "The game program is built for this PC from your game, then the game is copied into this "
                       "folder. Stopping keeps what is copied: the install resumes from there.",
                       fit({}, SeamFit::BlueSkewed));
    } else if (ok && (task_kind_ == m::TaskKind::kInstall || task_kind_ == m::TaskKind::kUpdate)) {
        describe_panel(ui, "task/xpl", "Next",
                       "Fighters adds Tekken 7's and Tekken 8's characters from your own games; Settings has the "
                       "display and the keys.",
                       fit({}, SeamFit::BlueSkewed));
    } else if (failed) {
        describe_panel(ui, "task/xpl", "What now",
                       "Details has the task's own words. Try Again starts it again; Close goes back.",
                       fit({}, SeamFit::BlueSkewed));
    }
}

// Fighters and Settings: the next part of the overhaul builds them.
void App::placeholder(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const bool fighters = screen_ == Screen::kFighters;
    {
        auto g = ui.open("ph/crimson", crimson);
        section_label(ui, "ph/label", fighters ? "Fighters" : "Settings", Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        MenuRowSpec s{fighters ? "stroke:users" : "stroke:gear", "Back to Home"};
        menu_row(ui, "ph/home", s, crimson_focus(true), fit({}, SeamFit::CrimsonSkewed));
    }
    auto g = ui.open("ph/blue", blue);
    section_label(ui, "ph/b-label", fighters ? "Roster" : "Settings", Half::Blue, {}, fit({}, SeamFit::BlueRect));
    note(ui, "ph/note", Tone::Blue, "This screen is not built yet in this version of the launcher.",
         fit({}, SeamFit::BlueRect), "stroke:info");
}

} // namespace launcher::app
