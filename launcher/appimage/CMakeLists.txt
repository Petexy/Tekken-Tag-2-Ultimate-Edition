# The checks a Linux release program must pass (release_checks.sh, which make_appimage.sh runs on the AppImage),
# tested on programs made for each fault; and run on launcher_smoke when this build links SDL in as a release does.
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    return()
endif()
find_program(TTT2_BASH bash)
if(NOT TTT2_BASH)
    return()
endif()
add_test(NAME launcher_release_checks_test
    COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/test_release_checks.sh ${CMAKE_C_COMPILER} ${CMAKE_CXX_COMPILER}
            "${TTT2_GLIBC_FLOOR_HEADER}")
set_tests_properties(launcher_release_checks_test PROPERTIES LABELS launcher)
# (GNU ld marks programs with the ISA level of the system's startup files, x86-64-v4 on some: as make_appimage.sh,
# link with LLD there, -DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld.)
if(TTT2_LAUNCHER_SDL_MODE STREQUAL "static" AND TARGET launcher_smoke)
    add_test(NAME launcher_smoke_release_checks
        COMMAND ${TTT2_BASH} ${CMAKE_CURRENT_SOURCE_DIR}/release_checks.sh --launcher $<TARGET_FILE:launcher_smoke>)
    set_tests_properties(launcher_smoke_release_checks PROPERTIES LABELS launcher)
endif()
