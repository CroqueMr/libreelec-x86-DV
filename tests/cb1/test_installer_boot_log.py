"""Execute the installer collector against a boot-media fixture, without mounting host disks."""
import configparser
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LOGGER = ROOT/'packages/sysutils/busybox/scripts/installer-boot-log'
UNIT = ROOT/'packages/sysutils/busybox/system.d/installer-boot-log.service'


class InstallerBootLog(unittest.TestCase):
    def fixture(self, base, *, mode='installer', fs='vfat', options='ro', room=300000, fail_mount=False):
        self.assertTrue(LOGGER.is_file(), 'installer logs need a collector outside volatile /storage')
        for name in ('flash', 'run', 'proc', 'bin'):
            (base/name).mkdir()
        (base/'proc/cmdline').write_text('boot=UUID=test '+mode+'\n')
        (base/'proc/sys/kernel/random').mkdir(parents=True)
        (base/'proc/sys/kernel/random/boot_id').write_text('fixture-boot-id\n')
        (base/'proc/mounts').write_text(f'/dev/test {base}/flash {fs} {options} 0 0\n')
        script = LOGGER.read_text()
        for name in ('flash', 'run', 'proc'):
            script = script.replace(name+'=/'+name, name+'='+str(base/name))
        (base/'collector').write_text(script)
        (base/'bin/mount').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$FIXTURE/mounts.log"\nexit '+('1' if fail_mount else '0')+'\n')
        (base/'bin/df').write_text('#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/test 1000000 1 '+str(room)+' 1%% /flash\\n"\n')
        (base/'bin/journalctl').write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$FIXTURE/journal.args"\ncat "$FIXTURE/messages"\n')
        for p in (base/'bin').iterdir():
            p.chmod(0o755)
        (base/'messages').write_text('kernel: snd_virtuoso probe\nservice: NVIDIA ready\n')
        env = dict(os.environ, FIXTURE=str(base), PATH=str(base/'bin')+':'+os.environ['PATH'])
        return env

    def run_collector(self, base, env, action='start'):
        result = subprocess.run(['sh', str(base/'collector'), action], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_failed_boot_trace_survives_next_installer_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);env=self.fixture(base);folder=base/'flash/cb1-boot-logs'
            folder.mkdir();(folder/'current.log').write_text('previous failed boot\n')
            (folder/'previous.log').write_text('obsolete boot\n')
            self.run_collector(base,env)
            self.assertEqual((folder/'previous.log').read_text(),'previous failed boot\n')
            self.assertIn('snd_virtuoso probe',(folder/'current.log').read_text())
            self.assertIn('--lines=all',(base/'journal.args').read_text())
            self.assertIn('--follow',(base/'journal.args').read_text())
            mounts=(base/'mounts.log').read_text()
            self.assertIn('remount,rw',mounts);self.assertIn('remount,ro',mounts)
            self.assertFalse((base/'run/installer-boot-log-remounted').exists())

    def test_non_installer_low_space_network_and_read_only_failures_do_not_change_boot(self):
        for kwargs in ({'mode':'foo=installer'}, {'room':100}, {'fs':'nfs'}, {'fail_mount':True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);env=self.fixture(base,**kwargs)
                self.run_collector(base,env)
                self.assertFalse((base/'journal.args').exists())
                self.assertFalse((base/'flash/cb1-boot-logs').exists())

    def test_size_is_bounded_and_original_writable_mount_stays_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);env=self.fixture(base,options='rw')
            (base/'messages').write_bytes(b'x'*(9*1024*1024))
            self.run_collector(base,env)
            self.assertEqual((base/'flash/cb1-boot-logs/current.log').stat().st_size,8*1024*1024)
            self.assertFalse((base/'mounts.log').exists())

    def test_preparation_failure_restores_read_only_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);env=self.fixture(base)
            (base/'flash/cb1-boot-logs').write_text('existing file\n')
            self.run_collector(base,env)
            self.assertEqual((base/'flash/cb1-boot-logs').read_text(),'existing file\n')
            self.assertIn('remount,ro',(base/'mounts.log').read_text())
            self.assertFalse((base/'run/installer-boot-log-remounted').exists())

    def test_early_service_does_not_require_or_delay_graphical_clients(self):
        self.assertTrue(UNIT.is_file())
        config=configparser.ConfigParser(interpolation=None);config.read(UNIT)
        self.assertEqual(config['Unit']['ConditionKernelCommandLine'],'installer')
        self.assertEqual(config['Unit']['DefaultDependencies'],'no')
        self.assertIn('systemd-journald.service',config['Unit']['After'])
        self.assertIn('flash.mount',config['Unit']['After'])
        self.assertIn('shutdown.target',config['Unit']['Conflicts'])
        self.assertIn('systemd-udevd.service',config['Unit']['Before'])
        self.assertEqual(config['Service']['Type'],'simple')
        self.assertEqual(config['Service']['RuntimeMaxSec'],'10min')
        self.assertIn(' stop',config['Service']['ExecStopPost'])
        for name in ('packages/tools/installer/system.d/installer.service',
                     'packages/mediacenter/kodi/system.d/kodi.service'):
            self.assertNotIn('Requires=installer-boot-log',(ROOT/name).read_text())
