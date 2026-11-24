# ttt2-launcher: the players' launcher (Ultimate Launcher) in the Tag Split look, on the toolkit of ../ui (SDL 3)
# over the model of ../model (what the window shows and does) and core's processes (../backend). This folder has
# the program: its loop, its screens, and what it asks of Linux (backend_linux.cpp). Windows' backend comes with
# the Windows program (launcher/windows/); until then this program is Linux only.

# The importer, as the launcher runs it installed: read-only, without its tests and caches.
install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../../tools/characters/ DESTINATION share/ttt2/characters
    PATTERN tests EXCLUDE
    PATTERN __pycache__ EXCLUDE
    PATTERN .pytest_cache EXCLUDE
    PATTERN "*.pyc" EXCLUDE)

if(NOT TARGET ttt2_launcher_ui)
    message(STATUS "SDL 3 not found (TTT2_LAUNCHER_SDL): ttt2-launcher is left out")
    return()
endif()
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    return()
endif()

set(TTT2_LAUNCHER_APP_ID io.github.petexy.TekkenTag2UltimateEdition)
# (Its version is the kit's, set in builder/: a release is tagged v<version>.)
if(NOT TTT2_LAUNCHER_VERSION)
    message(FATAL_ERROR "TTT2_LAUNCHER_VERSION is not set (launcher/builder sets it)")
endif()
if(NOT TTT2_KIT_DIR)
    set(TTT2_KIT_DIR ${CMAKE_BINARY_DIR}/launcher/kit)
endif()

# The parts without SDL (tested on their own): the file browser's folders, the install's steps from its log.
add_library(ttt2_launcher_app_parts STATIC browser.cpp steps.cpp)
target_include_directories(ttt2_launcher_app_parts PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(ttt2_launcher_app_parts PUBLIC launcher_model)
target_compile_features(ttt2_launcher_app_parts PUBLIC cxx_std_20)
target_compile_options(ttt2_launcher_app_parts PRIVATE -Wall -Wextra -Wpedantic)

add_executable(ttt2-launcher
    main.cpp
    app.cpp
    home.cpp
    picker.cpp
    tests_hooks.cpp
    backend_linux.cpp)
find_package(Threads REQUIRED)
target_link_libraries(ttt2-launcher PRIVATE ttt2_launcher_app_parts ttt2_launcher_ui launcher_backend launcher_model
    ttt2_launcher_core_linux Threads::Threads)
ttt2_launcher_program(ttt2-launcher NAME ttt2-launcher FILENAME ttt2-launcher DESCRIPTION "Ultimate Launcher")
# The build tree's kit and the source tree's importer are found when the launcher runs from the build tree (an
# installed one has its own). A package turns that off (launcher/appimage/make_appimage.sh): then the program names
# no folder of the computer it was built on.
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
# This build's commit (launcher/builder reads it; empty without Git), in a file of its own: a new commit
# compiles only that file again.
file(CONFIGURE OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/build_commit.cpp @ONLY CONTENT
    "namespace launcher { extern const char* const kBuildCommit;\nconst char* const kBuildCommit = \"@TTT2_LAUNCHER_COMMIT@\"; }\n")
target_sources(ttt2-launcher PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/build_commit.cpp)

install(TARGETS ttt2-launcher RUNTIME DESTINATION bin)
install(FILES ${TTT2_LAUNCHER_APP_ID}.desktop DESTINATION share/applications)
install(FILES ${TTT2_LAUNCHER_APP_ID}.svg DESTINATION share/icons/hicolor/scalable/apps)

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
    # Frame sequences and the screens' rules (FEEDBACK F1/F4/F6): tests/frames.sh.
    add_test(NAME launcher_app_frames
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/tests/frames.sh $<TARGET_FILE:ttt2-launcher>
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/stub ${CMAKE_CURRENT_BINARY_DIR}/frames ${Python3_EXECUTABLE})
    list(APPEND _app_tests launcher_app_frames)
    set_tests_properties(launcher_app_frames PROPERTIES TIMEOUT 600)
endif()
set_tests_properties(${_app_tests} PROPERTIES LABELS launcher)
