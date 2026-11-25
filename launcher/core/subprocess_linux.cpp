// Programs the launcher runs, on Linux (see subprocess.h): fork and execve, a
// reader thread per program polling its pipes, its pidfd (or every 100 ms
// without one) and a pipe that wakes it to stop the program.

#include "subprocess_internal.h"

#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <set>
#include <thread>

extern char** environ;

#ifndef CLOSE_RANGE_CLOEXEC
#define CLOSE_RANGE_CLOEXEC (1U << 2)
#endif

namespace launcher {

struct Process::State::Os {
    int wake[2] = {-1, -1}; // terminate() writes a byte to wake[1]
};

Process::State::~State() {
    if (os) {
        for (int fd : os->wake) {
            if (fd >= 0) ::close(fd);
        }
    }
}

namespace {

void close_fd(int& fd) {
    if (fd >= 0) ::close(fd);
    fd = -1;
}

int open_pidfd(pid_t pid) {
#ifdef SYS_pidfd_open
    return static_cast<int>(::syscall(SYS_pidfd_open, pid, 0));
#else
    (void)pid;
    return -1;
#endif
}

// The program to execve: `name` itself when it has a slash, else the first executable file of that name in the
// PATH it will have (as execvp and GLib's spawn search it).
std::string program_path(const std::string& name, const char* path) {
    if (name.find('/') != std::string::npos) return name;
    std::string_view dirs = path ? path : "/usr/local/bin:/usr/bin:/bin";
    while (true) {
        const size_t colon = std::min(dirs.find(':'), dirs.size());
        std::string dir(dirs.substr(0, colon));
        if (dir.empty()) dir = ".";
        const std::string candidate = dir + "/" + name;
        std::error_code ec;
        if (::access(candidate.c_str(), X_OK) == 0 && std::filesystem::is_regular_file(candidate, ec)) return candidate;
        if (colon >= dirs.size()) break;
        dirs.remove_prefix(colon + 1);
    }
    return {};
}

// What the child does between fork and execve: only async-signal-safe calls, on data made before the fork.
struct ChildPlan {
    const char* path;
    char* const* argv;
    char* const* envp;
    const char* cwd; // null: the launcher's
    int in, out, err; // to become 0, 1, 2 (-1: keep the launcher's)
    int report;       // the pipe execve's failure is told through (O_CLOEXEC: closed by a successful execve)
    bool group;       // a task: a process group of its own, SIGTERM when the launcher ends
    bool session;     // the game: a session of its own
    pid_t parent;
    sigset_t no_signals;
    struct sigaction default_action;
};

// The child's failure, told to the launcher (start_process waits for it or for the execve).
[[noreturn]] void child_failed(int report, int code) {
    [[maybe_unused]] ssize_t n = ::write(report, &code, sizeof code);
    ::_exit(127);
}

[[noreturn]] void child(const ChildPlan& p) {
    const auto fail = [&p](int code) { child_failed(p.report, code); };
    // (The launcher's signal mask and an ignored SIGPIPE would pass to the program.)
    ::sigprocmask(SIG_SETMASK, &p.no_signals, nullptr);
    ::sigaction(SIGPIPE, &p.default_action, nullptr);
    if (p.group) {
        ::setpgid(0, 0);
        ::prctl(PR_SET_PDEATHSIG, SIGTERM);
        if (::getppid() != p.parent) ::raise(SIGTERM); // (the launcher has ended already)
    }
    if (p.session) ::setsid();
    const int targets[3] = {p.in, p.out, p.err};
    for (int i = 0; i < 3; ++i) {
        if (targets[i] < 0) continue;
        if (targets[i] == i) {
            ::fcntl(i, F_SETFD, 0); // (already there: only its close-on-exec goes)
        } else if (::dup2(targets[i], i) < 0) {
            fail(errno);
        }
    }
    if (p.cwd && ::chdir(p.cwd) != 0) fail(errno);
    // Everything else the launcher has open (whoever opened it) closes with the execve; the report pipe stays until
    // then. (Kernels before 5.11: closed now, around it.)
    if (::close_range(3, ~0U, CLOSE_RANGE_CLOEXEC) != 0) {
        if (p.report > 3) ::close_range(3, static_cast<unsigned>(p.report) - 1, 0);
        ::close_range(static_cast<unsigned>(p.report) + 1, ~0U, 0);
    }
    ::execve(p.path, p.argv, p.envp);
    child_failed(p.report, errno);
}

struct Reader {
    std::shared_ptr<Process::State> state;
    pid_t pid = 0;
    int out = -1, err = -1, pidfd = -1, wake = -1;
    int log = -1; // a task's log file (each line written to it)
    bool task = true;
    LineSplitter out_lines, err_lines;

    void push_line(std::string&& text, bool error) {
        if (log >= 0) {
            std::string copy = text + "\n";
            for (size_t done = 0; done < copy.size();) {
                const ssize_t n = ::write(log, copy.data() + done, copy.size() - done);
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) break;
                done += static_cast<size_t>(n);
            }
        }
        state->host->push({state, false, error, 0, std::move(text)});
    }

    // Reads what is there; false at the end of that output.
    bool read(int& fd, LineSplitter& lines, bool error) {
        char buffer[65536];
        for (;;) {
            const ssize_t n = ::read(fd, buffer, sizeof buffer);
            if (n < 0 && errno == EINTR) continue;
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return true;
            if (n <= 0) {
                lines.finish([&](std::string&& l) { push_line(std::move(l), error); });
                close_fd(fd);
                return false;
            }
            lines.feed({buffer, static_cast<size_t>(n)}, [&](std::string&& l) { push_line(std::move(l), error); });
            if (static_cast<size_t>(n) < sizeof buffer) return true;
        }
    }

    void run() {
        ProcessHost::Shared& host = *state->host;
        bool exited = false, stopping = false, killed = false;
        int code = 1;
        Clock::time_point kill_at{}, drain_until{};
        for (;;) {
            if (exited && ((out < 0 && err < 0) || Clock::now() >= drain_until)) break;
            pollfd fds[4];
            nfds_t n = 0;
            int out_at = -1, err_at = -1, pid_at = -1, wake_at = -1;
            if (out >= 0) fds[out_at = static_cast<int>(n++)] = {out, POLLIN, 0};
            if (err >= 0) fds[err_at = static_cast<int>(n++)] = {err, POLLIN, 0};
            if (!exited && pidfd >= 0) fds[pid_at = static_cast<int>(n++)] = {pidfd, POLLIN, 0};
            if (!exited && wake >= 0) fds[wake_at = static_cast<int>(n++)] = {wake, POLLIN, 0};
            double timeout = -1;
            const auto until = [&](Clock::time_point t) {
                const double s = std::max(0.0, std::chrono::duration<double>(t - Clock::now()).count());
                timeout = timeout < 0 ? s : std::min(timeout, s);
            };
            if (!exited && pidfd < 0) until(Clock::now() + std::chrono::milliseconds(100));
            if (!exited && stopping && !killed) until(kill_at);
            if (exited) until(drain_until);
            const int ms = timeout < 0 ? -1 : static_cast<int>(timeout * 1000) + 1;
            if (::poll(fds, n, ms) < 0 && errno != EINTR) break;
            if (wake_at >= 0 && (fds[wake_at].revents & (POLLIN | POLLHUP))) {
                char drain[16];
                while (::read(wake, drain, sizeof drain) > 0) {
                }
                if (state->stop_requested && !stopping && task) {
                    // SIGTERM to it alone: it stops what it started, in its own order, and cleans up.
                    stopping = true;
                    ::kill(pid, SIGTERM);
                    kill_at = Clock::now() + std::chrono::duration_cast<Clock::duration>(
                                                 std::chrono::duration<double>(host.stop_seconds.load()));
                }
            }
            if (out_at >= 0 && fds[out_at].revents) read(out, out_lines, false);
            if (err_at >= 0 && fds[err_at].revents) read(err, err_lines, true);
            if (!exited) {
                siginfo_t info{};
                // (Seen without being waited for: its number stays its own while its group is killed.)
                if (::waitid(P_PID, static_cast<id_t>(pid), &info, WEXITED | WNOHANG | WNOWAIT) == 0 &&
                    info.si_pid == pid) {
                    exited = true;
                    // Stopped: nothing it started stays (a hidden Tekken 7 an importer that did not clean up left
                    // running, say).
                    if (stopping && task) ::kill(-pid, SIGKILL);
                    int status = 0;
                    while (::waitpid(pid, &status, 0) < 0 && errno == EINTR) {
                    }
                    code = WIFEXITED(status) ? WEXITSTATUS(status) : WIFSIGNALED(status) ? 128 + WTERMSIG(status) : 1;
                    drain_until = Clock::now() + std::chrono::duration_cast<Clock::duration>(
                                                     std::chrono::duration<double>(host.drain_seconds.load()));
                } else if (stopping && !killed && Clock::now() >= kill_at) {
                    killed = true;
                    ::kill(-pid, SIGKILL); // (its group: it and all it started)
                }
            }
        }
        // (A line not ended by a line break, still in a pipe a program it started holds open.)
        out_lines.finish([&](std::string&& l) { push_line(std::move(l), false); });
        err_lines.finish([&](std::string&& l) { push_line(std::move(l), true); });
        for (int* fd : {&out, &err, &pidfd, &log}) close_fd(*fd);
        host.push({state, true, false, code, {}});
    }
};

} // namespace

void request_stop(Process::State& state) {
    if (state.os && state.os->wake[1] >= 0) {
        const char byte = 1;
        [[maybe_unused]] ssize_t n = ::write(state.os->wake[1], &byte, 1);
    }
}

std::shared_ptr<Process::State> start_process(const std::shared_ptr<ProcessHost::Shared>& host,
                                              const ProcessSpec& spec, std::string* error) {
    const auto fail = [&](const std::string& why) -> std::shared_ptr<Process::State> {
        if (error) *error = why;
        return nullptr;
    };
    const bool task = spec.mode != ProcessSpec::Mode::kDetached;

    // Everything the child needs, made now (it may not allocate).
    std::vector<std::string> env_strings;
    std::set<std::string> overridden;
    for (const auto& [name, value] : spec.env) overridden.insert(name);
    const char* path_variable = std::getenv("PATH");
    for (char** e = environ; e && *e; ++e) {
        const std::string_view entry(*e);
        const std::string name(entry.substr(0, entry.find('=')));
        if (!overridden.count(name)) env_strings.emplace_back(entry);
    }
    std::string child_path;
    for (const auto& [name, value] : spec.env) {
        env_strings.push_back(name + "=" + value);
        if (name == "PATH") child_path = value;
    }
    const std::string program =
        program_path(spec.argv[0], overridden.count("PATH") ? child_path.c_str() : path_variable);
    if (program.empty()) return fail("cannot run " + spec.argv[0] + ": " + std::strerror(ENOENT));
    std::vector<char*> argv, envp;
    for (const std::string& a : spec.argv) argv.push_back(const_cast<char*>(a.c_str()));
    argv.push_back(nullptr);
    for (std::string& e : env_strings) envp.push_back(e.data());
    envp.push_back(nullptr);
    const std::string cwd = spec.cwd.string();

    if (spec.input.size() > ProcessSpec::kMaxInput) return fail("too much input for " + spec.argv[0]);
    // Standard input: the null device, or a socket the input is sent through (a socket: no SIGPIPE when the program
    // ends without reading it, MSG_NOSIGNAL).
    int input[2] = {-1, -1};
    if (task && !spec.input.empty() && ::socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, input) != 0)
        return fail(std::string("cannot make pipes: ") + std::strerror(errno));
    int null = input[1] >= 0 ? input[1] : ::open("/dev/null", O_RDONLY | O_CLOEXEC);
    if (null < 0) {
        close_fd(input[0]);
        return fail(std::string("cannot open /dev/null: ") + std::strerror(errno));
    }
    int out[2] = {-1, -1}, err[2] = {-1, -1}, report[2] = {-1, -1}, wake[2] = {-1, -1};
    int output = -1, log = -1;
    const auto close_all = [&] {
        for (int* fd : {&null, &input[0], &out[0], &out[1], &err[0], &err[1], &report[0], &report[1], &wake[0],
                        &wake[1], &output, &log}) {
            close_fd(*fd);
        }
    };
    if (task) {
        if (::pipe2(out, O_CLOEXEC) != 0 || ::pipe2(err, O_CLOEXEC) != 0 ||
            ::pipe2(wake, O_CLOEXEC | O_NONBLOCK) != 0) {
            const std::string why = std::strerror(errno);
            close_all();
            return fail("cannot make pipes: " + why);
        }
        if (!spec.output.empty())
            log = ::open(spec.output.c_str(), O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
    } else if (!spec.output.empty()) {
        // (Its output into the file, else where the launcher's goes.)
        output = ::open(spec.output.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    }
    if (::pipe2(report, O_CLOEXEC) != 0) {
        const std::string why = std::strerror(errno);
        close_all();
        return fail("cannot make pipes: " + why);
    }

    ChildPlan plan{};
    plan.path = program.c_str();
    plan.argv = argv.data();
    plan.envp = envp.data();
    plan.cwd = cwd.empty() ? nullptr : cwd.c_str();
    plan.in = null;
    plan.out = task ? out[1] : output;
    plan.err = task ? err[1] : output;
    plan.report = report[1];
    plan.group = task;
    plan.session = !task;
    plan.parent = ::getpid();
    sigemptyset(&plan.no_signals);
    plan.default_action.sa_handler = SIG_DFL;
    sigemptyset(&plan.default_action.sa_mask);

    const pid_t pid = ::fork();
    if (pid < 0) {
        const std::string why = std::strerror(errno);
        close_all();
        return fail("cannot start " + spec.argv[0] + ": " + why);
    }
    if (pid == 0) child(plan);

    if (task) ::setpgid(pid, pid); // (also here: its group is there before terminate() may signal it)
    close_fd(report[1]);
    close_fd(out[1]);
    close_fd(err[1]);
    close_fd(null);
    close_fd(output);
    int code = 0;
    ssize_t n;
    while ((n = ::read(report[0], &code, sizeof code)) < 0 && errno == EINTR) {
    }
    close_fd(report[0]);
    if (n == static_cast<ssize_t>(sizeof code)) {
        int status = 0;
        while (::waitpid(pid, &status, 0) < 0 && errno == EINTR) {
        }
        close_all();
        return fail("cannot run " + spec.argv[0] + ": " + std::strerror(code));
    }

    auto state = std::make_shared<Process::State>();
    state->host = host;
    state->mode = spec.mode;
    state->cancel_file = spec.cancel_file;
    state->pid = pid;
    state->os = std::make_unique<Process::State::Os>();
    state->os->wake[0] = wake[0];
    state->os->wake[1] = wake[1];
    wake[0] = wake[1] = -1;
    if (input[0] >= 0) {
        // (Sent on a thread of its own: a program that writes before it reads never waits for this one.)
        std::thread([fd = input[0], data = spec.input] {
            for (size_t done = 0; done < data.size();) {
                const ssize_t n = ::send(fd, data.data() + done, data.size() - done, MSG_NOSIGNAL);
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) break;
                done += static_cast<size_t>(n);
            }
            ::shutdown(fd, SHUT_WR);
            ::close(fd);
        }).detach();
        input[0] = -1;
    }

    auto reader = std::make_shared<Reader>();
    reader->state = state;
    reader->pid = pid;
    reader->out = out[0];
    reader->err = err[0];
    reader->log = log;
    reader->task = task;
    reader->wake = state->os->wake[0];
    reader->pidfd = open_pidfd(pid);
    if (reader->pidfd >= 0) ::fcntl(reader->pidfd, F_SETFD, FD_CLOEXEC);
    for (int fd : {reader->out, reader->err}) {
        if (fd >= 0) ::fcntl(fd, F_SETFL, ::fcntl(fd, F_GETFL) | O_NONBLOCK);
    }
    std::thread([reader] { reader->run(); }).detach();
    return state;
}

} // namespace launcher
