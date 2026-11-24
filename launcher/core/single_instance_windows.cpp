// One launcher per user on Windows: a mutex in this session and a named pipe
// (see single_instance.h).

#include "single_instance.h"

#include "win32.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <chrono>
#include <cstdlib>
#include <thread>

namespace launcher {

namespace {

using Clock = std::chrono::steady_clock;

double seconds_since(Clock::time_point t) { return std::chrono::duration<double>(Clock::now() - t).count(); }

std::wstring pipe_name(const std::string& name) {
    DWORD session = 0;
    ProcessIdToSessionId(GetCurrentProcessId(), &session);
    return L"\\\\.\\pipe\\" + win32::wide(name) + L"-" + std::to_wstring(session);
}

HANDLE new_pipe(const std::wstring& name, bool first) {
    return CreateNamedPipeW(name.c_str(),
                            PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | (first ? FILE_FLAG_FIRST_PIPE_INSTANCE : 0),
                            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                            PIPE_UNLIMITED_INSTANCES, 4096, 4096, 0, nullptr);
}

// One overlapped read or write on `pipe`, given up after `seconds` or when `stop` is set.
bool pipe_io(HANDLE pipe, bool reading, void* data, DWORD size, DWORD* done, double seconds, HANDLE stop) {
    OVERLAPPED ov{};
    ov.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ov.hEvent) return false;
    *done = 0;
    BOOL ok = reading ? ReadFile(pipe, data, size, done, &ov) : WriteFile(pipe, data, size, done, &ov);
    if (!ok && GetLastError() == ERROR_IO_PENDING) {
        HANDLE events[2] = {ov.hEvent, stop};
        const DWORD which = WaitForMultipleObjects(stop ? 2 : 1, events, FALSE, static_cast<DWORD>(seconds * 1000));
        if (which != WAIT_OBJECT_0) {
            CancelIoEx(pipe, &ov);
            GetOverlappedResult(pipe, &ov, done, TRUE);
            CloseHandle(ov.hEvent);
            return false;
        }
        ok = GetOverlappedResult(pipe, &ov, done, FALSE);
    }
    CloseHandle(ov.hEvent);
    return ok && (*done > 0 || size == 0);
}

bool read_until(HANDLE pipe, std::string* text, const char* until, double seconds, HANDLE stop) {
    const auto t0 = Clock::now();
    char buffer[4096];
    while (text->find(until) == std::string::npos) {
        const double left = seconds - seconds_since(t0);
        DWORD n = 0;
        if (left <= 0 || text->size() > (64 << 10) || !pipe_io(pipe, true, buffer, sizeof buffer, &n, left, stop))
            return false;
        text->append(buffer, n);
    }
    return true;
}

bool write_all(HANDLE pipe, const std::string& text, HANDLE stop) {
    DWORD n = 0;
    return pipe_io(pipe, false, const_cast<char*>(text.data()), static_cast<DWORD>(text.size()), &n, 5, stop) &&
           n == text.size();
}

} // namespace

struct SingleInstance::Os {
    HANDLE mutex = nullptr;
    HANDLE stop = nullptr;
    std::thread thread;
};

SingleInstance::SingleInstance() : shared_(std::make_shared<Shared>()), os_(std::make_unique<Os>()) {}

SingleInstance::~SingleInstance() {
    if (os_->stop) SetEvent(os_->stop);
    if (os_->thread.joinable()) os_->thread.join();
    if (os_->stop) CloseHandle(os_->stop);
    if (os_->mutex) CloseHandle(os_->mutex);
}

namespace {

void listen_for_starts(HANDLE pipe, std::wstring name, HANDLE stop, std::shared_ptr<SingleInstance::Shared> shared) {
    const std::string pid = std::to_string(GetCurrentProcessId());
    for (;;) {
        if (pipe == INVALID_HANDLE_VALUE) {
            pipe = new_pipe(name, false);
            if (pipe == INVALID_HANDLE_VALUE) {
                if (WaitForSingleObject(stop, 1000) == WAIT_OBJECT_0) return;
                continue;
            }
        }
        OVERLAPPED ov{};
        ov.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        bool connected = ConnectNamedPipe(pipe, &ov) != 0;
        if (!connected) {
            const DWORD error = GetLastError();
            if (error == ERROR_PIPE_CONNECTED) {
                connected = true;
            } else if (error == ERROR_IO_PENDING) {
                HANDLE events[2] = {ov.hEvent, stop};
                if (WaitForMultipleObjects(2, events, FALSE, INFINITE) != WAIT_OBJECT_0) {
                    CancelIoEx(pipe, &ov);
                    DWORD n = 0;
                    GetOverlappedResult(pipe, &ov, &n, TRUE);
                    CloseHandle(ov.hEvent);
                    CloseHandle(pipe);
                    return;
                }
                DWORD n = 0;
                connected = GetOverlappedResult(pipe, &ov, &n, FALSE) != 0;
            }
        }
        CloseHandle(ov.hEvent);
        std::string text;
        Forwarded message;
        if (connected && read_until(pipe, &text, "end\n", 2, stop) && decode_forwarded(text, &message)) {
            {
                std::lock_guard lock(shared->mutex);
                shared->arrived.push_back(std::move(message));
            }
            write_all(pipe, "ok " + pid + " " + shared->files + "\n", stop);
            FlushFileBuffers(pipe);
            if (shared->wake) shared->wake();
        }
        DisconnectNamedPipe(pipe);
        CloseHandle(pipe);
        pipe = INVALID_HANDLE_VALUE;
        if (WaitForSingleObject(stop, 0) == WAIT_OBJECT_0) return;
    }
}

enum class Handed { kOk, kNotListening, kNoAnswer };

Handed hand_over(const std::wstring& name, const InstanceOptions& options, InstanceClaim* claim) {
    HANDLE pipe = CreateFileW(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
                              FILE_FLAG_OVERLAPPED, nullptr);
    if (pipe == INVALID_HANDLE_VALUE) {
        if (GetLastError() == ERROR_PIPE_BUSY) WaitNamedPipeW(name.c_str(), 500);
        return Handed::kNotListening;
    }
    std::string reply;
    const bool ok = write_all(pipe, encode_forwarded(options.message), nullptr) &&
                    read_until(pipe, &reply, "\n", 5, nullptr) && reply.rfind("ok ", 0) == 0;
    CloseHandle(pipe);
    if (!ok) return Handed::kNoAnswer;
    const std::string rest = reply.substr(3, reply.find('\n') - 3);
    const size_t space = rest.find(' ');
    claim->other_pid = std::strtoll(rest.substr(0, space).c_str(), nullptr, 10);
    claim->other_files = space == std::string::npos ? "" : rest.substr(space + 1);
    // (Only the program the player started may take the foreground: it lets the running launcher take it.)
    if (claim->other_pid > 0) AllowSetForegroundWindow(static_cast<DWORD>(claim->other_pid));
    return Handed::kOk;
}

} // namespace

InstanceClaim claim_instance(const InstanceOptions& options) {
    InstanceClaim claim;
    const std::wstring mutex_name = L"Local\\" + win32::wide(options.name);
    const std::wstring pipe = pipe_name(options.name);
    const auto t0 = Clock::now();
    const double patience = options.after ? options.after_seconds : 2;
    for (;;) {
        HANDLE mutex = CreateMutexW(nullptr, FALSE, mutex_name.c_str());
        if (!mutex) {
            claim.result = InstanceClaim::Result::kAlone;
            claim.error = "cannot claim the launcher's name: " + win32::last_error_text();
            return claim;
        }
        if (GetLastError() != ERROR_ALREADY_EXISTS) {
            HANDLE first = new_pipe(pipe, true);
            if (first == INVALID_HANDLE_VALUE) {
                // (Someone else has the pipe's name: no second start can reach this one, but it runs.)
                claim.result = InstanceClaim::Result::kAlone;
                claim.error = "cannot listen for later starts: " + win32::last_error_text();
                CloseHandle(mutex);
                return claim;
            }
            auto instance = std::unique_ptr<SingleInstance>(new SingleInstance());
            instance->shared_->wake = options.wake;
            instance->shared_->files = options.files;
            instance->os_->mutex = mutex;
            instance->os_->stop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
            instance->os_->thread = std::thread(listen_for_starts, first, pipe, instance->os_->stop, instance->shared_);
            claim.result = InstanceClaim::Result::kPrimary;
            claim.instance = std::move(instance);
            return claim;
        }
        CloseHandle(mutex);
        if (!options.after) {
            const Handed handed = hand_over(pipe, options, &claim);
            if (handed == Handed::kOk) {
                claim.result = InstanceClaim::Result::kForwarded;
                return claim;
            }
            if (handed == Handed::kNoAnswer) {
                claim.result = InstanceClaim::Result::kAlone;
                claim.error = "the running launcher did not answer";
                return claim;
            }
        }
        if (seconds_since(t0) >= patience) {
            claim.result = options.after ? InstanceClaim::Result::kFailed : InstanceClaim::Result::kAlone;
            claim.error = options.after ? "Another Ultimate Launcher is still running: close it, then start this one "
                                          "again."
                                        : "the running launcher does not listen";
            return claim;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(options.after ? 100 : 50));
    }
}

} // namespace launcher
