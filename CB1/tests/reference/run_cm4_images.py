# SPDX-License-Identifier: GPL-3.0-only
"""Compare the independent native reference graph with pre-candidate fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import cm4_reference as ref
from cm4_reference import pq


def main():
    if len(sys.argv) > 2:
        return full()
    result = subprocess.run([sys.argv[1]], check=True, text=True, capture_output=True)
    print(result.stderr, end='', file=sys.stderr)
    actual = json.loads(result.stdout)
    expected = json.loads(Path(__file__).with_name('cm4-native-vectors.json').read_text())
    assert actual['algorithm'] == expected['algorithm']
    assert actual['size'] == expected['size'] == [8, 8]
    assert actual['unit_nits'] == expected['unit_nits'] == 203
    assert len(actual['native']) == len(expected['native']) == 6
    for got, wanted in zip(actual['native'], expected['native']):
        assert (got['gamut'], got['detail']) == (wanted['gamut'], wanted['detail'])
        assert len(got['linear']) == len(wanted['linear']) == 64
        error = max(abs(pq(max(0, a*203))-pq(max(0, b*203)))
                    for rgb, reference in zip(got['linear'], wanted['linear'])
                    for a, b in zip(rgb, reference))
        assert error <= 2e-5, (got['gamut'], got['detail'], error)
    print('PASS frozen native base/detail graph, six FP32 reference rasters')


def full():
    if sys.argv[2] == '--spatial-numeric':
        return spatial()
    colour = sys.argv[2] == '--full-colour'
    result = subprocess.run([sys.argv[1], sys.argv[2]], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)['full']
    assert len(data) == 22
    fixture = 'cm4-colour-vectors.json' if colour else 'cm4-envelope-vectors.json'
    native = json.loads(Path(__file__).with_name(fixture).read_text())['native']
    maximum, all_errors, worst, per_control = 0, [], None, {}
    for case in data:
        c = case['control']
        controls = dict(primary=[2048]*6, mid_contrast=2048, clip_trim=2048,
                        saturation=[128]*6, hue=[128]*6)
        if 0 < c < 6:
            controls['primary'][c-1] = 3072
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
        prim = [[.68, .32], [.265, .690], [.150, .060], [.3127, .3290]] if case['gamut'] else ref.BT2020
        coeff = ref.decode_controls(controls, 1000, prim)
        before = native[case['gamut']]['linear']
        assert len(case['pq']) == len(before) == 64
        linear = [[0.0]*3 if i % 8 == 0 else [v*203 for v in rgb] for i, rgb in enumerate(before)]
        expected = [ref.trim_rgb(rgb, coeff) for rgb in linear]
        if colour:
            payload = str(case['gamut'])+'\n'+'\n'.join(' '.join(map(str, rgb)) for rgb in expected)
            finish = subprocess.run([sys.argv[1], '--gamut-oracle'], input=payload, text=True, capture_output=True)
            assert finish.returncode == 0, finish.stderr
            expected_pq = json.loads(finish.stdout)['pq']
        else:
            expected_pq = [[pq(max(0, v)) for v in rgb] for rgb in expected]
        for index, (actual, wanted) in enumerate(zip(case['pq'], expected_pq)):
            # Exact signal black precedes authored offsets in the complete policy.
            errors = [abs(a-v) for a, v in zip(actual, wanted)]
            if colour and index % 8 == 0 and coeff['sop'][1] <= 0:
                errors = [abs(a) for a in actual]
            if max(errors) > maximum:
                maximum = max(errors)
                worst = dict(control=c, gamut=case['gamut'], pixel=index,
                             input=linear[index], actual=actual, expected_pq=wanted)
            all_errors.extend(errors)
            key = (case['gamut'], c)
            per_control[key] = max(per_control.get(key, 0), max(errors))
    if maximum > 1e-3:
        print('Per-gamut/control maximum PQ:', per_control, file=sys.stderr)
    assert maximum <= 1e-3, (maximum, worst)
    p999 = sorted(all_errors)[int((len(all_errors)-1)*.999)]
    assert p999 <= 2.5e-4, p999
    print('PASS complete CM4 gray rasters against frozen native base, max PQ', maximum, 'p99.9', p999)


def spatial():
    result = subprocess.run([sys.argv[1], '--spatial-numeric'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)['spatial']
    assert len(data) == 16
    errors, worst = [], None
    for case in data:
        controls = dict(primary=[2048]*6, mid_contrast=2048, clip_trim=2048,
                        saturation=[128]*6, hue=[128]*6)
        if case['control'] == 11:
            controls.update(primary=[2304, 2200, 1900, 3000, 2700, 2048],
                            mid_contrast=2400, clip_trim=1800)
            controls['saturation'][1], controls['hue'][4] = 180, 200
        controls['primary'][5] = case['ms']
        prim = [[.68, .32], [.265, .690], [.150, .060], [.3127, .3290]] if case['gamut'] else ref.BT2020
        coeff = ref.decode_controls(controls, 1000, prim)
        linear = [[v*203 for v in rgb] for rgb in case['native']]
        expected = [ref.trim_rgb(rgb, coeff) for rgb in linear]
        payload = str(case['gamut'])+'\n'+'\n'.join(' '.join(map(str, rgb)) for rgb in expected)
        finish = subprocess.run([sys.argv[1], '--gamut-oracle'], input=payload, text=True, capture_output=True)
        assert finish.returncode == 0, finish.stderr
        pq = json.loads(finish.stdout)['pq']
        for i, (actual, wanted) in enumerate(zip(case['pq'], pq)):
            x, y = i % 8, i // 8
            if (case['border'] and (x in (0, 7) or y in (0, 7))) or (x == 0 and coeff['sop'][1] <= 0):
                wanted = [0, 0, 0]
            e = [abs(a-b) for a, b in zip(actual, wanted)]
            if not errors or max(e) > max(errors):
                worst = (case['gamut'], case['control'], case['ms'], case['border'], i, actual, wanted)
            errors.extend(e)
    maximum = max(errors)
    p999 = sorted(errors)[int((len(errors)-1)*.999)]
    assert maximum <= 1e-3, (maximum, worst)
    assert p999 <= 2.5e-4, (p999, worst)
    print('PASS signed CM4 detail and combined controls, max PQ', maximum, 'p99.9', p999)


if __name__ == '__main__':
    main()
