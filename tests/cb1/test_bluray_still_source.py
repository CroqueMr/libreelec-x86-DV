"""A disc-authored still must release decoded frames before navigation retries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class BlurayStillSource(unittest.TestCase):
    def test_authoritative_still_drains_once_after_packets_not_on_normal_retry(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text()
        retry = body(source, 'if(next == CDVDInputStream::NEXTSTREAM_RETRY)')
        next_call = next(line for line in source.splitlines()
                         if 'CDVDInputStream::ENextStream next = ' in line)
        self.assertLess(source.index(next_call), source.index(retry))
        packet = source.split('    // process the packet\n', 1)[1].split('\n  }\n}', 1)[0]
        program = r'''
#include <cassert>
#include <chrono>
#include <memory>
using namespace std::chrono_literals;
constexpr int DVDSTATE_NORMAL=0, DVDSTATE_STILL=1, DVDSTREAM_TYPE_BLURAY=2;
struct CDVDMsg { enum { VIDEO_DRAIN=1 }; int type; explicit CDVDMsg(int t):type(t){} };
struct CDVDInputStream {
 enum ENextStream { NEXTSTREAM_RETRY };
 bool bluray=true; int* state=nullptr; int nextState=-1;
 ENextStream NextStream() { if(nextState>=0) *state=nextState; return NEXTSTREAM_RETRY; }
 bool IsStreamType(int type) const { assert(type==DVDSTREAM_TYPE_BLURAY); return bluray; }
};
struct CThread { static void Sleep(std::chrono::milliseconds) {} };
struct Stream {}; struct Packet {};
struct Video {
 int drains=0;
 void SendMessage(std::shared_ptr<CDVDMsg> msg) { assert(msg->type==CDVDMsg::VIDEO_DRAIN); ++drains; }
};
struct Player {
 bool stillDrainPending=false, selected=true;
 struct { bool inited=true; } m_CurrentVideo;
 struct {
  int state=DVDSTATE_STILL;
 } m_dvd;
 Video video; Video* m_VideoPlayerVideo=&video;
 std::shared_ptr<CDVDInputStream> m_pInputStream=std::make_shared<CDVDInputStream>();
 bool CheckIsCurrent(decltype(m_CurrentVideo)&, Stream*, Packet*) { return selected; }
 void ProcessPacket(Stream*, Packet*) {}
 void Receive() {
  Stream stream; Packet packet; auto* pStream=&stream; auto* pPacket=&packet;
  @PACKET@
 }
 void Retry(int nextState=-1) {
  m_pInputStream->state=&m_dvd.state; m_pInputStream->nextState=nextState;
  for (int pass=0;pass<1;++pass) {
   @NEXT@
   if(next == CDVDInputStream::NEXTSTREAM_RETRY) @RETRY@
  }
 }
};
int main() {
 Player p;
 p.Retry(); assert(p.video.drains==0);
 p.Receive(); assert(p.video.drains==0);
 p.Retry(); assert(p.video.drains==1);
 p.Retry(); assert(p.video.drains==1);
 p.selected=false; p.Receive(); p.Retry(); assert(p.video.drains==1);
 p.selected=true; p.Receive(); p.Retry(); assert(p.video.drains==2);
 Player normal; normal.m_dvd.state=DVDSTATE_NORMAL;
 normal.Receive(); normal.Retry(); normal.Retry(); assert(normal.video.drains==0);
 normal.m_dvd.state=DVDSTATE_STILL; normal.Retry(); assert(normal.video.drains==1);
 Player empty; empty.m_CurrentVideo.inited=false;
 empty.Receive(); empty.Retry(); assert(empty.video.drains==0);
 empty.m_CurrentVideo.inited=true; empty.Retry(); assert(empty.video.drains==1);
 Player dvd; dvd.m_pInputStream->bluray=false;
 dvd.Receive(); dvd.Retry(); assert(dvd.video.drains==0);
 Player changed; changed.Receive();
 changed.Retry(DVDSTATE_NORMAL); assert(changed.video.drains==0);
 changed.Retry(DVDSTATE_STILL); assert(changed.video.drains==1);
}
'''.replace('@RETRY@', retry).replace('@PACKET@', packet).replace('@NEXT@', next_call)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    '-fno-omit-frame-pointer', str(root / 'check.cpp'),
                                    '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
