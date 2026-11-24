# The launcher players start (later shipped as an AppImage): it builds the
# game program from the player's own .wua on their PC (builder/: ttt2-build
# and the kit it uses), installs and uninstalls the game, starts it, and adds
# Tekken 7's and Tekken 8's characters through tools/characters (app/: GTK 4;
# core/: its logic without GTK; model/: what the window shows and does,
# without any toolkit). ui/: the toolkit of its new interface on SDL 3, which
# replaces the GTK one and the Windows Tk one.
#
# With TTT2_LAUNCHER_ONLY (no game tools, no kit) only the new interface is
# built: the Windows release .exe cross-built on Linux
# (windows/make_launcher_exe.py) and the source ZIP's first start.
# (core/ and model/ build on any OS, also launcher-only and with MinGW: the new interface's logic.)
if(NOT TTT2_LAUNCHER_ONLY)
    add_subdirectory(builder)
endif()
add_subdirectory(core)
add_subdirectory(model)
add_subdirectory(backend)
if(NOT TTT2_LAUNCHER_ONLY)
    add_subdirectory(app)
endif()
add_subdirectory(ui)
# (The new launcher's stand-in in the release packaging until app/'s ttt2-launcher is the SDL program.)
add_subdirectory(standin)
add_subdirectory(appimage)

# The Windows release program, as make_launcher_exe.py makes the release .exe of it (its DEFAULT_CMAKE_TARGET; one
# line here too: launcher_standin until app/'s ttt2-launcher is the SDL program): windows/test_launcher_exe.py, its
# version and its files appended as the release has them (only in a build without TTT2_LAUNCHER_PAYLOAD: one with it
# has its files in it already). Built on Linux, through Wine when there is one (the start as a player's only with
# WINEPREFIX set to a prefix of the tests' own).
set(TTT2_LAUNCHER_RELEASE_TARGET launcher_standin)
if(WIN32 AND TARGET ${TTT2_LAUNCHER_RELEASE_TARGET} AND NOT TTT2_LAUNCHER_PAYLOAD)
    find_package(Python3 COMPONENTS Interpreter)
    if(Python3_Interpreter_FOUND)
        add_test(NAME launcher_release_exe_test
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/windows/test_launcher_exe.py
                    $<TARGET_FILE:${TTT2_LAUNCHER_RELEASE_TARGET}> ${TTT2_LAUNCHER_VERSION}
            WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/windows)
        set_tests_properties(launcher_release_exe_test PROPERTIES LABELS launcher TIMEOUT 900)
    endif()
endif()
