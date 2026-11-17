# HookLinkWindows

**Experimental Windows build tools and graphical interface for [HookLink](https://github.com/dsi-hub/HookLink), using the [nxnative](https://github.com/dsi-hub/nxnative) engine.**

HookLinkWindows helps users build an **unsigned iOS application locally** from a user-supplied *The Legend of Zelda: Ocarina of Time* remake `.nup` file. It provides a Windows GUI, prerequisite diagnostics, source-build tooling, and a packaging workflow for a smaller IPA with separate game data.

> **Experimental / pre-release:** A Windows-built app was tested on one iPhone, but this consolidated public fork has **not yet passed a clean-Windows, end-to-end `.nup`-to-iPhone build**. The automated Windows EXE workflow also requires validation on GitHub Actions. Expect compatibility issues. This repository does not include the game, a game-specific IPA, the iPhoneOS SDK, Metal compiler binaries, or signing credentials.

## Quick start

1. **Download the complete repository**, or (once a tested ZIP is available) its **complete Windows x64 release archive**. Extract it anywhere you can write files. A GUI-only download is not sufficient; the `engine/` directory must be present.
2. Open `HookLinkWindows.exe` at the repository root, if present. A CI-built **standalone GUI EXE** does not require Python simply to *open the interface*, but **Python is still needed for the build pipeline**. If no EXE is available, run `python win/hooklink_gui.pyw` with Python/Tkinter installed.
3. Click **Check prerequisites** and follow each reported installation or repair instruction.
4. Browse for your own Ocarina of Time remake **`.nup`**. This NUP-specific interface does not require a `prod.keys` field.
5. Select **App-only (recommended)** or **Full** packaging, review the settings with **Preview command**, and select **Build IPA**.
6. **Sign and sideload** the generated IPA using a compatible tool. With app-only packaging, transfer the accompanying `RomFS.img`, matching `b-<shader-chain>.img`, and `env.txt` into the app's Documents folder as described in the setup guide.

**Read the full instructions before building:** [Getting Started](docs/GETTING_STARTED.md) · [Prerequisites](docs/PREREQUISITES.md) · [Shader-chain setup](docs/SHADER_CHAIN.md)

## Prerequisites at a glance

The **Check prerequisites** button is the authoritative detection path for the active build. The Windows port currently expects:

| Component | Purpose |
|---|---|
| Windows 10/11 x64 | Build host |
| Python 3.10+ and required Python modules | Extraction, asset processing, and build scripts |
| .NET SDK 10 x64 | Extraction and shader translator |
| LLVM/Clang 20+ and `ld64.lld` | ARM64 iOS compilation and linking |
| SPIRV-Cross and zstd | Shader processing and compression |
| Apple's Metal Developer Tools for Windows | Metal shader compilation |
| iPhoneOS SDK 26+ | iOS headers and link libraries |
| Compatible iPhone, signing/sideloading software | Installing the locally generated application |

Apple's Xcode **IDE** runs on macOS; it is **not** an application users install on Windows. The iPhoneOS SDK and Metal developer tools must be acquired separately from authorized sources, subject to their license terms; this project does not redistribute them. See [Getting Started](docs/GETTING_STARTED.md) for download links, required Python modules, and nonstandard-path configuration. A passing prerequisite check does not guarantee a successful build.

## Packaging

- **App-only (default):** Builds the IPA, exports a smaller app IPA, and prepares a separate transfer folder with game resources and the corresponding compiled shader archive. The build may temporarily use substantial disk space.
- **Full:** Produces a large IPA with game resources bundled; many sideloading utilities cannot handle its size.

**Both formats are local build outputs, not public release artifacts.** Do not upload completed game-specific IPAs, translated game binaries, shader archives, or extracted game assets to this repository or its Releases.

## Project structure

| Path | Contents |
|---|---|
| `Sources/` and other upstream HookLink paths | Original HookLink project files |
| `engine/` | nxnative engine plus Windows build compatibility changes |
| `engine/win/` | Windows compiler and SDK-toolchain integration |
| `win/` | Windows GUI, prerequisite checker, portability helpers |
| `config/iphone-oot.env` | Example iPhone runtime settings tested with one configuration |
| `docs/` | Setup, requirements, release status, and issue history |
| `.github/workflows/windows-gui.yml` | CI packaging workflow for a full source-plus-GUI ZIP |

The repository can be extracted outside the Windows home directory. Build/output folders are user-selectable. Machine-specific settings belong in local ignored configuration, not Git.

## Known limitations

- **Clean-install reproducibility remains unverified.** The Alpha V1.0.0 IPA was successfully built and tested on the developer machine, and 96 regression tests passed. A fresh Windows checkout, compilation, signing, and sideload have not yet been validated end to end.
- **Windows shader-chain setup is build-specific.** The tested Windows toolchain uses shader chain `a58d7f1f4ef9`. Fresh installations can build the managed translator from source and generate a matching local tool lock and chain header using [Translator Bootstrap](docs/TRANSLATOR_BOOTSTRAP.md); this clean-install procedure remains unverified. Shader caches produced with different tool fingerprints are not necessarily compatible. [ENGINE_PIN.json](ENGINE_PIN.json) records the bundled nxnative revision.
- Some portability workarounds and the UIKit game-menu bridge are experimental. See [Getting Started](docs/GETTING_STARTED.md) and [release checklist](docs/RELEASE_CHECKLIST.md).
- The app may require an increased-memory-limit entitlement, which depends on signing and device support. An unsigned IPA alone does not grant it.
- The GitHub Actions GUI executable packaging is independent of the much larger iOS compilation toolchain and does not supply missing SDKs or proprietary tools.

See [Release Checklist](docs/RELEASE_CHECKLIST.md) for outstanding verification and [Publication Notes](docs/GITHUB_PUBLICATION.md) for distribution policy.

## Upstream, credits, and licensing

HookLinkWindows is a fork of **[dsi-hub/HookLink](https://github.com/dsi-hub/HookLink)**. Its engine is based on **[dsi-hub/nxnative](https://github.com/dsi-hub/nxnative)**; the initial Windows toolchain was adapted from **[zenvyzenshiro/NXNativeWindows](https://github.com/zenvyzenshiro/NXNativeWindows)**. Credit and relevant license text must be preserved for each included upstream or third-party component; see [`LICENSE`](LICENSE), [`NOTICE.md`](NOTICE.md), [`engine/LICENSE`](engine/LICENSE), and the license files included under `engine/dm/third_party/`.

This is an independent, experimental community project and is **not affiliated with or endorsed by Nintendo or Apple**. Game names and trademarks belong to their respective owners. Users are responsible for obtaining their own lawful game inputs, development components, and signing tools, and for observing applicable license terms and laws. The project does not distribute copyrighted game content, Apple SDKs, or game-specific IPAs.

## Development

Contributions and bug reports are welcome once the first source revision has been reviewed and published. Please include the Windows version, relevant tool versions, steps to reproduce, and a log with personal paths or secrets removed. Do not attach game files, private keys, extracted game assets, or commercial SDK files.

Project repository: [BluePhoenix120/HookLinkWindows](https://github.com/BluePhoenix120/HookLinkWindows)
