"""Stdlib-only helpers for the HookLinkWindows NUP build interface."""
from __future__ import annotations

from dataclasses import dataclass, replace
import copy
from pathlib import Path
from typing import Callable
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

PACKAGE_APP_ONLY = "app_only"
PACKAGE_FULL = "full"
PACKAGE_MODES = (PACKAGE_APP_ONLY, PACKAGE_FULL)

BUNDLE_RE = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
SHADER_RE = re.compile(r"b-[0-9a-f]{8,32}\.img(?:\.img\.\d+)?$", re.I)
OOT_RUNTIME_REQUIRED = {'DM_NVN_ENC_THREAD': '0', 'DM_NVN_BARRIER': 'full',
                        'DM_PSO_MTL4': '0', 'DM_MSL_DIR': '.'}
SAFE_APP_DISPLAY_NAME = 'HookLinkWindows'


@dataclass(frozen=True)
class BuildConfig:
    root: Path
    input_path: Path
    work_dir: Path
    env_file: Path
    output_ipa: Path
    bundle_id: str
    workers: int = 61
    metal_workers: int = 24  # independent physical RAM-aware Metal compile concurrency
    allow_damaged: bool = True
    allow_other_metal: bool = True
    entitlements: bool = True
    reuse_shader_work: Path | None = None  # completed old WORK DIR, read-only: refuse on any mismatch
    native_app_only: bool = False          # experimental direct split-data builder


@dataclass(frozen=True)
class BuildPlan:
    mode: str
    final_ipa: Path
    builder_ipa: Path
    transfer_dir: Path | None
    command: list[str]
    native_split: bool = False


def default_output_name(mode: str) -> str:
    if mode == PACKAGE_APP_ONLY:
        return 'HookLinkWindows-AppOnly.ipa'
    if mode == PACKAGE_FULL:
        return 'HookLinkWindows-Full.ipa'
    raise ValueError('Unknown IPA packaging mode.')


def make_build_plan(c: BuildConfig, mode: str, token: str = 'preview', python: str | None = None) -> BuildPlan:
    verify_build_config(c)
    if mode not in PACKAGE_MODES:
        raise ValueError('Choose either app-only or full IPA packaging.')
    native = mode == PACKAGE_APP_ONLY and c.native_app_only
    if mode == PACKAGE_FULL:
        builder = c.output_ipa
        transfer = None
    elif native:
        builder = c.output_ipa
        transfer = c.output_ipa.with_name(c.output_ipa.stem + '-iPhone-Files')
    else:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', token):
            raise ValueError('Invalid staging token.')
        builder = c.work_dir / '.hooklink-staging' / f'{token}-Full.ipa'
        if builder.resolve() == c.output_ipa.resolve():
            raise ValueError('Final IPA must not overwrite the staging IPA.')
        transfer = c.output_ipa.with_name(c.output_ipa.stem + '-iPhone-Files')
    command = make_build_command(replace(c, output_ipa=builder), python=python, split_data_dir=transfer if native else None)
    return BuildPlan(mode, c.output_ipa, builder, transfer, command, native)


def shader_chain_from_ipa(source: Path) -> str | None:
    names = inspect_ipa(source)['external_names']
    chains = {m.group(1).lower() for n in names if (m := re.search(r'/msl/b-([0-9a-f]{8,32})\.img(?:\.img\.\d+)?$', n, re.I))}
    if len(chains) > 1:
        raise ValueError('Multiple shader chains found in the full IPA; choose the correct one manually.')
    return next(iter(chains), None)


def read_host_shader_chain(header: Path) -> str:
    """Use the checked toolchain's host chain ID when the IPA has no embedded MSL image."""
    text = header.read_text(encoding='utf-8')
    ids = re.findall(r'^\s*#define\s+DMSH_CHAIN\s+"([0-9a-f]{12})"\s*$', text, re.M)
    if len(ids) != 1:
        raise ValueError(f'Cannot identify one host shader chain from {header}')
    return ids[0]


def verified_shader_chain_from_ipa(source: Path, host_header: Path) -> str:
    host_chain = read_host_shader_chain(host_header)
    embedded_chain = shader_chain_from_ipa(source)
    if embedded_chain is not None and embedded_chain != host_chain:
        raise ValueError(f'IPA shader chain {embedded_chain} disagrees with host header {host_chain}')
    return host_chain


def find_transfer_sources(work_dir: Path, env_file: Path, chain: str | None = None,
                          *, donor_shader_work: Path | None = None,
                          donor_verified: bool = False) -> dict[str, Path]:
    roms = sorted((work_dir / 'extract').glob('*/RomFS.img'))
    if len(roms) != 1:
        raise ValueError(f'Expected one extracted RomFS.img, found {len(roms)}; inspect {work_dir / "extract"}.')
    shaders = sorted((work_dir / 'shader' / 'ios').glob('b-*.img'))
    if chain:
        shaders = [q for q in shaders if q.name.lower() == f'b-{chain.lower()}.img']
    if not shaders and donor_shader_work is not None:
        if not donor_verified or not chain:
            raise ValueError('External shader archive requires a verified donor and exact shader-chain ID.')
        # The builder already compared package CONTENT, toolchain, game, profile,
        # pulling policy and tables. Only trust the donor on that explicit success.
        shader = donor_shader_work / 'shader' / 'ios' / f'b-{chain}.img'
        if shader.is_file():
            shaders = [shader]
    if len(shaders) != 1:
        raise ValueError(f'Expected one shader archive for this build, found {len(shaders)} matching candidates; inspect {work_dir / "shader" / "ios"} and the verified donor.')
    for file in (roms[0], shaders[0], env_file):
        if not file.is_file() or file.stat().st_size == 0:
            raise ValueError(f'Required iPhone transfer file missing or empty: {file}')
    return {'RomFS.img': roms[0], shaders[0].name: shaders[0], 'env.txt': env_file}


def prepare_transfer_folder(work_dir: Path, env_file: Path, output_dir: Path,
                            chain: str | None = None,
                            reporter: Callable[[str], None] | None = None,
                            *, donor_shader_work: Path | None = None,
                            donor_verified: bool = False) -> Path:
    """Prepare ready-to-copy files; hard-link where possible to avoid duplicating huge assets.

    Does not modify source images. If the transfer directory exists, select a numbered
    sibling rather than overwriting another run's game files.
    """
    reporter = reporter or (lambda _: None)
    sources = find_transfer_sources(work_dir, env_file, chain,
                                    donor_shader_work=donor_shader_work,
                                    donor_verified=donor_verified)
    dest = output_dir
    suffix = 2
    while dest.exists() or dest.with_name(dest.name + '.building').exists():
        dest = output_dir.with_name(output_dir.name + f'-{suffix}')
        suffix += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + '.building')
    temporary.mkdir()
    try:
        for name, source in sources.items():
            target = temporary / name
            if name == 'env.txt':
                shutil.copy2(source, target)
            elif donor_shader_work is not None and source.resolve().is_relative_to(donor_shader_work.resolve()):
                # NEVER hard-link a reusable donor: edits to the transfer folder
                # would otherwise mutate the supposedly read-only old archive.
                reporter('Copying verified donor archive without hard-linking: ' + name)
                shutil.copy2(source, target)
            else:
                try:
                    os.link(source, target)
                    reporter('Linked transfer file without duplicating data: ' + name)
                except OSError:
                    reporter('Hard links unavailable; copying transfer file: ' + name)
                    shutil.copy2(source, target)
            if source.stat().st_size != target.stat().st_size:
                raise ValueError('Transfer file size differs from source: ' + name)
        details = ('iPhone file transfer\n\n'
                   '1. Install and sign the app-only IPA using your sideloading tool.\n'
                   '2. Open Apple Devices > Files and select the installed app.\n'
                   '3. Transfer RomFS.img, the b-*.img shader archive, and env.txt from this folder into the app Documents directory.\n'
                   '4. Use the increased-memory-limit entitlement if required for your device.\n\n'
                   'Keep these game-derived files private. They are not part of the public source repository.\n')
        (temporary / 'TRANSFER_README.txt').write_text(details, encoding='utf-8')
        temporary.rename(dest)
        return dest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_build_config(c: BuildConfig) -> None:
    if not (c.root / 'win' / 'build_ipa_windows.py').is_file():
        raise ValueError('Windows builder not found inside the selected project root.')
    if not c.input_path.is_file() or c.input_path.suffix.lower() != '.nup':
        raise ValueError('Select a supported .nup file. Other input formats are not supported.')
    if not c.env_file.is_file():
        raise ValueError('Runtime settings file not found. Select a configuration file or use the included preset.')
    if not BUNDLE_RE.fullmatch(c.bundle_id):
        raise ValueError('Bundle ID must have at least two dot-separated components, such as PhoenixNetwork.HookLinkWindows.')
    if not 1 <= c.workers <= 61:
        raise ValueError('Worker count must be between 1 and 61 on Windows.')
    if not 1 <= c.metal_workers <= 61:
        raise ValueError('Metal compiler count must be between 1 and 61 on Windows.')
    if c.output_ipa.suffix.lower() != '.ipa':
        raise ValueError('Output path must end with .ipa.')
    if c.output_ipa.resolve() == c.input_path.resolve():
        raise ValueError('Output cannot overwrite the input game file.')
    if c.work_dir.resolve() in (c.input_path.resolve(), c.root.resolve()):
        raise ValueError('Choose a separate build work directory.')
    if c.reuse_shader_work is not None:
        if not c.reuse_shader_work.is_dir():
            raise ValueError('The existing shader work folder does not exist; select a completed WORK directory.')
        donor = c.reuse_shader_work.resolve()
        work = c.work_dir.resolve()
        out = c.output_ipa.resolve()
        if work == donor or donor in work.parents or work in donor.parents:
            raise ValueError('Existing shader work folder and new build directory must not overlap.')
        if out == donor or donor in out.parents:
            raise ValueError('Output IPA must not be written inside the existing shader work folder.')


def make_build_command(c: BuildConfig, python: str | None = None, split_data_dir: Path | None = None) -> list[str]:
    verify_build_config(c)
    cmd = [python or sys.executable, str(c.root / 'win' / 'build_ipa_windows.py'), str(c.input_path)]
    cmd += ['--work-dir', str(c.work_dir), '--env-file', str(c.env_file), '--bundle-id', c.bundle_id,
            '--gpu', 'none', ('--split-data=' + str(split_data_dir)) if split_data_dir is not None else '--no-split-data',
            '--progress', 'lines', '-o', str(c.output_ipa)]
    cmd += ['--entitlements' if c.entitlements else '--no-entitlements']
    if c.allow_damaged:
        cmd.append('--allow-damaged')
    if c.allow_other_metal:
        cmd.append('--allow-other-metal')
    return cmd


def make_build_environment(c: BuildConfig) -> dict[str, str]:
    env = os.environ.copy()
    env['J'] = str(c.workers)
    env['NXW_METAL_J'] = str(c.metal_workers)
    env['NXW_METAL_MIN_FREE_GB'] = '8'
    env['DMSH_PROCS'] = '0'  # Avoid the unsupported Unix 'fork' context on Windows.
    if c.reuse_shader_work is not None:
        env['NXW_REUSE_SHADER_WORK'] = str(c.reuse_shader_work.resolve())
    else:
        env.pop('NXW_REUSE_SHADER_WORK', None)
    env.setdefault('PYTHONUTF8', '1')
    return env


def _runtime_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            values[k.strip()] = v.strip()
    return values


def oot_runtime_errors(path: Path) -> list[str]:
    """Release-blocking mismatches for this OOT-specific builder (no silent edits)."""
    values = _runtime_values(path)
    return [f'{key}={values.get(key, "<missing>")!r}; expected {expected!r}'
            for key, expected in OOT_RUNTIME_REQUIRED.items() if values.get(key) != expected]


def check_runtime_config(path: Path) -> list[str]:
    """Return advisories, not silent mutations of user-provided runtime settings."""
    values = _runtime_values(path)
    warnings = []
    for key, required in OOT_RUNTIME_REQUIRED.items():
        if values.get(key) != required:
            warnings.append(f'{key} is {values.get(key, "not set")!r}; recommended OOT preset uses {required!r}.')
    for key in ('DM_NVN_SHOT','DM_NVN_TSV','DM_NVN_TSV_CALLS','DM_NDVE_ENGINE'):
        if key in values:
            warnings.append(f'{key} is a diagnostic or compatibility override, not included in the normal preset.')
    return warnings


def is_external_data_entry(name: str) -> bool:
    """Strip ONLY recognized externalizable game image / shader entries."""
    low = name.replace('\\', '/').lower()
    if not low.startswith('payload/') or '.app/' not in low:
        return False
    rel = low.split('.app/', 1)[1]
    if rel == 'romfs.img' or rel.startswith('romfs/'):
        return True
    if rel.startswith('msl/'):
        return True
    if rel.startswith('aoc/'):
        return True
    return False


def inspect_ipa(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f'IPA missing: {path}')
    with zipfile.ZipFile(path) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        plists = [i for i in files if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', i.filename)]
        if len(plists) != 1:
            raise ValueError(f'IPA must contain exactly one Payload/*.app/Info.plist; found {len(plists)}')
        plist = plistlib.loads(z.read(plists[0]))
        binary = 'Payload/' + plists[0].filename.split('/')[1] + '/' + plist['CFBundleExecutable']
        if binary not in z.namelist():
            raise ValueError(f'IPA does not contain its declared executable: {binary}')
        included = [i for i in files if is_external_data_entry(i.filename)]
        return {'bundle': plist.get('CFBundleIdentifier', ''), 'binary': binary, 'entries': len(files),
                'external_names': [i.filename for i in included],
                'external_bytes': sum(i.file_size for i in included),
                'large_remaining': [(i.filename, i.file_size) for i in files if not is_external_data_entry(i.filename) and i.file_size > 256 * 1024 * 1024]}


def export_app_only_ipa(source: Path, destination: Path, reporter: Callable[[str], None] | None = None) -> dict:
    """Stream-copy app resources from a locally built IPA; never include RomFS or shader archives.

    Fails closed on unexpected >256 MiB remaining entries. Keeps ZipInfo/Unix exec bits;
    the sideloading tool must still sign the IPA after repackaging.
    """
    reporter = reporter or (lambda _: None)
    info = inspect_ipa(source)
    if info['large_remaining']:
        raise ValueError('Unexpected large bundled file(s): ' + ', '.join(k for k, _ in info['large_remaining']) + '; inspect before exporting')
    if source.resolve() == destination.resolve():
        raise ValueError('Use a new output filename; the original IPA must be preserved.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + '.building')
    if tmp.exists():
        raise FileExistsError(f'Temporary file already exists: {tmp}')
    kept = skipped = 0
    try:
        with zipfile.ZipFile(source, 'r') as zin, zipfile.ZipFile(tmp, 'w', allowZip64=False) as zout:
            for entry in zin.infolist():
                if is_external_data_entry(entry.filename):
                    skipped += 1
                    reporter('External: ' + entry.filename)
                    continue
                if entry.is_dir():
                    zout.writestr(entry, b'')
                    continue
                # AltStore can reject the game title as an App ID name. Name only
                # the app shell; do not change the bundle ID or executable.
                if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', entry.filename):
                    raw = zin.read(entry)
                    metadata = plistlib.loads(raw)
                    metadata['CFBundleDisplayName'] = SAFE_APP_DISPLAY_NAME
                    metadata['CFBundleName'] = SAFE_APP_DISPLAY_NAME
                    fmt = plistlib.FMT_BINARY if raw.startswith(b'bplist00') else plistlib.FMT_XML
                    replacement = plistlib.dumps(metadata, fmt=fmt)
                    with zout.open(copy.copy(entry), 'w', force_zip64=False) as writer:
                        writer.write(replacement)
                else:
                    # Copy in chunks: never read large app binaries wholly into RAM.
                    with zin.open(entry, 'r') as reader, zout.open(copy.copy(entry), 'w', force_zip64=False) as writer:
                        shutil.copyfileobj(reader, writer, length=1024 * 1024)
                kept += 1
                reporter('Included: ' + entry.filename)
        if zipfile.is_zipfile(tmp) is False:
            raise ValueError('Output is not a valid ZIP archive')
        with zipfile.ZipFile(tmp) as z:
            if z.testzip() is not None:
                raise ValueError('App-only archive integrity check failed')
        check = inspect_ipa(tmp)
        if check['external_names']:
            raise ValueError('External payload entries still present after export')
        os.replace(tmp, destination)
        return {'output': str(destination), 'kept': kept, 'skipped': skipped, 'bundle': check['bundle'], 'size': destination.stat().st_size}
    finally:
        if tmp.exists():
            tmp.unlink()


def verify_native_split_ipa(ipa: Path, transfer_dir: Path, chain: str) -> dict:
    """Verify the native output without copying any of its large files.

    An IPA must not contain game/shader payload entries; the separate directory must
    contain all three actual files. Caller must never report success on partial output.
    """
    info = inspect_ipa(ipa)
    if info['external_names'] or info['large_remaining']:
        raise ValueError('Native app-only IPA still contains game data or an unrecognized large resource')
    for name in ('RomFS.img', f'b-{chain}.img', 'env.txt'):
        file = transfer_dir / name
        if not file.is_file() or file.stat().st_size == 0:
            raise ValueError(f'Native transfer folder is missing required file: {file}')
    return info


def make_data_instructions(work_dir: Path, env_file: Path) -> str:
    romfs = sorted((work_dir / 'extract').glob('*/RomFS.img')) if (work_dir / 'extract').is_dir() else []
    shader = sorted((work_dir / 'shader' / 'ios').glob('b-*.img')) if (work_dir / 'shader' / 'ios').is_dir() else []
    rom = str(romfs[0]) if len(romfs) == 1 else ('Multiple images found; select matching game version' if romfs else 'Not found in the expected build directory')
    msl = str(shader[0]) if len(shader) == 1 else ('Multiple shaders found; select matching shader chain' if shader else 'Not found in the expected build directory')
    return ("After you sideload and sign the app-only IPA, copy these 3 files into that app's Documents folder using Apple Devices > Files:\n\n"
            f"1. RomFS.img: {rom}\n"
            f"2. b-<shader-chain>.img: {msl}\n"
            f"\n3. env.txt: {env_file}\n\n"
            "Use the shader image matching the app's shader-chain ID.\n"
            "Sign the exported IPA with your selected sideloading tool before installation.\n")
