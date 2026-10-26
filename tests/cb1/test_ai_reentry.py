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
    def test_output_reset_cancels_pending_transaction_but_retains_retirement_guard(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        reset=body(source,'void CDVBridgeGLES::Reset()')
        cancel=body(source,'void CDVBridgeGLES::Cancel()')
        execute(r'''
#include <cassert>
#include <optional>
#include <vector>
#define CB1_HAS_HDR10_AI
void cb1_hdr10plus_analysis_reset(int){}
void dvbridge_render_dv_policy_cancel(int){}
void dvbridge_render_policy_cancel(int){}
void dvbridge_renderer_reset(int){}
namespace DVBRIDGE {struct StreamTelemetry{static void ClearOutput(){}};}
struct Context{void ClearNextHDR10AI(){}};
struct Renderer{
 Context context;Context*m_context=&context;
 int m_hdr10plusAnalysis=0,m_renderer=0,m_pendingInfo=1,m_pendingHDR10Fallback=1;
 std::optional<int>m_hdr10plusMetadata=1;std::vector<int>m_rawELCache{1};
 bool m_firstFrame=false,m_prepared=true,m_packed=true,m_direct=true;
 bool m_pending=true,m_asyncEligible=true,m_dvPolicyActive=true;
 bool m_aiFrame=true,m_aiOutputAccepted=true;
 struct Submission{int sequence;}m_submission{12};
 void ClearFELPrefetch(){}void Summary(const char*){}
 void Reset() RESET
 void Cancel() CANCEL
};
int main(){
 for(bool active:{false,true}){
  Renderer r;r.m_dvPolicyActive=active;r.Reset();
  assert(!r.m_pending && !r.m_prepared && !r.m_packed);
  assert(!r.m_asyncEligible && !r.m_submission.sequence);
  assert(r.m_dvPolicyActive==active);
  assert(!r.m_aiFrame && !r.m_aiOutputAccepted && r.m_rawELCache.empty());
 }
}
'''.replace('RESET',reset).replace('CANCEL',cancel))

    def test_hdr10_analysis_uses_repaired_presentation_pts_not_duplicate_decode_pts(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text(),
                    'bool CRendererVAAPIGLES::BuildDVBridgeLayer(')
        selection=source[source.index('  auto& buffer ='):source.index('  const auto texture =')]
        execute(r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <memory>
#define CB1_HAS_HDR10_AI
constexpr double DVD_TIME_BASE=1000000,DVD_NOPTS_VALUE=1e20;
constexpr int64_t AV_NOPTS_VALUE=INT64_MIN;
enum{VA_FOURCC_NV12,VA_FOURCC_P010,VA_FOURCC_P012,VA_FOURCC_P016};
enum{DVBRIDGE_NV12,DVBRIDGE_P010,DVBRIDGE_P012,DVBRIDGE_P016};
enum class StreamHdrType{HDR_TYPE_HDR10,HDR_TYPE_DOLBYVISION};
struct Binding{bool Valid()const{return true;}};
struct Picture{StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;
 Binding doviSourceBinding;struct{int profile=0;}doviSourceInfo;
 int64_t doviSourcePts=1000000;double pts=1000000;};
struct Metadata{const void* Data(){return this;}::Binding Binding(){return {};}};
struct Layer{int width,height,layout;double pts;::Binding binding;};
struct Renderer{
 struct Slot{std::shared_ptr<Picture>doviSourcePicture=std::make_shared<Picture>();
  Metadata doviMetadata;double doviPts=1.25;}m_buffers[1];
 int m_vaapiFourcc=VA_FOURCC_P010,m_sourceWidth=3840,m_sourceHeight=2160;
 bool Build(Layer&layer){int idx=0;SELECTION return true;}
};
int main(){
 Renderer r;Layer first{},replayed{};assert(r.Build(first));
 r.m_buffers[0].doviSourcePicture->pts=1250000;
 assert(r.Build(replayed));assert(first.pts==1.0 && replayed.pts==1.25);
 assert(r.m_buffers[0].doviSourcePicture->doviSourcePts==1000000);
 r.m_buffers[0].doviSourcePicture->pts=DVD_NOPTS_VALUE;assert(!r.Build(replayed));
 r.m_buffers[0].doviSourcePicture->hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;
 r.m_buffers[0].doviSourcePicture->doviSourceInfo.profile=7;
 assert(r.Build(replayed) && replayed.pts==1.25);
}
'''.replace('SELECTION',selection))

    def test_ai_capture_horizon_uses_the_same_repaired_presentation_timeline(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text(),
                    'HDR10AIQueuePreparation CRendererVAAPIGLES::CaptureHDR10AIQueue(')
        start=source.index('  const auto horizon =')
        selection=source[start:source.index('  for (const auto idx',start)]
        execute(r'''
#include <cassert>
constexpr double DVD_TIME_BASE=1000000;
int main(){struct{double pts=9000000,doviSourcePts=1000000;}picture;auto*head=&picture;
 SELECTION assert(horizon==10.0);
}
'''.replace('SELECTION',selection))

    def test_native_output_rejection_is_pending_not_default_ready(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text(),
                    'HDR10AIQueuePreparation CRendererVAAPIGLES::CaptureHDR10AIQueue(')
        start=source.index('  if (preferences.hdr10Source == DVBRIDGE::HDR10SourceMode::Native)')
        native=source[start:source.index('  return {false,',start)]
        preparation=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/BaseRenderer.h').read_text(),
                         'struct HDR10AIQueuePreparation')
        execute(r'''
#include <cassert>
#include <functional>
struct HDR10AIQueuePreparation PREPARATION;
namespace DVBRIDGE {enum class HDR10SourceMode{Native,ReferenceDV};}
struct Window{
 bool stopped=true;
 template<class... T>bool PrepareHDR10AIQueue(T...){return stopped;}
 bool HDR10AILookaheadActive(){return false;}
};
struct Renderer{
 bool m_aiLookahead=true,m_aiOutputPending=true,admitted=false;
 bool ConfigureVideoOutput(int){return admitted;}
 HDR10AIQueuePreparation Capture(Window* window){
  struct{DVBRIDGE::HDR10SourceMode hdr10Source=DVBRIDGE::HDR10SourceMode::Native;}preferences;
  int picture=0,*head=&picture,layers=0,end=0,paused=0,presentationDeadline=0;
  NATIVE
  return {};
 }
};
int main(){
 Renderer r;Window w;assert(!r.Capture(&w).ready && r.m_aiOutputPending);
 r.admitted=true;assert(r.Capture(&w).ready && !r.m_aiOutputPending);
 r.m_aiOutputPending=true;w.stopped=false;
 assert(!r.Capture(&w).ready && r.m_aiOutputPending);
}
'''.replace('PREPARATION',preparation).replace('NATIVE',native))

    def test_successful_output_retry_reenables_rendering_after_temporary_rejection(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp').read_text(),
                    'bool CLinuxRendererGLES::ConfigureVideoOutput(')
        execute(r'''
#include <cassert>
#define CB1_HAS_HDR10_AI
#define HAVE_DVBRIDGE
constexpr int LOGWARNING=1,LOGERROR=2,LOGDEBUG=3;
struct VideoPicture{bool dv=false;int color_transfer=0;};
namespace DVBRIDGE {enum class OutputRoute{DV,HDR10};}
struct WindowBase{virtual ~WindowBase()=default;
 virtual bool SetVideoOutput(const VideoPicture*)=0;
 virtual void SetColorimetry(const VideoPicture*)=0;
 virtual bool SetHDR(const VideoPicture*)=0;
 virtual bool SetGuiCompositing(int)=0;};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext:WindowBase{
 bool output=true,restore=false,bridge=true,conversion=true;
 DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::DV;
 static bool DVBridgeRequested(const VideoPicture* p){return p->dv;}
 bool BeginDVBridge(){return bridge;}
 bool SetVideoOutput(const VideoPicture*)override{return output;}
 bool HasPendingDVBridgeRestore(){return restore;}
 void SetColorimetry(const VideoPicture*)override{}
 struct Selection{DVBRIDGE::OutputRoute route;};
 Selection SelectedDVOutput(const VideoPicture*){return {route};}
 bool ConfigureHDR10Conversion(const VideoPicture&){return conversion;}
 bool SetHDR(const VideoPicture*)override{return true;}
 bool SetGuiCompositing(int)override{return true;}
};}
inline KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker{static WindowBase* GetWinSystem(){return &window;}};
struct CLog{template<class... T>static void Log(T...){};};
struct Renderer{
 bool m_aiOutputPending=false,m_dvRequested=false,m_passthroughHDR=false;
 bool m_hdrFboActive=false,m_bConfigured=true;
 bool ConfigureVideoOutput(const VideoPicture& picture) BODY
};
int main(){
 VideoPicture dv{true},native{false};
 Renderer retry;window.output=false;
 assert(!retry.ConfigureVideoOutput(dv) && !retry.m_bConfigured);
 window.output=true;assert(retry.ConfigureVideoOutput(dv) && retry.m_bConfigured);
 retry.m_bConfigured=false;assert(retry.ConfigureVideoOutput(native) && retry.m_bConfigured);
 Renderer ai;ai.m_aiOutputPending=true;window.bridge=false;
 assert(!ai.ConfigureVideoOutput(dv) && !ai.m_bConfigured);
 window.bridge=true;assert(ai.ConfigureVideoOutput(dv) && ai.m_bConfigured);
 window.route=DVBRIDGE::OutputRoute::HDR10;window.conversion=false;
 assert(!retry.ConfigureVideoOutput(dv) && !retry.m_bConfigured);
 window.conversion=true;assert(retry.ConfigureVideoOutput(dv) && retry.m_bConfigured);
}
'''.replace('BODY',source))

    def test_first_presentation_wait_yields_when_its_committed_policy_is_obsolete(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                    'bool CRenderManager::PrepareHDR10AILookahead(')
        selection=source[source.index('  // Let the video worker'):source.index('  // Reuse only existing slots')]
        execute(r'''
#include <cassert>
constexpr double DVD_NOPTS_VALUE=-1e20;
struct Renderer{bool current=true;bool HDR10AILookahead(){return true;}bool HDR10AIFrameCommitted(){return current;}};
struct Manager{
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 bool m_aiGuiReady=true,m_showVideo=false,m_aiQueueReady=true,advanced=false;
 double m_aiStartPts=1;
 bool Prepare(){ SELECTION advanced=true;return false; }
};
int main(){
 Manager current;assert(current.Prepare());assert(!current.advanced && current.m_aiGuiReady);
 Manager obsolete;obsolete.renderer.current=false;assert(!obsolete.Prepare());
 assert(obsolete.advanced && !obsolete.m_aiGuiReady && obsolete.m_aiStartPts==DVD_NOPTS_VALUE);
}
'''.replace('SELECTION',selection))

    def test_committed_ai_readiness_belongs_to_current_activation_and_preferences(self):
        header=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.h').read_text()
        selection=body(header,
                       'bool HDR10AIFrameCommitted() const')
        pending=body(header,'bool HDR10AISelectionPending() const')
        execute(r'''
#include <cassert>
#include <optional>
#include <mutex>
namespace DVBRIDGE{
enum class HDR10SourceMode{Native,ReferenceDV};
struct Preferences{int revision=1;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;inline auto FrameOutputSettings(){return prefs;}
}
struct Source{bool Current(int binding,DVBRIDGE::Preferences p){return binding==7 && p.revision==1;}};
struct Context{Source source;Source& HDR10AI(){return source;}};
struct Bridge{std::optional<int> committed=1;const auto& CommittedHDR10AI(){return committed;}};
struct Window{Context context;Context* m_dvContext=&context;Bridge bridge;Bridge* m_dvBridge=&bridge;
 int m_aiActivation=7,m_aiPolicy=17,m_aiSelectionPolicy=1;mutable std::mutex m_dvCapabilityMutex;
 bool Committed()const BODY
 bool SelectionPending()const PENDING
};
int main(){
 Window w;assert(w.Committed());w.m_aiActivation=8;assert(!w.Committed());
 w.m_aiActivation=7;DVBRIDGE::prefs.revision=2;assert(!w.Committed());DVBRIDGE::prefs.revision=1;
 w.bridge.committed.reset();assert(!w.Committed());
 assert(!w.SelectionPending());DVBRIDGE::prefs.revision=2;assert(w.SelectionPending());
 w.m_aiSelectionPolicy=2;assert(!w.SelectionPending());
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;
 DVBRIDGE::prefs.revision=3;assert(w.SelectionPending());
 w.m_aiSelectionPolicy=3;assert(!w.SelectionPending());
}
'''.replace('BODY',selection).replace('PENDING',pending))

    def test_native_to_ai_resets_only_first_presentation_readiness(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                    'bool CRenderManager::ExecuteHDR10AIQueuePreparation(')
        at=source.index('    // After rejection, fresh pending analysis')
        selection=source[at:source.index('\n  }\n  else',at)]
        execute(r'''
#include <cassert>
constexpr double DVD_NOPTS_VALUE=-1e20;
struct Manager {
 bool m_aiQueuePreparationStale=false,m_aiGuiReady=true,m_aiQueueReady=true;
 double m_aiStartPts=1;
 void Publish(bool lookahead,bool next,bool ready){struct {bool lookahead,ready;} outcome{next,ready};
 SELECTION }
};
int main(){
 Manager entering;entering.Publish(false,true,false);
 assert(entering.m_aiStartPts==DVD_NOPTS_VALUE && !entering.m_aiGuiReady && !entering.m_aiQueueReady);
 Manager active;active.Publish(true,true,true);assert(active.m_aiStartPts==1 && active.m_aiGuiReady);
 Manager native;native.Publish(false,false,true);assert(native.m_aiStartPts==1 && native.m_aiGuiReady);
}
'''.replace('SELECTION',selection))

    def test_ai_bootstrap_never_redraws_an_unselected_retained_picture(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                    'void CRenderManager::Render(')
        at=source.index('    // Pending readiness is normal;')
        selection=source[at:source.index('\n  }\n#endif',at)]
        execute(r'''
#include <cassert>
constexpr double DVD_NOPTS_VALUE=-1e20;
enum Step{PRESENT_FRAME,PRESENT_READY,PRESENT_IDLE};
struct Renderer{bool active=true;bool HDR10AILookahead(){return active;}};
struct Manager{
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 bool m_aiQueuePreparationStale=false,m_aiGuiReady=false,rendered=false;
 double m_aiStartPts=DVD_NOPTS_VALUE;Step m_presentstep=PRESENT_FRAME;
 void Render(){ SELECTION rendered=true; }
};
int main(){
 Manager unprepared;unprepared.Render();assert(!unprepared.rendered);
 Manager unselected;unselected.m_aiStartPts=1;unselected.m_presentstep=PRESENT_READY;
 unselected.Render();assert(!unselected.rendered);
 Manager selected;selected.m_aiStartPts=1;selected.Render();assert(selected.rendered);
 Manager active;active.m_aiGuiReady=true;active.Render();assert(active.rendered);
 Manager ordinary;ordinary.renderer.active=false;ordinary.Render();assert(ordinary.rendered);
}
'''.replace('SELECTION',selection))

    def test_reprimed_queue_selects_new_frame_instead_of_redrawing_retained_native(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                    'bool CRenderManager::ExecuteHDR10AIQueuePreparation(')
        selection=source[source.rindex('  if (m_aiQueueReady && m_aiStartPts == DVD_NOPTS_VALUE)'):]
        execute(r'''
#include <cassert>
constexpr double DVD_NOPTS_VALUE=-1e20;
enum Step {PRESENT_IDLE,PRESENT_READY,PRESENT_FRAME,PRESENT_FLIP};
struct Renderer {bool active=true;bool HDR10AILookahead(){return active;}};
struct Manager {
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 bool m_aiQueueReady=true;double m_aiStartPts=DVD_NOPTS_VALUE;
 Step m_presentstep=PRESENT_FRAME;
 bool Publish(){double startPts=6000000; SELECTION
};
int main(){
 Manager startup;assert(startup.Publish());assert(startup.m_aiStartPts==6000000);
 assert(startup.m_presentstep==PRESENT_READY);
 Manager pending;pending.m_aiQueueReady=false;assert(!pending.Publish());
 assert(pending.m_aiStartPts==DVD_NOPTS_VALUE && pending.m_presentstep==PRESENT_FRAME);
 Manager ordinary;ordinary.renderer.active=false;assert(ordinary.Publish());
 assert(ordinary.m_presentstep==PRESENT_FRAME);
 Manager running;running.m_aiStartPts=1;assert(running.Publish());
 assert(running.m_aiStartPts==1 && running.m_presentstep==PRESENT_FRAME);
 Manager selected;selected.m_presentstep=PRESENT_FLIP;assert(selected.Publish());
 assert(selected.m_presentstep==PRESENT_FLIP);
}
'''.replace('SELECTION',selection))

    def test_ai_waits_for_ordinary_restore_before_preparing_first_image(self):
        source=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::PrepareHDR10AIQueue(')
        selection=source[:source.index('  const auto binding =')]
        execute(r'''
#include <cassert>
#include <mutex>
namespace DVBRIDGE {
enum class HDR10SourceMode {Native,ReferenceDV};enum class OutputRoute {Vanilla,DV};
struct Preferences {int revision=1;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;inline auto FrameOutputSettings(){return prefs;}
struct Caps{bool isHDR10=true;};
struct Selection{OutputRoute route;};
inline Selection SelectOutput(Preferences p,Caps){return {p.hdr10Source==HDR10SourceMode::Native?OutputRoute::Vanilla:OutputRoute::DV};}
}
struct Context{int stops=0;bool ready=true;bool StopHDR10AI(){++stops;return ready;}};
struct Window{
 std::mutex m_dvCapabilityMutex;bool m_aiActive=true;int m_aiPolicy=17,m_aiSelectionPolicy=0;
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
 w.context.ready=false;assert(!w.Prepare());
 assert(w.m_aiPolicy==17 && w.m_aiSelectionPolicy==0);
 w.context.ready=true;assert(w.Prepare());
 assert(w.context.stops==2 && !w.m_aiActive && w.m_aiPolicy==17 && w.m_aiSelectionPolicy==1);
}
'''.replace('SELECTION',selection))

    def test_rejected_preparation_is_reconciled_after_native_disables_lookahead(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                    'void CRenderManager::FrameMove()')
        at=source.rfind('    if (',0,source.index('      PrepareHDR10AILookahead(lock2);'))
        if '    bool aiReselection =' in source:
            at=source.index('    bool aiReselection =')
        selection=source[at:source.index('#endif',at)]
        execute(r'''
#include <cassert>
constexpr double DVD_NOPTS_VALUE=-1e20;
namespace DVBRIDGE {
enum class HDR10SourceMode {Native,ReferenceDV};
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::Native;};
inline Preferences prefs;inline auto FrameOutputSettings(){return prefs;}
}
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext {
 bool pending=false;
 bool HDR10AISelectionPending(){return pending;}
};
}
inline KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker{static auto* GetWinSystem(){return &window;}};
struct Renderer {bool active=false,eligible=true;
 bool HDR10AILookahead(){return active;}bool HDR10AIQueueEligible(){return eligible;}};
struct Manager {
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 bool m_aiQueuePreparationStale=false,m_aiQueueReady=true;double m_aiStartPts=100;int calls=0;
 void PrepareHDR10AILookahead(int){++calls;m_aiQueuePreparationStale=false;}
 void Tick(){int lock2=0; SELECTION }
};
int main(){
 Manager normal;normal.Tick();assert(normal.calls==0);
 Manager outputPending;outputPending.m_aiQueueReady=false;outputPending.Tick();assert(outputPending.calls==1);
 Manager startup;startup.m_aiStartPts=DVD_NOPTS_VALUE;startup.Tick();assert(startup.calls==1);
 Manager active;active.renderer.active=true;active.Tick();assert(active.calls==1);
 Manager rejected;rejected.m_aiQueuePreparationStale=true;rejected.Tick();
 assert(rejected.calls==1 && !rejected.m_aiQueuePreparationStale);
 rejected.Tick();assert(rejected.calls==1);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::ReferenceDV;
 window.pending=true;
 Manager requested;requested.Tick();assert(requested.calls==1);
 Manager ineligible;ineligible.renderer.eligible=false;ineligible.Tick();assert(ineligible.calls==0);
 window.pending=false;Manager fallback;fallback.Tick();assert(fallback.calls==0);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;
 window.pending=true;Manager stopping;stopping.Tick();assert(stopping.calls==1);
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
 struct Outcome{bool ready,lookahead;};bool ready{true};
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
