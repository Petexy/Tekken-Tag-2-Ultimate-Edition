// One launcher per user on Linux: an abstract unix socket, and an old GTK
// launcher looked for on the session bus (see single_instance.h).

#include "single_instance.h"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cerrno>
#include <chrono>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <type_traits>
#include <dlfcn.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>

namespace launcher {

namespace {

using Clock = std::chrono::steady_clock;

double seconds_since(Clock::time_point t) { return std::chrono::duration<double>(Clock::now() - t).count(); }

struct Address {
    sockaddr_un address{};
    socklen_t size = 0;
};

Address address_of(const std::string& name) {
    Address a;
    a.address.sun_family = AF_UNIX;
    const std::string path = name + "." + std::to_string(getuid());
    const size_t n = std::min(path.size(), sizeof a.address.sun_path - 1);
    std::memcpy(a.address.sun_path + 1, path.data(), n); // (sun_path[0] = 0: abstract)
    a.size = static_cast<socklen_t>(offsetof(sockaddr_un, sun_path) + 1 + n);
    return a;
}

bool same_user(int fd) {
    ucred peer{};
    socklen_t size = sizeof peer;
    return getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &size) == 0 && peer.uid == getuid();
}

// Reads up to "end\n" (or `limit`) within `seconds`.
bool read_message(int fd, std::string* text, double seconds, const char* until) {
    const auto t0 = Clock::now();
    char buffer[4096];
    while (text->find(until) == std::string::npos) {
        const double left = seconds - seconds_since(t0);
        if (left <= 0 || text->size() > (64 << 10)) return false;
        pollfd p{fd, POLLIN, 0};
        const int ready = poll(&p, 1, static_cast<int>(left * 1000) + 1);
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0) return false;
        const ssize_t n = read(fd, buffer, sizeof buffer);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return text->find(until) != std::string::npos;
        text->append(buffer, static_cast<size_t>(n));
    }
    return true;
}

bool write_all(int fd, std::string_view text) {
    while (!text.empty()) {
        const ssize_t n = send(fd, text.data(), text.size(), MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        text.remove_prefix(static_cast<size_t>(n));
    }
    return true;
}

// ---- An old GTK launcher on the session bus (libdbus-1 through dlopen; its types stay opaque here).

struct DBus {
    void* library = nullptr;
    void* (*bus_get_private)(int, void*) = nullptr;
    void (*set_exit_on_disconnect)(void*, unsigned) = nullptr;
    unsigned (*name_has_owner)(void*, const char*, void*) = nullptr;
    void* (*new_method_call)(const char*, const char*, const char*, const char*) = nullptr;
    void (*iter_init_append)(void*, void*) = nullptr;
    unsigned (*iter_open_container)(void*, int, const char*, void*) = nullptr;
    unsigned (*iter_close_container)(void*, void*) = nullptr;
    unsigned (*iter_append_basic)(void*, int, const void*) = nullptr;
    void* (*send_with_reply_and_block)(void*, void*, int, void*) = nullptr;
    void (*message_unref)(void*) = nullptr;
    void (*connection_close)(void*) = nullptr;
    void (*connection_unref)(void*) = nullptr;
    // (Answering under the old launcher's name, serve_old_name.)
    int (*request_name)(void*, const char*, unsigned, void*) = nullptr;
    unsigned (*add_filter)(void*, int (*)(void*, void*, void*), void*, void (*)(void*)) = nullptr;
    unsigned (*read_write_dispatch)(void*, int) = nullptr;
    int (*message_get_type)(void*) = nullptr;
    const char* (*message_get_path)(void*) = nullptr;
    const char* (*message_get_interface)(void*) = nullptr;
    const char* (*message_get_member)(void*) = nullptr;
    void* (*new_method_return)(void*) = nullptr;
    void* (*new_error)(void*, const char*, const char*) = nullptr;
    unsigned (*send)(void*, void*, uint32_t*) = nullptr;
    unsigned (*iter_init)(void*, void*) = nullptr;
    int (*iter_get_arg_type)(void*) = nullptr;
    void (*iter_recurse)(void*, void*) = nullptr;
    void (*iter_get_basic)(void*, void*) = nullptr;
    unsigned (*iter_next)(void*) = nullptr;

    bool load() {
        library = dlopen("libdbus-1.so.3", RTLD_NOW | RTLD_LOCAL);
        if (!library) return false;
        const auto get = [&](auto& f, const char* name) {
            f = reinterpret_cast<std::remove_reference_t<decltype(f)>>(dlsym(library, name));
            return f != nullptr;
        };
        return get(bus_get_private, "dbus_bus_get_private") &&
               get(set_exit_on_disconnect, "dbus_connection_set_exit_on_disconnect") &&
               get(name_has_owner, "dbus_bus_name_has_owner") &&
               get(new_method_call, "dbus_message_new_method_call") &&
               get(iter_init_append, "dbus_message_iter_init_append") &&
               get(iter_open_container, "dbus_message_iter_open_container") &&
               get(iter_close_container, "dbus_message_iter_close_container") &&
               get(iter_append_basic, "dbus_message_iter_append_basic") &&
               get(send_with_reply_and_block, "dbus_connection_send_with_reply_and_block") &&
               get(message_unref, "dbus_message_unref") && get(connection_close, "dbus_connection_close") &&
               get(connection_unref, "dbus_connection_unref");
    }
    bool load_service() {
        const auto get = [&](auto& f, const char* name) {
            f = reinterpret_cast<std::remove_reference_t<decltype(f)>>(dlsym(library, name));
            return f != nullptr;
        };
        return load() && get(request_name, "dbus_bus_request_name") &&
               get(add_filter, "dbus_connection_add_filter") &&
               get(read_write_dispatch, "dbus_connection_read_write_dispatch") &&
               get(message_get_type, "dbus_message_get_type") && get(message_get_path, "dbus_message_get_path") &&
               get(message_get_interface, "dbus_message_get_interface") &&
               get(message_get_member, "dbus_message_get_member") &&
               get(new_method_return, "dbus_message_new_method_return") &&
               get(new_error, "dbus_message_new_error") && get(send, "dbus_connection_send") &&
               get(iter_init, "dbus_message_iter_init") && get(iter_get_arg_type, "dbus_message_iter_get_arg_type") &&
               get(iter_recurse, "dbus_message_iter_recurse") && get(iter_get_basic, "dbus_message_iter_get_basic") &&
               get(iter_next, "dbus_message_iter_next");
    }
    ~DBus() {
        if (library) dlclose(library);
    }
};

// (DBusMessageIter lives on the caller's stack; libdbus's is smaller than this.)
struct alignas(16) Iter {
    unsigned char bytes[256];
};

constexpr int kSession = 0; // DBUS_BUS_SESSION
constexpr int kArray = 'a', kDictEntry = 'e', kString = 's', kVariant = 'v';
constexpr int kMethodCall = 1;                         // DBUS_MESSAGE_TYPE_METHOD_CALL
constexpr unsigned kDoNotQueue = 4;                     // DBUS_NAME_FLAG_DO_NOT_QUEUE
constexpr int kPrimaryOwner = 1;                        // DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER
constexpr int kHandled = 0, kNotYetHandled = 1;         // DBusHandlerResult

std::string file_uri(const std::string& path) {
    static const char digits[] = "0123456789ABCDEF";
    std::string out = "file://";
    for (const unsigned char c : path) {
        if (std::isalnum(c) || std::strchr("/-._~", c)) {
            out += static_cast<char>(c);
        } else {
            out += '%';
            out += digits[c >> 4];
            out += digits[c & 15];
        }
    }
    return out;
}

enum class Old { kNone, kActivated, kRunning };

// Asks a GApplication holding `name` to show itself (org.freedesktop.Application.Activate, or Open with the .wua),
// with the activation token. kRunning: it is there but did not answer. `activate` false: only whether it is there
// (kRunning), nothing asked of it.
Old activate_old(const InstanceOptions& options, bool activate = true) {
    if (options.old_bus_name.empty() || !std::getenv("DBUS_SESSION_BUS_ADDRESS")) return Old::kNone;
    DBus dbus;
    if (!dbus.load()) return Old::kNone;
    void* bus = dbus.bus_get_private(kSession, nullptr);
    if (!bus) return Old::kNone;
    dbus.set_exit_on_disconnect(bus, 0);
    Old result = Old::kNone;
    if (dbus.name_has_owner(bus, options.old_bus_name.c_str(), nullptr)) {
        result = Old::kRunning;
        if (activate) {
            std::vector<std::string> uris;
            for (const std::string& arg : options.message.args) {
                if (!arg.empty() && arg[0] == '/') uris.push_back(file_uri(arg));
            }
            void* call = dbus.new_method_call(options.old_bus_name.c_str(), options.old_object_path.c_str(),
                                              "org.freedesktop.Application", uris.empty() ? "Activate" : "Open");
            if (call) {
                Iter args, list, entry, variant;
                dbus.iter_init_append(call, &args);
                bool ok = true;
                if (!uris.empty()) {
                    ok = dbus.iter_open_container(&args, kArray, "s", &list);
                    for (const std::string& uri : uris) {
                        const char* text = uri.c_str();
                        ok = ok && dbus.iter_append_basic(&list, kString, &text);
                    }
                    ok = ok && dbus.iter_close_container(&args, &list);
                }
                ok = ok && dbus.iter_open_container(&args, kArray, "{sv}", &list);
                if (!options.message.token.empty()) {
                    // (GTK reads either: Wayland's xdg-activation token, X11's startup notification id.)
                    for (const char* key : {"activation-token", "desktop-startup-id"}) {
                        const char* value = options.message.token.c_str();
                        ok = ok && dbus.iter_open_container(&list, kDictEntry, nullptr, &entry) &&
                             dbus.iter_append_basic(&entry, kString, &key) &&
                             dbus.iter_open_container(&entry, kVariant, "s", &variant) &&
                             dbus.iter_append_basic(&variant, kString, &value) &&
                             dbus.iter_close_container(&entry, &variant) && dbus.iter_close_container(&list, &entry);
                    }
                }
                ok = ok && dbus.iter_close_container(&args, &list);
                if (ok) {
                    if (void* reply = dbus.send_with_reply_and_block(bus, call, 5000, nullptr)) {
                        dbus.message_unref(reply);
                        result = Old::kActivated;
                    }
                }
                dbus.message_unref(call);
            }
        }
    }
    dbus.connection_close(bus);
    dbus.connection_unref(bus);
    return result;
}

// ---- Handing over to a running launcher.

enum class Handed { kOk, kNotListening, kOtherUser, kNoAnswer };

Handed hand_over(const Address& a, const InstanceOptions& options, InstanceClaim* claim) {
    const int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return Handed::kNotListening;
    struct Closer {
        int fd;
        ~Closer() { close(fd); }
    } closer{fd};
    if (connect(fd, reinterpret_cast<const sockaddr*>(&a.address), a.size) != 0) return Handed::kNotListening;
    if (!same_user(fd)) return Handed::kOtherUser;
    std::string reply;
    if (!write_all(fd, encode_forwarded(options.message)) || !read_message(fd, &reply, 5, "\n"))
        return Handed::kNoAnswer;
    // "ok <pid> <files>"
    if (reply.rfind("ok ", 0) != 0) return Handed::kNoAnswer;
    const std::string rest = reply.substr(3, reply.find('\n') - 3);
    const size_t space = rest.find(' ');
    claim->other_pid = std::strtoll(rest.substr(0, space).c_str(), nullptr, 10);
    claim->other_files = space == std::string::npos ? "" : rest.substr(space + 1);
    return Handed::kOk;
}

} // namespace

struct SingleInstance::Os {
    int listener = -1;
    int stop_read = -1, stop_write = -1;
    std::thread thread;
    std::thread bus;                                         // serve_old_name
    std::shared_ptr<std::atomic<bool>> stopping = std::make_shared<std::atomic<bool>>(false);
};

SingleInstance::SingleInstance() : shared_(std::make_shared<Shared>()), os_(std::make_unique<Os>()) {}

SingleInstance::~SingleInstance() {
    *os_->stopping = true;
    if (os_->bus.joinable()) os_->bus.join();
    if (os_->stop_write >= 0) {
        const char c = 0;
        [[maybe_unused]] const ssize_t n = write(os_->stop_write, &c, 1);
    }
    if (os_->thread.joinable()) os_->thread.join();
    for (const int fd : {os_->listener, os_->stop_read, os_->stop_write}) {
        if (fd >= 0) close(fd);
    }
}

namespace {

// "file:///a%20b.wua" -> "/a b.wua"; "" for another kind of URI.
std::string file_path(const std::string& uri) {
    if (uri.rfind("file://", 0) != 0) return {};
    std::string out;
    for (size_t i = 7; i < uri.size(); ++i) {
        if (uri[i] == '%' && i + 2 < uri.size() && std::isxdigit(static_cast<unsigned char>(uri[i + 1])) &&
            std::isxdigit(static_cast<unsigned char>(uri[i + 2]))) {
            out += static_cast<char>(std::stoi(uri.substr(i + 1, 2), nullptr, 16));
            i += 2;
        } else {
            out += uri[i];
        }
    }
    return out.empty() || out[0] != '/' ? std::string() : out;
}

// The reverse of activate_old (C12): this launcher answers under the old GTK launcher's bus name, so that an old
// launcher started now (a second copy of 0.8.0's AppImage, its menu entry) hands over to it as it would to itself:
// GApplication's org.gtk.Actions DescribeAll (the old one asks it first), org.gtk.Application and
// org.freedesktop.Application Activate / Open arrive as later starts (their files and activation token).
struct BusService {
    DBus dbus;
    void* bus = nullptr;
    std::string path;
    std::shared_ptr<SingleInstance::Shared> shared;

    // The activation token of a{sv} platform data at `dict` (an iterator on it).
    std::string token(void* dict) {
        std::string found;
        Iter entries, entry, value;
        if (dbus.iter_get_arg_type(dict) != kArray) return found;
        dbus.iter_recurse(dict, &entries);
        while (dbus.iter_get_arg_type(&entries) == kDictEntry) {
            dbus.iter_recurse(&entries, &entry);
            const char* key = nullptr;
            if (dbus.iter_get_arg_type(&entry) == kString) dbus.iter_get_basic(&entry, &key);
            if (key && dbus.iter_next(&entry) && dbus.iter_get_arg_type(&entry) == kVariant) {
                dbus.iter_recurse(&entry, &value);
                const char* text = nullptr;
                if (dbus.iter_get_arg_type(&value) == kString) dbus.iter_get_basic(&value, &text);
                if (text && (std::strcmp(key, "activation-token") == 0 ||
                             (found.empty() && std::strcmp(key, "desktop-startup-id") == 0)))
                    found = text;
            }
            if (!dbus.iter_next(&entries)) break;
        }
        return found;
    }

    // Open's URIs (as) at `list`: the files' paths.
    std::vector<std::string> paths(void* list) {
        std::vector<std::string> out;
        Iter items;
        if (dbus.iter_get_arg_type(list) != kArray) return out;
        dbus.iter_recurse(list, &items);
        while (dbus.iter_get_arg_type(&items) == kString) {
            const char* uri = nullptr;
            dbus.iter_get_basic(&items, &uri);
            if (uri && !file_path(uri).empty()) out.push_back(file_path(uri));
            if (!dbus.iter_next(&items)) break;
        }
        return out;
    }

    void reply(void* message, const char* error = nullptr) {
        void* answer = error ? dbus.new_error(message, error, "Golden Fist Launcher does not do this")
                             : dbus.new_method_return(message);
        if (!answer) return;
        if (!error && std::strcmp(dbus.message_get_member(message), "DescribeAll") == 0) {
            Iter args, list; // (no actions: a{s(bgav)} empty)
            dbus.iter_init_append(answer, &args);
            dbus.iter_open_container(&args, kArray, "{s(bgav)}", &list);
            dbus.iter_close_container(&args, &list);
        } else if (!error && std::strcmp(dbus.message_get_member(message), "List") == 0) {
            Iter args, list;
            dbus.iter_init_append(answer, &args);
            dbus.iter_open_container(&args, kArray, "s", &list);
            dbus.iter_close_container(&args, &list);
        }
        dbus.send(bus, answer, nullptr);
        dbus.message_unref(answer);
    }

    int handle(void* message) {
        const char* at = dbus.message_get_path(message);
        const char* interface = dbus.message_get_interface(message);
        const char* member = dbus.message_get_member(message);
        if (dbus.message_get_type(message) != kMethodCall || !at || path != at || !interface || !member)
            return kNotYetHandled;
        const std::string i = interface, m = member;
        if (i == "org.gtk.Actions" && (m == "DescribeAll" || m == "List")) {
            reply(message);
            return kHandled;
        }
        const bool gtk = i == "org.gtk.Application", freedesktop = i == "org.freedesktop.Application";
        if ((gtk || freedesktop) && (m == "Activate" || m == "Open" || (freedesktop && m == "ActivateAction"))) {
            Forwarded start;
            Iter args;
            if (dbus.iter_init(message, &args)) {
                if (m == "Open") {
                    start.args = paths(&args);
                    dbus.iter_next(&args);
                    if (gtk) dbus.iter_next(&args); // (org.gtk.Application's hint)
                } else if (m == "ActivateAction") {
                    dbus.iter_next(&args);
                    dbus.iter_next(&args);
                }
                start.token = token(&args);
            }
            {
                std::lock_guard lock(shared->mutex);
                shared->arrived.push_back(std::move(start));
            }
            reply(message);
            if (shared->wake) shared->wake();
            return kHandled;
        }
        reply(message, "org.freedesktop.DBus.Error.UnknownMethod");
        return kHandled;
    }
};

void serve_old_name(InstanceOptions options, std::shared_ptr<SingleInstance::Shared> shared,
                    std::shared_ptr<std::atomic<bool>> stopping) {
    auto service = std::make_unique<BusService>();
    if (!service->dbus.load_service()) return;
    service->bus = service->dbus.bus_get_private(kSession, nullptr);
    if (!service->bus) return;
    service->dbus.set_exit_on_disconnect(service->bus, 0);
    service->path = options.old_object_path;
    service->shared = std::move(shared);
    const auto filter = [](void*, void* message, void* data) { return static_cast<BusService*>(data)->handle(message); };
    if (service->dbus.request_name(service->bus, options.old_bus_name.c_str(), kDoNotQueue, nullptr) == kPrimaryOwner &&
        service->dbus.add_filter(service->bus, filter, service.get(), nullptr)) {
        // (Answered on this thread; 0.2 s between looks at whether the launcher ends.)
        while (!*stopping && service->dbus.read_write_dispatch(service->bus, 200)) {
        }
    }
    service->dbus.connection_close(service->bus);
    service->dbus.connection_unref(service->bus);
}

void listen_for_starts(int listener, int stop, std::shared_ptr<SingleInstance::Shared> shared) {
    const std::string pid = std::to_string(getpid());
    for (;;) {
        pollfd p[2] = {{listener, POLLIN, 0}, {stop, POLLIN, 0}};
        if (poll(p, 2, -1) < 0) {
            if (errno == EINTR) continue;
            return;
        }
        if (p[1].revents) return;
        const int fd = accept4(listener, nullptr, nullptr, SOCK_CLOEXEC);
        if (fd < 0) continue;
        std::string text;
        Forwarded message;
        if (same_user(fd) && read_message(fd, &text, 2, "end\n") && decode_forwarded(text, &message)) {
            {
                std::lock_guard lock(shared->mutex);
                shared->arrived.push_back(std::move(message));
            }
            write_all(fd, "ok " + pid + " " + shared->files + "\n");
            if (shared->wake) shared->wake();
        }
        close(fd);
    }
}

} // namespace

InstanceClaim claim_instance(const InstanceOptions& options) {
    InstanceClaim claim;
    const Address a = address_of(options.name);
    const auto t0 = Clock::now();
    const double patience = options.after ? options.after_seconds : 2;
    bool asked_old = false; // (an old launcher is asked to show itself once, not at each try: compat review #8)
    for (;;) {
        const int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
        if (fd < 0) {
            claim.result = InstanceClaim::Result::kAlone;
            claim.error = std::string("no socket: ") + std::strerror(errno);
            return claim;
        }
        if (bind(fd, reinterpret_cast<const sockaddr*>(&a.address), a.size) == 0 && listen(fd, 16) == 0) {
            // This is the new launcher; an old one may still run (it has no socket).
            const Old old = activate_old(options, !asked_old);
            asked_old = true;
            if (old != Old::kNone && !options.after) {
                close(fd);
                claim.result = InstanceClaim::Result::kOldLauncher;
                claim.error = old == Old::kRunning ? "the old launcher runs but did not answer" : "";
                return claim;
            }
            if (old != Old::kNone) { // (a replaced GTK launcher still ending: wait for it)
                close(fd);
                if (seconds_since(t0) >= patience) {
                    claim.result = InstanceClaim::Result::kFailed;
                    claim.error = "The launcher this one replaces is still running.";
                    return claim;
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }
            auto instance = std::unique_ptr<SingleInstance>(new SingleInstance());
            instance->shared_->wake = options.wake;
            instance->shared_->files = options.files;
            int stop[2];
            if (pipe2(stop, O_CLOEXEC) != 0) {
                close(fd);
                claim.result = InstanceClaim::Result::kAlone;
                claim.error = std::string("no pipe: ") + std::strerror(errno);
                return claim;
            }
            instance->os_->listener = fd;
            instance->os_->stop_read = stop[0];
            instance->os_->stop_write = stop[1];
            instance->os_->thread = std::thread(listen_for_starts, fd, stop[0], instance->shared_);
            // (Under the old launcher's name too, when the session bus is there: an old one started now hands over.)
            if (!options.old_bus_name.empty() && std::getenv("DBUS_SESSION_BUS_ADDRESS"))
                instance->os_->bus = std::thread(serve_old_name, options, instance->shared_, instance->os_->stopping);
            claim.result = InstanceClaim::Result::kPrimary;
            claim.instance = std::move(instance);
            return claim;
        }
        const int error = errno;
        close(fd);
        if (error != EADDRINUSE) {
            claim.result = InstanceClaim::Result::kAlone;
            claim.error = std::string("cannot claim the launcher's name: ") + std::strerror(error);
            return claim;
        }
        if (!options.after) {
            switch (hand_over(a, options, &claim)) {
            case Handed::kOk:
                claim.result = InstanceClaim::Result::kForwarded;
                return claim;
            case Handed::kOtherUser:
                claim.result = InstanceClaim::Result::kAlone;
                claim.error = "another user's program holds the launcher's name";
                return claim;
            case Handed::kNoAnswer:
                claim.result = InstanceClaim::Result::kAlone;
                claim.error = "the running launcher did not answer";
                return claim;
            case Handed::kNotListening: // (it is starting, or just ended: try again)
                break;
            }
        }
        if (seconds_since(t0) >= patience) {
            claim.result = options.after ? InstanceClaim::Result::kFailed : InstanceClaim::Result::kAlone;
            claim.error = options.after ? "Another launcher is still running: close it, then start this one again."
                                        : "the running launcher does not listen";
            return claim;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(options.after ? 100 : 50));
    }
}

} // namespace launcher
