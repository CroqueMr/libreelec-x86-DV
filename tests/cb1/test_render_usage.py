"""Exercise the shipped graphics-client sampler with driver fdinfo records."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RenderUsageTests(unittest.TestCase):
    def test_driver_engines_deduplication_and_sampling(self):
        program = r'''
#include "DVRenderUsage.h"
#include <cassert>
#include <cmath>
using Usage = DVBRIDGE::RenderUsage;
Usage::Clients record(const char* driver, const char* engine, uint64_t busy,
                      unsigned capacity=1, const char* id="8")
{
  std::ostringstream text;
  text << "drm-client-id: " << id << "\ndrm-pdev: 0000:05:00.0\n"
       << "drm-engine-" << engine << ": " << busy << " ns\n"
       << "drm-engine-capacity-" << engine << ": " << capacity << "\n"
       << "drm-engine-compute: 99999999999 ns\n"
       << "drm-driver: " << driver << "\n";
  std::istringstream input(text.str());
  Usage::Clients clients;
  Usage::Parse(input,clients);
  return clients;
}
int main()
{
  for (const char* driver : {"i915","xe","amdgpu"})
  {
    const char* engine = std::string(driver)=="amdgpu" ? "gfx" : "render";
    Usage usage;
    auto clients=record(driver,engine,1000000000);
    assert(clients.size()==1);
    assert(!usage.Update(clients,1000000000));
    assert(std::abs(*usage.Update(record(driver,engine,1250000000),2000000000)-25)<.0001);
    // A temporary decrease must not double-count the recovery.
    assert(*usage.Update(record(driver,engine,1100000000),3000000000)==0);
    assert(std::abs(*usage.Update(record(driver,engine,1300000000),4000000000)-5)<.0001);
    assert(!usage.Update(record(driver,engine,1400000000,1,"9"),5000000000));
    assert(!usage.Update({},6000000000));
    assert(!usage.Update(record(driver,engine,1500000000),7000000000));
  }
  assert(record("amdgpu","render",100).empty());
  assert(record("i915","gfx",100).empty());
  assert(record("nouveau","gfx",100).empty());
  assert(record("nvidia-drm","render",100).empty());
  assert(record("amdgpu","gfx",100,0).empty());
  Usage usage;
  auto clients=record("amdgpu","gfx",1000000000,2);
  std::istringstream duplicate("drm-driver: amdgpu\ndrm-pdev: 0000:05:00.0\ndrm-client-id: 8\ndrm-engine-gfx: 900000000 ns\n");
  Usage::Parse(duplicate,clients);
  assert(clients.size()==1 && clients.begin()->second.busy==1000000000);
  assert(!usage.Update(clients,1000000000));
  assert(*usage.Update(record("amdgpu","gfx",1500000000,2),2000000000)==25);
  assert(!usage.Update(record("amdgpu","gfx",1500000000,1),3000000000));
  assert(!usage.Update(record("amdgpu","gfx",1500000000),7000000001));
  std::istringstream defaultCapacity("drm-driver: amdgpu\ndrm-pdev: 0000:05:00.0\ndrm-client-id: 7\ndrm-engine-gfx: 10 ns\n");
  clients.clear(); Usage::Parse(defaultCapacity,clients);
  assert(clients.size()==1 && clients.begin()->second.capacity==1);
  for (const auto& bad : {std::string("drm-engine-gfx: 100 us\n"), std::string(2050,'x')+"\n"})
  {
    std::istringstream input("drm-driver: amdgpu\ndrm-pdev: 0000:05:00.0\ndrm-client-id: 8\n"+bad);
    clients.clear(); Usage::Parse(input,clients); assert(clients.empty());
  }
}
'''
        patch = (ROOT / 'projects/Generic/patches/kodi/kodi-9996-output-modes-and-info.patch').read_text()
        section = patch.split('+++ b/xbmc/utils/DVRenderUsage.h\n', 1)[1].split('\ndiff --git ', 1)[0]
        header = '\n'.join(line[1:] for line in section.splitlines() if line.startswith('+')) + '\n'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'DVRenderUsage.h').write_text(header)
            (root / 'check.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                    str(root / 'check.cpp'), '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
