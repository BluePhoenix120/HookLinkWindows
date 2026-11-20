"""Prevent silent cross-engine iOS host compilation API drift.

Source contract tests run on the Windows GitHub runner without the proprietary
iPhoneOS SDK. They do NOT replace a real arm64-apple-ios26.0 Clang compilation.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
METAL = ROOT / 'engine' / 'dm' / 'gfx' / 'nvn' / 'nvn_mtl.m'
FRONT = ROOT / 'engine' / 'dm' / 'ios' / 'Sources' / 'front_ios.m'


class IOSHostMergeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mtl = METAL.read_text(encoding='utf-8')
        cls.front = FRONT.read_text(encoding='utf-8')

    def test_texture_alias_result_is_bridge_safe(self):
        self.assertIn(
            'if (shared) { if (!g_pool_walk) tu_stamp(shared, 0); '
            'return tex_mtl_result(shared, owned); }', self.mtl)
        self.assertNotIn('tu_stamp(shared, 0); return shared;', self.mtl)

    def test_compressed_alias_declarations_precede_early_users(self):
        checks = [
            ('static int g_nbcp;', 'if (g_nbcp) { bcp_flush();'),
            ('static void bcp_flush(void);', 'if (g_nbcp) { bcp_flush();'),
            ('static void bcp_wrote(const tex_t *t, id<MTLTexture> m);',
             'bcp_wrote(t, base);'),
            ('static void bcp_idx(int id_, const tex_t *t, int add);',
             'bcp_idx((int)(r - g_treg), &r->t, 0);'),
            ('static int bcp_before(const tex_t *t, id<MTLTexture> m, tex_t *o);',
             'bcp_before(t, mt, &pair);'),
            ('static void bcp_after_to(const tex_t *t, const tex_t *op, unsigned level, const NVNcopyRegion *r);',
             'bcp_after_to(t, &pair, (unsigned)lv, &rr);'),
        ]
        for declaration, first_use in checks:
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, self.mtl)
                self.assertIn(first_use, self.mtl)
                self.assertLess(self.mtl.index(declaration), self.mtl.index(first_use))

    def test_deferred_unbind_state_is_declared(self):
        declaration = 'static int g_unb; static p_set_rt g_unb_rt; static uint64_t g_unb_n;'
        self.assertEqual(self.mtl.count(declaration), 1)
        self.assertIn('static int unb_on(void)', self.mtl)
        self.assertLess(self.mtl.index(declaration),
                        self.mtl.index('if (g_unb) { g_unb = 0; R.rt = g_unb_rt; }'))

    def test_depth_stencil_feedback_forward_contract(self):
        enum = 'enum { FB_DS_DEPTH = 1, FB_DS_STENCIL = 2, FB_DS_BOTH = 3 };'
        forward = 'static void fb_ds_note_write(uint32_t planes);'
        use = 'uint32_t ds_clear = (R.clear_d && pd.depthAttachment.texture ? FB_DS_DEPTH : 0)'
        self.assertEqual(self.mtl.count(enum), 1)
        self.assertEqual(self.mtl.count(forward), 1)
        self.assertLess(self.mtl.index(enum), self.mtl.index(use))
        self.assertLess(self.mtl.index(forward), self.mtl.index('fb_ds_note_write(ds_clear)'))
        self.assertIn('static void fb_ds_note_write(uint32_t planes) {', self.mtl)

    def test_ios_screen_rate_has_one_definition_and_atomic_header(self):
        definitions = re.findall(r'^\s*int\s+front_screen_max_fps\s*\(\s*void\s*\)\s*\{', self.front, re.M)
        self.assertEqual(len(definitions), 1)
        self.assertIn('#include <stdatomic.h>', self.front)
        self.assertNotIn('g_screen_max_fps', self.front)
        self.assertIn('atomic_load_explicit(&g_screen_hz, memory_order_relaxed)', self.front)
        self.assertIn('atomic_exchange_explicit(&g_screen_hz, hz, memory_order_relaxed)', self.front)
        self.assertIn('ws.screen.maximumFramesPerSecond', self.front)
        self.assertIn('if (lpm && hz > 60) hz = 60;', self.front)
        self.assertIn('screen_refresh();', self.front)


if __name__ == '__main__':
    unittest.main()
