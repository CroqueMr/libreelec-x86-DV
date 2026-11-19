"""A failed HDMI sink must retain ownership and logical stream controls."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AudioSampleOwnershipTests(unittest.TestCase):
    def test_error_seek_flush_returns_partial_buffers_and_accepts_unconfigured_stream(self):
        source=(TREE/'xbmc/cores/AudioEngine/Engines/ActiveAE/ActiveAE.cpp').read_text()
        error=source.split('case AE_TOP_ERROR:',1)[1]
        control=body(error,'if (port == &m_controlPort)')
        flush=body(source,'void CActiveAE::SFlushStream(CActiveAEStream *stream)')
        stream_source=(TREE/'xbmc/cores/AudioEngine/Engines/ActiveAE/ActiveAEStream.cpp').read_text()
        reset=body(stream_source,'void CActiveAEStream::ResetFreeBuffers()')
        program=r'''
#include <cassert>
#include <chrono>
#include <deque>
#include <list>
#include <memory>
#include <mutex>
using namespace std::chrono_literals;
struct CActiveAEControlProtocol {enum {DEVICECHANGE=3,DEFAULTDEVICECHANGE=4,DEVICECOUNTCHANGE=5,
 RECONFIGURE=1,PAUSESTREAM=8,RESUMESTREAM=9,FLUSHSTREAM=10,STREAMAMP=13,ACC=0};};
struct CAESyncInfo {enum class AESyncState {SYNC_OFF,SYNC_START};};
struct Buffer{int returned=0;void Return(){++returned;}};
struct Processing{int flushes=0;double rr=2;void Flush(){++flushes;}void SetRR(double v,double){rr=v;}};
struct Port{int pending=2;void Purge(){pending=0;}};
struct CActiveAEStream {
 bool m_paused=true;CAESyncInfo::AESyncState m_syncState=CAESyncInfo::AESyncState::SYNC_OFF;
 float m_amplify=1;struct{void SetAmplification(float){}}m_limiter;
 std::deque<Buffer*>m_processingSamples;
 std::unique_ptr<Processing>m_processingBuffers=std::make_unique<Processing>();
 Port port;Port*m_streamPort=&port;double m_bufferedTime=2,m_lastPts=3,m_lastPtsJump=4,m_resampleIntegral=5;
 int m_streamFreeBuffers=2;std::mutex m_streamLock;
 struct{int flushes=0;void Flush(){++flushes;}}m_syncError;
 std::chrono::milliseconds m_errorInterval{99};
 void ResetFreeBuffers() RESET
};
struct MsgStreamParameter{CActiveAEStream*stream;union{float float_par;double double_par;}parameter;};
struct Message{void*data;int reply=-1;void Reply(int value){reply=value;}};
struct Engine{
 int m_state=2,m_extErrorRetries=7,engineFlushes=0;
 std::chrono::milliseconds m_extTimeout{500};
 struct{void EnumerateSinkList(bool,const char*){}}m_sink;
 struct{double atempoThreshold=1;}m_settings;
 std::list<CActiveAEStream*>m_streams;
 struct{int updates=0;void UpdateStream(CActiveAEStream*){++updates;}}m_stats;
 void FlushEngine(){++engineFlushes;}
 void SFlushStream(CActiveAEStream*stream) @@FLUSH@@
 void control(int signal,Message*msg) CONTROL
};
int main(){
 for(bool withPools:{true,false}){
  Engine e;CActiveAEStream stream;if(!withPools)stream.m_processingBuffers.reset();
  Buffer partial;stream.m_processingSamples.push_back(&partial);e.m_streams.push_back(&stream);
  auto*ptr=&stream;Message message{&ptr};
  e.control(CActiveAEControlProtocol::FLUSHSTREAM,&message);
  assert(message.reply==CActiveAEControlProtocol::ACC);
  assert(partial.returned==1 && stream.m_processingSamples.empty() && stream.port.pending==0);
  assert(stream.m_streamFreeBuffers==0 && stream.m_bufferedTime==0 && stream.m_resampleIntegral==0);
  assert(stream.m_lastPts==0 && stream.m_lastPtsJump==0 && stream.m_syncError.flushes==1);
  assert(stream.m_syncState==CAESyncInfo::AESyncState::SYNC_START);
  if(withPools)assert(stream.m_processingBuffers->flushes==1 && stream.m_processingBuffers->rr==1);
  assert(e.m_state==2 && e.m_extErrorRetries==7 && e.m_extTimeout==0ms);
  assert(e.engineFlushes==1 && e.m_stats.updates==1);
 }
}
'''.replace('RESET',reset).replace('@@FLUSH@@',flush).replace('CONTROL',control)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_stream_creation_during_sink_error_replies_and_uses_native_recovery(self):
        source=(TREE/'xbmc/cores/AudioEngine/Engines/ActiveAE/ActiveAE.cpp').read_text()
        error=source[source.index('    case AE_TOP_ERROR:'):
                     source.index('    case AE_TOP_UNCONFIGURED:')]
        program=r'''
#include <cassert>
#include <chrono>
#include <cstring>
using namespace std::chrono_literals;
constexpr int AE_TOP_ERROR=2,AE_TOP_CONFIGURED_PLAY=8;
struct CActiveAEControlProtocol {enum {RECONFIGURE=1,DEVICECHANGE=3,
 DEFAULTDEVICECHANGE=4,DEVICECOUNTCHANGE=5,PAUSESTREAM=8,RESUMESTREAM=9,FLUSHSTREAM=10,STREAMAMP=13,TIMEOUT=25,ACC=0};};
struct CActiveAEDataProtocol {enum {NEWSTREAM=3};enum {ACC=0,ERR=1};};
struct CAESyncInfo {enum class AESyncState {SYNC_OFF,SYNC_START};};
struct Protocol{};
struct Stream {
 bool ready=false,m_paused=true;
 CAESyncInfo::AESyncState m_syncState=CAESyncInfo::AESyncState::SYNC_OFF;
 float m_amplify=1;struct {void SetAmplification(float){}}m_limiter;
};
using CActiveAEStream=Stream;
struct MsgStreamParameter {Stream*stream;union {float float_par;double double_par;}parameter;};
struct MsgStreamNew {int format=17;};
struct Message {
 void*data=nullptr;int reply=-1,count=0;Stream*stream=nullptr;
 void Reply(int result,const void* value=nullptr,unsigned size=0){
  reply=result;++count;if(value){assert(size==sizeof(stream));std::memcpy(&stream,value,size);}
 }
};
struct Engine {
 int m_state=AE_TOP_ERROR,m_extErrorRetries=7,allocations=0,configurations=0;
 bool m_extError=true,allocationFails=false,sinkFails=true;
 std::chrono::milliseconds m_extTimeout{500};Protocol m_controlPort,m_dataPort;
 struct {int calls=0;void EnumerateSinkList(bool,const char*){++calls;}}m_sink;
 Stream pending;
 Stream*CreateStream(MsgStreamNew*request){assert(request->format==17);++allocations;return allocationFails?nullptr:&pending;}
 void LoadSettings(){}
 void SFlushStream(Stream*){assert(false);}
 void Configure(){++configurations;m_extError=sinkFails;if(!sinkFails)pending.ready=true;}
 std::chrono::milliseconds ErrorRetryDelay(unsigned){return 500ms;}
 void StateMachine(int signal,Protocol*port,Message*msg){
  for(int state=m_state;;state=0){switch(state){OWNED_ERROR_CASE default:return;}}
 }
};
int main(){
 Engine e;MsgStreamNew request;Message message{&request};
 e.StateMachine(CActiveAEDataProtocol::NEWSTREAM,&e.m_dataPort,&message);
 assert(message.reply==CActiveAEDataProtocol::ACC && message.count==1);
 assert(message.stream==&e.pending && e.allocations==1);
 assert(e.m_state==AE_TOP_ERROR && !e.pending.ready && e.configurations==0);
 assert(e.m_extTimeout==0ms && e.m_extErrorRetries==7);
 e.StateMachine(CActiveAEControlProtocol::TIMEOUT,nullptr,nullptr);
 assert(e.m_state==AE_TOP_ERROR && !e.pending.ready && e.m_extErrorRetries==8);
 assert(e.configurations==1 && message.count==1 && e.allocations==1);
 e.sinkFails=false;e.StateMachine(CActiveAEControlProtocol::TIMEOUT,nullptr,nullptr);
 assert(e.m_state==AE_TOP_CONFIGURED_PLAY && e.pending.ready && !e.m_extError);
 assert(e.m_extErrorRetries==0 && e.configurations==2 && e.allocations==1);
 Engine failed;failed.allocationFails=true;Message rejected{&request};
 failed.StateMachine(CActiveAEDataProtocol::NEWSTREAM,&failed.m_dataPort,&rejected);
 assert(rejected.reply==CActiveAEDataProtocol::ERR && rejected.count==1 && !rejected.stream);
 assert(failed.m_state==AE_TOP_ERROR && failed.m_extTimeout==500ms && failed.configurations==0);
}
'''.replace('OWNED_ERROR_CASE',error)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_error_state_keeps_pause_resume_and_amplification_intent(self):
        source=(TREE/'xbmc/cores/AudioEngine/Engines/ActiveAE/ActiveAE.cpp').read_text()
        error=source.split('case AE_TOP_ERROR:',1)[1]
        control=body(error,'if (port == &m_controlPort)')
        program=r'''
#include <cassert>
#include <chrono>
using namespace std::chrono_literals;
struct CActiveAEControlProtocol {enum {DEVICECHANGE=3,DEFAULTDEVICECHANGE=4,DEVICECOUNTCHANGE=5,
 RECONFIGURE=1,PAUSESTREAM=8,RESUMESTREAM=9,FLUSHSTREAM=10,STREAMAMP=13,ACC=0};};
struct CAESyncInfo {enum class AESyncState {SYNC_OFF,SYNC_START};};
struct CActiveAEStream {
 bool m_paused=true;CAESyncInfo::AESyncState m_syncState=CAESyncInfo::AESyncState::SYNC_OFF;
 float m_amplify=1;struct {float value=1;void SetAmplification(float v){value=v;}}m_limiter;
};
struct MsgStreamParameter {CActiveAEStream* stream;union {float float_par;double double_par;}parameter;};
struct Message {void* data;void Reply(int){assert(false);}};
struct Window {
 int m_state=2,m_extErrorRetries=7;std::chrono::milliseconds m_extTimeout{500};
 struct {int calls=0;void EnumerateSinkList(bool,const char*){++calls;}} m_sink;
 void SFlushStream(CActiveAEStream*){assert(false);}
 void control(int signal,Message* msg) CONTROL
};
int main(){
 Window w;CActiveAEStream s;auto* ptr=&s;Message message{&ptr};
 w.control(CActiveAEControlProtocol::RESUMESTREAM,&message);
 assert(!s.m_paused && s.m_syncState==CAESyncInfo::AESyncState::SYNC_START);
 w.control(CActiveAEControlProtocol::PAUSESTREAM,&message);assert(s.m_paused);
 w.control(CActiveAEControlProtocol::RESUMESTREAM,&message);assert(!s.m_paused);
 MsgStreamParameter amplification{&s,{2.0f}};Message amp{&amplification};
 w.control(CActiveAEControlProtocol::STREAMAMP,&amp);
 assert(s.m_amplify==2.0f && s.m_limiter.value==2.0f);
 assert(w.m_state==2 && w.m_extTimeout==500ms && w.m_sink.calls==0);
 w.control(CActiveAEControlProtocol::DEVICECHANGE,&message);
 assert(w.m_sink.calls==1 && w.m_extTimeout==0ms && w.m_extErrorRetries==0);
}
'''.replace('CONTROL',control)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_failed_sink_retains_samples_and_allows_stream_destruction(self):
        source=(TREE/'xbmc/cores/AudioEngine/Engines/ActiveAE/ActiveAE.cpp').read_text()
        process=body(source,'void CActiveAE::Process()')
        start=process.index('    // check control port')
        poll=process[start:process.index('\n    if (gotMsg)',start)]
        top=source.split('case AE_TOP: // TOP',1)[1]
        data=body(top,'else if (port == &m_dataPort)')
        discard=body(source,'void CActiveAE::DiscardStream(CActiveAEStream *stream)')
        program=r'''
#include <cassert>
#include <chrono>
#include <deque>
#include <list>
#include <memory>
#include <vector>
using namespace std::chrono_literals;
constexpr int AE_TOP_ERROR=2,AE_TOP_CONFIGURED_PLAY=9,LOGERROR=0,LOGDEBUG=1;
struct CLog {template<class... T>static void Log(T...) {}};
struct CActiveAEDataProtocol {enum {NEWSOUND=0,PLAYSOUND,FREESOUND,NEWSTREAM,FREESTREAM,STREAMSAMPLE,DRAINSTREAM};enum {ACC=0,ERR,STREAMBUFFER,STREAMDRAINED};};
struct Message {void* data=nullptr;int reply=-1;void Reply(int signal){reply=signal;}};
struct Protocol {
 std::deque<Message*> messages;
 int lastIn=-1;void SendInMessage(int signal){lastIn=signal;}
 bool ReceiveOutMessage(Message** out){if(messages.empty())return false;*out=messages.front();messages.pop_front();return true;}
 bool ReceiveInMessage(Message** out){return ReceiveOutMessage(out);}
};
struct CSampleBuffer {
 struct Packet {int nb_samples=1;} packet;
 Packet* pkt=&packet;int returned=0;void Return(){++returned;}
};
struct Pool {void Flush(){};};
struct Processing {
 std::vector<CSampleBuffer*> m_inputSamples;
 bool drain=false;void SetDrain(bool value){drain=value;}
 void Flush(){}
 std::unique_ptr<Pool> GetResampleBuffers(){return {};}
 std::unique_ptr<Pool> GetAtempoBuffers(){return {};}
};
struct CActiveAEStream {
 int m_id=1;std::deque<CSampleBuffer*> m_processingSamples;
 bool m_drain=false;
 std::unique_ptr<Protocol> m_streamPort=std::make_unique<Protocol>();
 std::unique_ptr<Pool> m_inputBuffers;
 std::unique_ptr<Processing> m_processingBuffers=std::make_unique<Processing>();
};
struct MsgStreamSample {CActiveAEStream* stream;CSampleBuffer* buffer;};
struct MsgStreamFree {CActiveAEStream* stream;};
struct CActiveAESound {};
struct Window {
 int m_state=AE_TOP_ERROR;bool m_extDeferData=false;
 Protocol m_controlPort,m_dataPort;struct {Protocol m_dataPort;} m_sink;
 std::list<CActiveAEStream*> m_streams;
 std::chrono::milliseconds m_extTimeout{500};
 std::vector<CActiveAESound*> m_sounds;void ResampleSounds(){}void DiscardSound(CActiveAESound*){}
 std::vector<std::unique_ptr<Pool>> m_discardBufferPools;
 struct {void RemoveStream(int){}} m_stats;
 void ClearDiscardedBuffers(){}
 Message* poll(){bool gotMsg=false;Message* msg=nullptr;Protocol* port=nullptr;
  if(false){} POLL
  (void)port;return gotMsg?msg:nullptr;
 }
 void data(int signal,Message* msg) DATA
 void DiscardStream(CActiveAEStream* stream) DISCARD
};
int main(){
 Window w;auto* stream=new CActiveAEStream;w.m_streams.push_back(stream);
 CSampleBuffer a,b;MsgStreamSample pa{stream,&a},pb{stream,&b};Message ma{&pa},mb{&pb};
 stream->m_processingSamples={&a,&b};stream->m_streamPort->messages={&ma,&mb};
 Message control,sinkReturn,freeStream;
 w.m_controlPort.messages.push_back(&control);assert(w.poll()==&control);
 w.m_sink.m_dataPort.messages.push_back(&sinkReturn);assert(w.poll()==&sinkReturn);
 w.m_dataPort.messages.push_back(&freeStream);assert(w.poll()==&freeStream);
 auto* next=w.poll();assert(next==&ma);w.data(CActiveAEDataProtocol::STREAMSAMPLE,next);
 assert(stream->m_processingSamples.size()==1 && stream->m_processingSamples.front()==&b);
 next=w.poll();assert(next==&mb);w.data(CActiveAEDataProtocol::STREAMSAMPLE,next);
 assert(w.poll()==nullptr && stream->m_processingSamples.empty());
 assert((stream->m_processingBuffers->m_inputSamples==std::vector<CSampleBuffer*>{&a,&b}));
 assert(w.m_state==AE_TOP_ERROR && w.m_extTimeout==500ms);
 auto* ptr=stream;Message drain{&ptr};stream->m_streamPort->messages.push_back(&drain);
 assert(w.poll()==&drain);w.data(CActiveAEDataProtocol::DRAINSTREAM,&drain);
 assert(drain.reply==CActiveAEDataProtocol::ACC && stream->m_drain &&
        stream->m_streamPort->lastIn==CActiveAEDataProtocol::STREAMDRAINED);
 CSampleBuffer normal;MsgStreamSample pn{stream,&normal};Message mn{&pn};
 w.m_state=AE_TOP_CONFIGURED_PLAY;stream->m_processingSamples={&normal};
 stream->m_streamPort->messages.push_back(&mn);assert(w.poll()==&mn);
 w.data(CActiveAEDataProtocol::STREAMSAMPLE,&mn);
 assert(stream->m_processingBuffers->m_inputSamples.back()==&normal && w.m_extTimeout==0ms);
 assert(a.returned==0 && b.returned==0);w.DiscardStream(stream);assert(w.m_streams.empty());
 auto* dying=new CActiveAEStream;w.m_streams.push_back(dying);w.m_state=AE_TOP_ERROR;
 CSampleBuffer c,d;MsgStreamSample pc{dying,&c},pd{dying,&d};Message mc{&pc},md{&pd};
 dying->m_processingSamples={&c,&d};dying->m_streamPort->messages={&mc,&md};
 MsgStreamFree freePayload{dying};freeStream.data=&freePayload;
 w.m_dataPort.messages.push_back(&freeStream);assert(w.poll()==&freeStream);
 w.data(CActiveAEDataProtocol::FREESTREAM,&freeStream);
 assert(w.m_streams.empty() && c.returned==1 && d.returned==1 && w.poll()==nullptr);
 auto* empty=new CActiveAEStream;w.m_streams.push_back(empty);empty->m_processingBuffers.reset();
 CSampleBuffer orphan;MsgStreamSample po{empty,&orphan};Message mo{&po};
 empty->m_processingSamples={&orphan};w.data(CActiveAEDataProtocol::STREAMSAMPLE,&mo);
 assert(orphan.returned==1 && empty->m_processingSamples.empty());
 auto* emptyPtr=empty;Message emptyDrain{&emptyPtr};
 w.data(CActiveAEDataProtocol::DRAINSTREAM,&emptyDrain);
 assert(emptyDrain.reply==CActiveAEDataProtocol::ACC && empty->m_drain &&
        empty->m_streamPort->lastIn==CActiveAEDataProtocol::STREAMDRAINED);
 w.DiscardStream(empty);assert(w.m_streams.empty());
}
'''.replace('POLL',poll).replace('DATA',data).replace('DISCARD',discard)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
