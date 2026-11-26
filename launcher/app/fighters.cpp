// Fighters: Tekken 7's, Tekken 7's DLC and Tekken 8's characters as the model's characters view has them. Crimson:
// the groups (a header with its counts and its actions, disabled ones too: they say why) and their tiles, then
// Outfits for every character. Blue: ONLY the focused fighter (its game, its name, one state pill,
// its sentence, its outfits, its own progress while a task has it, its actions), or the focused group action's
// group (what the games and Steam say, its warnings, what that action would do), or what outfits are. Accept on a
// tile gives its actions on the blue side the focus and locks the crimson side until Back.

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

// [Tekken 8?][DLC?]
const char* kGroupTitles[2][2] = {{"Tekken 7", "Tekken 7 DLC"}, {"Tekken 8", "Tekken 8 DLC"}};

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
                // From the top of the frame's inside down (at most to the hips: the card's height), the face on the
                // card's middle at the eyes' height - the card leans, so its middle there is right of its box's - and
                // the picture at least as wide there as the card, either side of the face.
                const float face = art::kFaceX - art::kInner.x;   // (in the inside's pixels)
                const float s = std::max(r.h / std::min(art::kInner.h, 470.f),
                                         r.w / 2 / std::min(face, art::kInner.w - face));
                const float eyes = (art::kFaceY - art::kInner.y) * s;
                const float middle = r.center().x + (r.h / 2 - eyes) * theme::kSeamTan;
                const Rect dst{middle - face * s, r.y, art::kInner.w * s, r.h};
                const Rect uv{art::kInner.x / art::kPortraitW, art::kInner.y / art::kPortraitH,
                              art::kInner.w / art::kPortraitW, r.h / s / art::kPortraitH};
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
        base.title = kGroupTitles[t8][0];
        base.game = g.game;
        base.group = &g;
        for (const m::FighterRow& r : g.rows) base.rows.push_back(&r);
        out.push_back(base);
        if (g.dlc && !g.dlc->rows.empty()) {
            FighterGroup dlc;
            dlc.key = t8 ? "dlc8" : "dlc";
            dlc.title = kGroupTitles[t8][1];
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
// (a disabled action is a button with its own label, never a second state pill).
std::vector<m::Action> App::fighter_actions(const m::FighterRow& r) const {
    std::vector<m::Action> out;
    const m::Action* main = nullptr;
    const m::Action* remove = nullptr;
    for (const m::Action& a : r.buttons) {
        if (a.id.starts_with("remove:")) remove = &a;
        else main = &a;
    }
    // (The model's words, in the same language: the row's main button removes them.)
    const bool main_is_remove = main && main->label == tr("chars.remove", "Remove");
    if (main && !main_is_remove) out.push_back(*main);
    if (!main && !remove) {
        m::Action add;
        add.id = "fighter:" + r.name;
        add.label = tr("chars.add", "Add");
        add.enabled = false;
        add.why = !r.button_note.empty() || r.state_text == tr("chars.not_owned", "Not owned")
                      ? tr("chars.not_owned_why", "Your Steam account does not own their DLC: only owned ones can be added.")
                      : tr("fighters.cannot_add_now", "They cannot be added now.");
        add.describe.title = tr("fighters.add_name", "Add {name}", {{"name", r.display}});
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
    t.removing = s.kind == m::TaskKind::kRemove;
    t.verb = t.removing ? tr("fighters.removing", "Removing")
             : s.update ? tr("fighters.updating", "Updating")
                        : tr("fighters.adding", "Adding");
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
    if (cv.add_all_owned) screen_actions_[cv.add_all_owned->id] = *cv.add_all_owned;
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
        if (f.id == "missing") missing = &f;
    {
        auto g = ui.open("fi/crimson", crimson);
        int n = 0;
        for (const m::Line& l : cv.lines) {
            const bool warn = l.icon == m::Icon::kWarning || l.tone == m::Tone::kError;
            note(ui, "fi/line" + std::to_string(n++), warn ? Tone::Warn : Tone::Blue, l.text.empty() ? l.title : l.text,
                 fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::CrimsonRect), warn ? "stroke:warn" : "stroke:info");
        }
        if (missing) {
            MenuRowSpec s{"stroke:warn", tr("fighters.missing_row", "Missing to add characters"), ""};
            s.compact = true;
            s.value = missing->lines.empty() ? "" : tr("fighters.see_why", "See why");
            s.value_tone = Tone::Warn;
            menu_row(ui, "fx:needs", s, crimson_focus(), fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonSkewed));
        }
        // One button for every game's characters, above the games.
        if (cv.add_all_owned) {
            const m::Action& a = *cv.add_all_owned;
            const size_t count = m::all_owned_to_add(model_->facts()).size();
            MenuRowSpec s{"stroke:users", a.label};
            s.value = count > 0 ? trn("fighters.to_add", static_cast<long long>(count), "{n} to add", "{n} to add")
                                : tr("fighters.none_to_add", "None to add");
            s.value_tone = count > 0 ? Tone::Ok : Tone::Neutral;
            s.compact = true;
            s.disabled = !a.enabled;
            menu_row(ui, a.id, s, crimson_focus(false, !a.enabled),
                     fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonSkewed));
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
            h.count = tr("home.added_of", "{added} of {total} added", {{"added", added}, {"total", fg.rows.size()}});
            h.focus_group = -1;
            if (fg.dlc) {
                if (model_->facts().owned.state == m::OwnedState::kChecking) {
                    h.sub = tr("fighters.asking_steam", "Asking Steam…");
                    h.sub_tone = Tone::Dim;
                } else if (known > 0) {
                    h.sub = tr("fighters.owned_of", "{owned} of {total} owned", {{"owned", owned}, {"total", fg.rows.size()}});
                    h.sub_tone = Tone::Ok;
                } else {
                    h.sub = tr("fighters.ownership_unknown", "Ownership not known");
                    h.sub_tone = Tone::Dim;
                }
            } else if (update) {
                h.sub = trn("home.to_update", update, "{n} to update", "{n} to update");
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
                t.tone = fg.game == kTekken8 ? (fg.dlc ? TileTone::Gold : TileTone::Orange)
                         : fg.dlc            ? TileTone::Pink
                                             : TileTone::Red;
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
                    t.tag = tr("fighters.outfits", "Outfits");
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
            o.title = tr("fighters.outfits_all", "Outfits for every character");
            o.value = a.checked     ? tr("fighters.all", "All")
                      : wanted == 0 ? tr("fighters.none", "None")
                                    : tr("progress.of", "{done} of {total}", {{"done", wanted}, {"total", choices.size()}});
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
        u.label = tr("fighters.update_all", "Update All");
        out.push_back(u);
    } else {
        m::Action u;
        u.id = fg.key == "t8" ? "update-all:tekken8" : "update-all";
        u.label = tr("fighters.update_all", "Update All");
        u.enabled = false;
        u.why = tr("fighters.all_up_to_date", "Every added character is up to date.");
        u.describe.title = u.label;
        u.describe.why = u.why;
        out.push_back(u);
    }
    if (stand_ins) {
        m::Action s = *stand_ins;
        s.label = tr("fighters.own_moves", "Own Moves");
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
        section_label(ui, "fi/label", tr("home.fighters", "Fighters"), Half::Crimson, {},
                      fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::CrimsonRect));
        MenuRowSpec s{looking ? "stroke:dots" : "stroke:warn",
                      looking ? tr("fighters.looking_games", "Looking for your games…")
                              : tr("fighters.cannot_yet", "Fighters cannot be added yet")};
        s.compact = true;
        menu_row(ui, "fx:early", s, crimson_focus(true), fit({}, SeamFit::CrimsonSkewed));
    }
    auto g = ui.open("fi/blue", blue);
    section_label(ui, "fe/label", tr("home.fighters", "Fighters"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
    text(ui, "fe/title",
         TextSpec{.text = looking ? tr("fighters.looking", "Looking") : tr("fighters.not_yet", "Not yet"),
                  .style = tx::kBig, .chroma = 3, .autofit_min = 28},
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
        b.label = tr("pre.copy", "Copy");
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
    else if (fo == "add-all-owned:all") key = "all";
    else if (fo == "fx:needs") key = "needs";
    // (Nothing focused yet, or a key from another state: the first fighter.)
    const auto known = [&](const std::string& k) {
        if (k.starts_with("f:")) return fighter_row(k.substr(2)) != nullptr;
        if (k.starts_with("g:")) {
            const size_t colon = k.find(':', 2);
            return colon != std::string::npos && screen_actions_.count(k.substr(colon + 1)) > 0;
        }
        if (k == "outfits") return view_.characters.outfits_all.has_value();
        if (k == "all") return view_.characters.add_all_owned.has_value();
        if (k == "needs") return std::any_of(view_.characters.facts.begin(), view_.characters.facts.end(),
                                              [](const m::Fact& f) { return f.id == "missing"; });
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
        else if (k == "all") add_all_view();
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
    section_label(ui, "fv/label", tr("fighters.fighter", "Fighter"), Half::Blue, std::to_string(index) + "/" + std::to_string(total),
                  fit({}, SeamFit::BlueRect));
    const bool t8 = f->of(kTekken8);
    const std::optional<bool> owned = m::owns(facts, *f);
    {
        auto row = ui.open("fv/game", fit(Box{.layout = Layout::Row, .h = Size::fixed(26), .margin = {0, 0, 0, 10},
                                              .gap = 12, .align = Align::Center},
                                          SeamFit::BlueRect));
        pill(ui, "fv/game-pill", (t8 ? "Tekken 8" : "Tekken 7") + std::string(f->dlc ? " · DLC" : ""), t8 ? Tone::Blue : Tone::Red);
        std::string found;
        if (f->dlc) {
            found = owned == true    ? tr("fighters.steam_owned", "Steam: owned")
                    : owned == false ? tr("fighters.steam_not_owned", "Steam: not owned")
                    : facts.owned.state == m::OwnedState::kChecking ? tr("fighters.steam_asking", "Steam: asking…")
                                                                     : tr("fighters.steam_unknown", "Steam: not known");
        } else {
            const bool usable = t8 ? s.tekken8_usable() : s.tekken7_usable();
            const bool present = t8 ? s.tekken8_found : s.tekken7_found;
            const i18n::Args game = {{"game", t8 ? "Tekken 8" : "Tekken 7"}};
            found = usable    ? tr("fighters.game_found", "{game} found", game)
                    : present ? tr("fighters.game_unusable", "{game} cannot be used", game)
                              : tr("fighters.game_absent", "{game} not installed", game);
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

    // ONE state pill, then its sentence.
    const FighterTask task = fighter_task(name);
    std::string state, sentence;
    Tone tone = Tone::Neutral;
    bool live = false;
    if (task.in) {
        state = task.verb + "…";
        tone = Tone::Blue;
        live = true;
        sentence = task.state == 2 ? tr("fighters.part_done", "Their part is done: the rest of the task finishes it.")
                   : task.state == 1 ? tr("fighters.being_made", "Their pack is being made now.")
                                     : tr("fighters.waiting_turn", "Waiting for their turn: {i} of {n}.",
                                          {{"i", task.index}, {"n", task.count}});
        if (task.removing)
            sentence = task.state == 2 ? tr("fighters.removed_rest", "Removed: the rest of the task finishes it.")
                                       : tr("fighters.being_removed", "Their pack is being removed.");
    } else if (r->pill) {
        state = r->pill->text;
        tone = pill_tone(r->pill->kind);
        sentence = r->pill->text == tr("chars.pill_added", "Added")
                       ? tr("fighters.in_game", "In the game: on the select screen next time it starts.")
                       : r->pill->explain;
    } else if (owned == false) {
        state = tr("chars.not_owned", "Not owned");
        sentence = tr("chars.not_owned_why", "Your Steam account does not own their DLC: only owned ones can be added.");
    } else if (f->dlc && !owned && facts.owned.state == m::OwnedState::kChecking) {
        state = tr("fighters.checking", "Checking");
        tone = Tone::Blue;
        live = true;
        sentence = tr("fighters.asking_owns", "Asking Steam whether your account owns their DLC…");
    } else {
        state = tr("fighters.not_added", "Not added");
        const std::vector<m::Action> acts = fighter_actions(*r);
        const m::Action* add = acts.empty() ? nullptr : &acts.front();
        if (add && !add->enabled && !add->why.empty()) sentence = add->why;
        else
            sentence = tr("fighters.not_in_game", "Not in the game yet: Add makes their pack from your {game}. It "
                                                  "takes a few minutes.",
                          {{"game", t8 ? "Tekken 8" : "Tekken 7"}});
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
        const i18n::Args args = {{"i", task.index}, {"n", task.count}};
        std::string line = task.state == 2   ? tr("fighters.done_of", "Done · {i} of {n}", args)
                           : task.state == 1 ? tr("fighters.now_of", "Now · {i} of {n}", args)
                                             : tr("fighters.waiting_of", "Waiting · {i} of {n}", args);
        if (task.state == 1 && !task.detail.empty()) line += " · " + task.detail;
        text(ui, "fv/progress", TextSpec{line, tx::kKick, c::kBlueDim}, fit({}, SeamFit::BlueRect));
    }
    // Its actions: right-aligned in the blue half; disabled ones dimmed, their why is the sentence
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
        else if (a.id.starts_with("remove:") || a.label == tr("chars.remove", "Remove")) bs.kind = ButtonKind::Danger;
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
    section_label(ui, "gv/label", tr("fighters.group", "Group"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
    {
        auto row = ui.open("gv/count", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        pill(ui, "gv/pill", tr("home.added_of", "{added} of {total} added", {{"added", added}, {"total", fg->rows.size()}}));
    }
    text(ui, "gv/title", TextSpec{.text = fg->title, .style = tx::kBig, .chroma = 3, .autofit_min = 28},
         fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    // The games and Steam as the importer found them.
    std::vector<Fact> list;
    for (const m::Fact& f : cv.facts) {
        const bool game_fact = f.id == kTekken7 || f.id == kTekken8;
        if (game_fact && f.id != fg->game) continue;
        if (f.id == "missing") continue;
        std::vector<Run> runs;
        for (const m::Line& l : f.lines) {
            if (!l.actions.empty()) continue;
            if (!runs.empty()) runs.push_back({"\n", kValue});
            const Color col = l.tone == m::Tone::kError     ? c::kBad
                              : l.tone == m::Tone::kWarning ? c::kWarn
                              : l.tone == m::Tone::kDim     ? c::kBlueDim
                              : f.id == "steam" && l.text == tr("chars.steam_running", "Running") ? c::kOk
                                                                                                  : kValue;
            runs.push_back({l.text, col});
        }
        list.push_back({f.name, runs, f.id != "steam" && f.id != "game"});
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
    enum class Doing { kNone, kAdd, kUpdate, kOwnMoves, kRemove } doing = Doing::kNone;
    if (action_id == "add-all") names = m::base_to_add(fa, kTekken7), doing = Doing::kAdd;
    else if (action_id == "add-all:tekken8") names = m::base_to_add(fa, kTekken8), doing = Doing::kAdd;
    else if (action_id == "add-all-owned") names = m::owned_to_add(fa, kTekken7), doing = Doing::kAdd;
    else if (action_id == "add-all-owned:tekken8") names = m::owned_to_add(fa, kTekken8), doing = Doing::kAdd;
    else if (action_id == "update-all") names = m::to_update(fa, kTekken7), doing = Doing::kUpdate;
    else if (action_id == "update-all:tekken8") names = m::to_update(fa, kTekken8), doing = Doing::kUpdate;
    else if (action_id == "update-stand-ins") names = m::to_update(fa, kTekken8, true), doing = Doing::kOwnMoves;
    else if (action_id.starts_with("remove-all:")) names = m::to_remove_all(fa, action_id.substr(11)), doing = Doing::kRemove;
    std::string body;
    if (!a.enabled) {
        body = a.why;
    } else if (!names.empty()) {
        std::vector<std::string> shown;
        for (const std::string& nm : names) shown.push_back(m::display_name(fa, nm));
        const std::string list = m::joined_most(shown, 6);
        const std::string game = m::game_name(fg->game);
        if (doing == Doing::kRemove)
            body = a.describe.explain.empty()
                       ? tr("fighters.removes", "Removes {names}.", {{"names", list}})
                       : tr("fighters.removes_about", "Removes {names}. {about}", {{"names", list}, {"about", a.describe.explain}});
        else if (doing == Doing::kOwnMoves)
            body = tr("fighters.own_moves_about", "Gives their own moves to {names}: Tekken 8 runs hidden in the "
                                                  "background to save them.",
                      {{"names", list}});
        else if (doing == Doing::kUpdate)
            body = tr("fighters.updates_about", "Updates {names}: a few minutes each; the first time, {game} runs "
                                                "hidden in the background to save their moves.",
                      {{"names", list}, {"game", game}});
        else
            body = tr("fighters.adds_about", "Adds {names}: a few minutes each; the first time, {game} runs hidden in "
                                             "the background to save their moves.",
                      {{"names", list}, {"game", game}});
    }
    if (!body.empty())
        describe_panel(ui, "gv/what", a.label, body, fit(Box{.margin = {0, 6, 0, 0}}, SeamFit::BlueSkewed));
}

// Add All Owned for every game: who it adds, or why it cannot now.
void App::add_all_view() {
    Ui& ui = *ui_;
    const m::CharactersView& cv = view_.characters;
    if (!cv.add_all_owned) return;
    const m::Action& a = *cv.add_all_owned;
    const m::Facts& fa = model_->facts();
    const auto names = m::all_owned_to_add(fa);
    section_label(ui, "av/label", tr("fighters.every_game", "Every game"), Half::Blue, {}, fit({}, SeamFit::BlueRect));
    {
        auto row = ui.open("av/count", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        pill(ui, "av/pill",
             names.empty() ? tr("fighters.none_to_add", "None to add")
                           : trn("fighters.to_add", static_cast<long long>(names.size()), "{n} to add", "{n} to add"),
             names.empty() ? Tone::Neutral : Tone::Ok);
    }
    text(ui, "av/title", TextSpec{.text = a.label, .style = tx::kBig, .chroma = 3, .autofit_min = 28},
         fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    text(ui, "av/about", TextSpec{.text = a.describe.explain, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
         fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
    std::string body = a.why;
    if (a.enabled) {
        std::vector<std::string> shown;
        for (const std::string& nm : names) shown.push_back(m::display_name(fa, nm));
        body = tr("fighters.adds_all_about", "Adds {names}: a few minutes each; the first time, their game runs hidden "
                                             "in the background to save their moves.",
                  {{"names", m::joined_most(shown, 8)}});
    }
    describe_panel(ui, "av/what", a.label, body, fit(Box{.margin = {0, 6, 0, 0}}, SeamFit::BlueSkewed));
}

void App::outfits_view() {
    Ui& ui = *ui_;
    const m::CharactersView& cv = view_.characters;
    if (!cv.outfits_all) return;
    const m::Action& a = *cv.outfits_all;
    const auto choices = m::outfit_choices(model_->facts());
    size_t wanted = 0;
    for (const Fighter* f : choices) wanted += m::wants_outfits(model_->facts(), *f);
    section_label(ui, "ov/label", tr("fighters.outfits", "Outfits"), Half::Blue,
                  tr("progress.of", "{done} of {total}", {{"done", wanted}, {"total", choices.size()}}),
                  fit({}, SeamFit::BlueRect));
    {
        auto row = ui.open("ov/state", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 8}}, SeamFit::BlueRect));
        pill(ui, "ov/pill",
             a.checked        ? tr("fighters.all", "All")
             : a.inconsistent ? tr("fighters.some", "Some")
                              : tr("fighters.none", "None"),
             a.checked ? Tone::Ok : Tone::Neutral);
    }
    text(ui, "ov/title", TextSpec{.text = tr("fighters.outfits", "Outfits"), .style = tx::kBig, .chroma = 3, .autofit_min = 28},
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
        if (f.id == "missing") missing = &f;
    if (!missing) return;
    section_label(ui, "nv/label", missing->name, Half::Blue, {}, fit({}, SeamFit::BlueRect));
    text(ui, "nv/title",
         TextSpec{.text = tr("fighters.to_add_them", "To add them"), .style = tx::kBig, .chroma = 3, .autofit_min = 28},
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
            bs.label = a.id.starts_with("copy:") ? tr("pre.copy", "Copy") : a.label;
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
            if (f.id == "missing")
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
