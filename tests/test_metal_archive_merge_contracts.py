"""Regression checks for NXnative Metal 4 archive helper integration.

These source checks run on Windows CI without the iPhoneOS SDK.
A real clang arm64-apple-ios build is still required.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "engine" / "dm" / "gfx" / "nvn" / "nvn_mtl.m"


class MetalArchiveMergeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SRC.read_text(encoding="utf-8")
        cls.begin = cls.source.index("static ArchPlan *arch_plan(NSString *device) {")
        cls.end = cls.source.index("// The prewarm files of the bundle", cls.begin)
        cls.region = cls.source[cls.begin:cls.end]

    def test_archive_file_validation_is_declared_once(self):
        self.assertEqual(self.source.count("static int arch_file_check(NSString *path, arch_reads *rd)"), 1)
        self.assertIn("return arch_file_size(path, rd) != 0;", self.source)
        self.assertIn("arch_file_check(path, &rd)", self.source)
        self.assertIn("arch_file_check(path, NULL)", self.source)

    def test_archive_plan_is_a_consistent_object(self):
        self.assertIn("ArchPlan *p = [ArchPlan new];", self.region)
        self.assertIn("p->bundle =", self.region)
        self.assertIn("p->prewarm =", self.region)
        self.assertIn("p->run =", self.region)
        self.assertIn("return p;", self.region)
        plan = self.region.split("// Top-level mappings", 1)[0]
        self.assertNotIn("NSString *p =", plan)
        self.assertNotRegex(plan, r"\breturn\s*;")

    def test_archive_admission_definitions_are_present(self):
        for symbol in ("arch_vm_room", "arch_admit", "pso_bundle_open"):
            self.assertEqual(len(re.findall(r"(?m)^static\s+(?:int|void)\s+" + symbol + r"\s*\(", self.region)), 1, symbol)
        self.assertIn("arch_file_size(p, NULL)", self.region)
        self.assertIn("arch_vm_room(&free, &largest)", self.region)
        self.assertIn("reserve <= largest - bytes", self.region)

    def test_bundle_open_preserves_runtime_archive(self):
        self.assertIn("g_arch_bundle = a; g_bundle_dir = dir; [archp addObject:a];", self.region)
        self.assertIn("id<MTL4Archive> a = arch_open(p, &ae);", self.region)
        self.assertIn("pso_bundle_open(archp, plan);", self.source)
        self.assertIn("if (!arch_admit(plan, g_arch_dir))", self.source)
        self.assertIn("pso_bundle_open_prewarm(arch, plan);", self.source)

    def test_no_memory_scheduler_from_v116(self):
        self.assertFalse((ROOT / "engine" / "dm" / "gfx" / "tools" / "metal_budget.py").exists())
        self.assertFalse((ROOT / "engine" / "win" / "build_job.py").exists())


if __name__ == "__main__":
    unittest.main()
