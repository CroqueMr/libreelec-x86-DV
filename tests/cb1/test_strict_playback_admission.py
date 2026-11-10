"""Requested circuits keep pending distinct from actual engine failure."""
from test_native_video_source import TREE, body
from test_ai_reentry import execute
import unittest


class StrictPlaybackAdmissionTests(unittest.TestCase):
    def test_error_consumer_uses_the_source_selector_and_not_the_independent_dv_default(self):
        source=body((TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text(),
                    'bool CVideoPlayerVideo::HandleDVPlaybackFailure(')
        consume=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                     'DVBRIDGE::OutputReason CWinSystemGbmGLESContext::ConsumeDVPlaybackFailure(')
        execute(r'''
#include <cassert>
#include <memory>
#include <mutex>
#include <string>
constexpr int LOGERROR=1;
namespace DVBRIDGE {
enum class OutputMode{Standard,Disabled};enum class HDR10SourceMode{Native,ReferenceDV};enum class OutputReason{None,ActivationFailed};
struct Binding{int stream=1,revision=2;bool Valid()const{return true;}};using SourceBinding=Binding;
struct Preferences{OutputMode output=OutputMode::Disabled;HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;inline Preferences FrameOutputSettings(bool=false,bool=false){return prefs;}
struct PlaybackNotification{inline static int errors=0;static void RenderingUnavailable(OutputReason){++errors;}};
}
enum class StreamHdrType{HDR_TYPE_NONE,HDR_TYPE_DOLBYVISION,HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
struct VideoPicture{DVBRIDGE::Binding doviSourceBinding;struct{int profile=0;}doviSourceInfo;StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;std::string stereoMode;};
struct Base{virtual ~Base()=default;};
namespace KODI::WINDOWING::GBM {struct CWinSystemGbmGLESContext:Base{
 std::mutex m_dvCapabilityMutex;DVBRIDGE::Binding m_dvFatalBinding;bool m_dvFatalConsumed=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::ActivationFailed;
 DVBRIDGE::OutputReason ConsumeDVPlaybackFailure(DVBRIDGE::SourceBinding binding) CONSUME
};}
KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker{static Base* GetWinSystem(){return &window;}};
struct CLog{template<class... T>static void Log(T...){}};
struct CDVDMsg{enum{PLAYER_ABORT};};struct CDVDMsgBool{CDVDMsgBool(int,bool){}};
struct Worker{struct{int aborts=0;void Put(std::shared_ptr<CDVDMsgBool>){++aborts;}}m_messageParent;
 bool HandleDVPlaybackFailure(const VideoPicture* picture) HANDLE
};
int main(){VideoPicture picture;Worker worker;
 for(auto family:{StreamHdrType::HDR_TYPE_HDR10,StreamHdrType::HDR_TYPE_HDR10PLUS,StreamHdrType::HDR_TYPE_HLG}){
  picture.hdrType=family;window.m_dvFatalConsumed=false;
  assert(worker.HandleDVPlaybackFailure(&picture));assert(!worker.HandleDVPlaybackFailure(&picture));
 }
 assert(worker.m_messageParent.aborts==3&&DVBRIDGE::PlaybackNotification::errors==3);
 window.m_dvFatalConsumed=false;DVBRIDGE::prefs.output=DVBRIDGE::OutputMode::Standard;
 picture.hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;picture.stereoMode="left_right";
 assert(!worker.HandleDVPlaybackFailure(&picture));picture.stereoMode.clear();
 picture.hdrType=StreamHdrType::HDR_TYPE_NONE;assert(!worker.HandleDVPlaybackFailure(&picture));
 DVBRIDGE::prefs.output=DVBRIDGE::OutputMode::Disabled;
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;window.m_dvFatalConsumed=false;
 assert(!worker.HandleDVPlaybackFailure(&picture)); // An explicit native choice never consumes an old circuit failure.
 picture.hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;assert(!worker.HandleDVPlaybackFailure(&picture));
}
'''.replace('CONSUME',consume).replace('HANDLE',source))

    def test_failed_ai_engine_aborts_without_completing_native_output(self):
        queue=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                   'bool CWinSystemGbmGLESContext::PrepareHDR10AIQueue(')
        execute(r'''
#include <cassert>
#include <memory>
#include <mutex>
#include <span>
#include <vector>
#define CB1_HAS_HDR10_AI
enum {CB1_AI_READY,CB1_AI_PENDING,CB1_AI_INCOMPATIBLE};constexpr int LOGWARNING=1;
constexpr const char* CB1_L1L3_BUNDLE_DIR="unused";
namespace DVBRIDGE {
enum class OutputRoute{Vanilla,NativeDV};enum class OutputReason{None,ActivationFailed,ProcessingPending,NoDVTransport};
enum class HDR10SourceMode{Native,ReferenceDV,HDR10PlusDV,SDR};
struct SourceBinding{int stream=1,revision=2,picture=3;bool operator==(const SourceBinding&)const=default;};
struct Preferences{HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;int revision=4;};
Preferences prefs;auto FrameOutputSettings(bool,bool){return prefs;}
struct Caps{bool sourceKnown=true,isHDR10=true,isHLG=false,hdr10PlusSource=false,nativeDV=true,stereoSource=false,processingKnown=true;};
struct Selection{OutputRoute route=OutputRoute::NativeDV;int policy=1;OutputReason reason{};};
Selection SelectOutput(const Preferences& p,const Caps& c){if(p.hdr10Source==HDR10SourceMode::Native)return {OutputRoute::Vanilla,0,{}};
 if(c.stereoSource)return {OutputRoute::Vanilla,1,OutputReason::NoDVTransport};
 if(!c.processingKnown)return {OutputRoute::Vanilla,1,OutputReason::ProcessingPending};
 if(!c.nativeDV)return {OutputRoute::Vanilla,1,OutputReason::NoDVTransport};return {};}
unsigned DiagnosticNowMs(){return 1000;}template<class... T>void DiagnosticLog(T...){}
struct PlaybackNotification{static void HDR10Recovery(){}};
}
struct HDR10AISource{enum class Decision{Wait,Native,Prepare,Ignore};};
struct cb1_ai_result{};
enum class StreamHdrType{HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
struct VideoPicture{StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;struct{int profile=0;}doviSourceInfo;DVBRIDGE::SourceBinding doviSourceBinding;};
struct CDVBridgeGLES{
 struct Layer{DVBRIDGE::SourceBinding binding;double pts=0;};
 enum class FrameStatus{Pending,Ready,Reused,Failed,Unsupported};
 static inline HDR10AISource::Decision decision=HDR10AISource::Decision::Wait;
 bool CommittedHDR10AI(){return true;}
 FrameStatus PrepareHDR10AIFrame(const Layer&,int,const DVBRIDGE::Preferences&,const cb1_ai_result&,int){return FrameStatus::Ready;}
 struct Context{
  bool Initialize(bool){return true;}bool StopHDR10AI(){return true;}
  auto PrepareHDR10AIQueue(std::span<const Layer>,const DVBRIDGE::Preferences&,const char*,unsigned,bool,cb1_ai_result*,bool,unsigned long){return decision;}
  Context& HDR10AI(){return *this;}void RecordStatus(const char*,int){}
  auto Preparation(DVBRIDGE::SourceBinding,int,unsigned){return decision;}
  struct MetricsType{int pictures=0,gpu_submissions=0,readback_bytes=0,inferences=0;};auto Metrics()const{return MetricsType{};}
  const char* DiagnosticStage()const{return "engine";}int DiagnosticStatus()const{return CB1_AI_INCOMPATIBLE;}
  bool AwaitingPresentation()const{return false;}bool Committed()const{return false;}int LastSubmitted()const{return 0;}
 };
};
struct Window{
 std::mutex m_dvCapabilityMutex;DVBRIDGE::Caps caps;DVBRIDGE::SourceBinding m_aiActivation;
 int m_aiPolicy=4,m_aiSelectionPolicy=4,m_dvImportGeometry=0;struct{int policy=1;}m_dvSelection;
 bool m_aiActive=false,m_aiReady=false,m_aiFallback=false,m_dvOrdinaryFrame=false,m_dvEndPending=false,m_dvStopPending=false,m_dispReset=false,m_dvFatalConsumed=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None;
 std::shared_ptr<CDVBridgeGLES::Context>m_dvContext=std::make_shared<CDVBridgeGLES::Context>();
 std::shared_ptr<CDVBridgeGLES>m_dvBridge=std::make_shared<CDVBridgeGLES>();
 auto GetDVOutputCapabilities(const VideoPicture*,const DVBRIDGE::Preferences&){return caps;}
 bool PrepareDVOutputFrame(const VideoPicture&){return true;}bool BeginDVBridge(){return true;}
 bool PrepareHDR10AIQueue(const VideoPicture& picture,std::span<const CDVBridgeGLES::Layer> queue,bool end,bool paused,unsigned long presentationDeadline) QUEUE
};
int main(){using D=HDR10AISource::Decision;std::vector<CDVBridgeGLES::Layer> queue(1);VideoPicture picture;
 for(bool hlg:{false,true}){Window w;w.caps.isHLG=hlg;w.caps.isHDR10=!hlg;
  CDVBridgeGLES::decision=D::Wait;assert(!w.PrepareHDR10AIQueue(picture,queue,false,false,0));assert(w.m_dvFatalReason==DVBRIDGE::OutputReason::None);
  CDVBridgeGLES::decision=D::Prepare;assert(w.PrepareHDR10AIQueue(picture,queue,false,false,0));
  CDVBridgeGLES::decision=D::Native;assert(!w.PrepareHDR10AIQueue(picture,queue,false,false,0));
  assert(w.m_dvFatalReason==DVBRIDGE::OutputReason::ActivationFailed);
  assert(!w.PrepareHDR10AIQueue(picture,queue,false,false,0));
 }
 Window unavailable;unavailable.caps.nativeDV=false;assert(!unavailable.PrepareHDR10AIQueue(picture,queue,false,false,0));
 assert(unavailable.m_dvFatalReason==DVBRIDGE::OutputReason::NoDVTransport);
 Window stereo;stereo.caps.stereoSource=true;assert(stereo.PrepareHDR10AIQueue(picture,queue,false,false,0));
 assert(stereo.m_dvFatalReason==DVBRIDGE::OutputReason::None);
 Window importing;importing.caps.processingKnown=false;assert(!importing.PrepareHDR10AIQueue(picture,queue,false,false,0));
 assert(importing.m_dvFatalReason==DVBRIDGE::OutputReason::None);
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::Native;Window native;
 assert(native.PrepareHDR10AIQueue(picture,queue,false,false,0));assert(native.m_dvFatalReason==DVBRIDGE::OutputReason::None);
}
'''.replace('QUEUE',queue))

    def test_master_headroom_and_ai_readiness_never_replace_the_requested_circuit(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        method=body(source,'DVBRIDGE::OutputSelection CWinSystemGbmGLESContext::SelectedDVOutput(const VideoPicture* picture,')
        execute(r'''
#include <cassert>
#include <mutex>
#define CB1_HAS_HDR10_AI
constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=5,DVBRIDGE_MODE_STANDARD=1,DVBRIDGE_MODE_SDR=7;
namespace DVBRIDGE {
enum class OutputRoute{Vanilla,NativeDV};enum class OutputReason{None,ActivationFailed,ProcessingPending};
enum class HDR10SourceMode{ReferenceDV,HDR10PlusDV};
struct Binding{int stream=1,revision=2;bool Valid()const{return true;}};
struct OutputCapabilities{bool nativeDV=true,hdr10=true,isHDR10=false,isHLG=false,hdr10PlusSource=false;
 struct{bool usable=true;OutputReason reason{};}processing[8];};
struct OutputPreferences{int revision=3;bool allowMasterFallback=true;auto HDR10Mode(bool)const{return HDR10SourceMode::ReferenceDV;}};
struct OutputSelection{OutputRoute route=OutputRoute::NativeDV;struct{int mode=5;bool master_ipt=true;}policy;OutputReason reason{};};
OutputSelection SelectOutput(const OutputPreferences&,const OutputCapabilities&){return {};}
using SourceBinding=Binding;
}
struct VideoPicture{DVBRIDGE::Binding doviSourceBinding;struct{DVBRIDGE::Binding Binding()const{return {};}}doviMetadata;};
struct Window{
 std::mutex m_dvCapabilityMutex;int m_dvActivationStream=1,m_dvActivationPolicy=3;
 bool m_dvNativeFailed=false,m_dvHDR10Failed=false,m_dvSDRFailed=false;
 DVBRIDGE::OutputReason m_dvActivationReason=DVBRIDGE::OutputReason::None;
 struct{bool Active(int,int,int)const{return true;}}m_masterSafety;
 bool m_aiReady=false,m_aiFallback=false;DVBRIDGE::Binding m_aiActivation;int m_aiPolicy=3;
 auto Select(const VideoPicture* picture,const DVBRIDGE::OutputPreferences& preferences,DVBRIDGE::OutputCapabilities& caps) METHOD
};
int main(){Window w;VideoPicture picture;DVBRIDGE::OutputPreferences preferences;DVBRIDGE::OutputCapabilities caps;
 auto selected=w.Select(&picture,preferences,caps);assert(selected.policy.mode==DVBRIDGE_MODE_MASTER_REFERENCE);
 caps.isHDR10=true;selected=w.Select(&picture,preferences,caps);
 assert(selected.route==DVBRIDGE::OutputRoute::Vanilla&&selected.reason==DVBRIDGE::OutputReason::ProcessingPending);
 w.m_aiReady=true;selected=w.Select(&picture,preferences,caps);assert(selected.route==DVBRIDGE::OutputRoute::NativeDV);
 w.m_aiFallback=true;selected=w.Select(&picture,preferences,caps);
 assert(selected.route==DVBRIDGE::OutputRoute::Vanilla&&selected.reason==DVBRIDGE::OutputReason::ActivationFailed);
 w.m_aiActivation.stream=2;selected=w.Select(&picture,preferences,caps);
 assert(selected.reason==DVBRIDGE::OutputReason::ProcessingPending); // An old failure cannot cross source identity.
}
'''.replace('METHOD',method))

    def test_unavailable_source_failure_and_kodi_default_are_independent(self):
        source=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::PrepareDVOutputFrame(')
        start=source.index('  const auto& source = picture.doviSourceInfo;')
        error=source[start:source.index('  if (!PollRejectedDVSurface())',start)]
        execute(r'''
#include <cassert>
#include <mutex>
namespace DVBRIDGE {
enum class OutputMode{Disabled,Standard,MasterReference};enum class HDR10SourceMode{Native,ReferenceDV,SDR};
enum class OutputRoute{Vanilla,DV};enum class OutputReason{None,SourceIneligible,ProcessingPending,ActivationFailed};
}
struct Window{
 struct{DVBRIDGE::OutputMode output=DVBRIDGE::OutputMode::Standard;bool allowMasterFallback=false;
 DVBRIDGE::HDR10SourceMode hdr10Source=DVBRIDGE::HDR10SourceMode::ReferenceDV;}preferences;
 struct{bool sourceKnown=true,isDV=true,isHDR10=false,isHLG=false,processingKnown=true,stereoSource=false;}capabilities;
 struct{struct{int profile=7,compatibility=1;bool el=false;}doviSourceInfo;bool doviEnhancement=false;}picture;
 struct{DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::Vanilla;
 DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::ActivationFailed;}m_dvSelection;
 std::mutex m_dvCapabilityMutex;bool m_dvFatalConsumed=false;DVBRIDGE::OutputReason m_dvFatalReason{};
 bool Prepare(){ERROR return true;}
};
int main(){using namespace DVBRIDGE;
 for(int family=0;family<3;++family){Window w;w.capabilities.isDV=family==0;w.capabilities.isHDR10=family==1;w.capabilities.isHLG=family==2;
  if(family)w.preferences.output=OutputMode::Disabled; // Independent DV selector cannot mask HDR/HLG failure.
  assert(!w.Prepare()&&w.m_dvFatalReason==OutputReason::ActivationFailed);
  Window pending;pending.m_dvSelection.reason=OutputReason::ProcessingPending;assert(pending.Prepare());
  Window native;native.preferences.output=OutputMode::Disabled;native.preferences.hdr10Source=HDR10SourceMode::Native;
  native.capabilities=w.capabilities;assert(native.Prepare());
 }
 Window unknown;unknown.capabilities.sourceKnown=false;assert(unknown.Prepare());
 Window stereo;stereo.capabilities.stereoSource=true;stereo.m_dvSelection.reason=OutputReason::SourceIneligible;
 assert(stereo.Prepare()&&stereo.m_dvFatalReason==OutputReason::None);
}
'''.replace('ERROR',error))

if __name__=='__main__':unittest.main()
