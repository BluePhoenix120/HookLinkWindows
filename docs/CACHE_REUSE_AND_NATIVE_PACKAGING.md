# Experimental cache reuse and native app-only builds

HookLinkWindows v0.8.3 introduces two **opt-in** features in **Advanced settings**. They are
not prerequisites for building. Neither feature has yet completed an actual Windows IPA
build followed by an iPhone installation in the consolidated public repository.

## Previous shader work

Enter the path to an existing *completed build work directory* (for example,
`C:\HookLinkWindowsBuild`), **not** the repository root or the `shader/ios` subfolder.
The new build directory must remain separate.

The iOS shader stage will be skipped only if all of these checks pass:

1. The newly generated shader **package content fingerprint** matches the prior
   build's `shader/pkg` package.
2. The previous `shader/ios/b-<chain>.img` contains a complete iOS library.
3. Its embedded game ID and profile-input stamp match the current build.
4. The library includes any pulling shaders required by this build.
5. The local `c1_full.tsv` and `cb_extent.tsv` tables match the chain and inputs.

**If any check fails, the opted-in build stops with an error.** Remove the reuse path
and build normally if the old results are incompatible. Nothing in the old work directory
is modified by the reuse implementation. The compiler still performs extraction, NSO
patching and shader-package preparation for the current NUP before this check.

## Native app-only packaging

Enable **Experimental native app-only packaging** to ask the Windows compiler to
produce a small IPA directly, plus a sibling `*-iPhone-Files` directory containing
`RomFS.img`, `b-<chain>.img`, and `env.txt`. This avoids creating the 25+ GB
intermediate full IPA used by legacy app-only mode.

The final IPA is validated to contain an app executable and not include the externalized
game data. All three transfer files must be present and nonempty before the GUI reports
success. The shader image is **copied** rather than hard-linked if it came from an
existing external work directory, preventing edits to the transfer copy from changing
the donor image. Other sources may be hard-linked on the same volume to save space.

Install/sign the IPA using your supported sideloading tool, then copy the **contents** of
the `*-iPhone-Files` directory into the app's Documents folder through Apple Devices >
Files. Keep game-derived files private. The public source repository includes none.

This path is **experimental**; leave it disabled for the previously exercised full-IPA
then strip workflow until the new mode is validated end-to-end on Windows and iPhone.

## Limits and safety

- Shader-chain checking remains required before a build. A different toolchain may
  produce a different shader archive name and invalidate external reuse.
- A matching shader library stamp alone is insufficient; exact shader-package content
  is checked after the new NUP is processed.
- Reuse doesn't bypass extraction, profile generation or app compilation.
- App-only output still contains game-specific executable and metadata. Do not publish
  finished game-specific IPAs, game input files, or shader archives.
- The original build should remain intact; no direct hard links to its external shader
  archive are created for the transfer folder.
- User-installed Apple iPhoneOS SDKs and Metal tools must remain external to Git.
