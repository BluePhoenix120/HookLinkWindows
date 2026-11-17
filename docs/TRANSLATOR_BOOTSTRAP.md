# HookLinkWindows Alpha V1.0.0 — translator bootstrap candidate

**Status:** Candidate pending Windows and clean-room testing. Do not claim this is a fully verified setup path yet.

This ZIP adds `win/bootstrap_translator.py`, a source-only .NET 10 translator builder, plus six platform-neutral tests. Extract the ZIP **into the root of the HookLinkWindows repository**. The files are source code; no Apple SDK, proprietary tools, games, compiled translator DLLs, or shader caches are distributed.

## First check (read-only)

Run from Windows PowerShell, adjusting the checkout location:

```powershell
python -B 'D:\GitHubFork\HookLinkWindows-2.0-Integration\win\bootstrap_translator.py' --root 'D:\GitHubFork\HookLinkWindows-2.0-Integration' --check
```

Expected in the known-good development checkout: `STATUS: READY` and the existing chain fingerprint. This step must not compile anything or modify tracked files.

## Fresh checkout only: explicit local bootstrap

After installing .NET 10 SDK, SPIRV-Cross (tested via Vulkan SDK), and licensed Apple Metal Developer Tools for Windows, run:

```powershell
python -B 'D:\GitHubFork\HookLinkWindows-2.0-Integration\win\bootstrap_translator.py' --root 'D:\GitHubFork\HookLinkWindows-2.0-Integration' --install --accept-new-chain
```

The script builds the translator from bundled source, verifies its embedded source SHA, copies the managed DLL and dependencies, synchronizes the **local** `dmsh_chain.lock` and `dmsh_chain.h` using the existing nxnative CLI, and checks the resulting chain. It keeps a rollback backup under `.HookLinkWindows-Maintenance` beside the repo.

**Important:** This creates a new local shader-chain identity when the compiled DLL or shader toolchain differs. Shaders from another chain must not be reused. The lock and header are Git-tracked files and will show local modifications. **Never run this on a working checkout unless you explicitly intend to regenerate its chain.** It does not edit game assets or completed IPA files.

## Focused tests

```powershell
Set-Location 'D:\GitHubFork\HookLinkWindows-2.0-Integration'; python -B -m unittest discover -s tests -p 'test_alpha100_bootstrap.py' -v
```

Full Windows regression suite:

```powershell
Set-Location 'D:\GitHubFork\HookLinkWindows-2.0-Integration'; python -B -m unittest discover -s tests -p 'test_*.py'
```

The bootstrap does **not** acquire or distribute Apple SDKs, Metal Developer Tools, games, keys, or any proprietary content. It requires those dependencies to be installed from their official sources.
