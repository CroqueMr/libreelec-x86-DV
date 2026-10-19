# SPDX-License-Identifier: MIT
"""Keep base helper libraries needed by the packaged VAAPI driver."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

RECIPE = Path(__file__).resolve().parents[2] / 'packages/multimedia/gstreamer/gst-plugins-base/package.mk'


class GStreamerRuntimeTests(unittest.TestCase):
    def test_cleanup_retains_helper_libraries_without_plugins(self):
        cleanup = 'post_makeinstall_target() {' + RECIPE.read_text().split('post_makeinstall_target() {', 1)[1]
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / 'install'
            files = ('usr/lib/libgstvideo-1.0.so.0', 'usr/lib/libgstallocators-1.0.so.0',
                     'usr/lib/gstreamer-1.0/plugin.so', 'usr/share/doc/readme')
            for name in files:
                path = install / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            guard = '''safe_remove() {
              for target; do
                test -e "$target" || return 1
                case "$target" in "$INSTALL"|"$INSTALL"/*) rm -rf -- "$target";; *) return 1;; esac
              done
            }
            '''
            result = subprocess.run(['bash', '-e', '-c', guard + cleanup + '\npost_makeinstall_target'],
                                    env=dict(os.environ, INSTALL=str(install)), capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            for name in files[:2]:
                self.assertEqual((install / name).read_bytes(), name.encode())
            for name in files[2:]:
                self.assertFalse((install / name).exists(), name)
