# Build-time mods on Windows

HookLinkWindows can optionally apply compatible ExeFS code patches and RomFS
file replacements when building the IPA. This is not a live code patcher and
does not implement the full HookLink iOS mod-management interface.

## BodiesOfTruth

1. Use the separate [BodiesOfTruth converter](https://github.com/Rudeboy99/BodiesOfTruth-Conversion-Tool-OoTR)
   with the Ocarina of Time update supported by its patch (v131072 at the time
   of integration). Choose **Recomp (Hookshot/Longshot)**, not Emulation.
2. In HookLinkWindows, open **Advanced settings**, select **Mods folder** and
   choose the converter's `Converted` output directory containing both
   `BodiesOfTruth - Custom/romfs` and `LensPatch/exefs`. Use one unified
   converted output rather than combining several competing RESTBL files.
3. Keep your existing build directory and choose **Build IPA**. The code
   rewrite must run again when the code patch changes. Unchanged shader
   inputs can reuse existing shader archives; no clean build is necessary.
4. Install the rebuilt IPA. In app-only mode, copy the matching generated
   transfer folder's `RomFS.img`, shader archive and `env.txt` to the
   application. Do not use the previous unmodified RomFS for this mod.

Clear the Mods folder field and rebuild to disable build-time mods. Back up
your save data before replacing an app or testing modified game resources.

The converter's patch and modified resources are supplied by the user, not
distributed with HookLinkWindows. The Windows integration is experimental, but BodiesOfTruth was confirmed
working by the project maintainer on V1.3.3. Future engine updates still
require device retesting. Mods that replace shader inputs, introduce extra NSO
modules, or overlap other patches/files are not supported by this workflow.
