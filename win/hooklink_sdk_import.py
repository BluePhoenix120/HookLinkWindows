"""Import an SDK from a user-supplied, authorized Xcode .xip archive.

Runs from the GUI as a hidden/background Python operation. The existing Windows
streaming extractor remains the only archive decoder. No files are downloaded or
redistributed. Extraction happens in a private staging directory, is validated
before promotion, and never overwrites an existing SDK.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from hooklink_toolchain_setup import configured_ios_sdk, save_ios_sdk, validate_ios_sdk


def validate_xip_archive(archive: Path) -> Path:
    archive = Path(archive).expanduser().resolve(strict=False)
    if not archive.is_file() or archive.suffix.lower() != '.xip':
        raise ValueError('Select a downloaded Apple Xcode .xip archive (not the Xcode application or a ZIP).')
    with archive.open('rb') as stream:
        if stream.read(4) != b'xar!':
            raise ValueError('The selected file is not a valid XIP/XAR archive (missing xar! header).')
    return archive


def extract_with_bundled_tool(extractor: Path, archive: Path, destination: Path) -> None:
    """Run extraction in this process, avoiding a second visible Windows console."""
    if not extractor.is_file():
        raise FileNotFoundError(f'Bundled SDK extractor is missing: {extractor}')
    spec = importlib.util.spec_from_file_location('_hooklink_xip_extractor', extractor)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load the bundled Xcode archive extractor')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    argv = sys.argv
    try:
        sys.argv = [str(extractor), str(archive), str(destination)]
        module.main()
    finally:
        sys.argv = argv


def import_sdk(root: Path, archive: Path, *, extractor_function=None) -> Path:
    """Stage, validate and register a newly imported SDK without replacing old data."""
    root = Path(root).resolve(strict=False)
    archive = validate_xip_archive(archive)
    # Fail early on corrupt settings, before spending time extracting the archive.
    configured_ios_sdk(root)
    extractor = root / 'engine' / 'win' / 'sdk' / 'extract_xip.py'
    if not extractor.is_file():
        raise FileNotFoundError(f'Complete HookLinkWindows checkout required: {extractor}')
    out = root / 'engine' / 'win' / 'sdk' / 'out'
    out.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix='.xip-import-', dir=out))
    promoted = None
    success = False
    try:
        print(f'[SDK] Extracting selected Xcode archive locally: {archive}', flush=True)
        print(f'[SDK] Temporary extraction folder: {staged}', flush=True)
        (extractor_function or (lambda xip, dst: extract_with_bundled_tool(extractor, xip, dst)))(archive, staged)
        candidates = [p for p in staged.iterdir() if p.is_dir()
                      and p.suffix.lower() == '.sdk' and p.name.lower().startswith('iphoneos')]
        valid = []
        for sdk in candidates:
            try:
                valid.append(validate_ios_sdk(str(sdk)))
            except ValueError as exc:
                print(f'[SDK] Skipping invalid SDK folder {sdk.name}: {exc}', flush=True)
        if len(valid) != 1:
            raise ValueError(f'Expected one complete iPhoneOS 26+ SDK from the archive, found {len(valid)}. No SDK settings changed.')
        name = valid[0].name
        promoted = out / f'HookLinkWindows-Imported-{uuid.uuid4().hex[:12]}'
        staged.rename(promoted)
        sdk = validate_ios_sdk(str(promoted / name))
        saved = save_ios_sdk(root, str(sdk))
        success = True
        print(f'[SDK] Validated and configured iPhoneOS SDK: {saved}', flush=True)
        print('[SDK] Import complete. HookLinkWindows can now recheck prerequisites.', flush=True)
        return saved
    finally:
        if staged.exists():
            shutil.rmtree(staged)
        if promoted is not None and not success and promoted.exists():
            shutil.rmtree(promoted)


def main() -> int:
    parser = argparse.ArgumentParser(description='Import a user-provided Xcode SDK without installing Xcode')
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--archive', required=True, type=Path)
    args = parser.parse_args()
    try:
        import_sdk(args.root, args.archive)
        return 0
    except (OSError, ValueError, RuntimeError, SystemExit) as exc:
        print(f'[SDK ERROR] {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
