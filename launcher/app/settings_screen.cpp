// Settings: the section switcher (Display, Keyboard, Launcher, and Folders on Windows; Display and Keyboard once the
// game is installed, Launcher always) and the open section's rows on the crimson side, their values changed in
// place (FEEDBACK F5: every row, value box and arrow inside the plate, each row's end following the seam), the
// focused setting on the blue side (FEEDBACK F2: right-aligned): what it does, its options, notes. Keyboard: the 19
// inputs in three columns, a gamepad with the focused input lit, choosing a key (U4) with its 10 s countdown.

#include "app.h"

#include "builders.h"
#include "rules.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

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

std::string value_of(const m::Action& a) {
    if (a.kind == m::ActionKind::kSwitch || a.kind == m::ActionKind::kCheck) return a.checked ? "On" : "Off";
    if (a.kind == m::ActionKind::kChoice && a.chosen >= 0 && static_cast<size_t>(a.chosen) < a.choices.size())
        return a.choices[static_cast<size_t>(a.chosen)];
    return a.label;
}

const char* kSectionLabels[] = {"Display", "Keyboard", "Launcher", "Folders"};

// ---- the gamepad picture (an original, generic one: Settings > Keyboard)

struct PadPart {
    enum Kind { kArm, kFace, kStick, kPill, kHome, kBumper, kTrigger } kind;
    float x, y, w, h;
    float dx = 0, dy = 0; // sticks: the direction lit
};

// Where each input is on the picture (design box 330 x 176).
PadPart pad_part(const std::string& input) {
    if (input == "dpad_up") return {PadPart::kArm, 70, 54, 16, 20};
    if (input == "dpad_down") return {PadPart::kArm, 70, 82, 16, 20};
    if (input == "dpad_left") return {PadPart::kArm, 54, 70, 20, 16};
    if (input == "dpad_right") return {PadPart::kArm, 82, 70, 20, 16};
    if (input == "face_top") return {PadPart::kFace, 252, 56, 9, 0};
    if (input == "face_bottom") return {PadPart::kFace, 252, 100, 9, 0};
    if (input == "face_left") return {PadPart::kFace, 230, 78, 9, 0};
    if (input == "face_right") return {PadPart::kFace, 274, 78, 9, 0};
    if (input == "stick_up") return {PadPart::kStick, 122, 120, 19, 0, 0, -1};
    if (input == "stick_down") return {PadPart::kStick, 122, 120, 19, 0, 0, 1};
    if (input == "stick_left") return {PadPart::kStick, 122, 120, 19, 0, -1, 0};
    if (input == "stick_right") return {PadPart::kStick, 122, 120, 19, 0, 1, 0};
    if (input == "minus") return {PadPart::kPill, 140, 64, 20, 9};
    if (input == "plus") return {PadPart::kPill, 170, 64, 20, 9};
    if (input == "home") return {PadPart::kHome, 165, 90, 7, 0};
    if (input == "l") return {PadPart::kBumper, 34, 20, 100, 15};
    if (input == "r") return {PadPart::kBumper, 196, 20, 100, 15};
    if (input == "zl") return {PadPart::kTrigger, 44, 2, 80, 14};
    if (input == "zr") return {PadPart::kTrigger, 206, 2, 80, 14};
    return {PadPart::kHome, -100, -100, 0, 0};
}

void paint_pad(PaintContext& ctx, const std::string& lit, bool capturing) {
    Canvas& cv = ctx.canvas;
    const Rect r = ctx.rect;
    const float k = r.w / 330.f;
    const auto P = [&](float x, float y) { return Vec2{r.x + x * k, r.y + y * k}; };
    const auto R = [&](float x, float y, float w, float h) { return Rect{r.x + x * k, r.y + y * k, w * k, h * k}; };
    const Color stroke = rgba(150, 190, 255, .55f), body = rgb(0x0b1736), part = rgba(150, 190, 255, .18f);
    const Color on = capturing ? c::kWarn : c::kCyan;
    const PadPart litp = pad_part(lit);
    const auto lit_is = [&](PadPart::Kind kind, float x, float y) {
        return litp.kind == kind && std::abs(litp.x - x) < .5f && std::abs(litp.y - y) < .5f;
    };
    // Shoulders behind the body: triggers, then bumpers.
    for (const float x : {44.f, 206.f}) {
        const bool l = lit_is(PadPart::kTrigger, x, 2);
        rounded_rect(cv, R(x - 1, 1, 82, 16), 8 * k, stroke);
        rounded_rect(cv, R(x, 2, 80, 14), 7 * k, l ? on : body);
    }
    for (const float x : {34.f, 196.f}) {
        const bool l = lit_is(PadPart::kBumper, x, 20);
        rounded_rect(cv, R(x - 1, 19, 102, 17), 8.5f * k, stroke);
        rounded_rect(cv, R(x, 20, 100, 15), 7.5f * k, l ? on : body);
    }
    // The body: a wide rounded top and two grips (outline = the same shapes grown by a point, drawn first).
    const float o = 1.4f;
    rounded_rect(cv, R(10 - o, 34 - o, 310 + 2 * o, 92 + 2 * o), (46 + o) * k, stroke);
    cv.circle(P(70, 120), (54 + o) * k, stroke);
    cv.circle(P(260, 120), (54 + o) * k, stroke);
    rounded_rect(cv, R(10, 34, 310, 92), 46 * k, body);
    cv.circle(P(70, 120), 54 * k, body);
    cv.circle(P(260, 120), 54 * k, body);
    // D-pad.
    cv.fill_rect(R(70, 54, 16, 48), part);
    cv.fill_rect(R(54, 70, 48, 16), part);
    for (const PadPart arm : {pad_part("dpad_up"), pad_part("dpad_down"), pad_part("dpad_left"), pad_part("dpad_right")})
        if (lit_is(PadPart::kArm, arm.x, arm.y)) cv.fill_rect(R(arm.x, arm.y, arm.w, arm.h), on);
    // Face buttons.
    for (const char* f : {"face_top", "face_bottom", "face_left", "face_right"}) {
        const PadPart p = pad_part(f);
        cv.ring(P(p.x, p.y), p.w * k, 1.3f * k, stroke);
        if (lit_is(PadPart::kFace, p.x, p.y)) cv.circle(P(p.x, p.y), (p.w - 1) * k, on);
    }
    // Sticks: the lit direction as a dot toward it.
    for (const float x : {122.f, 208.f}) {
        cv.ring(P(x, 120), 19 * k, 1.3f * k, stroke);
        cv.circle(P(x, 120), 12 * k, part);
    }
    if (litp.kind == PadPart::kStick) {
        cv.ring(P(litp.x, litp.y), 19 * k, 2.2f * k, on);
        cv.circle(P(litp.x + litp.dx * 9, litp.y + litp.dy * 9), 6 * k, on);
    }
    // Minus, plus, home.
    for (const char* f : {"minus", "plus"}) {
        const PadPart p = pad_part(f);
        rounded_rect(cv, R(p.x, p.y, p.w, p.h), 4.5f * k, lit_is(PadPart::kPill, p.x, p.y) ? on : part);
    }
    cv.ring(P(165, 90), 7 * k, 1.2f * k, stroke);
    if (litp.kind == PadPart::kHome && litp.x > 0) cv.circle(P(165, 90), 6 * k, on);
    if (!lit.empty()) {
        // A soft glow on the lit part.
        cv.radial(litp.kind == PadPart::kArm || litp.kind == PadPart::kPill || litp.kind == PadPart::kBumper ||
                          litp.kind == PadPart::kTrigger
                      ? P(litp.x + litp.w / 2, litp.y + litp.h / 2)
                      : P(litp.x, litp.y),
                  26 * k, on.with_alpha(.35f));
    }
}

} // namespace

// The sections this Settings has (U17: the launcher's own always; the game's once it is installed, or on Windows).
std::vector<std::string> App::settings_sections() const {
    std::vector<std::string> out;
    if (!view_.settings) return {"launcher"};
    const m::SettingsView& s = *view_.settings;
    if (!s.display.empty()) out.push_back("display");
    if (!s.groups.empty()) out.push_back("keyboard");
    out.push_back("launcher");
    if (s.folders_shown) out.push_back("folders");
    return out;
}

void App::settings_switch(int delta, const std::string& to) {
    const std::vector<std::string> secs = settings_sections();
    if (secs.size() < 2) return;
    auto at = std::find(secs.begin(), secs.end(), settings_section_);
    int i = at == secs.end() ? 0 : static_cast<int>(at - secs.begin());
    if (!to.empty()) {
        const auto t = std::find(secs.begin(), secs.end(), to);
        if (t == secs.end() || *t == settings_section_) return;
        i = static_cast<int>(t - secs.begin());
    } else {
        i = (i + delta + static_cast<int>(secs.size())) % static_cast<int>(secs.size());
    }
    if (model_->keys().picking() >= 0) model_->cancel_key();
    settings_section_ = secs[static_cast<size_t>(i)];
    cue(ttt2::app::Cue::SectionSwitch);
    // (Its first row, as when Settings opens: U7.)
    ui_->focus("", true);
    settings_key_.clear();
    stage_->note_input(now());
}

void App::settings(const Box& crimson, const Box& blue) {
    Ui& ui = *ui_;
    if (!view_.settings) return placeholder(crimson, blue);
    const m::SettingsView& sv = *view_.settings;
    const std::vector<std::string> secs = settings_sections();
    if (std::find(secs.begin(), secs.end(), settings_section_) == secs.end()) settings_section_ = secs.front();
    std::vector<Section> tabs;
    int active = 0;
    for (const std::string& s : secs) {
        if (s == settings_section_) active = static_cast<int>(tabs.size());
        const int i = s == "display" ? 0 : s == "keyboard" ? 1 : s == "launcher" ? 2 : 3;
        tabs.push_back({"sec:" + s, kSectionLabels[i]});
    }
    // The rows' actions: their whys, kinds and values (prompts, refusals, Change).
    for (const m::SettingRow& r : sv.display) screen_actions_[r.control.id] = r.control;
    for (const m::SettingRow& r : sv.launcher) screen_actions_[r.control.id] = r.control;
    for (const m::KeyGroup& g : sv.groups)
        for (const m::KeyRow& k : g.rows) screen_actions_[k.keycap.id] = k.keycap;
    for (const m::Action& a : sv.keys_actions) screen_actions_[a.id] = a;
    for (const m::Action& a : sv.folders_actions) screen_actions_[a.id] = a;
    for (const m::FolderRow& f : sv.folders) screen_actions_[f.browse.id] = f.browse;
    {
        auto g = ui.open("st/crimson", crimson);
        section_tabs(ui, "secs", tabs, active, fit(Box{.margin = {0, 0, 0, 14}}, SeamFit::CrimsonRect), -1);
        const std::string up = "sec:" + settings_section_;
        if (settings_section_ == "display" || settings_section_ == "launcher") {
            int n = 0;
            if (settings_section_ == "display")
                for (const m::Line& l : sv.display_notes)
                    note(ui, "st/dnote" + std::to_string(n++), l.tone == m::Tone::kError ? Tone::Bad : Tone::Warn,
                         l.text, fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::CrimsonRect), "stroke:warn");
            auto rows = ui.open("st/rows", Box{.gap = 8});
            const std::vector<m::SettingRow>& list = settings_section_ == "display" ? sv.display : sv.launcher;
            bool first = true;
            for (const m::SettingRow& r : list) {
                SettingRowSpec s;
                s.title = r.name;
                s.disabled = !r.control.enabled;
                if (r.control.kind == m::ActionKind::kButton) {
                    s.chevron = true;
                } else {
                    s.value = value_of(r.control);
                    s.value_on = r.control.kind == m::ActionKind::kSwitch && r.control.checked;
                }
                s.slide = settings_slide_;
                Focus f = crimson_focus(first, !r.control.enabled);
                if (first) f.up = up;
                first = false;
                setting_row(ui, r.control.id, s, f, fit({}, SeamFit::CrimsonSkewed));
            }
        } else if (settings_section_ == "keyboard") {
            settings_keys_crimson(sv, up);
        } else if (settings_section_ == "folders") {
            auto rows = ui.open("st/rows", Box{.gap = 8});
            bool first = true;
            for (const m::FolderRow& r : sv.folders) {
                SettingRowSpec s;
                s.title = r.name;
                s.detail = r.value.empty() ? std::string("Not set") : m::shown_path(r.value);
                s.chevron = true;
                Focus f = crimson_focus(first);
                if (first) f.up = up;
                first = false;
                setting_row(ui, "fold:" + r.key, s, f, fit({}, SeamFit::CrimsonSkewed));
            }
            auto b = ui.open("st/fbtns", fit(Box{.layout = Layout::Row, .margin = {0, 8, 0, 0}, .gap = 12,
                                                .align = Align::Center},
                                            SeamFit::CrimsonRect));
            for (const m::Action& a : sv.folders_actions) {
                ButtonSpec bs;
                bs.label = a.label;
                bs.kind = a.primary ? ButtonKind::Primary : ButtonKind::Ghost;
                bs.half = Half::Crimson;
                bs.disabled = !a.enabled;
                button(ui, a.id, bs, crimson_focus(false, !a.enabled));
            }
            for (const m::Line& l : sv.folders_notes)
                text(ui, "st/fnote", TextSpec{l.text, tx::kKick, l.tone == m::Tone::kOk ? c::kOk : c::kBad},
                     Box{.shrink_order = 1});
        }
    }
    settings_blue(blue, sv);
}

// Keyboard: the 19 inputs in three columns (D-pad and Left stick, Face buttons and System, L / R / ZL / ZR).
void App::settings_keys_crimson(const m::SettingsView& sv, const std::string& up) {
    Ui& ui = *ui_;
    for (const m::Line& l : sv.keys_notes)
        note(ui, "st/knote", l.tone == m::Tone::kError ? Tone::Bad : Tone::Warn, l.text,
             fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::CrimsonRect), "stroke:warn");
    const char* columns[3][2] = {{"D-pad", "Left stick"}, {"Face buttons", "System"}, {"Shoulders", nullptr}};
    const float weights[3] = {1.1f, 1.3f, 1.f};
    auto row = ui.open("st/keys", fit(Box{.layout = Layout::Row, .gap = 14}, SeamFit::CrimsonRect));
    bool first = true;
    const double t = ui.now();
    for (int c = 0; c < 3; ++c) {
        auto col = ui.open("st/kcol" + std::to_string(c), Box{.w = Size::grow(weights[c])});
        for (const char* gname : columns[c]) {
            if (!gname) continue;
            const m::KeyGroup* group = nullptr;
            for (const m::KeyGroup& g : sv.groups)
                if (g.title == gname) group = &g;
            if (!group) continue;
            const std::string label = std::string(gname) == "Shoulders" ? "L / R / ZL / ZR" : gname;
            section_label(ui, std::string("st/kl-") + gname, label, Half::Crimson, {},
                          Box{.margin = {0, 0, 0, 6}});
            for (const m::KeyRow& k : group->rows) {
                KeyRowSpec s;
                s.icon = "icons/ttt2-input-" + k.input + ".svg";
                s.name = k.name;
                s.key = k.keycap.checked ? "…" : k.keycap.label;
                s.capturing = k.keycap.checked;
                s.swapped = k.note_tone == m::Tone::kOk && !k.note.empty();
                s.flash_until = k.flash ? t + .4 : 0;
                Focus f = crimson_focus(first);
                if (first) f.up = up;
                first = false;
                key_row(ui, k.keycap.id, s, f);
            }
            ui.leaf("st/kgap-" + std::string(gname), Box{.h = Size::fixed(10)}, {}, {});
        }
    }
}

void App::settings_blue(const Box& blue, const m::SettingsView& sv) {
    Ui& ui = *ui_;
    auto g = ui.open("st/blue", blue);
    const std::string& fo = ui.focused();
    std::string key = settings_key_;
    if (drilled() && drill_->opener.starts_with("fold:")) key = drill_->opener;
    else if (screen_actions_.count(fo) && !fo.starts_with("restore-keys") && fo != "open-keyboard-file" &&
             fo != "save-folders" && !fo.starts_with("folder:"))
        key = fo;
    else if (fo.starts_with("fold:")) key = fo;
    else if (fo.starts_with("sec:")) key = fo;
    // (A key of another section: its first row.)
    const auto in_section = [&](const std::string& k) {
        if (k.starts_with("sec:")) return true;
        if (settings_section_ == "display")
            return std::any_of(sv.display.begin(), sv.display.end(),
                               [&](const m::SettingRow& r) { return r.control.id == k; });
        if (settings_section_ == "launcher")
            return std::any_of(sv.launcher.begin(), sv.launcher.end(),
                               [&](const m::SettingRow& r) { return r.control.id == k; });
        if (settings_section_ == "keyboard") return k.starts_with("key:");
        return k.starts_with("fold:");
    };
    if (key.empty() || !in_section(key)) {
        key.clear();
        if (settings_section_ == "display" && !sv.display.empty()) key = sv.display[0].control.id;
        else if (settings_section_ == "launcher" && !sv.launcher.empty()) key = sv.launcher[0].control.id;
        else if (settings_section_ == "keyboard" && !sv.groups.empty()) key = sv.groups[0].rows[0].keycap.id;
        else if (settings_section_ == "folders" && !sv.folders.empty()) key = "fold:" + sv.folders[0].key;
    }
    settings_key_ = key;
    settings_ro_.show(settings_section_ + "|" + key, last_dy_, ui.now());
    settings_ro_.build(ui, "st/ro", Box{}, [&](const std::string& full) {
        const std::string k = full.substr(full.find('|') + 1);
        if (k.starts_with("key:")) return key_view(sv, k);
        if (k.starts_with("fold:")) return folder_view(sv, k.substr(5));
        if (k.starts_with("sec:")) {
            const std::string s = k.substr(4);
            section_label(ui, "sv/label", "Settings", Half::Blue, {}, fit({}, SeamFit::BlueRect));
            const int i = s == "display" ? 0 : s == "keyboard" ? 1 : s == "launcher" ? 2 : 3;
            text(ui, "sv/title", TextSpec{.text = kSectionLabels[i], .style = tx::kBig, .chroma = 3, .autofit_min = 28},
                 fit({}, SeamFit::BlueRect));
            const std::string about = s == "display"    ? sv.display_about
                                      : s == "keyboard" ? sv.keys_about
                                      : s == "launcher" ? std::string("The launcher's own settings: they apply at once.")
                                                        : sv.folders_about;
            text(ui, "sv/about", TextSpec{.text = about, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
                 fit(Box{.margin = {0, 10, 0, 0}}, SeamFit::BlueRect));
            return;
        }
        setting_view(sv, k);
    });
}

void App::setting_view(const m::SettingsView& sv, const std::string& id) {
    Ui& ui = *ui_;
    const bool display = settings_section_ == "display";
    const std::vector<m::SettingRow>& list = display ? sv.display : sv.launcher;
    const m::SettingRow* row = nullptr;
    int index = 0;
    for (size_t i = 0; i < list.size(); ++i)
        if (list[i].control.id == id) row = &list[i], index = static_cast<int>(i) + 1;
    if (!row) return;
    const m::Action& a = row->control;
    section_label(ui, "sv/label", display ? "Display" : "Launcher", Half::Blue,
                  std::to_string(index) + "/" + std::to_string(list.size()), fit({}, SeamFit::BlueRect));
    const std::string value = value_of(a);
    if (a.kind != m::ActionKind::kButton) {
        auto r = ui.open("sv/now", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
        pill(ui, "sv/now-pill", "Now: " + value,
             a.kind == m::ActionKind::kSwitch && a.checked ? Tone::Blue : Tone::Neutral);
    }
    text(ui, "sv/title", TextSpec{.text = row->name, .style = tx::kBig, .chroma = 3, .autofit_min = 26},
         fit({}, SeamFit::BlueRect));
    text(ui, "sv/about", TextSpec{.text = row->about, .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
         fit(Box{.margin = {0, 10, 0, 8}}, SeamFit::BlueRect));
    if (!a.enabled && !a.why.empty())
        note(ui, "sv/why", Tone::Warn, a.why, fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect), "stroke:warn");
    int n = 0;
    for (const m::Line& l : row->notes)
        text(ui, "sv/note" + std::to_string(n++),
             TextSpec{.text = l.text, .style = tx::kParaSmall, .color = c::kBlueFaint, .wrap = true},
             fit(Box{.margin = {0, 0, 0, 6}}, SeamFit::BlueRect));
    if (a.kind == m::ActionKind::kSwitch) {
        const std::string opts[] = {"Off", "On"};
        chips(ui, "sv/chips", opts, a.checked ? 1 : 0, fit(Box{.margin = {0, 4, 0, 10}}, SeamFit::BlueRect));
    } else if (a.kind == m::ActionKind::kChoice) {
        chips(ui, "sv/chips", a.choices, a.chosen, fit(Box{.margin = {0, 4, 0, 10}}, SeamFit::BlueRect));
    }
    if (display) {
        for (const m::Line& l : sv.display_notes)
            note(ui, "sv/dnote" + std::to_string(n++), l.tone == m::Tone::kError ? Tone::Bad : Tone::Warn, l.text,
                 fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect), "stroke:warn");
    }
    const std::string hint = a.kind == m::ActionKind::kButton
                                 ? "Enter uses it."
                                 : display ? "The game uses it when it starts. Left and right change it on the row."
                                           : "It applies at once. Left and right change it on the row.";
    text(ui, "sv/hint", TextSpec{.text = hint, .style = tx::kParaSmall, .color = c::kBlueFaint, .wrap = true},
         fit(Box{.margin = {0, 4, 0, 0}}, SeamFit::BlueRect));
}

void App::key_view(const m::SettingsView& sv, const std::string& id) {
    Ui& ui = *ui_;
    const m::KeyRow* row = nullptr;
    int index = 0, total = 0;
    for (const m::KeyGroup& g : sv.groups)
        for (const m::KeyRow& k : g.rows) {
            ++total;
            if (k.keycap.id == id) row = &k, index = total;
        }
    if (!row) return;
    const bool capturing = row->keycap.checked;
    section_label(ui, "kv/label", "Input", Half::Blue, std::to_string(index) + "/" + std::to_string(total),
                  fit({}, SeamFit::BlueRect));
    const std::string lit = row->input;
    {
        Box b = fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect);
        b.hug = true;
        ui.leaf(
            "kv/pad", b, [](float max_w) { const float w = std::min(330.f, max_w); return Vec2{w, 176 * w / 330}; },
            [lit, capturing](PaintContext& ctx) { paint_pad(ctx, lit, capturing); });
    }
    {
        auto r = ui.open("kv/name", fit(Box{.layout = Layout::Row, .margin = {0, 0, 0, 10}, .gap = 16,
                                            .align = Align::Center},
                                        SeamFit::BlueRect));
        text(ui, "kv/title", TextSpec{.text = row->full, .style = tx::kBig, .chroma = 3, .autofit_min = 24},
             Box{.shrink_order = 1});
        const std::string cap = capturing ? std::string("?") : row->keycap.label;
        TextEngine& te = ui.text();
        ui.leaf(
            "kv/cap", Box{.h = Size::fixed(44)},
            [&te, cap](float) { return Vec2{std::max(56.f, te.width(tx::kKeyCapBig, cap) + 30), 44}; },
            [cap, capturing](PaintContext& ctx) {
                const Rect r = ctx.rect;
                surface(ctx.canvas, r, capturing ? rgba(255, 200, 67, .25f) : rgba(255, 255, 255, .08f),
                        capturing ? c::kWarn : rgba(255, 255, 255, .4f));
                const float w = ctx.text.width(tx::kKeyCapBig, cap);
                ctx.text.draw(ctx.canvas, tx::kKeyCapBig, cap,
                              {r.center().x - w / 2, r.y + (r.h - ctx.text.line_height(tx::kKeyCapBig)) / 2},
                              rgb(0xffffff));
            });
    }
    if (capturing) {
        // The capture band: what to press, what stops it, the countdown.
        const double left = std::max(0.0, kCaptureSeconds - (ui.now() - capture_since_));
        auto band = ui.open(
            "kv/capture",
            fit(Box{.pad = {18, 12, 18, 12}, .margin = {0, 0, 0, 10}, .gap = 6}, SeamFit::BlueSkewed),
            [](PaintContext& ctx) {
                surface(ctx.canvas, ctx.rect, rgba(255, 200, 67, .14f), rgba(255, 200, 67, .7f));
            });
        text(ui, "kv/cap-title", TextSpec{"Press a key", tx::kExplainTitle, c::kWarn});
        const m::KeyCapture& keys = model_->keys();
        const std::string now_key = keys.label(keys.keymap().key(input_index(row->input)));
        text(ui, "kv/cap-text",
             TextSpec{.text = "For " + row->full + ". A key another input has is swapped with it. Esc (or the pad's B) "
                              "keeps " + now_key + ".",
                      .style = tx::kParaSmall, .color = c::kBlueDim, .wrap = true});
        const float share = static_cast<float>(left / kCaptureSeconds);
        ui.leaf("kv/cap-bar", Box{.h = Size::fixed(6), .margin = {0, 4, 0, 0}}, {}, [share](PaintContext& ctx) {
            const Rect r = ctx.rect;
            ctx.canvas.fill_rect(r, rgba(255, 200, 67, .18f));
            // (It empties toward the seam side: the right edge is the half's straight one.)
            ctx.canvas.fill_rect({r.right() - r.w * share, r.y, r.w * share, r.h}, c::kWarn);
            ctx.animate();
        });
        text(ui, "kv/cap-left",
             TextSpec{std::to_string(static_cast<int>(std::ceil(left))) + " s", tx::kKick, c::kWarn});
    } else {
        text(ui, "kv/explain",
             TextSpec{.text = "Enter, then press the key for it. " + sv.keys_about, .style = tx::kPara,
                      .color = c::kBlueDim, .wrap = true},
             fit(Box{.margin = {0, 0, 0, 6}}, SeamFit::BlueRect));
    }
    if (!row->note.empty())
        note(ui, "kv/note", row->note_tone == m::Tone::kError ? Tone::Bad : Tone::Ok, row->note,
             fit(Box{.margin = {0, 0, 0, 8}}, SeamFit::BlueRect),
             row->note_tone == m::Tone::kError ? "stroke:warn" : "stroke:check");
    text(ui, "kv/f11",
         TextSpec{.text = "F11 and Super stay with the game and the desktop.", .style = tx::kParaSmall,
                  .color = c::kBlueFaint, .wrap = true},
         fit(Box{.margin = {0, 0, 0, 10}}, SeamFit::BlueRect));
    auto b = ui.open("kv/btns", fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
    for (const m::Action& a : sv.keys_actions) {
        ButtonSpec bs;
        bs.label = a.label;
        bs.size = ButtonSize::Small;
        bs.kind = a.flat ? ButtonKind::Ghost : ButtonKind::Blue;
        bs.disabled = !a.enabled;
        button(ui, a.id, bs, blue_focus(!a.enabled));
    }
}

// Windows' Settings > Folders: the folder's now and its default, Browse… (the controller's folder browser), Default.
void App::folder_view(const m::SettingsView& sv, const std::string& key) {
    Ui& ui = *ui_;
    const m::FolderRow* row = nullptr;
    int index = 0;
    for (size_t i = 0; i < sv.folders.size(); ++i)
        if (sv.folders[i].key == key) row = &sv.folders[i], index = static_cast<int>(i) + 1;
    if (!row) return;
    section_label(ui, "fv/label", "Folders", Half::Blue,
                  std::to_string(index) + "/" + std::to_string(sv.folders.size()), fit({}, SeamFit::BlueRect));
    text(ui, "fv/title", TextSpec{.text = row->name, .style = tx::kBig, .chroma = 3, .autofit_min = 24},
         fit({}, SeamFit::BlueRect));
    text(ui, "fv/hint", TextSpec{.text = row->hint + ".", .style = tx::kPara, .color = c::kBlueDim, .wrap = true},
         fit(Box{.margin = {0, 8, 0, 10}}, SeamFit::BlueRect));
    const std::string def = folder_default(key);
    const Fact list[] = {{"Now", {{row->value.empty() ? std::string("Not set") : row->value, rgb(0xdbe3f1)}}},
                         {"Default", {{def.empty() ? std::string("None") : def, rgb(0xdbe3f1)}}}};
    facts(ui, "fv/facts", list, fit(Box{.margin = {0, 0, 0, 12}}, SeamFit::BlueRect));
    auto b = ui.open("fv/btns", fit(Box{.layout = Layout::Row, .gap = 12, .wrap = true}, SeamFit::BlueRect));
    ButtonSpec browse;
    browse.label = "Browse…";
    browse.kind = ButtonKind::Blue;
    browse.size = ButtonSize::Small;
    button(ui, row->browse.id, browse, blue_focus());
    ButtonSpec d;
    d.label = "Default";
    d.size = ButtonSize::Small;
    d.disabled = def.empty() || def == row->value;
    button(ui, "folder-default:" + key, d, blue_focus(d.disabled));
}

// A Change (Left / Right, or a click on an arrow) on a Settings row.
void App::settings_change(const std::string& id, int delta) {
    const m::Action* a = action(id);
    if (!a || !a->enabled) return;
    settings_slide_ = delta < 0 ? -1 : 1;
    if (a->kind == m::ActionKind::kSwitch) handle(model_->activate(id, now()));
    else if (a->kind == m::ActionKind::kChoice && !a->choices.empty()) {
        const int n = static_cast<int>(a->choices.size());
        handle(model_->choose(id, ((a->chosen < 0 ? 0 : a->chosen) + delta + n) % n, now()));
    } else {
        return;
    }
    cue(ttt2::app::Cue::Toggle);
    apply_launcher_settings();
}

// Accept on a Settings item.
bool App::settings_activate(const std::string& id, ttt2::ui::Device device) {
    if (id.starts_with("sec:")) {
        settings_switch(0, id.substr(4));
        return true;
    }
    if (id.starts_with("key:")) {
        const int input = input_index(id.substr(4));
        if (input < 0) return true;
        const m::Device d = device == ttt2::ui::Device::Gamepad ? m::Device::kPad
                            : device == ttt2::ui::Device::Mouse ? m::Device::kMouse
                                                                : m::Device::kKeyboard;
        model_->pick_key(input, d, now());
        if (model_->keys().picking() >= 0) {
            router_.begin_capture(device == ttt2::ui::Device::None ? ttt2::ui::Device::Keyboard : device, now());
            capture_since_ = now();
            if (o_.trace_cues) std::fprintf(stderr, "@capture start %s\n", id.c_str());
        } else {
            router_.end_capture();
        }
        return true;
    }
    if (id.starts_with("fold:")) {
        drill_in(id, "folder:" + id.substr(5));
        return true;
    }
    if (id.starts_with("folder-default:")) {
        const std::string key = id.substr(15);
        set_folder(key, folder_default(key));
        return true;
    }
    if (const m::Action* a = action(id); a && (a->kind == m::ActionKind::kSwitch || a->kind == m::ActionKind::kChoice)) {
        handle(model_->activate(id, now()));
        settings_slide_ = 1;
        apply_launcher_settings();
        return true;
    }
    return false;
}

// Choosing a key: the router hands the keys over (U4), the model takes them; 10 s without one stops it.
void App::key_capture_tick(double t) {
    if (!router_.capturing()) return;
    bool keyed = false;
    for (const CaptureEvent& e : router_.take_capture()) {
        switch (e.kind) {
        case CaptureEvent::Key:
            model_->key_down(e.scancode, false, t);
            keyed = true;
            break;
        case CaptureEvent::KeyUp: model_->key_up(e.scancode, t); break;
        case CaptureEvent::CancelByPad:
        case CaptureEvent::CancelByMouse: model_->cancel_key(); break;
        }
    }
    // A key it refused (F11, Super, one that cannot be used): its note on the row, choosing goes on.
    if (keyed && model_->keys().picking() >= 0 && !model_->keys().taken().ok &&
        !model_->keys().taken().text.starts_with("no key"))
        cue(ttt2::app::Cue::Refuse);
    if (model_->keys().picking() >= 0 && t - capture_since_ > kCaptureSeconds) model_->cancel_key();
    if (model_->keys().picking() < 0 || screen_ != Screen::kSettings || settings_section_ != "keyboard") {
        if (model_->keys().picking() >= 0) model_->cancel_key();
        router_.end_capture();
        const m::KeyCapture::Taken& taken = model_->keys().taken();
        if (o_.trace_cues)
            std::fprintf(stderr, "@capture end %s\n", taken.text.empty() ? "kept" : taken.text.c_str());
        const bool kept = taken.text.empty() || taken.text.starts_with("no key") ||
                          taken.text.starts_with("cancelled") || taken.text.starts_with("choosing");
        cue(taken.ok ? ttt2::app::Cue::Accept : kept ? ttt2::app::Cue::Back : ttt2::app::Cue::Refuse);
    }
}

} // namespace launcher::app

namespace launcher::app {

// Windows' Settings > Folders: a folder's default (what --query state said), "" when it has none.
std::string App::folder_default(const std::string& key) const {
    const auto it = folder_defaults_.find(key);
    return it == folder_defaults_.end() ? std::string() : it->second;
}

void App::set_folder(const std::string& key, const std::string& value) {
    if (value.empty()) return;
    model_->mutable_facts().windows.folders[key] = value;
    folders_changed_ = true;
    cue(ttt2::app::Cue::Toggle);
}

} // namespace launcher::app
