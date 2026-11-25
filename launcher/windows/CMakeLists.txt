# The classic starter (entry.cpp: the .exe of releases up to 0.8.0, make_launcher_exe.py --stub: it runs main.py,
# which builds the native launcher from these files); the native launcher is launcher/app (target ttt2-launcher).
# Its version is the Linux launcher's (one release has both).
file(STRINGS ${CMAKE_SOURCE_DIR}/launcher/builder/CMakeLists.txt version_line REGEX "^set\\(TTT2_LAUNCHER_VERSION [0-9.]+\\)")
string(REGEX REPLACE "^set\\(TTT2_LAUNCHER_VERSION ([0-9.]+)\\)$" "\\1" windows_launcher_version "${version_line}")
# (Its files as launcher/core reads them: payload.h, shared with the new launcher's start.)
set(launcher_core ${CMAKE_SOURCE_DIR}/launcher/core)
add_executable(ttt2-launcher-classic WIN32 entry.cpp ${launcher_core}/payload.cpp ${launcher_core}/sha256.cpp
    ${launcher_core}/win32.cpp)
target_include_directories(ttt2-launcher-classic PRIVATE ${launcher_core})
target_compile_features(ttt2-launcher-classic PRIVATE cxx_std_20)
target_compile_definitions(ttt2-launcher-classic PRIVATE TTT2_LAUNCHER_VERSION="${windows_launcher_version}")
target_link_options(ttt2-launcher-classic PRIVATE -municode -static)
target_link_libraries(ttt2-launcher-classic PRIVATE advapi32 shell32)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME windows_launcher_backend_test COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/test_backend.py)
set_target_properties(ttt2-launcher-classic PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

add_test(NAME windows_first_run_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_setup.py)
add_test(NAME windows_launcher_update_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_self_update.py)
add_test(NAME windows_launcher_query_test COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_query.py)
# The source ZIP's way to the new launcher (main.py without --worker: build_launcher.py).
add_test(NAME windows_build_launcher_test COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/test_build_launcher.py)
# The classic starter made a release .exe: it says its version and unpacks its files (as entry.cpp reads them). (The
# native launcher's own: windows_launcher_exe_test, launcher/app.)
add_test(NAME windows_launcher_classic_exe_test COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/test_launcher_exe.py $<TARGET_FILE:ttt2-launcher-classic> ${windows_launcher_version})
# The launcher's own checks are for its developers (CI runs them): a player's
# setup leaves them out (ctest -LE launcher), as the launcher is already running.
set_tests_properties(windows_launcher_backend_test windows_first_run_test windows_launcher_update_test
    windows_launcher_query_test windows_build_launcher_test windows_launcher_classic_exe_test
    PROPERTIES LABELS launcher)
