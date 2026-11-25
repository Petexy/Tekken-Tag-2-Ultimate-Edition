#include "settings.h"

#include <algorithm>
#include <iterator>

namespace launcher::model {

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

} // namespace

SettingsView settings_view(const Facts& facts, const SettingsInput& in) {
    SettingsView v;
    const bool installed = facts.install.state == InstallState::kInstalled;
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
        v.display.push_back(setting("input-delay", ActionKind::kSwitch, "Input delay",
                                    "Two frames between a button press and the game acting on it, as on the Wii U. "
                                    "Practice's own Input Delay works either way.",
                                    s.input_delay));
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
            v.display_notes.insert(v.display_notes.begin(), text_line(why, Tone::kError));
            for (SettingRow& r : v.display) {
                r.control.enabled = false;
                r.control.why = why;
                r.control.describe.why = why;
            }
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
