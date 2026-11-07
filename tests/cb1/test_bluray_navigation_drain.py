"""Native side actions must leave events for the old-reader EOF boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class BlurayNavigationDrain(unittest.TestCase):
    def test_pending_event_and_clip_bytes_survive_side_actions_in_order(self):
        source = (TREE/'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp').read_text()
        signatures = (
            'int CDVDInputStreamBluray::Read(uint8_t* buf, int buf_size)',
            'bool CDVDInputStreamBluray::PosTime(int ms)',
            'bool CDVDInputStreamBluray::SeekChapter(int ch)',
            'CDVDInputStream::ENextStream CDVDInputStreamBluray::NextStream()',
            'void CDVDInputStreamBluray::UserInput(bd_vk_key_e vk)',
            'void CDVDInputStreamBluray::SkipStill()',
        )
        user = next(line.strip() for line in source.splitlines() if line.startswith('void CDVDInputStreamBluray::UserInput('))
        signatures = signatures[:4] + (user,) + signatures[5:]
        definitions = '\n'.join(s + '\n' + body(source, s) for s in signatures)
        hold_signature = 'bool CDVDInputStreamBluray::HoldEvent()'
        definitions += '\n' + hold_signature + '\n' + (body(source, hold_signature) if hold_signature in source else '{return false;}')
        prologue=body(source,'void CDVDInputStreamBluray::ProcessEvent()').split('  int pid = -1;',1)[0][1:]
        program = r'''
#include <cassert>
#include <cstdint>
#include <deque>
#include <vector>
enum { BD_EVENT_NONE,BD_EVENT_SEEK,BD_EVENT_TITLE,BD_EVENT_ANGLE,BD_EVENT_PLAYLIST,
       BD_EVENT_PLAYITEM,BD_EVENT_STILL_TIME,BD_EVENT_DISCONTINUITY,BD_EVENT_MENU,
       BD_EVENT_AUDIO_STREAM,BD_EVENT_PG_TEXTST,BD_EVENT_ERROR,BD_EVENT_ENCRYPTED };
enum {HOLD_NONE,HOLD_DATA,HOLD_HELD,HOLD_ERROR,HOLD_EXIT,HOLD_STILL,LOGDEBUG};
using bd_vk_key_e=int;
struct BD_EVENT {int event{},param{};};
struct Fake {std::deque<BD_EVENT> queue;int calls{},clip{},seekResult{};};
struct CLog {template<class... T> static void Log(T...) {}};
static int bd_get_event(Fake* f,BD_EVENT* e) {
 if(f->queue.empty()){*e={};return 0;}*e=f->queue.front();f->queue.pop_front();return 1;
}
static uint64_t bd_tell_time(Fake*) {return 0;}
static int bd_read_ext(Fake* f,uint8_t* bytes,int,BD_EVENT* e) {
 ++f->calls;if(bd_get_event(f,e))return 0;*bytes=f->clip;return 1;
}
static int bd_read(Fake* f,uint8_t* bytes,int size){BD_EVENT e;return bd_read_ext(f,bytes,size,&e);}
static int bd_user_input(Fake* f,int,int key) {
 if(key==98){f->queue.push_back({BD_EVENT_MENU,0});f->queue.push_back({BD_EVENT_ENCRYPTED,0});f->queue.push_back({BD_EVENT_DISCONTINUITY,0});return 0;}
 if(key==99){for(int event:{BD_EVENT_MENU,BD_EVENT_AUDIO_STREAM,BD_EVENT_PG_TEXTST})f->queue.push_back({event,0});return 0;}
 if(key){f->queue.push_back({BD_EVENT_PLAYITEM,key});f->queue.push_back({BD_EVENT_DISCONTINUITY,0});}return 0;
}
static int64_t bd_seek_time(Fake* f,uint64_t) {
 if(f->seekResult<0)return -1;f->queue.push_back({BD_EVENT_SEEK,0});
 f->queue.push_back({BD_EVENT_PLAYITEM,4});f->queue.push_back({BD_EVENT_DISCONTINUITY,0});return 1;
}
static int64_t bd_seek_chapter(Fake* f,int) {return bd_seek_time(f,0);}
static void bd_read_skip_still(Fake* f) {
 f->queue.push_back({BD_EVENT_PLAYITEM,5});f->queue.push_back({BD_EVENT_DISCONTINUITY,0});
}
struct CDVDInputStream {enum ENextStream {NEXTSTREAM_NONE,NEXTSTREAM_RETRY,NEXTSTREAM_OPEN};};
struct CDVDInputStreamBluray : CDVDInputStream {
 Fake fake;Fake* m_bd{&fake};bool m_navmode{true};int m_hold{HOLD_NONE};
 BD_EVENT m_event{};int m_dispTimeBeforeRead{};void* m_titleInfo{this};
 std::vector<int> processed;
 void ProcessEvent() {
  PROLOGUE
  if(!m_event.event)return;processed.push_back(m_event.event*10+m_event.param);
  if(m_event.event==BD_EVENT_PLAYITEM)fake.clip=m_event.param;
  if(m_event.event==BD_EVENT_DISCONTINUITY)m_hold=HOLD_NONE;
  if(m_event.event==BD_EVENT_STILL_TIME)m_hold=HOLD_STILL;
  if(m_event.event==BD_EVENT_ERROR||m_event.event==BD_EVENT_ENCRYPTED)m_hold=HOLD_ERROR;
  m_event={};
 }
 int Read(uint8_t*,int);bool PosTime(int);bool SeekChapter(int);ENextStream NextStream();
 void UserInput(int);void SkipStill();bool HoldEvent();
};
DEFINITIONS
int main() {
 uint8_t byte=0;CDVDInputStreamBluray b;
 b.UserInput(99);assert(b.processed.size()==3&&b.fake.queue.empty());b.processed.clear();
 b.UserInput(1);
 assert(b.processed.empty() && "Side input must not consume the reader's navigation boundary");
 assert(b.Read(&byte,1)==0&&b.m_hold==HOLD_HELD&&b.m_event.event==BD_EVENT_PLAYITEM);
 const auto pending=b.m_event;const int calls=b.fake.calls;
 b.UserInput(2);assert(b.m_event.event==pending.event&&b.m_event.param==pending.param);
 assert(b.Read(&byte,1)==0&&b.fake.calls==calls);
 assert(b.NextStream()==CDVDInputStream::NEXTSTREAM_OPEN);
 assert((b.processed==std::vector<int>{BD_EVENT_PLAYITEM*10+1,BD_EVENT_DISCONTINUITY*10,
                                     BD_EVENT_PLAYITEM*10+2,BD_EVENT_DISCONTINUITY*10}));
 assert(b.Read(&byte,1)==1&&byte==2);
 // Seek may be requested while a prior boundary event is still held.
 for(bool chapter:{false,true}) {
  b.processed.clear();b.m_hold=HOLD_HELD;b.m_event={BD_EVENT_PLAYITEM,3};
  assert(chapter?b.SeekChapter(2):b.PosTime(1200));
  assert(b.m_hold==HOLD_HELD&&b.processed.empty()&&b.m_event.param==3);
  assert(b.Read(&byte,1)==0);
  assert(b.NextStream()==CDVDInputStream::NEXTSTREAM_OPEN);
  assert(b.processed.front()==BD_EVENT_PLAYITEM*10+3&&b.processed[1]==BD_EVENT_SEEK*10);
  assert(b.Read(&byte,1)==1&&byte==4);
 }
 b.fake.seekResult=-1;b.processed.clear();const int hold=b.m_hold;
 assert(!b.PosTime(900)&&!b.SeekChapter(3)&&b.m_hold==hold&&b.processed.empty());
 b.fake.seekResult=0;
 // A later discontinuity must not silently cancel the still skip's pending EOF.
 b.m_hold=HOLD_STILL;b.SkipStill();assert(b.m_hold==HOLD_HELD&&b.processed.empty());
 assert(b.Read(&byte,1)==0&&b.NextStream()==CDVDInputStream::NEXTSTREAM_OPEN);
 assert(b.Read(&byte,1)==1&&byte==5);
 // Start-up HOLD_DATA still processes a new item without manufacturing an EOF.
 b.processed.clear();b.m_hold=HOLD_DATA;b.UserInput(6);
 assert(b.Read(&byte,1)==1&&byte==6);
 // Plain title reads retain their historic synchronous seek event processing.
 b.m_navmode=false;b.processed.clear();assert(b.PosTime(1200));assert(!b.processed.empty());
 // Preserve data/still ordering even when the disc queues no discontinuity.
 CDVDInputStreamBluray moving;moving.m_hold=HOLD_HELD;moving.m_event={BD_EVENT_STILL_TIME,0};
 moving.fake.queue.push_back({BD_EVENT_PLAYITEM,4});moving.fake.queue.push_back({BD_EVENT_SEEK,0});
 assert(moving.NextStream()==CDVDInputStream::NEXTSTREAM_OPEN);
 assert(moving.Read(&byte,1)==1&&byte==4);
 CDVDInputStreamBluray still;still.m_hold=HOLD_HELD;still.m_event={BD_EVENT_PLAYITEM,4};
 still.fake.queue.push_back({BD_EVENT_STILL_TIME,0});
 assert(still.NextStream()==CDVDInputStream::NEXTSTREAM_RETRY&&still.m_hold==HOLD_STILL);
 // Abort/error remains terminal even if a remote key or seek arrives late.
 for(int terminal:{HOLD_EXIT,HOLD_ERROR}) {
  CDVDInputStreamBluray stopped;stopped.m_hold=terminal;
  stopped.UserInput(8);assert(stopped.m_hold==terminal&&stopped.fake.queue.empty());
  assert(!stopped.PosTime(50)&&!stopped.SeekChapter(2)&&stopped.m_hold==terminal);
  assert(stopped.NextStream()==CDVDInputStream::NEXTSTREAM_NONE);
 }
 // A fatal event encountered during a drain cannot be undone by a later event.
 for(int error:{BD_EVENT_ERROR,BD_EVENT_ENCRYPTED})for(bool later:{false,true}) {
  CDVDInputStreamBluray bad;bad.m_hold=HOLD_HELD;bad.m_event={BD_EVENT_PLAYITEM,4};
  bad.fake.queue.push_back({error,0});if(later)bad.fake.queue.push_back({BD_EVENT_DISCONTINUITY,0});
  assert(bad.NextStream()==CDVDInputStream::NEXTSTREAM_NONE&&bad.m_hold==HOLD_ERROR);
  assert(bad.Read(&byte,1)==-1);
 }
 CDVDInputStreamBluray badKey;badKey.UserInput(98);
 assert(badKey.m_hold==HOLD_ERROR&&badKey.fake.queue.size()==1);
 assert(badKey.NextStream()==CDVDInputStream::NEXTSTREAM_NONE);
}
'''.replace('DEFINITIONS', definitions).replace('PROLOGUE',prologue)
        program = program.replace('bd_vk_key_e vk', 'int vk')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary);(folder/'test.cpp').write_text(program)
            build = subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                str(folder/'test.cpp'),'-o',str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
