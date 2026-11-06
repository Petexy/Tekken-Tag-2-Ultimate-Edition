#pragma once
// Fades of a Tekken 8 fighter's summoned weapons (Miary Zo's staffs, tail and horn; the importer's
// convert/summonfade.py and summons8.fade_value). A summon or dismissal value is n | frames << 8: Tekken 8 dissolves
// the object in over that many frames (5 for most) and out again (10), a linear ramp of its material's Transition,
// and draws a dismissed one until its fade ends. Here the weapons of summon n with a ramp (character.ini's fifth
// field) have the rows of their local the ramp names (their bone's axes) scaled by the fade's share, 1 / frames more
// each frame: shown, the first frame drawn at 1 / frames, whole at the last; dismissed, drawn at 1 - 1 / frames ..
// 1 / frames, gone at the last. A ramp's bit 3 (a link under a ramped link of the same summon: the tail's) cancels
// its parent's scale (S L S^-1): each link thins about its own axis. frames 0 or 1: at once (every pack before;
// Noctis's). A row for a summon fading the same way is left alone (Tekken 8's queue); one the other way turns it
// round from the scale it has.
#include <array>
#include <cstdint>
#include <cstring>

namespace cafe::title::summon_fade {
constexpr uint32_t kFadeShift = 8, kSummonBits = 0xFF, kRampRows = 7, kRampUnder = 8;

struct Fade {
    uint32_t frames = 0, t = 0; // runs while frames > 1 and t < frames
    bool in = true;
    bool running() const { return frames > 1 && t < frames; }
    float scale() const { // the object's scale (1: whole; a fade-out's while it runs)
        if (!running()) return 1.0f;
        const float a = static_cast<float>(t) / static_cast<float>(frames);
        return in ? a : 1.0f - a;
    }
};
using Fades = std::array<Fade, 64>; // a player's, by summon number

struct Value {
    uint32_t n = 0, frames = 0;
};
// A summon / dismissal property's value: the summon number and the fade's frames (0 in Tekken 7 fighters' values).
inline Value split(uint32_t value) { return {value & kSummonBits, value >> kFadeShift & 0xFF}; }

// A summon (in) or dismissal (out) of n < 64 with a fade of `frames`; was: n was summoned before it.
inline void start(Fades& fades, uint32_t n, uint32_t frames, bool in, bool was) {
    Fade& f = fades[n];
    if (f.running() && f.in == in) return; // fading that way already
    if (frames <= 1) {                     // at once
        f = Fade{};
        return;
    }
    if (in == was) return; // shown already / not out: nothing to fade
    const float now = f.running() ? f.scale() : (in ? 0.0f : 1.0f); // (one fading the other way turns round)
    const float done = in ? now : 1.0f - now;
    f = Fade{frames, static_cast<uint32_t>(done * static_cast<float>(frames) + 0.5f), in};
    if (!f.running()) f = Fade{};
}

// Once a frame (the posing), before the fades are read.
inline void step(Fades& fades) {
    for (Fade& f : fades) {
        if (!f.running()) continue;
        if (++f.t >= f.frames) f = Fade{}; // whole, or gone
    }
}

// A weapon's local (16 floats as their bits; row-vector rows: the bone's axes, then its position) at `scale`: the
// rows its ramp names scaled; under a ramped weapon (kRampUnder) also the parent's scale cancelled (the columns it
// names divided by scale).
inline void ramp_local(std::array<uint32_t, 16>& local, uint32_t ramp, float scale) {
    const auto factor = [&](int i) { return i < 3 && (ramp >> i & 1) ? scale : 1.0f; };
    for (int row = 0; row < 4; ++row) {
        for (int col = 0; col < 3; ++col) {
            float f = factor(row);
            if (ramp & kRampUnder) f /= factor(col);
            if (f == 1.0f) continue;
            float v;
            std::memcpy(&v, &local[4 * row + col], 4);
            v *= f;
            std::memcpy(&local[4 * row + col], &v, 4);
        }
    }
}
} // namespace cafe::title::summon_fade
