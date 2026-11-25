"""Release-blocking X3-priority integration contracts."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PIN=json.loads((ROOT/"ENGINE_PIN.json").read_text(encoding="utf-8"))
MANIFEST=json.loads((ROOT/"ENGINE_PIN_FILES.json").read_text(encoding="utf-8"))

class X3Integration(unittest.TestCase):
    def test_all_conflicts_resolved(self):
        self.assertRegex(PIN["release"], r"^Alpha V1\.3\.\d+$")
        self.assertEqual(PIN["nxnative_commit"],"5dfc86ae80c53a62262c3b3c66eab043f1fc574a")
        self.assertEqual(PIN["hooklink_engine_commit"],"ee3ce6a02bc737d38795f0a96cce494cee7a799c")
        r=MANIFEST["conflict_resolution_report"]
        self.assertEqual(sum(x["hunks"] for x in r["upstream"]),64)
        self.assertEqual(sum(x["hunks"] for x in r["windows"]),20)
        self.assertEqual(r["unmerged_index_entries"],0)
        self.assertFalse(r["conflict_marker_paths"])
        self.assertFalse(r["missing_hooklink_changes"])
        self.assertFalse(r["missing_official_paths"])

    def test_all_hooklink_blobs_accounted_for(self):
        overrides=MANIFEST["hooklink_integration_overrides"]
        for row in MANIFEST["hooklink_tree"]:
            p=row["path"]; data=(ROOT/p).read_bytes()
            expected=overrides.get(p,{}).get("integrated_sha",row["sha"])
            def digest(b): return hashlib.sha1(b"blob "+str(len(b)).encode()+bytes([0])+b).hexdigest()
            self.assertIn(expected,(digest(data),digest(data.replace(bytes([13,10]),bytes([10])))),p)

    def test_x3_timing_abi_and_workgroup(self):
        base=ROOT/"engine/dm/gfx/nvn"
        self.assertIn("#define FSTEP_UNIT_OFF 0x48",(base/"nvn_fstep.h").read_text(encoding="utf-8"))
        h=(base/"hle_nvn.c").read_text(encoding="utf-8")
        for marker in ("dm_fps_state + 0x38","dm_fps_state + 0x3c","static void fwg_frame(","fwg_frame(rtp);","void dm_frame_wg_join("):
            self.assertIn(marker,h)
        stub=(ROOT/"engine/dm/games/0400486024DEC000/patches.py").read_text(encoding="utf-8").split("def frame_step(ctx):",1)[1].split("# The game's dynamic resolution",1)[0]
        self.assertIn("0xbd403a00",stub)
        self.assertIn("0xb9003e11",stub)
        self.assertNotIn("ctx.capabilities.add('FRAME_STEP_120')",stub)
        self.assertTrue((ROOT/"Resources/presets/launcher_background.jpg").is_file())

if __name__=="__main__": unittest.main()
