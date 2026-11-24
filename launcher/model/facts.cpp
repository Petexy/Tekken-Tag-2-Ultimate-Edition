#include "facts.h"

namespace launcher::model {

const char* task_kind_name(TaskKind kind) {
    switch (kind) {
    case TaskKind::kInstall: return "install";
    case TaskKind::kUpdate: return "upgrade";
    case TaskKind::kImport: return "import";
    case TaskKind::kRemove: return "remove";
    case TaskKind::kUninstall: return "uninstall";
    case TaskKind::kLauncherUpdate: return "launcher";
    case TaskKind::kLauncherFiles: return "files";
    case TaskKind::kPackages: return "packages";
    case TaskKind::kShaders: return "shaders";
    case TaskKind::kSetup: return "setup";
    case TaskKind::kBuild: return "build";
    case TaskKind::kInstallSource: return "install";
    case TaskKind::kUpdateInstalled: return "update";
    case TaskKind::kBootstrap: return "bootstrap";
    case TaskKind::kRefusal: return "refusal";
    }
    return "";
}

Caps Caps::linux_caps() {
    Caps c;
    c.install_flow = true;
    c.uninstall = true;
    c.prerequisites_listed = true;
    c.packages_download = true;
    c.game_error_report = true;
    c.game_outside = true;
    c.cancellable = {TaskKind::kInstall,  TaskKind::kUpdate,   TaskKind::kImport,        TaskKind::kRemove,
                     TaskKind::kPackages, TaskKind::kShaders,  TaskKind::kLauncherUpdate};
    c.close_policy = ClosePolicy::kAskStopAndQuit;
    c.platform_name = "Linux";
    return c;
}

Caps Caps::windows_caps() {
    Caps c;
    c.windows = true;
    c.setup_game = true;
    c.more_menu = true;
    c.folders = true;
    c.performance_preset = true;
    c.task_log_file = true;
    c.branch_updates = true;
    // (As window.py today: the workers that stop at a cancel file. OPEN: the long builds could too.)
    c.cancellable = {TaskKind::kImport, TaskKind::kRemove, TaskKind::kLauncherUpdate, TaskKind::kLauncherFiles};
    c.close_policy = ClosePolicy::kRefuse;
    c.platform_name = "Windows";
    return c;
}

} // namespace launcher::model
