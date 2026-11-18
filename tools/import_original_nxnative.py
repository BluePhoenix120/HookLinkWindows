#!/usr/bin/env python3
"""Make a non-destructive HookLinkWindows *candidate* using original NXNative.

The original engine is merged into HookLink's custom engine in an isolated
working checkout first. This importer then copies *only* version-controlled
engine source differences, skipping files modified by HookLinkWindows itself.
It cannot prove Objective-C Metal compatibility; run device builds separately.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OLD = "7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf"
OFFICIAL = "0b5fd6020093407af8bb5ad166e78e00bd2b7242"
HOOKLINK = "698b46bc5b14510fffc0a4b8fd4bf78309004e4c"
HOOKLINK_APP = "d04e664d253aafbd77a8fc543f6ed3c7d91d5dde"
OFFICIAL_REPO = "https://github.com/seedds/nxnative.git"
HOOKLINK_REPO = "https://github.com/dsi-hub/nxnative.git"


def git(cwd: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(cwd), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"git {args[:5]} failed: {result.stderr.decode('utf-8','replace')[-2500:]}")
    return result.stdout


def tree(cwd: Path, ref: str) -> dict[str, tuple[str, str]]:
    ret = {}
    for row in git(cwd, "ls-tree", "-r", "-z", ref).split(b"\0"):
        if not row:
            continue
        head, name = row.split(b"\t", 1)
        mode, kind, sha = head.decode("ascii").split()
        if kind != "blob":
            continue
        path = name.decode("utf-8", "surrogateescape")
        if path.startswith("/") or ".." in path.split("/"):
            raise RuntimeError(f"Unsafe engine path: {path!r}")
        ret[path] = (sha, mode)
    return ret


def local_index() -> dict[str, tuple[str, str]]:
    result = {}
    for row in git(ROOT, "ls-files", "-s", "-z", "--", "engine").split(b"\0"):
        if not row:
            continue
        info, name = row.split(b"\t", 1)
        mode, sha, stage = info.decode("ascii").split()
        if stage != "0":
            raise RuntimeError(f"Unexpected unmerged index stage: {row!r}")
        path = name.decode("utf-8", "surrogateescape")
        if path.startswith("engine/"):
            result[path[7:]] = sha, mode
    return result


def perform(merged: Path, hooklink_engine: Path) -> None:
    pin = json.loads((ROOT / "ENGINE_PIN.json").read_text(encoding="utf-8"))
    if (pin.get("nxnative_commit") != OLD
            or pin.get("nxnative_repo") != HOOKLINK_REPO
            or pin.get("engine_location") != "engine/"):
        raise RuntimeError("Expected unchanged Windows X2 pinned base; refusing unexpected checkout")
    if git(ROOT, "status", "--porcelain").strip():
        raise RuntimeError("Windows checkout must be clean before importing an upstream engine")
    base = tree(hooklink_engine, OLD)
    candidate = tree(merged, "HEAD")
    existing = local_index()
    parents = git(merged, "rev-list", "--parents", "-n", "1", "HEAD").decode().split()
    if len(parents) < 3 or HOOKLINK not in parents or OFFICIAL not in parents:
        raise RuntimeError("Merged engine must have both explicitly pinned parent commits")
    merged_sha = parents[0]
    if len(candidate) < 3300:
        raise RuntimeError("Original engine candidate is missing most source files")
    imported = []
    overlays = []
    deletes = []
    for name in sorted(set(base) | set(candidate)):
        if name.startswith(".git"):
            # Do not import original/HookLink CI or Git metadata into a Windows build.
            continue
        before = base.get(name)
        after = candidate.get(name)
        local = existing.get(name)
        if before == after:
            continue
        # Preserve *every* Windows-specific modified or deleted tracked file.
        if local != before and before is not None:
            overlays.append("engine/" + name)
            continue
        if before is None and local is not None:
            overlays.append("engine/" + name)
            continue
        target = ROOT / "engine" / name
        if after is None:
            if target.exists():
                target.unlink()
                deletes.append("engine/" + name)
            continue
        sha, mode = after
        if mode not in ("100644", "100755"):
            overlays.append("engine/" + name)
            continue
        source = merged / name
        if not source.is_file():
            raise RuntimeError(f"Missing merged source file: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if mode == "100755":
            target.chmod(target.stat().st_mode | 0o111)
        imported.append({"path": "engine/" + name, "sha": sha})

    if len(imported) < 250:
        raise RuntimeError(f"Suspiciously small original NXNative port: {len(imported)} imported files")
    if not any(x["path"] == "engine/dm/host/hle_audio.c" for x in imported):
        raise RuntimeError("Latest original NXNative host files were not imported")
    if not any(x["path"] == "engine/dm/gfx/nvn/nvn_mtl.m" for x in imported) and "engine/dm/gfx/nvn/nvn_mtl.m" not in overlays:
        raise RuntimeError("Missing Metal renderer integration provenance")

    pin.update({
        "hooklink_base": "3.0.1",
        "nxnative_repo": OFFICIAL_REPO,
        "nxnative_commit": OFFICIAL,
        "hooklink_engine_repo": HOOKLINK_REPO,
        "hooklink_engine_commit": HOOKLINK,
        "engine_integration_commit": merged_sha,
        "engine_integration_policy": "git-merge-ort-X-ours (conflicting hunks favor HookLink)",
        "release": "Alpha V1.1.2",
    })
    (ROOT / "ENGINE_PIN.json").write_text(json.dumps(pin, indent=4) + "\n", encoding="utf-8")
    manifest = {
        "nxnative_repo": OFFICIAL_REPO,
        "from_commit": OLD,
        "nxnative_commit": OFFICIAL,
        "hooklink_engine_commit": HOOKLINK,
        "engine_integration_commit": merged_sha,
        "changed_paths": imported,
        "windows_overlays": overlays,
        "deleted_paths": deletes,
        "notes": (
            "Merged original NXNative into HookLink engine, favoring HookLink in "
            "conflicting source hunks. Imported source Git blobs are verified; "
            "Windows-only files and source overlays are retained. "
            "The displayed SHA denotes original upstream ancestry, not an "
            "exact, unmodified original NXNative checkout."
        ),
    }
    (ROOT / "ENGINE_PIN_FILES.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ROOT / "VERSION").write_text("3.0.1\n", encoding="utf-8")
    guide = ROOT / "docs/GETTING_STARTED.md"
    intro = (
        "### Alpha 1.1.2: original NXNative plus HookLink's engine changes (experimental candidate)\n\n"
        "This candidate merges original [seedds/nxnative](https://github.com/seedds/nxnative) "
        "commit `" + OFFICIAL + "` with HookLink's custom [dsi-hub/nxnative]"
        "(https://github.com/dsi-hub/nxnative) commit `" + HOOKLINK + "`. "
        "Overlapping merge hunks favor HookLink to preserve its game-specific fixes. "
        "The source is **not byte-identical to original NXNative**. A manifest records "
        "the upstream SHA, HookLink parent, exact merged-source commit, imported blob hashes, "
        "and Windows-specific overlay paths. The GUI's primary commit link points "
        "to **original NXNative**, not HookLink.\n\n"
        "This is a **test candidate**, not a verified iPhone build. Build it using the "
        "GUI's **New clean…** button, which clears shader reuse and creates an empty sibling "
        "work folder. The reported earlier black screen was resolved by selecting the "
        "correct output file; no speculative graphics setting changes are included.\n\n"
    )
    old_guide = guide.read_text(encoding="utf-8")
    if "### Alpha 1.1.2: original NXNative" not in old_guide:
        old_guide = old_guide.replace(
            "## 1. Obtain the complete source checkout", 
            intro + "## 1. Obtain the complete source checkout"
        )
        guide.write_text(old_guide, encoding="utf-8")
    print(f"Imported {len(imported)} original/HookLink-merged engine files", flush=True)
    print(f"Preserved {len(overlays)} Windows engine overlays; removed {len(deletes)} obsolete files", flush=True)
    print(f"Official base: {OFFICIAL}; HookLink overlay: {HOOKLINK}; merged engine: {merged_sha}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", required=True, type=Path)
    parser.add_argument("--hooklink-engine", required=True, type=Path)
    args = parser.parse_args()
    perform(args.merged.resolve(), args.hooklink_engine.resolve())


if __name__ == "__main__":
    main()
