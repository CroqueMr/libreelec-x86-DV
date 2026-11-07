"""Exercise actual Blu-ray packet ownership and rejection diagnostics."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class BlurayPairingTests(unittest.TestCase):
    def test_exact_layer_clock_and_terminal_singletons(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
        program=r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
int main() {
 AVCodecParameters* cp=avcodec_parameters_alloc();assert(cp);
 cp->codec_type=AVMEDIA_TYPE_VIDEO;cp->codec_id=AV_CODEC_ID_HEVC;
 AVPacket *b=av_packet_alloc(),*e=av_packet_alloc(),*out=av_packet_alloc();
 assert(b&&e&&out&&av_new_packet(b,6)==0&&av_new_packet(e,13)==0);
 const uint8_t base[]={0,0,1,0x26,1,0xaa},el[]={0,0,0,1,0x26,1,0xbb,0,0,1,0x7c,1,0xcc};
 memcpy(b->data,base,6);memcpy(e->data,el,13);
 for(int sign : {-1,1}) {
  CBlurayDovi join;assert(join.Configure(cp,cp,{1,90000},{1,24000}));
  e->pts=e->dts=sign;
  assert(!join.Push(e,true)&&!strcmp(join.LastError(),"layer-time-base"));
 }
 CBlurayDovi join;join.Reset(true);
 // No data loss merely because the BL window fills before its delayed RPU.
 for(int i=0;i<32;++i){b->pts=i;b->dts=i-2;assert(join.Push(b,false));}
 e->pts=40;e->dts=0;assert(join.Push(e,true));
 assert(join.Take(out)==AVERROR(EAGAIN));
 e->pts=0;e->dts=0;assert(join.Push(e,true));
 assert(join.Take(out)==0&&join.Timing().presentable&&join.Timing().basePts==0);
 av_packet_unref(out);
 // EOF is an explicit boundary; BL2 and its saved RPU2 must not vanish.
 join.Reset(true);
 for(int i=0;i<3;++i){b->pts=i;b->dts=i-2;assert(join.Push(b,false));}
 for(int i=1;i<3;++i){e->pts=i;e->dts=i;assert(join.Push(e,true));}
 assert(join.Take(out,true)==0&&!join.Timing().presentable);av_packet_unref(out);
 assert(join.Take(out,true)==0&&join.Timing().basePts==1);av_packet_unref(out);
 assert(join.Take(out,true)==0&&join.Timing().basePts==2&&join.Timing().enhancementPts==AV_NOPTS_VALUE);
 av_packet_unref(out);assert(!join.Pending());
 // Symmetric terminal EL must still reach the existing FEL owner.
 join.Reset(true);b->pts=1;b->dts=-1;
 e->pts=e->dts=0;assert(join.Push(e,true));
 e->pts=e->dts=1;assert(join.Push(e,true));assert(join.Push(b,false));
 assert(join.Take(out,true)==0&&join.Timing().basePts==1);av_packet_unref(out);
 assert(join.Take(out,true)==0&&join.Timing().basePts==AV_NOPTS_VALUE&&join.Timing().enhancementPts==1);
 av_packet_unref(out);
 av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);avcodec_parameters_free(&cp);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            result=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lm','-o',str(root/'test')],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_failure_snapshot_distinguishes_el_head_from_minimum_rpu_pts(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
template<class T> void check(const T& join, bool populated, bool resync) {
 if constexpr(requires {join.GetState();}) {
  const auto s=join.GetState();
  assert(s.resync==resync && s.restartPeer==-1);
  assert(s.basePackets==(populated?1:0) && s.elPackets==(populated?2:0));
  assert(s.rpuPackets==(populated?2:0));
  assert(s.basePts==(populated?106:AV_NOPTS_VALUE));
  assert(s.baseDts==(populated?104:AV_NOPTS_VALUE));
  assert(s.elPts==(populated?110:AV_NOPTS_VALUE));
  assert(s.elDts==(populated?108:AV_NOPTS_VALUE));
  assert(s.baseIrap==populated && !s.elIrap);
 } else assert(false && "Rejection diagnostics need the actual EL decode head");
}
int main() {
 CBlurayDovi join;join.Reset(true);check(join,false,true);
 AVPacket *b=av_packet_alloc(),*e=av_packet_alloc();
 assert(b && e && av_new_packet(b,6)==0 && av_new_packet(e,13)==0);
 const uint8_t base[]={0,0,1,0x26,1,0xaa};
 const uint8_t enhancement[]={0,0,0,1,0x02,1,0xbb,0,0,1,0x7c,1,0xcc};
 memcpy(b->data,base,6);memcpy(e->data,enhancement,13);
 b->pts=106;b->dts=104;e->pts=110;e->dts=108;
 assert(join.Push(b,false) && join.Push(e,true));
 e->pts=108;e->dts=109;assert(join.Push(e,true));
 check(join,true,true);
 assert(join.RpuPTS()==108 && "Minimum RPU PTS must not stand in for EL head PTS110");
 join.Reset();check(join,false,false);
 av_packet_free(&b);av_packet_free(&e);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lm','-o',str(root/'test')],
                capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_seek_aligned_heads_keep_decode_order_with_unequal_layer_delays(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
int presentation(int i, bool alternate) {
 return (i/3)*3+(i%3==0?3:alternate?3-i%3:i%3);
}
int main() {
 for(bool seek : {false,true}) for(int elDelay : {0,1,2})
 for(bool alternate : {false,true}) {
  CBlurayDovi join;join.Reset(seek);
  AVPacket *b=av_packet_alloc(),*e=av_packet_alloc(),*out=av_packet_alloc();
  assert(b && e && out && av_new_packet(b,6)==0 && av_new_packet(e,13)==0);
  const uint8_t base[]={0,0,1,0x02,1,0xaa};
  const uint8_t enhancement[]={0,0,0,1,0x02,1,0xbb,0,0,1,0x7c,1,0xcc};
  int emitted=0;
  for(int i=0;i<30;++i) {
   assert(av_packet_make_writable(b)==0 && av_packet_make_writable(e)==0);
   memcpy(b->data,base,6);memcpy(e->data,enhancement,13);
   b->pts=presentation(i,false);b->dts=i-1;b->data[5]=1+i;
   e->pts=presentation(i,alternate);e->dts=i-elDelay;
   e->data[6]=100+i;e->data[12]=e->pts;
   assert(join.Push(b,false) && join.Push(e,true));
   while(join.Take(out)==0) {
    const int pts=presentation(emitted,false);
    assert(out->pts==pts && out->dts==emitted-1);
    const uint8_t expected[]={0,0,1,0x02,1,uint8_t(1+emitted),
      0,0,0,1,0x7e,1,0x02,1,uint8_t(100+emitted),
      0,0,0,1,0x7c,1,uint8_t(pts)};
    assert(out->size==sizeof(expected) && !memcmp(out->data,expected,sizeof(expected)));
    ++emitted;av_packet_unref(out);
   }
  }
  assert(emitted==30 && "Aligned seek heads must not wait for equal layer DTS");
  assert(!join.Pending() && join.TakePrerollCount()==0);
  av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);
 }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lm','-o',str(root/'test')],
                capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_seek_keeps_independent_layer_clocks_and_reference_primers(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
int main() {
 CBlurayDovi join(nullptr,true);join.Reset(true);
 AVPacket *b=av_packet_alloc(),*e=av_packet_alloc(),*out=av_packet_alloc();
 assert(b && e && out && av_new_packet(b,6)==0 && av_new_packet(e,13)==0);
 const uint8_t base[]={0,0,1,0x26,1,0xaa};
 const uint8_t enhancement[]={0,0,0,1,0x26,1,0xbb,0,0,1,0x7c,1,0xcc};
 memcpy(b->data,base,6);memcpy(e->data,enhancement,13);
 // Equal decode time is not equal source identity. Keep the BL reference;
 // its RPU lay before the native seek point and it must never be displayed.
 b->pts=106;b->dts=104;e->pts=110;e->dts=104;
 assert(join.Push(b,false) && join.Push(e,true) && join.Take(out)==AVERROR(EAGAIN));
 e->pts=111;e->dts=107;e->data[12]=111;
 assert(join.Push(e,true) && join.Take(out)==0);
 auto timing=join.Timing();
 assert(out->pts==106 && out->dts==104 && out->size==15);
 assert(timing.basePts==106 && timing.enhancementPts==110 && !timing.presentable);
 const auto epoch=timing.epoch;
 av_packet_unref(out);
 // The saved RPU110 is attached to BL110, not to the next EL111.
 b->pts=110;b->dts=105;
 assert(join.Push(b,false) && join.Take(out)==0);
 timing=join.Timing();
 assert(timing.basePts==110 && timing.enhancementPts==111 && timing.presentable);
 assert(timing.epoch==epoch && out->data[out->size-1]==0xcc);
 av_packet_unref(out);
 join.Reset(true);
 assert(join.Timing().epoch==0 && !join.Pending());
 b->pts=e->pts=20;b->dts=e->dts=18;e->data[12]=20;
 assert(join.Push(b,false) && join.Push(e,true) && join.Take(out)==0);
 assert(join.Timing().epoch!=epoch && join.Timing().presentable);
 av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lm','-o',str(root/'test')],
                capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_rejection_identifies_the_failed_guard(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
#include <string_view>
template<class T> std::string_view reason(const T& join) {
 if constexpr(requires{join.LastError();}) return join.LastError();
 return "unknown";
}
template<class T> void seekReset(T& join) {
 if constexpr(requires{join.Reset(true);}) join.Reset(true); else join.Reset();
}
int main() {
 CBlurayDovi join(nullptr,true);
 assert(!join.Push(nullptr,false));
 assert(reason(join)=="packet");
 AVPacket* p=av_packet_alloc(); assert(p && av_new_packet(p,6)==0);
 const unsigned char nal[]={0,0,1,0x26,1,0xaa};
 std::memcpy(p->data,nal,6); p->pts=0;
 // RPU may arrive on BL instead; an EL without it is not itself malformed.
 assert(join.Push(p,true));
 AVPacket* waiting=av_packet_alloc();assert(waiting);
 assert(join.Take(waiting)==AVERROR(EAGAIN));av_packet_free(&waiting);
 join.Reset();
 for(int i=0;i<32;++i){p->pts=i;assert(join.Push(p,false));}
 assert(!join.Push(p,false)); assert(reason(join)=="base-queue");
 join.Reset(); p->pts=0; assert(join.Push(p,false));
 assert(reason(join).empty());
 // A seek may start with an un-timestamped partial access unit.
 seekReset(join); p->pts=AV_NOPTS_VALUE;
 assert(join.Push(p,false));
 // The first base access unit has no corresponding EL/RPU after seek.
 seekReset(join);
 for(int i=1;i<=32;++i){p->pts=i;assert(join.Push(p,false));}
 AVPacket* el=av_packet_alloc();assert(el && av_new_packet(el,13)==0);
 const unsigned char enhancement[]={0,0,0,1,0x26,1,0xbb,0,0,1,0x7c,1,0xcc};
 std::memcpy(el->data,enhancement,13);
 for(int i=2;i<=32;++i){el->pts=el->dts=i;assert(join.Push(el,true));}
 AVPacket* out=av_packet_alloc();assert(join.Take(out)==0 && out->pts==1);
 assert(!join.Timing().presentable);
 p->pts=33;assert(join.Push(p,false));
 av_packet_unref(out);
 // A single future EL reference is not proof that reordered BL pictures are orphaned.
 seekReset(join);
 for(int i=1;i<=32;++i){p->pts=i;assert(join.Push(p,false));}
 el->pts=100;assert(join.Push(el,true));
 p->pts=33;assert(!join.Push(p,false));assert(reason(join)=="base-queue");
 // Even full disjoint windows are invalid, not successful resynchronization.
 for(int i=101;i<131;++i){el->pts=i;assert(join.Push(el,true));}
 assert(!join.Push(p,false));assert(reason(join)=="base-queue");
 // Once synchronized, a full queue remains an error, never silent data loss.
 join.Reset();
 for(int i=1;i<=32;++i){p->pts=i;assert(join.Push(p,false));}
 for(int i=2;i<=32;++i){el->pts=el->dts=i;assert(join.Push(el,true));}
 p->pts=33;assert(!join.Push(p,false));assert(reason(join)=="base-queue");
 // MPEG-TS can restart a layer clock while a previous access unit is queued.
 // Never join old BL pictures with the new segment's EL/RPU.
 join.Reset();p->pts=p->dts=200;el->pts=el->dts=200;
 assert(join.Push(p,false) && join.Push(el,true) && join.Take(out)==0);
 av_packet_unref(out);
 p->pts=p->dts=201;assert(join.Push(p,false));
 p->pts=p->dts=20;assert(join.Push(p,false));
 el->pts=el->dts=20;assert(join.Push(el,true));
 assert(join.Take(out)==0 && out->pts==20);av_packet_unref(out);
 // Delayed old-peer packets must not clear fresh pictures or shift EL decode order.
 for(bool enhancementFirst : {false,true}) {
   join.Reset();p->pts=p->dts=200;el->pts=el->dts=200;el->data[6]=200;el->data[12]=200;
   assert(join.Push(p,false) && join.Push(el,true) && join.Take(out)==0);av_packet_unref(out);
   AVPacket* first=enhancementFirst?el:p;AVPacket* peer=enhancementFirst?p:el;
   first->pts=first->dts=201;assert(join.Push(first,enhancementFirst));
   assert(join.Take(out)==AVERROR(EAGAIN));
   first->pts=first->dts=20;if(enhancementFirst)el->data[6]=el->data[12]=20;
   assert(join.Push(first,enhancementFirst));assert(join.Take(out)==AVERROR(EAGAIN));
   peer->pts=peer->dts=202;if(!enhancementFirst)el->data[6]=el->data[12]=202;
   assert(join.Push(peer,!enhancementFirst));assert(join.Take(out)==AVERROR(EAGAIN));
   peer->pts=peer->dts=20;el->data[6]=el->data[12]=20;
   assert(join.Push(peer,!enhancementFirst));
   assert(join.Take(out)==0 && out->pts==20 && out->data[5]==0xaa && out->data[14]==20 && out->data[out->size-1]==20);
   av_packet_unref(out);
   p->pts=p->dts=21;el->pts=el->dts=21;el->data[6]=el->data[12]=21;
   assert(join.Push(p,false) && join.Push(el,true));
   assert(join.Take(out)==0 && out->pts==21 && out->data[14]==21 && out->data[out->size-1]==21);
   av_packet_unref(out);
 }
 // Unknown peer clocks cannot complete a restart; explicit flush clears the barrier.
 join.Reset();p->pts=p->dts=200;el->pts=el->dts=200;
 assert(join.Push(p,false) && join.Push(el,true) && join.Take(out)==0);av_packet_unref(out);
 p->pts=p->dts=20;assert(join.Push(p,false));
 el->pts=20;el->dts=AV_NOPTS_VALUE;
 assert(!join.Push(el,true));assert(reason(join)=="restart-peer-dts");
 join.Reset();assert(join.Push(p,false) && join.Push(el,true) && join.Take(out)==0);av_packet_unref(out);
 p->pts=p->dts=10;
 assert(!join.Push(p,false));assert(reason(join)=="missing-peer-dts");
 seekReset(join);p->pts=AV_NOPTS_VALUE;p->dts=AV_NOPTS_VALUE;
 for(int i=0;i<32;++i)assert(join.Push(p,false));
 assert(!join.Push(p,false));assert(reason(join)=="seek-preroll-limit");
 // Malformed enhancement data is rejected even during seek recovery.
 seekReset(join);el->pts=2;el->data[4]=0x80;
 assert(!join.Push(el,true));assert(reason(join)=="nal-header");
 av_packet_free(&out);av_packet_free(&el);
 av_packet_free(&p);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'), '-I'+str(prefix/'include'), str(root/'test.cpp'),
                '-L'+str(prefix/'lib'), '-lavcodec', '-lavutil', '-lm', '-o',str(root/'test')],
                capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
