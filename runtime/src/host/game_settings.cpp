#include "host/game_settings.h"

#include "host/display_settings.h"
#include "host/file_io.h"

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>

namespace cafe::host::game {
namespace {

namespace fs = std::filesystem;

constexpr std::string_view kPlayerName = "player_name";
constexpr std::string_view kLanguage = "language";

// A hand-edited file is a few hundred bytes; anything much larger is not one.
constexpr uint64_t kMaxFileSize = 64 * 1024;

bool space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\v' || c == '\f'; }

std::string_view trim(std::string_view s) {
    while (!s.empty() && space(s.front())) s.remove_prefix(1);
    while (!s.empty() && space(s.back())) s.remove_suffix(1);
    return s;
}

// `#` starts a comment at the start of a line or after a space (a `#`
// inside a word is part of it).
std::string_view strip_comment(std::string_view line) {
    for (size_t i = 0; i < line.size(); ++i) {
        if (line[i] == '#' && (i == 0 || space(line[i - 1]))) return line.substr(0, i);
    }
    return line;
}

std::string in_quotes(std::string_view s) { return "\"" + std::string(s) + "\""; }

// The bytes of the UTF-8 sequence at `at`: 1 for a byte that does not
// start a whole one.
size_t sequence_length(std::string_view text, size_t at) {
    const auto lead = static_cast<unsigned char>(text[at]);
    const size_t length = lead >= 0xC2 && lead <= 0xDF ? 2 : lead >= 0xE0 && lead <= 0xEF ? 3
                          : lead >= 0xF0 && lead <= 0xF4                                  ? 4
                                                                                          : 1;
    if (length == 1 || at + length > text.size()) return 1;
    for (size_t k = 1; k < length; ++k) {
        if ((static_cast<unsigned char>(text[at + k]) & 0xC0) != 0x80) return 1;
    }
    return length;
}

} // namespace

std::string clean_name(std::string_view text) {
    text = trim(text);
    std::string name;
    for (size_t i = 0; i < text.size();) {
        const auto c = static_cast<unsigned char>(text[i]);
        if (c >= 0x20 && c <= 0x7E) {
            name += static_cast<char>(c);
            ++i;
        } else {
            name += '?';
            i += sequence_length(text, i);
        }
    }
    std::string_view kept = trim(name);
    kept = trim(kept.substr(0, std::min(kept.size(), kMaxNameLength)));
    return std::string(kept);
}

const Language* find_language(std::string_view code) {
    for (const Language& language : kLanguages) {
        if (code.size() == language.code.size() &&
            std::equal(code.begin(), code.end(), language.code.begin(), [](char a, char b) {
                return (a >= 'A' && a <= 'Z' ? static_cast<char>(a - 'A' + 'a') : a) == b;
            })) {
            return &language;
        }
    }
    return nullptr;
}

const Language& language_of(const Settings& settings) {
    const Language* language = find_language(settings.language);
    return language ? *language : kLanguages[0];
}

Parsed parse(std::string_view text) {
    Parsed parsed;
    // Of each key, the line that gave it (0: none) and its value.
    struct Given {
        std::string_view key;
        size_t line = 0;
        std::string_view value;
    } name{kPlayerName, 0, {}}, language{kLanguage, 0, {}};
    if (text.starts_with("\xEF\xBB\xBF")) text.remove_prefix(3); // a byte order mark from an editor
    size_t number = 0;
    while (!text.empty()) {
        ++number;
        const size_t end = std::min(text.find('\n'), text.size());
        const std::string_view line = trim(strip_comment(text.substr(0, end)));
        text.remove_prefix(std::min(end + 1, text.size()));
        if (line.empty()) continue;

        const size_t equals = line.find('=');
        if (equals == std::string_view::npos) {
            parsed.warnings.push_back({number, "not \"name = value\": " + in_quotes(line) + ", line ignored"});
            continue;
        }
        const std::string_view id = trim(line.substr(0, equals));
        Given* const g = id == kPlayerName ? &name : id == kLanguage ? &language : nullptr;
        if (!g) {
            parsed.warnings.push_back({number, "unknown setting " + in_quotes(id) + ", line ignored"});
            continue;
        }
        // The earlier line is the one left out.
        if (g->line != 0) {
            parsed.warnings.push_back({g->line, std::string(g->key) + ": given again on line " +
                                                    std::to_string(number) + ", line ignored"});
        }
        g->line = number;
        g->value = trim(line.substr(equals + 1));
    }
    parsed.settings.player_name = clean_name(name.value);
    if (parsed.settings.player_name != name.value) {
        parsed.warnings.push_back({name.line, std::string(kPlayerName) + ": " + in_quotes(name.value) +
                                                  " is shown as " + in_quotes(parsed.settings.player_name) +
                                                  " (at most " + std::to_string(kMaxNameLength) +
                                                  " characters of printable ASCII)"});
    }
    if (!language.value.empty()) {
        const Language* found = find_language(language.value);
        if (!found) {
            std::string codes;
            for (const Language& l : kLanguages) codes += (codes.empty() ? "" : ", ") + std::string(l.code);
            parsed.warnings.push_back({language.line, std::string(kLanguage) + ": the game has no language " +
                                                          in_quotes(language.value) + " (" + codes +
                                                          "), English shown"});
        } else if (found != &kLanguages[0]) {
            parsed.settings.language = std::string(found->code);
        }
    }
    std::stable_sort(parsed.warnings.begin(), parsed.warnings.end(),
                     [](const Warning& a, const Warning& b) { return a.line < b.line; });
    return parsed;
}

fs::path file_path() { return display::file_path().parent_path() / "game.ini"; }

Loaded load(const fs::path& file) {
    Loaded loaded;
    const std::string name = file.string();
    const auto unusable = [&](const std::string& why) {
        loaded.error = why;
        loaded.log.push_back("game: defaults (" + why + ")");
        return loaded;
    };
    host::io::Stat st{};
    if (host::io::stat(file, &st) != 0) {
        const int error = errno;
        if (error == ENOENT || error == ENOTDIR) {
            loaded.log.push_back("game: defaults (no " + name + ")");
            return loaded;
        }
        return unusable("cannot read " + name + ": " + std::strerror(error));
    }
    // Never open a pipe or a device: that could wait forever.
    if (!S_ISREG(st.st_mode)) return unusable(name + " is not a file");
    if (static_cast<uint64_t>(st.st_size) > kMaxFileSize) return unusable(name + " is larger than 64 KiB");
    std::ifstream in(file, std::ios::binary);
    std::string text;
    try {
        if (in) text.assign(std::istreambuf_iterator<char>(in), {});
    } catch (const std::ios_base::failure& e) {
        // (libstdc++ throws on a failed read whatever the exception mask.)
        return unusable("cannot read " + name + ": " + e.code().message());
    }
    if (!in.is_open() || in.bad()) {
        const int error = errno;
        return unusable("cannot read " + name + ": " + std::strerror(error));
    }
    const Parsed parsed = parse(text);
    for (const Warning& warning : parsed.warnings) {
        loaded.log.push_back("game: " + name + ":" + std::to_string(warning.line) + ": " + warning.text);
    }
    loaded.settings = parsed.settings;
    loaded.log.push_back("game: player name " +
                         (parsed.settings.player_name.empty() ? std::string("the game's own")
                                                              : in_quotes(parsed.settings.player_name)) +
                         ", language " + std::string(language_of(parsed.settings).name) + " (from " + name + ")");
    return loaded;
}

} // namespace cafe::host::game
