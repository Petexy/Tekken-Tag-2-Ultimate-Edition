#pragma once

// Host file operations: keep Unicode paths and 64-bit offsets on Windows.
#include <algorithm>
#include <cerrno>
#include <climits>
#include <cstdlib>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef _WIN32
#include <io.h>
#include <mutex>
#include <windows.h>
#endif

namespace cafe::host::file {
inline std::filesystem::path home(const std::filesystem::path& fallback = "/") {
    const char* value = std::getenv("HOME");
#ifdef _WIN32
    if (!value || !*value) value = std::getenv("USERPROFILE");
#endif
    return value && *value ? std::filesystem::path(value) : fallback;
}

#ifdef _WIN32
using Stat = struct _stat64;
inline int stat(const std::filesystem::path& path, Stat* out) { return _wstat64(path.c_str(), out); }
inline int fstat(int fd, Stat* out) { return _fstat64(fd, out); }
inline int open(const std::filesystem::path& path, int flags, int mode = 0644) {
    return _wopen(path.c_str(), flags | _O_BINARY | _O_NOINHERIT, mode);
}
inline int sync(int fd) { return _commit(fd); }
inline int sync_data(int fd) { return _commit(fd); }
inline std::mutex positional_io_mutex;
inline ssize_t read_at(int fd, void* data, size_t size, uint64_t offset) {
    // Guest reads can share a descriptor after releasing the VFS mutex.
    // Keep the seek and transfer atomic with respect to other positional I/O.
    std::lock_guard lock(positional_io_mutex);
    if (_lseeki64(fd, static_cast<int64_t>(offset), SEEK_SET) < 0) return -1;
    return _read(fd, data, static_cast<unsigned>(std::min<size_t>(size, INT_MAX)));
}
inline ssize_t write_at(int fd, const void* data, size_t size, uint64_t offset) {
    std::lock_guard lock(positional_io_mutex);
    if (_lseeki64(fd, static_cast<int64_t>(offset), SEEK_SET) < 0) return -1;
    return _write(fd, data, static_cast<unsigned>(std::min<size_t>(size, INT_MAX)));
}
inline std::filesystem::path executable() {
    std::wstring path(32768, L'\0');
    const DWORD size = GetModuleFileNameW(nullptr, path.data(), static_cast<DWORD>(path.size()));
    if (!size || size >= path.size()) throw std::runtime_error("cannot find this executable");
    path.resize(size);
    return path;
}
#else
using Stat = struct ::stat;
inline int stat(const std::filesystem::path& path, Stat* out) { return ::stat(path.c_str(), out); }
inline int fstat(int fd, Stat* out) { return ::fstat(fd, out); }
inline int open(const std::filesystem::path& path, int flags, int mode = 0644) {
    return ::open(path.c_str(), flags | O_CLOEXEC, mode);
}
inline int sync(int fd) { return ::fsync(fd); }
inline int sync_data(int fd) { return ::fdatasync(fd); }
inline ssize_t read_at(int fd, void* data, size_t size, uint64_t offset) { return ::pread(fd, data, size, offset); }
inline ssize_t write_at(int fd, const void* data, size_t size, uint64_t offset) { return ::pwrite(fd, data, size, offset); }
inline std::filesystem::path executable() { return std::filesystem::read_symlink("/proc/self/exe"); }
#endif
} // namespace cafe::host::file
