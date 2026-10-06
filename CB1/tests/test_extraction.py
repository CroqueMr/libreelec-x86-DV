# SPDX-License-Identifier: MIT
"""Extraction checks: detect missing/changed bytes and accidental Kodi coupling."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def extraction_matches_cumulative_tree(cumulative):
    origins = json.loads((ROOT / 'config/extraction-origins.json').read_text())
    owned = json.loads((ROOT / 'config/owned-sources.json').read_text())
    assert len(origins['files']) == 22
    for destination, record in origins['files'].items():
        extracted = ROOT / destination
        assert extracted.is_file(), 'Missing extracted source: ' + destination
        original = cumulative / record['source']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == record['sha256'], destination
        if destination not in owned:
            assert extracted.read_bytes() == original.read_bytes(), destination
    for destination, digest in owned.items():
        assert hashlib.sha256((ROOT / destination).read_bytes()).hexdigest() == digest, destination
    assert {p.name for p in (ROOT / 'src').iterdir()} == {
        Path(p).name for p in origins['files'].keys() | owned.keys()}


def engine_has_no_kodi_dependency(output, prefix):
    assert (ROOT / 'CMakeLists.txt').is_file(), 'Standalone root CMake is missing'
    assert not output.exists(), 'Build evidence must be fresh'
    subprocess.run(['cmake', '-S', str(ROOT), '-B', str(output),
                    '-DCMAKE_PREFIX_PATH=' + str(prefix),
                    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'], check=True)
    subprocess.run(['cmake', '--build', str(output), '-j2'], check=True)
    commands = json.loads((output / 'compile_commands.json').read_text())
    origins=json.loads((ROOT/'config/extraction-origins.json').read_text())
    owned=json.loads((ROOT/'config/owned-sources.json').read_text())
    optional = {'cb1_l1l3_model.c', 'cb1_hdr10_features.c', 'cb1_hdr10_extrema.c',
                'cb1_hdr10_quantiles.c', 'cb1_hdr10_statistics.c', 'cb1_hdr10_filter.c',
                'cb1_hdr10_ingress.c', 'cb1_hdr10_spatial.c', 'cb1_hdr10_temporal.c',
                'cb1_hdr10_ai.c'}
    expected={str((ROOT/p).resolve()) for p in origins['files'].keys() | owned.keys()
              if p.endswith('.c') and Path(p).name not in optional}
    assert {str(Path(c['file']).resolve()) for c in commands} == expected, 'Declared runtime units differ from compiled units'
    assert len(commands)==len(expected), 'Duplicate runtime compilation'
    assert all('/xbmc/' not in c['command'] and '/tools/dvbridge' not in c['command']
               for c in commands), 'Build imported Kodi source or headers'
    assert (output / 'src/libdvbridge_core.a').is_file()


def stock_headers_rejected(stock, prefix):
    dependencies = json.loads((ROOT / 'config/dependencies.json').read_text())
    assert (stock / 'RELEASE').read_text().strip() == dependencies['ffmpeg']['version']
    fixture = ROOT / 'tests/ffmpeg_metadata_fields.c'
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / 'fields.o'
        includes = [argument for path in str(prefix).split(';')
                    for argument in ('-I', str(Path(path) / 'include'))]
        matched = subprocess.run(['cc', *includes, '-c', str(fixture),
                                  '-o', str(output)], capture_output=True, text=True)
        assert matched.returncode == 0, matched.stderr
        stock_result = subprocess.run(['cc', '-I', str(stock), '-c', str(fixture),
                                       '-o', str(output)], capture_output=True, text=True)
        assert stock_result.returncode != 0, 'Stock headers unexpectedly accepted'
        for field in ('dvbridge_raw_magic', 'dvbridge_original_length', 'dvbridge_original_bytes'):
            assert field in stock_result.stderr, stock_result.stderr
        print(stock_result.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('check', choices=['extraction_matches_cumulative_tree',
                                          'engine_has_no_kodi_dependency', 'stock_headers_rejected'])
    parser.add_argument('--cumulative', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--stock', type=Path)
    args = parser.parse_args()
    if args.check == 'extraction_matches_cumulative_tree':
        extraction_matches_cumulative_tree(args.cumulative)
    elif args.check == 'stock_headers_rejected':
        stock_headers_rejected(args.stock, args.prefix)
    elif args.output:
        engine_has_no_kodi_dependency(args.output, args.prefix)
    else:
        with tempfile.TemporaryDirectory() as temporary:
            engine_has_no_kodi_dependency(Path(temporary) / 'build', args.prefix)
    print('PASS:', args.check)
