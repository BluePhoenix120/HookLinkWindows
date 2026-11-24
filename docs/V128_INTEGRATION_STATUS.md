# Alpha V1.2.8 integration checklist (in progress)

Target snapshots, verified November 24, 2026:

- HookLink desktop X3 (4.0): `b5c41acf469edb99abc5156f1f6f18397261f54a`.
- HookLink's pinned X3 engine: `ee3ce6a02bc737d38795f0a96cce494cee7a799c`.
- Official NXnative: `5dfc86ae80c53a62262c3b3c66eab043f1fc574a`.
- Prior tested-release source: V1.2.7 `57c24fb38b840bda7e916c52a5d63cbd02ea9de9`.

The read-only [integration audit](https://github.com/BluePhoenix120/HookLinkWindows/actions/runs/45512434282) compares complete Git histories rather than a capped GitHub compare file list. It found 224 official commits (671 changed paths), 460 HookLink engine commits (1,070 changed paths, overlapping official history), 22 official/X3 conflicting paths and nine additional Windows-delta conflicting paths. The provisional merge preference used to reveal the second set of conflicts is **not** an approved merge.

Preparation on main:
- The Windows host-source loader now derives the ordered SRC list from the actual Makefile, accepts the changed audio source list, retains existing Mac-only source filtering, and rejects unknown syntax.
- The Windows region-check shim accepts the new upstream optional `mac_only` parameter. It still does not pretend to run the Mac host on Windows.
- New regression tests cover both source-list formats and fail-closed behavior.

Remaining release gates:
- Resolve overlapping renderer/MetalFX, texture and memory lifetime, archive, Ocarina camera, mic/audio, launcher and rewriter hunks individually. Preserve V1.2.5–V1.2.7 compatibility repairs. Do not override an entire upstream file merely because it previously contained Windows changes.
- Integrate the six HookLink desktop commits, preserving this repository's Windows documentation and GUI. Update VERSION, both engine pins, manifest and exact translator bootstrap identities together. Retain the upstream app resource license and verify background-asset packaging.
- Port the relevant X3 SwiftUI launcher features to the Windows-built Objective-C UIKit launcher (engine/win/ios/Launcher.m), which does not compile Swift. Review updated iOS bridge symbols and the on-phone RomFS mod size-table packaging. The existing Windows GUI already specifies `--gpu none`.
- Reconcile the Windows shader compiler lock against the new translator chain. Preserve old game data and archives; do not claim incompatible shader archives can be reused.
- Run source audit, unit tests, Windows GUI packaging and the fullest available native build checks before changing release metadata. A real game IPA/iPhone test remains dependent on the user's own SDK, compiler, device and game input.

No separate branch is used. V1.2.7 remains the released version until a complete, reviewed V1.2.8 source integration is ready.
