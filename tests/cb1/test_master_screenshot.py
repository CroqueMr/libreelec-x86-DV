"""Decode actual Master carrier bytes only in screenshot readback."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code


class MasterScreenshot(unittest.TestCase):
    def test_native_readback_preserves_framebuffer_and_other_modes(self):
        from test_native_video_source import body
        implementation=body(shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp'),
                            'bool CDVBridgeGLES::ReadScreenshot(')
        program=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeScreenshot.h')+r'''
#include <cassert>
#include <memory>
#include <utility>
constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=5,AV_PIX_FMT_RGBA=1,AV_PIX_FMT_RGBA64LE=2;
constexpr int GL_READ_FRAMEBUFFER_BINDING=1,GL_READ_FRAMEBUFFER=2;
using GLint=int;
int bound=99,depth=0;bool flip=false,readOK=true,mapOK=true;
void glGetIntegerv(int,int* out){*out=bound;}
void glBindFramebuffer(int,unsigned value){bound=value;}
namespace KODI::RENDERING::CAPTURE {
struct ReadbackBuffer {std::unique_ptr<uint8_t[]> pixels; unsigned width=0,height=0;int stride=0,format=0;};
bool ReadFramebufferRegion(int,int,int w,int h,int bits,bool upsideDown,ReadbackBuffer& out){
 assert(w==3840 && h==2160);depth=bits;flip=upsideDown;
 if(!readOK)return false;
 out.width=2;out.height=1;out.stride=8;out.format=AV_PIX_FMT_RGBA;
 out.pixels=std::make_unique<uint8_t[]>(8);
 return true;
}}
struct pl_matrix3x3 {float m[3][3];};
struct pl_transform3x3 {pl_matrix3x3 mat;float c[3];};
struct dvbridge_color {int repr;struct {pl_matrix3x3 linear;}dovi;};
bool dvbridge_map_color(dvbridge_color* out,const void*,size_t,bool paired){
 assert(paired);out->dovi.linear={{{1,0,0},{0,1,0},{0,0,1}}};return mapOK;
}
void pl_color_repr_normalize(int*){}
pl_transform3x3 pl_color_repr_decode(int*,void*){return {{{{1,0,0},{0,1,0},{0,0,1}}},{0,0,0}};}
void pl_matrix3x3_mul(pl_matrix3x3*,const pl_matrix3x3*){}
struct CDVPlaybackInfo {enum {FEL=2};};
namespace DVBRIDGE {enum class OutputMode{MasterReference};}
struct CDVBridgeGLES {
 struct {DVBRIDGE::OutputMode output=DVBRIDGE::OutputMode::MasterReference;}m_requested;
 int m_effectiveMode=5;bool m_prepared=true,m_direct=true;
 struct Texture{struct{int w=3840,h=2160;}params;} texture;Texture* m_scanout=&texture;
 unsigned m_scanoutFramebuffer=42,m_pendingInfo=2;int pqCalls=0;
 struct {const void* Data(){return this;}size_t Size(){return 10;}}m_pendingMetadata;
 unsigned GetPQFramebuffer(){++pqCalls;return 77;}
 bool ReadScreenshot(KODI::RENDERING::CAPTURE::ReadbackBuffer& out) @@BODY@@
};
int main(){
 CDVBridgeGLES bridge;KODI::RENDERING::CAPTURE::ReadbackBuffer out;
 assert(bridge.ReadScreenshot(out));assert(bound==99 && depth==8 && flip);
 assert(out.format==AV_PIX_FMT_RGBA64LE && out.stride==-16 && bridge.pqCalls==0);
 auto* accepted=out.pixels.get();bridge.m_direct=false;
 assert(!bridge.ReadScreenshot(out) && out.pixels.get()==accepted && bound==99);
 bridge.m_direct=true;readOK=false;
 assert(!bridge.ReadScreenshot(out) && bound==99 && out.pixels.get()==accepted);
 readOK=true;mapOK=false;
 assert(!bridge.ReadScreenshot(out) && bound==99 && out.pixels.get()==accepted);
 bridge.m_effectiveMode=1;bridge.m_direct=false;
 assert(bridge.ReadScreenshot(out));assert(bound==99 && depth==16 && !flip && bridge.pqCalls==1);
 assert(out.format==AV_PIX_FMT_RGBA && out.stride==8);
}
'''.replace('@@BODY@@',implementation)
        with tempfile.TemporaryDirectory() as directory:
            source,binary=Path(directory)/'read.cpp',Path(directory)/'read'
            source.write_text(program)
            result=subprocess.run(['c++','-std=c++20','-O2',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_carrier_pairs_colours_orientation_and_input_unchanged(self):
        header = shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeScreenshot.h')
        self.assertTrue(header, 'Master screenshot decoder is missing')
        program = header + r'''
#include <cassert>
#include <cstring>
int main() {
  // Canonical limited-range YCC to PQ RGB, identity linear colour transform.
  const float decode[12]={1.16895f,0,1.68361f,-.91569f,
    1.16895f,-.18788f,-.65234f,.34746f,
    1.16895f,2.14807f,0,-1.147f};
  const float linear[9]={1,0,0,0,1,0,0,0,1};
  const auto pack=[](unsigned y,unsigned c,uint8_t* p) {
    p[0]=c>>4; p[1]=y>>4; p[2]=(y&15)|((c&15)<<4); p[3]=255;
  };
  uint8_t input[32]{};
  pack(256,2048,input); pack(256,2048,input+4);
  pack(3760,2048,input+8); pack(3760,2048,input+12);
  pack(1500,1000,input+16); pack(2000,3000,input+20);
  pack(2000,1000,input+24); pack(1500,3000,input+28);
  uint8_t original[32]; std::memcpy(original,input,sizeof input);
  uint16_t output[32]{};
  assert(DVBRIDGE::DecodeReferenceScreenshot(input,4,2,decode,linear,output));
  assert(!std::memcmp(input,original,sizeof input));
  for (int i=0;i<3;i++) {assert(output[i]<100); assert(output[8+i]>65000);}
  assert(output[3]==65535 && output[31]==65535);
  // Every pixel retains its own luma; chroma comes from the same horizontal pair.
  assert(output[16]>output[18]); assert(output[20]>output[16]);
  assert(output[24]>output[28]);
  assert(!DVBRIDGE::DecodeReferenceScreenshot(input,3,2,decode,linear,output));
  assert(!DVBRIDGE::DecodeReferenceScreenshot(nullptr,4,2,decode,linear,output));
  float identity[12]={1,0,0,0,0,1,0,0,0,0,1,0};
  pack(1000,1500,input); pack(2000,2500,input+4);
  assert(DVBRIDGE::DecodeReferenceScreenshot(input,2,1,identity,linear,output));
  assert(std::abs(int(output[0])-int(std::lround(1000.0/4095*65535)))<=1);
  assert(std::abs(int(output[1])-int(std::lround(1500.0/4095*65535)))<=1);
  assert(std::abs(int(output[2])-int(std::lround(2500.0/4095*65535)))<=1);
  assert(output[4]>output[0]);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'test.cpp', Path(directory)/'test'
            source.write_text(program)
            subprocess.run(['c++','-std=c++20','-O2',str(source),'-o',str(binary)],check=True,capture_output=True)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
