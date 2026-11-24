# The Windows resources of the launcher's programs: version details, the manifest (asInvoker, Windows 10), the icon,
# and for the release .exe its files (resource 100, RCDATA: launcher/windows/make_launcher_exe.py's payload).
#
#   ttt2_launcher_windows_resources(<target> NAME <internal name> FILENAME <original file name>
#                                   [DESCRIPTION <text>])
#
# TTT2_LAUNCHER_ICON (an .ico) and TTT2_LAUNCHER_PAYLOAD (the files) are given by make_launcher_exe.py. Without an
# icon one is made from launcher/app/io.github.petexy.TekkenTag2UltimateEdition.svg when rsvg-convert and Python are
# there (launcher/windows/make_icon.py); without either the program has none. Elsewhere than Windows: nothing.
include_guard(GLOBAL)
include("${CMAKE_CURRENT_LIST_DIR}/LauncherVersion.cmake")
set(TTT2_LAUNCHER_ICON "" CACHE FILEPATH "The launcher's Windows icon (.ico); made from its SVG when empty")
set(TTT2_LAUNCHER_PAYLOAD "" CACHE FILEPATH "The release .exe's files, built in as resource 100 (make_launcher_exe.py)")
get_filename_component(TTT2_LAUNCHER_RESOURCES_DIR "${CMAKE_CURRENT_LIST_DIR}/../launcher/windows" ABSOLUTE)

function(ttt2_launcher_windows_resources target)
    if(NOT WIN32)
        return()
    endif()
    cmake_parse_arguments(PARSE_ARGV 1 rc "" "NAME;FILENAME;DESCRIPTION" "")
    if(NOT rc_DESCRIPTION)
        set(rc_DESCRIPTION "Ultimate Launcher")
    endif()
    set(out "${CMAKE_CURRENT_BINARY_DIR}/${target}-resources")
    file(MAKE_DIRECTORY "${out}")
    set(icon "${TTT2_LAUNCHER_ICON}")
    set(depends)
    if(NOT icon)
        find_program(TTT2_RSVG_CONVERT rsvg-convert)
        find_package(Python3 COMPONENTS Interpreter QUIET)
        if(TTT2_RSVG_CONVERT AND Python3_Interpreter_FOUND)
            set(icon "${out}/launcher.ico")
            set(svg "${TTT2_LAUNCHER_RESOURCES_DIR}/../app/io.github.petexy.TekkenTag2UltimateEdition.svg")
            add_custom_command(OUTPUT "${icon}"
                COMMAND "${Python3_EXECUTABLE}" "${TTT2_LAUNCHER_RESOURCES_DIR}/make_icon.py"
                        --rsvg-convert "${TTT2_RSVG_CONVERT}" "${icon}"
                DEPENDS "${svg}" "${TTT2_LAUNCHER_RESOURCES_DIR}/make_icon.py"
                COMMENT "Making the launcher's Windows icon"
                VERBATIM)
            # (a source of the target, so that it is made before the resources are compiled)
            target_sources(${target} PRIVATE "${icon}")
            set_source_files_properties("${icon}" PROPERTIES HEADER_FILE_ONLY ON)
        endif()
    endif()
    string(REPLACE "." "," numbers "${TTT2_LAUNCHER_VERSION}.0")
    set(lines "")
    if(icon)
        file(TO_CMAKE_PATH "${icon}" icon)
        string(APPEND lines "1 ICON \"${icon}\"\n")
        list(APPEND depends "${icon}")
    endif()
    if(TTT2_LAUNCHER_PAYLOAD)
        file(TO_CMAKE_PATH "${TTT2_LAUNCHER_PAYLOAD}" payload)
        string(APPEND lines "100 RCDATA \"${payload}\"\n")
        list(APPEND depends "${payload}")
    endif()
    set(manifest "${TTT2_LAUNCHER_RESOURCES_DIR}/launcher.manifest")
    file(TO_CMAKE_PATH "${manifest}" manifest)
    configure_file("${TTT2_LAUNCHER_RESOURCES_DIR}/launcher.rc.in" "${out}/resources.rc" @ONLY)
    target_sources(${target} PRIVATE "${out}/resources.rc")
    set_source_files_properties("${out}/resources.rc" PROPERTIES OBJECT_DEPENDS "${depends};${manifest}")
endfunction()
