// launcher/backend: the model's programs through core's processes (a real
// one: the system's shell), and Windows' `main.py --query` answers read from
// recorded JSON (tests/windows/*.json).

#include "builders.h"
#include "model.h"
#include "starter.h"
#include "utf8_path.h"
#include "windows_backend.h"
#ifdef _WIN32
#include "win32.h"

#include <windows.h>

#include <shellapi.h>
#endif

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <thread>

namespace {

using namespace launcher;

int g_failures = 0, g_checks = 0;

void check(bool ok, const std::string& what) {
    ++g_checks;
    if (!ok) {
        std::printf("FAIL %s\n", what.c_str());
        std::fflush(stdout);
        ++g_failures;
    }
}

template <typename A, typename B> void check_eq(const A& a, const B& b, const std::string& what) {
    std::ostringstream text;
    text << what << ": got [" << a << "], wanted [" << b << "]";
    check(a == b, text.str());
}

std::string read_file(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    std::stringstream s;
    s << in.rdbuf();
    return s.str();
}

void test_starter(const fs::path& scratch) {
    ProcessHost host;
    backend::ProcessStarter starter(host);
    model::Command c;
#ifdef _WIN32
    c.argv = {"cmd.exe", "/d", "/c", "echo one& echo two 1>&2& exit /b 4"};
#else
    c.argv = {"sh", "-c", "echo one; echo two >&2; exit 4"};
#endif
    c.log_file = scratch / "logs" / "task.log"; // (a task's lines also go there; its folder is made)
    std::vector<std::string> out, err;
    int code = -1;
    std::string error;
    auto job = starter.start(c,
                             {[&](const std::string& line, bool is_error) {
                                  std::string l = line;
                                  while (!l.empty() && l.back() == ' ') l.pop_back(); // (cmd's echo)
                                  (is_error ? err : out).push_back(l);
                              },
                              [&](int c2) { code = c2; }},
                             &error);
    check(job != nullptr, "starter: started (" + error + ")");
    for (int i = 0; i < 200 && code == -1; ++i) {
        host.wait(0.05);
        host.pump();
    }
    check_eq(code, 4, "starter: exit code");
    check(out.size() == 1 && out[0] == "one", "starter: standard output");
    check(err.size() == 1 && err[0] == "two", "starter: standard error");
    const std::string log = read_file(c.log_file);
    check(log.find("one") != std::string::npos && log.find("two") != std::string::npos, "starter: the task's log");

    model::Command game;
    game.mode = model::Command::Mode::kDetached;
    game.log_file = scratch / "cache" / "game.log";
#ifdef _WIN32
    game.argv = {"cmd.exe", "/d", "/c", "echo played"};
#else
    game.argv = {"sh", "-c", "echo played"};
#endif
    bool lines = false;
    code = -1;
    auto played = starter.start(game, {[&](const std::string&, bool) { lines = true; }, [&](int c2) { code = c2; }},
                                &error);
    check(played != nullptr, "starter: the game started (" + error + ")");
    for (int i = 0; i < 200 && code == -1; ++i) {
        host.wait(0.05);
        host.pump();
    }
    check_eq(code, 0, "starter: the game's end");
    check(!lines, "starter: the game's output is not read");
    check(read_file(game.log_file).find("played") != std::string::npos, "starter: the game's output in its log");

    const ProcessSpec spec = backend::process_spec(
        model::Command{{"a"}, {{"K", "V"}}, "/f", "/l", "/c", model::Command::Mode::kSelfUpdate});
    check(spec.mode == ProcessSpec::Mode::kSelfUpdate && spec.cancel_file == "/c" && spec.output == "/l" &&
              spec.cwd == "/f" && spec.env.size() == 1,
          "process_spec: every field");
}

// Windows' answers (tests/windows): state-installed, state-no-exe, check-*, save-settings* are main.py --query's
// whole output in a scratch layout (its folders written /w, the project /w/repo; a first line added: the answer is
// the last one); state-windows is state-installed with Windows' paths, a commit and a test branch; state-protocol-2
// and state-error are made by hand.
void test_windows_answers(const fs::path& data) {
    const auto fixture = [&](const char* name) { return read_file(data / "windows" / name); };
    backend::QueryError error;
    auto state = backend::parse_windows_state(fixture("state-installed.txt"), &error);
    check(state.has_value(), "state: read (" + error.code + " " + error.text + ")");
    if (!state) return;
    const std::string game = "/w/Games/Jos\xc3\xa9 TTT2";
    check(state->state.play.has_value(), "state: Play starts the game");
    if (state->state.play) {
        const model::Command& play = *state->state.play;
        check(play.argv.size() == 1 && play.argv[0] == game + "/TTT2 Ultimate.exe", "state: the game's program");
        check_eq(path_utf8_generic(play.cwd), game, "state: its folder");
        check_eq(play.env.at("TTT2_DATA_DIR"), std::string("/w/appdata/TTT2Ultimate"), "state: its data folder");
        check_eq(path_utf8_generic(play.log_file), std::string("/w/appdata/TTT2Ultimate/logs/game-latest.log"),
                 "state: its log");
        check(play.mode == model::Command::Mode::kDetached && play.cancel_file.empty(), "state: on its own");
    }
    check_eq(state->state.folders.at("install"), game, "state: Settings > Folders");
    check_eq(state->state.folders.size(), size_t(7), "state: every folder");
    check_eq(path_utf8_generic(state->state.root), std::string("/w/repo"), "state: root");
    check_eq(path_utf8_generic(state->state.config), std::string("/w/local/windows-launcher.json"), "state: config");
    check_eq(path_utf8(state->state.latest_log.filename()), std::string("import-20261124-140000-1.log"),
             "state: the newest log");
    check_eq(state->installed_by, std::string("0.7.1-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"), "state: the kit's form");
    check_eq(state->files_id, std::string("0.8.0"), "state: files without a commit");
    check(!state->exe.empty() && !state->icon.empty(), "state: the release .exe and the icon");
    check_eq(path_utf8(state->keyboard_file.filename()), std::string("keyboard.ini"), "state: keyboard.ini");
    model::Facts facts;
    backend::apply_windows_state(*state, facts);
    check(facts.install.state == InstallState::kInstalled && path_utf8_generic(facts.install.folder) == game,
          "facts: the install");
    check(facts.self_update && facts.icon && facts.game_built == state->installed_by && facts.this_build == "0.8.0",
          "facts: updates itself, icon, builds");
    check_eq(facts.build_commit, state->state.commit, "facts: the commit");

    state = backend::parse_windows_state(fixture("state-no-exe.txt"), &error);
    check(state && !state->state.play && state->state.play_problem == "exe" && state->exe.empty(),
          "state: the game's program missing");
    state = backend::parse_windows_state(fixture("state-windows.txt"), &error);
    check(state && state->files_id == "0.8.0-" + std::string(40, 'c') && state->state.branch == "launcher-overhaul",
          "state: a test build's files");
    check(state && state->state.cannot_replace == "Access is denied", "state: the .exe's folder");
    check(state && state->state.play && state->state.play->env.at("LOCALAPPDATA") == "D:\\Data",
          "state: LOCALAPPDATA for a data folder elsewhere");
    check(state && state->state.play &&
              state->state.play->argv[0] == "C:\\Users\\Jos\xc3\xa9\\AppData\\Local\\Games\\Jos\xc3\xa9 TTT2\\TTT2 Ultimate.exe",
          "state: a Windows path with letters beyond ASCII");
    model::Facts windows_facts;
    if (state) backend::apply_windows_state(*state, windows_facts);
    check_eq(windows_facts.this_build, "0.8.0-" + std::string(40, 'c'), "facts: a test build's id");

    check(!backend::parse_windows_state(fixture("state-protocol-2.txt"), &error) && error.code == "protocol" &&
              error.text == "2",
          "state: another protocol refused");
    check(!backend::parse_windows_state(fixture("state-error.txt"), &error) && error.code == "error" &&
              error.text == "Permission denied",
          "state: a failure's reason");
    check(!backend::parse_windows_state("Traceback (most recent call last):\n  oops\n", &error) &&
              error.code == "answer",
          "state: no answer");

    auto problem = backend::parse_check(fixture("check-import.txt"), &error);
    check(problem && problem->code == "no_fighters", "check: the problem's code");
    problem = backend::parse_check(fixture("check-setup.txt"), &error);
    check(problem && problem->code == "inputs", "check: setup's inputs");
    problem = backend::parse_check("{\"problem\": {\"code\": \"\", \"what\": \"\", \"letters\": \"\", \"path\": \"\"}, "
                                   "\"protocol\": 1}\n",
                                   &error);
    check(problem && problem->code.empty(), "check: none");

    auto saved = backend::parse_save_settings(fixture("save-settings.txt"), &error);
    check(saved && saved->problem.code.empty() && saved->folders.at("packs") == "/w/packs", "save-settings: saved");
    saved = backend::parse_save_settings(fixture("save-settings-name.txt"), &error);
    check(saved && saved->problem.code == "data_name" && saved->problem.what == "data", "save-settings: refused");

    auto release = backend::parse_release_query(
        "{\"newer\": {\"version\": \"0.9.0\", \"tag\": \"v0.9.0\", \"page\": \"p\", \"asset\": \"a.exe\", \"url\": "
        "\"u\", \"size\": 123, \"sha256\": \"ab\"}, \"none\": false, \"error\": \"\", \"protocol\": 1}",
        &error);
    check(release && release->release && release->release->version == "0.9.0" && release->release->size == 123,
          "release: newer");
    release = backend::parse_release_query("{\"newer\": null, \"none\": false, \"error\": \"no .exe in it\", "
                                           "\"protocol\": 1}",
                                           &error);
    check(release && !release->release && release->error == "no .exe in it", "release: GitHub's reason");
    check(!backend::parse_release_query("{\"error\": \"timed out\", \"protocol\": 1}", &error) &&
              error.text == "timed out",
          "release: could not ask");
    check_eq(backend::kit_id("0.8.0 abc"), std::string("0.8.0-abc"), "kit id");
}

// A José in every folder: the players' own Windows builds (llvm-mingw, libc++) made path::string()
// and path(std::string) in the ANSI code page, so Python and main.py were started with broken names. Here this test
// program, copied into such a folder as "python", is started as the model's --query and worker commands are: it
// says the arguments it got and whether the script they name is there, as Python would open it.
#ifdef _WIN32
std::vector<std::string> own_arguments() {
    int n = 0;
    LPWSTR* wide = CommandLineToArgvW(GetCommandLineW(), &n);
    std::vector<std::string> args;
    for (int i = 0; i < n; ++i) args.push_back(win32::narrow(wide[i]));
    LocalFree(wide);
    return args;
}

fs::path own_program() {
    std::wstring self(32768, L'\0');
    self.resize(GetModuleFileNameW(nullptr, self.data(), 32768));
    return fs::path(self);
}
#else
fs::path own_program() { return fs::read_symlink("/proc/self/exe"); }
#endif

// The stand-in "python": `python -u SCRIPT ...` -> one line per argument, then whether SCRIPT is there.
int python_stand_in(const std::vector<std::string>& args) {
    for (size_t i = 0; i < args.size(); ++i) std::printf("ARG %zu %s\n", i, args[i].c_str());
    std::error_code ec;
    std::printf("SCRIPT %s\n", args.size() > 2 && fs::exists(utf8_path(args[2]), ec) ? "there" : "missing");
    return 0;
}

std::vector<std::string> run_lines(const model::Command& c, int* code) {
    ProcessHost host;
    backend::ProcessStarter starter(host);
    std::vector<std::string> out;
    std::string error;
    *code = -1;
    auto job = starter.start(c, {[&](const std::string& line, bool is_error) { if (!is_error) out.push_back(line); },
                                 [&](int c2) { *code = c2; }},
                             &error);
    check(job != nullptr, "José: started " + (c.argv.empty() ? std::string() : c.argv[0]) + " (" + error + ")");
    for (int i = 0; i < 400 && job && *code == -1; ++i) {
        host.wait(0.05);
        host.pump();
    }
    return out;
}

void test_non_ascii_root(const fs::path& scratch) {
    const std::string jose = "Jos\xc3\xa9";
    const fs::path root = fs::absolute(scratch / utf8_path(jose + " TTT2")); // (the commands run in it)
    const fs::path local = root / "local";
    fs::create_directories(root / "launcher" / "windows");
    fs::create_directories(local / "logs");
    std::ofstream(root / "launcher" / "windows" / "main.py") << "# the stand-in's script\n";
    const fs::path python = root / "python" / utf8_path(jose + (fs::path::preferred_separator == '\\' ? ".exe" : ""));
    fs::create_directories(python.parent_path());
    std::error_code ec;
    fs::copy_file(own_program(), python, fs::copy_options::overwrite_existing, ec);
    check(!ec, "José: the stand-in copied (" + ec.message() + ")");

    model::Facts facts;
    facts.python = python;
    facts.windows.root = root;
    facts.windows.build = root / "build-windows-tools";
    facts.windows.config = local / "windows-launcher.json";
    facts.windows.logs = local / "logs";
    model::WindowsCommands commands;
    commands.stamp = [] { return std::string("20261124-140000-1"); };

    const model::Command query = commands.query(facts, "state");
    check_eq(query.argv.at(0), path_utf8(python), "José: --query's python, in UTF-8");
    check_eq(query.argv.at(2), path_utf8(root / "launcher/windows/main.py"), "José: --query's main.py");
    check(query.argv.at(4).find(jose) != std::string::npos && query.argv.at(6).find(jose) != std::string::npos,
          "José: --build-dir and --config in UTF-8");
    int code = -1;
    std::vector<std::string> said = run_lines(query, &code);
    check_eq(code, 0, "José: --query ended");
    const auto arg = [&](size_t i) {
        const std::string head = "ARG " + std::to_string(i) + " ";
        for (const std::string& l : said)
            if (l.rfind(head, 0) == 0) return l.substr(head.size());
        return std::string("(none)");
    };
    check_eq(arg(2), query.argv[2], "José: python got main.py's name");
    check_eq(arg(4), query.argv[4], "José: and the build folder's");
    check_eq(arg(6), query.argv[6], "José: and the settings file's");
    check(std::find(said.begin(), said.end(), "SCRIPT there") != said.end(), "José: python finds main.py");

    const model::Command worker = commands.worker_command(facts, "build", {}, "");
    check_eq(worker.argv.at(10), path_utf8(worker.cancel_file), "José: the worker's cancel file");
    check(worker.argv[10].find(jose) != std::string::npos && path_utf8(worker.log_file).find(jose) != std::string::npos,
          "José: the worker's files in UTF-8");
    said = run_lines(worker, &code);
    check_eq(arg(10), worker.argv[10], "José: python got the cancel file's name");
    check(std::find(said.begin(), said.end(), "SCRIPT there") != said.end(), "José: the worker's main.py found");

    facts.install.state = InstallState::kInstalled;
    facts.install.folder = utf8_path("C:/Users/" + jose + "/Games/Tekken Tag Tournament 2");
    check(model::game_view(facts).folder.find(jose) != std::string::npos, "José: the game's folder as shown");
}

} // namespace

int main(int argc, char** argv) {
#ifdef _WIN32
    if (const std::vector<std::string> args = own_arguments(); args.size() > 1 && args[1] == "-u")
        return python_stand_in(args);
#else
    if (argc > 1 && std::string(argv[1]) == "-u") return python_stand_in(std::vector<std::string>(argv, argv + argc));
#endif
    const fs::path data = argc > 1 ? fs::path(argv[1]) : fs::path("tests");
    const fs::path scratch = (argc > 2 ? fs::path(argv[2]) : fs::temp_directory_path()) / "backend_test.scratch";
    std::error_code ec;
    fs::remove_all(scratch, ec);
    fs::create_directories(scratch);
    test_starter(scratch);
    test_windows_answers(data);
    test_non_ascii_root(scratch);
    fs::remove_all(scratch, ec);
    std::printf("%d checks, %d failed\n", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
