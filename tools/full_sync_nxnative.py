#!/usr/bin/env python3
"""Create a complete original-NXnative sync candidate, preserving HookLink/Windows edits.

The original-NXnative commit is the incoming branch, not a hand-picked file list.
Three-way merge attribution:
  (A) dsi-hub/nxnative:hooklink + pinned original-NXnative base,
  (B) current HookLinkWindows/engine working tree on top of (A),
  (C) merge the entire new seedds/nxnative target into (B), -X ours on conflicts.
This script stages an isolated candidate but NEVER pushes or changes the release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "ENGINE_PIN.json"
MANIFEST = ROOT / "ENGINE_PIN_FILES.json"
ORIGINAL = "https://github.com/seedds/nxnative.git"
HOOKLINK = "https://github.com/dsi-hub/nxnative.git"
X2_BASE = "7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf"
SHA = re.compile(r"[0-9a-f]{40}\Z")
# Intentional Windows source-distribution exception: upstream includes a prebuilt
# non-Windows translator executable; the Windows builder compiles its own DLL.
PLATFORM_BINARY_EXCLUSIONS = {"dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"}


def cmd(*argv: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(argv, cwd=cwd, capture_output=True, check=False)
    if check and p.returncode:
        raise RuntimeError(f"{argv[:6]} failed ({p.returncode}): {p.stderr.decode('utf-8', 'replace')[-4500:]}")
    return p


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return cmd("git", *args, cwd=cwd, check=check)


def gt(*args: str, cwd: Path = ROOT) -> str:
    return git(*args, cwd=cwd).stdout.decode("utf-8", "replace").strip()


def git_tree(work: Path, rev: str) -> dict[str, tuple[str, str]]:
    files = {}
    for rec in git("ls-tree", "-r", "-z", rev, cwd=work).stdout.split(b"\0"):
        if not rec:
            continue
        hdr, raw_path = rec.split(b"\t", 1)
        mode, kind, sha = hdr.decode("ascii").split()
        if kind != "blob":
            continue
        path = raw_path.decode("utf-8", "surrogateescape")
        if path.startswith("/") or any(x in ("", ".", "..") for x in path.split("/")):
            raise RuntimeError("Unsafe upstream path: " + repr(path))
        files[path] = (sha, mode)
    return files


def merge(work: Path, target: str, what: str) -> None:
    p = git("merge", "--no-ff", "--no-edit", "-X", "ours", target, cwd=work, check=False)
    unmerged = git("diff", "--name-only", "--diff-filter=U", cwd=work).stdout.decode("utf-8", "replace").strip()
    if p.returncode or unmerged:
        raise RuntimeError(f"{what}: unresolved Git merge; no silent file-level overwrite. "
                           f"Unmerged files:\n{unmerged}\n{p.stderr.decode('utf-8','replace')[-3000:]}")


def sync(target: str) -> None:
    if not SHA.fullmatch(target):
        raise ValueError("Target must be a full 40-character original-NXnative SHA")
    if gt("status", "--porcelain"):
        raise RuntimeError("Candidate checkout must be clean")
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    if pin.get("nxnative_repo") != ORIGINAL or pin.get("engine_location") != "engine/":
        raise RuntimeError("Unexpected NXnative source or engine directory")
    previous = pin["nxnative_commit"]
    hook_commit = pin["hooklink_engine_commit"]
    if not SHA.fullmatch(previous) or not SHA.fullmatch(hook_commit):
        raise RuntimeError("Missing pinned original/HookLink ancestry")
    if target == previous:
        raise RuntimeError("Upstream target equals pinned source; nothing to merge")
    with tempfile.TemporaryDirectory(prefix="nxnative-full-") as workdir:
        work = Path(workdir) / "merged"
        cmd("git", "clone", "--quiet", "--filter=blob:none", "--branch", "hooklink", HOOKLINK, str(work))
        actual_hook = gt("rev-parse", "HEAD", cwd=work)
        if actual_hook != hook_commit:
            raise RuntimeError(f"HookLink has advanced ({actual_hook}); preserve its new changes before syncing, not silently discarding them")
        git("config", "user.name", "HookLinkWindows source integration", cwd=work)
        git("config", "user.email", "merge@users.noreply.github.com", cwd=work)
        git("remote", "add", "official", ORIGINAL, cwd=work)
        git("fetch", "--quiet", "--filter=blob:none", "official", previous, target, X2_BASE, cwd=work)
        git("merge-base", "--is-ancestor", previous, target, cwd=work)
        # X2_BASE is a historical dsi-hub fork snapshot, not on original NXnative main.
        # It is a valid diff reference, but must not be asserted as a direct ancestor.
        git("cat-file", "-e", X2_BASE + "^{commit}", cwd=work)

        print("HookLink source:", hook_commit, flush=True)
        print("Original NXnative old:", previous, flush=True)
        print("Original NXnative latest:", target, flush=True)
        merge(work, previous, "Reconstruct prior HookLink + pinned-NXnative base")
        reconstructed = gt("rev-parse", "HEAD", cwd=work)

        # Overlay the full, tracked Windows engine. Unlike the former importer,
        # this does NOT skip any modified files before merging new upstream.
        cmd("rsync", "-a", "--delete", "--exclude=.git/", str(ROOT / "engine") + "/", str(work) + "/")
        git("add", "--all", "--force", cwd=work)
        if git("diff", "--cached", "--quiet", cwd=work, check=False).returncode:
            git("commit", "-m", "Preserve complete HookLinkWindows engine source on recorded HookLink/NXnative ancestor", cwd=work)
        before_merge = gt("rev-parse", "HEAD", cwd=work)
        merge(work, target, "Merge ALL new original-NXnative changes")
        merged_commit = gt("rev-parse", "HEAD", cwd=work)
        upstream = git_tree(work, target)
        combined = git_tree(work, "HEAD")
        if len(upstream) < 3000 or len(combined) < 3000:
            raise RuntimeError("Suspiciously incomplete original/merged NXnative source tree")
        if "dm/gfx/nvn/nvn_mtl.m" not in combined or "dm/host/hle_audren.c" not in combined:
            raise RuntimeError("Native graphics/audio host is absent after merge")

        changed_raw = git("diff", "--name-only", "-z", "--no-renames", X2_BASE, target, cwd=work).stdout
        changes = sorted({v.decode("utf-8", "surrogateescape") for v in changed_raw.split(b"\0") if v})
        all_paths = sorted(set(upstream) | set(combined))
        windows_overlays = ["engine/" + x for x in all_paths if upstream.get(x) != combined.get(x)]
        changed_paths = []
        overrides = {}
        omitted_binaries = []
        for path in changes:
            original_file = upstream.get(path)
            local_file = combined.get(path)
            if original_file is None:
                continue
            if local_file is None:
                if path not in PLATFORM_BINARY_EXCLUSIONS:
                    raise RuntimeError(f"Original NXnative source file absent after merge: {path}")
                omitted_binaries.append({"path": "engine/" + path, "upstream_sha": original_file[0],
                                         "reason": "Prebuilt non-Windows executable excluded from source-only Windows distribution"})
                continue
            changed_paths.append({"path": "engine/" + path, "sha": original_file[0]})
            if original_file != local_file:
                overrides["engine/" + path] = {
                    "upstream_sha": original_file[0],
                    "integrated_sha": local_file[0],
                    "reason": "Three-way merge keeps conflicting HookLink/Windows changes while importing nonconflicting original NXnative changes."
                }
        if len(changed_paths) < 250:
            raise RuntimeError(f"Unexpectedly small complete update: {len(changed_paths)} paths")

        # This is a separate candidate checkout, never the published release.
        cmd("rsync", "-a", "--delete", "--exclude=.git/", str(work) + "/", str(ROOT / "engine") + "/")
        pin["nxnative_commit"] = target
        pin["hooklink_engine_commit"] = hook_commit
        pin["engine_integration_commit"] = merged_commit
        pin["engine_integration_policy"] = "full-original-main-three-way-merge-ort-X-ours; HookLink/Windows conflict hunks retained"
        pin["full_upstream_sync_parent"] = previous
        PIN.write_text(json.dumps(pin, indent=4) + "\n", encoding="utf-8")
        manifest = {
            "nxnative_repo": ORIGINAL,
            "from_commit": X2_BASE,
            "nxnative_commit": target,
            "hooklink_engine_commit": hook_commit,
            "engine_integration_commit": merged_commit,
            "changed_paths": changed_paths,
            "windows_overlays": windows_overlays,
            "integration_overrides": overrides,
            "platform_binary_exclusions": omitted_binaries,
            "deleted_paths": ["engine/" + x for x in changes if x not in upstream],
            "reconstructed_hooklink_base": reconstructed,
            "windows_overlay_parent": before_merge,
            "notes": "Every original NXnative update through the exact target was three-way merged. Local conflicts favor HookLinkWindows; all different blobs are enumerated. This is an unvalidated candidate, not a verified iPhone build."
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        engine_pin_test = ROOT / "tests" / "test_engine_pin.py"
        s = engine_pin_test.read_text(encoding="utf-8")
        anchor = "    '" + previous + "',\n"
        if s.count(anchor) != 1:
            raise RuntimeError("Cannot update allowed pinned commit in engine-pin tests")
        engine_pin_test.write_text(s.replace(anchor, anchor + "    '" + target + "',\n"), encoding="utf-8")
        sync_test = ROOT / "tests" / "test_engine_sync_manifest.py"
        s = sync_test.read_text(encoding="utf-8")
        anchor = "OFFICIAL_PIN = '" + previous + "'"
        if s.count(anchor) != 1:
            raise RuntimeError("Cannot update manifest test pin")
        sync_test.write_text(s.replace(anchor, "OFFICIAL_PIN = '" + target + "'"), encoding="utf-8")
        rt_test = ROOT / "tests" / "test_audio_producer_rt_contracts.py"
        s = rt_test.read_text(encoding="utf-8")
        anchor = 'self.assertEqual(pin["nxnative_commit"], "' + previous + '")'
        if s.count(anchor) != 1:
            raise RuntimeError("Cannot update audio backport provenance test")
        rt_test.write_text(s.replace(anchor, 'self.assertEqual(pin["nxnative_commit"], "' + target + '")'), encoding="utf-8")
        report = ROOT / "docs" / "FULL_NXNATIVE_SYNC_CANDIDATE.md"
        report.write_text(
            "# Full original NXnative sync — unvalidated candidate\n\n"
            "Original NXnative target: https://github.com/seedds/nxnative/commit/" + target + "\n\n"
            "HookLink engine retained: https://github.com/dsi-hub/nxnative/commit/" + hook_commit + "\n\n"
            "Previous original base: " + previous + "\n\n"
            "Combined synthetic merge commit: " + merged_commit + "\n\n"
            f"Official files in target: {len(upstream)}; merged files: {len(combined)}; changed original paths since X2: {len(changes)}; "
            f"changed files with retained custom conflicts/overlays: {len(overrides)}; all different paths: {len(windows_overlays)}; "
            f"explicit non-Windows binary exclusions: {len(omitted_binaries)}.\n\n"
            "Git three-way merge imports all nonconflicting updates, favoring HookLinkWindows changes only where the merge conflicts. "
            "Windows-only files are retained. ENGINE_PIN_FILES.json records the original hashes and integrated hash for every conflicting updated file.\n\n"
            "**Not yet verified:** Windows full suite, arm64 iOS host cross-compile, shader-cache compatibility, IPA build, phone rendering, audio, power and startup. "
            "Do not replace the working published V1.2.1 IPA until these checks pass.\n", encoding="utf-8")
        print("MERGE_RESULT", json.dumps({
            "official_target": target, "hooklink": hook_commit, "merged_commit": merged_commit,
            "official_files": len(upstream), "merged_files": len(combined),
            "changed_paths": len(changes), "overrides": len(overrides),
            "windows_overlay_paths": len(windows_overlays), "excluded_nonwindows_binaries": len(omitted_binaries)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    sync(args.target)
