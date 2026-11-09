"""Kodi's display-reset pause must not consume the HDR10 AI computation budget."""
from pathlib import Path
import unittest
from test_ai_reentry import execute
from test_native_video_source import TREE, body


class AIRefreshDelayTests(unittest.TestCase):
    def test_native_display_reset_pauses_only_hdr10_ai_required_wait(self):
        prepare = body((TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text(),
                       'bool CWinSystemGbmGLESContext::PrepareHDR10AIQueue(')
        start = prepare.index('  auto decision = HDR10AISource::Decision::Native;')
        adapter = prepare[start:prepare.index('  if (decision == HDR10AISource::Decision::Prepare', start)]
        activation = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h').read_text()
        core = Path(__file__).resolve().parents[2]/'CB1/src'
        activation = activation.replace('#include "cb1_l1l3_model.h"',
                                        '#include "'+str(core/'cb1_l1l3_model.h')+'"')
        execute(r'''
ACTIVATION
#include <cassert>
struct cb1_ai_result{};
namespace DVBRIDGE {inline uint64_t now=0;uint64_t DiagnosticNowMs(){return now;}}
struct HDR10AISource {using Decision=DVBRIDGE::HDR10AIActivation::Decision;};
struct Context {
 DVBRIDGE::HDR10AIActivation activation;
 cb1_ai_identity id{7,1,9};cb1_ai_status status=CB1_AI_PENDING;
 Context(){activation.Begin(7,9,0);}
 bool Initialize(bool){return true;}
 HDR10AISource::Decision PrepareHDR10AIQueue(int,int,const char*,uint64_t now,bool,
                                           cb1_ai_result*,bool paused,uint64_t){
  activation.SetPaused(paused,now);
  return activation.Observe(status,id,now);
 }
 Context& HDR10AI(){return *this;}
 void RecordStatus(const char*,cb1_ai_status){assert(false);}
};
constexpr const char* CB1_L1L3_BUNDLE_DIR="unused";
enum class StreamHdrType {HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
struct Window {
 Context context;Context* m_dvContext=&context;
 bool m_dispReset=false;
 struct {StreamHdrType hdrType=StreamHdrType::HDR_TYPE_HDR10;}picture;
 HDR10AISource::Decision Tick(uint64_t now,bool paused=false){
  DVBRIDGE::now=now;int queue=0,preferences=0;bool end=false;uint64_t presentationDeadline=0;
  struct{bool isHLG;}caps{picture.hdrType==StreamHdrType::HDR_TYPE_HLG};
  ADAPTER
  return decision;
 }
};
int main(){
 using Decision=HDR10AISource::Decision;
 Window settling;settling.m_dispReset=true;
 assert(settling.Tick(10)==Decision::Wait);
 assert(settling.Tick(2510)==Decision::Wait);
 settling.m_dispReset=false;
 assert(settling.Tick(3010)==Decision::Wait);
 assert(settling.Tick(3999)==Decision::Wait);
 assert(settling.Tick(4000)==Decision::Native); // Still only 1000 ms of actual required wait.
 Window priming;assert(priming.Tick(999)==Decision::Wait);
 assert(priming.Tick(1000)==Decision::Native); // A stopped bootstrap clock is not a display reset.
 Window hlg;hlg.picture.hdrType=StreamHdrType::HDR_TYPE_HLG;hlg.m_dispReset=true;
 assert(hlg.Tick(0)==Decision::Wait);assert(hlg.Tick(2000)==Decision::Wait);hlg.m_dispReset=false;
 assert(hlg.Tick(3000)==Decision::Wait);assert(hlg.Tick(4000)==Decision::Native);
 Window guided;guided.picture.hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;guided.m_dispReset=true;
 assert(guided.Tick(1000)==Decision::Native); // Guided HDR10+ timing is unchanged.
 Window overlap;overlap.m_dispReset=true;assert(overlap.Tick(0)==Decision::Wait);
 assert(overlap.Tick(2500,true)==Decision::Wait);
 overlap.m_dispReset=false;assert(overlap.Tick(4000,true)==Decision::Wait);
 assert(overlap.Tick(5000)==Decision::Wait); // User pause still owns the clock after display reset.
 overlap.m_dispReset=true;assert(overlap.Tick(5200)==Decision::Wait);
 assert(overlap.Tick(8200)==Decision::Wait);
 overlap.m_dispReset=false;assert(overlap.Tick(8500)==Decision::Wait);
 assert(overlap.Tick(9299)==Decision::Wait);assert(overlap.Tick(9300)==Decision::Native);
 Window ready;ready.m_dispReset=true;ready.context.status=CB1_AI_READY;
 assert(ready.Tick(0)==Decision::Prepare); // Analysis may still finish during the display pause.
 Window stopped;stopped.m_dispReset=true;assert(stopped.Tick(0)==Decision::Wait);
 stopped.context.activation.Stop();assert(stopped.Tick(2500)==Decision::Ignore);
 stopped.context.activation.Begin(8,10,3000);stopped.m_dispReset=false;
 assert(stopped.Tick(3000)==Decision::Ignore); // Old prediction cannot cross a source change.
 stopped.context.id={8,1,10};assert(stopped.Tick(3999)==Decision::Wait);
 assert(stopped.Tick(4000)==Decision::Native);
}
'''.replace('ACTIVATION', activation).replace('ADAPTER', adapter))
