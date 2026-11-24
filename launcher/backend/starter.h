#pragma once

// The model's Starter (launcher/model/task.h) over core's ProcessHost
// (core/subprocess.h): each Command run as its mode says, its lines and end
// delivered on the UI thread by the host's pump().

#include "subprocess.h"
#include "task.h"

namespace launcher::backend {

// What core runs for a model Command: its arguments, variables, folder, mode, log (a task's lines, or the game's
// output) and cancel file.
ProcessSpec process_spec(const model::Command& command);

class ProcessStarter final : public model::Starter {
public:
    explicit ProcessStarter(ProcessHost& host) : host_(host) {}
    // (UI thread only, as ProcessHost::start.) The folders of its log and cancel file are made first.
    std::unique_ptr<model::Job> start(const model::Command& command, model::JobEvents events,
                                      std::string* error) override;

private:
    ProcessHost& host_;
};

} // namespace launcher::backend
