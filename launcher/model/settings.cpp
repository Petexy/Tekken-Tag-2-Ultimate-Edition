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

} // namespace

void GameController::load() {
    const game_ini::Loaded loaded = game_ini::load(file_);
    log_ = loaded.log;
    settings_ = loaded.settings;
    shown_.clear();
    error_.clear();
    note_.clear();
    if (!loaded.error.empty()) {
        note_ = "game.ini cannot be read (" + unreadable_reason(loaded.error, file_) +
                "): the game shows its own name (Player in English). Saving a name here writes it anew.";
        return;
    }
    // (What the game makes of the file: its own reader's, so what is shown here is what it shows.)
    shown_ = cafe::host::game::parse(loaded.text).settings.player_name;
    if (!settings_.player_name.empty() && shown_ != settings_.player_name)
        note_ = "game.ini's player name “" + settings_.player_name + "” shows in the game as " +
                (shown_.empty() ? std::string("its own name") : "“" + shown_ + "”") +
                ". Saving a name here replaces it.";
}

bool GameController::set_name(std::string_view name) {
    const std::string tidy = game_ini::tidy_name(name);
    std::string error;
    if (!game_ini::save_name(file_, tidy, &error)) {
        // (What is shown is what the game reads.)
        error_ = "The player name cannot be saved: " + error;
        return false;
    }
    settings_.player_name = tidy;
    shown_ = cafe::host::game::clean_name(tidy);
    error_.clear();
    note_.clear(); // (the file is what is shown now)
    return true;
}

std::string game_summary(const game_ini::Settings& s) {
    return s.player_name.empty() ? std::string("game.ini: no player name")
                                 : "game.ini: player name " + s.player_name;
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
            refuse((b < 0x20 || b == 0x7F ? std::string("A control character") : "\u201C" + one + "\u201D") +
                       " cannot be in a name.",
                   now);
            continue;
        }
        if (char_count(draft_) >= game_ini::kNameMost) {
            refuse("A name has " + std::to_string(game_ini::kNameMost) + " characters at most.", now);
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
                                 : "display.ini cannot be read (" + unreadable_reason(loaded.error, file_) +
                                       "): the game uses its defaults. Changing a setting here writes it anew.";
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
    error_ = "The display settings cannot be saved: " + error;
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
        note_ = "keyboard.ini cannot be read (" + notes.error +
                "): the game uses its default keys, shown here. "
                "Choosing a key, or Restore Defaults, writes the file anew.";
    } else if (!notes.shared.empty()) {
        std::string keys;
        for (size_t i = 0; i < notes.shared.size(); ++i) keys += (i ? "; " : "") + notes.shared[i];
        note_ = "keyboard.ini, changed by hand, gives a key to two inputs, which the game presses together (" + keys +
                "). Here each input has a key of its own: choosing a key, or Restore Defaults, saves them as shown.";
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
        note_row(input, bound.why, Tone::kError, false, kRefusalSeconds, now);
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
        note_row(bound.swapped, std::string("Swapped with ") + inputs()[input].full, Tone::kOk, true, kSwappedSeconds,
                 now);
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
    error_ = "The keys cannot be saved: " + error;
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
    r.control.describe.state = kind == ActionKind::kSwitch ? (on ? "On" : "Off") : "";
    r.control.describe.explain = std::move(about);
    return r;
}

Line warning_note(const std::string& text) {
    Line l = note_line(Icon::kWarning, text, true);
    return l;
}

const struct {
    const char *key, *name, *hint;
    bool folder;
} kFolders[] = {
    {"source", "Wii U archive", "Your European Wii U .wua with update v16", false},
    {"title", "Extracted Wii U title", "For development imports, instead of an installed game", true},
    {"install", "Installation folder", "Where Set Up Game installs the game", true},
    {"data", "Data folder", "Settings, logs and saves: its name ends in TTT2Ultimate", true},
    {"packs", "Fighter packs", "The characters added to the game", true},
    {"saves", "Save files", "The game's saves", true},
    {"tools", "Build tools", "The compiler and libraries Set Up Game downloads", true},
};

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
        if (line == "zxcvbnm.") row.push_back(key("name:shift", "Shift"));
        for (const char c : line) {
            const char shown = shifted && c >= 'a' && c <= 'z' ? static_cast<char>(c - 'a' + 'A') : c;
            row.push_back(key("name-key:" + std::string(1, c), std::string(1, shown)));
        }
        if (line == "zxcvbnm.") row.push_back(key("name:backspace", "Delete"));
        rows.push_back(std::move(row));
    }
    rows.push_back({key("name:cancel", "Cancel", 2), key("name:space", "Space", 5), key("name:done", "Done", 3)});
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
        const std::string& name = g.shown();
        SettingRow player = setting("player-name", ActionKind::kEntry, "Player name",
                                    "The name the game shows for you, in place of Player.", false);
        player.control.label = name;
        player.control.describe.state = name.empty() ? std::string("Player (the game's own)") : name;
        const std::string rule = game_ini::name_rule() + " Left empty, the game's own name (Player in English).";
        player.notes.push_back(text_line(rule, Tone::kDim, true));
        player.control.describe.more.push_back(rule);
        v.game.push_back(player);
        if (in.display) {
            const DisplayController& d = *in.display;
            // (display.ini's: what is said of it goes with its setting here too.)
            if (!d.error().empty()) v.game_notes.push_back(text_line(d.error(), Tone::kError));
            if (!d.note().empty()) v.game_notes.push_back(warning_note(d.note()));
            v.game.push_back(setting("input-delay", ActionKind::kSwitch, "Input delay",
                                     "Two frames between a button press and the game acting on it, as on the Wii U. "
                                     "Practice's own Input Delay works either way.",
                                     d.settings().input_delay));
        }
        if (in.name && in.name->editing()) {
            const NameEditor& e = *in.name;
            NameEditView edit;
            edit.draft = e.draft();
            edit.caret = e.caret();
            edit.placeholder = game_ini::kDefaultName;
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
        v.display.push_back(setting("fullscreen", ActionKind::kSwitch, "Fullscreen",
                                    "Start the game fullscreen. F11 switches it in the game.", s.fullscreen));
        SettingRow resolution = setting("resolution", ActionKind::kChoice, "Resolution",
                                        "The size the game draws at; the picture is scaled to the window or the "
                                        "screen.",
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
        SettingRow fps = setting("interpolation", ActionKind::kSwitch, "120 fps",
                                 "A frame between each two of the game's 60 every second: smoother motion on displays "
                                 "of 100 Hz and more.",
                                 s.interpolation);
        if (const std::string note = refresh_note(in.monitors); !note.empty()) {
            fps.notes.push_back(text_line(note, Tone::kDim, true));
            fps.control.describe.more.push_back(note);
        }
        v.display.push_back(fps);
        v.display.push_back(setting("async-shaders", ActionKind::kSwitch, "Shaders in the background",
                                    "The first time something is shown, it may appear a few frames late instead of "
                                    "the game stopping for a moment while its shader is made.",
                                    s.async_shaders));
        v.display.push_back(setting("precompile-shaders", ActionKind::kSwitch, "Prepare shaders before playing",
                                    "Play first makes ready the shaders the game has used on this PC so far, so that "
                                    "it does not stop for them again, for instance after a graphics driver update. "
                                    "What it has never shown yet is still made the first time.",
                                    s.precompile_shaders));
        if (facts.caps.performance_preset) {
            SettingRow p = setting("performance", ActionKind::kButton, "Performance",
                                   "1280 × 720 without 120 fps: for a slower graphics card.", false);
            p.control.label = "Use";
            v.display.push_back(p);
        }
        if (facts.windows.data_problem == "name") {
            const std::string why = "The data folder must end in TTT2Ultimate so the game and launcher share settings.";
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
            if (v.groups.empty() || v.groups.back().title != input.group) v.groups.push_back({input.group, {}});
            KeyRow r;
            r.input = input.id;
            r.name = input.name;
            r.full = input.full;
            const std::string label = k.label(k.keymap().key(i));
            r.keycap.id = std::string("key:") + input.id;
            r.keycap.kind = ActionKind::kKeycap;
            r.keycap.checked = k.picking() == i;
            r.keycap.label = r.keycap.checked ? "Press a key…" : label;
            r.keycap.tooltip = std::string("Change the key for ") + input.full;
            r.keycap.describe.title = input.full;
            r.keycap.describe.state = r.keycap.checked ? "Press a key…" : label;
            r.keycap.describe.explain =
                r.keycap.checked ? "Press the key for " + std::string(input.full) + ", or Esc to keep " + label + "."
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
        restore.label = "Restore Defaults";
        restore.enabled = k.restorable();
        restore.why = restore.enabled ? "" : "The keys are the default ones.";
        restore.describe.title = restore.label;
        restore.describe.why = restore.why;
        v.keys_actions.push_back(restore);
        if (facts.caps.windows) {
            Action open;
            open.id = "open-keyboard-file";
            open.label = "Open keyboard.ini";
            open.flat = true;
            open.describe.title = open.label;
            v.keys_actions.push_back(open);
        }
    }

    if (facts.caps.folders) {
        v.folders_shown = true;
        for (const auto& f : kFolders) {
            FolderRow r;
            r.key = f.key;
            r.name = f.name;
            r.hint = f.hint;
            const auto it = facts.windows.folders.find(f.key);
            r.value = it != facts.windows.folders.end() ? it->second : "";
            r.browse.id = std::string("folder:") + f.key;
            r.browse.label = "Browse…";
            r.browse.describe.title = f.name;
            r.browse.describe.explain = f.hint;
            r.browse.describe.path = r.value;
            v.folders.push_back(r);
        }
        Action save;
        save.id = "save-folders";
        save.label = "Save Folders";
        save.primary = true;
        save.enabled = !facts.task;
        save.why = facts.task ? "Wait for the task to end before changing folders." : "";
        save.describe.title = save.label;
        save.describe.why = save.why;
        v.folders_actions.push_back(save);
        if (!in.folders_note.empty()) v.folders_notes.push_back(text_line(in.folders_note, Tone::kOk, true));
    }

    // The launcher's own (new).
    SettingRow sounds = setting("sounds", ActionKind::kSwitch, "Sounds",
                                "Short sounds when moving between and choosing items.", in.launcher.sounds);
    SettingRow motion = setting("reduce-motion", ActionKind::kSwitch, "Reduce motion",
                                "No moving backgrounds, and pages change without sliding.", in.launcher.reduce_motion);
    SettingRow prompts = setting("prompts", ActionKind::kChoice, "Button prompts",
                                 "The buttons the prompts show: those of the last device used, or always these.",
                                 false);
    for (const char* p : kPrompts) prompts.control.choices.push_back(p);
    prompts.control.chosen =
        std::clamp(in.launcher.prompts, 0, static_cast<int>(prompts.control.choices.size()) - 1);
    prompts.control.describe.state = prompts.control.choices[static_cast<size_t>(prompts.control.chosen)];
    SettingRow text =
        setting("text-size", ActionKind::kChoice, "Text size", "How large this launcher's text is.", false);
    for (const int size : kTextSizes) {
        text.control.choices.push_back(std::to_string(size) + " %");
        if (size == in.launcher.text_size) text.control.chosen = static_cast<int>(text.control.choices.size()) - 1;
    }
    if (text.control.chosen >= 0) text.control.describe.state = text.control.choices[text.control.chosen];
    v.launcher = {sounds, motion, prompts, text};
    return v;
}

} // namespace launcher::model
