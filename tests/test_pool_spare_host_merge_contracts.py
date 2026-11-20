"""Regression tests for two pinned-NXnative iOS host merge conflicts.

These offline source checks cannot replace a complete Apple-SDK Clang compile.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
NVN = ROOT / "engine" / "dm" / "gfx" / "nvn" / "nvn_mtl.m"


class PoolSpareHostMergeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = NVN.read_text(encoding="utf-8")

    def test_demand_recorder_has_one_definition(self):
        self.assertEqual(len(re.findall(r"(?m)^static nvn_hmap g_demand_rec\s*=", self.src)), 1)
        self.assertEqual(len(re.findall(r"(?m)^static void demand_record\s*\(", self.src)), 1)
        self.assertIn("demand_record(&k, vs, fs);", self.src)

    def test_demand_record_retains_early_submission_behavior(self):
        i = self.src.index("static void demand_record(")
        j = self.src.index("static int pso_pend_demand(", i)
        body = self.src[i:j]
        self.assertIn("DM_PSO_DEMAND_RECORD", body)
        self.assertIn("pso_user_record(", body)
        self.assertIn("nvn_hm_put(&g_demand_rec", body)

    def test_pool_spare_type_matches_existing_patch_reuse(self):
        self.assertIn("typedef struct { __strong id<MTLBuffer> buf; uint64_t fence, build, lpos; int k; } pool_spare;", self.src)
        self.assertIn("static pool_spare g_pool_spare[POOL_SPARE_MAX]", self.src)
        self.assertIn("enum { POOL_SPARE_MAX = 64, POOL_SPARE_BYTES = 16 << 20 };", self.src)
        self.assertNotIn("enum { POOL_SPARES = 64 };", self.src)

    def test_pool_spare_helpers_and_counters_are_defined_before_first_use(self):
        first_take = self.src.index("static id<MTLBuffer> pool_table_take(")
        for declaration in (
            "static size_t g_pool_spare_cap = POOL_SPARE_BYTES;",
            "static int spare_live(const pool_spare *s)",
            "static id<MTLBuffer> spare_out(int i)",
            "static uint64_t g_stat_pool_replayed, g_stat_pool_replay_n, g_stat_pool_copied[3], g_stat_pool_take_ns;",
        ):
            self.assertEqual(self.src.count(declaration), 1, declaration)
            self.assertLess(self.src.index(declaration), first_take)
        self.assertIn("g_pool_spare_bytes -= b.length", self.src)
        self.assertIn("g_pool_spare[g_npool_spare].buf = nil", self.src)

    def test_existing_pool_patch_code_uses_matching_spare_structure(self):
        self.assertIn("const pool_spare *s = &g_pool_spare[i]", self.src)
        self.assertIn("s->k != k || s->build != g_plog[k].build", self.src)
        self.assertIn("s->lpos > g_pool_spare[o].lpos", self.src)
        self.assertIn("return spare_out(o)", self.src)
        self.assertIn("g_pool_spare[g_npool_spare] = (pool_spare){b, g_fence + 1", self.src)

    def test_v116_windows_memory_and_job_changes_remain_excluded(self):
        self.assertFalse((ROOT / "engine/dm/gfx/tools/metal_budget.py").exists())
        self.assertFalse((ROOT / "engine/win/build_job.py").exists())


if __name__ == "__main__":
    unittest.main()
