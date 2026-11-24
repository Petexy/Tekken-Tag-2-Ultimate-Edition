# Windows frontend is separate; Linux keeps launcher/{builder,core,app}.
# Its version is the Linux launcher's (one release has both).
file(STRINGS ${CMAKE_SOURCE_DIR}/launcher/builder/CMakeLists.txt version_line REGEX "^set\\(TTT2_LAUNCHER_VERSION [0-9.]+\\)")
string(REGEX REPLACE "^set\\(TTT2_LAUNCHER_VERSION ([0-9.]+)\\)$" "\\1" windows_launcher_version "${version_line}")
# (Its files as launcher/core reads them: payload.h, shared with the new launcher's start.)
set(launcher_core ${CMAKE_SOURCE_DIR}/launcher/core)
add_executable(ttt2-launcher WIN32 entry.cpp ${launcher_core}/payload.cpp ${launcher_core}/sha256.cpp
    ${launcher_core}/win32.cpp)
target_include_directories(ttt2-launcher PRIVATE ${launcher_core})
target_compile_features(ttt2-launcher PRIVATE cxx_std_20)
target_compile_definitions(ttt2-launcher PRIVATE TTT2_LAUNCHER_VERSION="${windows_launcher_version}")
target_link_options(ttt2-launcher PRIVATE -municode -static)
target_link_libraries(ttt2-launcher PRIVATE advapi32 shell32)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME windows_launcher_backend_test COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/test_backend.py)
set_target_properties(ttt2-launcher PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

add_test(NAME windows_first_run_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_setup.py)
add_test(NAME windows_launcher_update_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_self_update.py)
add_test(NAME windows_launcher_keys_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_keys.py)
add_test(NAME windows_launcher_query_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_query.py)
# The release .exe made of this build's launcher: it says its version and
# unpacks its files (as entry.cpp reads them).
add_test(NAME windows_launcher_exe_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_launcher_exe.py
    $<TARGET_FILE:ttt2-launcher> ${windows_launcher_version})
# The launcher's own checks are for its developers (CI runs them): a player's
# setup leaves them out (ctest -LE launcher), as the launcher is already running.
set_tests_properties(windows_launcher_backend_test windows_first_run_test windows_launcher_update_test
    windows_launcher_keys_test windows_launcher_query_test windows_launcher_exe_test PROPERTIES LABELS launcher)
