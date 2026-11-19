# SPDX-License-Identifier: MIT
"""Exercise the x86 firmware staging used before kernel configuration."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class IntelArcFirmwareTests(unittest.TestCase):
    def test_xe_and_i915_firmware_reach_the_builtin_list(self):
        source = (ROOT / "packages/linux/package.mk").read_text()
        block = source.split('  if [ "${TARGET_ARCH}" = "x86_64" ]; then', 1)[1]
        block = block.split('  elif [ "${TARGET_ARCH}" = "arm"', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            for family in ("amdgpu", "amd-ucode", "i915", "xe", "radeon", "e100", "rtl_nic"):
                folder = tree / "kernel-firmware/.copied-firmware" / family
                folder.mkdir(parents=True)
                (folder / "test.bin").write_bytes(b"firmware")
            xe = tree / "kernel-firmware/.copied-firmware/xe"
            (xe / "bmg_guc_70.bin").write_bytes(b"bmg-guc")
            (xe / "bmg_huc.bin").write_bytes(b"bmg-huc")
            (xe / "alias.bin").symlink_to("bmg_guc_70.bin")
            (tree / "intel-ucode/intel-ucode").mkdir(parents=True)
            (tree / "build/scripts").mkdir(parents=True)
            config = tree / "build/scripts/config"
            config.write_text('#!/bin/sh\nexit 0\n')
            config.chmod(0o755)
            result = subprocess.run(
                ["bash", "-euc", 'PKG_BUILD="$PWD/build"\n'
                 'get_build_dir() { printf "%s/%s" "$PWD" "$1"; }\n'
                 + block + '\nprintf "%s\\n" "$FW_LIST"'],
                cwd=tree, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = result.stdout.split()
            for name in ("i915/test.bin", "xe/bmg_guc_70.bin", "xe/bmg_huc.bin", "xe/alias.bin"):
                self.assertIn(name, files)
            self.assertEqual((tree / "build/external-firmware/xe/alias.bin").read_bytes(), b"bmg-guc")


if __name__ == "__main__":
    unittest.main()
