"""Official shader pipeline with narrowly scoped Windows portability overlays."""
import os
from pathlib import Path
import subprocess
import sys

CACHE = "dm/tools/shader_cache.py"
BUILD = "dm/gfx/tools/dmsh_build.py"
SPLIT = "dm/gfx/tools/shader_split.py"
ROMFS = "dm/tools/romfs.py"
PROFILE = "dm/games/game.py"
DRIVER = "win/build_ipa_windows.py"
APP = "win/build_app.py"
PACK = "scripts/build_ipa_from_nsp.py"
LOCK = "dm/gfx/tools/dmsh_chain.lock"
HEADER = "dm/gfx/nvn/dmsh_chain.h"
PATHS = (CACHE, BUILD, SPLIT, ROMFS, PROFILE, DRIVER, APP, PACK, LOCK, HEADER)


def replace(s, old, new, count=1):
    if s.count(old) != count:
        raise RuntimeError(f"Shader overlay anchor count {s.count(old)} != {count}: {old[:100]}")
    return s.replace(old, new)


def reconcile(cwd, target, windows, read):
    def get(p): return (cwd/p).read_text(encoding="utf-8")
    def put(p, s): (cwd/p).write_text(s, encoding="utf-8")
    # Official v2 compressed cache: keep ONLY the Windows file-lock backend
    # and read/write lock handles from the proven baseline.
    s = read(target, CACHE)
    s = replace(s, "import contextlib, fcntl,", "import contextlib,")
    s = replace(s, "from pathlib import Path\n", "from pathlib import Path\n\ntry:\n    import fcntl\nexcept ImportError:\n    if os.name != 'nt':\n        raise\n    import nxw_flock as fcntl\n")
    s = replace(s, ".lock', 'a')", ".lock', 'a+')", 2)
    put(CACHE, s)
    # Official shader compiler, including all translation and dedup changes.
    # Replay the four Windows-only compatibility edits, not old algorithms.
    s = read(target, BUILD)
    s = replace(s, "import dmsh_geometry,", "from concurrent.futures.process import BrokenProcessPool\nimport dmsh_geometry,")
    s = replace(s, "fd = os.open(path, os.O_RDONLY);", 'fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0));')
    s = replace(s, "    return name, os.pread(fd, e - o, o)\n", "    if hasattr(os, 'pread'):\n        return name, os.pread(fd, e - o, o)\n    with packs_lock:\n        os.lseek(fd, o, os.SEEK_SET)\n        return name, os.read(fd, e - o)\n")
    s = replace(s, "except cf.process.BrokenProcessPool:", "except BrokenProcessPool:")
    put(BUILD, s)
    s = read(target, SPLIT)
    s = replace(s, "os.path.relpath(os.path.join(dp, f), romfs)", "os.path.relpath(os.path.join(dp, f), romfs).replace(os.sep, '/')", 2)
    put(SPLIT, s)
    s = read(target, ROMFS)
    s = replace(s, "parts = p.split('/')", "parts = p.replace(_os.sep, '/').split('/')")
    s = replace(s, "_os.open(image.path, _os.O_RDONLY)", '_os.open(image.path, _os.O_RDONLY | getattr(_os, "O_BINARY", 0))')
    put(ROMFS, s)
    # The new official build generates profile tables in the workspace.
    # A literal colon breaks drive-letter paths on Windows. Preserve the
    # combined profile's independent HookLink keys while fixing lookup.
    s = get(PROFILE)
    s = replace(s, "os.environ.get('DM_GAMES_DIR', '').split(':')", "os.environ.get('DM_GAMES_DIR', '').split(os.pathsep)")
    put(PROFILE, s)
    s = read(target, PACK)
    s = replace(s, "STOPS = (signal.SIGTERM, signal.SIGHUP)", "STOPS = (signal.SIGTERM,) + ((signal.SIGHUP,) if hasattr(signal, 'SIGHUP') else ())")
    put(PACK, s)
    s = get(DRIVER)
    s = replace(s, "def capture_shaders(repo, d, patched, work, env, logs, g, api):", "def capture_shaders(repo, d, patched, work, env, logs, g, api, msl=None, aoc=None):")
    # Mixed NVN/GL capture needs a real NVN library and DLC at runtime;
    # refuse unsupported supplemental capture rather than silently ignoring
    # new parameters or making a misleading empty NVN capture app.
    s = replace(s, "        if api != 'gl': return device_capture", "        if msl is not None or aoc is not None:\n            raise BuildError('supplemental mixed NVN/GL runtime capture requires Windows device-capture integration')\n        if api != 'gl': return device_capture")
    put(DRIVER, s)
    s = get(APP)
    old = """    for f in ('shader_map.tsv', 'pso_manifest.tsv') + (() if gfx in ('vulkan', 'gl') else ('c1_full.tsv',)):
        if capture and not (gd / f).exists(): continue   # a capture IPA has no shader build: the tables it would stamp may not exist yet
        shutil.copy2(gd / f, dmres)"""
    new = """    # Match official packaging: NVN's map and C1 stamp are required for
    # a compiled NVN build, but other APIs and capture IPAs need not have
    # those files. Pipeline seeds are optional for every profile.
    for f in ('shader_map.tsv', 'c1_full.tsv'):
        if (gd / f).is_file(): shutil.copy2(gd / f, dmres)
        elif gfx == 'nvn' and not capture: die(f'missing generated shader table {gd / f}')
    if (gd / 'pso_manifest.tsv').is_file(): shutil.copy2(gd / 'pso_manifest.tsv', dmres)"""
    s = replace(s, old, new)
    put(APP, s)
    # Preserve the Windows toolchain lock as a provisional fingerprint.
    # Actual translator rebuild and lock refresh remain release gates.
    put(LOCK, read(windows, LOCK))
    chain = subprocess.check_output([sys.executable, "dm/gfx/tools/dmsh_chain.py", "--header"], cwd=cwd, text=True).strip()
    if len(chain) != 12 or any(c not in "0123456789abcdef" for c in chain):
        raise RuntimeError("Invalid provisional shader chain")
    return chain


def check(cwd, dest):
    # Verify lookup of a generated profile before the repository's stock
    # profile, including simulated Windows separators on the Linux runner.
    program = """
import os, sys, tempfile, shutil
from pathlib import Path
sys.path.insert(0, 'dm/games')
import game
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    a, b = root/'first', root/'second'
    a.mkdir(); b.mkdir()
    tid = '0400486024DEC000'
    p = b/tid; p.mkdir()
    shutil.copyfile(Path('dm/games')/tid/'game.tsv', p/'game.tsv')
    (p/'shader_map.tsv').write_text('generated')
    os.pathsep = ';'
    os.environ['DM_GAMES_DIR'] = str(a) + ';' + str(b)
    os.environ['DM_GAMES_FIRST'] = '1'
    assert game.extra_dirs() == [a, b]
    assert game.load(tid).table('shader_map.tsv').read_text() == 'generated'
print('Generated profile lookup: PASS')
"""
    tests = [
        [sys.executable, "-c", program],
        [sys.executable, "-c", "import sys; sys.path.insert(0, 'dm/tools'); import shader_cache; assert shader_cache.zstd is not None"],
        [sys.executable, "-m", "unittest", "-v",
         "dm.tools.tests.test_shader_cache.Entries",
         "dm.tools.tests.test_shader_cache.Compression.test_inline_compression_and_incompressible_fallback",
         "dm.tools.tests.test_shader_cache.Compression.test_older_checkout_fails_closed",
         "dm.tools.tests.test_shader_cache.Compression.test_legacy_v1_read_write_generation_copy_and_take",
         "dm.tools.tests.test_shader_cache.Compression.test_corrupt_zstd_frame_recovers_local_and_ignores_readonly",
         "dm.tools.tests.test_shader_cache.Compression.test_missing_codec_and_unknown_codec_preserve_cache",
         "dm.tools.tests.test_shader_lib.SharedPayloads"],
    ]
    with (dest/"shader-pipeline-tests.txt").open("w", encoding="utf-8") as log:
        for cmd in tests:
            p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(p.stdout); log.flush()
            print(p.stdout, flush=True)
            p.check_returncode()
