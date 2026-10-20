"""Debug identity and native image hooks use small, disposable source fixtures."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts/cb1-debug-build-info.py'


def put(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    return path


def fixture(root):
    for name in ('kodi', 'mesa'):
        directory = 'mediacenter' if name == 'kodi' else 'graphics'
        put(root, f'packages/{directory}/{name}/package.mk',
            'PKG_VERSION="1.0"\nPKG_SHA256="' + 'b' * 64 + '"\n')
    for name in ('CB1/CMakeLists.txt', 'CB1/src/core.c', 'CB1/models/core.bin', 'CB1/config/source.json'):
        put(root, name, 'pinned source\n')
    patch = put(root, 'packages/linux/patches/default/ordinary.patch', 'ordinary\n')
    ordinary = {'packages/linux/patches/default/ordinary.patch': hashlib.sha256(patch.read_bytes()).hexdigest()}
    policy = {'schema': 1, 'linux_source_sha256': 'a' * 64,
              'ordinary_patches': ordinary, 'graphics_patches': {'graphics.patch': 'c' * 64}}
    put(root, 'config/cb1-driver-profiles.json', json.dumps(policy))
    return policy


def install(root, target, profile='modified', source='a' * 64, paired=''):
    return subprocess.run(['python3', str(HELPER), '--root', str(root), '--install', str(target),
                           '--build-id', 'DV-R1.0.0-Beta5-debug', '--linux-version', '7.2.6',
                           '--linux-source-sha256', source, '--profiles-dir', str(paired)],
                          env={**os.environ, 'CB1_DRIVER_PROFILE': profile}, capture_output=True, text=True)


def hook(name):
    match = re.search(r'function ' + name + r'\(\) \{.*?\n\}', (ROOT / 'scripts/image').read_text(), re.S)
    return match.group() if match else ''


def shell_hook(name, root, arguments=(), preamble='', **environment):
    script = 'set -e\ndie(){ echo "$*" >&2; exit 1; };\n' + preamble + '\n' + hook(name) + '\n' + name + ' "$@"\n'
    return subprocess.run(['bash', '-c', script, 'test', *arguments],
                          env={**os.environ, 'ROOT': str(root), 'SCRIPTS': str(root/'scripts'),
                               'PROJECT': 'Generic', 'BOOTLOADER': 'syslinux', **environment},
                          capture_output=True, text=True)


class DebugBuildInfo(unittest.TestCase):
    def test_native_recipe_retains_variant_flags_after_configuration(self):
        script = '''set -e
get_target_linker(){ echo gold; }; get_graphicdrivers(){ :; }
get_pkg_version(){ echo 1; }; get_pkg_variable(){ echo pinned; }
get_build_dir(){ echo /tmp/package-source; }
source "$1"
configure_package
printf '%s\\n' "$PKG_CMAKE_OPTS_TARGET"
'''
        for debug, expected in (('no', 'OFF'), ('yes', 'ON')):
            for ai in ('yes', 'no'):
                with self.subTest(debug=debug, ai=ai):
                    result = subprocess.run(['bash', '-c', script, 'test',
                        str(ROOT/'packages/mediacenter/kodi/package.mk')],
                        env={**os.environ, 'CB1_DEBUG': debug, 'CB1_HDR10_AI': ai,
                             'TARGET_ARCH': 'x86_64', 'PROJECT': 'Generic'},
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    options = result.stdout.split()
                    for name in ('CB1_ENABLE_MASTER_IPT', 'CB1_DEBUG_BUILD'):
                        self.assertEqual([v for v in options if v.startswith('-D'+name+'=')],
                                         ['-D'+name+'='+expected])
                    self.assertIn('-DCB1_ENABLE_HDR10_AI='+('ON' if ai == 'yes' else 'OFF'), options)

    def test_identity_is_profile_and_location_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'one'; root.mkdir()
            policy = fixture(root)
            relocated = Path(directory)/'two'; shutil.copytree(root, relocated)
            outputs = []
            for source, profile in ((root, 'modified'), (relocated, 'standard')):
                target = source/'install'
                result = install(source, target, profile)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((target/'etc/cb1-debug').is_file())
                outputs.append((target/'usr/share/cb1/driver-profile-build.json').read_bytes())
            self.assertEqual(*outputs)
            build = json.loads(outputs[0])
            self.assertEqual(build['id'], 'DV-R1.0.0-Beta5-debug')
            self.assertEqual(build['linux_version'], '7.2.6')
            self.assertEqual(build['ordinary_patches_sha256'], hashlib.sha256(
                json.dumps(policy['ordinary_patches'], sort_keys=True, separators=(',', ':')).encode()).hexdigest())
            self.assertEqual(set(build['userspace']), {'kodi', 'cb1', 'mesa'})
            self.assertNotIn(str(root).encode(), outputs[0])

    def test_model_change_updates_only_cb1_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture(root)
            before = root/'before'; after = root/'after'
            self.assertEqual(install(root, before).returncode, 0)
            put(root, 'CB1/models/core.bin', 'new matched model\n')
            self.assertEqual(install(root, after).returncode, 0)
            a = json.loads((before/'usr/share/cb1/driver-profile-build.json').read_text())
            b = json.loads((after/'usr/share/cb1/driver-profile-build.json').read_text())
            self.assertNotEqual(a['userspace']['cb1'], b['userspace']['cb1'])
            self.assertEqual(a['userspace']['kodi'], b['userspace']['kodi'])
            self.assertEqual(a['userspace']['mesa'], b['userspace']['mesa'])

    def test_source_and_patch_policy_disagreement_refuses_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture(root)
            target = root/'install'
            self.assertNotEqual(install(root, target, source='f'*64).returncode, 0)
            self.assertFalse((target/'etc/cb1-debug').exists())
            put(root, 'packages/linux/patches/default/ordinary.patch', 'unrecorded patch\n')
            self.assertNotEqual(install(root, target).returncode, 0)
            self.assertFalse((target/'etc/cb1-debug').exists())

    def test_prepared_pair_must_match_current_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture(root)
            self.assertEqual(install(root, root/'component').returncode, 0)
            build = json.loads((root/'component/usr/share/cb1/driver-profile-build.json').read_text())
            put(root, 'pair/cb1/driver-profiles.json', json.dumps({'build': build}))
            self.assertEqual(install(root, root/'final', paired=root/'pair').returncode, 0)
            put(root, 'CB1/src/core.c', 'changed after component build\n')
            result = install(root, root/'refused', paired=root/'pair')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('current source identity', result.stderr)
            self.assertFalse((root/'refused/etc/cb1-debug').exists())

    def test_installed_ui_and_debug_runtime_overrides_are_source_inputs(self):
        for component, path in (('kodi', 'projects/Generic/filesystem/usr/share/kodi/media/cb1/panel.xml'),
                                ('cb1', 'projects/Generic/filesystem/usr/bin/cb1-driver-profile')):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); fixture(root)
                put(root, path, 'prepared override\n')
                self.assertEqual(install(root, root/'before').returncode, 0)
                put(root, path, 'changed override\n')
                self.assertEqual(install(root, root/'after').returncode, 0)
                a = json.loads((root/'before/usr/share/cb1/driver-profile-build.json').read_text())
                b = json.loads((root/'after/usr/share/cb1/driver-profile-build.json').read_text())
                self.assertNotEqual(a['userspace'][component], b['userspace'][component])

    def test_native_identity_hook_enables_actual_service_only_in_debug(self):
        native_enable = re.search(r'\nenable_service\(\) \{.*?\n\}',
                                  (ROOT/'config/functions').read_text(), re.S).group()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fixture(root)
            (root/'scripts').mkdir()
            shutil.copyfile(HELPER, root/'scripts/cb1-debug-build-info.py')
            preamble = native_enable + '\nget_pkg_version(){ echo 7.2.6; }; get_pkg_variable(){ echo ' + 'a'*64 + '; };'
            for debug in ('yes', 'no'):
                target = root/debug
                put(target, 'usr/lib/systemd/system/cb1-driver-profile.service', '[Install]\nWantedBy=multi-user.target\n')
                result = shell_hook('cb1_debug_install_identity', root, preamble=preamble,
                                    CB1_DEBUG=debug, INSTALL=str(target), CUSTOM_VERSION='DV-R1.0.0-Beta5-debug')
                self.assertEqual(result.returncode, 0, result.stderr)
                link = target/'usr/lib/systemd/system/multi-user.target.wants/cb1-driver-profile.service'
                self.assertEqual(link.is_symlink(), debug == 'yes')
                self.assertEqual((target/'etc/cb1-debug').exists(), debug == 'yes')

    def test_final_native_components_are_not_regenerated(self):
        source = (ROOT/'scripts/image').read_text()
        fragment = source[source.index('# Make target dir\n'):source.index('\nif [ "${1}" = "release" ]')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            put(root, 'scripts/cb1-debug-profiles.py', '''import argparse
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--check',type=Path); p.add_argument('--kernel',type=Path); p.add_argument('--system',type=Path)
a=p.parse_args(); assert a.kernel.read_bytes()==b'prepared kernel'; assert a.system.read_bytes()==b'prepared system'
''')
            put(root, 'target/debug.kernel', 'prepared kernel')
            put(root, 'target/debug.system', 'prepared system')
            script = '''set -e
die(){ echo "$*" >&2; exit 1; }; rm(){ exit 95; }; cp(){ exit 95; }
'''+fragment
            result = subprocess.run(['bash', '-c', script], env={**os.environ, 'SCRIPTS': str(root/'scripts'),
                                    'TARGET_IMG': str(root/'target'), 'IMAGE_NAME': 'debug',
                                    'CB1_DEBUG_FINAL_PAIR': 'yes', 'CB1_DEBUG_PROFILES_DIR': str(root/'pair')},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root/'target/debug.kernel').read_text(), 'prepared kernel')
            self.assertEqual((root/'target/debug.system').read_text(), 'prepared system')
            self.assertIn('not rebuilding', result.stdout)

    def test_mkimage_receives_debug_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = put(root, 'scripts/mkimage', '#!/usr/bin/env python3\nimport os,json\nprint(json.dumps({k:os.environ[k] for k in ("CB1_DEBUG","CB1_DEBUG_PROFILES_DIR","IMAGE_NAME")}))\n')
            target.chmod(0o755)
            result = shell_hook('do_mkimage', root, ('requested-name',), CB1_DEBUG='yes',
                                CB1_DEBUG_PROFILES_DIR=str(root/'paired'), IMAGE_NAME='prepared-name')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'CB1_DEBUG': 'yes',
                             'CB1_DEBUG_PROFILES_DIR': str(root/'paired'), 'IMAGE_NAME': 'requested-name'})

    def test_native_request_allows_components_but_not_unpaired_or_standard_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common = {'CB1_DEBUG': 'yes', 'CB1_DRIVER_PROFILE': 'standard'}
            self.assertEqual(shell_hook('cb1_debug_check_request', root, **common).returncode, 0)
            for kind in ('release', 'mkimage', 'noobs'):
                self.assertNotEqual(shell_hook('cb1_debug_check_request', root, (kind,), **common).returncode, 0)
                self.assertNotEqual(shell_hook('cb1_debug_check_request', root, (kind,),
                                              CB1_DEBUG='yes', CB1_DRIVER_PROFILE='modified').returncode, 0)
            (root/'pair/cb1').mkdir(parents=True)
            self.assertEqual(shell_hook('cb1_debug_check_request', root, ('release',), CB1_DEBUG='yes',
                                       CB1_DRIVER_PROFILE='modified', CB1_DEBUG_PROFILES_DIR=str(root/'pair')).returncode, 0)
            self.assertNotEqual(shell_hook('cb1_debug_check_request', root, ('noobs',), CB1_DEBUG='yes',
                                          CB1_DRIVER_PROFILE='modified', CB1_DEBUG_PROFILES_DIR=str(root/'pair')).returncode, 0)
            self.assertEqual(shell_hook('cb1_debug_check_request', root, ('release',), CB1_DEBUG='no').returncode, 0)

    def test_native_release_preserves_primary_and_refuses_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            put(root, 'scripts/cb1-debug-profiles.py', '''import argparse
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--check',type=Path); p.add_argument('--kernel',type=Path); p.add_argument('--system',type=Path)
a=p.parse_args()
assert a.kernel.read_bytes()==(a.check/'KERNEL').read_bytes()
assert a.system.read_bytes()==(a.check/'SYSTEM').read_bytes()
assert a.kernel.with_name('KERNEL.md5').is_file() and a.system.with_name('SYSTEM.md5').is_file()
''')
            for name in ('KERNEL', 'SYSTEM'):
                put(root, 'pair/'+name, name)
                put(root, 'release/target/'+name, name)
                put(root, 'release/target/'+name+'.md5', 'native checksum')
            put(root, 'pair/cb1/KERNEL.standard', 'standard kernel')
            put(root, 'pair/cb1/SYSTEM.standard', 'standard system')
            common = {'CB1_DEBUG': 'yes', 'CB1_DEBUG_PROFILES_DIR': str(root/'pair'), 'RELEASE_DIR': str(root/'release')}
            result = shell_hook('cb1_debug_stage_profiles', root, **common)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root/'release/target/cb1/KERNEL.standard').read_text(), 'standard kernel')
            self.assertEqual((root/'release/target/KERNEL').read_text(), 'KERNEL')
            self.assertEqual((root/'release/target/KERNEL.md5').read_text(), 'native checksum')
            put(root, 'release/target/KERNEL', 'wrong primary')
            self.assertNotEqual(shell_hook('cb1_debug_stage_profiles', root, **common).returncode, 0)
            self.assertEqual((root/'release/target/KERNEL').read_text(), 'wrong primary')


if __name__ == '__main__':
    unittest.main()
