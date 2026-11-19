"""Execute the shipped AI transport admission, including its retirement boundary."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_native_video_source import TREE, body


class AITransportAdmissionTests(unittest.TestCase):
    def test_committed_transport_reuses_only_the_existing_ordered_retirement_slot(self):
        code=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text(),
            'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareHDR10AIFrame(')
        start=min(code.index('  if (m_dvPolicyActive)\n'),code.index('  const bool eligible ='))
        code=code[start:code.index('  dvbridge_gl_frame imported{};')]
        program=r'''
#include <cassert>
enum {DVBRIDGE_DV_IDLE,DVBRIDGE_DV_BUSY,DVBRIDGE_DV_FAILED,DVBRIDGE_MODE_STANDARD=3};
int advances,polls;bool retiredSlotBusy;
int dvbridge_render_dv_policy_advance(void*){++advances;return retiredSlotBusy?DVBRIDGE_DV_BUSY:DVBRIDGE_DV_IDLE;}
int dvbridge_render_dv_policy_poll(void*){++polls;return DVBRIDGE_DV_BUSY;}
struct Binding{int stream=1,revision=2;};
struct Preferences{int mode=3;auto HDR10Policy()const{return *this;}};
struct Context{bool ordered=false;int Poll(bool value){ordered=value;return DVBRIDGE_DV_IDLE;}void SourceReadComplete(){}};
struct Renderer{
 enum class FrameStatus{Ready,Busy,Failed};
 bool m_dvPolicyActive=true,m_fallback=false,m_hasCommitted=true,m_aiOutputAccepted=true,m_aiFrame=true;
 Binding m_committedBinding;int m_committedRevision=2,m_committedMode=3;void* m_renderer=nullptr;
 Context context;Context* m_context=&context;
 FrameStatus Admit(bool allowAsync=true,bool sameGeometry=true,int mode=3,int revision=2){
  bool asyncSetting=true,allowPacked=true;struct{Binding binding;}base;
  struct{Binding id;}prediction;prediction.id.revision=revision;
  Preferences policy{mode},preferences{mode};
  ADMISSION
  return FrameStatus::Ready;
 }
};
int main(){
 Renderer r;assert(r.Admit()==Renderer::FrameStatus::Ready);assert(advances==1 && !polls && r.context.ordered);
 r.m_dvPolicyActive=true;retiredSlotBusy=true;assert(r.Admit()==Renderer::FrameStatus::Busy);assert(advances==2 && !polls);
 retiredSlotBusy=false;
 for(int which=0;which<6;which++){
  Renderer v;if(which==4)v.m_aiOutputAccepted=false;if(which==5)v.m_hasCommitted=false;
  assert(v.Admit(which!=0,which!=1,which==2?4:3,which==3?3:2)==Renderer::FrameStatus::Busy);
 }
 assert(advances==2 && polls==6);
}
'''.replace('ADMISSION',code)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)
