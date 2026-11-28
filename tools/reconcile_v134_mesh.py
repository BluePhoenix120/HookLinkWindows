"""Retain the distinct async mesh-miss feature without obsolete specialization."""
import re

GEOMETRY = "dm/gfx/nvn/nvn_geometry.inc"
METAL = "dm/gfx/nvn/nvn_mtl.m"
BEGIN = "static void mtk_bind_key("
END = "// The scratch buffer of the mesh shaders"
ASYNC = "// Native mesh pipelines built in the background"
CLAIM = "static void mtk_claim("
PSO = "static id<MTLRenderPipelineState> mtk_pso("

def region(s, a, b):
    if s.count(a) != 1 or s.count(b) != 1:
        raise RuntimeError("Nonunique mesh anchors: " + a + " / " + b)
    start = s.index(a)
    end = s.index(b, start)
    return s[start:end]

def replace(s, a, b):
    if s.count(a) != 1:
        raise RuntimeError("Unexpected mesh source anchor: " + a[:120])
    return s.replace(a, b, 1)

def reconcile(cwd, target, windows, read):
    official = read(target, GEOMETRY)
    local = read(windows, GEOMETRY)
    p = cwd/GEOMETRY
    candidate = p.read_text(encoding="utf-8")
    # Everything before mtk_bind_key in the mesh descriptor/build region
    # must be official: never build an unspecialized mesh pipeline base.
    desc_start = "// The Metal 4 descriptor of a native mesh pipeline, whole:"
    assert region(candidate, desc_start, BEGIN) == region(official, desc_start, BEGIN)
    extras = region(local, ASYNC, CLAIM)
    extras = replace(extras, "mtk_desc4(d, ts, ms, ff, k->border, 0)",
                     "mtk_desc4(d, ts, ms, ff, k->border)")
    # Preserve the feature as explicit opt-in pending on-device tests.
    extras = replace(extras, "atoi(e) != 0 : prepare_on()", "atoi(e) != 0 : 0")
    extras = replace(extras, "if (!ps) { MLOG", "if (hm_get_id(&g_pso_mtk, &d[i].k) != g_mtk_pending) continue;\n        if (!ps) { MLOG")
    # The official synchronous path remains the default. Its recording and
    # archive behavior are not replaced by the older HookLink base logic.
    bind = region(official, BEGIN, CLAIM)
    claim = region(official, CLAIM, PSO)
    claim = replace(claim, "current == NSNull.null)", "current == NSNull.null || current == g_mtk_pending)")
    sync = region(official, PSO, END)
    sync = replace(sync, "    NvShader *ts = g_mtk.ts", "    if (mtk_async_on()) mtk_drain();\n    NvShader *ts = g_mtk.ts")
    old_pso = local[local.index(PSO):]
    async_branch = region(old_pso, "    if (mtk_async_on()) {", "    NSError *error = nil; uint64_t start = bp_now();")
    lookup = "    if (ps) return ps == NSNull.null ? nil : ps;"
    sync = replace(sync, lookup, "    if (ps && ps == g_mtk_pending) { g_mtk_skipped++; return nil; }\n" + lookup + "\n" + async_branch.rstrip("\n"))
    candidate = replace(candidate, region(candidate, BEGIN, END), bind + extras + claim + sync)
    assert "int border, int unspec" not in candidate
    assert "mtk_fixed4(" not in candidate
    assert "mtk_base(" not in candidate
    assert "mtk_prefetch_base(" not in candidate
    assert "archived == 2" not in region(candidate, PSO, END)
    p.write_text(candidate, encoding="utf-8")
    # Verify the renderer does not call the now-removed mesh-base ABI.
    # Print any surviving references for review; native compilation will
    # fail if stale declarations or call sites remain.
    metal = (cwd/METAL).read_text(encoding="utf-8")
    stale = [(i, l.strip()) for i,l in enumerate(metal.splitlines(),1)
             if re.search(r'\b(mtk_prefetch|mtk_base|mtk_base_forget|mtk_fixed4|g_mtk_base_ns|g_mtk_base_wait_n|g_mtk_spec)\b',l)]
    for i,l in stale: print(f"Mesh ABI review {METAL}:{i}: {l}", flush=True)
    return {"whole_mesh_pipeline": "official", "async_mesh_miss": "retained, opt-in DM_MESH_ASYNC=1",
            "remaining_mesh_base_references": len(stale)}
