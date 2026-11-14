# Sample .gitignore additions — review before adding to the real repository

These are suggestions for a **source-only** public build. Do not replace upstream `.gitignore` wholesale; avoid ignoring legitimate source assets. Crucially, Git ignore rules do not erase previously committed file history.

```gitignore
# Local machine/toolchain configuration
/win/toolchain.json
/win/sdk/out/

# Build products (check the real build output location)
*.ipa
*.nup
*.nsp
*.xci
*.nsz
*.xcz
RomFS.img
romfs.img
b-*.img
*.img.img.*
*.metallib
*.xip
*.mobileprovision
*.p12
*.pfx

# Locally generated libraries / launch packaging
/dm/gfx/tools/dmsh_xlate_bin/
/build/
/dist/
__pycache__/
*.pyc

# Local logs, signing and user credentials
prod.keys
title.keys
*.p8
*.p12
*.pfx
*.cer
*.key
log.txt
log.prev.txt
```

Check other game-specific generated binaries in the complete engine, e.g. rewritten NSO/extracted SDK modules (`*.nso`, `*.nca`, `*.nro`), without blanket-ignoring unrelated source files. Run `python tools/release_audit.py .` before commit and inspect `git ls-files` and staged changes. No ignore list substitutes for a manual source-content and Git-history review.
