# SPDX-License-Identifier: MIT
"""Check CI patch enumeration with an absent optional architecture directory."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CIPatchInputs(unittest.TestCase):
    def test_missing_optional_directory_does_not_become_a_literal_input(self):
        script = (ROOT / '.github/scripts/prepare-test-sources.sh').read_text()
        setup = script.split('pin() {', 1)[0]
        loop = script.split('for patch_file in ', 1)[1].split('\ndone', 1)[0]
        header = loop.split('; do', 1)[0]
        probe = setup + 'for patch_file in ' + header + '; do\n'
        probe += 'test -f "$patch_file" || exit 42\nprintf "%s\\n" "$patch_file"\ndone\n'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expected = ['packages/mediacenter/kodi/patches/base.patch',
                        'projects/Generic/patches/kodi/shared.patch']
            for name in expected:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            result = subprocess.run(['bash', '-c', probe], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), expected)


if __name__ == '__main__':
    unittest.main()
