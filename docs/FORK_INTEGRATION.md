# Importing the Windows port into the HookLink fork

**Repository:** https://github.com/BluePhoenix120/HookLinkWindows
**Parent project:** https://github.com/dsi-hub/HookLink
**Windows engine basis:** https://github.com/dsi-hub/nxnative (branch `hooklink`) and source-only Windows compatibility work.

This is a **staging procedure, not a release approval**. The verified iPhone build exists separately on the developer's Windows machine. Do not publish any locally generated IPA, Nintendo game data, Apple SDK binaries or machine-specific configuration.

## Proposed directory structure

```text
HookLinkWindows/                    # Genuine fork of dsi-hub/HookLink
  .git/                             # Original HookLink repository history
  Sources/HookLink/                 # Existing upstream Mac app source, retained
  Resources/                        # Existing upstream resources, retained
  engine/                           # Imported, modified nxnative Windows source
    dm/
    scripts/
    win/build_ipa_windows.py
    win/doctor.py
  win/hooklink_gui.pyw               # Windows UI and helpers
  config/iphone-oot.env              # Working runtime compatibility preset
  docs/GETTING_STARTED.md
  HookLinkWindows.exe                # Optional GUI launcher (not game-specific)
```

v0.8.0 of the GUI supports either this layout or the earlier `dm/` + `win/` engine-at-root developer checkout. The GUI's prerequisite checker expects the compiler under `engine/` in a HookLink fork and invokes the engine's own doctor.

## 1. Clone and verify the fork — no commit or push

Run this **single line** in PowerShell on the developer's Windows machine. It refuses to overwrite an existing staging directory.

```powershell
$p='C:\HookLinkWindows-Public'; if(Test-Path -LiteralPath $p){throw "Directory already exists: $p"}; git clone 'https://github.com/BluePhoenix120/HookLinkWindows.git' $p; if($LASTEXITCODE -ne 0){throw 'Clone failed'}; git -C $p remote add upstream 'https://github.com/dsi-hub/HookLink.git'; git -C $p switch -c windows-port; if($LASTEXITCODE -ne 0){throw 'Could not create windows-port branch'}; git -C $p remote -v; git -C $p status --short
```

Confirm the remote is the real fork (not an unrelated newly created repository) before proceeding. `git log -1 --oneline`, `git remote -v`, and the GitHub page's “forked from dsi-hub/HookLink” label are useful crosschecks.

## 2. Audit local Windows engine **before** importing it

The original tested engine is at `C:\HookLinkWindows`, on local branch `windows-port`. Check it **without changing anything**:

```powershell
git -C 'C:\HookLinkWindows' branch --show-current; git -C 'C:\HookLinkWindows' status --short; git -C 'C:\HookLinkWindows' ls-files | Select-String -Pattern '(?i)(\.nup$|\.ipa$|romfs\.img$|\.metallib$|\.p12$|\.xip$|[\\/]sdk[\\/]out[\\/]|toolchain\.json$|prod\.keys$|title\.keys$|[\\/]dmsh_xlate_bin[\\/])'
```

Inspect ALL changes and untracked files. Verify the working Windows source changes are actually committed to its `windows-port` branch **before** an engine import; `git subtree` imports commits, **not** uncommitted working-tree changes. Do not commit generated shader packages, rewritten game binaries, game data, local compiler outputs, SDKs, signing secrets, or other proprietary files. If uncertain, stop and perform a manual content audit first.

## 3. Import the audited engine source as a subtree (later)

Only after step 2 passes, and the local Windows engine is a clean, audited branch, an integration approach is:

```powershell
git -C 'C:\HookLinkWindows-Public' subtree add --prefix=engine 'C:\HookLinkWindows' windows-port --squash
```

**This command immediately creates a local Git commit.** It should not be run until the branch is audited. `--squash` retains a snapshot, not the entire nxnative commit history; keep upstream license files and explicit parent-credit documentation. The public fork must continue to identify its separate nxnative origins. For a full-history import, evaluate a non-squashed subtree or a separately maintained engine fork/submodule instead.

## 4. Integrate the GUI overlay, test, and review

Extract the **v0.8.0** source overlay into the `C:\HookLinkWindows-Public` root after the engine has been imported; do not overwrite upstream `README.md`, `LICENSE` or `NOTICE.md` without manually reviewing edits. Run `python -m unittest discover -s tests -v`, then `python tools/release_audit.py .`. Confirm the GUI's **Check prerequisites** reports the engine under `engine/` and finds the external toolchain when installed.

Before any `git add`, run `git status --short`. After staging explicit source files, run `git diff --cached --name-only` and `git diff --cached --stat`. Manually inspect all staged content and verify `.gitignore` exclusions. Neither the audit script nor a clean status alone establishes copyright compliance.

**Do not run `git push` yet.** The app-only exporter, actual nested-layout Windows build, third-party notices, and GitHub Actions EXE all need final validation.
