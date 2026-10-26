#pragma once
#include <cstdint>
#include <ctime>

namespace cafe::host {
inline int64_t utc_offset(std::time_t seconds) {
    std::tm local{};
#ifdef _WIN32
    if (localtime_s(&local, &seconds) != 0) return 0;
    return static_cast<int64_t>(_mkgmtime64(&local) - seconds);
#else
    if (!localtime_r(&seconds, &local)) return 0;
    return local.tm_gmtoff;
#endif
}
}
