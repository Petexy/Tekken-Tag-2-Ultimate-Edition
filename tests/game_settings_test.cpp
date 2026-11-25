// The game settings from game.ini (runtime/src/host/game_settings.h): the
// player's name as the game keeps it (its limits), what a file says and
// what is left out, where the file is and what loading it logs. Files go to
// a scratch folder.

#include "host/display_settings.h"
#include "host/game_settings.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <random>
#include <string>
#include <vector>

namespace {

namespace fs = std::filesystem;
namespace game = cafe::host::game;

int g_failures = 0;

void check(bool ok, const std::string& what) {
    if (!ok) {
        std::printf("FAIL %s\n", what.c_str());
        ++g_failures;
    }
}

bool has_warning(const game::Parsed& parsed, size_t line, const std::string& part) {
    for (const game::Warning& w : parsed.warnings) {
        if (w.line == line && w.text.find(part) != std::string::npos) return true;
    }
    return false;
}

std::string joined(const std::vector<std::string>& lines) {
    std::string all;
    for (const std::string& line : lines) all += line + "\n";
    return all;
}

void write(const fs::path& file, const std::string& text) {
    std::ofstream out(file, std::ios::binary | std::ios::trunc);
    out << text;
}

// What the title may be given: at most kMaxNameLength bytes of printable
// ASCII, no space at either end.
bool keepable(const std::string& name) {
    if (name.size() > game::kMaxNameLength) return false;
    for (const char c : name) {
        if (c < 0x20 || c > 0x7E) return false;
    }
    return name.empty() || (name.front() != ' ' && name.back() != ' ');
}

void test_clean_name() {
    const struct {
        std::string text, name, what;
    } cases[] = {
        {"Zorbax", "Zorbax", "a plain name"},
        {"  Zorbax\t", "Zorbax", "spaces at both ends"},
        {"Iron Fist 7", "Iron Fist 7", "spaces inside"},
        {"A#B", "A#B", "a # inside a word"},
        {"~!@$%^&*()_+{}|:", "~!@$%^&*()_+{}|:", "punctuation, 16 characters"},
        {"ABCDEFGHIJKLMNOP", "ABCDEFGHIJKLMNOP", "16 characters"},
        {"ABCDEFGHIJKLMNOPQ", "ABCDEFGHIJKLMNOP", "17 characters: cut to 16"},
        {"ABCDEFGHIJKLMNO PQ", "ABCDEFGHIJKLMNO", "cut after a space: no space at the end"},
        {"   ABCDEFGHIJKLMNOPQRSTUVWXYZ", "ABCDEFGHIJKLMNOP", "spaces before a long name do not count"},
        {"Zo\xC3\xAB", "Zo?", "a letter of two bytes"},
        {"\xE6\x9D\xB1\xE4\xBA\xAC", "??", "letters of three bytes"},
        {"go \xF0\x9F\xA5\x8A", "go ?", "a character of four bytes"},
        {"a\tb", "a?b", "a tab inside"},
        {"a\x7F" "b", "a?b", "DEL"},
        {std::string("a\0b", 3), "a?b", "a zero byte"},
        {"\xFF" "x", "?x", "a byte that is no UTF-8"},
        {"\x80" "x", "?x", "a continuation byte alone"},
        {"x\xC3", "x?", "a sequence cut at the end"},
        {"\xE6\x9D" "x", "??x", "a sequence cut short: each byte refused"},
        {"\xC0\xAF", "??", "an overlong slash: two bytes, each refused"},
        {"", "", "empty"},
        {"     ", "", "only spaces"},
        {std::string(40, '\xE2'), std::string(16, '?'), "many bad bytes: 16 marks"},
    };
    for (const auto& c : cases) {
        const std::string name = game::clean_name(c.text);
        check(name == c.name, c.what + ": \"" + name + "\"");
        check(keepable(name), c.what + ": keepable");
    }
    std::string emoji;
    for (int i = 0; i < 30; ++i) emoji += "\xF0\x9F\xA5\x8A";
    check(game::clean_name(emoji) == std::string(16, '?'), "30 characters of four bytes: 16 marks");

    // Any bytes at all: what comes out may be given to the title.
    std::mt19937 random(1598);
    for (int round = 0; round < 20000; ++round) {
        std::string text(random() % 64, '\0');
        for (char& c : text) c = static_cast<char>(random() % 256);
        const std::string name = game::clean_name(text);
        if (!keepable(name)) {
            check(false, "random bytes, round " + std::to_string(round) + ": \"" + name + "\"");
            break;
        }
    }
}

void test_parse() {
    const game::Parsed plain = game::parse("player_name = Zorbax\n");
    check(plain.settings.player_name == "Zorbax" && plain.warnings.empty(), "one line");

    for (const char* empty : {"", "\n\n", "# nothing\n   \n\t# else\n", "player_name =\n", "player_name = # none\n",
                              "player_name =    \t\n"}) {
        const game::Parsed nothing = game::parse(empty);
        check(nothing.settings == game::Settings{} && nothing.warnings.empty(),
              std::string("no name: the game's own (") + empty + ")");
    }
    const game::Parsed windows = game::parse("\xEF\xBB\xBF"
                                             "# written by hand\r\n"
                                             "\r\n"
                                             "player_name = Iron Fist # mine\r\n");
    check(windows.settings.player_name == "Iron Fist" && windows.warnings.empty(),
          "byte order mark, CRLF and a comment: \"" + windows.settings.player_name + "\"");
    check(game::parse("player_name=Zorbax").settings.player_name == "Zorbax", "no spaces, no newline at the end");
    check(game::parse("player_name = A#B #C\n").settings.player_name == "A#B", "# inside a word is no comment");
    check(game::parse("player_name = a = b\n").settings.player_name == "a = b", "an = in the value");

    const game::Parsed twice = game::parse("player_name = First\nplayer_name = Second\n");
    check(twice.settings.player_name == "Second", "the later line counts");
    check(twice.warnings.size() == 1 && has_warning(twice, 1, "player_name: given again on line 2, line ignored"),
          "the earlier line is told");
    const game::Parsed cleared = game::parse("player_name = First\nplayer_name =\n");
    check(cleared.settings.player_name.empty(), "a later empty line: the game's own");

    const game::Parsed others = game::parse("input_delay = yes\n"     // 1: display.ini's, not this file's
                                            "Player_Name = Upper\n"   // 2: keys are exact
                                            "player_name Zorbax\n"    // 3: no =
                                            "= Zorbax\n"              // 4: no key
                                            "player_name = Kept\n");  // 5
    check(others.settings.player_name == "Kept", "other lines leave the name alone");
    check(has_warning(others, 1, "unknown setting \"input_delay\", line ignored") &&
              has_warning(others, 2, "unknown setting \"Player_Name\"") &&
              has_warning(others, 3, "not \"name = value\": \"player_name Zorbax\"") &&
              has_warning(others, 4, "unknown setting \"\"") && others.warnings.size() == 4,
          "a warning for each line left out");

    const game::Parsed changed = game::parse("\n\nplayer_name = Zo\xC3\xAB the very long name\n");
    check(changed.settings.player_name == "Zo? the very lon", "cleaned: \"" + changed.settings.player_name + "\"");
    check(changed.warnings.size() == 1 && has_warning(changed, 3, "is shown as \"Zo? the very lon\" (at most 16 "
                                                                  "characters of printable ASCII)"),
          "a cleaned name is told on its line");
}

void test_language() {
    check(std::size(game::kLanguages) > 1 && game::kLanguages[0].code == "en" && game::kLanguages[0].wiiu == 1,
          "English first, the console's language 1");
    for (const game::Language& l : game::kLanguages) {
        const std::string code(l.code);
        check(game::find_language(code) == &l, "found: " + code);
        std::string upper = code;
        for (char& c : upper) c = static_cast<char>(c - 'a' + 'A');
        check(game::find_language(upper) == &l, "found in capitals: " + upper);
        const game::Parsed parsed = game::parse("language = " + upper + "\n");
        check(parsed.warnings.empty() && parsed.settings.language == (l.code == "en" ? "" : code) &&
                  game::language_of(parsed.settings).code == l.code,
              "language = " + upper + ": \"" + parsed.settings.language + "\"");
        for (const game::Language& other : game::kLanguages) {
            check(&other == &l || (other.code != l.code && other.wiiu != l.wiiu), "one of each: " + code);
        }
    }
    for (const char* none : {"", " fr", "fra", "f", "french", "nl", "pt", "jp"}) {
        check(game::find_language(none) == nullptr, std::string("no language \"") + none + "\"");
    }

    for (const char* empty : {"", "language =\n", "language = # none\n", "player_name = Zorbax\n"}) {
        const game::Parsed parsed = game::parse(empty);
        check(parsed.settings.language.empty() && parsed.warnings.empty() &&
                  game::language_of(parsed.settings).code == "en",
              std::string("English: \"") + empty + "\"");
    }
    const game::Parsed both = game::parse("player_name = Zorbax\r\nlanguage = fr # French\r\n");
    check(both.settings.player_name == "Zorbax" && both.settings.language == "fr" && both.warnings.empty(),
          "a name and a language");
    const game::Parsed twice = game::parse("language = fr\nplayer_name = A\nlanguage = it\n");
    check(twice.settings.language == "it" && twice.warnings.size() == 1 &&
              has_warning(twice, 1, "language: given again on line 3, line ignored"),
          "the later language counts");
    const game::Parsed back = game::parse("language = fr\nlanguage =\n");
    check(back.settings.language.empty(), "a later empty line: English");
    const game::Parsed unknown = game::parse("\nlanguage = Klingon\n");
    check(unknown.settings.language.empty() && unknown.warnings.size() == 1 &&
              has_warning(unknown, 2, "language: the game has no language \"Klingon\" (en, fr, ") &&
              has_warning(unknown, 2, "), English shown"),
          "an unknown language: English, told on its line");
}

void test_path(const fs::path& scratch) {
    const char* old_home = std::getenv("HOME");
    const char* old_config = std::getenv("XDG_CONFIG_HOME");
    const std::string home = old_home ? old_home : "", config = old_config ? old_config : "";

    setenv("HOME", (scratch / "home").c_str(), 1);
    setenv("XDG_CONFIG_HOME", (scratch / "config").c_str(), 1);
    check(game::file_path() == scratch / "config/ttt2/game.ini", "XDG_CONFIG_HOME: " + game::file_path().string());
    setenv("XDG_CONFIG_HOME", "relative/config", 1);
    check(game::file_path() == scratch / "home/.config/ttt2/game.ini", "a relative XDG_CONFIG_HOME is ignored");
    unsetenv("XDG_CONFIG_HOME");
    check(game::file_path() == scratch / "home/.config/ttt2/game.ini", "no XDG_CONFIG_HOME");
    check(game::file_path().parent_path() == cafe::host::display::file_path().parent_path(),
          "the folder of display.ini");

    if (old_home) setenv("HOME", home.c_str(), 1);
    if (old_config) setenv("XDG_CONFIG_HOME", config.c_str(), 1);
}

void test_load(const fs::path& scratch) {
    const fs::path file = scratch / "game.ini";
    const std::string name = file.string();
    fs::remove(file);
    const game::Loaded missing = game::load(file);
    check(missing.settings == game::Settings{} && missing.error.empty() &&
              missing.log == std::vector<std::string>{"game: defaults (no " + name + ")"},
          "missing file: " + joined(missing.log));

    write(file, "# the launcher's\nplayer_name = Zorbax\nfuture_setting = 3\n");
    const game::Loaded loaded = game::load(file);
    check(loaded.settings.player_name == "Zorbax" && loaded.error.empty(),
          "file: \"" + loaded.settings.player_name + "\"");
    const std::vector<std::string> log{"game: " + name + ":3: unknown setting \"future_setting\", line ignored",
                                       "game: player name \"Zorbax\", language English (from " + name + ")"};
    check(loaded.log == log, "file: log " + joined(loaded.log));

    write(file, "language = de\n");
    const game::Loaded german = game::load(file);
    check(german.settings.language == "de" &&
              german.log == std::vector<std::string>{"game: player name the game's own, language German (from " +
                                                     name + ")"},
          "a language: " + joined(german.log));

    write(file, "");
    const game::Loaded empty = game::load(file);
    check(empty.settings == game::Settings{} && empty.error.empty() &&
              empty.log == std::vector<std::string>{"game: player name the game's own, language English (from " + name + ")"},
          "empty file: " + joined(empty.log));

    const auto refused = [](const game::Loaded& l, const std::string& why, const std::string& what) {
        check(l.settings == game::Settings{} && l.error.find(why) != std::string::npos &&
                  l.log == std::vector<std::string>{"game: defaults (" + l.error + ")"},
              what + ": error \"" + l.error + "\", log " + joined(l.log));
    };
    const fs::path folder = scratch / "folder.ini";
    fs::create_directories(folder);
    refused(game::load(folder), folder.string() + " is not a file", "a folder");
    const std::string first = "player_name = Big\n#";
    write(file, first + std::string(64 * 1024 - first.size(), '#'));
    check(game::load(file).settings.player_name == "Big", "a file of 64 KiB is read");
    write(file, first + std::string(64 * 1024 + 1 - first.size(), '#'));
    refused(game::load(file), name + " is larger than 64 KiB", "a file over 64 KiB");
}

} // namespace

int main(int argc, char** argv) {
    // The scratch folder: the build tree's, never the player's config.
    const fs::path scratch = fs::absolute(argc > 1 ? fs::path(argv[1]) : fs::path("game_settings_test.d"));
    fs::remove_all(scratch);
    fs::create_directories(scratch);

    test_clean_name();
    test_parse();
    test_language();
    test_path(scratch);
    test_load(scratch);

    fs::remove_all(scratch);
    if (g_failures == 0) std::printf("game_settings_test: all passed\n");
    return g_failures == 0 ? 0 : 1;
}
