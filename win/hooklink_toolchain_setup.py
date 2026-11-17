"""GUI-only configuration helpers for a locally acquired iPhoneOS SDK.

No SDK or game files are copied, downloaded or bundled. Configuration remains
machine-local under engine/win/toolchain.json and is ignored by Git.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import tempfile


def _config_path(root: Path) -> Path:
    return Path(root) / 'engine' / 'win' / 'toolchain.json'


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f'Cannot read existing toolchain settings: {exc}') from exc
    if not isinstance(data, dict):
        raise ValueError('Existing toolchain settings must be a JSON object; no settings were changed.')
    return data


def configured_ios_sdk(root: Path) -> str:
    value = _load_config(_config_path(root)).get('ios_sdk', '')
    return value if isinstance(value, str) else ''


def validate_ios_sdk(folder: str) -> Path:
    if not folder.strip():
        raise ValueError('Select the iPhoneOS SDK directory first.')
    sdk = Path(folder).expanduser().resolve(strict=False)
    if sdk.suffix.lower() != '.sdk' or not sdk.name.lower().startswith('iphoneos') or not sdk.is_dir():
        raise ValueError('Choose the iPhoneOS*.sdk folder, not Xcode.app or the enclosing out directory.')
    if not (sdk / 'usr' / 'include').is_dir() or not (sdk / 'System' / 'Library' / 'Frameworks').is_dir():
        raise ValueError('SDK is incomplete: usr/include or System/Library/Frameworks is missing.')
    version = None
    settings_json = sdk / 'SDKSettings.json'
    settings_plist = sdk / 'SDKSettings.plist'
    try:
        if settings_json.is_file():
            version = json.loads(settings_json.read_text(encoding='utf-8-sig')).get('Version')
        elif settings_plist.is_file():
            with settings_plist.open('rb') as f:
                version = plistlib.load(f).get('Version')
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f'Cannot read the selected SDK version: {exc}') from exc
    major = str(version or '').split('.', 1)[0]
    if not major.isdigit() or int(major) < 26:
        raise ValueError('HookLinkWindows requires an iPhoneOS SDK version 26 or later.')
    return sdk


def save_ios_sdk(root: Path, folder: str) -> Path:
    """Safely preserve all other toolchain keys and atomically save the SDK path."""
    sdk = validate_ios_sdk(folder)
    target = _config_path(root)
    data = _load_config(target)
    data['ios_sdk'] = str(sdk)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.hooklink-sdk-', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as writer:
            json.dump(data, writer, indent=2, ensure_ascii=False)
            writer.write('\n')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return sdk
