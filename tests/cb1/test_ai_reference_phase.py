"""Reference AI selects 30 FPS pictures on physical 60 Hz refresh boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AIReferencePhaseTests(unittest.TestCase):
    def test_native_edge_is_only_used_by_the_affected_driver_and_circuits(self):
        header = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.h').read_text()
        predicate = body(header, 'bool CB1NativeAsyncPlayback() const')
        program = r'''
#include <cassert>
constexpr int QUIRK_CB1_NATIVE_EDGE=2;
constexpr int DVBRIDGE_MODE_STANDARD=0,DVBRIDGE_MODE_MASTER_REFERENCE=4;
struct DRM {bool affected=false;bool HasQuirk(int) const {return affected;}};
struct Bridge {bool advanced=false;bool Advanced() const {return advanced;}};
struct Window {
 DRM drm,*m_DRM=&drm;Bridge bridge,*m_dvBridge=&bridge;
 bool async=true,m_hdrConversion=false;
 struct Selection {struct Policy {int mode=0;} policy;} m_dvSelection;
 bool CB1AsyncPlayback() const {return async;}
 bool CB1NativeAsyncPlayback() const PREDICATE
};
int main(){
 Window w;assert(!w.CB1NativeAsyncPlayback());
 w.drm.affected=true;assert(w.CB1NativeAsyncPlayback());
 w.m_dvSelection.policy.mode=4;assert(w.CB1NativeAsyncPlayback());
 w.bridge.advanced=true;assert(!w.CB1NativeAsyncPlayback());
 w.bridge.advanced=false;w.m_hdrConversion=true;assert(!w.CB1NativeAsyncPlayback());
 w.m_hdrConversion=false;w.m_dvSelection.policy.mode=3;assert(!w.CB1NativeAsyncPlayback());
 w.m_dvSelection.policy.mode=0;w.async=false;assert(!w.CB1NativeAsyncPlayback());
 w.async=true;w.m_DRM=nullptr;assert(!w.CB1NativeAsyncPlayback());
}
'''.replace('PREDICATE', predicate)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],
                                   capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run = subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_reference_selection_does_not_start_halfway_through_refresh(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        function = body(source, 'void CRenderManager::PrepareNextRender()')
        program = r'''
#define HAVE_DVBRIDGE 1
#define CB1_HAS_HDR10_AI 1
#include <cassert>
#include <cmath>
#include <deque>
#include <optional>
constexpr double DVD_NOPTS_VALUE=-1e20, DVD_TIME_BASE=1e6;
constexpr int PRESENT_READY=0,PRESENT_IDLE=1,PRESENT_FLIP=2;
constexpr int PRESENT_METHOD_SINGLE=0,FS_NONE=0,LOGERROR=0,LOGDEBUG=0,LOGAVTIMING=0;
struct CLog {template<class...T> static void Log(T...){} template<class...T> static void LogFC(T...){} };
namespace DVBRIDGE {
enum class HDR10SourceMode {Native,ReferenceDV,EnhancedDV};
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;
inline Preferences FrameOutputSettings(){return prefs;}
}
struct Clock {
 double now=4625876.598333334;
 bool paused=false;
 double GetClock(){return now;}
 double GetClockSpeed(){return 1;}
 bool IsPaused(){return paused;}
 void SetVsyncAdjust(double){}
};
struct Gfx {double GetFPS(){return 60;}};
struct Window {virtual ~Window()=default;Gfx gfx;Gfx& GetGfxContext(){return gfx;}};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext:Window {
 bool async=true,native=false;std::optional<double> age=8387.119;
 bool CB1AsyncPlayback(){return async;}
 bool CB1NativeAsyncPlayback(){return async && native;}
 std::optional<double> CB1PresentationAge(){return age;}
};
}
inline KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker {static Window* GetWinSystem(){return &window;}};
struct Renderer {bool lookahead=true;bool HDR10AILookahead(){return lookahead;}
 bool VideoBypassesFramebuffer(){return false;}};
struct Port {void UpdateRenderBuffers(size_t,size_t,size_t){}};
struct Event {void notifyAll(){}};
struct CRenderManager {
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 Port port;Port* m_playerPort=&port;
 Clock m_dvdClock;
 struct Sync {bool m_enabled=true,m_cb1Phase=true;double m_error=0,m_syncOffset=837.2486989247425;int m_errCount=31;} m_clockSync;
 struct Picture {double pts=0,duration=33333.333;int presentmethod=0,presentfield=0;} m_Queue[8];
 std::deque<int> m_queued{2,3},m_discard,m_free;
 bool m_aiQueueReady=true,m_showVideo=true,m_aiFullscreenRequested=false,m_aiGuiReady=true;
 double m_aiStartPts=1000,m_displayLatency=50000,m_presentpts=0,m_fps=30;
 int m_presentsource=1,m_presentsourcePast=-1,m_presentstep=PRESENT_READY,m_lateframes=0,m_QueueSkip=0;
 bool m_forceNext=false;Event m_presentevent;
 void UpdateDisplayLatency(){}
 void PrepareNextRender();
 CRenderManager(){m_Queue[1].pts=4667000-33333.333;m_Queue[2].pts=4700000;m_Queue[3].pts=4733000;}
};
void CRenderManager::PrepareNextRender()
FUNCTION
int main(){
 CRenderManager halfway;
 halfway.PrepareNextRender();
 assert(halfway.m_presentstep==PRESENT_READY);
 assert(halfway.m_queued.front()==2);
 window.age=16666.666666666668;
 CRenderManager boundary;boundary.m_dvdClock.now+=8279.547666666668;
 boundary.PrepareNextRender();
 assert(boundary.m_presentstep==PRESENT_FLIP);
 assert(boundary.m_presentsource==2);
 // Other source modes, matched refresh, missing anchors and pause retain selection.
 window.age=8387.119;
 for(auto mode:{DVBRIDGE::HDR10SourceMode::Native,DVBRIDGE::HDR10SourceMode::EnhancedDV}){
   DVBRIDGE::prefs.hdr10Source=mode;CRenderManager other;
   other.PrepareNextRender();assert(other.m_presentstep==PRESENT_FLIP);
 }
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::ReferenceDV;
 CRenderManager authored;authored.renderer.lookahead=false;
 authored.PrepareNextRender();assert(authored.m_presentstep==PRESENT_FLIP);
 CRenderManager matched;matched.m_fps=60;
 matched.PrepareNextRender();assert(matched.m_presentstep==PRESENT_FLIP);
 window.age.reset();CRenderManager missing;
 missing.PrepareNextRender();assert(missing.m_presentstep==PRESENT_FLIP);
 window.age=8387.119;CRenderManager paused;paused.m_dvdClock.paused=true;
 paused.PrepareNextRender();assert(paused.m_presentstep==PRESENT_READY);
 // Authored matched-rate one-ahead pictures do not wait for the blend midpoint.
 const auto edge=[] {
   CRenderManager r;r.renderer.lookahead=false;r.m_fps=60;r.m_displayLatency=0;
   r.m_dvdClock.now=0;r.m_clockSync.m_syncOffset=0;
   r.m_Queue[2].pts=25001;r.m_Queue[3].pts=50000;
   return r;
 };
 window.age=0;window.native=true;
 auto native=edge();native.PrepareNextRender();
 assert(native.m_presentstep==PRESENT_FLIP && native.m_presentsource==2);
 assert(native.m_queued.front()==3 && native.m_QueueSkip==0);
 for(int scenario=0;scenario<7;++scenario){
   window.age=0;window.async=true;window.native=true;auto other=edge();
   if(scenario==0)window.native=false;
   if(scenario==1)window.async=false;
   if(scenario==2)window.age.reset();
   if(scenario==3)other.m_fps=30;
   if(scenario==4)other.m_dvdClock.paused=true;
   if(scenario==5)other.m_clockSync.m_enabled=false;
   if(scenario==6)other.m_Queue[1].presentfield=1;
   other.PrepareNextRender();
   assert(other.m_presentstep==PRESENT_READY && other.m_queued.front()==2);
 }
}
'''.replace('FUNCTION', function)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'), '-o',
                                    str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
