"""Check the actual NVKMS x86 compiler contract, not a recipe string."""
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_nvidia_native_hdr as native_hdr


class NvidiaReturnThunk(unittest.TestCase):
    sources = native_hdr.NvidiaNativeHdr.sources

    def test_native_core_uses_the_target_kernel_return_thunk(self):
        for root in self.sources():
            cwd = root/'src/nvidia-modeset'
            with self.subTest(stack=str(root)), tempfile.TemporaryDirectory() as tmp:
                flags = subprocess.run(['make','-s','TARGET_ARCH=x86_64',
                    'OUTPUTDIR='+tmp,'CC=cc','__cb1_flags',
                    '--eval=__cb1_flags:; @printf "%s\\n" "$(CFLAGS)"'],
                    cwd=cwd,capture_output=True,text=True)
                self.assertEqual(flags.returncode,0,flags.stderr)
                src,obj = Path(tmp)/'check.c',Path(tmp)/'check.o'
                src.write_text('unsigned cb1_return(unsigned x) { return x+1; }\n')
                build = subprocess.run(['cc',*shlex.split(flags.stdout),'-c',str(src),'-o',str(obj)],
                                       cwd=cwd,capture_output=True,text=True)
                self.assertEqual(build.returncode,0,build.stderr)
                symbols = subprocess.run(['nm','-u',str(obj)],capture_output=True,text=True,check=True).stdout
                self.assertIn('__x86_return_thunk',symbols)


if __name__ == '__main__': unittest.main()
