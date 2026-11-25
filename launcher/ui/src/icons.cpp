#include "ttt2ui/icons.h"

#include <nanosvg.h>
#include <nanosvgrast.h>

#include <algorithm>
#include <cmath>
#include <vector>

#include "ttt2_launcher_icons.h"

namespace ttt2::ui {

namespace {
// Line icons drawn for the Tag Split look (24 x 24, strokes only): "stroke:<name>" or "stroke:<name>:<width>".
struct StrokeIcon {
    const char* name;
    const char* svg;
};
constexpr StrokeIcon kStrokeIcons[] = {
    {"update", R"(<path d="M12 15V4M7 9l5-5 5 5M5 20h14"/>)"},
    {"play", R"(<path d="M8 5.5v13l10.5-6.5z"/>)"},
    {"gear",
     R"(<circle cx="12" cy="12" r="3.2"/><path d="M12 3v2.6M12 18.4V21M3 12h2.6M18.4 12H21M5.6 5.6l1.9 1.9M16.5 16.5l1.9 1.9M5.6 18.4l1.9-1.9M16.5 7.5l1.9-1.9"/><circle cx="12" cy="12" r="6.4"/>)"},
    {"folder", R"(<path d="M3 6.5h6l2 2.2h10V19H3z"/>)"},
    {"trash", R"(<path d="M4.5 7h15M9.5 7V4h5v3M6.5 7l1 13h9l1-13"/>)"},
    {"check", R"(<path d="M5 12.5l4.2 4.2L19 7"/>)"},
    {"cross", R"(<path d="M6 6l12 12M18 6L6 18"/>)"},
    {"plus", R"(<path d="M12 5v14M5 12h14"/>)"},
    {"up", R"(<path d="M12 19V6M6 11l6-6 6 6"/>)"},
    {"ban", R"(<circle cx="12" cy="12" r="8"/><path d="M6.5 17.5l11-11"/>)"},
    {"diamond", R"(<path d="M12 4l7 8-7 8-7-8z"/>)"},
    {"dots", R"(<circle cx="6" cy="12" r=".9"/><circle cx="12" cy="12" r=".9"/><circle cx="18" cy="12" r=".9"/>)"},  // (circles: a zero-length path draws nothing)
    {"warn", R"(<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>)"},
    {"info", R"(<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8h.01"/>)"},
    {"users",
     R"(<circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19c.6-3.4 2.8-5.2 5.5-5.2s4.9 1.8 5.5 5.2"/><circle cx="16.5" cy="9.5" r="2.6"/><path d="M15.5 14c2.6-.2 4.4 1.3 5 4.6"/>)"},
    {"file", R"(<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>)"},
    {"disc", R"(<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="2.4"/>)"},
    {"home", R"(<path d="M4 11l8-7 8 7M6 9.5V20h12V9.5"/>)"},
    {"down", R"(<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>)"},
    {"drive", R"(<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 12h.01M11 12h6"/>)"},
    {"open", R"(<path d="M3 7h6l2 2h10v10H3z"/><path d="M3 11h18"/>)"},
    {"sound-on", R"(<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 9c1.4 1.6 1.4 4.4 0 6M19 6.5c2.8 3 2.8 8 0 11"/>)"},
    {"sound-off", R"(<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9.5l5 5M22 9.5l-5 5"/>)"},
    {"power", R"(<path d="M12 3v8"/><path d="M6.6 6.6a8 8 0 1 0 10.8 0"/>)"},
    {"minimise", R"(<path d="M6 17h12"/>)"},
    {"fullscreen", R"(<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>)"},
    {"windowed", R"(<path d="M9 4v5H4M20 9h-5V4M15 20v-5h5M4 15h5v5"/>)"},
    {"close", R"(<path d="M6 6l12 12M18 6L6 18"/>)"},
    {"copy", R"(<rect x="8" y="8" width="12" height="12"/><path d="M16 8V4H4v12h4"/>)"},
};

// The SVG text of an icon: an embedded file, or a line icon.
bool icon_svg(const std::string& path, std::string& out) {
    if (path.rfind("stroke:", 0) == 0) {
        std::string name = path.substr(7), width = "2";
        if (const auto c = name.find(':'); c != std::string::npos) {
            width = name.substr(c + 1);
            name.resize(c);
        }
        for (const StrokeIcon& i : kStrokeIcons)
            if (name == i.name) {
                out = std::string(
                          R"(<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">)") +
                      R"(<g fill="none" stroke="#ffffff" stroke-width=")" + width +
                      R"(" stroke-linecap="round" stroke-linejoin="round">)" + i.svg + "</g></svg>";
                return true;
            }
        return false;
    }
    const ttt2_icons::File* file = ttt2_icons::find(path);
    if (!file) return false;
    out.assign(reinterpret_cast<const char*>(file->data), file->size);
    return true;
}
}  // namespace

std::vector<std::uint8_t> rasterise_icon(const std::string& path, int pixels) {
    std::vector<std::uint8_t> rgba;
    std::string text;
    if (pixels <= 0 || !icon_svg(path, text)) return rgba;
    if (NSVGimage* image = nsvgParse(text.data(), "px", 96)) {  // (nsvgParse writes into the text)
        if (image->width > 0 && image->height > 0) {
            rgba.assign(static_cast<std::size_t>(pixels) * pixels * 4, 0);
            const float s = static_cast<float>(pixels) / std::max(image->width, image->height);
            const float tx = (static_cast<float>(pixels) - image->width * s) / 2,
                        ty = (static_cast<float>(pixels) - image->height * s) / 2;
            NSVGrasterizer* r = nsvgCreateRasterizer();
            nsvgRasterize(r, image, tx, ty, s, rgba.data(), pixels, pixels, pixels * 4);
            nsvgDeleteRasterizer(r);
        }
        nsvgDelete(image);
    }
    return rgba;
}

Icons::~Icons() {
    for (auto& [key, id] : cache_) textures_.destroy(id);
}

bool Icons::exists(const std::string& path) const {
    std::string text;
    return icon_svg(path, text);
}

TextureId Icons::texture(const std::string& path, int pixels, IconMode mode) {
    const std::string key = path + "@" + std::to_string(pixels) + (mode == IconMode::Mask ? "m" : "c");
    if (auto it = cache_.find(key); it != cache_.end()) return it->second;
    TextureId id = 0;
    if (std::vector<std::uint8_t> rgba = rasterise_icon(path, pixels); !rgba.empty()) {
        if (mode == IconMode::Mask)
            for (std::size_t i = 0; i < rgba.size(); i += 4) rgba[i] = rgba[i + 1] = rgba[i + 2] = 255;
        id = textures_.create(pixels, pixels, std::move(rgba));
    }
    cache_[key] = id;
    return id;
}

bool Icons::draw(Canvas& canvas, const std::string& path, const Rect& box, Color tint, IconMode mode) {
    const float side = std::min(box.w, box.h);
    const int pixels = std::max(4, static_cast<int>(std::lround(side * canvas.scale())));
    TextureId id = texture(path, pixels, mode);
    if (!id) return false;
    // Whole pixels: crisp at the size it was made for.
    const Vec2 c = canvas.to_pixels(box.center());
    const float x = std::round(c.x - static_cast<float>(pixels) / 2),
                y = std::round(c.y - static_cast<float>(pixels) / 2);
    const float s = canvas.scale();
    const Vec2 off = canvas.to_pixels({0, 0});
    canvas.image(id, {(x - off.x) / s, (y - off.y) / s, static_cast<float>(pixels) / s, static_cast<float>(pixels) / s},
                 tint);
    return true;
}

}  // namespace ttt2::ui
