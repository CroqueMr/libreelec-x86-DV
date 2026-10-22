"""Current Adaptive work stays owned even when future-frame preparation is off."""
import subprocess,tempfile,unittest
from pathlib import Path
from shipped_kodi import shipped_code

class AdaptiveSynchronousPending(unittest.TestCase):
    def test_pending_authored_adaptive_is_not_abandoned_when_async_is_off(self):
        code=shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        function=code.index('bool CWinSystemGbmGLESContext::RenderDVBridge(')
        assignment=code.index('  m_cb1FramePending =',code.index('  // A paused final surface',function))
        start=code.rfind('  glBindFramebuffer(GL_FRAMEBUFFER, 0);',function,assignment)
        end=code.index('  if (std::getenv("CB1_PRESENTATION_AUDIT"))',assignment)
        program=r'''
#include <cassert>
constexpr int GL_FRAMEBUFFER=0,DVBRIDGE_MODE_ENHANCED_DV=4,DVBRIDGE_MODE_HDR10PLUS=6;
void glBindFramebuffer(int,int){}
struct CDVBridgeGLES{enum class FrameStatus{Ready,Pending,Busy,Failed};};
using Status=CDVBridgeGLES::FrameStatus;
bool run(bool authored,int mode,Status status,bool allowAsync=false,bool setting=false){
 struct Metadata{bool value;const void* Data(){return value?this:nullptr;}}metadata{authored};
 struct{int mode;}policy{mode};
 struct Context{bool value;bool AsyncPreparation(int){return value;}}context{setting};
 auto* m_dvContext=&context;struct{struct{int stream=1;}binding;}layer;
 bool m_dvFrame=status==Status::Ready,m_cb1FramePending=false;
 @@BRANCH@@
 return m_cb1FramePending;
}
int main(){
 assert(run(true,4,Status::Pending));assert(run(true,4,Status::Busy));
 assert(!run(true,4,Status::Ready));assert(!run(true,4,Status::Failed));
 assert(!run(true,1,Status::Pending));assert(!run(false,4,Status::Pending));
 assert(run(true,1,Status::Ready,true,true));
 assert(run(false,4,Status::Pending,true,true));
 assert(!run(true,1,Status::Ready,true,false));
}
'''.replace('@@BRANCH@@',code[start:end])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'test.cpp';binary=root/'test'
            source.write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(source),'-o',str(binary)],text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(binary)],text=True,capture_output=True)
            self.assertEqual(ran.returncode,0,ran.stderr)
