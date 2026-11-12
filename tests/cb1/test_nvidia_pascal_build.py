"""Exercise the R580 source handoff without compiling or loading a GPU driver."""
from pathlib import Path
import os
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
DRM = ['nvidia-drm-'+name for name in ('connector.c', 'connector.h', 'drv.c',
       'priv.h', 'modeset.c', 'encoder.c', 'encoder.h')]


class PascalBuild(unittest.TestCase):
    def build(self, mismatch=False, retry=False):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            public, closed = base/'public', base/'closed'
            archive = base/'sources/nvidia-pascal-modeset/nvidia-pascal-modeset-test.tar.gz'
            pristine = base/'pristine/kernel-open'
            files = ['nvidia-drm/'+name for name in DRM] + ['common/inc/nvkms-kapi.h']
            for name in files:
                for root, data in ((pristine, b'vendor'), (closed/'kernel', b'vendor'),
                                   (public/'kernel-open', b'patched')):
                    path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            (closed/'kernel/nvidia-drm/nvidia-drm-linux.c').write_bytes(b'closed-flavour-license')
            for name in ('nvkms-cb1-vsif.h', 'nvkms-cb1-hdr10plus.h', 'nvkms-dv-vsif.h'):
                path = public/'src/common/inc'/name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'private-header')
            path = public/'src/nvidia-modeset/kapi/interface/nvkms-kapi.h'
            path.parent.mkdir(parents=True); path.write_bytes(b'authoritative-kapi')
            core = 'src/nvidia-modeset/_out/Linux_x86_64/nv-modeset-kernel.o'
            path = public/core; path.parent.mkdir(parents=True); path.write_bytes(b'rebuilt-core')
            path = closed/'kernel/nvidia-modeset/nv-modeset-kernel.o_binary'
            path.parent.mkdir(parents=True); path.write_bytes(b'original-core')
            archive.parent.mkdir(parents=True)
            with tarfile.open(archive, 'w:gz') as out:
                out.add(pristine, arcname='open-gpu-kernel-modules-commit/kernel-open')
            if mismatch:
                (closed/'kernel/nvidia-drm/nvidia-drm-encoder.c').write_bytes(b'wrong-release')
            command = ['bash', '-ec',
                'source "$1"; NVIDIA_BRANCH=r580; PKG_VERSION=test; '
                'get_build_dir(){ printf "%s" "$PUBLIC"; }; '
                'get_pkg_version(){ printf test; }; get_pkg_variable(){ printf commit; }; '
                'kernel_path(){ printf unused; }; die(){ echo "$*" >&2; exit 1; }; '
                'make(){ :; }; cd "$PKG_BUILD"; make_target',
                'build', str(ROOT/'packages/graphics/nvidia/common.mk')]
            environment = dict(os.environ, PUBLIC=str(public), PKG_BUILD=str(closed), SOURCES=str(base/'sources'))
            result = subprocess.run(command, env=environment, capture_output=True, text=True)
            if retry:
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run(command, env=environment, capture_output=True, text=True)
            if mismatch:
                self.assertNotEqual(result.returncode, 0, 'mixed source releases must be rejected')
                self.assertIn('mismatch', result.stderr.lower())
                self.assertEqual((closed/'kernel/nvidia-modeset/nv-modeset-kernel.o_binary').read_bytes(), b'original-core')
                self.assertEqual((closed/'kernel/nvidia-drm/nvidia-drm-connector.c').read_bytes(), b'vendor')
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((closed/'kernel/nvidia-modeset/nv-modeset-kernel.o_binary').read_bytes(), b'rebuilt-core')
                for name in files:
                    self.assertEqual((closed/'kernel'/name).read_bytes(),
                                     b'authoritative-kapi' if name == 'common/inc/nvkms-kapi.h' else b'patched')
                self.assertEqual((closed/'kernel/nvidia-drm/nvidia-drm-linux.c').read_bytes(), b'closed-flavour-license')

    def test_matched_source_handoff_preserves_the_closed_module_flavour(self):
        self.build()

    def test_mismatched_drm_sources_fail_before_replacing_the_vendor_core(self):
        self.build(mismatch=True)

    def test_retry_accepts_the_same_already_patched_sources(self):
        self.build(retry=True)


if __name__ == '__main__':
    unittest.main()
