# Windows shader-chain preflight

Before **Build IPA** starts compiling an app or game shaders, the GUI runs `win/shader_chain_prepare.py --check` against the user's installed tools and the selected source checkout.

- If the lock, host header, and installed tools already agree, the GUI continues without modifying either file.
- If the checker reports toolchain mismatches, the GUI checks that local shader lock/header edits are not already pending in Git, then runs `--sync`. The helper saves both originals under `%LOCALAPPDATA%\HookLinkWindows\shader-chain-backups\` (or the user's home directory if LOCALAPPDATA is unavailable), regenerates the local lock and header, and validates the result. Failure blocks the build; the helper attempts to restore the previous files if synchronization fails.
- If the preflight returns an error, or post-sync verification fails, the GUI **does not start IPA compilation**.

These files are intentionally **local toolchain state**, not universal distribution values:

- `engine/dm/gfx/tools/dmsh_chain.lock`
- `engine/dm/gfx/nvn/dmsh_chain.h`

They may show as changed in Git after synchronization. Do not commit per-machine tool fingerprints without an explicit upstream compatibility decision. The original engine files remain recoverable from Git or the saved backup.

The preflight does **not** compile, delete, or otherwise change game shaders. The subsequent **Build IPA** operation can still compile shaders if no matching library exists in the chosen build directory. A previously compiled `b-<id>.img` is only compatible when the chain ID matches. The GUI logs whether it finds a matching archive, but its existence alone does not prove that the archive matches the game and build inputs.

For manual diagnostics from a complete repository checkout:

```powershell
python -B .\win\shader_chain_prepare.py --check
```

`--check` returns `0` when consistent, `1` for mismatches, and `2` for checker errors. `--sync` modifies the two local files with backup/rollback protection. The GUI runs the same process automatically only after the user confirms **Build IPA**.

This logic was tested offline with simulated checker outcomes; a complete IPA compilation from the consolidated fork and GitHub Actions release build remain unverified.
