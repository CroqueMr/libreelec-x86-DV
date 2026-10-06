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
    assert len(cases)==10
    accepted=0
    for case in cases:
        assert case['status'] in (2,3),case
        accepted+=1
        peak=ref.eotf(3079/4095)
        original=ref.decode_controls({'primary':[2048]*6},peak,ref.BT2020)
        candidate=ref.decode_controls({'primary':case['words']+[2048]},peak,ref.BT2020)
        reference=math.floor(ref.pq(max(1000,case['peak']))*4095+.5)
        headroom=ref.clamp((reference-case['master_q'])/case['master_q'],-.5,.5)
        preset='Signature' if case['preset'] else 'Natural'
        for i in range(33):
            rgb=[ref.eotf(i/32*ref.pq(peak))]*3
            goal=ref.enhanced_objective(ref.trim_rgb(rgb,original),peak,headroom,case['scene'],preset)
            actual=ref.trim_rgb(rgb,candidate)
            assert abs(ref.pq(actual[0])-ref.pq(goal[0]))<=2/1024,(case,i,actual,goal)
        for vertex in ref.VERTICES:
            for intensity in [.1,.5,.9]:
                rgb=[v*ref.eotf(intensity*ref.pq(peak)) for v in vertex]
                goal=ref.enhanced_objective(ref.trim_rgb(rgb,original),peak,headroom,case['scene'],preset)
                a=ref.to_ipt(ref.trim_rgb(rgb,candidate),candidate)
                b=ref.to_ipt(goal,original)
                ca,cb=math.hypot(*a[1:]),math.hypot(*b[1:])
                if cb<=1e-7:
                    assert ca<=1e-7
                else:
                    assert abs(ca-cb)/cb<=.02,(case,ca,cb)
                    angle=abs(math.remainder(math.atan2(a[2],a[1])-math.atan2(b[2],b[1]),2*math.pi))
                    assert math.degrees(angle)<=.5,(case,angle)
    assert accepted==10
    authored=json.loads(subprocess.run([sys.argv[1],'--authored-json'],capture_output=True,
        text=True,check=True).stdout)
    source={'primary':[2304,2048,1900,2300,2100,2048], 'mid_contrast':2300,'clip_trim':2048,
        'saturation':[140,128,120,135,125,128],'hue':[130,128,126,129,127,128]}
    peak=ref.eotf(3079/4095)
    original=ref.decode_controls(source,peak,ref.BT2020)
    candidate=ref.decode_controls(dict(source,primary=authored['primary']),peak,ref.BT2020)
    assert len(authored['samples'])==38
    for sample in authored['samples']:
        actual=ref.trim_rgb(sample['rgb'],candidate)
        wanted=ref.enhanced_objective(ref.trim_rgb(sample['rgb'],original),peak,0,1,'Signature')
        for got,verified,expected in zip(sample['out'],actual,wanted):
            assert abs(ref.pq(max(0,got))-ref.pq(max(0,verified)))<=2e-5
            assert abs(ref.pq(max(0,got))-ref.pq(max(0,expected)))<=2/1024,(sample['rgb'],got,expected)
        a,b=ref.to_ipt(actual,candidate),ref.to_ipt(wanted,original)
        ca,cb=math.hypot(*a[1:]),math.hypot(*b[1:])
        if cb<=1e-7:
            assert ca<=1e-7
        else:
            assert abs(ca-cb)/cb<=.02
            angle=abs(math.remainder(math.atan2(a[2],a[1])-math.atan2(b[2],b[1]),2*math.pi))
            assert math.degrees(angle)<=.5
    print('PASS independent quantized fit bounds;',accepted,'accepted of',len(cases),'reported cases')
    print('PASS authored Signature/custom target; 38 independent preserved-control samples')
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
