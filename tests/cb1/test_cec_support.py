"""Exercise CEC recipe selection and resolve Generic against native Kconfig.

Run on Linux with CB1_KERNEL_SOURCE pointing at the matched, clean kernel tree.
Only temporary output directories are written; no CEC hardware is probed.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def recipe(project='Generic', framework='no'):
    # Build helpers are irrelevant to CEC selection; run the real recipe body.
    script = r'''
set -e
TARGET_ARCH=x86_64 SYSTEM_SIZE=1024 CEC_SUPPORT=yes
CEC_FRAMEWORK_SUPPORT=$2 PROJECT=$1 DISPLAYSERVER=gbm
if [ "$PROJECT" = Generic ]; then source projects/Generic/options; fi
source packages/devel/libcec/package.mk
printf '%s\n' "$PKG_CMAKE_OPTS_TARGET"
get_target_linker() { :; }
get_graphicdrivers() { :; }
get_pkg_version() { :; }
get_pkg_variable() { :; }
get_build_dir() { :; }
source packages/mediacenter/kodi/package.mk
configure_package
printf '%s\n' "$KODI_CEC" "$PKG_PATCH_DIRS" "$PKG_DEPENDS_TARGET"
'''
    return subprocess.check_output(['bash', '-c', script, 'cec-test', project, framework],
                                   cwd=ROOT, text=True).splitlines()


@unittest.skipUnless(shutil.which('bash'), 'bash required')
class CecRecipes(unittest.TestCase):
    def test_generic_builds_kodi_and_native_linux_cec(self):
        lines = recipe()
        self.assertIn('-DHAVE_LINUX_API=1', lines[0])
        self.assertEqual(lines[1], '-DENABLE_CEC=ON')
        self.assertIn('libcec', lines[3].split())

    def test_generic_keeps_removable_linux_adapter_rescanning(self):
        self.assertNotIn('cec-framework', recipe('Generic', 'yes')[2].split())

    def test_other_framework_projects_keep_existing_polling_workaround(self):
        lines = recipe('Rockchip', 'yes')
        self.assertIn('-DHAVE_LINUX_API=1', lines[0])
        self.assertIn('cec-framework', lines[2].split())
        lines = recipe('Rockchip', 'no')
        self.assertIn('-DHAVE_LINUX_API=0', lines[0])
        self.assertNotIn('cec-framework', lines[2].split())


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class CecNativeKconfig(unittest.TestCase):
    def test_both_generic_configs_retain_cec_after_dependency_resolution(self):
        kernel = Path(os.environ['CB1_KERNEL_SOURCE']).resolve()
        for config in ('linux.x86_64.conf', '7.2.6/linux.x86_64.conf'):
            with self.subTest(config=config), tempfile.TemporaryDirectory(prefix='cb1-cec-') as temp:
                output = Path(temp)
                shutil.copyfile(ROOT/'projects/Generic/linux'/config, output/'.config')
                result = subprocess.run(['make', '-s', '-C', str(kernel), 'O='+str(output),
                                         'ARCH=x86_64', 'olddefconfig'],
                                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(result.returncode, 0, result.stdout)
                effective = dict(line.split('=', 1) for line in (output/'.config').read_text().splitlines()
                                 if line.startswith('CONFIG_') and '=' in line)
                for symbol, value in {'CEC_CORE': 'y', 'CEC_NOTIFIER': 'y',
                                      'MEDIA_CEC_SUPPORT': 'y', 'CEC_SECO': 'm',
                                      'DRM_DISPLAY_DP_AUX_CEC': 'y', 'PCI': 'y',
                                      'DMI': 'y', 'DRM_I915': 'y', 'DRM_XE': 'm'}.items():
                    self.assertEqual(effective.get('CONFIG_'+symbol), value, config+': '+symbol)
                # USB Pulse-Eight remains libCEC-owned; do not grab its device
                # with the kernel's alternate backend or pull in unrelated SoCs.
                for symbol in ('USB_PULSE8_CEC', 'CEC_GPIO', 'CEC_CROS_EC', 'CEC_MESON_AO'):
                    self.assertNotIn('CONFIG_'+symbol, effective, config+': '+symbol)


if __name__ == '__main__':
    unittest.main()
