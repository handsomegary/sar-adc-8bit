#!/usr/bin/env python3
"""Verify this compact release and recompute its exported-data analyses."""
import hashlib
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
from reproduce_all import ROOT, read, reproduce


def main():
    manifest = read(ROOT / 'release_manifest.json')
    files = manifest['files']
    total = 0
    forbidden = {'.zip', '.oa', '.oalib', '.pdf', '.log', '.tran', '.db', '.pyc'}
    leaks = [r'/home/', r'/opt/eda', r'(?i)\b[A-Z]:[\\/]',
             r'192\.168\.\d+\.\d+', r'BEGIN [A-Z ]*PRIVATE KEY',
             r'(?i)(?:license_file|remote_host|password)\s*[=:]']
    for relative, expected in files.items():
        path = ROOT / relative
        if path.resolve() != path or not path.is_file() or path.suffix.lower() in forbidden:
            raise ValueError('Missing/unsafe/excluded artifact: ' + relative)
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != expected['sha256'] or len(body) != expected['bytes']:
            raise ValueError('Release bytes differ: ' + relative)
        if len(body) >= 50 * 1024 * 1024:
            raise ValueError('File too large')
        total += len(body)
        if path.suffix.lower() in {'.json', '.csv', '.py', '.md', '.svg', '.scs'}:
            text = body.decode('utf-8')
            # The scanner source itself contains intentional pattern literals.
            if relative != 'tools/verify_release.py' and any(re.search(pattern, text) for pattern in leaks):
                raise ValueError('Private environment/credential marker: ' + relative)
    if total >= 100 * 1024 * 1024:
        raise ValueError('Release exceeds compact package target')
    actual = {str(path.relative_to(ROOT)).replace('\\', '/') for path in ROOT.rglob('*') if path.is_file()
              and not any(part in {'.git', '__pycache__', 'reproduced', '.venv'} for part in path.relative_to(ROOT).parts)
              and path.name != 'release_manifest.json'}
    if actual != set(files):
        raise ValueError('Unexpected/unmanifested artifacts: ' + str(sorted(actual ^ set(files))))
    result = reproduce()
    if (ROOT / 'design/adc_topology.scs').read_text(encoding='utf-8') != __import__('adc_topology').generate_core():
        raise ValueError('Published nominal topology differs from authored generator')
    gate = read(ROOT / 'evidence/declared_gate.json')
    if gate['schematic_prototype_complete'] is not True or not all(value is True for value in gate['checks'].values()):
        raise ValueError('Historical declared prototype gate changed')
    if gate['diagnostics_retained_without_overriding']['strict_selected_reverse_70_codes_identical'] is not False:
        raise ValueError('Failed strict reverse-history diagnostic was hidden')
    print(json.dumps({'status': 'RELEASE_HASHES_EXPORT_ANALYSIS_AND_SCOPE_CHECKED', 'files': len(files),
                      'total_bytes': total, 'dynamic_records': len(result['dynamic']),
                      'static_corners': len(result['static']), 'nominal_MOS': result['topology_counts']['ADC'],
                      'strict_reverse_history_equality': False, 'simulations_launched': 0,
                      'native_power_reintegrated': False}, indent=2))


if __name__ == '__main__':
    main()
