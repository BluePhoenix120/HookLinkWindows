# Windows toolchain locator for the nxnative Windows port.
# Every Apple tool the upstream pipeline calls (xcrun metal / metallib / clang, xcodebuild, sips, ...) is mapped to a Windows equivalent here:
#   Metal compiler      Apple's "Metal Developer Tools for Windows" (metal.exe / metallib.exe, separate ios and macos toolchains)
#   C / ObjC / asm      LLVM for Windows (clang.exe + ld64.lld.exe), targeting arm64-apple-ios with an iPhoneOS SDK taken from Xcode.xip (win/sdk/extract_xip.py)
#   shader translator   the committed .NET DLLs in dm/gfx/tools/dmsh_xlate_bin, run with `dotnet dmsh_xlate.dll` (the Mach-O apphost next to them cannot run here)
# On Linux the same toolchain runs with native builds of LLVM, .NET, spirv-cross and zstd; only the Metal Developer Tools for Windows stay Windows programs, run under Wine (cmd()).
# Paths come from environment variables first, then win/toolchain.json (see win/toolchain.example.json), then well-known install locations.
import glob, json, os, plistlib, shutil, sys
from pathlib import Path

WIN = Path(__file__).resolve().parent
REPO = WIN.parent
CONFIG = WIN / 'toolchain.json'
WINDOWS = os.name == 'nt'
EXE = '.exe' if WINDOWS else ''   # the file name suffix of the native tools (clang, ld64.lld, spirv-cross, ...)

# Deployment targets: the iOS one matches dm/ios/project.yml (Metal 4 needs iOS 26); shaders keep ios_metal.py's -mios-version-min=18.0
IOS_DEPLOYMENT = '26.0'
METAL_MACOS_TARGET = '15.0'   # the Mac shader libraries only feed the Mac-side reflection checks; Xcode's default would be the SDK version


def _cfg():
    try: return json.loads(CONFIG.read_text(encoding='utf-8'))
    except FileNotFoundError: return {}
    except ValueError as e: sys.exit(f'[RED] {CONFIG}: {e}')


def setting(key, default=None):
    """NXW_<KEY> in the environment, else <key> in win/toolchain.json, else default"""
    v = os.environ.get('NXW_' + key.upper())
    if v: return v
    return _cfg().get(key, default)


if not WINDOWS:
    os.environ.setdefault('WINEDEBUG', '-all')   # Wine's own fixme / err lines would fill the shader build's logs
    if setting('wineprefix'): os.environ.setdefault('WINEPREFIX', os.path.expanduser(setting('wineprefix')))   # a prefix of its own keeps the Metal compiler's module cache apart


def wine():
    """The wine command that runs the Windows Metal tools off Windows: NXW_WINE / "wine" in win/toolchain.json, else wine on PATH"""
    return setting('wine') or shutil.which('wine')


def cmd(tool):
    """The argv prefix that runs a tool: a Windows program (.exe) goes through Wine off Windows, as ['wine', tool]; anything else runs as it is"""
    if not WINDOWS and Path(tool).suffix.lower() == '.exe': return [wine() or 'wine', str(tool)]
    return [str(tool)]


def _first(paths):
    for p in paths:
        if p and Path(p).exists(): return Path(p)
    return None


def metal_tools_root():
    """The Metal Developer Tools for Windows install folder (holds ios/ and macos/ toolchains)"""
    cands = [setting('metal_tools')]
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'), os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        cands += sorted(glob.glob(os.path.join(base, 'Metal Developer Tools*')), reverse=True)
    return _first(cands)


def metal_tool(sdk, name):
    """metal.exe / metallib.exe of the iOS (sdk iphoneos) or macOS (sdk macosx) toolchain"""
    root = metal_tools_root()
    if not root: return None
    sub = 'ios' if sdk.startswith('iphone') else 'macos'
    # 4.x shipped one toolchain per OS (ios/, macos/); 5.x and 6.x ship one for every target in bin/ (the -target triple picks the OS)
    for pat in (f'{sub}/bin/{name}.exe', f'{sub}/**/bin/{name}.exe', f'**/{sub}/**/{name}.exe', f'bin/{name}.exe'):
        hits = sorted(glob.glob(str(root / pat), recursive=True))
        if hits: return Path(hits[0])
    return None


def llvm_bin():
    cands = [setting('llvm')]
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),):
        cands.append(os.path.join(base, 'LLVM'))
    root = _first(cands)
    if root and (root / 'bin').is_dir(): return root / 'bin'
    c = shutil.which('clang')
    return Path(c).parent if c else None


def llvm_tool(name):
    b = llvm_bin()
    if b and (b / f'{name}{EXE}').exists(): return b / f'{name}{EXE}'
    w = shutil.which(name)
    return Path(w) if w else None


def _ios_sdk_valid(path):
    """Reject old/partial SDKs: Metal 4 requires iOS 26+, headers and frameworks."""
    try:
        path = Path(path)
        if not path.is_dir() or not path.name.lower().startswith('iphoneos') or path.suffix.lower() != '.sdk':
            return False
        version, _ = sdk_settings(path)
        major = str(version).split('.', 1)[0]
        return (major.isdigit() and int(major) >= 26
                and (path / 'usr' / 'include').is_dir()
                and (path / 'System' / 'Library' / 'Frameworks').is_dir())
    except (OSError, ValueError, TypeError):
        return False


def _ios_sdk_override(value):
    """Resolve SDK paths in local toolchain.json relative to that file when needed.

    ${PROJECT} is the top-level checkout; ${ENGINE} is the nxnative engine.
    Absolute paths remain supported. No configuration file is rewritten.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    value = os.path.expandvars(value.strip())
    project = REPO.parent if REPO.name.lower() == 'engine' else REPO
    for marker, base in (('${PROJECT}', project), ('${ENGINE}', REPO), ('${WIN}', WIN)):
        if value == marker:
            return base
        if value.startswith(marker + '/') or value.startswith(marker + chr(92)):
            return base / value[len(marker) + 1:]
    path = Path(value).expanduser()
    return path if path.is_absolute() else WIN / path


def _ios_sdk_search_roots():
    """Bounded relocation search: this checkout, then nearby source checkouts.

    No recursive scanning of entire drives, home directories or build workspaces.
    The relative patterns describe a checkout layout, not a particular drive or name.
    """
    project = REPO.parent if REPO.name.lower() == 'engine' else REPO
    roots = [WIN / 'sdk' / 'out', project / 'win' / 'sdk' / 'out',
             project / 'engine' / 'win' / 'sdk' / 'out']
    try:
        siblings = sorted((p for p in project.parent.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
    except OSError:
        siblings = []
    for sibling in siblings:
        roots.extend((sibling / 'win' / 'sdk' / 'out', sibling / 'engine' / 'win' / 'sdk' / 'out'))
    seen = set()
    for root in roots:
        key = os.path.normcase(str(root.resolve(strict=False)))
        if key not in seen:
            seen.add(key)
            yield root


def ios_sdk_details():
    """Return (SDK, source, warnings), preferring valid overrides over discovery.

    A stale local path never disables discovery. SDK directories must be complete
    and have a reported iOS version of at least 26.
    """
    warnings = []
    explicit = [('NXW_IOS_SDK', os.environ.get('NXW_IOS_SDK')),
                ('toolchain.json', _cfg().get('ios_sdk'))]
    for name, value in explicit:
        candidate = _ios_sdk_override(value)
        if candidate is None:
            continue
        if _ios_sdk_valid(candidate):
            return candidate, name, warnings
        warnings.append(f'{name} ios_sdk is missing, incomplete or older than iOS 26: {candidate}')
    for root in _ios_sdk_search_roots():
        if not root.is_dir():
            continue
        try:
            candidates = [p for p in root.rglob('iPhoneOS*.sdk') if p.is_dir()]
        except OSError:
            continue
        # Prefer the most recent version within each SDK output tree.
        def version_key(p):
            version, _ = sdk_settings(p)
            parts = str(version).split('.')
            return tuple(int(v) if v.isdigit() else 0 for v in (parts + ['0', '0'])[:3])
        for candidate in sorted(candidates, key=version_key, reverse=True):
            if _ios_sdk_valid(candidate):
                return candidate, 'auto-discovered near this checkout', warnings
    return None, 'not found', warnings


def ios_sdk():
    """Validated iPhoneOS SDK, independent of checkout location."""
    return ios_sdk_details()[0]


def sdk_settings(sdk):
    """(version, build version) of an SDK folder, from SDKSettings.json / SDKSettings.plist and System/Library/CoreServices/SystemVersion.plist"""
    ver = build = ''
    js = Path(sdk) / 'SDKSettings.json'
    if js.exists():
        try: ver = json.loads(js.read_text(encoding='utf-8')).get('Version', '')
        except ValueError: pass
    pl = Path(sdk) / 'SDKSettings.plist'
    if not ver and pl.exists():
        with open(pl, 'rb') as f: ver = plistlib.load(f).get('Version', '')
    sv = Path(sdk) / 'System/Library/CoreServices/SystemVersion.plist'
    if sv.exists():
        with open(sv, 'rb') as f: build = plistlib.load(f).get('ProductBuildVersion', '')
    return ver, build


def dotnet():
    w = shutil.which('dotnet') or (None if WINDOWS else _first([Path.home() / '.dotnet/dotnet']))   # dotnet-install.sh puts it in ~/.dotnet, which upstream's TOOL_PATHS also searches
    return Path(w) if w else None


def xlate_dll():
    return REPO / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate.dll'


def tool_on_path(name):
    """A native build of a cross-platform tool (spirv-cross, glslangValidator, zstd): win/toolchain.json may name its folder"""
    d = setting(name.replace('-', '_') + '_dir')
    if d:
        p = Path(d) / f'{name}{EXE}'
        if p.exists(): return p
    w = shutil.which(name)
    return Path(w) if w else None


def letter_font():
    """The letters of the button-icon font (make_ext_font.py; upstream: macOS's Arial Rounded Bold): LETTER_FONT, toolchain.json letter_font, else Windows' Arial Rounded MT Bold or Arial Bold"""
    fonts = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    linux = ['/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']   # Liberation Sans has Arial's metrics
    return _first([os.environ.get('LETTER_FONT'), setting('letter_font'), fonts / 'ARLRDBD.TTF', fonts / 'arialbd.ttf', fonts / 'arial.ttf'] + ([] if WINDOWS else linux))


def std_font():
    """The shared-font stand-in (standard.ttf). Upstream copies macOS's Arial Unicode; on Windows: STD_FONT, toolchain.json std_font, else a broad-coverage Windows font
    (on Linux DejaVu Sans, a TTF with broad coverage but no CJK: set STD_FONT for a game whose text needs it)"""
    windir = os.environ.get('WINDIR', r'C:\Windows')
    linux = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf']
    return _first([os.environ.get('STD_FONT'), setting('std_font'), os.path.join(windir, 'Fonts', 'ARIALUNI.TTF'), os.path.join(windir, 'Fonts', 'arial.ttf')] + ([] if WINDOWS else linux))
