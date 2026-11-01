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
