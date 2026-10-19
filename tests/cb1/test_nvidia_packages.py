"""NVIDIA recipe contracts and installed runtime payloads."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NvidiaPackages(unittest.TestCase):
    def recipe(self, relative, commands):
        return subprocess.run(['bash', '-c', 'VULKAN_SUPPORT=no; source "$1"; ' + commands,
                               'recipe', str(ROOT / relative)], text=True, capture_output=True)

    def test_matched_driver_and_open_modules(self):
        result = self.recipe('packages/graphics/nvidia/package.mk',
                             'printf "%s\\n%s\\n%s\\n" "$PKG_VERSION" "$PKG_DEPENDS_TARGET" "$PKG_BUILD_FLAGS"')
        self.assertEqual(result.returncode, 0, result.stderr)
        version, deps, flags = result.stdout.splitlines()
        self.assertEqual(version, '615.78.08')
        self.assertIn('nvidia-open-kernel-modules', deps.split())
        self.assertIn('-strip', flags.split())
        modules = self.recipe('packages/graphics/nvidia-open-kernel-modules/package.mk',
                              'printf "%s\\n%s\\n" "$PKG_VERSION" "$PKG_COMMIT"')
        self.assertEqual(modules.returncode, 0, modules.stderr)
        self.assertEqual(modules.stdout.splitlines(),
                         [version, '1a82fbfda8f321b056eb3568850f9316c5e465c5'])

    def test_dual_decoder_bridge_revision(self):
        result = self.recipe('packages/multimedia/nvidia-vaapi-driver/package.mk',
                             'printf "%s" "$PKG_VERSION"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '443050726fdb30888a2ced1cea1c5d036ea3b15c')

    def test_runtime_install_keeps_firmware_and_license(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload, installed = base / 'payload', base / 'installed'
            payload.mkdir(); installed.mkdir()
            recipe = ROOT / 'packages/graphics/nvidia/package.mk'
            # Missing payloads deliberately make the real installation fail.
            # A complete manifest supplies every copied file without executing vendor code.
            files = ['10_nvidia.json', '10_nvidia_wayland.json', '15_nvidia_gbm.json',
                     'libnvidia-egl-wayland.so.1.1.20', 'libnvidia-egl-gbm.so.1.1.3',
                     'nvidia-smi', 'nvidia-application-profiles-615.78.08-rc']
            files += [name + '.615.78.08' for name in
                      ('libnvidia-allocator.so', 'libEGL_nvidia.so', 'libnvidia-eglcore.so',
                       'libnvidia-glsi.so', 'libGLESv2_nvidia.so', 'libcuda.so',
                       'libnvcuvid.so', 'libnvidia-gpucomp.so', 'libnvidia-tls.so', 'libnvidia-ml.so')]
            for name in files:
                if '/' not in name:
                    (payload / name.replace('${PKG_VERSION}', '615.78.08')).touch()
            (payload / 'firmware').mkdir()
            for name in ('gsp_test.bin', 'ucodes_test.bin'):
                (payload / 'firmware' / name).write_bytes(b'firmware')
            (payload / 'LICENSE').write_bytes(b'test-license')
            (base / 'licenses').mkdir()
            (base / 'licenses/LicenseRef-NVIDIA-Driver-License-Agreement.txt').write_bytes(b'test-license')
            env = dict(os.environ, INSTALL=str(installed), ROOT=str(base))
            result = subprocess.run(['bash', '-ec',
                'VULKAN_SUPPORT=no; source "$1"; '
                'get_full_firmware_dir() { echo usr/lib/firmware; }; '
                'get_full_module_dir() { echo usr/lib/modules/test; }; '
                'die() { echo "$*" >&2; exit 1; }; cd "$2"; makeinstall_target',
                'install', str(recipe), str(payload)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((installed / 'usr/share/licenses/nvidia/LICENSE').read_bytes(), b'test-license')
            self.assertTrue((installed / 'usr/lib/firmware/nvidia/615.78.08/ucodes_test.bin').is_file())
            self.assertTrue((installed / 'usr/lib/libnvcuvid.so.1').is_symlink())


if __name__ == '__main__':
    unittest.main()
