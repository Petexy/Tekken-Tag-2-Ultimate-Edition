#pragma once

// The launcher's texts in the player's language: every text a player reads goes through tr() (or trn() for one
// that changes with a number), with its key and its English, which is the source: the English is in the code where
// the text is used, and launcher/i18n/en.txt lists every key with it (made from the code by
// launcher/i18n/extract.py, which the tests run). Each other language is a catalog, launcher/i18n/<code>.txt, built
// into the program:
//
//   # comments and blank lines
//   home.play = Spielen
//   fighters.added[one] = {n} Kämpfer hinzugefügt
//   fighters.added[other] = {n} Kämpfer hinzugefügt
//
// one text per line, UTF-8, `{name}` for a value the code puts in (by name, in any order), `\n` a new line, `\\` a
// backslash, `\s` a space (for one at a text's start or end). A text that changes with a number has one line per
// plural form the language has (CLDR's: English and German one/other, French, Italian and Spanish one/many/other,
// Russian and Polish one/few/many/other). A key a catalog lacks shows in English. Logs and command-line output stay
// English. How to add a language: docs/LAUNCHER.md#languages.

#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace launcher::i18n {

// The languages the launcher offers: the game's (runtime/src/host/game_settings.h kLanguages), each by its own name.
struct Language {
    std::string_view code, name;
};
inline constexpr Language kLanguages[] = {
    {"en", "English"},  {"fr", "Français"}, {"de", "Deutsch"}, {"it", "Italiano"},
    {"es", "Español"},  {"ru", "Русский"},  {"pl", "Polski"},
};
// The test language: every English text marked, its letters accented and made about a third longer, so that a text
// that does not go through tr() (plain English) or does not fit shows on the screen. Never offered in Settings.
inline constexpr std::string_view kPseudo = "qps";
// launcher.ini's language for the system's (the default).
inline constexpr std::string_view kSystem = "system";

// The language of `code` (lower case), nullptr when the launcher has none such (kPseudo is none).
const Language* find_language(std::string_view code);

// A value for a placeholder: {name} in a text gets `value`.
struct Arg {
    std::string_view name;
    std::string value;
    Arg(std::string_view n, std::string v) : name(n), value(std::move(v)) {}
    Arg(std::string_view n, std::string_view v) : name(n), value(v) {}
    Arg(std::string_view n, const char* v) : name(n), value(v ? v : "") {}
    Arg(std::string_view n, int v) : name(n), value(std::to_string(v)) {}
    Arg(std::string_view n, long v) : name(n), value(std::to_string(v)) {}
    Arg(std::string_view n, long long v) : name(n), value(std::to_string(v)) {}
    Arg(std::string_view n, unsigned v) : name(n), value(std::to_string(v)) {}
    Arg(std::string_view n, unsigned long v) : name(n), value(std::to_string(v)) {}
    Arg(std::string_view n, unsigned long long v) : name(n), value(std::to_string(v)) {}
};
using Args = std::initializer_list<Arg>;

// The text of `key` in the launcher's language (`english` when its catalog lacks it), its placeholders filled.
std::string tr(std::string_view key, std::string_view english);
std::string tr(std::string_view key, std::string_view english, Args args);
// A text that changes with `n`: the plural form of n in the launcher's language (English: `one` for 1, else
// `other`); {n} is n.
std::string trn(std::string_view key, long long n, std::string_view one, std::string_view other, Args args = {});

// Sets the launcher's language: a code of kLanguages or kPseudo; anything else is English. Safe from any thread.
void set_language(std::string_view code);
// The code of the launcher's language now ("en" for English).
std::string language();
bool english();

// launcher.ini's setting (kSystem, empty or a code) as a language code: the system's for kSystem, empty or one the
// launcher does not have.
std::string resolve(std::string_view setting);
// The system's user interface language as a code of kLanguages, "en" when it is none of them (Linux: LANGUAGE,
// LC_ALL, LC_MESSAGES, LANG; Windows: GetUserDefaultUILanguage).
std::string system_language();
// A locale or language list as the variables have it ("de_DE.UTF-8", "pt_BR:de:en", "C") -> its first code of
// kLanguages, else "" (for system_language; tests).
std::string language_of_locale(std::string_view locale);

// CLDR's plural category of the whole number n in a language: "one", "few", "many" or "other".
std::string_view plural_category(std::string_view code, long long n);
// The categories a language's catalog has a line for in each plural text, in CLDR's order.
std::vector<std::string_view> plural_categories(std::string_view code);

// A catalog file's texts (key or key[category] -> text, escapes undone) and what is wrong in it (line numbers from 1).
struct Catalog {
    std::map<std::string, std::string, std::less<>> texts;
    std::vector<std::string> errors;
};
Catalog parse_catalog(std::string_view text);
// The placeholders' names in a text ({name}), in order, each once.
std::vector<std::string> placeholders(std::string_view text);
// `text` with its placeholders filled ({name} without a value stays as it is; {{ and }} are { and }).
std::string fill(std::string_view text, Args args);
// The pseudo language's form of an English text (its placeholders kept).
std::string pseudo(std::string_view english);

// A number with `digits` decimals as the launcher's language writes it ("1.5" in English, "1,5" in the others).
std::string decimal(double value, int digits);
// A number written with a decimal point ("59.94") as the launcher's language writes it.
std::string decimal(std::string number);
// `text` with its first letter a capital (ASCII, Latin-1, Latin Extended-A and Cyrillic letters): for a value put at a
// sentence's start.
std::string capitalized(std::string text);

} // namespace launcher::i18n
