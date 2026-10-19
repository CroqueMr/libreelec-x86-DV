"""GUI redraw must not starve pending source-DV Enhanced content analysis."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

class EnhancedGUIEpoch(unittest.TestCase):
    def test_ai_rgb_gui_invalidates_prepack_before_native_composition(self):
        code=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        start=code.index('  if (!rendered)\n    rendered = dvbridge_render_hdr10_ai_rgb')
        end=code.index('  m_aiRenderSubmitNs+=',start)
        program=r'''
#include <cassert>
constexpr int DVBRIDGE_MODE_ENHANCED_DV=4;
static bool prepacked, updated, fail;
static bool dvbridge_render_hdr10_ai_rgb(void*,const void*,const void*,const void*,const void*){return true;}
static bool dvbridge_render_dv_policy_update_overlay(void*,const void* overlay,bool visible){
  assert(!overlay && visible); updated=true;
  if(fail)return false;
  prepacked=false;return true;
}
void run(int mode,bool visible,bool direct){
  bool rendered=direct,m_direct=direct,m_overlayVisible=visible;
  void *m_renderer=nullptr;int prediction=0,geometry=0;
  struct {int frame=0;} imported;
  struct {int mode;} policy{mode};
'''+code[start:end]+r'''
  assert(updated==(mode==4 && visible && !direct));
  assert(rendered==!(updated && fail));
  if(updated && !fail)assert(!prepacked);
}
int main(){for(int mode:{1,4})for(bool visible:{false,true})for(bool direct:{false,true}){
  prepacked=true;updated=false;fail=false;run(mode,visible,direct);
  prepacked=true;updated=false;fail=true;run(mode,visible,direct);
}}
'''
        self.run_program(program.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>'))

    def test_ai_pending_gui_reuses_the_same_analysis_transaction(self):
        code=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        method=code.index('CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareHDR10AIFrame')
        start=code.index('  if (m_pending)\n  {',method)+len('  if (m_pending)\n  {\n')
        end=code.index('    Cancel();',start)
        body=code[start:end]
        program=r'''
#include <cassert>
constexpr int DVBRIDGE_MODE_ENHANCED_DV=4;
enum class FrameStatus{Ready,Pending,Failed};
static int updates;
static bool accept;
static bool dvbridge_render_dv_policy_update_overlay(void*,const int*,bool){++updates;return accept;}
FrameStatus run(int mode,bool visibility,bool epoch,bool same=true,bool succeeds=true,bool ready=true){
  updates=0;accept=succeeds;
  struct {int binding=1;} base;
  struct {struct {int revision=1;} id;} prediction;
  struct {int revision=1;} m_pendingIdentity;
  struct Preferences{int revision=1;bool SameValues(const Preferences&)const{return true;}} preferences,m_requested;
  struct {int mode;} policy{mode};int m_effectiveMode=mode;
  int m_pendingBinding=same?1:2;
  bool m_direct=false,sameGeometry=true,allowPacked=true,m_dvPolicyActive=true;
  bool m_pendingOverlayVisible=false,m_overlayVisible=visibility,m_nativeOverlayEnabled=visibility;
  int m_pendingOverlayRevision=1,m_nativeOverlayRevision=epoch?2:1,m_nativeOverlay=1;
  void* m_renderer=nullptr;
  auto PollReady=[ready](){return ready;};
'''+body+r'''
  return FrameStatus::Failed;
}
int main(){
  assert(run(4,true,true)==FrameStatus::Ready && updates==1);
  assert(run(4,false,true)==FrameStatus::Ready && updates==1);
  assert(run(4,true,true,true,true,false)==FrameStatus::Pending && updates==1);
  assert(run(4,true,true,false)==FrameStatus::Failed && updates==0);
  assert(run(4,true,true,true,false)==FrameStatus::Failed && updates==1);
  assert(run(0,true,true)==FrameStatus::Failed && updates==0);
  assert(run(0,false,false)==FrameStatus::Ready && updates==0);
}
'''
        self.run_program(program)

    def test_ai_diagnostics_do_not_claim_authored_l2(self):
        code=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        start=code.index('      if (snapshot.output_generation==DVBRIDGE_RECONSTRUCTED_ENHANCED)')
        end=code.index('      else if',start)
        program=r'''
#define CB1_HAS_HDR10_AI 1
#include <cassert>
#include <array>
#include <algorithm>
constexpr int DVBRIDGE_RECONSTRUCTED_ENHANCED=3,DVBRIDGE_CREATIVE_READY=3;
unsigned applied(unsigned family){
  struct {int output_generation=3;unsigned guidance_family;std::array<int,3> l1{1,2,3};} snapshot{3,family};
  struct {bool creativeKnown=false,emittedL1Known=false;unsigned creativeApplied=0;
          int creativeStatus=0;std::array<int,3> emittedL1{};} output;
'''+code[start:end]+r'''
  assert(output.creativeKnown && output.emittedL1Known && output.emittedL1==snapshot.l1);
  return output.creativeApplied;
}
int main(){assert(applied(0)==(1u<<1));assert(applied(2)==((1u<<1)|(1u<<2)));
assert(applied(8)==((1u<<1)|(1u<<8)));}
'''
        self.run_program(program)

    def run_program(self,program):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);source=path/'check.cpp';binary=path/'check'
            source.write_text(program)
            subprocess.run(['c++','-std=c++20',str(source),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_gui_changes_preserve_matching_analysis_not_native_or_ai(self):
        code=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        start=code.index('    const bool sameTransaction = base.binding == m_pendingBinding')
        end=code.index('    Cancel();',start)
        body=code[start:end]
        program=r'''
#include <cassert>
constexpr int DVBRIDGE_MODE_ENHANCED_DV=4;
enum class FrameStatus {Ready,Pending};
static bool accepted;
static int calls;
static bool dvbridge_render_dv_policy_update_overlay(void*,const int*,bool){++calls;return accepted;}
FrameStatus test(int mode,bool metadata,bool same,bool succeeds,bool visible,bool direct=true){
  calls=0;accepted=succeeds;
  struct {int binding=1;} base;
  int m_pendingBinding=same?1:2,revision=1;
  struct {int revision=1;} m_pendingIdentity;
  struct {int mode;} policy{mode};
  int m_effectiveMode=mode;
  bool allowPacked=true,m_direct=direct,m_dvPolicyActive=true;
  bool m_pendingOverlayVisible=false,m_overlayVisible=visible,m_nativeOverlayEnabled=visible;
  int m_pendingOverlayRevision=1,m_nativeOverlayRevision=2,m_nativeOverlay=1;
  struct {bool present;const void* Data()const{return present?this:nullptr;}} m_pendingMetadata{metadata};
  void* m_renderer=nullptr;
  auto PollReady=[](){return true;};
'''+body+r'''
  return FrameStatus::Pending;
}
int main(){
  assert(test(4,true,true,true,true)==FrameStatus::Ready && calls==1);
  assert(test(4,true,true,true,false)==FrameStatus::Ready && calls==1);
  assert(test(4,true,true,false,true)==FrameStatus::Pending && calls==1);
  assert(test(4,true,false,true,true)==FrameStatus::Pending && calls==0);
  assert(test(0,true,true,true,true)==FrameStatus::Pending && calls==0);
  assert(test(4,false,true,true,true)==FrameStatus::Pending && calls==0);
  assert(test(4,true,true,true,true,false)==FrameStatus::Pending && calls==0);
}
'''
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);source=path/'check.cpp';binary=path/'check'
            source.write_text(program)
            subprocess.run(['c++','-std=c++20',str(source),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
