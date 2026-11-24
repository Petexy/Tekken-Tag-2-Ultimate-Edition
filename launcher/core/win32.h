#pragma once

// Windows only: UTF-8 <-> UTF-16, environment variables and the system's
// words for an error, for the launcher's Windows parts (process, single
// instance, the .exe's start).

#ifdef _WIN32

#include <cstdint>
#include <string>
#include <string_view>

namespace launcher::win32 {

std::wstring wide(std::string_view text);
std::string narrow(std::wstring_view text);
// A variable of the launcher's environment ("" when unset).
std::wstring environment(const wchar_t* name);
// The system's words for an error code (GetLastError), without the line break: "Access is denied."
std::string error_text(uint32_t code);
std::string last_error_text();

} // namespace launcher::win32

#endif
