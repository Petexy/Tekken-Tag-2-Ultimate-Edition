// Every texture of the interface goes through this registry, which keeps what it needs to make it again: when the
// renderer loses its textures (SDL_EVENT_RENDER_DEVICE_RESET: driver update, TDR, RDP) they are rebuilt from their
// CPU pixels, and render targets are recreated empty (their owners see generation() change and draw them again).
#pragma once

#include <cstdint>
#include <vector>

struct SDL_Renderer;
struct SDL_Texture;

namespace ttt2::ui {

using TextureId = std::uint32_t;  // 0 = none

class TextureRegistry {
public:
    explicit TextureRegistry(SDL_Renderer* renderer = nullptr) : renderer_(renderer) {}
    ~TextureRegistry();
    TextureRegistry(const TextureRegistry&) = delete;
    TextureRegistry& operator=(const TextureRegistry&) = delete;

    void set_renderer(SDL_Renderer* renderer);  // (drops every SDL texture; they are made again on use)
    SDL_Renderer* renderer() const { return renderer_; }

    // RGBA32 pixels (straight alpha), kept for rebuilding. `linear`: filtered when scaled.
    TextureId create(int w, int h, std::vector<std::uint8_t> rgba, bool linear = true);
    // A one-channel coverage image shown as white with that alpha (glyph atlas pages); kept likewise.
    TextureId create_alpha(int w, int h, std::vector<std::uint8_t> coverage, bool linear = true);
    // Replace a region of an alpha texture's coverage (glyphs added to a page).
    void update_alpha(TextureId id, int x, int y, int w, int h, const std::uint8_t* coverage, int pitch);
    // A render target of w x h pixels (contents are lost on a reset: see generation()).
    TextureId create_target(int w, int h);
    void destroy(TextureId id);

    // The SDL texture (made now if needed); nullptr without a renderer or when SDL refuses.
    SDL_Texture* get(TextureId id);
    bool size(TextureId id, int& w, int& h) const;

    // The renderer lost its textures: drop them all (made again from the CPU copies on use); targets are new and
    // empty. Call on SDL_EVENT_RENDER_DEVICE_RESET.
    void device_reset();
    // Only the render targets' contents were lost (SDL_EVENT_RENDER_TARGETS_RESET): their owners redraw them.
    void targets_reset() { ++generation_; }
    // Counts device resets: owners of render targets redraw them when it changed.
    unsigned generation() const { return generation_; }
    std::size_t count() const;

private:
    struct Entry {
        bool used = false;
        enum Kind { Rgba, Alpha, Target } kind = Rgba;
        int w = 0, h = 0;
        bool linear = true;
        std::vector<std::uint8_t> pixels;  // RGBA or coverage
        SDL_Texture* texture = nullptr;
        bool dirty = false;  // the CPU copy changed after the texture was made
        int dx0 = 0, dy0 = 0, dx1 = 0, dy1 = 0;  // ... in this rectangle (alpha textures; empty = all)
    };
    void make(Entry& e);
    SDL_Renderer* renderer_ = nullptr;
    std::vector<Entry> entries_;  // id = index + 1
    unsigned generation_ = 0;
};

}  // namespace ttt2::ui
