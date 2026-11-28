#!/usr/bin/env python3
"""Materialize an official-first candidate in a temporary checkout.

First reconciliation pass: replace the entire competing timing ABI and
preserve the independent model-heap retry. This is not release approval.
No branches, engine pins, or published releases are modified.
"""
from pathlib import Path
import argparse
import json
import subprocess
import tempfile

from audit_v128_integration import ROOT, git, out, commit_tree, audit_merge
from audit_v134_incremental import BASE, TARGET
import reconcile_v134_shaders as shaders
import reconcile_v134_pso as pso
import reconcile_v134_mesh as mesh
import reconcile_v134_renderer as renderer
import reconcile_v134_settings as settings

OOT = "dm/games/0400486024DEC000/patches.py"
FSTEP = "dm/gfx/nvn/nvn_fstep.h"
NVN = "dm/gfx/nvn/hle_nvn.c"
LOADER = "dm/host/loader.c"
PATCHER = "dm/tools/patch_nso.py"
FRAME_TEST = "dm/gfx/tests/t_fstep.c"


def section(s, start, end):
    if s.count(start) != 1 or s.count(end) != 1:
        raise RuntimeError("Nonunique source anchors: " + start + " / " + end)
    a, b = s.index(start), s.index(end)
    if a >= b:
        raise RuntimeError("Reversed source anchors: " + start)
    return s[a:b]


def replace_once(s, old, new):
    if s.count(old) != 1:
        raise RuntimeError("Nonunique replacement: " + old[:120])
    return s.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    dest = ap.parse_args().output.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    pin = json.loads((ROOT/"ENGINE_PIN.json").read_text())
    if pin["nxnative_commit"] != BASE or pin["release"] != "Alpha V1.3.3":
        raise RuntimeError("Working baseline changed")
    report = ["# First official-first source reconciliation", "",
              "Unreleased candidate. Remaining semantic review required."]
    summary = {}
    try:
        with tempfile.TemporaryDirectory(prefix="hlw-v134-candidate-") as d:
            cwd = Path(d)
            git(cwd, "init", "--quiet")
            git(cwd, "config", "user.name", "HookLinkWindows candidate")
            git(cwd, "config", "user.email", "integration@users.noreply.github.com")
            git(cwd, "fetch", "--quiet", "--no-tags", "https://github.com/seedds/nxnative.git", BASE, TARGET)
            git(cwd, "merge-base", "--is-ancestor", BASE, TARGET)
            local = out(ROOT, "rev-parse", "HEAD")
            git(cwd, "fetch", "--quiet", "--no-tags", str(ROOT), local)
            windows = commit_tree(cwd, out(cwd, "rev-parse", local + ":engine"), BASE, "Tested Windows baseline")
            preview = audit_merge(cwd, TARGET, windows, "official-first", report, summary, prefer="ours")
            for p in ("dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate", "dm/gfx/tools/spirv_cross_bin/spirv-cross"):
                git(cwd, "rm", "-f", "--ignore-unmatch", "--", p)
            def read(rev, p):
                return git(cwd, "show", rev + ":" + p).stdout.decode("utf-8")
            def get(p):
                return (cwd/p).read_text(encoding="utf-8")
            def put(p, s):
                (cwd/p).write_text(s, encoding="utf-8")
            # Restore the official timing state and its tests as a pair.
            for p in (FSTEP, FRAME_TEST):
                put(p, read(TARGET, p))
            # Replace frame stepping, resolution selection, scaling, shape and
            # movie timing with official implementations. Heap retry is a
            # distinct model allocation fix, not a competing timing feature.
            original = read(TARGET, OOT)
            unique = section(read(windows, OOT), "# A full model heap", "# The framework's half rate")
            original = replace_once(original, "MATCH_FRAME_STEP = {'main': [", unique + "\nMATCH_FRAME_STEP = {'main': [")
            original = replace_once(original, "    screen_shape(ctx)\n", "    screen_shape(ctx)\n    heap_retry(ctx)\n")
            put(OOT, original)
            # Replace the complete controller region; leave other NVN methods
            # and independent QoS hooks alone for the broader graphics review.
            start, end = "// Whether late frames may raise the hold", "// The crop a present shows:"
            nvn = get(NVN)
            nvn = replace_once(nvn, section(nvn, start, end), section(read(TARGET, NVN), start, end))
            if "static nvn_fdelta fd;" in nvn:
                # fps_step_cap() occurs in several unrelated functions. Scope
                # both anchors to the unique present function and use the
                # exact old measured-duration block from the tested baseline.
                present = "NVN(nvnQueuePresentTexture, void, NVNqueue *q, NVNwindow *w, int idx) {"
                begin = "    if (dm_fps_state && __atomic_load_n((uint32_t *)(dm_fps_state + 0x3c)"
                end = "    int c = fps_step_cap();"
                prior = read(windows, NVN)
                if prior.count(present) != 1 or nvn.count(present) != 1:
                    raise RuntimeError("Nonunique present function")
                prior = prior[prior.index(present):]
                a = prior.index(begin)
                b = prior.index(end, a)
                old = prior[a:b]
                if "static nvn_fdelta fd;" not in old:
                    raise RuntimeError("Unexpected measured-duration block")
                # Only remove a byte-for-byte matching block in the candidate.
                nvn = replace_once(nvn, old, "")
            put(NVN, nvn)
            loader = get(LOADER).replace("page's unit (+0x48)", "page's unit (+0x38)")
            put(LOADER, loader)
            # Keep the real Windows mod insertion from V1.3.3 after official
            # matching, while restoring the official frame-state documentation.
            patch = get(PATCHER)
            start, end = "# ---- Frame step in whole vsyncs", "FRAME_STEP = PATCHES['FRAME_STEP']"
            patch = replace_once(patch, section(patch, start, end), section(read(TARGET, PATCHER), start, end))
            mod = section(read(windows, PATCHER), "# Windows user mods join the resolved cuts", "ALIAS_APPLIED =")
            if "NXW_MOD_CUTS" not in patch:
                patch = replace_once(patch, "ALIAS_APPLIED =", mod + "ALIAS_APPLIED =")
            if mod not in patch:
                raise RuntimeError("Windows mod-cut block differs; review before proceeding")
            put(PATCHER, patch)
            # Check concrete ABI contracts and that the heap retry toggle is
            # still wired, without treating these tests as complete validation.
            assert "#define FSTEP_UNIT_OFF 0x38" in get(FSTEP)
            assert "def frame_step_v0(ctx)" in get(OOT)
            assert "heap_retry(ctx)" in get(OOT) and "DM_HEAP_RETRY" in get(LOADER)
            assert "nvn_fstep_moved(" not in get(NVN)
            assert "static nvn_fdelta fd;" not in get(NVN)
            assert "dm_fps_state + 0x38" not in get(NVN)
            assert get(PATCHER).index("if BUILD_ID not in PATCHES['CUTS']:") < get(PATCHER).index("if os.environ.get('NXW_MOD_CUTS'):")
            summary["provisional_shader_chain"] = shaders.reconcile(cwd, TARGET, windows, read)
            summary["pso_reconciliation"] = pso.reconcile(cwd, dest, BASE, TARGET, windows, read)
            import shutil
            shutil.copyfile(ROOT/"tools/nxw_proc_group.py", cwd/"dm/tools/proc_group_windows.py")
            proc = "dm/tools/proc_group.py"
            put(proc, read(TARGET, proc) + "\n\nif os.name == 'nt':\n    from proc_group_windows import Group, stop_all\n")
            subprocess.run(["python3", "-m", "py_compile", proc, "dm/tools/proc_group_windows.py"], cwd=cwd, check=True)
            summary["windows_process_backend"] = "Job Object; tested separately on native Windows"
            summary["mesh_reconciliation"] = mesh.reconcile(cwd, TARGET, windows, read)
            summary["renderer_reconciliation"] = renderer.reconcile(cwd, TARGET, dest)
            summary["profile_reconciliation"] = settings.reconcile(cwd, TARGET, windows, read)
            git(cwd, "add", "-A")
            pso.inventory(cwd, dest, TARGET)
            assert not out(cwd, "ls-files", "-u")
            summary["candidate_tree"] = out(cwd, "write-tree")
            summary["timing_paths_reconciled"] = [OOT, FSTEP, FRAME_TEST, NVN, LOADER, PATCHER]
            summary["shader_paths_reconciled"] = list(shaders.PATHS)
            summary["semantic_review_complete"] = False
            summary["remaining"] = [
                "Wide-view ultrawide-only hooks need disjoint site and capability review against official screen shape.",
                "Review remaining HookLink custom graphics, MetalFX, launcher and audio behavior.",
                "Reconcile Windows shader tooling, generated profile paths, PSO manifest, stale settings and historical tests.",
                "Recompute shader chain and provenance; run complete Windows/native/iOS validation.",
            ]
            (dest/"candidate-paths.txt").write_text(out(cwd, "diff", "--cached", "--name-status", windows) + "\n")
            (dest/"remaining-custom-paths.txt").write_text(out(cwd, "diff", "--cached", "--name-status", TARGET) + "\n")
            with (dest/"timing-reconciliation.patch").open("wb") as stream:
                subprocess.run(["git", "diff", "--cached", preview, "--", OOT, FSTEP, FRAME_TEST, NVN, LOADER, PATCHER],
                               cwd=cwd, stdout=stream, check=True)
            subprocess.run(["python3", "-m", "py_compile", OOT, PATCHER], cwd=cwd, check=True)
            exe = dest/"t_fstep"
            subprocess.run(["cc", "-std=c11", "-O2", FRAME_TEST, "-lm", "-o", str(exe)], cwd=cwd, check=True)
            test = subprocess.run([str(exe)], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (dest/"frame-step-tests.txt").write_text(test.stdout)
            print(test.stdout, flush=True)
            test.check_returncode()
            exe.unlink()
            summary["frame_step_controller_tests"] = "passed"
            with (dest/"shader-reconciliation.patch").open("wb") as stream:
                subprocess.run(["git", "diff", "--cached", preview, "--", *shaders.PATHS], cwd=cwd, stdout=stream, check=True)
            subprocess.run(["python3", "-m", "py_compile", *[p for p in shaders.PATHS if p.endswith(".py")]], cwd=cwd, check=True)
            shaders.check(cwd, dest)
            summary["shader_pipeline_tests"] = "passed"
            subprocess.run(["python3", "-m", "unittest", "-v", "dm.tools.tests.test_merge_prewarm_seeds"], cwd=cwd, check=True)
            summary["prewarm_import_tests"] = "passed"
            settings.check(cwd, dest)
            summary["profile_settings_tests"] = "passed"
            # Export the exact staged source tree, never the old engine on main.
            subprocess.run(["git", "archive", "--format=tar.gz", "--output=" + str(dest/"candidate-engine.tar.gz"), summary["candidate_tree"]], cwd=cwd, check=True)
            summary["native_compile_archive"] = "candidate-engine.tar.gz"
            report.extend(["", "## Remaining semantic review", "", *summary["remaining"]])
    finally:
        (dest/"report.md").write_text("\n".join(report) + "\n")
        (dest/"summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
