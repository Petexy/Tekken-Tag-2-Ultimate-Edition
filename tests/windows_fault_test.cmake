execute_process(COMMAND "${EXE}" --fault RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error TIMEOUT 10)
if(NOT result STREQUAL "70" OR NOT error MATCHES "guest memory fault: 0x0000F000")
    message(FATAL_ERROR "Windows guest fault reporting failed (${result}): ${output}${error}")
endif()
