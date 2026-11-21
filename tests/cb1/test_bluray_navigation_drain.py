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
            'bool CDVDInputStreamBluray::HoldEvent(bool sequentialRead)',
            'bool CDVDInputStreamBluray::HasGivenUpReading() const',
            'bool CDVDInputStreamBluray::IsSequentialClipRead(uint64_t position) const',
            'bool CDVDInputStreamBluray::WaitingForReadablePlaylist() const',
        )
        definitions = '\n'.join(s + '\n' + body(source, s) for s in signatures)
        prologue=body(source,'void CDVDInputStreamBluray::ProcessEvent()').split('  int pid = -1;',1)[0][1:]
        header = (TREE/'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.h').read_text()
        program = r'''
#include <cassert>
#include <cstdint>
#include <deque>
#include <vector>
#include "BlurayClipClock.h"
#define BD_BDJ_WAITING_FOR_PLAYLIST
enum { BD_EVENT_NONE,BD_EVENT_SEEK,BD_EVENT_TITLE,BD_EVENT_ANGLE,BD_EVENT_PLAYLIST,
       BD_EVENT_PLAYITEM,BD_EVENT_STILL_TIME,BD_EVENT_DISCONTINUITY,BD_EVENT_MENU,
       BD_EVENT_AUDIO_STREAM,BD_EVENT_PG_TEXTST,BD_EVENT_ERROR,BD_EVENT_ENCRYPTED,
       BD_EVENT_IDLE,BD_EVENT_HDMV_PROGRAM_END };
enum {HOLD_NONE,HOLD_DATA,HOLD_HELD,HOLD_ERROR,HOLD_STILL,LOGDEBUG};
constexpr unsigned MAX_CONSECUTIVE_READ_ERRORS = 1000;
using bd_vk_key_e=int;
struct BD_EVENT {int event{},param{};};
struct Fake {
 std::deque<BD_EVENT> queue, pollEvents;
 int calls{},clip{},seekResult{};
 uint64_t position{};
 bool waitingForPlaylist{};
};
struct CLog {template<class... T> static void Log(T...) {}};
static int bd_get_event(Fake* f,BD_EVENT* e) {
 if(f->queue.empty()){*e={};return 0;}*e=f->queue.front();f->queue.pop_front();return 1;
}
static uint64_t bd_tell_time(Fake*) {return 0;}
static uint64_t bd_tell(Fake* f) {return f->position;}
static bool bd_bdj_waiting_for_playlist(Fake* f) {return f->waitingForPlaylist;}
static int bd_read_ext(Fake* f,uint8_t* bytes,int size,BD_EVENT* e) {
 ++f->calls;
 if(bd_get_event(f,e))return 0;
 if(!size) {
  assert(!bytes);
  if(!f->pollEvents.empty()){*e=f->pollEvents.front();f->pollEvents.pop_front();}
  return 0;
 }
 *bytes=f->clip;
 ++f->position;
 return 1;
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
 BD_EVENT m_event{};int m_dispTimeBeforeRead{};
 struct {unsigned clip_count{8};struct {unsigned pkt_count{1};} clips[8];} title;
 decltype(title)* m_titleInfo{&title};
 std::vector<int> processed;
 bool m_aborted{};
 unsigned m_readErrors{},m_playlist{};
 uint64_t m_lastReadEnd{};
 bool m_hdmvEndPending{},m_hdmvEndReleased{},m_hdmvProgramEnded{};
 bool compatibleNextClip{};
 void ProcessEvent() {
  PROLOGUE
  if(!m_event.event)return;processed.push_back(m_event.event*10+m_event.param);
  if(m_event.event==BD_EVENT_PLAYITEM)fake.clip=m_event.param;
  if(m_event.event==BD_EVENT_PLAYLIST)m_hdmvEndPending=m_hdmvEndReleased=m_hdmvProgramEnded=false;
  if(m_event.event==BD_EVENT_HDMV_PROGRAM_END){m_hdmvEndReleased=false;m_hdmvProgramEnded=true;}
  if(m_event.event==BD_EVENT_DISCONTINUITY)m_hold=HOLD_NONE;
  if(m_event.event==BD_EVENT_STILL_TIME)m_hold=HOLD_STILL;
  if(m_event.event==BD_EVENT_ERROR||m_event.event==BD_EVENT_ENCRYPTED)m_hold=HOLD_ERROR;
  m_event={};
 }
 int Read(uint8_t*,int);bool PosTime(int);bool SeekChapter(int);ENextStream NextStream();
 void UserInput(bd_vk_key_e);void SkipStill();bool HoldEvent(bool sequentialRead=false);
 bool HasGivenUpReading() const;
 bool IsSequentialClipRead(uint64_t) const;
 bool WaitingForReadablePlaylist() const;
 bool WaitingForHdmvProgram() const WAITING_HDMV
 bool CanContinuePlayItem(uint32_t next) const { return compatibleNextClip && next==1; }
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
 for(bool aborted:{false,true}) {
  CDVDInputStreamBluray stopped;
  stopped.m_aborted=aborted;
  stopped.m_hold=aborted?HOLD_HELD:HOLD_ERROR;
  const int terminal=stopped.m_hold;
  stopped.UserInput(8);assert(stopped.m_hold==terminal&&stopped.fake.queue.empty());
  assert(!stopped.PosTime(50)&&!stopped.SeekChapter(2)&&stopped.m_hold==terminal);
  assert(stopped.Read(&byte,1)==-1&&stopped.fake.calls==0);
  assert(stopped.NextStream()==CDVDInputStream::NEXTSTREAM_NONE);
 }
 CDVDInputStreamBluray unreadable;
 unreadable.m_readErrors=MAX_CONSECUTIVE_READ_ERRORS;
 unreadable.m_hold=HOLD_HELD;
 assert(unreadable.Read(&byte,1)==-1&&unreadable.fake.calls==0);
 assert(unreadable.NextStream()==CDVDInputStream::NEXTSTREAM_NONE);
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
 // The same compatible clip can be reached by a read or by a menu command.
 for(bool menuJump:{false,true}) {
  CDVDInputStreamBluray compatible;
  compatible.compatibleNextClip=true;compatible.fake.position=191;
  assert(compatible.Read(&byte,1)==1&&compatible.m_lastReadEnd==192&&byte==0);
  if(menuJump) {
   compatible.UserInput(1);
   assert(compatible.Read(&byte,1)==0&&compatible.m_hold==HOLD_HELD);
   assert(compatible.NextStream()==CDVDInputStream::NEXTSTREAM_OPEN);
  } else {
   compatible.fake.queue.push_back({BD_EVENT_PLAYITEM,1});
  }
  assert(compatible.Read(&byte,1)==1&&compatible.m_hold==HOLD_NONE&&byte==1);
 }
 // The released VM is polled without consuming the next playlist's bytes.
 CDVDInputStreamBluray hdmv;
 hdmv.m_hdmvEndPending=true;
 assert(hdmv.Read(&byte,1)==0&&hdmv.fake.calls==0);
 assert(hdmv.NextStream()==CDVDInputStream::NEXTSTREAM_RETRY&&hdmv.fake.calls==0);
 hdmv.m_hdmvEndPending=false;hdmv.m_hdmvEndReleased=true;
 assert(hdmv.NextStream()==CDVDInputStream::NEXTSTREAM_RETRY&&hdmv.fake.position==0);
 hdmv.fake.pollEvents.push_back({BD_EVENT_PLAYLIST,1});
 assert(hdmv.NextStream()==CDVDInputStream::NEXTSTREAM_OPEN&&hdmv.fake.position==0);
 assert(hdmv.Read(&byte,1)==1&&hdmv.fake.position==1);
 hdmv.m_hdmvEndReleased=true;
 hdmv.fake.pollEvents.push_back({BD_EVENT_HDMV_PROGRAM_END,0});
 assert(hdmv.NextStream()==CDVDInputStream::NEXTSTREAM_NONE);
 // BD-J can signal idle while the next playlist is still being authored.
 CDVDInputStreamBluray bdj;
 bdj.fake.waitingForPlaylist=true;bdj.fake.queue.push_back({BD_EVENT_IDLE,0});
 assert(bdj.Read(&byte,1)==0&&bdj.fake.position==0);
 assert(bdj.NextStream()==CDVDInputStream::NEXTSTREAM_RETRY);
 bdj.fake.waitingForPlaylist=false;
 assert(bdj.NextStream()==CDVDInputStream::NEXTSTREAM_OPEN);
}
'''.replace('DEFINITIONS', definitions).replace('PROLOGUE',prologue).replace(
            'WAITING_HDMV', body(header, 'bool WaitingForHdmvProgram() const'))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary);(folder/'test.cpp').write_text(program)
            build = subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I', str(TREE/'xbmc/cores/VideoPlayer/DVDInputStreams'),
                str(folder/'test.cpp'),'-o',str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
