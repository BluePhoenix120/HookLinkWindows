"""Build a separate DMROMFS1 image with build-time mod replacements.

Keep the original image intact, including its damaged-file flags. Rebuild
the index so new files (including nested pack resources) are visible to
the native host. No extraction to a Windows filesystem is necessary.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
import romfs


def _identity(path):
    st = path.stat()
    return [st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino]


def overlay_image(source, mod_dirs, root, log=print):
    source, root = Path(source).resolve(), Path(root).resolve()
    image = romfs.Image(source)
    stock = _identity(source)
    tree = {}
    def load(k, node):
        a, b, _, _, kind, flags = image.entry(k)
        for i in range(a, a + b):
            name = image.name(i)
            off, size, _, _, typ, damage = image.entry(i)
            if typ: node[name] = (off, size, damage)
            else:
                node[name] = {}
                load(i, node[name])
    load(0, tree)
    changes = {}
    tables = []
    for directory in map(Path, mod_dirs):
        for f in sorted(directory.rglob('*')):
            if f.is_symlink(): raise ValueError(f'Mod symlinks are not supported: {f}')
            if not f.is_file(): continue
            rel = f.relative_to(directory)
            if any(x.startswith('.') for x in rel.parts): continue
            if rel.parts[0].lower() == 'shader' or '.bfsha' in f.name.lower() or '.bnsh' in f.name.lower():
                raise ValueError(f'Mod changes shader inputs; not supported by this cached build: {rel}')
            key = tuple(x.encode('utf-8') for x in rel.parts)
            if key in changes: raise ValueError(f'Multiple mods change {rel}; combine them in the converter first')
            if f.name.lower().endswith('.rsizetable.zs'): tables.append(f)
            changes[key] = f
    if not changes: raise ValueError('Selected RomFS mods have no files')
    if len(tables) > 1: raise ValueError('Multiple resource-size tables; combine outfits in the converter first')
    for parts, f in changes.items():
        node = tree
        for component in parts[:-1]:
            node = node.setdefault(component, {})
            if not isinstance(node, dict): raise ValueError(f'Mod path conflicts with a file: {f}')
        if isinstance(node.get(parts[-1]), dict): raise ValueError(f'Mod path conflicts with a directory: {f}')
        if f.name.lower().endswith('.rsizetable.zs') and parts[-1] not in node:
            raise ValueError(f'Mod resource-size table does not match the game: {f}')
        node[parts[-1]] = f
    def fingerprint():
        h = hashlib.sha256()
        h.update(json.dumps([str(source), _identity(source)]).encode())
        h.update(Path(__file__).read_bytes())
        for rel, f in sorted(changes.items()):
            h.update(b'/'.join(rel) + b'\0')
            file_hash = hashlib.sha256()
            with f.open('rb') as stream:
                while chunk := stream.read(8 << 20): file_hash.update(chunk)
            h.update(file_hash.digest())
        return h.hexdigest()
    digest = fingerprint()
    dest = root / digest / 'RomFS.img'
    stamp = dest.with_suffix('.json')
    try:
        if json.loads(stamp.read_text(encoding='utf-8')) == _identity(dest):
            romfs.Image(dest)
            log(f'mods: reusing packed RomFS ({len(changes)} replacement/addition files)')
            return dest
    except (OSError, ValueError): pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix('.part')
    log(f'mods: creating separate RomFS for {len(changes)} replacement/addition files (original remains intact)')
    try:
        with source.open('rb') as src, tmp.open('wb') as out:
            _, end, _, _ = romfs.HEAD.unpack(src.read(romfs.HEAD.size))
            out.write(b'\0' * romfs.HEAD.size)
            remaining = end - romfs.HEAD.size
            while remaining:
                chunk = src.read(min(8 << 20, remaining))
                if not chunk: raise ValueError('Truncated source RomFS')
                out.write(chunk)
                remaining -= len(chunk)
            entries = [(b'', tree)]
            index, names = bytearray(), bytearray()
            i = 0
            while i < len(entries):
                name, item = entries[i]; i += 1
                if isinstance(item, dict):
                    a, b, kind, flags = len(entries), len(item), 0, 0
                    entries.extend(sorted(item.items()))
                elif isinstance(item, Path):
                    a, kind, flags = out.tell(), 1, 0
                    with item.open('rb') as f: shutil.copyfileobj(f, out, 8 << 20)
                    b = out.tell() - a
                else:
                    a, b, flags = item; kind = 1
                index.extend(romfs.ENT.pack(a, b, len(names), len(name), kind, flags))
                names.extend(name)
            end = out.tell()
            out.write(index); out.write(names)
            out.seek(0)
            out.write(romfs.HEAD.pack(romfs.MAGIC, end, len(index) + len(names), len(entries)))
        romfs.Image(tmp)
        if _identity(source) != stock or fingerprint() != digest: raise ValueError('RomFS or mod inputs changed during packaging')
        os.replace(tmp, dest)
        stamp.write_text(json.dumps(_identity(dest)), encoding='utf-8')
    finally:
        tmp.unlink(missing_ok=True)
    log(f'mods: packed {len(changes)} replacement/addition files into {dest}')
    return dest
