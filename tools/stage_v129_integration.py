#!/usr/bin/env python3
"""Materialize an upstream-first X3/NXnative integration in a detached workspace.

Known independent conflict hunks are reconciled here. Every remaining hunk is
reported as BLOCKED; a provisional selection is used solely to make a source
snapshot for inspection. This tool never pushes an engine or publishes a release.
"""
from pathlib import Path
import argparse
import json
import re
import subprocess
import tempfile
from audit_v128_integration import (
    ROOT, OLD_WINDOWS, OLD_ORIGINAL, NEW_ORIGINAL, OLD_HOOK, NEW_HOOK,
    OLD_APP, NEW_APP, OFFICIAL_URL, HOOK_URL, APP_URL,
    git, out, blob, commit_tree, audit_merge, api_review,
)

HUNK = re.compile(r"^<<<<<<<[^\n]*\n(.*?)^\|\|\|\|\|\|\|[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*(?:\n|$)", re.M | re.S)
# These are the exact conflict counts of the pinned official and X3 heads;
# a change in the conflict layout cannot silently select another hunk.
EXPECTED = {
    ".github/workflows/tests.yml": 1,
    "dm/games/0400486024DEC000/README.md": 1,
    "dm/games/0400486024DEC000/patches.py": 2,
    "dm/games/settings.tsv": 3,
    "dm/gfx/nvn/hle_nvn.c": 4,
    "dm/gfx/nvn/nvn_mtl.m": 22,
    "dm/gfx/tests/Makefile": 1,
    "dm/host/Makefile": 1,
    "dm/host/hle_thread.c": 1,
    "dm/host/main.c": 1,
    "dm/host/tests/Makefile": 2,
    "dm/host/tests/t_svc_memory.c": 1,
    "dm/ios/Sources/DmIOS-Bridging-Header.h": 2,
    "dm/ios/Sources/GameMenu.swift": 2,
    "dm/ios/Sources/Launcher.swift": 2,
    "dm/ios/Sources/front_ios.m": 1,
    "dm/mac/Launcher.swift": 2,
    "dm/tools/patch_nso.py": 1,
    "dm/tools/tests/test_launcher_settings.py": 2,
    "docs/agents/game-patches.md": 1,
    "docs/env_switches.tsv": 8,
    "docs/settings.md": 3,
}


def replace_once(s, old, new):
    if s.count(old) != 1:
        raise ValueError("expected exact source anchor: " + old)
    return s.replace(old, new, 1)


def combine(a, b):
    return a.rstrip("\n") + "\n" + b


def reconcile(path, i, official, base, hook):
    """Only independent/explicitly reconciled edits return a non-None result."""
    if path == "dm/games/settings.tsv" and i == 1:
        if not hook.startswith("DM_UPSCALER\t") or "DM_NVN_ANISO\t" not in official:
            raise ValueError("unexpected settings row")
        return combine(hook, "\n".join(x for x in official.splitlines() if x.startswith("DM_NVN_ANISO\t")))
    if path == "dm/gfx/nvn/hle_nvn.c" and i == 0:
        if "dm_device_share(share_mem," not in official or "mtl_preread(o->mem" not in hook:
            raise ValueError("unexpected pool-share hunk")
        return combine(official, "\n".join(x for x in hook.splitlines() if "mtl_preread(o->mem" in x))
    if path == "dm/gfx/nvn/nvn_mtl.m":
        if i == 1:
            return replace_once(hook, "static int g_npost, g_postcap;", "static size_t g_npost, g_postcap;")
        if i in (2, 5, 18, 20) and not base.strip():
            return combine(official, hook)
        if i == 3:
            return replace_once(official, "nvn_shadow_writeback(ops[i].addr, sizeof rec);", "nvn_shadow_writeback(ops[i].addr, sizeof rec); vis_report_done(ops[i].addr);")
        if i == 6:
            row = hook.splitlines()[0]
            if "pool_census(frame)" not in row:
                raise ValueError("unexpected pool census")
            return combine(row, official)
        if i == 7:
            row = hook.splitlines()[0]
            if "g_pbase_epoch" not in row:
                raise ValueError("unexpected archive epoch")
            return combine(row, official)
        if i == 12:
            return replace_once(official, "g_tu_now - g_tu_last >= 10", "g_tu_now - g_tu_last >= TU_EVERY")
        if i == 13:
            return replace_once(official, '!tex_level_ok(mt, level, "CPU readback")', '!lv_host(t, mt, &level) || !tex_level_ok(mt, level, "CPU readback")')
        if i == 14 and not base.strip():
            return combine(hook, official)
        if i == 15:
            return replace_once(official, "hw_note(ad);", "hw_note(ad); occ_report(ad);")
        if i == 16:
            row = hook.splitlines()[-1]
            if "g_up_chain_in" not in row:
                raise ValueError("unexpected upscaler chain")
            return combine(official, row)
        if i == 17:
            return replace_once(replace_once(hook, "{ g_link_empty++;", "{ g_link_latch_health.prev = 0; g_link_empty++;"), "if (hold) { g_link_held++;", "if (hold) { g_link_latch_health.prev = 0; g_link_held++;")
        if i == 19:
            return replace_once(official, "present_now(&it.t,", "present_now(gen ? &gt : &it.t,")
        if i == 21:
            return replace_once(official, "&& link_30hz())", "&& link_30hz() && !fg_on())")
        # Heap trimming, alias retirement, pending/archive PSO ownership, and
        # package eviction interact across the file. Do not auto-approve them.
        return None
    if path == "dm/gfx/tests/Makefile" and not base.strip():
        return combine(official, hook)
    if path == "dm/host/Makefile":
        return replace_once(official, "haptics_apple.m audio_input.c", "haptics_apple.m mic_apple.m audio_input.c")
    if path == "dm/host/hle_thread.c":
        first = "\n".join(hook.splitlines()[:2])
        if "frame_thread;" not in first or "bg_thread;" not in first:
            raise ValueError("unexpected thread QoS fields")
        return combine(first, official)
    if path == "dm/host/main.c" and not base.strip():
        return combine(official, hook)
    if path == "dm/host/tests/Makefile":
        if i == 0:
            return official.rstrip("\n") + " $(B)/t_dump_live\n"
        if i == 1:
            return replace_once(hook, base.rstrip("\n"), official.rstrip("\n"))
    if path == "dm/host/tests/t_svc_memory.c":
        return replace_once(official, "file_rule(); file_sweep();", "file_rule(); file_unbacked(); file_sweep();")
    if path == "dm/ios/Sources/DmIOS-Bridging-Header.h":
        if i == 0:
            return replace_once(official, "the screen's rate", "mods_api.h's mods, the screen's rate")
        return combine('#include "mods_api.h"   // Mods.swift: mod checks and import', official)
    if path == "dm/ios/Sources/GameMenu.swift":
        if i == 0:
            return replace_once(replace_once(hook, '"Tap"', 'GameMenuText.tap.text'), '(0..<5)', '(0..<5)')
        return replace_once(hook, 'title: "Controller layout"', 'title: GameMenuText.controllerLayout.text')
    if path == "dm/ios/Sources/front_ios.m" and not base.strip():
        return combine(official, hook)
    if path == "docs/env_switches.tsv":
        # Combine independent newly introduced keys. Do not overwrite a
        # conflicting definition (e.g. FPS state semantics or mic gain).
        rows_a = official.splitlines()
        rows_b = hook.splitlines()
        keys_a = {x.split("\t", 1)[0] for x in rows_a if "\t" in x}
        keys_b = {x.split("\t", 1)[0] for x in rows_b if "\t" in x}
        if not keys_a.intersection(keys_b):
            return "\n".join(sorted(rows_a + rows_b, key=lambda x: x.split("\t", 1)[0])) + "\n"
    return None


def staged_merge(cwd, left, right, stage, dest, summary):
    git(cwd, "checkout", "--quiet", "--detach", left)
    p = git(cwd, "-c", "merge.conflictStyle=diff3", "merge", "--no-commit", "--no-ff", right, check=False)
    paths = out(cwd, "diff", "--name-only", "--diff-filter=U").splitlines()
    if p.returncode and not paths:
        raise RuntimeError("merge failed outside a textual conflict: " + p.stderr.decode(errors="replace")[-3000:])
    if stage == "upstream" and set(paths) != set(EXPECTED):
        raise RuntimeError("exact upstream conflict paths changed; review the new range before applying any resolution")
    records = []
    for path in paths:
        file = cwd / path
        raw = file.read_bytes() if file.is_file() else b""
        src = raw.decode("utf-8", errors="replace") if b"\0" not in raw else ""
        matches = list(HUNK.finditer(src))
        save = dest / "conflicts" / stage / (path + ".diff3")
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_bytes(raw)
        if stage == "upstream" and len(matches) != EXPECTED[path]:
            raise RuntimeError("exact upstream hunk count changed: " + path + " got " + str(len(matches)))
        if not matches:
            records.append({"path": path, "hunk": 0, "status": "BLOCKED", "reason": "binary or non-text conflict"})
            if git(cwd, "show", ":3:" + path, check=False).returncode == 0:
                git(cwd, "checkout", "--theirs", "--", path); git(cwd, "add", "--", path)
            else:
                git(cwd, "rm", "-f", "--", path)
            continue
        idx = 0
        def resolve(m):
            nonlocal idx
            i = idx
            idx += 1
            a, b, c = m.groups()
            replacement = None
            if stage == "upstream":
                try:
                    replacement = reconcile(path, i, a, b, c)
                except ValueError as exc:
                    records.append({"path": path, "hunk": i + 1, "status": "BLOCKED", "reason": str(exc)})
                    return c
            else:
                # In the replay, only identical source hunks / known compiler
                # import union can be taken without another semantic review.
                if a.strip() == c.strip():
                    replacement = a
                elif path == "dm/gfx/tools/dmsh_build.py" and "import atexit, errno" in a and "BrokenProcessPool" in c:
                    replacement = combine(a, "from concurrent.futures.process import BrokenProcessPool")
            status = "reconciled" if replacement is not None else "BLOCKED"
            records.append({"path": path, "hunk": i + 1, "status": status,
                            "reason": "explicit reviewed combination" if replacement is not None else "provisional right side for inspection only"})
            return (replacement if replacement is not None else c).rstrip("\n") + "\n"
        file.write_text(HUNK.sub(resolve, src), encoding="utf-8")
        git(cwd, "add", "--", path)
    result = commit_tree(cwd, out(cwd, "write-tree"), left, "Detached integration preview: " + stage)
    git(cwd, "reset", "--hard", result)
    summary[stage] = records
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    summary = {"approval": False, "publication": False}
    try:
        with tempfile.TemporaryDirectory(prefix="hlw-v129-") as temp:
            cwd = Path(temp) / "engine"
            subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                            "--branch", "hooklink", HOOK_URL, str(cwd)], check=True)
            git(cwd, "config", "user.name", "HookLinkWindows integration preview")
            git(cwd, "config", "user.email", "integration@users.noreply.github.com")
            git(cwd, "remote", "add", "official", OFFICIAL_URL)
            git(cwd, "fetch", "--quiet", "--filter=blob:none", "official", OLD_ORIGINAL, NEW_ORIGINAL)
            git(cwd, "fetch", "--quiet", "--filter=blob:none", "origin", OLD_HOOK, NEW_HOOK)
            # Use the same explicitly provisional historical reference as
            # the earlier audit to isolate Windows' actual historical delta.
            old_report, old_summary = [], {}
            old_ref = audit_merge(cwd, OLD_ORIGINAL, OLD_HOOK, "previous_reference", old_report, old_summary)
            upstream = staged_merge(cwd, NEW_ORIGINAL, NEW_HOOK, "upstream", dest, summary)
            current = out(ROOT, "rev-parse", "HEAD")
            git(cwd, "fetch", "--quiet", "--no-tags", str(ROOT), current)
            actual = out(cwd, "rev-parse", current + ":engine")
            w = commit_tree(cwd, actual, old_ref, "Actual main engine with Windows deltas")
            target = commit_tree(cwd, out(cwd, "rev-parse", upstream + "^{tree}"), old_ref, "Staged upstream+X3 tree")
            final = staged_merge(cwd, target, w, "windows", dest, summary)
            # This is a real source diff for continued work, NOT a release.
            # It includes all clean changes and the explicitly reconciled
            # hunks; every provisional unresolved choice is enumerated.
            with (dest / "unapproved-engine.patch").open("wb") as f:
                f.write(git(cwd, "diff", "--binary", w, final).stdout)
            git(cwd, "remote", "add", "hookapp", APP_URL)
            git(cwd, "fetch", "--quiet", "--no-tags", "hookapp", OLD_APP, NEW_APP)
            (dest / "hooklink-desktop.patch").write_bytes(git(cwd, "diff", "--binary", OLD_APP, NEW_APP).stdout)
            summary["base_main"] = current
            summary["official"] = NEW_ORIGINAL
            summary["hooklink_engine"] = NEW_HOOK
            summary["hooklink_app"] = NEW_APP
            summary["engine_changed_paths"] = len(out(cwd, "diff", "--name-only", w, final).splitlines())
            summary["counts"] = {stage: {status: sum(x["status"] == status for x in summary[stage])
                                        for status in ("reconciled", "BLOCKED")}
                                 for stage in ("upstream", "windows")}
            api_review(cwd, final, [], summary)
    finally:
        (dest / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
