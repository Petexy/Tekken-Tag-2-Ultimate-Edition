#include "host/window.h"

#include "cafe/input.h"
#include "cafe/runtime.h"
#include "host/display_settings.h"
#include "host/keymap.h"

#include <SDL3/SDL.h>
#include <SDL3/SDL_vulkan.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

namespace cafe::host {
namespace {

SDL_Window* g_window = nullptr;
std::atomic<uint32_t> g_width{1280}, g_height{720};
std::atomic<uint32_t> g_display_width{1280}, g_display_height{720};
std::atomic<float> g_display_refresh{60.0f};
std::atomic<float> g_window_refresh{60.0f};

// A display's current refresh rate, as exactly as SDL knows it.
float refresh_of(SDL_DisplayID display) {
    const SDL_DisplayMode* mode = SDL_GetCurrentDisplayMode(display);
    if (mode == nullptr) return 0.0f;
    if (mode->refresh_rate_denominator) {
        return static_cast<float>(double(mode->refresh_rate_numerator) / mode->refresh_rate_denominator);
    }
    return mode->refresh_rate;
}

// The window's display: it moves with the window (and its mode may change).
void update_window_refresh() {
    const SDL_DisplayID display = g_window ? SDL_GetDisplayForWindow(g_window) : 0;
    const float hz = display ? refresh_of(display) : 0.0f;
    if (hz > 0.0f) g_window_refresh = hz;
}

// The keyboard's keys (host/keymap.h): the player's from keyboard.ini, read
// again when the launcher's Settings change it, so new keys apply at once.
// Main thread only.
keymap::Keys g_keymap = keymap::default_keys();
std::optional<keymap::Watcher> g_keymap_file;

// The keymap's numbers are SDL's scancodes: the defaults are these keys.
static_assert(keymap::kKeyCount == SDL_SCANCODE_COUNT);
constexpr SDL_Scancode kDefaultKeys[] = {
    SDL_SCANCODE_W,      SDL_SCANCODE_S,         SDL_SCANCODE_A,    SDL_SCANCODE_D,     // D-pad
    SDL_SCANCODE_I,      SDL_SCANCODE_K,         SDL_SCANCODE_J,    SDL_SCANCODE_L,     // X, B, Y, A
    SDL_SCANCODE_H,      SDL_SCANCODE_SEMICOLON, SDL_SCANCODE_U,    SDL_SCANCODE_O,     // L, R, ZL, ZR
    SDL_SCANCODE_UP,     SDL_SCANCODE_DOWN,      SDL_SCANCODE_LEFT, SDL_SCANCODE_RIGHT, // left stick
    SDL_SCANCODE_RETURN, SDL_SCANCODE_BACKSPACE, SDL_SCANCODE_HOME,                     // +, -, HOME
};
static_assert([] {
    for (size_t i = 0; i < keymap::kInputCount; ++i) {
        if (keymap::kInputs[i].default_key != kDefaultKeys[i]) return false;
    }
    return std::size(kDefaultKeys) == keymap::kInputCount;
}());
static_assert(keymap::kReserved ==
              std::array<uint16_t, 4>{SDL_SCANCODE_F11, SDL_SCANCODE_ESCAPE, SDL_SCANCODE_LGUI, SDL_SCANCODE_RGUI});

void reload_keymap() {
    if (!g_keymap_file) return;
    const std::optional<keymap::Loaded> loaded = g_keymap_file->reload();
    if (!loaded) return;
    for (const std::string& line : loaded->log) std::fprintf(stderr, "ttt2: %s\n", line.c_str());
    g_keymap = loaded->keys;
}

// Gamepads by button position: the Wii U's A is on the right, B at the bottom.
struct PadButton {
    SDL_GamepadButton button;
    uint32_t vpad;
};
constexpr PadButton kPadButtons[] = {
    {SDL_GAMEPAD_BUTTON_EAST, os::vpad::kA},           {SDL_GAMEPAD_BUTTON_SOUTH, os::vpad::kB},
    {SDL_GAMEPAD_BUTTON_NORTH, os::vpad::kX},          {SDL_GAMEPAD_BUTTON_WEST, os::vpad::kY},
    {SDL_GAMEPAD_BUTTON_DPAD_UP, os::vpad::kUp},       {SDL_GAMEPAD_BUTTON_DPAD_DOWN, os::vpad::kDown},
    {SDL_GAMEPAD_BUTTON_DPAD_LEFT, os::vpad::kLeft},   {SDL_GAMEPAD_BUTTON_DPAD_RIGHT, os::vpad::kRight},
    {SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, os::vpad::kL},  {SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, os::vpad::kR},
    {SDL_GAMEPAD_BUTTON_START, os::vpad::kPlus},       {SDL_GAMEPAD_BUTTON_BACK, os::vpad::kMinus},
    {SDL_GAMEPAD_BUTTON_GUIDE, os::vpad::kHome},       {SDL_GAMEPAD_BUTTON_LEFT_STICK, os::vpad::kStickL},
    {SDL_GAMEPAD_BUTTON_RIGHT_STICK, os::vpad::kStickR},
};

// ------------------------------------------------------------ controller kind

std::atomic<Controller> g_controller{Controller::kOther};
bool g_controller_fixed = false;
bool g_controller_used = false; // a button or stick moved: added pads no longer count
std::function<void(Controller)> g_controller_callback;
// A device: the keyboard (0: SDL's gamepad ids never are) or a gamepad.
constexpr SDL_JoystickID kKeyboard = 0;
SDL_JoystickID g_last_used = kKeyboard; // the device with the latest input

Controller kind_of(SDL_JoystickID id) {
    switch (SDL_GetGamepadTypeForID(id)) {
    case SDL_GAMEPAD_TYPE_PS3:
    case SDL_GAMEPAD_TYPE_PS4:
    case SDL_GAMEPAD_TYPE_PS5: return Controller::kPlayStation;
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_PRO:
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_LEFT:
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_RIGHT:
    case SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_PAIR: return Controller::kNintendo;
    default: return Controller::kOther;
    }
}

// The keyboard, as the window's key events tell it. Steam controllers also
// type (Steam's desktop layout, or the controller's own keyboard mode: A is
// Enter, which is the Wii U's Plus here, opening the pause menu while the
// same press is the gamepad's button): keys from a keyboard whose name says
// it is a controller's are left out.
std::array<bool, SDL_SCANCODE_COUNT> g_keys{};

bool controller_keyboard(SDL_KeyboardID id) {
    const char* name = id ? SDL_GetKeyboardNameForID(id) : nullptr;
    if (name == nullptr) return false;
    const std::string n = name;
    return n.find("Steam Controller") != std::string::npos || n.find("Steam Deck") != std::string::npos ||
           n.find("Valve Software") != std::string::npos;
}

void note_key(const SDL_Event& event) {
    switch (event.type) {
    case SDL_EVENT_KEY_DOWN:
    case SDL_EVENT_KEY_UP:
        if (event.key.scancode < SDL_SCANCODE_COUNT && !controller_keyboard(event.key.which)) {
            g_keys[event.key.scancode] = event.type == SDL_EVENT_KEY_DOWN;
        }
        break;
    case SDL_EVENT_WINDOW_FOCUS_LOST: g_keys.fill(false); break;
    default: break;
    }
}

void set_controller(Controller kind) {
    if (g_controller_fixed || g_controller.exchange(kind) == kind) return;
    if (g_controller_callback) g_controller_callback(kind);
}

// Which controller the player picked up: the one with the latest input; a
// pad plugged in counts until anything is pressed.
void note_controller(const SDL_Event& event) {
    switch (event.type) {
    case SDL_EVENT_GAMEPAD_ADDED:
        if (!g_controller_used) {
            g_last_used = event.gdevice.which;
            set_controller(kind_of(event.gdevice.which));
        }
        break;
    case SDL_EVENT_GAMEPAD_BUTTON_DOWN:
        g_controller_used = true;
        g_last_used = event.gbutton.which;
        set_controller(kind_of(event.gbutton.which));
        break;
    case SDL_EVENT_GAMEPAD_AXIS_MOTION:
        if (std::abs(event.gaxis.value) > 16000) {
            g_controller_used = true;
            g_last_used = event.gaxis.which;
            set_controller(kind_of(event.gaxis.which));
        }
        break;
    case SDL_EVENT_KEY_DOWN:
        if (controller_keyboard(event.key.which)) break;
        g_controller_used = true;
        g_last_used = kKeyboard;
        set_controller(Controller::kOther);
        break;
    default: break;
    }
}

float axis(SDL_Gamepad* pad, SDL_GamepadAxis a) {
    const float v = SDL_GetGamepadAxis(pad, a) / 32767.0f;
    return std::fabs(v) < 0.15f ? 0.0f : std::clamp(v, -1.0f, 1.0f);
}

// ------------------------------------------------------------ players

// A device and what it holds.
struct DeviceState {
    SDL_JoystickID id;
    os::GamepadState state;
};

std::function<bool(bool)> g_own_check;
bool g_own = false;                                          // players have controllers of their own
std::array<std::optional<SDL_JoystickID>, kControllers> g_owners; // the device that took each controller
std::vector<SDL_JoystickID> g_plus_held;                     // devices holding + at the last update
std::optional<std::array<std::optional<Device>, kControllers>> g_fixed_devices; // TTT2_DEVICES
std::function<void()> g_devices_callback;
std::mutex g_devices_mutex;
std::array<std::optional<Device>, kControllers> g_devices{Device::kKeyboard};

Device device_of(SDL_JoystickID id) {
    if (id == kKeyboard) return Device::kKeyboard;
    switch (kind_of(id)) {
    case Controller::kPlayStation: return Device::kPlayStation;
    case Controller::kNintendo: return Device::kNintendo;
    case Controller::kOther: break;
    }
    return Device::kXbox;
}

// The devices on the title's controllers, for the pictures of them.
void update_devices() {
    std::array<std::optional<Device>, kControllers> devices{};
    if (g_fixed_devices) {
        devices = *g_fixed_devices;
    } else {
        devices[0] = device_of(g_owners[0].value_or(g_last_used));
        for (size_t c = 1; c < kControllers; ++c) {
            if (g_owners[c]) devices[c] = device_of(*g_owners[c]);
        }
    }
    {
        std::lock_guard lock(g_devices_mutex);
        if (devices == g_devices) return;
        g_devices = devices;
    }
    if (g_devices_callback) g_devices_callback();
}

void merge(os::GamepadState& into, const os::GamepadState& state) {
    into.buttons |= state.buttons;
    into.left_x = std::clamp(into.left_x + state.left_x, -1.0f, 1.0f);
    into.left_y = std::clamp(into.left_y + state.left_y, -1.0f, 1.0f);
    into.right_x = std::clamp(into.right_x + state.right_x, -1.0f, 1.0f);
    into.right_y = std::clamp(into.right_y + state.right_y, -1.0f, 1.0f);
}

// A press of + by another device this soon after one took a controller
// takes none: the same press, as a controller that shows as two devices
// (Steam's virtual gamepad beside the one it stands for) gives it.
constexpr auto kSamePress = std::chrono::milliseconds(100);
std::chrono::steady_clock::time_point g_last_taken{};

void trace_players(const char* what) {
    static const bool trace = std::getenv("TTT2_TRACE_PLAYERS") != nullptr;
    if (!trace) return;
    std::string owners;
    for (size_t c = 0; c < kControllers; ++c) {
        owners += c ? ", " : "";
        owners += g_owners[c] ? (*g_owners[c] == kKeyboard ? std::string("keyboard")
                                                           : "gamepad " + std::to_string(*g_owners[c]))
                              : std::string("-");
    }
    std::fprintf(stderr, "ttt2: players: %s (%s; GamePad, Pro Controllers: %s)\n", what,
                 g_own ? "own controllers" : "all on the GamePad", owners.c_str());
}

// Who drives which of the title's controllers, from the devices' states.
void assign(const std::vector<DeviceState>& devices) {
    const bool joined = std::any_of(g_owners.begin(), g_owners.end(), [](const auto& o) { return o.has_value(); });
    if (const bool own = g_own_check && g_own_check(joined); own != g_own) {
        g_own = own;
        g_owners = {};
        trace_players(g_own ? "a mode for several players" : "a mode for one");
    }
    const auto present = [&](SDL_JoystickID id) {
        return std::any_of(devices.begin(), devices.end(), [&](const DeviceState& d) { return d.id == id; });
    };
    for (auto& owner : g_owners) {
        if (owner && !present(*owner)) {
            owner.reset();
            trace_players("a device left");
        }
    }
    const auto now = std::chrono::steady_clock::now();
    std::vector<SDL_JoystickID> plus_held;
    for (const DeviceState& d : devices) {
        if (!(d.state.buttons & os::vpad::kPlus)) continue;
        plus_held.push_back(d.id);
        const bool pressed = std::find(g_plus_held.begin(), g_plus_held.end(), d.id) == g_plus_held.end();
        if (!g_own || !pressed || std::find(g_owners.begin(), g_owners.end(), d.id) != g_owners.end()) continue;
        const auto free = std::find(g_owners.begin(), g_owners.end(), std::nullopt);
        if (free == g_owners.end() || now - g_last_taken < kSamePress) continue;
        *free = d.id;
        g_last_taken = now;
        trace_players("a device joined");
    }
    g_plus_held = std::move(plus_held);

    os::GamepadState gamepad{};
    std::array<std::optional<os::GamepadState>, os::kProControllers> pro{};
    for (const DeviceState& d : devices) {
        const auto owned = std::find(g_owners.begin(), g_owners.end(), d.id);
        if (owned == g_owners.begin()) {
            gamepad = d.state;
        } else if (owned != g_owners.end()) {
            pro[static_cast<size_t>(owned - g_owners.begin()) - 1] = d.state;
        } else if (!g_owners[0]) {
            merge(gamepad, d.state);
        }
    }
    // The title offers VS Battle and Pair Play only with another controller
    // connected than the GamePad: each device beyond one keeps a Pro
    // Controller connected, idle until a device takes it.
    size_t connected = std::min(devices.size() - 1, size_t{os::kProControllers});
    for (size_t c = 1; c < kControllers; ++c) {
        if (g_owners[c]) connected = std::max(connected, c);
    }
    for (size_t c = 0; c < connected; ++c) {
        if (!pro[c]) pro[c] = os::GamepadState{};
    }
    os::set_gamepad_state(gamepad);
    os::set_pro_controller_states(pro);
    update_devices();
}

void update_input() {
    std::vector<DeviceState> devices;
    os::GamepadState keyboard{};
    for (size_t i = 0; i < keymap::kInputCount; ++i) {
        if (!g_keys[g_keymap[i]]) continue;
        keyboard.buttons |= keymap::kInputs[i].button;
        keyboard.left_x += keymap::kInputs[i].stick_x;
        keyboard.left_y += keymap::kInputs[i].stick_y;
    }
    devices.push_back({kKeyboard, keyboard});

    int count = 0;
    SDL_JoystickID* ids = SDL_GetGamepads(&count);
    for (int i = 0; i < count; ++i) {
        SDL_Gamepad* pad = SDL_GetGamepadFromID(ids[i]);
        if (pad == nullptr) pad = SDL_OpenGamepad(ids[i]);
        if (pad == nullptr) continue;
        os::GamepadState state{};
        for (const PadButton& b : kPadButtons) {
            if (SDL_GetGamepadButton(pad, b.button)) state.buttons |= b.vpad;
        }
        if (axis(pad, SDL_GAMEPAD_AXIS_LEFT_TRIGGER) > 0.5f) state.buttons |= os::vpad::kZL;
        if (axis(pad, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER) > 0.5f) state.buttons |= os::vpad::kZR;
        state.left_x = axis(pad, SDL_GAMEPAD_AXIS_LEFTX);
        state.left_y = -axis(pad, SDL_GAMEPAD_AXIS_LEFTY);
        state.right_x = axis(pad, SDL_GAMEPAD_AXIS_RIGHTX);
        state.right_y = -axis(pad, SDL_GAMEPAD_AXIS_RIGHTY);
        devices.push_back({ids[i], state});
    }
    SDL_free(ids);
    assign(devices);
}

void update_size() {
    int w = 0, h = 0;
    SDL_GetWindowSizeInPixels(g_window, &w, &h);
    g_width = static_cast<uint32_t>(std::max(w, 1));
    g_height = static_cast<uint32_t>(std::max(h, 1));
}

} // namespace

bool open_window(const char* title) {
    // The identifier is the Wayland app id: ttt2.desktop's (ttt2 --install).
    SDL_SetAppMetadata(title, nullptr, "ttt2");
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMEPAD)) {
        std::fprintf(stderr, "ttt2: no window: %s\n", SDL_GetError());
        return false;
    }
    // The player's display settings (display.ini, which the launcher's
    // Settings write) with the environment's values over them, for this run:
    // the renderer takes the scale and the frame rate when it starts.
    const display::Loaded loaded = display::load(display::file_path());
    std::vector<std::string> log = loaded.log;
    display::set_active(display::resolve(loaded.settings, std::getenv("TTT2_FULLSCREEN"), std::getenv("TTT2_SCALE"),
                                         std::getenv("TTT2_FPS"), std::getenv("TTT2_INPUT_DELAY"), log));
    for (const std::string& line : log) std::fprintf(stderr, "ttt2: %s\n", line.c_str());
    const display::Active& active = display::active();
    // The window starts at the render size when that fits on the desktop
    // with room to spare, else at the largest multiple of 640x360 that does
    // (1280x720 on 1080p, 1920x1080 on 1440p, 3200x1800 on 4K at 100 %).
    int window_w = 1280, window_h = 720;
    if (const SDL_DisplayMode* mode = SDL_GetDesktopDisplayMode(SDL_GetPrimaryDisplay())) {
        g_display_width = static_cast<uint32_t>(mode->w * mode->pixel_density);
        g_display_height = static_cast<uint32_t>(mode->h * mode->pixel_density);
        if (const float hz = refresh_of(SDL_GetPrimaryDisplay()); hz > 0.0f) g_display_refresh = g_window_refresh = hz;
        std::tie(window_w, window_h) = display::window_size(mode->w, mode->h, mode->pixel_density, active.scale);
    }
    // Fullscreen keeps the desktop's mode (F11 switches it in the game; that is not saved).
    g_window = SDL_CreateWindow(title, window_w, window_h,
                                SDL_WINDOW_VULKAN | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY |
                                    (active.fullscreen ? SDL_WINDOW_FULLSCREEN : 0));
    if (g_window == nullptr) {
        std::fprintf(stderr, "ttt2: no window: %s\n", SDL_GetError());
        return false;
    }
    update_size();
    update_window_refresh();
    std::fprintf(stderr, "ttt2: window: %ux%u pixels, %s\n", g_width.load(), g_height.load(),
                 active.fullscreen ? "fullscreen" : "windowed");
    g_keymap_file.emplace(keymap::file_path(), [](const std::string& name) {
        return static_cast<uint16_t>(SDL_GetScancodeFromName(name.c_str()));
    });
    reload_keymap();
    return true;
}

bool window_open() { return g_window != nullptr; }

void set_window_icon(const std::vector<uint8_t>& rgba, uint32_t width, uint32_t height) {
    if (g_window == nullptr || rgba.size() < size_t{width} * height * 4) return;
    SDL_Surface* icon = SDL_CreateSurfaceFrom(static_cast<int>(width), static_cast<int>(height), SDL_PIXELFORMAT_RGBA32,
                                              const_cast<uint8_t*>(rgba.data()), static_cast<int>(width * 4));
    if (icon == nullptr) return;
    SDL_SetWindowIcon(g_window, icon);
    SDL_DestroySurface(icon);
}

Controller active_controller() { return g_controller; }

void on_controller_change(std::function<void(Controller)> callback) {
    g_controller_callback = std::move(callback);
    if (const char* forced = std::getenv("TTT2_CONTROLLER")) {
        const std::string kind = forced;
        g_controller = kind == "playstation" ? Controller::kPlayStation
                       : kind == "nintendo"  ? Controller::kNintendo
                                             : Controller::kOther;
        g_controller_fixed = true;
    }
    if (g_controller_callback) g_controller_callback(g_controller);
}

void on_own_controllers(std::function<bool(bool)> check) { g_own_check = std::move(check); }

std::array<std::optional<Device>, kControllers> controller_devices() {
    std::lock_guard lock(g_devices_mutex);
    return g_devices;
}

void on_controller_devices_change(std::function<void()> callback) {
    g_devices_callback = std::move(callback);
    if (const char* fixed = std::getenv("TTT2_DEVICES")) {
        std::array<std::optional<Device>, kControllers> devices{};
        const std::string list = fixed;
        size_t c = 0;
        for (size_t pos = 0; pos <= list.size() && c < kControllers; ++c) {
            const size_t end = std::min(list.find(',', pos), list.size());
            const std::string name = list.substr(pos, end - pos);
            devices[c] = name == "playstation" ? Device::kPlayStation
                         : name == "nintendo"  ? Device::kNintendo
                         : name == "xbox"      ? Device::kXbox
                                               : Device::kKeyboard;
            pos = end + 1;
        }
        g_fixed_devices = devices;
        std::lock_guard lock(g_devices_mutex);
        g_devices = devices;
    }
    if (g_devices_callback) g_devices_callback();
}

bool run_event_loop(const std::function<bool()>& finished) {
    using namespace std::chrono_literals;
    track_thread_cpu("window");
    auto keymap_check = std::chrono::steady_clock::now();
    while (!finished()) {
        // A stat about once a second; the file is read only when it changed.
        if (const auto now = std::chrono::steady_clock::now(); now - keymap_check >= 1s) {
            keymap_check = now;
            reload_keymap();
        }
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            note_controller(event);
            note_key(event);
            switch (event.type) {
            case SDL_EVENT_QUIT:
            case SDL_EVENT_WINDOW_CLOSE_REQUESTED: return false;
            case SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED:
            case SDL_EVENT_WINDOW_RESIZED: update_size(); break;
            case SDL_EVENT_WINDOW_DISPLAY_CHANGED:
            case SDL_EVENT_DISPLAY_CURRENT_MODE_CHANGED: update_window_refresh(); break;
            case SDL_EVENT_KEY_DOWN:
                // (F11 held repeats its press: the first one toggles, once.)
                if (event.key.scancode == SDL_SCANCODE_F11 && !event.key.repeat &&
                    !controller_keyboard(event.key.which)) {
                    const bool full = (SDL_GetWindowFlags(g_window) & SDL_WINDOW_FULLSCREEN) != 0;
                    SDL_SetWindowFullscreen(g_window, !full);
                }
                break;
            default: break;
            }
        }
        update_input();
        std::this_thread::sleep_for(4ms);
    }
    return true;
}

std::vector<const char*> vulkan_instance_extensions() {
    Uint32 count = 0;
    const char* const* names = SDL_Vulkan_GetInstanceExtensions(&count);
    if (names == nullptr) fatal("SDL cannot present with Vulkan: %s", SDL_GetError());
    return std::vector<const char*>(names, names + count);
}

VkSurfaceKHR create_vulkan_surface(VkInstance instance) {
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    if (!SDL_Vulkan_CreateSurface(g_window, instance, nullptr, &surface)) {
        fatal("cannot create a Vulkan surface for the window: %s", SDL_GetError());
    }
    return surface;
}

float display_refresh_rate() { return g_display_refresh; }
float window_refresh_rate() {
    // TTT2_DISPLAY_HZ: report another rate (testing how presentation copes
    // with a display that refreshes otherwise than reported).
    static const float assumed = [] {
        const char* v = std::getenv("TTT2_DISPLAY_HZ");
        return v ? static_cast<float>(std::atof(v)) : 0.0f;
    }();
    return assumed > 0.0f ? assumed : g_window_refresh.load();
}

void display_size(uint32_t& width, uint32_t& height) {
    width = g_display_width;
    height = g_display_height;
}

void drawable_size(uint32_t& width, uint32_t& height) {
    width = g_width;
    height = g_height;
}

} // namespace cafe::host
