"""Safe, pre-build shader-chain consistency check for the Windows GUI.

Only the local lock and host header are synchronized, using the backup/rollback
procedure in shader_chain_prepare.py. This does not run a game shader build.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess


CHAIN_RE = re.compile(r'^Computed chain:\s*([0-9a-f]{12})\s*$', re.M)
SHADER_PATHS = ('dm/gfx/tools/dmsh_chain.lock', 'dm/gfx/nvn/dmsh_chain.h')


class ChainPreflightError(RuntimeError):
    """A required pre-build chain check or synchronization failed."""


@dataclass(frozen=True)
class ChainResult:
    chain: str
    synchronized: bool
    log: str


def _execute(root: Path, python: str, flag: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    script = root / 'win' / 'shader_chain_prepare.py'
    try:
        return subprocess.run(
            [python, '-B', str(script), flag], cwd=str(root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8',
            errors='replace', timeout=180, check=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ChainPreflightError(f'Could not run shader-chain {flag} check: {exc}') from exc


def _ensure_unmodified_source(engine: Path) -> None:
    """Do not overwrite locally edited/staged source lock/header on an automatic sync."""
    if shutil.which('git') is None:
        return  # Source ZIP distributions have no Git checkout.
    root = subprocess.run(['git', '-C', str(engine), 'rev-parse', '--show-toplevel'],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, check=False)
    if root.returncode != 0:
        return
    result = subprocess.run(['git', '-C', str(engine), 'status', '--porcelain', '--', *SHADER_PATHS],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, check=False)
    if result.returncode != 0:
        raise ChainPreflightError('Cannot verify Git status of shader-chain files before synchronization.')
    if result.stdout.strip():
        raise ChainPreflightError('Shader lock/header already have local Git changes. '
                                  'Review or restore them before automatic synchronization. '
                                  'No files were changed.')


def run_build_chain_preflight(root: Path, engine: Path, python: str, env: dict[str, str]) -> ChainResult:
    """Check first; if mismatched, back up + synchronize then verify again.

    Fail closed before launching the IPA builder, including if the subsequent
    chain ID cannot be identified. Never reuse or remove any shader archive here.
    """
    script = root / 'win' / 'shader_chain_prepare.py'
    if not script.is_file():
        raise ChainPreflightError(f'Shader-chain preparation helper missing: {script}. '
                                  'Install the full HookLinkWindows source checkout.')
    lines = ['=== Shader-chain preflight (before IPA compilation) ===']
    check = _execute(root, python, '--check', env)
    lines.append(check.stdout.strip())
    if check.returncode == 0:
        synchronized = False
    elif check.returncode == 1 and '[MISMATCH]' in check.stdout:
        _ensure_unmodified_source(engine)
        lines.append('[NOTE] Compiler fingerprints differ. Creating external backups and synchronizing local chain files.')
        sync = _execute(root, python, '--sync', env)
        lines.append(sync.stdout.strip())
        if sync.returncode != 0:
            raise ChainPreflightError('\n'.join(lines) + '\n[BLOCKED] Local synchronization failed; IPA compilation not started.')
        synchronized = True
        check = _execute(root, python, '--check', env)
        lines.append('=== Post-synchronization verification ===\n' + check.stdout.strip())
    else:
        raise ChainPreflightError('\n'.join(lines) + f'\n[BLOCKED] Chain checker exit code {check.returncode}; IPA compilation not started.')
    match = CHAIN_RE.search(check.stdout)
    if check.returncode != 0 or '[OK] Shader lock, host header and installed tools agree' not in check.stdout or not match:
        raise ChainPreflightError('\n'.join(lines) + '\n[BLOCKED] Shader-chain verification failed; IPA compilation not started.')
    chain = match.group(1)
    lines.append(f'[READY] Shader chain {chain}; IPA builder may start.')
    lines.append('[NOTE] This preflight did not compile or delete any game shaders.')
    return ChainResult(chain, synchronized, '\n'.join(lines) + '\n')
