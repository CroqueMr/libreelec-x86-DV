"""Run the actual common controller against hand-derived timing sequences."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FastRenderingTests(unittest.TestCase):
    def test_threshold_bursts_exclusions_latch_and_reset(self):
        program = r'''
#include <cassert>
#include "DVBridgeFastRendering.h"
int main()
{
  DVBRIDGE::FastRendering controller;
  DVBRIDGE::FastRendering startup;
  for (unsigned i=1; i<=100; ++i)
    assert(!startup.Observe(i*20000000ULL, -1000000, true));
  assert(!startup.Enabled());
  auto warm = [&]() {
    for (unsigned i=1; i<=8; ++i) assert(!controller.Observe(i*20000000ULL, 30000000, true));
    assert(!controller.Observe(8100000000ULL,30000000,true));
  };
  constexpr uint64_t settled = 8100000000ULL;
  auto observe = [&](uint64_t now, int64_t margin, bool eligible) {
    return controller.Observe(settled+now,margin,eligible);
  };
  warm();
  assert(!observe(200000000, 2500000, true));
  assert(!observe(220000000, 2499999, true));
  assert(observe(240000000, 2000000, true));
  assert(controller.Enabled());
  assert(!observe(260000000, 30000000, true));
  assert(controller.Enabled());
  controller.Reset();
  assert(!controller.Enabled());
  warm();
  assert(!observe(200000000, -1000000, true));
  assert(!observe(500000001, 1000000, true));
  assert(!controller.Enabled());
  // GUI/seek/stall observations never complete an activation burst.
  assert(!observe(510000000, 1000000, false));
  for (unsigned i=1; i<=8; ++i) observe(520000000+i*20000000ULL, 1000000, true);
  assert(!controller.Enabled());
  assert(!observe(700000000, 1000000, true));
  assert(observe(720000000, 1000000, true));
  controller.Reset();
  warm();
  assert(!observe(200000000, 1000000, true));
  assert(!observe(199999999, 1000000, true));
  assert(!controller.Enabled());
  assert(!DVBRIDGE::FastRenderingEnabled(0, true));
  assert(DVBRIDGE::FastRenderingEnabled(1, false));
  assert(!DVBRIDGE::FastRenderingEnabled(2, false));
  assert(DVBRIDGE::FastRenderingEnabled(2, true));
  assert(!DVBRIDGE::FastRenderingEnabled(99, true));
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
