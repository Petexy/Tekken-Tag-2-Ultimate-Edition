// The launcher's texts in the player's language (i18n.h): catalogs, plural forms, placeholders, the system's
// language, the pseudo language, and every built-in catalog read without an error.

#include "i18n.h"

#include "ttt2_launcher_i18n.h"

#include <cstdio>
#include <cstdlib>
#include <string>

using namespace launcher::i18n;

namespace {

int failures = 0;

void check(bool ok, const std::string& what) {
    if (!ok) {
        std::fprintf(stderr, "FAILED: %s\n", what.c_str());
        ++failures;
    }
}

void check_eq(const std::string& got, const std::string& want, const std::string& what) {
    if (got != want) {
        std::fprintf(stderr, "FAILED: %s\n    got:  %s\n    want: %s\n", what.c_str(), got.c_str(), want.c_str());
        ++failures;
    }
}

} // namespace

int main() {
    // ---- English: the text in the code, its placeholders filled.
    set_language("en");
    check(english(), "en is English");
    check_eq(tr("test.plain", "Play"), "Play", "English as it is");
    check_eq(tr("test.args", "Adding {name} ({i} of {n})", {{"name", "Kazumi"}, {"i", 2}, {"n", 3}}),
             "Adding Kazumi (2 of 3)", "placeholders by name");
    check_eq(tr("test.missing", "{a} and {b}", {{"a", "x"}}), "x and {b}", "a placeholder without a value stays");
    check_eq(tr("test.braces", "{{a}} {a}", {{"a", "x"}}), "{a} x", "{{ and }} are braces");
    check_eq(tr("test.once", "{a}", {{"a", "{b}"}, {"b", "no"}}), "{b}", "a value is not filled again");
    check_eq(trn("test.n", 1, "{n} fighter", "{n} fighters"), "1 fighter", "English one");
    check_eq(trn("test.n", 0, "{n} fighter", "{n} fighters"), "0 fighters", "English other (0)");
    check_eq(trn("test.n", 21, "{n} fighter", "{n} fighters"), "21 fighters", "English other (21)");
    check_eq(decimal(1.25, 1), "1.2", "English decimal point");

    // ---- CLDR's plural categories.
    const auto cat = [](const char* code, long long n) { return std::string(plural_category(code, n)); };
    check_eq(cat("de", 1), "one", "de 1");
    check_eq(cat("de", 2), "other", "de 2");
    check_eq(cat("fr", 0), "one", "fr 0 is one");
    check_eq(cat("fr", 1), "one", "fr 1");
    check_eq(cat("fr", 2), "other", "fr 2");
    check_eq(cat("fr", 1000000), "many", "fr a million");
    check_eq(cat("es", 0), "other", "es 0");
    check_eq(cat("it", 1), "one", "it 1");
    for (const auto& [n, want] : {std::pair{1LL, "one"}, {2LL, "few"}, {4LL, "few"}, {5LL, "many"}, {11LL, "many"},
                                  {12LL, "many"}, {14LL, "many"}, {21LL, "one"}, {22LL, "few"}, {25LL, "many"},
                                  {101LL, "one"}, {111LL, "many"}, {0LL, "many"}}) {
        check_eq(cat("ru", n), want, "ru " + std::to_string(n));
    }
    for (const auto& [n, want] : {std::pair{1LL, "one"}, {2LL, "few"}, {5LL, "many"}, {12LL, "many"},
                                  {21LL, "many"}, {22LL, "few"}, {0LL, "many"}}) {
        check_eq(cat("pl", n), want, "pl " + std::to_string(n));
    }
    check(plural_categories("ru").size() == 4 && plural_categories("fr").size() == 3 &&
              plural_categories("de").size() == 2,
          "each language's plural forms");

    // ---- A catalog's format.
    const Catalog c = parse_catalog("\xEF\xBB\xBF# a comment\n"
                                    "\n"
                                    "home.play = Spielen  \r\n"
                                    "  fighters.n[one] = {n} Kämpfer\n"
                                    "fighters.n[other]={n} Kämpfer\n"
                                    "lines = one\\ntwo\\\\ \\send\\s\n"
                                    "no equals sign\n"
                                    "bad key! = x\n"
                                    "bad.form[some] = x\n"
                                    "home.play = again\n"
                                    "lone = x\\\n"
                                    "odd = \\q\n");
    check_eq(c.texts.count("home.play") ? c.texts.at("home.play") : "", "Spielen", "key = text, spaces trimmed");
    check_eq(c.texts.count("fighters.n[one]") ? c.texts.at("fighters.n[one]") : "", "{n} Kämpfer", "plural form");
    check_eq(c.texts.count("lines") ? c.texts.at("lines") : "", "one\ntwo\\  end ", "escapes");
    check(c.errors.size() == 6, "six errors (" + std::to_string(c.errors.size()) + ")");
    for (const std::string& e : c.errors) std::printf("  (expected) %s\n", e.c_str());
    check(placeholders("{a} {b} {a} {{c}} {d e}") == std::vector<std::string>{"a", "b"}, "placeholders");

    // ---- The system's language.
    check_eq(language_of_locale("de_DE.UTF-8"), "de", "de_DE.UTF-8");
    check_eq(language_of_locale("pt_BR:ru:en"), "ru", "a list: its first known");
    check_eq(language_of_locale("C"), "", "C is none");
    check_eq(language_of_locale("POSIX"), "", "POSIX is none");
    check_eq(language_of_locale("pl"), "pl", "a bare code");
    check_eq(language_of_locale("fr_CA@euro"), "fr", "a modifier");
    check_eq(language_of_locale("ja_JP.UTF-8"), "", "one the launcher lacks");
#ifndef _WIN32
    unsetenv("LANGUAGE");
    unsetenv("LC_ALL");
    unsetenv("LC_MESSAGES");
    setenv("LANG", "es_ES.UTF-8", 1);
    check_eq(system_language(), "es", "LANG");
    setenv("LC_MESSAGES", "it_IT.UTF-8", 1);
    check_eq(system_language(), "it", "LC_MESSAGES over LANG");
    setenv("LANGUAGE", "ru:en", 1);
    check_eq(system_language(), "ru", "LANGUAGE first");
    setenv("LC_ALL", "C", 1);
    unsetenv("LANGUAGE");
    check_eq(system_language(), "en", "C: English");
    setenv("LANG", "ja_JP.UTF-8", 1);
    unsetenv("LC_ALL");
    unsetenv("LC_MESSAGES");
    check_eq(system_language(), "en", "none of them: English");
    check_eq(resolve("system"), "en", "System");
    check_eq(resolve("de"), "de", "a code");
    check_eq(resolve("xx"), "en", "an unknown code: the system's");
    check_eq(resolve("qps"), "qps", "the pseudo language");
#endif

    // ---- The pseudo language: marked, accented, longer, placeholders kept.
    set_language(kPseudo);
    check(!english(), "qps is not English");
    const std::string p = tr("test.args", "Adding {name}", {{"name", "Kazumi"}});
    check(p.front() == '[' && p.find("Kazumi") != std::string::npos && p.find("Åddíñg") != std::string::npos,
          "pseudo: " + p);
    check(pseudo("Settings").size() > std::string("Settings").size() * 13 / 10, "pseudo is longer");
    check_eq(decimal(1.25, 1), "1.2", "pseudo keeps the point");

    // ---- A language: its catalog's text, else English; its plural form; its decimal comma.
    set_language("ru");
    check_eq(language(), "ru", "set to ru");
    check_eq(tr("test.absent", "Not there"), "Not there", "a key the catalog lacks: English");
    check_eq(trn("test.absent", 3, "{n} fighter", "{n} fighters"), "3 fighters", "a plural the catalog lacks: English");
    check_eq(decimal(1.25, 1), "1,2", "ru decimal comma");
    check_eq(capitalized("ещё"), "Ещё", "Cyrillic capital");
    check_eq(capitalized("łatwo"), "Łatwo", "Polish capital");
    check_eq(capitalized("étape"), "Étape", "Latin-1 capital");
    check_eq(capitalized("über"), "Über", "German capital");
    check_eq(capitalized("ok"), "Ok", "ASCII capital");
    set_language("xx");
    check(english(), "an unknown code is English");

    // ---- Every built-in catalog reads without an error.
    for (const Language& l : kLanguages) {
        if (l.code == "en") continue;
        const ttt2_i18n::File* f = ttt2_i18n::find(std::string(l.code) + ".txt");
        check(f != nullptr, std::string(l.code) + ".txt is built in");
        if (!f) continue;
        const Catalog cat_l = parse_catalog(std::string_view(reinterpret_cast<const char*>(f->data), f->size));
        for (const std::string& e : cat_l.errors) check(false, std::string(l.code) + ".txt " + e);
    }

    if (failures) {
        std::fprintf(stderr, "%d failed\n", failures);
        return 1;
    }
    std::printf("i18n: all passed\n");
    return 0;
}
