// What the model looks at on Linux itself (preflight.h's SystemProbe, self_update.h's RealUpdateFiles): built only
// there, with launcher/core's Linux part (ttt2_launcher_core_linux).

#include "preflight.h"
#include "self_update.h"

namespace launcher::model {

bool SystemProbe::exists(const fs::path& path) {
    std::error_code ec;
    return fs::is_regular_file(path, ec) || fs::is_directory(path, ec);
}

std::optional<uint64_t> RealUpdateFiles::size(const fs::path& file) {
    std::error_code ec;
    const uintmax_t n = fs::file_size(file, ec);
    if (ec) return std::nullopt;
    return static_cast<uint64_t>(n);
}

void RealUpdateFiles::remove(const fs::path& file) {
    std::error_code ec;
    fs::remove(file, ec);
}

} // namespace launcher::model
