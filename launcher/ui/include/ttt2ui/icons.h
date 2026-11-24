// SVG icons (the launcher's own, built into the program) rasterised by nanosvg per pixel size into the texture
// registry; drawn in their own colours or as a mask tinted with any colour (single-colour "symbolic" icons).
#pragma once

#include <string>
#include <unordered_map>

#include "ttt2ui/canvas.h"

namespace ttt2::ui {

enum class IconMode {
    Colour,  // as drawn
    Mask,    // its shape only: drawn in the tint colour
};

class Icons {
public:
    explicit Icons(TextureRegistry& textures) : textures_(textures) {}
    ~Icons();
    // `path` as the embedded file list names it ("icons/ttt2-input-face_bottom.svg"), or one of the look's line icons
    // ("stroke:check", "stroke:check:3" = stroke width 3 of 24; see icons.cpp); the icon fitted into `box`
    // (points, aspect kept, centred). False when there is no such icon.
    bool draw(Canvas& canvas, const std::string& path, const Rect& box, Color tint = {1, 1, 1, 1},
              IconMode mode = IconMode::Colour);
    bool exists(const std::string& path) const;
    std::size_t cached() const { return cache_.size(); }

private:
    TextureId texture(const std::string& path, int pixels, IconMode mode);
    TextureRegistry& textures_;
    std::unordered_map<std::string, TextureId> cache_;
};

}  // namespace ttt2::ui
