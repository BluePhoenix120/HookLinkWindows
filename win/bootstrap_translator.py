#!/usr/bin/env python3
"""HookLinkWindows Alpha V1.0.0: guarded, source-only Windows translator setup.

--check: read-only prerequisite, source, and shader-chain inspection.
--install --accept-new-chain: build the managed translator from bundled source,
  verify its embedded source digest, then synchronize a LOCAL shader-chain lock
  and header. This intentionally changes the shader-chain ID and invalidates
  caches from another toolchain. Never silently run this on a working setup.

No game assets, existing IPA, or previously compiled shader archives are edited.
Run the clean-room test before presenting this as a supported installer.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


OUTPUTS = (
    'dmsh_xlate.dll', 'dmsh_xlate.deps.json', 'dmsh_xlate.runtimeconfig.json',
    'Ryujinx.Common.dll', 'Ryujinx.Graphics.Shader.dll', 'Spv.Generator.dll',
)

# The original Alpha 1.0.0 bootstrap recognized only HookLink 2.0.
# Keep the check strict, but also accept the explicitly imported X2 engine.
# No branch HEAD or Git checkout is used to infer the engine version.
_SUPPORTED_ENGINE_BASES = {
    ('2.0', '3a28152fe7052c9f45ede460022d39be6c91e3cf'),
    ('3.0', '7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf'),
}
_PINNED_REPO = 'https://github.com/dsi-hub/nxnative.git'


def verify_source_identity(root: Path) -> tuple[str, str]:
    """Validate the HookLink release and recorded NXNative revision as a pair.

    Deliberately fail closed when metadata is missing, mismatched or unknown,
    rather than treating any VERSION or arbitrary engine SHA as approved.
    """
    version_file = root / 'VERSION'
    need(version_file.is_file(), 'Missing HookLink VERSION file')
    version = version_file.read_text(encoding='utf-8-sig').strip()
    pin_file = root / 'ENGINE_PIN.json'
    need(pin_file.is_file(), 'Missing ENGINE_PIN.json: cannot verify the bundled NXNative engine')
    try:
        meta = json.loads(pin_file.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError, OSError) as exc:
        raise RuntimeError(f'Invalid ENGINE_PIN.json: {exc}') from exc
    need(isinstance(meta, dict), 'ENGINE_PIN.json must contain an object')
    engine_sha = meta.get('nxnative_commit')
    need(isinstance(engine_sha, str), 'NXNative pin must be a commit SHA string')
    need(meta.get('nxnative_repo') == _PINNED_REPO,
         'Unexpected NXNative source repository in ENGINE_PIN.json')
    need(meta.get('engine_location') == 'engine/',
         'Unexpected NXNative engine directory in ENGINE_PIN.json')
    need(meta.get('hooklink_base') == version,
         f'HookLink VERSION {version!r} disagrees with ENGINE_PIN.json hooklink_base')
    need((version, engine_sha) in _SUPPORTED_ENGINE_BASES,
         f'Unsupported HookLink {version!r} / NXNative {str(engine_sha)[:12]!r} pair; '
         'use an unmodified complete HookLinkWindows release')

    if version == '3.0':
        manifest = root / 'ENGINE_PIN_FILES.json'
        need(manifest.is_file(), 'X2 engine provenance manifest missing (ENGINE_PIN_FILES.json)')
        try:
            record = json.loads(manifest.read_text(encoding='utf-8-sig'))
        except (ValueError, UnicodeError, OSError) as exc:
            raise RuntimeError(f'Invalid ENGINE_PIN_FILES.json: {exc}') from exc
        need(isinstance(record, dict)
             and record.get('nxnative_commit') == engine_sha
             and record.get('nxnative_repo') == _PINNED_REPO
             and isinstance(record.get('changed_paths'), list)
             and len(record['changed_paths']) == 25,
             'X2 engine manifest does not match pinned revision; use the complete release')
    print(f'PASS: HookLink {version}, pinned NXNative {engine_sha}', flush=True)
    return version, engine_sha



def need(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def hidden_process_options() -> dict:
    """Keep CLI children silent when the application is launched by pythonw/PyInstaller."""
    if os.name != 'nt':
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {'creationflags': subprocess.CREATE_NO_WINDOW, 'startupinfo': startup}


def isolated_dotnet_build_environment() -> dict[str, str]:
    """Prevent MSBuild/Roslyn background servers from opening their own consoles.

    Only applies to the shader translator build, not system-wide settings.
    """
    env = os.environ.copy()
    env['DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER'] = '1'
    env['MSBUILDDISABLENODEREUSE'] = '1'
    return env


def execute(args, *, env=None, timeout=180, cwd=None, verbose=False) -> str:
    argv = list(map(str, args))
    if verbose:
        print('RUN:', ' '.join(argv), flush=True)
    opts = hidden_process_options()
    result = subprocess.run(argv, env=env, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors='replace',
                            timeout=timeout, **opts)
    if verbose or result.returncode:
        print(result.stdout[-12000:], flush=True)
    need(result.returncode == 0, f'Command failed ({result.returncode}): {argv[0]}')
    return result.stdout.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as reader:
        for block in iter(lambda: reader.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_sha(project: Path) -> str:
    return hashlib.sha256((project / 'Program.cs').read_bytes() +
                          (project / 'dmsh_xlate.csproj').read_bytes()).hexdigest()[:16]


def locate_spirv(toolchain, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        need(p.is_file(), f'SPIRV-Cross missing: {p}')
        return p.resolve()
    if os.environ.get('SPIRV_CROSS'):
        p = Path(os.environ['SPIRV_CROSS'])
        need(p.is_file(), f'SPIRV_CROSS points to missing file: {p}')
        return p.resolve()
    if getattr(toolchain, 'tool_on_path', None):
        p = toolchain.tool_on_path('spirv-cross')
        if p and Path(p).is_file():
            return Path(p).resolve()
    p = shutil.which('spirv-cross')
    if p:
        return Path(p).resolve()
    sdk_root = Path(os.environ.get('SystemDrive', 'C:') + r'\VulkanSDK')
    matches = sorted(sdk_root.glob('*/Bin/spirv-cross.exe'))
    need(bool(matches), 'SPIRV-Cross missing. Install Vulkan SDK or specify --spirv-cross <path>')
    return matches[-1].resolve()


def paths(root: Path) -> dict[str, Path]:
    eng = root / 'engine'
    return {'root': root, 'engine': eng,
            'project': eng / 'dm/gfx/tools/dmsh_xlate',
            'dll_dir': eng / 'dm/gfx/tools/dmsh_xlate_bin',
            'lock': eng / 'dm/gfx/tools/dmsh_chain.lock',
            'header': eng / 'dm/gfx/nvn/dmsh_chain.h',
            'chain': eng / 'dm/gfx/tools/dmsh_chain.py',
            'tool_lock': eng / 'dm/gfx/tools/tool_lock.py',
            'shim': eng / 'win/pyshim',
            'toolchain': eng / 'win/toolchain.py'}


def inspect(root: Path, explicit_spirv: str | None) -> tuple[dict, dict]:
    need(os.name == 'nt', 'Native Windows required; do not run through WSL')
    p = paths(root)
    for key in ('project', 'lock', 'header', 'chain', 'tool_lock', 'shim', 'toolchain'):
        need(p[key].is_dir() if key in ('project', 'shim') else p[key].is_file(),
             f'Missing source: {p[key]}')
    for f in ('Program.cs', 'dmsh_xlate.csproj'):
        need((p['project'] / f).is_file(), f'Missing translator source: {f}')
    need((p['shim'] / 'sitecustomize.py').is_file(), 'Windows compatibility shim missing')
    verify_source_identity(root)
    expected = source_sha(p['project'])
    print('Translator source fingerprint:', expected)
    dotnet = shutil.which('dotnet')
    need(dotnet is not None, '.NET 10 SDK missing; install .NET 10 SDK x64')
    sdks = execute([dotnet, '--list-sdks'])
    need(re.search(r'(?m)^10\.', sdks) is not None,
         '.NET 10 SDK not found; installed SDKs:\n' + sdks)
    print('PASS: .NET 10 SDK found')
    sys.path.insert(0, str(p['engine'] / 'win'))
    import toolchain
    spirv = locate_spirv(toolchain, explicit_spirv)
    print('SPIRV-Cross:', spirv)
    for sdk in ('iphoneos', 'macosx'):
        metal = toolchain.metal_tool(sdk, 'metal')
        need(metal is not None and Path(metal).is_file(),
             f'Apple Metal compiler missing for {sdk}; install licensed Windows Metal Developer Tools')
        version = execute([metal, '--version'])
        need('Apple metal version' in version,
             f'Unexpected Metal compiler version: {version[:200]}')
        print(f'PASS: {sdk} Metal compiler:', version.splitlines()[0])
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(p['shim'])] +
                            [x for x in env.get('PYTHONPATH', '').split(os.pathsep) if x])
    env['PYTHONUTF8'] = '1'
    env['SPIRV_CROSS'] = str(spirv)
    env.pop('XLATE', None)
    info = {'dotnet': dotnet, 'env': env, 'spirv': spirv, 'source_sha': expected}
    dll = p['dll_dir'] / 'dmsh_xlate.dll'
    if dll.is_file():
        result = execute([dotnet, dll, '--source-sha'])
        need(result.splitlines()[-1].strip() == expected,
             'Existing DLL source differs from bundled project; do not replace it blindly')
        print('PASS: Installed translator has matching embedded source')
        try:
            execute([sys.executable, '-B', p['tool_lock'], '--check-tools'], env=env)
            chain = execute([sys.executable, '-B', p['chain']], env=env).splitlines()[-1].strip()
            header = p['header'].read_text(encoding='utf-8')
            need(re.fullmatch(r'[0-9a-f]{12}', chain) is not None, 'Malformed shader-chain ID')
            need(f'#define DMSH_CHAIN "{chain}"' in header, 'Header does not match chain')
            info['ready'] = True
            info['chain'] = chain
            print('PASS: Tool lock and header agree:', chain)
        except Exception as exc:
            info['ready'] = False
            print('NOTE: Installed translator is present, but shader chain needs setup:', exc)
    else:
        info['ready'] = False
        print('NOTE: Managed translator is not built; this is expected on a fresh checkout')
    return p, info


def ensure_clean_tracked_state(p: dict) -> None:
    if not (p['root'] / '.git').exists():
        return  # Source ZIP with no Git metadata
    git = shutil.which('git')
    if not git:
        return
    target = ['engine/dm/gfx/tools/dmsh_chain.lock', 'engine/dm/gfx/nvn/dmsh_chain.h']
    for args in (['diff', '--quiet', '--'] + target,
                 ['diff', '--cached', '--quiet', '--'] + target):
        result = subprocess.run([git, '-C', str(p['root'])] + args,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                **hidden_process_options())
        need(result.returncode == 0,
             'Shader lock/header already have local Git changes; preserve them before bootstrapping')


def install(root: Path, explicit_spirv: str | None, consent: bool) -> None:
    p, info = inspect(root, explicit_spirv)
    if info['ready']:
        print('PASS: Translator already installed and verified; no files changed')
        return
    need(consent, 'Refusing to generate a NEW shader chain without --accept-new-chain')
    ensure_clean_tracked_state(p)
    maint = root.parent / '.HookLinkWindows-Maintenance'
    maint.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix='alpha100-bootstrap-', dir=str(maint)))
    output = workspace / 'publish'
    backup = workspace / 'backup'
    backup.mkdir()
    originals = {name: p[name].read_bytes() for name in ('lock', 'header')}
    for name, data in originals.items():
        (backup / p[name].name).write_bytes(data)
    previous_dll_dir = p['dll_dir'].is_dir()
    if previous_dll_dir:
        shutil.copytree(p['dll_dir'], backup / 'dmsh_xlate_bin')
    changed = False
    try:
        cmd = [info['dotnet'], 'publish', p['project'] / 'dmsh_xlate.csproj',
               '-c', 'Release', '-r', 'win-x64', '--self-contained', 'false',
               '-p:PublishAot=false', '-p:PublishSingleFile=false',
               '-p:PublishTrimmed=false', '-p:UseSharedCompilation=false',
               '-o', output, '-nologo']
        execute(cmd, env=isolated_dotnet_build_environment(), timeout=600, verbose=True)
        for name in OUTPUTS:
            need((output / name).is_file(), f'Publish missing dependency: {name}')
        embedded = execute([info['dotnet'], output / 'dmsh_xlate.dll', '--source-sha'])
        need(embedded.splitlines()[-1].strip() == info['source_sha'],
             'New translator does not embed the bundled source fingerprint')
        print('PASS: Fresh managed translator embeds expected source fingerprint')
        # Install all DLL dependencies as a unit, retaining anything else already present.
        p['dll_dir'].mkdir(parents=True, exist_ok=True)
        changed = True
        for name in OUTPUTS:
            shutil.copy2(output / name, p['dll_dir'] / name)
        execute([sys.executable, '-B', p['tool_lock'], '--update-lock'],
                env=info['env'], verbose=True)
        ver = execute([sys.executable, '-B', p['chain'], '--header'],
                      env=info['env'], verbose=True)
        ver = ver.splitlines()[-1].strip()
        need(re.fullmatch('[0-9a-f]{12}', ver) is not None, f'Bad chain version: {ver}')
        execute([sys.executable, '-B', p['tool_lock'], '--check-tools'],
                env=info['env'], verbose=True)
        current = execute([sys.executable, '-B', p['chain']], env=info['env']).splitlines()[-1].strip()
        need(current == ver, 'The regenerated chain is unstable')
        need(f'#define DMSH_CHAIN "{ver}"' in p['header'].read_text(encoding='utf-8'),
             'The regenerated host header does not match the lock')
        print('PASS: Translator and Windows shader chain verified:', ver)
        print('IMPORTANT: A new chain needs freshly compiled iOS shaders.')
        print('LOCAL CHANGES: engine/dm/gfx/tools/dmsh_chain.lock, engine/dm/gfx/nvn/dmsh_chain.h')
        print('BACKUP:', backup)
    except BaseException:
        if changed:
            for name, data in originals.items():
                p[name].write_bytes(data)
            if p['dll_dir'].exists():
                shutil.rmtree(p['dll_dir'])
            if previous_dll_dir:
                shutil.copytree(backup / 'dmsh_xlate_bin', p['dll_dir'])
            print('ROLLBACK: Translator directory, chain lock, and header restored', file=sys.stderr)
        print('Diagnostic workspace preserved:', workspace, file=sys.stderr)
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument('--spirv-cross', default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Read-only prerequisites and existing-chain verification')
    mode.add_argument('--install', action='store_true', help='Build and locally synchronize translator tools')
    ap.add_argument('--accept-new-chain', action='store_true',
                    help='Explicitly allow regenerating tracked chain lock/header on the LOCAL checkout')
    args = ap.parse_args()
    root = args.root.resolve()
    if args.check:
        _, info = inspect(root, args.spirv_cross)
        print('STATUS: READY' if info['ready'] else 'STATUS: BOOTSTRAP NEEDED')
        print('PASS: Read-only inspection; no source or build files changed')
    else:
        install(root, args.spirv_cross, args.accept_new_chain)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
