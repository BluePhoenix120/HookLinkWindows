"""V1.2.4 guards the full four-commit original NXnative update.

All source paths are already verified byte-for-byte against the new official
tree by test_engine_sync_manifest. These checks prevent important behaviors
from regressing when HookLinkWindows integration conflict policies change.
"""
from pathlib import Path
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/"engine"


class LatestNxNativeDeltaContracts(unittest.TestCase):
    def test_all_recent_original_commits_are_pinned(self):
        pin=json.loads((ROOT/"ENGINE_PIN.json").read_text(encoding="utf-8"))
        m=json.loads((ROOT/"ENGINE_PIN_FILES.json").read_text(encoding="utf-8"))
        self.assertEqual(pin["nxnative_commit"],"3ec5b785f37f8c87d78433f152914d89c4ef93c9")
        self.assertEqual(m["incremental_upstream_to"],pin["nxnative_commit"])
        self.assertEqual(m["incremental_upstream_from"],"d2fd78b402f92d5a83b78987e49aba22e8626719")
        self.assertGreaterEqual(len(m["changed_paths"]),3895)

    def test_new_audio_route_stall_recovery_is_present(self):
        text=(ENGINE/"dm/host/hle_audio.c").read_text(encoding="utf-8")
        for item in ("au_route_stalled", "au_route_recover", "WD_ROUTE_SETTLE_MS", "route_until"):
            self.assertIn(item,text)

    def test_shifted_nup_metadata_and_nacp_check_are_present(self):
        text=(ENGINE/"scripts/pack_nup.py").read_text(encoding="utf-8")
        for item in ("NACP_SIZE = 0x4000", "shifted_meta(", "bad_size", "T_NACP"):
            self.assertIn(item,text)

    def test_latest_ampere_gather_translation_is_present(self):
        text=(ENGINE/"dm/gfx/tools/dmsh_xlate/Program.cs").read_text(encoding="utf-8")
        self.assertIn("QueryHostSupportsNonConstantTextureGatherOffsets()",text)
        self.assertIn("return false;",text)

    def test_native_clang_fixes_survived_full_update(self):
        text=(ENGINE/"dm/gfx/nvn/nvn_mtl.m").read_text(encoding="utf-8")
        self.assertIn("ow.ev_val, update.drawable",text)
        self.assertIn("it.ev_val, update.drawable",text)
        self.assertIn("int shot_ready = -1;",text)
        self.assertIn("uint64_t elapsed = q4_commit_elapsed(&cb, 1, o);",text)
        ndve=(ENGINE/"dm/gfx/nvn/nvn_ndve.inc").read_text(encoding="utf-8")
        self.assertNotIn("(void)dp;",ndve)


if __name__=="__main__":
    unittest.main()
