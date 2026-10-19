# SPDX-License-Identifier: MIT
"""Observe the actual carrier without changing GL pixels or leaking pack state."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class DebugCarrierTests(unittest.TestCase):
    def run_cpp(self, program, graphics=False):
        header = TREE/'xbmc/utils/DVBridgeDebug.h'
        self.assertTrue(header.is_file(), 'Automatic bounded carrier diagnostics are missing')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'test.cpp').write_text(program)
            command = ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                       '-fsanitize=address,undefined', '-I'+str(TREE/'xbmc'),
                       '-I'+str(prefix/'include'), str(root/'test.cpp'),
                       '-L'+str(prefix/'lib'), '-lavutil', '-lm', '-o', str(root/'test')]
            if graphics:
                command += ['-lEGL', '-lGLESv2']
            built = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            env = dict(os.environ, EGL_PLATFORM='surfaceless', ASAN_OPTIONS='detect_leaks=0')
            ran = subprocess.run([str(root/'test')], capture_output=True, text=True, env=env)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_sampling_is_bounded_across_pause_visibility_changes_and_seeks(self):
        # A per-frame/paused probe, a seek refilling the budget, or missing edges fails.
        self.run_cpp(r'''
#include "utils/DVBridgeDebug.h"
#include <cassert>
int main() {
 using namespace DVBRIDGE;
 DebugProbe schedule;
 assert(!schedule.Due(0,0,1,1,false));
 assert(schedule.Due(0,1,1,1,false)==1);
 assert(!schedule.Due(1,1,1,1,false));
 assert(!schedule.Due(499,1,2,1,false));
 assert(schedule.Due(500,1,2,1,false)==2);
 assert(!schedule.Due(501,1,2,1,false));
 assert(schedule.Due(1000,1,3,1,true)==3);
 assert(!schedule.Due(1001,1,3,1,true));
 assert(schedule.Due(1500,1,3,1,true)==4); // Settled sample while paused.
 assert(!schedule.Due(1501,1,3,1,true));
 assert(schedule.Due(2000,1,3,1,false)==5);
 assert(schedule.Due(2500,1,3,1,false)==6);
 assert(!schedule.Due(3000,1,3,1,false));
 assert(schedule.Due(12500,1,4,1,false)==7);
 unsigned admitted=7;
 for(unsigned n=1;n<2000;++n)
   admitted+=schedule.Due(12500+n*500,1,n+4,n+1,n%2)!=0;
 assert(admitted<=32); // New policy/seek revisions cannot refill a film's cap.
 assert(!schedule.Due(2000000,1,999,999,false));
 assert(schedule.Due(2000001,2,1,2,false)==1); // New film resets.
 assert(!schedule.Due(2000002,1,999,999,true)); // Late old stream is ignored.
}
''')

    def test_carrier_decodes_copies_crc_l5_and_detects_corruption(self):
        # Wrong row orientation, parity, copy selection or CRC must be observable.
        self.run_cpp(FIXTURE + r'''
int main() {
 using namespace DVBRIDGE;
 auto [pixels,words]=fixture();
 auto result=DecodeDebugCarrier(pixels,3840*4,false,words,1);
 assert(result.valid && result.packets==1 && !result.byteErrors && !result.crcErrors);
 assert(result.refresh==1 && result.l5Known);
 assert((result.l5==std::array<unsigned,4>{0,0,275,276}));
 auto flipped=pixels;
 for(unsigned y=0;y<4;++y)
   std::copy_n(pixels.data()+y*3840*4,3840*4,flipped.data()+(3-y)*3840*4);
 result=DecodeDebugCarrier(flipped,3840*4,true,words,1);
 assert(result.valid && !result.byteErrors && !result.crcErrors);
 pixels[(1024+91)*4+2]^=16; // Only second copy, one payload bit.
 result=DecodeDebugCarrier(pixels,3840*4,false,words,1);
 assert(result.byteErrors==1 && result.crcErrors==1);
 assert(!DecodeDebugCarrier({},3840*4,false,words,1).valid);
 assert(!DecodeDebugCarrier(pixels,3840*4,false,words,6).valid);
 assert(!DecodeDebugCarrier(pixels,3840*4,false,{},1).valid);
}
''')

    def test_real_gles_probe_restores_bindings_and_keeps_all_pixels(self):
        self.run_cpp(FIXTURE + r'''
#include "cores/VideoPlayer/VideoRenderers/DVBridgeDebugReadback.h"
#include <EGL/egl.h>
#include <cassert>
int main() {
 auto display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
 assert(eglInitialize(display,nullptr,nullptr) && eglBindAPI(EGL_OPENGL_ES_API));
 EGLConfig config; EGLint count;
 const EGLint attributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,
   EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};
 assert(eglChooseConfig(display,attributes,&config,1,&count) && count);
 const EGLint ca[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
 auto context=eglCreateContext(display,config,EGL_NO_CONTEXT,ca);
 const EGLint sa[]={EGL_WIDTH,3840,EGL_HEIGHT,2160,EGL_NONE};
 auto surface=eglCreatePbufferSurface(display,config,sa);
 assert(eglMakeCurrent(display,surface,surface,context));
 auto [carrier,words]=fixture();
 std::vector<uint8_t> image(3840*2160*4,0);
 for(size_t i=0;i<image.size();i+=4) {image[i]=128;image[i+1]=62;image[i+2]=8;image[i+3]=255;}
 std::copy(carrier.begin(),carrier.end(),image.begin());
 GLuint texture,framebuffer,buffer;
 glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,3840,2160,0,GL_RGBA,GL_UNSIGNED_BYTE,image.data());
 glGenFramebuffers(1,&framebuffer);glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
 glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
 assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
 glGenBuffers(1,&buffer);glBindBuffer(GL_PIXEL_PACK_BUFFER,buffer);
 glBufferData(GL_PIXEL_PACK_BUFFER,1024,nullptr,GL_STATIC_READ);
 glPixelStorei(GL_PACK_ALIGNMENT,8);glPixelStorei(GL_PACK_ROW_LENGTH,32);
 glPixelStorei(GL_PACK_SKIP_PIXELS,3);glPixelStorei(GL_PACK_SKIP_ROWS,2);
 glViewport(1,2,3,4);glScissor(5,6,7,8);glEnable(GL_SCISSOR_TEST);
 auto result=DVBRIDGE::ReadDebugCarrier(framebuffer,3840,2160,false,words,1);
 assert(result.read && result.carrier.valid && !result.carrier.byteErrors && !result.carrier.crcErrors);
 assert(result.ycc[0][0]==1000 && result.ycc[0][1]==2048 && result.ycc[0][2]==2048);
 GLint value;glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&value);assert(value==int(buffer));
 glGetIntegerv(GL_PACK_ALIGNMENT,&value);assert(value==8);
 glGetIntegerv(GL_PACK_ROW_LENGTH,&value);assert(value==32);
 glGetIntegerv(GL_PACK_SKIP_PIXELS,&value);assert(value==3);
 glGetIntegerv(GL_PACK_SKIP_ROWS,&value);assert(value==2);
 glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&value);assert(value==int(framebuffer));
 GLint viewport[4];glGetIntegerv(GL_VIEWPORT,viewport);assert(viewport[0]==1 && viewport[3]==4);
 assert(glIsEnabled(GL_SCISSOR_TEST));
 glBindBuffer(GL_PIXEL_PACK_BUFFER,0);glPixelStorei(GL_PACK_ALIGNMENT,1);
 glPixelStorei(GL_PACK_ROW_LENGTH,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);glPixelStorei(GL_PACK_SKIP_ROWS,0);
 std::vector<uint8_t> after(image.size());
 glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,after.data());
 assert(glGetError()==GL_NO_ERROR && after==image);
 glDisable(GL_SCISSOR_TEST);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,0);
 glBlitFramebuffer(0,0,3840,2160,0,2160,3840,0,GL_COLOR_BUFFER_BIT,GL_NEAREST);
 result=DVBRIDGE::ReadDebugCarrier(0,3840,2160,true,words,1);
 assert(result.read && result.carrier.valid && !result.carrier.byteErrors && !result.carrier.crcErrors);
 glDeleteBuffers(1,&buffer);glDeleteFramebuffers(1,&framebuffer);glDeleteTextures(1,&texture);
 eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
 eglDestroySurface(display,surface);eglDestroyContext(display,context);eglTerminate(display);
}
''', graphics=True)


FIXTURE = r'''
#include "utils/DVBridgeDebug.h"
#include <cassert>
#include <algorithm>
#include <vector>
#include <utility>
auto fixture() {
 std::vector<uint32_t> words(128,0);
 words[3]=0;words[4]=84; // Payload length: 71-byte header + one L5 block.
 words[6]=1;words[75]=1;words[79]=8;words[80]=5;
 words[85]=1;words[86]=19;words[87]=1;words[88]=20; // L5 275 / 276.
 uint32_t crc=0xffffffff;
 for(unsigned byte=0;byte<124;++byte) {
   crc^=words[byte]<<24;
   for(unsigned b=0;b<8;++b)crc=(crc<<1)^((crc>>31)?0x04c11db7u:0);
 }
 for(unsigned i=0;i<4;++i)words[124+i]=(crc>>(24-8*i))&255;
 std::vector<uint8_t> pixels(3840*4*4,0);
 for(unsigned index=0;index<3072;++index) {
   unsigned bit=index%1024, y=1000,c=2048;
   unsigned value=(words[bit/8]>>(7-bit%8))&1;
   c|=value^(std::popcount(y^(c>>1))&1);
   pixels[index*4]=c>>4;pixels[index*4+1]=y>>4;
   pixels[index*4+2]=(y&15)|((c&15)<<4);pixels[index*4+3]=255;
 }
 return std::pair{pixels,words};
}
'''
