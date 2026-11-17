# HookLinkWindows — source-only public release checklist

This checkout contains the integrated HookLink 2.0 frontend, bundled nxnative engine, and Windows port. Alpha V1.0.0 has passed developer-machine build and regression testing; a fresh Windows installation and complete end-to-end build and sideload remain unverified. Complete the checks below before declaring clean-install support validated.

- [ ] The public repository includes the working, licensed HookLink/nxnative engine and all required `win/` source modifications, not just this small GUI overlay.
- [ ] Preserve upstream copyright and license notices, document the origin of ported components, and review third-party license obligations.
- [ ] Do **not** publish a compiled game-specific IPA, NUP, RomFS, rewritten game binaries, generated shaders, certificates, signing profiles/keys, extracted Apple SDKs, or Apple compilers.
- [ ] Run `python tools/release_audit.py .` before staging or publishing; review findings. It checks filenames only and is not a comprehensive audit.
- [ ] Inspect `git status --short` and `git diff --cached --stat` before committing. Do not use blanket `git add .` without reviewing untracked files.
- [ ] Ensure `.gitignore` excludes local `win/toolchain.json`, SDK extraction, personal logs, work folders, IPA, shader archives, and credentials; do not overwrite upstream `.gitignore` blindly.
- [ ] On a clean Windows account, extract/clone into an arbitrary non-default directory and run **Check prerequisites**; verify that it checks project layout first and compilers/SDKs second.
- [ ] Run **Check prerequisites** and resolve every reported dependency error, including any external SDK path referenced in the local configuration.
- [ ] Build using a separately supplied, authorized `.nup` in **both** packaging modes; verify IPA integrity, automatic shader/RomFS/env transfer-folder preparation, signed app installation and device launch.
- [ ] Test interrupted or failed app-only packaging: no data loss, the original files remain intact, and the staging IPA is kept for recovery.
- [ ] Test app-only transfer folder with source files on a different volume (hard-link fallback/copy), and without a matching shader chain (fail closed).
- [ ] Move the repo and restart the GUI; verify the built-in environment preset rebases to the new repository path and preferences remain intact.
- [ ] Verify no personal paths, logs, or game-specific input files are committed.

- [ ] Windows GUI executable: verify double-click launch of the native Python-dependent launcher on a fresh Windows profile.
- [ ] Run the `Build Windows GUI EXE` GitHub Actions workflow and test the PyInstaller output from a clean, relocated checkout. The standalone GUI must resolve the checkout root and must call a real external Python for compilation.
- [ ] Validate that the executable contains only the GUI runtime and source-derived assets, not game data, Apple SDKs, or local test artifacts.
- [ ] Assess publisher signing and Windows SmartScreen warnings for public releases.

## Limitations

- This release audit inspects **filenames**, not embedded binary contents, code provenance, or licensing.
- The offline relocation tests use mock builder/engine files; they **do not** demonstrate a clean Windows install, successful compilation, or device compatibility.
- An `app-only` IPA can still contain copyrighted game-derived executable code. It is a local packaging feature, not a publishing recommendation.
- The existing Windows port has experimental workarounds (`tree_tar` shim, compiler fingerprint changes, damaged asset bypass, provisional UIKit bridge) requiring independent review.

## v0.7.1 prerequisite integration checks

- [ ] Read `docs/GETTING_STARTED.md`; validate every installer URL and license statement for the public project.
- [ ] On a clean Windows installation, check that **Check prerequisites** detects each missing external requirement with an actionable URL/instruction.
- [ ] Confirm doctor JSON and GUI detection work with the **actual modified HookLinkWindows** tree; mismatched JSON from a customized doctor is a blocking integration issue.
- [ ] Verify the SDK and Metal compiler under applicable Apple licensing and that none are included in release archives or Git objects.
- [ ] Check `python win/hooklink_prereqs.py` and GUI reporting with all required tools installed; confirm `dmsh_xlate.dll` can be rebuilt from source when absent.
- [ ] Test app-only output, AltStore signing, and iPhone Documents transfer on a second machine before claiming public release readiness.

- [ ] See `docs/GITHUB_PUBLICATION.md` and use reviewed `.gitignore` additions before committing or creating public tags.
