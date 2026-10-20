# SPDX-License-Identifier: MIT
"""Exercise the shipped selector against disposable offline boot filesystems."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "projects/Generic/filesystem/usr/bin/cb1-driver-profile"
PACKAGER = ROOT / "scripts/cb1-debug-profiles.py"
ORDINARY = {"ordinary.patch": "b" * 64}
GRAPHICS = {"gpu.patch": "f" * 64}
BUILD = {"id": "fixture-debug", "linux_version": "7.2.6",
         "linux_source_sha256": "a" * 64,
         "ordinary_patches_sha256": hashlib.sha256(json.dumps(ORDINARY, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
         "userspace": {"kodi": "c" * 64, "cb1": "d" * 64, "mesa": "e" * 64}}


class DriverProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.flash = self.root / "flash"
        for path in ("etc/cb1-debug", "usr/share/cb1/driver-profile-build.json",
                     "proc/cmdline", "proc/sys/kernel/osrelease", "flash/syslinux.cfg",
                     "flash/EFI/BOOT/grub.cfg"):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / "etc/cb1-debug").touch()
        (self.root / "usr/share/cb1/driver-profile-build.json").write_text(json.dumps(BUILD))
        (self.root / "proc/cmdline").write_text("BOOT_IMAGE=/KERNEL boot=UUID=ABCD disk=UUID=EFGH quiet")
        (self.root / "proc/sys/kernel/osrelease").write_text("7.2.6-modified\n")
        (self.flash / "syslinux.cfg").write_text(
            "DEFAULT linux\nPROMPT 0\nLABEL linux\n KERNEL /KERNEL\n"
            " APPEND boot=UUID=ABCD disk=UUID=EFGH quiet\n")
        (self.flash / "EFI/BOOT/grub.cfg").write_text(
            'set default="LibreELEC"\nmenuentry "LibreELEC" {\n'
            '\tsearch --set -f /KERNEL\n'
            '\tlinux /KERNEL boot=UUID=ABCD disk=UUID=EFGH quiet\n}\n')
        self.manifest = {"schema": 1, "build": BUILD, "profiles": {}}
        for profile in ("modified", "standard"):
            pair = {"kernel_release": "7.2.6-" + profile, "modules_sha256": "f" * 64}
            for kind in ("kernel", "system"):
                path = kind.upper() if profile == "modified" else "cb1/" + kind.upper() + ".standard"
                target = self.flash / path
                target.parent.mkdir(parents=True, exist_ok=True)
                data = (profile + kind).encode()
                target.write_bytes(data)
                pair[kind] = {"path": path, "size": len(data),
                              "sha256": hashlib.sha256(data).hexdigest()}
            self.manifest["profiles"][profile] = pair
        self.save_manifest()

    def save_manifest(self):
        (self.flash / "cb1/driver-profiles.json").write_text(json.dumps(self.manifest))
        names = ("KERNEL", "SYSTEM", "cb1/KERNEL.standard", "cb1/SYSTEM.standard", "cb1/driver-profiles.json")
        (self.flash / "cb1/driver-profiles.sha256").write_text("".join(
            hashlib.sha256((self.flash / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in names))

    def call(self, *args, success=True):
        result = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertTrue(result.stdout, result.stderr)
        return json.loads(result.stdout)

    def test_status_is_read_only_and_distinguishes_pending_from_active(self):
        before = {p: p.read_bytes() for p in self.flash.rglob("*") if p.is_file()}
        state = self.call("status")
        self.assertEqual((state["active"], state["pending"], state["available"]),
                         ("modified", "modified", True))
        self.assertEqual(before, {p: p.read_bytes() for p in self.flash.rglob("*") if p.is_file()})
        state = self.call("select", "standard")
        self.assertEqual((state["active"], state["pending"]), ("modified", "standard"))
        self.assertEqual(self.call("status")["pending"], "standard")
        for path in ("syslinux.cfg", "EFI/BOOT/grub.cfg"):
            text = (self.flash / path).read_text()
            self.assertIn("boot=UUID=ABCD disk=UUID=EFGH", text)
            self.assertIn("SYSTEM_IMAGE=/cb1/SYSTEM.standard", text)
            self.assertIn("cb1-modified-recovery", text)
            self.assertIn("SYSTEM_IMAGE=/SYSTEM", text)
        self.assertEqual(self.call("select", "modified")["pending"], "modified")

    def test_select_refuses_corruption_without_changing_either_bootloader(self):
        (self.flash / "cb1/SYSTEM.standard").write_bytes(b"bad" * 6)
        before = (self.flash / "syslinux.cfg").read_bytes()
        self.call("select", "standard", success=False)
        self.assertEqual((self.flash / "syslinux.cfg").read_bytes(), before)

    def test_select_rehashes_even_same_size_payload(self):
        path = self.flash / "cb1/SYSTEM.standard"
        path.write_bytes(b"!" * path.stat().st_size)
        self.assertTrue(self.call("status")["available"])
        state = self.call("select", "standard", success=False)
        self.assertIn("hash", state["reason"].lower())

    def test_normal_build_cannot_select(self):
        (self.root / "etc/cb1-debug").unlink()
        self.assertFalse(self.call("status")["available"])
        self.call("select", "standard", success=False)

    def test_malformed_manifest_still_returns_refusal_json(self):
        self.manifest["profiles"]["standard"]["kernel_release"] = 7
        self.save_manifest()
        self.assertFalse(self.call("status")["available"])
        self.call("select", "standard", success=False)

    def test_status_does_not_repeat_full_patch_provenance_in_ui_or_boot_log(self):
        self.manifest["profiles"]["modified"]["patches"] = {"patch" + str(i): "f" * 64 for i in range(200)}
        self.save_manifest()
        state = self.call("status")
        self.assertLess(len(json.dumps(state)), 4096)
        self.assertIn("sha256", state["payloads"]["system"])

    def test_wrong_build_and_kernel_release_are_refused(self):
        self.manifest["build"] = dict(BUILD, id="other")
        self.save_manifest()
        self.assertFalse(self.call("status")["available"])
        self.manifest["build"] = BUILD
        self.save_manifest()
        (self.root / "proc/sys/kernel/osrelease").write_text("7.2.6-unknown")
        self.assertFalse(self.call("status")["available"])

    def test_mismatched_boot_pair_and_bootloader_defaults_are_refused(self):
        (self.root / "proc/cmdline").write_text("BOOT_IMAGE=/KERNEL SYSTEM_IMAGE=/cb1/SYSTEM.standard")
        self.assertFalse(self.call("status")["available"])
        (self.root / "proc/cmdline").write_text("BOOT_IMAGE=/KERNEL")
        (self.flash / "EFI/BOOT/grub.cfg").write_text('set default="Missing"\n')
        self.call("select", "standard", success=False)

    def test_symlink_payload_and_unexpected_paths_are_refused(self):
        self.manifest["profiles"]["standard"]["kernel"]["path"] = "../outside"
        self.save_manifest()
        self.call("select", "standard", success=False)
        self.manifest["profiles"]["standard"]["kernel"]["path"] = "cb1/KERNEL.standard"
        self.save_manifest()
        if os.name != "nt":
            path = self.flash / "cb1/KERNEL.standard"
            path.rename(self.root / "outside")
            path.symlink_to(self.root / "outside")
            self.call("select", "standard", success=False)

    def test_live_modes_preserved_and_recovery_does_not_accumulate(self):
        (self.flash / "syslinux.cfg").write_text(
            "DEFAULT run\nLABEL live\n KERNEL /KERNEL\n APPEND boot=UUID=ABCD live quiet\n"
            "LABEL run\n KERNEL /KERNEL\n APPEND boot=UUID=ABCD disk=UUID=EFGH portable quiet\n")
        (self.flash / "EFI/BOOT/grub.cfg").unlink()
        self.call("select", "standard")
        first = (self.flash / "syslinux.cfg").read_bytes()
        self.call("select", "standard")
        self.assertEqual(first, (self.flash / "syslinux.cfg").read_bytes())
        self.assertIn(b"portable quiet", first)
        self.assertIn(b"live quiet", first)

    def test_second_bootloader_write_failure_rolls_back_first(self):
        before = {name: (self.flash / name).read_bytes() for name in ("syslinux.cfg", "EFI/BOOT/grub.cfg")}
        program = """
import os, runpy, sys
from pathlib import Path
runtime = runpy.run_path(sys.argv[1])
replace = os.replace
def fail_second(source, destination):
    if Path(destination).name == 'grub.cfg':
        raise PermissionError('fixture second bootloader is read-only')
    return replace(source, destination)
os.replace = fail_second
sys.exit(runtime['main'](['--root', sys.argv[2], 'select', 'standard']))
"""
        result = subprocess.run([sys.executable, "-c", program, str(CLI), str(self.root)],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["available"])
        self.assertEqual(before, {name: (self.flash / name).read_bytes() for name in before})

    def test_paired_install_uses_manifest_pairs_not_current_standard_images(self):
        self.call("check-install", str(64 * 1024 * 1024))
        self.call("check-install", "100", success=False)
        (self.root / "proc/cmdline").write_text(
            "BOOT_IMAGE=/cb1/KERNEL.standard SYSTEM_IMAGE=/cb1/SYSTEM.standard")
        (self.root / "proc/sys/kernel/osrelease").write_text("7.2.6-standard")
        target = self.root / "installed"
        target.mkdir()
        shutil.copytree(self.flash / "EFI", target / "EFI")
        shutil.copyfile(self.flash / "syslinux.cfg", target / "syslinux.cfg")
        self.call("install", str(target))
        self.assertEqual((target / "KERNEL").read_bytes(), b"modifiedkernel")
        self.assertEqual((target / "SYSTEM").read_bytes(), b"modifiedsystem")
        self.assertEqual((target / "cb1/SYSTEM.standard").read_bytes(), b"standardsystem")
        self.assertEqual(json.loads((target / "cb1/driver-profiles.json").read_text()), self.manifest)
        for line in (target / "cb1/driver-profiles.sha256").read_text().splitlines():
            value, name = line.split("  ")
            self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), value)
        self.assertIn("cb1-modified-recovery", (target / "syslinux.cfg").read_text())


@unittest.skipUnless(shutil.which("mksquashfs") and shutil.which("unsquashfs"), "squashfs tools required")
class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = {"build": BUILD, "profiles": {}}
        self.policy = self.root / "policy.json"
        self.policy.write_text(json.dumps({"schema": 1, "linux_source_sha256": "a" * 64,
                                           "ordinary_patches": ORDINARY, "graphics_patches": GRAPHICS}))
        for profile in ("modified", "standard"):
            tree = self.root / (profile + "-root")
            for path, data in {"etc/cb1-debug": "",
                               "usr/share/cb1/driver-profile-build.json": json.dumps(BUILD),
                               "usr/lib/kodi/kodi.bin": "same kodi",
                               "usr/lib/libcb1.so": "same cb1",
                               "usr/lib/dri/iris_dri.so": "same mesa",
                               "usr/lib/kernel-overlays/base/lib/modules/7.2.6-" + profile + "/test.ko":
                               "\0vermagic=7.2.6-" + profile + " SMP\0"}.items():
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(data)
            kernel = self.root / (profile + ".kernel")
            kernel.write_bytes(profile.encode())
            system = self.root / (profile + ".system")
            self.squash(tree, system)
            self.evidence["profiles"][profile] = {
                "kernel": str(kernel), "system": str(system),
                "kernel_sha256": hashlib.sha256(kernel.read_bytes()).hexdigest(),
                "system_sha256": hashlib.sha256(system.read_bytes()).hexdigest(),
                "kernel_release": "7.2.6-" + profile,
                "patches": dict(ORDINARY, **GRAPHICS) if profile == "modified" else ORDINARY}

    def squash(self, tree, output):
        subprocess.run(["mksquashfs", str(tree), str(output), "-noappend", "-processors", "1", "-quiet"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def call(self, success=True):
        evidence = self.root / "evidence.json"
        evidence.write_text(json.dumps(self.evidence))
        result = subprocess.run([sys.executable, str(PACKAGER), "--evidence", str(evidence),
                                 "--policy", str(self.policy), "--output", str(self.root / "output")], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_verified_pairs_are_packaged_without_rebuilding_them(self):
        self.call()
        output = self.root / "output"
        self.assertEqual((output / "KERNEL").read_bytes(), b"modified")
        self.assertEqual((output / "cb1/KERNEL.standard").read_bytes(), b"standard")
        manifest = json.loads((output / "cb1/driver-profiles.json").read_text())
        self.assertEqual(manifest["build"], BUILD)
        self.assertNotEqual(manifest["profiles"]["modified"]["modules_sha256"],
                            manifest["profiles"]["standard"]["modules_sha256"])
        subprocess.run(["sha256sum", "-c", "cb1/driver-profiles.sha256"], cwd=output, check=True,
                       stdout=subprocess.DEVNULL)
        result = subprocess.run([sys.executable, str(PACKAGER), "--check", str(output),
                                 "--policy", str(self.policy), "--capacity", str(64 * 1024 * 1024),
                                 "--kernel", str(self.root / "modified.kernel"),
                                 "--system", str(self.root / "modified.system")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_packaging_refuses_mismatched_userspace_even_with_valid_evidence_hash(self):
        tree = self.root / "standard-root"
        (tree / "usr/lib/kodi/kodi.bin").write_text("different kodi")
        system = self.root / "standard.system"
        self.squash(tree, system)
        self.evidence["profiles"]["standard"]["system_sha256"] = hashlib.sha256(system.read_bytes()).hexdigest()
        self.call(success=False)
        self.assertFalse((self.root / "output").exists())

    def test_packaging_refuses_wrong_kernel_hash_or_modified_standard_policy(self):
        self.evidence["profiles"]["standard"]["kernel_sha256"] = "0" * 64
        self.call(success=False)
        self.evidence["profiles"]["standard"]["kernel_sha256"] = hashlib.sha256(b"standard").hexdigest()
        self.evidence["profiles"]["standard"]["patches"] = dict(ORDINARY, **GRAPHICS)
        self.call(success=False)

    def test_patch_provenance_must_match_independent_expected_policy(self):
        self.evidence["profiles"]["modified"]["patches"] = {}
        self.call(success=False)
        self.evidence["profiles"]["modified"]["patches"] = dict(ORDINARY, **GRAPHICS)
        policy = json.loads(self.policy.read_text())
        policy["ordinary_patches"] = {"missing.patch": "a" * 64}
        self.policy.write_text(json.dumps(policy))
        self.call(success=False)

    def test_packaging_refuses_wrong_module_vermagic_despite_release_directory(self):
        tree = self.root / "standard-root"
        module = tree / "usr/lib/kernel-overlays/base/lib/modules/7.2.6-standard/test.ko"
        module.write_bytes(b"\0vermagic=7.2.6-modified SMP\0")
        system = self.root / "standard.system"
        self.squash(tree, system)
        self.evidence["profiles"]["standard"]["system_sha256"] = hashlib.sha256(system.read_bytes()).hexdigest()
        self.call(success=False)


@unittest.skipUnless(os.name == "posix", "native shell required")
class NativeHookTests(unittest.TestCase):
    def test_initramfs_includes_the_required_sha256_applet(self):
        config = (ROOT / "packages/sysutils/busybox/config/busybox-init.conf").read_text()
        self.assertTrue(re.search(r"(?m)^CONFIG_SHA256SUM=y$", config),
                        "paired updater needs SHA256 in initramfs, not only target SYSTEM")

    def run_function(self, relative, name, body, replacements=None):
        text = (ROOT / relative).read_text()
        self.assertTrue(name + "() {" in text, "native guard is not implemented")
        start = text.index(name + "() {")
        end = start + re.search(r"\n}\n(?=\n[a-z_]+\(\))", text[start:]).end()
        function = text[start:end]
        for before, after in (replacements or {}).items():
            function = function.replace(before, after)
        return subprocess.run(["bash", "-c", function + "\n" + body], capture_output=True, text=True)

    def test_updater_debug_guard_refuses_old_or_new_debug_and_allows_normal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in ("sysroot/etc", "update/etc", "flash/cb1"):
                (root / path).mkdir(parents=True)
            replacements = {"/sysroot/": str(root / "sysroot") + "/",
                            "/update/": str(root / "update") + "/",
                            "/flash/": str(root / "flash") + "/"}
            def run():
                return self.run_function("packages/sysutils/busybox/scripts/init", "cb1_update_allowed",
                                         "cb1_update_allowed", replacements)
            self.assertEqual(run().returncode, 0)
            for marker in ("sysroot/etc/cb1-debug", "update/etc/cb1-debug", "flash/cb1/driver-profiles.json"):
                path = root / marker
                path.touch()
                self.assertNotEqual(run().returncode, 0)
                path.unlink()

    def test_installer_preflight_refuses_before_any_disk_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cb1-debug").touch()
            helper = root / "helper"
            helper.write_text("#!/bin/sh\nexit 1\n")
            helper.chmod(0o755)
            result = self.run_function("packages/tools/installer/scripts/installer", "do_install_quick",
                                       "whiptail() { :; }; create_device_list() { echo DESTRUCTIVE; return 1; }; "
                                       'TMPDIR="' + str(root) + '"; LOGFILE="' + str(root / "log") + '"; '
                                       "PARTSIZE_SYSTEM=1024; do_install_quick",
                                       {"/etc/cb1-debug": str(root / "cb1-debug"),
                                        "/usr/bin/cb1-driver-profile": str(helper)})
            self.assertNotIn("DESTRUCTIVE", result.stdout)
            self.assertEqual(result.returncode, 1, result.stderr)
            helper.write_text("#!/bin/sh\nexit 0\n")
            result = self.run_function("packages/tools/installer/scripts/installer", "do_install_quick",
                                       "whiptail() { :; }; create_device_list() { echo SAFE_SELECTION; return 1; }; "
                                       'TMPDIR="' + str(root) + '"; LOGFILE="' + str(root / "log") + '"; '
                                       "PARTSIZE_SYSTEM=1024; do_install_quick",
                                       {"/etc/cb1-debug": str(root / "cb1-debug"),
                                        "/usr/bin/cb1-driver-profile": str(helper)})
            self.assertIn("SAFE_SELECTION", result.stdout)

    def test_paired_updater_verifies_and_writes_fixed_pairs_preserving_boot_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, flash = root / "incoming", root / "flash"
            for path in ("sysroot/etc/cb1-debug", "update/etc/cb1-debug"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            names = ("KERNEL", "SYSTEM", "cb1/KERNEL.standard", "cb1/SYSTEM.standard", "cb1/driver-profiles.json")
            sums = []
            for name in names:
                for directory, prefix in ((source, "new:"), (flash, "old:")):
                    target = directory / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(prefix + name)
                sums.append(hashlib.sha256((source / name).read_bytes()).hexdigest() + "  " + name + "\n")
            (source / "cb1/driver-profiles.sha256").write_text("".join(sums))
            (flash / "syslinux.cfg").write_text("DEFAULT standard\n")
            replacements = {"/sysroot/": str(root / "sysroot") + "/",
                            "/update/": str(root / "update") + "/",
                            "/flash/": str(flash) + "/", '"/flash"': '"' + str(flash) + '"'}
            init = "packages/sysutils/busybox/scripts/init"
            def invoke(body):
                # Run the real read-only preflight and fixed-path writer with only mounts replaced.
                allowed = self.run_function(init, "cb1_update_allowed", "declare -f cb1_update_allowed", replacements)
                native = ""
                if os.environ.get("CB1_INIT_BUSYBOX"):
                    for applet in ("stat", "df", "awk"):
                        native += applet + '() { "' + os.environ["CB1_INIT_BUSYBOX"] + '" ' + applet + ' "$@"; };\n'
                return self.run_function(init, "cb1_write_update", allowed.stdout +
                    '\nUPDATE_DIR="' + str(source) + '"\nmount() { :; }; umount() { :; };\n' + native + body, replacements)
            result = invoke("cb1_update_allowed && cb1_write_update")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((flash / "syslinux.cfg").read_text(), "DEFAULT standard\n")
            for name in names:
                self.assertEqual((flash / name).read_bytes(), (source / name).read_bytes())
            self.assertNotEqual(invoke('df() { printf "Filesystem 1024-blocks Used Available Capacity Mounted on\\nfixture 1 1 0 100%% /flash\\n"; }; cb1_update_allowed').returncode, 0)
            (source / "cb1/SYSTEM.standard").write_text("corrupt")
            self.assertNotEqual(invoke("cb1_update_allowed").returncode, 0)
            (source / "cb1/driver-profiles.sha256").write_text("".join(sums) + "0" * 64 + "  ../outside\n")
            self.assertNotEqual(invoke("cb1_update_allowed").returncode, 0)

    def test_mkimage_refuses_debug_without_verified_pairs_before_disk_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / "bin"
            stub.mkdir()
            (stub / "dd").write_text("#!/bin/sh\nexit 91\n")
            (stub / "dd").chmod(0o755)
            env = dict(os.environ, PATH=str(stub) + ":" + os.environ["PATH"],
                       TARGET_IMG=str(root), IMAGE_NAME="fixture", BUILD_NAME="fixture",
                       PROJECT="Generic", BOOTLOADER="syslinux", KERNEL_NAME="KERNEL",
                       SCRIPTS=str(ROOT / "scripts"), CB1_DEBUG="yes",
                       CB1_DEBUG_PROFILES_DIR="", SYSTEM_SIZE="1024", SYSTEM_PART_START="2048")
            result = subprocess.run(["bash", str(ROOT / "scripts/mkimage")], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("paired Debug", result.stdout + result.stderr)
            self.assertFalse((root / "fixture.img").exists())


if __name__ == "__main__":
    unittest.main()
