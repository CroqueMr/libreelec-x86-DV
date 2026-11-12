"""Keep ordinary output native without bypassing an owned CB1 restoration."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class OrdinaryOutputIsolationTests(unittest.TestCase):
    def test_idle_context_is_not_output_ownership(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        signatures = (
            'bool CWinSystemGbmGLESContext::SetVideoOutput(const VideoPicture* picture)',
            'bool CWinSystemGbmGLESContext::PrepareOrdinaryDVOutput(const VideoPicture* picture)',
            'bool CWinSystemGbmGLESContext::RetireDVContext()',
            'bool CWinSystemGbmGLESContext::PrepareDVOutputFrame(const VideoPicture& picture)',
        )
        methods = '\n'.join(signature + body(source, signature) for signature in signatures)
        program = r'''
#include <memory>
#include <optional>
#include <string>
#include <iostream>
#include <mutex>
#include "windowing/gbm/ModeChangeHold.h"
using KODI::WINDOWING::GBM::CHeldModeAnnouncement;
constexpr int DVBRIDGE_DV_IDLE=0;
constexpr int LOGWARNING=1,AVCOL_TRC_GAMMA22=4;
struct Services {Services& GetWindowManager(){return *this;}void MarkDirty(){}};
struct CServiceBroker {static Services* GetGUI(){static Services value;return &value;}};
enum class StreamHdrType {HDR_TYPE_NONE,HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG,HDR_TYPE_DOLBYVISION};
struct Binding {unsigned stream=0,picture=0,revision=0; bool Valid() const {return stream!=0;}};
struct VideoPicture {
 Binding doviSourceBinding; struct {::Binding value;::Binding Binding() const {return value;}} doviMetadata;
 struct {int profile=0,compatibility=0;bool el=false;unsigned informationGeneration=0;} doviSourceInfo;
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_NONE; std::string strDVELType;
 bool doviEnhancement=false; int color_transfer=0;double pts=0;
};
namespace DVBRIDGE {
 enum class OutputMode {Disabled=2,Standard=0,HDR10=1,MasterReference=4,SDR=6}; enum class OutputRoute {Vanilla,NativeDV,HDR10,SDR,PlayerLed};
 enum class OutputReason {None,RestoreFailed,SourceIneligible,TVProfileRequired,ProcessingPending};
 enum class HDR10SourceMode {Native,ReferenceDV};
 struct Policy {int mode=0;};
 struct Preferences {OutputMode output=OutputMode::Standard; unsigned revision=1;bool allowMasterFallback=true;
   double peak=1000;int panel=0,gamut=2;HDR10SourceMode hdr10Source=HDR10SourceMode::Native;
   ::DVBRIDGE::Policy Policy()const{return {};}};
 Preferences FrameOutputSettings(bool=false,bool=false){return {};}
 bool DiagnosticsEnabled(){return false;}
 std::string lastStage;
 void DiagnosticStage(const char* stage){lastStage=stage;}
 template<class... T> void ObserveDiagnostic(T...){}
 template<class... T> bool DiagnosticLog(T...){return true;}
 using SourceBinding=::Binding;
 int PolicyCode(Policy){return 0;}
 struct StreamTelemetry {
  struct Snapshot {struct {OutputReason reason=OutputReason::None;} transaction;};
  static Snapshot Read(){return {};}
  template<class... T> static void NativeFailure(T...){}
  template<class... T> static void PublishNativePending(T...){}
  template<class... T> static void NativeSelection(T...){}
 };
}
struct Capabilities {bool isDV=false,isHDR10=false,isHLG=false,stereoSource=false,processingKnown=true,sourceKnown=false,nativeDV=true;};
struct Selection {DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::Vanilla;
 DVBRIDGE::Policy policy;DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::None;};
struct CDVBridgeGLES {
 bool PlayerLed()const{return false;}
 struct Context {
  static bool NewContextBlocked(){return false;}
  bool gl=true,ready=true; int initialized=0,closed=0,fences=0;
  bool GL() const {return gl;} int Poll(){return ready ? DVBRIDGE_DV_IDLE : 1;}
  bool Initialize(bool){++initialized;gl=true;return true;}
  bool FenceLastUse(){++fences;return true;}
  bool Close(){++closed;gl=false;return true;}
 };
 bool rebindHDR=false,rebindSDR=false;
 void Cancel(){} bool RebindOutputSurface(bool hdr10,bool sdr=false,unsigned=0){rebindHDR=hdr10;rebindSDR=sdr;return true;}
 template<class... T> Binding SelectionIdentity(T...){return {};}
};
struct State {bool captured=false; bool Captured()const{return captured;}
 template<class T> bool Stage(T&,bool){return true;}};
struct DRM {virtual ~DRM()=default;};
struct CDRMAtomic : DRM {
 unsigned DVActivationFailures(){return 0;}
 void SetDVActivationPending(bool){} void* GetConnector(){return this;}
 bool AddProperty(void*,const char*,unsigned){return true;}
};
struct GBM {int lifetime=0; GBM& GetDevice(){return *this;}
 void UseDVOutputLifetime(){++lifetime;}};
struct CWinSystemGbmEGLContext {
 bool transaction=false,pending=false,baseOK=true,formatChanges=true; int native=0,stages=0;
 int depth=8,targetDepth=8;
 void UseDVOutputSurfaceTransaction(bool value){transaction=value;}
 bool HasPendingDVOutputSurface(){return pending;}
 bool SetVideoOutput(const VideoPicture*) {
  ++native;if(!baseOK)return false;
  if(transaction){++stages;pending=formatChanges;} depth=targetDepth;return true;
 }
};
struct CWinSystemGbmGLESContext : CWinSystemGbmEGLContext {
 bool requested=false,m_dvStopPending=false,m_dvOrdinaryFrame=false;
 bool m_dvActivating=false,m_dvOutputRetiring=false,m_hdrConversion=false,m_sdrConversion=false,m_dvPriorSDRConversion=false;
 bool m_pascalHDRActive=false,m_priorPascalHDRActive=false;
 unsigned HDR10Framebuffer()const{return 0;}
 bool m_dvPriorHDRConversion=false,m_dvPriorGuiCompositing=false,m_guiCompositing=false;
 float m_guiSDRGamma=2.4f,m_dvPriorGuiSDRGamma=2.4f;
 bool m_cb1FramePending=false,m_dvFrame=false,m_dvNativeGui=false;
 bool m_failedHDR10SetupRestore=false,m_dvShutdownFence=false;
 bool completeOK=true,pollOK=true,restoreOK=true,modeOK=true,recoveryOK=true;
 Capabilities capabilities;
 bool m_dvSuperseded=false,m_dvRollbackFailed=false,m_dvFatalConsumed=false,m_dvNativeFailed=false,m_dvFallbackActive=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None,m_dvActivationReason=DVBRIDGE::OutputReason::None;
 std::mutex m_dvCapabilityMutex;
 unsigned m_dvAttemptFailures=0,m_hdr10SessionStream=0;
 uint64_t m_dvProfileLoggedRevision{},m_dvProfileLoggedStream{};
 std::optional<int> m_hdr10Session;
 struct {template<class... T> void Begin(T...){}} m_masterSafety;
 bool m_cb1RestoringPreferences=false;
 int ordinaryStages=0;
 std::optional<int> m_dvPriorConfiguredOutput,m_dvConfiguredOutput,m_hdr10Signal;
 std::optional<unsigned> m_hdrDeepColorPrevious;
 unsigned m_dvPendingStream=0,m_dvPendingPolicy=0;
 struct {void Cancel(){}} m_modeHold;
 CHeldModeAnnouncement m_modeAnnouncement;
 State m_dvState;
 Selection m_dvSelection;
 std::shared_ptr<CDVBridgeGLES::Context> m_dvContext;
 std::unique_ptr<CDVBridgeGLES> m_dvBridge;
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<GBM> m_GBM=std::make_shared<GBM>();
 bool StopDVBridgePlayback(){return true;}
 bool SupportsDVOutputMode(){return modeOK;}
 bool SupportsSDRConversion(){return modeOK;}
 bool DVBridgeRequested(const VideoPicture*){return requested;}
 bool CompleteDVBridgePage(){return completeOK;}
 bool RecoverDVActivation(){return recoveryOK;}
 void ResetDVActivation(const VideoPicture*){}
 Capabilities GetDVOutputCapabilities(const VideoPicture*){return capabilities;}
 Capabilities GetDVOutputCapabilities(const VideoPicture*,DVBRIDGE::Preferences){return capabilities;}
 Selection SelectedDVOutput(const VideoPicture*){return m_dvSelection;}
 Selection SelectedDVOutput(const VideoPicture*,DVBRIDGE::Preferences,Capabilities){return m_dvSelection;}
 bool PollRejectedDVSurface(){return pollOK;}
 bool RejectDVOutputSurface(){return true;}
 bool EndDVBridge(){return restoreOK;}
 void SetColorimetry(const VideoPicture*){}
 bool SetHDR(const VideoPicture* picture){++ordinaryStages;return picture && picture->color_transfer;}
 bool SetGuiCompositing(int color){m_guiCompositing=color!=0;return true;}
 bool SetVideoOutput(const VideoPicture*);
 bool StageCB1ConnectorPreferences(bool){return true;}
 bool PrepareOrdinaryDVOutput(const VideoPicture*);
 bool RetireDVContext();
 bool PrepareDVOutputFrame(const VideoPicture&);
 bool ConfigureSDRConversion(const VideoPicture&){m_sdrConversion=m_hdrConversion=true;return true;}
 int hdrConfigurations=0;
 bool ConfigureHDR10Conversion(const VideoPicture& p){
  ++hdrConfigurations;if(depth<10)return false;
  m_hdrConversion=true;m_hdr10Session=1;m_hdr10SessionStream=p.doviMetadata.Binding().stream;
  return true;
 }
 bool BeginDVBridge(){m_dvState.captured=true;return true;}
};
METHODS
int main(){
 int failures=0,cases=0;
 auto expect=[&](bool value,const std::string& name){++cases;std::cout<<(value?"PASS ":"FAIL ")<<name<<'\n';failures+=!value;};
 for(int gate=0;gate<7;++gate){
  CWinSystemGbmGLESContext window;VideoPicture picture;
  const char* stages[]={"output-stop-pending","output-mode-unavailable",
    "output-restore-pending","output-await-previous-scanout",
    "output-await-source-import","output-await-fel","output-await-rejected-scanout"};
  if(gate==0)window.m_dvStopPending=true;
  if(gate==1){window.modeOK=false;window.requested=true;}
  if(gate==2)window.recoveryOK=false;
  if(gate==3){window.m_dvOrdinaryFrame=true;window.pending=true;}
  if(gate==4){window.capabilities.isDV=true;window.capabilities.processingKnown=false;}
  if(gate==5){window.capabilities.isDV=true;picture.strDVELType="FEL";}
  if(gate==6)window.pollOK=false;
  DVBRIDGE::lastStage.clear();
  expect(!window.PrepareDVOutputFrame(picture) && DVBRIDGE::lastStage==stages[gate],
         std::string("preparation identifies deferred gate ")+stages[gate]);
  expect(window.native==0 && window.stages==0,"deferred gate does not activate output");
 }
 for(auto hdr : {StreamHdrType::HDR_TYPE_NONE,StreamHdrType::HDR_TYPE_HDR10,StreamHdrType::HDR_TYPE_HLG}) {
  VideoPicture picture;picture.hdrType=hdr;picture.color_transfer=hdr==StreamHdrType::HDR_TYPE_NONE?0:18;
  const auto name=hdr==StreamHdrType::HDR_TYPE_NONE?"SDR":hdr==StreamHdrType::HDR_TYPE_HDR10?"HDR10":"HLG/PVR";
  for(int history=0;history<3;++history){
   CWinSystemGbmGLESContext window;
   if(history) window.m_dvContext=std::make_shared<CDVBridgeGLES::Context>();
   if(history==2) expect(window.RetireDVContext() && !window.m_dvContext->GL(),std::string(name)+" retirement completed");
   const bool accepted=window.SetVideoOutput(&picture);
   expect(accepted && window.native==1 && window.stages==0 && !window.pending &&
          !window.m_dvOrdinaryFrame && window.m_GBM->lifetime==0,
          std::string(name)+" ordinary history="+std::to_string(history)+" no DV surface transaction");
  }
 }
 {
  CWinSystemGbmGLESContext window;VideoPicture picture;
  window.capabilities.isDV=true;picture.doviSourceInfo.profile=7;picture.doviEnhancement=true;
  window.m_dvSelection.reason=DVBRIDGE::OutputReason::TVProfileRequired;
  DVBRIDGE::lastStage.clear();
  expect(window.PrepareDVOutputFrame(picture) && window.native==1 && window.stages==0 &&
         !window.m_dvOrdinaryFrame && DVBRIDGE::lastStage=="output-tv-profile-required",
         "missing TV profile stays ordinary and identifies its prerequisite");
 }
 for(int kind=0;kind<3;++kind){
  CWinSystemGbmGLESContext window;VideoPicture picture;
  window.requested=kind==0;window.m_dvState.captured=kind==1;window.m_hdrConversion=kind==2;
  window.m_dvSelection.route=window.requested?DVBRIDGE::OutputRoute::NativeDV:DVBRIDGE::OutputRoute::Vanilla;
  window.m_dvContext=std::make_shared<CDVBridgeGLES::Context>();
  expect(window.SetVideoOutput(&picture) && window.stages==1 && window.pending &&
         window.m_dvOrdinaryFrame==(kind!=0),
         "real CB1 activation/restore remains transactional kind="+std::to_string(kind));
  expect(window.m_modeAnnouncement.Pending()==CHeldModeAnnouncement::Step::BEFORE_NEXT,
         "same-refresh transport entry/exit announces its actual commit");
 }
 for(auto route : {DVBRIDGE::OutputRoute::NativeDV,DVBRIDGE::OutputRoute::HDR10}) {
  CWinSystemGbmGLESContext window;VideoPicture picture;window.requested=true;
  window.m_dvSelection.route=route;
  window.m_dvState.captured=route==DVBRIDGE::OutputRoute::NativeDV;
  window.m_hdrConversion=route==DVBRIDGE::OutputRoute::HDR10;
  expect(window.SetVideoOutput(&picture) && window.m_modeAnnouncement.Pending()==CHeldModeAnnouncement::Step::NONE,
         "stable transport does not announce a metadata/policy-only update");
 }
 // A retained RGB renderer entering SDR must bind the native SDR drawable,
 // rather than applying HDR10's deep-colour requirement to its 8-bit successor.
 {
  CWinSystemGbmGLESContext window;VideoPicture picture;window.requested=true;
  window.m_dvSelection.route=DVBRIDGE::OutputRoute::SDR;
  window.m_dvBridge=std::make_unique<CDVBridgeGLES>();
  window.m_dvContext=std::make_shared<CDVBridgeGLES::Context>();
  expect(window.SetVideoOutput(&picture) && window.depth==8 &&
         window.m_dvBridge->rebindHDR && window.m_dvBridge->rebindSDR,
         "SDR transaction forwards native drawable identity to retained RGB renderer");
 }
 // A successful session can outlive a rejected surface: rollback restores the
 // ordinary 8-bit drawable and ownership, not the cached session's stream.
 for(int history=0;history<4;++history) {
  CWinSystemGbmGLESContext window;VideoPicture next;
  window.requested=true;window.capabilities.isDV=true;next.doviSourceInfo.profile=8;
  next.doviMetadata.value.stream=2;window.m_hdr10Session=1;window.m_hdr10SessionStream=1;
  window.m_dvSelection.route=DVBRIDGE::OutputRoute::HDR10;
  window.targetDepth=10;
  if(history==1){window.m_hdrConversion=true;window.depth=10;}
  if(history==2){window.m_dvContext=std::make_shared<CDVBridgeGLES::Context>();window.m_dvContext->ready=false;}
  if(history==3)window.baseOK=false;
  const bool ready=window.PrepareDVOutputFrame(next);
  if(history==0)
   expect(ready && window.depth==10 && window.stages==1 && window.hdrConfigurations==1 &&
          window.m_hdr10SessionStream==2,"rejected HDR session stages native 10-bit output before reconfiguration");
  else if(history==1)
   expect(ready && window.native==0 && window.hdrConfigurations==1 && window.m_hdr10SessionStream==2,
          "live HDR transport refreshes the source session without replacing its surface");
  else
   expect(!ready && window.hdrConfigurations==0,
          "stale session cannot bypass GPU retirement or failed native surface setup history="+std::to_string(history));
 }
 for(auto hdr : {StreamHdrType::HDR_TYPE_NONE,StreamHdrType::HDR_TYPE_HDR10,StreamHdrType::HDR_TYPE_HLG}) {
  for(int history=0;history<2;++history) {
   CWinSystemGbmGLESContext window; VideoPicture picture;picture.hdrType=hdr;
   picture.doviSourceBinding.stream=1;
   if(history)window.m_dvContext=std::make_shared<CDVBridgeGLES::Context>();
   expect(window.PrepareDVOutputFrame(picture) && window.stages==0 && !window.m_dvOrdinaryFrame,
          "ordinary PrepareDVOutputFrame type="+std::to_string(int(hdr))+" history="+std::to_string(history)+" stays native");
  }
 }
 for(int kind=0;kind<3;++kind){
  CWinSystemGbmGLESContext window;VideoPicture picture;
  window.m_dvState.captured=kind==0;window.m_hdrConversion=kind==1;window.pending=kind==2;
  expect(window.PrepareDVOutputFrame(picture) && window.m_dvOrdinaryFrame,
         "Prepare retains actual ordinary successor kind="+std::to_string(kind));
  expect(window.ordinaryStages==1,
         "ordinary successor initializes native metadata exactly once kind="+std::to_string(kind));
 }
 CWinSystemGbmGLESContext pending;pending.requested=true;pending.pending=true;VideoPicture picture;
 expect(!pending.SetVideoOutput(&picture) && pending.native==0,"pending transaction cannot be overwritten");
 CWinSystemGbmGLESContext ordinaryPending;ordinaryPending.pending=true;
 expect(!ordinaryPending.SetVideoOutput(&picture) && ordinaryPending.native==0 && ordinaryPending.pending,
        "pending ordinary successor cannot enter native output with no active CB1 route");
 for(bool formatChanges : {true,false}) {
  CWinSystemGbmGLESContext restore;restore.m_hdrConversion=true;restore.formatChanges=formatChanges;
  expect(restore.SetVideoOutput(&picture) && !restore.m_hdrConversion && restore.m_dvOrdinaryFrame &&
         restore.pending==formatChanges && restore.native==1 && restore.stages==1,
         std::string("HDR conversion stages an owned ordinary successor format-change=")+std::to_string(formatChanges));
  const bool repeated=restore.SetVideoOutput(nullptr);
  expect(!repeated && restore.native==1 && restore.stages==1 && restore.m_dvOrdinaryFrame &&
         restore.pending==formatChanges,
         std::string("repeat before Present cannot overwrite ordinary successor format-change=")+std::to_string(formatChanges));
 }
 CWinSystemGbmGLESContext busy;busy.m_dvState.captured=true;
 busy.m_dvContext=std::make_shared<CDVBridgeGLES::Context>();busy.m_dvContext->ready=false;
 expect(!busy.SetVideoOutput(&picture) && busy.native==0,"busy actual DV restoration remains deferred");
 std::cout<<cases-failures<<"/"<<cases<<" cases passed\n";
 return failures?1:0;
}
'''.replace('METHODS', methods)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code = root / 'check.cpp'
            binary = root / 'check'
            code.write_text(program)
            build = subprocess.run(
                ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-I'+str(TREE/'xbmc'),str(code), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

