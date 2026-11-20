# Full original NXnative sync — unvalidated candidate

Original NXnative target: https://github.com/seedds/nxnative/commit/d2fd78b402f92d5a83b78987e49aba22e8626719

HookLink engine retained: https://github.com/dsi-hub/nxnative/commit/698b46bc5b14510fffc0a4b8fd4bf78309004e4c

Previous original base: 0b5fd6020093407af8bb5ad166e78e00bd2b7242

Combined synthetic merge commit: 4c7473846bf0df7b2af2d7f881fc9e2989821c8b

Official files in target: 3897; merged files: 3940; changed original paths since X2: 925; changed files with retained custom conflicts/overlays: 76; all different paths: 133; explicit non-Windows binary exclusions: 2.

Git three-way merge imports all nonconflicting updates, favoring HookLinkWindows changes only where the merge conflicts. Windows-only files are retained. ENGINE_PIN_FILES.json records the original hashes and integrated hash for every conflicting updated file.

**Not yet verified:** Windows full suite, arm64 iOS host cross-compile, shader-cache compatibility, IPA build, phone rendering, audio, power and startup. Do not replace the working published V1.2.1 IPA until these checks pass.
