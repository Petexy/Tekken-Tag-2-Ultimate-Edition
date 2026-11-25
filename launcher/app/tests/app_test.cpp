// The launcher program's parts without a window: the in-app browser's folders and the install's steps.

#include <algorithm>
#include "browser.h"
#include "steps.h"

#include <cstdio>
#include <fstream>
#include <string>

namespace {

int failures = 0;

void check(bool ok, const std::string& what) {
    if (!ok) {
        ++failures;
        std::fprintf(stderr, "FAILED: %s\n", what.c_str());
    }
}

void test_browser(const std::filesystem::path& scratch) {
    using namespace launcher::app;
    namespace fs = std::filesystem;
    std::error_code ec;
    fs::remove_all(scratch, ec);
    fs::create_directories(scratch / "b" / "Zeta", ec);
    fs::create_directories(scratch / "b" / "alpha", ec);
    fs::create_directories(scratch / "b" / ".hidden", ec);
    std::ofstream(scratch / "b" / "Game.WUA") << "x";
    std::ofstream(scratch / "b" / "notes.txt") << "hello";
    std::string error;
    const auto all = list_folder(scratch / "b", false, &error);
    check(error.empty(), "list_folder reads the folder");
    check(all.size() == 5, "up, two folders, two files (hidden left out): " + std::to_string(all.size()));
    if (all.size() == 5) {
        check(all[0].kind == Entry::Kind::kUp && all[0].name == ".. (up to " + scratch.filename().string() + ")",
              "up first: " + all[0].name);
        check(all[1].name == "alpha" && all[2].name == "Zeta", "folders by name without case");
        check(all[3].name == "Game.WUA" && all[3].wua, "a .wua in any case");
        check(all[4].name == "notes.txt" && !all[4].wua && all[4].size == 5, "a file with its size");
        check(all[1].items == 0, "an empty folder holds 0 items");
    }
    const auto folders = list_folder(scratch / "b", true);
    check(folders.size() == 3, "folders only");
    const auto root = list_folder("/", true);
    check(root.empty() || root[0].kind != Entry::Kind::kUp, "no up at /");
    std::string missing;
    list_folder(scratch / "none", false, &missing);
    check(!missing.empty(), "an error for a folder that is not there");
    check(size_text(15'800'000'000ull) == "15.8 GB", "size_text GB: " + size_text(15'800'000'000ull));
    check(size_text(340'000'000ull) == "340 MB", "size_text MB");
    check(size_text(2'000) == "2 KB", "size_text KB");
    check(size_text(5) == "5 B", "size_text B");
    check(start_folder(scratch / "b" / "gone" / "deeper", {}) == scratch / "b", "start_folder: the nearest there");
    const auto ps = places(scratch, "");
#ifdef _WIN32
    // (Windows: the drives last, C: always.)
    check(ps.size() >= 2 && ps.front().id == "home" && ps.back().id.starts_with("drive:"), "places: Home first, drives last");
    check(std::any_of(ps.begin(), ps.end(), [](const Place& p) { return p.id == "drive:C"; }), "places: drive C:");
#else
    check(ps.size() >= 2 && ps.front().id == "home" && ps.back().id == "root", "places: Home first, Computer last");
    // REVIEW2_app #6: hidden names listed only when asked, counted the same way; counts left for later.
    const auto hidden = list_folder(scratch / "b", false, nullptr, true);
    check(hidden.size() == 6 && hidden[1].name == ".hidden", "hidden folders listed when asked");
    fs::create_directories(scratch / "b" / "alpha" / ".git", ec);
    std::ofstream(scratch / "b" / "alpha" / "readme") << "x";
    const auto counted = list_folder(scratch / "b", false, nullptr, false);
    check(counted.size() == 5 && counted[1].items == 1, "a folder's hidden entries are not counted");
    check(count_items(scratch / "b" / "alpha", true) == 2 && count_items(scratch / "b" / "alpha") == 1,
          "count_items with and without hidden ones");
    const auto later = list_folder(scratch / "b", false, nullptr, false, false);
    check(later.size() == 5 && later[1].items == kNotCounted && later[3].items == -1, "counts left for later");
    // The places a file manager hides: Steam's, Flatpak apps', Wine prefixes (a folder with drive_c).
    const fs::path home = scratch / "home";
    for (const char* d : {".local/share/Steam/steamapps", ".var/app/com.valvesoftware.Steam/data/Steam", ".wine/drive_c",
                          ".local/share/wineprefixes/tricks/drive_c", "Games/lutris-ttt2/drive_c", "Games/not-a-prefix",
                          "Faugus/faugus-one/drive_c", "Downloads"})
        fs::create_directories(home / d, ec);
    const auto found = places(home, "");
    std::string ids;
    // (The drives mounted on the machine running the test are left out.)
    for (const Place& p : found)
        if (!p.id.starts_with("drive:")) ids += p.id.substr(0, p.id.starts_with("wine:") ? 5 : std::string::npos) + ",";
    check(ids == "home,downloads,games,steam,steam-flatpak,flatpak,wine:,wine:,wine:,wine:,root,", "places: " + ids);
    std::vector<std::string> wines;
    for (const Place& p : found)
        if (p.kind == "Wine") wines.push_back(p.name);
    check(wines == std::vector<std::string>{"Wine", "faugus-one", "lutris-ttt2", "tricks"}, "places: Wine prefixes by name");
    check(found[3].path == home / ".local/share/Steam" && found[5].path == home / ".var/app", "places: Steam, Flatpak");
    check(wine_prefixes(home, 2).size() == 2, "wine_prefixes: at most the limit");
#endif
}

void test_steps() {
    using namespace launcher::app;
    const std::vector<std::string> log = {"ttt2-build install game.wua folder", "@step check Checking the game",
                                          "@progress 3 3", "@step compile Compiling the game's code", "@progress 1705 2310",
                                          "some compiler line"};
    auto s = build_steps(log, false, false);
    check(s.size() == 7, "seven steps");
    check(s[0].state == StepLine::State::kDone && s[1].state == StepLine::State::kDone, "steps before are done");
    check(s[3].state == StepLine::State::kCurrent && s[3].name == "Compiling" &&
              s[3].text == "Compiling the game's code",
          "the current step, its builder's words");
    check(s[3].count == "1,705 of 2,310", "its count: " + s[3].count);
    check(s[3].fraction > 0.73 && s[3].fraction < 0.74, "its fraction");
    check(s[4].state == StepLine::State::kPending, "later ones pending");
    check(current_step(s) == 4, "step 4 of 7");
    auto failed = build_steps(log, true, false);
    check(failed[3].state == StepLine::State::kFailed && current_step(failed) == 4, "stopped at step 4");
    auto done = build_steps(log, true, true);
    bool all = true;
    for (const auto& x : done) all = all && x.state == StepLine::State::kDone;
    check(all && current_step(done) == 7, "all done");
    auto none = build_steps({}, false, false);
    check(current_step(none) == 0, "none began");
    auto extra = build_steps({"@step shaders Preparing shaders"}, false, false);
    check(extra.size() == 8 && extra[7].id == "shaders" && current_step(extra) == 8, "a step not known is added");
}

} // namespace

void test_bootstrap() {
    using launcher::app::bootstrap_progress;
    check(bootstrap_progress("").step.empty(), "bootstrap: nothing yet");
    const std::string old = "@step check Checking\r\n@step download Downloading\r\n####  40.0%\r\n@step ready Ready\r\n";
    const std::string now = old + "Launcher runtime ready\r\n@step check Checking the launcher's tools\r\n"
                                  "@step download Downloading Python for the launcher\r\n"
                                  "\r#####                12.5%\r##########           50,0%";
    const auto p = bootstrap_progress(now);
    check(p.step == "download" && p.text == "Downloading Python for the launcher", "bootstrap: the last run's step");
    check(p.download > .49 && p.download < .51, "bootstrap: curl's last percentage (" + std::to_string(p.download) + ")");
    check(p.fraction > .4 && p.fraction < .5, "bootstrap: the whole's part");
    const auto r = bootstrap_progress(now + "\r\n@step verify Checking the download\r\n@step unpack Unpacking\r\n");
    check(r.step == "unpack" && r.fraction > .85 && r.fraction < .9, "bootstrap: unpacking");
}

int main(int argc, char** argv) {
    const std::filesystem::path scratch = argc > 1 ? argv[1] : "app-test";
    test_bootstrap();
    test_browser(scratch);
    test_steps();
    if (failures) {
        std::fprintf(stderr, "%d failed\n", failures);
        return 1;
    }
    std::printf("launcher_app_test: all passed\n");
    return 0;
}
