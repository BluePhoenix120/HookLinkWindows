"""Create isolated, empty Windows build workspaces for release smoke tests.

This only creates a sibling folder; it never removes, copies, or reuses an
existing shader cache, game build, or IPA. Keep source files outside it.
"""
from __future__ import annotations

from pathlib import Path


def new_clean_test_work_dir(current: Path, *, name: str = 'HookLinkWindowsBuild-112-Clean') -> Path:
    """Atomically create a previously nonexistent sibling directory.

    On each invocation pick a new destination; existing work is untouched.
    Never choose the existing project directory as a build workspace.
    """
    current = Path(current).expanduser()
    if not str(current).strip() or str(current) == '.':
        raise ValueError('Select an existing build-directory location first.')
    parent = current.parent
    if not parent.is_dir():
        raise FileNotFoundError(f'Parent build directory does not exist: {parent}')
    if not name or any(c in name for c in '/\\:') or name in ('.', '..'):
        raise ValueError('Invalid clean-build workspace name')
    for n in range(1, 10000):
        candidate = parent / (name if n == 1 else f'{name}-{n}')
        try:
            candidate.mkdir(exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise FileExistsError('No available new clean-build directory name')
