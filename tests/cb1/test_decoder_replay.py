"""Convergence replay keeps FIFO decode order across reopen and EAGAIN."""
import unittest
from test_native_video_source import TREE, body
from test_ai_reentry import execute


class DecoderReplayTests(unittest.TestCase):
    def run_queue(self, replay, checks):
        queue=(TREE/'xbmc/cores/VideoPlayer/DVDMessageQueue.cpp').read_text()
        player=(TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        put=body(queue,'MsgQueueReturnCode CDVDMessageQueue::Put(const std::shared_ptr<CDVDMsg>& pMsg,\n                                         int priority,')
        get=body(queue,'MsgQueueReturnCode CDVDMessageQueue::Get(')
        send=body(player,'inline void CVideoPlayerVideo::SendMessage(')
        back=body(player,'inline void CVideoPlayerVideo::SendMessageBack(')
        retry=body(player,'      else\n      {\n        SendMessageBack')
        timeout=body(player,'else if (ret == MSGQ_TIMEOUT)')
        timeout=timeout[:timeout.index('      // if we only wanted priority messages')]+'\n}'
        execute(r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <deque>
#include <list>
#include <memory>
#include <mutex>
#include <string>
using namespace std::chrono_literals;
constexpr int LOGWARNING=0,LOGFATAL=1,OUTPUT_AGAIN=1,DVD_PLAYSPEED_PAUSE=0;constexpr double DVD_NOPTS_VALUE=1e20;
namespace IDVDStreamPlayer{constexpr int SYNC_INSYNC=0;}
enum MsgQueueReturnCode{MSGQ_OK=1,MSGQ_TIMEOUT=0,MSGQ_ABORT=-1,MSGQ_NOT_INITIALIZED=-2,MSGQ_INVALID_MSG=-3};
struct CDVDMsg{enum{DEMUXER_PACKET};char name;explicit CDVDMsg(char c):name(c){}virtual~CDVDMsg()=default;
 bool IsType(int)const{return true;}};
struct DemuxPacket{int iSize=1;};
struct CDVDMsgDemuxerPacket:CDVDMsg{using CDVDMsg::CDVDMsg;DemuxPacket data;DemuxPacket*GetPacket(){return &data;}};
struct DVDMessageListItem{std::shared_ptr<CDVDMsg>message;int priority;
 DVDMessageListItem(std::shared_ptr<CDVDMsg>m,int p):message(std::move(m)),priority(p){}};
struct CLog{template<class... T>static void Log(T...){}};
struct Queue{
 std::mutex m_section;bool m_bInitialized=true,m_bAbortRequest=false,m_drain=false;
 int m_iDataSize=0;double m_TimeBack=0,m_TimeFront=0;const char*m_owner="test";
 std::list<DVDMessageListItem>m_prioMessages,m_messages;
 struct{void Set(){}void Reset(){}bool Wait(std::chrono::milliseconds){return false;}}m_hEvent;
 void UpdateTimeBack(){}void UpdateTimeFront(){}int GetLevel(){return 0;}
 MsgQueueReturnCode Put(const std::shared_ptr<CDVDMsg>&pMsg,int priority,bool front) @PUT@
 void Put(const std::shared_ptr<CDVDMsg>&m,int p=0){assert(Put(m,p,true)==MSGQ_OK);}
 void PutBack(const std::shared_ptr<CDVDMsg>&m,int p=0){assert(Put(m,p,false)==MSGQ_OK);}
 MsgQueueReturnCode Get(std::shared_ptr<CDVDMsg>&pMsg,std::chrono::milliseconds timeout,int&priority) @GET@
 std::shared_ptr<CDVDMsg>Take(int*actual=nullptr){std::shared_ptr<CDVDMsg>m;int p=0;assert(Get(m,0ms,p)==MSGQ_OK);if(actual)*actual=p;return m;}
 std::string Drain(){std::string s;while(!m_messages.empty()||!m_prioMessages.empty())s+=Take()->name;return s;}
};
auto packet(char c){return std::make_shared<CDVDMsgDemuxerPacket>(c);}
struct Player{
 Queue m_messageQueue;struct{void SetLevelVQ(int){}bool IsFrameAdvance(){return false;}}m_processInfo;
 int m_outputSate=0,m_speed=1,m_syncState=IDVDStreamPlayer::SYNC_INSYNC,drains=0;
 bool m_paused=false,decoderReady=false;
 struct Picture{void*videoBuffer=nullptr;}m_picture;
 int OutputPicture(Picture*){return 0;}
 bool ProcessDecoderOutput(double,double){decoderReady=true;drains++;return false;}
 struct Saved{std::shared_ptr<CDVDMsg>message;};std::deque<Saved>m_packets;
 void SendMessage(const std::shared_ptr<CDVDMsg>&pMsg,int priority=0) @SEND@
 void SendMessageBack(const std::shared_ptr<CDVDMsg>&pMsg,int priority=0) @BACK@
 void Replay(){@REPLAY@}
 void Retry(const std::shared_ptr<CDVDMsg>&pMsg,int iPriority){bool onlyPrioMsgs=false;@RETRY@ assert(onlyPrioMsgs);}
 void Drain(){double frametime=33333,pts=0;bool onlyPrioMsgs=false;for(int once=0;once<1;once++) @DRAIN_BODY@}
};
int main(){@CHECKS@}
'''.replace('@PUT@',put).replace('@GET@',get).replace('@SEND@',send).replace('@BACK@',back)
           .replace('@REPLAY@',replay).replace('@RETRY@',retry).replace('@DRAIN_BODY@',timeout).replace('@CHECKS@',checks))

    def test_reopen_and_flush_prepend_fifo_prefix_before_remaining_replay(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        for state in ('VC_REOPEN','VC_FLUSHED'):
            branch=body(source,'if (decoderState == CDVDVideoCodec::'+state+')')
            replay='while (!m_packets.empty())'+body(branch,'while (!m_packets.empty())')
            with self.subTest(state=state):
                self.run_queue(replay,r'''
 Player p;p.SendMessage(packet('!'),20);p.SendMessage(packet('^'),1);
 for(char c:std::string("DE"))p.m_packets.push_back({packet(c)});p.Replay();
 p.SendMessage(packet('N'),0);for(char c:std::string("ABC"))p.m_packets.push_back({packet(c)});
 p.Replay();assert(p.m_messageQueue.m_iDataSize==6);assert(p.m_messageQueue.Drain()=="!^ABCDEN");
 assert(p.m_messageQueue.m_iDataSize==0);
 Player repeated;for(char c:std::string("ABC"))repeated.m_packets.push_back({packet(c)});
 repeated.Replay();assert(repeated.m_messageQueue.Take()->name=='A');
 repeated.m_packets.push_back({packet('A')});repeated.Replay();assert(repeated.m_messageQueue.Drain()=="ABC");
''')

    def test_eagain_replay_yields_to_native_output_drain_without_reordering(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        branch=body(source,'if (decoderState == CDVDVideoCodec::VC_REOPEN)')
        replay='while (!m_packets.empty())'+body(branch,'while (!m_packets.empty())')
        self.run_queue(replay,r'''
 Player replay;auto a=packet('A');replay.m_packets.push_back({a});replay.m_packets.push_back({packet('B')});
 replay.SendMessage(packet('C'));replay.Replay();int priority=0;
 auto rejected=replay.m_messageQueue.Take(&priority);assert(rejected==a);replay.Retry(rejected,priority);
 std::shared_ptr<CDVDMsg>m;priority=1;
 assert(replay.m_messageQueue.Get(m,1ms,priority)==MSGQ_TIMEOUT);
 replay.Drain();assert(replay.decoderReady && replay.drains==1);
 assert(replay.m_messageQueue.Drain()=="ABC");
 Player normal;normal.SendMessage(a);normal.SendMessage(packet('B'));
 rejected=normal.m_messageQueue.Take();normal.Retry(rejected,0);assert(normal.m_messageQueue.Drain()=="AB");
 Player paused;paused.m_paused=true;paused.m_packets.push_back({a});paused.Replay();
 paused.SendMessage(packet('R'),1);priority=1;assert(paused.m_messageQueue.Get(m,1ms,priority)==MSGQ_OK && m->name=='R');
 priority=1;assert(paused.m_messageQueue.Get(m,1ms,priority)==MSGQ_TIMEOUT);paused.Drain();assert(paused.drains==0);
 paused.m_paused=false;paused.m_speed=DVD_PLAYSPEED_PAUSE;paused.Drain();assert(paused.drains==0);
 paused.m_speed=1;paused.m_messageQueue.m_drain=true;priority=1;
 assert(paused.m_messageQueue.Get(m,1ms,priority)==MSGQ_TIMEOUT);paused.Drain();assert(paused.drains==1);
 assert(paused.m_messageQueue.Drain()=="A");
''')
