// Windows' answers to the new launcher (see windows_backend.h).

#include "windows_backend.h"

#include <string_view>

namespace launcher::backend {

namespace {

fs::path path_of(const json::Value& v) {
#ifdef _WIN32
    // (UTF-8 in the answer: wide on Windows, so that a José in a path is kept.)
    const std::string text = v.string();
    return fs::path(std::u8string(text.begin(), text.end()));
#else
    return fs::path(v.string());
#endif
}

model::SetupProblem problem_of(const json::Value& p) {
    return {p["code"].string(), p["what"].string(), p["letters"].string(), p["path"].string()};
}

} // namespace

namespace {

// The answer's object with its protocol checked; its "error" left to the caller.
std::optional<json::Value> parse_object(const std::string& output, QueryError* error) {
    // (Other lines may come before it: the last non-empty one is the answer.)
    std::string_view rest = output;
    while (!rest.empty() && (rest.back() == '\n' || rest.back() == '\r' || rest.back() == ' ')) rest.remove_suffix(1);
    const size_t start = rest.rfind('\n');
    const std::string_view line = start == std::string_view::npos ? rest : rest.substr(start + 1);
    std::optional<json::Value> value = json::parse(line);
    if (!value || !value->is_object()) {
        if (error) *error = {"answer", std::string(line.substr(0, 300))};
        return std::nullopt;
    }
    if ((*value)["protocol"].number(-1) != kQueryProtocol) {
        if (error) *error = {"protocol", std::to_string(static_cast<int>((*value)["protocol"].number(-1)))};
        return std::nullopt;
    }
    return value;
}

} // namespace

std::optional<json::Value> parse_query(const std::string& output, QueryError* error) {
    std::optional<json::Value> value = parse_object(output, error);
    if (value && (*value)["error"].is_string()) {
        if (error) *error = {"error", (*value)["error"].string()};
        return std::nullopt;
    }
    return value;
}

std::string kit_id(const std::string& files_id) {
    const size_t space = files_id.find(' ');
    return space == std::string::npos ? files_id : files_id.substr(0, space) + "-" + files_id.substr(space + 1);
}

std::optional<WindowsStateAnswer> parse_windows_state(const std::string& output, QueryError* error) {
    const auto value = parse_query(output, error);
    if (!value) return std::nullopt;
    const json::Value& v = *value;
    if (!v["root"].is_string() || !v["play"].is_object()) {
        if (error) *error = {"answer", "no state"};
        return std::nullopt;
    }
    WindowsStateAnswer a;
    model::WindowsState& w = a.state;
    w.root = path_of(v["root"]);
    w.build = path_of(v["build"]);
    w.config = path_of(v["config"]);
    w.branch = v["branch"].string();
    w.commit = v["commit"].string();
    const json::Value& settings = v["settings"];
    for (size_t i = 0; i < settings.keys().size(); ++i) w.folders[settings.keys()[i]] = settings.values()[i].string();
    // (Files older than 0.8.0's answer have none: no Default then.)
    if (const json::Value& defaults = v["defaults"]; defaults.is_object())
        for (size_t i = 0; i < defaults.keys().size(); ++i)
            w.folder_defaults[defaults.keys()[i]] = defaults.values()[i].string();
    w.logs = path_of(v["logs"]);
    w.latest_log = path_of(v["latest_log"]);
    w.data_problem = v["data_problem"].string();
    w.cannot_replace = v["cannot_replace"].string();
    const json::Value& play = v["play"];
    if (play["argv"].is_array() && !play["argv"].items().empty()) {
        model::Command c;
        for (const json::Value& arg : play["argv"].items()) c.argv.push_back(arg.string());
        c.cwd = path_of(play["cwd"]);
        const json::Value& env = play["env"];
        for (size_t i = 0; i < env.keys().size(); ++i) c.env[env.keys()[i]] = env.values()[i].string();
        c.log_file = path_of(play["log"]);
        c.mode = model::Command::Mode::kDetached; // (the game outlives the launcher; never in a task's job)
        w.play = std::move(c);
    } else {
        w.play_problem = play["problem"].string("source");
    }
    a.version = v["version"].string();
    a.files_id = kit_id(v["files_id"].string());
    a.installed_by = kit_id(v["installed_by"].string());
    a.exe = path_of(v["exe"]);
    a.installed = path_of(v["installed"]);
    a.icon = path_of(v["icon"]);
    a.display_file = path_of(v["display_file"]);
    a.keyboard_file = path_of(v["keyboard_file"]);
    return a;
}

void apply_windows_state(const WindowsStateAnswer& a, model::Facts& facts) {
    facts.windows = a.state;
    facts.this_build = a.files_id;
    facts.build_commit = a.state.commit;
    facts.install = a.installed.empty() ? Install{} : Install{InstallState::kInstalled, a.installed, {}};
    facts.game_built = a.installed_by;
    facts.icon = !a.icon.empty();
    facts.self_update = !a.exe.empty();
}

std::optional<model::SetupProblem> parse_check(const std::string& output, QueryError* error) {
    const auto value = parse_query(output, error);
    if (!value) return std::nullopt;
    if (!(*value)["problem"].is_object()) {
        if (error) *error = {"answer", "no problem"};
        return std::nullopt;
    }
    return problem_of((*value)["problem"]);
}

std::optional<SavedSettings> parse_save_settings(const std::string& output, QueryError* error) {
    const auto value = parse_query(output, error);
    if (!value) return std::nullopt;
    SavedSettings saved;
    const json::Value& settings = (*value)["settings"];
    if (settings.is_object()) {
        for (size_t i = 0; i < settings.keys().size(); ++i)
            saved.folders[settings.keys()[i]] = settings.values()[i].string();
    } else if ((*value)["problem"].is_object()) {
        saved.problem = problem_of((*value)["problem"]);
    } else {
        if (error) *error = {"answer", "no settings"};
        return std::nullopt;
    }
    return saved;
}

std::optional<ReleaseAnswer> parse_release_query(const std::string& output, QueryError* error) {
    // (Its "error" is GitHub's reason, a fact of the answer; an answer without "none" is a failure's.)
    const auto value = parse_object(output, error);
    if (!value) return std::nullopt;
    const json::Value& v = *value;
    std::optional<ReleaseAnswer> answer = release_query_answer(v);
    if (!answer && error) *error = {v["error"].is_string() ? "error" : "answer", v["error"].string()};
    return answer;
}

} // namespace launcher::backend
