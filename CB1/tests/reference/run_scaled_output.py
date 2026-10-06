# SPDX-License-Identifier: MIT
"""Complete output check of independently frozen additional scaler fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import reference as R
from run_gpu_images import wire
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'scaled-output-vectors.json').read_text())
assert data['source_vectors_sha256']==hashlib.sha256((ROOT/'vectors.json').read_bytes()).hexdigest()
assert len(data['cases'])==3
failures=0
for case in data['cases']:
    result=subprocess.run([sys.argv[1]],input=wire(case),capture_output=True,text=True)
    print(case['id'],'exit',result.returncode,flush=True);print(result.stderr,end='')
    if result.returncode:
        failures+=1
        continue
    actual=json.loads(result.stdout)
    errors=[abs(a-b) for p,q in zip(actual['rgb'],case['expected']['rgb']) for a,b in zip(p,q)]
    index=max(range(len(errors)),key=errors.__getitem__);worst=errors[index]
    try:
        R.check_image_integrity(case,actual)
        if case['source_scaler_id']=='two-axis-upscale-overshoot':
            assert 0<max(actual['rgb'][28])<max(actual['rgb'][30])<max(actual['rgb'][35]),'near-black detail order'
    except AssertionError as error:
        failures+=1
        print('FAIL',error,'max PQ error',worst,'pixel',index//3,'component',index%3,
              'actual=',json.dumps(actual),flush=True)
        continue
    print('PASS unchanged complete-output PQ/code/black/hue budgets; max PQ error',worst,flush=True)
print('additional complete cases',len(data['cases']),'failures',failures,flush=True)
sys.exit(bool(failures))
