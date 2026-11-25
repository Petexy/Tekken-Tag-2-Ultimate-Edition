// Programs the launcher runs, on Windows (see subprocess.h): CreateProcessW, a Job
// Object per task, and a reader thread per program waiting on its overlapped
// pipes, its process and an event that wakes it to stop the program.

#include "subprocess_internal.h"

#include "win32.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <thread>

namespace launcher {

using win32::wide;

struct Process::State::Os {
    HANDLE wake = nullptr; // terminate() sets it
};

Process::State::~State() {
    if (os && os->wake) CloseHandle(os->wake);
}

namespace {

void close_handle(HANDLE& h) {
    if (h && h != INVALID_HANDLE_VALUE) CloseHandle(h);
    h = nullptr;
}

bool same_name(const std::wstring& a, const std::wstring& b) {
    return CompareStringOrdinal(a.c_str(), static_cast<int>(a.size()), b.c_str(), static_cast<int>(b.size()),
                                TRUE) == CSTR_EQUAL;
}

std::wstring name_of(const std::wstring& entry) {
    // ("=C:=C:\..." entries: the drive's folder; their name starts after the first '='.)
    const size_t equals = entry.find(L'=', entry.empty() || entry[0] != L'=' ? 0 : 1);
    return entry.substr(0, equals);
}

// The launcher's environment with `env` set over it, as CreateProcessW takes it (sorted by name, case ignored).
std::wstring environment_block(const std::vector<std::pair<std::string, std::string>>& env) {
    std::vector<std::wstring> entries;
    if (wchar_t* block = GetEnvironmentStringsW()) {
        for (const wchar_t* e = block; *e; e += wcslen(e) + 1) entries.emplace_back(e);
        FreeEnvironmentStringsW(block);
    }
    for (const auto& [name, value] : env) {
        const std::wstring n = wide(name);
        entries.erase(std::remove_if(entries.begin(), entries.end(),
                                     [&](const std::wstring& e) { return same_name(name_of(e), n); }),
                      entries.end());
        entries.push_back(n + L"=" + wide(value));
    }
    std::stable_sort(entries.begin(), entries.end(), [](const std::wstring& a, const std::wstring& b) {
        const std::wstring na = name_of(a), nb = name_of(b);
        return CompareStringOrdinal(na.c_str(), static_cast<int>(na.size()), nb.c_str(), static_cast<int>(nb.size()),
                                    TRUE) == CSTR_LESS_THAN;
    });
    std::wstring out;
    for (const std::wstring& e : entries) {
        out += e;
        out += L'\0';
    }
    out += L'\0';
    return out;
}

// A pipe the program writes to (its end inheritable) and the launcher reads with overlapped I/O (anonymous pipes
// cannot do that).
bool make_pipe(HANDLE* read, HANDLE* write) {
    static std::atomic<unsigned> serial{0};
    const std::wstring name = L"\\\\.\\pipe\\ttt2-launcher-" + std::to_wstring(GetCurrentProcessId()) + L"-" +
                              std::to_wstring(serial++) + L"-" + std::to_wstring(GetTickCount64());
    *read = CreateNamedPipeW(name.c_str(), PIPE_ACCESS_INBOUND | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
                             PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS, 1, 0,
                             1 << 16, 0, nullptr);
    if (*read == INVALID_HANDLE_VALUE) {
        *read = nullptr;
        return false;
    }
    SECURITY_ATTRIBUTES sa{sizeof sa, nullptr, TRUE};
    *write = CreateFileW(name.c_str(), GENERIC_WRITE, 0, &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (*write == INVALID_HANDLE_VALUE) {
        *write = nullptr;
        close_handle(*read);
        return false;
    }
    // (Connected already, by the CreateFileW above: ConnectNamedPipe says so.)
    OVERLAPPED connect{};
    connect.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ConnectNamedPipe(*read, &connect) && GetLastError() == ERROR_IO_PENDING) {
        DWORD n = 0;
        GetOverlappedResult(*read, &connect, &n, TRUE);
    }
    CloseHandle(connect.hEvent);
    return true;
}

// A pipe the program reads its standard input from (its end inheritable), with room for `size` bytes, so that the
// launcher's write does not wait for the program.
bool make_input_pipe(size_t size, HANDLE* write, HANDLE* read) {
    static std::atomic<unsigned> serial{0};
    const std::wstring name = L"\\\\.\\pipe\\ttt2-launcher-in-" + std::to_wstring(GetCurrentProcessId()) + L"-" +
                              std::to_wstring(serial++) + L"-" + std::to_wstring(GetTickCount64());
    *write = CreateNamedPipeW(name.c_str(), PIPE_ACCESS_OUTBOUND | FILE_FLAG_FIRST_PIPE_INSTANCE,
                              PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS, 1,
                              static_cast<DWORD>(size + 4096), 0, 0, nullptr);
    if (*write == INVALID_HANDLE_VALUE) {
        *write = nullptr;
        return false;
    }
    SECURITY_ATTRIBUTES sa{sizeof sa, nullptr, TRUE};
    *read = CreateFileW(name.c_str(), GENERIC_READ, 0, &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (*read == INVALID_HANDLE_VALUE) {
        *read = nullptr;
        close_handle(*write);
        return false;
    }
    return true;
}

struct Pipe {
    HANDLE handle = nullptr;
    OVERLAPPED ov{};
    bool pending = false;
    bool error = false; // standard error
    LineSplitter lines;
    char buffer[1 << 16];
};

struct Reader {
    std::shared_ptr<Process::State> state;
    HANDLE process = nullptr, job = nullptr, log = nullptr;
    Pipe out, err;

    void push_line(std::string&& text, bool error) {
        if (log) {
            const std::string copy = text + "\r\n";
            DWORD n = 0;
            WriteFile(log, copy.data(), static_cast<DWORD>(copy.size()), &n, nullptr);
        }
        state->host->push({state, false, error, 0, std::move(text)});
    }

    void end_of(Pipe& p) {
        p.lines.finish([&](std::string&& l) { push_line(std::move(l), p.error); });
        p.pending = false;
        close_handle(p.handle);
        close_handle(p.ov.hEvent);
    }

    void got(Pipe& p, DWORD n) {
        p.lines.feed({p.buffer, n}, [&](std::string&& l) { push_line(std::move(l), p.error); });
    }

    // Reads what is there and asks for more; ends the pipe at its end.
    void read(Pipe& p) {
        while (p.handle) {
            ResetEvent(p.ov.hEvent);
            DWORD n = 0;
            if (ReadFile(p.handle, p.buffer, sizeof p.buffer, &n, &p.ov)) {
                if (!GetOverlappedResult(p.handle, &p.ov, &n, FALSE)) return end_of(p);
                got(p, n);
                continue;
            }
            if (GetLastError() == ERROR_IO_PENDING) {
                p.pending = true;
                return;
            }
            return end_of(p); // (ERROR_BROKEN_PIPE: the program and all it started closed it)
        }
    }

    // Its pending read came back.
    void completed(Pipe& p) {
        DWORD n = 0;
        if (GetOverlappedResult(p.handle, &p.ov, &n, FALSE)) {
            p.pending = false;
            got(p, n);
            read(p);
        } else if (GetLastError() != ERROR_IO_INCOMPLETE) {
            end_of(p);
        }
    }

    void stop_all() {
        if (job) TerminateJobObject(job, 1);
        else if (process) TerminateProcess(process, 1);
    }

    void run() {
        ProcessHost::Shared& host = *state->host;
        const bool task = state->mode == ProcessSpec::Mode::kTask;
        bool exited = false, stopping = false, killed = false;
        int code = 1;
        Clock::time_point kill_at{}, drain_until{};
        for (Pipe* p : {&out, &err}) {
            if (p->handle) read(*p);
        }
        for (;;) {
            if (exited && ((!out.handle && !err.handle) || Clock::now() >= drain_until)) break;
            HANDLE handles[4];
            DWORD n = 0;
            int wake_at = -1, process_at = -1, out_at = -1, err_at = -1;
            if (!exited) {
                handles[wake_at = static_cast<int>(n++)] = state->os->wake;
                handles[process_at = static_cast<int>(n++)] = process;
            }
            if (out.handle) handles[out_at = static_cast<int>(n++)] = out.ov.hEvent;
            if (err.handle) handles[err_at = static_cast<int>(n++)] = err.ov.hEvent;
            double timeout = -1;
            const auto until = [&](Clock::time_point t) {
                const double s = std::max(0.0, std::chrono::duration<double>(t - Clock::now()).count());
                timeout = timeout < 0 ? s : std::min(timeout, s);
            };
            if (!exited && stopping && !killed && task) until(kill_at);
            if (exited) until(drain_until);
            const DWORD ms = timeout < 0 ? INFINITE : static_cast<DWORD>(timeout * 1000) + 1;
            const DWORD r = n ? WaitForMultipleObjects(n, handles, FALSE, ms) : WAIT_TIMEOUT;
            if (r == WAIT_FAILED) break;
            const int at = r >= WAIT_OBJECT_0 && r < WAIT_OBJECT_0 + n ? static_cast<int>(r - WAIT_OBJECT_0) : -1;
            if (at >= 0 && at == wake_at && state->stop_requested && !stopping) {
                stopping = true;
                if (task) {
                    // With a cancel file (made by terminate()) the worker stops what it started and ends; without
                    // one, it is ended now. The update workers are never ended.
                    if (state->cancel_file.empty()) stop_all();
                    kill_at = Clock::now() + std::chrono::duration_cast<Clock::duration>(
                                                 std::chrono::duration<double>(host.stop_seconds.load()));
                }
            }
            if (at >= 0 && at == out_at) completed(out);
            if (at >= 0 && at == err_at) completed(err);
            if (!exited && WaitForSingleObject(process, 0) == WAIT_OBJECT_0) {
                exited = true;
                DWORD status = 1;
                GetExitCodeProcess(process, &status);
                code = static_cast<int>(status);
                // Stopped: nothing it started stays.
                if (stopping && task && job) TerminateJobObject(job, 1);
                drain_until = Clock::now() + std::chrono::duration_cast<Clock::duration>(
                                                 std::chrono::duration<double>(host.drain_seconds.load()));
            } else if (!exited && stopping && task && !killed && Clock::now() >= kill_at) {
                killed = true;
                stop_all();
            }
        }
        for (Pipe* p : {&out, &err}) {
            if (p->handle && p->pending) {
                CancelIoEx(p->handle, &p->ov);
                DWORD n = 0;
                GetOverlappedResult(p->handle, &p->ov, &n, TRUE);
            }
            if (p->handle) end_of(*p);
        }
        close_handle(process);
        close_handle(log);
        // (A task's job: what is left in it ends with this handle, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.)
        close_handle(job);
        host.push({state, true, false, code, {}});
    }
};

} // namespace

void request_stop(Process::State& state) {
    if (!state.cancel_file.empty()) {
        // (The worker looks for it every 0.2 s, or between a download's parts.)
        HANDLE f = CreateFileW(state.cancel_file.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE, nullptr,
                               CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        close_handle(f);
    }
    if (state.os && state.os->wake) SetEvent(state.os->wake);
}

std::shared_ptr<Process::State> start_process(const std::shared_ptr<ProcessHost::Shared>& host,
                                              const ProcessSpec& spec, std::string* error) {
    const auto fail = [&](const std::string& why) -> std::shared_ptr<Process::State> {
        if (error) *error = why;
        return nullptr;
    };
    const bool task = spec.mode != ProcessSpec::Mode::kDetached;
    SECURITY_ATTRIBUTES inherit{sizeof inherit, nullptr, TRUE};
    if (spec.input.size() > ProcessSpec::kMaxInput) return fail("too much input for " + spec.argv[0]);
    // Standard input: NUL, or a pipe the input is written to (its buffer holds all of it).
    HANDLE input = nullptr, in = nullptr;
    if (task && !spec.input.empty()) {
        if (!make_input_pipe(spec.input.size(), &input, &in)) return fail("cannot make pipes: " + win32::last_error_text());
    } else {
        in = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &inherit, OPEN_EXISTING,
                         FILE_ATTRIBUTE_NORMAL, nullptr);
        if (in == INVALID_HANDLE_VALUE) return fail("cannot open NUL: " + win32::last_error_text());
    }
    HANDLE out_read = nullptr, out_write = nullptr, err_read = nullptr, err_write = nullptr, output = nullptr,
           log = nullptr;
    const auto close_all = [&] {
        for (HANDLE* h : {&input, &in, &out_read, &out_write, &err_read, &err_write, &output, &log}) close_handle(*h);
    };
    if (task) {
        if (!make_pipe(&out_read, &out_write) || !make_pipe(&err_read, &err_write)) {
            const std::string why = win32::last_error_text();
            close_all();
            return fail("cannot make pipes: " + why);
        }
        if (!spec.output.empty()) {
            log = CreateFileW(spec.output.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE, nullptr,
                              CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (log == INVALID_HANDLE_VALUE) log = nullptr;
        }
    } else if (!spec.output.empty()) {
        output = CreateFileW(spec.output.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_DELETE, &inherit,
                             CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (output == INVALID_HANDLE_VALUE) output = nullptr;
    }

    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb = sizeof startup;
    HANDLE std_out = task ? out_write : output, std_err = task ? err_write : output;
    std::vector<HANDLE> inherited;
    if (std_out) {
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = in;
        startup.StartupInfo.hStdOutput = std_out;
        startup.StartupInfo.hStdError = std_err;
        for (HANDLE h : {in, std_out, std_err}) {
            if (std::find(inherited.begin(), inherited.end(), h) == inherited.end()) inherited.push_back(h);
        }
    }
    // Only these are inherited, whatever else the launcher has open as inheritable (another start's, at once).
    SIZE_T list_size = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &list_size);
    std::vector<char> list_memory(list_size);
    auto* list = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(list_memory.data());
    bool with_list = !inherited.empty() && InitializeProcThreadAttributeList(list, 1, 0, &list_size) &&
                     UpdateProcThreadAttribute(list, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited.data(),
                                               inherited.size() * sizeof(HANDLE), nullptr, nullptr);
    if (with_list) startup.lpAttributeList = list;

    std::wstring command = wide(windows_command_line(spec.argv));
    std::wstring env = environment_block(spec.env);
    const std::wstring cwd = spec.cwd.wstring();
    DWORD flags = CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW | (with_list ? EXTENDED_STARTUPINFO_PRESENT : 0);
    if (spec.mode == ProcessSpec::Mode::kTask) flags |= CREATE_SUSPENDED;
    if (spec.mode == ProcessSpec::Mode::kDetached) flags |= CREATE_NEW_PROCESS_GROUP;
    // The game and the update workers outlive the launcher: out of a job it may run in (Steam's, say), when
    // that job lets them.
    const bool breakaway = spec.mode != ProcessSpec::Mode::kTask;
    PROCESS_INFORMATION info{};
    BOOL started = FALSE;
    DWORD code = 0;
    for (int attempt = breakaway ? 0 : 1; attempt < 2 && !started; ++attempt) {
        std::vector<wchar_t> line(command.begin(), command.end());
        line.push_back(L'\0');
        started = CreateProcessW(nullptr, line.data(), nullptr, nullptr, !inherited.empty(),
                                 flags | (attempt == 0 ? CREATE_BREAKAWAY_FROM_JOB : 0), env.data(),
                                 cwd.empty() ? nullptr : cwd.c_str(), &startup.StartupInfo, &info);
        code = started ? 0 : GetLastError();
    }
    if (with_list) DeleteProcThreadAttributeList(list);
    close_handle(in);
    close_handle(out_write);
    close_handle(err_write);
    close_handle(output);
    if (!started) {
        close_all();
        return fail("cannot run " + spec.argv[0] + ": " + win32::error_text(code));
    }

    if (input) {
        // (Written on a thread of its own: a program that writes before it reads never waits for this one.)
        std::thread([input, data = spec.input] {
            DWORD written = 0;
            WriteFile(input, data.data(), static_cast<DWORD>(data.size()), &written, nullptr);
            FlushFileBuffers(input);
            CloseHandle(input);
        }).detach();
        input = nullptr;
    }

    HANDLE job = nullptr;
    if (spec.mode == ProcessSpec::Mode::kTask) {
        job = CreateJobObjectW(nullptr, nullptr);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if (!job || !SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof limits) ||
            !AssignProcessToJobObject(job, info.hProcess)) {
            close_handle(job); // (then Cancel ends the program alone)
        }
        ResumeThread(info.hThread);
    }
    CloseHandle(info.hThread);

    auto state = std::make_shared<Process::State>();
    state->host = host;
    state->mode = spec.mode;
    state->cancel_file = spec.cancel_file;
    state->pid = info.dwProcessId;
    state->os = std::make_unique<Process::State::Os>();
    state->os->wake = CreateEventW(nullptr, FALSE, FALSE, nullptr);

    auto reader = std::make_shared<Reader>();
    reader->state = state;
    reader->process = info.hProcess;
    reader->job = job;
    reader->log = log;
    reader->out.handle = out_read;
    reader->err.handle = err_read;
    reader->err.error = true;
    for (Pipe* p : {&reader->out, &reader->err}) {
        if (!p->handle) continue;
        p->ov.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    }
    std::thread([reader] { reader->run(); }).detach();
    return state;
}

} // namespace launcher
