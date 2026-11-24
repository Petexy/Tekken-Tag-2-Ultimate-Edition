# TTT2_LAUNCHER_VERSION from its one place, the line "set(TTT2_LAUNCHER_VERSION X.Y.Z)" in
# launcher/builder/CMakeLists.txt (old launchers' updates read that line too). Read at each configure and kept in the
# cache too (INTERNAL), so that every directory has it, also those where launcher/builder has not set it
# (TTT2_LAUNCHER_ONLY and TOOLS_ONLY builds) and those that only call a function using it (ttt2_launcher_program).
include_guard(GLOBAL)
file(STRINGS "${CMAKE_CURRENT_LIST_DIR}/../launcher/builder/CMakeLists.txt" _ttt2_version_line
    REGEX "^set\\(TTT2_LAUNCHER_VERSION [0-9.]+\\)$")
string(REGEX REPLACE "^set\\(TTT2_LAUNCHER_VERSION ([0-9.]+)\\)$" "\\1" _ttt2_version "${_ttt2_version_line}")
if(NOT _ttt2_version)
    message(FATAL_ERROR "launcher/builder/CMakeLists.txt has no line set(TTT2_LAUNCHER_VERSION X.Y.Z)")
endif()
set(TTT2_LAUNCHER_VERSION "${_ttt2_version}" CACHE INTERNAL "The launcher's version (launcher/builder/CMakeLists.txt)"
    FORCE)
set(TTT2_LAUNCHER_VERSION "${_ttt2_version}")
unset(_ttt2_version_line)
unset(_ttt2_version)
