"""Read-only witnesses at the real VAAPI timeout and decoder recovery boundaries."""
import unittest
import test_diagnostics_runtime as runtime


PRELUDE = r'''
#define HAVE_DVBRIDGE
#define CB1_HAS_HDR10_AI
#include <fmt/format.h>
#include <cassert>
#include <string>
#include <vector>
#include <cstdint>
constexpr int LOGINFO=1,LOGWARNING=2,LOGERROR=3,LOGDEBUG=4;
struct CLog {template<class...T>static void Log(T...) {}};
namespace DVBRIDGE {
inline bool enabled=true;
bool DiagnosticsEnabled(){return enabled;}
inline std::vector<std::string> lines;
inline std::string failureStage;
template<class...T>bool DiagnosticLog(int,fmt::format_string<T...> f,T&&...a){
 lines.push_back(fmt::format(f,std::forward<T>(a)...));return true;}
template<class...T>void DiagnosticFailureLog(const char* stage,bool,int level,fmt::format_string<T...> f,T&&...a){
 failureStage=stage;DiagnosticLog(level,f,std::forward<T>(a)...);}
}
'''


class PlaybackStallDiagnostics(unittest.TestCase):
    def test_native_health_uses_current_worker_not_prior_cb1_flags(self):
        source = (runtime.TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        start = source.index('  if (DVBRIDGE::DiagnosticsEnabled()',
                             source.index('CVideoPlayerVideo::EOutputState CVideoPlayerVideo::OutputPicture('))
        health = source[start:source.index('  DVBRIDGE::StreamTelemetry::Counters(', start)]
        start = source.index('  m_diagnosticRender.Reset();', source.index('void CVideoPlayerVideo::OpenStream('))
        reset = source[start:source.index('#endif', start)]
        runtime.DiagnosticsRuntime.run_cpp(self, r'''
#include <fmt/format.h>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
constexpr int LOGINFO=1;
constexpr double DVD_NOPTS_VALUE=-1e20,DVD_TIME_BASE=1000000;
struct CLog {
 inline static std::vector<std::string> lines;
 template<class...T>static void Log(int,fmt::format_string<T...>f,T&&...a){
  lines.push_back(fmt::format(f,std::forward<T>(a)...));}
};
namespace StringUtils {
 template<class...T>auto Format(fmt::format_string<T...>f,T&&...a){return fmt::format(f,std::forward<T>(a)...);}
}
namespace DVBRIDGE {
 bool enabled=true;uint64_t now=1000;
 bool DiagnosticsEnabled(){return enabled;}
 uint64_t DiagnosticNowMs(){return now;}
}
struct CDVPlaybackInfo {inline static std::atomic<unsigned>presented{0};};
struct Worker {
 struct Sampler {unsigned samples=0,resets=0;bool available=false;
  void Reset(){++resets;samples=0;}
  std::optional<double> Sample(uint64_t window){assert(window==60000000000ULL);++samples;
   return available ? std::optional<double>{42.5} : std::nullopt;}}m_diagnosticRender;
 uint64_t m_diagnosticTime=999999,m_diagnosticPictures=99;
 int m_diagnosticDropped=20,m_diagnosticSkipped=20,m_diagnosticTransitions=20;
 int m_speed=1000,m_iDroppedFrames=3;double m_fFrameRate=25;
 std::atomic<bool>m_stalled{false};
 struct Renderer{int skipped=2;int GetSkippedFrames(){return skipped;}}m_renderManager;
 struct ProcessInfo{int GetLevelVQ(){return 50;}}m_processInfo;
 struct Queue{double GetTimeSize(){return 3;}}m_messageQueue;
 double GetVideoBitrate(){return 12500000;}
 struct Picture{double pts=4000000;}picture;
 void OpenStream(){@RESET@}
 void OutputPicture(){auto*pPicture=&picture;@HEALTH@}
};
void contains(const std::string&line,const char*part){assert(line.find(part)!=std::string::npos);}
int main(){
 using namespace DVBRIDGE;
 Worker native;native.OpenStream();native.OutputPicture();
 assert(CLog::lines.size()==1 && "Native flags0 must emit current-worker health without CB1 priming");
 const auto first=CLog::lines.back();
 for(auto part:{"interval_ms=0 ","output_attempts=1 ","source_fps=25.000 ","speed=1000 ",
               "stalled=false ","pts_s=4.000 ","drop_total=3 ","skip_total=2 ",
               "drop_delta=3 ","skip_delta=2 ","counters_reset=false ","video_queue_pct=50 ",
               "video_queue_s=3.000 ","bitrate_mbps=12.50 ","render_avg_pct=unavailable ",
               "transitions=0 ","pts_valid=true ","attempts are not display flips"})contains(first,part);
 assert(CDVPlaybackInfo::presented==0 && native.m_diagnosticRender.samples==1);
 now=10999;native.OutputPicture();assert(CLog::lines.size()==1); // Exact boundary not reached.
 now=11000;native.picture.pts=14000000;native.m_iDroppedFrames=4;
 native.m_renderManager.skipped=5;native.m_diagnosticTransitions=3;
 native.m_speed=0;native.m_stalled=true;native.m_diagnosticRender.available=true;
 native.OutputPicture();assert(CLog::lines.size()==2);
 for(auto part:{"interval_ms=10000 ","output_attempts=2 ","speed=0 ","stalled=true ",
               "pts_s=14.000 ","drop_delta=1 ","skip_delta=3 ","counters_reset=false ",
               "render_avg_pct=42.5 ","transitions=3 ","pts_valid=true "})contains(CLog::lines.back(),part);
 assert(native.m_speed==0 && native.m_stalled && native.m_diagnosticTransitions==0);
 native.OutputPicture();assert(CLog::lines.size()==2 && native.m_diagnosticRender.samples==2);
 now=21000;native.m_iDroppedFrames=0;native.m_renderManager.skipped=0;
 native.picture.pts=DVD_NOPTS_VALUE;native.OutputPicture();
 for(auto part:{"counters_reset=true ","drop_delta=0 ","skip_delta=0 ","pts_valid=false "})
  contains(CLog::lines.back(),part);
 const auto beforeDisabled=CLog::lines.size();const auto beforeSamples=native.m_diagnosticRender.samples;
 const auto beforeTime=native.m_diagnosticTime;const auto beforePictures=native.m_diagnosticPictures;
 enabled=false;now=50000;native.OutputPicture();
 assert(CLog::lines.size()==beforeDisabled && native.m_diagnosticRender.samples==beforeSamples);
 assert(native.m_diagnosticTime==beforeTime && native.m_diagnosticPictures==beforePictures);
 enabled=true;now=60000;native.OpenStream();native.OutputPicture();
 contains(CLog::lines.back(),"interval_ms=0 ");contains(CLog::lines.back(),"counters_reset=false ");
 assert(native.m_diagnosticRender.resets==2 && native.m_diagnosticRender.samples==1);
 assert(native.m_diagnosticTime==60000 && native.m_diagnosticPictures==0);
 // Accepted CB1 bits and stale bits must not change the same worker's diagnostics.
 for(unsigned flags:{0u,1u,8u,32u,63u}){
  CDVPlaybackInfo::presented=flags;now=1000;Worker current;current.OpenStream();current.OutputPicture();
  assert(CLog::lines.back()==first && CDVPlaybackInfo::presented==flags);
 }
 // No OutputPicture invocation means no synthetic heartbeat, including after worker lifetime.
 const auto stopped=CLog::lines.size();now+=60000;{Worker idle;idle.OpenStream();}
 assert(CLog::lines.size()==stopped);
}
'''.replace('@RESET@',reset).replace('@HEALTH@',health))

    def test_pause_is_visible_without_enabling_kodi_debug(self):
        text = (runtime.TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        start = text.index('      m_paused = std::static_pointer_cast<CDVDMsgBool>')
        end = text.index('    }',start)
        runtime.DiagnosticsRuntime.run_cpp(self, PRELUDE+r'''
#include <memory>
struct CDVDMsgBool{bool m_value;};
void Pause(bool value){
 auto pMsg=std::make_shared<CDVDMsgBool>(value);
 bool m_paused=!value;
 BLOCK
 assert(m_paused==value);
}
int main(){
 Pause(true);Pause(false);assert(DVBRIDGE::lines.size()==2 && "Missing native pause/resume witness");
 assert(DVBRIDGE::lines.front().find("paused=true")!=std::string::npos);
 assert(DVBRIDGE::lines.back().find("paused=false")!=std::string::npos);
 DVBRIDGE::enabled=false;Pause(true);assert(DVBRIDGE::lines.size()==2);
}
'''.replace('BLOCK',text[start:end]))

    def test_timeout_reports_render_pressure_not_only_free_decode_surfaces(self):
        text = (runtime.TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/VAAPI.cpp').read_text()
        start = text.index('  CLog::Log(LOGERROR,\n            "VAAPI::{} - timed out')
        end = text.index('  m_DisplayState = VAAPI_ERROR;', start)
        runtime.DiagnosticsRuntime.run_cpp(self, PRELUDE+r'''
void Timeout(){
 uint16_t decoded=0,processed=4,render=77;bool vpp=false;
 struct Stats{void Get(uint16_t&d,uint16_t&p,uint16_t&r,bool&v){d=1;p=3;r=6;v=true;}}m_bufferStats;
 struct Surfaces{bool HasFree(){return true;}}m_videoSurfaces;
 struct Config{unsigned maxReferences=48,renderPictures=38;}m_vaapiConfig;
 unsigned m_hdr10AIBuffers=37,m_codecControl=16;bool drain=true;
 void* m_presentPicture=&m_vaapiConfig;
 (void)m_bufferStats;(void)m_hdr10AIBuffers;(void)m_codecControl;(void)drain;(void)m_presentPicture;
 BLOCK
 assert(decoded==0 && processed==4 && render==77 && !vpp);
 assert(m_vaapiConfig.maxReferences==48 && m_vaapiConfig.renderPictures==38);
}
int main(){
 Timeout();assert(DVBRIDGE::lines.size()==1 && "Missing VAAPI output-pressure witness");
 assert(DVBRIDGE::failureStage=="vaapi-output-timeout" && "Timeout must use first-failure admission");
 const auto& line=DVBRIDGE::lines.back();
 for(auto part:{"decoded=1","processed=3","render=6","decode_free=true","vpp=true",
                "decode_limit=48","render_limit=38","ai_buffers=37","present=true","drain=true"})
  assert(line.find(part)!=std::string::npos);
 DVBRIDGE::enabled=false;Timeout();assert(DVBRIDGE::lines.size()==1);
}
'''.replace('BLOCK',text[start:end]))

    def test_recovery_reports_replay_context_without_reordering_packets(self):
        text = (runtime.TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        start = text.index('  if (decoderState == CDVDVideoCodec::VC_REOPEN)')
        start = text.index('{',start)+1
        end = text.index('    while (!m_packets.empty())',start)
        runtime.DiagnosticsRuntime.run_cpp(self, PRELUDE+r'''
void Reopen(){
 std::vector<int> m_packets{4,7,9};bool m_paused=true;int m_speed=0,m_syncState=2;
 struct Extra{size_t GetSize(){return 83;}};
 struct Hints{int codec=226;Extra extradata;}m_hints;
 BLOCK
 assert((m_packets==std::vector<int>{4,7,9}) && m_paused && m_speed==0 && m_syncState==2);
}
int main(){
 Reopen();assert(DVBRIDGE::lines.size()==1 && "Missing decoder replay witness");
 for(auto part:{"codec=226","extradata=83","replay_packets=3","paused=true","speed=0","sync=2"})
  assert(DVBRIDGE::lines.back().find(part)!=std::string::npos);
 DVBRIDGE::enabled=false;Reopen();assert(DVBRIDGE::lines.size()==1);
}
'''.replace('BLOCK',text[start:end]))

    def test_uninit_reports_retained_output_before_releasing_queues(self):
        text = (runtime.TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/VAAPI.cpp').read_text()
        start = text.index('bool COutput::Uninit()')
        start = text.index('{',start)+1
        end = text.index('  ProcessSyncPicture();',start)
        runtime.DiagnosticsRuntime.run_cpp(self, PRELUDE+r'''
void Uninit(bool withPool){
 struct Pool{std::vector<int> decodedPics{1,2},processedPics{3,4,5},processedPicsAway{6,7,8,9};
  bool HasFree(){return false;}}pool;
 auto* m_bufferPool=withPool?&pool:nullptr;
 std::vector<int> m_discardedPostprocs{10};void* m_pp=&pool;
 (void)m_bufferPool;(void)m_pp;
 BLOCK
 assert(pool.decodedPics.size()==2 && pool.processedPics.size()==3 && pool.processedPicsAway.size()==4);
}
int main(){
 Uninit(true);assert(DVBRIDGE::lines.size()==1 && "Missing output teardown witness");
 for(auto part:{"decoded=2","processed=3","held=4","render_free=false","postproc=true","discarded=1"})
  assert(DVBRIDGE::lines.back().find(part)!=std::string::npos);
 Uninit(false);DVBRIDGE::enabled=false;Uninit(true);assert(DVBRIDGE::lines.size()==1);
}
'''.replace('BLOCK',text[start:end]))


if __name__ == '__main__':
    unittest.main()
