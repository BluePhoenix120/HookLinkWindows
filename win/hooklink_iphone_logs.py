"""Local, read-only summary of iPhone NXNative/HookLink game logs.

The application writes Documents/log.txt and rotates it to log.prev.txt on
launch. The previous session is generally the one to inspect after a black
screen. This parser never reads game payloads, writes to the phone, or uploads
logs; its output is shown in the Windows GUI only.
"""
from __future__ import annotations

from pathlib import Path
import re


MAX_TAIL_BYTES = 8 * 1024 * 1024
MAX_DISPLAY_LINES = 80
MAX_SIGNALS = 35
MAX_LINE_LENGTH = 500
SIGNAL = re.compile(
    r'\[(?:RED|ERROR|WARN)\]|\b(?:fatal|failed|failure|error|exception|panic|assertion|'
    r'black screen|shader library|shader archive|pipeline creation|present failed|'
    r'romfs.*(?:missing|invalid|not found)|Metal.*(?:failed|error))\b',
    re.IGNORECASE,
)


def summarize_iphone_log(path: Path) -> str:
    """Render a bounded, non-destructive report; do not guess an exact cause."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'iPhone log file not found: {path}')
    length = path.stat().st_size
    if length == 0:
        return 'The selected iPhone log is empty. Launch the app and try again.'
    with path.open('rb') as source:
        if length > MAX_TAIL_BYTES:
            source.seek(-MAX_TAIL_BYTES, 2)
        data = source.read(MAX_TAIL_BYTES)
    if length > MAX_TAIL_BYTES:
        first = data.find(b'\n')
        data = data[first + 1:] if first >= 0 else b''
    rows = data.decode('utf-8', 'replace').splitlines()
    cleaned = [r[:MAX_LINE_LENGTH] + (' …' if len(r) > MAX_LINE_LENGTH else '')
               for r in rows]
    signals = [r for r in cleaned if SIGNAL.search(r)]
    name = path.name
    output = [
        '=== iPhone game log (read-only analysis) ===',
        f'File: {path}',
        f'Size: {length:,} bytes; read last {min(MAX_TAIL_BYTES, length):,} bytes.',
        'NOTE: Potential error lines below are observations, not a confirmed root cause.',
        'NOTE: After reopening the game, log.prev.txt is usually the prior gameplay session.',
        '',
        f'Potentially relevant messages ({len(signals)} found in inspected text; showing last {MAX_SIGNALS}):'
    ]
    output.extend(signals[-MAX_SIGNALS:] or ['No obvious error messages found in the inspected portion.'])
    output.extend(['', f'Last {MAX_DISPLAY_LINES} log lines:'])
    output.extend(cleaned[-MAX_DISPLAY_LINES:] or ['(No complete log lines)'])
    output.extend(['', 'If the game screen is black but controls respond, share the prior',
                   'game session log for renderer investigation. Preserve matching',
                   'RomFS.img, b-<shader-chain>.img, and env.txt in the app Documents.'])
    return '\n'.join(output)
