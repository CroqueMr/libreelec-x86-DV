"""Retain decoded audio and retry sink creation after a temporary display reset."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AudioDisplayRecoveryTests(unittest.TestCase):
    def test_failed_sink_does_not_start_or_strand_pending_audio(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoPlayerAudio.cpp').read_text()
        code = body(source, 'bool CVideoPlayerAudio::ProcessDecoderOutput(')
        process = body(source, 'void CVideoPlayerAudio::Process()')
        scheduling = process[process.index('    std::shared_ptr<CDVDMsg> pMsg;'):
                             process.index('    MsgQueueReturnCode ret =')]
        stream_change = body(process, 'else if (pMsg->IsType(CDVDMsg::GENERAL_STREAMCHANGE))')
        program = r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <vector>
enum {LOGERROR,LOGDEBUG,LOGINFO,AV_CODEC_ID_FLAC,VideoPlayer_AUDIO,
      SYNC_RESAMPLE=1,SYNC_DISCON=0};
constexpr double DVD_NOPTS_VALUE=-1,DVD_TIME_BASE=1000000;
constexpr int DVD_PLAYSPEED_NORMAL=1000,DVD_PLAYSPEED_PAUSE=0;
using namespace std::chrono_literals;
double DVD_MSEC_TO_TIME(double t) {return t*1000;}
struct IDVDStreamPlayer {enum {SYNC_STARTING,SYNC_WAITSYNC,SYNC_INSYNC};};
struct Layout {int count;Layout(int n=2):count(n) {} int Count() const {return count;}
 operator int() const {return count;}};
struct DVDAudioFrame {
 unsigned nb_frames=0,framesOut=0;bool hasDownmix=false,hasTimestamp=false,passthrough=false;
 double pts=DVD_NOPTS_VALUE,duration=4000,centerMixLevel=0;
 int bits_per_sample=24;
 struct {unsigned m_sampleRate=48000;Layout m_channelLayout;} format;
 const unsigned char* bytes=nullptr;
};
struct Codec {
 int reads=0;bool empty=false,passthrough=false;int channels=2;
 std::vector<unsigned char> storage{0x01,0x10,0x20,0x7f};
 void AddData() {storage.assign({0xde,0xad,0xbe,0xef});}
 void GetData(DVDAudioFrame& f) {++reads;f.nb_frames=empty?0:4;f.framesOut=0;
   f.pts=180000000;f.passthrough=passthrough;f.format.m_channelLayout=channels;
   f.bytes=storage.data();}
 const char* GetName() {return "fixture";}
};
struct Sink {
 bool valid=false,available=true;int creates=0,writeLimit=4,resumes=0,channels=0;
 bool passthrough=false;
 std::vector<unsigned char> written;
 bool IsValidFormat(const DVDAudioFrame& f) {return valid && channels==f.format.m_channelLayout && passthrough==f.passthrough;}
 void Drain() {} void Destroy(bool) {valid=false;}
 bool Create(const DVDAudioFrame& f,int,bool) {++creates;if(!available)return false;
   valid=true;channels=f.format.m_channelLayout;passthrough=f.passthrough;return true;}
 void Resume() {++resumes;} void SetDynamicRangeCompression(long) {}
 double GetSyncError() {return 0;} void SetSyncErrorCorrection(double) {}
 int AddPackets(const DVDAudioFrame& f) {if(!valid)return 0;
   int n=std::min<unsigned>(writeLimit,f.nb_frames-f.framesOut);
   written.insert(written.end(),f.bytes+f.framesOut,f.bytes+f.framesOut+n);return n;}
 double GetCacheTotal() {return valid?0.3:0;} double GetCacheTime() {return valid?0.3:0;}
 double GetMaxDelay() {return 0.3;} double GetDelay() {return 0.3;}
};
struct ProcessInfo {
 bool IsTempoAllowed(float) {return true;}
 bool IsRealtimeStream() {return false;}
 struct Settings {double m_VolumeAmplification=0,m_CenterMixLevel=0;};
 Settings GetVideoSettings() {return {};}
 void SetAudioChannels(int) {} void SetAudioSampleRate(int) {} void SetAudioBitsPerSample(int) {}
 void SetAudioDecoderName(const char*) {}
};
struct Clock {double ErrorAdjust(double,const char*) {return 0;}double GetClock() {return 0;}};
struct SStartMsg {int player;double cachetotal,cachetime,timestamp;};
struct CDVDMsg {enum {PLAYER_STARTED,PLAYER_AVCHANGE};explicit CDVDMsg(int) {}};
struct CDVDMsgAudioCodecChange : CDVDMsg {int m_hints=0;std::unique_ptr<Codec> m_codec;
 CDVDMsgAudioCodecChange():CDVDMsg(0),m_codec(std::make_unique<Codec>()) {}};
template<class T> struct CDVDMsgType : CDVDMsg {CDVDMsgType(int n,T) : CDVDMsg(n) {}};
struct Parent {int messages=0;template<class T>void Put(T) {++messages;}};
struct CAEUtil {static int GetAEChannelLayout(int n) {return n;}};
struct CLog {static inline int errors=0;
 template<class... T>static void Log(int level,T...) {if(level==LOGERROR)++errors;}};
struct Engine {bool suspended=false;bool IsSuspended() {return suspended;}};
struct CServiceBroker {static inline Engine engine;static Engine* GetActiveAE() {return &engine;}};
struct CVideoPlayerAudio {
 Codec codec;Codec* m_pAudioCodec=&codec;Sink m_audioSink;ProcessInfo m_processInfo;
 struct {int samplerate=48000,codec=-10,channellayout=0,channels=0;} m_streaminfo;
 int m_speed=1000,m_synctype=SYNC_DISCON,m_prevsynctype=0,m_disconAdjustTimeMs=50;
 int m_syncState=IDVDStreamPlayer::SYNC_STARTING,m_disconAdjustCounter=0;
 bool m_displayReset=true,m_stalled=true,m_paused=false;double m_audioClock=0;
 Clock clock;Clock* m_pClock=&clock;Parent m_messageParent;
 DVDAudioFrame* watched=nullptr;std::unique_ptr<Codec> replacement;
 void OpenStream(int,std::unique_ptr<Codec> next) {
   assert(watched && watched->nb_frames==0 && watched->framesOut==0);
   codec.storage.clear();codec.storage.shrink_to_fit();
   replacement=std::move(next);m_pAudioCodec=replacement.get();}
 std::pair<int,std::chrono::milliseconds> Poll(DVDAudioFrame& audioframe,bool onlyPrioMsgs) {
   SCHEDULING
   return {priority,timeout};}
 void SwitchStream(DVDAudioFrame& audioframe,std::shared_ptr<CDVDMsg> pMsg) STREAM_CHANGE
 bool SwitchCodecIfNeeded() {m_displayReset=false;return false;}
 void SetSyncType(bool) {}
 bool ProcessDecoderOutput(DVDAudioFrame& audioframe) BODY
};
int main(int argc,char** argv) {
 assert(argc==2);
 if(std::atoi(argv[1])==1) {
   CVideoPlayerAudio player;DVDAudioFrame frame;player.m_audioSink.available=false;
   assert(player.ProcessDecoderOutput(frame));player.watched=&frame;
   player.SwitchStream(frame,std::make_shared<CDVDMsgAudioCodecChange>());
   assert(frame.nb_frames==0 && frame.framesOut==0);
   player.m_audioSink.available=true;
   assert(player.ProcessDecoderOutput(frame) && player.replacement->reads==1);
   return 0;
 }
 using State=IDVDStreamPlayer;
 for(bool passthrough : {false,true}) {
   CLog::errors=0;
   CVideoPlayerAudio player;DVDAudioFrame frame;
   player.codec.passthrough=passthrough;player.codec.channels=passthrough?8:2;
   player.m_audioSink.available=false;
   // A suspended audio engine refuses creation during the display reset.
   // Process() accepts another normal DEMUXER_PACKET unless output returns true.
   bool pending=player.ProcessDecoderOutput(frame);
   if(!pending)player.codec.AddData();
   assert(pending);
   assert(player.m_syncState==State::SYNC_STARTING && player.m_messageParent.messages==0);
   assert(frame.framesOut==0 && frame.nb_frames==4 && player.codec.reads==1);
   CServiceBroker::engine.suspended=true;
   assert(player.ProcessDecoderOutput(frame) && player.m_audioSink.creates==1);
   CServiceBroker::engine.suspended=false;
   pending=player.ProcessDecoderOutput(frame);
   if(!pending)player.codec.AddData();
   assert(pending);
   assert(player.codec.reads==1 && player.m_messageParent.messages==0);
   assert(CLog::errors==1);
   // Priority events clear onlyPrioMsgs in Process(), but must not admit new data.
   auto [priority,timeout]=player.Poll(frame,false);
   if(priority==0)player.codec.AddData();
   assert(priority==1 && timeout==10ms);
   // Once the native engine is available, retry the same decoded bytes/PTS.
   player.m_audioSink.available=true;
   assert(player.ProcessDecoderOutput(frame));
   assert(player.m_audioSink.creates==3 && player.codec.reads==1);
   assert(player.m_audioSink.written==std::vector<unsigned char>({0x01,0x10,0x20,0x7f}));
   assert(frame.framesOut==4 && frame.pts==180000000);
   assert(player.m_syncState==State::SYNC_WAITSYNC && player.m_messageParent.messages==2);
   assert(player.m_audioSink.passthrough==passthrough && player.m_audioSink.channels==(passthrough?8:2));
 }
 // Normal and partial writes keep one sink and consume every byte once.
 CVideoPlayerAudio normal;DVDAudioFrame frame;normal.m_audioSink.writeLimit=2;
 assert(normal.ProcessDecoderOutput(frame) && frame.framesOut==2);
 assert(normal.ProcessDecoderOutput(frame) && frame.framesOut==4);
 assert(normal.codec.reads==1 && normal.m_audioSink.creates==1);
 assert(normal.m_audioSink.written==std::vector<unsigned char>({0x01,0x10,0x20,0x7f}));
 CVideoPlayerAudio empty;DVDAudioFrame none;empty.codec.empty=true;
 assert(!empty.ProcessDecoderOutput(none) && empty.m_audioSink.creates==0);
}
'''.replace('BODY', code).replace('SCHEDULING', scheduling).replace('STREAM_CHANGE', stream_change)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'),
                                    '-o', str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            for scenario in (0, 1):
                with self.subTest(scenario=scenario):
                    run = subprocess.run([str(root / 'test'), str(scenario)], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
