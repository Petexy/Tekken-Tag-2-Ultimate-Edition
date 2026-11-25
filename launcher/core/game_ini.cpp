// game.ini (see game_ini.h).

#include "game_ini.h"
#include "utf8_path.h"

#include "files.h"
#include "host/file_io.h"

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

const char* const kHeader =
    "# Tekken Tag Tournament 2's game settings, written by the launcher's Settings.\n"
    "# The game reads them when it starts.\n"
    "# player_name: the name the game shows for you (without it, its own: Player in English).\n";

} // namespace

fs::path beside(const fs::path& display_file) { return display_file.parent_path() / "game.ini"; }

bool name_character(char32_t c) { return c >= 0x20 && c <= 0x7E && c != '#'; }

std::string name_rule() {
    return "Up to " + std::to_string(kNameMost) +
           " characters: the letters A to Z, digits, spaces and the punctuation of an English keyboard but #.";
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
        const std::string shown = b < 0x20 || b == 0x7F ? std::string("a control character")
                                  : refused == " "      ? std::string("a space")
                                                        : "“" + refused + "”";
        return "It has " + shown + ", which a name cannot have.";
    }
    if (const size_t n = characters(tidy); n > kNameMost) {
        return "It has " + std::to_string(n) + " characters: " + std::to_string(kNameMost) + " at most.";
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
                         " (from " + name + ")");
    return loaded;
}

std::string with_name(std::string_view text, std::string_view name) {
    const std::string line = std::string(kNameKey) + " = " + std::string(name);
    // (A file with nothing in it: a new one.)
    std::string_view rest = text.starts_with("\xEF\xBB\xBF") ? text.substr(3) : text;
    while (!rest.empty() && (space(rest.front()) || rest.front() == '\n')) rest.remove_prefix(1);
    if (rest.empty())
        return name.empty() ? std::string(kHeader) : kHeader + line + "\n";
    std::string out;
    bool written = false;
    while (!text.empty()) {
        const size_t end = text.find('\n');
        const std::string_view whole = text.substr(0, end == std::string_view::npos ? text.size() : end + 1);
        text.remove_prefix(whole.size());
        std::string_view body = whole;
        if (body.ends_with('\n')) body.remove_suffix(1);
        const bool crlf = body.ends_with('\r');
        const auto [key, value] = setting_of(body.starts_with("\xEF\xBB\xBF") ? body.substr(3) : body);
        (void)value;
        if (key != kNameKey) {
            out += whole;
            continue;
        }
        // (The first line of the key takes the new value; a later one would win over it: left out.)
        if (written || name.empty()) continue;
        written = true;
        if (body.starts_with("\xEF\xBB\xBF")) out += "\xEF\xBB\xBF";
        out += line + (crlf ? "\r\n" : "\n");
    }
    if (!written && !name.empty()) {
        if (!out.empty() && out.back() != '\n') out += '\n';
        out += line + "\n";
    }
    return out;
}

bool save_name(const fs::path& file, std::string_view name, std::string* error) {
    const Loaded now = load(file);
    // (A file that cannot be read is written anew: what it had cannot be kept.)
    return replace_file(file, with_name(now.error.empty() ? std::string_view(now.text) : std::string_view(),
                                        tidy_name(name)),
                        error);
}

} // namespace launcher::game_ini
