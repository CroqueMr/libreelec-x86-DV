"""Run the engine's own L5 overlay/metadata contract against the matched FFmpeg."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DolbyVisionAbsentL5(unittest.TestCase):
    def test_engine_overlay_metadata_contract(self):
        """CB1/tests/overlay_metadata.c with the shipped dvbridge_core.c.

        An RPU without L5 transmits none, with or without an overlay; borders added by the
        player's own placement are still described; an authored L5 keeps its margins and
        reports the full raster while an overlay is visible."""
        prefix = os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:
            self.skipTest('Matched FFmpeg test prefix required')
        prefix = Path(prefix)
        # The IPT transport matrices live in the GPU unit; take just the shipped definitions.
        ipt = re.findall(r'^const int16_t cb1_ipt_output_(?:ycc|lms)\[9\]=\{[^}]+\};$',
                         (ROOT / 'CB1/src/cb1_master_ipt.c').read_text(), re.M)
        self.assertEqual(len(ipt), 2)
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / 'overlay_metadata'
            constants = Path(temporary) / 'ipt.c'
            constants.write_text('#include <stdint.h>\n' + '\n'.join(ipt) + '\n')
            built = subprocess.run(['cc', '-std=c11', '-UNDEBUG', '-fsanitize=address,undefined',
                                    '-I' + str(ROOT / 'CB1/src'), '-I' + str(prefix / 'include'),
                                    str(ROOT / 'CB1/tests/overlay_metadata.c'),
                                    str(ROOT / 'CB1/src/dvbridge_core.c'), str(constants),
                                    '-L' + str(prefix / 'lib'), '-lavutil', '-lm', '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr[-6000:])
            env = dict(os.environ, LD_LIBRARY_PATH=str(prefix / 'lib') + ':' +
                       os.environ.get('LD_LIBRARY_PATH', ''))
            ran = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == '__main__':
    unittest.main()
