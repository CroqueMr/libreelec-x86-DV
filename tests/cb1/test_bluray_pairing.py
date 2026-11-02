"""Exercise actual Blu-ray packet ownership and rejection diagnostics."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class BlurayPairingTests(unittest.TestCase):
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
 e->pts=100;e->dts=109;assert(join.Push(e,true));
 check(join,true,true);
 assert(join.RpuPTS()==100 && "Minimum RPU PTS must not stand in for EL head PTS110");
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

    def test_seek_common_irap_accepts_different_layer_decode_delays(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
int main() {
 const uint8_t base[]={0,0,1,0x02,1,0xaa};
 const uint8_t enhancement[]={0,0,0,1,0x26,1,0xbb,0,0,1,0x7c,1,0xcc};
 AVPacket *b=av_packet_alloc(),*e=av_packet_alloc(),*out=av_packet_alloc();
 assert(b && e && out && av_new_packet(b,sizeof(base))==0 && av_new_packet(e,sizeof(enhancement))==0);
 memcpy(b->data,base,sizeof(base));memcpy(e->data,enhancement,sizeof(enhancement));
 // Same presentation epoch, distinct per-layer decoder reorder delays.
 CBlurayDovi pair;pair.Reset(true);
 for(int i=0;i<32;++i){
  assert(av_packet_make_writable(b)==0);
  b->pts=383762006+3754*i;b->dts=b->pts-7508;b->data[3]=i==6?0x26:0x02;
  assert(pair.Push(b,false));
 }
 e->pts=e->dts=383784530;assert(pair.Push(e,true));
 assert(pair.Take(out)==0 && "A common independent random-access picture must recover despite different DTS");
 const uint8_t joined[]={0,0,1,0x26,1,0xaa,0,0,0,1,0x7e,1,0x26,1,0xbb,0,0,0,1,0x7c,1,0xcc};
 assert(out->pts==383784530 && out->dts==383777022);
 assert(out->size==sizeof(joined) && !memcmp(out->data,joined,sizeof(joined)));
 assert(pair.TakePrerollCount()==6);av_packet_unref(out);
 // EL can precede BL too; compare decode times within each layer, not across layers.
 for(int prefix : {1,6}){
  pair.Reset(true);
  for(int i=0;i<=prefix;++i){
   assert(av_packet_make_writable(e)==0);e->pts=e->dts=106-prefix+i;
   e->data[4]=i==prefix?0x26:0x02;assert(pair.Push(e,true));
  }
  assert(av_packet_make_writable(b)==0);b->pts=106;b->dts=104;b->data[3]=0x26;
  assert(pair.Push(b,false) && pair.Take(out)==0);
  assert(out->pts==106 && out->dts==104 && out->size==sizeof(joined));
  assert(!memcmp(out->data,joined,sizeof(joined)) && pair.TakePrerollCount()==prefix);
  av_packet_unref(out);
 }
 // Already aligned heads need no retirement proof or coincident IRAP boundaries.
 pair.Reset(true);assert(av_packet_make_writable(e)==0);
 b->pts=e->pts=106;b->dts=e->dts=104;b->data[3]=0x26;e->data[4]=0x02;
 assert(pair.Push(b,false) && pair.Push(e,true) && pair.Take(out)==0);
 assert(out->pts==106 && out->dts==104 && out->data[12]==0x02);
 assert(pair.TakePrerollCount()==0);av_packet_unref(out);
 // A common PTS is insufficient without independent access on both layers.
 for(bool baseIrap : {false,true}) {
  pair.Reset(true);
  for(int i=0;i<32;++i){assert(av_packet_make_writable(b)==0);b->pts=100+i;b->dts=98+i;b->data[3]=(i==6 && baseIrap)?0x26:0x02;assert(pair.Push(b,false));}
  e->pts=e->dts=106;e->data[4]=baseIrap?0x02:0x26;assert(pair.Push(e,true));
  assert(pair.Take(out)==AVERROR(EAGAIN));
  b->pts=132;b->dts=130;assert(!pair.Push(b,false));
 }
 av_packet_free(&b);av_packet_free(&e);av_packet_free(&out);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),'-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lm','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_seek_prefix_is_retired_in_decode_order_not_minimum_rpu_pts(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        # Trace-derived GOP: presentation 3,1,2,6,4,5 with monotone decode time.
        # Captured seeks start EL six, one and seven decode units after BL.
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>
int pts(int i) {return 3*(i/3)+(i%3==0?3:i%3);}
int main() {
 for(int offset : {6,1,7}) {
   CBlurayDovi join;join.Reset(true);
   AVPacket* p=av_packet_alloc();AVPacket* el=av_packet_alloc();AVPacket* out=av_packet_alloc();
   assert(p && el && out && av_new_packet(p,6)==0 && av_new_packet(el,13)==0);
   const unsigned char base[]={0,0,1,0x26,1,0xaa};
   const unsigned char enhancement[]={0,0,0,1,0x26,1,0xbb,0,0,1,0x7c,1,0xcc};
   std::memcpy(p->data,base,6);std::memcpy(el->data,enhancement,13);
   for(int i=0;i<32;++i) {p->pts=pts(i);p->dts=i;assert(join.Push(p,false));assert(join.Take(out)==AVERROR(EAGAIN));}
   int emitted=0;
   for(int i=offset;i<offset+28;++i) {
     el->pts=pts(i);el->dts=i;el->data[6]=100+i;el->data[12]=100+pts(i);
     assert(join.Push(el,true));
     if(join.Take(out)==0) {
       const int original=offset+emitted++;
       assert(out->pts==pts(original) && out->dts==original);
       assert(out->data[14]==100+original && out->data[out->size-1]==100+pts(original));
       av_packet_unref(out);
     }
   }
   assert(emitted==std::min(28,32-offset));
   p->pts=pts(32);p->dts=32;assert(join.Push(p,false));
   if(offset==6) {
     assert(join.Take(out)==0 && out->dts==32 && out->pts==pts(32));
     assert(out->data[14]==132 && out->data[out->size-1]==100+pts(32));av_packet_unref(out);
     p->pts=pts(33);p->dts=33;assert(join.Push(p,false));
     assert(join.Take(out)==0 && out->dts==33 && out->pts==pts(33));
     assert(out->data[14]==133 && out->data[out->size-1]==100+pts(33));av_packet_unref(out);
   }
   // EL can fill first: a full EL window must allow the same proven BL retirement.
   for(int baseCount : {20,29,31}) {
     join.Reset(true);
     for(int i=0;i<baseCount;++i){p->pts=pts(i);p->dts=i;assert(join.Push(p,false));}
     int recovered=0;
     for(int i=offset;i<offset+32;++i) {
       el->pts=pts(i);el->dts=i;el->data[6]=100+i;el->data[12]=100+pts(i);
       assert(join.Push(el,true));
       while(join.Take(out)==0) {
         const int original=offset+recovered++;
         assert(out->pts==pts(original) && out->dts==original);
         assert(out->data[14]==100+original && out->data[out->size-1]==100+pts(original));
         av_packet_unref(out);
       }
     }
     assert(recovered==baseCount-offset);
   }
   // A common PTS with different DTS is not an anchor for dependent pictures.
   join.Reset(true);
   assert(av_packet_make_writable(p)==0);p->data[3]=0x02;
   for(int i=0;i<32;++i) {p->pts=pts(i);p->dts=i;assert(join.Push(p,false));}
   el->pts=3;el->dts=1;assert(join.Push(el,true));
   p->pts=pts(32);p->dts=32;assert(!join.Push(p,false));
   assert(av_packet_make_writable(p)==0);p->data[3]=0x26;
   // Matching DTS without matching PTS is not a decode anchor either.
   join.Reset(true);
   for(int i=0;i<32;++i) {p->pts=pts(i);p->dts=i;assert(join.Push(p,false));}
   el->pts=1;el->dts=0;assert(join.Push(el,true));
   p->pts=pts(32);p->dts=32;assert(!join.Push(p,false));
   // Unknown prefix clocks cannot prove retirement, even with a later anchor.
   join.Reset(true);
   for(int i=0;i<32;++i) {p->pts=pts(i);p->dts=i?i:AV_NOPTS_VALUE;assert(join.Push(p,false));}
   el->pts=el->dts=1;assert(join.Push(el,true));
   p->pts=pts(32);p->dts=32;assert(!join.Push(p,false));
   // Equal prefix DTS is not evidence that the prefix precedes the anchor.
   join.Reset(true);
   for(int i=0;i<32;++i) {p->pts=pts(i);p->dts=i?i:1;assert(join.Push(p,false));}
   el->pts=el->dts=1;assert(join.Push(el,true));
   p->pts=pts(32);p->dts=32;assert(!join.Push(p,false));
   // The new proof cannot enable retirement in ordinary steady playback.
   join.Reset();
   for(int i=0;i<32;++i) {p->pts=pts(i);p->dts=i;assert(join.Push(p,false));}
   el->pts=el->dts=1;assert(join.Push(el,true));
   p->pts=pts(32);p->dts=32;assert(!join.Push(p,false));
   // Retirement still requires a full BL window and an available skip budget.
   for(int skipped : {0,32}) {
     join.Reset(true);p->pts=p->dts=AV_NOPTS_VALUE;
     for(int i=0;i<skipped;++i)assert(join.Push(p,false));
     for(int i=0;i<31;++i){p->pts=pts(i);p->dts=i;assert(join.Push(p,false));}
     el->pts=pts(6);el->dts=6;assert(join.Push(el,true));
     assert(join.Take(out)==AVERROR(EAGAIN));
     p->pts=pts(31);p->dts=31;assert(join.Push(p,false));
     const int taken=join.Take(out);
     if(skipped){assert(taken==AVERROR(EAGAIN));p->pts=pts(32);p->dts=32;assert(!join.Push(p,false));}
     else {assert(taken==0 && out->pts==pts(6));av_packet_unref(out);}
   }
   av_packet_free(&out);av_packet_free(&el);av_packet_free(&p);
 }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'), '-I'+str(prefix/'include'), str(root/'test.cpp'),
                '-L'+str(prefix/'lib'), '-lavcodec', '-lavutil', '-lm', '-o', str(root/'test')],
                text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root/'test')], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)

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
 CBlurayDovi join;
 assert(!join.Push(nullptr,false));
 assert(reason(join)=="packet");
 AVPacket* p=av_packet_alloc(); assert(p && av_new_packet(p,6)==0);
 const unsigned char nal[]={0,0,1,0x26,1,0xaa};
 std::memcpy(p->data,nal,6); p->pts=0;
 assert(!join.Push(p,true)); assert(reason(join)=="missing-layer-or-rpu");
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
 for(int i=2;i<=32;++i){el->pts=i;assert(join.Push(el,true));}
 p->pts=33;assert(join.Push(p,false));
 AVPacket* out=av_packet_alloc();assert(join.Take(out)==0 && out->pts==2);
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
 for(int i=2;i<=32;++i){el->pts=i;assert(join.Push(el,true));}
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
