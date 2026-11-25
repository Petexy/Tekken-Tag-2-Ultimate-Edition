// Unit tests of the interface toolkit (no window, no renderer): layout, focus navigation, input arbitration timings,
// springs, text measuring / ellipsis / wrapping, per-id state. A tiny runner: each TEST registers itself; the program
// runs all (or those whose name contains argv[1]) and exits non-zero when any check failed.
#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

#include "ttt2ui/anim.h"
#include "ttt2ui/focus.h"
#include "ttt2ui/input.h"
#include "ttt2ui/text.h"
#include "ttt2ui/ui.h"
#include "ttt2ui/window.h"

using namespace ttt2::ui;

namespace {

struct Test {
    const char* name;
    std::function<void()> run;
};
std::vector<Test>& tests() {
    static std::vector<Test> t;
    return t;
}
struct Register {
    Register(const char* name, std::function<void()> f) { tests().push_back({name, std::move(f)}); }
};
int g_failed = 0, g_checks = 0;
const char* g_current = "";

void check(bool ok, const std::string& what, int line) {
    ++g_checks;
    if (!ok) {
        ++g_failed;
        std::printf("FAIL %s (line %d): %s\n", g_current, line, what.c_str());
    }
}
#define CHECK(cond) check((cond), #cond, __LINE__)
#define CHECK_NEAR(a, b, eps)            \
    check(std::fabs((a) - (b)) <= (eps), \
          std::string(#a " ~ " #b ": ") + std::to_string(a) + " vs " + std::to_string(b), __LINE__)
#define TEST(name)                                                                                                   \
    void name();                                                                                                     \
    Register reg_##name(#name, name);                                                                                \
    void name()

// A Ui without a renderer (measuring only).
struct Harness {
    TextureRegistry textures;
    TextEngine text{textures};
    Icons icons{textures};
    Ui ui{text, icons};
    double now = 0;
    Harness() { text.set_system_fallback(false); }
    FrameInput frame(Vec2 size = {1280, 800}) {
        FrameInput f;
        f.size = size;
        f.now = now;
        return f;
    }
    // One frame: declare, then end; the clock moves 1/60 s after it.
    std::vector<Event> run(const std::function<void(Ui&)>& declare, std::vector<ActionEvent> actions = {},
                           MouseState mouse = {}, Vec2 size = {1280, 800}) {
        FrameInput f = frame(size);
        f.actions = std::move(actions);
        f.mouse = mouse;
        ui.begin(f);
        declare(ui);
        ui.end();
        now += 1.0 / 60;
        return ui.take_events();
    }
};

Box fixed(float w, float h) {
    Box b;
    b.w = Size::fixed(w);
    b.h = Size::fixed(h);
    return b;
}
ActionEvent act(Action a, double t, Device d = Device::Keyboard) {
    ActionEvent e;
    e.action = a;
    e.device = d;
    e.press_time = t;
    return e;
}
bool has_event(const std::vector<Event>& ev, EventKind k, const std::string& id = {}) {
    for (const Event& e : ev)
        if (e.kind == k && (id.empty() || e.id == id)) return true;
    return false;
}

// ---- layout ---------------------------------------------------------------------------------------------------------

TEST(layout_column_padding_gap_margin) {
    Harness h;
    h.run([](Ui& ui) {
        auto root = ui.open("root", Box{});  // (top-level boxes fill the window: the root stretches them)
        Box col;
        col.pad = {10, 20, 10, 20};
        col.gap = 5;
        col.w = Size::fixed(300);
        auto g = ui.open("col", col);
        ui.leaf("a", fixed(100, 30), {}, {});
        Box b = fixed(50, 40);
        b.margin = {7, 3, 0, 0};
        ui.leaf("b", b, {}, {});
        Box c;
        c.h = Size::fixed(10);  // fit width in a stretching column: the column's inner width
        ui.leaf("c", c, {}, {});
    });
    const Rect a = h.ui.rect("a"), b = h.ui.rect("b"), c = h.ui.rect("c"), col = h.ui.rect("col");
    CHECK_NEAR(a.x, 10.f, .01f);
    CHECK_NEAR(a.y, 20.f, .01f);
    CHECK_NEAR(b.x, 17.f, .01f);
    CHECK_NEAR(b.y, 20 + 30 + 5 + 3.f, .01f);
    CHECK_NEAR(c.w, 280.f, .01f);
    CHECK_NEAR(c.y, 58 + 40 + 5.f, .01f);
    CHECK_NEAR(col.h, 20 + 30 + 5 + 3 + 40 + 5 + 10 + 20.f, .01f);
}

TEST(layout_row_grow_and_shrink) {
    Harness h;
    h.run([](Ui& ui) {
        Box row;
        row.layout = Layout::Row;
        row.w = Size::fixed(400);
        row.gap = 10;
        auto g = ui.open("row", row);
        ui.leaf("fixed", fixed(100, 20), {}, {});
        Box g1;
        g1.w = Size::grow(1);
        ui.leaf("g1", g1, {}, {});
        Box g3;
        g3.w = Size::grow(3);
        ui.leaf("g3", g3, {}, {});
    });
    // 400 - 100 - 2 * 10 = 280 shared 1:3.
    CHECK_NEAR(h.ui.rect("g1").w, 70.f, .01f);
    CHECK_NEAR(h.ui.rect("g3").w, 210.f, .01f);
    CHECK_NEAR(h.ui.rect("g3").x, 100 + 10 + 70 + 10.f, .01f);
    // Fit children too wide for the row shrink toward their minimum.
    Harness s;
    s.run([](Ui& ui) {
        Box row;
        row.layout = Layout::Row;
        row.w = Size::fixed(200);
        auto g = ui.open("row", row);
        for (const char* id : {"x", "y"}) {
            Box b;
            b.min_w = 50;
            ui.leaf(id, b, [](float) { return Vec2{150, 10}; }, {});
        }
    });
    CHECK_NEAR(s.ui.rect("x").w + s.ui.rect("y").w, 200.f, .01f);
    CHECK(s.ui.rect("x").w >= 50);
}

TEST(layout_heights_measured_at_widths) {
    // A wrapping leaf: its height comes from the width it got (pass 2 after pass 1).
    Harness h;
    h.run([](Ui& ui) {
        Box col;
        col.w = Size::fixed(100);
        auto g = ui.open("col", col);
        ui.leaf("text", Box{}, [](float w) { return Vec2{std::min(w, 400.f), std::ceil(400 / std::max(1.f, w)) * 10}; },
                {});
        ui.leaf("after", fixed(10, 10), {}, {});
    });
    CHECK_NEAR(h.ui.rect("text").w, 100.f, .01f);
    CHECK_NEAR(h.ui.rect("text").h, 40.f, .01f);
    CHECK_NEAR(h.ui.rect("after").y, 40.f, .01f);
}

TEST(layout_wrapping_row) {
    Harness h;
    h.run([](Ui& ui) {
        auto root = ui.open("root", Box{});
        Box row;
        row.layout = Layout::Row;
        row.wrap = true;
        row.w = Size::fixed(250);
        row.gap = 10;
        row.line_gap = 4;
        auto g = ui.open("row", row);
        for (int i = 0; i < 5; ++i) ui.leaf("t" + std::to_string(i), fixed(70, 92), {}, {});
    });
    // 3 per line (3*70 + 2*10 = 230 <= 250).
    CHECK_NEAR(h.ui.rect("t2").y, 0.f, .01f);
    CHECK_NEAR(h.ui.rect("t3").x, 0.f, .01f);
    CHECK_NEAR(h.ui.rect("t3").y, 96.f, .01f);
    CHECK_NEAR(h.ui.rect("row").h, 92 * 2 + 4.f, .01f);
}

TEST(layout_grow_height_and_stack) {
    Harness h;
    h.run([](Ui& ui) {
        auto g = ui.open("col", fixed(100, 300));
        ui.leaf("top", fixed(100, 50), {}, {});
        Box grow;
        grow.h = Size::grow();
        ui.leaf("rest", grow, {}, {});
    });
    CHECK_NEAR(h.ui.rect("rest").h, 250.f, .01f);
    Harness s;
    s.run([](Ui& ui) {
        Box st = fixed(200, 100);
        st.layout = Layout::Stack;
        st.align = Align::Center;
        auto g = ui.open("stack", st);
        ui.leaf("mid", fixed(20, 10), {}, {});
    });
    CHECK_NEAR(s.ui.rect("mid").x, 90.f, .01f);
    CHECK_NEAR(s.ui.rect("mid").y, 45.f, .01f);
}

TEST(layout_seam_staircase_fit) {
    // Crimson boxes end `fit_gap` before the seam (skewed: at their middle; rect: at their bottom); blue boxes start
    // that far after it.
    Harness h;
    const Seam seam{640, 414, theme::kSeamTan};
    h.run([&](Ui& ui) {
        Box half;
        half.seam = seam;
        half.margin = {38, 102, 0, 0};
        half.w = Size::fixed(500);
        auto g = ui.open("crimson", half);
        for (int i = 0; i < 3; ++i) {
            Box row;
            row.h = Size::fixed(58);
            row.margin.bottom = 10;
            row.fit = i == 2 ? SeamFit::CrimsonRect : SeamFit::CrimsonSkewed;
            ui.leaf("r" + std::to_string(i), row, {}, {});
        }
    });
    for (int i = 0; i < 2; ++i) {
        const Rect r = h.ui.rect("r" + std::to_string(i));
        CHECK_NEAR(r.right(), std::round(seam.x_at(r.y + r.h / 2) - theme::kSeamGap), .51f);
    }
    const Rect r2 = h.ui.rect("r2");
    CHECK_NEAR(r2.right(), std::round(seam.x_at(r2.bottom()) - theme::kSeamGap), .51f);
    CHECK(h.ui.rect("r1").w < h.ui.rect("r0").w);  // lower rows are narrower (the seam leans left)
    Harness b;
    b.run([&](Ui& ui) {
        Box half;
        half.seam = seam;
        half.margin = {500, 102, 0, 0};
        half.w = Size::fixed(600);
        auto g = ui.open("blue", half);
        Box row;
        row.h = Size::fixed(40);
        row.fit = SeamFit::BlueRect;
        ui.leaf("x", row, {}, {});
    });
    const Rect x = b.ui.rect("x");
    CHECK_NEAR(x.x, std::round(seam.x_at(x.y) + theme::kSeamGap), .51f);
}

TEST(layout_mirror_right_aligned) {
    // A mirrored (blue) half anchors everything to its right edge; fitted boxes keep the gap from the
    // seam on their left; rows go to the right end.
    Harness h;
    const Seam seam{640, 414, theme::kSeamTan};
    h.run([&](Ui& ui) {
        Box half;
        half.seam = seam;
        half.mirror = true;
        half.margin = {640, 102, 0, 0};
        half.w = Size::fixed(560);
        auto g = ui.open("blue", half);
        CHECK(ui.mirrored());
        ui.leaf("fixed", fixed(100, 30), {}, {});
        Box fb = fixed(200, 30);
        fb.fit = SeamFit::BlueRect;
        ui.leaf("fitted", fb, {}, {});
        Box wide;
        wide.h = Size::fixed(30);
        wide.fit = SeamFit::BlueRect;
        ui.leaf("wide", wide, {}, {});
        Box row;
        row.layout = Layout::Row;
        row.gap = 10;
        auto r = ui.open("row", row);
        ui.leaf("b1", fixed(80, 30), {}, {});
        ui.leaf("b2", fixed(80, 30), {}, {});
    });
    CHECK_NEAR(h.ui.rect("fixed").right(), 1200, .51f);
    CHECK_NEAR(h.ui.rect("fitted").right(), 1200, .51f);
    const Rect w = h.ui.rect("wide");
    CHECK_NEAR(w.right(), 1200, .51f);
    CHECK_NEAR(w.x, std::round(seam.x_at(w.y) + theme::kSeamGap), .51f);  // (the slack: its left side only)
    CHECK_NEAR(h.ui.rect("b2").right(), 1200, .51f);
    CHECK_NEAR(h.ui.rect("b1").right(), h.ui.rect("b2").x - 10, .51f);
    // Crimson (not mirrored) stays left-aligned.
    Harness c;
    c.run([&](Ui& ui) {
        Box half;
        half.seam = seam;
        half.margin = {40, 102, 0, 0};
        half.w = Size::fixed(560);
        auto g = ui.open("crimson", half);
        CHECK(!ui.mirrored());
        ui.leaf("fixed", fixed(100, 30), {}, {});
    });
    CHECK_NEAR(c.ui.rect("fixed").x, 40, .51f);
}

TEST(layout_audit_finds_seam_crossings) {
    // Ui::audit: a painted crimson box running into the gutter is reported, a fitted one not.
    const Seam seam{640, 414, theme::kSeamTan};
    auto declare = [&](bool fitted) {
        return [&seam, fitted](Ui& ui) {
            Box half;
            half.seam = seam;
            half.margin = {40, 102, 0, 0};
            half.w = Size::fixed(700);
            auto g = ui.open("crimson", half);
            Box row;
            row.h = Size::fixed(40);
            if (fitted) row.fit = SeamFit::CrimsonRect;
            else row.w = Size::fixed(640);
            ui.leaf("row", row, {}, [](PaintContext&) {});
        };
    };
    Harness bad;
    bad.run(declare(false));
    const std::vector<std::string> p = bad.ui.audit();
    CHECK(p.size() == 1);
    CHECK(!p.empty() && p[0].find("row (crimson)") == 0);
    Harness good;
    good.run(declare(true));
    CHECK(good.ui.audit(theme::kSeamGap - 1).empty());
}

TEST(focus_highlight_follows_moving_item) {
    // Once the highlight reached its item it is drawn exactly on it while the layout moves (a
    // springing seam narrows the rows), and a new focus is on its item from the first frame (snap).
    Harness h;
    float width = 400;
    auto declare = [&](Ui& ui) {
        Focus f;
        ui.leaf("a", fixed(width, 40), {}, {}, &f);
    };
    h.run(declare);
    for (int i = 0; i < 30; ++i) h.run(declare);
    CHECK(!h.ui.focus_rect().empty());
    CHECK_NEAR(h.ui.highlight_rect().w, h.ui.focus_rect().w, .01f);
    for (int i = 0; i < 20; ++i) {
        width -= 7;
        h.run(declare);
        CHECK_NEAR(h.ui.highlight_rect().w, h.ui.focus_rect().w, .01f);
    }
}

TEST(focus_drill_in_lock) {
    // A locked half takes no focus (keys or hover) so the pointer can travel over it to the other
    // half's actions; a left click anywhere on it is Unlock (naming the item clicked, else the half); it fades and
    // moves back while locked.
    Harness h;
    bool lock = false;
    auto declare = [&](Ui& ui) {
        Box hb{.layout = Layout::Row, .gap = 100};
        hb.seam = Seam{450, 150, theme::kSeamTan};
        auto halves = ui.open("halves", hb);
        {
            Box c = fixed(400, 300);
            c.locked = lock;
            auto g = ui.open("crimson", c);
            for (const char* id : {"a", "b"}) {
                Focus f;
                ui.leaf(id, fixed(300, 40), {}, {}, &f);
            }
        }
        auto g = ui.open("blue", fixed(400, 300));
        for (const char* id : {"x", "y"}) {
            Focus f;
            ui.leaf(id, fixed(300, 40), {}, {}, &f);
        }
    };
    h.run(declare);
    CHECK(h.ui.focused() == "a");
    // Accept on "a" -> the app drills in: lock crimson, focus the blue action.
    lock = true;
    h.ui.focus("x", true);
    h.run(declare);
    CHECK(h.ui.focused() == "x");
    CHECK(h.ui.highlight_rect() == h.ui.focus_rect());  // (into the other half: no flight across)
    auto ev = h.run(declare, {act(Action::Left, h.now)});
    CHECK(h.ui.focused() == "x");
    CHECK(has_event(ev, EventKind::Bump));
    // The pointer crosses crimson ("b") on its way: no focus change; on "y" it focuses.
    MouseState m;
    m.inside = true;
    m.moved = true;
    m.pos = h.ui.rect("b").center();
    h.run(declare, {}, m);
    CHECK(h.ui.focused() == "x");
    m.pos = h.ui.rect("y").center();
    h.run(declare, {}, m);
    CHECK(h.ui.focused() == "y");
    for (int i = 0; i < 40; ++i) h.run(declare);
    CHECK_NEAR(h.ui.state("crimson")->lock, 1.f, .001f);
    // A click on "b": Unlock naming "b" (no Activate); a click on crimson's empty part: Unlock naming the half.
    m.moved = false;
    m.pos = h.ui.rect("b").center();
    m.pressed = m.down = true;
    h.run(declare, {}, m);
    m.pressed = m.down = false;
    m.released = true;
    ev = h.run(declare, {}, m);
    CHECK(has_event(ev, EventKind::Unlock, "b"));
    for (const Event& e : ev)
        if (e.kind == EventKind::Unlock) CHECK(e.delta == 1);
    CHECK(!has_event(ev, EventKind::Activate));
    m.released = false;
    m.pos = {h.ui.rect("crimson").x + 10, h.ui.rect("crimson").bottom() - 10};
    m.pressed = m.down = true;
    h.run(declare, {}, m);
    m.pressed = m.down = false;
    m.released = true;
    ev = h.run(declare, {}, m);
    CHECK(has_event(ev, EventKind::Unlock, "crimson"));
    for (const Event& e : ev)
        if (e.kind == EventKind::Unlock) CHECK(e.delta == 0);
    // Unlocked: the app focuses the item; it fades back in.
    lock = false;
    h.ui.focus("b", true);
    m.released = false;
    h.run(declare, {}, m);
    CHECK(h.ui.focused() == "b");
    for (int i = 0; i < 40; ++i) h.run(declare);
    CHECK_NEAR(h.ui.state("crimson")->lock, 0.f, .001f);
}

TEST(layout_scroll_keeps_focus_in_view) {
    Harness h;
    auto declare = [](Ui& ui) {
        Box s = fixed(200, 100);
        s.scroll = true;
        auto g = ui.open("list", s);
        for (int i = 0; i < 10; ++i) {
            Focus f;
            ui.leaf("i" + std::to_string(i), fixed(200, 40), {}, {}, &f);
        }
    };
    h.run(declare);
    CHECK(h.ui.focused() == "i0");
    // Down x5: the list scrolls so the focused row (and its highlight margin) is inside.
    for (int i = 0; i < 5; ++i) h.run(declare, {act(Action::Down, h.now)});
    CHECK(h.ui.focused() == "i5");
    for (int i = 0; i < 120; ++i) h.run(declare);
    const Rect r = h.ui.rect("i5"), view = h.ui.rect("list");
    CHECK(r.y >= view.y - .5f);
    CHECK(r.bottom() <= view.bottom() + .5f);
    CHECK(!h.ui.animating());
    // End jumps to the last item and scrolls to the end.
    h.run(declare, {act(Action::End, h.now)});
    CHECK(h.ui.focused() == "i9");
    for (int i = 0; i < 120; ++i) h.run(declare);
    CHECK_NEAR(h.ui.state("list")->scroll.value, 400 - 100.f, .5f);
}

TEST(layout_scroll_anchoring) {
    // Lines inserted above the focused row (a refresh) move the scroll offset with it: the row stays in place.
    Harness h;
    int extra = 0;
    auto declare = [&](Ui& ui) {
        Box s = fixed(200, 100);
        s.scroll = true;
        auto g = ui.open("list", s);
        for (int i = 0; i < extra; ++i) ui.leaf("new" + std::to_string(i), fixed(200, 40), {}, {});
        for (int i = 0; i < 10; ++i) {
            Focus f;
            ui.leaf("i" + std::to_string(i), fixed(200, 40), {}, {}, &f);
        }
    };
    h.run(declare);
    h.ui.focus("i6", true);
    for (int i = 0; i < 60; ++i) h.run(declare);
    const float before = h.ui.rect("i6").y;
    extra = 2;
    h.run(declare);
    CHECK_NEAR(h.ui.rect("i6").y, before, .5f);
}

// ---- focus ----------------------------------------------------------------------------------------------------------

TEST(focus_navigate_grid) {
    std::vector<FocusItem> grid;
    for (int y = 0; y < 3; ++y)
        for (int x = 0; x < 3; ++x) grid.push_back({{x * 100.f, y * 60.f, 90, 50}, 0});
    CHECK(navigate(grid, 4, Dir::Down) == 7);
    CHECK(navigate(grid, 4, Dir::Up) == 1);
    CHECK(navigate(grid, 4, Dir::Left) == 3);
    CHECK(navigate(grid, 4, Dir::Right) == 5);
    CHECK(navigate(grid, 2, Dir::Right) == -1);  // nothing there: the caller bumps
    CHECK(navigate(grid, 2, Dir::Right, WrapRule{true, false}) == 0);
    CHECK(navigate(grid, 7, Dir::Down, WrapRule{false, true}) == 1);
    // Up/down prefer their own group (the half) even when the other is nearer.
    std::vector<FocusItem> halves = {{{0, 0, 300, 50}, -1}, {{0, 200, 300, 50}, -1}, {{320, 100, 300, 50}, 1}};
    CHECK(navigate(halves, 0, Dir::Down) == 1);
    CHECK(nearest(grid, {150, 70, 20, 20}) == 4);
    // Items the lost rect overlaps come first, even when another's centre is nearer.
    const std::vector<FocusItem> two = {{{0, 0, 100, 10}, 0}, {{120, 0, 10, 10}, 0}};
    CHECK(nearest(two, {95, 0, 10, 10}) == 0);
}

TEST(focus_disappearing_item_goes_to_nearest_or_fallback) {
    Harness h;
    bool with_b = true;
    auto declare = [&](Ui& ui) {
        auto g = ui.open("col", Box{.gap = 10});
        for (const char* id : {"a", "b", "c"}) {
            if (std::string(id) == "b" && !with_b) continue;
            Focus f;
            ui.leaf(id, fixed(100, 30), {}, {}, &f);
        }
    };
    h.run(declare);
    h.ui.focus("c");
    h.run(declare);
    CHECK(h.ui.focused() == "c");
    h.ui.focus("b");
    h.run(declare);
    with_b = false;
    h.run(declare);
    CHECK(h.ui.focused() == "c" || h.ui.focused() == "a");
    // The app's fallback comes first.
    with_b = true;
    h.ui.focus("b");
    h.run(declare);
    h.ui.set_fallback([](const std::string& lost) { return lost == "b" ? std::string("a") : std::string(); });
    with_b = false;
    h.run(declare);
    CHECK(h.ui.focused() == "a");
}

TEST(focus_disabled_items_stay_focusable) {
    Harness h;
    auto declare = [](Ui& ui) {
        auto g = ui.open("col", Box{});
        Focus a;
        ui.leaf("a", fixed(100, 30), {}, {}, &a);
        Focus b;
        b.disabled = true;
        ui.leaf("b", fixed(100, 30), {}, {}, &b);
    };
    h.run(declare);
    auto ev = h.run(declare, {act(Action::Down, h.now)});
    CHECK(h.ui.focused() == "b");
    ev = h.run(declare, {act(Action::Accept, h.now)});
    CHECK(has_event(ev, EventKind::Refused, "b"));
    CHECK(!has_event(ev, EventKind::Activate));
}

TEST(focus_explicit_neighbours_and_bump) {
    Harness h;
    auto declare = [](Ui& ui) {
        auto g = ui.open("row", Box{.layout = Layout::Row});
        Focus a;
        a.right = "c";
        a.up = "-";
        ui.leaf("a", fixed(50, 30), {}, {}, &a);
        Focus b;
        ui.leaf("b", fixed(50, 30), {}, {}, &b);
        Focus c;
        ui.leaf("c", fixed(50, 30), {}, {}, &c);
    };
    h.run(declare);
    h.run(declare, {act(Action::Right, h.now)});
    CHECK(h.ui.focused() == "c");
    h.ui.focus("a");
    h.run(declare);
    auto ev = h.run(declare, {act(Action::Up, h.now)});
    CHECK(has_event(ev, EventKind::Bump));
    CHECK(h.ui.focused() == "a");
    // Adjust items turn Left/Right into Change.
    Harness s;
    auto sel = [](Ui& ui) {
        Focus f;
        f.adjust = true;
        ui.leaf("sel", fixed(100, 30), {}, {}, &f);
    };
    s.run(sel);
    ev = s.run(sel, {act(Action::Left, s.now)});
    CHECK(has_event(ev, EventKind::Change, "sel"));
    CHECK(ev.size() >= 1 && ev[0].delta == -1);
}

TEST(focus_modal_scope_and_press_gate) {
    Harness h;
    bool open = false;
    double opened_at = 0;
    auto declare = [&](Ui& ui) {
        {
            auto g = ui.open("page", Box{});
            for (const char* id : {"x", "y"}) {
                Focus f;
                ui.leaf(id, fixed(100, 30), {}, {}, &f);
            }
        }
        if (open) {
            Box m = fixed(400, 200);
            m.margin = {300, 300, 0, 0};
            auto g = ui.modal("dialog", m);
            for (const char* id : {"ok", "cancel"}) {
                Focus f;
                ui.leaf(id, fixed(100, 30), {}, {}, &f);
            }
        }
    };
    h.run(declare);
    h.run(declare, {act(Action::Down, h.now)});
    CHECK(h.ui.focused() == "y");
    // The Accept that opens the dialog is still held: its press began before the dialog.
    const double press = h.now - 1.0 / 60;  // (pressed during the frame before)
    open = true;
    opened_at = h.now;
    h.run(declare);
    CHECK(h.ui.focused() == "ok");
    auto ev = h.run(declare, {act(Action::Accept, press)});
    CHECK(!has_event(ev, EventKind::Activate));
    // A new press works, and the focus never leaves the dialog.
    ev = h.run(declare, {act(Action::Accept, h.now)});
    CHECK(has_event(ev, EventKind::Activate, "ok"));
    for (int i = 0; i < 4; ++i) h.run(declare, {act(Action::Up, h.now)});
    CHECK(h.ui.focused() == "ok" || h.ui.focused() == "cancel");
    // A click outside it.
    MouseState m;
    m.inside = true;
    m.pos = {10, 10};
    m.pressed = m.down = true;
    ev = h.run(declare, {}, m);
    CHECK(has_event(ev, EventKind::ClickOutside, "dialog"));
    (void)opened_at;
    // Closed: the focus is back where it was.
    open = false;
    h.run(declare);
    CHECK(h.ui.focused() == "y");
}

TEST(focus_mouse_hover_and_click) {
    Harness h;
    auto declare = [](Ui& ui) {
        auto g = ui.open("col", Box{});
        for (const char* id : {"a", "b"}) {
            Focus f;
            ui.leaf(id, fixed(100, 30), {}, {}, &f);
        }
        Focus z;
        z.adjust = true;
        z.zones[0] = {0, 20, 1};
        z.zone_count = 1;
        ui.leaf("sel", fixed(100, 30), {}, {}, &z);
    };
    h.run(declare);
    MouseState m;
    m.inside = true;
    m.pos = {50, 45};
    // Resting pointer (no real motion): no focus change.
    h.run(declare, {}, m);
    CHECK(h.ui.focused() == "a");
    m.moved = true;
    h.run(declare, {}, m);
    CHECK(h.ui.focused() == "b");
    m.moved = false;
    m.pressed = m.down = true;
    h.run(declare, {}, m);
    m.pressed = m.down = false;
    m.released = true;
    auto ev = h.run(declare, {}, m);
    CHECK(has_event(ev, EventKind::Activate, "b"));
    // A click in a zone (10 points from the right edge of "sel") is Change +1.
    m.pos = {90, 75};
    m.released = false;
    m.pressed = m.down = true;
    h.run(declare, {}, m);
    m.pressed = m.down = false;
    m.released = true;
    ev = h.run(declare, {}, m);
    CHECK(has_event(ev, EventKind::Change, "sel"));
}

// ---- per-id state ---------------------------------------------------------------------------------------------------

TEST(state_swept_when_not_declared) {
    Harness h;
    bool both = true;
    auto declare = [&](Ui& ui) {
        ui.leaf("a", fixed(10, 10), {}, {});
        if (both) ui.leaf("b", fixed(10, 10), {}, {});
    };
    h.run(declare);
    CHECK(h.ui.state("b") != nullptr);
    h.ui.state("b")->user[0] = 42;
    both = false;
    h.run(declare);
    CHECK(h.ui.state("b") == nullptr);
    both = true;
    h.run(declare);
    CHECK(h.ui.state("b") && h.ui.state("b")->user[0] == 0);  // a new start
    // Ids declared twice are counted (and asserted in debug builds unless turned off).
    h.ui.set_strict_ids(false);
    h.run([](Ui& ui) {
        ui.leaf("same", fixed(10, 10), {}, {});
        ui.leaf("same", fixed(10, 10), {}, {});
    });
    CHECK(h.ui.duplicate_ids() == 1);
    // Prefixes keep repeated content apart.
    h.run([](Ui& ui) {
        ui.leaf("x", fixed(10, 10), {}, {});
        ui.push_prefix("old:");
        ui.leaf("x", fixed(10, 10), {}, {});
        ui.pop_prefix();
    });
    CHECK(h.ui.duplicate_ids() == 0);
    CHECK(h.ui.has("old:x"));
}

// ---- input ----------------------------------------------------------------------------------------------------------

RawEvent key(int scancode, double t, bool down = true) {
    RawEvent e;
    e.kind = down ? RawEvent::KeyDown : RawEvent::KeyUp;
    e.device = Device::Keyboard;
    e.device_id = 1;
    e.code = scancode;
    e.time = t;
    return e;
}
RawEvent button(int b, double t, bool down = true, Glyphs kind = Glyphs::Xbox) {
    RawEvent e;
    e.kind = down ? RawEvent::ButtonDown : RawEvent::ButtonUp;
    e.device = Device::Gamepad;
    e.device_id = 9;
    e.code = b;
    e.time = t;
    e.pad_kind = kind;
    return e;
}
constexpr int kDown = 81, kEnter = 40, kEsc = 41, kA = 4;  // SDL scancodes

TEST(input_same_press_from_two_devices_counts_once) {
    InputRouter r;
    r.feed(key(kEnter, 1.0));
    r.feed(button(pad::South, 1.05));
    r.tick(1.06);
    auto a = r.take_actions();
    CHECK(a.size() == 1 && a[0].action == Action::Accept);
    // ... but not when far enough apart.
    r.feed(key(kEnter, 1.1, false));
    r.feed(button(pad::South, 1.1, false));
    r.feed(key(kEnter, 2.0));
    r.feed(button(pad::South, 2.0 + theme::input::kSamePress + .01));
    r.tick(2.2);
    CHECK(r.take_actions().size() == 2);
}

TEST(input_accept_back_never_repeat_moves_do) {
    InputRouter r;
    r.feed(key(kEnter, 0));
    r.feed(key(kEsc, 0));
    r.feed(key(kDown, 0));
    // OS repeats are ignored.
    RawEvent rep = key(kDown, .3);
    rep.os_repeat = true;
    r.feed(rep);
    r.tick(.39);
    auto a = r.take_actions();
    CHECK(a.size() == 3);
    r.tick(theme::input::kKeyRepeatDelay + .001);
    a = r.take_actions();
    CHECK(a.size() == 1 && a[0].action == Action::Down && a[0].repeat);
    r.tick(theme::input::kKeyRepeatDelay + 5 * theme::input::kKeyRepeatRate + .002);
    a = r.take_actions();
    CHECK(a.size() == 5);
    for (const auto& e : a) CHECK(e.action == Action::Down);
    r.feed(key(kDown, 1.0, false));
    r.tick(2.0);
    CHECK(r.take_actions().empty());
}

TEST(input_nintendo_confirms_with_east) {
    InputRouter r;
    r.feed(button(pad::East, 0, true, Glyphs::Nintendo));
    r.tick(0);
    auto a = r.take_actions();
    CHECK(a.size() == 1 && a[0].action == Action::Accept);
    r.feed(button(pad::East, .1, true, Glyphs::Xbox));
    r.tick(.5);
    a = r.take_actions();
    CHECK(a.size() == 1 && a[0].action == Action::Back);
    CHECK(r.glyphs() == Glyphs::Xbox);
}

TEST(input_mouse_ignored_right_after_navigation) {
    InputRouter r;
    r.feed(key(kDown, 1.0));
    r.feed(key(kDown, 1.05, false));
    RawEvent m;
    m.kind = RawEvent::MouseMove;
    m.device = Device::Mouse;
    m.pos = {100, 100};
    m.delta = {10, 10};
    m.time = 1.1;
    r.feed(m);
    CHECK(!r.take_mouse().moved);
    m.time = 1.0 + theme::input::kMouseAfterNav + .05;
    m.pos = {120, 120};
    r.feed(m);
    CHECK(r.take_mouse().moved);
}

TEST(input_capture_rules) {
    InputRouter r;
    // Started by a pad: the keyboard is ignored for a while.
    r.begin_capture(Device::Gamepad, 5.0);
    r.feed(key(kA, 5.1));
    CHECK(r.take_capture().empty());
    r.feed(key(kA, 5.1, false));
    r.feed(key(kA, 5.0 + theme::input::kCaptureKeyboardIgnore + .01));
    auto c = r.take_capture();
    CHECK(c.size() == 1 && c[0].kind == CaptureEvent::Key && c[0].scancode == kA);
    CHECK(r.take_actions().empty());  // no actions while capturing
    r.feed(button(pad::South, 6));
    c = r.take_capture();
    CHECK(c.size() == 1 && c[0].kind == CaptureEvent::CancelByPad);
    r.end_capture();
    // A key held before the capture began: its key-up is not a capture.
    InputRouter k;
    k.feed(key(kEnter, 0));
    k.begin_capture(Device::Keyboard, .01);
    k.feed(key(kEnter, .2, false));
    CHECK(k.take_capture().empty());
}

// ---- springs --------------------------------------------------------------------------------------------------------

TEST(springs_settle_without_runaway) {
    for (const theme::SpringSpec spec :
         {theme::motion::kFocus, theme::motion::kSeam, theme::motion::kTabBar, theme::motion::kScroll}) {
        Spring s{0, spec};
        s.target = 100;
        float peak = 0;
        double t = 0;
        while (t < 3) {
            s.step(1.f / 60);
            peak = std::max(peak, s.value);
            t += 1.0 / 60;
        }
        CHECK(s.settled(.05f));
        // Under-damped springs overshoot a little; critically damped ones never.
        const float overshoot = (peak - 100) / 100;
        if (spec.ratio >= 1) CHECK(overshoot <= .001f);
        else CHECK(overshoot < .2f);
    }
    // The same motion at any frame rate (fixed sub-steps).
    Spring a{0, theme::motion::kFocus}, b{0, theme::motion::kFocus};
    a.target = b.target = 50;
    for (int i = 0; i < 15; ++i) a.step(1.f / 30);
    for (int i = 0; i < 72; ++i) b.step(1.f / 144);
    CHECK_NEAR(a.value, b.value, .5f);
    // A long pause snaps instead of exploding.
    Spring c{0, theme::motion::kFocus};
    c.target = 10;
    c.step(5);
    CHECK_NEAR(c.value, 10.f, .001f);
    // Tweens and curves.
    CHECK_NEAR(ease::in_out_cubic(.5f), .5f, .001f);
    CHECK_NEAR(ease::out_expo_like(1), 1.f, .001f);
    Tween tw;
    tw.begin(1, .5f);
    CHECK_NEAR(tw.at(1.25), .5f, .001f);
    CHECK(!tw.active(2));
}

// ---- text -----------------------------------------------------------------------------------------------------------

TEST(text_measure_ellipsis_wrap) {
    TextureRegistry textures;
    TextEngine t(textures);
    t.set_system_fallback(false);
    const TextStyle st = theme::text::kPara;
    const float w1 = t.width(st, "Tekken"), w2 = t.width(st, "Tekken Tag");
    CHECK(w1 > 10 && w2 > w1);
    // Capitals and tracking.
    const TextStyle up = theme::text::kLabel;
    CHECK(t.width(up, "menu") == t.width(up, "MENU"));
    // Measuring follows the scale's quantised sizes but stays in points.
    t.set_scale(2);
    CHECK_NEAR(t.width(st, "Tekken"), w1, w1 * .06f);
    t.set_scale(1);
    // Ellipsis at the end and in the middle (paths).
    const std::string path = "/home/someone/Games/Tekken Tag Tournament 2/the game/folder";
    const std::string end = t.ellipsize(st, path, 150);
    CHECK(t.width(st, end) <= 150.5f);
    CHECK(end.size() >= 3 && end.substr(end.size() - 3) == "…");
    const std::string mid = t.ellipsize(st, path, 200, Ellipsis::Middle);
    CHECK(t.width(st, mid) <= 200.5f);
    CHECK(mid.rfind("/home", 0) == 0);
    CHECK(mid.substr(mid.size() - 6) == "folder");
    CHECK(t.ellipsize(st, "short", 500) == "short");
    // Wrapping: lines fit, words are kept, a long word breaks anywhere, newlines break.
    const auto& lines = t.wrap(st, "In the game: on the select screen next time it starts.", 150);
    CHECK(lines.size() >= 2);
    for (const TextLine& l : lines) CHECK(l.width <= 150.5f);
    const auto& word = t.wrap(st, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 60);
    CHECK(word.size() >= 3);
    CHECK(t.wrap(st, "one\ntwo", 500).size() == 2);
    CHECK_NEAR(t.wrapped_height(st, "one\ntwo", 500), 2 * t.line_height(st), .01f);
    // Invalid UTF-8 becomes U+FFFD (drawn by us); characters no face has are measured too.
    std::vector<char32_t> cps;
    decode_utf8("a\xff" "b\xc3\xa9\xed\xa0\x80" "c", cps);  // (a surrogate: one U+FFFD per byte, as browsers do)
    CHECK(cps.size() == 8 && cps[1] == 0xFFFD && cps[3] == 0xE9 && cps[4] == 0xFFFD && cps[6] == 0xFFFD &&
          cps[7] == 'c');
    CHECK(t.width(st, "\xe4\xb8\xad") > 0);
    CHECK(to_upper(U'é') == U'É' && to_upper(U'α') == U'Α' && to_upper(U'ж') == U'Ж');
    CHECK(t.has_glyph_builtin(U'A'));
}

TEST(text_system_fallback) {
    // The system's fonts (fc-match on Linux, the Fonts folders on Windows) for characters the launcher's own fonts
    // lack. Not every machine has one with Chinese letters: then the letter falls back to U+FFFD, measured all the
    // same; a face found is used only when stb_truetype accepts it.
    TextureRegistry textures;
    TextEngine t(textures);
    t.set_system_fallback(true);
    const int before = t.face_count();
    const int face = t.face_for(theme::text::kPara, U'\u4e2d');
    std::printf("     (system fallback for U+4E2D: face %d of %d, %d before)\n", face, t.face_count(), before);
    CHECK(face < t.face_count());
    CHECK(t.width(theme::text::kPara, "\xe4\xb8\xad\xe6\x96\x87") > 0);
    // A file that is not a font is refused.
    CHECK(!t.add_fallback_file("/nonexistent/font.ttf"));
}

TEST(scale_follows_window_size) {
    CHECK_NEAR(ui_scale({1280, 800}, 1), 1.f, .001f);
    CHECK_NEAR(ui_scale({960, 640}, 1), 1.f, .001f);   // smaller: the layout reflows, letters keep their size
    CHECK_NEAR(ui_scale({1920, 1200}, 1), 1.5f, .001f);
    CHECK_NEAR(ui_scale({3840, 2160}, 1), 2.f, .001f);  // at most twice
    CHECK_NEAR(ui_scale({2560, 1600}, 2), 2.f, .001f);  // a 2x display at the stage's size
    CHECK_NEAR(ui_scale({1280, 800}, 1, 1.25f), 1.25f, .001f);
    // Text size: the layout never gets smaller than the Steam Deck's 1280x800 at 150 % (853x533 points).
    CHECK_NEAR(ui_scale({1280, 800}, 1, 1.5f), 1.5f, .001f);
    CHECK_NEAR(ui_scale({960, 640}, 1, 1.5f), 1.125f, .001f);   // 853x569 points: as large as it can be
    CHECK_NEAR(ui_scale({960, 640}, 1, 1.25f), 1.125f, .001f);
    CHECK_NEAR(ui_scale({960, 600}, 1, 1.5f), 1.125f, .001f);
    CHECK_NEAR(ui_scale({2560, 1600}, 1, 1.5f), 3.f, .001f);     // 853x533 points again
    CHECK_NEAR(ui_scale({1920, 1080}, 1, 1.5f), 2.025f, .001f);  // 948x533
    CHECK_NEAR(ui_scale({1920, 1200}, 1.5f, 1.5f), 2.25f, .001f);
    CHECK_NEAR(ui_scale({800, 500}, 1, 1.5f), 1.f, .001f);       // (never smaller than without a Text size)
}

}  // namespace

int main(int argc, char** argv) {
    const std::string filter = argc > 1 ? argv[1] : "";
    int ran = 0;
    for (const Test& t : tests()) {
        if (!filter.empty() && std::string(t.name).find(filter) == std::string::npos) continue;
        g_current = t.name;
        const int before = g_failed;
        t.run();
        ++ran;
        std::printf("%s %s\n", g_failed == before ? "ok  " : "FAIL", t.name);
    }
    std::printf("%d tests, %d checks, %d failed\n", ran, g_checks, g_failed);
    return g_failed ? 1 : 0;
}
