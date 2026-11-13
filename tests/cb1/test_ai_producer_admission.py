"""A complete owned startup snapshot must yield before codec extraction blocks."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code
from test_native_video_source import body


class AIProducerAdmission(unittest.TestCase):
    def run_cpp(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'check.cpp').write_text(source)
            build=subprocess.run(['c++','-std=c++20',str(path/'check.cpp'),'-o',str(path/'check')],
                                 capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(path/'check')],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_valid_captured_horizon_not_raw_queue_size(self):
        capture=body(shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp'),
                     'HDR10AIQueuePreparation CLinuxRendererGLES::CaptureHDR10AIQueue(')
        at=capture.find('  const bool buffered =')
        calculation=(capture[at:capture.index('  const auto preferences =',at)] if at>=0 else
                     'const bool buffered=false;')
        self.run_cpp(r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <memory>
#include <vector>
struct Binding{unsigned stream=1,picture=1,revision=1;bool Valid()const{return stream&&picture&&revision;}};
struct Layer{Binding binding;double pts;std::shared_ptr<int>lease=std::make_shared<int>(1);};
bool covers(const std::vector<Layer>&layers,bool end=false,size_t queued=0){Binding binding;
 std::vector<int> queue(queued?queued:layers.size());
 @CALCULATION@
 return buffered;}
int main(){
 assert(covers({{{1,1,1},9.0},{{1,61,1},10.0}}));
 assert(!covers({{{1,1,1},9.0},{{1,60,1},9.983333}}));
 assert(covers({{{1,1,1},9.0}},true));
 assert(!covers({{{1,1,1},9.0}},true,2)); // EOF cannot validate a failed second import.
 assert(covers({{{1,1,1},9.0},{{1,61,1},10.0}},true,3)); // Complete horizon may be a valid prefix.
 assert(!covers({},true)); // EOF cannot manufacture a valid owned head.
 assert(!covers({{{2,1,1},9.0},{{2,61,1},10.0}}));
 assert(!covers({{{1,1,1},9.0},{{1,61,2},10.0}}));
 assert(!covers({{{1,1,1},9.0},{{1,61,1},NAN}},true));
 Layer unowned{{1,1,1},9.0};unowned.lease.reset();assert(!covers({unowned},true));
}
'''.replace('@CALCULATION@',calculation))

    def test_full_snapshot_yields_before_gui_ready_and_parent_resync(self):
        manager=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp')
        worker=shipped_code('xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp')
        process=body(worker,'void CVideoPlayerVideo::Process()')
        producer=('{return false;}' if 'bool CRenderManager::HDR10AIStartupBuffered()' not in manager else
                  body(manager,'bool CRenderManager::HDR10AIStartupBuffered()'))
        wrapper=re.search(r'  const auto processDecoderOutput = \[&\]\(\).*?\n  };',process,re.S)
        wrapper=wrapper[0] if wrapper else 'const auto processDecoderOutput=[&](){return ProcessDecoderOutput(frametime,pts);};'
        predicate=r'if \((?:ProcessDecoderOutput\(frametime, pts\)|processDecoderOutput\(\))\)'
        first=re.search(predicate,process)
        last=list(re.finditer(predicate,process))[-1]
        timeout=first[0]+' '+body(process[first.start():],first[0])
        packet=last[0]+' '+body(process[last.start():],last[0])
        extract=body(worker,'bool CVideoPlayerVideo::ProcessDecoderOutput(')
        extract=extract[:extract.index('\n  if (decoderState !=')]+ '\nreturn false;\n}'
        self.run_cpp(r'''
#define CB1_HAS_HDR10_AI 1
#include <cassert>
#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
using CCriticalSection=std::mutex;
constexpr double DVD_NOPTS_VALUE=-1e20;
enum{PRESENT_IDLE,PRESENT_READY,PRESENT_FRAME};
struct HDR10AIQueuePreparation {
 struct Outcome{bool ready,lookahead;};bool ready=false;
 std::function<Outcome()>execute;std::function<bool(const Outcome&)>publish;bool buffered=false;
};
struct Renderer{
 bool active=true,eligible=true,full=true,accept=true;
 std::function<void()>during;
 bool HDR10AILookahead(){return active;}bool HDR10AIQueueEligible(){return eligible;}
 HDR10AIQueuePreparation CaptureHDR10AIQueue(const std::deque<int>&,bool,bool,uint64_t){
 return {false,[this]{if(during)during();return HDR10AIQueuePreparation::Outcome{true,active};},
 [this](const auto&){return accept;},full};}
};
struct CRenderManager{
 Renderer renderer;Renderer*m_pRenderer=&renderer;CCriticalSection m_presentlock;
 bool m_showVideo=false,m_aiFullscreenRequested=true,m_aiGuiReady=false,m_aiFullscreenWanted=true;
 bool m_aiStartupBuffered=false,m_aiQueuePreparationStale=false,m_aiQueueReady=false,m_aiGUIOwnsRenderer=false,m_aiEnd=false;
 uint64_t m_aiQueueGeneration=1;int m_presentstep=PRESENT_READY;std::deque<int>m_queued{0,1};
 struct Slot{double pts=9000000,duration=16667;}m_Queue[2];
 double m_aiStartPts=DVD_NOPTS_VALUE;
 struct ClockSync{bool m_cb1Phase=false;void Reset(){}}m_clockSync;
 struct Clock{void SetVsyncAdjust(int){}}m_dvdClock;
 bool HDR10AIStartupBuffered() @PRODUCER@
 bool GetHDR10AIStartTime(double&pts) @START@
 double GetDelay(){return 0;}
 bool ExecuteHDR10AIQueuePreparation(const std::deque<int>&queue,bool paused,uint64_t deadline,
                                   std::unique_lock<CCriticalSection>&lock) @EXECUTE@
 void ResetHDR10AIQueue() @RESET@
 void Prepare(){std::unique_lock lock(m_presentlock);ExecuteHDR10AIQueuePreparation(m_queued,false,0,lock);}
};
struct IDVDStreamPlayer{enum{SYNC_STARTING,SYNC_WAITSYNC,SYNC_INSYNC};};
constexpr int VideoPlayer_VIDEO=1;
#define DVD_MSEC_TO_TIME(x) ((x)*1000)
struct SStartMsg{int player;double cachetime,cachetotal,timestamp;};
struct CDVDMsg{enum{PLAYER_STARTED};};
template<class T>struct CDVDMsgType{CDVDMsgType(int,const T&){}};
struct CDVDVideoCodec{
 enum VCReturn{VC_BUFFER};unsigned reads=0;bool blocks=true;
 VCReturn GetPicture(void*){++reads;if(blocks)throw std::runtime_error("codec entered full leased pool before startup sync");return VC_BUFFER;}
};
struct CVideoPlayerVideo{
 int m_syncState=IDVDStreamPlayer::SYNC_STARTING;CRenderManager&m_renderManager;
 CDVDVideoCodec codec;CDVDVideoCodec*m_pVideoCodec=&codec;
 struct Picture{std::string stereoMode="stereo";}m_picture;
 struct Parent{unsigned starts=0;template<class T>void Put(T){++starts;}}m_messageParent;
 void TryStartHDR10AI() @TRY_START@
 bool ProcessDecoderOutput(double&frametime,double&pts) @EXTRACT@
 bool Step(bool packet=false){double frametime=16667,pts=0;bool onlyPrioMsgs=false;
 @WRAPPER@
 do {if(packet){@PACKET@}else{@TIMEOUT@}}while(false);
 return onlyPrioMsgs;}
};
int main(){
 CRenderManager manager;CVideoPlayerVideo worker{IDVDStreamPlayer::SYNC_STARTING,manager};
 bool observed=false;
 manager.renderer.during=[&]{
   assert(!manager.m_aiGuiReady);observed=true;
   try{assert(worker.Step()&&worker.Step(true));}catch(...){assert(false&&"complete captured window must backpressure before GetPicture");}
   assert(worker.codec.reads==0); // Completeness is visible BEFORE execute returns / first page commits.
 };
 manager.Prepare();assert(observed&&manager.m_aiStartupBuffered);
 manager.m_aiGuiReady=true;worker.TryStartHDR10AI();
 assert(worker.m_syncState==IDVDStreamPlayer::SYNC_WAITSYNC&&worker.m_messageParent.starts==1);
 assert(worker.Step()&&worker.codec.reads==0); // Priority timeout BEFORE parent GENERAL_RESYNC.
 manager.m_showVideo=true;worker.m_syncState=IDVDStreamPlayer::SYNC_INSYNC;worker.codec.blocks=false;
 assert(!worker.Step()&&worker.codec.reads==1); // Steady extraction unchanged.
 manager.m_showVideo=false;worker.m_syncState=IDVDStreamPlayer::SYNC_STARTING;
 manager.renderer.during={};manager.renderer.full=false;manager.Prepare();
 assert(!manager.HDR10AIStartupBuffered());assert(!worker.Step(true)&&worker.codec.reads==2);
 manager.renderer.full=true;manager.renderer.active=false;manager.Prepare();assert(!manager.HDR10AIStartupBuffered());
 manager.renderer.active=true;manager.renderer.accept=false;manager.Prepare();assert(!manager.HDR10AIStartupBuffered());
 manager.renderer.accept=true;assert(manager.m_aiQueuePreparationStale);
 manager.renderer.during=[&]{assert(worker.Step()&&worker.codec.reads==2);};
 manager.Prepare(); // A fresh valid captured horizon must backpressure before stale render-readiness is republished.
 manager.renderer.accept=true;manager.m_aiQueuePreparationStale=false;
 manager.renderer.during=[&]{++manager.m_aiQueueGeneration;};manager.Prepare();assert(!manager.HDR10AIStartupBuffered());
 manager.renderer.during={};manager.m_aiQueuePreparationStale=false;manager.Prepare();assert(manager.HDR10AIStartupBuffered());
 manager.ResetHDR10AIQueue();assert(!manager.HDR10AIStartupBuffered()); // New stream/flush cannot reuse old coverage.
 manager.m_aiFullscreenRequested=true;manager.renderer.during=[]{throw std::runtime_error("GPU failure");};
 try{manager.Prepare();assert(false);}catch(const std::runtime_error&){}assert(!manager.HDR10AIStartupBuffered());
 worker.codec.blocks=false;double frame=0,pts=0;assert(!worker.ProcessDecoderOutput(frame,pts)); // Explicit drains remain unguarded.
}
'''.replace('@PRODUCER@',producer).replace('@START@',body(manager,'bool CRenderManager::GetHDR10AIStartTime('))
                         .replace('@EXECUTE@',body(manager,'bool CRenderManager::ExecuteHDR10AIQueuePreparation('))
                         .replace('@RESET@',body(manager,'void CRenderManager::ResetHDR10AIQueue()'))
                         .replace('@TRY_START@',body(worker,'void CVideoPlayerVideo::TryStartHDR10AI()'))
                         .replace('@EXTRACT@',extract).replace('@WRAPPER@',wrapper)
                         .replace('@PACKET@',packet).replace('@TIMEOUT@',timeout))


if __name__=='__main__':unittest.main()
