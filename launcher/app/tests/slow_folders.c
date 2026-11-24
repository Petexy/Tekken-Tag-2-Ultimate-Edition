// LD_PRELOAD for tests/picker.sh: opening a folder whose path contains "/slow" (opendir, or open/openat with
// O_DIRECTORY, as libstdc++'s directory_iterator does, fortified or not) takes SLOW_MS milliseconds (default 2000),
// as a sleeping disk or a slow network share does. Everything else is as usual.
#define _GNU_SOURCE
#include <dirent.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static void slow(const char* name) {
    if (!name || !strstr(name, "/slow")) return;
    const char* ms = getenv("SLOW_MS");
    const long m = ms ? atol(ms) : 2000;
    struct timespec t = {m / 1000, (m % 1000) * 1000000L};
    while (nanosleep(&t, &t) != 0) {
    }
}

DIR* opendir(const char* name) {
    static DIR* (*real)(const char*) = 0;
    if (!real) real = (DIR * (*)(const char*)) dlsym(RTLD_NEXT, "opendir");
    slow(name);
    return real(name);
}

#define OPENAT(fn)                                                                                                    \
    int fn(int dir, const char* name, int flags, ...) {                                                               \
        static int (*real)(int, const char*, int, ...) = 0;                                                           \
        if (!real) real = (int (*)(int, const char*, int, ...))dlsym(RTLD_NEXT, #fn);                                 \
        va_list ap;                                                                                                   \
        va_start(ap, flags);                                                                                          \
        const int mode = (flags & (O_CREAT | O_TMPFILE)) ? va_arg(ap, int) : 0;                                       \
        va_end(ap);                                                                                                   \
        if (flags & O_DIRECTORY) slow(name);                                                                          \
        return real(dir, name, flags, mode);                                                                          \
    }
OPENAT(openat)
OPENAT(openat64)

#define OPEN(fn)                                                                                                      \
    int fn(const char* name, int flags, ...) {                                                                        \
        static int (*real)(const char*, int, ...) = 0;                                                                \
        if (!real) real = (int (*)(const char*, int, ...))dlsym(RTLD_NEXT, #fn);                                      \
        va_list ap;                                                                                                   \
        va_start(ap, flags);                                                                                          \
        const int mode = (flags & (O_CREAT | O_TMPFILE)) ? va_arg(ap, int) : 0;                                       \
        va_end(ap);                                                                                                   \
        if (flags & O_DIRECTORY) slow(name);                                                                          \
        return real(name, flags, mode);                                                                               \
    }
OPEN(open)
OPEN(open64)

// (_FORTIFY_SOURCE builds call these for two-argument opens.)
int __openat_2(int dir, const char* name, int flags) {
    static int (*real)(int, const char*, int) = 0;
    if (!real) real = (int (*)(int, const char*, int))dlsym(RTLD_NEXT, "__openat_2");
    if (flags & O_DIRECTORY) slow(name);
    return real(dir, name, flags);
}
int __open_2(const char* name, int flags) {
    static int (*real)(const char*, int) = 0;
    if (!real) real = (int (*)(const char*, int))dlsym(RTLD_NEXT, "__open_2");
    if (flags & O_DIRECTORY) slow(name);
    return real(name, flags);
}
