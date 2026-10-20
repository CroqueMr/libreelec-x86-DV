# SPDX-License-Identifier: MIT
"""Verify native LibreELEC release defaults."""
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ReleaseTests(unittest.TestCase):
    def test_release_tree_excludes_local_build_results(self):
        private = {'artifacts', 'compile-native.sh', 'test-engine.sh', 'test-kodi.sh',
                   'PROGRESS.md', 'RESULTS.md'}
        found = [p.relative_to(ROOT).as_posix() for p in ROOT.iterdir()
                 if p.name in private or p.suffix == '.log']
        runtime = ROOT/'projects/Generic/filesystem'
        found += [p.relative_to(ROOT).as_posix() for p in runtime.rglob('*')
                  if p.is_file() and (p.suffix in ('.pyc', '.o') or '__pycache__' in p.parts)]
        lock = json.loads((ROOT/'config/cb1-source-lock.json').read_text())
        found += [name for name in lock['integration_files']
                  if '__pycache__' in Path(name).parts or name.endswith('.pyc')]
        self.assertEqual(found, [], 'Local build data must not enter release sources or runtime')

    def test_native_image_version_and_ai_defaults(self):
        keys = ("CUSTOM_VERSION", "BUILDER_VERSION", "CB1_HDR10_AI")
        options = (ROOT / "projects/Generic/options").read_text()
        defaults = options.split('################################################################################', 1)[0]
        script = "unset " + " ".join(keys) + "\n" + defaults
        script += '\nprintf "%s\\n" "$CUSTOM_VERSION" "$BUILDER_VERSION" "$CB1_HDR10_AI"'
        result = subprocess.check_output(["bash", "-c", script], text=True).splitlines()
        self.assertEqual(result, ["DV-R1.0.0-Beta5", "DV-R1.0.0 Beta5", "yes"])
        versions = json.loads((ROOT / "config/cb1-versions.json").read_text())
        self.assertEqual(versions["Release"]["version"], result[1])
        self.assertEqual(versions["Release"]["tag"], "R1.0.0-Beta5")
        self.assertEqual(versions["Release"]["image"],
                         "LibreELEC-Generic.x86_64-13.0-DV-R1.0.0-Beta5")


if __name__ == "__main__":
    unittest.main()
