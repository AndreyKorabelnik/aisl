#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parents[1]
mods=json.loads((root/'MODULES.json').read_text())['modules']
errors=[]
for mod in mods:
    mroot=root/mod['path']; manifest=mroot/'SOURCE_TREE_MANIFEST.sha256'
    actual_manifest_sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if actual_manifest_sha!=mod['source_manifest_sha256']:
        errors.append(f"{mod['name']}: source manifest fingerprint mismatch")
        continue
    count=0
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        expected,rel=line.split('  ',1); p=mroot/rel
        actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        if actual!=expected: errors.append(f"{mod['name']}: {rel}")
        count+=1
    if count!=mod['source_file_count']: errors.append(f"{mod['name']}: file count mismatch")
    print(f"{mod['name']} {count}/{mod['source_file_count']} {'PASS' if not any(e.startswith(mod['name']+':') for e in errors) else 'FAIL'}")
if errors:
    print('\n'.join(errors),file=sys.stderr); raise SystemExit(1)
print('AISL Consumer Suite source verification PASS')
