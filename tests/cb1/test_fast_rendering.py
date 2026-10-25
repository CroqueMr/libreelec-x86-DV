"""Run native frame timing and bounded Master safety against literal boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FastRenderingTests(unittest.TestCase):
    def test_headroom_continuity_and_master_safety(self):
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
  DVBRIDGE::MasterSafety safety;
  safety.Begin(1,1,1,0,true);
  for(int i=1;i<=120;i++){
    safety.Begin(1,1,1,i*16666.0,true);
    assert(!safety.Observe(3000000,true));
  }
  assert(!safety.Active());
  // GUI work and unavailable measurements cannot arm the safety.
  for(int i=0;i<120;i++){assert(!safety.Observe(-10000000,false));assert(!safety.Observe({},true));}
  for(int i=0;i<59;i++)assert(!safety.Observe(1000000,true));
  assert(safety.Observe(1000000,true) && safety.Active());
  assert(!safety.Observe(-10000000,true)); // Only one transition notification.
  safety.Begin(1,1,1,121*16666.0,true);assert(safety.Active());
  safety.Begin(1,1,1,0,true);assert(!safety.Active()); // Backward seek.
  for(int i=0;i<119;i++)assert(!safety.Observe(-1,true));
  assert(safety.Observe(-1,true));
  safety.Begin(1,2,1,16666,true);assert(!safety.Active()); // Manual policy change.
  for(int i=0;i<120;i++){safety.Begin(1,2,1,i*16666.0,false);assert(!safety.Observe(-1,true));}
  assert(!safety.Active()); // Strict Master.
  safety.Begin(2,2,2,0,true);assert(!safety.Active());
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
