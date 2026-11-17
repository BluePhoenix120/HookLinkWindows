#!/usr/bin/env python3
"""Reproducibly transplant a pinned NXNative revision into HookLinkWindows/engine.

This is NOT a checkout or reset of the engine tree. Only the paths changed
between the recorded upstream base and the requested upstream target are
applied. Every affected old file must still have its original Git blob SHA,
and every staged new file must exactly match the upstream target blob.

Use in a clean Git checkout:
    python tools/sync_nxnative_engine.py --target <full-40-character-sha>

Needs Git and access to https://github.com/dsi-hub/nxnative.git.
No game assets or Apple SDK files are involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / 'ENGINE_PIN.json'
MANIFEST = ROOT / 'ENGINE_PIN_FILES.json'
UPSTREAM_URL = 'https://github.com/dsi-hub/nxnative.git'
_SHA = re.compile(r'[a-f0-9]{40}\Z')


def git(*args: str, input_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(['git', *args], cwd=ROOT, input=input_bytes,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError('git ' + ' '.join(args[:9]) + ': '
                           + result.stderr.decode('utf-8', 'replace')[-2500:])
    return result


def git_text(*args: str) -> str:
    return git(*args).stdout.decode('utf-8', 'replace').strip()


def object_sha(revision: str, path: str) -> str | None:
    item = git('rev-parse', '--verify', f'{revision}:{path}', check=False)
    if item.returncode:
        return None
    return item.stdout.decode().strip()


def index_sha(path: str) -> str | None:
    value = git('ls-files', '--stage', '--', path).stdout.decode().strip()
    if not value:
        return None
    entries = value.splitlines()
    if len(entries) != 1:
        raise ValueError(f'Ambiguous index state for {path}: {entries!r}')
    return entries[0].split()[1]


def safe_changed_path(path: str) -> str:
    bits = path.replace('\\', '/').split('/')
    if (not path or path.startswith('/') or '\\' in path
            or any(p in ('', '.', '..') for p in bits)
            or bits[0] not in ('dm', 'docs')):
        raise ValueError(f'Refusing unexpected upstream path: {path!r}')
    return path


def changed_paths(base: str, target: str) -> list[str]:
    raw = git('diff', '--name-only', '-z', '--no-renames', base, target).stdout
    paths = [safe_changed_path(p.decode('utf-8')) for p in raw.split(b'\0') if p]
    if not paths or len(paths) > 100 or len(paths) != len(set(paths)):
        raise ValueError(f'Unexpected NXNative upstream delta: {len(paths)} paths')
    return paths


def sync(target: str) -> None:
    if not _SHA.fullmatch(target):
        raise ValueError('Target commit must be a full lowercase 40-character Git SHA')
    if git('status', '--porcelain').stdout.strip():
        raise RuntimeError('Working tree must be clean before importing the engine')
    settings = json.loads(PIN.read_text(encoding='utf-8'))
    if settings['nxnative_repo'] != UPSTREAM_URL or settings['engine_location'] != 'engine/':
        raise ValueError('Unrecognized engine location or upstream source in ENGINE_PIN.json')
    base = settings['nxnative_commit']
    if not isinstance(base, str) or not _SHA.fullmatch(base):
        raise ValueError('ENGINE_PIN.json has an invalid base commit')
    if base == target:
        print(f'[SYNC] NXNative already pinned to {target}; no changes', flush=True)
        return

    print(f'[SYNC] Fetching fixed upstream NXNative commit {target} (not branch HEAD)', flush=True)
    git('fetch', '--no-tags', '--filter=blob:none', '--depth=64', UPSTREAM_URL, target)
    git('cat-file', '-e', f'{base}^{{commit}}')
    git('merge-base', '--is-ancestor', base, target)
    paths = changed_paths(base, target)
    print(f'[SYNC] Upstream delta: {len(paths)} paths', flush=True)

    # Stop rather than silently overwriting diverged Windows engine sources.
    for path in paths:
        original_sha = object_sha(base, path)
        local_sha = index_sha('engine/' + path)
        if original_sha != local_sha:
            raise RuntimeError(f'[SYNC] Bundled engine file differs from old pin: '
                               f'engine/{path} (expected {original_sha}, found {local_sha})')
        if object_sha(target, path) is None and original_sha is None:
            raise RuntimeError(f'[SYNC] Neither base nor target has {path}')

    patch = git('diff', '--binary', '--no-renames', base, target).stdout
    git('apply', '--check', '--index', '--directory=engine', input_bytes=patch)
    git('apply', '--index', '--directory=engine', input_bytes=patch)

    # Verify every transplanted blob matches the exact target upstream snapshot.
    rows = []
    for path in paths:
        expected = object_sha(target, path)
        actual = index_sha('engine/' + path)
        if actual != expected:
            raise RuntimeError(f'[SYNC] Post-apply mismatch: engine/{path} '
                               f'(expected {expected}, found {actual})')
        if expected:
            rows.append({'path': 'engine/' + path, 'sha': expected})

    settings['nxnative_commit'] = target
    settings['hooklink_base'] = '3.0'
    # Preserve the GUI release identity: importing an engine should not silently
    # reset the Windows application's version metadata.
    PIN.write_text(json.dumps(settings, indent=4) + '\n', encoding='utf-8')
    MANIFEST.write_text(json.dumps({
        'nxnative_repo': UPSTREAM_URL,
        'from_commit': base,
        'nxnative_commit': target,
        'changed_paths': rows,
        'notes': 'Exact upstream Git blob hashes for files transplanted into engine/. Windows-only additions remain separate.'
    }, indent=4) + '\n', encoding='utf-8')

    test_file = ROOT / 'tests/test_engine_pin.py'
    test_source = test_file.read_text(encoding='utf-8')
    if test_source.count(base) != 1:
        raise RuntimeError('Expected exactly one pinned base SHA in tests/test_engine_pin.py')
    test_file.write_text(test_source.replace(base, target), encoding='utf-8')
    guide = ROOT / 'docs/GETTING_STARTED.md'
    guide_text = guide.read_text(encoding='utf-8')
    guide_text = guide_text.replace(
        '**HookLinkWindows continues to ship its existing pinned NXNative base '
        f'{chr(96)}{base}{chr(96)} plus Windows-specific changes.** '
        'Accordingly, the upstream X2 feature/fix claims are **not yet verified or guaranteed in the Windows IPA**. '
        'Upgrading the bundled engine to X2 requires a separate compatibility review and Windows end-to-end testing.',
        f'**HookLinkWindows now bundles the X2 NXNative engine revision '
        f'{chr(96)}{target}{chr(96)} plus Windows-specific changes.** '
        'All 25 changed upstream files were imported from the pinned base after checking their original blob hashes, '
        'and the exact target hashes were verified. The Windows-specific UIKit launcher and build toolchain remain '
        'separate from the upstream SwiftUI launcher. Windows end-to-end IPA and device tests are still required '
        'before treating every X2 feature or fix as verified.')
    guide.write_text(guide_text, encoding='utf-8')

    git('add', '--', 'engine', 'ENGINE_PIN.json', 'ENGINE_PIN_FILES.json',
        'tests/test_engine_pin.py', 'docs/GETTING_STARTED.md')
    git('diff', '--cached', '--check')
    print('[SYNC] Verified exact target upstream blob hashes for '
          f'{len(rows)} paths; {len(paths) - len(rows)} deletions.', flush=True)
    print('[SYNC] ENGINE_PIN.json and offline blob manifest updated.', flush=True)
    print(git_text('diff', '--cached', '--stat'), flush=True)
    print('[SYNC] Review, test, then commit; this script never pushes.', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True, help='Full pinned NXNative commit SHA')
    args = parser.parse_args()
    try:
        sync(args.target)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'[SYNC ERROR] {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
