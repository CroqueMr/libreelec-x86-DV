"""Run the native Java addon recipe against matched and stale BD-J staging."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / 'packages/addons/tools/jre.zulu'
BLURAY = ROOT / 'packages/multimedia/libbluray/package.mk'


@unittest.skipUnless(shutil.which('bash'), 'Native LibreELEC packaging requires bash')
class BDJRuntimePackagingTests(unittest.TestCase):
    def package(self, directory, jars):
        root = Path(directory)
        (root / 'jdk/jre/bin').mkdir(parents=True)
        (root / 'jdk/jre/bin/java').write_bytes(b'JRE fixture')
        staged = root / 'jre-libbluray/usr/share/java'
        staged.mkdir(parents=True)
        for jar in jars:
            (staged / jar).write_bytes(jar.encode())
        libraries = {
            'chrome-libXtst': 'libXtst', 'jre-libXinerama': 'libXinerama',
            'libXi': 'libXi', 'libXrender': 'libXrender', 'libX11': 'libX11',
            'libXext': 'libXext', 'libxcb': 'libxcb',
        }
        for package, library in libraries.items():
            target = root / package / 'usr/lib'
            target.mkdir(parents=True)
            (target / (library + '.so.1')).write_bytes(b'Library fixture')
        result = subprocess.run(['bash', '-e', '-c', r'''
get_build_dir() { printf '%s/jdk\n' "$FIXTURE"; }
get_install_dir() { printf '%s/%s\n' "$FIXTURE" "$1"; }
get_pkg_version() { . "$BLURAY_RECIPE"; printf '%s\n' "$PKG_VERSION"; }
. "$PKG_DIR/package.mk"
addon
'''], env=dict(os.environ, FIXTURE=str(root), PKG_DIR=str(ADDON),
              BLURAY_RECIPE=str(BLURAY), TARGET_ARCH='x86_64', DISPLAYSERVER='gbm',
              ADDON_BUILD=str(root / 'output'), PKG_ADDON_ID='tools.jre.zulu'),
            capture_output=True, text=True)
        return result, root / 'output/tools.jre.zulu'

    def matched(self):
        version = re.search(r'^PKG_VERSION="([^"]+)"', BLURAY.read_text(), re.M)[1]
        return {f'libbluray-j2se-{version}.jar', f'libbluray-awt-j2se-{version}.jar'}

    def test_only_the_pair_matching_the_native_library_is_packaged(self):
        wanted = self.matched()
        with tempfile.TemporaryDirectory() as directory:
            result, output = self.package(directory, wanted | {
                'libbluray-j2se-0.0.0.jar', 'libbluray-awt-j2se-0.0.0.jar'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({p.name for p in output.glob('*.jar')}, wanted)
            for jar in wanted:
                self.assertEqual((output / jar).read_bytes(), jar.encode())
            self.assertTrue((output / 'jre/bin/java').is_file())
            self.assertEqual((output / 'profile.d/jre.profile').read_bytes(),
                             (ADDON / 'profile.d/jre.profile').read_bytes())

    def test_a_missing_matched_jar_stops_packaging(self):
        wanted = self.matched()
        for omitted in sorted(wanted):
            with self.subTest(omitted=omitted), tempfile.TemporaryDirectory() as directory:
                result, _ = self.package(directory, (wanted - {omitted}) | {
                    'libbluray-j2se-0.0.0.jar', 'libbluray-awt-j2se-0.0.0.jar'})
                self.assertNotEqual(result.returncode, 0,
                                    'An incomplete BD-J runtime must not be released')


if __name__ == '__main__':
    unittest.main()
