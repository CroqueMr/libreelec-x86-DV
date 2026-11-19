#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare compatible creative operations with the separately compiled normal Beta5 oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = {
    'dvbridge_creative.c': '012be30409c5009218f510098e8911fc6c7f947f66fddebdf8d1b40450aabd3a',
    'dvbridge_creative.h': '5ae44af7af239049542825c6b7e80d8671a2ac43b49c1a9eb70750981985763b',
    'dvbridge_metadata.h': 'e75d7210b2c605aed52df28bc1b42413b83e261e264de634025cd8a682f1d66d',
    'dvbridge_metadata_bounds.h': '445b9be0a4634faf57f33efa866133061e7f3eee98f8a650224383de48cbad25',
    'mpv_dvbridge_cm4.h': 'f6762808f5d7a5824983d72b0188098f19e86bd2a6db7b997ef63e2d35612661',
}
ALIASES = {
    'resolve': 'resolve', 'scene_weight': 'scene', 'trim_rgb': 'trim', 'cm4_coefficients': 'coefficients',
    'cm4_apply': 'apply', 'cm4_trim_rgb': 'cm4_trim', 'enhanced_source': 'source',
    'enhanced_source_b': 'source_b', 'edit': 'edit',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path, help='Frozen normal Beta5 CB1 directory')
    parser.add_argument('--ffmpeg-prefix', required=True, type=Path)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    old = args.baseline.resolve()/'src'
    if old == ROOT/'src':
        parser.error('Baseline must be separately frozen')
    for name, expected in BASELINE.items():
        if hashlib.sha256((old/name).read_bytes()).hexdigest() != expected:
            parser.error('Baseline does not match normal Beta5: '+name)
    cc = shlex.split(os.environ.get('CC', 'cc'))
    pkg = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'libplacebo']).decode())
    flags = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation', '-UNDEBUG',
             '-I'+str(args.ffmpeg_prefix/'include')]
    if args.sanitize:
        flags += ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    with tempfile.TemporaryDirectory(prefix='cb1-creative-') as temp:
        oracle = Path(temp)/'oracle.o'
        subprocess.run([*cc, *flags, '-I'+str(old),
                        *['-Ddvbridge_creative_'+name+'=beta5_'+alias for name, alias in ALIASES.items()],
                        '-c', str(old/'dvbridge_creative.c'), *pkg, '-o', str(oracle)], check=True)
        binary = Path(temp)/'compare'
        subprocess.run([*cc, *flags, '-I'+str(ROOT/'src'), str(ROOT/'tests/creative_compatibility.c'),
                        str(ROOT/'src/dvbridge_creative.c'), str(ROOT/'src/dvbridge_policy.c'), str(oracle),
                        str(args.ffmpeg_prefix/'lib/libavutil.a'), *pkg, '-lm', '-latomic', '-o', str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
        output = subprocess.check_output([str(binary)], env=env)
    print(json.dumps(json.loads(output), indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run the comparison without Python -O')
    main()
