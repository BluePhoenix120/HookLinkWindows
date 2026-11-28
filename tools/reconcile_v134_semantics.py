"""Review cross-layer graphics policy, Windows launcher and audio contracts.

Keep the official playback and render-scale logic. Restore only distinct
iPhone pipeline prewarming and microphone support; the Windows UI must
understand the same generated setting dependencies as the upstream launcher.
"""
import json
import subprocess
import sys

LOADER = "dm/host/loader.c"
PROFILE = "dm/games/0400486024DEC000/game.tsv"
TABLE = "dm/games/settings.tsv"
APP = "win/build_app.py"
UI = "win/ios/Launcher.m"
FRONT = "dm/ios/Sources/front_ios.m"
MIC = "dm/host/mic_apple.m"

def once(s, old, new):
    if s.count(old) != 1:
        raise RuntimeError("Unexpected semantic source anchor: " + old[:150])
    return s.replace(old, new, 1)

def reconcile(cwd, target, windows, read, dest):
    def get(p): return (cwd/p).read_text(encoding="utf-8")
    def put(p,s): (cwd/p).write_text(s,encoding="utf-8")
    # The official DRS stub explicitly respects a fixed render scale < 1.
    # The old HookLink loader zeroed it whenever DRS was enabled. Preserve
    # the unique 25% preset and Cool mode, not that competing override.
    s=get(LOADER)
    start="    // HookLink VX1: with the game's dynamic resolution on"
    end="    memcpy(dm_fps_state + 0x10, &sc, sizeof sc);"
    assert s.count(start)==1 and s.count(end)==1
    a=s.index(start); b=s.index(end,a)
    assert "sc = 0.0f" in s[a:b]
    s=s[:a]+s[b:]
    put(LOADER,s)

    # The upstream OOT profile has no iPhone archive configuration. Keep
    # HookLink's independent target-specific pipeline prebuild opt-in.
    s=get(PROFILE)
    old=read(windows,PROFILE)
    rows=[l for l in old.splitlines() if l.startswith(("pso_mtl4\t","pso_gpu\t"))]
    assert rows==["pso_mtl4\ton","pso_gpu\tapplegpu_g19p"]
    assert not any(l.startswith(("pso_mtl4\t","pso_gpu\t")) for l in s.splitlines())
    put(PROFILE,s.rstrip()+"\n\n# HookLink iPhone pipeline archive and prebuild\n"+"\n".join(rows)+"\n")
    s=get(APP)
    old="('g18p' if prof.get('pso_mtl4', 'off') == 'on' else 'none')"
    new="(','.join(prof.get('pso_gpu', 'g18p').split()) if prof.get('pso_mtl4', 'off') == 'on' else 'none')"
    put(APP,once(s,old,new))

    s=get(TABLE)
    # 0 in the existing mode ABI does not force 60; it uses official
    # target (including 40), buffering, hold and independent FG settings.
    s=once(s,"0=60 fps,1=30 fps steady", "0=Custom (use Frame rate),1=30 fps steady")
    rows=s.splitlines()
    for i,l in enumerate(rows):
        if l.startswith("DM_FRAME_MODE\t"):
            c=l.split("\t")
            c[7]="Custom uses the selected frame rate (including 40 fps where supported). The other modes set the frame rate, buffering, hold and frame generation for you."
            rows[i]="\t".join(c)
    put(TABLE,"\n".join(rows)+"\n")

    # Windows compiles UIKit, not the Swift launcher. Support the official
    # needs metadata, HookLink preset locks, and launch environment overrides.
    s=get(UI)
    s=once(s,"*env, *kind, *label, *note, *def, *section, *on, *off;",
           "*env, *kind, *label, *note, *def, *section, *on, *off, *needs;\n@property (copy) NSArray<NSString *> *sets;")
    s=once(s,'s.section = str(d, @"section"); s.on = str(d, @"on"); s.off = str(d, @"off");',
           '''s.section = str(d, @"section"); s.on = str(d, @"on"); s.off = str(d, @"off"); s.needs = str(d, @"needs");
        if ([d[@"sets"] isKindOfClass:NSArray.class]) s.sets = d[@"sets"];''')
    s=once(s,'    NSString *keys = NSProcessInfo.processInfo.environment[@"DM_ENV_FILE_KEYS"] ?: @"";',
           '''    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    NSString *keys = [NSString stringWithFormat:@"%@ %@", environment[@"DM_ENV_FILE_KEYS"] ?: @"", environment[@"DM_ENV_LAUNCH_KEYS"] ?: @""];
    BOOL ignoreSaved = [environment[@"DM_SAVED_CHOICES"] isEqualToString:@"0"];''')
    s=once(s,'NSString *saved = [ud stringForKey:[@"launcher." stringByAppendingString:s.env]];',
           '''id raw = ignoreSaved ? nil : [ud objectForKey:[@"launcher." stringByAppendingString:s.env]];
        NSString *saved = [raw isKindOfClass:NSString.class] ? raw : nil;''')
    s=once(s,'return [s.sectionTitle isEqualToString:sec];',
           'return [s.sectionTitle isEqualToString:sec] && [self visible:s];')
    s=once(s,'- (BOOL)locked:(DmSetting *)s { return s.disabled || [self.fromFile containsObject:s.env]; }',
           '''- (BOOL)visible:(DmSetting *)s {
    NSArray *parts = [s.needs componentsSeparatedByString:@"="];
    if (parts.count == 2 && self.values[parts[0]] && ![self.values[parts[0]] isEqualToString:parts[1]]) return NO;
    // A non-custom mode owns these values; do not offer a contradictory row.
    NSString *mode = self.values[@"DM_FRAME_MODE"];
    if (mode && [@[@"1", @"2", @"3"] containsObject:mode] &&
        [@[@"DM_FPS_TARGET", @"DM_FRAMEGEN", @"DM_PRESENT_SNAP", @"DM_FPS_HOLD"] containsObject:s.env] &&
        ![self.fromFile containsObject:s.env]) return NO;
    return YES;
}
- (BOOL)presetLocked:(DmSetting *)s {
    for (DmSetting *p in self.settings)
        if ([p.env isEqualToString:@"DM_PRESET"] && [[self value:p] isEqualToString:p.onValue] && [p.sets containsObject:s.env]) return YES;
    return NO;
}
- (BOOL)locked:(DmSetting *)s { return s.disabled || [self.fromFile containsObject:s.env] || [self presetLocked:s]; }''')
    s=once(s,'    if (s.disabled || ![self.fromFile containsObject:s.env]) return s.note;',
           '''    if ([self presetLocked:s]) return [NSString stringWithFormat:@"%@ Set by Potato mode.", s.note ?: @""];
    if (s.disabled || ![self.fromFile containsObject:s.env]) return s.note;''')
    s=once(s,'        [ud removeObjectForKey:[@"launcher." stringByAppendingString:s.env]];\n        if (![self.fromFile containsObject:s.env]) self.values[s.env] = s.def;',
           '''        if (![self.fromFile containsObject:s.env]) self.values[s.env] = s.def;''')
    s=once(s,'- (void)apply {\n    NSUserDefaults *ud = NSUserDefaults.standardUserDefaults;',
           '''- (void)applyPersist:(BOOL)persist {
    NSUserDefaults *ud = NSUserDefaults.standardUserDefaults;
    BOOL ignoreSaved = [NSProcessInfo.processInfo.environment[@"DM_SAVED_CHOICES"] isEqualToString:@"0"];''')
    s=once(s,'        if (def) [ud removeObjectForKey:key]; else [ud setObject:v forKey:key];',
           '        if (persist && !ignoreSaved) { if (def) [ud removeObjectForKey:key]; else [ud setObject:v forKey:key]; }')
    s=once(s,'            [me refreshReset];','            [me.tableView reloadData];')
    s=once(s,'- (void)toggled:(UISwitch *)sw { DmSetting *s = self.m.settings[sw.tag]; self.m.values[s.env] = sw.on ? s.onValue : s.offValue; [self refreshReset]; }',
           '- (void)toggled:(UISwitch *)sw { DmSetting *s = self.m.settings[sw.tag]; self.m.values[s.env] = sw.on ? s.onValue : s.offValue; [self.tableView reloadData]; }')
    s=once(s,'    if (off && !strcmp(off, "0")) { fprintf(stderr, "launcher: off (DM_LAUNCHER=0)\\n"); return false; }',
           '    BOOL skipLauncher = off && !strcmp(off, "0");')
    s=once(s,'    DmLauncherVC *vc = [DmLauncherVC new];',
           '''    if (skipLauncher) {
        if (![NSProcessInfo.processInfo.environment[@"DM_SAVED_CHOICES"] isEqualToString:@"0"]) [model applyPersist:NO];
        return false;
    }
    DmLauncherVC *vc = [DmLauncherVC new];''')
    s=once(s,'        [model apply];','        [model applyPersist:YES];')
    put(UI,s)

    # Official playback and the shared audio input layer must remain exact.
    for p in ("dm/host/hle_audio.c","dm/host/audio_input.c","dm/host/hle_audren.c"):
        assert get(p)==read(target,p), p+": official audio implementation changed"
    # Use the actual callback format; re-open the optional microphone when
    # a new route or media-services reset invalidates its input node.
    s=get(MIC)
    s=once(s,"buf.frameLength, rate);","buf.frameLength, buf.format.sampleRate);")
    s=once(s,"int dm_audio_input_platform_route_changed(void) { return 0; }   // the front end's audio session restarts the outputs; the engine follows the route itself",
           "int dm_audio_input_platform_route_changed(void) { return 1; }   // input layer closes and reopens on the control queue")
    put(MIC,s)
    s=get(FRONT)
    s=once(s,'#import "mic_apple.h"','#import "mic_apple.h"\n#include "audio_input.h"')
    s=once(s,'    if (dm_mic_wanted()) {','    if (dm_mic_available()) {')
    anchor="static void front_ios_audio_watch(void) {\n    NSNotificationCenter *nc"
    s=once(s,anchor,'''static void front_ios_mic_route(void) {
    if (!dm_mic_wanted()) return;
    static dispatch_queue_t q;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ q = dispatch_queue_create("dm.audio.input.route", DISPATCH_QUEUE_SERIAL); });
    dispatch_async(q, ^{ dm_audio_input_route_changed(); });
}
static void front_ios_audio_watch(void) {
    NSNotificationCenter *nc''')
    s=once(s,'        if (!moved && reason == AVAudioSessionRouteChangeReasonCategoryChange) return;',
           '''        BOOL inputMoved = previous && !front_ios_same_outputs(previous.inputs, session.currentRoute.inputs);
        if (inputMoved || moved) front_ios_mic_route();
        if (!moved && reason == AVAudioSessionRouteChangeReasonCategoryChange) return;''')
    s=once(s,'        front_ios_audio_session(); dm_audio_reset();','        front_ios_audio_session(); dm_audio_reset(); front_ios_mic_route();')
    put(FRONT,s)
    result={"official_audio_core_exact":True,"official_render_scale_priority":True,
            "iphone_pipeline_archive":"applegpu_g19p","windows_launcher_dependencies":True,
            "mic_route_reopen":True,"semantic_review_complete":False}
    (dest/"semantic-review.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

def check(cwd,dest):
    program=r"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0,'dm/games')
import game, settings
g=game.load('0400486024DEC000')
assert g.get('pso_mtl4')=='on' and g.get('pso_gpu')=='applegpu_g19p'
os.environ.update(SETTINGS_PLATFORM='ios',GFXAPI='nvn')
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    (root/'main.fixups.tsv').write_text('# FRAME_STEP_120\t1\n# DYNAMIC_RESOLUTION\t1\n# RENDER_SCALE\t1\n# SCREEN_ASPECT\t1\n# HOOKLINK_WIDE\t1\n')
    rows={r['env']:r for r in settings.build('0400486024DEC000',root,root/'absent.nacp')['settings']}
    assert rows['DM_FRAME_MODE']['options'][0]==['0','Custom (use Frame rate)']
    assert '40' in [o[0] for o in rows['DM_FPS_TARGET']['options']]
    assert rows['DM_PSO_MTL4']['default']=='1' and rows['DM_PSO_PREBUILD']['default']=='1'
    assert rows['DM_WIDE_HUD']['needs']=='DM_WIDE_VIEW=1'
    assert 'DM_RENDER_SCALE' in rows['DM_PRESET']['sets']
print('Official timing, iPhone pipeline defaults and launcher dependency schema passed')
"""
    r=subprocess.run([sys.executable,"-c",program],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (dest/"semantic-tests.txt").write_text(r.stdout)
    print(r.stdout,flush=True); r.check_returncode()

def inventory(cwd,target,dest):
    # Preserve exact hunks for semantic review, rather than counting source
    # files or treating compilation as proof of behavioral equivalence.
    names=["dm/gfx/nvn/nvn_mtl.m","dm/gfx/nvn/hle_nvn.c","dm/gfx/nvn/nvn_geometry.inc",
           "dm/gfx/nvn/nvn_ndve.inc","dm/gfx/nvn/nvn_owner.m","dm/ios/Sources/front_ios.m",
           "dm/host/loader.c","dm/host/audio_input.h","dm/host/mic_apple.m"]
    with (dest/"semantic-native-differences.patch").open("wb") as f:
        subprocess.run(["git","diff","--cached","--no-ext-diff",target,"--",*names],cwd=cwd,stdout=f,check=True)
