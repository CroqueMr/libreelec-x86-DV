"""Irrecoverable FEL must stop playback, not leave the last frame indefinitely."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class FELTerminalTests(unittest.TestCase):
    def test_final_drain_keeps_error_observable_until_parent_consumes_it(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        has=body(source,'bool CVideoPlayerVideo::HasData(')
        send=body(source,'inline void CVideoPlayerVideo::SendMessage(')
        flush=body(source,'inline void CVideoPlayerVideo::FlushMessages(')
        drain=source.split('else if (pMsg->IsType(CDVDMsg::VIDEO_DRAIN))',1)[1].split('else if',1)[0].strip()
        program=r'''
#include <atomic>
#include <cassert>
#include <memory>
#include <mutex>
struct CDVDMsg{enum{VIDEO_DRAIN=1,PLAYER_ABORT=2};int type;bool IsType(int t){return type==t;}};
struct Queue{int queued=0;void Put(std::shared_ptr<CDVDMsg>,int){++queued;}void Flush(){queued=0;}
 int GetDataSize()const{return 0;}int GetLevel(){return 0;}int GetPacketCount(int)const{return queued;}};
constexpr int DVD_CODEC_CTRL_DRAIN=1;
struct Codec{void SetCodecControl(int){}};
struct CVideoPlayerVideo{
 mutable std::atomic_uint m_drainPending=0;std::mutex m_drainMutex;
 Queue m_messageQueue,m_messageParent;struct{void SetLevelVQ(int){}}m_processInfo;
 bool m_bStop=false;Codec codec;Codec*m_pVideoCodec=&codec;
 bool HasData()const @HAS@
 void SendMessage(std::shared_ptr<CDVDMsg>pMsg,int priority) @SEND@
 void FlushMessages() @FLUSH@
 bool ProcessDecoderOutput(double&,double&){++m_messageParent.queued;return false;}
 void Drain(){double frametime=0,pts=0;@DRAIN@}
};
int main(){CVideoPlayerVideo p;assert(!p.HasData());
 p.SendMessage(std::make_shared<CDVDMsg>(CDVDMsg{CDVDMsg::VIDEO_DRAIN}),0);
 assert(p.HasData());p.m_messageQueue.queued=0;assert(p.HasData());
 p.Drain();assert(!p.m_drainPending && p.HasData());
 p.m_messageParent.queued=0;assert(!p.HasData());
 p.SendMessage(std::make_shared<CDVDMsg>(CDVDMsg{CDVDMsg::VIDEO_DRAIN}),0);
 p.SendMessage(std::make_shared<CDVDMsg>(CDVDMsg{CDVDMsg::VIDEO_DRAIN}),0);
 p.Drain();p.m_messageParent.queued=0;assert(p.HasData());
 p.FlushMessages();assert(!p.HasData());}
'''.replace('@HAS@',has).replace('@SEND@',send).replace('@DRAIN@',drain).replace('@FLUSH@',flush)
        self.compile_run(program)

    def test_actual_fel_decoder_reports_terminal_failure_and_keeps_vanilla_result(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        native=body(source,'CDVDVideoCodec::VCReturn CDVDVideoCodecFFmpeg::GetPicture(')
        control=body(source,'void CDVDVideoCodecFFmpeg::SetCodecControl(').split('  if (m_pCodecContext)',1)[0]+'}'
        program=r'''
#include <cassert>
#include <deque>
#include <memory>
#include <cstdint>
#define HAVE_DVBRIDGE 1
#define HAVE_LIBVA 1
constexpr int64_t AV_NOPTS_VALUE=INT64_MIN;
constexpr unsigned DVD_CODEC_CTRL_DRAIN=1,DVD_CODEC_CTRL_POLL=2,DVD_CODEC_CTRL_DROP_ANY=4;
constexpr unsigned DVP_FLAG_DROPPED=8;
constexpr int VA_STATUS_SUCCESS=0;
using VASurfaceID=unsigned;
struct Buffer{void* data=nullptr;};
struct AVVAAPIDeviceContext{void* display=(void*)123;};
struct Device{void* hwctx=nullptr;};
struct AVHWFramesContext{void* device_ref=nullptr;Device* device_ctx=nullptr;};
AVVAAPIDeviceContext va;Device device{&va};AVHWFramesContext pool{nullptr,&device};Buffer frameBuffer{&pool};
int waited=0,syncError=0;
int vaSyncSurface(void* display,unsigned surface){assert(display==(void*)123 && surface==17);++waited;return syncError;}
struct AVFrame{Buffer* hw_frames_ctx=&frameBuffer;uint8_t* data[4]={nullptr,nullptr,nullptr,(uint8_t*)17};};
void av_frame_free(AVFrame** f){delete *f;*f=nullptr;}
struct Metadata{bool valid=true;int Binding()const{return 1;}const void* Data()const{return valid?this:nullptr;}};
struct VideoPicture{int64_t doviSourcePts=1;Metadata doviMetadata;unsigned iFlags=0;
 int doviSourceBinding=1;
 std::shared_ptr<AVFrame>doviEnhancement;int doviEnhancementBinding=0;
 void Reset(){}void CopyRef(const VideoPicture&v){*this=v;}};
struct Context{Buffer* hw_frames_ctx=nullptr;};
struct Fel{bool failed=false,exhausted=false;int result=0;};
bool dvbridge_fel_failed(Fel*f){return f->failed;}
bool dvbridge_fel_exhausted(Fel*f){return f->exhausted;}
int dvbridge_fel_take(Fel*f,int64_t,AVFrame**out){if(f->result==1)*out=new AVFrame;return f->result;}
bool dvbridge_fel_device(Fel*,void*){return true;}
bool dvbridge_fel_drain(Fel*){return true;}
enum{LOGWARNING,LOGERROR};
struct CLog{template<class... T>static void Log(T...){}};
struct CDVDVideoCodec{enum VCReturn{VC_NONE,VC_BUFFER,VC_PICTURE,VC_ERROR,VC_EOF,VC_FATAL};};
struct CDVDVideoCodecFFmpeg:CDVDVideoCodec{
 std::shared_ptr<Fel>m_dvFel=std::make_shared<Fel>();bool m_dvFailed=false,m_dvNativeOutput=false;
 uint64_t m_dvLayerEpoch=0;
 std::deque<std::shared_ptr<VideoPicture>>m_dvPending;Context context;Context*m_pCodecContext=&context;
 unsigned m_codecControlFlags=0;static constexpr unsigned DVEnhancementPendingPictures=16;
 int reads=0;VCReturn baseResult=VC_BUFFER;void ReportDVStartup(unsigned,const char*){}
 VCReturn GetBasePicture(VideoPicture*){++reads;return baseResult;}
 VCReturn GetPicture(VideoPicture*pVideoPicture) @@NATIVE@@
 void SetCodecControl(int flags) @@CONTROL@@
};
int main(){
 VideoPicture out;
 for(int failure=0;failure<2;failure++){
  CDVDVideoCodecFFmpeg c;c.m_dvFailed=failure==0;c.m_dvFel->failed=failure==1;
  assert(c.GetPicture(&out)==CDVDVideoCodec::VC_FATAL);
 }
 CDVDVideoCodecFFmpeg missingTime;
 auto base=std::make_shared<VideoPicture>();base->doviSourcePts=AV_NOPTS_VALUE;
 missingTime.m_dvPending.push_back(base);
 assert(missingTime.GetPicture(&out)==CDVDVideoCodec::VC_FATAL);
 CDVDVideoCodecFFmpeg lost;lost.m_dvFel->result=-1;
 lost.m_dvPending.push_back(std::make_shared<VideoPicture>());
 assert(lost.GetPicture(&out)==CDVDVideoCodec::VC_FATAL);
 CDVDVideoCodecFFmpeg incomplete;incomplete.m_dvFel->result=-1;incomplete.m_dvFel->exhausted=true;
 incomplete.m_dvPending.push_back(std::make_shared<VideoPicture>());
 assert(incomplete.GetPicture(&out)==CDVDVideoCodec::VC_FATAL);
 CDVDVideoCodecFFmpeg cleanEnd;cleanEnd.baseResult=CDVDVideoCodec::VC_EOF;
 assert(cleanEnd.GetPicture(&out)==CDVDVideoCodec::VC_EOF);
 CDVDVideoCodecFFmpeg readyThenFailed;readyThenFailed.m_dvFailed=true;
 readyThenFailed.m_dvFel->failed=true;readyThenFailed.m_dvFel->result=1;
 readyThenFailed.m_dvPending.push_back(std::make_shared<VideoPicture>());
 assert(readyThenFailed.GetPicture(&out)==CDVDVideoCodec::VC_PICTURE);
 assert(readyThenFailed.GetPicture(&out)==CDVDVideoCodec::VC_FATAL);
 CDVDVideoCodecFFmpeg poll;poll.SetCodecControl(DVD_CODEC_CTRL_DRAIN|DVD_CODEC_CTRL_POLL);
 assert(poll.m_codecControlFlags==DVD_CODEC_CTRL_POLL);
 assert(poll.GetPicture(&out)==CDVDVideoCodec::VC_BUFFER && poll.reads==0);
 poll.SetCodecControl(0);poll.baseResult=CDVDVideoCodec::VC_PICTURE;
 assert(poll.GetPicture(&out)==CDVDVideoCodec::VC_BUFFER && poll.reads==1);
 CDVDVideoCodecFFmpeg valid;valid.m_dvFel->result=1;
 valid.m_dvPending.push_back(std::make_shared<VideoPicture>());
 assert(valid.GetPicture(&out)==CDVDVideoCodec::VC_PICTURE && out.doviEnhancement);
 assert(waited==0 && "Displayed FEL retains its existing renderer synchronization");
 CDVDVideoCodecFFmpeg preroll;preroll.m_dvFel->result=1;
 auto dropped=std::make_shared<VideoPicture>();dropped->iFlags=DVP_FLAG_DROPPED;
 preroll.m_dvPending.push_back(dropped);out=VideoPicture{};
 assert(preroll.GetPicture(&out)==CDVDVideoCodec::VC_PICTURE && out.doviEnhancement);
 assert(waited==1 && "Discarded FEL must consume decode completion before bypassing the renderer");
 CDVDVideoCodecFFmpeg badSync;badSync.m_dvFel->result=1;badSync.m_dvPending.push_back(dropped);
 syncError=1;out=VideoPicture{};
 assert(badSync.GetPicture(&out)==CDVDVideoCodec::VC_FATAL && !out.doviEnhancement && waited==2);
 syncError=0;
 CDVDVideoCodecFFmpeg invalidMetadata;invalidMetadata.m_dvLayerEpoch=1;invalidMetadata.m_dvFel->result=1;
 auto invalid=std::make_shared<VideoPicture>();invalid->doviMetadata.valid=false;
 invalidMetadata.m_dvPending.push_back(invalid);
 assert(invalidMetadata.GetPicture(&out)==CDVDVideoCodec::VC_FATAL);
 CDVDVideoCodecFFmpeg wait;
 assert(wait.GetPicture(&out)==CDVDVideoCodec::VC_BUFFER);
 CDVDVideoCodecFFmpeg vanilla;vanilla.m_dvFel.reset();vanilla.baseResult=CDVDVideoCodec::VC_ERROR;
 assert(vanilla.GetPicture(&out)==CDVDVideoCodec::VC_ERROR);
}
'''.replace('@@NATIVE@@',native).replace('@@CONTROL@@',control)
        self.compile_run(program)

    def test_native_player_forwards_fatal_error_to_existing_abort_without_reopen(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        native=body(source,'bool CVideoPlayerVideo::ProcessDecoderOutput(')
        native=native.split('  // if decoder was flushed',1)[0]+'return false;\n}'
        program=r'''
#include <cassert>
#include <memory>
#include <string>
#include <utility>
enum{LOGERROR};
struct CLog{template<class...T>static void Log(T...){}};
struct CDVDMsg{enum{PLAYER_ABORT=1};};
struct CDVDMsgBool{int type;bool error;CDVDMsgBool(int t,bool e):type(t),error(e){}};
struct CDVDVideoCodec{enum VCReturn{VC_NONE,VC_BUFFER,VC_PICTURE,VC_ERROR,VC_FATAL};
 VCReturn result=VC_FATAL;VCReturn GetPicture(void*){return result;}};
struct Queue{int aborts=0;void Put(std::shared_ptr<CDVDMsgBool>m){
 assert(m->type==CDVDMsg::PLAYER_ABORT && m->error);++aborts;}};
struct CVideoPlayerVideo{struct{std::string stereoMode="left_right";}m_picture;
 CDVDVideoCodec codec;CDVDVideoCodec*m_pVideoCodec=&codec;Queue m_messageParent;
 struct{bool aborted=false;void Abort(){aborted=true;}bool ReceivedAbortRequest(){return aborted;}}m_messageQueue;
 bool ProcessDecoderOutput(double&frametime,double&pts) @@NATIVE@@
};
int main(){CVideoPlayerVideo player;double frame=0,pts=0;
 assert(!player.ProcessDecoderOutput(frame,pts));
 assert(player.m_messageParent.aborts==1 && player.m_picture.stereoMode=="left_right" && player.m_messageQueue.aborted);
 assert(!player.ProcessDecoderOutput(frame,pts) && player.m_messageParent.aborts==1);
 for(auto status:{CDVDVideoCodec::VC_NONE,CDVDVideoCodec::VC_BUFFER,CDVDVideoCodec::VC_ERROR}){
  CVideoPlayerVideo ordinary;ordinary.codec.result=status;
  assert(!ordinary.ProcessDecoderOutput(frame,pts) && ordinary.m_messageParent.aborts==0 && !ordinary.m_messageQueue.aborted);
 }
}
'''.replace('@@NATIVE@@',native)
        self.compile_run(program)

    def compile_run(self,program):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'check.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

if __name__=='__main__':unittest.main()
