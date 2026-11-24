// launcher_ui_demo: the toolkit's Tag Split screens (Home, Fighters, Settings) built from FAKE data, to show and test
// the toolkit without the launcher's model. Nothing here is the launcher: no files, no game, no settings saved.
//
//   launcher_ui_demo [--screen home|fighters|settings|widgets] [--dialog] [--size WxH] [--scale S]
//                    [--glyphs kb|xbox|ps|nintendo|generic] [--reduced] [--script FILE] [--frames N]
//                    [--screenshot FILE [--compare REF.png [--tolerance T] [--max-changed N]]] [--write-reference F]
//   launcher_ui_demo --version
//   launcher_ui_demo --sounds-wav DIR [GAME_FOLDER]
//
// --screenshot: SDL's offscreen driver and the software renderer, a fixed clock (60 frames a second, N frames),
// the ambient layer still, a seeded random source: the same picture every time. --script: input events at times
// ("0.5 key Down", "1 pad South", "1.2 move 300 400", "1.3 click 300 400", "1.5 wheel -1"; '#' comments).
// --compare: the frame scaled down to the reference's size; exit 3 when the mean difference is over T (default 4)
// or more than --max-changed pixels (default 200 of a 320 x 200 reference) differ by more than 48 in a channel.
// Every --screenshot also checks the last frame's layout (Ui::audit: everything painted keeps the gutter from its
// half's seam, the highlight is not empty): exit 4 with the problems listed.
// --sounds-wav: every cue's sound (the launcher's own, and the game's from GAME_FOLDER when given) as WAV files to
// listen to; no window, no audio device.
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shellapi.h>
#endif

#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "ttt2ui/sound.h"
#include "ttt2ui/stage.h"
#include "ttt2ui/widgets.h"
#include "ttt2ui/window.h"

using namespace ttt2::ui;
namespace c = theme::color;
namespace tx = theme::text;

namespace {

void say(std::string_view text, bool error = false) {
#ifdef _WIN32
    HANDLE out = GetStdHandle(error ? STD_ERROR_HANDLE : STD_OUTPUT_HANDLE);
    DWORD written = 0;
    if (out && out != INVALID_HANDLE_VALUE)
        WriteFile(out, text.data(), static_cast<DWORD>(text.size()), &written, nullptr);
#else
    std::fwrite(text.data(), 1, text.size(), error ? stderr : stdout);
    std::fflush(error ? stderr : stdout);
#endif
}

// ---- fake data ------------------------------------------------------------------------------------------------------

struct Fighter {
    std::string first, last, code, short_name;
    int group;  // 0 Tekken 7, 1 DLC, 2 Tekken 8
    TileState state;
    int outfits;
    bool with_outfits;
};

std::vector<Fighter> fake_fighters() {
    struct Row {
        const char *first, *last, *code, *short_name;
        int group;
        TileState st;
        int n;
        bool o;
    };
    using S = TileState;
    const Row rows[] = {{"Kazumi", "Mishima", "KAZ", "Kazumi", 0, S::Added, 3, true},
                        {"Lucky", "Chloe", "CHL", "Chloe", 0, S::Added, 4, false},
                        {"Claudio", "Serafino", "CLA", "Claudio", 0, S::Update, 2, false},
                        {"Akuma", "", "AKU", "Akuma", 0, S::Newer, 2, true},
                        {"Gigas", "", "GIG", "Gigas", 0, S::None, 2, false},
                        {"Josie", "Rizal", "JOS", "Josie", 0, S::Added, 3, false},
                        {"Katarina", "Alves", "KAT", "Katarina", 0, S::None, 3, false},
                        {"Master", "Raven", "MRV", "Raven", 0, S::Added, 2, false},
                        {"Shaheen", "", "SHA", "Shaheen", 0, S::None, 2, false},
                        {"Eliza", "", "ELI", "Eliza", 1, S::Added, 2, false},
                        {"Fahkumram", "", "FAH", "Fahkumram", 1, S::Added, 2, false},
                        {"Leroy", "Smith", "LER", "Leroy", 1, S::Update, 2, true},
                        {"Lidia", "Sobieska", "LID", "Lidia", 1, S::NotOwned, 2, false},
                        {"Kunimitsu", "II", "KUN", "Kunimitsu", 1, S::None, 2, false},
                        {"Negan", "", "NEG", "Negan", 1, S::NotOwned, 1, false},
                        {"Geese", "Howard", "GEE", "Geese", 1, S::Added, 2, false},
                        {"Noctis", "", "NOC", "Noctis", 1, S::Added, 2, false},
                        {"Reina", "", "REI", "Reina", 2, S::Added, 3, false},
                        {"Azucena", "", "AZU", "Azucena", 2, S::Added, 3, false},
                        {"Miary", "Zo", "MIA", "Miary", 2, S::Update, 2, false},
                        {"Victor", "Chevalier", "VIC", "Victor", 2, S::None, 2, false},
                        {"Clive", "Rosfield", "CLI", "Clive", 2, S::Added, 1, false},
                        {"Azazel", "", "AZA", "Azazel", 2, S::None, 1, false}};
    std::vector<Fighter> out;
    for (const Row& r : rows) out.push_back({r.first, r.last, r.code, r.short_name, r.group, r.st, r.n, r.o});
    return out;
}

const char* kResolutions[] = {"Automatic", "1280 x 720", "1920 x 1080", "2560 x 1440", "3840 x 2160", "5120 x 2880"};

struct DisplayRow {
    const char *key, *name, *about;
};
const DisplayRow kDisplayRows[] = {
    {"fullscreen", "Fullscreen", "Start the game fullscreen. F11 switches it in the game."},
    {"res", "Resolution", "The size the game draws at; the picture is scaled to the window or the screen."},
    {"interp", "120 FPS",
     "A frame between each two of the game's 60 every second: smoother motion on displays of 100 Hz and more."},
    {"delay", "Input delay", "Two frames between a button press and the game acting on it, as on the Wii U."},
    {"async", "Shaders in the background",
     "The first time something is shown, it may appear a few frames late instead of the game stopping."},
    {"pre", "Prepare shaders before playing",
     "Play first makes ready the shaders the game has used on this PC so far."}};

// ---- the demo -------------------------------------------------------------------------------------------------------

class Demo {
public:
    Demo() : fighters_(fake_fighters()) {
        // (A task's log for the widget gallery.)
        log_.append("ttt2 --install ~/Games/Tekken Tag Tournament 2", LogKind::Command);
        log_.append("Checking the game", LogKind::Status);
        for (int i = 0; i < 40; ++i)
            log_.append("checked content/" + std::string(i % 3 ? "chara/" : "stage/") + std::to_string(4096 + i * 37) +
                        ".bin (" + std::to_string(100 + i * 13) + " KB)");
        log_.append("Compiling the game program", LogKind::Status);
        log_.append("clang++: error: unable to execute command: Killed (a long line that wraps where the log view is "
                    "narrower than it)",
                    LogKind::Error);
    }

    int screen = 0;  // 0 Home, 1 Fighters, 2 Settings, 3 the other widgets (--screen widgets)
    bool quit = false;
    bool dialog = false;  // the Uninstall dialog band over the screen
    float share() const {
        return screen == 1   ? theme::split::kFighters
               : screen == 2 ? theme::split::kSettings
               : screen == 3 ? theme::split::kSetup
                             : theme::split::kHome;
    }

    void declare(Ui& ui, SplitStage& stage, const Window& window) {
        const Vec2 size = ui.frame().size;
        // Top band.
        {
            Box top;
            top.layout = Layout::Row;
            top.align = Align::Center;
            top.w = Size::fixed(size.x);
            top.h = Size::fixed(theme::kTopBand);
            top.pad = {30, 0, 22, 0};
            auto g = ui.open("top", top);
            brand(ui, "brand", "Ultimate", "Launcher");
            const int ups = static_cast<int>(std::count_if(
                fighters_.begin(), fighters_.end(), [](const Fighter& f) { return f.state == TileState::Update; }));
            const Tab tabs[] = {{"tab:home", "Home", ""},
                                {"tab:fighters", "Fighters", ups ? std::to_string(ups) : ""},
                                {"tab:settings", "Settings", ""}};
            tab_bar(ui, "tabs", tabs, screen < 3 ? screen : -1);
            ui.leaf("top/space", Box{.w = Size::grow()}, {}, {});
            TextSpec version{"Launcher 0.8.0", tx::kVersion, c::kFaint};
            version.drop = true;  // (the first thing to go in a narrow window)
            text(ui, "version", version, Box{.margin = {0, 0, 16, 0}, .shrink_order = 3});
            icon_button(ui, "sound",
                        {sound_ ? "stroke:sound-on" : "stroke:sound-off", sound_ ? "Sound on" : "Sound off", sound_},
                        Box{.margin = {0, 0, 10, 0}});
            icon_button(ui, "quit", {"stroke:power", "Quit"});
            caption_buttons(ui, "frame", window.can_minimise(), window.can_toggle_fullscreen(), window.fullscreen(),
                            false, Box{.margin = {10, 0, 0, 0}});
        }
        // The screen's halves.
        const Seam seam = stage.layout_seam(stage.share_now());
        const Rect cr = stage.crimson_area(stage.share_now()), bl = stage.blue_area(stage.share_now());
        Box crimson;
        crimson.seam = seam;
        crimson.scroll = true;
        crimson.margin = {cr.x - 16, cr.y, 0, 0};
        crimson.w = Size::fixed(cr.w + 16 + 22);
        crimson.h = Size::fixed(std::max(60.f, cr.h + 14));
        crimson.pad = {16, 0, 22, 8};
        Box blue;
        blue.seam = seam;
        blue.scroll = true;
        blue.margin = {bl.x - 16, bl.y, 0, 0};
        blue.w = Size::fixed(bl.w + 16 + 16);
        blue.h = Size::fixed(std::max(60.f, bl.h + 14));
        blue.pad = {16, 0, 16, 8};
        blue.mirror = true;  // (FEEDBACK F2: the blue half is right-aligned)
        if (screen == 0) home(ui, crimson, blue);
        else if (screen == 1) fighters(ui, crimson, blue);
        else if (screen == 2) settings(ui, crimson, blue);
        else gallery(ui, crimson, blue);
        if (dialog) uninstall_dialog(ui);
        // Bottom band.
        {
            Box bottom;
            bottom.layout = Layout::Row;
            bottom.align = Align::Center;
            bottom.w = Size::fixed(size.x);
            bottom.h = Size::fixed(theme::kBottomBand);
            bottom.margin = {0, size.y - theme::kBottomBand, 0, 0};
            bottom.pad = {34, 0, 26, 0};
            auto g = ui.open("bottom", bottom);
            std::vector<Hint> hints;
            hints.push_back({Prompt::Move, "Move"});
            if (dialog) {
                hints.push_back({Prompt::Accept, ui.focused() == "dlg-ok"       ? "Uninstall"
                                                 : ui.focused() == "dlg-cancel" ? "Cancel"
                                                                                : "Tick"});
                hint_bar(ui, "hints", hints);
                return;
            }
            if (screen == 2) hints.push_back({Prompt::Change, "Change"});
            hints.push_back({Prompt::Accept, screen == 0 ? "Play" : screen == 1 ? "Options" : "Switch"});
            if (screen == 1) hints.push_back({Prompt::Context1, "Outfits"});
            if (screen == 2) hints.push_back({Prompt::Sections, "Section"});
            if (screen != 0) hints.push_back({Prompt::Back, "Home"});
            hints.push_back({Prompt::Tabs, "Tabs"});
            hint_bar(ui, "hints", hints);
        }
    }

    // Events: returns +-1 when the screen changed (wipe direction).
    int handle(Ui& ui, const std::vector<Event>& events, Window& window) {
        int switched = 0;
        for (const Event& e : events) {
            auto go = [&](int to) {
                if (to == screen) return;
                saved_focus_[screen] = ui.focused();
                switched = to > screen ? 1 : -1;
                screen = to;
                const char* def[] = {"play", "f:0", "set:fullscreen"};
                ui.focus(saved_focus_.count(to) ? saved_focus_[to] : def[to], true);
            };
            switch (e.kind) {
            case EventKind::TabNext: if (!dialog) go((screen + 1) % 3); break;
            case EventKind::TabPrev: if (!dialog) go((screen + 2) % 3); break;
            case EventKind::Back:
                if (dialog) dialog = false;
                else if (screen != 0) go(0);
                break;
            case EventKind::ClickOutside: dialog = false; break;
            case EventKind::SectionNext: if (screen == 2) section_ = (section_ + 1) % 3; break;
            case EventKind::SectionPrev: if (screen == 2) section_ = (section_ + 2) % 3; break;
            case EventKind::Fullscreen: window.toggle_fullscreen(); break;
            case EventKind::FocusMoved: last_dy_ = 0; break;
            case EventKind::Change:
                if (e.id.rfind("set:", 0) == 0) change_setting(e.id.substr(4), e.delta);
                break;
            case EventKind::Activate:
                if (e.id == "tab:home") go(0);
                else if (e.id == "tab:fighters" || e.id == "fighters") go(1);
                else if (e.id == "tab:settings" || e.id == "settings") go(2);
                else if (e.id == "sound") sound_ = !sound_;
                else if (e.id == "quit" || e.id == "frame/close") quit = true;
                else if (e.id == "frame/min") window.minimise();
                else if (e.id == "frame/full") window.toggle_fullscreen();
                else if (e.id.rfind("set:", 0) == 0) change_setting(e.id.substr(4), 1);
                else if (e.id.rfind("sec:", 0) == 0) section_ = std::stoi(e.id.substr(4));
                else if (e.id == "oall") outfits_all_ = !outfits_all_;
                else if (e.id == "uninstall") dialog = true;
                else if (e.id == "dlg-cancel" || e.id == "dlg-ok") dialog = false;
                else if (e.id == "opt:saves") del_saves_ = !del_saves_;
                else if (e.id == "opt:chars") del_chars_ = !del_chars_;
                else if (e.id == "copy-log") copy_text(log_.text());
                break;
            default: break;
            }
        }
        return switched;
    }
    void note_move(int dy) { last_dy_ = dy; }

private:
    void change_setting(const std::string& key, int delta) {
        if (key == "res") {
            res_ = std::clamp(res_ + delta, 0, 5);
        } else {
            for (int i = 0; i < 6; ++i)
                if (key == kDisplayRows[i].key) display_[i] = delta > 0;
        }
        slide_ = delta;
    }

    static Box fit(Box b, SeamFit f) {
        b.fit = f;
        return b;
    }

    // ---- Home
    void home(Ui& ui, const Box& crimson, const Box& blue) {
        {
            auto g = ui.open("home/crimson", crimson);
            section_label(ui, "home/menu-label", "Menu", Half::Crimson, {},
                          fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
            Focus f;
            f.is_default = true;
            f.group = -1;
            slab(ui, "play", {"Play", "Tekken Tag", "Tournament 2"}, f,
                 fit(Box{.margin = {12, 0, 0, 18}}, SeamFit::CrimsonSkewed));
            auto rows = ui.open("home/rows", Box{.gap = 10});
            Focus r;
            r.group = -1;
            const int added = static_cast<int>(std::count_if(fighters_.begin(), fighters_.end(), [](const Fighter& x) {
                return x.state == TileState::Added || x.state == TileState::Update || x.state == TileState::Newer;
            }));
            menu_row(ui, "fighters",
                     {"stroke:users", "Fighters", std::to_string(added) + " of " + std::to_string(fighters_.size())}, r,
                     fit({}, SeamFit::CrimsonSkewed));
            menu_row(ui, "settings", {"stroke:gear", "Settings"}, r, fit({}, SeamFit::CrimsonSkewed));
            menu_row(ui, "folder", {"stroke:folder", "Open the game folder"}, r, fit({}, SeamFit::CrimsonSkewed));
            MenuRowSpec un{"stroke:trash", "Uninstall"};
            un.danger = true;
            menu_row(ui, "uninstall", un, r, fit({}, SeamFit::CrimsonSkewed));
        }
        auto g = ui.open("home/blue", blue);
        section_label(ui, "home/game-label", "The game", Half::Blue, {}, fit({}, SeamFit::BlueRect));
        {
            auto k = ui.open("home/kick", fit(Box{.layout = Layout::Row,
                                                  .h = Size::fixed(26),
                                                  .margin = {0, 0, 0, 10},
                                                  .gap = 12,
                                                  .align = Align::Center},
                                              SeamFit::BlueRect));
            pill(ui, "home/installed", "Installed", Tone::Ok);
            text(ui, "home/kv", TextSpec{"Game 0.8.0 · built on this PC", tx::kKick, c::kBlueDim});
        }
        text(ui, "home/t1", TextSpec{.text = "Tekken Tag", .style = tx::kTitleLine, .chroma = 4, .autofit_min = 30},
             fit({}, SeamFit::BlueRect));
        text(ui, "home/t2", TextSpec{.text = "Tournament 2", .style = tx::kTitleLine, .chroma = 4, .autofit_min = 30},
             fit({}, SeamFit::BlueRect));
        edition(ui, "home/edition", fit(Box{.margin = {4, 12, 0, 16}}, SeamFit::BlueSkewed));
        const int added = 15;
        const Fact facts_list[] = {
            {"Version", {{"0.8.0 (1cab8c6)", rgb(0xdbe3f1)}}},
            {"Folder", {{"~/Games/Tekken Tag Tournament 2", rgb(0xdbe3f1)}}},
            {"Fighters",
             {{std::to_string(added) + " of 23 added · ", rgb(0xdbe3f1)}, {"3 to update", c::kWarn}},
             false}};
        facts(ui, "home/facts", facts_list, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
        const std::string key = ui.focused().empty() ? "play" : ui.focused();
        readout_[0].show(key, last_dy_, ui.now());
        readout_[0].build(ui, "home/ro", Box{}, [&](const std::string& k) {
            static const std::map<std::string, std::pair<std::string, std::string>> kExplain = {
                {"play",
                 {"Play", "Starts Tekken Tag Tournament 2 with the Display settings and keys as they are now."}},
                {"fighters", {"Fighters", "Add Tekken 7 and Tekken 8 characters to the game from your own copies."}},
                {"settings", {"Settings", "Display, keyboard and the launcher's own settings."}},
                {"folder", {"Open the game folder", "Shows the folder the game is installed in."}},
                {"uninstall",
                 {"Uninstall", "Removes the game program; your saves and added characters stay (it asks first)."}}};
            auto it = kExplain.find(k);
            if (it == kExplain.end()) return;
            describe_panel(ui, "home/xpl", it->second.first, it->second.second, fit({}, SeamFit::BlueSkewed));
        });
    }

    static void edition(Ui& ui, const std::string& id, const Box& box) {
        TextEngine& te = ui.text();
        Box b = box;
        b.h = Size::fixed(34);
        b.hug = true;
        ui.leaf(
            id, b, [&te](float) { return Vec2{te.width(tx::kEdition, "Ultimate Edition") + 44, 34}; },
            [](PaintContext& ctx) {
                const Rect r = ctx.rect;
                surface(ctx.canvas, r,
                        Gradient::css(r, 90, {{0, rgb(0xe8173f)}, {.5f, rgb(0x7c1a6a)}, {1, rgb(0x1f5fe8)}}),
                        rgba(255, 255, 255, .35f));
                ctx.text.draw(ctx.canvas, tx::kEdition, "Ultimate Edition",
                              {r.x + 20, r.y + (r.h - ctx.text.line_height(tx::kEdition)) / 2}, rgb(0xffffff));
            });
    }

    // ---- Fighters
    void fighters(Ui& ui, const Box& crimson, const Box& blue) {
        {
            auto g = ui.open("fighters/crimson", crimson);
            const char* titles[] = {"Tekken 7", "Tekken 7 DLC", "Tekken 8"};
            for (int gi = 0; gi < 3; ++gi) {
                auto gg = ui.open("grp" + std::to_string(gi), Box{.margin = {0, 0, 0, 14}});
                int n = 0, added = 0, upd = 0;
                for (const Fighter& f : fighters_)
                    if (f.group == gi) {
                        ++n;
                        added +=
                            f.state == TileState::Added || f.state == TileState::Update || f.state == TileState::Newer;
                        upd += f.state == TileState::Update;
                    }
                GroupHeaderSpec h;
                h.title = titles[gi];
                h.count = std::to_string(added) + " of " + std::to_string(n) + " added";
                if (gi == 1) h.sub = "6 of 8 owned", h.sub_tone = Tone::Ok;
                else if (upd) h.sub = std::to_string(upd) + " to update", h.sub_tone = Tone::Warn;
                const std::string gid = gi == 0 ? "t7" : gi == 1 ? "dlc" : "t8";
                h.buttons = {{"gadd:" + gid, gi == 1 ? "Add All Owned" : "Add All"},
                             {"gupd:" + gid, "Update All"},
                             {"grem:" + gid, "Remove All"}};
                group_header(ui, "grp" + std::to_string(gi) + "/h", h,
                             fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::CrimsonRect));
                auto tiles =
                    ui.open("grp" + std::to_string(gi) + "/tiles",
                            fit(Box{.layout = Layout::Row, .pad = {12, 0, 0, 0}, .gap = 8, .line_gap = 8, .wrap = true},
                                SeamFit::CrimsonRect));
                for (std::size_t i = 0; i < fighters_.size(); ++i) {
                    const Fighter& f = fighters_[i];
                    if (f.group != gi) continue;
                    TileSpec t;
                    t.code = f.code;
                    t.name = f.short_name;
                    t.tone = gi == 0 ? TileTone::Red : gi == 1 ? TileTone::Pink : TileTone::Orange;
                    t.state = f.state;
                    if (f.with_outfits && f.state != TileState::None && f.state != TileState::NotOwned)
                        t.tag = "Outfits";
                    Focus fo;
                    fo.group = -1;
                    fo.is_default = i == 0;
                    fighter_tile(ui, "f:" + std::to_string(i), t, fo);
                }
            }
            MenuRowSpec o;
            o.title = "Outfits for every character";
            o.value = outfits_all_ ? "All" : "3 of 21";
            o.check = outfits_all_ ? 1 : 2;
            o.compact = true;
            Focus fo;
            fo.group = -1;
            menu_row(ui, "oall", o, fo, fit({}, SeamFit::CrimsonSkewed));
        }
        auto g = ui.open("fighters/blue", blue);
        std::string key = ui.focused();
        if (key.rfind("f:", 0) != 0) key = last_fighter_;
        else last_fighter_ = key;
        readout_[1].show(key, last_dy_, ui.now());
        readout_[1].build(ui, "fighters/ro", Box{}, [&](const std::string& k) {
            if (k.rfind("f:", 0) != 0) return;
            const int i = std::stoi(k.substr(2));
            const Fighter& f = fighters_[static_cast<std::size_t>(i)];
            const Fighter& p = fighters_[static_cast<std::size_t>(i == 17 ? 18 : 17)];
            section_label(ui, "fro/label", "Fighter", Half::Blue,
                          std::to_string(i + 1) + "/" + std::to_string(fighters_.size()), fit({}, SeamFit::BlueRect));
            {
                auto r =
                    ui.open("fro/stl",
                            fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 10}, .gap = 12, .align = Align::Center},
                                SeamFit::BlueRect));
                pill(ui, "fro/game",
                     f.group == 2   ? "Tekken 8"
                     : f.group == 1 ? "Tekken 7 · DLC"
                                    : "Tekken 7",
                     f.group == 2 ? Tone::Blue : Tone::Red);
                text(ui, "fro/own",
                     TextSpec{f.group == 1   ? "Steam: owned"
                              : f.group == 2 ? "Tekken 8 found"
                                             : "Tekken 7 found",
                              theme::TextStyle{theme::Font::BodySemiBold, 13.5f, 0, false, 1}, c::kBlueDim});
            }
            text(ui, "fro/first", TextSpec{.text = f.first, .style = tx::kFighterName, .chroma = 4, .autofit_min = 34},
                 fit({}, SeamFit::BlueRect));
            text(ui, "fro/last",
                 TextSpec{.text = f.last.empty() ? " " : f.last,
                          .style = tx::kLastName,
                          .color = rgba(255, 255, 255, .78f),
                          .outline = 1.2f},
                 fit(Box{.h = Size::fixed(30), .margin = {4, 4, 0, 14}}, SeamFit::BlueRect));
            // (No "P1 TAG P2" preview: the blue side shows only the focused fighter, FEEDBACK F3.)
            (void)p;
            {
                auto r =
                    ui.open("fro/st2", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                const bool in = f.state == TileState::Added;
                pill(ui, "fro/state",
                     in                               ? "Added"
                     : f.state == TileState::Update   ? "Update ready"
                     : f.state == TileState::NotOwned ? "Not owned"
                                                      : "Not added",
                     in                             ? Tone::Ok
                     : f.state == TileState::Update ? Tone::Warn
                                                    : Tone::Neutral);
            }
            text(ui, "fro/why",
                 TextSpec{.text = "In the game: on the select screen next time it starts.",
                          .style = tx::kPara,
                          .color = c::kBlueDim,
                          .wrap = true},
                 fit({}, SeamFit::BlueRect));
            text(ui, "fro/out",
                 TextSpec{.text = "Their pack has their outfits: untick, then Update, to remove them.",
                          .style = tx::kParaSmall,
                          .color = c::kBlueFaint,
                          .wrap = true},
                 fit(Box{.margin = {0, 6, 0, 0}}, SeamFit::BlueRect));
            auto b = ui.open("fro/btns",
                             fit(Box{.layout = Layout::Row, .margin = {0, 14, 0, 0}, .gap = 12}, SeamFit::BlueRect));
            Focus bf;
            bf.group = 1;
            bf.left = k;
            ButtonSpec outfits;
            outfits.label = "Outfits";
            outfits.size = ButtonSize::Small;
            outfits.check = f.with_outfits;
            button(ui, "ro-out", outfits, bf);
            ButtonSpec rem;
            rem.label = "Remove";
            rem.kind = ButtonKind::Danger;
            rem.size = ButtonSize::Small;
            button(ui, "ro-rem", rem, bf);
        });
    }

    static void pair(Ui& ui, const std::string& id, const Fighter& p1, const Fighter& p2, const Box& box) {
        // 328 x 118 at most; narrower in a narrow window, everything scaled with it.
        Box b = box;
        b.hug = true;
        ui.leaf(id, b, [](float max_w) { const float w = std::min(328.f, max_w); return Vec2{w, 118 * w / 328}; },
                [p1, p2](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const float k = ctx.rect.w / 328;
            const Rect r = ctx.rect;
            auto sz = [k](theme::TextStyle st) { st.size *= k; return st; };
            auto slot = [&](const Rect& s, const Fighter& f, bool blue, const char* label) {
                const Gradient g =
                    blue ? Gradient::css(
                               s, 165,
                               {{0, rgba(45, 128, 255, .62f)}, {.7f, rgba(8, 26, 80, .9f)}, {1, rgba(8, 26, 80, .9f)}})
                         : Gradient::css(
                               s, 165,
                               {{0, rgba(255, 42, 85, .5f)}, {.7f, rgba(70, 6, 22, .9f)}, {1, rgba(70, 6, 22, .9f)}});
                surface(cv, s, g, blue ? rgba(160, 205, 255, .75f) : rgba(255, 255, 255, .22f));
                const theme::TextStyle kCode = sz({theme::Font::DisplayBlackItalic, 58, -.01f, true, 1});
                const theme::TextStyle kSmall = sz({theme::Font::DisplayExtraBoldItalic, 12, .22f, false, 1});
                const theme::TextStyle kName = sz({theme::Font::DisplayBoldItalic, 12, .1f, true, 1});
                const float cw = ctx.text.width(kCode, f.code);
                ctx.text.draw(cv, kCode, f.code, {s.center().x - cw / 2, s.y + 22 * k}, rgba(255, 255, 255, .95f));
                ctx.text.draw(cv, kSmall, label, {s.x + 16 * k, s.y + 8 * k}, rgba(255, 255, 255, .8f));
                const float nw = ctx.text.width(kName, f.short_name);
                ctx.text.draw(cv, kName, f.short_name, {s.center().x - nw / 2, s.bottom() - 22 * k}, rgb(0xffffff));
            };
            slot({r.x, r.y, 142 * k, r.h}, p1, false, "P1");
            slot({r.x + 186 * k, r.y, 142 * k, r.h}, p2, true, "P2");
            const Rect tag{r.x + 141 * k, r.y + 44 * k, 48 * k, 30 * k};
            cv.fill(skewed(tag.outset(3), theme::kSeamTan), rgb(0x07080d));
            cv.glow(skewed(tag, theme::kSeamTan), 18, rgba(255, 255, 255, .35f));
            cv.fill(skewed(tag, theme::kSeamTan), rgb(0xffffff));
            const theme::TextStyle mark = sz(tx::kTagMark);
            const float tw = ctx.text.width(mark, "TAG");
            ctx.text.draw(cv, mark, "TAG", {tag.center().x - tw / 2, tag.y + (tag.h - ctx.text.line_height(mark)) / 2},
                          rgb(0x07080d));
        });
    }

    // ---- Settings
    void settings(Ui& ui, const Box& crimson, const Box& blue) {
        {
            auto g = ui.open("settings/crimson", crimson);
            const Section secs[] = {{"sec:0", "Display"}, {"sec:1", "Keyboard"}, {"sec:2", "Launcher"}};
            section_tabs(ui, "secs", secs, section_);
            auto rows = ui.open("settings/rows", Box{.gap = 8});
            for (int i = 0; i < 6; ++i) {
                const DisplayRow& d = kDisplayRows[i];
                SettingRowSpec s;
                s.title = d.name;
                const bool is_res = std::string(d.key) == "res";
                s.value = is_res ? kResolutions[res_] : display_[i] ? "On" : "Off";
                s.value_on = !is_res && display_[i];
                s.slide = slide_;
                Focus f;
                f.group = -1;
                f.is_default = i == 0;
                setting_row(ui, std::string("set:") + d.key, s, f, fit({}, SeamFit::CrimsonSkewed));
            }
        }
        auto g = ui.open("settings/blue", blue);
        std::string key = ui.focused();
        if (key.rfind("set:", 0) != 0) key = "set:fullscreen";
        readout_[2].show(key, last_dy_, ui.now());
        readout_[2].build(ui, "settings/ro", Box{}, [&](const std::string& k) {
            int i = 0;
            for (int j = 0; j < 6; ++j)
                if (k.substr(4) == kDisplayRows[j].key) i = j;
            const DisplayRow& d = kDisplayRows[i];
            const bool is_res = i == 1;
            const std::string value = is_res ? kResolutions[res_] : display_[i] ? "On" : "Off";
            section_label(ui, "sro/label", "Display", Half::Blue, std::to_string(i + 1) + "/6",
                          fit({}, SeamFit::BlueRect));
            {
                auto r =
                    ui.open("sro/stl", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
                pill(ui, "sro/now", "Now: " + value, !is_res && display_[i] ? Tone::Blue : Tone::Neutral);
            }
            text(ui, "sro/big",
                 TextSpec{.text = d.name,
                          .style = theme::TextStyle{tx::kBig.font, 44, tx::kBig.tracking, true, .92f},
                          .chroma = 3},
                 fit({}, SeamFit::BlueRect));
            text(ui, "sro/about", TextSpec{.text = d.about, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 12, 0, 10}}, SeamFit::BlueRect));
            std::vector<std::string> opts;
            if (is_res) opts.assign(std::begin(kResolutions), std::end(kResolutions));
            else opts = {"Off", "On"};
            chips(ui, "sro/chips", opts, is_res ? res_ : display_[i] ? 1 : 0, fit({}, SeamFit::BlueRect));
            diagram(ui, "sro/diag", display_[0], fit(Box{.margin = {0, 10, 0, 4}}, SeamFit::BlueRect));
            text(ui, "sro/hint",
                 TextSpec{.text = "The game uses it when it starts. Left and right change it on the row.",
                          .style = tx::kParaSmall,
                          .color = c::kBlueFaint,
                          .wrap = true},
                 fit(Box{.margin = {0, 6, 0, 0}}, SeamFit::BlueRect));
        });
    }

    // ---- the other widgets (no screen of the mock shows them all)
    void gallery(Ui& ui, const Box& crimson, const Box& blue) {
        {
            auto g = ui.open("kit/crimson", crimson);
            section_label(ui, "kit/keys-label", "Keys", Half::Crimson, {}, fit({}, SeamFit::CrimsonRect));
            {
                auto k = ui.open("kit/keys", Box{.margin = {0, 0, 0, 14}, .gap = 6});
                const KeyRowSpec keys[] = {{"icons/ttt2-input-dpad_up.svg", "Up", "W"},
                                           {"icons/ttt2-input-face_left.svg", "Punch (Left)", "J", true},
                                           {"icons/ttt2-input-face_bottom.svg", "Kick (Right)", "L", false, true, 1e9}};
                for (int i = 0; i < 3; ++i) {
                    Focus f;
                    f.group = -1;
                    f.is_default = i == 0;
                    key_row(ui, "key:" + std::to_string(i), keys[i], f, fit({}, SeamFit::CrimsonSkewed));
                }
            }
            section_label(ui, "kit/steps-label", "Steps", Half::Crimson, {}, fit({}, SeamFit::CrimsonRect));
            {
                auto s = ui.open("kit/steps", Box{.margin = {0, 0, 0, 14}, .gap = 6});
                const StepRowSpec steps[] = {{"Checking", "16.2 GB", 1, StepState::Done, 1},
                                             {"Copying", "7.9 / 16.2 GB", .49f, StepState::Current, 2},
                                             {"Compiling", "", 0, StepState::Pending, 3},
                                             {"Finishing", "", 0, StepState::Failed, 4}};
                for (int i = 0; i < 4; ++i)
                    step_row(ui, "step:" + std::to_string(i), steps[i], fit({}, SeamFit::CrimsonSkewed));
            }
            section_label(ui, "kit/files-label", "Files", Half::Crimson, {}, fit({}, SeamFit::CrimsonRect));
            const FileRowSpec files[] = {
                {"stroke:up", ".. (up to Games)", "", Tone::Neutral},
                {"stroke:disc", "Tekken Tag Tournament 2 [EUR] (update 16).wua", "6.9 GB", Tone::Ok},
                {"stroke:file", "notes.txt", "2 KB", Tone::Dim}};
            for (int i = 0; i < 3; ++i) {
                Focus f;
                f.group = -1;
                file_row(ui, "file:" + std::to_string(i), files[i], f,
                         fit(Box{.margin = {0, 0, 0, 6}}, SeamFit::CrimsonSkewed));
            }
        }
        auto g = ui.open("kit/blue", blue);
        section_label(ui, "kit/task-label", "Installing", Half::Blue, "49%", fit({}, SeamFit::BlueRect));
        progress_bar(ui, "kit/progress", .49f, Tone::Blue, fit({}, SeamFit::BlueRect));
        {
            auto r = ui.open(
                "kit/pills",
                fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 12}, .gap = 10, .wrap = true}, SeamFit::BlueRect));
            pill(ui, "kit/p-ok", "Ready", Tone::Ok, true);
            pill(ui, "kit/p-warn", "Update", Tone::Warn);
            pill(ui, "kit/p-bad", "Failed", Tone::Bad);
            pill(ui, "kit/p-blue", "Running", Tone::Blue, true);
            pill(ui, "kit/p-n", "Not added");
        }
        log_view(ui, "kit/log", log_, fit(Box{.h = Size::fixed(176), .margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
        note(ui, "kit/note", Tone::Warn, "The game is from an older Ultimate Launcher: update it to play.",
             fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect), "stroke:warn");
        auto b = ui.open("kit/buttons", fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
        Focus bf;
        bf.group = 1;
        ButtonSpec copy;
        copy.label = "Copy the log";
        copy.kind = ButtonKind::Blue;
        copy.size = ButtonSize::Small;
        button(ui, "copy-log", copy, bf);
        ButtonSpec stop;
        stop.label = "Stop";
        stop.kind = ButtonKind::Danger;
        stop.size = ButtonSize::Small;
        stop.prompt = Prompt::Back;
        button(ui, "stop", stop, bf);
        ButtonSpec off;
        off.label = "Not now";
        off.size = ButtonSize::Small;
        off.disabled = true;
        button(ui, "later", off, bf);
    }

    // ---- the Uninstall dialog (the mock's uninstall.png)
    void uninstall_dialog(Ui& ui) {
        const Vec2 size = ui.frame().size;
        const float yc = (theme::kTopBand + size.y - theme::kBottomBand) / 2, height = 334;
        const BandLayout L = band_layout(size, std::round(yc - height / 2), height);
        auto g = dialog_band(ui, "dlg", L);
        {
            Box c = L.crimson;
            c.pad = {0, 0, 0, 0};
            auto cg = ui.open("dlg/crimson", c);
            section_label(ui, "dlg/label", "Uninstall", Half::Crimson, {}, fit({}, SeamFit::CrimsonRect));
            text(ui, "dlg/title",
                 TextSpec{.text = "Uninstall Tekken Tag Tournament 2?", .style = tx::kDialogTitle, .wrap = true},
                 fit(Box{.margin = {0, 0, 0, 14}}, SeamFit::CrimsonRect));
            Focus f;
            option_row(ui, "opt:saves", {"Also delete saves", del_saves_}, f, fit({}, SeamFit::CrimsonSkewed));
            option_row(ui, "opt:chars",
                       {"Also delete added characters and what was saved from Tekken 7 and Tekken 8", del_chars_}, f,
                       fit({}, SeamFit::CrimsonSkewed));
            auto bg = ui.open("dlg/btns", fit(Box{.layout = Layout::Row, .margin = {0, 14 - 8, 0, 0}, .gap = 12},
                                              SeamFit::CrimsonRect));
            ButtonSpec cancel;
            cancel.label = "Cancel";
            cancel.prompt = Prompt::Back;
            cancel.half = Half::Crimson;
            Focus cf;
            cf.is_default = true;
            button(ui, "dlg-cancel", cancel, cf);
            ButtonSpec ok;
            ok.label = "Uninstall";
            ok.kind = ButtonKind::Danger;
            button(ui, "dlg-ok", ok);
        }
        auto bg = ui.open("dlg/blue", L.blue);
        section_label(ui, "dlg/what-label", "What happens", Half::Blue, {}, fit({}, SeamFit::BlueRect));
        const WhatLine what[] = {
            {"Deleted",
             WhatTone::Removed,
             {{"The game, its program and its menu entry, from"}, {" ~/Games/Tekken Tag Tournament 2", true}}},
            {"Stays", WhatTone::Kept, {{"Anything else in that folder."}}},
            {"Saves",
             del_saves_ ? WhatTone::Removed : WhatTone::Kept,
             {{del_saves_ ? "Deleted too:" : "Kept:"}, {" ~/.local/share/ttt2/save", true}}},
            {"Fighters",
             del_chars_ ? WhatTone::Removed : WhatTone::Kept,
             {{del_chars_ ? "The added characters and what was saved from Tekken 7 and Tekken 8 are deleted too."
                          : "The added characters are kept, for when it is installed again."}}}};
        what_list(ui, "dlg/what", what, fit({}, SeamFit::BlueRect));
    }

    static void diagram(Ui& ui, const std::string& id, bool full, const Box& box) {
        Box b = box;
        b.h = Size::fixed(86);
        ui.leaf(id, b, [](float) { return Vec2{340, 86}; }, [full](PaintContext& ctx) {
            Canvas& cv = ctx.canvas;
            const Rect r = ctx.rect;
            const Rect screen{r.x, r.y, 152, 86};
            rounded_rect(cv, screen, 4, rgba(170, 200, 255, .5f));
            rounded_rect(cv, screen.outset(-2), 3, rgb(0x0a1430));
            const Rect win = full ? screen.outset(-6) : Rect{screen.x + 28, screen.y + 18, 94, 52};
            cv.fill_rect(win, rgba(98, 160, 220, .55f));
            constexpr theme::TextStyle kT{theme::Font::DisplayExtraBoldItalic, 14, .12f, true, 1};
            ctx.text.draw(cv, kT, full ? "The whole screen" : "A window", {r.x + 172, r.y + 26}, rgb(0xe9edf5));
            ctx.text.draw(cv, theme::TextStyle{theme::Font::Body, 12.5f, 0, false, 1.3f}, "F11 switches it in the game",
                          {r.x + 172, r.y + 48}, c::kBlueFaint);
        });
    }

    std::vector<Fighter> fighters_;
    Readout readout_[3];
    std::map<int, std::string> saved_focus_;
    std::string last_fighter_ = "f:0";
    int last_dy_ = 0;
    int section_ = 0, res_ = 0, slide_ = 1;
    bool display_[6] = {false, false, true, false, false, false};
    bool sound_ = false, outfits_all_ = false, del_saves_ = false, del_chars_ = false;
    LogView log_;
};

const char* kWatermarks[] = {"Tag", "Roster", "Setup", "Kit"};

// ---- scripted input -------------------------------------------------------------------------------------------------

struct Scripted {
    double time;
    RawEvent event;
};

bool load_script(const std::string& path, std::vector<Scripted>& out, std::string& error) {
    std::ifstream in(path);
    if (!in) {
        error = "cannot read " + path;
        return false;
    }
    std::string line;
    int n = 0;
    while (std::getline(in, line)) {
        ++n;
        if (const auto h = line.find('#'); h != std::string::npos) line.resize(h);
        std::istringstream ls(line);
        double t;
        std::string kind;
        if (!(ls >> t >> kind)) continue;
        RawEvent e;
        e.time = t;
        if (kind == "key") {
            std::string name;
            ls >> name;
            const SDL_Scancode sc = SDL_GetScancodeFromName(name.c_str());
            if (sc == SDL_SCANCODE_UNKNOWN) {
                error = path + ":" + std::to_string(n) + ": unknown key " + name;
                return false;
            }
            e.device = Device::Keyboard;
            e.device_id = 1;
            e.code = sc;
            e.kind = RawEvent::KeyDown;
            out.push_back({t, e});
            e.kind = RawEvent::KeyUp;
            e.time = t + .05;
            out.push_back({t + .05, e});
        } else if (kind == "pad") {
            std::string name;
            ls >> name;
            const SDL_GamepadButton b = SDL_GetGamepadButtonFromString(name.c_str());
            if (b == SDL_GAMEPAD_BUTTON_INVALID) {
                error = path + ":" + std::to_string(n) + ": unknown pad button " + name;
                return false;
            }
            e.device = Device::Gamepad;
            e.device_id = 7;
            e.pad_kind = Glyphs::Xbox;
            e.code = b;
            e.kind = RawEvent::ButtonDown;
            out.push_back({t, e});
            e.kind = RawEvent::ButtonUp;
            e.time = t + .05;
            out.push_back({t + .05, e});
        } else if (kind == "move" || kind == "click") {
            ls >> e.pos.x >> e.pos.y;
            e.device = Device::Mouse;
            e.kind = RawEvent::MouseMove;
            e.delta = {1, 1};
            out.push_back({t, e});
            if (kind == "click") {
                e.kind = RawEvent::MouseDown;
                e.code = 1;
                out.push_back({t, e});
                e.kind = RawEvent::MouseUp;
                e.time = t + .05;
                out.push_back({t + .05, e});
            }
        } else if (kind == "wheel") {
            ls >> e.value;
            e.device = Device::Mouse;
            e.kind = RawEvent::Wheel;
            out.push_back({t, e});
        } else {
            error = path + ":" + std::to_string(n) + ": unknown event " + kind;
            return false;
        }
    }
    std::stable_sort(out.begin(), out.end(), [](const Scripted& a, const Scripted& b) { return a.time < b.time; });
    return true;
}

// ---- comparing with a reference -------------------------------------------------------------------------------------

int compare(const std::vector<std::uint8_t>& rgba, int w, int h, const std::string& ref_path, float tolerance,
            int max_changed) {
    SDL_Surface* loaded = SDL_LoadPNG(ref_path.c_str());
    SDL_Surface* ref = loaded ? SDL_ConvertSurface(loaded, SDL_PIXELFORMAT_RGBA32) : nullptr;
    SDL_DestroySurface(loaded);
    if (!ref) {
        say("launcher_ui_demo: cannot read " + ref_path + ": " + SDL_GetError() + "\n", true);
        return 2;
    }
    // Box-filter the frame down to the reference's size.
    const int rw = ref->w, rh = ref->h;
    double total = 0;
    int big = 0;
    for (int y = 0; y < rh; ++y) {
        const int y0 = y * h / rh, y1 = std::max(y0 + 1, (y + 1) * h / rh);
        const auto* row = static_cast<const std::uint8_t*>(ref->pixels) + static_cast<std::size_t>(y) * ref->pitch;
        for (int x = 0; x < rw; ++x) {
            const int x0 = x * w / rw, x1 = std::max(x0 + 1, (x + 1) * w / rw);
            double acc[3] = {0, 0, 0};
            for (int yy = y0; yy < y1; ++yy)
                for (int xx = x0; xx < x1; ++xx)
                    for (int k = 0; k < 3; ++k) acc[k] += rgba[(static_cast<std::size_t>(yy) * w + xx) * 4 + k];
            const double n = static_cast<double>((y1 - y0) * (x1 - x0));
            double diff = 0;
            for (int k = 0; k < 3; ++k) diff = std::max(diff, std::fabs(acc[k] / n - row[x * 4 + k]));
            total += diff;
            big += diff > 48;
        }
    }
    SDL_DestroySurface(ref);
    const double mean = total / (rw * rh);
    const bool bad = mean > tolerance || big > max_changed;
    char line[300];
    std::snprintf(line, sizeof line,
                  "compare %s: mean difference %.2f (tolerance %.2f), %d of %d pixels differ by > 48 (at most %d)\n",
                  ref_path.c_str(), mean, tolerance, big, rw * rh, max_changed);
    say(line, bad);
    return bad ? 3 : 0;
}

bool write_small(const std::vector<std::uint8_t>& rgba, int w, int h, const std::string& path, int rw) {
    // (Making a reference: the frame box-filtered to rw wide.)
    const int rh = h * rw / w;
    SDL_Surface* s = SDL_CreateSurface(rw, rh, SDL_PIXELFORMAT_RGBA32);
    if (!s) return false;
    for (int y = 0; y < rh; ++y) {
        const int y0 = y * h / rh, y1 = std::max(y0 + 1, (y + 1) * h / rh);
        auto* row = static_cast<std::uint8_t*>(s->pixels) + static_cast<std::size_t>(y) * s->pitch;
        for (int x = 0; x < rw; ++x) {
            const int x0 = x * w / rw, x1 = std::max(x0 + 1, (x + 1) * w / rw);
            double acc[3] = {0, 0, 0};
            for (int yy = y0; yy < y1; ++yy)
                for (int xx = x0; xx < x1; ++xx)
                    for (int k = 0; k < 3; ++k) acc[k] += rgba[(static_cast<std::size_t>(yy) * w + xx) * 4 + k];
            const double n = static_cast<double>((y1 - y0) * (x1 - x0));
            for (int k = 0; k < 3; ++k) row[x * 4 + k] = static_cast<std::uint8_t>(std::lround(acc[k] / n));
            row[x * 4 + 3] = 255;
        }
    }
    const bool ok = SDL_SavePNG(s, path.c_str());
    SDL_DestroySurface(s);
    return ok;
}

int usage(bool error) {
    say("usage: launcher_ui_demo [--screen home|fighters|settings|widgets] [--dialog] [--size WxH] [--scale S]\n"
        "                        [--glyphs kb|xbox|ps|nintendo|generic]\n"
        "                        [--reduced] [--script FILE] [--frames N] [--screenshot FILE] [--compare REF.png]\n"
        "                        [--tolerance T] [--max-changed N] [--write-reference FILE] | --version\n"
        "       launcher_ui_demo --sounds-wav DIR [GAME_FOLDER]\n",
        error);
    return error ? 2 : 0;
}

int run(const std::vector<std::string>& args) {
    if (!args.empty() && args[0] == "--version") {
        say("launcher_ui_demo " TTT2_LAUNCHER_VERSION "\n");
        return 0;
    }
    if (!args.empty() && args[0] == "--sounds-wav") {
        if (args.size() < 2 || args.size() > 3) return usage(true);
        const int n = write_sound_wavs(args[1], args.size() > 2 ? args[2] : std::string());
        say(std::to_string(n) + " sound files written to " + args[1] + "\n", n == 0);
        return n ? 0 : 1;
    }
    std::string screenshot, script_path, compare_path, reference_out;
    int width = 1280, height = 800, frames = 90, screen = 0, max_changed = 200;
    float scale = 0, tolerance = 4;
    bool reduced = false, dialog = false;
    std::optional<Glyphs> glyphs;
    for (std::size_t i = 0; i < args.size(); ++i) {
        const std::string& a = args[i];
        const bool more = i + 1 < args.size();
        if (a == "-h" || a == "--help") return usage(false);
        if (a == "--screenshot" && more) screenshot = args[++i];
        else if (a == "--script" && more) script_path = args[++i];
        else if (a == "--compare" && more) compare_path = args[++i];
        else if (a == "--write-reference" && more) reference_out = args[++i];
        else if (a == "--tolerance" && more) tolerance = std::stof(args[++i]);
        else if (a == "--max-changed" && more) max_changed = std::stoi(args[++i]);
        else if (a == "--frames" && more) frames = std::max(1, std::stoi(args[++i]));
        else if (a == "--scale" && more) scale = std::stof(args[++i]);
        else if (a == "--reduced") reduced = true;
        else if (a == "--dialog") dialog = true;
        else if (a == "--size" && more) {
            if (std::sscanf(args[++i].c_str(), "%dx%d", &width, &height) != 2 || width < 320 || height < 240)
                return usage(true);
        } else if (a == "--screen" && more) {
            const std::string s = args[++i];
            screen = s == "fighters" ? 1 : s == "settings" ? 2 : s == "widgets" ? 3 : s == "home" ? 0 : -1;
            if (screen < 0) return usage(true);
        } else if (a == "--glyphs" && more) {
            const std::string g = args[++i];
            glyphs = g == "xbox" ? Glyphs::Xbox : g == "ps" ? Glyphs::PlayStation : g == "nintendo" ? Glyphs::Nintendo
                     : g == "generic" ? Glyphs::Generic : Glyphs::Keyboard;
        } else {
            say("launcher_ui_demo: unknown option " + a + "\n", true);
            return usage(true);
        }
    }
    const bool test = !screenshot.empty();
    std::vector<Scripted> script;
    if (!script_path.empty()) {
        std::string error;
        if (!load_script(script_path, script, error)) {
            say("launcher_ui_demo: " + error + "\n", true);
            return 2;
        }
    }

    SDL_SetMainReady();
    Window window;
    WindowOptions wo;
    wo.title = "Ultimate Launcher (toolkit demo)";
    wo.app_id = TTT2_LAUNCHER_APP_ID ".Demo";
    wo.version = TTT2_LAUNCHER_VERSION;
    wo.size = {static_cast<float>(width), static_cast<float>(height)};
    wo.min_size = {320, 240};
    wo.offscreen = test;
    wo.forced_scale = scale;
    if (!window.open(wo)) return 1;
    // (Offscreen: the window is as big as asked, in pixels, whatever the scale.)
    if (test && scale > 0) SDL_SetWindowSize(window.sdl(), width, height);
    window.update_scale();

    TextureRegistry textures(window.renderer());
    TextEngine text(textures);
    text.set_system_fallback(!test);
    Icons icons(textures);
    Canvas canvas(window.renderer(), textures);
    Ui ui(text, icons);
    ui.set_highlight(paint_focus_highlight);
    SplitStage stage(textures, 20261124);
    stage.set_frozen(test);
    Wipe wipe(textures);
    InputRouter router;
    if (glyphs) router.force_glyphs(true, *glyphs);
    Demo demo;
    demo.screen = screen;
    demo.dialog = dialog;
    stage.set_target(demo.share(), false, 0);
    stage.snap();

    SystemClock system_clock;
    ManualClock manual_clock;
    const Clock& clock = test ? static_cast<const Clock&>(manual_clock) : system_clock;
    std::size_t next_script = 0;
    int frame = 0;
    bool first = true;
    double last = clock.now();
    while (!demo.quit) {
        const double now = clock.now();
        // Input.
        SDL_Event ev;
        if (!test) {
            const bool busy = ui.animating() || stage.animating() || wipe.active(now) || router.holding() || first;
            double wake = std::min({stage.next_ambient_time(now), router.holding() ? router.next_repeat_time() : 1e18,
                                    window.next_pad_poll()});
            const int wait_ms = busy ? 0 : static_cast<int>(std::clamp((wake - now) * 1000, 0.0, 1000.0));
            if (busy ? SDL_PollEvent(&ev) : SDL_WaitEventTimeout(&ev, wait_ms)) {
                do {
                    if (ev.type == SDL_EVENT_QUIT || ev.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) demo.quit = true;
                    if (ev.type == SDL_EVENT_RENDER_DEVICE_RESET) textures.device_reset();
                    if (ev.type == SDL_EVENT_RENDER_TARGETS_RESET) textures.targets_reset();
                    if (ev.type == SDL_EVENT_WINDOW_FOCUS_LOST) router.release_all();
                    RawEvent raw;
                    if (window.translate(ev, raw, clock.now()) && !raw.filtered) {
                        router.feed(raw);
                        stage.note_input(clock.now());
                    }
                } while (SDL_PollEvent(&ev));
            }
            window.pads_tick(clock.now(), false);
            stage.set_ambient(window.focused() && window.visible());
        } else {
            while (next_script < script.size() && script[next_script].time <= now) {
                router.feed(script[next_script].event);
                stage.note_input(now);
                ++next_script;
            }
            while (SDL_PollEvent(&ev)) {
            }
        }
        router.tick(now);
        // A frame.
        FrameInput in;
        in.size = window.points();
        in.scale = window.scale();
        in.now = now;
        in.actions = router.take_actions();
        in.mouse = router.take_mouse();
        in.reduced_motion = reduced;
        in.glyphs = router.glyphs();
        for (const ActionEvent& a : in.actions)
            if (a.action == Action::Up || a.action == Action::Down) demo.note_move(a.action == Action::Up ? -1 : 1);
        // The seam first (leaning toward the half the focus was on: blue items are in focus group 1), then the
        // screen laid out for the split as it is drawn now (FEEDBACK F1: never for an old or target split).
        {
            const Rect fr = ui.rect(ui.focused());
            const int side = fr.empty() ? 0 : fr.center().x > stage.seam_now().x_at(fr.center().y) ? 1 : -1;
            stage.set_target(demo.share(), false, side);
            if (first) stage.snap();
            stage.update(now, static_cast<float>(std::clamp(now - last, 0.0, .25)), in.size, reduced);
            last = now;
        }
        ui.begin(in);
        demo.declare(ui, stage, window);
        ui.end();
        const std::vector<Event> events = ui.take_events();
        window.set_drag_area({0, 0, in.size.x, theme::kTopBand},
                             {ui.rect("tabs"), ui.rect("sound"), ui.rect("quit"), ui.rect("frame")});

        const Vec2 px = window.pixels();
        canvas.begin(window.scale(), static_cast<int>(px.x), static_cast<int>(px.y));
        SDL_SetRenderDrawColor(window.renderer(), 3, 3, 6, 255);
        SDL_RenderClear(window.renderer());
        wipe.set_area(theme::kTopBand, in.size.y - theme::kBottomBand);
        wipe.begin_frame(canvas, in.size);
        stage.draw(canvas, now);
        watermark(canvas, text, kWatermarks[demo.screen], {in.size.x + 30, in.size.y - theme::kBottomBand + 60});
        ui.paint(canvas);
        wipe.end_frame(canvas, now);
        canvas.flush();
        if (!test) {
            SDL_RenderPresent(window.renderer());
            if (first) window.show();
        }
        first = false;
        // Events after the frame: a switch keeps this frame for the wipe.
        if (const int dir = demo.handle(ui, events, window)) {
            wipe.start(now, dir, reduced);
            stage.note_input(now);
        }
        ++frame;
        if (test) {
            if (frame >= frames) break;
            manual_clock.advance(1.0 / 60);
        }
    }
    if (!test) return 0;
    // Draw the last frame again (the loop presented nothing) and keep it.
    std::vector<std::uint8_t> rgba;
    int w = 0, h = 0;
    if (!window.read_pixels(rgba, w, h)) {
        say(std::string("launcher_ui_demo: cannot read the frame: ") + SDL_GetError() + "\n", true);
        return 1;
    }
    std::string error;
    if (!window.screenshot(screenshot, &error)) {
        say("launcher_ui_demo: " + error + "\n", true);
        return 1;
    }
    say("launcher_ui_demo: " + screenshot + " (" + std::to_string(w) + "x" + std::to_string(h) + ", scale " +
        std::to_string(window.scale()) + ", " + window.renderer_name() + ")\n");
    if (!reference_out.empty() && !write_small(rgba, w, h, reference_out, 320)) {
        say("launcher_ui_demo: cannot write " + reference_out + "\n", true);
        return 1;
    }
    const std::vector<std::string> problems = ui.audit();
    for (const std::string& p : problems) say("launcher_ui_demo: layout: " + p + "\n", true);
    if (!compare_path.empty()) {
        const int c = compare(rgba, w, h, compare_path, tolerance, max_changed);
        if (c != 0) return c;
    }
    return problems.empty() ? 0 : 4;
}

}  // namespace

#ifdef _WIN32
int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    int argc = 0;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    std::vector<std::string> args;
    for (int i = 1; argv && i < argc; ++i) {
        int n = WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, nullptr, 0, nullptr, nullptr);
        std::string arg(n > 0 ? static_cast<std::size_t>(n - 1) : 0, '\0');
        if (n > 1) WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, arg.data(), n, nullptr, nullptr);
        args.push_back(std::move(arg));
    }
    if (argv) LocalFree(argv);
    return run(args);
}
#else
int main(int argc, char** argv) { return run(std::vector<std::string>(argv + 1, argv + argc)); }
#endif
