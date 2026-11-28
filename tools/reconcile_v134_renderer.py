"""Restore official renderer hunks identified by the exact native candidate compile.

The hunk coordinates are in the pinned official source (not mutable candidate
line numbers). Fail on a changed hunk inventory instead of guessing.
"""
import re
import subprocess

METAL = "dm/gfx/nvn/nvn_mtl.m"
NDVE = "dm/gfx/nvn/nvn_ndve.inc"
# The official-side coordinates in validation #6's native hunk inventory.
# Reconcile whole hunks, including paired edits which did not themselves
# emit a compiler error. All unrelated HookLink changes remain in place.
DECISIONS = {
    6983: "official texture allocation, compression and initialization",
    11998: "official pipeline archive file handling, not old clonefile helper",
    12037: "official archive plan (paired clonefile helper caller)",
    15158: "official retired texture pool handling",
    15185: "restore paired official pool-entry checks",
    20470: "official MetalFX dispatch instead of HookLink upscaler-chain dispatch",
    20637: "official texture readback",
    20681: "official buffer-to-texture copy setup",
    20718: "official buffer-to-texture copy and completion",
}

def restore_frame_generation(cwd, target, windows, dest):
    """Restore the independent owed-picture presentation lost in the three-way merge."""
    def source(ref):
        return subprocess.check_output(["git", "show", ref + ":" + METAL], cwd=cwd).decode("utf-8")
    prior, official = source(windows), source(target)
    start = "    // Frame generation: the present whose generated frame is on screen now"
    anchor = "    // Keep a multi-tick frame on screen until its hold ends"
    if prior.count(start) != 1 or prior.count(anchor) != 1 or start in official:
        raise RuntimeError("Unexpected frame-generation source anchors")
    block = prior[prior.index(start):prior.index(anchor)]
    assert "if (g_fg_owed && tick_time >= g_fg_owe_at - tol)" in block
    assert block.count("present_now(&ow.t, 0, ow.frame, tk, ow.crop, ow.ev_val, update.drawable, update.targetPresentationTimestamp, 0)") == 1
    path = cwd/METAL
    s = path.read_text(encoding="utf-8")
    if s.count(anchor) != 1 or start in s:
        raise RuntimeError("Candidate frame-generation anchor changed")
    # Use the official callback's additional coverage guard; do not replace its
    # hold, late-latch, or frame timing implementation.
    guard = "if (!newer && g_dm_present_link && !g_rescue_mode)"
    assert block.count(guard) == 1
    block = block.replace(guard, "if (!newer && g_dm_present_link && !g_rescue_mode && !atomic_load(&g_covered) && !atomic_load(&g_present_suspended))")
    lock = "            pthread_mutex_unlock(&g_pq_mu);"
    assert block.count(lock) == 1
    block = block.replace(lock, "            atomic_fetch_add(&g_link_presenting, 1);\n" + lock)
    reset = "            g_fg_owing = 0;"
    assert block.count(reset) == 1
    block = block.replace(reset, reset + "\n            atomic_fetch_sub(&g_link_presenting, 1);")
    s = s.replace(anchor, block + anchor)
    path.write_text(s, encoding="utf-8")
    (dest/"frame-generation-owed-picture.txt").write_text(block, encoding="utf-8")
    assert s.count("present_now(&ow.t,") == 1
    return {"owed_picture_restored": True, "device_validation_required": True}


def reconcile(cwd, target, dest):
    # Stage the exact candidate before deriving the review patch. Use Git's
    # own reverse apply, with normal context checks, to recover official code.
    subprocess.run(["git", "add", "-A"], cwd=cwd, check=True)
    patch = subprocess.check_output(["git", "diff", "--cached", "--no-ext-diff",
                                      "--unified=3", target, "--", METAL], cwd=cwd)
    chunks = re.split(rb"(?m)(?=^@@ -)", patch)
    header, hunks = chunks[0], chunks[1:]
    selected = {}
    for h in hunks:
        match = re.match(rb"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", h)
        if not match:
            raise RuntimeError("Unrecognized renderer diff hunk")
        line = int(match.group(1))
        if line in DECISIONS:
            if line in selected:
                raise RuntimeError("Duplicate renderer hunk")
            selected[line] = h
    if set(selected) != set(DECISIONS):
        raise RuntimeError(f"Renderer review coordinates changed: found {sorted(selected)}, expected {sorted(DECISIONS)}")
    reverse = header + b"".join(selected.values())
    (dest/"renderer-official-restoration.patch").write_bytes(reverse)
    for line, h in selected.items():
        print(f"Restore official renderer line {line}: {DECISIONS[line]}", flush=True)
        print(h.decode("utf-8"), flush=True)
    subprocess.run(["git", "apply", "--reverse", "--index", "--check", "-"], input=reverse, cwd=cwd, check=True)
    subprocess.run(["git", "apply", "--reverse", "--index", "-"], input=reverse, cwd=cwd, check=True)
    # Keep distinct HookLink kernels (occlusion and lightweight movie
    # processing) and use the official no-argument compute encoder.
    for path in (METAL, NDVE):
        p = cwd/path
        s = p.read_text(encoding="utf-8")
        count = s.count("enc_c_begin(NULL)")
        if count != 1:
            raise RuntimeError(f"{path}: expected one old encoder call, found {count}")
        s = s.replace("enc_c_begin(NULL)", "enc_c_begin()")
        p.write_text(s, encoding="utf-8")
    s = (cwd/METAL).read_text(encoding="utf-8")
    assert "g_up_chain_refused" not in s and "g_up_chain_in" not in s
    assert "pool_skip_retired()" not in s and "g_pool_skipped++" not in s
    assert "clonefile(src.fileSystemRepresentation" not in s
    assert "rt_lossy(d);" not in s
    return {"restored_official_hunks": len(selected),
            "adapted_unique_kernel_calls": 2, "native_validation_required": True}
