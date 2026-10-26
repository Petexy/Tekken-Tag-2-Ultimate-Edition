/* t8helper: reads Tekken 8 fighters' moveset files with the game's own file reader, from inside its Wine prefix (run
 * with Proton next to the running game; tools/characters/ttt2char/tekken8/autodump.py drives it).
 *
 *   t8helper serve <port> <secret>     takes one connection at a time on 127.0.0.1:<port> (Proton's launcher passes no
 *                                      stdin/stdout on); the first line must be the secret, then commands, one per
 *                                      line, each answered on the connection:
 *     dlc <steam_api64.dll path>       the game's DLC as the game asks Steam (SteamAppId=1778820, Steam running):
 *                                      "<appid> <owned 0/1> <name>" lines, then "end" ("error ..." without Steam)
 *     attach                           finds the game (Polaris-Win64-Shipping.exe) and where it is loaded, and checks
 *                                      that it is the build whose functions this helper knows (by hashes of their
 *                                      first bytes): "ok", or "error ..."
 *     ready                            whether the game has opened its moveset archive and made its task manager:
 *                                      "1" or "0"
 *     want <path>                      queues a file of the moveset archive for `fetch` ("Binary/mothead/...", '/'
 *                                      between folders): "ok", or "error ..."
 *     fetch                            reads the queued files as the game reads them (its own archive reader, which
 *                                      hands them over decoded): "file <0/1> <n>" then n raw bytes per file, in queue
 *                                      order, then "end"; the queue is emptied
 *     protected <path>                 for a motbin fetched before: the plain values of the six protected fields of
 *                                      each of its moves, as the game's own code gives them: "protected <moves>
 *                                      <stride> <moves offset>" then moves x 6 little-endian u32 (each move's fields
 *                                      at +0x00 +0x20 +0x58 +0x78 +0xd0 +0xf0), or "error ..."
 *     quit                             ends the helper
 *
 * Reading a file: the game's own request function makes the request (its layout is the game's business) and queues
 * it; the game's archive tick, every frame, hands the queue to its reader, which reads, decodes and decompresses the
 * file; the helper polls the request's state and copies the bytes out. The queue has no lock, so a request is made
 * only while the archive is idle (nothing being read, no queue being drained) and only one at a time: the game queues
 * nothing itself on its start-up screens, so the reader never sees more than that one request. Requests are never
 * released (the archive's release lists have no lock either): their buffers stay in the game, which the session
 * closes at its end.
 *
 * The protected fields: the motbin as the reader hands it over is plain but for six 32-byte fields of every move,
 * which the game turns into a 16-byte form of its own when it loads a fighter (the motbin request's completion
 * callback) and reads back with a getter. The helper copies the motbin into memory the game allocates, runs that
 * callback on the copy and calls the getter on every field. Neither the transform nor its constants are read or
 * reimplemented here.
 *
 * The game's functions are called on a thread of their own; no address or code comes from the connection. The only
 * functions ever called are the four below, each checked by a hash of its first bytes before any call, so another
 * build of the game is refused, not crashed. The moveset archive (tkdata.bin) is never opened by the helper, and
 * nothing is written into the game's files, saves or prefix (but the helper's copy at C:\t8helper.exe).
 *
 * Written for this project (MIT); no third-party code.
 */
#include <winsock2.h>
#include <windows.h>
#include <tlhelp32.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------ the game (TEKKEN 8, Steam build 25221600) */

#define GAME_EXE "Polaris-Win64-Shipping.exe"
/* Addresses are the ones at the exe's preferred base; `attach` moves them all to where the game is loaded. */
#define PREFERRED_BASE 0x140000000ull

/* The game's functions the helper calls, each checked before any call by a hash (64-bit FNV-1a) of its first bytes. */
struct Function {
    unsigned long long address;
    size_t length;               /* bytes hashed */
    unsigned long long hash;
};
/* memory = ALLOCATE(size): the game's allocator (16-byte aligned), for the motbin's copy and the field table */
static const struct Function ALLOCATE = {0x142cd0070ull, 16, 0x9A0F7237C356D9F4ull};
/* request = REQUEST_FILE(archive, path): makes a request (0xa0 bytes, the path copied) and queues it on the archive */
static const struct Function REQUEST_FILE = {0x1459f9c50ull, 16, 0xAD224657991D6490ull};
/* PROTECT_FIELDS(motbin): the motbin request's completion callback; turns the six fields of every move into the
 * game's 16-byte form, in place, at the same offsets */
static const struct Function PROTECT_FIELDS = {0x1418acfb0ull, 16, 0xEF46830222BE4AC8ull};
/* value = READ_FIELD(field): the getter the battle code reads a protected field with (a u32 in eax) */
static const struct Function READ_FIELD = {0x141809d00ull, 16, 0x4C7611802A9CD63Bull};
/* Read, never called: the archive (a pointer to it) and the task manager (a pointer to it). */
static const unsigned long long ARCHIVE = 0x149b8b970ull, TASK_MANAGER = 0x149880000ull;
enum {
    ARCHIVE_OPEN = 0x80,         /* u8: 1 once the moveset archive is open */
    ARCHIVE_READING = 0xc0,      /* the read in flight (0: none) */
    ARCHIVE_DRAINING = 0xd8,     /* the queue being drained (0: none) */
    REQUEST_DATA = 0x20,         /* the file's bytes */
    REQUEST_SIZE = 0x28,         /* u32 */
    REQUEST_STATE = 0x30,        /* i32: 0 pending, 1 failed, 2 done */
    STATE_FAILED = 1, STATE_DONE = 2,
    /* a motbin in its file form: "TEK\0" at 8, byte 2 zero (set once the game has turned its offsets into pointers),
     * the moves table's offset (from MOTBIN_BASE) and count in the header */
    MOTBIN_MAGIC = 8, MOTBIN_FIXED = 2, MOTBIN_BASE = 0x318, MOTBIN_MOVES = 0x230, MOTBIN_MOVE_COUNT = 0x238,
    MOVE_SIZE = 0x448, FIELDS = 6, MAX_MOVES = 100000,
    MAX_FILES = 64, PATH_CHARS = 260
};
static const unsigned FIELD_OFFSETS[FIELDS] = {0x00, 0x20, 0x58, 0x78, 0xd0, 0xf0};
/* How long the helper waits (ms): for the archive to be idle before a request; for a request (com.anmbin, 552 MB, takes
 * seconds); for a game function's thread; for the getter's thread (a few ms per thousand moves). The driver's socket
 * waits longer than the first two together. */
enum { IDLE_WAIT = 30000, REQUEST_WAIT = 120000, CALL_WAIT = 30000, FIELDS_WAIT = 120000, POLL = 5 };

static HANDLE g_game;
static int g_checked, g_ready;
static unsigned long long g_delta;           /* where the game is loaded - PREFERRED_BASE */
static unsigned long long g_archive;         /* the archive (once `ready`) */

static unsigned long long at(unsigned long long preferred) { return preferred + g_delta; }

/* ------------------------------------------------------------ answers */

static SOCKET g_sock = INVALID_SOCKET;
static char g_buf[1 << 16];
static size_t g_len;

static void out_flush(void) {
    size_t sent = 0;
    while (sent < g_len) {
        const int n = send(g_sock, g_buf + sent, (int)(g_len - sent), 0);
        if (n <= 0) break;
        sent += (size_t)n;
    }
    g_len = 0;
}
static void out_write(const void* data, size_t n) {
    const char* p = data;
    while (n) {
        if (g_len == sizeof g_buf) out_flush();
        size_t k = sizeof g_buf - g_len;
        if (k > n) k = n;
        memcpy(g_buf + g_len, p, k);
        g_len += k;
        p += k;
        n -= k;
    }
}
static void out_printf(const char* format, ...) {
    char line[512];
    va_list args;
    va_start(args, format);
    const int n = vsnprintf(line, sizeof line, format, args);
    va_end(args);
    if (n > 0) out_write(line, (size_t)n < sizeof line ? (size_t)n : sizeof line - 1);
    out_flush();
}

/* ------------------------------------------------------------ Steam: the DLC the player owns */

static void dlc(const char* dll) {
    HMODULE steam = LoadLibraryA(dll && *dll ? dll : "steam_api64.dll");
    if (!steam) {
        out_printf("error steam_api64.dll not found\n");
        return;
    }
    typedef int (*Init)(void);
    typedef void (*Shutdown)(void);
    typedef void* (*Apps)(void);
    typedef int (*Count)(void*);
    typedef int (*Data)(void*, int, unsigned*, int*, char*, int);
    typedef int (*Subscribed)(void*, unsigned);
    Init init = (Init)(void*)GetProcAddress(steam, "SteamAPI_Init");
    Shutdown shutdown = (Shutdown)(void*)GetProcAddress(steam, "SteamAPI_Shutdown");
    /* (Tekken 8's Steamworks has the versioned accessor only; older ones the plain one) */
    Apps apps = (Apps)(void*)GetProcAddress(steam, "SteamAPI_SteamApps_v008");
    if (!apps) apps = (Apps)(void*)GetProcAddress(steam, "SteamApps");
    Count count = (Count)(void*)GetProcAddress(steam, "SteamAPI_ISteamApps_GetDLCCount");
    Data data = (Data)(void*)GetProcAddress(steam, "SteamAPI_ISteamApps_BGetDLCDataByIndex");
    /* whether the account owns an app (a DLC too, also through family sharing): the list's own flag is Steam's
     * "available", which it documents as "on the store" */
    Subscribed subscribed = (Subscribed)(void*)GetProcAddress(steam, "SteamAPI_ISteamApps_BIsSubscribedApp");
    if (!init || !shutdown || !apps || !count || !data) {
        out_printf("error steam_api64.dll lacks the calls it needs\n");
        return;
    }
    if (!init()) {
        out_printf("error Steam is not running (or does not know the game)\n");
        return;
    }
    void* a = apps();
    const int n = a ? count(a) : 0;
    for (int i = 0; i < n; ++i) {
        unsigned id = 0;
        int available = 0; /* a C++ bool: only its first byte is written (a returned one: al) */
        char name[256] = {0};
        if (!data(a, i, &id, &available, name, sizeof name)) continue;
        out_printf("%u %d %s\n", id, (subscribed ? subscribed(a, id) : available) & 0xFF ? 1 : 0, name);
    }
    out_printf("end\n");
    shutdown();
}

/* ------------------------------------------------------------ the game's process */

static DWORD game_pid(void) {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32 pe;
    memset(&pe, 0, sizeof pe);
    pe.dwSize = sizeof pe;
    DWORD pid = 0;
    if (snap == INVALID_HANDLE_VALUE) return 0;
    for (BOOL ok = Process32First(snap, &pe); ok; ok = Process32Next(snap, &pe)) {
        if (_stricmp(pe.szExeFile, GAME_EXE) == 0) {
            pid = pe.th32ProcessID;
            break;
        }
    }
    CloseHandle(snap);
    return pid;
}

/* Where the game's exe is loaded in its process (0: not yet). */
static unsigned long long game_base(DWORD pid) {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    MODULEENTRY32 me;
    memset(&me, 0, sizeof me);
    me.dwSize = sizeof me;
    unsigned long long base = 0;
    if (snap == INVALID_HANDLE_VALUE) return 0;
    for (BOOL ok = Module32First(snap, &me); ok; ok = Module32Next(snap, &me)) {
        if (_stricmp(me.szModule, GAME_EXE) == 0) {
            base = (unsigned long long)(size_t)me.modBaseAddr;
            break;
        }
    }
    CloseHandle(snap);
    return base;
}

static int read_game(unsigned long long address, void* out, size_t size) {
    SIZE_T got = 0;
    return g_game && ReadProcessMemory(g_game, (void*)(size_t)address, out, size, &got) && got == size;
}

static unsigned long long read_u64(unsigned long long address) {
    unsigned long long v = 0;
    read_game(address, &v, 8);
    return v;
}

static unsigned read_u32(unsigned long long address) {
    unsigned v = 0;
    read_game(address, &v, 4);
    return v;
}

static int matches(const struct Function* f) {
    unsigned char b[16];
    if (f->length > sizeof b || !read_game(at(f->address), b, f->length)) return 0;
    unsigned long long h = 0xcbf29ce484222325ull;
    for (size_t i = 0; i < f->length; ++i) h = (h ^ b[i]) * 0x100000001b3ull;
    return h == f->hash;
}

static void attach(void) {
    g_checked = g_ready = 0;
    const DWORD pid = game_pid();
    if (!pid) {
        out_printf("error Tekken 8 is not running\n");
        return;
    }
    const unsigned long long base = game_base(pid);
    if (!base) {
        out_printf("error the game is not loaded yet\n");
        return;
    }
    if (g_game) CloseHandle(g_game);
    g_game = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE |
                         PROCESS_VM_READ, FALSE, pid);
    if (!g_game) {
        out_printf("error cannot open the game (%lu)\n", (unsigned long)GetLastError());
        return;
    }
    g_delta = base - PREFERRED_BASE;
    const struct Function* all[] = {&ALLOCATE, &REQUEST_FILE, &PROTECT_FIELDS, &READ_FIELD};
    for (size_t i = 0; i < sizeof all / sizeof all[0]; ++i) {
        if (!matches(all[i])) {
            out_printf("error this Tekken 8 build is not the one the helper knows\n");
            return;
        }
    }
    g_checked = 1;
    out_printf("ok\n");
}

static void ready(void) {
    unsigned char open = 0;
    g_archive = g_checked ? read_u64(at(ARCHIVE)) : 0;
    if (g_archive) read_game(g_archive + ARCHIVE_OPEN, &open, 1);
    g_ready = g_archive && open == 1 && read_u64(at(TASK_MANAGER));
    out_printf("%d\n", g_ready);
}

/* ------------------------------------------------------------ calling the game's functions */

static void put64(unsigned char* code, size_t* n, unsigned char a, unsigned char b, unsigned long long v) {
    code[(*n)++] = a;
    code[(*n)++] = b;
    memcpy(code + *n, &v, 8);
    *n += 8;
}

/* Runs `n` bytes of code on a thread of its own in the game; -> whether the thread finished within `wait` ms (the code
 * is freed then; a thread still running keeps it). */
static int run(const unsigned char* code, size_t n, DWORD wait, unsigned char** where) {
    unsigned char* stub = VirtualAllocEx(g_game, NULL, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    SIZE_T done;
    int finished = 0;
    if (!stub) return 0;
    if (where) *where = stub;
    if (WriteProcessMemory(g_game, stub, code, n, &done)) {
        FlushInstructionCache(g_game, stub, n);
        HANDLE t = CreateRemoteThread(g_game, NULL, 0, (LPTHREAD_START_ROUTINE)stub, NULL, 0, NULL);
        if (t) {
            finished = WaitForSingleObject(t, wait) == WAIT_OBJECT_0;
            CloseHandle(t);
        }
    }
    return finished;
}

/* Calls one of the game's functions (two integer arguments) on a thread of its own: -> whether it returned, its rax in
 * `result`. The stub: sub rsp,0x28; rcx, rdx = the arguments; call the function; store rax at stub+0x100;
 * add rsp,0x28; ret (the thread starts with rsp 8 below a multiple of 16: the call is aligned). */
static int call(const struct Function* f, unsigned long long a1, unsigned long long a2, unsigned long long* result) {
    enum { RESULT = 0x100 };
    unsigned char code[96], *stub = NULL;
    size_t n = 0;
    if (!g_checked) return 0;
    code[n++] = 0x48; code[n++] = 0x83; code[n++] = 0xEC; code[n++] = 0x28;   /* sub rsp, 0x28 */
    put64(code, &n, 0x48, 0xB9, a1);                                          /* mov rcx, a1 */
    put64(code, &n, 0x48, 0xBA, a2);                                          /* mov rdx, a2 */
    put64(code, &n, 0x48, 0xB8, at(f->address));                              /* mov rax, function */
    code[n++] = 0xFF; code[n++] = 0xD0;                                       /* call rax */
    code[n++] = 0x48; code[n++] = 0x8D; code[n++] = 0x0D;                     /* lea rcx, [rip + to RESULT] */
    const int to_result = (int)(RESULT - (n + 4));
    memcpy(code + n, &to_result, 4); n += 4;
    code[n++] = 0x48; code[n++] = 0x89; code[n++] = 0x01;                     /* mov [rcx], rax */
    code[n++] = 0x48; code[n++] = 0x83; code[n++] = 0xC4; code[n++] = 0x28;   /* add rsp, 0x28 */
    code[n++] = 0x31; code[n++] = 0xC0; code[n++] = 0xC3;                     /* xor eax, eax; ret */
    if (!run(code, n, CALL_WAIT, &stub)) return 0;
    const int ok = read_game((unsigned long long)(size_t)stub + RESULT, result, 8);
    VirtualFreeEx(g_game, stub, 0, MEM_RELEASE);
    return ok;
}

static unsigned long long allocate(unsigned long long size) {
    unsigned long long memory = 0;
    return call(&ALLOCATE, size, 0, &memory) ? memory : 0;
}

/* ------------------------------------------------------------ reading files with the game's reader */

static char g_wanted[MAX_FILES][PATH_CHARS];
static unsigned g_wanted_count;

/* The files read this session (the request's bytes stay in the game): for `protected`. */
static struct {
    char path[PATH_CHARS];
    unsigned long long data;
    unsigned size;
} g_read[MAX_FILES];
static unsigned g_read_count;

/* Only files of the moveset archive by a plain relative path: "Binary/" then letters, digits, '_', '-', '.' and '/',
 * no "..". */
static int path_ok(const char* path) {
    const size_t len = strlen(path);
    if (strncmp(path, "Binary/", 7) || len >= PATH_CHARS || strstr(path, "..")) return 0;
    for (size_t i = 0; i < len; ++i) {
        const char c = path[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-' ||
              c == '.' || c == '/'))
            return 0;
    }
    return 1;
}

static void want(const char* path) {
    if (!path_ok(path)) {
        out_printf("error not a path of the game's moveset files\n");
        return;
    }
    if (g_wanted_count == MAX_FILES) {
        out_printf("error too many files queued\n");
        return;
    }
    memcpy(g_wanted[g_wanted_count++], path, strlen(path) + 1);
    out_printf("ok\n");
}

static int archive_idle(void) {
    unsigned long long v[2] = {1, 1};
    return read_game(g_archive + ARCHIVE_READING, &v[0], 8) && read_game(g_archive + ARCHIVE_DRAINING, &v[1], 8) &&
           !v[0] && !v[1];
}

/* Has the game read one file: -> its request once done, or 0 (the archive stayed busy, the game failed, or it took too
 * long). A request is made only while the archive is idle; the next one only once this one is done. */
static unsigned long long read_file(const char* path) {
    if (!g_ready) return 0;
    int waited = 0;
    while (!archive_idle()) {
        if (waited >= IDLE_WAIT) return 0;
        Sleep(POLL);
        waited += POLL;
    }
    const size_t len = strlen(path) + 1;
    unsigned char* text = VirtualAllocEx(g_game, NULL, len, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    SIZE_T done;
    unsigned long long request = 0;
    if (!text || !WriteProcessMemory(g_game, text, path, len, &done) ||
        !call(&REQUEST_FILE, g_archive, (unsigned long long)(size_t)text, &request) || !request) {
        if (text) VirtualFreeEx(g_game, text, 0, MEM_RELEASE);
        return 0;
    }
    for (waited = 0; waited < REQUEST_WAIT; waited += POLL) {
        const unsigned state = read_u32(request + REQUEST_STATE);
        if (state == STATE_DONE || state == STATE_FAILED) {
            VirtualFreeEx(g_game, text, 0, MEM_RELEASE);      /* (the request keeps a copy of the path) */
            return state == STATE_DONE ? request : 0;
        }
        Sleep(POLL);
    }
    return 0;                                                 /* (the path's memory stays: the request may go on) */
}

static void remember(const char* path, unsigned long long data, unsigned size) {
    unsigned i = 0;
    while (i < g_read_count && strcmp(g_read[i].path, path)) ++i;
    if (i == MAX_FILES) return;
    if (i == g_read_count) {
        memcpy(g_read[i].path, path, strlen(path) + 1);
        ++g_read_count;
    }
    g_read[i].data = data;
    g_read[i].size = size;
}

static void fetch(void) {
    const unsigned count = g_wanted_count;
    g_wanted_count = 0;
    for (unsigned i = 0; i < count; ++i) {
        const unsigned long long request = read_file(g_wanted[i]);
        const unsigned long long data = request ? read_u64(request + REQUEST_DATA) : 0;
        const unsigned size = request ? read_u32(request + REQUEST_SIZE) : 0;
        char* bytes = data && size ? malloc(size) : NULL;
        const int ok = bytes && read_game(data, bytes, size);
        out_printf("file %d %u\n", ok, ok ? size : 0);
        if (ok) {
            out_write(bytes, size);
            remember(g_wanted[i], data, size);
        }
        out_flush();
        free(bytes);
    }
    out_printf("end\n");
}

/* ------------------------------------------------------------ the protected move fields */

/* Calls READ_FIELD on every field of every move (`moves` moves of MOVE_SIZE bytes from `first`), all on one thread of
 * its own, storing the u32 values one after the other at `table`: -> whether the thread finished. The stub keeps its
 * state in rbx (the move), esi (moves left), rdi (the table) and r13 (the getter), which the getter preserves. */
static int read_fields(unsigned long long first, unsigned moves, unsigned long long table) {
    unsigned char code[256];
    size_t n = 0;
    code[n++] = 0x53; code[n++] = 0x56; code[n++] = 0x57;                     /* push rbx; push rsi; push rdi */
    code[n++] = 0x41; code[n++] = 0x55;                                       /* push r13 */
    code[n++] = 0x48; code[n++] = 0x83; code[n++] = 0xEC; code[n++] = 0x28;   /* sub rsp, 0x28 (call aligned) */
    put64(code, &n, 0x48, 0xBB, first);                                       /* mov rbx, first */
    code[n++] = 0xBE; memcpy(code + n, &moves, 4); n += 4;                    /* mov esi, moves */
    put64(code, &n, 0x48, 0xBF, table);                                       /* mov rdi, table */
    put64(code, &n, 0x49, 0xBD, at(READ_FIELD.address));                      /* mov r13, getter */
    const size_t loop = n;
    code[n++] = 0x85; code[n++] = 0xF6;                                       /* test esi, esi */
    code[n++] = 0x74; const size_t done = n++;                                /* je done (rel8: 107 bytes on) */
    for (int k = 0; k < FIELDS; ++k) {
        const unsigned offset = FIELD_OFFSETS[k];
        code[n++] = 0x48; code[n++] = 0x8D; code[n++] = 0x8B;                 /* lea rcx, [rbx + offset] */
        memcpy(code + n, &offset, 4); n += 4;
        code[n++] = 0x41; code[n++] = 0xFF; code[n++] = 0xD5;                 /* call r13 */
        code[n++] = 0x89; code[n++] = 0x07;                                   /* mov [rdi], eax */
        code[n++] = 0x48; code[n++] = 0x83; code[n++] = 0xC7; code[n++] = 0x04; /* add rdi, 4 */
    }
    const unsigned stride = MOVE_SIZE;
    code[n++] = 0x48; code[n++] = 0x81; code[n++] = 0xC3;                     /* add rbx, MOVE_SIZE */
    memcpy(code + n, &stride, 4); n += 4;
    code[n++] = 0xFF; code[n++] = 0xCE;                                       /* dec esi */
    code[n++] = 0xEB; code[n] = (unsigned char)(loop - (n + 1)); n++;         /* jmp loop (rel8: 111 bytes back) */
    code[done] = (unsigned char)(n - (done + 1));
    code[n++] = 0x48; code[n++] = 0x83; code[n++] = 0xC4; code[n++] = 0x28;   /* add rsp, 0x28 */
    code[n++] = 0x41; code[n++] = 0x5D;                                       /* pop r13 */
    code[n++] = 0x5F; code[n++] = 0x5E; code[n++] = 0x5B;                     /* pop rdi; pop rsi; pop rbx */
    code[n++] = 0x31; code[n++] = 0xC0; code[n++] = 0xC3;                     /* xor eax, eax; ret */
    unsigned char* stub = NULL;
    if (!run(code, n, FIELDS_WAIT, &stub)) return 0;
    VirtualFreeEx(g_game, stub, 0, MEM_RELEASE);
    return 1;
}

static void protected_fields(const char* path) {
    unsigned long long source = 0;
    unsigned size = 0;
    for (unsigned i = 0; i < g_read_count; ++i)
        if (!strcmp(g_read[i].path, path)) {
            source = g_read[i].data;
            size = g_read[i].size;
        }
    if (!source || !g_checked) {
        out_printf("error that motbin was not read this session\n");
        return;
    }
    /* the motbin in its file form, its moves table inside it */
    char* bytes = size >= MOTBIN_BASE ? malloc(size) : NULL;
    if (!bytes || !read_game(source, bytes, size)) {
        free(bytes);
        out_printf("error cannot read the motbin\n");
        return;
    }
    unsigned long long moves_at;
    int moves;
    memcpy(&moves_at, bytes + MOTBIN_MOVES, 8);
    memcpy(&moves, bytes + MOTBIN_MOVE_COUNT, 4);
    if (memcmp(bytes + MOTBIN_MAGIC, "TEK", 4) || bytes[MOTBIN_FIXED] || moves <= 0 || moves > MAX_MOVES ||
        moves_at > size || MOTBIN_BASE + moves_at + (unsigned long long)moves * MOVE_SIZE > size) {
        free(bytes);
        out_printf("error not a motbin in its file form\n");
        return;
    }
    /* a copy for the game's callback to change (the request's bytes stay as they are), and the table of values; both
     * stay in the game, as the requests do */
    const unsigned long long copy = allocate(size);
    const unsigned long long table = allocate((unsigned long long)moves * FIELDS * 4);
    SIZE_T done;
    unsigned long long ignored;
    const int copied = copy && table && WriteProcessMemory(g_game, (void*)(size_t)copy, bytes, size, &done);
    free(bytes);
    if (!copied) {
        out_printf("error cannot copy the motbin in the game\n");
        return;
    }
    if (!call(&PROTECT_FIELDS, copy, 0, &ignored) ||
        !read_fields(copy + MOTBIN_BASE + moves_at, (unsigned)moves, table)) {
        out_printf("error the game did not give the fields\n");
        return;
    }
    const size_t table_size = (size_t)moves * FIELDS * 4;
    unsigned* values = malloc(table_size);
    if (!values || !read_game(table, values, table_size)) {
        free(values);
        out_printf("error cannot read the fields\n");
        return;
    }
    out_printf("protected %d %d %llu\n", moves, MOVE_SIZE, moves_at);
    out_write(values, table_size);
    out_flush();
    free(values);
}

/* ------------------------------------------------------------ the connection */

static int serve(int port, const char* secret) {
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return 2;
    SOCKET listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    struct sockaddr_in local;
    memset(&local, 0, sizeof local);
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    local.sin_port = htons((u_short)port);
    if (listener == INVALID_SOCKET || bind(listener, (struct sockaddr*)&local, sizeof local) != 0 ||
        listen(listener, 1) != 0) {
        fprintf(stderr, "t8helper: cannot listen on 127.0.0.1:%d\n", port);
        return 2;
    }
    char input[4096], line[512];
    size_t have = 0;
    int quit = 0, trusted = 0;
    while (!quit) {
        if (g_sock == INVALID_SOCKET) { /* the next client */
            g_sock = accept(listener, NULL, NULL);
            have = 0;
            trusted = 0;
            if (g_sock == INVALID_SOCKET) break;
        }
        char* end = memchr(input, '\n', have);
        if (!end) {
            if (have == sizeof input) have = 0; /* an overlong line: dropped */
            const int n = recv(g_sock, input + have, (int)(sizeof input - have), 0);
            if (n <= 0) {
                closesocket(g_sock);
                g_sock = INVALID_SOCKET;
                continue;
            }
            have += (size_t)n;
            continue;
        }
        size_t len = (size_t)(end - input);
        if (len >= sizeof line) len = sizeof line - 1;
        memcpy(line, input, len);
        line[len] = 0;
        if (len && line[len - 1] == '\r') line[len - 1] = 0;
        have -= (size_t)(end - input) + 1;
        memmove(input, end + 1, have);
        if (!trusted) {                    /* the first line: the secret, or the connection is dropped */
            trusted = strcmp(line, secret) == 0;
            if (!trusted) {
                closesocket(g_sock);
                g_sock = INVALID_SOCKET;
            }
            continue;
        }
        char cmd[32] = {0}, arg[300] = {0};
        if (sscanf(line, "%31s", cmd) != 1) continue;
        if (!strcmp(cmd, "quit")) {
            quit = 1;
        } else if (!strcmp(cmd, "dlc") && sscanf(line, "%*s %299[^\n]", arg) == 1) {
            dlc(arg);
        } else if (!strcmp(cmd, "attach")) {
            attach();
        } else if (!strcmp(cmd, "ready")) {
            ready();
        } else if (!strcmp(cmd, "want") && sscanf(line, "%*s %299[^\n]", arg) == 1) {
            want(arg);
        } else if (!strcmp(cmd, "fetch")) {
            fetch();
        } else if (!strcmp(cmd, "protected") && sscanf(line, "%*s %299[^\n]", arg) == 1) {
            protected_fields(arg);
        } else {
            out_printf("error %s\n", line);
        }
    }
    if (g_sock != INVALID_SOCKET) closesocket(g_sock);
    closesocket(listener);
    WSACleanup();
    if (g_game) CloseHandle(g_game);
    return 0;
}

int main(int argc, char** argv) {
    if (argc >= 4 && !strcmp(argv[1], "serve")) return serve(atoi(argv[2]), argv[3]);
    fprintf(stderr, "usage: t8helper serve <port> <secret>\n");
    return 1;
}
