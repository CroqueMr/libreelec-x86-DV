"""Execute the real atomic commit/retirement with rejected SDR transitions."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class SDRRestoreTests(unittest.TestCase):
    def test_retryable_native_restore_does_not_become_a_gpu_rollback_failure(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        present = body(source, 'void CWinSystemGbmGLESContext::PresentFrame(')
        ordinary = present[present.index('\n  if (m_dvOrdinaryFrame)\n'):
                           present.index('  if (m_hdrConversion)')]
        prepare = body(source, 'bool CWinSystemGbmGLESContext::PrepareDVOutputFrame(')
        guard = prepare[prepare.index('  if (m_dvRollbackFailed || !RecoverDVActivation())'):
                        prepare.index('  ResetDVActivation(&picture);')]
        program = r'''
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <map>
#include <vector>
constexpr int DVBRIDGE_DV_IDLE=0,DVBRIDGE_DV_FAILED=3,AVCOL_TRC_GAMMA22=4,AVCOL_TRC_SMPTE2084=16;
namespace DVBRIDGE {
 enum class OutputRoute{Vanilla,NativeDV,HDR10,SDR};
 enum class OutputReason{None,ProcessingPending,RestoreFailed,ActivationFailed};
 struct StreamTelemetry{
  struct Value{struct{OutputReason reason=OutputReason::None;}transaction;};
  static Value Read(){return {};}
  template<class... T>static void NativeFailure(T...){}
  static void PublishNativePending(unsigned){}static void ClearOutput(){}
 };
 struct PlaybackNotification{static void OrdinaryOutputAccepted(bool){}};
}
struct CServiceBroker{struct Cache{unsigned GetVideoProcessingGeneration(){return 1;}
 Cache& GetWindowManager(){return *this;}void MarkDirty(){}};
 static Cache* GetGUI(){return &GetDataCacheCore();}
 static Cache& GetDataCacheCore(){static Cache c;return c;}};
struct DRM{virtual ~DRM()=default;};
struct CDRMAtomic:DRM{
 bool accept=false;unsigned commits=0,failures=0;
 std::map<std::string,uint64_t> request;
 std::vector<std::map<std::string,uint64_t>> attempts;
 CDRMAtomic* GetConnector(){return this;}bool SupportsProperty(const char*){return true;}
 bool AddProperty(void*,const char* name,uint64_t value){request[name]=value;return true;}
 void AllowModeset(){}
 unsigned DVActivationFailures(){return failures;}int DVActivationError(){return EINVAL;}
 void FailDVActivation(int){++failures;}bool CanRetryDVActivation(bool){return true;}
 bool FlipPageTransactional(void*,bool){++commits;attempts.push_back(request);request.clear();return accept;}
};
struct CDVBridgeState{enum class Backend{KERNEL,NVIDIA};bool captured=true;
 bool Captured(){return captured;}
 bool Stage(CDRMAtomic&drm,bool restore){assert(restore);return drm.AddProperty(&drm,"DV",0);}
 Backend CapturedBackend(){return Backend::KERNEL;}void Restored(){captured=false;}};
struct Context{bool fence=true;int status=DVBRIDGE_DV_IDLE;
 bool FenceLastUse(){return fence;}int Poll(){return status;}};
struct Bridge{void Cancel(){}void Reset(){}bool RebindOutputSurface(bool,bool){return true;}};
struct Surface{Surface& GetDevice(){return *this;}Surface& GetSurface(){return *this;}
 void* LockTransactionalBuffer(){return this;}void CompleteTransactionalBuffer(bool){}
 void EndTransactionalMode(){}};
struct Picture{int color_transfer=16;struct{unsigned informationGeneration=1;}doviSourceInfo;};
struct Window{
 bool m_cb1RestoringPreferences=false;
 bool m_dvOrdinaryFrame=true,m_dvStopPending=false,m_dvRollbackFailed=false;
 bool m_dvActivating=false,m_dvRecoveryPending=false,m_dvSuperseded=false,m_dvRejectedSurface=false;
 bool m_dvPriorHDRConversion=false,m_dvPriorSDRConversion=false,m_dvPriorGuiCompositing=false;
 bool m_hdrConversion=false,m_sdrConversion=false,m_dvFatalConsumed=false,m_dvFallbackActive=false;
 bool m_dvNativeFailed=false,m_dvHDR10Failed=false,m_dvSDRFailed=false;
 bool pending=true,complete=true,bind=true,restore=false;unsigned restores=0;
 unsigned m_dvAttemptFailures=0,m_dvFailedStream=0,m_dvFailedPolicy=0;
 unsigned m_dvActivationStream=1,m_dvActivationPolicy=1,m_hdr10SessionStream=1;
 float m_dvPriorGuiSDRGamma=2.4f;int m_videoSourceSideData=0;
 std::mutex m_dvCapabilityMutex;
 DVBRIDGE::OutputReason m_dvActivationReason{},m_dvFatalReason{};
 DVBRIDGE::OutputRoute m_dvRejectedRoute{};
 struct{DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::Vanilla;
 DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::None;}m_dvSelection;
 std::optional<int>m_hdr10Signal,m_hdr10Session,m_hdr10BasicSignal,m_hdrDeepColorPrevious;
 std::optional<int>m_dvConfiguredOutput,m_dvPriorConfiguredOutput;
 std::optional<uint64_t>m_queuedHdrMetadata,m_queuedColorspace;
 std::shared_ptr<DRM>m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<Surface>m_GBM=std::make_shared<Surface>();
 std::unique_ptr<Context>m_dvContext=std::make_unique<Context>();
 std::unique_ptr<Bridge>m_dvBridge=std::make_unique<Bridge>();
 CDVBridgeState m_dvState;
 struct EGL{Window*w;bool TrySwapBuffers(){return true;}bool BindPriorOutputSurface(){return w->bind;}}m_eglContext{this};
 bool HasPendingDVOutputSurface(){return pending;}
 bool CompleteDVOutputSurface(bool){if(!complete)return false;pending=false;return true;}
 bool ConfigureGuiCompositing(int,float){return true;}
 bool EndDVBridge(){++restores;if(!restore)return false;m_dvState.Restored();return true;}
 void AnnounceCB1Mode(bool){}void CompleteCB1Mode(bool,bool){}
 void CompleteCB1ConnectorRestore(){}void PublishVideoSource(bool,int){}
 void SetColorimetry(const Picture*p){m_queuedColorspace=p?9:0;
  auto drm=std::dynamic_pointer_cast<CDRMAtomic>(m_DRM);drm->AddProperty(drm.get(),"Colorspace",*m_queuedColorspace);}
 bool SetHDR(const Picture*p){m_queuedHdrMetadata=p?12:0;
  auto drm=std::dynamic_pointer_cast<CDRMAtomic>(m_DRM);drm->AddProperty(drm.get(),"HDR_OUTPUT_METADATA",*m_queuedHdrMetadata);return p;}
 void SetGuiCompositing(int){}
 bool StageCB1ConnectorPreferences(bool){
  auto drm=std::dynamic_pointer_cast<CDRMAtomic>(m_DRM);
  return drm->AddProperty(drm.get(),"max bpc",12) && drm->AddProperty(drm.get(),"Broadcast RGB",3);
 }
 bool RequeueOutputProperties() @REQUEUE@
 bool PrepareOrdinaryDVOutput(const Picture* picture) @ORDINARY_PREPARE@
 bool FlipDVBridgePage(CDVBridgeState&,bool,bool,bool,void*){assert(false);return false;}
 bool RejectDVOutputSurface() @REJECT@
 bool PollRejectedDVSurface() @POLL@
 bool RecoverDVActivation() @RECOVER@
 bool Prepare(){Picture picture;auto deferred=[](const char*){return false;};@GUARD@ return true;}
 void Present(bool rendered){@ORDINARY@}
};
int main(int argc,char**argv){
 assert(argc==2);std::string scenario=argv[1];Window w;
 auto drm=std::dynamic_pointer_cast<CDRMAtomic>(w.m_DRM);
 if(scenario=="missing-drm"){
  w.m_DRM.reset();w.Present(true);
  assert(w.m_dvOrdinaryFrame && w.pending && w.m_dvState.captured && !w.Prepare());
  assert(drm->commits==0 && !w.m_dvRollbackFailed);
 }else if(scenario=="live-retry" || scenario=="stop-retry"){
  Picture picture;w.m_dvOrdinaryFrame=false;w.m_hdrDeepColorPrevious=5;
  assert(w.PrepareOrdinaryDVOutput(&picture));
  w.m_dvStopPending=scenario=="stop-retry";
  w.Present(true);w.Present(true);drm->accept=true;w.Present(true);
  assert(drm->attempts.size()==3);
  for(const auto&attempt:drm->attempts){
   assert(attempt.contains("DV") && attempt.at("DV")==0 && "Retry lost the native DV-disable intent");
   assert(attempt.at("HDR_OUTPUT_METADATA")==uint64_t(scenario=="stop-retry"?0:12));
   assert(attempt.at("Colorspace")==uint64_t(scenario=="stop-retry"?0:9));
   assert(attempt.at("DVBRIDGE_HDR10_DEEP_COLOR")==5);
   assert(attempt.at("max bpc")==12 && attempt.at("Broadcast RGB")==3);
  }
  assert(w.Prepare() && !w.m_dvOrdinaryFrame);
 }else if(scenario=="ordinary" || scenario=="stop" || scenario=="completion"){
  w.m_dvStopPending=scenario=="stop";
  w.Present(true);w.Present(true);
  assert(w.m_dvOrdinaryFrame && w.pending && w.m_dvState.captured);
  assert(!w.Prepare() && "An unaccepted native restore cannot admit a successor");
  drm->accept=true;
  if(scenario=="completion"){
   w.complete=false;w.Present(true);
   assert(w.m_dvOrdinaryFrame && w.pending && !w.Prepare());w.complete=true;
  }
  w.Present(true);
  assert(!w.m_dvOrdinaryFrame && !w.m_dvStopPending && !w.pending && !w.m_dvState.captured);
  assert(w.Prepare() && "Accepted ordinary restore poisoned later playback");
 }else if(scenario=="recovery"){
  w.m_dvOrdinaryFrame=false;w.pending=false;w.m_dvRecoveryPending=true;
  assert(!w.Prepare() && w.m_dvRecoveryPending && w.m_dvState.captured);
  w.restore=true;
  assert(w.Prepare() && !w.m_dvRecoveryPending && !w.m_dvState.captured);
  assert(w.restores==2 && "Rejected restoration must retry through its original owner");
 }else{
  w.m_dvOrdinaryFrame=false;w.m_dvActivating=true;
  if(scenario=="fence")w.m_dvContext->fence=false;
  if(scenario=="rebind")w.bind=false;
  if(scenario=="poll")w.m_dvContext->status=DVBRIDGE_DV_FAILED;
  assert(!w.RejectDVOutputSurface() && w.m_dvRollbackFailed);
  w.m_dvContext->fence=true;w.bind=true;w.m_dvContext->status=DVBRIDGE_DV_IDLE;
  w.restore=true;drm->accept=true;
  assert(!w.Prepare() && w.m_dvRollbackFailed && w.m_dvRejectedSurface);
  assert(w.restores==0 && "A genuine failed GPU retirement must remain blocked");
 }
}
'''
        for token, signature in (
                ('@REJECT@', 'bool CWinSystemGbmGLESContext::RejectDVOutputSurface()'),
                ('@POLL@', 'bool CWinSystemGbmGLESContext::PollRejectedDVSurface()'),
                ('@RECOVER@', 'bool CWinSystemGbmGLESContext::RecoverDVActivation()')):
            program = program.replace(token, body(source, signature))
        program = program.replace('@GUARD@', guard).replace('@ORDINARY@', ordinary)
        program = program.replace('@ORDINARY_PREPARE@', body(
            source, 'bool CWinSystemGbmGLESContext::PrepareOrdinaryDVOutput('))
        program = program.replace('@REQUEUE@', body(
            (TREE/'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text(),
            'bool CWinSystemGbm::RequeueOutputProperties()'))
        with tempfile.TemporaryDirectory(prefix='native-restore-reentry-') as temporary:
            root = Path(temporary)
            code, binary = root / 'check.cpp', root / 'check'
            code.write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    '-fsanitize=address,undefined', str(code), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            for scenario in ('ordinary', 'stop', 'completion', 'recovery', 'fence', 'rebind', 'poll',
                             'live-retry', 'stop-retry', 'missing-drm'):
                with self.subTest(scenario=scenario):
                    run = subprocess.run([str(binary), scenario], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_stop_successor_survives_resize_rejection_and_idle_gui_retries(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        present = body(source, 'void CWinSystemGbmGLESContext::PresentFrame(')
        wake = present[1:present.index('#ifdef HAVE_DVBRIDGE')]
        ordinary = present[present.index('\n  if (m_dvOrdinaryFrame)\n'):
                           present.index('  if (m_hdrConversion)')]
        stage = body(source, 'bool CWinSystemGbmGLESContext::PrepareOrdinaryDVOutput(')
        stop = body(source, 'bool CWinSystemGbmGLESContext::StopDVBridgePlayback()')
        destroy = body(source, 'bool CWinSystemGbmGLESContext::DestroyWindow()')
        retry = 'if (m_dvStopPending && !m_dvOrdinaryFrame)' + body(
            present, 'if (m_dvStopPending && !m_dvOrdinaryFrame)')
        program = r'''
#include <cassert>
#include <memory>
#include <optional>
#include <cstdint>
#include <mutex>
struct CModeChangeHold {enum class Kind{NONE,STOP};Kind Holding(){return Kind::NONE;}
 bool Commits(uint64_t){return true;}void Cancel(){}};
struct VideoPicture{int color_transfer=16;};
struct Services {unsigned dirty=0;Services& GetWindowManager(){return *this;}
 void MarkDirty(){++dirty;}};
struct CServiceBroker {static Services* GetGUI(){static Services value;return &value;}};
namespace DVBRIDGE {
 uint64_t DiagnosticNowMs(){return 0;}
 enum class OutputReason {None,ProcessingPending};
 struct PlaybackNotification{
  static inline unsigned accepted=0;
  static void OrdinaryOutputAccepted(bool ok){accepted+=ok;}
 };
 struct StreamTelemetry{static void ClearOutput(){}};
}
struct DRM{virtual ~DRM()=default;};
struct CDRMAtomic:DRM{
 bool pending=true,stageOK=true;int reject=0,commits=0;
 bool IsSDRRestorePending(){return pending;}
 void SetCB1TimingPeriod(uint64_t){}
 void* GetConnector(){return this;}
 bool AddProperty(void*,const char*,uint64_t){return true;}
 bool FlipPageTransactional(void*,bool){++commits;if(reject){--reject;return false;}pending=false;return true;}
};
struct CDVBridgeState{enum class Backend{KERNEL,NVIDIA};
 unsigned stages=0;bool captured=true;Backend CapturedBackend(){return Backend::KERNEL;}
 bool Captured(){return captured;}bool Stage(CDRMAtomic& drm,bool){++stages;return drm.stageOK;}
 void Restored(){captured=false;}};
struct Surface{
 Surface& GetDevice(){return *this;}Surface& GetSurface(){return *this;}
 void* LockTransactionalBuffer(){return this;}void CompleteTransactionalBuffer(bool){}
 void EndTransactionalMode(){}
};
struct CWinSystemGbmEGLContext{
 bool destroyOK=true;bool DestroyWindow(){return destroyOK;}
};
struct CWinSystemGbmGLESContext:CWinSystemGbmEGLContext{
 struct {DVBRIDGE::OutputReason reason=DVBRIDGE::OutputReason::None;}m_dvSelection;
 bool m_cb1RestoringPreferences=false;
 bool m_dvOrdinaryFrame=true,m_dvStopPending=true,rollback=false;
 unsigned rejects=0,gui=0,swaps=0;
 unsigned colorClears=0,hdrClears=0;
 std::mutex m_dvCapabilityMutex;int m_masterSafety=0;
 unsigned m_masterFramePeriodNs=0,m_previousSourceStream=0,m_previousSourcePts=0;
 bool m_continuousFrameEligible=false;CModeChangeHold m_modeHold;
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<Surface> m_GBM=std::make_shared<Surface>();
 struct EGL{unsigned* count;bool TrySwapBuffers(){++*count;return true;}}m_eglContext{&swaps};
 CDVBridgeState m_dvState;
 std::optional<uint64_t> m_hdrDeepColorPrevious;
 std::optional<int> m_hdr10Session,m_hdr10BasicSignal,m_hdr10Signal;
 unsigned m_hdr10SessionStream=1;int m_videoSourceSideData=0;
 struct Bridge{void Reset(){}};std::unique_ptr<Bridge> m_dvBridge;
 void AnnounceCB1Mode(bool){}void CompleteCB1Mode(bool,bool){}
 bool surfacePending=false,surfaceOK=true,endOK=true,retireOK=true;
 unsigned outputRefused=0;
 bool CompleteDVOutputSurface(bool){if(!surfaceOK)return false;surfacePending=false;return true;}
 void PublishVideoSource(bool,int){}
 bool FlipDVBridgePage(CDVBridgeState&,bool,bool,bool,void*){return false;}
 void SetColorimetry(const VideoPicture* picture){if(!picture)++colorClears;}
 bool SetHDR(const VideoPicture* picture){if(!picture){++hdrClears;
   std::dynamic_pointer_cast<CDRMAtomic>(m_DRM)->pending=true;}return picture!=nullptr;}
 void SetGuiCompositing(int value){gui=value;}
 bool RejectDVOutputSurface(){++rejects;return false;}
 bool RequeueOutputProperties(){return true;}
 bool StageCB1ConnectorPreferences(bool){return true;}
 void CompleteCB1ConnectorRestore(){}
 bool PrepareOrdinaryDVOutput(const VideoPicture* picture) STAGE
 bool HoldCB1Stop(){return false;}bool HasPendingDVOutputSurface(){return surfacePending;}
 bool SetVideoOutput(const VideoPicture*){if(outputRefused){--outputRefused;return false;}m_dvState.captured=false;return true;}
 bool StopDVBridgePlayback() @STOP_BODY@
 // GPU/EGL retirement does not itself perform the native SDR request.
 bool EndDVBridge(){if(!endOK)return false;m_dvState.Restored();return true;}
 bool RetireDVContext(){return retireOK;}
 void ObserveDVImport(int,int,bool){}
 bool DestroyWindow() @DESTROY_BODY@
 void Present(bool rendered){WAKE @RETRY_BODY@ ORDINARY}
};
int main(){
 CWinSystemGbmGLESContext window;
 auto drm=std::dynamic_pointer_cast<CDRMAtomic>(window.m_DRM);
 window.Present(false);assert(CServiceBroker::GetGUI()->dirty==1 && !window.swaps);
 drm->reject=2;
 for(int i=0;i<2;++i){window.Present(true);
  assert(window.m_dvOrdinaryFrame && window.m_dvStopPending && !window.rollback && !window.rejects);
 }
 window.Present(true);
 assert(!window.m_dvOrdinaryFrame && !window.m_dvStopPending && !drm->pending && drm->commits==3);
 assert(window.m_dvState.stages==3);
 assert(DVBRIDGE::PlaybackNotification::accepted==1);
 // A temporary ordinary frame must restore normally without reporting a fallback
 // while the selected processing route is still being probed.
 CWinSystemGbmGLESContext probing;
 probing.m_dvSelection.reason=DVBRIDGE::OutputReason::ProcessingPending;
 probing.Present(true);
 assert(!probing.m_dvOrdinaryFrame && !probing.m_dvStopPending);
 assert(DVBRIDGE::PlaybackNotification::accepted==1);
 const auto dirty=CServiceBroker::GetGUI()->dirty;window.Present(false);
 assert(CServiceBroker::GetGUI()->dirty==dirty);
 CWinSystemGbmGLESContext staged;
 auto stagedDRM=std::dynamic_pointer_cast<CDRMAtomic>(staged.m_DRM);stagedDRM->stageOK=false;
 staged.Present(true);
 assert(staged.m_dvOrdinaryFrame && staged.m_dvStopPending && !staged.rollback);
 stagedDRM->stageOK=true;staged.Present(true);
 assert(!staged.m_dvStopPending && !staged.rollback);
 CWinSystemGbmGLESContext transition;transition.m_dvStopPending=false;
 auto td=std::dynamic_pointer_cast<CDRMAtomic>(transition.m_DRM);td->reject=1;
 transition.Present(true);assert(transition.rejects==1 && !transition.rollback);
 CWinSystemGbmGLESContext recovered;
 recovered.m_dvStopPending=recovered.m_dvOrdinaryFrame=false;recovered.gui=16;
 auto rd=std::dynamic_pointer_cast<CDRMAtomic>(recovered.m_DRM);rd->pending=false;
 assert(recovered.StopDVBridgePlayback());
 assert(!recovered.m_dvState.Captured() && !recovered.m_dvStopPending);
 assert(rd->pending && recovered.gui==0 && recovered.colorClears==1 && recovered.hdrClears==1);

 // A delayed stop survives replacement of the drawable before its next GUI frame.
 CWinSystemGbmGLESContext resized;
 resized.m_dvOrdinaryFrame=resized.m_dvStopPending=false;
 auto resizedDRM=std::dynamic_pointer_cast<CDRMAtomic>(resized.m_DRM);
 resizedDRM->pending=false;resized.outputRefused=1;
 assert(!resized.StopDVBridgePlayback() && resized.m_dvStopPending);
 assert(resized.DestroyWindow());
 assert(resized.m_dvStopPending && "Window recreation discarded an unfinished SDR stop");
 resized.Present(false);
 assert(!resized.m_dvStopPending && resized.hdrClears==1 && resized.colorClears==1);
 assert(resizedDRM->pending);
 const auto beforeWake=CServiceBroker::GetGUI()->dirty;resized.Present(false);
 assert(CServiceBroker::GetGUI()->dirty==beforeWake+1);

 // Cancelling a staged successor on resize also retains the original stop.
 CWinSystemGbmGLESContext successor;
 successor.surfacePending=true;successor.surfaceOK=false;
 assert(!successor.DestroyWindow() && successor.m_dvStopPending);
 successor.surfaceOK=true;assert(successor.DestroyWindow());
 assert(!successor.m_dvOrdinaryFrame && successor.m_dvStopPending);
 successor.Present(false);
 assert(successor.hdrClears==1 && successor.colorClears==1 && !successor.m_dvStopPending);

 // Failed teardown is retryable; successful active-video resize is not a stop.
 for(int failure=0;failure<3;++failure){
  CWinSystemGbmGLESContext failed;
  failed.m_dvOrdinaryFrame=false;
  if(failure==0)failed.endOK=false;
  if(failure==1)failed.retireOK=false;
  if(failure==2)failed.destroyOK=false;
  assert(!failed.DestroyWindow() && failed.m_dvStopPending);
  failed.endOK=failed.retireOK=failed.destroyOK=true;
  assert(failed.DestroyWindow() && failed.m_dvStopPending);
  failed.Present(false);assert(failed.hdrClears==1 && !failed.m_dvStopPending);
 }
 CWinSystemGbmGLESContext activeResize;
 activeResize.m_dvOrdinaryFrame=activeResize.m_dvStopPending=false;
 std::dynamic_pointer_cast<CDRMAtomic>(activeResize.m_DRM)->pending=false;
 assert(activeResize.DestroyWindow() && !activeResize.m_dvStopPending);
 activeResize.Present(false);assert(!activeResize.hdrClears && !activeResize.colorClears);
}
'''.replace('STAGE', stage).replace('WAKE', wake).replace('ORDINARY', ordinary).replace('@STOP_BODY@', stop).replace('@DESTROY_BODY@', destroy).replace('@RETRY_BODY@', retry)
        with tempfile.TemporaryDirectory(prefix='sdr-stop-') as temporary:
            root = Path(temporary)
            code, binary = root / 'check.cpp', root / 'check'
            code.write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(code), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_rejected_restore_is_retried_and_new_hdr_supersedes_it(self):
        source = (TREE / 'xbmc/windowing/gbm/drm/DRMAtomic.cpp').read_text()
        header = (TREE / 'xbmc/windowing/gbm/drm/DRMAtomic.h').read_text()
        methods = ''
        for signature in ('bool CDRMAtomic::DrmAtomicCommit(',
                          'void CDRMAtomic::FinishRequest(',
                          'int CDRMAtomic::TestAtomicFrame('):
            start = source.index(signature)
            methods += source[start:source.index('{', start)] + body(source, signature) + '\n'
        prepare = ('{return true;}' if 'bool CDRMAtomic::PrepareSDRRestore(' not in source
                   else body(source, 'bool CDRMAtomic::PrepareSDRRestore('))
        pending = ('{}' if 'void SetSDRRestorePending(' not in header
                   else body(header, 'void SetSDRRestorePending('))
        add = body(source, 'bool CDRMAtomic::AddProperty(')
        program = r'''
#include <cassert>
#include <cerrno>
#include <cstring>
#include <cstdint>
#include <deque>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>
#include <unistd.h>
#include <xf86drmMode.h>
constexpr int LOGERROR=1,LOGINFO=2,LOGWARNING=3,LOGWINDOWING=4,QUIRK_NEEDSPRIMARY=8;
struct CLog {
 static inline unsigned nativeErrors=0;
 template<class... T>static void Log(T...){}
 template<class... T>static void LogF(int,const char* message,T...){
  if(std::strstr(message,"atomic commit failed"))++nativeErrors;
 }
};
namespace DVBRIDGE {
 bool DiagnosticsEnabled(){return false;}
 template<class... T>void DiagnosticLog(T...){}
}
uint64_t DVNowMs(){return 1;} uint64_t DVNowNs(){return 1;}
void CollectDVKernelLog(){}
struct CApplicationPlayer {bool HasVisibleOverlay(){return false;}};
struct Services {
 Services& GetWindowManager(){return *this;} bool HasVisibleControls(){return false;}
 bool CanLogComponent(int){return false;}
 template<class T>T* GetComponent(){static T value;return &value;}
};
struct CServiceBroker {
 static Services* GetGUI(){static Services value;return &value;}
 static Services& GetLogging(){return *GetGUI();}
 static Services& GetAppComponents(){return *GetGUI();}
};
struct Object {
 int id=1; bool metadata=true; std::map<std::string,uint64_t> cache;
 int GetId()const{return id;} int GetCrtcId()const{return id;}
 bool SupportsProperty(const char* name)const{return std::string(name)!="HDR_OUTPUT_METADATA" || metadata;}
 std::optional<uint64_t> GetPropertyValue(const char* name)const{
  auto it=cache.find(name);return it==cache.end()?std::optional<uint64_t>{}:it->second;
 }
 std::optional<uint64_t> GetPropertyEnumValue(const char*,const char* name)const{
  assert(std::string(name)=="Default");return 0;
 }
};
using CDRMCrtc=Object;using CDRMPlane=Object;using CDRMObject=Object;
bool rejectProperty=false;
struct CDRMPropertyBlob {
 unsigned id=0;CDRMPropertyBlob()=default;
 CDRMPropertyBlob(int,const void*,size_t):id(100){}
 bool IsValid()const{return id!=0;} unsigned Get()const{return id;}
};
struct Request {
 std::map<Object*,std::map<std::string,uint64_t>> values;
 std::optional<drmModeModeInfo> signalMode;std::optional<bool> hdr10plus;
 std::optional<uint64_t> requestedDV;bool sdrRestore=false;
 Request* Get(){return this;}
 bool AddProperty(Object* object,const char* name,uint64_t value){
  if(rejectProperty && std::string(name)=="HDR_OUTPUT_METADATA")return false;
  values[object][name]=value;return true;
 }
 void CacheProperties(){for(auto& [object,props]:values)for(auto& [key,value]:props)object->cache[key]=value;}
 void LogAtomicRequest(){} static void LogAtomicDiff(Request*,Request*){}
};
bool rejectTest=false,rejectCommit=false;unsigned realCommits=0;
std::map<std::string,uint64_t> signal;
int drmModeAtomicCommit(int,Request* request,int flags,void*){
 if((flags&DRM_MODE_ATOMIC_TEST_ONLY)?rejectTest:rejectCommit){errno=EBUSY;return -1;}
 if(!(flags&DRM_MODE_ATOMIC_TEST_ONLY)){
  ++realCommits;
  for(auto& [object,props]:request->values)for(auto& [key,value]:props)signal[key]=value;
 }
 return 0;
}
struct CDRMAtomic {
 using CDRMAtomicRequest=Request;
 Object connector,crtc,plane;
 Object* m_connector=&connector;Object* m_crtc=&crtc;Object* m_old_crtc=nullptr;
 Object* m_gui_plane=&plane;Object* m_video_plane=nullptr;
 std::vector<std::unique_ptr<Object>> m_planes;
 drmModeModeInfo mode{},m_committedMode{};drmModeModeInfo* m_mode=&mode;
 unsigned m_width=3840,m_height=2160;int m_fd=1,m_inFenceFd=-1,m_outFenceFd=-1;
 bool m_dvRestoring=false,m_dvActivating=false,m_active=true,m_propertyFailure=false;
 bool m_dvCommitReported=false,m_dvLastCommitRestore=false,m_signalDirty=false,m_hdr10plusActive=false;
 bool m_sdrRestorePending=false,m_sdrRestoreFailed=false;
 bool m_commitFellBack=false,m_colorRangeTransition=false;
 std::optional<uint64_t> m_sdrRestoreColorspace;
 int m_cb1TimingInput=-1;uint64_t m_cb1SubmittedNs=0;
 struct Failures {
  void Failed(int){} template<class... T>bool Record(T...){return false;}
  bool Recovered(uint64_t){return false;}unsigned Count(){return 0;}unsigned Recoveries(){return 0;}
 }m_dvRetry,m_dvFailures;
 std::deque<std::unique_ptr<Request>> m_atomicRequestQueue;Request* m_req=nullptr;
 CDRMAtomic(){m_atomicRequestQueue.emplace_back(std::make_unique<Request>());m_req=m_atomicRequestQueue.back().get();}
 bool AddProperty(Object* object,const char* name,uint64_t value) @ADD_BODY@
 bool HasQuirk(int)const{return false;}const drmModeModeInfo* GetDVTransportMode(){return m_mode;}
 void ReportDVFailure(const char*,int){}void ReportDVCommit(const char*){}void ReportSignalState(){}
 bool PrepareHDR10Plus(int&,bool& bound){bound=false;return true;}
 bool RemoveRejectedHDR10Plus(int&){return false;}
 void AcceptHDR10Plus(bool){assert(false);}
 void SetSDRRestorePending(bool pending) PENDING
 bool PrepareSDRRestore(int& flags) PREPARE
 bool DrmAtomicCommit(int,int,bool,bool,bool=false);
 int TestAtomicFrame(int&,bool);void FinishRequest(bool);
};
METHODS
int main(int argc,char** argv){
 assert(argc==2);int scenario=std::stoi(argv[1]);
 CDRMAtomic drm;
 // An accepted HDR movie is the independent physical starting state.
 drm.AddProperty(drm.m_connector,"HDR_OUTPUT_METADATA",17);
 drm.AddProperty(drm.m_connector,"Colorspace",9);
 drm.AddProperty(drm.m_connector,"DVBRIDGE_HDR10_DEEP_COLOR",1);
 assert(drm.DrmAtomicCommit(42,0,true,false));
 assert(signal["HDR_OUTPUT_METADATA"]==17);
 const auto movie=signal;
 drm.SetSDRRestorePending(true);
 drm.AddProperty(drm.m_connector,"HDR_OUTPUT_METADATA",0);
 drm.AddProperty(drm.m_connector,"Colorspace",0);
 if(scenario==0)rejectTest=true;
 if(scenario==1)rejectCommit=true;
 if(scenario==2)rejectProperty=true;
 if(scenario<=2){
  assert(!drm.DrmAtomicCommit(42,0,true,false) && "A refused SDR transition must not reuse the HDR request");
  assert(signal==movie && drm.m_sdrRestorePending);
  rejectTest=rejectCommit=rejectProperty=false;
  // No new SetHDR/stop call: the next native presentation must retry by itself.
  assert(drm.DrmAtomicCommit(42,0,true,false));
  assert(signal["HDR_OUTPUT_METADATA"]==0 && signal["Colorspace"]==0);
  assert(signal["DVBRIDGE_HDR10_DEEP_COLOR"]==0);
  assert(!drm.m_sdrRestorePending);
 }else if(scenario==3){
  rejectCommit=true;assert(!drm.DrmAtomicCommit(42,0,true,false));rejectCommit=false;
  // A newly admitted movie overrides the previous stop's SDR intent and properties.
  drm.SetSDRRestorePending(false);
  drm.AddProperty(drm.m_connector,"HDR_OUTPUT_METADATA",29);
  drm.AddProperty(drm.m_connector,"Colorspace",9);
  assert(drm.DrmAtomicCommit(42,0,true,false));
  assert(signal["HDR_OUTPUT_METADATA"]==29 && signal["Colorspace"]==9);
 }else if(scenario==4){
  // Repeated stop, then an idle GUI commit with no new framebuffer.
  drm.SetSDRRestorePending(true);
  assert(drm.DrmAtomicCommit(0,0,false,false));
  assert(signal["HDR_OUTPUT_METADATA"]==0 && !drm.m_sdrRestorePending);
  drm.SetSDRRestorePending(true);assert(drm.DrmAtomicCommit(0,0,false,false));
  assert(signal["HDR_OUTPUT_METADATA"]==0 && !drm.m_sdrRestorePending);
 }else if(scenario==5){
  for(int i=0;i<3;++i){rejectTest=true;assert(!drm.DrmAtomicCommit(42,0,true,false));}
  assert(drm.m_sdrRestorePending && signal==movie);
  rejectTest=false;assert(drm.DrmAtomicCommit(42,0,true,false));
  assert(!drm.m_sdrRestorePending && signal["HDR_OUTPUT_METADATA"]==0);
 }else if(scenario==6){
  for(unsigned i=0;i<64;++i){
   drm.SetSDRRestorePending(false);
   drm.AddProperty(drm.m_connector,"HDR_OUTPUT_METADATA",100+i);
   drm.AddProperty(drm.m_connector,"Colorspace",9);
   assert(drm.DrmAtomicCommit(42,0,true,false));
   assert(signal["HDR_OUTPUT_METADATA"]==100+i && signal["Colorspace"]==9);
   drm.SetSDRRestorePending(true);
   rejectTest=(i%2)==0;rejectCommit=!rejectTest;
   assert(!drm.DrmAtomicCommit(42,0,true,false) && drm.m_sdrRestorePending);
   assert(signal["HDR_OUTPUT_METADATA"]==100+i);
   rejectTest=rejectCommit=false;
   assert(drm.DrmAtomicCommit(42,0,true,false));
   assert(!drm.m_sdrRestorePending && signal["HDR_OUTPUT_METADATA"]==0);
  }
 }else if(scenario==7){
  // New HDR before the queued stop has had any commit attempt.
  drm.SetSDRRestorePending(false);
  drm.AddProperty(drm.m_connector,"HDR_OUTPUT_METADATA",29);
  drm.AddProperty(drm.m_connector,"Colorspace",9);
  assert(drm.DrmAtomicCommit(42,0,true,false));
  assert(signal["HDR_OUTPUT_METADATA"]==29 && signal["Colorspace"]==9);
 }else if(scenario==8){
  rejectCommit=true;assert(!drm.DrmAtomicCommit(42,0,true,false));
  // The successor is SDR transfer with BT.2020 primaries, not an SDR GUI.
  drm.AddProperty(drm.m_connector,"Colorspace",9);
  assert(!drm.DrmAtomicCommit(42,0,true,false));
  rejectCommit=false;
  assert(drm.DrmAtomicCommit(42,0,true,false));
  assert(signal["HDR_OUTPUT_METADATA"]==0 && signal["Colorspace"]==9);
 }else if(scenario==9){
  rejectCommit=true;
  for(int i=0;i<3;++i)assert(!drm.DrmAtomicCommit(42,0,true,false));
  assert(CLog::nativeErrors==0 && "SDR retries use the single pending warning, not a per-frame native error");
  rejectCommit=false;assert(drm.DrmAtomicCommit(42,0,true,false));
  assert(signal["HDR_OUTPUT_METADATA"]==0);
 }
}
'''.replace('PENDING', pending).replace('PREPARE', prepare).replace('METHODS', methods).replace('@ADD_BODY@', add)
        with tempfile.TemporaryDirectory(prefix='sdr-restore-') as temporary:
            root = Path(temporary)
            code, binary = root / 'check.cpp', root / 'check'
            code.write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-I/usr/include/libdrm',
                                    '-fsanitize=address,undefined', str(code), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            for scenario in range(10):
                with self.subTest(scenario=scenario):
                    run = subprocess.run([str(binary), str(scenario)], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
