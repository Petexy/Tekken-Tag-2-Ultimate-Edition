/* Windows memory mapping for the private PE image used by oodle.c. */
#include <windows.h>
#include <intrin.h>
#include <io.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define PROT_READ 1
#define PROT_WRITE 2
#define PROT_EXEC 4
#define MAP_PRIVATE 1
#define MAP_ANONYMOUS 2
#define MAP_FIXED_NOREPLACE 4
#define MAP_FAILED ((void *)-1)
#define O_CLOEXEC 0

static int open_utf8(const char *name, int flags) {
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name, -1, NULL, 0);
    if (!n) return -1;
    wchar_t *wide = malloc((size_t)n * sizeof *wide);
    if (!wide) return -1;
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name, -1, wide, n);
    int fd = _wopen(wide, flags | _O_BINARY);
    free(wide);
    return fd;
}
#define open open_utf8

static void *mmap(void *address, size_t size, int prot, int flags, int fd, long offset) {
    (void)prot; (void)offset;
    void *p;
    if (flags & MAP_ANONYMOUS) {
        p = VirtualAlloc(address, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    } else {
        HANDLE mapping = CreateFileMappingW((HANDLE)_get_osfhandle(fd), NULL, PAGE_READONLY, 0, 0, NULL);
        if (!mapping) return MAP_FAILED;
        p = MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, size);
        CloseHandle(mapping);
    }
    return p ? p : MAP_FAILED;
}

static int munmap(void *p, size_t size) {
    (void)size;
    MEMORY_BASIC_INFORMATION info;
    if (!VirtualQuery(p, &info, sizeof info)) return -1;
    return (info.Type == MEM_MAPPED ? UnmapViewOfFile(p) : VirtualFree(p, 0, MEM_RELEASE)) ? 0 : -1;
}

static int mprotect(void *p, size_t size, int prot) {
    DWORD old, flags = PAGE_NOACCESS;
    if (prot & PROT_EXEC) flags = prot & PROT_WRITE ? PAGE_EXECUTE_READWRITE : PAGE_EXECUTE_READ;
    else if (prot & PROT_WRITE) flags = PAGE_READWRITE;
    else if (prot & PROT_READ) flags = PAGE_READONLY;
    if (!VirtualProtect(p, size, flags, &old)) return -1;
    if (prot & PROT_EXEC) FlushInstructionCache(GetCurrentProcess(), p, size);
    return 0;
}

static const void *memmem(const void *haystack, size_t size, const void *needle, size_t length) {
    const unsigned char *p = haystack;
    if (length > size) return NULL;
    for (size_t i = 0; i <= size - length; ++i)
        if (!memcmp(p + i, needle, length)) return p + i;
    return NULL;
}
