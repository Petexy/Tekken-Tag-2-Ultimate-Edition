// Programs the launcher runs (see subprocess.h): what both OSes share - the
// queue, pump(), the line splitter and Windows' command-line rules (which the
// Linux side uses too, for forwarded arguments and tests).

#include "subprocess_internal.h"

#include <algorithm>

namespace launcher {

// ---------------------------------------------------------------- the queue

void ProcessHost::Shared::push(Event event) {
    std::function<void()> to_wake;
    {
        std::lock_guard<std::mutex> lock(mutex);
        events.push_back(std::move(event));
        to_wake = wake;
    }
    changed.notify_all();
    if (to_wake) to_wake();
}

ProcessHost::ProcessHost(std::function<void()> wake) : shared_(std::make_shared<Shared>()) {
    shared_->wake = std::move(wake);
}

ProcessHost::~ProcessHost() {
    // (The reader threads hold the queue: they may still finish a program's end, which nobody delivers.)
    std::lock_guard<std::mutex> lock(shared_->mutex);
    shared_->wake = nullptr;
    shared_->events.clear();
}

void ProcessHost::set_times(double stop_seconds, double drain_seconds) {
    shared_->stop_seconds = stop_seconds;
    shared_->drain_seconds = drain_seconds;
}

std::unique_ptr<Process> ProcessHost::start(const ProcessSpec& spec, ProcessEvents events, std::string* error) {
    if (spec.argv.empty() || spec.argv[0].empty()) {
        if (error) *error = "no program to start";
        return nullptr;
    }
    std::shared_ptr<Process::State> state = start_process(shared_, spec, error);
    if (!state) return nullptr;
    state->events = std::make_shared<const ProcessEvents>(std::move(events));
    return std::unique_ptr<Process>(new Process(std::move(state)));
}

size_t ProcessHost::pump() {
    std::deque<Shared::Event> events;
    {
        std::lock_guard<std::mutex> lock(shared_->mutex);
        events.swap(shared_->events);
    }
    size_t delivered = 0;
    for (Shared::Event& e : events) {
        Process::State& state = *e.state;
        if (state.reported) continue;
        if (e.exit) state.reported = true;
        // (A handler may drop its Process, which forgets them: the call keeps its own.)
        const std::shared_ptr<const ProcessEvents> handlers = state.events;
        if (!handlers) continue;
        ++delivered;
        if (e.exit) {
            if (handlers->exited) handlers->exited(e.code);
        } else if (handlers->line) {
            handlers->line(e.text, e.error);
        }
    }
    return delivered;
}

bool ProcessHost::wait(double seconds) {
    std::unique_lock<std::mutex> lock(shared_->mutex);
    return shared_->changed.wait_for(lock, std::chrono::duration<double>(seconds),
                                     [this] { return !shared_->events.empty(); });
}

// ---------------------------------------------------------------- a program

Process::~Process() {
    if (state_) state_->events.reset();
}

void Process::terminate() {
    if (!state_ || state_->reported || state_->stop_requested.exchange(true)) return;
    request_stop(*state_);
}

bool Process::running() const { return state_ && !state_->reported; }

int64_t Process::pid() const { return state_ ? state_->pid : 0; }

// ---------------------------------------------------------------- lines

void LineSplitter::feed(std::string_view bytes, const std::function<void(std::string&&)>& line) {
    for (const char c : bytes) {
        if (after_cr_) {
            after_cr_ = false;
            if (c == '\n') continue; // (\r\n: one break)
        }
        if (c == '\n' || c == '\r') {
            after_cr_ = c == '\r';
            line(std::move(partial_));
            partial_.clear();
        } else {
            partial_ += c;
        }
    }
}

void LineSplitter::finish(const std::function<void(std::string&&)>& line) {
    if (!partial_.empty()) line(std::move(partial_));
    partial_.clear();
    after_cr_ = false;
}

// ---------------------------------------------------------------- Windows' command line

std::string windows_command_line(const std::vector<std::string>& argv) {
    // (Quotes only where needed, as Python's subprocess.list2cmdline: cmd.exe and other programs that read their
    // command line themselves take plain words as they are.)
    std::string out;
    for (size_t i = 0; i < argv.size(); ++i) {
        if (i) out += ' ';
        const std::string& arg = argv[i];
        const bool quote = arg.empty() || arg.find_first_of(" \t\n\v\"") != std::string::npos;
        if (i == 0) {
            // (The program: read up to the next quote, backslashes as they are; it has no quote in it.)
            out += quote ? "\"" + arg + "\"" : arg;
            continue;
        }
        if (quote) out += '"';
        size_t slashes = 0;
        for (const char c : arg) {
            if (c == '\\') {
                ++slashes;
                continue;
            }
            // Backslashes before a quote are doubled and the quote escaped; any others are as they are.
            out.append(c == '"' ? slashes * 2 + 1 : slashes, '\\');
            slashes = 0;
            out += c;
        }
        out.append(quote ? slashes * 2 : slashes, '\\'); // (doubled before the closing quote)
        if (quote) out += '"';
    }
    return out;
}

std::vector<std::string> split_windows_command_line(std::string_view line) {
    std::vector<std::string> out;
    size_t i = 0;
    // The program's name: in quotes up to the next quote, else up to a space or tab.
    {
        std::string arg;
        if (i < line.size() && line[i] == '"') {
            ++i;
            while (i < line.size() && line[i] != '"') arg += line[i++];
            if (i < line.size()) ++i;
        } else {
            while (i < line.size() && line[i] != ' ' && line[i] != '\t') arg += line[i++];
        }
        out.push_back(std::move(arg));
    }
    for (;;) {
        while (i < line.size() && (line[i] == ' ' || line[i] == '\t')) ++i;
        if (i >= line.size()) break;
        std::string arg;
        bool quoted = false;
        while (i < line.size()) {
            const char c = line[i];
            if (!quoted && (c == ' ' || c == '\t')) break;
            if (c == '\\') {
                size_t slashes = 0;
                while (i < line.size() && line[i] == '\\') {
                    ++slashes;
                    ++i;
                }
                if (i < line.size() && line[i] == '"') {
                    arg.append(slashes / 2, '\\');
                    if (slashes % 2) {
                        arg += '"';
                        ++i;
                    }
                } else {
                    arg.append(slashes, '\\');
                }
                continue;
            }
            if (c == '"') {
                // ("" inside quotes is a quote, as the MSVC runtime since 2008 and CommandLineToArgvW read it.)
                if (quoted && i + 1 < line.size() && line[i + 1] == '"') {
                    arg += '"';
                    i += 2;
                    continue;
                }
                quoted = !quoted;
                ++i;
                continue;
            }
            arg += c;
            ++i;
        }
        out.push_back(std::move(arg));
    }
    return out;
}

} // namespace launcher
