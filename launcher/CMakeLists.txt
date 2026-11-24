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
add_subdirectory(appimage)
