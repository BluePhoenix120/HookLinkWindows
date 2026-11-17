"""Offline first-run dependency catalogue and approved setup actions.

The GUI displays the engine doctor's actual results, rather than guessing from
the presence of a folder or a local download. All links are public vendor pages.
No executable or proprietary SDK is downloaded or silently installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# Direct Apple-hosted Xcode 27.2 archive. Opening this URL may require an Apple
# Developer sign-in; the GUI never downloads or redistributes Apple files itself.
XCODE_XIP_DOWNLOAD_URL = 'https://download.developer.apple.com/Developer_Tools/Xcode_27.2/Xcode_27.2.xip'


@dataclass(frozen=True)
class Dependency:
    key: str
    label: str
    purpose: str
    url: str = ''


DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency('Python 3.10+', 'Python 3.10+', 'Required to compile game assets and build the IPA.', 'https://www.python.org/downloads/windows/'),
    Dependency('python module lz4.block', 'Python package: lz4', 'Compression support. Installed within the GUI using pip.'),
    Dependency('python module capstone', 'Python package: capstone', 'Disassembly support. Installed within the GUI using pip.'),
    Dependency('python module fontTools', 'Python package: fonttools', 'Font tools. Installed within the GUI using pip.'),
    Dependency('python zstd (compression.zstd / backports.zstd)', 'Python package: zstd', 'Python Zstandard support; installed within the GUI if missing.'),
    Dependency('python module PIL', 'Python package: Pillow', 'Optional image support.'),
    Dependency('.NET SDK 10', '.NET SDK 10 (x64)', 'Builds the managed shader translator and supporting tools.', 'https://dotnet.microsoft.com/en-us/download/dotnet/10.0'),
    Dependency('LLVM clang (20+)', 'LLVM / Clang 20+', 'Compiles ARM64 iOS code.', 'https://github.com/llvm/llvm-project/releases'),
    Dependency('ld64.lld (LLVM Mach-O linker)', 'LLVM Mach-O linker (ld64.lld)', 'Included with the Windows LLVM distribution.', 'https://github.com/llvm/llvm-project/releases'),
    Dependency('Metal compiler (iphoneos)', 'Apple Metal tools (iOS)', 'Windows-hosted Metal shader compilers; Apple terms apply.', 'https://developer.apple.com/metal/tools/'),
    Dependency('Metal compiler (macosx)', 'Apple Metal tools (macOS)', 'Also supplied by the Windows-hosted Metal tools.', 'https://developer.apple.com/metal/tools/'),
    Dependency('spirv-cross', 'SPIRV-Cross (Vulkan SDK)', 'Shader translation executable.', 'https://vulkan.lunarg.com/sdk/home'),
    Dependency('zstd', 'Zstandard (zstd.exe)', 'Command-line compression tool.', 'https://github.com/facebook/zstd/releases'),
    Dependency('iPhoneOS SDK 26+', 'iPhoneOS SDK 26+', 'Not included with Windows; Apple licensing restricts how SDKs can be used.', 'https://developer.apple.com/download/all/'),
    Dependency('shader translator DLLs', 'HookLinkWindows graphics support', 'Prepared automatically from bundled source when prerequisites are ready.'),
    Dependency('glslangValidator', 'glslangValidator (optional)', 'Optional shader compiler included with the Vulkan SDK.', 'https://vulkan.lunarg.com/sdk/home'),
    Dependency('standard font (STD_FONT)', 'Standard Unicode font', 'A compatible Windows font is usually already installed.'),
)

# Explicitly allowlisted PyPI packages. Never accept package names from doctor
# output, user paths, error messages, or untrusted download pages.
_PIP_PACKAGES: tuple[tuple[str, str], ...] = (
    ('python module lz4.block', 'lz4'),
    ('python module capstone', 'capstone'),
    ('python module fontTools', 'fonttools'),
    ('python zstd (compression.zstd / backports.zstd)', 'backports.zstd'),
)


def dependency_statuses(report) -> list[tuple[Dependency, str, str]]:
    """The real doctor report is authoritative; unknown != missing."""
    available = {} if report is None else {item['name']: item for item in report.entries}
    rows = []
    for dep in DEPENDENCIES:
        item = available.get(dep.key)
        if item is None:
            status, detail = 'Not checked', dep.purpose
        elif item['ok']:
            status, detail = 'Installed', item['detail'] or dep.purpose
        elif not item['required']:
            status, detail = 'Optional', item['detail'] or dep.purpose
        else:
            status, detail = 'Missing', item['detail'] or dep.purpose
        rows.append((dep, status, detail))
    return rows


def missing_python_packages(report) -> tuple[str, ...]:
    """Return only the required, missing PyPI packages in a fixed safe order."""
    if report is None or report.blockers:
        return ()
    items = {x['name']: x for x in report.entries}
    python = items.get('Python 3.10+')
    if not python or not python['ok']:
        return ()
    return tuple(package for key, package in _PIP_PACKAGES
                 if key in items and items[key]['required'] and not items[key]['ok'])
