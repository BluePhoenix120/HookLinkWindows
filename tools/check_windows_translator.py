#!/usr/bin/env python3
"""Real Windows managed translator publish gate; no game or Apple SDK needed."""
from pathlib import Path
import os
import argparse
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
import bootstrap_translator as bootstrap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expected-source')
    ap.add_argument('--spirv-cross', type=Path)
    ap.add_argument('--evidence', type=Path)
    args = ap.parse_args()
    bootstrap.need(os.name == 'nt', 'Windows CI required')
    bootstrap.verify_source_identity(ROOT)
    dotnet = shutil.which('dotnet')
    bootstrap.need(dotnet is not None, '.NET 10 SDK not found')
    project = bootstrap.paths(ROOT)['project']
    expected = bootstrap.source_sha(project)
    print('Canonical translator source fingerprint:', expected, flush=True)
    if args.expected_source:
        bootstrap.need(expected == args.expected_source, 'Windows checkout source fingerprint differs from Linux candidate')
        recorded = dict(l.split('\t',1) for l in bootstrap.paths(ROOT)['lock'].read_text().splitlines() if '\t' in l and not l.startswith('#'))
        bootstrap.need(recorded.get('xlate_source') == expected, 'Candidate source lock mismatch')
    with tempfile.TemporaryDirectory(prefix='hlw translator smoke ') as td:
        output = Path(td) / 'managed publish'
        bootstrap.publish_managed_translator(dotnet, project, output, expected)
        # Independently ask the same engine tool-lock module used on the
        # user's PC. No Apple compiler or SPIRV-Cross is needed for this
        # source check. Do not modify the packaged lock or host header.
        env = os.environ.copy()
        env['XLATE'] = str(output / 'dmsh_xlate.dll')
        result = bootstrap.execute([sys.executable, '-B', '-c',
            "import sys; sys.path.insert(0,sys.argv[1]); "
            "import tool_lock; print(tool_lock.xlate_embedded()); "
            "print(tool_lock.xlate_source_sha())", str(project.parent)], env=env)
        bootstrap.need(result.splitlines() == [expected, expected],
                       f'Engine tool lock disagrees with managed translator: {result}')
        if args.spirv_cross:
            bootstrap.need(args.spirv_cross.is_file(), 'Pinned Windows SPIRV-Cross missing')
            env['SPIRV_CROSS'] = str(args.spirv_cross.resolve())
            script = """
import json, pathlib, sys
sys.path.insert(0,sys.argv[1])
import tool_lock as t, dmsh_chain as c
actual=t.tools_now(False)
assert actual['xlate_source']==c.xlate_source_sha()
assert all(len(actual[k])==16 and all(ch in '0123456789abcdef' for ch in actual[k]) for k in ('dmsh_xlate','spirv-cross'))
lock=pathlib.Path(c.LOCK); header=pathlib.Path(c.HEADER)
old, old_header=lock.read_bytes(),header.read_bytes()
before=c.version()
try:
    # Unmeasured source candidate must reject even a correctly built DLL.
    assert t.check_tools(False)
    recorded=dict(l.split('\\t',1) for l in old.decode().splitlines() if '\\t' in l and not l.startswith('#'))
    recorded.update(actual)
    lock.write_bytes((''.join(k+'\\t'+v+'\\n' for k,v in recorded.items())).encode())
    after=c.version()
    header.write_text(c.header_text(after),encoding='utf-8',newline='\\n')
    assert before!=after and not t.check_tools(False)
    assert c.version()==after
    # A changed SPIRV-Cross lock must fail and produce a different cache chain.
    lock.write_bytes(lock.read_bytes().replace(actual['spirv-cross'].encode(),b'0000000000000000'))
    assert t.check_tools(False) and c.version()!=after
    print(json.dumps({'source':actual['xlate_source'],'translator':actual['dmsh_xlate'],'spirv_cross':actual['spirv-cross'],'candidate_chain':before,'source_only_measured_chain':after,'metal_measured':False,'cache_invalidation':'passed'}))
finally:
    lock.write_bytes(old); header.write_bytes(old_header)
"""
            result = bootstrap.execute([sys.executable, '-B', '-c', script, str(project.parent)], env=env)
            evidence = json.loads(result)
            print('Measured Windows source-only toolchain: '+json.dumps(evidence), flush=True)
            if args.evidence:
                args.evidence.parent.mkdir(parents=True, exist_ok=True)
                args.evidence.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print('PASS: Windows managed translator publish and tool-lock fingerprint verified')


if __name__ == '__main__':
    main()
