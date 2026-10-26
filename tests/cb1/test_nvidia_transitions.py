"""Exercise native DV restoration commits, including refused head restart."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code


class NvidiaTransitions(unittest.TestCase):
    def test_head_restart_only_for_same_mode_active_nvidia_restore(self):
        path='xbmc/windowing/gbm/WinSystemGbm.cpp'
        override=os.environ.get('CB1_DRM_STATE_SOURCE')
        source=(Path(override)/path).read_text() if override else shipped_code(path)
        method=re.search(r'bool CWinSystemGbm::FlipDVBridgePage\(.*?^}',source,re.S|re.M).group()
        program=r'''
#include <cassert>
#include <memory>
#include <vector>
constexpr unsigned DRM_MODE_FLAG_INTERLACE=1,DRM_MODE_FLAG_DBLSCAN=2;
constexpr unsigned DRM_FORMAT_XRGB8888=1,DRM_FORMAT_ARGB8888=2;
struct gbm_bo {};
unsigned gbm_bo_get_width(gbm_bo*) {return 3840;}
unsigned gbm_bo_get_height(gbm_bo*) {return 2160;}
unsigned gbm_bo_get_format(gbm_bo*) {return DRM_FORMAT_XRGB8888;}
struct CResolutionUtils {static bool IsCB1RefreshRate(double) {return true;}};
struct Mode {unsigned hdisplay=3840,vdisplay=2160,flags=0,clock=1,htotal=1,vtotal=1;};
struct CDRMAtomic {
  bool active=true,committed=true,pending=false; Mode mode;
  int reject=-1; std::vector<bool> commits;
  bool HasPendingCB1Page() const {return pending;}
  bool IsSelectedModeCommitted() const {return committed;}
  bool IsActive() const {return active;}
  bool SetActive(bool value) {active=value;return true;}
  Mode* GetSelectedMode() {return &mode;}
  bool FlipPageTransactional(gbm_bo*,bool,bool=false) {
    commits.push_back(active); return static_cast<int>(commits.size())!=reject;
  }
};
struct Surface {
  gbm_bo bo; bool ended=false,completed=false;
  gbm_bo* LockTransactionalBuffer() {return &bo;}
  void CompleteTransactionalBuffer(bool accepted) {completed=accepted;}
  void EndTransactionalMode() {ended=true;}
};
struct GBM {Surface surface; GBM& GetDevice() {return *this;} Surface& GetSurface() {return surface;}};
struct CDVBridgeState {
  enum class Backend {NONE,KERNEL,NVIDIA}; Backend backend=Backend::NVIDIA;
  bool captured=true;
  bool Captured() const {return captured;}
  Backend CapturedBackend() const {return backend;}
  bool Stage(CDRMAtomic&,bool) {return true;}
  void Restored() {captured=false;}
};
struct CWinSystemGbm {
  std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
  std::shared_ptr<GBM> m_GBM=std::make_shared<GBM>();
  bool CompleteDVBridgePage() {return true;}
  bool SupportsDVOutputMode() const {return true;}
  unsigned requeues=0;
  bool RequeueOutputProperties() {++requeues;return true;}
  bool FlipDVBridgePage(CDVBridgeState&,bool,bool=false,bool=false);
};
METHOD
int main() {
  for(int kind=0;kind<5;++kind) {
    CWinSystemGbm window; CDVBridgeState state;
    if(kind==1) window.m_DRM->active=false;
    if(kind==2) window.m_DRM->committed=false;
    if(kind==3) state.backend=CDVBridgeState::Backend::KERNEL;
    if(kind==4) window.m_DRM->reject=2;
    const bool accepted=window.FlipDVBridgePage(state,true,false,true);
    assert(accepted==(kind!=4));
    const auto& commits=window.m_DRM->commits;
    if(kind==0 || kind==4) assert(commits==std::vector<bool>({false,true}));
    else assert(commits==std::vector<bool>({kind!=1}));
    assert(state.captured==(kind==4));
    assert(window.m_GBM->surface.ended==(kind!=4));
    assert(window.requeues==(kind==0 || kind==4 ? 2u : 1u));
    if(kind==4) {
      window.m_DRM->reject=-1;
      assert(window.FlipDVBridgePage(state,true) && !state.captured);
    }
  }
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as directory:
            code=Path(directory)/'check.cpp'; code.write_text(program)
            binary=Path(directory)/'check'
            result=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
