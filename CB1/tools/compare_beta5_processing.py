#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare complete processing outputs using separately selected modified libraries."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-build',type=Path,required=True)
    parser.add_argument('--candidate-build',type=Path,required=True)
    parser.add_argument('--baseline-library',type=Path,required=True)
    parser.add_argument('--candidate-library',type=Path,required=True)
    parser.add_argument('--negative-control',action='store_true')
    args=parser.parse_args()
    outputs=[]
    with tempfile.TemporaryDirectory(prefix='cb1-processing-') as temp:
        for number,(build,library) in enumerate(((args.baseline_build,args.baseline_library),
                                               (args.candidate_build,args.candidate_library))):
            build=build.resolve();library=library.resolve()
            folder=build/'tests/CMakeFiles/scaled_adaptive.dir'
            flags=[]
            for line in (folder/'flags.make').read_text().splitlines():
                if line.startswith(('C_DEFINES =','C_INCLUDES =','C_FLAGS =')):
                    flags.extend(shlex.split(line.split('=',1)[1]))
            link=shlex.split((folder/'link.txt').read_text())
            binary=Path(temp)/str(number)
            command=[link[0],*flags,'-UNDEBUG','-I'+str(ROOT/'tests'),str(ROOT/'tests/processing_compatibility.c')]
            if number and args.negative_control:command.append('-DCB1_MUTATE_LOOKUP=1')
            libraries=[str(library) if Path(arg).name.startswith('libplacebo.so') else arg
                       for arg in link[link.index('-o')+2:]]
            subprocess.run([*command,'-o',str(binary),*libraries],cwd=build/'tests',check=True)
            env=dict(os.environ,EGL_PLATFORM='surfaceless',LIBGL_ALWAYS_SOFTWARE='1',GALLIUM_DRIVER='llvmpipe',
                CB1_REFERENCE_TRACE='1',LD_LIBRARY_PATH=str(library.parent)+':'+os.environ.get('LD_LIBRARY_PATH',''))
            run=subprocess.run([str(binary)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
            print(run.stderr.decode(errors='replace'),file=sys.stderr)
            if run.returncode or b'Validation failed:' in run.stderr:
                raise SystemExit('Processing capture failed or GPU validation error')
            outputs.append(run.stdout)
    if not outputs[0] or outputs[0]!=outputs[1]:raise SystemExit('Processing output mismatch')
    print(json.dumps({'records':48,'bytes_compared':len(outputs[0]),'exact':True,'hardware_test':False},indent=2))


if __name__=='__main__':main()
