"""Regression tests for the real V1.2.3 Windows-hosted iOS Clang failures.

The 270-file native compile completed all attempted files but Clang rejected
five source errors in the merged Metal renderer. These checks operate without
Apple's SDK on GitHub Windows CI and must not be mistaken for a device build.
"""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
METAL = ROOT / "engine/dm/gfx/nvn/nvn_mtl.m"
NDVE = ROOT / "engine/dm/gfx/nvn/nvn_ndve.inc"


def call_arguments(source, marker):
    """Return balanced function arguments, splitting only top-level commas."""
    pos = 0
    calls = []
    while (at := source.find(marker, pos)) >= 0:
        i = at + len(marker)
        begin = i
        level = 1
        args = []
        while i < len(source) and level:
            if source[i] == "(":
                level += 1
            elif source[i] == ")":
                level -= 1
                if level == 0:
                    args.append(source[begin:i].strip())
                    break
            elif source[i] == "," and level == 1:
                args.append(source[begin:i].strip())
                begin = i + 1
            i += 1
        if level != 0:
            raise AssertionError("Unbalanced call " + marker)
        calls.append(args)
        pos = i + 1
    return calls


class IosMetalNativeMergeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metal = METAL.read_text(encoding="utf-8")
        cls.ndve = NDVE.read_text(encoding="utf-8")

    def test_all_present_now_calls_supply_producer_event_eight_arguments(self):
        all_calls = call_arguments(self.metal, "present_now(")
        definition = next(x for x in all_calls if x[0].startswith("const tex_t *t"))
        self.assertEqual(len(definition), 8, "present_now signature changed")
        invocations = [args for args in all_calls if args is not definition]
        self.assertEqual(len(invocations), 3)
        for args in invocations:
            self.assertEqual(len(args), 8, args)
        self.assertEqual(
            sorted(args[5] for args in invocations),
            ["it.ev_val", "it.ev_val", "ow.ev_val"],
        )

    def test_screenshot_ready_is_defined_before_queue_and_direct_shot(self):
        source = self.metal.split("static int present_now(", 1)[1].split("pthread_mutex_unlock(&g_shotq_mu)", 1)[0]
        self.assertIn("int shot_ready = -1;", source)
        self.assertLess(source.index("int shot_ready = -1;"), source.index("present_shot(src, path"))
        self.assertEqual(source.count("&shot_ready"), 2)
        self.assertNotIn("mtl_finish_gpu(); shot(src, path", source)
        self.assertIn("present_shot(src, g_shotq[i].path, crop, ev_val, &shot_ready)", source)

    def test_snapshot_commit_timing_retains_metal4_commit_options(self):
        source = self.metal.split("static uint64_t snap_take(", 1)[1].split("static uint64_t present_enqueue(", 1)[0]
        self.assertIn("uint64_t elapsed = q4_commit_elapsed(&cb, 1, o)", source)
        self.assertIn('q4_commit_slow(elapsed, "snap_take (snapshot copy)")', source)
        self.assertLess(source.index("uint64_t elapsed ="), source.index("q4_commit_slow(elapsed"))
        self.assertNotIn("[g_q4 commit:&cb count:1 options:o]", source)
        self.assertIn("pthread_mutex_lock(&g_res_commit_mu)", source)
        self.assertIn("pthread_mutex_unlock(&g_res_commit_mu)", source)

    def test_ndve_lite_dispatch_returns_without_undeclared_dp(self):
        self.assertNotIn("(void)dp;", self.ndve)
        self.assertIn("if (!chk && ndve_lite()) ndve_encode_lite", self.ndve)
        self.assertRegex(self.ndve, r"g_nd\.pos = 13;[\s\S]*return !chk;")


if __name__ == "__main__":
    unittest.main()
