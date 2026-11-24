// The immediate-mode interface: every frame the app declares a tree of boxes with STABLE ids (data in), the Ui lays
// it out (widths, then heights at those widths, then positions; flex rows/columns/stacks, wrapping rows, scroll
// containers, the seam "staircase" fit), keeps per-id state across frames (hover/focus/appear animation, scroll
// offsets; swept when an id is not declared any more), moves the focus (spatial navigation, scopes, fallbacks),
// turns input actions and clicks into events (events out), and paints the tree with the callbacks the widgets gave.
#pragma once

#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "ttt2ui/anim.h"
#include "ttt2ui/canvas.h"
#include "ttt2ui/focus.h"
#include "ttt2ui/icons.h"
#include "ttt2ui/input.h"
#include "ttt2ui/text.h"
#include "ttt2ui/theme.h"

namespace ttt2::ui {

struct Size {
    enum Mode : std::uint8_t { Fit, Fixed, Grow };
    Mode mode = Fit;
    float value = 0;  // Fixed: points; Grow: weight
    static constexpr Size fit() { return {Fit, 0}; }
    static constexpr Size fixed(float v) { return {Fixed, v}; }
    static constexpr Size grow(float weight = 1) { return {Grow, weight}; }
};
enum class Layout : std::uint8_t { Column, Row, Stack };
enum class Align : std::uint8_t { Start, Center, End, Stretch };

// A slanted line x(y) = c - (y - yc) * tan in screen points (the Tag Split seam).
struct Seam {
    float c = 0, yc = 0, tan = theme::kSeamTan;
    float x_at(float y) const { return c - (y - yc) * tan; }
};
// How a box is fitted to its seam (the staircase): crimson boxes get a WIDTH so their seam-side edge is `fit_gap`
// from the seam (skewed: at their middle; rect: at their bottom-right corner); blue boxes get a LEFT offset so their
// top-left corner (rect) or middle (skewed) is that far from it.
enum class SeamFit : std::uint8_t { None, CrimsonSkewed, CrimsonRect, BlueSkewed, BlueRect };

struct Box {
    Layout layout = Layout::Column;
    Size w = Size::fit(), h = Size::fit();
    float min_w = 0, max_w = 1e9f, min_h = 0, max_h = 1e9f;
    Insets pad{}, margin{};
    float gap = 0;
    float line_gap = 0;           // wrapping rows: between lines
    Align align = Align::Stretch; // children across the main axis (Stack: both axes, Stretch = fill)
    Align justify = Align::Start; // children along the main axis
    bool wrap = false;            // rows: wrap onto more lines
    bool scroll = false;          // vertical scroll container (clips, scroll bar, keeps the focus in view)
    bool clip = false;
    bool hug = false;             // Fit width: its content's width even in a stretching column (inline blocks)
    // A row too narrow for its Fit children shrinks them toward min_w, the highest shrink_order first (all of it),
    // then the next (a top band: the version text goes, then the buttons' labels, then the brand's words).
    int shrink_order = 0;
    Insets scroll_insets{};       // parts of the viewport covered by overlays (the focus is kept out of them)
    SeamFit fit = SeamFit::None;
    float fit_gap = theme::kSeamGap;
    std::optional<Seam> seam{};   // the seam this subtree fits to (inherited)
    // Drawing only (layout and hit tests ignore them): moved by `shift` points, faded by `opacity` (entries and the
    // blue readout's slides).
    Vec2 shift{};
    float opacity = 1;
    bool inert = false;           // nothing inside takes focus or clicks (content fading out)
    // The blue half (FEEDBACK F2): its straight edge is its RIGHT one, so everything inside is anchored and aligned
    // to the right (inherited): rows and narrower children go to the right end, the widgets right-align their
    // text, mirror their tables (facts) and put their marks (label bar, note icon, accent) on the right; the slanted
    // left side only takes up the slack, its seam fit keeping the gap on every row.
    bool mirror = false;
    // A drill-in lock (FEEDBACK F4): the half whose item opened the other half's actions. Nothing inside takes the
    // focus (navigation, hover) so the pointer travels over it freely; it fades and moves back (eased, drawn
    // only); a left click anywhere on it is an Unlock event (id: the item under the pointer, else this box).
    bool locked = false;
};

struct Focus {
    bool on = true;
    bool disabled = false;   // still focusable (dimmed; Accept gives Refused with the item's id)
    int group = 0;           // e.g. -1 crimson list, 1 blue readout: up/down stay in their group
    bool skewed = true;      // the highlight's shape
    float pad = theme::metric::kFocusPad;
    bool is_default = false; // focused when nothing else is
    bool adjust = false;     // Left/Right give Change -1/+1 instead of moving (selectors)
    bool nav = true;         // false: clicks only (tabs in the top band); never takes the focus
    std::string up, down, left, right;  // explicit neighbours (an id; "-" = nothing: bump)
    struct Zone {
        float from_right0, from_right1;  // a click between these distances from the right edge...
        int delta;                       // ... is Change by delta
    };
    Zone zones[2]{};
    int zone_count = 0;
};

struct NodeState {
    std::uint64_t last_frame = 0;
    double first_seen = 0;
    float hover = 0, focus = 0;  // 0..1, eased
    float lock = 0;              // 0..1 eased toward Box::locked
    bool pressed = false;
    Spring scroll{0, theme::motion::kScroll};
    float content_h = 0, view_h = 0;
    bool dragging_bar = false;
    float drag_grab = 0;
    float user[4] = {0, 0, 0, 0};  // widget-owned values (e.g. a progress bar's shown fraction)
    bool user_set = false;
    Rect rect;
};

struct PaintContext {
    Canvas& canvas;
    TextEngine& text;
    Icons& icons;
    NodeState& state;
    Rect rect;
    double now;
    float dt;            // since the last frame
    bool focused;        // has the focus now
    float focus_t;       // 0..1 eased toward focused
    float hover_t;
    float appear;        // seconds since first declared
    bool disabled;
    bool reduced;        // Reduce motion
    Glyphs glyphs;
    bool* more;          // set *more = true while the painting animates (the loop then draws the next frame)
    // The ambient clock (FrameInput::ambient): endless decorative loops (a sheen, a blinking dot, a pulse, moving
    // stripes) take their phase from it and call loop(), never animate(). Like the stage's ambient layer (U9) they
    // never count as animation: the loop draws them at most theme::motion::kAmbientHz times a second, and the clock
    // stands still (a still picture) while ambient motion is paused, unfocused, hidden or the game runs.
    double ambient;
    bool* loops;
    void loop() { *loops = true; }
    void animate() { *more = true; }
};
using PaintFn = std::function<void(PaintContext&)>;
using MeasureFn = std::function<Vec2(float max_width)>;

enum class EventKind : std::uint8_t {
    Activate,     // Accept / click on an enabled item
    Refused,      // ... on a disabled one (show why)
    Change,       // Left/Right on an adjust item, or a click on one of its zones (delta)
    Back,
    TabPrev,
    TabNext,
    SectionPrev,
    SectionNext,
    Context1,
    Context2,
    Menu,
    Fullscreen,
    Bump,         // a move with nowhere to go
    ClickOutside, // a click outside the open modal (id = the modal)
    FocusMoved,   // (id = the new focus)
    Unlock,       // a left click on a locked box (Box::locked): delta 1, id = the item clicked; else 0, the box
};
const char* event_name(EventKind k);

struct Event {
    EventKind kind;
    std::string id;  // the focused / clicked item (or the modal)
    int delta = 0;
    Device device = Device::None;
};

struct FrameInput {
    Vec2 size;          // points
    float scale = 1;    // physical pixels per point
    double now = 0;
    std::vector<ActionEvent> actions;
    MouseState mouse;
    bool reduced_motion = false;
    Glyphs glyphs = Glyphs::Keyboard;
    // The ambient clock for decorative loops (PaintContext::ambient); unset: `now`.
    std::optional<double> ambient;
};

using HighlightFn = std::function<void(Canvas&, const Rect& r, bool skewed, float alpha, double now)>;

class Ui {
public:
    Ui(TextEngine& text, Icons& icons);

    void begin(FrameInput frame);
    // Containers: close with close() or let the returned guard do it.
    class [[nodiscard]] Guard {
    public:
        explicit Guard(Ui* ui) : ui_(ui) {}
        Guard(Guard&& o) noexcept : ui_(o.ui_) { o.ui_ = nullptr; }
        Guard(const Guard&) = delete;
        ~Guard() {
            if (ui_) ui_->close();
        }

    private:
        Ui* ui_;
    };
    Guard open(std::string id, const Box& box, PaintFn paint = {}, const Focus* focus = nullptr,
               PaintFn paint_after = {});
    void close();
    void leaf(std::string id, const Box& box, MeasureFn measure, PaintFn paint, const Focus* focus = nullptr);
    // A modal layer: the focus stays inside it, presses that began before it opened are ignored, a click outside
    // gives ClickOutside; when it goes, the focus returns to where it was.
    Guard modal(std::string id, const Box& box, PaintFn paint = {});
    void end();
    void paint(Canvas& canvas);
    std::vector<Event> take_events() { return std::exchange(events_, {}); }

    // Focus.
    const std::string& focused() const { return focused_; }
    void focus(const std::string& id, bool snap = false);
    // Asked when the focused id is gone: an id to focus instead ("" = none; then the nearest item, then the default).
    void set_fallback(std::function<std::string(const std::string& lost)> f) { fallback_ = std::move(f); }
    void set_highlight(HighlightFn f) { highlight_paint_ = std::move(f); }
    void set_wrap(WrapRule w) { wrap_ = w; }
    // The highlight as drawn (screen points, with its item's drawing shift) and where it belongs: the focused item
    // outset by its pad, shifted as its item is drawn (empty when nothing has the focus).
    Rect highlight_rect() const;
    Rect focus_rect() const;

    // Checks of the Tag Split rule on this frame's layout (after end()), for tests: every painted node of a half
    // (the side of its nearest seam-fitted ancestor, else of its centre) stays `min_gap` points from its seam on
    // every row it covers (skewed shapes measured along their slanted edge), as it is drawn (shift included, the
    // part scrolled out of view left out); the highlight is never empty while something has the focus. Returns
    // one sentence per problem (empty: all good).
    std::vector<std::string> audit(float min_gap = theme::kGutter) const;

    // Queries (after end()).
    bool animating() const { return animating_ || paint_animating_; }
    // Whether the last paint drew a decorative loop (PaintContext::loop): worth an ambient frame while ambient motion
    // runs, never a reason to draw at the display's rate.
    bool looping() const { return paint_looping_; }
    bool has(const std::string& id) const;
    Rect rect(const std::string& id) const;  // screen points; empty when absent
    NodeState* state(const std::string& id);
    std::size_t duplicate_ids() const { return duplicates_; }
    // Debug builds stop at an id declared twice in a frame (assert); tests that make one on purpose turn it off.
    void set_strict_ids(bool on) { strict_ids_ = on; }
    std::size_t node_count() const { return nodes_.size(); }
    std::size_t state_count() const { return states_.size(); }
    std::vector<std::string> focusable_ids() const;
    TextEngine& text() { return text_; }
    Icons& icons() { return icons_; }
    double now() const { return frame_.now; }
    float dt() const { return dt_; }
    bool reduced() const { return frame_.reduced_motion; }
    Glyphs glyphs() const { return frame_.glyphs; }
    const FrameInput& frame() const { return frame_; }
    std::string id_scope() const;  // the current container's id (for children ids)
    // Whether what is declared now goes into a mirrored (right-aligned) container (Box::mirror).
    bool mirrored() const;
    // Ids declared until the matching pop get this prefix (the same content declared twice: a readout's old and
    // new content).
    void push_prefix(const std::string& p) { prefixes_.push_back(prefix_); prefix_ += p; }
    void pop_prefix() {
        prefix_ = prefixes_.back();
        prefixes_.pop_back();
    }
    const std::string& prefix() const { return prefix_; }

    // Scrolling a container by hand (ids as declared, with any prefix). scroll_to_end may come before the container
    // is declared in the frame (a log following its end); `snap`: no animation.
    void scroll_by(const std::string& container, float dy);
    void scroll_to_end(const std::string& container, bool snap = false);

private:
    struct Node {
        std::string id;
        Box box;
        PaintFn paint, paint_after;
        MeasureFn measure;
        std::optional<Focus> focus;
        int parent = -1;
        std::vector<int> children;
        bool modal = false;
        bool mirrored = false;  // Box::mirror here or above
        float slot_x = 0;       // the left edge of the room its parent gave it (the seam fit measures from it)
        // layout
        float pref_w = 0, w = 0, h = 0, x = 0, y = 0, content_h = 0;
        float fit_w = -1, fit_dx = 0;
        float scroll_used = 0;  // scroll containers: the (pixel-rounded) offset their children were placed with
        Rect clip;      // visible part (ancestors' clips and scroll viewports)
        int scroller = -1;  // nearest scroll container above
    };
    int add(std::string id, const Box& box);
    void layout();
    void measure_widths();
    void assign_widths(int n);
    float content_height(int n);
    void assign_heights(int n);
    void place(int n, float x, float y);
    bool fit_pass();
    void compute_clips(int n, Rect clip, int scroller);
    void collect_focus();
    void resolve_focus();
    void handle_mouse();
    void handle_actions();
    void keep_in_view(bool snap);
    void step_animations();
    void set_focus(int index, Device device, bool by_mouse);
    int node_index(const std::string& id) const;
    int scroll_container_of(int n) const;
    float scroll_max(int n) const;
    Rect bar_rect(int n, float& thumb_y, float& thumb_h) const;
    void paint_node(Canvas& canvas, int n);
    const Seam* seam_of(int n) const;

    TextEngine& text_;
    Icons& icons_;
    FrameInput frame_;
    float dt_ = 0;
    double last_now_ = -1;
    std::uint64_t frame_no_ = 0;
    std::vector<Node> nodes_;
    std::vector<int> stack_;
    std::unordered_map<std::string, int> index_;
    std::unordered_map<std::string, NodeState> states_;
    std::size_t duplicates_ = 0;
    std::vector<Event> events_;

    // focus
    struct Item {
        int node;
        FocusItem f;
    };
    std::vector<Item> items_;       // can take the focus
    std::vector<int> clickables_;   // nodes that take clicks (items_ and click-only ones)
    std::vector<int> locked_;       // locked boxes (Box::locked), outermost first
    std::vector<int> locked_items_; // items inside them (what an unlocking click names)
    int press_locked_ = -1;         // the locked box a press began on
    std::string hovered_;
    int item_of_node(int node) const;
    Vec2 drawn_shift(int node, float* opacity = nullptr) const;  // the drawing shift of a node and its ancestors
    float lock_shift(int node, float lock) const;                // a locked box's move away from its seam
    std::string focused_, focus_before_modal_, modal_id_;
    std::string highlight_id_;  // the item the highlight reached (it then follows that item's layout exactly)
    int highlight_side_ = 0;    // the half it is on (-1 crimson, 1 blue, 0 no seam): it jumps between halves
    int modal_ = -1;
    double modal_opened_ = -1;
    Rect last_focus_rect_{};
    bool focus_by_mouse_ = false;
    bool snap_next_ = true;
    WrapRule wrap_{};
    std::function<std::string(const std::string&)> fallback_;
    HighlightFn highlight_paint_;
    RectSpring highlight_{theme::motion::kFocus};
    std::string highlight_container_ = "\x01";
    Rect highlight_screen_{};
    float highlight_alpha_ = 0;
    bool highlight_skewed_ = true;
    int press_node_ = -1;
    int drag_scroller_ = -1;
    std::string anchor_id_;
    float anchor_y_ = 0;
    bool user_scrolled_ = false;
    bool animating_ = false, paint_animating_ = false, paint_looping_ = false, strict_ids_ = true;
    std::string prefix_;
    std::vector<std::string> prefixes_;
};

}  // namespace ttt2::ui
