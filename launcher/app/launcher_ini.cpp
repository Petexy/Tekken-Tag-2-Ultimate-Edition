#include "launcher_ini.h"
#include "utf8_path.h"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <sstream>
#include <system_error>

namespace launcher::app {

model::LauncherSettings read_launcher_ini(const std::filesystem::path& file) {
    model::LauncherSettings s;
    std::ifstream in(file);
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const size_t eq = line.find('=');
        if (eq == std::string::npos || line.starts_with('#') || line.starts_with(';')) continue;
        std::string key = line.substr(0, eq), value = line.substr(eq + 1);
        const auto trim = [](std::string& t) {
            while (!t.empty() && (t.back() == ' ' || t.back() == '\t')) t.pop_back();
            while (!t.empty() && (t.front() == ' ' || t.front() == '\t')) t.erase(t.begin());
        };
        trim(key);
        trim(value);
        const bool yes = value == "1" || value == "yes" || value == "true" || value == "on";
        const bool no = value == "0" || value == "no" || value == "false" || value == "off";
        if (key == "sounds" && (yes || no)) s.sounds = yes;
        else if (key == "reduce_motion" && (yes || no)) s.reduce_motion = yes;
        else if (key == "text_size") {
            const int v = std::atoi(value.c_str());
            if (std::find(std::begin(model::kTextSizes), std::end(model::kTextSizes), v) != std::end(model::kTextSizes))
                s.text_size = v;
        } else if (key == "prompts") {
            for (size_t i = 0; i < std::size(model::kPrompts); ++i) {
                std::string name = model::kPrompts[i];
                std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return std::tolower(c); });
                if (value == name) s.prompts = static_cast<int>(i);
            }
        }
    }
    return s;
}

bool write_launcher_ini(const std::filesystem::path& file, const model::LauncherSettings& s, std::string* error) {
    std::string prompts = model::kPrompts[std::clamp(s.prompts, 0, static_cast<int>(std::size(model::kPrompts)) - 1)];
    std::transform(prompts.begin(), prompts.end(), prompts.begin(), [](unsigned char c) { return std::tolower(c); });
    std::ostringstream o;
    o << "# Ultimate Launcher's own settings (Settings > Launcher)\n"
      << "sounds=" << (s.sounds ? "yes" : "no") << "\n"
      << "reduce_motion=" << (s.reduce_motion ? "yes" : "no") << "\n"
      << "prompts=" << prompts << "\n"
      << "text_size=" << s.text_size << "\n";
    std::error_code ec;
    if (!file.parent_path().empty()) std::filesystem::create_directories(file.parent_path(), ec);
    std::filesystem::path tmp = file;
    tmp += ".new";
    {
        std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
        out << o.str();
        if (!out) {
            if (error) *error = "cannot write " + path_utf8(tmp);
            return false;
        }
    }
    std::filesystem::rename(tmp, file, ec);
    if (ec) {
        if (error) *error = "cannot write " + path_utf8(file) + ": " + ec.message();
        return false;
    }
    return true;
}

} // namespace launcher::app
