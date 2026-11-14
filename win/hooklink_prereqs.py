"""Read-only, structured prerequisites report using the port's own doctor.py.

The doctor is the source of truth for external Windows build dependencies.
No software is installed and no build/game files are altered.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import sys


@dataclass
class CheckReport:
    entries: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw: str = ''

    @property
    def ready(self) -> bool:
        return not self.blockers and all(x['ok'] for x in self.entries if x['required'])

    def format(self) -> str:
        lines = ['=== Windows build prerequisites ===']
        for item in self.entries:
            status = 'OK' if item['ok'] else ('MISSING' if item['required'] else 'OPTIONAL')
            lines.append(f"[{status}] {item['name']}" + (f": {item['detail']}" if item['detail'] else ''))
            if not item['ok'] and item['how']:
                lines.append('    Action: ' + item['how'])
        for reason in self.blockers:
            lines.append('[BLOCKED] ' + reason)
        for note in self.notes:
            lines.append('[INFO] ' + note)
        if self.raw:
            lines.append('Diagnostic output:\n' + self.raw)
        if self.ready:
            lines.append('RESULT: No missing required items detected by this check; a real build is still unverified.')
        else:
            lines.append('RESULT: One or more required items need attention. See actions above.')
        return '\n'.join(lines)


def _parse_version(line: str) -> int | None:
    m = re.search(r'(?:clang version|LLVM version)\s+(\d+)', line, re.I)
    return int(m.group(1)) if m else None


def normalize_doctor_json(payload) -> CheckReport:
    if not isinstance(payload, list) or not payload:
        raise ValueError('The toolchain doctor did not return a list of dependency checks.')
    report = CheckReport()
    for obj in payload:
        if not isinstance(obj, dict) or not isinstance(obj.get('name'), str) or not isinstance(obj.get('ok'), bool):
            raise ValueError('The dependency report contains an invalid check.')
        item = {'name': obj['name'], 'ok': obj['ok'], 'required': bool(obj.get('required', True)),
                'detail': str(obj.get('detail') or '').strip(), 'how': str(obj.get('how') or '').strip()}
        if item['name'].startswith('LLVM clang') and item['ok']:
            major = _parse_version(item['detail'])
            if major is not None and major < 20:
                item['ok'] = False
                item['how'] = 'Install LLVM 20 or later: https://github.com/llvm/llvm-project/releases'
        report.entries.append(item)
    report.notes.extend([
        'Xcode.app runs on macOS and is not required on Windows. This build instead needs an iPhoneOS SDK and Apple Metal Developer Tools for Windows.',
        'The iPhoneOS SDK and Metal tools must be obtained separately under applicable Apple license terms; they are not bundled.',
        'Signing/sideloading, the Increased Memory Limit capability, and successful device gameplay must be verified manually after building.',
    ])
    return report


def run_prerequisite_check(root: Path, python: str, timeout: int = 150) -> CheckReport:
    root = Path(root)
    doctor = root / 'win' / 'doctor.py'
    if not doctor.is_file():
        return CheckReport(blockers=['Complete Windows port missing: win/doctor.py. Extract or clone the full HookLinkWindows source tree, not only its GUI add-on.'])
    try:
        p = subprocess.run([str(python), str(doctor), '--json'], cwd=str(root), text=True,
                           errors='replace', capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckReport(blockers=[f'Cannot start dependency checker using {python}: {exc}. Verify Python 3.10+ and the launcher configuration.'])
    stdout = p.stdout.strip()
    try:
        result = normalize_doctor_json(json.loads(stdout))
    except (ValueError, json.JSONDecodeError) as exc:
        return CheckReport(blockers=[f'Unable to parse win/doctor.py --json ({exc}). The installed port may need an updated doctor.py.'],
                           raw=(stdout + '\n' + p.stderr.strip()).strip()[:7000])
    if p.stderr.strip():
        result.notes.append('Doctor stderr: ' + p.stderr.strip()[:500])
    if p.returncode not in (0, 1):
        result.blockers.append(f'win/doctor.py exited unexpectedly with code {p.returncode}.')
    return result


if __name__ == '__main__':
    from hooklink_portable import check_project_installation
    root = Path(__file__).resolve().parent.parent
    project = check_project_installation(root)
    print(project.summary())
    print()
    result = run_prerequisite_check(root, sys.executable)
    print(result.format())
    raise SystemExit(0 if project.ready_for_doctor and result.ready else 1)
