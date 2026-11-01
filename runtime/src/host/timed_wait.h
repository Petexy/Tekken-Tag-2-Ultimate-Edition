#pragma once

// Timed condition variable waits that sleep on Windows too. Windows' libc++
// (llvm-mingw) cuts a timed wait down to whole milliseconds and returns at
// once below one, so a wait looping to its deadline (its own wait_for with a
// predicate among them) spins on the lock for the last millisecond. There
// these wait whole milliseconds instead, rounded up (up to ~1 ms late);
// elsewhere they are the standard waits.

#include <chrono>
#include <condition_variable>
#include <mutex>

namespace cafe::host {

// Waits on `cv` until notified or about `timeout` has passed.
inline void timed_wait(std::condition_variable& cv, std::unique_lock<std::mutex>& lock,
                       std::chrono::nanoseconds timeout) {
#ifdef _WIN32
    // (libc++ rounds down what is left when it gets to wait: 999 us more
    // keeps the whole milliseconds asked for)
    cv.wait_for(lock, std::chrono::ceil<std::chrono::milliseconds>(timeout) + std::chrono::microseconds(999));
#else
    cv.wait_for(lock, timeout);
#endif
}

// Waits on `cv` until `ready()` holds or `timeout` has passed; returns
// whether it holds, as condition_variable::wait_for with a predicate.
template <typename Predicate>
bool timed_wait(std::condition_variable& cv, std::unique_lock<std::mutex>& lock, std::chrono::nanoseconds timeout,
                Predicate ready) {
#ifdef _WIN32
    // (on its own deadline: libc++'s loop to it would spin)
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    while (!ready()) {
        const auto left = deadline - std::chrono::steady_clock::now();
        if (left <= left.zero()) return false;
        timed_wait(cv, lock, left);
    }
    return true;
#else
    return cv.wait_for(lock, timeout, ready);
#endif
}

} // namespace cafe::host
