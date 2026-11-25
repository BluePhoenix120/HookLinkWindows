#!/usr/bin/env python3
"""Finalize exact, validated X3-first candidate in a CI checkout.

This runs after integrate_v130_hooklink_priority.py. It does not publish;
all final release checks operate on the exact resulting detached commit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from integrate_v130_hooklink_priority import POLICY, require
from audit_v128_integration import ROOT, OLD_ORIGINAL, NEW_ORIGINAL, NEW_HOOK, NEW_APP, git, out

RELEASE = "Alpha V1.3.0"
OLD_RELEASE = "Alpha V1.2.8"


def dump(path, value):
    (ROOT/path).write_text(json.dumps(value, indent=4)+"\n", encoding="utf-8")


def read(path):
    return (ROOT/path).read_text(encoding="utf-8")


def edit(path, old, new):
    s = read(path)
    require(old in s, "Expected metadata/test anchor in " + path + ": " + old[:100])
    (ROOT/path).write_text(s.replace(old,new), encoding="utf-8")


def sha(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


def finalize(dest):
    report=json.loads((dest/"summary.json").read_text())
    require(report.get("source_materialized"), "No exact materialized engine")
    require(report.get("unmerged_index_entries")==0 and not report.get("conflict_marker_paths"), "Unresolved conflicts")
    require(not report.get("missing_hooklink_changes") and not report.get("missing_official_paths"), "Source inventory incomplete")
    require(report["official"]==NEW_ORIGINAL and report["hooklink"]==NEW_HOOK and report["desktop"]==NEW_APP, "Unexpected upstream identities")
    require(sum(x["hunks"] for x in report["upstream"])==64 and sum(x["hunks"] for x in report["windows"])==20, "Unexpected conflict inventory")
    require(not out(ROOT,"ls-files","-u"), "Unmerged index")
    require(read("VERSION").strip()=="4.0","Desktop X3 VERSION missing")

    # Preserve exact historical Windows compiler fingerprint, then compute
    # the actual source-derived version for the new engine. The normal
    # Windows preflight rebuilds/synchronizes the user's installed translator.
    chain_script=ROOT/"engine/dm/gfx/tools/dmsh_chain.py"
    chain=subprocess.check_output([sys.executable,str(chain_script),"--header"],cwd=ROOT,text=True).strip()
    require(re.fullmatch("[0-9a-f]{12}",chain) is not None,"Invalid source-derived shader chain")
    pin=json.loads(read("ENGINE_PIN.json")); manifest=json.loads(read("ENGINE_PIN_FILES.json"))
    require(pin["release"]==OLD_RELEASE and pin["nxnative_commit"]==OLD_ORIGINAL,"Unexpected previous release")
    (ROOT/"docs/HOOKLINK_X3_UPSTREAM_CHANGELOG.md").write_bytes((dest/"hooklink-x3-upstream-changelog.md").read_bytes())
    # Record all source differences, including independent changes. Both
    # upstream trees have their own independently verifiable Git blob hashes.
    excluded=set(report["explicit_exclusions"])
    clean_deleted=set(report["clean_official_deletions"])
    def record(tree_file,allowed_missing):
        t=json.loads((dest/tree_file).read_text())
        files=[]; overrides={}
        for p,(_,digest) in sorted(t.items()):
            if p in excluded or p in allowed_missing: continue
            path="engine/"+p; file=ROOT/path
            require(file.is_file(),"Missing source "+path)
            actual=sha(file.read_bytes())
            files.append({"path":path,"sha":digest})
            if actual!=digest:
                overrides[path]={"upstream_sha":digest,"integrated_sha":actual,
                                 "reason":"X3-first original/HookLink merge, independently retained Windows changes, or documented ABI adaptation"}
        return files,overrides
    official, overrides=record("official-tree.json",set())
    hook, hook_overrides=record("hooklink-tree.json",clean_deleted)
    # A real source integration commit, not an invented upstream pin.
    git(ROOT,"config","user.name","HookLinkWindows release integration")
    git(ROOT,"config","user.email","41898282+github-actions[bot]@users.noreply.github.com")
    git(ROOT,"add","-A")
    git(ROOT,"commit","-m","Integrate official NXnative and HookLink X3: all 84 conflicts resolved with HookLink priority")
    integration=out(ROOT,"rev-parse","HEAD")
    pin.update(hooklink_base="4.0",nxnative_commit=NEW_ORIGINAL,hooklink_engine_commit=NEW_HOOK,
               engine_integration_commit=integration,shader_chain=chain,release=RELEASE,
               engine_integration_policy="upstream-first: "+POLICY,incremental_upstream_from=OLD_ORIGINAL,
               incremental_upstream_to=NEW_ORIGINAL,hooklink_desktop_commit=NEW_APP)
    manifest.update({k:pin[k] for k in ("nxnative_commit","hooklink_engine_commit","engine_integration_commit",
        "engine_integration_policy","incremental_upstream_from","incremental_upstream_to","hooklink_desktop_commit")})
    manifest.update(changed_paths=official,integration_overrides=overrides,windows_overlays=sorted(overrides),
        hooklink_tree=hook,hooklink_integration_overrides=hook_overrides,
        original_hooklink_conflicts=["engine/"+x["path"] for x in report["upstream"]],
        windows_reviewed_hunk_conflicts=["engine/"+x["path"] for x in report["windows"]],
        conflict_resolution_report=report,clean_official_deletions=sorted(clean_deleted),
        platform_binary_exclusions=[{"path":"engine/"+p,"reason":"Non-Windows prebuilt binary; rebuild on Windows"} for p in sorted(excluded)])
    dump("ENGINE_PIN.json",pin);dump("ENGINE_PIN_FILES.json",manifest)
    edit("win/hooklink_gui.pyw","GUI_VERSION = 'Alpha V1.2.8'","GUI_VERSION = 'Alpha V1.3.0'")
    # Exact new pair accepted; never disable provenance validation.
    edit("win/bootstrap_translator.py","_HOOKLINK_X201_ENGINE =", "_HOOKLINK_X3_ENGINE = '"+NEW_HOOK+"'\n_HOOKLINK_X201_ENGINE =")
    edit("win/bootstrap_translator.py","_SUPPORTED_ENGINE_BASES = {","_SUPPORTED_ENGINE_BASES = {\n    ('4.0', '"+NEW_ORIGINAL+"', 'https://github.com/seedds/nxnative.git'),")
    edit("win/bootstrap_translator.py","if version in ('3.0', '3.0.1'):","if version in ('3.0', '3.0.1', '4.0'):")
    edit("win/bootstrap_translator.py","        else:\n            need(len(record['changed_paths']) >= 250","        elif version == '4.0':\n            need(record.get('hooklink_engine_commit') == _HOOKLINK_X3_ENGINE\n                 and meta.get('hooklink_engine_commit') == _HOOKLINK_X3_ENGINE\n                 and len(record['changed_paths']) >= 3800\n                 and isinstance(record.get('hooklink_tree'), list)\n                 and record.get('conflict_resolution_report', {}).get('unmerged_index_entries') == 0\n                 and not record.get('conflict_resolution_report', {}).get('missing_hooklink_changes'),\n                 'X3 integration manifest is incomplete')\n        else:\n            need(len(record['changed_paths']) >= 250")
    # Version-specific regression expectations track the new pinned tree,
    # not a stale snapshot. Behavioral tests are otherwise retained.
    for path in ("tests/test_engine_sync_manifest.py","tests/test_latest_nxnative_delta.py",
                 "tests/test_upstream_first_contracts.py","tests/test_audio_producer_rt_contracts.py"):
        edit(path,OLD_ORIGINAL,NEW_ORIGINAL)
    edit("tests/test_engine_sync_manifest.py","698b46bc5b14510fffc0a4b8fd4bf78309004e4c",NEW_HOOK)
    edit("tests/test_latest_nxnative_delta.py","3ec5b785f37f8c87d78433f152914d89c4ef93c9",OLD_ORIGINAL)
    edit("tests/test_engine_pin.py","    '"+OLD_ORIGINAL+"',","    '"+OLD_ORIGINAL+"',\n    '"+NEW_ORIGINAL+"',")
    edit("tests/test_alpha100_bootstrap.py","            ('3.0.1', '"+OLD_ORIGINAL+"'),","            ('3.0.1', '"+OLD_ORIGINAL+"'),\n            ('4.0', '"+NEW_ORIGINAL+"'),")
    edit("tests/test_bahs_record_guard.py","0272b8d46727ed5d8139b5510df35ddd0633c321",next(x["sha"] for x in official if x["path"]=="engine/dm/gfx/tools/shader_split.py"))
    path="tests/test_upstream_first_contracts.py"
    content=read(path)
    content,n=re.subn(r"        self.assertEqual\(reviewed,\{\n.*?\n        \}\)", "        self.assertEqual(reviewed, set("+repr(manifest["windows_reviewed_hunk_conflicts"])+"))",content,count=1,flags=re.S)
    require(n==1,"Windows conflict expectation changed")
    (ROOT/path).write_text(content,encoding="utf-8")
    # Keep the original regression tests for historical behaviors where
    # still applicable, updating the explicit X3-priority choices.
    path="tests/test_v125_upstream_merge_contracts.py"
    s=read(path).replace(OLD_ORIGINAL,NEW_ORIGINAL).replace("3ec5b785f37f8c87d78433f152914d89c4ef93c9",OLD_ORIGINAL)
    s=s.replace("        self.assertIn(\"        screen_shape(ctx)\", patches)\n","")
    s=s.replace("        self.assertNotIn(\"MATCH_CUTS =\", patches)  # documented HookLink iPhone movie fix","        self.assertIn(\"MATCH_CUTS\", patches)  # X3's current movie cuts take priority")
    s=s.replace('self.assertIn("private var settingsTab", code)','self.assertIn("ModStore.shared", code)')
    # X3's camera/shape settings supersede the old mutually-exclusive row.
    s=s.replace('"DM_SCREEN_ASPECT\\t", ','')
    (ROOT/path).write_text(s,encoding="utf-8")
    # Current X3 retains the wide-view call, with its new function indentation.
    edit("tests/test_v125_upstream_merge_contracts.py",'self.assertIn("        wide_view(ctx)", patches)','self.assertIn("    wide_view(ctx)", patches)')
    # Preserve the cache tests against the production supplemental table API.
    p="tests/test_allow_damaged_external_reuse.py"
    edit(p,"'shader_facts.tsv', 'shader_pairs.tsv', 'pso_pairs.tsv')","'shader_facts.tsv', 'shader_pairs.tsv', 'pso_pairs.tsv', 'geo_pairs.tsv', 'mesh_pairs.tsv')")
    edit(p,"'split_output_key', 'split_profile_inputs', 'split_shaders'}","'split_output_key', 'split_profile_inputs', 'split_shaders', 'side_table'}")
    edit(p,"    ns['SPLIT_TABLES'] = TABLES","    ns['SPLIT_TABLES'] = TABLES\n    ns['SPLIT_SIDE_TABLES'] = ('pso_pairs.tsv', 'geo_pairs.tsv', 'mesh_pairs.tsv')")
    # The new split stores supplemental tables beside the temporary package;
    # the test still exercises actual production cache and manifest logic.
    p="tests/test_native_host_callsite_contracts.py"
    edit(p,'body.index("if (!tex_level_ok(")','body.index("if (on_host && !tex_level_ok(")')
    edit(p,'self.assertIn("link_drain_note(cb, cb - it.t_in, ticket > first, -1, 0);", body)','self.assertIn("link_drain_note(cb, cb - it.t_in, ticket > first, k < 0 || wk_cb[k] < 0 ? -1 : it.t_in - wk_cb[k], gl, k < 0 ? 0 : wk_room[k]);", body)')
    edit(p,"static void link_drain_note(double cb, double age, int dropped, double lead, double room)","static void link_drain_note(double cb, double age, int dropped, double lead, double gpu_lead, double room)")
    edit(p,"def test_link_drain_receives_all_five_arguments","def test_link_drain_receives_all_six_arguments")
    p="tests/test_native_metal_merge_contracts.py"
    edit(p,"def test_all_present_now_calls_supply_producer_event_eight_arguments","def test_all_present_now_calls_supply_producer_event_nine_arguments")
    edit(p,'self.assertEqual(len(definition), 8,','self.assertEqual(len(definition), 9,')
    edit(p,"self.assertEqual(len(args), 8, args)","self.assertEqual(len(args), 9, args)\n            self.assertIn(args[8], ('0', 'latched_now ? update.targetTimestamp : 0'))")
    # Source contract for new timing page and preservation of both trees.
    (ROOT/"tests/test_v130_integration.py").write_text('''"""Release-blocking X3-priority integration contracts."""\nimport hashlib\nimport json\nfrom pathlib import Path\nimport unittest\n\nROOT=Path(__file__).resolve().parents[1]\nPIN=json.loads((ROOT/"ENGINE_PIN.json").read_text(encoding="utf-8"))\nMANIFEST=json.loads((ROOT/"ENGINE_PIN_FILES.json").read_text(encoding="utf-8"))\n\nclass X3Integration(unittest.TestCase):\n    def test_all_conflicts_resolved(self):\n        self.assertEqual(PIN["release"],"Alpha V1.3.0")\n        self.assertEqual(PIN["nxnative_commit"],"'''+NEW_ORIGINAL+'''")\n        self.assertEqual(PIN["hooklink_engine_commit"],"'''+NEW_HOOK+'''")\n        r=MANIFEST["conflict_resolution_report"]\n        self.assertEqual(sum(x["hunks"] for x in r["upstream"]),64)\n        self.assertEqual(sum(x["hunks"] for x in r["windows"]),20)\n        self.assertEqual(r["unmerged_index_entries"],0)\n        self.assertFalse(r["conflict_marker_paths"])\n        self.assertFalse(r["missing_hooklink_changes"])\n        self.assertFalse(r["missing_official_paths"])\n\n    def test_all_hooklink_blobs_accounted_for(self):\n        overrides=MANIFEST["hooklink_integration_overrides"]\n        for row in MANIFEST["hooklink_tree"]:\n            p=row["path"]; data=(ROOT/p).read_bytes()\n            expected=overrides.get(p,{}).get("integrated_sha",row["sha"])\n            def digest(b): return hashlib.sha1(b"blob "+str(len(b)).encode()+bytes([0])+b).hexdigest()\n            self.assertIn(expected,(digest(data),digest(data.replace(bytes([13,10]),bytes([10])))),p)\n\n    def test_x3_timing_abi_and_workgroup(self):\n        base=ROOT/"engine/dm/gfx/nvn"\n        self.assertIn("#define FSTEP_UNIT_OFF 0x48",(base/"nvn_fstep.h").read_text(encoding="utf-8"))\n        h=(base/"hle_nvn.c").read_text(encoding="utf-8")\n        for marker in ("dm_fps_state + 0x38","dm_fps_state + 0x3c","static void fwg_frame(","fwg_frame(rtp);","void dm_frame_wg_join("):\n            self.assertIn(marker,h)\n        stub=(ROOT/"engine/dm/games/0400486024DEC000/patches.py").read_text(encoding="utf-8").split("def frame_step(ctx):",1)[1].split("# The game's dynamic resolution",1)[0]\n        self.assertIn("0xbd403a00",stub)\n        self.assertIn("0xb9003e11",stub)\n        self.assertNotIn("ctx.capabilities.add('FRAME_STEP_120')",stub)\n        self.assertTrue((ROOT/"Resources/presets/launcher_background.jpg").is_file())\n\nif __name__=="__main__": unittest.main()\n''',encoding="utf-8")
    release_note=("## HookLinkWindows Alpha V1.3.0 (2026-11-25)\n\n"
      "- Integrates HookLink X3 (4.0), engine "+NEW_HOOK[:12]+", with official NXnative "+NEW_ORIGINAL[:12]+". "
      "Official NXnative is the base; X3 wins overlapping changes. All 64 upstream and 20 Windows replay conflict hunks have explicit resolutions.\n"
      "- Keeps HookLink's measured frame duration at state +0x38; the official optional tick-unit field is moved to +0x48. "
      "The conflicting official Ocarina 40 fps stub is not offered. The X3 frame-workgroup implementation is preserved.\n"
      "- Preserves independent Windows build/SDK/translator compatibility, the Ocarina 16 GiB alias, and existing caches. "
      "New shader-chain "+chain+" is generated from the integrated sources; Windows preflight verifies the installed translator and may rebuild shaders.\n"
      "- Includes the X3 engine/desktop changes, packaged background support, mod resource-size-table packaging, and native Custom controller layout. "
      "The Windows UIKit launcher does not yet include X3’s full SwiftUI photo picker or mod-management UI. End-to-end game IPA and device runtime require user testing.\n"
      "- Exact source inventories and conflict decisions are in ENGINE_PIN_FILES.json. See the original X3 changelog in docs/HOOKLINK_X3_UPSTREAM_CHANGELOG.md.\n\n")
    edit("CHANGELOG.md","# Changelog\n","# Changelog\n\n"+release_note)
    s=read("README.md")
    s=("## Alpha V1.3.0 — HookLink X3 + updated original NXnative\n\n"+release_note.split("\n\n",1)[1]+s)
    s=s.replace("**Latest release: [Alpha V1.2.8]","**Latest release: [Alpha V1.3.0]").replace("releases/download/v1.2.8-alpha.1/","releases/download/v1.3.0-alpha.1/").replace("**Alpha V1.2.8 — experimental Windows port","**Alpha V1.3.0 — experimental Windows port")
    (ROOT/"README.md").write_text(s,encoding="utf-8")
    git(ROOT,"add","-A")
    git(ROOT,"commit","-m","Release Alpha V1.3.0: X3-priority merged engine provenance and validation contracts")
    candidate=out(ROOT,"rev-parse","HEAD")
    print("V1.3.0 candidate",candidate,"chain",chain,"official",len(official),"HookLink",len(hook),flush=True)
    (dest/"candidate.json").write_text(json.dumps({"commit":candidate,"base":report["base_main"],"chain":chain},indent=2)+"\n",encoding="utf-8")
    git(ROOT,"bundle","create",str(dest/"candidate.bundle"),"HEAD","^"+report["base_main"])


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);finalize(p.parse_args().output.resolve())
