# SPDX-License-Identifier: MIT
"""Exposed-PQ checks of unchanged frozen two-axis source-scaler controls."""
import json
from pathlib import Path
import subprocess
import sys
from run_source_images import exposed_pq

def main():
    data=json.loads((Path(__file__).resolve().parent/'vectors.json').read_text())
    cases=[c for c in data['scaler_cases'] if c.get('id') in
           ('two-axis-upscale-overshoot','mixed-axis-downscale-precedence','mixed-axis-exact-black')]
    assert len(cases)==3
    for case in cases:
        numbers=[*case['input_size'],*case['output_size']]
        numbers.extend(exposed_pq(x) for pixel in case['input'] for x in pixel)
        result=subprocess.run([sys.argv[1]],input=' '.join(map(str,numbers))+'\n',capture_output=True,text=True)
        print(case['id'],'exit',result.returncode,flush=True);print(result.stderr,end='')
        assert result.returncode==0
        # Inverse of the test-only observation transport, before comparison.
        # This protects >1 source PQ from the renderer's final RGB swizzle;
        # no expected value/operator/budget is adjusted.
        actual=[[2*(x-.25) for x in pixel] for pixel in json.loads(result.stdout)['rgb']]
        expected=case['sampled']
        assert len(actual)==len(expected)
        worst=max(abs(a-exposed_pq(b)) for p,q in zip(actual,expected) for a,b in zip(p,q))
        assert worst<=1/65535,(case['id'],worst,actual)
        if case['id']=='two-axis-upscale-overshoot':
            assert any(x>1 for pixel in actual for x in pixel),'PQ >1 must not be clipped'
        print('PASS existing two-axis operator, separate PQ coverage max error',worst,flush=True)
    return 0

if __name__=='__main__':sys.exit(main())
