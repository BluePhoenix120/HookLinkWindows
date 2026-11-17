#!/usr/bin/env python3
"""Local Windows shader-chain preflight for HookLinkWindows.

Place in <HookLinkWindows repository>/win/shader_chain_prepare.py.
Run with --check (read only) or --sync (regenerate the local lock and header).
Does not compile game shaders or package an IPA. Do not commit generated local lock/header.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone


WIN = Path(__file__).resolve().parent
ROOT = WIN.parent
ENGINE = ROOT / "engine" if (ROOT / "engine" / "dm" / "gfx" / "tools" / "dmsh_chain.py").is_file() else ROOT
ENGINE_WIN = ENGINE / "win"
TOOLS = ENGINE / "dm" / "gfx" / "tools"
LOCK = TOOLS / "dmsh_chain.lock"
HEADER = ENGINE / "dm" / "gfx" / "nvn" / "dmsh_chain.h"


def select_backup_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home()) / "HookLinkWindows" / "shader-chain-backups"


def setup_windows_shim() -> None:
    # Unlike the upstream Mac-only tool-lock checker, Windows invokes Apple's
    # Metal Tools and the .NET translator DLL through the engine-local source shim.
    # In the HookLink fork, this lives at <repository>/engine/win/pyshim/.
    if not (ENGINE_WIN / "pyshim" / "sitecustomize.py").is_file():
        raise RuntimeError(f"Windows process shim not found: {WIN / 'pyshim' / 'sitecustomize.py'}")
    sys.path.insert(0, str(ENGINE_WIN))
    import toolchain
    spirv = toolchain.tool_on_path("spirv-cross")
    if not spirv:
        raise RuntimeError("SPIRV-Cross not found; run Check prerequisites first")
    os.environ["SPIRV_CROSS"] = str(spirv)
    shim_path = ENGINE_WIN / "pyshim" / "sitecustomize.py"
    spec = importlib.util.spec_from_file_location("hooklinkwindows_shader_chain_shim", shim_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load Windows subprocess compatibility shim")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def read_lock(raw: bytes) -> dict[str, str]:
    out = {}
    for line in raw.decode("utf-8").splitlines():
        if not line.startswith("#") and "\t" in line:
            name, value = line.split("\t", 1)
            out[name] = value
    return out


def lock_bytes(actual: dict[str, str]) -> bytes:
    if not actual or any("\n" in k or "\t" in k or "\n" in v for k, v in actual.items()):
        raise ValueError("Invalid toolchain fingerprint data")
    preamble = "# Translation chain tool fingerprints (written by tool_lock.py --update-lock; regenerate after changing tools and commit it)\n"
    return (preamble + "".join(f"{k}\t{v}\n" for k, v in actual.items())).encode("utf-8")


def inspect(actual, wanted, computed, header_text) -> tuple[bool, list[str]]:
    messages = []
    for k in sorted(set(actual) | set(wanted)):
        if actual.get(k) != wanted.get(k):
            messages.append(f"{k}: lock={wanted.get(k, '<none>')}, installed={actual.get(k, '<none>')}")
    match = re.search(r'^\s*#define\s+DMSH_CHAIN\s+"([0-9a-f]+)"', header_text, re.M)
    stamped = match.group(1) if match else "<not present>"
    if computed != stamped:
        messages.append(f"header={stamped}, computed={computed}")
    return not messages, messages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    choice = ap.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check", action="store_true", help="read-only lock/header check")
    choice.add_argument("--sync", action="store_true", help="save backups, rewrite local lock and header, then verify")
    ap.add_argument("--backup-dir", type=Path, default=select_backup_dir(), help="backup destination outside the Git repository")
    args = ap.parse_args()
    if not (TOOLS / "dmsh_chain.py").is_file() or not LOCK.is_file() or not HEADER.is_file():
        raise RuntimeError(f"Complete engine shader-chain files are missing from {ENGINE}")
    if os.name != "nt":
        raise RuntimeError("This bootstrap is for the Windows toolchain; do not rewrite the macOS lock on other platforms")
    setup_windows_shim()
    sys.path.insert(0, str(TOOLS))
    import dmsh_chain
    import tool_lock

    source_hash = dmsh_chain.xlate_source_sha()
    actual = tool_lock.tools_now()
    expected = read_lock(LOCK.read_bytes())
    embedded = actual.get("xlate_source", "")
    if embedded != source_hash:
        raise RuntimeError(f"Translator DLL is not built from current source: embedded={embedded}, source={source_hash}; rebuild dmsh_xlate first")
    for k in ("spirv-cross", "metal_iphoneos", "metal_macosx"):
        if actual.get(k, "missing") == "missing":
            raise RuntimeError(f"Required tool fingerprint unavailable: {k}")
    current = dmsh_chain.version()
    header = HEADER.read_text(encoding="utf-8")
    ok, diff = inspect(actual, expected, current, header)
    print(f"Engine root: {ENGINE}")
    print(f"Computed chain: {current}")
    print(f"Translator source: {source_hash}")
    if ok:
        print("[OK] Shader lock, host header and installed tools agree")
        return 0
    for item in diff:
        print(f"[MISMATCH] {item}")
    if args.check:
        print("[NOTE] Read-only check; no changes made. Use --sync only after reviewing the installed toolchain.")
        return 1

    backups = args.backup_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backups.mkdir(parents=True, exist_ok=False)
    old_lock, old_header = LOCK.read_bytes(), HEADER.read_bytes()
    (backups / "dmsh_chain.lock").write_bytes(old_lock)
    (backups / "dmsh_chain.h").write_bytes(old_header)
    (backups / "manifest.json").write_text(json.dumps({"engine": str(ENGINE), "previous_chain": current, "toolchain": actual}, indent=2), encoding="utf-8")
    try:
        LOCK.write_bytes(lock_bytes(actual))
        next_chain = dmsh_chain.version()
        HEADER.write_bytes(dmsh_chain.header_text(next_chain).encode("utf-8"))
        # This checks independently that source, binaries, and both Metal compilers match.
        errors = tool_lock.check_tools()
        if errors:
            raise RuntimeError("; ".join(errors))
        final = dmsh_chain.version()
        final_ok, final_diff = inspect(tool_lock.tools_now(), read_lock(LOCK.read_bytes()), final, HEADER.read_text(encoding="utf-8"))
        if not final_ok:
            raise RuntimeError("Verification failed after sync: " + "; ".join(final_diff))
    except BaseException:
        LOCK.write_bytes(old_lock)
        HEADER.write_bytes(old_header)
        print("[ROLLBACK] Original lock and header restored")
        raise
    print(f"[OK] Locally synchronized shader chain: {next_chain}")
    print(f"[BACKUP] {backups}")
    print("[NOTE] This did not build any game shaders. A new chain may require a new shader archive.")
    print("[NOTE] Keep these local changes out of public Git commits until the release strategy is finalized.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(2)
