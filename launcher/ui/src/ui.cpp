#include "ttt2ui/ui.h"

#include <algorithm>
#include <functional>
#include <cassert>
#include <cmath>

namespace ttt2::ui {

namespace {
constexpr float kInf = 1e9f;
float approach(float v, float target, float rate, float dt) {
    const float k = 1 - std::exp(-rate * dt);
    return v + (target - v) * k;
}
}  // namespace

const char* event_name(EventKind k) {
    static const char* kNames[] = {"activate",     "refused",      "change",   "back",     "tab-prev",
                                   "tab-next",     "section-prev", "section-next", "context1", "context2",
                                   "menu",         "fullscreen",   "bump",     "click-outside", "focus"};
    return kNames[static_cast<int>(k)];
}

Ui::Ui(TextEngine& text, Icons& icons) : text_(text), icons_(icons) {}

void Ui::begin(FrameInput frame) {
    frame_ = std::move(frame);
    dt_ = last_now_ < 0 ? 0 : static_cast<float>(std::clamp(frame_.now - last_now_, 0.0, 0.25));
    last_now_ = frame_.now;
    ++frame_no_;
    nodes_.clear();
    stack_.clear();
    index_.clear();
    duplicates_ = 0;
    prefix_.clear();
    prefixes_.clear();
    text_.set_scale(frame_.scale);
    text_.begin_frame();
    Box root;
    root.layout = Layout::Stack;
    root.w = Size::fixed(frame_.size.x);
    root.h = Size::fixed(frame_.size.y);
    add("", root);
    stack_.push_back(0);
}

std::string Ui::id_scope() const { return stack_.empty() ? std::string() : nodes_[static_cast<std::size_t>(stack_.back())].id; }

int Ui::add(std::string id, const Box& box) {
    const int parent = stack_.empty() ? -1 : stack_.back();
    if (!id.empty()) id = prefix_ + id;
    if (id.empty() && parent >= 0) {
        // (Anonymous boxes: named by their place under their parent.)
        id = nodes_[static_cast<std::size_t>(parent)].id + "/#" +
             std::to_string(nodes_[static_cast<std::size_t>(parent)].children.size());
    }
    if (index_.count(id)) {
        ++duplicates_;
        assert(!strict_ids_ || !"ttt2::ui: an id was declared twice in one frame");
        id += "~" + std::to_string(duplicates_);
    }
    Node n;
    n.id = id;
    n.box = box;
    n.parent = parent;
    nodes_.push_back(std::move(n));
    const int index = static_cast<int>(nodes_.size()) - 1;
    if (parent >= 0) nodes_[static_cast<std::size_t>(parent)].children.push_back(index);
    index_[nodes_.back().id] = index;
    NodeState& s = states_[nodes_.back().id];
    if (s.last_frame == 0 || s.last_frame + 1 < frame_no_) s.first_seen = frame_.now;
    s.last_frame = frame_no_;
    return index;
}

Ui::Guard Ui::open(std::string id, const Box& box, PaintFn paint, const Focus* focus, PaintFn paint_after) {
    const int n = add(std::move(id), box);
    nodes_[static_cast<std::size_t>(n)].paint = std::move(paint);
    nodes_[static_cast<std::size_t>(n)].paint_after = std::move(paint_after);
    if (focus && focus->on) nodes_[static_cast<std::size_t>(n)].focus = *focus;
    stack_.push_back(n);
    return Guard(this);
}

void Ui::close() {
    if (stack_.size() > 1) stack_.pop_back();
}

void Ui::leaf(std::string id, const Box& box, MeasureFn measure, PaintFn paint, const Focus* focus) {
    const int n = add(std::move(id), box);
    nodes_[static_cast<std::size_t>(n)].measure = std::move(measure);
    nodes_[static_cast<std::size_t>(n)].paint = std::move(paint);
    if (focus && focus->on) nodes_[static_cast<std::size_t>(n)].focus = *focus;
}

Ui::Guard Ui::modal(std::string id, const Box& box, PaintFn paint) {
    const int n = add(std::move(id), box);
    nodes_[static_cast<std::size_t>(n)].paint = std::move(paint);
    nodes_[static_cast<std::size_t>(n)].modal = true;
    stack_.push_back(n);
    return Guard(this);
}

// ---- layout ------------------------------------------------------------------------------------------------------

void Ui::measure_widths() {
    for (int i = static_cast<int>(nodes_.size()) - 1; i >= 0; --i) {
        Node& n = nodes_[static_cast<std::size_t>(i)];
        const Box& b = n.box;
        float w;
        if (b.w.mode == Size::Fixed) {
            w = b.w.value;
        } else if (n.children.empty()) {
            w = (n.measure ? n.measure(kInf).x : 0) + b.pad.horizontal();
        } else {
            float sum = 0, best = 0;
            for (int c : n.children) {
                const Node& k = nodes_[static_cast<std::size_t>(c)];
                const float cw = k.pref_w + k.box.margin.horizontal();
                sum += cw;
                best = std::max(best, cw);
            }
            if (b.layout == Layout::Row) sum += b.gap * static_cast<float>(n.children.size() - 1);
            w = (b.layout == Layout::Row ? sum : best) + b.pad.horizontal();
        }
        n.pref_w = std::clamp(w, b.min_w, b.max_w);
    }
}

void Ui::assign_widths(int index) {
    Node& n = nodes_[static_cast<std::size_t>(index)];
    const Box& b = n.box;
    const float inner = std::max(0.f, n.w - b.pad.horizontal());
    auto base_of = [&](const Node& k) {
        if (k.fit_w >= 0 && (k.box.fit == SeamFit::CrimsonSkewed || k.box.fit == SeamFit::CrimsonRect))
            return std::max(k.box.min_w, k.fit_w);
        if (k.box.w.mode == Size::Fixed) return k.box.w.value;
        return k.pref_w;
    };
    if (b.layout == Layout::Row && !b.wrap) {
        float sum = 0, weights = 0;
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            const bool grows = k.box.w.mode == Size::Grow && k.fit_w < 0;
            k.w = grows ? 0 : base_of(k);
            sum += k.w + k.box.margin.horizontal();
            if (grows) weights += std::max(.0001f, k.box.w.value);
        }
        if (!n.children.empty()) sum += b.gap * static_cast<float>(n.children.size() - 1);
        const float free = inner - sum;
        auto shrinks = [](const Node& k) { return k.box.w.mode == Size::Fit && k.fit_w < 0; };
        if (free < 0) {
            // Too narrow: Fit children give up width toward their minimum, in shrink_order (highest first), each
            // order's children in proportion to what they can give.
            float deficit = -free;
            std::vector<int> orders;
            for (int c : n.children)
                if (shrinks(nodes_[static_cast<std::size_t>(c)])) orders.push_back(nodes_[static_cast<std::size_t>(c)].box.shrink_order);
            std::sort(orders.begin(), orders.end(), std::greater<>());
            orders.erase(std::unique(orders.begin(), orders.end()), orders.end());
            for (int order : orders) {
                if (deficit <= 0) break;
                float room = 0;
                for (int c : n.children) {
                    const Node& k = nodes_[static_cast<std::size_t>(c)];
                    if (shrinks(k) && k.box.shrink_order == order) room += std::max(0.f, k.w - k.box.min_w);
                }
                if (room <= 0) continue;
                const float take = std::min(deficit, room);
                for (int c : n.children) {
                    Node& k = nodes_[static_cast<std::size_t>(c)];
                    if (shrinks(k) && k.box.shrink_order == order) k.w -= take * std::max(0.f, k.w - k.box.min_w) / room;
                }
                deficit -= take;
            }
        }
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            const bool grows = k.box.w.mode == Size::Grow && k.fit_w < 0;
            if (grows && free > 0) k.w = free * std::max(.0001f, k.box.w.value) / weights;
            else if (grows) k.w = 0;
            k.w = std::clamp(k.w, k.box.min_w, k.box.max_w);
        }
    } else if (b.layout == Layout::Row) {
        // Wrapping: each child as wide as it likes (at most the row), then lines as place() makes them; Grow
        // children share their own line's free space.
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            const float room = std::max(0.f, inner - k.box.margin.horizontal());
            float w;
            if (k.box.w.mode == Size::Fixed) w = k.box.w.value;
            else if (k.box.w.mode == Size::Grow) w = 0;
            else w = std::min(k.pref_w, room);
            k.w = std::clamp(w, k.box.min_w, k.box.max_w);
        }
        std::size_t i = 0;
        while (i < n.children.size()) {
            std::size_t j = i;
            float line_w = 0, weights = 0;
            while (j < n.children.size()) {
                const Node& k = nodes_[static_cast<std::size_t>(n.children[j])];
                const float cw = k.w + k.box.margin.horizontal();
                if (j > i && line_w + b.gap + cw > inner + .01f) break;
                line_w += (j > i ? b.gap : 0) + cw;
                if (k.box.w.mode == Size::Grow) weights += std::max(.0001f, k.box.w.value);
                ++j;
            }
            const float free = inner - line_w - .02f;  // (a hair less: the same lines when placed)
            if (weights > 0 && free > 0)
                for (std::size_t q = i; q < j; ++q) {
                    Node& k = nodes_[static_cast<std::size_t>(n.children[q])];
                    if (k.box.w.mode == Size::Grow) k.w = std::min(k.box.max_w, free * std::max(.0001f, k.box.w.value) / weights);
                }
            i = j;
        }
    } else {
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            const float room = std::max(0.f, inner - k.box.margin.horizontal() - k.fit_dx);
            float w;
            if (k.fit_w >= 0 && (k.box.fit == SeamFit::CrimsonSkewed || k.box.fit == SeamFit::CrimsonRect))
                w = k.fit_w;
            else if (k.box.w.mode == Size::Fixed) w = k.box.w.value;
            else if (k.box.w.mode == Size::Grow || (b.align == Align::Stretch && !k.box.hug)) w = room;
            else w = std::min(k.pref_w, room);
            k.w = std::clamp(w, k.box.min_w, k.box.max_w);
        }
    }
    for (int c : n.children) assign_widths(c);
}

float Ui::content_height(int index) {
    Node& n = nodes_[static_cast<std::size_t>(index)];
    const Box& b = n.box;
    for (int c : n.children) nodes_[static_cast<std::size_t>(c)].h = content_height(c);
    float h = 0;
    if (n.children.empty()) {
        h = n.measure ? n.measure(std::max(0.f, n.w - b.pad.horizontal())).y : 0;
    } else if (b.layout == Layout::Column) {
        for (int c : n.children) h += nodes_[static_cast<std::size_t>(c)].h + nodes_[static_cast<std::size_t>(c)].box.margin.vertical();
        h += b.gap * static_cast<float>(n.children.size() - 1);
    } else if (b.layout == Layout::Row && b.wrap) {
        const float inner = std::max(0.f, n.w - b.pad.horizontal());
        float line_w = 0, line_h = 0;
        bool first = true;
        int lines = 0;
        for (int c : n.children) {
            const Node& k = nodes_[static_cast<std::size_t>(c)];
            const float cw = k.w + k.box.margin.horizontal();
            if (!first && line_w + b.gap + cw > inner + .01f) {
                h += line_h;
                ++lines;
                line_w = 0;
                line_h = 0;
                first = true;
            }
            line_w += (first ? 0 : b.gap) + cw;
            line_h = std::max(line_h, k.h + k.box.margin.vertical());
            first = false;
        }
        h += line_h;
        h += b.line_gap * static_cast<float>(lines);
    } else {
        for (int c : n.children)
            h = std::max(h, nodes_[static_cast<std::size_t>(c)].h + nodes_[static_cast<std::size_t>(c)].box.margin.vertical());
    }
    h += b.pad.vertical();
    n.content_h = h;
    if (b.h.mode == Size::Fixed) h = b.h.value;
    return std::clamp(h, b.min_h, b.max_h);
}

void Ui::assign_heights(int index) {
    Node& n = nodes_[static_cast<std::size_t>(index)];
    const Box& b = n.box;
    const float inner = std::max(0.f, n.h - b.pad.vertical());
    if (b.layout == Layout::Column && !b.scroll) {
        float used = 0, weights = 0;
        for (int c : n.children) {
            const Node& k = nodes_[static_cast<std::size_t>(c)];
            used += k.h + k.box.margin.vertical();
            if (k.box.h.mode == Size::Grow) weights += std::max(.0001f, k.box.h.value);
        }
        if (!n.children.empty()) used += b.gap * static_cast<float>(n.children.size() - 1);
        const float extra = inner - used;
        if (extra > 0 && weights > 0)
            for (int c : n.children) {
                Node& k = nodes_[static_cast<std::size_t>(c)];
                if (k.box.h.mode == Size::Grow)
                    k.h = std::min(k.box.max_h, k.h + extra * std::max(.0001f, k.box.h.value) / weights);
            }
    } else if (b.layout != Layout::Column) {
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            if (b.wrap) continue;
            if (k.box.h.mode == Size::Grow || (b.align == Align::Stretch && k.box.h.mode != Size::Fixed))
                k.h = std::clamp(std::max(k.h, inner - k.box.margin.vertical()), k.box.min_h, k.box.max_h);
        }
    }
    for (int c : n.children) assign_heights(c);
}

void Ui::place(int index, float x, float y) {
    Node& n = nodes_[static_cast<std::size_t>(index)];
    n.x = x;
    n.y = y;
    const Box& b = n.box;
    const float ix = x + b.pad.left, iy = y + b.pad.top;
    const float iw = std::max(0.f, n.w - b.pad.horizontal()), ih = std::max(0.f, n.h - b.pad.vertical());
    float scroll = 0;
    if (b.scroll) {
        NodeState& s = states_[n.id];
        s.content_h = n.content_h;
        s.view_h = n.h;
        const float max = std::max(0.f, n.content_h - n.h);
        s.scroll.target = std::clamp(s.scroll.target, 0.f, max);
        s.scroll.value = std::clamp(s.scroll.value, 0.f, max);
        scroll = std::round(s.scroll.value * frame_.scale) / frame_.scale;
        n.scroll_used = scroll;
    }
    auto cross = [&](const Node&, float room, float size, Align a) {
        if (a == Align::Center) return (room - size) / 2;
        if (a == Align::End) return room - size;
        return 0.f;
    };
    if (b.layout == Layout::Column) {
        float used = 0;
        for (int c : n.children) used += nodes_[static_cast<std::size_t>(c)].h + nodes_[static_cast<std::size_t>(c)].box.margin.vertical();
        if (!n.children.empty()) used += b.gap * static_cast<float>(n.children.size() - 1);
        float cy = iy - scroll + (b.scroll ? 0 : std::max(0.f, cross(n, ih, used, b.justify)));
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            const float room = iw - k.box.margin.horizontal() - k.fit_dx;
            const float cx = ix + k.box.margin.left + k.fit_dx + (b.align == Align::Stretch ? 0 : cross(k, room, k.w, b.align));
            place(c, cx, cy + k.box.margin.top);
            cy += k.h + k.box.margin.vertical() + b.gap;
        }
    } else if (b.layout == Layout::Row && !b.wrap) {
        float used = 0;
        for (int c : n.children) used += nodes_[static_cast<std::size_t>(c)].w + nodes_[static_cast<std::size_t>(c)].box.margin.horizontal();
        if (!n.children.empty()) used += b.gap * static_cast<float>(n.children.size() - 1);
        float cx = ix + std::max(0.f, cross(n, iw, used, b.justify));
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            const float room = ih - k.box.margin.vertical();
            const float cy = iy - scroll + k.box.margin.top + (b.align == Align::Stretch ? 0 : cross(k, room, k.h, b.align));
            place(c, cx + k.box.margin.left + k.fit_dx, cy);
            cx += k.w + k.box.margin.horizontal() + k.fit_dx + b.gap;
        }
    } else if (b.layout == Layout::Row) {
        // Wrapping: lines of children, each line as tall as its tallest.
        std::size_t i = 0;
        float cy = iy - scroll;
        while (i < n.children.size()) {
            std::size_t j = i;
            float line_w = 0, line_h = 0;
            while (j < n.children.size()) {
                const Node& k = nodes_[static_cast<std::size_t>(n.children[j])];
                const float cw = k.w + k.box.margin.horizontal();
                if (j > i && line_w + b.gap + cw > iw + .01f) break;
                line_w += (j > i ? b.gap : 0) + cw;
                line_h = std::max(line_h, k.h + k.box.margin.vertical());
                ++j;
            }
            float cx = ix + std::max(0.f, cross(n, iw, line_w, b.justify));
            for (std::size_t q = i; q < j; ++q) {
                Node& k = nodes_[static_cast<std::size_t>(n.children[q])];
                place(n.children[q], cx + k.box.margin.left, cy + k.box.margin.top + cross(k, line_h - k.box.margin.vertical(), k.h, b.align == Align::Stretch ? Align::Start : b.align));
                cx += k.w + k.box.margin.horizontal() + b.gap;
            }
            cy += line_h + b.line_gap;
            i = j;
        }
    } else {
        for (int c : n.children) {
            Node& k = nodes_[static_cast<std::size_t>(c)];
            const Align a = b.align == Align::Stretch ? Align::Start : b.align;
            place(c, ix + k.box.margin.left + k.fit_dx + cross(k, iw - k.box.margin.horizontal() - k.fit_dx, k.w, a),
                  iy - scroll + k.box.margin.top + cross(k, ih - k.box.margin.vertical(), k.h, b.justify == Align::Start ? a : b.justify));
        }
    }
}

const Seam* Ui::seam_of(int n) const {
    for (int i = n; i >= 0; i = nodes_[static_cast<std::size_t>(i)].parent)
        if (nodes_[static_cast<std::size_t>(i)].box.seam) return &*nodes_[static_cast<std::size_t>(i)].box.seam;
    return nullptr;
}

bool Ui::fit_pass() {
    bool changed = false;
    for (int i = 0; i < static_cast<int>(nodes_.size()); ++i) {
        Node& n = nodes_[static_cast<std::size_t>(i)];
        if (n.box.fit == SeamFit::None) continue;
        const Seam* seam = seam_of(i);
        if (!seam) continue;
        const float g = n.box.fit_gap;
        switch (n.box.fit) {
        case SeamFit::CrimsonSkewed:
        case SeamFit::CrimsonRect: {
            const float y = n.box.fit == SeamFit::CrimsonSkewed ? n.y + n.h / 2 : n.y + n.h;
            const float w = std::max(0.f, std::round(seam->x_at(y) - g - n.x));
            if (std::fabs(w - n.fit_w) > .5f) {
                n.fit_w = w;
                changed = true;
            }
            break;
        }
        case SeamFit::BlueSkewed:
        case SeamFit::BlueRect: {
            const float y = n.box.fit == SeamFit::BlueSkewed ? n.y + n.h / 2 : n.y;
            const float x0 = n.x - n.fit_dx;
            const float dx = std::max(0.f, std::round(seam->x_at(y) + g - x0));
            if (std::fabs(dx - n.fit_dx) > .5f) {
                n.fit_dx = dx;
                changed = true;
            }
            break;
        }
        default:
            break;
        }
    }
    return changed;
}

void Ui::compute_clips(int index, Rect clip, int scroller) {
    Node& n = nodes_[static_cast<std::size_t>(index)];
    n.clip = clip;
    n.scroller = scroller;
    Rect inner = clip;
    int s = scroller;
    if (n.box.scroll || n.box.clip) inner = clip.intersect({n.x, n.y, n.w, n.h});
    if (n.box.scroll) s = index;
    for (int c : n.children) compute_clips(c, inner, s);
}

void Ui::layout() {
    measure_widths();
    Node& root = nodes_[0];
    root.w = frame_.size.x;
    for (int pass = 0; pass < 4; ++pass) {
        assign_widths(0);
        content_height(0);
        root.h = frame_.size.y;
        assign_heights(0);
        place(0, 0, 0);
        if (pass == 3 || !fit_pass()) break;
    }
    compute_clips(0, {0, 0, frame_.size.x, frame_.size.y}, -1);
}

// ---- focus -------------------------------------------------------------------------------------------------------

int Ui::node_index(const std::string& id) const {
    auto it = index_.find(id);
    return it == index_.end() ? -1 : it->second;
}

bool Ui::has(const std::string& id) const { return node_index(id) >= 0; }

Rect Ui::rect(const std::string& id) const {
    const int i = node_index(id);
    if (i < 0) return {};
    const Node& n = nodes_[static_cast<std::size_t>(i)];
    return {n.x, n.y, n.w, n.h};
}

NodeState* Ui::state(const std::string& id) {
    auto it = states_.find(id);
    return it == states_.end() ? nullptr : &it->second;
}

int Ui::scroll_container_of(int n) const { return n >= 0 ? nodes_[static_cast<std::size_t>(n)].scroller : -1; }

float Ui::scroll_max(int n) const {
    const Node& s = nodes_[static_cast<std::size_t>(n)];
    return std::max(0.f, s.content_h - s.h);
}

std::vector<std::string> Ui::focusable_ids() const {
    std::vector<std::string> out;
    for (const Item& i : items_) out.push_back(nodes_[static_cast<std::size_t>(i.node)].id);
    return out;
}

void Ui::collect_focus() {
    // The newest modal is the scope; everything outside it is out of reach.
    modal_ = -1;
    for (int i = 0; i < static_cast<int>(nodes_.size()); ++i)
        if (nodes_[static_cast<std::size_t>(i)].modal) modal_ = i;
    auto inside = [&](int i) {
        if (modal_ < 0) return true;
        for (int p = i; p >= 0; p = nodes_[static_cast<std::size_t>(p)].parent)
            if (p == modal_) return true;
        return false;
    };
    auto inert = [&](int i) {
        for (int p = i; p >= 0; p = nodes_[static_cast<std::size_t>(p)].parent)
            if (nodes_[static_cast<std::size_t>(p)].box.inert) return true;
        return false;
    };
    items_.clear();
    clickables_.clear();
    for (int i = 0; i < static_cast<int>(nodes_.size()); ++i) {
        const Node& n = nodes_[static_cast<std::size_t>(i)];
        if (!n.focus || !inside(i) || inert(i)) continue;
        const Rect r{n.x, n.y, n.w, n.h};
        // Items scrolled out of their viewport still count (navigation scrolls to them); items clipped away by a
        // plain clip do not.
        if (n.scroller < 0 && r.intersect(n.clip).empty()) continue;
        clickables_.push_back(i);
        if (n.focus->nav) items_.push_back({i, {r, n.focus->group}});
    }
    const std::string modal_id = modal_ >= 0 ? nodes_[static_cast<std::size_t>(modal_)].id : std::string();
    if (modal_id != modal_id_) {
        if (!modal_id.empty() && modal_id_.empty()) {
            focus_before_modal_ = focused_;
            focused_.clear();
        } else if (modal_id.empty()) {
            focused_ = focus_before_modal_;
            snap_next_ = true;
        }
        modal_id_ = modal_id;
    }
    modal_opened_ = modal_ >= 0 ? states_[modal_id].first_seen : -1;
}

int Ui::item_of_node(int node) const {
    for (int i = 0; i < static_cast<int>(items_.size()); ++i)
        if (items_[static_cast<std::size_t>(i)].node == node) return i;
    return -1;
}

void Ui::set_focus(int item, Device device, bool by_mouse) {
    if (item < 0 || item >= static_cast<int>(items_.size())) return;
    const std::string& id = nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(item)].node)].id;
    if (id == focused_) return;
    focused_ = id;
    focus_by_mouse_ = by_mouse;
    events_.push_back({EventKind::FocusMoved, id, 0, device});
}

void Ui::focus(const std::string& id, bool snap) {
    focused_ = id;
    focus_by_mouse_ = false;
    if (snap) snap_next_ = true;
}

void Ui::resolve_focus() {
    int current = -1;
    for (int i = 0; i < static_cast<int>(items_.size()); ++i)
        if (nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(i)].node)].id == focused_) current = i;
    if (current >= 0 || items_.empty()) {
        if (current >= 0) last_focus_rect_ = items_[static_cast<std::size_t>(current)].f.rect;
        if (items_.empty() && !focused_.empty() && modal_ < 0) {
            // (Nothing focusable now: keep the id; it may come back.)
        }
        return;
    }
    // Lost (or none yet): the app's choice, then the nearest item to where it was, then the default, then the first.
    int pick = -1;
    if (!focused_.empty() && fallback_) {
        const std::string alt = fallback_(focused_);
        for (int i = 0; i < static_cast<int>(items_.size()) && !alt.empty(); ++i)
            if (nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(i)].node)].id == alt) pick = i;
    }
    if (pick < 0 && !focused_.empty() && !last_focus_rect_.empty()) {
        std::vector<FocusItem> f;
        for (const Item& it : items_) f.push_back(it.f);
        pick = nearest(f, last_focus_rect_);
    }
    if (pick < 0)
        for (int i = 0; i < static_cast<int>(items_.size()); ++i)
            if (nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(i)].node)].focus->is_default) {
                pick = i;
                break;
            }
    if (pick < 0) pick = 0;
    const bool first = focused_.empty();
    focused_ = nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(pick)].node)].id;
    last_focus_rect_ = items_[static_cast<std::size_t>(pick)].f.rect;
    if (first) snap_next_ = true;
}

// ---- input -------------------------------------------------------------------------------------------------------

Rect Ui::bar_rect(int n, float& thumb_y, float& thumb_h) const {
    const Node& s = nodes_[static_cast<std::size_t>(n)];
    const float max = scroll_max(n);
    const Rect track{s.x + s.w - theme::metric::kScrollBarGrab, s.y, theme::metric::kScrollBarGrab, s.h};
    thumb_h = std::max(24.f, s.h * s.h / std::max(s.h, s.content_h));
    auto it = states_.find(s.id);
    const float v = it == states_.end() ? 0 : it->second.scroll.value;
    thumb_y = s.y + (max > 0 ? (s.h - thumb_h) * v / max : 0);
    return track;
}

void Ui::handle_mouse() {
    const MouseState& m = frame_.mouse;
    // Scroll bar drags first.
    if (drag_scroller_ >= 0) {
        if (!m.down || drag_scroller_ >= static_cast<int>(nodes_.size())) {
            drag_scroller_ = -1;
        } else {
            Node& s = nodes_[static_cast<std::size_t>(drag_scroller_)];
            NodeState& st = states_[s.id];
            float ty, th;
            bar_rect(drag_scroller_, ty, th);
            const float max = scroll_max(drag_scroller_);
            const float travel = std::max(1.f, s.h - th);
            st.scroll.target = std::clamp((m.pos.y - st.drag_grab - s.y) / travel * max, 0.f, max);
            st.scroll.snap();
            user_scrolled_ = true;
            return;
        }
    }
    // What is under the pointer: the topmost clickable (last declared) in reach, and the innermost scroller.
    int hover = -1, scroller = -1;
    if (m.inside) {
        for (int i = static_cast<int>(clickables_.size()) - 1; i >= 0 && hover < 0; --i) {
            const Node& n = nodes_[static_cast<std::size_t>(clickables_[static_cast<std::size_t>(i)])];
            if (Rect{n.x, n.y, n.w, n.h}.intersect(n.clip).contains(m.pos)) hover = clickables_[static_cast<std::size_t>(i)];
        }
        for (int i = static_cast<int>(nodes_.size()) - 1; i >= 0; --i) {
            const Node& n = nodes_[static_cast<std::size_t>(i)];
            if (n.box.scroll && Rect{n.x, n.y, n.w, n.h}.intersect(n.clip).contains(m.pos) && scroll_max(i) > 0) {
                scroller = i;
                break;
            }
        }
    }
    for (auto& [id, s] : states_) s.pressed = false;
    hovered_ = hover >= 0 ? nodes_[static_cast<std::size_t>(hover)].id : std::string();
    if (hover >= 0 && m.moved) set_focus(item_of_node(hover), Device::Mouse, true);
    // The wheel scrolls the page under the pointer - never a selector's value.
    if (m.wheel != 0 && scroller >= 0) {
        NodeState& st = states_[nodes_[static_cast<std::size_t>(scroller)].id];
        st.scroll.target = std::clamp(st.scroll.target - m.wheel * theme::input::kWheelStep, 0.f, scroll_max(scroller));
        if (frame_.reduced_motion) st.scroll.snap();
        user_scrolled_ = true;
    }
    if (m.pressed) {
        press_node_ = -1;
        if (scroller >= 0) {
            float ty, th;
            const Rect track = bar_rect(scroller, ty, th);
            if (track.contains(m.pos)) {
                drag_scroller_ = scroller;
                NodeState& st = states_[nodes_[static_cast<std::size_t>(scroller)].id];
                st.drag_grab = (m.pos.y >= ty && m.pos.y < ty + th) ? m.pos.y - ty : th / 2;
                st.dragging_bar = true;
                return;
            }
        }
        if (modal_ >= 0) {
            const Node& md = nodes_[static_cast<std::size_t>(modal_)];
            if (!Rect{md.x, md.y, md.w, md.h}.contains(m.pos)) {
                events_.push_back({EventKind::ClickOutside, md.id, 0, Device::Mouse});
                return;
            }
        }
        if (hover >= 0) press_node_ = hover;
    }
    if (press_node_ >= 0 && m.down) states_[nodes_[static_cast<std::size_t>(press_node_)].id].pressed = hover == press_node_;
    if (m.released) {
        for (auto& [id, s] : states_) s.dragging_bar = false;
        if (press_node_ >= 0 && hover == press_node_) {
            const Node& n = nodes_[static_cast<std::size_t>(press_node_)];
            set_focus(item_of_node(hover), Device::Mouse, true);
            const Focus& f = *n.focus;
            int delta = 0;
            for (int z = 0; z < f.zone_count; ++z) {
                const float d = n.x + n.w - m.pos.x;
                if (d >= f.zones[z].from_right0 && d < f.zones[z].from_right1) delta = f.zones[z].delta;
            }
            if (f.disabled) events_.push_back({EventKind::Refused, n.id, 0, Device::Mouse});
            else if (delta) events_.push_back({EventKind::Change, n.id, delta, Device::Mouse});
            else events_.push_back({EventKind::Activate, n.id, 0, Device::Mouse});
        }
        press_node_ = -1;
    }
}

void Ui::handle_actions() {
    for (const ActionEvent& a : frame_.actions) {
        // A modal ignores a press that began before it opened (the Accept that opened it, held).
        if (modal_ >= 0 && a.press_time < modal_opened_) continue;
        int current = -1;
        for (int i = 0; i < static_cast<int>(items_.size()); ++i)
            if (nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(i)].node)].id == focused_) current = i;
        const Node* fn = current >= 0 ? &nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(current)].node)] : nullptr;
        auto emit = [&](EventKind k, int delta = 0) { events_.push_back({k, focused_, delta, a.device}); };
        auto bump = [&]() {
            if (!frame_.reduced_motion) highlight_.kick((frame_.now * 1000 - std::floor(frame_.now * 1000)) < .5 ? -theme::motion::kBump : theme::motion::kBump);
            emit(EventKind::Bump);
        };
        switch (a.action) {
        case Action::Up:
        case Action::Down:
        case Action::Left:
        case Action::Right: {
            if (current < 0) {
                if (!items_.empty()) set_focus(0, a.device, false);
                break;
            }
            const Dir d = a.action == Action::Up ? Dir::Up : a.action == Action::Down ? Dir::Down
                          : a.action == Action::Left ? Dir::Left : Dir::Right;
            if (fn->focus->adjust && (d == Dir::Left || d == Dir::Right)) {
                emit(EventKind::Change, d == Dir::Left ? -1 : 1);
                break;
            }
            const std::string& over = d == Dir::Up ? fn->focus->up : d == Dir::Down ? fn->focus->down
                                      : d == Dir::Left ? fn->focus->left : fn->focus->right;
            if (!over.empty()) {
                int target = -1;
                for (int i = 0; i < static_cast<int>(items_.size()); ++i)
                    if (nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(i)].node)].id == over) target = i;
                if (target >= 0) {
                    set_focus(target, a.device, false);
                    break;
                }
                if (over == "-") {
                    bump();
                    break;
                }
            }
            std::vector<FocusItem> f;
            f.reserve(items_.size());
            for (const Item& it : items_) f.push_back(it.f);
            const int next = navigate(f, current, d, wrap_);
            if (next >= 0) set_focus(next, a.device, false);
            else bump();
            break;
        }
        case Action::FocusNext:
        case Action::FocusPrev:
            if (!items_.empty()) {
                const int n = static_cast<int>(items_.size());
                set_focus(current < 0 ? 0 : (current + (a.action == Action::FocusNext ? 1 : n - 1)) % n, a.device, false);
            }
            break;
        case Action::Accept:
            if (!fn) break;
            emit(fn->focus->disabled ? EventKind::Refused : EventKind::Activate);
            if (fn->focus->disabled) bump();
            break;
        case Action::Back: emit(EventKind::Back); break;
        case Action::TabPrev: emit(EventKind::TabPrev); break;
        case Action::TabNext: emit(EventKind::TabNext); break;
        case Action::SectionPrev: emit(EventKind::SectionPrev); break;
        case Action::SectionNext: emit(EventKind::SectionNext); break;
        case Action::Context1: emit(EventKind::Context1); break;
        case Action::Context2: emit(EventKind::Context2); break;
        case Action::Menu: emit(EventKind::Menu); break;
        case Action::Fullscreen: emit(EventKind::Fullscreen); break;
        case Action::PageUp:
        case Action::PageDown:
        case Action::Home:
        case Action::End: {
            // Page the focused item's scroll container (or the first one in reach); the focus follows to the first
            // item in view.
            int s = fn ? fn->scroller : -1;
            if (s < 0)
                for (const Item& it : items_)
                    if (nodes_[static_cast<std::size_t>(it.node)].scroller >= 0) {
                        s = nodes_[static_cast<std::size_t>(it.node)].scroller;
                        break;
                    }
            if (s < 0) break;
            const Node& sc = nodes_[static_cast<std::size_t>(s)];
            NodeState& st = states_[sc.id];
            const float max = scroll_max(s), page = std::max(40.f, sc.h * .9f);
            float target = st.scroll.target;
            if (a.action == Action::PageUp) target -= page;
            else if (a.action == Action::PageDown) target += page;
            else if (a.action == Action::Home) target = 0;
            else target = max;
            target = std::clamp(target, 0.f, max);
            const float shift = target - st.scroll.value;
            st.scroll.target = target;
            if (frame_.reduced_motion) st.scroll.snap();
            user_scrolled_ = true;
            int pick = -1;
            for (int i = 0; i < static_cast<int>(items_.size()); ++i) {
                const Node& n = nodes_[static_cast<std::size_t>(items_[static_cast<std::size_t>(i)].node)];
                if (n.scroller != s) continue;
                const float y = n.y - shift;
                const bool in_view = y >= sc.y - .5f && y + n.h <= sc.y + sc.h + .5f;
                if (a.action == Action::End) {
                    pick = i;
                } else if (in_view || a.action == Action::Home) {
                    pick = i;
                    break;
                }
            }
            if (pick >= 0) set_focus(pick, a.device, false);
            break;
        }
        default:
            break;
        }
    }
}

void Ui::keep_in_view(bool snap) {
    const int fi = node_index(focused_);
    if (fi < 0) return;
    const Node& n = nodes_[static_cast<std::size_t>(fi)];
    // Scroll anchoring: content above the focus changed height (a refresh inserted a line): the scroll offset moves
    // by the same amount in the same frame, so the focused row stays where it was.
    if (n.scroller >= 0) {
        const Node& s = nodes_[static_cast<std::size_t>(n.scroller)];
        NodeState& st = states_[s.id];
        // (Its place in the content: as laid out, with the offset it was laid out with, not the moving value: the
        // pixel rounding would read as content moving.)
        const float content_y = n.y - s.y + s.scroll_used;
        if (anchor_id_ == focused_ && !user_scrolled_ && std::fabs(content_y - anchor_y_) > .5f) {
            const float delta = content_y - anchor_y_;
            st.scroll.value = std::clamp(st.scroll.value + delta, 0.f, scroll_max(n.scroller));
            st.scroll.target = std::clamp(st.scroll.target + delta, 0.f, scroll_max(n.scroller));
            place(0, 0, 0);
            compute_clips(0, {0, 0, frame_.size.x, frame_.size.y}, -1);
            for (Item& it : items_) {
                const Node& k = nodes_[static_cast<std::size_t>(it.node)];
                it.f.rect = {k.x, k.y, k.w, k.h};
            }
        }
        anchor_id_ = focused_;
        anchor_y_ = nodes_[static_cast<std::size_t>(fi)].y - s.y + s.scroll_used;
    } else {
        anchor_id_.clear();
    }
    if (focus_by_mouse_) return;  // (never move the page under a resting pointer)
    // Keep the focused item (and its highlight) inside every scroll container above it, out of the insets.
    for (int s = n.scroller; s >= 0; s = nodes_[static_cast<std::size_t>(s)].scroller) {
        const Node& sc = nodes_[static_cast<std::size_t>(s)];
        NodeState& st = states_[sc.id];
        const float margin = n.focus ? n.focus->pad + 4 : 4;
        const float top = sc.y + sc.box.scroll_insets.top, bottom = sc.y + sc.h - sc.box.scroll_insets.bottom;
        // (Positions of the item as laid out with the current value; where it would be at the target.)
        const float y = n.y + (st.scroll.value - st.scroll.target);
        float target = st.scroll.target;
        if (y - margin < top) target -= top - (y - margin);
        else if (y + n.h + margin > bottom) target += (y + n.h + margin) - bottom;
        target = std::clamp(target, 0.f, scroll_max(s));
        if (target != st.scroll.target && !user_scrolled_) {
            st.scroll.target = target;
            if (snap || frame_.reduced_motion) st.scroll.snap();
        }
    }
}

void Ui::step_animations() {
    animating_ = false;
    const float dt = dt_;
    for (auto& [id, s] : states_) {
        if (s.last_frame != frame_no_) continue;
        if (frame_.reduced_motion) s.scroll.snap();
        else s.scroll.step(dt);
        if (!s.scroll.settled(.2f)) animating_ = true;
        const float hv = id == hovered_ ? 1.f : 0.f;
        s.hover = frame_.reduced_motion ? hv : approach(s.hover, hv, 22, dt);
        if (std::fabs(s.hover - hv) > .01f) animating_ = true;
        else s.hover = hv;
        const bool f = id == focused_;
        const float fh = f ? 1.f : 0.f;
        s.focus = frame_.reduced_motion ? fh : approach(s.focus, fh, 18, dt);
        if (std::fabs(s.focus - fh) > .01f) animating_ = true;
        else s.focus = fh;
    }
    // The highlight: a spring in the focused item's scroll content space (it rides along with scrolling).
    const int fi = node_index(focused_);
    if (fi < 0 || !nodes_[static_cast<std::size_t>(fi)].focus) {
        highlight_alpha_ = 0;
        return;
    }
    const Node& n = nodes_[static_cast<std::size_t>(fi)];
    const float pad = n.focus->pad;
    const Rect target{n.x - pad, n.y - pad, n.w + 2 * pad, n.h + 2 * pad};
    auto origin_of = [&](int s) {
        if (s < 0) return Vec2{0, 0};
        const Node& sc = nodes_[static_cast<std::size_t>(s)];
        return Vec2{sc.x, sc.y - states_[sc.id].scroll.value};
    };
    const std::string container = n.scroller >= 0 ? nodes_[static_cast<std::size_t>(n.scroller)].id : std::string();
    const Vec2 o = origin_of(n.scroller);
    if (container != highlight_container_) {
        // Into another container: the highlight's screen place is kept, in the new content space.
        const Rect screen = highlight_.value();
        Vec2 old{0, 0};
        if (highlight_container_ != "\x01" && !highlight_container_.empty()) {
            const int oi = node_index(highlight_container_);
            if (oi >= 0) old = origin_of(oi);
        }
        const Rect moved = screen.translated(old - o);
        highlight_.x.value = moved.x;
        highlight_.y.value = moved.y;
        highlight_container_ = container;
    }
    highlight_.set_target(target.translated(Vec2{0, 0} - o));
    if (snap_next_ || frame_.reduced_motion) {
        highlight_.snap_to(target.translated(Vec2{0, 0} - o));
        snap_next_ = false;
    }
    highlight_.set_spec(frame_.reduced_motion ? theme::motion::kReduced : theme::motion::kFocus);
    highlight_.step(dt);
    if (!highlight_.settled(.1f)) animating_ = true;
    highlight_screen_ = highlight_.value().translated(o);
    highlight_skewed_ = n.focus->skewed;
    highlight_alpha_ = 1;
}

void Ui::end() {
    layout();
    collect_focus();
    resolve_focus();
    user_scrolled_ = false;
    handle_mouse();
    handle_actions();
    // (Focus moved by input this frame: its item may need scrolling.)
    keep_in_view(snap_next_);
    step_animations();
    // Forget ids not declared this frame (their animations start over when they come back).
    for (auto it = states_.begin(); it != states_.end();)
        it = it->second.last_frame != frame_no_ ? states_.erase(it) : std::next(it);
    for (Node& n : nodes_) {
        auto it = states_.find(n.id);
        if (it != states_.end()) it->second.rect = {n.x, n.y, n.w, n.h};
    }
}

void Ui::scroll_by(const std::string& container, float dy) {
    const int i = node_index(container);
    if (i < 0) return;
    NodeState& st = states_[container];
    st.scroll.target = std::clamp(st.scroll.target + dy, 0.f, scroll_max(i));
}

// ---- painting ----------------------------------------------------------------------------------------------------

void Ui::paint_node(Canvas& canvas, int index) {
    Node& n = nodes_[static_cast<std::size_t>(index)];
    const Rect r{n.x, n.y, n.w, n.h};
    if (index > 0 && r.intersect(n.clip).empty() && n.children.empty()) return;
    if (n.box.opacity <= .002f) return;
    const bool layer = n.box.opacity < 1 || n.box.shift.x != 0 || n.box.shift.y != 0;
    if (layer) canvas.push_layer(n.box.shift, n.box.opacity);
    NodeState& s = states_[n.id];
    PaintContext ctx{canvas,
                     text_,
                     icons_,
                     s,
                     r,
                     frame_.now,
                     dt_,
                     n.id == focused_,
                     s.focus,
                     s.hover,
                     static_cast<float>(frame_.now - s.first_seen),
                     n.focus && n.focus->disabled,
                     frame_.reduced_motion,
                     frame_.glyphs,
                     &paint_animating_};
    if (n.paint) n.paint(ctx);
    const bool clips = n.box.scroll || n.box.clip;
    if (clips) canvas.push_clip(r);
    for (int c : n.children) paint_node(canvas, c);
    if (clips) canvas.pop_clip();
    if (n.paint_after) n.paint_after(ctx);
    if (n.box.scroll && scroll_max(index) > 0) {
        // A thin scroll bar (wider while dragged).
        float ty, th;
        bar_rect(index, ty, th);
        const float w = s.dragging_bar ? theme::metric::kScrollBarWidth + 2 : theme::metric::kScrollBarWidth;
        canvas.fill_rect({n.x + n.w - w - 2, ty, w, th},
                         s.dragging_bar ? theme::color::kScrollBarActive : theme::color::kScrollBar);
    }
    if (layer) canvas.pop_layer();
}

void Ui::paint(Canvas& canvas) {
    paint_animating_ = false;
    if (nodes_.empty()) return;
    paint_node(canvas, 0);
    const int fi = node_index(focused_);
    if (highlight_paint_ && highlight_alpha_ > 0 && fi >= 0) {
        const Node& n = nodes_[static_cast<std::size_t>(fi)];
        canvas.push_clip(n.clip.outset(n.focus ? n.focus->pad + 12 : 12));
        highlight_paint_(canvas, highlight_screen_, highlight_skewed_, highlight_alpha_, frame_.now);
        canvas.pop_clip();
    }
    canvas.flush();
}

}  // namespace ttt2::ui
