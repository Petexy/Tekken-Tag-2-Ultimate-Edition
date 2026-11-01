#pragma once

// How the title presents buttons and its logo on a computer:
// - Menus confirm with the bottom face button and go back with the right
//   one, as on the other consoles (Nintendo controllers keep the Wii U's
//   right-button confirm). The title has this choice built in, from its
//   PlayStation 3 version's system setting; its icons follow it.
// - Button icons follow the controller in use: PlayStation controllers get
//   PlayStation-style icons drawn here, others neutral ones (face buttons
//   shown by their place on the pad). Both are made from the title's font.
// - The title screen's logo is subtitled "Ultimate Edition" in the brush
//   lettering of its "Wii U Edition"; the copyright line loses the words.
// Everything is made from the Wii U game's own files.

#include "title/image.h"

#include <cstdint>
#include <functional>
#include <optional>
#include <vector>

namespace cafe::title {

// After vfs::open_game and the image load, before the title runs.
void prepare_presentation();

// An entry of the title's archives ("content/hdd/data003", the entry's name
// hash), unpacked, as the game has it; its NRCZ header flags in `flags`.
std::optional<std::vector<uint8_t>> game_file(const char* archive, uint32_t hash, uint8_t (*flags)[8] = nullptr);

// The title's texture shows `contents()` instead (RGBA8, its size; null:
// its own); gpu::texture_replacements_changed() when that changes. Before
// the title runs.
void replace_texture(const ntp3::Texture& original, std::function<const std::vector<uint8_t>*()> contents);

} // namespace cafe::title
