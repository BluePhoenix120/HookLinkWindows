#!/usr/bin/env python3
"""Review/apply ALL NXnative commits since the current full original snapshot.

Three-way source reconciliation:
  BASE = old original NXnative
  OURS = new original NXnative
  THEIRS = HookLinkWindows (HookLink plus Windows-specific edits)
Only keep a Windows difference when new upstream does not supersede it;
overlapping edits MUST be reviewed and explicitly resolved, never silently
preserve a whole old Windows file.

Does not publish or release anything. A dry run only reports conflicts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PIN=ROOT/"ENGINE_PIN.json"
MANIFEST=ROOT/"ENGINE_PIN_FILES.json"
REPO="https://github.com/seedds/nxnative.git"
FROM="d2fd78b402f92d5a83b78987e49aba22e8626719"
TO="3ec5b785f37f8c87d78433f152914d89c4ef93c9"
EXCLUDE={"dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate","dm/gfx/tools/spirv_cross_bin/spirv-cross"}
# Toolchain fingerprints refer to the Windows-specific Metal compiler.
# The GUI independently verifies/rebuilds them through shader_chain_prepare.py.
WINDOWS_CHAIN={"dm/gfx/nvn/dmsh_chain.h","dm/gfx/tools/dmsh_chain.lock"}


def run(*args,cwd=ROOT,check=True):
    p=subprocess.run(args,cwd=cwd,capture_output=True)
    if p.returncode and check:
        raise RuntimeError(f"{args[:6]}: {p.stderr.decode(errors='replace')[-2000:]}")
    return p


def git(*args,cwd,check=True):return run("git",*args,cwd=cwd,check=check)


def show(repo,rev,path):
    p=git("show",rev+":"+path,cwd=repo,check=False)
    return None if p.returncode else p.stdout


def sha(data):return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


def tree(repo,rev):
    out={}
    for row in git("ls-tree","-r","-z",rev,cwd=repo).stdout.split(b"\0"):
        if not row:continue
        hdr,path=row.split(b"\t",1)
        mode,typ,digest=hdr.decode().split()
        if typ=="blob":out[path.decode("utf-8","surrogateescape")]=digest
    return out


def three_way(up,old,windows,dir):
    if b"\0" in up or b"\0" in old or b"\0" in windows:
        return None,"binary"
    files=[dir/(f"merge-{i}") for i in range(3)]
    for file,src in zip(files,[up,old,windows]):file.write_bytes(src)
    p=run("git","merge-file","--diff3","-p",*map(str,files),check=False)
    if p.returncode:return None,p.stdout.decode("utf-8","replace")
    return p.stdout,None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--report",type=Path,default=ROOT/"upstream-recent-review.md")
    opts=parser.parse_args()
    pin=json.loads(PIN.read_text(encoding="utf-8"))
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    if pin["nxnative_commit"]!=FROM or manifest["nxnative_commit"]!=FROM:
        raise RuntimeError("Original baseline changed; require an updated reviewed comparison")
    if git("status","--porcelain",cwd=ROOT).stdout.strip():
        raise RuntimeError("Require a clean candidate branch; refusing to edit worktree")
    with tempfile.TemporaryDirectory(prefix="latest-nxnative-") as d:
        tmp=Path(d)
        repo=tmp/"original"
        run("git","clone","--quiet","--filter=blob:none","--no-checkout",REPO,str(repo))
        git("fetch","--quiet","--filter=blob:none","origin",FROM,TO,cwd=repo)
        old_tree,new_tree=tree(repo,FROM),tree(repo,TO)
        changed=[p for p in sorted(set(old_tree)|set(new_tree)) if old_tree.get(p)!=new_tree.get(p)]
        changes={}
        conflicts={}
        stats={"new_original":0,"unchanged":0,"three_way_clean":0,"windows_chain":0,"skipped_binary":0}
        for path in changed:
            if path in EXCLUDE:
                stats["skipped_binary"]+=1
                continue
            w=ROOT/"engine"/path
            W=w.read_bytes() if w.is_file() else None
            old=show(repo,FROM,path) if path in old_tree else None
            new=show(repo,TO,path) if path in new_tree else None
            if path in WINDOWS_CHAIN:
                if W is None:raise RuntimeError("Missing Windows compiler chain metadata "+path)
                stats["windows_chain"]+=1
                continue
            if new is None:
                if W is not None and old is not None and W!=old:
                    conflicts[path]="upstream deletes locally changed file"
                else: changes[path]=None
            elif W is None or W==old:
                changes[path]=new
                stats["new_original"]+=1
            elif W==new:
                changes[path]=W
                stats["unchanged"]+=1
            elif old is None:
                conflicts[path]="upstream adds path already customized by Windows"
            else:
                result,err=three_way(new,old,W,tmp)
                if err is not None:
                    conflicts[path]=err[:14000]
                else:
                    changes[path]=result
                    stats["three_way_clean"]+=1
        lines=[
            "# Full NXnative incremental upstream merge review", "",
            "- From original: \`"+FROM+"\`",
            "- To latest original: \`"+TO+"\`",
            "- Files modified upstream: "+str(len(changed)),
            "- Conflicts (need manual hunk review): "+str(len(conflicts)),
            "- Windows-specific chain/lock retained for automatic local preflight: "+str(stats["windows_chain"]),
            "- Non-Windows prebuilt binaries excluded: "+str(stats["skipped_binary"]),
            "- Clean 3-way source merges: "+str(stats["three_way_clean"]),
            "", "## Conflicts", ""
        ]
        for path,c in conflicts.items():
            lines+=["### \`"+path+"\`","", "\`\`\`diff",c,"\`\`\`",""]
        if not conflicts:lines+=["None.",""]
        lines+=["## Modified upstream paths", ""]
        for p in changed:lines.append("- \`"+p+"\`")
        opts.report.parent.mkdir(parents=True,exist_ok=True)
        opts.report.write_text("\n".join(lines)+"\n",encoding="utf-8")
        print(json.dumps({"from":FROM,"to":TO,"changed":len(changed),"conflicts":list(conflicts),
            "statistics":stats,"report":str(opts.report)},indent=2),flush=True)
        if not opts.apply:
            print("DRY RUN ONLY. Nothing in engine/ or PIN was changed.",flush=True)
            return
        if conflicts:raise RuntimeError("Unresolved upstream conflicts; no source was written: "+", ".join(conflicts))
        for p,content in changes.items():
            dest=ROOT/"engine"/p
            if content is None:
                dest.unlink(missing_ok=True)
            else:
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(content)
        pin["nxnative_commit"]=TO
        pin["release"]="Alpha V1.2.4"
        pin["engine_integration_policy"]="complete original NXnative up to "+TO[:12]+"; retain actual HookLink and Windows changes by three-way merge; local Windows chain revalidated before IPA"
        pin["incremental_upstream_from"]=FROM
        pin["incremental_upstream_to"]=TO
        PIN.write_text(json.dumps(pin,indent=4)+"\n",encoding="utf-8")
        manifest["nxnative_commit"]=TO
        manifest["engine_integration_policy"]=pin["engine_integration_policy"]
        manifest["changed_paths"]=[{"path":"engine/"+p,"sha":digest}
            for p,digest in sorted(new_tree.items()) if p not in EXCLUDE]
        manifest["platform_binary_exclusions"]=[
            {"path":"engine/"+p,"reason":"Non-Windows prebuilt binary; Windows rebuilds from original source"}
            for p in sorted(EXCLUDE)]
        old_overrides=manifest["integration_overrides"]
        merged_overrides={}
        for p,new_sha in new_tree.items():
            if p in EXCLUDE:continue
            dest=ROOT/"engine"/p
            if not dest.is_file():raise RuntimeError("Missing required latest NXnative source "+p)
            digest=sha(dest.read_bytes())
            if digest!=new_sha:
                key="engine/"+p
                merged_overrides[key]={
                    "upstream_sha":new_sha,"integrated_sha":digest,
                    "reason":old_overrides.get(key,{}).get("reason") or (
                        "Windows compiler chain metadata; local preflight rebuilds/synchronizes" if p in WINDOWS_CHAIN
                        else "Actual preserved HookLink/Windows edits verified by incremental Git three-way merge")}
        manifest["windows_overlays"]=sorted(set(merged_overrides) |
            {"engine/"+p for p in changed if p not in new_tree and (ROOT/"engine"/p).is_file()} |
            {p for p in manifest["windows_overlays"] if p[7:] not in new_tree and p[7:] not in EXCLUDE})
        manifest["integration_overrides"]=merged_overrides
        manifest["incremental_upstream_from"]=FROM
        manifest["incremental_upstream_to"]=TO
        manifest["incremental_merge_conflicts"]=[]
        MANIFEST.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        for p in ["tests/test_upstream_first_contracts.py","tests/test_engine_sync_manifest.py"]:
            f=ROOT/p
            c=f.read_text(encoding="utf-8")
            if FROM not in c:raise RuntimeError("Expected old snapshot contract missing from "+p)
            f.write_text(c.replace(FROM,TO),encoding="utf-8")
        d=ROOT/"docs"/"NXNATIVE_RECENT_UPSTREAM_V124.md"
        d.write_text("# Complete latest original NXnative update for Alpha V1.2.4\n\n"
            "Original source update: \`"+FROM+"\` to \`"+TO+"\` (all "+str(len(changed))+" affected paths).\n\n"
            "All nonconflicting original code was integrated, and real HookLink/Windows changes "
            "were preserved by three-way merge. No upstream paths skipped except two prebuilt "
            "non-Windows translator binaries. Windows-specific Metal compiler lock/header stay "
            "configured for Windows; the GUI preflight verifies and regenerates them against "
            "the rebuilt translator before generating any IPA. This changes shader chain IDs "
            "and requires rebuild of incompatible shader libraries; cached game assets are not deleted.\n\n"
            "This update contains original audio output route recovery, shader gather "
            "offsets, packing metadata checks and GL fixed-function adjustments. "
            "Full iOS IPA and device runtime verification remain outstanding.\n",encoding="utf-8")
        print("INTEGRATED_ALL_RECENT_NXNATIVE",len(changed),"paths; manifest",len(new_tree)-len(EXCLUDE),"original sources; differences",len(merged_overrides),flush=True)


if __name__=="__main__":main()
