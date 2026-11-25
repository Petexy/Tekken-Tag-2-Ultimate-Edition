// Native Windows entry point for the Windows-only launcher frontend.
// No GTK, POSIX process code, game assets, or user-specific paths are embedded.
//
// As CMake builds it, it opens the launcher of the project it was built in.
// The release's Golden_Fist_Launcher-x86_64.exe is this program with the
// project's files in it (make_launcher_exe.py): it keeps them in
// %LOCALAPPDATA%\TTT2Ultimate\launcher (files_folder), unpacked again whenever they differ
// from the last ones, and opens the launcher from there, which can replace
// this .exe with a newer release (self_update.py).
//
// Its files (their format, checks, folder and unpacking) are launcher/core's
// payload.h, which the new launcher's start (startup.h) shares.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shellapi.h>
#include <cwchar>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include "payload.h"
namespace fs = std::filesystem;
using launcher::payload::files_folder;
using launcher::payload::unpack;

#ifndef TTT2_LAUNCHER_VERSION
#error "TTT2_LAUNCHER_VERSION must name the launcher's version (launcher/builder/CMakeLists.txt)"
#endif

std::wstring quote(const std::wstring& s) {
    std::wstring out=L"\""; size_t slashes=0;
    for(wchar_t c:s) {
        if(c==L'\\') { ++slashes; continue; }
        if(c==L'\"') out.append(slashes*2+1,L'\\'); else out.append(slashes,L'\\');
        slashes=0; out+=c;
    }
    out.append(slashes*2,L'\\'); return out+L'\"';
}
std::wstring environment(const wchar_t* name) {
    DWORD n=GetEnvironmentVariableW(name,nullptr,0); if(!n) return {};
    std::wstring result(n,L'\0'); GetEnvironmentVariableW(name,result.data(),n); result.resize(n-1); return result;
}
std::wstring wide(std::string_view s) {
    if(s.empty()) return {};
    int n=MultiByteToWideChar(CP_UTF8,0,s.data(),static_cast<int>(s.size()),nullptr,0);
    std::wstring out(n,L'\0'); MultiByteToWideChar(CP_UTF8,0,s.data(),static_cast<int>(s.size()),out.data(),n); return out;
}
std::string narrow(const std::wstring& s) {
    if(s.empty()) return {};
    int n=WideCharToMultiByte(CP_UTF8,0,s.data(),static_cast<int>(s.size()),nullptr,0,nullptr,nullptr);
    std::string out(n,'\0'); WideCharToMultiByte(CP_UTF8,0,s.data(),static_cast<int>(s.size()),out.data(),n,nullptr,nullptr); return out;
}
fs::path python(const fs::path& folder) {
    if(auto value=environment(L"TTT2_PYTHON"); !value.empty()) {
        if(!fs::is_regular_file(value)) throw std::runtime_error("TTT2_PYTHON does not name a Python executable.");
        return value;
    }
    const auto portable=folder.parent_path()/"local/windows-tools/python-runtime/python/python.exe";
    if(fs::is_regular_file(portable)) return portable;
    for(HKEY hive:{HKEY_CURRENT_USER,HKEY_LOCAL_MACHINE}) {
        HKEY parent;
        if(RegOpenKeyExW(hive,L"Software\\Python\\PythonCore",0,KEY_READ,&parent)!=ERROR_SUCCESS) continue;
        wchar_t version[256]; DWORD length;
        std::vector<std::wstring> versions;
        for(DWORD i=0;;++i) {
            length=256;
            if(RegEnumKeyExW(parent,i,version,&length,nullptr,nullptr,nullptr,nullptr)!=ERROR_SUCCESS) break;
            if(version[0]==L'3') versions.emplace_back(version);
        }
        for(auto it=versions.rbegin();it!=versions.rend();++it) {
            HKEY key;
            if(RegOpenKeyExW(parent,(*it+L"\\InstallPath").c_str(),0,KEY_READ,&key)!=ERROR_SUCCESS) continue;
            wchar_t path[32768]; DWORD bytes=sizeof(path),type=0;
            const auto result=RegQueryValueExW(key,L"ExecutablePath",nullptr,&type,reinterpret_cast<BYTE*>(path),&bytes);
            RegCloseKey(key);
            if(result==ERROR_SUCCESS && type==REG_SZ && fs::is_regular_file(path)) { RegCloseKey(parent); return path; }
        }
        RegCloseKey(parent);
    }
    wchar_t found[32768];
    if(SearchPathW(nullptr,L"python.exe",nullptr,32768,found,nullptr) && fs::is_regular_file(found)) return found;
    throw std::runtime_error("Install Python 3 with Tcl/Tk from python.org, or set TTT2_PYTHON to its python.exe.");
}

// The launcher an update replaces ends first: its window would be shown
// instead of this one's, and its files are about to be replaced.
void wait_for_replaced() {
    const auto pid=environment(L"TTT2_LAUNCHER_AFTER");
    if(pid.empty()) return;
    SetEnvironmentVariableW(L"TTT2_LAUNCHER_AFTER",nullptr);
    if(HANDLE old=OpenProcess(SYNCHRONIZE,FALSE,std::wcstoul(pid.c_str(),nullptr,10))) {
        WaitForSingleObject(old,60000); CloseHandle(old);
    }
}

// The private Python of the launcher's files, as "Start Golden Fist Launcher.cmd"
// gets it ready (downloaded and checked) in a console window of its own.
fs::path release_python(const fs::path& root) {
    if(!environment(L"TTT2_PYTHON").empty()) return python(root);
    const fs::path interpreter=root/"local/windows-tools/python-runtime/python/python.exe";
    if(fs::is_regular_file(interpreter)) return interpreter;
    std::wstring shell=environment(L"ComSpec"); if(shell.empty()) shell=L"cmd.exe";
    std::wstring command=L"cmd.exe /d /c \""+quote((root/L"Start Golden Fist Launcher.cmd").wstring())+L" --check\"";
    STARTUPINFOW startup{}; startup.cb=sizeof(startup); PROCESS_INFORMATION process{};
    if(!CreateProcessW(shell.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NEW_CONSOLE,nullptr,root.c_str(),&startup,&process))
        throw std::runtime_error("Cannot start the Windows command processor to get Python ready.");
    CloseHandle(process.hThread); WaitForSingleObject(process.hProcess,INFINITE);
    DWORD result=1; GetExitCodeProcess(process.hProcess,&result); CloseHandle(process.hProcess);
    if(result || !fs::is_regular_file(interpreter))
        throw std::runtime_error("Golden Fist Launcher could not get its Python ready. Check your internet connection and start it again. "
                                 "Details: "+narrow((root/L"local/windows-bootstrap.log").wstring()));
    return interpreter;
}

void say(std::string_view text, DWORD where=STD_OUTPUT_HANDLE) {
    HANDLE out=GetStdHandle(where); DWORD n=0;
    if(out && out!=INVALID_HANDLE_VALUE) WriteFile(out,text.data(),static_cast<DWORD>(text.size()),&n,nullptr);
}

int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    bool quiet=false; // (asked by a program: errors to standard error, not a window)
    try {
        int argc=0; LPWSTR* argv=CommandLineToArgvW(GetCommandLineW(),&argc);
        if(!argv) throw std::runtime_error("Cannot read launcher arguments.");
        std::vector<std::wstring> args(argv+1,argv+argc); LocalFree(argv);
        quiet=!args.empty() && (args[0]==L"--version" || args[0]==L"--unpack");
        // (Asked by an update, before it puts this .exe in place.)
        if(!args.empty() && args[0]==L"--version") { say("ttt2-launcher " TTT2_LAUNCHER_VERSION "\n"); return 0; }
        wchar_t self[32768]; DWORD n=GetModuleFileNameW(nullptr,self,32768);
        if(!n || n>=32768) throw std::runtime_error("Cannot locate Golden Fist Launcher.");
        const fs::path exe=self;
        const auto files=launcher::payload::own(exe); // (none: a CMake build)
        const bool release=files.has_value();
        // (Tests: the files into a folder, and nothing else.)
        if(args.size()==2 && args[0]==L"--unpack") {
            if(!release) throw std::runtime_error("This launcher holds no files.");
            unpack(*files,args[1]); return 0;
        }
        fs::path folder=exe.parent_path(),script,build=folder,logfile=folder/"launcher.log",interpreter;
        if(release) {
            wait_for_replaced();
            DeleteFileW((folder/(exe.stem().wstring()+L".old.exe")).c_str()); // (what an update replaced)
            folder=files_folder();
            // (Started twice at once: one unpacks, the other then finds the files there.)
            HANDLE lock=CreateMutexW(nullptr,FALSE,launcher::payload::kFilesMutex);
            if(lock) WaitForSingleObject(lock,INFINITE);
            try { unpack(*files,folder); } catch(...) { if(lock) { ReleaseMutex(lock); CloseHandle(lock); } throw; }
            if(lock) { ReleaseMutex(lock); CloseHandle(lock); }
            script=fs::path(folder/"launcher/windows/main.py").make_preferred(); build=folder/"build-windows-tools";
            logfile=fs::path(folder/"local/launcher.log").make_preferred();
            interpreter=release_python(folder);
            SetEnvironmentVariableW(L"TTT2_LAUNCHER_EXE",exe.c_str());
        } else {
            script=folder.parent_path()/"launcher/windows/main.py";
            if(!fs::exists(script)) script=folder/"launcher/windows/main.py";
            if(!fs::exists(script)) throw std::runtime_error("Keep this launcher in the project's build folder, beside the launcher/windows source folder.");
            interpreter=python(folder);
        }
        bool check=false;
        std::wstring command=quote(interpreter.wstring())+L" -u "+quote(script.wstring())+L" --build-dir "+quote(build.wstring());
        for(const auto& arg:args) { command+=L" "+quote(arg); if(arg==L"--check") check=true; }
        SECURITY_ATTRIBUTES sa{sizeof(sa),nullptr,TRUE};
        HANDLE log=CreateFileW(logfile.c_str(),GENERIC_WRITE,FILE_SHARE_READ,&sa,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        HANDLE input=CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,&sa,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(log==INVALID_HANDLE_VALUE || input==INVALID_HANDLE_VALUE) {
            if(log!=INVALID_HANDLE_VALUE) CloseHandle(log); if(input!=INVALID_HANDLE_VALUE) CloseHandle(input);
            throw std::runtime_error("Cannot write "+narrow(logfile.wstring())+".");
        }
        STARTUPINFOW startup{}; startup.cb=sizeof(startup); startup.dwFlags=STARTF_USESTDHANDLES;
        startup.hStdInput=input; startup.hStdOutput=log; startup.hStdError=log;
        PROCESS_INFORMATION process{};
        bool ok=CreateProcessW(interpreter.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,folder.c_str(),&startup,&process);
        CloseHandle(log); CloseHandle(input);
        if(!ok) throw std::runtime_error("Cannot start Python. See "+narrow(logfile.wstring())+".");
        CloseHandle(process.hThread);
        // Report early startup failures, then release the bootstrap executable
        // so Build/Rebuild (or an update of the release .exe) can replace it
        // while the Python window stays open.
        if(WaitForSingleObject(process.hProcess,check ? INFINITE : 2500)==WAIT_TIMEOUT) {
            CloseHandle(process.hProcess); return 0;
        }
        DWORD result=1;
        GetExitCodeProcess(process.hProcess,&result); CloseHandle(process.hProcess);
        if(result && !check) {
            const std::wstring text=L"Golden Fist Launcher stopped with an error. Read "+logfile.wstring()+
                (release ? L"." : L". Python needs Tcl/Tk installed.");
            MessageBoxW(nullptr,text.c_str(),L"Golden Fist Launcher",MB_OK|MB_ICONERROR);
        }
        return static_cast<int>(result);
    } catch(const std::exception& error) {
        if(quiet) say(std::string("ttt2-launcher: ")+error.what()+"\n",STD_ERROR_HANDLE);
        else MessageBoxW(nullptr,wide(error.what()).c_str(),L"Golden Fist Launcher",MB_OK|MB_ICONERROR);
        return 1;
    }
}
