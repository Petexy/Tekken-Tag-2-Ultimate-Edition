// Where things are, what is the same on any OS (see paths.h; paths.cpp:
// Linux's places).

#include "paths.h"

#include <fstream>

namespace launcher {
namespace {

bool starts_with(const fs::path& path, const fs::path& folder) {
    auto p = path.begin();
    for (auto f = folder.begin(); f != folder.end(); ++f, ++p) {
        if (p == path.end() || *p != *f) return false;
    }
    return true;
}

} // namespace

std::string first_line(const fs::path& file) {
    std::ifstream in(file);
    std::string line;
    if (!in || !std::getline(in, line)) return {};
    if (!line.empty() && line.back() == '\r') line.pop_back();
    return line;
}

fs::path normal(const fs::path& path) {
    std::error_code ec;
    fs::path out = fs::absolute(path, ec).lexically_normal();
    if (!out.has_filename() && out.has_relative_path()) out = out.parent_path(); // a trailing slash
    return out;
}

bool inside(const fs::path& path, const fs::path& folder) {
    if (starts_with(normal(path), normal(folder))) return true;
    std::error_code ec, ec2;
    const fs::path real_path = fs::weakly_canonical(path, ec), real_folder = fs::weakly_canonical(folder, ec2);
    return !ec && !ec2 && starts_with(normal(real_path), normal(real_folder));
}

} // namespace launcher
