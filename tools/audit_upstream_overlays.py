#!/usr/bin/env python3
"""Read-only complete upstream/HookLink/Windows difference audit.

A file labeled Windows-preserved is never automatically treated as a valid
override. Compare original NXnative, the true HookLink engine fork, and
the integrated Windows source. Does not modify engine or publish releases.
"""
from __future__ import annotations
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = "https://github.com/seedds/nxnative.git"
HOOKLINK = "https://github.com/dsi-hub/nxnative.git"
Q = chr(96)


def run(*args, cwd=ROOT, check=True):
    proc = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode:
        raise RuntimeError(str(args[:6]) + ": " + proc.stderr.decode(errors="replace")[-2500:])
    return proc


def git(*args, cwd, check=True):
    return run("git", *args, cwd=cwd, check=check)


def content(repo, rev, path):
    proc = git("show", rev + ":" + path, cwd=repo, check=False)
    return proc.stdout if not proc.returncode else None


def blob(data):
    if data is None:
        return None
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def symbols(raw):
    if raw is None:
        return {}
    try:
        s = raw.decode("utf-8")
        t = ast.parse(s)
    except (UnicodeDecodeError, SyntaxError):
        return {}
    lines = s.splitlines(keepends=True)
    result = {}
    def walk(items, prefix=""):
        for node in items:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                result[name] = "".join(lines[node.lineno - 1:node.end_lineno]).strip()
                if isinstance(node, ast.ClassDef):
                    walk(node.body, name + ".")
    walk(t.body)
    return result


def changed_lines(u, w):
    if u is None or w is None:
        return -1
    a = u.decode("utf-8", "replace").splitlines()
    b = w.decode("utf-8", "replace").splitlines()
    sm = difflib.SequenceMatcher(None, a, b)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def scan(out):
    pin = json.loads((ROOT / "ENGINE_PIN.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "ENGINE_PIN_FILES.json").read_text(encoding="utf-8"))
    target = pin["nxnative_commit"]
    hook = pin["hooklink_engine_commit"]
    if pin["nxnative_repo"] != ORIGINAL or manifest["nxnative_commit"] != target:
        raise RuntimeError("Original NXnative pin/manifest disagree")
    if pin["hooklink_engine_repo"] != HOOKLINK or manifest["hooklink_engine_commit"] != hook:
        raise RuntimeError("HookLink pin/manifest disagree")
    listed = sorted(set(manifest["windows_overlays"]) | set(manifest["integration_overrides"]))
    if any(not x.startswith("engine/") or ".." in Path(x).parts for x in listed):
        raise RuntimeError("Unsafe manifest source paths")
    with tempfile.TemporaryDirectory(prefix="nxnative-source-audit-") as tmp:
        clone = Path(tmp) / "engine"
        run("git", "clone", "--quiet", "--filter=blob:none", "--branch", "hooklink", HOOKLINK, str(clone))
        if git("rev-parse", "HEAD", cwd=clone).stdout.decode().strip() != hook:
            raise RuntimeError("HookLink HEAD has advanced; pin must be reviewed")
        git("remote", "add", "official", ORIGINAL, cwd=clone)
        git("fetch", "--quiet", "--filter=blob:none", "official", target, cwd=clone)
        latest = git("ls-remote", ORIGINAL, "refs/heads/main", cwd=clone).stdout.decode().split()[0]
        merge_base_result = git("merge-base", target, hook, cwd=clone, check=False)
        ancestor = merge_base_result.stdout.decode().strip() if merge_base_result.returncode == 0 else None
        refmerge = None
        refproblem = "No shared ancestor" if not ancestor else ""
        if ancestor:
            git("config", "user.name", "NXnative audit", cwd=clone)
            git("config", "user.email", "audit@users.noreply.github.com", cwd=clone)
            git("switch", "--detach", target, cwd=clone)
            # Upstream-first reference. HookLink changed hunks win overlaps.
            result = git("merge", "--no-ff", "--no-edit", "-X", "theirs", hook, cwd=clone, check=False)
            unmerged = git("diff", "--name-only", "--diff-filter=U", cwd=clone).stdout.decode().splitlines()
            if result.returncode or unmerged:
                refproblem = "Needs manual conflict resolution: " + ", ".join(unmerged[:25])
                git("merge", "--abort", cwd=clone, check=False)
            else:
                refmerge = git("rev-parse", "HEAD", cwd=clone).stdout.decode().strip()
        rows = []
        stale = []
        absent = []
        bad_hash = []
        for fullpath in listed:
            rel = fullpath[7:]
            localpath = ROOT / fullpath
            W = localpath.read_bytes() if localpath.is_file() else None
            U = content(clone, target, rel)
            H = content(clone, hook, rel)
            B = content(clone, ancestor, rel) if ancestor else None
            R = content(clone, refmerge, rel) if refmerge else None
            if U is None:
                kind = "Windows/HookLink-only"
            elif W is None:
                kind = "MISSING official NXnative"
            elif W == U:
                kind = "Exact official NXnative"
            elif W == H and U != H:
                kind = "Legacy HookLink file retained"
            elif H == U and W != U:
                kind = "Windows modification; verify necessity"
            elif B is not None and U == B and H != B:
                kind = "HookLink change (upstream unchanged)"
            else:
                kind = "Conflicting/combined changes: review hunks"
            us = symbols(U) if fullpath.endswith(".py") else {}
            ws = symbols(W) if fullpath.endswith(".py") else {}
            hs = symbols(H) if fullpath.endswith(".py") else {}
            missing = sorted(set(us) - set(ws))
            older = sorted(n for n in set(us) & set(ws) & set(hs) if us[n] != ws[n] and ws[n] == hs[n])
            if missing:
                absent.append((fullpath, missing))
            if older:
                stale.append((fullpath, older))
            if fullpath in manifest["integration_overrides"]:
                expected = manifest["integration_overrides"][fullpath]["integrated_sha"]
                if blob(W) != expected:
                    bad_hash.append((fullpath, blob(W), expected))
            rows.append((fullpath, kind, W == H if W is not None else False,
                         U != B if B is not None else None, W == R if R is not None else None,
                         changed_lines(U, W)))
        allpaths = git("ls-tree", "-r", "--name-only", target, cwd=clone).stdout.decode().splitlines()
        missing_tree = [p for p in allpaths if not (ROOT / "engine" / p).is_file()]
        output = [
            "# Full original NXnative / HookLink / HookLinkWindows source audit", "",
            "- Original pinned: " + Q + target + Q,
            "- Original HEAD observed: " + Q + latest + Q,
            "- HookLink pinned: " + Q + hook + Q,
            "- Git common ancestor: " + Q + str(ancestor) + Q,
            "- Upstream-first HookLink reference merge: " + Q + str(refmerge) + Q,
            "- Reference issue: " + (refproblem or "none"),
            "- Differing paths in manifest: **" + str(len(rows)) + "**",
            "- Exact official blobs: **" + str(sum(r[1] == "Exact official NXnative" for r in rows)) + "**",
            "- Legacy HookLink blobs: **" + str(sum(r[1] == "Legacy HookLink file retained" for r in rows)) + "**",
            "- Python files with missing official definitions: **" + str(len(absent)) + "**",
            "- Python files with old HookLink definitions: **" + str(len(stale)) + "**",
            "- Missing files from entire original tree: **" + str(len(missing_tree)) + "**",
            "- Invalid manifest hashes: **" + str(len(bad_hash)) + "**", "",
            "This is an audit, **not a blanket approval**. A file differs from upstream until",
            "the individual HookLink/Windows changes are shown to be necessary and current.",
            "The upstream-first reference is informative, not a validated build.", "",
            "## Every differing path", "",
            "| File | Classification | Matches HookLink? | Original changed since ancestor? | Matches upstream-first reference? | Approx. changed lines |",
            "|---|---|---|---|---|---:|",
        ]
        for path, kind, hookmatch, originalchanged, reference, diffcount in rows:
            output.append("| " + Q + path + Q + " | " + kind + " | " + str(hookmatch) + " | " +
                          str(originalchanged) + " | " + str(reference) + " | " + str(diffcount) + " |")
        output.extend(["", "## Missing upstream Python definitions", ""])
        for path, names in absent:
            output.append("- " + Q + path + Q + ": " + ", ".join(Q + n + Q for n in names))
        if not absent:
            output.append("None found by AST analysis.")
        output.extend(["", "## Legacy HookLink Python definitions retained verbatim", ""])
        for path, names in stale:
            output.append("- " + Q + path + Q + ": " + ", ".join(Q + n + Q for n in names))
        if not stale:
            output.append("None found by AST analysis.")
        output.extend(["", "## Missing files from original source", ""])
        output += ["- " + Q + "engine/" + p + Q for p in missing_tree]
        if not missing_tree:
            output.append("None.")
        output.extend(["", "## Manifest SHA mismatches", ""])
        output += ["- " + Q + x + Q + ": actual=" + str(a) + ", manifest=" + str(b) for x, a, b in bad_hash]
        if not bad_hash:
            output.append("None.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(output) + "\n", encoding="utf-8")
        print(json.dumps({"latest_original":latest, "pin":target, "common_ancestor":ancestor,
            "upstream_first_reference":refmerge, "reference_issue":refproblem,
            "overlay_paths":len(rows),
            "legacy_hooklink_blobs":[r[0] for r in rows if r[1] == "Legacy HookLink file retained"],
            "missing_python_definitions":absent,
            "stale_python_definitions":stale,
            "missing_official_files":missing_tree,
            "bad_hashes":bad_hash}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / "upstream-audit.md")
    args = parser.parse_args()
    scan(args.report)
