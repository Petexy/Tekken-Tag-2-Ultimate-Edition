#include "ttt2ui/textures.h"

#include <SDL3/SDL.h>

#include <algorithm>
#include <cstring>

namespace ttt2::ui {

TextureRegistry::~TextureRegistry() {
    for (Entry& e : entries_)
        if (e.texture) SDL_DestroyTexture(e.texture);
}

void TextureRegistry::set_renderer(SDL_Renderer* renderer) {
    for (Entry& e : entries_) {
        if (e.texture && renderer_) SDL_DestroyTexture(e.texture);
        e.texture = nullptr;
    }
    renderer_ = renderer;
    ++generation_;
}

TextureId TextureRegistry::create(int w, int h, std::vector<std::uint8_t> rgba, bool linear) {
    Entry e;
    e.used = true;
    e.kind = Entry::Rgba;
    e.w = w;
    e.h = h;
    e.linear = linear;
    e.pixels = std::move(rgba);
    for (std::size_t i = 0; i < entries_.size(); ++i)
        if (!entries_[i].used) {
            entries_[i] = std::move(e);
            return static_cast<TextureId>(i + 1);
        }
    entries_.push_back(std::move(e));
    return static_cast<TextureId>(entries_.size());
}

TextureId TextureRegistry::create_alpha(int w, int h, std::vector<std::uint8_t> coverage, bool linear) {
    TextureId id = create(w, h, std::move(coverage), linear);
    entries_[id - 1].kind = Entry::Alpha;
    return id;
}

TextureId TextureRegistry::create_target(int w, int h) {
    TextureId id = create(w, h, {}, true);
    entries_[id - 1].kind = Entry::Target;
    return id;
}

void TextureRegistry::destroy(TextureId id) {
    if (id == 0 || id > entries_.size()) return;
    Entry& e = entries_[id - 1];
    if (e.texture) SDL_DestroyTexture(e.texture);
    e = Entry{};
}

void TextureRegistry::update_alpha(TextureId id, int x, int y, int w, int h, const std::uint8_t* coverage, int pitch) {
    if (id == 0 || id > entries_.size()) return;
    Entry& e = entries_[id - 1];
    if (e.kind != Entry::Alpha || x < 0 || y < 0 || x + w > e.w || y + h > e.h) return;
    for (int row = 0; row < h; ++row)
        std::memcpy(&e.pixels[static_cast<std::size_t>(y + row) * e.w + x], coverage + static_cast<std::size_t>(row) * pitch,
                    static_cast<std::size_t>(w));
    if (!e.dirty) {
        e.dx0 = x;
        e.dy0 = y;
        e.dx1 = x + w;
        e.dy1 = y + h;
    } else if (e.dx1 > e.dx0) {
        e.dx0 = std::min(e.dx0, x);
        e.dy0 = std::min(e.dy0, y);
        e.dx1 = std::max(e.dx1, x + w);
        e.dy1 = std::max(e.dy1, y + h);
    }
    e.dirty = true;
}

void TextureRegistry::make(Entry& e) {
    if (!renderer_) return;
    if (e.kind == Entry::Target) {
        e.texture = SDL_CreateTexture(renderer_, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_TARGET, e.w, e.h);
    } else {
        e.texture = SDL_CreateTexture(renderer_, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, e.w, e.h);
    }
    if (!e.texture) return;
    SDL_SetTextureBlendMode(e.texture, SDL_BLENDMODE_BLEND);
    SDL_SetTextureScaleMode(e.texture, e.linear ? SDL_SCALEMODE_LINEAR : SDL_SCALEMODE_NEAREST);
    e.dirty = true;
    e.dx0 = e.dy0 = e.dx1 = e.dy1 = 0;  // (all of it)
}

SDL_Texture* TextureRegistry::get(TextureId id) {
    if (id == 0 || id > entries_.size()) return nullptr;
    Entry& e = entries_[id - 1];
    if (!e.used) return nullptr;
    if (!e.texture) make(e);
    if (!e.texture) return nullptr;
    if (e.dirty && e.kind != Entry::Target) {
        if (e.kind == Entry::Rgba) {
            SDL_UpdateTexture(e.texture, nullptr, e.pixels.data(), e.w * 4);
        } else {
            // White with the coverage as alpha; only the part that changed.
            SDL_Rect r{0, 0, e.w, e.h};
            if (e.dx1 > e.dx0 && e.dy1 > e.dy0) r = {e.dx0, e.dy0, e.dx1 - e.dx0, e.dy1 - e.dy0};
            std::vector<std::uint8_t> rgba(static_cast<std::size_t>(r.w) * r.h * 4);
            for (int y = 0; y < r.h; ++y)
                for (int x = 0; x < r.w; ++x) {
                    std::uint8_t* o = &rgba[(static_cast<std::size_t>(y) * r.w + x) * 4];
                    o[0] = o[1] = o[2] = 255;
                    o[3] = e.pixels[static_cast<std::size_t>(r.y + y) * e.w + r.x + x];
                }
            SDL_UpdateTexture(e.texture, &r, rgba.data(), r.w * 4);
        }
    }
    e.dirty = false;
    e.dx0 = e.dy0 = e.dx1 = e.dy1 = 0;
    return e.texture;
}

bool TextureRegistry::size(TextureId id, int& w, int& h) const {
    if (id == 0 || id > entries_.size() || !entries_[id - 1].used) return false;
    w = entries_[id - 1].w;
    h = entries_[id - 1].h;
    return true;
}

void TextureRegistry::device_reset() {
    // (After a device reset SDL has already freed the old textures' resources; destroying the handles is still
    // needed to release SDL's objects.)
    for (Entry& e : entries_) {
        if (e.texture) SDL_DestroyTexture(e.texture);
        e.texture = nullptr;
    }
    ++generation_;
}

std::size_t TextureRegistry::count() const {
    std::size_t n = 0;
    for (const Entry& e : entries_) n += e.used ? 1 : 0;
    return n;
}

}  // namespace ttt2::ui
