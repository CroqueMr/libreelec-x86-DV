"""Exercise the early NVIDIA selector with a synthetic sysfs and payload."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SELECTOR = ROOT/'packages/graphics/nvidia/files/select-driver'


class NvidiaSelection(unittest.TestCase):
    def test_pci_map_rejects_conflicting_or_unmatched_vendor_input(self):
        spec = importlib.util.spec_from_file_location('pci_map', ROOT/'packages/graphics/nvidia/generate-pci-map.py')
        generator = importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
        current = {'chips': [{'devid': '0x1b80', 'legacybranch': '580.xx'}, {'devid': '0x1e04'}]}
        legacy = {'chips': [{'devid': '0x1b80'}]}
        self.assertEqual(generator.table(current, legacy), '1b80 r580\n1e04 r615\n')
        with self.assertRaises(ValueError):
            generator.table(current, {'chips': []})
        current['chips'].append({'devid': '0x1B80'})
        with self.assertRaises(ValueError):
            generator.table(current, legacy)

    def fixture(self, base, devices=()):
        lib, run, sys = base/'usr/lib', base/'run', base/'sys'
        (sys/'bus/pci/devices').mkdir(parents=True)
        run.mkdir()
        for branch, version in [('r615', '615.78.08'), ('r580', '580.178.04')]:
            payload = lib/'nvidia-drivers'/branch
            (payload/'usr/lib').mkdir(parents=True)
            (payload/'driver-version').write_text(version+'\n')
            for name in ('libEGL_nvidia.so.0', 'libcuda.so.1', 'libnvcuvid.so.1',
                         'libnvidia-ml.so.1'):
                (payload/'usr/lib'/name).write_bytes(b'matched-vendor')
            (payload/'required-userspace').write_text(''.join(p.relative_to(payload).as_posix()+'\n'
                for p in sorted((payload/'usr').rglob('*')) if p.is_file()))
            firmware = lib/'kernel-overlays'/('nvidia-'+branch)/'lib/firmware/nvidia'/version
            firmware.mkdir(parents=True)
            (firmware/'gsp-test.bin').write_bytes(branch.encode())
            (payload/'required-firmware').write_text('nvidia/'+version+'/gsp-test.bin\n')
            modules = lib/'kernel-overlays'/('nvidia-'+branch)/'lib/modules/test/nvidia'
            modules.mkdir(parents=True)
            for name in ('nvidia', 'nvidia-modeset', 'nvidia-drm', 'nvidia-uvm'):
                (modules/(name+'.ko')).write_bytes(branch.encode())
        (lib/'nvidia-drivers/pci-branches').write_text('1b80 r580\n1c82 r580\n1e04 r615\n2b85 r615\n')
        (lib/'nvidia-drivers/r615/hdr-depth.conf').write_text('options nvidia-modeset max_output_color_depth=12\n')
        for i, (vendor, device, boot, cls) in enumerate(devices):
            path = sys/'bus/pci/devices'/('0000:01:%02x.0' % i)
            path.mkdir()
            for key, value in [('vendor', vendor), ('device', device), ('boot_vga', boot), ('class', cls)]:
                (path/key).write_text(value+'\n')
        return sys, lib, run

    def select(self, fixture):
        return subprocess.run(['sh', '-ec', '. "$1"; KVER=test; '
            'log(){ echo "$*" >&2; }; select_nvidia_driver "$2" "$3" "$4"; '
            'printf "%s" "$NVIDIA_OVERLAY"', 'select', str(SELECTOR),
            *map(str, fixture)], text=True, capture_output=True)

    def test_known_no_unknown_and_non_display_devices(self):
        for devices, branch, overlay in [
            ([], 'r615', ''),
            ([('0x10de', '0x1b80', '0', '0x030000')], 'r580', 'nvidia-r580'),
            ([('0x10de', '0x1E04', '0', '0x030200')], 'r615', 'nvidia-r615'),
            ([('0x10de', '0xffff', '0', '0x030000')], 'r615', ''),
            ([('0x10de', '0x1b80', '0', '0x040300')], 'r615', ''),
            ([('0x1002', '0x1b80', '1', '0x030000')], 'r615', ''),
            ([('0x10de', '0xffff', '1', '0x030000'), ('0x10de', '0x1b80', '0', '0x030000')], 'r615', ''),
            ([('0x10de', '0x1b80', '0', '0x030000'), ('0x10de', '0x1c82', '0', '0x030000')], 'r580', 'nvidia-r580'),
        ]:
            with self.subTest(devices=devices), tempfile.TemporaryDirectory() as tmp:
                fixture = self.fixture(Path(tmp), devices)
                result = self.select(fixture)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, overlay)
                self.assertEqual((fixture[2]/'nvidia-driver').resolve(), fixture[1]/'nvidia-drivers'/branch)
                self.assertEqual((fixture[2]/'modprobe.d/nvidia-hdr-depth.conf').exists(), branch == 'r615' and bool(overlay))

    def test_multiple_and_mixed_devices_prefer_known_boot_display(self):
        for first_boot, second_boot, expected in [('1', '0', 'r580'), ('0', '1', 'r615'), ('0', '0', 'r615')]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                fixture = self.fixture(Path(tmp), [('0x10de', '0x1b80', first_boot, '0x030000'),
                    ('0x10de', '0x1e04', second_boot, '0x030000')])
                result = self.select(fixture)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'nvidia-'+expected)
                self.assertIn('mixed', result.stderr)

    def test_incomplete_payload_fails_without_exposing_a_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.fixture(Path(tmp), [('0x10de', '0x1b80', '1', '0x030000')])
            (fixture[1]/'nvidia-drivers/r580/usr/lib/libcuda.so.1').unlink()
            result = self.select(fixture)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((fixture[2]/'nvidia-driver').is_symlink())
            self.assertFalse((fixture[2]/'modprobe.d/nvidia-hdr-depth.conf').exists())

    def test_incomplete_firmware_fails_without_exposing_a_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.fixture(Path(tmp), [('0x10de', '0x1b80', '1', '0x030000')])
            (fixture[1]/'kernel-overlays/nvidia-r580/lib/firmware/nvidia/580.178.04/gsp-test.bin').unlink()
            result = self.select(fixture)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((fixture[2]/'nvidia-driver').is_symlink())

    def test_repeat_setup_removes_r615_only_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.fixture(Path(tmp), [('0x10de', '0x1e04', '1', '0x030000')])
            self.assertEqual(self.select(fixture).returncode, 0)
            (fixture[0]/'bus/pci/devices/0000:01:00.0/device').write_text('0x1b80\n')
            self.assertEqual(self.select(fixture).returncode, 0)
            self.assertFalse((fixture[2]/'modprobe.d/nvidia-hdr-depth.conf').exists())

    def test_module_override_is_detected_before_overlay_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); module = base/'lib/modules/test/extra/nvidia-drm.ko.xz'
            module.parent.mkdir(parents=True); module.write_bytes(b'wrong-branch')
            result = subprocess.run(['sh', '-ec', '. "$1"; '
                'nvidia_overlay_conflicts "$2"', 'check', str(SELECTOR), str(base)], capture_output=True)
            self.assertEqual(result.returncode, 0)
            linked = base/'linked/lib/modules'
            linked.parent.mkdir(parents=True)
            linked.symlink_to(base/'lib/modules', target_is_directory=True)
            result = subprocess.run(['sh', '-ec', '. "$1"; '
                'nvidia_overlay_conflicts "$2"', 'check', str(SELECTOR), str(base/'linked')], capture_output=True)
            self.assertEqual(result.returncode, 0, 'symlinked module overrides must also be rejected')
            module.unlink()
            result = subprocess.run(['sh', '-ec', '. "$1"; '
                'nvidia_overlay_conflicts "$2"', 'check', str(SELECTOR), str(base)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_native_overlay_caller_installs_one_stack_and_propagates_failure(self):
        native = (ROOT/'packages/sysutils/busybox/scripts/kernel-overlays-setup').read_text()
        for failure in ('none', 'payload', 'depmod'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                sys, lib, run = self.fixture(base, [('0x10de', '0x1b80', '1', '0x030000')])
                (lib/'nvidia-drivers/select-driver').write_bytes(SELECTOR.read_bytes())
                user = base/'storage/.cache/kernel-overlays'; user.mkdir(parents=True)
                override = base/'override/lib/modules/test/extra/nvidia.ko'
                override.parent.mkdir(parents=True); override.write_bytes(b'foreign-module')
                (user/'foreign.conf').write_text(str(base/'override'))
                if failure == 'payload':
                    (lib/'nvidia-drivers/r580/driver-version').unlink()
                depmod = base/'depmod'
                depmod.write_text('#!/bin/sh\nexit '+('1' if failure == 'depmod' else '0')+'\n')
                depmod.chmod(0o755)
                script = native.replace('KVER=$(uname -r)', 'KVER=test')
                for old, new in [('/usr/lib', str(lib)), ('/storage', str(base/'storage')),
                                 ('/run', str(run)), ('/sys ', str(sys)+' '),
                                 ('/dev/kmsg', str(base/'kmsg')), ('/usr/sbin/depmod', str(depmod))]:
                    script = script.replace(old, new)
                caller = base/'overlay-setup'; caller.write_text(script)
                result = subprocess.run(['sh', str(caller)], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, failure == 'none', result.stderr)
                modules = list((run/'kernel-overlays/modules/test').rglob('*.ko'))
                if failure == 'payload':
                    self.assertEqual(modules, [])
                    self.assertFalse((run/'nvidia-driver').exists())
                else:
                    self.assertEqual(len(modules), 4)
                    self.assertTrue(all(p.read_bytes() == b'r580' for p in modules))
        init = (ROOT/'packages/sysutils/busybox/scripts/init').read_text()
        self.assertIn('if ! /usr/bin/busybox chroot /sysroot /usr/sbin/kernel-overlays-setup; then', init)
        self.assertIn('exec /usr/bin/busybox chroot /sysroot /bin/sh', init)


if __name__ == '__main__':
    unittest.main()
