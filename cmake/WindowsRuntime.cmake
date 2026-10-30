# Included after portable dependencies and recomp/ have been configured.
set(SDL3_DIR "${CMAKE_SOURCE_DIR}/third_party/windows/SDL3-3.4.18/x86_64-w64-mingw32/lib/cmake/SDL3")
set(Vulkan_INCLUDE_DIR "${CMAKE_SOURCE_DIR}/third_party/Vulkan-Headers/include" CACHE PATH "" FORCE)
set(Vulkan_LIBRARY "${CMAKE_SOURCE_DIR}/third_party/windows/libvulkan-1.dll.a" CACHE FILEPATH "" FORCE)
set(SHADERC_LIBRARY "${CMAKE_SOURCE_DIR}/build-windows-shaderc/libshaderc/libshaderc_shared.dll.a")
add_library(ZArchive::zarchive ALIAS windows_zarchive)
set(ADDRLIB_DIR "${CMAKE_SOURCE_DIR}/third_party/addrlib")
add_library(amd_addrlib STATIC
    ${ADDRLIB_DIR}/src/addrinterface.cpp ${ADDRLIB_DIR}/src/core/addrelemlib.cpp
    ${ADDRLIB_DIR}/src/core/addrlib.cpp ${ADDRLIB_DIR}/src/core/addrobject.cpp
    ${ADDRLIB_DIR}/src/r600/r600addrlib.cpp)
target_include_directories(amd_addrlib SYSTEM PUBLIC ${ADDRLIB_DIR}/include)
target_include_directories(amd_addrlib PRIVATE ${ADDRLIB_DIR}/src)
target_compile_features(amd_addrlib PRIVATE cxx_std_17)
target_compile_options(amd_addrlib PRIVATE -w)
add_subdirectory(runtime)
set(TTT2_GENERATED_DIR "${CMAKE_SOURCE_DIR}/generated/ttt2-windows")
include(${TTT2_GENERATED_DIR}/sources.cmake)
add_library(ttt2_windows_generated OBJECT ${CAFE_GENERATED_SOURCES})
target_include_directories(ttt2_windows_generated PRIVATE runtime/include)
target_compile_features(ttt2_windows_generated PRIVATE cxx_std_20)
target_compile_options(ttt2_windows_generated PRIVATE -O2 -march=x86-64-v3 -fno-exceptions -Wno-unused-label)
add_executable(ttt2-ultimate runtime/src/main.cpp)
target_link_libraries(ttt2-ultimate PRIVATE cafe_runtime ttt2_windows_generated)
# Portable development build: carry its native DLL dependencies beside it.
add_custom_command(TARGET ttt2-ultimate POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_SOURCE_DIR}/third_party/windows/SDL3-3.4.18/x86_64-w64-mingw32/bin/SDL3.dll"
        "${CMAKE_SOURCE_DIR}/build-windows-shaderc/libshaderc/libshaderc_shared.dll"
        "$<TARGET_FILE_DIR:ttt2-ultimate>")

get_filename_component(TTT2_COMPILER_BIN "${CMAKE_CXX_COMPILER}" DIRECTORY)
add_custom_command(TARGET ttt2-ultimate POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${TTT2_COMPILER_BIN}/libc++.dll" "${TTT2_COMPILER_BIN}/libunwind.dll"
        "${TTT2_COMPILER_BIN}/libwinpthread-1.dll" "$<TARGET_FILE_DIR:ttt2-ultimate>")

# Gameplay regression tests from the merged branch, built natively.
foreach(game_test damage_scaling_test outfit_menu_test eliza_assist_test noctis_assault_test practice_checkpoint_test memory_model_test)
    add_executable(${game_test} tests/${game_test}.cpp)
    target_include_directories(${game_test} PRIVATE runtime/src runtime/include)
    target_compile_features(${game_test} PRIVATE cxx_std_20)
    target_compile_options(${game_test} PRIVATE -UNDEBUG -march=x86-64-v3)
    add_test(NAME ${game_test} COMMAND ${game_test})
endforeach()
add_executable(title_test tests/title_test.cpp)
target_link_libraries(title_test PRIVATE cafe_title)
target_compile_options(title_test PRIVATE -UNDEBUG)
add_test(NAME title_test COMMAND title_test)
add_executable(wua_layers_test tests/wua_layers_test.cpp runtime/src/wua.cpp)
target_include_directories(wua_layers_test PRIVATE runtime/src)
target_compile_features(wua_layers_test PRIVATE cxx_std_20)
target_link_libraries(wua_layers_test PRIVATE windows_zarchive)
add_test(NAME wua_layers_test COMMAND wua_layers_test)

foreach(input_check input_test game_input_test)
    add_executable(${input_check} tests/${input_check}.cpp)
    target_link_libraries(${input_check} PRIVATE cafe_runtime ttt2_windows_generated)
endforeach()
add_test(NAME input_test COMMAND input_test)
set(TTT2_WINDOWS_TEST_RPX "${CMAKE_SOURCE_DIR}/local/wua-windows/0000000000000000_v0/code/Tekken.rpx" CACHE FILEPATH "RPX used by native gameplay input regression")
add_test(NAME game_input_test COMMAND game_input_test "${TTT2_WINDOWS_TEST_RPX}")
