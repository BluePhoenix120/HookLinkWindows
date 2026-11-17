"""Read the provenance PIN shipped in the exact local HookLinkWindows checkout.

This is a recorded *upstream base*, not the live upstream HEAD and not proof
that the Windows-modified engine tree is byte-identical to that commit.
No git executable, network access, or per-user configuration is required.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


_UPSTREAM_COMMIT_URL = 'https://github.com/seedds/nxnative/commit/'
_SHA40 = re.compile(r'[0-9a-f]{40}\Z')


@dataclass(frozen=True)
class EnginePin:
    commit: str | None
    description: str

    @property
    def url(self) -> str | None:
        return _UPSTREAM_COMMIT_URL + self.commit if self.commit is not None else None

    @property
    def display(self) -> str:
        return self.commit if self.commit is not None else 'Unknown (see ENGINE_PIN.json)'


def read_engine_pin(root: Path) -> EnginePin:
    """Gracefully handle incomplete or damaged checkout metadata."""
    path = Path(root) / 'ENGINE_PIN.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, UnicodeError):
        return EnginePin(None, 'Engine provenance metadata is missing or unreadable.')
    if not isinstance(data, dict):
        return EnginePin(None, 'Engine provenance metadata is not a JSON object.')
    sha = data.get('nxnative_commit')
    if not isinstance(sha, str) or _SHA40.fullmatch(sha) is None:
        return EnginePin(None, 'No valid 40-character upstream SHA recorded in ENGINE_PIN.json.')
    if data.get('engine_location') != 'engine/':
        return EnginePin(None, 'Engine provenance has an unexpected engine location.')
    return EnginePin(sha, 'Pinned upstream NXNative base. The bundled Windows engine contains additional changes.')
