"""Source-contract tests for the V1.1.9 iOS native host compilation failures.

CI lacks the iPhoneOS SDK; this complements, not replaces, real arm64 Clang compilation.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "engine" / "dm" / "gfx" / "nvn" / "nvn_mtl.m"


class NativeHostCallSiteContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = SRC.read_text(encoding="utf-8")

    def test_pool_entry_signature_has_lead_parameter(self):
        prototype = "static uint64_t pool_entry(int samp, int dtt, int id_, uint64_t limit, int *gone, int *left, int *left_req, int *transient, int *dead, uint32_t *lead) {"
        self.assertEqual(self.s.count(prototype), 1)
        self.assertIn("if (lead && got == MTLTextureTypeTextureBuffer) *lead = tbuf_lead", self.s)

    def test_pool_entry_callers_supply_tenth_argument(self):
        self.assertEqual(len(re.findall(r"\bpool_entry\s*\(", self.s)), 3)
        self.assertIn("pool_entry(samp, dtt, ids[k], limit, &gone, &left, &left_req, &t, &d, NULL)", self.s)
        self.assertIn("pool_entry(samp, dtt, base + i, limit, &gone, &left, &left_req, &t, &d, leads ? leads + i : NULL)", self.s)

    def test_buffer_to_texture_pairs_alias_before_copy(self):
        start = self.s.index("static void copy_b2t(")
        end = self.s.index("// Texture copies a blit cannot do", start)
        body = self.s[start:end]
        self.assertEqual(body.count("tex_t pair; int paired = bcp_before(c->tex, t, &pair);"), 1)
        self.assertLess(body.index("int paired = bcp_before("), body.index("if (paired) bcp_after("))
        self.assertLess(body.index("if (!tex_level_ok("), body.index("int paired = bcp_before("))

    def test_display_link_timestamp_tolerance_is_in_scope(self):
        start = self.s.index("- (void)metalDisplayLink:")
        end = self.s.index("\n@end", start)
        body = self.s[start:end]
        self.assertEqual(body.count("const double tol = 0.002;"), 1)
        self.assertLess(body.index("const double tol = 0.002;"), body.index("g_fg_owe_at - tol"))
        self.assertIn("g_link_hold_until - tol", body)

    def test_link_drain_receives_all_five_arguments(self):
        start = self.s.index("- (void)metalDisplayLink:")
        end = self.s.index("\n@end", start)
        body = self.s[start:end]
        self.assertIn("link_drain_note(cb, cb - it.t_in, ticket > first, -1, 0);", body)
        self.assertNotIn("link_drain_note(cb, cb - it.t_in, ticket > first);", body)
        self.assertIn("static void link_drain_note(double cb, double age, int dropped, double lead, double room)", self.s)

    def test_v116_resource_management_remains_excluded(self):
        self.assertFalse((ROOT / "engine" / "dm" / "gfx" / "tools" / "metal_budget.py").exists())
        self.assertFalse((ROOT / "engine" / "win" / "build_job.py").exists())


if __name__ == "__main__":
    unittest.main()
