# HookLinkWindows full-distribution workflow update

This overlay updates `.github/workflows/windows-gui.yml` and adds this release note. Extract into your **public fork checkout** (`C:\HookLinkWindows-Public`), not into the tested `C:\HookLinkWindows` engine.

The updated GitHub Actions job will run the GUI tests and filename-based release audit, build the standalone GUI executable on a Windows runner, and create one ZIP containing the repository files at `HEAD` plus `HookLinkWindows.exe` at the root. It fails if essential source files are missing from the final ZIP.

The source is included from Git's **committed `HEAD`** via `git archive`: it will not include untracked local files. Your Windows source must therefore be audited and committed before the workflow can package it. **No proprietary Apple SDK or game files should be committed.**

The workflow is not an installer and does not install prerequisites for compiling games. Users still need the separately acquired toolchain. A successful workflow does **not** demonstrate that a full NUP-to-IPA build works on a clean Windows PC, nor does it automatically publish a GitHub Release.

After copying this overlay, run GUI tests and review the YAML. Trigger `workflow_dispatch` manually **after** the validated branch has been committed and pushed, then inspect the resulting artifact before tagging or publishing a release.
