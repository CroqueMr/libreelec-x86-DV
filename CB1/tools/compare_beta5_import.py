#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare separate DMA-BUF validation/identity implementations without hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--baseline-build',type=Path,required=True)
    parser.add_argument('--candidate-build',type=Path,required=True)
    parser.add_argument('--negative-control',action='store_true')
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args()
    old=args.baseline.resolve()
    expected='43afd8b1f6504c45c7deb10d0c3f69e04a55fa9e9e0bb4c6d015f25215e2fa99'
    if old==ROOT or hashlib.sha256((old/'src/dvbridge_dmabuf.c').read_bytes()).hexdigest()!=expected:
        parser.error('Use frozen normal Beta5 DMA-BUF source')
    outputs=[]
    with tempfile.TemporaryDirectory(prefix='cb1-import-') as temp:
        for number,(source,build) in enumerate(((old,args.baseline_build),(ROOT,args.candidate_build))):
            flags=[]
            folder=build.resolve()/'tests/CMakeFiles/dmabuf_layout.dir'
            for line in (folder/'flags.make').read_text().splitlines():
                if line.startswith(('C_DEFINES =','C_INCLUDES =','C_FLAGS =')):
                    flags.extend(shlex.split(line.split('=',1)[1]))
            link=shlex.split((folder/'link.txt').read_text())
            if args.sanitize:
                flags.extend(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'])
            implementation=source/'src/dvbridge_dmabuf.c'
            if number and args.negative_control:
                implementation=Path(temp)/'mutated.c'
                implementation.write_text((source/'src/dvbridge_dmabuf.c').read_text().replace('DRM_FORMAT_RG1616','DRM_FORMAT_R8'))
            binary=Path(temp)/str(number)
            subprocess.run([link[0],*flags,'-UNDEBUG','-I'+str(source/'src'),
                '-DCB1_IMPORT_IMPLEMENTATION="'+str(implementation)+'"',str(ROOT/'tests/import_compatibility.c'),
                '-o',str(binary),*link[link.index('-o')+2:]],cwd=build.resolve()/'tests',check=True)
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
            outputs.append(subprocess.check_output([str(binary)],env=env))
    if outputs[0]!=outputs[1]:
        raise SystemExit('DMA-BUF decision/identity mismatch')
    print(json.dumps({'cases':24000,'bytes_compared':len(outputs[0]),'exact':True,'hardware_test':False},indent=2))


if __name__=='__main__':
    main()
