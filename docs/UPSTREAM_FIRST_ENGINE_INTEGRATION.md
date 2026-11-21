# Alpha V1.2.3 upstream-first engine integration

Latest original NXnative commit: d2fd78b402f92d5a83b78987e49aba22e8626719

HookLink custom engine commit: 698b46bc5b14510fffc0a4b8fd4bf78309004e4c

Synthetic Git source integration commit: c0c4aba1774690c82ba78b11d9a1551aeacedf09

Source is original NXnative first, with HookLink conflict hunks retained; Windows differences are rebased by three-way merge against HookLink (not by old-file preference).

Original/HookLink overlaps requiring reviewed HookLink resolution: 20

- .github/workflows/tests.yml
- dm/games/010056B015FE8000/README.md
- dm/games/0400486024DEC000/README.md
- dm/games/0400486024DEC000/patches.py
- dm/games/settings.tsv
- dm/gfx/nvn/nvn_mtl.m
- dm/gfx/nvn/nvn_ndve.inc
- dm/gfx/nvn/nvn_owner.m
- dm/gfx/tests/t_arena_trim.m
- dm/host/Makefile
- dm/host/hle_audio.c
- dm/host/tests/Makefile
- dm/host/tests/t_svc_memory.c
- dm/ios/Sources/front_ios.m
- dm/ios/Sources/main.m
- dm/mac/Launcher.swift
- docs/agents/game-patches.md
- docs/agents/symptoms.md
- docs/env_switches.tsv
- docs/reference/memory.md

Windows custom overlaps resolved explicitly: 6

- dm/gfx/nvn/dmsh_chain.h: explicit reviewed hunk resolution
- dm/gfx/nvn/nvn_mtl.m: explicit reviewed hunk resolution
- dm/gfx/tools/dmsh_build.py: explicit reviewed hunk resolution
- dm/gfx/tools/dmsh_chain.lock: explicit reviewed hunk resolution
- dm/gfx/tools/dmsh_rewrite.py: explicit reviewed hunk resolution
- docs/reference/frame-rate.md: explicit reviewed hunk resolution

Original source files: 3897; integrated source files: 3940; modified original files: 77.

The Windows Metal compiler lock and chain header are deliberately preserved and **must be reverified/rebuilt** by the Windows toolchain. This source integration has not been validated through a full IPA build or on-device test. Keep the known-working V1.2.1 app and shader caches intact.
