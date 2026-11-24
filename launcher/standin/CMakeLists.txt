# launcher_standin (standin.cpp): the new launcher's stand-in in the release packaging and its tests until
# launcher/app's ttt2-launcher is the SDL program: linked as that one is (ttt2_launcher_program), started as it is
# (launcher/core/startup.h), one frame drawn with SDL. make_appimage.sh --ui sdl and make_launcher_exe.py
# --cmake-target package it (each names it in one place: launcher_target / DEFAULT_CMAKE_TARGET); switching those to
# ttt2-launcher makes this folder unused.
if(NOT COMMAND ttt2_launcher_program)
    return() # (no SDL: launcher/ui is left out)
endif()
include("${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/LauncherVersion.cmake")
add_executable(launcher_standin standin.cpp)
target_link_libraries(launcher_standin PRIVATE ttt2_launcher_core)
ttt2_launcher_program(launcher_standin NAME ttt2-launcher FILENAME Ultimate_Launcher-x86_64.exe
    DESCRIPTION "Ultimate Launcher")

# The AppImage's launcher while it is the stand-in (make_appimage.sh --ui sdl sets this): installed as
# bin/ttt2-launcher with the launcher's menu entry and icon, as launcher/app installs ttt2-launcher.
option(TTT2_LAUNCHER_STANDIN_INSTALL "Install launcher_standin as bin/ttt2-launcher (make_appimage.sh --ui sdl)" OFF)
if(TTT2_LAUNCHER_STANDIN_INSTALL)
    set(app_id io.github.petexy.TekkenTag2UltimateEdition)
    set_target_properties(launcher_standin PROPERTIES OUTPUT_NAME ttt2-launcher)
    install(TARGETS launcher_standin RUNTIME DESTINATION bin)
    install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/../app/${app_id}.desktop DESTINATION share/applications)
    install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/../app/${app_id}.svg DESTINATION share/icons/hicolor/scalable/apps)
endif()

# Its start as the launcher's: --version without SDL ("ttt2-launcher <version>", what an update asks), an unknown
# option refused (2).
add_test(NAME launcher_standin_version COMMAND launcher_standin --version)
set_tests_properties(launcher_standin_version PROPERTIES
    PASS_REGULAR_EXPRESSION "^ttt2-launcher ${TTT2_LAUNCHER_VERSION}\n$")
add_test(NAME launcher_standin_unknown_option COMMAND launcher_standin --no-such-option)
set_tests_properties(launcher_standin_unknown_option PROPERTIES WILL_FAIL ON)
set_tests_properties(launcher_standin_version launcher_standin_unknown_option PROPERTIES LABELS launcher)
if(CMAKE_CROSSCOMPILING AND NOT CMAKE_CROSSCOMPILING_EMULATOR)
    find_program(TTT2_WINE wine)
    if(TTT2_WINE AND WIN32)
        set_property(TARGET launcher_standin PROPERTY CROSSCOMPILING_EMULATOR "${TTT2_WINE}")
        set_tests_properties(launcher_standin_version launcher_standin_unknown_option PROPERTIES
            ENVIRONMENT_MODIFICATION
            "WINEDEBUG=set:-all;WINEDLLOVERRIDES=set:winemenubuilder.exe=d;DISPLAY=unset:;WAYLAND_DISPLAY=unset:")
    else()
        set_tests_properties(launcher_standin_version launcher_standin_unknown_option PROPERTIES DISABLED ON)
    endif()
endif()
