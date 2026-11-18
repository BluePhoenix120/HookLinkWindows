# HookLinkWindows — Windows first-time setup (release candidate)

This guide covers **building your own local iOS application from your own Ocarina of Time remake `.nup`**. HookLinkWindows is an experimental Windows port. It does **not** include the game, a prebuilt game-specific IPA, signing credentials, Apple's SDK, or Apple's proprietary compiler tools. The source-only GitHub release must include **the entire tested HookLinkWindows engine**; a GUI add-on ZIP alone cannot compile an IPA.

> **Status:** The original port and one iPhone build were tested by the project's developer. This GUI release candidate has **not** passed a clean Windows machine build or complete end-to-end device installation. Some steps depend on third-party tools and terms that users must review.

### Alpha 1.1.1: iPhone black-screen diagnostics

A black game picture with responsive controls is **not automatically a sideloading failure**. It can indicate a rendering/presentation problem, missing or mismatched shader libraries, or another on-device issue. Do not delete the existing Windows build cache to diagnose this. **A game log is needed before claiming a root cause.**

The Windows-built **iPhone launcher** now offers **Export Game Logs** below Play. After a black-screen attempt, fully close the game, reopen it to the launcher, and choose **Export Game Logs → Save to Files** or share manually. This exports **HookLink-last-game-session.txt** (the previous run, originally `Documents/log.prev.txt`) and **HookLink-this-launch.txt** (current run, originally `Documents/log.txt`). iOS file sharing is also enabled, so the same originals can be copied from the application's Documents folder using Files or Apple Devices. The launcher does not upload logs automatically; review them before sharing because device paths and other diagnostics may be present.

In the Windows builder choose **iPhone log…**, select the downloaded `log.prev.txt` / `HookLink-last-game-session.txt`, and review the error excerpts and last log lines in **Build output and diagnostics**. This is **offline, read-only log inspection**, not a conclusive renderer diagnosis or an automatic repair.

For **app-only IPA** installs, confirm that the *installed app's* Documents folder contains `RomFS.img`, the exact matching `b-<shader-chain>.img` archive, and `env.txt`. The tested Ocarina settings in the phone's effective `env.txt` are `DM_MSL_DIR=.`, `DM_NVN_ENC_THREAD=0`, `DM_PSO_MTL4=0`, and `DM_NVN_BARRIER=full`. The local Windows configuration file alone does not update a previously installed app. Avoid changing render switches speculatively until the iPhone logs show what failed.

### Alpha 1.1.0: X2-compatible graphics setup

**Alpha 1.1.0 fixes an Alpha 1.0.9 regression** where `Check prerequisites` or `Toolchain setup… → Retry graphics setup` could report `Expected HookLink 2.0 source tree` before attempting to build the shader translator. The previous bootstrap hardcoded both HookLink `VERSION=2.0` and the X1 NXNative pin. The bootstrap now checks consistent **HookLink 3.0 + NXNative X2 `7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf`** metadata and validates the accompanying 25-file X2 provenance manifest. The earlier 2.0/pinned-engine pair is also recognized for older source checkouts; unknown or inconsistent engine pins remain rejected. This check runs before the external toolchain build and does not reset, download or rewrite the engine.

**Test on Windows:** Use the complete Alpha 1.1.0 ZIP rather than only replacing the executable. In the same extracted tree, choose **Check prerequisites** to let graphics support build automatically, or **Toolchain setup… → Retry graphics setup** if earlier checks failed. The application must still have the required .NET, Metal, SPIRV-Cross and SDK components for their respective stages. The new validation is regression-tested in CI; a complete IPA build on the user's machine remains to be validated.

### NXNative upstream version shown in Alpha 1.0.9

The main GUI shows **NXNative upstream base (pinned)** and its full 40-character commit SHA. The **View commit** button now constructs the link using **both** `nxnative_repo` and `nxnative_commit` from the bundled `ENGINE_PIN.json`, rather than assuming the original `seedds/nxnative` repository. The currently pinned repo is [dsi-hub/nxnative](https://github.com/dsi-hub/nxnative); this is the source of the pinned commit. The link works offline until the user chooses to open it, and the displayed value remains tied to the release's bundled metadata. A missing or malformed repository link disables the button rather than opening an unrelated website. This is the **upstream base**, not the latest upstream branch commit, and the Windows-modified `engine/` tree may differ from that base.

### Alpha 1.0.9: upstream HookLink X2 metadata and Windows shader paths

Alpha 1.0.9 includes the latest upstream [HookLink X2 (3.0)](https://github.com/dsi-hub/HookLink/commit/2295235c3153b087746027a22ac64c7261a274fa) **changelog and VERSION metadata** and records its commit in the fork's Git history. The upstream commit contains *no engine source files*: its release notes refer to a newer NXNative `hooklink` engine commit, `7ba845ab8`. **HookLinkWindows now bundles the X2 NXNative engine revision `7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf` plus Windows-specific changes.** All 25 changed upstream files were imported from the pinned base after checking their original blob hashes, and the exact target hashes were verified. The Windows-specific UIKit launcher and build toolchain remain separate from the upstream SwiftUI launcher. Windows end-to-end IPA and device tests are still required before treating every X2 feature or fix as verified.

Alpha 1.0.9 also protects **iOS host Metal shader generation** from Windows installation paths containing spaces. When needed, the builder copies only the small host Metal source folder into a whitespace-free staging directory, generates its metallibs and header there, and publishes a successful header back to the normal checkout path. This leaves the existing game shaders and build cache untouched. The workaround was reproduced on the affected Windows installation by compiling its 16 host Metal shader files from a directory with no spaces; full IPA completion still needs to be verified.

## 1. Obtain the complete source checkout

Use the project's GitHub **Code → Download ZIP**, extract it to any writable folder (for example `D:\Projects\HookLinkWindows`), or clone the future published repository with Git. No special installation directory or administrator-level path is required. **Keep the EXE in the checkout root beside the `win`, `engine`, `config`, `Sources`, and `docs` directories. The Windows engine lives under `engine/`; a GUI-only ZIP cannot compile.** Do not run the GUI from a separate archive containing only the GUI add-on.

Double-click `HookLinkWindows.exe`. For the compact native launcher, Python must be installed; the separate PyInstaller EXE distributed by a successful Windows GitHub Actions build can open the GUI without Python, but compiling a game still requires Python and the toolchain. If Windows SmartScreen warns about an unsigned new application, verify the release's source and download origin before deciding whether to run it.

The single **Check prerequisites** action first checks the repository layout, then checks compilers and SDKs. Open **Toolchain setup…** for the Alpha 1.0.4 dependency manager, which displays each actual installed/missing/optional status with official tool download/info links and a **Check again** button. The **Setup guide** remains available from the GUI.

## 2. Windows build prerequisites

Most tools must be installed separately. After each installation, restart the GUI so updated environment variables/PATH are visible. **Use Check prerequisites to see exact detected paths, versions, and missing items.** The port's `engine/win/doctor.py --json` (or `win/doctor.py` for a legacy engine-root checkout) is the source of truth for this checklist.

| Requirement | Minimum / purpose | Where to obtain or how to prepare |
|---|---|---|
| Windows 10/11 x64 | Build host; Windows 11 used for successful local testing | Existing Windows PC |
| Python **3.10+**, recommended 3.12–3.13 | Build scripts and Python modules; Tkinter for source GUI | https://www.python.org/downloads/windows/ ; install Python and add it to PATH |
| Python packages `lz4`, `capstone`, `fonttools`, `pillow` | Extracting assets, parsing modules, graphics and fonts | `python -m pip install lz4 capstone fonttools pillow` |
| Python zstd support | `compression.zstd` in supporting Python versions or `backports.zstd` | On Python before 3.14: `python -m pip install backports.zstd` |
| **.NET SDK 10 x64** | Switch/NUP extraction and shader translator | https://dotnet.microsoft.com/en-us/download/dotnet/10.0 |
| **LLVM/Clang 20+ for Windows**, including `ld64.lld.exe` | Cross-compile and link ARM64 iOS host | https://github.com/llvm/llvm-project/releases |
| **Apple Metal Developer Tools for Windows** | `metal.exe` and `metallib.exe` for shader compilation | https://developer.apple.com/metal/tools/ (requires Apple developer access; comply with terms) |
| **iPhoneOS SDK 26 or later** | Apple iOS framework headers and link stubs | Obtained separately through Apple's Xcode distribution or an authorized SDK source; see SDK section below |
| **SPIRV-Cross** executable | Shader translation | https://github.com/KhronosGroup/SPIRV-Cross or https://vulkan.lunarg.com/sdk/home |
| **zstd** executable | Compression/decompression in toolchain | https://github.com/facebook/zstd/releases |
| **Shader translator `dmsh_xlate.dll`** | Translates shaders via .NET | Build locally from repository source; see section 4 |
| Unicode-compatible `.ttf` font | Built-in font stand-in; Windows defaults are usually sufficient | Optional; `STD_FONT` or `win/toolchain.json` |
| `glslangValidator` | Additional shader paths; not required for this OOT NUP workflow according to upstream doctor | Optional (Vulkan SDK) |
| Git | Clone and contribute to source repository | Optional if downloaded as ZIP; https://git-scm.com/downloads/win |
| iPhone, Apple ID, compatible signing/sideloading tool | Install locally generated IPA; appropriate entitlements and game data transfer | For example https://altstore.io/ ; these are **not** build-compiler prerequisites |

The prerequisite checker tests what is present and compatible enough to attempt a build; it does **not** install anything, verify Apple license rights, confirm user game ownership, sign an IPA, or promise device compatibility.

### Install Python packages without a terminal (Alpha 1.0.4)

Open **Toolchain setup…** and click **Check again** to refresh the dependency list. When required Python modules are missing, **Install missing Python packages** installs only the missing packages from the explicit project allowlist after the user confirms the package names and the change to the active Python environment. No command-line instructions or JSON edits are necessary. Optional Pillow is not automatically installed. The operation uses public PyPI and needs an internet connection. A failed pip operation is reported in the existing GUI diagnostics; no third-party executables or Apple SDKs are downloaded silently.

After manually installing an external Windows tool through its official download page, reopen or restart HookLinkWindows if needed so PATH changes take effect and click **Check again**. A green dependency result is based on the actual doctor check, not simply on the presence of an installation directory.

## 3. Apple SDK and Metal tools — important distinction

**Xcode.app is a macOS application, not a Windows installer.** On Windows this experimental project needs a locally available **iPhoneOS SDK 26+** folder and separate **Metal Developer Tools for Windows**. Apple's Xcode and Apple SDKs Agreement restricts SDK use, including on non-Apple-branded computers. The app does not grant rights to use Apple files, and users are responsible for confirming their usage complies with Apple's terms.

The only supported source for the Xcode archive link is Apple's official Developer Downloads page: https://developer.apple.com/download/all/ . Users obtain the Xcode `.xip` archive themselves. **Alpha 1.0.6 adds a direct Download .xip button next to the existing SDK importer:**

1. In **Toolchain setup…**, choose **Download .xip** to open Apple's direct [Xcode 27.2 archive](https://download.developer.apple.com/Developer_Tools/Xcode_27.2/Xcode_27.2.xip) in the default browser. Apple Developer sign-in or agreement acceptance may be required. If the direct download is unavailable, use **Official Apple downloads** to locate the archive.
2. After obtaining the archive, choose **Import SDK from Xcode .xip…**, select the downloaded file, review the authorization/licensing warning, and explicitly approve import only if your use is permitted.
3. The app runs its bundled Windows extractor `engine/win/sdk/extract_xip.py` in a hidden background operation. The GUI streams the extractor's progress and errors; it does not install Xcode, download anything, or bundle Apple files.
4. The importer extracts to a new, private directory under `engine/win/sdk/out/`, validates that exactly one complete iPhoneOS 26+ SDK was produced, and registers that directory automatically without overwriting an existing SDK or unrelated toolchain settings. It then reruns **Check prerequisites**.
5. If the import fails, it discards its temporary extraction and preserves the previously configured SDK. The original `.xip` archive is never changed.

Extraction may require considerable temporary disk space and take significant time because the Xcode archive itself is large and the upstream extractor scans it. Cancellation by forcibly terminating a process can leave a temporary folder to clean up. A real Xcode 27.x import on a clean Windows installation still requires end-to-end testing; the offline tests do **not** exercise Apple's proprietary archive bytes.

Alternatively, select an existing SDK directory using **Browse… → Save**, subject to the same licensing restrictions. Never commit SDKs, Xcode files, or private game assets to GitHub.

## 4. Toolchain setup in Alpha 1.0.9

**No command-line compilation or JSON editing is needed for the shader translator.** Click **Check prerequisites** in the GUI. When the `dmsh_xlate.dll` translator is absent and the required .NET 10 SDK, SPIRV-Cross and Apple Metal compilers are already available, HookLinkWindows automatically prepares graphics support from the bundled source, verifies it, and backs up the local shader-chain metadata before synchronization. The progress and any errors appear in **Build output and diagnostics**. This does not delete the game or shader caches, although a new shader-chain identity can make previously built shaders incompatible.

If automatic graphics setup fails, open **Toolchain setup… → Retry graphics setup**. For an existing translator, automatic setup never overwrites it: any manual retry that may regenerate a shader chain requires confirmation.

The **iPhoneOS 26+ SDK is a separate prerequisite**; it is *not* needed for preparing the translator. It is not bundled with HookLinkWindows. Obtain it from an authorized Apple Xcode distribution and comply with the applicable Apple license. The GUI provides **Toolchain setup… → Browse… → Save** for an existing SDK, or **Import SDK from Xcode .xip…** to import a locally selected archive without using command-line tools. **Download / info** for this item opens Apple's information/download portal, not a Windows SDK installer; Apple's licensing rules remain applicable. The user-controlled Xcode archive importer handles extraction and registration locally; the application does not automatically obtain Xcode or Apple SDK files.

The advanced developer path `engine/win/toolchain.json` also supports nonstandard paths (`ios_sdk`, `llvm`, `metal_tools`, `spirv_cross_dir`, `zstd_dir`), but everyday users should not need to edit this file for SDK selection or graphics setup. Python 3 and the separately installed compiler/SDK tools remain required for actual IPA compilation.

## 5. Run checks and choose the game NUP

1. Open `HookLinkWindows.exe` from the **complete** checkout root.
2. Click **Check prerequisites**. If the repository is incomplete, follow **Why** and **How to fix** beside `Repository layout: incomplete`, then retry.
3. Once the layout is complete, the same action checks compilers/SDKs and automatically prepares missing graphics support if its dependencies are available. Select an existing iPhoneOS SDK through **Toolchain setup…** if needed. Other required third-party compilers must still be installed independently; rerun until every required item shows `OK`. Optional entries are labeled as optional.
4. Choose your own Ocarina of Time remake **`.nup`** under **Game .nup file**. No `prod.keys` field is used in this NUP-specific GUI.
5. Leave the default **App-only (recommended)** packaging selected for a smaller sideloadable IPA plus separately transferred data files. Change build directory and output IPA if you want; neither must be in your Windows home directory.
6. The included `config/iphone-oot.env` uses `DM_NVN_ENC_THREAD=0`, `DM_PSO_MTL4=0`, `DM_NVN_BARRIER=full`, and `DM_MSL_DIR=.`. The user may choose another runtime file; these settings were verified on one device, not every iPhone.
7. Leave **Allow damaged assets** and **Allow alternate Metal version** checked if required by your toolchain. They bypass validation and may mask problems; they are user-editable.
8. Optionally edit **Advanced settings → Bundle ID** (default `PhoenixNetwork.HookLinkWindows`). A different ID creates a separate iOS application identity with separate Documents/save data.
9. Click **Preview command** and review its output. Click **Build IPA**. The GUI validates the shader-chain lock and host header against installed tools before compilation. If the chain differs, it backs up and synchronizes only these local source files, verifies them again, and blocks the build on any failure. This preflight does not compile game shaders; the subsequent build may compile them if the matching library is absent. See `docs/SHADER_CHAIN.md`. Do not interrupt game shader compilation unnecessarily; it can be lengthy and consume substantial disk space (tens of gigabytes for the tested game).

### Output formats

- **App-only:** The GUI temporarily builds a full IPA, then exports a smaller IPA and a transfer folder with the matching `RomFS.img`, `b-<shader-chain>.img`, and `env.txt`. Packaging can consume considerable storage before the temporary IPA is deleted on success. The exported IPA still contains a locally built game-specific executable and is **not appropriate for public redistribution**.
- **Full:** The GUI retains one large IPA with the game resources; many sideloading utilities cannot handle a file this large.

**Build error:** Do not erase the build directory while troubleshooting. Logs, shader intermediates, and a failed app-only staging IPA may be needed for recovery. A passing prerequisite check does not guarantee a successful compile.

## 6. Sign, install and transfer to an iPhone

The produced IPA is **unsigned** until signed by a compatible sideloading tool. Use AltStore or another appropriate tool according to its current documentation. Device entitlement configuration is separate from the compiler; this build requests an Increased Memory Limit entitlement in the build settings, but you must **verify the app's final signature and the capability after signing**. Some devices and signing methods do not permit it.

For app-only mode, transfer the locally generated `RomFS.img`, the **matching** `b-<shader-chain>.img`, and `env.txt` into the newly installed app's Documents folder (Apple Devices → Files on Windows, where supported). The matching shader chain matters: do not copy an archive from a different build. Launch and test the game. Maintain backups of saves and data; reinstalling with a different Bundle ID can make existing data inaccessible to the new installation.

## 7. Troubleshooting and contributor validation

- **Incomplete checkout:** The engine source is missing under `engine/`, or the GUI add-on was extracted alone. Obtain the complete project and see `docs/FORK_INTEGRATION.md`.
- **Python missing when double-clicking EXE:** The compact native launcher needs Python installed. The separately packaged PyInstaller GUI EXE does not need Python merely to open, but *still* needs Python for building.
- **Python module/LLVM/.NET/SDK/Metal missing:** Follow the actionable `Check prerequisites` output; verify PATH and optionally local toolchain configuration. Restart the GUI after changing PATH.
- **Black screen or stalls on the tested OOT build:** Confirm `DM_NVN_ENC_THREAD=0` and `DM_NVN_BARRIER=full` in the app's actual device `env.txt`. A local Windows file is not automatically deployed to the phone.
- **Very low FPS during diagnostics:** Ensure temporary frame logging/capture overrides are removed. The working preset does not enable them.
- **IPA fails to install:** Verify signing/entitlements, output integrity, App IDs and device limitations, and keep the matching external game data available.
- **No SDK/compiler bundled:** This is intentional, for licensing and release-size reasons.

For project release preparation read `docs/RELEASE_CHECKLIST.md`, `docs/SHADER_CHAIN.md`, and the upstream port's `engine/win/README.md` when available. The published GitHub source must be audited for third-party licenses and private/generated assets. **The repository is not yet certified as clean-room reproducible.**
