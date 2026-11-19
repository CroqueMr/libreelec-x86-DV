"""Catch missing early primary acquisition and lost errors in Intel recovery."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_hdr10plus_kernel import function


class IntelRecoveryTests(unittest.TestCase):
    def test_existing_primary_and_acquisition_errors(self):
        location = os.environ.get('CB1_KERNEL_SOURCE')
        if not location:
            self.skipTest('Set CB1_KERNEL_SOURCE to the matched patched kernel')
        kernel = Path(location)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            connector = (kernel / 'drivers/gpu/drm/drm_connector.c').read_text()
            display = (kernel / 'drivers/gpu/drm/i915/display/intel_display.c').read_text()
            (root / 'frame_mask.inc').write_text(function(connector, 'drm_atomic_hdr10plus_frame_mask'))
            (root / 'recovery.inc').write_text(function(display, 'intel_modeset_commit_pipes'))
            binary = root / 'recovery'
            compiled = subprocess.run(['cc', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-function', '-fsanitize=address,undefined', '-fno-pie', '-no-pie',
                '-I' + str(root), str(Path(__file__).with_name('hdr10plus_recovery.c')),
                '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
