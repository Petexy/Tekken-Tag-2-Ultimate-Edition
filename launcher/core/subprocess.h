#pragma once

// Programs the launcher runs (the builder, the importer, Python's workers and
// questions, the game, the updated launcher), on Linux and Windows alike: their
// output read line by line as it comes, their end, and stopping them. No
// toolkit: the app wakes its loop when there is news (ProcessHost's `wake`, which
// the SDL app wires to SDL_PushEvent) and delivers it on its own thread (pump()).
//
// Threads: start(), pump(), terminate() and a Process's destruction belong to ONE
// thread, the window's (the UI thread): the handlers run there, from pump(). On
// Linux the program is started with fork(), which copies only the thread that
// calls it; before the fork everything the child needs (arguments, environment,
// folder, files) is ready, and the child makes only async-signal-safe calls
// (dup2, setpgid or setsid, prctl, sigprocmask/sigaction, close_range, chdir,
// execve, write, _exit) - never malloc or a lock another thread may hold.
// PR_SET_PDEATHSIG is tied to the thread that forked: that is the UI thread,
// which lives as long as the launcher. Each program has a reader thread of its
// own (poll on its pipes and its pidfd; Windows: overlapped named pipes and the
// process handle) that queues what it reads.
//
// Linux:
//  - a task (Mode::kTask): a process group of its own (setpgid), SIGTERM when
//    the launcher ends first (PR_SET_PDEATHSIG), standard input /dev/null, its
//    standard output and error through pipes (O_CLOEXEC), split into lines on
//    any line break (\n, \r\n, \r) over the raw bytes (paths are the file
//    system's bytes, not always UTF-8). terminate(): SIGTERM to it alone, so
//    that it stops what it started in its own order; what is left of its group
//    once it has ended is killed (SIGKILL), and all of the group when it has
//    not ended within kStopSeconds. After its end, its output is read on for up
//    to kDrainSeconds (a program it started, Wine's server, may hold it open).
//  - the game or the updated launcher (Mode::kDetached, kSelfUpdate's
//    meaning on Linux too): a session of its own (setsid), so that it keeps
//    running when the launcher is closed; standard input /dev/null; its
//    output into `output` (made anew), else where the launcher's goes. Never
//    killed by terminate() (which then does nothing).
//  - Every file the launcher has open beyond 0-2 is closed in the child
//    (close_range), whoever opened it (SDL, a driver).
//  - Exit code: the program's, 128 + the signal when one ended it, else 1.
// Windows:
//  - CreateProcessW: the arguments quoted as CommandLineToArgvW reads them
//    (windows_command_line), an environment block of the launcher's own with the
//    variables set over it, the folder, CREATE_NO_WINDOW, only its own standard
//    handles inherited (PROC_THREAD_ATTRIBUTE_HANDLE_LIST), standard input NUL.
//  - a task: started suspended, put in a Job Object of its own that kills
//    everything in it when the launcher's last handle to it closes
//    (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE), then resumed: what it starts is in
//    the job too. terminate(): its cancel file is made when it has one (the
//    worker stops itself, cleans up and ends), else the job is ended at once;
//    once a cancelled task has ended, what is left in its job is ended
//    (TerminateJobObject), and all of it when it has not ended within
//    kStopSeconds. Its output and lines go also into `output` when given (the
//    task's log file, as the Tk window wrote it).
//  - Mode::kSelfUpdate (the 'launcher' and 'files' workers): like a task,
//    but in no job (closing the launcher never ends it half-way through
//    replacing the .exe or its files) and never killed: terminate() only makes
//    its cancel file.
//  - Mode::kDetached (the game; the updated launcher): plain CreateProcessW,
//    out of the launcher's own job when that allows it, no job of its own,
//    its output into `output`.
//  - Exit code: GetExitCodeProcess.

#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace launcher {

namespace fs = std::filesystem;

struct ProcessSpec {
    enum class Mode { kTask, kDetached, kSelfUpdate };
    std::vector<std::string> argv;                        // UTF-8 (Linux: the bytes as given)
    std::vector<std::pair<std::string, std::string>> env; // set over the launcher's own
    fs::path cwd;                                         // empty: the launcher's
    Mode mode = Mode::kTask;
    // kDetached: its standard output and error, made anew (empty: the launcher's). Tasks: the lines are also
    // written to it, each as read (Windows' task logs; empty: none).
    fs::path output;
    // Windows tasks: made by terminate(), for the worker to stop itself (empty: terminate() ends it at once).
    fs::path cancel_file;
    // Tasks: written to its standard input, which then ends (main.py --query save-settings' JSON); at most
    // kMaxInput bytes. Empty: standard input is the null device.
    std::string input;
    static constexpr size_t kMaxInput = 1 << 16;
};

struct ProcessEvents {
    // A line of its output, without its line break; `error`: standard error.
    std::function<void(const std::string& line, bool error)> line;
    // It ended and its output is read: its exit code.
    std::function<void(int code)> exited;
};

class ProcessHost;

// A running program as its starter holds it. Dropping it forgets the
// handlers; the program runs on (and is waited for, so that no zombie is left).
class Process {
public:
    ~Process();
    Process(const Process&) = delete;
    Process& operator=(const Process&) = delete;

    // Asks it to stop (see the header comment per OS and mode). Again: nothing more.
    void terminate();
    bool running() const;
    int64_t pid() const;

    struct State; // (process.cpp and the OS's part)

private:
    friend class ProcessHost;
    explicit Process(std::shared_ptr<State> state) : state_(std::move(state)) {}
    std::shared_ptr<State> state_;
};

class ProcessHost {
public:
    static constexpr double kStopSeconds = 45; // how long a program asked to stop may take to clean up
    static constexpr double kDrainSeconds = 3; // its output read on after its end

    // `wake` is called from the reader threads when there is something for pump() (the app pushes an SDL event).
    explicit ProcessHost(std::function<void()> wake = {});
    ~ProcessHost();
    ProcessHost(const ProcessHost&) = delete;
    ProcessHost& operator=(const ProcessHost&) = delete;

    // Starts it (UI thread only); none, with the reason, when it cannot start.
    std::unique_ptr<Process> start(const ProcessSpec& spec, ProcessEvents events, std::string* error);
    // Delivers the lines and ends read since (UI thread): how many.
    size_t pump();
    // Waits until there is something to pump or `seconds` have passed (tests and the app's quit path).
    bool wait(double seconds);
    // Tests: shorter times than kStopSeconds and kDrainSeconds.
    void set_times(double stop_seconds, double drain_seconds);

    struct Shared; // (process.cpp)

private:
    std::shared_ptr<Shared> shared_;
};

// Splits raw output into lines on any line break (\n, \r\n, \r), as GLib's
// G_DATA_STREAM_NEWLINE_TYPE_ANY did; a \r\n split between two reads is one.
class LineSplitter {
public:
    // Calls `line` for each complete line in `bytes`.
    void feed(std::string_view bytes, const std::function<void(std::string&&)>& line);
    // The last line, when the output did not end with a line break.
    void finish(const std::function<void(std::string&&)>& line);

private:
    std::string partial_;
    bool after_cr_ = false;
};

// Windows' command line for `argv` (UTF-8), quoted so that CommandLineToArgvW
// (and the MSVC runtime) gives back exactly these arguments: in quotes when
// empty or with a space, tab or quote (as Python's list2cmdline), backslashes
// before a quote and before a closing quote doubled, quotes escaped.
std::string windows_command_line(const std::vector<std::string>& argv);
// CommandLineToArgvW's reading of a command line (the first argument by its
// own rule: up to the next quote, or a space when it does not start with one):
// tests, and the arguments of a second start forwarded on Linux and Windows.
std::vector<std::string> split_windows_command_line(std::string_view line);

} // namespace launcher
