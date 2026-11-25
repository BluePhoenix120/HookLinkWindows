from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
M=(ROOT/'engine/dm/gfx/nvn/nvn_mtl.m').read_text(encoding='utf-8')
G=(ROOT/'engine/dm/gfx/nvn/nvn_geometry.inc').read_text(encoding='utf-8')

class MetalABI(unittest.TestCase):
    def test_borrowed_pipeline_pointer(self):
        self.assertEqual(M.count('static void *pso_get_(NvProg *pr, MTLRenderPassDescriptor *unused)'),2)
        self.assertIn('((__bridge id<MTLRenderPipelineState>)pso_get_ref(pr, unused))',M)
        start=M.index('static void *pso_get_(NvProg *pr, MTLRenderPassDescriptor *unused) {')
        body=M[start:M.index('static NSString *warm_key(',start)]
        self.assertNotIn('return nil;',body)
        self.assertIn('return (__bridge void *)ps;',body)

    def test_pending_slot_metadata_before_free(self):
        start=M.index('static id<MTLRenderPipelineState> pso_pend_take(')
        body=M[start:M.index('static int pso_pend_try(',start)]
        self.assertLess(body.index('int off = g_pp[at].off;'),body.index('pso_pend_free(at)'))
        self.assertIn('return pso_build(d, off, &e);',body)

    def test_mesh_archive_and_display_link(self):
        self.assertIn('mtk_desc4(d, ts, ms, ff, k->border, 0)',G)
        self.assertNotIn('mtk_desc4(d, ts, ms, ff, k->border)',G)
        self.assertIn('static _Atomic int g_test_link_hold;',M)
        start=M.index('const double pres_gpu = g_present_gpu_s;')
        end=M.index('link_gpu_lead(it.frame, it.t_in, cb, wk_cb[k], pres_gpu',start)
        self.assertIn('pthread_mutex_unlock(&g_pq_mu);',M[start:end])
