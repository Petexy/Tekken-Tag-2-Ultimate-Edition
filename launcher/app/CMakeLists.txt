# ttt2-launcher: the players' launcher (Golden Fist Launcher) in the Tag Split look, on the toolkit of ../ui (SDL 3)
# over the model of ../model (what the window shows and does) and core's processes (../backend). This folder has
# the program: its loop, its screens, and what it asks of the OS (backend_sdl.cpp through SDL; backend_linux.cpp
# Linux's install, kit and AppImage; backend_windows.cpp + windows_app.cpp Windows' files, first start and
# --query answers). On Windows it is the CMake target ttt2-launcher of a player's Set Up Game
# (TOOLS_ONLY, on the pinned SDL3 DLL) and of the release .exe (TTT2_LAUNCHER_ONLY, SDL built in).

if(NOT WIN32)
    # The importer, as the launcher runs it installed: read-only, without its tests and caches.
    install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../../tools/characters/ DESTINATION share/ttt2/characters
        PATTERN tests EXCLUDE
        PATTERN __pycache__ EXCLUDE
        PATTERN .pytest_cache EXCLUDE
        PATTERN "*.pyc" EXCLUDE)
    # The launcher's catalogs and their reader, for the importer's texts (ttt2char/texts.py: ../i18n beside it).
    install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/../i18n/launcher_texts.py DESTINATION share/ttt2/i18n)
    install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../i18n/ DESTINATION share/ttt2/i18n FILES_MATCHING PATTERN "*.txt"
        PATTERN __pycache__ EXCLUDE)
endif()

if(NOT TARGET ttt2_launcher_ui)
    message(STATUS "SDL 3 not found (TTT2_LAUNCHER_SDL): ttt2-launcher is left out")
    return()
endif()
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" AND NOT WIN32)
    return()
endif()

set(TTT2_LAUNCHER_APP_ID io.github.petexy.TekkenTag2UltimateEdition)
# (Its version is the kit's, set in builder/: a release is tagged v<version>. Without builder/ (Windows, a
# launcher-only build): cmake/LauncherVersion.cmake reads the same line.)
if(NOT TTT2_LAUNCHER_VERSION)
    # (Read here: cmake/LauncherVersion.cmake is included once, in ui/'s scope.)
    file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/../builder/CMakeLists.txt" _version_line
        REGEX "^set\\(TTT2_LAUNCHER_VERSION [0-9.]+\\)$")
    string(REGEX REPLACE "^set\\(TTT2_LAUNCHER_VERSION ([0-9.]+)\\)$" "\\1" TTT2_LAUNCHER_VERSION "${_version_line}")
endif()
if(NOT TTT2_LAUNCHER_VERSION)
    message(FATAL_ERROR "TTT2_LAUNCHER_VERSION is not set (launcher/builder sets it)")
endif()

# The parts without SDL (tested on their own): the file browser's folders, the install's steps from its log,
# launcher.ini, the first start's progress.
add_library(ttt2_launcher_app_parts STATIC browser.cpp steps.cpp launcher_ini.cpp)
target_include_directories(ttt2_launcher_app_parts PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(ttt2_launcher_app_parts PUBLIC launcher_model)
target_compile_features(ttt2_launcher_app_parts PUBLIC cxx_std_20)
target_compile_options(ttt2_launcher_app_parts PRIVATE -Wall -Wextra -Wpedantic)

add_executable(ttt2-launcher
    main.cpp
    app.cpp
    home.cpp
    fighters.cpp
    settings_screen.cpp
    picker.cpp
    tests_hooks.cpp
    backend_sdl.cpp)
find_package(Threads REQUIRED)
if(WIN32)
    target_sources(ttt2-launcher PRIVATE backend_windows.cpp windows_app.cpp)
    target_link_libraries(ttt2-launcher PRIVATE ttt2_launcher_app_parts ttt2_launcher_ui launcher_backend
        launcher_model ttt2_launcher_core Threads::Threads)
else()
    target_sources(ttt2-launcher PRIVATE backend_linux.cpp)
    target_link_libraries(ttt2-launcher PRIVATE ttt2_launcher_app_parts ttt2_launcher_ui launcher_backend
        launcher_model ttt2_launcher_core_linux Threads::Threads)
endif()
target_link_libraries(ttt2-launcher PRIVATE ttt2_launcher_game_art)  # (the added fighters' portraits)
ttt2_launcher_program(ttt2-launcher NAME ttt2-launcher FILENAME ttt2-launcher.exe DESCRIPTION "Golden Fist Launcher")
if(NOT WIN32)
    if(NOT TTT2_KIT_DIR)
        set(TTT2_KIT_DIR ${CMAKE_BINARY_DIR}/launcher/kit)
    endif()
    # The build tree's kit and the source tree's importer are found when the launcher runs from the build tree (an
    # installed one has its own). A package turns that off (launcher/appimage/make_appimage.sh): then the program
    # names no folder of the computer it was built on.
    option(TTT2_LAUNCHER_BUILD_TREE_PATHS "ttt2-launcher also looks in its build and source trees" ON)
    if(TTT2_LAUNCHER_BUILD_TREE_PATHS)
        set(build_kit ${TTT2_KIT_DIR})
        set(source_importer ${CMAKE_CURRENT_SOURCE_DIR}/../../tools/characters)
    else()
        set(build_kit "")
        set(source_importer "")
    endif()
    target_compile_definitions(ttt2-launcher PRIVATE
        TTT2_LAUNCHER_BUILD_KIT="${build_kit}"
        TTT2_LAUNCHER_SOURCE_IMPORTER="${source_importer}")
endif()
# This build's commit (launcher/builder reads it; empty without Git), in a file of its own: a new commit
# compiles only that file again.
file(CONFIGURE OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/build_commit.cpp @ONLY CONTENT
    "namespace launcher { extern const char* const kBuildCommit;\nconst char* const kBuildCommit = \"@TTT2_LAUNCHER_COMMIT@\"; }\n")
target_sources(ttt2-launcher PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/build_commit.cpp)

if(WIN32)
    # (Its tests: the parts under Wine when cross-built; the program's own runs: tests/windows/run_wine.sh.)
    add_executable(launcher_app_test tests/app_test.cpp)
    target_link_libraries(launcher_app_test PRIVATE ttt2_launcher_app_parts)
    target_link_options(launcher_app_test PRIVATE -static)
    add_test(NAME launcher_app_test COMMAND launcher_app_test ${CMAKE_CURRENT_BINARY_DIR}/app-test)
    add_test(NAME launcher_app_version COMMAND ttt2-launcher --version)
    # The stand-ins of python/curl/certutil/findstr/tar.exe for tests/windows/run_wine.sh.
    add_executable(launcher_win_stub tests/windows/stub_tools.cpp)
    target_compile_features(launcher_win_stub PRIVATE cxx_std_20)
    target_link_options(launcher_win_stub PRIVATE -static)
    set_tests_properties(launcher_app_version PROPERTIES PASS_REGULAR_EXPRESSION "^ttt2-launcher ${TTT2_LAUNCHER_VERSION}")
    set_tests_properties(launcher_app_test launcher_app_version PROPERTIES LABELS launcher)
    if(TTT2_TOOLS_ONLY)
        # (The players' Set Up Game build: this program made a release .exe says its version and unpacks its files,
        # as old launchers' updates check it. A launcher-only build has launcher_release_exe_test instead.)
        find_package(Python3 COMPONENTS Interpreter)
        if(Python3_Interpreter_FOUND)
            add_test(NAME windows_launcher_exe_test COMMAND ${Python3_EXECUTABLE}
                ${CMAKE_CURRENT_SOURCE_DIR}/../windows/test_launcher_exe.py $<TARGET_FILE:ttt2-launcher>
                ${TTT2_LAUNCHER_VERSION} WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../windows)
            set_tests_properties(windows_launcher_exe_test PROPERTIES LABELS launcher TIMEOUT 900)
        endif()
    endif()
    if(CMAKE_CROSSCOMPILING AND NOT CMAKE_CROSSCOMPILING_EMULATOR)
        find_program(TTT2_WINE wine)
        foreach(t launcher_app_test ttt2-launcher)
            if(TTT2_WINE)
                set_property(TARGET ${t} PROPERTY CROSSCOMPILING_EMULATOR "${TTT2_WINE}")
            endif()
        endforeach()
        if(TTT2_WINE)
            set_tests_properties(launcher_app_test launcher_app_version PROPERTIES ENVIRONMENT_MODIFICATION
                "WINEDEBUG=set:-all;WINEDLLOVERRIDES=set:winemenubuilder.exe=d;DISPLAY=unset:;WAYLAND_DISPLAY=unset:;DBUS_SESSION_BUS_ADDRESS=unset:")
            # The program itself under headless Wine against stub tools (its own prefix in the build folder).
            find_program(TTT2_BASH bash)
            find_package(Python3 COMPONENTS Interpreter)
            if(TTT2_BASH AND Python3_Interpreter_FOUND)
                add_test(NAME launcher_app_wine COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/windows/run_wine.sh
                    ${CMAKE_BINARY_DIR} ${CMAKE_CURRENT_BINARY_DIR}/wine-run)
                set_tests_properties(launcher_app_wine PROPERTIES LABELS launcher TIMEOUT 900
                    ENVIRONMENT "WINE=${TTT2_WINE};PYTHON=${Python3_EXECUTABLE}")
            endif()
        else()
            set_tests_properties(launcher_app_test launcher_app_version PROPERTIES DISABLED ON)
        endif()
    endif()
    return()
endif()

install(TARGETS ttt2-launcher RUNTIME DESTINATION bin)
install(FILES ${TTT2_LAUNCHER_APP_ID}.desktop DESTINATION share/applications)
install(FILES ${TTT2_LAUNCHER_APP_ID}.svg DESTINATION share/icons/hicolor/scalable/apps)
# The license texts, at the paths THIRD_PARTY_NOTICES.md names (the AppImage must have them: release_license_files in
# ../appimage/release_checks.sh).
set(licenses_source ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(licenses_folder share/licenses/ttt2-launcher)
install(FILES ${licenses_source}/LICENSE ${licenses_source}/THIRD_PARTY_NOTICES.md DESTINATION ${licenses_folder})
install(DIRECTORY ${licenses_source}/licenses DESTINATION ${licenses_folder})
install(DIRECTORY ${licenses_source}/launcher/ui/fonts DESTINATION ${licenses_folder}/launcher/ui
    FILES_MATCHING PATTERN OFL.txt)

# Tests: the parts (no window), and the program itself offscreen against stub programs (tests/stub: an importer
# answering from a fixture, a builder printing the protocol, a game writing a marker), in a scratch home.
add_executable(launcher_app_test tests/app_test.cpp)
target_link_libraries(launcher_app_test PRIVATE ttt2_launcher_app_parts)
target_compile_options(launcher_app_test PRIVATE -Wall -Wextra)
add_test(NAME launcher_app_test COMMAND launcher_app_test ${CMAKE_CURRENT_BINARY_DIR}/app-test)
add_test(NAME launcher_app_version COMMAND ttt2-launcher --version)
set_tests_properties(launcher_app_version PROPERTIES PASS_REGULAR_EXPRESSION "^ttt2-launcher ${TTT2_LAUNCHER_VERSION}\n$")
find_program(TTT2_BASH bash)
find_package(Python3 COMPONENTS Interpreter QUIET)
set(_app_tests launcher_app_test launcher_app_version)
if(TTT2_BASH AND Python3_Interpreter_FOUND)
    add_test(NAME launcher_app_e2e
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/e2e.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/stub ${CMAKE_CURRENT_BINARY_DIR}/e2e ${Python3_EXECUTABLE})
    list(APPEND _app_tests launcher_app_e2e)
    set_tests_properties(launcher_app_e2e PROPERTIES TIMEOUT 240)
    # Frame sequences and the screens' rules: tests/frames.sh.
    add_test(NAME launcher_app_frames
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/frames.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/stub ${CMAKE_CURRENT_BINARY_DIR}/frames ${Python3_EXECUTABLE})
    list(APPEND _app_tests launcher_app_frames)
    # (About 3.5 minutes on 4 cores: large windows drawn by the software renderer.)
    set_tests_properties(launcher_app_frames PROPERTIES TIMEOUT 900)
    # Fighters and Settings (choosing a key, Add/Remove/Cancel): tests/screens.sh.
    add_test(NAME launcher_app_screens
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/screens.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/stub ${CMAKE_CURRENT_BINARY_DIR}/screens ${Python3_EXECUTABLE})
    list(APPEND _app_tests launcher_app_screens)
    set_tests_properties(launcher_app_screens PROPERTIES TIMEOUT 1200)
    # The sounds as heard: SDL's disk audio driver into files, Sound on / off / its button / Play.
    add_test(NAME launcher_app_sounds
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/sounds.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/stub ${CMAKE_CURRENT_BINARY_DIR}/sounds ${Python3_EXECUTABLE})
    list(APPEND _app_tests launcher_app_sounds)
    set_tests_properties(launcher_app_sounds PROPERTIES TIMEOUT 300)
    # The update's way back: an update to a version that breaks before its first frame (tests/way_back).
    find_program(TTT2_CURL curl)
    if(TTT2_CURL)
        add_executable(launcher_way_back_broken tests/way_back/broken.cpp)
        add_test(NAME launcher_app_way_back
            COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/way_back/way_back.sh $<TARGET_FILE:ttt2-launcher>
                    $<TARGET_FILE:launcher_way_back_broken> ${CMAKE_CURRENT_BINARY_DIR}/way-back ${Python3_EXECUTABLE})
        list(APPEND _app_tests launcher_app_way_back)
        set_tests_properties(launcher_app_way_back PROPERTIES TIMEOUT 300)
    endif()
    # The other video driver when the one the player named fails: a headless cage, else skipped.
    add_test(NAME launcher_app_video_fallback
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/video_fallback.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_BINARY_DIR}/video-fallback)
    list(APPEND _app_tests launcher_app_video_fallback)
    set_tests_properties(launcher_app_video_fallback PROPERTIES TIMEOUT 400 SKIP_RETURN_CODE 77)
    # The in-app browser: long lists at two sizes, Show hidden, and a folder slow to open
    # (tests/slow_folders.c, an LD_PRELOAD: the window never waits for it).
    add_library(launcher_slow_folders MODULE tests/slow_folders.c)
    target_link_libraries(launcher_slow_folders PRIVATE ${CMAKE_DL_LIBS})
    add_test(NAME launcher_app_picker
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/picker.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/stub ${CMAKE_CURRENT_BINARY_DIR}/picker ${Python3_EXECUTABLE}
                $<TARGET_FILE:launcher_slow_folders>)
    list(APPEND _app_tests launcher_app_picker)
    set_tests_properties(launcher_app_picker PROPERTIES TIMEOUT 600)
    # Left alone, as a player starts it: frames only when something changed, ambient motion
    # at most 30 a second and paused after 20 s, none with Reduce motion or while the game runs: tests/idle.sh.
    add_test(NAME launcher_app_idle
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/idle.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/stub ${CMAKE_CURRENT_BINARY_DIR}/idle ${Python3_EXECUTABLE})
    list(APPEND _app_tests launcher_app_idle)
    set_tests_properties(launcher_app_idle PROPERTIES TIMEOUT 180)
endif()
set_tests_properties(${_app_tests} PROPERTIES LABELS launcher)
