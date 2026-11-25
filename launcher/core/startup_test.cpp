// The launcher's first steps (startup.h), one launcher per user
// (single_instance.h) and the release .exe's files (payload.h, sha256.h),
// with real programs: this test starts itself as the launcher
// (`--child DIR -- ARGS`), on Linux and on Windows (Wine), each run under a
// name of its own so that it never reaches a real launcher.
//
//   launcher_startup_test DIR          the tests
//   launcher_startup_test --dbus DIR   Linux: an old GTK launcher (a GApplication made with Python's gi) on a
//                                      private session bus (dbus-run-session); 77 (skipped) without one

#include "payload.h"
#include "sha256.h"
#include "single_instance.h"
#include "startup.h"
#include "subprocess.h"
#include "utf8_path.h"

#ifdef _WIN32
#include "win32.h"
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <unistd.h>
#endif

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <thread>

namespace {

using namespace launcher;
using Clock = std::chrono::steady_clock;

double seconds_since(Clock::time_point t) { return std::chrono::duration<double>(Clock::now() - t).count(); }

int g_failures = 0, g_checks = 0;
fs::path g_self, g_root;
std::string g_instance; // this run's launcher name

void check(bool ok, const std::string& what) {
    ++g_checks;
    if (!ok) {
        std::printf("FAIL %s\n", what.c_str());
        std::fflush(stdout);
        ++g_failures;
    }
}

template <typename A, typename B> void check_eq(const A& a, const B& b, const std::string& what) {
    std::ostringstream text;
    text << what << ": got [" << a << "], wanted [" << b << "]";
    check(a == b, text.str());
}

std::string read_file(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    std::stringstream s;
    s << in.rdbuf();
    return s.str();
}

void write_file(const fs::path& file, const std::string& data) {
    fs::create_directories(file.parent_path());
    std::ofstream(file, std::ios::binary) << data;
}

std::string utf8(const fs::path& p) {
#ifdef _WIN32
    return win32::narrow(p.wstring());
#else
    return p.string();
#endif
}

std::string env(const char* name) {
#ifdef _WIN32
    return win32::narrow(win32::environment(win32::wide(name).c_str()));
#else
    const char* v = std::getenv(name);
    return v ? v : "";
#endif
}

int64_t own_pid() {
#ifdef _WIN32
    return GetCurrentProcessId();
#else
    return getpid();
#endif
}

void out(const std::string& text) {
#ifdef _WIN32
    DWORD n = 0;
    WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), text.data(), static_cast<DWORD>(text.size()), &n, nullptr);
#else
    std::fwrite(text.data(), 1, text.size(), stdout);
    std::fflush(stdout);
#endif
}

// The release .exe's files as make_launcher_exe.py writes them.
std::string make_payload(const std::vector<std::pair<std::string, std::string>>& files) {
    std::string body;
    const auto number = [&](uint64_t v, int bytes) {
        for (int i = 0; i < bytes; ++i) body += static_cast<char>((v >> (8 * i)) & 0xff);
    };
    for (const auto& [path, data] : files) {
        number(path.size(), 4);
        body += path;
        number(data.size(), 8);
        body += data;
    }
    payload::Trailer t{};
    t.size = body.size();
    t.count = files.size();
    const auto digest = sha256(body);
    std::memcpy(t.sha256, digest.data(), 32);
    std::memcpy(t.magic, payload::kMagic, 8);
    return body + std::string(reinterpret_cast<const char*>(&t), sizeof t);
}

// ---------------------------------------------------------------- the launcher (child)

int child(const std::vector<std::string>& args) {
    startup::Program program;
    program.version = "9.9.9";
    program.usage = "usage: ttt2-launcher [GAME.wua] [--files DIR] [--screenshot FILE] | --version\n";
    program.options = {{"--files", 1}, {"--screenshot", 1}};
    program.instance_name = env("TTT2_TEST_INSTANCE");
    if (const std::string s = env("TTT2_TEST_AFTER_SECONDS"); !s.empty()) program.after_seconds = std::atof(s.c_str());
    program.tell = [](const std::string& text) { out("TELL " + text + "\n"); };
    std::atomic<int> woken{0};
    program.wake = [&] { ++woken; };
    startup::Start start = startup::begin(args, program);
    if (start.exit >= 0) {
        out("EXIT " + std::to_string(start.exit) + "\n");
        return start.exit;
    }
    out(std::string("RUN primary=") + (start.instance ? "1" : "0") + " note=" + start.note + "\n");
    out("FILES " + utf8(start.files) + "\n");
    out("DIGEST " + start.files_digest + "\n");
    out("AFTER " + env("TTT2_LAUNCHER_AFTER") + "\n");
    out("EXE " + env("TTT2_LAUNCHER_EXE") + "\n");
    out("UIPID " + env("TTT2_LAUNCHER_UI_PID") + " PID " + std::to_string(own_pid()) + "\n");
    out("READY\n");
    const double hold = std::atof(env("TTT2_TEST_HOLD").c_str());
    for (const auto t0 = Clock::now(); seconds_since(t0) < hold;) {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        if (!start.instance) continue;
        for (const Forwarded& f : start.instance->take()) {
            std::string joined;
            for (const std::string& a : f.args) joined += (joined.empty() ? "" : "|") + a;
            out("GOT " + joined + " TOKEN " + f.token + " WOKEN " + std::to_string(woken.load()) + "\n");
        }
    }
    return 0;
}

// ---------------------------------------------------------------- running it

struct Run {
    std::vector<std::string> out, err;
    int code = -1;
    std::unique_ptr<Process> process;
    bool has(const std::string& prefix) const {
        for (const auto& l : out) {
            if (l.rfind(prefix, 0) == 0) return true;
        }
        return false;
    }
    std::string line(const std::string& prefix) const {
        for (const auto& l : out) {
            if (l.rfind(prefix, 0) == 0) return l.substr(prefix.size());
        }
        return "<none>";
    }
    std::string all() const {
        std::string s;
        for (const auto& l : out) s += "<" + l + ">";
        for (const auto& l : err) s += "{" + l + "}";
        return s;
    }
};

ProcessHost* g_host = nullptr;

std::shared_ptr<Run> launch(const std::vector<std::string>& args, std::map<std::string, std::string> vars = {},
                            const fs::path& program = {}) {
    auto run = std::make_shared<Run>();
    ProcessSpec spec;
    spec.argv = {utf8(program.empty() ? g_self : program), "--child", utf8(g_root), "--"};
    spec.argv.insert(spec.argv.end(), args.begin(), args.end());
    vars.try_emplace("TTT2_TEST_INSTANCE", g_instance);
    vars.try_emplace("TTT2_LAUNCHER_AFTER", "");
    vars.try_emplace("XDG_ACTIVATION_TOKEN", "");
    vars.try_emplace("DESKTOP_STARTUP_ID", "");
    vars.try_emplace("TTT2_LAUNCHER_EXE", "");
    vars.try_emplace("TTT2_LAUNCHER_UI_PID", "");
    spec.env.assign(vars.begin(), vars.end());
    spec.cwd = g_root;
    std::string error;
    run->process = g_host->start(spec,
                                 {[run](const std::string& l, bool e) { (e ? run->err : run->out).push_back(l); },
                                  [run](int c) { run->code = c; }},
                                 &error);
    check(run->process != nullptr, "started (" + error + ")");
    return run;
}

bool wait_until(const std::function<bool()>& done, double seconds) {
    for (const auto t0 = Clock::now(); !done();) {
        if (seconds_since(t0) > seconds) return false;
        g_host->wait(0.05);
        g_host->pump();
    }
    return true;
}

bool ended(const std::shared_ptr<Run>& r, double seconds = 30) {
    return wait_until([&] { return r->code != -1; }, seconds);
}

// ---------------------------------------------------------------- tests

void test_sha256() {
    check_eq(sha256_hex(""), std::string("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"), "sha256 ''");
    check_eq(sha256_hex("abc"), std::string("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
             "sha256 abc");
    Sha256 s;
    const std::string chunk(1000, 'a');
    for (int i = 0; i < 1000; ++i) s.update(chunk.substr(0, 1 + i % 999)), s.update(chunk.substr(0, 999 - i % 999));
    const auto d = s.finish();
    check_eq(hex(d.data(), d.size()), std::string("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
             "sha256 a million a's in pieces");
}

void test_payload() {
    const fs::path root = g_root / "unpacked";
    const std::string one = make_payload({{"a.txt", "one"}, {"sub/dir/b.txt", "two"}, {"launcher/windows/main.py", ""}});
    const auto p = payload::read(one);
    check(p.has_value(), "payload: read");
    check(!payload::read("no trailer here, just a program's bytes that are long enough to hold one, more than 56")
               .has_value(),
          "payload: none in a program without files");
    check(payload::unpack(*p, root), "payload: unpacked");
    check_eq(read_file(root / "sub/dir/b.txt"), std::string("two"), "payload: a file in a folder");
    check_eq(payload::unpacked_digest(root), p->digest(), "payload: the stamp names them");
    check(!payload::unpack(*p, root), "payload: the same files are not unpacked again");
    // (A test build's Update: other files under the .exe's digest, REVIEW2_compat #3. Again: its own files back.)
    write_file(root / "a.txt", "updated");
    write_file(root / "update-only.txt", "new");
    write_file(root / "local/launcher-files.txt",
               p->digest() + "\na.txt\nlauncher/windows/main.py\nsub/dir/b.txt\nupdate-only.txt\n");
    check(!payload::unpack(*p, root), "payload: an update's files under the .exe's digest are kept");
    check(payload::unpack(*p, root, true), "payload: again, whatever the stamp says");
    check_eq(read_file(root / "a.txt"), std::string("one"), "payload: again: its own files back");
    check(!fs::exists(root / "update-only.txt"), "payload: again: the update's own files gone");
    check_eq(payload::unpacked_digest(root), p->digest(), "payload: again: the stamp names its own");
    write_file(root / "local/windows-tools/kept", "x");
    write_file(root / "build-windows-tools/kept", "x");
    const auto newer = payload::read(make_payload({{"a.txt", "ONE"}, {"c.txt", "three"}, {"launcher/windows/main.py", ""}}));
    check(payload::unpack(*newer, root), "payload: newer files unpacked");
    check_eq(read_file(root / "a.txt") + read_file(root / "c.txt"), std::string("ONEthree"), "payload: newer files");
    check(!fs::exists(root / "sub/dir/b.txt"), "payload: what only the old files had is gone");
    check(fs::exists(root / "local/windows-tools/kept") && fs::exists(root / "build-windows-tools/kept"),
          "payload: nothing else is touched");
    for (const std::string unsafe : {"../escape.txt", "C:/escape.txt", "a\\..\\b.txt", "/abs.txt", "a//b", "./a"}) {
        std::string said;
        try {
            payload::unpack(*payload::read(make_payload({{unsafe, "x"}})), g_root / "unsafe");
        } catch (const std::exception& e) {
            said = e.what();
        }
        check(said.find("unsafe path") != std::string::npos, "payload: refused " + unsafe + " (" + said + ")");
    }
    std::string damaged = one;
    damaged[10] ^= 1;
    std::string said;
    try {
        payload::read(damaged);
    } catch (const std::exception& e) {
        said = e.what();
    }
    check_eq(said, std::string("This Golden Fist Launcher is damaged: download it again."), "payload: damaged");
    check(payload::read(damaged, false).has_value(), "payload: unchecked, as the trailer says");
    check(!fs::exists(g_root / "escape.txt") && !fs::exists(g_root / "unsafe"), "payload: nothing written");
}

void test_message() {
    const Forwarded f{{"/a b/c.wua", "--files", "x\ny\\z"}, "tok en"};
    Forwarded back;
    check(decode_forwarded(encode_forwarded(f), &back) && back == f, "message: round trip");
    check(!decode_forwarded("arg x\n", &back), "message: incomplete");
    check(!decode_forwarded("bogus\nend\n", &back), "message: malformed");
}

void test_options() {
    auto version = launch({"game.wua", "--version"});
    check(ended(version), "--version: ended");
    check_eq(version->code, 0, "--version: code");
    check_eq(version->line("ttt2-launcher "), std::string("9.9.9"), "--version: what it says");
    auto help = launch({"--help"});
    check(ended(help) && help->code == 0 && help->has("usage: ttt2-launcher"), "--help: usage, 0 " + help->all());
    auto bad = launch({"--bogus"});
    check(ended(bad) && bad->code == 2, "unknown option: 2");
    check(!bad->err.empty() && bad->err[0] == "ttt2-launcher: unknown option --bogus", "unknown option: said " +
                                                                                           bad->all());
    auto missing = launch({"--files"});
    check(ended(missing) && missing->code == 2, "an option without its value: 2");
}

void test_one_launcher() {
    auto first = launch({}, {{"TTT2_TEST_HOLD", "8"}});
    check(wait_until([&] { return first->has("READY") || first->code != -1; }, 20), "one launcher: the first runs");
    check_eq(first->line("RUN primary="), std::string("1 note="), "one launcher: the first is it");
    check_eq(first->line("AFTER "), std::string(""), "one launcher: no TTT2_LAUNCHER_AFTER");
    auto second = launch({"game.wua", "--files", "dir"}, {{"XDG_ACTIVATION_TOKEN", "tok123"}});
    check(ended(second) && second->code == 0, "one launcher: a second start ends, 0 " + second->all());
    check(!second->has("RUN"), "one launcher: the second does not run");
    check(wait_until([&] { return first->has("GOT "); }, 10), "one launcher: the first is told");
    const std::string wua = utf8((g_root / "game.wua").lexically_normal());
    check_eq(first->line("GOT "), wua + "|--files|dir TOKEN tok123 WOKEN 1",
             "one launcher: the arguments (the file absolute) and token");

    // Replacing it (TTT2_LAUNCHER_AFTER): never handed over to the one it replaces or to any other one.
    const std::string first_pid = first->line("UIPID ").substr(first->line("UIPID ").find("PID ") + 4);
    auto stubborn = launch({}, {{"TTT2_LAUNCHER_AFTER", "999999"}, {"TTT2_TEST_AFTER_SECONDS", "1"}});
    check(ended(stubborn) && stubborn->code == 1, "after: the name stays taken: 1 " + stubborn->all());
    check(stubborn->has("TELL Another launcher is still running"), "after: the player is told");
    auto replacing = launch({}, {{"TTT2_LAUNCHER_AFTER", first_pid}, {"TTT2_TEST_HOLD", "0.5"}});
    check(wait_until([&] { return replacing->has("READY") || replacing->code != -1; }, 30), "after: it runs");
    check(first->code != -1, "after: once the one it replaces ended");
    check_eq(replacing->line("RUN primary="), std::string("1 note="), "after: it is the launcher");
    check_eq(replacing->line("AFTER "), std::string(""), "after: its programs do not see TTT2_LAUNCHER_AFTER");
    int got = 0;
    for (const auto& l : first->out) got += l.rfind("GOT ", 0) == 0;
    check_eq(got, 1, "after: the replaced one was handed nothing more");
    check(ended(replacing), "after: ended");
}

#ifdef _WIN32
void test_release() {
    // The test program with files appended is a release .exe as make_launcher_exe.py --stub makes them.
    const std::string self = read_file(g_self);
    const fs::path folder = g_root / "release";
    const fs::path exe = folder / "Golden_Fist_Launcher-x86_64.exe", other = folder / "Other_Launcher.exe";
    const std::string files1 = make_payload({{"a.txt", "one"}, {"launcher/windows/main.py", ""}});
    const std::string files2 = make_payload({{"a.txt", "two"}, {"launcher/windows/main.py", ""}});
    write_file(exe, self + files1);
    write_file(other, self + files2);
    write_file(folder / "Golden_Fist_Launcher-x86_64.old.exe", "old");
    const fs::path local = g_root / "appdata";
    const fs::path unpacked = local / "TTT2Ultimate" / "launcher";
    const std::map<std::string, std::string> vars = {{"LOCALAPPDATA", utf8(local)}};

    auto version = launch({"--version"}, vars, exe);
    check(ended(version) && version->code == 0 && version->has("ttt2-launcher 9.9.9"), "release: --version");
    check(!fs::exists(unpacked), "release: --version unpacks nothing");
    auto unpack = launch({"--unpack", utf8(g_root / "into")}, vars, exe);
    check(ended(unpack) && unpack->code == 0, "release: --unpack " + unpack->all());
    check_eq(read_file(g_root / "into" / "a.txt"), std::string("one"), "release: --unpack wrote its files");
    auto none = launch({"--unpack", utf8(g_root / "into2")}, vars);
    check(ended(none) && none->code == 1 && !none->err.empty() &&
              none->err[0] == "ttt2-launcher: This launcher holds no files.",
          "a build without files: --unpack refused " + none->all());

    auto first = launch({}, [&] {
        auto v = vars;
        v["TTT2_TEST_HOLD"] = "6";
        return v;
    }(), exe);
    check(wait_until([&] { return first->has("READY") || first->code != -1; }, 30), "release: runs " + first->all());
    check_eq(first->line("FILES "), utf8(unpacked), "release: its files' folder");
    check_eq(read_file(unpacked / "a.txt"), std::string("one"), "release: its files there");
    check_eq(first->line("DIGEST "), payload::read(files1)->digest(), "release: their digest");
    check_eq(first->line("EXE "), utf8(exe), "release: TTT2_LAUNCHER_EXE");
    const std::string ids = first->line("UIPID ");
    check(ids.substr(0, ids.find(' ')) == ids.substr(ids.find("PID ") + 4), "release: TTT2_LAUNCHER_UI_PID " + ids);
    check(!fs::exists(folder / "Golden_Fist_Launcher-x86_64.old.exe"), "release: the replaced .exe deleted");

    auto same = launch({}, vars, exe);
    check(ended(same) && same->code == 0 && !same->has("TELL"), "release: a second start hands over " + same->all());
    auto different = launch({}, vars, other);
    check(ended(different) && different->code == 0, "release: another version hands over too");
    check(different->has("TELL Another launcher is already running. Close it to switch"),
          "release: another version says to close the running one " + different->all());
    check_eq(read_file(unpacked / "a.txt"), std::string("one"), "release: and unpacks nothing");
    check(wait_until([&] { return first->code != -1; }, 30), "release: ended");

    // Its own files again (a test build's Update got another program's files, REVIEW2_compat #3), into a folder
    // with a letter beyond ASCII.
    const fs::path again = g_root / launcher::utf8_path("Jos\xc3\xa9 again");
    write_file(again / "a.txt", "updated");
    write_file(again / "local/launcher-files.txt", payload::read(files1)->digest() + "\na.txt\nnew.txt\n");
    write_file(again / "new.txt", "new");
    payload::unpack_own_again(exe, again);
    check(read_file(again / "a.txt") == "one" && !fs::exists(again / "new.txt") &&
              payload::unpacked_digest(again) == payload::read(files1)->digest(),
          "release: its own files unpacked again");
    std::string said;
    try {
        payload::unpack_own_again(g_self, again);
    } catch (const std::exception& e) {
        said = e.what();
    }
    check_eq(said, std::string("This launcher holds no files."), "release: again, without files");
}
#endif

#ifndef _WIN32
// An old GTK launcher: a GApplication with the launcher's id (Python's gi) on a private session bus.
int test_old_gtk_launcher() {
    const std::string bus = env("DBUS_SESSION_BUS_ADDRESS");
    if (bus.empty() || bus.find("/run/user/") != std::string::npos) {
        std::printf("SKIP: not on a private session bus (run under dbus-run-session)\n");
        return 77;
    }
    if (std::system("python3 -c 'from gi.repository import Gio' 2>/dev/null") != 0) {
        std::printf("SKIP: no Python gi\n");
        return 77;
    }
    const fs::path script = g_root / "old_launcher.py";
    write_file(script, R"(import sys
from gi.repository import Gio, GLib
class Old(Gio.Application):
    token = ''
    def do_before_emit(self, data):
        self.token = data.lookup_value('activation-token', None).get_string() if data.lookup_value('activation-token', None) else ''
        Gio.Application.do_before_emit(self, data)
    def do_startup(self):
        Gio.Application.do_startup(self)
        self.hold()
        print('READY', flush=True)
    def do_activate(self):
        print('ACTIVATE', self.token, flush=True)
    def do_open(self, files, n, hint):
        print('OPEN', ' '.join(f.get_uri() for f in files), self.token, flush=True)
Old(application_id=sys.argv[1], flags=Gio.ApplicationFlags.HANDLES_OPEN).run([sys.argv[0]])
)");
    ProcessHost host;
    g_host = &host;
    const std::string id = "io.github.petexy.TekkenTag2UltimateEdition";
    auto old = std::make_shared<Run>();
    ProcessSpec spec;
    spec.argv = {"python3", utf8(script), id};
    // (GIO on its own: no GVfs daemon or FUSE mount for file URIs.)
    spec.env = {{"GIO_USE_VFS", "local"}, {"GVFS_DISABLE_FUSE", "1"}, {"GSETTINGS_BACKEND", "memory"}};
    std::string error;
    old->process = host.start(spec,
                              {[old](const std::string& l, bool e) { (e ? old->err : old->out).push_back(l); },
                               [old](int c) { old->code = c; }},
                              &error);
    check(wait_until([&] { return old->has("READY") || old->code != -1; }, 20), "old launcher: runs " + old->all());

    InstanceOptions options;
    options.name = g_instance;
    options.message = {{"/games/my game.wua"}, "tok1"};
    InstanceClaim claim = claim_instance(options);
    check(claim.result == InstanceClaim::Result::kOldLauncher && claim.error.empty(), "old launcher: found");
    check(!claim.instance, "old launcher: this one is not the launcher");
    check(wait_until([&] { return old->has("OPEN "); }, 10), "old launcher: asked to open " + old->all());
    check_eq(old->line("OPEN "), std::string("file:///games/my%20game.wua tok1"), "old launcher: the file and token");
    options.message = {{}, "tok2"};
    check(claim_instance(options).result == InstanceClaim::Result::kOldLauncher, "old launcher: found again");
    // (It activated itself when it started; then once more with the token.)
    check(wait_until([&] { return old->has("ACTIVATE tok2"); }, 10), "old launcher: activated, the token " + old->all());
    const auto activations = [&] {
        int n = 0;
        for (const auto& l : old->out) n += l.rfind("ACTIVATE", 0) == 0;
        return n;
    };
    const int before = activations();
    options.after = true;
    options.after_seconds = 1.5;
    options.message = {{}, "tok3"};
    claim = claim_instance(options);
    check(claim.result == InstanceClaim::Result::kFailed, "old launcher: one replacing it waits, then fails");
    check_eq(claim.error, std::string("The launcher this one replaces is still running."),
             "old launcher: why it failed");
    // (Asked to show itself once while waited for, not every 100 ms: compat review #8.)
    wait_until([&] { return activations() > before; }, 5);
    wait_until([] { return false; }, 0.5);
    check_eq(activations() - before, 1, "old launcher: activated once while waited for " + old->all());
    old->process->terminate();
    check(wait_until([&] { return old->code != -1; }, 60), "old launcher: ended");
    options.after = false;
    claim = claim_instance(options);
    check(claim.result == InstanceClaim::Result::kPrimary, "old launcher: once it is gone this one is the launcher");

    // The other way (C12): an old launcher started now finds this one under its bus name and hands over to it.
    const fs::path remote = g_root / "old_remote.py";
    // (GtkApplication's platform data, as the old launcher sends it: the activation token, X11's id.)
    write_file(remote, R"(import os, sys
from gi.repository import Gio, GLib
class Old(Gio.Application):
    def do_add_platform_data(self, builder):
        token = os.environ.get('XDG_ACTIVATION_TOKEN', '')
        builder.add_value(GLib.Variant('{sv}', ('activation-token', GLib.Variant('s', token))))
        builder.add_value(GLib.Variant('{sv}', ('desktop-startup-id', GLib.Variant('s', 'x11-' + token))))
app = Old(application_id=sys.argv[1], flags=Gio.ApplicationFlags.HANDLES_OPEN)
app.register(None)
print('REMOTE', app.get_is_remote(), flush=True)
sys.exit(app.run(['old'] + sys.argv[2:]) if app.get_is_remote() else 3)
)");
    const auto old_start = [&](const std::vector<std::string>& files, const std::string& token) {
        auto run = std::make_shared<Run>();
        ProcessSpec s;
        s.argv = {"python3", utf8(remote), id};
        s.argv.insert(s.argv.end(), files.begin(), files.end());
        s.env = {{"GIO_USE_VFS", "local"}, {"GVFS_DISABLE_FUSE", "1"}, {"GSETTINGS_BACKEND", "memory"},
                 {"XDG_ACTIVATION_TOKEN", token}};
        std::string why;
        run->process = host.start(s,
                                  {[run](const std::string& l, bool e) { (e ? run->err : run->out).push_back(l); },
                                   [run](int c) { run->code = c; }},
                                  &why);
        wait_until([&] { return run->code != -1; }, 20);
        return run;
    };
    std::shared_ptr<Run> handed;
    for (int i = 0; i < 25; ++i) { // (until this one owns the name: its bus thread asks for it)
        handed = old_start({}, "tokR1");
        if (handed->has("REMOTE True")) break;
        wait_until([] { return false; }, 0.2);
    }
    check(handed->has("REMOTE True") && handed->code == 0, "reverse: an old launcher hands over " + handed->all());
    std::vector<Forwarded> got;
    wait_until([&] {
        for (auto& f : claim.instance->take()) got.push_back(std::move(f));
        return !got.empty();
    }, 10);
    const auto said = [&] {
        std::string s;
        for (const auto& f : got) s += "[" + encode_forwarded(f) + "]";
        return s;
    };
    check(!got.empty() && got.back() == Forwarded{{}, "tokR1"}, "reverse: activated, with its token " + said());
    handed = old_start({"/games/my game.wua"}, "tokR2");
    check(handed->has("REMOTE True") && handed->code == 0, "reverse: an old launcher opening a file " + handed->all());
    got.clear();
    wait_until([&] {
        for (auto& f : claim.instance->take()) got.push_back(std::move(f));
        return !got.empty();
    }, 10);
    check(got.size() == 1 && got[0] == Forwarded{{"/games/my game.wua"}, "tokR2"}, "reverse: the file and token " + said());
    claim.instance.reset(); // (the name is given back)
    handed = old_start({}, "tokR3");
    check(handed->has("REMOTE False"), "reverse: once it ended, an old launcher is the launcher again " + handed->all());
    std::printf("%d checks, %d failed\n", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
#endif

} // namespace

int main(int argc, char** argv) {
    const std::vector<std::string> args = startup::arguments(argc, argv);
#ifdef _WIN32
    std::wstring self(32768, L'\0');
    self.resize(GetModuleFileNameW(nullptr, self.data(), 32768));
    g_self = self;
#else
    g_self = fs::read_symlink("/proc/self/exe");
#endif
    if (args.size() >= 3 && args[0] == "--child" && args[2] == "--") {
        g_root = launcher::utf8_path(args[1]);
        return child(std::vector<std::string>(args.begin() + 3, args.end()));
    }
    const bool dbus = !args.empty() && args[0] == "--dbus";
    const std::vector<std::string> rest(args.begin() + (dbus ? 1 : 0), args.end());
    // (In the OS's own form: libc++ keeps an absolute C:/x as it is where libstdc++ makes it C:\x, and the children
    // say GetModuleFileNameW's backslashes. UTF-8 to a path never through the ANSI code page: compat review #2.)
    const fs::path base =
        fs::absolute(!rest.empty() ? launcher::utf8_path(rest[0]) : fs::temp_directory_path()).make_preferred();
    g_root = base / ("startup_test." + std::to_string(own_pid()));
    g_instance = "ttt2-startup-test." + std::to_string(own_pid());
    std::error_code ec;
    fs::remove_all(g_root, ec);
    fs::create_directories(g_root);
#ifndef _WIN32
    if (dbus) {
        const int result = test_old_gtk_launcher();
        fs::remove_all(g_root, ec);
        return result;
    }
#endif
    ProcessHost host;
    g_host = &host;
    test_sha256();
    test_payload();
    test_message();
    test_options();
    test_one_launcher();
#ifdef _WIN32
    test_release();
#endif
    fs::remove_all(g_root, ec);
    std::printf("%d checks, %d failed\n", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
