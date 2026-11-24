# SDL 3 for the launcher's own interface (launcher/ui and what links it): the INTERFACE target ttt2_launcher_sdl.
#
#   TTT2_LAUNCHER_SDL=system  the SDL3 package find_package(SDL3) finds, as the game uses it (shared library). On
#                             Windows (players' Set Up Game, TOOLS_ONLY) that is the pinned SDL3 mingw devel zip:
#                             ttt2_launcher_sdl_runtime(<target>) copies its SDL3.dll beside the program.
#   TTT2_LAUNCHER_SDL=static  third_party/SDL (python3 tools/setup_deps.py --launcher: the revision in
#                             dependencies.launcher.lock.json) built here as a project of its own and linked in:
#                             the release programs (AppImage, Ultimate_Launcher-x86_64.exe) need no SDL on the PC.
#   empty (the default)       system when find_package(SDL3) finds it, else static when third_party/SDL is there,
#                             else the launcher's interface is left out.
#
# TTT2_LAUNCHER_SDL_MODE (system, static or none; also in the cache as INTERNAL) says what was chosen.
#
# The static SDL is an ExternalProject, never add_subdirectory: SDL's own CMake defines SDL3::SDL3 as an alias of its
# static library when it builds no shared one, and the game's find_package(SDL3) would then take that target instead
# of the system's library. Only libSDL3.a and its headers are imported, as ttt2_launcher_sdl3. It is built with the
# launcher's compiler, flags (no -march: any x86-64), toolchain file, prefix maps and glibc floor header
# (GlibcFloor.cmake), and every library it can use on Linux (X11, Wayland, libdecor, PipeWire, PulseAudio, ALSA, udev,
# D-Bus) is opened at run time, never linked. The build stops unless SDL's configuration has what the launcher needs
# (LauncherSDLCheck.cmake): old launchers only ask the new one's --version before switching to it, so a launcher
# without a video driver would only show itself broken on the players' PCs.
include_guard(GLOBAL)
get_filename_component(TTT2_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
include("${CMAKE_CURRENT_LIST_DIR}/GlibcFloor.cmake")

set(TTT2_LAUNCHER_SDL "" CACHE STRING
    "SDL 3 of the launcher's interface: system, static (third_party/SDL), or empty (system when found, else static)")
set_property(CACHE TTT2_LAUNCHER_SDL PROPERTY STRINGS "" system static)
set(TTT2_LAUNCHER_SDL_SOURCE "${TTT2_REPO_ROOT}/third_party/SDL" CACHE PATH
    "SDL 3's source for TTT2_LAUNCHER_SDL=static (tools/setup_deps.py --launcher)")

set(mode "${TTT2_LAUNCHER_SDL}")
if(NOT mode MATCHES "^(|system|static)$")
    message(FATAL_ERROR "TTT2_LAUNCHER_SDL is '${mode}': it must be system, static or empty")
endif()
if(mode STREQUAL "" OR mode STREQUAL "system")
    find_package(SDL3 3.2 CONFIG QUIET)
    if(SDL3_FOUND)
        set(mode system)
    elseif(mode STREQUAL "system")
        message(FATAL_ERROR "TTT2_LAUNCHER_SDL=system: find_package(SDL3) finds no SDL 3.2 or newer")
    elseif(EXISTS "${TTT2_LAUNCHER_SDL_SOURCE}/CMakeLists.txt")
        set(mode static)
    else()
        set(mode none)
    endif()
endif()
if(mode STREQUAL "static" AND NOT EXISTS "${TTT2_LAUNCHER_SDL_SOURCE}/CMakeLists.txt")
    message(FATAL_ERROR "TTT2_LAUNCHER_SDL=static: ${TTT2_LAUNCHER_SDL_SOURCE} has no SDL 3 source "
                        "(python3 tools/setup_deps.py --launcher)")
endif()
set(TTT2_LAUNCHER_SDL_MODE ${mode} CACHE INTERNAL "SDL 3 of the launcher's interface: system, static or none" FORCE)
unset(mode)

if(TTT2_LAUNCHER_SDL_MODE STREQUAL "none")
    message(STATUS "Launcher interface: no SDL 3 (neither find_package(SDL3) nor third_party/SDL: "
                   "python3 tools/setup_deps.py --launcher): it is left out")
    return()
endif()

add_library(ttt2_launcher_sdl INTERFACE)
# (The launcher has its own wWinMain/main: SDL_main.h must not rename it.)
target_compile_definitions(ttt2_launcher_sdl INTERFACE SDL_MAIN_HANDLED)
target_link_libraries(ttt2_launcher_sdl INTERFACE ttt2_launcher_glibc_floor)

if(TTT2_LAUNCHER_SDL_MODE STREQUAL "system")
    target_link_libraries(ttt2_launcher_sdl INTERFACE SDL3::SDL3)
    message(STATUS "Launcher interface: the system's SDL ${SDL3_VERSION} (${SDL3_DIR})")
else()
    include(ExternalProject)
    file(READ "${TTT2_REPO_ROOT}/dependencies.launcher.lock.json" lock)
    string(JSON revision GET "${lock}" SDL revision)
    if(CMAKE_BUILD_TYPE)
        set(build_type ${CMAKE_BUILD_TYPE})
    else()
        set(build_type Release)
    endif()
    # What the library is built as. Its features are chosen here, not by what this computer happens to have: the
    # build fails when one is missing (LauncherSDLCheck.cmake).
    set(options
        -DSDL_SHARED=OFF -DSDL_STATIC=ON -DSDL_TEST_LIBRARY=OFF -DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF
        -DSDL_INSTALL=ON -DSDL_INSTALL_DOCS=OFF -DSDL_INSTALL_CPACK=OFF -DSDL_UNINSTALL=OFF
        -DSDL_GPU=OFF -DSDL_CAMERA=OFF -DSDL_RENDER_GPU=OFF
        -DSDL_VIDEO=ON -DSDL_RENDER=ON -DSDL_AUDIO=ON -DSDL_JOYSTICK=ON -DSDL_GAMEPAD=ON -DSDL_HAPTIC=ON
        -DSDL_HIDAPI=ON -DSDL_HIDAPI_JOYSTICK=ON -DSDL_OFFSCREEN=ON -DSDL_DUMMYVIDEO=ON
        # (AVX-512 code, even only run where the processor has it, fails the AppImage's check)
        -DSDL_AVX512F=OFF
        -DSDL_CCACHE=OFF -DSDL_RPATH=OFF)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        list(APPEND options
            -DSDL_DEPS_SHARED=ON -DSDL_X11=ON -DSDL_X11_SHARED=ON -DSDL_WAYLAND=ON -DSDL_WAYLAND_SHARED=ON
            -DSDL_WAYLAND_LIBDECOR=ON -DSDL_WAYLAND_LIBDECOR_SHARED=ON -DSDL_KMSDRM=OFF
            -DSDL_PIPEWIRE=ON -DSDL_PIPEWIRE_SHARED=ON -DSDL_PULSEAUDIO=ON -DSDL_PULSEAUDIO_SHARED=ON
            -DSDL_ALSA=ON -DSDL_ALSA_SHARED=ON -DSDL_JACK=OFF -DSDL_SNDIO=OFF -DSDL_OSS=OFF
            -DSDL_LIBUDEV=ON -DSDL_DBUS=ON -DSDL_IBUS=ON -DSDL_LIBURING=OFF -DSDL_HIDAPI_LIBUSB=OFF
            -DSDL_VULKAN=ON -DSDL_OPENGL=ON -DSDL_OPENGLES=ON)
    elseif(WIN32)
        list(APPEND options -DSDL_DIRECTX=ON -DSDL_RENDER_D3D11=ON -DSDL_RENDER_D3D12=OFF -DSDL_XINPUT=ON
            -DSDL_WASAPI=ON)
    endif()
    set(c_flags "${CMAKE_C_FLAGS}")
    if(TTT2_GLIBC_FLOOR_HEADER)
        # (The header from GlibcFloor.cmake, as the launcher's own code gets it.)
        string(APPEND c_flags " -include ${TTT2_GLIBC_FLOOR_HEADER}")
    endif()
    string(STRIP "${c_flags}" c_flags)
    set(forwarded
        -DCMAKE_BUILD_TYPE=${build_type}
        -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
        -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER}
        "-DCMAKE_C_FLAGS=${c_flags}"
        "-DCMAKE_EXE_LINKER_FLAGS=${CMAKE_EXE_LINKER_FLAGS}"
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON
        -DCMAKE_INSTALL_LIBDIR=lib
        -DCMAKE_INSTALL_INCLUDEDIR=include)
    foreach(variable CMAKE_TOOLCHAIN_FILE CMAKE_C_COMPILER_TARGET CMAKE_SYSROOT CMAKE_C_COMPILER_LAUNCHER
                     CMAKE_RC_COMPILER CMAKE_AR CMAKE_RANLIB CMAKE_MAKE_PROGRAM TTT2_MINGW_PREFIX)
        if(DEFINED ${variable} AND NOT "${${variable}}" STREQUAL "")
            list(APPEND forwarded "-D${variable}=${${variable}}")
        endif()
    endforeach()
    # A folder of its own for each source revision, compiler and setting: changing one builds SDL afresh instead of
    # reconfiguring a build made otherwise.
    string(SHA256 key "${revision};${CMAKE_C_COMPILER_ID};${CMAKE_C_COMPILER_VERSION};${options};${forwarded}")
    string(SUBSTRING "${key}" 0 12 key)
    set(TTT2_LAUNCHER_SDL_PREFIX "${CMAKE_BINARY_DIR}/launcher-sdl3/${key}")
    set(install "${TTT2_LAUNCHER_SDL_PREFIX}/install")
    set(library "${install}/lib/${CMAKE_STATIC_LIBRARY_PREFIX}SDL3${CMAKE_STATIC_LIBRARY_SUFFIX}")
    string(TOLOWER "${build_type}" config)
    ExternalProject_Add(ttt2_launcher_sdl3_build
        SOURCE_DIR "${TTT2_LAUNCHER_SDL_SOURCE}"
        BINARY_DIR "${TTT2_LAUNCHER_SDL_PREFIX}/build"
        INSTALL_DIR "${install}"
        PREFIX "${TTT2_LAUNCHER_SDL_PREFIX}"
        CMAKE_ARGS ${forwarded} "-DCMAKE_INSTALL_PREFIX=<INSTALL_DIR>" ${options}
        BUILD_ALWAYS ON
        BUILD_BYPRODUCTS "${library}"
        USES_TERMINAL_CONFIGURE ON
        USES_TERMINAL_BUILD ON
        USES_TERMINAL_INSTALL ON)
    ExternalProject_Add_Step(ttt2_launcher_sdl3_build check_features
        COMMAND ${CMAKE_COMMAND} "-DCONFIG=${TTT2_LAUNCHER_SDL_PREFIX}/build/include-config-${config}/build_config/SDL_build_config.h"
                "-DSYSTEM=${CMAKE_SYSTEM_NAME}" -P "${TTT2_REPO_ROOT}/cmake/LauncherSDLCheck.cmake"
        COMMENT "Checking that SDL has what the launcher needs"
        DEPENDEES configure
        DEPENDERS build
        DEPENDS "${TTT2_REPO_ROOT}/cmake/LauncherSDLCheck.cmake")
    # (An imported target's include folder must exist when CMake generates the build.)
    file(MAKE_DIRECTORY "${install}/include")
    add_library(ttt2_launcher_sdl3 STATIC IMPORTED GLOBAL)
    set_target_properties(ttt2_launcher_sdl3 PROPERTIES
        IMPORTED_LOCATION "${library}"
        INTERFACE_INCLUDE_DIRECTORIES "${install}/include")
    add_dependencies(ttt2_launcher_sdl3 ttt2_launcher_sdl3_build)
    target_link_libraries(ttt2_launcher_sdl INTERFACE ttt2_launcher_sdl3)
    # What libSDL3.a needs at link time (its sdl3.pc's Libs.private, which only exists once it is built).
    if(WIN32)
        target_link_libraries(ttt2_launcher_sdl INTERFACE
            m kernel32 user32 gdi32 winmm imm32 ole32 oleaut32 version uuid advapi32 setupapi shell32 dinput8)
    else()
        find_package(Threads REQUIRED)
        # (Only what is used is recorded as needed: libraries such as libdl.so.2 only hold glibc's old names.)
        target_link_options(ttt2_launcher_sdl INTERFACE "LINKER:--as-needed")
        target_link_libraries(ttt2_launcher_sdl INTERFACE m ${CMAKE_DL_LIBS} Threads::Threads)
        # Linked by LLD where there is one and no linker was chosen (as make_appimage.sh links): GNU ld copies the x86
        # ISA level of the system's startup files into every program, x86-64-v4 on a system built for its own
        # processor (CachyOS), and glibc then refuses to start it on any processor without AVX-512; LLD writes none
        # (release_checks.sh checks it).
        if(NOT CMAKE_EXE_LINKER_FLAGS MATCHES "-fuse-ld=" AND NOT CMAKE_LINKER_TYPE)
            find_program(TTT2_LD_LLD NAMES ld.lld)
            if(TTT2_LD_LLD)
                target_link_options(ttt2_launcher_sdl INTERFACE -fuse-ld=lld)
            endif()
        endif()
    endif()
    message(STATUS "Launcher interface: SDL ${revision} built here (static, ${TTT2_LAUNCHER_SDL_PREFIX})")
    unset(lock)
    unset(revision)
    unset(key)
    unset(install)
    unset(library)
    unset(config)
    unset(options)
    unset(forwarded)
    unset(build_type)
    unset(c_flags)
endif()

# ttt2_launcher_sdl_runtime(<target>): with the system's SDL on Windows, SDL3.dll is copied beside <target> after it
# is built (as the game does); elsewhere nothing is needed.
function(ttt2_launcher_sdl_runtime target)
    if(WIN32 AND TTT2_LAUNCHER_SDL_MODE STREQUAL "system" AND TARGET SDL3::SDL3-shared)
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_FILE:SDL3::SDL3-shared> $<TARGET_FILE_DIR:${target}>
            VERBATIM)
    endif()
endfunction()
