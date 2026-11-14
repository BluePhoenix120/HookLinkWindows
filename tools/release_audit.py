"""Conservative source-only release audit by filename (NOT a content/licensing audit)."""
from __future__ import annotations
import fnmatch
from pathlib import Path
import subprocess
import sys

SKIP_DIRS = {'.git', '__pycache__', '.venv', 'node_modules'}
SENSITIVE_NAMES = {'prod.keys', 'title.keys', 'romfs.img', 'toolchain.json', 'log.txt', 'log.prev.txt'}
SENSITIVE_SUFFIXES = ('.nup', '.nsp', '.xci', '.nsz', '.xcz', '.ipa', '.metallib', '.mobileprovision', '.p12', '.pfx', '.xip')
SENSITIVE_GLOBS = ('b-*.img', '*.img.img.*', '*.entitlements.private', 'id_rsa*')


def inventory(root: Path) -> tuple[list[str], str]:
    try:
        p = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], capture_output=True, check=True)
        files = [s.decode('utf-8', 'replace') for s in p.stdout.split(b'\0') if s]
        return files, 'Git tracked and unignored files'
    except (OSError, subprocess.CalledProcessError):
        files = []
        for f in root.rglob('*'):
            if f.is_file() and not any(part in SKIP_DIRS for part in f.relative_to(root).parts):
                files.append(f.relative_to(root).as_posix())
        return files, 'Folder inventory (Git not available)'


def audit(root: Path) -> tuple[list[str], str]:
    files, mode = inventory(root)
    flagged = []
    for name in files:
        low = name.replace('\\', '/').lower()
        base = low.rsplit('/', 1)[-1]
        if base in SENSITIVE_NAMES or base.endswith(SENSITIVE_SUFFIXES) or any(fnmatch.fnmatch(base, pat) for pat in SENSITIVE_GLOBS) or '/sdk/out/' in '/' + low + '/' or low.startswith('win/sdk/out/'):
            flagged.append(name)
    return sorted(set(flagged)), mode


if __name__ == '__main__':
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    flagged, mode = audit(root)
    print('Source-only release filename audit: ' + mode)
    print('Root: ' + str(root))
    if flagged:
        for name in flagged:
            print('[REVIEW / REMOVE] ' + name)
        print(f'{len(flagged)} suspicious file name(s). Do not stage/publish until reviewed.')
        sys.exit(2)
    print('No known high-risk filenames found. Manual license, source-content, and build-output audits still required.')
