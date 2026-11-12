cmake_minimum_required(VERSION 3.20)
project(ttt2_recomp_tools LANGUAGES C CXX)

option(TTT2_WINDOWS_RUNTIME "Build experimental native Windows game runtime" OFF)
option(TTT2_TOOLS_ONLY "Build portable RPX/recompiler tools without the game runtime" OFF)
if(TTT2_TOOLS_ONLY)
    if(POLICY CMP0135)
        cmake_policy(SET CMP0135 NEW)
    endif()
    include(FetchContent)
    set(ZLIB_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(zlib URL https://zlib.net/fossils/zlib-1.3.1.tar.gz
        URL_HASH SHA256=9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23)
    FetchContent_MakeAvailable(zlib)
    if(NOT TARGET ZLIB::ZLIB)
        add_library(ZLIB::ZLIB ALIAS zlibstatic)
    endif()
    set(ZLIB_FOUND TRUE)
    set(ZLIB_INCLUDE_DIR "${zlib_SOURCE_DIR};${zlib_BINARY_DIR}")
    set(ZLIB_LIBRARY zlibstatic)
    set(ZSTD_BUILD_PROGRAMS OFF CACHE BOOL "" FORCE)
    set(ZSTD_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(ZSTD_BUILD_SHARED OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(zstd URL https://github.com/facebook/zstd/archive/refs/tags/v1.5.7.tar.gz
        URL_HASH SHA256=37d7284556b20954e56e1ca85b80226768902e2edabd3b649e9e72c0c9012ee3
        SOURCE_SUBDIR build/cmake)
    FetchContent_MakeAvailable(zstd)
    add_library(windows_zarchive STATIC third_party/ZArchive/src/zarchivereader.cpp
        third_party/ZArchive/src/zarchivewriter.cpp
        third_party/ZArchive/src/sha_256.c)
    target_include_directories(windows_zarchive PUBLIC third_party/ZArchive/include)
    target_compile_features(windows_zarchive PUBLIC cxx_std_20)
    target_link_libraries(windows_zarchive PRIVATE libzstd_static)
    # ZArchive's writer calls malloc and free without <cstdlib>, which newer
    # libc++ (MSYS2's CLANG64 since November 2026) no longer brings in through
    # its other headers.
    set_source_files_properties(third_party/ZArchive/src/zarchivewriter.cpp
        PROPERTIES COMPILE_OPTIONS "-include;cstdlib")
    if(WIN32)
        add_executable(wua_extract tools/wua_extract_windows.cpp)
        target_link_libraries(wua_extract PRIVATE windows_zarchive)
    endif()
    add_subdirectory(recomp)
    if(WIN32)
        file(GLOB WINDOWS_OS_SOURCES CONFIGURE_DEPENDS runtime/src/os/*.cpp)
        add_library(windows_runtime_core OBJECT ${WINDOWS_OS_SOURCES}
            runtime/src/memory.cpp runtime/src/diagnostics.cpp runtime/src/dispatch.cpp
            runtime/src/exports.cpp runtime/src/sysmem.cpp runtime/src/vfs.cpp runtime/src/wua.cpp)
        target_include_directories(windows_runtime_core PRIVATE runtime/include runtime/src recomp/src
            third_party/ZArchive/include)
        target_compile_features(windows_runtime_core PRIVATE cxx_std_20)
        target_compile_options(windows_runtime_core PRIVATE -march=x86-64-v3)
        add_executable(ttt2-play WIN32 tools/windows_launcher.cpp)
        target_compile_features(ttt2-play PRIVATE cxx_std_20)
        target_link_options(ttt2-play PRIVATE -municode -static)
        enable_testing()
        add_subdirectory(launcher/windows)
        set(SDL3_DIR "${CMAKE_SOURCE_DIR}/third_party/windows/SDL3-3.4.18/x86_64-w64-mingw32/lib/cmake/SDL3")
        find_package(SDL3 REQUIRED CONFIG)
        add_executable(windows_installer_driver tests/windows_installer_driver.cpp
            runtime/src/wua.cpp runtime/src/gpu/vulkan/png.cpp)
        target_include_directories(windows_installer_driver PRIVATE runtime/include runtime/src)
        target_compile_features(windows_installer_driver PRIVATE cxx_std_20)
        target_link_libraries(windows_installer_driver PRIVATE windows_zarchive SDL3::SDL3 bcrypt ole32 shell32 uuid)
        add_custom_command(TARGET windows_installer_driver POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_FILE:SDL3::SDL3-shared> $<TARGET_FILE_DIR:windows_installer_driver>)
        find_package(Python3 REQUIRED COMPONENTS Interpreter)
        add_test(NAME windows_installer_test COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/tests/windows_installer_test.py $<TARGET_FILE:windows_installer_driver>)

        add_executable(windows_host_smoke tests/windows_host_smoke.cpp)
        target_include_directories(windows_host_smoke PRIVATE runtime/src)
        target_compile_features(windows_host_smoke PRIVATE cxx_std_20)
        target_link_libraries(windows_host_smoke PRIVATE winpthread bcrypt)
        add_test(NAME windows_host_smoke COMMAND windows_host_smoke)
        add_executable(windows_vfs_smoke tests/windows_vfs_smoke.cpp runtime/src/vfs.cpp
            runtime/src/wua.cpp runtime/src/title/archive.cpp)
        target_include_directories(windows_vfs_smoke PRIVATE runtime/include runtime/src)
        target_compile_features(windows_vfs_smoke PRIVATE cxx_std_20)
        target_link_libraries(windows_vfs_smoke PRIVATE windows_zarchive ZLIB::ZLIB)
        add_test(NAME windows_vfs_smoke COMMAND windows_vfs_smoke)
        add_executable(windows_memory_smoke tests/windows_memory_smoke.cpp runtime/src/memory.cpp)
        target_include_directories(windows_memory_smoke PRIVATE runtime/include)
        target_compile_features(windows_memory_smoke PRIVATE cxx_std_20)
        add_test(NAME windows_memory_smoke COMMAND windows_memory_smoke)
    endif()
    if(TTT2_WINDOWS_RUNTIME)
        include(cmake/WindowsRuntime.cmake)
    endif()
    if(WIN32)
        # Every test above as one target (each is named after its program), so
        # the setup scripts build all that ctest runs: none is left "Not Run".
        add_custom_target(windows_checks)
        get_property(windows_tests DIRECTORY PROPERTY TESTS)
        foreach(windows_test IN LISTS windows_tests)
            if(TARGET ${windows_test})
                add_dependencies(windows_checks ${windows_test})
            endif()
        endforeach()
    endif()
    return()
endif()

if(NOT UNIX)
    message(FATAL_ERROR "The safe extraction utility currently requires a POSIX host.")
endif()

add_subdirectory(third_party/ZArchive EXCLUDE_FROM_ALL)

# AMD's surface address library (MIT), in its R600 variant for the Wii U GPU:
# GX2 surface layouts must match the console's exactly.
set(ADDRLIB_DIR ${CMAKE_SOURCE_DIR}/third_party/addrlib)
add_library(amd_addrlib STATIC EXCLUDE_FROM_ALL
    ${ADDRLIB_DIR}/src/addrinterface.cpp
    ${ADDRLIB_DIR}/src/core/addrelemlib.cpp
    ${ADDRLIB_DIR}/src/core/addrlib.cpp
    ${ADDRLIB_DIR}/src/core/addrobject.cpp
    ${ADDRLIB_DIR}/src/r600/r600addrlib.cpp)
target_include_directories(amd_addrlib SYSTEM PUBLIC ${ADDRLIB_DIR}/include)
target_include_directories(amd_addrlib PRIVATE ${ADDRLIB_DIR}/src)
target_compile_features(amd_addrlib PRIVATE cxx_std_17)
target_compile_options(amd_addrlib PRIVATE -w)

add_executable(wua_extract tools/wua_extract.cpp)
target_compile_features(wua_extract PRIVATE cxx_std_20)
target_link_libraries(wua_extract PRIVATE ZArchive::zarchive)
target_compile_options(wua_extract PRIVATE -Wall -Wextra -Wpedantic)

# Function-level PowerPC -> C++ recompiler for the standalone port.
add_subdirectory(recomp)
add_subdirectory(runtime)
enable_testing()
add_subdirectory(tests)

# How the generated code is compiled, here and by the launcher's kit on the
# players' PCs (launcher/builder). Translated code is huge and flat: -O2
# compiles far faster than -O3 for the same result. FMA is required for exact
# fused multiply-add.
set(TTT2_GENERATED_OPTIONS -O2 -march=x86-64-v3 -fno-exceptions -Wno-unused-label)

# The port itself: runtime + code generated by cafe-recomp. Point
# TTT2_GENERATED_DIR at a cafe-recomp output directory to build it.
set(TTT2_GENERATED_DIR "" CACHE PATH "cafe-recomp output directory")
if(TTT2_GENERATED_DIR)
    include(${TTT2_GENERATED_DIR}/sources.cmake)
    add_library(ttt2_generated OBJECT ${CAFE_GENERATED_SOURCES})
    target_include_directories(ttt2_generated PRIVATE runtime/include)
    target_compile_features(ttt2_generated PRIVATE cxx_std_20)
    target_compile_options(ttt2_generated PRIVATE ${TTT2_GENERATED_OPTIONS})

    add_executable(ttt2 runtime/src/main.cpp)
    target_link_libraries(ttt2 PRIVATE cafe_runtime ttt2_generated)
    target_compile_options(ttt2 PRIVATE -Wall -Wextra -Wpedantic)
endif()

# The players' launcher (launcher/): builds the game program on the player's
# PC from their .wua, installs it and adds Tekken 7's characters.
add_subdirectory(launcher)
