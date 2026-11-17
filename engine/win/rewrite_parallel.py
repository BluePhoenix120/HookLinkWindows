"""Windows x18 scan in independent Python processes (not fork/spawn of patch_nso.py).

The native rewriter is a top-level script with a large mutable image; the Windows
spawn start method would re-import and rerun that script. Instead, launch this
small, standalone worker program with read-only code chunks over stdin.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import pickle
import re
import subprocess
import sys

MAX_WORKERS = 8  # per rewritten module; the build can rewrite modules concurrently
_R18 = re.compile(r'\b[xw]18\b')


def scan_batch(jobs):
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    found = set()
    for start, data in jobs:
        at = 0
        while at < len(data):
            end = min(len(data), at + 0x4000)
            last = at - 4
            for addr, size, mnemonic, operands in decoder.disasm_lite(data[at:end], start + at):
                last = addr - start
                if _R18.search(operands):
                    found.add(addr)
            at = last + 4 if last + 4 >= end else last + 8
    return found


def _execute_batch(jobs):
    data = pickle.dumps(jobs, protocol=5)
    flags = 0x08000000 if os.name == 'nt' else 0  # CREATE_NO_WINDOW
    cmd = [sys.executable, '-B', os.path.abspath(__file__), '--x18-child']
    proc = subprocess.run(cmd, input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, creationflags=flags, check=False)
    if proc.returncode:
        raise RuntimeError('Windows rewrite worker failed (exit %s): %s' %
                           (proc.returncode, proc.stderr.decode('utf-8', 'replace')[-2000:]))
    return set(json.loads(proc.stdout.decode('utf-8')))


def scan_x18(image, ranges, requested_workers):
    """Match patch_nso.x18_words(), distributing 1-MiB code regions to subprocesses."""
    if requested_workers < 1:
        raise ValueError('Windows rewrite workers must be positive')
    if not ranges:
        return set()
    n = min(MAX_WORKERS, requested_workers, len(ranges))
    batches = [[] for _ in range(n)]
    # Assign largest ranges first; each process receives its own immutable data.
    for index, (lo, hi) in enumerate(sorted(ranges, key=lambda r: r[1] - r[0], reverse=True)):
        if not 0 <= lo <= hi <= len(image):
            raise ValueError('Invalid code range for Windows rewrite worker')
        batches[index % n].append((lo, bytes(image[lo:hi])))
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as executor:
        merged = set()
        for part in executor.map(_execute_batch, batches):
            merged.update(part)
        return merged


if __name__ == '__main__':
    if sys.argv[1:] != ['--x18-child']:
        sys.exit('usage: rewrite_parallel.py --x18-child')
    try:
        jobs = pickle.load(sys.stdin.buffer)  # IPC from the trusted parent only
        sys.stdout.write(json.dumps(sorted(scan_batch(jobs))))
    except Exception as exc:
        print('%s: %s' % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(1)
