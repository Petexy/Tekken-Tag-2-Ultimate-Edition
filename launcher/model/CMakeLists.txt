# The launcher's view models and controllers, without any toolkit: what the
# window shows (plain structs with every text, id and why) and what its
# actions do (state machines driven by events and an injected clock and
# process starter). The SDL app draws them; model_test holds them to the old
# launchers' goldens (tests/golden, dumped from the GTK app).
add_library(launcher_model STATIC
    rules.cpp
    game_view.cpp
    characters_view.cpp
    settings.cpp
    task.cpp
    preflight.cpp
    self_update.cpp
    facts.cpp
    model.cpp
    golden.cpp)
target_include_directories(launcher_model PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(launcher_model PUBLIC ttt2_launcher_core)
target_compile_features(launcher_model PUBLIC cxx_std_20)
target_compile_options(launcher_model PRIVATE -Wall -Wextra -Wpedantic)
# (What it looks at on Linux itself: the PC before an install, the AppImage's files. Windows: the model only, with
# the portable core; its tests run on Linux.)
if(WIN32)
    return()
endif()
target_sources(launcher_model PRIVATE linux.cpp)
target_link_libraries(launcher_model PUBLIC ttt2_launcher_core_linux)

add_executable(launcher_model_test tests/model_test.cpp tests/replay.cpp tests/units.cpp)
target_include_directories(launcher_model_test PRIVATE tests)
target_link_libraries(launcher_model_test PRIVATE launcher_model)
target_compile_options(launcher_model_test PRIVATE -Wall -Wextra)
add_test(NAME launcher_model_test
    COMMAND launcher_model_test ${CMAKE_CURRENT_SOURCE_DIR}/tests/golden ${CMAKE_CURRENT_BINARY_DIR}/test-scratch)
set_tests_properties(launcher_model_test PROPERTIES LABELS launcher)

# The old launchers' dumps -> goldens (tests/golden/README.md).
add_executable(launcher_model_golden_convert tests/golden_convert.cpp)
target_link_libraries(launcher_model_golden_convert PRIVATE launcher_model)
