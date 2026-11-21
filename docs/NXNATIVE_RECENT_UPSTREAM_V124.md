# Complete latest original NXnative update for Alpha V1.2.4

Original source update: \`d2fd78b402f92d5a83b78987e49aba22e8626719\` to \`3ec5b785f37f8c87d78433f152914d89c4ef93c9\` (all 29 affected paths).

All nonconflicting original code was integrated, and real HookLink/Windows changes were preserved by three-way merge. No upstream paths skipped except two prebuilt non-Windows translator binaries. Windows-specific Metal compiler lock/header stay configured for Windows; the GUI preflight verifies and regenerates them against the rebuilt translator before generating any IPA. This changes shader chain IDs and requires rebuild of incompatible shader libraries; cached game assets are not deleted.

This update contains original audio output route recovery, shader gather offsets, packing metadata checks and GL fixed-function adjustments. Full iOS IPA and device runtime verification remain outstanding.
