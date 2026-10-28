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
            'bool CWinSystemGbmGLESContext::StageOrdinaryDVOutput(const VideoPicture* picture)',
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
constexpr int DVBRIDGE_DV_IDLE=0;
struct Services {Services& GetWindowManager(){return *this;}void MarkDirty(){}};
struct CServiceBroker {static Services* GetGUI(){static Services value;return &value;}};
enum class StreamHdrType {HDR_TYPE_NONE,HDR_TYPE_HDR10,HDR_TYPE_HLG,HDR_TYPE_DOLBYVISION};
struct Binding {unsigned stream=0,picture=0,revision=0; bool Valid() const {return stream!=0;}};
struct VideoPicture {
 Binding doviSourceBinding; struct {::Binding Binding() const {return {};}} doviMetadata;
 struct {int profile=0,compatibility=0;bool el=false;unsigned informationGeneration=0;} doviSourceInfo;
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_NONE; std::string strDVELType;
 bool doviEnhancement=false; int color_transfer=0;double pts=0;
};
namespace DVBRIDGE {
 enum class OutputMode {Disabled,Standard,HDR10,MasterReference}; enum class OutputRoute {Vanilla,NativeDV,HDR10};
 enum class OutputReason {None,RestoreFailed,SourceIneligible,TVProfileRequired};
 struct Policy {int mode=0;};
 struct Preferences {OutputMode output=OutputMode::Standard; unsigned revision=1;bool allowMasterFallback=true;
   ::DVBRIDGE::Policy Policy()const{return {};}};
 Preferences FrameOutputSettings(){return {};}
 bool DiagnosticsEnabled(){return false;}
 std::string lastStage;
 void DiagnosticStage(const char* stage){lastStage=stage;}
 template<class... T> void ObserveDiagnostic(T...){}
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
struct Capabilities {bool isDV=false,processingKnown=true,sourceKnown=false,nativeDV=true;};
struct Selection {DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::Vanilla;
 DVBRIDGE::Policy policy;DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::None;};
struct CDVBridgeGLES {
 struct Context {
  static bool NewContextBlocked(){return false;}
  bool gl=true,ready=true; int initialized=0,closed=0,fences=0;
  bool GL() const {return gl;} int Poll(){return ready ? DVBRIDGE_DV_IDLE : 1;}
  bool Initialize(bool){++initialized;gl=true;return true;}
  bool FenceLastUse(){++fences;return true;}
  bool Close(){++closed;gl=false;return true;}
 };
 void Cancel(){} bool RebindOutputSurface(bool){return true;}
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
 void UseDVOutputSurfaceTransaction(bool value){transaction=value;}
 bool HasPendingDVOutputSurface(){return pending;}
 bool SetVideoOutput(const VideoPicture*) {
  ++native;if(transaction){++stages;pending=formatChanges;} return baseOK;
 }
};
struct CWinSystemGbmGLESContext : CWinSystemGbmEGLContext {
 bool requested=false,m_dvStopPending=false,m_dvOrdinaryFrame=false;
 bool m_dvActivating=false,m_dvOutputRetiring=false,m_hdrConversion=false;
 bool m_dvPriorHDRConversion=false,m_dvPriorGuiCompositing=false,m_guiCompositing=false;
 bool m_cb1FramePending=false,m_dvFrame=false,m_dvNativeGui=false;
 bool m_failedHDR10SetupRestore=false,m_dvShutdownFence=false;
 bool completeOK=true,pollOK=true,restoreOK=true,modeOK=true,recoveryOK=true;
 Capabilities capabilities;
 bool m_dvRollbackFailed=false,m_dvFatalConsumed=false,m_dvNativeFailed=false,m_dvFallbackActive=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None,m_dvActivationReason=DVBRIDGE::OutputReason::None;
 std::mutex m_dvCapabilityMutex;
 unsigned m_dvAttemptFailures=0,m_hdr10SessionStream=0;
 std::optional<int> m_hdr10Session;
 struct {template<class... T> void Begin(T...){}} m_masterSafety;
 int ordinaryStages=0;
 std::optional<int> m_dvPriorConfiguredOutput,m_dvConfiguredOutput,m_hdr10Signal;
 std::optional<unsigned> m_hdrDeepColorPrevious;
 unsigned m_dvPendingStream=0,m_dvPendingPolicy=0;
 struct {void Cancel(){}} m_modeHold;
 State m_dvState;
 Selection m_dvSelection;
 std::shared_ptr<CDVBridgeGLES::Context> m_dvContext;
 std::unique_ptr<CDVBridgeGLES> m_dvBridge;
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<GBM> m_GBM=std::make_shared<GBM>();
 bool StopDVBridgePlayback(){return true;}
 bool SupportsDVOutputMode(){return modeOK;}
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
 void SetGuiCompositing(int color){m_guiCompositing=color!=0;}
 bool SetVideoOutput(const VideoPicture*);
 bool StageOrdinaryDVOutput(const VideoPicture*);
 bool RetireDVContext();
 bool PrepareDVOutputFrame(const VideoPicture&);
 bool ConfigureHDR10Conversion(const VideoPicture&){m_hdrConversion=true;return true;}
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
                ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', str(code), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

