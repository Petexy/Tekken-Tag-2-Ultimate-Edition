#pragma once

// The one task that runs (the task panel): a program started through the
// injected Starter, its lines read into core's Progress, Cancel, the result's
// texts per kind (launcher/app/task.cpp's task_exited; Windows-only kinds from
// window.py's task_done), the 12 s auto-hide of a success and the refusals
// shown in the panel. No real process or timer: the app gives the clock.

#include "facts.h"
#include "protocol.h"
#include "view.h"

#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace launcher::model {

// "$ <argv>" as the log shows it: an argument with a space in quotes.
std::string command_text(const std::vector<std::string>& argv);

struct JobEvents {
    std::function<void(const std::string& line, bool is_error)> line;
    std::function<void(int code)> exited; // 128 + the signal when one ended it (Linux); 130: cancelled (Windows)
};

// A program that runs: Cancel terminates it (it stops what it started and
// cleans up first: seconds).
struct Job {
    virtual ~Job() = default;
    virtual void terminate() = 0;
};

// Starts programs: the app's real one (Process), a fake in tests.
struct Starter {
    virtual ~Starter() = default;
    virtual std::unique_ptr<Job> start(const Command& command, JobEvents events, std::string* error) = 0;
};

// What a task is: what to run and what its result says.
struct TaskSpec {
    TaskKind kind = TaskKind::kImport;
    std::string title;   // "Adding Kazumi Mishima", "Installing Tekken Tag Tournament 2"
    Command command;     // empty argv: done in the launcher (uninstall, the launcher's own update)
    bool update = false; // import: updating characters ("Updated X")
    std::string subject; // import, remove: "Kazumi Mishima" / "3 characters"
    std::string hidden;  // import: the game run hidden ("Tekken 7", "Tekken 8", "Tekken 7 and Tekken 8"), or ""
    std::vector<std::string> names; // import, remove: the characters (Windows' result names them)
    bool started_record = false;    // install: whether the folder's started record is there at the end (Resume)
};

// What a task's end says.
struct TaskResult {
    TaskKind kind = TaskKind::kImport;
    bool ok = false, cancelled = false;
    std::string title, detail;
    std::vector<std::string> added; // @added / @removed names
    std::string updated;            // Windows launcher tasks: the version updated to ("" when none)
};

// The texts of a task's end from what it said (task.cpp's task_exited and,
// for Windows-only kinds, window.py's task_done). `display` names characters.
struct TaskEnd {
    int code = 0;
    bool cancelled = false;
    std::string error;                // the last @error
    std::vector<std::string> added;   // @added / @removed
    std::vector<std::string> skipped; // "<name>: <why>"
    std::vector<std::pair<std::string, std::string>> stand_ins;
    std::string last_step; // Windows launcher tasks: the last step said
    std::string updated;   // Windows: @launcher-updated <version>
};
TaskResult task_result(const Caps& caps, const TaskSpec& spec, const TaskEnd& end,
                       const std::function<std::string(const std::string&)>& display);
// "It was stopped: Killed (code 137, see Details)" / "It stopped with code 2 (see Details)".
std::string stopped_why(const Caps& caps, int code);

class TaskRunner {
public:
    static constexpr double kShownSeconds = 12; // a success says so this long (not while Details is open)
    static constexpr size_t kLogLines = 5000;   // the log keeps the newest

    TaskRunner(Starter& starter, const Caps& caps) : starter_(starter), caps_(caps) {}

    // Display names for Progress and the results (from the status).
    void set_names(std::map<std::string, std::string> names) { names_ = std::move(names); }

    bool running() const { return running_; }
    // Starts the task's program; false (and the panel says why) when it cannot start. A task that runs refuses
    // (the model checks first: refuse()).
    bool start(TaskSpec spec, double now);
    // A task the launcher does itself (uninstall, its own update's steps): ended by finish().
    void begin(TaskSpec spec, double now);
    // The launcher's own steps: shown as the task's step and logged.
    void step(const std::string& text);
    void progress(uint64_t done, uint64_t total);
    void set_title(std::string title);
    // A line of the task (also for begin()'s tasks: their programs' output).
    void line(const std::string& text, bool is_error);
    void cancel();
    bool cancellable() const;
    // The end of a begin() task, or of anything that stops the task early.
    void finish(bool ok, std::string title, std::string detail, bool cancelled, double now);
    // A refusal with no task running: the panel shows it as a failed one.
    void refuse(const std::string& title, const std::string& why, double now);
    // Close (the button when nothing runs), and the auto-hide.
    void close() { shown_ = false; }
    void set_details(bool expanded) { details_ = expanded; }
    void tick(double now);

    // Called once a task ended (after the panel says so; also a refusal's, kind kRefusal): the model
    // refreshes, launches after shaders ...
    std::function<void(const TaskResult&)> on_end;

    TaskView view() const;
    std::optional<TaskFacts> facts() const;
    const TaskSpec& spec() const { return spec_; }
    const std::vector<std::string>& log() const { return log_; }
    const Progress& progress_state() const { return progress_; }
    const TaskResult& last() const { return last_; }
    bool shown() const { return shown_; }
    // Changes when a task starts and when it ends (a result shown is the task's whose end gave this number).
    int serial() const { return serial_; }
    // The job that runs (the self-update replaces it with each step's).
    void set_job(std::unique_ptr<Job> job) {
        if (job_) ended_job_ = std::move(job_); // (it may be ending from its own callback)
        job_ = std::move(job);
    }
    Job* job() { return job_.get(); }
    void add_log(const std::string& line);

private:
    void exited(int code, double now);
    void clear_for(TaskSpec spec, double now);

    Starter& starter_;
    Caps caps_;
    std::map<std::string, std::string> names_;
    TaskSpec spec_;
    std::unique_ptr<Job> job_, ended_job_;
    Progress progress_{Progress::Kind::kBuild};
    TaskEnd end_;
    TaskResult last_;
    std::vector<std::string> log_;
    bool running_ = false, shown_ = false, cancelled_ = false, failed_ = false, details_ = false;
    std::string title_, detail_;
    bool started_ = false; // a line moved the progress: the detail is no more "Starting…"
    // Windows' own update: the worker said "@step update Putting ... in place": from then on it is replacing
    // the .exe or its files, and Cancel is gone (the worker no longer looks at its cancel file).
    bool replacing_ = false;
    double hide_at_ = -1;
    int serial_ = 0;
    double now_ = 0;
};

} // namespace launcher::model
