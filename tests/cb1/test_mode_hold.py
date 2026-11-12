"""Held display changes notify around commits, including refused first output."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class ModeHoldTests(unittest.TestCase):
    def test_first_output_keeps_held_mode_until_real_receipt_across_deadline(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        present=body(source,'void CWinSystemGbmGLESContext::PresentFrame(bool rendered, bool videoLayer)')
        # Execute the actual entry gate before the unchanged restoration branches.
        gate=present.split('  if (m_dvStopPending && !m_dvOrdinaryFrame',1)[0]+'\n#endif\n++pastGate;\n}'
        complete=body(source,'bool CWinSystemGbmGLESContext::CompleteDVModeSwitch(')
        receipt=body(source,'void CWinSystemGbmGLESContext::CompleteCB1Mode(')
        program=r'''
#define HAVE_DVBRIDGE
#include "ModeChangeHold.h"
#include <cassert>
#include <chrono>
#include <cstdint>
#include <memory>
#include <mutex>
#include <thread>
using namespace KODI::WINDOWING::GBM;
int64_t now=0;
namespace DVBRIDGE {
 int64_t DiagnosticNowMs(){return now;}
 enum class OutputReason {None,ActivationFailed};
 enum class OutputRoute {NativeDV,HDR10,SDR,PlayerLed};
}
struct VideoPicture {};
struct CDRMAtomic {
 bool committed=false;
 bool IsSDRRestorePending(){return false;}
 bool IsSelectedModeCommitted(){return committed;}
};
struct Manager {void MarkDirty(){}};
struct GUI {Manager manager;Manager& GetWindowManager(){return manager;}};
struct Settings {Settings* GetSettings(){return this;}int GetInt(const char*){return 3;}};
struct CServiceBroker {
 static GUI* GetGUI(){static GUI g;return &g;}
 static Settings* GetSettingsComponent(){static Settings s;return &s;}
};
struct Timer {void Set(std::chrono::milliseconds){}};
struct State {bool captured=false;bool Captured(){return captured;}};
struct Window {
 CModeChangeHold m_modeHold;CHeldModeAnnouncement m_modeAnnouncement;
 std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
 State m_dvState;bool m_hdrConversion=false,m_dvFrame=false,pageReady=true,supported=true;
 bool m_dvNativeFailed=false,m_dvHDR10Failed=false,m_dvSDRFailed=false,m_dvPlayerLedFailed=false,m_dvFallbackActive=false;
 struct {DVBRIDGE::OutputRoute route=DVBRIDGE::OutputRoute::NativeDV;}m_dvSelection;
 std::mutex m_dvCapabilityMutex;Timer m_dispResetTimer;
 DVBRIDGE::OutputReason m_dvActivationReason=DVBRIDGE::OutputReason::None;
 uint64_t m_dvFailedStream=0,m_dvFailedPolicy=0,m_dvActivationStream=9,m_dvActivationPolicy=2;
 int pastGate=0;
 bool CompleteDVBridgePage(int){return pageReady;}
 bool SupportsDVOutputMode(){return supported;}
 bool SupportsSDRConversion(){return supported;}
 struct LldvStatus{bool currentTiming;};
 LldvStatus GetLldvConnectorStatus(){return {supported};}
 void ResetDVActivation(const VideoPicture*){}
 void tick(bool rendered=false,bool videoLayer=false) GATE
 bool complete(const VideoPicture& picture) COMPLETE
 void receipt(bool accepted,bool transport) RECEIPT
};
void first_output(bool converted) {
 Window w;VideoPicture picture;
 now=0;w.m_modeHold.Start(now);w.m_modeAnnouncement.Held();
 // Real first picture captured just before the observed 3-second boundary.
 now=2999;w.m_dvState.captured=!converted;w.m_hdrConversion=converted;
 now=3001;w.tick();
 assert(w.m_modeHold.Holding()==CModeChangeHold::Kind::START &&
        "a prepared output must retain ownership until its real flip");
 assert(w.pastGate==1 && "stop/recovery/restoration must remain reachable");
 assert(w.complete(picture) && !w.m_dvNativeFailed);
 // A first frame that never arrives can still be stopped/restored after expiry.
 now=4000;w.tick();assert(w.pastGate==2);
 assert(w.m_modeAnnouncement.Before(false));w.receipt(false,false);
 now=5000;w.tick();assert(w.pastGate==3);
 assert(w.m_modeAnnouncement.Before(false));w.receipt(true,false);
 w.m_dvState.captured=false;w.m_hdrConversion=false;w.m_DRM->committed=true;
 assert(w.m_modeHold.Holding()==CModeChangeHold::Kind::NONE);
 assert(w.complete(picture));
 // Normal first output also closes the hold at its real accepted receipt.
 Window accepted;now=0;accepted.m_modeHold.Start(now);accepted.m_modeAnnouncement.Held();
 accepted.m_dvState.captured=!converted;accepted.m_hdrConversion=converted;
 now=3001;accepted.tick();assert(accepted.complete(picture));
 accepted.m_dvFrame=true;accepted.tick();assert(accepted.pastGate==2);
 assert(accepted.m_modeAnnouncement.Before(true));accepted.receipt(true,true);
 assert(accepted.m_modeHold.Holding()==CModeChangeHold::Kind::NONE);
 accepted.m_DRM->committed=true;assert(accepted.complete(picture));
}
int main(){
 first_output(false);first_output(true);
 // No producer: the existing deadline still releases the ordinary commit.
 Window idle;now=0;idle.m_modeHold.Start(now);
 now=2999;idle.tick();assert(idle.pastGate==0);
 now=3001;idle.tick();assert(idle.pastGate==1);
 assert(idle.m_modeHold.Holding()==CModeChangeHold::Kind::NONE);
 VideoPicture picture;assert(!idle.complete(picture) && idle.m_dvNativeFailed);
 // Ready native first frame closes the hold only with an accepted receipt.
 Window native;now=0;native.m_modeHold.Start(now);native.m_modeAnnouncement.Held();
 native.m_dvState.captured=true;native.m_dvFrame=true;now=3001;native.tick();
 assert(native.pastGate==1 && native.complete(picture));
 assert(native.m_modeAnnouncement.Before(true));native.receipt(false,true);
 assert(native.m_modeAnnouncement.Pending()==CHeldModeAnnouncement::Step::BEFORE_ORDINARY);
 native.m_dvFrame=false;native.tick();assert(native.pastGate==2);
 assert(native.m_modeAnnouncement.Before(false));native.receipt(true,false);
 native.m_dvState.captured=false;native.m_DRM->committed=true;
 assert(native.complete(picture));
 // Unsupported output and missing DRM must still fail even during START.
 Window unsupported;now=0;unsupported.m_modeHold.Start(now);unsupported.supported=false;
 assert(!unsupported.complete(picture));
 Window missing;missing.m_modeHold.Start(now);missing.m_DRM.reset();
 assert(!missing.complete(picture));
 Window pending;pending.m_modeHold.Start(now);pending.pageReady=false;
 now=4000;pending.tick();assert(pending.pastGate==0);
}
'''.replace('GATE',gate).replace('COMPLETE',complete).replace('RECEIPT',receipt)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-fno-omit-frame-pointer','-I'+str(TREE/'xbmc/windowing/gbm'),
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_renderer_carries_startup_intent_with_its_native_resolution_request(self):
        method=body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                    'void CRenderManager::UpdateResolution()')
        program=r'''
#define HAVE_DVBRIDGE
#include <atomic>
#include <cassert>
#include <optional>
#include <string>
using RESOLUTION=int;
constexpr int ADJUST_REFRESHRATE_OFF=0;
namespace DVBRIDGE {
inline std::atomic<int> modeChangeResolution{-1};
inline thread_local std::optional<int> guiModeChangeResolution;
}
struct CSettings {static constexpr const char* SETTING_VIDEOPLAYER_ADJUSTREFRESHRATE="adjust";};
struct Picture {int iWidth=3840,iHeight=2160;std::string stereoMode;};
struct Gfx {
 bool fullscreen=true,deferred=false,interleave=false;int resolution=60,intent=-9,calls=0;
 bool IsFullScreenVideo(){return fullscreen;}bool IsFullScreenRoot(){return true;}
 void SetVideoResolution(int res,bool){
  if(interleave)DVBRIDGE::modeChangeResolution.store(90);
  intent=DVBRIDGE::guiModeChangeResolution.value_or(DVBRIDGE::modeChangeResolution.load());
  if(!deferred)resolution=res;++calls;
 }
 int GetVideoResolution(){return resolution;}
};
namespace KODI::WINDOWING::GBM {struct CWinSystemGbmGLESContext {
 Gfx gfx;Gfx& GetGfxContext(){return gfx;}
 bool DVModeSwitchDeferred(){return gfx.deferred;}bool CompleteDVModeSwitch(const Picture&){return true;}
};}
struct Settings {int adjust=2;Settings* GetSettings(){return this;}int GetInt(const char*){return adjust;}};
struct CServiceBroker {
 static auto* GetWinSystem(){static KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;return &window;}
 static Settings* GetSettingsComponent(){static Settings settings;return &settings;}
};
struct CResolutionUtils {static int ChooseBestResolution(float,int,int,bool){return 24;}};
struct Renderer {int updates=0;void Update(){++updates;}};
struct Port {int changes=0;void VideoParamsChange(){++changes;}};
struct Manager {
 bool m_bTriggerUpdateResolution=true,m_nativeDVRate=true;float m_fps=24;Picture m_picture;
 Renderer renderer,*m_pRenderer=&renderer;Port port,*m_playerPort=&port;
 int ChoosePlaybackResolution(const Picture& picture,float fps,bool)const{return CResolutionUtils::ChooseBestResolution(fps,picture.iWidth,picture.iHeight,!picture.stereoMode.empty());}
 void UpdateLatencyTweak(){}
 void update() METHOD
};
int main(){
 auto& gfx=CServiceBroker::GetWinSystem()->gfx;
 // The initial request can be a no-op; the render manager owns the later switch.
 Manager native;native.update();assert(gfx.intent==24 && gfx.resolution==24);
 assert(DVBRIDGE::modeChangeResolution.load()==-1 && !native.m_bTriggerUpdateResolution);
 DVBRIDGE::modeChangeResolution.store(90);Manager pending;pending.update();
 assert(gfx.intent==24 && DVBRIDGE::modeChangeResolution.load()==90);
 Manager ordinary;ordinary.m_nativeDVRate=false;ordinary.update();
 assert(gfx.intent==-1 && DVBRIDGE::modeChangeResolution.load()==90);
 gfx.deferred=true;gfx.resolution=60;Manager deferred;deferred.update();
 assert(gfx.intent==24 && DVBRIDGE::modeChangeResolution.load()==90 && deferred.m_bTriggerUpdateResolution);
 gfx.deferred=false;
 DVBRIDGE::modeChangeResolution.store(-1);gfx.interleave=true;Manager overlap;overlap.update();
 assert(gfx.intent==24 && DVBRIDGE::modeChangeResolution.load()==90);
 assert(!DVBRIDGE::guiModeChangeResolution.has_value());gfx.interleave=false;
 int calls=gfx.calls;Manager inactive;gfx.fullscreen=false;inactive.update();assert(gfx.calls==calls);
 gfx.fullscreen=true;CServiceBroker::GetSettingsComponent()->adjust=0;
 Manager disabled;disabled.update();assert(gfx.calls==calls);
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],
                                 capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_display_reset_delay_starts_after_commit_not_before(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        announce=body(source,'void CWinSystemGbmGLESContext::AnnounceCB1Mode(bool transport)')
        complete=body(source,'void CWinSystemGbmGLESContext::CompleteCB1Mode(bool accepted, bool transport)')
        present=body(source,'void CWinSystemGbmGLESContext::PresentRender(bool rendered, bool videoLayer)')
        program=r'''
#define HAVE_DVBRIDGE
#include "ModeChangeHold.h"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <mutex>
#include <vector>
using namespace KODI::WINDOWING::GBM;
int now=0;
void glFinish(){}
constexpr int LOGDEBUG=0;
struct CLog {template<class... T>static void Log(T...) {}};
struct Settings {Settings* GetSettings(){return this;}int GetInt(const char*){return 3;}};
struct CServiceBroker {static Settings* GetSettingsComponent(){static Settings s;return &s;}};
struct Timer {int deadline=0,sets=0;void Set(std::chrono::milliseconds d){deadline=now+d.count();++sets;}
 bool IsTimePast(){return now>=deadline;}};
struct Resource {int resets=0;void OnResetDisplay(){++resets;}};
struct Window {
 CHeldModeAnnouncement m_modeAnnouncement;CModeChangeHold m_modeHold;
 bool m_bRenderCreated=true,m_dispReset=false,pending=false;
 int lost=0;Timer m_dispResetTimer;std::mutex m_resourceSection;
 Resource audio;std::vector<Resource*> m_resources{&audio};
 void OnLostDevice(){if(!m_dispReset){m_dispReset=true;++lost;}}
 void PresentFrame(bool,bool){}
 bool HasPendingDVOutputSurface(){return pending;}
 void announce(bool transport) ANNOUNCE
 void complete(bool accepted,bool transport) COMPLETE
 void present(bool rendered,bool videoLayer) PRESENT
};
int main(){
 Window w;w.m_modeAnnouncement.Held();w.announce(true);
 assert(w.lost==1 && w.m_dispResetTimer.sets==0);
 now=10000;w.present(false,false);assert(w.audio.resets==0);
 w.complete(true,true);assert(w.m_dispResetTimer.sets==1);
 now=10299;w.present(false,false);assert(w.audio.resets==0);
 now=10300;w.present(false,false);assert(w.audio.resets==1);
 w.announce(true);w.complete(true,true);assert(w.lost==1 && w.m_dispResetTimer.sets==1);
 w.m_modeAnnouncement.Held();w.announce(true);w.complete(false,true);
 now=20000;w.present(false,false);assert(w.audio.resets==1);
 w.announce(true);assert(w.lost==2);
 w.announce(false);w.complete(true,false);assert(w.m_dispResetTimer.sets==2);
 w.pending=true;now=21000;w.present(false,false);assert(w.audio.resets==1);
 w.pending=false;w.present(false,false);assert(w.audio.resets==2);
 w.m_modeAnnouncement.Held();w.announce(false);w.complete(false,false);
 now=30000;w.present(false,false);assert(w.audio.resets==2);
 w.announce(false);w.complete(true,false);assert(w.m_dispResetTimer.sets==3);
 now=30299;w.present(false,false);assert(w.audio.resets==2);
 now=30300;w.present(false,false);assert(w.audio.resets==3);
}
'''.replace('ANNOUNCE',announce).replace('COMPLETE',complete).replace('PRESENT',present)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/windowing/gbm'),
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_native_display_reset_compiles_without_dvbridge(self):
        present=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                     'void CWinSystemGbmGLESContext::PresentRender(bool rendered, bool videoLayer)')
        program=r'''
#include <cassert>
#include <mutex>
#include <vector>
constexpr int LOGDEBUG=0;
struct CLog {template<class... T>static void Log(T...) {}};
struct Resource {int resets=0;void OnResetDisplay(){++resets;}};
struct Window {
 bool m_bRenderCreated=true,m_dispReset=true;
 struct {bool IsTimePast(){return true;}} m_dispResetTimer;
 std::mutex m_resourceSection;Resource audio;std::vector<Resource*> m_resources{&audio};
 void PresentFrame(bool,bool){}
 void present(bool rendered,bool videoLayer) PRESENT
};
int main(){Window w;w.present(false,false);assert(w.audio.resets==1 && !w.m_dispReset);}
'''.replace('PRESENT',present)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_held_start_does_not_queue_an_unpresented_egl_buffer(self):
        method=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::SetFullScreen(')
        program=r'''
#define HAVE_DVBRIDGE
#include "ModeChangeHold.h"
#include "rendering/RenderSystemTypes.h"
#include <atomic>
#include <cassert>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
using namespace KODI::WINDOWING::GBM;
struct RESOLUTION_INFO {int iWidth=3840,iHeight=2160,dwFlags=0; std::string strId="mode";};
using RESOLUTION=int;
constexpr int D3DPRESENTFLAG_MODE3DSBS=1,D3DPRESENTFLAG_MODE3DTB=2,LOGERROR=0,LOGDEBUG=1,LOGINFO=2;
struct CLog {template<class... T> static void Log(T...) {}};
struct CEGLUtils {template<class... T> static void Log(T...) {}};
namespace DVBRIDGE {std::atomic<int> modeChangeResolution{0};
inline thread_local std::optional<int> guiModeChangeResolution;int DiagnosticNowMs(){return 0;}}
struct CDisplaySettings {
 static CDisplaySettings& GetInstance(){static CDisplaySettings value;return value;}
 RESOLUTION_INFO GetResolutionInfo(RESOLUTION) const{return {};}
};
struct Base {virtual ~Base()=default;};
struct CDRMAtomic:Base {bool IsSelectedModeCommitted()const{return true;}};
struct CWinSystemGbm {int commits=0; bool SetFullScreen(bool,RESOLUTION_INFO&,bool){++commits;return true;}};
struct CRenderSystemGLES {static void ResetRenderSystem(int,int){}};
struct EGL {int swaps=0;bool TrySwapBuffers(){++swaps;return true;}};
struct Gfx {void SetStereoMode(RenderStereoMode){}};
struct Window:CWinSystemGbm,CRenderSystemGLES {
 CModeChangeHold m_modeHold;CHeldModeAnnouncement m_modeAnnouncement;
 std::shared_ptr<int> m_dvBridge;
 std::shared_ptr<Base> m_DRM=std::make_shared<CDRMAtomic>();
 EGL m_eglContext;int m_nWidth=3840,m_nHeight=2160;bool held=true;
 bool HoldCB1Mode(RESOLUTION_INFO&){return held;}
 bool EndDVBridge(){return true;} bool RetireDVContext(){return true;}
 bool PrepareNvidiaModeRestore(const RESOLUTION_INFO&) {return true;}
 bool SupportsDVOutputMode(){return true;}
 bool CreateNewWindow(const char*,bool,RESOLUTION_INFO&){return true;}
 Gfx& GetGfxContext(){static Gfx gfx;return gfx;}
 void RefreshDVOutputCapabilities(){}
 bool set(bool fullScreen,RESOLUTION_INFO& res,bool blankOtherDisplays) METHOD
};
int main(){
 Window window;RESOLUTION_INFO res;
 assert(window.set(true,res,false));
 assert(window.m_modeHold.Holding()==CModeChangeHold::Kind::START);
 assert(window.m_eglContext.swaps==0 && window.commits==0);
 window.held=false;assert(window.set(true,res,false));
 assert(window.m_eglContext.swaps==1 && window.commits==1);
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),
                '-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_native_2d_mode_is_admitted_and_stereo_is_excluded(self):
        method=body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                    'bool CWinSystemGbmGLESContext::CB1ModeCanJoin(')
        program=r'''
#include "rendering/RenderSystemTypes.h"
#include <cassert>
#include <cmath>
#include <memory>
#include <optional>
struct RESOLUTION_INFO {int iWidth=3840,iHeight=2160,dwFlags=0; float fRefreshRate=60;};
constexpr int D3DPRESENTFLAG_MODE3DSBS=1,D3DPRESENTFLAG_MODE3DTB=2;
struct Base {virtual ~Base()=default;};
struct Crtc {std::optional<int> GetPropertyValue(const char*) const {return 1;}};
struct CDRMAtomic:Base {
 Crtc crtc; const Crtc* GetCrtc() const {return &crtc;}
 bool HasPendingCB1Page() const {return false;}
 bool IsSelectedModeCommitted() const {return true;}
 RESOLUTION_INFO GetCurrentMode() const {return {};}
};
struct Gfx {RenderStereoMode mode=RenderStereoMode::OFF; RenderStereoMode GetStereoMode() const {return mode;}};
struct Window {
 std::shared_ptr<Base> m_DRM=std::make_shared<CDRMAtomic>();
 int m_nWidth=3840,m_nHeight=2160; Gfx gfx;
 const Gfx& GetGfxContext() const {return gfx;}
 bool joins(const RESOLUTION_INFO& res) const METHOD
};
int main() {
 Window window; RESOLUTION_INFO target; target.fRefreshRate=24;
 assert(window.joins(target));
 window.gfx.mode=RenderStereoMode::MONO; assert(!window.joins(target));
 window.gfx.mode=RenderStereoMode::SPLIT_HORIZONTAL; assert(!window.joins(target));
 window.gfx.mode=RenderStereoMode::OFF;
 target.dwFlags=D3DPRESENTFLAG_MODE3DSBS; assert(!window.joins(target));
 target.dwFlags=0; target.fRefreshRate=60; assert(!window.joins(target));
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_selected_mode_can_prepare_before_its_first_atomic_commit(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        method=body(source,'bool CWinSystemGbmGLESContext::BeginDVBridge()')
        gate='auto drm ='+method.split('auto drm =',1)[1].split('CDVWindowRetirement::PollOnce();',1)[0]
        program=r'''
#include "ModeChangeHold.h"
#include <cassert>
#include <memory>
using namespace KODI::WINDOWING::GBM;
struct CDRMAtomic { bool committed=false; bool IsSelectedModeCommitted() const {return committed;} };
struct Window {
 std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
 CModeChangeHold m_modeHold;
 bool begin() { auto failure=[](const char*){return false;}; GATE return true; }
};
int main() {
 Window window; assert(!window.begin());
 window.m_modeHold.Start(0); assert(window.begin());
 window.m_modeHold.Cancel(); assert(!window.begin());
 window.m_DRM->committed=true; assert(window.begin());
 window.m_DRM.reset(); assert(!window.begin());
}
'''.replace('GATE',gate)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_plain_completed_present_stall_thresholds(self):
        self.assertTrue((TREE/'xbmc/windowing/gbm/DVPresentStall.h').is_file(),
                        'completed presentation stall policy is missing')
        program=r'''
#include "DVPresentStall.h"
#include <cassert>
using namespace KODI::WINDOWING::GBM;
int main() {
 CDVPresentStall stall;
 using V=CDVPresentStall::Verdict;
 assert(stall.Presented(false,10000)==V::NONE);
 assert(stall.Presented(true,1999)==V::NONE);
 assert(stall.Presented(true,2000)==V::STALLED);
 assert(stall.Presented(true,40)==V::NONE && stall.Stalls()==0);
 assert(stall.Presented(true,3000)==V::STALLED);
 assert(stall.Presented(true,3000)==V::GIVE_UP);
 assert(stall.Presented(true,5000)==V::GIVE_UP);
 stall.Reset(); assert(stall.Stalls()==0);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_deadline_cancellation_and_balanced_notifications(self):
        self.assertTrue((TREE/'xbmc/windowing/gbm/ModeChangeHold.h').is_file(),
                        'coherent mode-change policy is missing')
        program=r'''
#include "ModeChangeHold.h"
#include <cassert>
using namespace KODI::WINDOWING::GBM;
int main() {
 CModeChangeHold hold;
 CModeChangeHold::Change change{true,true,true,false,false,false,true};
 assert(CModeChangeHold::StartHolds(CModeChangeHold::Video::NATIVE_DV,change));
 assert(!CModeChangeHold::StartHolds(CModeChangeHold::Video::ORDINARY,change));
 change.sameWindow=false;
 assert(!CModeChangeHold::StartHolds(CModeChangeHold::Video::HDR,change));
 hold.Start(100); assert(!hold.Commits(3099)); assert(hold.Commits(3100));
 assert(hold.Take().second==CModeChangeHold::End::DEADLINE);
 hold.Start(100); assert(hold.Configured() && hold.Commits(101));
 assert(hold.Take().second==CModeChangeHold::End::CONFIGURED);
 hold.Stop(200); assert(!hold.Commits(2199)); assert(hold.ModeChange());
 assert(hold.Take().second==CModeChangeHold::End::MODE);
 hold.Start(0); assert(hold.Cancel()); assert(hold.Commits(1));
 CHeldModeAnnouncement announcement;
 announcement.Held(); assert(announcement.Before(true));
 announcement.After(false,true); assert(!announcement.Before(true));
 assert(announcement.Before(false)); announcement.After(true,false);
 assert(!announcement.Before(false));
 announcement.Held(); announcement.Dropped(); assert(!announcement.Before(true));
 announcement.Held(); assert(announcement.Before(true)); announcement.After(true,true);
 assert(!announcement.Before(true));
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc/windowing/gbm'),str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
