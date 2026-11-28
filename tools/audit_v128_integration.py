#!/usr/bin/env python3
"""Read-only X3 + latest official NXnative + Windows integration audit.

All merge operations occur in a temporary detached Git checkout. Conflict
preferences are used ONLY to preview subsequent merge stages; no conflicted
result is approved, installed, committed to main or released by this script.
"""
from pathlib import Path
import argparse
import ast
import json
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OLD_WINDOWS = "57c24fb38b840bda7e916c52a5d63cbd02ea9de9"
OLD_ORIGINAL = "3e1ada5b96acb61293ac790bd6dd093a947abed6"
NEW_ORIGINAL = "5dfc86ae80c53a62262c3b3c66eab043f1fc574a"
OLD_HOOK = "698b46bc5b14510fffc0a4b8fd4bf78309004e4c"
NEW_HOOK = "ee3ce6a02bc737d38795f0a96cce494cee7a799c"
OLD_APP = "d04e664d253aafbd77a8fc543f6ed3c7d91d5dde"
NEW_APP = "b5c41acf469edb99abc5156f1f6f18397261f54a"
OFFICIAL_URL = "https://github.com/seedds/nxnative.git"
HOOK_URL = "https://github.com/dsi-hub/nxnative.git"
APP_URL = "https://github.com/dsi-hub/HookLink.git"


def git(cwd, *args, check=True):
    p = subprocess.run(["git", *map(str, args)], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError(str(args[:5]) + ": " + p.stderr.decode(errors="replace")[-4000:])
    return p


def out(cwd, *args):
    return git(cwd, *args).stdout.decode().strip()


def blob(cwd, rev, path):
    p = git(cwd, "show", rev + ":" + path, check=False)
    return None if p.returncode else p.stdout


def diffpaths(cwd, a, b):
    return git(cwd, "diff", "--name-only", "-z", a, b).stdout.decode(errors="surrogateescape").strip("\0").split("\0")


def commit_tree(cwd, tree, parent, label):
    args = ["commit-tree", tree]
    if parent:
        args += ["-p", parent]
    return out(cwd, *args, "-m", label)


def audit_merge(cwd, left, right, label, report, summary, prefer="theirs"):
    if prefer not in ("ours", "theirs"):
        raise ValueError("Invalid preview preference")
    ancestor = out(cwd, "merge-base", left, right)
    git(cwd, "checkout", "--quiet", "--detach", left)
    p = git(cwd, "-c", "merge.conflictStyle=diff3", "merge", "--no-commit", "--no-ff", right, check=False)
    conflict_paths = [x for x in out(cwd, "diff", "--name-only", "--diff-filter=U").splitlines() if x]
    if p.returncode and not conflict_paths:
        raise RuntimeError(label + ": " + p.stderr.decode(errors="replace")[-4000:])
    summary[label] = {"left": left, "right": right, "ancestor": ancestor,
                      "conflicts": conflict_paths}
    print(label, "ancestor", ancestor, "conflicts", len(conflict_paths), flush=True)
    for path in conflict_paths:
        print("CONFLICT", label, path, flush=True)
        report.extend(["### " + label + ": " + path, "", "Unmerged index:", "",
                       "~~~text", out(cwd, "ls-files", "-u", "--", path), "~~~", ""])
        file = cwd / path
        if file.is_file():
            raw = file.read_bytes()
            if b"\0" not in raw:
                lines = raw.decode(errors="replace").splitlines()
                hunks, active = [], []
                for line in lines:
                    if line.startswith("<<<<<<<"):
                        active = [line]
                    elif active:
                        active.append(line)
                        if line.startswith(">>>>>>>"):
                            hunks += active + [""]
                            active = []
                if hunks:
                    report.extend(["~~~diff", *hunks, "~~~", ""])
                else:
                    report.append("No textual conflict markers (rename, deletion, mode or binary conflict).")
    # A clean merge is exact. Otherwise prefer the requested side ONLY in
    # overlapping hunks for the next diagnostic stage, never for publication.
    if conflict_paths:
        git(cwd, "merge", "--abort")
        p = git(cwd, "merge", "--no-commit", "--no-ff", "-X", prefer, right, check=False)
        remaining = out(cwd, "diff", "--name-only", "--diff-filter=U").splitlines()
        for path in remaining:
            # Use stage 3 when present, else a provisional removal. These
            # choices are explicitly recorded and are not merge approval.
            stage = "2" if prefer == "ours" else "3"
            selected = git(cwd, "show", ":" + stage + ":" + path, check=False)
            if selected.returncode == 0:
                git(cwd, "checkout", "--" + prefer, "--", path)
                git(cwd, "add", "--", path)
            else:
                git(cwd, "rm", "-f", "--", path)
        if p.returncode and not remaining:
            # Git may have returned nonzero for conflicts already resolved by
            # its preference; require an actually writable index below.
            pass
        summary[label]["provisional_only"] = True
        summary[label]["preview_preference"] = prefer
        summary[label]["provisional_file_level_choices"] = remaining
    tree = out(cwd, "write-tree")
    result = commit_tree(cwd, tree, left, "Temporary audit result: " + label)
    # Reset the scratch worktree only, not the project checkout.
    git(cwd, "reset", "--hard", result)
    return result


def api_review(cwd, reference, report, summary):
    """Compare upstream function definitions against the existing wrapper's calls."""
    filename = "scripts/build_ipa_from_nsp.py"
    old = blob(cwd, OLD_ORIGINAL, filename)
    new = blob(cwd, reference, filename)
    wrapper = (ROOT / "engine/win/build_ipa_windows.py").read_text(encoding="utf-8")
    uses = {node.attr for node in ast.walk(ast.parse(wrapper))
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "up"}
    def definitions(raw):
        tree = ast.parse(raw.decode("utf-8"))
        return {n.name: ast.unparse(n.args) for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    a, b = definitions(old), definitions(new)
    changes = [{"name": n, "old": a.get(n), "new": b.get(n)}
               for n in sorted(uses) if n in a and a.get(n) != b.get(n)]
    summary["windows_driver_api_changes"] = changes
    report.extend(["## Windows driver interface changes (review before IPA)", "", "~~~json",
                   json.dumps(changes, indent=2), "~~~", ""])


def app_review(cwd, report, summary):
    git(cwd, "remote", "add", "hookapp", APP_URL)
    git(cwd, "fetch", "--quiet", "--no-tags", "hookapp", OLD_APP, NEW_APP)
    paths = diffpaths(cwd, OLD_APP, NEW_APP)
    rows = []
    for path in paths:
        if not path:
            continue
        old, new = blob(cwd, OLD_APP, path), blob(cwd, NEW_APP, path)
        w = blob(cwd, OLD_WINDOWS, path)
        state = "Windows equals old upstream; incoming change can replace it" if w == old else (
            "Already identical to new upstream" if w == new else "Windows-specific difference requires review")
        rows.append({"path": path, "state": state})
        if path.endswith(".swift"):
            patch = out(cwd, "diff", OLD_APP, NEW_APP, "--", path)
            report.extend(["### HookLink desktop change: " + path, "", "~~~diff", patch, "~~~", ""])
    summary["hooklink_desktop_changes"] = rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    opts = parser.parse_args()
    dest = opts.output.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    report = ["# V1.2.8 read-only integration audit", "",
              "No engine files, version pins or releases are changed by this workflow.", "",
              "Official NXnative: " + OLD_ORIGINAL + " -> " + NEW_ORIGINAL,
              "HookLink engine: " + OLD_HOOK + " -> " + NEW_HOOK,
              "HookLink desktop: " + OLD_APP + " -> " + NEW_APP, ""]
    summary = {}
    try:
        with tempfile.TemporaryDirectory(prefix="hlw-v128-audit-") as td:
            cwd = Path(td) / "engine"
            subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                            "--branch", "hooklink", HOOK_URL, str(cwd)], check=True)
            git(cwd, "config", "user.name", "HookLinkWindows integration audit")
            git(cwd, "config", "user.email", "audit@users.noreply.github.com")
            git(cwd, "remote", "add", "official", OFFICIAL_URL)
            git(cwd, "fetch", "--quiet", "--filter=blob:none", "official", OLD_ORIGINAL, NEW_ORIGINAL)
            git(cwd, "fetch", "--quiet", "--filter=blob:none", "origin", OLD_HOOK, NEW_HOOK)
            git(cwd, "merge-base", "--is-ancestor", OLD_ORIGINAL, NEW_ORIGINAL)
            git(cwd, "merge-base", "--is-ancestor", OLD_HOOK, NEW_HOOK)
            git(cwd, "merge-base", "--is-ancestor", OLD_ORIGINAL, NEW_HOOK)
            summary["official_commits"] = int(out(cwd, "rev-list", "--count", OLD_ORIGINAL + ".." + NEW_ORIGINAL))
            summary["hooklink_engine_commits"] = int(out(cwd, "rev-list", "--count", OLD_HOOK + ".." + NEW_HOOK))
            summary["official_changed_paths"] = len(diffpaths(cwd, OLD_ORIGINAL, NEW_ORIGINAL))
            summary["hooklink_changed_paths"] = len(diffpaths(cwd, OLD_HOOK, NEW_HOOK))
            # Reconstruct the prior upstream+HookLink reference. All differences
            # in the real V1.2.7 tree are then treated as historical integration
            # decisions, not as a blanket list of Windows-preserved filenames.
            old_ref = audit_merge(cwd, OLD_ORIGINAL, OLD_HOOK, "previous_reference", report, summary)
            new_ref = audit_merge(cwd, NEW_ORIGINAL, NEW_HOOK, "latest_original_plus_x3", report, summary)
            git(cwd, "fetch", "--quiet", "--no-tags", str(ROOT), OLD_WINDOWS)
            actual = out(cwd, "rev-parse", OLD_WINDOWS + ":engine")
            w = commit_tree(cwd, actual, old_ref, "Temporary V1.2.7 integrated engine snapshot")
            target = commit_tree(cwd, out(cwd, "rev-parse", new_ref + "^{tree}"), old_ref,
                                 "Temporary latest upstream plus X3 snapshot")
            preview = audit_merge(cwd, target, w, "windows_delta", report, summary)
            api_review(cwd, preview, report, summary)
            app_review(cwd, report, summary)
            summary["preview_is_not_approved"] = True
            summary["engine_changes_applied"] = False
    finally:
        report.extend(["## Summary", "", "~~~json", json.dumps(summary, indent=2), "~~~", ""])
        (dest / "review.md").write_text("\n".join(report), encoding="utf-8")
        (dest / "summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
