# SPDX-License-Identifier: MIT
"""Check source staging without changing playback code."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/cb1-stage.py"


class StagingTests(unittest.TestCase):
    def test_defaults_to_bundled_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "CB1").mkdir()
            (root / "CB1/source.c").write_bytes(b"source\n")
            (root / "config/cb1-source-lock.json").write_text(json.dumps({
                "engine": {"commit": None, "source": "CB1/"},
                "staging": {"packages/source.c": {
                    "source": "source.c", "sha256": hashlib.sha256(b"source\n").hexdigest()}},
            }))
            result = subprocess.run([sys.executable, str(SCRIPT), "--tree", str(root)],
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual((root / "packages/source.c").read_bytes(), b"source\n")

    def test_release_declares_complete_model_from_cb1(self):
        tree = SCRIPT.parents[1]
        lock = json.loads((tree / "config/cb1-source-lock.json").read_text())
        expected = {"contract/cb1_l1l3_bundle.h", "data/manifest.json",
                    "data/normalization.f32", "data/cb1_l1l3_schema.h"}
        expected.update(f"data/field-{i}.txt" for i in range(6))
        prefix = "packages/mediacenter/kodi/cb1-model/"
        models = {name[len(prefix):]: record for name, record in lock["staging"].items()
                  if name.startswith(prefix)}
        self.assertEqual(set(models), expected)
        for name, record in models.items():
            self.assertEqual(record["source"], "models/l1l3/" + name)
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")

    def run_stage(self, root, engine, mapping, *options):
        (root / "config").mkdir(exist_ok=True)
        (root / "config/cb1-source-lock.json").write_text(json.dumps({
            "engine": {"commit": None}, "staging": mapping,
        }), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), "--tree", str(root),
                               "--engine", str(engine), *options], capture_output=True)

    def test_stages_matching_sources_and_check_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, engine = Path(tmp) / "le", Path(tmp) / "engine"
            root.mkdir(); engine.mkdir()
            (engine / "source.c").write_bytes(b"source\n")
            mapping = {"packages/mediacenter/kodi/cb1/src/source.c": {
                "source": "source.c", "sha256": hashlib.sha256(b"source\n").hexdigest()}}
            result = self.run_stage(root, engine, mapping, "--check")
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertFalse((root / "packages").exists())
            result = self.run_stage(root, engine, mapping)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual((root / next(iter(mapping))).read_bytes(), b"source\n")

    def test_rejects_modified_source_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, engine = Path(tmp) / "le", Path(tmp) / "engine"
            root.mkdir(); engine.mkdir()
            (engine / "source.c").write_bytes(b"modified\n")
            result = self.run_stage(root, engine, {"packages/source.c": {
                "source": "source.c", "sha256": hashlib.sha256(b"source\n").hexdigest()}})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"Source mismatch", result.stderr)
            self.assertFalse((root / "packages").exists())

    def test_rejects_destination_escape_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, engine = Path(tmp) / "le", Path(tmp) / "engine"
            root.mkdir(); engine.mkdir()
            (engine / "source.c").write_bytes(b"source\n")
            result = self.run_stage(root, engine, {"../outside.c": {
                "source": "source.c", "sha256": hashlib.sha256(b"source\n").hexdigest()}})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"Unsafe path", result.stderr)
            self.assertFalse((root.parent / "outside.c").exists())

    def test_preserves_conflicting_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, engine = Path(tmp) / "le", Path(tmp) / "engine"
            root.mkdir(); engine.mkdir()
            (engine / "source.c").write_bytes(b"source\n")
            (root / "source.c").write_bytes(b"local edit\n")
            result = self.run_stage(root, engine, {"source.c": {
                "source": "source.c", "sha256": hashlib.sha256(b"source\n").hexdigest()}})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"Destination differs", result.stderr)
            self.assertEqual((root / "source.c").read_bytes(), b"local edit\n")


if __name__ == "__main__":
    unittest.main()
