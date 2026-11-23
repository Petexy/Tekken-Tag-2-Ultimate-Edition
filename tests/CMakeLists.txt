# Differential semantics test: generated code vs Dolphin's interpreter.
# Needs the Dolphin reference checkout (third_party/ref/dolphin) and the game
# executable (TTT2_RPX), which supplies the instruction encodings under test.
set(TTT2_RPX "${CMAKE_SOURCE_DIR}/local/wua/000500001010f800_v16/code/Tekken.rpx"
    CACHE FILEPATH "Tekken.rpx used to sample test encodings")
set(DOLPHIN_CORE "${CMAKE_SOURCE_DIR}/third_party/ref/dolphin/Source/Core")
find_package(fmt QUIET)

if(EXISTS "${DOLPHIN_CORE}/Core/PowerPC/Interpreter/Interpreter_Tables.cpp"
   AND EXISTS "${TTT2_RPX}" AND fmt_FOUND)
    # Dolphin's Interpreter.h minus the emulator core interface, derived at
    # configure time so no Dolphin source is copied into this tree.
    file(READ "${DOLPHIN_CORE}/Core/PowerPC/Interpreter/Interpreter.h" interpreter_h)
    string(REPLACE " : public CPUCoreBase" "" interpreter_h "${interpreter_h}")
    string(REPLACE " override;" ";" interpreter_h "${interpreter_h}")
    string(REPLACE "private:" "public:" interpreter_h "${interpreter_h}")
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/oracle_shim/Core/PowerPC/Interpreter/Interpreter.h"
        "${interpreter_h}")
    # Likewise PowerPC.h's register state and access macros, without the
    # core manager and the debugger (oracle/PowerPC.h.in).
    file(READ "${DOLPHIN_CORE}/Core/PowerPC/PowerPC.h" powerpc_h)
    string(FIND "${powerpc_h}" "// TLB cache" state_begin)
    string(FIND "${powerpc_h}" "#ifdef _M_X86_64\n#ifdef __GNUC__" state_end)
    string(FIND "${powerpc_h}" "// Easy register access macros." macros_begin)
    string(FIND "${powerpc_h}" "void RoundingModeUpdated" macros_end)
    foreach(position state_begin state_end macros_begin macros_end)
        if(${position} LESS 0)
            message(FATAL_ERROR "semantics_test: Dolphin's PowerPC.h has changed (${position} not found)")
        endif()
    endforeach()
    math(EXPR state_length "${state_end} - ${state_begin}")
    math(EXPR macros_length "${macros_end} - ${macros_begin}")
    string(SUBSTRING "${powerpc_h}" ${state_begin} ${state_length} powerpc_state)
    string(SUBSTRING "${powerpc_h}" ${macros_begin} ${macros_length} powerpc_macros)
    string(REPLACE "InstructionCache iCache;" "NoopCache iCache;" powerpc_state "${powerpc_state}")
    string(REPLACE "Cache dCache;" "NoopCache dCache;" powerpc_state "${powerpc_state}")
    configure_file(oracle/PowerPC.h.in "${CMAKE_CURRENT_BINARY_DIR}/oracle_shim/Core/PowerPC/PowerPC.h" @ONLY)

    set(interp "${DOLPHIN_CORE}/Core/PowerPC/Interpreter")
    add_library(dolphin_oracle STATIC
        oracle/oracle.cpp
        ${interp}/Interpreter_Tables.cpp
        ${interp}/Interpreter_Integer.cpp
        ${interp}/Interpreter_LoadStore.cpp
        ${interp}/Interpreter_FloatingPoint.cpp
        ${interp}/Interpreter_Paired.cpp
        ${interp}/Interpreter_LoadStorePaired.cpp
        ${interp}/Interpreter_SystemRegisters.cpp
        ${interp}/Interpreter_Branch.cpp
        ${DOLPHIN_CORE}/Core/PowerPC/ConditionRegister.cpp
        ${DOLPHIN_CORE}/Common/FloatUtils.cpp)
    target_include_directories(dolphin_oracle PRIVATE
        "${CMAKE_CURRENT_BINARY_DIR}/oracle_shim" oracle/shim "${DOLPHIN_CORE}")
    target_compile_features(dolphin_oracle PRIVATE cxx_std_23)
    target_compile_options(dolphin_oracle PRIVATE -w)
    target_link_libraries(dolphin_oracle PRIVATE fmt::fmt)

    set(semantics_cases "${CMAKE_CURRENT_BINARY_DIR}/semantics_cases.cpp")
    add_custom_command(OUTPUT "${semantics_cases}"
        COMMAND cafe-semgen "${TTT2_RPX}" "${semantics_cases}" 48
        DEPENDS cafe-semgen
        COMMENT "Sampling instruction encodings from Tekken.rpx"
        VERBATIM)
    add_executable(semantics_test oracle/semantics_test.cpp "${semantics_cases}")
    target_include_directories(semantics_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/include)
    target_link_libraries(semantics_test PRIVATE dolphin_oracle cafe_recomp)
    target_compile_features(semantics_test PRIVATE cxx_std_20)
    target_compile_options(semantics_test PRIVATE -O2 -march=x86-64-v3 -Wno-unused-label)
    add_test(NAME semantics_test COMMAND semantics_test)

    add_executable(cafe-cfgen oracle/cfgen_main.cpp)
    target_link_libraries(cafe-cfgen PRIVATE cafe_recomp)
    set(control_flow_cases "${CMAKE_CURRENT_BINARY_DIR}/control_flow_cases.cpp")
    add_custom_command(OUTPUT "${control_flow_cases}"
        COMMAND cafe-cfgen "${control_flow_cases}"
        DEPENDS cafe-cfgen
        COMMENT "Assembling control-flow test programs"
        VERBATIM)
    add_executable(control_flow_test oracle/control_flow_test.cpp "${control_flow_cases}")
    target_include_directories(control_flow_test PRIVATE
        ${CMAKE_SOURCE_DIR}/runtime/include ${CMAKE_CURRENT_SOURCE_DIR}/oracle)
    target_link_libraries(control_flow_test PRIVATE dolphin_oracle)
    target_compile_features(control_flow_test PRIVATE cxx_std_20)
    target_compile_options(control_flow_test PRIVATE -O2 -march=x86-64-v3 -Wno-unused-label)
    add_test(NAME control_flow_test COMMAND control_flow_test)
else()
    message(STATUS "semantics_test disabled: needs third_party/ref/dolphin, fmt and TTT2_RPX")
endif()

# The game's files from a .wua whose update is merged or beside the base
# game (synthetic archives; no game data needed).
add_executable(wua_layers_test wua_layers_test.cpp ${CMAKE_SOURCE_DIR}/runtime/src/wua.cpp)
target_include_directories(wua_layers_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(wua_layers_test PRIVATE cxx_std_20)
target_link_libraries(wua_layers_test PRIVATE ZArchive::zarchive)
add_test(NAME wua_layers_test COMMAND wua_layers_test)

# The title's file formats, icons and texts (synthetic data; no game files).
add_executable(title_test title_test.cpp)
target_link_libraries(title_test PRIVATE cafe_title)
target_compile_options(title_test PRIVATE -Wall -Wextra)
add_test(NAME title_test COMMAND title_test)

# The GamePad's touch screen on a computer: window points as points of the
# picture (letterboxing, scale), the stick's cursor (host/touch_screen.h).
add_executable(touch_screen_test touch_screen_test.cpp)
target_include_directories(touch_screen_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(touch_screen_test PRIVATE cxx_std_20)
target_compile_options(touch_screen_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME touch_screen_test COMMAND touch_screen_test)

# Exported Cafe OS functions' arguments past r10 come from the caller's stack (cafe/export.h).
add_executable(export_abi_test export_abi_test.cpp)
target_include_directories(export_abi_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/include)
target_compile_features(export_abi_test PRIVATE cxx_std_20)
target_compile_options(export_abi_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME export_abi_test COMMAND export_abi_test)

add_executable(damage_scaling_test damage_scaling_test.cpp)
target_include_directories(damage_scaling_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_options(damage_scaling_test PRIVATE -Wall -Wextra)
add_test(NAME damage_scaling_test COMMAND damage_scaling_test)

# The keyboard's keys from keyboard.ini and its reloading (files in a
# scratch folder of the build tree; SDL only for its key names).
find_package(SDL3 REQUIRED CONFIG)
add_executable(keymap_test keymap_test.cpp ${CMAKE_SOURCE_DIR}/runtime/src/host/keymap.cpp)
target_include_directories(keymap_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src ${CMAKE_SOURCE_DIR}/runtime/include)
target_compile_features(keymap_test PRIVATE cxx_std_20)
target_link_libraries(keymap_test PRIVATE SDL3::SDL3)
target_compile_options(keymap_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME keymap_test COMMAND keymap_test ${CMAKE_CURRENT_BINARY_DIR}/keymap_test.d)

# keyboard.ini as the launcher writes it, read by the game's parser: their
# inputs, defaults and reserved keys stay the same.
add_executable(keyboard_file_test keyboard_file_test.cpp ${CMAKE_SOURCE_DIR}/runtime/src/host/keymap.cpp)
target_include_directories(keyboard_file_test PRIVATE
    ${CMAKE_SOURCE_DIR}/runtime/src ${CMAKE_SOURCE_DIR}/runtime/include)
target_link_libraries(keyboard_file_test PRIVATE ttt2_launcher_core SDL3::SDL3)
target_compile_options(keyboard_file_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME keyboard_file_test COMMAND keyboard_file_test)

# The display settings from display.ini, the environment over them and the
# window's size (files in a scratch folder of the build tree; no SDL).
add_executable(display_settings_test display_settings_test.cpp
    ${CMAKE_SOURCE_DIR}/runtime/src/host/display_settings.cpp)
target_include_directories(display_settings_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(display_settings_test PRIVATE cxx_std_20)
target_compile_options(display_settings_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME display_settings_test
    COMMAND display_settings_test ${CMAKE_CURRENT_BINARY_DIR}/display_settings_test.d)

# Guest polling loops must see other threads' stores (no Dolphin needed).
add_executable(memory_model_test memory_model_test.cpp)
target_include_directories(memory_model_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/include)
target_compile_features(memory_model_test PRIVATE cxx_std_20)
# The flags the port compiles generated code with.
target_compile_options(memory_model_test PRIVATE -O2 -march=x86-64-v3 -Wno-unused-label)
add_test(NAME memory_model_test COMMAND memory_model_test)

# The thread keeping the memory the GPU reads on huge pages leaves its
# contents alone (Linux: the memory module's own program, six seconds).
if(NOT WIN32)
    add_executable(guest_memory_keeper_test guest_memory_keeper_test.cpp
        ${CMAKE_SOURCE_DIR}/runtime/src/memory.cpp)
    target_include_directories(guest_memory_keeper_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/include)
    target_compile_features(guest_memory_keeper_test PRIVATE cxx_std_20)
    target_compile_options(guest_memory_keeper_test PRIVATE -O2 -Wall -Wextra -Wpedantic)
    find_package(Threads REQUIRED)
    target_link_libraries(guest_memory_keeper_test PRIVATE Threads::Threads)
    add_test(NAME guest_memory_keeper_test COMMAND guest_memory_keeper_test)
endif()

# Its rule (which blocks it asks the kernel for, how long it waits, what it
# tells the log) on made-up answers: no kernel needed.
add_executable(memory_keeper_test memory_keeper_test.cpp)
target_include_directories(memory_keeper_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(memory_keeper_test PRIVATE cxx_std_20)
target_compile_options(memory_keeper_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME memory_keeper_test COMMAND memory_keeper_test)

# The character importer's formats (tools/characters; synthetic data, no game
# files). Needs Python 3 with numpy and Pillow.
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
    execute_process(COMMAND "${Python3_EXECUTABLE}" -c "import numpy, PIL"
        RESULT_VARIABLE character_import_modules OUTPUT_QUIET ERROR_QUIET)
    if(character_import_modules EQUAL 0)
        add_test(NAME character_import_test
            COMMAND "${Python3_EXECUTABLE}" -m unittest discover -s "${CMAKE_SOURCE_DIR}/tools/characters/tests")
    else()
        message(STATUS "character_import_test disabled: needs Python 3 with numpy and Pillow")
    endif()
endif()

# Outfit namespace validation and loader/menu state transitions, without game assets.
add_executable(outfit_menu_test outfit_menu_test.cpp)
target_include_directories(outfit_menu_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(outfit_menu_test PRIVATE cxx_std_20)
target_compile_options(outfit_menu_test PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME outfit_menu_test COMMAND outfit_menu_test)

# Which draws may be left out while their shader is made in the background (gpu/vulkan/leave_out.h).
add_executable(leave_out_test leave_out_test.cpp)
target_include_directories(leave_out_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(leave_out_test PRIVATE cxx_std_20)
target_compile_options(leave_out_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME leave_out_test COMMAND leave_out_test)

# Eliza's scoped native Tag Assault lifetime; no game assets required.
add_executable(eliza_assist_test eliza_assist_test.cpp)
target_include_directories(eliza_assist_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(eliza_assist_test PRIVATE cxx_std_20)
target_compile_options(eliza_assist_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME eliza_assist_test COMMAND eliza_assist_test)

add_executable(noctis_assault_test noctis_assault_test.cpp)
target_include_directories(noctis_assault_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(noctis_assault_test PRIVATE cxx_std_20)
target_compile_options(noctis_assault_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME noctis_assault_test COMMAND noctis_assault_test)

# The select grid's rings and the '?' two rows share; made-up grids.
add_executable(select_grid_test select_grid_test.cpp)
target_include_directories(select_grid_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(select_grid_test PRIVATE cxx_std_20)
target_compile_options(select_grid_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME select_grid_test COMMAND select_grid_test)

# Meshes the motion blur leaves out (title/unblurred.h); a made-up NUD.
add_executable(unblurred_test unblurred_test.cpp)
target_include_directories(unblurred_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(unblurred_test PRIVATE cxx_std_20)
target_compile_options(unblurred_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME unblurred_test COMMAND unblurred_test)

# Fades of a Tekken 8 fighter's summoned weapons (title/summon_fade.h); made-up values.
add_executable(summon_fade_test summon_fade_test.cpp)
target_include_directories(summon_fade_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(summon_fade_test PRIVATE cxx_std_20)
target_compile_options(summon_fade_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME summon_fade_test COMMAND summon_fade_test)

# The developer's customization record (title/test_record.h); made-up items and colours.
add_executable(test_record_test test_record_test.cpp)
target_include_directories(test_record_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(test_record_test PRIVATE cxx_std_20)
target_compile_options(test_record_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME test_record_test COMMAND test_record_test)

# An added fighter's saved customizations (title/customize_store.h): the port's own file per fighter code.
add_executable(customize_store_test customize_store_test.cpp)
target_include_directories(customize_store_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(customize_store_test PRIVATE cxx_std_20)
target_compile_options(customize_store_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME customize_store_test COMMAND customize_store_test)

# CUSTOMIZE mode's character grid with the added fighters' cells (title/customize_grid.h); a made-up script.
add_executable(customize_grid_test customize_grid_test.cpp)
target_include_directories(customize_grid_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(customize_grid_test PRIVATE cxx_std_20)
target_compile_options(customize_grid_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME customize_grid_test COMMAND customize_grid_test)

add_executable(win_pose_test win_pose_test.cpp)
target_include_directories(win_pose_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(win_pose_test PRIVATE cxx_std_20)
target_compile_options(win_pose_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME win_pose_test COMMAND win_pose_test)

add_executable(win_shot_test win_shot_test.cpp)
target_include_directories(win_shot_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(win_shot_test PRIVATE cxx_std_20)
target_compile_options(win_shot_test PRIVATE -UNDEBUG -Wall -Wextra)
add_test(NAME win_shot_test COMMAND win_shot_test)
