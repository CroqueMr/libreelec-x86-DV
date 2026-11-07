"""Run actual packet tagging and late picture validation for both video consumers."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE,body


class BlurayVideoDisposition(unittest.TestCase):
    def test_window_markers_do_not_change_unrestricted_sources_and_missing_markers_fail_closed(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        add=body(source,'bool CDVDVideoCodecFFmpeg::AddData(')
        start=add.index('\n#ifdef HAVE_DVBRIDGE',add.index('  avpkt->size = packet.iSize;'))
        end=add.index('    avpkt->flags |= AV_PKT_FLAG_DISCARD;',start)+len('    avpkt->flags |= AV_PKT_FLAG_DISCARD;')
        tag=add[start:end]
        common=body(source,'bool CDVDVideoCodecFFmpeg::GetPictureCommon(')
        late='if (m_dvLayerEpoch)'+body(common[common.rfind('if (m_dvLayerEpoch)'):],'if (m_dvLayerEpoch)')
        program=r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
#define HAVE_DVBRIDGE 1
constexpr int AV_PKT_FLAG_DISCARD=4,AV_FRAME_FLAG_CORRUPT=1,DVP_FLAG_DROPPED=8;
constexpr int64_t AV_NOPTS_VALUE=INT64_MIN;
constexpr int AV_FRAME_DATA_DOVI_RPU_BUFFER=1;
char presentableDVPacket,decodeOnlyDVPacket;
struct Packet {bool videoDecodeOnly=false,videoWindowed=false;};
struct AVPacket {int flags=0;void* opaque=nullptr;};
struct AVFrame {int64_t pts=200;int decode_error_flags=0,flags=0;void* opaque=nullptr;};
struct Raw {uint8_t bytes[5]={25,8,1,2,3};uint8_t* data=bytes;int size=5;}raw;
const Raw* av_frame_get_side_data(AVFrame*,int){return &raw;}
struct Picture {int iFlags=0;struct {bool valid=true;void Reset(){valid=false;}}doviMetadata;};
struct Codec {
 bool m_dvFel=false,m_dvVideoWindow=false;uint64_t m_dvLayerEpoch=1;AVFrame frame;AVFrame* m_pFrame=&frame;
 AVPacket Tag(const Packet& packet){AVPacket out;AVPacket* avpkt=&out;TAG;return out;}
 Picture Validate(){Picture out;Picture* pVideoPicture=&out;LATE;return out;}
};
int main(){
 for(bool paired:{false,true})for(bool windowed:{false,true})for(bool hidden:{false,true}){
  Codec c;c.m_dvFel=paired;c.m_dvVideoWindow=windowed;c.m_dvLayerEpoch=paired?1:0;
  Packet p{hidden,windowed};auto packet=c.Tag(p);
  assert(bool(packet.flags&AV_PKT_FLAG_DISCARD)==(!paired&&hidden));
  if(paired&&windowed)assert(packet.opaque==(hidden?&decodeOnlyDVPacket:&presentableDVPacket));
  else assert(!packet.opaque && "Unrestricted sources must keep their existing packet metadata");
  c.frame.opaque=packet.opaque;
  auto picture=c.Validate();
  assert(picture.doviMetadata.valid);
  if(paired&&windowed)assert(bool(picture.iFlags&DVP_FLAG_DROPPED)==hidden);
 }
 for(bool windowed:{false,true}){
  Codec c;c.m_dvFel=true;c.m_dvVideoWindow=windowed;
  c.frame.opaque=nullptr;assert(c.Validate().doviMetadata.valid==!windowed);
  int unknown;c.frame.opaque=&unknown;assert(c.Validate().doviMetadata.valid==!windowed);
  c.frame.opaque=&presentableDVPacket;c.frame.decode_error_flags=1;
  assert(!c.Validate().doviMetadata.valid); // Original corrupt-picture refusal remains strict.
 }
}
'''.replace('TAG',tag).replace('LATE',late)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'test.cpp').write_text(program)
            result=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                str(folder/'test.cpp'),'-o',str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
