"""Mode changes must reconcile rejected work and re-admit the renderer output."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


def execute(program):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/'test.cpp').write_text(program)
        built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
        if built.returncode:raise AssertionError(built.stderr)
        ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
        if ran.returncode:raise AssertionError(ran.stderr)


class AIReentryTests(unittest.TestCase):
    def test_ai_waits_for_ordinary_restore_before_preparing_first_image(self):
        source=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::PrepareHDR10AIQueue(')
        selection=source[:source.index('  const auto binding =')]
        execute(r'''
#include <cassert>
#include <mutex>
namespace DVBRIDGE {
enum class HDR10SourceMode {Native,ReferenceDV};enum class OutputRoute {Vanilla,DV};
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;inline auto FrameOutputSettings(){return prefs;}
struct Caps{bool isHDR10=true;};
struct Selection{OutputRoute route;};
inline Selection SelectOutput(Preferences p,Caps){return {p.hdr10Source==HDR10SourceMode::Native?OutputRoute::Vanilla:OutputRoute::DV};}
}
struct Context{int stops=0;bool StopHDR10AI(){++stops;return true;}};
struct Window{
 std::mutex m_dvCapabilityMutex;bool m_aiActive=true;
 bool m_dvOrdinaryFrame=false,m_dvEndPending=false,m_dvStopPending=false;
 Context context;Context* m_dvContext=&context;
 auto GetDVOutputCapabilities(int*,DVBRIDGE::Preferences){return DVBRIDGE::Caps{};}
 int picture=0;bool Prepare()
  SELECTION
  return true;
 }
};
int main(){
 Window w;assert(w.Prepare());
 for(int which=0;which<3;which++){
  w.m_dvOrdinaryFrame=which==0;w.m_dvEndPending=which==1;w.m_dvStopPending=which==2;
  assert(!w.Prepare());assert(w.context.stops==0);
 }
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;
 assert(w.Prepare());assert(w.context.stops==1 && !w.m_aiActive);
}
'''.replace('SELECTION',selection))

    def test_rejected_preparation_is_reconciled_after_native_disables_lookahead(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                    'void CRenderManager::FrameMove()')
        at=source.rfind('    if (',0,source.index('      PrepareHDR10AILookahead(lock2);'))
        selection=source[at:source.index('#endif',at)]
        execute(r'''
#include <cassert>
constexpr double DVD_NOPTS_VALUE=-1e20;
struct Renderer {bool active=false;bool HDR10AILookahead(){return active;}};
struct Manager {
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 bool m_aiQueuePreparationStale=false;double m_aiStartPts=100;int calls=0;
 void PrepareHDR10AILookahead(int){++calls;m_aiQueuePreparationStale=false;}
 void Tick(){int lock2=0; SELECTION }
};
int main(){
 Manager normal;normal.Tick();assert(normal.calls==0);
 Manager startup;startup.m_aiStartPts=DVD_NOPTS_VALUE;startup.Tick();assert(startup.calls==1);
 Manager active;active.renderer.active=true;active.Tick();assert(active.calls==1);
 Manager rejected;rejected.m_aiQueuePreparationStale=true;rejected.Tick();
 assert(rejected.calls==1 && !rejected.m_aiQueuePreparationStale);
 rejected.Tick();assert(rejected.calls==1);
}
'''.replace('SELECTION',selection))

    def test_mode_reentry_reuses_existing_output_admission_without_reconfiguring_pool(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text(),
                    'HDR10AIQueuePreparation CRendererVAAPIGLES::CaptureHDR10AIQueue(')
        selection=source[source.index('  const auto preferences ='):]
        execute(r'''
#include <cassert>
#include <functional>
#include <memory>
#include <vector>
namespace DVBRIDGE {
enum class HDR10SourceMode {Native,ReferenceDV};
struct Preferences {int revision=1;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;
 bool SameValues(const Preferences& other)const{return hdr10Source==other.hdr10Source;}};
inline Preferences prefs;inline auto FrameOutputSettings(){return prefs;}
}
struct Binding{int stream=1,picture=1,revision=1;bool operator==(const Binding&)const=default;};
struct Picture{Binding doviSourceBinding;};
struct Preparation {
 struct Outcome{bool ready,lookahead;};bool ready;
 std::function<Outcome()> execute;std::function<bool(const Outcome&)> publish;
};
using HDR10AIQueuePreparation=Preparation;
struct Window {
 bool ready=true;
 bool PrepareHDR10AIQueue(const Picture&,const std::vector<int>&,bool,bool,unsigned long){return ready;}
 bool HDR10AILookaheadActive(){return DVBRIDGE::prefs.hdr10Source!=DVBRIDGE::HDR10SourceMode::Native;}
};
struct Renderer {
 bool m_aiLookahead=false,m_aiOutputPending=false,m_dvRequested=false;int admissions=0;
 struct Slot {std::shared_ptr<Picture> doviSourcePicture=std::make_shared<Picture>();} m_buffers[1];
 Window output;
 bool ConfigureVideoOutput(const Picture&){++admissions;m_dvRequested=output.HDR10AILookaheadActive();return true;}
 Preparation Capture(){
  auto* window=&output;auto head=m_buffers[0].doviSourcePicture;
  std::vector<int> layers;bool end=false,paused=false;unsigned long presentationDeadline=0;
  int index=0;auto binding=head->doviSourceBinding;
  SELECTION
};
bool run(Renderer& r){auto p=r.Capture();if(!p.execute)return p.ready;auto o=p.execute();return p.publish(o)&&o.ready;}
int main(){
 Renderer r;r.output.ready=false;assert(!run(r));assert(r.admissions==0);
 r.output.ready=true;assert(run(r));assert(r.admissions==1 && r.m_dvRequested && !r.m_aiOutputPending);
 assert(run(r));assert(r.admissions==1);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;++DVBRIDGE::prefs.revision;
 r.output.ready=false;assert(!run(r));assert(r.admissions==1 && r.m_dvRequested);
 r.output.ready=true;assert(run(r));assert(r.admissions==2 && !r.m_dvRequested && !r.m_aiOutputPending);
 assert(run(r));assert(r.admissions==2);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::ReferenceDV;++DVBRIDGE::prefs.revision;
 auto stale=r.Capture();++DVBRIDGE::prefs.revision;assert(!stale.publish(stale.execute()));
 assert(r.admissions==2 && !r.m_dvRequested);
 assert(run(r));assert(r.admissions==3 && r.m_dvRequested);
}
'''.replace('SELECTION',selection))
