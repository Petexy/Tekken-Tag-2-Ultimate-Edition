#pragma once

// Test stand-ins for what the model is given: programs (FakeStarter: each
// started program's lines and end are queued and delivered by pump(), as a
// real one's arrive later), the PC (FakeEnvironment) and the AppImage's files.

#include "model.h"

#include <deque>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace launcher::model::testing {

struct Run {
    Command command;
    JobEvents events;
    std::vector<std::pair<std::string, bool>> lines; // (line, stderr)
    int code = 0;
    bool terminated = false;
    bool held = false;      // not ended until released (a task stopped by Cancel)
    int terminate_code = 143;
    size_t next = 0;
};

// What a program answers: its lines and code, decided from its argv when it starts.
using Script = std::function<void(Run&)>;

class FakeStarter final : public Starter {
public:
    explicit FakeStarter(Script script = {}) : script_(std::move(script)) {}
    void set_script(Script script) { script_ = std::move(script); }
    std::string fail; // the next start fails with this

    std::unique_ptr<Job> start(const Command& command, JobEvents events, std::string* error) override {
        if (!fail.empty()) {
            if (error) *error = fail;
            fail.clear();
            return nullptr;
        }
        auto run = std::make_shared<Run>();
        run->command = command;
        run->events = std::move(events);
        if (script_) script_(*run);
        runs_.push_back(run);
        started.push_back(command);
        struct FakeJob final : Job {
            std::shared_ptr<Run> run;
            void terminate() override { run->terminated = true; }
        };
        auto job = std::make_unique<FakeJob>();
        job->run = run;
        return job;
    }

    // Delivers one line (or the end) of the oldest program that has more; false when none has.
    bool step() {
        for (auto it = runs_.begin(); it != runs_.end(); ++it) {
            std::shared_ptr<Run> run = *it;
            if (run->next < run->lines.size() && !run->terminated) {
                const auto [line, err] = run->lines[run->next++];
                if (run->events.line) run->events.line(line, err);
                return true;
            }
            if (run->held && !run->terminated) continue;
            runs_.erase(it);
            if (run->events.exited) run->events.exited(run->terminated ? run->terminate_code : run->code);
            return true;
        }
        return false;
    }
    void pump(const std::function<void()>& after_each = {}) {
        while (step()) {
            if (after_each) after_each();
        }
    }
    bool idle() const { return runs_.empty(); }
    std::vector<Command> started;

private:
    Script script_;
    std::deque<std::shared_ptr<Run>> runs_;
};

struct FakeEnvironment final : Environment {
    Install install;
    std::string built;
    bool icon = false;
    bool running_outside = false;
    std::set<std::string> there;
    std::string target_error;
    bool started_flag = false;
    int forgot = 0;
    std::vector<std::pair<fs::path, fs::path>> records;

    void look(Facts& facts) override {
        facts.install = install;
        facts.game_built = built;
        facts.icon = icon;
        if (!facts.game_started_here) facts.game_running = running_outside;
    }
    std::optional<fs::path> install_target(const fs::path& chosen, std::string* why) override {
        if (!target_error.empty()) {
            if (why) *why = target_error;
            return std::nullopt;
        }
        return chosen / "Tekken Tag Tournament 2";
    }
    void write_started_record(const fs::path& folder, const fs::path& game) override { records.emplace_back(folder, game); }
    bool started(const fs::path&) override { return started_flag; }
    void forget_started_record() override { ++forgot; }
    std::string log_end(const fs::path&) override { return "line one\nline two\nSegmentation fault\n"; }
    bool exists(const fs::path& path) override { return there.count(path.string()) > 0; }
    fs::path build_work() override { return "/home/player/.cache/ttt2/build"; }
};

struct FakeFiles final : UpdateFiles {
    std::string cannot;
    bool downloader = true;
    std::optional<uint64_t> file_size = 1000;
    std::string sum = "abc";
    bool appimage = true;
    std::string exec_error, replace_error;
    std::vector<fs::path> removed;
    std::string cannot_replace(const fs::path&) override { return cannot; }
    std::optional<Downloader> find_downloader() override {
        if (!downloader) return std::nullopt;
        return Downloader{"/usr/bin/curl", true};
    }
    std::optional<uint64_t> size(const fs::path&) override { return file_size; }
    std::string sha256(const fs::path&) override { return sum; }
    bool is_appimage(const fs::path&) override { return appimage; }
    std::string make_executable(const fs::path&, const fs::path&) override { return exec_error; }
    std::string replace(const fs::path&, const fs::path&) override { return replace_error; }
    void remove(const fs::path& file) override { removed.push_back(file); }
    Distro distro() override { return Distro{"arch", "Arch Linux", "", {"arch"}, false}; }
};

struct MemoryKeys final : KeyStore {
    Keymap saved;
    std::string text; // when set, loaded with parse() (notes)
    std::string fail;
    int saves = 0;
    Keymap load(Keymap::Notes* notes) override { return text.empty() ? saved : Keymap::parse(text, notes); }
    bool save(const Keymap& keymap, std::string* error) override {
        if (!fail.empty()) {
            if (error) *error = fail;
            return false;
        }
        saved = keymap;
        text.clear();
        ++saves;
        return true;
    }
};

} // namespace launcher::model::testing
