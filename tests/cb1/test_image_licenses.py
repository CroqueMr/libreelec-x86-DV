# SPDX-License-Identifier: MIT
"""Exercise the native image license-copy commands with nested notices."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/image'


class ImageLicenseTests(unittest.TestCase):
    def test_release_and_noobs_preserve_nested_licenses(self):
        commands = [line.strip() for line in SCRIPT.read_text().splitlines()
                    if line.strip().startswith('cp ') and '${ROOT}/licenses/' in line]
        self.assertEqual(len(commands), 2)
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / 'source'
                release = Path(temporary) / 'release'
                (root / 'licenses/cb1').mkdir(parents=True)
                (root / 'licenses/MIT.txt').write_text('upstream license\n')
                (root / 'licenses/cb1/UPSTREAM-NOTICES.txt').write_text('CB1 notice\n')
                destinations = [release / 'licenses', release / 'Test/System/licenses']
                for path in destinations:
                    path.mkdir(parents=True)
                env = dict(os.environ, ROOT=str(root), RELEASE_DIR=str(release), NOOBS_DISTRO='Test')
                result = subprocess.run(['bash', '-e', '-c', command], env=env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                destination = destinations[1] if 'NOOBS_DISTRO' in command else destinations[0]
                self.assertEqual((destination / 'MIT.txt').read_bytes(), b'upstream license\n')
                self.assertEqual((destination / 'cb1/UPSTREAM-NOTICES.txt').read_bytes(), b'CB1 notice\n')
