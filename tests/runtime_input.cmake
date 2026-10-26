# Exercise the real runtime exports without distributing generated game code.
# Empty guest tables and hook stubs satisfy the runtime's game references.
if(CMAKE_NM)
    set(runtime_nm "${CMAKE_NM}")
else()
    find_program(runtime_nm NAMES llvm-nm nm REQUIRED)
endif()
set(stub ${CMAKE_CURRENT_BINARY_DIR}/runtime_check_stub.cpp)
add_custom_command(OUTPUT ${stub}
    COMMAND ${CMAKE_COMMAND} -DNM=${runtime_nm} -DARCHIVES=$<TARGET_FILE:ttt2_runtime>
            -DOUTPUT=${stub} -P ${CMAKE_SOURCE_DIR}/launcher/builder/kit_stub.cmake
    DEPENDS ttt2_runtime ${CMAKE_SOURCE_DIR}/launcher/builder/kit_stub.cmake VERBATIM)
add_library(runtime_check_stub OBJECT ${stub})
target_include_directories(runtime_check_stub PRIVATE ${CMAKE_SOURCE_DIR}/runtime/include)
target_compile_features(runtime_check_stub PRIVATE cxx_std_20)

add_executable(runtime_link_test ${CMAKE_SOURCE_DIR}/runtime/src/main.cpp $<TARGET_OBJECTS:runtime_check_stub>)
target_link_libraries(runtime_link_test PRIVATE cafe_runtime)
add_test(NAME runtime_cli_help COMMAND runtime_link_test --help)
