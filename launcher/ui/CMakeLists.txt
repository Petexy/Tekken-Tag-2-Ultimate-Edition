# The launcher's new interface toolkit on SDL 3 (drawing, text, icons; it knows nothing of the launcher), the libraries
# and fonts it is made with, and launcher_smoke: a small program linked as the launcher will be, which draws a frame
# with each of them (tests: --screenshot with SDL's offscreen driver).
#
# SDL comes from cmake/LauncherSDL.cmake (TTT2_LAUNCHER_SDL: the system's, or third_party/SDL built in statically for
# the release programs); without any, this folder is left out.
include("${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/LauncherSDL.cmake")
if(TTT2_LAUNCHER_SDL_MODE STREQUAL "none")
    return()
endif()
include("${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/EmbedFiles.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/LauncherVersion.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/LauncherResources.cmake")

# The single-header libraries (third_party/README.md), compiled once, as they are.
add_library(ttt2_launcher_vendor STATIC third_party.c)
target_include_directories(ttt2_launcher_vendor SYSTEM PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/third_party")
target_compile_options(ttt2_launcher_vendor PRIVATE -w)
target_compile_definitions(ttt2_launcher_vendor PUBLIC $<$<PLATFORM_ID:Windows>:STBIW_WINDOWS_UTF8>)
target_link_libraries(ttt2_launcher_vendor PRIVATE ttt2_launcher_glibc_floor)
if(NOT WIN32)
    target_link_libraries(ttt2_launcher_vendor PUBLIC m)
endif()

# The fonts (fonts/README.md), built into the program: ttt2_fonts::find("BarlowCondensed/...ttf").
set(TTT2_LAUNCHER_FONTS
    BarlowCondensed/BarlowCondensed-SemiBold.ttf
    BarlowCondensed/BarlowCondensed-Bold.ttf
    BarlowCondensed/BarlowCondensed-BoldItalic.ttf
    BarlowCondensed/BarlowCondensed-ExtraBold.ttf
    BarlowCondensed/BarlowCondensed-ExtraBoldItalic.ttf
    BarlowCondensed/BarlowCondensed-Black.ttf
    BarlowCondensed/BarlowCondensed-BlackItalic.ttf
    Barlow/Barlow-Regular.ttf
    Barlow/Barlow-Medium.ttf
    Barlow/Barlow-SemiBold.ttf
    Barlow/Barlow-Bold.ttf
    JetBrainsMono/JetBrainsMono-Regular.ttf
    JetBrainsMono/JetBrainsMono-Bold.ttf)
list(TRANSFORM TTT2_LAUNCHER_FONTS PREPEND "${CMAKE_CURRENT_SOURCE_DIR}/fonts/")
ttt2_embed_files(ttt2_launcher_fonts NAMESPACE ttt2_fonts BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/fonts"
    FILES ${TTT2_LAUNCHER_FONTS})

# The launcher's icons (launcher/app: its own and icons/*.svg, original drawings), likewise:
# ttt2_icons::find("icons/ttt2-input-face_bottom.svg").
get_filename_component(app_dir "${CMAKE_CURRENT_SOURCE_DIR}/../app" ABSOLUTE)
file(GLOB TTT2_LAUNCHER_ICONS CONFIGURE_DEPENDS "${app_dir}/icons/*.svg")
list(SORT TTT2_LAUNCHER_ICONS)
ttt2_embed_files(ttt2_launcher_icons NAMESPACE ttt2_icons BASE_DIR "${app_dir}"
    FILES "${app_dir}/io.github.petexy.TekkenTag2UltimateEdition.svg" ${TTT2_LAUNCHER_ICONS})

# How every program of the new interface is linked (ttt2_launcher_program(<target>)): SDL, the libraries above, the
# fonts and icons; warnings; on Windows a GUI program with a wide-character entry (wWinMain), static C++ runtime,
# no time stamp in the file (the same sources make the same .exe), its resources (cmake/LauncherResources.cmake)
# and, with the system's SDL, SDL3.dll beside it.
function(ttt2_launcher_program target)
    cmake_parse_arguments(PARSE_ARGV 1 program "" "NAME;FILENAME;DESCRIPTION" "")
    target_link_libraries(${target} PRIVATE ttt2_launcher_sdl ttt2_launcher_vendor ttt2_launcher_fonts
        ttt2_launcher_icons)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_options(${target} PRIVATE $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra -Wpedantic>)
    target_compile_definitions(${target} PRIVATE TTT2_LAUNCHER_VERSION="${TTT2_LAUNCHER_VERSION}"
        TTT2_LAUNCHER_APP_ID="io.github.petexy.TekkenTag2UltimateEdition")
    set_target_properties(${target} PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/launcher")
    if(WIN32)
        set_target_properties(${target} PROPERTIES WIN32_EXECUTABLE ON)
        target_link_options(${target} PRIVATE -municode -static "LINKER:--no-insert-timestamp")
        ttt2_launcher_windows_resources(${target} NAME "${program_NAME}" FILENAME "${program_FILENAME}"
            DESCRIPTION "${program_DESCRIPTION}")
        ttt2_launcher_sdl_runtime(${target})
    endif()
endfunction()

add_executable(launcher_smoke smoke/smoke.cpp)
ttt2_launcher_program(launcher_smoke NAME launcher_smoke FILENAME launcher_smoke.exe
    DESCRIPTION "Ultimate Launcher (smoke test)")

# Its checks: --version without SDL, and a frame drawn offscreen with the software renderer, which it checks itself
# (text, icon and shape where they belong, anti-aliased edges) before writing it as a PNG.
add_test(NAME launcher_smoke_version COMMAND launcher_smoke --version)
set_tests_properties(launcher_smoke_version PROPERTIES
    PASS_REGULAR_EXPRESSION "^launcher_smoke ${TTT2_LAUNCHER_VERSION}\n$")
add_test(NAME launcher_smoke_screenshot
    COMMAND launcher_smoke --screenshot "${CMAKE_CURRENT_BINARY_DIR}/launcher_smoke.png")
set_tests_properties(launcher_smoke_version launcher_smoke_screenshot PROPERTIES LABELS launcher)
if(CMAKE_CROSSCOMPILING AND NOT CMAKE_CROSSCOMPILING_EMULATOR)
    # (A Windows program built on Linux: run through Wine when it is there, else not at all.)
    find_program(TTT2_WINE wine)
    if(TTT2_WINE AND WIN32)
        set_property(TARGET launcher_smoke PROPERTY CROSSCOMPILING_EMULATOR "${TTT2_WINE}")
        # (never on this PC's screen: no display for Wine; the frame is drawn offscreen anyway)
        set_tests_properties(launcher_smoke_version launcher_smoke_screenshot PROPERTIES
            ENVIRONMENT_MODIFICATION "WINEDEBUG=set:-all;DISPLAY=unset:;WAYLAND_DISPLAY=unset:")
    else()
        set_tests_properties(launcher_smoke_version launcher_smoke_screenshot PROPERTIES DISABLED ON)
    endif()
endif()
