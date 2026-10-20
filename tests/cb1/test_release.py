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

    def test_normal_image_omits_diagnostic_only_executables(self):
        import tempfile
        hook = re.search(r'function cb1_debug_install_identity\(\) \{.*?^\}',
                         (ROOT/'scripts/image').read_text(), re.M|re.S).group()
        with tempfile.TemporaryDirectory() as folder:
            install = Path(folder)
            paths = ('usr/bin/cb1-driver-profile', 'usr/lib/systemd/system/cb1-driver-profile.service')
            for name in (*paths, 'usr/share/kodi/media/cb1/keep.xml'):
                path = install/name; path.parent.mkdir(parents=True, exist_ok=True); path.touch()
            script = 'set -e\nCB1_DEBUG=no\nINSTALL="$1"\n' + hook + '\ncb1_debug_install_identity\n'
            subprocess.run(['bash', '-c', script, 'test', folder], check=True)
            self.assertTrue((install/'usr/share/kodi/media/cb1/keep.xml').exists())
            self.assertFalse(any((install/name).exists() for name in paths))

    def test_kodi_native_stamp_separates_normal_and_debug_caches(self):
        recipe = (ROOT/'packages/mediacenter/kodi/package.mk').read_text().split('configure_package()', 1)[0]
        functions = (ROOT/'config/functions').read_text()
        stamp = re.search(r'^calculate_stamp\(\) \{.*?^\}', functions, re.M|re.S).group()
        script = 'set -e\nROOT="$PWD";PROJECT_DIR="$ROOT/projects";PROJECT=Generic\n'
        script += 'PKG_DIR="$ROOT/packages/mediacenter/kodi"\n' + stamp + '\n'
        script += 'for CB1_DEBUG in no yes no;do\nPKG_STAMP=""\n' + recipe + '\ncalculate_stamp\ndone\n'
        stamps = subprocess.check_output(['bash', '-c', script], cwd=ROOT, text=True).splitlines()
        self.assertEqual(len(stamps), 3)
        self.assertNotEqual(stamps[0], stamps[1])
        self.assertEqual(stamps[0], stamps[2])

    def test_native_image_version_and_ai_defaults(self):
        keys = ("CUSTOM_VERSION", "BUILDER_VERSION", "CB1_HDR10_AI")
        options = (ROOT / "projects/Generic/options").read_text()
        defaults = options.split('################################################################################', 1)[0]
        script = "unset " + " ".join(keys) + " CB1_DEBUG CB1_DRIVER_PROFILE\n" + defaults
        script += '\nprintf "%s\\n" "$CUSTOM_VERSION" "$BUILDER_VERSION" "$CB1_HDR10_AI"'
        result = subprocess.check_output(["bash", "-c", script], text=True).splitlines()
        self.assertEqual(result, ["DV-R1.0.0-Beta5", "DV-R1.0.0 Beta5", "yes"])
        versions = json.loads((ROOT / "config/cb1-versions.json").read_text())
        self.assertEqual(versions["Release"]["version"], result[1])
        self.assertEqual(versions["Release"]["tag"], "R1.0.0-Beta5")
        self.assertEqual(versions["Release"]["image"],
                         "LibreELEC-Generic.x86_64-13.0-DV-R1.0.0-Beta5")
        debug = "unset " + " ".join(keys) + " CB1_DRIVER_PROFILE\nCB1_DEBUG=yes\n" + defaults
        debug += '\nprintf "%s\\n" "$CUSTOM_VERSION" "$BUILDER_VERSION"'
        result = subprocess.check_output(["bash", "-c", debug], text=True).splitlines()
        self.assertEqual(result, ["DV-R1.0.0-Beta5-debug", "DV-R1.0.0 Beta5 Debug"])
        self.assertEqual(versions['Debug release']['version'], result[1])


if __name__ == "__main__":
    unittest.main()
