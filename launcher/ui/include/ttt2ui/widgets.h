// Generic widgets of the Tag Split look: data in (plain structs), events out (Ui::take_events() with the ids given
// here). They declare nodes on a Ui and paint with theme.h's constants; none knows a screen of the launcher.
//
// Ids: every widget takes the id of its focusable/clickable node; parts inside get "<id>/<part>" ids (a group
// header's buttons use the ids in its spec). Focus extras (explicit neighbours, default, group) come in `focus`.
#pragma once

#include <deque>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include "ttt2ui/ui.h"

namespace ttt2::ui {

enum class Tone : std::uint8_t { Neutral, Ok, Warn, Bad, Blue, Red, Dim };
enum class Half : std::uint8_t { Crimson, Blue, Neutral };  // which half's colours

// ---- primitives used by widgets (and by apps for their own pieces) ----------------------------------------------
// A 12-degree parallelogram surface (CSS .sk::before): fill + 1 point border.
void surface(Canvas& canvas, const Rect& r, Color fill, Color border, float tan = theme::kSeamTan);
void surface(Canvas& canvas, const Rect& r, const Gradient& fill, Color border, float tan = theme::kSeamTan);
// A dashed border around a quad (tiles not added yet).
void dashed(Canvas& canvas, const Quad& q, float width, float dash, float gap, Color color);
// Rounded rectangle as a convex polygon.
void rounded_rect(Canvas& canvas, const Rect& r, float radius, Color color);
void rounded_rect(Canvas& canvas, const Rect& r, float top_radius, float bottom_radius, Color color);
// Text with the look's chromatic split (red left, blue right) and a soft drop shadow (.tline, .big, .fname).
void chroma_text(Canvas& canvas, TextEngine& text, const TextStyle& style, std::string_view s, Vec2 pos, float split,
                 float alpha = 1);
// An icon: an embedded SVG path or a line icon ("stroke:check"); see Icons.
void icon(Canvas& canvas, Icons& icons, const std::string& name, const Rect& box, Color color);

// The Tag Split focus highlight: give it to Ui::set_highlight.
void paint_focus_highlight(Canvas& canvas, const Rect& r, Shape shape, float alpha, double now);

// ---- prompt glyphs ------------------------------------------------------------------------------------------------
enum class Prompt : std::uint8_t {
    Accept, Back, Context1, Context2, TabPrev, TabNext, SectionPrev, SectionNext, Menu, Move, Change, AnyKey,
    Tabs,      // TabPrev + TabNext
    Sections,  // SectionPrev + SectionNext
};
// The keyboard's "any key" prompt's key cap in the launcher's language (English "Any key" until set).
void set_any_key_label(std::string label);
// Width (points) of a prompt in a glyph set, and drawing it with its left edge at `left`, centred on `cy`.
float prompt_width(TextEngine& text, Glyphs glyphs, Prompt p);
float draw_prompt(Canvas& canvas, TextEngine& text, Icons& icons, Glyphs glyphs, Prompt p, float left, float cy,
                  float alpha = 1);
// A key cap with any label (key binding rows, hints): returns its width.
float draw_keycap(Canvas& canvas, TextEngine& text, std::string_view label, float left, float cy, float alpha = 1);
void prompt(Ui& ui, const std::string& id, Prompt p, const Box& box = {});

// ---- text ---------------------------------------------------------------------------------------------------------
// One line (ellipsized to the width it gets) or a wrapped block.
struct TextSpec {
    std::string text{};
    TextStyle style = theme::text::kPara;
    Color color = theme::color::kText;
    bool wrap = false;
    Ellipsis ellipsis = Ellipsis::End;
    float align = 0;     // wrapped: 0 left, .5 centre, 1 right
    float outline = 0;   // > 0: outlined letters (.lname)
    float chroma = 0;    // > 0: chromatic split (.tline 4, .big 3)
    float autofit_min = 0;  // > 0: shrink the size (to this) until one line fits
    bool drop = false;      // narrower than the text: nothing at all (no ellipsis); with Box.shrink_order
};
void text(Ui& ui, const std::string& id, const TextSpec& spec, const Box& box = {});
// Coloured runs on one line ("15 of 23 added · 3 to update").
struct Run {
    std::string text{};
    Color color = theme::color::kText;
};
void runs(Ui& ui, const std::string& id, const TextStyle& style, std::vector<Run> runs, const Box& box = {});

// The small heading of a block with its bar and hairline (.lab); `right` in light text after the line.
void section_label(Ui& ui, const std::string& id, const std::string& label, Half half, const std::string& right = {},
                   const Box& box = {});
// Key/value lines (.facts): keys in small capitals, values mono or UI font, coloured runs.
struct Fact {
    std::string key{};
    std::vector<Run> value{};
    bool mono = true;
};
void facts(Ui& ui, const std::string& id, std::span<const Fact> facts, const Box& box = {});
// A line with a leading icon (.warnl): Warn / info (Blue) / Bad.
void note(Ui& ui, const std::string& id, Tone tone, const std::string& text, const Box& box = {},
          const std::string& icon_name = {});
// A big outlined word behind a screen (.wm), anchored at `bottom_right`.
void watermark(Canvas& canvas, TextEngine& text, const std::string& word, Vec2 bottom_right);

// ---- top band -------------------------------------------------------------------------------------------------------
void brand(Ui& ui, const std::string& id, const std::string& line1, const std::string& line2, const Box& box = {});
struct Tab {
    std::string id{}, label{}, badge{};
};
// Tabs with the Q/E (LB/RB) glyphs and a springing underline; clicks only (tabs are switched with the shoulder
// buttons): Activate with the tab's id.
void tab_bar(Ui& ui, const std::string& id, std::span<const Tab> tabs, int active, const Box& box = {});
// A small icon button of the top band (.ib): clicks only unless `nav`.
struct IconButtonSpec {
    std::string icon{}, label{};
    bool on = false;
    bool nav = false;
};
void icon_button(Ui& ui, const std::string& id, const IconButtonSpec& spec, const Box& box = {});
// The window's own minimise / fullscreen / close buttons (ids "<id>/min", "<id>/full", "<id>/close"); the ones the
// window cannot offer under gamescope are left out.
void caption_buttons(Ui& ui, const std::string& id, bool minimise, bool fullscreen_toggle, bool is_fullscreen,
                     bool close = true, const Box& box = {});
// The bottom band's prompts. `room` (points, 0: not known): short of it, the gaps narrow, then the labels close up and
// get a little smaller (85 %), and only then the last hints are left out (never one over another).
struct Hint {
    Prompt prompt;
    std::string label{};
};
void hint_bar(Ui& ui, const std::string& id, std::span<const Hint> hints, const Box& box = {}, float room = 0);

// ---- crimson lists --------------------------------------------------------------------------------------------------
// The big slab (PLAY / INSTALL / UPDATE).
struct SlabSpec {
    std::string big{}, line1{}, line2{};
    bool mid = false;  // a longer word: smaller letters
    bool disabled = false;
};
void slab(Ui& ui, const std::string& id, const SlabSpec& spec, Focus focus = {}, const Box& box = {});
// A menu row (.mrow): icon box, title, value, chevron; `two`: a small caption over the title (.mrow.tall).
struct MenuRowSpec {
    std::string icon{}, title{}, value{}, caption{};
    Tone value_tone = Tone::Neutral;
    bool danger = false, disabled = false, mono_title = false;
    int number = 0;  // > 0: an outlined number instead of the icon (setup slots)
    bool ok = false;
    int check = -1;  // >= 0: a check box instead of the icon: 0 off, 1 on, 2 some (.oall)
    bool compact = false;  // a lower row with smaller letters
};
void menu_row(Ui& ui, const std::string& id, const MenuRowSpec& spec, Focus focus = {}, const Box& box = {});
// A fighter tile with its corner badge.
enum class TileState : std::uint8_t { Added, Update, None, NotOwned, Checking, Newer };
enum class TileTone : std::uint8_t { Red, Pink, Orange, Gold };
struct TileSpec {
    std::string code{}, name{}, tag{};  // tag: the white corner label ("OUTFITS"), empty for none
    TileTone tone = TileTone::Red;
    TileState state = TileState::Added;
    bool busy = false;
    // The fighter's picture in place of its code (an added fighter's, from its pack): `portrait_uv` is the part of
    // the texture the tile's upright rectangle shows (its slanted sides show a little more, at the same scale).
    TextureId portrait = 0;
    Rect portrait_uv{};
};
void fighter_tile(Ui& ui, const std::string& id, const TileSpec& spec, Focus focus = {});
// A group heading with counts and action buttons (Activate with each button's id).
struct HeaderButton {
    std::string id{}, label{};
    bool disabled = false;
};
struct GroupHeaderSpec {
    std::string title{}, count{}, sub{};
    Tone sub_tone = Tone::Neutral;
    std::vector<HeaderButton> buttons{};
    int focus_group = 0;  // the buttons' Focus::group (a list's: -1, so up/down from its items reach them)
};
void group_header(Ui& ui, const std::string& id, const GroupHeaderSpec& spec, const Box& box = {});
// A settings row with its value in place: Left/Right (or a click on an arrow) give Change -1/+1, Accept Activate.
// `slide`: the direction of the last change (-1/+1), the new value slides in from that side.
struct SettingRowSpec {
    std::string title{}, value{}, detail{};  // detail: a mono line under the title (folders)
    bool value_on = false;             // value shown as "on" (blue)
    bool chevron = false;              // a chevron instead of the selector (opens something)
    bool value_as_typed = false;       // the value in its own case (a name), not in capitals
    bool disabled = false;
    int slide = 1;
};
void setting_row(Ui& ui, const std::string& id, const SettingRowSpec& spec, Focus focus = {}, const Box& box = {});
// Section switcher (.secs): Z/C glyphs around section buttons; Activate with the section's id.
struct Section {
    std::string id{}, label{};
    bool disabled = false;
};
// `focus_group`: the sections' Focus::group (the list's below them: -1, so Up from its first item reaches them).
// A row too narrow for them shrinks the sections (their names closed up, then smaller); `box.wrap`: on two lines
// (or more) instead, every section as wide as it likes (for a row narrower than section_tabs_width(..., true)).
void section_tabs(Ui& ui, const std::string& id, std::span<const Section> sections, int active, const Box& box = {},
                  int focus_group = 0);
// How wide section_tabs is on one line: the prompts, the gaps and every section as it likes, or (`least`) as narrow
// as it may be shrunk.
float section_tabs_width(Ui& ui, std::span<const Section> sections, bool least);
// A key binding row.
struct KeyRowSpec {
    std::string icon{}, name{}, key{};
    bool capturing = false, swapped = false;
    double flash_until = 0;
};
void key_row(Ui& ui, const std::string& id, const KeyRowSpec& spec, Focus focus = {}, const Box& box = {});
// The width a key row takes with its whole name (points).
float key_row_width(TextEngine& te, const KeyRowSpec& spec);
// A task step with its mini bar (not focusable).
enum class StepState : std::uint8_t { Pending, Current, Done, Failed };
struct StepRowSpec {
    std::string name{}, count{};
    float fraction = 0;
    StepState state = StepState::Pending;
    int number = 1;
    // The name column: the widest name of the list's rows (step_name_width), so that their bars line up; the bar
    // keeps 30 points at least (a name longer than that leaves is cut).
    float name_width = kStepNameWidth;
    static constexpr float kStepNameWidth = 118;
};
// The name column for a list of step rows: their widest name, at least StepRowSpec::kStepNameWidth.
float step_name_width(TextEngine& text, const std::vector<std::string>& names);
void step_row(Ui& ui, const std::string& id, const StepRowSpec& spec, const Box& box = {});
// A file browser row.
struct FileRowSpec {
    std::string icon = "stroke:file", name{}, meta{};
    Tone tone = Tone::Neutral;  // Ok: the file wanted; Dim: not choosable
};
void file_row(Ui& ui, const std::string& id, const FileRowSpec& spec, Focus focus = {}, const Box& box = {});

// ---- text entry ----------------------------------------------------------------------------------------------------
// A line of text being typed: its words, a caret blinking where the next character goes, the placeholder (dim) when
// it is empty, a count at its end ("4/16"); `refused`: its frame in the warning colour (a character not taken).
struct TextFieldSpec {
    std::string text{}, placeholder{}, count{};
    std::size_t caret = 0;  // a byte index into text
    bool refused = false;
};
void text_field(Ui& ui, const std::string& id, const TextFieldSpec& spec, const Box& box = {});
// A key of an on-screen keyboard: its label, or an icon ("stroke:shift"); `primary`: the key that ends it (Done);
// `on`: a key that stays pressed (Shift). In a row it grows with its Box::w weight (its width in keys).
struct ScreenKeySpec {
    std::string label{}, icon{};
    bool primary = false, on = false, disabled = false;
};
void screen_key(Ui& ui, const std::string& id, const ScreenKeySpec& spec, Focus focus = {}, const Box& box = {});

// ---- blue readout ---------------------------------------------------------------------------------------------------
// The progress bar: the fill eases toward `fraction` (< 0: unknown, a pulse runs).
void progress_bar(Ui& ui, const std::string& id, float fraction, Tone tone = Tone::Blue, const Box& box = {});
// `as_typed`: the label in its own case (a name), not in capitals.
void pill(Ui& ui, const std::string& id, const std::string& label, Tone tone = Tone::Neutral, bool dot = false,
          const Box& box = {}, bool as_typed = false);
// Choices shown as chips, the current one lit (a picture of a setting's options, not focusable).
void chips(Ui& ui, const std::string& id, std::span<const std::string> options, int current, const Box& box = {});
// A described thing: a title in cyan and its text (.xpl).
void describe_panel(Ui& ui, const std::string& id, const std::string& title, const std::string& body,
                    const Box& box = {});
// An entry of a numbered list (Home's UPDATE, its parts in order): the number in a small square, the title, the text
// under it, wrapped. Mirrored (the blue side): the number at the right end, the words right-aligned before it.
void numbered_item(Ui& ui, const std::string& id, int number, const std::string& title, const std::string& text,
                   const Box& box = {});
enum class ButtonKind : std::uint8_t { Ghost, Primary, Blue, Danger };
enum class ButtonSize : std::uint8_t { Normal, Small, Tiny };
struct ButtonSpec {
    std::string label{};
    ButtonKind kind = ButtonKind::Ghost;
    ButtonSize size = ButtonSize::Normal;
    std::optional<Prompt> prompt;   // a glyph before the label
    std::optional<bool> check;      // a check box before the label (on/off)
    bool disabled = false;
    Half half = Half::Blue;         // the focused ghost's colour
};
void button(Ui& ui, const std::string& id, const ButtonSpec& spec, Focus focus = {}, const Box& box = {});

// The blue half's content follows the focused item: when its key changes, the old content slides out toward the
// seam's far side and fades while the new one slides in from the seam (direction of the move: dy -1 up, 1 down).
class Readout {
public:
    void show(const std::string& key, int dy, double now);
    const std::string& key() const { return key_; }
    // Declares a Stack `id` with the old content (inert, fading) and the new one; `content(key)` declares one.
    void build(Ui& ui, const std::string& id, const Box& box,
               const std::function<void(const std::string& key)>& content);
    bool animating(double now) const;

private:
    std::string key_{}, old_{};
    double changed_ = -1e9;
    int dy_ = 0;
};

// ---- dialog parts --------------------------------------------------------------------------------------------------
// A ticked option of a dialog (.opt): check box and its text (wrapped), Accept toggles it.
struct OptionRowSpec {
    std::string text{};
    bool on = false;
    bool disabled = false;
};
void option_row(Ui& ui, const std::string& id, const OptionRowSpec& spec, Focus focus = {}, const Box& box = {});
// "What happens" lines (.wh): a key in small capitals (red: removed, green: kept) and words wrapped after it, some
// of them in the mono font (paths).
enum class WhatTone : std::uint8_t { Neutral, Removed, Kept };
struct WhatPart {
    std::string text{};
    bool mono = false;
};
struct WhatLine {
    std::string key{};
    WhatTone tone = WhatTone::Neutral;
    std::vector<WhatPart> parts{};
};
void what_list(Ui& ui, const std::string& id, std::span<const WhatLine> lines, const Box& box = {});
// Puts text on the clipboard (a log, a command to run); false when the system refused.
bool copy_text(const std::string& text);
// What the clipboard holds as text ("" for nothing).
std::string pasted_text();

// ---- dialog band ---------------------------------------------------------------------------------------------------
// A split band across the dimmed screen (a modal): the crimson half (options) and the blue half (what happens),
// split by the dialog's seam. Returns the guard of the modal; declare the halves inside with the boxes given.
struct BandLayout {
    Box crimson, blue;
    Rect band;
};
BandLayout band_layout(Vec2 size, float top, float height, float share = theme::split::kDialog);
[[nodiscard]] Ui::Guard dialog_band(Ui& ui, const std::string& id, const BandLayout& layout);

// ---- log view -------------------------------------------------------------------------------------------------------
enum class LogKind : std::uint8_t { Normal, Command, Error, Status };
struct LogLine {
    std::string text{};
    LogKind kind = LogKind::Normal;
};
// The lines of a log (kept to `limit`), wrapped per line at the width it is shown (cached), drawn only where
// visible; it follows the end while scrolled to the end.
class LogView {
public:
    explicit LogView(std::size_t limit = 20000) : limit_(limit) {}
    void append(std::string text, LogKind kind = LogKind::Normal);
    void clear();
    std::size_t size() const { return lines_.size(); }
    const LogLine& line(std::size_t i) const { return lines_[i]; }
    std::string text() const;  // everything (copy)
    // (widget internals)
    float height(TextEngine& text, float width);
    void paint(PaintContext& ctx, const Rect& content, float view_top, float view_bottom);
    std::uint64_t serial() const { return serial_; }

private:
    void rewrap(TextEngine& text, float width);
    std::deque<LogLine> lines_;
    std::deque<int> rows_;  // wrapped rows per line at width_
    std::size_t limit_;
    float width_ = -1, scale_ = -1;
    std::size_t total_rows_ = 0;
    std::uint64_t serial_ = 0;
};
void log_view(Ui& ui, const std::string& id, LogView& log, const Box& box);

}  // namespace ttt2::ui
