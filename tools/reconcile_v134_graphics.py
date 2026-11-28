"""Reconcile HookLink frame interpolation with official display timing.

The two paths share one counted display clock. Keep the distinct interpolation
and motion estimation but do not insert an uneven half-frame in an odd hold
(40 Hz on 120 Hz, for example). Cross-thread state uses atomics; owed pictures
are invalidated when the official present queue is discarded or handed off.
"""
import json
import subprocess

RENDERER = "dm/gfx/nvn/nvn_mtl.m"
HLE = "dm/gfx/nvn/hle_nvn.c"
MODE = "dm/host/frame_mode.h"
UI = "win/ios/Launcher.m"
TABLE = "dm/games/settings.tsv"
HEADER = "dm/gfx/nvn/nvn_fg_pacing.h"
TEST = "dm/gfx/tests/t_fg_pacing.c"

PACING = r"""#ifndef NVN_FG_PACING_H
#define NVN_FG_PACING_H
#include <math.h>
#include <stdint.h>
// Only synthesize a midpoint if two equal groups of counted ticks fit.
static inline int nvn_fg_even_hold(double period, double tick) {
    if (!(period > 0 && tick > 0)) return 0;
    double n = period / tick;
    if (!(n >= 1.5 && n <= 120)) return 0;
    unsigned ticks = (unsigned)(n + 0.5);
    return ticks >= 2 && !(ticks & 1) && fabs(n - ticks) <= 0.125;
}
static inline int nvn_fg_debt_allowed(uint64_t epoch, uint64_t current,
                                      int link, int rescue, int covered, int suspended) {
    return epoch == current && link && !rescue && !covered && !suspended;
}
#endif
"""
TEST_SRC = r"""#include "../nvn/nvn_fg_pacing.h"
#include "../../host/frame_mode.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    assert(nvn_fg_even_hold(1.0/30, 1.0/60));
    assert(nvn_fg_even_hold(1.0/60, 1.0/120));
    assert(nvn_fg_even_hold(1.0/30, 1.0/120));
    assert(nvn_fg_even_hold(33333333e-9, 1.0/60));
    assert(!nvn_fg_even_hold(1.0/40, 1.0/120));
    assert(!nvn_fg_even_hold(1.0/40, 1.0/60));
    assert(!nvn_fg_even_hold(1.0/60, 1.0/60));
    assert(!nvn_fg_even_hold(1.0/30, 1.0/30));
    assert(!nvn_fg_even_hold(0, 1.0/60));
    assert(!nvn_fg_even_hold(INFINITY, 1.0/60));
    assert(nvn_fg_debt_allowed(5,5,1,0,0,0));
    assert(!nvn_fg_debt_allowed(4,5,1,0,0,0));
    assert(!nvn_fg_debt_allowed(5,5,0,0,0,0));
    assert(!nvn_fg_debt_allowed(5,5,1,1,0,0));
    assert(!nvn_fg_debt_allowed(5,5,1,0,1,0));
    assert(!nvn_fg_debt_allowed(5,5,1,0,0,1));
    assert(dm_frame_mode_override(0,"DM_FPS_TARGET")==NULL);
    assert(!strcmp(dm_frame_mode_override(1,"DM_FRAMEGEN"),"0"));
    assert(!strcmp(dm_frame_mode_override(2,"DM_FRAMEGEN"),"1"));
    assert(!strcmp(dm_frame_mode_override(2,"DM_FPS_TARGET"),"30"));
    assert(!strcmp(dm_frame_mode_override(3,"DM_FPS_TARGET"),"60"));
    assert(!strcmp(dm_frame_mode_override(3,"DM_FRAMEGEN"),"1"));
    assert(dm_frame_mode_override(3,"DM_FRAMEGEN_SCALE")==NULL);
    setenv("DM_FRAME_MODE","2",1);
    dm_frame_mode_apply();
    assert(!strcmp(getenv("DM_FRAMEGEN"),dm_frame_mode_override(2,"DM_FRAMEGEN")));
    assert(!strcmp(getenv("DM_FPS_TARGET"),dm_frame_mode_override(2,"DM_FPS_TARGET")));
    puts("Frame interpolation clock, debt invalidation, and mode dependency contract passed");
    return 0;
}
"""

def once(s,a,b):
    if s.count(a)!=1: raise RuntimeError("Unexpected graphics source anchor: "+a[:160])
    return s.replace(a,b,1)

def reconcile(cwd, target, windows, read, dest):
    def get(p): return (cwd/p).read_text(encoding="utf-8")
    def put(p,s): (cwd/p).write_text(s,encoding="utf-8")
    put(HEADER,PACING); put(TEST,TEST_SRC)
    s=get(RENDERER)
    s=once(s,'#include "nvn_link_latch.h"', '#include "nvn_link_latch.h"\n#include "nvn_fg_pacing.h"')
    s=once(s,'static pq_item g_fg_owe; static uint64_t g_fg_owe_tk; static double g_fg_owe_at, g_fg_tick; static int g_fg_owed;',
           '''static pq_item g_fg_owe; static uint64_t g_fg_owe_tk, g_fg_epoch; static double g_fg_owe_at;
static _Atomic double g_fg_tick;
static int g_fg_owed;
static void fg_cancel_debt_locked(void) { g_fg_owed = 0; g_fg_epoch++; }''')
    s=once(s,'g_fg_tick: the interval between counted ticks (a running mean)','g_fg_tick: the official counted tick period, published to the snapshot producer')
    s=once(s,'static _Atomic int g_fg_shed; static int g_fg_resume = 30; static uint64_t g_fg_sheds, g_fg_shed_frames, g_fg_calm;',
           'static _Atomic int g_fg_shed; static int g_fg_resume = 30; static uint64_t g_fg_sheds, g_fg_calm; static _Atomic uint64_t g_fg_shed_frames;')
    a='''    { static double t_prev; double t = update.targetPresentationTimestamp, dt = t - t_prev; t_prev = t;   // frame generation: the interval of counted ticks
      if (dt > 0.004 && dt < 0.1) g_fg_tick = g_fg_tick > 0 ? g_fg_tick * 0.9 + dt * 0.1 : dt; }
    const int rate = mtl_link_rate();
    const double tick_period = vp > 0 ? vp : 1.0 / rate;'''
    b='''    const int rate = mtl_link_rate();
    const double tick_period = vp > 0 ? vp : 1.0 / rate;
    atomic_store_explicit(&g_fg_tick, tick_period, memory_order_relaxed);'''
    s=once(s,a,b)
    s=once(s,'(unsigned long long)g_fg_sheds, (unsigned long long)g_fg_shed_frames);',
           '(unsigned long long)g_fg_sheds, (unsigned long long)atomic_load_explicit(&g_fg_shed_frames, memory_order_relaxed));')
    s=once(s,'    pq_item it = g_pq[(ticket - 1) % PQ]; g_link_it_tin = it.t_in;',
           '    pq_item it = g_pq[(ticket - 1) % PQ]; g_link_it_tin = it.t_in;\n    uint64_t fg_epoch = g_fg_epoch;   // queue ownership, while g_pq_mu is held')
    s=once(s,'    tex_t gt; int gen = it.gen && g_fg_tick > 0 && it.period >= 1.5 * g_fg_tick;',
           '    tex_t gt; int gen = it.gen && nvn_fg_even_hold(it.period, tick_period);')
    s=once(s,'    if (submitted && gen) { pthread_mutex_lock(&g_pq_mu); g_fg_owe = it; g_fg_owe_tk = ticket; g_fg_owe_at = update.targetPresentationTimestamp + it.period / 2; g_fg_owed = 1; pthread_mutex_unlock(&g_pq_mu); }',
           '''    if (submitted && gen) {
        pthread_mutex_lock(&g_pq_mu);
        if (nvn_fg_debt_allowed(fg_epoch, g_fg_epoch, g_dm_present_link, g_rescue_mode,
                                atomic_load(&g_covered), atomic_load(&g_present_suspended)) && !atomic_load(&g_present_discard)) {
            g_fg_owe = it; g_fg_owe_tk = ticket;
            g_fg_owe_at = tick_time + it.period / 2;   // same counted clock as the official hold
            g_fg_owed = 1;
        }
        pthread_mutex_unlock(&g_pq_mu);
    }''')
    s=once(s,'    if (!want) { g_link_probe_pending = 0; g_link_probe_at = 0; }',
           '    if (!want) { g_link_probe_pending = 0; g_link_probe_at = 0; fg_cancel_debt_locked(); }')
    s=once(s,'static uint64_t drop_queued_presents_locked(void) {\n    uint64_t n',
           'static uint64_t drop_queued_presents_locked(void) {\n    fg_cancel_debt_locked();\n    uint64_t n')
    s=once(s,'    g_fg_owed = 0;\n    if (g_link_owns_layer)', '    fg_cancel_debt_locked();\n    if (g_link_owns_layer)')
    s=once(s,'        g_fg_owed = 0;   // frame generation: a picture the display link owed before it fell silent is older than this one',
           '        fg_cancel_debt_locked();   // classic presentation invalidates any older owed picture')
    s=once(s,'            g_rescue_mode = g_dm_present_link; g_rescue_n++;',
           '            fg_cancel_debt_locked();\n            g_rescue_mode = g_dm_present_link; g_rescue_n++;')
    s=once(s,'        double tk = g_fg_tick; int two = tk > 0.004 ? period >= 1.5 * tk : period > 0.025;',
           '        double tk = atomic_load_explicit(&g_fg_tick, memory_order_relaxed); int two = nvn_fg_even_hold(period, tk > 0 ? tk : 1.0 / 60.0);')
    s=once(s,'if (two && !paused) g_fg_shed_frames++;','if (two && !paused) atomic_fetch_add_explicit(&g_fg_shed_frames, 1, memory_order_relaxed);')
    # Immutable configuration is first read after Metal initialization but
    # can be requested by both the submit thread and the display thread.
    s=once(s,'static int g_fg_mode = -1;\nstatic int fg_on(void) {\n    if (g_fg_mode >= 0) return g_fg_mode;',
           'static int g_fg_mode; static pthread_once_t g_fg_mode_once = PTHREAD_ONCE_INIT;\nstatic void fg_mode_init(void) {')
    s=once(s,'    return g_fg_mode = v;\n}', '    g_fg_mode = v;\n}\nstatic int fg_on(void) { pthread_once(&g_fg_mode_once, fg_mode_init); return g_fg_mode; }')
    s=once(s,'static double fg_size(void) {\n    static double v = -1; if (v >= 0) return v;',
           'static double g_fg_size = 1; static pthread_once_t g_fg_size_once = PTHREAD_ONCE_INIT;\nstatic void fg_size_init(void) {\n    double v;')
    s=once(s,'    return v;\n}\nstatic int fg_shown_size(', '    g_fg_size = v;\n}\nstatic double fg_size(void) { pthread_once(&g_fg_size_once, fg_size_init); return g_fg_size; }\nstatic int fg_shown_size(')
    # Preserve upstream's residency safety at the actual presentation edge.
    # HookLink snapshots have their own committed residency set; normal game
    # textures must still pass through the original res_commit path.
    assert 'if ((t->serial >> 61) != 1) { uint64_t r0 = now_ns(); res_commit();' in s
    assert 'if (g_snap_res) [cb useResidencySet:g_snap_res];' in s
    put(RENDERER,s)

    # The opt-in Apple workgroup is independent of upstream RT scheduling,
    # but its lazy creation and counters are shared by several guest threads.
    s=get(HLE)
    s=once(s,'static uint64_t g_fwg_joins, g_fwg_fail;\nstatic int fwg_get(void) {\n    if (g_fwg_state) return g_fwg_state > 0;',
           'static _Atomic uint64_t g_fwg_joins, g_fwg_fail;\nstatic pthread_once_t g_fwg_once = PTHREAD_ONCE_INIT;\nstatic void fwg_init(void) {')
    s=once(s,'g_fwg_state = -1; return 0; }   // off unless asked for (launcher: Deadline boost)',
           'g_fwg_state = -1; return; }   // off unless asked for (launcher: Deadline boost)')
    s=once(s,'    return g_fwg_state > 0;\n}\nvoid dm_frame_wg_join',
           '}\nstatic int fwg_get(void) { pthread_once(&g_fwg_once, fwg_init); return g_fwg_state > 0; }\nvoid dm_frame_wg_join')
    # Do not re-enable the obsolete second real-time declaration algorithm:
    # NXnative now tracks individual acquire/replay/encode threads itself.
    # The distinct presenting-thread QoS hook, however, was stranded by merge.
    s=once(s,'    if (o->offscreen) return;   // dropped (nvnWindowInitialize)\n    dm_ue_cvar_tick();',
           '    if (o->offscreen) return;   // dropped (nvnWindowInitialize)\n    dm_frame_thread_qos();   // HookLink: the presenting guest thread carries the frame\n    dm_ue_cvar_tick();')
    put(HLE,s)

    # Single source of truth for preset overrides, shared with the actual
    # Windows/UIKit launcher. Otherwise a 30+FG preset hides the size row
    # because the independently stored DM_FRAMEGEN row is still off.
    s=get(MODE)
    start='    static const char *const set[4][7][2] = {'
    a=s.index(start); b=s.index('    };',a)+len('    };')
    table=s[a:b].replace('    static const char *const set','static const char *const dm_frame_mode_set',1)
    s=s[:a]+s[b:]
    s=once(s,'static inline void dm_frame_mode_apply(void) {',table+'''
static inline const char *dm_frame_mode_override(int mode, const char *key) {
    if (mode < 1 || mode > 3) return NULL;
    for (int i = 0; i < 7 && dm_frame_mode_set[mode][i][0]; i++)
        if (!strcmp(key, dm_frame_mode_set[mode][i][0])) return dm_frame_mode_set[mode][i][1];
    return NULL;
}
static inline void dm_frame_mode_apply(void) {''')
    s=s.replace('set[m][i]', 'dm_frame_mode_set[m][i]')
    put(MODE,s)
    s=get(UI)
    s=once(s,'#include <string.h>','#include <string.h>\n#include "frame_mode.h"')
    s=once(s,'- (BOOL)visible:(DmSetting *)s {\n    NSArray *parts = [s.needs componentsSeparatedByString:@"="];\n    if (parts.count == 2 && self.values[parts[0]] && ![self.values[parts[0]] isEqualToString:parts[1]]) return NO;',
           '''- (NSString *)effectiveValueForEnv:(NSString *)env {
    const char *v = dm_frame_mode_override(self.values[@"DM_FRAME_MODE"].intValue, env.UTF8String);
    return v ? @(v) : self.values[env];
}
- (BOOL)visible:(DmSetting *)s {
    NSArray *parts = [s.needs componentsSeparatedByString:@"="];
    if (parts.count == 2) {
        NSString *effective = [self effectiveValueForEnv:parts[0]];
        if (effective && ![effective isEqualToString:parts[1]]) return NO;
    }''')
    put(UI,s)
    s=get(TABLE)
    rows=s.splitlines()
    for i,l in enumerate(rows):
        if l.startswith("DM_FRAMEGEN_MV\t"):
            c=l.split("\t")
            assert len(c)==8
            rows[i]=l+"\tneeds=DM_FRAMEGEN=1"
    put(TABLE,"\n".join(rows)+"\n")
    # The existing GPU test directly reads g_fg_tick: use explicit atomic read.
    s=get("dm/gfx/tests/t_framegen.m")
    s=once(s,'fabs(g_fg_tick - 1 / 60.0)', 'fabs(atomic_load(&g_fg_tick) - 1 / 60.0)')
    put("dm/gfx/tests/t_framegen.m",s)
    mk=get("dm/gfx/tests/Makefile")
    mk=once(mk,'t_fstep: t_fstep.c ../nvn/nvn_fstep.h',
            't_fg_pacing: t_fg_pacing.c ../nvn/nvn_fg_pacing.h ../../host/frame_mode.h\n\tclang -O2 -Wall -Wextra -Werror -o $@ t_fg_pacing.c\nt_fstep: t_fstep.c ../nvn/nvn_fstep.h')
    put("dm/gfx/tests/Makefile",mk)
    result={"official_clock":True,"even_holds_only":True,"owed_picture_epoch":True,
            "frame_generation_config_once":True,"workgroup_init_once":True,
            "presenting_thread_qos_restored":True,"preset_dependencies_shared":True,
            "native_gpu_execution_required":True,"semantic_review_complete":False}
    (dest/"graphics-semantic-review.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

def check(cwd,dest):
    binary=dest/"fg-pacing-test"
    subprocess.run(["cc","-std=gnu11","-Wall","-Wextra","-Werror","-O2",TEST,"-lm","-o",str(binary)],cwd=cwd,check=True)
    p=subprocess.run([str(binary)],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (dest/"graphics-contract-tests.txt").write_text(p.stdout)
    print(p.stdout,flush=True)
    p.check_returncode()
    binary.unlink()
