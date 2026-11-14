# Toolchain requirements and detection contract

The GUI's **Check prerequisites** button runs `win/doctor.py --json` from the complete HookLinkWindows checkout using the same external Python executable used by the build. The structured results are displayed as `OK`, `MISSING` (required), or `OPTIONAL`, together with the doctor's installation/repair instructions. The GUI additionally treats detected LLVM clang versions below 20 as insufficient. It does not change PATH, download tools, create folders, download SDKs, or compile the game.

The upstream doctor checks: Windows/host OS; Python 3.10+; lz4.block, capstone, fontTools, PIL; Python zstd support; .NET SDK 10; `dmsh_xlate.dll`; LLVM clang and ld64.lld; iPhoneOS SDK 26+; Apple Metal compiler + metallib for iPhoneOS and macOS shader passes; SPIRV-Cross; zstd executable; a usable standard font; optional glslangValidator. The upstream Windows port also uses imported Apple SDK files, not Xcode IDE on Windows.

If the repository is incomplete, the GUI refuses to run the doctor and directs users to the full checkout. If `doctor.py --json` cannot run or cannot return valid JSON, the GUI **reports that it could not verify** requirements; it does not falsely display a pass. Standard Python scripts can also run `python win/hooklink_prereqs.py` from the repo root for a textual read-only report.

The checker cannot automatically verify the legality of supplied inputs or Apple licensing, external GitHub authenticity, code signing eligibility, sideloading entitlements, device compatibility, free storage safety, or successful compilation. See `GETTING_STARTED.md` for all first-install steps, official downloads, and troubleshooting.
