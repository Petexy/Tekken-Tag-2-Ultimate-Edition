#pragma once

// The language the game shows its texts in (game.ini's language: see
// host/game_settings.h), and the port's own texts in each of them.
//
// The title has every language's text banks in memory at once and reads
// the console's language (cafe.language: os/system_config.cpp) to choose
// among them. The port's own texts (labels, descriptions it writes over the
// title's, names of its own modes) come in each language the game can be
// shown in, chosen here; one a language lacks is English.

#include "host/game_settings.h"

#include <cstddef>
#include <string_view>

namespace cafe::title::language {

// The languages' places in a Text, in host::game::kLanguages' order.
enum Place : size_t { kEnglish, kFrench, kGerman, kItalian, kSpanish, kRussian, kPlaces };

// A text of the port's in each language (UTF-8; null or empty: English's).
struct Text {
    const char* en;
    const char* fr = nullptr;
    const char* de = nullptr;
    const char* it = nullptr;
    const char* es = nullptr;
    const char* ru = nullptr;
};

// Before the title runs (main.cpp, with game.ini's language).
void set(const host::game::Language& language);

// The language set (English until set).
const host::game::Language& current();

// The place of `code` (kLanguages' codes), or kPlaces for one the game does not have.
Place place_of(std::string_view code);

// The language's place (English until set).
Place place();

// `text` in the language at `place`, else in English.
std::string_view in(const Text& text, Place place);

// `text` in the language set.
std::string_view in_current(const Text& text);

// The number of characters of a UTF-8 text (the title's texts hold it before their bytes).
size_t characters(std::string_view utf8);

} // namespace cafe::title::language
