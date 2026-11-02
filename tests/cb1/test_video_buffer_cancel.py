"""A requested output cancellation is not a buffer timeout or a dropped picture."""
import unittest
from test_ai_reentry import execute
from test_native_video_source import TREE, body


class VideoBufferCancelTests(unittest.TestCase):
    def test_cancelled_buffer_wait_aborts_while_real_timeouts_stay_visible(self):
        output=body((TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text(),
                    'CVideoPlayerVideo::EOutputState CVideoPlayerVideo::OutputPicture(')
        wait=output[output.index('  int buffer = m_renderManager.WaitForBuffer('):output.index('  ProcessOverlays(')]
        execute(r'''
#include <cassert>
enum{OUTPUT_NORMAL,OUTPUT_ABORT,OUTPUT_DROPPED,OUTPUT_AGAIN,LOGWARNING};
constexpr int DVD_PLAYSPEED_NORMAL=1000,DVD_PLAYSPEED_PAUSE=0;
struct CLog{static inline int warnings=0;template<class... T>static void Log(T...){++warnings;}};
struct Player{
 bool m_bAbortOutput=false,cancel=true,available=false;int m_speed=1000,drops=0;
 struct Stats{int* drops;void AddOutputDropGain(double,int){++*drops;}}m_droppingStats{&drops};
 struct Manager{Player* player;int WaitForBuffer(bool& abort,int){abort=player->cancel;return player->available?0:-1;}}m_renderManager{this};
 int Output(){int maxWaitTime=500;struct{double pts=1;}picture;auto* pPicture=&picture;
 WAIT
 return OUTPUT_NORMAL;
 }
};
int main(){
 Player cancelled;assert(cancelled.Output()==OUTPUT_ABORT && CLog::warnings==0 && cancelled.drops==0);
 Player timeout;timeout.cancel=false;assert(timeout.Output()==OUTPUT_AGAIN && CLog::warnings==1);
 Player paused;paused.cancel=false;paused.m_speed=0;assert(paused.Output()==OUTPUT_AGAIN && CLog::warnings==1);
 Player trick;trick.cancel=false;trick.m_speed=2000;assert(trick.Output()==OUTPUT_DROPPED && trick.drops==1);
 Player ready;ready.cancel=false;ready.available=true;assert(ready.Output()==OUTPUT_NORMAL && CLog::warnings==1);
}
'''.replace('WAIT',wait))
