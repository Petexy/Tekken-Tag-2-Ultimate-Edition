// The model's Starter over core's processes (see starter.h).

#include "starter.h"

namespace launcher::backend {

ProcessSpec process_spec(const model::Command& command) {
    ProcessSpec spec;
    spec.argv = command.argv;
    spec.env.assign(command.env.begin(), command.env.end());
    spec.cwd = command.cwd;
    spec.mode = command.mode == model::Command::Mode::kDetached     ? ProcessSpec::Mode::kDetached
                : command.mode == model::Command::Mode::kSelfUpdate ? ProcessSpec::Mode::kSelfUpdate
                                                                    : ProcessSpec::Mode::kTask;
    spec.output = command.log_file;
    spec.cancel_file = command.cancel_file;
    return spec;
}

std::unique_ptr<model::Job> ProcessStarter::start(const model::Command& command, model::JobEvents events,
                                                  std::string* error) {
    // (A first task's log folder, ~/.cache/ttt2 for the game's log: made as needed.)
    for (const fs::path& file : {command.log_file, command.cancel_file}) {
        std::error_code ec;
        if (!file.empty() && file.has_parent_path()) fs::create_directories(file.parent_path(), ec);
    }
    auto process = host_.start(process_spec(command), {std::move(events.line), std::move(events.exited)}, error);
    if (!process) return nullptr;
    struct ProcessJob final : model::Job {
        std::unique_ptr<Process> process;
        void terminate() override { process->terminate(); }
    };
    auto job = std::make_unique<ProcessJob>();
    job->process = std::move(process);
    return job;
}

} // namespace launcher::backend
