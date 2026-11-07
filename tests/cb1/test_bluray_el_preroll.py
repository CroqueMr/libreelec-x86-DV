"""Keep EL native decode order, including its independent seek acquisition."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class BlurayEnhancementPreroll(unittest.TestCase):
    def test_el_decode_prefix_is_preserved_with_its_source_clock(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
AVPacket* packet(bool el,int pts,int dts,int type) {
 AVPacket* p=av_packet_alloc();assert(p && av_new_packet(p,el?13:6)==0);
 const uint8_t b[]={0,0,1,uint8_t(type<<1),1,0xaa};
 const uint8_t e[]={0,0,0,1,uint8_t(type<<1),1,uint8_t(pts),0,0,1,0x7c,1,uint8_t(pts)};
 memcpy(p->data,el?e:b,p->size);p->pts=pts;p->dts=dts;return p;
}
int main() {
 CBlurayDovi join;join.Reset(true);
 AVPacket* out=av_packet_alloc();assert(out);
 // RPU60 is in the fourth EL AU, not its decode head. No EL references
 // may be discarded or assigned the BL clock merely to align these heads.
 for(int pts : {60,40,50}) {
  auto* b=packet(false,pts,pts==60?3:pts==40?4:5,pts==60?21:1);
  assert(join.Push(b,false));av_packet_free(&b);
 }
 const int times[]={30,10,20,60,40,50};
 for(int i=0;i<6;++i) {
  auto* e=packet(true,times[i],i,i==3?21:1);
  assert(join.Push(e,true));av_packet_free(&e);
  if(i<3)assert(join.Take(out)==AVERROR(EAGAIN));
 }
 const int bases[]={60,40,50};
 for(int i=0;i<3;++i) {
  assert(join.Take(out)==0);
  const auto timing=join.Timing();
  assert(timing.basePts==bases[i] && timing.enhancementPts==times[i]);
  assert(out->data[14]==times[i]);
  assert(timing.presentable && out->size==22);
  assert(out->data[out->size-1]==bases[i]);
  av_packet_unref(out);
 }
 assert(join.GetState().elPackets==3); // Still native CRA60, leading40,50.
 join.Reset(true);assert(!join.Pending());
 auto* unknown=packet(true,1,1,21);unknown->pts=AV_NOPTS_VALUE;
 assert(!join.Push(unknown,true) && !strcmp(join.LastError(),"packet"));
 av_packet_free(&unknown);av_packet_free(&out);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lm','-o',str(root/'test')],
                capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
