# SPDX-License-Identifier: MIT
"""Run the engine's temporal regression tests in the integration workflow."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ENGINE = Path(__file__).resolve().parents[2] / "CB1"


class TemporalAnalysisTests(unittest.TestCase):
    def test_temporal_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "hdr10_ai_temporal"
            subprocess.run(
                [
                    "cc", "-std=c11", "-ffp-contract=off", "-frounding-math",
                    "-I", str(ENGINE / "src"),
                    str(ENGINE / "tests/hdr10_ai_temporal.c"),
                    str(ENGINE / "src/cb1_hdr10_temporal.c"),
                    str(ENGINE / "src/cb1_hdr10_features.c"),
                    "-lm", "-o", str(binary),
                ],
                check=True,
            )
            subprocess.run([str(binary)], check=True)
