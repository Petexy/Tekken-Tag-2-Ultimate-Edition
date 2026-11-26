#pragma once

// What the player sees, as plain structures the view builders return
// (builders.h) and the screens draw: texts verbatim, every focusable item
// with a stable id (the old apps' element ids), whether
// it can be used now and why not, and a describe block, which the blue half
// of the screen shows for the focused item: nothing lives only in a
// tooltip. A disabled item stays in the view with its why.

#include "i18n.h"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace launcher::model {

// Every text a player reads: i18n.h.
using i18n::tr;
using i18n::trn;

// How a text reads: the old apps' style classes (error-text, warning-text,
// dim, path, the headings), for the look to map to its own.
enum class Tone { kNormal, kDim, kError, kWarning, kOk, kPath, kHeading };
enum class PillKind { kNeutral, kOk, kWarn, kBad };
// The icons the views name (the look draws them): the GTK app's icon names
// in parentheses.
enum class Icon {
    kNone,
    kInfo,     // dialog-information-symbolic
    kWarning,  // dialog-warning-symbolic
    kError,    // dialog-error-symbolic
    kOk,       // object-select-symbolic
    kUpdate,   // ttt2-update-symbolic
    kDocument, // document-open-symbolic
    kPlay,     // media-playback-start-symbolic
    kSettings, // ttt2-settings-symbolic
    kFolder,   // folder-symbolic
    kBack,     // ttt2-back-symbolic
    kRefresh,  // view-refresh-symbolic
    kCopy,     // edit-copy-symbolic
    kMore,     // (Windows' More)
    kLog,      // (Windows' logs)
};

// What the blue side says about the focused item.
struct Describe {
    std::string title;             // what it is: "Kazumi Mishima", "Play", "Fullscreen"
    std::string state;             // how it is: "Added", "Update ready", "On", "W"
    std::string explain;           // what the state means (a pill's explanation), or what the item does
    std::string why;               // why it cannot be used now (empty when it can)
    std::string path;              // a full path, when the item has one
    std::vector<std::string> more; // further lines (a command to copy, notes)
    bool operator==(const Describe&) const = default;
};

struct Pill {
    std::string text;
    PillKind kind = PillKind::kNeutral;
    std::string explain; // the GTK tooltip
    bool operator==(const Pill&) const = default;
};

enum class ActionKind { kButton, kCheck, kSwitch, kChoice, kExpander, kKeycap, kMenu, kMenuItem, kEntry };

// A focusable item: a button, a check box, a switch, a list, an expander, a
// keycap, a menu entry, a text entry (its label: the text it holds).
// `id` addresses it (activate(id)).
struct Action {
    std::string id;
    std::string label;
    ActionKind kind = ActionKind::kButton;
    Icon icon = Icon::kNone;
    bool enabled = true;
    std::string why;          // why it is disabled now (also in describe.why); empty when it is not, or nothing says
    std::string tooltip;      // what the old app's tooltip said (goldens; the blue side says it in describe)
    bool primary = false;     // suggested-action
    bool destructive = false; // destructive-action / CSS uninstall
    bool flat = false;
    bool checked = false;             // check, switch, expander (expanded), keycap (waiting for a key)
    bool inconsistent = false;        // check: some of them
    std::vector<std::string> choices; // choice: its entries
    int chosen = -1;
    std::string placeholder;          // entry: shown while it holds nothing (the game's own name)
    Describe describe;
    bool operator==(const Action&) const = default;
};

// A line of a card: a text, a note with its icon, a spinner with its text,
// a command to copy, a check's result, the .wua chosen. Buttons at its end.
struct Line {
    enum class Kind { kText, kNote, kSpinner, kCommand, kCheck, kFile };
    Kind kind = Kind::kText;
    Icon icon = Icon::kNone;
    Tone icon_tone = Tone::kNormal; // the icon's own (warn, ok, bad, dim)
    Tone tone = Tone::kNormal;
    bool small = false;
    std::string title; // kCheck: the check's title; kFile: the file's name
    std::string text;  // kCheck: its detail; kFile: its folder; kCommand: the command
    std::vector<Action> actions;
    bool operator==(const Line&) const = default;
};

Line text_line(std::string text, Tone tone = Tone::kNormal, bool small = false);
Line note_line(Icon icon, std::string text, bool warn, Tone icon_tone = Tone::kNormal);

// ---------------------------------------------------------------- the pages

struct Banner {
    std::string title = "Tekken Tag Tournament 2";
    std::string edition = "ULTIMATE EDITION";
    std::string note;
    bool icon = false; // <install>/icon.png
    bool operator==(const Banner&) const = default;
};

struct Header {
    std::string title;           // "Golden Fist Launcher" / "Settings"
    std::vector<Action> actions; // back, refresh, update-launcher
    bool update_offered = false; // the Update button stands out (a newer release)
    bool operator==(const Header&) const = default;
};

enum class GameState { kNotInstalled, kChecking, kCannotInstall, kInstalling, kNotFinished, kInstalled };

// A part of Home's UPDATE, as the blue side lists it: "launcher", "game", "fighters", or "later" (characters it
// leaves for later, with why).
struct UpdatePart {
    std::string kind;
    std::string title; // "Golden Fist Launcher 0.8.0 → 0.9.0", "The game program", "Fighters", "Left for later"
    std::string text;  // what happens, in a sentence or two
    bool operator==(const UpdatePart&) const = default;
};

struct GameView {
    GameState state = GameState::kNotInstalled;
    std::string title = "Tekken Tag Tournament 2";
    std::string folder; // shown under the title, empty when none
    Pill pill;
    std::vector<Line> body;
    std::vector<Action> actions; // the button row, in order
    size_t spacer = SIZE_MAX;    // actions from this index on are at the row's right end
    std::vector<Action> more;    // Windows: the More menu's entries (the menu button is in `actions`)
    std::vector<UpdatePart> update; // UPDATE's parts in order, then what is left for later (empty: nothing to do)
    bool operator==(const GameView&) const = default;
};

struct Fact {
    std::string name;        // "Tekken 7", "Steam", "Missing"
    std::vector<Line> lines; // its value(s)
    Describe describe;
    bool operator==(const Fact&) const = default;
};

struct FighterRow {
    std::string name, display;
    std::optional<Action> outfits; // outfits:<name>
    std::optional<Pill> pill;      // the state
    std::string state_text;        // "Owned" / "Not owned" (a DLC's, no pill)
    std::vector<Action> buttons;   // remove:<name>, fighter:<name>
    std::string button_note;       // "Not owned" in place of Add Again / Update
    Describe describe;             // the row's: name, state, explanation
    bool operator==(const FighterRow&) const = default;
};

struct DlcBlock {
    Action expander;              // dlc[:tekken8]
    std::vector<Pill> pills;      // "3 of 8 owned", "1 to add again", "2 to update"
    std::vector<Line> notes;      // what Steam said (inside)
    Action add_owned;             // add-all-owned[:tekken8]
    std::vector<FighterRow> rows; // inside
    bool operator==(const DlcBlock&) const = default;
};

struct GameGroup {
    std::string game; // kTekken7 / kTekken8
    std::string heading, about;
    std::vector<Action> head; // add-all[:tekken8], remove-all:<game>
    std::vector<Line> notes;  // warnings, stand-ins, updates (with their buttons)
    std::vector<FighterRow> rows;
    std::optional<DlcBlock> dlc; // the game's DLC
    bool operator==(const GameGroup&) const = default;
};

struct CharactersView {
    // An early exit (no importer, no Python, looking, cannot tell): only these lines.
    bool early = false;
    std::vector<Line> lines; // early lines, or the notes above the facts
    std::vector<Fact> facts;
    std::vector<Line> news; // "Main adds ..."
    std::optional<Action> add_all_owned; // add-all-owned:all: every game's characters at once
    std::optional<Action> outfits_all;
    std::vector<Line> outfits_notes;
    std::vector<GameGroup> games;
    bool operator==(const CharactersView&) const = default;
};

struct NoticeView {
    bool shown = false;
    Icon icon = Icon::kUpdate;
    std::string title, detail;
    std::optional<Action> page; // release-page (What's New), when there is a page
    Action update;              // notice-update
    bool whole = false;         // Home's UPDATE does it (with the game and the fighters): no button of its own
    bool operator==(const NoticeView&) const = default;
};

// ---------------------------------------------------------------- Settings

struct SettingRow {
    Action control; // fullscreen, resolution, ...
    std::string name, about;
    std::vector<Line> notes; // automatic note, refresh note
    bool operator==(const SettingRow&) const = default;
};

struct KeyRow {
    Action keycap;     // key:<input id>: label = the key's label, or "Press a key…"
    std::string input; // the input's id (its icon: ttt2-input-<id>)
    std::string name, full;
    std::string note;               // the row's message
    Tone note_tone = Tone::kNormal; // error (refusal) / swapped
    bool flash = false;
    bool operator==(const KeyRow&) const = default;
};

struct KeyGroup {
    std::string title;
    std::vector<KeyRow> rows;
    bool operator==(const KeyGroup&) const = default;
};

struct FolderRow { // Windows: Settings > Folders
    std::string key, name, hint, value;
    Action browse; // folder:<key>
    bool operator==(const FolderRow&) const = default;
};

// Typing the player's name (Settings > Game, its row activated): the text as typed so far and the on-screen
// keyboard for a pad.
struct NameKey {
    Action key; // name-key:<character> (letters by their small one), name:shift, name:backspace, name:space,
                // name:cancel, name:done
    int span = 1; // how many key widths it takes in its row
    bool operator==(const NameKey&) const = default;
};

struct NameEditView {
    std::string draft;           // the name as typed so far
    size_t caret = 0;            // where the next character goes (a byte index into draft)
    std::string placeholder;     // shown when the draft is empty: the game's own name
    std::string count;           // "4/16"
    std::string refusal;         // a character or a name refused, for a moment ("" none)
    std::string rule;            // what a name may be
    bool shifted = false;        // the keyboard's letters are capitals
    std::vector<std::vector<NameKey>> keys; // the on-screen keyboard, row by row (each the same width in spans)
    bool operator==(const NameEditView&) const = default;
};

struct SettingsView {
    // Game (game.ini: the player's name, the language; Input delay: display.ini)
    std::string game_title = tr("settings.game", "Game");
    std::string game_about = tr("settings.game_about",
                                "Your name in the game, the language of its texts, and how it takes your presses. The "
                                "game uses these when it starts.");
    std::vector<Line> game_notes; // error / unreadable note
    std::vector<SettingRow> game;
    std::optional<NameEditView> name_edit; // the player's name being typed
    // Display (display.ini)
    std::string display_title = tr("settings.display", "Display"),
                display_about = tr("settings.display_about", "The game uses these when it starts.");
    std::vector<Line> display_notes; // error / unreadable note
    std::vector<SettingRow> display;
    // Keyboard (keyboard.ini)
    std::string keys_title = tr("settings.keyboard", "Keyboard");
    std::string keys_about = tr("settings.keyboard_about",
                                "Keys by position on the keyboard; the game uses them as the Wii U GamePad's buttons. "
                                "Changes apply at once, also while the game runs.");
    std::vector<Line> keys_notes;
    std::vector<KeyGroup> groups;
    std::vector<Action> keys_actions; // restore-keys (+ Windows: open-keyboard-file)
    // Folders (Windows)
    bool folders_shown = false;
    std::string folders_title = tr("settings.folders", "Folders");
    std::string folders_about = tr("settings.folders_about",
                                   "Where the launcher finds your game and keeps its tools, characters and saves "
                                   "(Windows).");
    std::vector<FolderRow> folders;
    std::vector<Action> folders_actions; // save-folders
    std::vector<Line> folders_notes;
    // The launcher's own (launcher.ini): new.
    std::string launcher_title = "Golden Fist Launcher";
    std::string launcher_about = tr("settings.launcher_about", "How this launcher looks and sounds.");
    std::vector<SettingRow> launcher;
    bool operator==(const SettingsView&) const = default;
};

// ---------------------------------------------------------------- the task panel

struct TaskView {
    bool shown = false;   // the panel is out
    bool running = false; // spinner and progress bar
    std::string title, detail;
    bool failed = false;            // the title in red
    bool stopping = false;          // cancelled, not ended yet
    double fraction = -1;           // below 0: unknown (pulsing)
    Action button;                  // task: Cancel / Stopping… / Close
    std::optional<Action> open_log; // Windows: Open Log
    Action details;                 // details: the log's expander
    // Home's UPDATE, one part after another: which part this task is ("2 of 3: the game program"), what comes
    // after it, and, once all are done, what it brought. `count` 0: the task is not an update's part.
    struct Chain {
        int at = 0, count = 0;          // this part's number (1-based) and how many
        std::string part;               // "Golden Fist Launcher", "The game program", "Fighters"
        std::vector<UpdatePart> next;   // the parts still to come after it (all of them when `waiting`: from it)
        bool waiting = false;           // the part `at` starts by itself once the launcher has looked again
        bool handed_over = false;       // the launcher's part is done: the new launcher goes on with the rest
        bool stopped = false;           // stopped at `at` (failed or cancelled): Try Again goes on from it
        bool done = false;              // every part is done
        std::string summary;            // done: "Updated: launcher 0.9.0, the game program, 3 fighters"
        std::string later;              // characters left for later, and why ("" none)
        bool operator==(const Chain&) const = default;
    } chain;
    bool operator==(const TaskView&) const = default;
};

// ---------------------------------------------------------------- dialogs

struct Dialog {
    std::string id; // "uninstall", "remove-all", "stop-and-quit", "setup", "refusal", "message"
    std::string title, text;
    // Further texts (paths, notes) and the check boxes (uninstall-saves, uninstall-characters: a line's action),
    // in order.
    std::vector<Line> lines;
    std::vector<Action> buttons; // in order; the safe one is `cancel`
    std::string cancel;          // the id Esc / B gives
    std::string default_id;      // the focused one at first
    bool operator==(const Dialog&) const = default;
};

} // namespace launcher::model
