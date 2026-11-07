"""Exercise native libbluray byte/event ownership across clip and angle changes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_native_video_source import body


class LibblurayReadBoundary(unittest.TestCase):
    def test_navigation_suspends_before_new_clip_bytes_and_preserves_plain_reads(self):
        include=os.environ.get('LIBBLURAY_TEST_INCLUDE')
        if not include:self.skipTest('Matched libbluray sources required')
        original=Path(include)/'libbluray/bluray.c'
        root=Path(__file__).resolve().parents[2]
        patch=root/'packages/multimedia/libbluray/patches/0002-navigation-read-boundary.patch'
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);native=folder/'src/libbluray/bluray.c'
            for name in ('bluray.c','bluray.h','decoders/m2ts_filter.c','decoders/m2ts_filter.h'):
                target=folder/'src/libbluray'/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(Path(include)/'libbluray'/name,target)
            if patch.exists():
                result=subprocess.run(['patch','-p1','--fuzz=0','-i',str(patch)],cwd=folder,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            source=native.read_text()
            navigation='nav_boundary' in source.split('static int _bd_read(',1)[1].split('{',1)[0]
            program=r'''
#include <assert.h>
#include <inttypes.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <libbluray/bluray.h>
#define BD_DEBUG(...) ((void)0)
#define BD_UNLIKELY(v) (v)
#define SPN(v) ((v)/192)
#define TS_PID(v) 999
enum {CONNECT_NON_SEAMLESS=5,HDMV_PID_PCR=4097,
 title_undef,title_hdmv,title_bdj,GC_STATUS_ANIMATE=1,GC_CTRL_INIT_MENU,
 GC_CTRL_PG_UPDATE,GC_CTRL_NOP,BDJ_EVENT_END_OF_PLAYLIST,PSR_PLAYLIST};
typedef struct clip {uint32_t end_pkt,title_pkt,in_time;int still_mode,still_time,connection,ref;} NAV_CLIP;
typedef struct {NAV_CLIP* clip;void* fp;uint64_t clip_pos;unsigned int_buf_off;
 int ig_pid,pg_pid,seek_flag;} BD_STREAM;
struct bluray {
 BD_STREAM st0,st_textst;uint64_t s_pos;unsigned char int_buf[6144];
 int seamless_angle_change;uint32_t angle_change_pkt;uint64_t angle_change_time;
 void* title;void* graphics_controller;void* hdmv_vm;void* regs;void* event_queue;
 int title_type,hdmv_suspended,gc_status,end_of_playlist,bdj_wait_start;
 int next_mark;uint64_t next_mark_pos;int mutex;
 NAV_CLIP clips[2];BD_EVENT events[16];int event_count,reads,opens,angles,angle;
};
static void _queue_event(BLURAY* b,uint32_t type,uint32_t value){
 if(!b->event_queue)return;
 assert(b->event_count<16);b->events[b->event_count++]=(BD_EVENT){type,value};
}
static int _get_event(BLURAY* b,BD_EVENT* event){
 *event=(BD_EVENT){0};if(!b->event_queue||!b->event_count)return 0;
 *event=b->events[0];--b->event_count;
 memmove(b->events,b->events+1,b->event_count*sizeof(*b->events));return 1;
}
static NAV_CLIP* nav_next_clip(void* title,NAV_CLIP* current){
 BLURAY* b=title;return current==b->clips?b->clips+1:NULL;
}
static int _open_m2ts(BLURAY* b,BD_STREAM* stream){
 ++b->opens;stream->clip_pos=0;stream->int_buf_off=6144;
 _queue_event(b,BD_EVENT_PLAYITEM,stream->clip->ref);return 1;
}
static unsigned char sample(int clip,int angle,int byte){return clip*53+angle*31+byte*17;}
static int _read_block(BLURAY* b,BD_STREAM* stream,unsigned char* out){
 ++b->reads;int start=(stream->clip_pos/6144)*6144;
 for(int i=0;i<6144;++i)out[i]=sample(stream->clip->ref,b->angle,start+i);return 1;
}
static void _change_angle(BLURAY* b){++b->angles;++b->angle;_queue_event(b,BD_EVENT_ANGLE,1);}
static void _clip_seek_time(BLURAY* b,uint64_t time){(void)time;b->st0.int_buf_off=6144;}
static int gc_decode_ts(void*a,int b,unsigned char*c,int d,int e){return 0;}
static int _run_gc(BLURAY*a,int b,int c){return 0;}
static int gc_run(void*a,int b,int c,void*d){return 0;}
static void _update_textst_timer(BLURAY*b){}
static void _playmark_reached(BLURAY*b){}
static void bd_mutex_lock(int* m){}static void bd_mutex_unlock(int* m){}
static int _run_hdmv(BLURAY*b){b->hdmv_suspended=1;return 0;}
static void hdmv_vm_resume(void* p){}static int hdmv_vm_running(void* p){return 0;}
static void _bdj_event(BLURAY*b,int e,int p){}
static uint32_t bd_psr_read(void*r,int p){return 0;}
static int _bd_read(BLURAY *bd,unsigned char *buf,int len@@NAV@@) READ
static int _bd_read_locked(BLURAY *bd,unsigned char *buf,int len@@NAV@@) LOCKED
int bd_read(BLURAY *bd,unsigned char *buf,int len) PLAIN
static int _read_ext(BLURAY *bd,unsigned char *buf,int len,BD_EVENT *event) EXTENDED
static void init(BLURAY* b,int connection,int angle_case,int type){
 memset(b,0,sizeof(*b));b->title=b;b->event_queue=b;b->title_type=type;b->hdmv_suspended=1;b->next_mark=-1;
 b->clips[0]=(NAV_CLIP){32,0,0,0,0,0,0};b->clips[1]=(NAV_CLIP){64,32,0,0,0,connection,1};
 b->st0.clip=b->clips;b->st0.fp=b;b->st0.int_buf_off=6144;
 if(angle_case){b->seamless_angle_change=1;b->angle_change_pkt=angle_case==1?16:32;}
}
static void check(int fragment,int connection,int angle_case,int type){
 unsigned char outputs[2][18432];
 for(int nav=0;nav<2;++nav){
  BLURAY b;init(&b,connection,angle_case,type);unsigned used=0;int boundary=0;
  for(int steps=0;steps<30000&&used<sizeof(outputs[nav]);++steps){
   unsigned char bytes[16384];BD_EVENT event={0};int reads=b.reads;
   int n=nav?_read_ext(&b,bytes,fragment,&event):bd_read(&b,bytes,fragment);
   assert(n>=0&&used+n<=sizeof(outputs[nav]));
   if(nav&&(event.event==BD_EVENT_PLAYITEM||event.event==BD_EVENT_ANGLE)){
    assert(n==0&&"Navigation must announce the boundary before consuming its new bytes");
    assert(b.reads==reads);++boundary;
   }
   memcpy(outputs[nav]+used,bytes,n);used+=n;
  }
  assert(used==sizeof(outputs[nav])&&b.s_pos==sizeof(outputs[nav]));
  assert(!b.seamless_angle_change);
  if(nav)assert(boundary>=1);
 }
 assert(!memcmp(outputs[0],outputs[1],sizeof(outputs[0])));
 for(int i=0;i<18432;++i){
  int clip=i<6144?0:1,angle=angle_case==1&&i>=3072?1:0;
  assert(outputs[1][i]==sample(clip,angle,clip?i-6144:i));
 }
}
int main(){
 int fragments[]={1,191,192,511,4096,8192};
 for(unsigned i=0;i<sizeof(fragments)/sizeof(*fragments);++i)
 for(int connection=0;connection<2;++connection)
 for(int angle_case=0;angle_case<3;++angle_case)
 for(int type=title_hdmv;type<=title_bdj;++type)
  check(fragments[i],connection?CONNECT_NON_SEAMLESS:0,angle_case,type);
 /* bd_select_playlist callers may use bd_read_ext without enabling events.
  * No observable boundary exists there: zero must not masquerade as EOF. */
 {
  BLURAY b;init(&b,CONNECT_NON_SEAMLESS,0,title_undef);b.event_queue=NULL;
  unsigned used=0;unsigned char bytes[4096];BD_EVENT event={0};
  while(used<18432){
   int n=_read_ext(&b,bytes,sizeof(bytes),&event);
   assert(n>0&&"No event queue must not introduce an apparent EOF between clips");
   assert(event.event==BD_EVENT_NONE&&used+n<=18432);
   for(int i=0;i<n;++i){int pos=used+i;assert(bytes[i]==sample(pos<6144?0:1,0,pos<6144?pos:pos-6144));}
   used+=n;
  }
  assert(b.s_pos==18432);
 }
 for(int still=1;still<=2;++still){
  BLURAY b;init(&b,0,0,title_bdj);b.clips[0].still_mode=still;b.clips[0].still_time=3;
  b.st0.clip_pos=6144;b.s_pos=6144;unsigned char bytes[4096];BD_EVENT event={0};
  assert(_read_ext(&b,bytes,sizeof(bytes),&event)==0&&event.event==BD_EVENT_STILL_TIME&&!b.reads);
 }
 puts("PASS: exact byte stream, clip/angle event ownership, fragmented reads, HDMV and BD-J");
}
'''
            program=program.replace('@@NAV@@',', int nav_boundary' if navigation else '')
            for token,signature in [('READ','static int _bd_read('),('LOCKED','static int _bd_read_locked('),
                                    ('PLAIN','int bd_read('),('EXTENDED','static int _read_ext(')]:
                program=program.replace(' '+token,body(source,signature))
            (folder/'check.c').write_text(program)
            build=subprocess.run(['cc','-std=c11','-fsanitize=address,undefined','-I'+include,
                str(folder/'check.c'),'-o',str(folder/'check')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(folder/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
