# Cross-building for 64-bit Windows on Linux with MinGW-w64 (GCC: x86_64-w64-mingw32-gcc, Arch's mingw-w64-gcc;
# or llvm-mingw's clang with -DTTT2_MINGW_PREFIX=... and -DCMAKE_C_COMPILER=...-clang):
#
#   cmake -S . -B build-win -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-mingw64.cmake -DTTT2_LAUNCHER_ONLY=ON ...
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
if(NOT TTT2_MINGW_PREFIX)
    set(TTT2_MINGW_PREFIX x86_64-w64-mingw32)
endif()
set(TTT2_MINGW_PREFIX "${TTT2_MINGW_PREFIX}" CACHE STRING "MinGW-w64 tool prefix (x86_64-w64-mingw32)")
if(NOT CMAKE_C_COMPILER)
    set(CMAKE_C_COMPILER ${TTT2_MINGW_PREFIX}-gcc)
endif()
if(NOT CMAKE_CXX_COMPILER)
    set(CMAKE_CXX_COMPILER ${TTT2_MINGW_PREFIX}-g++)
endif()
if(NOT CMAKE_RC_COMPILER)
    find_program(CMAKE_RC_COMPILER NAMES ${TTT2_MINGW_PREFIX}-windres llvm-windres windres)
endif()
# Libraries and headers only from the MinGW-w64 tree (and the folders given to find_package), programs from this PC.
set(CMAKE_FIND_ROOT_PATH /usr/${TTT2_MINGW_PREFIX})
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
