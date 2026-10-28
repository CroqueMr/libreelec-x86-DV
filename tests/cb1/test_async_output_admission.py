"""Compatibility explanations must not serialize an already admitted CB1 output."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AsyncOutputAdmissionTests(unittest.TestCase):
    def test_admitted_policy_is_not_an_internal_render_failure(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare = body(source, 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        selection = prepare[prepare.index('  auto policy = selected ?'):prepare.index('  // Capture the proven observation key')]
        program = r'''
#include <cassert>
constexpr int DVBRIDGE_MODE_STANDARD=0,DVBRIDGE_MODE_HDR10_BASIC=2,
 DVBRIDGE_MODE_HDR10_EXPERT=3,DVBRIDGE_MODE_ENHANCED_DV=5,DVBRIDGE_ADAPTIVE_A=0;
namespace DVBRIDGE {enum class OutputMode {Standard,HDR10,MasterReference};}
struct TestPolicy {int mode=6,tv=1,adaptive=1;};
struct Preferences {DVBRIDGE::OutputMode output=DVBRIDGE::OutputMode::HDR10;
 bool allowMasterFallback=false,valid=true;TestPolicy requested;
 TestPolicy Policy()const{return requested;}bool ProfileValid()const{return valid;}};
bool internalFallback(const Preferences& preferences,const TestPolicy* selected){
 BODY
 return fallback;
}
int main(){
 Preferences p;TestPolicy basic;basic.mode=DVBRIDGE_MODE_HDR10_BASIC;
 assert(!internalFallback(p,&basic));
 p.valid=false;assert(!internalFallback(p,&basic));
 p.requested.mode=DVBRIDGE_MODE_HDR10_EXPERT;assert(internalFallback(p,nullptr));
 p.requested.mode=DVBRIDGE_MODE_ENHANCED_DV;assert(internalFallback(p,nullptr));
 p.valid=true;assert(!internalFallback(p,nullptr));
}
'''.replace('BODY', selection)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root/'check.cpp'), '-o', str(root/'check')],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root/'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_effective_route_keeps_fences_and_all_safety_guards(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        implementation = body(source, 'bool CWinSystemGbmGLESContext::CB1AsyncAvailable() const')
        program = r'''
#include <cassert>
#include <memory>
namespace DVBRIDGE {
enum class OutputRoute { Vanilla, NativeDV, HDR10 };
enum class OutputReason { None, NoHDR10PlusTransport, NoDVTransport, NoGPUProcessing };
}
struct DRM {virtual ~DRM()=default;};
struct CDRMAtomic:DRM {bool available=true;bool CanAsyncDVBridge(){return available;}};
struct Bridge {bool fallback=false;bool Fallback(){return fallback;}};
struct State {bool captured=true;bool Captured()const{return captured;}};
struct Context {
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<Bridge> m_dvBridge=std::make_shared<Bridge>();
 bool m_eglFence=true,m_dvFallbackActive=false,m_dvActivating=false;
 bool m_dvRecoveryPending=false,m_dvRejectedSurface=false,m_dvRollbackFailed=false;
 bool m_dvOutputRetiring=false,m_dvShutdownFence=false,m_dvStopPending=false;
 bool pending=false,m_hdrConversion=false;State m_dvState;
 struct {DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::NativeDV;
 DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::None;}m_dvSelection;
 bool HasPendingDVOutputSurface()const{return pending;}
 bool available()const BODY
};
int main(){
 using namespace DVBRIDGE;
 for(auto reason:{OutputReason::None,OutputReason::NoHDR10PlusTransport,OutputReason::NoDVTransport}){
  Context c;c.m_hdrConversion=true;c.m_dvState.captured=false;
  c.m_dvSelection={OutputRoute::HDR10,reason};assert(c.available());
 }
 for(int guard=0;guard<15;++guard){
  Context c;c.m_hdrConversion=true;c.m_dvSelection={OutputRoute::HDR10,OutputReason::NoHDR10PlusTransport};
  switch(guard){
   case 0:c.m_eglFence=false;break;
   case 1:c.m_DRM.reset();break;
   case 2:std::dynamic_pointer_cast<CDRMAtomic>(c.m_DRM)->available=false;break;
   case 3:c.m_dvBridge.reset();break;
   case 4:c.m_dvBridge->fallback=true;break;
   case 5:c.m_dvFallbackActive=true;break;
   case 6:c.m_dvActivating=true;break;
   case 7:c.m_dvRecoveryPending=true;break;
   case 8:c.m_dvRejectedSurface=true;break;
   case 9:c.m_dvRollbackFailed=true;break;
   case 10:c.m_dvOutputRetiring=true;break;
   case 11:c.m_dvShutdownFence=true;break;
   case 12:c.m_dvStopPending=true;break;
   case 13:c.pending=true;break;
   case 14:c.m_dvSelection.route=OutputRoute::Vanilla;break;
  }
  assert(!c.available());
 }
 Context c;c.m_dvState.captured=false;assert(!c.available());
 c.m_dvState.captured=true;assert(c.available());
 c.m_DRM=std::make_shared<DRM>();assert(!c.available());
}
'''.replace('BODY', implementation)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(root/'check.cpp'), '-o', str(root/'check')],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root/'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
