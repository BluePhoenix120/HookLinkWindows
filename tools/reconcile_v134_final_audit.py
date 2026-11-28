"""Final source-integrity audit; distinguish proven contracts from device gates."""
import json
import re
import subprocess
import sys

def run(cwd, *args):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()

def check(cwd, target, read, dest):
    def get(p): return (cwd/p).read_text(encoding="utf-8")
    chain=run(cwd,sys.executable,"dm/gfx/tools/dmsh_chain.py")
    header=get("dm/gfx/nvn/dmsh_chain.h")
    assert re.search(r'#define DMSH_CHAIN "([0-9a-f]{12})"',header).group(1)==chain
    source=run(cwd,sys.executable,"dm/gfx/tools/dmsh_chain.py","--xlate-source-sha")
    lock=dict(l.split("\t",1) for l in get("dm/gfx/tools/dmsh_chain.lock").splitlines() if "\t" in l and not l.startswith("#"))
    assert len(source)==16 and re.fullmatch("[0-9a-f]{16}",source)
    assert lock.get("metal_iphoneos") and lock.get("spirv-cross")
    assert lock.get("xlate_source") == source, 'Candidate source lock does not match the exported source'
    assert all(lock.get(k) == 'unmeasured' for k in ('dmsh_xlate','spirv-cross','metal_iphoneos','metal_macosx'))
    # The committed historical lock is not a measurement of the newly
    # rebuilt Windows binary or the user's installed Metal toolchain.
    # Report stale inputs explicitly rather than forging a matching lock.
    renderer=get("dm/gfx/nvn/nvn_mtl.m")
    assert renderer.count("static _Atomic int g_present_discard;")==1
    assert renderer.index("static _Atomic int g_present_discard;") < renderer.index("nvn_fg_debt_allowed(")
    assert renderer.count("atomic_fetch_sub(&g_link_presenting, 1);")==2
    assert renderer.count("atomic_fetch_sub(&g_link_presenting, 1);\n")==2
    for p in ("dm/host/hle_audio.c","dm/host/audio_input.c","dm/host/hle_audren.c","dm/gfx/nvn/nvn_fstep.h"):
        assert get(p)==read(target,p), p
    paths=run(cwd,"git","diff","--cached","--name-status",target).splitlines()
    native=[p for p in paths if any(x in p for x in ("dm/gfx/nvn/","dm/host/","dm/ios/Sources/"))]
    assert not run(cwd,"git","ls-files","-u")
    audit={"source_integrity":"passed","shader_header_matches_provisional_lock":True,
           "provisional_shader_chain":chain,"canonical_source_fingerprint":source,
           "recorded_source_fingerprint":lock.get("xlate_source"),
           "shader_lock_matches_source":source==lock.get("xlate_source"),
           "installed_tools_measured":False,
           "native_custom_paths":len(native),
           "official_audio_and_timing_core":"exact",
           "release_ready":False,
           "release_blockers":["Windows toolchain fingerprint refresh and actual shader build",
              "Game-specific PSO stage validation", "Physical iPhone runtime regression",
              "Remaining native custom changes require runtime verification"]}
    (dest/"final-integration-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    print("Final source audit: "+json.dumps(audit),flush=True)
    return audit
