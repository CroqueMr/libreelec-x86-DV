"""Actual output/surface/renderer owners reject superseded targets without false failure.

External device ABIs are deterministic adapters, not GPU/DRM/receiver proof.
The initial accepted boundary calls the real surface completion owner. Real
Master-overlay and renderer-retirement guards defer the unpresented successor.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body

ROOT=Path(__file__).resolve().parents[2]
class OutputSupersessionTests(unittest.TestCase):
 def test_pending_target_rekeys_and_rolls_back_through_existing_owners(self):
  window=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(encoding='utf-8')
  egl=(TREE/'xbmc/windowing/gbm/WinSystemGbmEGLContext.cpp').read_text(encoding='utf-8')
  render=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text(encoding='utf-8')
  utils=(TREE/'xbmc/utils/EGLUtils.cpp').read_text(encoding='utf-8')
  settings=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text(encoding='utf-8')
  settings=settings[:settings.index('inline std::mutex& OutputSettingsMutex()')]
  settings='\n'.join(line for line in settings.splitlines() if not line.startswith(('#include','#pragma')))+'\n}\n'
  selector=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSelection.h').read_text(encoding='utf-8')
  selector='\n'.join(line for line in selector.splitlines() if not line.startswith(('#include','#pragma')))
  status_header=(ROOT/'CB1/src/dvbridge_render.h').read_text(encoding='utf-8')
  status_start=status_header.index('enum dvbridge_dv_policy_status {')
  status_enum=status_header[status_start:status_header.index('};',status_start)+2]
  program=r'''
#include <memory>
#include <cassert>
#include <array>
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <algorithm>
#include <map>
#include <vector>
#include <utility>
#include <cerrno>
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <optional>
#include <string>
#include <iostream>
#include <mutex>
#include "windowing/gbm/ModeChangeHold.h"
using KODI::WINDOWING::GBM::CHeldModeAnnouncement;
ACTUAL_RETIREMENT_STATUS
constexpr int LOGWARNING=1,LOGERROR=2,LOGINFO=3,AVCOL_TRC_GAMMA22=4,AVCOL_TRC_SMPTE2084=16,AVCOL_PRI_BT2020=9,AVCOL_SPC_BT2020_NCL=9,EGL_OPENGL_ES3_BIT=64;
struct Services {Services& GetWindowManager(){return *this;}void MarkDirty(){}};
struct Cache{unsigned GetVideoProcessingGeneration(){return 1;}};struct CServiceBroker {static Cache&GetDataCacheCore(){static Cache cache;return cache;}static Services* GetGUI(){static Services value;return &value;}};
enum class StreamHdrType {HDR_TYPE_NONE,HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG,HDR_TYPE_DOLBYVISION};
struct Binding {uint64_t stream=0,picture=0,revision=0; bool Valid() const {return stream!=0;} bool operator==(const Binding&)const=default;};
struct VideoPicture {
 Binding doviSourceBinding; struct {::Binding value;::Binding Binding() const {return value;} const void* Data()const{return this;} size_t Size()const{return 1;}} doviMetadata;
 struct {int profile=0,compatibility=0;bool el=false;unsigned informationGeneration=0;} doviSourceInfo;
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_NONE; std::string strDVELType;
 bool doviEnhancement=false; int color_transfer=0,color_primaries=0,color_space=0,colorBits=10;double pts=0;
 bool hasDisplayMetadata=false,hasLightMetadata=false;
 struct {bool has_luminance=false;std::pair<int,int> max_luminance{},min_luminance{};}displayMetadata;
 struct {unsigned MaxCLL{},MaxFALL{};}lightMetadata;
 void SetParams(const VideoPicture& other){*this=other;}
};
__ACTUAL_BODY_0_END____ACTUAL_BODY_1_END__
namespace DVBRIDGE {
 OutputPreferences current;
 OutputPreferences FrameOutputSettings(bool=false,bool=false){return current;}
 inline std::string lastStage,lastFailure;
 bool DiagnosticsEnabled(){return true;}
 void DiagnosticStage(const char* value){lastStage=value;}
 inline uint64_t DiagnosticNowMs(){return 1;}
 template<class...T>void ObserveDiagnostic(T...){}
 template<class...T>bool DiagnosticLog(T...){return true;}
 template<class...T>void DiagnosticFailureLog(const char*,int,int,const char*,const char*,const char* detail,T...){lastFailure=detail;}
 void DiagnosticReserveProgress(){}
 using SourceBinding=::Binding;
 struct StreamTelemetry {
  struct Snapshot {struct {OutputReason reason=OutputReason::None;}transaction;};
  static Snapshot Read(){return {};}
  template<class...T>static void NativeFailure(T...){}
  template<class...T>static void PublishNativePending(T...){}
  template<class...T>static void NativeSelection(T...){}
 };
}
using Capabilities=DVBRIDGE::OutputCapabilities;
using Selection=DVBRIDGE::OutputSelection;
struct dvbridge_hdr10_session {struct {unsigned max_luminance=1000,min_luminance=50,max_cll=1000,max_fall=400;bool level6=true;}output;struct {struct {float max_luma=1000;}hdr;}target;};
bool dvbridge_hdr10_session_init(dvbridge_hdr10_session*,const void*,size_t){return true;}
struct CModeChangeHold{enum class Kind{START,STOP};};
struct CDVWindowRetirement {static void PollOnce(){}};

struct dvbridge_geometry{int source_width=3840,source_height=2160,x=0,y=0,width=3840,height=2160,target_width=3840,target_height=2160;bool ignore_l5=false;int crop[4]{},placement[4]{};};
template<class...T>void dvbridge_renderer_set_l2_trims_disabled(T...){}
template<class...T>void dvbridge_renderer_set_cmv40(T...){}
template<class...T>bool dvbridge_render_dv_policy_update_overlay(T...){return true;}
template<class...T>int dvbridge_render_dv_policy_advance(T...){return DVBRIDGE_DV_IDLE;}
template<class...T>int dvbridge_render_dv_policy_poll(T...){return DVBRIDGE_DV_IDLE;}
namespace DVBRIDGE{uint64_t NextRevisionAfter(uint64_t n){return n+1;}}
// Deterministic external device ABI. The transaction methods inserted below
// this adapter are copied verbatim from Kodi. No GPU/DRM success is claimed.
constexpr int GL_SCISSOR_TEST=20,GL_TRUE=1,GL_COLOR_BUFFER_BIT=21;void glDisable(int){}void glColorMask(int,int,int,int){}void glClearColor(int,int,int,int){}void glClear(int){}void glFinish(){}
using EGLSurface=int;using EGLConfig=int;using EGLDisplay=int;using EGLNativeWindowType=uintptr_t;
using khronos_uintptr_t=uintptr_t;using GLint=int;using EGLint=int;
constexpr int EGL_NO_SURFACE=0,EGL_NO_DISPLAY=0,EGL_NO_CONTEXT=0,EGL_TRUE=1,EGL_DRAW=1,
 EGL_WIDTH=2,EGL_HEIGHT=3,EGL_NATIVE_VISUAL_ID=4,EGL_RED_SIZE=5;
constexpr int GL_DRAW_FRAMEBUFFER_BINDING=1,GL_READ_FRAMEBUFFER_BINDING=2,GL_FRAMEBUFFER=3,
 GL_RED_BITS=4,GL_GREEN_BITS=5,GL_BLUE_BITS=6,GL_SAMPLES=7,GL_BACK=8,
 GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING=9,GL_LINEAR=10,GL_FRAMEBUFFER_COMPLETE=11,
 GL_DRAW_FRAMEBUFFER=12,GL_READ_FRAMEBUFFER=13,GL_COLOR_ATTACHMENT0=14,DRM_FORMAT_MOD_LINEAR=0;
namespace KODI::WINDOWING::GBM{constexpr int QUIRK_NEEDSPRIMARY=1;}
inline std::map<int,int>surfaces{{1,24}};inline int currentSurface=1,nextSurface=2;
inline bool failRestore=false;
int eglGetCurrentDisplay(){return 1;}int eglGetCurrentSurface(int){return currentSurface;}
int eglQuerySurface(int,int,int attr,int*value){*value=attr==EGL_WIDTH?3840:2160;return EGL_TRUE;}
int eglMakeCurrent(int,int draw,int,int){if(failRestore)return 0;currentSurface=draw;return EGL_TRUE;}
int eglDestroySurface(int,int value){surfaces.erase(value);return EGL_TRUE;}
void glGetIntegerv(int attr,int*value){*value=(attr==GL_RED_BITS||attr==GL_GREEN_BITS||attr==GL_BLUE_BITS)?(surfaces[currentSurface]==30?10:8):0;}
void glBindFramebuffer(int,int){}void glGetFramebufferAttachmentParameteriv(int,int,int,int*v){*v=GL_LINEAR;}
int glCheckFramebufferStatus(int){return GL_FRAMEBUFFER_COMPLETE;}
struct pl_opengl_t{int gpu=1;};using pl_opengl=pl_opengl_t*;inline pl_opengl_t fakeGL;
struct pl_opengl_wrap_params{int width{},height{},framebuffer{};};using pl_tex=int*;
using pl_renderer=void*;using pl_log=void*;
inline int texture=1,packer=1,rendererToken=1;
pl_tex pl_opengl_wrap(int,const pl_opengl_wrap_params*){return &texture;}
void pl_tex_destroy(int,pl_tex*p){*p=nullptr;}bool pl_opengl_has_ext(pl_opengl,const char*){return true;}
void*dvbridge_gl_packer_create(const char*,const char*){return &packer;}
constexpr char DVBRIDGE_VERTEX[]="",DVBRIDGE_FRAGMENT[]="";
struct CLog{template<class...T>static void LogF(T...){}};
struct gbm_bo{unsigned format=24;};unsigned gbm_bo_get_format(gbm_bo*b){return b->format;}
struct Plane{unsigned format=24;uint64_t modifier=0;unsigned GetFormat(){return format;}uint64_t GetModifier(){return modifier;}void SetFormat(unsigned x){format=x;}void SetModifier(uint64_t x){modifier=x;}};
struct CEGLContextUtils{
 bool m_outputSurfaceTransaction=false;EGLSurface m_eglSurface=1,m_priorSurface=0;
 EGLConfig m_eglConfig=24,m_priorConfig=0,m_eglHDRConfig=0,m_priorHDRConfig=0;
 int m_eglDisplay=1,m_eglContext=1;
 bool BeginOutputSurface();bool StageOutputSurface(void*,EGLNativeWindowType);
 bool BindPriorOutputSurface();bool CompleteOutputSurface(bool);
 unsigned GetConfigAttrib(int attr){return attr==EGL_RED_SIZE?(m_eglConfig==30?10:8):m_eglConfig;}
 bool CreatePlatformSurface(void*,uintptr_t){m_eglSurface=nextSurface++;surfaces[m_eglSurface]=m_eglConfig;return true;}
 void DestroySurface(){}bool BindContext(){currentSurface=m_eglSurface;return true;}bool TrySwapBuffers(){return true;}
};
struct CDVBridgeGLES {
 explicit CDVBridgeGLES(bool playerLed=false):m_playerLed(playerLed){}
 bool m_playerLed{};
 struct CpuQueue {
  Binding source;
  uint64_t generation{}, revision{};
  bool Backpressured() const {return false;}
 };
 std::unique_ptr<CpuQueue> m_playerLedCpu;
 void* m_playerLedCpuDevice{};
 bool PlayerLed() const{return m_playerLed;}
 struct Context {
  static bool NewContextBlocked(){return false;}
  bool gl=true,ready=true,fenceOK=true,pollFailed=false; int initialized=0,closed=0,fences=0;
  bool Quarantined()const{return false;}bool AsyncPreparation(unsigned)const{return true;}
  pl_opengl GL() const {return gl?&fakeGL:nullptr;}pl_log Log(){return nullptr;}pl_renderer Attach(){return &rendererToken;} int Poll(bool=false){return pollFailed?DVBRIDGE_DV_FAILED:ready ? DVBRIDGE_DV_IDLE : DVBRIDGE_DV_BUSY;}void SourceReadComplete(){}
  bool Initialize(bool){++initialized;gl=true;return true;}
  bool FenceLastUse(){++fences;return fenceOK;}
  bool Close(){++closed;gl=false;return true;}
 };
 enum class FrameStatus {Ready,Pending,Busy,Failed,Reused,Unsupported};
 struct Layer {Binding binding;double pts=0;bool lease=true;int scalingMethod=0;struct {unsigned profile=8; uint64_t informationGeneration{}; }sourceInfo;};
 bool m_submissionAsync=false,m_asyncEligible=false,m_hdr10plusSubmits=false;
 struct {bool asyncEligible=false;}m_submission;
 pl_renderer m_renderer=&rendererToken;pl_opengl m_gl=nullptr;pl_log m_log=nullptr;void*m_packer=&packer;pl_tex m_scanout=nullptr;bool m_pending=false,m_prepared=false,m_live=true,m_hdr10=false;unsigned m_outputBits=0,m_scanoutFramebuffer=0;Binding m_failedIdentity{};
 std::shared_ptr<Context> m_context;
 dvbridge_geometry m_sourceGeometry{};bool m_geometryKnown=false,m_hasCommitted=false,m_committedPacked=false;
 bool m_direct=false,m_dvPolicyActive=false,m_pendingOverlayVisible=false,m_overlayVisible=false,m_nativeOverlayEnabled=false,m_directUsable=false,m_fallback=false;
 bool Advanced(){return false;}void Reset(){m_pending=m_prepared=false;}int m_spatialMethod=0,m_pendingHDR10Fallback=0,m_nativeOverlay=0;
 dvbridge_gamut m_sdrGamut{};
 uint64_t m_geometryRevision=0,m_committedRevision=0,m_nativeOverlayRevision=0,m_committedOverlayRevision=0,m_pendingOverlayRevision=0;
 Binding m_committedBinding{},m_pendingBinding{},m_pendingIdentity{};
 decltype(VideoPicture::doviMetadata)m_pendingMetadata;
 dvbridge_mode m_effectiveMode=DVBRIDGE_MODE_DISABLED,m_committedMode=DVBRIDGE_MODE_DISABLED;
 bool PollReady(){return true;}

 void BeginDiagnosticStream(unsigned){}bool Failure(const char*){return false;}
 FrameStatus PrepareFrame(const Layer& base,const Layer* enhancement,const decltype(VideoPicture::doviMetadata)& metadata,
  dvbridge_geometry geometry,const DVBRIDGE::OutputPreferences& preferences,bool allowPacked,const dvbridge_policy* selected,bool allowAsync) __ACTUAL_BODY_2_END__
 bool Initialize(bool allowSoftware,bool hdr10,std::shared_ptr<Context> context,bool sdr,unsigned framebuffer=0) __ACTUAL_BODY_18_END__
 void SetHDR10PlusVersion(int){}
 bool SetHDR10Session(const dvbridge_hdr10_session&,unsigned,bool){return true;}
 bool rebindHDR=false,rebindSDR=false;
 void Cancel(){} bool RebindOutputSurface(bool hdr10,bool sdr=false,unsigned framebuffer=0) __ACTUAL_BODY_19_END__
 template<class... T> Binding SelectionIdentity(T...){return {};}
};
struct State {bool CapturePlayerLed(...){captured=true;return true;}bool Capture(...){captured=true;return true;}const char* CaptureFailure(){return "none";}void Restored(){captured=false;}bool captured=false; bool Captured()const{return captured;}
 template<class T> bool Stage(T&,bool){return true;}};
struct Mode {int hdisplay=3840,vdisplay=2160;unsigned clock=296703,htotal=4400,vtotal=2250;};
struct Connector {bool SupportsProperty(const char*){return true;}std::optional<unsigned>GetPropertyValue(const char*){return 0;}};
struct DRM {virtual ~DRM()=default;Mode mode;const Mode*GetSelectedMode(){return &mode;}};
struct gbm_bo;
struct CDRMAtomic : DRM {
 unsigned failures=0;unsigned DVActivationFailures(){return failures;}void FailDVActivation(int){++failures;}void ResetDVActivation(){failures=0;}void SetCB1TimingPeriod(uint64_t){}bool CanRetryDVActivation(bool){return true;}int DVActivationError(){return failures?22:0;}
 Plane plane;Plane*GetGuiPlane(){return &plane;}Plane*GetVideoPlane(){return nullptr;}bool FindVideoPlane(unsigned,uint64_t){return true;}bool FindGuiPlane(unsigned,uint64_t){return true;}bool HasQuirk(int){return false;}void SetActive(bool){}bool TestFramebuffer(gbm_bo*){return true;}
 void SetDVActivationPending(bool){} Connector connector;Connector*GetConnector(){return &connector;}bool IsSelectedModeCommitted(){return true;}bool FlipPageTransactional(void*,bool){return true;}
 bool AddProperty(void*,const char*,unsigned){return true;}
};
struct GBM {
 int lifetime=0;gbm_bo front,prior;bool pending=false;
 struct Lease{gbm_bo*value;gbm_bo*Get(){return value;}};
 GBM&GetDevice(){return *this;}GBM&GetSurface(){return *this;}void*Get(){return this;}
 void UseDVOutputLifetime(){++lifetime;}
 bool CreateSurface(int,int,unsigned format,const uint64_t*,size_t,bool transaction){if(transaction){prior=front;pending=true;}front.format=format;return true;}
 void CompleteOutputSurface(bool accepted){if(pending&&!accepted)front=prior;pending=false;}
gbm_bo*LockTransactionalBuffer(){return &front;}void CompleteTransactionalBuffer(bool){}void EndTransactionalMode(){}
 Lease LockFrontBuffer(){return {&front};}
};
struct CWinSystemGbm {
 int m_nWidth=3840,m_nHeight=2160,m_renderableType=EGL_OPENGL_ES3_BIT;std::shared_ptr<CDRMAtomic>m_DRM=std::make_shared<CDRMAtomic>();std::shared_ptr<GBM>m_GBM=std::make_shared<GBM>();

 bool SetVideoOutput(const VideoPicture*){return true;}
};
struct CWinSystemGbmEGLContext:CWinSystemGbm {
 CEGLContextUtils m_eglContext;
 bool m_dvOutputSurface=false,m_dvSurfacePending=false,m_floatOutputBlocked=false,m_priorOutputVideo=false;
 std::unique_ptr<VideoPicture>m_floatOutputPicture;
 Plane*m_priorOutputPlane=nullptr;unsigned m_priorOutputFormat=0;uint64_t m_priorOutputModifier=0;
 virtual int VideoOutputBitDepth(const VideoPicture*p)const{return p?p->colorBits:8;}
 virtual bool PrepareHDR10Scanout(){return false;}
 virtual bool RetainHDR10ScanoutOnTransition()const{return false;}
 virtual bool RejectDVOutputSurface(){return CompleteDVOutputSurface(false);}
 bool HasPendingDVOutputSurface(){return m_dvSurfacePending;}
 void UseDVOutputSurfaceTransaction(bool enabled){m_dvOutputSurface=enabled;}
 bool FloatOutputUsable(){return false;}bool HasFloatOutput(){return false;}
 std::vector<uint64_t>OutputModifiers(unsigned){return {0};}
 bool ChooseEGLConfig(int,int depth){m_eglContext.m_eglConfig=depth>8?30:24;return true;}
 bool SetVideoOutput(const VideoPicture*);bool CompleteDVOutputSurface(bool);
};
struct CWinSystemGbmGLESContext : CWinSystemGbmEGLContext {
 bool requested=true,m_dvStopPending=false,m_dvOrdinaryFrame=false;
 bool m_dvActivating=false,m_dvOutputRetiring=false,m_hdrConversion=false,m_sdrConversion=false,m_dvPriorSDRConversion=false;
 bool m_pascalHDRActive=false,m_priorPascalHDRActive=false;
 unsigned HDR10Framebuffer()const{return 0;}
 bool m_dvPriorHDRConversion=false,m_dvPriorGuiCompositing=false,m_guiCompositing=false;
 float m_guiSDRGamma=2.4f,m_dvPriorGuiSDRGamma=2.4f;
 bool m_dvPQSubtitleDraws=false;
 bool m_cb1FramePending=false,m_dvFrame=false,m_dvNativeGui=false;
 bool m_failedHDR10SetupRestore=false,m_dvShutdownFence=false;
 bool completeOK=true,pollOK=true,restoreOK=true,modeOK=true,recoveryOK=true;
 Capabilities capabilities;
 bool m_dvSuperseded=false,m_dvEndPending=false,m_dvRecoveryPending=false,m_dvRejectedSurface=false,m_dvRollbackFailed=false,m_dvFatalConsumed=false,m_dvNativeFailed=false,m_dvFallbackActive=false;
 DVBRIDGE::OutputReason m_dvFatalReason=DVBRIDGE::OutputReason::None,m_dvActivationReason=DVBRIDGE::OutputReason::None;
 mutable std::mutex m_dvCapabilityMutex;
 unsigned m_dvAttemptFailures=0,m_hdr10SessionStream=0;
 uint64_t m_dvProfileLoggedRevision{},m_dvProfileLoggedStream{};
 std::optional<dvbridge_hdr10_session> m_hdr10Session;
 std::unique_ptr<VideoPicture>m_hdr10BasicSignal;
 struct {template<class... T> void Begin(T...){}template<class... T>bool Active(T...)const{return false;}} m_masterSafety;
 bool m_cb1RestoringPreferences=false;
 int ordinaryStages=0;
 std::optional<dvbridge_mode>m_dvPriorConfiguredOutput,m_dvConfiguredOutput;std::optional<std::array<unsigned,5>>m_hdr10Signal;
 std::optional<unsigned> m_hdrDeepColorPrevious;
 enum class SDRBT2020Support { Available, Display, Driver };
 SDRBT2020Support sdrSupport=SDRBT2020Support::Available;
 SDRBT2020Support GetSDRBT2020Support()const{return sdrSupport;}
 bool m_sdrBT2020Rejected{};
 unsigned m_dvPendingStream=0,m_dvPendingPolicy=0,m_dvFailedStream=0,m_dvFailedPolicy=0;
 struct {void Cancel(){}bool Commits(uint64_t){return true;}CModeChangeHold::Kind Holding(){return CModeChangeHold::Kind::START;}} m_modeHold;
 CHeldModeAnnouncement m_modeAnnouncement;
 State m_dvState;
 Selection m_dvSelection;
 std::shared_ptr<CDVBridgeGLES::Context> m_dvContext;
 std::unique_ptr<CDVBridgeGLES> m_dvBridge;


bool StopDVBridgePlayback();bool HoldCB1Stop(){return false;}uint64_t m_masterFramePeriodNs=0,m_previousSourceStream=0;bool m_continuousFrameEligible=false;double m_previousSourcePts=0;
 bool SupportsDVOutputMode(){return modeOK;}
 struct LldvStatus{bool currentTiming;};
 LldvStatus GetLldvConnectorStatus(){return {modeOK};}
 bool SupportsSDRConversion(){return modeOK;}
 bool DVBridgeRequested(const VideoPicture* p){return p&&SelectedDVOutput(p).route!=DVBRIDGE::OutputRoute::Vanilla;}
 bool CompleteDVBridgePage(){return completeOK;}
 bool RecoverDVActivation();
 void ResetDVActivation(const VideoPicture*);
 Capabilities GetDVOutputCapabilities(const VideoPicture*)const{return capabilities;}
 Capabilities GetDVOutputCapabilities(const VideoPicture*,const DVBRIDGE::OutputPreferences&)const{return capabilities;}
 Selection SelectedDVOutput(const VideoPicture*)const;
 Selection SelectedDVOutput(const VideoPicture*,const DVBRIDGE::OutputPreferences&,Capabilities&)const;
 bool PollRejectedDVSurface();
 bool RejectDVOutputSurface();
 bool EndDVBridge();
 void SetColorimetry(const VideoPicture*){}
 bool SetHDR(const VideoPicture* picture){++ordinaryStages;return picture && picture->color_transfer;}
 bool SetGuiCompositing(int color){m_guiCompositing=color!=0;if(color)m_compositeShader=std::make_unique<int>(1);return true;}
 bool SetVideoOutput(const VideoPicture*);
 bool StageCB1ConnectorPreferences(bool){return true;}
 bool PrepareOrdinaryDVOutput(const VideoPicture*);
 bool RetireDVContext();
 bool PrepareDVOutputFrame(const VideoPicture&);
 bool ConfigureSDRConversion(const VideoPicture&){return BeginDVBridge();}
bool RestoreFailedHDR10Setup(){m_failedHDR10SetupRestore=false;return true;}void AnnounceCB1Mode(bool){}void CompleteCB1Mode(bool,bool){}bool FlipDVBridgePage(State& state,bool){state.Restored();return true;}
 bool ConfigureHDR10Conversion(const VideoPicture&);
 bool BeginDVBridge();
 bool m_dvHDR10Failed=false,m_dvSDRFailed=false,m_dvPlayerLedFailed=false;
 unsigned m_dvActivationStream{},m_dvActivationPolicy{};
 DVBRIDGE::OutputRoute m_dvRejectedRoute=DVBRIDGE::OutputRoute::Vanilla;
 State m_cb1ConnectorState;
 struct Failures {int Record(...){return 1;}int Count(){return 1;}bool Recovered(...){return false;}}m_dvSetupFailures;
 struct {void Reset(){}}m_presentStall;
 std::unique_ptr<int>m_compositeShader;

 struct Display {int HDR10PlusVersion()const{return -1;}struct Caps{bool supports_2160p60=true,legacy_vsif=false;};Caps GetDolbyVisionCaps()const{return {};}}display;
 const Display*GetDisplayInfo(){return &display;}
 int GetOutputBitDepth(){return m_eglContext.GetConfigAttrib(EGL_RED_SIZE);}
 int VideoOutputBitDepth(const VideoPicture* picture)const override __ACTUAL_BODY_3_END__
 bool CaptureCB1ConnectorPreferences(){m_cb1ConnectorState.captured=true;return true;}
 void CompleteCB1ConnectorRestore(){m_cb1ConnectorState.Restored();}
 void DeferConnectorPreferences(){}
 bool UseLimitedColor(){return false;}bool FloatOutputUsable(){return true;}
 bool ConfigureGuiCompositing(int color,float gamma){m_guiCompositing=color!=0;m_guiSDRGamma=gamma;return true;}


};
bool CWinSystemGbmGLESContext::SetVideoOutput(const VideoPicture* picture)__ACTUAL_BODY_4_END__
bool CWinSystemGbmGLESContext::PrepareOrdinaryDVOutput(const VideoPicture* picture)__ACTUAL_BODY_5_END__
bool CWinSystemGbmGLESContext::RetireDVContext()__ACTUAL_BODY_6_END__
bool CWinSystemGbmGLESContext::PrepareDVOutputFrame(const VideoPicture& picture)__ACTUAL_BODY_7_END__
bool CWinSystemGbmGLESContext::BeginDVBridge()__ACTUAL_BODY_8_END__
bool CWinSystemGbmGLESContext::ConfigureHDR10Conversion(const VideoPicture& picture)__ACTUAL_BODY_9_END__
bool CWinSystemGbmGLESContext::RejectDVOutputSurface()__ACTUAL_BODY_10_END__
bool CWinSystemGbmGLESContext::PollRejectedDVSurface()__ACTUAL_BODY_11_END__
DVBRIDGE::OutputSelection CWinSystemGbmGLESContext::SelectedDVOutput(const VideoPicture* picture) const__ACTUAL_BODY_12_END__
DVBRIDGE::OutputSelection CWinSystemGbmGLESContext::SelectedDVOutput(const VideoPicture* picture,
    const DVBRIDGE::OutputPreferences& preferences, DVBRIDGE::OutputCapabilities& caps) const__ACTUAL_BODY_13_END__
bool CWinSystemGbmGLESContext::StopDVBridgePlayback()__ACTUAL_BODY_17_END__
void CWinSystemGbmGLESContext::ResetDVActivation(const VideoPicture* picture)__ACTUAL_BODY_14_END__
bool CWinSystemGbmGLESContext::RecoverDVActivation()__ACTUAL_BODY_15_END__
bool CWinSystemGbmGLESContext::EndDVBridge()__ACTUAL_BODY_16_END__
bool CWinSystemGbmEGLContext::SetVideoOutput(const VideoPicture* videoPicture)__ACTUAL_BODY_20_END__
bool CWinSystemGbmEGLContext::CompleteDVOutputSurface(bool submitted)__ACTUAL_BODY_21_END__
bool CEGLContextUtils::BeginOutputSurface()__ACTUAL_BODY_22_END__
bool CEGLContextUtils::StageOutputSurface(void* nativeWindow, EGLNativeWindowType legacy)__ACTUAL_BODY_23_END__
bool CEGLContextUtils::BindPriorOutputSurface()__ACTUAL_BODY_24_END__
bool CEGLContextUtils::CompleteOutputSurface(bool presented)__ACTUAL_BODY_25_END__
int main(){
 using Route=DVBRIDGE::OutputRoute;using Mode=DVBRIDGE::OutputMode;
 int failed=0;
 auto check=[&](bool good,const char* label){std::cout<<(good?"PASS ":"FAIL ")<<label<<'\n';failed+=!good;};
 auto setup=[](CWinSystemGbmGLESContext& w){
  w.capabilities.sourceKnown=w.capabilities.isDV=w.capabilities.processingKnown=true;
  w.capabilities.nativeDV=w.capabilities.hdr10=true;
  for(auto& admission:w.capabilities.processing)admission={true,DVBRIDGE::OutputReason::None};
 };
 VideoPicture picture;picture.doviSourceBinding={1,1,1};picture.doviMetadata.value=picture.doviSourceBinding;
 picture.doviSourceInfo.profile=8;picture.doviSourceInfo.compatibility=1;picture.hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;
 auto request=[](Mode mode){DVBRIDGE::current.output=mode;++DVBRIDGE::current.revision;};
 for(int test=0;test<3;++test){
  CWinSystemGbmGLESContext w;setup(w);request(Mode::HDR10);
  check(w.PrepareDVOutputFrame(picture)&&w.GetOutputBitDepth()==10,"HDR initial admission stages native10");
  check(w.CompleteDVOutputSurface(true),"HDR surface accepted boundary");w.m_dvActivating=false;
  request(Mode::MasterReference);
  check(w.PrepareDVOutputFrame(picture)&&w.GetOutputBitDepth()==8&&w.HasPendingDVOutputSurface(),"Master stages pending8 without accepting it");
  CDVBridgeGLES::Layer layer;layer.binding=picture.doviSourceBinding;
  const auto status=w.m_dvBridge->PrepareFrame(layer,nullptr,picture.doviMetadata,{},DVBRIDGE::current,false,&w.m_dvSelection.policy,false);
  check(status==CDVBridgeGLES::FrameStatus::Busy&&DVBRIDGE::lastStage=="master-await-overlay","real Master entry defers before first presentation");
  request(test==0?Mode::HDR10:test==1?Mode::SDR:Mode::MasterReference);
  const auto result=w.PrepareDVOutputFrame(picture);
  std::cout<<"TRACE case="<<test<<" ready="<<result<<" depth="<<w.GetOutputBitDepth()<<" pending="<<w.HasPendingDVOutputSurface()
    <<" route="<<int(w.m_dvSelection.route)<<" rebindHDR="<<w.m_dvBridge->m_hdr10
    <<" pending_policy="<<w.m_dvPendingPolicy<<" selected_policy="<<DVBRIDGE::current.revision
    <<" recovery="<<w.m_dvRecoveryPending<<" rejected_route="<<int(w.m_dvRejectedRoute)<<'\n';
  if(test==0)check(result,"superseding proven HDR destination must not fail on abandoned Master8 surface");
  if(test==1)check(result&&w.m_dvBridge->m_hdr10&&w.m_dvBridge->m_outputBits==8,"same-depth SDR destination must rebind renderer out of abandoned DV transport");
  if(test==2)check(result,"same-route Master retry remains admissible");
 }
 // Inverse: the actual retirement Busy path keeps HDR unpresented before DV returns.
 {
  CWinSystemGbmGLESContext w;setup(w);request(Mode::MasterReference);
  check(w.PrepareDVOutputFrame(picture)&&w.GetOutputBitDepth()==8,"inverse initial Master stages8");
  check(w.CompleteDVOutputSurface(true),"inverse Master accepted boundary");w.m_dvActivating=false;
  request(Mode::HDR10);
  check(w.PrepareDVOutputFrame(picture)&&w.GetOutputBitDepth()==10&&w.HasPendingDVOutputSurface(),"inverse HDR stages pending10");
  w.m_dvContext->ready=false;
  CDVBridgeGLES::Layer layer;layer.binding=picture.doviSourceBinding;
  check(w.m_dvBridge->PrepareFrame(layer,nullptr,picture.doviMetadata,{},DVBRIDGE::current,true,&w.m_dvSelection.policy,false)==CDVBridgeGLES::FrameStatus::Busy,"actual HDR retirement Busy path defers first presentation");
  w.m_dvContext->ready=true;request(Mode::MasterReference);
  const auto result=w.PrepareDVOutputFrame(picture);
  std::cout<<"TRACE inverse ready="<<result<<" depth="<<w.GetOutputBitDepth()<<" recovery="<<w.m_dvRecoveryPending<<" rejected_route="<<int(w.m_dvRejectedRoute)<<'\n';
  check(result&&w.GetOutputBitDepth()==8,"inverse final Master must not fail on abandoned HDR10 surface");
 }
 auto pendingMaster=[&](CWinSystemGbmGLESContext& w){setup(w);request(Mode::HDR10);assert(w.PrepareDVOutputFrame(picture));assert(w.CompleteDVOutputSurface(true));w.m_dvActivating=false;request(Mode::MasterReference);assert(w.PrepareDVOutputFrame(picture));};
 {
  CWinSystemGbmGLESContext w;pendingMaster(w);const auto retained=nextSurface;const auto owner=w.m_dvPendingPolicy;
  check(w.PrepareDVOutputFrame(picture)&&nextSurface==retained&&w.m_dvPendingPolicy==owner,"unchanged pending target does not recreate or rekey surfaces");
 }
 {
  CWinSystemGbmGLESContext w;pendingMaster(w);request(Mode::HDR10);w.m_dvContext->ready=false;
  check(!w.PrepareDVOutputFrame(picture)&&w.HasPendingDVOutputSurface()&&!w.m_dvRollbackFailed,"supersession waits for ordinary GPU retirement");
  check(w.m_DRM->DVActivationFailures()==0,"benign pending supersession does not count activation failure");
  w.m_dvContext->ready=true;
  check(w.PrepareDVOutputFrame(picture)&&w.GetOutputBitDepth()==10&&!w.m_dvRecoveryPending&&!w.m_dvSuperseded,"retired supersession admits final HDR target and clears cancellation state");
 }
 for(bool gpuFailure:{false,true}){
  CWinSystemGbmGLESContext w;pendingMaster(w);request(Mode::HDR10);
  failRestore=!gpuFailure;w.m_dvContext->fenceOK=!gpuFailure;
  check(!w.PrepareDVOutputFrame(picture)&&w.m_dvRollbackFailed&&w.HasPendingDVOutputSurface(),"real rollback/GPU failure remains blocking and retains surfaces");
  check(w.m_eglContext.m_priorSurface!=0&&w.m_eglContext.m_priorConfig==30&&w.m_dvPriorConfiguredOutput==DVBRIDGE_MODE_HDR10_BASIC,"failed cancellation retains accepted predecessor format and mode");
  check(!w.PrepareDVOutputFrame(picture)&&w.m_dvFatalReason==DVBRIDGE::OutputReason::RestoreFailed,"failed cancellation is diagnosed as restoration failure");
  failRestore=false;
 }
 {
  CWinSystemGbmGLESContext w;pendingMaster(w);w.m_renderableType=0;request(Mode::SDR);
  check(!w.PrepareDVOutputFrame(picture)&&w.m_dvRecoveryPending&&w.m_DRM->DVActivationFailures()>0,"genuine successor setup failure still uses activation failure bookkeeping");
 }
 {
  CWinSystemGbmGLESContext w;pendingMaster(w);request(Mode::HDR10);w.m_dvContext->ready=false;
  check(!w.PrepareDVOutputFrame(picture),"stop control begins with deferred supersession");w.m_dvContext->ready=true;
  check(w.StopDVBridgePlayback()&&!w.m_dvRecoveryPending&&!w.m_dvSuperseded&&!w.HasPendingDVOutputSurface(),"stop drains cancellation through existing shared recovery");
 }
 {
  CWinSystemGbmGLESContext w;pendingMaster(w);auto other=picture;other.doviSourceBinding.stream=2;other.doviMetadata.value=other.doviSourceBinding;
  check(w.PrepareDVOutputFrame(other)&&w.m_dvPendingStream==2,"new source stream cannot inherit another stream pending surface owner");
 }
 {
  CWinSystemGbmGLESContext w;pendingMaster(w);request(Mode::SDR);DVBRIDGE::current.sdrPreset=2;DVBRIDGE::current.sdrGamma=2.6;
  DVBRIDGE::current.sdrBT2020=true;
  w.sdrSupport=CWinSystemGbmGLESContext::SDRBT2020Support::Driver;
  check(w.PrepareDVOutputFrame(picture)&&w.m_dvSelection.policy.sdr.gamut==DVBRIDGE_GAMUT_BT709,
      "unsupported wide gamut remains BT.709 through surface setup");
  w.sdrSupport=CWinSystemGbmGLESContext::SDRBT2020Support::Available;
  w.m_sdrBT2020Rejected=true;
  check(w.PrepareDVOutputFrame(picture)&&w.m_dvSelection.policy.sdr.gamut==DVBRIDGE_GAMUT_BT709,
      "a rejected wide gamut remains BT.709 for this playback policy");
  const auto previous=w.m_dvPendingPolicy;++DVBRIDGE::current.revision;DVBRIDGE::current.sdrGamma=2.2;
  check(w.PrepareDVOutputFrame(picture)&&w.m_dvPendingPolicy!=previous&&w.m_dvSelection.policy.sdr.gamut==DVBRIDGE_GAMUT_BT2020,"same effective SDR mode with changed target revision rekeys pending owner");
 }
 {CWinSystemGbmGLESContext w;w.m_dvSuperseded=true;check(w.EndDVBridge()&&!w.m_dvSuperseded,"successful already-ordinary cleanup clears cancellation state");}
 {
  CWinSystemGbmGLESContext w;pendingMaster(w);request(Mode::HDR10);w.m_dvContext->pollFailed=true;
  check(!w.PrepareDVOutputFrame(picture)&&w.m_dvRollbackFailed,"failed GPU retirement is fatal rather than an endless benign wait");
  check(!w.PrepareDVOutputFrame(picture)&&w.m_dvFatalReason==DVBRIDGE::OutputReason::RestoreFailed,"failed GPU retirement publishes restoration failure");
 }
 return failed?1:0;
}
'''
  program=program.replace('ACTUAL_RETIREMENT_STATUS',status_enum)
  program=program.replace('__ACTUAL_BODY_0_END__',settings)
  program=program.replace('__ACTUAL_BODY_1_END__',selector)
  program=program.replace('__ACTUAL_BODY_2_END__',body(render,'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(').split('  m_live = true;')[0]+'\nreturn FrameStatus::Ready;}')
  program=program.replace('__ACTUAL_BODY_3_END__',body(window,'int CWinSystemGbmGLESContext::VideoOutputBitDepth('))
  program=program.replace('__ACTUAL_BODY_4_END__',body(window,'bool CWinSystemGbmGLESContext::SetVideoOutput(const VideoPicture* picture)'))
  program=program.replace('__ACTUAL_BODY_5_END__',body(window,'bool CWinSystemGbmGLESContext::PrepareOrdinaryDVOutput(const VideoPicture* picture)'))
  program=program.replace('__ACTUAL_BODY_6_END__',body(window,'bool CWinSystemGbmGLESContext::RetireDVContext()'))
  program=program.replace('__ACTUAL_BODY_7_END__',body(window,'bool CWinSystemGbmGLESContext::PrepareDVOutputFrame(const VideoPicture& picture)'))
  program=program.replace('__ACTUAL_BODY_8_END__',body(window,'bool CWinSystemGbmGLESContext::BeginDVBridge()'))
  program=program.replace('__ACTUAL_BODY_9_END__',body(window,'bool CWinSystemGbmGLESContext::ConfigureHDR10Conversion(const VideoPicture& picture)'))
  program=program.replace('__ACTUAL_BODY_10_END__',body(window,'bool CWinSystemGbmGLESContext::RejectDVOutputSurface()'))
  program=program.replace('__ACTUAL_BODY_11_END__',body(window,'bool CWinSystemGbmGLESContext::PollRejectedDVSurface()'))
  program=program.replace('__ACTUAL_BODY_12_END__',body(window,'DVBRIDGE::OutputSelection CWinSystemGbmGLESContext::SelectedDVOutput(const VideoPicture* picture) const'))
  program=program.replace('__ACTUAL_BODY_13_END__',body(window,'DVBRIDGE::OutputSelection CWinSystemGbmGLESContext::SelectedDVOutput(const VideoPicture* picture,\n    const DVBRIDGE::OutputPreferences& preferences, DVBRIDGE::OutputCapabilities& caps) const'))
  program=program.replace('__ACTUAL_BODY_14_END__',body(window,'void CWinSystemGbmGLESContext::ResetDVActivation(const VideoPicture* picture)'))
  program=program.replace('__ACTUAL_BODY_15_END__',body(window,'bool CWinSystemGbmGLESContext::RecoverDVActivation()'))
  program=program.replace('__ACTUAL_BODY_16_END__',body(window,'bool CWinSystemGbmGLESContext::EndDVBridge()'))
  program=program.replace('__ACTUAL_BODY_17_END__',body(window,'bool CWinSystemGbmGLESContext::StopDVBridgePlayback()'))
  program=program.replace('__ACTUAL_BODY_18_END__',body(render,'bool CDVBridgeGLES::Initialize('))
  program=program.replace('__ACTUAL_BODY_19_END__',body(render,'bool CDVBridgeGLES::RebindOutputSurface('))
  program=program.replace('__ACTUAL_BODY_20_END__',body(egl,'bool CWinSystemGbmEGLContext::SetVideoOutput(const VideoPicture* videoPicture)'))
  program=program.replace('__ACTUAL_BODY_21_END__',body(egl,'bool CWinSystemGbmEGLContext::CompleteDVOutputSurface(bool submitted)'))
  program=program.replace('__ACTUAL_BODY_22_END__',body(utils,'bool CEGLContextUtils::BeginOutputSurface()'))
  program=program.replace('__ACTUAL_BODY_23_END__',body(utils,'bool CEGLContextUtils::StageOutputSurface(void* nativeWindow, EGLNativeWindowType legacy)'))
  program=program.replace('__ACTUAL_BODY_24_END__',body(utils,'bool CEGLContextUtils::BindPriorOutputSurface()'))
  program=program.replace('__ACTUAL_BODY_25_END__',body(utils,'bool CEGLContextUtils::CompleteOutputSurface(bool presented)'))
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);code=root/'check.cpp';binary=root/'check'
   code.write_text(program,encoding='utf-8')
   built=subprocess.run(['c++','-std=c++20','-DHAVE_DVBRIDGE','-I'+str(TREE/'xbmc'),'-I'+str(ROOT/'CB1/src'),str(code),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(built.returncode,0,built.stderr)
   ran=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
