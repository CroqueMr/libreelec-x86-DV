"""Exercise actual Blu-ray packet ownership and rejection diagnostics."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class BlurayPairingTests(unittest.TestCase):
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
   // A common PTS with a different DTS is not a decode anchor.
   join.Reset(true);
   for(int i=0;i<32;++i) {p->pts=pts(i);p->dts=i;assert(join.Push(p,false));}
   el->pts=3;el->dts=1;assert(join.Push(el,true));
   p->pts=pts(32);p->dts=32;assert(!join.Push(p,false));
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
