"""Windows counterparts of X3 build_ipa.sh's optional launcher resources."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def stage_launcher_resources(engine, app, dmres, control, romfs, is_image, env, log=print):
    engine, app, dmres, control = map(Path, (engine, app, dmres, control))
    if control.is_file():
        shutil.copy2(control, dmres / "control.nacp")
    else:
        log("No control.nacp to package")
    # X3 puts its default picture in the desktop project, not the engine.
    # Respect an explicit override, otherwise use the packaged default if present.
    source = env.get("DM_LAUNCHER_BG")
    background = Path(source) if source else engine.parent / "Resources/presets/launcher_background.jpg"
    if background.is_file():
        shutil.copy2(background, dmres / "launcher_background.jpg")
    elif source:
        log("Launcher background file not found: " + str(background))
    # X3's host reads the uncompressed resource size table at the app root.
    # Earlier engine revisions lack the generator and retain their old behavior.
    generator = engine / "scripts/oot_mods_rstb.py"
    if not is_image or not generator.is_file():
        return
    output = app / "mods_rstb.bin"
    output.unlink(missing_ok=True)
    overlay = env.get("DM_ROMFS_OVERLAY", "")
    run = subprocess.run([sys.executable, str(generator), os.fspath(romfs),
                          str(output), overlay],
                         capture_output=True, text=True, env=dict(env))
    if run.returncode or not output.is_file():
        output.unlink(missing_ok=True)
        log("Mods: no resource size table (" + (run.stderr or run.stdout or "generator did not produce a table").strip()[-500:] + ")")
    else:
        log("Mods: resource size table packaged")
