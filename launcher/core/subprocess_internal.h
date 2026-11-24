#pragma once

// What subprocess.cpp shares with the OS's part (subprocess_linux.cpp,
// subprocess_windows.cpp): the queue the reader threads fill and pump() empties,
// and a program's state.

#include "subprocess.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <mutex>

namespace launcher {

struct ProcessHost::Shared {
    struct Event {
        std::shared_ptr<Process::State> state;
        bool exit = false;
        bool error = false; // a line of standard error
        int code = 0;
        std::string text;
    };

    std::function<void()> wake;
    std::mutex mutex;
    std::condition_variable changed;
    std::deque<Event> events;
    std::atomic<double> stop_seconds{ProcessHost::kStopSeconds};
    std::atomic<double> drain_seconds{ProcessHost::kDrainSeconds};

    void push(Event event);
};

struct Process::State {
    std::shared_ptr<ProcessHost::Shared> host;
    std::shared_ptr<const ProcessEvents> events; // (UI thread only: null once the Process is dropped)
    ProcessSpec::Mode mode = ProcessSpec::Mode::kTask;
    fs::path cancel_file;
    int64_t pid = 0;
    bool reported = false;                   // (UI thread) its end was delivered
    std::atomic<bool> stop_requested{false}; // terminate() was called
    struct Os;                               // the OS's handles (process_linux.cpp, process_windows.cpp)
    std::unique_ptr<Os> os;
    ~State();
};

// The OS's part.
std::shared_ptr<Process::State> start_process(const std::shared_ptr<ProcessHost::Shared>& host,
                                              const ProcessSpec& spec, std::string* error);
void request_stop(Process::State& state); // (UI thread) wakes the reader thread to stop it

using Clock = std::chrono::steady_clock;
inline double seconds_since(Clock::time_point t) {
    return std::chrono::duration<double>(Clock::now() - t).count();
}

} // namespace launcher
