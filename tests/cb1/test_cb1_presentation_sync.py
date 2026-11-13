"""CB1 asynchronous presentation keeps the shown picture on the audio clock.

The shipped PrepareNextRender and UpdateDisplayLatency run against a simulated
display: each refresh selects a picture, the picture reaches the screen a fixed
number of refreshes later and its KMS completion is reported back. The test
compares the picture on screen with the audio clock at each refresh.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


def shipped(relative):
    return (TREE / relative).read_text()


HARNESS = r'''
#define HAVE_DVBRIDGE 1
#define CB1_HAS_HDR10_AI 1
#include <cassert>
#define CWinSystemGbmDVContext CWinSystemGbmGLESContext  // GL/GLES alias in the tree
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <optional>
#include <random>
#include <utility>
#include <vector>
#include <atomic>
constexpr double DVD_NOPTS_VALUE=-1e20, DVD_TIME_BASE=1e6;
constexpr double DVD_MSEC_TO_TIME(double x){return x*DVD_TIME_BASE/1000;}
constexpr int PRESENT_READY=0,PRESENT_IDLE=1,PRESENT_FLIP=2,PRESENT_FRAME=3;
constexpr int PRESENT_METHOD_SINGLE=0,FS_NONE=0,LOGERROR=0,LOGDEBUG=0,LOGAVTIMING=0;
struct CLog {template<class...T> static void Log(T...){} template<class...T> static void LogFC(T...){} };
uint64_t g_nowNs=1;
PRESENTATION
namespace DVBRIDGE {
inline uint64_t MonotonicNowNs(){return g_nowNs;}
HDR10_SOURCE_MODE
struct Preferences {HDR10SourceMode hdr10Source=HDR10SourceMode::Native;};
inline Preferences FrameOutputSettings(bool=false,bool=false){return {};}
}
struct Clock {
 double now=0,adjust=0;
 double GetClock(){return now;}
 double GetClockSpeed(){return 1;}
 bool IsPaused(){return false;}
 void SetVsyncAdjust(double value){adjust=value;}
};
struct Gfx {double refresh=24,latencyMs=125;
 double GetFPS(){return refresh;} float GetDisplayLatency(){return float(latencyMs);}};
struct Window {virtual ~Window()=default;Gfx gfx;Gfx& GetGfxContext(){return gfx;}
 float GetFrameLatencyAdjustment(){return 0;}};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext:Window {
 std::optional<double> age;std::optional<std::pair<double,uint64_t>> presented;
 bool CB1AsyncPlayback(){return true;}
 std::optional<double> CB1PresentationAge(){return age;}
 std::optional<std::pair<double,uint64_t>> CB1PresentedPicture(){return presented;}
};
}
inline KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker {static Window* GetWinSystem(){return &window;}};
struct Renderer {bool HDR10AILookahead(){return false;} bool VideoBypassesFramebuffer(){return false;}};
struct Port {void UpdateRenderBuffers(size_t,size_t,size_t){}};
struct Event {void notifyAll(){}};
struct CRenderManager {
 enum class StreamHdrType {HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
 struct ConfigPicture {StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;} m_picture;
 Renderer renderer;Renderer* m_pRenderer=&renderer;
 Port port;Port* m_playerPort=&port;
 Clock m_dvdClock;
 struct Sync {bool m_enabled=false,m_cb1Phase=false;double m_error=0,m_syncOffset=0;int m_errCount=0;
  DVBRIDGE::PresentationLatency m_cb1Latency;bool m_cb1LatencyActive=false;} m_clockSync;
 struct Picture {double pts=0,duration=0;int presentmethod=0,presentfield=0;} m_Queue[8];
 std::deque<int> m_queued,m_discard,m_free;
 bool m_aiQueueReady=true,m_showVideo=true,m_aiFullscreenRequested=false,m_aiGuiReady=true;
 bool m_cb1PresentPending=false;
 double m_aiStartPts=DVD_NOPTS_VALUE,m_displayLatency=0,m_presentpts=0,m_latencyTweak=0;
 float m_fps=24;
 std::atomic_int m_videoDelay{0};
 int m_presentsource=0,m_presentsourcePast=-1,m_presentstep=PRESENT_READY,m_lateframes=0,m_QueueSkip=0;
 bool m_forceNext=false;Event m_presentevent;
 void UpdateDisplayLatency();
 void PrepareNextRender();
};
void CRenderManager::UpdateDisplayLatency()
LATENCY
void CRenderManager::PrepareNextRender()
FUNCTION

struct Scenario {
 double refresh,fps;       // display refresh and source frame rate
 double startupLagMs=0;    // audio clock already running when the first picture is queued
 double overload=0;        // probability that a picture reaches the screen one refresh late
 int depth=2;              // refreshes between selection and scanout
 double reportedLatencyMs=0; // 0: the configured CB1 one-ahead estimate
 double startupPhaseErrorMs=0; // refresh-phase anchor error during the first two seconds
};
struct Result {double meanMs,worstLateMs,worstEarlyMs;int skipped;};

// Error at each refresh: shown picture timestamp minus heard audio clock (negative: video late).
Result Run(const Scenario& s,int refreshes,int settle){
 window=KODI::WINDOWING::GBM::CWinSystemGbmGLESContext{};
 window.gfx.refresh=s.refresh;
 window.gfx.latencyMs=s.reportedLatencyMs?s.reportedLatencyMs:
     1000/s.refresh+1000/std::min(s.fps,s.refresh);
 CRenderManager r;r.m_fps=float(s.fps);
 const double ratio=s.refresh>s.fps?s.refresh/s.fps:s.fps/s.refresh;
 r.m_clockSync.m_enabled=std::abs(std::round(ratio)-ratio)<0.0005;
 const double period=1e6/s.refresh,frame=1e6/s.fps,selectDelay=300;
 r.m_Queue[0].pts=-frame;r.m_Queue[0].duration=frame;
 for(int i=1;i<8;++i)r.m_free.push_back(i);
 long next=0;std::mt19937 random(7);std::uniform_real_distribution<double> uniform(0,1);
 std::vector<std::pair<long,double>> scheduled; // refresh index, picture
 double shown=-frame;long lastSlot=-1;std::optional<std::pair<double,uint64_t>> completed;
 double sum=0,late=0,early=-1e9;int samples=0,skipped=0;double previous=-frame;
 for(long k=0;k<refreshes;++k){
  const double wall=k*period;
  // Scanout at refresh k: the latest picture whose commit completed by now.
  for(auto& [slot,pts]:scheduled)if(slot==k){shown=pts;completed=std::make_pair(pts,uint64_t((wall+1)*1000));}
  if(k>=settle){
   const double error=shown-(wall+s.startupLagMs*1000+r.m_dvdClock.adjust);
   sum+=error;++samples;late=std::min(late,error);early=std::max(early,error);
  }
  if(shown-previous>frame*1.5 && k>=settle)++skipped;
  previous=shown;
  while(!r.m_discard.empty()){r.m_free.push_back(r.m_discard.front());r.m_discard.pop_front();}
  while(r.m_queued.size()<3 && !r.m_free.empty()){
   const int slot=r.m_free.front();r.m_free.pop_front();
   r.m_Queue[slot].pts=next++*frame;r.m_Queue[slot].duration=frame;r.m_queued.push_back(slot);
  }
  g_nowNs=uint64_t((wall+selectDelay)*1000);
  r.m_dvdClock.now=wall+selectDelay+s.startupLagMs*1000;
  const double phaseError=k<2*s.refresh?s.startupPhaseErrorMs*1000:0;
  window.age=completed?std::optional<double>(selectDelay+phaseError):std::nullopt;
  window.presented=completed;
  r.m_presentstep=PRESENT_READY;
  r.PrepareNextRender();
  if(r.m_presentstep==PRESENT_FLIP){
   const long slot=std::max(k+s.depth+(uniform(random)<s.overload?1:0),lastSlot+1);
   lastSlot=slot;scheduled.emplace_back(slot,r.m_Queue[r.m_presentsource].pts);
  }
 }
 return {sum/samples/1000,late/1000,early/1000,skipped};
}
int main(){
 TESTS
}
'''


def program(tests):
    presentation = shipped('xbmc/utils/DVBridgePresentation.h')
    presentation = presentation.replace('inline uint64_t MonotonicNowNs()',
                                        'inline uint64_t SystemMonotonicNowNs()')
    manager = shipped('xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp')
    source_mode = re.search(r'enum class HDR10SourceMode[^;]+;',
        shipped('xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h')).group()
    return (HARNESS.replace('PRESENTATION', presentation)
            .replace('HDR10_SOURCE_MODE', source_mode)
            .replace('LATENCY', body(manager, 'void CRenderManager::UpdateDisplayLatency()'))
            .replace('FUNCTION', body(manager, 'void CRenderManager::PrepareNextRender()'))
            .replace('TESTS', tests))


def run(tests):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'test.cpp').write_text(program(tests))
        build = subprocess.run(['c++', '-std=c++20', '-O1', str(root / 'test.cpp'), '-o',
                                str(root / 'test')], capture_output=True, text=True)
        if build.returncode:
            raise AssertionError(build.stderr)
        return subprocess.run([str(root / 'test')], capture_output=True, text=True)


CHECK = r'''
 // Bounds: lateness in source pictures, earliness in display refreshes, 2 ms scheduling jitter.
 auto check=[](const char* name,Scenario s,double lateFrames,double earlyRefreshes,int maxSkips){
  const double frame=1000/s.fps,period=1000/s.refresh;
  const auto r=Run(s,s.refresh*60,s.refresh*3);
  std::printf("%s mean=%.1f late=%.1f early=%.1f skipped=%d\n",name,r.meanMs,r.worstLateMs,r.worstEarlyMs,r.skipped);
  if(r.worstLateMs<-(lateFrames*frame+2) || r.worstEarlyMs>earlyRefreshes*period+2 ||
     r.meanMs<-(frame/2+period/4) || r.skipped>maxSkips){std::printf("FAILED %s\n",name);std::exit(1);}
 };
'''


class CB1PresentationSyncTests(unittest.TestCase):
    def assertRuns(self, tests):
        result = run(CHECK + tests)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_matched_rate_shows_the_current_picture(self):
        # 24p on 24 Hz and 60p on 60 Hz: the shown picture starts with its audio.
        self.assertRuns(r'''
 check("24p@24",{24,24},0.25,0.25,0);
 check("60p@60",{60,60},0.25,0.25,0);
 check("24p@24 deeper scanout",{24,24,0,0,3},0.25,0.25,0);
 check("24p@24 misreported latency",{24,24,0,0,2,125},0.25,0.25,0);''')

    def test_startup_lag_is_recovered(self):
        # Dolby Vision activation lets audio run before the first picture is shown.
        self.assertRuns(r'''
 check("24p@24 startup 590 ms",{24,24,590},0.25,0.25,0);
 check("24p@24 startup one frame",{24,24,45},0.25,0.25,0);
 check("24p@24 startup phase error",{24,24,590,0,2,0,18},0.25,0.25,0);
 check("23.976p@24 startup 590 ms",{24,24000.0/1001,590},1.0,0.0,2);''')

    def test_unmatched_rates_stay_within_one_picture(self):
        # Without a matching refresh, the shown picture is valid within one refresh of scanout.
        self.assertRuns(r'''
 check("23.976p@24",{24,24000.0/1001},1.0,0.0,2);
 check("24p@60",{60,24},1.0,1.0,0);
 check("25p@60",{60,25},1.0,1.0,0);
 check("24p@50",{50,24},1.0,1.0,0);''')

    def test_overloaded_scanout_does_not_keep_a_frame_of_lag(self):
        # A GPU that sometimes misses its refresh may skip, but must not stay a picture late.
        self.assertRuns(r'''
 const auto r=Run({24,24,590,0.3},24*60,24*3);
 std::printf("overload mean=%.1f late=%.1f\n",r.meanMs,r.worstLateMs);
 if(r.meanMs< -1000.0/24/4 || r.worstLateMs< -1000.0/24){std::printf("FAILED overload\n");return 1;}''')

    def test_latency_uses_first_completed_scanout_and_ignores_stalls(self):
        result = run(r'''
 DVBRIDGE::PresentationLatency latency;
 const auto at=[](int picture){return 1000000ull*(picture+1);};
 const auto sample=[&](int picture,uint64_t delay){latency.Selected(picture,at(picture));latency.Completed(picture,at(picture)+delay);};
 assert(!latency.EstimateUs());
 for(int i=0;i<7;++i)sample(i,80000000);
 assert(!latency.EstimateUs());
 sample(7,80000000);
 assert(latency.EstimateUs() && std::abs(*latency.EstimateUs()-80000)<1);
 // A repeated scanout of the same picture and one stall do not move the median.
 latency.Completed(7,at(7)+120000000);
 sample(8,400000000);
 assert(std::abs(*latency.EstimateUs()-80000)<1);
 // Samples beyond the bound and unknown pictures are ignored.
 sample(9,900000000);
 latency.Completed(42,123456789);
 assert(std::abs(*latency.EstimateUs()-80000)<1);
 // A sustained change replaces the old delay.
 for(int i=10;i<30;++i)sample(i,125000000);
 assert(std::abs(*latency.EstimateUs()-125000)<1);
 latency.Reset();assert(!latency.EstimateUs());
 return 0;''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
