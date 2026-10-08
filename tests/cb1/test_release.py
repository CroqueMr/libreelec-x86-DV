# SPDX-License-Identifier: MIT
"""Verify native LibreELEC release defaults."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ReleaseTests(unittest.TestCase):
    def test_native_image_version_and_ai_defaults(self):
        keys = ("CUSTOM_VERSION", "BUILDER_VERSION", "CB1_HDR10_AI")
        options = (ROOT / "projects/Generic/options").read_text()
        defaults = "\n".join(line for line in options.splitlines()
                             if line.strip().startswith(tuple(key + "=" for key in keys)))
        script = "unset " + " ".join(keys) + "\n" + defaults
        script += '\nprintf "%s\\n" "$CUSTOM_VERSION" "$BUILDER_VERSION" "$CB1_HDR10_AI"'
        result = subprocess.check_output(["bash", "-c", script], text=True).splitlines()
        self.assertEqual(result, ["R1.0.0-Beta2", "R1.0.0 Beta2", "yes"])
        versions = json.loads((ROOT / "config/cb1-versions.json").read_text())
        self.assertEqual(versions["Release"]["version"], result[1])
        self.assertEqual(versions["Release"]["tag"], result[0])


if __name__ == "__main__":
    unittest.main()
