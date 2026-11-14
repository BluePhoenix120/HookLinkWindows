# Publishing HookLinkWindows — source-only release process

This is a **draft publishing workflow** for the new repository. Do not publish the current GUI ZIP as a complete build system: it contains an executable launcher and GUI overlays, not the entire HookLinkWindows engine. The eventual GitHub repository must contain all verified, licensable source components and the Windows patches required by the functioning local build.

## Before making the repository public

1. Assemble the complete Windows port, including GUI `win/`, engine `engine/win/`, and engine source patches under `engine/dm/` and `engine/scripts/`, the compiled GUI launcher sources, tests, and docs. Preserve upstream Git history, licenses, and copyright notices where appropriate. Review dependencies, licenses, and whether source inclusion is authorized; do not assume every external file is MIT-licensed.
2. Keep **out of Git and out of Releases**: game NUP/NSP/XCI, game-derived executable binaries, RomFS, shaders and metallib archives, generated IPA, user saves, logs with personal paths, Apple SDKs/compiler binaries, signing keys/certificates, and `win/toolchain.json` containing local paths.
3. Add robust ignore rules, such as the example in `docs/GITIGNORE_EXAMPLE.md`; check existing rules before appending. A `.gitignore` prevents new additions, but **does not remove already tracked files or prior Git history**.
4. Inspect the entire Git staging area (`git status --short`, `git diff --cached --stat`, `git diff --cached --name-only`), then run the supplied filename audit (`python tools/release_audit.py .`). Manually inspect binaries and code too: filename scanning cannot prove that files are free of copyrighted content.
5. If a private artifact ever entered a Git commit, do not simply delete it in a later commit. Clean the affected history in a private working copy and audit the results **before any public push**; rotate any exposed secrets.
6. Confirm the main README links to `docs/GETTING_STARTED.md`, `docs/PREREQUISITES.md`, and `docs/RELEASE_CHECKLIST.md`, plus engine license and upstream credits. Provide issue templates and a clear experimental-status notice.
7. Validate cloning/ZIP extraction into an arbitrary folder and opening the project-root GUI EXE. **Check prerequisites** must check both repository layout and external dependencies on a clean account, reporting missing dependencies accurately.
8. Test a full fresh build from an authorized NUP, app-only packaging and shader-chain transfer, IPA signing, iPhone launch, saves, and gameplay. Record tested versions and checksums of the release archive and EXE. The existing working local build alone does not certify this new end-to-end GUI workflow.
9. Run the provided Windows GitHub Actions PyInstaller build from source. The included tiny Windows EXE still requires Python; make that clear in the Release assets. A standalone GUI EXE built by CI doesn't bundle the game toolchain.
10. Start with a private GitHub repository while completing the release audit and smoke tests. Publish only after the required source and dependency checks pass.

## Suggested public releases

- **Source ZIP / Git checkout:** Complete Windows-port source, docs, GUI, tests, runtime preset; no game- or Apple-derived binaries.
- **Windows GUI EXE:** Source-compiled native launcher or a verified CI PyInstaller EXE. State clearly that the build still requires external toolchains.
- **No prebuilt OOT game IPA:** Users build from their own lawful input and transfer their own game data.

## Example readme opening

> HookLinkWindows is an experimental, community-maintained Windows build interface and compatibility port for creating a locally signed iOS app from a user-supplied Ocarina of Time remake `.nup` file. It is not affiliated with Nintendo or Apple. The repository does not include game content, game-specific compiled IPAs, or Apple's development SDK/compiler files. See [Getting Started](docs/GETTING_STARTED.md) for the separate toolchain requirements and [Release Checklist](docs/RELEASE_CHECKLIST.md) for the current validation status.

## References

- Upstream Windows port: https://github.com/zenvyzenshiro/NXNativeWindows
- HookLink: https://github.com/dsi-hub/HookLink
- Apple developer downloads: https://developer.apple.com/download/all/
- Apple Metal tools for Windows: https://developer.apple.com/metal/tools/
- Microsoft .NET SDK 10: https://dotnet.microsoft.com/en-us/download/dotnet/10.0

**Licensing note:** This document is a technical release checklist, not a legal opinion. Review Apple's SDK/software license and each included component's licensing obligations before any public source or executable distribution.


The public GitHub fork is `BluePhoenix120/HookLinkWindows` (parent: `dsi-hub/HookLink`). See `docs/FORK_INTEGRATION.md` for the separate nxnative engine subtree and the audited local staging procedure. Do not push until the source import, licensing, and nested-layout build have been verified.
