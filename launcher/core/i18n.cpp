// The launcher's texts in the player's language (see i18n.h).

#include "i18n.h"

#include "ttt2_launcher_i18n.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <mutex>
#include <sstream>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace launcher::i18n {
namespace {

constexpr int kEnglish = 0;
constexpr int kCount = static_cast<int>(std::size(kLanguages));
constexpr int kPseudoIndex = kCount; // (after the languages)

std::atomic<int> g_language{kEnglish};

// Every language's catalog, read once: the built-in files, or TTT2_LAUNCHER_I18N_DIR's (a translator's try-out).
const std::array<Catalog, kCount>& catalogs() {
    static std::array<Catalog, kCount> all;
    static std::once_flag once;
    std::call_once(once, [] {
        const char* dir = std::getenv("TTT2_LAUNCHER_I18N_DIR");
        for (int i = 1; i < kCount; ++i) {
            const std::string file = std::string(kLanguages[i].code) + ".txt";
            std::string text;
            if (dir && *dir) {
                std::ifstream in(std::string(dir) + "/" + file, std::ios::binary);
                std::ostringstream o;
                o << in.rdbuf();
                text = o.str();
            }
            if (text.empty()) {
                if (const ttt2_i18n::File* f = ttt2_i18n::find(file))
                    text.assign(reinterpret_cast<const char*>(f->data), f->size);
            }
            all[static_cast<size_t>(i)] = parse_catalog(text);
        }
    });
    return all;
}

bool key_char(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '.' ||
           c == '-';
}

bool name_char(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'; }

// The placeholder's name at text[i] == '{' ("" when it is none), and its end (past '}').
std::string_view placeholder_at(std::string_view text, size_t i, size_t* end) {
    size_t j = i + 1;
    while (j < text.size() && name_char(text[j])) ++j;
    if (j == i + 1 || j >= text.size() || text[j] != '}') return {};
    *end = j + 1;
    return text.substr(i + 1, j - i - 1);
}

const std::string* find_text(int language, std::string_view key) {
    if (language <= kEnglish || language >= kCount) return nullptr;
    const Catalog& c = catalogs()[static_cast<size_t>(language)];
    const auto it = c.texts.find(key);
    return it != c.texts.end() ? &it->second : nullptr;
}

bool in_range(long long n, long long from, long long to) { return n >= from && n <= to; }

std::string fill_range(std::string_view text, const Arg* first, const Arg* last);

} // namespace

const Language* find_language(std::string_view code) {
    for (const Language& l : kLanguages)
        if (l.code == code) return &l;
    return nullptr;
}

void set_language(std::string_view code) {
    int index = kEnglish;
    if (code == kPseudo) index = kPseudoIndex;
    else if (const Language* l = find_language(code)) index = static_cast<int>(l - kLanguages);
    if (index != kEnglish && index != kPseudoIndex) catalogs(); // (read before the first text needs them)
    g_language.store(index);
}

std::string language() {
    const int i = g_language.load();
    return i == kPseudoIndex ? std::string(kPseudo) : std::string(kLanguages[i].code);
}

bool english() { return g_language.load() == kEnglish; }

std::string tr(std::string_view key, std::string_view english) { return tr(key, english, {}); }

std::string tr(std::string_view key, std::string_view english, Args args) {
    const int language = g_language.load();
    if (language == kPseudoIndex) return fill(pseudo(english), args);
    const std::string* text = find_text(language, key);
    return fill(text ? std::string_view(*text) : english, args);
}

std::string trn(std::string_view key, long long n, std::string_view one, std::string_view other, Args args) {
    const int language = g_language.load();
    std::vector<Arg> all(args);
    all.emplace_back("n", n);
    const auto filled = [&](std::string_view text) { return fill_range(text, all.data(), all.data() + all.size()); };
    std::string_view english = n == 1 ? one : other;
    if (language == kPseudoIndex) return filled(pseudo(english));
    if (language != kEnglish) {
        const std::string category(plural_category(kLanguages[language].code, n));
        const std::string base(key);
        if (const std::string* text = find_text(language, base + "[" + category + "]")) return filled(*text);
        if (const std::string* text = find_text(language, base + "[other]")) return filled(*text);
    }
    return filled(english);
}

std::string_view plural_category(std::string_view code, long long n) {
    const long long a = n < 0 ? -n : n;
    const long long ten = a % 10, hundred = a % 100;
    if (code == "fr") {
        if (a == 0 || a == 1) return "one";
        if (a != 0 && a % 1000000 == 0) return "many";
        return "other";
    }
    if (code == "it" || code == "es") {
        if (a == 1) return "one";
        if (a != 0 && a % 1000000 == 0) return "many";
        return "other";
    }
    if (code == "ru") {
        if (ten == 1 && hundred != 11) return "one";
        if (in_range(ten, 2, 4) && !in_range(hundred, 12, 14)) return "few";
        return "many"; // (CLDR's "other" is for fractions only)
    }
    if (code == "pl") {
        if (a == 1) return "one";
        if (in_range(ten, 2, 4) && !in_range(hundred, 12, 14)) return "few";
        return "many";
    }
    return a == 1 ? "one" : "other"; // en, de
}

std::vector<std::string_view> plural_categories(std::string_view code) {
    if (code == "fr" || code == "it" || code == "es") return {"one", "many", "other"};
    if (code == "ru" || code == "pl") return {"one", "few", "many", "other"};
    return {"one", "other"};
}

Catalog parse_catalog(std::string_view text) {
    Catalog c;
    size_t number = 0;
    while (!text.empty()) {
        const size_t newline = text.find('\n');
        std::string_view line = text.substr(0, newline);
        text.remove_prefix(newline == std::string_view::npos ? text.size() : newline + 1);
        ++number;
        if (number == 1 && line.starts_with("\xEF\xBB\xBF")) line.remove_prefix(3); // (a byte order mark)
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t')) line.remove_suffix(1);
        size_t start = 0;
        while (start < line.size() && (line[start] == ' ' || line[start] == '\t')) ++start;
        line.remove_prefix(start);
        if (line.empty() || line.front() == '#') continue;
        const std::string where = "line " + std::to_string(number) + ": ";
        const size_t eq = line.find('=');
        if (eq == std::string_view::npos) {
            c.errors.push_back(where + "no '=' in it");
            continue;
        }
        std::string_view key = line.substr(0, eq), value = line.substr(eq + 1);
        while (!key.empty() && (key.back() == ' ' || key.back() == '\t')) key.remove_suffix(1);
        while (!value.empty() && (value.front() == ' ' || value.front() == '\t')) value.remove_prefix(1);
        std::string_view base = key, form;
        if (const size_t open = key.find('['); open != std::string_view::npos && key.back() == ']') {
            base = key.substr(0, open);
            form = key.substr(open + 1, key.size() - open - 2);
        }
        const bool good_form =
            form.empty() || form == "zero" || form == "one" || form == "two" || form == "few" || form == "many" ||
            form == "other";
        if (base.empty() || !std::all_of(base.begin(), base.end(), key_char) || !good_form ||
            (key.find('[') != std::string_view::npos && form.empty())) {
            c.errors.push_back(where + "the key \"" + std::string(key) + "\" is not one");
            continue;
        }
        std::string out;
        for (size_t i = 0; i < value.size(); ++i) {
            if (value[i] != '\\' || i + 1 == value.size()) {
                if (value[i] == '\\') c.errors.push_back(where + "a lone \\ at the end");
                out += value[i];
                continue;
            }
            switch (value[++i]) {
            case 'n': out += '\n'; break;
            case 't': out += '\t'; break;
            case 's': out += ' '; break;
            case '\\': out += '\\'; break;
            default:
                c.errors.push_back(where + "\\" + value[i] + " is no escape (\\n, \\t, \\s or \\\\)");
                out += '\\';
                out += value[i];
            }
        }
        if (!c.texts.emplace(std::string(key), std::move(out)).second)
            c.errors.push_back(where + "\"" + std::string(key) + "\" is there twice");
    }
    return c;
}

std::vector<std::string> placeholders(std::string_view text) {
    std::vector<std::string> names;
    for (size_t i = 0; i < text.size(); ++i) {
        if (text[i] != '{') continue;
        if (i + 1 < text.size() && text[i + 1] == '{') {
            ++i;
            continue;
        }
        size_t end = 0;
        const std::string_view name = placeholder_at(text, i, &end);
        if (name.empty()) continue;
        if (std::find(names.begin(), names.end(), name) == names.end()) names.emplace_back(name);
        i = end - 1;
    }
    return names;
}

std::string fill(std::string_view text, Args args) { return fill_range(text, args.begin(), args.end()); }

std::string decimal(double value, int digits) {
    char text[64];
    std::snprintf(text, sizeof text, "%.*f", digits, value);
    return decimal(std::string(text));
}

std::string decimal(std::string number) {
    // (CLDR: every language here but English writes a decimal comma.)
    const int language = g_language.load();
    if (language != kEnglish && language != kPseudoIndex) std::replace(number.begin(), number.end(), '.', ',');
    return number;
}

std::string capitalized(std::string text) {
    if (text.empty()) return text;
    const auto c0 = static_cast<unsigned char>(text[0]);
    if (c0 < 0x80) {
        if (c0 >= 'a' && c0 <= 'z') text[0] = static_cast<char>(c0 - 32);
        return text;
    }
    if ((c0 & 0xE0) != 0xC0 || text.size() < 2) return text;
    const unsigned cp = ((c0 & 0x1Fu) << 6) | (static_cast<unsigned char>(text[1]) & 0x3Fu);
    unsigned upper = cp;
    if ((cp >= 0xE0 && cp <= 0xFE && cp != 0xF7) || (cp >= 0x430 && cp <= 0x44F)) upper = cp - 0x20;
    else if (cp >= 0x450 && cp <= 0x45F) upper = cp - 0x50;
    else if ((cp >= 0x100 && cp <= 0x137) || (cp >= 0x14A && cp <= 0x177)) upper = cp & ~1u;
    else if ((cp >= 0x139 && cp <= 0x148) || (cp >= 0x179 && cp <= 0x17E)) upper = (cp % 2 == 0) ? cp - 1 : cp;
    text[0] = static_cast<char>(0xC0 | (upper >> 6));
    text[1] = static_cast<char>(0x80 | (upper & 0x3F));
    return text;
}

namespace {

std::string fill_range(std::string_view text, const Arg* first, const Arg* last) {
    if (text.find('{') == std::string_view::npos && text.find('}') == std::string_view::npos) return std::string(text);
    std::string out;
    out.reserve(text.size() + 32);
    for (size_t i = 0; i < text.size(); ++i) {
        const char c = text[i];
        if ((c == '{' || c == '}') && i + 1 < text.size() && text[i + 1] == c) {
            out += c;
            ++i;
            continue;
        }
        if (c == '{') {
            size_t end = 0;
            const std::string_view name = placeholder_at(text, i, &end);
            if (!name.empty()) {
                const Arg* it = std::find_if(first, last, [&](const Arg& a) { return a.name == name; });
                if (it != last) {
                    out += it->value;
                    i = end - 1;
                    continue;
                }
            }
        }
        out += c;
    }
    return out;
}

} // namespace

std::string pseudo(std::string_view english) {
    if (english.empty()) return {};
    static const std::pair<char, const char*> kAccents[] = {
        {'a', "á"}, {'e', "é"}, {'i', "í"}, {'o', "ö"}, {'u', "ü"}, {'c', "ç"}, {'n', "ñ"}, {'s', "š"}, {'z', "ž"},
        {'y', "ý"}, {'A', "Å"}, {'E', "É"}, {'I', "Î"}, {'O', "Ö"}, {'U', "Ü"}, {'C', "Ç"}, {'N', "Ñ"}, {'S', "Š"},
        {'Z', "Ž"}, {'Y', "Ý"}};
    std::string out = "[";
    size_t letters = 0;
    for (size_t i = 0; i < english.size(); ++i) {
        const char c = english[i];
        if (c == '{') {
            size_t end = 0;
            if (!placeholder_at(english, i, &end).empty()) {
                out.append(english.substr(i, end - i));
                i = end - 1;
                continue;
            }
        }
        const auto it = std::find_if(std::begin(kAccents), std::end(kAccents), [c](const auto& p) { return p.first == c; });
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) ++letters;
        out += it != std::end(kAccents) ? it->second : std::string(1, c);
    }
    // (About a third longer, as German and Russian are.)
    out += ' ';
    out.append(std::max<size_t>(1, (letters + 2) / 3), '~');
    out += ']';
    return out;
}

std::string language_of_locale(std::string_view locale) {
    while (!locale.empty()) {
        const size_t colon = locale.find(':');
        std::string_view one = locale.substr(0, colon);
        locale.remove_prefix(colon == std::string_view::npos ? locale.size() : colon + 1);
        const size_t cut = one.find_first_of("_.@-");
        std::string code(one.substr(0, cut));
        std::transform(code.begin(), code.end(), code.begin(), [](unsigned char ch) { return std::tolower(ch); });
        if (find_language(code)) return code;
    }
    return {};
}

std::string system_language() {
#ifdef _WIN32
    switch (PRIMARYLANGID(GetUserDefaultUILanguage())) {
    case LANG_FRENCH: return "fr";
    case LANG_GERMAN: return "de";
    case LANG_ITALIAN: return "it";
    case LANG_SPANISH: return "es";
    case LANG_RUSSIAN: return "ru";
    case LANG_POLISH: return "pl";
    default: return "en";
    }
#else
    const auto variable = [](const char* name) -> std::string_view {
        const char* v = std::getenv(name);
        return v ? std::string_view(v) : std::string_view();
    };
    std::string_view locale = variable("LC_ALL");
    if (locale.empty()) locale = variable("LC_MESSAGES");
    if (locale.empty()) locale = variable("LANG");
    // (gettext's rule: LANGUAGE's list comes first, unless the locale is C.)
    if (const std::string_view list = variable("LANGUAGE"); !list.empty() && locale != "C" && locale != "POSIX") {
        if (std::string code = language_of_locale(list); !code.empty()) return code;
    }
    if (std::string code = language_of_locale(locale); !code.empty()) return code;
    return "en";
#endif
}

std::string resolve(std::string_view setting) {
    if (setting == kPseudo) return std::string(kPseudo);
    if (find_language(setting)) return std::string(setting);
    return system_language();
}

} // namespace launcher::i18n
