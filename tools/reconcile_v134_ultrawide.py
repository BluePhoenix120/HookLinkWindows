"""Keep the official tall-screen ABI and add the distinct HookLink ultrawide mode.

Only the known retail layout gets the old fixed-address hooks. The shared
projection instruction is cut once; a flag-preserving branch selects the
official or HookLink stub. All other original bytes are checked by ctx.site.
"""
import json
import subprocess
import sys

OOT = "dm/games/0400486024DEC000/patches.py"
LOADER = "dm/host/loader.c"
HEADER = "dm/host/dm.h"
FRONT = "dm/ios/Sources/front_ios.m"
TABLE = "dm/games/settings.tsv"

# Function fingerprints must resolve to the reviewed v131072 layout before
# the old fixed-address HookLink patches can be installed.
LAYOUT = {
    'graphics init': 0x1202ce0, 'scene app init': 0x31f3890,
    'base scene defaults': 0x108b300, 'display mgr defaults': 0x36b2bc0,
    'base res read': 0xe82f30, 'display target a': 0xd565a0,
    'display target b': 0xebf370, 'display target c': 0xf96310,
    'layout ortho': 0x1520c80, 'layout view ortho': 0x773b90,
    'perspective proj': 0x3485cc0, 'camera update': 0x33a8c0,
    'device proj': 0x23b910, 'layout calc matrix': 0x14e9980,
    'pane global matrix': 0x152caa0, 'layout pane array': 0x1525d60,
    'pane constructor': 0x1529620, 'movie draw': 0x3b5c710,
}

DISPATCH = r'''
def screen_shape_with_wide(ctx):
    # Official behavior is unchanged on all other builds and match layouts.
    if ctx.base != 0x6e6be0 or any(ctx.others.get(k) != v for k, v in _wide_layout.items()):
        screen_shape(ctx)
        return
    shared = 0x3485cc0
    branches = []
    put = ctx.put
    def defer_shared(off, words, why):
        if off == shared:
            if len(words) != 1 or words[0] >> 26 != 5:
                raise RuntimeError("Unexpected shared projection branch")
            branches.append(words[0])
        else:
            put(off, words, why)
    ctx.put = defer_shared
    try:
        screen_shape(ctx)
        wide_view(ctx)
    finally:
        ctx.put = put
    if len(branches) != 2 or 'SCREEN_ASPECT' not in ctx.capabilities:
        raise RuntimeError("Incomplete official/ultrawide projection hooks")
    def destination(word):
        imm = word & 0x3ffffff
        return shared + ((imm - (1 << 26) if imm & (1 << 25) else imm) << 2)
    start = ctx.here()
    # x16/x17 are free at this site in both implementations. CB(N)Z and
    # direct B preserve flags. Wide width at +0x100 is nonzero only in wide mode.
    ctx.emit(ADRP(16, ctx.here(), ctx.state))
    ctx.emit(0xb9410211)  # ldr w17,[x16,#0x100]
    ctx.emit(0x35000051)  # cbnz w17,+8 (wide branch)
    ctx.emit(B(ctx.here(), destination(branches[0])))
    ctx.emit(B(ctx.here(), destination(branches[1])))
    put(shared, [B(shared, start)], 'official/wide projection dispatch (one cut)')
    ctx.capabilities.add('HOOKLINK_WIDE')
'''

def once(s, old, new):
    if s.count(old) != 1:
        raise RuntimeError("Unexpected ultrawide source anchor: " + old[:100])
    return s.replace(old, new, 1)

def region(s, start, end):
    if s.count(start) != 1 or s.count(end) != 1:
        raise RuntimeError("Unexpected ultrawide region anchors")
    a, b = s.index(start), s.index(end)
    if a >= b: raise RuntimeError("Reversed ultrawide region")
    return s[a:b]

def reconcile(cwd, target, windows, read, dest):
    def get(p): return (cwd/p).read_text(encoding="utf-8")
    def put(p,s): (cwd/p).write_text(s,encoding="utf-8")
    original = read(target, OOT)
    prior = read(windows, OOT)
    wide = region(prior, "# Wide view (DM_WIDE_VIEW, a launcher setting)", "# A full model heap")
    s = get(OOT)
    s = once(s, "from nso_asm import ADRP, B, BL", "from nso_asm import ADRP, ADDI, B, BL")
    s = once(s, "    screen_shape(ctx)\n", "    screen_shape_with_wide(ctx)\n")
    s = once(s, "# A full model heap", wide + "\n_wide_layout = " + repr(LAYOUT) + "\n" + DISPATCH + "\n# A full model heap")
    # Keep the official screen_shape implementation byte-for-byte unchanged.
    anchor = "# Under a host render scale below"
    assert region(s, "def screen_shape(ctx):", anchor) == region(original, "def screen_shape(ctx):", anchor)
    put(OOT, s)

    # Loader parses the capability from the actual patched executable.
    s = get(HEADER)
    anchor = next(l for l in s.splitlines() if "int fstep_t120;" in l)
    put(HEADER, once(s, anchor, anchor+"\n    int hooklink_wide;          // HOOKLINK_WIDE fixups capability"))
    s = get(LOADER)
    line = '        else if (!strcmp(key, "FRAME_STEP_120")) m->fstep_t120 = v != 0;'
    s = once(s,line,line+'\n        else if (!strcmp(key, "HOOKLINK_WIDE")) m->hooklink_wide = v != 0;')
    s = once(s,"static void install_fps_state(module_t *m) {","static int g_hooklink_wide;\nstatic void install_fps_state(module_t *m) {")
    s = once(s,"    g_fstep_t120 = m->fstep_t120;","    g_fstep_t120 = m->fstep_t120;\n    g_hooklink_wide = m->hooklink_wide;")
    old = read(windows, LOADER)
    block = region(old, "    // Wide view (Ocarina of Time's patches.py wide_view)", "    // Screen shape: DM_SCREEN_ASPECT")
    block = once(block, '((wr >= 1.8f && wr <= 2.6f) || (wr >= 1.25f && wr <= 1.74f))', '(wr >= 1.8f && wr <= 2.6f)')
    block = once(block, 'if (wv && !strcmp(wv, "1")', 'if (g_hooklink_wide && !official_tall && wv && !strcmp(wv, "1")')
    block = block.replace("   // (squarer than 16:9 too: an unfolded iPhone Duo, 1.43)", "")
    block = once(block, '      if (g_hooklink_wide', '''      const char *shape = getenv("DM_SCREEN_ASPECT"); char *shape_end = NULL;
      float ratio = shape ? strtof(shape, &shape_end) : 0;
      int official_tall = shape && shape_end != shape && !*shape_end && ratio >= 1.3f && ratio < 1.77f;
      if (g_hooklink_wide''')
    # Remove unreachable squarer-screen branch; official NXnative owns it.
    a = block.index('           else if (hud && wcam <')
    b = block.index('           // The view size', a)
    block = block[:a] + block[b:]
    block = block.replace('hud || wcam < 16.0f / 9.0f ? 0 : (float)w2', 'hud ? 0 : (float)w2')
    s = once(s, "    // Screen shape: DM_SCREEN_ASPECT", block+"    // Screen shape: DM_SCREEN_ASPECT")
    put(LOADER,s)

    # Use the existing iOS window ratio logic, but do not allow an old wide
    # value to leak into a subsequent launch or route a taller window to it.
    s = get(FRONT)
    start = "    {   // Wide view:"
    if start in s:
        a=s.index(start); b=s.index("    self.fill =",a)
        s=s[:a]+s[b:]
    block = region(read(windows, FRONT), start, "    self.fill =")
    block = once(block, '        const char *wv = getenv("DM_WIDE_VIEW");', '        unsetenv("DM_WIDE_ASPECT");\n        const char *wv = getenv("DM_WIDE_VIEW");')
    block = once(block, '((r >= 1.8 && r <= 2.6) || (r >= 1.25 && r <= 1.74))', '(r >= 1.8 && r <= 2.6)')
    block = once(block, 'r < 1.77 ? ", squarer than 16:9" : ""', '""')
    block = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("// (HookLink 1.9:") and "untested on a device)" not in l)+"\n"
    block = block.replace(" or squarer (an unfolded iPhone Duo, an iPad)", "")
    put(FRONT,once(s,"    self.fill =",block+"    self.fill ="))

    # A capability rather than a platform-only setting avoids offering old
    # hard-coded patches for an unknown game build.
    old_rows = [l.split("\t") for l in read(windows,TABLE).splitlines() if l.startswith(("DM_WIDE_VIEW\t","DM_WIDE_HUD\t"))]
    assert len(old_rows)==2
    for row in old_rows:
        row[4] = "platform:ios&fixups:HOOKLINK_WIDE"
        if row[0]=="DM_WIDE_VIEW":
            row[7]="Experimental: fills a wide iPhone screen with a wider 3D view. Taller screens use Picture shape. Takes effect on the next start."
    s=get(TABLE)
    assert not any(l.startswith(("DM_WIDE_VIEW\t","DM_WIDE_HUD\t")) for l in s.splitlines())
    put(TABLE,s.rstrip()+"\n"+"\n".join("\t".join(row) for row in old_rows)+"\n")
    result={"shared_projection_site":"0x3485cc0","official_shape_unchanged":True,"fixed_layout_only":True,
            "wide_only_ratio":"1.8-2.6","capability":"HOOKLINK_WIDE","device_validation_required":True}
    (dest/"ultrawide-reconciliation.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

def check(cwd, dest):
    program=r"""
import importlib.util, sys, types, struct, math
from pathlib import Path
sys.path.insert(0,'dm/tools')
sys.path.insert(0,'dm/games')
import unicorn as uc
from unicorn import arm64_const as arm
spec=importlib.util.spec_from_file_location('oot',Path('dm/games/0400486024DEC000/patches.py'))
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
base=0x4000000; area=0x2000000; state=0x9000000; frame=0xa000000
u=uc.Uc(uc.UC_ARCH_ARM64,uc.UC_MODE_ARM)
for addr,n in ((base,0x4000000),(state,0x1000),(frame,0x1000)): u.mem_map(addr,n)
cursor=[area]; sites={}; cuts={}
def emit(w):
    u.mem_write(base+cursor[0],struct.pack('<I',w)); cursor[0]+=4
def site(off, orig):
    assert off not in cuts
    assert sites.setdefault(off,orig)==orig
def put(off,words,why):
    assert off not in cuts
    cuts[off]=why; u.mem_write(base+off,struct.pack('<'+'I'*len(words),*words))
ctx=types.SimpleNamespace(here=lambda:cursor[0],emit=emit,site=site,put=put,state=state-base,
    base=0x6e6be0,others=p._wide_layout.copy(),capabilities=set())
p.screen_shape_with_wide(ctx)
assert ctx.capabilities=={'SCREEN_ASPECT','HOOKLINK_WIDE'}
assert set(sites)==set(cuts) and cuts[0x3485cc0]=='official/wide projection dispatch (one cut)'
assert 0x3b5c758 in cuts and 0x3b5c774 in cuts
def projection(oh, width, aspect, expected):
    u.mem_write(state,bytes(0x1000))
    u.mem_write(state+0x48,struct.pack('<I',oh))
    u.mem_write(state+0x100,struct.pack('<I',width))
    u.mem_write(state+0x110,struct.pack('<f',aspect))
    if oh:
        r=1920/oh
        u.mem_write(state+0x58,struct.pack('<3f',r,(16/9)/r,.01))
    proj=frame+0x200; fovy=1.0
    u.mem_write(proj+0xa0,struct.pack('<5f',fovy,math.sin(fovy/2),math.cos(fovy/2),math.tan(fovy/2),16/9))
    u.reg_write(arm.UC_ARM64_REG_X0,proj)
    u.reg_write(arm.UC_ARM64_REG_SP,frame+0xf00)
    start=base+0x3485cc0
    u.emu_start(start,start+4,count=2000)
    assert u.reg_read(arm.UC_ARM64_REG_PC)==start+4
    got=struct.unpack('<5f',u.mem_read(proj+0xa0,20))
    assert abs(got[-1]-expected)<1e-5,got
    if not oh: assert abs(got[0]-fovy)<1e-6,got
projection(0,0,0,16/9)
projection(1200,0,0,1.6)
projection(0,3200,3200/1440,3200/1440)
# Unknown layouts only get official hooks; missing fingerprint gets neither.
for altered,want in ((dict(p._wide_layout,**{'perspective proj':0x3485dc0}),{'SCREEN_ASPECT'}),
                     (dict(p._wide_layout,**{'movie draw':None}),set())):
    seen={}; cap=set(); c=[0x2000000]
    def e(w): c[0]+=4
    q=types.SimpleNamespace(here=lambda:c[0],emit=e,site=lambda o,b:None,put=lambda o,w,y:seen.setdefault(o,y),
        state=state-base,base=0x6e6be0,others=altered,capabilities=cap)
    p.screen_shape_with_wide(q)
    assert cap==want and 0x3b5c758 not in seen
import tempfile, os, settings
os.environ.update(SETTINGS_PLATFORM='ios',GFXAPI='nvn')
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    for capable in (False,True):
        (root/'main.fixups.tsv').write_text('# SCREEN_ASPECT\t1\n'+('# HOOKLINK_WIDE\t1\n' if capable else ''))
        env={r['env'] for r in settings.build('0400486024DEC000',root,root/'absent.nacp')['settings']}
        assert ('DM_WIDE_VIEW' in env)==capable and ('DM_WIDE_HUD' in env)==capable
        assert 'DM_SCREEN_ASPECT' in env
print('Ultrawide projection dispatch, original layout gates and launcher capability passed')
"""
    r=subprocess.run([sys.executable,"-c",program],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (dest/"ultrawide-tests.txt").write_text(r.stdout)
    print(r.stdout,flush=True)
    r.check_returncode()
