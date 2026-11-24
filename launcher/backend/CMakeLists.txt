# What the new launcher's model is given on each OS (ARCHITECTURE section 6): its programs run through core's
# processes (starter), and on Windows the answers of `main.py --query` (windows_backend). No SDL: tested on its own,
# Windows' answers from recorded JSON (tests/windows), on Linux too.
add_library(launcher_backend STATIC
    starter.cpp)
target_include_directories(launcher_backend PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(launcher_backend PUBLIC launcher_model)
target_compile_features(launcher_backend PUBLIC cxx_std_20)
target_compile_options(launcher_backend PRIVATE -Wall -Wextra -Wpedantic)

add_executable(launcher_backend_test tests/backend_test.cpp)
target_link_libraries(launcher_backend_test PRIVATE launcher_backend)
target_compile_options(launcher_backend_test PRIVATE -Wall -Wextra)
if(WIN32)
    target_link_options(launcher_backend_test PRIVATE -static)
endif()
add_test(NAME launcher_backend_test COMMAND launcher_backend_test ${CMAKE_CURRENT_SOURCE_DIR}/tests
    ${CMAKE_CURRENT_BINARY_DIR})
set_tests_properties(launcher_backend_test PROPERTIES LABELS launcher TIMEOUT 120)
if(CMAKE_CROSSCOMPILING AND NOT CMAKE_CROSSCOMPILING_EMULATOR)
    find_program(TTT2_WINE wine)
    if(TTT2_WINE AND WIN32)
        set_property(TARGET launcher_backend_test PROPERTY CROSSCOMPILING_EMULATOR "${TTT2_WINE}")
        set_tests_properties(launcher_backend_test PROPERTIES ENVIRONMENT_MODIFICATION
            "WINEDEBUG=set:-all;WINEDLLOVERRIDES=set:winemenubuilder.exe=d;DISPLAY=unset:;WAYLAND_DISPLAY=unset:")
    else()
        set_tests_properties(launcher_backend_test PROPERTIES DISABLED ON)
    endif()
endif()
