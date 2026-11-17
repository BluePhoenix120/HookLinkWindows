"""Capture the host Metal shader helper's full failure reason for Windows builds.

This tiny module is intentionally independent of the game build pipeline so
diagnostic behavior can be unit-tested without Apple tools, SDKs, or game files.
"""
from __future__ import annotations

import subprocess
import sys


def run_host_msl(cmd, env, *, runner=subprocess.run) -> int:
    """Run the host compiler invisibly through the existing Windows process shim.

    The parent app build process is already logged by the build pipeline.
    Without explicit capture, nested Python/Metal compiler stderr can be lost
    and the player sees only "iOS host Metal shader generation failed".
    """
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
