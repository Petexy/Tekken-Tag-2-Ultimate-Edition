#include "title/language.h"

#include <atomic>
#include <iterator>

namespace cafe::title::language {
namespace {

static_assert(std::size(host::game::kLanguages) == kPlaces, "a Text has a place for each language");

std::atomic<size_t> g_place{kEnglish};

} // namespace

void set(const host::game::Language& language) {
    g_place.store(place_of(language.code), std::memory_order_relaxed);
    if (g_place.load(std::memory_order_relaxed) == kPlaces) g_place.store(kEnglish, std::memory_order_relaxed);
}

const host::game::Language& current() { return host::game::kLanguages[place()]; }

Place place_of(std::string_view code) {
    for (size_t i = 0; i < std::size(host::game::kLanguages); ++i) {
        if (host::game::kLanguages[i].code == code) return static_cast<Place>(i);
    }
    return kPlaces;
}

Place place() { return static_cast<Place>(g_place.load(std::memory_order_relaxed)); }

std::string_view in(const Text& text, Place place) {
    const char* const by_place[kPlaces] = {text.en, text.fr, text.de, text.it, text.es, text.ru};
    const char* chosen = place < kPlaces ? by_place[place] : nullptr;
    if (!chosen || !*chosen) chosen = text.en;
    return chosen ? std::string_view(chosen) : std::string_view();
}

std::string_view in_current(const Text& text) { return in(text, place()); }

size_t characters(std::string_view utf8) {
    size_t n = 0;
    for (const char c : utf8) n += (static_cast<unsigned char>(c) & 0xC0) != 0x80;
    return n;
}

} // namespace cafe::title::language
