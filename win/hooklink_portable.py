"""Portable project preflight and per-user GUI preferences for HookLinkWindows.

No network, registry writes, dependency installs, or generated game data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile

SETTINGS_VERSION = 2
DEFAULT_WORK_NAME = 'HookLinkWindowsBuild'
DEFAULT_IPA_NAME = 'HookLinkWindows-Full.ipa'
PRESET_REL = 'config/iphone-oot.env'
ALLOWED_KEYS = {
    'input_path', 'work_dir', 'env_file', 'output_ipa', 'bundle_id',
    'workers', 'auto_workers', 'allow_damaged', 'allow_metal', 'entitlements', 'output_auto', 'package_mode',
    'reuse_shader_work', 'native_app_only',
}


def native_display_path(value: str) -> str:
    """Normalize only for display; Windows accepts forward or backslashes."""
    return os.path.normpath(value) if value else value

def user_settings_path(home: Path | None = None, local_appdata: str | None = None) -> Path:
    """Settings live outside the checkout, irrespective of clone/extract location."""
    home = home or Path.home()
    if local_appdata is None:
        local_appdata = os.environ.get('LOCALAPPDATA', '') if os.name == 'nt' else ''
    if local_appdata:
        base = Path(local_appdata)
    elif os.name == 'nt':
        base = home / 'AppData' / 'Local'
    else:
        base = home / '.config'
    return base / 'HookLinkWindows' / 'gui-settings.json'


def _encode_path(value: str, root: Path) -> str:
    if not value:
        return ''
    p = Path(value)
    try:
        rel = p.resolve(strict=False).relative_to(root.resolve(strict=False))
        return '${PROJECT}/' + rel.as_posix()
    except ValueError:
        return str(p)


def _decode_path(value: str, root: Path) -> str:
    if value == '${PROJECT}':
        return str(root)
    if value.startswith('${PROJECT}/'):
        return str(root / Path(value[len('${PROJECT}/'):]))
    return value




def locate_engine_root(project_root: Path) -> Path:
    """Resolve either the legacy engine-at-root layout or the HookLink-fork layout.

    In a fork of dsi-hub/HookLink, vendored nxnative sources are placed under
    engine/ to preserve the parent project's unrelated Mac app files.
    """
    root = Path(project_root).resolve(strict=False)
    if (root / 'win' / 'build_ipa_windows.py').is_file():
        return root
    return root / 'engine'


class SettingsStore:
    def __init__(self, root: Path, path: Path | None = None):
        self.root = Path(root)
        self.path = path or user_settings_path()

    def load(self) -> tuple[dict, list[str]]:
        if not self.path.exists():
            return {}, []
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8-sig'))
            if not isinstance(raw, dict) or raw.get('version') not in (1, SETTINGS_VERSION) or not isinstance(raw.get('settings'), dict):
                return {}, ['Saved preferences have an unsupported format; using defaults.']
            legacy = raw['version'] == 1
            values = {k: v for k, v in raw['settings'].items() if k in ALLOWED_KEYS}
            # v0.4.0 wrote both compatibility flags as False to fresh preferences.
            # Reset only those legacy values to the new, enabled defaults, then
            # respect explicit choices saved by v0.4.1 and later (version 2).
            if legacy:
                values.pop('allow_damaged', None)
                values.pop('allow_metal', None)
            if values.get('package_mode') not in ('app_only', 'full'):
                values.pop('package_mode', None)
            for key in ('input_path', 'work_dir', 'env_file', 'output_ipa', 'bundle_id', 'reuse_shader_work'):
                if key in values and not isinstance(values[key], str):
                    values.pop(key)
            for key in ('auto_workers', 'allow_damaged', 'allow_metal', 'entitlements', 'output_auto', 'native_app_only'):
                if key in values and not isinstance(values[key], bool):
                    values.pop(key)
            n = values.get('workers')
            if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 61:
                values.pop('workers', None)
            for key in ('input_path', 'work_dir', 'env_file', 'output_ipa', 'reuse_shader_work'):
                if key in values:
                    values[key] = native_display_path(_decode_path(values[key], self.root))
            warnings = ['Previous GUI preferences loaded; compatibility defaults upgraded to enabled.'] if legacy else []
            return values, warnings
        except (OSError, ValueError, UnicodeError) as exc:
            return {}, [f'Could not read saved preferences ({type(exc).__name__}); using defaults.']

    def save(self, values: dict) -> None:
        safe = {k: v for k, v in values.items() if k in ALLOWED_KEYS}
        for key in ('input_path', 'work_dir', 'env_file', 'output_ipa', 'reuse_shader_work'):
            if isinstance(safe.get(key), str):
                safe[key] = _encode_path(safe[key], self.root)
        payload = {'version': SETTINGS_VERSION, 'settings': safe}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement; no settings file is stored in the Git repository.
        fd, temporary = tempfile.mkstemp(prefix='.gui-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.write('\n')
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


@dataclass
class Preflight:
    root: Path
    blockers: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    @property
    def ready_for_doctor(self) -> bool:
        return not self.blockers

    def summary(self) -> str:
        lines = [f'Installation root: {self.root}', 'Repository checks:']
        lines.extend(' [OK] ' + x for x in self.passed)
        lines.extend(' [MISSING] ' + x for x in self.blockers)
        lines.extend(' [NOTE] ' + x for x in self.advisories)
        if self.ready_for_doctor:
            lines.append('Repository layout: complete for preflight')
            lines.append('External compilers/SDKs: checked next by Check prerequisites.')
        else:
            lines.append(f'Repository layout: incomplete — {len(self.blockers)} required project file(s) missing.')
            lines.append('Why: This folder does not contain the complete HookLinkWindows build sources; it may be a GUI-only ZIP or a partial checkout.')
            lines.append('How to fix: Download the complete HookLinkWindows fork, including its engine/ Windows source tree, and launch HookLinkWindows.exe from the repository root. Do not run a GUI-only update ZIP by itself.')
            lines.append('After fixing the checkout, run Check prerequisites again to verify the external compilers and SDK.')
        return '\n'.join(lines)


def check_project_installation(root: Path) -> Preflight:
    """Check layout and local overrides, NOT the availability of external toolchains.

    Avoid hardcoded paths, and never run a build or modify user's toolchain config.
    """
    root = Path(root).resolve(strict=False)
    result = Preflight(root)
    engine = locate_engine_root(root)
    nested = engine != root
    if nested:
        result.advisories.append('Fork layout: expecting nxnative Windows build sources under engine/.')
    required = {
        'win/build_ipa_windows.py': 'Windows IPA driver',
        'win/build_app.py': 'Windows host compiler adapter',
        'win/doctor.py': 'Windows dependency doctor',
        'win/toolchain.py': 'Toolchain locator',
        'win/sdk/extract_xip.py': 'iPhoneOS SDK extractor',
        'dm/host/Makefile': 'HookLink host Makefile',
        'dm/gfx/tools/dmsh_build.py': 'Shader compiler driver',
        'scripts/build_ipa_from_nsp.py': 'Upstream IPA pipeline',
        PRESET_REL: 'OOT runtime preset',
    }
    for rel, label in required.items():
        # The runtime preset belongs to the HookLink fork; engine files belong to nxnative.
        base = root if rel == PRESET_REL else engine
        displayed = rel if base == root else 'engine/' + rel
        if (base / rel).is_file():
            result.passed.append(label)
        else:
            result.blockers.append(f'{label}: {displayed} (the complete Windows engine sources are required)')
    # Report stale absolute overrides in local, user-specific toolchain.json without modifying them.
    cfg = engine / 'win' / 'toolchain.json'
    if cfg.is_file():
        try:
            raw = cfg.read_text(encoding='utf-8-sig')
            settings = json.loads(raw)
            if not isinstance(settings, dict):
                raise ValueError('expected a JSON object')
            result.passed.append('Local toolchain.json parses as JSON')
            if raw.startswith('\ufeff'):
                result.advisories.append('toolchain.json contains a UTF-8 BOM; use UTF-8 without BOM if Python rejects it')
            for key in ('ios_sdk', 'llvm', 'metal_tools', 'spirv_cross_dir', 'glslangValidator_dir', 'zstd', 'dotnet'):
                value = settings.get(key)
                if isinstance(value, str) and value and not Path(value).exists():
                    result.advisories.append(f'toolchain.json: {key} points to a missing location: {value}' + ('; automatic SDK discovery will try nearby checkouts without rewriting your JSON' if key == 'ios_sdk' else ''))
        except (OSError, UnicodeError, ValueError) as exc:
            result.advisories.append(f'toolchain.json could not be parsed ({type(exc).__name__}); check encoding and JSON syntax')
    else:
        result.advisories.append('No local win/toolchain.json; toolchain locator may use PATH or NXW_* overrides')
    if (engine / 'win' / 'sdk' / 'out' / 'iPhoneOS.sdk').is_dir():
        result.passed.append('Repository-relative iPhoneOS SDK present')
    else:
        result.advisories.append('iPhoneOS SDK is not bundled with this source checkout; Check prerequisites will look for an external SDK')
    return result
