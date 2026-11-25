#pragma once

// Settings: the game's game.ini (GameController: the player's name, typed
// with NameEditor, and the language of the game's texts), display.ini
// (DisplayController: shown = saved, a save that fails puts the controls
// back), keyboard.ini (KeyCapture: choosing a key) and, new, the launcher's
// own; on Windows also the folders. The texts are the GTK app's
// (launcher/app/settings.cpp); Windows shows the same (Tk's own had drifted:
// "Cannot save: ...").

#include "facts.h"
#include "game_ini.h"
#include "view.h"

#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace launcher::model {

// ---------------------------------------------------------------- game.ini

class GameController {
public:
    explicit GameController(fs::path file = {}) : file_(std::move(file)) {}
    void set_file(fs::path file) { file_ = std::move(file); }
    const fs::path& file() const { return file_; }

    // Read game.ini (each time Settings opens): what it says and what the game makes of it (shown(), language()),
    // with a note when it cannot be read, the game shows its name differently or does not have its language.
    void load();
    // A name chosen (tidied: the spaces at both ends left out; "" the game's own): saved at once; false (error())
    // when it cannot be, what is shown staying what the file has.
    bool set_name(std::string_view name);
    // A language chosen (a code of cafe::host::game::kLanguages; English too is written): saved at once; false
    // (error()) when it cannot be, or when the game has no such language.
    bool set_language(std::string_view code);

    const game_ini::Settings& settings() const { return settings_; }
    // The name the game shows, as its own reader makes it of the file (cafe::host::game); "" for its own name.
    const std::string& shown() const { return shown_; }
    // The language the game shows its texts in, as its own reader makes it of the file: a code of kLanguages ("en"
    // for English, also when the file has none or one the game does not have).
    const std::string& language() const { return language_; }
    const std::string& note() const { return note_; } // game.ini cannot be read (...) / the game shows its name as ...
    const std::string& language_note() const { return language_note_; } // game.ini's language "xx" is not one ...
    const std::string& error() const { return error_; } // The player name / language cannot be saved: ...
    const std::vector<std::string>& log() const { return log_; }

private:
    fs::path file_;
    game_ini::Settings settings_;
    std::string shown_, language_ = "en", note_, language_note_, error_;
    bool unreadable_ = false; // note_ says game.ini cannot be read
    std::vector<std::string> log_;
};

// "game.ini: player name Mira" / "game.ini: no player name" (the test action's answer).
std::string game_summary(const game_ini::Settings& settings);
// "game.ini: language fr" / "game.ini: no language" (the test action's answer).
std::string language_summary(const game_ini::Settings& settings);

// Typing the player's name: the text so far and where the next character goes. What a name cannot have is not
// taken (its refusal said for a moment); the on-screen keyboard's letters are capitals while shifted (by its Shift,
// once; and at the start of an empty name).
class NameEditor {
public:
    static constexpr double kRefusalSeconds = 3;

    void begin(std::string_view name, double now);
    void stop();
    bool editing() const { return editing_; }

    // Text typed (the keyboard's text, a paste, an on-screen key), at the caret.
    void type(std::string_view text, double now);
    // An on-screen letter or character key (its id's character): a capital while shifted.
    void key(char c, double now);
    void backspace();
    void erase_next();
    void clear();
    void left();
    void right();
    void home() { caret_ = 0; }
    void end() { caret_ = draft_.size(); }
    void shift() { shifted_ = !shifted_; }
    // The name is not one that can be kept: said as a refusal.
    void refuse(std::string why, double now);
    void tick(double now);
    // When tick() has a refusal to take away, a large number when none.
    double next_tick() const { return refusal_.empty() ? 1e18 : refusal_until_; }

    const std::string& draft() const { return draft_; }
    size_t caret() const { return caret_; }
    bool shifted() const { return shifted_; }
    const std::string& refusal() const { return refusal_; }

private:
    void edited() { shifted_ = draft_.empty(); }

    bool editing_ = false;
    std::string draft_;
    size_t caret_ = 0;
    bool shifted_ = false;
    std::string refusal_;
    double refusal_until_ = 0;
};

// ---------------------------------------------------------------- display.ini

class DisplayController {
public:
    explicit DisplayController(fs::path file = {}) : file_(std::move(file)) {}
    void set_file(fs::path file) { file_ = std::move(file); }
    const fs::path& file() const { return file_; }

    // Read display.ini (each time Settings opens: it may have been changed by
    // hand): what it says, or the defaults with a note when it cannot be read.
    void load();
    // A control changed: saved at once; when that fails, the error is shown
    // and the controls go back to what the file has.
    bool change(const display::Settings& wanted);
    // By element id: fullscreen, interpolation, input-delay, async-shaders, precompile-shaders (a switch: on/off),
    // resolution (an index into display::kResolutions). False for any other id.
    bool set(std::string_view id, int value);
    // Windows' Performance "Use": 1280 x 720 without 120 fps.
    bool performance();
    // What Play reads (precompile_shaders read when Play is pressed, not when Settings last opened).
    display::Settings read() const;

    const display::Settings& settings() const { return settings_; }
    const std::string& note() const { return note_; }            // display.ini cannot be read (...)
    const std::string& error() const { return error_; }          // The display settings cannot be saved: ...
    const std::vector<std::string>& log() const { return log_; } // stderr lines of the last load

private:
    fs::path file_;
    display::Settings settings_;
    std::string note_, error_;
    std::vector<std::string> log_;
};

// "display.ini: fullscreen yes, resolution auto, ..." (the test action's answer).
std::string display_summary(const display::Settings& settings);

// ---------------------------------------------------------------- keyboard.ini

// Where the keys are kept: keyboard.ini (KeyFile), or a stand-in in tests.
struct KeyStore {
    virtual ~KeyStore() = default;
    virtual Keymap load(Keymap::Notes* notes) = 0;
    virtual bool save(const Keymap& keymap, std::string* error) = 0;
};

struct KeyFile final : KeyStore {
    explicit KeyFile(fs::path file) : file(std::move(file)) {}
    Keymap load(Keymap::Notes* notes) override { return Keymap::load(file, notes); }
    bool save(const Keymap& keymap, std::string* error) override { return keymap.save(file, error); }
    fs::path file;
};

// The label a key has in the keyboard layout used (injected by the app: SDL's
// key names for the layout, on both systems). By default the US one: Key::name.
using KeyLabel = std::function<std::string(int usage)>;
std::string us_key_label(int usage);

// Which device a press came from.
enum class Device { kKeyboard, kPad, kMouse };

// Choosing a key: a keycap clicked waits
// for a key; Esc, the pad's B (or A again on it), a click elsewhere or a
// shortcut stop it; a modifier alone is taken once it is let go; a held key's
// repeats are not taken; while a pad started it, the keyboard is ignored for
// 250 ms, and a key let go that was pressed before it started is not taken.
class KeyCapture {
public:
    static constexpr double kIgnoreAfterPad = 0.25;
    static constexpr double kRefusalSeconds = 4, kSwappedSeconds = 3, kRestoredSeconds = 2;

    KeyCapture(KeyStore& store, KeyLabel label = us_key_label) : store_(store), label_(std::move(label)) {}
    void set_label(KeyLabel label) { label_ = std::move(label); }

    // Settings opened: keyboard.ini read again (a note when it is not what the game has).
    void load();
    // Settings closed: choosing stops.
    void close() { stop(); }

    // The keycap of `input` activated (Accept, a click): it waits for a key,
    // or stops waiting when it waited already (A again).
    void pick(int input, Device device, double now);
    void stop();
    // Pad B / a click elsewhere while choosing.
    void cancel() { stop(); }

    // A key pressed (its HID usage = SDL scancode; 0 for one with no usage)
    // while Settings is open: true when it is used here (not navigation).
    // Without a key being chosen nothing is used (Alt+Left is the app's).
    bool key_down(int usage, bool repeat, double now);
    void key_up(int usage, double now);

    // Restore Defaults.
    void restore(double now);
    // The notes that expire.
    void tick(double now);

    struct Taken {
        bool ok = false;
        std::string text; // "<full> is <label>[, swapped with <full>]", or why not
    };
    // What the last key pressed while choosing did (for bind:).
    const Taken& taken() const { return taken_; }

    int picking() const { return picking_; }
    const Keymap& keymap() const { return keymap_; }
    bool restorable() const { return !keymap_.is_default() || !as_shown_; }
    const std::string& note() const { return note_; }   // keyboard.ini cannot be read / two inputs on one key
    const std::string& error() const { return error_; } // The keys cannot be saved: ...
    std::string label(int usage) const;

    struct RowNote {
        std::string text;
        Tone tone = Tone::kNormal; // kError: a refusal, kOk: "Swapped with ..."
        bool flash = false;
        double until = 0;
    };
    const std::map<int, RowNote>& row_notes() const { return rows_; }

private:
    void take(int usage, double now);
    bool save(const Keymap& before);
    void note_row(int input, std::string text, Tone tone, bool flash, double seconds, double now);

    KeyStore& store_;
    KeyLabel label_;
    Keymap keymap_;
    bool as_shown_ = true;
    std::string note_, error_;
    int picking_ = -1;
    int modifier_ = 0;            // a modifier pressed alone while choosing: taken when let go
    std::set<int> held_;          // keys down now
    std::set<int> pressed_since_; // keys pressed since choosing started
    double keyboard_from_ = 0;    // keys before this time are not taken (a pad started choosing)
    Taken taken_;
    std::map<int, RowNote> rows_;
};

// XKB keycodes (bind:<input>:<keycode>[+...]) as HID usages:
// a keycode less 8 is the evdev code. 0 for a keycode no key has.
int usage_of_xkb(int keycode);

// ---------------------------------------------------------------- the page

struct SettingsInput {
    const GameController* game = nullptr;
    const NameEditor* name = nullptr; // the player's name being typed, when editing()
    const DisplayController* display = nullptr;
    std::vector<Monitor> monitors; // from the monitor provider (the app's: SDL's displays)
    const KeyCapture* keys = nullptr;
    LauncherSettings launcher;
    std::string folders_note; // Windows: "Saved." for a moment, or why not
};

SettingsView settings_view(const Facts& facts, const SettingsInput& in);

} // namespace launcher::model
