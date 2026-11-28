"""V1.2.5 source-level contracts for complete original NXnative + HookLink/Windows."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
TARGET = "5dfc86ae80c53a62262c3b3c66eab043f1fc574a"
V134 = json.loads((ROOT / "ENGINE_PIN.json").read_text(encoding="utf-8"))["nxnative_commit"] == "f36fa59becd8b3ffc4347e6f9d58e45fe4e51bdf"


class V125UpstreamMergeContracts(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_pinned_full_50_commit_tip_and_manifest(self):
        pin = json.loads(self.read("ENGINE_PIN.json"))
        manifest = json.loads(self.read("ENGINE_PIN_FILES.json"))
        self.assertIn(pin["nxnative_commit"], (TARGET, "f36fa59becd8b3ffc4347e6f9d58e45fe4e51bdf"))
        self.assertGreaterEqual(tuple(map(int, pin["release"].removeprefix("Alpha V").split("."))), (1, 2, 5))
        self.assertEqual(manifest["nxnative_commit"], pin["nxnative_commit"])
        self.assertEqual(manifest["incremental_upstream_to"], pin["nxnative_commit"])
        if pin["nxnative_commit"] == "f36fa59becd8b3ffc4347e6f9d58e45fe4e51bdf":
            self.assertEqual(manifest["incremental_upstream_from"], TARGET)
            self.assertEqual(len(manifest["changed_paths"]), 3082)
        else:
            self.assertEqual(manifest["incremental_upstream_from"], "3e1ada5b96acb61293ac790bd6dd093a947abed6")
            self.assertGreaterEqual(len(manifest["changed_paths"]), 3895)

    def test_game_keeps_iphone_alias_and_new_screen_shape(self):
        settings = self.read("engine/dm/games/0400486024DEC000/game.tsv")
        if V134:
            for row in ("mem_alias\t0x200000000", "mem_reserve\t0x420000000", "mem_map_limit\ton", "mod_input_hold\t660"):
                self.assertIn(row, settings.splitlines())
            patches = self.read("engine/dm/games/0400486024DEC000/patches.py")
            for marker in ("def screen_shape(ctx)", "**screen_shape_functions", "def frame_step_v0(ctx)", "heap_retry(ctx)", "MATCH_CUTS"):
                self.assertIn(marker, patches)
            self.assertNotIn("    wide_view(ctx)", patches)
            return
        self.assertIn("mem_alias\t0x400000000", settings)
        self.assertIn("mem_reserve\t0x620000000", settings)
        self.assertIn("mem_map_limit\toff", settings)
        patches = self.read("engine/dm/games/0400486024DEC000/patches.py")
        self.assertIn("def screen_shape(ctx)", patches)
        self.assertIn("def wide_view(ctx)", patches)
        self.assertIn("if ctx.base == 0x6e6be0:", patches)
        self.assertIn("    wide_view(ctx)", patches)
        self.assertIn("**screen_shape_functions", patches)
        self.assertIn("half_rate(ctx)", patches)
        self.assertIn("MATCH_CUTS", patches)  # X3's current movie cuts take priority

    def test_upstream_and_hooklink_metal_rendering_both_present(self):
        code = self.read("engine/dm/gfx/nvn/nvn_mtl.m")
        for name in ("tex_2d_size_exceeds_limit", "shadow_scale_desc",
                     "g_ed.dbnd[0] = 0;", "g_ed.dbnd[1] = 1;",
                     ):
            self.assertIn(name, code)
        archive = ("static void arch_write_batch(int gate_held)", "arch_keys_write(kp, ep->keys", "arch_pkg_period_done(ep, ok && keyed)") if V134 else (
            "arch_write(ArchEpoch *ep, int gate_held)", "arch_write_file(ep, gate_held);", "arch_write_script(")
        for name in archive:
            self.assertIn(name, code)

    def test_romfs_preserves_windows_binary_mode_and_upstream_cache(self):
        code = self.read("engine/dm/tools/romfs.py")
        self.assertIn("_scan_descriptors.get()", code)
        self.assertIn('getattr(_os, "O_BINARY", 0)', code)

    def test_hooklink_launcher_and_original_settings(self):
        code = self.read("engine/dm/ios/Sources/Launcher.swift")
        self.assertIn("ModStore.shared", code)
        settings = self.read("engine/dm/games/settings.tsv")
        if V134:
            for env in ("DM_SCREEN_ASPECT\t", "DM_FRAMEGEN\t", "DM_MIC\t", "DM_NVN_RC_STALE\t"):
                self.assertIn(env, settings)
            self.assertTrue(any(row.startswith("DM_MIC\t") and "\tplatform:ios\t" in row for row in settings.splitlines()))
            self.assertNotIn("DM_WIDE_VIEW\t", settings)
            self.assertNotIn("DM_WIDE_HUD\t", settings)
            return
        for env in ("DM_WIDE_VIEW\t", "DM_WIDE_HUD\t", "DM_MIC\t",
                    "DM_NVN_RC_STALE\t"):
            self.assertIn(env, settings)

    def test_no_unresolved_three_way_markers(self):
        for path in ("engine/dm/gfx/nvn/nvn_mtl.m",
                     "engine/dm/ios/Sources/Launcher.swift",
                     "engine/dm/games/0400486024DEC000/patches.py"):
            data = self.read(path)
            self.assertNotIn("<<<<<<<", data)
            self.assertNotIn(">>>>>>>", data)


if __name__ == "__main__":
    unittest.main()
