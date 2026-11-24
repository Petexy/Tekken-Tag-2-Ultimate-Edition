// launcher/backend: the model's programs through core's processes (a real
// one: the system's shell), and Windows' `main.py --query` answers read from
// recorded JSON (tests/windows/*.json).

#include "starter.h"

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

} // namespace

int main(int argc, char** argv) {
    const fs::path data = argc > 1 ? fs::path(argv[1]) : fs::path("tests");
    const fs::path scratch = (argc > 2 ? fs::path(argv[2]) : fs::temp_directory_path()) / "backend_test.scratch";
    std::error_code ec;
    fs::remove_all(scratch, ec);
    fs::create_directories(scratch);
    (void)data;
    test_starter(scratch);
    fs::remove_all(scratch, ec);
    std::printf("%d checks, %d failed\n", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
