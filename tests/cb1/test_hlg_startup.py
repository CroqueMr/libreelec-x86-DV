"""Source-resolved first-page acceptance releases the native player startup."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class HLGStartup(unittest.TestCase):
    def test_prepared_source_identity_releases_native_start_and_cache_resync(self):
        def read(path):
            return (TREE / ('xbmc/' + path)).read_text()

        settings = read('cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h')
        settings = '\n'.join(x for x in settings.splitlines() if not x.startswith('#include'))
        metadata = read('cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h')
        binding = metadata[metadata.index('namespace DVBRIDGE'):metadata.index('class CDVMetadataBuffer')]
        source_h = read('cores/VideoPlayer/VideoRenderers/HDR10AISource.h')
        source_cpp = read('cores/VideoPlayer/VideoRenderers/HDR10AISource.cpp')
        bridge_h = read('cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h')
        bridge_cpp = read('cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        manager = read('cores/VideoPlayer/VideoRenderers/RenderManager.cpp')
        worker = read('cores/VideoPlayer/VideoPlayerVideo.cpp')
        player = read('cores/VideoPlayer/VideoPlayer.cpp')
        window = read('windowing/gbm/WinSystemGbmGLESContext.h')
        vaapi = read('cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp')
        config = vaapi[vaapi.index('  m_aiBuffers = m_isVAAPIBuffer'):
                       vaapi.index('  m_aiLookahead=m_aiBuffers>NUM_BUFFERS;')]
        family = read('cores/VideoPlayer/DVDCodecs/Video/HDR10SourceType.h')
        family = '\n'.join(x for x in family.splitlines() if not x.startswith('#include'))
        # These contiguous production branches retain their actual predicates and actions.
        ready = manager[manager.index('    if (!m_aiGuiReady && m_aiFullscreenRequested'):
                        manager.index('    bool aiReselection =')]
        started = body(player, 'else if (pMsg->IsType(CDVDMsg::PLAYER_STARTED))')
        sync = body(player, 'else if (video && audio && !deferNoPts)')
        # Outbound callbacks after this point do not own clock/cache synchronization.
        sync = sync[:sync.index('      m_syncTimer.Set(')] + '\n}'
        accessor = ('bool HDR10AISourceHLG() const ' + body(bridge_h, 'bool HDR10AISourceHLG() const')
                    if 'bool HDR10AISourceHLG() const' in bridge_h else '')
        program = r'''
#include <algorithm>
#include <atomic>
#include <bit>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#define HAVE_DVBRIDGE
#define CB1_HAS_HDR10_AI
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/HDR10AIActivation.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
using namespace std::chrono_literals;
constexpr double DVD_NOPTS_VALUE=-1e20;
constexpr int DVD_PLAYSPEED_NORMAL=1000,DVD_PLAYSPEED_PAUSE=0;
#define DVD_MSEC_TO_TIME(x) ((x)*1000)
struct Settings {
 std::map<std::string,int> ints;
 int GetInt(const char* id){return ints[id];}
 double GetNumber(const char*){return 100;}
 bool GetBool(const char* id){return ints[id];}
};
auto stored=std::make_shared<Settings>();
struct Component {auto GetSettings(){return stored;}} component;
struct Windows {bool fullscreen=true;bool IsWindowActive(int){return fullscreen;}} windows;
struct GUI {auto& GetWindowManager(){return windows;}} gui;
struct Messenger {void PostMsg(int){}} messenger;
struct CServiceBroker {
 static auto GetSettingsComponent(){return &component;}
 static auto GetGUI(){return &gui;}
 static auto GetAppMessenger(){return &messenger;}
};
enum {WINDOW_FULLSCREEN_VIDEO,TMSG_SWITCHTOFULLSCREEN,LOGDEBUG};
struct CLog {template<class...T>static void Log(T...){}};
@BINDING@
@SETTINGS@
enum class StreamHdrType{HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
@FAMILY@
bool DVBridgeOrientationSupported(int){return true;}
bool queueEligible(StreamHdrType type,unsigned profile){
 struct Picture{StreamHdrType hdrType;struct{unsigned profile;}doviSourceInfo;
  unsigned iFlags=0,renderBufferCount=28;}picture{type,{profile}};auto*pic=&picture;
 constexpr unsigned DVP_FLAG_INTERLACED=1,NUM_BUFFERS=4;
 bool m_isVAAPIBuffer=true;int orientation=0;unsigned m_aiBuffers=NUM_BUFFERS;
 @CONFIG@
 return m_aiBuffers>NUM_BUFFERS;
}
struct Source {
 DVBRIDGE::OutputPreferences m_preferences;
 DVBRIDGE::SourceBinding m_binding{},m_preparedBinding{};bool m_active=true,m_fallback=false;
 struct Result{cb1_ai_identity id;};std::optional<Result>m_prepared,m_committed;
 std::shared_ptr<int>m_preparedHDR10Plus,m_committedHDR10Plus;
 DVBRIDGE::HDR10AIActivation m_activation;
 bool Matches(DVBRIDGE::SourceBinding binding)const @MATCHES@
 bool Current(DVBRIDGE::SourceBinding binding,const DVBRIDGE::OutputPreferences& preferences)const @CURRENT@
 bool HDR10Plus()const @PLUS@
 bool Presented(DVBRIDGE::SourceBinding binding,bool success) @PRESENTED@
 const auto& Committed()const{return m_committed;}
};
struct Context {Source source;auto& HDR10AI(){return source;}};
struct Bridge {
 Context* m_context;bool m_sourceHLG=false;
 @ACCESSOR@
 const std::optional<Source::Result>& CommittedHDR10AI()const @COMMITTED@
 void Prepare(bool hlg){struct{bool hlg;}base{hlg};@SOURCE_ASSIGNMENT@}
};
struct Window {
 Context context;Context* m_dvContext=&context;Bridge bridge{&context};Bridge* m_dvBridge=&bridge;
 DVBRIDGE::SourceBinding m_aiActivation{11,1,22};
 bool HDR10AIFrameCommitted()const @FRAME_COMMITTED@
 bool eligible=true,lookahead=true;
 bool HDR10AIQueueEligible(){return eligible;}bool HDR10AILookahead(){return lookahead;}
 void Prepare(bool plus,bool hlg,bool accepted=true){bridge.Prepare(hlg);
  context.source.m_preferences=DVBRIDGE::FrameOutputSettings(plus,hlg);
  auto& source=context.source;source.m_binding=m_aiActivation;source.m_preparedBinding=m_aiActivation;
  source.m_active=source.m_preferences.hdr10Source!=DVBRIDGE::HDR10SourceMode::Native;
  if(!source.m_active)return;
  const cb1_ai_identity identity{m_aiActivation.stream,m_aiActivation.picture,33};
  source.m_activation.Begin(identity.stream,identity.revision,0);
  assert(source.m_activation.Observe(CB1_AI_READY,identity,0)==DVBRIDGE::HDR10AIActivation::Decision::Prepare);
  source.m_prepared=Source::Result{identity};
  assert(!HDR10AIFrameCommitted()); // Prepared analysis alone cannot release startup.
  assert(source.Presented(m_aiActivation,accepted)==accepted);}
};
struct Manager {
 Window renderer;Window* m_pRenderer=&renderer;std::mutex m_presentlock;
 bool m_aiFullscreenRequested=true,m_aiFullscreenWanted=true,m_aiGuiReady=false;
 bool m_aiQueueReady=true,m_bTriggerUpdateResolution=false;
 double m_aiStartPts=9000000;
 struct Event{void notifyAll(){}}m_presentevent;
 void FrameMove(){@READY@}
 bool GetHDR10AIStartTime(double& pts) @START_TIME@
 bool PrepareHDR10AIStartup(bool fullscreen) @STARTUP@
 double GetDelay(){return 0;}
};
struct IDVDStreamPlayer{enum{SYNC_STARTING,SYNC_WAITSYNC,SYNC_INSYNC};};
enum{VideoPlayer_AUDIO,VideoPlayer_VIDEO};
struct SStartMsg {int player{};double cachetime{},cachetotal{},timestamp{};bool timestampPending=false;};
struct CDVDMsg {enum{PLAYER_STARTED,GENERAL_RESYNC};virtual ~CDVDMsg()=default;};
template<class T>struct CDVDMsgType:CDVDMsg {T m_value;CDVDMsgType(int,T v):m_value(v){}};
struct CDVDMsgDouble:CDVDMsg {double value;CDVDMsgDouble(int,double v):value(v){}};
struct ParentQueue {std::shared_ptr<CDVDMsg> message;unsigned starts=0;
 void Put(std::shared_ptr<CDVDMsg> value){message=value;++starts;}};
struct Worker {
 int m_syncState=IDVDStreamPlayer::SYNC_STARTING;Manager& m_renderManager;ParentQueue m_messageParent;
 void TryStartHDR10AI() @TRY_START@
};
struct Parent {
 enum ECacheState{CACHESTATE_FLUSH,CACHESTATE_FULL,CACHESTATE_INIT,CACHESTATE_PLAY,CACHESTATE_DONE};
 ECacheState m_caching=CACHESTATE_DONE;
 struct CacheInfo{bool valid=false;};CacheInfo GetCachingTimes(){return {};}
 int m_playSpeed=1000,m_streamPlayerSpeed=1000;
 struct Clock {int speed=1000;double time=0;
  void SetSpeed(int s){speed=s;}void SetSpeedAdjust(int){}void Discontinuity(double t){time=t;}}m_clock;
 struct Endpoint{int speed=1000,resyncs=0;double pts=0;void SetSpeed(int s){speed=s;}
  void SendMessage(std::shared_ptr<CDVDMsgDouble>m,int){++resyncs;pts=m->value;}
  int GetLevel(){return 0;}}audio,video;
 Endpoint* m_VideoPlayerAudio=&audio;Endpoint* m_VideoPlayerVideo=&video;
 struct Timer{void Set(std::chrono::milliseconds){}}m_cachingTimer;
 struct CCurrentStream {enum{AV_SYNC_NONE,AV_SYNC_CONT};
  int syncState=IDVDStreamPlayer::SYNC_STARTING,avsync=AV_SYNC_NONE,packets=0;
  double starttime=DVD_NOPTS_VALUE,cachetime=0,cachetotal=0;bool starttimePending=false;};
 CCurrentStream m_CurrentVideo,m_CurrentAudio;
 struct Input {bool IsRealtime(){return false;}}input;Input*m_pInputStream=&input;
 int m_messageQueueTimeSize=1;std::optional<int>m_syncStartPtsWait;
 double publishedTime=0;void UpdatePlayState(int){publishedTime=m_clock.time;}
 void SetCaching(ECacheState state) @CACHE@
 void Started(std::shared_ptr<CDVDMsg>pMsg) @PLAYER_STARTED@
 void Resync() @SYNC@
};
void handoff(Manager&manager,int requestedSpeed=1000){
 Worker worker{IDVDStreamPlayer::SYNC_STARTING,manager};Parent parent;
 parent.m_playSpeed=requestedSpeed;parent.SetCaching(Parent::CACHESTATE_INIT);
 assert(parent.m_clock.speed==0 && parent.video.speed==0);
 manager.FrameMove();worker.TryStartHDR10AI();
 assert(manager.PrepareHDR10AIStartup(true));
 assert(worker.m_syncState==IDVDStreamPlayer::SYNC_WAITSYNC && worker.m_messageParent.starts==1);
 parent.Started(worker.m_messageParent.message);parent.m_CurrentVideo.packets=1;
 parent.Resync();
 assert(parent.video.resyncs==1 && parent.m_CurrentVideo.syncState==IDVDStreamPlayer::SYNC_INSYNC);
 const double expectedPts=requestedSpeed==0 ? 9000000 : 8900000;
 assert(parent.publishedTime==expectedPts && parent.video.pts==expectedPts);
 assert(parent.m_clock.speed==requestedSpeed && parent.video.speed==requestedSpeed);
 worker.TryStartHDR10AI();assert(worker.m_messageParent.starts==1);
}
int main(){
 using namespace DVBRIDGE;
 stored->ints["dvbridge.hlgsource"]=1;
 for(int hdr=0;hdr<=4;++hdr){
  stored->ints["dvbridge.hdr10source"]=hdr;
  Manager m;m.renderer.Prepare(false,true);
  assert(m.renderer.context.source.m_preferences.hdr10Source==HDR10SourceMode::ReferenceDV);
  assert(m.renderer.HDR10AIFrameCommitted() && "HLG commit must use its actual prepared source identity");
  handoff(m);Manager paused;paused.renderer.Prepare(false,true);handoff(paused,0);
 }
 // The same getter remains correct for HDR10 and independently saved HDR10+.
 for(int hdr:{1,2}){stored->ints["dvbridge.hdr10source"]=hdr;Manager m;m.renderer.Prepare(false,false);handoff(m);}
 stored->ints["dvbridge.hdr10plussource"]=3;Manager plus;plus.renderer.Prepare(true,false);handoff(plus);
 stored->ints["dvbridge.hlgsource"]=0;Manager native;native.renderer.Prepare(false,true);
 assert(native.renderer.context.source.m_preferences.hdr10Source==HDR10SourceMode::Native);
 native.renderer.lookahead=false;assert(native.PrepareHDR10AIStartup(true));
 for(auto type:{StreamHdrType::HDR_TYPE_HLG,StreamHdrType::HDR_TYPE_HDR10,StreamHdrType::HDR_TYPE_HDR10PLUS}){
  assert(queueEligible(type,0));
  for(unsigned dvProfile:{8,10})assert(!queueEligible(type,dvProfile)); // P8.4/P10.4 stay full DV.
 }
 for(int choice:{0,4}){stored->ints["dvbridge.hdr10plussource"]=choice;
  assert(int(FrameOutputSettings(true).hdr10Source)==choice);
  assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::EnhancedDV);
 }
 stored->ints["dvbridge.hlgsource"]=1;
 Manager rejected;rejected.renderer.Prepare(false,true,false);rejected.FrameMove();
 Worker rejectedWorker{IDVDStreamPlayer::SYNC_STARTING,rejected};rejectedWorker.TryStartHDR10AI();
 assert(!rejected.m_aiGuiReady && rejectedWorker.m_messageParent.starts==0);
 for(int guard=0;guard<13;++guard){Manager m;m.renderer.Prepare(false,true);
  if(guard==0)m.renderer.context.source.m_committed.reset();
  if(guard==1)++m.renderer.m_aiActivation.stream;
  if(guard==2)++m.renderer.m_aiActivation.revision; // Seek/epoch invalidation.
  if(guard==3)m.renderer.context.source.m_active=false; // Stopped session.
  if(guard==4){stored->ints["dvbridge.sdrpreset"]++;FrameOutputSettings();}
  if(guard==5)m.m_aiStartPts=DVD_NOPTS_VALUE;
  if(guard==6)m.m_bTriggerUpdateResolution=true;
  if(guard==7)windows.fullscreen=false;
  if(guard==8)m.renderer.context.source.m_preferences.method=99;
  if(guard==9)m.renderer.context.source.m_binding={}; // Rejected/unbound preparation.
  if(guard==10)m.renderer.bridge.m_sourceHLG=false; // Wrong prepared source cannot authorize HLG.
  if(guard==11)m.renderer.m_dvBridge=nullptr;
  if(guard==12)m.renderer.m_dvContext=nullptr;
  m.FrameMove();Worker worker{IDVDStreamPlayer::SYNC_STARTING,m};worker.TryStartHDR10AI();
  assert(!m.m_aiGuiReady && worker.m_messageParent.starts==0);
  windows.fullscreen=true;
 }
}
'''
        replacements = {
            '@BINDING@': binding, '@SETTINGS@': settings,
            '@FAMILY@': family, '@CONFIG@': config,
            '@MATCHES@': body(source_cpp, 'bool HDR10AISource::Matches('),
            '@CURRENT@': body(source_h, 'bool Current('),
            '@PRESENTED@': body(source_cpp, 'bool HDR10AISource::Presented('),
            '@PLUS@': body(source_h, 'bool HDR10Plus() const'),
            '@ACCESSOR@': accessor,
            '@COMMITTED@': body(bridge_cpp, 'CDVBridgeGLES::CommittedHDR10AI() const'),
            '@SOURCE_ASSIGNMENT@': 'm_sourceHLG = base.hlg;',
            '@FRAME_COMMITTED@': body(window, 'bool HDR10AIFrameCommitted() const'),
            '@READY@': ready,
            '@START_TIME@': body(manager, 'bool CRenderManager::GetHDR10AIStartTime('),
            '@STARTUP@': body(manager, 'bool CRenderManager::PrepareHDR10AIStartup('),
            '@TRY_START@': body(worker, 'void CVideoPlayerVideo::TryStartHDR10AI()'),
            '@CACHE@': body(player, 'void CVideoPlayer::SetCaching('),
            '@PLAYER_STARTED@': started, '@SYNC@': sync,
        }
        self.assertIn(replacements['@SOURCE_ASSIGNMENT@'], bridge_cpp)
        for marker, value in replacements.items():
            program = program.replace(marker, value)
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'check.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-I'+str(repo/'CB1/src'),
                                    '-I'+str(TREE/'xbmc'), str(root/'check.cpp'), '-o', str(root/'check')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root/'check')], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)


if __name__ == '__main__':
    unittest.main()
