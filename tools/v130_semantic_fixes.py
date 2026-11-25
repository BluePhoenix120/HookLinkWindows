"""Semantic reconciliation of X3-priority merge regions caught by native Clang."""
import re

def once(s, old, new):
    if s.count(old)!=1: raise RuntimeError("Semantic repair anchor: "+old[:120])
    return s.replace(old,new,1)

def repair(cwd, original, source, notes):
    # The first run recipe merges tests from both parents. Preserve every
    # invoked executable AND its prerequisite, including the new original
    # crash and memory diagnostics whose dependencies fell out of the overlap.
    host_tests=cwd/"dm/host/tests/Makefile"
    mk=host_tests.read_text(encoding="utf-8")
    first=re.search(r"(?m)^run: [^\n]+\n(?:\t[^\n]*\n)+",mk)
    if first is None: raise RuntimeError("Missing host test run recipe")
    deps=set(re.findall(r"\$\(B\)/(t_\w+)", "\n".join(re.findall(r"(?m)^run:[^\n]*",mk))))
    invoked=set(re.findall(r"\$\(B\)/(t_\w+)",first.group(0).split("\n",1)[1]))
    rules=set(re.findall(r"(?m)^\$\(B\)/(t_\w+):",mk))
    missing=invoked-deps
    if missing!={"t_crash_diag","t_memstat"} or not missing<=rules:
        raise RuntimeError("Unexpected host test prerequisite mismatch: "+str(sorted(missing)))
    header=first.group(0).split("\n",1)[0]
    mk=once(mk,header+"\n",header+" "+" ".join("$(B)/"+t for t in sorted(missing))+"\n")
    host_tests.write_text(mk,encoding="utf-8")
    notes.append("dm/host/tests/Makefile: build both crash diagnostics and memory-stat tests before running")
    p=cwd/"dm/host/hle_thread.c"
    s=p.read_text(encoding="utf-8")
    s=once(s,"_Atomic int pause_req; int paused;","_Atomic int pause_req; int paused, act_busy, act_waiters;")
    p.write_text(s,encoding="utf-8")
    notes.append("dm/host/hle_thread.c: retain X3 QoS and original activity serialization fields")
    path="dm/gfx/nvn/nvn_mtl.m"; p=cwd/path
    s=p.read_text(encoding="utf-8"); o=source(cwd,original,path)
    # Preserve X3's hot-memory trimming policy within the original accounted trim API.
    end="static void rh_trim(void) { rh_trim_n(0, NULL); }"
    a=o.index("static uint64_t rh_trim_n(int all, unsigned *n_out) {")
    b=o.index(end,a)+len(end)
    trim=once(o[a:b],"    uint64_t now =", "    all = all || mem_hot();  // X3: release waiting heaps immediately under memory pressure\n    uint64_t now =")
    a=s.index("static void rh_trim(void) {"); b=s.index(end,a)+len(end)
    s=s[:a]+trim+s[b:]
    # The two sides inserted unrelated declarations/implementations at the same
    # source positions. Keep both: official package eviction and X3 pool residency.
    decl="static void mem_trim(void);\nstatic void pkg_sweep(void);\nstatic uint64_t spare_trim(int all, unsigned *n_out);\nstatic void movie_kept_flush(void);\nstatic void movie_trim(int all);\nstatic unsigned g_evict_why[5];\n"
    s=once(s,"static void res_trickle(void) {",decl+"static void res_trickle(void) {")
    a=o.index("static void seen_stamp_used(uint32_t now, int clear) {")
    q=o.index("static void pkg_sweep(void) {",a)
    b=re.search(r"(?m)^}\s*$",o[q:]); assert b
    block=o[a:q+b.end()].rstrip()+"\n"
    s=once(s,"// Profile key pool_skip_retired (",block+"// Profile key pool_skip_retired (")
    s=once(s,"if (g_tu_now - g_tu_last >= TU_EVERY && sw_on(tu_mode())) tu_pass();",
        "if (g_tu_now - g_tu_last >= TU_EVERY) {\n        if (sw_on(tu_mode())) tu_pass();\n        else { g_tu_last = g_tu_now; os_unfair_lock_lock(&g_rmu); seen_stamp_used(g_tu_now, 1); os_unfair_lock_unlock(&g_rmu); }\n    }")
    # Identical forward definitions from the older Windows native repair and
    # newly upstreamed implementation: keep the earlier definition only.
    def duplicate_function(text,name):
        pattern=r"(?m)^static [^\n]*\b"+name+r"\([^\n]*\) \{"
        hits=list(re.finditer(pattern,text))
        assert len(hits)==2, (name,len(hits))
        start=hits[1].start()
        if name=="unb_on": end=text.index("\n",start)+1
        else:
            end=text.index("\n}",start)+2
            if text[end:end+1]=="\n": end+=1
        return text[:start]+text[end:]
    s=duplicate_function(s,"tex_2d_size_exceeds_limit")
    unb="static int g_unb; static p_set_rt g_unb_rt; static uint64_t g_unb_n;\n"
    assert s.count(unb)==2
    n=s.rindex(unb); s=s[:n]+s[n+len(unb):]
    s=duplicate_function(s,"unb_on")
    s=once(s,"    const double tol = 0.002;   // how early a tick may come and still count (HookLink's frame generation below)\n","")
    s=once(s,"ow.ev_val, update.drawable, update.targetPresentationTimestamp);","ow.ev_val, update.drawable, update.targetPresentationTimestamp, 0);")
    s=once(s,"it.ev_val, update.drawable, update.targetPresentationTimestamp);","it.ev_val, update.drawable, update.targetPresentationTimestamp, latched_now ? update.targetTimestamp : 0);")
    # Keep X3 guest mip mapping; validate the host mip before activating the
    # compressed alias pair. Family writes use the translated host level.
    old="    tex_t pair; int paired = bcp_before(c->tex, t, &pair);   // a side of a compressed-alias pair: filled first, the copied region goes into its other side after\n"
    s=once(s,old,"")
    anchor='    if (on_host && !tex_level_ok(t, hl, "buffer-to-texture copy")) return;\n'
    s=once(s,anchor,anchor+old)
    a=s.index("static void copy_b2t("); b=s.index("// Texture copies a blit cannot do",a)
    region=s[a:b]
    region=once(region,"int fam_full = !c->r.xoffset","int fam_full = on_host && !c->r.xoffset")
    region=region.replace("t.width >> level","t.width >> hl").replace("t.height >> level","t.height >> hl")
    region=once(region,"    fam_prepare_write(t, fam_full);","    if (on_host) fam_prepare_write(t, fam_full);")
    s=s[:a]+region+s[b:]
    # The sparse refresh path already performs the alias lookup; retain X3's
    # retirement check without repeating the lookup or declaring ak twice.
    s=once(s,"    alias_key ak = tex_alias_key(t);\n    id shared = own_alias_take(t->serial, &ak);   // found and published in one hold (nvn_owner.m)\n    if (shared) { if (!g_pool_walk) tu_stamp(shared, 0); return tex_mtl_result(shared, owned); }\n","")
    # X3's periodic pool report and original's memory-pressure accounting
    # occupy adjacent insertion points. Retain both implementations.
    a=o.index("    static unsigned long long last_rss, last_gpu, last_frame, last_wired;")
    b=o.index("    int sparse = lines",a)
    a2=s.index("    static unsigned long long last_rss, last_gpu, last_frame;")
    b2=s.index("    int sparse = lines",a2)
    s=s[:a2]+o[a:b]+s[b2:]
    decl="static _Atomic uint64_t g_lib_data_n, g_lib_data_bytes, g_lib_data_fails, g_lib_data_fail_bytes;\nstatic int lib_borrow(void);\n"
    s=once(s,"void mtl_mem_stat(unsigned long long frame, unsigned long long rss_mb) {",decl+"void mtl_mem_stat(unsigned long long frame, unsigned long long rss_mb) {")
    # A stolen pending pipeline must use its own captured border flag,
    # before the slot is freed and another worker can reuse it.
    s=once(s,"MTLRenderPipelineDescriptor *d = g_pp[at].d; g_pp[at].d = nil; pso_pend_free(at); g_pp_stolen++;",
           "MTLRenderPipelineDescriptor *d = g_pp[at].d; int off = g_pp[at].off; g_pp[at].d = nil; pso_pend_free(at); g_pp_stolen++;")
    # The renderer's borrowed pointer ABI wins: the forward declaration,
    # wrapper, and all successful returns already use bridged void pointers.
    a=s.index("static __unsafe_unretained id<MTLRenderPipelineState> pso_get_(")
    b=s.index("\nstatic NSString *warm_key(",a)
    region=s[a:b]
    region=once(region,"static __unsafe_unretained id<MTLRenderPipelineState> pso_get_(","static void *pso_get_(")
    region=once(region,"                        return nil;","                        return NULL;")
    s=s[:a]+region+s[b:]
    # Capture the GPU duration while the queue mutex still protects it.
    s=once(s,"    pthread_cond_broadcast(&g_pq_cv);\n    pthread_mutex_unlock(&g_pq_mu);\n    // Hold the whole ticks",
           "    const double pres_gpu = g_present_gpu_s;\n    pthread_cond_broadcast(&g_pq_cv);\n    pthread_mutex_unlock(&g_pq_mu);\n    // Hold the whole ticks")
    s=once(s,"static CAMetalDisplayLink *g_link; static CFRunLoopRef g_link_rl; static int g_link_started;",
           "static CAMetalDisplayLink *g_link; static CFRunLoopRef g_link_rl; static int g_link_started;\nstatic _Atomic int g_test_link_hold;  // DM_TEST_LINK_STALL diagnostic")
    # Archive probe uses the complete (specialized) descriptor, exactly as
    # the normal build path. Keep the six-argument mesh base interface.
    g=cwd/"dm/gfx/nvn/nvn_geometry.inc"
    geo=g.read_text(encoding="utf-8")
    geo=once(geo,"mtk_desc4(d, ts, ms, ff, k->border) : nil;","mtk_desc4(d, ts, ms, ff, k->border, 0) : nil;")
    g.write_text(geo,encoding="utf-8")
    notes.append("dm/gfx/nvn/nvn_geometry.inc: archive lookup uses complete mesh descriptor")
    p.write_text(s,encoding="utf-8")
    notes.append(path+": reconcile memory trim, eviction, frame generation/latch ABI and mip alias ordering")
