# SPDX-License-Identifier: MIT
"""Separate exposed-PQ assertions derived from frozen signed reconstruction.

Does not replace or alter the original pre-encoding linear-nits oracle/budget.
Public floating descriptors allow the original .5 pivot to be represented exactly.
The engine AVDOVIMetadata ingress remains covered by separate compiled tests.
"""
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

def wire(case):
    v = case['input']
    numbers = list(v['size']) + v.get('ycc_offset', [0]*3)
    for matrix in (v.get('ycc', IDENTITY), v.get('linear', IDENTITY)):
        numbers.extend(x for row in matrix for x in row)
    shapes = {s['channel']: s for s in v.get('reshape', [])}
    for c in range(3):
        shape = shapes.get(c, {})
        pivots = shape.get('pivots', [0, 1])
        numbers.extend([len(pivots), *pivots])
        for segment in shape.get('segments', [{'poly': [0, 1, 0]}]):
            mmr = segment.get('mmr', [])
            numbers.extend([int(bool(mmr)), len(mmr), segment.get('constant', 0)])
            numbers.extend(segment.get('poly', [0]*3))
            for order in range(3):
                numbers.extend(mmr[order] if order < len(mmr) else [0]*7)
    numbers.extend(x for pixel in v['rgb'] for x in pixel)
    return ' '.join(map(str, numbers)) + '\n'

def exposed_pq(nits):
    # Original public shader's negative-only guard. No upper clamp: source
    # reconstruction controls intentionally include values exceeding 10000.
    v = (max(nits, 0)/10000)**(2610/16384)
    return ((3424/4096 + (2413/128)*v)/(1+(2392/128)*v))**(2523/32)

def main():
    cases = [c for c in json.loads((ROOT/'vectors.json').read_text())['image_cases']
             if c['id'].startswith('reconstruct-nonidentity-')]
    assert len(cases) == 3
    for case in cases:
        result = subprocess.run([sys.argv[1]], input=wire(case), capture_output=True, text=True)
        print(case['id'], 'exit', result.returncode, flush=True)
        print(result.stderr, end='')
        assert result.returncode == 0
        rgb = json.loads(result.stdout)['rgb']
        signed = case['expected']['rgb']
        assert len(rgb) == len(signed)
        if len(sys.argv)>2 and sys.argv[2] == 'signed-capture':
            # Captured nits/10000: sign and upper-bound retention only, not an
            # invented FP32 linear-nit accuracy budget.
            for p,q in zip(rgb,signed):
                for actual,frozen in zip(p,q):
                    assert math.isfinite(actual)
                    if frozen<0: assert actual<0
                    if frozen>10000: assert actual>1
            print('PASS actual pre-guard signed/over-10000 retention; no linear accuracy claim', flush=True)
        else:
            worst=max(abs(a-exposed_pq(b)) for p,q in zip(rgb,signed) for a,b in zip(p,q))
            assert worst <= 1/65535, (case['id'], worst, rgb)
            for p,q in zip(rgb,signed):
                for actual,frozen in zip(p,q):
                    if frozen>10000: assert actual>1
            print('PASS separate exposed-PQ coverage, max PQ error',worst,flush=True)
    return 0

if __name__ == '__main__':
    sys.exit(main())
