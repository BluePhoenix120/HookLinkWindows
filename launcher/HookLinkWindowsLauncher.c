/* Small native Windows GUI bootstrap for the source version of HookLinkWindows.
   This launcher does not embed Python. A full standalone GUI is built by the
   accompanying PyInstaller GitHub Actions workflow on Windows. */

typedef unsigned int DWORD;
typedef unsigned short wchar_t;
typedef int BOOL;
typedef void *HWND;
typedef void *HINSTANCE;
typedef const wchar_t *LPCWSTR;
typedef wchar_t *LPWSTR;
#define DLLIMPORT __declspec(dllimport)
DLLIMPORT DWORD __stdcall GetModuleFileNameW(void *, LPWSTR, DWORD);
DLLIMPORT DWORD __stdcall GetFileAttributesW(LPCWSTR);
DLLIMPORT void __stdcall ExitProcess(unsigned int);
DLLIMPORT HINSTANCE __stdcall ShellExecuteW(HWND, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, int);
DLLIMPORT int __stdcall MessageBoxW(HWND, LPCWSTR, LPCWSTR, unsigned int);

static wchar_t module_path[32768];
static wchar_t script_path[32768];
static wchar_t params[32768];
static unsigned int length_w(const wchar_t *s) { unsigned int i=0; while(s[i])++i; return i; }
static void append_w(wchar_t *dest, const wchar_t *from, unsigned int max) {
    unsigned int i=length_w(dest), j=0;
    while(from[j] && i+1<max) dest[i++]=from[j++];
    dest[i]=0;
}
static int launch(const wchar_t *interpreter, const wchar_t *directory) {
    HINSTANCE h=ShellExecuteW(0,L"open",interpreter,params,directory,1);
    return (unsigned long long)h > 32ULL;
}
void entry(void) {
    DWORD n=GetModuleFileNameW(0,module_path,32768);
    if(!n || n>=32767) {
        MessageBoxW(0,L"Unable to locate HookLinkWindows.exe.",L"HookLinkWindows",0x10);
        ExitProcess(1);
    }
    unsigned int end=length_w(module_path);
    while(end && module_path[end-1]!=L'\\' && module_path[end-1]!=L'/')--end;
    if(!end) {
        MessageBoxW(0,L"Unable to determine the installation folder.",L"HookLinkWindows",0x10);
        ExitProcess(1);
    }
    module_path[end-1]=0;
    script_path[0]=0;
    append_w(script_path,module_path,32768);
    append_w(script_path,L"\\win\\hooklink_gui.pyw",32768);
    if(GetFileAttributesW(script_path)==0xFFFFFFFFUL) {
        MessageBoxW(0,L"The source GUI is missing. Place HookLinkWindows.exe in the root of the full HookLinkWindows checkout, alongside the win directory.",L"HookLinkWindows — Missing files",0x30);
        ExitProcess(2);
    }
    params[0]=L'"';params[1]=0;
    append_w(params,script_path,32768);
    append_w(params,L"\"",32768);
    if(launch(L"pyw.exe",module_path) || launch(L"pythonw.exe",module_path) ||
       launch(L"py.exe",module_path) || launch(L"python.exe",module_path)) ExitProcess(0);
    MessageBoxW(0,L"Python 3 was not found. Install Python 3 with the Windows launcher, then double-click HookLinkWindows.exe again. For a GUI that does not require Python, use the standalone executable created by the GitHub Actions workflow.",L"HookLinkWindows — Python required",0x30);
    ExitProcess(3);
}
