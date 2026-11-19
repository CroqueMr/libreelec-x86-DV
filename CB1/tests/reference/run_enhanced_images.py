# SPDX-License-Identifier: MIT
"""Compare actual Enhanced HDR10 images to pre-runtime independent C vectors."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import reference as R
from run_gpu_images import wire

def main():
    vectors = json.loads((Path(__file__).parent/'vectors.json').read_text())
    cases = [c for c in vectors['image_cases'] if c['mode'] == 'Enhanced HDR10' and 'codes' in c['expected']]
    assert len(cases) == 36
    # The accepted independent neutral-FEL controls prove the projection seam.
    for pair in vectors['dv_cases']:
        if not pair['id'].startswith('dv-neutral-output-'):
            continue
        case = copy.deepcopy(pair)
        case['input'] = pair['input']['image_input']
        case['input'].update(bits=10, limited=True)
        rgb = pair['expected']['rgb']
        case['expected'] = dict(rgb=rgb, codes=[[math.floor(64+876*x+.5) for x in p] for p in rgb])
        cases.append(case)
    assert len(cases) == 48
    failed = 0
    for case in cases:
        result = subprocess.run([sys.argv[1], case['input']['preset']], input=wire(case), capture_output=True, text=True)
        print(case['id'], 'exit', result.returncode, flush=True)
        print(result.stderr, end='')
        if result.returncode:
            failed += 1
            continue
        actual = json.loads(result.stdout)
        try:
            R.check_image_integrity(case, actual)
        except AssertionError as error:
            print('FAIL', error, 'actual', json.dumps(actual), flush=True)
            failed += 1
        else:
            maximum = max(abs(a-b) for p,q in zip(actual['rgb'],case['expected']['rgb']) for a,b in zip(p,q))
            print('PASS unchanged GPU budget, max PQ error', maximum, flush=True)
    print('Enhanced HDR10 compiled images', len(cases), 'failures', failed, flush=True)
    return bool(failed)

if __name__ == '__main__':
    sys.exit(main())
