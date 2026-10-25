"""Run native frame timing and bounded Master safety against literal boundaries."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

ROOT = Path(__file__).resolve().parents[2]


class FastRenderingTests(unittest.TestCase):
    def test_master_budget_uses_source_fps_even_when_a_picture_was_missed(self):
        root=os.environ.get('CB1_DRM_STATE_SOURCE')
        name='xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp'
        cpp=(Path(root)/name).read_text() if root else shipped_code(name)
        assignment=re.search(r'm_masterFramePeriodNs=.*?;',cpp,re.S).group()
        patch=(ROOT/'projects/Generic/patches/kodi/kodi-9999-zz-beta3.patch').read_text()
        section=patch.split('+++ b/xbmc/utils/DVBridgeFastRendering.h\n',1)[1].split('\ndiff --git ',1)[0]
        header='\n'.join(line[1:] for line in section.splitlines() if line.startswith('+'))+'\n'
        program=r'''
#include <cassert>
#include "DVBridgeFastRendering.h"
struct Cache {double fps=59.94;double GetVideoFps(){return fps;}};
struct CServiceBroker {static Cache& GetDataCacheCore(){static Cache cache;return cache;}};
int main(){bool m_fastRenderEligible=true;uint64_t m_masterFramePeriodNs=0;
 constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=4;
 struct {bool allowMasterFallback=true;}preferences;
 struct {struct {int mode=4;}policy;}m_dvSelection;
 (void)preferences;(void)m_dvSelection;(void)DVBRIDGE_MODE_MASTER_REFERENCE;
 double m_fastSourcePts=100000;struct {double pts=133367;}layer;
 (void)m_fastSourcePts;(void)layer;
 ASSIGNMENT
 assert(m_masterFramePeriodNs==16683350);
 m_fastRenderEligible=false;
 ASSIGNMENT
 assert(m_masterFramePeriodNs==0);
 m_fastRenderEligible=true;preferences.allowMasterFallback=false;
 ASSIGNMENT
 assert(m_masterFramePeriodNs==0);
 preferences.allowMasterFallback=true;m_dvSelection.policy.mode=0;
 ASSIGNMENT
 assert(m_masterFramePeriodNs==0);
}
'''.replace('ASSIGNMENT',assignment)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'DVBridgeFastRendering.h').write_text(header)
            code=Path(directory)/'check.cpp';code.write_text(program);binary=Path(directory)/'check'
            built=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',directory,str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_next_submission_keeps_completed_headroom_until_consumed(self):
        def source(name):
            root=os.environ.get('CB1_DRM_STATE_SOURCE')
            return (Path(root)/name).read_text() if root else shipped_code(name)
        owner='xbmc/windowing/gbm/drm/DRMAtomic'
        cpp=source(owner+'.cpp')
        reset=re.search(r'void CDRMAtomic::ResetCB1Timing\(.*?^}',cpp,re.S|re.M).group()
        take=re.search(r'std::optional<int64_t> CDRMAtomic::TakeCB1Headroom\(.*?^}',cpp,re.S|re.M).group()
        declaration=re.search(r'void ResetCB1Timing\([^;]+;',source(owner+'.h')).group()
        admission=cpp.split('const bool asynchronous = async && !restore && CanAsyncDVBridge() && m_inFenceFd >= 0;',1)[1].split('  const int flags',1)[0]
        program=r'''
#include <cassert>
#include <cstdint>
#include <optional>
#include <fcntl.h>
#include <unistd.h>
struct CDRMAtomic {
  int m_cb1TimingInput=-1,m_inFenceFd=-1;
  uint64_t m_cb1SubmittedNs=7,m_cb1TimingPeriodNs=16683333;
  std::optional<int64_t> m_cb1Headroom=-7000000;
  DECLARATION
  std::optional<int64_t> TakeCB1Headroom();
  void Submit(){const bool asynchronous=true;ADMISSION}
};
RESET
TAKE
int main(){CDRMAtomic d;int pipes[2];assert(pipe(pipes)==0);d.m_inFenceFd=pipes[0];
 d.Submit();assert(d.m_cb1TimingInput>=0 && d.m_cb1TimingInput!=pipes[0]);
 assert(d.TakeCB1Headroom()==-7000000);assert(!d.TakeCB1Headroom());
 d.m_cb1Headroom=4000000;int owned=d.m_cb1TimingInput;d.ResetCB1Timing();
 assert(!d.TakeCB1Headroom() && d.m_cb1TimingInput==-1 && d.m_cb1SubmittedNs==0);
 assert(fcntl(owned,F_GETFD)==-1);assert(fcntl(pipes[0],F_GETFD)>=0);
 close(pipes[0]);close(pipes[1]);}
'''.replace('DECLARATION',declaration).replace('ADMISSION',admission).replace('RESET',reset).replace('TAKE',take)
        with tempfile.TemporaryDirectory() as directory:
            code=Path(directory)/'check.cpp';code.write_text(program)
            binary=Path(directory)/'check'
            built=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

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
