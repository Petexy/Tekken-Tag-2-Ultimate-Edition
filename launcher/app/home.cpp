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

// `s` in capitals (Latin and Cyrillic letters too).
std::string upper(const std::string& s) {
    std::vector<char32_t> points;
    decode_utf8(s, points);
    std::string out;
    for (const char32_t c : points) out += encode_utf8(to_upper(c));
    return out;
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
    section_label(ui, "home/game-label", tr("home.the_game", "The game"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
    {
        auto k = ui.open("home/kick", fit(Box{.layout = Layout::Row, .h = Size::fixed(26), .margin = {0, 0, 0, 10},
                                              .gap = 12, .align = Align::Center},
                                          SeamFit::BlueRect));
        const bool live = view_.game.pill.live;
        pill(ui, "home/pill", view_.game.pill.text, live ? Tone::Blue : pill_tone(view_.game.pill.kind), live);
        TextSpec ks{kick, tx::kKick, c::kBlueDim};
        ks.autofit_min = 12;  // (a longer language beside a longer pill: a little smaller before it is cut)
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
        if (k == "update-everything" && !view_.game.update.empty()) {
            if (const m::Action* a = action(k)) update_list(*a);
            return;
        }
        if (const m::Action* a = action(k)) {
            title = a->describe.title.empty() ? a->label : a->describe.title;
            if (title.ends_with("…")) title.resize(title.size() - std::string("…").size());
            body = a->describe.explain.empty() ? a->tooltip : a->describe.explain;
            why = a->why;
            notes = a->primary || k == "update";
        } else if (k == "fighters") {
            title = tr("home.fighters", "Fighters");
            if (f.install.state == InstallState::kInstalled && f.status) {
                int added = 0, update = 0;
                for (const Fighter& x : f.status->fighters) {
                    added += x.added();
                    update += x.added() && x.update;
                }
                const i18n::Args args = {{"added", added}, {"total", f.status->fighters.size()}, {"update", update}};
                body = update ? trn("home.fighters_about_update", update,
                                    "Tekken 7's and Tekken 8's characters, made from your own games: {added} of "
                                    "{total} added, {update} to update.",
                                    "Tekken 7's and Tekken 8's characters, made from your own games: {added} of "
                                    "{total} added, {update} to update.",
                                    args)
                              : tr("home.fighters_about_added",
                                   "Tekken 7's and Tekken 8's characters, made from your own games: {added} of {total} "
                                   "added.",
                                   args);
            } else if (f.install.state == InstallState::kInstalled) {
                body = tr("home.fighters_about", "Tekken 7's and Tekken 8's characters, made from your own games.");
            } else {
                body = tr("home.fighters_about_later", "See which characters can be added: they are made from your "
                                                       "Tekken 7 and Tekken 8 once the game is installed.");
            }
        } else if (k == "slot:game") {
            title = tr("home.game_file", "Game file");
            body = f.chosen_game.empty()
                       ? tr("home.choose_wua_about", "Choose your .wua with the file browser: it works with a controller too.")
                       : tr("home.chosen_wua_about", "{file}, in {folder}. Choose another one with the file browser.",
                            {{"file", path_utf8(f.chosen_game.filename())},
                             {"folder", m::shown_path(f.chosen_game.parent_path())}});
        } else if (k == "slot:folder") {
            title = tr("home.install_folder", "Install folder");
            body = tr("home.folder_about", "The game goes into {folder}. Choose another place with the folder browser.",
                      {{"folder", slot_target()}});
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
    // (Home's UPDATE gets it with the rest: one Update, the slab's.)
    if (view_.notice.whole && screen_ == Screen::kHome) return;
    ButtonSpec u;
    u.label = view_.notice.update.label;
    u.kind = ButtonKind::Blue;
    u.size = ButtonSize::Tiny;
    u.disabled = !view_.notice.update.enabled;
    Focus uf = blue_focus();
    uf.disabled = u.disabled;
    button(ui, "notice-update", u, uf);
}

// Home's UPDATE in the slab: the word and what it brings up to date ("launcher, game" / "+ fighters").
SlabSpec App::update_slab() const {
    std::vector<std::string> kinds;
    for (const m::UpdatePart& p : view_.game.update)
        if (p.kind == "launcher" || p.kind == "game" || p.kind == "fighters") kinds.push_back(p.kind);
    const auto name = [](const std::string& kind) {
        return kind == "launcher" ? tr("slab.launcher", "launcher")
               : kind == "game"   ? tr("slab.game", "game")
                                  : tr("slab.fighters", "fighters");
    };
    const std::string big = tr("slab.update", "Update");
    if (kinds.size() == 1) {
        const std::string one = kinds[0] == "launcher" ? tr("slab.the_launcher", "the launcher")
                                : kinds[0] == "game"   ? tr("slab.the_game", "the game")
                                                       : tr("slab.the_fighters", "the fighters");
        return {big, one, tr("slab.then_play", "then play")};
    }
    if (kinds.size() == 2)
        return {big, tr("slab.two", "{first} + {second}", {{"first", name(kinds[0])}, {"second", name(kinds[1])}}),
                tr("slab.then_play", "then play")};
    if (kinds.size() < 3) return {big, {}, {}};
    return {big, tr("slab.three_first", "{first}, {second}", {{"first", name(kinds[0])}, {"second", name(kinds[1])}}),
            tr("slab.three_last", "+ {third}", {{"third", name(kinds[2])}})};
}

// The focused UPDATE on the blue side: what it does, its parts in order (numbered), what it leaves for later.
void App::update_list(const m::Action& a) {
    Ui& ui = *ui_;
    describe_panel(ui, "home/xpl", tr("slab.update", "Update"), a.describe.explain, fit({}, SeamFit::BlueSkewed));
    if (!a.why.empty())
        note(ui, "home/why", Tone::Warn, a.why, fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect), "stroke:warn");
    int n = 0;
    for (const m::UpdatePart& p : view_.game.update) {
        if (p.kind == "later") {
            note(ui, "home/later", Tone::Warn, tr("common.title_detail", "{title}: {detail}", {{"title", p.title}, {"detail", p.text}}),
                 fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect), "stroke:warn");
            continue;
        }
        ++n;
        numbered_item(ui, "home/part" + std::to_string(n), n, p.title, p.text,
                      fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect));
    }
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
    // (The slab became UPDATE while Play was focused, the importer's answer in: the focus goes with the slab, so that
    // Accept does what the big button says.)
    if (primary && primary->id != home_primary_ && ui.focused() == home_primary_) ui_->focus(primary->id, false);
    home_primary_ = primary ? primary->id : std::string();
    {
        auto g = ui.open("home/crimson", crimson);
        section_label(ui, "home/menu-label", tr("home.menu", "Menu"), Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (primary) {
            SlabSpec s;
            if (primary->id == "update-everything") s = update_slab();
            else if (primary->id == "update")
                s = {tr("slab.update", "Update"), tr("slab.then_play", "then play"), tr("slab.few_minutes", "a few minutes")};
            else s = {primary->label, "Tekken Tag", "Tournament 2"};
            s.mid = s.big.size() > 6;
            s.disabled = !primary->enabled;
            slab(ui, primary->id, s, crimson_focus(true, !primary->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        // (Update in the slab: Play is an ordinary row, first.)
        if (const m::Action* play = action("play"); play && !play->primary) {
            MenuRowSpec p{"stroke:play", play->label};
            p.disabled = !play->enabled;
            menu_row(ui, "play", p, crimson_focus(false, !play->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
        menu_row(ui, "fighters",
                 {"stroke:users", tr("home.fighters", "Fighters"),
                  f.status ? tr("progress.of", "{done} of {total}", {{"done", added}, {"total", total}}) : ""},
                 crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", tr("home.settings", "Settings")}, crimson_focus(),
                 fit({}, SeamFit::CrimsonSkewed));
        for (const m::Action& a : view_.game.actions) {
            if (a.id == "update" && !a.primary) {
                MenuRowSpec u{"stroke:update", tr("home.update_game", "Update the game"), tr("home.ready", "Ready")};
                u.value_tone = Tone::Warn;
                u.disabled = !a.enabled;
                menu_row(ui, "update", u, crimson_focus(false, !a.enabled), fit({}, SeamFit::CrimsonSkewed));
            }
        }
        if (action("open-folder"))
            menu_row(ui, "open-folder", {"stroke:folder", tr("home.open_folder", "Open the game folder")}, crimson_focus(),
                     fit({}, SeamFit::CrimsonSkewed));
        if (const m::Action* more = action("more")) {
            MenuRowSpec s{"stroke:dots", tr("home.more", "More"), tr("home.more_value", "Build, install, logs")};
            s.disabled = !more->enabled;
            menu_row(ui, "more", s, crimson_focus(false, !more->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
        if (const m::Action* un = action("uninstall")) {
            MenuRowSpec s{"stroke:trash", tr("home.uninstall", "Uninstall")};
            s.danger = true;
            s.disabled = !un->enabled;
            menu_row(ui, "uninstall", s, crimson_focus(false, !un->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
    }
    auto g = ui.open("home/blue", blue);
    const std::string kick = f.game_built.empty()
                                 ? tr("home.not_built_here", "Not built by this launcher")
                                 : tr("home.built_here", "Game {version} · built on this PC",
                                      {{"version", launcher_version(f.game_built)}});
    game_head(kick);
    std::vector<Run> fighters_runs;
    if (f.status) {
        fighters_runs.push_back({tr("home.added_of", "{added} of {total} added", {{"added", added}, {"total", total}}), kValue});
        if (update) {
            fighters_runs.push_back({" · ", kValue});
            fighters_runs.push_back({trn("home.to_update", update, "{n} to update", "{n} to update"), c::kWarn});
        }
    } else {
        fighters_runs.push_back({f.status_loading ? tr("home.looking", "Looking…") : tr("home.not_known", "Not known"),
                                 c::kBlueDim});
    }
    const Fact list[] = {
        {tr("home.version", "Version"),
         {{f.game_built.empty() ? tr("home.unknown", "Unknown") : m::shown_build(f.game_built), kValue}}},
        {tr("home.folder", "Folder"), {{m::shown_path(f.install.folder), kValue}}},
        {tr("home.fighters", "Fighters"), fighters_runs, false}};
    // (Drilled into More: its entries and what the focused one does take the facts' place.)
    if (drilled() && drill_->opener == "more") return more_view();
    const std::string& fo = ui.focused();
    if (!fo.empty() && (ui.rect(fo).x < stage_->seam_now().x_at(ui.rect(fo).center().y) ||
                        fo == "notice-update" || fo == "release-page"))
        readout_key_ = fo;
    // (UPDATE focused: its parts take the facts' and the notice's place, what they say is in them; a small window
    // scrolls to them while they come in, then leaves the scrolling to the player.)
    const bool parts = readout_key_ == "update-everything" && !view_.game.update.empty();
    if (!parts) {
        facts(ui, "home/facts", list, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
        notice_card();
        update_scroll_since_ = -1;
    } else {
        // (Again when a part comes in: the fighters' once the importer has answered.)
        if (update_scroll_since_ < 0 || update_parts_seen_ != view_.game.update.size()) {
            update_scroll_since_ = ui.now();
            update_parts_seen_ = view_.game.update.size();
        }
        if (ui.now() - update_scroll_since_ < 1.0) ui.scroll_to_end("home/blue");
    }
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
        section_label(ui, "home/menu-label", tr("home.set_up", "Set Up"), Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (setup) {
            SlabSpec s{tr("slab.set_up", "Set Up"), tr("slab.from_your", "from your"), tr("slab.own_wua", "own .wua")};
            s.mid = true;
            s.disabled = !setup->enabled;
            slab(ui, "setup", s, crimson_focus(true, !setup->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        menu_row(ui, "fighters", {"stroke:users", tr("home.fighters", "Fighters")}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", tr("home.settings", "Settings")}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        if (const m::Action* more = action("more")) {
            MenuRowSpec s{"stroke:dots", tr("home.more", "More"), tr("home.more_value", "Build, install, logs")};
            s.disabled = !more->enabled;
            menu_row(ui, "more", s, crimson_focus(false, !more->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
    }
    auto g = ui.open("home/blue", blue);
    game_head(tr("home.port_kick", "Native PC port · built from your own copy"));
    const auto folder = [&](const char* key) {
        const auto it = f.windows.folders.find(key);
        return it == f.windows.folders.end() ? std::string() : it->second;
    };
    const std::string source = folder("source"), install = folder("install");
    section_label(ui, "home/needs-label", tr("home.setup_needs", "What the setup needs"), Half::Blue, {},
                  fit(Box{.margin = {0, 4, 0, 0}}, SeamFit::BlueRect));
    const std::string later = tr("home.chosen_later", "Chosen when you set up");
    const Fact list[] = {
        {tr("home.your_copy", "Your copy"),
         {{tr("home.your_copy_value", "{game}: European, update 16, as a .wua archive",
              {{"game", "TEKKEN TAG TOURNAMENT 2 WII U EDITION"}}),
           kValue}},
         false},
        {tr("home.archive", "Archive"),
         {{source.empty() ? later : m::shown_path(utf8_path(source)), source.empty() ? c::kBlueDim : kValue}},
         !source.empty()},
        {tr("home.folder", "Folder"),
         {{install.empty() ? later : m::shown_path(utf8_path(install)), install.empty() ? c::kBlueDim : kValue}},
         !install.empty()},
        {tr("home.space", "Space"), {{tr("home.setup_space", "About 30 GB and internet: the tools are downloaded once"), kValue}},
         false}};
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

// Windows' More, drilled into from its row: its entries on the blue side (the crimson side locked).
void App::more_view() {
    Ui& ui = *ui_;
    section_label(ui, "more/label", tr("home.more", "More"), Half::Blue, {}, fit(Box{.margin = {0, 6, 0, 8}}, SeamFit::BlueRect));
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
            body = id == "more:build"
                       ? tr("more.build_about", "Builds the Windows game program again from the extracted game (a while).")
                   : id == "more:install"     ? tr("more.install_about", "Installs the built game into the installation folder.")
                   : id == "more:update"      ? tr("more.update_about", "Puts the newest built program into the installed game.")
                   : id == "more:setup-again" ? tr("more.setup_again_about", "Set Up Game again: another archive or folder.")
                   : id == "more:open-logs"   ? tr("more.open_logs_about", "Opens the folder of every task's log.")
                                              : tr("more.open_log_about", "Opens the newest task's log.");
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
        section_label(ui, "home/menu-label", tr("home.install", "Install"), Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (install) {
            SlabSpec s{tr("slab.install", "Install"), tr("slab.from_your", "from your"), tr("slab.own_wua", "own .wua")};
            s.mid = true;
            s.disabled = !install->enabled;
            slab(ui, "install", s, crimson_focus(true, !install->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        MenuRowSpec one;
        one.number = 1;
        one.caption = tr("home.game_file", "Game file");
        one.title = f.chosen_game.empty() ? tr("home.choose_wua", "Choose your .wua") : path_utf8(f.chosen_game.filename());
        one.ok = !f.chosen_game.empty();
        one.mono_title = !f.chosen_game.empty();
        menu_row(ui, "slot:game", one, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        MenuRowSpec two;
        two.number = 2;
        two.caption = tr("home.install_folder", "Install folder");
        two.title = slot_target();
        two.mono_title = true;
        two.ok = true;
        menu_row(ui, "slot:folder", two, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "fighters", {"stroke:users", tr("home.fighters", "Fighters")}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", tr("home.settings", "Settings")}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
    }
    auto g = ui.open("home/blue", blue);
    game_head(tr("home.port_kick", "Native PC port · built from your own copy"));
    section_label(ui, "home/needs-label", tr("home.install_needs", "What the install needs"), Half::Blue, {},
                  fit(Box{.margin = {0, 4, 0, 0}}, SeamFit::BlueRect));
    const Fact list[] = {
        {tr("home.your_copy", "Your copy"),
         {{tr("home.your_copy_value", "{game}: European, update 16, as a .wua archive",
              {{"game", "TEKKEN TAG TOURNAMENT 2 WII U EDITION"}}),
           kValue}},
         false},
        {tr("home.game_file", "Game file"),
         {{f.chosen_game.empty() ? tr("home.not_chosen", "Not chosen yet") : path_utf8(f.chosen_game.filename()),
           f.chosen_game.empty() ? c::kWarn : kValue}},
         !f.chosen_game.empty()},
        {tr("home.space", "Space"), {{tr("home.install_space", "About 16 GB, plus 3 GB while building"), kValue}}, false},
        {tr("home.this_pc", "This PC"),
         {{tr("home.this_pc_value", "A C++ compiler and an x86-64-v3 processor: checked first"), kValue}}, false}};
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
        section_label(ui, "home/menu-label", tr("home.menu", "Menu"), Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        if (const m::Action* r = action("resume")) {
            SlabSpec s{tr("slab.resume", "Resume"), tr("slab.the_install", "the install"), tr("slab.not_finished", "not finished")};
            s.mid = true;
            s.disabled = !r->enabled;
            slab(ui, "resume", s, crimson_focus(true, !r->enabled),
                 fit(Box{.margin = {0, 0, 0, 18}}, SeamFit::CrimsonSkewed));
        }
        auto rows = ui.open("home/rows", Box{.gap = 10});
        menu_row(ui, "fighters", {"stroke:users", tr("home.fighters", "Fighters")}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        menu_row(ui, "settings", {"stroke:gear", tr("home.settings", "Settings")}, crimson_focus(), fit({}, SeamFit::CrimsonSkewed));
        if (const m::Action* un = action("uninstall")) {
            MenuRowSpec s{"stroke:trash", tr("home.uninstall", "Uninstall")};
            s.danger = true;
            s.disabled = !un->enabled;
            menu_row(ui, "uninstall", s, crimson_focus(false, !un->enabled), fit({}, SeamFit::CrimsonSkewed));
        }
    }
    auto g = ui.open("home/blue", blue);
    game_head(tr("home.stopped_kick", "Stopped before it was complete"));
    const Fact list[] = {{tr("home.folder", "Folder"), {{m::shown_path(f.install.folder), kValue}}},
                         {tr("home.game_file", "Game file"),
                          {{f.install.game.empty() ? tr("home.asked_later", "Asked for when it resumes")
                                                   : m::shown_path(f.install.game),
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
        section_label(ui, "pre/label", tr("pre.before", "Before the install"), Half::Crimson,
                      running ? "" : trn("pre.checks", static_cast<long long>(checks.size()), "{n} check", "{n} checks"),
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        auto rows = ui.open("pre/rows", Box{.gap = 8});
        if (running) {
            MenuRowSpec s{"stroke:dots", tr("pre.checking_pc", "Checking this PC…")};
            s.compact = true;
            menu_row(ui, "check:0", s, crimson_focus(true), fit({}, SeamFit::CrimsonSkewed));
        }
        int first_bad = -1;
        for (size_t i = 0; i < checks.size(); ++i)
            if (first_bad < 0 && checks[i]->icon_tone == m::Tone::kError) first_bad = static_cast<int>(i);
        for (size_t i = 0; i < checks.size(); ++i) {
            const m::Line& l = *checks[i];
            const bool ok = l.icon_tone != m::Tone::kError;
            MenuRowSpec s{ok ? "stroke:check" : "stroke:cross", l.title,
                          ok ? tr("home.ready", "Ready") : tr("pre.missing", "Missing")};
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
            again.label = tr("pre.check_again", "Check Again");
            again.kind = ButtonKind::Primary;
            again.prompt = Prompt::Accept;
            again.half = Half::Crimson;
            button(ui, "check-again", again, crimson_focus());
            ButtonSpec cancel;
            cancel.label = tr("common.cancel", "Cancel");
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
            section_label(ui, "pre/c-label", tr("pre.checking", "Checking"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
            text(ui, "pre/c-title",
                 TextSpec{.text = tr("home.this_pc", "This PC"), .style = tx::kBig, .chroma = 3, .autofit_min = 30},
                 fit({}, SeamFit::BlueRect));
            text(ui, "pre/c-text",
                 TextSpec{.text = tr("pre.checking_about", "The game file, the processor, a C++ compiler and the free "
                                                           "space are checked before the install starts."),
                          .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect));
            return;
        }
        const size_t i = std::min(checks.size() - 1, static_cast<size_t>(std::max(0, std::atoi(k.c_str() + 6))));
        const m::Line& l = *checks[i];
        const bool ok = l.icon_tone != m::Tone::kError;
        section_label(ui, "pre/c-label",
                      tr("pre.check_of", "Check {i} of {n}", {{"i", i + 1}, {"n", checks.size()}}),
                      Half::Blue, {}, fit({}, SeamFit::BlueRect));
        pill(ui, "pre/c-pill", ok ? tr("home.ready", "Ready") : tr("pre.missing", "Missing"), ok ? Tone::Ok : Tone::Bad, false,
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
            b.label = tr("pre.copy", "Copy");
            b.kind = ButtonKind::Blue;
            b.size = ButtonSize::Small;
            button(ui, a.id, b, blue_focus(), fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        }
        if (!ok) {
            text(ui, "pre/c-then",
                 TextSpec{.text = tr("pre.then_again", "Then Check Again: the install starts once everything is ready."),
                          .style = tx::kParaSmall, .color = c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
        }
    });
    if (f.preflight) {
        const Fact list[] = {{tr("home.game_file", "Game file"), {{m::shown_path(f.preflight->game), kValue}}},
                             {tr("pre.into", "Into"), {{m::shown_path(f.preflight->folder), kValue}}}};
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
    // Home's UPDATE: its parts one after another ("Update · 2 of 3 · The game program"); between two of them (the
    // next starts by itself) and once the new launcher opens, nothing to close yet.
    const m::TaskView::Chain& chain = view_.task.chain;
    const bool update = chain.count > 0;
    const bool between = update && !running && (chain.waiting || chain.handed_over);
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
        const std::string steps_label = build ? trn("task.steps_n", static_cast<long long>(steps.size()), "{n} step", "{n} steps")
                                              : tr("task.steps", "Steps");
        section_label(ui, "task/steps-label",
                      !update       ? steps_label
                      : chain.done ? tr("task.last_part", "Last part · {steps}", {{"steps", steps_label}})
                                   : tr("task.part_of_steps", "Part {i} of {n} · {steps}",
                                        {{"i", chain.waiting ? chain.at - 1 : chain.at},
                                         {"n", chain.count},
                                         {"steps", steps_label}}),
                      Half::Crimson, {}, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        {
            std::vector<std::string> names;
            for (const StepLine& step : steps) names.push_back(step.name);
            const float name_width = step_name_width(ui.text(), names);
            auto rows = ui.open("task/rows", Box{.gap = 6});
            for (size_t i = 0; i < steps.size(); ++i) {
                StepRowSpec s;
                s.name = steps[i].name;
                s.name_width = name_width;
                s.count = steps[i].state == StepLine::State::kDone     ? tr("task.done", "Done")
                          : steps[i].state == StepLine::State::kFailed ? tr("task.stopped", "Stopped")
                          : !steps[i].slash.empty()                    ? steps[i].slash
                                                                       : steps[i].count;
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
        const bool can_play = ok && !between &&
                              (update ? chain.done
                                      : task_kind_ == m::TaskKind::kInstall || task_kind_ == m::TaskKind::kUpdate) &&
                              action("play") && action("play")->enabled;
        if (between && chain.handed_over) {
            // (The new launcher opens and this one ends: nothing to press.)
        } else if (running || between) {
            ButtonSpec cancel;
            cancel.label =
                !running || view_.task.button.label.empty() ? tr("common.cancel", "Cancel") : view_.task.button.label;
            cancel.prompt = Prompt::Back;
            cancel.half = Half::Crimson;
            cancel.disabled = !view_.task.button.enabled;
            button(ui, "task", cancel, crimson_focus(true, cancel.disabled));
        } else {
            if (can_play) {
                ButtonSpec play;
                play.label = tr("game.play", "Play");
                play.kind = ButtonKind::Primary;
                play.prompt = Prompt::Accept;
                play.half = Half::Crimson;
                button(ui, "task/play", play, crimson_focus(true));
            }
            if (failed || stopped) {
                ButtonSpec again;
                again.label = tr("task.try_again", "Try Again");
                again.kind = ButtonKind::Primary;
                again.prompt = Prompt::Accept;
                again.half = Half::Crimson;
                button(ui, "task/again", again, crimson_focus(true));
            }
            ButtonSpec close;
            close.label = tr("common.close", "Close");
            close.prompt = Prompt::Back;
            close.half = Half::Crimson;
            button(ui, "task/close", close, crimson_focus(!can_play && !failed && !stopped));
        }
        ButtonSpec details;
        details.label = view_.task.details.checked ? tr("task.hide_details", "Hide Details") : tr("task.details", "Details");
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
    section_label(ui, "task/label", running ? tr("task.progress", "Progress") : tr("task.what_happened", "What happened"),
                  Half::Blue, {}, fit({}, SeamFit::BlueRect));
    {
        auto k = ui.open("task/kick", fit(Box{.layout = Layout::Row, .h = Size::fixed(26), .margin = {0, 0, 0, 8},
                                              .gap = 12, .align = Align::Center},
                                          SeamFit::BlueRect));
        const std::string running_text = tr("task.running", "Running");
        if (running)
            pill(ui, "task/pill", view_.task.stopping ? tr("task.stopping_pill", "Stopping") : running_text, Tone::Blue, true);
        else if (between && chain.waiting) pill(ui, "task/pill", running_text, Tone::Blue, true);
        else
            pill(ui, "task/pill", ok ? tr("task.done", "Done") : stopped ? tr("task.stopped", "Stopped") : tr("task.failed_pill", "Failed"),
                 ok ? Tone::Ok : stopped ? Tone::Warn : Tone::Bad);
        if (update) {
            // ("UPDATE · 2 OF 3 · THE GAME PROGRAM": the part that runs, or the one that starts next.)
            std::string kick = tr("task.update_kick", "Update · {i} of {n} · {part}",
                                  {{"i", chain.at}, {"n", chain.count},
                                   {"part", chain.waiting && !chain.next.empty() ? chain.next[0].title : chain.part}});
            if (chain.done) kick = tr("task.update_kick_all", "Update · all {n} parts", {{"n", chain.count}});
            kick = upper(kick);
            text(ui, "task/folder", TextSpec{kick, tx::kKick, c::kCyan}, Box{.w = Size::grow()});
        } else {
            text(ui, "task/folder", TextSpec{m::shown_path(folder), tx::kKick, c::kBlueDim}, Box{.w = Size::grow()});
        }
    }
    const std::string doing = task_kind_ == m::TaskKind::kInstall     ? tr("game.pill_installing", "Installing")
                              : task_kind_ == m::TaskKind::kUninstall ? tr("game.pill_uninstalling", "Uninstalling")
                                                                      : tr("game.pill_updating", "Updating");
    const std::string big = running || (between && chain.waiting) ? doing
                            : update && chain.done                ? tr("task.updated", "Updated")
                                                                  : last.title;
    text(ui, "task/title", TextSpec{.text = big, .style = tx::kBig, .chroma = 3, .autofit_min = 26},
         fit({}, SeamFit::BlueRect));
    text(ui, "task/game",
         TextSpec{.text = task_kind_ == m::TaskKind::kLauncherUpdate ? "Golden Fist Launcher"
                                                                     : "Tekken Tag Tournament 2",
                  .style = tx::kLastName, .color = rgb(0xe9edf5), .autofit_min = 20},
         fit(Box{.margin = {0, 0, 0, 4}}, SeamFit::BlueRect));
    const std::string pct = fraction >= 0 ? std::to_string(static_cast<int>(std::floor(fraction * 100 + 1e-6))) + "%"
                                          : std::string("…");
    // The big number with where it is beside it ("Step 4 of 7 / Compiling"), the bar, then what the step does.
    std::string where, step_name;
    if (build && at > 0) {
        const i18n::Args args = {{"i", at}, {"n", steps.size()}};
        where = running ? tr("task.step_of", "Step {i} of {n}", args)
                : ok    ? trn("task.all_steps", static_cast<long long>(steps.size()), "All {n} steps", "All {n} steps")
                        : tr("task.stopped_at_step", "Stopped at step {i} of {n}", args);
        step_name = ok ? tr("task.done", "Done") : steps[static_cast<size_t>(at - 1)].name;
    } else if (!running) {
        where = ok ? tr("task.done", "Done") : stopped ? tr("task.stopped", "Stopped") : tr("task.failed_pill", "Failed");
    }
    if (between && chain.waiting) {
        where = tr("task.part_done", "Part {i} of {n} done", {{"i", chain.at - 1}, {"n", chain.count}});
        step_name = tr("task.next_part", "Next: {part}", {{"part", chain.next.empty() ? chain.part : chain.next[0].title}});
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
            headline = tr("task.stopped_at", "Stopped at: {step}", {{"step", l.text}}) + (l.count.empty() ? "" : "  ·  " + l.count);
        }
        detail = last.detail;
        if (between && chain.waiting) {
            headline = tr("task.next_soon", "The next part starts by itself in a moment.");
            detail.clear();
        } else if (between) {
            headline = tr("task.handed_over", "{title}: the new launcher opens and goes on with the rest.", {{"title", last.title}});
            detail.clear();
        } else if (update && chain.done) {
            headline = chain.summary;
            detail = chain.later;
        } else if (update && !ok) {
            detail = chain.later.empty() || last.detail.empty()
                         ? last.detail + chain.later
                         : tr("common.two_sentences", "{first} {second}", {{"first", last.detail}, {"second", chain.later}});
        }
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
    if (update && (running || between) && !chain.next.empty() && !chain.handed_over) {
        // What comes after this part, in order.
        text(ui, "task/next-label", TextSpec{tr("task.then", "Then"), tx::kLabelEm, c::kCyan},
             fit(Box{.margin = {0, 12, 0, 0}}, SeamFit::BlueRect));
        int n = chain.waiting ? chain.at : chain.at + 1;
        for (size_t i = 0; i < chain.next.size(); ++i, ++n) {
            numbered_item(ui, "task/next" + std::to_string(i), n, chain.next[i].title, chain.next[i].text,
                          fit(Box{.margin = {0, 8, 0, 0}}, SeamFit::BlueRect));
        }
    } else if (update && chain.done) {
        describe_panel(ui, "task/xpl", tr("task.next", "Next"),
                       tr("task.next_update_about", "Play starts the game. Fighters has every character; Settings the "
                                                    "display and the keys."),
                       fit({}, SeamFit::BlueSkewed));
    } else if (update && (failed || stopped)) {
        describe_panel(ui, "task/xpl", tr("task.what_now", "What now"),
                       tr("task.what_now_update", "Details has this part's own words. Try Again goes on from it: the "
                                                  "parts done stay done. Close leaves the rest for Update on Home."),
                       fit({}, SeamFit::BlueSkewed));
    } else if (update) {
    } else if (running && task_kind_ == m::TaskKind::kInstall) {
        describe_panel(ui, "task/xpl", tr("task.while_it_runs", "While it runs"),
                       tr("task.while_install", "The game program is built for this PC from your game, then the game is "
                                                "copied into this folder. Stopping keeps what is copied: the install "
                                                "resumes from there."),
                       fit({}, SeamFit::BlueSkewed));
    } else if (ok && (task_kind_ == m::TaskKind::kInstall || task_kind_ == m::TaskKind::kUpdate)) {
        describe_panel(ui, "task/xpl", tr("task.next", "Next"),
                       tr("task.next_install_about", "Fighters adds Tekken 7's and Tekken 8's characters from your own "
                                                     "games; Settings has the display and the keys."),
                       fit({}, SeamFit::BlueSkewed));
    } else if (failed) {
        describe_panel(ui, "task/xpl", tr("task.what_now", "What now"),
                       tr("task.what_now_about", "Details has the task's own words. Try Again starts it again; Close "
                                                 "goes back."),
                       fit({}, SeamFit::BlueSkewed));
    }
}

// Fighters and Settings: the next part of the overhaul builds them.
void App::placeholder(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const bool fighters = screen_ == Screen::kFighters;
    {
        auto g = ui.open("ph/crimson", crimson);
        section_label(ui, "ph/label", fighters ? tr("home.fighters", "Fighters") : tr("home.settings", "Settings"),
                      Half::Crimson, {}, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        MenuRowSpec s{fighters ? "stroke:users" : "stroke:gear", tr("home.back_home", "Back to Home")};
        menu_row(ui, "ph/home", s, crimson_focus(true), fit({}, SeamFit::CrimsonSkewed));
    }
    auto g = ui.open("ph/blue", blue);
    section_label(ui, "ph/b-label", fighters ? tr("home.roster", "Roster") : tr("home.settings", "Settings"), Half::Blue,
                  {}, fit({}, SeamFit::BlueRect));
    note(ui, "ph/note", Tone::Blue, tr("home.not_built_yet", "This screen is not built yet in this version of the launcher."),
         fit({}, SeamFit::BlueRect), "stroke:info");
}

} // namespace launcher::app
