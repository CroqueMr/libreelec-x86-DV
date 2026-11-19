"""A live HDR policy switch must not shrink and reopen a sufficient decoder pool."""
import unittest
from test_ai_reentry import execute
from test_native_video_source import TREE, body


class AIPoolLifetimeTests(unittest.TestCase):
    def test_reopen_only_when_requested_pool_exceeds_the_allocated_pool(self):
        check=body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/VAAPI.cpp').read_text(),
                   'CDVDVideoCodec::VCReturn CDecoder::Check(')
        gate=check[check.index('  if (state == VAAPI_OPEN &&'):check.index('#endif')]
        execute(r'''
#include <cassert>
#include <mutex>
enum{VAAPI_OPEN,VAAPI_LOST,VAAPI_ERROR};
bool outputActive=true;unsigned flushes=0;int resetState=VAAPI_OPEN,m_DisplayState=VAAPI_OPEN;
std::mutex m_DecoderSection;
void Reset(){++flushes;m_DisplayState=resetState;if(resetState==VAAPI_OPEN)outputActive=false;}
struct ICallbackHWAccel{
 unsigned requested=6,reopens=0;
 unsigned GetHDR10AIBufferCount(){return requested;}
 void PrepareHDR10AIReopen(){assert(!outputActive);++reopens;}
};
struct AVCodecContext{void* opaque;};
struct CDVDVideoCodec{enum VCReturn{VC_NONE,VC_REOPEN,VC_FATAL};};
auto Check(AVCodecContext* avctx,unsigned m_hdr10AIBuffers,int state=VAAPI_OPEN){
 GATE
 return state==VAAPI_ERROR ? CDVDVideoCodec::VC_FATAL : CDVDVideoCodec::VC_NONE;
}
int main(){
 ICallbackHWAccel callback;AVCodecContext context{&callback};
 assert(Check(&context,36)==CDVDVideoCodec::VC_NONE && !callback.reopens);
 callback.requested=36;assert(Check(&context,36)==CDVDVideoCodec::VC_NONE && !callback.reopens);
 assert(Check(&context,6)==CDVDVideoCodec::VC_REOPEN && callback.reopens==1);
 outputActive=true;callback.requested=64;assert(Check(&context,36)==CDVDVideoCodec::VC_REOPEN && callback.reopens==2);
 assert(Check(&context,36,VAAPI_LOST)==CDVDVideoCodec::VC_NONE && callback.reopens==2);
 assert(flushes==2);
 for(int failure : {1,2}){ // Negative ACK and timeout share Reset's error contract.
  (void)failure;outputActive=true;resetState=VAAPI_ERROR;
  assert(Check(&context,36)==CDVDVideoCodec::VC_FATAL && callback.reopens==2);
  assert(outputActive); // No unsafe reopen may destroy this still-busy context.
 }
 assert(flushes==4);
}
'''.replace('GATE',gate))
