"""Terminate a Windows build and its descendants without leaving orphan Metal compilers."""
from __future__ import annotations

import os
import subprocess


def terminate_build_tree(proc):
    """Taskkill descendants *before* the builder PID vanishes.

    Returns False if already stopped. Windows' /T traverses the live process
    tree, unlike Popen.terminate(), which only kills the Python parent.
    """
    if proc.poll() is not None:
        return False
    if os.name != 'nt':
        proc.terminate()
        return True
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    result = subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                            capture_output=True, text=True, errors='replace',
                            timeout=30, creationflags=flags)
    if result.returncode and proc.poll() is None:
        raise RuntimeError('Could not stop the complete builder process tree: ' +
                           (result.stderr.strip() or result.stdout.strip()))
    return True
