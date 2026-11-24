#include "ttt2ui/focus.h"

#include <cmath>
#include <limits>

namespace ttt2::ui {

int navigate(const std::vector<FocusItem>& items, int current, Dir dir, WrapRule wrap) {
    if (current < 0 || current >= static_cast<int>(items.size())) return items.empty() ? -1 : 0;
    const Rect a = items[static_cast<std::size_t>(current)].rect;
    const float acx = a.x + a.w / 2, acy = a.y + a.h / 2;
    const bool horizontal = dir == Dir::Left || dir == Dir::Right;
    int best = -1;
    float best_score = std::numeric_limits<float>::max();
    for (int i = 0; i < static_cast<int>(items.size()); ++i) {
        if (i == current) continue;
        const Rect b = items[static_cast<std::size_t>(i)].rect;
        const float bcx = b.x + b.w / 2, bcy = b.y + b.h / 2;
        float along, edge, overlap, off;
        if (horizontal) {
            along = dir == Dir::Right ? bcx - acx : acx - bcx;
            if (along <= 6) continue;
            edge = dir == Dir::Right ? b.x - a.right() : a.x - b.right();
            overlap = std::min(a.bottom(), b.bottom()) - std::max(a.y, b.y);
            off = std::fabs(bcy - acy);
            if (overlap <= 0 && edge < -8) continue;  // a staircased list: the row above is not "to the right"
        } else {
            along = dir == Dir::Down ? bcy - acy : acy - bcy;
            if (along <= 6) continue;
            edge = dir == Dir::Down ? b.y - a.bottom() : a.y - b.bottom();
            overlap = std::min(a.right(), b.right()) - std::max(a.x, b.x);
            off = std::fabs(bcx - acx);
        }
        float score = std::max(0.f, edge) + along * .25f + (overlap > 0 ? off * .6f : 1000 - overlap * 2.4f + off * .4f);
        if (!horizontal && items[static_cast<std::size_t>(i)].group != items[static_cast<std::size_t>(current)].group)
            score += 3000;
        if (score < best_score) {
            best_score = score;
            best = i;
        }
    }
    if (best >= 0) return best;
    const bool wraps = horizontal ? wrap.horizontal : wrap.vertical;
    if (!wraps) return -1;
    // Wrap: the farthest item on the other side among those in the same row (horizontal) / column (vertical).
    float far = -std::numeric_limits<float>::max();
    for (int i = 0; i < static_cast<int>(items.size()); ++i) {
        if (i == current) continue;
        const Rect b = items[static_cast<std::size_t>(i)].rect;
        const float overlap = horizontal ? std::min(a.bottom(), b.bottom()) - std::max(a.y, b.y)
                                         : std::min(a.right(), b.right()) - std::max(a.x, b.x);
        if (overlap <= 0) continue;
        const float d = horizontal ? (dir == Dir::Right ? acx - (b.x + b.w / 2) : (b.x + b.w / 2) - acx)
                                   : (dir == Dir::Down ? acy - (b.y + b.h / 2) : (b.y + b.h / 2) - acy);
        if (d > far) {
            far = d;
            best = i;
        }
    }
    return best;
}

int nearest(const std::vector<FocusItem>& items, const Rect& rect) {
    int best = -1;
    float best_d = std::numeric_limits<float>::max();
    const Vec2 c = rect.center();
    for (int i = 0; i < static_cast<int>(items.size()); ++i) {
        const Rect& r = items[static_cast<std::size_t>(i)].rect;
        const Vec2 d = r.center() - c;
        float dist = std::sqrt(d.x * d.x + d.y * d.y);
        if (r.overlaps(rect)) dist *= .25f;
        if (dist < best_d) {
            best_d = dist;
            best = i;
        }
    }
    return best;
}

}  // namespace ttt2::ui
