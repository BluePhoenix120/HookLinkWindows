#!/usr/bin/env python3
"""Real Windows managed translator publish gate; no game or Apple SDK needed."""
from pathlib import Path
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
import bootstrap_translator as bootstrap


def main():
    bootstrap.need(os.name == 'nt', 'Windows CI required')
    bootstrap.verify_source_identity(ROOT)
    dotnet = shutil.which('dotnet')
    bootstrap.need(dotnet is not None, '.NET 10 SDK not found')
    project = bootstrap.paths(ROOT)['project']
    expected = bootstrap.source_sha(project)
    print('Canonical translator source fingerprint:', expected, flush=True)
    with tempfile.TemporaryDirectory(prefix='hlw translator smoke ') as td:
        output = Path(td) / 'managed publish'
        bootstrap.publish_managed_translator(dotnet, project, output, expected)
        # Independently ask the same engine tool-lock module used on the
        # user's PC. No Apple compiler or SPIRV-Cross is needed for this
        # source check. Do not modify the packaged lock or host header.
        env = os.environ.copy()
        env['XLATE'] = str(output / 'dmsh_xlate.dll')
        result = bootstrap.execute([sys.executable, '-B', '-c',
            "import sys; sys.path.insert(0,sys.argv[1]); "
            "import tool_lock; print(tool_lock.xlate_embedded()); "
            "print(tool_lock.xlate_source_sha())", str(project.parent)], env=env)
        bootstrap.need(result.splitlines() == [expected, expected],
                       f'Engine tool lock disagrees with managed translator: {result}')
    print('PASS: Windows managed translator publish and tool-lock fingerprint verified')


if __name__ == '__main__':
    main()
