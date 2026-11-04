# SPDX-License-Identifier: MIT
"""Public Expert integration checks; legacy artistic goldens stay immutable.

Those goldens describe the retired mapper, not the approved public intensity
curve. Scalar/native curve and trim equations have separate numeric tests;
these cases retain container geometry, L5, range, flip and output-code checks.
"""
import json
import math
from pathlib import Path
import subprocess
import sys
from run_gpu_images import wire

ROOT=Path(__file__).resolve().parent

def pq(nits):
    x=(nits/10000)**(2610/16384)
    return ((3424/4096+2413/128*x)/(1+2392/128*x))**(2523/32)

data=json.loads((ROOT/'vectors.json').read_text())
cases=[c for c in data['image_cases'] if c['mode']=='Reference Expert' and 'codes' in c['expected']]
if '--scaled' in sys.argv:
    cases=json.loads((ROOT/'scaled-output-vectors.json').read_text())['cases']
for case in cases:
    process=subprocess.run([sys.argv[1]],input=wire(case),capture_output=True,text=True)
    assert process.returncode==0,(case['id'],process.stderr)
    actual=json.loads(process.stdout);settings=case['input']
    width,height=settings.get('output_size',settings['size'])
    assert len(actual['rgb'])==len(actual['codes'])==width*height
    bits=settings.get('bits',10);limited=settings.get('limited',True)
    maximum=(1<<bits)-1;offset=16*(1<<(bits-8)) if limited else 0
    span=219*(1<<(bits-8)) if limited else maximum
    ceiling=math.floor(offset+span*pq(settings['peak']))
    for pixel,codes,legacy in zip(actual['rgb'],actual['codes'],case['expected']['rgb']):
        for value,code in zip(pixel,codes):
            assert math.isfinite(value) and 0<=value<=pq(settings['peak'])+1e-6,(case['id'],value)
            assert offset<=code<=ceiling,(case['id'],code,ceiling)
            expected=min(math.floor(offset+span*value+.5),ceiling)
            assert abs(code-expected)<=1,(case['id'],code,expected)
        if not any(legacy):assert not any(pixel),(case['id'],'zero/L5 endpoint')
    if '--scaled' in sys.argv and case['source_scaler_id']=='two-axis-upscale-overshoot':
        assert 0<max(actual['rgb'][28])<max(actual['rgb'][30])<max(actual['rgb'][35])
    print('PASS public Expert integration:',case['id'],flush=True)
print('Cases:',len(cases),'(not a comparison with proprietary Dolby rendering)')
