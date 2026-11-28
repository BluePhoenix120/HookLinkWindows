"""Preserve official PSO seeds and import only distinct, valid local additions."""
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys

MANIFEST = "dm/games/0400486024DEC000/pso_manifest.tsv"


def reconcile(cwd, dest, base, target, windows, read):
    # Reuse the upstream parser, including its normalization of render-state
    # keys; raw hex strings alone are not sufficient for deduplication.
    native = dest / "prewarm_skey"
    subprocess.run(["clang", "-std=c11", "-I", "dm/gfx/nvn", "-I",
                    "dm/gfx/nvn/include", "dm/tools/prewarm_skey.c", "-o", str(native)],
                   cwd=cwd, check=True)
    sys.path.insert(0, str(cwd/"scripts"))
    import merge_prewarm_seeds as seeds
    official = read(target, MANIFEST)
    prior = read(windows, MANIFEST)
    old_base = read(base, MANIFEST)
    def rows(s):
        return list(dict.fromkeys(line for line in s.splitlines()
                                  if seeds.ROW.fullmatch(line)))
    upstream = rows(official)
    old = set(rows(old_base))
    upstream_raw = set(upstream)
    additions = [r for r in rows(prior) if r not in old and r not in upstream_raw]
    candidates = [r for r in additions if not r.startswith("S\t")]
    parsed = seeds.parse_pipelines(native, upstream + candidates)
    seen = {seeds.row_key(r, parsed) for r in upstream}
    kept, rejected = [], []
    counts = Counter()
    counts["obsolete_standalone_rows"] = len([r for r in rows(prior) if r.startswith("S\t")])
    for row in candidates:
        key = seeds.row_key(row, parsed)
        if not key:
            rejected.append(row); counts["invalid_pipeline"] += 1
        elif key in seen:
            counts["duplicate"] += 1
        else:
            seen.add(key); kept.append(row); counts["added_" + row[0]] += 1
    # Do not reintroduce rows removed by official upstream, including S.
    if any(line.startswith("S\t") for line in official.splitlines()):
        raise RuntimeError("Pinned official manifest unexpectedly contains obsolete S rows")
    content = official
    if kept:
        if not content.endswith("\n"): content += "\n"
        content += "# Unique HookLink observations retained after official-first deduplication.\n"
        content += "\n".join(kept) + "\n"
    (cwd/MANIFEST).write_text(content, encoding="utf-8")
    assert content.startswith(official)
    assert not any(r.startswith("S\t") for r in content.splitlines())
    (dest/"pso-retained-local.tsv").write_text("".join(r+"\n" for r in kept))
    (dest/"pso-rejected-local.tsv").write_text("".join(r+"\n" for r in rejected))
    native.unlink()
    result = dict(counts, official_rows=len(upstream), distinct_local_candidates=len(candidates),
                  retained_local=len(kept), final_rows=len(rows(content)),
                  local_shader_stage_validation="deferred until workspace shader map is generated")
    print("PSO reconciliation: " + json.dumps(result), flush=True)
    return result


def inventory(cwd, dest, target):
    # Expose the actual surviving custom hunks, not a second blanket merge.
    # Keep the large graphics source out of the log; list each hunk heading.
    paths = ["dm/gfx/nvn", "dm/gfx/msl", "dm/host", "dm/ios/Sources"]
    args = ["git", "diff", "--cached", "--no-ext-diff", "--unified=3", target, "--", *paths]
    p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, check=True)
    (dest/"remaining-native-custom.patch").write_bytes(p.stdout)
    headings = [line for line in p.stdout.decode("utf-8", errors="replace").splitlines()
                if line.startswith(("diff --git ", "@@ "))]
    (dest/"remaining-native-hunks.txt").write_text("\n".join(headings)+"\n")
    print("Remaining native custom hunk inventory:", flush=True)
    print("\n".join(headings), flush=True)
