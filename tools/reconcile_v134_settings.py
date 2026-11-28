"""Official game profile and settings defaults, plus independent HookLink features."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PROFILE = "dm/games/0400486024DEC000/game.tsv"
TABLE = "dm/games/settings.tsv"
LOADER = "dm/host/loader.c"
MODE = "dm/host/frame_mode.h"
APP = "win/build_app.py"

# These are distinct additions, not replacements of official profile keys.
# Memory geometry and map limiting intentionally follow the official profile.
UNIQUE = {"pad_theme", "mod_input_hold", "potato"}
# These controls are obsolete after official timing, shape and pool changes.
# Ultrawide requires a separate patch-site review before it can be offered.
DEFER = {"DM_WIDE_VIEW", "DM_WIDE_HUD"}

def data_rows(s):
    return [l for l in s.splitlines() if l.strip() and not l.lstrip().startswith("#")]

def key(l):
    return l.split("\t", 1)[0]

def reconcile(cwd, target, windows, read):
    def get(p): return (cwd/p).read_text(encoding="utf-8")
    def put(p,s): (cwd/p).write_text(s,encoding="utf-8")
    official = read(target, PROFILE)
    old = data_rows(read(windows, PROFILE))
    extra = [l for l in old if key(l) in UNIQUE]
    # Keep the independent preset, without obsolete texture retirement knobs.
    extra = [l.replace(",DM_NVN_ALIAS_HI=60,DM_NVN_ALIAS_LO=50", "") if key(l)=="potato" else l for l in extra]
    assert {key(l) for l in extra} == UNIQUE
    put(PROFILE, official.rstrip("\n")+"\n\n# Independent HookLink features\n"+"\n".join(extra)+"\n")
    official = read(target, TABLE)
    old = data_rows(read(windows, TABLE))
    known = {key(l) for l in data_rows(official)}
    # Keep iOS microphone controls (official microphone rows are mac-only).
    unique = list(dict.fromkeys(l for l in old if key(l) not in DEFER and
               (key(l) not in known or (key(l) in {"DM_MIC","DM_MIC_GAIN"} and l.split("\t")[4]=="platform:ios"))))
    put(TABLE, official.rstrip("\n")+"\n\n# Independent HookLink launcher controls\n"+"\n".join(unique)+"\n")
    # The candidate no longer installs the old wide-view guest stubs.
    # Do not publish state writes for the absent patches, even from old env files.
    s = get(LOADER)
    start = "    // Wide view (Ocarina of Time's patches.py wide_view)"
    end = "    // Screen shape: DM_SCREEN_ASPECT"
    if start in s:
        a=s.index(start); b=s.index(end,a)
        s=s[:a]+s[b:]
    put(LOADER,s)
    # Frame generation modes can still set the real official target and hold
    # switches; remove old measured-duration/payback controls no longer read.
    s = get(MODE)
    s = s.replace('{"DM_FPS_PAYBACK", "off"}, {"DM_FRAME_DELTA", "0"}, ', '')
    put(MODE,s)
    # The Windows packer builds the Info.plist independently of project.yml.
    s=get(APP)
    anchor="        'GCSupportedGameControllers':"
    if s.count(anchor)!=1: raise RuntimeError("Info.plist anchor changed")
    s=s.replace(anchor,"        'NSBluetoothAlwaysUsageDescription': 'Plays Nintendo Switch 2 controllers over Bluetooth while you hold Sync on one.',\n        'NSMicrophoneUsageDescription': 'Lets the game hear your microphone when enabled.',\n"+anchor)
    put(APP,s)
    return {"official_profile_keys":len(data_rows(official)),
            "retained_profile_keys": sorted(UNIQUE),
            "official_shared_settings": len(known),
            "unique_launcher_rows":len(unique),
            "deferred_controls":sorted(DEFER),
            "memory_policy":"official 8 GiB alias region and map limit; device regression required"}

def check(cwd, dest):
    program = r"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0,'dm/games')
import game, settings
tid='0400486024DEC000'
g=game.load(tid)
assert g.int('mem_alias') == 0x200000000
assert g.get('mem_map_limit') == 'on'
assert g.get('mod_input_hold') == '660'
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    (root/'main.fixups.tsv').write_text('# FRAME_STEP_120\t1\n# DYNAMIC_RESOLUTION\t1\n# RENDER_SCALE\t1\n# SCREEN_ASPECT\t1\n')
    os.environ.update(SETTINGS_PLATFORM='ios', GFXAPI='nvn')
    rows=settings.build(tid,root,root/'absent.nacp')['settings']
    by={r['env']:r for r in rows}
    assert len(rows)==len(by)
    assert '40' in [x[0] for x in by['DM_FPS_TARGET']['options']]
    assert by['DM_RENDER_SCALE']['default']=='1.0'
    assert by['DM_SW2']['default']=='0'
    assert 'DM_FRAMEGEN' in by and 'DM_MIC' in by
    assert 'DM_WIDE_VIEW' not in by and 'DM_WIDE_HUD' not in by  # no HOOKLINK_WIDE capability in this fixture
    assert by['DM_PRESET']['sets']
print('Official-first launcher and profile checks passed')
"""
    r=subprocess.run([sys.executable,"-c",program],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (dest/"profile-settings-tests.txt").write_text(r.stdout)
    print(r.stdout,flush=True)
    r.check_returncode()
