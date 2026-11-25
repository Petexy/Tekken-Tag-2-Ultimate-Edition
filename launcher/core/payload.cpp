// The release .exe's files (see payload.h). Moved here from
// launcher/windows/entry.cpp, unchanged in what it does.

#include "payload.h"

#include "sha256.h"

#ifdef _WIN32
#include "win32.h"
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

#include <algorithm>
#include <cstring>
#include <exception>
#include <fstream>
#include <set>
#include <sstream>
#include <stdexcept>

namespace launcher::payload {
namespace {

std::string shown(const fs::path& path) {
#ifdef _WIN32
    return win32::narrow(path.wstring());
#else
    return path.string();
#endif
}

fs::path from_utf8(const std::string& path) {
#ifdef _WIN32
    return fs::path(win32::wide(path));
#else
    return fs::path(path);
#endif
}

std::string read_file(const fs::path& path) {
#ifdef _WIN32
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
                              FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return {};
    LARGE_INTEGER size{};
    std::string out;
    if (GetFileSizeEx(file, &size) && size.QuadPart < (int64_t(1) << 31)) {
        out.resize(static_cast<size_t>(size.QuadPart));
        DWORD n = 0;
        if (!out.empty() && (!ReadFile(file, out.data(), static_cast<DWORD>(out.size()), &n, nullptr) || n != out.size()))
            out.clear();
    }
    CloseHandle(file);
    return out;
#else
    std::ifstream in(path, std::ios::binary);
    std::stringstream s;
    s << in.rdbuf();
    return s.str();
#endif
}

// Written beside the file, then renamed over it: never half a file.
void write_file(const fs::path& path, std::string_view data) {
    fs::path part = path;
    part += ".part";
#ifdef _WIN32
    HANDLE file = CreateFileW(part.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot write " + shown(part) + ".");
    bool ok = true;
    while (ok && !data.empty()) {
        const DWORD n = static_cast<DWORD>(std::min<size_t>(data.size(), 1 << 20));
        DWORD written = 0;
        ok = WriteFile(file, data.data(), n, &written, nullptr) && written == n;
        data.remove_prefix(n);
    }
    ok = CloseHandle(file) && ok;
    if (!ok || !MoveFileExW(part.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING)) {
        DeleteFileW(part.c_str());
        throw std::runtime_error("Cannot write " + shown(path) + ".");
    }
#else
    {
        std::ofstream out(part, std::ios::binary | std::ios::trunc);
        out.write(data.data(), static_cast<std::streamsize>(data.size()));
        if (!out) {
            std::error_code ec;
            fs::remove(part, ec);
            throw std::runtime_error("Cannot write " + shown(part) + ".");
        }
    }
    std::error_code ec;
    fs::rename(part, path, ec);
    if (ec) {
        fs::remove(part, ec);
        throw std::runtime_error("Cannot write " + shown(path) + ".");
    }
#endif
}

void remove_file(const fs::path& path) {
#ifdef _WIN32
    DeleteFileW(path.c_str());
#else
    std::error_code ec;
    if (fs::is_regular_file(fs::symlink_status(path, ec))) fs::remove(path, ec);
#endif
}

} // namespace

std::string Payload::digest() const { return hex(trailer.sha256, sizeof trailer.sha256); }

std::optional<Payload> read(std::string_view all, bool check) {
    if (all.size() < sizeof(Trailer)) throw std::runtime_error("Cannot read Golden Fist Launcher's own file.");
    Payload p;
    std::memcpy(&p.trailer, all.data() + all.size() - sizeof(Trailer), sizeof(Trailer));
    if (std::memcmp(p.trailer.magic, kMagic, sizeof kMagic) != 0) return std::nullopt;
    if (p.trailer.size > all.size() - sizeof(Trailer))
        throw std::runtime_error("This Golden Fist Launcher is incomplete: download it again.");
    p.files = std::string(all.substr(all.size() - sizeof(Trailer) - p.trailer.size, p.trailer.size));
    if (!check) return p;
    const auto digest = sha256(p.files);
    if (std::memcmp(digest.data(), p.trailer.sha256, 32) != 0)
        throw std::runtime_error("This Golden Fist Launcher is damaged: download it again.");
    return p;
}

std::vector<Entry> entries(const Payload& p) {
    std::vector<Entry> out;
    std::string_view rest = p.files;
    const auto take = [&](size_t n) {
        if (n > rest.size()) throw std::runtime_error("This Golden Fist Launcher is damaged: download it again.");
        const std::string_view part = rest.substr(0, n);
        rest.remove_prefix(n);
        return part;
    };
    const auto number = [&](size_t n) {
        uint64_t v = 0;
        std::memcpy(&v, take(n).data(), n);
        return v;
    };
    for (uint64_t i = 0; i < p.trailer.count; ++i) {
        std::string path(take(number(4)));
        const std::string_view data = take(number(8));
        // Only plain paths inside the folder: no "..", drive, or backslash.
        bool safe = !path.empty() && path.front() != '/' && path.find_first_of("\\:") == std::string::npos;
        for (size_t start = 0; safe && start <= path.size();) {
            const size_t end = std::min(path.find('/', start), path.size());
            const std::string_view part = std::string_view(path).substr(start, end - start);
            safe = !part.empty() && part != "." && part != "..";
            start = end + 1;
        }
        if (!safe) throw std::runtime_error("This Golden Fist Launcher holds an unsafe path: " + path);
        out.push_back({std::move(path), data});
    }
    if (!rest.empty()) throw std::runtime_error("This Golden Fist Launcher is damaged: download it again.");
    return out;
}

std::string unpacked_digest(const fs::path& root) {
    const std::string text = read_file(root / "local" / "launcher-files.txt");
    return text.substr(0, std::min(text.find('\n'), text.size()));
}

bool unpack(const Payload& p, const fs::path& root, bool again) {
    const fs::path stamp = root / "local" / "launcher-files.txt";
    const std::string digest = p.digest();
    std::vector<std::string> last;
    const std::string text = read_file(stamp);
    for (size_t start = 0; start < text.size();) {
        const size_t end = std::min(text.find('\n', start), text.size());
        last.push_back(text.substr(start, end - start));
        start = end + 1;
    }
    std::error_code ec;
    if (!again && !last.empty() && last[0] == digest &&
        fs::is_regular_file(root / "launcher" / "windows" / "main.py", ec))
        return false;
    std::set<std::string> now;
    std::string list = digest + "\n";
    for (const Entry& e : entries(p)) {
        const fs::path path = root / from_utf8(e.path);
        fs::create_directories(path.parent_path());
        write_file(path, e.data);
        now.insert(e.path);
        list += e.path + "\n";
    }
    for (size_t i = 1; i < last.size(); ++i) {
        if (last[i].empty() || now.count(last[i]) || last[i].find("..") != std::string::npos) continue;
        remove_file(root / from_utf8(last[i]));
    }
    fs::create_directories(stamp.parent_path());
    write_file(stamp, list);
    return true;
}

#ifdef _WIN32
std::optional<Payload> own(const fs::path& exe, bool check) {
    std::string all;
    if (HRSRC found = FindResourceW(nullptr, MAKEINTRESOURCEW(kFilesResource), MAKEINTRESOURCEW(10))) {
        HGLOBAL loaded = LoadResource(nullptr, found);
        const DWORD n = SizeofResource(nullptr, found);
        if (const void* data = loaded ? LockResource(loaded) : nullptr; data && n)
            all.assign(static_cast<const char*>(data), n);
    }
    if (all.empty()) all = read_file(exe);
    return read(all, check);
}

fs::path files_folder() {
    const std::wstring data = win32::environment(L"LOCALAPPDATA");
    if (data.empty()) throw std::runtime_error("LOCALAPPDATA is not set.");
    const std::wstring drive = win32::environment(L"SystemDrive");
    for (const std::wstring& base : {data, win32::environment(L"PUBLIC"), drive.empty() ? drive : drive + L"\\"}) {
        if (!base.empty() && std::all_of(base.begin(), base.end(), [](wchar_t c) { return c < 128; }))
            return fs::path(base) / L"TTT2Ultimate\\launcher";
    }
    return fs::path(data) / L"TTT2Ultimate\\launcher";
}

void unpack_own_again(const fs::path& exe, const fs::path& root) {
    const auto files = own(exe);
    if (!files) throw std::runtime_error("This launcher holds no files.");
    HANDLE lock = CreateMutexW(nullptr, FALSE, kFilesMutex);
    if (lock) WaitForSingleObject(lock, INFINITE);
    std::exception_ptr failed;
    try {
        unpack(*files, root, true);
    } catch (...) {
        failed = std::current_exception();
    }
    if (lock) {
        ReleaseMutex(lock);
        CloseHandle(lock);
    }
    if (failed) std::rethrow_exception(failed);
}
#endif

} // namespace launcher::payload
