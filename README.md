<p align="center"><img src="docs/icon.png" width="112" alt="HookLinkWindows icon"></p>

<h1 align="center">HookLinkWindows</h1>

<p align="center"><strong>Build an iPhone app from your own supported Ocarina of Time `.nup` — using Windows.</strong></p>

<p align="center">
<a href="#download">Download</a> ·
<a href="#project-status">Status</a> ·
<a href="#requirements">Requirements</a> ·
<a href="#quick-start-windows">Quick start</a> ·
<a href="#install-on-iphone">Install on iPhone</a> ·
<a href="#troubleshooting">Troubleshooting</a> ·
<a href="#engine-and-upstream">Engine</a> ·
<a href="#credits">Credits</a>
</p>

> [!IMPORTANT]
> **Alpha software — not a one-click game installer.** HookLinkWindows is an experimental, Windows-hosted build tool for producing an iOS app **locally from game files you already own**. It does not distribute the game, an IPA containing game assets, signing credentials, Apple SDKs, or proprietary compiler binaries. You must provide the required tools and game input yourself. Do not upload or redistribute game dumps, generated IPAs, RomFS images, shader caches, private keys, or saves.

HookLinkWindows combines the [HookLink](https://github.com/dsi-hub/HookLink) , [NXnativeWindows](https://github.com/zenvyzenshiro/NXNativeWindows) and [NXnative](https://github.com/seedds/nxnative) projects to a **Windows-first, GUI-based workflow**. It translates game code and graphics for iOS/Metal rather than using a conventional Switch emulator. It is a **builder for iPhone**, not a Windows port of the game itself.

## Download

**Latest release: [Alpha V1.1.6](https://github.com/BluePhoenix120/HookLinkWindows/releases/latest)**

| Download | Intended use |
|---|---|
| **[Complete Windows package (ZIP)](https://github.com/BluePhoenix120/HookLinkWindows/releases/download/v1.1.6-alpha.1/HookLinkWindows-Windows-x64.zip)** | **Recommended.** Contains the Windows GUI executable together with the source tree, integrated engine and build scripts needed for IPA compilation. |
| [Standalone GUI EXE](https://github.com/BluePhoenix120/HookLinkWindows/releases/download/v1.1.6-alpha.1/HookLinkWindows.exe) | GUI launcher only. **Not sufficient to build an IPA by itself.** Use the complete ZIP instead. |
| [Source code](https://github.com/BluePhoenix120/HookLinkWindows) | For contributors and users who want to inspect the project or work from a Git checkout. |

1. Download the **complete ZIP** and extract it to a writable Windows folder (for example, somewhere on `D:\`).
2. Keep `HookLinkWindows.exe` in the extracted **project root** beside `win/`, `engine/`, `config/` and `docs/`. Do **not** move the EXE out on its own.
3. Open `HookLinkWindows.exe`. The bundled GUI can open without a separate Python installation, but **building the game still requires Python and the other prerequisites** listed below.

Windows may display an unsigned-app security warning. Check the publisher/source, release location and files before deciding whether to run an unsigned executable. This is not a Microsoft Store installer.

## Project status

**Alpha V1.1.6 — experimental Windows port (November 2026).**

| Area | Status |
|---|---|
| Windows GUI, package creation and automated regression tests | **164 Windows tests passed** for the V1.1.2 candidate; V1.1.3 adds shader-builder integration tests, but has not passed an end-to-end iOS build |
| Source integration | Original NXnative base integrated with HookLink-specific modifications and Windows overlays; see [Engine and upstream](#engine-and-upstream) |
| Fresh Windows install → full NUP build → signed IPA → iPhone game rendering | **Not yet verified end to end for V1.1.6** |
| Device compatibility and performance | **Limited testing**. Results from upstream HookLink or older local builds are not guarantees for this release |
| Installation, entitlements and on-device game-data transfer | Depend on the user's device, signing method and toolchain |

The developer has previously run Windows-generated builds on an iPhone 18 Pro Max with iOS 27.2, but that **does not establish that the V1.1.6 engine renders and functions correctly** this project is still in Alpha after all.

For development history, see [CHANGELOG.md](CHANGELOG.md). For the longer Windows setup and diagnostics reference, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

## Alpha V1.1.6 changes

**Windows resource-safety Alpha** following a 61-worker run that saturated 64 GiB RAM and made Windows nearly unresponsive. The 61 shader workers remain available, while actual Metal compile/link sessions now have an independent 24-session default and an 8 GiB physical-RAM admission reserve (configure Metal sessions in Advanced settings). Pauses and capacity report as `[METAL]` lines in the GUI. The Stop button now requests termination of the live builder's process tree on Windows, not just its top-level Python process. This does not claim a proven memory-leak root cause or a completed IPA build; diagnostic observations in full builds are still needed. Leave existing shader caches in place.

## Previous Alpha V1.1.5 changes

A fresh V1.1.4 Windows build completed 42,848 shader translations and 52,980 iOS Metal compilations, then failed when `cb_extent.py` imported missing `memo_reflection` from an older HookLink `c1_guard.py`. V1.1.5 replaces the stale guard with the **exact pinned original NXnative implementation**, preserving the analyzer and normalized memo-key behavior. Source-contract and functional tests now detect this mismatch in CI. **IPA creation and on-device rendering are still unverified.** Retain your compiled shader work directory rather than creating another clean one for the first retry.

## Previous Alpha V1.1.4 changes

A fresh V1.1.3 Windows build reached shader compilation and exposed another merged-engine API mismatch: the builder calls `dmsh_rewrite.membar_fence()`, but the original NXnative rewrite module did not contain HookLink's implementation. V1.1.4 restores HookLink's device-scope memory-fence rewrite in that module, retaining the original NXnative changes, and adds regression tests for the merged shader helper APIs. The underlying build had already rewritten its main/SDK binaries, split 186,587 shader inputs, and discovered 42,848 shaders; **no completed IPA or iPhone rendering verification is claimed for V1.1.4**.

## Previous Alpha V1.1.3 changes

This Alpha release fixes a source compatibility failure discovered in a clean Windows build of V1.1.2. The original NXnative `dmsh_atomic.py` no longer exports `cross_args()`, but the merged HookLink shader builder still called it. V1.1.3 removes those calls, uses the integrated shader-chain MSL 3.2 flags, fixes the worker exception handler for Windows/Python 3.14, and adds regression tests to catch API drift. **This is a testable fix, not a claim of a completed iOS shader compile or an on-device rendering fix.** Preserve existing build-work directories for retry; the shader-chain check may need to resynchronize local metadata.

## Requirements

You need a **Windows 10/11 x64 PC**, a compatible iPhone, your own supported `.nup` game file, adequate disk space, and the separate build toolchain. The integrated GUI checks the installed tools; it does not bundle or silently install third-party compilers.

| Component | Purpose / source |
|---|---|
| [Python 3.10+](https://www.python.org/downloads/windows/) (3.12–3.13 recommended) | Running the build scripts and their Python dependencies |
| [.NET SDK 10 (x64)](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) | Game-data and shader translator tooling |
| [LLVM/Clang 20+ for Windows](https://github.com/llvm/llvm-project/releases), including `ld64.lld` | Cross-compilation and linking |
| [Apple Metal Developer Tools for Windows](https://developer.apple.com/metal/tools/) | `metal.exe` and `metallib.exe` shader compilation |
| **iPhoneOS SDK 26+** | Required iOS SDK headers/framework stubs, **not included**; see [Apple SDK note](#apple-sdk-note) |
| [SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross) and [zstd](https://github.com/facebook/zstd/releases) | Shader translation and compression |
| Python packages and `dmsh_xlate.dll` | Check via the GUI; it can install missing approved Python packages with confirmation and build/repair the translator from source when prerequisites are present |
| [AltStore](https://altstore.io/) or another compatible signing/sideloading tool; [Apple Devices for Windows](https://apps.microsoft.com/detail/9np83lwlpz9k) | IPA installation/signing and, where supported, app file sharing |
| **Ample free storage** | Plan on **at least ~80 GB of working space** as an initial estimate, potentially more depending on extracted assets, shaders, staging files and output format |

Also needed: a supported version of the Ocarina of Time remake as a `.nup` file, supplied by the user. **No game or copyrighted game assets are available for download here.** The Windows GUI is specific to this NUP build flow; it does not provide a `prod.keys` field.

The authoritative requirement checker is the included engine doctor's report. For the detailed list and detection rules, see [docs/PREREQUISITES.md](docs/PREREQUISITES.md).

### Apple SDK note

**Xcode.app does not install or run as a Windows application.** The Windows builder uses the separately installed Metal Developer Tools for Windows and a locally accessible iPhoneOS SDK. HookLinkWindows does not distribute Apple's SDK or compiler executables.

Within **Toolchain setup…** the GUI provides **Download .xip** (opens an official Apple Xcode download link), **Import SDK from Xcode .xip…**, and a way to select an existing SDK folder. Review Apple's license and usage restrictions before attempting SDK extraction or use, particularly on non-Apple hardware. The project's tooling does not change those restrictions or promise that an import will succeed.

## Quick start (Windows)

The normal path uses the **GUI**; there is no need to hand-edit JSON configuration files for initial setup.

1. **Extract the complete release ZIP** and open `HookLinkWindows.exe` in its root directory.
2. Click **Check prerequisites**. Open **Toolchain setup…** for the detected statuses, download links, Python package installation, Metal/shader-translator repair and SDK selection or import. Install external dependencies from their official sources, reopen the GUI as needed, and check again.
3. In **Game .nup file**, browse to your own supported game input. Set **Build directory** to a separate workspace with substantial free space. Choose your **iOS runtime settings** file if you have a reason to override the included defaults.
4. Leave **App-only (recommended)** selected for a smaller IPA and a separate transfer folder. **Full (includes game data)** is available, but can produce an IPA too large for common sideloading tools.
5. Review **Preview command**, then select **Build IPA**. Read **Build output and diagnostics** for progress and any toolchain errors. The first build may take hours; cached rebuilds can be faster, but neither completion time nor successful compilation is guaranteed.
6. Sign and install the generated IPA using your own compatible sideloading tool, then transfer the files described in [Install on iPhone](#install-on-iphone).

**Testing from scratch?** The GUI's **New clean…** button creates a fresh sibling build directory and clears optional previous-shader reuse without deleting your existing build folders. This is the preferred way to validate V1.1.6 independently of an older shader cache.

**Advanced controls:** You can configure shader split workers (automatic mode detects logical CPUs with a cap of 61), Bundle ID, runtime settings, optional previous shader work, compatibility settings, and experimental native app-only packaging. The default Bundle ID is `PhoenixNetwork.HookLinkWindows`. **Changing it may create a separate iPhone app and leave previous saves inaccessible from the new app.** Start with the defaults unless testing a specific issue.

For step-by-step details and developer options, use [the full Windows setup guide](docs/GETTING_STARTED.md).

## Install on iPhone

The usual **App-only** build produces an IPA **and** a matching directory of game-derived files. The IPA is not a finished, independently playable download.

1. **Sign and install the generated IPA** using AltStore or another sideloading tool compatible with your Apple account, iOS version and requested entitlements. Enable Developer Mode on the phone when required.
2. Keep the generated transfer files together. Using **Apple Devices → Files** on Windows (where available), open the **installed app's Documents folder** and transfer:
   - `RomFS.img`
   - the exact matching `b-<shader-chain>.img` archive
   - `env.txt`
3. Verify the files belong to the **same build**. An old shader archive or an environment file updated only on Windows can result in a failed or black-screen launch.
4. Launch the app and test. Preserve your existing device data and saves before reinstalling or changing app IDs.

The runtime preset expected by this build includes `DM_MSL_DIR=.`, `DM_NVN_ENC_THREAD=0`, `DM_PSO_MTL4=0` and `DM_NVN_BARRIER=full`. Confirm the settings in the **phone's actual `env.txt`**, not only the Windows file, when investigating an issue.

**Full IPA:** This mode packages game data within the IPA instead of relying on the same split-transfer flow. Its output is much larger, and support depends on the signing/install tool.

> [!WARNING]
> Do **not** delete the existing iPhone app as a troubleshooting step without backing up its saves. Removing an app or installing under a different Bundle ID can delete or isolate its Documents data. HookLinkWindows does not provide an automatic Windows-side save-backup guarantee.

## Builds, caches and disk space

Builds can generate tens of gigabytes of intermediates and shader data. Keep the build workspace separate from the source tree and your original NUP file. By default, reuse a successful workspace for subsequent builds.

- **Do not delete shader caches or staging data when diagnosing a failure.** A new build may otherwise repeat lengthy extraction and compilation steps.
- **Previous shader work** is an optional, strict-verified reuse feature; it is not an automatic shortcut for incompatible shader chains. See [cache reuse documentation](docs/CACHE_REUSE_AND_NATIVE_PACKAGING.md).
- **New clean…** deliberately creates an isolated workspace with no shader reuse for reproducible testing.
- The **Build output and diagnostics** area and output logs are more useful for troubleshooting than assuming an apparently quiet compiler has frozen.

## Troubleshooting

| Symptom | What to check |
|---|---|
| GUI opens, but **Check prerequisites** fails | Confirm you extracted the **complete ZIP**, with `engine/` and `win/` next to the EXE; follow the listed missing-tool details |
| `dmsh_xlate.dll` or shader toolchain is missing | In **Toolchain setup…**, install/check .NET, SPIRV-Cross and Metal tools; use **Retry graphics setup** where offered |
| iPhoneOS SDK not detected | Use the GUI's SDK browse/import controls; remember Metal Developer Tools and the iPhoneOS SDK are separate requirements |
| Build seems idle during shader work | Inspect the diagnostics and underlying build logs before interrupting; some stages have long stretches with little visible progress |
| IPA signing or installation fails | Verify the IPA, chosen Bundle ID, signing capability, increased-memory entitlement if required, iOS compatibility and available device storage |
| **Black picture but controls respond** | Verify you installed the **correct IPA**, copied the matching `RomFS.img` and shader archive, and placed the expected `env.txt` inside **that app's Documents folder**. Collect logs rather than blindly changing render switches |
| Game exits or behaves incorrectly | Preserve the existing build/output, check the input version and runtime settings, and review device logs |

**Log collection:** The iPhone launcher includes **Export Game Logs** when available in the built app. After an affected session, export the previous/current logs from the launcher or the app's Documents folder. In the Windows GUI, choose **iPhone log…** to inspect a saved log locally. Logs may contain local paths or device information, so review them before sharing.

Still stuck? Open a [GitHub issue](https://github.com/BluePhoenix120/HookLinkWindows/issues) and include the release version, Windows version, toolchain status, iPhone/iOS model, build stage, and relevant **redacted** log excerpts. Never attach copyrighted game content, generated shader archives, IPAs, signing credentials or personal saves.

## Engine and upstream

V1.1.6 retains V1.1.2's integration of **original NXnative**, **HookLink's customized engine**, and the project's **Windows-specific adaptations**. It is **not** an unmodified copy of any one upstream repository.

| Component | Pinned revision |
|---|---|
| [Original `seedds/nxnative`](https://github.com/seedds/nxnative) | [`0b5fd6020093407af8bb5ad166e78e00bd2b7242`](https://github.com/seedds/nxnative/commit/0b5fd6020093407af8bb5ad166e78e00bd2b7242) |
| [HookLink engine `dsi-hub/nxnative`](https://github.com/dsi-hub/nxnative) | [`698b46bc5b14510fffc0a4b8fd4bf78309004e4c`](https://github.com/dsi-hub/nxnative/commit/698b46bc5b14510fffc0a4b8fd4bf78309004e4c) |
| Integrated engine source | `19528cf1e3115e64ecc8f02ab555ed0341579c09`, with preserved Windows overlays |
| HookLink base | `3.0.1` (X2.0.1) |

Conflicting merge hunks favored HookLink's existing behavior to retain game-specific fixes. The current pin and policy are recorded in [ENGINE_PIN.json](ENGINE_PIN.json); file provenance is in [ENGINE_PIN_FILES.json](ENGINE_PIN_FILES.json). The Windows GUI's upstream commit link points to the **original NXnative base**, not to an assertion that the merged engine is byte-identical to it.

Other relevant project documentation: [fork integration](docs/FORK_INTEGRATION.md), [shader-chain validation](docs/SHADER_CHAIN.md), [contribution guide](CONTRIBUTING.md), [changelog](CHANGELOG.md), and [upstream HookLink README snapshot](docs/UPSTREAM_HOOKLINK_README.md).

## Contributing

Windows clean-build results, verified device logs, tested fixes, and carefully scoped pull requests are welcome. When reporting performance or rendering issues, distinguish the **original upstream app**, **older HookLinkWindows releases**, and **this exact integrated engine**. Do not publish game-derived assets or Apple proprietary binaries.

**Community:** [Discord](https://discord.gg/bSrN5kEScg) · [Issues](https://github.com/BluePhoenix120/HookLinkWindows/issues) · [Releases](https://github.com/BluePhoenix120/HookLinkWindows/releases)


## Credits

- **[nxnative](https://github.com/seedds/nxnative)** by seedds and its contributors: the engine HookLinkWindows runs, which translates the game to native code and Metal.
- **[PromethOps](https://github.com/PromethOps)**: [nxnative PR #1455](https://github.com/seedds/nxnative/pull/1455), unused textures are retired when GPU memory runs short (the freeze after the talk with Saria).
- **[LeonardoBai12](https://github.com/LeonardoBai12)**: [nxnative PR #1543](https://github.com/seedds/nxnative/pull/1543), the game keeps real speed below 60 fps.
- **[vladbondarenko97](https://github.com/vladbondarenko97)**: [nxnative PR #1460](https://github.com/seedds/nxnative/pull/1460), the code locations behind Wide view.
- **[oliverames](https://github.com/oliverames)**: tested the engine on an iPhone Duo, and found and fixed the game running fast below 60 fps ([issue #1](https://github.com/dsi-hub/HookLinkWindows/issues/1)).
- **gunvalk**: found that the game's frame step ignores the frame's time (zortos293/Lichii PR #216), the basis of the real-speed fix.
- **[cheemu21](https://github.com/cheemu21)**, creator of kid-with-sword ([kid-with-sword-remake](https://github.com/cheemu21/kid-with-sword-remake)): inspired HookLinkWindows's touch controls, the glass look and the Mobile layout; the steady 30 fps mode and frame generation in 1.8 come from that fork, and so does the 8 GB memory layout that also fixes the Master Sword.
- **The fork's other contributors**, whose work is in those pieces: ednofedulo, ChiefSZ13 (the game's profile and bring-up), Pedro Nascimento (lunks), Xipzer, nanotchec, Adrian Smith, Romen Adama Caetano Ramírez, Travis (travislikestocode), uncraftablexd, mmkzer0, Nimesh Ambepitiya, MetaIX, TheGoldfish11, David Padron-Harris, zatteogit, tut, and the author of the oot2 branch.
- **[Tyuv97G](https://github.com/Tyuv97G)**: tested the engine on an iPhone 17 Pro and found the slowdown that the 30 fps steady mode answers ([issue #3](https://github.com/dsi-hub/HookLinkWindows/issues/3)).
- **[cshess](https://github.com/cshess)**: offered iPhone Duo testing and reported the third-party signer problem ([issue #1](https://github.com/dsi-hub/HookLinkWindows/issues/1)).
- **[HookShot](https://github.com/NotRexed/Hookshot)** by NotRexed: inspired HookLinkWindows's name and the idea of frame generation.
- **[HookLink](https://github.com/dsi-hub/HookLink)** by DSi-hub aka DSi: Developed HookLink. I'd say he is the most important dev from my perspective. Without DSi, this project would not exist. Thank you so much DSi.

## License

HookLinkWindows is free software under the [MIT License](LICENSE). It builds on nxnative, also MIT; its notice is kept in [NOTICE.md](NOTICE.md).

HookLinkWindows is an unofficial fan project, not affiliated with or endorsed by Nintendo. The Legend of Zelda and Ocarina of Time are trademarks of Nintendo.
