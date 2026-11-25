// Fighters: Tekken 7's, Tekken 7's DLC and Tekken 8's characters as the model's characters view has them. Crimson:
// the groups (a header with its counts and its actions, disabled ones too: they say why) and their tiles, then
// Outfits for every character. Blue: ONLY the focused fighter (FEEDBACK F3: its game, its name, one state pill,
// its sentence, its outfits, its own progress while a task has it, its actions), or the focused group action's
// group (what the games and Steam say, its warnings, what that action would do), or what outfits are. Accept on a
// tile gives its actions on the blue side the focus and locks the crimson side until Back (FEEDBACK F4).

#include "app.h"

#include "builders.h"
#include "game_art.h"
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

Focus crimson_focus(bool is_default = false, bool disabled = false) {
    Focus f;
    f.group = -1;
    f.is_default = is_default;
    f.disabled = disabled;
    return f;
}

Focus blue_focus(bool disabled = false) {
    Focus f;
    f.group = 1;
    f.disabled = disabled;
    return f;
}

Tone pill_tone(m::PillKind k) {
    switch (k) {
    case m::PillKind::kOk: return Tone::Ok;
    case m::PillKind::kWarn: return Tone::Warn;
    case m::PillKind::kBad: return Tone::Bad;
    default: return Tone::Neutral;
    }
}

const Color kValue = rgb(0xdbe3f1);

// The name a tile shows: the display name's first word, or the next one after a title ("Lucky Chloe", "Master
// Raven" are Chloe and Raven on the select screen).
std::string short_name(const std::string& display) {
    std::vector<std::string> words;
    for (size_t at = 0; at < display.size();) {
        const size_t sp = display.find(' ', at);
        words.push_back(display.substr(at, sp == std::string::npos ? std::string::npos : sp - at));
        if (sp == std::string::npos) break;
        at = sp + 1;
    }
    if (words.empty()) return display;
    if (words.size() > 1 && (words[0] == "Lucky" || words[0] == "Master")) return words[1];
    return words[0];
}

std::string tile_code(const std::string& display) {
    const std::string s = short_name(display);
    if (s == "Raven" && display.starts_with("Master")) return "MRV";
    std::string code;
    for (const char ch : s) {
        if (code.size() == 3) break;
        if (static_cast<unsigned char>(ch) < 0x80 && std::isalpha(static_cast<unsigned char>(ch)))
            code += static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
    }
    return code.empty() ? s.substr(0, 3) : code;
}

std::pair<std::string, std::string> split_name(const std::string& display) {
    const size_t sp = display.find(' ');
    if (sp == std::string::npos) return {display, ""};
    return {display.substr(0, sp), display.substr(sp + 1)};
}

const char* kGroupTitles[] = {"Tekken 7", "Tekken 7 DLC", "Tekken 8"};

namespace art = launcher::game_art;

// The part of a portrait (its texture's 0..1) a w x h box shows: `tall` pixels of the picture from a little above
// the head, the eyes at `eyes` of the height and centred across.
Rect portrait_uv(float w, float h, float tall, float eyes) {
    const float wide = tall * w / h;
    return {(art::kFaceX - wide / 2) / art::kPortraitW, (art::kFaceY - eyes * tall) / art::kPortraitH,
            wide / art::kPortraitW, tall / art::kPortraitH};
}

// The fighter's portrait on the blue side: a card slanted like the seam (its left edge parallel to it), the picture
// fading into its dark ground towards the bottom and at the sides it does not reach.
void portrait_card(Ui& ui, const std::string& id, TextureId texture, float w, float h) {
    ui.leaf(id, fit(Box{.w = Size::fixed(w), .h = Size::fixed(h)}, SeamFit::BlueSkewed), {},
            [texture](PaintContext& ctx) {
                Canvas& cv = ctx.canvas;
                const Rect r = ctx.rect;
                const Quad q = skewed(r, theme::kSeamTan);
                cv.fill(q, Gradient::css(r, 180, {{0, rgba(20, 34, 70, .9f)}, {1, rgba(4, 8, 22, .95f)}}));
                // From the top of the frame's inside down to the hips (the card's height), centred on the face.
                const float tall = std::min(art::kInner.h, 470.f);
                const float s = r.h / tall;
                const float wide = art::kInner.w * s;
                const float face = art::kFaceX - art::kInner.x;   // (in the inside's pixels)
                Rect dst{r.center().x - face * s, r.y, wide, r.h};
                // (Kept inside the frame: the card's middle is all picture.)
                dst.x = std::clamp(dst.x, r.right() - wide, r.x);
                const Rect uv{art::kInner.x / art::kPortraitW, art::kInner.y / art::kPortraitH,
                              art::kInner.w / art::kPortraitW, tall / art::kPortraitH};
                cv.picture(texture, dst, uv, std::span<const Vec2>(q.p, 4), [dst](Vec2 p) {
                    const float u = (p.x - dst.x) / dst.w, v = (p.y - dst.y) / dst.h;
                    const float sides = std::clamp(std::min(u, 1 - u) / .07f, 0.f, 1.f);
                    const float bottom = std::clamp((1 - v) / .22f, 0.f, 1.f);
                    return sides * bottom * bottom;
                }, rgba(255, 255, 255, 1), 10);
                // The blue side's marks: a light top edge, a thin frame.
                cv.fill(shaped_part(r, {r.x, r.y, r.w, 3}, Shape::Skewed, theme::kSeamTan),
                        Gradient::linear({r.x, 0}, {r.right(), 0}, c::kBlue, rgba(45, 128, 255, .2f)));
                cv.stroke(q, 1, rgba(130, 180, 255, .3f));
            });
}

} // namespace

// ---------------------------------------------------------------- what the screen is made of

std::vector<App::FighterGroup> App::fighter_groups() const {
    std::vector<FighterGroup> out;
    const m::CharactersView& cv = view_.characters;
    for (const m::GameGroup& g : cv.games) {
        const bool t8 = g.game == kTekken8;
        FighterGroup base;
        base.key = t8 ? "t8" : "t7";
        base.title = t8 ? kGroupTitles[2] : kGroupTitles[0];
        base.game = g.game;
        base.group = &g;
        for (const m::FighterRow& r : g.rows) base.rows.push_back(&r);
        out.push_back(base);
        if (g.dlc && !g.dlc->rows.empty()) {
            FighterGroup dlc;
            dlc.key = "dlc";
            dlc.title = kGroupTitles[1];
            dlc.game = g.game;
            dlc.group = &g;
            dlc.dlc = true;
            for (const m::FighterRow& r : g.dlc->rows) dlc.rows.push_back(&r);
            out.push_back(dlc);
        }
    }
    return out;
}

const Fighter* App::status_fighter(const std::string& name) const {
    if (!model_->facts().status) return nullptr;
    for (const Fighter& f : model_->facts().status->fighters)
        if (f.name == name) return &f;
    return nullptr;
}

const m::FighterRow* App::fighter_row(const std::string& name) const {
    for (const m::GameGroup& g : view_.characters.games) {
        for (const m::FighterRow& r : g.rows)
            if (r.name == name) return &r;
        if (g.dlc)
            for (const m::FighterRow& r : g.dlc->rows)
                if (r.name == name) return &r;
    }
    return nullptr;
}

// The actions of a fighter's blue side, in the order shown: Add / Update / Add Again (or Remove when that is
// their only one), Outfits, Remove. A DLC character the account does not own gets a dimmed Add saying why
// (FEEDBACK F3: a disabled action is a button with its own label, never a second state pill).
std::vector<m::Action> App::fighter_actions(const m::FighterRow& r) const {
    std::vector<m::Action> out;
    const m::Action* main = nullptr;
    const m::Action* remove = nullptr;
    for (const m::Action& a : r.buttons) {
        if (a.id.starts_with("remove:")) remove = &a;
        else main = &a;
    }
    const bool main_is_remove = main && main->label == "Remove";
    if (main && !main_is_remove) out.push_back(*main);
    if (!main && !remove) {
        m::Action add;
        add.id = "fighter:" + r.name;
        add.label = "Add";
        add.enabled = false;
        add.why = !r.button_note.empty() || r.state_text == "Not owned"
                      ? "Your Steam account does not own their DLC: only owned ones can be added."
                      : "They cannot be added now.";
        add.describe.title = "Add " + r.display;
        add.describe.why = add.why;
        out.push_back(add);
    }
    if (r.outfits) out.push_back(*r.outfits);
    if (main_is_remove) out.push_back(*main);
    if (remove) out.push_back(*remove);
    return out;
}

App::FighterTask App::fighter_task(const std::string& name) const {
    FighterTask t;
    const m::TaskRunner& r = model_->task();
    if (!r.running()) return t;
    const m::TaskSpec& s = r.spec();
    if (s.kind != m::TaskKind::kImport && s.kind != m::TaskKind::kRemove) return t;
    const auto it = std::find(s.names.begin(), s.names.end(), name);
    if (it == s.names.end()) return t;
    t.in = true;
    t.count = static_cast<int>(s.names.size());
    t.index = static_cast<int>(it - s.names.begin()) + 1;
    t.verb = s.kind == m::TaskKind::kRemove ? "Removing" : s.update ? "Updating" : "Adding";
    // The importer's "@step fighter <name> <i> <n>" lines say whose turn it is; "@step shared" comes after them.
    std::string current;
    bool shared = false;
    for (const std::string& l : r.log()) {
        if (l.starts_with("@step fighter ")) {
            const size_t a = 14, b = l.find(' ', a);
            current = l.substr(a, b == std::string::npos ? std::string::npos : b - a);
        } else if (l.starts_with("@step shared")) {
            shared = true;
        }
    }
    int at = 0;
    if (!current.empty()) {
        const auto ci = std::find(s.names.begin(), s.names.end(), current);
        if (ci != s.names.end()) at = static_cast<int>(ci - s.names.begin()) + 1;
    }
    t.state = shared || at > t.index ? 2 : at == t.index ? 1 : 0;
    const double whole = r.progress_state().fraction();
    t.fraction = t.state == 2 ? 1.0
                 : t.state == 0 ? 0.0
                 : whole < 0    ? -1.0
                                : std::clamp(whole * t.count - (t.index - 1), 0.0, 1.0);
    t.detail = r.progress_state().detail();
    return t;
}

// ---------------------------------------------------------------- crimson

void App::fighters(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::CharactersView& cv = view_.characters;
    // Every action of the screen: their whys for refusals, their labels for the prompt bar.
    for (const m::GameGroup& g : cv.games) {
        for (const m::Action& a : g.head) screen_actions_[a.id] = a;
        for (const m::Line& l : g.notes)
            for (const m::Action& a : l.actions) screen_actions_[a.id] = a;
        if (g.dlc) screen_actions_[g.dlc->add_owned.id] = g.dlc->add_owned;
    }
    if (cv.outfits_all) screen_actions_[cv.outfits_all->id] = *cv.outfits_all;
    for (const m::Line& l : cv.outfits_notes)
        for (const m::Action& a : l.actions) screen_actions_[a.id] = a;
    for (const m::Fact& f : cv.facts)
        for (const m::Line& l : f.lines)
            for (const m::Action& a : l.actions) screen_actions_[a.id] = a;
    for (const m::Line& l : cv.lines)
        for (const m::Action& a : l.actions) screen_actions_[a.id] = a;
    if (cv.early) return fighters_early(crimson, blue);

    const std::vector<FighterGroup> groups = fighter_groups();
    for (const FighterGroup& g : groups)
        for (const m::FighterRow* r : g.rows)
            for (const m::Action& a : fighter_actions(*r)) screen_actions_[a.id] = a;
    group_of_button_.clear();
    const m::Fact* missing = nullptr;
    for (const m::Fact& f : cv.facts)
        if (f.name == "Missing") missing = &f;
    {
        auto g = ui.open("fi/crimson", crimson);
        int n = 0;
        for (const m::Line& l : cv.lines) {
            const bool warn = l.icon == m::Icon::kWarning || l.tone == m::Tone::kError;
            note(ui, "fi/line" + std::to_string(n++), warn ? Tone::Warn : Tone::Blue, l.text.empty() ? l.title : l.text,
                 fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::CrimsonRect), warn ? "stroke:warn" : "stroke:info");
        }
        if (missing) {
            MenuRowSpec s{"stroke:warn", "Missing to add characters", ""};
            s.compact = true;
            s.value = missing->lines.empty() ? "" : "See why";
            s.value_tone = Tone::Warn;
            menu_row(ui, "fx:needs", s, crimson_focus(), fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonSkewed));
        }
        bool first_tile = true;
        for (const FighterGroup& fg : groups) {
            auto gg = ui.open("fi/" + fg.key, Box{.margin = {0, 0, 0, 14}});
            int added = 0, update = 0, owned = 0, known = 0;
            for (const m::FighterRow* r : fg.rows) {
                const Fighter* f = status_fighter(r->name);
                if (!f) continue;
                added += f->added();
                update += f->added() && (f->update || m::outfits_changed(model_->facts(), *f));
                const std::optional<bool> o = m::owns(model_->facts(), *f);
                owned += o == true;
                known += o.has_value();
            }
            GroupHeaderSpec h;
            h.title = fg.title;
            h.count = std::to_string(added) + " of " + std::to_string(fg.rows.size()) + " added";
            h.focus_group = -1;
            if (fg.dlc) {
                if (model_->facts().owned.state == m::OwnedState::kChecking) {
                    h.sub = "Asking Steam…";
                    h.sub_tone = Tone::Dim;
                } else if (known > 0) {
                    h.sub = std::to_string(owned) + " of " + std::to_string(fg.rows.size()) + " owned";
                    h.sub_tone = Tone::Ok;
                } else {
                    h.sub = "Ownership not known";
                    h.sub_tone = Tone::Dim;
                }
            } else if (update) {
                h.sub = std::to_string(update) + " to update";
                h.sub_tone = Tone::Warn;
            }
            for (const m::Action& a : group_actions(fg)) {
                h.buttons.push_back({a.id, a.label, !a.enabled});
                group_of_button_[a.id] = fg.key;
                screen_actions_[a.id] = a;
            }
            group_header(ui, "fi/" + fg.key + "/h", h, fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::CrimsonRect));
            auto tiles = ui.open("fi/" + fg.key + "/tiles",
                                 fit(Box{.layout = Layout::Row, .pad = {12, 0, 0, 0}, .gap = 8, .line_gap = 8,
                                         .wrap = true},
                                     SeamFit::CrimsonRect));
            for (const m::FighterRow* r : fg.rows) {
                const Fighter* f = status_fighter(r->name);
                TileSpec t;
                t.code = tile_code(r->display);
                t.name = short_name(r->display);
                t.tone = fg.key == "t8" ? TileTone::Orange : fg.dlc ? TileTone::Pink : TileTone::Red;
                const std::optional<bool> o = f ? m::owns(model_->facts(), *f) : std::nullopt;
                if (!f) t.state = TileState::None;
                else if (f->added() && (f->update || m::outfits_changed(model_->facts(), *f))) t.state = TileState::Update;
                else if (f->installed && (f->outdated || f->newer)) t.state = TileState::Update;
                else if (f->added() && m::newer_on_main(model_->facts(), f->name)) t.state = TileState::Newer;
                else if (f->added()) t.state = TileState::Added;
                else if (o == false) t.state = TileState::NotOwned;
                else if (f->dlc != 0 && !o && model_->facts().owned.state == m::OwnedState::kChecking)
                    t.state = TileState::Checking;
                else t.state = TileState::None;
                if (f && f->outfits > 0 && t.state != TileState::NotOwned &&
                    ((f->added() && f->outfits_added) || m::wants_outfits(model_->facts(), *f)))
                    t.tag = "Outfits";
                t.busy = fighter_task(r->name).in;
                // An added fighter: their portrait in place of the letters.
                if (f && f->installed && t.state != TileState::NotOwned) {
                    t.portrait = portrait_of(f->display);
                    t.portrait_uv = portrait_uv(theme::metric::kTileWidth, theme::metric::kTileHeight, 210, .36f);
                }
                fighter_tile(ui, "tile:" + r->name, t, crimson_focus(first_tile));
                first_tile = false;
            }
        }
        if (cv.outfits_all) {
            const m::Action& a = *cv.outfits_all;
            const auto choices = m::outfit_choices(model_->facts());
            size_t wanted = 0;
            for (const Fighter* f : choices) wanted += m::wants_outfits(model_->facts(), *f);
            MenuRowSpec o;
            o.title = "Outfits for every character";
            o.value = a.checked ? "All" : wanted == 0 ? "None" : std::to_string(wanted) + " of " +
                                                                    std::to_string(choices.size());
            o.check = a.checked ? 1 : a.inconsistent ? 2 : 0;
            o.compact = true;
            o.disabled = !a.enabled;
            menu_row(ui, a.id, o, crimson_focus(false, !a.enabled), fit({}, SeamFit::CrimsonSkewed));
        }
    }
    fighters_blue(blue, groups);
}

// A group's actions as its header shows them: what the model gives (Add All / Add All Owned, Remove All when its
// game is gone, Update All when some are to update), and Update All dimmed when nothing is (it says why).
std::vector<m::Action> App::group_actions(const FighterGroup& fg) const {
    std::vector<m::Action> out;
    const m::GameGroup& g = *fg.group;
    if (fg.dlc) {
        out.push_back(g.dlc->add_owned);
        return out;
    }
    const m::Action* update = nullptr;
    const m::Action* stand_ins = nullptr;
    for (const m::Line& l : g.notes)
        for (const m::Action& a : l.actions) {
            if (a.id.starts_with("update-all")) update = &a;
            if (a.id == "update-stand-ins") stand_ins = &a;
        }
    for (const m::Action& a : g.head)
        if (a.id.starts_with("add-all")) out.push_back(a);
    if (update) {
        m::Action u = *update;
        u.label = "Update All";
        out.push_back(u);
    } else {
        m::Action u;
        u.id = fg.key == "t8" ? "update-all:tekken8" : "update-all";
        u.label = "Update All";
        u.enabled = false;
        u.why = "Every added character is up to date.";
        u.describe.title = u.label;
        u.describe.why = u.why;
        out.push_back(u);
    }
    if (stand_ins) {
        m::Action s = *stand_ins;
        s.label = "Own Moves";
        out.push_back(s);
    }
    for (const m::Action& a : g.head)
        if (a.id.starts_with("remove-all")) out.push_back(a);
    return out;
}

// No list yet (no importer, no Python, still looking, the importer failed): one row says it, blue has the rest.
void App::fighters_early(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    const m::CharactersView& cv = view_.characters;
    const bool looking = !cv.lines.empty() && cv.lines[0].kind == m::Line::Kind::kSpinner;
    std::string copy;
    for (const m::Line& l : cv.lines)
        for (const m::Action& a : l.actions)
            if (a.id.starts_with("copy:")) copy = a.id;
    {
        auto g = ui.open("fi/crimson", crimson);
        section_label(ui, "fi/label", "Fighters", Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        MenuRowSpec s{looking ? "stroke:dots" : "stroke:warn",
                      looking ? "Looking for your games…" : "Fighters cannot be added yet"};
        s.compact = true;
        menu_row(ui, "fx:early", s, crimson_focus(true), fit({}, SeamFit::CrimsonSkewed));
    }
    auto g = ui.open("fi/blue", blue);
    section_label(ui, "fe/label", "Fighters", Half::Blue, {}, fit({}, SeamFit::BlueRect));
    text(ui, "fe/title",
         TextSpec{.text = looking ? "Looking" : "Not yet", .style = tx::kBig, .chroma = 3, .autofit_min = 28},
         fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
    int n = 0;
    for (const m::Line& l : cv.lines) {
        const std::string id = "fe/l" + std::to_string(n++);
        if (l.kind == m::Line::Kind::kCommand) {
            text(ui, id, TextSpec{.text = l.text, .style = tx::kFactValue, .color = rgb(0xe9f1ff), .wrap = true},
                 fit(Box{.pad = {12, 10, 12, 10}, .margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
            continue;
        }
        const bool bad = l.tone == m::Tone::kError;
        text(ui, id,
             TextSpec{.text = l.text, .style = l.small ? tx::kParaSmall : tx::kPara,
                      .color = bad ? c::kBad : c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
    }
    if (!copy.empty()) {
        ButtonSpec b;
        b.label = "Copy";
        b.kind = ButtonKind::Blue;
        b.size = ButtonSize::Small;
        button(ui, copy, b, blue_focus(), fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
    }
}

// ---------------------------------------------------------------- blue

void App::fighters_blue(const Box& blue, const std::vector<FighterGroup>& groups) {
    Ui& ui = *ui_;
    auto g = ui.open("fi/blue", blue);
    const std::string& fo = ui.focused();
    std::string key = fighters_key_;
    if (drilled() && drill_->opener.starts_with("tile:")) key = "f:" + drill_->opener.substr(5);
    else if (drilled() && drill_->opener == "fx:needs") key = "needs";
    else if (fo.starts_with("tile:")) key = "f:" + fo.substr(5);
    else if (group_of_button_.count(fo)) key = "g:" + group_of_button_.at(fo) + ":" + fo;
    else if (fo == "outfits-all") key = "outfits";
    else if (fo == "fx:needs") key = "needs";
    // (Nothing focused yet, or a key from another state: the first fighter.)
    const auto known = [&](const std::string& k) {
        if (k.starts_with("f:")) return fighter_row(k.substr(2)) != nullptr;
        if (k.starts_with("g:")) {
            const size_t colon = k.find(':', 2);
            return colon != std::string::npos && screen_actions_.count(k.substr(colon + 1)) > 0;
        }
        if (k == "outfits") return view_.characters.outfits_all.has_value();
        if (k == "needs") return std::any_of(view_.characters.facts.begin(), view_.characters.facts.end(),
                                              [](const m::Fact& f) { return f.name == "Missing"; });
        return false;
    };
    if (!known(key)) {
        key.clear();
        for (const FighterGroup& fg : groups)
            if (!fg.rows.empty() && key.empty()) key = "f:" + fg.rows[0]->name;
    }
    fighters_key_ = key;
    fighters_ro_.show(key, last_dy_, ui.now());
    fighters_ro_.build(ui, "fi/ro", Box{}, [&](const std::string& k) {
        if (k.starts_with("f:")) fighter_view(k.substr(2));
        else if (k.starts_with("g:")) {
            const size_t colon = k.find(':', 2);
            group_view(k.substr(2, colon - 2), k.substr(colon + 1), groups);
        } else if (k == "outfits") outfits_view();
        else if (k == "needs") needs_view();
    });
}

void App::fighter_view(const std::string& name) {
    Ui& ui = *ui_;
    const m::FighterRow* r = fighter_row(name);
    const Fighter* f = status_fighter(name);
    if (!r || !f) return;
    const m::Facts& facts = model_->facts();
    const ImporterStatus& s = *facts.status;
    int index = 0, total = static_cast<int>(s.fighters.size());
    for (int i = 0; i < total; ++i)
        if (s.fighters[static_cast<size_t>(i)].name == name) index = i + 1;
    section_label(ui, "fv/label", "Fighter", Half::Blue, std::to_string(index) + "/" + std::to_string(total),
                  fit({}, SeamFit::BlueRect));
    const bool t8 = f->of(kTekken8);
    const std::optional<bool> owned = m::owns(facts, *f);
    {
        auto row = ui.open("fv/game", fit(Box{.layout = Layout::Row, .h = Size::fixed(26), .margin = {0, 0, 0, 10},
                                              .gap = 12, .align = Align::Center},
                                          SeamFit::BlueRect));
        pill(ui, "fv/game-pill", t8 ? "Tekken 8" : f->dlc ? "Tekken 7 · DLC" : "Tekken 7", t8 ? Tone::Blue : Tone::Red);
        std::string found;
        if (f->dlc) {
            found = owned == true    ? "Steam: owned"
                    : owned == false ? "Steam: not owned"
                    : facts.owned.state == m::OwnedState::kChecking ? "Steam: asking…"
                                                                     : "Steam: not known";
        } else {
            const bool usable = t8 ? s.tekken8_usable() : s.tekken7_usable();
            const bool present = t8 ? s.tekken8_found : s.tekken7_found;
            found = std::string(t8 ? "Tekken 8" : "Tekken 7") +
                    (usable ? " found" : present ? " cannot be used" : " not installed");
        }
        text(ui, "fv/found", TextSpec{found, tx::kKick, c::kBlueDim}, Box{.shrink_order = 1});
    }
    // An added fighter: their portrait on a card at the seam, the rest of what is said of them right-aligned beside it.
    std::optional<Ui::Guard> card, info;
    // The card leaves the words at least kWords beside it (the seam's slant and the gap taken off too); when even its
    // smallest size cannot, there is none (a small window: the tile shows the portrait).
    constexpr float kWords = 220, kAround = 22 + 70;
    const Rect bl = stage_->blue_area(stage_->share_now());
    const float card_w = std::min(std::clamp(std::round(bl.w * .34f), 112.f, 230.f), std::floor(bl.w - kAround - kWords));
    if (const TextureId pic = f->installed && card_w >= 112 ? portrait_of(f->display) : 0) {
        const float w = card_w;
        const float h = std::min(std::round(w * 1.9f), std::max(160.f, bl.h - 120));
        // (The row fitted at its middle, like the card: the card's slanted edge keeps the seam's distance.)
        card.emplace(ui.open("fv/card", fit(Box{.layout = Layout::Row, .gap = 22, .align = Align::Start},
                                            SeamFit::BlueSkewed)));
        portrait_card(ui, "fv/portrait", pic, w, h);
        info.emplace(ui.open("fv/info", Box{.w = Size::grow()}));
    }
    const auto [first, last] = split_name(r->display);
    text(ui, "fv/first", TextSpec{.text = first, .style = tx::kFighterName, .chroma = 4, .autofit_min = 34},
         fit({}, SeamFit::BlueRect));
    text(ui, "fv/last",
         TextSpec{.text = last.empty() ? " " : last, .style = tx::kLastName, .color = rgba(255, 255, 255, .78f),
                  .outline = 1.2f},
         fit(Box{.h = Size::fixed(30), .margin = {4, 4, 0, 14}}, SeamFit::BlueRect));

    // ONE state pill, then its sentence (FEEDBACK F3).
    const FighterTask task = fighter_task(name);
    std::string state, sentence;
    Tone tone = Tone::Neutral;
    bool live = false;
    if (task.in) {
        state = std::string(task.verb) + "…";
        tone = Tone::Blue;
        live = true;
        sentence = task.state == 2 ? std::string("Their part is done: the rest of the task finishes it.")
                   : task.state == 1 ? std::string("Their pack is being made now.")
                                     : "Waiting for their turn: " + std::to_string(task.index) + " of " +
                                           std::to_string(task.count) + ".";
        if (task.verb == std::string("Removing"))
            sentence = task.state == 2 ? "Removed: the rest of the task finishes it." : "Their pack is being removed.";
    } else if (r->pill) {
        state = r->pill->text;
        tone = pill_tone(r->pill->kind);
        sentence = r->pill->text == "Added" ? "In the game: on the select screen next time it starts."
                                             : r->pill->explain;
    } else if (owned == false) {
        state = "Not owned";
        sentence = "Your Steam account does not own their DLC: only owned ones can be added.";
    } else if (f->dlc && !owned && facts.owned.state == m::OwnedState::kChecking) {
        state = "Checking";
        tone = Tone::Blue;
        live = true;
        sentence = "Asking Steam whether your account owns their DLC…";
    } else {
        state = "Not added";
        const std::vector<m::Action> acts = fighter_actions(*r);
        const m::Action* add = acts.empty() ? nullptr : &acts.front();
        if (add && !add->enabled && !add->why.empty()) sentence = add->why;
        else
            sentence = std::string("Not in the game yet: Add makes their pack from your ") +
                       (t8 ? "Tekken 8" : "Tekken 7") + ". It takes a few minutes.";
    }
    {
        auto row = ui.open("fv/state", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        pill(ui, "fv/state-pill", state, tone, live);
    }
    if (!sentence.empty())
        text(ui, "fv/sentence", TextSpec{.text = sentence, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 0, 0, 6}}, SeamFit::BlueRect));
    if (r->outfits && !task.in) {
        const m::Action& o = *r->outfits;
        std::string words = o.enabled ? o.describe.explain : o.tooltip;
        if (!words.empty()) {
            if (!words.ends_with(".") && !words.ends_with("…") && !words.ends_with(")")) words += ".";
            text(ui, "fv/outfits",
                 TextSpec{.text = words, .style = tx::kParaSmall, .color = c::kBlueFaint, .wrap = true},
                 fit(Box{.margin = {0, 0, 0, 6}}, SeamFit::BlueRect));
        }
    }
    if (task.in) {
        progress_bar(ui, "fv/bar", static_cast<float>(task.fraction), task.state == 2 ? Tone::Ok : Tone::Blue,
                     fit(Box{.margin = {0, 8, 0, 6}}, SeamFit::BlueRect));
        std::string line = (task.state == 2 ? std::string("Done") : task.state == 1 ? std::string("Now") : "Waiting") +
                           " · " + std::to_string(task.index) + " of " + std::to_string(task.count);
        if (task.state == 1 && !task.detail.empty()) line += " · " + task.detail;
        text(ui, "fv/progress", TextSpec{line, tx::kKick, c::kBlueDim}, fit({}, SeamFit::BlueRect));
    }
    // Its actions: right-aligned in the blue half (FEEDBACK F2); disabled ones dimmed, their why is the sentence
    // or comes as a note when Accept is pressed on them.
    const std::vector<m::Action> acts = fighter_actions(*r);
    auto b = ui.open("fv/btns",
                     fit(Box{.layout = Layout::Row, .margin = {0, 14, 0, 0}, .gap = 12, .line_gap = 12, .wrap = true},
                         SeamFit::BlueRect));
    bool first_button = true;
    for (const m::Action& a : acts) {
        ButtonSpec bs;
        bs.label = a.label;
        bs.size = ButtonSize::Small;
        bs.disabled = !a.enabled;
        if (a.kind == m::ActionKind::kCheck) bs.check = a.checked;
        else if (a.label == "Remove") bs.kind = ButtonKind::Danger;
        else bs.kind = ButtonKind::Blue;
        Focus fo = blue_focus(!a.enabled);
        // (Left from the first returns to its tile, unless the crimson side is locked: then Back does.)
        if (first_button && !drilled()) fo.left = "tile:" + name;
        first_button = false;
        button(ui, a.id, bs, fo);
    }
}

void App::group_view(const std::string& group, const std::string& action_id,
                     const std::vector<FighterGroup>& groups) {
    Ui& ui = *ui_;
    const FighterGroup* fg = nullptr;
    for (const FighterGroup& g : groups)
        if (g.key == group) fg = &g;
    if (!fg) return;
    const m::Facts& fa = model_->facts();
    const m::CharactersView& cv = view_.characters;
    int added = 0;
    for (const m::FighterRow* r : fg->rows)
        if (const Fighter* f = status_fighter(r->name)) added += f->added();
    section_label(ui, "gv/label", "Group", Half::Blue, {}, fit({}, SeamFit::BlueRect));
    {
        auto row = ui.open("gv/count", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        pill(ui, "gv/pill", std::to_string(added) + " of " + std::to_string(fg->rows.size()) + " added");
    }
    text(ui, "gv/title", TextSpec{.text = fg->title, .style = tx::kBig, .chroma = 3, .autofit_min = 28},
         fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    // The games and Steam as the importer found them.
    std::vector<Fact> list;
    for (const m::Fact& f : cv.facts) {
        const bool game_fact = f.name == "Tekken 7" || f.name == "Tekken 8";
        if (game_fact && f.name != m::game_name(fg->game)) continue;
        if (f.name == "Missing") continue;
        std::vector<Run> runs;
        for (const m::Line& l : f.lines) {
            if (!l.actions.empty()) continue;
            if (!runs.empty()) runs.push_back({"\n", kValue});
            const Color col = l.tone == m::Tone::kError     ? c::kBad
                              : l.tone == m::Tone::kWarning ? c::kWarn
                              : l.tone == m::Tone::kDim     ? c::kBlueDim
                              : f.name == "Steam" && l.text == "Running" ? c::kOk
                                                                         : kValue;
            runs.push_back({l.text, col});
        }
        list.push_back({f.name, runs, f.name != "Steam" && f.name != "Game"});
    }
    if (fg->dlc && fg->group->dlc) {
        std::vector<Run> runs;
        for (const m::Line& l : fg->group->dlc->notes)
            runs.push_back({l.text, l.tone == m::Tone::kError ? c::kBad : kValue});
        if (!runs.empty()) list.push_back({"DLC", runs, false});
    }
    facts(ui, "gv/facts", list, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
    // Its warnings (older and newer packs, stand-ins, updates).
    int n = 0;
    for (const m::Line& l : fg->group->notes) {
        if (fg->dlc) break;
        const Tone t = l.icon == m::Icon::kWarning ? Tone::Warn : l.icon == m::Icon::kUpdate ? Tone::Warn : Tone::Blue;
        note(ui, "gv/note" + std::to_string(n++), t, l.text, fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect),
             t == Tone::Blue ? "stroke:info" : l.icon == m::Icon::kUpdate ? "stroke:update" : "stroke:warn");
    }
    // What the focused action would do, or why it cannot.
    const auto it = screen_actions_.find(action_id);
    if (it == screen_actions_.end()) return;
    const m::Action& a = it->second;
    std::vector<std::string> names;
    std::string doing;
    if (action_id == "add-all") names = m::base_to_add(fa, kTekken7), doing = "Adds ";
    else if (action_id == "add-all:tekken8") names = m::base_to_add(fa, kTekken8), doing = "Adds ";
    else if (action_id == "add-all-owned") names = m::owned_to_add(fa), doing = "Adds ";
    else if (action_id == "update-all") names = m::to_update(fa, kTekken7), doing = "Updates ";
    else if (action_id == "update-all:tekken8") names = m::to_update(fa, kTekken8), doing = "Updates ";
    else if (action_id == "update-stand-ins") names = m::to_update(fa, kTekken8, true), doing = "Gives their own moves to ";
    else if (action_id.starts_with("remove-all:")) names = m::to_remove_all(fa, action_id.substr(11)), doing = "Removes ";
    std::string body;
    if (!a.enabled) {
        body = a.why;
    } else if (!names.empty()) {
        std::vector<std::string> shown;
        for (const std::string& nm : names) shown.push_back(m::display_name(fa, nm));
        body = doing + m::joined_most(shown, 6);
        if (doing == "Removes ") body += ". " + (a.describe.explain.empty() ? std::string() : a.describe.explain);
        else if (doing == "Gives their own moves to ")
            body += ": Tekken 8 runs hidden in the background to save them.";
        else
            body += std::string(": a few minutes each; the first time, ") + m::game_name(fg->game) +
                    " runs hidden in the background to save their moves.";
    }
    if (!body.empty())
        describe_panel(ui, "gv/what", a.label, body, fit(Box{.margin = {0, 6, 0, 0}}, SeamFit::BlueSkewed));
}

void App::outfits_view() {
    Ui& ui = *ui_;
    const m::CharactersView& cv = view_.characters;
    if (!cv.outfits_all) return;
    const m::Action& a = *cv.outfits_all;
    const auto choices = m::outfit_choices(model_->facts());
    size_t wanted = 0;
    for (const Fighter* f : choices) wanted += m::wants_outfits(model_->facts(), *f);
    section_label(ui, "ov/label", "Outfits", Half::Blue, std::to_string(wanted) + " of " + std::to_string(choices.size()),
                  fit({}, SeamFit::BlueRect));
    {
        auto row = ui.open("ov/state", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        pill(ui, "ov/pill", a.checked ? "All" : a.inconsistent ? "Some" : "None", a.checked ? Tone::Ok : Tone::Neutral);
    }
    text(ui, "ov/title", TextSpec{.text = "Outfits", .style = tx::kBig, .chroma = 3, .autofit_min = 28},
         fit({}, SeamFit::BlueRect));
    text(ui, "ov/about", TextSpec{.text = a.tooltip, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
         fit(Box{.margin = {0, 8, 0, 10}}, SeamFit::BlueRect));
    int n = 0;
    std::optional<m::Action> update;
    for (const m::Line& l : cv.outfits_notes) {
        const Tone t = l.icon == m::Icon::kWarning ? Tone::Warn : Tone::Blue;
        note(ui, "ov/note" + std::to_string(n++), t, l.text, fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect),
             l.icon == m::Icon::kUpdate ? "stroke:update" : "stroke:warn");
        for (const m::Action& b : l.actions) update = b;
    }
    if (update) {
        ButtonSpec bs;
        bs.label = update->label;
        bs.kind = ButtonKind::Blue;
        bs.size = ButtonSize::Small;
        bs.disabled = !update->enabled;
        Focus fo = blue_focus(!update->enabled);
        fo.left = "outfits-all";
        button(ui, update->id, bs, fo, fit(Box{.margin = {0, 6, 0, 0}}, SeamFit::BlueRect));
    }
}

// What adding characters needs that this PC lacks (Linux: numpy/Pillow with Download, the package manager's
// command to copy).
void App::needs_view() {
    Ui& ui = *ui_;
    const m::Fact* missing = nullptr;
    for (const m::Fact& f : view_.characters.facts)
        if (f.name == "Missing") missing = &f;
    if (!missing) return;
    section_label(ui, "nv/label", "Missing", Half::Blue, {}, fit({}, SeamFit::BlueRect));
    text(ui, "nv/title", TextSpec{.text = "To add them", .style = tx::kBig, .chroma = 3, .autofit_min = 28},
         fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
    int n = 0;
    bool first_button = true;
    for (const m::Line& l : missing->lines) {
        const std::string id = "nv/l" + std::to_string(n++);
        if (l.kind == m::Line::Kind::kCommand) {
            text(ui, id, TextSpec{.text = l.text, .style = tx::kFactValue, .color = rgb(0xe9f1ff), .wrap = true},
                 fit(Box{.pad = {12, 10, 12, 10}, .margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        } else {
            text(ui, id,
                 TextSpec{.text = l.text, .style = l.small ? tx::kParaSmall : tx::kPara,
                          .color = l.tone == m::Tone::kWarning ? c::kWarn : c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        }
        for (const m::Action& a : l.actions) {
            ButtonSpec bs;
            bs.label = a.id.starts_with("copy:") ? "Copy" : a.label;
            bs.kind = ButtonKind::Blue;
            bs.size = ButtonSize::Small;
            bs.disabled = !a.enabled;
            Focus fo = blue_focus(!a.enabled);
            if (first_button && !drilled()) fo.left = "fx:needs";
            first_button = false;
            button(ui, a.id, bs, fo, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        }
    }
}

// Accept on a crimson item of Fighters whose actions are on the blue side.
bool App::fighters_activate(const std::string& id) {
    if (id.starts_with("tile:")) {
        const m::FighterRow* r = fighter_row(id.substr(5));
        if (!r) return true;
        const std::vector<m::Action> acts = fighter_actions(*r);
        std::string target;
        for (const m::Action& a : acts)
            if (target.empty() && a.enabled) target = a.id;
        if (target.empty() && !acts.empty()) target = acts.front().id;
        if (!target.empty()) drill_in(id, target);
        return true;
    }
    if (id == "fx:needs") {
        for (const m::Fact& f : view_.characters.facts)
            if (f.name == "Missing")
                for (const m::Line& l : f.lines)
                    for (const m::Action& a : l.actions)
                        if (!drilled()) drill_in(id, a.id);
        return true;
    }
    if (id == "fx:early") {
        for (const m::Line& l : view_.characters.lines)
            for (const m::Action& a : l.actions)
                if (a.id.starts_with("copy:") && !drilled()) drill_in(id, a.id);
        return true;
    }
    return false;
}

} // namespace launcher::app
