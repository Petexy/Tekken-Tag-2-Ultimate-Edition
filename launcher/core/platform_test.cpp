// The launcher's platform layer with real programs: subprocess.h (lines,
// exit codes, Cancel, a task's group or job, the launcher's end, files left
// open, the game started on its own, Windows' quoting), on Linux and on
// Windows (under Wine when built with MinGW). The programs are this test
// itself, started as `platform_test child <what> ...`.

#include "subprocess.h"

#ifdef _WIN32
#include "win32.h"
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shellapi.h>

#include <fcntl.h>
#include <io.h>
#else
#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>
#endif

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <iostream>
#include <sstream>
#include <thread>

namespace {

using namespace launcher;
using namespace std::chrono_literals;
using Clock = std::chrono::steady_clock;

double seconds_since(Clock::time_point t) { return std::chrono::duration<double>(Clock::now() - t).count(); }

int g_failures = 0;
int g_checks = 0;
fs::path g_self;  // this program
fs::path g_root;  // a scratch folder of its own

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

void sleep_for(double seconds) { std::this_thread::sleep_for(std::chrono::duration<double>(seconds)); }

bool alive(int64_t pid) {
#ifdef _WIN32
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, static_cast<DWORD>(pid));
    if (!h) return false;
    const bool running = WaitForSingleObject(h, 0) == WAIT_TIMEOUT;
    CloseHandle(h);
    return running;
#else
    std::ifstream in("/proc/" + std::to_string(pid) + "/stat");
    std::string stat;
    if (!std::getline(in, stat)) return false;
    const size_t close = stat.rfind(')');
    return close != std::string::npos && close + 2 < stat.size() && stat[close + 2] != 'Z' && stat[close + 2] != 'X';
#endif
}

bool gone_within(int64_t pid, double seconds) {
    for (double t = 0; t < seconds; t += 0.05) {
        if (!alive(pid)) return true;
        sleep_for(0.05);
    }
    return !alive(pid);
}

void kill_pid(int64_t pid) {
#ifdef _WIN32
    if (HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, static_cast<DWORD>(pid))) {
        TerminateProcess(h, 9);
        CloseHandle(h);
    }
#else
    ::kill(static_cast<pid_t>(pid), SIGKILL);
#endif
}

int64_t own_pid() {
#ifdef _WIN32
    return GetCurrentProcessId();
#else
    return ::getpid();
#endif
}

// ---------------------------------------------------------------- the child programs

void out(const std::string& text) {
    std::fwrite(text.data(), 1, text.size(), stdout);
    std::fflush(stdout);
}

// Starts this program again as `child <args>` on its own (not through the code under test), for grandchildren.
int64_t start_grandchild(const std::vector<std::string>& args) {
#ifdef _WIN32
    std::vector<std::string> argv = {g_self.string(), "child"};
    argv.insert(argv.end(), args.begin(), args.end());
    std::wstring line = win32::wide(windows_command_line(argv));
    STARTUPINFOW si{};
    si.cb = sizeof si;
    PROCESS_INFORMATION pi{};
    if (!CreateProcessW(nullptr, line.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi))
        return 0;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return pi.dwProcessId;
#else
    const pid_t pid = ::fork();
    if (pid == 0) {
        std::vector<std::string> argv = {g_self.string(), "child"};
        argv.insert(argv.end(), args.begin(), args.end());
        std::vector<char*> a;
        for (std::string& s : argv) a.push_back(s.data());
        a.push_back(nullptr);
        ::execv(g_self.c_str(), a.data());
        ::_exit(127);
    }
    return pid;
#endif
}

std::vector<std::string> utf8_arguments(int argc, char** argv) {
#ifdef _WIN32
    (void)argc;
    (void)argv;
    int n = 0;
    LPWSTR* wide_argv = CommandLineToArgvW(GetCommandLineW(), &n);
    std::vector<std::string> out;
    for (int i = 0; i < n; ++i) out.push_back(win32::narrow(wide_argv[i]));
    LocalFree(wide_argv);
    return out;
#else
    return std::vector<std::string>(argv, argv + argc);
#endif
}

int child_main(const std::vector<std::string>& a) {
    const std::string what = a.size() > 2 ? a[2] : "";
#ifdef _WIN32
    // (Bytes as written: the C runtime's text mode would make each \n a \r\n.)
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);
#endif
    if (what == "lines") {
        // Every kind of line break, a line without one at the end, standard error, a code.
        out("one\ntwo\r\nthree\rfour\n\n");
        std::fprintf(stderr, "bad one\nbad two");
        std::fflush(stderr);
        out("five");
        return 3;
    }
    if (what == "argv") {
        for (size_t i = 3; i < a.size(); ++i) out("[" + a[i] + "]\n");
        return 0;
    }
    if (what == "env") {
#ifdef _WIN32
        const std::wstring name = win32::wide(a.at(3));
        const bool set = GetEnvironmentVariableW(name.c_str(), nullptr, 0) > 0;
        out(set ? "=" + win32::narrow(win32::environment(name.c_str())) + "\n" : "unset\n");
#else
        const char* v = std::getenv(a.at(3).c_str());
        out(v ? std::string("=") + v + "\n" : "unset\n");
#endif
        return 0;
    }
    if (what == "cwd") {
        out(fs::current_path().string() + "\n");
        return 0;
    }
    if (what == "stdin") {
#ifdef _WIN32
        _setmode(_fileno(stdin), _O_BINARY);
#endif
        std::string text;
        for (int c; (c = std::getchar()) != EOF;) text += static_cast<char>(c);
        out(text.empty() ? "eof\n" : "read [" + text + "]\n");
        return 0;
    }
    if (what == "sleep") {
        out("sleeping\n");
        sleep_for(std::atof(a.at(3).c_str()));
        return 0;
    }
    if (what == "many") {
        // (Lots, in pieces, to see none is lost.)
        for (int i = 0; i < 20000; ++i) std::printf("line %d of many\n", i);
        std::fflush(stdout);
        return 0;
    }
#ifndef _WIN32
    if (what == "signal") {
        ::raise(SIGKILL);
        return 0;
    }
    if (what == "stubborn") {
        ::signal(SIGTERM, SIG_IGN);
        out("stubborn\n");
        sleep_for(30);
        return 0;
    }
    if (what == "fds") {
        // The files open beyond 0-2.
        std::string open;
        for (int fd = 3; fd < 1024; ++fd) {
            if (::fcntl(fd, F_GETFD) >= 0) open += std::to_string(fd) + " ";
        }
        out("open:" + open + "\n");
        return 0;
    }
    if (what == "session") {
        out(std::to_string(::getsid(0)) + " " + std::to_string(::getpgid(0)) + " " + std::to_string(::getpid()) +
            "\n");
        return 0;
    }
    if (what == "parent") {
        // A launcher of its own that starts a task and ends without stopping it: the task gets SIGTERM.
        ProcessHost host;
        std::string error;
        ProcessSpec spec;
        spec.argv = {g_self.string(), "child", "sleep", "30"};
        auto p = host.start(spec, {}, &error);
        out((p ? std::to_string(p->pid()) : "0") + "\n");
        sleep_for(0.3);
        std::_Exit(0);
    }
#endif
    if (what == "family") {
        // A grandchild that runs on (and holds the output, when `hold`), then this one's end or its wait.
        const bool hold = a.size() > 3 && a[3] == "hold";
#ifdef _WIN32
        (void)hold;
        const int64_t g = start_grandchild({"sleep", "30"});
#else
        int64_t g = 0;
        if (hold) {
            const pid_t pid = ::fork();
            if (pid == 0) {
                sleep_for(0.4);
                out("late line\n"); // (written after its parent's end, into the pipe it holds)
                sleep_for(30);
                ::_exit(0);
            }
            g = pid;
        } else {
            g = start_grandchild({"sleep", "30"});
        }
#endif
        out("grandchild " + std::to_string(g) + "\n");
        if (a.size() > 3 && a[3] == "end") return 0;
        if (hold) return 0;
        sleep_for(30);
        return 0;
    }
    if (what == "worker") {
        // A Windows worker: a grandchild, then waits for its cancel file (or `stubborn`: ignores it).
        const fs::path cancel = a.at(3);
        const bool stubborn = a.size() > 4 && a[4] == "stubborn";
        const int64_t g = start_grandchild({"sleep", "30"});
        out("grandchild " + std::to_string(g) + "\n");
        for (int i = 0; i < 300; ++i) {
            std::error_code ec;
            if (!stubborn && fs::exists(cancel, ec)) {
                out("Cancelled.\n");
                return 130;
            }
            sleep_for(0.1);
        }
        return 0;
    }
    std::fprintf(stderr, "unknown child %s\n", what.c_str());
    return 99;
}

// ---------------------------------------------------------------- the tests

struct Run {
    std::vector<std::pair<std::string, bool>> lines;
    int code = -1000;
    bool ended = false;
    std::unique_ptr<Process> process;

    std::vector<std::string> out() const {
        std::vector<std::string> v;
        for (const auto& [l, e] : lines) {
            if (!e) v.push_back(l);
        }
        return v;
    }
    std::vector<std::string> err() const {
        std::vector<std::string> v;
        for (const auto& [l, e] : lines) {
            if (e) v.push_back(l);
        }
        return v;
    }
    bool has_line(const std::string& prefix) const {
        for (const auto& [l, e] : lines) {
            if (l.rfind(prefix, 0) == 0) return true;
        }
        return false;
    }
    std::string first_word_after(const std::string& prefix) const {
        for (const auto& [l, e] : lines) {
            if (l.rfind(prefix, 0) == 0) return l.substr(prefix.size());
        }
        return {};
    }
};

std::string joined(const std::vector<std::string>& v) {
    std::string s;
    for (const std::string& x : v) s += "<" + x + ">";
    return s;
}

std::unique_ptr<Run> start(ProcessHost& host, ProcessSpec spec, std::string* error = nullptr) {
    auto run = std::make_unique<Run>();
    Run* r = run.get();
    std::string why;
    r->process = host.start(spec,
                            {[r](const std::string& line, bool err) { r->lines.emplace_back(line, err); },
                             [r](int code) {
                                 r->code = code;
                                 r->ended = true;
                             }},
                            &why);
    if (error) *error = why;
    if (!r->process) {
        if (!error) check(false, "cannot start " + spec.argv.at(0) + ": " + why);
        return nullptr;
    }
    return run;
}

ProcessSpec child(std::vector<std::string> args) {
    ProcessSpec spec;
    spec.argv = {g_self.string(), "child"};
    spec.argv.insert(spec.argv.end(), args.begin(), args.end());
    return spec;
}

// Pumps until the run ended (true) or `seconds` passed.
bool wait_end(ProcessHost& host, Run& run, double seconds) {
    const auto until = Clock::now() + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
    while (!run.ended && Clock::now() < until) {
        host.wait(0.05);
        host.pump();
    }
    return run.ended;
}

bool wait_line(ProcessHost& host, Run& run, const std::string& prefix, double seconds) {
    const auto until = Clock::now() + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
    while (!run.has_line(prefix) && Clock::now() < until && !run.ended) {
        host.wait(0.05);
        host.pump();
    }
    return run.has_line(prefix);
}

void test_command_line() {
    const std::vector<std::vector<std::string>> cases = {
        {"C:\\Program Files\\Python\\python.exe", "-u", "main.py"},
        {"p.exe", "", "a b", "tab\there", "quote\"inside", "\\\"", "ends\\", "ends\\\\", "C:\\a dir\\",
         "\\\\server\\share\\", "two  spaces", "\"", "\\", "a\\\\\"b"},
        {"p.exe", "Jos\xc3\xa9", "\xe6\x97\xa5\xe6\x9c\xac", "\xf0\x9f\x8e\xae emoji"},
    };
    for (const auto& argv : cases) {
        const std::string line = windows_command_line(argv);
        check_eq(joined(split_windows_command_line(line)), joined(argv), "command line round trip of " + line);
    }
    check_eq(windows_command_line({"a.exe", "x", "/d"}), std::string("a.exe x /d"), "plain words as they are");
    check_eq(windows_command_line({"C:\\a b\\a.exe", "", "x y"}), std::string("\"C:\\a b\\a.exe\" \"\" \"x y\""),
             "quoted where needed");
    check_eq(windows_command_line({"a.exe", "b\\\"c", "d\\", "e f\\"}),
             std::string("a.exe \"b\\\\\\\"c\" d\\ \"e f\\\\\""), "backslashes before quotes doubled");
    // CommandLineToArgvW's own rules for the program's name and plain words.
    check_eq(joined(split_windows_command_line("prog.exe a  b\t\"c d\" e\\\\f")), joined({"prog.exe", "a", "b", "c d",
                                                                                      "e\\\\f"}),
             "plain words");
    check_eq(joined(split_windows_command_line("\"C:\\x y\\p.exe\" z")), joined({"C:\\x y\\p.exe", "z"}),
             "quoted program");

    LineSplitter s;
    std::vector<std::string> lines;
    const auto add = [&](std::string&& l) { lines.push_back(l); };
    s.feed("a\r", add);
    s.feed("\nb\r", add);
    s.feed("c\n\nd", add);
    s.finish(add);
    check_eq(joined(lines), joined({"a", "b", "c", "", "d"}), "line breaks split across reads");
}

void test_lines(ProcessHost& host) {
    auto run = start(host, child({"lines"}));
    if (!run) return;
    check(wait_end(host, *run, 10), "lines: it ended");
    check_eq(run->code, 3, "lines: exit code");
    check_eq(joined(run->out()), joined({"one", "two", "three", "four", "", "five"}), "lines: standard output");
    check_eq(joined(run->err()), joined({"bad one", "bad two"}), "lines: standard error");
    check(!run->process->running(), "lines: not running once ended");

    auto many = start(host, child({"many"}));
    if (!many) return;
    check(wait_end(host, *many, 20), "many: it ended");
    check_eq(many->out().size(), size_t(20000), "many: every line");
    check_eq(many->out().empty() ? std::string() : many->out().back(), std::string("line 19999 of many"),
             "many: the last line");
}

void test_environment(ProcessHost& host) {
    ProcessSpec spec = child({"env", "TTT2_PLATFORM_TEST"});
    spec.env = {{"TTT2_PLATFORM_TEST", "set here \xc3\xa9"}};
    auto run = start(host, spec);
    if (!run) return;
    wait_end(host, *run, 10);
    check_eq(joined(run->out()), joined({"=set here \xc3\xa9"}), "environment: a variable set");

#ifdef _WIN32
    // (Windows: names are the same whatever their case; the launcher's PATH is replaced, not doubled.)
    spec = child({"env", "Path"});
    spec.env = {{"PATH", "C:\\only-this"}};
    run = start(host, spec);
    if (!run) return;
    wait_end(host, *run, 10);
    check_eq(joined(run->out()), joined({"=C:\\only-this"}), "environment: a variable's case ignored");
#endif

    const fs::path folder = g_root / "a folder \xc3\xa9";
    fs::create_directories(folder);
    spec = child({"cwd"});
    spec.cwd = folder;
    run = start(host, spec);
    if (!run) return;
    wait_end(host, *run, 10);
    std::error_code ec;
    check_eq(run->out().empty() ? std::string() : run->out()[0],
             fs::canonical(folder, ec).string(), "cwd: the folder given");

    run = start(host, child({"stdin"}));
    if (!run) return;
    wait_end(host, *run, 10);
    check_eq(joined(run->out()), joined({"eof"}), "stdin: nothing to read");
    // Input given: all of it, then its end (main.py --query save-settings' JSON).
    ProcessSpec given = child({"stdin"});
    given.input = "{\"data\": \"C:\\\\Jos\xc3\xa9\"}\tend";
    run = start(host, given);
    if (!run) return;
    wait_end(host, *run, 10);
    check_eq(joined(run->out()), joined({"read [" + given.input + "]"}), "stdin: the input given");
    given.input = std::string(ProcessSpec::kMaxInput, 'x');
    run = start(host, given);
    if (!run) return;
    wait_end(host, *run, 10);
    check_eq(run->out().empty() ? 0 : run->out()[0].size(), ProcessSpec::kMaxInput + 7, "stdin: 64 KiB of input");
    given.input += "y";
    std::string error;
    check(!host.start(given, {}, &error) && error.find("too much input") != std::string::npos, "stdin: no more");
}

void test_quoting(ProcessHost& host) {
    const std::vector<std::string> args = {"",         "a b",        "quote\"inside", "\\\"",      "ends\\",
                                           "ends\\\\", "C:\\a dir\\", "two  spaces",  "\"",        "\\",
                                           "a\\\\\"b", "Jos\xc3\xa9", "\xe6\x97\xa5\xe6\x9c\xac", "%PATH%", "^&|<>"};
    std::vector<std::string> argv = {"argv"};
    argv.insert(argv.end(), args.begin(), args.end());
    auto run = start(host, child(argv));
    if (!run) return;
    wait_end(host, *run, 10);
    std::vector<std::string> want;
    for (const std::string& a : args) want.push_back("[" + a + "]");
    check_eq(joined(run->out()), joined(want), "arguments arrive as given");
}

void test_start_failure(ProcessHost& host) {
    std::string error;
    ProcessSpec spec;
    spec.argv = {(g_root / "no such program").string()};
    auto run = start(host, spec, &error);
    check(!run, "a missing program does not start");
    check(!error.empty(), "a missing program: why (" + error + ")");
#ifndef _WIN32
    spec.argv = {"sh", "-c", "exit 7"}; // (found in PATH)
    run = start(host, spec);
    if (!run) return;
    wait_end(host, *run, 10);
    check_eq(run->code, 7, "a program found in PATH");
    spec = child({"cwd"});
    spec.cwd = g_root / "no such folder";
    run = start(host, spec, &error);
    check(!run, "a missing folder: it does not start");
#endif
}

void test_cancel(ProcessHost& host) {
    host.set_times(1.5, 0.5);
#ifndef _WIN32
    // SIGTERM to it alone: it ends (143).
    auto run = start(host, child({"sleep", "30"}));
    if (!run) return;
    check(wait_line(host, *run, "sleeping", 10), "cancel: it runs");
    const auto t0 = Clock::now();
    run->process->terminate();
    check(wait_end(host, *run, 10), "cancel: it ended");
    check_eq(run->code, 128 + SIGTERM, "cancel: 128 + SIGTERM");
    check(seconds_since(t0) < 1.4, "cancel: at once");

    // Ignoring SIGTERM: its group is killed after the stop time (here 1.5 s).
    run = start(host, child({"stubborn"}));
    if (!run) return;
    check(wait_line(host, *run, "stubborn", 10), "stubborn: it runs");
    const auto t1 = Clock::now();
    run->process->terminate();
    check(wait_end(host, *run, 10), "stubborn: it ended");
    check_eq(run->code, 128 + SIGKILL, "stubborn: killed");
    check(seconds_since(t1) >= 1.4, "stubborn: after the stop time");

    // Ended by a signal of its own.
    run = start(host, child({"signal"}));
    if (!run) return;
    wait_end(host, *run, 10);
    check_eq(run->code, 128 + SIGKILL, "a signal's end: 128 + it");

    // What it started is in its group: killed once it ended after Cancel.
    run = start(host, child({"family"}));
    if (!run) return;
    wait_line(host, *run, "grandchild ", 10);
    const int64_t g = std::atoll(run->first_word_after("grandchild ").c_str());
    check(g > 0 && alive(g), "family: the grandchild runs");
    run->process->terminate();
    check(wait_end(host, *run, 10), "family: it ended");
    check(gone_within(g, 5), "family: the grandchild was killed with its group");

    // Not cancelled: what it started runs on.
    run = start(host, child({"family", "end"}));
    if (!run) return;
    wait_end(host, *run, 10);
    const int64_t g2 = std::atoll(run->first_word_after("grandchild ").c_str());
    check(g2 > 0 && alive(g2), "family end: the grandchild runs on after a normal end");
    kill_pid(g2);

    // A grandchild holding the output: lines read on after the end, the end told after the drain time (0.5 s).
    run = start(host, child({"family", "hold"}));
    if (!run) return;
    const auto t2 = Clock::now();
    check(wait_end(host, *run, 10), "hold: it ended");
    check(seconds_since(t2) < 3, "hold: its end told after the drain time, not the grandchild's");
    check(run->has_line("late line"), "hold: a line written after its end is read");
    const int64_t g3 = std::atoll(run->first_word_after("grandchild ").c_str());
    if (g3 > 0) kill_pid(g3);
#else
    // Without a cancel file: the job is ended at once.
    auto run = start(host, child({"family"}));
    if (!run) return;
    wait_line(host, *run, "grandchild ", 10);
    const int64_t g = std::atoll(run->first_word_after("grandchild ").c_str());
    check(g > 0 && alive(g), "job: the grandchild runs");
    run->process->terminate();
    check(wait_end(host, *run, 10), "job: it ended");
    check(gone_within(g, 5), "job: the grandchild ended with the job");

    // With a cancel file: made, the worker ends itself (130), what it started is ended after.
    ProcessSpec spec = child({"worker", (g_root / "w1.cancel").string()});
    spec.cancel_file = g_root / "w1.cancel";
    spec.output = g_root / "w1.log";
    run = start(host, spec);
    if (!run) return;
    wait_line(host, *run, "grandchild ", 10);
    const int64_t g1 = std::atoll(run->first_word_after("grandchild ").c_str());
    run->process->terminate();
    check(wait_end(host, *run, 10), "worker: it ended");
    check_eq(run->code, 130, "worker: its own code after the cancel file");
    check(fs::exists(spec.cancel_file), "worker: the cancel file was made");
    check(gone_within(g1, 5), "worker: its grandchild ended after it");
    check(read_file(spec.output).find("Cancelled.\r\n") != std::string::npos, "worker: its lines in its log");

    // A worker that does not stop: ended after the stop time.
    spec = child({"worker", (g_root / "w2.cancel").string(), "stubborn"});
    spec.cancel_file = g_root / "w2.cancel";
    run = start(host, spec);
    if (!run) return;
    wait_line(host, *run, "grandchild ", 10);
    const auto t1 = Clock::now();
    run->process->terminate();
    check(wait_end(host, *run, 10), "stubborn worker: it ended");
    check(seconds_since(t1) >= 1.4, "stubborn worker: after the stop time");

    // The update workers: never ended, no job.
    spec = child({"worker", (g_root / "w3.cancel").string(), "stubborn"});
    spec.cancel_file = g_root / "w3.cancel";
    spec.mode = ProcessSpec::Mode::kSelfUpdate;
    run = start(host, spec);
    if (!run) return;
    wait_line(host, *run, "grandchild ", 10);
    const int64_t g3 = std::atoll(run->first_word_after("grandchild ").c_str());
    run->process->terminate();
    check(!wait_end(host, *run, 3), "update worker: not ended by Cancel");
    check(fs::exists(spec.cancel_file), "update worker: its cancel file was made");
    check(alive(run->process->pid()), "update worker: still running");
    kill_pid(run->process->pid());
    check(wait_end(host, *run, 10), "update worker: ended (by the test)");
    check(alive(g3), "update worker: what it started is in no job");
    kill_pid(g3);
#endif
    host.set_times(ProcessHost::kStopSeconds, ProcessHost::kDrainSeconds);
}

void test_detached(ProcessHost& host) {
#ifndef _WIN32
    ProcessSpec spec = child({"session"});
    spec.mode = ProcessSpec::Mode::kDetached;
    spec.output = g_root / "game.log";
    std::ofstream(spec.output) << "old text that goes\n";
    auto run = start(host, spec);
    if (!run) return;
    check(wait_end(host, *run, 10), "game: it ended");
    check(run->lines.empty(), "game: no lines (its output is in its log)");
    std::istringstream words(read_file(spec.output));
    int64_t sid = 0, pgid = 0, pid = 0;
    words >> sid >> pgid >> pid;
    check(pid == run->process->pid() && sid == pid, "game: a session of its own (" + read_file(spec.output) + ")");

    spec = child({"session"});
    run = start(host, spec);
    if (!run) return;
    wait_end(host, *run, 10);
    std::istringstream words2(run->out().empty() ? std::string() : run->out()[0]);
    words2 >> sid >> pgid >> pid;
    check(pgid == pid && sid != pid, "task: a group of its own, the launcher's session");

    spec = child({"sleep", "30"});
    spec.mode = ProcessSpec::Mode::kDetached;
    spec.output = g_root / "game2.log";
    run = start(host, spec);
    if (!run) return;
    run->process->terminate();
    check(!wait_end(host, *run, 0.5), "game: terminate() does not end it");
    kill_pid(run->process->pid());
    check(wait_end(host, *run, 10), "game: its end is told");
#else
    ProcessSpec spec = child({"lines"});
    spec.mode = ProcessSpec::Mode::kDetached;
    spec.output = g_root / "game-latest.log";
    auto run = start(host, spec);
    if (!run) return;
    check(wait_end(host, *run, 10), "game: it ended");
    check_eq(run->code, 3, "game: its code");
    check(run->lines.empty(), "game: no lines (its output is in its log)");
    const std::string log = read_file(spec.output);
    check(log.find("one\ntwo") != std::string::npos && log.find("bad one") != std::string::npos,
          "game: its output and errors in its log");
#endif
}

void test_dropped(ProcessHost& host) {
    // Dropped while it runs: nothing is told any more, nothing breaks, it is still waited for.
    auto run = start(host, child({"lines"}));
    if (!run) return;
    run->process.reset();
    sleep_for(0.5);
    host.pump();
    check(run->lines.empty() && !run->ended, "dropped: nothing told");
}

#ifndef _WIN32
void test_files_and_parent(ProcessHost& host) {
    // Files the launcher has open (not close-on-exec, as a library may leave them) do not reach the program.
    const int leaked = ::open("/dev/null", O_RDONLY);
    int p[2];
    check(::pipe(p) == 0, "a pipe");
    auto run = start(host, child({"fds"}));
    if (run) {
        wait_end(host, *run, 10);
        check_eq(joined(run->out()), joined({"open:"}), "no file of the launcher's is open in it");
    }
    ::close(leaked);
    ::close(p[0]);
    ::close(p[1]);

    // The launcher ends first: its task gets SIGTERM (PR_SET_PDEATHSIG).
    run = start(host, child({"parent"}));
    if (!run) return;
    wait_end(host, *run, 10);
    const int64_t task = std::atoll(run->out().empty() ? "0" : run->out()[0].c_str());
    check(task > 0, "parent: its task started");
    check(task > 0 && gone_within(task, 5), "parent: its task ended with it");
}
#endif

} // namespace

int main(int argc, char** argv) {
    const std::vector<std::string> args = utf8_arguments(argc, argv);
#ifdef _WIN32
    wchar_t self[32768];
    GetModuleFileNameW(nullptr, self, 32768);
    g_self = self;
#else
    g_self = fs::read_symlink("/proc/self/exe");
#endif
    if (args.size() > 1 && args[1] == "child") return child_main(args);
    const fs::path base = fs::absolute(args.size() > 1 ? fs::path(args[1]) : fs::temp_directory_path());
    g_root = base / ("platform_test." + std::to_string(own_pid()));
    std::error_code ec;
    fs::remove_all(g_root, ec);
    fs::create_directories(g_root);

    ProcessHost host;
    const auto timed = [](const char* name, const std::function<void()>& test) {
        const auto t0 = Clock::now();
        test();
        std::printf("%-22s %.1f s\n", name, seconds_since(t0));
        std::fflush(stdout);
    };
    timed("command line", [] { test_command_line(); });
    timed("lines", [&] { test_lines(host); });
    timed("environment", [&] { test_environment(host); });
    timed("quoting", [&] { test_quoting(host); });
    timed("start failure", [&] { test_start_failure(host); });
    timed("cancel", [&] { test_cancel(host); });
    timed("detached", [&] { test_detached(host); });
    timed("dropped", [&] { test_dropped(host); });
#ifndef _WIN32
    timed("files and parent", [&] { test_files_and_parent(host); });
#endif

    fs::remove_all(g_root, ec);
    std::printf("%d checks, %d failed\n", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
