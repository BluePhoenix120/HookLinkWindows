"""Host Metal shader diagnostics and space-safe compilation for Windows.

Some Windows Metal compiler builds fail when the source or metallib output
argument contains spaces, even when Python invokes them with an argv list.
The Windows app builder stages this one small host-shader step in a space-free
working directory. The original sources and generated header stay in place.
"""
from __future__ import annotations

import filecmp
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def _has_whitespace(path) -> bool:
    return any(char.isspace() for char in str(path))


def _run_captured(cmd, env, runner) -> int:
    """Keep nested host Metal failures in the parent build_ipa.log."""
    result = runner(cmd, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, errors='replace')
    output = (result.stdout or '').strip()
    if result.returncode:
        print('---- iOS host Metal shader compiler diagnostics ----', flush=True)
        if output:
            if len(output) > 24000:
                print(f'[NOTE] Showing the last 24,000 characters of {len(output):,} from the compiler.', flush=True)
            print(output[-24000:], flush=True)
        else:
            print('[ERROR] The Metal shader helper exited without diagnostic output.', flush=True)
        print(f'[ERROR] iOS host Metal helper exited with code {result.returncode}. '
              'This is separate from the completed game shader compilation.', flush=True)
    elif output:
        print(output[-5000:], flush=True)
    return result.returncode


def _stage_directory(staging_parent: Path | None) -> Path:
    """Prefer the existing build volume; fall back to Windows' temp folder."""
    candidates = [staging_parent, Path(tempfile.gettempdir())]
    for parent in candidates:
        if parent is None:
            continue
        parent = Path(parent).resolve(strict=False)
        if _has_whitespace(parent):
            continue
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return parent
    raise OSError('Windows Metal compiler requires a writable staging directory '
                  'without spaces. Choose a build directory without spaces or '
                  'set TEMP to a writable path without spaces; the existing '
                  'shader cache is safe.')


def _publish_header(source: Path, target: Path) -> None:
    """Do not invalidate already compiled C objects for an identical header."""
    if target.is_file() and filecmp.cmp(source, target, shallow=False):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + f'.{os.getpid()}.partial')
    try:
        shutil.copyfile(source, partial)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def run_host_msl(cmd, env, *, runner=subprocess.run,
                 output_path=None, source_paths=(), staging_parent=None,
                 force_stage=False) -> int:
    """Compile host shaders; stage paths only when Windows needs it.

    cmd must end with "<output> <shader1.metal> ...", and source_paths must
    correspond exactly to those final arguments. The upstream host_msl.py
    remains untouched. All extra copying is limited to its 16 host shaders and
    the generated C header, never the game's shader cache.
    """
    sources = tuple(Path(p) for p in source_paths)
    output = Path(output_path) if output_path is not None else None
    if not sources or output is None:
        return _run_captured(cmd, env, runner)
    needs_stage = force_stage or (
        os.name == 'nt' and
        any(_has_whitespace(p) for p in (*sources, output, tempfile.gettempdir()))
    )
    if not needs_stage:
        return _run_captured(cmd, env, runner)
    if tuple(map(str, sources)) != tuple(map(str, cmd[-len(sources):])):
        raise ValueError('Host Metal staging sources do not match compiler arguments')
    if str(output) != str(cmd[-len(sources) - 1]):
        raise ValueError('Host Metal staging output does not match compiler arguments')
    source_dir = sources[0].parent
    if any(p.parent != source_dir for p in sources):
        raise ValueError('Host Metal source staging requires a single source directory')
    parent = _stage_directory(Path(staging_parent) if staging_parent else None)
    identity = hashlib.sha256(str(output.resolve(strict=False)).encode('utf-8')).hexdigest()[:16]
    stage = parent / f'hooklink_host_msl_{identity}'
    staged_sources_dir = stage / 'src'
    staged_header = stage / 'host_msl_gen.h'
    stage.mkdir(parents=True, exist_ok=True)
    # Copy the whole source folder so any local Metal headers included by .metal
    # files keep their original relative locations.
    shutil.copytree(source_dir, staged_sources_dir, dirs_exist_ok=True)
    staged_sources = [staged_sources_dir / p.name for p in sources]
    new_cmd = list(cmd[:-len(sources) - 1]) + [str(staged_header), *map(str, staged_sources)]
    staged_env = dict(env)
    # The upstream helper itself uses tempfile.TemporaryDirectory for metallib
    # outputs. Those paths must also be free of spaces.
    staged_env.update(TMP=str(stage), TEMP=str(stage), TMPDIR=str(stage))
    print('[INFO] Windows Metal shader paths contain whitespace; compiling '
          f'{len(sources)} host shaders from a space-free staging directory.', flush=True)
    rc = _run_captured(new_cmd, staged_env, runner)
    if rc:
        return rc
    if not staged_header.is_file():
        print('[ERROR] Host Metal compiler exited successfully but generated '
              'no header in its staging directory.', flush=True)
        return 1
    _publish_header(staged_header, output)
    return 0
