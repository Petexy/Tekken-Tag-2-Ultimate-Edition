# cmake -DCONFIG=<SDL_build_config.h> -DSYSTEM=<CMAKE_SYSTEM_NAME> -P LauncherSDLCheck.cmake
#
# Stops the launcher's static SDL build (LauncherSDL.cmake) unless SDL was configured with what the launcher needs on
# the players' PCs: its video drivers (Linux: X11 and Wayland, each loaded at run time; Windows: its own, with Direct3D
# 11 and the software renderer), the offscreen driver (screenshots, tests), joysticks with HIDAPI. A library missing
# on the build PC (X11's or Wayland's development files) otherwise only turns a driver off without a word.
if(NOT EXISTS "${CONFIG}")
    message(FATAL_ERROR "SDL's configuration ${CONFIG} is missing")
endif()
file(READ "${CONFIG}" config)

set(needed SDL_VIDEO_DRIVER_OFFSCREEN SDL_VIDEO_DRIVER_DUMMY SDL_JOYSTICK_HIDAPI SDL_JOYSTICK_VIRTUAL)
set(absent SDL_VIDEO_DISABLED SDL_RENDER_DISABLED SDL_JOYSTICK_DISABLED SDL_HIDAPI_DISABLED SDL_AUDIO_DISABLED
    SDL_THREADS_DISABLED SDL_DIALOG_DISABLED)
set(dynamic)
if(SYSTEM STREQUAL "Linux")
    list(APPEND needed SDL_VIDEO_DRIVER_X11 SDL_VIDEO_DRIVER_WAYLAND SDL_JOYSTICK_LINUX SDL_INPUT_LINUXEV
        HAVE_DBUS_DBUS_H HAVE_LIBUDEV_H)
    # (each with the library's file name, which it opens at run time: never linked)
    list(APPEND dynamic SDL_VIDEO_DRIVER_X11_DYNAMIC SDL_VIDEO_DRIVER_WAYLAND_DYNAMIC
        SDL_VIDEO_DRIVER_WAYLAND_DYNAMIC_EGL SDL_VIDEO_DRIVER_WAYLAND_DYNAMIC_CURSOR
        SDL_VIDEO_DRIVER_WAYLAND_DYNAMIC_XKBCOMMON SDL_UDEV_DYNAMIC)
elseif(SYSTEM STREQUAL "Windows")
    list(APPEND needed SDL_VIDEO_DRIVER_WINDOWS SDL_VIDEO_RENDER_D3D11 SDL_JOYSTICK_XINPUT SDL_JOYSTICK_RAWINPUT)
else()
    message(FATAL_ERROR "The launcher's SDL is not checked for ${SYSTEM}")
endif()

set(missing)
foreach(name IN LISTS needed)
    if(NOT config MATCHES "\n#define ${name} ")
        list(APPEND missing ${name})
    endif()
endforeach()
foreach(name IN LISTS dynamic)
    if(NOT config MATCHES "\n#define ${name} \"[^\"\n]+\"")
        list(APPEND missing "${name} (a library opened at run time)")
    endif()
endforeach()
foreach(name IN LISTS absent)
    if(config MATCHES "\n#define ${name} ")
        list(APPEND missing "not ${name}")
    endif()
endforeach()
if(missing)
    string(REPLACE ";" ", " missing "${missing}")
    message(FATAL_ERROR "SDL for the launcher lacks: ${missing}. Its development files are missing on this PC "
        "(Linux: X11's, Wayland's with wayland-scanner, libdecor's, D-Bus', udev's; see SDL's docs/README-linux.md); "
        "${CONFIG} has what SDL found.")
endif()
message(STATUS "SDL for the launcher has what it needs (${SYSTEM})")
