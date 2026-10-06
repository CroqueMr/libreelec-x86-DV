# SPDX-License-Identifier: MIT
"""Feed immutable frozen inputs to the compiled renderer, check frozen GPU budget."""
import json
from pathlib import Path
import subprocess
import sys
import reference as R

ROOT = Path(__file__).resolve().parent

def wire(case):
    v = case['input']
    sw, sh = v['size']
    dw, dh = v.get('output_size', v['size'])
    l1 = v['l1'][0]
    l6 = v.get('l6', [])
    active = v.get('active', [0, 0, dw, dh])
    offsets = [active[0]*sw/dw, (dw-active[2])*sw/dw,
               active[1]*sh/dh, (dh-active[3])*sh/dh]
    assert all(x.is_integer() for x in offsets), 'source L5 not exactly encodable'
    header = [sw, sh, dw, dh, v['peak'], {'BT709': 1, 'P3-D65': 2, 'BT2020': 3}[v['gamut']],
              v.get('bits', 10), int(v.get('limited', True)), int(v.get('flip_y', False)),
              int(v.get('fel', False)), 40 if v.get('generation') == 'CM4' else 29,
              len(l6), l6[0]['min'] if l6 else 0, l6[0]['max'] if l6 else 0,
              v['source_min_pq'], v['source_max_pq'], l1['min'], l1['avg'], l1['max']]
    numbers = header + [int(x) for x in offsets]
    for c in range(3):
        numbers.extend([v.get('offset', [512]*3)[c], v.get('slope', [1]*3)[c], v.get('threshold', [0]*3)[c]])
    for index, pixel in enumerate(v['rgb']):
        numbers.extend(pixel + v.get('el', [[512]*3 for _ in v['rgb']])[index])
    overlays = v.get('overlays', [])
    numbers.append(len(overlays))
    for overlay in overlays:
        numbers.extend([overlay['index'], overlay['alpha'], *overlay['rgb']])
    return ' '.join(map(str, numbers)) + '\n'

def main():
    vectors = json.loads((ROOT/'vectors.json').read_text())
    cases = [c for c in vectors['image_cases'] if c['mode'] == 'Reference Expert' and 'codes' in c['expected']]
    assert len(cases) == 19
    if len(sys.argv)>2:
        cases=[c for c in cases if c['id']==sys.argv[2]]
        assert len(cases)==1
    failed = 0
    for case in cases:
        result = subprocess.run([sys.argv[1], *sys.argv[3:]], input=wire(case), capture_output=True, text=True)
        print(case['id'], 'exit', result.returncode, flush=True)
        print(result.stderr, end='')
        if result.returncode:
            failed += 1
            continue
        if sys.argv[3:] and sys.argv[3].startswith('library-source-image'):
            print('PASS exact NATIVE zero sample, no image qualification',flush=True)
            continue
        actual = json.loads(result.stdout)
        try:
            R.check_image_integrity(case, actual)
        except AssertionError as error:
            errors=[abs(a-b) for p,q in zip(actual['rgb'],case['expected']['rgb']) for a,b in zip(p,q)]
            worst=max(range(len(errors)),key=errors.__getitem__)
            print('FAIL:', error, 'max PQ error',errors[worst],'pixel',worst//3,'component',worst%3,
                  'actual=', json.dumps(actual), flush=True)
            failed += 1
        else:
            maximum = max(abs(a-b) for p,q in zip(actual['rgb'],case['expected']['rgb']) for a,b in zip(p,q))
            print('PASS frozen GPU budget, max PQ error', maximum, flush=True)
    print('compiled image cases', len(cases), 'failures', failed, flush=True)
    return bool(failed)

if __name__ == '__main__':
    sys.exit(main())
