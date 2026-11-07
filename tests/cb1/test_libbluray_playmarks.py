"""Keep later marks sharing a seek access packet without replaying earlier marks."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_native_video_source import body


class LibblurayPlaymarks(unittest.TestCase):
    def test_mark_seek_preserves_successors_on_both_event_channels(self):
        include = os.environ.get('LIBBLURAY_TEST_INCLUDE')
        if not include:
            self.skipTest('Matched libbluray sources required')
        root = Path(__file__).resolve().parents[2]
        owner = root / 'packages/multimedia/libbluray/patches/0002-navigation-read-boundary.patch'
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            native = folder / 'src/libbluray/bluray.c'
            for name in ('bluray.c','bluray.h','decoders/m2ts_filter.c','decoders/m2ts_filter.h'):
                target=folder/'src/libbluray'/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(Path(include)/'libbluray'/name,target)
            applied = subprocess.run(['patch', '-p1', '--fuzz=0', '-i', str(owner)],
                                     cwd=folder, capture_output=True, text=True)
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            source = native.read_text()
            program = r'''
#include <assert.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <libbluray/bluray.h>
#define BD_DEBUG(...) ((void)0)
enum {BDJ_EVENT_MARK=1, BDJ_EVENT_SEEK=2, GC_CTRL_PG_RESET=3};
typedef struct {uint32_t title_pkt;} NAV_MARK;
typedef struct {uint32_t in_time, title_time;} NAV_CLIP;
typedef struct {unsigned count; NAV_MARK mark[64];} MARKS;
typedef struct {MARKS mark_list; NAV_CLIP clip;} TITLE;
typedef struct {const NAV_CLIP* clip;} BD_STREAM;
struct bluray {
 TITLE* title; BD_STREAM st0; uint64_t s_pos, next_mark_pos;
 int next_mark, mutex, fail, chapters, seeks, java_seeks;
 unsigned events[128], java[128], count, java_count;
 void* graphics_controller;
};
static void _update_chapter_psr(BLURAY* b) {++b->chapters;}
static void _queue_event(BLURAY* b, uint32_t type, uint32_t value) {
 if(type==BD_EVENT_PLAYMARK) {assert(b->count<128);b->events[b->count++]=value;}
 else {assert(type==BD_EVENT_SEEK);++b->seeks;}
}
static void _bdj_event(BLURAY* b, int type, uint32_t value) {
 if(type==BDJ_EVENT_MARK) {assert(b->java_count<128);b->java[b->java_count++]=value;}
 else {assert(type==BDJ_EVENT_SEEK);++b->java_seeks;}
}
static void bd_mutex_lock(int* m) {assert(!*m);++*m;}
static void bd_mutex_unlock(int* m) {assert(*m==1);--*m;}
static void _change_angle(BLURAY* b) {(void)b;}
static const NAV_CLIP* nav_mark_search(TITLE* t, unsigned m, uint32_t* c, uint32_t* p) {
 *c=*p=t->mark_list.mark[m].title_pkt;return &t->clip;
}
static int64_t _seek_stream(BLURAY* b, BD_STREAM* s, const NAV_CLIP* c, uint32_t p) {
 (void)p;if(b->fail)return -1;s->clip=c;return 0;
}
static uint32_t _update_time_psr_from_stream(BLURAY* b) {return b->st0.clip->in_time;}
static int gc_run(void* c, int a, int b, void* d) {return 0;}
static void _init_textst_timer(BLURAY* b) {}
static void _find_next_playmark(BLURAY* bd) @FIND@
static void _playmark_reached(BLURAY* bd) @REACHED@
static int64_t _seek_internal(BLURAY* bd, const NAV_CLIP* clip,
                             uint32_t title_pkt, uint32_t clip_pkt) @SEEK@
int64_t bd_seek_mark(BLURAY* bd, unsigned mark) @MARK@

static BLURAY init(TITLE* title) {
 BLURAY b={0};b.title=title;b.next_mark=-1;b.next_mark_pos=UINT64_MAX;return b;
}
static void check(TITLE* title, unsigned wanted) {
 BLURAY b=init(title);
 uint64_t start=(uint64_t)title->mark_list.mark[wanted].title_pkt*192;
 assert(bd_seek_mark(&b,wanted)==(int64_t)start && !b.mutex);
 assert(b.seeks==1 && b.java_seeks==1 && !b.count && !b.java_count);
 _playmark_reached(&b);assert(!b.count && !b.java_count);
 b.s_pos+=192;_playmark_reached(&b);
 unsigned expected=0;
 for(unsigned i=wanted+1;i<title->mark_list.count;++i)
  if((uint64_t)title->mark_list.mark[i].title_pkt*192<b.s_pos)++expected;
 assert(b.count==expected && b.java_count==expected);
 expected=0;
 for(unsigned i=wanted+1;i<title->mark_list.count;++i) {
  if((uint64_t)title->mark_list.mark[i].title_pkt*192<b.s_pos) {
   assert(b.events[expected]==i && b.java[expected]==i);++expected;
  }
 }
 assert(b.count==expected && b.java_count==expected);
 _playmark_reached(&b);assert(b.count==expected && b.java_count==expected);
 b.s_pos=((uint64_t)title->mark_list.mark[title->mark_list.count-1].title_pkt+1)*192;
 _playmark_reached(&b);
 assert(b.count==title->mark_list.count-wanted-1 && b.java_count==b.count);
 for(unsigned i=0;i<b.count;++i)assert(b.events[i]==wanted+i+1 && b.java[i]==b.events[i]);
 _playmark_reached(&b);assert(b.count==title->mark_list.count-wanted-1);
}
int main(void) {
 TITLE avatar={.mark_list={4,{{4},{4},{1509892},{1509892}}}};
 /* At the second access packet, mark 2 consumes itself; mark 3 must survive.
  * Seeking mark 3 must not replay mark 2 from that same access packet. */
 unsigned order[]={2,3,0,1};
 for(unsigned i=0;i<4;++i)check(&avatar,order[i]);
 BLURAY failed=init(&avatar);failed.s_pos=1920;_find_next_playmark(&failed);
 int next=failed.next_mark;uint64_t pos=failed.next_mark_pos;failed.fail=1;
 bd_seek_mark(&failed,2);
 assert(failed.s_pos==1920 && failed.next_mark==next && failed.next_mark_pos==pos);
 assert(!failed.seeks && !failed.java_seeks && !failed.count && !failed.java_count);
 bd_seek_mark(&failed,4);assert(failed.next_mark==next && !failed.count);
 /* Ordinary byte/time/playitem seeks retain their existing boundary policy. */
 BLURAY ordinary=init(&avatar);_seek_internal(&ordinary,&avatar.clip,1509892,1509892);
 ordinary.s_pos+=192;_playmark_reached(&ordinary);assert(!ordinary.count && !ordinary.java_count);
 /* Vary duplicate groups and packet positions, including offsets beyond 4GB. */
 uint32_t seed=1297;
 for(unsigned trial=0;trial<100;++trial) {
  TITLE t={0};t.mark_list.count=2+trial%31;
  uint32_t packet=trial==99 ? UINT32_MAX-128 : trial*1000;
  for(unsigned i=0;i<t.mark_list.count;++i) {
   seed=seed*1664525u+1013904223u;packet+=(seed>>16)%4;
   t.mark_list.mark[i].title_pkt=packet;
  }
  for(unsigned i=0;i<t.mark_list.count;++i)check(&t,i);
 }
 puts("PASS: same-packet mark successors, no replay, read boundary, failed seek, both channels");
}
'''
            for token, signature in [('FIND', 'static void _find_next_playmark('),
                                     ('REACHED', 'static void _playmark_reached('),
                                     ('SEEK', 'static int64_t _seek_internal('),
                                     ('MARK', 'int64_t bd_seek_mark(')]:
                program = program.replace('@' + token + '@', body(source, signature))
            (folder / 'check.c').write_text(program)
            built = subprocess.run(['cc', '-std=c11', '-fsanitize=address,undefined',
                                    '-I' + include, str(folder / 'check.c'), '-o', str(folder / 'check')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(folder / 'check')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == '__main__':
    unittest.main()
