"""Pure worker-count policy for the HookLinkWindows GUI."""
from __future__ import annotations
import os

def logical_workers(cpu_count=None, limit=61):
    if cpu_count is None:
        cpu_count = os.cpu_count()
    return min(limit, max(1, 2 * (cpu_count or 0)))
