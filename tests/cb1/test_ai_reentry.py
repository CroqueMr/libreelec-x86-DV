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
    def test_retaining_display_flush_keeps_selected_ai_bootstrap(self):
        manager=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        flush=body(body(manager,'bool CRenderManager::Flush('),'if (m_pRenderer)')
        reset=body(manager,'void CRenderManager::ResetHDR10AIQueue()')
        selection=body(manager,'bool CRenderManager::PrepareHDR10AILookahead(').split('  uint64_t deadline =')[0]
        execute(r'''
#include <cassert>
#include <deque>
#include <mutex>
#define CB1_HAS_HDR10_AI 1
#define HAVE_DVBRIDGE 1
constexpr double DVD_NOPTS_VALUE=-1e20;
constexpr int PRESENT_IDLE=0,PRESENT_FLIP=1,PRESENT_FRAME=2;
using CCriticalSection=std::mutex;
struct Renderer{bool retained=true;bool Flush(bool){return retained;}
 bool HDR10AIQueueEligible(){return true;}bool HDR10AILookahead(){return true;}
 bool HDR10AIFramePending(){return true;}bool HDR10AIFrameCommitted(){return false;}};
struct Resource{void Flush(){}void Set(){}};
struct Slot{struct Data{void reset(){}}sourceSideData;};
struct CRenderManager{
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 Resource m_overlays,m_debugRenderer,m_flushEvent;
 struct{bool m_cb1Phase=true;double offset=12;unsigned resets=0;
  void Reset(){m_cb1Phase=false;offset=0;++resets;}}m_clockSync;
 struct{unsigned resets=0;void SetVsyncAdjust(int v){assert(v==0);++resets;}
  bool IsPaused(){return true;}}m_dvdClock;
 unsigned m_aiQueueGeneration=9;
 bool m_aiEnd=false,m_aiQueueReady=true,m_aiFullscreenRequested=true,m_aiGuiReady=false,m_aiFullscreenWanted=false;
 bool m_aiQueuePreparationStale=false,m_showVideo=false,m_aiStartupBuffered=false;
 double m_aiStartPts=40000000;
 Slot m_Queue[3];std::deque<int> m_queued,m_discard,m_free;
 int m_presentsource=1,m_presentsourcePast=0,m_presentstep=PRESENT_FRAME,m_QueueSize=3;
 bool m_cb1PresentPending=true;
 std::deque<int> observed;
 void ReleaseDiscardedBuffers(bool){}
 bool Select(std::unique_lock<CCriticalSection>& lock) SELECTION
 observed=queue;return true;}
 void ResetHDR10AIQueue() RESET
 void Flush(bool saveBuffers) FLUSH
};
int main(){
 CRenderManager retained;retained.Flush(true);
 assert(retained.m_aiQueueGeneration==9 && retained.m_aiStartPts==40000000);
 assert(retained.m_aiFullscreenRequested && !retained.m_aiGuiReady);
 assert(retained.m_presentstep==PRESENT_FRAME && retained.m_presentsource==1);
 assert(retained.m_cb1PresentPending);
 assert(!retained.m_clockSync.m_cb1Phase && retained.m_clockSync.offset==0);
 assert(retained.m_clockSync.resets==1 && retained.m_dvdClock.resets==1);
 std::mutex mutex;std::unique_lock lock(mutex);
 assert(retained.Select(lock) && (retained.observed==std::deque<int>{1}));
 CRenderManager shown;shown.m_aiGuiReady=true;shown.Flush(true);
 assert(shown.m_aiGuiReady && shown.m_aiQueueGeneration==9);
 for(bool requested : {false,true}){
  CRenderManager dropped;dropped.renderer.retained=false;dropped.Flush(requested);
  assert(dropped.m_aiQueueGeneration==10 && dropped.m_aiStartPts==DVD_NOPTS_VALUE);
  assert(!dropped.m_aiFullscreenRequested && !dropped.m_aiGuiReady);
  assert(dropped.m_presentstep==PRESENT_IDLE && dropped.m_presentsource==0);
  assert((dropped.m_free==std::deque<int>{1,2}));
  assert(dropped.m_clockSync.resets==1 && dropped.m_dvdClock.resets==1);
  assert(!dropped.Select(lock));
 }
}
'''.replace('RESET',reset).replace('FLUSH',flush).replace('SELECTION',selection))

    def test_metadata_seek_retires_once_then_begins_new_epoch(self):
        context=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        begin=body(context,'HDR10AISource::Decision CDVBridgeGLES::Context::PrepareHDR10AIQueue(')
        begin=begin.split('  auto& source=HDR10AI();')[0]
        stop=body(context,'bool CDVBridgeGLES::Context::StopHDR10AI()')
        source=body(context,'HDR10AISource& CDVBridgeGLES::Context::HDR10AI()')
        execute(r'''
#include <cassert>
#include <chrono>
#include <memory>
#include <span>
struct AVDynamicHDRPlus{};
struct cb1_ai_result{};struct cb1_hdr10plus_dovi_result{};
enum {CB1_AI_READY,CB1_AI_PENDING,CB1_AI_INVALID,CB1_AI_INCOMPATIBLE};
enum {CB1_HDR10PLUS_DOVI_OK,DVBRIDGE_DV_IDLE,DVBRIDGE_DV_BUSY,DVBRIDGE_DV_FAILED};
struct Side {AVDynamicHDRPlus value;const auto* HDR10Plus()const{return &value;}};
namespace DVBRIDGE {
enum class HDR10SourceMode{Native,HDR10PlusDV,SDR};
struct OutputPreferences{HDR10SourceMode hdr10Source=HDR10SourceMode::HDR10PlusDV;};
struct Binding{unsigned stream=1,revision=2,picture=3;};
bool HDR10PlusDVSnapshotMatches(auto&&...){return true;}
}
int cb1_hdr10plus_dovi_describe(auto*,auto*,void*){return CB1_HDR10PLUS_DOVI_OK;}
void glDeleteSync(void*){}
struct HDR10AISource {
 enum class Decision{Wait,Ignore,Native,Prepare};bool current=false;
 void ReleaseRetired(){};void SetPaused(bool,unsigned long){}
 bool Current(auto&&...)const{return current;}
 bool ResetPending()const{return false;}
 int RecordStatus(auto&&...){return CB1_AI_INCOMPATIBLE;}
 int Begin(auto&&...){current=true;return CB1_AI_READY;}
};
struct Context {
 struct Layer{double pts=40;DVBRIDGE::Binding binding;std::shared_ptr<Side> sourceSideData=std::make_shared<Side>();
 struct{unsigned informationGeneration=1;}sourceInfo;unsigned sourceSerial=1;};
 struct GL{void* gpu=this;};
 struct State{std::unique_ptr<::HDR10AISource> ai=std::make_unique<::HDR10AISource>();
 GL graphics;GL* gl=&graphics;bool aiStopping=false,aiNextFailed=false;void* aiFence=nullptr;
 unsigned aiFencedSubmission=0;};
 std::unique_ptr<State> m_state=std::make_unique<State>();unsigned fences=0,latency=1,busy=0;
 void ClearNextHDR10AI(){};bool Quarantined(){return false;}
 bool FenceLastUse(){++fences;busy=latency;return true;}
 int Poll(){if(busy){--busy;return DVBRIDGE_DV_BUSY;}return DVBRIDGE_DV_IDLE;}
 auto& HDR10AI() SOURCE
 int BeginHDR10AI(auto&&...){return CB1_AI_INVALID;}
 bool StopHDR10AI() STOP
 ::HDR10AISource::Decision Prepare(std::span<const Layer> queue,
 const DVBRIDGE::OutputPreferences& preferences,const char* bundle,unsigned long now,
 bool end,cb1_ai_result* result,bool paused,unsigned long presentationDeadline)
 BEGIN
 return Decision::Prepare;}
};
int main(){for(unsigned latency : {0,1,3}) {
 Context context;context.latency=latency;Context::Layer layer;DVBRIDGE::OutputPreferences prefs;cb1_ai_result output;
 auto prepare=[&]{return context.Prepare({&layer,1},prefs,"",1,false,&output,false,0);};
 for(unsigned i=0;i<latency;++i) {
  assert(prepare()==HDR10AISource::Decision::Wait);
  assert(context.m_state->aiStopping && context.fences==1);
 }
 assert(prepare()==HDR10AISource::Decision::Prepare);
 assert(!context.m_state->aiStopping && context.m_state->ai->current && context.fences==1);
 assert(prepare()==HDR10AISource::Decision::Prepare && context.fences==1);
 }
}
'''.replace('STOP',stop).replace('BEGIN',begin).replace('SOURCE',source))

    def test_rejected_guided_snapshot_signals_error_without_native_completion(self):
        window=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        prepare=body(window,'bool CWinSystemGbmGLESContext::PrepareHDR10AIQueue(')
        stop=prepare[:prepare.index('  // The ordinary commit retires')]
        header=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.h').read_text()
        pending=body(header,'bool HDR10AISelectionPending() const')
        execute(r'''
#include <cassert>
#include <mutex>
namespace DVBRIDGE{
enum class HDR10SourceMode{Native,ReferenceDV,EnhancedDV,HDR10PlusDV,SDR};
enum class OutputRoute{Vanilla,NativeDV};
struct Preferences{unsigned revision=7;HDR10SourceMode hdr10Source=HDR10SourceMode::HDR10PlusDV;};
enum class OutputReason{None,ProcessingPending,SourceIneligible};
struct Caps{bool sourceKnown=true,isHLG=false,isHDR10=true,hdr10PlusSource=true,nativeDV=true,eligible=false,stereoSource=false;};
inline Preferences prefs;inline auto FrameOutputSettings(bool=false,bool=false){return prefs;}
struct Selection{OutputRoute route;OutputReason reason=OutputReason::SourceIneligible;};
// The real selector has separate source/admission controls; this fixture owns teardown only.
auto SelectOutput(const Preferences&,const Caps& c){return Selection{c.eligible?OutputRoute::NativeDV:OutputRoute::Vanilla};}
}
struct Context{bool stopped=true;unsigned calls=0;bool StopHDR10AI(){++calls;return stopped;}};
struct Window{
 Context context;Context* m_dvContext=&context;DVBRIDGE::Caps caps;
 bool m_aiActive=true,m_aiReady=true,m_aiFallback=false,m_dvFatalConsumed=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None;
 struct Binding{unsigned stream{},revision{},picture{};}m_aiActivation{11,2,17};
 enum class StreamHdrType{HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
 struct Picture{struct{int profile=0;}doviSourceInfo;Binding doviSourceBinding;StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;}picture{{},{11,2,17}};
 unsigned m_aiPolicy=7,m_aiSelectionPolicy=7;mutable std::mutex m_dvCapabilityMutex;
 DVBRIDGE::Caps GetDVOutputCapabilities(const Picture*,const DVBRIDGE::Preferences&)const{return caps;}
 bool Pending()const PENDING
 bool Stop(){PREFIX return false;}
};
int main(){
 Window rejected;assert(!rejected.Stop());
 assert(!rejected.m_aiReady && !rejected.m_aiActive);
 assert(rejected.m_dvFatalReason==DVBRIDGE::OutputReason::SourceIneligible);
 assert(!rejected.Pending()); // A failure is not successful native completion.
 rejected.caps.eligible=true;assert(!rejected.Pending() && !rejected.m_aiReady);
 rejected.caps.eligible=false;++rejected.picture.doviSourceBinding.stream;
 assert(!rejected.Stop() && !rejected.m_aiFallback); // New source gets its own admission error, not a native circuit.
 Window busy;busy.context.stopped=false;assert(!busy.Stop());assert(!busy.m_aiReady);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;
 Window native;assert(native.Stop() && !native.Pending() && !native.m_aiReady);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::ReferenceDV;
 Window saved;assert(!saved.Stop() && !saved.Pending() && !saved.m_aiReady);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::HDR10PlusDV;
 Window absent;absent.m_dvContext=nullptr;absent.m_aiActive=absent.m_aiReady=false;
 assert(!absent.Stop());assert(absent.m_dvFatalReason==DVBRIDGE::OutputReason::SourceIneligible);
}
'''.replace('PENDING',pending).replace('PREFIX',stop.lstrip()[1:]))

    def test_hdr10plus_render_storage_tracks_actual_pool_not_live_processing_policy(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text()
        configure=body(source,'unsigned int orientation, bool retainedNativeDV)')
        selection=configure[configure.index('  CVaapiRenderPicture *pic ='):configure.index('#endif')+len('#endif')]
        changed=body(source,'bool CRendererVAAPIGLES::ConfigChanged(')
        orientation=body(source,'bool CRendererVAAPIGLES::DVBridgeOrientationSupported(')
        hdr_types=body((TREE/'xbmc/cores/VideoPlayer/Interface/StreamInfo.h').read_text(),
                       'enum class StreamHdrType')
        helper=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/HDR10SourceType.h').read_text()
        eligible=body(helper,'inline bool IsHDR10AIInput(')
        family=body(helper,'inline bool IsHDR10Family(')
        execute(r'''
#include <cassert>
#include <initializer_list>
#define CB1_HAS_HDR10_AI
constexpr int VA_INVALID_ID=-1,NUM_BUFFERS=6;
constexpr unsigned DVP_FLAG_INTERLACED=1;
enum class StreamHdrType HDR_TYPES;
namespace DVBRIDGE {
enum class HDR10SourceMode{Native,ReferenceDV,HDR10PlusDV,SDR};
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::HDR10PlusDV;};
inline Preferences prefs;inline auto FrameOutputSettings(bool=false,bool=false){return prefs;}
inline bool IsHDR10Family(StreamHdrType source) FAMILY
inline bool IsHDR10AIInput(StreamHdrType source,bool guided) ELIGIBLE
}
struct VideoBuffer {virtual ~VideoBuffer()=default;};
struct CVaapiRenderPicture:VideoBuffer {
 struct {int videoSurface=7,fourcc=11;}procPic;
 unsigned renderBufferCount=36;
};
struct VideoPicture {
 VideoBuffer* videoBuffer;
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;
 struct {unsigned profile=0;}doviSourceInfo;
 unsigned iFlags=0;
};
struct Renderer {
 bool m_isVAAPIBuffer=false,m_aiLookahead=false;
 int m_vaapiFourcc=0;
 unsigned m_aiBuffers=NUM_BUFFERS,m_renderOrientation=0;
 bool DVBridgeOrientationSupported(unsigned orientation)const ORIENTATION
 void SetFps(float) {}
 void Configure(const VideoPicture& picture,unsigned orientation=0,float fps=24){
  m_renderOrientation=orientation;
  SELECTION
 }
 bool ConfigChanged(const VideoPicture& picture) CHANGED
};
int main(){
 using namespace DVBRIDGE;
 CVaapiRenderPicture pool;VideoPicture picture{&pool};Renderer renderer;
 renderer.Configure(picture);
 assert(renderer.m_aiBuffers==36 && renderer.m_aiLookahead && !renderer.ConfigChanged(picture));
 prefs.hdr10Source=HDR10SourceMode::Native;
 assert(!renderer.ConfigChanged(picture) && "A preference change must not pretend the retained 36-slot pool shrank");
 renderer.Configure(picture);
 assert(renderer.m_aiBuffers==36 && renderer.m_aiLookahead);
 pool.renderBufferCount=6;
 assert(renderer.ConfigChanged(picture));renderer.Configure(picture);
 assert(renderer.m_aiBuffers==6 && !renderer.m_aiLookahead);
 prefs.hdr10Source=HDR10SourceMode::HDR10PlusDV;
 assert(!renderer.ConfigChanged(picture) && "Guided admission must not invent decoder surfaces before reopen");
 renderer.Configure(picture);assert(renderer.m_aiBuffers==6 && !renderer.m_aiLookahead);
 pool.renderBufferCount=36;
 assert(renderer.ConfigChanged(picture));renderer.Configure(picture);
 assert(renderer.m_aiBuffers==36 && renderer.m_aiLookahead);
 // Plain HDR10 storage has always followed the actual pool, even in native mode.
 picture.hdrType=StreamHdrType::HDR_TYPE_HDR10;prefs.hdr10Source=HDR10SourceMode::Native;
 renderer.Configure(picture);assert(renderer.m_aiBuffers==36 && !renderer.ConfigChanged(picture));
 // Storage eligibility still excludes SDR, DV, software, interlace and rotation.
 for(auto mode:{HDR10SourceMode::Native,HDR10SourceMode::HDR10PlusDV}){
  prefs.hdr10Source=mode;
  for(unsigned excluded=0;excluded<6;++excluded){
   VideoPicture other{&pool};unsigned rotation=0;pool.procPic.videoSurface=7;
   if(excluded==0)other.hdrType=StreamHdrType::HDR_TYPE_NONE;
   if(excluded==1)other.hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;
   if(excluded==2)other.doviSourceInfo.profile=7;
   if(excluded==3)pool.procPic.videoSurface=VA_INVALID_ID;
   if(excluded==4)other.iFlags=DVP_FLAG_INTERLACED;
   if(excluded==5)rotation=90;
   if(excluded==6)other.hdrType=StreamHdrType::HDR_TYPE_HLG;
   Renderer control;control.Configure(other,rotation);
   assert(control.m_aiBuffers==NUM_BUFFERS && !control.m_aiLookahead);
   assert(!control.ConfigChanged(other));
  }
 }
}
'''.replace('HDR_TYPES',hdr_types).replace('ELIGIBLE',eligible).replace('FAMILY',family).replace('ORIENTATION',orientation)
            .replace('SELECTION',selection).replace('CHANGED',changed))

    def test_strict_dv_failure_does_not_abort_a_native_hdr10_transition(self):
        source=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::PrepareDVOutputFrame(')
        selection=source[source.index('  const auto& source = picture.doviSourceInfo;'):
                         source.index('  if (!PollRejectedDVSurface())')]
        execute(r'''
#include <cassert>
#include <mutex>
namespace DVBRIDGE {
enum class OutputMode{Disabled,Standard,MasterReference};
enum class OutputRoute{Vanilla,DV};enum class OutputReason{None,SourceIneligible,ProcessingPending};
enum class HDR10SourceMode{Native,ReferenceDV};
}
struct Window {
 struct Preferences{DVBRIDGE::OutputMode output=DVBRIDGE::OutputMode::MasterReference;
  bool allowMasterFallback=false;DVBRIDGE::HDR10SourceMode hdr10Source=DVBRIDGE::HDR10SourceMode::Native;}preferences;
 struct Caps{bool sourceKnown=true,isDV=false,isHDR10=true,isHLG=false,stereoSource=false,processingKnown=true;}capabilities;
 struct Picture{struct{int profile=0,compatibility=1;bool el=false;}doviSourceInfo;
  bool doviEnhancement=false;}picture;
 struct{DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::Vanilla;
  DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::SourceIneligible;}m_dvSelection;
 std::mutex m_dvCapabilityMutex;bool m_dvFatalConsumed=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None;
 bool Prepare(){SELECTION return true;}
};
int main(){
 // Native HDR10, AI priming and SDR are not strict-DV source failures.
 for(bool fallback:{false,true}){
  Window hdr;hdr.preferences.allowMasterFallback=fallback;
  assert(hdr.Prepare());assert(hdr.m_dvFatalReason==DVBRIDGE::OutputReason::None);
 }
 Window dv;dv.capabilities.isDV=true;dv.picture.doviSourceInfo.profile=7;
 assert(!dv.Prepare());assert(dv.m_dvFatalReason==DVBRIDGE::OutputReason::SourceIneligible);
 Window standard;standard.capabilities.isDV=true;standard.picture.doviSourceInfo.profile=7;
 standard.preferences.output=DVBRIDGE::OutputMode::Standard;assert(!standard.Prepare()); // Unavailable chosen circuit cannot use ordinary BL.
 Window p5;p5.capabilities.isDV=true;p5.picture.doviSourceInfo.profile=5;
 p5.picture.doviSourceInfo.compatibility=0;p5.preferences.output=DVBRIDGE::OutputMode::Standard;
 assert(!p5.Prepare());
 Window pending;pending.capabilities.isDV=true;pending.capabilities.processingKnown=false;pending.m_dvSelection.reason=DVBRIDGE::OutputReason::ProcessingPending;
 assert(pending.Prepare());
 Window disabled;disabled.capabilities.isDV=true;disabled.preferences.output=DVBRIDGE::OutputMode::Disabled;
 assert(disabled.Prepare());
 Window paired;paired.capabilities.isDV=true;paired.picture.doviSourceInfo.el=true;
 assert(paired.Prepare());
}
'''.replace('SELECTION',selection))

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
 struct {void reset(){}} m_playerLedCpu;
 Context context;Context*m_context=&context;
 int m_hdr10plusAnalysis=0,m_renderer=0,m_pendingInfo=1,m_pendingHDR10Fallback=1;
 std::optional<int>m_hdr10plusMetadata=1;std::vector<int>m_rawELCache{1};
 bool m_firstFrame=false,m_prepared=true,m_packed=true,m_direct=true;
 bool m_pending=true,m_asyncEligible=true,m_dvPolicyActive=true;
 bool m_aiFrame=true,m_aiOutputAccepted=true;
 std::optional<int> m_aiGuidance=1;
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
  assert(!r.m_aiGuidance);
 }
}
'''.replace('RESET',reset).replace('CANCEL',cancel))

    def test_hdr10_analysis_uses_repaired_presentation_pts_not_duplicate_decode_pts(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text(),
                    'bool CRendererVAAPIGLES::BuildDVBridgeLayer(')
        selection=source[source.index('  auto& buffer ='):source.index('  const auto texture =')]
        hdr_types=body((TREE/'xbmc/cores/VideoPlayer/Interface/StreamInfo.h').read_text(),
                       'enum class StreamHdrType')
        eligible=body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/HDR10SourceType.h').read_text(),
                      'inline bool IsHDR10AIInput(')
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
enum class StreamHdrType HDR_TYPES;
namespace DVBRIDGE {
enum class HDR10SourceMode{ReferenceDV,HDR10PlusDV,SDR};
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;
inline auto FrameOutputSettings(bool=false,bool=false){return prefs;}
inline bool IsHDR10AIInput(StreamHdrType source,bool guided) ELIGIBLE
inline bool IsHDR10Family(StreamHdrType source){return IsHDR10AIInput(source,true) || source==StreamHdrType::HDR_TYPE_HLG;}
}
struct Binding{bool Valid()const{return true;}};
struct Picture{StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;
 Binding doviSourceBinding;struct{int profile=0;}doviSourceInfo;
 int64_t doviSourcePts=1000000;double pts=1000000;};
struct Metadata{const void* Data(){return this;}::Binding Binding(){return {};}};
struct Layer{int width,height,layout,scalingMethod;double pts;::Binding binding;};
struct Renderer{
 struct Slot{std::shared_ptr<Picture>doviSourcePicture=std::make_shared<Picture>();
  Metadata doviMetadata;double doviPts=1.25;}m_buffers[1];
 int m_vaapiFourcc=VA_FOURCC_P010,m_sourceWidth=3840,m_sourceHeight=2160;
 int SelectScalingMethod()const{return 17;}
 bool Build(Layer&layer){int idx=0;SELECTION return true;}
};
int main(){
 Renderer r;Layer first{},replayed{};assert(r.Build(first));
 assert(first.scalingMethod==17);
 r.m_buffers[0].doviSourcePicture->pts=1250000;
 assert(r.Build(replayed));assert(first.pts==1.0 && replayed.pts==1.25);
 assert(r.m_buffers[0].doviSourcePicture->doviSourcePts==1000000);
 r.m_buffers[0].doviSourcePicture->pts=DVD_NOPTS_VALUE;assert(!r.Build(replayed));
 r.m_buffers[0].doviSourcePicture->hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;
 r.m_buffers[0].doviSourcePicture->doviSourceInfo.profile=7;
 assert(r.Build(replayed) && replayed.pts==1.25);
}
'''.replace('SELECTION',selection).replace('HDR_TYPES',hdr_types).replace('ELIGIBLE',eligible))

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
        start=source.index('  if (preferences.hdr10Source == DVBRIDGE::HDR10SourceMode::Native')
        native=source[start:source.index('  return {false,',start)]
        preparation=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/BaseRenderer.h').read_text(),
                         'struct HDR10AIQueuePreparation')
        execute(r'''
#include <cassert>
#include <functional>
struct HDR10AIQueuePreparation PREPARATION;
namespace DVBRIDGE {enum class HDR10SourceMode{Native,ReferenceDV,SDR};}
struct Window{
 bool stopped=true;
 template<class... T>bool PrepareHDR10AIQueue(T...){return stopped;}
 bool HDR10AILookaheadActive(){return false;}
};
struct Renderer{
 bool m_aiLookahead=true,m_aiOutputPending=true,m_dvRequested=false,admitted=false;
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
 bool m_hdrFboActive=false,m_bConfigured=true,m_reloadShaders=false;
 bool ConfigureVideoOutput(const VideoPicture& picture) BODY
};
int main(){
 VideoPicture dv{true},native{false};
 Renderer retry;window.output=false;
 assert(!retry.ConfigureVideoOutput(dv) && !retry.m_bConfigured);
 window.output=true;assert(retry.ConfigureVideoOutput(dv) && retry.m_bConfigured);
 retry.m_bConfigured=false;assert(retry.ConfigureVideoOutput(native) && retry.m_bConfigured);
 assert(retry.m_passthroughHDR && retry.m_reloadShaders); // Rebuild the former BT.709 bootstrap shader for native BT.2020 PQ.
 retry.m_reloadShaders=false;
 assert(retry.ConfigureVideoOutput(native) && retry.m_reloadShaders); // Reconfiguration must not reuse output-dependent shader state.
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
enum class HDR10SourceMode{Native,ReferenceDV,HDR10PlusDV,SDR};
struct Preferences{int revision=1;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;inline auto FrameOutputSettings(bool plus=false,bool=false){auto p=prefs;
 if(plus)p.hdr10Source=HDR10SourceMode::HDR10PlusDV;return p;}
}
struct Source{bool guided=false;bool MetadataOnly(){return false;}bool HDR10Plus(){return guided;}
 bool Current(int binding,DVBRIDGE::Preferences p){return binding==7 && p.revision==1 &&
 p.hdr10Source==(guided?DVBRIDGE::HDR10SourceMode::HDR10PlusDV:DVBRIDGE::HDR10SourceMode::ReferenceDV);}};
struct Context{Source source;Source& HDR10AI(){return source;}};
struct Bridge{std::optional<int> committed=1;bool HDR10AISourceHLG(){return false;}
 const auto& CommittedHDR10AI(){return committed;}};
struct Window{Context context;Context* m_dvContext=&context;Bridge bridge;Bridge* m_dvBridge=&bridge;
 int m_aiActivation=7,m_aiPolicy=17,m_aiSelectionPolicy=1;mutable std::mutex m_dvCapabilityMutex;
 bool Committed()const BODY
 bool SelectionPending()const PENDING
};
int main(){
 Window w;assert(w.Committed());
 w.context.source.guided=true;assert(w.Committed()); // Sparse HDR10+ can use AI, not metadata-only.
 w.context.source.guided=false;w.m_aiActivation=8;assert(!w.Committed());
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
        selection=source[:source.index('  if (queue.empty()')]
        execute(r'''
#include <cassert>
#include <mutex>
namespace DVBRIDGE {
enum class HDR10SourceMode{Native,ReferenceDV,HDR10PlusDV,SDR};enum class OutputRoute {Vanilla,DV,NativeDV=DV};
struct Preferences {int revision=1;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;inline auto FrameOutputSettings(bool=false,bool=false){return prefs;}
enum class OutputReason{None,ProcessingPending};
struct Caps{bool sourceKnown=true,isHLG=false,isHDR10=true,hdr10PlusSource=false,nativeDV=true,stereoSource=false;};
struct Selection{OutputRoute route;OutputReason reason=OutputReason::None;};
inline Selection SelectOutput(Preferences p,Caps){return {p.hdr10Source==HDR10SourceMode::Native?OutputRoute::Vanilla:OutputRoute::DV};}
}
struct Context{int stops=0;bool ready=true;bool StopHDR10AI(){++stops;return ready;}};
struct Window{
 std::mutex m_dvCapabilityMutex;bool m_aiActive=true;int m_aiPolicy=17,m_aiSelectionPolicy=0;
 bool m_aiReady=true,m_aiFallback=false,m_dvFatalConsumed=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None;
 struct Binding{int stream{},revision{},picture{};}m_aiActivation{7,17,1};
 enum class StreamHdrType{HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
 struct Picture{struct{int profile=0;}doviSourceInfo;Binding doviSourceBinding;StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;}picture{{},{7,17,1}};
 bool m_dvOrdinaryFrame=false,m_dvEndPending=false,m_dvStopPending=false;
 Context context;Context* m_dvContext=&context;
 auto GetDVOutputCapabilities(Picture*,DVBRIDGE::Preferences){return DVBRIDGE::Caps{};}
 bool Prepare()
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
 assert(w.m_aiPolicy==0 && w.m_aiSelectionPolicy==0 && !w.m_aiReady);
 w.context.ready=true;assert(w.Prepare());
 assert(w.context.stops==2 && !w.m_aiActive && w.m_aiPolicy==0 && w.m_aiSelectionPolicy==1);
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
enum class HDR10SourceMode{Native,ReferenceDV,SDR};
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::Native;};
inline Preferences prefs;inline auto FrameOutputSettings(bool=false,bool=false){return prefs;}
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
enum class HDR10SourceMode{Native,ReferenceDV,SDR};
struct Preferences {int revision=1;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;
 bool SameValues(const Preferences& other)const{return hdr10Source==other.hdr10Source;}};
inline Preferences prefs;inline auto FrameOutputSettings(bool=false,bool=false){return prefs;}
}
struct Binding{int stream=1,picture=1,revision=1;bool operator==(const Binding&)const=default;};
enum class StreamHdrType{HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
struct Picture{struct{int profile=0;}doviSourceInfo;Binding doviSourceBinding;StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;};
struct Preparation {
 struct Outcome{bool ready,lookahead;};bool ready{true};
 std::function<Outcome()> execute;std::function<bool(const Outcome&)> publish;
 bool buffered=false;
};
using HDR10AIQueuePreparation=Preparation;
struct Window {
 bool ready=true,fallback=false;
 bool PrepareHDR10AIQueue(const Picture&,const std::vector<int>&,bool,bool,unsigned long){return ready;}
 bool HDR10AILookaheadActive(){return !fallback && DVBRIDGE::prefs.hdr10Source!=DVBRIDGE::HDR10SourceMode::Native;}
};
struct Renderer {
 bool m_aiLookahead=false,m_aiOutputPending=false,m_dvRequested=false,buffered=false;int admissions=0;
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
 Renderer r;r.buffered=true;assert(r.Capture().buffered);
 r.m_buffers[0].doviSourcePicture->hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;
 assert(!r.Capture().buffered); // Guided/metadata startup keeps its existing admission.
 r.m_buffers[0].doviSourcePicture->hdrType=StreamHdrType::HDR_TYPE_HDR10;r.buffered=false;
 r.output.ready=false;assert(!run(r));assert(r.admissions==0);
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
 // A metadata rejection changes the resolved route without changing user intent.
 r.output.fallback=true;assert(run(r));
 assert(r.admissions==4 && !r.m_dvRequested && !r.m_aiOutputPending);
 assert(DVBRIDGE::prefs.hdr10Source==DVBRIDGE::HDR10SourceMode::ReferenceDV);
 assert(run(r));assert(r.admissions==4); // The latched native route is already admitted.
}
'''.replace('SELECTION',selection))
