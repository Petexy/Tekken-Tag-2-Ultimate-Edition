# The launcher's logic without GTK: finding the install, the kit, the importer
# and Python; reading the builder's and the importer's output; checking the
# PC before an install; uninstalling; the game's keyboard keys and display
# settings; the launcher's own updates. Tested on its own.
#
# Two libraries: ttt2_launcher_core is what any OS's launcher uses (JSON, the
# progress lines, keyboard.ini, display.ini, release numbers and GitHub's
# answers, the test actions, the importer's answers, writing settings files),
# ttt2_launcher_core_linux what only Linux's has (its folders and the install,
# the PC's checks before an install, uninstalling, the AppImage). The Windows
# programs link only the first; it builds with MinGW too.
#
# display.ini is read and written by the game's own code for it (runtime/src,
# found from here so that this folder also builds as a project's
# subdirectory of its own): what the launcher writes is what the game reads.
set(runtime_src ${CMAKE_CURRENT_SOURCE_DIR}/../../runtime/src)
add_library(ttt2_launcher_core STATIC
    display.cpp
    distro.cpp
    files.cpp
    json.cpp
    keymap.cpp
    paths_common.cpp
    protocol.cpp
    release.cpp
    status.cpp
    test_actions.cpp
    ${runtime_src}/host/display_settings.cpp)
target_include_directories(ttt2_launcher_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR} ${runtime_src})
target_compile_features(ttt2_launcher_core PUBLIC cxx_std_20)
target_compile_options(ttt2_launcher_core PRIVATE -Wall -Wextra -Wpedantic)

# Match SDL's key-name inventory (keyboard.ini names keys as the game's SDL does): read from the SDL 3 headers the
# game is built with (find_package(SDL3); on Windows the pinned mingw one), else the launcher's own SDL source
# (third_party/SDL), so that nothing here compiles or links against SDL (the launcher-only and MinGW builds have none
# of the game's).
if(NOT TARGET SDL3::Headers)
    find_package(SDL3 CONFIG QUIET)
endif()
set(sdl_scancode_headers "")
if(TARGET SDL3::Headers)
    get_target_property(sdl_include_dirs SDL3::Headers INTERFACE_INCLUDE_DIRECTORIES)
    foreach(dir IN LISTS sdl_include_dirs)
        list(APPEND sdl_scancode_headers "${dir}/SDL3/SDL_scancode.h")
    endforeach()
endif()
list(APPEND sdl_scancode_headers
    "${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/windows/SDL3-3.4.18/x86_64-w64-mingw32/include/SDL3/SDL_scancode.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/SDL/include/SDL3/SDL_scancode.h")
foreach(header IN LISTS sdl_scancode_headers)
    if(EXISTS "${header}")
        file(STRINGS "${header}" front REGEX "SDL_SCANCODE_FRONT[ \t]*=")
        if(front)
            target_compile_definitions(ttt2_launcher_core PRIVATE TTT2_SDL_HAS_FRONT)
        endif()
        message(STATUS "Launcher core: SDL key names as ${header}")
        break()
    endif()
endforeach()

if(WIN32)
    return()
endif()

add_library(ttt2_launcher_core_linux STATIC
    appimage.cpp
    paths.cpp
    system.cpp
    uninstall.cpp)
target_link_libraries(ttt2_launcher_core_linux PUBLIC ttt2_launcher_core)
target_compile_options(ttt2_launcher_core_linux PRIVATE -Wall -Wextra -Wpedantic)

add_executable(launcher_core_test core_test.cpp)
target_link_libraries(launcher_core_test PRIVATE ttt2_launcher_core_linux)
target_compile_options(launcher_core_test PRIVATE -Wall -Wextra)
add_test(NAME launcher_core_test COMMAND launcher_core_test ${CMAKE_CURRENT_BINARY_DIR})

# The key tables are cross-checked against Linux's and SDL3's headers when
# this computer has them (where they are looked for when the test runs).
find_file(TTT2_INPUT_EVENT_CODES_H linux/input-event-codes.h)
find_file(TTT2_SDL_SCANCODE_H SDL3/SDL_scancode.h)
foreach(header TTT2_INPUT_EVENT_CODES_H TTT2_SDL_SCANCODE_H)
    if(NOT ${header})
        set(${header} /nonexistent/${header})
    endif()
endforeach()
add_executable(launcher_keymap_test keymap_test.cpp)
target_link_libraries(launcher_keymap_test PRIVATE ttt2_launcher_core_linux)
target_compile_options(launcher_keymap_test PRIVATE -Wall -Wextra)
add_test(NAME launcher_keymap_test
    COMMAND launcher_keymap_test ${CMAKE_CURRENT_BINARY_DIR} ${TTT2_INPUT_EVENT_CODES_H} ${TTT2_SDL_SCANCODE_H})
