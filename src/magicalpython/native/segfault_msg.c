// src/native/segfault_msg.c
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <signal.h>
#include <unistd.h>
#endif

static const char PPP_CRASH_MSG[] = "\x1b[31m\x1b[1mSegmentation fault!\x1b[0m\n\n\x1b[31mChances are, your assembly is faulty.\n\nRemember that segmentation faults may be a sign of memory corruption.\nIf you experience unusual program crashes or behaviour, restart your device.\nAlright, time to go now, bye!\n\n- Python++\x1b[0m\n";

#ifdef _WIN32

static LONG WINAPI handler(EXCEPTION_POINTERS* info)
{
    DWORD code = info->ExceptionRecord->ExceptionCode;

    if (code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_STACK_OVERFLOW || code == EXCEPTION_ILLEGAL_INSTRUCTION || code == EXCEPTION_PRIV_INSTRUCTION || code == EXCEPTION_IN_PAGE_ERROR) {

        HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
        DWORD written;
        WriteFile(err, PPP_CRASH_MSG, (DWORD)(sizeof(PPP_CRASH_MSG) - 1), &written, NULL);

        // Terminate immediately - do NOT let ctypes' own SEH wrapper catch this
        // and turn it into a recoverable Python OSError. This IS the crash.
        TerminateProcess(GetCurrentProcess(), (UINT)0xC0000005);
    }

    return EXCEPTION_CONTINUE_SEARCH; // only reached for exception types we don't claim
}

__declspec(dllexport) void ppp_install_segfault_handler(void)
{
    AddVectoredExceptionHandler(1, handler);
}

#else

static void handler(int sig)
{
    write(STDERR_FILENO, PPP_CRASH_MSG, sizeof(PPP_CRASH_MSG) - 1);
    signal(sig, SIG_DFL);
    raise(sig); // already unrecoverable on POSIX - this re-raise really does kill the process
}

__attribute__((visibility("default"))) void ppp_install_segfault_handler(void)
{
    static char altstack[SIGSTKSZ];
    stack_t ss;
    ss.ss_sp = altstack;
    ss.ss_size = sizeof(altstack);
    ss.ss_flags = 0;
    sigaltstack(&ss, NULL);

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = handler;
    sa.sa_flags = SA_ONSTACK;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
}

#endif