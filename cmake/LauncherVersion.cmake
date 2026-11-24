# TTT2_LAUNCHER_VERSION from its one place, the line "set(TTT2_LAUNCHER_VERSION X.Y.Z)" in
# launcher/builder/CMakeLists.txt (old launchers' updates read that line too), where launcher/builder has not set it
# (TTT2_LAUNCHER_ONLY and TOOLS_ONLY builds).
include_guard(GLOBAL)
if(NOT TTT2_LAUNCHER_VERSION)
    file(STRINGS "${CMAKE_CURRENT_LIST_DIR}/../launcher/builder/CMakeLists.txt" line
        REGEX "^set\\(TTT2_LAUNCHER_VERSION [0-9.]+\\)$")
    string(REGEX REPLACE "^set\\(TTT2_LAUNCHER_VERSION ([0-9.]+)\\)$" "\\1" TTT2_LAUNCHER_VERSION "${line}")
    if(NOT TTT2_LAUNCHER_VERSION)
        message(FATAL_ERROR "launcher/builder/CMakeLists.txt has no line set(TTT2_LAUNCHER_VERSION X.Y.Z)")
    endif()
    unset(line)
endif()
