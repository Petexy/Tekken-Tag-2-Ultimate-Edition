#pragma once

// A path as UTF-8 text, and UTF-8 text as a path: the same on every OS and with every C++ library.
//
// The launcher's text is UTF-8 everywhere (its arguments, the JSON answers, the screen, SDL), but on Windows
// path::string(), generic_string() and path(std::string / const char*) use the ANSI code page with libc++ (the
// pinned llvm-mingw of a player's Set Up Game and of the ZIP route) and UTF-8 with libstdc++ (the release .exe).
// A José in C:\Users would then become "Jos\xe9" or "?" in libc++ builds. So for a path that can hold a letter
// beyond ASCII never use those: path_utf8() / path_utf8_generic() and utf8_path() instead. (The manifest's
// activeCodePage UTF-8 makes Windows 10 1903 and later use UTF-8 for them too; older ones and the tests need these.)
// On Linux they change nothing: a path's bytes stay as they are.

#include <filesystem>
#include <string>
#include <string_view>

namespace launcher {

inline std::string path_utf8(const std::filesystem::path& path) {
    const std::u8string text = path.u8string();
    return std::string(text.begin(), text.end());
}

// With '/' between its parts on every OS.
inline std::string path_utf8_generic(const std::filesystem::path& path) {
    const std::u8string text = path.generic_u8string();
    return std::string(text.begin(), text.end());
}

inline std::filesystem::path utf8_path(std::string_view text) {
    return std::filesystem::path(std::u8string(text.begin(), text.end()));
}

} // namespace launcher
