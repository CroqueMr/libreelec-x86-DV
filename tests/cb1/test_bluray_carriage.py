"""Execute the adapter: exact presentation identity, either physical RPU track."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class BlurayCarriage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            raise unittest.SkipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        (root/'probe.cpp').write_text(r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
static const uint8_t bl[]={0,0,1,0x26,1,0xaa};
static const uint8_t el[]={0,0,1,0x26,1,0xbb};
static const uint8_t rpu[]={0,0,0,1,0x7c,1,0xcc};
AVPacket* packet(bool base,bool metadata) {
 AVPacket* p=av_packet_alloc();assert(p&&av_new_packet(p,6+(metadata?7:0))==0);
 memcpy(p->data,base?bl:el,6);if(metadata)memcpy(p->data+6,rpu,7);
 p->pts=15;p->dts=0;return p;
}
void exact_clock() {
 AVCodecParameters* cp=avcodec_parameters_alloc();assert(cp);
 cp->codec_type=AVMEDIA_TYPE_VIDEO;cp->codec_id=AV_CODEC_ID_HEVC;
 for(int sign : {-1,1}) {
  CBlurayDovi join;assert(join.Configure(cp,cp,{1,90000},{1,24000}));
  AVPacket* b=packet(true,false);AVPacket* e=packet(false,true);AVPacket* out=av_packet_alloc();
  b->pts=15*sign;b->dts=-15;e->pts=4*sign;e->dts=-5;e->duration=1;
  assert(join.Push(b,false)&&join.Push(e,true));
  assert(join.Take(out)==0&&out->pts==15*sign&&out->dts==-15);
  assert(join.Timing().basePts==15*sign&&join.Timing().enhancementPts==15*sign);
  assert(join.Timing().presentable&&!join.Pending());
  av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);
 }
 // A fractional presentation instant must still be rejected, not rounded into a match.
 CBlurayDovi join;assert(join.Configure(cp,cp,{1,90000},{1,24000}));
 AVPacket* e=packet(false,true);e->pts=1;e->dts=0;
 assert(!join.Push(e,true));av_packet_free(&e);avcodec_parameters_free(&cp);
}
void carriage() {
 for(bool onBase : {false,true})for(bool elFirst : {false,true})for(bool duplicate : {false,true}) {
  CBlurayDovi join;
  AVPacket* b=packet(true,onBase||duplicate);AVPacket* e=packet(false,!onBase||duplicate);
  AVPacket* out=av_packet_alloc();assert(out);
  for(bool restart : {false,true}) {
   join.Reset(restart);
   assert(join.Push(elFirst?e:b,elFirst)&&join.Push(elFirst?b:e,!elFirst));
   assert(join.Take(out)==0&&join.Timing().presentable);
   const uint8_t expected[]={0,0,1,0x26,1,0xaa,0,0,0,1,0x7e,1,0x26,1,0xbb,0,0,0,1,0x7c,1,0xcc};
   assert(out->size==sizeof(expected)&&!memcmp(out->data,expected,sizeof(expected)));
   assert(b->size==6+((onBase||duplicate)?7:0)); // Caller packet must remain untouched.
   av_packet_unref(out);assert(!join.Pending());
  }
  av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);
 }
}
void conflict() {
 for(bool elFirst : {false,true}) {
  CBlurayDovi join;AVPacket* b=packet(true,true);AVPacket* e=packet(false,true);
  e->data[e->size-1]=0xdd;
  assert(join.Push(elFirst?e:b,elFirst));
  assert(!join.Push(elFirst?b:e,!elFirst));
  join.Reset();assert(!join.Pending());
  av_packet_free(&b);av_packet_free(&e);
 }
}
void reordered() {
 CBlurayDovi join;AVPacket* out=av_packet_alloc();assert(out);
 for(int carriage : {0,1,2})for(bool elFirst : {false,true}) {
 join.Reset();int emitted=0;
 for(int i=0;i<300;++i) {
  AVPacket* b=packet(true,carriage!=1);AVPacket* e=packet(false,carriage!=0);
  b->pts=(i/3)*3+(i%3?i%3:3);e->pts=(i/3)*3+(i%3?3-i%3:3);b->dts=e->dts=i;
  if(carriage!=1)b->data[b->size-1]=b->pts%251;
  if(carriage!=0)e->data[e->size-1]=e->pts%251;
  assert(join.Push(elFirst?e:b,elFirst)&&join.Push(elFirst?b:e,!elFirst));
  while(join.Take(out)==0) {
   int expected=(emitted/3)*3+(emitted%3?emitted%3:3);
   assert(out->pts==expected&&out->data[out->size-1]==expected%251);
   ++emitted;av_packet_unref(out);
  }
  av_packet_free(&b);av_packet_free(&e);
  if(i%3==2)assert(!join.Pending()&&emitted==i+1);
 }
 }
 // The peer can carry contradictory metadata after the BL has been emitted.
 AVPacket* b=packet(true,true);AVPacket* e=packet(false,true);
 b->pts=303;e->pts=301;b->dts=e->dts=300;
 assert(join.Push(b,false)&&join.Push(e,true)&&join.Take(out)==0);av_packet_unref(out);
 e->pts=303;e->dts=301;e->data[e->size-1]=0xdd;
 assert(!join.Push(e,true));
 av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);
}
int main(int argc,char** argv) {
 assert(argc==2);
 if(!strcmp(argv[1],"clock"))exact_clock();
 else if(!strcmp(argv[1],"carriage"))carriage();
 else if(!strcmp(argv[1],"reordered"))reordered();else conflict();
}
''')
        cls.binary = root/'probe'
        result = subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
            '-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'probe.cpp'),
            '-L'+str(prefix/'lib'),'-Wl,-rpath,'+str(prefix/'lib'),
            '-lavcodec','-lavutil','-o',str(cls.binary)],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def run_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_pts_accepts_fractional_decode_clock(self):
        self.run_case('clock')

    def test_either_track_and_identical_duplicates_emit_one_unchanged_rpu(self):
        self.run_case('carriage')

    def test_conflicting_rpu_is_rejected_and_reset_clears_it(self):
        self.run_case('conflict')

    def test_reordered_layers_retire_metadata_and_check_late_conflicts(self):
        self.run_case('reordered')
