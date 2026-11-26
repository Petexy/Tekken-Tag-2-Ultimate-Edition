// game.ini (see game_ini.h).

#include "game_ini.h"
#include "i18n.h"
#include "utf8_path.h"

#include "files.h"
#include "host/file_io.h"
#include "host/game_settings.h"

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>
#include <utility>

namespace launcher::game_ini {
namespace {

// A hand-edited file is a few hundred bytes; anything much larger is not one (as display.ini).
constexpr std::uint64_t kMostBytes = 64 * 1024;

bool space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\v' || c == '\f'; }

std::string_view trim(std::string_view s) {
    while (!s.empty() && space(s.front())) s.remove_prefix(1);
    while (!s.empty() && space(s.back())) s.remove_suffix(1);
    return s;
}

// `#` starts a comment at the start of a line or after a space (a `#` inside a word is part of it).
std::string_view strip_comment(std::string_view line) {
    for (size_t i = 0; i < line.size(); ++i) {
        if (line[i] == '#' && (i == 0 || space(line[i - 1]))) return line.substr(0, i);
    }
    return line;
}

// The setting a line gives: its key ("" for none: a comment, an empty line, not "key = value") and its value.
std::pair<std::string_view, std::string_view> setting_of(std::string_view line) {
    line = trim(strip_comment(line));
    const size_t equals = line.find('=');
    if (line.empty() || equals == std::string_view::npos) return {};
    return {trim(line.substr(0, equals)), trim(line.substr(equals + 1))};
}

// The UTF-8 sequence at `at` (its length; 1 for a byte that does not start a whole one) and its character.
size_t decode(std::string_view s, size_t at, char32_t* c) {
    const auto b = static_cast<unsigned char>(s[at]);
    const size_t n = b < 0x80 ? 1 : (b >> 5) == 6 ? 2 : (b >> 4) == 14 ? 3 : (b >> 3) == 30 ? 4 : 0;
    if (n == 0 || at + n > s.size()) {
        *c = 0xFFFD;
        return 1;
    }
    char32_t v = n == 1 ? b : n == 2 ? (b & 0x1F) : n == 3 ? (b & 0x0F) : (b & 0x07);
    for (size_t i = 1; i < n; ++i) {
        const auto x = static_cast<unsigned char>(s[at + i]);
        if ((x >> 6) != 2) {
            *c = 0xFFFD;
            return 1;
        }
        v = (v << 6) | (x & 0x3F);
    }
    *c = v;
    return n;
}

size_t characters(std::string_view s) {
    size_t count = 0;
    for (size_t at = 0; at < s.size(); ++count) {
        char32_t c;
        at += decode(s, at, &c);
    }
    return count;
}

// A new file's first lines: what it is, and its keys (the languages' codes from the game's own list).
std::string header() {
    std::string codes;
    const size_t count = std::size(cafe::host::game::kLanguages);
    for (size_t i = 0; i < count; ++i)
        codes += (i == 0 ? "" : i + 1 == count ? " or " : ", ") + std::string(cafe::host::game::kLanguages[i].code);
    return "# Tekken Tag Tournament 2's game settings, written by the launcher's Settings.\n"
           "# The game reads them when it starts.\n"
           "# player_name: the name the game shows for you (without it, its own: Player in English).\n"
           "# language: the language of its texts and menus: " + codes + " (without it, English).\n";
}

// `text` with `key` set to `value`: one line of it, where the first line of the key was (`at_last`: the last one,
// the line that counts), the key's other lines left out, or added at the end; an empty `value` leaves the key out.
// Every other line kept as it was. A new file (nothing in `text`) gets the header.
std::string with_setting(std::string_view text, std::string_view key, std::string_view value, bool at_last) {
    const std::string line = std::string(key) + " = " + std::string(value);
    // (A file with nothing in it: a new one.)
    std::string_view rest = text.starts_with("\xEF\xBB\xBF") ? text.substr(3) : text;
    while (!rest.empty() && (space(rest.front()) || rest.front() == '\n')) rest.remove_prefix(1);
    if (rest.empty()) return value.empty() ? header() : header() + line + "\n";
    // Each line: whole (with its end), without its end, whether it gives the key.
    struct Part {
        std::string_view whole, body;
        bool keyed, marked; // marked: the file's byte order mark starts it (the first line only, as the game reads it)
    };
    std::vector<Part> parts;
    size_t keyed = 0;
    while (!text.empty()) {
        const size_t end = text.find('\n');
        const std::string_view whole = text.substr(0, end == std::string_view::npos ? text.size() : end + 1);
        text.remove_prefix(whole.size());
        std::string_view body = whole;
        if (body.ends_with('\n')) body.remove_suffix(1);
        const bool marked = parts.empty() && body.starts_with("\xEF\xBB\xBF");
        const bool is_key = setting_of(marked ? body.substr(3) : body).first == key;
        keyed += is_key;
        parts.push_back({whole, body, is_key, marked});
    }
    std::string out;
    size_t seen = 0;
    for (const Part& p : parts) {
        if (!p.keyed) {
            out += p.whole;
            continue;
        }
        // (One line of the key takes the new value; another would win over it, or lose to it: left out.)
        ++seen;
        if (p.marked) out += "\xEF\xBB\xBF"; // (the file's byte order mark stays)
        if (value.empty() || seen != (at_last ? keyed : 1)) continue;
        out += line + (p.body.ends_with('\r') ? "\r\n" : "\n");
    }
    if (keyed == 0 && !value.empty()) {
        if (!out.empty() && out.back() != '\n') out += '\n';
        out += line + "\n";
    }
    return out;
}

// Saves `file` with `change` made to what it has (written anew when it cannot be read: what it had cannot be kept).
template <typename Change>
bool save_with(const fs::path& file, Change change, std::string* error) {
    const Loaded now = load(file);
    return replace_file(file, change(now.error.empty() ? std::string_view(now.text) : std::string_view()), error);
}

} // namespace

fs::path beside(const fs::path& display_file) { return display_file.parent_path() / "game.ini"; }

bool name_character(char32_t c) { return c >= 0x20 && c <= 0x7E && c != '#'; }

std::string_view own_name(std::string_view language) {
    // (The game's text common 1599 in each language's bank; Polish's is ours, over English's.)
    static constexpr std::pair<std::string_view, std::string_view> kWords[] = {
        {"en", kDefaultName}, {"fr", "Joueur"}, {"de", "Spieler"}, {"it", "Giocatore"},
        {"es", "Jugador"},    {"ru", ""},       {"pl", "Gracz"},
    };
    const cafe::host::game::Language* l = cafe::host::game::find_language(language);
    const std::string_view code = l ? l->code : std::string_view("en");
    for (const auto& [c, word] : kWords) {
        if (c == code) return word;
    }
    return kDefaultName; // (a language added to the game's list without its word here: tests say so)
}

std::string name_rule() {
    return i18n::trn("name.rule", static_cast<long long>(kNameMost),
                     "Up to {n} character: the letters A to Z, digits, spaces and the punctuation of an English "
                     "keyboard but #.",
                     "Up to {n} characters: the letters A to Z, digits, spaces and the punctuation of an English "
                     "keyboard but #.");
}

std::string tidy_name(std::string_view name) { return std::string(trim(name)); }

std::string first_refused(std::string_view text) {
    for (size_t at = 0; at < text.size();) {
        char32_t c;
        const size_t n = decode(text, at, &c);
        // (Any byte past ASCII: a name is ASCII, and an overlong sequence must not pass as the letter it spells.)
        if (static_cast<unsigned char>(text[at]) >= 0x80 || !name_character(c)) return std::string(text.substr(at, n));
        at += n;
    }
    return {};
}

std::string name_problem(std::string_view name) {
    const std::string tidy = tidy_name(name);
    if (const std::string refused = first_refused(tidy); !refused.empty()) {
        const auto b = static_cast<unsigned char>(refused[0]);
        if (b < 0x20 || b == 0x7F)
            return i18n::tr("name.has_control", "It has a control character, which a name cannot have.");
        if (refused == " ") return i18n::tr("name.has_space", "It has a space, which a name cannot have.");
        return i18n::tr("name.has", "It has “{character}”, which a name cannot have.", {{"character", refused}});
    }
    if (const size_t n = characters(tidy); n > kNameMost) {
        return i18n::trn("name.too_long", static_cast<long long>(n), "It has {n} character: {most} at most.",
                         "It has {n} characters: {most} at most.", {{"most", kNameMost}});
    }
    return {};
}

Settings parse(std::string_view text) {
    Settings settings;
    if (text.starts_with("\xEF\xBB\xBF")) text.remove_prefix(3); // a byte order mark from an editor
    while (!text.empty()) {
        const size_t end = std::min(text.find('\n'), text.size());
        const auto [key, value] = setting_of(text.substr(0, end));
        text.remove_prefix(std::min(end + 1, text.size()));
        // (The later line counts.)
        if (key == kNameKey) settings.player_name = std::string(value);
        else if (key == kLanguageKey) settings.language = std::string(value);
    }
    return settings;
}

Loaded load(const fs::path& file) {
    Loaded loaded;
    const std::string name = path_utf8(file);
    const auto unusable = [&](const std::string& why) {
        loaded.error = why;
        loaded.log.push_back("game settings: defaults (" + why + ")");
        return loaded;
    };
    cafe::host::io::Stat st{};
    if (cafe::host::io::stat(file, &st) != 0) {
        const int error = errno;
        if (error == ENOENT || error == ENOTDIR) {
            loaded.log.push_back("game settings: defaults (no " + name + ")");
            return loaded;
        }
        return unusable("cannot read " + name + ": " + std::strerror(error));
    }
    loaded.exists = true;
    // Never open a pipe or a device: that could wait forever.
    if (!S_ISREG(st.st_mode)) return unusable(name + " is not a file");
    if (static_cast<std::uint64_t>(st.st_size) > kMostBytes) return unusable(name + " is larger than 64 KiB");
    std::ifstream in(file, std::ios::binary);
    std::string text;
    try {
        if (in) text.assign(std::istreambuf_iterator<char>(in), {});
    } catch (const std::ios_base::failure& e) {
        return unusable("cannot read " + name + ": " + e.code().message());
    }
    if (!in.is_open() || in.bad()) {
        const int error = errno;
        return unusable("cannot read " + name + ": " + std::strerror(error));
    }
    loaded.text = std::move(text);
    loaded.settings = parse(loaded.text);
    loaded.log.push_back("game settings: player name " +
                         (loaded.settings.player_name.empty() ? std::string("the game's own")
                                                              : "\"" + loaded.settings.player_name + "\"") +
                         ", language " +
                         (loaded.settings.language.empty() ? std::string("none")
                                                           : "\"" + loaded.settings.language + "\"") +
                         " (from " + name + ")");
    return loaded;
}

// (The name: where its first line was, as the launcher has always written it.)
std::string with_name(std::string_view text, std::string_view name) {
    return with_setting(text, kNameKey, name, false);
}

bool save_name(const fs::path& file, std::string_view name, std::string* error) {
    const std::string tidy = tidy_name(name);
    return save_with(file, [&](std::string_view text) { return with_name(text, tidy); }, error);
}

// (The language: where the line that counts was.)
std::string with_language(std::string_view text, std::string_view code) {
    return with_setting(text, kLanguageKey, code, true);
}

bool save_language(const fs::path& file, std::string_view code, std::string* error) {
    return save_with(file, [&](std::string_view text) { return with_language(text, code); }, error);
}

} // namespace launcher::game_ini
