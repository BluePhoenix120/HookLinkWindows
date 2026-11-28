#!/usr/bin/env python3
"""Audit the complete next upstream delta against the tested Windows tree.
No remote branch, release, engine source or pin is changed by this tool.
"""
from pathlib import Path
import argparse
import ast
import json
import subprocess
import tempfile

from audit_v128_integration import ROOT, git, out, commit_tree, audit_merge, diffpaths

TARGET = "f36fa59becd8b3ffc4347e6f9d58e45fe4e51bdf"
BASE = "5dfc86ae80c53a62262c3b3c66eab043f1fc574a"

def definitions(data):
    return {n.name: ast.unparse(n.args) for n in ast.parse(data).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    pin = json.loads((ROOT / "ENGINE_PIN.json").read_text(encoding="utf-8"))
    if pin["nxnative_commit"] != BASE or pin["release"] != "Alpha V1.3.3":
        raise RuntimeError("Working baseline changed; review new inputs before integration")
    local = out(ROOT, "rev-parse", "HEAD")
    report = ["# V1.3.4 official-first upstream audit", "", "Provisional only; no engine changes published.",
              "Policy: prefer official NXnative for identical, similar or overlapping functionality; retain only independent HookLink features and required Windows/mod compatibility.",
              "", f"Official: {BASE} -> {TARGET}", f"Windows: {local}", ""]
    summary = {"base": BASE, "target": TARGET, "windows": local,
               "policy": "official-first; retain unique HookLink features and Windows compatibility",
               "semantic_review_complete": False}
    try:
        with tempfile.TemporaryDirectory(prefix="hlw-v134-") as tmp:
            cwd = Path(tmp)
            git(cwd, "init", "--quiet")
            git(cwd, "config", "user.name", "HookLinkWindows audit")
            git(cwd, "config", "user.email", "audit@users.noreply.github.com")
            git(cwd, "remote", "add", "official", "https://github.com/seedds/nxnative.git")
            git(cwd, "fetch", "--quiet", "--no-tags", "official", BASE, TARGET)
            git(cwd, "merge-base", "--is-ancestor", BASE, TARGET)
            git(cwd, "fetch", "--quiet", "--no-tags", str(ROOT), local)
            windows = commit_tree(cwd, out(cwd, "rev-parse", local + ":engine"), BASE,
                                  "Tested HookLink and Windows changes over pinned original")
            paths = diffpaths(cwd, BASE, TARGET)
            summary["official_commits"] = int(out(cwd, "rev-list", "--count", BASE + ".." + TARGET))
            summary["upstream_paths"] = len(paths)
            (dest / "upstream-paths.txt").write_text("\n".join(paths) + "\n", encoding="utf-8")
            # Official latest is first. Textual conflicts prefer official source,
            # but the resulting tree still needs a separate semantic review.
            result = audit_merge(cwd, TARGET, windows, "incremental", report, summary, prefer="ours")
            # A Mac-only prebuilt translator must never enter the Windows distribution.
            # Leave the actual compiler lock/header reconciliation to integration.
            for p in ("dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate", "dm/gfx/tools/spirv_cross_bin/spirv-cross"):
                git(cwd, "rm", "--ignore-unmatch", "-f", "--", p)
            result = commit_tree(cwd, out(cwd, "write-tree"), result, "Exclude foreign prebuilt tools from preview")
            git(cwd, "reset", "--hard", result)
            # Review ALL differences from official source, including clean merges,
            # because redundant behavior can survive without a Git conflict.
            custom = out(cwd, "diff", "--name-status", "--no-renames", TARGET, result)
            (dest / "remaining-custom-paths.txt").write_text(custom + "\n", encoding="utf-8")
            summary["remaining_custom_paths"] = len(custom.splitlines())
            for name, first, second in (("previous-custom-delta.patch", BASE, windows),
                                         ("remaining-custom-delta.patch", TARGET, result),
                                         ("official-delta.patch", BASE, TARGET)):
                with (dest / name).open("wb") as stream:
                    subprocess.run(["git", "diff", "--no-ext-diff", "--no-renames", first, second],
                                   cwd=cwd, stdout=stream, check=True)
            report.extend(["## Semantic review inventory", "",
                           "Review every remaining custom path, not just conflicts. Full textual deltas are attached.", "",
                           "~~~text", custom, "~~~", ""])
            summary["provisional_tree"] = out(cwd, "rev-parse", result + "^{tree}")
            summary["provisional_changed_paths"] = len(diffpaths(cwd, windows, result))
            (dest / "candidate-paths.txt").write_text(out(cwd, "diff", "--name-status", windows, result) + "\n", encoding="utf-8")
            wrapper = (ROOT / "engine/win/build_ipa_windows.py").read_text(encoding="utf-8")
            used = {n.attr for n in ast.walk(ast.parse(wrapper))
                    if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "up"}
            old = definitions(git(cwd, "show", windows + ":scripts/build_ipa_from_nsp.py").stdout)
            new = definitions(git(cwd, "show", result + ":scripts/build_ipa_from_nsp.py").stdout)
            summary["driver_api_changes"] = [{"name": n, "old": old.get(n), "new": new.get(n)}
                                              for n in sorted(used) if old.get(n) != new.get(n)]
            report.extend(["## Windows driver API changes", "", "```json",
                           json.dumps(summary["driver_api_changes"], indent=2), "```", ""])
            # Preserve the complete text conflict report, with no truncation.
            # Never execute the provisional engine or automatically approve it.
            report.extend(["## Follow-up", "",
                           "Restore the official frame-step ABI end to end (+0x38 tick unit, native patches for both game versions, host writer and reader, tests); remove competing HookLink timing writes and stale relocated offsets.",
                           "Review official MetalFX, texture lifetime, render-pass and memory optimizations against ALL remaining custom hunks; remove equivalent implementations even when Git merged them cleanly.",
                           "Retain distinct HookLink launcher customization, mod features, independent audio work only where not superseded, and all Windows-specific functionality including BodiesOfTruth code cuts and packed RomFS.",
                           "Reconcile PSO manifests by pipeline key, drop obsolete standalone S rows and follow official workspace-generated shader tables; preserve compatible unique observations.",
                           "Review C1 validation, Windows shader toolchain, native ABI, progress and cache paths. Only a reviewed integration may update the pin and release."])
    finally:
        (dest / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        (dest / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    main()
