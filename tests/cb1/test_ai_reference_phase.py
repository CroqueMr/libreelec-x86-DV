"""Reference AI selects 30 FPS pictures on physical 60 Hz refresh boundaries."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AIReferencePhaseTests(unittest.TestCase):
    def test_reference_selection_does_not_start_halfway_through_refresh(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        function = body(source, 'void CRenderManager::PrepareNextRender()')
        source_mode = re.search(r'enum class HDR10SourceMode[^;]+;',
            (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()).group()
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
PRESENTATION
namespace DVBRIDGE {
inline uint64_t MonotonicNowNs(){return 1;}
HDR10_SOURCE_MODE
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::ReferenceDV;};
inline Preferences prefs;
inline Preferences plusPrefs{HDR10SourceMode::HDR10PlusDV};
inline Preferences FrameOutputSettings(bool plus=false,bool=false){return plus?plusPrefs:prefs;}
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
 bool async=true;std::optional<double> age=8387.119;
 bool CB1AsyncPlayback(){return async;}
 std::optional<double> CB1PresentationAge(){return age;}
 std::optional<std::pair<double,uint64_t>> CB1PresentedPicture(){return std::nullopt;}
};
}
inline KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker {static Window* GetWinSystem(){return &window;}};
struct Renderer {bool lookahead=true;bool HDR10AILookahead(){return lookahead;}
 bool VideoBypassesFramebuffer(){return false;}};
struct Port {void UpdateRenderBuffers(size_t,size_t,size_t){}};
struct Event {void notifyAll(){}};
struct CRenderManager {
 enum class StreamHdrType {HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
 struct ConfigPicture {StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;} m_picture;
 ConfigPicture* m_pConfigPicture=nullptr; // Configure has retired its temporary picture.
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 Port port;Port* m_playerPort=&port;
 Clock m_dvdClock;
 struct Sync {bool m_enabled=true,m_cb1Phase=true;double m_error=0,m_syncOffset=837.2486989247425;int m_errCount=31;
  DVBRIDGE::PresentationLatency m_cb1Latency;bool m_cb1LatencyActive=false;} m_clockSync;
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
 // Retained HDR10+ source stays phase-aligned after Configure releases its picture,
 // independently of all three plain-HDR10 choices.
 for(auto plain:{DVBRIDGE::HDR10SourceMode::Native,DVBRIDGE::HDR10SourceMode::ReferenceDV,
                 DVBRIDGE::HDR10SourceMode::EnhancedDV}){
  DVBRIDGE::prefs.hdr10Source=plain;
  window.age=8387.119;CRenderManager guidedHalfway;
  guidedHalfway.m_picture.hdrType=CRenderManager::StreamHdrType::HDR_TYPE_HDR10PLUS;
  assert(!guidedHalfway.m_pConfigPicture);
  guidedHalfway.PrepareNextRender();
  assert(guidedHalfway.m_presentstep==PRESENT_READY && guidedHalfway.m_queued.front()==2);
  window.age=16666.666666666668;CRenderManager guidedBoundary;
  guidedBoundary.m_picture.hdrType=CRenderManager::StreamHdrType::HDR_TYPE_HDR10PLUS;
  guidedBoundary.m_dvdClock.now+=8279.547666666668;guidedBoundary.PrepareNextRender();
  assert(guidedBoundary.m_presentstep==PRESENT_FLIP && guidedBoundary.m_presentsource==2);
 }
 // Outside the AI reference phase, a picture after the refresh midpoint waits for its refresh.
 window.age=8387.119;
 for(auto mode:{DVBRIDGE::HDR10SourceMode::Native,DVBRIDGE::HDR10SourceMode::EnhancedDV}){
   DVBRIDGE::prefs.hdr10Source=mode;CRenderManager other;
   other.PrepareNextRender();assert(other.m_presentstep==PRESENT_READY && other.m_queued.front()==2);
 }
 DVBRIDGE::prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::ReferenceDV;
 CRenderManager authored;authored.renderer.lookahead=false;
 authored.PrepareNextRender();assert(authored.m_presentstep==PRESENT_READY);
 CRenderManager matched;matched.m_fps=60;
 matched.PrepareNextRender();assert(matched.m_presentstep==PRESENT_READY);
 window.age.reset();CRenderManager missing;
 missing.PrepareNextRender();assert(missing.m_presentstep==PRESENT_READY);
 window.age=8387.119;CRenderManager paused;paused.m_dvdClock.paused=true;
 paused.PrepareNextRender();assert(paused.m_presentstep==PRESENT_READY);
 // The same picture is presented once its refresh midpoint is reached.
 CRenderManager due;due.renderer.lookahead=false;due.m_dvdClock.now+=17000;
 due.PrepareNextRender();assert(due.m_presentstep==PRESENT_FLIP && due.m_presentsource==2);
 // CB1 one-ahead pictures use the same refresh-midpoint admission as Kodi on every driver.
 const auto edge=[] {
   CRenderManager r;r.renderer.lookahead=false;r.m_fps=60;r.m_displayLatency=0;
   r.m_dvdClock.now=0;r.m_clockSync.m_syncOffset=0;
   r.m_Queue[2].pts=25001;r.m_Queue[3].pts=50000;
   return r;
 };
 for(int scenario=0;scenario<7;++scenario){
   window.age=0;window.async=true;auto other=edge();
   if(scenario==1)window.async=false;
   if(scenario==2)window.age.reset();
   if(scenario==3)other.m_fps=30;
   if(scenario==4)other.m_dvdClock.paused=true;
   if(scenario==5)other.m_clockSync.m_enabled=false;
   if(scenario==6)other.m_Queue[1].presentfield=1;
   other.PrepareNextRender();
   assert(other.m_presentstep==PRESENT_READY && other.m_queued.front()==2);
 }
 // Catch-up uses the admission deadline, including latency, but not an old edge's age.
 // At 60 Hz, two queued pictures are overdue; the fourth is still in the future.
 for(double age:{0.0,8333.333333333}){
   window.async=true;window.age=age;
   CRenderManager delayed;delayed.renderer.lookahead=false;delayed.m_fps=60;
   delayed.m_dvdClock.now=1000000;delayed.m_displayLatency=33333.333333333;
   delayed.m_clockSync.m_syncOffset=0;delayed.m_queued={2,3,4};
   delayed.m_Queue[2].pts=983333.333333333;
   delayed.m_Queue[3].pts=1000000;
   delayed.m_Queue[4].pts=1083333.333333333;
   delayed.PrepareNextRender();
   assert(delayed.m_presentsource==3 && delayed.m_queued.front()==4);
 }
 // With an anchored refresh phase, a picture one frame behind is replaced at once.
 // Without it, Kodi's hysteresis keeps the picture until lateness is sustained.
 window.async=true;window.age=8333.333333333;
 const auto behind=[](int lateframes,bool anchored) {
   CRenderManager r;r.renderer.lookahead=false;r.m_fps=60;r.m_lateframes=lateframes;
   r.m_dvdClock.now=1000000;r.m_displayLatency=33334;r.m_clockSync.m_enabled=anchored;
   r.m_clockSync.m_syncOffset=0;r.m_queued={2,3,4};
   r.m_Queue[2].pts=1016667;r.m_Queue[3].pts=1033333;r.m_Queue[4].pts=1050000;
   r.PrepareNextRender();
   return r;
 };
 const auto anchored=behind(0,true);
 assert(anchored.m_presentsource==3 && anchored.m_queued.front()==4);
 const auto first=behind(0,false);
 assert(first.m_presentsource==2 && first.m_lateframes==1);
 const auto sustained=behind(7,false);
 assert(sustained.m_presentsource==3 && sustained.m_queued.front()==4);
 // A current presentation anchor must not postpone ordinary, async-off selection.
 window.async=false;window.age=8333.333333333;
 CRenderManager vanilla;vanilla.renderer.lookahead=false;vanilla.m_fps=60;
 vanilla.m_dvdClock.now=1000000;vanilla.m_displayLatency=33333.333333333;
 vanilla.m_clockSync.m_syncOffset=0;vanilla.m_queued={2,3,4};
 vanilla.m_Queue[2].pts=983333.333333333;vanilla.m_Queue[3].pts=1000000;
 vanilla.m_Queue[4].pts=1083333.333333333;
 vanilla.PrepareNextRender();
 assert(vanilla.m_presentsource==3 && vanilla.m_queued.front()==4);
}
'''.replace('FUNCTION', function).replace('HDR10_SOURCE_MODE', source_mode).replace(
            'PRESENTATION', (TREE/'xbmc/utils/DVBridgePresentation.h').read_text().replace(
                'inline uint64_t MonotonicNowNs()', 'inline uint64_t SystemMonotonicNowNs()'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'), '-o',
                                    str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
