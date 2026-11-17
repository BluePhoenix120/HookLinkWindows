"""Parse stage-scoped progress from the Windows IPA builder's plain-text log.

The stages do not take equal time; a percent belongs to its *stage*, never
an estimate of overall compilation completion.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

# Examples: [06:33:23] [3/6] shader split A: splitting: 43%, 80,720/186,587 files
#           [05:47:37] [4/6] iOS shaders: compiling: 59%, 25,308/42,848 shaders
STAGE_RE = re.compile(r'\[(?P<stage>\d{1,2})/(?P<total>\d{1,2})\]\s*(?P<message>[^\r\n]*)')
PERCENT_RE = re.compile(r'(?<![\w.])(?P<percent>\d{1,3}(?:\.\d+)?)\s*%(?!\w)')
COUNTS_RE = re.compile(r'(?<!\w)(?P<done>\d[\d,]*)\s*/\s*(?P<all>\d[\d,]*)(?!\w)')
ETA_RE = re.compile(r'\bETA\s+(?P<eta>\d{1,3}:\d{2}(?::\d{2})?)\b', re.IGNORECASE)


@dataclass(frozen=True)
class StageProgress:
    stage: int
    stages: int
    label: str
    percent: float | None
    count: str | None = None
    eta: str | None = None


def parse_build_progress(line: str) -> StageProgress | None:
    """Read one reported stage. Return None for unrelated log output.

    Numeric percentages are accepted only with a stage marker. Counts can
    provide a percentage when the builder omits one. No arbitrary estimates.
    """
    m = STAGE_RE.search(line)
    if m is None:
        return None
    stage, stages = int(m['stage']), int(m['total'])
    if stage < 1 or stages < 1 or stage > stages or stages > 64:
        return None
    raw = m['message'].strip()
    # Split only on colon + a word; do not accidentally truncate timestamps.
    label = re.split(r':\s+(?=[A-Za-z])', raw, maxsplit=1)[0].strip()
    if not label:
        return None
    label = label[:80]

    match = PERCENT_RE.search(raw)
    percent = float(match['percent']) if match else None
    if percent is not None and not 0 <= percent <= 100:
        percent = None

    count = None
    c = COUNTS_RE.search(raw)
    if c:
        done, total = int(c['done'].replace(',', '')), int(c['all'].replace(',', ''))
        if total > 0 and 0 <= done <= total:
            count = f'{done:,}/{total:,}'
            if percent is None:
                percent = (100.0 * done) / total
    eta = ETA_RE.search(raw)
    return StageProgress(stage, stages, label, percent, count, eta['eta'] if eta else None)
