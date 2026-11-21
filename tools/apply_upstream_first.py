#!/usr/bin/env python3
"""Integrate full original NXnative first; preserve actual HookLink and Windows deltas.

Runs ONLY in an isolated CI PR checkout, not in a published release.
Never substitutes an entire old Windows file merely because it differs.
Conflicting Windows hunks are explicitly resolved below for the pinned source
revisions; any NEW/unrecognized conflict is fatal.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = "https://github.com/seedds/nxnative.git"
HOOKLINK = "https://github.com/dsi-hub/nxnative.git"
BINARIES = {"dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate",
            "dm/gfx/tools/spirv_cross_bin/spirv-cross"}
EXPECTED_ORIGINAL = "d2fd78b402f92d5a83b78987e49aba22e8626719"
EXPECTED_HOOKLINK = "698b46bc5b14510fffc0a4b8fd4bf78309004e4c"
EXPECTED_CONFLICTS = {
    "dm/gfx/nvn/dmsh_chain.h", "dm/gfx/nvn/nvn_mtl.m",
    "dm/gfx/tools/dmsh_build.py", "dm/gfx/tools/dmsh_chain.lock",
    "dm/gfx/tools/dmsh_rewrite.py", "docs/reference/frame-rate.md"
}


def run(*args, cwd=ROOT, check=True):
    p = subprocess.run(args, cwd=cwd, capture_output=True)
    if p.returncode and check:
        raise RuntimeError(f"{args[:6]} ({p.returncode}): {p.stderr.decode(errors='replace')[-3500:]}")
    return p


def git(*args, cwd, check=True):
    return run("git", *args, cwd=cwd, check=check)


def show(work, rev, path):
    p = git("show", rev + ":" + path, cwd=work, check=False)
    return p.stdout if not p.returncode else None


def sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def tree(work, rev):
    out = {}
    for record in git("ls-tree", "-r", "-z", rev, cwd=work).stdout.split(b"\0"):
        if not record:
            continue
        hdr, name = record.split(b"\t", 1)
        mode, typ, value = hdr.decode().split()
        if typ == "blob":
            out[name.decode("utf-8", "surrogateescape")] = value
    return out


def resolve(path, ours, base, windows):
    if b"\0" in ours or b"\0" in base or b"\0" in windows:
        raise RuntimeError(f"Binary triple-sided conflict needs manual review: {path}")
    with tempfile.TemporaryDirectory(prefix="hunk-") as td:
        files = [Path(td)/str(i) for i in range(3)]
        for file, data in zip(files, (ours, base, windows)):
            file.write_bytes(data)
        p = run("git", "merge-file", "--diff3", "-p", *map(str, files), check=False)
    if p.returncode == 0:
        return p.stdout, "clean Windows delta"
    if p.returncode != 1 or path not in EXPECTED_CONFLICTS:
        raise RuntimeError(f"Unexpected conflict in {path} ({p.returncode})")
    source = p.stdout.decode("utf-8")
    # Git diff3 chunks: upstream+HookLink (ours), older HookLink (base),
    # Windows (theirs). Exact pinned input must have expected hunk shapes.
    chunks = []
    pos = 0
    while True:
        start = source.find("<<<<<<< ", pos)
        if start < 0:
            chunks.append(("plain", source[pos:]))
            break
        chunks.append(("plain", source[pos:start]))
        pivot = source.find("||||||| ", start)
        middle = source.find("=======\n", pivot)
        end = source.find(">>>>>>> ", middle)
        newline = source.find("\n", end)
        if min(pivot, middle, end, newline) < 0:
            raise RuntimeError(f"Broken conflict markers in {path}")
        ours_block = source[source.find("\n",start)+1:pivot]
        base_block = source[source.find("\n",pivot)+1:middle]
        theirs_block = source[middle+8:end]
        chunks.append(("conflict", (ours_block, base_block, theirs_block)))
        pos = newline+1
    hunks = [value for kind, value in chunks if kind=="conflict"]
    def require(condition, message):
        if not condition:
            raise RuntimeError(f"Unexpected {path} conflict: {message}")
    substitutions=[]
    if path == "dm/gfx/nvn/dmsh_chain.h":
        require(len(hunks)==1 and 'DMSH_CHAIN "a58d7f1f4ef9"' in hunks[0][2], "chain header version")
        substitutions=[hunks[0][2]] # Windows Metal toolchain version, to be revalidated by Windows preflight
    elif path == "dm/gfx/tools/dmsh_chain.lock":
        require(len(hunks)==1 and "metalfe-custom-windows" in hunks[0][2], "Windows compiler lock")
        substitutions=[hunks[0][2]] # Explicit Windows compiler fingerprint; tool lock preflight must recheck
    elif path == "dm/gfx/nvn/nvn_mtl.m":
        require(len(hunks)==1 and hunks[0][0] == hunks[0][2] and "g_stand_sparse_unmapped" in hunks[0][0], "sparse texture mapping")
        substitutions=[hunks[0][0]]
    elif path == "dm/gfx/tools/dmsh_rewrite.py":
        require(len(hunks)==1 and "def membar_fence(msl):" in hunks[0][2], "Windows MEMBAR fence")
        substitutions=[hunks[0][2]] # Windows compatibility; upstream removed it, build calls it
    elif path == "docs/reference/frame-rate.md":
        require(len(hunks)==1 and "TUNIC" in hunks[0][0], "upstream frame-rate docs")
        substitutions=[hunks[0][0]]
    elif path == "dm/gfx/tools/dmsh_build.py":
        require(len(hunks)==3,"expected 3 source hunks")
        a,b,c = hunks
        require("dmsh_rt_build" in a[0] and "BrokenProcessPool" in a[2],"RT imports and Windows pool handling")
        require("dmsh_chain.CROSS_MSL" in b[0] and "dmsh_chain.CROSS_MSL" in b[2],"MSL options")
        require("try: RT_PLAN" in c[0] and "hasattr(os, 'pread')" in c[2],"RT plan plus Windows pread")
        substitutions=[
            "from concurrent.futures.process import BrokenProcessPool\n" + a[0],
            b[0],
            c[2].rstrip("\n")+"\n"+c[0][c[0].index("try: RT_PLAN"):]
        ]
    else:
        raise RuntimeError("No source-level resolution for "+path)
    answer = []
    selected = iter(substitutions)
    for kind, value in chunks:
        answer.append(value if kind=="plain" else next(selected))
    print("RESOLVED",path,"explicit hunks",len(hunks),flush=True)
    return "".join(answer).encode("utf-8"), "explicit reviewed hunk resolution"


def main():
    pin_file=ROOT/"ENGINE_PIN.json"
    manifest_file=ROOT/"ENGINE_PIN_FILES.json"
    pin=json.loads(pin_file.read_text(encoding="utf-8"))
    oldmanifest=json.loads(manifest_file.read_text(encoding="utf-8"))
    official=pin["nxnative_commit"]
    hook=pin["hooklink_engine_commit"]
    if official != EXPECTED_ORIGINAL or hook != EXPECTED_HOOKLINK or pin["release"] != "Alpha V1.2.3":
        raise RuntimeError("Pinned source changed; review the full integration before reuse")
    if git("status", "--porcelain", cwd=ROOT).stdout.strip():
        raise RuntimeError("Checkout is not clean; cannot apply full engine update")
    with tempfile.TemporaryDirectory(prefix="full-original-first-") as td:
        work=Path(td)/"merged"
        run("git","clone","--quiet","--filter=blob:none","--branch","hooklink",HOOKLINK,str(work))
        if git("rev-parse","HEAD",cwd=work).stdout.decode().strip()!=hook:
            raise RuntimeError("HookLink fork moved since pin; do not silently skip its latest changes")
        git("config","user.name","HookLinkWindows engine integrator",cwd=work)
        git("config","user.email","source-merge@users.noreply.github.com",cwd=work)
        git("remote","add","official",ORIGINAL,cwd=work)
        git("fetch","--quiet","--filter=blob:none","official",official,cwd=work)
        git("switch","--detach",official,cwd=work)
        first=git("merge","--no-ff","--no-edit",hook,cwd=work,check=False)
        hook_conflicts=git("diff","--name-only","--diff-filter=U",cwd=work).stdout.decode().splitlines()
        if first.returncode or hook_conflicts:
            git("merge","--abort",cwd=work)
            # Preserve actual HookLink conflict hunks over latest original.
            keep=git("merge","--no-ff","--no-edit","-X","theirs",hook,cwd=work,check=False)
            rem=git("diff","--name-only","--diff-filter=U",cwd=work).stdout.decode().splitlines()
            if keep.returncode or rem:
                raise RuntimeError("Unresolved official/HookLink source conflicts: "+str(rem))
        reference=git("rev-parse","HEAD",cwd=work).stdout.decode().strip()
        original_tree=tree(work,official)
        reference_tree=tree(work,reference)
        hook_tree=tree(work,hook)
        before=ROOT/"engine"
        windows_paths={f.relative_to(before).as_posix():f for f in before.rglob("*") if f.is_file() and ".git" not in f.parts}
        observed_conflicts=set()
        decisions={}
        for path in sorted(set(reference_tree)|set(windows_paths)):
            if path in BINARIES:
                (work/path).unlink(missing_ok=True)
                continue
            local=windows_paths.get(path)
            W=local.read_bytes() if local is not None else None
            R=show(work,reference,path) if path in reference_tree else None
            H=show(work,hook,path) if path in hook_tree else None
            merged=None
            if R is None:
                if W is not None and H is None:
                    merged=W
                    decisions[path]="Windows-only new file"
                elif W is not None:
                    raise RuntimeError("Upstream/HookLink removed file but older Windows retained it: "+path)
            elif W is None or W==R or W==H:
                merged=R
            elif H is None or H==R:
                merged=W
                decisions[path]="Windows-only customization with no upstream conflict"
            else:
                merged,desc=resolve(path,R,H,W)
                decisions[path]=desc
                if desc.startswith("explicit"):observed_conflicts.add(path)
            if merged is None:
                continue
            if merged!=R:
                dest=work/path
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(merged)
        if observed_conflicts!=EXPECTED_CONFLICTS:
            raise RuntimeError(f"Unexpected reviewed-conflict set: {sorted(observed_conflicts)}; expected {sorted(EXPECTED_CONFLICTS)}")
        git("add","--all","--force",cwd=work)
        if git("diff","--cached","--quiet",cwd=work,check=False).returncode:
            git("commit","-m","Integrate Windows deltas into latest original NXnative+HookLink at hunk granularity",cwd=work)
        merged_commit=git("rev-parse","HEAD",cwd=work).stdout.decode().strip()
        merged_tree=tree(work,merged_commit)
        for critical,needle in [
            ("dm/gfx/tools/shader_split.py",b"def bahs_binary_records("),
            ("dm/gfx/tools/shader_split.py",b"def kit_jobs("),
            ("dm/gfx/tools/dmsh_build.py",b"def owned_output("),
            ("dm/gfx/tools/dmsh_build.py",b"def rt_finish("),
            ("scripts/build_ipa_from_nsp.py",b"def build_sources("),
            ("scripts/build_ipa_from_nsp.py",b"def drop_prewarm("),
            ("dm/gfx/tools/dmsh_rewrite.py",b"def membar_fence(msl):")
        ]:
            if critical not in merged_tree or needle not in show(work,merged_commit,critical):
                raise RuntimeError("Full original/Windows integration missing required definition: "+critical+" "+needle.decode())
        missing=set(original_tree)-set(merged_tree)
        if missing != BINARIES:
            raise RuntimeError("Latest original source missing from merged tree: "+str(sorted(missing)[:30]))
        # The candidate is complete, but must still pass Windows/iOS validation.
        run("rsync","-a","--delete","--exclude=.git/","--exclude=.git",str(work)+"/",str(before)+"/")
        # Exclude old metadata from installed Windows file until regenerated.
        if any((before/path).exists() for path in BINARIES):
            raise RuntimeError("Prebuilt non-Windows translators unexpectedly copied")
        upstream_rows=[{"path":"engine/"+path,"sha":value} for path,value in sorted(original_tree.items()) if path not in BINARIES]
        overlay_paths=sorted({"engine/"+path for path in set(merged_tree)|set(original_tree)
                             if merged_tree.get(path)!=original_tree.get(path)})
        overrides={}
        for entry in upstream_rows:
            path=entry["path"]
            rel=path[7:]
            value=merged_tree.get(rel)
            if value is None:
                raise RuntimeError("Missing original source path "+rel)
            if entry["sha"]!=value:
                overrides[path]={"upstream_sha":entry["sha"],"integrated_sha":value,
                                 "reason":decisions.get(rel,"Original NXnative + actual HookLink changed-hunk integration; see reviewed upstream-first conflict report")}
        manifest={
            "nxnative_repo":ORIGINAL,"from_commit":oldmanifest.get("from_commit"),
            "nxnative_commit":official,"hooklink_engine_commit":hook,
            "engine_integration_commit":merged_commit,
            "engine_integration_policy":"original-upstream-first; real HookLink conflict hunks preserved; only necessary Windows delta reapplied by three-way merge",
            "changed_paths":upstream_rows,
            "windows_overlays":overlay_paths,
            "integration_overrides":overrides,
            "deleted_paths":oldmanifest.get("deleted_paths",[]),
            "platform_binary_exclusions":[{"path":"engine/"+p,"reason":"Prebuilt non-Windows binary; Windows rebuilds tool from original source"} for p in sorted(BINARIES)],
            "original_hooklink_conflicts":["engine/"+p for p in hook_conflicts],
            "windows_reviewed_hunk_conflicts":["engine/"+p for p in sorted(observed_conflicts)],
            "notes":"Original-first complete upstream snapshot; preserve HookLink modified hunks, not older whole files. Windows patches applied only where necessary. iOS IPA and phone testing not yet complete."
        }
        manifest_file.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        pin["engine_integration_commit"]=merged_commit
        pin["engine_integration_policy"]=manifest["engine_integration_policy"]
        pin_file.write_text(json.dumps(pin,indent=4)+"\n",encoding="utf-8")
        report=(ROOT/"docs/UPSTREAM_FIRST_ENGINE_INTEGRATION.md")
        report.write_text("# Alpha V1.2.3 upstream-first engine integration\n\n"
            "Latest original NXnative commit: "+official+"\n\n"
            "HookLink custom engine commit: "+hook+"\n\n"
            "Synthetic Git source integration commit: "+merged_commit+"\n\n"
            "Source is original NXnative first, with HookLink conflict hunks retained; Windows differences are rebased by three-way merge against HookLink (not by old-file preference).\n\n"
            "Original/HookLink overlaps requiring reviewed HookLink resolution: "+str(len(hook_conflicts))+"\n\n"+
            "\n".join("- "+p for p in hook_conflicts)+"\n\n"
            "Windows custom overlaps resolved explicitly: "+str(len(observed_conflicts))+"\n\n"+
            "\n".join("- "+p+": "+decisions[p] for p in sorted(observed_conflicts))+"\n\n"
            "Original source files: "+str(len(original_tree))+"; integrated source files: "+str(len(merged_tree))+"; modified original files: "+str(len(overrides))+".\n\n"
            "The Windows Metal compiler lock and chain header are deliberately preserved and **must be reverified/rebuilt** by the Windows toolchain. This source integration has not been validated through a full IPA build or on-device test. Keep the known-working V1.2.1 app and shader caches intact.\n",encoding="utf-8")
        print("COMPLETE_UPSTREAM_FIRST",json.dumps({"original":official,"hooklink":hook,"merged_source":merged_commit,
            "original_files":len(original_tree),"merged_files":len(merged_tree),"overrides":len(overrides),
            "windows_extra":len(overlay_paths),"hooklink_strict_conflicts":len(hook_conflicts),
            "windows_reviewed_conflicts":sorted(observed_conflicts),"decisions":len(decisions)}),flush=True)


if __name__ == "__main__":
    main()
