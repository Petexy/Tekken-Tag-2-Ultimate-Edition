# Tests using synthetic data only. The Linux launcher tests use fork, /proc
# and Unix permissions; they remain enabled on Linux in CMakeLists.txt.
add_executable(wua_layers_test wua_layers_test.cpp ${CMAKE_SOURCE_DIR}/runtime/src/wua.cpp)
target_include_directories(wua_layers_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/src)
target_compile_features(wua_layers_test PRIVATE cxx_std_20)
target_link_libraries(wua_layers_test PRIVATE ZArchive::zarchive)
add_test(NAME wua_layers_test COMMAND wua_layers_test)

add_executable(title_test title_test.cpp)
target_link_libraries(title_test PRIVATE cafe_title)
add_test(NAME title_test COMMAND title_test)

add_executable(memory_model_test memory_model_test.cpp)
target_include_directories(memory_model_test PRIVATE ${CMAKE_SOURCE_DIR}/runtime/include)
target_compile_features(memory_model_test PRIVATE cxx_std_20)
target_compile_options(memory_model_test PRIVATE ${TTT2_GENERATED_OPTIONS})
add_test(NAME memory_model_test COMMAND memory_model_test)

add_executable(windows_host_test windows_host_test.cpp windows_weak_alias.cpp $<TARGET_OBJECTS:runtime_check_stub>)
target_link_libraries(windows_host_test PRIVATE cafe_runtime)
add_test(NAME windows_host_test COMMAND windows_host_test ${CMAKE_CURRENT_BINARY_DIR}/windows_host_test.d)
add_test(NAME windows_fault_test COMMAND ${CMAKE_COMMAND} -DEXE=$<TARGET_FILE:windows_host_test>
    -P ${CMAKE_CURRENT_SOURCE_DIR}/windows_fault_test.cmake)

add_executable(wua_extract_test wua_extract_test.cpp)
target_link_libraries(wua_extract_test PRIVATE ZArchive::zarchive)
target_compile_features(wua_extract_test PRIVATE cxx_std_20)
add_test(NAME wua_extract_test COMMAND wua_extract_test $<TARGET_FILE:wua_extract> ${CMAKE_CURRENT_BINARY_DIR}/wua_extract_test.d)

find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
    execute_process(COMMAND "${Python3_EXECUTABLE}" -c "import numpy, PIL"
        RESULT_VARIABLE character_modules OUTPUT_QUIET ERROR_QUIET)
    if(character_modules EQUAL 0)
        foreach(pattern "test_autodump*.py" "test_memdump.py" "test_formats.py" "test_import_slots.py")
            string(REPLACE ".py" "" name "${pattern}")
            string(REPLACE "*" "" name "${name}")
            add_test(NAME character_${name}
                COMMAND "${Python3_EXECUTABLE}" -m unittest discover
                        -s "${CMAKE_SOURCE_DIR}/tools/characters/tests" -p "${pattern}")
        endforeach()
    endif()
endif()
