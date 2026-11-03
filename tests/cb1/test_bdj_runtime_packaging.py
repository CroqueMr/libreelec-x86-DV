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
BUILTIN = ROOT / 'packages/multimedia/bdj-runtime'


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

    def test_builtin_runtime_keeps_java_and_licenses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('bin/java', 'lib/amd64/server/libjvm.so', 'LICENSE',
                         'THIRD_PARTY_README'):
                file = root / 'jdk/jre' / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(name.encode())
                if name == 'bin/java':
                    file.chmod(0o755)
            recipe = BUILTIN / 'package.mk'
            self.assertTrue(recipe.is_file(), 'The system image needs a native Java package')
            result = subprocess.run(['bash', '-e', '-c', '''
get_build_dir() { printf '%s/jdk\\n' "$FIXTURE"; }
. "$PKG_DIR/package.mk"
makeinstall_target
'''], env=dict(os.environ, FIXTURE=str(root), PKG_DIR=str(BUILTIN),
              INSTALL=str(root / 'image'), TARGET_ARCH='x86_64'),
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ('bin/java', 'lib/amd64/server/libjvm.so', 'LICENSE',
                         'THIRD_PARTY_README'):
                self.assertEqual((root/'image/usr/lib/jvm/zulu8'/name).read_bytes(),
                                 name.encode())

    def test_builtin_profile_overrides_stale_addon_without_starting_java(self):
        profile = BUILTIN / 'profile.d/90-bdj.conf'
        self.assertTrue(profile.is_file(), 'Native profile must select the matched system runtime')
        result = subprocess.run(['sh', '-e', '-c', '''
export JAVA_HOME=/storage/.kodi/addons/tools.jre.zulu
export LIBBLURAY_CP=/storage/.kodi/addons/tools.jre.zulu/
. "$BDJ_PROFILE"
printf '%s\\n%s\\n' "$JAVA_HOME" "$LIBBLURAY_CP"
'''], env=dict(os.environ, BDJ_PROFILE=str(profile)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ['/usr/lib/jvm/zulu8', '/usr/share/java/'])

    def test_native_library_build_requires_both_matching_jars(self):
        wanted = self.matched()
        for omitted in (None, *sorted(wanted)):
            with self.subTest(omitted=omitted), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                jars = root/'image/usr/share/java'
                jars.mkdir(parents=True)
                for name in wanted - {omitted}:
                    (jars/name).write_bytes(b'JAR fixture')
                result = subprocess.run(['bash', '-e', '-c', '''
get_build_dir() { printf '%s/jdk\\n' "$FIXTURE"; }
. "$BLURAY_RECIPE"
configure_package
pre_configure_target
[[ "$PKG_MESON_OPTS_TARGET" == *"-Dbdj_jar=enabled"* ]]
post_makeinstall_target
'''], env=dict(os.environ, FIXTURE=str(root), BLURAY_RECIPE=str(BLURAY),
              INSTALL=str(root/'image'), PROJECT='Generic', TARGET_ARCH='x86_64',
              MACHINE_HARDWARE_NAME='x86_64'), capture_output=True, text=True)
                if omitted is None:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0,
                                        'A missing matching JAR must fail the native build')

    def test_jdk_is_registered_before_native_unpack_hashing(self):
        result = subprocess.run(['bash', '-e', '-c', '''
. "$BLURAY_RECIPE"
case " $PKG_DEPENDS_UNPACK " in
  *" jdk-x86_64-zulu "*) exit 0 ;;
  *) exit 1 ;;
esac
'''], env=dict(os.environ, BLURAY_RECIPE=str(BLURAY), PROJECT='Generic',
              TARGET_ARCH='x86_64', MACHINE_HARDWARE_NAME='x86_64'),
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         'A JDK update must invalidate native libbluray and its JARs')


if __name__ == '__main__':
    unittest.main()
