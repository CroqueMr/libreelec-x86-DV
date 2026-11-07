"""Exercise the real native AddData and video dispatch with boundary doubles."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class DualClockLifecycle(unittest.TestCase):
    def test_only_presentable_current_rpu_keeps_bound_metadata(self):
        prefix=os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:self.skipTest('Matched FFmpeg required')
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        common=body(source,'bool CDVDVideoCodecFFmpeg::GetPictureCommon(')
        start=common.rfind('  if (m_dvLayerEpoch)')
        guard=body(common[start:],'  if (m_dvLayerEpoch)')
        program=r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
extern "C" {
#include <libavutil/frame.h>
}
#include <cassert>
constexpr int DVP_FLAG_DROPPED=8;
char presentableDVPacket,decodeOnlyDVPacket;
struct VideoPicture{CDVMetadataBuffer doviMetadata;int iFlags=0;};
void check(AVFrame* m_pFrame,VideoPicture* pVideoPicture,uint64_t m_dvLayerEpoch){
 bool m_dvVideoWindow=false;
 if(m_dvLayerEpoch) GUARD
}
int main(){
 AVFrame* frame=av_frame_alloc();assert(frame);frame->pts=123;
 auto* raw=av_frame_new_side_data(frame,AV_FRAME_DATA_DOVI_RPU_BUFFER,5);assert(raw);
 raw->data[0]=25;raw->data[1]=8;
 VideoPicture p;uint8_t bytes[]={1};
 for(int mode=0;mode<5;++mode){
  assert(p.doviMetadata.Assign(bytes,1,{1,1,1}));
  raw->data[1]=mode==1?12:8;
  frame->decode_error_flags=mode==2?1:0;
  frame->pts=mode==3?AV_NOPTS_VALUE:123;
  check(frame,&p,mode==4?0:1);
  assert(bool(p.doviMetadata.Data())==(mode==0||mode==4));
 }
 assert(p.doviMetadata.Assign(bytes,1,{1,1,1}));
 av_frame_remove_side_data(frame,AV_FRAME_DATA_DOVI_RPU_BUFFER);
 check(frame,&p,1);assert(!p.doviMetadata.Data());
 av_frame_free(&frame);
}
'''.replace('GUARD',guard)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            result=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+prefix+'/include',str(root/'test.cpp'),
                '-L'+prefix+'/lib','-lavutil','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_epoch_eagain_and_el_only_do_not_advance_the_base_decoder(self):
        prefix=os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:self.skipTest('Matched FFmpeg required')
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        add=body(source,'bool CDVDVideoCodecFFmpeg::AddData(')
        player=(TREE/'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text()
        dispatch=body(player,'void CVideoPlayer::ProcessVideoData(')
        program=r'''
#define HAVE_DVBRIDGE 1
#include "cores/VideoPlayer/Interface/DemuxPacket.h"
#include <cassert>
#include <memory>
extern "C" {
#include <libavcodec/avcodec.h>
#include "dvbridge_fel.h"
}
constexpr int LOGERROR=1,VC_NOBUFFER=2;
char presentableDVPacket,decodeOnlyDVPacket;
struct CLog{template<class... T>static void Log(T...){}};
struct dvbridge_fel{};
int calls=0,submits=0;bool again=false;
extern "C" int __wrap_avcodec_send_packet(AVCodecContext*,const AVPacket*) {
 ++calls;if(again){again=false;return AVERROR(EAGAIN);}return 0;
}
extern "C" bool dvbridge_fel_submit_source(dvbridge_fel*,const AVPacket*,const dvbridge_fel_source*){++submits;return true;}
extern "C" bool dvbridge_fel_submit(dvbridge_fel*,const AVPacket*){++submits;return true;}
struct Hardware{int Check(AVCodecContext*){return 0;}};
struct CDVDVideoCodecFFmpeg {
 AVCodecContext context{};AVCodecContext* m_pCodecContext=&context;
 std::shared_ptr<dvbridge_fel> m_dvFel=std::make_shared<dvbridge_fel>();
 uint64_t m_dvLayerEpoch{};bool m_dvVideoWindow=false,m_dvFailed=false,m_eof=false,m_started=false,m_startedInput=false;
 double m_dts{};int m_iLastKeyframe=0,resets=0;
 Hardware* m_pHardware=nullptr;
 void Reset(){++resets;m_dvLayerEpoch=0;m_dvVideoWindow=false;m_eof=false;}
 void ReportDVStartup(int,const char*){}
 bool AddData(const DemuxPacket& packet) ADD
};
struct CDemuxStream{};
struct CDVDMsgDemuxerPacket{
 DemuxPacket* packet;
 CDVDMsgDemuxerPacket(DemuxPacket* p,bool drop):packet(p){assert(!drop);}
};
struct Video{
 int calls=0;
 void SendMessage(std::shared_ptr<CDVDMsgDemuxerPacket>){++calls;}
};
struct CCurrentStream{
 enum{AV_SYNC_CHECK,AV_SYNC_NONE};int avsync=AV_SYNC_CHECK,packets=0;
};
struct CVideoPlayer{
 CCurrentStream m_CurrentVideo;Video output;Video* m_VideoPlayerVideo=&output;
 void CheckStreamChanges(CCurrentStream&,CDemuxStream*){assert(false);}
 bool CheckContinuity(CCurrentStream&,DemuxPacket*){assert(false);return false;}
 void UpdateTimestamps(CCurrentStream&,DemuxPacket*){assert(false);}
 bool CheckPlayerInit(CCurrentStream&){assert(false);return false;}
 bool CheckSceneSkip(CCurrentStream&){assert(false);return false;}
 void ProcessVideoData(CDemuxStream* pStream,DemuxPacket* pPacket) DISPATCH
};
int main(){
 uint8_t bytes[]={0,0,1,0x26,1,0xaa};DemuxPacket p;p.pData=bytes;p.iSize=sizeof(bytes);
 p.pts=p.dts=1000;p.doviLayerTimes={1,1,1,1,90000,true,true};
 CDVDVideoCodecFFmpeg c;
 p.videoWindowed=true;p.videoDecodeOnly=true;
 again=true;assert(!c.AddData(p)&&calls==1&&submits==0&&c.resets==0);
 assert(!c.m_dvVideoWindow); // Rejected EAGAIN has not changed the accepted decoder epoch.
 assert(c.AddData(p)&&calls==2&&submits==1&&c.m_dvLayerEpoch==1);
 assert(c.m_dvVideoWindow);
 p.doviLayerTimes.epoch=2;again=true;
 p.videoWindowed=false;p.videoDecodeOnly=false;
 assert(!c.AddData(p)&&c.resets==1&&submits==1);
 assert(c.AddData(p)&&c.resets==1&&submits==2&&c.m_dvLayerEpoch==2);
 assert(!c.m_dvVideoWindow);
 p.doviLayerTimes.basePts=AV_NOPTS_VALUE;p.doviLayerTimes.presentable=false;
 int before=c.m_iLastKeyframe;
 assert(c.AddData(p)&&calls==4&&submits==3&&c.m_iLastKeyframe==before);
 CVideoPlayer player;player.ProcessVideoData(nullptr,&p);
 assert(player.output.calls==1&&player.m_CurrentVideo.packets==0);
 p.doviLayerTimes.epoch=1;
 assert(c.AddData(p)&&c.m_dvFailed&&calls==4&&submits==3);
}
'''.replace(' ADD',add).replace(' DISPATCH',dispatch)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            result=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+prefix+'/include',
                '-I'+str(Path(__file__).resolve().parents[2]/'CB1/src'),str(root/'test.cpp'),
                '-L'+prefix+'/lib','-lavcodec','-lavutil','-Wl,--wrap=avcodec_send_packet',
                '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
