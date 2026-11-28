"""Materialize the exact candidate, record all official and historical paths,
and prepare a detached commit for full Windows testing. Never publish it.
"""
import json
import re
import subprocess
import sys
from audit_v128_integration import git, out, commit_tree, ROOT

EXCLUDED = {"dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate", "dm/gfx/tools/spirv_cross_bin/spirv-cross"}
OFFICIAL_COUNT = 3084

def tree(cwd, rev):
    rows = git(cwd, "ls-tree", "-r", "-z", rev).stdout.split(b"\0")
    result = {}
    for row in rows:
        if not row: continue
        meta, path = row.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        if kind != "blob": raise RuntimeError("Unexpected non-blob tree entry")
        result[path.decode()] = (mode, sha)
    return result

def materialize(cwd, local, base, target, dest, summary):
    candidate = summary["candidate_tree"]
    official = tree(cwd,target)
    prior = tree(cwd,base)
    integrated = tree(cwd,candidate)
    assert len(official)==OFFICIAL_COUNT
    assert EXCLUDED <= official.keys() and not EXCLUDED & integrated.keys()
    missing = sorted(set(official)-set(integrated)-EXCLUDED)
    if missing: raise RuntimeError("Missing official source paths: "+repr(missing))
    def path(p): return "engine/"+p
    rows = [{"path":path(p),"sha":sha} for p,(_,sha) in sorted(official.items()) if p not in EXCLUDED]
    overrides = {path(p):{"upstream_sha":official[p][1],"integrated_sha":integrated[p][1],
                    "reason":"Recorded candidate difference; review against official-first policy before release"}
                 for p in sorted(set(official)&set(integrated)) if official[p]!=integrated[p]}
    local_only = {path(p):{"sha":integrated[p][1],"mode":integrated[p][0]}
                  for p in sorted(set(integrated)-set(official))}
    deleted = sorted(set(prior)-set(official))
    resurrected = sorted(set(deleted)&set(integrated))
    # Record every historical HookLink blob from the previous manifest,
    # including upstream deletions and superseded implementations.
    old = json.loads((ROOT/"ENGINE_PIN_FILES.json").read_text(encoding="utf-8"))
    historical = old["hooklink_tree"]
    hook_rows, hook_overrides, hook_omissions = [], {}, {}
    for row in historical:
        p = row["path"].removeprefix("engine/")
        if p not in integrated:
            hook_omissions[row["path"]] = {"hooklink_sha":row["sha"],
                  "reason":"Official upstream deletion" if p in deleted else "Absent from candidate; review"}
            continue
        hook_rows.append(row)
        if integrated[p][1]!=row["sha"]:
            hook_overrides[row["path"]]={"upstream_sha":row["sha"],"integrated_sha":integrated[p][1],
                 "reason":"Official-first candidate; exact historical comparison"}
    evidence={"official_paths":len(official),"official_included":len(rows),
              "official_overrides":len(overrides),"candidate_local_only":len(local_only),
              "upstream_deleted":len(deleted),"upstream_deleted_still_present":resurrected,
              "hooklink_historical_paths":len(historical),"hooklink_omissions":len(hook_omissions),
              "missing_official_paths":missing,"semantic_review_complete":False}
    (dest/"candidate-provenance.json").write_text(json.dumps(evidence,indent=2)+"\n")
    print("Candidate provenance: "+json.dumps(evidence),flush=True)
    # Construct a real root-level commit with the exact staged engine tree
    # as a subtree. No working branch or remote is changed.
    git(cwd,"read-tree",local)
    git(cwd,"rm","-r","--cached","-f","--quiet","engine")
    git(cwd,"read-tree","--prefix=engine/",candidate)
    root_tree=out(cwd,"write-tree")
    integration=commit_tree(cwd,root_tree,local,"Unpublished V1.3.4 official-first engine candidate")
    assert out(cwd,"rev-parse",integration+":engine")==candidate
    git(cwd,"reset","--hard",integration)
    policy="upstream-first: official NXnative priority for overlapping or equivalent functionality; retain distinct HookLink and Windows compatibility."
    pin=json.loads((cwd/"ENGINE_PIN.json").read_text())
    pin.update(nxnative_commit=target,incremental_upstream_from=base,incremental_upstream_to=target,
               engine_integration_commit=integration,engine_integration_policy=policy,
               shader_chain=summary["provisional_shader_chain"],release="Alpha V1.3.4")
    report={"policy":policy,"unmerged_index_entries":0,"missing_official_paths":missing,
            "semantic_review_complete":False,"conflicts":summary["official-first"]["conflicts"],
            "candidate_only":True,"source_tree":candidate}
    manifest=dict(old)
    for k in ("nxnative_commit","incremental_upstream_from","incremental_upstream_to","engine_integration_commit","engine_integration_policy"):
        manifest[k]=pin[k]
    manifest.update(changed_paths=rows,integration_overrides=overrides,
                    windows_overlays=sorted(overrides),candidate_local_only=local_only,
                    hooklink_tree=hook_rows,hooklink_integration_overrides=hook_overrides,
                    hooklink_omissions=hook_omissions,clean_official_deletions=deleted,
                    incremental_merge_conflicts=summary["official-first"]["conflicts"],
                    conflict_resolution_report=report,
                    notes="Unpublished candidate: full semantic review and release gates remain outstanding.")
    for name,obj in (("ENGINE_PIN.json",pin),("ENGINE_PIN_FILES.json",manifest)):
        (cwd/name).write_text(json.dumps(obj,indent=4)+"\n",encoding="utf-8")
    gui=cwd/"win/hooklink_gui.pyw"
    s=gui.read_text(encoding="utf-8")
    assert s.count("GUI_VERSION = 'Alpha V1.3.3'")==1
    gui.write_text(s.replace("GUI_VERSION = 'Alpha V1.3.3'","GUI_VERSION = 'Alpha V1.3.4'"),encoding="utf-8")
    # Support this specific new official snapshot without relaxing older
    # version checks. Its full tree is exactly 3082 blobs after exclusions.
    boot=cwd/"win/bootstrap_translator.py"
    s=boot.read_text(encoding="utf-8")
    anchor="_SUPPORTED_ENGINE_BASES = {\n"
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+"    ('4.0', '"+target+"', 'https://github.com/seedds/nxnative.git'),\n")
    anchor="        elif version == '4.0':\n"
    assert s.count(anchor)==1
    s=s.replace(anchor,"        elif version == '4.0' and engine_sha == '"+target+"':\n"
        "            need(record.get('hooklink_engine_commit') == _HOOKLINK_X3_ENGINE\n"
        "                 and meta.get('hooklink_engine_commit') == _HOOKLINK_X3_ENGINE\n"
        "                 and len(record['changed_paths']) == 3082\n"
        "                 and len({r['path'] for r in record['changed_paths']}) == 3082\n"
        "                 and record.get('engine_integration_commit') == meta.get('engine_integration_commit')\n"
        "                 and isinstance(record.get('hooklink_tree'), list)\n"
        "                 and isinstance(record.get('hooklink_omissions'), dict)\n"
        "                 and record.get('conflict_resolution_report', {}).get('unmerged_index_entries') == 0\n"
        "                 and record.get('conflict_resolution_report', {}).get('missing_official_paths') == [],\n"
        "                 'Official-first integration manifest is incomplete')\n"+anchor)
    boot.write_text(s,encoding="utf-8")
    # Adjust only the allowed pin in the test that otherwise cannot import.
    # Leave historic behavior contracts intact to expose every incompatibility.
    p=cwd/"tests/test_engine_pin.py"
    s=p.read_text(encoding="utf-8")
    anchor="_ALLOWED_PINS = {\n"
    assert s.count(anchor)==1
    p.write_text(s.replace(anchor,anchor+"    '"+target+"',\n"),encoding="utf-8")
    git(cwd,"add","ENGINE_PIN.json","ENGINE_PIN_FILES.json","win/bootstrap_translator.py","win/hooklink_gui.pyw","tests/test_engine_pin.py")
    git(cwd,"commit","-m","Prepare unpublished V1.3.4 candidate provenance for complete regression validation")
    head=out(cwd,"rev-parse","HEAD")
    assert out(cwd,"rev-parse","HEAD:engine")==candidate
    git(cwd,"bundle","create",dest/"candidate.bundle","HEAD","^"+local)
    (dest/"candidate.json").write_text(json.dumps({"base":local,"commit":head,"engine_tree":candidate,"semantic_review_complete":False},indent=2)+"\n")
    summary["materialized_candidate"]=head
    summary["provenance"]=evidence
