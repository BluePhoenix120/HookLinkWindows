#!/usr/bin/env python3
"""Build a real X3-first integration in the CI checkout, not a provisional merge.

Official NXnative is the first parent of the scratch engine merge; HookLink
wins overlapping changes. The current Windows delta is replayed on that
result, preserving its independent additions. Nothing is pushed or tagged
by this script. Validation and publication are separate steps.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from audit_v128_integration import (
    ROOT, OLD_ORIGINAL, NEW_ORIGINAL, OLD_HOOK, NEW_HOOK, OLD_APP, NEW_APP,
    OFFICIAL_URL, HOOK_URL, APP_URL, git, out, blob, commit_tree, audit_merge,
)

EXCLUDE = {"dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate", "dm/gfx/tools/spirv_cross_bin/spirv-cross"}
LOCK = "dm/gfx/tools/dmsh_chain.lock"
HUNK = re.compile(r"(?m)^<<<<<<<[^\n]*\n")
MARKERS = re.compile(rb"(?m)^(?:<<<<<<< |>>>>>>> |[|]{7} )")
POLICY = ("Official NXnative base; HookLink X3 wins overlapping upstream hunks; "
          "independent Windows changes replayed; Windows toolchain lock retained and regenerated locally.")


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def source(cwd, rev, path):
    data = blob(cwd, rev, path)
    require(data is not None, "Missing " + rev + ":" + path)
    return data.decode("utf-8")


def replace_once(s, old, new):
    require(s.count(old) == 1, "Expected one source anchor: " + old[:140])
    return s.replace(old, new, 1)


def inventory(cwd, rev):
    rows = {}
    for row in git(cwd, "ls-tree", "-r", "-z", rev).stdout.split(b"\0"):
        if not row:
            continue
        meta, path = row.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        if kind == "blob":
            rows[path.decode()] = (mode, sha)
    return rows


def merge(cwd, left, right, label, prefer, report):
    git(cwd, "checkout", "--quiet", "--detach", left)
    p = git(cwd, "-c", "merge.conflictStyle=diff3", "merge", "--no-commit", "--no-ff", right, check=False)
    conflicts = out(cwd, "diff", "--name-only", "--diff-filter=U").splitlines()
    require(not p.returncode or conflicts, "Git merge failed outside conflict handling: " + p.stderr.decode(errors="replace"))
    decisions = []
    for path in conflicts:
        raw = (cwd/path).read_bytes() if (cwd/path).is_file() else b""
        count = len(HUNK.findall(raw.decode(errors="replace"))) if b"\0" not in raw else 0
        decisions.append({"path": path, "hunks": count or 1, "choice": prefer, "resolution": "Git hunk-level preference" if count else "Explicit non-text resolution"})
    if conflicts:
        git(cwd, "merge", "--abort")
        p = git(cwd, "merge", "--no-commit", "--no-ff", "-X", prefer, right, check=False)
        remaining = out(cwd, "diff", "--name-only", "--diff-filter=U").splitlines()
        for path in remaining:
            # A Windows-excluded Mac binary stays absent. For any other
            # non-text conflict the documented side wins, including deletions.
            stage = "3" if prefer == "theirs" else "2"
            if path in EXCLUDE and label == "windows":
                git(cwd, "rm", "-f", "--", path)
            elif git(cwd, "show", ":" + stage + ":" + path, check=False).returncode == 0:
                git(cwd, "checkout", "--" + prefer, "--", path); git(cwd, "add", "--", path)
            else:
                git(cwd, "rm", "-f", "--", path)
        require(not p.returncode or remaining, "Git priority merge failed unexpectedly")
    require(not out(cwd, "ls-files", "-u"), "Unmerged index entries in " + label)
    tree = out(cwd, "write-tree")
    result = commit_tree(cwd, tree, left, "X3-first integration: " + label)
    git(cwd, "reset", "--hard", result)
    report[label] = decisions
    print(label, len(decisions), "conflicting paths,", sum(x["hunks"] for x in decisions), "resolved hunks", flush=True)
    return result


def adapt_engine(cwd, current, report):
    """Resolve cross-file ABI dependencies that a line merge cannot see."""
    notes = []
    def edit(path, fn):
        p = cwd/path
        old = p.read_text(encoding="utf-8")
        new = fn(old)
        if new != old:
            p.write_text(new, encoding="utf-8")
            notes.append(path)

    # HookLink's float duration at +0x38 and marker at +0x3c win. Official
    # loader's optional tick unit is relocated to a separate field and no
    # HookLink OOT stub advertises FRAME_STEP_120. Keep other upstream pacing
    # improvements; do not expose the official 40-fps OOT mode with this stub.
    edit("dm/gfx/nvn/nvn_fstep.h", lambda s: replace_once(s, "#define FSTEP_UNIT_OFF 0x38", "#define FSTEP_UNIT_OFF 0x48"))
    edit("dm/host/loader.c", lambda s: s.replace("page's unit (+0x38)", "page's unit (+0x48)"))
    edit("dm/tools/patch_nso.py", lambda s: s.replace("+0x40 u32 1 = the game's own dynamic resolution runs", "+0x48 u32 optional ticks per second (0 = 60); +0x40 u32 1 = the game's own dynamic resolution runs"))
    def patches(s):
        # The complete X3 frame_step function is the authoritative ABI,
        # including the measured duration, half rate and heap retry calls.
        h = source(cwd, NEW_HOOK, "dm/games/0400486024DEC000/patches.py")
        pattern = re.compile(r"(?ms)^def frame_step\(ctx\):\n.*?(?=^# The game's dynamic resolution)")
        old, new = pattern.search(s), pattern.search(h)
        require(old and new, "Cannot isolate X3 Ocarina frame-step implementation")
        s = s[:old.start()] + new.group(0) + s[old.end():]
        return s
    edit("dm/games/0400486024DEC000/patches.py", patches)
    def acquire(s):
        # The official acquire implementation now has deferred CPU waits.
        # Keep its whole internally consistent acquire region, and port the
        # X3 frame workgroup hook into the new acquire callsite.
        o = source(cwd, NEW_ORIGINAL, "dm/gfx/nvn/hle_nvn.c")
        start = "struct acq_wait {"
        # Find the exact full acquisition block through the next function
        # that is common to both implementations, using its source anchor.
        # The first overlapping hunk begins with the deferred-acquire struct
        # and X3 workgroup ends immediately before its own AcquireTexture.
        a = o.find(start)
        if a < 0:
            a = o.find("typedef struct acq_wait")
        require(a >= 0, "Official deferred acquisition anchor missing")
        # Determine the following NVN method from official source, then replace
        # the merged acquire region if the hunk choice left incompatible code.
        n = o.find("NVN(nvnWindowAcquireTexture,", a)
        next_n = re.search(r"(?m)^NVN\(", o[n+4:])
        require(n >= 0 and next_n, "Cannot isolate official acquire section")
        end = n+4+next_n.start()
        following = o[end:o.index("\n", end)]
        # Hook workgroup declarations are outside the acquire region.
        sn = s.find("NVN(nvnWindowAcquireTexture,")
        se = s.find(following, sn)
        require(sn >= 0 and se > sn, "Cannot locate merged acquire endpoint")
        section = o[a:end]
        section = replace_once(section, "rt_acquire(rt_period_ns(o, period));", "uint64_t rtp = rt_period_ns(o, period); rt_acquire(rtp); fwg_frame(rtp);")
        # Official helpers may have survived the textual merge already.
        sa = s.find(start)
        if sa < 0:
            sa = s.find("typedef struct acq_wait")
        if sa < 0 or sa > sn:
            sa = sn
        # The official helper functions precede the acquire method. If any
        # remain before the selected region, flag rather than duplicate them.
        require("static int acq_pace_do(" not in s[:sa], "Duplicate acquire helper before replacement")
        s = s[:sa] + section + s[se:]
        return s
    edit("dm/gfx/nvn/hle_nvn.c", acquire)
    # Keep the X3 frame delta accounting AND the independent official pause
    # detection and tick-unit state from surrounding nonconflicting code.
    def fstep(s):
        old = "    g_fs.nopay = !fstep_payback();\n    g_fs.per_vsync = fstep_hz() / 60;"
        new = "    g_fs.nopay = !fstep_payback();\n    g_fs.settle = settled;\n    g_fs.per_vsync = fstep_hz() / 60; g_fs.t120 = t120;"
        if old in s:
            s = replace_once(s, old, new)
        return s
    edit("dm/gfx/nvn/hle_nvn.c", fstep)
    # Carry the Windows tool lock verbatim; the local GUI preflight rebuilds
    # and fingerprints the actual translator and Metal compiler. Exclude
    # foreign precompiled tools as in earlier releases.
    (cwd/LOCK).write_bytes(blob(cwd, current, LOCK))
    for path in EXCLUDE:
        (cwd/path).unlink(missing_ok=True)
    def compiler(s):
        if "from concurrent.futures.process import BrokenProcessPool" not in s:
            line = next(x for x in s.splitlines() if x.startswith("import atexit,"))
            s = replace_once(s, line, line + "\nfrom concurrent.futures.process import BrokenProcessPool")
        s = s.replace("except cf.process.BrokenProcessPool:", "except BrokenProcessPool:")
        require("hasattr(os, 'pread')" in s, "Windows shader reader fallback lost")
        return s
    edit("dm/gfx/tools/dmsh_build.py", compiler)
    report["abi_adaptations"] = notes
    print("Cross-file ABI and Windows adaptations:", notes, flush=True)


def materialize(args):
    report = {"policy": POLICY, "official": NEW_ORIGINAL, "hooklink": NEW_HOOK, "desktop": NEW_APP, "published": False}
    try:
        with tempfile.TemporaryDirectory(prefix="hlw-v130-") as td:
            cwd = Path(td)/"engine"
            subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                            "--branch", "hooklink", HOOK_URL, str(cwd)], check=True)
            git(cwd, "config", "user.name", "HookLinkWindows integration")
            git(cwd, "config", "user.email", "integration@users.noreply.github.com")
            git(cwd, "remote", "add", "official", OFFICIAL_URL)
            git(cwd, "fetch", "--quiet", "--filter=blob:none", "official", OLD_ORIGINAL, NEW_ORIGINAL)
            git(cwd, "fetch", "--quiet", "--filter=blob:none", "origin", OLD_HOOK, NEW_HOOK)
            git(cwd, "merge-base", "--is-ancestor", OLD_ORIGINAL, NEW_ORIGINAL)
            git(cwd, "merge-base", "--is-ancestor", OLD_HOOK, NEW_HOOK)
            old = merge(cwd, OLD_ORIGINAL, OLD_HOOK, "historical_reference", "theirs", report)
            upstream = merge(cwd, NEW_ORIGINAL, NEW_HOOK, "upstream", "theirs", report)
            base = out(ROOT, "rev-parse", "HEAD")
            git(cwd, "fetch", "--quiet", "--no-tags", str(ROOT), base)
            w = commit_tree(cwd, out(cwd, "rev-parse", base + ":engine"), old, "Existing Windows source delta")
            target = commit_tree(cwd, out(cwd, "rev-parse", upstream + "^{tree}"), old, "Updated original + X3 source")
            final = merge(cwd, target, w, "windows", "ours", report)
            adapt_engine(cwd, w, report)
            git(cwd, "add", "-A")
            require(not out(cwd, "ls-files", "-u"), "Unresolved index")
            # Use Git archive, preserving the upstream file modes and every
            # nonconflicting file. Never use a whole outdated overlay tree.
            final = commit_tree(cwd, out(cwd, "write-tree"), final, "X3 ABI and Windows toolchain adaptations")
            git(cwd, "reset", "--hard", final)
            changed = out(cwd, "diff", "--name-only", w, final).splitlines()
            report["engine_changed_paths"] = len(changed)
            official = inventory(cwd, NEW_ORIGINAL)
            hook = inventory(cwd, NEW_HOOK)
            integrated = inventory(cwd, final)
            for path in changed:
                if path not in integrated:
                    continue
                data = blob(cwd, final, path)
                if data and b"\0" not in data and MARKERS.search(data):
                    raise RuntimeError("Unresolved conflict marker in " + path)
            report["unmerged_index_entries"] = 0
            report["conflict_marker_paths"] = []
            report["explicit_exclusions"] = sorted(EXCLUDE)
            report["missing_official_paths"] = sorted(set(official)-set(integrated)-EXCLUDE)
            # Deletions must be recorded, not hidden behind a stale pin.
            report["missing_hooklink_paths"] = sorted(set(hook)-set(integrated)-EXCLUDE)
            require(not report["missing_hooklink_paths"], "HookLink files missing after priority merge: " + str(report["missing_hooklink_paths"]))
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output/"engine.patch").write_bytes(git(cwd, "diff", "--binary", w, final).stdout)
            git(cwd, "remote", "add", "hookapp", APP_URL)
            git(cwd, "fetch", "--quiet", "--no-tags", "hookapp", OLD_APP, NEW_APP)
            # The root README/changelog belong to the Windows product.
            # Every other desktop delta is applied from the exact X3 commit.
            for path in out(cwd, "diff", "--name-only", OLD_APP, NEW_APP).splitlines():
                if path == "CHANGELOG.md":
                    (args.output/"hooklink-x3-upstream-changelog.md").write_bytes(blob(cwd, NEW_APP, path))
                    continue
                old_data, new_data = blob(cwd, OLD_APP, path), blob(cwd, NEW_APP, path)
                dest = ROOT/path
                require(not dest.exists() or dest.read_bytes() in (old_data, new_data), "Root desktop overlap: " + path)
                if new_data is None:
                    dest.unlink(missing_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(new_data)
            # Apply engine diff only to this ephemeral checkout. No branch
            # changes until all validation is complete.
            git(ROOT, "apply", "--binary", "--index", "--directory=engine", str(args.output/"engine.patch"))
            report["source_materialized"] = True
            report["base_main"] = base
            # Supply the full two-parent inventories to the provenance
            # updater; every intentional byte difference is inspectable.
            (args.output/"official-tree.json").write_text(json.dumps(official), encoding="utf-8")
            (args.output/"hooklink-tree.json").write_text(json.dumps(hook), encoding="utf-8")
            print("Materialized", len(changed), "engine paths; zero unresolved Git conflicts", flush=True)
    finally:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/"summary.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    materialize(parser.parse_args())
