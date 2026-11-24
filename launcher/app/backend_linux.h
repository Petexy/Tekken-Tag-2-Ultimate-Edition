#pragma once

// What the launcher asks of Linux (as the GTK app did; spec/linux_app.md 2.0, 8): the pieces it runs and their
// versions (the facts at start), the install and the game (Environment), the AppImage's files. (What any OS has
// through SDL: backend.h.)

#include "backend.h"
#include "paths.h"

#include <optional>
#include <string>

namespace launcher::app {

namespace fs = std::filesystem;

// The facts before anything is asked (spec 2.0): kit, importer, Python, this build, the AppImage, the .wua given,
// Steam's last answer kept, the distribution, the saves. `banner`: the stderr line the GTK app printed.
model::Facts start_facts(const Places& places, const fs::path& program_dir, const fs::path& chosen_game,
                         std::optional<fs::path>* appimage, std::string* banner);

class LinuxEnvironment final : public model::Environment {
public:
    explicit LinuxEnvironment(Places places) : places_(std::move(places)) {}
    void look(model::Facts& facts) override;
    bool game_runs(const model::Facts& facts) override;
    std::optional<fs::path> install_target(const fs::path& chosen, std::string* why) override;
    void write_started_record(const fs::path& folder, const fs::path& game) override;
    bool started(const fs::path& folder) override;
    void forget_started_record() override;
    std::string log_end(const fs::path& log) override;
    bool exists(const fs::path& path) override;
    fs::path build_work() override { return places_.build_work(); }

private:
    Places places_;
};

// C2 (an AppImage after its update): this start drew its first frame, so the version before is not needed any more.
void appimage_first_frame();
// This start cannot open its window: the version before an update put back when it is kept. What the player is
// told then (empty: nothing was kept).
std::string appimage_no_window();

struct LinuxUpdateFiles final : model::RealUpdateFiles {
    std::string sha256(const fs::path& file) override;
};

} // namespace launcher::app
