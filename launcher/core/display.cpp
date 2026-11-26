// The game's display settings (see display.h).

#include "display.h"
#include "utf8_path.h"

#include "files.h"
#include "i18n.h"

#include <algorithm>
#include <cmath>

namespace launcher {
namespace {

std::string size_text(float scale) {
    return std::to_string(std::lround(1280 * scale)) + " × " + std::to_string(std::lround(720 * scale));
}

} // namespace

bool save_display(const fs::path& file, const display::Settings& settings, std::string* error) {
    return replace_file(file, display::format(settings), error);
}

std::string resolution_label(display::Resolution resolution) {
    const float scale = display::scale_of(resolution);
    return scale > 0 ? size_text(scale) : i18n::tr("settings.automatic", "Automatic");
}

std::string automatic_size(uint32_t display_height) { return size_text(display::auto_scale(display_height)); }

std::string automatic_note(const std::vector<Monitor>& monitors) {
    using i18n::tr;
    if (monitors.size() > 1) return tr("display.auto_main", "Automatic: enough to cover the main display.");
    if (monitors.empty() || !monitors[0].height) return tr("display.auto", "Automatic: enough to cover the display.");
    return tr("display.auto_size", "Automatic: enough to cover the display ({size} on this one).",
              {{"size", automatic_size(monitors[0].height)}});
}

std::string refresh_note(const std::vector<Monitor>& monitors) {
    int most = 0;
    for (const Monitor& m : monitors) {
        if (m.refresh <= 0 || m.refresh >= display::kInterpolationHz * 1000) return {};
        most = std::max(most, m.refresh);
    }
    if (monitors.empty()) return {};
    using i18n::tr;
    const std::string rate = hertz_text(most);
    const i18n::Args args = {{"rate", i18n::decimal(rate)}};
    if (monitors.size() == 1)
        return tr("display.refresh_one", "This display refreshes at {rate} Hz: the game stays at 60 fps there.", args);
    const bool same = std::all_of(monitors.begin(), monitors.end(),
                                  [&](const Monitor& m) { return hertz_text(m.refresh) == rate; });
    return same ? tr("display.refresh_all", "These displays refresh at {rate} Hz: the game stays at 60 fps.", args)
                : tr("display.refresh_most", "These displays refresh at up to {rate} Hz: the game stays at 60 fps.",
                     args);
}

std::string hertz_text(int millihertz) {
    const long whole = std::lround(millihertz / 1000.0);
    if (whole < display::kInterpolationHz || millihertz >= display::kInterpolationHz * 1000) {
        return std::to_string(whole);
    }
    // (Cut, not rounded: 99.999 Hz reads 99.99, never 100.)
    const int hundredths = millihertz / 10;
    std::string text = std::to_string(hundredths / 100) + "." + std::to_string(hundredths / 10 % 10) +
                       std::to_string(hundredths % 10);
    while (text.back() == '0') text.pop_back();
    if (text.back() == '.') text.pop_back();
    return text;
}

std::string unreadable_reason(const std::string& error, const fs::path& file) {
    const std::string name = path_utf8(file), unread = "cannot read " + name + ": ";
    if (error.starts_with(unread)) return error.substr(unread.size());
    if (error.starts_with(name + " ")) return "it" + error.substr(name.size());
    return error;
}

} // namespace launcher
