#!/usr/bin/env python3
"""Upstream-FIRST, read-only dry-run merge of original NXnative + HookLink + Windows.

Original NXnative newest pinned tree is the foundation. Git then merges the
HookLink engine changes from the real shared ancestor. Only *actual Windows
differences from HookLink's old tree* are applied by a second three-way merge:
    ours = official+HookLink, base = old HookLink, theirs = Windows.
No old Windows file wins merely because its pathname was marked preserved.

Conflicting hunks are reported, NEVER resolved by silent replacement.
Does not change main, the repo working tree, pins, release, or game assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = "https://github.com/seedds/nxnative.git"
HOOKLINK = "https://github.com/dsi-hub/nxnative.git"
Q = chr(96)


def command(*args, cwd=ROOT, check=True):
    p = subprocess.run(args, cwd=cwd, capture_output=True)
    if check and p.returncode:
        raise RuntimeError(f"{args[:7]}: {p.stderr.decode(errors='replace')[-2000:]}")
    return p


def git(*args, cwd, check=True):
    return command("git", *args, cwd=cwd, check=check)


def blob(repo, rev, path):
    p = git("show", rev + ":" + path, cwd=repo, check=False)
    return p.stdout if not p.returncode else None


def tree_blobs(repo, rev):
    result = {}
    records = git("ls-tree", "-r", "-z", rev, cwd=repo).stdout.split(b"\0")
    for record in records:
        if not record:
            continue
        header, name = record.split(b"\t", 1)
        mode, kind, sha = header.decode("ascii").split()
        if kind == "blob":
            result[name.decode("utf-8", "surrogateescape")] = sha
    return result


def sha(data):
    if data is None:
        return None
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def three_way(ours, base, windows, temp, label):
    if b"\0" in ours or b"\0" in base or b"\0" in windows:
        return None, "binary content changed on both sides"
    names = [temp / ("ours" + str(i)) for i in range(3)]
    for f, data in zip(names, [ours, base, windows]):
        f.write_bytes(data)
    p = command("git", "merge-file", "--diff3", "-p", *(str(f) for f in names), check=False)
    if p.returncode:
        return None, "text merge has overlapping hunks"
    return p.stdout, None


def preview(report):
    pin = json.loads((ROOT / "ENGINE_PIN.json").read_text(encoding="utf-8"))
    original, hook = pin["nxnative_commit"], pin["hooklink_engine_commit"]
    with tempfile.TemporaryDirectory(prefix="upstream-first-") as d:
        tmp = Path(d)
        clone = tmp / "base"
        command("git", "clone", "--quiet", "--filter=blob:none", "--branch", "hooklink", HOOKLINK, str(clone))
        if git("rev-parse", "HEAD", cwd=clone).stdout.decode().strip() != hook:
            raise RuntimeError("HookLink branch moved since pinned; update pin first")
        git("remote", "add", "upstream", OFFICIAL, cwd=clone)
        git("fetch", "--quiet", "--filter=blob:none", "upstream", original, cwd=clone)
        git("config", "user.email", "merge@users.noreply.github.com", cwd=clone)
        git("config", "user.name", "NXnative integration audit", cwd=clone)
        ancestor = git("merge-base", hook, original, cwd=clone).stdout.decode().strip()
        git("switch", "--detach", original, cwd=clone)
        strict = git("merge", "--no-ff", "--no-edit", hook, cwd=clone, check=False)
        original_hook_conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=clone).stdout.decode().splitlines()
        if strict.returncode or original_hook_conflicts:
            git("merge", "--abort", cwd=clone)
            preferred = git("merge", "--no-ff", "--no-edit", "-X", "theirs", hook, cwd=clone, check=False)
            still = git("diff", "--name-only", "--diff-filter=U", cwd=clone).stdout.decode().splitlines()
            if preferred.returncode or still:
                raise RuntimeError("Reference NXnative+HookLink merge has unresolved conflicts: " + str(still[:20]))
        ref = git("rev-parse", "HEAD", cwd=clone).stdout.decode().strip()
        officials = tree_blobs(clone, original)
        reference = tree_blobs(clone, ref)
        hookfiles = tree_blobs(clone, hook)
        windows_files = {p.relative_to(ROOT / "engine").as_posix(): p for p in (ROOT / "engine").rglob("*") if p.is_file() and ".git" not in p.parts}
        names = sorted(set(reference) | set(windows_files))
        report_conflicts = []
        updated = []
        retained = []
        identical = []
        additions = []
        lost_official = []
        approx_candidate_blobs = {}
        for path in names:
            W = windows_files[path].read_bytes() if path in windows_files else None
            whash = sha(W)
            rhash = reference.get(path)
            hhash = hookfiles.get(path)
            if rhash is None and W is not None:
                # Original+HookLink has no such file. Preserve Windows additions.
                output_hash = whash
                additions.append(path)
            elif W is None:
                output_hash = rhash
                if path in officials and rhash is None:
                    lost_official.append(path)
            elif whash == rhash or whash == hhash:
                # Windows has no unique edit; use the *latest* original+HookLink.
                output_hash = rhash
                identical.append(path)
            elif hhash is None or hhash == rhash:
                # Only Windows added/modified this file relative to unchanged
                # HookLink base; there is no competing incoming edit.
                output_hash = whash
                retained.append(path)
            else:
                # Fetch file content only when BOTH upstream and Windows changed.
                H = blob(clone, hook, path)
                R = blob(clone, ref, path)
                candidate, why = three_way(R, H, W, tmp, path)
                if candidate is None:
                    report_conflicts.append((path, why))
                    output_hash = rhash  # audit-only, not a resolved merge!
                else:
                    output_hash = sha(candidate)
                    updated.append(path)
            approx_candidate_blobs[path] = output_hash
        if lost_official:
            raise RuntimeError("Official source dropped from upstream-first reference: " + str(lost_official[:25]))
        critical = [
            ("dm/gfx/tools/shader_split.py", b"def bahs_binary_records("),
            ("dm/gfx/tools/shader_split.py", b"def kit_jobs("),
            ("dm/gfx/tools/dmsh_build.py", b"def owned_output("),
            ("dm/gfx/tools/dmsh_build.py", b"def rt_finish("),
            ("scripts/build_ipa_from_nsp.py", b"def build_sources("),
            ("scripts/build_ipa_from_nsp.py", b"def drop_prewarm("),
        ]
        # Check merged source content from reference + Windows deltas, without
        # falsely claiming that conflict-selected reference is a final answer.
        missing = []
        for path, needle in critical:
            if path not in approx_candidate_blobs:
                missing.append(path + " (missing file)")
            elif path in reference:
                r = blob(clone, ref, path)
                if needle not in r:
                    missing.append(path + ": " + needle.decode())
        text = [
            "# Upstream-first NXnative + HookLink + Windows three-way merge dry run", "",
            "- Original NXnative: " + Q + original + Q,
            "- HookLink fork revision: " + Q + hook + Q,
            "- Shared Git ancestor: " + Q + ancestor + Q,
            "- Upstream-first NXnative+HookLink synthetic merge: " + Q + ref + Q,
            "- Strict overlapping original/HookLink conflicts: **" + str(len(original_hook_conflicts)) + "**",
            "- Files in candidate: **" + str(len(approx_candidate_blobs)) + "**",
            "- Files using original+HookLink because Windows is identical to older HookLink: **" + str(len(identical)) + "**",
            "- Nonconflicting Windows-specific three-way patches: **" + str(len(updated)) + "**",
            "- Windows-only additions: **" + str(len(additions)) + "**",
            "- Windows-only modifications without competing changes: **" + str(len(retained)) + "**",
            "- Unresolved Windows-versus-original+HookLink conflicts: **" + str(len(report_conflicts)) + "**",
            "- Official source regressions in critical functions: **" + str(len(missing)) + "**", "",
            "This is a **DRY RUN**. A conflicting file is listed for manual",
            "hunk resolution and **is not approved**. No engine or release was modified.",
            "", "## Strict NXnative+HookLink source conflicts", "",
        ]
        text += ["- " + Q + x + Q for x in original_hook_conflicts] or ["None."]
        text += ["", "## Windows delta conflicts requiring manual source merge", ""]
        text += ["- " + Q + x + Q + ": " + why for x,why in report_conflicts] or ["None."]
        text += ["", "## Clean Windows-specific source merges", ""]
        text += ["- " + Q + x + Q for x in updated] or ["None."]
        text += ["", "## Windows-only additions preserved", ""]
        text += ["- " + Q + x + Q for x in additions] or ["None."]
        text += ["", "## Windows-only modifications with no competing source change", ""]
        text += ["- " + Q + x + Q for x in retained] or ["None."]
        text += ["", "## Missing critical functions", ""]
        text += ["- " + Q + x + Q for x in missing] or ["None."]
        report.parent.mkdir(exist_ok=True,parents=True)
        report.write_text("\n".join(text) + "\n",encoding="utf-8")
        print(json.dumps({
            "old_hook_conflicts": original_hook_conflicts,
            "Windows_vs_merged_upstream_conflicts": report_conflicts,
            "clean_windows_patches": len(updated),
            "windows_modifications_without_competing_change": len(retained),
            "windows_additions": len(additions),
            "files_considered": len(approx_candidate_blobs),
            "critical_functions_missing": missing
        }, indent=2),flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report",type=Path,default=ROOT/"upstream-first-dryrun.md")
    args = ap.parse_args()
    preview(args.report)
