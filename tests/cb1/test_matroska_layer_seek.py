"""A native Matroska seek must retain both declared Dolby layer keys."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_mkv_dual_track import matroska


def element(number, data):
    tag=number.to_bytes((number.bit_length()+7)//8,'big')
    size=(0x80|len(data)).to_bytes(1,'big') if len(data)<127 else (0x4000|len(data)).to_bytes(2,'big')
    return tag+size+data


class MatroskaLayerSeek(unittest.TestCase):
    def test_seek_keeps_earlier_cluster_of_the_other_layer(self):
        prefix=os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:self.skipTest('Matched FFmpeg required')
        # Same key time in separate clusters, with either layer stored first.
        # Changing the seek to retain only the selected layer's cluster loses
        # the peer key and makes the existing exact assembler wait forever.
        program=r'''
extern "C" {
#include <libavformat/avformat.h>
}
#include <cassert>
int main(int argc,char**argv) {
 assert(argc==4);av_log_set_level(AV_LOG_QUIET);
 const bool grouped=argv[2][0]=='1';const int first=argv[3][0]-'0';
 for(int selected=0;selected<2;selected++) {
  AVFormatContext* f=nullptr;assert(avformat_open_input(&f,argv[1],nullptr,nullptr)==0);
  f->flags|=AVFMT_FLAG_NOPARSE|AVFMT_FLAG_NOFILLIN;
  AVPacket* p=av_packet_alloc();assert(p);
  while(av_read_frame(f,p)>=0)av_packet_unref(p);
  assert(f->nb_stream_groups==unsigned(grouped));
  assert(av_seek_frame(f,selected,1000,AVSEEK_FLAG_BACKWARD)>=0);
  unsigned mask=0;
  while(av_read_frame(f,p)>=0) {
   if(p->pts==1000 && (p->flags&AV_PKT_FLAG_KEY))mask|=1u<<p->stream_index;
   av_packet_unref(p);
  }
  const unsigned expected=grouped||first==selected?3:1u<<selected;
  assert(mask==expected && "Native seek lost the peer key or changed an ungrouped seek");
  av_packet_free(&p);avformat_close_input(&f);
 }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            compiled=subprocess.run(['c++','-std=c++20','-I'+prefix+'/include',str(root/'test.cpp'),
                '-L'+prefix+'/lib','-lavformat','-lavcodec','-lavutil','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            for grouped,first in ((True,0),(True,1),(False,0),(False,1)):
                header=matroska(2,1 if grouped else -1)
                cluster=header.index(bytes.fromhex('1f43b675'))
                body=header[header.index(bytes.fromhex('1549a966')):cluster]
                for time,track in ((0,0),(0,1),(1000,first),(1000,1-first),(2000,0),(2000,1)):
                    payload=b'\0\0\0\3\x26\1\xaa'
                    if track:payload+=b'\0\0\0\3\x7c\1\xcc'
                    block=element(0xa3,bytes([0x81+track,0,0,0x80])+payload)
                    body+=element(0x1f43b675,element(0xe7,time.to_bytes(2,'big'))+block)
                # Rebuild the segment size after extending the original fixture.
                data=header[:header.index(bytes.fromhex('18538067'))]+element(0x18538067,body)
                (root/'test.mkv').write_bytes(data)
                ran=subprocess.run([str(root/'test'),str(root/'test.mkv'),str(int(grouped)),str(first)],capture_output=True,text=True)
                self.assertEqual(ran.returncode,0,ran.stderr)
