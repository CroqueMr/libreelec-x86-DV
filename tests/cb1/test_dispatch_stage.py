"""Compile the stage-isolation check against the matched libplacebo source/build."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class DispatchStageTests(unittest.TestCase):
    def test_custom_fragment_and_compute_preludes_do_not_enter_vertex_shader(self):
        if not os.environ.get('LIBPLACEBO_TEST_SOURCE') or not os.environ.get('LIBPLACEBO_TEST_BUILD'):
            self.skipTest('set LIBPLACEBO_TEST_SOURCE and LIBPLACEBO_TEST_BUILD to matched libplacebo')
        source = Path(os.environ['LIBPLACEBO_TEST_SOURCE'])
        build = Path(os.environ['LIBPLACEBO_TEST_BUILD'])
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / 'dispatch-stage'
            command = ['cc', '-std=gnu11', '-D_GNU_SOURCE', '-pthread',
                       '-I'+str(source/'src'), '-I'+str(build/'src'),
                       '-I'+str(source/'src/include'), '-I'+str(build/'src/include'),
                       str(Path(__file__).with_name('dispatch_stage.c')),
                       '-L'+str(build/'src'), '-Wl,-rpath,'+str(build/'src'),
                       '-lplacebo', '-lm', '-o', str(executable)]
            compiled = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([str(executable)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
