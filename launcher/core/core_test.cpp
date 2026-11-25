// The launcher's logic without its window: the JSON reader, the progress
// lines, the install's state and folders, the PC checks' parsing, the test
// actions, the display settings' file, uninstalling, and the launcher's own
// updates (in a folder of its own, made and deleted here).

#include "display.h"
#include "game_ini.h"
#include "host/game_settings.h"
#include "json.h"
#include "paths.h"
#include "protocol.h"
#include "release.h"
#include "status.h"
#include "system.h"
#include "test_actions.h"
#include "uninstall.h"

#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <thread>

namespace {

using namespace launcher;

int g_failures = 0;

void check(bool ok, const std::string& what) {
    if (!ok) {
        std::printf("FAIL %s\n", what.c_str());
        ++g_failures;
    }
}

void write(const fs::path& file, const std::string& text) {
    std::error_code ec;
    fs::create_directories(file.parent_path(), ec);
    std::ofstream(file) << text;
}

bool there(const fs::path& path) {
    std::error_code ec;
    return fs::exists(fs::symlink_status(path, ec));
}

// A program that runs until it is killed, made at `program` as the game's
// program would be (a copy of sleep: a script would show as its shell in
// /proc/<pid>/exe). Its pid once it runs from there, or 0.
pid_t run_program(const fs::path& program) {
    std::error_code ec;
    fs::create_directories(program.parent_path(), ec);
    fs::copy_file("/bin/sleep", program, fs::copy_options::overwrite_existing, ec);
    fs::permissions(program, fs::perms::owner_all, ec);
    if (ec) return 0;
    const pid_t pid = ::fork();
    if (pid == 0) {
        // (argv[0] "sleep": a multi-call coreutils picks its tool by it.)
        ::execl(program.c_str(), "sleep", "60", static_cast<char*>(nullptr));
        ::_exit(127);
    }
    const std::string exe = "/proc/" + std::to_string(pid) + "/exe";
    for (int i = 0; i < 200; ++i) {
        if (fs::read_symlink(exe, ec) == program) return pid;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    return pid;
}

void stop_program(pid_t pid) {
    if (pid <= 0) return;
    ::kill(pid, SIGKILL);
    ::waitpid(pid, nullptr, 0);
}

void test_json() {
    const auto doc = json::parse(R"( {"a": [1, -2.5e3, true, false, null], "s": "x\"\\\/\b\f\n\r\t\u00e9\ud83d\ude00",
                                     "o": {"k": "v"}, "a2": [], "o2": {}, "k": 1, "k": 2} )");
    check(doc.has_value(), "json: a valid document");
    if (!doc) return;
    const json::Value& d = *doc;
    check(d["a"].items().size() == 5, "json: array items");
    check(d["a"][0].number() == 1 && d["a"][1].number() == -2500, "json: numbers");
    check(d["a"][2].boolean() && !d["a"][3].boolean(true) && d["a"][4].is_null(), "json: literals");
    check(d["s"].string() == "x\"\\/\b\f\n\r\t\xC3\xA9\xF0\x9F\x98\x80", "json: escapes and UTF-16 pairs");
    check(d["o"]["k"].string() == "v", "json: nested object");
    check(d["a2"].is_array() && d["a2"].items().empty() && d["o2"].is_object(), "json: empty containers");
    check(d["k"].number() == 2, "json: the last of repeated members");
    check(d["missing"]["deeper"][3].string("fallback") == "fallback", "json: missing members give the fallback");
    check(d["a"].string("x") == "x" && d["s"].number(7) == 7 && d["s"].items().empty(), "json: wrong types too");
    check(json::parse("\"\\ud800\"")->string() == "\xEF\xBF\xBD", "json: a lone surrogate");
    check(json::parse("0")->number() == 0 && json::parse("-0.5")->number() == -0.5, "json: plain numbers");

    for (const char* bad : {"", "{", "[1,]", "{\"a\":1,}", "{\"a\" 1}", "\"open", "\"a\tb\"", "01", "1.", "1e",
                            "-", "nul", "[1] 2", "{1: 2}", "\"\\x\"", "\"\\u12G4\"", "+1", ".5", "1e999"}) {
        std::string error;
        check(!json::parse(bad, &error) && !error.empty(), std::string("json: rejects ") + bad);
    }
    check(!json::parse(std::string(100, '[') + std::string(100, ']')), "json: nesting too deep");
    check(json::parse(std::string(60, '[') + std::string(60, ']')).has_value(), "json: nesting within the limit");
}

void test_status() {
    const char* text = R"({"python": {"version": "3.14.0", "numpy": true, "pillow": false},
        "tools": {"gamescope": "/usr/bin/gamescope", "pactl": null, "helper": "prebuilt"},
        "steam": {"installed": true, "running": false},
        "tekken7": {"found": true, "path": "/s/steamapps/common/TEKKEN 7", "error": null},
        "packs_folder": "/d/ttt2/characters", "future": {"x": 1},
        "movesets": {"folder": "/m", "heihachi": false}, "game": {"path": null, "error": "not a game"},
        "fighters": [{"name": "kazumi", "display": "Kazumi Mishima", "dlc": null, "installed": true,
                      "moveset_saved": true, "outfits": 9, "outfits_added": true},
                     {"name": "eliza", "display": "Eliza", "dlc": 592370, "installed": false, "moveset_saved": false},
                     {"name": "chloe", "display": "Lucky Chloe", "dlc": null, "installed": true, "outdated": true,
                      "update": true, "moveset_saved": true},
                     {"name": "geese", "display": "Geese Howard", "dlc": 592373, "installed": true,
                      "outdated": false, "update": true, "moveset_saved": false, "needs_game": false},
                     {"name": "noctis", "display": "Noctis", "dlc": 592374, "installed": false, "outdated": true},
                     {"name": "josie", "display": "Josie Rizal", "dlc": null, "installed": true, "outdated": false,
                      "newer": true},
                     {"name": "akuma", "display": "Akuma", "dlc": null, "installed": false, "newer": true},
                     {"display": "nameless"}]})";
    std::string error;
    const auto s = parse_status(text, &error);
    check(s.has_value(), "status: parses (" + error + ")");
    if (!s) return;
    check(s->python_version == "3.14.0" && s->numpy && !s->pillow, "status: python");
    check(!s->packages_gettable && s->packages_size == 0, "status: no \"packages\": not gettable");
    check(s->gamescope == "/usr/bin/gamescope" && s->pactl.empty() && s->helper == "prebuilt", "status: tools");
    check(s->steam_installed && !s->steam_running, "status: steam");
    check(s->tekken7_usable() && s->tekken7_path == "/s/steamapps/common/TEKKEN 7", "status: tekken 7");
    check(s->packs_folder == "/d/ttt2/characters", "status: packs folder");
    check(!s->heihachi_saved && s->game_error == "not a game", "status: heihachi and the game");
    check(s->fighters.size() == 7, "status: fighters without a name are left out");
    if (s->fighters.size() == 7) {
        const Fighter &josie = s->fighters[5], &akuma = s->fighters[6];
        check(josie.installed && josie.newer && !josie.outdated && !josie.added(), "status: a newer pack is not added");
        check(!akuma.installed && !akuma.newer && !akuma.added(), "status: newer without a pack is not");
        check(!s->fighters[0].newer && !s->fighters[2].newer, "status: no \"newer\": not newer");
        const Fighter &kazumi = s->fighters[0], &eliza = s->fighters[1], &chloe = s->fighters[2],
                      &geese = s->fighters[3], &noctis = s->fighters[4];
        check(kazumi.name == "kazumi" && kazumi.dlc == 0 && kazumi.installed, "status: kazumi");
        check(!kazumi.outdated && kazumi.added(), "status: no \"outdated\": a pack the game loads");
        check(eliza.dlc == 592370 && !eliza.installed && !eliza.outdated && !eliza.added(), "status: eliza");
        check(chloe.installed && chloe.outdated && !chloe.added(), "status: an outdated pack is not in the game");
        check(geese.installed && !geese.outdated && geese.added(), "status: a current pack");
        check(geese.update && !kazumi.update, "status: a pack to update is still added");
        check(!chloe.update, "status: an outdated pack is to add again, not to update");
        check(!noctis.installed && !noctis.outdated && !noctis.added(), "status: outdated without a pack is not");
        check(kazumi.outfits == 9 && kazumi.outfits_added, "status: outfits");
        check(eliza.outfits == 0 && !eliza.outfits_added && !chloe.outfits_added, "status: no \"outfits\": none");
        check(!geese.needs_game, "status: a pack whose shared pictures need no game");
        check(kazumi.needs_game && !eliza.needs_game && !chloe.needs_game,
              "status: no \"needs_game\": an added pack needs its game");
    }
    const auto missing =
        parse_status(R"({"tekken7": {"found": false, "path": null, "error": "Steam is not installed"}})");
    check(missing && !missing->tekken7_usable() && missing->tekken7_error == "Steam is not installed",
          "status: tekken 7 missing");
    check(missing && missing->heihachi_saved && missing->game_error.empty(), "status: optional fields' defaults");
    check(missing && !missing->tekken7_readable && !missing->tekken8_found && !missing->tekken8_usable() &&
              !missing->tekken8_build_known && missing->tekken8_helper.empty() && missing->cc.empty(),
          "status: an older importer's, without Tekken 8");
    check(s->fighters[0].of(kTekken7) && !s->fighters[0].stand_in, "status: no \"game\": a Tekken 7 fighter");
    const auto older = parse_status(R"({"tekken7": {"found": true, "path": "/t", "error": null}})");
    check(older && older->tekken7_readable && older->readable(kTekken7),
          "status: no \"readable\": a usable Tekken 7 is readable");

    // Both games: Tekken 7 that cannot run but whose files are there, and
    // Tekken 8 with a stand-in Reina.
    const auto both = parse_status(R"({
        "tools": {"gamescope": "/usr/bin/gamescope", "pactl": "/usr/bin/pactl", "helper": "prebuilt",
                  "tekken8_helper": "mingw", "cc": "/usr/bin/gcc"},
        "steam": {"installed": true, "running": true},
        "tekken7": {"found": true, "path": "/l/TEKKEN 7", "error": "Tekken 7 has not run with Proton yet",
                    "readable": true},
        "tekken8": {"found": true, "path": "/l/TEKKEN 8", "error": null, "run_error": null, "build_known": false},
        "fighters": [{"name": "kazumi", "display": "Kazumi Mishima", "dlc": null, "installed": true,
                      "moveset_saved": true},
                     {"name": "reina", "display": "Reina", "dlc": null, "installed": true, "outdated": false,
                      "newer": false, "update": true, "moveset_saved": false, "stand_in": true, "game": "tekken8"},
                     {"name": "later", "display": "Later", "dlc": 2732280, "installed": false, "update": false,
                      "moveset_saved": false, "stand_in": true, "game": "tekken8"}]})");
    check(both && both->tekken8_helper == "mingw" && both->helper == "prebuilt" && both->cc == "/usr/bin/gcc",
          "status both: each game's helper, the C compiler");
    check(both && !both->tekken7_usable() && both->tekken7_readable && both->readable(kTekken7) &&
              both->found(kTekken7),
          "status both: Tekken 7 readable, not usable");
    check(both && both->tekken8_usable() && both->readable(kTekken8) && both->tekken8_path == "/l/TEKKEN 8" &&
              both->tekken8_build_known == false && both->tekken8_run_error.empty(),
          "status both: Tekken 8");
    check(both && both->fighters.size() == 3, "status both: fighters");
    if (both && both->fighters.size() == 3) {
        const Fighter &kazumi = both->fighters[0], &reina = both->fighters[1], &later = both->fighters[2];
        check(kazumi.of(kTekken7) && !kazumi.of(kTekken8) && !kazumi.stand_in, "status both: kazumi");
        check(reina.of(kTekken8) && reina.added() && reina.stand_in && reina.update && !reina.moveset_saved &&
                  reina.dlc == 0,
              "status both: a stand-in Reina to update");
        check(later.of(kTekken8) && later.dlc == 2732280 && !later.stand_in && !later.added(),
              "status both: a Tekken 8 DLC fighter, a stand-in only with a pack");
    }

    // Neither game.
    const auto neither = parse_status(R"({"steam": {"installed": false, "running": false},
        "tekken7": {"found": false, "path": null, "error": "Steam is not installed", "readable": false},
        "tekken8": {"found": false, "path": null, "error": "Tekken 8 is not installed in any Steam library",
                    "run_error": null, "build_known": null},
        "fighters": [{"name": "reina", "display": "Reina", "installed": false, "game": "tekken8"}]})");
    check(neither && !neither->tekken7_usable() && !neither->tekken7_readable && !neither->found(kTekken7) &&
              !neither->tekken8_usable() && !neither->readable(kTekken8) && !neither->found(kTekken8) &&
              !neither->tekken8_build_known &&
              neither->tekken8_error == "Tekken 8 is not installed in any Steam library",
          "status neither: no game");
    check(neither && neither->fighters.size() == 1 && !neither->fighters[0].added(), "status neither: fighters");

    // Tekken 8 alone, a build the helper knows, never run with Proton.
    const auto only8 = parse_status(R"({
        "tekken7": {"found": false, "path": null, "error": "Tekken 7 is not installed in any Steam library",
                    "readable": false},
        "tekken8": {"found": true, "path": "/l/TEKKEN 8", "error": null, "build_known": true,
                    "run_error": "Tekken 8 has not run with Proton yet: start it once from Steam"}})");
    check(only8 && !only8->tekken7_readable && only8->tekken8_usable() && only8->tekken8_build_known == true &&
              only8->tekken8_run_error == "Tekken 8 has not run with Proton yet: start it once from Steam",
          "status Tekken 8 only");
    const auto gettable = parse_status(R"({"python": {"numpy": false, "pillow": false,
        "packages": {"folder": "/d/ttt2/python/cp313", "size": 23864284, "error": null}}})");
    check(gettable && gettable->packages_gettable && gettable->packages_size == 23864284 &&
              gettable->packages_error.empty(),
          "status: numpy and Pillow the launcher can get");
    const auto refused = parse_status(R"({"python": {"packages": {"folder": "/d", "size": 0,
        "error": "the launcher gets numpy and Pillow for Python 3.10, 3.11 only, not 3.9"}}})");
    check(refused && !refused->packages_gettable && refused->packages_error.ends_with("not 3.9"),
          "status: numpy and Pillow the launcher cannot get, and why");
    check(!parse_status("[1]") && !parse_status("not json"), "status: not an object");

    const Ownership owned = parse_owned(R"({"owned": {"eliza": true, "geese": false}})");
    check(owned.error.empty() && owned.owned.size() == 2 && owned.owned.at("eliza") && !owned.owned.at("geese"),
          "owned: answer");
    check(parse_owned(R"({"error": "Steam is not running"})").error == "Steam is not running", "owned: error");
    check(!parse_owned("garbage").error.empty() && !parse_owned("{}").error.empty(), "owned: malformed");
    // Tekken 8 answered, Tekken 7 could not be asked: its fighters left out, and why.
    const Ownership partly = parse_owned(R"({"owned": {"clive": true, "miary_zo": false},
        "errors": {"tekken7": "Tekken 7 is running: close it first"}})");
    check(partly.error.empty() && partly.owned.size() == 2 && partly.owned.at("clive") &&
              partly.errors.at("tekken7") == "Tekken 7 is running: close it first" && partly.errors.size() == 1,
          "owned: one game not asked");
    const Ownership both_failed = parse_owned(R"({"error": "Tekken 7 is running: close it first",
        "errors": {"tekken7": "Tekken 7 is running: close it first", "tekken8": "Tekken 8 is running: close it first"}})");
    check(both_failed.error == "Tekken 7 is running: close it first" && both_failed.owned.empty() &&
              both_failed.errors.at("tekken8") == "Tekken 8 is running: close it first",
          "owned: neither game asked");
    const Ownership again = parse_owned(ownership_json({{"clive", true}, {"eliza", false}}));
    check(again.error.empty() && again.owned == std::map<std::string, bool>{{"clive", true}, {"eliza", false}} &&
              again.errors.empty() && parse_owned(ownership_json({})).owned.empty(),
          "owned: kept as JSON");

    const MainNews news = parse_main_news(R"({"ahead": 3, "head": "f434935", "page": "https://github.com/x/compare",
        "changes": ["Newest", "Older"], "fighters": ["kazumi"], "new": [{"name": "jin", "display": "Jin Kazama"}]})");
    check(news.error.empty() && news.ahead == 3 && news.head == "f434935" && news.changes.size() == 2 &&
              news.changes[0] == "Newest" && news.fighters == std::vector<std::string>{"kazumi"} &&
              news.fresh.size() == 1 && news.fresh[0].second == "Jin Kazama",
          "main news: answer");
    check(parse_main_news(R"({"error": "GitHub does not know commit abc"})").error == "GitHub does not know commit abc",
          "main news: error");
    check(!parse_main_news("[]").error.empty() && parse_main_news("{}").ahead == 0, "main news: malformed or empty");
    check(build_commit("0.4.0-1cab8c68f39b") == "1cab8c68f39b" && build_commit("0.4.0").empty() &&
              build_commit("0.4.0-dirty").empty() && build_commit("").empty(),
          "build commit");
}

void test_saved_ownership(const fs::path& root) {
    const fs::path file = root / "cache/ttt2/dlc-owned.json";
    check(!saved_ownership(file), "saved owned: none at first");
    check(!save_ownership(file, R"({"error": "Steam is not running"})") && !there(file), "saved owned: not an error");
    check(save_ownership(file, R"({"owned": {"eliza": true, "geese": false}})"), "saved owned: saved");
    const auto saved = saved_ownership(file);
    check(saved && saved->owned.size() == 2 && saved->owned.at("eliza") && !saved->owned.at("geese"),
          "saved owned: read back");
    check(!there(fs::path(file.string() + ".part")), "saved owned: no part file left");
    write(file, "{\"owned\": ");
    check(!saved_ownership(file), "saved owned: a broken file is none");
}

void test_protocol() {
    Line l = parse_line("@step compile Compiling the game program\n");
    check(l.kind == Line::Kind::kStep && l.word == "compile" && l.text == "Compiling the game program", "line: step");
    l = parse_line("@progress 412 1203");
    check(l.kind == Line::Kind::kProgress && l.done == 412 && l.total == 1203, "line: progress");
    check(parse_line("@progress 4x 10").kind == Line::Kind::kText, "line: bad progress is text");
    l = parse_line("@folder /home/u/Games/Tekken Tag Tournament 2");
    check(l.kind == Line::Kind::kFolder && l.text == "/home/u/Games/Tekken Tag Tournament 2", "line: folder");
    l = parse_line("@error not enough free space");
    check(l.kind == Line::Kind::kError && l.text == "not enough free space", "line: error");
    check(parse_line("@done").kind == Line::Kind::kDone && parse_line("@ok").kind == Line::Kind::kOk, "line: done, ok");
    l = parse_line("@skipped geese its DLC is not owned");
    check(l.kind == Line::Kind::kSkipped && l.word == "geese" && l.text == "its DLC is not owned", "line: skipped");
    l = parse_line("@added kazumi");
    check(l.kind == Line::Kind::kAdded && l.word == "kazumi", "line: added");
    l = parse_line("@stand-in reina Steam is not running: start it");
    check(l.kind == Line::Kind::kStandIn && l.word == "reina" && l.text == "Steam is not running: start it",
          "line: stand-in");
    check(parse_line("@stand-in").kind == Line::Kind::kText, "line: stand-in without a fighter is text");
    l = parse_line("@removed chloe");
    check(l.kind == Line::Kind::kRemoved && l.word == "chloe", "line: removed");
    l = parse_line("[ 12%] Building CXX object");
    check(l.kind == Line::Kind::kText && l.text == "[ 12%] Building CXX object", "line: text");
    check(parse_line("@unknown x").kind == Line::Kind::kText && parse_line("@done now").kind == Line::Kind::kText,
          "line: unknown words are text");

    Progress build(Progress::Kind::kBuild);
    check(build.fraction() < 0, "progress: unknown at first");
    build.feed(parse_line("@step check Checking the game"));
    check(build.fraction() == 0 && build.step() == "Checking the game", "progress: first step");
    build.feed(parse_line("@step compile"));
    const double compile_start = build.fraction();
    check(build.step() == "Compiling the game program" && compile_start > 0.05, "progress: compile, own text");
    build.feed(parse_line("@progress 500 1000"));
    check(build.fraction() > compile_start && build.detail() == "500 of 1,000 files", "progress: compile files");
    build.feed(parse_line("@step copy Copying the game"));
    build.feed(parse_line("@progress 4200000000 15900000000"));
    check(build.detail() == "4.2 of 15.9 GB", "progress: copy bytes (" + build.detail() + ")");
    const double copying = build.fraction();
    build.feed(parse_line("@step finish Finishing"));
    check(build.fraction() > copying && build.detail().empty(), "progress: finish");
    build.feed(parse_line("@done"));
    check(build.fraction() == 1, "progress: done");

    Progress import(Progress::Kind::kImport);
    import.set_names({{"kazumi", "Kazumi Mishima"}});
    import.feed(parse_line("@step dump Saving movesets"));
    check(import.fraction() < 0 && import.step() == "Saving movesets", "progress: dump has no fraction");
    import.feed(parse_line("@step fighter kazumi 1 2"));
    check(import.step() == "Adding Kazumi Mishima" && import.detail() == "1 of 2" && import.fraction() == 0,
          "progress: first fighter");
    import.feed(parse_line("@added kazumi"));
    check(std::fabs(import.fraction() - 0.475) < 1e-9, "progress: a fighter added");
    import.feed(parse_line("@step fighter chloe 2 2"));
    check(import.step() == "Adding chloe" && std::fabs(import.fraction() - 0.475) < 1e-9, "progress: second fighter");
    import.feed(parse_line("@step shared"));
    check(import.fraction() == 0.95, "progress: shared");

    Progress download(Progress::Kind::kDownload);
    download.feed(parse_line("@step update Downloading version 0.2.0"));
    check(download.step() == "Downloading version 0.2.0" && download.fraction() < 0, "progress: download step");
    download.feed(parse_line("@progress 1300000 2652664"));
    check(download.detail() == "1.3 of 2.7 MB" && std::fabs(download.fraction() - 1300000.0 / 2652664) < 1e-9,
          "progress: download bytes (" + download.detail() + ")");
    download.feed(parse_line("@step update Checking version 0.2.0"));
    check(download.fraction() < 0 && download.detail().empty(), "progress: download's next step");

    // The game's last lines: a crash's registers and return addresses, an X
    // error's details and the frame rate reports left out.
    const std::string crash = "ttt2: window: 1280x800 pixels, fullscreen\n"
                              "ttt2: gpu: cannot compile vertex shader 0123456789abcdef:\n"
                              "ttt2: gpu: 40.1 frames/s, 325 draws per frame\n"
                              "ttt2: gpu: video memory: 4 stream-out buffers (88 MB)\n"
                              "ttt2: present: 39.8/s, interval mean 25.10 ms\n"
                              "ttt2: cpu: window 1%, present 6%, gpu 41%\n"
                              "\n"
                              "ttt2: cannot create a Vulkan surface for the window: no device\n"
                              "  r0  00000000  r1  0FFFE000  r2  00000000  r3  00000001\n"
                              "guest backtrace (LR, then saved return addresses):\n"
                              "  0x0865BDF0\n";
    auto said = last_words(crash, 3);
    check(said.size() == 3 && said[0] == "ttt2: window: 1280x800 pixels, fullscreen" &&
              said[1] == "ttt2: gpu: cannot compile vertex shader 0123456789abcdef:" &&
              said[2] == "ttt2: cannot create a Vulkan surface for the window: no device",
          "last words: a fatal error");
    said = last_words("[guest] Devname usb0\r\nX Error of failed request:  BadMatch\n"
                      "  Major opcode of failed request:  20 (X_GetProperty)\nttt2: the game exited with status 1",
                      2);
    check(said.size() == 2 && said[0] == "X Error of failed request:  BadMatch" &&
              said[1] == "ttt2: the game exited with status 1",
          "last words: the last two, without a line break at the end");
    check(last_words("", 3).empty() && last_words("\n\n  r0 0\n", 3).empty(), "last words: none");
    check(last_words(std::string(500, 'x'), 1)[0].size() == 300, "last words: a long line is cut");

    check(thousands(0) == "0" && thousands(999) == "999" && thousands(1000) == "1,000" &&
              thousands(1234567) == "1,234,567",
          "thousands");
    check(gigabytes(15'900'000'000) == "15.9 GB", "gigabytes");
}

void test_paths(const fs::path& root) {
    // Menu entries as install.cpp writes them.
    auto program = desktop_program("[Desktop Entry]\nType=Application\nName=Tekken Tag Tournament 2\n"
                                   "Exec=\"/home/u/Games/Tekken Tag Tournament 2/Tekken Tag Tournament 2\"\n");
    check(program && *program == "/home/u/Games/Tekken Tag Tournament 2/Tekken Tag Tournament 2", "desktop: quoted");
    program = desktop_program("[Desktop Entry]\nExec=\"/a \\\\\"b\\\\\" 100%% \\\\$x\\\\\\\\y/p\" --flag\n");
    check(program && *program == "/a \"b\" 100% $x\\y/p", "desktop: escapes (" + program.value_or("").string() + ")");
    program = desktop_program("[Desktop Entry]\nExec=/usr/bin/ttt2 %f\n");
    check(program && *program == "/usr/bin/ttt2", "desktop: unquoted");
    check(!desktop_program("[Other]\nExec=/x\n") && !desktop_program("[Desktop Entry]\nName=x\n") &&
              !desktop_program("[Desktop Entry]\nExec=\"/open\n"),
          "desktop: no program");
    program = desktop_program("[Desktop Entry]\nExecutable=/no\nExec = /yes\n[Desktop Action x]\nExec=/action\n");
    check(program && *program == "/yes", "desktop: the main group's Exec key");

    check(inside("/a/b/c", "/a/b") && inside("/a/b", "/a/b/") && !inside("/a/bc", "/a/b") && !inside("/a", "/a/b"),
          "inside");
    check(normal("/a/./b/../c/") == "/a/c" && normal("/") == "/", "normal");

    // Where an install into a chosen folder goes.
    const fs::path games = root / "Games";
    fs::create_directories(games / "full");
    write(games / "full/other.txt", "x");
    fs::create_directories(games / "empty");
    write(games / "done/.ttt2-install", "x");
    check(install_target(games / "new") == games / "new", "target: a new folder");
    check(install_target(games / "empty") == games / "empty", "target: an empty folder");
    check(install_target(games / "done/") == games / "done", "target: an earlier install");
    check(install_target(games / "full") == games / "full" / kProgramName, "target: a folder in use gets one inside");
    write(games / "full" / kProgramName / "mine.txt", "x");
    std::string error;
    check(!install_target(games / "full", &error) &&
              error == "holds a \"Tekken Tag Tournament 2\" that is not an install of the game",
          "target: taken twice (" + error + ")");
    check(!install_target(games / "full/other.txt", &error) && error == "is not a folder", "target: a file");

    // The install's state.
    Places places;
    places.home = root / "home";
    places.config = root / "config";
    places.data = root / "data";
    check(find_install(places).state == InstallState::kNone, "state: nothing");
    write(places.record(), (games / "done").string() + "\n");
    Install install = find_install(places);
    check(install.state == InstallState::kInstalled && install.folder == games / "done", "state: installed");
    write(games / "half/.ttt2-installing", "x");
    check(write_started_record(places, games / "half", "/x/game.wua"), "state: started record");
    install = find_install(places);
    check(install.state == InstallState::kUnfinished && install.folder == games / "half" &&
              install.game == "/x/game.wua",
          "state: an unfinished install started by the launcher");
    write(games / "half/.ttt2-install", "x");
    check(find_install(places).folder == games / "done", "state: a finished one's start record is stale");
    fs::remove(places.started_record());
    write(games / "done/.ttt2-installing", "x");
    fs::remove(games / "done/.ttt2-install");
    install = find_install(places);
    check(install.state == InstallState::kUnfinished && install.folder == games / "done" && install.game.empty(),
          "state: an install over the recorded one stopped");

    write(root / "kit/VERSION", "0.3.0-abc1234\n");
    check(kit_version(root / "kit") == "0.3.0-abc1234" && kit_version(root / "nokit").empty(), "kit version");
    write(games / "done/.ttt2-build", "compiler clang++ 21\nkit 0.2.0-0000000\n");
    check(built_version(games / "done") == "0.2.0-0000000" && built_version(games / "new").empty(), "built version");
    check(find_in_path("sh").has_value() && !find_in_path("no-such-program-ttt2").has_value(), "find in PATH");
}

// The game's program running, as started from anywhere.
void test_running(const fs::path& root) {
    const fs::path folder = root / "disk/Tekken Tag Tournament 2";
    const fs::path program = folder / kProgramName;
    fs::create_directories(folder);
    check(!program_running(folder), "running: nothing runs");
    const pid_t pid = run_program(program);
    check(pid > 0 && program_running(folder), "running: the program");
    check(program_running(folder.string() + "/"), "running: the folder with a trailing slash");
    std::error_code ec;
    fs::create_directories(root / "Games");
    fs::create_directory_symlink(folder, root / "Games/TTT2", ec);
    check(program_running(root / "Games/TTT2"), "running: the folder through a link");
    check(!program_running(root / "disk"), "running: another folder's program");
    write(root / "disk/other/x", "x");
    check(!program_running(root / "disk/other"), "running: a folder without it");
    fs::remove(program);
    check(program_running(folder), "running: the program deleted while it runs");
    stop_program(pid);
    check(!program_running(folder), "running: it ended");
}

void test_system() {
    const auto none = missing_cpu_features("processor : 0\nflags : fpu sse2 cx16 lahf_lm popcnt pni ssse3 sse4_1 "
                                           "sse4_2 avx avx2 bmi1 bmi2 f16c fma abm movbe xsave\n");
    check(none.empty(), "cpu: x86-64-v3");
    const auto some = missing_cpu_features("flags\t\t: fpu sse2 cx16 lahf_lm popcnt pni ssse3 sse4_1 sse4_2 avx\n");
    check(some.size() == 8 && some[0] == "AVX2", "cpu: x86-64-v2 lacks AVX2 and more");
    check(missing_cpu_features("Features : fp asimd\n").size() == 16, "cpu: not x86");

    Distro d = parse_os_release("NAME=\"Example Linux\"\nID=example\nID_LIKE=arch\n");
    check(d.name == "Example Linux" && d.like.size() == 2 && d.like[1] == "arch", "os-release: like arch");
    check(install_command(d, {Package::kCompiler}) == "sudo pacman -S --needed clang", "command: arch");
    d = parse_os_release("ID=linuxmint\nID_LIKE=\"ubuntu debian\"\n");
    check(install_command(d, {Package::kNumpy, Package::kPillow}) == "sudo apt install python3-numpy python3-pil",
          "command: mint");
    d = parse_os_release("ID=\"opensuse-tumbleweed\"\nID_LIKE=\"opensuse suse\"\n");
    check(install_command(d, {Package::kPactl}) == "sudo zypper install pulseaudio-utils", "command: suse");
    d = parse_os_release("ID=fedora\n");
    check(install_command(d, {Package::kCompiler, Package::kCompiler}) == "sudo dnf install clang gcc-c++",
          "command: fedora");
    check(install_command(parse_os_release("ID=plan9\n"), {Package::kCompiler}).empty(), "command: unknown");

    // Systems whose own files come as one image.
    const auto image = [](const char* os_release, bool ostree = false) {
        Distro distro = parse_os_release(os_release);
        distro.ostree = ostree;
        return image_based(distro) && install_command(distro, {Package::kCompiler}).empty();
    };
    check(image("ID=steamos\nID_LIKE=arch\nVARIANT_ID=steamdeck\n"), "image: SteamOS");
    check(image("ID=fedora\nVARIANT_ID=silverblue\n") && image("ID=fedora\nVARIANT_ID=kinoite\n") &&
              image("ID=fedora\nVARIANT_ID=sericea\n") && image("ID=fedora\nVARIANT_ID=onyx\n") &&
              image("ID=fedora\nVARIANT_ID=atomic\n") && image("ID=fedora\nVARIANT_ID=iot\n") &&
              image("ID=fedora\nVARIANT_ID=coreos\n"),
          "image: Fedora's atomic variants");
    check(image("ID=fedora\nVARIANT_ID=cosmic-atomic\n", true), "image: any OSTree system");
    check(image("NAME=\"Bazzite\"\nID=bazzite\nID_LIKE=\"fedora\"\nVARIANT_ID=bazzite-deck\n"), "image: Bazzite");
    check(image("ID=\"opensuse-microos\"\nID_LIKE=\"suse opensuse opensuse-tumbleweed\"\n") &&
              image("ID=opensuse-tumbleweed\nID_LIKE=\"opensuse suse aeon\"\n") && image("ID=\"opensuse-kalpa\"\n"),
          "image: openSUSE MicroOS, Aeon, Kalpa");
    check(image("ID=nixos\n") && image("ID=guix\n"), "image: NixOS and Guix");
    check(!image_based(parse_os_release("ID=fedora\nVARIANT_ID=workstation\n")) &&
              !image_based(parse_os_release("ID=cachyos\nID_LIKE=arch\n")) &&
              !image_based(parse_os_release("ID=opensuse-tumbleweed\nID_LIKE=\"opensuse suse\"\n")) &&
              !image_based(parse_os_release("ID=ubuntu\nID_LIKE=debian\nVARIANT_ID=atomicish\n")),
          "image: package-managed systems are not");
    check(image_based_hint("a C++ compiler") ==
              "This system's own files cannot be changed with a package manager: a C++ compiler must come from a "
              "toolbox or distrobox container, or from the system's own way of adding software.",
          "image: the hint, as the builder's");

    check(run_output({"sh", "-c", "echo hello"}) == std::optional<std::string>("hello\n"), "run: output");
    check(!run_output({"sh", "-c", "exit 3"}) && !run_output({"no-such-program-ttt2"}), "run: failures");
    // The preflight probes from a worker thread; a file the launcher has open without O_CLOEXEC
    // (another thread's, a library's) is not the probe's, and the probe runs with no signal blocked.
    {
        const int leaky = ::open("/dev/null", O_RDONLY); // (no O_CLOEXEC on purpose)
        sigset_t block, old;
        sigemptyset(&block);
        sigaddset(&block, SIGTERM);
        std::optional<std::string> fds, blocked;
        std::thread worker([&] {
            ::pthread_sigmask(SIG_BLOCK, &block, &old); // (as a thread may have them)
            fds = run_output({"sh", "-c", "test -e /proc/self/fd/" + std::to_string(leaky) + " && echo open || echo closed"});
            blocked = run_output({"sh", "-c", "grep SigBlk /proc/self/status"});
        });
        worker.join();
        check(leaky > 2 && fds == std::optional<std::string>("closed\n"),
              "run: the launcher's files are closed in the probe (" + fds.value_or("none") + ")");
        check(blocked && blocked->find("SigBlk:\t0000000000000000") != std::string::npos,
              "run: no signal blocked in the probe (" + blocked.value_or("none") + ")");
        ::close(leaky);
    }
}

// The compiler as the builder chooses it, with compilers that only say their
// version in a PATH of their own.
void test_compiler(const fs::path& root) {
    const auto compiler = [&](const char* name, const char* version) {
        const fs::path file = root / name;
        write(file, std::string("#!/bin/sh\necho ") + version + "\n");
        fs::permissions(file, fs::perms::owner_all);
    };
    const char* path = std::getenv("PATH");
    const char* cxx = std::getenv("CXX");
    const std::string saved_path = path ? path : "", saved_cxx = cxx ? cxx : "";
    ::unsetenv("CXX");
    ::setenv("PATH", root.c_str(), 1); // (not the PC's own compilers)
    std::string why;
    check(!find_compiler(&why) && why == "no C++ compiler is installed", "compiler: none");
    compiler("g++", "13.2.0");
    check(!find_compiler(&why) && why == "g++ 13.2.0 is too old (15 or newer is needed)", "compiler: GCC too old");
    compiler("clang++-12", "12.0.1");
    compiler("clang++-18", "18.1.3");
    const auto found = find_compiler();
    check(found && found->path == root / "clang++-18" && found->name == "clang++-18 18.1.3",
          "compiler: a versioned Clang, the newest that will do");
    ::setenv("PATH", saved_path.c_str(), 1);
    if (cxx) ::setenv("CXX", saved_cxx.c_str(), 1);
}

void test_actions() {
    std::string error;
    const auto actions = parse_test_actions(
        "install:/g/TEKKEN (EU).wua:/i/x ; update;add:kazumi, chloe;add-all-base;add-all-owned;remove:kazumi;"
        "uninstall:keep;uninstall:all;play;expand-dlc;expand-log;show-uninstall;wait:1.5;quit;focus:add:kazumi;"
        "refresh;toggle:outfits:kazumi;get-packages",
        &error);
    check(actions.has_value(), "actions: parse (" + error + ")");
    if (!actions) return;
    check(actions->size() == 18, "actions: count");
    check((*actions)[17].name == "get-packages" && (*actions)[17].args.empty(), "actions: get-packages");
    check((*actions)[16].name == "toggle" && (*actions)[16].args == std::vector<std::string>{"outfits:kazumi"},
          "actions: toggle");
    check((*actions)[14].name == "focus" && (*actions)[14].args.size() == 1 && (*actions)[14].args[0] == "add:kazumi" &&
              (*actions)[14].label() == "focus-add_kazumi",
          "actions: focus");
    check((*actions)[15].name == "refresh" && (*actions)[15].args.empty(), "actions: refresh");
    check((*actions)[0].name == "install" && (*actions)[0].args.size() == 2 &&
              (*actions)[0].args[0] == "/g/TEKKEN (EU).wua" && (*actions)[0].args[1] == "/i/x",
          "actions: install");
    check((*actions)[0].label() == "install", "actions: no paths in labels");
    check((*actions)[2].args.size() == 2 && (*actions)[2].args[1] == "chloe" &&
              (*actions)[2].label() == "add-kazumi-chloe",
          "actions: add");
    check((*actions)[7].label() == "uninstall-all", "actions: uninstall label");
    const auto all = parse_test_actions("add-all:tekken8;remove-all:tekken7;add-all-owned:tekken8", &error);
    check(all && all->size() == 3 && (*all)[0].args == std::vector<std::string>{"tekken8"} &&
              (*all)[0].label() == "add-all-tekken8" && (*all)[1].label() == "remove-all-tekken7" &&
              (*all)[2].label() == "add-all-owned-tekken8" && !parse_test_actions("add-all-owned:tekken6", nullptr) &&
              parse_test_actions("add-all-owned:all", nullptr),
          "actions: a game's Add All and Remove All (" + error + ")");
    const auto settings =
        parse_test_actions("settings; bind:face_bottom:38 ;bind:plus:9;reset-keys;back;bind:zl:64+23", &error);
    check(settings && settings->size() == 6, "actions: settings (" + error + ")");
    if (settings && settings->size() == 6) {
        const TestAction& chord = (*settings)[5];
        check(chord.args.size() == 2 && chord.args[1] == "64+23" && chord.label() == "bind-zl-64_23",
              "actions: bind, keys together");
        const TestAction& bind = (*settings)[1];
        check(bind.name == "bind" && bind.args.size() == 2 && bind.args[0] == "face_bottom" && bind.args[1] == "38" &&
                  bind.label() == "bind-face_bottom-38",
              "actions: bind");
        check((*settings)[0].name == "settings" && (*settings)[3].name == "reset-keys" && (*settings)[4].name == "back",
              "actions: settings, reset-keys, back");
    }
    const auto input =
        parse_test_actions("press:Return;pad:south;steam:south;click:play;hover:fighters;tab:next", &error);
    check(input && input->size() == 6 && (*input)[0].args == std::vector<std::string>{"Return"} &&
              (*input)[5].label() == "tab-next",
          "actions: input as the devices give it (" + error + ")");
    const auto name = parse_test_actions("player-name:Mira Q;player-name:;type:ab c", &error);
    check(name && name->size() == 3 && (*name)[0].args == std::vector<std::string>{"Mira Q"} &&
              (*name)[1].args == std::vector<std::string>{""} && (*name)[2].args == std::vector<std::string>{"ab c"} &&
              (*name)[0].label() == "player-name-_ira__",
          "actions: player-name and type (" + error + ")");
    check(!parse_test_actions("player-name", &error) && !parse_test_actions("type:", &error) &&
              !parse_test_actions("type", &error),
          "actions: player-name needs its colon, type its text");
    const auto language = parse_test_actions("language:fr;language:RU;language:en", &error);
    check(language && language->size() == 3 && (*language)[0].args == std::vector<std::string>{"fr"} &&
              (*language)[1].args == std::vector<std::string>{"ru"} && (*language)[1].label() == "language-ru" &&
              (*language)[2].args == std::vector<std::string>{"en"},
          "actions: language, by the game's codes in any case (" + error + ")");
    check(!parse_test_actions("language:xx", &error) && !parse_test_actions("language:", &error) &&
              !parse_test_actions("language", &error),
          "actions: language needs a code the game has");
    check(!parse_test_actions("tab:sideways", &error) && !parse_test_actions("press", &error),
          "actions: input needs what to press");
    const auto rows = parse_test_actions("rows:pe::300;rows:pp::0.5", &error);
    check(rows && rows->size() == 2 && (*rows)[0].args == std::vector<std::string>{"pe:", "300"} &&
              (*rows)[1].args == std::vector<std::string>{"pp:", "0.5"},
          "actions: rows of a list in view (" + error + ")");
    const auto shown = parse_test_actions(
        "fullscreen:yes;fullscreen:no;resolution:1920x1080;resolution:AUTO;interpolation:no;interpolation:yes;"
        "input-delay:yes",
        &error);
    check(shown && shown->size() == 7, "actions: display settings (" + error + ")");
    if (shown && shown->size() == 7) {
        check((*shown)[0].name == "fullscreen" && (*shown)[0].args == std::vector<std::string>{"yes"} &&
                  (*shown)[0].label() == "fullscreen-yes" && (*shown)[1].args[0] == "no",
              "actions: fullscreen");
        check((*shown)[2].name == "resolution" && (*shown)[2].args == std::vector<std::string>{"1920x1080"} &&
                  (*shown)[2].label() == "resolution-1920x1080",
              "actions: resolution");
        check((*shown)[3].args == std::vector<std::string>{"auto"} && (*shown)[3].text == "resolution:AUTO",
              "actions: resolution as the file names it");
        check((*shown)[4].name == "interpolation" && (*shown)[4].args[0] == "no" &&
                  (*shown)[5].label() == "interpolation-yes",
              "actions: interpolation");
        check((*shown)[6].name == "input-delay" && (*shown)[6].args[0] == "yes" &&
                  (*shown)[6].label() == "input-delay-yes",
              "actions: input-delay");
    }
    for (const char* bad : {"install:/only", "uninstall:some", "add:", "dance", "play:now", "wait:x", "focus:", "focus",
                            "toggle:", "toggle",
                            "refresh:now", "bind", "bind:face_bottom", "bind:face_bottom:", "bind:nope:38",
                            "bind:face_bottom:x", "bind:face_bottom:0", "settings:now", "reset-keys:all",
                            "bind:zl:64+", "bind:zl:+64", "bind:zl:64++23", "bind:zl:64+x", "bind:zl:-1",
                            "fullscreen", "fullscreen:", "fullscreen:on", "fullscreen:YES", "interpolation",
                            "interpolation:1", "input-delay", "input-delay:2", "input_delay:yes", "async-shaders",
                            "async-shaders:1", "async_shaders:yes", "precompile-shaders", "precompile-shaders:on", "resolution",
                            "resolution:", "resolution:1920", "resolution:1366x768",
                            "resolution:auto:x", "add-all", "add-all:", "add-all:tekken6", "remove-all",
                            "get-packages:numpy", "rows", "rows:", "rows:pe:", "rows::300", "rows:pe::x",
                            "rows:pe::-1"}) {
        check(!parse_test_actions(bad), std::string("actions: rejects ") + bad);
    }
}

std::string text_of(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(in), {});
}

// display.ini as the Settings page saves it, read back by the game's code.
void test_display(const fs::path& root) {
    Places places;
    places.config = root / "config";
    const fs::path file = places.display();
    check(file == root / "config/ttt2/display.ini", "display: next to keyboard.ini");
    check(display::load(file).error.empty() && display::load(file).settings == display::Settings{},
          "display: no file, the defaults");

    // Every value, each written whole over the one before (the folder made
    // by the first).
    int saved = 0;
    for (const bool fullscreen : {false, true}) {
        for (const display::Resolution resolution : display::kResolutions) {
            for (const bool interpolation : {true, false}) {
                for (const bool input_delay : {false, true}) {
                    const display::Settings settings{fullscreen, resolution, interpolation, input_delay};
                    std::string error;
                    const bool ok = save_display(file, settings, &error);
                    const display::Loaded loaded = display::load(file);
                    const std::string what = "display: round trip of " + std::string(display::name_of(resolution)) +
                                             (fullscreen ? ", fullscreen" : "") + (interpolation ? "" : ", 60 fps") +
                                             (input_delay ? ", input delay" : "");
                    check(ok && error.empty(), what + ", saved (" + error + ")");
                    check(loaded.error.empty() && loaded.settings == settings &&
                              text_of(file) == display::format(settings),
                          what + ", read back");
                    saved += ok;
                }
            }
        }
    }
    check(saved == 48, "display: all 48 saved");
    std::error_code ec;
    size_t files = 0;
    for (const auto& entry : fs::directory_iterator(file.parent_path(), ec)) files += entry.path() == file ? 1 : 100;
    check(files == 1, "display: no temporary file left");

    // Its mode kept, and a link kept as one (the file it leads to written).
    fs::permissions(file, fs::perms(0640), ec);
    check(save_display(file, {}), "display: saved over a 0640 file");
    struct stat st{};
    check(::stat(file.c_str(), &st) == 0 && (st.st_mode & 07777) == 0640, "display: its mode kept");
    const fs::path elsewhere = root / "dotfiles/display.ini";
    write(elsewhere, "fullscreen = yes\n");
    fs::remove(file, ec);
    fs::create_symlink("../../dotfiles/display.ini", file, ec);
    const display::Settings big{true, display::Resolution::k2880, false};
    check(save_display(file, big) && fs::is_symlink(file, ec) && display::load(elsewhere).settings == big,
          "display: a link followed and kept");
    fs::remove(file, ec);
    // A link to itself, and a loop of two, say why (not "Success").
    const std::string loop = "cannot follow the link " + file.string() + ": " + std::strerror(ELOOP);
    for (const char* to : {"display.ini", "other.ini"}) {
        fs::create_symlink(to, file, ec);
        if (std::string_view(to) != "display.ini") fs::create_symlink("display.ini", file.parent_path() / to, ec);
        std::string error;
        check(!save_display(file, big, &error) && error == loop, "display: a link loop (" + error + ")");
        fs::remove(file, ec);
        fs::remove(file.parent_path() / "other.ini", ec);
    }

    // A file that is there and cannot be read: the reason without its path.
    fs::create_directories(file, ec);
    display::Loaded loaded = display::load(file);
    check(unreadable_reason(loaded.error, file) == "it is not a file" && loaded.settings == display::Settings{},
          "display: a folder (" + loaded.error + ")");
    std::string error;
    check(!save_display(file, big, &error) && error.starts_with("cannot write " + file.string() + ": ") &&
              fs::is_directory(file, ec),
          "display: a folder is not replaced (" + error + ")");
    fs::remove(file, ec);
    write(file, "resolution = 1920x1080\n");
    fs::permissions(file, fs::perms::none, ec);
    loaded = display::load(file);
    // (Root reads it anyway.)
    if (::geteuid() != 0) {
        check(unreadable_reason(loaded.error, file) == "Permission denied",
              "display: unreadable (" + loaded.error + ")");
    }
    check(save_display(file, big) && display::load(file).settings == big, "display: an unreadable file written anew");
    check(::stat(file.c_str(), &st) == 0 && (st.st_mode & 07777) == 0600, "display: written anew, its owner's");
    check(unreadable_reason("something else", file) == "something else", "display: other reasons as they are");

    check(resolution_label(display::Resolution::kAuto) == "Automatic" &&
              resolution_label(display::Resolution::k720) == "1280 \u00d7 720" &&
              resolution_label(display::Resolution::k1080) == "1920 \u00d7 1080" &&
              resolution_label(display::Resolution::k2880) == "5120 \u00d7 2880",
          "display: the list's names");
    check(automatic_size(720) == "1280 \u00d7 720" && automatic_size(1080) == "2560 \u00d7 1440" &&
              automatic_size(1440) == "2560 \u00d7 1440" && automatic_size(2160) == "3840 \u00d7 2160" &&
              automatic_size(0) == "1280 \u00d7 720" && automatic_size(4320) == "5120 \u00d7 2880",
          "display: automatic sizes");

    // What the page says of the monitors: figures only when the game surely
    // goes by them (one monitor; with more, every one below 100 Hz).
    check(automatic_note({{1080, 60000}}) == "Automatic: enough to cover the display (2560 \u00d7 1440 on this one)." &&
              automatic_note({{2160, 0}}) == "Automatic: enough to cover the display (3840 \u00d7 2160 on this one)." &&
              automatic_note({{0, 60000}}) == "Automatic: enough to cover the display." &&
              automatic_note({}) == "Automatic: enough to cover the display." &&
              automatic_note({{1080, 60000}, {1080, 60000}}) == "Automatic: enough to cover the main display.",
          "display: the Automatic note");
    check(hertz_text(60000) == "60" && hertz_text(59940) == "60" && hertz_text(99499) == "99" &&
              hertz_text(99500) == "99.5" && hertz_text(99982) == "99.98" && hertz_text(99999) == "99.99" &&
              hertz_text(99900) == "99.9" && hertz_text(100000) == "100" && hertz_text(143998) == "144",
          "display: refresh rates as said");
    const auto note = [](std::vector<Monitor> monitors) { return refresh_note(monitors); };
    check(note({{1080, 60000}}) == "This display refreshes at 60 Hz: the game stays at 60 fps there." &&
              note({{1080, 99982}}) == "This display refreshes at 99.98 Hz: the game stays at 60 fps there." &&
              note({{1080, 100000}}).empty() && note({{1080, 144000}}).empty() && note({{1080, 0}}).empty() &&
              note({}).empty(),
          "display: the 60 fps note, one monitor");
    check(note({{1080, 60000}, {2160, 59940}}) == "These displays refresh at 60 Hz: the game stays at 60 fps." &&
              note({{1080, 60000}, {1440, 75000}}) ==
                  "These displays refresh at up to 75 Hz: the game stays at 60 fps." &&
              note({{1080, 60000}, {1440, 144000}}).empty() && note({{1080, 60000}, {1440, 0}}).empty(),
          "display: the 60 fps note, more monitors");
}

// game.ini as Settings > Game saves it: the player's name, every other line kept.
void test_game_ini(const fs::path& root) {
    Places places;
    places.config = root / "config";
    const fs::path file = game_ini::beside(places.display());
    check(file == root / "config/ttt2/game.ini", "game.ini: beside display.ini");
    game_ini::Loaded loaded = game_ini::load(file);
    check(loaded.error.empty() && !loaded.exists && loaded.settings.player_name.empty(), "game.ini: no file, no name");

    // The limits.
    check(game_ini::name_problem("").empty() && game_ini::name_problem("   ").empty() &&
              game_ini::name_problem("Mira").empty() && game_ini::name_problem("  Mira Q.  ").empty() &&
              game_ini::name_problem("A~z!0 9_-'()[]{}").empty() && game_ini::name_problem("a#b").size() > 0,
          "game.ini: names that can be kept, # cannot");
    check(game_ini::name_problem("ABCDEFGHIJKLMNOP").empty() &&
              game_ini::name_problem("ABCDEFGHIJKLMNOPQ") == "It has 17 characters: 16 at most." &&
              game_ini::name_problem(" ABCDEFGHIJKLMNOP ").empty(),
          "game.ini: 16 characters at most, the spaces at both ends not counted");
    check(game_ini::name_problem("Jos\xC3\xA9") == "It has \u201C\xC3\xA9\u201D, which a name cannot have." &&
              game_ini::name_problem("a\tb") == "It has a control character, which a name cannot have." &&
              game_ini::name_problem("a\xFF") == "It has \u201C\xFF\u201D, which a name cannot have.",
          "game.ini: what a name cannot have, said (" + game_ini::name_problem("Jos\xC3\xA9") + ")");
    check(game_ini::first_refused("ok \xE2\x82\xAC!") == "\xE2\x82\xAC" && game_ini::first_refused("ok").empty() &&
              game_ini::first_refused("\xE2\x82") == "\xE2",
          "game.ini: the first character refused, whole");
    check(game_ini::tidy_name("  Mira Q  ") == "Mira Q" && game_ini::tidy_name(" \t ").empty(), "game.ini: tidied");
    // The game's own name in each of its languages: its own word, or none where the font cannot draw it.
    for (const cafe::host::game::Language& l : cafe::host::game::kLanguages) {
        const std::string_view own = game_ini::own_name(l.code);
        check(l.code == "en" ? own == "Player" : own != "Player",
              "game.ini: the game's own name in " + std::string(l.name) + " (\"" + std::string(own) + "\")");
        for (const char c : own) check(static_cast<unsigned char>(c) < 0x80 || l.code != "ru", "game.ini: drawable");
    }
    check(game_ini::own_name("") == "Player" && game_ini::own_name("Klingon") == "Player" &&
              game_ini::own_name("FR") == "Joueur" && game_ini::own_name("ru").empty(),
          "game.ini: the game's own name, by code");
    // An overlong UTF-8 sequence is no letter: refused whole (the game shows "?" for it).
    check(game_ini::first_refused("\xC1\xA1" "bc") == "\xC1\xA1" && !game_ini::name_problem("\xC1\xA1" "bc").empty(),
          "game.ini: an overlong sequence refused");
    // The launcher reads a file's lines as the game does: its name, cleaned as the game cleans it, is the game's.
    for (const std::string text :
         {"player_name = Mira\n", "player_name = A #B\n", "player_name = A#B # c\n", "# c\nplayer_name=  Zo\xC3\xAB \n",
          "\xEF\xBB\xBFplayer_name = X\r\nplayer_name = Y\r\n", "player_name =\n", "other = 1\nplayer_name = Q\n",
          "player_name = ABCDEFGHIJKLMNOPQRST\n", "player_name\n", "player_name = \t tab\t\n", "#player_name = no\n",
          "  player_name   =   Spaced Out  \n", "player_name = a\xFF" "b\n", "player_name = \xC1\xA1" "bc\n", ""}) {
        const std::string mine = cafe::host::game::clean_name(game_ini::parse(text).player_name),
                          game = cafe::host::game::parse(text).settings.player_name;
        check(mine == game, "game.ini: read as the game reads it (" + mine + " / " + game + ")");
    }
    check(game_ini::name_rule().find("16") != std::string::npos, "game.ini: the rule says the most");

    // A new file: a header, the name.
    std::string error;
    check(game_ini::save_name(file, "  Mira Q ", &error), "game.ini: saved (" + error + ")");
    loaded = game_ini::load(file);
    check(loaded.exists && loaded.error.empty() && loaded.settings.player_name == "Mira Q",
          "game.ini: read back (" + loaded.error + ")");
    check(text_of(file).starts_with("# ") && text_of(file).ends_with("\nplayer_name = Mira Q\n"),
          "game.ini: a new file's text (" + text_of(file) + ")");

    // Another one's lines kept: comments, settings the launcher does not know, their order, CRLF.
    const std::string hand = "\xEF\xBB\xBF# mine\r\nvolume = 7  # loud\r\nplayer_name = Old # was\r\n"
                             "\r\nfuture_thing = yes\r\nplayer_name=Older\r\nlast = 1";
    write(file, hand);
    check(game_ini::load(file).settings.player_name == "Older", "game.ini: the later line counts");
    check(game_ini::save_name(file, "New One", &error), "game.ini: saved over another's (" + error + ")");
    check(text_of(file) == "\xEF\xBB\xBF# mine\r\nvolume = 7  # loud\r\nplayer_name = New One\r\n\r\n"
                           "future_thing = yes\r\nlast = 1",
          "game.ini: every other line kept (" + text_of(file) + ")");
    check(game_ini::load(file).settings.player_name == "New One", "game.ini: the new name read back");
    // The key on the first line, after a byte order mark; a name in a comment is no setting.
    check(game_ini::with_name("\xEF\xBB\xBFplayer_name = A\n# player_name = B\n", "C") ==
              "\xEF\xBB\xBFplayer_name = C\n# player_name = B\n",
          "game.ini: the key after a byte order mark");
    check(game_ini::parse("# player_name = B\nplayer_name = A#1 # comment\n").player_name == "A#1",
          "game.ini: comments as display.ini's");
    // None: the key left out, the rest kept.
    check(game_ini::save_name(file, "   ", &error), "game.ini: no name saved (" + error + ")");
    check(text_of(file) == "\xEF\xBB\xBF# mine\r\nvolume = 7  # loud\r\n\r\nfuture_thing = yes\r\nlast = 1",
          "game.ini: no name, no key (" + text_of(file) + ")");
    check(game_ini::load(file).settings.player_name.empty(), "game.ini: no name read back");
    check(game_ini::with_name("last = 1", "Z") == "last = 1\nplayer_name = Z\n", "game.ini: added at the end");
    check(game_ini::with_name("", "") == game_ini::with_name("\n \n", "") &&
              game_ini::parse(game_ini::with_name("", "")).player_name.empty(),
          "game.ini: a new file without a name");

    // The language: its line set, every other line kept.
    write(file, hand);
    check(game_ini::load(file).settings.language.empty(), "game.ini: no language");
    check(game_ini::save_language(file, "fr", &error), "game.ini: language saved (" + error + ")");
    check(text_of(file) == hand + "\nlanguage = fr\n", "game.ini: language added at the end (" + text_of(file) + ")");
    loaded = game_ini::load(file);
    check(loaded.settings.language == "fr" && loaded.settings.player_name == "Older",
          "game.ini: language read back, the name kept");
    // English is written too (the choice, not the key left out).
    check(game_ini::save_language(file, "en", &error) && text_of(file) == hand + "\nlanguage = en\n",
          "game.ini: English written (" + text_of(file) + ")");
    // Given twice: the later line (the one that counts) takes it, the earlier one goes; CRLF, comments and
    // unknown keys kept.
    const std::string twice = "# mine\r\nlanguage = de # first\r\nvolume = 7\r\nplayer_name = Mira\r\n"
                              "language = XX\r\nfuture_thing = yes\r\n";
    write(file, twice);
    check(game_ini::load(file).settings.language == "XX", "game.ini: the later language line counts");
    check(game_ini::save_language(file, "it", &error) &&
              text_of(file) == "# mine\r\nvolume = 7\r\nplayer_name = Mira\r\nlanguage = it\r\nfuture_thing = yes\r\n",
          "game.ini: the later language line replaced (" + text_of(file) + ")");
    // The name saved after: the language line kept, and the other way round.
    check(game_ini::save_name(file, "Zo", &error) &&
              text_of(file) == "# mine\r\nvolume = 7\r\nplayer_name = Zo\r\nlanguage = it\r\nfuture_thing = yes\r\n",
          "game.ini: a name saved keeps the language (" + text_of(file) + ")");
    // A comment naming the key is no setting; a byte order mark before it.
    check(game_ini::with_language("\xEF\xBB\xBFlanguage = de\n# language = fr\n", "es") ==
              "\xEF\xBB\xBFlanguage = es\n# language = fr\n",
          "game.ini: the language after a byte order mark");
    check(game_ini::with_language("\xEF\xBB\xBFlanguage = de\nlanguage = fr\n", "es") == "\xEF\xBB\xBFlanguage = es\n",
          "game.ini: the byte order mark of a line left out kept");
    check(game_ini::with_language("last = 1", "ru") == "last = 1\nlanguage = ru\n" &&
              game_ini::with_language("language = fr\n", "") == "",
          "game.ini: language added at the end, or left out");
    // A new file: the header (the game's codes), then the line.
    std::error_code gone;
    fs::remove(file, gone);
    check(game_ini::save_language(file, "de", &error) && text_of(file).starts_with("# ") &&
              text_of(file).find("en, fr, de, it, es") != std::string::npos &&
              text_of(file).ends_with("\nlanguage = de\n") && game_ini::load(file).settings.language == "de",
          "game.ini: a new file with a language (" + text_of(file) + ")");
    // The launcher reads the language as the game does: the code it shows is the game's.
    for (const std::string text :
         {"language = fr\n", "language = FR\n", "language=de # mine\n", "language = xx\n", "language =\n",
          "language = en\n", "language = it\nlanguage = es\n", "language = es\nlanguage = qq\n",
          "\xEF\xBB\xBFlanguage = ru\r\n", "#language = fr\n", "language\n", "Language = fr\n", "language = f r\n",
          "  language   =   It  \n", "language = de#x\n", "language = de #x\n", "player_name = A\nlanguage = es\n",
          ""}) {
        const cafe::host::game::Language* found = cafe::host::game::find_language(game_ini::parse(text).language);
        const std::string mine = found && found != &cafe::host::game::kLanguages[0] ? std::string(found->code) : "",
                          game = cafe::host::game::parse(text).settings.language;
        check(mine == game, "game.ini: the language read as the game reads it (" + mine + " / " + game + ")");
    }

    // Files that cannot be read: said, and written anew.
    std::error_code ec;
    fs::remove(file, ec);
    fs::create_directories(file, ec);
    loaded = game_ini::load(file);
    check(loaded.error == file.string() + " is not a file" && loaded.settings.player_name.empty(),
          "game.ini: a folder (" + loaded.error + ")");
    check(!game_ini::save_name(file, "X", &error) && !error.empty(), "game.ini: a folder is not replaced");
    fs::remove(file, ec);
    write(file, std::string(70 * 1024, '#'));
    check(game_ini::load(file).error == file.string() + " is larger than 64 KiB", "game.ini: too large");
    check(game_ini::save_name(file, "Mira", &error) && game_ini::load(file).settings.player_name == "Mira" &&
              text_of(file).size() < 400,
          "game.ini: one too large written anew");
    if (::geteuid() != 0) {
        ::chmod(file.c_str(), 0);
        loaded = game_ini::load(file);
        check(loaded.error.starts_with("cannot read " + file.string() + ": "),
              "game.ini: unreadable (" + loaded.error + ")");
        ::chmod(file.c_str(), 0600);
    }
}

void test_uninstall(const fs::path& root) {
    Places places;
    places.home = root / "home";
    places.config = root / "config";
    places.data = root / "data";
    places.cache = root / "cache";
    places.saves = root / "home/.local/share/ttt2/save";
    places.packs = root / "data/ttt2/characters";
    places.tekken7_data = root / "home/.local/share/ttt2/tekken7";
    places.tekken8_data = root / "home/.local/share/ttt2/tekken8";
    const fs::path folder = root / "Games/Tekken Tag Tournament 2";
    const fs::path outside = root / "outside";

    const auto make = [&] {
        write(folder / kProgramName, "program");
        write(folder / "icon.png", "png");
        write(folder / "game/code/Tekken.rpx", "rpx");
        write(folder / "game/content/hdd/data005.bin", "data");
        write(folder / "game/content/hdd/data006.bin.part", "half");
        write(folder / (std::string(kProgramName) + ".part"), "half");
        write(folder / (std::string(kBuildRecord) + ".part"), "half");
        write(folder / kMarker, "done");
        write(folder / kBuildRecord, "kit 1\n");
        write(folder / "my notes.txt", "keep me");
        fs::create_directories(folder / "icon.png.d");
        write(outside / "precious.txt", "keep me");
        std::error_code ec;
        fs::create_directory_symlink(outside, folder / "game/content/link", ec);
        fs::create_symlink(outside / "precious.txt", folder / "game/file-link", ec);
        write(places.desktop_entry(), "[Desktop Entry]\nExec=\"" + (folder / kProgramName).string() + "\"\n");
        write(places.record(), folder.string() + "\n");
        write(places.keyboard(), "face_top = 22\n");
        write(places.display(), "fullscreen = yes\n");
        write(places.cache / "ttt2/pipelines.bin", "p");
        write(places.cache / "ttt2/spirv/1.spv", "s");
        write(places.cache / "ttt2/build/gen/a.cpp", "w");
        write(places.cache / "ttt2/tekken7/t7helper.exe", "h");
        write(places.home / ".cache/ttt2/tekken7/run/helper.log", "h"); // (an importer before $XDG_CACHE_HOME)
        write(places.owned_cache(), R"({"owned": {"eliza": true}})");
        write(places.game_log(), "ttt2: loaded image\n");
        write(places.saves / "80000001/save.dat", "save");
        write(places.saves / "common/x.dat", "save");
        write(places.packs / "kzm/character.ini", "pack");
        write(places.packs / "shared/x.bin", "shared");
        write(places.packs / "shared.part/keys/y.bin", "half"); // (an importer killed while it made shared/)
        write(places.packs / "shared.old/keys/z.bin", "old");
        // (An importer killed while it made a pack again: the new one, its
        // character.ini not written yet, and the earlier one.)
        write(places.packs / ".kzm.part/kzm.nud", "half");
        write(places.packs / ".dnc.old/dnc.nud", "old");
        write(places.packs / "notapack/readme.txt", "user");
        for (const char* name : {".kzm.tmp", ".kazumi.part", ".KZM.part", "kzm.part", ".kzm.part.bak", ".k.old"}) {
            write(places.packs / name / "readme.txt", "user");
        }
        write(places.tekken7_data / "movesets/T7_kazumi.tkmvst", "m");
        write(places.tekken8_data / "movesets/zbr.motbin", "m");
        write(places.cache / "ttt2/tekken8/t8helper.exe", "h");
        write(places.cache / "ttt2/native/oodle.so", "o");
    };
    make();

    UninstallReport r = uninstall(places, folder, {});
    check(r.refused.empty() && r.problems.empty(),
          "uninstall: ran (" + (r.problems.empty() ? r.refused : r.problems[0].text()) + ")");
    check(!r.folder_removed && r.left.size() == 2 && r.left[0] == "icon.png.d" && r.left[1] == "my notes.txt",
          "uninstall: the user's files are left");
    check(!there(folder / kProgramName) && !there(folder / "game") && !there(folder / kMarker) &&
              !there(folder / "icon.png") && !there(folder / kBuildRecord) &&
              !there(folder / (std::string(kProgramName) + ".part")) &&
              !there(folder / (std::string(kBuildRecord) + ".part")),
          "uninstall: the install's entries are gone");
    check(there(outside / "precious.txt") && there(outside), "uninstall: links are not followed");
    check(!there(places.desktop_entry()) && !there(places.record()), "uninstall: menu entry and record");
    check(!there(places.cache / "ttt2/pipelines.bin") && !there(places.cache / "ttt2/spirv") &&
              !there(places.cache / "ttt2/build") && !there(places.owned_cache()) && !there(places.game_log()),
          "uninstall: shader caches, work folder, the DLC answer and the game's log");
    check(there(places.saves / "80000001/save.dat") && there(places.packs / "kzm/character.ini") &&
              there(places.packs / ".kzm.part") && there(places.packs / ".dnc.old") &&
              there(places.tekken7_data) && there(places.cache / "ttt2/tekken7") &&
              there(places.home / ".cache/ttt2/tekken7") && there(places.tekken8_data) &&
              there(places.cache / "ttt2/tekken8") && there(places.cache / "ttt2/native"),
          "uninstall: saves and characters kept");
    check(there(places.keyboard()), "uninstall: the keyboard's keys kept (a setting)");
    check(there(places.display()), "uninstall: the display settings kept (a setting)");

    // Everything, and a folder left empty goes too.
    fs::remove_all(folder);
    make();
    fs::remove(folder / "my notes.txt");
    fs::remove(folder / "icon.png.d");
    // A menu entry and record of another install stay.
    write(places.desktop_entry(), "[Desktop Entry]\nExec=\"/elsewhere/Tekken Tag Tournament 2\"\n");
    write(places.record(), "/elsewhere\n");
    r = uninstall(places, folder, {.saves = true, .characters = true});
    check(r.refused.empty() && r.problems.empty() && r.folder_removed && r.left.empty(), "uninstall all: ran");
    check(!there(folder) && there(outside / "precious.txt"), "uninstall all: the folder is gone, links not followed");
    check(there(places.desktop_entry()) && there(places.record()), "uninstall all: another install's entries stay");
    check(!there(places.saves) && !there(places.tekken7_data) && !there(places.tekken8_data) &&
              !there(places.cache / "ttt2") && !there(places.home / ".cache/ttt2") &&
              !there(places.home / ".local/share/ttt2"),
          "uninstall all: data, the default save folder and both helper caches");
    check(!there(places.packs / "kzm") && !there(places.packs / "shared") && !there(places.packs / "shared.part") &&
              !there(places.packs / "shared.old") && there(places.packs / "notapack"),
          "uninstall all: only packs and what they share");
    check(!there(places.packs / ".kzm.part") && !there(places.packs / ".dnc.old"),
          "uninstall all: the packs a killed importer was making");
    for (const char* name : {".kzm.tmp", ".kazumi.part", ".KZM.part", "kzm.part", ".kzm.part.bak", ".k.old"}) {
        check(there(places.packs / name / "readme.txt"), std::string("uninstall all: not the importer's: ") + name);
    }
    check(there(places.keyboard()), "uninstall all: the keyboard's keys kept");
    check(there(places.display()), "uninstall all: the display settings kept");

    // Not an install: nothing happens.
    write(root / "Games/other/file.txt", "x");
    r = uninstall(places, root / "Games/other", {});
    check(!r.refused.empty() && there(root / "Games/other/file.txt"), "uninstall: refuses a folder without markers");
    write(places.home / kMarker, "x");
    r = uninstall(places, places.home, {});
    check(!r.refused.empty(), "uninstall: refuses the home folder");
    check(!uninstall(places, "relative/folder", {}).refused.empty() && !uninstall(places, "/", {}).refused.empty(),
          "uninstall: refuses relative paths and the root");

    // A save folder of the player's ($TTT2_SAVE_DIR): only what the game
    // wrote goes, and the folder stays.
    const fs::path documents = root / "home/Documents";
    places.saves = documents;
    write(documents / "80000001/SAVE.DAT", "save");
    write(documents / "8000000a/SAVE.DAT", "save");
    write(documents / "common/x.dat", "save");
    write(documents / "notes.txt", "mine");
    write(documents / "8000000/mine.txt", "mine");
    write(documents / "8000000g/mine.txt", "mine");
    write(documents / "800000012/mine.txt", "mine");
    write(documents / "ABCDEF12", "a file of mine");
    write(outside / "common.txt", "mine");
    std::error_code ec;
    fs::create_directory_symlink(outside, documents / "12345678", ec);
    write(folder / kStarted, "x");
    r = uninstall(places, folder, {.saves = true});
    check(r.refused.empty() && r.problems.empty() && r.folder_removed, "uninstall saves: ran");
    check(!there(documents / "80000001") && !there(documents / "8000000a") && !there(documents / "common"),
          "uninstall saves: the game's");
    check(there(documents / "notes.txt") && there(documents / "8000000/mine.txt") &&
              there(documents / "8000000g/mine.txt") && there(documents / "800000012/mine.txt") &&
              there(documents / "ABCDEF12") && there(documents / "12345678") && there(outside / "common.txt"),
          "uninstall saves: nothing else");
    fs::remove_all(documents);
    fs::create_directories(documents / "80000001");
    write(folder / kStarted, "x");
    r = uninstall(places, folder, {.saves = true});
    check(r.problems.empty() && !there(documents / "80000001") && there(documents),
          "uninstall saves: the player's save folder stays when empty");

    places.saves = "";
    write(folder / kStarted, "x");
    r = uninstall(places, folder, {.saves = true});
    check(r.folder_removed && r.problems.size() == 1, "uninstall: no saves folder without its full path");
    places.saves = root / "home/.local/share/ttt2/save";

    // At the top of the folder only the install's own ".part" files go: a
    // download beside it, and lib/ (nothing makes it yet), are the user's.
    write(folder / kStarted, "x");
    write(folder / (std::string(kProgramName) + ".part"), "half");
    write(folder / "Movie.mkv.part", "a download");
    write(folder / "lib/libx.so", "theirs");
    r = uninstall(places, folder, {});
    check(r.problems.empty() && !r.folder_removed && r.left.size() == 2 && r.left[0] == "Movie.mkv.part" &&
              r.left[1] == "lib" && !there(folder / (std::string(kProgramName) + ".part")),
          "uninstall: other part files and lib/ stay");
    fs::remove_all(folder);

    // An install folder reached through a link: the folder and the link go.
    const fs::path real = root / "disk/TTT2", link = root / "Games/TTT2 link";
    fs::create_directories(real);
    fs::create_directory_symlink(real, link, ec);
    write(link / kProgramName, "program");
    write(link / "game/code/Tekken.rpx", "rpx");
    write(link / kMarker, "done");
    r = uninstall(places, link, {});
    check(r.refused.empty() && r.problems.empty() && r.folder_removed && !there(real) && !there(link),
          "uninstall: a linked folder (" + (r.problems.empty() ? r.refused : r.problems[0].text()) + ")");
    check(there(root / "disk") && there(root / "Games"), "uninstall: a linked folder's parents stay");

    // Not while the game runs from it: nothing is deleted.
    make();
    const pid_t pid = run_program(folder / kProgramName);
    r = uninstall(places, folder, {.saves = true, .characters = true});
    check(!r.refused.empty() && there(folder / "game/code/Tekken.rpx") && there(folder / kMarker) &&
              there(places.saves / "80000001/save.dat") && there(places.packs / "kzm/character.ini"),
          "uninstall: refused while the game runs (" + r.refused + ")");
    stop_program(pid);
    r = uninstall(places, folder, {});
    check(r.refused.empty() && !there(folder / "game"), "uninstall: once the game has ended");
}

// The output of `argv` run by /bin/sh (stdout and stderr) and its code; `env` set over this one's.
std::string run_shell(const std::vector<std::string>& argv, const std::vector<std::pair<std::string, std::string>>& env,
                      int* code) {
    int out[2];
    if (::pipe(out) != 0) return {};
    const pid_t pid = ::fork();
    if (pid == 0) {
        ::dup2(out[1], 1);
        ::dup2(out[1], 2);
        ::close(out[0]);
        ::close(out[1]);
        for (const auto& [name, value] : env) ::setenv(name.c_str(), value.c_str(), 1);
        std::vector<char*> args;
        for (const std::string& a : argv) args.push_back(const_cast<char*>(a.c_str()));
        args.push_back(nullptr);
        ::execv(args[0], args.data());
        ::_exit(127);
    }
    ::close(out[1]);
    std::string text;
    char buffer[4096];
    for (ssize_t n; (n = ::read(out[0], buffer, sizeof buffer)) > 0;) text.append(buffer, static_cast<size_t>(n));
    ::close(out[0]);
    int status = 0;
    ::waitpid(pid, &status, 0);
    *code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    return text;
}

std::string read_all(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    return {std::istreambuf_iterator<char>(in), {}};
}

// The way back: the AppImage an update replaces kept until the new one drew its first frame.
void test_way_back(const fs::path& root) {
    const fs::path folder = root / "way back";
    fs::create_directories(folder);
    const fs::path image = folder / "Golden_Fist_Launcher-x86_64.AppImage", previous = previous_file(image);
    check(previous == folder / ".Golden_Fist_Launcher-x86_64.AppImage.previous", "way back: its name");
    // The versions are scripts here: the old one says who it is and why it was opened.
    const std::string old_one = "#!/bin/sh\necho \"old one: rolled back from [$TTT2_LAUNCHER_ROLLED_BACK] after [$TTT2_LAUNCHER_AFTER]\"\n";
    const auto install = [&](const std::string& script) {
        write(image, script);
        ::chmod(image.c_str(), 0755);
    };
    install(old_one);
    check(keep_previous(image).empty() && read_all(previous) == old_one, "way back: kept");
    struct stat a = {}, b = {};
    check(::stat(image.c_str(), &a) == 0 && ::stat(previous.c_str(), &b) == 0 && a.st_ino == b.st_ino &&
              (b.st_mode & 0777) == 0755,
          "way back: a hard link, executable");
    check(keep_previous(image).empty(), "way back: kept again over an earlier one");
    const auto update = [&](const std::string& new_one) {
        install(old_one);
        check(keep_previous(image).empty(), "way back: kept before the update");
        write(update_file(image), new_one);
        ::chmod(update_file(image).c_str(), 0755);
        check(replace_appimage(update_file(image), image).empty() && read_all(previous) == old_one,
              "way back: the old one stays when the new one is put in place");
    };
    const std::vector<std::pair<std::string, std::string>> env = {{"TTT2_LAUNCHER_AFTER", "42"}};
    int code = -1;
    // A new version that crashes before its first frame: the old one is put back and opened, told which.
    update("#!/bin/sh\necho new one\nkill -SEGV $$\n");
    std::string said = run_shell(open_with_rollback(image, "9.9.9"), env, &code);
    check(code == 0 && said.find("new one") != std::string::npos &&
              said.find("version 9.9.9 ended (code 139) before its first frame") != std::string::npos &&
              said.find("old one: rolled back from [9.9.9] after [42]") != std::string::npos,
          "way back: a crash before the first frame puts the old one back and opens it: " + said);
    check(read_all(image) == old_one && !there(previous), "way back: the old one is back in place");
    // One that drew its first frame (it forgets the previous one) and crashes later: it stays.
    update("#!/bin/sh\nrm -f \"$(dirname \"$0\")/.$(basename \"$0\").previous\"\nkill -SEGV $$\n");
    said = run_shell(open_with_rollback(image, "9.9.9"), env, &code);
    check(code == 139 && said.find("old one") == std::string::npos && read_all(image) != old_one,
          "way back: after its first frame a crash changes nothing: " + said);
    // One that ends normally (handed over to a running launcher) or says no: it stays, the copy waits.
    for (const int exit : {0, 1}) {
        update("#!/bin/sh\necho new one; exit " + std::to_string(exit) + "\n");
        said = run_shell(open_with_rollback(image, "9.9.9"), env, &code);
        check(code == exit && said == "new one\n" && read_all(image) != old_one && there(previous),
              "way back: code " + std::to_string(exit) + " changes nothing: " + said);
    }
    // forget_previous (the new one after its first frame) and restore_previous (the new one without a window).
    forget_previous(image);
    check(!there(previous) && read_all(image) != old_one, "way back: forgotten");
    check(!restore_previous(image).empty(), "way back: nothing to put back");
    update("new");
    check(restore_previous(image).empty() && read_all(image) == old_one && !there(previous), "way back: put back");
    fs::remove_all(folder);
}

void test_release(const fs::path& root) {
    using V = std::vector<unsigned>;
    check(version_numbers("0.1.0") == V{0, 1, 0} && version_numbers("v0.2") == V{0, 2} &&
              version_numbers("V1.10.3") == V{1, 10, 3},
          "release: versions");
    for (const char* bad : {"", "v", "0.", ".1", "0..1", "1.2-rc1", "1.2 ", "x1", "1234567890"}) {
        check(!version_numbers(bad), std::string("release: not a version: '") + bad + "'");
    }
    check(compare_versions("0.1.1", "0.1.0") == 1 && compare_versions("0.2", "0.2.0") == 0 &&
              compare_versions("v0.10.0", "0.9.9") == 1 && compare_versions("0.1.0", "1.0") == -1 &&
              !compare_versions("next", "0.1.0"),
          "release: comparing");
    // An install's program from an older launcher than the kit: Play and adding characters wait for its Update
    // (testers played the 0.6.2 importer's packs on a game an 0.5.1 launcher built). The same version (another
    // commit), a newer one, or one not known never wait.
    check(launcher_version("0.6.2-1cab8c68f39b") == "0.6.2" && launcher_version("0.6.2") == "0.6.2" &&
              launcher_version("").empty(),
          "release: a kit's launcher version");
    check(built_older("0.5.1-79795183ad3a", "0.6.2-d9258007cb1c") && built_older("0.5.1", "0.6.2-d9258007cb1c") &&
              built_older("0.9.1-aaaaaaa", "0.10.0"),
          "release: a program an older launcher built");
    check(!built_older("0.6.2-d9258007cb1c", "0.6.2-d9258007cb1c") &&
              !built_older("0.6.2-0123456789ab", "0.6.2-d9258007cb1c") && !built_older("0.6.2", "0.6.2-d9258007cb1c") &&
              !built_older("0.7.0-aaaaaaa", "0.6.2-d9258007cb1c") && !built_older("0.10.0", "0.9.1"),
          "release: a program of this launcher's version or a newer one");
    check(!built_older("", "0.6.2-d9258007cb1c") && !built_older("0.5.1", "") && !built_older("next", "0.6.2") &&
              !built_older("0.5.1", "next"),
          "release: a program whose launcher is not known");

    // GitHub's answers: a release, none yet, the hourly limit.
    const std::string asset = R"({"name": "%s", "state": "uploaded", "size": 2652664,
        "digest": "sha256:9F86D081884C7D659A2FEAA0C55AD015A3BF4F1B2B0B822CD15D6C15B0F00A08",
        "browser_download_url": "https://github.com/o/r/releases/download/v0.2.0/%s"})";
    const auto release_json = [&](std::initializer_list<const char*> names, const char* tag = "v0.2.0") {
        std::string assets;
        for (const char* name : names) {
            std::string a = asset;
            for (size_t at; (at = a.find("%s")) != std::string::npos;) a.replace(at, 2, name);
            assets += (assets.empty() ? "" : ",") + a;
        }
        return std::string(R"({"tag_name": ")") + tag +
               R"(", "html_url": "https://github.com/o/r/releases/tag/v0.2.0", "draft": false, "assets": [)" + assets +
               "]}";
    };
    ReleaseAnswer a = parse_release(release_json({"x.AppImage.zsync", "TTT2-aarch64.AppImage", "TTT2-x86_64.AppImage"}));
    check(a.release && a.release->version == "0.2.0" && a.release->tag == "v0.2.0" &&
              a.release->page == "https://github.com/o/r/releases/tag/v0.2.0" &&
              a.release->asset == "TTT2-x86_64.AppImage" && a.release->size == 2652664 &&
              a.release->url == "https://github.com/o/r/releases/download/v0.2.0/TTT2-x86_64.AppImage" &&
              a.release->sha256 == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
          "release: its x86-64 AppImage");
    a = parse_release(release_json({"Tekken.AppImage"}, "0.3"));
    check(a.release && a.release->version == "0.3" && a.release->asset == "Tekken.AppImage", "release: the only one");
    a = parse_release(release_json({"a.AppImage", "b.AppImage"}));
    check(!a.release && !a.none && a.error == "version 0.2.0 has no AppImage to download", "release: which one");
    a = parse_release(release_json({"notes.txt", "TTT2-aarch64.AppImage"}));
    check(!a.release && a.error == "version 0.2.0 has no AppImage to download", "release: none for this PC");
    a = parse_release(release_json({"TTT2-x86_64.AppImage"}, "nightly"));
    check(!a.release && a.error.find("is not named as a version") != std::string::npos, "release: tag not a version");
    a = parse_release(R"({"message": "Not Found", "documentation_url": "https://docs.github.com", "status": "404"})");
    check(a.none && !a.release && a.error.empty(), "release: none published");
    a = parse_release(R"j({"message": "API rate limit exceeded for 192.0.2.1. (But here's the good news: ...)"})j");
    check(!a.none && a.error.find("try again later") != std::string::npos, "release: rate limit");
    a = parse_release("<html>");
    check(!a.none && !a.release && a.error.starts_with("GitHub's answer is not readable"), "release: not JSON");

    // The AppImage it runs from: only with the program inside $APPDIR.
    const fs::path image = root / "Golden_Fist_Launcher-x86_64.AppImage", mount = root / "mount";
    write(image, "old");
    const fs::path program = mount / "usr/bin/ttt2-launcher";
    check(running_appimage(program, image.c_str(), mount.c_str()) == image, "release: running AppImage");
    check(!running_appimage(root / "elsewhere/ttt2-launcher", image.c_str(), mount.c_str()),
          "release: another AppImage's variables");
    check(!running_appimage(program, nullptr, mount.c_str()) && !running_appimage(program, image.c_str(), "") &&
              !running_appimage(program, "relative.AppImage", mount.c_str()) &&
              !running_appimage(program, (root / "gone.AppImage").c_str(), mount.c_str()),
          "release: no AppImage");
    check(update_file(image) == root / ".Golden_Fist_Launcher-x86_64.AppImage.update", "release: update file");
    check(cannot_replace(image).empty() && !cannot_replace(root / "missing/x.AppImage").empty(),
          "release: folder writable");

    // The download: an AppImage (as checked), made executable as the old
    // one, then renamed over it.
    const fs::path update = update_file(image);
    std::string head(32, '\0');
    head.replace(0, 4, "\177ELF");
    head[8] = 'A', head[9] = 'I', head[10] = 2, head[18] = 0x3e;
    const std::string written = head + "new";
    write(update, written);
    check(is_appimage(update) && !is_appimage(image) && !is_appimage(root / "missing"), "release: is an AppImage");
    head[10] = 1;
    write(root / "type1", head);
    check(!is_appimage(root / "type1"), "release: type 1 is not");
    ::chmod(image.c_str(), 0750);
    check(make_executable(update, image).empty(), "release: made executable");
    struct stat st = {};
    check(::stat(update.c_str(), &st) == 0 && (st.st_mode & 07777) == 0750, "release: the old one's permissions");
    check(replace_appimage(update, image).empty() && !there(update), "release: replaced");
    std::ifstream in(image, std::ios::binary);
    const std::string now((std::istreambuf_iterator<char>(in)), {});
    check(now == written, "release: the new one's bytes");
    check(!replace_appimage(update, image).empty(), "release: nothing to replace with");
    test_way_back(root);

    check(version_in("ttt2-launcher 0.2.0\n") == "0.2.0" && version_in("ttt2-launcher v1.0\n") == "1.0" &&
              version_in("Gtk-WARNING\nttt2-launcher 0.3.1") == "0.3.1" && version_in("usage: ttt2-launcher").empty(),
          "release: --version's answer");

    const Downloader curl{"/usr/bin/curl", true}, wget{"/usr/bin/wget", false};
    auto argv = download_command(curl, "https://x/latest", true, {}, "ttt2-launcher/0.1.0");
    check(argv.front() == "/usr/bin/curl" && argv.back() == "https://x/latest" &&
              std::find(argv.begin(), argv.end(), "-f") == argv.end() &&
              std::find(argv.begin(), argv.end(), "Accept: application/vnd.github+json") != argv.end(),
          "release: curl asks the API");
    argv = download_command(curl, "https://x/a.AppImage", false, "/d/.a.update", "ua");
    check(std::find(argv.begin(), argv.end(), "-f") != argv.end() &&
              std::find(argv.begin(), argv.end(), "/d/.a.update") != argv.end(),
          "release: curl downloads");
    argv = download_command(wget, "https://x/latest", true, {}, "ua");
    check(argv.front() == "/usr/bin/wget" && std::find(argv.begin(), argv.end(), "--content-on-error") != argv.end() &&
              std::find(argv.begin(), argv.end(), "-") != argv.end(),
          "release: wget asks the API");

    check(process_alive(::getpid()) && !process_alive(0) && !process_alive(-1), "release: alive");
    const pid_t child = ::fork();
    if (child == 0) ::_exit(0);
    // (Ended, not yet waited for: a zombie, which has ended.)
    for (int i = 0; i < 200 && process_alive(child); ++i) std::this_thread::sleep_for(std::chrono::milliseconds(10));
    check(!process_alive(child), "release: a zombie has ended");
    ::waitpid(child, nullptr, 0);
    check(!process_alive(child), "release: gone");
}

} // namespace

int main(int argc, char** argv) {
    const fs::path base = fs::absolute(argc > 1 ? fs::path(argv[1]) : fs::temp_directory_path()).lexically_normal();
    fs::create_directories(base);
    std::string pattern = (base / "launcher_core_test.XXXXXX").string();
    if (!mkdtemp(pattern.data())) {
        std::printf("FAIL cannot make a folder in %s\n", base.c_str());
        return 1;
    }
    const fs::path root = pattern;
    test_json();
    test_status();
    test_protocol();
    test_saved_ownership(root / "owned");
    test_paths(root / "paths");
    test_running(root / "running");
    test_system();
    test_compiler(root / "compiler");
    test_actions();
    test_display(root / "display");
    test_game_ini(root / "game");
    test_uninstall(root / "uninstall");
    test_release(root / "release");
    std::error_code ec;
    fs::remove_all(root, ec);
    if (g_failures == 0) std::printf("launcher_core_test: all passed\n");
    return g_failures == 0 ? 0 : 1;
}
