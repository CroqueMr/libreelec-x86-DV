#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare the complete canonical tunnel against a separately frozen Beta5 packer."""
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
    'dvbridge_gl_pack.c': '26754ea4f1298f521eabc3594b7d28c80da12f4fc13f3c1c83058c257068be63',
    'dvbridge_gl_pack.h': '29e7800616662210fd71776263b6c63bcc8502b7f7910851805ceb3a42e6b6ba',
    'pack_gles300.frag': 'f05e4f3b27945cb8c53b2f9948d53cec28006f8053bcdd4d4bc89693120346a7',
    'pack_gles300.vert': '55662e6ebfd1bdef5539f2aac80db7771b1521b980e52be2f348f6340c148311',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path, help='Frozen normal Beta5 CB1 directory')
    args = parser.parse_args()
    old = args.baseline.resolve()/'src'
    if old == ROOT/'src':
        parser.error('Baseline must be separately frozen')
    for name, expected in BASELINE.items():
        if hashlib.sha256((old/name).read_bytes()).hexdigest() != expected:
            parser.error('Baseline does not match normal Beta5: '+name)
    cc = shlex.split(os.environ.get('CC', 'cc'))
    flags = ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    new = ROOT/'src'
    with tempfile.TemporaryDirectory(prefix='cb1-tunnel-') as temp:
        oracle = Path(temp)/'oracle.o'
        aliases = {'dvbridge_gl_packer_create': 'beta5_create', 'dvbridge_gl_packer_destroy': 'beta5_destroy',
                   'dvbridge_gl_pack': 'beta5_pack', 'dvbridge_gl_patch': 'beta5_patch',
                   'dvbridge_gl_patch_inplace': 'beta5_inplace'}
        subprocess.run([*cc, *flags, '-I'+str(old), *['-D'+k+'='+v for k, v in aliases.items()],
                        '-c', str(old/'dvbridge_gl_pack.c'), '-o', str(oracle)], check=True)
        binary = Path(temp)/'compare'
        subprocess.run([*cc, *flags, '-I'+str(new), str(ROOT/'tests/tunnel_compatibility.c'),
                        str(new/'dvbridge_gl_pack.c'), str(oracle), '-lEGL', '-lGLESv2', '-o', str(binary)], check=True)
        env = dict(os.environ, EGL_PLATFORM='surfaceless', LIBGL_ALWAYS_SOFTWARE='1', GALLIUM_DRIVER='llvmpipe')
        output = subprocess.check_output([str(binary), str(old/'pack_gles300.vert'), str(old/'pack_gles300.frag'),
                                          str(new/'pack_gles300.vert'), str(new/'pack_gles300.frag')], env=env)
    print(json.dumps(json.loads(output), indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run the comparison without Python -O')
    main()
