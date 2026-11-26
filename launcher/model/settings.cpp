#include "settings.h"

#include "host/game_settings.h"

#include <algorithm>
#include <iterator>

namespace launcher::model {

// ---------------------------------------------------------------- game.ini

namespace {

// The next and the previous character's start in UTF-8 text (a name read from a file may have any).
size_t next_char(const std::string& s, size_t at) {
    if (at >= s.size()) return s.size();
    ++at;
    while (at < s.size() && (static_cast<unsigned char>(s[at]) & 0xC0) == 0x80) ++at;
    return at;
}

size_t previous_char(const std::string& s, size_t at) {
    if (at == 0) return 0;
    --at;
    while (at > 0 && (static_cast<unsigned char>(s[at]) & 0xC0) == 0x80) --at;
    return at;
}

size_t char_count(const std::string& s) {
    size_t n = 0;
    for (size_t at = 0; at < s.size(); at = next_char(s, at)) ++n;
    return n;
}

// The GamePad inputs' words (keymap.h's Input: group, name, full) in the launcher's language; the buttons' own names
// (L, ZR, HOME) as they are.
std::string input_text(std::string_view english) {
    if (english == "D-pad") return tr("input.dpad", "D-pad");
    if (english == "Face buttons") return tr("input.face_buttons", "Face buttons");
    if (english == "Shoulders") return tr("input.shoulders", "Shoulders");
    if (english == "Left stick") return tr("input.left_stick", "Left stick");
    if (english == "System") return tr("input.system", "System");
    if (english == "Up") return tr("input.up", "Up");
    if (english == "Down") return tr("input.down", "Down");
    if (english == "Left") return tr("input.left", "Left");
    if (english == "Right") return tr("input.right", "Right");
    if (english == "Top button") return tr("input.top_button", "Top button");
    if (english == "Bottom button") return tr("input.bottom_button", "Bottom button");
    if (english == "Left button") return tr("input.left_button", "Left button");
    if (english == "Right button") return tr("input.right_button", "Right button");
    if (english == "+ (Start)") return tr("input.plus", "+ (Start)");
    if (english == "\u2212 (Select)") return tr("input.minus", "\u2212 (Select)");
    if (english == "D-pad Up") return tr("input.dpad_up", "D-pad Up");
    if (english == "D-pad Down") return tr("input.dpad_down", "D-pad Down");
    if (english == "D-pad Left") return tr("input.dpad_left", "D-pad Left");
    if (english == "D-pad Right") return tr("input.dpad_right", "D-pad Right");
    if (english == "Left stick Up") return tr("input.stick_up", "Left stick Up");
    if (english == "Left stick Down") return tr("input.stick_down", "Left stick Down");
    if (english == "Left stick Left") return tr("input.stick_left", "Left stick Left");
    if (english == "Left stick Right") return tr("input.stick_right", "Left stick Right");
    return std::string(english);
}

std::string input_full(const Input& input) { return input_text(input.full); }

// Why a key cannot be chosen (keymap.cpp's Bound::why) in the launcher's language.
std::string key_refusal(int usage, const std::string& why) {
    if (usage == 68) return tr("keys.f11", "F11 toggles full screen");
    if (usage == kEscape) return tr("keys.esc", "Esc stops choosing a key");
    if (usage == 227 || usage == 231) return tr("keys.super", "Super is the desktop's key");
    if (why == "This key cannot be used") return tr("keys.unusable", "This key cannot be used");
    return why;
}

} // namespace

void GameController::load() {
    const game_ini::Loaded loaded = game_ini::load(file_);
    log_ = loaded.log;
    settings_ = loaded.settings;
    shown_.clear();
    language_ = std::string(cafe::host::game::kLanguages[0].code);
    error_.clear();
    note_.clear();
    language_note_.clear();
    unreadable_ = !loaded.error.empty();
    if (unreadable_) {
        note_ = tr("settings.game_ini_unreadable",
                   "game.ini cannot be read ({why}): the game shows its own name (Player in English) and its texts in "
                   "English. Saving a name or choosing a language here writes it anew.",
                   {{"why", unreadable_reason(loaded.error, file_)}});
        return;
    }
    // (What the game makes of the file: its own reader's, so what is shown here is what it shows.)
    const cafe::host::game::Settings game = cafe::host::game::parse(loaded.text).settings;
    shown_ = game.player_name;
    language_ = std::string(cafe::host::game::language_of(game).code);
    if (!settings_.player_name.empty() && shown_ != settings_.player_name)
        note_ = shown_.empty()
                    ? tr("settings.name_shows_own", "game.ini's player name “{name}” shows in the game as its own "
                                                    "name. Saving a name here replaces it.",
                         {{"name", settings_.player_name}})
                    : tr("settings.name_shows_as", "game.ini's player name “{name}” shows in the game as “{shown}”. "
                                                   "Saving a name here replaces it.",
                         {{"name", settings_.player_name}, {"shown", shown_}});
    if (!settings_.language.empty() && !cafe::host::game::find_language(settings_.language))
        language_note_ = tr("settings.language_unknown", "game.ini's language “{code}” is not one the game has: the "
                                                         "game shows English. Choosing one here replaces it.",
                            {{"code", settings_.language}});
}

bool GameController::set_name(std::string_view name) {
    const std::string tidy = game_ini::tidy_name(name);
    std::string error;
    if (!game_ini::save_name(file_, tidy, &error)) {
        // (What is shown is what the game reads.)
        error_ = tr("settings.name_not_saved", "The player name cannot be saved: {error}", {{"error", error}});
        return false;
    }
    settings_.player_name = tidy;
    shown_ = cafe::host::game::clean_name(tidy);
    error_.clear();
    note_.clear(); // (the file is what is shown now)
    if (unreadable_) {
        // (Written anew: its language is the game's own now.)
        unreadable_ = false;
        settings_.language.clear();
        language_ = std::string(cafe::host::game::kLanguages[0].code);
    }
    return true;
}

bool GameController::set_language(std::string_view code) {
    const cafe::host::game::Language* language = cafe::host::game::find_language(code);
    if (!language) {
        error_ = tr("settings.no_such_language", "The language cannot be saved: the game has no language “{code}”.",
                    {{"code", std::string(code)}});
        return false;
    }
    std::string error;
    if (!game_ini::save_language(file_, language->code, &error)) {
        // (What is shown is what the game reads.)
        error_ = tr("settings.language_not_saved", "The language cannot be saved: {error}", {{"error", error}});
        return false;
    }
    if (unreadable_) {
        // (Written anew: no name in it now.)
        unreadable_ = false;
        note_.clear();
        settings_.player_name.clear();
        shown_.clear();
    }
    settings_.language = std::string(language->code);
    language_ = settings_.language;
    error_.clear();
    language_note_.clear(); // (the file is what is shown now)
    return true;
}

std::string game_summary(const game_ini::Settings& s) {
    return s.player_name.empty() ? std::string("game.ini: no player name")
                                 : "game.ini: player name " + s.player_name;
}

std::string language_summary(const game_ini::Settings& s) {
    return s.language.empty() ? std::string("game.ini: no language") : "game.ini: language " + s.language;
}

void NameEditor::begin(std::string_view name, double now) {
    (void)now;
    editing_ = true;
    draft_ = std::string(name);
    caret_ = draft_.size();
    refusal_.clear();
    edited();
}

void NameEditor::stop() {
    editing_ = false;
    refusal_.clear();
}

void NameEditor::type(std::string_view text, double now) {
    const std::string in(text);
    bool changed = false;
    for (size_t at = 0; at < in.size();) {
        const size_t to = next_char(in, at);
        const std::string one = in.substr(at, to - at);
        at = to;
        if (!game_ini::first_refused(one).empty()) {
            const auto b = static_cast<unsigned char>(one[0]);
            refuse(b < 0x20 || b == 0x7F
                       ? tr("settings.name_control", "A control character cannot be in a name.")
                       : tr("settings.name_refused", "“{character}” cannot be in a name.", {{"character", one}}),
                   now);
            continue;
        }
        if (char_count(draft_) >= game_ini::kNameMost) {
            refuse(trn("settings.name_most", static_cast<long long>(game_ini::kNameMost),
                       "A name has {n} character at most.", "A name has {n} characters at most."),
                   now);
            break;
        }
        draft_.insert(caret_, one);
        caret_ += one.size();
        changed = true;
    }
    if (changed) edited();
}

void NameEditor::key(char c, double now) {
    if (c >= 'a' && c <= 'z' && shifted_) c = static_cast<char>(c - 'a' + 'A');
    type(std::string_view(&c, 1), now);
}

void NameEditor::backspace() {
    if (caret_ == 0) return;
    const size_t from = previous_char(draft_, caret_);
    draft_.erase(from, caret_ - from);
    caret_ = from;
    edited();
}

void NameEditor::erase_next() {
    if (caret_ >= draft_.size()) return;
    draft_.erase(caret_, next_char(draft_, caret_) - caret_);
    edited();
}

void NameEditor::clear() {
    draft_.clear();
    caret_ = 0;
    edited();
}

void NameEditor::left() { caret_ = previous_char(draft_, caret_); }
void NameEditor::right() { caret_ = next_char(draft_, caret_); }

void NameEditor::refuse(std::string why, double now) {
    refusal_ = std::move(why);
    refusal_until_ = now + kRefusalSeconds;
}

void NameEditor::tick(double now) {
    if (!refusal_.empty() && now >= refusal_until_) refusal_.clear();
}

// ---------------------------------------------------------------- display.ini

void DisplayController::load() {
    const display::Loaded loaded = display::load(file_);
    log_ = loaded.log;
    if (!loaded.error.empty()) log_.push_back("display: " + loaded.error);
    settings_ = loaded.settings;
    note_ = loaded.error.empty() ? std::string()
                                 : tr("settings.display_unreadable", "display.ini cannot be read ({why}): the game "
                                                                     "uses its defaults. Changing a setting here "
                                                                     "writes it anew.",
                                      {{"why", unreadable_reason(loaded.error, file_)}});
    error_.clear();
}

bool DisplayController::change(const display::Settings& wanted) {
    if (wanted == settings_) return true;
    std::string error;
    if (save_display(file_, wanted, &error)) {
        settings_ = wanted;
        error_.clear();
        note_.clear(); // (the file is what is shown now)
        return true;
    }
    // (What is shown is what the game reads.)
    error_ = tr("settings.display_not_saved", "The display settings cannot be saved: {error}", {{"error", error}});
    return false;
}

bool DisplayController::set(std::string_view id, int value) {
    display::Settings wanted = settings_;
    if (id == "fullscreen")
        wanted.fullscreen = value != 0;
    else if (id == "interpolation")
        wanted.interpolation = value != 0;
    else if (id == "input-delay")
        wanted.input_delay = value != 0;
    else if (id == "async-shaders")
        wanted.async_shaders = value != 0;
    else if (id == "precompile-shaders")
        wanted.precompile_shaders = value != 0;
    else if (id == "resolution" && value >= 0 && static_cast<size_t>(value) < std::size(display::kResolutions)) {
        wanted.resolution = display::kResolutions[value];
    } else {
        return false;
    }
    return change(wanted);
}

bool DisplayController::performance() {
    display::Settings wanted = settings_;
    wanted.resolution = display::Resolution::k720;
    wanted.interpolation = false;
    return change(wanted);
}

display::Settings DisplayController::read() const { return display::load(file_).settings; }

std::string display_summary(const display::Settings& s) {
    return std::string("display.ini: fullscreen ") + (s.fullscreen ? "yes" : "no") + ", resolution " +
           std::string(display::name_of(s.resolution)) + ", interpolation " + (s.interpolation ? "yes" : "no") +
           ", input delay " + (s.input_delay ? "yes" : "no") + ", shaders in the background " +
           (s.async_shaders ? "yes" : "no") + ", shaders prepared " + (s.precompile_shaders ? "yes" : "no");
}

// ---------------------------------------------------------------- keyboard.ini

std::string us_key_label(int usage) {
    const Key* key = key_by_usage(usage);
    return key && key->typed ? std::string(key->name) : key_name(usage);
}

int usage_of_xkb(int keycode) {
    const Key* key = keycode >= 8 ? key_by_evdev(keycode - 8) : nullptr;
    return key ? key->usage : 0;
}

std::string KeyCapture::label(int usage) const {
    std::string text = label_ ? label_(usage) : std::string();
    return text.empty() ? us_key_label(usage) : text;
}

void KeyCapture::load() {
    stop();
    Keymap::Notes notes;
    keymap_ = store_.load(&notes);
    as_shown_ = notes.as_shown();
    note_.clear();
    error_.clear();
    if (!notes.error.empty()) {
        note_ = tr("settings.keyboard_unreadable", "keyboard.ini cannot be read ({why}): the game uses its default "
                                                   "keys, shown here. Choosing a key, or Restore Defaults, writes the "
                                                   "file anew.",
                   {{"why", notes.error}});
    } else if (!notes.shared.empty()) {
        std::string keys;
        for (size_t i = 0; i < notes.shared.size(); ++i) keys += (i ? "; " : "") + notes.shared[i];
        note_ = tr("settings.keyboard_shared", "keyboard.ini, changed by hand, gives a key to two inputs, which the "
                                               "game presses together ({keys}). Here each input has a key of its own: "
                                               "choosing a key, or Restore Defaults, saves them as shown.",
                   {{"keys", keys}});
    }
}

void KeyCapture::pick(int input, Device device, double now) {
    if (input < 0 || input >= kInputs) return;
    const bool again = picking_ == input;
    stop();
    if (again) return;
    picking_ = input;
    modifier_ = 0;
    pressed_since_.clear();
    taken_ = {false, "no key was taken yet"};
    // (Started from the pad: the keyboard's keys of that moment are not the player's choice.)
    keyboard_from_ = device == Device::kPad ? now + kIgnoreAfterPad : now;
}

void KeyCapture::stop() {
    modifier_ = 0;
    if (picking_ < 0) return;
    const int input = picking_;
    picking_ = -1;
    // (A refusal's message goes with it.)
    if (const auto it = rows_.find(input); it != rows_.end() && it->second.tone == Tone::kError) rows_.erase(it);
}

bool KeyCapture::key_down(int usage, bool repeat, double now) {
    const bool fresh = held_.insert(usage).second;
    if (picking_ < 0) return false;
    // (The key that clicked the keycap, held, repeats: it is not taken.)
    if (repeat || !fresh) return true;
    if (now < keyboard_from_) return true;
    pressed_since_.insert(usage);
    // Ctrl, Shift, Alt or Super held with another key: a shortcut (Alt+Tab,
    // Ctrl+Q), the desktop's or the window's, not a key for the game.
    // Choosing stops, and the key goes on.
    if (std::any_of(held_.begin(), held_.end(), [&](int u) { return u != usage && u >= 224 && u <= 231; })) {
        stop();
        taken_ = {false, "choosing a key stopped: a shortcut"};
        return false;
    }
    // A modifier alone is taken once it is let go (pressed first, it may be
    // the start of a shortcut).
    if (modifier_key(usage)) {
        modifier_ = usage;
        return true;
    }
    take(usage, now);
    return true;
}

void KeyCapture::key_up(int usage, double now) {
    held_.erase(usage);
    // (A key let go that was pressed before choosing started is not taken.)
    const bool ours = pressed_since_.erase(usage) > 0;
    if (modifier_ != usage) return;
    modifier_ = 0;
    if (picking_ >= 0 && ours) take(usage, now);
}

void KeyCapture::take(int usage, double now) {
    const int input = picking_;
    if (input < 0) {
        taken_ = {false, "no key is being chosen"};
        return;
    }
    if (usage == kEscape) {
        stop();
        taken_ = {false, "cancelled with Esc"};
        return;
    }
    const Keymap before = keymap_;
    const Keymap::Bound bound =
        key_by_usage(usage) ? keymap_.bind(input, usage) : Keymap::Bound{false, -1, "This key cannot be used"};
    if (!bound.ok) {
        note_row(input, key_refusal(usage, bound.why), Tone::kError, false, kRefusalSeconds, now);
        taken_ = {false, bound.why};
        return;
    }
    picking_ = -1;
    modifier_ = 0;
    if (!save(before)) {
        taken_ = {false, error_};
        return;
    }
    rows_.erase(input); // (an older message of its own is not about this key: gone)
    std::string text = std::string(inputs()[input].full) + " is " + label(usage);
    if (bound.swapped >= 0) {
        note_row(bound.swapped, tr("settings.swapped_with", "Swapped with {input}", {{"input", input_full(inputs()[input])}}),
                 Tone::kOk, true, kSwappedSeconds, now);
        text += std::string(", swapped with ") + inputs()[bound.swapped].full;
    }
    taken_ = {true, text};
}

void KeyCapture::restore(double now) {
    stop();
    const Keymap before = keymap_;
    keymap_.reset();
    if (!save(before)) return;
    // (The rows that changed show it for a moment.)
    for (int i = 0; i < kInputs; ++i) {
        if (before.key(i) != keymap_.key(i)) note_row(i, "", Tone::kNormal, true, kRestoredSeconds, now);
    }
}

bool KeyCapture::save(const Keymap& before) {
    std::string error;
    if (store_.save(keymap_, &error)) {
        error_.clear();
        as_shown_ = true; // (the file is what is shown now)
        note_.clear();
        return true;
    }
    // (What is shown is what the game has.)
    keymap_ = before;
    error_ = tr("settings.keys_not_saved", "The keys cannot be saved: {error}", {{"error", error}});
    return false;
}

void KeyCapture::note_row(int input, std::string text, Tone tone, bool flash, double seconds, double now) {
    rows_[input] = RowNote{std::move(text), tone, flash, now + seconds};
}

void KeyCapture::tick(double now) {
    for (auto it = rows_.begin(); it != rows_.end();) {
        it = it->second.until <= now ? rows_.erase(it) : std::next(it);
    }
}

// ---------------------------------------------------------------- the page

namespace {

SettingRow setting(std::string id, ActionKind kind, std::string name, std::string about, bool on) {
    SettingRow r;
    r.name = name;
    r.about = about;
    r.control.id = std::move(id);
    r.control.kind = kind;
    r.control.checked = on;
    r.control.describe.title = std::move(name);
    r.control.describe.state = kind == ActionKind::kSwitch ? (on ? tr("common.on", "On") : tr("common.off", "Off"))
                                                           : std::string();
    r.control.describe.explain = std::move(about);
    return r;
}

Line warning_note(const std::string& text) {
    Line l = note_line(Icon::kWarning, text, true);
    return l;
}

struct FolderText {
    const char* key;
    std::string name, hint;
};
std::vector<FolderText> folder_texts() {
    return {
        {"source", tr("folders.source", "Wii U archive"), tr("folders.source_hint", "Your European Wii U .wua with update v16")},
        {"title", tr("folders.title", "Extracted Wii U title"),
         tr("folders.title_hint", "For development imports, instead of an installed game")},
        {"install", tr("folders.install", "Installation folder"),
         tr("folders.install_hint", "Where Set Up Game installs the game")},
        {"data", tr("folders.data", "Data folder"),
         tr("folders.data_hint", "Settings, logs and saves: its name ends in TTT2Ultimate")},
        {"packs", tr("folders.packs", "Fighter packs"), tr("folders.packs_hint", "The characters added to the game")},
        {"saves", tr("folders.saves", "Save files"), tr("folders.saves_hint", "The game's saves")},
        {"tools", tr("folders.tools", "Build tools"),
         tr("folders.tools_hint", "The compiler and libraries Set Up Game downloads")},
    };
}

// The on-screen keyboard for typing the name with a pad: digits, letters, - and ., Shift and Delete, then Cancel,
// Space and Done (every row ten key widths).
std::vector<std::vector<NameKey>> name_keys(bool shifted) {
    const auto key = [](std::string id, std::string label, int span = 1) {
        NameKey k;
        k.key.id = std::move(id);
        k.key.label = label;
        k.key.describe.title = std::move(label);
        k.span = span;
        return k;
    };
    std::vector<std::vector<NameKey>> rows;
    for (const std::string_view line : {"1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm."}) {
        std::vector<NameKey> row;
        if (line == "zxcvbnm.") row.push_back(key("name:shift", tr("name.shift", "Shift")));
        for (const char c : line) {
            const char shown = shifted && c >= 'a' && c <= 'z' ? static_cast<char>(c - 'a' + 'A') : c;
            row.push_back(key("name-key:" + std::string(1, c), std::string(1, shown)));
        }
        if (line == "zxcvbnm.") row.push_back(key("name:backspace", tr("name.delete", "Delete")));
        rows.push_back(std::move(row));
    }
    rows.push_back({key("name:cancel", tr("common.cancel", "Cancel"), 2), key("name:space", tr("name.space", "Space"), 5),
                    key("name:done", tr("name.done", "Done"), 3)});
    rows.back().back().key.primary = true;
    return rows;
}

} // namespace

SettingsView settings_view(const Facts& facts, const SettingsInput& in) {
    SettingsView v;
    const bool installed = facts.install.state == InstallState::kInstalled;
    // Game: the player's name (game.ini) and the input delay (display.ini). As the display's, when the game is
    // installed (Windows: also before).
    if (in.game && (installed || facts.caps.windows)) {
        const GameController& g = *in.game;
        if (!g.error().empty()) v.game_notes.push_back(text_line(g.error(), Tone::kError));
        if (!g.note().empty()) v.game_notes.push_back(warning_note(g.note()));
        if (!g.language_note().empty()) v.game_notes.push_back(warning_note(g.language_note()));
        const std::string& name = g.shown();
        // The game's own name in its language, where the launcher's font can draw it.
        const std::string own(game_ini::own_name(g.language()));
        SettingRow player = setting("player-name", ActionKind::kEntry, tr("settings.player_name", "Player name"),
                                    tr("settings.player_name_about", "The name the game shows for you, in place of "
                                                                     "Player."),
                                    false);
        player.control.label = name;
        player.control.placeholder = own.empty() ? tr("settings.name_placeholder", "Game's own") : own;
        player.control.describe.state = !name.empty() ? name
                                        : own.empty() ? tr("settings.name_own", "The game's own (Player in English)")
                                                      : tr("settings.name_own_is", "{name} (the game's own)",
                                                           {{"name", own}});
        const std::string rule =
            tr("common.two_sentences", "{first} {second}",
               {{"first", game_ini::name_rule()},
                {"second", tr("settings.name_empty", "Left empty, the game's own name in its language (Player in "
                                                     "English).")}});
        player.notes.push_back(text_line(rule, Tone::kDim, true));
        player.control.describe.more.push_back(rule);
        v.game.push_back(player);
        // The language of the game's texts: its languages each by its own name, the one the game will show chosen.
        SettingRow language = setting("language", ActionKind::kChoice, tr("settings.language", "Language"),
                                      tr("settings.language_about", "The game's texts and menus show in this "
                                                                    "language."),
                                      false);
        for (const cafe::host::game::Language& l : cafe::host::game::kLanguages) {
            const i18n::Language* own_name = i18n::find_language(l.code);
            language.control.choices.push_back(std::string(own_name ? own_name->name : l.name));
        }
        const cafe::host::game::Language* chosen = cafe::host::game::find_language(g.language());
        language.control.chosen = chosen ? static_cast<int>(chosen - std::begin(cafe::host::game::kLanguages)) : 0;
        language.control.describe.state = language.control.choices[static_cast<size_t>(language.control.chosen)];
        v.game.push_back(language);
        if (in.display) {
            const DisplayController& d = *in.display;
            // (display.ini's: what is said of it goes with its setting here too.)
            if (!d.error().empty()) v.game_notes.push_back(text_line(d.error(), Tone::kError));
            if (!d.note().empty()) v.game_notes.push_back(warning_note(d.note()));
            v.game.push_back(setting("input-delay", ActionKind::kSwitch, tr("settings.input_delay", "Input delay"),
                                     tr("settings.input_delay_about",
                                        "Two frames between a button press and the game acting on it, as on the Wii "
                                        "U. Practice's own Input Delay works either way."),
                                     d.settings().input_delay));
        }
        if (in.name && in.name->editing()) {
            const NameEditor& e = *in.name;
            NameEditView edit;
            edit.draft = e.draft();
            edit.caret = e.caret();
            edit.placeholder = player.control.placeholder;
            edit.count = std::to_string(char_count(e.draft())) + "/" + std::to_string(game_ini::kNameMost);
            edit.refusal = e.refusal();
            edit.rule = rule;
            edit.shifted = e.shifted();
            edit.keys = name_keys(e.shifted());
            v.name_edit = std::move(edit);
        }
    }
    // The game's settings: when it is installed (Windows: also before, its files are in the data folder).
    if (in.display && (installed || facts.caps.windows)) {
        const DisplayController& d = *in.display;
        const display::Settings& s = d.settings();
        if (!d.error().empty()) v.display_notes.push_back(text_line(d.error(), Tone::kError));
        if (!d.note().empty()) v.display_notes.push_back(warning_note(d.note()));
        v.display.push_back(setting("fullscreen", ActionKind::kSwitch, tr("settings.fullscreen", "Fullscreen"),
                                    tr("settings.fullscreen_about", "Start the game fullscreen. F11 switches it in the "
                                                                    "game."),
                                    s.fullscreen));
        SettingRow resolution = setting("resolution", ActionKind::kChoice, tr("settings.resolution", "Resolution"),
                                        tr("settings.resolution_about", "The size the game draws at; the picture is "
                                                                        "scaled to the window or the screen."),
                                        false);
        for (const display::Resolution r : display::kResolutions)
            resolution.control.choices.push_back(resolution_label(r));
        resolution.control.chosen = static_cast<int>(
            std::find(std::begin(display::kResolutions), std::end(display::kResolutions), s.resolution) -
            std::begin(display::kResolutions));
        if (resolution.control.chosen < static_cast<int>(resolution.control.choices.size())) {
            resolution.control.describe.state = resolution.control.choices[resolution.control.chosen];
        }
        if (const std::string note = automatic_note(in.monitors); !note.empty()) {
            resolution.notes.push_back(text_line(note, Tone::kDim, true));
            resolution.control.describe.more.push_back(note);
        }
        v.display.push_back(resolution);
        SettingRow fps = setting("interpolation", ActionKind::kSwitch, tr("settings.fps", "120 fps"),
                                 tr("settings.fps_about", "A frame between each two of the game's 60 every second: "
                                                          "smoother motion on displays of 100 Hz and more."),
                                 s.interpolation);
        if (const std::string note = refresh_note(in.monitors); !note.empty()) {
            fps.notes.push_back(text_line(note, Tone::kDim, true));
            fps.control.describe.more.push_back(note);
        }
        v.display.push_back(fps);
        v.display.push_back(setting("async-shaders", ActionKind::kSwitch,
                                    tr("settings.async_shaders", "Shaders in the background"),
                                    tr("settings.async_shaders_about",
                                       "The first time something is shown, it may appear a few frames late instead of "
                                       "the game stopping for a moment while its shader is made."),
                                    s.async_shaders));
        v.display.push_back(setting("precompile-shaders", ActionKind::kSwitch,
                                    tr("settings.precompile", "Prepare shaders before playing"),
                                    tr("settings.precompile_about",
                                       "Play first makes ready the shaders the game has used on this PC so far, so "
                                       "that it does not stop for them again, for instance after a graphics driver "
                                       "update. What it has never shown yet is still made the first time."),
                                    s.precompile_shaders));
        if (facts.caps.performance_preset) {
            SettingRow p = setting("performance", ActionKind::kButton, tr("settings.performance", "Performance"),
                                   tr("settings.performance_about", "1280 × 720 without 120 fps: for a slower graphics "
                                                                    "card."),
                                   false);
            p.control.label = tr("settings.use", "Use");
            v.display.push_back(p);
        }
        if (facts.windows.data_problem == "name") {
            const std::string why = tr("settings.data_name", "The data folder must end in TTT2Ultimate so the game and "
                                                             "launcher share settings.");
            for (auto [notes, rows] : {std::pair{&v.display_notes, &v.display}, std::pair{&v.game_notes, &v.game}}) {
                if (rows->empty()) continue;
                notes->insert(notes->begin(), text_line(why, Tone::kError));
                for (SettingRow& r : *rows) {
                    r.control.enabled = false;
                    r.control.why = why;
                    r.control.describe.why = why;
                }
            }
            v.name_edit.reset();
        }
    }

    if (in.keys && (installed || facts.caps.windows)) {
        const KeyCapture& k = *in.keys;
        if (!k.error().empty()) v.keys_notes.push_back(text_line(k.error(), Tone::kError));
        if (!k.note().empty()) v.keys_notes.push_back(warning_note(k.note()));
        for (int i = 0; i < kInputs; ++i) {
            const Input& input = inputs()[i];
            const std::string group = input_text(input.group), full = input_full(input);
            if (v.groups.empty() || v.groups.back().id != input.group) v.groups.push_back({group, input.group, {}});
            KeyRow r;
            r.input = input.id;
            r.name = input_text(input.name);
            r.full = full;
            const std::string label = k.label(k.keymap().key(i));
            r.keycap.id = std::string("key:") + input.id;
            r.keycap.kind = ActionKind::kKeycap;
            r.keycap.checked = k.picking() == i;
            const std::string press = tr("keys.press", "Press a key…");
            r.keycap.label = r.keycap.checked ? press : label;
            r.keycap.tooltip = tr("keys.change", "Change the key for {input}", {{"input", full}});
            r.keycap.describe.title = full;
            r.keycap.describe.state = r.keycap.checked ? press : label;
            r.keycap.describe.explain =
                r.keycap.checked
                    ? tr("keys.press_for", "Press the key for {input}, or Esc to keep {key}.", {{"input", full}, {"key", label}})
                    : r.keycap.tooltip;
            if (const auto it = k.row_notes().find(i); it != k.row_notes().end()) {
                r.note = it->second.text;
                r.note_tone = it->second.tone;
                r.flash = it->second.flash;
                if (!r.note.empty()) r.keycap.describe.more.push_back(r.note);
            }
            v.groups.back().rows.push_back(r);
        }
        Action restore;
        restore.id = "restore-keys";
        restore.label = tr("keys.restore", "Restore Defaults");
        restore.enabled = k.restorable();
        restore.why = restore.enabled ? "" : tr("keys.restore_why", "The keys are the default ones.");
        restore.describe.title = restore.label;
        restore.describe.why = restore.why;
        v.keys_actions.push_back(restore);
        if (facts.caps.windows) {
            Action open;
            open.id = "open-keyboard-file";
            open.label = tr("keys.open_file", "Open keyboard.ini");
            open.flat = true;
            open.describe.title = open.label;
            v.keys_actions.push_back(open);
        }
    }

    if (facts.caps.folders) {
        v.folders_shown = true;
        for (const FolderText& f : folder_texts()) {
            FolderRow r;
            r.key = f.key;
            r.name = f.name;
            r.hint = f.hint;
            const auto it = facts.windows.folders.find(f.key);
            r.value = it != facts.windows.folders.end() ? it->second : "";
            r.browse.id = std::string("folder:") + f.key;
            r.browse.label = tr("folders.browse", "Browse…");
            r.browse.describe.title = f.name;
            r.browse.describe.explain = f.hint;
            r.browse.describe.path = r.value;
            v.folders.push_back(r);
        }
        Action save;
        save.id = "save-folders";
        save.label = tr("folders.save", "Save Folders");
        save.primary = true;
        save.enabled = !facts.task;
        save.why = facts.task ? tr("folders.save_why", "Wait for the task to end before changing folders.") : "";
        save.describe.title = save.label;
        save.describe.why = save.why;
        v.folders_actions.push_back(save);
        if (!in.folders_note.empty()) v.folders_notes.push_back(text_line(in.folders_note, Tone::kOk, true));
    }

    // The launcher's own (new).
    SettingRow sounds = setting("sounds", ActionKind::kSwitch, tr("settings.sounds", "Sounds"),
                                tr("settings.sounds_about", "Short sounds when moving between and choosing items."),
                                in.launcher.sounds);
    SettingRow motion = setting("reduce-motion", ActionKind::kSwitch, tr("settings.reduce_motion", "Reduce motion"),
                                tr("settings.reduce_motion_about", "No moving backgrounds, and pages change without "
                                                                   "sliding."),
                                in.launcher.reduce_motion);
    SettingRow prompts = setting("prompts", ActionKind::kChoice, tr("settings.prompts", "Button prompts"),
                                 tr("settings.prompts_about", "The buttons the prompts show: those of the last device "
                                                              "used, or always these."),
                                 false);
    for (const char* p : kPrompts)
        prompts.control.choices.push_back(std::string_view(p) == "Automatic" ? tr("settings.automatic", "Automatic")
                                                                             : std::string(p));
    prompts.control.chosen =
        std::clamp(in.launcher.prompts, 0, static_cast<int>(prompts.control.choices.size()) - 1);
    prompts.control.describe.state = prompts.control.choices[static_cast<size_t>(prompts.control.chosen)];
    SettingRow text = setting("text-size", ActionKind::kChoice, tr("settings.text_size", "Text size"),
                              tr("settings.text_size_about", "How large this launcher's text is."), false);
    for (const int size : kTextSizes) {
        text.control.choices.push_back(std::to_string(size) + " %");
        if (size == in.launcher.text_size) text.control.chosen = static_cast<int>(text.control.choices.size()) - 1;
    }
    if (text.control.chosen >= 0) text.control.describe.state = text.control.choices[text.control.chosen];
    // The launcher's language: the system's (the default) or one of i18n.h's, each by its own name.
    SettingRow language = setting("launcher-language", ActionKind::kChoice, tr("settings.launcher_language", "Language"),
                                  tr("settings.launcher_language_about",
                                     "The language of this launcher's texts. System: the one your system shows, when "
                                     "the launcher has it, else English."),
                                  false);
    language.control.choices.push_back(tr("settings.system_language", "System ({language})",
                                          {{"language", i18n::find_language(i18n::system_language())->name}}));
    language.control.chosen = 0;
    for (const i18n::Language& l : i18n::kLanguages) {
        language.control.choices.emplace_back(l.name);
        if (in.launcher.language == l.code) language.control.chosen = static_cast<int>(language.control.choices.size()) - 1;
    }
    language.control.describe.state = language.control.choices[static_cast<size_t>(language.control.chosen)];
    v.launcher = {language, sounds, motion, prompts, text};
    return v;
}

} // namespace launcher::model
