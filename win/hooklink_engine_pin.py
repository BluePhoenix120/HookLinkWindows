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
from urllib.parse import urlsplit


_SHA40 = re.compile(r'[0-9a-f]{40}\Z')
_GITHUB_OWNER = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z')
_GITHUB_REPO = re.compile(r'[A-Za-z0-9_.-]+\Z')


def github_repository_url(value: object) -> str | None:
    """Normalize a pinned HTTPS GitHub clone URL to the corresponding repository page.

    Strict validation prevents a corrupted pin from turning the View commit
    button into an arbitrary website link. Accepts the .git clone suffix.
    """
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        if (url.scheme != 'https' or url.netloc != 'github.com'
                or url.query or url.fragment or not url.path.startswith('/')):
            return None
        parts = url.path.strip('/').split('/')
        if len(parts) != 2:
            return None
        owner, name = parts
        if name.endswith('.git'):
            name = name[:-4]
        if not _GITHUB_OWNER.fullmatch(owner) or not _GITHUB_REPO.fullmatch(name):
            return None
        if name in ('.', '..'):
            return None
        return f'https://github.com/{owner}/{name}'
    except ValueError:
        return None


@dataclass(frozen=True)
class EnginePin:
    commit: str | None
    repository: str | None
    description: str

    @property
    def url(self) -> str | None:
        if self.commit is None or self.repository is None:
            return None
        return f'{self.repository}/commit/{self.commit}'

    @property
    def display(self) -> str:
        return self.commit if self.commit is not None else 'Unknown (see ENGINE_PIN.json)'


def read_engine_pin(root: Path) -> EnginePin:
    """Read both SHA and source repository, failing closed on malformed metadata."""
    path = Path(root) / 'ENGINE_PIN.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, UnicodeError):
        return EnginePin(None, None, 'Engine provenance metadata is missing or unreadable.')
    if not isinstance(data, dict):
        return EnginePin(None, None, 'Engine provenance metadata is not a JSON object.')
    sha = data.get('nxnative_commit')
    if not isinstance(sha, str) or _SHA40.fullmatch(sha) is None:
        return EnginePin(None, None, 'No valid 40-character upstream SHA recorded in ENGINE_PIN.json.')
    if data.get('engine_location') != 'engine/':
        return EnginePin(None, None, 'Engine provenance has an unexpected engine location.')
    repo = github_repository_url(data.get('nxnative_repo'))
    if repo is None:
        return EnginePin(sha, None, 'Pinned SHA recorded, but the source repository URL is invalid or unsupported.')
    return EnginePin(sha, repo, 'Pinned upstream NXNative base. The bundled Windows engine contains additional changes.')
