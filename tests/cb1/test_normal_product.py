# SPDX-License-Identifier: MIT
"""Keep Debug-only product inputs out of normal release sources."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NormalProductTests(unittest.TestCase):
    def test_normal_release_sources_have_no_debug_product(self):
        # Source archives must not contain an optional second product either.
        forbidden = (b'CB1_ENABLE_MASTER_IPT', b'CB1_DEBUG_BUILD', b'CB1_DEBUG_PROFILES_DIR',
                     b'cb1-driver-profile', b'cb1-debug-profiles', b'cb1standarddrivers',
                     b'cb1_master_ipt', b'MasterReferenceIPT')
        roots = ('CB1/src', 'CB1/patches', 'projects/Generic', 'packages', 'scripts', 'config')
        found = []
        names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).decode().split('\0')
        for name in names:
            path = ROOT/name
            if name.startswith(roots) and path.is_file():
                data = path.read_bytes()
                if any(token in data for token in forbidden):
                    found.append(name)
        for name in ('CB1/CMakeLists.txt', 'CB1/tests/CMakeLists.txt'):
            if any(token in (ROOT/name).read_bytes() for token in forbidden):
                found.append(name)
        self.assertEqual(found, [], 'Debug-only sources must remain outside normal main')


if __name__ == '__main__':
    unittest.main()
