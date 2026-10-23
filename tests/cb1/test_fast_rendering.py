"""Run native frame-timing and legacy-setting helpers against literal boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FastRenderingTests(unittest.TestCase):
    def test_headroom_continuity_and_legacy_values(self):
        program = r'''
#include <cassert>
#include "DVBridgeFastRendering.h"
int main()
{
  assert(DVBRIDGE::PresentationHeadroom(100000000, 120000000, 125000000, 133000000, 33000000) == 8000000);
  assert(DVBRIDGE::PresentationHeadroom(100000000, 140000000, 139000000, 166000000, 33000000) == -7000000);
  assert(!DVBRIDGE::PresentationHeadroom(0, 120000000, 125000000, 133000000, 33000000));
  assert(!DVBRIDGE::PresentationHeadroom(100000000, 170000000, 125000000, 133000000, 33000000));
  assert(!DVBRIDGE::PresentationHeadroom(100000000, 120000000, 125000000, 400000000, 33000000));
  assert(DVBRIDGE::LegacyFastRendering("false") == 0);
  assert(DVBRIDGE::LegacyFastRendering("true") == 1);
  assert(DVBRIDGE::LegacyFastRendering("True") == 1);
  assert(!DVBRIDGE::LegacyFastRendering("2"));
  assert(!DVBRIDGE::LegacyFastRendering("invalid"));
  assert(DVBRIDGE::ContinuousFastRenderingPicture(11700000,11666666));
  assert(!DVBRIDGE::ContinuousFastRenderingPicture(11700000,11700000));
  assert(!DVBRIDGE::ContinuousFastRenderingPicture(1000000,2000000));
  assert(!DVBRIDGE::ContinuousFastRenderingPicture(80000000,2000000));
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            source, binary = Path(temporary) / 'check.cpp', Path(temporary) / 'check'
            patch = (ROOT / 'projects/Generic/patches/kodi/kodi-9999-zz-beta3.patch').read_text()
            section = patch.split('+++ b/xbmc/utils/DVBridgeFastRendering.h\n', 1)[1].split('\n--- ', 1)[0]
            header = '\n'.join(line[1:] for line in section.splitlines() if line.startswith('+')) + '\n'
            (Path(temporary) / 'DVBridgeFastRendering.h').write_text(header)
            source.write_text(program)
            result = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                     '-I', temporary,
                                     str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
