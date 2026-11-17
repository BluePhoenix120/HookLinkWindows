# HookLinkWindows — Windows first-time setup (release candidate)

This guide covers **building your own local iOS application from your own Ocarina of Time remake `.nup`**. HookLinkWindows is an experimental Windows port. It does **not** include the game, a prebuilt game-specific IPA, signing credentials, Apple's SDK, or Apple's proprietary compiler tools. The source-only GitHub release must include **the entire tested HookLinkWindows engine**; a GUI add-on ZIP alone cannot compile an IPA.

> **Status:** The original port and one iPhone build were tested by the project's developer. This GUI release candidate has **not** passed a clean Windows machine build or complete end-to-end device installation. Some steps depend on third-party tools and terms that users must review.

## 1. Obtain the complete source checkout

Use the project's GitHub **Code → Download ZIP**, extract it to any writable folder (for example `D:\Projects\HookLinkWindows`), or clone the future published repository with Git. No special installation directory or administrator-level path is required. **Keep the EXE in the checkout root beside the `win`, `engine`, `config`, `Sources`, and `docs` directories. The Windows engine lives under `engine/`; a GUI-only ZIP cannot compile.** Do not run the GUI from a separate archive containing only the GUI add-on.

Double-click `HookLinkWindows.exe`. For the compact native launcher, Python must be installed; the separate PyInstaller EXE distributed by a successful Windows GitHub Actions build can open the GUI without Python, but compiling a game still requires Python and the toolchain. If Windows SmartScreen warns about an unsigned new application, verify the release's source and download origin before deciding whether to run it.

The single **Check prerequisites** action first inspects the repository layout and reports missing files with the reason and fix. If the checkout is complete, it then checks compilers and SDKs. The **Setup guide** remains available from the GUI.

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

### Verify Python packages (one command)

Run in PowerShell or Windows Terminal if the checker reports missing Python modules:

```powershell
python -m pip install --upgrade lz4 capstone fonttools pillow backports.zstd
```

For Python 3.14+, `compression.zstd` is expected; the extra backport may not be needed. Use a Python interpreter supported by the engine. This single command installs only Python packages, not external SDKs or compilers.

## 3. Apple SDK and Metal tools — important distinction

**Xcode.app is a macOS application. You cannot install and run the entire Xcode IDE on Windows.** For this Windows build you need an **iPhoneOS SDK folder** and Apple's **Metal Developer Tools for Windows**. The upstream Windows port documents a script `win/sdk/extract_xip.py` that can extract SDK files from an Xcode `.xip`; it also supports pointing to an SDK acquired on a Mac. Consult Apple's license terms before obtaining or using these files, particularly on non-Apple hardware; this project does not include or redistribute them.

Official sources: https://developer.apple.com/download/all/ and https://developer.apple.com/xcode/system-requirements/ . For the release tested here, an SDK from Xcode **27.2** was used; the upstream Windows doctor requires **26+**. The project's local `win/toolchain.json` or environment variables may point to a different SDK directory.

**Do not copy the full Xcode application into the project or commit an SDK folder to GitHub.** Keep local SDK/compiler paths in ignored local config. The GUI checks that `win/toolchain.json` is readable but does not download or manage these files.

## 4. Toolchain setup in Alpha 1.0.3

**No command-line compilation or JSON editing is needed for the shader translator.** Click **Check prerequisites** in the GUI. When the `dmsh_xlate.dll` translator is absent and the required .NET 10 SDK, SPIRV-Cross and Apple Metal compilers are already available, HookLinkWindows automatically prepares graphics support from the bundled source, verifies it, and backs up the local shader-chain metadata before synchronization. The progress and any errors appear in **Build output and diagnostics**. This does not delete the game or shader caches, although a new shader-chain identity can make previously built shaders incompatible.

If automatic graphics setup fails, open **Toolchain setup… → Retry graphics setup**. For an existing translator, automatic setup never overwrites it: any manual retry that may regenerate a shader chain requires confirmation.

The **iPhoneOS 26+ SDK is a separate prerequisite**; it is *not* needed for preparing the translator. It is not bundled with HookLinkWindows. Obtain it from an authorized Apple Xcode distribution and comply with the applicable Apple license. The GUI currently provides **Toolchain setup… → Browse… → Save SDK directory** to register an already extracted SDK. Automatic SDK acquisition and extraction are not yet implemented.

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
