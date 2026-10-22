"""Keep the opt-in Pascal build on one coherent proprietary R580 stack."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PascalPackages(unittest.TestCase):
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
