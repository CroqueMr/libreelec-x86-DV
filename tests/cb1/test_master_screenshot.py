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
        diagnostics=body(shipped_code('xbmc/utils/DVBridgeDiagnosticState.h'),'class DiagnosticFailures')
        program=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeScreenshot.h')+r'''
#include <cassert>
#include <memory>
#include <utility>
#include <string>
constexpr int LOGWARNING=1;
namespace DVBRIDGE {
class DiagnosticFailures DIAGNOSTICS;
inline bool enabled=false;inline uint64_t now=0;inline unsigned logs=0;inline std::string lastStage;
bool DiagnosticsEnabled(){return enabled;}uint64_t DiagnosticNowMs(){return now;}
template<class... T>void DiagnosticLog(int,const char*,const char* stage,T...){++logs;lastStage=stage;}
}
constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=5,DVBRIDGE_MODE_SDR=7,AV_PIX_FMT_RGBA=1,AV_PIX_FMT_RGBA64LE=2,AV_PIX_FMT_BGRA=3,AV_PIX_FMT_X2BGR10LE=4;
constexpr int GL_READ_FRAMEBUFFER_BINDING=1,GL_READ_FRAMEBUFFER=2;
using GLint=int;
int bound=99,depth=0,readFormat=AV_PIX_FMT_RGBA;bool flip=false,readOK=true,mapOK=true;
void glGetIntegerv(int,int* out){*out=bound;}
void glBindFramebuffer(int,unsigned value){bound=value;}
namespace KODI::RENDERING::CAPTURE {
struct ReadbackBuffer {std::unique_ptr<uint8_t[]> pixels; unsigned width=0,height=0;int stride=0,format=0;};
bool ReadFramebufferRegion(int,int,int w,int h,int bits,bool upsideDown,ReadbackBuffer& out){
 assert(w==3840 && h==2160);depth=bits;flip=upsideDown;
 if(!readOK)return false;
 out.width=2;out.height=1;out.stride=8;out.format=readFormat;
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
 struct {DVBRIDGE::OutputMode output=DVBRIDGE::OutputMode::MasterReference;int sdrPreset=0;double sdrGamma=2.4;}m_requested;
 DVBRIDGE::DiagnosticFailures m_captureFailures;
 struct{uint64_t stream=3,picture=4,revision=5;}m_pendingIdentity;
 int m_effectiveMode=5;bool m_prepared=true,m_direct=true,m_hdr10Limited=false;unsigned m_outputBits=10;
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
 bridge.m_effectiveMode=DVBRIDGE_MODE_SDR;bridge.m_direct=true;mapOK=false;
 const int priorPQ=bridge.pqCalls;
 assert(bridge.ReadScreenshot(out));assert(bound==99 && depth==10 && flip);
 assert(bridge.pqCalls==priorPQ && out.format==AV_PIX_FMT_RGBA64LE && out.stride==-16);
 bridge.m_scanoutFramebuffer=0; // Native EGL output may be the default framebuffer.
 assert(bridge.ReadScreenshot(out) && bridge.pqCalls==priorPQ && bound==99);
 assert(depth==10 && flip && out.format==AV_PIX_FMT_RGBA64LE && out.stride==-16);
 bridge.m_direct=false;accepted=out.pixels.get();
 assert(!bridge.ReadScreenshot(out) && out.pixels.get()==accepted && bound==99);
 DVBRIDGE::enabled=true;bridge.m_prepared=false;
 for(int i=0;i<1000;++i)assert(!bridge.ReadScreenshot(out));
 assert(DVBRIDGE::logs==1 && DVBRIDGE::lastStage=="unprepared");
 DVBRIDGE::now=30000;assert(!bridge.ReadScreenshot(out));assert(DVBRIDGE::logs==2);
 bridge.m_prepared=true;bridge.m_scanout=nullptr;assert(!bridge.ReadScreenshot(out));
 assert(DVBRIDGE::lastStage=="no-scanout");
 bridge.m_scanout=&bridge.texture;bridge.m_direct=false;assert(!bridge.ReadScreenshot(out));
 assert(DVBRIDGE::lastStage=="direct-target");
 bridge.m_direct=true;readOK=false;assert(!bridge.ReadScreenshot(out));
 assert(DVBRIDGE::lastStage=="readback");
 const auto bounded=DVBRIDGE::logs;readOK=true;readFormat=99;assert(!bridge.ReadScreenshot(out));
 assert(DVBRIDGE::logs==bounded); // At most four failure reports per 30-second window.
 DVBRIDGE::now=60000;assert(!bridge.ReadScreenshot(out));
 assert(DVBRIDGE::lastStage=="unsupported-format");
 readFormat=AV_PIX_FMT_RGBA;bridge.m_requested.sdrPreset=2;bridge.m_requested.sdrGamma=NAN;
 assert(!bridge.ReadScreenshot(out));assert(DVBRIDGE::lastStage=="decode");
 assert(out.pixels.get()==accepted && bound==99);
}
'''.replace('@@BODY@@',implementation).replace('DIAGNOSTICS',diagnostics)
        with tempfile.TemporaryDirectory() as directory:
            source,binary=Path(directory)/'read.cpp',Path(directory)/'read'
            source.write_text(program)
            result=subprocess.run(['c++','-std=c++20','-O2',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_final_sdr_readback_expands_range_and_normalizes_gamma(self):
        header=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeScreenshot.h').replace('#pragma once','')
        program=header+r'''
#include <cassert>
#include <array>
int main(){
 using namespace DVBRIDGE;
 std::array<uint16_t,12> out{};
 for(unsigned bits:{8u,10u,12u})for(bool limited:{false,true}){
  const unsigned maximum=(1u<<bits)-1;
  const unsigned lo=limited ? 16u<<(bits-8) : 0;
  const unsigned hi=limited ? 235u<<(bits-8) : maximum;
  uint16_t samples[8]{};
  for(unsigned c=0;c<3;++c){samples[c]=std::lround(double(lo)*65535/maximum);
   samples[4+c]=std::lround(double(hi)*65535/maximum);}
  samples[3]=32768;samples[7]=65535;
  for(double gamma:{2.2,2.4,2.6}){
   assert(DecodeSDRScreenshot(reinterpret_cast<uint8_t*>(samples),1,2,
       SDRScreenshotFormat::RGBA16,bits,limited,gamma,out.data()));
   for(unsigned c=0;c<3;++c){assert(out[c]<=2);assert(out[4+c]>=65533);}
   assert(out[3]==32768 && out[7]==65535); // Alpha and GL row order stay intact.
  }
 }
 const uint8_t rgba[8]={255,0,0,128,0,0,255,255};
 assert(DecodeSDRScreenshot(rgba,2,1,SDRScreenshotFormat::BGRA8,8,false,2.4,out.data()));
 assert(out[0]==0 && out[2]==65535 && out[3]==32896 && out[4]==65535 && out[6]==0);
 uint32_t packed[2]={64u|(64u<<10)|(64u<<20)|(3u<<30),940u|(940u<<10)|(940u<<20)|(1u<<30)};
 assert(DecodeSDRScreenshot(reinterpret_cast<uint8_t*>(packed),2,1,
     SDRScreenshotFormat::RGB10,10,true,2.4,out.data()));
 assert(out[0]==0 && out[4]==65535 && out[3]==65535 && out[7]==65535);
 const uint16_t middle[4]={32768,32768,32768,65535};
 const double expected[3]={0.5038667822745281,0.4725,0.44289369993959327};
 int i=0;for(double gamma:{2.2,2.4,2.6}){
  assert(DecodeSDRScreenshot(reinterpret_cast<const uint8_t*>(middle),1,1,
      SDRScreenshotFormat::RGBA16,12,false,gamma,out.data()));
  assert(std::abs(double(out[0])/65535-expected[i++])<2./65535);
 }
 const auto accepted=out;
 assert(!DecodeSDRScreenshot(rgba,1,1,SDRScreenshotFormat::RGBA8,7,false,2.4,out.data()));
 assert(!DecodeSDRScreenshot(rgba,1,1,SDRScreenshotFormat::RGBA8,8,false,NAN,out.data()));
 assert(out==accepted);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source,binary=Path(directory)/'sdr.cpp',Path(directory)/'sdr'
            source.write_text(program)
            result=subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],capture_output=True,text=True)
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
            built=subprocess.run(['c++','-std=c++20','-O2',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
