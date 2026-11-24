"""Read the supported host-source declaration used by NXnative's Makefile.

The Windows build cannot run the upstream macOS make/clang commands.  Resolve
the actual ordered SRC list instead of freezing it at a particular engine
revision.  Reject unfamiliar make syntax rather than silently omit sources.
"""
import re
from pathlib import Path


HLE_WILDCARD = "$(sort $(wildcard hle_*.c))"


def host_source_paths(host, makefile):
    """Return the ordered source paths from the upstream SRC line.

    Supported forms are plain relative filenames and the single, sorted
    hle_*.c wildcard that NXnative already uses.  Platform filtering stays
    in build_app.py (matching upstream gen_build.py's *_mac exclusion).
    """
    host = Path(host)
    rows = re.findall(r"(?m)^SRC\s*=\s*([^\r\n]+)", makefile)
    if len(rows) != 1:
        raise ValueError("Expected exactly one NXnative SRC declaration")
    row = rows[0].strip()
    if row.count(HLE_WILDCARD) != 1:
        raise ValueError("Unrecognized NXnative SRC wildcard")
    parts = row.replace(HLE_WILDCARD, "@HLE@").split()
    result = []
    for part in parts:
        if part == "@HLE@":
            result.extend(sorted(host.glob("hle_*.c"), key=lambda p: p.name))
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:c|m|S)", part):
            raise ValueError("Unrecognized NXnative SRC entry: " + part)
        result.append(host / part)
    if len(result) != len(set(result)):
        raise ValueError("Duplicate NXnative SRC entry")
    missing = [str(path) for path in result if not path.is_file()]
    if missing:
        raise ValueError("Missing NXnative host sources: " + ", ".join(missing))
    return result
