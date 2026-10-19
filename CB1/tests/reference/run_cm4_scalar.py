# SPDX-License-Identifier: GPL-3.0-only
"""Compare the C trim-only stage with the independent binary64 contract."""
import json
import math
import subprocess
import sys
import cm4_reference as ref

if len(sys.argv)>2 and sys.argv[2]=='--fit':
    result=subprocess.run([sys.argv[1],'--fit-json'],capture_output=True,text=True,check=True)
    print(result.stderr,end='',file=sys.stderr)
    cases=json.loads(result.stdout)['cases']
    assert len(cases)==5
    neutral=rejected=0
    for case in cases:
        # These fixtures do not satisfy the stronger expansion/midtone objective.
        expected=2 if not case['preset'] and case['peak']<=1000 else 1
        assert case['status']==expected,case
        assert case['words']==[2048]*5,case
        neutral+=case['status']==2
        rejected+=case['status']==1
    authored=json.loads(subprocess.run([sys.argv[1],'--authored-json'],capture_output=True,
        text=True,check=True).stdout)
    assert authored=={'status':1,'preserved':True},authored
    # Check objective samples emitted by the real C model against Python.
    if len(sys.argv)>3:
        measured=json.loads(subprocess.run([sys.argv[3],'objective-json'],
            capture_output=True,text=True,check=True).stdout)
        for row in measured:
            wanted=ref.enhanced_objective(row['input'],row['master'],row['target'],1,
                'Signature' if row['preset'] else 'Natural')
            for got,want in zip(row['output'],wanted):
                # C obtains its luma matrix from native float libplacebo primaries.
                assert math.isclose(got,want,rel_tol=2e-7,abs_tol=1e-8),(row,wanted)
        assert len(measured)==18
    print('PASS explicit qualification:',neutral,'identities,',rejected,
          'preserved rejections; no successful expansion claimed')
    sys.exit(0)

gpu = len(sys.argv) > 2 and sys.argv[2] == '--gpu'
result = subprocess.run([sys.argv[1], '--gpu' if gpu else '--scalar'], capture_output=True, text=True, check=True)
print(result.stderr, end='', file=sys.stderr)
cases = json.loads(result.stdout)['cases']
assert len(cases) == (408 if gpu else 312)
for case in cases:
    c = case['control']
    controls = dict(primary=[2048]*6, mid_contrast=2048, clip_trim=2048,
                    saturation=[128]*6, hue=[128]*6)
    if 0 < c < 6:
        controls['primary'][c-1] = 3072
    if c == 6:
        controls['primary'][5] = 4095
    if c == 7:
        controls['mid_contrast'] = 3072
    if c == 8:
        controls['clip_trim'] = 0
    if c == 9:
        controls['saturation'][0], controls['saturation'][2] = 255, 0
    if c == 10:
        controls['hue'][0], controls['hue'][2] = 0, 255
    if c == 11:
        controls.update(primary=[2304, 2200, 1900, 3000, 2700, 2048],
                        mid_contrast=2400, clip_trim=1800)
        controls['saturation'][1], controls['hue'][4] = 180, 200
    primaries = [[.68, .32], [.265, .690], [.150, .060], [.3127, .3290]] if case['gamut'] else ref.BT2020
    expected = ref.trim_rgb(case['rgb'], ref.decode_controls(controls, 1000, primaries))
    for got, want in zip(case['out'], expected):
        error = abs(ref.pq(max(0, got))-ref.pq(max(0, want)))
        assert error <= 2e-5, (case, expected, error)
        if not gpu and max(case['rgb']) == min(case['rgb']) and c not in [3, 7, 11]:
            assert abs(got-want) <= 1e-12, (case, expected)
print('PASS', len(cases), 'independent CM4 scalar samples, both target gamuts, 2e-5 PQ')
