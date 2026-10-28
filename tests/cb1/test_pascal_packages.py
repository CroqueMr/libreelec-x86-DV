"""Keep the opt-in Pascal build on one coherent proprietary R580 stack."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PascalPackages(unittest.TestCase):
    def test_r580_build_stages_complete_private_transport(self):
        # A copied KAPI header without its new include, or a stale DRM modeset
        # owner, must fail before a packaged module can be called coherent.
        artifacts = {
            'src/nvidia-modeset/_out/Linux_x86_64/nv-modeset-kernel.o':
                'nvidia-modeset/nv-modeset-kernel.o_binary',
            'src/nvidia-modeset/kapi/interface/nvkms-kapi.h': 'common/inc/nvkms-kapi.h',
            'src/common/inc/nvkms-cb1-vsif.h': 'common/inc/nvkms-cb1-vsif.h',
            'src/common/inc/nvkms-cb1-hdr10plus.h': 'common/inc/nvkms-cb1-hdr10plus.h',
        }
        for name in ('connector.c', 'connector.h', 'drv.c', 'priv.h', 'modeset.c'):
            owner = 'nvidia-drm/nvidia-drm-' + name
            artifacts['kernel-open/' + owner] = owner
        for enabled in ('yes', 'no'):
            with self.subTest(pascal=enabled), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                public, payload = base/'public', base/'payload'
                kernel = payload/'kernel'
                for source, target in artifacts.items():
                    path = public/source
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(('native-r580:' + target).encode())
                    (kernel/target).parent.mkdir(parents=True, exist_ok=True)
                rm = kernel/'nvidia/nv-kernel.o_binary'
                rm.parent.mkdir()
                rm.write_bytes(b'unchanged-matched-proprietary-RM')
                result = subprocess.run(['bash', '-ec',
                    'VULKAN_SUPPORT=no; source "$1"; '
                    'get_build_dir(){ printf "%s" "$PUBLIC_SOURCE"; }; '
                    'kernel_path(){ printf "%s" /matched/kernel; }; '
                    'make(){ printf "%s\\n" "$@" >"$BUILD_CALL"; }; make_target',
                    'stage', str(ROOT/'packages/graphics/nvidia/package.mk')],
                    env=dict(os.environ, CB1_NVIDIA_PASCAL=enabled,
                        PKG_BUILD=str(payload), PUBLIC_SOURCE=str(public),
                        BUILD_CALL=str(base/'build-call'), CC='matched-cc', LD='matched-ld'),
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(rm.read_bytes(), b'unchanged-matched-proprietary-RM')
                for source, target in artifacts.items():
                    if enabled == 'yes':
                        self.assertTrue((kernel/target).is_file(), 'missing staged ' + target)
                        self.assertEqual((kernel/target).read_bytes(),
                                         ('native-r580:' + target).encode())
                    else:
                        self.assertFalse((kernel/target).exists())
                self.assertEqual((base/'build-call').exists(), enabled == 'yes')

    def test_recipe_selects_one_matched_module_stack(self):
        for enabled, version, dependency in (
            ('no', '615.78.08', 'nvidia-open-kernel-modules'),
            ('yes', '580.178.04', 'nvidia-pascal-modeset'),
        ):
            with self.subTest(pascal=enabled):
                result = subprocess.run(['bash', '-ec',
                    'VULKAN_SUPPORT=no; source "$1"; '
                    'printf "%s\\n%s\\n%s\\n" "$PKG_VERSION" "$PKG_DEPENDS_TARGET" "$PKG_URL"',
                    'recipe', str(ROOT/'packages/graphics/nvidia/package.mk')],
                    env=dict(os.environ, CB1_NVIDIA_PASCAL=enabled),
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                actual, dependencies, url = result.stdout.splitlines()
                self.assertEqual(actual, version)
                self.assertIn(dependency, dependencies.split())
                excluded = ('nvidia-pascal-modeset' if enabled == 'no'
                            else 'nvidia-open-kernel-modules')
                self.assertNotIn(excluded, dependencies.split())
                self.assertTrue(url.endswith('/'+version+'/NVIDIA-Linux-x86_64-'+version+'-no-compat32.run'))

    def test_r580_runtime_install_keeps_modules_and_needs_no_ucodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); payload=base/'payload'; payload.mkdir()
            (payload/'firmware').mkdir(); (payload/'kernel').mkdir()
            (base/'licenses').mkdir()
            version='580.178.04'
            names=['10_nvidia.json','10_nvidia_wayland.json','15_nvidia_gbm.json',
                'libnvidia-egl-wayland.so.1.1.20','libnvidia-egl-gbm.so.1.1.3',
                'nvidia-smi','nvidia-application-profiles-'+version+'-rc',
                'firmware/gsp_test.bin']
            names += [n+'.'+version for n in ('libnvidia-allocator.so','libEGL_nvidia.so',
                'libnvidia-eglcore.so','libnvidia-glsi.so','libGLESv2_nvidia.so','libcuda.so',
                'libnvcuvid.so','libnvidia-gpucomp.so','libnvidia-tls.so','libnvidia-ml.so')]
            modules=('nvidia','nvidia-modeset','nvidia-drm','nvidia-uvm')
            names += ['kernel/'+n+'.ko' for n in modules]
            for name in names: (payload/name).write_bytes(('fixture:'+name).encode())
            (payload/'LICENSE').write_bytes(b'fixture-license')
            (base/'licenses/LicenseRef-NVIDIA-Driver-License-Agreement.txt').write_bytes(b'fixture-license')
            result=subprocess.run(['bash','-ec',
                'VULKAN_SUPPORT=no; source "$1"; '
                'get_full_firmware_dir(){ echo usr/lib/firmware; }; '
                'get_full_module_dir(){ echo usr/lib/modules/test; }; '
                'die(){ echo "$*" >&2; exit 1; }; cd "$2"; makeinstall_target',
                'install',str(ROOT/'packages/graphics/nvidia/package.mk'),str(payload)],
                env=dict(os.environ,CB1_NVIDIA_PASCAL='yes',ROOT=str(base),INSTALL=str(base/'install')),
                text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for module in modules:
                self.assertEqual((base/'install/usr/lib/modules/test/nvidia'/ (module+'.ko')).read_bytes(),
                                 (payload/'kernel'/ (module+'.ko')).read_bytes())
            self.assertTrue((base/'install/usr/lib/libnvcuvid.so.1').is_symlink())
            self.assertTrue((base/'install/usr/lib/libEGL_nvidia.so.0').is_symlink())


if __name__ == '__main__':
    unittest.main()
